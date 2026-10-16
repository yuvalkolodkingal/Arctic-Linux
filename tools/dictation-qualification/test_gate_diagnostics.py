"""Fixed, transcript-free gate and collector failure projection controls."""
import importlib.util
import inspect
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

    def test_transcription_failures_project_only_fixed_stage_number_and_family(self):
        families = (
            (PrivateInvalid('sensitive-canary transcript'), 'invalid'),
            (OSError('sensitive-canary path'), 'os-error'),
            (ValueError('sensitive-canary value'), 'value-error'),
            (subprocess.TimeoutExpired(['sensitive-canary'], 1,
                                       output=b'sensitive-canary'), 'timeout'),
            (KeyError('sensitive-canary key'), 'key-error'),
            (TypeError('sensitive-canary type'), 'type-error'),
        )
        gate = 'cpu-hebrew-transcription-insertion'
        for stage, number in guest.TRANSCRIPTION_FAILURE_STAGES.items():
            for error, label in families:
                with self.subTest(stage=stage, label=label):
                    checker = self.checker(gate)
                    action = lambda: checker.transcription_stage(
                        stage, self.raising(error))
                    self.assertFalse(checker.gate(gate, action))
                    result = checker.report['gates'][0]
                    self.assertEqual(result['code'], 'gate-' + gate + '-' + label)
                    self.assertEqual(result['observations'], {'failure_stage': number})
                    self.assertNotIn('sensitive-canary', json.dumps(result))

    def test_transcription_stage_inventory_is_closed(self):
        checker = self.checker('cpu-english-transcription-insertion')
        with self.assertRaisesRegex(guest.Invalid,
                                    '^unknown-transcription-failure-stage$'):
            checker.transcription_stage('private-stage', lambda: None)
        with self.assertRaisesRegex(guest.Invalid,
                                    '^unknown-transcription-failure-family$'):
            guest.TranscriptionStageFailure('terminal-state', 'private-family')

    def test_microphone_failures_project_only_fixed_stage_number_and_family(self):
        gate = 'microphone-disconnect-error'
        checker = self.checker(gate)
        error = subprocess.TimeoutExpired(['sensitive-canary'], 1,
                                          output=b'sensitive-canary')
        action = lambda: checker.microphone_stage(
            'actionable-error', self.raising(error))
        self.assertFalse(checker.gate(gate, action))
        result = checker.report['gates'][0]
        self.assertEqual(result['code'], 'gate-' + gate + '-timeout')
        self.assertEqual(result['observations'], {
            'failure_stage': guest.MICROPHONE_FAILURE_STAGES['actionable-error']})
        self.assertNotIn('sensitive-canary', json.dumps(result))

    def test_microphone_stage_inventory_is_closed(self):
        checker = self.checker('microphone-disconnect-error')
        with self.assertRaisesRegex(guest.Invalid, '^unknown-microphone-failure-stage$'):
            checker.microphone_stage('private-stage', lambda: None)
        with self.assertRaisesRegex(guest.Invalid, '^unknown-microphone-failure-family$'):
            guest.MicrophoneStageFailure('actionable-error', 'private-family')

    def test_gpu_failures_project_only_fixed_stage_number_and_family(self):
        gate = guest.MODERN_GPU_GATE
        checker = self.checker(gate)
        error = subprocess.TimeoutExpired(['sensitive-canary'], 1,
                                          output=b'sensitive-canary')
        action = lambda: checker.gpu_stage(
            'gpu-failure-screen', self.raising(error))
        self.assertFalse(checker.gate(gate, action))
        result = checker.report['gates'][0]
        self.assertEqual(result['code'], 'gate-' + gate + '-timeout')
        self.assertEqual(result['observations'], {
            'failure_stage': guest.GPU_FAILURE_STAGES['gpu-failure-screen']})
        self.assertNotIn('sensitive-canary', json.dumps(result))

    def test_gpu_stage_inventory_is_closed(self):
        checker = self.checker(guest.MODERN_GPU_GATE)
        with self.assertRaisesRegex(guest.Invalid, '^unknown-gpu-failure-stage$'):
            checker.gpu_stage('private-stage', lambda: None)
        with self.assertRaisesRegex(guest.Invalid, '^unknown-gpu-failure-family$'):
            guest.GpuStageFailure('gpu-failure-screen', 'private-family')

    def test_first_recovery_screen_projects_only_closed_substage_and_family(self):
        errors = (
            (PrivateInvalid('sensitive-canary transcript'), 'invalid'),
            (OSError('sensitive-canary path'), 'os-error'),
            (ValueError('sensitive-canary value'), 'value-error'),
            (subprocess.TimeoutExpired(['sensitive-canary'], 1,
                                       output=b'sensitive-canary'), 'timeout'),
            (KeyError('sensitive-canary key'), 'key-error'),
            (TypeError('sensitive-canary type'), 'type-error'),
        )
        for substage, number in guest.RECOVERY_SCREEN_FAILURE_SUBSTAGES.items():
            for error, label in errors:
                with self.subTest(substage=substage, label=label):
                    checker = self.checker(guest.MODERN_GPU_GATE)
                    self.assertFalse(checker.gate(
                        guest.MODERN_GPU_GATE,
                        lambda: checker.recovery_screen_stage(
                            'gpu_failure', substage, self.raising(error))))
                    result = checker.report['gates'][0]
                    self.assertEqual(result['code'],
                                     'gate-' + guest.MODERN_GPU_GATE + '-' + label)
                    self.assertEqual(result['observations'], {
                        'failure_stage': guest.GPU_FAILURE_STAGES['gpu-failure-screen'],
                        'failure_substage': number})
                    self.assertNotIn('sensitive-canary', json.dumps(result))

    def test_recovery_screen_substage_inventory_is_closed_and_first_screen_only(self):
        checker = self.checker(guest.MODERN_GPU_GATE)
        with self.assertRaisesRegex(guest.Invalid,
                                    '^unknown-recovery-screen-capture-stage$'):
            checker.recovery_screen_stage('private', 'preconditions', lambda: None)
        with self.assertRaisesRegex(guest.Invalid,
                                    '^unknown-recovery-screen-failure-substage$'):
            checker.recovery_screen_stage('gpu_failure', 'private', lambda: None)
        private = PrivateInvalid('sensitive-canary transcript')
        with self.assertRaises(PrivateInvalid) as raised:
            checker.recovery_screen_stage(
                'cpu_ready', 'preconditions', self.raising(private))
        self.assertIs(raised.exception, private)

        source = inspect.getsource(guest.Checker.recovery_screen)
        for substage in guest.RECOVERY_SCREEN_FAILURE_SUBSTAGES:
            self.assertEqual(source.count("stage, '" + substage + "'"), 1)

    def test_closed_engine_substage_projects_without_command_output(self):
        cpu_gate = 'cpu-hebrew-transcription-insertion'
        checker = self.checker(cpu_gate)
        failure = guest.TranscriptionStageFailure('engine-profile', 'invalid', 704)
        self.assertFalse(checker.gate(cpu_gate, self.raising(failure)))
        self.assertEqual(checker.report['gates'][0]['observations'], {
            'failure_stage': guest.TRANSCRIPTION_FAILURE_STAGES['engine-profile'],
            'failure_substage': 704})

    def test_gpu_wrapper_preserves_nested_transcription_stage(self):
        checker = self.checker(guest.MODERN_GPU_GATE)
        nested = guest.TranscriptionStageFailure('text-delivery', 'invalid')
        with self.assertRaises(guest.TranscriptionStageFailure) as raised:
            checker.gpu_stage('cpu-ready-screen', self.raising(nested))
        self.assertIs(raised.exception, nested)

    def test_state_contract_reports_allowed_cardinality_not_observed_count(self):
        checker = guest.Checker.__new__(guest.Checker)
        checker.state = lambda: 'idle'
        with tempfile.TemporaryDirectory() as temp:
            unit = Path(temp) / 'voxtype.service'
            unit.write_text('ConditionPathExists=%h/.config/voxtype/config.toml\n'
                            'ConditionPathExists=%t/arctic-dictation/voxtype-session-started-v1\n'
                            'UMask=0077\nRestrictAddressFamilies=AF_UNIX\n'
                            'UnsetEnvironment=' + ' '.join(sorted(guest.SERVICE_UNSET_ENV)) + '\n'
                            'ExecStart=/usr/bin/voxtype --config %h/.config/voxtype/config.toml -q daemon\n')
            original, guest.UNIT = guest.UNIT, unit
            try:
                self.assertEqual(checker.state_contract(), {'allowed_state_count': 4})
                unit.write_text(unit.read_text().replace('VOXTYPE_REMOTE_ENDPOINT ', ''))
                with self.assertRaisesRegex(guest.Invalid, '^upstream-service-privacy-contract$'):
                    checker.state_contract()
            finally:
                guest.UNIT = original

    def test_service_override_inventory_covers_remote_hotkey_output_and_logging(self):
        expected = {
            'RUST_LOG', 'VOXTYPE_CONFIG', 'VOXTYPE_ENGINE', 'VOXTYPE_MODEL',
            'VOXTYPE_LANGUAGE', 'VOXTYPE_TRANSLATE', 'VOXTYPE_THREADS',
            'VOXTYPE_ON_DEMAND_LOADING', 'VOXTYPE_GPU_ISOLATION',
            'VOXTYPE_GPU_DEVICE', 'VOXTYPE_FLASH_ATTENTION', 'VOXTYPE_VULKAN_DEVICE',
            'VOXTYPE_CPU_BACKUP', 'VOXTYPE_REMOTE_ENDPOINT',
            'VOXTYPE_WHISPER_API_KEY', 'SONIOX_API_KEY', 'VOXTYPE_OPENVINO_DIR',
            'VOXTYPE_OPENVINO_DEVICE', 'VOXTYPE_OPENVINO_MODEL',
            'VOXTYPE_COHERE_MODEL_DIR', 'VOXTYPE_MEETING_DIARIZATION',
            'VOXTYPE_HOTKEY', 'VOXTYPE_HOTKEY_ENABLED', 'VOXTYPE_CANCEL_KEY',
            'VOXTYPE_AUDIO_DEVICE', 'VOXTYPE_MAX_DURATION_SECS',
            'VOXTYPE_AUDIO_FEEDBACK', 'VOXTYPE_PAUSE_MEDIA', 'VOXTYPE_DUCK_MEDIA',
            'VOXTYPE_DUCK_MEDIA_VOLUME_PERCENT', 'VOXTYPE_DUCK_MEDIA_FADE_MS',
            'VOXTYPE_OUTPUT_MODE', 'VOXTYPE_APPEND_TEXT', 'VOXTYPE_AUTO_SUBMIT',
            'VOXTYPE_SHIFT_ENTER_NEWLINES', 'VOXTYPE_PRE_TYPE_DELAY',
            'VOXTYPE_TYPE_DELAY', 'VOXTYPE_FALLBACK_TO_CLIPBOARD',
            'VOXTYPE_PASTE_KEYS', 'VOXTYPE_WTYPE_SHIFT_PREFIX',
            'VOXTYPE_DOTOOL_XKB_LAYOUT', 'VOXTYPE_DOTOOL_XKB_VARIANT',
            'VOXTYPE_EITYPE_XKB_LAYOUT', 'VOXTYPE_EITYPE_XKB_VARIANT',
            'VOXTYPE_SMART_AUTO_SUBMIT', 'VOXTYPE_FILTER_FILLERS',
            'VOXTYPE_SPOKEN_PUNCTUATION', 'VOXTYPE_RESTORE_CLIPBOARD',
            'VOXTYPE_RESTORE_CLIPBOARD_DELAY_MS', 'VOXTYPE_CONTEXT',
        }
        self.assertEqual(guest.SERVICE_UNSET_ENV, expected)


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
