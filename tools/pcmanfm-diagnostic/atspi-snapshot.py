#!/usr/bin/env python3
"""Owned-process read-only AT-SPI snapshot. No imports perform bus/UI actions."""
import json
import os
from pathlib import Path
import re
import signal
import sys
import time

ACCESSIBLE = 'org.a11y.atspi.Accessible'
PROPERTIES = 'org.freedesktop.DBus.Properties'
TEXT = 'org.a11y.atspi.Text'
ACTION = 'org.a11y.atspi.Action'
MAX_NODES, MAX_DEPTH, MAX_TEXT, MAX_OUTPUT = 256, 12, 4096, 256*1024
STATES = dict(editable=7, focusable=11, focused=12, showing=25, visible=30, defunct=6)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def wire_type(value):
    typ = type(value)
    if typ.__module__.startswith('dbus'):
        return {'UInt32':'u', 'Int32':'i', 'Boolean':'b', 'String':'s', 'ObjectPath':'o'}.get(typ.__name__, 'other:'+typ.__name__)
    return {int:'host-int', bool:'host-bool', str:'host-str'}.get(typ, 'other:'+typ.__name__)


def uint(value):
    require(wire_type(value) in ('u', 'host-int') and 0 <= value < 2**32,
            'invalid typed unsigned integer (expected u)')
    return int(value)


def nonnegative_int(value):
    require(wire_type(value) in ('i', 'host-int') and 0 <= value < 2**31,
            'invalid typed signed integer (expected i)')
    return int(value)


def boolean(value):
    require(wire_type(value) in ('b', 'host-bool') and int(value) in (0, 1), 'invalid typed Boolean (expected b)')
    return bool(value)


def optional(call, *args):
    try:
        return dict(status='observed', value=call(*args))
    except Exception as exc:
        name = exc.get_dbus_name() if hasattr(exc, 'get_dbus_name') else None
        if name in ('org.freedesktop.DBus.Error.UnknownMethod', 'org.freedesktop.DBus.Error.UnknownInterface',
                    'org.freedesktop.DBus.Error.UnknownProperty'):
            return dict(status='unsupported', dbus_error=name, detail=str(exc))
        raise


def state_words(words):
    require(isinstance(words, (list, tuple)) and len(words) == 2, 'invalid state word count')
    words = [uint(word) for word in words]
    value = words[0] | (words[1] << 32)
    return dict(words=words, **{name: bool(value & (1 << index)) for name, index in STATES.items()})


def object_ref(value):
    require(isinstance(value, (tuple, list)) and len(value) == 2, 'invalid accessible reference')
    bus, path = value
    require(isinstance(bus, str) and re.fullmatch(r':[0-9]+\.[0-9]+', bus), 'expected unique a11y bus name')
    require(isinstance(path, str) and re.fullmatch(r'/(?:[A-Za-z0-9_]+(?:/[A-Za-z0-9_]+)*)?', path),
            'invalid accessible object path')
    return str(bus), str(path)


def identity(proof):
    require(type(proof.get('pid')) is int and proof['pid'] > 1 and type(proof.get('start_ticks')) is int,
            'invalid owned process identity')
    proc = Path('/proc') / str(proof['pid'])
    require(proc.stat().st_uid == os.getuid(), 'snapshot target is another UID')
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    require(fields[0] not in ('Z', 'X') and int(fields[19]) == proof['start_ticks']
            and str((proc / 'exe').resolve(strict=True)) == proof['executable'], 'target exited/recycled/changed executable')
    import hashlib
    require(hashlib.sha256(Path(proof['executable']).read_bytes()).hexdigest() == proof['executable_sha256'],
            'target executable bytes changed')


def snapshot(proof, connection, started=None):
    """connection is a typed dbus.BusConnection; all methods used are reads."""
    started = time.monotonic() if started is None else started
    nodes = []
    def call(bus, path, interface, method, *args):
        require(time.monotonic() - started < 5, 'snapshot deadline exceeded')
        proxy = connection.get_object(bus, path, introspect=False)
        return proxy.get_dbus_method(method, interface)(*args, timeout=.3)
    def pid(bus):
        owner = call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                     'org.freedesktop.DBus', 'GetNameOwner', bus)
        require(str(owner) == bus, 'a11y unique owner changed')
        return uint(call('org.freedesktop.DBus', '/org/freedesktop/DBus',
                         'org.freedesktop.DBus', 'GetConnectionUnixProcessID', bus))
    identity(proof)
    roots = call('org.a11y.atspi.Registry', '/org/a11y/atspi/accessible/root', ACCESSIBLE, 'GetChildren')
    require(isinstance(roots, (list, tuple)) and len(roots) <= MAX_NODES, 'invalid registry root bounds')
    owned = []
    for item in roots:
        bus, path = object_ref(item)
        if pid(bus) == proof['pid']:
            owned.append((bus, path))
    require(len(owned) <= 1, 'ambiguous owned accessible application')
    if not owned:
        return dict(status='unavailable', reason='owned application is not exported', nodes=[])
    bus, root = owned[0]
    require(pid(bus) == proof['pid'], 'owned application PID changed before traversal')
    identity(proof)
    queue, seen = [(root, [], 0)], set()
    frames = []
    candidates = []
    while queue:
        path, ancestors, depth = queue.pop(0)
        require(path not in seen and len(seen) < MAX_NODES and depth <= MAX_DEPTH,
                'accessible cycle/tree/depth bound exceeded')
        seen.add(path)
        require(pid(bus) == proof['pid'], 'owned bus PID changed during traversal')
        raw_role = call(bus, path, ACCESSIBLE, 'GetRole'); role = uint(raw_role)
        raw_words = call(bus, path, ACCESSIBLE, 'GetState'); words = state_words(raw_words)
        interfaces = call(bus, path, ACCESSIBLE, 'GetInterfaces')
        require(isinstance(interfaces, (list, tuple)) and len(interfaces) <= 32
                and all(isinstance(x, str) and len(x) <= 128 for x in interfaces), 'invalid interface list')
        props = {}
        for name in ('Name', 'Description'):
            value = call(bus, path, PROPERTIES, 'Get', ACCESSIBLE, name)
            require(isinstance(value, str) and len(value) <= MAX_TEXT, 'accessible string bound exceeded')
            props[name.lower()] = str(value)
        node = dict(bus=bus, path=path, ancestors=ancestors, role=role,
                    state=words, interfaces=list(map(str, interfaces)),
                    typed_fields=dict(role=wire_type(raw_role), state_words=[wire_type(x) for x in raw_words]), **props)
        if role == 23 and words['showing'] and words['visible']:
            frames.append(path)
        # GtkEntry is AT-SPI TEXT or ENTRY depending on the bridge; description is evidence, not a localized ID.
        if role in (61, 79) and words['showing'] and words['visible'] and words['editable'] and TEXT in interfaces:
            raw_count = call(bus, path, PROPERTIES, 'Get', TEXT, 'CharacterCount')
            count = nonnegative_int(raw_count); node['typed_fields']['character_count'] = wire_type(raw_count)
            require(count <= MAX_TEXT, 'owned entry text exceeds bound')
            value = call(bus, path, TEXT, 'GetText', 0, count)
            require(isinstance(value, str) and len(value) == count and len(value.encode()) <= MAX_TEXT*4,
                    'owned entry text/count differs')
            node['text'] = str(value)
            caret = call(bus, path, PROPERTIES, 'Get', TEXT, 'CaretOffset')
            node['caret'] = nonnegative_int(caret); node['typed_fields']['caret'] = wire_type(caret)
            require(node['caret'] <= count, 'invalid entry caret')
            selections = optional(call, bus, path, TEXT, 'GetNSelections')
            node['selections'] = []
            node['selections_status'] = selections['status']
            if selections['status'] == 'observed':
                selection_count = nonnegative_int(selections['value'])
                require(selection_count <= 8, 'selection count exceeds bound')
                for index in range(selection_count):
                    selection = optional(call, bus, path, TEXT, 'GetSelection', index)
                    if selection['status'] != 'observed':
                        node['selections_status'] = selection; break
                    value = selection['value']
                    require(isinstance(value, (list, tuple)) and len(value) == 2, 'invalid text selection')
                    bounds = [nonnegative_int(x) for x in value]
                    require(bounds[0] <= bounds[1] <= count, 'selection outside entry')
                    node['selections'].append(bounds)
            else:
                node['selections_status'] = selections
            if ACTION in interfaces:
                actions = optional(call, bus, path, ACTION, 'GetActions')
                if actions['status'] == 'observed':
                    value = actions['value']
                    require(isinstance(value, (tuple, list)) and len(value) <= 16, 'action bound exceeded')
                    require(all(isinstance(a, (tuple, list)) and len(a) == 3
                                and all(isinstance(x, str) and len(x) <= MAX_TEXT for x in a) for a in value),
                            'invalid action descriptions')
                    node['actions'] = [list(map(str, a)) for a in value]
                else:
                    node['actions_status'] = actions
            else:
                node['actions_status'] = 'unsupported interface'
            candidates.append(node)
        nodes.append(node)
        # Hidden menus/completion widgets are retained as nodes, but their large hidden subtrees are not read.
        if role != 75 and not (words['showing'] and words['visible']):
            continue
        children = call(bus, path, ACCESSIBLE, 'GetChildren')
        require(isinstance(children, (tuple, list)) and len(children) <= MAX_NODES, 'child count exceeds bound')
        for child in children:
            child_bus, child_path = object_ref(child)
            require(child_bus == bus, 'cross-application child reference refused')
            queue.append((child_path, ancestors+[path], depth+1))
    require(pid(bus) == proof['pid'], 'owned bus PID changed after snapshot')
    identity(proof)
    require(len(frames) <= 1, 'ambiguous owned accessible frame')
    candidates = [n for n in candidates if any(f in n['ancestors'] for f in frames)
                  and n['description'] == 'Folder location bar']
    require(len(candidates) <= 1, 'ambiguous owned editable entry')
    return dict(status='observed' if len(frames) == len(candidates) == 1 else 'unavailable',
                reason=None if candidates else 'owned frame/location-specific description unavailable or not recognized in this locale',
                unique_bus=bus, process=proof, frames=frames, entry=candidates[0] if candidates else None,
                nodes=nodes, elapsed_seconds=time.monotonic()-started)


def bus_snapshot(proof, dbus, started):
    bus = dbus.SessionBus(private=True)
    service = bus.get_object('org.a11y.Bus', '/org/a11y/bus', introspect=False)
    try:
        enabled = service.get_dbus_method('Get', PROPERTIES)('org.a11y.Status', 'IsEnabled', timeout=.3)
    except Exception as exc:
        name=exc.get_dbus_name() if hasattr(exc,'get_dbus_name') else None
        if name in ('org.freedesktop.DBus.Error.ServiceUnknown','org.freedesktop.DBus.Error.NameHasNoOwner'):
            return dict(status='unavailable',reason='actual a11y service has no owner',dbus_error=name)
        raise
    enabled_value = boolean(enabled)
    if not enabled_value:
        return dict(status='unavailable',reason='actual a11y IsEnabled is false; no enabling attempted',
                    a11y_enabled_observed=False,a11y_enabled_wire_type=wire_type(enabled))
    address = service.get_dbus_method('GetAddress', 'org.a11y.Bus')(timeout=.3)
    require(isinstance(address, str) and address.startswith('unix:') and ';' not in address
            and len(address) < 2048, 'invalid a11y bus address')
    connection = dbus.bus.BusConnection(address)
    result = snapshot(proof, connection, started)
    result['a11y_enabled_observed'] = enabled_value
    result['a11y_enabled_wire_type'] = wire_type(enabled)
    return result


def main():
    started = time.monotonic()
    signal.signal(signal.SIGALRM, lambda *_: (_ for _ in ()).throw(TimeoutError('snapshot deadline exceeded')))
    signal.setitimer(signal.ITIMER_REAL, 5)
    try:
        require(len(sys.argv) == 2 and os.geteuid() > 0, 'requires one proof as desktop UID')
        proof = json.loads(sys.argv[1]); identity(proof)
        try:
            import dbus
        except ImportError as exc:
            result = dict(status='unavailable', reason='shipped Python D-Bus import unavailable: '+str(exc))
        else:
            result = bus_snapshot(proof,dbus,started)
        identity(proof)
        result['locale'] = {name:os.environ.get(name) for name in ('LANG','LC_ALL','LC_MESSAGES')}
        result.update(monotonic_start_seconds=started, monotonic_end_seconds=time.monotonic())
        status = 0
    except Exception as exc:
        result = dict(status='collector-error', error=type(exc).__name__+': '+str(exc),
                      monotonic_start_seconds=started, monotonic_end_seconds=time.monotonic())
        status = 1
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
    text = json.dumps(result, ensure_ascii=False)
    require(len(text.encode()) <= MAX_OUTPUT, 'snapshot output exceeded bound')
    print(text, flush=True)
    return status


if __name__ == '__main__':
    raise SystemExit(main())
