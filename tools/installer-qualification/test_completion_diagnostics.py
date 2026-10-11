"""Exercise the original completion wait and strict failure-only phase projection."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import runner as R
G = R.E.guest
spec = importlib.util.spec_from_file_location('completion_active_guest', Path(__file__).with_name('active-guest.py'))
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
PRIVATE = 'password=private-account; Transcript: private-audio; תמלול: private-hebrew'


class CompletionFixture:
    def __init__(self):
        installer = A.installer_type(G)
        self.value = installer.__new__(installer)
        self.value.deadline = 5000
        self.value.started_ns = 1
        self.value.diagnostic_phase = 'completion'
        self.identities = {'daemon': {'pid': 20}}
        self.keyboard = {'synthetic-keyboard': True}
        self.value.safe_config = {'synthetic-config': True}
        self.value.baseline = {'identities': self.identities, 'keyboard_files': self.keyboard}
        self.engine = {'hello': {'state': 'done'}, 'install': {'options': {'failed': False, 'attention': False}}}
        self.gui = {'page': 'done', 'current': 'done', 'percent': 100}
        self.fail = None
        self.error = None
        self.not_done_samples = 0
        self.calls = []
        self.value.rpc = SimpleNamespace(snapshot=self.snapshot, config=lambda: self.observe('config', self.value.safe_config))
        self.value.ipc = lambda method: self.observe('gui', json.dumps(self.gui))
        self.value.identities = lambda: self.observe('identities', self.identities)
        self.value.keyboard_files = lambda: self.observe('keyboard', self.keyboard)
        self.clock = 0

    def observe(self, operation, result):
        self.calls.append(operation)
        if operation == self.fail:
            raise self.error
        return result

    def snapshot(self):
        value = self.observe('snapshot', self.engine)
        if self.not_done_samples:
            self.not_done_samples -= 1
            value = copy.deepcopy(value)
            value['hello']['state'] = 'installing'
        return value

    def advance_to_timeout(self, seconds):
        assert seconds == .2
        self.clock = 2401

class CompletionControls(unittest.TestCase):
    def projected(self, error, phase):
        masked = G.masked_active_error(error, phase)
        codes = R.primary_reported_codes({'errors': [masked]}, True)
        self.assertIn('installer-reported-active-primary-phase-' + phase, codes)
        for private in ('private-account', 'private-audio', 'private-hebrew', 'password=', 'Transcript:', 'תמלול:'):
            self.assertNotIn(private, masked)
            self.assertNotIn(private, '\n'.join(codes))
        return codes

    def test_original_wait_times_out_with_last_nested_operation_and_private_mask(self):
        cases = (
            ('not-done', 'completion-wait'),
            ('snapshot', 'completion-snapshot'),
            ('engine', 'completion-engine-guard'),
            ('gui', 'completion-gui-state'),
            ('gui-guard', 'completion-gui-guard'),
            ('identities', 'completion-identities'),
            ('config', 'completion-identity-guard'),
            ('identity-guard', 'completion-identity-guard'),
            ('result', 'completion-result'),
        )
        for operation, phase in cases:
            with self.subTest(operation=operation):
                fixture = CompletionFixture()
                if operation == 'not-done': fixture.not_done_samples = 1
                elif operation == 'engine': fixture.engine['install']['options']['attention'] = True
                elif operation == 'gui-guard': fixture.gui['percent'] = 99
                elif operation == 'identity-guard': fixture.value.baseline['identities'] = {'foreign': True}
                elif operation == 'result':
                    original = fixture.value.keyboard_files
                    count = 0
                    def keyboard():
                        nonlocal count
                        count += 1
                        if count == 2: raise RuntimeError(PRIVATE)
                        return original()
                    fixture.value.keyboard_files = keyboard
                else:
                    fixture.fail = operation
                    fixture.error = RuntimeError(PRIVATE)
                stdout = io.StringIO()
                with patch.object(G.time, 'monotonic', side_effect=lambda: fixture.clock), \
                        patch.object(G.time, 'sleep', side_effect=fixture.advance_to_timeout), \
                        contextlib.redirect_stdout(stdout), self.assertRaises(RuntimeError) as caught:
                    fixture.value.finish_install()
                self.assertEqual(fixture.clock, 2401)
                self.assertTrue(caught.exception.args[0].startswith('same real installation did not finish within its separate bound'))
                self.assertEqual(fixture.value.diagnostic_phase, phase)
                self.projected(caught.exception, phase)
                self.assertEqual(stdout.getvalue(), '')

    def test_actual_wait_success_polls_and_restores_caller_phase_with_original_result(self):
        fixture = CompletionFixture()
        fixture.not_done_samples = 1
        fixture.value.diagnostic_phase = 'output-0'
        def sleep(seconds):
            self.assertEqual(seconds, .2)
            self.assertEqual(fixture.value.diagnostic_phase, 'completion-wait')
            fixture.clock += seconds
        with patch.object(G.time, 'monotonic', side_effect=lambda: fixture.clock), \
                patch.object(G.time, 'monotonic_ns', return_value=101), patch.object(G.time, 'sleep', side_effect=sleep):
            result = fixture.value.finish_install()
        self.assertEqual(fixture.value.diagnostic_phase, 'output-0')
        self.assertEqual(result, {'engine': fixture.engine, 'identities': fixture.identities,
            'config': fixture.value.safe_config, 'keyboard_files': fixture.keyboard, 'gui': fixture.gui, 'elapsed_ns': 100})
        self.assertEqual(fixture.calls, ['snapshot', 'snapshot', 'gui', 'identities', 'config', 'keyboard', 'keyboard'])

    def test_uncaught_private_errors_and_cancellation_keep_exact_original_exception(self):
        for operation, phase in (('snapshot', 'completion-snapshot'), ('gui', 'completion-gui-state'),
                                  ('identities', 'completion-identities'), ('config', 'completion-identity-guard')):
            for error in (TypeError(PRIVATE), KeyboardInterrupt(PRIVATE), SystemExit(PRIVATE)):
                with self.subTest(operation=operation, error=type(error).__name__):
                    fixture = CompletionFixture()
                    fixture.fail = operation
                    fixture.error = error
                    with patch.object(G.time, 'monotonic', side_effect=lambda: fixture.clock), \
                            patch.object(G.time, 'sleep', side_effect=AssertionError('cancellation must not retry')), \
                            self.assertRaises(type(error)) as caught:
                        fixture.value.finish_install()
                    self.assertIs(caught.exception, error)
                    self.assertEqual(error.args, (PRIVATE,))
                    self.assertEqual(fixture.value.diagnostic_phase, phase)
                    self.projected(error, phase)

    def test_original_wait_exception_is_preserved_and_not_formatted_by_completion(self):
        error = RuntimeError(PRIVATE)
        fixture = CompletionFixture()
        def original_wait(fn, seconds, reason):
            self.assertEqual(seconds, 40 * 60)
            self.assertEqual(reason, 'same real installation did not finish within its separate bound')
            self.assertEqual(fixture.value.diagnostic_phase, 'completion-wait')
            raise error
        fixture.value.wait = original_wait
        with self.assertRaises(RuntimeError) as caught:
            fixture.value.finish_install()
        self.assertIs(caught.exception, error)
        self.assertEqual(error.args, (PRIVATE,))
        self.projected(error, 'completion-wait')

    def test_actual_run_keeps_failure_and_masks_private_wait_error_in_report_and_stdout(self):
        fixture = CompletionFixture()
        value = fixture.value
        fixture.fail = 'snapshot'
        fixture.error = RuntimeError(PRIVATE)
        value.context = {}
        value.boot_id = 'synthetic-boot'
        value.uid = 1000
        value.session = 'synthetic-session'
        value.original_vt = 1
        value.results = []
        value.samples = []
        value.capture_count = 4
        value.password = PRIVATE
        value.gui_fd = None
        value.native = SimpleNamespace(SecurityInterval=lambda: SimpleNamespace(finish=lambda: {'selinux': 'Enforcing'}))
        value.prepare = lambda: value.baseline
        value.vt_cycle = lambda cycle: {'kind': 'vt', 'cycle': cycle, 'status': 'passed'}
        value.output_cycle = lambda cycle: {'kind': 'output', 'cycle': cycle, 'status': 'passed'}
        value.cleanup = lambda: {'original_vt_restored': True, 'engine_retained': True, 'errors': []}
        value.rpc.close = lambda: None
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as directory:
            value.root = Path(directory)
            with patch.object(G.time, 'monotonic', side_effect=lambda: fixture.clock), \
                    patch.object(G.time, 'sleep', side_effect=fixture.advance_to_timeout), contextlib.redirect_stdout(stdout):
                report = value.run()
                R.diagnose_report(report, True)
            self.assertEqual(report['status'], 'failed')
            self.assertIs(report['release_acceptance'], False)
            self.assertNotIn('completion', report)
            self.assertIsNone(value.password)
            self.assertEqual(report['errors'], [G.masked_active_error(RuntimeError('unobserved private cause'), 'completion-snapshot')])
            private_report = (value.root / 'installer-report.json').read_bytes()
            self.assertEqual(json.loads(private_report), report)
            self.assertNotIn('private', private_report.decode())
        self.assertIn('installer-reported-active-primary-phase-completion-snapshot', stdout.getvalue())
        self.assertNotIn('private', stdout.getvalue())


if __name__ == '__main__':
    unittest.main()
