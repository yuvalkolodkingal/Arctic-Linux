#!/usr/bin/env python3
import contextlib,importlib.util,io,json,subprocess,sys,types,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('private_review_common',HERE/'common.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
composition_spec=importlib.util.spec_from_file_location('private_review_composition',HERE/'composition.py')
P=importlib.util.module_from_spec(composition_spec);composition_spec.loader.exec_module(P)
class Tests(unittest.TestCase):
    def test_manifest_recipient_state_is_closed(self):
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes());checked=C.manifest(value)
        binding=value['private_review_binding']
        if checked['ready']:
            self.assertTrue(binding['recipient_generated_outside_github']);self.assertIs(C.manifest(value,True),value)
        else:
            self.assertIsNone(binding['recipient'])
            with self.assertRaisesRegex(RuntimeError,'pending local key generation'):C.manifest(value,True)
    def test_activation_and_no_manual_dispatch(self):
        workflow=(ROOT/'.github/workflows/final-bios-private-record-review-20261013.yml').read_text()
        self.assertNotIn('workflow_dispatch',workflow);marker=ROOT/C.MARKER
        if marker.exists():self.assertRegex(marker.read_text(),r'\A[0-9a-f]{40}\n\Z')
        else:self.assertTrue(C.manifest(C.strict_json((HERE/'execution-manifest.json').read_bytes()))['ready'])
        self.assertIn('sealed/record.age',workflow);self.assertIn('sealed/receipt.json',workflow);self.assertNotIn('/private/',workflow)
    def test_seal_diagnostic_is_finite_and_does_not_render_errors(self):
        class Foreign(BaseException):
            def __str__(self):raise AssertionError('foreign exception was rendered')
        for candidate,expected in (('private-seal-stage-record-boundary','private-seal-stage-record-boundary'),('private-value',P.SEAL_STAGE_UNKNOWN)):
            sealer=types.SimpleNamespace(closed_failure_label=lambda unused,value=candidate:value);output=io.StringIO()
            with contextlib.redirect_stdout(output):self.assertEqual(P.report_seal_failure(sealer,Foreign()),expected)
            self.assertEqual(output.getvalue(),P.SEAL_DIAGNOSTIC_PREFIX+expected+'\n');self.assertNotIn('private-value',output.getvalue())
        def fail(unused):raise RuntimeError('private-value')
        output=io.StringIO()
        with contextlib.redirect_stdout(output):self.assertEqual(P.report_seal_failure(types.SimpleNamespace(closed_failure_label=fail),Foreign()),P.SEAL_STAGE_UNKNOWN)
        self.assertNotIn('private-value',output.getvalue())
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
