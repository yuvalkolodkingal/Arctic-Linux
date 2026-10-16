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

from contract import (ASSETS, ERROR_LABELS, EXPECTED_KINDS, FAILURE_SUBSTAGES, GPU_FAILURE_STAGES, LEGACY_GPU_GATE, LIMITATIONS, MICROPHONE_FAILURE_STAGES, MODERN_GPU_GATE, PROFILE_ASSETS, PROFILES, SCHEMA, TRANSCRIPTION_FAILURE_STAGES, UPSTREAM, VULKAN_ISOLATION_GATE, Invalid, context, gates, pinned, require, validate)

HERE = Path(__file__).resolve().parent
DATA = Path('/run/t')
VOXTYPE = Path('/usr/bin/voxtype')
ADAPTER = Path('/usr/bin/arctic-dictation')
TOGGLE = Path('/usr/bin/arctic-dictation-toggle')
SETUP = Path('/usr/libexec/arctic/arctic-voxtype-setup')
HOST_PROFILE = Path('/usr/libexec/arctic/arctic-voxtype-host-profile')
CONFIGURE = Path('/usr/libexec/arctic/arctic-voxtype-configure')
KEY = Path('/usr/share/arctic/dictation/voxtype-release-key.asc')
PROVENANCE_SUMS = Path('/usr/share/arctic/dictation/provenance/1.1.1/SHA256SUMS.txt')
PROVENANCE_SUMS_SIG = Path('/usr/share/arctic/dictation/provenance/1.1.1/SHA256SUMS.txt.asc')
PROVENANCE_BASELINE_SIG = Path('/usr/share/arctic/dictation/provenance/1.1.1/voxtype-1.1.1-linux-x86_64-baseline.asc')
PROVENANCE_AVX2_SIG = Path('/usr/share/arctic/dictation/provenance/1.1.1/voxtype-1.1.1-linux-x86_64-avx2.asc')
POLICY = Path('/usr/share/polkit-1/actions/org.arcticlinux.dictation.policy')
UNIT = Path('/usr/lib/systemd/user/voxtype.service')
SETUP_SERVICE = Path('/usr/lib/systemd/system/arctic-dictation-setup.service')
SETUP_TIMER = Path('/usr/lib/systemd/system/arctic-dictation-setup.timer')
SKEL_BINDINGS = Path('/etc/skel/.config/mango/arctic/binds.conf')
PACKAGED_BINDINGS = Path('/usr/share/arctic/mango/binds.conf')
PAYLOAD = Path('/opt/arctic/voxtype/1.1.1')
MODELS = Path('/opt/arctic/voxtype/models')
SYSTEM = Path('/var/lib/arctic/dictation')
VULKAN_CACHE = Path('/var/cache/arctic/voxtype/voxtype-1.1.1-linux-x86_64-vulkan')
VULKAN_RELEASE_NAME = 'voxtype-1.1.1-linux-x86_64-vulkan'
VULKAN_RELEASE_URL = ('https://github.com/peteonrails/voxtype/releases/download/v1.1.1/'
                      + VULKAN_RELEASE_NAME)
VULKAN_CACHE_SIG = VULKAN_CACHE.with_name(VULKAN_CACHE.name + '.asc')
SUMS_CACHE = VULKAN_CACHE.parent / 'SHA256SUMS.txt'
SUMS_CACHE_SIG = VULKAN_CACHE.parent / 'SHA256SUMS.txt.asc'
VULKAN_SIG_BYTES = 228
VULKAN_SIG_SHA256 = 'aaf15615b5f7f5d18e5df132fd6a1ade754991162108b1a3990b303dd1a9109b'
SUMS_BYTES = 2931
SUMS_SHA256 = 'a93de5d79f6180626181aaf2315cc8415b084914b9f69a71e71bfb56bae1a32e'
SUMS_SIG_BYTES = 228
SUMS_SIG_SHA256 = '2bce1ff42615d322b1e686f05373c99889d506e230d5f5512aeb22d728510af8'
RELEASE_FINGERPRINT = '9CCF7915B750CAE8B095ED1AA3FC9F33FD209279'
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


class TranscriptionStageFailure(Invalid):
    """Transcript-free projection of one fixed transcription operation."""

    def __init__(self, stage, label, substage=None):
        require(type(stage) is str and stage in TRANSCRIPTION_FAILURE_STAGES,
                'unknown-transcription-failure-stage')
        require(type(label) is str and label in ERROR_LABELS,
                'unknown-transcription-failure-family')
        super().__init__()
        self.failure_stage = TRANSCRIPTION_FAILURE_STAGES[stage]
        self.error_label = label
        require(substage is None or (type(substage) is int
                and substage in FAILURE_SUBSTAGES.get(self.failure_stage, ())),
                'unknown-transcription-failure-substage')
        self.failure_substage = substage


class MicrophoneStageFailure(Invalid):
    """Transcript-free projection of one fixed microphone operation."""

    def __init__(self, stage, label):
        require(type(stage) is str and stage in MICROPHONE_FAILURE_STAGES,
                'unknown-microphone-failure-stage')
        require(type(label) is str and label in ERROR_LABELS,
                'unknown-microphone-failure-family')
        super().__init__()
        self.failure_stage = MICROPHONE_FAILURE_STAGES[stage]
        self.error_label = label


class GpuStageFailure(Invalid):
    """Transcript-free projection of one fixed GPU recovery operation."""

    def __init__(self, stage, label, substage=None, returncode=None):
        require(type(stage) is str and stage in GPU_FAILURE_STAGES,
                'unknown-gpu-failure-stage')
        require(type(label) is str and label in ERROR_LABELS,
                'unknown-gpu-failure-family')
        super().__init__()
        self.failure_stage = GPU_FAILURE_STAGES[stage]
        self.error_label = label
        require(substage is None or (type(substage) is int
                and substage in FAILURE_SUBSTAGES.get(self.failure_stage, ())),
                'unknown-gpu-failure-substage')
        require(returncode is None or (type(returncode) is int
                and 1 <= returncode <= 255 and substage == 2022),
                'unknown-gpu-failure-returncode')
        self.failure_substage = substage
        self.failure_returncode = returncode

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
    # A complete same-boot VoxType MESSAGE projection can exceed the ordinary
    # command bound during CPU transcription. Keep it finite and private while
    # scanning the whole interval; every other command keeps the 16 MiB bound.
    limit = 32 * 1024 * 1024 if output_role == 'interval-journal' else 16 * 1024 * 1024
    require(len(result.stdout) + len(result.stderr) < limit, code)
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


def _owned_binding_link(path, link_uid, target, target_uid, code):
    """Read one binding through an exact, non-replaceable absolute link."""
    path, target = Path(path), Path(target)
    try:
        link = path.lstat()
        parent = path.parent.lstat()
        # Linux ignores symlink mode bits. Its parent controls replacement, so
        # require that directory to be owned by the link owner and closed to
        # group/other writes as well as checking the link's own UID.
        require(target.is_absolute()
                and stat.S_ISLNK(link.st_mode) and link.st_uid == link_uid
                and stat.S_ISDIR(parent.st_mode) and parent.st_uid == link_uid
                and not parent.st_mode & 0o022
                and os.readlink(path) == str(target), code)
        # Open the named package path itself with O_NOFOLLOW. This rejects a
        # missing, replaced or chained target even after the exact link text
        # has been checked above.
        return owned_text(target, target_uid, code)
    except OSError:
        raise Invalid(code) from None


def owned_binding_link(path, link_uid, code):
    """Read only Arctic's root-owned packaged Mango binding."""
    return _owned_binding_link(path, link_uid, PACKAGED_BINDINGS, 0, code)

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
        ('packaging/dictation/provenance/v1.1.1/SHA256SUMS.txt', PROVENANCE_SUMS),
        ('packaging/dictation/provenance/v1.1.1/SHA256SUMS.txt.asc', PROVENANCE_SUMS_SIG),
        ('packaging/dictation/provenance/v1.1.1/voxtype-1.1.1-linux-x86_64-baseline.asc', PROVENANCE_BASELINE_SIG),
        ('packaging/dictation/provenance/v1.1.1/voxtype-1.1.1-linux-x86_64-avx2.asc', PROVENANCE_AVX2_SIG),
        ('packaging/dictation/org.arcticlinux.dictation.policy', POLICY),
        ('packaging/systemd/voxtype.service', UNIT),
        ('packaging/systemd/arctic-dictation-setup.service', SETUP_SERVICE),
        ('packaging/systemd/arctic-dictation-setup.timer', SETUP_TIMER),
    )
    result = hashlib.sha256()
    # Fedora's brp-mangle-shebangs rewrites these six executable source
    # shebangs while building the RPM.  Hash their exact source form so the
    # installed-byte identity can be compared with the reviewed source tree;
    # every other byte, and every non-executable integration file, remains
    # byte-for-byte bound.
    shebangs = {
        ADAPTER: (b'#!/usr/bin/sh\n', b'#!/bin/sh\n'),
        TOGGLE: (b'#!/usr/bin/sh\n', b'#!/bin/sh\n'),
        VOXTYPE: (b'#!/usr/bin/sh\n', b'#!/bin/sh\n'),
        SETUP: (b'#!/usr/bin/bash\n', b'#!/bin/bash\n'),
        HOST_PROFILE: (b'#!/usr/bin/sh\n', b'#!/bin/sh\n'),
        CONFIGURE: (b'#!/usr/bin/sh\n', b'#!/bin/sh\n'),
    }
    for name, path in files:
        owned_file(path)
        encoded = name.encode()
        content = path.read_bytes()
        if path in shebangs:
            installed, source = shebangs[path]
            require(content.startswith(installed), 'installed-integration-shebang-mismatch')
            content = source + content[len(installed):]
        result.update(len(encoded).to_bytes(4, 'big'))
        result.update(encoded)
        result.update(content)
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
        self.selected_language = None
        self.selected_backend = None
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
            observations = {}
            if type(error) in (TranscriptionStageFailure, MicrophoneStageFailure,
                               GpuStageFailure):
                label = error.error_label
                observations = {'failure_stage': error.failure_stage}
                if type(error) in (TranscriptionStageFailure, GpuStageFailure):
                    if error.failure_substage is not None:
                        observations['failure_substage'] = error.failure_substage
                if type(error) is GpuStageFailure and error.failure_returncode is not None:
                    observations['failure_returncode'] = error.failure_returncode
            result['code'] = GATE_FAILURE_CODES[name].get(label, 'gate-' + name + '-unknown')
            result['observations'] = observations
            if type(error) is MicrophoneIsolationUnavailable:
                result['code'] = 'gate-microphone-disconnect-error-isolation-unavailable'
                result['status'] = 'unrun'
        self.report['gates'].append(result)
        return result['status'] == 'passed'

    def dependent_unrun(self, name):
        """Record a dependent gate only after a concrete checked failure."""
        require(name in self.gates
                and not any(gate.get('id') == name for gate in self.report['gates']),
                'unknown-or-duplicate-dependent-gate')
        require(any(gate.get('status') == 'failed' for gate in self.report['gates']),
                'dependent-gate-without-concrete-failure')
        self.report['gates'].append({
            'id': name, 'status': 'unrun',
            'evidence_kind': EXPECTED_KINDS[name],
            'code': 'prerequisite-or-collector-failed', 'observations': {}})
        return False

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
                        'vulkan_download_bytes', 'upgrade_pending'}
                    and value.get('state') in {
                        'unavailable', 'queued', 'downloading', 'starting', 'ready',
                        'recording', 'transcribing', 'error'}
                    and type(value.get('ready')) is bool
                    and type(value.get('error')) is str
                    and len(value.get('error')) <= 512
                    and value.get('version') == '1.1.1'
                    and value.get('upgrade_pending') is False
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
        require(value.get('ready') is True and value.get('state') == 'ready'
                and value.get('profile') == self.profile_id
                and value.get('backend') in ('cpu', 'vulkan')
                and not (SYSTEM / 'pending').exists(), 'upstream-not-ready')
        marker = SYSTEM / 'upstream-direct-v1'
        owned_file(marker)
        require(marker.read_text() == 'upstream-direct-v1\n',
                'upstream-readiness-marker-invalid')
        service = self.cmd(['systemctl', '--user', 'is-active', 'voxtype.service'],
                           check=False)
        require(service.stdout.strip() != b'active' and not self.state_path.exists()
                and self.engines() == [], 'upstream-lazy-login-resident')
        session_marker = self.runtime / 'arctic-dictation/voxtype-session-started-v1'
        require(not session_marker.exists(), 'upstream-lazy-session-marker-present')

        # Establish the deterministic PipeWire route before exercising the same
        # first guarded activation that Mango exposes. This is the only start;
        # later gates reuse the resident official daemon.
        self.route()
        activation = self.cmd([str(TOGGLE)], timeout=75, check=False)
        require(activation.returncode == 0 and len(activation.stdout) <= 16384
                and len(activation.stderr) <= 16384,
                'upstream-first-activation-failed')
        self.observe('upstream-first-activation-recording',
                     lambda: self.state(allow_absent=True) == 'recording', 20)
        require(session_marker.is_dir() and not session_marker.is_symlink(),
                'upstream-lazy-session-marker-missing')
        self.record('cancel')
        self.daemon_ready('upstream-first-activation-resident', 60)
        engines = self.engines()
        require(len(engines) == 1, 'upstream-daemon-not-unique')
        status = (Path('/proc') / str(engines[0][0]) / 'status').read_text()
        rss = re.search(r'^VmRSS:\s+(\d+) kB$', status, re.M)
        require(rss is not None and int(rss.group(1)) > 0,
                'upstream-resident-rss-unavailable')
        return {'ready': True, 'pending': False,
                'pre_activation_engine_count': 0,
                'resident_rss_bytes': int(rss.group(1)) * 1024}

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
            binds = owned_binding_link(path, uid, 'mango-bindings-unsafe')
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
                and 'ConditionPathExists=%t/arctic-dictation/voxtype-session-started-v1' in unit
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
                and whisper.get('on_demand_loading') is False
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

    @staticmethod
    def exact_root_file(path, size, digest):
        try:
            info = Path(path).lstat()
            return (stat.S_ISREG(info.st_mode) and info.st_uid == 0
                    and not info.st_mode & 0o022 and info.st_size == size
                    and sha(path) == digest)
        except OSError:
            return False

    def prefetch_vulkan_cache(self):
        """Download and authenticate optional bytes without executing VoxType."""
        cache = VULKAN_CACHE.parent
        info = cache.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == 0
                and not info.st_mode & 0o022, 'vulkan-cache-directory-unsafe')
        require(self.exact_root_file(PROVENANCE_SUMS, SUMS_BYTES, SUMS_SHA256)
                and self.exact_root_file(PROVENANCE_SUMS_SIG, SUMS_SIG_BYTES,
                                         SUMS_SIG_SHA256),
                'vulkan-packaged-provenance-invalid')
        try:
            sums = PROVENANCE_SUMS.read_text(encoding='ascii').splitlines()
        except (OSError, UnicodeError):
            raise Invalid('vulkan-packaged-provenance-invalid') from None
        require(sums.count(ASSETS['vulkan']['sha256'] + '  ' + VULKAN_RELEASE_NAME) == 1,
                'vulkan-packaged-provenance-invalid')

        temporary = Path(tempfile.mkdtemp(prefix='.qualification-vulkan-', dir=cache))
        try:
            keyring = temporary / 'release-key.gpg'
            shown = run(['gpg', '--batch', '--show-keys', '--with-colons', str(KEY)])
            try:
                fingerprints = [row.split(':')[9] for row in
                                shown.stdout.decode('ascii').splitlines()
                                if row.startswith('fpr:') and len(row.split(':')) > 9]
            except UnicodeError:
                raise Invalid('vulkan-release-key-invalid') from None
            require(fingerprints and fingerprints[0] == RELEASE_FINGERPRINT,
                    'vulkan-release-key-invalid')
            run(['gpg', '--batch', '--yes', '--dearmor', '--output', str(keyring),
                 str(KEY)])

            binary = temporary / VULKAN_RELEASE_NAME
            signature = temporary / (VULKAN_RELEASE_NAME + '.asc')
            if (self.exact_root_file(VULKAN_CACHE, ASSETS['vulkan']['bytes'],
                                     ASSETS['vulkan']['sha256'])
                    and self.exact_root_file(VULKAN_CACHE_SIG, VULKAN_SIG_BYTES,
                                             VULKAN_SIG_SHA256)):
                shutil.copyfile(VULKAN_CACHE, binary)
                shutil.copyfile(VULKAN_CACHE_SIG, signature)
            else:
                for url, target in ((VULKAN_RELEASE_URL, binary),
                                    (VULKAN_RELEASE_URL + '.asc', signature)):
                    run(['curl', '--noproxy', '*', '--fail', '--location',
                         '--silent', '--show-error',
                         '--retry', '3', '--retry-delay', '2', '--connect-timeout', '20',
                         '--speed-limit', '1024', '--speed-time', '60',
                         '--output', str(target), url], 750)
            require(binary.stat().st_size == ASSETS['vulkan']['bytes']
                    and sha(binary) == ASSETS['vulkan']['sha256']
                    and signature.stat().st_size == VULKAN_SIG_BYTES
                    and sha(signature) == VULKAN_SIG_SHA256,
                    'vulkan-prefetch-integrity')

            def signed(sig, payload):
                result = run(['gpgv', '--status-fd', '1', '--keyring', str(keyring),
                              str(sig), str(payload)])
                try:
                    valid = [line.split()[2] for line in result.stdout.decode('ascii').splitlines()
                             if line.startswith('[GNUPG:] VALIDSIG ') and len(line.split()) > 2]
                except UnicodeError:
                    raise Invalid('vulkan-prefetch-signature') from None
                require(valid == [RELEASE_FINGERPRINT], 'vulkan-prefetch-signature')

            signed(PROVENANCE_SUMS_SIG, PROVENANCE_SUMS)
            signed(signature, binary)
            for source, target, size, digest in (
                    (PROVENANCE_SUMS, SUMS_CACHE, SUMS_BYTES, SUMS_SHA256),
                    (PROVENANCE_SUMS_SIG, SUMS_CACHE_SIG,
                     SUMS_SIG_BYTES, SUMS_SIG_SHA256),
                    (binary, VULKAN_CACHE, ASSETS['vulkan']['bytes'],
                     ASSETS['vulkan']['sha256']),
                    (signature, VULKAN_CACHE_SIG, VULKAN_SIG_BYTES,
                     VULKAN_SIG_SHA256)):
                staged = temporary / (target.name + '.publish')
                shutil.copyfile(source, staged)
                os.chmod(staged, 0o644)
                require(staged.stat().st_size == size and sha(staged) == digest,
                        'vulkan-prefetch-publish-integrity')
                os.replace(staged, target)
            require(all(self.exact_root_file(path, size, digest) for path, size, digest in (
                (SUMS_CACHE, SUMS_BYTES, SUMS_SHA256),
                (SUMS_CACHE_SIG, SUMS_SIG_BYTES, SUMS_SIG_SHA256),
                (VULKAN_CACHE, ASSETS['vulkan']['bytes'], ASSETS['vulkan']['sha256']),
                (VULKAN_CACHE_SIG, VULKAN_SIG_BYTES, VULKAN_SIG_SHA256),
            )), 'vulkan-prefetch-publish-integrity')
        finally:
            shutil.rmtree(temporary)

    def prepare_vulkan_offline_boundary(self):
        """Fetch and verify optional Vulkan, then remove outside reachability.

        This runs only in a disposable Turbo boot whose host network was
        explicitly enabled for the download.  It performs no recording or
        transcription.  The normal GPU gate later repeats the unsupported
        Vulkan attempt and both CPU recovery transcriptions while offline.
        """
        require(self.profile_id == 'turbo-q5-v3'
                and self.context['phase'] in ('online-installed', 'recovery'),
                'vulkan-boundary-scope')

        def isolate():
            network_off = run(['/usr/bin/nmcli', 'networking', 'off'],
                              20, check=False)
            require(network_off.returncode == 0,
                    'vulkan-boundary-network-disable')
            return self.offline()

        try:
            # The connected portion only downloads and authenticates bytes.
            # It never invokes VoxType, setup, recording or transcription.
            self.prefetch_vulkan_cache()
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                KeyError, TypeError):
            # A preparation failure remains the reported cause only after the
            # disposable guest proves isolation. A failed disconnect/proof is
            # more immediate and therefore fails here before the original is
            # re-raised. Neither path can reach setup below.
            isolate()
            raise
        except BaseException:
            # Preserve interrupts and other unexpected control flow, while
            # still making a best effort to isolate the disposable guest. Do
            # not let a second exception hide the original BaseException.
            try:
                isolate()
            except BaseException:
                pass
            raise
        isolated = isolate()
        # Only after the HTTP 000 proof may official setup run its local
        # Vulkan probe (including its silence.wav transcription) from cache.
        self.cmd(['systemctl', '--user', 'stop', 'voxtype.service'], check=False)
        failed = run(['/usr/bin/env', 'PKEXEC_UID=' + str(self.account.pw_uid),
                      str(SETUP), '--backend', 'vulkan'], 750, check=False)
        require(failed.returncode != 0,
                'vm-vulkan-fixture-unexpectedly-supported')
        require((SYSTEM / 'backend').read_text().strip() == 'cpu'
                and (SYSTEM / 'setup.error').read_text().strip() == 'backend-vulkan',
                'vulkan-boundary-cpu-not-preserved')
        self.checked_vulkan_payload()
        # Use the product's supported selector to clear the checked failure
        # while keeping the daemon stopped for readiness testing.
        run(['/usr/bin/env', 'PKEXEC_UID=' + str(self.account.pw_uid),
             str(SETUP), '--backend', 'cpu'], 750)
        require((SYSTEM / 'backend').read_text().strip() == 'cpu'
                and not (SYSTEM / 'setup.error').exists(),
                'vulkan-boundary-cpu-not-restored')
        require(not self.engines() and not self.state_path.exists(),
                'vulkan-boundary-resident-session')
        return {'gpu_supported': False, 'explicit_cpu_selected': True,
                'bytes': ASSETS['vulkan']['bytes'],
                'sha256': ASSETS['vulkan']['sha256'],
                'returncode': isolated['returncode']}

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
        self._capture_engine = None
        engines = self.engines()
        if len(engines) != 1:
            self._wait_last_graph = (False, False, False, False, False)
            return False
        pid = engines[0][0]
        objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
        owned, captures = authenticated_capture_nodes(objects, pid, self.account.pw_uid)
        unchanged = self.engines() == engines
        linked = any(row.get('type') == 'PipeWire:Interface:Link'
                     and row.get('info', {}).get('output-node-id') == self.source
                     and row.get('info', {}).get('input-node-id') in captures
                     for row in objects) if captures else False
        source = any(row.get('type') == 'PipeWire:Interface:Node'
                     and row.get('id') == self.source for row in objects)
        self._wait_last_graph = (unchanged, bool(owned), bool(captures), source, linked)
        accepted = unchanged and linked
        if accepted:
            self._capture_engine = engines[0]
        return accepted

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
        # A transcription gate retains only this closed progress marker if a
        # supported language change fails.  It never retains command output,
        # status text, paths, process IDs or transcript material.
        self._selection_checkpoint = 'entry'
        changed = False
        if backend is not None:
            require(backend in ('cpu', 'vulkan'), 'unknown-backend-selection')
            if backend == getattr(self, 'selected_backend', None):
                require((SYSTEM / 'backend').read_text().strip() == backend,
                        'selected-backend-state-changed')
        if backend is not None and backend != getattr(self, 'selected_backend', None):
            # Setup may regenerate the canonical multilingual config before a
            # later restart or readiness check fails. Invalidate first so a
            # following selection cannot trust a stale single-language cache.
            self.selected_language = None
            self.selected_backend = None
            run(['/usr/bin/env', 'PKEXEC_UID=' + str(self.account.pw_uid),
                 str(SETUP), '--backend', backend], 750)
            self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
            changed = True
        selected = None
        if language is not None and language != getattr(self, 'selected_language', None):
            # The adapter writes config before its restart/readiness boundary.
            # Invalidate before mutation for the same reason as backend setup.
            self.selected_language = None
            self._selection_checkpoint = 'language-adapter'
            self.adapter('set-language', language)
            self._selection_checkpoint = 'language-adapter-complete'
            selected = language
            changed = True
        if changed:
            # Retain only the authenticated process tuple returned by the
            # existing readiness boundary.  It lets a later failed start say
            # whether systemd replaced the daemon without reading or exposing
            # logs, command output, paths or transcript material.
            self._selection_checkpoint = 'daemon-readiness'
            self._ready_engine = self.daemon_ready('daemon-restart', 30)
            if backend is not None:
                self.selected_backend = backend
            if selected is not None:
                self.selected_language = selected
        self._selection_checkpoint = 'complete'

    def transcription_stage(self, stage, fn):
        """Run one fixed operation and retain only its numeric stage/family."""
        require(type(stage) is str and stage in TRANSCRIPTION_FAILURE_STAGES,
                'unknown-transcription-failure-stage')
        try:
            return fn()
        except TranscriptionStageFailure:
            raise
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
            raise TranscriptionStageFailure(stage, caught_error_label(error)) from None

    def microphone_stage(self, stage, fn):
        """Run one fixed microphone operation without retaining private output."""
        require(type(stage) is str and stage in MICROPHONE_FAILURE_STAGES,
                'unknown-microphone-failure-stage')
        try:
            return fn()
        except (MicrophoneIsolationUnavailable, MicrophoneStageFailure):
            raise
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
            raise MicrophoneStageFailure(stage, caught_error_label(error)) from None

    def gpu_stage(self, stage, fn):
        """Run one fixed GPU recovery operation without retaining private output."""
        require(type(stage) is str and stage in GPU_FAILURE_STAGES,
                'unknown-gpu-failure-stage')
        try:
            return fn()
        except (GpuStageFailure, TranscriptionStageFailure):
            raise
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError) as error:
            raise GpuStageFailure(stage, caught_error_label(error)) from None

    def daemon_ready(self, target, seconds=30):
        """Wait beyond a restart until one unchanged official daemon is usable."""
        previous, stable = None, 0
        def ready():
            nonlocal previous, stable
            service = self.cmd(['systemctl', '--user', 'is-active', 'voxtype.service'],
                               check=False)
            engines = self.engines()
            current = engines[0] if (service.stdout.strip() == b'active'
                                      and len(engines) == 1
                                      and self.state(allow_absent=True) == 'idle') else None
            stable = stable + 1 if current is not None and current == previous else 0
            previous = current
            return current if stable >= 3 else None
        return self.observe(target, ready, seconds)

    def daemon_idle(self, target, seconds=240):
        """Wait until the official daemon has finished its advertised idle transition.

        VoxType publishes ``idle`` before the result handler returns and, with
        on-demand loading, before it trims the just-unloaded model heap.  A
        following SIGUSR1 can therefore be pending while the state file already
        says idle.  Require the same official process to remain idle with no CPU
        progress for three observations.  This orders consecutive fixtures at
        the daemon's real event-loop boundary without restarting it, retrying a
        command, or extending the existing terminal-state deadline.
        """
        previous, stable = None, 0
        def idle():
            nonlocal previous, stable
            engines = self.engines()
            if len(engines) != 1 or self.state() != 'idle':
                previous, stable = None, 0
                return None
            pid, started, binary = engines[0]
            fields = (Path('/proc') / str(pid) / 'stat').read_text()
            fields = fields[fields.rfind(')') + 2:].split()
            require(len(fields) > 19 and int(fields[19]) == started,
                    'idle-daemon-identity-changed')
            current = (pid, started, binary, int(fields[11]) + int(fields[12]))
            stable = stable + 1 if current == previous else 0
            previous = current
            return engines[0] if stable >= 3 else None
        return self.observe(target, idle, seconds)

    def transcribe(self, sample, purpose='cpu-session'):
        self.transcription_stage('receiver-clear', self.empty)
        self.transcription_stage(
            'focus-before', lambda: require(self.focused(), 'receiver-focus-lost'))
        language = self.transcription_stage(
            'language-selection', lambda: self.checked_language_selection(sample))
        before = time.monotonic_ns()
        self.transcription_stage('record-start', lambda: self.record('start'))
        self.transcription_stage(
            'recording-state', self.checked_recording_state)
        self.transcription_stage(
            'capture-link', lambda: self.observe('capture-link', self.capture_link, 10))
        # The native state file can report recording before PipeWire has
        # published the restarted daemon's authenticated capture graph.  Use
        # that already-bounded observation as the synchronization boundary,
        # then pin the exact official process and binary.  A persistent
        # missing, duplicate, changed or unlinked daemon still fails the
        # capture-link stage; a wrong binary still fails engine-profile.
        cpu_key = self.transcription_stage('engine-profile', self.checked_engine_profile)
        self.transcription_stage('fixture-play-start', lambda: self.play(sample))
        self.transcription_stage('fixture-playback', lambda: require(
            self.player.wait(timeout=sample['audio_seconds'] + 20) == 0,
            'fixture-playback-failed'))
        self.transcription_stage('record-stop', lambda: self.record('stop'))
        self.transcription_stage(
            'transcribing-state', self.checked_transcribing_state)
        self.transcription_stage(
            'terminal-state', lambda: self.daemon_idle('terminal-state', 240))
        elapsed = time.monotonic_ns() - before
        previous, stable = None, 0
        def received():
            nonlocal previous, stable
            value = (self.root / 'received.private').read_text()
            stable = stable + 1 if value and value == previous else 0
            previous = value
            return value if stable >= 3 else None
        hypothesis = self.transcription_stage(
            'text-delivery', lambda: self.observe('text-delivery', received, 5))
        self.transcription_stage('text-shape', lambda: require(
            hypothesis and '\n' not in hypothesis, 'empty-or-unintended-enter'))
        self.transcription_stage(
            'focus-after', lambda: require(self.focused(), 'insertion-focus-lost'))
        if language == 'he':
            self.transcription_stage('language-script', lambda: require(
                any('\u05d0' <= char <= '\u05ea' for char in hypothesis),
                'hebrew-script-not-inserted'))
        metric = self.transcription_stage('accuracy-metrics', lambda: self.accuracy.metrics(
            (DATA / 'dictation-fixtures' / sample['reference']).read_text(), hypothesis))
        def record_sample():
            item = {'language': language, 'source_row': sample['source_row'],
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
            self.phrases.append(hypothesis)
            return item
        item = self.transcription_stage('sample-record', record_sample)
        return item

    def checked_language_selection(self, sample):
        """Select a fixture language and close only a failed restart diagnosis."""
        language = sample.get('language') if type(sample) is dict else None
        if language not in ('en', 'he'):
            raise TranscriptionStageFailure('language-selection', 'invalid', 401)
        try:
            self.select(language=language)
            return language
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                KeyError, TypeError) as error:
            label = caught_error_label(error)
            checkpoint = getattr(self, '_selection_checkpoint', None)
            if checkpoint == 'language-adapter':
                substage = 402
            else:
                try:
                    active = self.cmd(
                        ['systemctl', '--user', 'is-active', '--quiet',
                         'voxtype.service'], check=False)
                    if active.returncode != 0:
                        failed = self.cmd(
                            ['systemctl', '--user', 'is-failed', '--quiet',
                             'voxtype.service'], check=False)
                        substage = 403 if failed.returncode == 0 else 404
                    else:
                        engines = self.engines()
                        if len(engines) == 0:
                            substage = 405
                        elif len(engines) != 1:
                            substage = 406
                        elif engines[0] == getattr(self, '_ready_engine', None):
                            substage = 407
                        else:
                            state = self.state(allow_absent=True)
                            if state == 'stopped':
                                substage = 408
                            elif state == 'recording':
                                substage = 409
                            elif state == 'transcribing':
                                substage = 410
                            elif state == 'streaming':
                                substage = 411
                            elif state == 'idle':
                                status = self.adapter('status')
                                substage = 412 if status.get('language') == language else 413
                            else:
                                substage = 414
                except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                        KeyError, TypeError):
                    substage = 414
            raise TranscriptionStageFailure(
                'language-selection', label, substage) from None

    def checked_recording_state(self):
        """Keep the ten-second gate and close only its failure diagnosis.

        The official command returns after delivering SIGUSR1, before the
        daemon publishes its native state.  On a timeout, classify fixed
        service/process/state outcomes.  No command output, journal message,
        path, PID or transcript enters the report.
        """
        try:
            return self.observe(
                'recording-state', lambda: self.state() == 'recording', 10)
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                KeyError, TypeError) as error:
            label = caught_error_label(error)
            try:
                active = self.cmd(
                    ['systemctl', '--user', 'is-active', '--quiet',
                     'voxtype.service'], check=False)
                if active.returncode != 0:
                    failed = self.cmd(
                        ['systemctl', '--user', 'is-failed', '--quiet',
                         'voxtype.service'], check=False)
                    substage = 601 if failed.returncode == 0 else 602
                else:
                    engines = self.engines()
                    if len(engines) == 0:
                        substage = 603
                    elif len(engines) != 1:
                        substage = 604
                    elif engines[0] != getattr(self, '_ready_engine', None):
                        substage = 605
                    else:
                        state = self.state(allow_absent=True)
                        if state == 'stopped':
                            substage = 606
                        elif state == 'idle':
                            substage = (607 if (self.runtime / 'voxtype/start_requested').exists()
                                        else 608)
                        elif state == 'transcribing':
                            substage = 609
                        elif state == 'streaming':
                            substage = 610
                        elif state == 'recording':
                            substage = 611
                        else:
                            substage = 612
            except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                    KeyError, TypeError):
                substage = 612
            raise TranscriptionStageFailure(
                'recording-state', label, substage) from None

    def checked_transcribing_state(self):
        """Keep the ten-second post-stop gate and close only its diagnosis."""
        try:
            return self.observe(
                'transcribing-state', lambda: self.state() in ('transcribing', 'idle'), 10)
        except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                KeyError, TypeError) as error:
            label = caught_error_label(error)
            try:
                active = self.cmd(
                    ['systemctl', '--user', 'is-active', '--quiet',
                     'voxtype.service'], check=False)
                if active.returncode != 0:
                    failed = self.cmd(
                        ['systemctl', '--user', 'is-failed', '--quiet',
                         'voxtype.service'], check=False)
                    substage = 1201 if failed.returncode == 0 else 1202
                else:
                    engines = self.engines()
                    if len(engines) == 0:
                        substage = 1203
                    elif len(engines) != 1:
                        substage = 1204
                    elif engines[0] != getattr(self, '_capture_engine', None):
                        substage = 1205
                    else:
                        state = self.state(allow_absent=True)
                        substage = {
                            'stopped': 1206,
                            'recording': 1207,
                            'streaming': 1208,
                            'transcribing': 1209,
                            'idle': 1210,
                        }.get(state, 1211)
            except (Invalid, OSError, ValueError, subprocess.TimeoutExpired,
                    KeyError, TypeError):
                substage = 1212
            raise TranscriptionStageFailure(
                'transcribing-state', label, substage) from None

    def checked_engine_profile(self):
        """Pin the exact process already authenticated by capture_link()."""
        cpu_key = {'small-v2': 'cpu', 'turbo-q5-v3': 'avx2'}.get(self.profile_id)
        if (cpu_key is None or type(self.names.get(cpu_key)) is not str
                or type(self.assets.get(cpu_key)) is not dict):
            raise TranscriptionStageFailure('engine-profile', 'invalid', 701)
        engine = getattr(self, '_capture_engine', None)
        if (type(engine) is not tuple or len(engine) != 3
                or type(engine[0]) is not int or type(engine[1]) is not int
                or not isinstance(engine[2], Path)):
            raise TranscriptionStageFailure('engine-profile', 'invalid', 702)
        _pid, _ticks, binary = engine
        if binary != PAYLOAD / self.names[cpu_key]:
            raise TranscriptionStageFailure('engine-profile', 'invalid', 703)
        if sha(binary) != self.assets[cpu_key]['sha256']:
            raise TranscriptionStageFailure('engine-profile', 'invalid', 704)
        return cpu_key

    def checked_vulkan_payload(self):
        """Classify only fixed integrity states for the optional signed binary."""
        asset = ASSETS['vulkan']
        target = PAYLOAD / asset['name']

        def state(path):
            try:
                info = path.lstat()
            except FileNotFoundError:
                return 'absent'
            except OSError:
                return 'unreadable'
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                    or info.st_mode & 0o022):
                return 'unsafe'
            if info.st_size != asset['bytes']:
                return 'size'
            try:
                return 'exact' if sha(path) == asset['sha256'] else 'sha256'
            except OSError:
                return 'unreadable'

        target_state = state(target)
        if target_state == 'exact':
            return True
        if target_state == 'absent':
            cache_state = state(VULKAN_CACHE)
            substage = {'absent': 2031, 'exact': 2032}.get(cache_state, 2033)
            label = 'os-error'
        else:
            substage = {
                'unsafe': 2034, 'size': 2035, 'sha256': 2036,
                'unreadable': 2037,
            }[target_state]
            label = 'os-error' if target_state == 'unreadable' else 'invalid'
        raise GpuStageFailure('vulkan-payload-integrity', label, substage)

    def samples(self, language):
        def selected_rows():
            rows = [sample for sample in self.fixtures if sample['language'] == language]
            require([sample['source_row'] for sample in rows] == list(range(5)),
                    'fixture-language-rows')
            return rows
        rows = self.transcription_stage('fixture-selection', selected_rows)
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
            status = self.adapter('status')
            error = str(status.get('error', '')).lower()
            require(status.get('state') == 'error' and status.get('ready') is False
                    and any(word in error for word in ('model', 'whisper'))
                    and any(word in error for word in ('repair', 'retry')),
                    'missing-model-not-actionable')
            # Exercise the same guarded Mango activation path users receive.
            # Bypassing it with `voxtype record start` asks upstream to enter a
            # recording/transcribing transition after Arctic has already
            # rejected the missing model, and does not describe product use.
            activation = self.cmd([str(TOGGLE)], check=False)
            require(activation.returncode == 69, 'missing-model-activation-not-blocked')
            require((self.root / 'received.private').read_bytes() == b'',
                    'missing-model-inserted-text')
        finally:
            self.kill(self.player)
            self.player = None
            hidden.rename(target)
            self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
            self.daemon_ready('model-restored', 30)
        require(sha(target) == self.assets['model']['sha256'],
                'missing-model-restore-integrity')
        return {'ready': False, 'restored': True}

    def microphone(self):
        self.microphone_stage('receiver-clear', self.empty)
        self.microphone_stage('cpu-backend', lambda: self.select(backend='cpu'))
        def initial_status():
            initial = self.adapter('status')
            restore_language = initial.get('language')
            require(initial.get('ready') is True and restore_language in ('auto', 'he', 'en'),
                    'microphone-initial-state-invalid')
            return restore_language
        restore_language = self.microphone_stage('initial-status', initial_status)
        try:
            # VoxType accepts ALSA/CPAL device names, not PipeWire node names.
            # The fixture has already made its owned source the PipeWire
            # default, so exercise the same supported `default` route users
            # receive.  After that source disappears, a fresh official daemon
            # open deterministically observes that no input device remains.
            # All mutations are inside this cleanup boundary: a failed start
            # or link assertion must not poison the following lock/GPU gates.
            self.microphone_stage('source-selection', lambda: self.cmd(
                [str(VOXTYPE), 'config', 'set', 'audio.device', 'default']))
            self.microphone_stage('pinned-daemon-restart', lambda: self.cmd(
                ['systemctl', '--user', 'restart', 'voxtype.service']))
            self.microphone_stage('pinned-daemon-ready', lambda: self.daemon_ready(
                'microphone-pinned-daemon', 30))
            self.microphone_stage('record-start', lambda: self.record('start'))
            self.microphone_stage('recording-state', lambda: self.observe(
                'recording-state', lambda: self.state() == 'recording', 10))
            self.microphone_stage('capture-link', lambda: self.observe(
                'capture-link', self.capture_link, 10))
            self.microphone_stage('route-destroy', lambda: self.destroy_route(restore=False))
            def isolated():
                objects = json.loads(self.cmd(['/usr/bin/pw-dump']).stdout)
                remaining = [
                    row for row in objects
                    if row.get('type') == 'PipeWire:Interface:Node'
                    and row.get('info', {}).get('props', {}).get(
                        'media.class', '').startswith('Audio/Source')]
                if remaining:
                    raise MicrophoneIsolationUnavailable()
            self.microphone_stage('source-isolation', isolated)
            # Discard the interrupted session, then select a unique absent
            # ALSA/CPAL device name through VoxType's supported configuration
            # interface.  A removed PipeWire source does not guarantee that
            # ALSA's synthetic `default` device disappears, so relying on that
            # alias can start a null/default stream instead of exercising the
            # actionable open failure.  The owned source is still removed and
            # isolated above; the impossible name makes the subsequent open
            # failure deterministic.
            self.microphone_stage(
                'interrupted-cancel', lambda: self.record('cancel', check=False))
            missing_device = 'ArcticQualificationMissingInput-' + os.urandom(16).hex()
            def restart_disconnected():
                self.cmd([str(VOXTYPE), 'config', 'set', 'audio.device', missing_device])
                return self.cmd(['systemctl', '--user', 'restart', 'voxtype.service'])
            self.microphone_stage('disconnected-daemon-restart', restart_disconnected)
            self.microphone_stage('disconnected-daemon-ready', lambda: self.daemon_ready(
                'microphone-disconnected-daemon', 30))
            self.microphone_stage(
                'failed-record-start', lambda: self.record('start', check=False))
            def actionable():
                status = self.adapter('status')
                error = str(status.get('error', '')).lower()
                return status if (status.get('state') == 'error'
                    and any(word in error for word in ('microphone', 'audio', 'input device'))) else None
            # Wait for the fresh actionable projection itself. Sampling the
            # pre-signal idle state first can succeed before VoxType processes
            # record start, leaving an earlier fixture's error to contaminate
            # this gate.
            self.microphone_stage('actionable-error', lambda: self.observe(
                'microphone-actionable-error', actionable, 30))
            self.microphone_stage('idle-state', lambda: self.observe(
                'microphone-idle', lambda: self.state() == 'idle', 10))
            self.microphone_stage('receiver-empty', lambda: require(
                (self.root / 'received.private').read_bytes() == b'',
                'microphone-failure-inserted-text'))
        finally:
            cleanup_failures = []
            def cleanup(stage, operation):
                try:
                    self.microphone_stage(stage, operation)
                except MicrophoneStageFailure as error:
                    cleanup_failures.append(error)
            cleanup('cleanup-cancel', lambda: self.record('cancel', check=False))
            if self.loop is None:
                cleanup('route-restore', self.route)
            cleanup('default-source-restore', lambda: self.cmd(
                [str(VOXTYPE), 'config', 'set', 'audio.device', 'default']))
            # Removing a PipeWire source is intentionally destructive. A
            # daemon which still owns that dead CPAL stream must not influence
            # the independent lock, GPU and privacy gates which follow. Use
            # Arctic's supported settings operation to restart the daemon and
            # clear the already-observed error, rather than mutating its
            # private runtime projection from the qualification client.
            # The failed daemon owns an audio error even when its configured
            # language is unchanged.  Invalidate the qualification cache so
            # the supported language selection performs its documented
            # restart/readiness boundary and clears that error before the
            # independent lock and backend gates run.
            self.selected_language = None
            cleanup('language-restore', lambda: self.select(language=restore_language))
            error_path = self.runtime / 'arctic-dictation/voxtype-error'
            cleanup('error-clear', lambda: require(
                not error_path.exists() and not error_path.is_symlink(),
                'microphone-error-not-cleared'))
            if cleanup_failures:
                raise cleanup_failures[0]
        return {'count': 0, 'drained': True, 'restored': True}

    def locked(self):
        self.empty()
        self.select(backend='cpu')
        lock_command = False
        locked = False
        unlocked = False
        unlock_requested = False
        try:
            self.record('start')
            self.observe('recording-state', lambda: self.state() == 'recording', 10)
            self.observe('capture-link', self.capture_link, 10)
            self.play(self.fixtures[0])
            time.sleep(.3)
            self.cmd(['/usr/bin/arctic-shell-ipc', 'lock', 'lock'])
            lock_command = True
            self.observe('lock-state', lambda: self.cmd(
                ['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'true')
            locked = True
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
            unlock_requested = True
            self.observe('unlock-state', lambda: self.cmd(
                ['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'false', 90)
            unlocked = True
            self.daemon_ready('unlock-daemon-restarted', 30)
        finally:
            self.record('cancel', check=False)
            self.kill(self.player)
            self.player = None
            # A failed assertion must not leave the disposable VM locked or
            # VoxType stopped and contaminate later independent gates.
            if lock_command and not locked:
                locked = self.cmd(['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked'],
                                  check=False).stdout.strip() == b'true'
            if locked and not unlocked:
                if not unlock_requested:
                    print('ARCTIC-DESKTOP-UNLOCK-REQUESTED', flush=True)
                self.observe('unlock-cleanup', lambda: self.cmd(
                    ['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']).stdout.strip() == b'false', 90)
                unlocked = True
            if lock_command:
                self.cmd(['systemctl', '--user', 'start', 'voxtype.service'], check=False)
                self.daemon_ready('unlock-cleanup-daemon', 30)
        return {'locked': True, 'count': 0, 'drained': True}

    def gpu_failure(self):
        require(self.profile_id == 'turbo-q5-v3', 'gpu-gate-requires-modern-profile')
        self.gpu_stage('receiver-clear', self.empty)
        # The frozen GitHub-hosted VM exposes a 2D virtio display without
        # virgl, GPU passthrough or another accelerated Vulkan device. It can
        # validate the signed Vulkan payload and the real unsupported-device
        # failure/recovery path, but it cannot certify GPU acceleration.
        self.gpu_stage('cpu-backend-selection', lambda: self.select(backend='cpu'))

        # Make the visible language selection deterministic for both recovery screens.
        self.gpu_stage('language-selection', lambda: self.select(language='he'))
        # Exercise Arctic's guarded selector against the VM's real unsupported
        # Vulkan environment. Upstream may fall back internally, so a successful
        # command would not certify GPU execution and must invalidate this frozen
        # fixture instead of being counted as recovery evidence. Stop the resident
        # CPU model to make resource pressure independent of the setup outcome.
        self.gpu_stage('failed-vulkan-setup', self.vm_vulkan_failure)
        # The explicit setup attempt downloads and verifies the signed Vulkan
        # binary before the unsupported-device proof fails.  Bind those exact
        # retained bytes after that attempt; the normal CPU setup intentionally
        # does not preinstall the optional Vulkan payload.
        self.gpu_stage('cpu-preservation', lambda: require(
            (SYSTEM / 'backend').read_text().strip() == 'cpu'
            and (SYSTEM / 'setup.error').read_text().strip() == 'backend-vulkan',
            'gpu-failure-did-not-preserve-cpu'))
        self.gpu_stage('vulkan-payload-integrity', self.checked_vulkan_payload)
        self.gpu_stage('receiver-empty', lambda: require(
            (self.root / 'received.private').read_bytes() == b'',
            'gpu-failure-inserted-text'))
        def actionable():
            status = self.adapter('status')
            error = str(status.get('error', '')).lower()
            return status if (status.get('state') == 'error'
                and status.get('backend') == 'cpu'
                and ('vulkan' in error or 'gpu' in error)) else None
        status = self.gpu_stage('actionable-error', lambda: self.observe(
            'gpu-failure-actionable-error', actionable, 10))
        gpu_failure_capture_ack_sha256 = self.gpu_stage(
            'gpu-failure-screen', lambda: self.recovery_screen(
                'gpu_failure', status, expected_language='he'))
        # The failed setup preserved CPU authoritatively but also published a
        # setup error.  Invalidate the control cache so the supported CPU
        # selection clears that error and restarts the official daemon before
        # the two recovery dictations.
        self.selected_backend = None
        self.gpu_stage('cpu-recovery-selection', lambda: self.select(backend='cpu'))
        for language in ('en', 'he'):
            sample = next(row for row in self.fixtures
                          if row['language'] == language and row['source_row'] == 0)
            self.transcribe(sample, 'cpu-retry')
        status = self.gpu_stage('cpu-ready-status', lambda: self.adapter('status'))
        cpu_ready_capture_ack_sha256 = self.gpu_stage(
            'cpu-ready-screen', lambda: self.recovery_screen(
                'cpu_ready', status, expected_language='he'))
        return {'gpu_supported': False, 'explicit_cpu_selected': True,
                'failed_attempt_inserted': False, 'count': 2,
                'bytes': ASSETS['vulkan']['bytes'],
                'sha256': ASSETS['vulkan']['sha256'],
                'gpu_failure_capture_ack_sha256': gpu_failure_capture_ack_sha256,
                'cpu_ready_capture_ack_sha256': cpu_ready_capture_ack_sha256}

    def vm_vulkan_failure(self):
        """Require the frozen non-GPU VM to reject real Vulkan selection."""
        self.cmd(['systemctl', '--user', 'stop', 'voxtype.service'])
        try:
            failed = run(['/usr/bin/env', 'PKEXEC_UID=' + str(self.account.pw_uid),
                          str(SETUP), '--backend', 'vulkan'], 750, check=False)
            require(failed.returncode != 0, 'vm-vulkan-fixture-unexpectedly-supported')
            return failed
        finally:
            # The setup failure preserves CPU and publishes an error. Restore
            # the official daemon so Settings can display that checked state;
            # the later explicit CPU selection clears the error and restarts it.
            self.cmd(['systemctl', '--user', 'start', 'voxtype.service'], check=False)

    def recovery_screen(self, stage, status, expected_language):
        """Bind an exact host screenshot to the visible, transcript-free Settings state."""
        require(stage in ('gpu_failure', 'cpu_ready'), 'recovery-screen-stage')
        require((status.get('state'), status.get('backend')) ==
                (('error', 'cpu') if stage == 'gpu_failure' else ('ready', 'cpu')),
                'recovery-screen-status')
        require(expected_language is None or status.get('language') == expected_language,
                'recovery-screen-language')
        require(stage != 'cpu_ready' or status.get('ready') is True,
                'recovery-screen-not-ready')
        self.empty()
        self.cmd(['/usr/bin/arctic-settings', 'dictation'])

        def visible():
            page = self.cmd(['/usr/bin/quickshell', 'ipc', 'call', 'settings', 'page'],
                            check=False)
            ready = self.cmd(['/usr/bin/quickshell', 'ipc', 'call', 'settings', 'ready'],
                             check=False)
            clients = json.loads(self.cmd(['mmsg', 'get', 'all-clients']).stdout)['clients']
            rows = [row for row in clients if row.get('title') == 'Arctic Settings']
            require(len(rows) <= 1, 'recovery-settings-window-duplicate')
            return (page.returncode == ready.returncode == 0
                    and page.stdout.strip() == b'dictation'
                    and ready.stdout.strip() == b'true'
                    and len(rows) == 1 and rows[0].get('is_visible') is True
                    and rows[0].get('is_focused') is True
                    and Path('/proc', str(rows[0]['pid'])).stat().st_uid == self.account.pw_uid)
        self.observe('recovery-settings-visible', visible, 30)
        # DictationPage refreshes its service model asynchronously when shown.
        time.sleep(2)
        # Refresh after opening and bind the screen to the same checked state.
        shown = self.adapter('status')
        require(shown == status, 'recovery-screen-status-changed')
        screenshot = self.root / ('dictation-recovery-' + stage + '.png')
        self.cmd(['/usr/bin/grim', str(screenshot)])
        require(screenshot.is_file() and screenshot.stat().st_size > 1000,
                'recovery-screen-guest-screenshot-missing')
        require((self.root / 'received.private').read_bytes() == b'',
                'recovery-screen-receiver-not-empty')
        nonce = os.urandom(16).hex()
        print('ARCTIC-DICTATION-RECOVERY-SCREEN-REQUESTED ' + json.dumps({
            'boot_id': self.report['boot_id'],
            'installation_id': self.context['installation_id'],
            'phase': self.context['phase'], 'desktop_uid': self.account.pw_uid,
            'receiver_empty': True, 'stage': stage, 'state': shown['state'],
            'backend': shown['backend'], 'language': shown['language'],
            'capture_nonce': nonce}), flush=True)
        wait(lambda: (self.root / 'received.private').read_text() == nonce, 45)
        self.empty()
        return hashlib.sha256(nonce.encode()).hexdigest()

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

    def privacy_gate(self):
        name = 'transcript-log-notification-leak-scan'
        if len(self.phrases) < 12 and any(
                gate.get('status') == 'failed' for gate in self.report['gates']):
            return self.dependent_unrun(name)
        return self.gate(name, self.leakage)

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
        if not self.loop:
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
        self.privacy_gate()

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
                available = self.gate('explicit-service-recovery-ready', self.recovery)
                integrity = self.gate('installed-payload-integrity', self.payload)
                if available and integrity and self.profile_id == 'turbo-q5-v3':
                    self.gate(VULKAN_ISOLATION_GATE,
                              self.prepare_vulkan_offline_boundary)
            else:
                readiness = 'online-installer-ready' if phase == 'online-installed' else 'recovered-ready'
                integrity = self.gate('installed-payload-integrity', self.payload)
                isolated = True
                if (integrity and phase == 'online-installed'
                        and self.profile_id == 'turbo-q5-v3'):
                    isolated = self.gate(VULKAN_ISOLATION_GATE,
                                         self.prepare_vulkan_offline_boundary)
                available = self.gate(readiness, self.ready) if integrity and isolated else False
                if available and integrity and isolated:
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
