#!/usr/bin/env python3
"""Validate exact dictation artifacts and emit only fixed staged diagnostics."""
import argparse
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import signal
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
REPO_API = 'repos/' + REPOSITORY
WORKFLOW = '.github/workflows/dictation-candidate-20261009.yml'
WORKFLOW_ID = 380362486
WORKFLOW_NAME = 'Candidate direct VoxType image qualification'
RUN_ID = 38887529276
RUN_ATTEMPT = 1
JOB_ID = 116928816988
ARTIFACT_ID = 12041905724
ARTIFACT_NAME = 'dictation-candidate-qualification-turbo-q5-v3'
ARTIFACT_BYTES = 158436
ARTIFACT_SHA256 = '404e7c560c0c385a99113814d9584a1b683989b082896927491e7ff8ea1836ec'
SOURCE_SHA = '7770b86f45eb40c8fc6d673f40a060e38a5f47a0'
REPOSITORY_ID = 1390608717
QUALIFICATION_BRANCH = 'codex/qualification-dispatch-20261010'
BRANCH = 'codex/read-dictation-turbo-388875-20261016'
ACTIVATION = Path('.github/dictation-turbo-failure-reader-388875.activate')
READER_WORKFLOW = Path('.github/workflows/read-dictation-turbo-failure-388875.yml')
READER = Path('tools/dictation-turbo-failure-reader-388875/read.py')
CONTRACT = Path('tools/dictation-turbo-failure-reader-388875/contract.py')
QUALIFICATION_MANIFEST = Path('tools/dictation-turbo-failure-reader-388875/qualification-execution-manifest.json')
PROFILES = ('turbo-q5-v3',)
# This byte-for-byte copy is itself SHA-256 pinned by execution-manifest.json.
# Derive every runner-owned context pin from the exact 7770b86f run manifest
# rather than from files on this later diagnostic branch.
FROZEN_QUALIFICATION = json.loads((ROOT / QUALIFICATION_MANIFEST).read_bytes())
FROZEN_EXECUTION_FILES = FROZEN_QUALIFICATION['execution_files']
FIXTURE_SHA256 = FROZEN_QUALIFICATION['fixture_manifest_sha256']
IMAGE = FROZEN_QUALIFICATION['image']
CONTEXT_PINS = {
    'source_sha': IMAGE['source_sha'], 'iso_sha256': IMAGE['sha256'],
    'iso_bytes': IMAGE['bytes'], 'fixture_manifest_sha256': FIXTURE_SHA256,
    'checker_sha256': FROZEN_EXECUTION_FILES['tools/dictation-qualification/guest_check.py'],
    'contract_sha256': FROZEN_EXECUTION_FILES['tools/dictation-qualification/contract.py'],
    'accuracy_sha256': FROZEN_EXECUTION_FILES['tools/dictation-accuracy/accuracy.py'],
    'pins_sha256': FROZEN_EXECUTION_FILES['tools/dictation-accuracy/pins.json'],
    # runner.integration_sha() intentionally hashes product files from the
    # frozen image source f369b978, rather than observer files from 7770b86f.
    'integration_sha256': '896fe653f960d314f8fe1f9f6eabaec60e1745690aad27982ed7bcb30ad4fc03',
}
MANIFEST_FIELDS = {'schema', 'ready', 'repository', 'workflow', 'run_id', 'run_attempt',
                   'source_sha', 'job_id', 'reader_sha256', 'contract_sha256',
                   'qualification_manifest_sha256', 'reader_workflow_sha256', 'artifacts'}
ARTIFACT_FIELDS = {'id', 'name', 'bytes', 'sha256'}
BASE_MEMBERS = {'execution.json', 'fixtures.json', 'online-installed-live.json',
                'online-installed.json', 'dictation-indicator-online-installed.png'}
RECOVERY_MEMBERS = {
    'gpu_failure': 'dictation-recovery-online-installed-gpu-failure.png',
    'cpu_ready': 'dictation-recovery-online-installed-cpu-ready.png',
}
ERROR_FAMILIES = {'invalid', 'os-error', 'value-error', 'timeout', 'key-error', 'type-error'}
SAFE_FAMILIES = ERROR_FAMILIES | {'none', 'prerequisite', 'isolation'}
FAILURE_SUBSTAGES = {6: set(range(601, 613)), 7: {701, 702, 703, 704},
                     12: set(range(1201, 1213)), 203: set(range(2031, 2038)),
                     301: set(range(3011, 3033))}
REJECTION_STAGES = {'manifest', 'run', 'artifact-metadata', 'archive', 'fixtures',
                    'execution', 'installations', 'report-inventory', 'live-report',
                    'live-receipt', 'live-hash', 'live-json', 'live-context',
                    'live-contract', 'live-status-binding', 'live-context-shape',
                    'live-context-profile', 'live-context-phase',
                    'live-context-installation',
                    *{'live-context-' + name.replace('_', '-') for name in CONTEXT_PINS},
                    'failed-report', 'indicator', 'recovery', 'projection'}
REJECTION_STAGE = 'manifest'
MAX_DOWNLOAD_BYTES = 1_000_000
MAX_OUTPUT_BYTES = 8192


def checkpoint(stage):
    global REJECTION_STAGE
    require(stage in REJECTION_STAGES)
    REJECTION_STAGE = stage


GATE_NAMES = {
    'english': 'cpu-english-transcription-insertion',
    'hebrew': 'cpu-hebrew-transcription-insertion',
    'gpu': 'gpu-failure-explicit-cpu-fallback',
    'legacy_gpu': 'legacy-no-vulkan-explicit-cpu',
    'cleanup': 'transcript-private-cleanup',
    'privacy': 'transcript-log-notification-leak-scan',
}


def require(value, reason='safe dictation reader rejected artifact'):
    if not value:
        raise RuntimeError(reason)


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def uuid(value):
    return type(value) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value) is not None


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(type(key) is str and key not in result)
        result[key] = value
    return result


def strict_json(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum)
    def reject_constant(_value):
        raise RuntimeError('safe dictation reader rejected artifact')
    return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=unique,
                      parse_constant=reject_constant)


def read_json_file(path, maximum):
    require(path.is_file() and not path.is_symlink())
    return strict_json(path.read_bytes(), maximum)


def validate_manifest(manifest):
    require(type(manifest) is dict and set(manifest) == MANIFEST_FIELDS)
    require(manifest['schema'] == 'arctic-dictation-failure-reader-v1'
            and manifest['ready'] is True and manifest['repository'] == REPOSITORY
            and manifest['workflow'] == WORKFLOW and manifest['run_id'] == RUN_ID
            and manifest['run_attempt'] == RUN_ATTEMPT and manifest['source_sha'] == SOURCE_SHA
            and manifest['job_id'] == JOB_ID)
    for field in ('reader_sha256', 'contract_sha256', 'qualification_manifest_sha256'):
        require(digest(manifest[field]))
    require(digest(manifest['reader_workflow_sha256']))
    require(sha256((ROOT / READER).read_bytes()) == manifest['reader_sha256']
            and sha256((ROOT / CONTRACT).read_bytes()) == manifest['contract_sha256']
            and sha256((ROOT / QUALIFICATION_MANIFEST).read_bytes()) ==
                manifest['qualification_manifest_sha256']
            and sha256((ROOT / READER_WORKFLOW).read_bytes()) ==
                manifest['reader_workflow_sha256'])
    require(type(manifest['artifacts']) is dict and set(manifest['artifacts']) == set(PROFILES))
    ids = set()
    for profile in PROFILES:
        pin = manifest['artifacts'][profile]
        require(type(pin) is dict and set(pin) == ARTIFACT_FIELDS
                and type(pin['id']) is int and pin['id'] == ARTIFACT_ID and pin['id'] not in ids
                and pin['name'] == ARTIFACT_NAME
                and pin['bytes'] == ARTIFACT_BYTES and pin['sha256'] == ARTIFACT_SHA256)
        ids.add(pin['id'])
    return manifest


def activation_guard():
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_WORKFLOW') ==
                'Read safe Turbo diagnostics for dictation run 38887529276'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1')
    child = os.environ.get('GITHUB_SHA', '')
    require(digest(child, 40))
    marker = ROOT / ACTIVATION
    require(marker.is_file() and not marker.is_symlink() and marker.stat().st_size == 41)
    parent = marker.read_text().strip()
    require(digest(parent, 40))
    event = read_json_file(Path(os.environ['GITHUB_EVENT_PATH']), 1_000_000)
    require(event.get('before') == parent and event.get('after') == child)
    parents = subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-list', '--parents', '-n', '1', child],
        text=True, timeout=30).split()
    require(parents == [child, parent])
    changed = subprocess.check_output(
        ['git', '-C', str(ROOT), 'diff', '--name-only', parent, child],
        text=True, timeout=30).splitlines()
    require(changed == [ACTIVATION.as_posix()]
            and marker.read_bytes() == (parent + '\n').encode()
            and not subprocess.check_output(
                ['git', '-C', str(ROOT), 'status', '--porcelain'],
                text=True, timeout=30).strip())


def api(path):
    result = subprocess.run(['gh', 'api', REPO_API + path], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60, check=False)
    require(result.returncode == 0 and 0 < len(result.stdout) <= 20_000_000)
    return strict_json(result.stdout, 20_000_000)


def download(artifact_id, target, expected_bytes):
    """Download to a regular file whose kernel-enforced size cannot exceed the pin."""
    require(not target.exists() and type(expected_bytes) is int
            and 0 < expected_bytes <= MAX_DOWNLOAD_BYTES)

    def limit_file_size():
        resource.setrlimit(resource.RLIMIT_FSIZE, (expected_bytes, expected_bytes))

    with target.open('xb') as output:
        child = subprocess.Popen(
            ['gh', 'api', REPO_API + '/actions/artifacts/' + str(artifact_id) + '/zip'],
            stdout=output, stderr=subprocess.DEVNULL, start_new_session=True,
            preexec_fn=limit_file_size)
        try:
            returncode = child.wait(timeout=120)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=10)
            raise RuntimeError('safe dictation reader rejected artifact') from None
    require(returncode == 0)
    info = target.lstat()
    require(stat.S_ISREG(info.st_mode) and not target.is_symlink()
            and info.st_size == expected_bytes)


def bounded_archive(path, expected_bytes, expected_sha256):
    require(type(expected_bytes) is int and 0 < expected_bytes <= MAX_DOWNLOAD_BYTES
            and digest(expected_sha256))
    result = hashlib.sha256()
    chunks = []
    total = 0
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        raise RuntimeError('safe dictation reader rejected artifact') from None
    with os.fdopen(descriptor, 'rb') as stream:
        info = os.fstat(stream.fileno())
        require(stat.S_ISREG(info.st_mode) and info.st_size == expected_bytes)
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                break
            total += len(chunk)
            require(total <= expected_bytes)
            result.update(chunk)
            chunks.append(chunk)
    require(total == expected_bytes and result.hexdigest() == expected_sha256)
    return b''.join(chunks)


def validate_workflow(workflow):
    require(type(workflow) is dict and workflow.get('id') == WORKFLOW_ID
            and workflow.get('name') == WORKFLOW_NAME
            and workflow.get('path') == WORKFLOW
            and workflow.get('state') == 'active')


def validate_run(run, jobs):
    require(type(run) is dict and run.get('id') == RUN_ID and run.get('run_attempt') == RUN_ATTEMPT
            and run.get('workflow_id') == WORKFLOW_ID and run.get('name') == WORKFLOW_NAME
            and run.get('head_sha') == SOURCE_SHA
            and run.get('head_branch') == QUALIFICATION_BRANCH
            and run.get('path') == WORKFLOW and run.get('event') == 'push'
            and run.get('status') == 'completed' and run.get('conclusion') == 'failure')
    for field in ('repository', 'head_repository'):
        repository = run.get(field)
        require(type(repository) is dict and repository.get('id') == REPOSITORY_ID
                and repository.get('full_name') == REPOSITORY)
    require(type(jobs) is dict and jobs.get('total_count') == 2
            and type(jobs.get('jobs')) is list and len(jobs['jobs']) == 2)
    expected = {'dictation (small-v2)', 'dictation (turbo-q5-v3)'}
    require({job.get('name') for job in jobs['jobs']} == expected)
    turbo = next(job for job in jobs['jobs'] if job.get('name') == 'dictation (turbo-q5-v3)')
    require(turbo.get('id') == JOB_ID and turbo.get('run_id') == RUN_ID
            and turbo.get('workflow_name') == WORKFLOW_NAME
            and turbo.get('head_sha') == SOURCE_SHA
            and turbo.get('head_branch') == QUALIFICATION_BRANCH
            and turbo.get('status') == 'completed' and turbo.get('conclusion') == 'failure')
    steps = {step.get('name'): step.get('conclusion') for step in turbo.get('steps', [])}
    require(steps.get('Fetch the retained ISO and verify its real bytes and source') == 'success'
            and steps.get('Direct upstream commands, online install, offline retry, local sessions and privacy') == 'failure'
            and steps.get('Run actions/upload-artifact@v4') == 'success')


def load_contract():
    path = ROOT / CONTRACT
    spec = importlib.util.spec_from_file_location('safe_dictation_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def safe_member(item, maximum):
    path = PurePosixPath(item.filename)
    mode = item.external_attr >> 16
    require(not path.is_absolute() and '..' not in path.parts and len(path.parts) == 1
            and not item.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
            and not (item.flag_bits & 0x1)
            and item.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
            and 0 < item.file_size <= maximum and 0 <= item.compress_size <= 1_000_000)


def validate_context(value, profile, phase, installation_id, checkpoint_prefix=None):
    def boundary(name):
        if checkpoint_prefix is not None:
            checkpoint(checkpoint_prefix + '-context-' + name)

    boundary('shape')
    require(type(value) is dict)
    boundary('profile')
    require(value.get('hardware_profile') == profile)
    boundary('phase')
    require(value.get('phase') == phase)
    boundary('installation')
    require(value.get('installation_id') == installation_id)
    for key, expected in CONTEXT_PINS.items():
        boundary(key.replace('_', '-'))
        require(value.get(key) == expected)


def validate_indicator(value, archive, installation_id, report):
    require(type(value) is dict and set(value) == {'path', 'sha256', 'iso_sha256',
            'installation_id', 'request'}
            and value['path'] == 'dictation-indicator-online-installed.png'
            and digest(value['sha256']) and value['iso_sha256'] == IMAGE['sha256']
            and value['installation_id'] == installation_id)
    request = value['request']
    require(type(request) is dict and set(request) == {'boot_id', 'installation_id', 'phase',
            'desktop_uid', 'receiver_empty', 'capture_nonce'}
            and request['boot_id'] == report['boot_id']
            and request['installation_id'] == installation_id
            and request['phase'] == 'online-installed' and request['receiver_empty'] is True
            and type(request['desktop_uid']) is int and request['desktop_uid'] > 0
            and digest(request['capture_nonce'], 32))
    raw = archive.read(value['path'])
    require(len(raw) <= 4_000_000 and raw.startswith(b'\x89PNG\r\n\x1a\n')
            and sha256(raw) == value['sha256'])
    return request['desktop_uid']


def validate_recovery(value, archive, installation_id, report, expected_desktop_uid):
    require(type(expected_desktop_uid) is int and expected_desktop_uid > 0)
    require(type(value) is dict and set(value) <= set(RECOVERY_MEMBERS))
    present = {}
    for stage, name in RECOVERY_MEMBERS.items():
        proof = value.get(stage)
        present[stage] = proof is not None
        if proof is None:
            require(name not in archive.namelist())
            continue
        require(type(proof) is dict and set(proof) == {'path', 'sha256', 'iso_sha256',
                'installation_id', 'request'} and proof['path'] == name
                and digest(proof['sha256']) and proof['iso_sha256'] == IMAGE['sha256']
                and proof['installation_id'] == installation_id)
        request = proof['request']
        require(type(request) is dict and set(request) == {'boot_id', 'installation_id', 'phase',
                'desktop_uid', 'receiver_empty', 'stage', 'state', 'backend', 'language',
                'capture_nonce'} and request['boot_id'] == report['boot_id']
                and request['installation_id'] == installation_id
                and request['phase'] == 'online-installed' and request['stage'] == stage
                and type(request['desktop_uid']) is int
                and request['desktop_uid'] == expected_desktop_uid
                and request['receiver_empty'] is True and request['backend'] == 'cpu'
                and request['state'] == ('error' if stage == 'gpu_failure' else 'ready')
                and request['language'] in ('en', 'he') and digest(request['capture_nonce'], 32))
        raw = archive.read(name)
        require(len(raw) <= 4_000_000 and raw.startswith(b'\x89PNG\r\n\x1a\n')
                and sha256(raw) == proof['sha256'])
    require(present['gpu_failure'] == present['cpu_ready'])
    return present


def family(gate):
    if gate['status'] == 'passed':
        result = 'none'
    elif gate['status'] == 'unrun':
        result = ('isolation' if gate['code'].endswith('-isolation-unavailable')
                  else 'prerequisite')
    else:
        prefix = 'gate-' + gate['id'] + '-'
        require(gate['code'].startswith(prefix))
        result = gate['code'][len(prefix):]
    require(result in SAFE_FAMILIES)
    return result


def staged_gate(gate, allowed_stages):
    stage = gate['observations'].get('failure_stage')
    present = stage is not None
    require(not present or type(stage) is int and stage in allowed_stages)
    substage = gate['observations'].get('failure_substage')
    substage_present = substage is not None
    require(not substage_present or (type(substage) is int
            and stage in FAILURE_SUBSTAGES and substage in FAILURE_SUBSTAGES[stage]))
    returncode = gate['observations'].get('failure_returncode')
    returncode_present = returncode is not None
    require(not returncode_present)
    return {'status': gate['status'], 'family': family(gate),
            'stage_present': present, 'stage': stage if present else 0,
            'substage_present': substage_present,
            'substage': substage if substage_present else 0,
            'returncode_present': returncode_present,
            'returncode': returncode if returncode_present else 0}


def bounded_counter(observations, name, maximum):
    value = observations.get(name)
    present = value is not None
    require(not present or type(value) is int and 0 <= value <= maximum)
    return present, value if present else 0


def failed_gates(report):
    """Project only contract-validated gate identities and numeric stage codes."""
    result = []
    for gate in report['gates']:
        if gate['status'] != 'failed':
            continue
        observed = gate['observations']
        stage = observed.get('failure_stage')
        substage = observed.get('failure_substage')
        require(stage is None or type(stage) is int and 0 < stage < 10_000)
        require(substage is None or (type(substage) is int and stage in FAILURE_SUBSTAGES
                and substage in FAILURE_SUBSTAGES[stage]))
        result.append({'gate': gate['id'], 'family': family(gate),
                       'stage_present': stage is not None, 'stage': stage or 0,
                       'substage_present': substage is not None, 'substage': substage or 0})
    require(0 < len(result) <= 4)
    return result


def diagnostic(report, recovery):
    by_name = {gate['id']: gate for gate in report['gates']}
    english = staged_gate(by_name[GATE_NAMES['english']], set(range(1, 20)))
    hebrew = staged_gate(by_name[GATE_NAMES['hebrew']], set(range(1, 20)))
    gpu_name = (GATE_NAMES['gpu'] if report['context']['hardware_profile'] == 'turbo-q5-v3'
                else GATE_NAMES['legacy_gpu'])
    gpu_allowed = set(range(1, 20)) | (set(range(201, 215)) if gpu_name == GATE_NAMES['gpu'] else set())
    gpu = staged_gate(by_name[gpu_name], gpu_allowed)
    cleanup_gate = by_name[GATE_NAMES['cleanup']]
    privacy_gate = by_name[GATE_NAMES['privacy']]
    files_present, files = bounded_counter(cleanup_gate['observations'], 'file_count', 64)
    matched_present, matched = bounded_counter(privacy_gate['observations'], 'matched', 64)
    count_present, count = bounded_counter(privacy_gate['observations'], 'count', 64)
    drained = cleanup_gate['observations'].get('drained')
    require(drained is None or type(drained) is bool)
    return {
        'report_status': report['status'],
        'failed_gates': failed_gates(report),
        'english': english, 'hebrew': hebrew, 'gpu': gpu,
        'cleanup': {'status': cleanup_gate['status'], 'family': family(cleanup_gate),
                    'file_count_present': files_present, 'file_count': files,
                    'drained_present': drained is not None,
                    'drained': drained if drained is not None else False},
        'privacy': {'status': privacy_gate['status'], 'family': family(privacy_gate),
                    'matched_present': matched_present, 'matched': matched,
                    'count_present': count_present, 'count': count},
        'recovery_receipts': {'entry_present': any(recovery.values()),
                              'gpu_failure': recovery['gpu_failure'],
                              'cpu_ready': recovery['cpu_ready']},
    }


def inspect_artifact(profile, pin, artifact, archive_raw, contract):
    checkpoint('artifact-metadata')
    require(type(artifact) is dict and artifact.get('id') == pin['id']
            and artifact.get('name') == pin['name'] and artifact.get('expired') is False
            and artifact.get('size_in_bytes') == pin['bytes']
            and artifact.get('digest') == 'sha256:' + pin['sha256'])
    workflow_run = artifact.get('workflow_run')
    require(type(workflow_run) is dict and workflow_run.get('id') == RUN_ID
            and workflow_run.get('head_sha') == SOURCE_SHA
            and workflow_run.get('head_branch') == QUALIFICATION_BRANCH
            and workflow_run.get('repository_id') == REPOSITORY_ID
            and workflow_run.get('head_repository_id') == REPOSITORY_ID)
    require(type(archive_raw) is bytes and len(archive_raw) == pin['bytes']
            and sha256(archive_raw) == pin['sha256'])
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        checkpoint('archive')
        items = archive.infolist()
        names = [item.filename for item in items]
        require(len(names) == len(set(names)) and BASE_MEMBERS <= set(names)
                and set(names) <= BASE_MEMBERS | set(RECOVERY_MEMBERS.values())
                and len(items) <= 7 and sum(item.file_size for item in items) <= 8_000_000)
        for item in items:
            safe_member(item, 4_000_000 if item.filename.endswith('.png') else 2_000_000)
        checkpoint('fixtures')
        fixtures = archive.read('fixtures.json')
        require(len(fixtures) <= 128 * 1024 and sha256(fixtures) == FIXTURE_SHA256)
        checkpoint('execution')
        state = strict_json(archive.read('execution.json'), 64 * 1024)
        fields = {'schema', 'hardware_profile', 'status', 'release_acceptance', 'image',
                  'execution_checker_head', 'fixture_manifest_sha256', 'reports',
                  'installations', 'indicators', 'recovery_screens', 'recorded_at_utc',
                  'vm_tool_image_id', 'current_phase', 'error'}
        require(type(state) is dict and set(state) == fields
                and state['schema'] == 'arctic-voxtype-execution-v3'
                and state['hardware_profile'] == profile and state['status'] == 'failed_or_unrun'
                and state['release_acceptance'] is False and state['image'] == IMAGE
                and state['execution_checker_head'] == SOURCE_SHA
                and state['fixture_manifest_sha256'] == FIXTURE_SHA256
                and state['current_phase'] == 'online-installed'
                and state['error'] == 'Qualification failed; inspect private Actions harness logs'
                and type(state['recorded_at_utc']) is str
                and re.fullmatch(r'[0-9T:.+\-]+', state['recorded_at_utc'])
                and type(state['vm_tool_image_id']) is str
                and re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', state['vm_tool_image_id']))
        checkpoint('installations')
        require(type(state['installations']) is dict and set(state['installations']) == {'online', 'offline'}
                and all(uuid(value) for value in state['installations'].values())
                and state['installations']['online'] != state['installations']['offline'])
        # reports() writes and validates the bounded failed report before its
        # strict require-passed check raises.  The runner therefore retains the
        # exact JSON member but deliberately does not add a passing receipt for
        # it to execution.json.  Only the successful live report has a receipt.
        checkpoint('report-inventory')
        require(type(state['reports']) is dict
                and set(state['reports']) == {'online-installed-live'})
        checkpoint('live-report')
        reports = {}
        receipt = state['reports']['online-installed-live']
        checkpoint('live-receipt')
        require(type(receipt) is dict and set(receipt) == {'path', 'sha256', 'phase',
                'installation_id', 'boot_id', 'status'}
                and receipt['path'] == 'online-installed-live.json'
                and receipt['phase'] == 'live' and receipt['status'] == 'passed'
                and receipt['installation_id'] == state['installations']['online']
                and uuid(receipt['boot_id']) and digest(receipt['sha256']))
        checkpoint('live-hash')
        live_raw = archive.read('online-installed-live.json')
        require(sha256(live_raw) == receipt['sha256'])
        checkpoint('live-json')
        live = strict_json(live_raw, 2_000_000)
        checkpoint('live-context')
        validate_context(live.get('context'), profile, 'live', state['installations']['online'],
                         checkpoint_prefix='live')
        checkpoint('live-contract')
        contract.validate(live, live['context'], require_passed=False,
                          fixture_manifest=fixtures)
        checkpoint('live-status-binding')
        require(live['status'] == 'passed' and live['boot_id'] == receipt['boot_id'])
        reports['online-installed-live'] = live
        checkpoint('failed-report')
        failed_raw = archive.read('online-installed.json')
        failed = strict_json(failed_raw, 2_000_000)
        validate_context(failed.get('context'), profile, 'online-installed',
                         state['installations']['online'])
        contract.validate(failed, failed['context'], require_passed=False,
                          fixture_manifest=fixtures)
        require(failed['status'] == 'failed')
        reports['online-installed'] = failed
        require(reports['online-installed-live']['boot_id'] != reports['online-installed']['boot_id'])
        checkpoint('indicator')
        require(type(state['indicators']) is dict and set(state['indicators']) == {'online-installed'})
        desktop_uid = validate_indicator(state['indicators']['online-installed'], archive,
                                         state['installations']['online'],
                                         reports['online-installed'])
        checkpoint('recovery')
        require(type(state['recovery_screens']) is dict
                and set(state['recovery_screens']) <= {'online-installed'})
        recovery = validate_recovery(state['recovery_screens'].get('online-installed', {}), archive,
                                     state['installations']['online'], reports['online-installed'],
                                     desktop_uid)
        checkpoint('projection')
        result = diagnostic(reports['online-installed'], recovery)
        result.update(profile=profile, artifact_id=pin['id'],
                      artifact_inventory=sorted(names),
                      execution_status=state['status'], current_phase=state['current_phase'])
        return result


def inspect(manifest, api_call=api, downloader=download):
    checkpoint('manifest')
    validate_manifest(manifest)
    checkpoint('run')
    workflow = api_call('/actions/workflows/' + str(WORKFLOW_ID))
    run = api_call('/actions/runs/' + str(RUN_ID))
    jobs = api_call('/actions/runs/' + str(RUN_ID) + '/jobs?filter=all&per_page=100')
    validate_workflow(workflow)
    validate_run(run, jobs)
    contract = load_contract()
    results = {}
    with tempfile.TemporaryDirectory(prefix='arctic-dictation-safe-reader-') as directory:
        for profile in PROFILES:
            pin = manifest['artifacts'][profile]
            artifact = api_call('/actions/artifacts/' + str(pin['id']))
            target = Path(directory) / (profile + '.zip')
            downloader(pin['id'], target, pin['bytes'])
            archive_raw = bounded_archive(target, pin['bytes'], pin['sha256'])
            results[profile] = inspect_artifact(profile, pin, artifact, archive_raw, contract)
    return {'schema': 'arctic-dictation-safe-diagnostic-v1', 'run_id': RUN_ID,
            'release_acceptance': False, 'profiles': results}


def exact_fields(value, fields):
    require(type(value) is dict and set(value) == set(fields))


def status_family(value):
    require(value['status'] in ('passed', 'failed', 'unrun'))
    expected = ({'none'} if value['status'] == 'passed' else
                ERROR_FAMILIES if value['status'] == 'failed' else
                {'prerequisite', 'isolation'})
    require(value['family'] in expected)


def projected_stage(value, allowed_stages):
    fields = {'status', 'family', 'stage_present', 'stage', 'substage_present',
              'substage', 'returncode_present', 'returncode'}
    exact_fields(value, fields)
    status_family(value)
    require(type(value['stage_present']) is bool and type(value['stage']) is int
            and ((value['stage_present'] and value['stage'] in allowed_stages)
                 or (not value['stage_present'] and value['stage'] == 0)))
    require(type(value['substage_present']) is bool and type(value['substage']) is int
            and ((value['substage_present'] and value['stage_present']
                  and value['stage'] in FAILURE_SUBSTAGES
                  and value['substage'] in FAILURE_SUBSTAGES[value['stage']])
                 or (not value['substage_present'] and value['substage'] == 0)))
    require(value['returncode_present'] is False and value['returncode'] == 0)
    return {name: value[name] for name in sorted(fields)}


def projected_failed_gate(value, allowed_ids):
    fields = {'gate', 'family', 'stage_present', 'stage', 'substage_present', 'substage'}
    exact_fields(value, fields)
    require(value['gate'] in allowed_ids and value['family'] in ERROR_FAMILIES
            and type(value['stage_present']) is bool and type(value['stage']) is int
            and ((value['stage_present'] and 0 < value['stage'] < 10_000)
                 or (not value['stage_present'] and value['stage'] == 0))
            and type(value['substage_present']) is bool and type(value['substage']) is int
            and ((value['substage_present'] and value['stage_present']
                  and value['stage'] in FAILURE_SUBSTAGES
                  and value['substage'] in FAILURE_SUBSTAGES[value['stage']])
                 or (not value['substage_present'] and value['substage'] == 0)))
    return {name: value[name] for name in sorted(fields)}


def projected_profile(value, profile):
    fields = {'profile', 'artifact_id', 'artifact_inventory', 'execution_status',
              'current_phase', 'report_status', 'failed_gates', 'english', 'hebrew',
              'gpu', 'cleanup', 'privacy', 'recovery_receipts'}
    exact_fields(value, fields)
    require(value['profile'] == profile
            and value['artifact_id'] == ARTIFACT_ID
            and value['execution_status'] == 'failed_or_unrun'
            and value['current_phase'] == 'online-installed'
            and value['report_status'] == 'failed')
    inventory = value['artifact_inventory']
    require(type(inventory) is list and inventory == sorted(inventory)
            and len(inventory) == len(set(inventory)) and len(inventory) <= 7
            and BASE_MEMBERS <= set(inventory)
            and set(inventory) <= BASE_MEMBERS | set(RECOVERY_MEMBERS.values())
            and ((set(RECOVERY_MEMBERS.values()) <= set(inventory))
                 or not (set(RECOVERY_MEMBERS.values()) & set(inventory))))
    allowed_ids = frozenset(load_contract().EXPECTED_KINDS)
    failed = value['failed_gates']
    require(type(failed) is list and 0 < len(failed) <= 4)
    safe_failed = [projected_failed_gate(item, allowed_ids) for item in failed]
    require(len({item['gate'] for item in safe_failed}) == len(safe_failed))
    cleanup = value['cleanup']
    exact_fields(cleanup, {'status', 'family', 'file_count_present', 'file_count',
                           'drained_present', 'drained'})
    status_family(cleanup)
    require(type(cleanup['file_count_present']) is bool and type(cleanup['file_count']) is int
            and 0 <= cleanup['file_count'] <= 64
            and (cleanup['file_count_present'] or cleanup['file_count'] == 0)
            and type(cleanup['drained_present']) is bool and type(cleanup['drained']) is bool
            and (cleanup['drained_present'] or cleanup['drained'] is False))
    privacy = value['privacy']
    exact_fields(privacy, {'status', 'family', 'matched_present', 'matched',
                           'count_present', 'count'})
    status_family(privacy)
    require(type(privacy['matched_present']) is bool and type(privacy['matched']) is int
            and 0 <= privacy['matched'] <= 64
            and (privacy['matched_present'] or privacy['matched'] == 0)
            and type(privacy['count_present']) is bool and type(privacy['count']) is int
            and 0 <= privacy['count'] <= 64
            and (privacy['count_present'] or privacy['count'] == 0))
    recovery = value['recovery_receipts']
    exact_fields(recovery, {'entry_present', 'gpu_failure', 'cpu_ready'})
    require(all(type(recovery[name]) is bool for name in recovery)
            and recovery['gpu_failure'] == recovery['cpu_ready'] == recovery['entry_present'])
    safe = {
        'profile': profile, 'artifact_id': value['artifact_id'],
        'artifact_inventory': list(inventory), 'execution_status': value['execution_status'],
        'current_phase': value['current_phase'], 'report_status': value['report_status'],
        'failed_gates': safe_failed,
        'english': projected_stage(value['english'], set(range(1, 20))),
        'hebrew': projected_stage(value['hebrew'], set(range(1, 20))),
        'gpu': projected_stage(value['gpu'], set(range(1, 20)) | set(range(201, 215))),
        'cleanup': {name: cleanup[name] for name in sorted(cleanup)},
        'privacy': {name: privacy[name] for name in sorted(privacy)},
        'recovery_receipts': {name: recovery[name] for name in sorted(recovery)},
    }
    return safe


def safe_projection(report):
    exact_fields(report, {'schema', 'run_id', 'release_acceptance', 'profiles'})
    require(report['schema'] == 'arctic-dictation-safe-diagnostic-v1'
            and report['run_id'] == RUN_ID and report['release_acceptance'] is False)
    exact_fields(report['profiles'], PROFILES)
    return {'schema': report['schema'], 'run_id': RUN_ID, 'release_acceptance': False,
            'profiles': {profile: projected_profile(report['profiles'][profile], profile)
                         for profile in PROFILES}}


def emit(report, output):
    projected = safe_projection(report)
    line = ('ARCTIC-DICTATION-SAFE-DIAGNOSTIC=' +
            json.dumps(projected, sort_keys=True, separators=(',', ':')) + '\n')
    encoded = line.encode('ascii', errors='strict')
    require(0 < len(encoded) <= MAX_OUTPUT_BYTES)
    output.write(line)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    activation_guard()
    manifest = read_json_file(args.manifest, 32_768)
    try:
        emit(inspect(manifest), os.sys.stdout)
    except RuntimeError:
        require(REJECTION_STAGE in REJECTION_STAGES)
        output = os.environ.get('GITHUB_OUTPUT')
        require(type(output) is str and output and '\n' not in output)
        with open(output, 'a', encoding='utf-8') as stream:
            stream.write('rejection=' + REJECTION_STAGE + '\n')
        print('ARCTIC-DICTATION-SAFE-READER-REJECTION=' + REJECTION_STAGE)
        raise


if __name__ == '__main__':
    main()
