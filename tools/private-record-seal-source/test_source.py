#!/usr/bin/env python3
import contextlib,hashlib,importlib.util,io,json,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
spec=importlib.util.spec_from_file_location('private_record_seal',HERE/'seal.py')
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
RECIPIENT='age1'+'q'*58
RECIPIENT_SHA=hashlib.sha256((RECIPIENT+'\n').encode()).hexdigest()
class Tests(unittest.TestCase):
    def stub(self,root):
        path=root/'age'
        path.write_text("""#!/usr/bin/env python3
import hashlib,sys
if sys.argv[1:]==['--version']:
 print('v1.2.1');raise SystemExit
if len(sys.argv)==4 and sys.argv[1:3]==['--encrypt','--recipient']:
 data=sys.stdin.buffer.read()
 sys.stdout.buffer.write(b'age-encryption.org/v1\\n'+hashlib.sha256(data).digest()+b'X'*96)
 raise SystemExit
raise SystemExit(2)
""")
        path.chmod(0o700)
        raw=path.read_bytes()
        old=S.AGE_BINARY_SHA256;S.AGE_BINARY_SHA256=hashlib.sha256(raw).hexdigest()
        return path,old
    def test_source_recipient_state_is_closed(self):
        manifest=json.loads((HERE/'source-manifest.json').read_text())
        self.assertFalse(manifest['release_acceptance'])
        if manifest['ready']:
            self.assertTrue(manifest['recipient_generated_outside_github'])
            self.assertEqual(S.validate_recipient(manifest['recipient'],manifest['recipient_sha256']),manifest['recipient'])
        else:
            self.assertIsNone(manifest['recipient']);self.assertIsNone(manifest['recipient_sha256'])
            self.assertFalse(manifest['recipient_generated_outside_github'])
    def test_closed_stage_labels_are_finite_and_foreign_errors_fail_closed(self):
        self.assertEqual(S.closed_failure_label(RuntimeError('private-value')),S.SEAL_STAGE_UNKNOWN)
        for label in S.SEAL_STAGE_LABELS:
            error=S.SealStageError(label)
            self.assertEqual(error.args,(S.SEAL_FAILURE_MESSAGE,))
            self.assertEqual(S.closed_failure_label(error),label)
            self.assertRegex(label,r'\Aprivate-seal-stage-[a-z-]+\Z')
        with self.assertRaises(S.SealStageError) as caught:
            S.exact_record(RuntimeError('private-value'),{},b'private-value',b'',HERE/'missing')
        self.assertEqual(S.closed_failure_label(caught.exception),'private-seal-stage-finite-contract')
        self.assertNotIn('private-value',str(caught.exception))
    def test_closed_label_does_not_inspect_foreign_exception(self):
        class Foreign(BaseException):
            def __str__(self):raise AssertionError('foreign exception was stringified')
        self.assertEqual(S.closed_failure_label(Foreign()),S.SEAL_STAGE_UNKNOWN)
    def test_recipient_is_exact_and_pinned(self):
        self.assertEqual(S.validate_recipient(RECIPIENT,RECIPIENT_SHA),RECIPIENT)
        for bad in ('age1'+'q'*57,'AGE1'+'q'*58,'age1'+'b'*58):
            with self.assertRaises(RuntimeError):S.validate_recipient(bad,RECIPIENT_SHA)
    def test_exact_owned_scanner_record_only(self):
        scanner_raw=(ROOT/'tools/bounded-complete-csi-source/scanner.py').read_bytes()
        diagnostic_raw=(ROOT/'tools/unit-record-observation-source/diagnostic.py').read_bytes()
        scanner=S.load(scanner_raw,ROOT/'tools/native-functional/screen-evidence.py','test_exact_scanner')
        original='prefix '+chr(27)+'[31mapp-example.desktop@autostart.service'+chr(27)+'[0m suffix'
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                scanner.external_text(original.encode())
        except RuntimeError as error:
            family={'schema':'arctic-unit-record-family-source-diagnostic-v1',
                'source_member_id':'serial-install-log','unit_family_id':'repo-xdg-autostart-unit',
                'record_family_id':'unknown','exact_repo_attested_unit_family':True,
                'exact_repo_attested_record_family':False,'privacy_admitted':False,
                'runtime_cause_proven':False,'operand_value_or_digest_exported':False,
                'release_acceptance':False}
            state={'finite':{'schema':'arctic-bios-strict-original-source-failure-v1',
                'original_records_stage':'live','actual_raising_Source_Code_globals_owned':True,
                'actual_runtime_cause_proven':False,'exception_unchanged':True,
                'privacy_admitted':False,'release_acceptance':False,
                'same_rejected_match':{'unit_record_family':family}},'context':{}}
            record=S.exact_record(error,state,scanner_raw,diagnostic_raw,
                ROOT/'tools/unit-record-observation-source/diagnostic.py')
        else:
            self.fail('Pinned scanner did not reject synthetic private unit')
        self.assertEqual(record,original.encode())
    def test_fixed_envelope_and_wipe(self):
        record=bytearray(b'private-value')
        value=S.envelope(record)
        self.assertEqual(len(value),S.ENVELOPE_BYTES)
        self.assertTrue(value.startswith(S.MAGIC+len(record).to_bytes(4,'big')+record))
        S.wipe(record);self.assertEqual(record,bytearray(len(record)))
    def test_encrypt_writes_ciphertext_and_closed_receipt_only(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);age,old=self.stub(root);out=root/'sealed'
            record=bytearray(b'private-value@autostart.service')
            stdout=io.StringIO();stderr=io.StringIO()
            try:
                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                    receipt=S.encrypt_record(age,RECIPIENT,RECIPIENT_SHA,record,out,{
                        'execution_commit':'1'*40,'source_commit':'2'*40,'image_sha256':'3'*64})
            finally:S.AGE_BINARY_SHA256=old
            self.assertEqual(stdout.getvalue(),'');self.assertEqual(stderr.getvalue(),'')
            self.assertEqual(record,bytearray(len(record)))
            self.assertEqual({p.name for p in out.iterdir()},{'record.age','receipt.json'})
            self.assertNotIn(b'private-value',(out/'record.age').read_bytes())
            public=(out/'receipt.json').read_bytes()
            self.assertNotIn(b'private-value',public);self.assertNotIn(b'plaintext_sha',public)
            self.assertFalse(receipt['plaintext_written_by_observer'])
            self.assertFalse(receipt['public_plaintext_artifact'])
            self.assertFalse(receipt['release_acceptance'])
    def test_failure_removes_partial_outputs_and_wipes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);age,old=self.stub(root);out=root/'sealed';record=bytearray(b'secret')
            age.write_text("#!/bin/sh\nif [ \"$1\" = \"--version\" ]; then echo v1.2.1; exit 0; fi\nexit 7\n");age.chmod(0o700)
            S.AGE_BINARY_SHA256=hashlib.sha256(age.read_bytes()).hexdigest()
            try:
                with self.assertRaises(Exception):
                    S.encrypt_record(age,RECIPIENT,RECIPIENT_SHA,record,out,{
                        'execution_commit':'1'*40,'source_commit':'2'*40,'image_sha256':'3'*64})
            finally:S.AGE_BINARY_SHA256=old
            self.assertEqual(record,bytearray(len(record)));self.assertFalse(out.exists())
if __name__=='__main__':unittest.main()
