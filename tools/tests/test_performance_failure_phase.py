"""Fail-only fixed diagnostics: synthetic private logs, no VM/acceptance result."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

import performance_external_fixture as F

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inner = load('fixed_phase_inner', 'tools/performance/run-paired.py')
outer = load('fixed_phase_outer', 'tools/performance/qualification.py')
screen = load('fixed_phase_screen', 'tools/native-functional/screen-evidence.py')


class FixedFailurePhaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root/'work'
        self.work.mkdir()
        self.task = 'a'*32
        self.state = dict(task_id=self.task, phase='blocked', error='password=do-not-export')
        self.owner = dict(schema='arctic-paired-test-image-owner-v1', release_acceptance=False,
            task_id=self.task, container='arctic-paired-'+self.task+'-'+'b'*8, base_id='sha256:'+'c'*64)
        self.write('status.json', json.dumps(self.state))
        self.write('vm-prepared-image-owner.json', json.dumps(self.owner))
        self.write('baseline-install-harness.log', 'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean\n')
        self.write('candidate-install-harness.log', 'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean\n')
        self.write('runs/baseline/1/performance-context.json', json.dumps(dict(image='baseline', boot=1,
            collector='console', arbitrary_private='token=private')))
        self.write('runs/baseline/1/harness.log', '[  10s] booting the default entry\n'
            '[  20s] passphrase prompt on screen: boot-31-luks-prompt.png\n'
            'password=do-not-export https://private.invalid/?access_token=private\n')
        self.write('runs/baseline/1/serial-boot.log', 'transcript: private words\n'
            'RuntimeError: No unique actual desktop session for console restoration\n')

    def write(self, name, content):
        path = self.work/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def summary(self, code='sensitive_text'):
        return inner.failure_phase_summary(self.work, code)

    def exporter(self, name, path):
        return inner if name == 'paired_failure_phase' else screen

    def export(self, target=None):
        with patch.object(outer, 'C', F.contract), patch.object(outer, 'load', side_effect=self.exporter):
            outer.export_failure_phase(self.work, target or self.root/'screened', 'sensitive_text')

    def test_private_text_never_enters_closed_summary_and_originals_unchanged(self):
        originals = {p: p.read_bytes() for p in self.work.rglob('*') if p.is_file()}
        result = self.summary()
        content = json.dumps(result).encode()
        for private in (b'do-not-export', b'private words', b'private.invalid', b'access_token', b'arbitrary_private'):
            self.assertNotIn(private, content)
        self.assertEqual(result['observed_context'], 'baseline_1')
        self.assertEqual(result['console_restore_error'], 'no_unique_desktop_session')
        self.assertTrue(result['private_owner_verified'])
        self.assertFalse(result['release_acceptance'])
        self.assertFalse(result['performance_acceptance'])
        self.assertFalse(result['original_evidence_uploaded'])
        self.assertNotIn('completed_boots', result)
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})
        self.assertEqual(screen.external_text(content), content)

    def test_markers_and_smoke_zero_are_only_observations_not_measurements(self):
        self.write('runs/baseline/1/harness.log', 'qemu started (boot): private arguments\n'
            'qemu exited: see qemu-boot.log\nno QMP socket\n')
        self.write('runs/baseline/1/serial-boot.log', 'ARCTIC-PERFORMANCE-CONSOLE-RESTORED session=private vt=1\n'
            'ARCTIC-COLLECT-BEGIN\nARCTIC-COLLECT-END\nARCTIC-INSTALLED-SMOKE-EXIT=0\n')
        result = self.summary()
        self.assertEqual(result['smoke_exit'], 'zero')
        self.assertTrue(result['markers']['collector_end'])
        self.assertTrue(result['markers']['qemu_start'])
        self.assertTrue(result['markers']['qmp_not_connected'])
        self.assertTrue(result['markers']['qemu_exit_before_qmp'])
        self.assertEqual(result['status'], 'unqualified_fixed_observations_only')
        self.assertNotIn('comparison', result)
        self.assertFalse(result['performance_acceptance'])

    def test_duplicate_or_nonzero_exit_has_no_dynamic_value_export(self):
        for content, expected in [('ARCTIC-INSTALLED-SMOKE-EXIT=255\n', 'nonzero'),
                ('ARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-INSTALLED-SMOKE-EXIT=1\n', 'ambiguous'),
                ('ARCTIC-INSTALLED-SMOKE-EXIT=password=private\n', 'absent')]:
            self.write('runs/baseline/1/serial-boot.log', content)
            result = self.summary()
            self.assertEqual(result['smoke_exit'], expected)
            self.assertNotIn('private', json.dumps(result).replace('private_owner_verified', ''))

    def test_wrong_owner_boolean_and_duplicate_json_prevent_log_reads(self):
        for fault in ('task', 'release', 'duplicate'):
            owner = dict(self.owner)
            if fault == 'task': owner['task_id'] = 'd'*32
            if fault == 'release': owner['release_acceptance'] = 0
            content = json.dumps(owner)
            if fault == 'duplicate': content = content[:-1] + ',"task_id":"'+self.task+'"}'
            self.write('vm-prepared-image-owner.json', content)
            result = self.summary()
            self.assertFalse(result['private_owner_verified'])
            self.assertEqual(result['read_status']['serial'], 'unavailable')

    def test_symlinked_root_and_intermediate_directories_are_not_followed(self):
        link = self.root/'linked-work'
        link.symlink_to(self.work, target_is_directory=True)
        self.assertFalse(inner.failure_phase_summary(link, 'unclassified')['private_owner_verified'])
        runs = self.work/'runs'
        runs.rename(self.root/'private-runs')
        runs.symlink_to(self.root/'private-runs', target_is_directory=True)
        result = self.summary()
        self.assertEqual(result['read_status']['context'], 'unsafe_or_oversized')
        self.assertEqual(result['read_status']['serial'], 'unavailable')

    def test_serial_symlink_fifo_and_oversize_are_rejected_without_payload_read(self):
        path = self.work/'runs/baseline/1/serial-boot.log'
        original = self.root/'private-serial.log'
        original.write_text('ARCTIC-COLLECT-END\npassword=private\n')
        for fault in ('symlink', 'fifo', 'oversize'):
            path.unlink()
            if fault == 'symlink': path.symlink_to(original)
            elif fault == 'fifo': os.mkfifo(path)
            else:
                with path.open('wb') as output:
                    output.seek(8388608)
                    output.write(b'x')
            result = self.summary()
            self.assertEqual(result['read_status']['serial'], 'unsafe_or_oversized')
            self.assertFalse(result['markers']['collector_end'])

    def test_malformed_context_and_boolean_boot_are_not_selected(self):
        for content in ('{"image":"baseline","boot":true,"collector":"console"}',
                        '{"image":"baseline","boot":1,"boot":1,"collector":"console"}'):
            self.write('runs/baseline/1/performance-context.json', content)
            result = self.summary()
            self.assertEqual(result['observed_context'], 'none')
            self.assertEqual(result['read_status']['serial'], 'unavailable')

    def test_screen_exception_classifier_never_stringifies_arbitrary_errors(self):
        class PrivateError(RuntimeError):
            def __str__(self): raise AssertionError('Private error must not be rendered')
        for error in (PrivateError('password=private'), RuntimeError('token=private'),
                      RuntimeError('Sensitive text in external evidence', 'password=private'),
                      ValueError('https://private.invalid/?token=private')):
            self.assertEqual(outer.fixed_screen_failure(error), 'unclassified')
        self.assertEqual(outer.fixed_screen_failure(RuntimeError('Sensitive text in external evidence')), 'sensitive_text')
        self.assertEqual(outer.fixed_screen_failure(TimeoutError('password=private')), 'deadline')
        for code in ('password=private', True, 'sensitive_text\nprivate'):
            with self.assertRaises(ValueError): self.summary(code)

    def test_export_uses_unchanged_atomic_scanner_and_keeps_private_originals(self):
        raw = {p: p.read_bytes() for p in self.work.rglob('*') if p.is_file()}
        with self.assertRaises(RuntimeError): screen.external_text(raw[self.work/'runs/baseline/1/serial-boot.log'])
        self.export()
        target = self.root/'screened'
        self.assertEqual({p.name for p in target.iterdir()}, {'unqualified-failure-phase.json', 'upload-screening.json'})
        content = (target/'unqualified-failure-phase.json').read_bytes()
        receipt = json.loads((target/'upload-screening.json').read_bytes())['files']['unqualified-failure-phase.json']
        digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(receipt, dict(original_sha256=digest, uploaded_sha256=digest, bytes=len(content), redactions=0))
        self.assertEqual(raw, {p: p.read_bytes() for p in raw})
        entries = {p.name: p.read_bytes() for p in target.iterdir()}
        _, kwargs = F.fixture()
        with F.archive(entries) as archive, self.assertRaisesRegex(ValueError, 'Missing full original paired inputs'):
            F.contract.validate_evidence(archive, **kwargs)

    def test_existing_or_symlinked_output_and_non_siblings_are_never_modified(self):
        target = self.root/'screened'
        outside = self.root/'private-target'
        outside.write_text('password=private')
        for fault in ('file', 'symlink', 'non_sibling'):
            candidate = target
            if fault == 'file': target.write_text('existing')
            elif fault == 'symlink': target.symlink_to(outside)
            else: candidate = self.root/'elsewhere'/'screened'
            with self.assertRaises(ValueError): self.export(candidate)
            self.assertEqual(outside.read_text(), 'password=private')
            if target.is_symlink() or target.exists(): target.unlink()

    def test_failed_runner_and_rejected_full_export_produce_only_unqualified_summary(self):
        # Exercise the real finalizer with an owned synthetic child and real
        # strict scanner. No process, VM, host log or measurement is created.
        self.work.rename(self.root/'seed')
        seed = self.root/'seed'
        args = types.SimpleNamespace(work=self.work, screened=self.root/'screened', evidence=self.root/'evidence',
            inputs=self.root/'inputs', source=self.root/'source', manifest=self.root/'manifest.json')
        args.inputs.mkdir(); (args.inputs/'PERFORMANCE-PLAN.json').write_text('{}\n'); args.manifest.write_text('{}\n')
        class Child:
            pid = 123456789
            def wait(child, timeout=None):
                if not self.work.exists():
                    import shutil
                    shutil.copytree(seed, self.work)
                return 1
            def poll(child): return 1
        plan = dict(image=dict(name='test.iso', source_sha='a'*40, sha256='b'*64),
            observer={}, candidate_source_files={}, execution_files={})
        contract = types.SimpleNamespace(require=F.contract.require, BASELINE=F.contract.BASELINE, validate_evidence=Mock())
        with patch.object(outer, 'C', contract), patch.object(outer, 'activation', return_value=(plan, 'c'*40)), \
                patch.object(outer, 'verify', return_value={}), patch.object(outer, 'baseline', return_value=self.root/'baseline.iso'), \
                patch.object(outer, 'load', side_effect=self.exporter), patch.object(outer.subprocess, 'Popen', return_value=Child()), \
                patch.dict(os.environ, GITHUB_RUN_ID='31', GITHUB_SHA='d'*40):
            with self.assertRaisesRegex(RuntimeError, 'screen'):
                outer.run(args)
        contract.validate_evidence.assert_not_called()
        diagnostic = json.loads((args.screened/'unqualified-failure-phase.json').read_bytes())
        self.assertEqual(diagnostic['screening_failure'], 'sensitive_text')
        self.assertEqual(diagnostic['status'], 'unqualified_fixed_observations_only')
        self.assertEqual((args.evidence/'runs/baseline/1/serial-boot.log').read_bytes(),
                         (seed/'runs/baseline/1/serial-boot.log').read_bytes())
        self.assertEqual({p.name for p in args.screened.iterdir()}, {'unqualified-failure-phase.json', 'upload-screening.json'})


if __name__ == '__main__':
    unittest.main()
