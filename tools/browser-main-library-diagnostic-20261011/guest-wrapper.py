#!/usr/bin/env python3
"""Transport only the pinned collector's finite report from an owned VM.

This template is disabled. The reviewed host composer inserts immutable bytes;
it does not alter the collector, browser or installed disk configuration.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import types

PAYLOAD = None  # HOST_COMPOSE_PINNED_PAYLOAD
MAX_REPORT = 16 * 1024 * 1024
PREFIX = 'ARCTIC-BROWSER-STARTUP-REPORT'
NAMES = {'profile.py', 'guest.py', 'causal.py', 'browser-startup-context.json'}
FAILURE_PREFIX = 'ARCTIC-BROWSER-STARTUP-FAILURE '
FAILURE_PHASES = frozenset(('unknown', 'arguments', 'payload', 'vm_security',
    'immutable_mount', 'staging', 'collector', 'report_binding', 'staging_cleanup',
    'post_security', 'report_emission'))
FAILURE_REASONS = frozenset(('guest_guard', 'command_failed', 'command_timeout',
    'os_error', 'interrupted', 'unclassified_exception'))
failure_phase = 'unknown'


def finite_guest_failure(error):
    reason = 'unclassified_exception'
    if type(error) is RuntimeError:
        trace = BaseException.__getattribute__(error, '__traceback__')
        for _ in range(64):
            if trace is None: break
            if trace.tb_frame.f_code is require.__code__: reason = 'guest_guard'
            trace = trace.tb_next
        if trace is not None: reason = 'unclassified_exception'
    elif type(error) is subprocess.CalledProcessError: reason = 'command_failed'
    elif type(error) is subprocess.TimeoutExpired: reason = 'command_timeout'
    elif type(error) in (KeyboardInterrupt, InterruptedError, SystemExit): reason = 'interrupted'
    elif isinstance(error, OSError): reason = 'os_error'
    return {'scope': 'guest', 'phase': failure_phase if type(failure_phase) is str and failure_phase in FAILURE_PHASES else 'unknown',
            'reason': reason}


def emit_finite_failure(value, profile=None):
    require(type(value) is dict and set(value) == {'scope', 'phase', 'reason'})
    require(all(type(item) is str for item in value.values()))
    if value['scope'] == 'guest':
        require(value['phase'] in FAILURE_PHASES and value['reason'] in FAILURE_REASONS)
    else:
        require(value['scope'] == 'collector')
        require((profile is None and value['phase'] == 'unknown' and value['reason'] == 'unclassified_exception')
                or (profile is not None and value['phase'] in profile.FAILURE_PHASES
                    and value['reason'] in profile.FAILURE_REASONS))
    print(FAILURE_PREFIX + value['scope'] + ' ' + value['phase'] + ' ' + value['reason'], flush=True)


def private_collector_failure(path, profile):
    """Only a validated finite marker can leave the private stderr file."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                and stat.S_IMODE(before.st_mode) == 0o600)
        if before.st_size > 4096: return None
        raw = stream.read(4097)
        after = os.fstat(stream.fileno())
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(identity(before) == identity(after) and len(raw) == before.st_size)
    return profile.parse_failure_marker(raw)


def invoke_collector(profile_bytes, checksum, private=Path('/run/arctic-browser-startup-private')):
    require(type(profile_bytes) is bytes and type(checksum) is str
            and hashlib.sha256(profile_bytes).hexdigest() == checksum)
    require(not private.exists() and not private.is_symlink())
    private.mkdir(mode=0o700)
    require(private.stat().st_uid == 0 and stat.S_IMODE(private.stat().st_mode) == 0o700)
    stderr = private / 'collector.stderr'
    fd = os.open(stderr, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as errors:
        try:
            subprocess.run(['/usr/bin/python3', '-B', '/run/t/profile.py'], check=True,
                           stdout=subprocess.DEVNULL, stderr=errors, timeout=900)
        except BaseException:
            value, profile = None, None
            try:
                # These already staged and byte-verified Source definitions are
                # loaded only after collection failed, never during measurement.
                profile = types.ModuleType('owned_failure_classifier')
                profile.__file__ = '/run/t/profile.py'
                exec(compile(profile_bytes, profile.__file__, 'exec'), profile.__dict__)
                value = private_collector_failure(stderr, profile)
            except BaseException:
                profile = None
            try:
                emit_finite_failure(value or {'scope': 'collector', 'phase': 'unknown', 'reason': 'unclassified_exception'}, profile)
            except BaseException:
                pass  # Preserve the original owned child failure, never its text.
            raise


def require(value):
    if not value:
        raise RuntimeError('owned_guest_transport')


def staged_payload(payload):
    require(type(payload) is dict and set(payload) == {'files', 'context', 'execution'})
    require(type(payload['files']) is dict and set(payload['files']) == NAMES)
    decoded = {}
    for name, pin in payload['files'].items():
        require(type(pin) is dict and set(pin) == {'base64', 'sha256', 'bytes'})
        raw = base64.b64decode(pin['base64'], validate=True)
        require(type(pin['bytes']) is int and 0 < pin['bytes'] <= 512 * 1024
                and len(raw) == pin['bytes']
                and hashlib.sha256(raw).hexdigest() == pin['sha256'])
        decoded[name] = raw
    context = json.loads(decoded['browser-startup-context.json'])
    require(context == payload['context'] and context['ready'] is True)
    require(context['modules'] == {name: payload['files'][name]['sha256']
                                  for name in ('guest.py', 'causal.py')})
    return decoded


def read_report(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0
                and stat.S_IMODE(before.st_mode) == 0o600 and 0 < before.st_size <= MAX_REPORT)
        raw = source.read(MAX_REPORT + 1)
        after = os.fstat(source.fileno())
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(after))
    return raw


def emit_report(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_REPORT)
    checksum = hashlib.sha256(raw).hexdigest()
    print(PREFIX + ' BEGIN ' + str(len(raw)) + ' ' + checksum, flush=True)
    encoded = base64.b64encode(raw).decode('ascii')
    for index, offset in enumerate(range(0, len(encoded), 1024)):
        print(PREFIX + ' DATA ' + str(index) + ' ' + encoded[offset:offset + 1024], flush=True)
    print(PREFIX + ' END ' + checksum, flush=True)


def main():
    global failure_phase
    if sys.argv[1:] == ['live']:
        print('ARCTIC-BROWSER-STARTUP-DIAGNOSTIC live_skipped', flush=True)
        return
    failure_phase = 'arguments'
    require(sys.argv[1:] == ['installed'] and os.geteuid() == 0)
    failure_phase = 'payload'
    decoded = staged_payload(PAYLOAD)
    failure_phase = 'vm_security'
    require(Path(__file__).parent == Path('/run/t'))
    require(subprocess.check_output(['systemd-detect-virt', '--vm'], text=True).strip() in ('qemu', 'kvm'))
    require(subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing')
    failure_phase = 'immutable_mount'
    mounted = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,OPTIONS', '--target', '/run/t'],
                                      text=True).strip().split()
    require(len(mounted) == 2 and mounted[0] == 'iso9660' and 'ro' in mounted[1].split(','))
    acquired = False
    raw = None
    try:
        failure_phase = 'staging'
        # Cover only the test CD mount with a private RAM filesystem. The CD,
        # installed root, user profile and security settings remain unchanged.
        subprocess.run(['mount', '-t', 'tmpfs', '-o', 'mode=0700,nosuid,nodev,noexec,size=2m',
                        'tmpfs', '/run/t'], check=True, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, timeout=15)
        acquired = True
        root = Path('/run/t')
        require(not root.is_symlink() and root.stat().st_uid == 0
                and stat.S_IMODE(root.stat().st_mode) == 0o700 and not list(root.iterdir()))
        actual = {}
        for name, body in decoded.items():
            path = root / name
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, 'wb') as output:
                output.write(body)
            info = path.stat()
            require(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o600
                    and path.read_bytes() == body and not path.is_symlink())
            actual[name] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest(),
                            'mode': '0600', 'uid': 0}
        failure_phase = 'collector'
        invoke_collector(decoded['profile.py'], PAYLOAD['files']['profile.py']['sha256'])
        failure_phase = 'report_binding'
        raw = read_report(Path('/run/arctic-browser-startup/report.json'))
        report = json.loads(raw)
        require(report['image'] == PAYLOAD['context']['image']
                and report['collector_sha256'] == actual['profile.py']['sha256']
                and report['modules'] == PAYLOAD['context']['modules'])
        report['diagnostic_execution'] = PAYLOAD['execution']
        report['staged_sources'] = actual
        raw = (json.dumps(report, sort_keys=True, allow_nan=False) + '\n').encode()
        require(len(raw) <= MAX_REPORT)
    finally:
        if acquired:
            original_phase = failure_phase
            failure_phase = 'staging_cleanup'
            subprocess.run(['umount', '/run/t'], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15)
            failure_phase = original_phase
    failure_phase = 'post_security'
    require(subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing')
    failure_phase = 'report_emission'
    emit_report(raw)


if __name__ == '__main__':
    try:
        main()
    except BaseException as error:
        # No app output, exception text, trace bytes or report fragment escapes.
        print('ARCTIC-BROWSER-STARTUP-DIAGNOSTIC transport_failed', flush=True)
        try:
            emit_finite_failure(finite_guest_failure(error))
        except BaseException:
            pass
        sys.exit(1)
