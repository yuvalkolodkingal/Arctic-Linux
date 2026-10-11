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

PAYLOAD = None  # HOST_COMPOSE_PINNED_PAYLOAD
MAX_REPORT = 16 * 1024 * 1024
PREFIX = 'ARCTIC-BROWSER-STARTUP-REPORT'
NAMES = {'profile.py', 'guest.py', 'causal.py', 'browser-startup-context.json'}


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
    if sys.argv[1:] == ['live']:
        print('ARCTIC-BROWSER-STARTUP-DIAGNOSTIC live_skipped', flush=True)
        return
    require(sys.argv[1:] == ['installed'] and os.geteuid() == 0)
    decoded = staged_payload(PAYLOAD)
    require(Path(__file__).parent == Path('/run/t'))
    require(subprocess.check_output(['systemd-detect-virt', '--vm'], text=True).strip() in ('qemu', 'kvm'))
    require(subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing')
    mounted = subprocess.check_output(['findmnt', '-n', '-o', 'FSTYPE,OPTIONS', '--target', '/run/t'],
                                      text=True).strip().split()
    require(len(mounted) == 2 and mounted[0] == 'iso9660' and 'ro' in mounted[1].split(','))
    acquired = False
    raw = None
    try:
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
        subprocess.run(['/usr/bin/python3', '-B', '/run/t/profile.py'], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=900)
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
            subprocess.run(['umount', '/run/t'], check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=15)
    require(subprocess.check_output(['getenforce'], text=True).strip() == 'Enforcing')
    emit_report(raw)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        # No app output, exception text, trace bytes or report fragment escapes.
        print('ARCTIC-BROWSER-STARTUP-DIAGNOSTIC transport_failed', flush=True)
        sys.exit(1)
