"""Synthetic schema controls only. These tests never boot or mark dictation ready."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
import contract as c

def fixture_bytes():
    return json.dumps({'schema': 'arctic-dictation-fixtures-v1',
        'dataset': {'commit': '70bb2e84b976b7e960aa89f1c648e09c59f894dd'},
        'samples': [{'language': lang, 'source_row': row, 'wav_sha256': str(row + 1) * 64,
                     'reference_sha256': 'a' * 64, 'audio_frames': 16000, 'sample_rate': 16000}
                    for lang in ('en', 'he') for row in range(5)]}, sort_keys=True).encode()

FIXTURES = fixture_bytes()

def declared(phase='live', installation=1, profile='turbo-q5-v3'):
    return {'schema': 'arctic-dictation-context-v2', 'phase': phase, 'hardware_profile': profile, 'source_sha': 'b' * 40,
            'iso_bytes': 1_000_000_000, 'installation_id': f'00000000-0000-0000-0000-{installation:012d}',
            **{key: hashlib.sha256(FIXTURES).hexdigest() if key == 'fixture_manifest_sha256' else 'c' * 64
               for key in c.CONTEXT_KEYS if key.endswith('_sha256')}}

def synthetic(phase='live', installation=1, boot=1, profile='turbo-q5-v3'):
    """A contract fixture, explicitly unrelated to execution or setup evidence."""
    ctx = declared(phase, installation, profile)
    report = {'schema': c.SCHEMA, 'status': 'passed', 'release_acceptance': False,
              'context': ctx, 'boot_id': f'00000000-0000-0000-0000-{boot:012d}',
              'controller_sha256': ctx['controller_sha256'], 'payload': {}, 'samples': [],
              'limitations': c.LIMITATIONS, 'gates': [], 'disk': {}, 'profile': c.PROFILES[profile],
              'hardware': {'profile': profile, 'v3_supported': profile == 'turbo-q5-v3',
                           'cpuinfo_sha256': 'f' * 64, 'profile_selection': 'recommended'}}
    if phase != 'live':
        report['disk'] = {key: f'00000000-0000-0000-0000-{installation:012d}'
                          for key in ('root_luks_uuid', 'root_fs_uuid', 'root_partuuid')}
    if phase in ('online-installed', 'recovery', 'recovered-offline'):
        report['payload'] = c.pinned(profile)
    for name in sorted(c.gates(phase, profile)):
        observations = dict(c.REQUIRED_OBSERVATIONS.get(name, {}))
        if name == 'installed-payload-integrity':
            observations['file_count'] = len(c.PROFILE_ASSETS[profile])
        if name == 'local-offline-transcription':
            observations['returncode'] = 7
        if name == 'recording-status-published':
            observations['snapshot_sha256'] = 'd' * 64
            observations['sha256'] = 'e' * 64
        if name == 'transcript-log-notification-leak-scan':
            observations['count'] = 14 if profile == 'turbo-q5-v3' else 12
        if name == c.LOADER_GPU_GATE:
            observations.update(pid=123, start_ticks=456, socket_inode=789, sha256='d' * 64,
                actionable_gpu_error=True, cpu_continuation_inferred=False,
                cpu_preference_explicitly_selected=False, continuation_samples=[])
        if name == 'no-new-avcs':
            observations.update(audit_lost=0, audit_lost_before=0, audit_enabled=1, audit_enabled_before=1)
        report['gates'].append({'id': name, 'status': 'passed', 'evidence_kind': c.EXPECTED_KINDS[name],
                                'code': 'observed', 'observations': observations})
    if phase in ('online-installed', 'recovered-offline'):
        for purpose in ('cpu-session', 'cpu-retry'):
            for lang in ('en', 'he'):
                for row in range(5 if purpose == 'cpu-session' else 1):
                    report['samples'].append({'language': lang, 'source_row': row, 'purpose': purpose,
                        'wav_sha256': str(row + 1) * 64, 'reference_sha256': 'a' * 64,
                        'hypothesis_sha256': 'e' * 64, 'elapsed_ns': 123456789, 'audio_frames': 16000,
                        'sample_rate': 16000, 'reference_words': 10, 'word_edits': 3,
                        'reference_chars': 20, 'char_edits': 2, 'backend': 'cpu', 'cpu_variant': c.PROFILES[profile]['cpu_variant'],
                        'binary_sha256': c.PROFILE_ASSETS[profile]['avx2' if profile == 'turbo-q5-v3' else 'cpu']['sha256'],
                        'model_sha256': c.PROFILE_ASSETS[profile]['model']['sha256']})
        if profile == 'turbo-q5-v3':
            gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
            gate['observations']['retry_samples'] = [dict(item, purpose='cpu-loader-retry')
                for item in report['samples'] if item['purpose'] == 'cpu-retry']
    return report

class ContractControls(unittest.TestCase):
    def rejects(self, report, code):
        with self.assertRaisesRegex(c.Invalid, '^' + code + '$'):
            c.validate_report(report, report['context'], FIXTURES)

    def test_valid_contract_does_not_claim_release_acceptance(self):
        report = synthetic('online-installed')
        result = c.validate_report(report, report['context'], FIXTURES)
        self.assertTrue(result['contract_valid'])
        self.assertFalse(result['release_acceptance'])

    def test_transcript_and_arbitrary_text_fields_rejected(self):
        report = synthetic(); report['transcript'] = 'private sentence'
        self.rejects(report, 'report-fields')
        report = synthetic(); report['gates'][0]['observations']['transcript'] = 'private sentence'
        self.rejects(report, 'gate-observation-fields')
        report = synthetic(); report['gates'][0]['code'] = 'private sentence'
        self.rejects(report, 'gate-safe-code')

    def test_duplicate_or_missing_gate_rejected(self):
        report = synthetic(); report['gates'].append(copy.deepcopy(report['gates'][0]))
        self.rejects(report, 'report-missing-duplicate-extra-gates')
        report = synthetic(); report['gates'].pop()
        self.rejects(report, 'report-missing-duplicate-extra-gates')

    def test_failed_gpu_blocks_otherwise_complete_session(self):
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == 'gpu-runtime-failure-cpu-retry')
        gate.update(status='unrun', code='no-supported-vulkan-device', observations={})
        report['status'] = 'failed'
        c.validate(report, report['context'], fixture_manifest=FIXTURES)
        self.rejects(report, 'image-dictation-gates-incomplete')

    def test_loader_gate_is_additive_modern_only_and_fail_closed(self):
        report = synthetic('online-installed')
        self.assertIn('gpu-runtime-failure-cpu-retry', {g['id'] for g in report['gates']})
        self.assertIn(c.LOADER_GPU_GATE, {g['id'] for g in report['gates']})
        self.assertEqual(len(report['samples']), 12)
        gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
        gate.update(status='failed', code='loader-engine-not-observed', observations={})
        report['status'] = 'failed'
        c.validate(report, report['context'], fixture_manifest=FIXTURES)
        self.rejects(report, 'image-dictation-gates-incomplete')
        report = synthetic('online-installed', profile='small-v2')
        self.assertNotIn(c.LOADER_GPU_GATE, {g['id'] for g in report['gates']})
        self.assertIn(c.LEGACY_GPU_GATE, {g['id'] for g in report['gates']})

    def test_loader_requires_actual_identity_environment_error_and_new_recordings(self):
        for field in ('fresh_broker', 'inherited_loader_environment',
                      'receiver_empty_before_retry', 'explicit_new_cpu_recordings', 'drained'):
            report = synthetic('online-installed')
            gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
            gate['observations'][field] = False
            self.rejects(report, 'gate-contradictory-or-missing-observations')
        for field, value in (('pid', 0), ('start_ticks', True), ('socket_inode', 0), ('sha256', 'diagnostic text')):
            report = synthetic('online-installed')
            gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
            gate['observations'][field] = value
            self.rejects(report, 'gate-observation-hash' if field == 'sha256' else 'loader-retry-broker-fixture-identity')

    def test_real_local_continuation_is_distinct_from_actionable_discard(self):
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
        item = dict(report['samples'][0], purpose='loader-continuation',
            backend='cpu-inferred-after-loader-fault', cpu_variant='vulkan-build',
            binary_sha256=c.ASSETS['vulkan']['sha256'])
        gate['observations'].update(actionable_gpu_error=False, cpu_continuation_inferred=True,
            cpu_preference_explicitly_selected=True, continuation_samples=[item])
        leak = next(g for g in report['gates'] if g['id'] == 'transcript-log-notification-leak-scan')
        leak['observations']['count'] = 15
        c.validate_report(report, report['context'], FIXTURES)
        self.assertEqual(len(report['samples']), 12)
        for field, value, code in (('actionable_gpu_error', True, 'loader-outcome-contradiction'),
                ('cpu_preference_explicitly_selected', False, 'loader-outcome-contradiction'),
                ('native_backend_directly_observed', True, 'gate-contradictory-or-missing-observations')):
            changed = copy.deepcopy(report)
            next(g for g in changed['gates'] if g['id'] == c.LOADER_GPU_GATE)['observations'][field] = value
            self.rejects(changed, code)
        for field, value, code in (('binary_sha256', c.ASSETS['avx2']['sha256'], 'sample-profile-backend-pins'),
                ('model_sha256', c.ASSETS['small']['sha256'], 'sample-profile-backend-pins'),
                ('wav_sha256', 'f' * 64, 'sample-fixture-binding'),
                ('elapsed_ns', True, 'sample-numeric'), ('backend', 'vulkan', 'sample-profile-backend-pins')):
            changed = copy.deepcopy(report)
            next(g for g in changed['gates'] if g['id'] == c.LOADER_GPU_GATE)['observations']['continuation_samples'][0][field] = value
            self.rejects(changed, code)
        changed = copy.deepcopy(report)
        next(g for g in changed['gates'] if g['id'] == 'transcript-log-notification-leak-scan')['observations']['count'] = 14
        self.rejects(changed, 'loader-continuation-leak-scan-coverage')
        changed = copy.deepcopy(report)
        next(g for g in changed['gates'] if g['id'] == c.LOADER_GPU_GATE)['observations']['continuation_samples'].append(item)
        self.rejects(changed, 'loader-retry-samples-scope-bound')

    def test_loader_retry_measurements_bind_fixture_profile_and_separate_bounds(self):
        for field, value, code in (('wav_sha256', 'f' * 64, 'sample-fixture-binding'),
                ('binary_sha256', c.ASSETS['cpu']['sha256'], 'sample-profile-backend-pins'),
                ('model_sha256', c.ASSETS['small']['sha256'], 'sample-profile-backend-pins'),
                ('elapsed_ns', True, 'sample-numeric'), ('purpose', 'cpu-retry', 'sample-language-purpose'),
                ('source_row', 1, 'sample-fixture-binding')):
            report = synthetic('online-installed')
            gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
            gate['observations']['retry_samples'][0][field] = value
            self.rejects(report, code)
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
        gate['observations']['retry_samples'].append(copy.deepcopy(gate['observations']['retry_samples'][0]))
        self.rejects(report, 'loader-retry-samples-scope-bound')
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
        gate['observations']['retry_samples'][0]['transcript'] = 'private text'
        self.rejects(report, 'sample-fields')
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == c.LOADER_GPU_GATE)
        report['samples'].append(gate['observations']['retry_samples'][0])
        self.rejects(report, 'report-samples-bound')

    def test_no_fake_gpu_or_ordinary_fixture_evidence(self):
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == 'gpu-runtime-failure-cpu-retry')
        gate['evidence_kind'] = 'actual-session'
        self.rejects(report, 'gate-evidence-kind')
        report = synthetic(); report['gates'][0]['evidence_kind'] = 'file-removal-fixture'
        self.rejects(report, 'gate-evidence-kind')

    def test_observation_contradiction_rejected(self):
        report = synthetic('offline-installed')
        gate = next(g for g in report['gates'] if g['id'] == 'offline-setup-pending')
        gate['observations']['ready'] = True
        self.rejects(report, 'gate-contradictory-or-missing-observations')
        report = synthetic(); report['gates'][0]['observations']['ready'] = 1
        self.rejects(report, 'gate-contradictory-or-missing-observations')

    def test_sample_binds_actual_manifest_and_integer_clock(self):
        report = synthetic('online-installed'); report['samples'][0]['wav_sha256'] = 'f' * 64
        self.rejects(report, 'sample-fixture-binding')
        report = synthetic('online-installed'); report['samples'][0]['elapsed_ns'] = True
        self.rejects(report, 'sample-numeric')
        report = synthetic('online-installed')
        with self.assertRaisesRegex(c.Invalid, 'fixture-manifest-hash'):
            c.validate_report(report, report['context'], FIXTURES + b' ')

    def test_cpu_retry_requires_both_language_samples(self):
        report = synthetic('online-installed'); report['samples'].pop()
        self.rejects(report, 'session-sample-coverage')

    def test_release_claim_and_strict_iso_size(self):
        report = synthetic(); report['release_acceptance'] = True
        self.rejects(report, 'report-schema-scope')
        ctx = declared(); ctx['iso_bytes'] = 2_000_000_000
        with self.assertRaisesRegex(c.Invalid, 'context-iso-size'):
            c.context(ctx)

    def execution(self, profile='turbo-q5-v3', offset=0):
        reports = {'online-installed-live': synthetic('live', 1 + offset, 1 + offset, profile),
                   'offline-installed-live': synthetic('live', 2 + offset, 2 + offset, profile),
                   'online-installed': synthetic('online-installed', 1 + offset, 3 + offset, profile),
                   'offline-installed': synthetic('offline-installed', 2 + offset, 4 + offset, profile),
                   'recovery': synthetic('recovery', 2 + offset, 5 + offset, profile),
                   'recovered-offline': synthetic('recovered-offline', 2 + offset, 6 + offset, profile)}
        return reports

    def test_execution_actual_boots_and_encrypted_disk_binding(self):
        reports = self.execution()
        result = c.validate_execution({'status': 'running', 'release_acceptance': False, 'hardware_profile': 'turbo-q5-v3'}, reports, FIXTURES)
        self.assertFalse(result['release_acceptance'])
        reports['recovery']['disk']['root_luks_uuid'] = '00000000-0000-0000-0000-000000000999'
        with self.assertRaisesRegex(c.Invalid, 'execution-offline-disk-changed'):
            c.validate_execution({'release_acceptance': False, 'hardware_profile': 'turbo-q5-v3'}, reports, FIXTURES)
        reports = self.execution(); reports['recovery']['boot_id'] = reports['offline-installed']['boot_id']
        with self.assertRaisesRegex(c.Invalid, 'execution-boot-id-reused'):
            c.validate_execution({'release_acceptance': False, 'hardware_profile': 'turbo-q5-v3'}, reports, FIXTURES)

    def test_guest_import_has_no_execution(self):
        spec = importlib.util.spec_from_file_location('guest_check', Path(__file__).with_name('guest_check.py'))
        module = importlib.util.module_from_spec(spec)
        with (mock.patch('subprocess.run', side_effect=AssertionError('unexpected execution')),
              mock.patch('subprocess.Popen', side_effect=AssertionError('unexpected child'))):
            spec.loader.exec_module(module)

    def test_profiles_bind_model_binary_sizes_and_hardware(self):
        for profile in c.PROFILES:
            with self.subTest(profile=profile):
                report = synthetic('online-installed', profile=profile)
                c.validate_report(report, report['context'], FIXTURES)
                for field, value in (('model', 'wrong'), ('download_bytes', 572524159),
                                     ('download_bytes', float(c.PROFILES[profile]['download_bytes'])),
                                     ('model_download_bytes', True), ('cpu_variant', 'wrong')):
                    changed = copy.deepcopy(report); changed['profile'][field] = value
                    self.rejects(changed, 'report-profile-descriptor')
                for field, value in (('bytes', 1), ('sha256', '0' * 64)):
                    changed = copy.deepcopy(report); changed['payload']['model'][field] = value
                    self.rejects(changed, 'report-payload-pins')
                changed = copy.deepcopy(report)
                changed['payload']['model']['bytes'] = float(changed['payload']['model']['bytes'])
                self.rejects(changed, 'report-payload-pin-types')
                changed = copy.deepcopy(report); changed['hardware']['v3_supported'] = profile != 'turbo-q5-v3'
                self.rejects(changed, 'report-hardware-profile')
                changed = copy.deepcopy(report); changed['hardware']['profile_selection'] = 'compatibility'
                self.rejects(changed, 'report-hardware-profile')
                for field, value in (('backend', 'vulkan'), ('cpu_variant', 'wrong'),
                                     ('binary_sha256', '0' * 64), ('model_sha256', '0' * 64)):
                    changed = copy.deepcopy(report); changed['samples'][0][field] = value
                    self.rejects(changed, 'sample-profile-backend-pins')

    def test_legacy_gpu_cannot_substitute_for_modern_gpu_failure(self):
        report = synthetic('online-installed', profile='small-v2')
        self.assertNotIn('gpu-runtime-failure-cpu-retry', {g['id'] for g in report['gates']})
        gate = next(g for g in report['gates'] if g['id'] == c.LEGACY_GPU_GATE)
        gate['observations']['gpu_supported'] = True
        self.rejects(report, 'gate-contradictory-or-missing-observations')
        report = synthetic('online-installed')
        gate = next(g for g in report['gates'] if g['id'] == 'gpu-runtime-failure-cpu-retry')
        gate['id'] = c.LEGACY_GPU_GATE
        self.rejects(report, 'report-missing-duplicate-extra-gates')

    def test_release_requires_two_independent_complete_hardware_lanes(self):
        executions = {profile: {'state': {'release_acceptance': False, 'hardware_profile': profile},
                               'reports': self.execution(profile, offset)}
                      for profile, offset in (('small-v2', 100), ('turbo-q5-v3', 200))}
        result = c.validate_release_profiles(executions, FIXTURES)
        self.assertFalse(result['release_acceptance'])
        with self.assertRaisesRegex(c.Invalid, 'release-profile-inventory'):
            c.validate_release_profiles({'small-v2': executions['small-v2']}, FIXTURES)
        changed = copy.deepcopy(executions)
        changed['turbo-q5-v3']['reports']['online-installed-live']['boot_id'] = executions['small-v2']['reports']['online-installed-live']['boot_id']
        with self.assertRaisesRegex(c.Invalid, 'release-profile-boot-reused'):
            c.validate_release_profiles(changed, FIXTURES)
        changed = copy.deepcopy(executions)
        changed['turbo-q5-v3']['reports']['online-installed']['payload']['model']['bytes'] = 487601967
        with self.assertRaisesRegex(c.Invalid, 'report-payload-pins'):
            c.validate_release_profiles(changed, FIXTURES)

    def test_native_pins_match_actual_controller_whitelist(self):
        source = Path(__file__).resolve().parents[2] / 'packaging/dictation/dictation.py'
        spec = importlib.util.spec_from_file_location('actual_dictation_control', source)
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertEqual(set(c.PROFILES), set(module.PROFILES))
        for profile, value in c.PROFILES.items():
            self.assertEqual(value, module.profile_status(module.PROFILES[profile]))
            self.assertEqual(set(c.PROFILE_ASSETS[profile]), set(module.PROFILES[profile]['assets']))
            for key, asset in c.PROFILE_ASSETS[profile].items():
                name, _url, size, digest = module.PROFILES[profile]['assets'][key]
                self.assertEqual((asset['name'], asset['bytes'], asset['sha256']), (name, size, digest))

    def guest(self):
        spec = importlib.util.spec_from_file_location('guest_check', Path(__file__).with_name('guest_check.py'))
        module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        return module

    def test_guest_status_rejects_wrong_profile_bytes_and_backend(self):
        module = self.guest()
        checker = module.Checker.__new__(module.Checker)
        checker.profile_id = 'turbo-q5-v3'; checker.snapshots = []
        value = {**c.PROFILES['turbo-q5-v3'], 'version': '1.1.0', 'profile_selection': 'recommended',
                 'recommended_profile': c.PROFILES['turbo-q5-v3'], 'compatibility_profile': c.PROFILES['small-v2'],
                 'compatibility_required': False, 'active_backend': 'cpu', 'active_cpu_variant': 'avx2'}
        checker.cmd = mock.Mock(return_value=mock.Mock(stdout=json.dumps(value).encode()))
        checker.status()
        for key, item, code in (('model', 'small', 'status-profile-descriptor-pin'),
                                ('download_bytes', 572524159, 'status-profile-descriptor-pin'),
                                ('download_bytes', 678117115.0, 'status-profile-descriptor-pin'),
                                ('active_backend', 'bad', 'status-backend-unknown'),
                                ('active_cpu_variant', 'baseline', 'status-cpu-variant-profile'),
                                ('compatibility_required', True, 'optimized-cpu-incompatible')):
            changed = dict(value, **{key: item})
            checker.cmd.return_value.stdout = json.dumps(changed).encode()
            with self.assertRaisesRegex(c.Invalid, '^' + code + '$'):
                checker.status()

    def test_guest_controller_rejects_wrong_native_model_pin(self):
        module = self.guest()
        source = Path(__file__).resolve().parents[2] / 'packaging/dictation/dictation.py'
        with mock.patch.object(module, 'CONTROLLER', source):
            module.installed_controller()
        with tempfile.TemporaryDirectory() as root:
            changed = Path(root) / 'dictation.py'
            changed.write_text(source.read_text().replace(c.ASSETS['turbo']['sha256'], '0' * 64))
            with mock.patch.object(module, 'CONTROLLER', changed):
                with self.assertRaisesRegex(c.Invalid, 'installed-profile-asset-pin'):
                    module.installed_controller()

    def test_loader_environment_requires_actual_values_owner_and_stable_process(self):
        module = self.guest()
        checker = module.Checker.__new__(module.Checker)
        checker.account = mock.Mock(pw_uid=module.os.getuid())
        environment = {'VK_DRIVER_FILES': '/private/bad-icd.json', 'VK_LOADER_DEBUG': 'error'}
        with tempfile.TemporaryDirectory() as root:
            proc = Path(root) / '123'; proc.mkdir()
            (proc / 'environ').write_bytes(b'VK_DRIVER_FILES=/private/bad-icd.json\0VK_LOADER_DEBUG=error\0')
            with (mock.patch.object(module, 'Path', side_effect=lambda value: Path(root) if str(value) == '/proc' else Path(value)),
                  mock.patch.object(module, 'iter_process', return_value=456) as ticks):
                checker.loader_environment(123, 456, environment)
                ticks.side_effect = [456, 457]
                with self.assertRaisesRegex(c.Invalid, 'loader-environment-not-inherited'):
                    checker.loader_environment(123, 456, environment)
                ticks.side_effect = None
                (proc / 'environ').write_bytes(b'VK_DRIVER_FILES=/other.json\0VK_LOADER_DEBUG=error\0')
                with self.assertRaisesRegex(c.Invalid, 'loader-environment-not-inherited'):
                    checker.loader_environment(123, 456, environment)
                checker.account.pw_uid += 1
                with self.assertRaisesRegex(c.Invalid, 'loader-environment-process-identity'):
                    checker.loader_environment(123, 456, environment)

    def test_loader_engine_requires_same_broker_and_actual_direct_parent(self):
        module = self.guest()
        checker = module.Checker.__new__(module.Checker)
        broker = (42, 100, 200)
        environment = {'VK_DRIVER_FILES': '/private/bad-icd.json', 'VK_LOADER_DEBUG': 'error'}
        checker.broker_identity = mock.Mock(return_value=broker)
        checker.loader_environment = mock.Mock()
        with tempfile.TemporaryDirectory() as root:
            proc = Path(root) / '123'; proc.mkdir(); (proc / 'status').write_text('PPid:\t42\n')
            with mock.patch.object(module, 'Path', side_effect=lambda value: Path(root) if str(value) == '/proc' else Path(value)):
                checker.loader_engine((123, 456, Path('/pinned/voxtype-vulkan')), broker, environment)
                checker.broker_identity.assert_called_with(broker)
                checker.loader_environment.assert_called_once_with(123, 456, environment)
                (proc / 'status').write_text('PPid:\t43\n')
                with self.assertRaisesRegex(c.Invalid, 'loader-engine-parent-mismatch'):
                    checker.loader_engine((123, 456, Path('/pinned/voxtype-vulkan')), broker, environment)

    def test_loader_start_allows_only_real_recording_or_actionable_initialization_failure(self):
        module = self.guest()
        recording = {'ok': True, 'state': 'recording', 'backend': 'vulkan',
                     'active_backend': 'vulkan', 'error': ''}
        failed = {'ok': False, 'state': 'error', 'backend': 'vulkan', 'active_backend': 'cpu',
                  'error': 'GPU initialization failed. CPU is selected for this session; record again.'}
        module.Checker.loader_start_response(0, recording)
        module.Checker.loader_start_response(1, failed)
        for code, value in ((1, recording), (0, failed), (True, failed), (2, failed),
                (1, dict(failed, error='Recording could not start. Check the microphone in Sound settings.')),
                (1, dict(failed, error='GPU transcription failed. CPU is selected for this session; record again.')),
                (1, dict(failed, active_backend='vulkan')), (1, dict(failed, backend='cpu')),
                (0, dict(recording, state='ready')), (0, dict(recording, active_backend='cpu'))):
            with self.assertRaisesRegex(c.Invalid, 'loader-start-command-outcome'):
                module.Checker.loader_start_response(code, value)

    def test_hidden_upstream_transcript_temporaries_are_audited(self):
        module = self.guest()
        checker = module.Checker.__new__(module.Checker)
        with tempfile.TemporaryDirectory() as root:
            checker.private = Path(root)
            for name in ('transcript', '.transcript.123.tmp', '.transcript.done.123.tmp', 'config.toml'):
                (checker.private / name).touch()
            self.assertEqual({p.name for p in checker.transcript_files()},
                             {'transcript', '.transcript.123.tmp', '.transcript.done.123.tmp'})

    def test_cleanup_attempts_every_owned_resource_after_failures(self):
        module = self.guest()
        checker = module.Checker.__new__(module.Checker)
        checker.player, checker.window, checker.loop = object(), object(), object()
        checker.root = Path('/tmp/synthetic-unit-test-never-removed')
        checker.status = mock.Mock(side_effect=c.Invalid('synthetic-cancel-failure'))
        checker.kill = mock.Mock(side_effect=c.Invalid('synthetic-process-failure'))
        checker.destroy_route = mock.Mock(side_effect=c.Invalid('synthetic-route-failure'))
        with mock.patch.object(module.shutil, 'rmtree') as remove:
            with self.assertRaisesRegex(c.Invalid, 'owned-cleanup-failed'):
                checker.close()
            self.assertEqual(checker.kill.call_count, 2)
            checker.destroy_route.assert_called_once()
            remove.assert_called_once_with(checker.root)

    def test_guest_requires_explicit_authorization_before_commands(self):
        module = self.guest()
        with (mock.patch.object(sys, 'argv', ['guest_check.py', 'installed']),
              mock.patch.object(module, 'run', side_effect=AssertionError('must not execute')),
              mock.patch.object(module.resource, 'setrlimit')):
            with self.assertRaisesRegex(c.Invalid, 'explicit-root-disposable-guest-required'):
                module.main()

    def test_audit_loss_or_mode_change_rejected(self):
        report = synthetic()
        gate = next(g for g in report['gates'] if g['id'] == 'no-new-avcs')
        gate['observations']['audit_lost'] = 1
        self.rejects(report, 'audit-mode-or-loss-changed')
        report = synthetic()
        gate = next(g for g in report['gates'] if g['id'] == 'no-new-avcs')
        gate['observations'].update(audit_enabled=2, audit_enabled_before=2)
        c.validate_report(report, report['context'])

if __name__ == '__main__':
    unittest.main()
