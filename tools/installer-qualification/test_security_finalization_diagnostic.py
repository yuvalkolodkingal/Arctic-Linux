"""Exact unchanged Native function counterfactuals, not VM evidence."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
G=load('security_diagnostic_exact_guest',HERE/'guest.py')
N=load('security_diagnostic_unchanged_native',HERE.parent/'native-functional/native_smoke.py')
R=load('security_diagnostic_exact_runner',HERE/'runner.py')
S=load('security_diagnostic_unchanged_screen',HERE.parent/'native-functional/screen-evidence.py')
STATE={'selinux':'Enforcing','audit':{'enabled':0,'lost':0}}


class SecurityFinalizationDiagnostic(unittest.TestCase):
    def raised(self,fn):
        try:fn()
        except BaseException as error:return error
        self.fail('The unchanged Native guard did not reject')

    def test_actual_private_avc_guard_projects_only_closed_ids(self):
        private='audit: avc: denied { read } for pid=199 comm="rsync" name="/mnt" tclass=dir private=PRIVATE_AVC_SENTINEL'
        error=self.raised(lambda:N.verify_security(STATE,STATE,private))
        row=G.security_finalization_diagnostic(error,N)
        self.assertEqual(row['guard'],'guard-008');self.assertEqual(row['step'],'verify-security');self.assertEqual(row['avc_count'],1)
        self.assertEqual(row['avc_subject'],'rsync');self.assertEqual(row['avc_object'],'dir');self.assertEqual(row['avc_path'],'target-root');self.assertEqual(row['avc_permission'],'read')
        mask=G.masked_security_finalization_error(error,N);self.assertNotIn('PRIVATE_AVC_SENTINEL',mask);self.assertNotIn('199',mask)
        self.assertEqual(S.external_text(mask.encode()),mask.encode())
        codes=R.primary_reported_codes({'errors':[mask]},True)
        self.assertIn('installer-reported-active-primary-security-guard-guard-008',codes)
        self.assertIn('installer-reported-active-primary-security-avc-count-1',codes)

    def test_actual_security_acceptance_guards_remain_unchanged(self):
        for after,guard in [({'selinux':'Permissive','audit':{'enabled':0,'lost':0}},'guard-005'),
                            ({'selinux':'Enforcing','audit':{'enabled':1,'lost':0}},'guard-006'),
                            ({'selinux':'Enforcing','audit':{'enabled':0,'lost':1}},'guard-007')]:
            error=self.raised(lambda:N.verify_security(STATE,after,''));self.assertEqual(G.security_finalization_diagnostic(error,N)['guard'],guard)
        self.assertEqual(N.verify_security(STATE,STATE,'')['observed_new_avcs'],0)

    def interval(self,path):
        interval=N.SecurityInterval.__new__(N.SecurityInterval);interval.before=STATE;interval.cursor='PRIVATE_CURSOR_SENTINEL';interval.audit_offset=None;interval.audit_file=path
        return interval

    def response(self,argv,code=0,out=b'',err=b''):
        if argv==['getenforce']:return subprocess.CompletedProcess(argv,0,b'Enforcing\n',b'')
        if argv==['auditctl','-s']:return subprocess.CompletedProcess(argv,0,b'enabled 0\nlost 0\n',b'')
        return subprocess.CompletedProcess(argv,code,out,err)

    def test_actual_full_finish_command_bound_and_exit_guard_source(self):
        with tempfile.TemporaryDirectory() as temp:
            interval=self.interval(Path(temp)/'absent-audit')
            for out,code,guard in [(b'x'*(N.LIMIT+1),0,'guard-001'),(b'',7,'guard-002')]:
                with mock.patch.object(N.subprocess,'run',side_effect=lambda argv,**kwargs:self.response(argv,code,out,b'PRIVATE_STDERR_SENTINEL')):
                    error=self.raised(interval.finish)
                row=G.security_finalization_diagnostic(error,N)
                self.assertEqual(row['guard'],guard);self.assertEqual(row['command'],'journal-interval');self.assertEqual(row['exit_code'],code)
                self.assertEqual(row['stdout_bytes'],len(out));self.assertEqual(row['stderr_bytes'],len(b'PRIVATE_STDERR_SENTINEL'))
                mask=G.masked_security_finalization_error(error,N);self.assertNotIn('PRIVATE_',mask);self.assertNotIn('journalctl',mask)
                self.assertIn('installer-reported-active-primary-security-command-journal-interval',R.primary_reported_codes({'errors':[mask]},True))

    def test_actual_full_finish_timeout_no_made_up_exit(self):
        with tempfile.TemporaryDirectory() as temp:
            interval=self.interval(Path(temp)/'absent-audit');primary=subprocess.TimeoutExpired(['PRIVATE_ARG'],60,output=b'PRIVATE_OUTPUT')
            def run(argv,**kwargs):
                if argv[0]=='journalctl':raise primary
                return self.response(argv)
            with mock.patch.object(N.subprocess,'run',side_effect=run):error=self.raised(interval.finish)
            self.assertIs(error,primary);row=G.security_finalization_diagnostic(error,N)
            self.assertEqual(row['error_class'],'timeout');self.assertEqual(row['step'],'journal-query');self.assertEqual(row['command'],'journal-interval')
            self.assertIsNone(row['exit_code']);self.assertIsNone(row['stdout_bytes']);self.assertEqual(row['guard'],'unknown')

    def test_actual_audit_file_identity_and_status_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'audit';path.write_bytes(b'');interval=self.interval(path);st=path.stat();interval.audit_offset=(st.st_dev,st.st_ino+1,0)
            with mock.patch.object(N.subprocess,'run',side_effect=lambda argv,**kwargs:self.response(argv)):error=self.raised(interval.finish)
            self.assertEqual(G.security_finalization_diagnostic(error,N)['guard'],'guard-009')
        for data,guard in [('lost 0\n','guard-003'),('enabled 0\n','guard-004')]:
            error=self.raised(lambda:N.parse_audit_status(data));self.assertEqual(G.security_finalization_diagnostic(error,N)['guard'],guard)

    def test_foreign_literal_subclass_and_traceback_never_mint_guard(self):
        for error in [RuntimeError('new AVC requires investigation: PRIVATE'),type('Hostile',(RuntimeError,),{'__str__':lambda self:(_ for _ in ()).throw(AssertionError('must not format'))})('PRIVATE')]:
            error=self.raised(lambda:(_ for _ in ()).throw(error));row=G.security_finalization_diagnostic(error,N)
            self.assertEqual(row['guard'],'unknown');self.assertIsNone(row['avc_count']);self.assertNotIn('PRIVATE',json.dumps(row))
        with mock.patch.object(N,'require',side_effect=RuntimeError('new AVC requires investigation: PRIVATE')):
            error=self.raised(lambda:N.verify_security(STATE,STATE,'avc: denied { read } for comm="rsync"'))
        self.assertEqual(G.security_finalization_diagnostic(error,N)['guard'],'unknown')

    def test_forged_embedded_and_duplicate_avc_fields_stay_unknown(self):
        for text in ['avc: denied { read } for comm="PRIVATE comm=rsync" tclass="PRIVATE tclass=dir" name="PRIVATE name=/mnt"',
                     'avc: denied { read write } for comm="rsync" comm="systemd" tclass=dir tclass=file name="/mnt" name="/etc/selinux"']:
            error=self.raised(lambda:N.verify_security(STATE,STATE,text));row=G.security_finalization_diagnostic(error,N)
            self.assertEqual(row['guard'],'guard-008');self.assertEqual(row['avc_subject'],'unknown');self.assertEqual(row['avc_object'],'unknown');self.assertEqual(row['avc_path'],'unknown')
        self.assertEqual(row['avc_permission'],'unknown')

    def test_whole_primary_consumer_rejects_forged_and_out_of_bound_labels(self):
        error=self.raised(lambda:N.verify_security(STATE,STATE,'avc: denied { read } for comm="rsync"'));mask=G.masked_security_finalization_error(error,N)
        self.assertIsNotNone(R.security_reported_codes(mask))
        mutants=[mask.replace('guard-008','guard-999'),mask.replace('class=runtime-error','class=private'),mask.replace('exit=none','exit=99999'),
            mask.replace('out=none','out=67108865'),mask.replace('avcs=1','avcs=1048577'),mask.replace('subject=rsync','subject=private'),mask+' PRIVATE_EXTRA']
        for value in mutants:
            self.assertIsNone(R.security_reported_codes(value));self.assertEqual(R.primary_reported_codes({'errors':[value]},True),('installer-reported-active-primary-unknown',))
        self.assertIn('installer-reported-active-primary-security-finalization-failed',R.primary_reported_codes({'errors':['active security interval failed']},True))


if __name__=='__main__':unittest.main(verbosity=2)
