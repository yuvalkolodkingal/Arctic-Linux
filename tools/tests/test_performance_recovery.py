"""Recovery controls use actual socket exchange and bounded ownership negatives."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import test_performance_observer as transport
import test_performance_roles as roles

guest = roles.guest
comparison = roles.comparison

class OwnershipRecoveryTest(unittest.TestCase):
    frontend = 'epiphany-1:50.6-1.fc44.x86_64'
    runtime = 'epiphany-runtime-1:50.6-1.fc44.x86_64'
    payload = b'\x7fELF' + b'bounded executable payload'

    def proof(self, *, frontend=None, owner=None, runtime=None, path='/usr/bin/epiphany',
              symlink=False, regular=True, resolved=None, payload=None, header=None, duplicates=False):
        data = self.payload if payload is None else payload
        digest = hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as tmp:
            file=Path(tmp)/'epiphany';file.write_bytes(data)
            virtual = types.SimpleNamespace(is_symlink=lambda:symlink,is_file=lambda:regular,
                resolve=lambda strict:resolved or path,stat=file.stat,open=file.open)
            entries=[self.frontend,self.runtime if runtime is None else runtime]
            if duplicates:entries.append(entries[-1])
            def run(argv):
                if argv[0]=='cat':return '00000000-0000-0000-0000-000000000001'
                return '/usr/bin/epiphany\t'+digest+'\t' if header is None else header
            with patch.object(guest,'EPIPHANY_EXPECTED_NATIVE_ELF_SHA256',digest),patch.object(guest,'Path',return_value=virtual),patch.object(guest,'run',side_effect=run),patch.object(guest,'emit'):
                package=guest.epiphany_family_ownership(path,frontend or self.frontend,
                    owner or self.runtime,dict(nevra=entries))
                now=time.monotonic_ns()
                app=dict(id='gnome-web',role='browser',program_path=path,package=package)
                bound=dict(launch_started_monotonic_ns=now-1000,first_present_query=dict(worker_received_ns=now-500))
                declared=dict(image='candidate',boot_context=dict(boot=1),pristine_state=dict(uid=1000))
                guest.verify_role_payload_after_first_gui(app,bound,now,declared)
                return package

    def test_actual_matching_family_keeps_exact_binary_digest(self):
        result=self.proof()
        self.assertEqual(result['runtime_nevra'],self.runtime)
        self.assertEqual(result['rpm_header_sha256'],hashlib.sha256(self.payload).hexdigest())
        self.assertEqual(result['post_first_gui_integrity']['executable_sha256'],result['rpm_header_sha256'])
        self.assertNotIn('executable_sha256',result)
        self.assertEqual(result['executable_path'],'/usr/bin/epiphany')

    def test_foreign_owner_versions_architecture_links_and_forged_payload_fail(self):
        faults=[dict(owner=self.frontend),dict(owner='foreign-1:50.6-1.fc44.x86_64'),
            dict(runtime='epiphany-runtime-1:50.7-1.fc44.x86_64'),
            dict(runtime='epiphany-runtime-0:50.6-1.fc44.x86_64'),
            dict(runtime='epiphany-runtime-1:50.6-1.fc44.aarch64'),
            dict(runtime='epiphany-helper-1:50.6-1.fc44.x86_64'),dict(duplicates=True),
            dict(path='/usr/local/bin/epiphany'),dict(symlink=True),dict(regular=False),dict(resolved='/opt/foreign'),
            dict(payload=b'#!/bin/sh'),dict(header='/usr/bin/epiphany\t'+'f'*64+'\t'),
            dict(header='/usr/bin/epiphany\t'+'f'*64+'\t/opt/foreign')]
        for fault in faults:
            with self.subTest(fault=fault),self.assertRaises(RuntimeError):self.proof(**fault)

    def test_saved_family_evidence_cannot_bypass_comparison_guards(self):
        for fault in ('owner','epoch','arch','version','missing','duplicate','path','hash','model'):
            runs=roles.paired_roles();r=runs['candidate'][0];p=r['app_roles']['roles']['browser']['package']
            if fault=='owner':p['binary_owner']='foreign-0:1-1.x86_64'
            elif fault=='epoch':p['runtime_nevra']='epiphany-runtime-1:1-1.x86_64'
            elif fault=='arch':p['runtime_nevra']='epiphany-runtime-0:1-1.aarch64'
            elif fault=='version':p['runtime_nevra']='epiphany-runtime-0:2-1.x86_64'
            elif fault=='missing':r['rpm_inventory']['nevra'].remove(p['runtime_nevra'])
            elif fault=='duplicate':r['rpm_inventory']['nevra'].append(p['runtime_nevra'])
            elif fault=='path':p['executable_path']='/opt/epiphany'
            elif fault=='hash':p['rpm_header_sha256']='f'*64
            else:p['ownership_model']='arbitrary-owner-allowed'
            # Mutations to inventory are correctly re-hashed, so this exercises
            # family validation instead of relying only on an inventory hash fault.
            entries=r['rpm_inventory']['nevra'];entries.sort()
            r['rpm_inventory']['sha256']=hashlib.sha256(('\n'.join(entries)+'\n').encode()).hexdigest()
            with self.subTest(fault=fault),self.assertRaises(ValueError):comparison.compare(runs)

class HistoricalFailureTest(unittest.TestCase):
    def test_reported_kitty_medians_still_fail_with_overlapping_control_ranges(self):
        # Reported historical medians are retained. The surrounding synthetic
        # ranges are an overlapping-range control, not invented historical boots.
        runs={image:[roles.legacy.run(image+str(n)) for n in range(3)] for image in ('baseline','candidate')}
        for image,values in [('baseline',(.12,.140385157,.18)),('candidate',(.13,.169684455,.20))]:
            for run,value in zip(runs[image],values):
                timing=run['startup_kitty_seconds'];timing['warm']=[value,value]
                for bound in timing['observation_bounds'][1:]:
                    bound.update(lower_seconds=value-.001,upper_seconds=value,interval_seconds=.001)
                    roles.legacy.worker_proof(bound)
        result=comparison.compare(runs)
        metric=next(row for row in result['metrics'] if row['metric']=='kitty_subsequent_mapped')
        self.assertTrue(metric['regression']);self.assertTrue(metric['range_overlap'])
        self.assertAlmostEqual(metric['percent_difference'],20.8706521537,places=6)
        self.assertEqual(result['status'],'regression_gate_failed')


class DeferredPayloadTest(unittest.TestCase):
    payload = b'\x7fELF' + b'actual payload fixture\n'*10000

    def prepare(self, directory):
        file=Path(directory)/'epiphany';file.write_bytes(self.payload)
        sha=hashlib.sha256(self.payload).hexdigest()
        virtual=types.SimpleNamespace(is_symlink=lambda:False,is_file=file.is_file,
            resolve=lambda strict:'/usr/bin/epiphany',stat=file.stat,open=file.open)
        before=guest.executable_file_identity(file.stat())
        package=dict(rpm_header_sha256=sha,prelaunch_file_identity=before)
        app=dict(id='gnome-web',role='browser',program_path='/usr/bin/epiphany',package=package)
        declared=dict(image='candidate',boot_context=dict(boot=1),pristine_state=dict(uid=1000))
        now=time.monotonic_ns()
        bound=dict(launch_started_monotonic_ns=now-1000,first_present_query=dict(worker_received_ns=now-500))
        return file,sha,virtual,app,declared,bound,now

    def test_prelaunch_never_opens_content_then_postlaunch_checks_actual_elf_and_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            file,sha,virtual,app,declared,bound,now=self.prepare(tmp)
            virtual.open=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Prelaunch executable read forbidden'))
            with patch.object(guest,'Path',return_value=virtual),patch.object(guest,'EPIPHANY_EXPECTED_NATIVE_ELF_SHA256',sha), \
                    patch.object(guest,'run',return_value='/usr/bin/epiphany\t'+sha+'\t'):
                result=guest.epiphany_family_ownership('/usr/bin/epiphany',OwnershipRecoveryTest.frontend,
                    OwnershipRecoveryTest.runtime,dict(nevra=[OwnershipRecoveryTest.frontend,OwnershipRecoveryTest.runtime]))
            self.assertEqual(result['prelaunch_content_bytes_read'],0)
            self.assertEqual(result['elf_magic_checked_bytes'],0)
            self.assertNotIn('executable_sha256',result)
            app['package']=result;virtual.open=file.open
            with patch.object(guest,'Path',return_value=virtual),patch.object(guest,'run',return_value='boot-fixture'),patch.object(guest,'emit') as emit:
                guest.verify_role_payload_after_first_gui(app,bound,now,declared)
            proof=app['package']['post_first_gui_integrity']
            self.assertEqual(proof['executable_sha256'],sha)
            self.assertGreaterEqual(proof['hash_started_ns'],proof['measurement_returned_ns'])
            self.assertEqual(emit.call_args.args[0],'role_payload_integrity')

    def test_changed_each_identity_field_rejects_before_content_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            file,sha,virtual,app,declared,bound,now=self.prepare(tmp)
            for field in ('device','inode','size','mtime_ns','ctime_ns'):
                changed=dict(app['package']['prelaunch_file_identity']);changed[field]+=1
                with self.subTest(field=field),patch.object(guest,'epiphany_file_identity',return_value=changed), \
                        patch.object(guest,'Path') as path,patch.object(guest,'emit') as emit:
                    with self.assertRaisesRegex(RuntimeError,'changed before'):guest.verify_role_payload_after_first_gui(app,bound,now,declared)
                    path.assert_not_called();emit.assert_not_called()

    def test_wrong_fd_same_stat_path_and_wrong_actual_hash_are_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            file,sha,virtual,app,declared,bound,now=self.prepare(tmp)
            other=Path(tmp)/'foreign';other.write_bytes(self.payload)
            with patch.object(guest,'Path',return_value=virtual),patch.object(guest,'emit') as emit:
                virtual.open=other.open
                with self.assertRaisesRegex(RuntimeError,'different executable'):guest.verify_role_payload_after_first_gui(app,bound,now,declared)
                virtual.open=file.open;app['package']['rpm_header_sha256']='f'*64
                with self.assertRaisesRegex(RuntimeError,'actual ELF payload'):guest.verify_role_payload_after_first_gui(app,bound,now,declared)
                emit.assert_not_called()

    def test_same_payload_with_metadata_changed_during_hash_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            file,sha,virtual,app,declared,bound,now=self.prepare(tmp)
            original=file.open
            class ChangingReader:
                def __enter__(self):self.binary=original('rb');self.changed=False;return self
                def __exit__(self,*args):self.binary.close()
                def fileno(self):return self.binary.fileno()
                def read(self,size):
                    data=self.binary.read(size)
                    if not self.changed:
                        self.changed=True;info=file.stat()
                        # Payload bytes stay identical; metadata guard must catch
                        # this even though a whole-file digest would still match.
                        os.utime(file,ns=(info.st_atime_ns,info.st_mtime_ns+10_000_000))
                    return data
            virtual.open=lambda mode:ChangingReader()
            with patch.object(guest,'Path',return_value=virtual),patch.object(guest,'emit') as emit:
                with self.assertRaisesRegex(RuntimeError,'changed while'):guest.verify_role_payload_after_first_gui(app,bound,now,declared)
                emit.assert_not_called()
            self.assertEqual(hashlib.sha256(file.read_bytes()).hexdigest(),sha)

    def test_omitted_early_late_stale_and_prewarmed_proof_cannot_pass_even_done_true(self):
        faults=('missing','wrong_digest','boot','image','uid','role','phase','early','late','map','launch',
                'stat','bool_stat','boolean_time','prehash','magic_read','content_read','missing_precond')
        for fault in faults:
            runs=roles.paired_roles();r=runs['candidate'][0];p=r['app_roles']['roles']['browser']['package'];v=r['role_payload_integrity']
            if fault=='missing':r.pop('role_payload_integrity')
            elif fault=='wrong_digest':v['executable_sha256']='f'*64
            elif fault=='boot':v['boot_id']='foreign-boot'
            elif fault=='image':v['image']='baseline'
            elif fault=='uid':v['desktop_uid']=1001
            elif fault=='role':v['role']='terminal'
            elif fault=='phase':v['phase']='before_first_gui'
            elif fault=='early':v['hash_started_ns']=v['first_gui_launch_ns']-1
            elif fault=='late':v['hash_finished_ns']=r['precondition_role_terminal']['launch_started_monotonic_ns']+1
            elif fault=='map':v['first_gui_map_upper_ns']+=1
            elif fault=='launch':v['first_gui_launch_ns']+=1
            elif fault=='stat':v['after_hash_identity']['inode']+=1
            elif fault=='bool_stat':v['before_hash_identity']['device']=True
            elif fault=='boolean_time':v['hash_finished_ns']=True
            elif fault=='prehash':p['executable_sha256']=p['rpm_header_sha256']
            elif fault=='magic_read':p['elf_magic_checked_bytes']=4
            elif fault=='content_read':p['prelaunch_content_bytes_read']=4096
            else:r['precondition_role_terminal'].pop('launch_started_monotonic_ns')
            self.assertTrue(r['done'])
            with self.subTest(fault=fault),self.assertRaises(ValueError):comparison.compare(runs)

    def test_full_verification_is_between_last_first_gui_and_first_precondition(self):
        declared=roles.role_run('candidate',1)['app_roles'];events=[]
        workload=dict(files='/tmp/fixture',url='http://127.0.0.1:1/benchmark.html')
        def startup(prefix,command,appids,**kwargs):
            events.append(('precondition:' if kwargs.get('hold_seconds')==45 else 'cold:')+command[0])
            kwargs['observations'].append(dict(launch_started_monotonic_ns=1,first_present_query=dict(worker_received_ns=2)))
            return .04
        def verify(*args):events.append('actual-elf-and-full-hash')
        with patch.object(guest,'startup',side_effect=startup),patch.object(guest,'emit'), \
                patch.object(guest,'epiphany_file_identity',return_value=declared['roles']['browser']['package']['prelaunch_file_identity']), \
                patch.object(guest,'verify_role_payload_after_first_gui',side_effect=verify):
            guest.first_use_and_precondition([],declared,workload)
        self.assertEqual(events,['cold:foot','cold:pcmanfm','cold:epiphany','actual-elf-and-full-hash',
                                 'precondition:foot','precondition:pcmanfm','precondition:epiphany'])

    def test_failed_postverification_stops_before_any_preconditioning(self):
        declared=roles.role_run('candidate',1)['app_roles'];calls=[]
        def startup(*args,**kwargs):
            calls.append(kwargs.get('hold_seconds',5));kwargs['observations'].append(dict(launch_started_monotonic_ns=1))
            return .04
        with patch.object(guest,'startup',side_effect=startup),patch.object(guest,'emit'), \
                patch.object(guest,'epiphany_file_identity',return_value=declared['roles']['browser']['package']['prelaunch_file_identity']), \
                patch.object(guest,'verify_role_payload_after_first_gui',side_effect=RuntimeError('bad payload')):
            with self.assertRaisesRegex(RuntimeError,'bad payload'):
                guest.first_use_and_precondition([],declared,dict(files='/tmp/f',url='http://127.0.0.1:1/benchmark.html'))
        self.assertEqual(calls,[5,5,5])


class WorkerClockRecoveryTest(unittest.TestCase):
    def test_actual_socket_timestamps_exclude_parent_normalization_delay(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture=transport.MangoFixture(tmp,lambda:b'{"clients":[]}\n')
            original=guest.json.loads
            def delayed(value):
                time.sleep(.025)
                return original(value)
            try:
                with guest.NativeClientQuery(['env','MANGO_INSTANCE_SIGNATURE='+fixture.path]) as query:
                    with patch.object(guest.json,'loads',side_effect=delayed):self.assertEqual(query.query(),{})
                    returned=time.monotonic_ns();proof=query.last_query_bounds
                    self.assertGreaterEqual(returned-proof['worker_received_ns'],20_000_000)
                    self.assertLessEqual(proof['parent_started_ns'],proof['worker_sent_ns'])
                    self.assertLessEqual(proof['worker_received_ns'],proof['parent_received_ns'])
            finally:fixture.close()

    def test_delayed_negative_snapshot_retains_true_map_and_fails_precision(self):
        state=dict(queries=0,mapped_ns=None)
        def response():
            state['queries']+=1
            if state['queries']==2:
                # Snapshot is negative; mapping happens before that old response
                # arrives. Receipt-side lower bounds would be unsound.
                time.sleep(.012);state['mapped_ns']=time.monotonic_ns();time.sleep(.012)
                return b'{"clients":[]}\n'
            return json.dumps(dict(clients=[] if state['mapped_ns'] is None else
                [dict(id=1,appid='kitty',title='fixture')])).encode()+b'\n'
        with tempfile.TemporaryDirectory() as tmp:
            fixture=transport.MangoFixture(tmp,response);bounds=[]
            try:
                with patch.object(guest,'clients',side_effect=[{}, {'1':dict(id=1,appid='kitty')}]), \
                        patch.object(guest,'snapshot',return_value={}),patch.object(guest,'emit'), \
                        patch.object(guest.subprocess,'run',return_value=subprocess.CompletedProcess([],0)):
                    guest.startup(['env','MANGO_INSTANCE_SIGNATURE='+fixture.path],
                        [sys.executable,'-c','import time;time.sleep(10)'],'kitty',
                        timeout=3,hold_seconds=.001,observations=bounds)
                bound=bounds[0];actual=(state['mapped_ns']-bound['launch_started_monotonic_ns'])/1e9
                self.assertLessEqual(bound['lower_seconds'],actual)
                self.assertGreaterEqual(bound['upper_seconds'],actual)
                comparison.worker_mapping_proof(bound)
                self.assertGreater(bound['interval_seconds'],.005)
            finally:fixture.close()

    def test_actual_worker_forged_clock_envelopes_fail_without_fallback(self):
        for fault in ('boolean','reversed','future','old','uid'):
            code="""import os,json,sys,time
for line in sys.stdin:
 t=time.monotonic_ns();a,b,c=t,t,t
 if FAULT=='boolean':a=True
 elif FAULT=='reversed':b=t+1_000_000
 elif FAULT=='future':c=t+1_000_000_000
 elif FAULT=='old':a=1
 print(json.dumps(dict(uid=os.getuid()+(1 if FAULT=='uid' else 0),payload=dict(clients=[]),query_seconds=0,query_started_ns=a,query_sent_ns=b,query_received_ns=c)),flush=True)
""".replace('FAULT',repr(fault))
            with self.subTest(fault=fault),patch.object(guest,'CLIENT_QUERY_WORKER',code):
                with guest.NativeClientQuery([]) as query:
                    with self.assertRaises(RuntimeError):query.query()

    def test_valid_response_followed_by_actual_worker_eof3_is_fatal(self):
        code="""import os,json,sys,time
for line in sys.stdin:
 t=time.monotonic_ns()
 print(json.dumps(dict(uid=os.getuid(),payload=dict(clients=[]),query_seconds=0,query_started_ns=t,query_sent_ns=t,query_received_ns=t)),flush=True)
raise SystemExit(3)
"""
        with patch.object(guest,'CLIENT_QUERY_WORKER',code):
            with self.assertRaisesRegex(RuntimeError,'Native observer cleanup exited 3'):
                with guest.NativeClientQuery([]) as query:self.assertEqual(query.query(),{})
        self.assertEqual(query.process.returncode,3)
        self.assertTrue(query.process.stdout.closed and query.process.stderr.closed)

    def test_forced_cleanup_of_unresponsive_worker_is_fatal_and_reaped(self):
        code="""import os,json,sys,time
for line in sys.stdin:
 t=time.monotonic_ns()
 print(json.dumps(dict(uid=os.getuid(),payload=dict(clients=[]),query_seconds=0,query_started_ns=t,query_sent_ns=t,query_received_ns=t)),flush=True)
time.sleep(30)
"""
        started=time.monotonic()
        with patch.object(guest,'CLIENT_QUERY_WORKER',code):
            with self.assertRaisesRegex(RuntimeError,'Native observer cleanup exited -'):
                with guest.NativeClientQuery([]) as query:query.query()
        self.assertLess(time.monotonic()-started,4.5)
        self.assertIsNotNone(query.process.poll())

    def test_body_error_remains_primary_after_worker_eof3(self):
        code="""import os,json,sys,time
for line in sys.stdin:
 t=time.monotonic_ns()
 print(json.dumps(dict(uid=os.getuid(),payload=dict(clients=[]),query_seconds=0,query_started_ns=t,query_sent_ns=t,query_received_ns=t)),flush=True)
raise SystemExit(3)
"""
        with patch.object(guest,'CLIENT_QUERY_WORKER',code):
            with self.assertRaisesRegex(RuntimeError,'original body failure'):
                with guest.NativeClientQuery([]) as query:
                    query.query();raise RuntimeError('original body failure')
        self.assertEqual(query.process.returncode,3)

    def test_uncaught_query_error_remains_primary_after_failed_worker(self):
        with patch.object(guest,'CLIENT_QUERY_WORKER','raise RuntimeError("worker protocol failed")'):
            with self.assertRaisesRegex(RuntimeError,'Native Mango observer disconnected'):
                with guest.NativeClientQuery([]) as query:query.query()
        self.assertNotEqual(query.process.returncode,0)

    def test_raw_clock_or_relative_bounds_forgery_cannot_qualify(self):
        for fault in ('missing','boolean','uid','both_uid','reversed','overlap','relative','basis','prelaunch'):
            runs=roles.paired_roles();b=runs['candidate'][0]['startup_role_terminal_cold_seconds']['observation_bounds'][0]
            if fault=='missing':b.pop('first_present_query')
            elif fault=='boolean':b['first_present_query']['worker_received_ns']=True
            elif fault=='uid':b['first_present_query']['uid']=1001
            elif fault=='both_uid':b['first_present_query']['uid']=b['last_absent_query']['uid']=1001
            elif fault=='reversed':b['first_present_query']['worker_sent_ns']+=1000000000
            elif fault=='overlap':b['last_absent_query']['parent_received_ns']=b['first_present_query']['parent_started_ns']+1
            elif fault=='relative':b['launch_started_monotonic_ns']+=100000
            elif fault=='basis':b['bound_basis']='receipt-lower'
            else:b['launch_started_monotonic_ns']=b['first_present_query']['worker_received_ns']+1
            with self.subTest(fault=fault),self.assertRaises(ValueError):comparison.compare(runs)

if __name__=='__main__':unittest.main()
