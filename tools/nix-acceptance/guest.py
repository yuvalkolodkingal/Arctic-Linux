#!/usr/bin/env python3
"""Nix acceptance probes, run as root ONLY inside the disposable QEMU guest.

Desktop/window probe adapted from PR12 tools/reliability/guest.py; PR12 is not merged.

Print one structured serial record per check. GUI probes run as the desktop user,
require a new Mango client and keep it mapped for five seconds.
"""
import configparser
import json
import os
from pathlib import Path
import pwd
import re
import shlex
import signal
import subprocess
import sys
import time
from urllib.parse import urlsplit

NIX_STORE = Path('/nix/store')
WEBKIT_WEB_PROCESS = Path('/usr/libexec/webkitgtk-6.0/WebKitWebProcess')


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
                    *[f'{key}={env[key]}' for key in ('PATH', 'XDG_DATA_DIRS', 'XDG_DATA_HOME',
                        'XDG_CONFIG_HOME', 'XDG_CACHE_HOME') if key in env],
                    *([f'MANGO_SOCKET={env["MANGO_SOCKET"]}'] if 'MANGO_SOCKET' in env else [])]
        except (FileNotFoundError, ProcessLookupError):
            continue
    raise RuntimeError('no non-root Mango session')


def clients(prefix):
    return {str(c['id']): c for c in json.loads(run(prefix + ['mmsg', 'get', 'all-clients']))['clients']}


def user_executable(prefix, name):
    """Resolve using the actual desktop user's environment, never root's PATH."""
    code = ('import json,os,shutil,sys; p=shutil.which(sys.argv[1]); '
            'print(json.dumps(os.path.realpath(p) if p else None))')
    return json.loads(run(prefix + ['python3', '-c', code, name]))


def user_desktop_file(prefix, desktop_id):
    # Match Quickshell's XDG precedence for a top-level desktop ID. Its public
    # DesktopEntry API has no source-path property; never invent one in QML.
    code = ('import json,os,pathlib,sys; '
            'home=os.environ.get("XDG_DATA_HOME") or os.path.join(os.environ["HOME"],".local/share"); '
            'dirs=[home]+(os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share").split(":"); '
            'paths=[pathlib.Path(d)/"applications"/(sys.argv[1]+".desktop") for d in dirs if d]; '
            'print(json.dumps(next((str(p.resolve()) for p in paths if p.is_file()),None)))')
    return json.loads(run(prefix + ['python3', '-c', code, desktop_id]))


def nix_store_output(path):
    path = Path(path).resolve(strict=True)
    try:
        relative = path.relative_to(NIX_STORE)
    except ValueError as exc:
        raise RuntimeError(f'Not a Nix-store export: {path}') from exc
    if not re.fullmatch(r'[0123456789abcdfghijklmnpqrsvwxyz]{32}-.+', relative.parts[0]):
        raise RuntimeError(f'Invalid Nix-store output: {path}')
    return NIX_STORE / relative.parts[0]


def nix_foot_export(prefix, profile):
    """A native foot.desktop/binary with the same app ID is not Nix evidence."""
    executable = (profile / 'bin/foot').resolve(strict=True)
    output = nix_store_output(executable)
    if executable != output / 'bin/foot' or not os.access(executable, os.X_OK):
        raise RuntimeError(f'Profile does not export executable Nix Foot: {executable}')
    if user_executable(prefix, 'foot') != str(executable):
        raise RuntimeError('Desktop user PATH does not resolve Foot to the Arctic Nix profile')
    entry = (profile / 'share/applications/foot.desktop').resolve(strict=True)
    if not entry.is_relative_to(output):
        raise RuntimeError('Foot desktop file is outside its exact profile store output')
    if user_desktop_file(prefix, 'foot') != str(entry):
        raise RuntimeError('Desktop user XDG precedence does not select the private-profile Foot export')
    data = configparser.ConfigParser(interpolation=None)
    data.read_string(entry.read_text())
    section = data['Desktop Entry']
    argv = shlex.split(section['Exec'])
    # Inspect only; never evaluate or execute a raw desktop Exec string.
    if (not argv or (argv[0] != 'foot' and
            (not Path(argv[0]).is_absolute() or Path(argv[0]).resolve(strict=True) != executable))):
        raise RuntimeError(f'Nix Foot desktop export does not name its profile binary: {argv}')
    # The union profile can contain symlinked icon directories; walk the exact
    # package output and then prove each icon is exported through the profile.
    icons = [p.resolve(strict=True) for p in (output / 'share/icons').rglob(section['Icon'] + '.*')
             if p.is_file() and (profile / p.relative_to(output)).resolve(strict=True) == p.resolve(strict=True)]
    if not icons or any(not p.is_relative_to(output) for p in icons):
        raise RuntimeError('Nix Foot profile icon exports are missing or outside its store output')
    return dict(executable=str(executable), output=str(output), desktop_file=str(entry),
                exec_string=section['Exec'], exec_program=argv[0], icon_name=section['Icon'],
                icon_files=[str(p) for p in icons])


def nix_desktop_entry(selected, export):
    """Check the entry actually selected by the live Quickshell model."""
    if (not isinstance(selected, dict) or selected.get('id') != 'foot'
            or selected.get('execString') != export['exec_string']):
        raise RuntimeError(f'DesktopEntries selected a different/native Foot export: {selected}')
    command = selected.get('command')
    if (not isinstance(command, list) or not command or not all(isinstance(p, str) for p in command)
            or command[0] != export['exec_program']):
        raise RuntimeError(f'DesktopEntries does not launch the profile Foot binary: {command}')
    if (selected.get('icon') != export['icon_name'] or selected.get('iconReady') is not True
            or selected.get('iconPresent') is not True
            or selected.get('iconPath') != 'image://icon/' + export['icon_name']):
        raise RuntimeError(f'DesktopEntries did not render the exported Foot icon name: {selected}')
    return selected


def process_identity(proc, uid):
    if proc.stat().st_uid != uid:
        raise RuntimeError('Window PID is not owned by the desktop user')
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    if fields[0] in ('Z', 'X'):
        raise RuntimeError('Window PID is not a live process')
    return dict(pid=int(proc.name), start_ticks=int(fields[19]),
                executable=str((proc / 'exe').resolve(strict=True)))


def process_snapshot(proc_root, uid):
    seen = set()
    for proc in proc_root.glob('[0-9]*'):
        try:
            value = process_identity(proc, uid)
            seen.add((value['pid'], value['start_ticks']))
        except (OSError, ValueError, IndexError, RuntimeError):
            continue
    return seen


def nix_window_identity(client, before_processes, expected_executable, uid, proc_root=Path('/proc')):
    """Bind a new native Wayland surface to fresh exact-output Foot credentials."""
    pid = client.get('pid')
    if (type(pid) is not int or pid <= 1 or client.get('is_xwayland') is not False
            or client.get('is_visible') is not True
            or client.get('width', 0) <= 0 or client.get('height', 0) <= 0):
        raise RuntimeError(f'Foot client lacks a visible native Wayland PID: {client}')
    value = process_identity(proc_root / str(pid), uid)
    if (value['pid'], value['start_ticks']) in before_processes:
        raise RuntimeError('Foot window belongs to a stale/pre-existing process')
    expected = Path(expected_executable)
    # Nix's GApps hook can wrap bin/foot with a shell script; only the ELF in
    # that same exact store output is allowed, not an arbitrary other Nix Foot.
    if Path(value['executable']) not in (expected, expected.with_name('.foot-wrapped')):
        raise RuntimeError(f'Foot window PID runs a different/native executable: {value}')
    with open(value['executable'], 'rb') as binary:
        if binary.read(4) != b'\x7fELF':
            raise RuntimeError('Foot window PID has not executed its Nix ELF')
    return value


def app(prefix, command, pattern, timeout=300, expected_executable=None, proc_root=Path('/proc')):
    before = set(clients(prefix))
    uid = pwd.getpwnam(prefix[2]).pw_uid if expected_executable else None
    before_processes = process_snapshot(proc_root, uid) if expected_executable else set()
    proof = None
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
                    key = sorted(new)[0]
                    if expected_executable:
                        proof = nix_window_identity(current[key], before_processes, expected_executable, uid, proc_root)
                    time.sleep(5)
                    later = clients(prefix)
                    if key in later:
                        if expected_executable:
                            persisted = nix_window_identity(later[key], before_processes, expected_executable, uid, proc_root)
                            if persisted != proof:
                                raise RuntimeError('Foot window changed PID/start identity during persistence check')
                        return f'{command}: new mapped client {key} persisted 5s; Nix identity {proof}'
                time.sleep(2)
            raise RuntimeError(f'{command}: no persistent new window; see /tmp/arctic-release-app.log')
        finally:
            if proof:
                # DesktopEntry.execute detaches. Close only the newly proven test
                # process, and never signal a recycled PID or unrelated Foot.
                try:
                    if process_identity(proc_root / str(proof['pid']), uid) == proof:
                        os.kill(proof['pid'], signal.SIGTERM)
                except (OSError, ValueError, IndexError, RuntimeError):
                    pass
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()


def nix_foot_app(prefix, profile, command=None):
    export = nix_foot_export(prefix, profile)
    return app(prefix, command or [str(profile / 'bin/foot'), '-e', 'sleep', '30'],
               'foot', expected_executable=export['executable'])


def wait_desktop_rescan(scan_epoch, before):
    if type(before) is not int:
        raise RuntimeError('DesktopEntries pre-refresh epoch is unavailable')
    for _ in range(20):
        current = scan_epoch()
        if type(current) is int and current > before:
            return current
        time.sleep(1)
    raise RuntimeError('DesktopEntries did not complete a hot rescan after the profile refresh')


def offline_foot_cycle(prefix, profile, export, selected, scan_epoch):
    """No flake evaluation: cached store-path add/remove/rollback and hot exports."""
    nix = prefix + ['/usr/bin/nix', '--extra-experimental-features', 'nix-command',
                    '--store', 'daemon', '--offline', 'profile']
    original_link = os.readlink(profile)
    original_output = str(profile.resolve(strict=True))
    listing = json.loads(run(nix + ['list', '--profile', str(profile), '--json']))
    names = [name for name, element in listing['elements'].items()
             if export['output'] in element.get('storePaths', [])]
    if len(names) != 1:
        raise RuntimeError(f'Expected one private-profile Foot store export: {names}')

    def refresh():
        # Exercise the installed helper's exact refresh mechanism after direct
        # offline Nix operations, without copying or synthesizing desktop files.
        before = scan_epoch()
        run(prefix + ['python3', '-c',
            'import sys; sys.path.insert(0, "/usr/share/arctic/shell/scripts"); '
            'import nixlib; nixlib.refresh_desktop()'])
        return wait_desktop_rescan(scan_epoch, before)

    def absent():
        for relative in ('bin/foot', 'share/applications/foot.desktop'):
            path = profile / relative
            if path.exists() or path.is_symlink():
                raise RuntimeError(f'Removed Foot export remains: {path}')
        if user_executable(prefix, 'foot') == export['executable']:
            raise RuntimeError('Desktop user PATH still resolves removed Nix Foot')
        current_entry = user_desktop_file(prefix, 'foot')
        if current_entry == export['desktop_file']:
            raise RuntimeError('XDG still selects the removed private-profile Foot export')
        fallback_exec = None
        if current_entry:
            data = configparser.ConfigParser(interpolation=None)
            data.read(current_entry)
            fallback_exec = data['Desktop Entry']['Exec']
        # Native and Nix Foot can have identical Exec/Icon metadata. Require
        # the completed rescan, absent exports and changed PATH separately.
        for _ in range(20):
            value = selected()
            if ((value is None and fallback_exec is None) or
                    (isinstance(value, dict) and value.get('execString') == fallback_exec)):
                return value
            time.sleep(1)
        raise RuntimeError('DesktopEntries retained stale removed Nix Foot')

    run(nix + ['remove', '--profile', str(profile), names[0]], timeout=300)
    refresh()
    removed = absent()
    run(nix + ['add', '--profile', str(profile), export['output']], timeout=300)
    refresh()
    restored = nix_foot_export(prefix, profile)
    for _ in range(20):
        try:
            nix_desktop_entry(selected(), restored)
            break
        except (RuntimeError, OSError):
            time.sleep(1)
    else:
        raise RuntimeError('Offline cached Foot add did not refresh its selected export')
    window = nix_foot_app(prefix, profile)
    run(nix + ['rollback', '--profile', str(profile)], timeout=300)
    refresh()
    absent()
    run(nix + ['rollback', '--profile', str(profile)], timeout=300)
    refresh()
    if os.readlink(profile) != original_link or str(profile.resolve(strict=True)) != original_output:
        raise RuntimeError('Offline Foot cycle did not restore the original profile generation')
    nix_foot_export(prefix, profile)
    return dict(removed_selected_entry=removed, cached_store=export['output'],
                restored_generation=original_link, restored_profile_output=original_output, window=window,
                mode='--offline cached store path; no flake evaluation')


def zen_browser(prefix, command=None):
    """Exercise the shipped Firefox-based browser through its exported launcher."""
    ref = 'app.zen_browser.zen'
    entry = '/var/lib/flatpak/exports/share/applications/' + ref + '.desktop'
    run(prefix + ['test', '-r', entry])
    info = run(prefix + ['flatpak', 'info', '--system', ref])
    commit = run(prefix + ['flatpak', 'info', '--system', '--show-commit', ref])
    try:
        window = app(prefix, command or ['gtk-launch', ref], r'zen')
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


def configured_browser(paths):
    command = None
    for path in paths:
        if path.is_file():
            for line in path.read_text().splitlines():
                if line.startswith('browser='):
                    command = shlex.split(line.split('=', 1)[1])
    allowed = {('epiphany',): 'epiphany', ('gtk-launch', 'org.gnome.Epiphany'): 'epiphany',
               ('firefox',): 'firefox', ('gtk-launch', 'org.mozilla.firefox'): 'firefox',
               ('gtk-launch', 'app.zen_browser.zen'): 'zen'}
    if tuple(command or []) not in allowed:
        raise RuntimeError(f'Configured browser lacks a maintained non-Chromium acceptance path: {command}')
    return allowed[tuple(command)]


def browser_choice(prefix):
    code = ('import json,os,pathlib; print(json.dumps(str(pathlib.Path('
            'os.environ.get("XDG_CONFIG_HOME") or pathlib.Path.home()/".config")/"arctic/default-apps")))')
    user_config = Path(json.loads(run(prefix + ['python3', '-c', code])))
    return configured_browser([Path('/etc/arctic/default-apps'), user_config])


def offline_browser_fixture(prefix):
    # Create as the actual desktop user. A unique title prevents an older tab
    # from supplying evidence; no homepage/network request is needed to render.
    code = '''import json,os,pathlib,tempfile,uuid
root=pathlib.Path(os.environ.get("XDG_CACHE_HOME") or pathlib.Path.home()/".cache")/"arctic-acceptance"
root.mkdir(parents=True,exist_ok=True,mode=0o700)
folder=pathlib.Path(tempfile.mkdtemp(prefix="browser-",dir=root))
title="Arctic offline browser acceptance "+uuid.uuid4().hex
page=folder/"browser.html"
page.write_text("<!doctype html><html lang=en><meta charset=utf-8><title>"+title+"</title>"
 "<h1>Arctic offline browser acceptance</h1><p>Local page rendered without network access.</p>"
 "<label>Accessible text input <input value=Arctic></label>"
 "<script>document.title="+json.dumps(title+" JS ready")+";</script></html>")
print(json.dumps(dict(uri=page.as_uri(),title=title+" JS ready",path=str(page),uid=os.geteuid())))'''
    fixture = json.loads(run(prefix + ['python3', '-c', code]))
    if fixture['uid'] != pwd.getpwnam(prefix[2]).pw_uid or not fixture['uri'].startswith('file:///'):
        raise RuntimeError('Offline browser fixture is not a desktop-user local file')
    return fixture


def browser_handlers(prefix, kind):
    wanted = {'epiphany': 'org.gnome.Epiphany.desktop', 'firefox': 'org.mozilla.firefox.desktop',
              'zen': 'app.zen_browser.zen.desktop'}[kind]
    values = {mime: run(prefix + ['xdg-mime', 'query', 'default', mime]) for mime in
              ('text/html', 'application/xhtml+xml', 'x-scheme-handler/http', 'x-scheme-handler/https')}
    if any(value != wanted for value in values.values()):
        raise RuntimeError(f'Configured browser {wanted} does not own its HTML/HTTP/HTTPS handlers: {values}')
    return values


def archive_tools(prefix):
    programs = {'7zip': ('7z', '7zz'), **{name: (name,) for name in
                ('zip', 'unzip', 'tar', 'xz', 'bzip2', 'zstd', 'cpio')}}
    resolved = {}
    for name, candidates in programs.items():
        for command in candidates:
            executable = user_executable(prefix, command)
            if executable:
                resolved[name] = executable
                break
        else:
            raise RuntimeError(f'Archive helper is missing from desktop user PATH: {name}')
    return dict(executables=resolved, scope='PATH availability; no archive-format roundtrip claim')


def process_descends_from(proc_root, pid, ancestor):
    seen = set()
    while pid > 1 and pid not in seen:
        seen.add(pid)
        fields = (proc_root / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()
        pid = int(fields[1])
        if pid == ancestor:
            return True
    return False


def webkit_sandbox(expected_ui, uid, proc_root=Path('/proc')):
    """Fail closed: evidence must belong to this browser, not an older web app."""
    ui_pid = expected_ui['pid']
    ui = proc_root / str(ui_pid)
    if process_identity(ui, uid) != expected_ui:
        raise RuntimeError('Browser UI process identity changed before sandbox inspection')
    ui_namespaces = {name: os.readlink(ui / 'ns' / name) for name in ('mnt', 'pid')}
    def safe_environment(proc):
        env = dict(item.split('=', 1) for item in
            (proc / 'environ').read_bytes().decode().split('\0') if '=' in item)
        if any('WEBKIT' in key and 'DISABLE_SANDBOX' in key for key in env):
            raise RuntimeError('Browser process has a sandbox-disabling environment')
    safe_environment(ui)
    found = []
    for proc in proc_root.glob('[0-9]*'):
        try:
            executable = (proc / 'exe').resolve(strict=True)
            if executable != WEBKIT_WEB_PROCESS:
                continue
            if not process_descends_from(proc_root, int(proc.name), ui_pid):
                continue
            identity = process_identity(proc, uid)
            status = dict(line.split(':', 1) for line in (proc / 'status').read_text().splitlines() if ':' in line)
            if status.get('Seccomp', '').strip() != '2' or status.get('NoNewPrivs', '').strip() != '1':
                raise RuntimeError('Browser WebKit process lacks Seccomp2/NoNewPrivs1')
            namespaces = {name: os.readlink(proc / 'ns' / name) for name in ('mnt', 'pid')}
            if any(namespaces[name] == ui_namespaces[name] for name in namespaces):
                raise RuntimeError('Browser WebKit process shares host/UI mount or PID namespace')
            safe_environment(proc)
            if process_identity(proc, uid) != identity:
                raise RuntimeError('Browser WebKit process identity changed during sandbox inspection')
            found.append(dict(**identity, namespaces=namespaces,
                              seccomp=2, no_new_privs=1, descendant_of=ui_pid))
        except (FileNotFoundError, ProcessLookupError):
            continue
    if not found:
        raise RuntimeError('No verified descendant WebKitGTK6 web process; sandbox evidence unavailable')
    if process_identity(ui, uid) != expected_ui:
        raise RuntimeError('Browser UI process identity changed during sandbox inspection')
    return found


def browser(prefix):
    user = pwd.getpwnam(prefix[2])
    kind = browser_choice(prefix)
    fixture = offline_browser_fixture(prefix)
    handlers = browser_handlers(prefix, kind)
    command = ['/usr/bin/arctic-open', 'browser', fixture['uri']]
    if kind == 'zen':
        return dict(configured_browser=kind, handlers=handlers, fixture=fixture,
                    window=zen_browser(prefix, command))
    before = set(clients(prefix))
    old_processes = process_snapshot(Path('/proc'), user.pw_uid)
    executable = user_executable(prefix, kind)
    if not executable or not executable.startswith('/usr/'):
        raise RuntimeError(f'Expected configured native Fedora browser, got {executable}')
    versions = run(['rpm', '-q', kind, *(['webkitgtk6.0', 'epiphany-runtime'] if kind == 'epiphany' else [])])
    window = app(prefix, command, 'epiphany|org.gnome.Epiphany' if kind == 'epiphany' else 'firefox')
    time.sleep(45)
    current = [value for key, value in clients(prefix).items() if key not in before
               and re.search('epiphany' if kind == 'epiphany' else 'firefox',
                             str(value.get('appid', value.get('app_id', ''))), re.I)]
    if (len(current) != 1 or type(current[0].get('pid')) is not int
            or current[0].get('is_xwayland') is not False or current[0].get('is_visible') is not True
            or current[0].get('width', 0) <= 0 or current[0].get('height', 0) <= 0
            or fixture['title'] not in current[0].get('title', '')):
        raise RuntimeError('Configured browser did not retain one identifiable native Wayland window')
    proof = process_identity(Path('/proc') / str(current[0]['pid']), user.pw_uid)
    if proof['executable'] != executable or (proof['pid'], proof['start_ticks']) in old_processes:
        raise RuntimeError(f'Browser window belongs to a different or pre-existing binary: {proof}')
    sandbox = webkit_sandbox(proof, user.pw_uid) if kind == 'epiphany' else 'Firefox sandbox qualification remains separate'
    return dict(configured_browser=kind, versions=versions, mapped_window=window,
                fixture=fixture, handlers=handlers,
                ui_process=proof, webkit_sandbox=sandbox,
                visual_review='retained45s; startup/sandbox smoke, not full media/a11y/site qualification')


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
    configured = check('configured-browser-choice', lambda: browser_choice(prefix))
    if configured != 'zen' and Path('/var/lib/flatpak/exports/share/applications/app.zen_browser.zen.desktop').is_file():
        check('optional-installed-zen', lambda: zen_browser(prefix))
    check('configured-files', lambda: app(prefix, ['/usr/bin/arctic-open', 'files'],
          'nautilus|thunar|pcmanfm|org.gnome.Nautilus|yazi'))
    check('configured-terminal', lambda: app(prefix, ['/usr/bin/arctic-open', 'terminal', '-e', 'sleep', '30'],
          'foot|kitty|alacritty|ghostty'))
    if configured == 'epiphany':
        check('configured-editor', lambda: app(prefix, ['/usr/bin/arctic-open', 'editor'], 'featherpad'))
        check('native-media-player', lambda: app(prefix, ['/usr/bin/celluloid'], 'celluloid|io.github.celluloid_player.Celluloid'))
        check('native-archive-manager', lambda: app(prefix, ['/usr/bin/xarchiver'], 'xarchiver'))
        check('native-archive-helpers', lambda: archive_tools(prefix))

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
        check('graphical-after-reboot', lambda: nix_foot_app(prefix, profile))
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
 property int scanEpoch: 0
 property var entry: DesktopEntries.applications.values.find(e => e.id === "foot") || null
 property Image iconProbe: Image { source: probeRoot.entry ? Quickshell.iconPath(probeRoot.entry.icon) : "" }
 Connections { target: DesktopEntries; function onApplicationsChanged() { probeRoot.scanEpoch++; } }
 IpcHandler {
  target: "nixacceptance"
  function seen(): bool { return DesktopEntries.byId("foot") !== null; }
  function iconReady(): bool { return probeRoot.iconProbe.status === Image.Ready; }
  function epoch(): int { return probeRoot.scanEpoch; }
  function selected(): string {
   const e = DesktopEntries.byId("foot");
   return JSON.stringify(e ? {id: e.id, execString: e.execString, command: e.command,
    icon: e.icon, iconPath: Quickshell.iconPath(e.icon), iconPresent: Quickshell.hasThemeIcon(e.icon),
    iconReady: probeRoot.iconProbe.status === Image.Ready} : null);
  }
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
    scan_before_install = check('desktop-preinstall-epoch', lambda: int(run(prefix + probe_cmd + ['epoch'])))
    check('install', lambda: run(nix + ['install', 'hello', 'foot'], timeout=1200))
    def selected():
        return json.loads(run(prefix + probe_cmd + ['selected']))

    def scan_epoch():
        return int(run(prefix + probe_cmd + ['epoch']))

    def profile_entry():
        export = nix_foot_export(prefix, profile)
        last = ''
        for _ in range(20):
            try:
                return nix_desktop_entry(selected(), export)
            except (RuntimeError, OSError) as exc:
                last = str(exc)
            time.sleep(1)
        raise RuntimeError('Nix Foot model/command/icon identity did not refresh: ' + last)

    check('profile-export-identity', lambda: nix_foot_export(prefix, profile))
    check('desktop-hot-install-rescan', lambda: wait_desktop_rescan(scan_epoch, scan_before_install))
    check('desktop-after-install', profile_entry)
    check('desktop-entry-launch', lambda: (profile_entry(),
          nix_foot_app(prefix, profile, probe_cmd + ['launch'])))
    check('hello', lambda: run(prefix + [str(profile/'bin/hello')]))
    check('desktop-file', lambda: must(bool(list((profile/'share/applications').glob('*.desktop'))), 'profile contains desktop entries'))
    check('icons', lambda: must((profile/'share/icons').is_dir(), 'profile contains icon data'))
    check('graphical-foot', lambda: nix_foot_app(prefix, profile))

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
    check('offline-foot-profile-exports', lambda: offline_foot_cycle(
          prefix, profile, nix_foot_export(prefix, profile), selected, scan_epoch))
    check('desktop-after-offline-rollback', profile_entry)
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
