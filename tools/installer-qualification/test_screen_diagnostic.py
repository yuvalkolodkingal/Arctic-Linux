"""Private synthetic failure-path controls; no VM or ISO qualification."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('installer_partial_control', HERE / 'screen-diagnostic.py')
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)
# A real, tiny static PNG fixture, copied unchanged. It is not a VM capture.
PNG = bytes.fromhex('89504e470d0a1a0a0000000d4948445200000001000000010802000000907753de0000000c49444154789c6360000000020001e221bc330000000049454e44ae426082')


class PartialDiagnostic(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='arctic-partial-control-')
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'; self.source.mkdir()
        self.out = self.root / 'partial'

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, data):
        path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
        return path

    def reject(self, data=b'private-person@example.invalid\n'):
        return self.put('host/serial.log', data)

    def test_idle_all_twelve_original_images_report_and_uart_preserved(self):
        c = D.load('idle_fixture_inventory', HERE / 'contract.py')
        self.reject()
        for name in c.REQUIRED_IMAGES:self.put(name, PNG)
        self.put('installer/installer-report.json', b'{"status":"passed","release_acceptance":false}\n')
        before = {p.relative_to(self.source).as_posix():p.read_bytes() for p in self.source.rglob('*') if p.is_file()}
        r = D.prepare(self.source, self.out, 'idle')
        self.assertTrue(r['all_required_images_present']);self.assertFalse(r['release_acceptance']);self.assertFalse(r['image_qualified'])
        self.assertEqual(len(r['required_images']), 12)
        self.assertFalse((self.out/'host/serial.log').exists())
        for name, data in before.items():
            self.assertEqual((self.source/name).read_bytes(),data)
            if name in r['files']:self.assertEqual((self.out/name).read_bytes(),data)
        self.assertNotIn('private-person', json.dumps(r));self.assertNotIn('example.invalid',json.dumps(r))
        self.assertIsNone(r['rejected_members'][0]['matches'][0]['public_candidate_sha256'])
        self.assertEqual(r['files']['installer/baseline.png']['original_sha256'],hashlib.sha256(PNG).hexdigest())
        D.scanner().external_text((self.out/'diagnostic-partial.json').read_bytes())

    def test_active_all_seven_original_images_retained_failed_report_unchanged(self):
        c = D.load('active_fixture_inventory', HERE / 'active-contract.py');self.reject()
        for name in c.REQUIRED_IMAGES:self.put(name,PNG)
        report=b'{"status":"failed","release_acceptance":false}\n';self.put('installer/installer-report.json',report)
        r=D.prepare(self.source,self.out,'active')
        self.assertEqual(len(r['required_images']),7);self.assertTrue(r['all_required_images_present']);self.assertFalse(r['image_qualified'])
        self.assertEqual((self.out/'installer/installer-report.json').read_bytes(),report)

    def test_fixed_getty_candidate_remains_strictly_rejected(self):
        m=D.scanner();data=b'getty@tty2.service\n';passed,reason,rows=D.screened_text(m,data)
        self.assertFalse(passed);self.assertEqual(reason,'sensitive-text');self.assertEqual(rows[0]['public_candidate'],'getty-template-tty2')
        self.assertEqual(rows[0]['public_candidate_sha256'],hashlib.sha256(b'getty@tty2.service').hexdigest())
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):m.external_text(data)

    def test_decorated_or_embedded_candidate_never_attests_original_literal(self):
        for data in [b'getty@tty\x1b[31m2\x1b[0m.service\n',b'xgetty@tty2.service\n',b'getty@tty2.service.private\n']:
            with self.subTest(data=data):
                passed,_,rows=D.screened_text(D.scanner(),data);self.assertFalse(passed)
                self.assertEqual(rows[0]['public_candidate'],'unknown');self.assertIsNone(rows[0]['public_candidate_sha256'])

    def test_unknown_unit_and_named_secret_only_typed_unknown(self):
        for data in [b'private-name@private.instance.service\n',b'password=DO_NOT_EXPORT_PRIVATE_SENTINEL\n']:
            passed,_,rows=D.screened_text(D.scanner(),data);self.assertFalse(passed);self.assertEqual(rows[0]['public_candidate'],'unknown')
            self.assertIsNone(rows[0]['public_candidate_sha256']);self.assertNotIn('PRIVATE_SENTINEL',json.dumps(rows))

    def test_strict_safe_source_cannot_become_partial_success(self):
        self.put('host/serial.log',b'Only public plain diagnostics\n')
        with self.assertRaisesRegex(RuntimeError,'requires a strict rejected original'):D.prepare(self.source,self.out,'idle')
        self.assertFalse(self.out.exists())

    def test_unknown_files_and_unscreened_binary_prefixes_not_exported(self):
        self.reject();self.put('unknown-private-name.log',b'password=PRIVATE_UNKNOWN\n')
        self.put('host/installer-port.log.bounded-prefix.bin',b'password=PRIVATE_BINARY\n')
        r=D.prepare(self.source,self.out,'idle');self.assertFalse((self.out/'unknown-private-name.log').exists())
        self.assertFalse((self.out/'host/installer-port.log.bounded-prefix.bin').exists())
        self.assertNotIn('PRIVATE_UNKNOWN',json.dumps(r));self.assertNotIn('PRIVATE_BINARY',json.dumps(r))

    def test_symlink_original_fails_before_any_output(self):
        self.reject();target=self.root/'foreign';target.write_bytes(b'{}\n');p=self.source/'execution.json';p.symlink_to(target)
        with self.assertRaises(OSError):D.prepare(self.source,self.out,'idle')
        self.assertFalse(self.out.exists());self.assertEqual(target.read_bytes(),b'{}\n')

    def test_hardlink_and_fifo_originals_fail_closed(self):
        for mode in ['link','fifo']:
            with self.subTest(mode=mode):
                p=self.source/'execution.json'
                if mode=='link':
                    target=self.root/'linked';target.write_bytes(b'{}\n');os.link(target,p)
                else:os.mkfifo(p)
                self.reject()
                with self.assertRaisesRegex(RuntimeError,'type owner or bounds'):D.prepare(self.source,self.out,'idle')
                self.assertFalse(self.out.exists());p.unlink()

    def test_replaced_original_name_is_rejected(self):
        p=self.put('execution.json',b'{"safe":true}\n');replacement=self.root/'replacement';replacement.write_bytes(p.read_bytes());self.reject()
        original_read=os.read;done=False
        def swap(fd,count):
            nonlocal done
            data=original_read(fd,count)
            if not done and data:
                done=True;os.replace(replacement,p)
            return data
        with mock.patch.object(D.os,'read',side_effect=swap),self.assertRaisesRegex(RuntimeError,'changed during read|name was replaced'):D.prepare(self.source,self.out,'idle')
        self.assertFalse(self.out.exists())

    def test_foreign_owner_and_oversize_are_rejected(self):
        p=self.put('execution.json',b'{}\n');self.reject()
        if os.geteuid()==0:
            os.chown(p,1,-1)
            try:
                with self.assertRaisesRegex(RuntimeError,'type owner or bounds'):D.prepare(self.source,self.out,'idle')
            finally:os.chown(p,0,-1)
        with mock.patch.object(D,'MAX_MEMBER',1),self.assertRaisesRegex(RuntimeError,'bounds'):D.prepare(self.source,self.out,'idle')

    def test_unused_output_and_exact_scanner_binding_required(self):
        self.reject();self.out.mkdir()
        with self.assertRaises(FileExistsError):D.prepare(self.source,self.out,'idle')
        with mock.patch.object(D,'SCANNER_SHA256','0'*64),self.assertRaisesRegex(RuntimeError,'source binding'):D.scanner()

    def test_scanner_executes_verified_snapshot_after_path_replacement(self):
        original = (HERE.parent/'native-functional/screen-evidence.py').read_bytes()
        installer = self.root/'tools/installer-qualification';installer.mkdir(parents=True)
        path = self.root/'tools/native-functional/screen-evidence.py';path.parent.mkdir()
        path.write_bytes(original)
        replacement = b"raise RuntimeError('UNVALIDATED_SCANNER_EXECUTED')\n"
        read_bytes = Path.read_bytes;reads = []
        def swap(p):
            raw = read_bytes(p)
            if p == path:
                reads.append(raw);path.write_bytes(replacement)
            return raw
        with mock.patch.object(D,'HERE',installer),mock.patch.object(Path,'read_bytes',swap):
            m = D.scanner()
        self.assertEqual(reads,[original]);self.assertEqual(path.read_bytes(),replacement)
        self.assertEqual(m.__file__,str(path))
        with contextlib.redirect_stdout(io.StringIO()),self.assertRaises(RuntimeError):
            m.external_text(b'private-person@example.invalid\n')
        self.assertTrue(callable(m.external_text))

    def test_original_cancellation_and_scanner_hook_preserved(self):
        m=D.scanner();prior=m.diagnose_sensitive_match;exc=KeyboardInterrupt()
        with mock.patch.object(m,'external_text',side_effect=exc),self.assertRaises(KeyboardInterrupt) as caught:D.screened_text(m,b'plain')
        self.assertIs(caught.exception,exc);self.assertIs(m.diagnose_sensitive_match,prior)

    def test_close_failure_retains_existing_primary_object(self):
        primary=KeyboardInterrupt()
        with mock.patch.object(D.os,'close',side_effect=OSError('close failure')):
            with self.assertRaises(KeyboardInterrupt) as caught:
                try:raise primary
                finally:D.close_preserving(123)
            self.assertIs(caught.exception,primary)
            with self.assertRaises(OSError):D.close_preserving(123)


if __name__=='__main__':unittest.main(verbosity=2)
