#!/usr/bin/env python3
"""Focused exact composition and pre-API controls, synthetic Source only."""
import copy,json,sys,types,unittest
from pathlib import Path
from unittest import mock
import common as C
import run as R
HERE=Path(__file__).resolve().parent

def manifest():return C.manifest(C.strict_json((HERE/'execution-manifest.json').read_bytes()))
class Controls(unittest.TestCase):
    def test_exact_main_and_only_admission_dependency_changed(self):
        wrapped,observed,original,state=R.main_adapter(manifest())
        self.assertIs(wrapped.__code__,observed.__code__);self.assertIs(wrapped.__code__,original.__code__)
        self.assertEqual(set(wrapped.__globals__),set(observed.__globals__))
        self.assertEqual({n for n in observed.__globals__ if wrapped.__globals__[n]is not observed.__globals__[n]},{'C'})
        before=observed.__globals__['C'];after=wrapped.__globals__['C']
        self.assertEqual(set(before.__dict__),set(after.__dict__))
        self.assertEqual({n for n in before.__dict__ if before.__dict__[n]is not after.__dict__[n]},{'guard'})
        self.assertIsNone(state['finite'])
        self.assertEqual(manifest()['install_timeout'],2400);self.assertEqual(manifest()['harness_seconds'],6600)
    def test_actual_original_main_reaches_new_guard_before_runtime(self):
        wrapped,observed,original,state=R.main_adapter(manifest());seen=[]
        class GuardReached(Exception):pass
        def guard(value,source,inputs=None):seen.append((value,source,inputs));raise GuardReached()
        with mock.patch.object(C,'guard',guard),mock.patch.object(sys,'argv',
            ['Source-control','--source','/source','--inputs','/inputs','--out','/unused']):
            with self.assertRaises(GuardReached):wrapped()
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][0],manifest())
        self.assertEqual(seen[0][1:],(Path('/source'),Path('/inputs')))
    def test_disabled_main_and_guard_reject_before_API(self):
        with mock.patch.object(C,'load',side_effect=AssertionError('No module before disabled main')):
            with self.assertRaisesRegex(RuntimeError,'lane remains disabled'):R.main()
        with mock.patch.object(C,'git',side_effect=AssertionError('No Git/API before disabled guard')):
            with self.assertRaisesRegex(RuntimeError,'lane remains disabled'):C.guard(manifest(),Path('/source'))
    def test_changed_projection_and_component_binding_before_delegate(self):
        wrapped,observed,original,state=R.main_adapter(manifest())
        with mock.patch.object(C,'guard',side_effect=AssertionError('No guard after changed projection')):
            with self.assertRaisesRegex(RuntimeError,'manifest projection differs'):
                wrapped.__globals__['C'].guard({'foreign':'Source control'},Path('/source'))
        value=copy.deepcopy(manifest());value['strict_screen_binding']['source_sha']='0'*40
        with mock.patch.object(C,'load',side_effect=AssertionError('No factory after changed binding')):
            with self.assertRaisesRegex(RuntimeError,'strict screen Source binding differs'):R.main_adapter(value)
    def test_runtime_drift_before_factory(self):
        value=copy.deepcopy(manifest());value['execution_files']['tools/final-bios-strict-screen-observer/observer.py']='0'*64
        with mock.patch.object(C,'load',side_effect=AssertionError('No factory after runtime drift')):
            with self.assertRaisesRegex(RuntimeError,'runtime pin differs'):R.main_adapter(value)
    def test_workflow_original_private_upload_and_budget_contract(self):
        raw=(C.ROOT/'.github/workflows/final-bios-strict-observed-install-20261011.yml').read_bytes()
        self.assertIn(b'contents: read\n  actions: read',raw);self.assertIn(b'fetch-depth: 0',raw)
        self.assertIn(b'tesseract-ocr',raw);self.assertIn(b'timeout-minutes: 180',raw)
        self.assertIn(b'evidence/public/',raw);self.assertNotIn(b'evidence/private',raw)
        self.assertNotIn(b'tail -n',raw);self.assertEqual(len(C.ADDITIONS),11);self.assertEqual(len(C.FILES),44)
if __name__=='__main__':unittest.main()
