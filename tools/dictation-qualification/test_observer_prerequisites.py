"""Qualification-only resource and dependent-gate controls."""
import hashlib
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import tempfile
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

    def test_vulkan_payload_diagnostics_are_closed_and_exact(self):
        data = b'signed-vulkan-test-payload'
        asset = {'name': 'voxtype-vulkan', 'bytes': len(data),
                 'sha256': hashlib.sha256(data).hexdigest()}
        with tempfile.TemporaryDirectory() as temp, \
                mock.patch.dict(guest.ASSETS, {'vulkan': asset}), \
                mock.patch.object(guest, 'PAYLOAD', Path(temp) / 'payload'), \
                mock.patch.object(guest, 'VULKAN_CACHE', Path(temp) / 'cache'):
            guest.PAYLOAD.mkdir()
            checker = self.checker()

            with self.assertRaises(guest.GpuStageFailure) as absent:
                checker.checked_vulkan_payload()
            self.assertEqual((absent.exception.error_label,
                              absent.exception.failure_substage), ('os-error', 2031))

            def cache_only(path):
                if path == guest.PAYLOAD / asset['name']:
                    raise FileNotFoundError
                return SimpleNamespace(st_mode=0o100755, st_uid=0, st_size=len(data))
            with mock.patch.object(Path, 'lstat', autospec=True, side_effect=cache_only), \
                    mock.patch.object(guest, 'sha', return_value=asset['sha256']), \
                    self.assertRaises(guest.GpuStageFailure) as cached:
                checker.checked_vulkan_payload()
            self.assertEqual((cached.exception.error_label,
                              cached.exception.failure_substage), ('os-error', 2032))

            wrong = SimpleNamespace(st_mode=0o100755, st_uid=0, st_size=len(data) + 1)
            with mock.patch.object(Path, 'lstat', autospec=True, return_value=wrong), \
                    self.assertRaises(guest.GpuStageFailure) as wrong_size:
                checker.checked_vulkan_payload()
            self.assertEqual((wrong_size.exception.error_label,
                              wrong_size.exception.failure_substage), ('invalid', 2035))

            exact = SimpleNamespace(st_mode=0o100755, st_uid=0, st_size=len(data))
            with mock.patch.object(Path, 'lstat', autospec=True, return_value=exact), \
                    mock.patch.object(guest, 'sha', return_value=asset['sha256']):
                self.assertIs(checker.checked_vulkan_payload(), True)

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
