"""Synthetic host-stage controls only; no Docker, guests, ISO or private export."""
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
import runner as R


class PrivateError(RuntimeError):
    def __str__(self):
        raise AssertionError('diagnostic must not format private exception text')

    def __repr__(self):
        raise AssertionError('diagnostic must not format private exception representation')


class Controls(unittest.TestCase):
    def test_fixed_codes_cover_classes_and_stage_specific_literals_without_formatting(self):
        for stage in R.DIAGNOSTIC_STAGES:
            for error_class, label in R.DIAGNOSTIC_ERROR_TYPES:
                if error_class is subprocess.TimeoutExpired:
                    error = error_class(['private-argv'], 1, output=b'private-output', stderr=b'private-stderr')
                elif error_class is subprocess.CalledProcessError:
                    error = error_class(1, ['private-argv'], output=b'private-output', stderr=b'private-stderr')
                else:
                    error = error_class('private-text')
                self.assertEqual(R.diagnostic_code(stage, error), 'installer-' + stage + '-' + label)
            for message, code in R.DIAGNOSTIC_LITERALS.get(stage, ()):
                self.assertEqual(R.diagnostic_code(stage, PrivateError(message)), 'installer-' + stage + '-' + code)
            self.assertRegex(R.diagnostic_code(stage, PrivateError('private-text')), '^[a-z0-9-]{1,80}$')
        self.assertEqual(R.diagnostic_code('docker-info', PrivateError('Actual physical capture build differs')),
                         'installer-docker-info-runtime-error')

    def test_arbitrary_arguments_and_unknown_classes_have_fixed_fallbacks(self):
        class PrivateString(str):
            def __eq__(self, other):
                raise AssertionError('must not compare arbitrary string subclass')
        for args in ((), ('private-text',), ('Actual physical capture build differs', 'private'),
                     (b'Actual physical capture build differs',), ({'transcript': 'private'},),
                     (PrivateString('Actual physical capture build differs'),)):
            self.assertEqual(R.diagnostic_code('build-binding', PrivateError(*args)),
                             'installer-build-binding-runtime-error')
        class PrivateBase(BaseException):
            def __str__(self):
                raise AssertionError('must not format unknown class')
        self.assertEqual(R.diagnostic_code('run-live', PrivateBase('private')), 'installer-run-live-other-error')
        for stage in (None, '', 'private-stage', 1, [], {}):
            with self.assertRaisesRegex(RuntimeError, '^Unknown installer diagnostic stage$'):
                R.diagnostic_code(stage, PrivateError('private'))

    def pipeline(self, failed_stage=None, active=False):
        """Drive actual main() using synthetic files and intercepted host commands."""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'; source.mkdir()
            manifest_path = root / 'manifest.json'; manifest_path.write_text('{}')
            evidence = root / 'evidence'
            secret = 'synthetic-private-transcript-argv-stderr'
            inputs = {name: 'a' * 64 for name in set(R.C.EXECUTION_FILES) |
                      {'tools/installer-qualification/active-guest.py', 'tools/installer-qualification/installed-guest.py'}}
            manifest = {'image': {'source_sha': 'b' * 40, 'sha256': 'c' * 64, 'bytes': 1_000_000_000},
                        'execution_files': inputs}
            verification = 0
            original_sha = R.sha
            trace = []
            cleanup_images = []

            def fault(stage):
                if failed_stage == stage:
                    raise ValueError(secret)

            def verify(*_):
                nonlocal verification
                verification += 1
                if verification == 2:
                    fault('source-verify')
                return manifest, root / 'fixture.iso'

            def digest(path):
                if Path(path).name == 'raw-screencopy':
                    fault('build-binding')
                return original_sha(path)

            def info(*_, **__):
                fault('docker-info')
                return b'synthetic-version'

            def host_command(argv, **kwargs):
                if argv[:3] == ['docker', 'image', 'rm']:
                    cleanup_images.append(argv[3])
                    if failed_stage == 'cleanup':
                        raise subprocess.CalledProcessError(1, ['private-argv'], output=secret, stderr=secret)
                    return SimpleNamespace(returncode=0)
                self.assertEqual(argv[:3], ['docker', 'container', 'inspect'])
                return SimpleNamespace(returncode=1)

            def execute(argv, log, *_):
                stage = Path(log).stem
                if stage == 'installer-harness':
                    stage = 'run-live'
                trace.append(stage)
                if stage != 'run-live':
                    fault(stage)
                if stage == 'provision':
                    (evidence / 'vm-prepared-image-id.txt').write_text('d' * 64)
                elif stage == 'capture-build':
                    payload = Path(argv[-1])
                    (payload / 'taskbar-vm-prepared-image-id.txt').write_text('e' * 64)
                    binary = payload / 'raw-screencopy'; binary.write_bytes(b'\x7fELFsynthetic-host-fixture')
                    build = {'schema': 'arctic-taskbar-tools-v1', 'release_acceptance': False,
                             'sources': {name: inputs[name] for name in ('shell/dev/virtual-pointer.c',
                                 'tools/native-functional/taskbar-screencopy.c', 'shell/dev/wlr-screencopy-unstable-v1.xml')},
                             'binaries': {'raw-screencopy': original_sha(binary)}}
                    (payload / 'build-provenance.json').write_text(json.dumps(build))
                else:
                    vm = Path(argv[-1]); vm.mkdir()
                    (vm / 'serial.log').write_bytes(b'synthetic serial')
                    (vm / 'installer-port.log').write_bytes(b'synthetic port')
                    fault(stage)

            def preserve(_vm, target, _active):
                target.mkdir()
                (target / 'host-execution.json').write_text(json.dumps({'host_transitions': []}))
                (target / 'installer-host-transitions.json').write_text(json.dumps({'receipts': []}))
                return {}

            def extract(_port, _serial, target, _context):
                fault('extract')
                target.mkdir()
                (target / 'installer-report.json').write_text('{}')
                return {'report': {}, 'state': {'status': 'passed'}, 'files': {}, 'requests': []}

            contract = SimpleNamespace(require=R.C.require, REQUIRED_IMAGES=(),
                cleanup_images=cleanup_images,
                context_check=Mock(side_effect=lambda *_: fault('context')),
                validate_report=Mock(side_effect=lambda *_: fault('report-validation')),
                validate_execution=Mock(side_effect=lambda *_: fault('execution-validation')),
                packaged_source_hashes=Mock(return_value={}), validate_catalog_selection=Mock())
            (source / 'modules').mkdir(); (source / 'modules/catalog.toml').write_text('')
            stdout = io.StringIO()
            argv = ['runner', '--source', str(source), '--inputs', str(root / 'inputs'),
                    '--manifest', str(manifest_path), '--evidence', str(evidence)]
            if active:
                argv.append('--active-profile')
            with contextlib.ExitStack() as stack:
                for object_, name, replacement in [(R, 'C', contract), (R, 'verify', verify), (R, 'sha', digest),
                        (R, 'execute', execute), (R, 'preserve_host', preserve), (R.E, 'extract', extract),
                        (R.E, 'active_contract', lambda: contract), (R.subprocess, 'check_output', info),
                        (R.subprocess, 'run', host_command), (R.signal, 'signal', lambda *_: None),
                        (R.H, 'cleanup_signals', lambda: contextlib.nullcontext([]))]:
                    stack.enter_context(patch.object(object_, name, replacement))
                stack.enter_context(patch.object(sys, 'argv', argv))
                stack.enter_context(patch.dict(R.os.environ, {'GITHUB_SHA': 'f' * 40, 'GITHUB_RUN_ID': '7'}))
                stack.enter_context(contextlib.redirect_stdout(stdout))
                status = R.main()
            state = json.loads((evidence / 'execution.json').read_text())
            return status, stdout.getvalue(), state, trace, contract

    def test_actual_main_failure_stages_emit_only_bounded_codes_and_remain_failed(self):
        for active in (False, True):
            for stage in R.DIAGNOSTIC_STAGES:
                with self.subTest(active=active, stage=stage):
                    status, stdout, state, trace, _ = self.pipeline(stage, active)
                    self.assertEqual(status, 1)
                    self.assertEqual(state['status'], 'failed')
                    self.assertIs(state['release_acceptance'], False)
                    self.assertTrue(state['errors'])
                    self.assertNotIn('synthetic-private', stdout)
                    lines = stdout.splitlines()
                    self.assertTrue(lines)
                    self.assertTrue(all(line.startswith('ARCTIC-INSTALLER-DIAGNOSTIC=installer-' + stage + '-') for line in lines))
                    self.assertTrue(all(len(line) <= 110 for line in lines))
                    if stage in ('docker-info', 'provision', 'capture-build', 'build-binding', 'context', 'source-verify'):
                        self.assertNotIn('run-live', trace)
                        self.assertNotIn('guest', state)

    def test_success_is_silent_and_retains_original_pending_review_status(self):
        for active in (False, True):
            with self.subTest(active=active):
                status, stdout, state, trace, contract = self.pipeline(active=active)
                self.assertEqual(status, 0)
                self.assertEqual(stdout, '')
                self.assertEqual(state['errors'], [])
                self.assertIs(state['release_acceptance'], False)
                self.assertIn('pending_manual_visual_review', state['status'])
                self.assertEqual(trace, ['provision', 'capture-build', 'run-live'])
                contract.validate_report.assert_called_once()
                contract.validate_execution.assert_called_once()
                self.assertEqual(state['transport']['status'], 'passed')
                self.assertNotIn('diagnostic_stage', state)

    def test_unavailable_stdout_does_not_abort_owned_cleanup_or_failure_persistence(self):
        for error in (BrokenPipeError('synthetic-private-output-error'),
                      ValueError('synthetic-private-closed-stream')):
            for active in (False, True):
                with self.subTest(active=active, error_class=type(error).__name__), patch('builtins.print', side_effect=error):
                    status, stdout, state, _, contract = self.pipeline('cleanup', active)
                self.assertEqual(status, 1)
                self.assertEqual(stdout, '')
                self.assertEqual(state['status'], 'failed')
                self.assertIs(state['release_acceptance'], False)
                self.assertEqual(len(contract.cleanup_images), 2)
                self.assertEqual(len(state['errors']), 2)
                self.assertNotIn('synthetic-private-output-error', json.dumps(state))
                self.assertNotIn('synthetic-private-closed-stream', json.dumps(state))


if __name__ == '__main__':
    unittest.main()
