"""Small fresh composition controls; accepted eleven component controls reused."""
import ast,hashlib,importlib.util,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('fresh_UI_test_common',HERE/'common.py');C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
old=sys.modules.get('common');absent='common'not in sys.modules
try:
    sys.modules['common']=C
    spec=importlib.util.spec_from_file_location('fresh_UI_test_run',HERE/'run.py');R=importlib.util.module_from_spec(spec);spec.loader.exec_module(R)
finally:
    if absent:sys.modules.pop('common',None)
    else:sys.modules['common']=old

class Controls(unittest.TestCase):
    def value(self):return json.loads((HERE/'execution-manifest.json').read_bytes())
    def test_disabled_and_original_all_budget_guards(self):
        value=self.value();self.assertIs(C.manifest(value),value)
        with self.assertRaises(RuntimeError):C.manifest(value,True)
        for key,wrong in(('ui_seconds',719),('max_png',15),('install_timeout',2399),('harness_seconds',4199),('boot_network','online'),('release_acceptance',True)):
            bad=dict(value);bad[key]=wrong
            with self.assertRaises(RuntimeError):R.main_adapter(bad)

    def test_original_Code_and_exact_guard_projection_only(self):
        observed,published,state,helper,originals,buffers=R.main_adapter(self.value())
        self.assertIs(observed.main.__code__,published.main.__code__)
        self.assertIs(observed.C.decode,published.C.decode)
        self.assertIs(observed.C.require,published.C.require)
        self.assertEqual(observed.C.ROOT,published.C.ROOT)
        bad=json.loads(buffers[C.ORIGINAL_PREFIX+'execution-manifest.json']);bad['ui_seconds']=719
        with mock.patch.object(C,'guard',side_effect=AssertionError('wrong projection reached guard')),self.assertRaises(RuntimeError):observed.C.guard(bad,Path('/unused'))
        sentinel=RuntimeError('explicit synthetic guard stop')
        good=json.loads(buffers[C.ORIGINAL_PREFIX+'execution-manifest.json'])
        with mock.patch.object(C,'guard',side_effect=sentinel)as guard,self.assertRaises(RuntimeError)as caught:observed.C.guard(good,Path('/unused'))
        self.assertIs(caught.exception,sentinel);self.assertIs(guard.call_args.args[0]['ready'],False)
        self.assertIsNone(state['finite'])

    def test_source_component_drift_before_factory(self):
        value=self.value();path=C.ROOT/C.COMPONENT_PREFIX/'match-diagnostic.py';original=path.read_bytes()
        try:
            path.write_bytes(original+b'\n# synthetic fixture drift\n')
            with self.assertRaises(RuntimeError):R.main_adapter(value)
        finally:path.write_bytes(original)

    def test_actual_publication_writer_exact_and_negative_outputs(self):
        originals=R.originals_module(self.value())
        with tempfile.TemporaryDirectory()as d:
            output=Path(d)/'step-output';output.touch(mode=0o600)
            R.publication_output(output,originals);self.assertEqual(output.read_bytes(),b'upload_admitted=true\n')
            with self.assertRaises(ValueError):R.publication_output(output,originals)
            link=Path(d)/'symlink';link.symlink_to(output)
            with self.assertRaises(ValueError):R.publication_output(link,originals)

    def test_workflow_only_admitted_upload_and_unchanged_budgets(self):
        raw=(C.ROOT/'.github/workflows/final-installed-ui-retained-evidence-20261011.yml').read_text()
        self.assertIn("if: always() && steps.screened.outputs.upload_admitted == 'true'",raw)
        self.assertEqual(raw.count('actions/upload-artifact@v4'),1)
        self.assertIn('python3-pil tesseract-ocr tesseract-ocr-eng',raw)
        self.assertIn('timeout-minutes: 120',raw)
        self.assertEqual(C.BASE,'44c789f068a49d642b5122288ccccca767f1ddc0')
        self.assertEqual(len(C.ADDITIONS),12);self.assertEqual(len(C.FILES),24)
        self.assertNotIn(C.MARKER,C.ADDITIONS)

if __name__=='__main__':unittest.main()
