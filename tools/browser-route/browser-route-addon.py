"""Transparent browser-only native-argv diagnostic; frozen observer is unchanged."""
import stat
import base64

ROUTE_ARMS = ('historical-new-window', 'native-product-argv')
ROUTE_SCHEMA = 'arctic-browser-native-argv-v1'
ROUTE_STDERR_BYTES = 512 * 1024
ROUTE_SESSION_BYTES = 1024 * 1024
ROUTE_LOG = Path('/tmp/arctic-performance-apps.log')
ROUTE_SESSION_READER = r'''
import hashlib,json,os,stat,sys,time,xml.etree.ElementTree as ET
from pathlib import Path
limit=1024*1024
url=sys.argv[1]
home=Path(os.environ['HOME'])
data=Path(os.environ.get('XDG_DATA_HOME') or str(home/'.local/share'))
path=data/'epiphany/session_state.xml'
started=time.monotonic_ns()
result=dict(path=str(path),uid=os.getuid(),exists=False,started_ns=started,
    scope='read-only disposable default profile; native argv diagnostic only')
if not data.is_absolute() or not home.is_absolute() or data != home/'.local/share':
    raise RuntimeError('Invalid default data/home path')
for parent in (home,home/'.local',data,path.parent):
    if parent.exists() or parent.is_symlink():
        s=parent.lstat()
        if stat.S_ISLNK(s.st_mode) or not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid():
            raise RuntimeError('Default session ancestor is not owned/canonical')
if path.exists() or path.is_symlink():
    for parent in (path.parent,path):
        s=parent.lstat()
        if stat.S_ISLNK(s.st_mode) or s.st_uid != os.getuid():
            raise RuntimeError('Session path is not owned/canonical')
    s=path.lstat()
    if not stat.S_ISREG(s.st_mode) or not 0<s.st_size<=limit:
        raise RuntimeError('Session state is not a bounded regular file')
    flags=os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        identity=lambda x:(x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns,x.st_uid,x.st_mode)
        if identity(before)!=identity(s):raise RuntimeError('Session changed before read')
        with os.fdopen(fd,'rb',closefd=False) as f:raw=f.read(limit+1)
        after=os.fstat(fd)
        if len(raw)!=s.st_size or identity(before)!=identity(after) or identity(after)!=identity(path.lstat()):
            raise RuntimeError('Session changed while reading')
    finally:os.close(fd)
    tree=ET.fromstring(raw)
    if tree.tag!='session':raise RuntimeError('Unexpected session XML root')
    windows=list(tree.findall('./window'))
    tabs=[]
    for window in windows:
        for tab in window.findall('./embed'):
            value=tab.get('url','')
            kind=('local-fixture' if value==url else 'internal-page' if value.startswith(('ephy-about:','about:')) else 'other-uri')
            tabs.append(dict(uri_kind=kind,uri_sha256=hashlib.sha256(value.encode()).hexdigest()))
    if len(windows)>16 or len(tabs)>256:raise RuntimeError('Session XML exceeds declared counts')
    result.update(exists=True,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),
        file_identity=dict(device=s.st_dev,inode=s.st_ino,size=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns),
        window_count=len(windows),tabs=tabs)
result['finished_ns']=time.monotonic_ns()
print(json.dumps(result,sort_keys=True))
'''


def route_context():
    context = json.loads(Path('/run/t/performance-context.json').read_text())
    arm = context.get('browser_route_arm')
    if (arm not in ROUTE_ARMS or context.get('image') != 'candidate'
            or context.get('fresh_installed_overlay') is not True
            or context.get('collector') != 'console' or type(context.get('boot')) is not int
            or context['boot'] != 1 or context.get('browser_route_schema') != ROUTE_SCHEMA):
        raise RuntimeError('Invalid finite browser route context')
    return context


def route_session(prefix, url):
    result = json.loads(run(prefix + ['python3', '-c', ROUTE_SESSION_READER, url], timeout=15))
    if (type(result.get('uid')) is not int or result['uid'] != pwd.getpwnam(prefix[2]).pw_uid
            or type(result.get('exists')) is not bool
            or type(result.get('started_ns')) is not int or type(result.get('finished_ns')) is not int
            or not 0 < result['started_ns'] <= result['finished_ns']):
        raise RuntimeError('Invalid actual-user session-state evidence')
    return result


def route_stderr(offset):
    started_ns = time.monotonic_ns()
    if not ROUTE_LOG.exists():
        if offset != 0:
            raise RuntimeError('Owned application log disappeared')
        return dict(offset=0,bytes=0,sha256=hashlib.sha256(b'').hexdigest(),text='',exists=False)
    s = ROUTE_LOG.lstat()
    if (ROUTE_LOG.is_symlink() or not stat.S_ISREG(s.st_mode) or s.st_uid != 0
            or not 0 <= offset <= s.st_size <= ROUTE_STDERR_BYTES):
        raise RuntimeError('Owned application log exceeds regular-file bounds')
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    fd = os.open(ROUTE_LOG, flags)
    try:
        before = os.fstat(fd)
        fields = lambda x: (x.st_dev,x.st_ino,x.st_size,x.st_mtime_ns,x.st_ctime_ns)
        if fields(before) != fields(s):
            raise RuntimeError('Application log changed before read')
        os.lseek(fd,offset,os.SEEK_SET)
        raw = os.read(fd,ROUTE_STDERR_BYTES+1)
        after = os.fstat(fd)
        if len(raw) != s.st_size-offset or fields(before) != fields(after) or fields(after) != fields(ROUTE_LOG.lstat()):
            raise RuntimeError('Application log changed during read')
    finally:
        os.close(fd)
    return dict(offset=offset,bytes=len(raw),total_bytes=s.st_size,sha256=hashlib.sha256(raw).hexdigest(),
        started_ns=started_ns,finished_ns=time.monotonic_ns(),
        raw_base64=base64.b64encode(raw).decode('ascii'),
        text=raw.decode('utf-8',errors='replace'),exists=True,
        file_identity=dict(device=s.st_dev,inode=s.st_ino,size=s.st_size,mtime_ns=s.st_mtime_ns,ctime_ns=s.st_ctime_ns))


def install_browser_route():
    global role_command,startup,first_use_and_precondition,measure
    context = route_context()
    arm = context['browser_route_arm']
    original_command = role_command
    original_startup = startup
    original_first_use = first_use_and_precondition
    original_measure = measure
    invocation = 0
    last_log_identity = None
    if ROUTE_LOG.exists() or ROUTE_LOG.is_symlink():
        raise RuntimeError('Use a fresh disposable app log; refuse an existing path')

    def command(app, workload):
        argv = original_command(app,workload)
        if (app.get('id') != 'gnome-web' or app.get('role') != 'browser'
                or app.get('configured_command') != 'epiphany'
                or argv != ['epiphany','--new-window',workload['url']]):
            raise RuntimeError('Native argv diagnostic requires exact configured Web')
        return argv if arm == ROUTE_ARMS[0] else ['epiphany',workload['url']]

    def observe(prefix, argv, pattern, **kwargs):
        nonlocal invocation,last_log_identity
        invocation += 1
        if invocation > 5 or kwargs.get('label') != 'role_browser':
            raise RuntimeError('Only five unfiltered browser invocations are allowed')
        url = argv[-1]
        expected = ['epiphany','--new-window',url] if arm == ROUTE_ARMS[0] else ['epiphany',url]
        if argv != expected or tuple(pattern) != ('org.gnome.epiphany','epiphany'):
            raise RuntimeError('Native argv/role identity differs')
        prior = route_stderr(0)
        if prior['exists']:
            identity = {k:prior['file_identity'][k] for k in ('device','inode')}
            if last_log_identity != identity:
                raise RuntimeError('Owned app log was replaced between invocations')
        offset = prior.get('total_bytes',0)
        before = route_session(prefix,url)
        trace = dict(schema=ROUTE_SCHEMA,arm=arm,invocation=invocation,argv=argv,
            direct_native_argv_only=True,detached_arctic_open_timing_included=False,
            session_before=before,launcher_exit_status_observed=False,launcher_grace_outcome_observed=False,
            limitation='Frozen observer/cleanup does not export wrapper returncode or natural-exit grace outcome')
        try:
            value = original_startup(prefix,argv,pattern,**kwargs)
            trace['mapped_upper_seconds'] = value
            trace['observer_returned_ns'] = time.monotonic_ns()
            return value
        finally:
            primary = sys.exc_info()[0] is not None
            errors = []
            for field, collect in (('session_after',lambda:route_session(prefix,url)),
                                   ('stderr',lambda:route_stderr(offset))):
                try:
                    trace[field] = collect()
                except BaseException as error:
                    errors.append(dict(field=field,type=type(error).__name__,message=str(error)))
            if 'stderr' in trace and trace['stderr']['exists']:
                last_log_identity = {k:trace['stderr']['file_identity'][k] for k in ('device','inode')}
            trace['supplemental_collection_errors'] = errors
            emit('browser_route_invocation_'+str(invocation),trace)
            if errors and not primary:
                raise RuntimeError('Bounded browser evidence collection failed: '+json.dumps(errors))

    def browser_only(function, *args, **kwargs):
        global ROLE_ORDER
        previous = ROLE_ORDER
        ROLE_ORDER = ('browser',)
        try:
            return function(*args,**kwargs)
        finally:
            ROLE_ORDER = previous

    role_command = command
    startup = observe
    first_use_and_precondition = lambda *a,**k:browser_only(original_first_use,*a,**k)
    measure = lambda *a,**k:browser_only(original_measure,*a,**k)
    emit('browser_route_diagnostic',dict(schema=ROUTE_SCHEMA,arm=arm,planned_invocations=5,
        measured_roles=['browser'],declared_core_roles=list(ROLE_ORDER),
        direct_native_argv_only=True,detached_arctic_open_timing_included=False,
        session_reads_outside_mapping_interval=True,session_read_cache_overhead_declared=True,
        observer_and_cleanup_unchanged=True,full_six_boot_performance_acceptance=False,release_acceptance=False))
