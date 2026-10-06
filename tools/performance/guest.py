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


MAPPING_OBSERVER = 'mango-socket-worker-v2-worker-clock'
MAPPING_POLL_SECONDS = .001
SAMPLER = 'cpu-30-pss-6-v6-bounded-native-query'
ROLE_SAMPLER = 'cpu-30-pss-6-v7-declared-role-first-use'
ROLE_POLL_SECONDS = .00025
ROLE_ORDER = ('terminal', 'files', 'browser')
# Native ELF payload identity independently verified from the fixed candidate's
# signed Fedora epiphany-runtime RPM; no executable bytes are read before launch.
EPIPHANY_EXPECTED_NATIVE_ELF_SHA256 = '1c91ba76182612fa4f6b9a768510d818d8b901888ee3f31bbb1452ad308b3b4d'
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
                     program='epiphany', rpm='epiphany', desktop='org.gnome.Epiphany.desktop',
                     appids=('org.gnome.epiphany', 'epiphany'),
                     cold_paths=('cache/epiphany', 'data/epiphany', 'config/epiphany')),
}

# One worker enters the actual desktop user/environment before timing begins.
# Mango 0.17.3's mmsg uses this same newline-delimited Unix-socket protocol.
# A fresh socket is required for each get: Mango closes one-shot connections.
# A watch arrival has no server timestamp and is not an exact map timestamp.
CLIENT_QUERY_WORKER = r'''
import json, os, socket, sys, time
path = os.environ['MANGO_INSTANCE_SIGNATURE']
for command in sys.stdin:
    if command != 'get\n':
        raise RuntimeError('Unexpected observer command')
    started = time.monotonic_ns()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(path)
        sent_ns = time.monotonic_ns()
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
        received_ns = time.monotonic_ns()
    value = json.loads(b''.join(chunks))
    if not isinstance(value, dict) or not isinstance(value.get('clients'), list):
        raise RuntimeError('Invalid Mango client response')
    print(json.dumps(dict(payload=value, uid=os.getuid(),
        query_seconds=(received_ns-started)/1e9, query_started_ns=started,
        query_sent_ns=sent_ns, query_received_ns=received_ns)), flush=True)
'''


class NativeClientQuery:
    """Bounded read-only queries with no per-poll process launch or root IPC."""
    def __init__(self, prefix):
        self.prefix = prefix
        self.process = None
        self.buffer = b''
        self.roundtrips = []
        self.bound_prefix = tuple(prefix)
        self.expected_uid = pwd.getpwnam(prefix[2]).pw_uid if prefix[:2] == ['runuser','-u'] else os.getuid()
        self.last_query_bounds = None

    def __enter__(self):
        self.process = subprocess.Popen(self.prefix + ['python3', '-u', '-c', CLIENT_QUERY_WORKER],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        return self

    def query(self):
        if tuple(self.prefix) != self.bound_prefix:
            raise RuntimeError('Native observer desktop user prefix changed')
        parent_started_ns = time.monotonic_ns()
        started = parent_started_ns / 1e9
        self.process.stdin.write(b'get\n')
        until = started + 3
        while b'\n' not in self.buffer:
            remaining = until - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout], [], [], remaining)[0]:
                raise RuntimeError('Native Mango observer timed out; no CLI fallback')
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
        parent_received_ns = time.monotonic_ns()
        value = json.loads(line)
        if type(value['uid']) is not int or value['uid'] != self.expected_uid:
            raise RuntimeError('Native observer did not use the desktop user')
        times = [value.get(key) for key in ('query_started_ns','query_sent_ns','query_received_ns')]
        if (any(type(stamp) is not int for stamp in times)
                or not parent_started_ns <= times[0] <= times[1] <= times[2] <= parent_received_ns):
            raise RuntimeError('Worker monotonic timestamps are outside the parent request envelope')
        self.last_query_bounds = dict(parent_started_ns=parent_started_ns,parent_received_ns=parent_received_ns,
                                      worker_started_ns=times[0],worker_sent_ns=times[1],worker_received_ns=times[2],uid=value['uid'])
        result = {}
        for client in value['payload']['clients']:
            if not isinstance(client, dict) or 'id' not in client or str(client['id']) in result:
                raise RuntimeError('Invalid or duplicate Mango client identity')
            result[str(client['id'])] = client
        self.roundtrips.append(dict(parent_seconds=time.monotonic()-started,
                                    socket_seconds=value['query_seconds'], uid=value['uid'],
                                    monotonic_envelope=self.last_query_bounds))
        return result

    def __exit__(self, *args):
        if self.process is None:
            return
        self.process.stdin.close()
        try:
            # Let runuser reap the worker after natural stdin EOF. Immediately
            # terminating the wrapper can orphan a worker zombie in containers.
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
        # A meaningful query/body failure already prevents completion; retain
        # it. A failed worker cleanup after successful work must also fail closed.
        if self.process.returncode != 0 and not (args and args[0] is not None):
            raise RuntimeError('Native observer cleanup exited ' + str(self.process.returncode))


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


def executable_file_identity(info):
    return dict(device=info.st_dev,inode=info.st_ino,size=info.st_size,
                mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)


def epiphany_file_identity(program_path):
    path = Path(program_path)
    if (program_path != '/usr/bin/epiphany' or path.is_symlink() or not path.is_file()
            or str(path.resolve(strict=True)) != program_path):
        raise RuntimeError('GNOME Web executable path or symlink differs')
    return executable_file_identity(path.stat())


def epiphany_family_ownership(program_path, frontend, owner, inventory):
    """Only GNOME Web's signed Fedora frontend/runtime split is recognized."""
    runtime = [value for value in inventory['nevra'] if re.match(r'epiphany-runtime-[0-9]+:', value)]
    if len(runtime) != 1 or not frontend.startswith('epiphany-'):
        raise RuntimeError('Missing or ambiguous GNOME Web runtime RPM')
    if frontend[len('epiphany-'):] != runtime[0][len('epiphany-runtime-'):] or owner != runtime[0]:
        raise RuntimeError('GNOME Web frontend/runtime EVR, architecture or binary owner differs')
    path = Path(program_path)
    before = epiphany_file_identity(program_path)
    # Metadata only: even a four-byte magic read can cause kernel readahead.
    # Actual ELF magic and whole-file digest are mandatory after first GUI use.
    headers = run(['rpm','-qf','--qf','[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILELINKTOS}\n]',program_path])
    records = [line.split('\t') for line in headers.splitlines() if line.startswith(program_path+'\t')]
    if (len(records) != 1 or len(records[0]) != 3
            or records[0][1] != EPIPHANY_EXPECTED_NATIVE_ELF_SHA256 or records[0][2] != ''):
        raise RuntimeError('GNOME Web installed RPM executable header is invalid')
    return dict(runtime_nevra=runtime[0], ownership_model='epiphany-frontend-runtime-v1',
                executable_path=program_path, rpm_header_sha256=records[0][1],
                payload_integrity_model='full-hash-after-first-gui-v1',
                prelaunch_file_identity=before, prelaunch_content_bytes_read=0,elf_magic_checked_bytes=0)


def verify_role_payload_after_first_gui(app, bound, returned_ns, declared):
    package = app['package']
    path = app['program_path']
    expected = package['prelaunch_file_identity']
    before = epiphany_file_identity(path)
    if before != expected:
        raise RuntimeError('GNOME Web executable changed before post-first-GUI verification')
    started = time.monotonic_ns()
    checksum = hashlib.sha256()
    with Path(path).open('rb') as binary:
        if executable_file_identity(os.fstat(binary.fileno())) != expected:
            raise RuntimeError('GNOME Web opened a different executable during post-first-GUI verification')
        magic = binary.read(4)
        if magic != b'\x7fELF':
            raise RuntimeError('GNOME Web post-first-GUI payload is not native ELF')
        checksum.update(magic)
        for block in iter(lambda:binary.read(128*1024),b''):
            checksum.update(block)
        if executable_file_identity(os.fstat(binary.fileno())) != expected:
            raise RuntimeError('GNOME Web executable changed while its payload was hashed')
    after = epiphany_file_identity(path)
    finished = time.monotonic_ns()
    actual = checksum.hexdigest()
    if after != expected or actual != package['rpm_header_sha256']:
        raise RuntimeError('GNOME Web actual ELF payload or file identity differs after first GUI')
    proof = dict(status='verified',role=app['role'],app_id=app['id'],path=path,
        boot_id=run(['cat','/proc/sys/kernel/random/boot_id']),image=declared['image'],
        boot=declared['boot_context']['boot'],desktop_uid=declared['pristine_state']['uid'],
        phase='immediately_after_first_gui_before_any_preconditioning',
        executable_sha256=actual,rpm_header_sha256=package['rpm_header_sha256'],
        declaration_identity=expected,before_hash_identity=before,after_hash_identity=after,
        first_gui_launch_ns=bound['launch_started_monotonic_ns'],
        first_gui_map_upper_ns=bound['first_present_query']['worker_received_ns'],
        measurement_returned_ns=returned_ns,hash_started_ns=started,hash_finished_ns=finished)
    if not (proof['first_gui_launch_ns'] <= proof['first_gui_map_upper_ns'] <= returned_ns <= started <= finished):
        raise RuntimeError('GNOME Web full payload verification did not follow its first GUI measurement')
    package['post_first_gui_integrity'] = proof
    emit('role_payload_integrity',proof)


def require_role_payload_integrity(declared):
    for app in declared['roles'].values():
        if app['id'] == 'gnome-web':
            proof = app['package'].get('post_first_gui_integrity',{})
            if (proof.get('status') != 'verified'
                    or proof.get('executable_sha256') != app['package']['rpm_header_sha256']):
                raise RuntimeError('Missing final GNOME Web actual payload verification')


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
            if ident == 'gnome-web':
                package.update(epiphany_family_ownership(state['programs'][app['program']],packages[0],owner,inventory))
            elif owner != packages[0]:
                raise RuntimeError('Configured program is not owned by the declared role RPM: ' + ident)
            package['binary_owner'] = owner
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
        last_absent_start = started
        last_absent_proof = None
        child = subprocess.Popen(prefix + command, stdout=output, stderr=output)
        observed_window_ids = set()
        try:
            while time.monotonic() - started < timeout:
                query_started = time.monotonic()
                current = observer.query()
                windows = [c for key, c in current.items() if key not in before and (
                    pattern in (str(c.get('appid', c.get('app_id', ''))) + ' ' + str(c.get('title', ''))).lower()
                    if isinstance(pattern, str) else str(c.get('appid', c.get('app_id', ''))).lower() in pattern)]
                if windows:
                    observed_window_ids.update(str(window['id']) for window in windows)
                    present_proof = dict(observer.last_query_bounds)
                    measured = (present_proof['worker_received_ns'] - started_ns) / 1e9
                    time.sleep(hold_seconds)
                    if not any(str(window['id']) in observer.query() for window in windows):
                        continue
                    if observations is not None:
                        observations.append(dict(lower_seconds=last_absent_start - started,
                                                 upper_seconds=measured,
                                                 interval_seconds=measured - (last_absent_start - started),
                                                 launch_started_monotonic_ns=started_ns,
                                                 bound_basis='worker-sent-to-received',
                                                 last_absent_query=last_absent_proof,
                                                 first_present_query=present_proof,
                                                 observer=MAPPING_OBSERVER,
                                                 query_roundtrips=observer.roundtrips))
                    emit('mapped_window_' + label, windows)
                    emit('app_workload_' + label, snapshot())
                    return measured
                last_absent_proof = dict(observer.last_query_bounds)
                last_absent_start = last_absent_proof['worker_sent_ns'] / 1e9
                time.sleep(poll_seconds)
                if child.poll() not in (None, 0):
                    break
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


def measure(prefix, declared=None, workload=None, order=None, complete=True):
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
                 observer=MAPPING_OBSERVER, app_id=app['id'], phase='after_45_second_preconditioning'))
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
        if declared:
            require_role_payload_integrity(declared)
        emit('done', True)


def first_use_and_precondition(prefix, declared, workload):
    order = []
    # All three first GUI-role executions precede every 45-second preparation.
    # Guest/host shared libraries may be cached: this is a pristine-profile
    # first-use observation, never a claim that all storage/cache layers are cold.
    for role in ROLE_ORDER:
        app = declared['roles'][role]
        bounds = []
        if app['id'] == 'gnome-web' and epiphany_file_identity(app['program_path']) != app['package']['prelaunch_file_identity']:
            raise RuntimeError('GNOME Web executable changed before its first GUI launch')
        seconds = startup(prefix, role_command(app, workload), app['appids'], observations=bounds,
                          poll_seconds=ROLE_POLL_SECONDS, label='role_'+role)
        returned_ns = time.monotonic_ns()
        if app['id'] == 'gnome-web':
            verify_role_payload_after_first_gui(app,bounds[0],returned_ns,declared)
        emit('startup_role_' + role + '_cold_seconds', dict(first=seconds, observation_bounds=bounds,
             poll_sleep_seconds=ROLE_POLL_SECONDS, observer=MAPPING_OBSERVER, app_id=app['id'],
             phase='first_gui_role_execution_from_pristine_install',
             meaning='Before any role preconditioning, from pristine user state on this boot; shared OS libraries/host caches may be warm'))
        order.append('cold:'+role)
    for role in ROLE_ORDER:
        app = declared['roles'][role]
        bounds = []
        seconds = startup(prefix, role_command(app, workload), app['appids'], hold_seconds=45,
                          observations=bounds,poll_seconds=ROLE_POLL_SECONDS, label='role_'+role)
        emit('precondition_role_' + role, dict(mapped_after_seconds=seconds, persistent_hold_seconds=45,
             app_id=app['id'],launch_started_monotonic_ns=bounds[0]['launch_started_monotonic_ns'],
             meaning='Cache/profile normalization; later launches are warmed'))
        order.append('precondition:'+role)
    return order


def main(preconditioned=False):
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
        emit('measured_payload', dict(
            arctic_shell=run(['rpm', '-q', 'arctic-shell']),
            catalog_sha256=run(['sha256sum', '/usr/share/arctic/shell/AppsService.qml']),
            battery_sha256=run(['sha256sum', '/usr/share/arctic/shell/BatteryService.qml']),
            mangowm=run(['rpm', '-q', 'mangowm']),
            quickshell=run(['rpm', '-q', 'quickshell']),
            role_packages={role: app['package'] for role, app in declared['roles'].items()} if declared
                          else dict(kitty=run(['rpm', '-q', 'kitty']))))
        if declared:
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
        else:
            measure(prefix, complete=False)
    finally:
        restored = json.loads(run(prefix + ['arctic-keep-awake', 'off', '--quiet']))
        emit('keep_awake_restored', restored)
        if restored.get('on') is not False:
            raise RuntimeError('Keep awake did not restore its initial off state')
    # Completion requires all workload lifecycle and session-state cleanup.
    if declared:
        require_role_payload_integrity(declared)
    emit('done', True)


if __name__ == '__main__':
    main()
