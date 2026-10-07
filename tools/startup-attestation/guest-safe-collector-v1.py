#!/usr/bin/env python3
"""Bounded, post-interaction read-only telemetry in one disposable Safe guest.

Only /tmp evidence is written. No package, setting, service, renderer or QML changes.
Importing this module never runs a collector or creates files.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys
import tempfile
import time
import zlib

MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
CHUNK = 24000
ENV_FIELDS = {'HOME', 'PATH', 'LANG', 'XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'DISPLAY',
              'DBUS_SESSION_BUS_ADDRESS', 'XDG_CONFIG_HOME', 'XDG_CACHE_HOME', 'XDG_STATE_HOME',
              'XDG_DATA_HOME', 'XDG_DATA_DIRS', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_ID',
              'XDG_SESSION_TYPE', 'XDG_SESSION_DESKTOP', 'XDG_VTNR', 'MANGO_INSTANCE_SIGNATURE',
              'ARCTIC_REDUCE_MOTION', 'ARCTIC_SHELL'}
MANGO_QUERIES = ('get version', 'get all-monitors', 'get all-clients', 'get all-layers')
AVC = re.compile(r'\bavc:\s*denied\b|\btype=(?:USER_)?AVC\b', re.I)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def emit(name, value):
    print('ARCTIC-SAFE-' + name + ' ' + json.dumps(value, sort_keys=True), flush=True)


def execute(argv, timeout=20, env=None, limit=MAX_FILE):
    result = subprocess.run(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(len(result.stdout) <= limit and len(result.stderr) <= 65536, 'Command output exceeds bound: ' + argv[0])
    require(result.returncode == 0, 'Command failed: ' + repr(argv) + ': ' + result.stderr.decode(errors='replace'))
    return result.stdout


def whitelisted_env(raw):
    return {k: v for k, v in raw.items() if k in ENV_FIELDS or k.startswith(('QT_', 'QSG_', 'WLR_', 'LIBGL_'))}


def process(pid):
    folder = Path('/proc') / str(pid)
    values = (folder / 'stat').read_text().rsplit(')', 1)[1].split()
    executable = (folder / 'exe').resolve(strict=True)
    return dict(pid=int(pid), uid=folder.stat().st_uid, start_ticks=int(values[19]),
                executable=str(executable), executable_sha256=sha(executable.read_bytes()),
                cmdline=(folder / 'cmdline').read_bytes().decode().split('\0')[:-1])


def environment(pid):
    return dict(piece.split('=', 1) for piece in (Path('/proc') / str(pid) / 'environ').read_bytes().decode().split('\0') if '=' in piece)


def desktop():
    user = pwd.getpwnam('liveuser')
    matches = {'mango': [], 'quickshell': []}
    for folder in Path('/proc').glob('[0-9]*'):
        try:
            if folder.stat().st_uid != user.pw_uid:
                continue
            exe = (folder / 'exe').resolve(strict=True)
            if exe.name not in matches:
                continue
            item = process(int(folder.name))
            if exe.name == 'quickshell' and '/usr/share/arctic/shell' not in item['cmdline']:
                continue
            matches[exe.name].append(item)
        except (FileNotFoundError, ProcessLookupError):
            continue
    require(all(len(v) == 1 for v in matches.values()), 'Expected one live-user Mango and shipped Arctic Quickshell')
    proofs = {k: v[0] for k, v in matches.items()}
    env = environment(proofs['quickshell']['pid'])
    require(env.get('HOME') == user.pw_dir and env.get('XDG_RUNTIME_DIR') == '/run/user/' + str(user.pw_uid)
            and env.get('WAYLAND_DISPLAY') and env.get('MANGO_INSTANCE_SIGNATURE'), 'Actual desktop environment is incomplete')
    runtime = Path(env['XDG_RUNTIME_DIR'])
    for path in (runtime / env['WAYLAND_DISPLAY'], Path(env['MANGO_INSTANCE_SIGNATURE'])):
        info = path.stat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == user.pw_uid, 'Desktop socket ownership/type differs')
    for name, proof in proofs.items():
        require(process(proof['pid']) == proof, 'Desktop process changed during identity collection: ' + name)
    return user, proofs, env


MANGO_WORKER = r'''
import json, os, socket, sys
queries = ('get version','get all-monitors','get all-clients','get all-layers')
result = {}
for query in queries:
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(3); peer.connect(os.environ['MANGO_INSTANCE_SIGNATURE'])
        peer.sendall((query+'\n').encode()); data = bytearray()
        while True:
            block = peer.recv(65536)
            if not block: break
            data.extend(block)
            if len(data)>4*1024*1024: raise RuntimeError('Mango response exceeds bound')
    value = json.loads(data)
    if not isinstance(value,dict) or 'error' in value: raise RuntimeError('Mango query failed')
    result[query] = value
print(json.dumps(dict(uid=os.getuid(),queries=result)))
'''


def session_prefix(user, env):
    actual = whitelisted_env(env)
    return ['/usr/sbin/runuser', '-u', user.pw_name, '--', '/usr/bin/env', '-i'] + [k + '=' + v for k, v in sorted(actual.items())]


def kernel_avcs(records):
    """Require actual kernel/audit provenance; sudo command text is not a denial."""
    return [r for r in records if r.get('_TRANSPORT') in ('kernel', 'audit')
            and AVC.search(str(r.get('MESSAGE', '')))]


def security(root=None, label='snapshot'):
    mode = execute(['getenforce']).decode().strip()
    require(mode == 'Enforcing', 'Guest SELinux must remain Enforcing')
    audit_text = execute(['auditctl', '-s']).decode()
    fields = dict(line.split(None, 1) for line in audit_text.splitlines() if len(line.split(None, 1)) == 2)
    require(fields.get('enabled') in ('1', '2') and fields.get('lost') == '0', 'Audit disabled or has lost records')
    raw = execute(['journalctl', '-b', '--no-pager', '-o', 'json'], timeout=30, limit=32 * 1024 * 1024)
    records = [json.loads(line) for line in raw.splitlines() if line]
    require(records and all(isinstance(r, dict) and 'MESSAGE' in r for r in records), 'Malformed/empty current-boot journal')
    denied = kernel_avcs(records)
    retained = raw
    if len(retained) > MAX_FILE:
        retained = retained[-MAX_FILE:].split(b'\n', 1)[-1]
    if root:
        (root / ('system-journal-' + label + '.log')).write_bytes(retained)
    return dict(selinux=mode, audit_status=audit_text, current_boot_journal_records=len(records),
                avc_records=denied, journal_total_bytes=len(raw), journal_retained_bytes=len(retained),
                journal_retained_sha256=sha(retained), journal_retention='Whole current-boot JSON journal up to 4 MiB; larger inputs retain the last complete records with this explicit bound',
                scope='Entire current boot AVC scan, post-interaction; not a pre-input cursor or cause attribution')


def read_config(path):
    if not path.exists():
        return dict(path=str(path), status='unavailable')
    resolved = path.resolve(strict=True)
    require(resolved.is_file() and resolved.stat().st_size <= 65536, 'Config is not a bounded regular file: ' + str(path))
    data = resolved.read_bytes()
    return dict(path=str(path), resolved=str(resolved), status='read', bytes=len(data), sha256=sha(data), text=data.decode())


def mango_sources(entry, home):
    """Read the declared ordered includes; do not execute/modify Mango config."""
    seen = set(); result = []
    def visit(path, depth):
        require(depth <= 6 and len(seen) < 32, 'Mango source graph exceeds bound')
        record = read_config(path)
        if record['status'] != 'read':
            return
        resolved = record['resolved']
        if resolved in seen:
            return
        seen.add(resolved)
        for line in record['text'].splitlines():
            match = re.match(r'^\s*(source(?:-optional)?)\s*=\s*(.+?)\s*$', line)
            if not match:
                continue
            declared = match[2]
            if declared.startswith('~/'):
                child = Path(home) / declared[2:]
            elif Path(declared).is_absolute():
                child = Path(declared)
            else:
                child = path.parent / declared
            include = read_config(child)
            result.append(dict(directive=match[1], declared=declared, **include))
            visit(child, depth+1)
    visit(entry, 0)
    return result


def quickshell_logs(user, env, root):
    roots = [Path(env['XDG_RUNTIME_DIR']) / 'quickshell',
             Path(env.get('XDG_CACHE_HOME', user.pw_dir + '/.cache')) / 'quickshell',
             Path(env.get('XDG_STATE_HOME', user.pw_dir + '/.local/state')) / 'quickshell']
    records = []; found = 0; visited = 0
    for base in roots:
        if not base.exists():
            records.append(dict(root=str(base), status='absent')); continue
        allowed = base.resolve(strict=True)
        require(allowed.is_relative_to(Path(user.pw_dir)) or allowed.is_relative_to(Path(env['XDG_RUNTIME_DIR'])),
                'Runtime log root resolves outside actual user/runtime paths')
        records.append(dict(root=str(base), resolved=str(allowed), status='searched'))
        for directory, dirs, files in os.walk(allowed, followlinks=False):
            visited += 1; require(visited <= 128, 'Runtime log directory search exceeds bound')
            dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
            for name in sorted(files):
                source = Path(directory) / name
                info = source.lstat()
                if not stat.S_ISREG(info.st_mode) or info.st_uid != user.pw_uid:
                    continue
                found += 1; require(found <= 64, 'Runtime log file search exceeds bound')
                fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(fd, 'rb') as stream:
                    stream.seek(max(0, info.st_size - 65536)); data = stream.read(65536)
                target = 'quickshell-runtime-%02d.log' % found
                (root / target).write_bytes(data)
                records.append(dict(path=str(source), evidence=target, status='bounded-tail-read',
                                    original_bytes=info.st_size, retained_bytes=len(data), sha256=sha(data),
                                    format='uninterpreted bytes; binary logs may need a separate reviewed decoder'))
    return records


def collect(user, proofs, env, root):
    report = dict(schema='arctic-safe-telemetry-v1', release_acceptance=False, safe_visual_gate='open',
                  scope='post-separated-input read-only telemetry; no renderer/opacity assertion',
                  collector_sha256=sha(Path(__file__).read_bytes()), boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                  cmdline=Path('/proc/cmdline').read_text().strip(), desktop_uid=user.pw_uid, processes=proofs,
                  environment={k: whitelisted_env(environment(v['pid'])) for k, v in proofs.items()},
                  effective_render_loop='unobserved', live_welcome_opacity='unobserved', files={})
    for name, proof in proofs.items():
        pid = proof['pid']; process_root = Path('/proc') / str(pid)
        maps = (process_root / 'maps').read_bytes()
        require(len(maps) <= MAX_FILE, 'Process maps exceed bound')
        (root / (name + '-maps.txt')).write_bytes(maps)
        targets = {}
        for fd in (1, 2):
            path = process_root / 'fd' / str(fd)
            target = os.readlink(path); targets[str(fd)] = target
            try:
                regular = Path(target)
                info = regular.lstat()
                if stat.S_ISREG(info.st_mode) and info.st_uid == user.pw_uid:
                    with regular.open('rb') as stream:
                        stream.seek(max(0, info.st_size - 65536)); data = stream.read(65536)
                    (root / (name + '-fd-' + str(fd) + '.log')).write_bytes(data)
            except FileNotFoundError:
                pass
        report.setdefault('stdout_stderr_targets', {})[name] = targets
        require(process(pid) == proof, 'Desktop identity changed while reading telemetry')
    config = Path(env.get('XDG_CONFIG_HOME', user.pw_dir + '/.config'))
    names = ['mango/config.conf', 'mango/settings.conf', 'mango/user.conf', 'arctic/effects.json', 'arctic/effects.conf',
             'arctic/settings.json', 'arctic/shell.json', 'arctic/motion.conf',
             'arctic/current/theme.json', 'arctic/current/mango-colors.conf']
    report['configs'] = [read_config(config / name) for name in names]
    report['mango_declared_sources'] = mango_sources(config / 'mango/config.conf', user.pw_dir)
    report['motion_preference_inputs'] = dict(env_reduce_motion=env.get('ARCTIC_REDUCE_MOTION'),
        motion_conf=next(v for v in report['configs'] if v['path'].endswith('/arctic/motion.conf')),
        meaning='Session.qml reads motion.conf and exact ARCTIC_REDUCE_MOTION=1; live QML property remains unobserved')
    # Runtime stdout/err and actual user journal replace the missing SDDM glob.
    journal = execute(['journalctl', '-b', '--no-pager', '_UID=' + str(user.pw_uid), '-n', '250', '-o', 'short-monotonic'], limit=MAX_FILE)
    (root / 'desktop-journal.log').write_bytes(journal)
    report['quickshell_runtime_logs'] = quickshell_logs(user, env, root)
    value = json.loads(execute(session_prefix(user, env) + ['python3', '-c', MANGO_WORKER]))
    require(value['uid'] == user.pw_uid and set(value['queries']) == set(MANGO_QUERIES), 'Mango query UID/file set differs')
    report['mango_read_only_queries'] = value
    report['security_before_grim'] = security(root, 'before-grim')
    return report


def export_files(root):
    files = []
    total = 0
    payloads = []
    for path in sorted(root.iterdir()):
        require(path.is_file() and not path.is_symlink(), 'Unexpected evidence file type')
        data = path.read_bytes(); total += len(data)
        require(len(data) <= MAX_FILE and total <= MAX_TOTAL, 'Guest evidence exceeds bound')
        packed = zlib.compress(data)
        pieces = [packed[i:i+CHUNK] for i in range(0, len(packed), CHUNK)]
        files.append(dict(path=path.name, bytes=len(data), sha256=sha(data), compressed_bytes=len(packed), chunks=len(pieces)))
        payloads.append((path.name, pieces))
    emit('MANIFEST', dict(schema='arctic-safe-files-v1', encoding='zlib+base64', files=files, bytes=total))
    for name, pieces in payloads:
        for i, piece in enumerate(pieces):
            emit('CHUNK', dict(path=name, index=i, data=base64.b64encode(piece).decode()))


def main():
    report = dict(schema='arctic-safe-telemetry-v1', status='failed', release_acceptance=False, safe_visual_gate='open')
    root = None
    error = None
    emit('BEGIN', dict(collector_sha256=sha(Path(__file__).read_bytes()), release_acceptance=False))
    try:
        require(os.geteuid() == 0 and Path(__file__).resolve() == Path('/run/arctic-safe/guest-safe-collector-v1.py'), 'Requires the exact root test-CD collector path')
        require(execute(['systemd-detect-virt']).decode().strip() in ('qemu', 'kvm'), 'Requires disposable QEMU/KVM guest')
        args = Path('/proc/cmdline').read_text().split()
        require('rd.live.image' in args and 'nomodeset' in args, 'Requires actual live Safe mode')
        require(execute(['getenforce']).decode().strip() == 'Enforcing', 'Guest SELinux must be Enforcing before telemetry')
        require('ro' in execute(['findmnt', '-n', '-o', 'OPTIONS', '/run/arctic-safe']).decode().strip().split(','), 'Test-CD must be mounted read-only')
        root = Path(tempfile.mkdtemp(prefix='arctic-safe-evidence-'))
        user, proofs, env = desktop()
        report = collect(user, proofs, env, root)
        configs_before = report['configs']
        emit('GRIM-READY', dict(guest_monotonic_ns=time.monotonic_ns(), wait_seconds=20,
                              qualification='Post-interaction screencopy can itself request repaint; not original-screen acceptance'))
        time.sleep(20)
        emit('GRIM-BEGIN', dict(guest_monotonic_ns=time.monotonic_ns()))
        image = execute(session_prefix(user, env) + ['grim', '-'], timeout=15)
        require(image.startswith(b'\x89PNG\r\n\x1a\n'), 'Guest grim output is not PNG')
        (root / 'guest-grim.png').write_bytes(image)
        report['grim'] = dict(bytes=len(image), sha256=sha(image), guest_monotonic_ns=time.monotonic_ns(),
                              qualification='Post-interaction, capture may perturb repaint')
        emit('GRIM-DONE', report['grim'])
        report['security_after_grim'] = security(root, 'after-grim')
        require(all(process(v['pid']) == v for v in proofs.values()), 'Desktop identity changed after screencopy')
        require([read_config(Path(v['path'])) for v in configs_before] == configs_before, 'Observed config changed during collector')
        require(mango_sources(Path(configs_before[0]['path']), user.pw_dir) == report['mango_declared_sources'],
                'Observed Mango include graph changed during collector')
        require(not report['security_before_grim']['avc_records'] and not report['security_after_grim']['avc_records'], 'Actual current-boot AVC requires review')
        report['status'] = 'read-only-telemetry-collected-visual-gate-open'
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
        report['status'] = 'failed'; report['error'] = error
    if root:
        (root / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    emit('REPORT', report)
    try:
        if root:
            export_files(root)
        else:
            emit('MANIFEST', dict(schema='arctic-safe-files-v1', encoding='zlib+base64', files=[], bytes=0))
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc)
    emit('END', dict(status='failed' if error else 'collected', error=error, release_acceptance=False))
    return 1 if error else 0


if __name__ == '__main__':
    sys.exit(main())
