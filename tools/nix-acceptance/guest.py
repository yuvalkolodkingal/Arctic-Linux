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
from urllib.parse import urlsplit


def run(argv, **kwargs):
    result = subprocess.run(argv, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=kwargs.pop('timeout', 45),
                            check=False, **kwargs)
    if result.returncode:
        raise RuntimeError(f'{argv}: exit {result.returncode}: {result.stdout[-8000:]}')
    return result.stdout.strip()


def record(stage, check, status, detail):
    print('ARCTIC-NIX-ACCEPTANCE ' + json.dumps(dict(stage=stage, check=check,
          status=status, detail=str(detail))), flush=True)


def online_preflight(prefix):
    """Bounded DNS and verified HTTPS checks before network-dependent acceptance.

    The optional existing test proxy resolves upstream names itself. Check its
    address in that mode; a direct online boot must resolve both upstream hosts.
    """
    proxy = os.environ.get('https_proxy') or os.environ.get('HTTPS_PROXY')
    hosts = ['api.github.com', 'cache.nixos.org']
    if proxy:
        host = urlsplit(proxy).hostname
        if not host:
            raise RuntimeError('Test HTTPS proxy has no hostname')
        hosts = [host]
    for host in hosts:
        if not run(prefix + ['getent', 'ahosts', host], timeout=15):
            raise RuntimeError(f'DNS returned no addresses for {host}')
    urls = ['https://api.github.com/', 'https://cache.nixos.org/nix-cache-info']
    for url in urls:
        status = run(prefix + ['curl', '--fail', '--silent', '--show-error', '--location',
                     '--connect-timeout', '10', '--max-time', '30', '--output', '/dev/null',
                     '--write-out', '%{http_code}', url], timeout=40)
        if status != '200':
            raise RuntimeError(f'HTTPS preflight for {url} returned HTTP {status}')
    return dict(dns_hosts=hosts, dns_mode='proxy' if proxy else 'direct', verified_https=urls)


def nix_socket_defaults():
    """Require candidate socket defaults, then separately probe real user activation."""
    socket = run(['systemctl', 'show', 'nix-daemon.socket', '-p', 'UnitFileState', '--value'])
    service = run(['systemctl', 'show', 'nix-daemon.service', '-p', 'UnitFileState', '--value'])
    if socket != 'enabled' or service != 'disabled':
        raise RuntimeError(f'Expected enabled Nix socket and disabled eager service; socket={socket}, service={service}')
    active = run(['systemctl', 'is-active', 'nix-daemon.socket'])
    if active != 'active':
        raise RuntimeError(f'Nix socket is not active: {active}')
    return 'enabled active socket; eager service disabled; user store request follows'


def no_new_nix_avc(before):
    after = run(['journalctl', '-b', '--no-pager', '-o', 'cat'])
    new_lines = after[len(before):] if after.startswith(before) else after
    if re.search(r'avc:\s+denied.*(?:nix|foot)', new_lines, re.I):
        raise RuntimeError('New Nix/Foot AVC: ' + new_lines[-6000:])
    return 'no matching new Nix/Foot AVC'


def verified_rpm_signatures(files):
    """Require a successful cryptographic signature for every downloaded RPM.

    RPM 6 prints lowercase ``signature``. A digest-only unsigned RPM can also
    exit successfully, so neither capitalization nor one global ``OK`` is a gate.
    """
    if not files:
        raise RuntimeError('No RPM files to verify')
    output = run(['rpmkeys', '--checksig', '--verbose', *files], timeout=180)
    blocks = {}
    current = None
    for line in output.splitlines():
        if line.endswith(':') and line[:-1] in files:
            current = line[:-1]
            blocks[current] = []
        elif current is not None:
            blocks[current].append(line.strip())
    for filename in files:
        lines = blocks.get(filename, [])
        signatures = [line for line in lines if re.search(r'\bsignature\b', line, re.I)]
        if not signatures or any(not line.endswith(': OK') for line in signatures):
            raise RuntimeError(f'No valid signature for {filename}: {lines!r}')
    return output


def latest_offline_history():
    """Select the latest positive index listed by the installed DNF version.

    DNF 5.4.6 converts --number with stoul and cannot resolve the documented
    negative index. Require a real listed boot; an empty history is a failure.
    """
    listing = run(['dnf5', 'offline', 'log'], timeout=180)
    entries = re.findall(r'^\s*([1-9][0-9]*)\s*/\s*([0-9a-f]{32}):',
                         listing, flags=re.M | re.I)
    if not entries:
        raise RuntimeError(f'No listed offline transaction boot: {listing}')
    number, boot_id = max(entries, key=lambda entry: int(entry[0]))
    history = run(['dnf5', 'offline', 'log', '--number=' + number], timeout=180)
    return dict(listing=listing, number=int(number), boot_id=boot_id, log=history)


def session_signature(proc_root, uid, runtime, display, env):
    # Mango exports IPC after exec; its children, not /proc/<mango>/environ,
    # expose the new value. Only accept this user's matching Wayland session.
    signatures = {env['MANGO_INSTANCE_SIGNATURE']} if env.get('MANGO_INSTANCE_SIGNATURE') else set()
    for child in proc_root.glob('[0-9]*'):
        try:
            if child.stat().st_uid != uid:
                continue
            child_env = dict(v.split('=', 1) for v in
                (child/'environ').read_bytes().decode().split('\0') if '=' in v)
            if (child_env.get('WAYLAND_DISPLAY') == display
                    and child_env.get('XDG_RUNTIME_DIR') == str(runtime)
                    and child_env.get('MANGO_INSTANCE_SIGNATURE')):
                signatures.add(child_env['MANGO_INSTANCE_SIGNATURE'])
        except (FileNotFoundError, ProcessLookupError, PermissionError, UnicodeDecodeError):
            continue
    if len(signatures) != 1:
        raise RuntimeError(f'expected one Mango IPC signature, found {len(signatures)}')
    return signatures.pop()


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
            signature = session_signature(Path('/proc'), user.pw_uid, runtime, sockets[0].name, env)
            return ['runuser', '-u', user.pw_name, '--', 'env',
                    'MANGO_INSTANCE_SIGNATURE=' + signature,
                    f'HOME={user.pw_dir}', f'XDG_RUNTIME_DIR={runtime}',
                    f'WAYLAND_DISPLAY={sockets[0].name}',
                    f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus',
                    'XDG_SESSION_TYPE=wayland',
                    *[f'{key}={env[key]}' for key in ('PATH', 'XDG_DATA_DIRS', 'XDG_DATA_HOME') if key in env],
                    *([f'MANGO_SOCKET={env["MANGO_SOCKET"]}'] if 'MANGO_SOCKET' in env else [])]
        except (FileNotFoundError, ProcessLookupError):
            continue
    raise RuntimeError('no non-root Mango session')


def clients(prefix):
    return {str(c['id']): c for c in json.loads(run(prefix + ['mmsg', 'get', 'all-clients']))['clients']}


def app(prefix, command, pattern, timeout=300):
    before = set(clients(prefix))
    # arctic-open may detach. Its exit status alone is not evidence of a window.
    with open('/tmp/arctic-release-app.log', 'a') as log:
        child = subprocess.Popen(prefix + command, stdout=log, stderr=log)
        try:
            until = time.monotonic() + timeout
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


def browser(prefix):
    """Exercise the shipped Firefox-based browser through its exported launcher."""
    ref = 'app.zen_browser.zen'
    entry = '/var/lib/flatpak/exports/share/applications/' + ref + '.desktop'
    run(prefix + ['test', '-r', entry])
    info = run(prefix + ['flatpak', 'info', '--system', ref])
    commit = run(prefix + ['flatpak', 'info', '--system', '--show-commit', ref])
    try:
        window = app(prefix, ['gtk-launch', ref], r'zen')
        # Mapping precedes browser chrome/content painting under TCG. Keep the
        # detached browser open for the interactive harness's screenshot review;
        # a blank initial surface alone cannot qualify browser usability.
        time.sleep(45)
        if not any(re.search(r'zen', str(value.get('appid', value.get('app_id', '')))
                             + ' ' + str(value.get('title', '')), re.I)
                   for value in clients(prefix).values()):
            raise RuntimeError('Zen window did not survive the visual-review interval')
        return f'{info}; Flatpak commit {commit}; exported entry {entry}; {window}'
    finally:
        # gtk-launch detaches; close only this user's test browser before installing.
        subprocess.run(prefix + ['flatpak', 'kill', ref], capture_output=True, timeout=15)


def main(update_method='dnf', expected_stable_source=None):
    if update_method not in ('dnf', 'arctic-offline'):
        raise ValueError('Unknown update acceptance method')
    if expected_stable_source is not None and not re.fullmatch('[0-9a-f]{40}', expected_stable_source):
        raise ValueError('Expected stable source must be a full Git SHA')
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

    check('non-chromium-browser', lambda: browser(prefix))

    if stage == 'live':
        must('rd.live.image' in Path('/proc/cmdline').read_text(), 'booted live media')
        p = subprocess.run(nix + ['install', 'hello'], capture_output=True, text=True, timeout=30)
        check('live-mutation-denied', lambda: must(p.returncode != 0 and 'after installing Arctic to disk' in (p.stdout+p.stderr), p.stdout+p.stderr))
        return int(failed)

    must('rd.live.image' not in Path('/proc/cmdline').read_text(), 'installed boot')
    # Include the first user store request/socket activation in the AVC interval.
    before_avc = run(['journalctl', '-b', '--no-pager', '-o', 'cat'])
    check('daemon-socket-defaults', nix_socket_defaults)
    check('daemon-store-info', lambda: run(prefix + ['/usr/bin/nix', '--extra-experimental-features',
          'nix-command', 'store', 'info', '--store', 'daemon']))
    check('daemon', lambda: run(['systemctl', 'is-active', 'nix-daemon.service']))
    check('persistent-mount', lambda: must(run(['findmnt', '-n', '-o', 'TARGET', '-T', '/nix']) == '/nix', run(['findmnt', '/nix'])))
    check('store-ownership', lambda: must(Path('/nix').stat().st_uid == 0 and not Path('/nix').stat().st_mode & 0o022, '/nix root-owned and not group/world writable'))
    check('labels', lambda: run(['ls', '-ldZ', '/nix/store', '/nix/var/nix/daemon-socket']))
    prior = json.loads(state_file.read_text()) if state_file.exists() else None
    settings = prefix + ['python3', '/usr/share/arctic/settings/scripts/arctic_settings.py']
    check('mango-dodge-capability', lambda: must(
        json.loads(run(prefix + ['mmsg', 'get', 'capabilities'])).get('client_geometry_events') is True,
        'installed Mango advertises coalesced client geometry events'))
    def customization():
        data = json.loads(run(settings + ['binds']))
        row = next(b for b in data['builtin'] if b['action'] == 'killclient')
        if prior:
            must(row['modified'] and row['key'] == 'F9', 'built-in remap survived update and reboot')
            saved = json.loads(run(settings + ['shell-options']))
            must(saved['barPosition'] == 'right', 'side taskbar preference survived update and reboot')
            must(saved['barHideMode'] == 'dodge' and saved['barDodgeAvailable'],
                 'Dodge preference and compositor capability survived update and reboot')
            run(settings + ['builtin-bind', 'reset-all'])
            must((Path(user.pw_dir)/'.config/mango/arctic/binds.conf').is_symlink(), 'reset restored packaged shortcut link')
        else:
            run(settings + ['builtin-bind', 'set', row['id'], 'SUPER+ALT', 'F9'])
            data = json.loads(run(settings + ['binds']))
            must(any(b['action'] == 'reload_config' and set(b['mods']) == {'ALT','CTRL','SUPER'} for b in data['all']), 'recovery reload binding retained')
            for position in ('left', 'bottom', 'top', 'right'):
                run(settings + ['shell-option-set', 'barPosition', position])
                time.sleep(1)
            saved = json.loads(run(settings + ['shell-option-set', 'barHideMode', 'dodge']))
            must(saved['barHideMode'] == 'dodge' and saved['barDodgeAvailable'],
                 'Dodge preference accepted by installed session')
        # The installed compositor parses the complete sourced configuration.
        parsed = run(prefix + ['mango', '-c', str(Path(user.pw_dir)/'.config/mango/config.conf'), '-p'])
        must('[ERROR]' not in parsed, parsed[-3000:])
        return 'native Mango parser, remap/recovery and per-user taskbar persistence checks'
    check('desktop-customization', customization)
    if prior:
        check('new-boot', lambda: must(prior['boot'] != Path('/proc/sys/kernel/random/boot_id').read_text(), 'new boot ID after update'))
        check('profile-persistence', lambda: must(str(profile.resolve()) == prior['profile'], 'personal generation survived update/reboot'))
        check('hello-after-reboot', lambda: run(prefix + [str(profile/'bin/hello')]))
        check('nix-engine-after-update', lambda: run(['/usr/bin/nix', '--version']))
        check('graphical-after-reboot', lambda: app(prefix, [str(profile/'bin/foot'), '-e', 'sleep', '30'], 'foot'))
        if prior.get('update_method') == 'arctic-offline':
            def offline_update_completed():
                data = json.loads(run(['/usr/bin/arctic-update', 'status', '--json'], timeout=180))
                must(not data.get('install_error') and not data.get('boot_failures'), data)
                history = json.loads(Path('/var/lib/arctic/update-status.json').read_text())
                must(data.get('state') == 'idle' and not data.get('armed') and not data.get('stored'), data)
                versions = run(['rpm', '-q', 'arctic-shell', 'arctic-desktop-config'])
                must('.preview.' not in versions and versions != prior['arctic_rpms'], versions)
                expected = prior.get('expected_stable_source')
                if expected:
                    must(all('git'+expected[:7] in line for line in versions.splitlines()), versions)
                must(not Path('/system-update').is_symlink(), 'offline update link removed')
                return dict(status=data, installed_at=history.get('installed_at'), arctic_rpms=versions)
            check('signed-offline-update-completed', offline_update_completed)
            check('signed-offline-update-history', latest_offline_history)
        check('avc', lambda: no_new_nix_avc(before_avc))
        return int(failed)

    if check('online-network-preflight', lambda: online_preflight(prefix)) is None:
        record(stage, 'network-dependent-acceptance', 'unrun',
               'DNS/HTTPS preflight failed; Nix fetch/update acceptance requires an online installed boot')
        return 1

    # Start a real DesktopEntries consumer BEFORE the first profile exists.
    # The existing shell uses this same Quickshell singleton/model.
    probe = Path('/tmp/arctic-nix-desktop-probe.qml')
    probe.write_text("""import QtQuick
import Quickshell
import Quickshell.Io
ShellRoot {
 id: probeRoot
 property var entry: DesktopEntries.applications.values.find(e => e.id === "foot") || null
 property Image iconProbe: Image { source: probeRoot.entry ? Quickshell.iconPath(probeRoot.entry.icon) : "" }
 IpcHandler {
  target: "nixacceptance"
  function seen(): bool { return DesktopEntries.byId("foot") !== null; }
  function iconReady(): bool { return probeRoot.iconProbe.status === Image.Ready; }
  function launch(): bool { const e = DesktopEntries.byId("foot"); if (!e) return false; e.execute(); return true; }
 }
}
""")
    with open('/tmp/arctic-nix-desktop-probe.log', 'w') as output:
        subprocess.Popen(prefix + ['quickshell', '-n', '-p', str(probe)], stdout=output, stderr=output)
    probe_cmd = ['quickshell', 'ipc', '-p', str(probe), 'call', 'nixacceptance']

    def probe_wait(method, expected):
        last = ''
        for _ in range(20):
            try:
                last = run(prefix + probe_cmd + [method])
                if last == expected or (expected is None and last in ('true', 'false')):
                    return f'{method}={last}'
            except RuntimeError as exc:
                last = str(exc)
            time.sleep(1)
        raise RuntimeError(f'{method}: expected {expected}, got {last}')
    check('desktop-before-install', lambda: probe_wait('seen', None))  # Foot may already exist as an RPM.
    check('search', lambda: must(bool(json.loads(run(nix + ['search', 'hello'], timeout=600))), 'real Nix search returned JSON'))
    check('install', lambda: run(nix + ['install', 'hello', 'foot'], timeout=1200))
    check('desktop-after-install', lambda: probe_wait('seen', 'true'))
    check('desktop-icon-load', lambda: probe_wait('iconReady', 'true'))
    check('desktop-entry-launch', lambda: app(prefix, probe_cmd + ['launch'], 'foot'))
    def launched_from_store():
        for proc in Path('/proc').glob('[0-9]*'):
            try:
                executable = str((proc/'exe').resolve())
                if proc.stat().st_uid == user.pw_uid and executable.startswith('/nix/store/') and 'foot' in executable:
                    return executable
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
        raise RuntimeError('no Nix-store Foot process after desktop-entry launch')
    check('desktop-entry-nix-executable', launched_from_store)
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
    check('avc', lambda: no_new_nix_avc(before_avc))
    if not failed:
        before_rpm = run(['rpm', '-q', 'nix', 'nix-daemon'])
        before_arctic = run(['rpm', '-q', 'arctic-shell', 'arctic-desktop-config'])
        if update_method == 'arctic-offline':
            check('signed-offline-update-stage', lambda: run(
                  ['/usr/bin/arctic-update', 'now', '--sync'], timeout=2400))
            def staged_update():
                data = json.loads(run(['/usr/bin/arctic-update', 'status', '--json'], timeout=180))
                must(data.get('state') == 'ready' and data.get('armed') is True and data.get('packages', 0) > 0, data)
                must(Path('/system-update').is_symlink(), 'offline update is armed for the next boot')
                must(run(['rpm', '-q', 'arctic-shell', 'arctic-desktop-config']) == before_arctic,
                     'staging does not mutate the running Arctic packages')
                files = [str(path) for path in Path('/var/lib/dnf/offline/packages').rglob('*.rpm')
                         if path.name.startswith(('arctic-', 'sddm-wayland-mango-'))]
                must(bool(files), 'signed Arctic packages were actually downloaded')
                signatures = verified_rpm_signatures(files)
                expected = {line.split()[0] for line in run(['rpm', '-qa', '--qf', '%{NAME} %{RELEASE}\n']).splitlines()
                            if '.preview.' in line and line.startswith(('arctic-', 'sddm-wayland-mango '))}
                downloaded = set(run(['rpm', '-qp', '--qf', '%{NAME}\n', *files], timeout=180).splitlines())
                must(bool(expected) and expected.issubset(downloaded),
                     dict(expected=sorted(expected), downloaded=sorted(downloaded)))
                if expected_stable_source:
                    releases = run(['rpm', '-qp', '--qf', '%{NAME} %{RELEASE}\n', *files], timeout=180).splitlines()
                    must(all('git'+expected_stable_source[:7] in line for line in releases
                             if line.split()[0] in expected), releases)
                return dict(status=data, arctic_download_count=len(files),
                            arctic_downloaded_names=sorted(downloaded), signatures=signatures)
            check('signed-offline-update-ready', staged_update)
        else:
            check('dnf-update', lambda: run(['dnf5', '-y', '--refresh', 'upgrade'], timeout=1800))
        after_rpm = run(['rpm', '-q', 'nix', 'nix-daemon'])
        record(stage, 'engine-version-change', 'passed' if before_rpm != after_rpm else 'unrun', f'{before_rpm} -> {after_rpm}; same version is not upgrade proof')
        if not failed:
            state_file.write_text(json.dumps(dict(boot=Path('/proc/sys/kernel/random/boot_id').read_text(),
                                  profile=str(profile.resolve()), update_method=update_method, arctic_rpms=before_arctic,
                                  expected_stable_source=expected_stable_source)))
    for log in ('/tmp/arctic-release-app.log', '/tmp/arctic-nix-desktop-probe.log'):
        if Path(log).exists():
            print(Path(log).read_text(errors='replace')[-8000:], flush=True)
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
