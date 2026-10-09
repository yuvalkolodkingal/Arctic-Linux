"""Fail-closed host controls; these tests never run a VM or install payloads."""
import importlib.util
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('dictation_qualification_runner', Path(__file__).with_name('runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerGuards(unittest.TestCase):
    def test_unresponsive_docker_still_terminates_owned_host_process_group(self):
        child = Mock(pid=123, poll=Mock(return_value=None),
                     wait=Mock(side_effect=[runner.subprocess.TimeoutExpired('fixture', 1), 0]))
        with tempfile.TemporaryDirectory() as temp, patch.object(runner.subprocess, 'Popen', return_value=child), \
                patch.object(runner.subprocess, 'run', side_effect=runner.subprocess.TimeoutExpired('docker', 30)), \
                patch.object(runner.os, 'killpg') as kill:
            with self.assertRaises(runner.subprocess.TimeoutExpired):
                runner.execute(['fixture'], Path(temp) / 'private.log', 1, {}, 'arctic-paired-dictation-' + 'a' * 32)
            kill.assert_called_once_with(123, runner.signal.SIGTERM)

    def test_disabled_manifest_stops_before_commands_or_downloads(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / 'manifest.json'
            manifest.write_text(json.dumps(dict(ready=False, release_acceptance=False)))
            with patch.object(runner.subprocess, 'check_output') as command:
                with self.assertRaisesRegex(RuntimeError, 'disabled'):
                    runner.verify(SimpleNamespace(manifest=manifest))
                command.assert_not_called()

    def test_wrong_actions_identity_stops_before_source_or_payload_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / 'manifest.json'
            manifest.write_text(json.dumps(dict(ready=True, release_acceptance=False)))
            with patch.dict(runner.os.environ, {}, clear=True), patch.object(runner.subprocess, 'check_output') as command:
                with self.assertRaisesRegex(RuntimeError, 'disposable dictation Actions'):
                    runner.verify(SimpleNamespace(manifest=manifest))
                command.assert_not_called()

    def test_unreviewed_hardware_profile_stops_before_checkout_commands(self):
        identity = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
                        GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',
                        GITHUB_REF='refs/heads/codex/qualification-dispatch-20261008',
                        GITHUB_WORKFLOW='Candidate dictation image qualification',
                        GITHUB_EVENT_NAME='push', GITHUB_RUN_ATTEMPT='1')
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / 'manifest.json'
            manifest.write_text(json.dumps(dict(ready=True, release_acceptance=False,
                                                hardware_profiles=['small-v2', 'turbo-q5-v3'])))
            with patch.dict(runner.os.environ, identity, clear=True), patch.object(runner.subprocess, 'check_output') as command:
                with self.assertRaisesRegex(RuntimeError, 'Unreviewed dictation hardware profile'):
                    runner.verify(SimpleNamespace(manifest=manifest, hardware_profile='external-model'))
                command.assert_not_called()

    def test_duplicate_or_missing_serial_reports_never_enter_public_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vm, evidence = root / 'vm', root / 'evidence'
            vm.mkdir(); evidence.mkdir()
            context = dict(phase='offline-installed')
            for serial in ('', 'ARCTIC-DICTATION-QUALIFICATION {}\n' * 2):
                (vm / 'serial-boot.log').write_text(serial)
                with self.assertRaisesRegex(RuntimeError, 'Missing/duplicate'):
                    runner.reports(vm, 'installed', context, evidence, SimpleNamespace())
                self.assertEqual(list(evidence.iterdir()), [])

    def test_failed_schema_validation_never_copies_raw_serial_or_report(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            vm, evidence = root / 'vm', root / 'evidence'
            vm.mkdir(); evidence.mkdir()
            (vm / 'serial-boot.log').write_text('private transcript\nARCTIC-DICTATION-QUALIFICATION {}\n')
            contract = SimpleNamespace(validate=lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('invalid report')))
            with self.assertRaisesRegex(RuntimeError, 'invalid report'):
                runner.reports(vm, 'installed', dict(phase='offline-installed'), evidence, contract)
            self.assertEqual(list(evidence.iterdir()), [])
