#!/usr/bin/env python3
"""Print only the safe identity fields of one exact Arctic ISO producer run."""
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
WORKFLOW = '.github/workflows/iso.yml'
RUN_ID = 38823208615
RUN_ATTEMPT = 1
SOURCE_SHA = 'cfc39dad61125e4fa8fb7906ac14f4c360b58228'
BRANCH = 'codex/prepare-final-iso-reader-20261015'
ACTIVATION = Path('.github/final-iso-reader-38823208615.activate')
RECEIPT_NAME = 'PERFORMANCE-PLAN.json'
MAX_RECEIPT_ARCHIVE_BYTES = 131_072
MAX_RECEIPT_BYTES = 32_768
MAX_ISO_ARCHIVE_BYTES = 2_010_000_000
MANIFEST_FIELDS = {
    'schema', 'ready', 'repository', 'workflow', 'run_id', 'run_attempt',
    'source_sha', 'iso_artifact_id', 'receipt_artifact_id',
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'Duplicate JSON field')
        result[key] = value
    return result


def sha256_bytes(raw):
    return hashlib.sha256(raw).hexdigest()


def read_json_file(path, maximum):
    require(path.is_file() and not path.is_symlink() and 0 < path.stat().st_size <= maximum,
            'JSON input is absent, linked or oversized')
    return json.loads(path.read_bytes(), object_pairs_hook=unique)


def validate_manifest(manifest):
    require(isinstance(manifest, dict) and set(manifest) == MANIFEST_FIELDS,
            'Reader manifest fields differ')
    require(manifest['schema'] == 'arctic-final-iso-identity-reader-v1'
            and manifest['ready'] is True,
            'Final ISO identity reader remains disabled until exact artifacts are reviewed')
    require(manifest['repository'] == REPOSITORY and manifest['workflow'] == WORKFLOW
            and manifest['run_id'] == RUN_ID and manifest['run_attempt'] == RUN_ATTEMPT
            and manifest['source_sha'] == SOURCE_SHA,
            'Pinned producer repository, workflow, run, attempt or source differs')
    for field in ('iso_artifact_id', 'receipt_artifact_id'):
        require(type(manifest[field]) is int and manifest[field] > 0,
                'Exact artifact IDs have not been pinned')
    require(manifest['iso_artifact_id'] != manifest['receipt_artifact_id'],
            'ISO and receipt artifacts must be distinct')
    return manifest


def activation_guard(root):
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
            'Reader must be the first push attempt on its dedicated branch')
    source = os.environ.get('GITHUB_SHA', '')
    require(re.fullmatch('[0-9a-f]{40}', source), 'Invalid reader source identity')
    marker = root / ACTIVATION
    require(marker.is_file() and not marker.is_symlink() and marker.stat().st_size == 41,
            'Reviewed activation marker is absent')
    reviewed = marker.read_text().strip()
    require(re.fullmatch('[0-9a-f]{40}', reviewed), 'Invalid reviewed activation parent')
    event = read_json_file(Path(os.environ['GITHUB_EVENT_PATH']), 1_000_000)
    require(event.get('before') == reviewed and event.get('after') == source,
            'Push event does not bind the reviewed parent and activation child')
    parent_line = subprocess.check_output(
        ['git', '-C', str(root), 'rev-list', '--parents', '-n', '1', source],
        text=True, timeout=30).split()
    require(parent_line == [source, reviewed], 'Activation must have exactly one reviewed parent')
    require(marker.read_bytes() == (reviewed + '\n').encode(), 'Activation bytes differ')
    changed = subprocess.check_output(
        ['git', '-C', str(root), 'diff', '--name-only', reviewed, source],
        text=True, timeout=30).splitlines()
    require(changed == [ACTIVATION.as_posix()], 'Activation child changed reviewed source')
    require(not subprocess.check_output(
        ['git', '-C', str(root), 'status', '--porcelain'], text=True, timeout=30).strip(),
        'Reader checkout is dirty')


def api(path):
    raw = subprocess.check_output(['gh', 'api', REPO_API + path], timeout=60)
    require(len(raw) <= 20_000_000, 'GitHub API response is oversized')
    return json.loads(raw, object_pairs_hook=unique)


def download_artifact(artifact_id, target):
    require(not target.exists(), 'Artifact download path must be unused')
    with target.open('xb') as output:
        result = subprocess.run(
            ['gh', 'api', REPO_API + '/actions/artifacts/' + str(artifact_id) + '/zip'],
            stdout=output, stderr=subprocess.PIPE, timeout=180, check=False)
    require(result.returncode == 0, 'Receipt artifact download failed')


def load_fetch_contract():
    path = ROOT / 'tools/native-functional/fetch-image.py'
    require(path.is_file() and not path.is_symlink(), 'Existing image fetch contract is absent')
    spec = importlib.util.spec_from_file_location('final_iso_fetch_contract', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_run(run):
    require(isinstance(run, dict) and run.get('id') == RUN_ID
            and run.get('head_sha') == SOURCE_SHA and run.get('event') == 'workflow_dispatch'
            and run.get('path') == WORKFLOW and run.get('run_attempt') == RUN_ATTEMPT
            and run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'Exact first-attempt producer run is absent or unsuccessful')


def validate_artifact(artifact, artifact_id, name, maximum):
    require(isinstance(artifact, dict) and artifact.get('id') == artifact_id
            and artifact.get('name') == name and artifact.get('expired') is False,
            'Pinned artifact identity is absent, renamed or expired')
    workflow_run = artifact.get('workflow_run')
    require(isinstance(workflow_run, dict) and workflow_run.get('id') == RUN_ID
            and workflow_run.get('head_sha') == SOURCE_SHA,
            'Pinned artifact belongs to another run or source')
    size = artifact.get('size_in_bytes')
    digest = artifact.get('digest')
    require(type(size) is int and 0 < size <= maximum
            and type(digest) is str and re.fullmatch('sha256:[0-9a-f]{64}', digest),
            'Pinned artifact size or digest is invalid')


def receipt_member(archive_raw):
    require(isinstance(archive_raw, bytes) and 0 < len(archive_raw) <= MAX_RECEIPT_ARCHIVE_BYTES,
            'Receipt archive is absent or oversized')
    with zipfile.ZipFile(io.BytesIO(archive_raw)) as archive:
        entries = archive.infolist()
        require(len(entries) == 1 and entries[0].filename == RECEIPT_NAME,
                'Receipt archive member inventory differs')
        entry = entries[0]
        path = PurePosixPath(entry.filename)
        mode = entry.external_attr >> 16
        require(not path.is_absolute() and '..' not in path.parts and len(path.parts) == 1
                and not entry.is_dir() and stat.S_IFMT(mode) in (0, stat.S_IFREG)
                and not (entry.flag_bits & 0x1)
                and entry.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                and 0 < entry.file_size <= MAX_RECEIPT_BYTES
                and 0 <= entry.compress_size <= MAX_RECEIPT_ARCHIVE_BYTES,
                'Unsafe receipt archive member')
        raw = archive.read(entry)
    require(len(raw) == entry.file_size, 'Receipt member length differs')
    return raw


def preliminary_receipt(raw):
    require(0 < len(raw) <= MAX_RECEIPT_BYTES, 'Producer receipt is absent or oversized')
    receipt = json.loads(raw, object_pairs_hook=unique)
    require(isinstance(receipt, dict) and isinstance(receipt.get('image'), dict)
            and set(receipt['image']) == {'name', 'bytes', 'sha256'},
            'Producer receipt image identity is malformed')
    return receipt


def inspect(manifest, workspace, api_call=api, downloader=download_artifact, fetch=None):
    validate_manifest(manifest)
    fetch = fetch or load_fetch_contract()
    run = api_call('/actions/runs/' + str(RUN_ID))
    validate_run(run)
    iso_artifact = api_call('/actions/artifacts/' + str(manifest['iso_artifact_id']))
    receipt_artifact = api_call('/actions/artifacts/' + str(manifest['receipt_artifact_id']))
    validate_artifact(iso_artifact, manifest['iso_artifact_id'], 'arctic-linux-iso',
                      MAX_ISO_ARCHIVE_BYTES)
    validate_artifact(receipt_artifact, manifest['receipt_artifact_id'],
                      'arctic-external-producer-receipt', MAX_RECEIPT_ARCHIVE_BYTES)

    archive = workspace / 'receipt.zip'
    downloader(manifest['receipt_artifact_id'], archive)
    archive_raw = archive.read_bytes()
    require(len(archive_raw) == receipt_artifact['size_in_bytes']
            and 'sha256:' + sha256_bytes(archive_raw) == receipt_artifact['digest'],
            'Downloaded receipt archive bytes differ from GitHub metadata')
    receipt_raw = receipt_member(archive_raw)
    receipt_preview = preliminary_receipt(receipt_raw)
    image = dict(receipt_preview['image'], run_id=RUN_ID, source_sha=SOURCE_SHA,
                 artifact_id=manifest['iso_artifact_id'],
                 archive_bytes=iso_artifact['size_in_bytes'],
                 archive_sha256=iso_artifact['digest'].removeprefix('sha256:'),
                 producer_mode=fetch.EXTERNAL_MODE,
                 producer_receipt_sha256=sha256_bytes(receipt_raw))
    receipt = fetch.read_receipt(receipt_raw, image)
    fetch.validate(image, run, iso_artifact)
    jobs = api_call('/actions/runs/' + str(RUN_ID) + '/jobs?filter=all&per_page=100')
    require(isinstance(jobs, dict) and type(jobs.get('total_count')) is int
            and isinstance(jobs.get('jobs'), list)
            and jobs['total_count'] == len(jobs['jobs']) and jobs['total_count'] <= 100,
            'Producer job inventory is incomplete')
    fetch.validate_external_producer_steps(image, jobs['jobs'])
    return {
        'image': receipt['image'],
        'receipt_sha256': sha256_bytes(receipt_raw),
        'startup_results': receipt['startup_results'],
        'artifact_id': iso_artifact['id'],
        'archive_bytes': iso_artifact['size_in_bytes'],
        'archive_sha256': iso_artifact['digest'].removeprefix('sha256:'),
    }


def emit(report, output):
    lines = [
        ('ISO_NAME', report['image']['name']),
        ('ISO_BYTES', report['image']['bytes']),
        ('ISO_SHA256', report['image']['sha256']),
        ('PRODUCER_RECEIPT_SHA256', report['receipt_sha256']),
    ]
    for lane in ('uefi-try', 'bios-install', 'uefi-safe'):
        prefix = 'STARTUP_' + lane.upper().replace('-', '_')
        result = report['startup_results'][lane]
        lines.extend(((prefix + '_STATUS', result['status']),
                      (prefix + '_SERIAL_BYTES', result['serial_bytes']),
                      (prefix + '_SERIAL_SHA256', result['serial_sha256'])))
    lines.extend((('ARCHIVE_BYTES', report['archive_bytes']),
                  ('ARCHIVE_SHA256', report['archive_sha256']),
                  ('ARTIFACT_ID', report['artifact_id'])))
    for key, value in lines:
        print(f'{key}={value}', file=output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    activation_guard(ROOT)
    manifest = read_json_file(args.manifest, 32_768)
    with tempfile.TemporaryDirectory(prefix='arctic-final-iso-reader-') as directory:
        report = inspect(manifest, Path(directory))
    emit(report, os.sys.stdout)


if __name__ == '__main__':
    main()
