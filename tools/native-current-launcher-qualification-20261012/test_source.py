"""Focused actual Source integration controls; owned synthetic inputs only."""
import importlib.util,json,os,sys,tempfile,types,unittest,wave
from pathlib import Path
from unittest import mock
HERE=Path(__file__).resolve().parent
sys.path.insert(1,str(HERE.parent/'native-functional'))
import failure_evidence as F
import inner_runtime as IR
import inner_validation_observer as C
spec=importlib.util.spec_from_file_location('actual_native_inner_csi_runner',HERE/'runner.py')
R=importlib.util.module_from_spec(spec);sys.modules[R.__name__]=R;spec.loader.exec_module(R)
OUT=HERE.parents[1]/'out/native-current-launcher-source'

def observation(root):
    value=json.loads((HERE/'execution-manifest.json').read_bytes());value['ready']=True
    manifest=root/'synthetic-ready-manifest.json';manifest.write_text(json.dumps(value));manifest.chmod(0o600)
    return F.Observation(root,manifest,R.__dict__,R.E.__dict__)
def serials(root):
    harness=root/'harness';harness.mkdir()
    for name in('serial-install.log','serial-boot.log'):(harness/name).write_text('public synthetic fixture\n')
    return harness

class Controls(unittest.TestCase):
    def test_same_code_foreign_globals_observer_denies_before_original_body(self):
        with tempfile.TemporaryDirectory(dir=OUT)as directory:
            root=Path(directory);obs=observation(root);original=C.Capture.trace
            foreign=types.FunctionType(original.__code__,dict(original.__globals__),original.__name__,original.__defaults__,original.__closure__)
            with mock.patch.object(C.Capture,'trace',foreign):
                with self.assertRaisesRegex(ValueError,'^Closed Native observer actual Code globals differs'):
                    with IR.observe(F,obs,root):self.fail('original body must not start under foreign observer binding')
            self.assertIsNone(sys.gettrace());self.assertFalse((root/F.INNER).exists())
    def test_disabled_original_main_and_fetch_deny_before_inputs_or_outgoing_process(self):
        args=types.SimpleNamespace(manifest=HERE/'execution-manifest.json')
        with mock.patch.object(R.subprocess,'check_output',side_effect=AssertionError('outgoing process forbidden')):
            with self.assertRaisesRegex(RuntimeError,'^Prepared native execution is disabled'):R.run(args)
        source=HERE.parent/'native-functional/fetch-image.py';s=importlib.util.spec_from_file_location('original_disabled_native_fetch',source);fetch=importlib.util.module_from_spec(s);s.loader.exec_module(fetch)
        with mock.patch.object(fetch,'api',side_effect=AssertionError('HTTP forbidden')),mock.patch.object(sys,'argv',['fetch','--manifest',str(HERE/'execution-manifest.json'),'--out',str(OUT/'never-opened-input')]):
            with self.assertRaisesRegex(RuntimeError,'^Image fetch is disabled'):fetch.main()
    def test_actual_modules_aggregate_and_retained_finite_member_keep_original108(self):
        with tempfile.TemporaryDirectory(dir=OUT)as directory:
            root=Path(directory);obs=observation(root);harness=serials(root)
            self.assertIs(obs.registry.owners[0].module,R);self.assertIs(obs.registry.owners[1].module,R.E)
            self.assertIs(R.validate_harness_serial,R.E.validate_harness_serial)
            self.assertEqual(tuple(len(o.sites)for o in obs.registry.owners),(50,113))
            try:
                with IR.observe(F,obs,root):R.E.validate_harness_serial(harness,root/'out')
            except RuntimeError as error:self.assertEqual(obs.registry.describe(error),'native-evidence-require-108')
            else:self.fail('original aggregate weakened')
            row=F.strict_json((root/F.INNER).read_bytes());C.closed(row,F)
            self.assertEqual(set(row['original_validation_roles']),{'native-live','native-installed','live-harness','installed-harness'})
            self.assertFalse(row['runtime_cause']);self.assertFalse(row['runtime_acceptance']);self.assertFalse(row['release_acceptance'])
            staged=F.private_member(obs.scanner,root/F.INNER,F.INNER,'inner-observation')
            self.assertEqual(staged[0],(root/F.INNER).read_bytes())
    def test_actual_original_WAV111_retained_without_audio_values_or_counts(self):
        with tempfile.TemporaryDirectory(dir=OUT)as directory:
            root=Path(directory);obs=observation(root);path=root/'synthetic.wav'
            with wave.open(str(path),'wb')as stream:
                stream.setnchannels(2);stream.setframerate(48000);stream.setsampwidth(2);stream.writeframes(b'')
            try:
                with IR.observe(F,obs,root):R.E.preserve_audio(path,root/'audio-out')
            except RuntimeError as error:self.assertEqual(obs.registry.describe(error),'native-evidence-require-111')
            else:self.fail('original WAV gate weakened')
            row=F.strict_json((root/F.INNER).read_bytes());wav=row['original_WAV_predicates']['unknown']
            self.assertEqual(wav['predicates'],dict(zip(C.WAV_FIELDS,(True,True,True,True,False))))
            self.assertNotIn('frames',wav);self.assertNotIn('path',wav)
    def test_foreign_same_code_validator_and_secondary_write_keep_primary(self):
        for foreign in(False,True):
            with self.subTest(foreign=foreign),tempfile.TemporaryDirectory(dir=OUT)as directory:
                root=Path(directory)
                # This is an explicitly synthetic observer output failure installed
                # before the actual module snapshots, never a Source admission.
                primary=[]
                def failed_write(*args):raise KeyboardInterrupt()
                with mock.patch.object(F,'write_exclusive',failed_write):
                    obs=observation(root);harness=serials(root);fn=R.E.validate_harness_serial
                    if foreign:fn=types.FunctionType(fn.__code__,dict(fn.__globals__),fn.__name__,fn.__defaults__,fn.__closure__)
                    try:
                        with IR.observe(F,obs,root)as capture:
                            try:fn(harness,root/'out')
                            except RuntimeError as error:primary.append(error);raise
                    except BaseException as error:
                        self.assertIs(error,primary[0]);self.assertIsInstance(error,RuntimeError)
                    else:self.fail('original failure suppressed')
                    self.assertEqual(capture.result()['original_validation_roles'],{} if foreign else capture.rows)
                    if foreign:self.assertIsNone(obs.registry.describe(primary[0]))
                    self.assertFalse((root/F.INNER).exists());self.assertIsNone(sys.gettrace())

class LiveBootstrapControls(unittest.TestCase):
    def test_actual_selected_v2_private_member_and_old_schema_denied(self):
        with tempfile.TemporaryDirectory(dir=OUT)as directory:
            root=Path(directory);obs=observation(root)
            paths={key:root/key for key in ('harness','serial-install','serial-boot')}
            for key,path in paths.items():path.write_bytes(b'ARCTIC-LIVE-SMOKE-EXIT=93\n'if key=='serial-install'else b'');path.chmod(0o600)
            IR.project_bootstrap(F,obs,paths,'f'*32,root/F.BOOTSTRAP)
            value=F.strict_json((root/F.BOOTSTRAP).read_bytes())
            self.assertEqual(value['schema'],'arctic-native-bootstrap-observation-v2')
            self.assertEqual(value['live_bootstrap']['live_smoke_exit'],'nonzero')
            retained=F.private_member(obs.scanner,root/F.BOOTSTRAP,F.BOOTSTRAP,'bootstrap-observation')
            self.assertEqual(retained[0],(root/F.BOOTSTRAP).read_bytes())
            value.pop('live_bootstrap');value['schema']='arctic-native-bootstrap-observation-v1'
            (root/F.BOOTSTRAP).write_bytes(F.encode_json(value))
            with self.assertRaises(ValueError):F.private_member(obs.scanner,root/F.BOOTSTRAP,F.BOOTSTRAP,'bootstrap-observation')
    def test_actual_selected_B_foreign_sameCode_globals_denied_before_projection(self):
        with tempfile.TemporaryDirectory(dir=OUT)as directory:
            root=Path(directory);obs=observation(root);B=F.BOOTSTRAP_OBSERVER;original=B.closed
            foreign=types.FunctionType(original.__code__,dict(original.__globals__),original.__name__,original.__defaults__,original.__closure__)
            with mock.patch.object(B,'closed',foreign):
                with self.assertRaisesRegex(ValueError,'^Closed Native bootstrap actual module identity differs'):
                    IR.bind_bootstrap(F,obs.public)
            IR.bind_bootstrap(F,obs.public)

if __name__=='__main__':unittest.main(verbosity=2)
