"""Strict bindings for one diagnostic; no image or release acceptance."""
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import base64
import select
import time
import zlib
import selectors
import signal
import sys

REPO = 'yuvalkolodkingal/Arctic-Linux'
BRANCH = 'codex/safe-diagnostic-v6-20261010'
MARKER = '.github/safe-diagnostic-v6-20261010.activate'
IMAGE = dict(source_sha='bc0521136520daaa221e815822e88ffc44107957',
             run_id=38032256030, artifact_id=11664120624,
             name='Arctic-Linux-1.2-candidate-38032256030-1-x86_64.iso',
             bytes=1929826304,
             sha256='0ab25cc921873ba8750042a6265b6a9e42e669cd78a08d6621c140fd18468609',
             archive_bytes=1930013330,
             archive_sha256='07d60353230eccd0b077279cf6195d73dc6a57f61d9cba3c55503776a76be716',
             producer_mode='frozen-external-paired-v1',
             producer_receipt_sha256='1695aa2af6ec0da618e87c5387a03f44752121111f0bbe6900699d9549b40994')
PAIRS = ('restored-desktop', 'terminal-initial', 'terminal-repaint')
EXECUTION_FILES = {
    '.github/workflows/safe-diagnostic-v6-20261010.yml',
    *('tools/safe-diagnostic/' + n for n in
      ('common.py', 'host.py', 'guest.py', 'run.sh', 'screencopy.c')),
    'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py',
    'tools/native-functional/native_smoke.py', 'tools/native-functional/taskbar-runtime.py',
    'tools/lib/container.sh', 'tools/lib/vmtest.py', 'tools/lib/iso_startup.py',
    'shell/dev/wlr-screencopy-unstable-v1.xml'}
SOURCE_FILES = {
    'packaging/desktop/arctic-graphics.sh',
    'packaging/sddm-wayland-mango/sddm-compositor-mango',
    'packaging/mangowm.spec', 'packaging/patches/mango-software-renderer-dmabuf.patch',
    'iso/kiwi/grub-arctic.cfg.iso-template', 'tools/test-iso.sh',
    'tools/lib/vmtest.py', 'tools/lib/iso_startup.py'}
MAX_FILE = 32 * 1024**2
MAX_TOTAL = 128 * 1024**2
MAX_WIRE = 200 * 1024**2
CHUNK = 18 * 1024
STAGES = ('docker-prep', 'docker-vm', 'bootstrap-cd', 'python-driver')
HOST_PHASES = ('entry', 'root-kvm', 'context', 'image', 'libraries', 'vm-capture', 'complete')
EXCEPTION_CLASSES = {'RuntimeError', 'ValueError', 'TypeError', 'AssertionError', 'OSError',
                     'FileNotFoundError', 'FileExistsError', 'PermissionError', 'TimeoutExpired', 'KeyboardInterrupt',
                     'SystemExit', 'BrokenPipeError', 'OTHER'}


def exception_class(error):
    name = type(error).__name__
    return name if name in EXCEPTION_CLASSES else 'OTHER'


GUEST_PHASES = ('entry', 'context', 'bundle', 'native-import', 'native-guard',
    'boot-flags', 'desktop-discovery', 'mango-identity', 'renderer-environment',
    'renderer-maps', 'library-resolution', 'library-owner-query', 'drm-fds',
    'kernel-framebuffer', 'kernel-drm', 'existing-debugfs', 'renderer-journal',
    'monitor-query', 'output-validation', 'workspace', 'port-open', 'port-duplex',
    'package-query', 'selinux-before', 'hello-send', 'hello-ack', 'capture', 'export', 'complete')
GUEST_EXCEPTION_CLASSES = EXCEPTION_CLASSES | {'ImportError', 'ModuleNotFoundError',
    'UnicodeDecodeError', 'ProcessLookupError', 'NotADirectoryError'}
GUEST_STATUS_PREFIX = 'ARCTIC-SAFE-GUEST-STATUS='


def guest_exception_class(error):
    name = type(error).__name__
    return name if name in GUEST_EXCEPTION_CLASSES else 'OTHER'


def guest_status(phase, status, error, ctx):
    ctx = context(ctx)
    require(type(phase) is str and phase in GUEST_PHASES and type(status) is str
            and status in ('completed', 'exception'), 'Guest fixed phase differs')
    require((phase == 'complete' and error is None) if status == 'completed'
            else (type(error) is str and error in GUEST_EXCEPTION_CLASSES),
            'Guest fixed exception class differs')
    return dict(schema='arctic-safe-guest-fixed-stage-v1', binding_id=ctx['binding_id'],
        execution_sha=ctx['execution_sha'], image_source_sha=IMAGE['source_sha'],
        phase=phase, status=status, exception_class=error, release_acceptance=False,
        image_qualified=False, performance_acceptance=False, observer_profile_admitted=False)


def validate_guest_status(value, ctx):
    require(type(value) is dict and set(value) == {'schema', 'binding_id', 'execution_sha',
        'image_source_sha', 'phase', 'status', 'exception_class', 'release_acceptance',
        'image_qualified', 'performance_acceptance', 'observer_profile_admitted'},
        'Guest fixed status fields differ')
    require(all(value[k] is False for k in ('release_acceptance','image_qualified',
        'performance_acceptance','observer_profile_admitted')), 'Guest fixed acceptance differs')
    expected = guest_status(value['phase'], value['status'], value['exception_class'], ctx)
    require(value == expected, 'Guest fixed status binding differs')
    return value


def project_guest_status(raw, ctx):
    require(type(raw) is bytes and len(raw) <= MAX_FILE, 'Guest fixed serial bound differs')
    matches = [line[len(GUEST_STATUS_PREFIX):] for line in raw.decode('utf-8').splitlines()
               if line.startswith(GUEST_STATUS_PREFIX)]
    require(len(matches) <= 1, 'Guest fixed status is ambiguous')
    if not matches:
        return None
    require(len(matches[0].encode()) <= 2048, 'Guest fixed status exceeds bound')
    return validate_guest_status(strict(matches[0]), ctx)


def exclusive_json(path, value):
    """Owned new reports only; never replace or follow a preexisting path."""
    path = Path(path)
    require(path.parent.is_dir() and not path.parent.is_symlink(), 'Owned report directory differs')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
    with os.fdopen(fd, 'wb') as stream:
        stream.write((json.dumps(value, sort_keys=True, allow_nan=False)+'\n').encode())


def fixed_status(stage, status, exit_code, error, raw=None, cleanup_errors=None):
    require(stage in (*STAGES, *HOST_PHASES) and status in ('completed', 'exception', 'cleanup-exception'),
            'Fixed diagnostic stage differs')
    require(exit_code is None or type(exit_code) is int and 0 <= exit_code <= 255,
            'Fixed diagnostic exit status differs')
    require(error is None or error in EXCEPTION_CLASSES, 'Fixed diagnostic exception class differs')
    value = dict(schema='arctic-safe-fixed-stage-v1', stage=stage, status=status,
                 exit_code=exit_code, exception_class=error, release_acceptance=False,
                 image_qualified=False, performance_acceptance=False, observer_profile_admitted=False)
    if raw is not None:
        require(set(raw) == {'stdout','stderr'}, 'Private output inventory differs')
        for label, record in raw.items():
            require(set(record) == {'bytes','sha256','complete'} and type(record['bytes']) is int
                    and 0 <= record['bytes'] <= MAX_FILE and type(record['complete']) is bool
                    and type(record['sha256']) is str and re.fullmatch('[0-9a-f]{64}',record['sha256']),
                    'Private output descriptor differs')
        value['private_raw_output'] = raw
    if cleanup_errors is not None:
        require(type(cleanup_errors) is list and len(cleanup_errors) <= 6,
                'Owned cleanup inventory differs')
        for item in cleanup_errors:
            require(set(item) == {'stage','exception_class'} and item['stage'] in
                    ('vm-close','port-close','temporary-cleanup','host-report','host-status')
                    and item['exception_class'] in EXCEPTION_CLASSES, 'Owned cleanup descriptor differs')
        value['cleanup_errors'] = cleanup_errors
    return value


def validate_fixed_status(value):
    require(type(value) is dict and set(value)-{'private_raw_output','cleanup_errors'} == {
            'schema','stage','status','exit_code','exception_class','release_acceptance',
            'image_qualified','performance_acceptance','observer_profile_admitted'}
            and value['schema']=='arctic-safe-fixed-stage-v1'
            and all(value[k] is False for k in ('release_acceptance','image_qualified',
                    'performance_acceptance','observer_profile_admitted')), 'Fixed stage report fields differ')
    expected=fixed_status(value['stage'],value['status'],value['exit_code'],value['exception_class'],
                          raw=value.get('private_raw_output'),cleanup_errors=value.get('cleanup_errors'))
    require(value==expected,'Fixed stage report contains arbitrary data')
    return value


def run_stage(stage, out, argv):
    """Observe exact argv without publishing argv, errors, or raw child text."""
    out = Path(out)
    require(stage in STAGES and out.is_dir() and not out.is_symlink()
            and type(argv) is list and argv and all(type(a) is str and a for a in argv),
            'Owned subprocess stage differs')
    report = out/('stage-'+stage+'.json')
    require(not report.exists() and not report.is_symlink(), 'Stage report must be new')
    proc, files, selection, hashes, counts, complete = None, {}, selectors.DefaultSelector(), {}, {}, {}
    primary, result = None, None
    old_handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    def interrupted(signum, frame):
        raise RuntimeError('Owned diagnostic stage interrupted')
    def observe():
        # Leave the owned leader unreaped until its acquired group is cleaned.
        # Its retained PID prevents reuse of this numeric process-group ID.
        return os.waitid(os.P_PID,proc.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
    def stop():
        if proc is not None:
            observe()  # Refuse to signal if this is no longer our child.
            try: os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError: pass
            # A terminated leader does not imply its descendants exited.
            # Keep its PID reserved throughout the original bounded grace.
            until=time.monotonic()+5
            while time.monotonic()<until: time.sleep(.05)
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait(timeout=5)
    try:
        for s in old_handlers: signal.signal(s,interrupted)
        for label in ('stdout','stderr'):
            path=out/('private-'+stage+'-'+label+'.log')
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
            files[label]=os.fdopen(fd,'wb');hashes[label]=hashlib.sha256();counts[label]=0;complete[label]=False
        proc=subprocess.Popen(argv,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE,start_new_session=True)
        for label in ('stdout','stderr'):
            selection.register(getattr(proc,label),selectors.EVENT_READ,label)
        deadline=time.monotonic()+1140  # Original outer 19-minute bound still applies.
        while selection.get_map():
            require(time.monotonic()<deadline, 'Private stage output deadline')
            for key,_ in selection.select(.2):
                block=os.read(key.fileobj.fileno(),65536);label=key.data
                if not block:
                    selection.unregister(key.fileobj);complete[label]=True;continue
                require(counts[label]+len(block)<=MAX_FILE, 'Private stage output bound')
                files[label].write(block);hashes[label].update(block);counts[label]+=len(block)
        until=time.monotonic()+5;info=observe()
        while info is None and time.monotonic()<until:
            time.sleep(.05);info=observe()
        require(info is not None,'Owned child exit observation deadline')
        result=info.si_status if info.si_code==os.CLD_EXITED else 128+info.si_status
        require(0<=result<=255, 'Child exit status bound')
        return result
    except BaseException as error:
        primary=error
        raise
    finally:
        secondary=None
        # A repeated TERM cannot interrupt the acquired group's KILL/reap.
        for s in old_handlers: signal.signal(s,lambda signum,frame:None)
        try: stop()
        except BaseException as error: secondary=error
        try: selection.close()
        except BaseException as error: secondary=secondary or error
        for label,stream in files.items():
            try: stream.close()
            except BaseException as error: secondary=secondary or error
        if proc is not None:
            for stream in (proc.stdout,proc.stderr):
                if stream is not None:
                    try: stream.close()
                    except BaseException as error: secondary=secondary or error
        raw={label:dict(bytes=counts.get(label,0),sha256=hashes.get(label,hashlib.sha256()).hexdigest(),
                        complete=complete.get(label,False)) for label in ('stdout','stderr')}
        try:
            exclusive_json(report,fixed_status(stage,'exception' if primary or secondary else 'completed',
                  result,exception_class(primary or secondary) if primary or secondary else None,raw=raw))
        except BaseException as error: secondary=secondary or error
        for s,handler in old_handlers.items(): signal.signal(s,handler)
        if primary is None and secondary is not None and not result: raise secondary


def require(value, message):
    if not value:
        raise RuntimeError(message)


def strict(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate diagnostic JSON key')
            result[key] = value
        return result
    def constant(_):
        raise RuntimeError('Nonfinite diagnostic JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(65536), b''):
            h.update(block)
    return h.hexdigest()


def capture(argv, timeout=30):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    require(result.returncode == 0 and len(result.stdout) <= 1024**2,
            'Bounded diagnostic command failed')
    return result.stdout.decode().strip()


def regular(path, limit=MAX_FILE, owner=None):
    path = Path(path)
    require(not path.is_symlink(), 'Diagnostic symlink rejected')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit
            and (owner is None or info.st_uid == owner), 'Diagnostic regular-file identity differs')
    return path


def read_regular(path, limit=MAX_FILE, dir_fd=None):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dir_fd)
    except OSError:
        raise RuntimeError('Cannot acquire diagnostic original member') from None
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 <= info.st_size <= limit,
                'Diagnostic original member is nonregular or oversized')
        value = bytearray()
        while len(value) <= limit:
            part = os.read(fd, min(65536, limit+1-len(value)))
            if not part: break
            value.extend(part)
        after = os.fstat(fd)
        require(len(value) == info.st_size and len(value) <= limit
                and (info.st_dev,info.st_ino,info.st_size,info.st_mtime_ns,info.st_ctime_ns)
                == (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns,after.st_ctime_ns),
                'Diagnostic original member changed while read')
        return bytes(value)
    finally:
        os.close(fd)


def validate_manifest(value):
    require(type(value) is dict and set(value) == {
        'schema', 'ready', 'release_acceptance', 'image_qualified', 'performance_acceptance',
        'observer_profile_admitted', 'image', 'execution_files', 'source_files'}, 'Diagnostic manifest fields differ')
    require(value['schema'] == 'arctic-safe-diagnostic-v1' and value['ready'] is True
            and all(value[k] is False for k in ('release_acceptance', 'image_qualified',
                    'performance_acceptance', 'observer_profile_admitted')), 'Diagnostic is disabled or claims acceptance')
    require(type(value['image']) is dict and value['image'] == IMAGE
            and all(type(value['image'][k]) is type(v) for k, v in IMAGE.items()), 'Exact original image pins differ')
    require(type(value['execution_files']) is dict and set(value['execution_files']) == EXECUTION_FILES,
            'Diagnostic execution inventory differs')
    require(all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v)
                for v in value['execution_files'].values()), 'Diagnostic execution hash differs')
    require(type(value['source_files']) is dict and set(value['source_files']) == SOURCE_FILES,
            'Diagnostic source inventory differs')
    for v in value['source_files'].values():
        require(type(v) is dict and set(v) == {'blob_sha', 'sha256', 'bytes', 'mode'}
                and type(v['bytes']) is int and 0 < v['bytes'] < 1000000
                and v['mode'] in ('100644', '100755')
                and type(v['blob_sha']) is str and re.fullmatch('[0-9a-f]{40}', v['blob_sha'])
                and type(v['sha256']) is str and re.fullmatch('[0-9a-f]{64}', v['sha256']),
                'Diagnostic original source pin differs')
    return value


def guard(root, source):
    root, source = Path(root), Path(source)
    manifest_path = root / 'tools/safe-diagnostic/execution-manifest.json'
    manifest = validate_manifest(strict(regular(manifest_path).read_bytes()))
    require(os.environ.get('GITHUB_REPOSITORY') == REPO
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted', 'Requires exact first-attempt hosted diagnostic')
    event = strict(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    head = capture(['git', '-C', str(root), 'rev-parse', 'HEAD'])
    parents = capture(['git', '-C', str(root), 'show', '-s', '--format=%P', 'HEAD']).split()
    require(len(parents) == 1 and event['before'] == parents[0]
            and event['after'] == os.environ.get('GITHUB_SHA') == head, 'Diagnostic activation ancestry differs')
    capture(['git', '-C', str(root), 'merge-base', '--is-ancestor', IMAGE['source_sha'], parents[0]])
    prepared_paths = capture(['git', '-C', str(root), 'diff', '--no-renames', '--name-only', IMAGE['source_sha'], parents[0]]).splitlines()
    require(prepared_paths and all(name.startswith('tools/safe-diagnostic/')
            or name == '.github/workflows/safe-diagnostic-v6-20261010.yml' for name in prepared_paths),
            'Diagnostic preparation changes existing product or qualification paths')
    require(subprocess.run(['git', '-C', str(root), 'cat-file', '-e', parents[0]+':'+MARKER],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30).returncode != 0,
            'Diagnostic parent was already activated')
    require(capture(['git', '-C', str(root), 'diff', '--no-renames', '--name-only', parents[0], head]).splitlines() == [MARKER]
            and regular(root / MARKER, 41).read_bytes() == (parents[0] + '\n').encode(),
            'Requires sole marker child of reviewed diagnostic preparation')
    marker_row = capture(['git', '-C', str(root), 'ls-tree', 'HEAD', '--', MARKER]).split()
    require(len(marker_row) == 4 and marker_row[0:2] == ['100644', 'blob']
            and marker_row[3] == MARKER, 'Diagnostic activation marker mode differs')
    require(not capture(['git', '-C', str(root), 'status', '--porcelain']), 'Diagnostic checkout is dirty')
    require(manifest_path.read_bytes() == subprocess.check_output(
        ['git', '-C', str(root), 'show', 'HEAD:tools/safe-diagnostic/execution-manifest.json'], timeout=30),
        'Diagnostic manifest differs from tracked bytes')
    for name, expected in manifest['execution_files'].items():
        raw = regular(root / name).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == expected
                and raw == subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + name], timeout=30),
                'Diagnostic execution pin mismatch')
        row = capture(['git', '-C', str(root), 'ls-tree', 'HEAD', '--', name]).split()
        require(len(row) == 4 and row[0] in ('100644', '100755') and row[1] == 'blob',
                'Diagnostic execution blob mode differs')
    require(capture(['git', '-C', str(source), 'rev-parse', 'HEAD']) == IMAGE['source_sha']
            and not capture(['git', '-C', str(source), 'status', '--porcelain']), 'Original image source checkout differs')
    for name, pin in manifest['source_files'].items():
        raw = subprocess.check_output(['git', '-C', str(source), 'show', 'HEAD:' + name], timeout=30)
        row = capture(['git', '-C', str(source), 'ls-tree', 'HEAD', '--', name]).split()
        require(row == [pin['mode'], 'blob', pin['blob_sha'], name]
                and len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'],
                'Original image product source pin mismatch')
    ref = strict(capture(['gh', 'api', 'repos/' + REPO + '/git/ref/heads/' + BRANCH]))
    require(ref['ref'] == 'refs/heads/' + BRANCH and ref['object']['sha'] == head,
            'Diagnostic branch advanced before execution')
    return dict(parent_sha=parents[0], execution_sha=head, image=IMAGE, release_acceptance=False)


def context(value):
    require(type(value) is dict and set(value) == {'schema', 'image', 'execution_sha', 'binding_id', 'bundle'},
            'Guest diagnostic context fields differ')
    require(value['schema'] == 'arctic-safe-guest-context-v1' and value['image'] == IMAGE
            and all(type(value['image'][k]) is type(v) for k, v in IMAGE.items()), 'Guest original image context differs')
    require(type(value['execution_sha']) is str and re.fullmatch('[0-9a-f]{40}', value['execution_sha'])
            and type(value['binding_id']) is str and re.fullmatch('[0-9a-f]{32}', value['binding_id']),
            'Guest execution identity differs')
    require(type(value['bundle']) is dict and set(value['bundle']) ==
            {'common.py', 'guest.py', 'taskbar-runtime.py', 'native_smoke.py', 'raw-screencopy', 'screen-evidence.py'}
            and all(type(v) is str and re.fullmatch('[0-9a-f]{64}', v) for v in value['bundle'].values()),
            'Protected guest bundle inventory differs')
    return value


GUEST_FILES = {'guest-report.json', *(
    label + '-wayland' + suffix for label in PAIRS
    for suffix in ('.rgb', '.rgb.shm.rgb', '.rgb.json', '.log'))}


class Channel:
    """Bounded newline protocol over the one owned duplex virtio connection."""
    def __init__(self, fd, binding, transcript=None):
        self.fd, self.binding, self.transcript = fd, binding, transcript
        self.buffer = bytearray()
        self.read_bytes = self.write_bytes = 0
        self.read_sha256 = hashlib.sha256()

    def send(self, kind, payload):
        raw = (json.dumps(dict(kind=kind, binding_id=self.binding, payload=payload),
                          sort_keys=True, allow_nan=False) + '\n').encode('ascii')
        require(len(raw) <= 32 * 1024, 'Diagnostic message exceeds bound')
        self.write_bytes += len(raw)
        require(self.write_bytes <= MAX_WIRE, 'Diagnostic wire exceeds bound')
        deadline, view = time.monotonic() + 30, memoryview(raw)
        while view:
            require(select.select([], [self.fd], [], max(0, deadline-time.monotonic()))[1],
                    'Diagnostic channel write deadline')
            try:
                n = os.write(self.fd, view)
                require(n > 0, 'Diagnostic channel disconnected')
                view = view[n:]
            except BlockingIOError:
                pass

    def receive(self, timeout=30):
        deadline = time.monotonic() + timeout
        while b'\n' not in self.buffer:
            require(len(self.buffer) <= 32 * 1024 and
                    select.select([self.fd], [], [], max(0, deadline-time.monotonic()))[0],
                    'Diagnostic channel read deadline or oversized line')
            try:
                raw = os.read(self.fd, 8192)
            except BlockingIOError:
                continue
            require(raw, 'Diagnostic channel disconnected')
            self.read_bytes += len(raw)
            self.read_sha256.update(raw)
            require(self.read_bytes <= MAX_WIRE, 'Diagnostic wire exceeds bound')
            if self.transcript:
                self.transcript.write(raw)
            self.buffer.extend(raw)
        line, _, tail = self.buffer.partition(b'\n')
        self.buffer = bytearray(tail)
        require(len(line) <= 32 * 1024, 'Diagnostic message exceeds bound')
        value = strict(line)
        require(type(value) is dict and set(value) == {'kind', 'binding_id', 'payload'}
                and value['binding_id'] == self.binding and type(value['kind']) is str
                and type(value['payload']) is dict, 'Diagnostic envelope identity differs')
        return value['kind'], value['payload']

    def expect(self, kind, payload=None, timeout=30):
        actual, value = self.receive(timeout)
        require(actual == kind and (payload is None or value == payload),
                'Diagnostic protocol order or acknowledgement differs')
        return value


def encode_files(root):
    entries, total = [], 0
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for name in sorted(os.listdir(directory)):
            require(name in GUEST_FILES, 'Unexpected guest evidence path')
            data = read_regular(name, dir_fd=directory)
            total += len(data)
            require(total <= MAX_TOTAL, 'Guest evidence aggregate exceeds bound')
            compressed = zlib.compress(data, 6)
            entries.append((dict(path=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                                 compressed_bytes=len(compressed), chunks=(len(compressed)+CHUNK-1)//CHUNK), compressed))
    finally:
        os.close(directory)
    require({entry['path'] for entry, _ in entries} == GUEST_FILES, 'Incomplete guest evidence inventory')
    return entries, total


def export_files(channel, root):
    entries, total = encode_files(root)
    channel.send('INVENTORY', dict(files=[entry for entry, _ in entries], bytes=total))
    for entry, compressed in entries:
        for index, start in enumerate(range(0, len(compressed), CHUNK)):
            channel.send('CHUNK', dict(path=entry['path'], index=index,
                         data=base64.b64encode(compressed[start:start+CHUNK]).decode('ascii')))
    channel.send('END', dict(files=len(entries), bytes=total))


def receive_files(channel, root):
    value = channel.expect('INVENTORY')
    require(set(value) == {'files', 'bytes'} and type(value['files']) is list
            and len(value['files']) == len(GUEST_FILES) and type(value['bytes']) is int
            and 0 < value['bytes'] <= MAX_TOTAL, 'Guest inventory bound differs')
    require({v['path'] for v in value['files']} == GUEST_FILES, 'Guest inventory paths differ')
    total = 0
    for entry in value['files']:
        require(type(entry) is dict and set(entry) == {'path', 'bytes', 'sha256', 'compressed_bytes', 'chunks'}
                and type(entry['bytes']) is int and 0 <= entry['bytes'] <= MAX_FILE
                and type(entry['compressed_bytes']) is int and 0 < entry['compressed_bytes'] <= MAX_FILE+65536
                and type(entry['chunks']) is int and entry['chunks'] == (entry['compressed_bytes']+CHUNK-1)//CHUNK
                and type(entry['sha256']) is str and re.fullmatch('[0-9a-f]{64}', entry['sha256']),
                'Guest inventory file bound differs')
        compressed = bytearray()
        for index in range(entry['chunks']):
            part = channel.expect('CHUNK')
            require(set(part) == {'path', 'index', 'data'} and part['path'] == entry['path']
                    and type(part['index']) is int and part['index'] == index and type(part['data']) is str,
                    'Guest chunk order differs')
            raw = base64.b64decode(part['data'], validate=True)
            require(0 < len(raw) <= CHUNK, 'Guest chunk bound differs')
            compressed.extend(raw)
            require(len(compressed) <= entry['compressed_bytes'], 'Guest compressed size exceeded')
        require(len(compressed) == entry['compressed_bytes'], 'Guest compressed bytes differ')
        decoder = zlib.decompressobj()
        data = decoder.decompress(compressed, entry['bytes'] + 1)
        require(len(data) == entry['bytes'] and decoder.eof and not decoder.unused_data
                and not decoder.unconsumed_tail and hashlib.sha256(data).hexdigest() == entry['sha256'],
                'Guest original member length/hash/compression differs')
        total += len(data)
        require(total <= MAX_TOTAL, 'Guest aggregate evidence exceeds bound')
        with (Path(root) / entry['path']).open('xb') as output:
            output.write(data)
    require(total == value['bytes'], 'Guest inventory aggregate differs')
    channel.expect('END', dict(files=len(GUEST_FILES), bytes=total))
    return value


if __name__ == '__main__':
    # Keep raw exception text private to the owned outer wrapper; fixed reports
    # carry only enumerated stage, exit code, class and bounded stream hashes.
    try:
        require(len(sys.argv)>4 and sys.argv[3]=='--', 'Stage invocation differs')
        code=run_stage(sys.argv[1],Path(sys.argv[2]),sys.argv[4:])
    except BaseException:
        code=1
    raise SystemExit(code)
