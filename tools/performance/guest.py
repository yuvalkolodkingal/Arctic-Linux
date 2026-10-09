#!/usr/bin/env python3
"""Reproducible measurements, ONLY in a disposable QEMU guest.

Use with tools/test-install.sh --guest-check tools/performance/guest.py.
Never drops caches, changes services, removes packages, or alters kernel knobs.
The observer's allocations are included and identified in process snapshots.
"""
import hashlib
import json
import os
from pathlib import Path
import pwd
import resource
import re
import select
import statistics
import subprocess
import sys
import time
from contextlib import contextmanager


MAPPING_OBSERVER = 'mango-socket-worker-v2-autonomous'
MAPPING_POLL_SECONDS = .001
SAMPLER = 'cpu-30-pss-6-v6-bounded-native-query'
ROLE_SAMPLER = 'cpu-30-pss-6-v8-autonomous-role-first-use'
ROLE_POLL_SECONDS = .00005
ROLE_ORDER = ('terminal', 'files', 'browser')
EXPECTED_ROLES = {'baseline': dict(terminal='kitty', files='nautilus', browser='zen'),
                  'candidate': dict(terminal='foot', files='pcmanfm', browser='gnome-web')}
ROLE_APPS = {
    'kitty': dict(role='terminal', configured=('kitty',), program='kitty', rpm='kitty',
                  appids=('kitty',), cold_paths=('cache/kitty',)),
    'foot': dict(role='terminal', configured=('foot',), program='foot', rpm='foot',
                 appids=('foot',), cold_paths=('cache/foot',)),
    'nautilus': dict(role='files', configured=('nautilus',), program='nautilus', rpm='nautilus',
                     appids=('org.gnome.nautilus',), cold_paths=('cache/nautilus', 'data/nautilus')),
    'pcmanfm': dict(role='files', configured=('pcmanfm',), program='pcmanfm', rpm='pcmanfm',
                    appids=('pcmanfm',), cold_paths=('cache/pcmanfm', 'data/pcmanfm')),
    'zen': dict(role='browser', configured=('gtk-launch app.zen_browser.zen',), program='flatpak',
               flatpak='app.zen_browser.zen', desktop='app.zen_browser.zen.desktop',
               appids=('zen', 'app.zen_browser.zen'), cold_paths=('home/.var/app/app.zen_browser.zen',)),
    'gnome-web': dict(role='browser', configured=('epiphany', 'gtk-launch org.gnome.Epiphany'),
                     program='epiphany', rpm='epiphany-runtime', desktop_rpm='epiphany',
                     desktop='org.gnome.Epiphany.desktop',
                     appids=('org.gnome.epiphany', 'epiphany'),
                     cold_paths=('cache/epiphany', 'data/epiphany', 'config/epiphany')),
}

# One worker enters the actual desktop user/environment before timing begins.
# Mango 0.17.3's mmsg uses this same newline-delimited Unix-socket protocol.
# A fresh socket is required for each get: Mango closes one-shot connections.
# A watch arrival has no server timestamp and is not an exact map timestamp.
CLIENT_QUERY_WORKER = r'''
import json, os, select, socket, sys, time
path = os.environ['MANGO_INSTANCE_SIGNATURE']
def query():
    started = time.monotonic_ns()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(path)
        peer.sendall(b'get all-clients\n')
        chunks, size = [], 0
        while True:
            chunk = peer.recv(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > 4 * 1024 * 1024:
                raise RuntimeError('Unbounded Mango response')
            chunks.append(chunk)
    value = json.loads(b''.join(chunks))
    if not isinstance(value, dict) or not isinstance(value.get('clients'), list):
        raise RuntimeError('Invalid Mango client response')
    identities = set()
    for client in value['clients']:
        if not isinstance(client, dict) or 'id' not in client or str(client['id']) in identities:
            raise RuntimeError('Invalid or duplicate Mango client identity')
        identities.add(str(client['id']))
    return value, started, time.monotonic_ns()

# Unbuffered stdin avoids hiding cancellation/EOF behind a TextIO buffer.
# No parent request or subprocess is needed between these read-only polls.
with os.fdopen(os.dup(sys.stdin.fileno()), 'rb', buffering=0) as control:
    while True:
        line = control.readline(65536)
        if not line:
            break
        command = json.loads(line)
        if command['kind'] == 'get':
            payload, started, finished = query()
            result = dict(payload=payload, query_seconds=(finished-started)/1e9)
        elif command['kind'] == 'observe':
            started_ns = command['started_ns']
            lower_ns = started_ns
            before = set(command['before'])
            pattern = command['pattern']
            traces = []
            until_ns = started_ns + int(command['timeout'] * 1e9)
            while time.monotonic_ns() < until_ns:
                if select.select([control], [], [], 0)[0]:
                    # Parent closes stdin on cancellation. Unexpected pipelined
                    # commands fail rather than produce an ambiguous response.
                    if control.read(1):
                        raise RuntimeError('Unexpected observer command while mapping')
                    sys.exit(0)
                payload, query_started, query_finished = query()
                traces.append(dict(socket_seconds=(query_finished-query_started)/1e9,
                    started_monotonic_ns=query_started, finished_monotonic_ns=query_finished))
                if len(traces) > 32768:
                    raise RuntimeError('Mapping observation exceeded bounded trace capacity')
                windows = [c for c in payload['clients'] if str(c['id']) not in before and (
                    pattern in (str(c.get('appid', c.get('app_id', ''))) + ' ' + str(c.get('title', ''))).lower()
                    if isinstance(pattern, str) else str(c.get('appid', c.get('app_id', ''))).lower() in pattern)]
                if windows:
                    result = dict(payload=payload, windows=windows, lower_ns=max(lower_ns, started_ns),
                                  upper_ns=query_finished, query_roundtrips=traces)
                    break
                # A negative query only proves absence at an unknown point
                # between its start and end. Its START is the conservative lower
                # bound; using its end could exclude the actual mapping event.
                lower_ns = query_started
                time.sleep(command['poll_seconds'])
            else:
                result = dict(payload={'clients': []}, windows=[], timed_out=True,
                              query_roundtrips=traces)
        else:
            raise RuntimeError('Unexpected observer command')
        result['uid'] = os.getuid()
        print(json.dumps(result, separators=(',', ':')), flush=True)
'''


class NativeClientQuery:
    """Bounded read-only queries and autonomous worker-side mapping timestamps."""
    def __init__(self, prefix):
        self.prefix = prefix
        self.process = None
        self.buffer = b''
        self.roundtrips = []
        self.pending = None

    def __enter__(self):
        self.process = subprocess.Popen(self.prefix + ['python3', '-u', '-c', CLIENT_QUERY_WORKER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        return self

    def _send(self, command):
        if self.pending is not None:
            raise RuntimeError('Native observer already has a pending operation')
        self.pending = command
        self.process.stdin.write((json.dumps(command) + '\n').encode())

    def _receive(self, timeout, child=None):
        started = time.monotonic()
        until = started + timeout
        while b'\n' not in self.buffer:
            remaining = until - time.monotonic()
            if remaining <= 0:
                raise RuntimeError('Native Mango observer timed out; no CLI fallback')
            if child is not None and child.poll() not in (None, 0):
                raise RuntimeError('Observed application exited before mapping')
            if not select.select([self.process.stdout], [], [], min(remaining, .1))[0]:
                continue
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                self.process.wait(timeout=1)
                raise RuntimeError('Native Mango observer disconnected: ' +
                    self.process.stderr.read(12000).decode(errors='replace'))
            self.buffer += chunk
            if len(self.buffer) > 4 * 1024 * 1024:
                raise RuntimeError('Unbounded native observer response')
        line, self.buffer = self.buffer.split(b'\n', 1)
        if self.buffer:
            raise RuntimeError('Unsolicited native observer response')
        value = json.loads(line)
        if self.prefix[:2] == ['runuser', '-u'] and value['uid'] != pwd.getpwnam(self.prefix[2]).pw_uid:
            raise RuntimeError('Native observer did not use the desktop user')
        result = {}
        for client in value['payload']['clients']:
            if not isinstance(client, dict) or 'id' not in client or str(client['id']) in result:
                raise RuntimeError('Invalid or duplicate Mango client identity')
            result[str(client['id'])] = client
        value['clients_by_id'] = result
        self.pending = None
        return value, time.monotonic()-started

    def query(self):
        self._send(dict(kind='get'))
        value, elapsed = self._receive(3)
        self.roundtrips.append(dict(parent_seconds=elapsed,
                                    socket_seconds=value['query_seconds'], uid=value['uid']))
        return value['clients_by_id']

    def begin_observation(self, before, pattern, started_ns, timeout, poll_seconds):
        self._send(dict(kind='observe', before=sorted(before), pattern=pattern,
                        started_ns=started_ns, timeout=timeout, poll_seconds=poll_seconds))

    def finish_observation(self, child, started_ns, timeout):
        value, _ = self._receive(timeout+3, child)
        if value.get('timed_out'):
            return None
        lower, upper = value['lower_ns'], value['upper_ns']
        if (any(type(n) is not int for n in (lower, upper))
                or not started_ns <= lower <= upper <= time.monotonic_ns()):
            raise RuntimeError('Invalid worker mapping timestamp bracket')
        identities = value['clients_by_id']
        if not value['windows'] or any(str(c['id']) not in identities for c in value['windows']):
            raise RuntimeError('Invalid worker mapped-window identities')
        self.roundtrips.extend(dict(trace, uid=value['uid']) for trace in value['query_roundtrips'])
        return value

    def __exit__(self, *args):
        if self.process is None:
            return
        self.process.stdin.close()
        try:
            # Let runuser reap the worker after natural stdin EOF, including
            # cancellation while autonomously polling. Only our worker is owned.
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.process.wait(timeout=3)
        finally:
            self.process.stdout.close()
            self.process.stderr.close()


def run(argv, timeout=45):
    try:
        return subprocess.check_output(argv, text=True, stderr=subprocess.STDOUT,
                                       timeout=timeout).strip()
    except subprocess.CalledProcessError as error:
        raise RuntimeError(f'Command exited {error.returncode}: {argv!r}\n{error.output[-12000:]}') from error


def emit(check, value):
    print('ARCTIC-PERFORMANCE ' + json.dumps(dict(stage=sys.argv[1], check=check, value=value)), flush=True)


def session_environment(proc_root, uid, runtime, display, base):
    """Keep login paths/session identity; obtain post-exec IPC from children.

    A terminal's shell can add its own XDG_DATA_DIRS. Requiring every child to
    agree would discard the desktop's Flatpak/Nix exports and report a false
    default browser. Keep the login's actual session identity and Qt backend.
    """
    fields = ('PATH', 'XDG_CONFIG_HOME', 'XDG_CONFIG_DIRS', 'XDG_DATA_HOME',
              'XDG_DATA_DIRS', 'XDG_CACHE_HOME', 'DISPLAY', 'XAUTHORITY',
              'XDG_SESSION_ID', 'XDG_SEAT', 'XDG_VTNR', 'XDG_CURRENT_DESKTOP',
              'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION', 'LANG', 'GDK_BACKEND',
              'QT_QPA_PLATFORM', 'MANGO_SOCKET')
    inherited = {key: base[key] for key in fields if base.get(key)}
    signatures = set()
    children = []
    for child in proc_root.glob('[0-9]*'):
        try:
            if child.stat().st_uid != uid:
                continue
            env = dict(item.split('=', 1) for item in
                       (child/'environ').read_bytes().decode().split('\0') if '=' in item)
            if (env.get('XDG_RUNTIME_DIR') == str(runtime)
                    and env.get('WAYLAND_DISPLAY') == display
                    and env.get('MANGO_INSTANCE_SIGNATURE')):
                signatures.add(env['MANGO_INSTANCE_SIGNATURE'])
                children.append(env)
        except (OSError, UnicodeError):
            continue
    if len(signatures) != 1:
        raise RuntimeError(f'Expected one Mango IPC signature, found {len(signatures)}')
    # Xwayland's display can appear after Mango's exec. Portal/application Qt
    # and GTK backend overrides are not session settings: inheriting them can
    # change Quickshell's display identity and hide the live shell from IPC.
    for key in ('DISPLAY', 'XAUTHORITY'):
        if key not in inherited:
            values = {env[key] for env in children if env.get(key)}
            if len(values) == 1:
                inherited[key] = values.pop()
    inherited['MANGO_INSTANCE_SIGNATURE'] = signatures.pop()
    if not all(inherited.get(key) for key in ('PATH', 'XDG_DATA_DIRS', 'XDG_SESSION_ID')):
        raise RuntimeError('Missing actual desktop PATH, XDG_DATA_DIRS or session identity')
    return inherited


def desktop():
    for path in Path('/proc').glob('[0-9]*'):
        try:
            if (path / 'comm').read_text().strip() != 'mango' or path.stat().st_uid == 0:
                continue
            user = pwd.getpwuid(path.stat().st_uid)
            runtime = Path('/run/user') / str(user.pw_uid)
            sockets = [p for p in runtime.glob('wayland-*') if p.is_socket()]
            if len(sockets) != 1:
                continue
            base = dict(item.split('=', 1) for item in
                        (path/'environ').read_bytes().decode().split('\0') if '=' in item)
            inherited = session_environment(Path('/proc'), user.pw_uid, runtime, sockets[0].name, base)
            return ['runuser', '-u', user.pw_name, '--', 'env', '-i',
                    'HOME=' + user.pw_dir, 'XDG_RUNTIME_DIR=' + str(runtime),
                    'USER=' + user.pw_name, 'LOGNAME=' + user.pw_name,
                    'WAYLAND_DISPLAY=' + sockets[0].name, 'XDG_SESSION_TYPE=wayland',
                    'DBUS_SESSION_BUS_ADDRESS=unix:path=' + str(runtime/'bus'),
                    *[key + '=' + value for key, value in inherited.items()]]
        except (OSError, UnicodeError, KeyError):
            continue
    raise RuntimeError('No unique non-root Mango session')


def meminfo():
    memory = {}
    for line in Path('/proc/meminfo').read_text().splitlines():
        key, value = line.split(':', 1)
        parts = value.split()
        if len(parts) == 2 and parts[1] == 'kB':
            memory[key] = int(parts[0]) * 1024
    return memory


def snapshot():
    memory = meminfo()
    processes = []
    skipped = []
    for path in Path('/proc').glob('[0-9]*'):
        try:
            values = {}
            for line in (path/'smaps_rollup').read_text().splitlines()[1:]:
                key, value = line.split(':', 1)
                values[key] = int(value.split()[0]) * 1024
            processes.append(dict(pid=int(path.name), name=(path/'comm').read_text().strip(),
                                  pss_bytes=values.get('Pss', 0),
                                  private_bytes=values.get('Private_Clean', 0) + values.get('Private_Dirty', 0)))
        except (OSError, ValueError):
            skipped.append(int(path.name))
    return dict(memory_bytes=memory, process_pss_bytes=sum(p['pss_bytes'] for p in processes),
                process_private_bytes=sum(p['private_bytes'] for p in processes),
                top_processes=sorted(processes, key=lambda p: p['pss_bytes'], reverse=True)[:30],
                observer_pid=os.getpid(), skipped_pids=skipped)


def cpu_ticks():
    values = list(map(int, Path('/proc/stat').read_text().splitlines()[0].split()[1:9]))
    return sum(values), values[3] + values[4]


def cpu_interval(before, idle_before, after, idle_after):
    total, idle = after-before, idle_after-idle_before
    if total <= 0 or not 0 <= idle <= total:
        raise RuntimeError(f'Invalid /proc/stat tick interval: total={total}, idle={idle}')
    return dict(cpu_ticks_delta=total, cpu_idle_ticks_delta=idle,
                cpu_busy_percent=100 * (total-idle) / total,
                cpu_resolution_percent=100 / total,
                cpu_clock_ticks_per_second=os.sysconf('SC_CLK_TCK'))


def clients(prefix):
    return {str(c['id']): c for c in json.loads(run(prefix + ['mmsg', 'get', 'all-clients']))['clients']}


def rpm_inventory():
    """Package-version attribution only; never alter packages or warm all files."""
    records = sorted(run(['rpm', '-qa', '--qf',
                          '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n']).splitlines())
    if not records or any(not record.strip() for record in records):
        raise RuntimeError('Missing RPM inventory')
    text = '\n'.join(records) + '\n'
    relevant = re.compile(r'^(?:mesa|libdrm|wayland|wlroots|gtk[234]|qt6|pango|cairo|harfbuzz|'
                          r'freetype|fontconfig|pixman|vte|libadwaita|glib2|glibc|libstdc\+\+|'
                          r'libepoxy|libxcb|xorg-x11-server-Xwayland|quickshell|mangowm|kitty|'
                          r'foot|epiphany|webkitgtk|pcmanfm|libfm|lxqt|celluloid|mpv|featherpad)')
    return dict(nevra=records, sha256=hashlib.sha256(text.encode()).hexdigest(),
                graphics_text_and_apps=[record for record in records if relevant.match(record)],
                scope='Sorted RPM NEVRA metadata (explicit epoch); not an RPM payload-content digest')


ROLE_STATE_READER = r'''
import hashlib,json,os,pathlib,shutil
home=pathlib.Path.home()
roots=dict(home=home,config=pathlib.Path(os.environ.get('XDG_CONFIG_HOME',home/'.config')),
    data=pathlib.Path(os.environ.get('XDG_DATA_HOME',home/'.local/share')),
    cache=pathlib.Path(os.environ.get('XDG_CACHE_HOME',home/'.cache')))
sources=[];configured={}
for path in (pathlib.Path('/etc/arctic/default-apps'),roots['config']/'arctic/default-apps'):
    if not path.exists():continue
    raw=path.read_bytes();sources.append(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest()))
    for line in raw.decode().splitlines():
        if '=' in line and line.split('=',1)[0] in ('terminal','files','browser'):
            key,value=line.split('=',1);configured[key]=value
programs={name:shutil.which(name) for name in ('kitty','foot','nautilus','pcmanfm','epiphany','flatpak')}
paths=json.loads(__import__('sys').argv[1]);present=[]
for relative in paths:
    root,rest=relative.split('/',1);path=roots[root]/rest
    if path.exists():present.append(str(path))
running=[]
for path in pathlib.Path('/proc').glob('[0-9]*'):
    try:
        if path.stat().st_uid!=os.getuid():continue
        name=path.joinpath('comm').read_text().strip().lower()
        if name in ('kitty','foot','nautilus','pcmanfm','epiphany','zen','zen-bin'):
            running.append(dict(pid=int(path.name),name=name))
    except OSError:pass
print(json.dumps(dict(configured=configured,sources=sources,programs=programs,
    prior_role_state_paths=present,running_role_apps=running,uid=os.getuid())))
'''


def declare_roles(prefix, context, inventory):
    image = context.get('image')
    if (image not in EXPECTED_ROLES or context.get('fresh_installed_overlay') is not True
            or context.get('collector') != 'console' or type(context.get('boot')) is not int
            or context.get('boot') not in (1, 2, 3)):
        raise RuntimeError('First-use role measurements require a pristine overlay and console collector')
    expected = EXPECTED_ROLES[image]
    paths = [path for app in expected.values() for path in ROLE_APPS[app]['cold_paths']]
    state = json.loads(run(prefix + ['python3', '-c', ROLE_STATE_READER, json.dumps(paths)]))
    if state['uid'] != pwd.getpwnam(prefix[2]).pw_uid:
        raise RuntimeError('Role declaration did not use the actual desktop user')
    if state['prior_role_state_paths'] or state['running_role_apps']:
        raise RuntimeError('First GUI-role execution is not pristine: ' + json.dumps(state))
    browser = run(prefix + ['xdg-settings', 'get', 'default-web-browser'])
    roles = {}
    for role in ROLE_ORDER:
        ident = expected[role]
        app = ROLE_APPS[ident]
        configured = state['configured'].get(role, '')
        # Original v1.2's offline installer can defer Zen's module while the
        # prebundled app remains the system MIME/fallback browser. Declare that
        # exact legacy case; never substitute an arbitrary installed browser.
        legacy_zen_fallback = image == 'baseline' and ident == 'zen' and not configured
        if configured not in app['configured'] and not legacy_zen_fallback:
            raise RuntimeError(f'Declared {role} differs from installed configuration: {configured!r}')
        if not state['programs'].get(app['program']):
            raise RuntimeError(f'Declared {role} program is missing: {app["program"]}')
        if role == 'browser' and browser != app['desktop']:
            raise RuntimeError('Declared browser differs from actual MIME default: ' + browser)
        if 'rpm' in app:
            packages = [value for value in inventory['nevra']
                        if re.match(re.escape(app['rpm'])+r'-[0-9]+:', value)]
            if len(packages) != 1:
                raise RuntimeError('Missing or ambiguous role RPM: ' + ident)
            package = dict(kind='rpm', nevra=packages[0])
            owner = run(['rpm', '-qf', '--qf', '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}',
                         state['programs'][app['program']]])
            if owner != packages[0]:
                raise RuntimeError('Configured program is not owned by the declared role RPM: ' + ident)
            package['binary_owner'] = owner
            if 'desktop_rpm' in app:
                launchers = [value for value in inventory['nevra']
                             if re.match(re.escape(app['desktop_rpm'])+r'-[0-9]+:', value)]
                if len(launchers) != 1:
                    raise RuntimeError('Missing or ambiguous role launcher RPM: ' + ident)
                desktop_owner = run(['rpm', '-qf', '--qf',
                    '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}',
                    '/usr/share/applications/' + app['desktop']])
                if desktop_owner != launchers[0]:
                    raise RuntimeError('Desktop launcher is not owned by the declared role RPM: ' + ident)
                package['desktop_owner'] = desktop_owner
        else:
            commit = run(prefix + ['flatpak', 'info', '--system', '--show-commit', app['flatpak']])
            if not re.fullmatch('[0-9a-f]{64}', commit):
                raise RuntimeError('Missing installed role Flatpak identity')
            package = dict(kind='flatpak', ref=app['flatpak'], commit=commit)
        roles[role] = dict(id=ident, role=role, configured_command=configured,
                          legacy_system_mime_fallback=legacy_zen_fallback, program_path=state['programs'][app['program']],
                          appids=list(app['appids']), package=package)
    return dict(image=image, roles=roles, configuration_sources=state['sources'],
                default_browser_desktop=browser, pristine_state=state, boot_context=context,
                meaning='First GUI-role execution from a pristine installed profile after normal desktop login; shared OS libraries and host disk caches may already be warm')


def functional_roles(prefix, inventory=None):
    """Verify installed roles without claiming pristine first-use measurements."""
    inventory = rpm_inventory() if inventory is None else inventory
    state = json.loads(run(prefix + ['python3', '-c', ROLE_STATE_READER, '[]']))
    if state['uid'] != pwd.getpwnam(prefix[2]).pw_uid:
        raise RuntimeError('Role declaration did not use the actual desktop user')
    browser = run(prefix + ['xdg-settings', 'get', 'default-web-browser'])
    matches = [(image, expected) for image, expected in EXPECTED_ROLES.items()
               if ROLE_APPS[expected['browser']]['desktop'] == browser
               and all(state['configured'].get(role) in ROLE_APPS[ident]['configured']
                       or (image == 'baseline' and ident == 'zen' and not state['configured'].get(role))
                       for role, ident in expected.items())]
    if len(matches) != 1:
        raise RuntimeError('Missing, mixed or unsupported installed default roles')
    image, expected = matches[0]
    roles = {}
    for role, ident in expected.items():
        app = ROLE_APPS[ident]
        path = state['programs'].get(app['program'])
        if not path:
            raise RuntimeError('Missing installed role program: ' + ident)
        if 'rpm' in app:
            packages = [value for value in inventory['nevra']
                        if re.match(re.escape(app['rpm']) + r'-[0-9]+:', value)]
            owner = run(['rpm', '-qf', '--qf', '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}', path])
            if len(packages) != 1 or owner != packages[0]:
                raise RuntimeError('Role RPM identity or binary owner differs: ' + ident)
            package = dict(kind='rpm', nevra=owner, binary_owner=owner)
            if 'desktop_rpm' in app:
                launchers = [value for value in inventory['nevra']
                             if re.match(re.escape(app['desktop_rpm'])+r'-[0-9]+:', value)]
                desktop_owner = run(['rpm', '-qf', '--qf',
                    '%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}',
                    '/usr/share/applications/' + app['desktop']])
                if len(launchers) != 1 or desktop_owner != launchers[0]:
                    raise RuntimeError('Role desktop launcher owner differs: ' + ident)
                package['desktop_owner'] = desktop_owner
        else:
            commit = run(prefix + ['flatpak', 'info', '--system', '--show-commit', app['flatpak']])
            if not re.fullmatch('[0-9a-f]{64}', commit):
                raise RuntimeError('Missing installed role Flatpak identity')
            package = dict(kind='flatpak', ref=app['flatpak'], commit=commit)
        roles[role] = dict(id=ident, role=role, program_path=path,
                          configured_command=state['configured'].get(role, ''),
                          appids=list(app['appids']), package=package)
    return dict(image=image, roles=roles, default_browser_desktop=browser,
                configuration_sources=state['sources'], first_use_measurement=False)


WORKLOAD_PAGE = '<!doctype html><meta charset="utf-8"><title>Arctic startup fixture</title><h1>Arctic offline browser</h1><p>Local page, no remote resources.</p>'
WORKLOAD_WORKER = r'''
import hashlib,http.server,json,os,pathlib,shutil,sys,tempfile,threading
page=sys.argv[1].encode();root=pathlib.Path(tempfile.mkdtemp(prefix='arctic-performance-files-'))
for number in range(16):(root/('file-%02d.txt'%number)).write_text('Arctic file fixture\n')
(root/'Folder').mkdir()
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path!='/benchmark.html':self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8')
        self.send_header('Content-Length',str(len(page)));self.end_headers();self.wfile.write(page)
    def log_message(self,*args):pass
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
print(json.dumps(dict(files=str(root),url='http://127.0.0.1:%d/benchmark.html'%server.server_port,
    page_sha256=hashlib.sha256(page).hexdigest(),file_count=16,
    file_payload_sha256=hashlib.sha256(b'Arctic file fixture\n').hexdigest(),uid=os.getuid(),pid=os.getpid(),
    start_ticks=int(pathlib.Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]))),flush=True)
try:
    for line in sys.stdin:pass
finally:
    server.shutdown();server.server_close();thread.join();shutil.rmtree(root)
'''


@contextmanager
def role_workload(prefix):
    process = subprocess.Popen(prefix+['python3', '-u', '-c', WORKLOAD_WORKER, WORKLOAD_PAGE],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
    try:
        response, deadline = b'', time.monotonic() + 5
        while b'\n' not in response:
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([process.stdout], [], [], remaining)[0]:
                raise RuntimeError('Offline role workload did not become ready')
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk or len(response) + len(chunk) > 4096:
                raise RuntimeError('Invalid offline role workload response')
            response += chunk
        data = json.loads(response)
        if (not re.fullmatch(r'http://127\.0\.0\.1:[0-9]+/benchmark\.html', data['url'])
                or not data['files'].startswith('/tmp/arctic-performance-files-')
                or data['page_sha256'] != hashlib.sha256(WORKLOAD_PAGE.encode()).hexdigest()
                or data['file_count'] != 16
                or data['file_payload_sha256'] != hashlib.sha256(b'Arctic file fixture\n').hexdigest()
                or type(data.get('pid')) is not int or data['pid'] <= 0
                or type(data.get('start_ticks')) is not int or data['start_ticks'] <= 0
                or data['uid'] != pwd.getpwnam(prefix[2]).pw_uid):
            raise RuntimeError('Invalid offline role workload identity')
        worker_cpu_ticks(data)
        yield data
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        finally:
            process.stdout.close(); process.stderr.close()
        if process.returncode != 0:
            raise RuntimeError('Temporary offline workload cleanup failed: exit ' + str(process.returncode))


def role_command(app, workload):
    ident = app['id']
    if ident in ('kitty', 'foot'):
        return [ident]
    if ident == 'nautilus':
        return ['nautilus', '--new-window', workload['files']]
    if ident == 'pcmanfm':
        return ['pcmanfm', '--new-win', workload['files']]
    if ident == 'zen':
        return ['flatpak', 'run', 'app.zen_browser.zen', '--new-window', workload['url']]
    if ident == 'gnome-web':
        return ['epiphany', '--new-window', workload['url']]
    raise RuntimeError('Unsupported declared role application: ' + ident)


def worker_cpu_ticks(worker, proc_root=Path('/proc')):
    """Read the known helper's whole-process CPU ticks, including its threads."""
    path = proc_root/str(worker['pid'])
    values = (path/'stat').read_text().rsplit(')', 1)[1].split()
    if (path.stat().st_uid != worker['uid'] or values[0] in ('Z', 'X')
            or int(values[19]) != worker['start_ticks']):
        raise RuntimeError('Temporary workload worker identity changed or exited')
    return int(values[11]) + int(values[12])


def collect_idle(worker=None):
    samples = []
    for index in range(30):
        started = time.monotonic()
        usage = resource.getrusage(resource.RUSAGE_SELF)
        observer_before = usage.ru_utime + usage.ru_stime
        before, idle_before = cpu_ticks()
        helper_before = worker_cpu_ticks(worker) if worker else None
        # Six full PSS scans, all 30 raw CPU/memory samples. The parent collector
        # is present in both phases; only normalized idle has the known worker.
        memory = snapshot() if index % 5 == 0 else dict(memory_bytes=meminfo(), observer_pid=os.getpid())
        memory['pss_measured'] = index % 5 == 0
        time.sleep(1)
        helper_after = worker_cpu_ticks(worker) if worker else None
        after, idle_after = cpu_ticks()
        elapsed = time.monotonic() - started
        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory['observer_cpu_percent_one_core'] = 100 * (
            usage.ru_utime + usage.ru_stime - observer_before) / elapsed
        memory['sample_elapsed_seconds'] = elapsed
        memory.update(cpu_interval(before, idle_before, after, idle_after))
        if worker:
            ticks = helper_after-helper_before
            if ticks < 0:
                raise RuntimeError('Temporary workload worker CPU counter moved backwards')
            memory['benchmark_worker_cpu'] = dict(pid=worker['pid'], uid=worker['uid'],
                start_ticks=worker['start_ticks'], ticks_delta=ticks,
                percent_one_core=100 * ticks / memory['cpu_clock_ticks_per_second'] / elapsed,
                resolution_percent_one_core=100 / memory['cpu_clock_ticks_per_second'] / elapsed)
        samples.append(memory)
    return samples


def startup(prefix, command, pattern, timeout=300, hold_seconds=5, observations=None,
            poll_seconds=MAPPING_POLL_SECONDS, label=None):
    label = label or (pattern if isinstance(pattern, str) else pattern[0])
    with NativeClientQuery(prefix) as observer, open('/tmp/arctic-performance-apps.log', 'a') as output:
        # Check the production CLI and native query agree before launching. No
        # altered compositor, application preference or service is involved.
        before = set(clients(prefix))
        native_before = observer.query()
        if before != set(native_before):
            raise RuntimeError('Mango CLI/native observer initial client identities differ')
        started_ns = time.monotonic_ns()
        started = started_ns / 1e9
        # Arm before the original parent-side Popen. Both processes use the
        # same monotonic clock; actual launch overhead remains in the metric.
        observer.begin_observation(before, pattern, started_ns, timeout, poll_seconds)
        child = subprocess.Popen(prefix + command, stdout=output, stderr=output)
        observed_window_ids = set()
        try:
            while time.monotonic() - started < timeout:
                observation = observer.finish_observation(child, started_ns, timeout)
                if observation is None:
                    break
                windows = observation['windows']
                observed_window_ids.update(str(window['id']) for window in windows)
                measured = (observation['upper_ns'] - started_ns)/1e9
                lower = (observation['lower_ns'] - started_ns)/1e9
                time.sleep(hold_seconds)
                persistent = observer.query()
                if not any(str(window['id']) in persistent for window in windows):
                    observer.begin_observation(before, pattern, started_ns, timeout, poll_seconds)
                    continue
                if observations is not None:
                    observations.append(dict(lower_seconds=lower, upper_seconds=measured,
                        interval_seconds=measured-lower, launch_started_monotonic_ns=started_ns,
                        observer=MAPPING_OBSERVER, query_roundtrips=observer.roundtrips))
                emit('mapped_window_' + label, windows)
                emit('app_workload_' + label, snapshot())
                return measured
            emit('startup_' + label + '_diagnostic', dict(exit_code=child.poll(),
                 clients=list(clients(prefix).values()),
                 launch_output=Path('/tmp/arctic-performance-apps.log').read_text(errors='replace')[-12000:]))
            raise RuntimeError(f'No persistent mapped {pattern} window within {timeout} s')
        finally:
            # Close the newly launched window using the compositor, not system-wide pkill.
            try:
                current = clients(prefix)
                for key in (set(current) - before) & observed_window_ids:
                    subprocess.run(prefix + ['mmsg', 'dispatch', 'killclient', 'client,' + key],
                                   capture_output=True, timeout=15)
            finally:
                # A disconnected compositor must fail the run and still reap
                # the process this probe launched. Only matching windows seen
                # during observation can be closed; later unrelated arrivals stay.
                if child.poll() is None:
                    try:
                        # A compositor close normally ends the app. Give its
                        # runuser wrapper time to reap it before sending signals.
                        child.wait(timeout=1)
                    except subprocess.TimeoutExpired:
                        child.terminate()
                        try:
                            child.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait(timeout=5)


def measure(prefix, declared=None, workload=None, order=None, complete=True, preconditioned=True):
    emit('idle_measurement_scope', dict(
        guest_counters='Whole guest, including the collector and temporary benchmark processes',
        parent_observer_cpu='RUSAGE_SELF of this Python collector only; helper CPU is included in guest counters',
        temporary_loopback_worker_present=declared is not None,
        meaning='Normalized idle after app workloads; does not establish pristine idle utilization'))
    emit('identity', dict(kernel=run(['uname', '-r']), virtualization=run(['systemd-detect-virt', '--vm']),
                          sampler=ROLE_SAMPLER if declared else SAMPLER, cpu=run(['lscpu']),
                          boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip()))
    emit('boot', dict(analyze=run(['systemd-analyze']),
                      uptime=Path('/proc/uptime').read_text().strip()))
    emit('security', run(['getenforce']))
    emit('installed_bytes', run(['du', '-sx', '-B1', '--exclude=/proc', '--exclude=/sys', '--exclude=/dev',
                                 '--exclude=/run', '--exclude=/tmp', '/'], timeout=300))
    emit('installed_allocation_scope', 'Root filesystem only (du -x); separate mounted trees excluded')
    allocations, devices = [], set()
    for path in ('/', '/boot', '/boot/efi', '/home', '/nix', '/var/log'):
        if not Path(path).is_dir() or (device := os.stat(path).st_dev) in devices:
            continue
        devices.add(device)
        allocations.append(dict(path=path, device=device, du_bytes=int(run([
            'du', '-sx', '-B1', '--exclude=/proc', '--exclude=/sys', '--exclude=/dev',
            '--exclude=/run', '--exclude=/tmp', path], timeout=300).split()[0])))
    emit('installed_mount_allocations', allocations)
    emit('installed_btrfs_usage', run(['btrfs', 'filesystem', 'usage', '--raw', '/'], timeout=120))
    # Let session initialization settle; record actual elapsed time and memory without flushing caches.
    time.sleep(60)
    emit('idle_samples', collect_idle(workload if declared else None))
    shell_path = run(prefix + ['arctic-shell', '--path'])
    emit('shell_path', shell_path)
    # Match the shipped helper's CLI order and selected shell directory.
    for label, command in [('fish', ['fish', '-ic', 'exit']), ('bash', ['bash', '-ic', 'exit']),
                           ('shell_ipc', ['quickshell', 'ipc', '-p', shell_path, 'call', 'bar', 'hidden'])]:
        times = []
        for _ in range(10):
            start = time.monotonic()
            run(prefix + command)
            times.append(time.monotonic() - start)
        emit(label + '_seconds', dict(samples=times, median=statistics.median(times), max=max(times)))
    if declared:
        for role in ROLE_ORDER:
            app = declared['roles'][role]
            bounds = []
            samples = [startup(prefix, role_command(app, workload), app['appids'], observations=bounds,
                               poll_seconds=ROLE_POLL_SECONDS, label='role_'+role) for _ in range(3)]
            emit('startup_role_' + role + '_warm_seconds', dict(first=samples[0], warm=samples[1:],
                 observation_bounds=bounds, poll_sleep_seconds=ROLE_POLL_SECONDS,
                 observer=MAPPING_OBSERVER, app_id=app['id'],
                 phase='after_45_second_preconditioning' if preconditioned else 'functional_probe_repeated_launch'))
            order.append('warm:'+role)
    else:
        for pattern, command in [('kitty', ['kitty']), ('org.gnome.nautilus', ['nautilus', '--new-window']),
                                 ('zen', ['flatpak', 'run', 'app.zen_browser.zen', 'about:blank'])]:
            bounds = []
            samples = [startup(prefix, command, pattern, observations=bounds) for _ in range(3)]
            emit('startup_' + pattern + '_seconds', dict(first=samples[0], warm=samples[1:],
                 observation_bounds=bounds, poll_sleep_seconds=MAPPING_POLL_SECONDS,
                 observer=MAPPING_OBSERVER))
    emit('final_idle', snapshot())
    emit('system_failed_units', run(['systemctl', '--failed', '--no-pager']))
    emit('flatpak', run(['flatpak', 'list', '--system', '--columns=ref,active,size']))
    # Enumerating the dependency graph can be very slow under TCG. A missing supplemental
    # graph must not discard the actual memory/window measurements or block an offline install.
    try:
        emit('critical_chain', run(['systemd-analyze', '--no-pager', 'critical-chain'], timeout=120))
    except (RuntimeError, subprocess.TimeoutExpired) as error:
        emit('critical_chain_unmeasured', str(error))
    if complete:
        emit('done', True)


def first_use_and_precondition(prefix, declared, workload):
    order = []
    # All three first GUI-role executions precede every 45-second preparation.
    # Guest/host shared libraries may be cached: this is a pristine-profile
    # first-use observation, never a claim that all storage/cache layers are cold.
    for role in ROLE_ORDER:
        app = declared['roles'][role]
        bounds = []
        seconds = startup(prefix, role_command(app, workload), app['appids'], observations=bounds,
                          poll_seconds=ROLE_POLL_SECONDS, label='role_'+role)
        emit('startup_role_' + role + '_cold_seconds', dict(first=seconds, observation_bounds=bounds,
             poll_sleep_seconds=ROLE_POLL_SECONDS, observer=MAPPING_OBSERVER, app_id=app['id'],
             phase='first_gui_role_execution_from_pristine_install',
             meaning='Before any role preconditioning, from pristine user state on this boot; shared OS libraries/host caches may be warm'))
        order.append('cold:'+role)
    for role in ROLE_ORDER:
        app = declared['roles'][role]
        seconds = startup(prefix, role_command(app, workload), app['appids'], hold_seconds=45,
                          poll_seconds=ROLE_POLL_SECONDS, label='role_'+role)
        emit('precondition_role_' + role, dict(mapped_after_seconds=seconds, persistent_hold_seconds=45,
             app_id=app['id'], meaning='Cache/profile normalization; later launches are warmed'))
        order.append('precondition:'+role)
    return order


def main(preconditioned=False, functional=False):
    if (Path(__file__).parent != Path('/run/t') or os.geteuid() != 0
            or run(['systemd-detect-virt', '--vm']) not in ('qemu', 'kvm')):
        raise RuntimeError('This probe requires root inside a disposable QEMU VM')
    prefix = desktop()
    awake = json.loads(run(prefix + ['arctic-keep-awake', 'status', '--json']))
    if awake.get('on'):
        raise RuntimeError('Start measurement with Keep awake off for identical conditions')
    # Slow emulated app launches can outlast the normal five-minute idle lock.
    # Use the shipped session-only feature, then restore it even if a probe fails.
    emit('measurement_conditions', dict(keep_awake_temporary=True, initial_keep_awake=awake))
    run(prefix + ['arctic-keep-awake', 'on', '--quiet'])
    try:
        inventory = rpm_inventory()
        emit('rpm_inventory', inventory)
        declared = None
        if preconditioned:
            context = json.loads(Path('/run/t/performance-context.json').read_text())
            declared = declare_roles(prefix, context, inventory)
            emit('app_roles', declared)
        elif functional:
            declared = functional_roles(prefix, inventory)
            emit('functional_app_roles', declared)
        emit('measured_payload', dict(
            arctic_shell=run(['rpm', '-q', 'arctic-shell']),
            catalog_sha256=run(['sha256sum', '/usr/share/arctic/shell/AppsService.qml']),
            battery_sha256=run(['sha256sum', '/usr/share/arctic/shell/BatteryService.qml']),
            mangowm=run(['rpm', '-q', 'mangowm']),
            quickshell=run(['rpm', '-q', 'quickshell']),
            role_packages={role: app['package'] for role, app in declared['roles'].items()} if declared
                          else dict(kitty=run(['rpm', '-q', 'kitty']))))
        if preconditioned:
            emit('pristine_idle_measurement_scope', dict(
                phase='before_any_gui_role_or_workload_worker',
                collector_present=True, workload_worker_present=False,
                meaning='Settled logged-in desktop before GUI-role execution; whole-guest counters/PSS include the frozen root collector and normal authenticated console/session processes'))
            emit('pristine_idle_samples', collect_idle())
            with role_workload(prefix) as workload:
                emit('role_workload', workload)
                order = first_use_and_precondition(prefix, declared, workload)
                order.insert(0, 'pristine_idle')
                measure(prefix, declared, workload, order, complete=False)
                emit('role_measurement_order', order)
        elif functional:
            with role_workload(prefix) as workload:
                measure(prefix, declared, workload, [], complete=False, preconditioned=False)
        else:
            measure(prefix, complete=False)
    finally:
        restored = json.loads(run(prefix + ['arctic-keep-awake', 'off', '--quiet']))
        emit('keep_awake_restored', restored)
        if restored.get('on') is not False:
            raise RuntimeError('Keep awake did not restore its initial off state')
    # Completion requires all workload lifecycle and session-state cleanup.
    emit('done', True)


if __name__ == '__main__':
    main()
