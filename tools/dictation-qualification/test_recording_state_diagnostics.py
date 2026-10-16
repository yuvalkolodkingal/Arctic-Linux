"""Closed diagnostics for a successful command that never publishes recording."""
import importlib.util
from pathlib import Path
import subprocess
from types import SimpleNamespace
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'direct_voxtype_recording_state', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


class RecordingStateDiagnostics(unittest.TestCase):
    ENGINE = (41, 123, Path('/owned/voxtype'))

    def checker(self, root, *, active=0, failed=1, engines=None, state='idle'):
        checker = guest.Checker.__new__(guest.Checker)
        checker.runtime = Path(root)
        checker._ready_engine = self.ENGINE
        checker.observe = mock.Mock(side_effect=guest.Invalid('private-timeout'))
        checker.engines = mock.Mock(
            return_value=[self.ENGINE] if engines is None else engines)
        checker.state = mock.Mock(return_value=state)
        checker.cmd = mock.Mock(side_effect=(
            SimpleNamespace(returncode=active), SimpleNamespace(returncode=failed)))
        return checker

    def substage(self, checker):
        with self.assertRaises(guest.TranscriptionStageFailure) as raised:
            checker.checked_recording_state()
        self.assertEqual(raised.exception.error_label, 'invalid')
        return raised.exception.failure_substage

    def test_service_process_and_identity_outcomes_are_closed(self):
        with tempfile.TemporaryDirectory() as root:
            cases = (
                (self.checker(root, active=3, failed=0), 601),
                (self.checker(root, active=3, failed=3), 602),
                (self.checker(root, engines=[]), 603),
                (self.checker(root, engines=[self.ENGINE, self.ENGINE]), 604),
                (self.checker(root, engines=[(42, 124, Path('/owned/voxtype'))]), 605),
            )
            for checker, expected in cases:
                with self.subTest(substage=expected):
                    self.assertEqual(self.substage(checker), expected)

    def test_native_state_outcomes_and_request_ack_are_closed(self):
        with tempfile.TemporaryDirectory() as root:
            runtime = Path(root) / 'voxtype'
            runtime.mkdir()
            for state, expected in (
                    ('stopped', 606), ('idle', 608), ('transcribing', 609),
                    ('streaming', 610), ('recording', 611)):
                with self.subTest(state=state):
                    self.assertEqual(
                        self.substage(self.checker(root, state=state)), expected)
            (runtime / 'start_requested').write_text('private')
            self.assertEqual(self.substage(self.checker(root, state='idle')), 607)

    def test_diagnostic_failure_is_closed_and_does_not_replace_family(self):
        with tempfile.TemporaryDirectory() as root:
            checker = self.checker(root)
            checker.engines.side_effect = OSError('private-path')
            self.assertEqual(self.substage(checker), 612)

    def test_success_keeps_the_existing_ten_second_acceptance(self):
        checker = guest.Checker.__new__(guest.Checker)
        checker.observe = mock.Mock(return_value=True)
        checker.state = mock.Mock(return_value='recording')
        self.assertIs(checker.checked_recording_state(), True)
        checker.observe.assert_called_once()
        args = checker.observe.call_args.args
        self.assertEqual((args[0], args[2]), ('recording-state', 10))


if __name__ == '__main__':
    unittest.main()
