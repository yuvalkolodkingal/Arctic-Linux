"""Fixed, transcript-free gate and collector failure projection controls."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location(
    'direct_voxtype_gate_diagnostics', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)


class PrivateInvalid(guest.Invalid):
    def __getattribute__(self, name):
        if name in ('args', '__class__'):
            raise AssertionError('private exception attribute read')
        return BaseException.__getattribute__(self, name)
    def __str__(self):
        raise AssertionError('private exception text formatted')
    def __repr__(self):
        raise AssertionError('private exception represented')
    def __eq__(self, _other):
        raise AssertionError('private exception compared')


def hostile_exception(base, constructor=()):
    accesses = []
    class HostileMeta(type):
        def __getattribute__(cls, name):
            if name == '__mro__':
                accesses.append('metaclass-mro')
                raise AssertionError('foreign metaclass accessor')
            return type.__getattribute__(cls, name)
    class Hostile(base, metaclass=HostileMeta):
        def __getattribute__(self, name):
            if name in ('__class__', 'args'):
                accesses.append(name)
                raise AssertionError('foreign exception accessor')
            return BaseException.__getattribute__(self, name)
        def __str__(self):
            accesses.append('str')
            raise AssertionError('foreign exception text')
        def __repr__(self):
            accesses.append('repr')
            raise AssertionError('foreign exception representation')
        def __eq__(self, _other):
            accesses.append('equality')
            raise AssertionError('foreign exception equality')
    return Hostile(*constructor), accesses


class GateDiagnosticControls(unittest.TestCase):
    def checker(self, gate):
        checker = guest.Checker.__new__(guest.Checker)
        checker.gates = {gate}
        checker.report = {'gates': []}
        return checker

    @staticmethod
    def raising(error):
        def run():
            raise error
        return run

    def test_every_gate_and_caught_family_projects_one_fixed_code(self):
        errors = (
            (PrivateInvalid('sensitive-canary transcript'), 'invalid'),
            (OSError('sensitive-canary path'), 'os-error'),
            (ValueError('sensitive-canary value'), 'value-error'),
            (subprocess.TimeoutExpired(['sensitive-canary'], 1,
                                       output=b'sensitive-canary'), 'timeout'),
            (KeyError('sensitive-canary key'), 'key-error'),
            (TypeError('sensitive-canary type'), 'type-error'),
        )
        self.assertEqual(set(guest.GATE_FAILURE_CODES), set(guest.EXPECTED_KINDS))
        for gate in sorted(guest.EXPECTED_KINDS):
            for error, label in errors:
                with self.subTest(gate=gate, label=label):
                    checker = self.checker(gate)
                    self.assertFalse(checker.gate(gate, self.raising(error)))
                    result = checker.report['gates'][0]
                    self.assertEqual(result['status'], 'failed')
                    self.assertEqual(result['code'], 'gate-' + gate + '-' + label)
                    self.assertRegex(result['code'], r'^[a-z0-9-]{1,80}$')
                    self.assertNotIn('sensitive-canary', json.dumps(result))

    def test_hostile_exception_instance_and_metaclass_are_never_observed(self):
        families = (
            (guest.Invalid, (), 'invalid'),
            (OSError, ('private',), 'os-error'),
            (ValueError, ('private',), 'value-error'),
            (subprocess.TimeoutExpired, (['private'], 1), 'timeout'),
            (KeyError, ('private',), 'key-error'),
            (TypeError, ('private',), 'type-error'),
        )
        for base, constructor, label in families:
            error, accesses = hostile_exception(base, constructor)
            checker = self.checker('cancel-discards')
            self.assertFalse(checker.gate('cancel-discards', self.raising(error)))
            self.assertEqual(checker.report['gates'][0]['code'],
                             'gate-cancel-discards-' + label)
            self.assertEqual(accesses, [])

    def test_only_exact_microphone_fixture_signal_is_unrun(self):
        checker = self.checker('microphone-disconnect-error')
        self.assertFalse(checker.gate(
            'microphone-disconnect-error',
            self.raising(guest.MicrophoneIsolationUnavailable())))
        result = checker.report['gates'][0]
        self.assertEqual(result['status'], 'unrun')
        self.assertEqual(result['code'],
                         'gate-microphone-disconnect-error-isolation-unavailable')
        class Derived(guest.MicrophoneIsolationUnavailable):
            pass
        checker = self.checker('microphone-disconnect-error')
        checker.gate('microphone-disconnect-error', self.raising(Derived('private')))
        self.assertEqual(checker.report['gates'][0]['status'], 'failed')
        self.assertEqual(checker.report['gates'][0]['code'],
                         'gate-microphone-disconnect-error-invalid')

    def test_state_contract_reports_allowed_cardinality_not_observed_count(self):
        checker = guest.Checker.__new__(guest.Checker)
        checker.state = lambda: 'idle'
        with tempfile.TemporaryDirectory() as temp:
            unit = Path(temp) / 'voxtype.service'
            unit.write_text('ConditionPathExists=%h/.config/voxtype/config.toml\n'
                            'UMask=0077\nRestrictAddressFamilies=AF_UNIX\n'
                            'UnsetEnvironment=RUST_LOG VOXTYPE_CONFIG\n'
                            'ExecStart=/usr/bin/voxtype --config %h/.config/voxtype/config.toml -q daemon\n')
            original, guest.UNIT = guest.UNIT, unit
            try:
                self.assertEqual(checker.state_contract(), {'allowed_state_count': 4})
            finally:
                guest.UNIT = original


class CollectorDiagnosticControls(unittest.TestCase):
    def test_every_stage_and_family_has_a_fixed_code(self):
        families = (
            (guest.Invalid, (), 'invalid'), (OSError, ('private',), 'os-error'),
            (ValueError, ('private',), 'value-error'),
            (subprocess.TimeoutExpired, (['private'], 1), 'timeout'),
            (KeyError, ('private',), 'key-error'),
            (TypeError, ('private',), 'type-error'),
        )
        for stage in guest.COLLECTOR_SETUP_STAGES:
            for base, constructor, label in families:
                error, accesses = hostile_exception(base, constructor)
                code = guest.collector_diagnostic_code(stage, error)
                self.assertEqual(code, 'collector-' + stage + '-' + label)
                self.assertEqual(accesses, [])
                self.assertNotIn('private', code)

    def test_unknown_stage_and_error_family_fail_closed(self):
        with self.assertRaisesRegex(guest.Invalid, '^unknown-collector-setup-stage$'):
            guest.collector_diagnostic_code('private-stage', guest.Invalid())
        error, accesses = hostile_exception(RuntimeError, ('private',))
        self.assertEqual(guest.collector_diagnostic_code('integration', error),
                         'collector-unknown')
        self.assertEqual(accesses, [])

    def test_stage_marker_accepts_only_source_inventory(self):
        old = guest.COLLECTOR_SETUP_STAGE
        try:
            for stage in guest.COLLECTOR_SETUP_STAGES:
                guest.mark_collector_setup(stage)
                self.assertEqual(guest.COLLECTOR_SETUP_STAGE, stage)
            with self.assertRaisesRegex(guest.Invalid, '^unknown-collector-setup-stage$'):
                guest.mark_collector_setup('private-stage')
        finally:
            guest.COLLECTOR_SETUP_STAGE = old


if __name__ == '__main__':
    unittest.main()
