#!/usr/bin/env python3
"""Exact-image, disposable live installer restoration evidence.

Uses the already running packaged GUI and root engine. No replacement GUI,
installation, package download, service restart, or policy change is permitted.
The prepared Hebrew keyboard baseline is retained across real VT and host-driven
DRM output loss. This evidence alone cannot qualify a public release.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import pwd
import re
import signal
import socket
import stat
import struct
import sys
import tempfile
import time
import zlib

SCHEMA = 'arctic-live-installer-restoration-v1'
CONTEXT_FIELDS = {'schema', 'source_sha', 'iso_sha256', 'iso_bytes', 'execution_sha', 'binding_id',
                  'checker_sha256', 'runtime_sha256', 'native_sha256', 'capture_sha256'}
ACTIVE_FIELDS = {'active_checker_sha256', 'installed_checker_sha256', 'disk_serial',
                 'disk_bytes', 'disk_node', 'write_bps'}
BUNDLE = {'installer-guest.py': 'checker_sha256', 'taskbar-runtime.py': 'runtime_sha256',
          'native_smoke.py': 'native_sha256', 'raw-screencopy': 'capture_sha256'}
GUI_PATH = '/usr/share/arctic/installer-ui'
SOCKET_PATH = '/run/arcticd.sock'
PORT_NAME = 'arctic-installer-evidence'
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 32 * 1024 * 1024
MAX_FILES = 32
CHUNK = 18 * 1024
TIMEOUT = 600
CHECK_BUDGET = 480
KEYBOARD = {'layout': 'il', 'variant': '', 'xkb': {
    'layout': 'us,il', 'variant': '', 'options': 'grp:alt_shift_toggle',
    'keymap': 'us', 'latin': False}}
OVERRIDES = ('ARCTIC_INSTALLER_BRIDGE', 'ARCTIC_INSTALLER_SOCKET', 'ARCTIC_INSTALLER_MOCK',
             'ARCTIC_LIVE_KEYBOARD')


# Only source-attested fixed literals and phases may survive active error masking.
# These labels describe failures; they never alter a report or release verdict.
PRIMARY_DIAGNOSTIC_LITERALS = {'DRM connector belongs to another card': 'drm-connector-belongs-to-another-card',
 'Mango DRM process is absent or ambiguous': 'mango-drm-process-is-absent-or-ambiguous',
 'Mango DRM process session differs': 'mango-drm-process-session-differs',
 'Mango DRM process changed during observation': 'mango-drm-process-changed-during-observation',
 'Mango DRM descriptor has no canonical sysfs identity': 'mango-drm-descriptor-has-no-canonical-sysfs-identity',
 'Mango DRM descriptor major/minor backlink differs': 'mango-drm-descriptor-major-minor-backlink-differs',
 'Mango primary/render DRM device binding differs': 'mango-primary-render-drm-device-binding-differs',
 'actual DRM PCI transport is not virtio-pci': 'actual-drm-pci-transport-is-not-virtio-pci',
 'actual DRM virtio child is not GPU': 'actual-drm-virtio-child-is-not-gpu',
 'GUI Hebrew autosave has not completed': 'gui-hebrew-autosave-has-not-completed',
 'GUI Start replaced the original engine': 'gui-start-replaced-the-original-engine',
 'GUI fill outside Hebrew keyboard choice': 'gui-fill-outside-hebrew-keyboard-choice',
 'GUI is not the packaged installer invocation': 'gui-is-not-the-packaged-installer-invocation',
 'GUI method outside bounded whitelist': 'gui-method-outside-bounded-whitelist',
 'GUI reconnected or subscription inventory is ambiguous': 'gui-reconnected-or-subscription-inventory-is-ambiguous',
 'Hebrew fill is only permitted on ready keyboard': 'hebrew-fill-is-only-permitted-on-ready-keyboard',
 'Next is only permitted from ready welcome': 'next-is-only-permitted-from-ready-welcome',
 'QEMU head binding requires exactly one actual DRM card': 'qemu-head-binding-requires-exactly-one-actual-drm-card',
 'account fixture differs (details withheld)': 'account-fixture-differs-details-withheld',
 'active GUI IPC failed (details withheld)': 'active-gui-ipc-failed-details-withheld',
 'active GUI is not on a ready wizard page': 'active-gui-is-not-on-a-ready-wizard-page',
 'active GUI method outside whitelist': 'active-gui-method-outside-whitelist',
 'active Hebrew configuration changed': 'active-hebrew-configuration-changed',
 'active Next is disabled': 'active-next-is-disabled',
 'active desktop does not own the actual foreground VT': 'active-desktop-does-not-own-the-actual-foreground-vt',
 'active engine progress regressed': 'active-engine-progress-regressed',
 'active fill outside reviewed choice': 'active-fill-outside-reviewed-choice',
 'active safe configuration changed': 'active-safe-configuration-changed',
 'active shipped sources or physical head binding changed': 'active-shipped-sources-or-physical-head-binding-changed',
 'active state parameters differ': 'active-state-parameters-differ',
 'actual DRM connector ID absent': 'actual-drm-connector-id-absent',
 'actual DRM device is not virtio_gpu': 'actual-drm-device-is-not-virtio-gpu',
 'actual DRM virtual connector inventory differs from exact two-head contract': 'actual-drm-virtual-connector-inventory-differs-from-exact-two-head-contract',
 'actual GUI page, choice, connection, or readiness differs': 'actual-gui-page-choice-connection-or-readiness-differs',
 'actual Hebrew keyboard baseline did not settle': 'actual-hebrew-keyboard-baseline-did-not-settle',
 'actual PCI device is not the isolated QEMU virtio GPU': 'actual-pci-device-is-not-the-isolated-qemu-virtio-gpu',
 'actual active GUI state differs': 'actual-active-gui-state-differs',
 'actual active engine identity differs': 'actual-active-engine-identity-differs',
 'actual copy writer argv differs': 'actual-copy-writer-argv-differs',
 'actual current output mode missing or ambiguous': 'actual-current-output-mode-missing-or-ambiguous',
 'actual default engine socket type/owner/mode differs': 'actual-default-engine-socket-type-owner-mode-differs',
 'actual engine Hello identity differs': 'actual-engine-hello-identity-differs',
 'actual engine connection closed': 'actual-engine-connection-closed',
 'actual engine started an installation': 'actual-engine-started-an-installation',
 'actual engine state changed during restoration': 'actual-engine-state-changed-during-restoration',
 'actual installer background pixels are absent': 'actual-installer-background-pixels-are-absent',
 'actual installer backing window is not visible': 'actual-installer-backing-window-is-not-visible',
 'actual installer process uses a test/mock override': 'actual-installer-process-uses-a-test-mock-override',
 'actual live Hebrew configuration differs': 'actual-live-hebrew-configuration-differs',
 'actual live engine identity/state differs': 'actual-live-engine-identity-state-differs',
 'actual writer target mount is not owned btrfs': 'actual-writer-target-mount-is-not-owned-btrfs',
 'armed Summary config changed': 'armed-summary-config-changed',
 'auto-opened installer must already be ready at welcome': 'auto-opened-installer-must-already-be-ready-at-welcome',
 'bridge is not the real default-socket invocation': 'bridge-is-not-the-real-default-socket-invocation',
 'bundle is not protected root-owned content': 'bundle-is-not-protected-root-owned-content',
 'default engine listening socket is missing or ambiguous': 'default-engine-listening-socket-is-missing-or-ambiguous',
 'duplicate JSON key': 'duplicate-json-key',
 'duplicate actual output': 'duplicate-actual-output',
 'duplicate process environment key': 'duplicate-process-environment-key',
 'engine response exceeded time/byte bound': 'engine-response-exceeded-time-byte-bound',
 'engine response framing differs': 'engine-response-framing-differs',
 'engine returned an error, event, or different response id': 'engine-returned-an-error-event-or-different-response-id',
 'engine snapshot fields differ': 'engine-snapshot-fields-differ',
 'engine socket peer is not root': 'engine-socket-peer-is-not-root',
 'engine uses unexpected mock/test/runtime flags': 'engine-uses-unexpected-mock-test-runtime-flags',
 'file changed while being read': 'file-changed-while-being-read',
 'file is nonregular or oversized': 'file-is-nonregular-or-oversized',
 'genuine copy phase is required for every disruption observation': 'genuine-copy-phase-is-required-for-every-disruption-observation',
 'initial actual engine page differs': 'initial-actual-engine-page-differs',
 'installer ELF path differs': 'installer-elf-path-differs',
 'installer PNG exceeded bound': 'installer-png-exceeded-bound',
 'installer RPC method or parameters outside read-only whitelist': 'installer-rpc-method-or-parameters-outside-read-only-whitelist',
 'installer belongs to a different actual session': 'installer-belongs-to-a-different-actual-session',
 'installer check budget exhausted': 'installer-check-budget-exhausted',
 'installer does not occupy the complete logical output': 'installer-does-not-occupy-the-complete-logical-output',
 'installer executable is not a native ELF': 'installer-executable-is-not-a-native-elf',
 'installer mapped to unavailable or ambiguous output': 'installer-mapped-to-unavailable-or-ambiguous-output',
 'installer process is dead': 'installer-process-is-dead',
 'installer process owner differs': 'installer-process-owner-differs',
 'invalid actual output identity': 'invalid-actual-output-identity',
 'invalid actual output inventory': 'invalid-actual-output-inventory',
 'invalid actual output scale': 'invalid-actual-output-scale',
 'invalid actual physical mode': 'invalid-actual-physical-mode',
 'invalid capture label': 'invalid-capture-label',
 'invalid listening Unix socket inode': 'invalid-listening-unix-socket-inode',
 'invalid mapped layer inventory': 'invalid-mapped-layer-inventory',
 'invalid native physical capture': 'invalid-native-physical-capture',
 'invalid process PID': 'invalid-process-pid',
 'invalid process command line': 'invalid-process-command-line',
 'live keyboard file protection differs': 'live-keyboard-file-protection-differs',
 'live-keyboard helper has not completed': 'live-keyboard-helper-has-not-completed',
 'malformed process environment': 'malformed-process-environment',
 'missing or duplicate mapped installer': 'missing-or-duplicate-mapped-installer',
 'native capture requires normal output transform': 'native-capture-requires-normal-output-transform',
 'nonfinite JSON number': 'nonfinite-json-number',
 'one original daemon-owned copy writer is required': 'one-original-daemon-owned-copy-writer-is-required',
 'original active engine/GUI identity changed': 'original-active-engine-gui-identity-changed',
 'original actual bridge process changed': 'original-actual-bridge-process-changed',
 'original copy writer was replaced': 'original-copy-writer-was-replaced',
 'original shipped GUI process changed': 'original-shipped-gui-process-changed',
 'owned target already has partitions': 'owned-target-already-has-partitions',
 'owned target device identity differs': 'owned-target-device-identity-differs',
 'owned target driver/size differs': 'owned-target-driver-size-differs',
 'owned target is already in use': 'owned-target-is-already-in-use',
 'owned target serial/path is absent or ambiguous': 'owned-target-serial-path-is-absent-or-ambiguous',
 'packaged installer entry point differs': 'packaged-installer-entry-point-differs',
 'physical capture dimensions differ': 'physical-capture-dimensions-differ',
 'prepared real engine Hebrew state differs': 'prepared-real-engine-hebrew-state-differs',
 'private credential fixture differs': 'private-credential-fixture-differs',
 'process environment is oversized': 'process-environment-is-oversized',
 'raw capture target already exists': 'raw-capture-target-already-exists',
 'real GUI engine did not enter genuine copy': 'real-gui-engine-did-not-enter-genuine-copy',
 'real GUI must own exactly one default-socket bridge': 'real-gui-must-own-exactly-one-default-socket-bridge',
 'real Hebrew choice failed': 'real-hebrew-choice-failed',
 'real bridge session differs': 'real-bridge-session-differs',
 'real keyboard page did not load': 'real-keyboard-page-did-not-load',
 'real root engine does not own the default listening socket FD': 'real-root-engine-does-not-own-the-default-listening-socket-fd',
 'real root engine service identity differs': 'real-root-engine-service-identity-differs',
 'real welcome Next failed': 'real-welcome-next-failed',
 'real wizard armed Next failed': 'real-wizard-armed-next-failed',
 'real wizard fill failed': 'real-wizard-fill-failed',
 'real wizard page did not become ready': 'real-wizard-page-did-not-become-ready',
 'real wizard selection is invalid': 'real-wizard-selection-is-invalid',
 'requires exactly one already running packaged installer': 'requires-exactly-one-already-running-packaged-installer',
 'restoration enabled-output count differs': 'restoration-enabled-output-count-differs',
 'safe Summary offline/disk/encryption differs': 'safe-summary-offline-disk-encryption-differs',
 'target partition belongs to another disk': 'target-partition-belongs-to-another-disk',
 'unexpected GUI method parameters': 'unexpected-gui-method-parameters',
 'unexpected writable guest disk': 'unexpected-writable-guest-disk',
 'virtio GPU PCI device binding is absent or ambiguous': 'virtio-gpu-pci-device-binding-is-absent-or-ambiguous'}
DIAGNOSTIC_EXCEPTION_CLASSES = {
    RuntimeError: ('RuntimeError', 'runtime-error'), ValueError: ('ValueError', 'value-error'),
    KeyError: ('KeyError', 'key-error'), TypeError: ('TypeError', 'type-error'),
    OSError: ('OSError', 'os-error'), InterruptedError: ('InterruptedError', 'interrupted'),
    FileNotFoundError: ('FileNotFoundError', 'file-not-found'),
    PermissionError: ('PermissionError', 'permission-error'),
    ProcessLookupError: ('ProcessLookupError', 'process-lookup-error'),
    TimeoutError: ('TimeoutError', 'timeout-error'),
    KeyboardInterrupt: ('KeyboardInterrupt', 'keyboard-interrupt'),
    SystemExit: ('SystemExit', 'system-exit'), Exception: ('Exception', 'exception'),
    BaseException: ('BaseException', 'base-exception')}
TARGET_DIAGNOSTIC_PHASES = frozenset((
    'target-enumerate', 'target-partition', 'target-serial', 'target-driver',
    'target-size', 'target-node-stat', 'target-major-minor', 'target-lsblk-disks',
    'target-pristine-partitions', 'target-lsblk-mounts'))
TARGET_DIAGNOSTIC_ERRNOS = {1: 'eperm', 5: 'eio', 6: 'enxio', 12: 'enomem',
    13: 'eacces', 16: 'ebusy', 19: 'enodev', 20: 'enotdir', 22: 'einval',
    30: 'erofs', 38: 'enosys', 40: 'eloop', 95: 'eopnotsupp'}
ACTIVE_DIAGNOSTIC_PHASES = frozenset((
    *TARGET_DIAGNOSTIC_PHASES,
    'unknown', 'security-init', 'prepare-start', 'prepare-find-gui', 'prepare-identities',
    'prepare-rpc', 'prepare-target', 'prepare-credentials', 'prepare-summary-config',
    'prepare-summary-identities', 'prepare-copy', 'prepare-copy-identities',
    'prepare-visible', 'prepare-baseline-physical', 'vt-0', 'output-0', 'completion',
    *('prepare-' + page + '-' + operation
      for page in ('welcome', 'keyboard', 'network', 'timezone', 'disk', 'encryption',
                   'account', 'apps', 'summary')
      for operation in ('ready', 'valid', 'next')),
    *('prepare-' + page + '-fill'
      for page in ('keyboard', 'network', 'disk', 'encryption', 'account', 'apps'))))


def primary_diagnostic_reason(error):
    # Exact builtin type avoids hostile subclass properties or __str__ calls.
    if type(error) is RuntimeError and type(error.args) is tuple and len(error.args) == 1 and type(error.args[0]) is str:
        return PRIMARY_DIAGNOSTIC_LITERALS.get(error.args[0], 'unknown')
    return 'unknown'


def primary_diagnostic_errno(error):
    """Read only the builtin descriptor of an exact builtin OSError."""
    if type(error) is not OSError:
        return 'unknown'
    number = OSError.errno.__get__(error, OSError)
    return TARGET_DIAGNOSTIC_ERRNOS.get(number, 'other') if type(number) is int else 'unknown'


def masked_active_error(error, phase):
    """Keep the original mask and only append fixed trusted failure labels."""
    error_class = next((name for error_type, (name, _) in DIAGNOSTIC_EXCEPTION_CLASSES.items()
                        if type(error) is error_type), 'OtherError')
    phase = phase if type(phase) is str and phase in ACTIVE_DIAGNOSTIC_PHASES else 'unknown'
    errno = '; errno=' + primary_diagnostic_errno(error) if type(error) is OSError and phase in TARGET_DIAGNOSTIC_PHASES else ''
    return (error_class + ': active installation or restoration failed [phase=' + phase + errno +
            '; reason=' + primary_diagnostic_reason(error) + ']')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise RuntimeError('nonfinite JSON number')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=MAX_FILE, root_owned=False):
    """Bootstrap protection before importing the hash-checked transport helper."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
                'file is nonregular or oversized')
        require(not root_owned or (info.st_uid == 0 and not info.st_mode & 0o022),
                'bundle is not protected root-owned content')
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        after = os.fstat(fd)
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        require(len(data) == info.st_size and len(data) <= limit
                and all(getattr(info, k) == getattr(after, k) for k in fields),
                'file changed while being read')
        return bytes(data)
    finally:
        os.close(fd)


def validate_context(value):
    if type(value) is dict and value.get('schema') == 'arctic-installer-active-context-v1':
        require(set(value) == CONTEXT_FIELDS | ACTIVE_FIELDS, 'active installer context differs')
        base = {key: value[key] for key in CONTEXT_FIELDS}
        base['schema'] = 'arctic-installer-context-v1'
        validate_context(base)
        require(all(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key])
                    for key in ('active_checker_sha256', 'installed_checker_sha256')),
                'active installer checker hash differs')
        require(type(value['disk_serial']) is str and re.fullmatch('arctic-a-[0-9a-f]{11}', value['disk_serial'])
                and type(value['disk_bytes']) is int and value['disk_bytes'] == 64 * 1024**3
                and value['disk_node'] == 'target0' and type(value['write_bps']) is int
                and value['write_bps'] == 8 * 1024**2, 'owned active target fixture differs')
        return value
    require(type(value) is dict and set(value) == CONTEXT_FIELDS
            and value['schema'] == 'arctic-installer-context-v1', 'installer context differs')
    for key in CONTEXT_FIELDS - {'schema', 'iso_bytes', 'source_sha', 'execution_sha', 'binding_id'}:
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]),
                'invalid installer SHA-256: ' + key)
    for key in ('source_sha', 'execution_sha'):
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{40}', value[key]),
                'invalid installer commit: ' + key)
    require(type(value['binding_id']) is str and re.fullmatch('[0-9a-f]{32}', value['binding_id']),
            'invalid installer execution binding_id')
    require(type(value['iso_bytes']) is int and 0 < value['iso_bytes'] < 2_000_000_000,
            'invalid exact-image size')
    return value


def emit(kind, value, stream=None):
    print('ARCTIC-INSTALLER-' + kind + ' ' + json.dumps(value, sort_keys=True, allow_nan=False),
          file=stream if stream is not None else sys.stdout, flush=True)


class EngineRPC:
    """A single, bounded, read-only connection to the real default engine socket."""
    def __init__(self, factory=socket.socket):
        self.sock = factory(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.sock.settimeout(5)
            self.sock.connect(SOCKET_PATH)
            _, peer_uid, peer_gid = struct.unpack('3i', self.sock.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i')))
            # systemd creates the listening socket: peer PID may be 1. It does not
            # identify the engine; service and /proc identity prove that separately.
            require(peer_uid == 0, 'engine socket peer is not root')
        except BaseException:
            self.sock.close()
            raise
        self.peer = dict(uid=peer_uid, gid=peer_gid,
                         pid_claim='none; socket activation can report systemd')
        self.buffer = b''
        self.next_id = 1

    def permitted(self, method, params):
        allowed = method == 'Hello' and params == {
            'client': 'installer-restoration-qualification', 'version': '1.2.1'}
        allowed |= method == 'GetWizard' and params is None
        allowed |= method == 'GetStep' and type(params) is dict and set(params) == {'id'} \
            and params['id'] in ('welcome', 'keyboard', 'install')
        return allowed

    def call(self, method, params=None):
        require(self.permitted(method, params), 'installer RPC method or parameters outside read-only whitelist')
        request_id = self.next_id
        self.next_id += 1
        request = dict(id=request_id, method=method)
        if params is not None:
            request['params'] = params
        self.sock.sendall((json.dumps(request, allow_nan=False) + '\n').encode())
        deadline = time.monotonic() + 5
        while b'\n' not in self.buffer:
            require(time.monotonic() < deadline and len(self.buffer) < MAX_FILE,
                    'engine response exceeded time/byte bound')
            self.sock.settimeout(max(.01, deadline - time.monotonic()))
            part = self.sock.recv(min(65536, MAX_FILE + 1 - len(self.buffer)))
            require(part, 'actual engine connection closed')
            self.buffer += part
        line, self.buffer = self.buffer.split(b'\n', 1)
        require(len(line) <= MAX_FILE and not self.buffer, 'engine response framing differs')
        response = strict_json(line)
        require(type(response) is dict and type(response.get('id')) is int and response['id'] == request_id
                and 'error' not in response and set(response) == {'id', 'result'},
                'engine returned an error, event, or different response id')
        return response['result']

    def snapshot(self):
        hello = self.call('Hello', {'client': 'installer-restoration-qualification', 'version': '1.2.1'})
        require(type(hello) is dict and hello.get('mock') is False and hello.get('live') is True
                and hello.get('state') == 'wizard' and hello.get('engine_version') == '1.2.1'
                and type(hello.get('protocol_version')) is int and hello['protocol_version'] == 1, 'actual live engine identity/state differs')
        return dict(hello=hello, wizard=self.call('GetWizard'),
                    welcome=self.call('GetStep', {'id': 'welcome'}),
                    keyboard=self.call('GetStep', {'id': 'keyboard'}),
                    install=self.call('GetStep', {'id': 'install'}))

    def close(self):
        self.sock.close()


def parse_environment(data):
    require(len(data) <= 1024 * 1024, 'process environment is oversized')
    entries = data.decode().rstrip('\0').split('\0')
    result = {}
    for entry in entries:
        if not entry:
            continue
        require('=' in entry, 'malformed process environment')
        key, value = entry.split('=', 1)
        require(key not in result, 'duplicate process environment key')
        result[key] = value
    require(not any(result.get(key) for key in OVERRIDES)
            and not any(k.startswith('ARCTIC_MOCK_') and v for k, v in result.items()),
            'actual installer process uses a test/mock override')
    return result


def process_proof(pid, uid, expected_executable, proc_root=Path('/proc')):
    require(type(pid) is int and pid > 1, 'invalid process PID')
    proc = Path(proc_root) / str(pid)
    require(proc.stat().st_uid == uid, 'installer process owner differs')
    text = (proc / 'stat').read_text()
    fields = text.rsplit(')', 1)[1].split()
    require(fields[0] not in ('Z', 'X'), 'installer process is dead')
    executable = str((proc / 'exe').resolve(strict=True))
    require(executable == str(Path(expected_executable).resolve(strict=True)), 'installer ELF path differs')
    binary = read_regular(executable, 128 * 1024 * 1024, root_owned=True)
    require(binary.startswith(b'\x7fELF'), 'installer executable is not a native ELF')
    argv = (proc / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')
    require(0 < len(argv) <= 32 and sum(map(len, argv)) <= 16384, 'invalid process command line')
    env = parse_environment((proc / 'environ').read_bytes())
    return dict(pid=pid, uid=uid, start_ticks=int(fields[19]), ppid=int(fields[1]),
                executable=executable, executable_sha256=sha(binary),
                argv=[v.decode() for v in argv], overrides_absent=True), env


def validate_gui_argv(argv):
    require(type(argv) is list and len(argv) == 3 and Path(argv[0]).name == 'quickshell'
            and argv[1:] == ['-p', GUI_PATH], 'GUI is not the packaged installer invocation')


def validate_bridge_argv(argv):
    require(type(argv) is list and len(argv) == 2 and Path(argv[0]).name == 'arctic-install'
            and argv[1] == 'bridge', 'bridge is not the real default-socket invocation')


def listener_proof(pid, proc_root=Path('/proc'), socket_path=Path(SOCKET_PATH)):
    """Bind the serving root process to the default listening Unix socket."""
    info = socket_path.lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o660,
            'actual default engine socket type/owner/mode differs')
    matches = []
    for line in (Path(proc_root) / 'net/unix').read_text().splitlines()[1:]:
        fields = line.split()
        if len(fields) == 8 and fields[7] == str(socket_path) and fields[3:6] == ['00010000', '0001', '01']:
            require(fields[6].isdigit(), 'invalid listening Unix socket inode')
            matches.append(int(fields[6]))
    require(len(matches) == 1, 'default engine listening socket is missing or ambiguous')
    links = []
    for entry in (Path(proc_root) / str(pid) / 'fd').iterdir():
        try:
            if entry.name.isdigit() and os.readlink(entry) == 'socket:[' + str(matches[0]) + ']':
                links.append(int(entry.name))
        except FileNotFoundError:
            pass
    require(1 <= len(links) <= 4, 'real root engine does not own the default listening socket FD')
    return dict(path=str(socket_path), filesystem_device=info.st_dev, filesystem_inode=info.st_ino,
                uid=info.st_uid, mode=stat.S_IMODE(info.st_mode), stream_inode=matches[0],
                serving_pid=pid, listening_fds=sorted(links))


def engine_log_counts(path=Path('/var/log/arctic-install/engine.log')):
    if not path.exists():
        return dict(available=False, reason='canonical engine log absent; no reconnect-log claim')
    data = read_regular(path, 16 * 1024 * 1024, root_owned=True).decode()
    hello, subscriptions = 0, []
    supported = False
    for line in data.splitlines():
        match = re.search(r'\barcticd: -> Hello (\{.*\})$', line)
        if match:
            supported = True
            if strict_json(match[1]).get('client') == 'installer-ui':
                hello += 1
        match = re.search(r'\barcticd: -> Subscribe \(session ([0-9]+)\)$', line)
        if match:
            supported = True
            subscriptions.append(int(match[1]))
    if not supported:
        return dict(available=False, reason='canonical log format unobserved; no reconnect-log claim')
    require(hello == 1 and len(subscriptions) == 1, 'GUI reconnected or subscription inventory is ambiguous')
    info = path.stat()
    return dict(available=True, path=str(path), device=info.st_dev, inode=info.st_ino,
                gui_hello_count=hello, subscribe_count=len(subscriptions),
                subscribe_sessions=subscriptions)


def validate_engine_snapshot(value, expected=None):
    require(type(value) is dict and set(value) == {'hello', 'wizard', 'welcome', 'keyboard', 'install'},
            'engine snapshot fields differ')
    hello = value['hello']
    require(type(hello) is dict and hello.get('live') is True and hello.get('mock') is False
            and hello.get('state') == 'wizard' and hello.get('engine_version') == '1.2.1'
            and type(hello.get('protocol_version')) is int and hello['protocol_version'] == 1
            and hello.get('firmware') in ('uefi', 'bios'), 'actual engine Hello identity differs')
    require(value['wizard']['current'] == 'keyboard' and value['wizard']['state'] == 'wizard'
            and value['keyboard']['data'] == KEYBOARD, 'prepared real engine Hebrew state differs')
    options = value['install']['options']
    require(type(options) is dict and not any(options.get(k) for k in ('progress', 'attention', 'failed'))
            and options.get('modules') == [], 'actual engine started an installation')
    if expected is not None:
        require(value == expected, 'actual engine state changed during restoration')
    return value


def enabled_outputs(value):
    require(type(value) is list and len(value) <= 16 and all(type(o) is dict for o in value),
            'invalid actual output inventory')
    require(all(type(o.get('enabled')) is bool and type(o.get('name')) is str
                and re.fullmatch('[A-Za-z0-9_.-]{1,63}', o['name']) for o in value),
            'invalid actual output identity')
    require(len({o['name'] for o in value}) == len(value), 'duplicate actual output')
    return [o for o in value if o['enabled']]


def window_proof(state, layers, outputs, expected_count=2):
    require(type(state) is dict and state.get('page') == state.get('current') == 'keyboard'
            and state.get('keyboard') == 'il' and state.get('view') == 'step'
            and state.get('connected') is True and state.get('ready') is True
            and state.get('valid') is True and state.get('busy') is False
            and not state.get('failure') and not state.get('error') and not state.get('fields'),
            'actual GUI page, choice, connection, or readiness differs')
    win = state['window']
    require(win.get('visible') is True and win.get('backing_visible') is True,
            'actual installer backing window is not visible')
    require(type(layers) is list, 'invalid mapped layer inventory')
    mapped = [l for l in layers if l.get('name') == 'arctic-installer']
    require(len(mapped) == 1 and mapped[0].get('layer') == 'top'
            and mapped[0].get('monitor') == win.get('screen'), 'missing or duplicate mapped installer')
    available = enabled_outputs(outputs)
    require(type(expected_count) is int and expected_count in (1, 2) and len(available) == expected_count,
            'restoration enabled-output count differs')
    matches = [o for o in available if o['name'] == win.get('screen')]
    require(len(matches) == 1, 'installer mapped to unavailable or ambiguous output')
    output = matches[0]
    require(output.get('transform') == 'normal', 'native capture requires normal output transform')
    modes = [m for m in output['modes'] if m.get('current') is True]
    require(len(modes) == 1, 'actual current output mode missing or ambiguous')
    mode = modes[0]
    scale = output.get('scale')
    require(type(scale) in (float, int) and math.isfinite(scale) and .5 <= scale <= 3,
            'invalid actual output scale')
    require(all(type(mode.get(k)) is int and (640 if k == 'width' else 360) <= mode[k] <= 8192
                for k in ('width', 'height')),
            'invalid actual physical mode')
    require(all(type(win.get(k)) in (float, int) and math.isfinite(win[k])
                and abs(win[k] - mode[k] / scale) <= 1 for k in ('width', 'height')),
            'installer does not occupy the complete logical output')
    return dict(window=win, layers=mapped, output=output, physical_size=[mode['width'], mode['height']])


def mango_drm_devices(uid, session, proc_root=Path('/proc'), sys_root=Path('/sys')):
    """Bind the real compositor's open primary/render FDs to sysfs devices."""
    mangos = []
    for proc in Path(proc_root).glob('[0-9]*'):
        try:
            if proc.stat().st_uid != uid or (proc / 'comm').read_text().strip() != 'mango':
                continue
            proof, env = process_proof(int(proc.name), uid, '/usr/bin/mango', proc_root)
            require(env.get('XDG_SESSION_ID') == session, 'Mango DRM process session differs')
            mangos.append(proof)
        except (FileNotFoundError, ProcessLookupError):
            pass
    require(len(mangos) == 1, 'Mango DRM process is absent or ambiguous')
    proof = mangos[0]
    devices, primary = set(), set()
    for descriptor in (Path(proc_root) / str(proof['pid']) / 'fd').iterdir():
        if not descriptor.name.isdigit():
            continue
        try:
            info = descriptor.stat()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev) != 226:
            continue
        number = str(os.major(info.st_rdev)) + ':' + str(os.minor(info.st_rdev))
        node = (Path(sys_root) / 'dev/char' / number).resolve(strict=True)
        require(re.fullmatch(r'card[0-9]+|renderD[0-9]+', node.name) and
                (Path(sys_root) / 'class/drm' / node.name).resolve(strict=True) == node,
                'Mango DRM descriptor has no canonical sysfs identity')
        require((node / 'dev').read_text().strip() == number,
                'Mango DRM descriptor major/minor backlink differs')
        device = (node / 'device').resolve(strict=True)
        devices.add(device)
        if re.fullmatch('card[0-9]+', node.name):
            primary.add(device)
    require(primary and devices == primary, 'Mango primary/render DRM device binding differs')
    current, _ = process_proof(proof['pid'], uid, '/usr/bin/mango', proc_root)
    require(current == proof, 'Mango DRM process changed during observation')
    return primary


class Installer:
    def __init__(self, native, context, request=emit):
        self.native, self.context, self.request_emit = native, context, request
        self.deadline = time.monotonic() + CHECK_BUDGET
        self.prefix = native.discover_desktop()
        require(self.prefix[:2] == ['runuser', '-u'] and self.prefix[3:5] == ['--', 'env'],
                'actual desktop prefix differs')
        self.user = pwd.getpwnam(self.prefix[2])
        self.uid = self.user.pw_uid
        require(self.user.pw_name == 'liveuser' and self.uid >= 1000, 'actual live account differs')
        env = dict(v.split('=', 1) for v in self.prefix[5:] if '=' in v)
        self.session = env.get('XDG_SESSION_ID')
        require(self.session and re.fullmatch('[A-Za-z0-9_-]{1,64}', self.session), 'actual session absent')
        self.session_env = env
        self.boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', self.boot_id), 'invalid boot ID')
        self.original_vt = int(self.session_property('VTNr'))
        require(1 <= self.original_vt <= 63 and self.original_vt != 6, 'actual VT cannot use the away VT6')
        self.active_session(True)
        self.root = Path(tempfile.mkdtemp(prefix='arctic-native-smoke-installer-', dir='/tmp'))
        os.chown(self.root, self.uid, self.user.pw_gid)
        self.results, self.steps = [], []
        self.rpc = None
        self.gui_pid = self.bridge_pid = None
        self.gui_fd = None
        self.baseline = None
        self.capture_count = 0

    def command(self, argv, desktop=False, timeout=8, allow_failure=False):
        require(time.monotonic() < self.deadline, 'installer check budget exhausted')
        return self.native.execute((self.prefix if desktop else []) + argv, timeout=timeout,
                                   allow_failure=allow_failure)

    def session_property(self, name):
        return self.command(['loginctl', 'show-session', self.session, '-p', name, '--value'])[1]

    def active_session(self, active):
        for key, expected in (('Type', 'wayland'), ('User', str(self.uid)),
                              ('VTNr', str(self.original_vt)), ('Active', 'yes' if active else 'no')):
            require(self.session_property(key) == expected, 'actual desktop session differs: ' + key)
        foreground = Path('/sys/class/tty/tty0/active').read_text().strip()
        require(not active or foreground == 'tty' + str(self.original_vt),
                'active desktop does not own the actual foreground VT')
        return dict(session=self.session, uid=self.uid, vt=self.original_vt, active=active, foreground=foreground)

    def wait(self, fn, seconds, reason):
        end = min(self.deadline, time.monotonic() + seconds)
        last = None
        while time.monotonic() < end:
            try:
                value = fn()
                if value:
                    return value
            except (RuntimeError, OSError, ValueError, KeyError) as exc:
                last = str(exc)
            time.sleep(.2)
        raise RuntimeError(reason + (': ' + last if last else ''))

    def ipc(self, method, payload=None):
        require(method in ('state', 'next', 'fill'), 'GUI method outside bounded whitelist')
        if method == 'next':
            state = strict_json(self.ipc('state'))
            require(state.get('page') == state.get('current') == 'welcome'
                    and state.get('ready') is True and state.get('connected') is True
                    and not state.get('failure'), 'Next is only permitted from ready welcome')
        if method == 'fill':
            require(payload == KEYBOARD or payload == {'layout': 'il', 'variant': ''},
                    'GUI fill outside Hebrew keyboard choice')
            state = strict_json(self.ipc('state'))
            require(state.get('page') == state.get('current') == 'keyboard'
                    and state.get('ready') is True, 'Hebrew fill is only permitted on ready keyboard')
        else:
            require(payload is None, 'unexpected GUI method parameters')
        self.assert_gui_identity()
        argv = ['quickshell', 'ipc', '--pid', str(self.gui_pid), 'call', 'installer', method]
        if method == 'fill':
            argv.append(json.dumps({'layout': 'il', 'variant': ''}))
        return self.command(argv, desktop=True)[1]

    def find_gui(self):
        matches = []
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                if proc.stat().st_uid != self.uid or (proc / 'comm').read_text().strip() != 'quickshell':
                    continue
                argv = [v.decode() for v in (proc / 'cmdline').read_bytes().rstrip(b'\0').split(b'\0')]
                if GUI_PATH not in argv:
                    continue
                proof, env = process_proof(int(proc.name), self.uid, '/usr/bin/quickshell')
                validate_gui_argv(proof['argv'])
                require(all(env.get(k) == self.session_env.get(k)
                            for k in ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'XDG_SESSION_ID')),
                        'installer belongs to a different actual session')
                matches.append(proof)
            except (FileNotFoundError, ProcessLookupError):
                continue
        require(len(matches) == 1, 'requires exactly one already running packaged installer')
        self.gui_pid = matches[0]['pid']
        self.initial_gui = matches[0]
        self.gui_fd = os.pidfd_open(self.gui_pid)
        self.assert_gui_identity()
        bridges = []
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                if proc.stat().st_uid != self.uid:
                    continue
                fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
                if int(fields[1]) != self.gui_pid or (proc / 'comm').read_text().strip() != 'arctic-install':
                    continue
                proof, env = process_proof(int(proc.name), self.uid, '/usr/bin/arctic-install')
                validate_bridge_argv(proof['argv'])
                require(all(env.get(k) == self.session_env.get(k)
                            for k in ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'XDG_SESSION_ID')),
                        'real bridge session differs')
                bridges.append(proof)
            except (FileNotFoundError, ProcessLookupError):
                continue
        require(len(bridges) == 1, 'real GUI must own exactly one default-socket bridge')
        self.bridge_pid = bridges[0]['pid']
        self.initial_bridge = bridges[0]

    def assert_gui_identity(self):
        current, _ = process_proof(self.gui_pid, self.uid, '/usr/bin/quickshell')
        require(current == self.initial_gui, 'original shipped GUI process changed')
        return current

    def identities(self):
        gui = self.assert_gui_identity()
        bridge, _ = process_proof(self.bridge_pid, self.uid, '/usr/bin/arctic-install')
        require(bridge == self.initial_bridge and bridge['ppid'] == gui['pid'],
                'original actual bridge process changed')
        text = self.command(['systemctl', 'show', 'arcticd.service',
                             '-p', 'MainPID', '-p', 'InvocationID', '-p', 'ExecMainStartTimestampMonotonic',
                             '-p', 'ActiveState', '-p', 'NRestarts'])[1]
        service = dict(line.split('=', 1) for line in text.splitlines() if '=' in line)
        require(set(service) == {'MainPID', 'InvocationID', 'ExecMainStartTimestampMonotonic',
                                 'ActiveState', 'NRestarts'} and service['ActiveState'] == 'active'
                and re.fullmatch('[0-9a-f]{32}', service['InvocationID'])
                and service['ExecMainStartTimestampMonotonic'].isdigit()
                and int(service['ExecMainStartTimestampMonotonic']) > 0
                and service['NRestarts'] == '0', 'real root engine service identity differs')
        daemon, _ = process_proof(int(service['MainPID']), 0, '/usr/bin/arcticd')
        require(len(daemon['argv']) == 1 and Path(daemon['argv'][0]).name == 'arcticd',
                'engine uses unexpected mock/test/runtime flags')
        return dict(gui=gui, bridge=bridge, daemon=daemon, service=service,
                    listener=listener_proof(daemon['pid']))

    def outputs(self):
        value = strict_json(self.command(['wlr-randr', '--json'], desktop=True)[1])
        enabled_outputs(value)
        return value

    def keyboard_files(self):
        result = {}
        for path, owner in ((Path('/etc/arctic/mango/keyboard.conf'), 0),
                            (Path(self.user.pw_dir) / '.config/arctic/live-keyboard.conf', self.uid)):
            info = path.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid == owner and not info.st_mode & 0o022,
                    'live keyboard file protection differs')
            data = read_regular(path, 16384)
            fields = dict(line.split('=', 1) for line in data.decode().splitlines()
                          if '=' in line and not line.startswith('#'))
            require(fields.get('xkb_rules_layout') == 'us,il'
                    and fields.get('xkb_rules_options') == 'grp:alt_shift_toggle'
                    and not fields.get('xkb_rules_variant'), 'actual live Hebrew configuration differs')
            result[str(path)] = dict(bytes=len(data), sha256=sha(data), uid=owner,
                                     mode=stat.S_IMODE(info.st_mode))
        # The autosave callback starts a finite live-keyboard helper. Do not
        # take the baseline while it can still reload the compositor config.
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                argv = (proc / 'cmdline').read_bytes().split(b'\0')
                require(not (proc.stat().st_uid == self.uid and b'/usr/libexec/arctic/live-keyboard' in argv),
                        'live-keyboard helper has not completed')
            except (FileNotFoundError, ProcessLookupError):
                pass
        return result

    def drm_heads(self):
        # A single isolated virtio GPU initializes scanouts in index order.
        # Linux DRM virtual connector numbering therefore binds Virtual-1/2
        # to scanout head 0/1. Bind Mango's open DRM devices before requiring
        # one card; reject renamed/extra connectors or missing kernel evidence.
        compositor_devices = mango_drm_devices(self.uid, self.session)
        cards = sorted(p for p in Path('/sys/class/drm').glob('card*')
                       if re.fullmatch('card[0-9]+', p.name) and
                       (p / 'device').resolve(strict=True) in compositor_devices)
        require(len(cards) == 1, 'QEMU head binding requires exactly one actual DRM card')
        card = cards[0]
        device = (card / 'device').resolve(strict=True)
        pci = [p for p in (device, *device.parents)
               if re.fullmatch(r'[0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}\.[0-7]', p.name)]
        require(len(pci) == 1, 'virtio GPU PCI device binding is absent or ambiguous')
        pci = pci[0]
        vendor = (pci / 'vendor').read_text().strip()
        pci_id = (pci / 'device').read_text().strip()
        require(vendor == '0x1af4' and pci_id == '0x1050', 'actual PCI device is not the isolated QEMU virtio GPU')
        require(device == pci and (device / 'driver').resolve(strict=True).name == 'virtio-pci',
                'actual DRM PCI transport is not virtio-pci')
        children = [p for p in device.glob('virtio*') if re.fullmatch('virtio[0-9]+', p.name)
                    and p.resolve(strict=True).parent == device
                    and (p / 'driver').resolve(strict=True).name == 'virtio_gpu']
        require(len(children) == 1, 'actual DRM device is not virtio_gpu')
        require(int((children[0] / 'device').read_text().strip(), 16) == 16,
                'actual DRM virtio child is not GPU')
        driver = (children[0] / 'driver').resolve(strict=True)
        connectors = sorted(p for p in Path('/sys/class/drm').glob(card.name + '-*') if p.is_dir())
        require({p.name for p in connectors} == {card.name + '-Virtual-1', card.name + '-Virtual-2'},
                'actual DRM virtual connector inventory differs from exact two-head contract')
        result = {}
        for head, name in enumerate(('Virtual-1', 'Virtual-2')):
            connector = next(p for p in connectors if p.name == card.name + '-' + name)
            canonical = connector.resolve(strict=True)
            require(card.resolve(strict=True) in canonical.parents, 'DRM connector belongs to another card')
            connector_id = (connector / 'connector_id').read_text().strip()
            require(connector_id.isdigit() and int(connector_id) > 0, 'actual DRM connector ID absent')
            result[name] = dict(head=head, connector=connector.name, connector_id=int(connector_id),
                                sysfs_path=str(canonical))
        return dict(card=card.name, device=str(device), driver=str(driver), pci_address=pci.name,
                    pci_vendor=vendor, pci_device=pci_id, outputs=result,
                    binding='single Linux virtio_gpu scanout index order; Virtual-1=0, Virtual-2=1')

    def packaged_sources(self):
        result = {}
        for name in ('shell.qml', 'Engine.qml', 'Wizard.qml', 'Frame.qml', 'steps/KeyboardStep.qml'):
            path = Path(GUI_PATH) / name
            data = read_regular(path, root_owned=True)
            result[str(path)] = dict(bytes=len(data), sha256=sha(data))
        path = Path('/usr/bin/arctic-installer')
        data = read_regular(path, 16384, root_owned=True)
        require(b'exec quickshell -p /usr/share/arctic/installer-ui' in data,
                'packaged installer entry point differs')
        result[str(path)] = dict(bytes=len(data), sha256=sha(data))
        return result

    def prepare(self):
        self.find_gui()
        current = strict_json(self.ipc('state'))
        require(current.get('page') == current.get('current') == 'welcome'
                and current.get('ready') is True and current.get('connected') is True,
                'auto-opened installer must already be ready at welcome')
        # Verify the actual root service before connecting: the observer must
        # not become the component that starts a missing installer daemon.
        self.identities()
        self.rpc = EngineRPC()
        initial_engine = self.rpc.snapshot()
        require(initial_engine['wizard']['current'] == 'welcome', 'initial actual engine page differs')
        require(self.ipc('next') == 'ok', 'real welcome Next failed')
        def keyboard_ready():
            state = strict_json(self.ipc('state'))
            return (state.get('page') == state.get('current') == 'keyboard'
                    and state.get('ready') is True)
        self.wait(keyboard_ready, 15,
                  'real keyboard page did not load')
        require(self.ipc('fill', {'layout': 'il', 'variant': ''}) == 'ok', 'real Hebrew choice failed')
        def settled():
            state = strict_json(self.ipc('state'))
            require(state.get('keyboard') == 'il', 'GUI Hebrew autosave has not completed')
            engine = validate_engine_snapshot(self.rpc.snapshot())
            configs = self.keyboard_files()
            outputs = self.outputs()
            layers = strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
            visible = window_proof(state, layers, outputs)
            return dict(engine=engine, identities=self.identities(), keyboard_files=configs,
                        gui_log_counts=engine_log_counts(), state=state, outputs=outputs,
                        visible=visible)
        self.baseline = self.wait(settled, 25, 'actual Hebrew keyboard baseline did not settle')
        self.baseline['capture'] = self.capture('baseline', self.baseline['visible'])
        self.baseline['initial_wizard'] = initial_engine['wizard']
        self.baseline['rpc_peer'] = self.rpc.peer
        self.baseline['drm_heads'] = self.drm_heads()
        self.baseline['packaged_sources'] = self.packaged_sources()
        self.baseline['scope'] = 'prepared Hebrew keyboard baseline; no claim of resetting pre-test wizard flags'
        return self.baseline

    def unchanged(self):
        identities = self.identities()
        require(identities == self.baseline['identities'], 'original engine or GUI process was replaced')
        engine = validate_engine_snapshot(self.rpc.snapshot(), self.baseline['engine'])
        require(self.drm_heads() == self.baseline['drm_heads'], 'actual DRM/head binding changed')
        require(self.packaged_sources() == self.baseline['packaged_sources'], 'shipped GUI files changed')
        keyboard = self.keyboard_files()
        require(keyboard == self.baseline['keyboard_files'], 'live Hebrew configuration changed')
        logs = engine_log_counts()
        require(logs == self.baseline['gui_log_counts'], 'real GUI engine connection changed')
        return dict(engine=engine, identities=identities, keyboard_files=keyboard, gui_log_counts=logs)

    def capture(self, label, visible):
        from PIL import Image, ImageColor
        require(re.fullmatch('(baseline|(?:vt|output)-[0-2]|output-[02]-relocated)', label), 'invalid capture label')
        raw = self.root / 'physical-capture.ppm'
        require(not raw.exists() and not raw.is_symlink(), 'raw capture target already exists')
        png = self.root / (label + '.png')
        self.command(['/run/t/raw-screencopy', visible['window']['screen'], str(raw)], desktop=True, timeout=12)
        try:
            require(raw.is_file() and not raw.is_symlink() and raw.stat().st_uid == self.uid
                    and 0 < raw.stat().st_size < 64 * 1024 * 1024, 'invalid native physical capture')
            with Image.open(raw) as image:
                require(list(image.size) == visible['physical_size'], 'physical capture dimensions differ')
                rgb = image.convert('RGB')
                expected = list(ImageColor.getrgb(visible['window']['background'])[:3])
                x, y = rgb.width - 10, rgb.height // 2
                pixels = [list(rgb.getpixel((xx, yy))) for yy in range(y - 1, y + 2)
                          for xx in range(x - 1, x + 2)]
                require(all(max(abs(a - b) for a, b in zip(pixel, expected)) <= 3 for pixel in pixels),
                        'actual installer background pixels are absent')
                image.save(png)
            data = read_regular(png)
            require(0 < len(data) <= MAX_FILE, 'installer PNG exceeded bound')
            self.capture_count += 1
            return dict(path=png.name, bytes=len(data), sha256=sha(data), size=visible['physical_size'],
                        background=expected, pixels=pixels, region=[x - 1, y - 1, x + 2, y + 2], tolerance=3)
        finally:
            raw.unlink(missing_ok=True)

    def request(self, kind, cycle, **fields):
        require(kind in ('vt-away', 'output-disconnect', 'output-restore')
                and type(cycle) is int and 0 <= cycle < 3, 'invalid installer host request')
        value = dict(schema='arctic-installer-request-v1', kind=kind, binding_id=self.context['binding_id'],
                     boot_id=self.boot_id, cycle=cycle, **fields)
        self.request_emit('REQUEST', value)
        return value

    def verify(self, kind, cycle, disruption):
        self.active_session(True)
        unchanged = self.unchanged()
        state = strict_json(self.ipc('state'))
        outputs = self.outputs()
        layers = strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
        visible = window_proof(state, layers, outputs)
        return dict(kind=kind, cycle=cycle, status='passed', **unchanged, state=state,
                    outputs=outputs, visible=visible, disruption=disruption,
                    capture=self.capture(kind + '-' + str(cycle), visible))

    def vt_cycle(self, cycle):
        self.unchanged()
        away, stable, request = None, None, None
        try:
            self.command(['chvt', '6'])
            def inactive():
                proof = self.active_session(False)
                require(proof['foreground'] == 'tty6', 'actual VT6 is not foreground')
                return proof
            away = self.wait(inactive, 15, 'actual desktop did not deactivate on VT6')
            stable = self.unchanged()
            request = self.request('vt-away', cycle, away=away, original_vt=self.original_vt,
                                   engine_sha256=sha(json.dumps(stable['engine'], sort_keys=True).encode()))
            time.sleep(3)  # Host captures the independently observed away-VT display.
        finally:
            # Return to the discovered live VT even if away-state observation,
            # request emission, a signal, or the host capture fails.
            self.native.execute(['chvt', str(self.original_vt)], timeout=8)
        return self.wait(lambda: self.verify('vt', cycle, dict(away=away, prepared_state=stable, request=request, returned_vt=self.original_vt)),
                         25, 'same real installer did not restore after VT6')

    def output_cycle(self, cycle):
        self.active_session(True)
        before = self.unchanged()
        outputs = self.outputs()
        require(len(enabled_outputs(outputs)) == 2, 'two real outputs absent before disconnect')
        state = strict_json(self.ipc('state'))
        layers = strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
        hosting = window_proof(state, layers, outputs)['window']['screen']
        mode = 'all' if cycle == 1 else 'hosting-only'
        heads = self.drm_heads()
        require(hosting in heads['outputs'], 'actual hosting output lacks a proved QEMU head')
        names = sorted(o['name'] for o in enabled_outputs(outputs))
        common = dict(mode=mode, hosting_output=hosting, hosting_head=heads['outputs'][hosting]['head'],
                      enabled_outputs=names)
        disconnect = self.request('output-disconnect', cycle, **common,
                                  engine_sha256=sha(json.dumps(before['engine'], sort_keys=True).encode()))
        def absent():
            actual = self.outputs()
            available = enabled_outputs(actual)
            stable = self.unchanged()
            current = strict_json(self.ipc('state'))
            mapped = strict_json(self.command(['mmsg', 'get', 'all-layers'], desktop=True)[1])['layers']
            installers = [l for l in mapped if l.get('name') == 'arctic-installer']
            if mode == 'all':
                require(len(available) == 0 and not installers,
                        'host has not disconnected all real outputs/installer layers')
                return dict(outputs=actual, enabled_output_count=0, state=current, installer_layers=[], **stable)
            require(len(available) == 1 and available[0]['name'] != hosting
                    and available[0]['name'] in names, 'hosting output has not disappeared alone')
            visible = window_proof(current, mapped, actual, expected_count=1)
            require(visible['window']['screen'] != hosting, 'installer did not relocate after hosting output loss')
            return dict(outputs=actual, enabled_output_count=1, state=current, visible=visible,
                        capture=self.capture('output-' + str(cycle) + '-relocated', visible), **stable)
        unavailable = self.wait(absent, 35, 'actual hosting/all-output loss was not observed')
        restore = self.request('output-restore', cycle, **common,
                               enabled_output_count=unavailable['enabled_output_count'], outputs=unavailable['outputs'],
                               outputs_sha256=sha(json.dumps(unavailable['outputs'], sort_keys=True).encode()),
                               engine_sha256=sha(json.dumps(unavailable['engine'], sort_keys=True).encode()))
        return self.wait(lambda: self.verify('output', cycle,
                         dict(mode=mode, hosting_output=hosting, hosting_head=common['hosting_head'],
                              disconnect_request=disconnect, unavailable=unavailable, restore_request=restore)),
                         35, 'same real installer did not restore after hosting/all-output loss')

    def cleanup(self):
        # Attempt independent cleanup stages even if returning the VT fails.
        # Nothing ever terminates/restarts the root engine.
        self.deadline = max(self.deadline, time.monotonic() + 45)
        value = dict(original_vt_restored=False, owned_gui_stopped=False, owned_bridge_stopped=False,
                     engine_retained=False, pretest_wizard_reset_claim=False, errors=[])
        try:
            self.native.execute(['chvt', str(self.original_vt)], timeout=8)
            returned = self.wait(lambda: self.active_session(True), 8, 'original live VT was not returned')
            require(returned['foreground'] == 'tty' + str(self.original_vt), 'cleanup foreground VT differs')
            value['original_vt_restored'] = True
        except BaseException as exc:
            value['errors'].append('VT return: ' + type(exc).__name__ + ': ' + str(exc)[:500])
        if self.baseline is None or self.gui_fd is None:
            value['errors'].append('prepared keyboard baseline/owned pidfd unavailable; GUI not terminated')
            return value
        try:
            validate_engine_snapshot(self.rpc.snapshot(), self.baseline['engine'])
            state = strict_json(self.ipc('state'))
            require(state.get('page') == state.get('current') == 'keyboard'
                    and state.get('keyboard') == 'il' and state.get('busy') is False
                    and state.get('connected') is True, 'refuse to terminate GUI outside owned prepared keyboard')
            self.assert_gui_identity()
            bridge, _ = process_proof(self.bridge_pid, self.uid, '/usr/bin/arctic-install')
            require(bridge == self.initial_bridge, 'refuse to stop GUI with a replaced bridge')
            signal.pidfd_send_signal(self.gui_fd, signal.SIGTERM)
            def stopped(pid, proof):
                try:
                    proc = Path('/proc') / str(pid)
                    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
                    require(proc.stat().st_uid == self.uid and int(fields[19]) == proof['start_ticks'],
                            'owned cleanup PID was reused')
                    if fields[0] in ('Z', 'X'):
                        return True
                    require(str((proc / 'exe').resolve(strict=True)) == proof['executable'],
                            'owned cleanup process executable changed')
                    return False
                except (FileNotFoundError, ProcessLookupError):
                    return True
            self.wait(lambda: stopped(self.gui_pid, self.initial_gui), 8, 'owned installer GUI did not stop')
            value['owned_gui_stopped'] = True
            self.wait(lambda: stopped(self.bridge_pid, self.initial_bridge), 8, 'owned GUI bridge did not stop')
            value['owned_bridge_stopped'] = True
        except BaseException as exc:
            value['errors'].append('owned GUI shutdown: ' + type(exc).__name__ + ': ' + str(exc)[:500])
        try:
            # The socket-activated engine deliberately survives its last client.
            snapshot = validate_engine_snapshot(self.rpc.snapshot(), self.baseline['engine'])
            daemon, _ = process_proof(self.baseline['identities']['daemon']['pid'], 0, '/usr/bin/arcticd')
            require(daemon == self.baseline['identities']['daemon'], 'root engine changed after owned GUI closed')
            require(listener_proof(daemon['pid']) == self.baseline['identities']['listener'],
                    'root engine listener changed after owned GUI closed')
            value['engine_retained'] = True
            value['engine_snapshot_sha256'] = sha(json.dumps(snapshot, sort_keys=True).encode())
        except BaseException as exc:
            value['errors'].append('retained root engine: ' + type(exc).__name__ + ': ' + str(exc)[:500])
        return value

    def run(self):
        report = dict(schema=SCHEMA, stage='live', status='failed', context=self.context,
                      boot_id=self.boot_id, desktop_uid=self.uid, active_desktop_session=self.session,
                      original_vt=self.original_vt, release_acceptance=False, evidence_root=str(self.root),
                      cases=self.results)
        security = None
        errors = []
        try:
            security = self.native.SecurityInterval()
            report['baseline'] = self.prepare()
            for cycle in range(3):
                self.results.append(self.vt_cycle(cycle))
            for cycle in range(3):
                self.results.append(self.output_cycle(cycle))
        except BaseException as exc:
            errors.append(type(exc).__name__ + ': ' + str(exc)[:2000])
        finally:
            try:
                report['cleanup'] = self.cleanup()
                errors.extend('cleanup: ' + e for e in report['cleanup']['errors'])
            except BaseException as exc:
                errors.append('cleanup: ' + type(exc).__name__ + ': ' + str(exc)[:2000])
            try:
                require(security is not None, 'security interval was not initialized')
                report['security'] = security.finish()
            except BaseException as exc:
                errors.append('security: ' + type(exc).__name__ + ': ' + str(exc)[:2000])
            try:
                if self.rpc is not None:
                    self.rpc.close()
            except BaseException as exc:
                errors.append('RPC close: ' + type(exc).__name__)
            finally:
                try:
                    if self.gui_fd is not None:
                        os.close(self.gui_fd)
                except BaseException as exc:
                    errors.append('pidfd close: ' + type(exc).__name__)
        report['errors'] = errors
        report['captures'] = self.capture_count
        expected = {(kind, cycle) for kind in ('vt', 'output') for cycle in range(3)}
        passed = (not errors and len(self.results) == 6
                  and {(c['kind'], c['cycle']) for c in self.results} == expected
                  and all(c['status'] == 'passed' for c in self.results) and self.capture_count == 9
                  and all(report.get('cleanup', {}).get(k) is True for k in
                          ('original_vt_restored', 'owned_gui_stopped', 'owned_bridge_stopped', 'engine_retained')))
        report['status'] = 'passed' if passed else 'failed'
        (self.root / 'installer-report.json').write_text(json.dumps(report, sort_keys=True, allow_nan=False) + '\n')
        return report


def inventory(root, uid, transport):
    root = Path(root)
    require(root.parent == Path('/tmp') and re.fullmatch('arctic-native-smoke-installer-[A-Za-z0-9_-]+', root.name)
            and root.is_dir() and not root.is_symlink() and root.resolve() == root
            and root.stat().st_uid == uid, 'unproved installer evidence root')
    files, total = [], 0
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode), 'installer evidence contains a directory, link, or special file')
        if path == root / 'physical-capture.ppm':
            continue
        require(path.suffix in {'.png', '.json'} and len(files) < MAX_FILES,
                'unexpected or excessive installer evidence files')
        data = transport.read_regular(path, MAX_FILE)
        total += len(data)
        require(total <= MAX_TOTAL, 'installer aggregate evidence exceeded bound')
        files.append((path.name, data))
    require(any(name == 'installer-report.json' for name, _ in files), 'installer report missing')
    return files, total


def export(root, uid, binding_id, transport, stream):
    # Same reviewed zlib/chunk bounds as taskbar transport, with installer
    # schema and report name. Validate all files before emitting any archive.
    files, total = inventory(root, uid, transport)
    entries = []
    for name, data in files:
        compressed = zlib.compress(data, 9)
        parts = [compressed[i:i + CHUNK] for i in range(0, len(compressed), CHUNK)]
        entries.append(dict(path=name, bytes=len(data), sha256=sha(data), compressed_bytes=len(compressed),
                            chunks=len(parts), encoding='zlib+base64'))
        for index, part in enumerate(parts):
            emit('EVIDENCE-CHUNK', dict(binding_id=binding_id, path=name, index=index,
                                      data=base64.b64encode(part).decode('ascii')), stream)
    emit('EVIDENCE-MANIFEST', dict(schema='arctic-installer-evidence-v1', binding_id=binding_id,
                                 evidence_root=str(root), files=entries, bytes=total), stream)


def load_checked(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-guest', action='store_true', required=True)
    args = parser.parse_args(argv)
    require(os.geteuid() == 0 and args.disposable_guest, 'requires explicit disposable root guest')
    require(Path(__file__).absolute() == Path('/run/t/installer-guest.py')
            and Path(__file__).resolve() == Path('/run/t/installer-guest.py'), 'reviewed CD checker path differs')
    context = validate_context(strict_json(read_regular('/run/t/installer-context.json', 16384, True)))
    active = context['schema'] == 'arctic-installer-active-context-v1'
    timeout = 55 * 60 if active else TIMEOUT
    overall_deadline = time.monotonic() + timeout
    for name, key in BUNDLE.items():
        require(sha(read_regular(Path('/run/t') / name, 32 * 1024 * 1024, True)) == context[key],
                'reviewed installer bundle hash differs: ' + name)
    require(os.access('/run/t/raw-screencopy', os.X_OK), 'reviewed native capture is not executable')
    transport = load_checked('/run/t/taskbar-runtime.py', 'installer_reviewed_transport')
    native = load_checked('/run/t/native_smoke.py', 'installer_reviewed_native')
    native.guest_guard('live', True)
    require('arctic.mode=install' in Path('/proc/cmdline').read_text().split(), 'actual installer boot mode differs')
    if active:
        require(sha(read_regular('/run/t/installer-active.py', root_owned=True)) == context['active_checker_sha256']
                and sha(read_regular('/run/t/installed-guest.py', root_owned=True)) == context['installed_checker_sha256'],
                'active fixture checker bytes differ')
        active_module = load_checked('/run/t/installer-active.py', 'reviewed_active_installer')
        collector = active_module.installer_type(sys.modules[__name__])(native, context)
    else:
        collector = Installer(native, context)
    collector.deadline = min(collector.deadline, overall_deadline - 120)
    require(time.monotonic() < collector.deadline, 'installer bootstrap exhausted the overall budget')
    identity = dict(boot_id=collector.boot_id, desktop_uid=collector.uid,
                    active_desktop_session=collector.session)
    transport.PORT_NAME = PORT_NAME
    transport.TIMEOUT = timeout
    transport.emit = emit
    port, port_proof = transport.open_port()
    port_proof['schema'] = 'arctic-installer-virtio-port-v1'
    port.deadline = overall_deadline
    provenance = dict(schema='arctic-installer-provenance-v1', stage='live', context=context,
                      **identity, cmdline=Path('/proc/cmdline').read_text().strip(),
                      virtualization=native.execute(['systemd-detect-virt'], timeout=8)[1],
                      transport=port_proof, release_acceptance=False)
    emit('BEGIN', dict(schema='arctic-installer-runner-v1', stage='live', context=context,
                       **identity, transport=port_proof, release_acceptance=False), port)
    emit('PROVENANCE', provenance, port)
    cancelled = False
    def interrupted(signum, _):
        nonlocal cancelled
        if not cancelled:
            cancelled = True
            raise InterruptedError('bounded installer collector interrupted by signal ' + str(signum))
    handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)}
    signal.alarm(max(1, int(overall_deadline - time.monotonic())))
    report, error, complete, passed = None, None, False, False
    try:
        report = collector.run()
        emit('REPORT', report, port)
        export(collector.root, collector.uid, context['binding_id'], transport, port)
        complete = True
        passed = report['status'] == 'passed' and not cancelled
        if not passed:
            error = 'live installer checks, security, or cleanup failed'
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)[:2000]
    finally:
        signal.alarm(0)
        try:
            end = dict(binding_id=context['binding_id'], **identity, status='passed' if passed else 'failed',
                       error=error, evidence_export_complete=complete, release_acceptance=False)
            emit('END', end, port)
            emit('PORT-END', dict(schema='arctic-installer-port-end-v1', binding_id=context['binding_id'], **identity,
                                 status=end['status'], release_acceptance=False,
                                 end_sha256=sha(json.dumps(end, sort_keys=True, allow_nan=False).encode('ascii'))))
        finally:
            try:
                port.close()
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('ARCTIC-INSTALLER-COLLECTOR-ERROR', flush=True)
        raise SystemExit(1)
