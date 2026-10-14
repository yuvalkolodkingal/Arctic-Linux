#!/usr/bin/env python3
"""Disposable image checker for direct official VoxType, PipeWire and Wayland.

The test CD supplies no runtime, model, configuration, cache or readiness marker.
Public output contains fixed codes, numeric measurements and hashes only.
"""
import argparse
import grp
import ctypes
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
import stat
import subprocess
import sys
import tempfile
import tomllib
import time

from contract import (ASSETS, EXPECTED_KINDS, LEGACY_GPU_GATE, LIMITATIONS, MODERN_GPU_GATE, PROFILE_ASSETS, PROFILES, SCHEMA, UPSTREAM, Invalid, context, gates, pinned, require, validate)

HERE = Path(__file__).resolve().parent
DATA = Path('/run/t')
VOXTYPE = Path('/usr/bin/voxtype')
ADAPTER = Path('/usr/bin/arctic-dictation')
TOGGLE = Path('/usr/bin/arctic-dictation-toggle')
SETUP = Path('/usr/libexec/arctic/arctic-voxtype-setup')
HOST_PROFILE = Path('/usr/libexec/arctic/arctic-voxtype-host-profile')
CONFIGURE = Path('/usr/libexec/arctic/arctic-voxtype-configure')
KEY = Path('/usr/share/arctic/dictation/voxtype-release-key.asc')
POLICY = Path('/usr/share/polkit-1/actions/org.arcticlinux.dictation.policy')
UNIT = Path('/usr/lib/systemd/user/voxtype.service')
SETUP_SERVICE = Path('/usr/lib/systemd/system/arctic-dictation-setup.service')
SETUP_TIMER = Path('/usr/lib/systemd/system/arctic-dictation-setup.timer')
SKEL_BINDINGS = Path('/etc/skel/.config/mango/arctic/binds.conf')
PAYLOAD = Path('/opt/arctic/voxtype/1.1.0')
MODELS = Path('/opt/arctic/voxtype/models')
SYSTEM = Path('/var/lib/arctic/dictation')
COLLECTOR_SETUP_STAGES = ('resource-limits', 'arguments', 'environment', 'context',
                          'source-integrity', 'integration', 'profile', 'hardware',
                          'report', 'desktop', 'workspace', 'journal', 'audit', 'execution')
COLLECTOR_ERROR_TYPES = ((Invalid, 'invalid'), (OSError, 'os-error'),
                         (ValueError, 'value-error'), (subprocess.TimeoutExpired, 'timeout'),
                         (KeyError, 'key-error'), (TypeError, 'type-error'))
COLLECTOR_SETUP_STAGE = 'resource-limits'
GATE_FAILURE_CODES = {
    name: {label: 'gate-' + name + '-' + label for _error, label in COLLECTOR_ERROR_TYPES}
    for name in EXPECTED_KINDS
}
SERVICE_UNSET_ENV = frozenset({
    'RUST_LOG', 'VOXTYPE_CONFIG', 'VOXTYPE_ENGINE', 'VOXTYPE_MODEL',
    'VOXTYPE_LANGUAGE', 'VOXTYPE_TRANSLATE', 'VOXTYPE_THREADS',
    'VOXTYPE_ON_DEMAND_LOADING', 'VOXTYPE_GPU_ISOLATION',
    'VOXTYPE_GPU_DEVICE', 'VOXTYPE_FLASH_ATTENTION', 'VOXTYPE_VULKAN_DEVICE',
    'VOXTYPE_CPU_BACKUP', 'VOXTYPE_REMOTE_ENDPOINT',
    'VOXTYPE_WHISPER_API_KEY', 'SONIOX_API_KEY', 'VOXTYPE_OPENVINO_DIR',
    'VOXTYPE_OPENVINO_DEVICE', 'VOXTYPE_OPENVINO_MODEL',
    'VOXTYPE_COHERE_MODEL_DIR', 'VOXTYPE_MEETING_DIARIZATION',
    'VOXTYPE_HOTKEY', 'VOXTYPE_HOTKEY_ENABLED', 'VOXTYPE_CANCEL_KEY',
    'VOXTYPE_AUDIO_DEVICE', 'VOXTYPE_MAX_DURATION_SECS',
    'VOXTYPE_AUDIO_FEEDBACK', 'VOXTYPE_PAUSE_MEDIA', 'VOXTYPE_DUCK_MEDIA',
    'VOXTYPE_DUCK_MEDIA_VOLUME_PERCENT', 'VOXTYPE_DUCK_MEDIA_FADE_MS',
    'VOXTYPE_OUTPUT_MODE', 'VOXTYPE_APPEND_TEXT', 'VOXTYPE_AUTO_SUBMIT',
    'VOXTYPE_SHIFT_ENTER_NEWLINES', 'VOXTYPE_PRE_TYPE_DELAY',
    'VOXTYPE_TYPE_DELAY', 'VOXTYPE_FALLBACK_TO_CLIPBOARD',
    'VOXTYPE_PASTE_KEYS', 'VOXTYPE_WTYPE_SHIFT_PREFIX',
    'VOXTYPE_DOTOOL_XKB_LAYOUT', 'VOXTYPE_DOTOOL_XKB_VARIANT',
    'VOXTYPE_EITYPE_XKB_LAYOUT', 'VOXTYPE_EITYPE_XKB_VARIANT',
    'VOXTYPE_SMART_AUTO_SUBMIT', 'VOXTYPE_FILTER_FILLERS',
    'VOXTYPE_SPOKEN_PUNCTUATION', 'VOXTYPE_RESTORE_CLIPBOARD',
    'VOXTYPE_RESTORE_CLIPBOARD_DELAY_MS', 'VOXTYPE_CONTEXT',
})


class MicrophoneIsolationUnavailable(Invalid):
    """Exact source-owned signal for a fixture the guest cannot isolate."""

def mark_collector_setup(stage):
    """Record only one source-owned setup stage; never retain failure material."""
    global COLLECTOR_SETUP_STAGE
    require(type(stage) is str and stage in COLLECTOR_SETUP_STAGES,
            'unknown-collector-setup-stage')
    COLLECTOR_SETUP_STAGE = stage


def caught_error_label(error):
    """Map a caught family without consulting its instance or foreign metaclass."""
    # isinstance() may consult a hostile exception instance's __class__ when
    # an earlier candidate does not match. Read the actual type's MRO through
    # type's built-in descriptor so no foreign instance or metaclass accessor,
    # payload, equality, text or representation can run.
    try:
        bases = type.__getattribute__(type(error), '__mro__')
    except BaseException:
        return 'unknown'
    if type(bases) is not tuple:
        return 'unknown'
    for error_class, label in COLLECTOR_ERROR_TYPES:
        if any(base is error_class for base in bases):
            return label
    return 'unknown'


def collector_diagnostic_code(stage, error):
    """Project setup failures using only built-in type metadata and identity."""
    require(type(stage) is str and stage in COLLECTOR_SETUP_STAGES,
            'unknown-collector-setup-stage')
    label = caught_error_label(error)
    return ('collector-unknown' if label == 'unknown'
            else 'collector-' + stage + '-' + label)

def verify_small_cpu_fixture(cpuinfo):
    """Check every declared two-vCPU Small fixture before any application gate.

    The host runner fixes --smp 2. Westmere-v2 supplies the x86-64-v2 floor
    without AVX or XSAVE; this checks observed guest flags, not a model name.
    No arbitrary flag, processor text or raw cpuinfo enters public output.
    """
    code = 'actual-compatibility-cpu-fixture'
    require(type(cpuinfo) is bytes and 0 < len(cpuinfo) <= 1024 * 1024, code)
    try:
        text = cpuinfo.decode('ascii')
    except UnicodeError:
        raise Invalid(code) from None
    floor = {'fpu', 'cx8', 'cmov', 'mmx', 'fxsr', 'sse', 'sse2', 'lm', 'syscall',
             'pni', 'ssse3', 'sse4_1', 'sse4_2', 'popcnt', 'cx16', 'lahf_lm'}
    excluded = {'avx', 'avx2', 'fma', 'f16c', 'bmi1', 'bmi2',
                'xsave', 'xsaveopt', 'xsavec', 'xsaves', 'osxsave'}
    records = re.split(r'\n[ \t]*\n', text.strip())
    require(len(records) == 2, code)
    processors = set()
    for record in records:
        fields = {'processor': [], 'flags': []}
        for line in record.splitlines():
            key, separator, value = line.partition(':')
            if separator and key.strip() in fields:
                fields[key.strip()].append(value.strip())
        require(all(len(values) == 1 for values in fields.values()), code)
        processor = fields['processor'][0]
        require(processor in ('0', '1') and processor not in processors, code)
        processors.add(processor)
        words = fields['flags'][0].split()
        require(0 < len(words) <= 512 and len(words) == len(set(words))
                and all(re.fullmatch(r'[a-z0-9][a-z0-9_]{0,63}', word) for word in words), code)
        flags = set(words)
        require(floor <= flags and not excluded & flags
                and not any(word.startswith(('avx', 'amx_', 'apx')) for word in words), code)
    require(processors == {'0', '1'}, code)

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

def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()

def read(path):
    return json.loads(Path(path).read_text())

def run(argv, timeout=20, check=True, output_role=None):
    require(output_role is None or (type(output_role) is str and output_role == 'interval-journal'),
            'unknown-command-output-role')
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    code = 'command-output-bound'
    if output_role is not None:
        # Only this source-assigned role and builtin byte counts enter a failed
        # gate code. Never include argv, the cursor, logs, stderr or error text.
        require(type(result.stdout) is bytes and type(result.stderr) is bytes, 'command-output-byte-types')
        code += '-journal-o' + str(len(result.stdout)) + '-e' + str(len(result.stderr))
    require(len(result.stdout) + len(result.stderr) < 16 * 1024 * 1024, code)
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


def owned_text(path, uid, code):
    """Read one bounded regular config through a no-follow descriptor."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == uid
                and not info.st_mode & 0o022 and 0 < info.st_size <= 64 * 1024, code)
        raw = os.read(fd, info.st_size + 1)
        require(len(raw) == info.st_size, code)
    finally:
        os.close(fd)
    try:
        return raw.decode('utf-8')
    except UnicodeError:
        raise Invalid(code) from None

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

def journal_messages(rows):
    """Decode every full MESSAGE value from journalctl's reversible JSON schema.

    --all retains long values; binary values and repeated fields are arrays.
    Unreadable or truncated material fails closed rather than becoming a clean
    scan. Raw messages stay private and never become diagnostic error text.
    """
    require(type(rows) is bytes, 'journal-output-byte-type')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'journal-json-duplicate-field')
            value[key] = item
        return value
    def invalid_constant(_value):
        raise Invalid('journal-json-nonfinite')
    def text(value):
        if type(value) is str:
            value.encode('utf-8')
            return value
        require(type(value) is list and all(type(byte) is int and 0 <= byte <= 255
                                           for byte in value), 'journal-message-type')
        return bytes(value).decode('utf-8')
    messages = []
    try:
        for line in rows.decode('utf-8').split('\n'):
            if not line:
                continue
            entry = json.loads(line, object_pairs_hook=unique, parse_constant=invalid_constant)
            require(type(entry) is dict, 'journal-json-entry-type')
            if 'MESSAGE' not in entry:
                continue
            value = entry['MESSAGE']
            if type(value) is list and value and not all(type(byte) is int for byte in value):
                messages.extend(text(item) for item in value)
            else:
                messages.append(text(value))
    except UnicodeError:
        raise Invalid('journal-message-encoding') from None
    except (ValueError, RecursionError):
        raise Invalid('journal-json-invalid') from None
    return '\n'.join(messages)

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

def installed_integration_sha():
    files = (
        ('packaging/dictation/arctic-dictation', ADAPTER),
        ('packaging/dictation/arctic-dictation-toggle', TOGGLE),
        ('packaging/dictation/voxtype', VOXTYPE),
        ('packaging/dictation/arctic-voxtype-setup', SETUP),
        ('packaging/dictation/arctic-voxtype-host-profile', HOST_PROFILE),
        ('packaging/dictation/arctic-voxtype-configure', CONFIGURE),
        ('packaging/dictation/voxtype-release-key.asc', KEY),
        ('packaging/dictation/org.arcticlinux.dictation.policy', POLICY),
        ('packaging/systemd/voxtype.service', UNIT),
        ('packaging/systemd/arctic-dictation-setup.service', SETUP_SERVICE),
        ('packaging/systemd/arctic-dictation-setup.timer', SETUP_TIMER),
    )
    result = hashlib.sha256()
    for name, path in files:
        owned_file(path)
        encoded = name.encode()
        result.update(len(encoded).to_bytes(4, 'big'))
        result.update(encoded)
        result.update(path.read_bytes())
    return result.hexdigest()


class Checker:
    def __init__(self, declared):
        self.context = declared
        mark_collector_setup('integration')
        self.profile_id = declared['hardware_profile']
        self.profile = PROFILES[self.profile_id]
        self.assets = PROFILE_ASSETS[self.profile_id]
        self.names = {key: asset['name'] for key, asset in self.assets.items()}
        mark_collector_setup('hardware')
        cpuinfo = Path('/proc/cpuinfo').read_bytes()
        if self.profile_id == 'small-v2':
            verify_small_cpu_fixture(cpuinfo)
        else:
            flags = [set(match.split()) for match in re.findall(rb'^flags\s*:\s*(.*)$', cpuinfo, re.M)]
            needed = {b'avx', b'avx2', b'fma', b'f16c', b'bmi1', b'bmi2'}
            require(len(flags) == 2 and all(needed <= row for row in flags),
                    'actual-modern-cpu-fixture')
        self.gates = gates(declared['phase'], self.profile_id)
        hardware = {'profile': self.profile_id,
                    'v3_supported': self.profile_id == 'turbo-q5-v3',
                    'cpuinfo_sha256': hashlib.sha256(cpuinfo).hexdigest(),
                    'profile_selection': 'recommended'}
        mark_collector_setup('report')
        self.report = {'schema': SCHEMA, 'status': 'failed', 'release_acceptance': False,
                       'context': declared,
                       'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                       'upstream': UPSTREAM, 'payload': {}, 'gates': [], 'samples': [],
                       'limitations': LIMITATIONS, 'disk': {}, 'profile': self.profile,
                       'hardware': hardware}
        mark_collector_setup('desktop')
        self.account, self.runtime, self.prefix = desktop()
        mark_collector_setup('workspace')
        self.root = Path(tempfile.mkdtemp(prefix='arctic-voxtype-test-', dir='/tmp'))
        os.chmod(self.root, 0o700)
        os.chown(self.root, self.account.pw_uid, self.account.pw_gid)
        self.prefix += ['XDG_CONFIG_HOME=' + str(Path(self.account.pw_dir) / '.config')]
        self.state_path = self.runtime / 'voxtype/state'
        self.config_path = Path(self.account.pw_dir) / '.config/voxtype/config.toml'
        self.user_bindings = Path(self.account.pw_dir) / '.config/mango/arctic/binds.conf'
        self.phrases, self.snapshots = [], []
        self.loop = self.window = self.player = None
        self.old_source = self.source = None
        self.initial_processes = {path.name for path in Path('/proc').glob('[0-9]*')}
        mark_collector_setup('journal')
        cursor = run(['journalctl', '-n', '0', '--show-cursor', '--no-pager']).stdout.decode()
        found = re.search(r'-- cursor: (\S+)', cursor)
        require(found, 'journal-cursor-unavailable')
        self.cursor = found.group(1)
        mark_collector_setup('audit')
        self.audit_before = self.audit_state()
        self.audit_file = Path('/var/log/audit/audit.log')
        self.audit_offset = None
        if self.audit_file.exists():
            info = self.audit_file.stat()
            self.audit_offset = (info.st_dev, info.st_ino, info.st_size)

    def cmd(self, argv, timeout=20, check=True):
        return run(self.prefix + argv, timeout, check)

    def gate(self, name, fn, kind=None):
        require(name in self.gates, 'unknown-gate')
        result = {'id': name, 'status': 'failed',
                  'evidence_kind': kind or EXPECTED_KINDS[name],
                  'code': 'collector-failed', 'observations': {}}
        try:
            result.update(status='passed', code='observed', observations=fn() or {})
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
            label = caught_error_label(error)
            result['code'] = GATE_FAILURE_CODES[name].get(label, 'gate-' + name + '-unknown')
            if type(error) is MicrophoneIsolationUnavailable:
                result['code'] = 'gate-microphone-disconnect-error-isolation-unavailable'
                result['status'] = 'unrun'
        self.report['gates'].append(result)
        return result['status'] == 'passed'

    def adapter(self, *args, check=True):
        result = self.cmd([str(ADAPTER), *args], check=check)
        require(len(result.stdout) <= 16384 and len(result.stderr) <= 16384,
                'adapter-output-bound')
        if args == ('status',):
            def unique(pairs):
                value = {}
                for key, item in pairs:
                    require(key not in value, 'adapter-status-fields')
                    value[key] = item
                return value
            value = json.loads(result.stdout, object_pairs_hook=unique)
            require(type(value) is dict and set(value) == {
                        'state', 'ready', 'error', 'version', 'language', 'backend',
                        'profile', 'model', 'model_download_bytes', 'download_bytes',
                        'vulkan_download_bytes'}
                    and value.get('state') in {
                        'unavailable', 'queued', 'downloading', 'ready', 'recording',
                        'transcribing', 'error'}
                    and type(value.get('ready')) is bool
                    and type(value.get('error')) is str
                    and len(value.get('error')) <= 512
                    and value.get('version') == '1.1.0'
                    and value.get('language') in ('auto', 'he', 'en')
                    and value.get('backend') in ('cpu', 'vulkan')
                    and value.get('profile') in PROFILES
                    and value.get('model') == PROFILES[value['profile']]['model']
                    and value.get('model_download_bytes') == PROFILES[value['profile']]['model_download_bytes']
                    and value.get('download_bytes') == PROFILES[value['profile']]['download_bytes']
                    and value.get('vulkan_download_bytes') == ASSETS['vulkan']['bytes'],
                    'adapter-status-contract')
            self.snapshots.append(result.stdout.decode())
            return value
        return result

    def record(self, action, check=True):
        require(action in ('start', 'stop', 'toggle', 'cancel'),
                'unknown-upstream-record-command')
        result = self.cmd([str(VOXTYPE), 'record', action], check=check)
        require(len(result.stdout) + len(result.stderr) <= 16384,
                'upstream-command-output-bound')
        return result

    def state(self, allow_absent=False):
        if not self.state_path.exists() and allow_absent:
            return 'stopped'
        fd = os.open(self.state_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == self.account.pw_uid
                    and not info.st_mode & 0o077 and 0 < info.st_size <= 32,
                    'upstream-state-file-unsafe')
            raw = os.read(fd, 33)
        finally:
            os.close(fd)
        try:
            value = raw.decode('ascii').strip()
        except UnicodeError:
            raise Invalid('upstream-state-invalid') from None
        require(value in ('idle', 'recording', 'transcribing', 'streaming'),
                'upstream-state-invalid')
        return value

    def observe(self, _target, fn, seconds=20):
        return wait(fn, seconds)

    def empty(self):
        path = self.root / 'clear'
        path.touch(mode=0o600)
        os.chown(path, self.account.pw_uid, self.account.pw_gid)
        self.observe('receiver-clear',
                     lambda: not path.exists() and (self.root / 'received.private').read_bytes() == b'')

    def engines(self):
        binaries = {PAYLOAD / asset['name'] for key, asset in ASSETS.items()
                    if key in ('cpu', 'avx2', 'vulkan')}
        found = []
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                exe = (proc / 'exe').resolve(strict=True)
                if proc.stat().st_uid == self.account.pw_uid and exe in binaries:
                    found.append((int(proc.name), iter_process(proc.name), exe))
            except (OSError, ValueError):
                pass
        return found

    def engine(self):
        found = self.engines()
        require(len(found) == 1, 'upstream-daemon-not-unique')
        return found[0]

    def payload(self):
        receipt_path = SYSTEM / 'verified.json'
        owned_file(receipt_path)
        receipt = read(receipt_path)
        require(receipt.get('version') == UPSTREAM['version']
                and receipt.get('source_commit') == UPSTREAM['source_commit']
                and receipt.get('release_signing_fingerprint') == UPSTREAM['signed_sums_fingerprint']
                and receipt.get('profile') == self.profile_id
                and receipt.get('user') == self.account.pw_name,
                'receipt-upstream-profile-pin')
        observed = {}
        for key, asset in self.assets.items():
            path = (MODELS if key == 'model' else PAYLOAD) / asset['name']
            info = owned_file(path, asset['bytes'])
            require(sha(path) == asset['sha256'], 'installed-payload-sha256')
            require(key == 'model' or info.st_mode & 0o111,
                    'installed-binary-not-executable')
            observed[key] = {'bytes': asset['bytes'], 'sha256': asset['sha256']}
        binary_key = 'avx2' if self.profile_id == 'turbo-q5-v3' else 'cpu'
        binary = self.assets[binary_key]
        model = self.assets['model']
        require(receipt.get('integration') == 'upstream-direct-v1'
                and receipt.get('binary') == binary['name']
                and receipt.get('binary_bytes') == binary['bytes']
                and receipt.get('binary_sha256') == binary['sha256']
                and receipt.get('model_path') == str(MODELS / model['name'])
                and receipt.get('model') == model['name'].removeprefix('ggml-')
                and receipt.get('model_bytes') == model['bytes']
                and receipt.get('model_sha256') == model['sha256']
                and receipt.get('backend') in ('cpu', 'vulkan'),
                'receipt-selected-assets-pin')
        self.report['payload'] = pinned(self.profile_id)
        return {'file_count': len(self.assets)}

    def ready(self):
        value = self.adapter('status')
        require(value.get('ready') is True and value.get('profile') == self.profile_id
                and value.get('backend') in ('cpu', 'vulkan')
                and not (SYSTEM / 'pending').exists(), 'upstream-not-ready')
        marker = SYSTEM / 'upstream-direct-v1'
        owned_file(marker)
        require(marker.read_text() == 'upstream-direct-v1\n',
                'upstream-readiness-marker-invalid')
        require(self.cmd(['systemctl', '--user', 'is-active', 'voxtype.service']).stdout.strip() == b'active',
                'upstream-user-service-inactive')
        require(self.state() == 'idle', 'upstream-daemon-not-idle')
        return {'ready': True, 'pending': False}

    def command_contract(self):
        help_result = self.cmd([str(VOXTYPE), 'record', '--help'])
        text = help_result.stdout.decode()
        require(all(re.search(r'^\s*' + name + r'\s', text, re.M)
                    for name in ('start', 'stop', 'toggle', 'cancel')),
                'upstream-record-help-contract')
        self.record('cancel')
        for forbidden in ('start', 'stop', 'toggle', 'cancel'):
            result = self.cmd([str(ADAPTER), forbidden], check=False)
            require(result.returncode != 0, 'setup-adapter-controls-recording')
        guard = owned_text(TOGGLE, 0, 'dictation-toggle-guard-unsafe')
        require('voxtype record toggle' in guard,
                'dictation-toggle-guard-not-upstream')
        for path, uid in ((SKEL_BINDINGS, 0), (self.user_bindings, self.account.pw_uid)):
            binds = owned_text(path, uid, 'mango-bindings-unsafe')
            require('spawn,arctic-dictation-toggle' in binds
                    and 'spawn,voxtype record cancel' in binds,
                    'mango-not-bound-directly-to-upstream')
        return {'command_count': 4}

    def state_contract(self):
        unit = UNIT.read_text()
        unset = [word for line in unit.splitlines()
                 if line.startswith('UnsetEnvironment=')
                 for word in line.partition('=')[2].split()]
        require('ExecStart=/usr/bin/voxtype --config %h/.config/voxtype/config.toml -q daemon' in unit
                and 'ConditionPathExists=%h/.config/voxtype/config.toml' in unit
                and 'UMask=0077' in unit
                and 'RestrictAddressFamilies=AF_UNIX' in unit
                and len(unset) == len(set(unset))
                and set(unset) == SERVICE_UNSET_ENV
                and not any(line.startswith('Environment=') for line in unit.splitlines()),
                'upstream-service-privacy-contract')
        require(self.state() == 'idle', 'upstream-initial-state-not-idle')
        return {'allowed_state_count': 4}

    def config_contract(self):
        info = self.config_path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == self.account.pw_uid
                and not info.st_mode & 0o077, 'voxtype-config-unsafe')
        config = tomllib.loads(self.config_path.read_text())
        whisper = config.get('whisper', {})
        output = config.get('output', {})
        notification = output.get('notification', {})
        language = whisper.get('language')
        require(config.get('engine') == 'whisper' and config.get('state_file') == 'auto'
                and config.get('hotkey', {}).get('enabled') is False
                and whisper.get('mode') == 'local'
                and whisper.get('model') == str(MODELS / self.names['model'])
                and language == ['he', 'en']
                and output.get('mode') == 'type'
                and output.get('driver_order') == ['wtype']
                and output.get('fallback_to_clipboard') is False
                and notification.get('on_transcription') is False
                and not any(key.startswith('remote') for key in whisper),
                'voxtype-local-he-en-config')
        return {'language_count': 2}

    def no_input(self):
        memberships = set(os.getgrouplist(self.account.pw_name, self.account.pw_gid))
        try:
            input_gid = grp.getgrnam('input').gr_gid
        except KeyError:
            input_gid = None
        require(input_gid is None or input_gid not in memberships,
                'desktop-user-has-input-group')
        return {'input_group_membership': 0}

    def encrypted(self):
        root = run(['findmnt', '-n', '-o', 'SOURCE', '/']).stdout.decode().strip()
        require(root.startswith('/dev/mapper/') and 'luks' in Path('/etc/crypttab').read_text(),
                'encrypted-root-not-observed')
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
                      '--connect-timeout', '3', '--max-time', '5',
                      'http://fedoraproject.org/'], check=False)
        require(result.returncode != 0 and result.stdout == b'000', 'outside-network-response')
        return {'returncode': result.returncode}

    def route(self):
        for name in ('pw-loopback', 'pw-play', 'pw-dump', 'wpctl'):
            require(Path('/usr/bin', name).is_file(), 'native-audio-tool-missing')
        help_text = self.cmd(['/usr/bin/pw-loopback', '--help']).stdout.decode()
        require(all(flag in help_text for flag in ('--channels', '--channel-map',
                                                    '--capture-props', '--playback-props')),
                'loopback-flags-unavailable')
        old = self.cmd(['/usr/bin/wpctl', 'inspect', '@DEFAULT_AUDIO_SOURCE@'], check=False)
        match = re.search(r'\bid (\d+),', old.stdout.decode())
        self.old_source = int(match.group(1)) if match else None
        nonce = os.urandom(8).hex()
        self.sink_name = 'ArcticVoxtypeFixtureSink' + nonce
        self.source_name = 'ArcticVoxtypeFixtureSource' + nonce
        self.loop = subprocess.Popen(self.prefix + ['/usr/bin/pw-loopback', '--channels=1',
            '--channel-map=[ MONO ]',
            '--capture-props=audio.rate=16000 media.class=Audio/Sink node.name=' + self.sink_name,
            '--playback-props=audio.rate=16000 media.class=Audio/Source node.name=' + self.source_name],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        def observed():
            require(self.loop.poll() is None, 'loopback-process-died')
            objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
            sources = [row['id'] for row in objects if row.get('type') == 'PipeWire:Interface:Node'
                       and row.get('info', {}).get('props', {}).get('node.name') == self.source_name
                       and row.get('info', {}).get('props', {}).get('media.class') == 'Audio/Source']
            sinks = [row['id'] for row in objects if row.get('type') == 'PipeWire:Interface:Node'
                     and row.get('info', {}).get('props', {}).get('node.name') == self.sink_name]
            return sources[0] if len(sources) == len(sinks) == 1 else None
        self.source = wait(observed)
        self.cmd(['/usr/bin/wpctl', 'set-default', str(self.source)])

    def destroy_route(self, restore=True):
        if self.loop:
            self.kill(self.loop)
            self.loop = None
        if restore:
            if self.old_source is not None:
                self.cmd(['/usr/bin/wpctl', 'set-default', str(self.old_source)])
            else:
                self.cmd(['/usr/bin/wpctl', 'clear-default', '1'])
        self.source = None

    @staticmethod
    def kill(child):
        if child and child.poll() is None:
            os.killpg(child.pid, signal.SIGTERM)
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=3)

    def window_start(self):
        nonce = 'arctic-voxtype-qualification-' + os.urandom(8).hex()
        self.window = subprocess.Popen(self.prefix + ['/usr/bin/python3', str(HERE / 'guest_check.py'),
                                          '_receiver', str(self.root), nonce],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        def owned_window():
            require(self.window.poll() is None, 'receiver-process-died')
            clients = json.loads(self.cmd(['mmsg', 'get', 'all-clients']).stdout)['clients']
            rows = [row for row in clients if row.get('title') == nonce]
            require(len(rows) <= 1, 'receiver-window-duplicate')
            if rows:
                row = rows[0]
                require(row['is_xwayland'] is False and row['is_visible'] is True
                        and Path('/proc', str(row['pid'])).stat().st_uid == self.account.pw_uid,
                        'receiver-window-identity')
                return row
        self.client = wait(owned_window)
        result = json.loads(self.cmd(['mmsg', 'dispatch', 'focusid',
                                      'client,' + str(self.client['id'])]).stdout)
        require(result.get('success') is True, 'receiver-focus-request-failed')
        wait(lambda: self.focused())
        wait(lambda: (self.root / 'received.private').exists())

    def focused(self):
        rows = json.loads(self.cmd(['mmsg', 'get', 'all-clients']).stdout)['clients']
        owned = [row for row in rows if row['id'] == self.client['id']
                 and row['pid'] == self.client['pid']]
        require(len(owned) == 1, 'receiver-window-disappeared')
        return owned[0].get('is_focused') is True and owned[0].get('is_visible') is True

    def capture_link(self):
        engines = self.engines()
        require(len(engines) == 1, 'recording-engine-not-unique')
        pid = engines[0][0]
        objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
        owned, captures = authenticated_capture_nodes(objects, pid, self.account.pw_uid)
        require(self.engines() == engines, 'recording-engine-changed')
        linked = any(row.get('type') == 'PipeWire:Interface:Link'
                     and row.get('info', {}).get('output-node-id') == self.source
                     and row.get('info', {}).get('input-node-id') in captures
                     for row in objects) if captures else False
        source = any(row.get('type') == 'PipeWire:Interface:Node'
                     and row.get('id') == self.source for row in objects)
        self._wait_last_graph = (True, bool(owned), bool(captures), source, linked)
        return linked

    def play(self, sample):
        self.audio = self.root / 'fixture.wav'
        shutil.copyfile(DATA / 'dictation-fixtures' / sample['wav'], self.audio)
        os.chmod(self.audio, 0o600)
        os.chown(self.audio, self.account.pw_uid, self.account.pw_gid)
        require(sha(self.audio) == sample['wav_sha256'], 'playback-fixture-sha256')
        self.player = subprocess.Popen(self.prefix + ['/usr/bin/pw-play',
                       '--target=' + self.sink_name, str(self.audio)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       start_new_session=True)

    def select(self, language=None, backend=None):
        if language is not None:
            self.adapter('set-language', language)
        if backend is not None:
            require(backend in ('cpu', 'vulkan'), 'unknown-backend-selection')
            run(['/usr/bin/env', 'PKEXEC_UID=' + str(self.account.pw_uid),
                 str(SETUP), '--backend', backend], 750)
            self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
            self.observe('daemon-restart', lambda: self.state(allow_absent=True) == 'idle', 20)

    def transcribe(self, sample, purpose='cpu-session'):
        self.empty()
        require(self.focused(), 'receiver-focus-lost')
        self.select(language=sample['language'])
        before = time.monotonic_ns()
        self.record('start')
        self.observe('recording-state', lambda: self.state() == 'recording', 10)
        _pid, _ticks, binary = self.engine()
        cpu_key = 'avx2' if self.profile_id == 'turbo-q5-v3' else 'cpu'
        require(binary == PAYLOAD / self.names[cpu_key]
                and sha(binary) == self.assets[cpu_key]['sha256'],
                'cpu-upstream-daemon-profile-pin')
        self.observe('capture-link', self.capture_link, 10)
        self.play(sample)
        require(self.player.wait(timeout=sample['audio_seconds'] + 20) == 0,
                'fixture-playback-failed')
        self.record('stop')
        self.observe('transcribing-state',
                     lambda: self.state() in ('transcribing', 'idle'), 10)
        self.observe('terminal-state', lambda: self.state() == 'idle', 240)
        elapsed = time.monotonic_ns() - before
        previous, stable = None, 0
        def received():
            nonlocal previous, stable
            value = (self.root / 'received.private').read_text()
            stable = stable + 1 if value and value == previous else 0
            previous = value
            return value if stable >= 3 else None
        hypothesis = self.observe('text-delivery', received, 5)
        require(hypothesis and '\n' not in hypothesis, 'empty-or-unintended-enter')
        require(self.focused(), 'insertion-focus-lost')
        if sample['language'] == 'he':
            require(any('\u05d0' <= char <= '\u05ea' for char in hypothesis),
                    'hebrew-script-not-inserted')
        self.phrases.append(hypothesis)
        metric = self.accuracy.metrics(
            (DATA / 'dictation-fixtures' / sample['reference']).read_text(), hypothesis)
        item = {'language': sample['language'], 'source_row': sample['source_row'],
                'purpose': purpose, 'wav_sha256': sample['wav_sha256'],
                'reference_sha256': sample['reference_sha256'],
                'hypothesis_sha256': hashlib.sha256(hypothesis.encode()).hexdigest(),
                'elapsed_ns': elapsed, 'audio_frames': sample['audio_frames'],
                'sample_rate': 16000, 'reference_words': metric['reference_words'],
                'word_edits': metric['word_edits'],
                'reference_chars': metric['reference_characters'],
                'char_edits': metric['character_edits'], 'backend': 'cpu',
                'cpu_variant': self.profile['cpu_variant'],
                'binary_sha256': self.assets[cpu_key]['sha256'],
                'model_sha256': self.assets['model']['sha256']}
        self.report['samples'].append(item)
        return item

    def samples(self, language):
        rows = [sample for sample in self.fixtures if sample['language'] == language]
        require([sample['source_row'] for sample in rows] == list(range(5)),
                'fixture-language-rows')
        for sample in rows:
            self.transcribe(sample)
        return {'count': 5}

    def cancel(self):
        self.empty()
        self.select(language='en', backend='cpu')
        self.record('start')
        self.observe('recording-state', lambda: self.state() == 'recording', 10)
        self.observe('capture-link', self.capture_link, 10)
        self.play(self.fixtures[0])
        time.sleep(.5)
        self.record('cancel')
        self.kill(self.player)
        self.player = None
        self.observe('cancel-idle', lambda: self.state() == 'idle', 20)
        time.sleep(.5)
        require((self.root / 'received.private').read_bytes() == b'',
                'cancel-inserted-text')
        return {'count': 0, 'drained': True}

    def missing(self):
        self.record('cancel', check=False)
        self.select(backend='cpu')
        target = MODELS / self.names['model']
        hidden = target.with_name(target.name + '.qualification-' + os.urandom(8).hex())
        target.rename(hidden)
        try:
            self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
            self.record('start', check=False)
            if self.state(allow_absent=True) == 'recording':
                self.play(self.fixtures[0])
                self.player.wait(timeout=self.fixtures[0]['audio_seconds'] + 20)
                self.record('stop', check=False)
            self.observe('missing-model-idle',
                         lambda: self.state(allow_absent=True) == 'idle', 30)
            status = self.adapter('status')
            require(status.get('ready') is False and bool(status.get('error')),
                    'missing-model-not-actionable')
            require((self.root / 'received.private').read_bytes() == b'',
                    'missing-model-inserted-text')
            self.record('cancel', check=False)
        finally:
            self.kill(self.player)
            self.player = None
            hidden.rename(target)
            self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
            self.observe('model-restored', lambda: self.state(allow_absent=True) == 'idle', 20)
        require(sha(target) == self.assets['model']['sha256'],
                'missing-model-restore-integrity')
        return {'ready': False, 'restored': True}

    def microphone(self):
        self.empty()
        self.select(backend='cpu')
        self.record('start')
        self.observe('recording-state', lambda: self.state() == 'recording', 10)
        self.observe('capture-link', self.capture_link, 10)
        self.destroy_route(restore=False)
        try:
            objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
            remaining = [row for row in objects if row.get('type') == 'PipeWire:Interface:Node'
                         and row.get('info', {}).get('props', {}).get('media.class', '').startswith('Audio/Source')]
            if remaining:
                raise MicrophoneIsolationUnavailable()
            self.record('stop', check=False)
            self.observe('microphone-idle', lambda: self.state() == 'idle', 30)
            require((self.root / 'received.private').read_bytes() == b'',
                    'microphone-failure-inserted-text')
            status = self.adapter('status')
            error = str(status.get('error', '')).lower()
            require(status.get('state') == 'error'
                    and any(word in error for word in ('microphone', 'audio', 'input device')),
                    'microphone-failure-not-actionable')
        finally:
            self.record('cancel', check=False)
            self.route()
        return {'count': 0, 'drained': True, 'restored': True}

    def locked(self):
        self.empty()
        self.select(backend='cpu')
        self.record('start')
        self.observe('recording-state', lambda: self.state() == 'recording', 10)
        self.observe('capture-link', self.capture_link, 10)
        self.play(self.fixtures[0])
        time.sleep(.3)
        self.cmd(['/usr/bin/arctic-shell-ipc', 'lock', 'lock'])
        self.observe('lock-state', lambda: self.cmd(
            ['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'true')
        self.kill(self.player)
        self.player = None
        def stopped():
            service = self.cmd(['systemctl', '--user', 'is-active', 'voxtype.service'],
                               check=False)
            return (service.stdout.strip() == b'inactive' and not self.engines()
                    and self.state(allow_absent=True) == 'stopped')
        self.observe('lock-daemon-stopped', stopped, 10)
        require((self.root / 'received.private').read_bytes() == b'',
                'lock-inserted-text')
        print('ARCTIC-DESKTOP-UNLOCK-REQUESTED', flush=True)
        self.observe('unlock-state', lambda: self.cmd(
            ['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'false', 90)
        def restarted():
            service = self.cmd(['systemctl', '--user', 'is-active', 'voxtype.service'],
                               check=False)
            return (service.stdout.strip() == b'active'
                    and self.state(allow_absent=True) == 'idle'
                    and len(self.engines()) == 1)
        self.observe('unlock-daemon-restarted', restarted, 20)
        return {'locked': True, 'count': 0, 'drained': True}

    def gpu_failure(self):
        require(self.profile_id == 'turbo-q5-v3', 'gpu-gate-requires-modern-profile')
        self.empty()
        icd = self.root / 'bad-icd.json'
        missing = self.root / 'libarctic-missing-vulkan-driver.so'
        icd.write_text(json.dumps({'file_format_version': '1.0.0',
            'ICD': {'library_path': str(missing), 'api_version': '1.3.0'}},
            sort_keys=True) + '\n')
        os.chmod(icd, 0o600)
        os.chown(icd, self.account.pw_uid, self.account.pw_gid)
        # The root helper exposes only this fixed setup operation; the test CD
        # supplies no binary, key, checksum or cache.
        run(['/usr/bin/env', 'PKEXEC_UID=' + str(self.account.pw_uid),
             str(SETUP), '--backend', 'vulkan'], 750)
        vulkan = PAYLOAD / ASSETS['vulkan']['name']
        owned_file(vulkan, ASSETS['vulkan']['bytes'])
        require(sha(vulkan) == ASSETS['vulkan']['sha256'],
                'installed-vulkan-payload-sha256')
        self.cmd(['systemctl', '--user', 'set-environment',
                  'VK_DRIVER_FILES=' + str(icd), 'VK_LOADER_DEBUG=error'])
        self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
        self.observe('vulkan-daemon', lambda: bool(self.engines()), 20)
        try:
            self.record('start', check=False)
            if self.state(allow_absent=True) == 'recording':
                self.observe('gpu-capture-link', self.capture_link, 10)
                sample = next(row for row in self.fixtures
                              if row['language'] == 'en' and row['source_row'] == 0)
                self.play(sample)
                require(self.player.wait(timeout=sample['audio_seconds'] + 20) == 0,
                        'gpu-failure-playback-failed')
                self.player = None
                self.record('stop', check=False)
            self.observe('gpu-failure-idle', lambda: self.state(allow_absent=True) == 'idle', 60)
            require((self.root / 'received.private').read_bytes() == b'',
                    'gpu-failure-inserted-text')
            status = self.adapter('status')
            error = str(status.get('error', '')).lower()
            require(status.get('state') == 'error'
                    and ('vulkan' in error or 'gpu' in error),
                    'gpu-failure-not-actionable')
        finally:
            self.record('cancel', check=False)
            self.cmd(['systemctl', '--user', 'unset-environment',
                      'VK_DRIVER_FILES', 'VK_LOADER_DEBUG'])
        self.select(backend='cpu')
        for language in ('en', 'he'):
            sample = next(row for row in self.fixtures
                          if row['language'] == language and row['source_row'] == 0)
            self.transcribe(sample, 'cpu-retry')
        return {'gpu_supported': True, 'explicit_cpu_selected': True,
                'failed_attempt_inserted': False, 'count': 2,
                'bytes': ASSETS['vulkan']['bytes'],
                'sha256': ASSETS['vulkan']['sha256']}

    def legacy_gpu(self):
        require(self.profile_id == 'small-v2' and 'vulkan' not in self.assets,
                'legacy-gpu-profile-pin')
        require(not (PAYLOAD / ASSETS['vulkan']['name']).exists(),
                'legacy-vulkan-payload-unexpected')
        self.select(backend='cpu')
        for language in ('en', 'he'):
            sample = next(row for row in self.fixtures
                          if row['language'] == language and row['source_row'] == 0)
            self.transcribe(sample, 'cpu-retry')
        return {'gpu_supported': False, 'explicit_cpu_selected': True, 'count': 2}

    def published(self):
        self.empty()
        self.select(backend='cpu')
        self.record('start')
        self.observe('recording-state', lambda: self.state() == 'recording', 10)
        screenshot = self.root / 'recording-indicator.png'
        self.cmd(['/usr/bin/grim', str(screenshot)])
        require(screenshot.is_file() and screenshot.stat().st_size > 1000,
                'indicator-screenshot-missing')
        require((self.root / 'received.private').read_bytes() == b'',
                'indicator-receiver-not-empty')
        nonce = os.urandom(16).hex()
        print('ARCTIC-DICTATION-RECORDING-INDICATOR-REQUESTED ' + json.dumps({
            'boot_id': self.report['boot_id'],
            'installation_id': self.context['installation_id'],
            'phase': self.context['phase'], 'desktop_uid': self.account.pw_uid,
            'receiver_empty': True, 'capture_nonce': nonce}), flush=True)
        wait(lambda: (self.root / 'received.private').read_text() == nonce, 45)
        self.empty()
        require(self.state() == 'recording', 'indicator-recording-ended')
        proof = {'snapshot_sha256': sha(screenshot), 'ready': True,
                 'sha256': hashlib.sha256(nonce.encode()).hexdigest()}
        self.record('cancel')
        self.observe('indicator-cancel-idle', lambda: self.state() == 'idle', 10)
        return proof

    def transcript_files(self):
        runtime = self.runtime / 'voxtype'
        if not runtime.exists():
            return []
        return [path for path in runtime.iterdir()
                if path.name.startswith(('transcript', '.transcript'))
                or path.name.endswith(('.done', '.tmp'))]

    def cleanup_check(self):
        self.record('cancel', check=False)
        self.observe('cleanup-idle', lambda: self.state(allow_absent=True) in ('idle', 'stopped'), 10)
        require(not self.transcript_files(), 'private-transcript-files-remain')
        return {'file_count': 0, 'drained': True}

    def leakage(self):
        require(len(self.phrases) >= 12, 'leak-scan-missing-real-hypotheses')
        rows = run(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor,
                    '-o', 'json', '--output-fields=MESSAGE', '--all'],
                   60, output_role='interval-journal').stdout
        journal = journal_messages(rows)
        notices = self.cmd(['/usr/bin/arctic-shell-ipc', 'notifications', 'history']).stdout.decode()
        status = self.adapter('status')
        material = self.accuracy.normalize('\n'.join(
            [journal, notices, json.dumps(status, sort_keys=True), *self.snapshots]))
        for phrase in self.phrases:
            normalized = self.accuracy.normalize(phrase)
            require(len(normalized) >= 12, 'leak-scan-excerpt-too-short')
            fragments = {normalized[index:index + 12]
                         for index in range(len(normalized) - 11)}
            require(not any(fragment in material for fragment in fragments),
                    'transcript-found-in-public-surface')
        return {'count': len(self.phrases), 'matched': 0}

    def pending(self):
        def settled():
            value = self.adapter('status')
            require(value.get('ready') is False, 'offline-became-ready')
            state = (SYSTEM / 'setup.state').read_text().strip() if (SYSTEM / 'setup.state').exists() else ''
            return value if state in ('queued', 'failed') else None
        value = wait(settled, 660)
        require((SYSTEM / 'pending').is_file() and not (SYSTEM / 'verified.json').exists(),
                'offline-queue-missing-or-false-ready')
        require(value.get('download_bytes') == self.profile['download_bytes'],
                'offline-size-undisclosed')
        forbidden = {asset['name'] for asset in ASSETS.values()}
        require(not any((PAYLOAD / name).exists() or (MODELS / name).exists()
                        for name in forbidden), 'offline-payload-unexpected')
        require(run(['systemctl', 'is-enabled', 'arctic-dictation-setup.timer']).stdout.strip() == b'enabled',
                'offline-firstboot-timer-not-enabled')
        result = self.record('start', check=False)
        require(result.returncode != 0, 'offline-recording-not-blocked')
        return {'ready': False, 'pending': True}

    def os_healthy(self):
        self.offline()
        require(self.cmd(['mmsg', 'get', 'all-clients']).returncode == 0,
                'offline-desktop-not-responsive')
        require(run(['systemctl', 'is-active', 'NetworkManager']).stdout.strip() == b'active',
                'offline-network-manager-inactive')
        return {'ready': True}

    def recovery(self):
        require(run(['systemctl', 'is-enabled', 'arctic-dictation-setup.timer']).stdout.strip() == b'enabled',
                'recovery-timer-not-enabled')
        automatic = self.adapter('status').get('ready') is True and not (SYSTEM / 'pending').exists()
        require(automatic or (SYSTEM / 'pending').is_file(),
                'recovery-neither-pending-nor-ready')
        if not automatic:
            run(['systemctl', 'start', 'arctic-dictation-setup.service'], 750)
        value = wait(lambda: (row if (row := self.adapter('status')).get('ready') is True
                              and not (SYSTEM / 'pending').exists() else None), 750)
        require(value.get('ready') is True, 'recovery-not-ready')
        return {'ready': True, 'pending': False, 'automatic_ready': automatic}

    def absence(self):
        forbidden = {asset['name'] for asset in ASSETS.values()}
        require(not any((PAYLOAD / name).exists() or (MODELS / name).exists()
                        for name in forbidden)
                and not (SYSTEM / 'verified.json').exists()
                and not (SYSTEM / 'upstream-direct-v1').exists(),
                'live-payload-receipt-present')
        require(Path('/run/rootfsbase').is_dir(), 'live-base-unavailable')
        forbidden = {asset['name'] for asset in ASSETS.values()}
        def failed(_error):
            raise Invalid('live-base-scan-unreadable')
        for _base, _directories, names in os.walk('/run/rootfsbase', followlinks=False,
                                                   onerror=failed):
            require(not forbidden.intersection(names),
                    'live-speech-payload-or-model-present')
            require(not any(name.startswith('ggml-') and name.endswith('.bin') for name in names),
                    'live-whisper-weight-present')
        return {'file_count': 0}

    def unavailable(self):
        value = self.adapter('status')
        require(value.get('ready') is False, 'live-false-readiness')
        result = self.cmd([str(VOXTYPE), '--version'], check=False)
        require(result.returncode != 0, 'live-voxtype-selector-usable')
        return {'ready': False}

    def security(self):
        require(run(['getenforce']).stdout.strip() == b'Enforcing',
                'selinux-not-enforcing')
        return {'ready': True}

    @staticmethod
    def audit_state():
        text = run(['auditctl', '-s']).stdout.decode()
        values = {key: int(value) for key, value in
                  re.findall(r'^(enabled|lost)\s+(\d+)$', text, re.M)}
        require(set(values) == {'enabled', 'lost'}, 'audit-status-unavailable')
        return values

    def avcs(self):
        rows = run(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor,
                    '-o', 'json', '--output-fields=MESSAGE', '--all'],
                   60, output_role='interval-journal').stdout
        journal = journal_messages(rows)
        after = self.audit_state()
        require(after['enabled'] == self.audit_before['enabled']
                and after['enabled'] in (1, 2)
                and after['lost'] == self.audit_before['lost'],
                'audit-disabled-or-lost-records')
        if self.audit_offset:
            info = self.audit_file.stat()
            dev, ino, offset = self.audit_offset
            require((info.st_dev, info.st_ino) == (dev, ino)
                    and offset <= info.st_size
                    and info.st_size - offset <= 8 * 1024 * 1024,
                    'audit-interval-rotated-or-oversized')
            with self.audit_file.open('rb') as stream:
                stream.seek(offset)
                journal += '\n' + stream.read().decode(errors='replace')
        require(not re.search(r'(?i)\bavc:\s*denied|type=(?:USER_)?AVC', journal),
                'new-selinux-avc')
        return {'avcs': 0, 'audit_lost': after['lost'],
                'audit_enabled': after['enabled'],
                'audit_lost_before': self.audit_before['lost'],
                'audit_enabled_before': self.audit_before['enabled']}

    def session(self):
        spec = importlib.util.spec_from_file_location(
            'arctic_accuracy', DATA / 'dictation-accuracy/accuracy.py')
        self.accuracy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.accuracy)
        try:
            self.fixtures = self.accuracy.load_fixtures(
                DATA / 'dictation-fixtures', self.context['fixture_manifest_sha256'])
        except self.accuracy.Invalid:
            raise Invalid('fixture-bundle-validation-failed') from None
        self.record('cancel', check=False)
        self.select(backend='cpu')
        self.route()
        self.window_start()
        require(self.gate('local-offline-transcription', self.offline),
                'session-network-not-isolated')
        require(self.gate('upstream-command-contract', self.command_contract),
                'upstream-command-contract-failed')
        require(self.gate('upstream-state-contract', self.state_contract),
                'upstream-state-contract-failed')
        require(self.gate('local-he-en-config', self.config_contract),
                'local-config-contract-failed')
        require(self.gate('no-broad-input-access', self.no_input),
                'input-access-contract-failed')
        require(self.gate('recording-status-published', self.published),
                'indicator-handshake-incomplete')
        self.gate('cpu-english-transcription-insertion', lambda: self.samples('en'))
        self.gate('cpu-hebrew-transcription-insertion', lambda: self.samples('he'))
        self.gate('cancel-discards', self.cancel)
        self.gate('missing-model-error', self.missing)
        self.gate('microphone-disconnect-error', self.microphone)
        self.gate('lock-discards', self.locked)
        if self.profile_id == 'turbo-q5-v3':
            self.gate(MODERN_GPU_GATE, self.gpu_failure)
        else:
            self.gate(LEGACY_GPU_GATE, self.legacy_gpu)
        self.gate('transcript-private-cleanup', self.cleanup_check)
        self.gate('transcript-log-notification-leak-scan', self.leakage)

    def execute(self):
        phase = self.context['phase']
        self.gate('selinux-enforcing', self.security)
        if phase == 'live':
            self.gate('live-payload-model-absent', self.absence)
            self.gate('live-voxtype-unavailable', self.unavailable)
        else:
            self.gate('encrypted-installed-boot', self.encrypted)
            if phase == 'offline-installed':
                self.gate('offline-setup-pending', self.pending)
                self.gate('offline-os-healthy', self.os_healthy)
            elif phase == 'recovery':
                self.gate('explicit-service-recovery-ready', self.recovery)
                self.gate('installed-payload-integrity', self.payload)
            else:
                readiness = 'online-installer-ready' if phase == 'online-installed' else 'recovered-ready'
                available = self.gate(readiness, self.ready)
                integrity = self.gate('installed-payload-integrity', self.payload)
                if available and integrity:
                    self.session()
        self.gate('no-new-avcs', self.avcs)
        present = {gate['id'] for gate in self.report['gates']}
        for name in sorted(self.gates - present):
            self.report['gates'].append({'id': name, 'status': 'unrun',
                'evidence_kind': EXPECTED_KINDS[name],
                'code': 'prerequisite-or-collector-failed', 'observations': {}})
        self.report['status'] = ('passed' if all(gate['status'] == 'passed'
                                                 for gate in self.report['gates'])
                                 else 'failed')
        return self.report

    def close(self):
        errors = []
        try:
            self.record('cancel', check=False)
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
    mark_collector_setup('resource-limits')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    mark_collector_setup('arguments')
    if len(sys.argv) == 4 and sys.argv[1] == '_receiver':
        receiver(sys.argv[2], sys.argv[3]); return 0
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=('live', 'installed'))
    parser.add_argument('--disposable-guest', action='store_true')
    args = parser.parse_args()
    mark_collector_setup('environment')
    require(args.disposable_guest and os.geteuid() == 0, 'explicit-root-disposable-guest-required')
    require(HERE == DATA / 'dictation-qualification', 'reviewed-test-cd-location-required')
    require(run(['systemd-detect-virt']).stdout.strip() in (b'qemu', b'kvm'), 'qemu-kvm-guest-required')
    live = 'rd.live.image' in Path('/proc/cmdline').read_text().split()
    require(live == (args.stage == 'live'), 'actual-boot-stage-mismatch')
    mark_collector_setup('context')
    declared = context(read(DATA / 'dictation-context.json'))
    if live:
        declared = dict(declared, phase='live')
    require((declared['phase'] == 'live') == live, 'context-boot-stage-mismatch')
    mark_collector_setup('source-integrity')
    for path, key in ((HERE / 'guest_check.py', 'checker_sha256'),
                      (HERE / 'contract.py', 'contract_sha256'),
                      (DATA / 'dictation-accuracy/accuracy.py', 'accuracy_sha256'),
                      (DATA / 'dictation-accuracy/pins.json', 'pins_sha256')):
        require(sha(path) == declared[key], 'reviewed-source-hash-mismatch')
    require(installed_integration_sha() == declared['integration_sha256'],
            'installed-integration-hash-mismatch')
    checker = Checker(declared)
    report = checker.report
    mark_collector_setup('execution')
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
    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
        try:
            code = collector_diagnostic_code(COLLECTOR_SETUP_STAGE, error)
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):
            code = 'collector-unknown'
        print('ARCTIC-DICTATION-COLLECTOR-ERROR ' + json.dumps(
            {'code': code, 'release_acceptance': False}, sort_keys=True), flush=True)
        sys.exit(1)
