"""Closed diagnostics for a supported language selection and daemon restart."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'direct_voxtype_language_selection', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


class LanguageSelectionDiagnostics(unittest.TestCase):
    OLD = (41, 123, Path('/owned/voxtype'))
    NEW = (42, 124, Path('/owned/voxtype'))

    def checker(self, *, checkpoint='daemon-readiness', active=0, failed=1,
                engines=None, state='idle', selected='en'):
        checker = guest.Checker.__new__(guest.Checker)
        checker._ready_engine = self.OLD
        checker._selection_checkpoint = checkpoint
        checker.select = mock.Mock(side_effect=guest.Invalid('private-selection'))
        checker.cmd = mock.Mock(side_effect=(
            SimpleNamespace(returncode=active), SimpleNamespace(returncode=failed)))
        checker.engines = mock.Mock(
            return_value=[self.NEW] if engines is None else engines)
        checker.state = mock.Mock(return_value=state)
        checker.adapter = mock.Mock(return_value={'language': selected})
        return checker

    def substage(self, checker, language='en'):
        with self.assertRaises(guest.TranscriptionStageFailure) as raised:
            checker.checked_language_selection({'language': language})
        self.assertEqual(raised.exception.error_label, 'invalid')
        return raised.exception.failure_substage

    def test_fixture_and_adapter_failures_are_closed(self):
        checker = self.checker()
        self.assertEqual(self.substage(checker, 'private'), 401)
        self.assertEqual(
            self.substage(self.checker(checkpoint='language-adapter')), 402)

    def test_service_process_and_restart_outcomes_are_closed(self):
        cases = (
            (self.checker(active=3, failed=0), 403),
            (self.checker(active=3, failed=3), 404),
            (self.checker(engines=[]), 405),
            (self.checker(engines=[self.NEW, self.NEW]), 406),
            (self.checker(engines=[self.OLD]), 407),
        )
        for checker, expected in cases:
            with self.subTest(substage=expected):
                self.assertEqual(self.substage(checker), expected)

    def test_native_state_and_selected_language_outcomes_are_closed(self):
        for state, expected in (
                ('stopped', 408), ('recording', 409), ('transcribing', 410),
                ('streaming', 411)):
            with self.subTest(state=state):
                self.assertEqual(self.substage(self.checker(state=state)), expected)
        self.assertEqual(self.substage(self.checker(state='idle', selected='en')), 412)
        self.assertEqual(self.substage(self.checker(state='idle', selected='he')), 413)
        checker = self.checker()
        checker.state.side_effect = OSError('private-state')
        self.assertEqual(self.substage(checker), 414)

    def test_success_uses_the_supported_selection_once(self):
        checker = guest.Checker.__new__(guest.Checker)
        checker.select = mock.Mock()
        self.assertEqual(
            checker.checked_language_selection({'language': 'he'}), 'he')
        checker.select.assert_called_once_with(language='he')


if __name__ == '__main__':
    unittest.main()
