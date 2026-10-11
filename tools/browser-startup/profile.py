#!/usr/bin/env python3
"""Private, finite startup phase observations in a separate disposable VM boot.

This diagnostic does not establish benchmark acceptance or remove application
sandboxing. It probes existing exported functions, not replacement functions.
No URLs, titles, transcripts, DBus payloads, arguments or raw trace are saved.
"""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import select
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid

MAX_EVENTS = 8192
MAX_LINE = 16384
MAX_ELF = 512 * 1024 * 1024
APPIDS = ('org.gnome.epiphany', 'epiphany')
SOURCE_SHA = '326690f173d4dc4f049f43e046c8380e66825a07'
LIBRARIES = {
    'gio': ('libgio-2.0.so', 'glib2'),
    'glib': ('libglib-2.0.so', 'glib2'),
    'gtk': ('libgtk-4.so', 'gtk4'),
    'adwaita': ('libadwaita-1.so', 'libadwaita'),
    'webkit': ('libwebkitgtk-6.0.so', 'webkitgtk6.0'),
    'keyring': ('libsecret-1.so', 'libsecret'),
}
# (library, function, DBus argument register layout). Optional absence is
# reported explicitly; another symbol/offset is never substituted.
PHASES = {
    'application_run': ('gio', 'g_application_run', None),
    'application_register': ('gio', 'g_application_register', None),
    'profile_helper_spawn': ('glib', 'g_spawn_sync', None),
    'gtk_init': ('gtk', 'gtk_init', None),
    'gtk_init_check': ('gtk', 'gtk_init_check', None),
    'adwaita_init': ('adwaita', 'adw_init', None),
    'window_present': ('gtk', 'gtk_window_present', None),
    'webkit_network_session': ('webkit', 'webkit_network_session_new', None),
    'webkit_context': ('webkit', 'webkit_web_context_new', None),
    'webkit_load_uri': ('webkit', 'webkit_web_view_load_uri', None),
    'secret_sync_get': ('keyring', 'secret_service_get_sync', None),
    'secret_async_get': ('keyring', 'secret_service_get', None),
    'dbus_call_sync': ('gio', 'g_dbus_connection_call_sync', ('si', 'cx', 'r8')),
    'dbus_call_async': ('gio', 'g_dbus_connection_call', ('si', 'cx', 'r8')),
    'dbus_proxy_sync': ('gio', 'g_dbus_proxy_new_sync', ('cx', 'r9', None)),
    'dbus_bus_proxy_sync': ('gio', 'g_dbus_proxy_new_for_bus_sync', ('cx', 'r9', None)),
}
DESTINATIONS = {
    'org.freedesktop.portal.Desktop': 'desktop_portal',
    'org.freedesktop.impl.portal.desktop.gtk': 'gtk_portal_backend',
    'org.freedesktop.impl.portal.desktop.wlr': 'wlr_portal_backend',
    'org.freedesktop.secrets': 'secret_service',
    'org.freedesktop.DBus': 'session_bus',
    'org.a11y.Bus': 'accessibility_bus',
    'org.gnome.Epiphany': 'browser_single_instance',
    'org.freedesktop.NetworkManager': 'network_manager',
}
INTERFACES = {
    'org.freedesktop.portal.Settings': 'settings',
    'org.freedesktop.portal.PermissionStore': 'permission_store',
    'org.freedesktop.impl.portal.PermissionStore': 'permission_store',
    'org.freedesktop.portal.FileChooser': 'file_chooser',
    'org.freedesktop.portal.Camera': 'camera',
    'org.freedesktop.portal.Device': 'device',
    'org.freedesktop.DBus.Properties': 'properties',
    'org.freedesktop.Secret.Service': 'secret_service',
    'org.freedesktop.DBus': 'session_bus',
}
METHODS = {name: name.lower() for name in (
    'Read', 'ReadAll', 'Get', 'GetAll', 'Set', 'Lookup', 'SearchItems',
    'OpenSession', 'GetSecrets', 'AccessCamera', 'OpenFile', 'SaveFile',
    'GetNameOwner', 'NameHasOwner', 'StartServiceByName', 'RequestName')}


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def digest(path):
    with path.open('rb') as stream:
        value = hashlib.file_digest(stream, 'sha256').hexdigest()
    return value


def file_identity(path):
    value = path.stat()
    return value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns


def exported_offset(raw, name):
    """Resolve one real exported x86_64 function in the immutable file bytes."""
    require(64 <= len(raw) <= MAX_ELF and raw[:6] == b'\x7fELF\x02\x01', 'elf_layout')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    require(header[2] == 62 and header[9] == 56 and header[11] == 64, 'elf_abi')
    require(header[5] + header[10] * 56 <= len(raw)
            and header[6] + header[12] * 64 <= len(raw), 'elf_tables')
    loads = [struct.unpack_from('<IIQQQQQQ', raw, header[5] + n * 56)
             for n in range(header[10])]
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, header[6] + n * 64)
                for n in range(header[12])]
    matches = []
    for section in sections:
        if section[1] != 11:
            continue
        require(section[9] == 24 and section[5] % 24 == 0
                and section[6] < len(sections)
                and section[4] + section[5] <= len(raw), 'elf_dynamic_symbols')
        strings = sections[section[6]]
        require(strings[4] + strings[5] <= len(raw), 'elf_dynamic_strings')
        table = raw[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], 24):
            string, info, _, index, address, _ = struct.unpack_from('<IBBHQQ', raw, offset)
            require(string < len(table), 'elf_symbol_name')
            end = table.find(b'\0', string)
            require(end >= 0, 'elf_symbol_name')
            if table[string:end] == name.encode('ascii') and index and info & 15 == 2:
                matches.append(address)
    if not matches:
        return None
    require(len(matches) == 1, 'elf_symbol_ambiguous')
    segments = [p for p in loads if p[0] == 1 and p[1] & 1
                and p[3] <= matches[0] < p[3] + p[5]
                and p[2] + p[5] <= len(raw)]
    require(len(segments) == 1, 'elf_symbol_executable_load')
    return matches[0] - segments[0][3] + segments[0][2]


def bus_label(body, field, table, kind):
    # The probe reads service/interface/method identifiers, never DBus bodies.
    # Even unknown identifiers are discarded after grammar validation.
    pattern = rf'\b{field}="([^"\\]{{0,255}})"'
    value = re.search(pattern, body)
    if value is None:
        require(re.search(rf'\b{field}=\(fault\)', body) is not None, 'trace_bus_field')
        return 'unreadable_identifier'
    value = value[1]
    valid = (re.fullmatch(r':?[A-Za-z0-9_.-]{1,255}', value) if kind == 'destination'
             else re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]{0,254}', value))
    require(valid is not None, 'trace_bus_identifier')
    return table.get(value, 'other_identifier')


def parse_event(line):
    require(len(line) <= MAX_LINE, 'trace_line_limit')
    value = re.search(r'-(\d+)\s+\[\d+\].*?\s(\d+)\.(\d{1,9}):\s+'
                      r'([a-z_]+)_(enter|return):\s+(.*)$', line)
    require(value is not None and value[4] in PHASES, 'trace_event_shape')
    fraction = value[3]
    record = dict(tid=int(value[1]), timestamp_ns=int(value[2]) * 10**9
                  + int(fraction.ljust(9, '0')), timestamp_resolution_ns=10**(9-len(fraction)),
                  phase=value[4], point=value[5])
    require(record['tid'] > 0, 'trace_tid')
    registers = PHASES[value[4]][2]
    if registers and value[5] == 'enter':
        record['destination'] = bus_label(value[6], 'destination', DESTINATIONS, 'destination')
        record['interface'] = bus_label(value[6], 'interface', INTERFACES, 'interface')
        record['method'] = (bus_label(value[6], 'method', METHODS, 'method')
                            if registers[2] else 'proxy_construction')
    return record


def spans(events, started_ns, stopped_ns):
    require(0 < started_ns <= stopped_ns and len(events) <= MAX_EVENTS, 'span_bounds')
    active, result = {}, []
    # File descriptor order preserves per-thread nesting; sort only the final
    # typed report, never reorder entry/return events for pairing.
    for event in events:
        require(started_ns <= event['timestamp_ns'] <= stopped_ns, 'span_timestamp')
        key = event['tid'], event['phase']
        if event['point'] == 'enter':
            active.setdefault(key, []).append(event)
        else:
            require(active.get(key), 'span_unmatched_return')
            entry = active[key].pop()
            require(entry['timestamp_ns'] <= event['timestamp_ns'], 'span_order')
            result.append(dict(entry, end_timestamp_ns=event['timestamp_ns'], completed=True,
                               elapsed_from_exec_gate_ns=entry['timestamp_ns'] - started_ns,
                               duration_ns=event['timestamp_ns'] - entry['timestamp_ns']))
    for stack in active.values():
        for entry in stack:
            result.append(dict(entry, end_timestamp_ns=None, completed=False, duration_ns=None,
                               elapsed_from_exec_gate_ns=entry['timestamp_ns'] - started_ns))
    return sorted(result, key=lambda item: (item['timestamp_ns'], item['tid'], item['phase']))


def proc_identity(pid, uid):
    path = Path('/proc') / str(pid)
    raw = (path / 'stat').read_text().rsplit(')', 1)[1].split()
    require(path.stat().st_uid == uid and raw[0] not in ('X', 'Z'), 'owned_process_identity')
    return int(raw[19]), raw[0]


def process_record(pid):
    path = Path('/proc') / str(pid)
    raw = (path / 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, uid=path.stat().st_uid, state=raw[0], ppid=int(raw[1]),
                pgrp=int(raw[2]), session=int(raw[3]), start_ticks=int(raw[19]))


def same_live_process(record):
    try:
        current = process_record(record['pid'])
        return (current['start_ticks'] == record['start_ticks'] and current['uid'] == record['uid']
                and current['state'] not in ('X', 'Z'))
    except (OSError, ValueError, IndexError):
        return False


def owned_scope(wrapper, gate):
    """Bind live descendants and same-session processes before closing the UI."""
    anchors = {record['pid']: record for record in (wrapper, gate) if record and same_live_process(record)}
    if not anchors:
        return []
    records = {}
    for path in Path('/proc').glob('[0-9]*'):
        try:
            value = process_record(int(path.name))
            if value['state'] not in ('X', 'Z'):
                records[value['pid']] = value
        except (OSError, ValueError, IndexError):
            continue
    # The new session is created by this exact Popen, not borrowed from the
    # desktop. Recheck the original wrapper generation before using its ID.
    scope = dict(anchors)
    if wrapper and same_live_process(wrapper):
        require(wrapper['session'] == wrapper['pid'] and wrapper['pgrp'] == wrapper['pid'], 'owned_session_binding')
        scope.update({pid: value for pid, value in records.items() if value['session'] == wrapper['pid']})
    while True:
        children = {pid: value for pid, value in records.items() if value['ppid'] in scope and pid not in scope}
        if not children:
            break
        scope.update(children)
    require(len(scope) <= 1024, 'owned_scope_limit')
    return list(scope.values())


def stop_owned_scope(records, child):
    errors = []
    for sig in (signal.SIGCONT, signal.SIGTERM, signal.SIGKILL):
        for record in records:
            if same_live_process(record):
                try:
                    os.kill(record['pid'], sig)
                except ProcessLookupError:
                    pass
                except OSError:
                    errors.append('owned_signal_failed')
        if sig != signal.SIGCONT:
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline and any(same_live_process(record) for record in records):
                time.sleep(.02)
    if child:
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            errors.append('owned_wrapper_not_reaped')
        if child.stdout:
            child.stdout.close()
    require(not errors and not any(same_live_process(record) for record in records), 'owned_process_cleanup_failed')


class PhaseProbe:
    def __init__(self, causal, root, libraries, uid):
        self.causal, self.root, self.libraries, self.uid = causal, root, libraries, uid
        self.group = 'arctic_browser_' + uuid.uuid4().hex
        self.instance = self.root / 'instances' / self.group
        self.registered, self.events, self.absent, self.readbacks = [], [], [], {}
        self.stopped, self.finish_requested, self.drained = threading.Event(), threading.Event(), threading.Event()
        self.failure = None
        self.fd, self.thread, self.created = None, None, False
        self.pending = b''

    def __enter__(self):
        try:
            with self.causal.deferred_termination():
                self.instance.mkdir(); self.created = True
            (self.instance / 'tracing_on').write_text('0')
            (self.instance / 'trace_clock').write_text('mono_raw')
            require('[mono_raw]' in (self.instance / 'trace_clock').read_text(), 'trace_clock')
            for name, value in [('buffer_size_kb', '256'), ('options/overwrite', '0'),
                                ('options/context-info', '1'), ('options/event-fork', '1')]:
                (self.instance / name).write_text(value)
            require((self.instance / 'options/event-fork').read_text().strip() == '1', 'trace_fork')
            if (self.instance / 'options/record-tgid').exists():
                (self.instance / 'options/record-tgid').write_text('0')
            if (self.instance / 'options/nsecs').exists():
                (self.instance / 'options/nsecs').write_text('1')
            for phase, (library, symbol, registers) in PHASES.items():
                path = self.libraries[library]['path']
                offset = self.libraries[library]['symbols'][symbol]
                if offset is None:
                    self.absent.append(phase); continue
                for point in ('enter', 'return'):
                    name = phase + '_' + point
                    command = ('p:' if point == 'enter' else 'r:') + f'{self.group}/{name} {path}:0x{offset:x}'
                    if registers and point == 'enter':
                        command += f' destination=+0(%{registers[0]}):string interface=+0(%{registers[1]}):string'
                        if registers[2]:
                            command += f' method=+0(%{registers[2]}):string'
                    with self.causal.deferred_termination():
                        self.registered.append(name)
                        self.causal.write_uprobe_command(self.root, command + '\n')
                    event = self.instance / 'events' / self.group / name
                    (event / 'enable').write_text('1')
                    # Format bytes describe fixed collector fields only. No
                    # raw trace or process-controlled string is preserved.
                    format_raw = (event / 'format').read_bytes()
                    require(0 < len(format_raw) <= MAX_LINE, 'trace_format_size')
                    self.readbacks[name] = hashlib.sha256(format_raw).hexdigest()
            require('application_run' not in self.absent and 'window_present' not in self.absent
                    and 'dbus_call_sync' not in self.absent, 'required_export_absent')
            with self.causal.deferred_termination():
                self.fd = os.open(self.instance / 'trace_pipe', os.O_RDONLY | os.O_NONBLOCK)
                self.thread = threading.Thread(target=self._read, daemon=True)
                self.thread.start()
            self.causal.loss_counts(self.instance)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def start(self, pid, start_ticks):
        require(proc_identity(pid, self.uid) == (start_ticks, 'T'), 'exec_gate_identity')
        (self.instance / 'set_event_pid').write_text(str(pid))
        require((self.instance / 'set_event_pid').read_text().split() == [str(pid)], 'trace_pid_filter')
        self.owner = dict(pid=pid, start_ticks=start_ticks, uid=self.uid)
        (self.instance / 'tracing_on').write_text('1')

    def _read(self):
        try:
            while not self.stopped.is_set():
                if not select.select([self.fd], [], [], .05)[0]:
                    if self.finish_requested.is_set():
                        require(not self.pending, 'trace_partial_line')
                        self.drained.set()
                        return
                    continue
                try:
                    self.pending += os.read(self.fd, 65536)
                except BlockingIOError:
                    continue
                require(len(self.pending) <= 128 * 1024, 'trace_buffer_limit')
                while b'\n' in self.pending:
                    line, self.pending = self.pending.split(b'\n', 1)
                    if line and not line.startswith(b'#'):
                        require(len(self.events) < MAX_EVENTS, 'trace_event_limit')
                        self.events.append(parse_event(line.decode('ascii')))
        except BaseException:
            # No raw text or exception interpolation may enter the report.
            self.failure = 'trace_reader_failed'

    def stop(self):
        (self.instance / 'tracing_on').write_text('0')
        # A zero overrun count is not a drain acknowledgement. The reader
        # must explicitly observe an empty pipe after tracing is disabled.
        self.finish_requested.set()
        require(self.drained.wait(timeout=2), 'trace_drain_timeout')
        self.thread.join(timeout=2)
        require(not self.thread.is_alive() and self.failure is None and not self.pending,
                'trace_reader_completion')
        self.causal.loss_counts(self.instance)
        for name, expected in self.readbacks.items():
            require(digest(self.instance / 'events' / self.group / name / 'format') == expected,
                    'trace_format_changed')

    def __exit__(self, *unused):
        errors = []
        def cleanup(action):
            try:
                action()
            except BaseException:
                errors.append('owned_trace_cleanup_failed')
        with self.causal.deferred_termination():
            if self.created and self.instance.exists():
                cleanup(lambda: (self.instance / 'tracing_on').write_text('0'))
            self.stopped.set()
            if self.thread:
                cleanup(lambda: self.thread.join(timeout=2))
                if self.thread.is_alive():
                    errors.append('owned_reader_remains')
            if self.fd is not None:
                cleanup(lambda: os.close(self.fd)); self.fd = None
            if self.created and self.instance.exists():
                for name in self.registered:
                    enable = self.instance / 'events' / self.group / name / 'enable'
                    if enable.exists():
                        cleanup(lambda enable=enable: enable.write_text('0'))
                cleanup(self.instance.rmdir)
            for name in self.registered:
                if (self.root / 'events' / self.group / name).exists():
                    cleanup(lambda name=name: self.causal.write_uprobe_command(
                        self.root, '-:' + self.group + '/' + name + '\n'))
            self.registered.clear()
        require(not errors, 'owned_trace_cleanup_failed')


def load_module(path, expected, name):
    require(path.parent == Path('/run/t') and path.is_file() and not path.is_symlink()
            and path.stat().st_uid == 0 and digest(path) == expected, 'module_binding')
    # Execute the exact validated bytes, rather than reopening a file after
    # accepting its digest.
    import types
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected, 'module_binding')
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def inventory(context):
    result = {}
    for package, expected in context['packages'].items():
        raw = subprocess.check_output(['rpm', '-q', '--qf', '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}', package],
                                      text=True, timeout=30)
        require(raw == expected, 'runtime_package_binding')
    # ldd is limited to the already verified, exact RPM-owned browser binary.
    browser = Path('/usr/bin/epiphany').resolve(strict=True)
    require(str(browser) in ('/usr/bin/epiphany', '/usr/libexec/epiphany'), 'browser_binary_path')
    owner = subprocess.check_output(['rpm', '-qf', '--qf', '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}', str(browser)],
                                    text=True, timeout=30)
    require(owner == context['packages']['epiphany-runtime'], 'browser_binary_owner')
    value = subprocess.run(['rpm', '-Vf', str(browser)], capture_output=True, timeout=60)
    require(value.returncode == 0 and not value.stdout and not value.stderr, 'browser_rpm_verification')
    browser_identity = file_identity(browser)
    require(64 <= browser_identity[2] <= MAX_ELF, 'browser_elf_size')
    browser_raw = browser.read_bytes()
    require(file_identity(browser) == browser_identity and browser_raw[:6] == b'\x7fELF\x02\x01'
            and struct.unpack_from('<H', browser_raw, 18)[0] == 62, 'browser_elf_binding')
    result['browser'] = dict(path=str(browser), owner=owner, bytes=len(browser_raw),
                             sha256=hashlib.sha256(browser_raw).hexdigest(),
                             file_identity=list(browser_identity))
    paths = re.findall(r'=>\s+(/(?:usr/)?lib64/[A-Za-z0-9_.+-]+)\s+\(',
                       subprocess.check_output(['ldd', str(browser)], text=True, timeout=30))
    verified = set()
    for ident, (prefix, package) in LIBRARIES.items():
        matches = {str(Path(path).resolve(strict=True)) for path in paths
                   if Path(path).name.startswith(prefix)}
        require(len(matches) == 1, 'runtime_library_ambiguity')
        path = Path(matches.pop())
        require(path.parent == Path('/usr/lib64') and path.is_file() and not path.is_symlink(), 'runtime_library_path')
        actual_owner = subprocess.check_output(['rpm', '-qf', '--qf', '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}', str(path)],
                                               text=True, timeout=30)
        require(actual_owner == context['packages'][package], 'runtime_library_owner')
        if package not in verified:
            value = subprocess.run(['rpm', '-Vf', str(path)], capture_output=True, timeout=60)
            require(value.returncode == 0 and not value.stdout and not value.stderr, 'runtime_library_rpm_verification')
            verified.add(package)
        before = file_identity(path)
        raw = path.read_bytes()
        require(len(raw) <= MAX_ELF and file_identity(path) == before, 'runtime_library_changed')
        symbols = {symbol: exported_offset(raw, symbol) for lib, symbol, _ in PHASES.values() if lib == ident}
        result[ident] = dict(path=str(path), owner=actual_owner, bytes=len(raw),
                             sha256=hashlib.sha256(raw).hexdigest(), symbols=symbols,
                             file_identity=list(before))
    return result


GATE = ('import os,signal;print(os.getpid(),flush=True);'
        'fd=os.open("/dev/null",os.O_WRONLY);os.dup2(fd,1);os.close(fd);'
        'os.kill(os.getpid(),signal.SIGSTOP);'
        'os.execv("/usr/bin/epiphany",["epiphany","--new-window",__import__("sys").argv[1]])')


def launch(prefix, guest, causal, lower, libraries, workload, hold_seconds):
    uid = pwd.getpwnam(prefix[2]).pw_uid
    child, wrapper, owner, windows = None, None, None, []
    try:
        with guest.NativeClientQuery(prefix, raw_clock=True) as observer, PhaseProbe(causal, lower.root, libraries, uid) as phases:
            before = set(observer.query())
            require(not any(str(value.get('appid') or value.get('app_id') or '').lower() in APPIDS
                            for value in observer.query().values()), 'browser_window_exists')
            with causal.deferred_termination():
                child = subprocess.Popen(prefix + ['python3', '-u', '-c', GATE, workload['url']],
                                         stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, start_new_session=True)
                wrapper = process_record(child.pid)
                require(wrapper['session'] == child.pid and wrapper['pgrp'] == child.pid, 'owned_wrapper_session')
            require(select.select([child.stdout], [], [], 10)[0], 'exec_gate_timeout')
            line = child.stdout.readline(32)
            require(re.fullmatch(rb'[1-9][0-9]{0,8}\n', line) is not None, 'exec_gate_pid')
            with causal.deferred_termination():
                pid = int(line)
                first_ticks, _ = proc_identity(pid, uid)
                owner = dict(pid=pid, start_ticks=first_ticks, uid=uid)
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                start_ticks, state = proc_identity(pid, uid)
                require(start_ticks == first_ticks, 'exec_gate_pid_reuse')
                if state == 'T':
                    break
                time.sleep(.01)
            require(state == 'T', 'exec_gate_not_stopped')
            owner = dict(pid=pid, start_ticks=start_ticks, uid=uid)
            phases.start(pid, start_ticks)
            started_ns = observer.now_ns()
            observer.begin_observation(before, APPIDS, started_ns, 120, guest.ROLE_POLL_SECONDS)
            os.kill(pid, signal.SIGCONT)
            observed = observer.finish_observation(child, started_ns, 120)
            require(observed is not None, 'browser_map_timeout')
            windows = observed['windows']
            lo, hi, proof = lower.bound(windows, started_ns, observed['lower_ns'], observed['upper_ns'], APPIDS)
            time.sleep(hold_seconds)
            after = observer.query()
            require(any(str(window['id']) in after for window in windows), 'browser_not_persistent')
            require(proc_identity(pid, uid)[0] == start_ticks
                    and str((Path('/proc') / str(pid) / 'exe').resolve(strict=True)) == libraries['browser']['path']
                    and file_identity(Path(libraries['browser']['path'])) == tuple(libraries['browser']['file_identity']),
                    'mapped_browser_executable_binding')
            phases.stop()
            stopped_ns = observer.now_ns()
            require(any(e['phase'] == 'application_run' and e['point'] == 'enter' for e in phases.events)
                    and any(e['phase'] == 'window_present' and e['point'] == 'enter' for e in phases.events),
                    'required_phase_not_observed')
            return dict(started_monotonic_raw_ns=started_ns, stopped_monotonic_raw_ns=stopped_ns,
                mapping=dict(lower_ns=lo, upper_ns=hi, bracket_ns=hi-lo,
                    lower_elapsed_from_exec_gate_ns=lo-started_ns, upper_elapsed_from_exec_gate_ns=hi-started_ns,
                    mango_sha256=proof['mango_sha256'], causal_method=proof['method']),
                phases=spans(phases.events, started_ns, stopped_ns), missing_exported_phases=phases.absent,
                kernel_event_format_sha256=phases.readbacks,
                phase_loss_counts=causal.loss_counts(phases.instance),
                browser_process=dict(pid=pid, uid=uid, start_ticks=start_ticks,
                    verified_executable_sha256=libraries['browser']['sha256']),
                process_scope='one_stopped_desktop_owned_exec_gate_and_event_fork_descendants',
                hold_seconds=hold_seconds)
    finally:
        # Only matching new windows observed by this launch are closed.
        with causal.deferred_termination():
            records = owned_scope(wrapper, owner)
            errors = []
            for window in windows:
                try:
                    subprocess.run(prefix + ['mmsg', 'dispatch', 'killclient', 'client,' + str(window['id'])],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
                except BaseException:
                    errors.append('owned_window_close_failed')
            if windows and child:
                try:
                    child.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    pass
            stop_owned_scope(records, child)
            require(not errors, 'owned_window_close_failed')


def validate_context(context):
    require(type(context) is dict and set(context) == {'schema', 'ready', 'boot_purpose', 'image', 'source_sha', 'modules', 'packages'}, 'context_schema')
    require(context['schema'] == 'arctic-browser-startup-diagnostic-v1' and context['ready'] is True
            and context['boot_purpose'] == 'separate-browser-startup-diagnostic'
            and context['source_sha'] == SOURCE_SHA, 'context_disabled_or_source')
    require(type(context['image']) is dict and set(context['image']) == {'source_sha', 'run_id', 'artifact_id', 'name', 'bytes', 'sha256',
            'archive_bytes', 'archive_sha256', 'producer_mode', 'producer_receipt_sha256'}
            and context['image']['source_sha'] == SOURCE_SHA, 'image_binding')
    require(context['image']['producer_mode'] == 'frozen-external-paired-v1'
            and type(context['image']['name']) is str
            and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}\.iso', context['image']['name'])
            and all(type(context['image'][key]) is int and context['image'][key] > 0
                    for key in ('run_id', 'artifact_id', 'bytes', 'archive_bytes'))
            and all(re.fullmatch(r'[0-9a-f]{64}', context['image'][key])
                    for key in ('sha256', 'archive_sha256', 'producer_receipt_sha256')), 'image_values')
    require(type(context['modules']) is dict and set(context['modules']) == {'guest.py', 'causal.py'}
            and all(re.fullmatch(r'[0-9a-f]{64}', value) for value in context['modules'].values()), 'module_pins')
    require(type(context['packages']) is dict and set(context['packages']) == {'epiphany', 'epiphany-runtime', 'glib2', 'gtk4',
            'libadwaita', 'webkitgtk6.0', 'libsecret'}
            and all(re.fullmatch(re.escape(name) + r'-[0-9]+:[A-Za-z0-9._^+~-]+\.x86_64', value)
                    for name, value in context['packages'].items()), 'package_pins')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--context', type=Path, default=Path('/run/t/browser-startup-context.json'))
    parser.add_argument('--out', type=Path, default=Path('/run/arctic-browser-startup/report.json'))
    args = parser.parse_args()
    require(os.geteuid() == 0 and Path(__file__).parent == Path('/run/t'), 'disposable_collector_only')
    require(args.context.parent == Path('/run/t') and args.context.is_file() and not args.context.is_symlink()
            and args.context.stat().st_uid == 0 and not args.context.stat().st_mode & 0o022
            and args.context.stat().st_size <= 32768, 'context_file')
    context = json.loads(args.context.read_text()); validate_context(context)
    require(subprocess.check_output(['systemd-detect-virt', '--vm'], text=True).strip() in ('qemu', 'kvm'), 'vm_only')
    require(subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing', 'selinux_required')
    require(args.out == Path('/run/arctic-browser-startup/report.json') and not args.out.exists()
            and not args.out.parent.exists(), 'fresh_private_report')
    guest = load_module(Path('/run/t/guest.py'), context['modules']['guest.py'], 'browser_diagnostic_guest')
    causal = load_module(Path('/run/t/causal.py'), context['modules']['causal.py'], 'browser_diagnostic_causal')
    libraries = inventory(context)
    prefix = guest.desktop()
    # A separate diagnostic boot with no previously resident browser is
    # required. There is no pkill of unrelated user processes or cache flush.
    uid = pwd.getpwnam(prefix[2]).pw_uid
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            require(not (proc.stat().st_uid == uid and (proc / 'comm').read_text().strip() == 'epiphany'), 'browser_process_exists')
        except OSError:
            pass
    report = dict(schema=context['schema'], diagnostic_only=True, benchmark_acceptance=False,
                  image=context['image'], packages=context['packages'], libraries=libraries,
                  collector_sha256=digest(Path(__file__)), modules=context['modules'],
                  profile_state='existing_installed_user_profile_not_reset_or_declared_cold',
                  interpretation=[
                      'Instrumented separate boot; observed intervals include diagnostic probe overhead.',
                      'RPM verification, ELF hashing and symbol resolution read libraries before launch; no cold-cache claim.',
                      'Exec gate excludes Python/runuser setup; cannot substitute these times for launch acceptance.',
                      'Exported function call durations include nested work and are not additive phase budgets.',
                      'Async DBus calls and secret_async_get show dispatch only, not request/reply latency.',
                      'No exported event is proof of a static Epiphany function or exact first content paint.',
                      'Private kernel string fields are identifier-only and discarded after finite classification.',
                      'No browser option, sandbox, accessibility, portal, renderer or scheduling policy is changed.'])
    with ExitStack() as stack:
        lower = stack.enter_context(causal.LowerBoundProbe(prefix))
        workload = stack.enter_context(guest.role_workload(prefix))
        report['workload_page_sha256'] = workload['page_sha256']
        report['precondition'] = launch(prefix, guest, causal, lower, libraries, workload, 45)
        report['repeated_launches'] = [launch(prefix, guest, causal, lower, libraries, workload, 5) for _ in range(3)]
    require(subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing', 'selinux_changed')
    args.out.parent.mkdir(mode=0o700)
    fd = os.open(args.out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump(report, stream, indent=2, sort_keys=True); stream.write('\n')


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        # The host may record only this fixed failure label. All diagnostics
        # remain private; no arbitrary exception or application text is echoed.
        print('ARCTIC-BROWSER-STARTUP-DIAGNOSTIC failed', file=sys.stderr)
        sys.exit(1)
