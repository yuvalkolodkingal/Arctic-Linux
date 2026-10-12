"""Current optional diagnostic Source controls; all records are synthetic."""
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
        self.obs=load(self.obs_raw,HERE/'observer.py','current_configured_observer')
        self.diag_raw=(HERE/'diagnostic.py').read_bytes()
        self.diag=load(self.diag_raw,HERE/'diagnostic.py','broker_shape_diagnostic')
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
        self.diag_owner=O(self.diag.__dict__,self.diag_raw,str(HERE/'diagnostic.py'),'broker-shape')
        self.obs_owner=O(self.obs.__dict__,self.obs_raw,str(HERE/'observer.py'),'configured-observer')
        self.scanners=[(self.sc,self.sc_owner)]
        self.binding=(self.diag,self.diag_owner,self.diag.diagnostic_broker_factory_shape,
            (self.diag.re.Match,self.diag.types.ModuleType,self.diag.FACTORY,self.diag.TARGETS),
            self.obs_owner,self.helper,self.helper_owner,self.scanners,self.c_owner,(self.run_owner,),
            (self.obs.broker_factory_observation,self.obs.broker_factory_observation.__code__,self.obs.__dict__))
        self.vocabulary=frozenset({node.value for node in ast.walk(ast.parse(self.helper_raw))
            if isinstance(node,ast.Constant)and type(node.value)is str}|{'external-rule-'+format(n,'03d')for n in range(1,11)})

    def caught(self,raw,*,enabled=True):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            try:self.run.records(raw,{},'live','a'*64,self.sc)
            except RuntimeError as error:
                original=(error,error.__traceback__)
                result=self.obs.describe(error,(self.run_owner,),self.c_owner,self.scanners,self.helper,
                    self.helper_owner,self.vocabulary,(self.c,),self.binding if enabled else None)
                self.assertIs(error,original[0]);self.assertIs(error.__traceback__,original[1])
                return result,error
        self.fail('Original scanner admitted synthetic private-shaped record')

    def test_actual_same_reject_frame_known_unknown_and_defaultoff(self):
        for name,target in self.diag.TARGETS:
            raw=(' dbus-:1.42-'+name+'@73.service\n').encode()
            result,error=self.caught(raw)
            row=result['same_rejected_match']['broker_factory_shape']
            self.assertEqual(row['target_id'],target);self.assertIs(row['exact_broker_factory_shape'],True)
            for key in ('privacy_admitted','runtime_cause_proven','operand_value_or_digest_exported'):
                self.assertIs(row[key],False)
            self.assertNotIn(name,json.dumps(result));self.assertNotIn('1.42',json.dumps(result))
            self.assertNotIn('broker_factory_shape',self.caught(raw,enabled=False)[0]['same_rejected_match'])
        result,error=self.caught(b' dbus-:1.42-private.example@73.service\n')
        self.assertEqual(result['same_rejected_match']['broker_factory_shape']['target_id'],'unknown')
        self.assertIs(result['same_rejected_match']['broker_factory_shape']['exact_broker_factory_shape'],True)

    def test_code_global_absent_cell_and_module_attributes_withhold_optional_only(self):
        raw=b' dbus-:1.42-org.a11y.Bus@73.service\n'
        function=self.diag.diagnostic_broker_factory_shape;code=function.__code__
        function.__code__=code.replace()
        self.assertNotIn('broker_factory_shape',self.caught(raw)[0]['same_rejected_match'])
        function.__code__=code
        self.diag.diagnostic_broker_factory_shape=types.FunctionType(code,self.diag.__dict__.copy())
        self.assertNotIn('broker_factory_shape',self.caught(raw)[0]['same_rejected_match'])
        self.diag.diagnostic_broker_factory_shape=function
        self.obs.zip=lambda *args:()
        self.assertNotIn('broker_factory_shape',self.caught(raw)[0]['same_rejected_match'])
        del self.obs.zip
        targets=self.diag.TARGETS;self.diag.TARGETS=tuple(list(targets))
        self.assertNotIn('broker_factory_shape',self.caught(raw)[0]['same_rejected_match'])
        self.diag.TARGETS=targets
        self.assertEqual(self.caught(raw)[0]['same_rejected_match']['broker_factory_shape']['target_id'],
            'broker-source-target-002')

    def test_unowned_callsite_and_foreign_owner_never_invoke_diagnostic(self):
        raw=b' dbus-:1.42-org.a11y.Bus@73.service\n'
        try:self.sc.external_text(raw)
        except RuntimeError as error:
            frame=error.__traceback__
            while frame.tb_next is not None:frame=frame.tb_next
            self.assertIsNone(self.obs.broker_factory_observation(self.binding,self.sc,
                self.sc_owner,frame.tb_frame,error))
        finally:
            if 'frame'in locals():del frame
        wrong=(*self.binding[:7],[(self.sc,object())],*self.binding[8:])
        held=self.binding;self.binding=wrong
        self.assertNotIn('broker_factory_shape',self.caught(raw)[0]['same_rejected_match'])
        self.binding=held

    def test_attach_typed_enable_ordinary_sigint_and_original_main_code(self):
        arguments=(self.run.main,self.run_raw,self.c_raw,self.sc_raw,self.helper_raw,self.helper_path)
        observed,state=self.obs.attach(*arguments)
        self.assertIs(observed.__code__,self.run.main.__code__)
        self.assertIsNone(state['finite'])
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

    def test_optional_actual_function_fault_keeps_original_finite_primary(self):
        target=self.obs.broker_factory_observation.__code__
        previous=sys.getprofile();fired=False;fault=ValueError('owned Source fixture fault')
        def profile(frame,event,arg):
            nonlocal fired
            if frame.f_code is target and event=='call'and not fired:
                fired=True;raise fault
        try:
            sys.setprofile(profile)
            result,error=self.caught(b' dbus-:1.42-org.a11y.Bus@73.service\n')
        finally:sys.setprofile(previous)
        self.assertTrue(fired)
        self.assertIs(type(error),RuntimeError)
        self.assertNotIn('broker_factory_shape',result['same_rejected_match'])
        self.assertIs(result['same_rejected_match']['privacy_admitted'],False)

    def test_late_hook_code_replacement_before_and_after_dispatch_denies_field(self):
        hook=self.obs.broker_factory_observation;original=hook.__code__
        helper_code=self.helper.diagnostic_known_public_Fedora44_UID_DNF_line.__code__
        def counterfeit(*args):
            return {'schema':'arctic-broker-factory-shape-source-diagnostic-v1',
                'target_id':'broker-source-target-003','exact_broker_factory_shape':True,
                'privacy_admitted':False,'runtime_cause_proven':False,'operand_value_or_digest_exported':False,
                'release_acceptance':False}
        for trigger in (helper_code,original):
            previous=sys.getprofile();fired=False
            def profile(frame,event,arg):
                nonlocal fired
                if frame.f_code is trigger and event=='return'and not fired:
                    fired=True;hook.__code__=counterfeit.__code__
            try:
                sys.setprofile(profile)
                result,error=self.caught(b' dbus-:1.42-org.a11y.Bus@73.service\n')
            finally:
                sys.setprofile(previous);hook.__code__=original
            self.assertTrue(fired)
            self.assertNotIn('broker_factory_shape',result['same_rejected_match'])
            self.assertIs(type(error),RuntimeError)
        self.assertEqual(self.caught(b' dbus-:1.42-org.a11y.Bus@73.service\n')[0]
            ['same_rejected_match']['broker_factory_shape']['target_id'],'broker-source-target-002')


if __name__=='__main__':unittest.main(verbosity=2)
