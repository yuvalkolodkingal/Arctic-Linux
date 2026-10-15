"""Schema controls only; no VM, daemon, setup, model or microphone is used."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import contract as c


def fixture_bytes():
    return json.dumps({'schema': 'arctic-dictation-fixtures-v1',
        'dataset': {'commit': '70bb2e84b976b7e960aa89f1c648e09c59f894dd'},
        'samples': [{'language': language, 'source_row': row,
                     'wav_sha256': str(row + 1) * 64, 'reference_sha256': 'a' * 64,
                     'audio_frames': 16000, 'sample_rate': 16000}
                    for language in ('en', 'he') for row in range(5)]},
        sort_keys=True).encode()


FIXTURES = fixture_bytes()


def declared(phase='live', installation=1, profile='turbo-q5-v3'):
    return {'schema': c.CONTEXT_SCHEMA, 'phase': phase, 'hardware_profile': profile,
            'source_sha': 'b' * 40, 'iso_bytes': 1_000_000_000,
            'installation_id': f'00000000-0000-0000-0000-{installation:012d}',
            **{key: hashlib.sha256(FIXTURES).hexdigest() if key == 'fixture_manifest_sha256'
               else 'c' * 64 for key in c.CONTEXT_KEYS if key.endswith('_sha256')}}


def sample(profile, language, row, purpose):
    cpu_key = 'avx2' if profile == 'turbo-q5-v3' else 'cpu'
    return {'language': language, 'source_row': row, 'purpose': purpose,
            'wav_sha256': str(row + 1) * 64, 'reference_sha256': 'a' * 64,
            'hypothesis_sha256': 'e' * 64, 'elapsed_ns': 123456789,
            'audio_frames': 16000, 'sample_rate': 16000, 'reference_words': 10,
            'word_edits': 3, 'reference_chars': 20, 'char_edits': 2,
            'backend': 'cpu', 'cpu_variant': c.PROFILES[profile]['cpu_variant'],
            'binary_sha256': c.PROFILE_ASSETS[profile][cpu_key]['sha256'],
            'model_sha256': c.PROFILE_ASSETS[profile]['model']['sha256']}


def synthetic(phase='live', installation=1, boot=1, profile='turbo-q5-v3'):
    ctx = declared(phase, installation, profile)
    report = {'schema': c.SCHEMA, 'status': 'passed', 'release_acceptance': False,
              'context': ctx, 'boot_id': f'00000000-0000-0000-0000-{boot:012d}',
              'upstream': c.UPSTREAM, 'payload': {}, 'samples': [],
              'limitations': c.LIMITATIONS, 'gates': [], 'disk': {},
              'profile': c.PROFILES[profile],
              'hardware': {'profile': profile, 'v3_supported': profile == 'turbo-q5-v3',
                           'cpuinfo_sha256': 'f' * 64, 'profile_selection': 'recommended'}}
    if phase != 'live':
        report['disk'] = {key: f'00000000-0000-0000-0000-{installation:012d}'
                          for key in ('root_luks_uuid', 'root_fs_uuid', 'root_partuuid')}
    if phase in ('online-installed', 'recovery', 'recovered-offline'):
        report['payload'] = c.pinned(profile)
    for name in sorted(c.gates(phase, profile)):
        observed = dict(c.REQUIRED_OBSERVATIONS.get(name, {}))
        if name == 'installed-payload-integrity':
            observed['file_count'] = len(c.PROFILE_ASSETS[profile])
        if name == 'local-offline-transcription':
            observed['returncode'] = 7
        if name == 'recording-status-published':
            observed.update(snapshot_sha256='d' * 64, sha256='e' * 64)
        if name == c.MODERN_GPU_GATE:
            observed.update(gpu_failure_capture_ack_sha256='1' * 64,
                            cpu_ready_capture_ack_sha256='2' * 64)
        if name == 'transcript-log-notification-leak-scan':
            observed['count'] = 12
        if name == 'no-new-avcs':
            observed.update(audit_lost=0, audit_lost_before=0,
                            audit_enabled=1, audit_enabled_before=1)
        report['gates'].append({'id': name, 'status': 'passed',
                                'evidence_kind': c.EXPECTED_KINDS[name],
                                'code': 'observed', 'observations': observed})
    if phase in ('online-installed', 'recovered-offline'):
        report['samples'] = [sample(profile, language, row, 'cpu-session')
                             for language in ('en', 'he') for row in range(5)]
        report['samples'] += [sample(profile, language, 0, 'cpu-retry')
                              for language in ('en', 'he')]
    return report


class ContractControls(unittest.TestCase):
    def rejects(self, report, code):
        with self.assertRaisesRegex(c.Invalid, '^' + code + '$'):
            c.validate_report(report, report['context'], FIXTURES)

    def test_complete_direct_upstream_contract_is_not_release_acceptance(self):
        report = synthetic('online-installed')
        result = c.validate_report(report, report['context'], FIXTURES)
        self.assertTrue(result['contract_valid'])
        self.assertFalse(result['release_acceptance'])

    def test_upstream_version_commit_and_signing_fingerprint_are_fixed(self):
        for key, value in (('version', '1.0.0'), ('source_commit', '0' * 40),
                           ('signed_sums_fingerprint', '0' * 40)):
            report = synthetic('online-installed')
            report['upstream'] = dict(report['upstream'], **{key: value})
            self.rejects(report, 'report-upstream-pin')

    def test_direct_command_state_config_and_no_input_gates_are_required(self):
        report = synthetic('online-installed')
        ids = {gate['id'] for gate in report['gates']}
        self.assertTrue({'upstream-command-contract', 'upstream-state-contract',
                         'local-he-en-config', 'no-broad-input-access'} <= ids)
        for name in ('upstream-command-contract', 'upstream-state-contract',
                     'local-he-en-config', 'no-broad-input-access'):
            changed = synthetic('online-installed')
            changed['gates'] = [gate for gate in changed['gates'] if gate['id'] != name]
            self.rejects(changed, 'report-missing-duplicate-extra-gates')

    def test_gpu_failure_never_implies_cpu_fallback(self):
        report = synthetic('online-installed')
        gate = next(gate for gate in report['gates'] if gate['id'] == c.MODERN_GPU_GATE)
        gate['observations']['explicit_cpu_selected'] = False
        self.rejects(report, 'gate-contradictory-or-missing-observations')
        report = synthetic('online-installed')
        gate = next(gate for gate in report['gates'] if gate['id'] == c.MODERN_GPU_GATE)
        gate['observations']['failed_attempt_inserted'] = True
        self.rejects(report, 'gate-contradictory-or-missing-observations')

    def test_modern_gpu_gate_requires_both_recovery_screen_acknowledgements(self):
        for key in ('gpu_failure_capture_ack_sha256', 'cpu_ready_capture_ack_sha256'):
            report = synthetic('online-installed')
            gate = next(gate for gate in report['gates'] if gate['id'] == c.MODERN_GPU_GATE)
            del gate['observations'][key]
            self.rejects(report, 'recovery-screen-evidence-missing')
        report = synthetic('online-installed')
        gate = next(gate for gate in report['gates'] if gate['id'] == c.MODERN_GPU_GATE)
        gate['observations']['cpu_ready_capture_ack_sha256'] = 'not-a-digest'
        self.rejects(report, 'gate-observation-hash')
        report = synthetic('online-installed')
        gate = next(gate for gate in report['gates'] if gate['id'] == c.MODERN_GPU_GATE)
        gate['observations']['cpu_ready_capture_ack_sha256'] = gate['observations']['gpu_failure_capture_ack_sha256']
        self.rejects(report, 'recovery-screen-evidence-missing')

    def test_legacy_lane_cannot_claim_vulkan(self):
        report = synthetic('online-installed', profile='small-v2')
        ids = {gate['id'] for gate in report['gates']}
        self.assertIn(c.LEGACY_GPU_GATE, ids)
        self.assertNotIn(c.MODERN_GPU_GATE, ids)
        legacy = next(gate for gate in report['gates'] if gate['id'] == c.LEGACY_GPU_GATE)
        self.assertNotIn('gpu_failure_capture_ack_sha256', legacy['observations'])
        self.assertNotIn('cpu_ready_capture_ack_sha256', legacy['observations'])

    def test_transcript_fields_and_arbitrary_codes_are_rejected(self):
        report = synthetic(); report['transcript'] = 'private sentence'
        self.rejects(report, 'report-fields')
        report = synthetic(); report['gates'][0]['observations']['transcript'] = 1
        self.rejects(report, 'gate-observation-fields')
        report = synthetic(); report['gates'][0]['code'] = 'private sentence'
        self.rejects(report, 'gate-safe-code')

    def test_failed_and_unrun_codes_are_source_owned(self):
        report = synthetic()
        gate = report['gates'][0]
        gate.update(status='failed', code='attackercontrolledtoken', observations={})
        report['status'] = 'failed'
        self.rejects(report, 'gate-code-status')
        gate['code'] = 'gate-' + gate['id'] + '-invalid'
        self.assertEqual(c.validate(report, report['context'])['status'], 'failed')
        gate.update(status='unrun', code='gate-' + gate['id'] + '-invalid')
        self.rejects(report, 'gate-code-status')

    def test_dependent_unrun_gates_require_a_concrete_source_owned_failure(self):
        report = synthetic('online-installed')
        failed, dependent = report['gates'][:2]
        failed.update(status='failed', code='gate-' + failed['id'] + '-invalid', observations={})
        dependent.update(status='unrun', code='prerequisite-or-collector-failed', observations={})
        report['status'] = 'failed'
        result = c.validate(report, report['context'], fixture_manifest=FIXTURES)
        self.assertEqual(result['status'], 'failed')
        self.assertFalse(result['release_acceptance'])
        with self.assertRaisesRegex(c.Invalid, '^image-dictation-gates-incomplete$'):
            c.validate_report(report, report['context'], FIXTURES)

        no_failure = synthetic('online-installed')
        no_failure['gates'][0].update(
            status='unrun', code='prerequisite-or-collector-failed', observations={})
        no_failure['status'] = 'failed'
        self.rejects(no_failure, 'gate-code-status')

    def test_dependent_unrun_cannot_mask_hostile_or_accepting_reports(self):
        for mutation, code in (
                (lambda report: report.update(status='passed'), 'gate-code-status'),
                (lambda report: report.update(release_acceptance=True), 'report-schema-scope'),
                (lambda report: report['gates'][1].update(code='private-transcript'),
                 'gate-code-status'),
                (lambda report: report['gates'][0].update(code='attackercontrolledtoken'),
                 'gate-code-status')):
            report = synthetic('online-installed')
            report['gates'][0].update(
                status='failed', code='gate-' + report['gates'][0]['id'] + '-invalid', observations={})
            report['gates'][1].update(
                status='unrun', code='prerequisite-or-collector-failed', observations={})
            report['status'] = 'failed'
            mutation(report)
            self.rejects(report, code)

    def test_exact_binary_model_and_fixture_pins_are_required(self):
        report = synthetic('online-installed')
        report['samples'][0]['binary_sha256'] = c.ASSETS['cpu']['sha256']
        self.rejects(report, 'sample-profile-backend-pins')
        report = synthetic('online-installed')
        report['samples'][0]['wav_sha256'] = '0' * 64
        self.rejects(report, 'sample-fixture-binding')
        report = synthetic('online-installed')
        report['payload']['model']['sha256'] = '0' * 64
        self.rejects(report, 'report-payload-pins')

    def test_strict_size_and_no_release_claim(self):
        report = synthetic(); report['release_acceptance'] = True
        self.rejects(report, 'report-schema-scope')
        ctx = declared(); ctx['iso_bytes'] = 2_000_000_000
        with self.assertRaisesRegex(c.Invalid, '^context-iso-size$'):
            c.context(ctx)

    def execution(self, profile='turbo-q5-v3', offset=0):
        return {'online-installed-live': synthetic('live', 1 + offset, 1 + offset, profile),
                'offline-installed-live': synthetic('live', 2 + offset, 2 + offset, profile),
                'online-installed': synthetic('online-installed', 1 + offset, 3 + offset, profile),
                'offline-installed': synthetic('offline-installed', 2 + offset, 4 + offset, profile),
                'recovery': synthetic('recovery', 2 + offset, 5 + offset, profile),
                'recovered-offline': synthetic('recovered-offline', 2 + offset, 6 + offset, profile)}

    def test_execution_binds_boots_disks_and_both_profiles(self):
        modern = self.execution()
        state = {'release_acceptance': False, 'hardware_profile': 'turbo-q5-v3'}
        self.assertEqual(c.validate_execution(state, modern, FIXTURES)['status'], 'passed')
        legacy = self.execution('small-v2', 10)
        executions = {'turbo-q5-v3': {'state': state, 'reports': modern},
                      'small-v2': {'state': {'release_acceptance': False,
                                            'hardware_profile': 'small-v2'},
                                   'reports': legacy}}
        self.assertEqual(c.validate_release_profiles(executions, FIXTURES)['status'], 'passed')
        changed = copy.deepcopy(modern)
        changed['recovery']['disk']['root_fs_uuid'] = '00000000-0000-0000-0000-000000000999'
        with self.assertRaisesRegex(c.Invalid, '^execution-offline-disk-changed$'):
            c.validate_execution(state, changed, FIXTURES)


if __name__ == '__main__':
    unittest.main()
