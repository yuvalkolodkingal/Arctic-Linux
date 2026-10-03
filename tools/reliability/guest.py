#!/usr/bin/env python3
"""Release probes, run as root ONLY inside the disposable QEMU guest.

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
    print('ARCTIC-RELIABILITY ' + json.dumps(dict(stage=stage, check=check,
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
    # Never run these probes/upgrades on a developer workstation or real test PC.
    if Path(__file__).parent != Path('/run/t') or os.geteuid() != 0 or run(['systemd-detect-virt']) not in ('qemu', 'kvm'):
        raise RuntimeError('guest probes require root inside a QEMU/KVM VM')
    config = json.loads(Path(__file__).with_name('config.json').read_text())
    failed = False
    upgrade = config.get('upgrade_to')
    state_path = Path('/var/lib/arctic-release-test/upgrade.json')
    state = json.loads(state_path.read_text()) if upgrade and state_path.exists() else None
    if state:
        config['version'] = upgrade

    def check(name, fn):
        nonlocal failed
        try:
            record(stage, name, 'passed', fn())
        except Exception as exc:
            failed = True
            record(stage, name, 'failed', exc)

    def identity():
        data = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
        expected = config['version']
        if data.get('ID', '').strip('"') != 'arctic' or data.get('VERSION_ID', '').strip('"') != expected:
            raise RuntimeError(f'expected Arctic {expected}, got {data}')
        if data.get('PLATFORM_ID', '').strip('"') != 'platform:f44':
            raise RuntimeError('only the documented Fedora 44 update path is supported')
        live = Path('/run/rootfsbase').exists()
        if live != (stage == 'live'):
            raise RuntimeError(f'wrong boot medium: live={live}')
        return f'Arctic {expected}; live={live}; root={run(["findmnt", "-n", "-o", "SOURCE", "/"])}'

    check('identity', identity)
    if stage == 'installed':
        # Avoid racing the installer's deferred app downloads on first login.
        deadline = time.monotonic() + 600
        while time.monotonic() < deadline:
            status = subprocess.run(['systemctl', 'is-active', 'arctic-firstboot.service'],
                                    capture_output=True, text=True, timeout=10).stdout.strip()
            if status not in ('active', 'activating'):
                break
            time.sleep(5)
    check('network', lambda: run(['curl', '--fail', '--location', '--max-time', '30',
                                 '--noproxy', '*', 'https://fedoraproject.org/']).splitlines()[0][:160])
    try:
        prefix = desktop()
        record(stage, 'desktop', 'passed', run(prefix + ['mmsg', 'get', 'all-clients']))
        # Profile-specific expectations: falling back to another app must not pass.
        for role, pattern in [('terminal', 'kitty'), ('files', 'nautilus'),
                              ('browser', 'zen'), ('editor', 'zed')]:
            if stage == 'live' and role == 'editor':
                record(stage, 'app-editor', 'unrun', 'Zed is downloaded by the installer; not a live-image requirement')
                continue
            check('app-' + role, lambda role=role, pattern=pattern:
                  app(prefix, ['arctic-open', role], pattern))
        check('app-vlc', lambda: app(prefix, ['vlc'], 'vlc'))
        check('app-settings', lambda: app(prefix, ['arctic-settings'], 'Arctic Settings'))
    except Exception as exc:
        failed = True
        record(stage, 'desktop', 'failed', exc)
    if upgrade and stage == 'installed':
        if state:
            def preserved():
                if state['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text():
                    raise RuntimeError('upgrade has not rebooted')
                if Path('/home/ci/release-test-sentinel').read_text() != state['sentinel']:
                    raise RuntimeError('user data did not survive upgrade')
                after = run(['rpm', '-q', 'arctic-release'])
                if after == state['rpm']:
                    raise RuntimeError('arctic-release did not change: no-op upgrade')
                return f"{state['rpm']} -> {after}; new boot ID; user data preserved"
            check('upgrade', preserved)
        elif not failed:
            def upgrade_system():
                sentinel = os.urandom(24).hex()
                Path('/home/ci/release-test-sentinel').write_text(sentinel)
                ci = pwd.getpwnam('ci')
                os.chown('/home/ci/release-test-sentinel', ci.pw_uid, ci.pw_gid)
                before = dict(sentinel=sentinel, rpm=run(['rpm', '-q', 'arctic-release']),
                              boot_id=Path('/proc/sys/kernel/random/boot_id').read_text())
                # Use the documented signed repository path. No releasever override,
                # no candidate ISO overlay, and no disabling signature verification.
                print(run(['dnf', '-y', '--refresh', 'upgrade'], timeout=1800), flush=True)
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(before))
                return 'transaction completed; reboot verification pending'
            check('upgrade-transaction', upgrade_system)
    log = Path('/tmp/arctic-release-app.log')
    if log.exists():
        print('ARCTIC-APP-LOG-BEGIN\n' + log.read_text(errors='replace')[-20000:] + '\nARCTIC-APP-LOG-END', flush=True)
    # Full browser content, audio and account-dependent calls remain manual.
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
