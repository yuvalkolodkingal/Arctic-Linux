"""Adversarial controls for retained installer UART evidence; never VM evidence."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = load('installer_public_uart_projection', HERE / 'evidence.py')
S = load('installer_public_uart_screen', HERE.parent / 'native-functional/screen-evidence.py')


class Controls(unittest.TestCase):
    def test_unrelated_sensitive_boot_text_is_neither_retained_nor_hashed(self):
        request = {'schema': 'arctic-installer-request-v1', 'kind': 'vt-away', 'cycle': 0}
        end = {'schema': 'arctic-installer-port-end-v1', 'status': 'passed'}
        raw = (b'private.person@example.test\n'
               b'github_pat_private_dictionary_oracle_value\n'
               b'ARCTIC-CONSOLE-READY=' + b'a' * 32 + b' user=liveuser uid=1000\n' +
               b'boot account private.second@example.test\n' +
               ('ARCTIC-INSTALLER-REQUEST ' + json.dumps(request) + '\n').encode() +
               b'Transcript: private recognized words\n' +
               ('ARCTIC-INSTALLER-PORT-END ' + json.dumps(end) + '\n').encode())
        projected, receipt = E.public_uart_receipt(raw)
        self.assertNotIn(b'private', projected)
        self.assertNotIn(b'Transcript', projected)
        self.assertNotIn(E.digest(raw), receipt.values())
        self.assertEqual(projected.count(b'ARCTIC-UART-OMITTED='), 3)
        self.assertIn(b'ARCTIC-INSTALLER-REQUEST ', projected)
        self.assertIn(b'ARCTIC-INSTALLER-PORT-END ', projected)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); source = root / 'source'; source.mkdir()
            (source / 'serial.log').write_bytes(projected)
            S.screen_external(source, root / 'screened')
            self.assertEqual((root / 'screened/serial.log').read_bytes(), projected)
            hostile = root / 'hostile'; hostile.mkdir(); (hostile / 'serial.log').write_bytes(raw)
            with self.assertRaisesRegex(RuntimeError, '^Sensitive text in external evidence$'):
                S.screen_external(hostile, root / 'rejected')

    def test_omission_marker_preserves_installed_protocol_adjacency(self):
        report = {'schema': 'arctic-active-installed-boot-v1', 'release_acceptance': False}
        ready = 'ARCTIC-ACTIVE-INSTALLED-READY=' + 'b' * 32 + ' user=arcticqual uid=1000\n'
        record = 'ARCTIC-ACTIVE-INSTALLED ' + json.dumps(report) + '\n'
        adjacent = E.public_uart_projection((ready + record).encode(), installed=True)
        separated = E.public_uart_projection((ready + 'private unrelated line\n' + record).encode(), installed=True)
        self.assertNotIn(b'ARCTIC-UART-OMITTED=', adjacent)
        self.assertIn(b'ARCTIC-UART-OMITTED=1\n', separated)
        self.assertNotEqual(adjacent, separated)

    def test_malformed_or_unknown_protocol_records_fail_closed(self):
        for raw, installed in (
                (b'ARCTIC-INSTALLER-UNKNOWN {}\n', False),
                (b'ARCTIC-INSTALLER-REQUEST {"secret":"private"}', False),
                (b'ARCTIC-ACTIVE-INSTALLED-READY=wrong user=arcticqual uid=1000\n', True),
                (b'ARCTIC-ACTIVE-INSTALLED {"secret":"private"}', True)):
            with self.subTest(raw=raw, installed=installed), self.assertRaises((RuntimeError, ValueError)):
                E.public_uart_projection(raw, installed=installed)


if __name__ == '__main__':
    unittest.main()
