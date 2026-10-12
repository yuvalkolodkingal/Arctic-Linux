#!/usr/bin/env python3
"""Narrow exact namespace controls; no VM, API responses or original inputs."""
import copy,json,sys,types,unittest
from pathlib import Path
from unittest import mock
import common as C
import run as R

def manifest():return C.manifest(C.strict_json((R.HERE/'execution-manifest.json').read_bytes()))

class Controls(unittest.TestCase):
    def test_original_code_and_all_dependencies_except_guard_exact(self):
        wrapped,exact,state=R.main_adapter(manifest())
        self.assertIs(wrapped.__code__,exact.__code__)
        self.assertEqual(set(wrapped.__globals__),set(exact.__globals__))
        for name,value in exact.__globals__.items():
            if name!='C':self.assertIs(wrapped.__globals__[name],value,name)
        before=exact.__globals__['C'];after=wrapped.__globals__['C']
        self.assertEqual(set(before.__dict__),set(after.__dict__))
        for name,value in before.__dict__.items():
            if name!='guard':self.assertIs(after.__dict__[name],value,name)
        self.assertIsNot(before.guard,after.guard)
        self.assertEqual(manifest()['install_timeout'],2400)
        self.assertEqual(manifest()['harness_seconds'],6600)

    def test_actual_original_main_reaches_new_guard_before_runtime(self):
        wrapped,exact,state=R.main_adapter(manifest());seen=[]
        class AdmissionReached(Exception):pass
        def admitted(value,source,inputs=None):
            seen.append((value,source,inputs));raise AdmissionReached()
        with mock.patch.object(C,'guard',admitted),mock.patch.object(sys,'argv',
            ['owned-source-control','--source','/source','--inputs','/inputs','--out','/unused-output']):
            with self.assertRaises(AdmissionReached):wrapped()
        self.assertEqual(len(seen),1);self.assertEqual(seen[0][0],manifest())
        self.assertEqual(seen[0][1:],(Path('/source'),Path('/inputs')))
        self.assertIsNone(state['diagnostic'])

    def test_changed_original_manifest_projection_rejected_before_guard(self):
        wrapped,exact,state=R.main_adapter(manifest())
        with mock.patch.object(C,'guard',side_effect=AssertionError('new guard must not run')):
            with self.assertRaisesRegex(RuntimeError,'manifest projection differs'):
                wrapped.__globals__['C'].guard({'foreign':'Source control'},Path('/source'))

    def test_disabled_manifest_and_changed_retention_binding_fail_before_factory(self):
        value=manifest();value['ready']=False
        with mock.patch.object(C,'load',side_effect=AssertionError('factory must not load')):
            with self.assertRaisesRegex(RuntimeError,'lane remains disabled'):R.main_adapter(value)
        value=copy.deepcopy(manifest());value['retention_binding']['source_sha']='0'*40
        with mock.patch.object(C,'load',side_effect=AssertionError('factory must not load')):
            with self.assertRaisesRegex(RuntimeError,'retained Source binding differs'):R.main_adapter(value)

    def test_runtime_pin_drift_rejected_before_factory(self):
        value=copy.deepcopy(manifest());value['execution_files']['tools/final-bios-failure-evidence/evidence.py']='0'*64
        with mock.patch.object(C,'load',side_effect=AssertionError('factory must not load')):
            with self.assertRaisesRegex(RuntimeError,'runtime pin differs'):R.main_adapter(value)

    def test_workflow_only_original_inventory_and_required_ocr(self):
        raw=(C.ROOT/'.github/workflows/final-bios-retained-install-20261011.yml').read_bytes()
        self.assertEqual(raw.count(b'tesseract-ocr'),1)
        self.assertIn(b'install -y python3-pil tesseract-ocr',raw)
        self.assertIn(b'codex/final-bios-retained-install-20261011',raw)
        self.assertIn(b'path: ${{ runner.temp }}/arctic-final-bios-retained/evidence/public/',raw)
        self.assertNotIn(b'evidence/private',raw)
        self.assertNotIn(b'tail -n',raw)
        self.assertEqual(raw.count(b'timeout-minutes: 180'),1)

if __name__=='__main__':unittest.main()
