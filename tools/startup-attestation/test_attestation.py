"""Meaningful owned host fixture controls; no VM, guest CLI, Git or Mango."""
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location('test_'+name,HERE/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
C=load('attest-startup-v1');F=load('runtime-fixtures-v1');T=load('toolkit')
EXE=str(Path(sys.executable).resolve());ENV={b'PATH':b'/usr/bin:/bin',b'LANG':b'C.UTF-8'}

class ProbeTests(unittest.TestCase):
    def test_real_memfd_all_positive_and_negative_cases_close(self):
        rows=F.seal_controls();self.assertEqual(len(rows),5);self.assertTrue(all(v['FD_closed'] for v in rows))
    def test_real_owned_provider_success_exact_bytes(self):
        with tempfile.TemporaryDirectory() as root:
            result=F.fixture([EXE,'-c','import os;os.write(1,b"own\\0bytes")'],ENV,root)
            self.assertEqual(result,b'own\0bytes')
    def test_early_pidfd_failure_reaps_own_process_and_closes_both_pipes(self):
        with tempfile.TemporaryDirectory() as root:
            real=F.subprocess.Popen;processes=[]
            def popen(*args,**kw):
                value=real(*args,**kw);processes.append(value);return value
            with patch.object(F.subprocess,'Popen',side_effect=popen),patch.object(F.os,'pidfd_open',side_effect=OSError('own pidfd exhausted')),patch.object(F.os,'killpg',side_effect=AssertionError('unverified group signal')),self.assertRaisesRegex(OSError,'pidfd exhausted'):
                F.fixture([EXE,'-c','import time;time.sleep(10)'],ENV,root)
            self.assertIsNotNone(processes[0].returncode);self.assertTrue(processes[0].stdout.closed);self.assertTrue(processes[0].stderr.closed)
            with self.assertRaises(ChildProcessError):os.waitpid(processes[0].pid,os.WNOHANG)
    def test_early_getpgid_failure_reaps_only_pidfd_bound_child_without_group_signal(self):
        with tempfile.TemporaryDirectory() as root:
            real=F.subprocess.Popen;real_open=F.os.pidfd_open;real_send=F.signal.pidfd_send_signal
            processes=[];descriptors=[];sent=[]
            def popen(*args,**kw):
                value=real(*args,**kw);processes.append(value);return value
            def opening(*args):
                fd=real_open(*args);descriptors.append(fd);return fd
            def sending(fd,sig,*args):
                sent.append((fd,sig));return real_send(fd,sig,*args)
            with patch.object(F.subprocess,'Popen',side_effect=popen),patch.object(F.os,'pidfd_open',side_effect=opening),patch.object(F.os,'getpgid',side_effect=OSError('own group proof unavailable')),patch.object(F.os,'killpg',side_effect=AssertionError('unverified group signal')),patch.object(F.signal,'pidfd_send_signal',side_effect=sending),self.assertRaisesRegex(OSError,'group proof unavailable'):
                F.fixture([EXE,'-c','import time;time.sleep(10)'],ENV,root)
            self.assertEqual(sent,[(descriptors[0],signal.SIGKILL)])
            self.assertIsNotNone(processes[0].returncode);self.assertTrue(processes[0].stdout.closed);self.assertTrue(processes[0].stderr.closed)
            with self.assertRaises(ChildProcessError):os.waitpid(processes[0].pid,os.WNOHANG)
            for fd in descriptors:
                with self.assertRaises(OSError):os.fstat(fd)
    def test_unavailable_or_wrong_waitid_proof_never_signals_and_preserves_primary(self):
        for kind in ['unavailable','wrong-child']:
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as root:
                real=F.subprocess.Popen;processes=[]
                def popen(*args,**kw):
                    value=real(*args,**kw);processes.append(value);return value
                def proof(*args):
                    if kind=='unavailable':raise OSError('owned waitid proof unavailable')
                    return type('WrongChild',(),{'si_pid':processes[0].pid+1})()
                with patch.object(F.subprocess,'Popen',side_effect=popen),patch.object(F.os,'pidfd_open',side_effect=OSError('own pidfd exhausted')),patch.object(F.os,'waitid',side_effect=proof),patch.object(F.os,'killpg',side_effect=AssertionError('unverified group signal')),patch.object(F.os,'kill',side_effect=AssertionError('unproven child signal')):
                    with self.assertRaisesRegex(OSError,'pidfd exhausted') as result:
                        F.fixture([EXE,'-c','import time;time.sleep(.1)'],ENV,root)
                self.assertTrue(any('cleanup also failed' in v for v in result.exception.__notes__))
                self.assertEqual(processes[0].returncode,0);self.assertTrue(processes[0].stdout.closed);self.assertTrue(processes[0].stderr.closed)
                with self.assertRaises(ChildProcessError):os.waitpid(processes[0].pid,os.WNOHANG)
    def test_late_group_revalidation_failure_uses_retained_pidfd_and_reaps(self):
        with tempfile.TemporaryDirectory() as root:
            real=F.subprocess.Popen;real_open=F.os.pidfd_open;real_group=F.os.getpgid;real_send=F.signal.pidfd_send_signal
            processes=[];descriptors=[];lookups=[];sent=[]
            def popen(*args,**kw):
                value=real(*args,**kw);processes.append(value)
                def communicate(*args,**kw):raise RuntimeError('owned body communication failed')
                value.communicate=communicate
                return value
            def opening(*args):
                fd=real_open(*args);descriptors.append(fd);return fd
            def group(pid):
                lookups.append(pid)
                if len(lookups)>1:raise OSError('owned late group proof unavailable')
                return real_group(pid)
            def sending(fd,sig,*args):
                sent.append((fd,sig));return real_send(fd,sig,*args)
            with patch.object(F.subprocess,'Popen',side_effect=popen),patch.object(F.os,'pidfd_open',side_effect=opening),patch.object(F.os,'getpgid',side_effect=group),patch.object(F.os,'killpg',side_effect=AssertionError('unverified group signal')),patch.object(F.signal,'pidfd_send_signal',side_effect=sending):
                with self.assertRaisesRegex(RuntimeError,'communication failed') as result:
                    F.fixture([EXE,'-c','import time;time.sleep(2.4)'],ENV,root)
            self.assertEqual(lookups,[processes[0].pid,processes[0].pid]);self.assertEqual(sent,[(descriptors[0],signal.SIGKILL)])
            self.assertTrue(any('late group proof unavailable' in v for v in result.exception.__notes__))
            self.assertEqual(processes[0].returncode,-signal.SIGKILL);self.assertTrue(processes[0].stdout.closed);self.assertTrue(processes[0].stderr.closed)
            with self.assertRaises(ChildProcessError):os.waitpid(processes[0].pid,os.WNOHANG)
            for fd in descriptors:
                with self.assertRaises(OSError):os.fstat(fd)
    def test_actual_outer_pidfd_close_error_prevents_return(self):
        real_open=F.os.pidfd_open;real_close=F.os.close;owned=[];attempts=[]
        def opening(*args):
            fd=real_open(*args);owned.append(fd);return fd
        def close(fd):
            real_close(fd)
            if fd in owned:attempts.append(fd);raise OSError('actual fixture pidfd closed then error')
        with tempfile.TemporaryDirectory() as root,patch.object(F.os,'pidfd_open',side_effect=opening),patch.object(F.os,'close',side_effect=close),self.assertRaisesRegex(OSError,'closed then error'):
            F.fixture([EXE,'-c','pass'],ENV,root)
        self.assertEqual(attempts,owned)
        for fd in owned:
            with self.assertRaises(OSError):os.fstat(fd)
    def test_actual_stdout_close_error_closes_stderr_pidfd_without_retry(self):
        with tempfile.TemporaryDirectory() as root:
            real=F.subprocess.Popen;real_pidfd=F.os.pidfd_open;processes=[];descriptors=[];attempts=[]
            def popen(*args,**kw):
                value=real(*args,**kw);processes.append(value);closing=value.stdout.close
                def close():
                    closing();attempts.append('stdout');raise OSError('actual stdout closed then error')
                value.stdout.close=close
                return value
            def opening(*args):
                fd=real_pidfd(*args);descriptors.append(fd);return fd
            with patch.object(F.subprocess,'Popen',side_effect=popen),patch.object(F.os,'pidfd_open',side_effect=opening),self.assertRaisesRegex(OSError,'stdout closed'):
                F.fixture([EXE,'-c','print("own")'],ENV,root)
            self.assertEqual(attempts,['stdout']);self.assertTrue(processes[0].stdout.closed);self.assertTrue(processes[0].stderr.closed)
            self.assertIsNotNone(processes[0].returncode)
            for fd in descriptors:
                with self.assertRaises(OSError):os.fstat(fd)
    def test_nonzero_and_timeout_reject_and_reap_only_owned_processes(self):
        for code in ['raise SystemExit(3)','import time;time.sleep(10)']:
            with self.subTest(code=code),tempfile.TemporaryDirectory() as root:
                real=F.subprocess.Popen;processes=[]
                def popen(*args,**kw):
                    value=real(*args,**kw);processes.append(value);return value
                with patch.object(F.subprocess,'Popen',side_effect=popen),self.assertRaises((RuntimeError,F.subprocess.TimeoutExpired)):
                    F.fixture([EXE,'-c',code],ENV,root)
                self.assertIsNotNone(processes[0].returncode);self.assertTrue(processes[0].stdout.closed);self.assertTrue(processes[0].stderr.closed)
                with self.assertRaises(ChildProcessError):os.waitpid(processes[0].pid,os.WNOHANG)
    def test_truncated_security_or_real_denial_refuses(self):
        class Security:
            def __init__(self,value):self.value=value
            def security(self,*args):return self.value
        for value in [dict(selinux='Permissive',avc_records=[],journal_total_bytes=1,journal_retained_bytes=1),dict(selinux='Enforcing',avc_records=['denied'],journal_total_bytes=1,journal_retained_bytes=1),dict(selinux='Enforcing',avc_records=[],journal_total_bytes=2,journal_retained_bytes=1)]:
            with self.assertRaises(RuntimeError):C.security(Security(value),Path('/tmp'),'fixture')
    def test_same_actual_regular_ELF_reads_but_hash_link_changed_bytes_fail(self):
        data=Path(EXE).read_bytes();actual=hashlib.sha256(data).hexdigest()
        if Path(EXE).stat().st_uid==0 and Path(EXE).stat().st_gid==0 and len(data)<=2097152:
            value=C.binary(EXE,actual);self.assertEqual(value['sha256'],actual)
        with self.assertRaises(RuntimeError):C.binary(EXE,'0'*64)
        with tempfile.TemporaryDirectory() as root:
            link=Path(root)/'link';link.symlink_to(EXE)
            with self.assertRaises(RuntimeError):C.binary(link,actual)
    def test_target_remains_unbound_and_no_profile_inventory_constants(self):
        self.assertIsNone(T.TARGET_ATTESTATION_SHA256)
        with self.assertRaisesRegex(RuntimeError,'UNBOUND'):T.load_bound_attestation(Path('/never-read'))
        text=(HERE/'attest-startup-v1.py').read_text()
        for name in ['source_set','profile_target_proofs','FOLLOWUP_FILES','/etc/profile','/home/liveuser/.bashrc']:
            self.assertNotIn(name,text)
        self.assertEqual(set(C.PROVIDERS),{'/usr/libexec/sddm-helper','/usr/bin/bash','/usr/bin/python3.14'})

if __name__=='__main__':unittest.main(verbosity=2)
