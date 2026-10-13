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
    def _host_root(self,base):
        root=Path(base);(root/'private').mkdir();(root/'public').mkdir()
        return root
    def _phase_path(self,root,rel,kind,payload=b'private bytes'):
        path=root/rel;path.parent.mkdir(parents=True,exist_ok=True)
        if kind=='directory':path.mkdir(exist_ok=True)
        else:path.write_bytes(payload)
        return path
    def test_closed_host_stage_exhaustive_presence_states_are_finite_metadata_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=self._host_root(td)
            self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_INITIAL)
            for expected,rel,kind in R.CLOSED_HOST_STAGE_PATHS:
                self._phase_path(root,rel,kind)
                self.assertEqual(R.closed_host_stage(root),expected)
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
            for forbidden in ('private bytes','vm-prepared-image-id.txt','harness.log','vm-toolchain.txt',
                              'data.iso','target.qcow2','qemu-install.log','serial-install.log',
                              'digest','length','content','path','size'):
                self.assertNotIn(forbidden,raw)

    def test_closed_host_stage_rejects_every_wrong_kind_symlink_gap_and_lstat_error(self):
        class Hostile(OSError):
            def __str__(self):raise AssertionError('foreign error rendered')
            def __repr__(self):raise AssertionError('foreign error represented')
        paths=R.CLOSED_HOST_STAGE_PATHS
        for index,(unused_label,rel,kind) in enumerate(paths):
            with tempfile.TemporaryDirectory() as td:
                root=self._host_root(td)
                for unused_prefix_label,prefix_rel,prefix_kind in paths[:index]:
                    self._phase_path(root,prefix_rel,prefix_kind)
                path=root/rel;path.parent.mkdir(parents=True,exist_ok=True)
                if kind=='directory':path.write_bytes(b'wrong-kind')
                else:path.mkdir()
                self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            with tempfile.TemporaryDirectory() as td:
                root=self._host_root(td)
                for unused_prefix_label,prefix_rel,prefix_kind in paths[:index]:
                    self._phase_path(root,prefix_rel,prefix_kind)
                path=root/rel;path.parent.mkdir(parents=True,exist_ok=True)
                path.symlink_to(root/'private/missing')
                self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
        with tempfile.TemporaryDirectory() as td:
            root=self._host_root(td)
            # A later fixed receipt with an earlier gap is inconsistent and fails closed.
            self._phase_path(root,paths[1][1],paths[1][2])
            self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            original=R.os.lstat
            try:
                R.os.lstat=lambda unused:(_ for _ in ()).throw(Hostile())
                self.assertEqual(R.closed_host_stage(root),R.CLOSED_HOST_STAGE_UNKNOWN)
            finally:R.os.lstat=original

    def test_closed_host_stage_runs_on_exact_nonzero_and_exception_only(self):
        calls=[];original=R.publish_closed_host_stage
        R.publish_closed_host_stage=lambda out,value:calls.append((out,value))
        try:
            marker=object();value=object()
            for result in (1,-1):
                self.assertEqual(R.run_private(lambda result=result:result,marker,value),result)
                self.assertEqual(calls,[(marker,value)]);calls.clear()
            self.assertEqual(R.run_private(lambda:0,marker,value),0)
            self.assertEqual(calls,[])
            self.assertIs(R.run_private(lambda:True,marker,value),True)
            class IntSubclass(int):pass
            subclass=IntSubclass(1)
            self.assertIs(R.run_private(lambda:subclass,marker,value),subclass)
            foreign=object()
            self.assertIs(R.run_private(lambda:foreign,marker,value),foreign)
            self.assertEqual(calls,[])
            class Failure(BaseException):pass
            original_error=Failure()
            def fail():raise original_error
            with self.assertRaises(Failure) as caught:R.run_private(fail,marker,value)
            self.assertIs(caught.exception,original_error)
            self.assertEqual(calls,[(marker,value)])
        finally:R.publish_closed_host_stage=original

    def test_closed_host_stage_write_failure_never_masks_result_or_exception(self):
        class DiagnosticFailure(BaseException):
            def __str__(self):raise AssertionError('diagnostic failure rendered')
            def __repr__(self):raise AssertionError('diagnostic failure represented')
        class OriginalFailure(BaseException):pass
        original=R.publish_closed_host_stage
        R.publish_closed_host_stage=lambda unused_out,unused_value:(_ for _ in ()).throw(DiagnosticFailure())
        try:
            self.assertEqual(R.run_private(lambda:1,object(),object()),1)
            failure=OriginalFailure()
            def fail():raise failure
            with self.assertRaises(OriginalFailure) as caught:
                R.run_private(fail,object(),object())
            self.assertIs(caught.exception,failure)
        finally:R.publish_closed_host_stage=original

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
    def test_preparation_commit_is_directly_over_guard_base(self):
        row=subprocess.check_output(['git','-C',str(ROOT),'rev-list','--parents','-n','1','HEAD'],
            text=True).split()
        self.assertIn(len(row),(2,3))
        candidate=row[0] if len(row)==2 else row[2]
        if len(row)==3:
            self.assertEqual(subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD^{tree}'],
                text=True).strip(),subprocess.check_output(
                ['git','-C',str(ROOT),'rev-parse',candidate+'^{tree}'],text=True).strip())
        self.assertEqual(subprocess.check_output(
            ['git','-C',str(ROOT),'rev-list','--parents','-n','1',candidate],
            text=True).split(),[candidate,C.BASE])
        paths=set(subprocess.check_output(
            ['git','-C',str(ROOT),'diff','--no-renames','--name-only',C.BASE,candidate],
            text=True).splitlines())
        self.assertEqual(paths,C.ADDITIONS)
        self.assertFalse(subprocess.run(['git','-C',str(ROOT),'cat-file','-e',
            candidate+':'+C.MARKER],capture_output=True).returncode==0)

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
