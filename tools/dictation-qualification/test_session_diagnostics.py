"""Synthetic setup failures only: no VM, microphone, model or transcription."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest import mock

from test_contract import FIXTURES, c, synthetic

spec = importlib.util.spec_from_file_location('dictation_session_diagnostics', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class PrivateError(c.Invalid):
    def __str__(self):
        raise AssertionError('exception text must remain private')

    def __repr__(self):
        raise AssertionError('exception representation must remain private')


class SessionDiagnosticControls(unittest.TestCase):
    def checker(self, phase='online-installed', profile='turbo-q5-v3'):
        checker = guest.Checker.__new__(guest.Checker)
        checker.report = synthetic(phase, profile=profile)
        observations = {gate['id']: copy.deepcopy(gate['observations']) for gate in checker.report['gates']}
        checker.report['gates'] = []
        checker.report['samples'] = []
        checker.context = checker.report['context']
        checker.profile_id = profile
        checker.gates = c.gates(phase, profile)
        operations = {'security': 'selinux-enforcing', 'encrypted': 'encrypted-installed-boot',
                      'ready': 'online-installer-ready' if phase == 'online-installed' else 'recovered-ready',
                      'payload': 'installed-payload-integrity', 'avcs': 'no-new-avcs',
                      'offline': 'local-offline-transcription'}
        for method, name in operations.items():
            setattr(checker, method, mock.Mock(return_value=observations.get(name, {})))
        checker.status = mock.Mock()
        checker.route = mock.Mock()
        checker.window_start = mock.Mock()
        return checker

    def setup(self, checker, stage=None, error=None):
        accuracy = SimpleNamespace(Invalid=c.Invalid, load_fixtures=mock.Mock(return_value=[]))
        spec = SimpleNamespace(loader=SimpleNamespace(exec_module=mock.Mock()))
        if stage == 'accuracy-module-import':
            spec.loader.exec_module.side_effect = error
        elif stage == 'fixture-bundle-validation':
            accuracy.load_fixtures.side_effect = error
        elif stage in ('broker-cancel', 'cpu-backend-selection'):
            action = 'cancel' if stage == 'broker-cancel' else 'set-backend'
            def status(command, *args, **kwargs):
                if command == action:
                    raise error
            checker.status.side_effect = status
        elif stage == 'virtual-microphone-route':
            checker.route.side_effect = error
        elif stage == 'receiver-window':
            checker.window_start.side_effect = error
        return (mock.patch.object(guest.importlib.util, 'spec_from_file_location', return_value=spec),
                mock.patch.object(guest.importlib.util, 'module_from_spec', return_value=accuracy))

    def failed_report(self, checker, expected_code):
        report = checker.report
        self.assertEqual(report['status'], 'failed')
        self.assertIs(report['release_acceptance'], False)
        self.assertEqual(report['samples'], [])
        self.assertEqual({gate['id'] for gate in report['gates']}, checker.gates)
        unrun = [gate for gate in report['gates'] if gate['status'] == 'unrun']
        self.assertTrue(unrun)
        self.assertEqual({gate['code'] for gate in unrun}, {expected_code})
        self.assertTrue(all(gate['observations'] == {} for gate in unrun))
        c.validate(report, checker.context, require_passed=False, fixture_manifest=FIXTURES)
        with self.assertRaises(c.Invalid):
            c.validate(report, checker.context, require_passed=True, fixture_manifest=FIXTURES)
        return report

    def test_each_actual_setup_stage_remains_failed_without_leaking_exception(self):
        for phase in ('online-installed', 'recovered-offline'):
            for profile in c.PROFILES:
                for stage in guest.SESSION_PREFLIGHT_STAGES:
                    with self.subTest(phase=phase, profile=profile, stage=stage):
                        checker = self.checker(phase, profile)
                        secret = 'synthetic-private-transcript-argv-stderr'
                        error = PrivateError(secret)
                        import_spec, module = self.setup(checker, stage, error)
                        with import_spec, module, mock.patch.object(guest.subprocess, 'run', side_effect=AssertionError('unexpected command')):
                            checker.execute()
                        label = 'fixture-bundle-validation-failed' if stage == 'fixture-bundle-validation' else 'invalid'
                        report = self.failed_report(checker, 'session-' + stage + '-' + label)
                        self.assertNotIn(secret, json.dumps(report))
                        checker.offline.assert_not_called()

    def test_all_existing_caught_classes_produce_only_fixed_codes(self):
        errors = (c.Invalid('private'), OSError('private'), ValueError('private'),
                  guest.subprocess.TimeoutExpired(['private-argv'], 1, output=b'private', stderr=b'private'),
                  KeyError('private'), TypeError('private'))
        labels = ('invalid', 'os-error', 'value-error', 'timeout', 'key-error', 'type-error')
        for stage in guest.SESSION_PREFLIGHT_STAGES:
            for error, label in zip(errors, labels):
                with self.subTest(stage=stage, label=label):
                    code = guest.session_diagnostic_code(stage, error)
                    self.assertEqual(code, 'session-' + stage + '-' + label)
                    self.assertRegex(code, '^[a-z0-9-]{1,80}$')
        self.assertEqual(guest.session_diagnostic_code('accuracy-module-import', FileNotFoundError('private')),
                         'session-accuracy-module-import-os-error')

    def test_unsupported_stages_and_error_classes_fail_closed(self):
        for stage in (None, '', 'private-transcript', 1, [], {}):
            with self.subTest(stage=stage), self.assertRaisesRegex(c.Invalid, '^unknown-session-preflight-stage$'):
                guest.session_diagnostic_code(stage, c.Invalid('private'))
        with self.assertRaisesRegex(c.Invalid, '^unknown-session-preflight-error-type$'):
            guest.session_diagnostic_code('receiver-window', RuntimeError('private'))

    def test_invalid_subtypes_use_only_stage_specific_trusted_literals(self):
        self.assertEqual(set(guest.SESSION_INVALID_CODES), set(guest.SESSION_PREFLIGHT_STAGES))
        for stage, codes in guest.SESSION_INVALID_CODES.items():
            for code in codes:
                with self.subTest(stage=stage, code=code):
                    result = guest.session_diagnostic_code(stage, PrivateError(code))
                    self.assertEqual(result, 'session-' + stage + '-' + code)
                    self.assertRegex(result, '^[a-z0-9-]{1,80}$')
        self.assertEqual(guest.session_diagnostic_code('broker-cancel', c.Invalid('loopback-process-died')),
                         'session-broker-cancel-invalid')

    def test_arbitrary_invalid_args_use_fixed_fallback_without_formatting(self):
        class PrivateString(str):
            def __eq__(self, other):
                raise AssertionError('untrusted string comparison')
        for error in (PrivateError('command-failed-private-transcript'), PrivateError('command-failed', 'private'),
                      PrivateError(b'command-failed'), PrivateError({'transcript': 'private'}),
                      PrivateError(PrivateString('command-failed')), PrivateError()):
            self.assertEqual(guest.session_diagnostic_code('virtual-microphone-route', error),
                             'session-virtual-microphone-route-invalid')

    def test_known_route_failure_reports_literal_subtype_and_keeps_gates_unrun(self):
        checker = self.checker()
        import_spec, module = self.setup(checker, 'virtual-microphone-route', PrivateError('loopback-flags-unavailable'))
        with import_spec, module:
            checker.execute()
        self.failed_report(checker, 'session-virtual-microphone-route-loopback-flags-unavailable')

    def test_execute_records_each_existing_caught_class_without_exception_payload(self):
        for error_class, label in guest.SESSION_ERROR_TYPES:
            with self.subTest(label=label):
                checker = self.checker()
                error = (error_class(['synthetic-private-argv'], 1, output=b'synthetic-private-output',
                                     stderr=b'synthetic-private-stderr')
                         if error_class is guest.subprocess.TimeoutExpired else error_class('synthetic-private-text'))
                import_spec, module = self.setup(checker, 'virtual-microphone-route', error)
                with import_spec, module:
                    checker.execute()
                report = self.failed_report(checker, 'session-virtual-microphone-route-' + label)
                self.assertNotIn('synthetic-private', json.dumps(report))

    def test_execute_does_not_expand_original_caught_exception_set(self):
        checker = self.checker()
        import_spec, module = self.setup(checker, 'receiver-window', RuntimeError('synthetic-uncaught'))
        with import_spec, module, self.assertRaisesRegex(RuntimeError, '^synthetic-uncaught$'):
            checker.execute()

    def test_post_setup_failure_does_not_reuse_stale_stage(self):
        checker = self.checker()
        checker.offline.side_effect = c.Invalid('synthetic-session-isolation-failure')
        import_spec, module = self.setup(checker)
        with import_spec, module:
            checker.execute()
        self.assertIsNone(checker.session_preflight_stage)
        self.failed_report(checker, 'prerequisite-or-collector-failed')
        local = next(gate for gate in checker.report['gates'] if gate['id'] == 'local-offline-transcription')
        self.assertEqual(local['status'], 'failed')
        self.assertEqual(local['code'], 'synthetic-session-isolation-failure')

    def test_readiness_and_integrity_failures_keep_original_reason(self):
        for prerequisite in ('ready', 'payload'):
            with self.subTest(prerequisite=prerequisite):
                checker = self.checker()
                getattr(checker, prerequisite).side_effect = c.Invalid('synthetic-prerequisite-failure')
                checker.session = mock.Mock(side_effect=AssertionError('session must not start'))
                checker.execute()
                self.failed_report(checker, 'prerequisite-or-collector-failed')
                checker.session.assert_not_called()

    def test_non_session_phase_gates_and_codes_remain_unchanged(self):
        for phase in ('live', 'offline-installed', 'recovery'):
            with self.subTest(phase=phase):
                checker = self.checker(phase)
                source = synthetic(phase)
                observations = {gate['id']: gate['observations'] for gate in source['gates']}
                for method, name in (('absence', 'live-payload-model-absent'), ('unavailable', 'live-controller-unavailable'),
                                     ('pending', 'offline-setup-pending'), ('os_healthy', 'offline-os-healthy'),
                                     ('recovery', 'explicit-service-recovery-ready')):
                    setattr(checker, method, mock.Mock(return_value=observations.get(name, {})))
                checker.session = mock.Mock(side_effect=AssertionError('session must not start'))
                checker.execute()
                self.assertEqual(checker.report['status'], 'passed')
                self.assertTrue(all(gate['code'] == 'observed' for gate in checker.report['gates']))
                c.validate(checker.report, checker.context, require_passed=True, fixture_manifest=FIXTURES)
                checker.session.assert_not_called()


if __name__ == '__main__':
    unittest.main()
