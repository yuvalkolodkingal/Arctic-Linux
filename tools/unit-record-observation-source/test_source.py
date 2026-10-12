"""Current optional member/record diagnostic Source controls; synthetic records only."""
import ast
import contextlib
import io
import json
from pathlib import Path
import signal
import os
import sys
import types
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]

def load(raw,path,name):
    module=types.ModuleType(name);module.__file__=str(path)
    exec(compile(raw,str(path),'exec',dont_inherit=True,optimize=0),module.__dict__)
    return module

class SourceControls(unittest.TestCase):
    def setUp(self):
        self.obs_raw=(HERE/'observer.py').read_bytes()
        self.obs=load(self.obs_raw,HERE/'observer.py','current_unit_record_observer')
        self.diag_raw=(HERE/'diagnostic.py').read_bytes()
        self.diag=load(self.diag_raw,HERE/'diagnostic.py','unit_record_diagnostic')
        self.helper_path=ROOT/'tools/final-bios-dnf-uid-observation-source/match-diagnostic.py'
        self.helper_raw=self.helper_path.read_bytes()
        self.helper=load(self.helper_raw,self.helper_path,'current_public_shape_helper')
        self.sc_path=ROOT/'tools/bounded-complete-csi-source/scanner.py'
        self.sc_raw=self.sc_path.read_bytes();self.sc=load(self.sc_raw,self.sc_path,'unchanged_scanner')
        self.c_path=ROOT/'tools/final-bios-install/common.py'
        self.c_raw=self.c_path.read_bytes();self.c=load(self.c_raw,self.c_path,'original_common')
        self.run_path=ROOT/'tools/final-bios-install/run.py'
        self.run_raw=self.run_path.read_bytes()
        saved={name:(name in sys.modules,sys.modules.get(name))for name in ('common','compose')}
        try:
            sys.modules['common']=self.c
            path=ROOT/'tools/final-bios-install/compose.py'
            sys.modules['compose']=load(path.read_bytes(),path,'original_compose')
            self.run=load(self.run_raw,self.run_path,'original_run')
        finally:
            for name,(present,value)in saved.items():
                if present:sys.modules[name]=value
                else:sys.modules.pop(name,None)
        O=self.obs.OwnedSource
        self.run_owner=O(self.run.__dict__,self.run_raw,str(self.run_path),'bios-host')
        self.c_owner=O(self.c.__dict__,self.c_raw,str(self.c_path),'bios-common')
        self.sc_owner=O(self.sc.__dict__,self.sc_raw,str(self.sc_path),'original-scanner')
        self.helper_owner=O(self.helper.__dict__,self.helper_raw,str(self.helper_path),'match-diagnostic')
        self.diag_owner=O(self.diag.__dict__,self.diag_raw,str(HERE/'diagnostic.py'),'unit-record')
        self.obs_owner=O(self.obs.__dict__,self.obs_raw,str(HERE/'observer.py'),'configured-observer')
        self.scanners=[(self.sc,self.sc_owner)]
        attributes=(self.diag.re.Match,self.diag.types.ModuleType,self.diag.XDG_AUTOSTART,
            self.diag.UNIT_FAMILY_IDS,self.diag.SOURCE_MEMBER_IDS,self.diag.RECORD_FAMILY_IDS,
            self.diag.JOB_PREFIX,self.diag.KERNEL_PREFIX,self.diag.DESCRIPTION,self.diag.STATES)
        self.binding=(self.diag,self.diag_owner,self.diag.diagnostic_unit_record_family,attributes,
            self.obs_owner,self.helper,self.helper_owner,self.scanners,self.c_owner,(self.run_owner,),
            (self.obs.unit_record_observation,self.obs.unit_record_observation.__code__,self.obs.__dict__))
        self.vocabulary=frozenset({node.value for node in ast.walk(ast.parse(self.helper_raw))
            if isinstance(node,ast.Constant)and type(node.value)is str}|{'external-rule-'+format(n,'03d')for n in range(1,11)})
        self.unit='app-org.arctic.Settings@autostart.service'

    def caught(self,raw,*,enabled=True,stage='live'):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            try:self.run.records(raw,{},stage,'a'*64,self.sc)
            except RuntimeError as error:
                original=(error,error.__traceback__)
                result=self.obs.describe(error,(self.run_owner,),self.c_owner,self.scanners,self.helper,
                    self.helper_owner,self.vocabulary,(self.c,),self.binding if enabled else None)
                self.assertIs(error,original[0]);self.assertIs(error.__traceback__,original[1])
                return result,error
        self.fail('Original scanner admitted synthetic private-shaped record')

    def row(self,text,**kwargs):
        result,error=self.caught((text+'\n').encode(),**kwargs)
        return result['same_rejected_match']['unit_record_family'],result,error

    def test_same_reject_frame_all_closed_record_families_and_members(self):
        cases={
          'systemd-kernel-lifecycle':f'[    1.234] systemd[1]: Started {self.unit} - Arctic settings entry.',
          'systemd-job-lifecycle':f'[  OK  ] Started {self.unit} - Arctic settings entry.',
          'systemd-kernel-deactivated':f'[ 22.5] systemd[1]: {self.unit}: Deactivated successfully.',
          'systemd-install-masked':f'Unit {self.unit} is masked, ignoring.',
          'systemctl-user-failed-row':f'● {self.unit} loaded failed failed Arctic settings entry',
        }
        for identifier,text in cases.items():
            with self.subTest(identifier=identifier):
                row,result,error=self.row(text)
                self.assertEqual(row['source_member_id'],'serial-install-log')
                self.assertEqual(row['unit_family_id'],'repo-xdg-autostart-unit')
                self.assertEqual(row['record_family_id'],identifier)
                self.assertIs(row['exact_repo_attested_unit_family'],True)
                self.assertIs(row['exact_repo_attested_record_family'],True)
                for key in ('privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported','release_acceptance'):
                    self.assertIs(row[key],False)
                encoded=json.dumps(result)
                self.assertNotIn(self.unit,encoded);self.assertNotIn('Arctic settings entry',encoded)
                self.assertIs(type(error),RuntimeError)
        row,_,_=self.row(f'Started {self.unit} - no attested wrapper.',stage='installed')
        self.assertEqual(row['source_member_id'],'serial-boot-log')
        self.assertEqual(row['unit_family_id'],'repo-xdg-autostart-unit')
        self.assertEqual(row['record_family_id'],'unknown')
        self.assertIs(row['exact_repo_attested_record_family'],False)

    def test_default_off_unknown_family_bound_and_no_value_digest_or_length(self):
        raw=(self.unit+'\n').encode()
        result,error=self.caught(raw,enabled=False)
        self.assertNotIn('unit_record_family',result['same_rejected_match'])
        row,result,error=self.row('private@example.invalid')
        self.assertEqual(row['source_member_id'],'serial-install-log')
        self.assertEqual(row['unit_family_id'],'unknown')
        self.assertEqual(row['record_family_id'],'unknown')
        self.assertFalse(row['exact_repo_attested_unit_family'])
        encoded=json.dumps(result)
        self.assertNotIn('private@example.invalid',encoded)
        self.assertNotIn('operand_value',row);self.assertNotIn('operand_digest',row)
        self.assertNotIn('operand_length',row)
        long='X'*4097
        row,_,_=self.row(long+' '+self.unit)
        self.assertEqual(row['unit_family_id'],'repo-xdg-autostart-unit')
        self.assertEqual(row['record_family_id'],'unknown')

    def test_exact_family_grammar_rejects_near_matches_and_ambiguous_context(self):
        values=(
          f'app-@autostart.service',
          f'app-private@example.invalid',
          f'app-org.arctic.Settings@other.service',
          f'prefix-{self.unit}',
          f'{self.unit}.private',
        )
        for value in values:
            with self.subTest(value=value):
                row,_,_=self.row(value)
                self.assertEqual(row['unit_family_id'],'unknown')
        wrappers=(
          f'[  OK  ] Started {self.unit} - Control\x01byte.',
          f'[  OK  ] Started {self.unit} - '+('x'*513)+'.',
          f'[  OK  ] Starting {self.unit} - entry.',
          f'[    1.0] systemd[2]: Started {self.unit} - entry.',
          f'Unit {self.unit} is masked, ignoring!',
          f"Removed '/etc/systemd/user/{self.unit}.d/arctic.conf'.",
          f'{self.unit} loaded failed unknown entry',
        )
        for text in wrappers:
            with self.subTest(text=text[:80]):
                row,_,_=self.row(text)
                self.assertEqual(row['record_family_id'],'unknown')

    def test_code_global_and_module_mutation_withhold_optional_only(self):
        raw=(f'[  OK  ] Started {self.unit} - Arctic settings entry.\n').encode()
        function=self.diag.diagnostic_unit_record_family;code=function.__code__
        function.__code__=code.replace()
        self.assertNotIn('unit_record_family',self.caught(raw)[0]['same_rejected_match'])
        function.__code__=code
        self.diag.diagnostic_unit_record_family=types.FunctionType(code,self.diag.__dict__.copy())
        self.assertNotIn('unit_record_family',self.caught(raw)[0]['same_rejected_match'])
        self.diag.diagnostic_unit_record_family=function
        self.obs.zip=lambda *args:()
        self.assertNotIn('unit_record_family',self.caught(raw)[0]['same_rejected_match'])
        del self.obs.zip
        families=self.diag.RECORD_FAMILY_IDS;self.diag.RECORD_FAMILY_IDS=tuple(list(families))
        self.assertNotIn('unit_record_family',self.caught(raw)[0]['same_rejected_match'])
        self.diag.RECORD_FAMILY_IDS=families
        self.assertEqual(self.caught(raw)[0]['same_rejected_match']['unit_record_family']['record_family_id'],
            'systemd-job-lifecycle')

    def test_unowned_callsite_and_foreign_owner_never_invoke_diagnostic(self):
        raw=(self.unit+'\n').encode()
        try:self.sc.external_text(raw)
        except RuntimeError as error:
            frame=error.__traceback__
            while frame.tb_next is not None:frame=frame.tb_next
            self.assertIsNone(self.obs.unit_record_observation(self.binding,self.sc,self.sc_owner,frame.tb_frame,error))
        finally:
            if 'frame'in locals():del frame
        wrong=(*self.binding[:7],[(self.sc,object())],*self.binding[8:])
        held=self.binding;self.binding=wrong
        self.assertNotIn('unit_record_family',self.caught(raw)[0]['same_rejected_match'])
        self.binding=held

    def test_attach_typed_enable_sigint_and_original_main_code(self):
        arguments=(self.run.main,self.run_raw,self.c_raw,self.sc_raw,self.helper_raw,self.helper_path)
        observed,state=self.obs.attach(*arguments)
        self.assertIs(observed.__code__,self.run.main.__code__);self.assertIsNone(state['finite'])
        for alias in (1,'true'):
            with self.assertRaises(ValueError):self.obs.attach(*arguments,configured_enabled=alias)
        options={'configured_enabled':True,'configured_raw':self.diag_raw,'configured_path':HERE/'diagnostic.py',
            'configured_observer_raw':self.obs_raw}
        observed,state=self.obs.attach(*arguments,**options)
        self.assertIs(observed.__code__,self.run.main.__code__)
        target=self.obs.attach.__code__;sent=False;previous=sys.gettrace()
        def trace(frame,event,arg):
            nonlocal sent
            if frame.f_code is target and event=='line'and not sent:
                sent=True;os.kill(os.getpid(),signal.SIGINT)
            return trace
        try:
            sys.settrace(trace)
            with self.assertRaises(KeyboardInterrupt):self.obs.attach(*arguments,**options)
        finally:sys.settrace(previous)
        self.assertTrue(sent)

    def test_optional_fault_and_late_hook_replacement_keep_original_primary(self):
        raw=(self.unit+'\n').encode()
        target=self.obs.unit_record_observation.__code__
        previous=sys.getprofile();fired=False;fault=ValueError('owned Source fixture fault')
        def profile(frame,event,arg):
            nonlocal fired
            if frame.f_code is target and event=='call'and not fired:
                fired=True;raise fault
        try:
            sys.setprofile(profile);result,error=self.caught(raw)
        finally:sys.setprofile(previous)
        self.assertTrue(fired);self.assertIs(type(error),RuntimeError)
        self.assertNotIn('unit_record_family',result['same_rejected_match'])
        hook=self.obs.unit_record_observation;original=hook.__code__
        helper_code=self.helper.diagnostic_known_public_Fedora44_UID_DNF_line.__code__
        def counterfeit(*args):
            return {'schema':'arctic-unit-record-family-source-diagnostic-v1',
                'source_member_id':'serial-install-log','unit_family_id':'repo-xdg-autostart-unit',
                'record_family_id':'systemd-job-lifecycle','exact_repo_attested_unit_family':True,
                'exact_repo_attested_record_family':True,'privacy_admitted':False,
                'runtime_cause_proven':False,'operand_value_or_digest_exported':False,'release_acceptance':False}
        for trigger in (helper_code,original):
            previous=sys.getprofile();fired=False
            def replace(frame,event,arg):
                nonlocal fired
                if frame.f_code is trigger and event=='return'and not fired:
                    fired=True;hook.__code__=counterfeit.__code__
            try:
                sys.setprofile(replace);result,error=self.caught(raw)
            finally:sys.setprofile(previous);hook.__code__=original
            self.assertTrue(fired);self.assertNotIn('unit_record_family',result['same_rejected_match'])
            self.assertIs(type(error),RuntimeError)
        self.assertEqual(self.caught(raw)[0]['same_rejected_match']['unit_record_family']['unit_family_id'],
            'repo-xdg-autostart-unit')

    def test_source_manifest_exact_files_and_closed_security_contract(self):
        manifest=json.loads((HERE/'source-manifest.json').read_text())
        self.assertEqual(manifest['schema'],'arctic-bios-unit-record-family-disabled-Source-v1')
        self.assertIs(manifest['ready'],False);self.assertIs(manifest['release_acceptance'],False)
        expected={}
        for name in ('README.md','diagnostic.py','observer.py','test_source.py'):
            expected['tools/unit-record-observation-source/'+name]=__import__('hashlib').sha256((HERE/name).read_bytes()).hexdigest()
        self.assertEqual(manifest['files'],expected)
        binding=manifest['binding']
        self.assertEqual(binding['record_family_id_count'],5)
        self.assertEqual(binding['unit_family_id_count'],1)
        self.assertEqual(binding['source_member_id_count'],2)
        self.assertEqual(binding['diagnostic_sha256'],expected['tools/unit-record-observation-source/diagnostic.py'])
        self.assertEqual(binding['selected_observer_sha256'],expected['tools/unit-record-observation-source/observer.py'])
        for key in ('private_operand_exported','private_operand_digest_exported','private_operand_length_exported',
                    'private_numeric_field_exported','private_excerpt_exported','scanner_changed',
                    'privacy_admission_changed','runtime_cause_proven','release_acceptance'):
            self.assertIs(binding[key],False)
        self.assertIs(binding['same_owned_rejection_only'],True)


if __name__=='__main__':unittest.main(verbosity=2)
