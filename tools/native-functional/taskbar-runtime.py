#!/usr/bin/env python3
"""Bounded test-CD taskbar collector; importing this file never runs a guest test."""
import argparse
import base64
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import pwd
import re
import select
import signal
import stat
import sys
import time
import zlib

MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 128 * 1024 * 1024
MAX_FILES = 512
CHUNK = 18 * 1024  # Base64 text is at most 24 KiB, excluding the JSON envelope.
TIMEOUT = 1800
FIELDS = {'schema', 'source_sha', 'iso_sha256', 'iso_bytes', 'execution_sha', 'token',
          'checker_sha256', 'runtime_sha256', 'native_sha256', 'pointer_sha256', 'capture_sha256'}
BUNDLE = {'taskbar.py': 'checker_sha256', 'taskbar-runtime.py': 'runtime_sha256',
          'native_smoke.py': 'native_sha256', 'virtual-pointer': 'pointer_sha256',
          'raw-screencopy': 'capture_sha256'}
PORT_NAME = 'arctic-taskbar-evidence'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate JSON key')
            result[key] = value
        return result
    def constant(_):
        raise RuntimeError('nonfinite JSON number')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def validate_context(value):
    require(type(value) is dict and set(value) == FIELDS
            and value['schema'] == 'arctic-taskbar-context-v1', 'taskbar context schema differs')
    for key in FIELDS - {'schema', 'iso_bytes', 'source_sha', 'execution_sha', 'token'}:
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{64}', value[key]),
                'taskbar SHA-256 differs: ' + key)
    for key in ('source_sha', 'execution_sha'):
        require(type(value[key]) is str and re.fullmatch('[0-9a-f]{40}', value[key]),
                'taskbar commit differs: ' + key)
    require(type(value['token']) is str and re.fullmatch('[0-9a-f]{32}', value['token']),
            'taskbar execution token differs')
    require(type(value['iso_bytes']) is int and 0 < value['iso_bytes'] < 2_000_000_000,
            'taskbar exact-image size differs')
    return value


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_regular(path, limit=MAX_FILE, root_owned=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
                'taskbar file is nonregular or oversized')
        require(not root_owned or (info.st_uid == 0 and not info.st_mode & 0o022),
                'taskbar bundle is not protected root-owned content')
        data = bytearray()
        while len(data) <= limit:
            part = os.read(fd, min(65536, limit + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        after = os.fstat(fd)
        require(len(data) == info.st_size and len(data) <= limit
                and (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                'taskbar file changed while being read')
        return bytes(data)
    finally:
        os.close(fd)


class PortWriter:
    """Write the bounded stream without an unbounded blocking device write."""
    def __init__(self, fd):
        self.fd = fd
        self.deadline = time.monotonic() + TIMEOUT + 600
        self.bytes = 0

    def write(self, text):
        data = text.encode('ascii')
        self.bytes += len(data)
        require(self.bytes <= 210 * 1024 * 1024, 'taskbar wire byte bound exceeded')
        deadline = min(self.deadline, time.monotonic() + 60)
        view = memoryview(data)
        while view:
            require(time.monotonic() < deadline, 'taskbar virtio write timed out')
            try:
                count = os.write(self.fd, view)
                require(count > 0, 'taskbar virtio device disconnected')
                view = view[count:]
            except BlockingIOError:
                require(select.select([], [self.fd], [], max(0, deadline-time.monotonic()))[1],
                        'taskbar virtio write timed out')
        return len(text)

    def flush(self):
        pass  # Unbuffered os.write; END is written before the UART completion receipt.

    def close(self):
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


def open_port():
    alias = Path('/dev/virtio-ports') / PORT_NAME
    canonical = alias.resolve(strict=True)
    require(canonical.parent == Path('/dev') and re.fullmatch('vport[0-9]+p[0-9]+', canonical.name),
            'taskbar named virtio port resolves outside the canonical device namespace')
    attrs = Path('/sys/class/virtio-ports') / canonical.name
    # Sysfs class entries are kernel-owned symlinks; their attributes bind the
    # named channel to the exact opened device, rather than trusting a dev alias.
    for path in (alias.parent, attrs / 'name', attrs / 'dev'):
        info = path.stat()
        require(info.st_uid == 0 and not info.st_mode & 0o022, 'taskbar device/sysfs metadata is unprotected')
    name = (attrs / 'name').read_text().strip()
    device = (attrs / 'dev').read_text().strip()
    require(name == PORT_NAME and re.fullmatch('[0-9]{1,5}:[0-9]{1,5}', device),
            'taskbar sysfs channel name/device differs')
    major, minor = (int(v) for v in device.split(':'))
    fd = os.open(canonical, os.O_WRONLY | os.O_NOFOLLOW | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and (os.major(info.st_rdev), os.minor(info.st_rdev)) == (major, minor),
                'taskbar virtio device type/owner/protection/sysfs identity differs')
        receipt = dict(schema='arctic-taskbar-virtio-port-v1', name=PORT_NAME, device=str(canonical),
                       major=major, minor=minor, uid=info.st_uid, mode=stat.S_IMODE(info.st_mode))
        return PortWriter(fd), receipt
    except BaseException:
        os.close(fd)
        raise


def emit(kind, value, stream=None):
    print('ARCTIC-TASKBAR-' + kind + ' ' + json.dumps(value, sort_keys=True, allow_nan=False),
          file=stream if stream is not None else sys.stdout, flush=True)


def inventory(root, uid):
    root = Path(root)
    require(root.parent == Path('/tmp') and re.fullmatch('arctic-native-smoke-[A-Za-z0-9_-]+', root.name)
            and root.is_dir() and not root.is_symlink() and root.resolve() == root
            and root.stat().st_uid == uid, 'unproved taskbar evidence root')
    files, total = [], 0
    for path in sorted(root.rglob('*')):
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode),
                'taskbar evidence contains a symlink or special file')
        if stat.S_ISDIR(info.st_mode):
            continue
        # An interrupted raw screencopy may leave its private, unconverted PPM.
        # It is not a report reference or part of the bounded public PNG archive.
        if path == root / 'physical-capture.ppm':
            continue
        require(path.suffix in {'.png', '.json', '.log'}, 'unexpected taskbar evidence file type')
        require(len(files) < MAX_FILES, 'taskbar file count exceeds bound')
        data = read_regular(path)
        total += len(data)
        require(total <= MAX_TOTAL, 'taskbar aggregate evidence exceeds bound')
        files.append((path.relative_to(root).as_posix(), data))
    require(any(name == 'taskbar-report.json' for name, _ in files), 'taskbar report file missing')
    return files, total


def export(root, uid, token, stream=None):
    files, total = inventory(root, uid)  # Check every bound before emitting a partial archive.
    entries = []
    for name, data in files:
        compressed = zlib.compress(data, 9)
        parts = [compressed[i:i + CHUNK] for i in range(0, len(compressed), CHUNK)]
        entries.append(dict(path=name, bytes=len(data), sha256=digest(data),
                            compressed_bytes=len(compressed), chunks=len(parts), encoding='zlib+base64'))
        for index, part in enumerate(parts):
            emit('EVIDENCE-CHUNK', dict(token=token, path=name, index=index,
                                      data=base64.b64encode(part).decode('ascii')), stream)
    emit('EVIDENCE-MANIFEST', dict(schema='arctic-taskbar-evidence-v1', token=token,
                                 evidence_root=str(root), files=entries, bytes=total), stream)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-guest', action='store_true', required=True)
    args = parser.parse_args(argv)
    require(Path(__file__).absolute() == Path('/run/t/taskbar-runtime.py')
            and Path(__file__).resolve() == Path('/run/t/taskbar-runtime.py'),
            'requires the reviewed /run/t/taskbar-runtime.py bundle')
    require(os.geteuid() == 0 and args.disposable_guest, 'requires explicit disposable root guest')
    context = validate_context(strict_json(read_regular('/run/t/taskbar-context.json', 16384, True)))
    for name, key in BUNDLE.items():
        require(digest(read_regular(Path('/run/t') / name, root_owned=True)) == context[key],
                'taskbar reviewed bundle hash differs: ' + name)
    require(all(os.access('/run/t/' + name, os.X_OK) for name in ('virtual-pointer', 'raw-screencopy')),
            'taskbar native helper is not executable')
    sys.path.insert(0, '/run/t')
    import native_smoke as native
    native.guest_guard('installed', True)
    prefix = native.discover_desktop()
    uid = pwd.getpwnam(prefix[2]).pw_uid
    sessions = [x.split('=', 1)[1] for x in prefix if x.startswith('XDG_SESSION_ID=')]
    require(len(sessions) == 1 and bool(sessions[0]), 'actual desktop session missing')
    session = sessions[0]
    for key, expected in (('Type', 'wayland'), ('Active', 'yes'), ('User', str(uid))):
        require(native.execute(['loginctl', 'show-session', session, '-p', key, '--value'])[1] == expected,
                'actual desktop session identity differs')
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    require(re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot_id), 'boot ID differs')
    identity = dict(boot_id=boot_id, desktop_uid=uid, active_desktop_session=session)
    port, transport = open_port()  # No guest fallback to the slow UART evidence path.
    emit('BEGIN', dict(schema='arctic-taskbar-runner-v1', stage='installed', context=context,
                       **identity, transport=transport, release_acceptance=False), port)
    emit('PROVENANCE', dict(schema='arctic-taskbar-provenance-v1', stage='installed',
                            context=context, **identity, cmdline=Path('/proc/cmdline').read_text().strip(),
                            virtualization=native.execute(['systemd-detect-virt'])[1],
                            transport=transport, release_acceptance=False), port)
    report, error, complete = None, None, False
    original_roots = set(Path('/tmp').glob('arctic-native-smoke-*'))
    cancelled = False
    def interrupted(signum, _):
        nonlocal cancelled
        # The unchanged helper restores its owned desktop in finally. A second
        # interrupt must not interrupt that bounded restoration.
        if not cancelled:
            cancelled = True
            signal.alarm(0)
            raise InterruptedError('bounded taskbar collector interrupted by signal ' + str(signum))
    handlers = {s: signal.signal(s, interrupted) for s in (signal.SIGALRM, signal.SIGTERM, signal.SIGINT)}
    signal.alarm(TIMEOUT)
    try:
        spec = importlib.util.spec_from_file_location('taskbar_installed_checked', '/run/t/taskbar.py')
        helper = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        # The unchanged helper prints its report; transport emits one separate authenticated report record.
        with contextlib.redirect_stdout(io.StringIO()):
            report = helper.run_checks(prefix, Path('/run/t/virtual-pointer'), Path('/run/t/raw-screencopy'),
                                       disposable_guest=True)
        emit('REPORT', report, port)
        if report.get('status') != 'passed':
            error = 'installed taskbar checks or restoration failed'
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)[:2000]
    finally:
        signal.alarm(0)
        # Defer a second interrupt until bounded export is complete; preserve failure evidence.
        mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try:
            try:
                roots = {Path(report['evidence_root'])} if report is not None else (
                    set(Path('/tmp').glob('arctic-native-smoke-*')) - original_roots)
                require(len(roots) == 1, 'ambiguous or absent taskbar evidence root')
                root = next(iter(roots))
                if report is None:
                    report = strict_json(read_regular(root / 'taskbar-report.json'))
                    emit('REPORT', report, port)
                export(root, uid, context['token'], port)
                complete = True
            except BaseException as exc:
                error = (error + '; ' if error else '') + 'evidence export: ' + type(exc).__name__ + ': ' + str(exc)[:2000]
            if signal.sigpending() & {signal.SIGTERM, signal.SIGINT}:
                error = (error + '; ' if error else '') + 'collector cancellation pending during export'
            passed = error is None and complete and report is not None and report.get('status') == 'passed'
            end = dict(token=context['token'], **identity, status='passed' if passed else 'failed',
                       error=error, evidence_export_complete=complete, release_acceptance=False)
            emit('END', end, port)
            emit('PORT-END', dict(schema='arctic-taskbar-port-end-v1', token=context['token'], **identity,
                                 status=end['status'], release_acceptance=False,
                                 end_sha256=digest(json.dumps(end, sort_keys=True, allow_nan=False).encode('ascii'))))
        finally:
            try:
                port.close()
            finally:
                for sig, handler in handlers.items():
                    signal.signal(sig, handler)
                signal.pthread_sigmask(signal.SIG_SETMASK, mask)
    return 0 if passed else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception:
        print('ARCTIC-TASKBAR-COLLECTOR-ERROR', flush=True)
        raise SystemExit(1)
