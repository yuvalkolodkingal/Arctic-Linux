#!/usr/bin/env python3
import importlib.util,json,subprocess,sys,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('private_review_common',HERE/'common.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
class Tests(unittest.TestCase):
    def test_manifest_is_disabled_without_recipient(self):
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes())
        self.assertIs(C.manifest(value)['ready'],False)
        self.assertIsNone(value['private_review_binding']['recipient'])
        with self.assertRaisesRegex(RuntimeError,'pending local key generation'):
            C.manifest(value,True)
    def test_no_marker_and_no_manual_dispatch(self):
        workflow=(ROOT/'.github/workflows/final-bios-private-record-review-20261012.yml').read_text()
        self.assertNotIn('workflow_dispatch',workflow)
        self.assertFalse((ROOT/C.MARKER).exists())
        self.assertIn('sealed/record.age',workflow);self.assertIn('sealed/receipt.json',workflow)
        self.assertNotIn('/private/',workflow)
    def test_source_suite(self):
        result=subprocess.run([sys.executable,'-B',str(ROOT/'tools/private-record-seal-source/test_source.py')],
            cwd=ROOT,text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_additions_are_all_new_and_release_false(self):
        self.assertTrue(all(not subprocess.run(['git','-C',str(ROOT),'cat-file','-e',
            C.BASE+':'+path],capture_output=True).returncode==0 for path in C.ADDITIONS))
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes())
        self.assertFalse(value['release_acceptance'])
        self.assertFalse(value['private_review_binding']['privacy_gate_changed'])
if __name__=='__main__':unittest.main()
