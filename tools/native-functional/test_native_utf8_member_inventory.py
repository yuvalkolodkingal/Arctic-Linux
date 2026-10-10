"""Diagnostic labels only: invalid original UTF-8 and all privacy gates fail."""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


def load():
    path = Path(__file__).with_name('screen-evidence.py')
    spec = importlib.util.spec_from_file_location('native_utf8_member_inventory', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


S = load()


class NativeUTF8MemberInventory(unittest.TestCase):
    def label(self, relative):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            S.diagnose_invalid_utf8_member(relative)
        return output.getvalue()

    def test_fixed_host_harness_and_guest_receipt_writers_get_only_literal_roles(self):
        for path, role in (
            ('vm-prepared-image-id.txt', 'native-tool-image-id'),
            ('taskbar-display-capabilities.txt', 'native-display-capabilities'),
            ('harness/vm-toolchain.txt', 'native-vm-toolchain'),
            ('harness/native-audio-capabilities.txt', 'native-audio-capabilities'),
            ('harness/test-install-stage.log', 'native-install-driver'),
            ('harness/native-stop-install.json', 'native-live-stop'),
            ('native-installed/0-controlled-renderer-trials.json', 'native-installed-renderer-trial-receipt'),
            ('native-live/serial-native-provenance.json', 'native-live-provenance'),
            ('taskbar/taskbar-state.json', 'native-taskbar-state'),
            ('native-live/extracted zip/Unicode-\u05e9.txt', 'native-live-archive-unicode-extract'),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.label(path), 'ARCTIC-EVIDENCE-DIAGNOSTIC=utf8-' + role + '-rejection-invalid-utf8\n')
                self.assertNotIn(path, self.label(path))

    def test_numbered_source_launch_inventory_is_finite_exact_and_never_exports_index(self):
        for stage in ('live', 'installed'):
            for index in range(130):
                self.assertEqual(self.label('native-' + stage + '/gui-launch-' + str(index) + '.log'),
                    'ARCTIC-EVIDENCE-DIAGNOSTIC=utf8-native-' + stage + '-gui-launch-rejection-invalid-utf8\n')
        for path in ('native-live/gui-launch-130.log', 'native-live/gui-launch-00.log',
                     'native-live/gui-launch--1.log', 'native-live/gui-launch-1.LOG',
                     'native-live/gui-launch-1.log/extra', 'native-live/private/gui-launch-1.log',
                     'native-live/../native-live/gui-launch-1.log', 'native-live/gui-launch-1.log\x00',
                     'customer-private.json', 'native-other/report.json', 'native-live/config/private.json'):
            with self.subTest(path=path):
                self.assertEqual(self.label(path), 'ARCTIC-EVIDENCE-DIAGNOSTIC=utf8-other-text-rejection-invalid-utf8\n')
        class Hostile(str):
            def __hash__(self): raise AssertionError('private object inspected')
        self.assertEqual(self.label(Hostile('native-live/report.json')),
            'ARCTIC-EVIDENCE-DIAGNOSTIC=utf8-other-text-rejection-invalid-utf8\n')

    def test_actual_decoder_exception_object_and_original_bytes_survive_optional_role_output(self):
        raw = b'\xdaoriginal unreadable bytes\xff\x00'
        error = None
        try:
            raw.decode('utf-8')
        except UnicodeDecodeError as caught:
            error = caught
        self.assertIsNotNone(error)
        original_object = error.object
        class Undecodable(bytes):
            def decode(self, *args, **kwargs): raise error
        for observation_failure in (None, RuntimeError('private optional metadata'), KeyboardInterrupt(), SystemExit(7)):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source = root/'source'; target = root/'target'; source.mkdir(); target.mkdir()
                original = source/'taskbar-display-capabilities.txt'; original.write_bytes(raw)
                with patch.object(Path, 'read_bytes', return_value=Undecodable(raw)), \
                        patch.object(S, 'diagnose_invalid_utf8_member', side_effect=observation_failure), \
                        self.assertRaises(UnicodeDecodeError) as observed:
                    S.copy_screened(source, target)
                self.assertIs(observed.exception, error)
                self.assertIs(observed.exception.object, original_object)
                self.assertEqual(observed.exception.object, raw)
                self.assertEqual((error.encoding, error.start, error.end, error.reason),
                    ('utf-8', 0, 1, 'invalid continuation byte'))
                self.assertEqual(original.read_bytes(), raw)
                self.assertEqual(list(target.iterdir()), [])

    def test_full_atomic_screen_fails_original_decode_and_removes_partial_export(self):
        raw = b'\xdaoriginal invalid bytes'
        for relative in ('harness/vm-toolchain.txt', 'native-live/gui-launch-7.log', 'native-live/report.json'):
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); source = root/'source'; source.mkdir()
                (source/'a-valid.json').write_text('{"status":"unqualified"}')
                member = source/relative; member.parent.mkdir(parents=True, exist_ok=True); member.write_bytes(raw)
                target = root/'upload'
                with contextlib.redirect_stdout(io.StringIO()) as output, self.assertRaises(UnicodeDecodeError) as error:
                    S.screen(source, target)
                self.assertEqual(error.exception.object, raw)
                self.assertFalse(target.exists())
                self.assertEqual(sorted(p.name for p in root.iterdir()), ['source'])
                self.assertEqual(member.read_bytes(), raw)
                self.assertIn('rejection-invalid-utf8', output.getvalue())
                self.assertNotIn(relative, output.getvalue())

    def test_external_sensitive_text_keeps_strict_original_rejection_for_every_role(self):
        private = b'authorization: PrivateFixtureSecretOnly'
        for relative in ('native-live/gui-launch-1.log', 'native-live/report.json', 'harness/vm-toolchain.txt'):
            with tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary); source=root/'source'; source.mkdir(); member=source/relative
                member.parent.mkdir(parents=True, exist_ok=True); member.write_bytes(private)
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(RuntimeError, '^Sensitive text in external evidence$'):
                    S.screen(source, root/'upload', external=True)
                self.assertFalse((root/'upload').exists())
                self.assertEqual(member.read_bytes(), private)


if __name__ == '__main__':
    unittest.main()
