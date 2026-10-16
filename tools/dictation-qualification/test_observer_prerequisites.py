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

    def test_frozen_runner_has_no_accelerated_vulkan_device(self):
        harness = (Path(__file__).resolve().parents[2] / 'tools/test-install.sh').read_text()
        self.assertIn('"-display", "none", "-vga", "virtio"', harness)
        self.assertNotIn('virgl=on', harness)
        self.assertNotIn('hostdev', harness)

    def test_frozen_vm_vulkan_failure_stops_resident_daemon_and_restores_it(self):
        checker = self.checker()
        failed = SimpleNamespace(stdout=b'private', stderr=b'private', returncode=1)
        with mock.patch.object(guest, 'run', return_value=failed) as execute:
            self.assertIs(checker.vm_vulkan_failure(), failed)
        checker.cmd.assert_has_calls([
            mock.call(['systemctl', '--user', 'stop', 'voxtype.service']),
            mock.call(['systemctl', '--user', 'start', 'voxtype.service'], check=False),
        ])
        execute.assert_called_once_with([
            '/usr/bin/env', 'PKEXEC_UID=1000', str(guest.SETUP),
            '--backend', 'vulkan'], 750, check=False)

    def test_frozen_vm_vulkan_success_invalidates_fixture_and_restores_daemon(self):
        checker = self.checker()
        succeeded = SimpleNamespace(stdout=b'private', stderr=b'private', returncode=0)
        with mock.patch.object(guest, 'run', return_value=succeeded):
            with self.assertRaisesRegex(
                    guest.Invalid, '^vm-vulkan-fixture-unexpectedly-supported$'):
                checker.vm_vulkan_failure()
        self.assertEqual(checker.cmd.call_args_list, [
            mock.call(['systemctl', '--user', 'stop', 'voxtype.service']),
            mock.call(['systemctl', '--user', 'start', 'voxtype.service'], check=False),
        ])

    def test_frozen_vm_vulkan_timeout_restores_daemon(self):
        checker = self.checker()
        with mock.patch.object(guest, 'run', side_effect=guest.subprocess.TimeoutExpired(
                ['private'], 1)):
            with self.assertRaises(guest.subprocess.TimeoutExpired):
                checker.vm_vulkan_failure()
        self.assertEqual(checker.cmd.call_args_list, [
            mock.call(['systemctl', '--user', 'stop', 'voxtype.service']),
            mock.call(['systemctl', '--user', 'start', 'voxtype.service'], check=False),
        ])

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
