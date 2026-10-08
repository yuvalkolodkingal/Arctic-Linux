#!/usr/bin/env python3
"""Release probes, run as root ONLY inside the disposable QEMU guest.

Print one structured serial record per check. GUI probes run as the desktop user,
require a new Mango client and keep it mapped for five seconds.
"""
import json
import hashlib
import os
from pathlib import Path
import pwd
import re
import subprocess
import sys
import time


# Expected app IDs are selected explicitly by the test lane. An arctic-open
# fallback or a window whose title happens to mention the expected app cannot pass.
PROFILES = {
    'legacy': {
        'terminal': (['arctic-open', 'terminal'], r'kitty'),
        'files': (['arctic-open', 'files'], r'(?:org\.gnome\.)?nautilus'),
        'browser': (['arctic-open', 'browser'], r'(?:app\.zen_browser\.)?zen'),
        'editor': (['arctic-open', 'editor'], r'(?:dev\.zed\.)?zed'),
        'media': (['vlc'], r'vlc'),
    },
    'lightweight': {
        'terminal': (['arctic-open', 'terminal'], r'foot'),
        'files': (['arctic-open', 'files'], r'pcmanfm'),
        'browser': (['arctic-open', 'browser'], r'org\.gnome\.Epiphany'),
        'editor': (['arctic-open', 'editor'], r'(?:org\.qt-project\.)?featherpad'),
        'media': (['celluloid'], r'io\.github\.celluloid_player\.Celluloid'),
    },
}


def expected_apps(profile, stage):
    if profile not in PROFILES:
        raise ValueError('unsupported reliability app profile: ' + str(profile))
    return {role: spec for role, spec in PROFILES[profile].items()
            if not (profile == 'legacy' and stage == 'live' and role == 'editor')}


def run(argv, **kwargs):
    return subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, timeout=kwargs.pop('timeout', 45),
                          check=True, **kwargs).stdout.strip()


def record(stage, check, status, detail):
    print('ARCTIC-RELIABILITY ' + json.dumps(dict(stage=stage, check=check,
          status=status, detail=str(detail))), flush=True)


def network(stage):
    # The live installation lane is intentionally isolated. External HTTPS,
    # deferred downloads and signed upgrades are tested only on the installed disk.
    if stage == 'live':
        return None
    return run(['curl', '--fail', '--location', '--max-time', '30',
                '--noproxy', '*', 'https://fedoraproject.org/']).splitlines()[0][:160]


def session_signature(proc_root, uid, runtime, display, env, expected_socket):
    # Mango sets this after exec, so its own /proc environ can lack it. Accept
    # only same-user children of the matching Wayland session, then authenticate
    # the socket against the running compositor's PID and runtime directory.
    signatures = {env['MANGO_INSTANCE_SIGNATURE']} if env.get('MANGO_INSTANCE_SIGNATURE') else set()
    for child in proc_root.glob('[0-9]*'):
        try:
            if child.stat().st_uid != uid:
                continue
            child_env = dict(v.split('=', 1) for v in
                (child / 'environ').read_bytes().decode().split('\0') if '=' in v)
            if (child_env.get('WAYLAND_DISPLAY') == display
                    and child_env.get('XDG_RUNTIME_DIR') == str(runtime)
                    and child_env.get('MANGO_INSTANCE_SIGNATURE')):
                signatures.add(child_env['MANGO_INSTANCE_SIGNATURE'])
        except (FileNotFoundError, ProcessLookupError, PermissionError, UnicodeDecodeError):
            continue
    if len(signatures) != 1:
        raise RuntimeError(f'expected one Mango IPC signature, found {len(signatures)}')
    signature = signatures.pop()
    socket = Path(signature)
    if (socket != expected_socket or socket.parent != runtime or socket.is_symlink()
            or not socket.is_socket() or socket.stat().st_uid != uid):
        raise RuntimeError('Mango IPC signature does not identify this compositor socket')
    return signature


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
            signature = session_signature(Path('/proc'), user.pw_uid, runtime,
                                          sockets[0].name, env, runtime / f'mango-{proc.name}.sock')
            return ['runuser', '-u', user.pw_name, '--', 'env',
                    f'MANGO_INSTANCE_SIGNATURE={signature}',
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


def app(prefix, command, pattern, match_title=False):
    def matches(client):
        value = client.get('title', '') if match_title else client.get('appid', client.get('app_id', ''))
        return re.fullmatch(pattern, str(value), re.I)

    before = set(clients(prefix))
    # arctic-open may detach. Its exit status alone is not evidence of a window.
    with open('/tmp/arctic-release-app.log', 'a') as log:
        child = subprocess.Popen(prefix + command, stdout=log, stderr=log)
        try:
            until = time.monotonic() + 60
            while time.monotonic() < until:
                current = clients(prefix)
                new = {key for key, value in current.items() if key not in before
                       and matches(value)}
                if new:
                    time.sleep(5)
                    after = clients(prefix)
                    if any(key in after and matches(after[key]) for key in new):
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


def wallpapers(prefix, expected, folder=Path('/usr/share/backgrounds/arctic'),
               greeter=Path('/usr/share/sddm/themes/arctic/background.png')):
    """Verify the intended exports in the actual image and discovery as its user."""
    from PIL import Image
    actual = json.loads((folder / 'collection.json').read_text())
    if actual != expected:
        raise RuntimeError('Installed photo collection differs from the source-pinned expectation')
    paths = []
    for item in expected['wallpapers']:
        path = folder / item['file']
        if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise RuntimeError('Packaged photo hash differs: ' + item['file'])
        with Image.open(path) as image:
            if image.format != 'JPEG' or image.size != (item['width'], item['height']):
                raise RuntimeError('Packaged photo dimensions/format differ: ' + item['file'])
            image.load()
        paths.append(str(path))
    owners = run(['rpm', '-qf', '--qf', '%{NAME}\n', *paths]).splitlines()
    if len(owners) != len(paths) or set(owners) != {'arctic-backgrounds'}:
        raise RuntimeError('Photo ownership is not arctic-backgrounds')
    if (folder / 'default.jpg').resolve() != folder / (expected['default'] + '.jpg'):
        raise RuntimeError('Fresh desktop/lock alias does not select the pinned default')
    if greeter.resolve() != folder / 'default.png':
        raise RuntimeError('Packaged greeter fallback does not select the photo default')
    with Image.open(folder / 'default.png') as image:
        if image.format != 'PNG':
            raise RuntimeError('Compatibility default is not a real PNG')
        image.load()
    found = json.loads(run(prefix + ['python3', '/usr/share/arctic/shell/scripts/wallpapers.py', 'list']))
    discovered = {item['key'] for item in found['items'] if item.get('arctic') and item.get('photographer') == expected['author']}
    if discovered != set(paths):
        raise RuntimeError('User wallpaper picker does not discover the complete pinned photo collection')
    return f"{len(paths)} owned/verified photos; source {expected['revision']}; picker and default aliases verified"


def main():
    stage = sys.argv[1]
    # Never run these probes/upgrades on a developer workstation or real test PC.
    if Path(__file__).parent != Path('/run/t') or os.geteuid() != 0 or run(['systemd-detect-virt']) not in ('qemu', 'kvm'):
        raise RuntimeError('guest probes require root inside a QEMU/KVM VM')
    config = json.loads(Path(__file__).with_name('config.json').read_text())
    profile = config.get('app_profile', 'legacy')
    applications = expected_apps(profile, stage)
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
    if stage == 'live':
        record(stage, 'network', 'unrun', 'Offline live installation; external HTTPS is required after disk boot')
    else:
        check('network', lambda: network(stage))
    try:
        prefix = desktop()
        record(stage, 'desktop', 'passed', run(prefix + ['mmsg', 'get', 'all-clients']))
        if profile == 'lightweight':
            check('wallpapers', lambda: wallpapers(prefix, json.loads(
                Path(__file__).with_name('expected-wallpapers.json').read_text())))
        for role, (command, pattern) in applications.items():
            check('app-' + role, lambda command=command, pattern=pattern:
                  app(prefix, command, pattern))
        if 'editor' not in applications:
            record(stage, 'app-editor', 'unrun', 'Legacy Zed is downloaded by the installer; not a live-image requirement')
        # Settings is a Quickshell window with a shared toolkit app ID.
        check('app-settings', lambda: app(prefix, ['arctic-settings'], r'Arctic Settings', match_title=True))
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
