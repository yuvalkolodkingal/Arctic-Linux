#!/usr/bin/env python3
import contextlib,importlib.util,io,json,os,subprocess,sys,tempfile,types,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('private_review_common',HERE/'common.py')
C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
composition_spec=importlib.util.spec_from_file_location('private_review_composition',HERE/'composition.py')
P=importlib.util.module_from_spec(composition_spec);composition_spec.loader.exec_module(P)
run_spec=importlib.util.spec_from_file_location('private_review_run',HERE/'run.py')
R=importlib.util.module_from_spec(run_spec);run_spec.loader.exec_module(R)
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
    def test_closed_host_stage_is_finite_metadata_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'private/vm').mkdir(parents=True);(root/'public').mkdir()
            for expected,rel,unused_kind in R.CLOSED_HOST_STAGE_PATHS:
                self.assertEqual(R.closed_host_stage(root),expected)
                path=root/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'private bytes')
            self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_AFTER)
            value=C.strict_json((HERE/'execution-manifest.json').read_bytes())
            label=R.publish_closed_host_stage(root,value)
            report=json.loads((root/'public'/R.CLOSED_HOST_STAGE_FILE).read_bytes())
            self.assertEqual(label,R.CLOSED_HOST_STAGE_AFTER)
            self.assertEqual(set(report),{'schema','label','release_acceptance'})
            self.assertEqual(report['schema'],R.CLOSED_HOST_STAGE_SCHEMA)
            self.assertIn(report['label'],R.CLOSED_HOST_STAGE_LABELS)
            self.assertFalse(report['release_acceptance'])
            raw=json.dumps(report,sort_keys=True)
            for forbidden in ('private bytes','vm-toolchain.txt','data.iso','target.qcow2',
                              'qemu-install.log','serial-install.log','digest','length'):
                self.assertNotIn(forbidden,raw)

    def test_closed_host_stage_rejects_nonregular_symlink_and_hostile_lstat(self):
        class Hostile(OSError):
            def __str__(self):raise AssertionError('foreign error rendered')
            def __repr__(self):raise AssertionError('foreign error represented')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'private/vm').mkdir(parents=True);(root/'public').mkdir()
            prepared=root/R.CLOSED_HOST_STAGE_PATHS[0][1]
            prepared.write_bytes(b'prepared')
            (root/'private/vm').rmdir()
            self.assertEqual(R.closed_host_stage(root),'bios-host-before-toolchain')
            (root/'private/vm').mkdir()
            (root/'public').rmdir()
            self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            (root/'public').mkdir()
            prepared.unlink()
            first=root/R.CLOSED_HOST_STAGE_PATHS[0][1]
            first.symlink_to(root/'private/missing')
            self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            first.unlink();first.mkdir()
            self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            original=R.os.lstat
            try:
                R.os.lstat=lambda unused:(_ for _ in ()).throw(Hostile())
                self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            finally:R.os.lstat=original

    def test_real_adapter_builds_only_with_exact_prior_execution_tree(self):
        value=C.strict_json((HERE/'execution-manifest.json').read_bytes())
        with self.assertRaisesRegex(RuntimeError,'prior execution checkout differs'):
            R.main_adapter(value,ROOT,ROOT/'missing-age',ROOT/'missing-sealed')
        with tempfile.TemporaryDirectory() as td:
            prior=Path(td)/'prior'
            subprocess.run(['git','-C',str(ROOT),'worktree','add','--detach',str(prior),
                value['private_review_binding']['prior_execution_commit']],
                check=True,capture_output=True)
            try:
                built=R.main_adapter(value,prior,ROOT/'missing-age',Path(td)/'sealed')
                self.assertEqual(len(built),5)
            finally:
                subprocess.run(['git','-C',str(ROOT),'worktree','remove','--force',str(prior)],
                    check=True,capture_output=True)
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
