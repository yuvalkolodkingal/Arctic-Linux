#!/usr/bin/env python3
"""Disposable image checker: actual installed controller, model, PipeWire and Wayland.

No download/cache is supplied to this checker. Only the recovery phase invokes
the shipped fixed setup wrapper. Public output contains fixed codes and hashes.
"""
import argparse
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import resource
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time

from contract import (ASSETS, EXPECTED_KINDS, LEGACY_GPU_GATE, LOADER_GPU_GATE, LIMITATIONS, PROFILE_ASSETS, PROFILES, SCHEMA, Invalid, context, gates, pinned, require, validate)

HERE = Path(__file__).resolve().parent
DATA = Path('/run/t')
CONTROLLER = Path('/usr/share/arctic/dictation/dictation.py')
CHILD_EXEC = CONTROLLER.with_name('child_exec.py')
PAYLOAD = Path('/opt/arctic/voxtype/1.1.0')
SYSTEM = Path('/var/lib/arctic/dictation')
SESSION_PREFLIGHT_STAGES = ('accuracy-module-import', 'fixture-bundle-validation',
                            'broker-cancel', 'cpu-backend-selection',
                            'virtual-microphone-route', 'receiver-window')
SESSION_ERROR_TYPES = ((Invalid, 'invalid'), (OSError, 'os-error'),
                       (ValueError, 'value-error'), (subprocess.TimeoutExpired, 'timeout'),
                       (KeyError, 'key-error'), (TypeError, 'type-error'))
SESSION_COMMAND_CODES = ('command-output-bound', 'command-failed')
SESSION_STATUS_CODES = SESSION_COMMAND_CODES + (
    'status-byte-bound', 'status-profile-descriptor-pin', 'status-profile-byte-types',
    'optimized-cpu-incompatible', 'status-backend-unknown', 'status-backend-profile',
    'status-cpu-variant-profile', 'status-idle-cpu-variant')
SESSION_INVALID_CODES = {
    'accuracy-module-import': (),
    'fixture-bundle-validation': ('fixture-bundle-validation-failed',),
    'broker-cancel': SESSION_STATUS_CODES,
    'cpu-backend-selection': SESSION_STATUS_CODES,
    'virtual-microphone-route': SESSION_COMMAND_CODES + (
        'native-audio-tool-missing', 'loopback-flags-unavailable',
        'loopback-process-died', 'observation-timeout'),
    'receiver-window': SESSION_COMMAND_CODES + (
        'receiver-process-died', 'receiver-window-duplicate', 'receiver-window-identity',
        'receiver-focus-request-failed', 'receiver-window-disappeared', 'observation-timeout'),
}
WAIT_DIAGNOSTIC_TARGETS = ('receiver-clear', 'capture-link', 'terminal-state', 'text-delivery',
                           'engine-exit', 'microphone-error', 'lock-state', 'unlock-state',
                           'loader-lock', 'loader-exit', 'loader-endpoint', 'loader-engine',
                           'loader-route', 'loader-terminal', 'loader-delivery')
WAIT_DIAGNOSTIC_STATES = ('ready', 'error', 'recording', 'transcribing', 'unavailable')
WAIT_DIAGNOSTIC_BACKENDS = ('', 'cpu', 'vulkan')

def authenticated_capture_nodes(objects, pid, uid):
    """Bind stream nodes to native-protocol peer credentials, never app metadata.

    PipeWire 1.6.9 assigns client.id on the server and protects it from stream
    updates. Its native protocol derives pipewire.sec.pid/uid from SO_PEERCRED;
    client updates cannot replace security properties. ALSA stream nodes need
    not repeat application.process.id, which is not an authenticated identity.
    """
    def number(value):
        if type(value) is int:
            return value if 0 <= value < 2**32 else None
        if type(value) is str and re.fullmatch(r'0|[1-9][0-9]{0,9}', value):
            result = int(value)
            return result if result < 2**32 else None
        return None
    if type(objects) is not list or type(pid) is not int or type(uid) is not int or pid <= 0 or uid <= 0:
        return set(), set()
    seen, clients, nodes = set(), [], []
    for obj in objects:
        if (type(obj) is not dict or any(type(key) is not str for key in obj)
                or type(obj.get('id')) is not int or number(obj['id']) is None or obj['id'] in seen):
            return set(), set()
        seen.add(obj['id'])
        kind = obj.get('type')
        if type(kind) is not str:
            return set(), set()
        if kind not in ('PipeWire:Interface:Client', 'PipeWire:Interface:Node'):
            continue
        info = obj.get('info')
        props = info.get('props') if type(info) is dict and all(type(key) is str for key in info) else None
        if type(props) is not dict or any(type(key) is not str for key in props):
            return set(), set()
        if kind == 'PipeWire:Interface:Client':
            protocol = props.get('pipewire.protocol')
            if (type(protocol) is str and protocol == 'protocol-native'
                    and number(props.get('pipewire.sec.pid')) == pid and number(props.get('pipewire.sec.uid')) == uid):
                clients.append(obj['id'])
        else:
            nodes.append((obj['id'], props))
    if len(clients) != 1:
        return set(), set()
    owned, captures = set(), set()
    for identity, props in nodes:
        if number(props.get('client.id')) != clients[0]:
            continue
        if 'application.process.id' in props and number(props['application.process.id']) != pid:
            continue
        owned.add(identity)
        media = props.get('media.class')
        if type(media) is str and media == 'Stream/Input/Audio':
            captures.add(identity)
    return owned, captures

def wait_status_projection(value):
    """Closed enums only; never export status messages, text, paths or unknown values."""
    if type(value) is not dict:
        return ('unknown', 'unknown')
    state, backend = value.get('state'), value.get('active_backend')
    state = state if type(state) is str and state in WAIT_DIAGNOSTIC_STATES else 'unknown'
    backend = ('idle' if backend == '' else backend) if type(backend) is str and backend in WAIT_DIAGNOSTIC_BACKENDS else 'unknown'
    return (state, backend)

def wait_runtime_projection(path, uid):
    """Failure-only observation from an owned bounded regular descriptor, not readiness."""
    fd = None
    try:
        if type(uid) is not int or uid <= 0:
            return ('unknown', 'unknown')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        before = os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid != uid
                or before.st_mode & 0o077 or not 0 < before.st_size <= 16384):
            return ('unknown', 'unknown')
        raw = os.read(fd, 16385)
        after = os.fstat(fd)
        if (len(raw) != before.st_size or len(raw) > 16384
                or (before.st_dev, before.st_ino, before.st_uid, before.st_mode,
                    before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_uid, after.st_mode,
                    after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            return ('unknown', 'unknown')
        named = os.stat(path, follow_symlinks=False)
        if (before.st_dev, before.st_ino, before.st_uid, before.st_mode,
            before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (
                named.st_dev, named.st_ino, named.st_uid, named.st_mode,
                named.st_size, named.st_mtime_ns, named.st_ctime_ns):
            return ('unknown', 'unknown')
        def unique_pairs(pairs):
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError()
                result[key] = value
            return result
        return wait_status_projection(json.loads(raw, object_pairs_hook=unique_pairs))
    except Exception:
        # Diagnostics cannot replace the original failure or interrupt cleanup.
        return ('unknown', 'unknown')
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass

def wait_diagnostic_code(target, last, current, graph):
    require(type(target) is str and target in WAIT_DIAGNOSTIC_TARGETS, 'unknown-wait-diagnostic-target')
    def projection(value):
        if type(value) is not tuple or len(value) != 2:
            return ('unknown', 'unknown')
        return wait_status_projection({'state': value[0], 'active_backend': '' if type(value[1]) is str and value[1] == 'idle' else value[1]})
    last, current = projection(last), projection(current)
    # Last graph poll: owned engine, authenticated client-owned node, capture-class node,
    # exact source present, exact owned capture link. Unknown is not false.
    bits = ''.join('1' if v is True else '0' if v is False else 'u' for v in graph) if type(graph) is tuple and len(graph) == 5 else 'uuuuu'
    return 'wait-' + target + '-last-' + last[0] + '-' + last[1] + '-now-' + current[0] + '-' + current[1] + '-lg' + bits

def session_diagnostic_code(stage, error):
    """Only fixed setup stages/classes enter public codes, never exception text."""
    require(type(stage) is str and stage in SESSION_PREFLIGHT_STAGES, 'unknown-session-preflight-stage')
    if isinstance(error, Invalid) and type(error.args) is tuple and len(error.args) == 1 and type(error.args[0]) is str:
        for code in SESSION_INVALID_CODES[stage]:
            if error.args[0] == code:
                return 'session-' + stage + '-' + code
    for error_class, label in SESSION_ERROR_TYPES:
        if isinstance(error, error_class):
            return 'session-' + stage + '-' + label
    raise Invalid('unknown-session-preflight-error-type')

def installed_controller():
    spec = importlib.util.spec_from_file_location('arctic_installed_dictation', CONTROLLER)
    controller = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(controller)
    require(set(controller.PROFILES) == set(PROFILES), 'installed-profile-inventory')
    for identity, descriptor in PROFILES.items():
        profile = controller.PROFILES[identity]
        require(controller.profile_status(profile) == descriptor, 'installed-profile-descriptor-pin')
        require(set(profile['assets']) == set(PROFILE_ASSETS[identity]), 'installed-profile-asset-inventory')
        for key, asset in PROFILE_ASSETS[identity].items():
            name, _url, size, digest = profile['assets'][key]
            require((name, size, digest) == (asset['name'], asset['bytes'], asset['sha256']), 'installed-profile-asset-pin')
    return controller

def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def run(argv, timeout=20, check=True):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(len(result.stdout) + len(result.stderr) < 16 * 1024 * 1024, 'command-output-bound')
    if check:
        require(result.returncode == 0, 'command-failed')
    return result

def wait(fn, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = fn()
        if value:
            return value
        time.sleep(.1)
    raise Invalid('observation-timeout')

def owned_file(path, size=None):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022, 'unsafe-installed-file')
    require(size is None or info.st_size == size, 'installed-file-size')
    return info

def desktop():
    users = []
    for path in Path('/proc').glob('[0-9]*'):
        try:
            if (path / 'comm').read_text().strip() != 'mango' or path.stat().st_uid == 0:
                continue
            account = pwd.getpwuid(path.stat().st_uid)
            env = dict(row.split('=', 1) for row in (path / 'environ').read_bytes().decode().split('\0') if '=' in row)
            runtime = Path('/run/user') / str(account.pw_uid)
            displays = [p.name for p in runtime.glob('wayland-*') if p.is_socket()]
            require(len(displays) == 1, 'desktop-wayland-ambiguous')
            candidates = [env]
            for child in Path('/proc').glob('[0-9]*'):
                try:
                    if child.stat().st_uid == account.pw_uid:
                        childenv = dict(row.split('=', 1) for row in (child / 'environ').read_bytes().decode().split('\0') if '=' in row)
                        if childenv.get('XDG_RUNTIME_DIR') == str(runtime):
                            candidates.append(childenv)
                except (OSError, UnicodeError):
                    pass
            signatures = {e['MANGO_INSTANCE_SIGNATURE'] for e in candidates if e.get('MANGO_INSTANCE_SIGNATURE')}
            require(len(signatures) == 1, 'desktop-mango-ambiguous')
            prefix = ['runuser', '-u', account.pw_name, '--', 'env',
                      'PATH=/usr/bin:/bin', 'LANG=C.UTF-8', 'HOME=' + account.pw_dir,
                      'XDG_RUNTIME_DIR=' + str(runtime), 'WAYLAND_DISPLAY=' + displays[0],
                      'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime / 'bus'),
                      'XDG_SESSION_TYPE=wayland', 'GDK_BACKEND=wayland',
                      'MANGO_INSTANCE_SIGNATURE=' + signatures.pop()]
            users.append((account, runtime, prefix))
        except (OSError, UnicodeError):
            pass
    require(len(users) == 1, 'desktop-not-unique')
    return users[0]

def iter_process(pid):
    value = (Path('/proc') / str(pid) / 'stat').read_text()
    return int(value[value.rfind(')') + 2:].split()[19])

def receiver(path, nonce):
    """Private GTK3 text capture; only local UTF-8 text, never stdout/journal."""
    require(os.geteuid() != 0, 'receiver-must-be-user')
    root = Path(path)
    require(root.stat().st_uid == os.getuid() and not root.stat().st_mode & 0o077, 'receiver-directory-unsafe')
    gtk = ctypes.CDLL('libgtk-3.so.0')
    glib = ctypes.CDLL('libglib-2.0.so.0')
    def api(lib, name, result, args):
        fn = getattr(lib, name); fn.restype = result; fn.argtypes = args; return fn
    ptr = ctypes.c_void_p
    api(glib, 'g_set_prgname', None, [ctypes.c_char_p])(nonce.encode())
    require(api(gtk, 'gtk_init_check', ctypes.c_int, [ptr, ptr])(None, None), 'receiver-gtk-init')
    window = api(gtk, 'gtk_window_new', ptr, [ctypes.c_int])(0)
    api(gtk, 'gtk_window_set_title', None, [ptr, ctypes.c_char_p])(window, nonce.encode())
    api(gtk, 'gtk_window_set_default_size', None, [ptr, ctypes.c_int, ctypes.c_int])(window, 720, 300)
    view = api(gtk, 'gtk_text_view_new', ptr, [])()
    buffer = api(gtk, 'gtk_text_view_get_buffer', ptr, [ptr])(view)
    api(gtk, 'gtk_container_add', None, [ptr, ptr])(window, view)
    api(gtk, 'gtk_widget_show_all', None, [ptr])(window)
    api(gtk, 'gtk_widget_grab_focus', None, [ptr])(view)
    bounds = api(gtk, 'gtk_text_buffer_get_bounds', None, [ptr, ptr, ptr])
    get_text = api(gtk, 'gtk_text_buffer_get_text', ptr, [ptr, ptr, ptr, ctypes.c_int])
    free = api(glib, 'g_free', None, [ptr])
    clear = api(gtk, 'gtk_text_buffer_set_text', None, [ptr, ctypes.c_char_p, ctypes.c_int])
    tick = ctypes.CFUNCTYPE(ctypes.c_int, ptr)
    @tick
    def update(_data):
        if (root / 'clear').exists():
            clear(buffer, b'', 0); (root / 'clear').unlink()
        start, end = (ctypes.c_uint64 * 16)(), (ctypes.c_uint64 * 16)()
        bounds(buffer, start, end)
        value = get_text(buffer, start, end, 1)
        content = ctypes.string_at(value); free(value)
        temporary = root / 'receiver.part'
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(content)
        temporary.replace(root / 'received.private')
        return 1
    api(glib, 'g_timeout_add', ctypes.c_uint, [ctypes.c_uint, tick, ptr])(50, update, None)
    api(gtk, 'gtk_main', None, [])()

class Checker:
    def __init__(self, declared):
        self.context = declared
        self.controller = installed_controller()
        self.profile_id = declared['hardware_profile']
        self.profile = self.controller.desired_profile()
        self.assets = PROFILE_ASSETS[self.profile_id]
        self.names = {key: asset['name'] for key, asset in self.assets.items()}
        cpuinfo = Path('/proc/cpuinfo').read_bytes()
        require(self.controller.profile_selection() == 'recommended'
                and self.profile['id'] == self.profile_id
                and self.controller.recommended_profile(cpuinfo.decode())['id'] == self.profile_id,
                'actual-hardware-profile-mismatch')
        self.gates = gates(declared['phase'], self.profile_id)
        hardware = {'profile': self.profile_id, 'v3_supported': self.controller.v3_supported(cpuinfo.decode()),
                    'cpuinfo_sha256': hashlib.sha256(cpuinfo).hexdigest(), 'profile_selection': 'recommended'}
        self.report = {'schema': SCHEMA, 'status': 'failed', 'release_acceptance': False,
                       'context': declared, 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                       'controller_sha256': sha(CONTROLLER), 'payload': {}, 'gates': [],
                       'samples': [], 'limitations': LIMITATIONS, 'disk': {},
                       'profile': PROFILES[self.profile_id], 'hardware': hardware}
        self.account, self.runtime, self.prefix = desktop()
        self.root = Path(tempfile.mkdtemp(prefix='arctic-dictation-test-', dir='/tmp'))
        os.chmod(self.root, 0o700); os.chown(self.root, self.account.pw_uid, self.account.pw_gid)
        self.prefix += ['XDG_CONFIG_HOME=' + str(self.root / 'config')]
        self.private = self.runtime / 'arctic/dictation'
        self.phrases = []
        self.snapshots = []
        self.loop = self.window = self.player = None
        self.old_source = None
        self.source = None
        self.initial_processes = {p.name for p in Path('/proc').glob('[0-9]*')}
        cursor = run(['journalctl', '-n', '0', '--show-cursor', '--no-pager']).stdout.decode()
        found = re.search(r'-- cursor: (\S+)', cursor)
        require(found, 'journal-cursor-unavailable'); self.cursor = found.group(1)
        self.audit_before = self.audit_state()
        self.audit_file = Path('/var/log/audit/audit.log')
        self.audit_offset = None
        if self.audit_file.exists():
            info = self.audit_file.stat()
            self.audit_offset = (info.st_dev, info.st_ino, info.st_size)

    def cmd(self, argv, timeout=20, check=True):
        return run(self.prefix + argv, timeout, check)

    def gate(self, name, fn, kind='actual-session'):
        require(name in self.gates, 'unknown-gate')
        self._wait_last_status = self._wait_last_graph = None
        result = {'id': name, 'status': 'failed', 'evidence_kind': kind, 'code': 'collector-failed', 'observations': {}}
        try:
            observations = fn()
            result.update(status='passed', code='observed', observations=observations or {})
        except Invalid as error:
            result['code'] = str(error)
            if str(error) in ('no-supported-vulkan-device', 'microphone-isolation-unavailable'):
                result['status'] = 'unrun'
        except (OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):
            pass
        self.report['gates'].append(result)
        return result['status'] == 'passed'

    def status(self, verb='status', *args, check=True):
        result = self.cmd(['/usr/bin/arctic-dictation', verb, *args], check=check)
        require(len(result.stdout) <= 16384, 'status-byte-bound')
        value = json.loads(result.stdout)
        require(isinstance(value, dict) and {key: value.get(key) for key in PROFILES[self.profile_id]} == PROFILES[self.profile_id]
                and all(type(value.get(key)) is type(item) for key, item in PROFILES[self.profile_id].items())
                and value.get('version') == '1.1.0' and value.get('profile_selection') == 'recommended'
                and value.get('recommended_profile') == PROFILES[self.profile_id]
                and value.get('compatibility_profile') == PROFILES['small-v2'], 'status-profile-descriptor-pin')
        for key, descriptor in (('recommended_profile', PROFILES[self.profile_id]), ('compatibility_profile', PROFILES['small-v2'])):
            require(all(type(value[key].get(field)) is type(item) for field, item in descriptor.items()),
                    'status-profile-byte-types')
        require(value.get('compatibility_required') is False, 'optimized-cpu-incompatible')
        require(value.get('active_backend') in ('', 'cpu', 'vulkan'), 'status-backend-unknown')
        if value.get('active_backend') == 'vulkan':
            require(self.profile_id == 'turbo-q5-v3' and value.get('active_cpu_variant') == '', 'status-backend-profile')
        elif value.get('active_backend') == 'cpu':
            require(value.get('active_cpu_variant') == PROFILES[self.profile_id]['cpu_variant'], 'status-cpu-variant-profile')
        else:
            require(value.get('active_cpu_variant') == '', 'status-idle-cpu-variant')
        self.snapshots.append(result.stdout.decode())
        self._wait_last_status = wait_status_projection(value)
        return value

    def observe(self, target, fn, seconds=20):
        """Use the original predicate/budget; label only its fixed timeout failure."""
        require(type(target) is str and target in WAIT_DIAGNOSTIC_TARGETS, 'unknown-wait-diagnostic-target')
        try:
            return wait(fn, seconds)
        except Invalid as error:
            arguments = BaseException.args.__get__(error)
            if not (type(arguments) is tuple and len(arguments) == 1
                    and type(arguments[0]) is str and arguments[0] == 'observation-timeout'):
                raise
            try:
                current = wait_runtime_projection(self.runtime / 'arctic/dictation.json', self.account.pw_uid)
                code = wait_diagnostic_code(target, self.__dict__.get('_wait_last_status'), current,
                                            self.__dict__.get('_wait_last_graph'))
            except Exception:
                code = wait_diagnostic_code(target, None, None, None)
            raise Invalid(code) from None

    def empty(self):
        path = self.root / 'clear'
        path.touch(mode=0o600); os.chown(path, self.account.pw_uid, self.account.pw_gid)
        self.observe('receiver-clear', lambda: not path.exists() and (self.root / 'received.private').read_bytes() == b'')

    def engines(self):
        found = []
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                exe = (proc / 'exe').resolve(strict=True)
                if proc.stat().st_uid == self.account.pw_uid and exe in {PAYLOAD / asset['name'] for key, asset in ASSETS.items() if key in ('cpu', 'avx2', 'vulkan')}:
                    require(proc.name not in self.initial_processes, 'preexisting-engine-forbidden')
                    found.append((int(proc.name), iter_process(proc.name), exe))
            except (OSError, ValueError):
                pass
        return found

    def no_engine(self):
        require(not self.engines(), 'engine-survived-cancel')
        return True

    def payload(self):
        owned_file(CHILD_EXEC)
        require(sha(CHILD_EXEC) == self.context['child_exec_sha256'], 'installed-child-guard-sha256')
        receipt = SYSTEM / 'verified.json'; owned_file(receipt)
        verified = read(receipt)
        require(verified.get('version') == '1.1.0'
                and verified.get('source_commit') == 'e2638ca63f566f1682bcedc0abea8e4b25211c21', 'receipt-version-source')
        require({key: verified.get(key) for key in PROFILES[self.profile_id]} == PROFILES[self.profile_id]
                and verified.get('profile_sha256') == self.controller.profile_digest(self.profile)
                and isinstance(verified.get('files'), dict) and set(verified['files']) == set(self.assets), 'receipt-profile-pin')
        for key, name in self.names.items():
            path = PAYLOAD / name; info = owned_file(path, self.assets[key]['bytes'])
            require(sha(path) == self.assets[key]['sha256'], 'installed-payload-sha256')
            require(verified.get('files', {}).get(key) == {'sha256': self.assets[key]['sha256'], 'size': self.assets[key]['bytes'], 'mtime_ns': info.st_mtime_ns}, 'receipt-file-pin')
            require(type(verified['files'][key].get('size')) is int and type(verified['files'][key].get('mtime_ns')) is int,
                    'receipt-file-pin-types')
            require(key == 'model' or info.st_mode & 0o111, 'installed-binary-not-executable')
        self.report['payload'] = pinned(self.profile_id)
        return {'file_count': len(self.assets)}

    def ready(self):
        value = self.status()
        require(value.get('ready') is True and value.get('state') == 'ready'
                and value.get('model') == self.profile['model'] and value.get('version') == '1.1.0', 'installed-controller-not-ready')
        require(not (SYSTEM / 'pending.json').exists(), 'ready-still-pending')
        return {'ready': True, 'pending': False}

    def encrypted(self):
        root = run(['findmnt', '-n', '-o', 'SOURCE', '/']).stdout.decode().strip()
        require(root.startswith('/dev/mapper/') and 'luks' in Path('/etc/crypttab').read_text(), 'encrypted-root-not-observed')
        mapper = root.split('[')[0]
        info = run(['cryptsetup', 'status', mapper]).stdout.decode()
        device = re.search(r'^\s*device:\s+(\S+)\s*$', info, re.M)
        require(device is not None, 'root-crypt-device-unavailable')
        self.report['disk'] = {
            'root_luks_uuid': run(['cryptsetup', 'luksUUID', device.group(1)]).stdout.decode().strip(),
            'root_fs_uuid': run(['lsblk', '-n', '-o', 'UUID', mapper]).stdout.decode().strip(),
            'root_partuuid': run(['lsblk', '-n', '-o', 'PARTUUID', device.group(1)]).stdout.decode().strip(),
        }
        return {'ready': True}

    def offline(self):
        result = run(['curl', '--noproxy', '*', '-s', '-o', '/dev/null', '-w', '%{http_code}',
                      '--connect-timeout', '3', '--max-time', '5', 'http://fedoraproject.org/'], check=False)
        require(result.returncode != 0 and result.stdout == b'000', 'outside-network-response')
        return {'returncode': result.returncode}

    def route(self):
        for name in ('pw-loopback', 'pw-play', 'pw-dump', 'wpctl'):
            require(Path('/usr/bin', name).is_file(), 'native-audio-tool-missing')
        help_text = self.cmd(['/usr/bin/pw-loopback', '--help']).stdout.decode()
        require('--channels' in help_text and '--channel-map' in help_text
                and '--capture-props' in help_text and '--playback-props' in help_text, 'loopback-flags-unavailable')
        old = self.cmd(['/usr/bin/wpctl', 'inspect', '@DEFAULT_AUDIO_SOURCE@'], check=False)
        match = re.search(r'\bid (\d+),', old.stdout.decode())
        self.old_source = int(match.group(1)) if match else None
        nonce = os.urandom(8).hex()
        self.sink_name = 'ArcticDictationFixtureSink' + nonce
        self.source_name = 'ArcticDictationFixtureSource' + nonce
        self.loop = subprocess.Popen(self.prefix + ['/usr/bin/pw-loopback', '--channels=1', '--channel-map=[ MONO ]',
            '--capture-props=audio.rate=16000 media.class=Audio/Sink node.name=' + self.sink_name,
            '--playback-props=audio.rate=16000 media.class=Audio/Source node.name=' + self.source_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        def observed():
            require(self.loop.poll() is None, 'loopback-process-died')
            objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
            sources = [o['id'] for o in objects if o.get('type') == 'PipeWire:Interface:Node'
                       and o.get('info', {}).get('props', {}).get('node.name') == self.source_name
                       and o.get('info', {}).get('props', {}).get('media.class') == 'Audio/Source']
            sinks = [o['id'] for o in objects if o.get('type') == 'PipeWire:Interface:Node'
                     and o.get('info', {}).get('props', {}).get('node.name') == self.sink_name]
            return sources[0] if len(sources) == len(sinks) == 1 else None
        self.source = wait(observed)
        self.cmd(['/usr/bin/wpctl', 'set-default', str(self.source)])

    def destroy_route(self, restore=True):
        if self.loop:
            self.kill(self.loop); self.loop = None
        if not restore:
            self.source = None
            return
        if self.old_source is not None:
            self.cmd(['/usr/bin/wpctl', 'set-default', str(self.old_source)])
        else:
            # WirePlumber clear-default ID=1 is the configured default audio source.
            self.cmd(['/usr/bin/wpctl', 'clear-default', '1'])
        self.source = None

    @staticmethod
    def kill(child):
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=3)

    def window_start(self):
        nonce = 'arctic-dictation-qualification-' + os.urandom(8).hex()
        self.window = subprocess.Popen(self.prefix + ['/usr/bin/python3', str(HERE / 'guest_check.py'),
                                          '_receiver', str(self.root), nonce],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        def owned_window():
            require(self.window.poll() is None, 'receiver-process-died')
            clients = json.loads(self.cmd(['mmsg', 'get', 'all-clients']).stdout)['clients']
            rows = [c for c in clients if c.get('title') == nonce]
            require(len(rows) <= 1, 'receiver-window-duplicate')
            if rows:
                row = rows[0]
                require(row['is_xwayland'] is False and row['is_visible'] is True
                        and Path('/proc', str(row['pid'])).stat().st_uid == self.account.pw_uid
                        and row['pid'] not in {int(p) for p in self.initial_processes}, 'receiver-window-identity')
                return row
        self.client = wait(owned_window)
        result = json.loads(self.cmd(['mmsg', 'dispatch', 'focusid', 'client,' + str(self.client['id'])]).stdout)
        require(result.get('success') is True, 'receiver-focus-request-failed')
        wait(lambda: self.focused())
        wait(lambda: (self.root / 'received.private').exists())

    def focused(self):
        rows = json.loads(self.cmd(['mmsg', 'get', 'all-clients']).stdout)['clients']
        owned = [c for c in rows if c['id'] == self.client['id'] and c['pid'] == self.client['pid']]
        require(len(owned) == 1, 'receiver-window-disappeared')
        return owned[0].get('is_focused') is True and owned[0].get('is_visible') is True

    def capture_link(self):
        engines = self.engines(); require(len(engines) == 1, 'recording-engine-not-unique')
        pid = engines[0][0]
        objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
        owned, captures = authenticated_capture_nodes(objects, pid, self.account.pw_uid)
        require(self.engines() == engines, 'recording-engine-changed')
        linked = any(o.get('type') == 'PipeWire:Interface:Link'
                   and o.get('info', {}).get('output-node-id') == self.source
                   and o.get('info', {}).get('input-node-id') in captures for o in objects) if captures else False
        owner = bool(owned)
        source = any(o.get('type') == 'PipeWire:Interface:Node' and o.get('id') == self.source for o in objects)
        self._wait_last_graph = (True, owner, bool(captures), source, linked)
        return linked

    def play(self, sample):
        self.audio = self.root / 'fixture.wav'
        shutil.copyfile(DATA / 'dictation-fixtures' / sample['wav'], self.audio)
        os.chmod(self.audio, 0o600); os.chown(self.audio, self.account.pw_uid, self.account.pw_gid)
        require(sha(self.audio) == sample['wav_sha256'], 'playback-fixture-sha256')
        self.player = subprocess.Popen(self.prefix + ['/usr/bin/pw-play', '--target=' + self.sink_name, str(self.audio)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)

    def transcribe(self, sample, purpose='cpu-session', store=True, loader=None):
        self.empty(); require(self.focused(), 'receiver-focus-lost')
        self.status('set-language', sample['language'])
        before = time.monotonic_ns()
        start = self.status('start', check=False)
        require(start.get('ok') is True and start.get('state') == 'recording'
                and start.get('active_backend') == 'cpu', 'cpu-recording-not-started')
        engines = self.engines()
        cpu_key = 'avx2' if self.profile['cpu_variant'] == 'avx2' else 'cpu'
        require(len(engines) == 1 and engines[0][2] == PAYLOAD / self.names[cpu_key]
                and sha(engines[0][2]) == self.assets[cpu_key]['sha256'], 'cpu-owned-process-profile-pin')
        if loader is not None:
            self.loader_engine(engines[0], *loader)
        self.observe('capture-link', self.capture_link, 10)
        self.play(sample)
        require(self.player.wait(timeout=sample['audio_seconds'] + 20) == 0, 'fixture-playback-failed')
        stopped = self.status('stop', check=False)
        require(stopped.get('ok') is True and stopped.get('state') == 'transcribing', 'recording-stop-failed')
        self.observe('terminal-state', lambda: self.status().get('state') in ('ready', 'error'), 240)
        elapsed = time.monotonic_ns() - before
        require(self.status().get('state') == 'ready', 'cpu-transcription-failed')
        # Controller completion and GTK's Wayland delivery are different events.
        previous, stable = None, 0
        def received():
            nonlocal previous, stable
            value = (self.root / 'received.private').read_text()
            stable = stable + 1 if value and value == previous else 0
            previous = value
            return value if stable >= 3 else None
        hypothesis = self.observe('text-delivery', received, 5)
        require(hypothesis and not hypothesis.endswith('\n') and '\n' not in hypothesis, 'empty-or-unintended-enter')
        require(self.focused(), 'insertion-focus-lost')
        if sample['language'] == 'he':
            require(any('\u05d0' <= c <= '\u05ea' for c in hypothesis), 'hebrew-script-not-inserted')
        self.phrases.append(hypothesis)
        reference = (DATA / 'dictation-fixtures' / sample['reference']).read_text()
        metric = self.accuracy.metrics(reference, hypothesis)
        item = {'language': sample['language'], 'source_row': sample['source_row'], 'purpose': purpose,
                'wav_sha256': sample['wav_sha256'], 'reference_sha256': sample['reference_sha256'],
                'hypothesis_sha256': hashlib.sha256(hypothesis.encode()).hexdigest(),
                'elapsed_ns': elapsed, 'audio_frames': sample['audio_frames'], 'sample_rate': 16000,
                'reference_words': metric['reference_words'], 'word_edits': metric['word_edits'],
                'reference_chars': metric['reference_characters'], 'char_edits': metric['character_edits'],
                'backend': 'cpu', 'cpu_variant': self.profile['cpu_variant'],
                'binary_sha256': self.assets[cpu_key]['sha256'], 'model_sha256': self.assets['model']['sha256']}
        if store:
            self.report['samples'].append(item)
        return item

    def samples(self, language):
        rows = [sample for sample in self.fixtures if sample['language'] == language]
        require([sample['source_row'] for sample in rows] == list(range(5)), 'fixture-language-rows')
        for sample in rows:
            self.transcribe(sample)
        return {'count': len(rows)}

    def cancel(self):
        self.empty(); self.status('set-backend', 'cpu'); self.status('set-language', 'en')
        require(self.status('start')['state'] == 'recording', 'cancel-recording-not-started')
        self.observe('capture-link', self.capture_link, 10); self.play(self.fixtures[0]); time.sleep(.5)
        value = self.status('cancel')
        self.kill(self.player); self.player = None
        require(value.get('state') == 'ready', 'cancel-not-ready')
        self.observe('engine-exit', lambda: not self.engines()); self.no_engine()
        time.sleep(.5)
        require((self.root / 'received.private').read_bytes() == b'', 'cancel-inserted-text')
        return {'count': 0, 'drained': True}

    def broker_death(self):
        self.empty(); self.status('set-backend', 'cpu'); self.status('set-language', 'en')
        require(self.status('start')['state'] == 'recording', 'broker-death-recording-not-started')
        self.observe('capture-link', self.capture_link, 10); self.play(self.fixtures[0]); time.sleep(.3)
        engines = self.engines(); require(len(engines) == 1, 'broker-death-engine-not-unique')
        engine_pid = engines[0][0]
        parent = (Path('/proc') / str(engine_pid) / 'status').read_text()
        match = re.search(r'^PPid:\s*(\d+)', parent, re.M)
        require(match is not None, 'engine-parent-unavailable')
        broker = int(match.group(1)); path = Path('/proc') / str(broker)
        require(path.stat().st_uid == self.account.pw_uid and str(broker) not in self.initial_processes, 'broker-not-owned')
        argv = (path / 'cmdline').read_bytes().split(b'\0')
        require(str(CONTROLLER).encode() in argv and b'_broker' in argv, 'broker-command-identity')
        ticks = iter_process(broker)
        require(iter_process(broker) == ticks, 'broker-replaced-before-kill')
        self.kill_identity(broker, ticks)
        self.kill(self.player); self.player = None
        self.observe('engine-exit', lambda: not self.engines(), 10); self.no_engine()
        value = self.status()
        require(value.get('ready') is True and value.get('state') == 'ready', 'broker-death-stale-status')
        require((self.root / 'received.private').read_bytes() == b'', 'broker-death-inserted-text')
        require(not self.transcript_files(), 'broker-death-retained-transcript')
        return {'count': 0, 'drained': True, 'ready': True, 'pid': broker, 'start_ticks': ticks}

    def missing(self):
        self.status('cancel')
        target = PAYLOAD / self.names['model']
        hidden = target.with_name(target.name + '.qualification-' + os.urandom(8).hex())
        target.rename(hidden)
        try:
            value = self.status('start', check=False)
            require(value.get('ok') is False and value.get('ready') is False
                    and value.get('state') == 'error' and bool(value.get('error')), 'missing-model-not-actionable')
            self.no_engine()
        finally:
            hidden.rename(target)
        require(sha(target) == self.assets['model']['sha256'], 'missing-model-restore-integrity')
        return {'ready': False, 'restored': True}

    def microphone(self):
        self.empty(); self.status('set-backend', 'cpu')
        require(self.status('start')['state'] == 'recording', 'mic-recording-not-started')
        self.observe('capture-link', self.capture_link, 10)
        self.destroy_route(restore=False)
        try:
            objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
            remaining = [o for o in objects if o.get('type') == 'PipeWire:Interface:Node'
                         and o.get('info', {}).get('props', {}).get('media.class', '').startswith('Audio/Source')]
            require(not remaining, 'microphone-isolation-unavailable')
            value = self.observe('microphone-error', lambda: (v if (v := self.status()).get('state') == 'error' else None), 10)
            require(bool(value.get('error')) and value.get('ok') is False, 'mic-failure-not-actionable')
            require((self.root / 'received.private').read_bytes() == b'', 'mic-failure-inserted-text')
            self.no_engine()
        finally:
            self.status('cancel', check=False); self.route()
        return {'count': 0, 'drained': True, 'restored': True}

    def locked(self):
        self.empty(); self.status('set-backend', 'cpu')
        require(self.status('start')['state'] == 'recording', 'lock-recording-not-started')
        self.observe('capture-link', self.capture_link, 10); self.play(self.fixtures[0]); time.sleep(.3)
        self.cmd(['/usr/bin/arctic-shell-ipc', 'lock', 'lock'])
        self.observe('lock-state', lambda: self.cmd(['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'true')
        self.kill(self.player); self.player = None
        self.observe('engine-exit', lambda: not self.engines(), 5); self.no_engine()
        value = self.status('start', check=False)
        require(value.get('ok') is False and value.get('state') == 'error', 'recording-started-while-locked')
        require((self.root / 'received.private').read_bytes() == b'', 'lock-inserted-text')
        # Existing host interactive path types only its disposable test password.
        print('ARCTIC-DESKTOP-UNLOCK-REQUESTED', flush=True)
        self.observe('unlock-state', lambda: self.cmd(['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'false', 90)
        self.status('cancel', check=False)
        require(self.focused(), 'receiver-focus-after-unlock')
        return {'locked': True, 'count': 0, 'drained': True}

    def gpu_failure(self):
        require(self.profile_id == 'turbo-q5-v3', 'gpu-gate-requires-modern-profile')
        self.empty(); self.status('set-backend', 'vulkan')
        value = self.status('start', check=False)
        if value.get('ok') is not True or value.get('state') != 'recording' or value.get('active_backend') != 'vulkan':
            self.status('cancel', check=False); self.status('set-backend', 'cpu')
            raise Invalid('no-supported-vulkan-device')
        self.observe('capture-link', self.capture_link, 10)
        found = self.engines(); require(len(found) == 1, 'gpu-engine-not-unique')
        pid, ticks, binary = found[0]
        require(binary == PAYLOAD / self.names['vulkan'] and iter_process(pid) == ticks
                and sha(binary) == self.assets['vulkan']['sha256'], 'gpu-owned-process-identity')
        self.kill_identity(pid, ticks)
        failed = self.observe('terminal-state', lambda: (v if (v := self.status()).get('state') == 'error' else None), 10)
        require(failed.get('active_backend') == 'cpu' and bool(failed.get('error')), 'gpu-failure-no-advertised-cpu-retry')
        self.no_engine()
        # Keep preference forced Vulkan: advertised CPU retry must still work.
        for language in ('en', 'he'):
            sample = next(s for s in self.fixtures if s['language'] == language and s['source_row'] == 0)
            self.transcribe(sample, 'cpu-retry')
        self.status('set-backend', 'cpu')
        return {'active_backend_vulkan': True, 'active_backend_cpu': True,
                'count': 2, 'pid': pid, 'start_ticks': ticks}

    def legacy_gpu(self):
        require(self.profile_id == 'small-v2' and 'vulkan' not in self.assets, 'legacy-gpu-profile-pin')
        self.empty(); self.status('set-backend', 'vulkan')
        value = self.status('start', check=False)
        require(value.get('ok') is False and value.get('state') == 'error' and bool(value.get('error')),
                'legacy-vulkan-start-not-rejected')
        self.no_engine()
        self.status('set-backend', 'cpu')
        for language in ('en', 'he'):
            sample = next(s for s in self.fixtures if s['language'] == language and s['source_row'] == 0)
            self.transcribe(sample, 'cpu-retry')
        return {'gpu_supported': False, 'active_backend_vulkan': False, 'active_backend_cpu': True, 'count': 2}

    def broker_identity(self, expected=None):
        control = self.private / 'control.sock'
        info = control.lstat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == self.account.pw_uid
                and not info.st_mode & 0o077, 'loader-control-socket-unsafe')
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
            peer.settimeout(1); peer.connect(str(control))
            pid, uid, _gid = struct.unpack('3i', peer.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        proc = Path('/proc') / str(pid)
        ticks = iter_process(pid)
        require(uid == self.account.pw_uid and proc.stat().st_uid == uid
                and str(pid) not in self.initial_processes, 'loader-broker-not-owned')
        require((proc / 'exe').resolve(strict=True) == Path('/usr/bin/python3').resolve(strict=True)
                and (proc / 'cmdline').read_bytes().split(b'\0') ==
                [b'/usr/bin/python3', b'-I', str(CONTROLLER).encode(), b'_broker', b''],
                'loader-broker-command-identity')
        identity = (pid, ticks, info.st_ino)
        require(expected is None or identity == expected, 'loader-broker-changed')
        require(iter_process(pid) == ticks, 'loader-broker-process-reused')
        return identity

    def loader_environment(self, pid, ticks, environment):
        proc = Path('/proc') / str(pid)
        require(proc.stat().st_uid == self.account.pw_uid and iter_process(pid) == ticks,
                'loader-environment-process-identity')
        raw = (proc / 'environ').read_bytes()
        require(len(raw) <= 128 * 1024, 'loader-environment-bound')
        actual = dict(row.split(b'=', 1) for row in raw.split(b'\0') if b'=' in row)
        require(all(actual.get(key.encode()) == value.encode() for key, value in environment.items())
                and iter_process(pid) == ticks, 'loader-environment-not-inherited')

    def loader_engine(self, engine, broker, environment):
        pid, ticks, _binary = engine
        self.broker_identity(broker)
        parent = (Path('/proc') / str(pid) / 'status').read_text()
        require(re.search(r'^PPid:\s*' + str(broker[0]) + r'\s*$', parent, re.M),
                'loader-engine-parent-mismatch')
        self.loader_environment(pid, ticks, environment)

    @staticmethod
    def loader_start_response(code, value):
        # An observed startup loader error is returned as CLI exit 1. Accept
        # exactly the actionable GPU initialization outcome, never an arbitrary
        # microphone, lock, setup or command error disguised as this fixture.
        recording = (type(code) is int and code == 0 and value.get('ok') is True
                     and value.get('state') == 'recording' and value.get('backend') == 'vulkan'
                     and value.get('active_backend') == 'vulkan' and not value.get('error'))
        init_error = (type(code) is int and code == 1 and value.get('ok') is False
                      and value.get('state') == 'error' and value.get('backend') == 'vulkan'
                      and value.get('active_backend') == 'cpu' and value.get('error') ==
                      'GPU initialization failed. CPU is selected for this session; record again.')
        require(recording or init_error, 'loader-start-command-outcome')

    def gpu_loader_failure(self):
        require(self.profile_id == 'turbo-q5-v3', 'loader-gate-requires-modern-profile')
        require(self.controller.gpu_available(), 'no-supported-vulkan-device')
        self.empty(); self.status('cancel', check=False); self.no_engine()
        self.status('set-backend', 'vulkan'); self.status('set-language', 'en')
        old = self.broker_identity()
        icd = self.root / 'bad-icd.json'
        missing = self.root / 'libarctic-qualification-missing-vulkan-driver.so'
        require(not icd.exists() and not missing.exists(), 'loader-fixture-already-present')
        descriptor = os.open(icd, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, 'w') as manifest:
            manifest.write(json.dumps({'file_format_version': '1.0.0', 'ICD': {
                'library_path': str(missing), 'api_version': '1.3.0'}}, sort_keys=True) + '\n')
        os.chmod(icd, 0o600); os.chown(icd, self.account.pw_uid, self.account.pw_gid)
        environment = {'VK_DRIVER_FILES': str(icd), 'VK_LOADER_DEBUG': 'error'}
        wrapper = activation = None
        broker = None
        try:
            # Hold the shipped client launcher lock across the owned handoff;
            # status-only clients cannot create a replacement audio owner.
            fd = os.open(self.private / 'launch.lock', os.O_RDWR | os.O_NOFOLLOW)
            with os.fdopen(fd, 'w') as launch:
                info = os.fstat(launch.fileno())
                require(stat.S_ISREG(info.st_mode) and info.st_uid == self.account.pw_uid
                        and not info.st_mode & 0o077, 'loader-launch-lock-unsafe')
                def locked():
                    try:
                        fcntl.flock(launch, fcntl.LOCK_EX | fcntl.LOCK_NB); return True
                    except BlockingIOError:
                        return False
                self.observe('loader-lock', locked, 3)
                self.broker_identity(old); self.kill_identity(old[0], old[1])
                self.observe('loader-exit', lambda: not (Path('/proc') / str(old[0])).exists(), 5)
                self.no_engine()
                wrapper = subprocess.Popen(self.prefix + [key + '=' + value for key, value in environment.items()]
                    + ['/usr/bin/python3', '-I', str(CONTROLLER), '_broker'], stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, start_new_session=True)
                def published():
                    require(wrapper.poll() is None, 'loader-broker-wrapper-died')
                    control = self.private / 'control.sock'
                    return control.exists() and control.lstat().st_ino != old[2]
                self.observe('loader-endpoint', published, 5)
                broker = self.broker_identity()
                require(broker[0] != old[0] and broker[2] != old[2], 'loader-broker-not-fresh')
                parent = (Path('/proc') / str(broker[0]) / 'status').read_text()
                require(re.search(r'^PPid:\s*' + str(wrapper.pid) + r'\s*$', parent, re.M),
                        'loader-broker-wrapper-parent')
                self.loader_environment(broker[0], broker[1], environment)
            response = self.root / 'loader-start-response.private'
            attempted = time.monotonic_ns()
            with response.open('xb') as out:
                os.fchmod(out.fileno(), 0o600)
                activation = subprocess.Popen(self.prefix + ['/usr/bin/arctic-dictation', 'start'],
                    stdout=out, stderr=subprocess.DEVNULL, start_new_session=True)
                def observed():
                    found = self.engines()
                    require(len(found) <= 1, 'loader-engine-not-unique')
                    return found[0] if found else None
                engine = self.observe('loader-engine', observed, 5)
                require(engine[2] == PAYLOAD / self.names['vulkan']
                        and sha(engine[2]) == self.assets['vulkan']['sha256'], 'loader-vulkan-process-pin')
                self.loader_engine(engine, broker, environment)
                start_code = activation.wait(timeout=15)
            require(response.stat().st_size <= 16384, 'loader-start-response-bound')
            start_raw = response.read_text()
            self.snapshots.append(start_raw)
            try:
                start_value = json.loads(start_raw)
            except ValueError:
                raise Invalid('loader-start-response-json')
            require(isinstance(start_value, dict), 'loader-start-response-json')
            self.loader_start_response(start_code, start_value)
            value = self.status(check=False)
            if value.get('state') == 'recording':
                # With on-demand model loading, initialization may not finish
                # until stop. Route actual speech and explicitly stop if alive.
                def capture_or_error():
                    if self.status(check=False).get('state') == 'error':
                        return 'error'
                    return 'capture' if self.engines() and self.capture_link() else None
                if self.observe('loader-route', capture_or_error, 10) == 'capture':
                    sample = next(s for s in self.fixtures if s['language'] == 'en' and s['source_row'] == 0)
                    self.play(sample)
                    require(self.player.wait(timeout=sample['audio_seconds'] + 20) == 0, 'loader-playback-failed')
                    if self.status(check=False).get('state') == 'recording':
                        self.status('stop', check=False)
            terminal = self.observe('loader-terminal', lambda: (v if (v := self.status(check=False)).get('state') in ('ready', 'error') else None), 240)
            continued = terminal.get('state') == 'ready'
            continuation = []
            if continued:
                # The native backend can swallow loader initialization errors
                # and complete locally on CPU. The controller selects a Vulkan
                # executable; its status alone cannot prove a native GPU device.
                sample = next(s for s in self.fixtures if s['language'] == 'en' and s['source_row'] == 0)
                previous, stable = None, 0
                def received():
                    nonlocal previous, stable
                    text = (self.root / 'received.private').read_text()
                    stable = stable + 1 if text and text == previous else 0
                    previous = text
                    return text if stable >= 3 else None
                hypothesis = self.observe('loader-delivery', received, 5)
                require(hypothesis and '\n' not in hypothesis and self.focused(), 'loader-continuation-insertion-failed')
                self.phrases.append(hypothesis)
                metrics = self.accuracy.metrics((DATA / 'dictation-fixtures' / sample['reference']).read_text(), hypothesis)
                continuation.append({'language': 'en', 'source_row': 0, 'purpose': 'loader-continuation',
                    'wav_sha256': sample['wav_sha256'], 'reference_sha256': sample['reference_sha256'],
                    'hypothesis_sha256': hashlib.sha256(hypothesis.encode()).hexdigest(),
                    'elapsed_ns': time.monotonic_ns() - attempted, 'audio_frames': sample['audio_frames'],
                    'sample_rate': 16000, 'reference_words': metrics['reference_words'], 'word_edits': metrics['word_edits'],
                    'reference_chars': metrics['reference_characters'], 'char_edits': metrics['character_edits'],
                    'backend': 'cpu-inferred-after-loader-fault', 'cpu_variant': 'vulkan-build',
                    'binary_sha256': self.assets['vulkan']['sha256'], 'model_sha256': self.assets['model']['sha256']})
                self.empty()
                # A successful native continuation does not activate Arctic's
                # session fallback. Explicitly select CPU for the new recording.
                self.status('set-backend', 'cpu')
            else:
                require(terminal.get('ok') is False and terminal.get('active_backend') == 'cpu'
                        and terminal.get('backend') == 'vulkan' and terminal.get('error') in (
                            'GPU initialization failed. CPU is selected for this session; record again.',
                            'GPU transcription failed. CPU is selected for this session; record again.'),
                        'loader-error-not-actionable-cpu-retry')
                require((self.root / 'received.private').read_bytes() == b'', 'loader-error-inserted-text')
            self.no_engine(); require(not self.transcript_files(), 'loader-error-retained-transcript')
            time.sleep(.5); self.no_engine()
            require((self.root / 'received.private').read_bytes() == b'', 'loader-receiver-not-empty-before-retry')
            retries = []
            for language in ('en', 'he'):
                self.broker_identity(broker)
                require(self.status().get('backend') == ('cpu' if continued else 'vulkan'), 'loader-retry-preference-changed')
                sample = next(s for s in self.fixtures if s['language'] == language and s['source_row'] == 0)
                retries.append(self.transcribe(sample, 'cpu-loader-retry', store=False, loader=(broker, environment)))
                self.broker_identity(broker)
            return {'count': 2, 'active_backend_vulkan': True, 'active_backend_cpu': True,
                    'fresh_broker': True, 'inherited_loader_environment': True,
                    'actionable_gpu_error': not continued, 'cpu_continuation_inferred': continued,
                    'native_backend_directly_observed': False, 'cpu_preference_explicitly_selected': continued,
                    'receiver_empty_before_retry': True,
                    'explicit_new_cpu_recordings': True, 'drained': True,
                    'pid': broker[0], 'start_ticks': broker[1], 'socket_inode': broker[2],
                    'sha256': sha(icd), 'retry_samples': retries, 'continuation_samples': continuation}
        finally:
            errors = []
            def stop_broker():
                if broker is not None and (Path('/proc') / str(broker[0])).exists():
                    self.broker_identity(broker); self.status('cancel', check=False)
                    self.kill_identity(broker[0], broker[1])
            for operation in (lambda: self.kill(activation), lambda: self.kill(self.player),
                              stop_broker, lambda: self.kill(wrapper),
                              lambda: self.status('cancel', check=False), self.no_engine,
                              lambda: self.status('set-backend', 'cpu'), lambda: icd.unlink(missing_ok=True)):
                try:
                    operation()
                except (Invalid, OSError, ValueError, subprocess.TimeoutExpired):
                    errors.append(True)
            self.player = None
            require(not errors, 'loader-owned-cleanup-failed')

    @staticmethod
    def kill_identity(pid, ticks):
        descriptor = os.pidfd_open(pid)
        try:
            require(iter_process(pid) == ticks, 'owned-process-reused-before-signal')
            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
        finally:
            os.close(descriptor)

    def published(self):
        self.empty(); self.status('set-backend', 'cpu')
        require(self.status('start')['state'] == 'recording', 'indicator-recording-not-started')
        value = read(self.runtime / 'arctic/dictation.json')
        require(value.get('state') == 'recording' and value.get('active_backend') == 'cpu', 'recording-status-not-published')
        # Image is transcript-free here. The report hashes it; visual review is separate.
        screenshot = self.root / 'recording-indicator.png'
        self.cmd(['/usr/bin/grim', str(screenshot)])
        require(screenshot.is_file() and screenshot.stat().st_size > 1000, 'indicator-screenshot-missing')
        require((self.root / 'received.private').read_bytes() == b'', 'indicator-receiver-not-empty')
        nonce = os.urandom(16).hex()
        print('ARCTIC-DICTATION-RECORDING-INDICATOR-REQUESTED ' + json.dumps({
            'boot_id': self.report['boot_id'], 'installation_id': self.context['installation_id'],
            'phase': self.context['phase'], 'desktop_uid': self.account.pw_uid, 'receiver_empty': True,
            'capture_nonce': nonce}), flush=True)
        # No speech playback can begin until the host captures this empty scene
        # and acknowledges it through the actual owned GTK/Wayland receiver.
        wait(lambda: (self.root / 'received.private').read_text() == nonce, 45)
        self.empty()
        require(self.status().get('state') == 'recording'
                and (self.root / 'received.private').read_bytes() == b'', 'indicator-interval-not-empty-recording')
        proof = {'snapshot_sha256': sha(screenshot), 'ready': True,
                 'sha256': hashlib.sha256(nonce.encode()).hexdigest()}
        self.status('cancel'); return proof

    def cleanup_check(self):
        self.status('cancel', check=False); self.no_engine()
        # Upstream may use .txt.tmp/.txt.done as well as controller file names.
        remaining = self.transcript_files()
        require(not remaining, 'private-transcript-files-remain')
        return {'file_count': 0, 'drained': True}

    def transcript_files(self):
        return [p for p in self.private.iterdir() if p.name.startswith(('transcript', '.transcript'))]

    def leakage(self):
        require(len(self.phrases) >= 10, 'leak-scan-missing-real-hypotheses')
        rows = run(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor, '-o', 'json'], 60).stdout.decode()
        journal = '\n'.join(str(json.loads(line).get('MESSAGE', '')) for line in rows.splitlines() if line)
        notices = self.cmd(['/usr/bin/arctic-shell-ipc', 'notifications', 'history']).stdout.decode()
        # Also inspect the fallback daemon if it actually owns a user process.
        fallback = self.cmd(['/usr/bin/pgrep', '-u', str(self.account.pw_uid), '-x', 'mako'], check=False)
        if fallback.returncode == 0:
            notices += '\n' + self.cmd(['/usr/bin/makoctl', 'list']).stdout.decode()
        status = (self.runtime / 'arctic/dictation.json').read_text()
        material = self.accuracy.normalize('\n'.join([journal, notices, status, *self.snapshots]))
        for phrase in self.phrases:
            normalized = self.accuracy.normalize(phrase)
            require(len(normalized) >= 12, 'leak-scan-excerpt-too-short')
            fragments = {normalized[index:index + 12] for index in range(len(normalized) - 11)}
            require(not any(fragment in material for fragment in fragments), 'transcript-found-in-public-surface')
        return {'count': len(self.phrases), 'matched': 0}

    def pending(self):
        def settled():
            value = self.status()
            require(value.get('ready') is False, 'offline-became-ready')
            return value if value.get('state') != 'downloading' else None
        value = wait(settled, 660)
        require(value.get('state') in ('queued', 'error') and (SYSTEM / 'pending.json').is_file()
                and not (SYSTEM / 'verified.json').exists(), 'offline-queue-missing-or-false-ready')
        require(value.get('download_bytes') == PROFILES[self.profile_id]['download_bytes'], 'offline-size-undisclosed')
        require(not any((PAYLOAD / name).exists() for name in (asset['name'] for asset in ASSETS.values())), 'offline-payload-unexpected')
        require(run(['systemctl', 'is-enabled', 'arctic-dictation-setup.timer']).stdout.strip() == b'enabled', 'offline-firstboot-timer-not-enabled')
        error = self.status('start', check=False)
        require(error.get('ok') is False and bool(error.get('error')), 'offline-recording-not-blocked')
        return {'ready': False, 'pending': True}

    def os_healthy(self):
        self.offline()
        require(self.cmd(['mmsg', 'get', 'all-clients']).returncode == 0, 'offline-desktop-not-responsive')
        require(run(['systemctl', 'is-active', 'NetworkManager']).stdout.strip() == b'active', 'offline-network-manager-inactive')
        return {'ready': True}

    def recovery(self):
        require(run(['systemctl', 'is-enabled', 'arctic-dictation-setup.timer']).stdout.strip() == b'enabled', 'recovery-timer-not-enabled')
        automatic = self.status().get('ready') is True and not (SYSTEM / 'pending.json').exists()
        require(automatic or (SYSTEM / 'pending.json').is_file(), 'recovery-neither-pending-nor-ready')
        run(['/usr/libexec/arctic/arctic-dictation-setup'], 750)
        value = wait(lambda: (v if (v := self.status()).get('ready') is True
                                   and not (SYSTEM / 'pending.json').exists() else None), 750)
        require(value.get('state') == 'ready', 'recovery-not-ready')
        return dict(self.ready(), automatic_ready=automatic)

    def absence(self):
        require(not PAYLOAD.exists() and not (SYSTEM / 'verified.json').exists(), 'live-payload-receipt-present')
        require(Path('/run/rootfsbase').is_dir(), 'live-base-unavailable')
        forbidden = set((asset['name'] for asset in ASSETS.values())) | {'voxtype', 'ggml-base.bin', 'ggml-tiny.bin', 'ggml-medium.bin', 'ggml-large.bin'}
        def failed(_error):
            raise Invalid('live-base-scan-unreadable')
        for base, directories, names in os.walk('/run/rootfsbase', followlinks=False, onerror=failed):
            require(not forbidden.intersection(names), 'live-speech-payload-or-model-present')
            require(not any(name.startswith('ggml-') and name.endswith('.bin') for name in names), 'live-whisper-weight-present')
        return {'file_count': 0}

    def unavailable(self):
        value = self.status()
        require(value.get('ready') is False, 'live-controller-false-readiness')
        return {'ready': False}

    def security(self):
        require(run(['getenforce']).stdout.strip() == b'Enforcing', 'selinux-not-enforcing')
        return {'ready': True}

    def avcs(self):
        self.security()
        rows = run(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor, '-o', 'json'], 60).stdout.decode()
        journal = '\n'.join(str(json.loads(line).get('MESSAGE', '')) for line in rows.splitlines() if line)
        after = self.audit_state()
        require(after['enabled'] == self.audit_before['enabled'] and after['enabled'] in (1, 2)
                and after['lost'] == self.audit_before['lost'], 'audit-disabled-or-lost-records')
        if self.audit_offset:
            require(self.audit_file.exists(), 'audit-log-disappeared')
            info = self.audit_file.stat(); dev, ino, offset = self.audit_offset
            require((info.st_dev, info.st_ino) == (dev, ino) and offset <= info.st_size
                    and info.st_size - offset <= 8 * 1024 * 1024, 'audit-interval-rotated-or-oversized')
            with self.audit_file.open('rb') as stream:
                stream.seek(offset); journal += '\n' + stream.read().decode(errors='replace')
        elif self.audit_file.exists():
            require(self.audit_file.stat().st_size <= 8 * 1024 * 1024, 'audit-new-log-oversized')
            journal += '\n' + self.audit_file.read_text(errors='replace')
        require(not re.search(r'(?i)\bavc:\s*denied|type=(?:USER_)?AVC', journal), 'new-selinux-avc')
        return {'avcs': 0, 'audit_lost': after['lost'], 'audit_enabled': after['enabled'],
                'audit_lost_before': self.audit_before['lost'], 'audit_enabled_before': self.audit_before['enabled']}

    @staticmethod
    def audit_state():
        text = run(['auditctl', '-s']).stdout.decode()
        values = {k: int(v) for k, v in re.findall(r'^(enabled|lost)\s+(\d+)$', text, re.M)}
        require(set(values) == {'enabled', 'lost'}, 'audit-status-unavailable')
        return values

    def session(self):
        self.session_preflight_stage = 'accuracy-module-import'
        spec = importlib.util.spec_from_file_location('arctic_accuracy', DATA / 'dictation-accuracy/accuracy.py')
        self.accuracy = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.accuracy)
        self.session_preflight_stage = 'fixture-bundle-validation'
        try:
            self.fixtures = self.accuracy.load_fixtures(DATA / 'dictation-fixtures', self.context['fixture_manifest_sha256'])
        except self.accuracy.Invalid:
            raise Invalid('fixture-bundle-validation-failed') from None
        self.session_preflight_stage = 'broker-cancel'
        self.status('cancel', check=False)
        self.session_preflight_stage = 'cpu-backend-selection'
        self.status('set-backend', 'cpu')
        self.session_preflight_stage = 'virtual-microphone-route'
        self.route()
        self.session_preflight_stage = 'receiver-window'
        self.window_start()
        self.session_preflight_stage = None
        require(self.gate('local-offline-transcription', self.offline, 'actual-boot'), 'session-network-not-isolated')
        require(self.gate('recording-status-published', self.published), 'indicator-handshake-incomplete')
        self.gate('cpu-english-transcription-insertion', lambda: self.samples('en'))
        self.gate('cpu-hebrew-transcription-insertion', lambda: self.samples('he'))
        self.gate('cancel-discards', self.cancel)
        self.gate('broker-death-discards', self.broker_death, 'owned-process-kill-fixture')
        self.gate('missing-model-error', self.missing, 'file-removal-fixture')
        self.gate('microphone-disconnect-error', self.microphone, 'device-disconnect-fixture')
        self.gate('lock-discards', self.locked)
        if self.profile_id == 'turbo-q5-v3':
            if self.gate('gpu-runtime-failure-cpu-retry', self.gpu_failure, 'owned-process-kill-fixture'):
                self.gate(LOADER_GPU_GATE, self.gpu_loader_failure, 'loader-configuration-fixture')
        else:
            self.gate(LEGACY_GPU_GATE, self.legacy_gpu)
        self.gate('transcript-private-cleanup', self.cleanup_check)
        self.gate('transcript-log-notification-leak-scan', self.leakage, 'interval-log-scan')

    def execute(self):
        phase = self.context['phase']
        failure_code = 'prerequisite-or-collector-failed'
        self.gate('selinux-enforcing', self.security, 'actual-boot')
        if phase == 'live':
            self.gate('live-payload-model-absent', self.absence, 'actual-installed-files')
            self.gate('live-controller-unavailable', self.unavailable)
        else:
            self.gate('encrypted-installed-boot', self.encrypted, 'actual-boot')
            if phase == 'offline-installed':
                self.gate('offline-setup-pending', self.pending)
                self.gate('offline-os-healthy', self.os_healthy, 'actual-boot')
            elif phase == 'recovery':
                self.gate('explicit-service-recovery-ready', self.recovery)
                self.gate('installed-payload-integrity', self.payload, 'actual-installed-files')
            else:
                readiness = 'online-installer-ready' if phase == 'online-installed' else 'recovered-ready'
                available = self.gate(readiness, self.ready)
                integrity = self.gate('installed-payload-integrity', self.payload, 'actual-installed-files')
                if available and integrity:
                    try:
                        self.session()
                    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
                        stage = getattr(self, 'session_preflight_stage', None)
                        if stage in SESSION_PREFLIGHT_STAGES:
                            failure_code = session_diagnostic_code(stage, error)
        self.gate('no-new-avcs', self.avcs, 'interval-log-scan')
        present = {g['id'] for g in self.report['gates']}
        for name in sorted(self.gates - present):
            self.report['gates'].append({'id': name, 'status': 'unrun', 'evidence_kind': EXPECTED_KINDS[name],
                                        'code': failure_code, 'observations': {}})
        self.report['status'] = 'passed' if all(g['status'] == 'passed' for g in self.report['gates']) else 'failed'
        return self.report

    def close(self):
        errors = []
        try:
            self.status('cancel', check=False)
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired):
            errors.append(True)
        for operation in (lambda: self.kill(self.player), lambda: self.kill(self.window),
                          lambda: self.destroy_route() if self.loop else None,
                          lambda: shutil.rmtree(self.root)):
            try:
                operation()
            except (Invalid, OSError, ValueError, subprocess.TimeoutExpired):
                errors.append(True)
        require(not errors, 'owned-cleanup-failed')

def main():
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if len(sys.argv) == 4 and sys.argv[1] == '_receiver':
        receiver(sys.argv[2], sys.argv[3]); return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('live', 'installed'))
    parser.add_argument('--disposable-guest', action='store_true')
    args = parser.parse_args()
    require(args.disposable_guest and os.geteuid() == 0, 'explicit-root-disposable-guest-required')
    require(HERE == DATA / 'dictation-qualification', 'reviewed-test-cd-location-required')
    require(run(['systemd-detect-virt']).stdout.strip() in (b'qemu', b'kvm'), 'qemu-kvm-guest-required')
    live = 'rd.live.image' in Path('/proc/cmdline').read_text().split()
    require(live == (args.stage == 'live'), 'actual-boot-stage-mismatch')
    declared = context(read(DATA / 'dictation-context.json'))
    if live:
        declared = dict(declared, phase='live')
    require((declared['phase'] == 'live') == live, 'context-boot-stage-mismatch')
    for path, key in ((HERE / 'guest_check.py', 'checker_sha256'), (HERE / 'contract.py', 'contract_sha256'),
                      (DATA / 'dictation-accuracy/accuracy.py', 'accuracy_sha256'),
                      (DATA / 'dictation-accuracy/pins.json', 'pins_sha256'), (CONTROLLER, 'controller_sha256'),
                      (CHILD_EXEC, 'child_exec_sha256')):
        if path in (CONTROLLER, CHILD_EXEC):
            owned_file(path)
        require(sha(path) == declared[key], 'reviewed-source-hash-mismatch')
    checker = Checker(declared)
    report = checker.report
    try:
        report = checker.execute()
    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):
        pass
    finally:
        try:
            checker.close()
        except (OSError, Invalid, subprocess.TimeoutExpired):
            report = checker.report
            failed_gate = 'transcript-private-cleanup' if 'transcript-private-cleanup' in checker.gates else 'no-new-avcs'
            for gate in report['gates']:
                if gate['id'] == failed_gate:
                    gate.update(status='failed', code='owned-cleanup-failed')
    present = {g['id'] for g in report['gates']}
    for name in sorted(checker.gates - present):
        report['gates'].append({'id': name, 'status': 'unrun', 'evidence_kind': EXPECTED_KINDS[name],
                               'code': 'prerequisite-or-collector-failed', 'observations': {}})
    report['status'] = 'passed' if all(g['status'] == 'passed' for g in report['gates']) else 'failed'
    validate(report, declared, fixture_manifest=DATA / 'dictation-fixtures/fixtures.json')
    print('ARCTIC-DICTATION-QUALIFICATION ' + json.dumps(report, sort_keys=True), flush=True)
    return int(report['status'] != 'passed')

if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):
        print('ARCTIC-DICTATION-COLLECTOR-ERROR {"code":"collector-guard-or-setup-failed","release_acceptance":false}', flush=True)
        sys.exit(1)
