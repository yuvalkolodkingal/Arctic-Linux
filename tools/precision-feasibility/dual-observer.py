"""Dedicated feasibility observer. Executed after the unchanged frozen guest.

No compositor timestamps are invented. A positive complete-frame receipt is an
upper bound; a negative GET send is the conservative lower bound. This module
is never installed in the candidate ISO or enabled in the original runner.
"""
import copy
import json
import os
from pathlib import Path
import pwd
import re
import select
import socket
import stat
import struct
import subprocess
import sys
import time
from contextlib import contextmanager

DUAL_OBSERVER = 'mango-dual-stream-worker-v1'
FRAME_BYTES = 4 * 1024 * 1024
TOTAL_BYTES = 64 * 1024 * 1024
WATCH_FRAMES = 4096
RESPONSE_BYTES = 16 * 1024 * 1024
OWNED_ROLE_PROCESSES = {}
DUAL_INVOCATIONS = {}

DUAL_WORKER = r'''
import hashlib, json, os, resource, select, socket, stat, struct, sys, time
FRAME_BYTES=4*1024*1024
TOTAL_BYTES=64*1024*1024
WATCH_FRAMES=4096
RESPONSE_BYTES=16*1024*1024
config=json.loads(os.environ['ARCTIC_DUAL_OBSERVER_PEER'])
path=os.environ['MANGO_INSTANCE_SIGNATURE']
pending=[]
counter=dict(socket_bytes=0,watch_frames=0,get_frames=0,get_queries=0)
active_query=None

def proc_identity(pid):
    root='/proc/'+str(pid)
    with open(root+'/stat') as source:
        fields=source.read().rsplit(')',1)[1].split()
    return dict(pid=pid,uid=os.stat(root).st_uid,start_ticks=int(fields[19]),
                exe=os.readlink(root+'/exe'))

def check_identity():
    if proc_identity(config['pid']) != config['process']:
        raise RuntimeError('Compositor process identity changed')
    if select.select([pidfd],[],[],0)[0]:
        raise RuntimeError('Compositor exited')
    binary=os.lstat(config['process']['exe'])
    actual=dict(device=binary.st_dev,inode=binary.st_ino,size=binary.st_size,
                mtime_ns=binary.st_mtime_ns,ctime_ns=binary.st_ctime_ns)
    if not stat.S_ISREG(binary.st_mode) or actual != config['executable_identity']:
        raise RuntimeError('Compositor executable identity changed')
    st=os.lstat(path)
    if not stat.S_ISSOCK(st.st_mode) or [st.st_dev,st.st_ino,st.st_uid] != config['socket_identity']:
        raise RuntimeError('Mango socket identity changed')

def connect():
    check_identity()
    peer=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        peer.settimeout(2)
        peer.connect(path)
        pid,uid,gid=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if pid != config['pid'] or uid != config['uid'] or uid != os.getuid():
            raise RuntimeError('Mango peer PID/UID differs from actual desktop')
        check_identity()
        return peer,dict(pid=pid,uid=uid,gid=gid,start_ticks=config['process']['start_ticks'],
                         exe=config['process']['exe'])
    except BaseException:
        peer.close()
        raise

def count_bytes(data):
    counter['socket_bytes']+=len(data)
    if counter['socket_bytes'] > TOTAL_BYTES:
        raise RuntimeError('Observer total socket bytes exceeded')

def payload(raw):
    if not raw.endswith(b'\n') or len(raw)>FRAME_BYTES:
        raise RuntimeError('Missing newline or oversized Mango frame')
    value=json.loads(raw)
    if not isinstance(value,dict) or set(value) != {'clients'} or not isinstance(value['clients'],list):
        raise RuntimeError('Invalid Mango client snapshot')
    ids=[]
    for client in value['clients']:
        if not isinstance(client,dict) or type(client.get('id')) is not int or client['id']<=0:
            raise RuntimeError('Invalid Mango client ID')
        ids.append(client['id'])
    if len(set(ids)) != len(ids):
        raise RuntimeError('Duplicate Mango client ID')
    return value

watch=None
watch_buffer=b''
watch_peer=None
pidfd=os.pidfd_open(config['pid'])

def read_watch(*,allow_eof=False):
    global watch_buffer
    check_identity()
    chunk=watch.recv(65536)
    received=time.monotonic_ns()
    if not chunk:
        if not allow_eof or watch_buffer:
            raise RuntimeError('Mandatory watcher disconnected or truncated')
        return True,received
    count_bytes(chunk)
    watch_buffer+=chunk
    while b'\n' in watch_buffer:
        line,watch_buffer=watch_buffer.split(b'\n',1)
        raw=line+b'\n'
        value=payload(raw)
        counter['watch_frames']+=1
        if counter['watch_frames']>WATCH_FRAMES:
            raise RuntimeError('Watch frame count exceeded')
        pending.append(dict(sequence=counter['watch_frames'],received_ns=received,raw=raw.decode(),
                            payload=value,peer=watch_peer))
    if len(watch_buffer)>FRAME_BYTES:
        raise RuntimeError('Unbounded partial watch frame')
    return False,received

def result(kind,**values):
    global pending
    usage=resource.getrusage(resource.RUSAGE_SELF)
    value=dict(kind=kind,uid=os.getuid(),worker_pid=os.getpid(),
               worker_process=proc_identity(os.getpid()),counter=dict(counter),
               cpu_seconds=usage.ru_utime+usage.ru_stime,
               worker_usage=dict(user_seconds=usage.ru_utime,system_seconds=usage.ru_stime,
                                 maximum_rss_kib=usage.ru_maxrss),
               watch_events=pending,**values)
    pending=[]
    encoded=json.dumps(value)
    if len(encoded.encode())>RESPONSE_BYTES:
        raise RuntimeError('Observer response byte limit exceeded')
    print(encoded,flush=True)

def query():
    global active_query
    started=time.monotonic_ns()
    peer,identity=connect()
    with peer:
        sent=time.monotonic_ns()
        active_query=dict(query_started_ns=started,query_sent_ns=sent)
        peer.sendall(b'get all-clients\n')
        counter['get_queries']+=1
        peer.setblocking(False)
        buffer=b''
        frame=None
        received=None
        until=time.monotonic()+2
        while True:
            remaining=until-time.monotonic()
            if remaining<=0:
                raise RuntimeError('GET/EOF deadline exceeded')
            ready=select.select([watch,peer],[],[],remaining)[0]
            if not ready:
                raise RuntimeError('GET/EOF deadline exceeded')
            # Read the event stream promptly even when the GET remains pending.
            if watch in ready:
                read_watch()
            if peer in ready:
                chunk=peer.recv(65536)
                stamp=time.monotonic_ns()
                active_query['last_received_ns']=stamp
                if not chunk:
                    if frame is None or buffer:
                        raise RuntimeError('GET EOF missing frame or trailing bytes')
                    check_identity()
                    response=dict(payload=payload(frame),raw=frame.decode(),peer=identity,
                        query_started_ns=started,query_sent_ns=sent,
                        query_frame_received_ns=received,query_received_ns=stamp,
                        frame_bytes=len(frame))
                    active_query=None
                    return response
                count_bytes(chunk)
                if frame is not None:
                    raise RuntimeError('GET bytes after its complete frame')
                buffer+=chunk
                if len(buffer)>FRAME_BYTES:
                    raise RuntimeError('GET frame byte limit exceeded')
                if b'\n' in buffer:
                    line,buffer=buffer.split(b'\n',1)
                    frame=line+b'\n'
                    payload(frame)
                    if buffer:
                        raise RuntimeError('GET trailing bytes or second frame')
                    received=stamp
                    active_query['query_frame_received_ns']=stamp
                    counter['get_frames']+=1

try:
    if config['uid'] != os.getuid():
        raise RuntimeError('Observer worker is not actual desktop user')
    watch,watch_peer=connect()
    watch.sendall(b'watch all-clients\n')
    watch.setblocking(False)
    until=time.monotonic()+2
    while not pending:
        remaining=until-time.monotonic()
        if remaining<=0 or not select.select([watch],[],[],remaining)[0]:
            raise RuntimeError('Initial watch snapshot deadline exceeded')
        read_watch()
    result('ready',peer=watch_peer)
    stdin_buffer=b''
    while True:
        ready=select.select([sys.stdin.fileno(),watch],[],[],2)[0]
        if watch in ready:
            read_watch()
        if sys.stdin.fileno() in ready:
            data=os.read(sys.stdin.fileno(),4096)
            if not data:
                raise RuntimeError('Parent EOF without proved watcher closure')
            stdin_buffer+=data
            if len(stdin_buffer)>64:
                raise RuntimeError('Observer command byte limit exceeded')
            if b'\n' not in stdin_buffer:
                continue
            command,stdin_buffer=stdin_buffer.split(b'\n',1)
            if stdin_buffer:
                raise RuntimeError('Concurrent observer commands')
            if command==b'get':
                result('query',query=query())
            elif command==b'stop':
                check_identity()
                watch.shutdown(socket.SHUT_WR)
                until=time.monotonic()+2
                while True:
                    remaining=until-time.monotonic()
                    if remaining<=0 or not select.select([watch],[],[],remaining)[0]:
                        raise RuntimeError('Mandatory watcher close/EOF deadline exceeded')
                    eof,stamp=read_watch(allow_eof=True)
                    if eof:
                        break
                result('closed',watch_eof_ns=stamp,partial_watch_bytes=len(watch_buffer))
                break
            else:
                raise RuntimeError('Unexpected observer command')
except BaseException as error:
    # Preserve bounded raw events/counters even when a required stream fails.
    try:
        tail=[dict(sequence=event['sequence'],received_ns=event['received_ns'],peer=event['peer'],
                   raw_tail=event['raw'][-65536:],raw_sha256=hashlib.sha256(event['raw'].encode()).hexdigest())
              for event in pending[-16:]]
        pending=[]
        result('error',error=type(error).__name__+': '+str(error),active_query=active_query,
               pending_tail=tail,partial_watch_bytes=len(watch_buffer),
               partial_watch_sha256=hashlib.sha256(watch_buffer).hexdigest())
    except BaseException:
        pass
    raise
finally:
    if watch is not None:
        watch.close()
    os.close(pidfd)
'''


def dual_proc_identity(pid):
    path = Path('/proc') / str(pid)
    values = (path / 'stat').read_text().rsplit(')', 1)[1].split()
    return dict(pid=pid, uid=path.stat().st_uid, start_ticks=int(values[19]),
                exe=os.readlink(path / 'exe'))


def dual_selected_socket_pid(socket_path, uid, runtime):
    """A pathname yields a provisional PID; only actual worker credentials authenticate it."""
    if type(uid) is not int or uid <= 0 or runtime != '/run/user/' + str(uid):
        raise RuntimeError('Actual desktop runtime/UID differs')
    if not isinstance(socket_path, str):
        raise RuntimeError('Selected Mango IPC pathname is malformed')
    match = re.fullmatch(re.escape(runtime) + r'/mango-([1-9][0-9]*)\.sock', socket_path)
    if match is None:
        raise RuntimeError('Selected Mango IPC pathname differs from pinned native socket naming')
    return int(match.group(1))


def dual_initial_environment(pid):
    """Observe only the old guard's fields; post-exec display equality is not evidence."""
    names = ('XDG_RUNTIME_DIR', 'WAYLAND_DISPLAY', 'MANGO_INSTANCE_SIGNATURE')
    try:
        with (Path('/proc') / str(pid) / 'environ').open('rb') as source:
            raw = source.read(65537)
        if len(raw) > 65536:
            raise ValueError('Initial environment exceeds diagnostic byte bound')
        entries = [entry.decode() for entry in raw.split(b'\0')
                   if entry.split(b'=', 1)[0] in [name.encode() for name in names]]
        values = dict(entry.split('=', 1) for entry in entries if '=' in entry)
        return dict(status='available', queried_keys=list(names), raw_selected_entries=entries,
                    values={name: values.get(name) for name in names}, required_for_authentication=False)
    except (OSError, UnicodeError, ValueError) as error:
        return dict(status='unavailable', queried_keys=list(names), reason=type(error).__name__,
                    required_for_authentication=False)


def dual_peer_declaration(prefix):
    if prefix[:2] != ['runuser', '-u']:
        raise RuntimeError('Dual observer requires the actual non-root desktop prefix')
    user = pwd.getpwnam(prefix[2])
    if user.pw_uid <= 0:
        raise RuntimeError('Dual observer refuses root desktop UID')
    env = dict(item.split('=', 1) for item in prefix if '=' in item)
    socket_path = env.get('MANGO_INSTANCE_SIGNATURE', '')
    pid = dual_selected_socket_pid(socket_path, user.pw_uid, env.get('XDG_RUNTIME_DIR'))
    path = Path(socket_path)
    st = path.lstat()
    if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != user.pw_uid
            or str(path.resolve(strict=True)) != socket_path):
        raise RuntimeError('Actual desktop socket ownership differs')
    identity = dual_proc_identity(pid)
    if (identity['uid'] != user.pw_uid or identity['exe'] != '/usr/bin/mango'
            or (Path('/proc') / str(pid) / 'comm').read_text().strip() != 'mango'):
        raise RuntimeError('Selected socket provisional process is not the actual expected Mango')
    executable = Path('/usr/bin/mango')
    if executable.is_symlink() or not executable.is_file() or str(executable.resolve(strict=True)) != '/usr/bin/mango':
        raise RuntimeError('Compositor executable is not canonical and regular')
    executable_identity = executable_file_identity(executable.stat())
    pidfd = os.pidfd_open(pid)
    primary_error = None
    try:
        if select.select([pidfd], [], [], 0)[0]:
            raise RuntimeError('Selected compositor exited during provisional discovery')
        package = run(['rpm','-qf','/usr/bin/mango','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n'])
        actual = run(['rpm','-q','mangowm','--qf','%{NAME}-%{EPOCHNUM}:%{VERSION}-%{RELEASE}.%{ARCH}\n'])
        context = json.loads(Path('/run/t/performance-context.json').read_text())
        expected = 'd13da6c' if context['image'] == 'baseline' else 'fe4742c' if context['image'] == 'candidate' else ''
        if (not expected or package != actual or not re.fullmatch(
                r'mangowm-0:0\.17\.3-[^\s]+\.git' + expected + r'\.fc44\.x86_64', package)):
            raise RuntimeError('Compositor binary RPM owner/source differs')
        initial_environment = dual_initial_environment(pid)
        after = path.lstat()
        if (dual_proc_identity(pid) != identity or select.select([pidfd], [], [], 0)[0]
                or [after.st_dev, after.st_ino, after.st_uid] != [st.st_dev, st.st_ino, st.st_uid]
                or not stat.S_ISSOCK(after.st_mode) or str(path.resolve(strict=True)) != socket_path
                or executable_file_identity(executable.stat()) != executable_identity):
            raise RuntimeError('Provisional compositor/socket/binary identity changed')
        return dict(uid=user.pw_uid,pid=pid,process=identity,
            socket_path=socket_path,socket_identity=[st.st_dev,st.st_ino,st.st_uid],
            executable_identity=executable_identity,rpm_owner=package,
            boot_id=run(['cat','/proc/sys/kernel/random/boot_id']),image=context['image'],boot=context['boot'],
            session_id=env.get('XDG_SESSION_ID'),wayland_display=env.get('WAYLAND_DISPLAY'),
            peer_discovery=dict(method='selected-ipc-pid-then-mandatory-watch-so-peercred-v1',
                provisional_socket_pid=pid,authentication_required_before_launch='watch-ready-so-peercred'),
            initial_environment_observation=initial_environment)
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            os.close(pidfd)
        except BaseException as cleanup_error:
            if primary_error is None:
                raise
            primary_error.add_note('Owned provisional pidfd cleanup also failed: ' + repr(cleanup_error))


class DualClientObserver:
    def __init__(self, prefix, declaration=None):
        self.prefix = list(prefix)
        self.bound_prefix = tuple(prefix)
        self.declaration = declaration if declaration is not None else dual_peer_declaration(prefix)
        if type(self.declaration.get('uid')) is not int or self.declaration['uid'] <= 0:
            raise RuntimeError('Dual observer requires a real non-root desktop UID')
        self.process = None
        self.buffer = b''
        self.events = []
        self.roundtrips = []
        self.counter = dict(socket_bytes=0,watch_frames=0,get_frames=0,get_queries=0)
        self.worker = None
        self.closure = None
        self.ready = None
        self.last_query = None
        self.worker_memory = None
        self.cleanup_errors = []

    def _response(self, kind, parent_started_ns):
        until = time.monotonic() + 3
        while b'\n' not in self.buffer:
            remaining = until - time.monotonic()
            if remaining <= 0 or not select.select([self.process.stdout],[],[],remaining)[0]:
                raise RuntimeError('Dual observer parent response deadline exceeded')
            chunk = os.read(self.process.stdout.fileno(),65536)
            if not chunk:
                raise RuntimeError('Dual observer worker disconnected')
            self.buffer += chunk
            if len(self.buffer) > RESPONSE_BYTES:
                raise RuntimeError('Dual observer parent response limit exceeded')
        line,self.buffer = self.buffer.split(b'\n',1)
        if self.buffer:
            raise RuntimeError('Unsolicited dual observer parent data')
        received = time.monotonic_ns()
        value = json.loads(line)
        if value.get('kind') == 'error':
            self.failed_worker_evidence = value
            raise RuntimeError(value.get('error','Dual observer failed'))
        if value.get('kind') != kind or type(value.get('uid')) is not int or value['uid'] != self.declaration['uid']:
            raise RuntimeError('Dual observer response kind/actual UID differs')
        worker = value.get('worker_process')
        if not isinstance(worker,dict) or worker.get('pid') != value.get('worker_pid') or worker.get('uid') != value['uid']:
            raise RuntimeError('Missing dual worker process identity')
        if self.worker is not None and worker != self.worker:
            raise RuntimeError('Dual worker process identity changed')
        self.worker = worker
        counters = value.get('counter',{})
        caps = dict(socket_bytes=TOTAL_BYTES,watch_frames=WATCH_FRAMES,get_frames=1000000,get_queries=1000000)
        if set(counters) != set(self.counter) or any(type(counters[k]) is not int or not self.counter[k] <= counters[k] <= caps[k] for k in caps):
            raise RuntimeError('Malformed or regressing observer counters')
        self.counter = counters
        events = value.get('watch_events')
        if not isinstance(events,list):
            raise RuntimeError('Missing watch event sequence')
        for event in events:
            if (type(event.get('sequence')) is not int or event['sequence'] != len(self.events)+1
                    or type(event.get('received_ns')) is not int or not 0 < event['received_ns'] <= received
                    or (self.events and event['received_ns'] < self.events[-1]['received_ns'])
                    or (self.ready is not None and event.get('peer') != self.ready['peer'])):
                raise RuntimeError('Watch sequence/clock/peer differs')
            if not isinstance(event.get('raw'),str) or len(event['raw'].encode()) > FRAME_BYTES or not event['raw'].endswith('\n'):
                raise RuntimeError('Missing raw complete watch frame')
            if json.loads(event['raw']) != event.get('payload'):
                raise RuntimeError('Watch raw bytes and parsed snapshot differ')
            self.events.append(event)
        if counters['watch_frames'] != len(self.events):
            raise RuntimeError('Watch event counters differ from raw sequence')
        value.update(parent_started_ns=parent_started_ns,parent_received_ns=received)
        return value

    def __enter__(self):
        started = time.monotonic_ns()
        env = dict(os.environ,MANGO_INSTANCE_SIGNATURE=self.declaration['socket_path'],
                   ARCTIC_DUAL_OBSERVER_PEER=json.dumps(self.declaration))
        # The prefix contains env -i, so put the proof after its actual environment.
        self.process = subprocess.Popen(self.prefix + ['env','ARCTIC_DUAL_OBSERVER_PEER='+json.dumps(self.declaration),
            'python3','-u','-c',DUAL_WORKER],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,env=env)
        try:
            self.ready = self._response('ready',started)
            peer = self.ready['peer']
            if peer.get('pid') != self.declaration['pid'] or peer.get('uid') != self.declaration['uid'] or peer.get('start_ticks') != self.declaration['process']['start_ticks']:
                raise RuntimeError('Ready peer identity differs')
            if not self.events:
                raise RuntimeError('Missing initial watch snapshot')
            return self
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise

    def query(self):
        if tuple(self.prefix) != self.bound_prefix:
            raise RuntimeError('Dual observer desktop prefix changed')
        started = time.monotonic_ns()
        self.process.stdin.write(b'get\n')
        value = self._response('query',started)
        query = value['query']
        clocks = [query.get(k) for k in ('query_started_ns','query_sent_ns','query_frame_received_ns','query_received_ns')]
        if any(type(n) is not int for n in clocks) or not started <= clocks[0] <= clocks[1] <= clocks[2] <= clocks[3] <= value['parent_received_ns']:
            raise RuntimeError('Dual GET raw worker clock envelope differs')
        if query.get('peer') != self.ready['peer'] or not isinstance(query.get('raw'),str) or json.loads(query['raw']) != query.get('payload'):
            raise RuntimeError('Dual GET raw/peer proof differs')
        proof = dict(parent_started_ns=started,parent_received_ns=value['parent_received_ns'],
            worker_started_ns=clocks[0],worker_sent_ns=clocks[1],worker_frame_received_ns=clocks[2],
            worker_received_ns=clocks[3],uid=value['uid'],peer=query['peer'],raw=query['raw'])
        self.last_query = proof
        self.roundtrips.append(proof)
        return {str(c['id']):c for c in query['payload']['clients']}

    def record_cleanup_error(self, operation, error):
        self.cleanup_errors.append(dict(operation=operation,error_type=type(error).__name__,error=str(error)))

    def __exit__(self, *args):
        if self.process is None:
            return
        primary = args and args[0] is not None
        cleanup = None
        try:
            if self.process.poll() is None:
                if self.worker is not None:
                    memory={}
                    for line in (Path('/proc')/str(self.worker['pid'])/'smaps_rollup').read_text().splitlines():
                        pieces=line.split()
                        if pieces and pieces[0] in ('Pss:','Private_Clean:','Private_Dirty:'):
                            memory[pieces[0][:-1]]=int(pieces[1])*1024
                    self.worker_memory=dict(pss_bytes=memory['Pss'],
                        private_bytes=memory['Private_Clean']+memory['Private_Dirty'],
                        phase='post-hold-before-worker-close',process=self.worker)
                started = time.monotonic_ns()
                self.process.stdin.write(b'stop\n')
                self.closure = self._response('closed',started)
                eof=self.closure.get('watch_eof_ns')
                if (self.closure.get('partial_watch_bytes') != 0 or type(eof) is not int
                        or not started <= eof <= self.closure['parent_received_ns']
                        or (self.events and eof < self.events[-1]['received_ns'])):
                    raise RuntimeError('Mandatory watcher clean EOF proof missing')
        except BaseException as error:
            cleanup = error
            self.record_cleanup_error('watcher-close',error)
        finally:
            try:
                self.process.stdin.close()
            except BaseException as error:
                cleanup = cleanup or error
                self.record_cleanup_error('stdin-close',error)
            try:
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        self.process.kill(); self.process.wait(timeout=3)
            except BaseException as error:
                cleanup = cleanup or error
                self.record_cleanup_error('worker-wait',error)
            finally:
                for name in ('stdout','stderr'):
                    try:
                        getattr(self.process,name).close()
                    except BaseException as error:
                        cleanup = cleanup or error
                        self.record_cleanup_error(name+'-close',error)
        if not primary and (cleanup or self.process.returncode != 0 or self.closure is None):
            raise RuntimeError('Dual watcher/helper cleanup failed: '+str(cleanup or self.process.returncode))
        if not primary and self.worker is not None:
            path=Path('/proc')/str(self.worker['pid'])
            if path.exists() and dual_proc_identity(self.worker['pid'])==self.worker:
                raise RuntimeError('Owned actual observer worker was not reaped')

    def evidence(self):
        return dict(declaration=self.declaration,worker=self.worker,ready=self.ready,
                    watch_events=self.events,query_roundtrips=self.roundtrips,counter=self.counter,
                    closure=self.closure,worker_exit=self.process.returncode if self.process else None,
                    worker_memory_before_close=self.worker_memory,cleanup_errors=self.cleanup_errors,
                    failed_worker_evidence=getattr(self,'failed_worker_evidence',None))


def dual_window_ownership(window, child, uid, role_key, invocation):
    pid = window.get('pid')
    if type(pid) is not int or pid <= 0:
        raise RuntimeError('Mapped role has no actual PID')
    chain=[]
    current=pid
    prior=OWNED_ROLE_PROCESSES.get(role_key,{})
    origin=None
    retained=None
    for _ in range(64):
        try:
            identity=dual_proc_identity(current)
        except OSError as error:
            raise RuntimeError('Mapped role ancestry identity unavailable') from error
        fields=(Path('/proc')/str(current)/'stat').read_text().rsplit(')',1)[1].split()
        parent=int(fields[1])
        chain.append(dict(identity,parent_pid=parent))
        if current == child.pid:
            break
        if current in prior and identity == prior[current]['process']:
            origin=prior[current]['origin']
            retained=identity
            break
        current=parent
        if current<=1:
            raise RuntimeError('Mapped role is outside the launched process ancestry')
    else:
        raise RuntimeError('Mapped role ancestry exceeded bound')
    leaf={key:value for key,value in chain[0].items() if key!='parent_pid'}
    if leaf['uid'] != uid or dual_proc_identity(pid) != leaf:
        raise RuntimeError('Mapped role actual UID/PID/start changed')
    proof=dict(window_id=window['id'],window_pid=pid,uid=uid,
        process=leaf,launch_wrapper_pid=child.pid,ancestry=chain,retained_identity=retained,
        model='same-invocation-ancestry' if origin is None else 'earlier-owned-role-process',
        invocation=invocation,origin=origin)
    if origin is None:
        proof['origin']=dict(invocation=invocation,process=leaf,ancestry=chain,
                            launch_wrapper_pid=child.pid)
    OWNED_ROLE_PROCESSES.setdefault(role_key,{})[pid]=dict(process=leaf,origin=proof['origin'])
    return proof


@contextmanager
def dual_failure_evidence(observer,label):
    try:
        yield
    except BaseException:
        emit('dual_observer_failure_'+label,observer.evidence())
        raise


def dual_role_pattern(pattern):
    if (not isinstance(pattern,(tuple,list)) or not pattern
            or any(not isinstance(value,str) or not value or value!=value.lower() for value in pattern)
            or len(set(pattern))!=len(pattern)):
        raise RuntimeError('Dedicated feasibility mode requires declared exact role app IDs')
    return tuple(pattern)


def dual_startup(prefix, command, pattern, timeout=300, hold_seconds=5, observations=None,
                 poll_seconds=.00025,label=None):
    pattern=dual_role_pattern(pattern)
    label=label or pattern[0]
    invocation=DUAL_INVOCATIONS.get(label,0)+1
    DUAL_INVOCATIONS[label]=invocation
    observer=DualClientObserver(prefix)
    role_key=(observer.declaration['boot_id'],observer.declaration['uid'],pattern)
    outcome=None
    child=None
    observed_ids=set()
    with dual_failure_evidence(observer,label), observer, open('/tmp/arctic-performance-apps.log','a') as output:
        before=set(clients(prefix))
        initial=observer.query()
        if before != set(initial) or before != {str(c['id']) for c in observer.events[0]['payload']['clients']}:
            raise RuntimeError('CLI/GET/watch initial membership differs before launch')
        started_ns=time.monotonic_ns()
        child=subprocess.Popen(prefix+command,stdout=output,stderr=output)
        last_negative=None
        try:
            launched=dual_proc_identity(child.pid)
            while time.monotonic_ns()-started_ns < timeout*1e9:
                current=observer.query()
                candidates=[]
                for event in observer.events:
                    if event['received_ns'] < started_ns:
                        continue
                    for window in event['payload']['clients']:
                        if str(window['id']) not in before and str(window.get('appid','')).lower() in pattern:
                            candidates.append((event['received_ns'],'watch',window,event))
                for window in current.values():
                    if str(window['id']) not in before and str(window.get('appid','')).lower() in pattern:
                        candidates.append((observer.last_query['worker_frame_received_ns'],'get',window,observer.last_query))
                if not candidates:
                    last_negative=copy.deepcopy(observer.last_query)
                    time.sleep(poll_seconds)
                    if child.poll() not in (None,0):
                        break
                    continue
                upper,stream,window,positive=min(candidates,key=lambda row:row[0])
                ownership=dual_window_ownership(window,child,observer.declaration['uid'],role_key,invocation)
                if ownership['model']=='same-invocation-ancestry' and dual_proc_identity(child.pid) != launched:
                    raise RuntimeError('Owned role launcher identity changed')
                observed_ids.add(str(window['id']))
                # A negative GET overlapping watch receipt is valid only for the
                # chosen ID and when its SEND precedes that receipt. Its receipt
                # may legitimately follow the watch. Never substitute receipt.
                negative=last_negative
                query=observer.last_query
                if (str(window['id']) not in current and query['worker_sent_ns'] <= upper
                        and query['worker_sent_ns'] >= started_ns):
                    negative=copy.deepcopy(query)
                lower=negative['worker_sent_ns'] if negative is not None else started_ns
                if not started_ns <= lower <= upper:
                    raise RuntimeError('Dual-stream negative/positive clocks contradict')
                time.sleep(hold_seconds)
                final=observer.query()
                final_window=final.get(str(window['id']))
                if (final_window is None or final_window.get('pid') != window['pid']
                        or dual_proc_identity(window['pid']) != ownership['process']):
                    raise RuntimeError('Selected mapped role failed unchanged persistent-window hold')
                held_ns=time.monotonic_ns()
                outcome=dict(lower_seconds=(lower-started_ns)/1e9,upper_seconds=(upper-started_ns)/1e9,
                    interval_seconds=(upper-lower)/1e9,launch_started_monotonic_ns=started_ns,
                    bound_basis='dual-stream-send-to-complete-frame-v1',observer=DUAL_OBSERVER,
                    selected_stream=stream,selected_upper_ns=upper,selected_positive=positive,
                    selected_window=window,window_ownership=ownership,launch_process=launched,
                    invocation=invocation,before_client_ids=sorted(before),
                    last_absent_query=negative,first_present_query=(copy.deepcopy(query) if stream=='get' else None),
                    hold_seconds=hold_seconds,hold_verified_ns=held_ns,final_present_query=copy.deepcopy(observer.last_query),
                    final_present_window=final_window)
                emit('mapped_window_'+label,[window]);emit('app_workload_'+label,snapshot())
                break
            if outcome is None:
                raise RuntimeError('No owned persistent mapped role within the fixed startup deadline')
        finally:
            primary=sys.exc_info()[0] is not None
            cleanup=None
            try:
                current=clients(prefix)
                for key in (set(current)-before)&observed_ids:
                    subprocess.run(prefix+['mmsg','dispatch','killclient','client,'+key],capture_output=True,timeout=15,check=True)
            except BaseException as error:
                cleanup=error
                observer.record_cleanup_error('owned-window-close',error)
            finally:
                try:
                    if child is not None and child.poll() is None:
                        try:child.wait(timeout=1)
                        except subprocess.TimeoutExpired:
                            child.terminate()
                            try:child.wait(timeout=3)
                            except subprocess.TimeoutExpired:
                                child.kill();child.wait(timeout=3)
                except BaseException as error:
                    cleanup=cleanup or error
                    observer.record_cleanup_error('owned-launch-wait',error)
            if cleanup is not None and not primary:
                raise cleanup
    # The required watch EOF and helper exit must be proved before returning or
    # appending a completed observation, so no cleanup failure can qualify it.
    outcome['dual_stream_evidence']=observer.evidence()
    if observations is not None:
        observations.append(outcome)
    emit('dual_invocation_'+label+'_'+str(invocation),outcome)
    return outcome['upper_seconds']


def install_dual_observer():
    global startup,MAPPING_OBSERVER,verify_role_payload_after_first_gui
    startup=dual_startup
    MAPPING_OBSERVER=DUAL_OBSERVER
    # The composer provides the transparent exact one-field integrity callback
    # delta. It binds full postlaunch hashing to the selected conservative upper.
    verify_role_payload_after_first_gui=dual_verify_role_payload_after_first_gui
