#!/usr/bin/env python3
"""Transcript-free image evidence contract; validation never runs or qualifies an ISO."""
import argparse
import json
import hashlib
from pathlib import Path
import re

SCHEMA = 'arctic-dictation-image-v2'
CONTEXT_KEYS = {'schema', 'phase', 'source_sha', 'iso_sha256', 'iso_bytes',
                'fixture_manifest_sha256', 'checker_sha256', 'contract_sha256',
                'accuracy_sha256', 'pins_sha256', 'controller_sha256', 'child_exec_sha256', 'installation_id', 'hardware_profile'}
PHASES = {'live', 'online-installed', 'offline-installed', 'recovery', 'recovered-offline'}
COMMON = {'selinux-enforcing', 'no-new-avcs'}
SESSION = {'installed-payload-integrity', 'cpu-english-transcription-insertion',
           'cpu-hebrew-transcription-insertion', 'recording-status-published',
           'cancel-discards', 'broker-death-discards', 'missing-model-error', 'microphone-disconnect-error',
           'lock-discards', 'gpu-runtime-failure-cpu-retry', 'transcript-private-cleanup',
           'transcript-log-notification-leak-scan', 'local-offline-transcription'}
GATES = {
    'live': COMMON | {'live-payload-model-absent', 'live-controller-unavailable'},
    'online-installed': COMMON | SESSION | {'encrypted-installed-boot', 'online-installer-ready'},
    'offline-installed': COMMON | {'encrypted-installed-boot', 'offline-setup-pending', 'offline-os-healthy'},
    'recovery': COMMON | {'encrypted-installed-boot', 'explicit-service-recovery-ready', 'installed-payload-integrity'},
    'recovered-offline': COMMON | SESSION | {'encrypted-installed-boot', 'recovered-ready'},
}
ASSETS = {
    'cpu': {'name': 'voxtype-cpu', 'bytes': 18579224, 'sha256': '1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a'},
    'avx2': {'name': 'voxtype-cpu-avx2', 'bytes': 19153728, 'sha256': 'e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28'},
    'vulkan': {'name': 'voxtype-vulkan', 'bytes': 66342968, 'sha256': 'db2c7938392ff08ec8b50b8afb90f8bd3d0111eccf5943df2f51c40a0368fec2'},
    'small': {'name': 'ggml-small.bin', 'bytes': 487601967, 'sha256': '1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b'},
    'turbo': {'name': 'ggml-large-v3-turbo-q5_0.bin', 'bytes': 574041195, 'sha256': '394221709cd5ad1f40c46e6031ca61bce88931e6e088c188294c6d5a55ffa7e2'},
}
PROFILE_ASSETS = {
    'small-v2': {'cpu': ASSETS['cpu'], 'model': ASSETS['small']},
    'turbo-q5-v3': {'cpu': ASSETS['cpu'], 'avx2': ASSETS['avx2'], 'vulkan': ASSETS['vulkan'], 'model': ASSETS['turbo']},
}
PROFILES = {
    'small-v2': {'profile': 'small-v2', 'model': 'small', 'cpu_variant': 'baseline',
                 'model_download_bytes': 487601967, 'download_bytes': 506181191},
    'turbo-q5-v3': {'profile': 'turbo-q5-v3', 'model': 'large-v3-turbo-q5_0', 'cpu_variant': 'avx2',
                    'model_download_bytes': 574041195, 'download_bytes': 678117115},
}
LEGACY_GPU_GATE = 'legacy-gpu-unsupported-cpu-retry'


def gates(phase, profile):
    expected = GATES[phase]
    if profile == 'small-v2' and 'gpu-runtime-failure-cpu-retry' in expected:
        return (expected - {'gpu-runtime-failure-cpu-retry'}) | {LEGACY_GPU_GATE}
    return expected


def pinned(profile):
    return {key: {'bytes': asset['bytes'], 'sha256': asset['sha256']}
            for key, asset in PROFILE_ASSETS[profile].items()}


EVIDENCE_KINDS = {'actual-boot', 'actual-installed-files', 'actual-session',
                  'file-removal-fixture', 'device-disconnect-fixture',
                  'owned-process-kill-fixture', 'interval-log-scan'}
LIMITATIONS = ['measured-public-read-speech-only', 'no-whisper-parity-claim',
               'virtual-source-not-physical-microphone', 'forced-process-failure-not-driver-failure',
               'legacy-profile-does-not-certify-vulkan',
               'hardware-acceleration-not-certified-by-this-vm', 'visible-indicator-needs-screenshot-review',
               'recovery-service-tested-separately-from-polkit-dialog',
               'explicit-language-selection-no-mixed-language-claim', 'elapsed-includes-recording-and-insertion']
OBSERVATIONS = {'count', 'ready', 'pending', 'elapsed_ns', 'matched', 'avcs', 'locked',
                'active_backend_cpu', 'active_backend_vulkan', 'returncode', 'bytes',
                'sha256', 'boot_id', 'pid', 'start_ticks', 'file_count', 'drained',
                'installer_exit', 'source_id', 'restored', 'snapshot_sha256', 'audit_lost', 'audit_enabled',
                'audit_lost_before', 'audit_enabled_before', 'automatic_ready', 'gpu_supported'}
EXPECTED_KINDS = {name: 'actual-session' for names in GATES.values() for name in names}
EXPECTED_KINDS.update({name: 'actual-boot' for name in ('selinux-enforcing', 'encrypted-installed-boot',
    'offline-os-healthy', 'local-offline-transcription')})
EXPECTED_KINDS.update({name: 'actual-installed-files' for name in ('live-payload-model-absent', 'installed-payload-integrity')})
EXPECTED_KINDS[LEGACY_GPU_GATE] = 'actual-session'
EXPECTED_KINDS.update({'missing-model-error': 'file-removal-fixture',
    'microphone-disconnect-error': 'device-disconnect-fixture',
    'gpu-runtime-failure-cpu-retry': 'owned-process-kill-fixture',
    'broker-death-discards': 'owned-process-kill-fixture',
    'transcript-log-notification-leak-scan': 'interval-log-scan', 'no-new-avcs': 'interval-log-scan'})
REQUIRED_OBSERVATIONS = {
    'selinux-enforcing': {'ready': True}, 'encrypted-installed-boot': {'ready': True},
    'live-payload-model-absent': {'file_count': 0}, 'live-controller-unavailable': {'ready': False},
    'online-installer-ready': {'ready': True, 'pending': False},
    'recovered-ready': {'ready': True, 'pending': False},
    'explicit-service-recovery-ready': {'ready': True, 'pending': False},
    'offline-setup-pending': {'ready': False, 'pending': True}, 'offline-os-healthy': {'ready': True},
    'installed-payload-integrity': {}, 'recording-status-published': {'ready': True},
    'cpu-english-transcription-insertion': {'count': 5}, 'cpu-hebrew-transcription-insertion': {'count': 5},
    'cancel-discards': {'count': 0, 'drained': True},
    'broker-death-discards': {'count': 0, 'drained': True, 'ready': True},
    'missing-model-error': {'ready': False, 'restored': True},
    'microphone-disconnect-error': {'count': 0, 'drained': True, 'restored': True},
    'lock-discards': {'locked': True, 'count': 0, 'drained': True},
    'gpu-runtime-failure-cpu-retry': {'active_backend_vulkan': True, 'active_backend_cpu': True, 'count': 2},
    LEGACY_GPU_GATE: {'gpu_supported': False, 'active_backend_vulkan': False, 'active_backend_cpu': True, 'count': 2},
    'transcript-private-cleanup': {'file_count': 0, 'drained': True},
    'no-new-avcs': {'avcs': 0}, 'transcript-log-notification-leak-scan': {'matched': 0},
}

class Invalid(Exception):
    """Only fixed codes, never arbitrary exception or command output."""

def require(value, code):
    if not value:
        raise Invalid(code)

def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None

def uuid(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None

def context(value):
    require(isinstance(value, dict) and set(value) == CONTEXT_KEYS, 'context-fields')
    require(value['schema'] == 'arctic-dictation-context-v2' and value['phase'] in PHASES, 'context-schema-phase')
    require(value['hardware_profile'] in PROFILES, 'context-hardware-profile')
    require(digest(value['source_sha'], 40), 'context-source')
    for key in CONTEXT_KEYS:
        if key.endswith('_sha256'):
            require(digest(value[key]), 'context-hash')
    require(type(value['iso_bytes']) is int and 0 < value['iso_bytes'] < 2_000_000_000, 'context-iso-size')
    require(uuid(value['installation_id']), 'context-installation-id')
    return value

def validate(report, expected, require_passed=False, fixture_manifest=None):
    """Structural and pinned provenance checks, not a substitute for trusted collection."""
    context(expected)
    fields = {'schema', 'status', 'release_acceptance', 'context', 'boot_id',
              'controller_sha256', 'payload', 'gates', 'samples', 'limitations', 'disk', 'profile', 'hardware'}
    require(isinstance(report, dict) and set(report) == fields, 'report-fields')
    require(report['schema'] == SCHEMA and report['release_acceptance'] is False, 'report-schema-scope')
    require(report['context'] == expected and uuid(report['boot_id']), 'report-context-boot')
    require(report['controller_sha256'] == expected['controller_sha256'], 'report-controller')
    require(report['limitations'] == LIMITATIONS, 'report-limitations')
    profile = expected['hardware_profile']
    require(isinstance(report['profile'], dict) and report['profile'] == PROFILES[profile]
            and all(type(report['profile'].get(key)) is type(value)
                    for key, value in PROFILES[profile].items()), 'report-profile-descriptor')
    require(isinstance(report['hardware'], dict) and set(report['hardware']) ==
            {'profile', 'v3_supported', 'cpuinfo_sha256', 'profile_selection'}, 'report-hardware-fields')
    require(report['hardware']['profile'] == profile and type(report['hardware']['v3_supported']) is bool
            and report['hardware']['v3_supported'] == (profile == 'turbo-q5-v3')
            and digest(report['hardware']['cpuinfo_sha256'])
            and report['hardware']['profile_selection'] == 'recommended', 'report-hardware-profile')
    require(isinstance(report['payload'], dict) and report['payload'] in ({}, pinned(profile)), 'report-payload-pins')
    if report['payload']:
        require(all(type(value.get('bytes')) is int and isinstance(value.get('sha256'), str)
                    for value in report['payload'].values()), 'report-payload-pin-types')
    require(isinstance(report['disk'], dict), 'report-disk-type')
    if expected['phase'] == 'live':
        require(report['disk'] == {} and report['payload'] == {}, 'live-disk-or-payload-unexpected')
    elif report['disk']:
        require(isinstance(report['disk'], dict) and set(report['disk']) ==
                {'root_luks_uuid', 'root_fs_uuid', 'root_partuuid'}, 'encrypted-disk-identity-fields')
        require(uuid(report['disk']['root_luks_uuid']) and uuid(report['disk']['root_fs_uuid'])
                and (uuid(report['disk']['root_partuuid']) or
                     re.fullmatch('[0-9a-f]{8}-[0-9a-f]{2}', report['disk']['root_partuuid'] or '')),
                'encrypted-disk-identity-invalid')
    require(isinstance(report['gates'], list), 'report-gates-type')
    ids = [gate.get('id') for gate in report['gates'] if isinstance(gate, dict)]
    require(len(ids) == len(report['gates']) and len(ids) == len(set(ids))
            and set(ids) == gates(expected['phase'], profile), 'report-missing-duplicate-extra-gates')
    for gate in report['gates']:
        require(set(gate) == {'id', 'status', 'evidence_kind', 'code', 'observations'}, 'gate-fields')
        require(gate['status'] in ('passed', 'failed', 'unrun'), 'gate-status')
        require(gate['evidence_kind'] == EXPECTED_KINDS[gate['id']], 'gate-evidence-kind')
        require(isinstance(gate['code'], str) and re.fullmatch('[a-z0-9-]{1,80}', gate['code']), 'gate-safe-code')
        require(isinstance(gate['observations'], dict) and set(gate['observations']) <= OBSERVATIONS, 'gate-observation-fields')
        for key, value in gate['observations'].items():
            if key.endswith('sha256'):
                require(digest(value), 'gate-observation-hash')
            elif key == 'boot_id':
                require(uuid(value), 'gate-observation-boot')
            else:
                require(type(value) in (int, bool) and (type(value) is bool or value >= 0), 'gate-observation-scalar')
        if gate['status'] == 'passed':
            required = REQUIRED_OBSERVATIONS.get(gate['id'], {})
            require(all(type(gate['observations'].get(key)) is type(value)
                        and gate['observations'].get(key) == value for key, value in required.items()),
                    'gate-contradictory-or-missing-observations')
            if gate['id'] == 'installed-payload-integrity':
                require(type(gate['observations'].get('file_count')) is int
                        and gate['observations']['file_count'] == len(PROFILE_ASSETS[profile]), 'profile-payload-file-count')
                require(report['payload'] == pinned(profile), 'profile-payload-integrity-absent')
            if gate['id'] == LEGACY_GPU_GATE:
                require(profile == 'small-v2', 'legacy-gpu-gate-on-modern-profile')
            if gate['id'] == 'gpu-runtime-failure-cpu-retry':
                require(profile == 'turbo-q5-v3', 'modern-gpu-gate-on-legacy-profile')
            if gate['id'] == 'local-offline-transcription':
                require(type(gate['observations'].get('returncode')) is int
                        and gate['observations']['returncode'] > 0, 'offline-network-check-successful-response')
            if gate['id'] == 'recording-status-published':
                require(digest(gate['observations'].get('snapshot_sha256')), 'recording-indicator-evidence-missing')
                require(digest(gate['observations'].get('sha256')), 'recording-indicator-ack-missing')
            if gate['id'] == 'transcript-log-notification-leak-scan':
                require(type(gate['observations'].get('count')) is int
                        and gate['observations']['count'] >= 10, 'leak-scan-coverage')
            if gate['id'] == 'no-new-avcs':
                observed = gate['observations']
                require(type(observed.get('audit_enabled')) is int and observed['audit_enabled'] in (1, 2)
                        and type(observed.get('audit_enabled_before')) is int
                        and observed.get('audit_enabled_before') == observed['audit_enabled']
                        and type(observed.get('audit_lost')) is int
                        and type(observed.get('audit_lost_before')) is int
                        and observed.get('audit_lost_before') == observed['audit_lost'], 'audit-mode-or-loss-changed')
        if gate['id'] == 'gpu-runtime-failure-cpu-retry' and gate['status'] == 'passed':
            require(gate['evidence_kind'] == 'owned-process-kill-fixture'
                    and gate['observations'].get('active_backend_vulkan') is True
                    and gate['observations'].get('active_backend_cpu') is True
                    and gate['observations'].get('count') == 2, 'gpu-real-start-and-retry')
    if expected['phase'] != 'live' and not report['disk']:
        encrypted = next(g for g in report['gates'] if g['id'] == 'encrypted-installed-boot')
        require(encrypted['status'] != 'passed', 'passed-encryption-without-disk-identity')
    require(isinstance(report['samples'], list) and len(report['samples']) <= 12, 'report-samples-bound')
    fixture_samples = None
    if report['samples']:
        require(fixture_manifest is not None, 'fixture-manifest-required')
        raw = fixture_manifest.read_bytes() if isinstance(fixture_manifest, Path) else fixture_manifest
        require(isinstance(raw, bytes) and len(raw) <= 128 * 1024
                and hashlib.sha256(raw).hexdigest() == expected['fixture_manifest_sha256'], 'fixture-manifest-hash')
        fixtures = json.loads(raw)
        require(fixtures.get('schema') == 'arctic-dictation-fixtures-v1'
                and fixtures.get('dataset', {}).get('commit') == '70bb2e84b976b7e960aa89f1c648e09c59f894dd', 'fixture-manifest-provenance')
        source_samples = fixtures.get('samples', [])
        require([(s.get('language'), s.get('source_row')) for s in source_samples] ==
                [(lang, row) for lang in ('en', 'he') for row in range(5)], 'fixture-manifest-selection')
        fixture_samples = {(s['language'], s['source_row']): s for s in source_samples}
    sample_keys = {'language', 'source_row', 'purpose', 'wav_sha256', 'reference_sha256',
                   'hypothesis_sha256', 'elapsed_ns', 'audio_frames', 'sample_rate',
                   'reference_words', 'word_edits', 'reference_chars', 'char_edits', 'backend', 'cpu_variant', 'binary_sha256', 'model_sha256'}
    seen = set()
    for sample in report['samples']:
        require(isinstance(sample, dict) and set(sample) == sample_keys, 'sample-fields')
        cpu_key = 'avx2' if PROFILES[profile]['cpu_variant'] == 'avx2' else 'cpu'
        require(sample['backend'] == 'cpu' and sample['cpu_variant'] == PROFILES[profile]['cpu_variant']
                and sample['binary_sha256'] == PROFILE_ASSETS[profile][cpu_key]['sha256']
                and sample['model_sha256'] == PROFILE_ASSETS[profile]['model']['sha256'], 'sample-profile-backend-pins')
        require(sample['language'] in ('he', 'en') and sample['purpose'] in ('cpu-session', 'cpu-retry'), 'sample-language-purpose')
        require(type(sample['source_row']) is int and 0 <= sample['source_row'] < 5, 'sample-row')
        identity = (sample['language'], sample['source_row'], sample['purpose'])
        require(identity not in seen, 'sample-duplicate'); seen.add(identity)
        fixture = fixture_samples.get(identity[:2])
        require(fixture is not None and all(sample[key] == fixture[key] for key in
                ('wav_sha256', 'reference_sha256', 'audio_frames', 'sample_rate')), 'sample-fixture-binding')
        for key in ('wav_sha256', 'reference_sha256', 'hypothesis_sha256'):
            require(digest(sample[key]), 'sample-hash')
        for key in ('elapsed_ns', 'audio_frames', 'sample_rate', 'reference_words', 'word_edits', 'reference_chars', 'char_edits'):
            require(type(sample[key]) is int and sample[key] >= 0, 'sample-numeric')
        require(sample['elapsed_ns'] > 0 and sample['audio_frames'] > 0 and sample['sample_rate'] == 16000
                and sample['reference_words'] > 0 and sample['reference_chars'] > 0, 'sample-positive-counts')
    passed = all(gate['status'] == 'passed' for gate in report['gates'])
    if expected['phase'] in ('online-installed', 'recovered-offline') and passed:
        require(report['payload'] == pinned(profile), 'session-payload-absent')
        require(seen == {(lang, row, 'cpu-session') for lang in ('en', 'he') for row in range(5)}
                | {(lang, 0, 'cpu-retry') for lang in ('en', 'he')}, 'session-sample-coverage')
    require(report['status'] == ('passed' if passed else 'failed'), 'report-status-derived')
    if require_passed:
        require(passed, 'image-dictation-gates-incomplete')
    return {'schema': SCHEMA, 'contract_valid': True, 'status': report['status'], 'release_acceptance': False}

def validate_report(report, expected, fixture_manifest=None):
    return validate(report, expected, require_passed=True, fixture_manifest=fixture_manifest)

def validate_execution(state, reports, fixture_manifest=None):
    """Require all six actual reports and preserved offline encrypted installation."""
    inventory = {'online-installed-live', 'offline-installed-live', 'online-installed',
                 'offline-installed', 'recovery', 'recovered-offline'}
    require(isinstance(reports, dict) and set(reports) == inventory, 'execution-report-inventory')
    for name, report in reports.items():
        expected_phase = 'live' if name.endswith('-live') else name
        require(report['context']['phase'] == expected_phase, 'execution-phase')
        validate_report(report, report['context'], fixture_manifest)
    contexts = [r['context'] for r in reports.values()]
    for key in CONTEXT_KEYS - {'phase', 'installation_id'}:
        require(len({c[key] for c in contexts}) == 1, 'execution-common-provenance-differs')
    require(len({r['boot_id'] for r in reports.values()}) == 6, 'execution-boot-id-reused')
    online = reports['online-installed']
    offline = reports['offline-installed']
    require(online['context']['installation_id'] == reports['online-installed-live']['context']['installation_id']
            and offline['context']['installation_id'] == reports['offline-installed-live']['context']['installation_id']
            and online['context']['installation_id'] != offline['context']['installation_id'], 'execution-fresh-installations')
    require(online['disk']['root_luks_uuid'] != offline['disk']['root_luks_uuid']
            and online['disk']['root_fs_uuid'] != offline['disk']['root_fs_uuid'], 'execution-disk-reused-between-installations')
    for phase in ('recovery', 'recovered-offline'):
        require(reports[phase]['context']['installation_id'] == offline['context']['installation_id']
                and reports[phase]['disk'] == offline['disk'], 'execution-offline-disk-changed')
    require(isinstance(state, dict) and state.get('release_acceptance') is False
            and state.get('hardware_profile') == contexts[0]['hardware_profile'], 'execution-scope-profile')
    return {'schema': SCHEMA, 'contract_valid': True, 'status': 'passed', 'release_acceptance': False}

def validate_release_profiles(executions, fixture_manifest=None):
    """Both actual hardware lanes are necessary; each contains its six real boots."""
    require(isinstance(executions, dict) and set(executions) == set(PROFILES), 'release-profile-inventory')
    boots, installations, disks, filesystems = set(), set(), set(), set()
    common = None
    for profile, execution in executions.items():
        require(isinstance(execution, dict) and set(execution) == {'state', 'reports'}, 'release-profile-fields')
        reports = execution['reports']
        require(isinstance(reports, dict), 'release-profile-reports-type')
        require(all(r.get('context', {}).get('hardware_profile') == profile for r in reports.values()),
                'release-profile-context-mismatch')
        validate_execution(execution['state'], reports, fixture_manifest)
        for report in reports.values():
            require(report['boot_id'] not in boots, 'release-profile-boot-reused')
            boots.add(report['boot_id'])
            identity = {key: value for key, value in report['context'].items()
                        if key not in ('phase', 'installation_id', 'hardware_profile')}
            require(common is None or identity == common, 'release-profile-provenance-differs')
            common = identity
        lane_installations = {r['context']['installation_id'] for r in reports.values()}
        lane_disks = {r['disk']['root_luks_uuid'] for r in reports.values() if r['disk']}
        lane_filesystems = {r['disk']['root_fs_uuid'] for r in reports.values() if r['disk']}
        require(not installations.intersection(lane_installations) and not disks.intersection(lane_disks)
                and not filesystems.intersection(lane_filesystems),
                'release-profile-installation-reused')
        installations.update(lane_installations); disks.update(lane_disks); filesystems.update(lane_filesystems)
    return {'schema': SCHEMA, 'contract_valid': True, 'status': 'passed',
            'hardware_profiles': sorted(PROFILES), 'release_acceptance': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--require-passed', action='store_true')
    parser.add_argument('--fixture-manifest', type=Path)
    args = parser.parse_args()
    require(args.report.stat().st_size <= 128 * 1024 and args.context.stat().st_size <= 16 * 1024, 'json-byte-bound')
    result = validate(json.loads(args.report.read_text()), json.loads(args.context.read_text()), args.require_passed, args.fixture_manifest)
    print(json.dumps(result, sort_keys=True))

if __name__ == '__main__':
    main()
