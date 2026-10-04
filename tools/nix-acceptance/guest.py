#!/usr/bin/env python3
"""Nix acceptance probes, run as root ONLY inside the disposable QEMU guest.

Desktop/window probe adapted from PR12 tools/reliability/guest.py; PR12 is not merged.

Print one structured serial record per check. GUI probes run as the desktop user,
require a new Mango client and keep it mapped for five seconds.
"""
import json
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time


def run(argv, **kwargs):
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=kwargs.pop('timeout', 45),
                          check=True, **kwargs).stdout.strip()


def record(stage, check, status, detail):
    print('ARCTIC-NIX-ACCEPTANCE ' + json.dumps(dict(stage=stage, check=check,
          status=status, detail=str(detail))), flush=True)


def desktop():
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if (proc / 'comm').read_text().strip() != 'mango':
                continue
            user = pwd.getpwuid(proc.stat().st_uid)
            if user.pw_uid == 0:
                continue
            env = dict(item.split('=', 1) for item in
                       (proc / 'environ').read_bytes().decode().split('\0') if '=' in item)
            # WAYLAND_DISPLAY can be set after the compositor starts.
            runtime = Path('/run/user') / str(user.pw_uid)
            sockets = sorted(p for p in runtime.glob('wayland-*') if p.is_socket())
            if len(sockets) != 1:
                raise RuntimeError(f'expected one Wayland socket, got {sockets}')
            return ['runuser', '-u', user.pw_name, '--', 'env',
                    f'HOME={user.pw_dir}', f'XDG_RUNTIME_DIR={runtime}',
                    f'WAYLAND_DISPLAY={sockets[0].name}',
                    f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus',
                    'XDG_SESSION_TYPE=wayland',
                    *([f'MANGO_SOCKET={env["MANGO_SOCKET"]}'] if 'MANGO_SOCKET' in env else [])]
        except (FileNotFoundError, ProcessLookupError):
            continue
    raise RuntimeError('no non-root Mango session')


def clients(prefix):
    return {str(c['id']): c for c in json.loads(run(prefix + ['mmsg', 'get', 'all-clients']))['clients']}


def app(prefix, command, pattern):
    before = set(clients(prefix))
    # arctic-open may detach. Its exit status alone is not evidence of a window.
    with open('/tmp/arctic-release-app.log', 'a') as log:
        child = subprocess.Popen(prefix + command, stdout=log, stderr=log)
        try:
            until = time.monotonic() + 60
            while time.monotonic() < until:
                current = clients(prefix)
                new = {key for key, value in current.items() if key not in before
                       and re.search(pattern, str(value.get('appid', value.get('app_id', ''))) +
                                     ' ' + str(value.get('title', '')), re.I)}
                if new:
                    time.sleep(5)
                    if new & set(clients(prefix)):
                        return f'{command}: new mapped clients {sorted(new)} persisted 5s'
                time.sleep(2)
            raise RuntimeError(f'{command}: no persistent new window; see /tmp/arctic-release-app.log')
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def main():
    stage = sys.argv[1]
    if (Path(__file__).parent != Path('/run/t') or os.geteuid() != 0
            or run(['systemd-detect-virt']) not in ('qemu', 'kvm')):
        raise RuntimeError('requires root in the disposable QEMU/KVM guest')
    if run(['getenforce']) != 'Enforcing':
        raise RuntimeError('SELinux must be enforcing; never relax policy to pass')
    record(stage, 'selinux', 'passed', 'Enforcing')
    prefix = desktop()
    username = prefix[2]
    user = pwd.getpwnam(username)
    nix = prefix + ['/usr/bin/arctic-nix']
    profile = Path(user.pw_dir) / '.local/state/nix/profiles/arctic'
    state_file = Path('/var/lib/arctic-nix-acceptance.json')
    failed = False

    def check(name, fn):
        nonlocal failed
        try:
            result = fn()
            record(stage, name, 'passed', result)
            return result
        except Exception as exc:
            failed = True
            record(stage, name, 'failed', exc)
            return None

    def must(condition, detail):
        if not condition:
            raise RuntimeError(detail)
        return detail

    if stage == 'live':
        must('rd.live.image' in Path('/proc/cmdline').read_text(), 'booted live media')
        p = subprocess.run(nix + ['install', 'hello'], capture_output=True, text=True, timeout=30)
        check('live-mutation-denied', lambda: must(p.returncode != 0 and 'live' in (p.stdout+p.stderr).lower(), p.stdout+p.stderr))
        return int(failed)

    must('rd.live.image' not in Path('/proc/cmdline').read_text(), 'installed boot')
    check('daemon', lambda: run(['systemctl', 'is-active', 'nix-daemon.service']))
    check('persistent-mount', lambda: must(run(['findmnt', '-n', '-o', 'TARGET', '-T', '/nix']) == '/nix', run(['findmnt', '/nix'])))
    check('store-ownership', lambda: must(Path('/nix').stat().st_uid == 0 and not Path('/nix').stat().st_mode & 0o022, '/nix root-owned and not group/world writable'))
    check('labels', lambda: run(['ls', '-ldZ', '/nix/store', '/nix/var/nix/daemon-socket']))
    before_avc = run(['journalctl', '-b', '--no-pager', '-o', 'cat'])
    prior = json.loads(state_file.read_text()) if state_file.exists() else None
    if prior:
        check('new-boot', lambda: must(prior['boot'] != Path('/proc/sys/kernel/random/boot_id').read_text(), 'new boot ID after update'))
        check('profile-persistence', lambda: must(str(profile.resolve()) == prior['profile'], 'personal generation survived update/reboot'))
        check('hello-after-reboot', lambda: run(prefix + [str(profile/'bin/hello')]))
        check('nix-engine-after-update', lambda: run(['/usr/bin/nix', '--version']))
        check('graphical-after-reboot', lambda: app(prefix, [str(profile/'bin/foot'), '-e', 'sleep', '30'], 'foot'))
        return int(failed)

    check('search', lambda: must(bool(json.loads(run(nix + ['search', 'hello'], timeout=600))), 'real Nix search returned JSON'))
    check('install', lambda: run(nix + ['install', 'hello', 'foot'], timeout=1200))
    check('hello', lambda: run(prefix + [str(profile/'bin/hello')]))
    check('desktop-file', lambda: must(bool(list((profile/'share/applications').glob('*.desktop'))), 'profile contains desktop entries'))
    check('icons', lambda: must((profile/'share/icons').is_dir(), 'profile contains icon data'))
    check('graphical-foot', lambda: app(prefix, [str(profile/'bin/foot'), '-e', 'sleep', '30'], 'foot'))

    def session_environment():
        # Read the existing desktop process environment, not a synthetic login shell.
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                if (proc/'comm').read_text().strip() == 'mango' and proc.stat().st_uid == user.pw_uid:
                    env = dict(v.split('=',1) for v in (proc/'environ').read_bytes().decode().split('\0') if '=' in v)
                    must(str(profile/'bin') in env.get('PATH','').split(':'), 'Arctic profile in desktop PATH')
                    must(str(profile/'share') in env.get('XDG_DATA_DIRS','').split(':'), 'Arctic profile in desktop XDG_DATA_DIRS')
                    return 'real login environment includes Nix launchers and binaries'
            except (FileNotFoundError, ProcessLookupError):
                continue
        raise RuntimeError('desktop environment unavailable')
    check('session-paths', session_environment)

    def second_user():
        run(['useradd', '--create-home', 'nixpeer'])
        peer = ['runuser', '-u', 'nixpeer', '--', 'env', 'HOME=/home/nixpeer']
        run(peer + ['/usr/bin/arctic-nix', 'install', 'hello'], timeout=600)
        run(peer + ['/home/nixpeer/.local/state/nix/profiles/arctic/bin/hello'])
        denied = subprocess.run(peer + ['/usr/bin/nix', '--extra-experimental-features', 'nix-command flakes', '--store', 'daemon', 'profile', 'remove', '--profile', str(profile), 'hello'], capture_output=True, text=True, timeout=60)
        must(denied.returncode != 0, 'second user cannot mutate first profile')
        return denied.stderr[-1000:]
    check('two-user-isolation', second_user)
    check('update-personal', lambda: run(nix + ['update'], timeout=1200))
    check('remove', lambda: run(nix + ['remove', 'hello'], timeout=300))
    check('rollback', lambda: run(nix + ['rollback'], timeout=300))
    check('rollback-hello', lambda: run(prefix + [str(profile/'bin/hello')]))

    def trust():
        data=json.loads(run(['/usr/bin/nix', '--extra-experimental-features', 'nix-command', 'config', 'show', '--json']))
        for key, wanted in [('require-sigs',True), ('sandbox',True), ('trusted-users',['root'])]:
            must(data[key]['value'] == wanted, f'{key}: {data[key]["value"]}')
        return 'signature, sandbox and root-only trust settings preserved (configuration check)'
    check('trust-config', trust)
    after_avc = run(['journalctl', '-b', '--no-pager', '-o', 'cat'])
    new_lines = after_avc[len(before_avc):] if after_avc.startswith(before_avc) else after_avc
    check('avc', lambda: must(not re.search(r'avc:\s+denied.*(?:nix|foot)', new_lines, re.I), new_lines[-6000:] if 'avc:' in new_lines else 'no matching new Nix/foot AVC'))
    if not failed:
        before_rpm = run(['rpm', '-q', 'nix', 'nix-daemon'])
        check('dnf-update', lambda: run(['dnf5', '-y', '--refresh', 'upgrade'], timeout=1800))
        after_rpm = run(['rpm', '-q', 'nix', 'nix-daemon'])
        record(stage, 'engine-version-change', 'passed' if before_rpm != after_rpm else 'unrun', f'{before_rpm} -> {after_rpm}; same version is not upgrade proof')
        if not failed:
            state_file.write_text(json.dumps(dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text(), profile=str(profile.resolve()))))
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
