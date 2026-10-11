"""Full unfiltered owned-process fixtures; no actual guest or qualification."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('journal_stream_actual_native',HERE/'native_smoke.py')
N=importlib.util.module_from_spec(spec);spec.loader.exec_module(N)
spec=importlib.util.spec_from_file_location('journal_stream_actual_diagnostic',HERE.parent/'installer-qualification/guest.py')
G=importlib.util.module_from_spec(spec);spec.loader.exec_module(G)
STATE={'selinux':'Enforcing','audit':{'enabled':1,'lost':0}}
CURSOR='owned-synthetic-cursor'
JOURNAL=['journalctl','-b','--no-pager','--after-cursor',CURSOR,'-o','json','--quiet']
PRODUCER='''import json,os,sys,time
mode=sys.argv[2]
if mode in ('sleep','fork'):
 if mode=='fork':
  child=os.fork()
  if child:open(sys.argv[1]+'.child','w').write(str(child));raise SystemExit(0)
 time.sleep(30);raise SystemExit(0)
if mode=='exit':raise SystemExit(7)
if mode=='stderr':
 for _ in range(70):os.write(2,b'x'*65536)
 raise SystemExit(0)
if mode=='both':
 for _ in range(200):
  os.write(2,b'notice\\n');os.write(1,b'{"MESSAGE":"ordinary"}\\n')
 raise SystemExit(0)
if mode=='malformed':os.write(1,b'{bad}\\n');raise SystemExit(0)
if mode=='truncated':os.write(1,b'{"MESSAGE":"ordinary"}');raise SystemExit(0)
if mode=='kind':os.write(1,b'[]\\n');raise SystemExit(0)
if mode=='line':
 os.write(1,b'{"MESSAGE":"'+b'x'*(4*1024*1024)+b'"}\\n');raise SystemExit(0)
if mode=='rawcap':
 row=json.dumps({'MESSAGE':'ordinary '+'x'*2048}).encode()+b'\\n'
 for _ in range(33000):os.write(1,row)
 raise SystemExit(0)
with open(sys.argv[1],'rb') as source:
 while True:
  block=source.read(65536)
  if not block:break
  os.write(1,block)
if mode=='late-stderr':
 for _ in range(20):os.write(2,b'x'*65536)
'''

def restore_journal_filter_native(source):
    """Exact streaming inverse before inherited whole-byte security proofs."""
    start=source.index('def execute_journal_interval(argv, *, timeout=60):\n')
    end=source.index('def digest(path):\n',start)
    source=source[:start]+source[end:]
    new="journal = execute_journal_interval(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor,\n                                            '-o', 'json', '--quiet'], timeout=60)[1]"
    old="journal = execute(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor,\n                           '-o', 'json'], timeout=60)[1]"
    if source.count(new)!=1:raise AssertionError('Journal streaming inverse occurrence differs')
    return source.replace(new,old)

class JournalStreamControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='arctic-journal-stream-owned-')
        self.root=Path(self.tmp.name);self.producer=self.root/'producer.py';self.producer.write_text(PRODUCER)
        self.fixture=self.root/'interval.jsonl';self.fixture.write_bytes(b'');self.processes=[]
    def tearDown(self):
        for process in self.processes:
            self.assertIsNotNone(process.returncode,'Owned child not reaped')
            with self.assertRaises(ChildProcessError):os.waitpid(process.pid,os.WNOHANG)
        self.tmp.cleanup()
    def route(self,mode='copy'):
        real=subprocess.Popen
        def routed(argv,**kwargs):
            self.assertEqual(argv,JOURNAL)
            self.assertEqual(kwargs,dict(stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,close_fds=True,start_new_session=True))
            process=real([sys.executable,str(self.producer),str(self.fixture),mode],**kwargs)
            self.processes.append(process);return process
        return mock.patch.object(N.subprocess,'Popen',side_effect=routed)
    def interval(self):
        value=N.SecurityInterval.__new__(N.SecurityInterval);value.before=copy.deepcopy(STATE)
        value.cursor=CURSOR;value.audit_file=self.root/'audit.log';value.audit_offset=None;return value
    def finish(self,value=None,mode='copy'):
        value=value or self.interval()
        with mock.patch.object(value,'state',return_value=copy.deepcopy(STATE)),self.route(mode):return value.finish()
    def rows(self,*messages):
        self.fixture.write_text(''.join(json.dumps({'MESSAGE':value})+'\n' for value in messages))
    def noise(self,late=None):
        row=json.dumps({'MESSAGE':'ordinary copy progress '+'x'*2048})+'\n'
        with self.fixture.open('w') as stream:
            for _ in range(4600):stream.write(row)
            if late is not None:stream.write(json.dumps({'MESSAGE':late})+'\n')
        self.assertGreater(self.fixture.stat().st_size,9*1024*1024)
    def raised(self,fn,kind=RuntimeError):
        try:fn()
        except kind as error:return error
        self.fail('Expected rejection absent')
    def test_duplicate_MESSAGE_later_denial_and_original_guard(self):
        self.rows(['ordinary copy progress','AVC: denied'])
        error=self.raised(self.finish);row=G.security_finalization_diagnostic(error,N)
        self.assertEqual(row['guard'],'guard-008');self.assertEqual(row['avc_count'],1)
        self.assertEqual(row['step'],'verify-security')
    def test_real_nine_MiB_noise_passes_and_late_denial_rejects(self):
        self.noise();self.assertEqual(self.finish()['observed_new_avcs'],0)
        self.noise(['ordinary','type=USER_AVC denied'])
        self.assertEqual(G.security_finalization_diagnostic(self.raised(self.finish),N)['guard'],'guard-008')
    def test_original_all_MESSAGE_semantics_case_multiline_types_and_Unicode(self):
        for message in ('AVC: DENIED','prefix\navc:\tdenied','type=USER_AVC','type=AVC','aVc:\u2003denied',
                        ['ordinary','avc: denied'],{'nested':'AVC: denied'}):
            self.rows(message);self.assertEqual(G.security_finalization_diagnostic(self.raised(self.finish),N)['guard'],'guard-008')
        self.rows('benign AVC progress',None,['ordinary','completed']);self.assertEqual(self.finish()['observed_new_avcs'],0)
    def test_empty_normal_zero_and_original_execute_exit_one_rejected(self):
        self.assertEqual(self.finish()['observed_new_avcs'],0)
        with self.assertRaisesRegex(RuntimeError,'^command failed'):
            N.execute([sys.executable,'-c','raise SystemExit(1)'])
        self.assertNotIn('empty_is_success',__import__('inspect').signature(N.execute).parameters)
    def test_selected_record_plus_stderr_bound_and_closed_source_diagnostic(self):
        row=json.dumps({'MESSAGE':'AVC: denied '+'x'*2048})+'\n';self.fixture.write_text(row*2200)
        error=self.raised(self.finish);diag=G.security_finalization_diagnostic(error,N)
        self.assertEqual(diag['command'],'journal-interval');self.assertEqual(diag['step'],'journal-query')
        self.assertIn(diag['guard'],G.SECURITY_DIAGNOSTIC_GUARDS);self.assertNotEqual(diag['guard'],'unknown')
        self.assertNotIn('denied',G.masked_security_finalization_error(error,N))
        self.assertGreater(diag['stdout_bytes'],N.LIMIT)
    def test_stderr_overflow_and_both_pipe_drain(self):
        error=self.raised(lambda:self.finish(mode='stderr'));self.assertIn('evidence bound',str(error))
        self.assertEqual(self.finish(mode='both')['observed_new_avcs'],0)
    def test_late_stderr_counts_against_selected_full_record_bound(self):
        row=json.dumps({'MESSAGE':'AVC: denied '+'x'*2048})+'\n'
        self.fixture.write_text(row*1550)
        error=self.raised(lambda:self.finish(mode='late-stderr'))
        self.assertEqual(str(error),'journal selected evidence bound exceeded')
        diag=G.security_finalization_diagnostic(error,N)
        self.assertGreater(diag['stdout_bytes'],3*1024*1024)
        self.assertGreater(diag['stderr_bytes'],0)
    def test_new_closed_guard_actual_strict_report_consumer(self):
        spec=importlib.util.spec_from_file_location('journal_stream_actual_runner',HERE.parent/'installer-qualification/runner.py')
        old_path=list(sys.path)
        try:
            sys.path.insert(0,str(HERE.parent/'installer-qualification'))
            R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
        finally:sys.path[:]=old_path
        error=self.raised(lambda:self.finish(mode='kind'))
        mask=G.masked_security_finalization_error(error,N)
        row=G.security_finalization_diagnostic(error,N)
        codes=R.primary_reported_codes({'errors':[mask]},True)
        self.assertIn('installer-reported-active-primary-security-guard-'+row['guard'],codes)
        self.assertNotIn('PRIVATE_',mask)
        self.assertNotIn('installer-reported-active-primary-security-guard-guard-999',R.primary_reported_codes({'errors':[mask.replace(row['guard'],'guard-999')]},True))
    def test_malformed_truncated_nonobject_and_long_line_fail_closed(self):
        for mode,kind in [('malformed',json.JSONDecodeError),('truncated',RuntimeError),('kind',RuntimeError),('line',RuntimeError)]:
            self.raised(lambda:self.finish(mode=mode),kind)
    def test_raw_processing_cap_fails_instead_of_partial_pass(self):
        error=self.raised(lambda:self.finish(mode='rawcap'));self.assertEqual(str(error),'journal raw processing cap exceeded')
    def test_command_exit_fail_and_timeout_owned_reap(self):
        error=self.raised(lambda:self.finish(mode='exit'));diag=G.security_finalization_diagnostic(error,N)
        self.assertEqual(diag['exit_code'],7);self.assertEqual(diag['command'],'journal-interval')
        with self.route('sleep'):
            error=self.raised(lambda:N.execute_journal_interval(JOURNAL,timeout=.05),subprocess.TimeoutExpired)
        self.assertEqual(error.timeout,.05)
    def test_owned_descendant_holding_pipe_is_killed_before_leader_reap(self):
        with self.route('fork'):
            self.raised(lambda:N.execute_journal_interval(JOURNAL,timeout=.2),subprocess.TimeoutExpired)
        child=int(Path(str(self.fixture)+'.child').read_text());end=time.monotonic()+2
        while time.monotonic()<end:
            try:state=(Path('/proc')/str(child)/'stat').read_text().rsplit(')',1)[1].split()[0]
            except FileNotFoundError:break
            if state in ('Z','X'):break
            time.sleep(.01)
        else:self.fail('Owned descendant remained running')
    def test_cancellation_identity_preserved_and_owned_streams_closed(self):
        class FalseyCancel(KeyboardInterrupt):
            def __bool__(self):return False
        primary=FalseyCancel('PRIVATE_CANCEL_SENTINEL');real_select=N.selectors.DefaultSelector
        class CancelSelector:
            def __init__(self):self.inner=real_select()
            def register(self,*a):return self.inner.register(*a)
            def get_map(self):return self.inner.get_map()
            def select(self,*a):raise primary
            def close(self):self.inner.close();raise OSError('PRIVATE_CLOSE_SENTINEL')
        with self.route('sleep'),mock.patch.object(N.selectors,'DefaultSelector',CancelSelector):
            error=self.raised(lambda:N.execute_journal_interval(JOURNAL),FalseyCancel)
        self.assertIs(error,primary)
        self.assertTrue(all(p.stdout.closed and p.stderr.closed for p in self.processes))
    def test_audit_file_only_AVC_rotation_and_original_bounds(self):
        value=self.interval();value.audit_file.write_text('old\n');st=value.audit_file.stat();value.audit_offset=(st.st_dev,st.st_ino,st.st_size)
        with value.audit_file.open('a') as stream:stream.write('type=USER_AVC denied\n')
        self.assertEqual(G.security_finalization_diagnostic(self.raised(lambda:self.finish(value)),N)['guard'],'guard-008')
        value.audit_file.rename(self.root/'old-audit');value.audit_file.write_text('new')
        self.assertEqual(G.security_finalization_diagnostic(self.raised(lambda:self.finish(value)),N)['guard'],'guard-009')
        value=self.interval();value.audit_file.write_bytes(b'x'*(N.LIMIT+1))
        self.assertEqual(G.security_finalization_diagnostic(self.raised(lambda:self.finish(value)),N)['guard'],'guard-011')
        st=value.audit_file.stat();value.audit_offset=(st.st_dev,st.st_ino,0)
        self.assertEqual(G.security_finalization_diagnostic(self.raised(lambda:self.finish(value)),N)['guard'],'guard-010')
    def test_original_Enforcing_audit_mode_and_loss_guards(self):
        for after,guard in [({'selinux':'Permissive','audit':{'enabled':1,'lost':0}},'guard-005'),
                            ({'selinux':'Enforcing','audit':{'enabled':0,'lost':0}},'guard-006'),
                            ({'selinux':'Enforcing','audit':{'enabled':1,'lost':1}},'guard-007')]:
            self.assertEqual(G.security_finalization_diagnostic(self.raised(lambda:N.verify_security(STATE,after,'')),N)['guard'],guard)
    def test_whole_original_native_and_generated_guest_byte_rollback(self):
        source=(HERE/'native_smoke.py').read_text();original=restore_journal_filter_native(source)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(),'d7c69563a4a9908d4e4c8c937222f7e814440bfbb6c06de07fbd32b7e0caa4f8')
        guest=(HERE/'guest-check-native-v6.py').read_text();self.assertTrue(guest.startswith(source[:source.index('def main():\n')]))
        restored=restore_journal_filter_native(guest).replace(hashlib.sha256(source.encode()).hexdigest(),'d7c69563a4a9908d4e4c8c937222f7e814440bfbb6c06de07fbd32b7e0caa4f8')
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(),'e9135f35df4fc3c39ff825e2e37bee253158623b5a9a81cbf841db1f8df7a93b')
if __name__=='__main__':unittest.main(verbosity=2)
