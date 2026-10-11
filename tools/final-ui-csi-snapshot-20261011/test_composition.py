"""Small fresh composition controls; accepted eleven component controls reused."""
import ast,gzip,hashlib,importlib.util,json,os,sys,tempfile,unittest,copy
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
        raw=(C.ROOT/'.github/workflows/final-ui-csi-snapshot-20261011.yml').read_text()
        self.assertIn("if: always() && steps.screened.outputs.upload_admitted == 'true'",raw)
        self.assertEqual(raw.count('actions/upload-artifact@v4'),1)
        self.assertIn('python3-pil tesseract-ocr tesseract-ocr-eng',raw)
        self.assertIn('timeout-minutes: 120',raw)
        self.assertEqual(C.BASE,'650f0d3e0ecf3e10352b6ced4b64785abced3514')
        self.assertEqual(len(C.ADDITIONS),10);self.assertEqual(len(C.FILES),36)
        self.assertNotIn(C.MARKER,C.ADDITIONS)

    def fixture(self):
        observed,published,state,helper,originals,buffers=R.main_adapter(self.value())
        scanner=C.load(C.ROOT/C.COMPONENT_PREFIX/'scanner.py','synthetic_UI_selected_scanner',
            self.value()['execution_files'][C.COMPONENT_PREFIX+'scanner.py'])
        raw=buffers[C.COMPONENT_PREFIX+'scanner.py'];match=buffers[C.COMPONENT_PREFIX+'match-diagnostic.py']
        context=dict(schema='arctic-final-installed-ui-context-v1',nonce='0'*32,execution_sha='0'*40,
            source_sha=C.IMAGE['source_sha'],iso_sha256=C.IMAGE['sha256'],native_sha256='0'*64,ui_sha256='0'*64)
        function=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)and n.name=='reject_sensitive_match'][0]
        line=[n for n in ast.walk(function)if isinstance(n,ast.Raise)][0].lineno
        finite=dict(schema='arctic-ui-strict-original-source-failure-v1',
            original_source_site=dict(source='original-scanner',source_sha256=helper.SCANNER_SHA,
                function='reject_sensitive_match',source_line=line,site_kind='raise',
                fixed_assertion_label='Sensitive text in external evidence'),original_uart_stage='live',
            same_rejected_match=dict(regex='exact-scanner-regex',offsets='exact-scanner-span',
                mapping='exact-source-view',source_rule='external-rule-004',
                candidate_reason='not-catalogued-public-literal',family_reason='not-known-public-family-fragment',
                privacy_admitted=False,runtime_cause_proven=False,operand_value_or_digest_exported=False),
            actual_raising_Source_Code_globals_owned=True,exception_unchanged=True,
            actual_runtime_cause_proven=False,complete_uart_admitted=False,release_acceptance=False)
        record=dict(schema='arctic-ui-private-snapshot-v1',context=context,finite=finite,
            members={'serial-install.log':1},complete_uart_admitted=False,actual_runtime_cause_proven=False,
            release_acceptance=False)
        return observed,published,helper,originals,buffers,scanner,raw,match,context,record

    def test_original_screen_selects_corrected_source_and_preserves_actual_gzip(self):
        observed,published,helper,originals,buffers,scanner,raw,match,context,record=self.fixture()
        self.assertIs(observed.screen.__code__,published.screen.__code__)
        acquired=[];before=sys.getprofile()
        def profile(frame,event,arg):
            if event=='call'and frame.f_code is originals.read_regular.__code__:
                acquired.append(Path(frame.f_locals['path']))
        with tempfile.TemporaryDirectory()as directory:
            source=Path(directory)/'source';source.mkdir();target=Path(directory)/'screened'
            (source/'host-status.json').write_text('{"status":"synthetic-Source-control"}\n')
            wire=b'\x1b[0;32mordinary synthetic Source text\x1b[0m\n';packed=gzip.compress(wire,mtime=0)
            (source/'serial-install.log.gz').write_bytes(packed)
            try:sys.setprofile(profile);observed.screen(source,target)
            finally:sys.setprofile(before)
            self.assertIn(C.ROOT/C.COMPONENT_PREFIX/'scanner.py',acquired)
            self.assertNotIn(C.ROOT/'tools/native-functional/screen-evidence.py',acquired)
            self.assertEqual((target/'serial-install.log.gz').read_bytes(),packed)
            private=Path(directory)/'sensitive';private.mkdir()
            (private/'host-status.json').write_text('{"status":"synthetic-Source-control"}\n')
            (private/'serial-install.log.gz').write_bytes(gzip.compress(b'private\x1b[0;32m-person@example.net\n',mtime=0))
            with self.assertRaises(RuntimeError):observed.screen(private,Path(directory)/'denied')

    def test_selected_snapshot_type_gate_context_and_no_uart_reads(self):
        observed,published,helper,originals,buffers,scanner,raw,match,context,record=self.fixture()
        with tempfile.TemporaryDirectory()as directory:
            holder=Path(directory);os.chmod(holder,0o700)
            metadata=holder/'snapshot.json'
            for scalar,status in((record['finite']['original_source_site']['source_line'],'validated'),
                    (float(record['finite']['original_source_site']['source_line']),'invalid'),(True,'invalid')):
                candidate=copy.deepcopy(record);candidate['finite']['original_source_site']['source_line']=scalar
                metadata.write_text(json.dumps(candidate)+'\n');metadata.chmod(0o600)
                result=json.loads(helper.finite_snapshot_observation(holder,context,published.C,scanner,raw,match))
                self.assertEqual(result['status'],status)
                self.assertIs(result['serialized_Source_observation_reauthenticated_runtime_Code'],False)
                self.assertIs(result['raw_private_exported'],False)
                if status=='invalid':self.assertIsNone(result['finite'])
            candidate=copy.deepcopy(record);candidate['context']['execution_sha']='1'*40
            metadata.write_text(json.dumps(candidate)+'\n')
            result=json.loads(helper.finite_snapshot_observation(holder,context,published.C,scanner,raw,match))
            self.assertEqual(result['status'],'invalid')
            # No raw UART file exists anywhere in this synthetic holder.
            self.assertEqual(set(p.name for p in holder.iterdir()),{'snapshot.json'})

    def test_conditional_new_member_requires_failed_original_screening_status(self):
        observed,published,helper,originals,buffers,scanner,raw,match,context,record=self.fixture()
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);holder=root/'private';holder.mkdir(mode=0o700)
            metadata=holder/'snapshot.json';metadata.write_text(json.dumps(record)+'\n');metadata.chmod(0o600)
            for index,(status,phase,wanted)in enumerate((('failed','original-screening',True),
                    ('passed','original-screening',False),('failed','harness',False))):
                source=root/('source-'+str(index));source.mkdir()
                (source/'host-status.json').write_text(json.dumps(dict(status=status,phase=phase,context=context))+'\n')
                target=root/('screened-'+str(index))
                helper.screen(observed.screen,source,target,holder,published.C,
                    buffers[C.ORIGINAL_PREFIX+'common.py'],scanner,raw,match)
                member=target/'strict-original-failure-observation.json'
                self.assertEqual(member.exists(),wanted)
                if wanted:self.assertEqual(json.loads(member.read_bytes())['status'],'validated')

if __name__=='__main__':unittest.main()
