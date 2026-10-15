"""Fail-closed host controls; these tests never run a VM or install payloads."""
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zlib

spec = importlib.util.spec_from_file_location('dictation_qualification_runner', Path(__file__).with_name('runner.py'))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerGuards(unittest.TestCase):
    @staticmethod
    def png(color=2, pixel=None):
        def chunk(kind, body):
            return (struct.pack('>I', len(body)) + kind + body
                    + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff))
        pixel = pixel or (b'\x12\x17\x1e' if color == 2 else b'\x12\x17\x1e\xff')
        raw = (b'\x00' + pixel * 1280) * 800
        return (b'\x89PNG\r\n\x1a\n'
                + chunk(b'IHDR', struct.pack('>IIBBBBB', 1280, 800, 8, color, 0, 0, 0))
                + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))

    def recovery_fixture(self, root, *, reverse=False, wrong_ack=False):
        vm, evidence = root / 'vm', root / 'evidence'
        vm.mkdir(); evidence.mkdir()
        phase = 'online-installed'
        installation = '11111111-1111-1111-1111-111111111111'
        boot = '22222222-2222-2222-2222-222222222222'
        nonces = {'gpu_failure': 'a' * 32, 'cpu_ready': 'b' * 32}
        observations = {stage + '_capture_ack_sha256': hashlib.sha256(nonce.encode()).hexdigest()
                        for stage, nonce in nonces.items()}
        if wrong_ack:
            observations['cpu_ready_capture_ack_sha256'] = '0' * 64
        report = {'boot_id': boot, 'gates': [{'id': 'gpu-failure-explicit-cpu-fallback',
                  'status': 'passed', 'observations': observations}]}
        (evidence / (phase + '.json')).write_text(json.dumps(report))
        proofs = []
        for stage in ('gpu_failure', 'cpu_ready'):
            state, backend, language = (('error', 'cpu', 'en') if stage == 'gpu_failure'
                                        else ('ready', 'cpu', 'he'))
            name = 'dictation-recovery-' + phase + '-' + stage.replace('_', '-') + '.png'
            data = self.png(pixel=(b'\x12\x17\x1e' if stage == 'gpu_failure'
                                   else b'\xee\xf2\xf5'))
            (vm / name).write_bytes(data)
            request = dict(boot_id=boot, installation_id=installation, phase=phase,
                           desktop_uid=1000, receiver_empty=True, stage=stage, state=state,
                           backend=backend, language=language, capture_nonce=nonces[stage])
            proofs.append(dict(request=request, path=name, sha256=hashlib.sha256(data).hexdigest(),
                               iso_sha256='c' * 64, installation_id=installation))
        if reverse:
            proofs.reverse()
        (vm / 'dictation-recovery-screen-receipts.json').write_text(json.dumps(proofs))
        ctx = dict(phase=phase, installation_id=installation, iso_sha256='c' * 64)
        return vm, evidence, ctx

    def test_recovery_screens_require_exact_order_and_ack_binding_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            vm, evidence, ctx = self.recovery_fixture(Path(temp))
            result = runner.recovery_screens(vm, ctx, evidence)
            self.assertEqual(set(result), {'gpu_failure', 'cpu_ready'})
            self.assertEqual({path.name for path in evidence.glob('*.png')}, {
                'dictation-recovery-online-installed-gpu-failure.png',
                'dictation-recovery-online-installed-cpu-ready.png'})
            self.assertFalse((evidence / 'dictation-recovery-screen-receipts.json').exists())
        for option in ({'reverse': True}, {'wrong_ack': True}):
            with tempfile.TemporaryDirectory() as temp:
                vm, evidence, ctx = self.recovery_fixture(Path(temp), **option)
                with self.assertRaisesRegex(RuntimeError, 'Recovery screen receipt'):
                    runner.recovery_screens(vm, ctx, evidence)
                self.assertEqual(list(evidence.glob('*.png')), [])

    def test_recovery_screens_reject_rgba(self):
        with tempfile.TemporaryDirectory() as temp:
            vm, evidence, ctx = self.recovery_fixture(Path(temp))
            name = 'dictation-recovery-online-installed-cpu-ready.png'
            data = self.png(6)
            (vm / name).write_bytes(data)
            receipts = json.loads((vm / 'dictation-recovery-screen-receipts.json').read_text())
            receipts[1]['sha256'] = hashlib.sha256(data).hexdigest()
            (vm / 'dictation-recovery-screen-receipts.json').write_text(json.dumps(receipts))
            with self.assertRaisesRegex(RuntimeError, 'screenshot bytes differ'):
                runner.recovery_screens(vm, ctx, evidence)
            self.assertEqual(list(evidence.glob('*.png')), [])

    def test_recovery_screens_reject_byte_identical_stage_frames_before_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            vm, evidence, ctx = self.recovery_fixture(Path(temp))
            first = vm / 'dictation-recovery-online-installed-gpu-failure.png'
            second = vm / 'dictation-recovery-online-installed-cpu-ready.png'
            second.write_bytes(first.read_bytes())
            receipts = json.loads((vm / 'dictation-recovery-screen-receipts.json').read_text())
            receipts[1]['sha256'] = receipts[0]['sha256']
            (vm / 'dictation-recovery-screen-receipts.json').write_text(json.dumps(receipts))
            with self.assertRaisesRegex(RuntimeError, 'byte-identical'):
                runner.recovery_screens(vm, ctx, evidence)
            self.assertEqual(list(evidence.glob('*.png')), [])

    def test_recovery_screens_roll_back_partial_copy(self):
        with tempfile.TemporaryDirectory() as temp:
            vm, evidence, ctx = self.recovery_fixture(Path(temp))
            original = shutil.copyfile
            calls = 0
            def fail_second(source, target):
                nonlocal calls
                calls += 1
                if calls == 2:
                    Path(target).write_bytes(b'partial')
                    raise OSError('private destination failure')
                return original(source, target)
            with patch.object(runner.shutil, 'copyfile', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'private destination failure'):
                    runner.recovery_screens(vm, ctx, evidence)
            self.assertEqual(list(evidence.glob('*.png')), [])

    def test_integration_hash_requires_every_direct_upstream_source_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in runner.INTEGRATION_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name)
            first = runner.integration_sha(root)
            self.assertRegex(first, r'^[0-9a-f]{64}$')
            (root / runner.INTEGRATION_FILES[1]).write_text('changed selector')
            self.assertNotEqual(first, runner.integration_sha(root))
            (root / runner.INTEGRATION_FILES[1]).unlink()
            with self.assertRaisesRegex(RuntimeError, 'lacks direct VoxType integration file'):
                runner.integration_sha(root)

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
                        GITHUB_REF='refs/heads/codex/diagnose-voxtype-readiness-387951',
                        GITHUB_WORKFLOW='Candidate direct VoxType image qualification',
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
