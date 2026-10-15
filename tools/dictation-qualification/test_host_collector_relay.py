"""Fixed-code-only host relay for guest dictation collector setup failures."""
import ast
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'dictation_runner_collector_relay', Path(__file__).with_name('runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

ROOT = Path(__file__).resolve().parents[2]
PARENT = 'a25d6c0e9e457a783e2de8f223028eaf945eee84'


def restore_collector_host_relay(text):
    """Remove exactly this relay layer and recover its reviewed parent bytes."""
    constants = 'COLLECTOR_SETUP_STAGES = ('
    helper = 'def relay_collector_diagnostic(vm, phase):'
    call = '                relay_collector_diagnostic(vm, phase)\n'
    present = (constants in text, helper in text, call in text)
    if not any(present):
        return text
    assert all(present)
    assert text.count(constants) == text.count(helper) == text.count(call) == 1
    start = text.index(constants)
    end = text.index('\ndef diagnostic(', start)
    text = text[:start] + text[end:]
    start = text.index(helper)
    end = text.index('def launch_diagnostic_read(', start)
    text = text[:start] + text[end:]
    return text.replace(call, '', 1)


class CollectorHostRelayControls(unittest.TestCase):
    def test_fixed_inventory_matches_guest_source(self):
        tree = ast.parse(Path(__file__).with_name('guest_check.py').read_text())
        assignments = {
            node.targets[0].id: node.value
            for node in tree.body
            if isinstance(node, ast.Assign) and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id in {'COLLECTOR_SETUP_STAGES', 'COLLECTOR_ERROR_TYPES'}
        }
        stages = ast.literal_eval(assignments['COLLECTOR_SETUP_STAGES'])
        labels = tuple(
            item.elts[1].value for item in assignments['COLLECTOR_ERROR_TYPES'].elts)
        self.assertEqual(runner.COLLECTOR_SETUP_STAGES, stages)
        self.assertEqual(runner.COLLECTOR_ERROR_LABELS, labels)
        self.assertEqual(
            runner.COLLECTOR_DIAGNOSTIC_CODES,
            frozenset({'collector-unknown'} | {
                'collector-' + stage + '-' + label
                for stage in stages for label in labels}))

    def relay(self, serial, phase='recovered-offline'):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'serial-boot.log').write_bytes(serial)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                runner.relay_collector_diagnostic(root, phase)
            return output.getvalue()

    def test_every_finite_guest_code_relays_without_payload(self):
        for code in sorted(runner.COLLECTOR_DIAGNOSTIC_CODES):
            with self.subTest(code=code):
                record = json.dumps(
                    {'code': code, 'release_acceptance': False},
                    sort_keys=True, separators=(',', ':')).encode('ascii')
                output = self.relay(
                    b'private transcript before\n'
                    b'ARCTIC-DICTATION-COLLECTOR-ERROR ' + record + b'\n'
                    b'private transcript after\n')
                self.assertEqual(
                    output,
                    'ARCTIC-DICTATION-HOST-FAILURE recovered-offline collector '
                    + code + '\n')
                self.assertNotIn('private', output)

    def test_untrusted_or_duplicate_records_cannot_escape_fixed_projection(self):
        records = (
            b'ARCTIC-DICTATION-COLLECTOR-ERROR '
            b'{"code":"private transcript","release_acceptance":false}\n',
            b'ARCTIC-DICTATION-COLLECTOR-ERROR '
            b'{"code":"collector-integration-invalid","release_acceptance":true}\n',
            b'ARCTIC-DICTATION-COLLECTOR-ERROR '
            b'{"code":"collector-integration-invalid","extra":"private",'
            b'"release_acceptance":false}\n',
            b'ARCTIC-DICTATION-COLLECTOR-ERROR '
            b'{"code":"collector-integration-invalid","release_acceptance":false}\n'
            b'ARCTIC-DICTATION-COLLECTOR-ERROR '
            b'{"code":"collector-integration-invalid","release_acceptance":false}\n',
        )
        for serial in records:
            with self.subTest(serial=serial):
                output = self.relay(serial)
                self.assertEqual(
                    output,
                    'ARCTIC-DICTATION-HOST-FAILURE recovered-offline collector '
                    'collector-invalid-record\n')
                self.assertNotIn('private', output)

    def test_malformed_foreign_bytes_and_missing_file_fail_closed(self):
        for serial in (
                b'ARCTIC-DICTATION-COLLECTOR-ERROR {\xff}\n',
                b'ARCTIC-DICTATION-COLLECTOR-ERROR '
                b'{"code":"collector-integration-invalid",'
                b'"code":"private","release_acceptance":false}\n',
                b'ARCTIC-DICTATION-COLLECTOR-ERROR {}',
                b'private transcript only\n'):
            with self.subTest(serial=serial):
                output = self.relay(serial)
                self.assertNotIn('private', output)
                self.assertIn(output, (
                    '',
                    'ARCTIC-DICTATION-HOST-FAILURE recovered-offline collector '
                    'collector-invalid-record\n'))
        with tempfile.TemporaryDirectory() as tmp:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                runner.relay_collector_diagnostic(Path(tmp), 'recovered-offline')
            self.assertEqual(output.getvalue(), '')

    def test_non_phase_context_cannot_relay(self):
        record = (b'ARCTIC-DICTATION-COLLECTOR-ERROR '
                  b'{"code":"collector-integration-invalid",'
                  b'"release_acceptance":false}\n')
        self.assertEqual(self.relay(record, phase='private-phase'), '')


if __name__ == '__main__':
    unittest.main()
