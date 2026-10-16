"""Qualification-only resource and dependent-gate controls."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    'dictation_observer_prerequisites', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


class ObserverPrerequisiteControls(unittest.TestCase):
    def checker(self):
        checker = guest.Checker.__new__(guest.Checker)
        checker.account = SimpleNamespace(pw_uid=1000)
        checker.cmd = mock.Mock(return_value=SimpleNamespace(
            stdout=b'', stderr=b'', returncode=0))
        return checker

    def test_successful_vulkan_preflight_stops_resident_daemon_until_cpu_selection(self):
        checker = self.checker()
        result = SimpleNamespace(stdout=b'', stderr=b'', returncode=0)
        with mock.patch.object(guest, 'run', return_value=result) as execute:
            self.assertIs(checker.initial_vulkan_setup(), result)
        checker.cmd.assert_called_once_with(
            ['systemctl', '--user', 'stop', 'voxtype.service'])
        execute.assert_called_once_with([
            '/usr/bin/env', 'PKEXEC_UID=1000', str(guest.SETUP),
            '--backend', 'vulkan'], 750, check=False)

    def test_failed_vulkan_preflight_exports_only_closed_exit_outcome_and_restores_daemon(self):
        checker = self.checker()
        failed = SimpleNamespace(stdout=b'private', stderr=b'private', returncode=1)
        with mock.patch.object(guest, 'run', return_value=failed):
            with self.assertRaises(guest.GpuStageFailure) as raised:
                checker.initial_vulkan_setup()
        self.assertEqual(raised.exception.failure_stage,
                         guest.GPU_FAILURE_STAGES['initial-vulkan-setup'])
        self.assertEqual(raised.exception.failure_substage, 2022)
        self.assertEqual(raised.exception.failure_returncode, 1)
        self.assertEqual(raised.exception.error_label, 'invalid')
        self.assertEqual(checker.cmd.call_args_list, [
            mock.call(['systemctl', '--user', 'stop', 'voxtype.service']),
            mock.call(['systemctl', '--user', 'start', 'voxtype.service'], check=False),
        ])

    def test_vulkan_preflight_substages_distinguish_stop_timeout_and_launch_error(self):
        checker = self.checker()
        checker.cmd.side_effect = guest.Invalid('command-failed')
        with self.assertRaises(guest.GpuStageFailure) as stopped:
            checker.initial_vulkan_setup()
        self.assertEqual((stopped.exception.failure_substage,
                          stopped.exception.error_label), (2021, 'invalid'))

        for error, expected in ((guest.subprocess.TimeoutExpired(['private'], 1), (2023, 'timeout')),
                                (OSError('private'), (2024, 'os-error'))):
            checker = self.checker()
            with mock.patch.object(guest, 'run', side_effect=error):
                with self.assertRaises(guest.GpuStageFailure) as raised:
                    checker.initial_vulkan_setup()
            self.assertEqual((raised.exception.failure_substage,
                              raised.exception.error_label), expected)

    def privacy_checker(self, phrase_count, prior_failed):
        checker = self.checker()
        gate = 'transcript-log-notification-leak-scan'
        checker.gates = {gate}
        checker.report = {'gates': ([{
            'id': 'cpu-english-transcription-insertion',
            'status': 'failed' if prior_failed else 'passed',
        }] if prior_failed is not None else [])}
        checker.phrases = ['bounded-hypothesis'] * phrase_count
        return checker, gate

    def test_missing_privacy_coverage_is_unrun_only_after_concrete_failure(self):
        checker, gate = self.privacy_checker(11, True)
        self.assertIs(checker.privacy_gate(), False)
        self.assertEqual(checker.report['gates'][-1], {
            'id': gate, 'status': 'unrun',
            'evidence_kind': guest.EXPECTED_KINDS[gate],
            'code': 'prerequisite-or-collector-failed', 'observations': {}})

    def test_dependent_unrun_cannot_replace_privacy_failure_or_duplicate_gate(self):
        checker, gate = self.privacy_checker(11, False)
        self.assertIs(checker.privacy_gate(), False)
        self.assertEqual(checker.report['gates'][-1]['status'], 'failed')
        self.assertEqual(checker.report['gates'][-1]['code'],
                         'gate-' + gate + '-invalid')
        checker.report['gates'][0]['status'] = 'failed'
        with self.assertRaisesRegex(
                guest.Invalid, '^unknown-or-duplicate-dependent-gate$'):
            checker.dependent_unrun(gate)

    def test_full_privacy_coverage_remains_a_required_executed_gate(self):
        checker, gate = self.privacy_checker(12, True)
        checker.leakage = mock.Mock(return_value={'count': 12, 'matched': 0})
        self.assertIs(checker.privacy_gate(), True)
        checker.leakage.assert_called_once_with()
        self.assertEqual(checker.report['gates'][-1]['status'], 'passed')


if __name__ == '__main__':
    unittest.main()
