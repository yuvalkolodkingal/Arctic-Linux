"""Keep failed Native receipts while rejecting a malformed private UART."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('failed_native_uart_screen', HERE / 'screen-evidence.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


def execution(status='failed_or_unrun'):
    return dict(status=status, error='closed native gate failure', source_image_run=38735141923,
        execution_checker_head='1' * 40, release_acceptance=False,
        checker=dict(method='native-functional', checker_sha256='2' * 64,
            native_source_sha256='3' * 64, release_acceptance=False))


class FailedNativeUARTScreening(unittest.TestCase):
    def fixture(self, root, *, status='failed_or_unrun', member='harness/serial-install.log'):
        source = root / 'source'
        (source / 'harness').mkdir(parents=True)
        (source / 'execution.json').write_text(json.dumps(execution(status), sort_keys=True) + '\n')
        (source / 'harness/native-host-frame-live.json').write_text(
            '{"release_acceptance":false,"status":"captured"}\n')
        raw = b'private UART prefix\n\xe2broken continuation\npassword=must-not-upload\n'
        path = source / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        return source, raw

    def test_failed_run_omits_only_invalid_uart_and_keeps_bounded_receipts(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, raw = self.fixture(root); target = root / 'upload'
            with contextlib.redirect_stdout(io.StringIO()) as output:
                S.screen(source, target)
            self.assertEqual(output.getvalue(),
                'ARCTIC-EVIDENCE-DIAGNOSTIC=utf8-native-live-uart-rejection-invalid-utf8\n')
            self.assertFalse((target / 'harness/serial-install.log').exists())
            self.assertEqual((source / 'harness/serial-install.log').read_bytes(), raw)
            self.assertEqual((target / 'harness/native-host-frame-live.json').read_text(),
                '{"release_acceptance":false,"status":"captured"}\n')
            manifest = json.loads((target / 'upload-screening.json').read_text())
            rejection = manifest['rejected_files']['harness/serial-install.log']
            self.assertEqual(rejection, dict(role='native-live-uart', reason='invalid-utf8',
                original_sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), uploaded=False,
                release_acceptance=False))
            uploaded = b''.join(p.read_bytes() for p in target.rglob('*') if p.is_file())
            self.assertNotIn(b'password=must-not-upload', uploaded)

    def test_success_or_unknown_text_member_keeps_original_atomic_rejection(self):
        for status, member in (
            ('limited_native_live_installed_smoke_passed_pending_visual_audio_review',
             'harness/serial-install.log'),
            ('failed_or_unrun', 'native-harness.log'),
        ):
            with self.subTest(status=status, member=member), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source, raw = self.fixture(root, status=status, member=member)
                target = root / 'upload'
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(UnicodeDecodeError) as error:
                    S.screen(source, target)
                self.assertEqual(error.exception.object, raw)
                self.assertFalse(target.exists())

    def test_external_original_mode_never_omits_invalid_uart(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source, raw = self.fixture(root); target = root / 'upload'
            with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(UnicodeDecodeError) as error:
                S.screen(source, target, external=True)
            self.assertEqual(error.exception.object, raw)
            self.assertFalse(target.exists())

    def test_malformed_or_unbound_failure_receipt_cannot_enable_omission(self):
        variants = (
            '{"status":"failed_or_unrun","status":"failed_or_unrun"}\n',
            json.dumps(dict(execution(), execution_checker_head='not-a-commit')) + '\n',
            json.dumps(dict(execution(), checker={'method': 'other', 'release_acceptance': False})) + '\n',
            json.dumps(dict(execution(), release_acceptance=True)) + '\n',
        )
        for value in variants:
            with self.subTest(value=value), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source, raw = self.fixture(root)
                (source / 'execution.json').write_text(value)
                target = root / 'upload'
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(UnicodeDecodeError):
                    S.screen(source, target)
                self.assertFalse(target.exists())
                self.assertEqual((source / 'harness/serial-install.log').read_bytes(), raw)


if __name__ == '__main__':
    unittest.main()
