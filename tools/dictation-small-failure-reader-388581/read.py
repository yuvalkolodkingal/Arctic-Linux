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
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
REPO_API = 'repos/' + REPOSITORY
WORKFLOW = '.github/workflows/dictation-candidate-20261009.yml'
RUN_ID = 38858151468
RUN_ATTEMPT = 1
SOURCE_SHA = '851a6a4a135e4293dc6ab01bdb568bb0aa98ba36'
BRANCH = 'codex/read-dictation-small-388581-20261016'
ACTIVATION = Path('.github/dictation-small-failure-reader-388581.activate')
READER = Path('tools/dictation-small-failure-reader-388581/read.py')
CONTRACT = Path('tools/dictation-qualification/contract.py')
QUALIFICATION_MANIFEST = Path('tools/dictation-qualification/execution-manifest.json')
PROFILES = ('small-v2',)
FIXTURE_SHA256 = 'd97f1daced07fd25e5ddeba3bbb8df7f5af1cccfa216dc0f31acd3ddb2abd2fd'
IMAGE = {
    'archive_bytes': 1936459062,
    'archive_sha256': '5f77dbf607abdada5ed140ae8635314554d5d2f03f88f1f5831e3d53bc18cf23',
    'artifact_id': 12016177474,
    'bytes': 1936271360,
    'name': 'Arctic-Linux-1.2-candidate-38823208615-1-x86_64.iso',
    'producer_mode': 'frozen-external-paired-v1',
    'producer_receipt_sha256': '82d102432819e8cc2f9d27b020f54a21021a176daa930e675c75229273ab7330',
    'run_id': 38823208615,
    'sha256': 'c13c4589d7b522fec7dbd5eeafec00cf9088d8788cdfb6771a7382285846d7c7',
    'source_sha': 'cfc39dad61125e4fa8fb7906ac14f4c360b58228',
}
CONTEXT_PINS = {
    'source_sha': IMAGE['source_sha'], 'iso_sha256': IMAGE['sha256'],
    'iso_bytes': IMAGE['bytes'], 'fixture_manifest_sha256': FIXTURE_SHA256,
    'checker_sha256': '0faf662102a583ef5f4ad59fa73128ce55d1f01b71c40c17030b883c71ed8461',
    'contract_sha256': 'c2c320ed140ee68db871f2b39abdd24aa17b7a2fcdd060501f0f6967d7e2ba8d',
    'accuracy_sha256': '8ad22b8c8c96a379b6dc460ae0503e5459968e9608d337b0cc639b31c129a68a',
    'pins_sha256': '446c24b770e046cb845f117d2bbb2dbcebd9fb6876d08c05ebdf278e067aa01d',
    'integration_sha256': '151ba0bb0265542d1b031bc94572ce671d06c1dbc177796a00f6e6d62ec8e7f7',
}
MANIFEST_FIELDS = {'schema', 'ready', 'repository', 'workflow', 'run_id', 'run_attempt',
                   'source_sha', 'reader_sha256', 'contract_sha256',
                   'qualification_manifest_sha256', 'artifacts'}
ARTIFACT_FIELDS = {'id', 'name', 'bytes', 'sha256'}
BASE_MEMBERS = {'execution.json', 'fixtures.json', 'online-installed-live.json',
                'online-installed.json', 'dictation-indicator-online-installed.png'}
RECOVERY_MEMBERS = {
    'gpu_failure': 'dictation-recovery-online-installed-gpu-failure.png',
    'cpu_ready': 'dictation-recovery-online-installed-cpu-ready.png',
}
ERROR_FAMILIES = {'invalid', 'os-error', 'value-error', 'timeout', 'key-error', 'type-error'}
SAFE_FAMILIES = ERROR_FAMILIES | {'none', 'prerequisite', 'isolation'}
FAILURE_SUBSTAGES = {
    4: {401, 402, 403, 404, 405, 406, 407, 408, 409, 410, 411, 412, 413, 414},
    6: {601, 602, 603, 604, 605, 606, 607, 608, 609, 610, 611, 612},
    7: {701, 702, 703, 704},
    12: {1201, 1202, 1203, 1204, 1205, 1206, 1207, 1208, 1209, 1210, 1211, 1212},
    202: {2021, 2022, 2023, 2024},
    203: {2031, 2032, 2033, 2034, 2035, 2036, 2037},
}
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
            and manifest['run_attempt'] == RUN_ATTEMPT and manifest['source_sha'] == SOURCE_SHA)
    for field in ('reader_sha256', 'contract_sha256', 'qualification_manifest_sha256'):
        require(digest(manifest[field]))
    require(sha256((ROOT / READER).read_bytes()) == manifest['reader_sha256']
            and sha256((ROOT / CONTRACT).read_bytes()) == manifest['contract_sha256']
            and sha256((ROOT / QUALIFICATION_MANIFEST).read_bytes()) ==
                manifest['qualification_manifest_sha256'])
    require(type(manifest['artifacts']) is dict and set(manifest['artifacts']) == set(PROFILES))
    ids = set()
    for profile in PROFILES:
        pin = manifest['artifacts'][profile]
        require(type(pin) is dict and set(pin) == ARTIFACT_FIELDS
                and type(pin['id']) is int and pin['id'] > 0 and pin['id'] not in ids
                and pin['name'] == 'dictation-candidate-qualification-' + profile
                and type(pin['bytes']) is int and 0 < pin['bytes'] <= 1_000_000
                and digest(pin['sha256']))
        ids.add(pin['id'])
    return manifest


def activation_guard():
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_WORKFLOW') ==
                'Read safe Small diagnostics for dictation run 38858151468'
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


def download(artifact_id, target):
    require(not target.exists())
    with target.open('xb') as output:
        result = subprocess.run(
            ['gh', 'api', REPO_API + '/actions/artifacts/' + str(artifact_id) + '/zip'],
            stdout=output, stderr=subprocess.PIPE, timeout=120, check=False)
    require(result.returncode == 0)


def validate_run(run, jobs):
    require(type(run) is dict and run.get('id') == RUN_ID and run.get('run_attempt') == RUN_ATTEMPT
            and run.get('head_sha') == SOURCE_SHA
            and run.get('head_branch') == 'codex/qualification-dispatch-20261010'
            and run.get('path') == WORKFLOW and run.get('event') == 'push'
            and run.get('status') in ('in_progress', 'completed')
            and run.get('conclusion') in (None, 'failure'))
    require(type(jobs) is dict and jobs.get('total_count') == 2
            and type(jobs.get('jobs')) is list and len(jobs['jobs']) == 2)
    expected = {'dictation (small-v2)', 'dictation (turbo-q5-v3)'}
    require({job.get('name') for job in jobs['jobs']} == expected)
    selected = next(job for job in jobs['jobs'] if job.get('name') == 'dictation (small-v2)')
    require(selected.get('status') == 'completed' and selected.get('conclusion') == 'failure')
    steps = {step.get('name'): step.get('conclusion') for step in selected.get('steps', [])}
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


def validate_context(value, profile, phase, installation_id):
    require(type(value) is dict and value.get('hardware_profile') == profile
            and value.get('phase') == phase and value.get('installation_id') == installation_id)
    for key, expected in CONTEXT_PINS.items():
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


def validate_recovery(value, archive, installation_id, report):
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
    require(not returncode_present or (type(returncode) is int and 1 <= returncode <= 255
            and stage == 202 and substage == 2022))
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
    require(type(artifact) is dict and artifact.get('id') == pin['id']
            and artifact.get('name') == pin['name'] and artifact.get('expired') is False
            and artifact.get('size_in_bytes') == pin['bytes']
            and artifact.get('digest') == 'sha256:' + pin['sha256'])
    workflow_run = artifact.get('workflow_run')
    require(type(workflow_run) is dict and workflow_run.get('id') == RUN_ID
            and workflow_run.get('head_sha') == SOURCE_SHA)
    require(type(archive_raw) is bytes and len(archive_raw) == pin['bytes']
            and sha256(archive_raw) == pin['sha256'])
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        items = archive.infolist()
        names = [item.filename for item in items]
        require(len(names) == len(set(names)) and BASE_MEMBERS <= set(names)
                and set(names) <= BASE_MEMBERS | set(RECOVERY_MEMBERS.values())
                and len(items) <= 7 and sum(item.file_size for item in items) <= 8_000_000)
        for item in items:
            safe_member(item, 4_000_000 if item.filename.endswith('.png') else 2_000_000)
        fixtures = archive.read('fixtures.json')
        require(len(fixtures) <= 128 * 1024 and sha256(fixtures) == FIXTURE_SHA256)
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
        require(type(state['installations']) is dict and set(state['installations']) == {'online', 'offline'}
                and all(uuid(value) for value in state['installations'].values())
                and state['installations']['online'] != state['installations']['offline'])
        # reports() writes and validates the bounded failed report before its
        # strict require-passed check raises.  The runner therefore retains the
        # exact JSON member but deliberately does not add a passing receipt for
        # it to execution.json.  Only the successful live report has a receipt.
        require(type(state['reports']) is dict
                and set(state['reports']) == {'online-installed-live'})
        reports = {}
        receipt = state['reports']['online-installed-live']
        require(type(receipt) is dict and set(receipt) == {'path', 'sha256', 'phase',
                'installation_id', 'boot_id', 'status'}
                and receipt['path'] == 'online-installed-live.json'
                and receipt['phase'] == 'live' and receipt['status'] == 'passed'
                and receipt['installation_id'] == state['installations']['online']
                and uuid(receipt['boot_id']) and digest(receipt['sha256']))
        live_raw = archive.read('online-installed-live.json')
        require(sha256(live_raw) == receipt['sha256'])
        live = strict_json(live_raw, 2_000_000)
        validate_context(live.get('context'), profile, 'live', state['installations']['online'])
        contract.validate(live, live['context'], require_passed=False,
                          fixture_manifest=fixtures)
        require(live['status'] == 'passed' and live['boot_id'] == receipt['boot_id'])
        reports['online-installed-live'] = live
        failed_raw = archive.read('online-installed.json')
        failed = strict_json(failed_raw, 2_000_000)
        validate_context(failed.get('context'), profile, 'online-installed',
                         state['installations']['online'])
        contract.validate(failed, failed['context'], require_passed=False,
                          fixture_manifest=fixtures)
        require(failed['status'] == 'failed')
        reports['online-installed'] = failed
        require(reports['online-installed-live']['boot_id'] != reports['online-installed']['boot_id'])
        require(type(state['indicators']) is dict and set(state['indicators']) == {'online-installed'})
        validate_indicator(state['indicators']['online-installed'], archive,
                           state['installations']['online'], reports['online-installed'])
        require(type(state['recovery_screens']) is dict
                and set(state['recovery_screens']) <= {'online-installed'})
        recovery = validate_recovery(state['recovery_screens'].get('online-installed', {}), archive,
                                     state['installations']['online'], reports['online-installed'])
        result = diagnostic(reports['online-installed'], recovery)
        result.update(profile=profile, artifact_id=pin['id'],
                      execution_status=state['status'], current_phase=state['current_phase'])
        return result


def inspect(manifest, api_call=api, downloader=download):
    validate_manifest(manifest)
    run = api_call('/actions/runs/' + str(RUN_ID))
    jobs = api_call('/actions/runs/' + str(RUN_ID) + '/jobs?filter=all&per_page=100')
    validate_run(run, jobs)
    contract = load_contract()
    results = {}
    with tempfile.TemporaryDirectory(prefix='arctic-dictation-safe-reader-') as directory:
        for profile in PROFILES:
            pin = manifest['artifacts'][profile]
            artifact = api_call('/actions/artifacts/' + str(pin['id']))
            target = Path(directory) / (profile + '.zip')
            downloader(pin['id'], target)
            results[profile] = inspect_artifact(profile, pin, artifact, target.read_bytes(), contract)
    return {'schema': 'arctic-dictation-safe-diagnostic-v1', 'run_id': RUN_ID,
            'release_acceptance': False, 'profiles': results}


def emit(report, output):
    require(type(report) is dict and report.get('schema') == 'arctic-dictation-safe-diagnostic-v1'
            and report.get('run_id') == RUN_ID and report.get('release_acceptance') is False
            and type(report.get('profiles')) is dict and set(report['profiles']) == set(PROFILES))
    print('ARCTIC-DICTATION-SAFE-DIAGNOSTIC=' +
          json.dumps(report, sort_keys=True, separators=(',', ':')), file=output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', required=True, type=Path)
    args = parser.parse_args()
    activation_guard()
    manifest = read_json_file(args.manifest, 32_768)
    emit(inspect(manifest), os.sys.stdout)


if __name__ == '__main__':
    main()
