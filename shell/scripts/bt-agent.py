#!/usr/bin/env python3
"""The shell's Bluetooth pairing agent (BlueZ org.bluez.Agent1), run by BluetoothService.qml.

It registers at /org/arcticlinux/shell/agent as the default agent ("KeyboardDisplay") and
forwards every question BlueZ asks to the shell, one JSON object per line on stdout:

    {"type":"ready","default":true}
    {"type":"request","id":3,"kind":"confirm","device":"/org/bluez/hci0/dev_…","address":"AA:…",
     "name":"Pixel 9","icon":"phone","passkey":"042917","solicited":true}
    {"type":"cancel","id":3}     {"type":"released"}     {"type":"error","error":"…"}

kinds: confirm, passkey, pin, show_passkey, show_pin, authorize, service. The shell answers on
stdin: {"op":"reply","id":3,"accept":true,"value":"1234"}, {"op":"expect","address":"AA:…"}
(the user chose that device in the Bluetooth menu), {"op":"default"} (ask to be the default
agent again) or {"op":"quit"}. A question left unanswered for 90 s is cancelled.
"solicited" says the user started this: a code for a device they chose in the menu in the last
minute. Anything else (a device pairing by itself, or asking to use a service) isn't, and the
dialog then focuses its "no" button. One question at a time: another device asking while one
waits is turned down, so the one on screen can still be answered.
Services for devices that are paired and trusted are allowed without asking. PINs and
passkeys are never logged.

It re-registers when BlueZ restarts, and asks to be the default agent again when blueman's
applet (which makes itself the default agent) goes away. Needs python3-dbus and GLib from
python3-gobject; the request building and reply checks below work without them (tests).
"""
import json
import os
import sys
import time

AGENT_PATH = '/org/arcticlinux/shell/agent'
CAPABILITY = 'KeyboardDisplay'
TIMEOUT_S = 90
EXPECT_S = 60                  # a device chosen in the menu this long ago still counts as the user's

# Bluetooth service UUIDs (16-bit, in the base UUID) → what the dialog says the device wants.
SERVICES = {
    '1108': 'audio', '110a': 'audio', '110b': 'audio', '110c': 'audio', '110d': 'audio', '110e': 'audio',
    '110f': 'audio', '111e': 'audio', '111f': 'audio', '1112': 'audio', '184e': 'audio', '184f': 'audio',
    '1124': 'typing and pointing', '1812': 'typing and pointing',
    '1105': 'file transfer', '1106': 'file transfer', '1104': 'file transfer',
    '1115': 'network sharing', '1116': 'network sharing', '1117': 'network sharing',
}


def service_name(uuid):
    u = str(uuid or '').lower()
    if u.endswith('-0000-1000-8000-00805f9b34fb') and u.startswith('0000'):
        return SERVICES.get(u[4:8], 'a service')
    return 'a service'


def passkey_text(value):
    """Passkeys are shown as six digits, zero-padded (42917 → "042917")."""
    return '%06d' % int(value)


def build_request(rid, kind, device, props, **extra):
    props = props or {}
    req = {'type': 'request', 'id': rid, 'kind': kind, 'device': str(device),
           'address': str(props.get('Address', '')),
           'name': str(props.get('Alias') or props.get('Name') or props.get('Address') or 'A device'),
           'icon': str(props.get('Icon', ''))}
    if 'passkey' in extra:
        req['passkey'] = passkey_text(extra.pop('passkey'))
    req.update(extra)
    return req


def expect(expected, address, now):
    """The user chose the device at `address` in the Bluetooth menu at `now` (monotonic seconds);
    choices older than EXPECT_S are dropped."""
    for a in [a for a, t in expected.items() if now - t > EXPECT_S]:
        del expected[a]
    if address:
        expected[str(address).upper()] = now


def solicited(kind, address, expected, now):
    """Whether the user started this question: a code or PIN for a device they chose in the
    menu less than EXPECT_S ago. A pairing the other device starts (authorize) and a service
    it wants to use (service) never are."""
    if kind in ('authorize', 'service'):
        return False
    t = expected.get(str(address or '').upper())
    return t is not None and 0 <= now - t <= EXPECT_S


def check_passkey(value):
    """A typed passkey: 0-999999 as an int, else None."""
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if 0 <= n <= 999999 and str(value).strip().isdigit() else None


def check_pin(value):
    """A legacy PIN: 1-16 printable characters, else None."""
    s = str(value if value is not None else '')
    return s if 1 <= len(s) <= 16 and s.isprintable() else None


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    sys.stdout.flush()


def main():
    try:
        import dbus
        import dbus.service
        from dbus.mainloop.glib import DBusGMainLoop
        from gi.repository import GLib
    except ImportError:
        emit({'type': 'error', 'error': 'The Bluetooth agent needs python3-dbus and python3-gobject.'})
        return 2

    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    loop = GLib.MainLoop()
    pending = {}                  # id → (kind, reply, error, timer id, device)
    expected = {}                 # address → when the user chose it in the menu
    counter = [0]

    def device_props(path):
        try:
            obj = bus.get_object('org.bluez', path)
            return obj.GetAll('org.bluez.Device1', dbus_interface='org.freedesktop.DBus.Properties')
        except dbus.DBusException:
            return {}

    def rejected(name='Rejected'):
        return dbus.DBusException('org.bluez.Error.' + name, name='org.bluez.Error.' + name)

    def ask(kind, device, reply, error, **extra):
        if pending:
            error(rejected())       # one at a time: the question on screen stays answerable
            return
        counter[0] += 1
        rid = counter[0]

        def expire():
            item = pending.pop(rid, None)
            if item:
                emit({'type': 'cancel', 'id': rid})
                item[2](rejected('Canceled'))
            return False
        timer = GLib.timeout_add_seconds(TIMEOUT_S, expire)
        pending[rid] = (kind, reply, error, timer, str(device))
        props = device_props(device)
        emit(build_request(rid, kind, device, props, **extra,
                           solicited=solicited(kind, props.get('Address'), expected, time.monotonic())))

    def answer(op):
        item = pending.pop(op.get('id'), None)
        if not item:
            return
        kind, reply, error, timer, _ = item
        GLib.source_remove(timer)
        if not op.get('accept'):
            error(rejected())
        elif kind == 'passkey':
            n = check_passkey(op.get('value'))
            if n is None:
                error(rejected())
            else:
                reply(dbus.UInt32(n))
        elif kind == 'pin':
            pin = check_pin(op.get('value'))
            if pin is None:
                error(rejected())
            else:
                reply(pin)
        else:
            reply()

    class Agent(dbus.service.Object):
        @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
        def Release(self):
            emit({'type': 'released'})

        @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s', async_callbacks=('reply', 'error'))
        def RequestPinCode(self, device, reply, error):
            ask('pin', device, reply, error)

        @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
        def DisplayPinCode(self, device, pincode):
            counter[0] += 1
            emit(build_request(counter[0], 'show_pin', device, device_props(device), pin=str(pincode)))

        @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u', async_callbacks=('reply', 'error'))
        def RequestPasskey(self, device, reply, error):
            ask('passkey', device, reply, error)

        @dbus.service.method('org.bluez.Agent1', in_signature='ouq', out_signature='')
        def DisplayPasskey(self, device, passkey, entered):
            # Called again for every digit typed on the device: one request id per device.
            counter[0] += 1
            emit(build_request(counter[0], 'show_passkey', device, device_props(device), passkey=passkey, entered=int(entered)))

        @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='', async_callbacks=('reply', 'error'))
        def RequestConfirmation(self, device, passkey, reply, error):
            ask('confirm', device, reply, error, passkey=passkey)

        @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='', async_callbacks=('reply', 'error'))
        def RequestAuthorization(self, device, reply, error):
            ask('authorize', device, reply, error)

        @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='', async_callbacks=('reply', 'error'))
        def AuthorizeService(self, device, uuid, reply, error):
            props = device_props(device)
            if props.get('Paired') and props.get('Trusted'):
                reply()
                return
            ask('service', device, reply, error, service=service_name(uuid), uuid=str(uuid))

        @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
        def Cancel(self):
            for rid in list(pending):
                kind, reply, error, timer, _ = pending.pop(rid)
                GLib.source_remove(timer)
                emit({'type': 'cancel', 'id': rid})
            emit({'type': 'cancel', 'id': 0})          # also closes a "type this code" dialog

    Agent(bus, AGENT_PATH)

    def manager():
        return dbus.Interface(bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.AgentManager1')

    def register():
        try:
            manager().RegisterAgent(AGENT_PATH, CAPABILITY)
        except dbus.DBusException as e:
            if 'AlreadyExists' not in e.get_dbus_name():
                emit({'type': 'error', 'error': 'Bluetooth isn’t running.'})
                return
        make_default()

    def make_default():
        try:
            manager().RequestDefaultAgent(AGENT_PATH)
            emit({'type': 'ready', 'default': True})
        except dbus.DBusException:
            emit({'type': 'ready', 'default': False})

    def bluez_owner(owner):
        if owner:
            register()
        else:
            emit({'type': 'error', 'error': 'Bluetooth isn’t running.'})

    def blueman_owner(owner):
        if not owner:
            GLib.timeout_add(500, lambda: (make_default(), False)[1])

    bus.watch_name_owner('org.bluez', bluez_owner)
    bus.watch_name_owner('org.blueman.Applet', blueman_owner)

    buf = [b'']

    def on_stdin(fd, condition):
        chunk = os.read(fd, 4096)
        if not chunk:
            loop.quit()
            return False
        buf[0] += chunk
        *lines, buf[0] = buf[0].split(b'\n')
        for line in lines:
            try:
                op = json.loads(line.decode(errors='replace'))
            except ValueError:
                continue
            if op.get('op') == 'reply':
                answer(op)
            elif op.get('op') == 'expect':
                expect(expected, op.get('address'), time.monotonic())
            elif op.get('op') == 'default':
                make_default()
            elif op.get('op') == 'quit':
                loop.quit()
                return False
        return True

    GLib.io_add_watch(sys.stdin.fileno(), GLib.PRIORITY_DEFAULT, GLib.IO_IN | GLib.IO_HUP, on_stdin)
    try:
        loop.run()
    finally:
        try:
            manager().UnregisterAgent(AGENT_PATH)
        except dbus.DBusException:
            pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
