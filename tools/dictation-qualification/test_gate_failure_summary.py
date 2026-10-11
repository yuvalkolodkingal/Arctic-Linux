"""Actual loaded validator throw and closed report-scalar observation controls.

Synthetic schema fixtures exercise real helper code, not dictation/VM outcomes.
"""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
BASE='b49438e2b681fa04e97887cf1342f2f1a5443735'
CONTRACT_SHA256='1ab44f66d744939d4bd7d6b7034f4c2beac738168d1ae34c2572a1f95a0da3cf'
GUEST_ADDON_SHA256='f13464b87929b242ef648cd9144766a06aaa472c22987f9a711da9ffa21765b1'
CALLER_ADDON_SHA256='b4f21508e7e3094f8eb00f514dee4b907f77340311fb7d942802cc5cbdd02f8c'
BINDING_ADDON_SHA256='7ae8d158a63bdf22e285298a77e08943c9ba1ea5d62bc2b97a43ae2d4585d17e'
RUNNER_ADDON_SHA256='11234d046791eabd3759ecec874dcc80db190edd2969c469b300637f123dbab1'

def remove_block(text,begin,end,digest):
    if begin not in text:return text
    assert text.count(begin)==text.count(end)==1
    first=text.index(begin);last=text.index(end,first)+len(end)
    assert hashlib.sha256(text[first:last].encode()).hexdigest()==digest
    return text[:first]+text[last:]

def restore_gate_failure_summary(text):
    if '# BEGIN OWNED_GATE_FAILURE_SUMMARY\n' not in text:return text
    text=remove_block(text,'# BEGIN OWNED_GATE_FAILURE_SUMMARY\n','# END OWNED_GATE_FAILURE_SUMMARY\n\n',GUEST_ADDON_SHA256)
    text=remove_block(text,'# BEGIN OWNED_GATE_FAILURE_BINDING\n','# END OWNED_GATE_FAILURE_BINDING\n\n',BINDING_ADDON_SHA256)
    text=remove_block(text,'            # BEGIN TRANSPARENT_GATE_SUMMARY_CALLER\n','            # END TRANSPARENT_GATE_SUMMARY_CALLER\n',CALLER_ADDON_SHA256)
    before="    validate_collected_report(checker, report, declared, DATA / 'dictation-fixtures/fixtures.json')\n"
    after="    validate(report, declared, fixture_manifest=DATA / 'dictation-fixtures/fixtures.json')\n"
    assert text.count(before)==1
    text=text.replace(before,after,1)
    assert hashlib.sha256(text.encode()).hexdigest()=='74fa64287f4420137f90a2b99a10b94efa8759af5efc7627b74dce7969ea2f76'
    return text

def restore_gate_failure_relay(text):
    if '# BEGIN GATE_FAILURE_SUMMARY_RELAY\n' not in text:return text
    text=remove_block(text,'# BEGIN GATE_FAILURE_SUMMARY_RELAY\n','# END GATE_FAILURE_SUMMARY_RELAY\n\n',RUNNER_ADDON_SHA256)
    before='    relay_gate_failures(vm, phase)\n'
    assert text.count(before)==1
    text=text.replace(before,'',1)
    assert hashlib.sha256(text.encode()).hexdigest()=='11a01d8b2bc67609a4b19436f40e26e0fc5b686ddc61b6514f6d2ce23b4217a5'
    return text

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
import contract as c
import test_contract as fixtures
g=load('actual_gate_failure_guest','guest_check.py')
r=load('actual_gate_failure_runner','runner.py')

def checker_for(report):
    checker=object.__new__(g.Checker)
    checker.report=report;checker.context=report['context'];checker.profile_id=report['context']['hardware_profile']
    checker.gates=set(c.gates(checker.context['phase'],checker.profile_id))
    return checker

def invoke(report,checker=None,function=None):
    checker=checker or checker_for(report)
    output=io.StringIO();error=None
    with contextlib.redirect_stdout(output):
        try:(function or g.validate_collected_report)(checker,report,report['context'],fixtures.FIXTURES)
        except c.Invalid as caught:error=caught
    rows=[json.loads(line.split(' ',1)[1]) for line in output.getvalue().splitlines()
          if line.startswith('ARCTIC-DICTATION-GATE-SUMMARY ')]
    return rows,error,output.getvalue()

class GateFailureSummary(unittest.TestCase):
    def failure(self,profile='turbo-q5-v3',phase='online-installed'):
        report=fixtures.synthetic(phase,profile=profile)
        if phase=='live':report['controller_sha256']='a'*64
        else:
            leak=next(row for row in report['gates'] if row['id']=='transcript-log-notification-leak-scan')
            leak['observations']['count']=1
        return report
    def test_whole_inverse_contract_and_all61_original_predicates_unchanged(self):
        for file,restore in (('guest_check.py',restore_gate_failure_summary),('runner.py',restore_gate_failure_relay)):
            actual=HERE.joinpath(file).read_text();base=subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':tools/dictation-qualification/'+file]).decode()
            self.assertEqual(restore(actual),base);self.assertEqual(ast.dump(ast.parse(restore(actual))),ast.dump(ast.parse(base)))
            with self.assertRaises(AssertionError):restore(actual.replace('release_acceptance=False','release_acceptance=True',1) if file=='guest_check.py' else actual.replace("value['release_acceptance'] is not False","value['release_acceptance'] is not True",1))
        self.assertEqual(hashlib.sha256(HERE.joinpath('contract.py').read_bytes()).hexdigest(),CONTRACT_SHA256)
        function=next(node for node in ast.parse(HERE.joinpath('contract.py').read_text()).body if isinstance(node,ast.FunctionDef) and node.name=='validate')
        self.assertEqual(len([node for node in ast.walk(function) if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='require']),61)
    def test_genuine_coverage_failure_projects_complete_cpu_gpu_and_other_gate_scalars(self):
        for profile,phase in (('small-v2','online-installed'),('turbo-q5-v3','online-installed'),('small-v2','recovered-offline'),('turbo-q5-v3','live')):
            report=self.failure(profile,phase)
            if phase!='live':
                for name in ('cpu-english-transcription-insertion','gpu-runtime-failure-cpu-retry'):
                    for row in report['gates']:
                        if row['id']==name:row.update(status='failed',code='command-failed',observations={})
            rows,error,text=invoke(report)
            self.assertIs(type(error),c.Invalid);self.assertEqual(len(rows),1)
            value=rows[0];self.assertEqual([row['id'] for row in value['gates']],sorted(c.gates(phase,profile)))
            self.assertIs(value['release_acceptance'],False);self.assertEqual(r.gate_failure_record(json.dumps(value).encode()),value)
            self.assertNotIn('observations',text);self.assertNotIn('count',text);self.assertNotIn('sha256',text)
            if phase!='live':self.assertEqual(next(row for row in value['gates'] if row['id']=='cpu-english-transcription-insertion')['status'],'failed')
    def test_private_operands_unknown_code_and_unknown_fields_never_export(self):
        report=self.failure();report['gates'][0]['code']='private Hebrew English transcript'
        rows,error,text=invoke(report);self.assertIsNotNone(error);self.assertEqual(rows[0]['gates'][0]['code'],'unknown');self.assertNotIn('private Hebrew English transcript',text)
        for mutate in (lambda report:report.update(private='private transcript'),lambda report:report['gates'][0].update(private='private transcript'),lambda report:report['gates'][0]['observations'].update(private='private transcript'),lambda report:report['gates'][0].update(status=True),lambda report:report['gates'][0].update(evidence_kind='private kind')):
            report=self.failure();mutate(report);rows,error,text=invoke(report);self.assertIsNotNone(error);self.assertEqual(rows,[]);self.assertEqual(text,'')
    def test_wrong_globals_lookalike_and_changed_loaded_functions_deny(self):
        report=self.failure();namespace=dict(g.__dict__)
        clone=types.FunctionType(g.validate_collected_report.__code__,namespace)
        rows,error,_=invoke(report,function=clone);self.assertIsNotNone(error);self.assertEqual(rows,[])
        namespace=dict(g.__dict__)
        exec(compile('def lookalike(checker, report, declared, fixture_manifest):\n try:validate(report,declared,fixture_manifest=fixture_manifest)\n except Invalid as error:\n  emit_gate_failure_summary(error,checker,report,declared)\n  raise\n','<source-looking foreign code>','exec'),namespace)
        rows,error,_=invoke(report,function=namespace['lookalike']);self.assertIsNotNone(error);self.assertEqual(rows,[])
        for name,value in (('require',lambda *args:None),('Checker',type('ForeignChecker',(),{})),('gate_failure_summary',types.FunctionType(g.gate_failure_summary.__code__,namespace))):
            checker=checker_for(report)
            with mock.patch.object(g,name,value):rows,error,_=invoke(report,checker=checker)
            self.assertIsNotNone(error);self.assertEqual(rows,[])
        code=g.Checker.gate.__code__
        try:
            g.Checker.gate.__code__=(lambda *args:False).__code__
            rows,error,_=invoke(report);self.assertIsNotNone(error);self.assertEqual(rows,[])
        finally:g.Checker.gate.__code__=code
    def test_checker_report_context_and_complete_expected_inventory_bound(self):
        for mutate in (lambda obj:obj.__dict__.update(context=copy.deepcopy(obj.context)),lambda obj:obj.__dict__.update(report=copy.deepcopy(obj.report)),lambda obj:obj.__dict__.update(profile_id='small-v2'),lambda obj:obj.gates.clear()):
            report=self.failure();checker=checker_for(report);mutate(checker)
            rows,error,_=invoke(report,checker=checker);self.assertIsNotNone(error);self.assertEqual(rows,[])
        for mutate in (lambda report:report['gates'].pop(),lambda report:report['gates'].append(copy.deepcopy(report['gates'][0])),lambda report:report['gates'][0].update(id='private gate')):
            report=self.failure();mutate(report);rows,error,_=invoke(report);self.assertIsNotNone(error);self.assertEqual(rows,[])
    def test_same_primary_throw_survives_emitter_failure_and_cancellation(self):
        for raised in (OSError('private output failure'),KeyboardInterrupt('private cancellation'),SystemExit('private exit')):
            report=self.failure();originals=[]
            def fail_print(*args,**kwargs):
                trace=sys.exception();originals.append(trace);raise raised
            with mock.patch('builtins.print',side_effect=fail_print):rows,error,_=invoke(report)
            self.assertEqual(rows,[]);self.assertEqual(len(originals),1);self.assertIs(error,originals[0]);self.assertIs(type(error),c.Invalid)
        report=fixtures.synthetic('live');rows,error,text=invoke(report);self.assertIsNone(error);self.assertEqual((rows,text),([],''))
    def test_actual_self_sigint_preserves_primary_and_corrupt_caller_linetable_denied(self):
        report=self.failure();originals=[];old_handler=signal.getsignal(signal.SIGINT)
        def interrupt_print(*args,**kwargs):
            originals.append(sys.exception());os.kill(os.getpid(),signal.SIGINT)
        try:
            signal.signal(signal.SIGINT,signal.default_int_handler)
            with mock.patch('builtins.print',side_effect=interrupt_print):rows,error,_=invoke(report)
        finally:signal.signal(signal.SIGINT,old_handler)
        self.assertEqual(rows,[]);self.assertEqual(len(originals),1);self.assertIs(error,originals[0])
        checker=checker_for(report);rows,error,_=invoke(report,checker=checker)
        trace=error.__traceback__;chain=[]
        while trace is not None:chain.append(trace);trace=trace.tb_next
        self.assertIs(chain[-3].tb_frame.f_code,g._GATE_VALIDATE_CODE)
        for lasti,line in ((chain[-3].tb_lasti,999999),(0,chain[-3].tb_lineno)):
            altered=types.TracebackType(chain[-2],chain[-3].tb_frame,lasti,line)
            for item in reversed(chain[:-3]):altered=types.TracebackType(altered,item.tb_frame,item.tb_lasti,item.tb_lineno)
            error.__traceback__=altered
            self.assertIsNone(g.gate_failure_summary(error,checker,report,report['context']))

    def test_actual_main_mutable_phase_and_absent_global_serializer_forgery(self):
        previous=g.collector_failure_phase
        try:
            g.collector_failure_phase='report-validation'
            rows,error,_=invoke(self.failure());self.assertIs(type(error),c.Invalid);self.assertEqual(len(rows),1)
            calls=[]
            with mock.patch.object(g,'print',side_effect=lambda *args,**kwargs:calls.append(True),create=True):
                rows,error,text=invoke(self.failure())
            self.assertEqual(calls,[]);self.assertEqual((rows,text),([],''));self.assertIs(type(error),c.Invalid)
            with mock.patch.object(g.json,'dumps',return_value='private forged serializer payload'):
                rows,error,text=invoke(self.failure())
            self.assertEqual((rows,text),([],''));self.assertIs(type(error),c.Invalid)
            self.assertTrue(g.gate_failure_binding_intact())
        finally:g.collector_failure_phase=previous

    def test_unowned_require_error_and_private_exception_not_projected(self):
        report=self.failure();checker=checker_for(report)
        try:c.require(False,'leak-scan-coverage')
        except c.Invalid as error:self.assertIsNone(g.gate_failure_summary(error,checker,report,report['context']))
        class Private(c.Invalid):
            def __str__(self):raise AssertionError('private formatter')
            @property
            def args(self):raise AssertionError('private args')
        self.assertIsNone(g.gate_failure_summary(Private('private transcript'),checker,report,report['context']))
    def test_host_decoder_denies_duplicate_unknown_private_unicode_bool_and_inventory(self):
        value=invoke(self.failure())[0][0]
        self.assertEqual(g.GATE_FAILURE_CODES,r.GATE_FAILURE_CODES);self.assertEqual(g.GATE_FAILURE_EXPECTED,r.GATE_FAILURE_EXPECTED)
        for mutate in (lambda row:row.update(private='private text'),lambda row:row.update(release_acceptance=0),lambda row:row.update(phase='private phase'),lambda row:row['gates'][0].update(code='private text'),lambda row:row['gates'][0].update(status=False),lambda row:row['gates'].reverse(),lambda row:row['gates'].append(copy.deepcopy(row['gates'][0]))):
            changed=copy.deepcopy(value);mutate(changed);self.assertIsNone(r.gate_failure_record(json.dumps(changed).encode()))
        for raw in (b'\xff',b'{"schema":"x","schema":"y"}',b'{"schema":NaN}',b' '*16385):self.assertIsNone(r.gate_failure_record(raw))
    def test_owned_uart_relay_bounded_complete_single_observation_only(self):
        value=invoke(self.failure())[0][0];line=b'ARCTIC-DICTATION-GATE-SUMMARY '+json.dumps(value).encode()+b'\r\n'
        with tempfile.TemporaryDirectory() as directory:
            vm=Path(directory);(vm/'serial-boot.log').write_bytes(b'private unrelated transcript\n'+line)
            out=io.StringIO()
            with contextlib.redirect_stdout(out):r.relay_gate_failures(vm,'online-installed')
            self.assertEqual(len(out.getvalue().splitlines()),1);self.assertNotIn('private unrelated transcript',out.getvalue())
            for raw in (line+line,line[:-1],line.replace(b'online-installed',b'offline-installed'),b'ARCTIC-DICTATION-GATE-SUMMARY '+b' '*16385+b'\n'):
                (vm/'serial-boot.log').write_bytes(raw);out=io.StringIO()
                with contextlib.redirect_stdout(out):r.relay_gate_failures(vm,'online-installed')
                self.assertEqual(out.getvalue(),'')
            (vm/'serial-boot.log').unlink();(vm/'serial-boot.log').symlink_to('/dev/null');out=io.StringIO()
            with contextlib.redirect_stdout(out):r.relay_gate_failures(vm,'online-installed')
            self.assertEqual(out.getvalue(),'')

if __name__=='__main__':unittest.main()
