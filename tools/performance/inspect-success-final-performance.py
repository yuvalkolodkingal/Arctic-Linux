#!/usr/bin/env python3
"""Replay one exact screened performance artifact and emit bounded release fields."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPO = 'repos/yuvalkolodkingal/Arctic-Linux'
RUN_ID = 38841063654
SOURCE_SHA = '8dde4600e295964c0ddfa0fdb76af2676efc7116'
REVIEWED_PARENT_SHA = '8c9571f24cad0f6e2c6d016ca0225bffc377fd71'
ARTIFACT_ID = 12025875027
ARCHIVE_BYTES = 19_633_955
ARCHIVE_SHA256 = 'b34dd39aa1c8f01bdf63448f7667eeefb8efd5cf43d7f2b98bd42eb3183f83e6'
WORKFLOW = '.github/workflows/paired-candidate-20261009.yml'
PLAN = 'tools/performance/execution-manifest.json'


def require(condition):
    if not condition:
        raise ValueError('successful performance reader rejected evidence')


def digest(content):
    return hashlib.sha256(content).hexdigest()


def file_digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def api(path):
    completed = subprocess.run(['gh', 'api', REPO + path], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, check=False, timeout=60)
    require(completed.returncode == 0 and len(completed.stdout) <= 256 * 1024)
    return json.loads(completed.stdout)


def source_bytes(ref, name):
    require(re.fullmatch('[0-9a-f]{40}', ref) is not None
            and not Path(name).is_absolute() and '..' not in Path(name).parts)
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', ref + ':' + name], timeout=120)


def load_verified(name, path, expected):
    require(path.is_file() and not path.is_symlink() and file_digest(path) == expected)
    content = path.read_bytes()
    require(digest(content) == expected)
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    module.__file__ = str(path)
    exec(compile(content, str(path), 'exec'), module.__dict__)
    return module


def finite_number(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


def bounded_metrics(comparison):
    expected = {
        'boot_systemd_total', 'root_filesystem_du_allocation',
        'process_pss_bytes', 'pristine_process_pss_bytes',
        'process_private_bytes', 'pristine_process_private_bytes',
        'cpu_busy_percent', 'pristine_cpu_busy_percent',
        'MemAvailable_bytes', 'pristine_MemAvailable_bytes',
        'fish_launch_or_roundtrip', 'bash_launch_or_roundtrip',
        'shell_ipc_launch_or_roundtrip',
        *{role + '_' + suffix for role in ('terminal', 'files', 'browser')
          for suffix in ('first_gui_role_mapped', 'first_mapped_after_preconditioning',
                         'subsequent_mapped')},
    }
    rows = comparison['metrics']
    require(isinstance(rows, list) and len(rows) == len(expected)
            and {row.get('metric') for row in rows} == expected)
    projected = []
    fields = {'metric', 'unit', 'per_boot', 'median', 'range', 'percent_difference',
              'range_overlap', 'regression_threshold_percent', 'regression'}
    for row in rows:
        require(row.get('unit') in {'seconds', 'bytes', 'percent'}
                and type(row.get('regression')) is bool
                and type(row.get('range_overlap')) is bool)
        for key in ('per_boot', 'median', 'range'):
            value = row.get(key)
            require(type(value) is dict and set(value) == {'baseline', 'candidate'})
        require(all(isinstance(values, list) and len(values) == 3
                    and all(finite_number(value) for value in values)
                    for values in row['per_boot'].values()))
        require(all(finite_number(value) for value in row['median'].values()))
        require(all(isinstance(values, list) and len(values) == 2
                    and all(finite_number(value) for value in values)
                    for values in row['range'].values()))
        require(row['percent_difference'] is None or finite_number(row['percent_difference']))
        require(row['regression_threshold_percent'] is None
                or finite_number(row['regression_threshold_percent']))
        projected.append({key: row[key] for key in fields})
    return projected


def project(replay, execution_sha256, plan_sha256):
    comparison = replay['comparison']
    precision = comparison['measurement_precision']
    require(replay['performance_mode'] == 'frozen-external-paired-v1'
            and replay['execution_run_id'] == RUN_ID
            and replay['execution_source_sha'] == SOURCE_SHA
            and replay['original_serials_replayed'] == 6
            and replay['release_acceptance'] is False
            and comparison['status'] == 'regression_gate_passed'
            and precision['valid'] is True
            and precision['threshold_enclosure_valid'] is True)
    roles = comparison['application_role_comparison']
    role_ids = {image: {role: roles[image]['roles'][role]['id']
                        for role in ('terminal', 'files', 'browser')}
                for image in ('baseline', 'candidate')}
    require(role_ids == {
        'baseline': {'terminal': 'kitty', 'files': 'nautilus', 'browser': 'zen'},
        'candidate': {'terminal': 'foot', 'files': 'pcmanfm', 'browser': 'gnome-web'},
    })
    limitations = comparison['limitations']
    require(isinstance(limitations, list) and len(limitations) == 9
            and all(isinstance(item, str) and 0 < len(item) <= 512 for item in limitations))
    return {
        'schema': 'arctic-final-performance-success-fields-v1',
        'run_id': RUN_ID,
        'run_attempt': 1,
        'source_sha': SOURCE_SHA,
        'reviewed_parent_sha': REVIEWED_PARENT_SHA,
        'artifact_id': ARTIFACT_ID,
        'archive_bytes': ARCHIVE_BYTES,
        'archive_sha256': ARCHIVE_SHA256,
        'plan_sha256': plan_sha256,
        'execution_json_sha256': execution_sha256,
        'status': comparison['status'],
        'original_serials_replayed': 6,
        'measurement_precision': {
            'valid': True,
            'threshold_enclosure_valid': True,
            'rule': precision['rule'],
            'enclosure_rule': precision['enclosure_rule'],
        },
        'applications': role_ids,
        'metrics': bounded_metrics(comparison),
        'limitations': limitations,
        'release_acceptance': False,
    }


def main():
    require(os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_ACTIONS') == 'true')
    run = api('/actions/runs/' + str(RUN_ID))
    require(run.get('id') == RUN_ID and run.get('head_sha') == SOURCE_SHA
            and run.get('head_branch') == 'codex/qualification-dispatch-20261010'
            and run.get('path') == WORKFLOW and run.get('event') == 'push'
            and run.get('run_attempt') == 1 and run.get('status') == 'completed'
            and run.get('conclusion') == 'success')
    artifact = api('/actions/artifacts/' + str(ARTIFACT_ID))
    require(artifact.get('id') == ARTIFACT_ID
            and artifact.get('name') == 'external-paired-performance'
            and artifact.get('expired') is False
            and artifact.get('size_in_bytes') == ARCHIVE_BYTES
            and artifact.get('digest') == 'sha256:' + ARCHIVE_SHA256
            and artifact.get('workflow_run', {}).get('id') == RUN_ID
            and artifact.get('workflow_run', {}).get('head_sha') == SOURCE_SHA)

    plan_raw = source_bytes(SOURCE_SHA, PLAN)
    plan_sha256 = digest(plan_raw)
    local_plan = ROOT / PLAN
    require(local_plan.is_file() and not local_plan.is_symlink()
            and local_plan.read_bytes() == plan_raw)
    provisional = json.loads(plan_raw)
    contract_hash = provisional['execution_files']['tools/performance/contract.py']
    contract = load_verified('final_success_performance_contract',
                             ROOT / 'tools/performance/contract.py', contract_hash)
    plan = contract.parse_json(plan_raw)
    expected_files = {name: digest(source_bytes(SOURCE_SHA, name))
                      for name in contract.EXECUTION_FILES}
    candidate_sources = {name: digest(source_bytes(plan['image']['source_sha'], name))
                         for name in contract.CANDIDATE_SOURCE_FILES}
    observer = contract.observer_hashes_from_sources(
        source_bytes(SOURCE_SHA, 'tools/performance/guest.py'),
        source_bytes(SOURCE_SHA, 'tools/performance/causal.py'))
    observer['comparator_sha256'] = digest(source_bytes(SOURCE_SHA, 'tools/performance/compare.py'))
    contract.validate_plan(plan, candidate_source_files=candidate_sources,
                           execution_files=expected_files, observer=observer)

    fetch = load_verified('final_success_performance_fetch',
                          ROOT / 'tools/native-functional/fetch-image.py',
                          expected_files['tools/native-functional/fetch-image.py'])
    comparator = load_verified('final_success_performance_compare',
                               ROOT / 'tools/performance/compare.py',
                               observer['comparator_sha256'])
    endpoint = '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip'
    with tempfile.TemporaryDirectory(prefix='arctic-final-performance-success-') as folder:
        archive_path = Path(folder) / 'artifact.zip'
        with archive_path.open('xb') as output:
            completed = subprocess.run(['gh', 'api', REPO + endpoint], stdout=output,
                                       stderr=subprocess.PIPE, check=False, timeout=180)
        require(completed.returncode == 0 and archive_path.stat().st_size == ARCHIVE_BYTES
                and file_digest(archive_path) == ARCHIVE_SHA256)
        with zipfile.ZipFile(archive_path) as evidence:
            receipt_raw = evidence.read('producer-receipt.json')
            receipt = fetch.read_receipt(receipt_raw, plan['image'])
            replay = contract.validate_evidence(
                evidence, plan=plan, plan_sha256=plan_sha256, image=plan['image'],
                execution_source_sha=SOURCE_SHA, reviewed_parent_sha=REVIEWED_PARENT_SHA,
                execution_run_id=RUN_ID, comparator=comparator, producer_receipt=receipt)
            execution_sha256 = digest(evidence.read('execution.json'))
    result = project(replay, execution_sha256, plan_sha256)
    content = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False)
    require(len(content.encode()) <= 32 * 1024)
    print('ARCTIC-FINAL-PERFORMANCE-SUCCESS=' + content)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('ARCTIC-FINAL-PERFORMANCE-SUCCESS-READER=rejected')
        raise SystemExit(1)
