"""Actual unchanged-validator failures, closed Source ownership and privacy controls.

Synthetic numeric schema data is not audio, installation or runtime acceptance.
"""
import ast
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
BASE_GUEST_SHA256='1033f55635d92ab874ab769cc006af501a1a5d866abe24afff826c2e2623e1b9'
BASE_RUNNER_SHA256='d7fde07abfe89c09a9e5a30d6744bd45b3dadc541f298947e6e43a165c4e2b52'
CONTRACT_SHA256='1ab44f66d744939d4bd7d6b7034f4c2beac738168d1ae34c2572a1f95a0da3cf'
ADDON_SHA256='9b614ca997292b0e3b169b80f8ef00d964599fdbd7208b9372420994a89feab8'
BRANCH_SHA256='2a9cbca44f6b6437fd5e5bf85a7b6dd160afa081ae518aabcbe9e57b0a777673'
RUNNER_ADDON_SHA256='b86d97be3d594cfa584b8cdf187ab614c4b86bec69b229e1760a553d090d7b28'

def restore_report_guard_projection(text):
    from test_gate_failure_summary import restore_gate_failure_summary
    text=restore_gate_failure_summary(text)
    begin='# BEGIN OWNED_REPORT_CONTRACT_GUARDS\n';end='# END OWNED_REPORT_CONTRACT_GUARDS\n\n'
    if begin not in text:return text
    assert text.count(begin)==text.count(end)==1
    start=text.index(begin);stop=text.index(end,start)+len(end)
    assert hashlib.sha256(text[start:stop].encode()).hexdigest()==ADDON_SHA256
    text=text[:start]+text[stop:]
    begin='    # A genuine unchanged contract.validate -> require failure gets only a\n'
    start=text.index(begin);stop=text.index('    for frame in frames[-1:]:\n',start)
    assert hashlib.sha256(text[start:stop].encode()).hexdigest()==BRANCH_SHA256
    text=text[:start]+text[stop:]
    before="return next((code for code in COLLECTOR_FAILURE_GUARDS if value == code and not code.startswith('contract-')), 'unknown')"
    after="return next((code for code in COLLECTOR_FAILURE_GUARDS if value == code), 'unknown')"
    assert text.count(before)==1
    text=text.replace(before,after,1)
    assert hashlib.sha256(text.encode()).hexdigest()==BASE_GUEST_SHA256
    return text

def restore_report_guard_relay(text):
    from test_gate_failure_summary import restore_gate_failure_relay
    text=restore_gate_failure_relay(text)
    begin='# BEGIN REPORT_CONTRACT_GUARD_RELAY\n';end='# END REPORT_CONTRACT_GUARD_RELAY\n\n'
    if begin not in text:return text
    assert text.count(begin)==text.count(end)==1
    start=text.index(begin);stop=text.index(end,start)+len(end)
    assert hashlib.sha256(text[start:stop].encode()).hexdigest()==RUNNER_ADDON_SHA256
    text=text[:start]+text[stop:]
    # Older rollback helpers may have already removed their own disjoint block.
    return text

def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
import contract as c
import test_contract as fixtures
g=load('actual_report_guard_guest','guest_check.py');r=load('actual_report_guard_runner','runner.py')

def actual_error(report):
    try:c.validate(report,report['context'],fixture_manifest=fixtures.FIXTURES)
    except c.Invalid as error:return error
    raise AssertionError('Expected genuine unchanged-validator failure')

class ReportGuardProjection(unittest.TestCase):
    def setUp(self):self.old_phase=g.collector_failure_phase;g.collector_failure_phase='report-validation'
    def tearDown(self):g.collector_failure_phase=self.old_phase
    def record(self,error):
        value=g.collector_failure(error)
        self.assertIs(value['release_acceptance'],False)
        self.assertEqual(r.collector_failure_record(json.dumps(value).encode()),value)
        self.assertNotIn('private',json.dumps(value));return value
    def test_whole_byte_inverse_and_unchanged_contract(self):
        self.assertEqual(hashlib.sha256(restore_report_guard_projection(HERE.joinpath('guest_check.py').read_text()).encode()).hexdigest(),BASE_GUEST_SHA256)
        self.assertEqual(hashlib.sha256(restore_report_guard_relay(HERE.joinpath('runner.py').read_text()).encode()).hexdigest(),BASE_RUNNER_SHA256)
        self.assertEqual(hashlib.sha256(HERE.joinpath('contract.py').read_bytes()).hexdigest(),CONTRACT_SHA256)
        text=HERE.joinpath('guest_check.py').read_text()
        for before,after in (("frames[-2].f_code is _REPORT_VALIDATE_CODE","True"),("frame.f_globals is not _REPORT_GLOBALS","frame.f_globals is _REPORT_GLOBALS"),("return result  # No truncated prefix", "return {}  # No truncated prefix")):
            self.assertIn(before,text)
            with self.assertRaises(AssertionError):restore_report_guard_projection(text.replace(before,after,1))
    def test_sites_cover_exact61_actual_literal_require_calls(self):
        fn=next(n for n in ast.parse(HERE.joinpath('contract.py').read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='validate')
        calls=sorted([n for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='require'],key=lambda n:(n.lineno,n.col_offset))
        self.assertEqual(len(calls),61)
        self.assertEqual(g._REPORT_GUARD_SITES,tuple((n.lineno,n.end_lineno,n.args[1].value,'contract-'+format(i+1,'03d')) for i,n in enumerate(calls)))
        self.assertEqual(set(g.COLLECTOR_FAILURE_GUARDS)|{'unknown'},r.COLLECTOR_FAILURE_GUARDS)
    def test_distinct_genuine_predicates_emit_only_closed_site_codes(self):
        cases=(('schema','private schema','contract-002'),('controller_sha256','a'*64,'contract-004'),('limitations',[],'contract-005'),('payload',{'private':{}},'contract-009'),('disk',[],'contract-011'),('gates',(),'contract-015'),('samples',[{}]*17,'contract-041'))
        for field,value,guard in cases:
            with self.subTest(field=field):
                report=fixtures.synthetic('online-installed') if field=='payload' else fixtures.synthetic();report[field]=value;error=actual_error(report);original=error;error.args=('private Hebrew English transcript',)
                record=self.record(error);self.assertEqual((record['frame'],record['guard'],record['caller']),('report-contract',guard,'unknown'))
                output=io.StringIO()
                with contextlib.redirect_stdout(output):g.emit_collector_failure(error)
                self.assertNotIn('private',output.getvalue());self.assertIs(error,original)
                try:raise error
                except c.Invalid as repeated:self.assertIs(repeated,original)
    def test_private_unknown_and_unowned_literal_calls_do_not_match(self):
        class Private(c.Invalid):
            def __str__(self):raise AssertionError('private formatter')
            @property
            def args(self):raise AssertionError('private args')
        self.assertEqual(self.record(Private('private'))['guard'],'unknown')
        try:c.require(False,'report-fields')
        except c.Invalid as error:self.assertEqual(self.record(error)['guard'],'unknown')
        error=actual_error(dict(fixtures.synthetic(),schema='private'))
        with mock.patch.object(g,'validate',types.FunctionType(c.validate.__code__,c.__dict__)):
            self.assertEqual(self.record(error)['guard'],'unknown')
    def test_foreign_globals_code_copy_and_changed_loaded_bindings_denied(self):
        foreign=dict(c.__dict__);function=types.FunctionType(c.validate.__code__,foreign,argdefs=c.validate.__defaults__)
        report=fixtures.synthetic();report['schema']='private'
        try:function(report,report['context'])
        except c.Invalid as error:self.assertEqual(self.record(error)['guard'],'unknown')
        error=actual_error(report)
        for module,name,value in ((c,'validate',lambda *args:None),(c,'require',lambda *args:None),(c,'SCHEMA','private changed constant'),(g,'require',lambda *args:None),(g,'Invalid',Exception)):
            with self.subTest(name=name),mock.patch.object(module,name,value):self.assertEqual(self.record(error)['guard'],'unknown')
    def test_foreign_function_cannot_use_closed_report_labels_via_generic_path(self):
        namespace=dict(g.__dict__)
        exec(compile("def fake(report, expected):\n    require(False, 'contract-001')\n", '<foreign private function>', 'exec'),namespace)
        with mock.patch.object(g,'validate',namespace['fake']):
            try:g.validate({}, {})
            except c.Invalid as error:
                value=self.record(error);self.assertEqual(value['guard'],'unknown')
            else:self.fail('Expected foreign failure')
    def test_replaced_code_and_changed_line_table_cannot_label(self):
        error=actual_error(dict(fixtures.synthetic(),schema='private'))
        original=c.validate.__code__
        try:
            c.validate.__code__=(lambda *args,**kwargs:None).__code__
            self.assertEqual(self.record(error)['guard'],'unknown')
        finally:c.validate.__code__=original
        trace=error.__traceback__
        while trace.tb_frame.f_code is not c.validate.__code__:trace=trace.tb_next
        throwing=trace.tb_next
        forged=types.TracebackType(throwing,trace.tb_frame,trace.tb_lasti,999999)
        self.assertEqual(g.owned_report_guard(forged,throwing),'unknown')
        forged=types.TracebackType(throwing,trace.tb_frame,0,trace.tb_lineno)
        self.assertEqual(g.owned_report_guard(forged,throwing),'unknown')
    def test_actual_main_callsite_preserves_cleanup_and_same_original_throw(self):
        report=fixtures.synthetic('online-installed');report['schema']='private transcript'
        cleaned=[]
        class SyntheticChecker:
            def __init__(self,declared):self.report=report;self.gates=c.gates(declared['phase'],declared['hardware_profile'])
            def execute(self):return self.report
            def close(self):cleaned.append('owned synthetic cleanup')
            def audit_state(self):return None
        result=types.SimpleNamespace(stdout=b'qemu',stderr=b'',returncode=0)
        with mock.patch.object(g.sys,'argv',['checker','installed','--disposable-guest']), \
                mock.patch.object(g.os,'geteuid',return_value=0), \
                mock.patch.object(g,'DATA',g.HERE.parent), \
                mock.patch.object(g.Path,'read_text',return_value='installed fixture'), \
                mock.patch.object(g,'run',return_value=result), \
                mock.patch.object(g,'read',return_value=report['context']), \
                mock.patch.object(g,'owned_file',return_value=None), \
                mock.patch.object(g,'sha',return_value='c'*64), \
                mock.patch.object(g,'Checker',SyntheticChecker):
            output=io.StringIO()
            with contextlib.redirect_stdout(output):
                try:g.main()
                except c.Invalid as error:
                    original=error;value=self.record(error);g.emit_collector_failure(error)
                    self.assertEqual((value['phase'],value['frame'],value['caller'],value['guard']),
                                     ('report-validation','report-contract','main','contract-002'))
                    self.assertIs(error,original)
                else:self.fail('Actual main must preserve failed validation')
        self.assertEqual(cleaned,['owned synthetic cleanup'])
        self.assertNotIn('private',output.getvalue())
        self.assertNotIn('ARCTIC-DICTATION-QUALIFICATION ',output.getvalue())
    def test_host_only_accepts_closed_exact_labels_not_private_values(self):
        record=self.record(actual_error(dict(fixtures.synthetic(),schema='private')))
        for field,value in (('guard','private transcript'),('guard','contract-062'),('frame','private'),('transcript','private'),('release_acceptance',True)):
            changed=dict(record);changed[field]=value
            with self.subTest(field=field,value=value):self.assertIsNone(r.collector_failure_record(json.dumps(changed).encode()))
        good=fixtures.synthetic();c.validate(good,good['context'],fixture_manifest=fixtures.FIXTURES)
        self.assertIs(good['release_acceptance'],False)

if __name__=='__main__':unittest.main()
