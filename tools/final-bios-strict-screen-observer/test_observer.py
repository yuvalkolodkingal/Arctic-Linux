#!/usr/bin/env python3
"""Actual original Source functions, synthetic owned files, no VM or originals."""
import contextlib,json,io,sys,tempfile,types,unittest
from pathlib import Path
from unittest import mock
import observer as O
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
def manifest():return json.loads((HERE/'execution-manifest.json').read_bytes())
def modules():return O.build(manifest())
def failed(evidence,raw):
    with tempfile.TemporaryDirectory() as td:
        vm=Path(td)
        for n in ('serial-install.log','serial-boot.log'):(vm/n).write_bytes(raw)
        with contextlib.redirect_stdout(io.StringIO()):
            try:evidence(vm,{'nonce':'a'*32},'f'*64)
            except BaseException as error:return error
    raise AssertionError('Actual original Source must reject synthetic invalid evidence')
def status(state):return {'status':'failed','phase':'strict-original-evidence','context':state['context'],'release_acceptance':False}
class Controls(unittest.TestCase):
    def test_disabled_and_drift_before_factory(self):
        with self.assertRaises(SystemExit):O.main()
        for k in ('ready','release_acceptance','operational_cli'):
            m=manifest();m[k]=True
            with mock.patch.object(O,'load',side_effect=AssertionError('Factory must not load')):
                with self.assertRaises(ValueError):O.build(m)
        m=manifest();m['published_execution_files']['tools/final-bios-install/run.py']='0'*64
        with mock.patch.object(O,'load',side_effect=AssertionError('Factory must not load')):
            with self.assertRaises(ValueError):O.build(m)
    def test_exact_cumulative_main_only_two_dependency_changes(self):
        observed,original,state=modules()
        self.assertIs(observed.__code__,original.__code__)
        self.assertEqual(tuple(observed.__code__.co_lines()),tuple(original.__code__.co_lines()))
        self.assertEqual(set(observed.__globals__),set(original.__globals__))
        self.assertEqual({n for n in original.__globals__ if original.__globals__[n] is not observed.__globals__[n]},
            {'original_evidence','publish'})
        for n in ('execute','argv','compose','C','remove_owned_container','recover_prepared_image'):
            self.assertIs(observed.__globals__[n],original.__globals__[n])
        self.assertIsNone(state['finite']);self.assertEqual(manifest()['limits']['install_timeout'],2400)
        self.assertEqual(manifest()['limits']['harness_seconds'],6600)
    def test_actual_records_callsite_and_exception_identity(self):
        observed,original,state=modules();seen=[];saved=O.describe
        def record(error,*args):seen.append(error);return saved(error,*args)
        with mock.patch.object(O,'describe',record):
            error=failed(observed.__globals__['original_evidence'],b'public synthetic record\n')
        self.assertIs(error,seen[0]);self.assertIs(type(error),RuntimeError)
        site=state['finite']['original_source_site']
        self.assertEqual(site['fixed_assertion_label'],'Missing or duplicate original BIOS report')
        self.assertEqual(site['function'],'records');self.assertEqual(site['site_kind'],'require')
        self.assertEqual(state['finite']['original_records_stage'],'live')
        self.assertIsNone(state['finite']['same_rejected_match'])
    def test_actual_same_old_scanner_rejected_match_closed_219_enums(self):
        observed,original,state=modules();private=b'control person@example.invalid unrelated secret-value\n'
        self.assertIs(type(failed(observed.__globals__['original_evidence'],private)),RuntimeError)
        item=state['finite'];site=item['original_source_site'];row=item['same_rejected_match']
        self.assertEqual(site['function'],'reject_sensitive_match')
        self.assertEqual(site['fixed_assertion_label'],'Sensitive text in external evidence')
        self.assertEqual(row['regex'],'exact-scanner-regex');self.assertEqual(row['mapping'],'exact-source-view')
        self.assertEqual(row['source_rule'],'external-rule-004');self.assertEqual(row['candidate_reason'],'not-unit-shaped')
        public=json.dumps(item).encode();self.assertNotIn(b'person',public)
        self.assertNotIn(O.sha(private).encode(),public);self.assertNotIn(b'codepoints',public)
        self.assertNotIn(b'public_candidate_sha256',public);self.assertFalse(item['release_acceptance'])
    def test_optional_loader_snapshot_fault_preserves_actual_original_primary(self):
        observed,original,state=modules();saved=O.OwnedSource.__init__;seen=[]
        def bind(owner,namespace,raw,filename,key):
            if key=='original-scanner':seen.append(key);raise OSError('Synthetic optional snapshot fault')
            return saved(owner,namespace,raw,filename,key)
        with mock.patch.object(O.OwnedSource,'__init__',bind):
            error=failed(observed.__globals__['original_evidence'],b'control person@example.invalid\n')
        self.assertIs(type(error),RuntimeError);self.assertEqual(seen,['original-scanner'])
        self.assertIsNone(state['finite'])
        observed,original,state=modules();saved_read=Path.read_bytes
        scanner=ROOT/'tools/native-functional/screen-evidence.py'
        def read(path):
            if path==scanner:raise OSError('No optional Source path reread')
            return saved_read(path)
        with mock.patch.object(Path,'read_bytes',read):
            error=failed(observed.__globals__['original_evidence'],b'public synthetic record\n')
        self.assertIs(type(error),RuntimeError)
        self.assertEqual(state['finite']['original_source_site']['fixed_assertion_label'],
            'Missing or duplicate original BIOS report')

    def test_success_publication_preserves_original_bytes(self):
        observed,original,state=modules()
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);(out/'private').mkdir();raw=b'{"status":"passed_pending_original_image_review"}\n'
            observed.__globals__['publish'](out,{'host-status.json':raw})
            self.assertEqual((out/'public/host-status.json').read_bytes(),raw)
            self.assertIsNone(state['finite'])

    def test_actual_incomplete_escape_raise_site(self):
        observed,original,state=modules()
        self.assertIs(type(failed(observed.__globals__['original_evidence'],b'public fixture\x1b[')),RuntimeError)
        self.assertEqual(state['finite']['original_source_site']['fixed_assertion_label'],
            'Incomplete terminal escape in external evidence')
        self.assertIsNone(state['finite']['same_rejected_match'])
    def test_real_post_binding_scanner_classification_table_drift_rejects(self):
        observed,original,state=modules();saved=O.OwnedSource.__init__;seen=[]
        def bind(owner,namespace,raw,filename,key):
            saved(owner,namespace,raw,filename,key)
            if key=='original-scanner':
                seen.append(key)
                namespace['EXTERNAL_RULES']=(('named-secret',namespace['EXTERNAL_RULES'][3][1]),)
        with mock.patch.object(O.OwnedSource,'__init__',bind):
            error=failed(observed.__globals__['original_evidence'],b'control person@example.invalid\n')
        self.assertIs(type(error),RuntimeError);self.assertEqual(seen,['original-scanner'])
        self.assertIsNone(state['finite'])

    def test_global_absence_equal_distinct_code_and_foreign_export_reject(self):
        for mode in ('late-builtin','code-clone','foreign-function'):
            observed,original,state=modules();ns=original.__globals__['original_evidence'].__globals__
            if mode=='late-builtin':ns['C'].__dict__['RuntimeError']=RuntimeError
            elif mode=='code-clone':ns['records'].__code__=ns['records'].__code__.replace()
            else:
                old=ns['records'];ns['records']=types.FunctionType(old.__code__,old.__globals__,old.__name__)
            self.assertIs(type(failed(observed.__globals__['original_evidence'],b'public control\n')),RuntimeError)
            self.assertIsNone(state['finite'],mode)
    def test_same_buffer_helper_no_path_reread(self):
        observed,original,state=modules();saved=Path.read_bytes;helper=HERE/'match-diagnostic.py'
        def read(path):
            if path==helper:raise AssertionError('No helper re-read after binding')
            return saved(path)
        with mock.patch.object(Path,'read_bytes',read):
            self.assertIs(type(failed(observed.__globals__['original_evidence'],b'control person@example.invalid\n')),RuntimeError)
        self.assertIsNotNone(state['finite'])
    def test_observer_fault_keeps_primary_unknown_foreign_class(self):
        observed,original,state=modules();seen=[]
        def broken(error,*args):seen.append(error);raise OSError('Synthetic observer fault')
        with mock.patch.object(O,'describe',broken):error=failed(observed.__globals__['original_evidence'],b'public record\n')
        self.assertIs(error,seen[0]);self.assertIsNone(state['finite'])
        observed,original,state=modules();ns=original.__globals__['original_evidence'].__globals__
        class Foreign(RuntimeError):pass
        ns['C'].__dict__['RuntimeError']=Foreign
        self.assertIs(type(failed(observed.__globals__['original_evidence'],b'public record\n')),Foreign)
        self.assertIsNone(state['finite'])
    def test_real_publication_whole_original_gate_and_fallback(self):
        observed,original,state=modules();failed(observed.__globals__['original_evidence'],b'control person@example.invalid\n')
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);(out/'private').mkdir();raw=(json.dumps(status(state))+'\n').encode()
            observed.__globals__['publish'](out,{'host-status.json':raw})
            data=(out/'public/host-status.json').read_bytes()
            self.assertEqual(json.loads(data)['strict_original_Source_failure'],state['finite']);self.assertNotIn(b'person',data)
        observed,original,state=modules();failed(observed.__globals__['original_evidence'],b'public record\n')
        state['finite']['foreign_private']='person@example.invalid'
        with tempfile.TemporaryDirectory() as td:
            out=Path(td);(out/'private').mkdir();raw=(json.dumps(status(state))+'\n').encode()
            with contextlib.redirect_stdout(io.StringIO()):observed.__globals__['publish'](out,{'host-status.json':raw})
            self.assertEqual((out/'public/host-status.json').read_bytes(),raw)
if __name__=='__main__':unittest.main()
