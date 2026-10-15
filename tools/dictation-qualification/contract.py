#!/usr/bin/env python3
"""Transcript-free evidence contract for direct upstream VoxType qualification."""
import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = 'arctic-voxtype-image-v3'
CONTEXT_SCHEMA = 'arctic-voxtype-context-v3'
CONTEXT_KEYS = {
    'schema', 'phase', 'source_sha', 'iso_sha256', 'iso_bytes',
    'fixture_manifest_sha256', 'checker_sha256', 'contract_sha256',
    'accuracy_sha256', 'pins_sha256', 'integration_sha256',
    'installation_id', 'hardware_profile',
}
PHASES = {'live', 'online-installed', 'offline-installed', 'recovery', 'recovered-offline'}

UPSTREAM = {
    'version': '1.1.1',
    'source_commit': '014c56105b2f071bb3457c51a95c38be380e5124',
    'signed_sums_fingerprint': '9CCF7915B750CAE8B095ED1AA3FC9F33FD209279',
}
ASSETS = {
    'cpu': {'name': 'voxtype-baseline', 'bytes': 18838904,
            'sha256': 'cc051aac0870e21d7378edbcde3ceff10238af12a11650ab897d0ad9195225af'},
    'avx2': {'name': 'voxtype-avx2', 'bytes': 19415936,
             'sha256': '3462262980e5a75391ffdeb7d3b63f9f638d6261df042f04f9119dfb7aab7770'},
    'vulkan': {'name': 'voxtype-vulkan', 'bytes': 66575872,
               'sha256': '102a7caa22facc5c257c526ae4a9e63c04c027297fec4ca370209a1f94ae9863'},
    'small': {'name': 'ggml-small.bin', 'bytes': 487601967,
              'sha256': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b'},
    'turbo': {'name': 'ggml-large-v3-turbo-q5_0.bin', 'bytes': 574041195,
              'sha256': '394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2'},
}
PROFILE_ASSETS = {
    'small-v2': {'cpu': ASSETS['cpu'], 'model': ASSETS['small']},
    'turbo-q5-v3': {'avx2': ASSETS['avx2'], 'model': ASSETS['turbo']},
}
PROFILES = {
    'small-v2': {'profile': 'small-v2', 'model': 'small', 'cpu_variant': 'baseline',
                 'model_download_bytes': 487601967, 'download_bytes': 506440871},
    'turbo-q5-v3': {'profile': 'turbo-q5-v3', 'model': 'large-v3-turbo-q5_0',
                    'cpu_variant': 'avx2', 'model_download_bytes': 574041195,
                    'download_bytes': 593457131},
}

COMMON = {'selinux-enforcing', 'no-new-avcs'}
SESSION = {
    'installed-payload-integrity', 'upstream-command-contract',
    'upstream-state-contract', 'local-he-en-config', 'no-broad-input-access',
    'cpu-english-transcription-insertion', 'cpu-hebrew-transcription-insertion',
    'recording-status-published', 'cancel-discards', 'missing-model-error',
    'microphone-disconnect-error', 'lock-discards',
    'transcript-private-cleanup', 'transcript-log-notification-leak-scan',
    'local-offline-transcription',
}
MODERN_GPU_GATE = 'gpu-failure-explicit-cpu-fallback'
LEGACY_GPU_GATE = 'legacy-no-vulkan-explicit-cpu'
GATES = {
    'live': COMMON | {'live-payload-model-absent', 'live-voxtype-unavailable'},
    'online-installed': COMMON | SESSION | {'encrypted-installed-boot', 'online-installer-ready'},
    'offline-installed': COMMON | {'encrypted-installed-boot', 'offline-setup-pending', 'offline-os-healthy'},
    'recovery': COMMON | {'encrypted-installed-boot', 'explicit-service-recovery-ready',
                          'installed-payload-integrity'},
    'recovered-offline': COMMON | SESSION | {'encrypted-installed-boot', 'recovered-ready'},
}


def gates(phase, profile):
    expected = set(GATES[phase])
    if phase in ('online-installed', 'recovered-offline'):
        expected.add(MODERN_GPU_GATE if profile == 'turbo-q5-v3' else LEGACY_GPU_GATE)
    return expected


def pinned(profile):
    return {key: {'bytes': asset['bytes'], 'sha256': asset['sha256']}
            for key, asset in PROFILE_ASSETS[profile].items()}


LIMITATIONS = [
    'measured-public-read-speech-only', 'no-whisper-parity-claim',
    'virtual-source-not-physical-microphone',
    'bad-icd-loader-fixture-not-physical-driver-failure',
    'legacy-profile-does-not-certify-vulkan',
    'hardware-acceleration-not-certified-by-this-vm',
    'visible-indicator-needs-screenshot-review',
    'recovery-service-tested-separately-from-polkit-dialog',
    'constrained-he-en-detection-no-mixed-language-claim',
    'elapsed-includes-recording-and-insertion',
]
OBSERVATIONS = {
    'count', 'ready', 'pending', 'matched', 'avcs', 'locked', 'returncode',
    'sha256', 'snapshot_sha256', 'file_count', 'drained', 'restored',
    'automatic_ready', 'gpu_supported', 'explicit_cpu_selected',
    'failed_attempt_inserted', 'audit_lost', 'audit_enabled',
    'gpu_failure_capture_ack_sha256', 'cpu_ready_capture_ack_sha256',
    'audit_lost_before', 'audit_enabled_before', 'command_count',
    'allowed_state_count', 'language_count', 'input_group_membership', 'bytes',
    'failure_stage', 'pre_activation_engine_count', 'resident_rss_bytes',
}
ERROR_LABELS = {'invalid', 'os-error', 'value-error', 'timeout', 'key-error', 'type-error'}
TRANSCRIPTION_FAILURE_STAGES = {
    'fixture-selection': 1,
    'receiver-clear': 2,
    'focus-before': 3,
    'language-selection': 4,
    'record-start': 5,
    'recording-state': 6,
    'engine-profile': 7,
    'capture-link': 8,
    'fixture-play-start': 9,
    'fixture-playback': 10,
    'record-stop': 11,
    'transcribing-state': 12,
    'terminal-state': 13,
    'text-delivery': 14,
    'text-shape': 15,
    'focus-after': 16,
    'language-script': 17,
    'accuracy-metrics': 18,
    'sample-record': 19,
}
MICROPHONE_FAILURE_STAGES = {
    'receiver-clear': 101,
    'cpu-backend': 102,
    'initial-status': 103,
    'source-selection': 104,
    'pinned-daemon-restart': 105,
    'pinned-daemon-ready': 106,
    'record-start': 107,
    'recording-state': 108,
    'capture-link': 109,
    'route-destroy': 110,
    'source-isolation': 111,
    'interrupted-cancel': 112,
    'disconnected-daemon-restart': 113,
    'disconnected-daemon-ready': 114,
    'failed-record-start': 115,
    'actionable-error': 116,
    'idle-state': 117,
    'receiver-empty': 118,
    'cleanup-cancel': 119,
    'route-restore': 120,
    'default-source-restore': 121,
    'language-restore': 122,
    'error-clear': 123,
}
READINESS_FAILURE_STAGES = {
    'status-command': 201,
    'status-contract': 202,
    'readiness-marker-stat': 203,
    'readiness-marker-content': 204,
    'lazy-process-state': 205,
    'lazy-session-marker': 206,
    'audio-route': 207,
    'first-activation-command': 208,
    'first-activation-recording': 209,
    'first-activation-session-marker': 210,
    'first-activation-cancel': 211,
    'resident-daemon-ready': 212,
    'resident-engine-unique': 213,
    'resident-rss': 214,
}
TRANSCRIPTION_GATES = {
    'cpu-english-transcription-insertion',
    'cpu-hebrew-transcription-insertion',
    MODERN_GPU_GATE,
    LEGACY_GPU_GATE,
}
FAILURE_STAGE_GATES = {
    **{gate: frozenset(TRANSCRIPTION_FAILURE_STAGES.values())
       for gate in TRANSCRIPTION_GATES},
    'microphone-disconnect-error': frozenset(MICROPHONE_FAILURE_STAGES.values()),
    'online-installer-ready': frozenset(READINESS_FAILURE_STAGES.values()),
    'recovered-ready': frozenset(READINESS_FAILURE_STAGES.values()),
}
TRANSCRIPTION_REQUIRED_FAILURE_GATES = {
    'cpu-english-transcription-insertion',
    'cpu-hebrew-transcription-insertion',
}
STAGED_FAILURE_GATES = (TRANSCRIPTION_REQUIRED_FAILURE_GATES |
                        {'microphone-disconnect-error', 'online-installer-ready',
                         'recovered-ready'})
EXPECTED_KINDS = {name: 'actual-session' for names in GATES.values() for name in names}
EXPECTED_KINDS.update({name: 'actual-boot' for name in (
    'selinux-enforcing', 'encrypted-installed-boot', 'offline-os-healthy',
    'local-offline-transcription')})
EXPECTED_KINDS.update({name: 'actual-installed-files' for name in (
    'live-payload-model-absent', 'installed-payload-integrity')})
EXPECTED_KINDS.update({name: 'config-inspection' for name in (
    'upstream-command-contract', 'upstream-state-contract',
    'local-he-en-config', 'no-broad-input-access')})
EXPECTED_KINDS.update({
    'missing-model-error': 'file-removal-fixture',
    'microphone-disconnect-error': 'device-disconnect-fixture',
    MODERN_GPU_GATE: 'loader-configuration-fixture',
    'transcript-log-notification-leak-scan': 'interval-log-scan',
    'no-new-avcs': 'interval-log-scan',
})
EXPECTED_KINDS[LEGACY_GPU_GATE] = 'actual-session'
REQUIRED_OBSERVATIONS = {
    'selinux-enforcing': {'ready': True}, 'encrypted-installed-boot': {'ready': True},
    'live-payload-model-absent': {'file_count': 0}, 'live-voxtype-unavailable': {'ready': False},
    'online-installer-ready': {'ready': True, 'pending': False,
                               'pre_activation_engine_count': 0},
    'recovered-ready': {'ready': True, 'pending': False,
                        'pre_activation_engine_count': 0},
    'explicit-service-recovery-ready': {'ready': True, 'pending': False},
    'offline-setup-pending': {'ready': False, 'pending': True},
    'offline-os-healthy': {'ready': True},
    'upstream-command-contract': {'command_count': 4},
    'upstream-state-contract': {'allowed_state_count': 4},
    'local-he-en-config': {'language_count': 2},
    'no-broad-input-access': {'input_group_membership': 0},
    'recording-status-published': {'ready': True},
    'cpu-english-transcription-insertion': {'count': 5},
    'cpu-hebrew-transcription-insertion': {'count': 5},
    'cancel-discards': {'count': 0, 'drained': True},
    'missing-model-error': {'ready': False, 'restored': True},
    'microphone-disconnect-error': {'count': 0, 'drained': True, 'restored': True},
    'lock-discards': {'locked': True, 'count': 0, 'drained': True},
    MODERN_GPU_GATE: {'gpu_supported': True, 'explicit_cpu_selected': True,
                      'failed_attempt_inserted': False, 'count': 2,
                      'bytes': ASSETS['vulkan']['bytes'],
                      'sha256': ASSETS['vulkan']['sha256']},
    LEGACY_GPU_GATE: {'gpu_supported': False, 'explicit_cpu_selected': True, 'count': 2},
    'transcript-private-cleanup': {'file_count': 0, 'drained': True},
    'transcript-log-notification-leak-scan': {'matched': 0},
    'no-new-avcs': {'avcs': 0},
}


class Invalid(Exception):
    """A fixed safe diagnostic code, never arbitrary command output."""


def require(value, code):
    if not value:
        raise Invalid(code)


def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def uuid(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None


def context(value):
    require(isinstance(value, dict) and set(value) == CONTEXT_KEYS, 'context-fields')
    require(value['schema'] == CONTEXT_SCHEMA and value['phase'] in PHASES, 'context-schema-phase')
    require(value['hardware_profile'] in PROFILES, 'context-hardware-profile')
    require(digest(value['source_sha'], 40), 'context-source')
    for key in CONTEXT_KEYS:
        if key.endswith('_sha256'):
            require(digest(value[key]), 'context-hash')
    require(type(value['iso_bytes']) is int and 0 < value['iso_bytes'] < 2_000_000_000,
            'context-iso-size')
    require(uuid(value['installation_id']), 'context-installation-id')
    return value


def _fixtures(raw, expected):
    require(isinstance(raw, bytes) and len(raw) <= 128 * 1024
            and hashlib.sha256(raw).hexdigest() == expected['fixture_manifest_sha256'],
            'fixture-manifest-hash')
    value = json.loads(raw)
    require(value.get('schema') == 'arctic-dictation-fixtures-v1'
            and value.get('dataset', {}).get('commit') == '70bb2e84b976b7e960aa89f1c648e09c59f894dd',
            'fixture-manifest-provenance')
    samples = value.get('samples', [])
    require([(row.get('language'), row.get('source_row')) for row in samples]
            == [(language, row) for language in ('en', 'he') for row in range(5)],
            'fixture-manifest-selection')
    return {(row['language'], row['source_row']): row for row in samples}


def validate(report, expected, require_passed=False, fixture_manifest=None):
    """Validate bounded evidence shape and exact upstream/local-only provenance."""
    context(expected)
    fields = {'schema', 'status', 'release_acceptance', 'context', 'boot_id',
              'upstream', 'payload', 'gates', 'samples', 'limitations', 'disk',
              'profile', 'hardware'}
    require(isinstance(report, dict) and set(report) == fields, 'report-fields')
    require(report['schema'] == SCHEMA and report['release_acceptance'] is False,
            'report-schema-scope')
    require(report['context'] == expected and uuid(report['boot_id']), 'report-context-boot')
    require(report['upstream'] == UPSTREAM, 'report-upstream-pin')
    require(report['limitations'] == LIMITATIONS, 'report-limitations')
    profile = expected['hardware_profile']
    require(report['profile'] == PROFILES[profile], 'report-profile-descriptor')
    require(isinstance(report['hardware'], dict) and set(report['hardware']) ==
            {'profile', 'v3_supported', 'cpuinfo_sha256', 'profile_selection'},
            'report-hardware-fields')
    require(report['hardware']['profile'] == profile
            and report['hardware']['v3_supported'] == (profile == 'turbo-q5-v3')
            and type(report['hardware']['v3_supported']) is bool
            and digest(report['hardware']['cpuinfo_sha256'])
            and report['hardware']['profile_selection'] == 'recommended',
            'report-hardware-profile')
    require(isinstance(report['payload'], dict) and report['payload'] in ({}, pinned(profile)),
            'report-payload-pins')
    require(isinstance(report['disk'], dict), 'report-disk-type')
    if expected['phase'] == 'live':
        require(report['disk'] == {} and report['payload'] == {}, 'live-disk-or-payload-unexpected')
    elif report['disk']:
        require(set(report['disk']) == {'root_luks_uuid', 'root_fs_uuid', 'root_partuuid'},
                'encrypted-disk-identity-fields')
        require(uuid(report['disk']['root_luks_uuid']) and uuid(report['disk']['root_fs_uuid'])
                and (uuid(report['disk']['root_partuuid']) or
                     re.fullmatch('[0-9a-f]{8}-[0-9a-f]{2}', report['disk']['root_partuuid'] or '')),
                'encrypted-disk-identity-invalid')
    require(isinstance(report['gates'], list), 'report-gates-type')
    ids = [gate.get('id') for gate in report['gates'] if isinstance(gate, dict)]
    require(len(ids) == len(report['gates']) == len(set(ids))
            and set(ids) == gates(expected['phase'], profile),
            'report-missing-duplicate-extra-gates')
    # The guest collector completes the fixed gate inventory after a checked
    # gate aborts a dependent sequence.  These placeholders are useful only
    # when a source-owned, concrete failed gate already explains the failure;
    # an all-placeholder report remains a collector failure and is rejected.
    concrete_failure = any(isinstance(gate, dict) and gate.get('status') == 'failed'
                           for gate in report['gates'])
    for gate in report['gates']:
        require(set(gate) == {'id', 'status', 'evidence_kind', 'code', 'observations'},
                'gate-fields')
        require(gate['status'] in ('passed', 'failed', 'unrun'), 'gate-status')
        require(gate['evidence_kind'] == EXPECTED_KINDS[gate['id']], 'gate-evidence-kind')
        require(isinstance(gate['code'], str) and re.fullmatch('[a-z0-9-]{1,80}', gate['code']),
                'gate-safe-code')
        if gate['status'] == 'passed':
            require(gate['code'] == 'observed', 'gate-code-status')
        elif gate['status'] == 'failed':
            require(gate['code'] in {
                'gate-' + gate['id'] + '-' + label for label in ERROR_LABELS},
                'gate-code-status')
        else:
            isolated_microphone = (gate['id'] == 'microphone-disconnect-error'
                                   and gate['code'] ==
                                   'gate-microphone-disconnect-error-isolation-unavailable')
            dependent_unrun = (gate['code'] == 'prerequisite-or-collector-failed'
                               and report['status'] == 'failed'
                               and report['release_acceptance'] is False
                               and concrete_failure)
            require(isolated_microphone or dependent_unrun,
                    'gate-code-status')
        observed = gate['observations']
        require(isinstance(observed, dict) and set(observed) <= OBSERVATIONS,
                'gate-observation-fields')
        for key, value in observed.items():
            if key.endswith('sha256'):
                require(digest(value), 'gate-observation-hash')
            else:
                require(type(value) in (int, bool) and (type(value) is bool or value >= 0),
                        'gate-observation-scalar')
        if 'failure_stage' in observed:
            require(gate['status'] == 'failed' and gate['id'] in FAILURE_STAGE_GATES,
                    'gate-failure-stage-scope')
            require(type(observed['failure_stage']) is int
                    and observed['failure_stage'] in FAILURE_STAGE_GATES.get(gate['id'], ()),
                    'gate-failure-stage-value')
        elif gate['status'] == 'failed' and gate['id'] in STAGED_FAILURE_GATES:
            require(False, 'gate-failure-stage-missing')
        if gate['status'] == 'passed':
            required = REQUIRED_OBSERVATIONS.get(gate['id'], {})
            require(all(type(observed.get(key)) is type(value) and observed.get(key) == value
                        for key, value in required.items()),
                    'gate-contradictory-or-missing-observations')
            if gate['id'] in ('online-installer-ready', 'recovered-ready'):
                require(type(observed.get('resident_rss_bytes')) is int
                        and observed['resident_rss_bytes'] > 0,
                        'gate-resident-rss-missing')
            if gate['id'] == 'installed-payload-integrity':
                require(observed.get('file_count') == len(PROFILE_ASSETS[profile])
                        and type(observed.get('file_count')) is int
                        and report['payload'] == pinned(profile),
                        'profile-payload-integrity-absent')
            if gate['id'] == 'recording-status-published':
                require(digest(observed.get('snapshot_sha256')) and digest(observed.get('sha256')),
                        'recording-indicator-evidence-missing')
            if gate['id'] == MODERN_GPU_GATE:
                require(digest(observed.get('gpu_failure_capture_ack_sha256'))
                        and digest(observed.get('cpu_ready_capture_ack_sha256'))
                        and observed['gpu_failure_capture_ack_sha256'] !=
                            observed['cpu_ready_capture_ack_sha256'],
                        'recovery-screen-evidence-missing')
            if gate['id'] == 'transcript-log-notification-leak-scan':
                require(type(observed.get('count')) is int and observed['count'] >= 12,
                        'leak-scan-coverage')
            if gate['id'] == 'local-offline-transcription':
                require(type(observed.get('returncode')) is int and observed['returncode'] > 0,
                        'offline-network-check-successful-response')
            if gate['id'] == 'no-new-avcs':
                require(observed.get('audit_enabled') in (1, 2)
                        and observed.get('audit_enabled_before') == observed.get('audit_enabled')
                        and observed.get('audit_lost_before') == observed.get('audit_lost'),
                        'audit-mode-or-loss-changed')
    if expected['phase'] != 'live' and not report['disk']:
        encrypted = next(g for g in report['gates'] if g['id'] == 'encrypted-installed-boot')
        require(encrypted['status'] != 'passed', 'passed-encryption-without-disk-identity')
    require(isinstance(report['samples'], list) and len(report['samples']) <= 12,
            'report-samples-bound')
    fixture_samples = None
    if report['samples']:
        require(fixture_manifest is not None, 'fixture-manifest-required')
        raw = fixture_manifest.read_bytes() if isinstance(fixture_manifest, Path) else fixture_manifest
        fixture_samples = _fixtures(raw, expected)
    sample_keys = {'language', 'source_row', 'purpose', 'wav_sha256', 'reference_sha256',
                   'hypothesis_sha256', 'elapsed_ns', 'audio_frames', 'sample_rate',
                   'reference_words', 'word_edits', 'reference_chars', 'char_edits',
                   'backend', 'cpu_variant', 'binary_sha256', 'model_sha256'}
    seen = set()
    for sample in report['samples']:
        require(isinstance(sample, dict) and set(sample) == sample_keys, 'sample-fields')
        cpu_key = 'avx2' if PROFILES[profile]['cpu_variant'] == 'avx2' else 'cpu'
        require(sample['backend'] == 'cpu'
                and sample['cpu_variant'] == PROFILES[profile]['cpu_variant']
                and sample['binary_sha256'] == PROFILE_ASSETS[profile][cpu_key]['sha256']
                and sample['model_sha256'] == PROFILE_ASSETS[profile]['model']['sha256'],
                'sample-profile-backend-pins')
        require(sample['language'] in ('he', 'en')
                and sample['purpose'] in ('cpu-session', 'cpu-retry'),
                'sample-language-purpose')
        require(type(sample['source_row']) is int and 0 <= sample['source_row'] < 5, 'sample-row')
        identity = (sample['language'], sample['source_row'], sample['purpose'])
        require(identity not in seen, 'sample-duplicate')
        seen.add(identity)
        fixture = fixture_samples.get(identity[:2])
        require(fixture is not None and all(sample[key] == fixture[key] for key in
                ('wav_sha256', 'reference_sha256', 'audio_frames', 'sample_rate')),
                'sample-fixture-binding')
        for key in ('wav_sha256', 'reference_sha256', 'hypothesis_sha256'):
            require(digest(sample[key]), 'sample-hash')
        for key in ('elapsed_ns', 'audio_frames', 'sample_rate', 'reference_words',
                    'word_edits', 'reference_chars', 'char_edits'):
            require(type(sample[key]) is int and sample[key] >= 0, 'sample-numeric')
        require(sample['elapsed_ns'] > 0 and sample['audio_frames'] > 0
                and sample['sample_rate'] == 16000 and sample['reference_words'] > 0
                and sample['reference_chars'] > 0, 'sample-positive-counts')
    passed = all(gate['status'] == 'passed' for gate in report['gates'])
    if expected['phase'] in ('online-installed', 'recovered-offline') and passed:
        required = {(language, row, 'cpu-session') for language in ('en', 'he') for row in range(5)}
        required |= {(language, 0, 'cpu-retry') for language in ('en', 'he')}
        require(seen == required, 'session-sample-coverage')
    require(report['status'] == ('passed' if passed else 'failed'), 'report-status-derived')
    if require_passed:
        require(passed, 'image-dictation-gates-incomplete')
    return {'schema': SCHEMA, 'contract_valid': True, 'status': report['status'],
            'release_acceptance': False}


def validate_report(report, expected, fixture_manifest=None):
    return validate(report, expected, True, fixture_manifest)


def validate_execution(state, reports, fixture_manifest=None):
    inventory = {'online-installed-live', 'offline-installed-live', 'online-installed',
                 'offline-installed', 'recovery', 'recovered-offline'}
    require(isinstance(reports, dict) and set(reports) == inventory,
            'execution-report-inventory')
    for name, report in reports.items():
        phase = 'live' if name.endswith('-live') else name
        require(report['context']['phase'] == phase, 'execution-phase')
        validate_report(report, report['context'], fixture_manifest)
    contexts = [report['context'] for report in reports.values()]
    for key in CONTEXT_KEYS - {'phase', 'installation_id'}:
        require(len({row[key] for row in contexts}) == 1,
                'execution-common-provenance-differs')
    require(len({report['boot_id'] for report in reports.values()}) == 6,
            'execution-boot-id-reused')
    online, offline = reports['online-installed'], reports['offline-installed']
    require(online['context']['installation_id'] == reports['online-installed-live']['context']['installation_id']
            and offline['context']['installation_id'] == reports['offline-installed-live']['context']['installation_id']
            and online['context']['installation_id'] != offline['context']['installation_id'],
            'execution-fresh-installations')
    require(online['disk']['root_luks_uuid'] != offline['disk']['root_luks_uuid']
            and online['disk']['root_fs_uuid'] != offline['disk']['root_fs_uuid'],
            'execution-disk-reused-between-installations')
    for phase in ('recovery', 'recovered-offline'):
        require(reports[phase]['context']['installation_id'] == offline['context']['installation_id']
                and reports[phase]['disk'] == offline['disk'],
                'execution-offline-disk-changed')
    require(isinstance(state, dict) and state.get('release_acceptance') is False
            and state.get('hardware_profile') == contexts[0]['hardware_profile'],
            'execution-scope-profile')
    return {'schema': SCHEMA, 'contract_valid': True, 'status': 'passed',
            'release_acceptance': False}


def validate_release_profiles(executions, fixture_manifest=None):
    require(isinstance(executions, dict) and set(executions) == set(PROFILES),
            'release-profile-inventory')
    boots, installations, disks, filesystems = set(), set(), set(), set()
    common = None
    for profile, execution in executions.items():
        require(isinstance(execution, dict) and set(execution) == {'state', 'reports'},
                'release-profile-fields')
        reports = execution['reports']
        require(all(row.get('context', {}).get('hardware_profile') == profile
                    for row in reports.values()), 'release-profile-context-mismatch')
        validate_execution(execution['state'], reports, fixture_manifest)
        for report in reports.values():
            require(report['boot_id'] not in boots, 'release-profile-boot-reused')
            boots.add(report['boot_id'])
            identity = {key: value for key, value in report['context'].items()
                        if key not in ('phase', 'installation_id', 'hardware_profile')}
            require(common is None or identity == common, 'release-profile-provenance-differs')
            common = identity
        lane_installations = {row['context']['installation_id'] for row in reports.values()}
        lane_disks = {row['disk']['root_luks_uuid'] for row in reports.values() if row['disk']}
        lane_filesystems = {row['disk']['root_fs_uuid'] for row in reports.values() if row['disk']}
        require(not installations & lane_installations and not disks & lane_disks
                and not filesystems & lane_filesystems,
                'release-profile-installation-reused')
        installations |= lane_installations
        disks |= lane_disks
        filesystems |= lane_filesystems
    return {'schema': SCHEMA, 'contract_valid': True, 'status': 'passed',
            'hardware_profiles': sorted(PROFILES), 'release_acceptance': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--require-passed', action='store_true')
    parser.add_argument('--fixture-manifest', type=Path)
    args = parser.parse_args()
    require(args.report.stat().st_size <= 128 * 1024
            and args.context.stat().st_size <= 16 * 1024, 'json-byte-bound')
    result = validate(json.loads(args.report.read_text()), json.loads(args.context.read_text()),
                      args.require_passed, args.fixture_manifest)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
