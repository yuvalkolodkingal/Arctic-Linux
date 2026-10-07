"""Actual Unix-socket/process controls; synthetic client state, never VM claims."""
import copy
import hashlib
import io
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from contextlib import contextmanager
from unittest.mock import patch

HERE=Path(__file__).resolve().parent
BASE=HERE/'unchanged-base' if (HERE/'unchanged-base').exists() else HERE.parents[1]
spec=importlib.util.spec_from_file_location('isolated_dual_observer',HERE/'dual-observer.py')
dual=importlib.util.module_from_spec(spec);spec.loader.exec_module(dual)


def file_identity(path):
    st=Path(path).stat()
    return dict(device=st.st_dev,inode=st.st_ino,size=st.st_size,mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns)


class Server:
    """Private actual AF_UNIX server, same logical list/builder and newline rules."""
    def __init__(self,**faults):
        self.tmp=tempfile.TemporaryDirectory(prefix='arctic-dual-source-control-')
        self.path=Path(self.tmp.name)/'mango.sock'
        self.socket=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.socket.bind(str(self.path));self.socket.listen();self.socket.settimeout(.05)
        self.faults=faults;self.state=[];self.transition=None;self.transitions=[];self.lock=threading.Lock()
        self.watch=None;self.peers=[];self.handlers=[];self.errors=[];self.stopped=False
        self.negative_started=threading.Event();self.watch_ready=threading.Event()
        self.thread=threading.Thread(target=self.accept);self.thread.start()

    def declaration(self):
        proc=dual.dual_proc_identity(os.getpid());st=self.path.stat()
        return dict(pid=os.getpid(),uid=os.getuid(),process=proc,socket_path=str(self.path),
            socket_identity=[st.st_dev,st.st_ino,st.st_uid],executable_identity=file_identity(proc['exe']),
            rpm_owner='synthetic-owned-source-control',boot_id='00000000-0000-0000-0000-000000000001',
            image='synthetic-control',boot=1,session_id='synthetic',wayland_display='synthetic')

    def raw(self,state=None):
        with self.lock:
            selected=copy.deepcopy(self.state if state is None else state)
        return (json.dumps(dict(clients=selected))+'\n').encode()

    def publish(self,clients,*,fragment=False):
        # Logical state and its independent clock transition are defined inside
        # the same lock used to snapshot state. No later file publication oracle.
        with self.lock:
            self.transition=time.monotonic_ns()
            self.state=copy.deepcopy(clients)
            self.transitions.append((self.transition,copy.deepcopy(clients)))
        raw=self.raw()
        if self.watch is None:raise RuntimeError('Watch was not ready')
        if fragment:
            cut=max(1,len(raw)//2);self.watch.sendall(raw[:cut]);time.sleep(.002);self.watch.sendall(raw[cut:])
        else:self.watch.sendall(raw)
        return self.transition

    def accept(self):
        while not self.stopped:
            try:peer,_=self.socket.accept()
            except socket.timeout:continue
            except OSError:break
            self.peers.append(peer)
            thread=threading.Thread(target=self.handle,args=(peer,));self.handlers.append(thread);thread.start()

    def handle(self,peer):
        try:
            peer.settimeout(3);command=b''
            while not command.endswith(b'\n'):
                part=peer.recv(4096)
                if not part:return
                command+=part
            if command==b'watch all-clients\n':
                self.watch=peer
                peer.sendall(self.raw())
                self.watch_ready.set()
                # A real Mango subscription is persistent across the unchanged
                # five/45-second holds; only the owned half-close ends it.
                peer.settimeout(None)
                while peer.recv(64):pass
                if self.faults.get('watch_eof_extra'):
                    peer.sendall(self.faults['watch_eof_extra'])
                if self.faults.get('watch_no_eof'):
                    time.sleep(2.2)
            elif command==b'get all-clients\n':
                raw=self.raw()
                if not json.loads(raw)['clients']:self.negative_started.set()
                if self.faults.get('get_delay'):time.sleep(self.faults['get_delay'])
                peer.sendall(self.faults.get('get_raw',raw))
                if self.faults.get('get_eof_delay'):time.sleep(self.faults['get_eof_delay'])
                if self.faults.get('get_trailing'):peer.sendall(self.faults['get_trailing'])
            else:raise RuntimeError('Unexpected source-control command')
        except (BrokenPipeError,ConnectionResetError,OSError) as error:
            if not self.stopped and not isinstance(error,(BrokenPipeError,ConnectionResetError)):
                self.errors.append(str(error))
        finally:peer.close()

    def close(self):
        self.stopped=True;self.socket.close()
        for peer in self.peers:
            try:peer.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        self.thread.join(1)
        for thread in self.handlers:thread.join(3)
        if self.thread.is_alive() or any(t.is_alive() for t in self.handlers):
            raise RuntimeError('Source-control server did not quiesce')
        self.tmp.cleanup()

    def __enter__(self):return self
    def __exit__(self,*args):self.close()


@unittest.skipUnless(os.getuid()>0,'Actual observer controls require nonroot; run this suite as an ordinary fixture user')
class DualSocketTest(unittest.TestCase):
    def observer(self,server):
        return dual.DualClientObserver(['env','MANGO_INSTANCE_SIGNATURE='+str(server.path)],server.declaration())

    def test_compile_actual_embedded_worker(self):
        compile(dual.DUAL_WORKER,'actual-worker','exec')

    def test_actual_nonroot_peer_frames_eof_and_normal_reap(self):
        with Server() as server:
            with self.observer(server) as observed:
                self.assertEqual(observed.query(),{})
                pid=observed.worker['pid'];self.assertNotEqual(pid,os.getpid())
                self.assertEqual(observed.ready['peer']['pid'],os.getpid())
                self.assertEqual(observed.ready['peer']['uid'],os.getuid())
                stamp=server.publish([dict(id=1,pid=os.getpid(),appid='fixture')],fragment=True)
                clients=observed.query();self.assertIn('1',clients)
                present=next(e for e in observed.events if e['payload']['clients'])
                self.assertLessEqual(stamp,present['received_ns'])
            self.assertEqual(observed.process.returncode,0)
            self.assertIsNotNone(observed.closure);self.assertEqual(observed.closure['partial_watch_bytes'],0)
            self.assertFalse(Path('/proc',str(pid)).exists())
            self.assertTrue(observed.process.stdout.closed);self.assertTrue(observed.process.stderr.closed)
            self.assertGreater(observed.worker_memory['pss_bytes'],0)

    def test_delayed_negative_overlap_keeps_send_as_lower(self):
        with Server(get_delay=.04) as server:
            with self.observer(server) as observed:
                server.negative_started.clear()
                def map_after_snapshot():
                    self.assertTrue(server.negative_started.wait(1))
                    server.publish([dict(id=1,pid=os.getpid(),appid='fixture')])
                actor=threading.Thread(target=map_after_snapshot);actor.start()
                self.assertEqual(observed.query(),{})
                actor.join(1);self.assertFalse(actor.is_alive())
                positive=next(e for e in observed.events if e['payload']['clients'])
                query=observed.last_query
                self.assertLessEqual(query['worker_sent_ns'],server.transition)
                self.assertLessEqual(server.transition,positive['received_ns'])
                self.assertLess(positive['received_ns'],query['worker_received_ns'])
                self.assertGreater(query['worker_frame_received_ns'],server.transition)
                # Receipt-side lower would exclude the independently defined map.
                self.assertGreater(query['worker_received_ns'],server.transition)

    def test_complete_get_frame_precedes_delayed_eof_without_faking_close(self):
        with Server(get_eof_delay=.025) as server:
            with self.observer(server) as observed:
                observed.query();proof=observed.last_query
                self.assertGreater(proof['worker_received_ns']-proof['worker_frame_received_ns'],15_000_000)
            self.assertEqual(observed.process.returncode,0)

    def test_mandatory_watcher_disconnect_cannot_use_get_fallback(self):
        with Server() as server:
            observed=self.observer(server)
            with self.assertRaisesRegex(RuntimeError,'watcher|worker disconnected'):
                with observed:
                    server.watch.shutdown(socket.SHUT_RDWR)
                    observed.query()
            self.assertIsNone(observed.closure)
            self.assertTrue(observed.process.stdout.closed)

    def test_short_watch_write_then_eof_fails(self):
        with Server() as server:
            observed=self.observer(server)
            with self.assertRaisesRegex(RuntimeError,'watcher|worker disconnected'):
                with observed:
                    server.watch.sendall(b'{"clients":[')
                    server.watch.shutdown(socket.SHUT_RDWR)
                    observed.query()

    def test_watch_partial_tail_at_owned_halfclose_fails(self):
        with Server(watch_eof_extra=b'{"clients":[') as server:
            observed=self.observer(server)
            with self.assertRaisesRegex(RuntimeError,'cleanup failed'):
                with observed:observed.query()
            self.assertFalse(observed.process.returncode==0)

    def test_get_trailing_partial_or_second_frame_fails(self):
        for suffix in (b'x',b'\n',b'{"clients":[]}\n'):
            with self.subTest(suffix=suffix),Server(get_eof_delay=.002,get_trailing=suffix) as server:
                observed=self.observer(server)
                with self.assertRaisesRegex(RuntimeError,'bytes after|trailing|worker disconnected'):
                    with observed:observed.query()

    def test_get_truncation_invalid_json_duplicate_id_fails(self):
        for raw in (b'{"clients":[',b'{}\n',b'{"clients":[{"id":true}]}\n',
                    b'{"clients":[{"id":1},{"id":1}]}\n'):
            with self.subTest(raw=raw),Server(get_raw=raw) as server:
                with self.assertRaises(RuntimeError):
                    with self.observer(server) as observed:observed.query()

    def test_actual_peer_pid_mismatch_rejected_before_ready(self):
        with Server() as server:
            declaration=server.declaration();declaration['pid']=os.getpid()+1
            observed=dual.DualClientObserver(['env','MANGO_INSTANCE_SIGNATURE='+str(server.path)],declaration)
            with self.assertRaises(RuntimeError):
                with observed:pass
            self.assertIsNone(observed.ready);self.assertTrue(observed.process.stdout.closed)

    def test_total_bytes_and_watch_frame_limits_are_executable_failures(self):
        for expression,replacement in [('TOTAL_BYTES=64*1024*1024','TOTAL_BYTES=64'),
                                      ('WATCH_FRAMES=4096','WATCH_FRAMES=1')]:
            with (self.subTest(expression=expression),Server() as server,
                  patch.object(dual,'DUAL_WORKER',dual.DUAL_WORKER.replace(expression,replacement,1))):
                with self.assertRaisesRegex(RuntimeError,'exceeded|disconnected'):
                    with self.observer(server) as observed:
                        server.publish([dict(id=1,pid=os.getpid(),appid='fixture')]);observed.query()

    def test_natural_worker_exit3_is_fatal_and_primary_error_is_preserved(self):
        code=dual.DUAL_WORKER.replace('    os.close(pidfd)','    os.close(pidfd)\n    sys.exit(3)',1)
        with patch.object(dual,'DUAL_WORKER',code):
            with Server() as server:
                observed=self.observer(server)
                with self.assertRaisesRegex(RuntimeError,'cleanup failed'):
                    with observed:observed.query()
                self.assertEqual(observed.process.returncode,3)
                self.assertTrue(observed.process.stdout.closed);self.assertTrue(observed.process.stderr.closed)
            with Server() as server:
                observed=self.observer(server)
                with self.assertRaisesRegex(RuntimeError,'original body failure'):
                    with observed:
                        observed.query();raise RuntimeError('original body failure')
                self.assertEqual(observed.process.returncode,3)

    def synthetic_startup(self,server,*,lose_hold=False,foreign_first=False,identity_failure=False,cleanup_failure=False):
        """Real owned Python child; synthetic role/window, never an actual GUI."""
        dual.OWNED_ROLE_PROCESSES.clear();dual.DUAL_INVOCATIONS.clear()
        actor_code='import time;time.sleep(20)'
        real_popen=subprocess.Popen;actors=[];threads=[];messages=[];foreign=None
        actual_identity=dual.dual_proc_identity;identity_failed=False;cli_calls=0
        def identity(pid):
            nonlocal identity_failed
            if identity_failure and not identity_failed and any(p.pid==pid for p in actors):
                identity_failed=True;raise RuntimeError('Injected owned launch identity read failure')
            return actual_identity(pid)
        if foreign_first:foreign=real_popen([sys.executable,'-c',actor_code])
        def launch(argv,*args,**kwargs):
            process=real_popen(argv,*args,**kwargs)
            if actor_code in argv:
                actors.append(process)
                def publish():
                    time.sleep(.002)
                    if foreign_first:
                        server.publish([dict(id=1,pid=foreign.pid,appid='foot')])
                    else:server.publish([dict(id=2,pid=process.pid,appid='foot')])
                    if lose_hold:
                        time.sleep(.02);server.publish([])
                thread=threading.Thread(target=publish);threads.append(thread);thread.start()
            return process
        def cli(prefix):
            nonlocal cli_calls
            cli_calls+=1
            if cleanup_failure and cli_calls>1:raise RuntimeError('Injected owned window cleanup failure')
            return {str(c['id']):c for c in json.loads(server.raw())['clients']}
        closed=[]
        def dispatch(argv,**kwargs):
            closed.append(argv[-1]);server.publish([])
            return subprocess.CompletedProcess(argv,0,b'',b'')
        bounds=[]
        try:
            with (patch.object(dual,'dual_peer_declaration',return_value=server.declaration()),
                  patch.object(dual,'dual_proc_identity',side_effect=identity),
                  patch.object(dual,'clients',side_effect=cli,create=True),
                  patch.object(dual,'emit',side_effect=lambda *a:messages.append(a),create=True),
                  patch.object(dual,'snapshot',return_value=dict(synthetic=True),create=True),
                  patch.object(dual.subprocess,'Popen',side_effect=launch),
                  patch.object(dual.subprocess,'run',side_effect=dispatch)):
                result=dual.dual_startup([],
                    [sys.executable,'-c',actor_code],['foot'],timeout=2,
                    observations=bounds,label='role_terminal')
            return result,bounds,messages,closed
        except BaseException:
            self.failed_startup=dict(bounds=bounds,messages=messages,closed=closed,
                foreign_alive=foreign is not None and foreign.poll() is None,
                owned_actor_alive_before_fixture_fallback=[p.poll() is None for p in actors])
            raise
        finally:
            for thread in threads:thread.join(1)
            for process in actors+([foreign] if foreign is not None else []):
                if process.poll() is None:process.terminate()
                process.wait(timeout=2)

    def test_actual_owned_startup_hold_selected_clock_and_cleanup(self):
        with Server(get_eof_delay=.025) as server:
            result,bounds,messages,closed=self.synthetic_startup(server)
            self.assertEqual(len(bounds),1);bound=bounds[0]
            self.assertEqual(result,bound['upper_seconds'])
            self.assertEqual(bound['selected_stream'],'watch')
            self.assertIsNone(bound['first_present_query'])
            transition=next(stamp for stamp,clients in server.transitions if clients)
            self.assertLessEqual(bound['launch_started_monotonic_ns'],transition)
            lower=bound['last_absent_query']['worker_sent_ns'] if bound['last_absent_query'] else bound['launch_started_monotonic_ns']
            self.assertLessEqual(lower,transition);self.assertLessEqual(transition,bound['selected_upper_ns'])
            self.assertEqual(bound['dual_stream_evidence']['worker_exit'],0)
            self.assertGreaterEqual(bound['hold_verified_ns']-bound['selected_upper_ns'],5_000_000_000)
            self.assertEqual(closed,['client,2'])
            self.assertEqual(sum(name=='dual_invocation_role_terminal_1' for name,value in messages),1)

    def test_actual_hold_loss_fails_without_completed_observation(self):
        with Server() as server:
            with self.assertRaisesRegex(RuntimeError,'persistent-window hold'):
                self.synthetic_startup(server,lose_hold=True)
            self.assertEqual(self.failed_startup['bounds'],[])
            self.assertTrue(any(name.startswith('dual_observer_failure_') for name,value in self.failed_startup['messages']))

    def test_actual_owned_launch_identity_read_failure_reaps_child_and_preserves_secondary(self):
        for secondary in (False,True):
            with self.subTest(secondary=secondary),Server() as server:
                with self.assertRaisesRegex(RuntimeError,'owned launch identity read failure'):
                    self.synthetic_startup(server,identity_failure=True,cleanup_failure=secondary)
                failure=self.failed_startup
                self.assertEqual(failure['owned_actor_alive_before_fixture_fallback'],[False])
                self.assertEqual(failure['bounds'],[])
                evidence=next(value for name,value in failure['messages'] if name.startswith('dual_observer_failure_'))
                self.assertEqual(evidence['worker_exit'],0)
                self.assertEqual(bool(evidence['cleanup_errors']),secondary)
                if secondary:self.assertEqual(evidence['cleanup_errors'][0]['operation'],'owned-window-close')

    def test_actual_stdout_close_then_raise_still_closes_stderr_and_preserves_primary(self):
        class CloseThenRaise:
            def __init__(self,wrapped):self.wrapped=wrapped
            def __getattr__(self,name):return getattr(self.wrapped,name)
            def close(self):
                self.wrapped.close();raise OSError('Injected close-after-close failure')
        for primary in (False,True):
            with self.subTest(primary=primary),Server() as server:
                observed=self.observer(server)
                with self.assertRaisesRegex(RuntimeError,'original body failure' if primary else 'cleanup failed'):
                    with observed:
                        observed.query();observed.process.stdout=CloseThenRaise(observed.process.stdout)
                        if primary:raise RuntimeError('original body failure')
                self.assertEqual(observed.process.returncode,0)
                self.assertTrue(observed.process.stdout.closed);self.assertTrue(observed.process.stderr.closed)
                self.assertEqual(observed.cleanup_errors,[dict(operation='stdout-close',error_type='OSError',error='Injected close-after-close failure')])

    def test_foreign_new_matching_window_cannot_be_adopted_or_closed(self):
        with Server() as server:
            with self.assertRaisesRegex(RuntimeError,'ancestry'):
                self.synthetic_startup(server,foreign_first=True)
            self.assertEqual(self.failed_startup['bounds'],[])
            self.assertEqual(self.failed_startup['closed'],[])
            self.assertTrue(self.failed_startup['foreign_alive'])


class OwnershipAndCompositionTest(unittest.TestCase):
    def test_original_declared_appid_lists_are_strictly_normalized(self):
        spec=importlib.util.spec_from_file_location('original_role_list_guest',BASE/'tools/performance/guest.py')
        original=importlib.util.module_from_spec(spec);spec.loader.exec_module(original)
        for app in original.ROLE_APPS.values():
            # Actual declare_roles stores list(app['appids']); preserve it.
            self.assertEqual(dual.dual_role_pattern(list(app['appids'])),app['appids'])
            self.assertEqual(dual.dual_role_pattern(app['appids']),app['appids'])
        for invalid in ('foot',[],['foot','foot'],[True],['Foot'],['']):
            with self.subTest(invalid=invalid),self.assertRaises(RuntimeError):dual.dual_role_pattern(invalid)

    def test_root_boolean_negative_declarations_reject_without_worker(self):
        for uid in (0,True,-1):
            with self.subTest(uid=uid),self.assertRaises(RuntimeError):
                dual.DualClientObserver([],dict(uid=uid))

    def test_actual_owned_child_ancestry_and_foreign_sibling_refusal(self):
        child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        foreign=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        try:
            proof=dual.dual_window_ownership(dict(id=1,pid=child.pid),child,os.getuid(),('fixture','owned'),1)
            self.assertEqual(proof['process']['pid'],child.pid)
            self.assertEqual(proof['model'],'same-invocation-ancestry')
            with self.assertRaises(RuntimeError):
                dual.dual_window_ownership(dict(id=2,pid=foreign.pid),child,os.getuid(),('fixture','foreign'),1)
            self.assertIsNone(foreign.poll())
            proof2=dual.dual_window_ownership(dict(id=3,pid=child.pid),foreign,os.getuid(),('fixture','owned'),2)
            self.assertEqual(proof2['model'],'earlier-owned-role-process')
            key=('fixture','owned');dual.OWNED_ROLE_PROCESSES[key][child.pid]['process']['start_ticks']+=1
            with self.assertRaises(RuntimeError):
                dual.dual_window_ownership(dict(id=4,pid=child.pid),foreign,os.getuid(),key,3)
            self.assertIsNone(child.poll())
        finally:
            for process in (child,foreign):
                process.terminate();process.wait(timeout=2)

    def test_original_guest_and_comparator_remain_exact_and_integrity_delta_is_one_endpoint(self):
        import ast
        spec=importlib.util.spec_from_file_location('composer',HERE/'compose-feasibility.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        guest=(BASE/'tools/performance/guest.py').read_text()
        source=module.compose(guest,(HERE/'dual-observer.py').read_text())
        compile(source,'actual-composed-feasibility','exec')
        self.assertEqual(hashlib.sha256(guest.encode()).hexdigest(),module.BASE_GUEST_SHA)
        self.assertIn("bound['selected_upper_ns']",source)
        self.assertEqual(hashlib.sha256((BASE/'tools/performance/compare.py').read_bytes()).hexdigest(),
                         '6565ebac71dd8f32fd08c0fdae3bdfe95677d6f487294fe7269a812bac4a87e3')
        original=next(n for n in ast.parse(guest).body if isinstance(n,ast.FunctionDef)
                      and n.name=='verify_role_payload_after_first_gui')
        text=ast.get_source_segment(guest,original);old="bound['first_present_query']['worker_received_ns']"
        self.assertEqual(text.count(old),1)


class PeerDiscoveryControls(unittest.TestCase):
    """Actual owned pidfd/socket metadata; native Mango names/RPM are explicit mocks."""
    @contextmanager
    def fixture(self, *, environ=b'XDG_RUNTIME_DIR=/run/user/1000\0', comm='mango',
                process=None, packages=None, binary_fault=None, socket_fault=None):
        uid=os.getuid();pid=os.getpid();real_proc=dual.dual_proc_identity(pid)
        identity=dict(real_proc,exe='/usr/bin/mango') if process is None else process
        selected='/run/user/'+str(uid)+'/mango-'+str(pid)+'.sock'
        owner='mangowm-0:0.17.3-1.fixture.gitd13da6c.fc44.x86_64'
        replies=iter(packages if packages is not None else [owner,owner])
        opened=[];closed=[];real_open=dual.os.pidfd_open;real_close=dual.os.close
        with tempfile.TemporaryDirectory(prefix='arctic-peer-declaration-control-') as temp:
            actual=Path(temp)/'owned.sock';sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.bind(str(actual))
            counts=dict(binary_stat=0,socket_lstat=0)
            class ModelPath:
                def __init__(self,value):self.value=str(value)
                def __truediv__(self,value):return ModelPath(self.value+'/'+str(value))
                def __str__(self):return self.value
                def lstat(self):
                    original=actual.lstat();counts['socket_lstat']+=1
                    if socket_fault=='replacement' and counts['socket_lstat']>1:
                        return type('SocketStat',(),dict(st_dev=original.st_dev,st_ino=original.st_ino+1,st_uid=original.st_uid,st_mode=original.st_mode))()
                    return original
                def resolve(self,strict=True):return self
                def is_symlink(self):return binary_fault=='symlink'
                def is_file(self):return binary_fault!='not-file'
                def stat(self):
                    original=Path(sys.executable).stat();counts['binary_stat']+=1
                    if binary_fault=='replacement' and counts['binary_stat']>1:
                        return type('BinaryStat',(),dict(st_dev=original.st_dev,st_ino=original.st_ino,st_size=original.st_size+1,st_mtime_ns=original.st_mtime_ns,st_ctime_ns=original.st_ctime_ns))()
                    return original
                def read_text(self):
                    if self.value.endswith('/comm'):return comm
                    if self.value=='/run/t/performance-context.json':return json.dumps(dict(image='baseline',boot=1))
                    raise AssertionError('Unexpected source read '+self.value)
                def open(self,mode):
                    if isinstance(environ,BaseException):raise environ
                    return io.BytesIO(environ)
            def open_pidfd(target):
                self.assertEqual(target,pid);fd=real_open(target);opened.append(fd);return fd
            def close_pidfd(fd):closed.append(fd);real_close(fd)
            def command(argv):
                return next(replies) if argv[0]=='rpm' else '00000000-0000-0000-0000-000000000001'
            prefix=['runuser','-u','source-control','--','env','-i','XDG_RUNTIME_DIR=/run/user/'+str(uid),
                'WAYLAND_DISPLAY=wayland-0','XDG_SESSION_ID=source-control','MANGO_INSTANCE_SIGNATURE='+selected]
            try:
                with patch.object(dual,'Path',ModelPath),patch.object(dual.pwd,'getpwnam',return_value=type('Account',(),dict(pw_uid=uid))()),\
                     patch.object(dual,'dual_proc_identity',return_value=identity),\
                     patch.object(dual,'executable_file_identity',lambda st:dict(device=st.st_dev,inode=st.st_ino,size=st.st_size,mtime_ns=st.st_mtime_ns,ctime_ns=st.st_ctime_ns),create=True),\
                     patch.object(dual,'run',command,create=True),patch.object(dual.os,'pidfd_open',open_pidfd),\
                     patch.object(dual.os,'close',close_pidfd):
                    yield prefix,identity,opened,closed
            finally:
                sock.close()
                for fd in opened:
                    with self.assertRaises(OSError):os.fstat(fd)
                self.assertEqual(opened,closed)

    def test_canonical_selected_path_only_yields_provisional_pid(self):
        self.assertEqual(dual.dual_selected_socket_pid('/run/user/1000/mango-42.sock',1000,'/run/user/1000'),42)
        for path in ['/run/user/1000/mango-0.sock','/run/user/1000/mango-042.sock','/run/user/1000/mango.sock',
                     '/run/user/1000/nested/mango-42.sock','/run/user/1000/../1000/mango-42.sock',
                     '/run/user/1001/mango-42.sock','/tmp/mango-42.sock','/run/user/1000/mango-42.sock/']:
            with self.subTest(path=path),self.assertRaises(RuntimeError):dual.dual_selected_socket_pid(path,1000,'/run/user/1000')
        for uid in [True,0,-1,1000.0]:
            with self.subTest(uid=uid),self.assertRaises(RuntimeError):dual.dual_selected_socket_pid('/run/user/1000/mango-42.sock',uid,'/run/user/1000')
        with self.assertRaises(RuntimeError):dual.dual_selected_socket_pid('/run/user/1000/mango-42.sock',1000,'/run/user/1001')

    def test_initial_missing_or_different_post_exec_display_is_observed_not_authentication(self):
        for raw in [b'XDG_RUNTIME_DIR=/run/user/1000\0',b'WAYLAND_DISPLAY=old-display\0MANGO_INSTANCE_SIGNATURE=old-value\0']:
            with self.subTest(raw=raw),self.fixture(environ=raw) as (prefix,identity,_,_):
                declaration=dual.dual_peer_declaration(prefix)
                self.assertEqual(declaration['process'],identity)
                self.assertEqual(declaration['peer_discovery']['authentication_required_before_launch'],'watch-ready-so-peercred')
                observed=declaration['initial_environment_observation']
                self.assertEqual(observed['status'],'available');self.assertFalse(observed['required_for_authentication'])
                self.assertNotEqual(observed['values']['WAYLAND_DISPLAY'],'wayland-0')

    def test_unavailable_or_bounded_initial_environment_does_not_replace_credentials(self):
        for raw in [PermissionError('synthetic denied observation'),b'X'*65537,b'WAYLAND_DISPLAY=\xff\0']:
            with self.subTest(raw_type=type(raw).__name__),self.fixture(environ=raw) as (prefix,_,_,_):
                declaration=dual.dual_peer_declaration(prefix)
                self.assertEqual(declaration['initial_environment_observation']['status'],'unavailable')
                self.assertEqual(declaration['peer_discovery']['authentication_required_before_launch'],'watch-ready-so-peercred')

    def test_foreign_uid_executable_or_comm_is_not_provisional_mango(self):
        identity=dict(dual.dual_proc_identity(os.getpid()),exe='/usr/bin/mango')
        for process,comm in [(dict(identity,uid=identity['uid']+1),'mango'),(dict(identity,exe='/usr/bin/python3'),'mango'),(identity,'foreign')]:
            with self.subTest(process=process,comm=comm),self.fixture(process=process,comm=comm) as (prefix,_,_,_):
                with self.assertRaisesRegex(RuntimeError,'not the actual expected Mango'):dual.dual_peer_declaration(prefix)

    def test_exact_owner_source_and_architecture_remain_mandatory(self):
        correct='mangowm-0:0.17.3-1.fixture.gitd13da6c.fc44.x86_64'
        for owners in [[correct.replace('d13da6c','fe4742c')]*2,[correct.replace('x86_64','aarch64')]*2,
                       [correct,correct+'.foreign'],[correct.replace('mangowm','foreign')]*2]:
            with self.subTest(owners=owners),self.fixture(packages=owners) as (prefix,_,_,_):
                with self.assertRaisesRegex(RuntimeError,'RPM owner/source differs'):dual.dual_peer_declaration(prefix)

    def test_changed_process_or_exited_pidfd_refuses_and_closes_owned_fd(self):
        with self.fixture() as (prefix,identity,_,_):
            with patch.object(dual,'dual_proc_identity',side_effect=[identity,dict(identity,start_ticks=identity['start_ticks']+1)]):
                with self.assertRaisesRegex(RuntimeError,'identity changed'):dual.dual_peer_declaration(prefix)
        with self.fixture() as (prefix,_,_,_):
            with patch.object(dual.select,'select',side_effect=lambda read,write,error,timeout:(read,[],[])):
                with self.assertRaisesRegex(RuntimeError,'exited during provisional'):dual.dual_peer_declaration(prefix)

    def test_pidfd_close_failure_is_fatal_and_preserves_primary_failure_note(self):
        for primary in [False,True]:
            owners=['foreign','foreign'] if primary else None
            with self.subTest(primary=primary),self.fixture(packages=owners) as (prefix,_,_,_):
                normal_close=dual.os.close
                def close_then_fail(fd):normal_close(fd);raise RuntimeError('synthetic owned fd close failure')
                with patch.object(dual.os,'close',close_then_fail):
                    with self.assertRaises(RuntimeError) as caught:dual.dual_peer_declaration(prefix)
                if primary:
                    self.assertIn('RPM owner/source differs',str(caught.exception))
                    self.assertTrue(any('close failure' in note for note in caught.exception.__notes__))
                else:self.assertIn('owned fd close failure',str(caught.exception))

    def test_binary_kind_and_binary_or_socket_replacement_never_qualify(self):
        for binary,socket_fault in [('symlink',None),('not-file',None),('replacement',None),(None,'replacement')]:
            with self.subTest(binary=binary,socket=socket_fault),self.fixture(binary_fault=binary,socket_fault=socket_fault) as (prefix,_,_,_):
                with self.assertRaises(RuntimeError):dual.dual_peer_declaration(prefix)

    def test_pidfd_open_failure_has_no_authentication_or_unclosed_resource(self):
        with self.fixture() as (prefix,_,opened,closed):
            with patch.object(dual.os,'pidfd_open',side_effect=OSError('synthetic pidfd failure')):
                with self.assertRaisesRegex(OSError,'synthetic pidfd failure'):dual.dual_peer_declaration(prefix)
            self.assertEqual(opened,[]);self.assertEqual(closed,[])

    def test_actual_filename_pid_server_mismatch_never_reaches_app_launch(self):
        # A real owned live child supplies a valid PID/start/UID, while another
        # real same-UID process serves a socket carrying that child's name.
        actor=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
        real_popen=subprocess.Popen;processes=[];bounds=[];messages=[]
        try:
            with Server() as server:
                renamed=server.path.with_name('mango-'+str(actor.pid)+'.sock');server.path.rename(renamed);server.path=renamed
                declaration=server.declaration();identity=dual.dual_proc_identity(actor.pid)
                declaration.update(pid=actor.pid,process=identity,executable_identity=file_identity(identity['exe']))
                self.assertEqual(int(server.path.stem.split('-')[1]),actor.pid)
                self.assertNotEqual(actor.pid,os.getpid())
                def record(argv,*args,**kwargs):
                    self.assertNotIn('must-not-launch-before-ready',argv)
                    p=real_popen(argv,*args,**kwargs);processes.append(p);return p
                with patch.object(dual,'dual_peer_declaration',return_value=declaration),\
                     patch.object(dual,'emit',side_effect=lambda *args:messages.append(args),create=True),\
                     patch.object(dual.subprocess,'Popen',side_effect=record):
                    with self.assertRaisesRegex(RuntimeError,'peer PID/UID differs'):
                        dual.dual_startup([],['must-not-launch-before-ready'],['foot'],observations=bounds)
                self.assertEqual(bounds,[]);self.assertTrue(messages)
                self.assertEqual(len(processes),1)
                self.assertIsNotNone(processes[0].returncode)
                self.assertTrue(processes[0].stdout.closed and processes[0].stderr.closed)
        finally:
            actor.terminate();actor.wait(timeout=2)


if __name__=='__main__':unittest.main()
