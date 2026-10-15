#!/usr/bin/env python3
"""Fail-closed, temporary export of pinned screened qualification evidence."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import resource
import stat
import struct
import subprocess
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
SOURCE_BRANCH = 'codex/evidence-review-export-20261015'
TARGET_BRANCH = 'codex/evidence-review-artifacts-20261015'
WORKFLOW = '.github/workflows/evidence-review-export-20261015.yml'
MARKER = '.github/evidence-review-export-20261015.activate'
MANIFEST = 'tools/evidence-review-export/manifest.json'
SCHEMA = 'arctic-screened-evidence-review-export-v1'

BOUNDS = {
    'max_artifacts': 12,
    'max_archive_bytes_each': 250_000_000,
    'max_total_archive_bytes': 900_000_000,
    'max_zip_members_each': 50_000,
    'max_uncompressed_bytes_each': 750_000_000,
    'max_export_files': 320,
    'max_export_bytes_each': 32_000_000,
    'max_total_export_bytes': 150_000_000,
}

ALLOWED_WORKFLOWS = {
    '.github/workflows/iso.yml',
    '.github/workflows/release-reliability-candidate.yml',
    '.github/workflows/installer-candidate-20261009.yml',
    '.github/workflows/installer-active-candidate-20261009.yml',
    '.github/workflows/dictation-candidate-20261009.yml',
    '.github/workflows/native-candidate-20261008.yml',
    '.github/workflows/paired-candidate-20261009.yml',
    '.github/workflows/image-update-20261008.yml',
    '.github/workflows/inspect-exact-image-mango-20261010.yml',
    '.github/workflows/showcase-exact-capture-20261014.yml',
    '.github/workflows/showcase-river-render.yml',
    '.github/workflows/showcase-river-verify.yml',
}

BASE_FILE_FIELDS = {'member', 'output', 'kind', 'privacy_class', 'bytes', 'sha256'}
KIND_FIELDS = {
    'png': BASE_FILE_FIELDS | {'width', 'height'},
    'json': BASE_FILE_FIELDS,
    'audio': BASE_FILE_FIELDS | {'format'},
}
PRIVACY_CLASS = {
    'png': 'screened-vm-ui',
    'json': 'screened-summary',
    'audio': 'public-narration',
}
SUFFIXES = {
    'png': {'.png'},
    'json': {'.json'},
    'audio': {'.mp3', '.wav', '.flac', '.m4a'},
}
HEX40 = re.compile(r'[0-9a-f]{40}')
HEX64 = re.compile(r'[0-9a-f]{64}')
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._ +()-]{0,199}')
SAFE_OUTPUT = re.compile(r'evidence/[a-z0-9][a-z0-9._/-]{0,239}')
SENSITIVE_JSON_KEY = re.compile(
    r'(?i)(authorization|clipboard|detail|email|hypothesis|inserted.?text|journal|log|message|'
    r'password|prompt|raw.?text|recognized|secret|stderr|stdout|text|token|transcri|username|utterance)'
)
SENSITIVE_VALUE = re.compile(
    r'(?i)(authorization\s*:|(?:gh[pousr]_|github_pat_)[a-z0-9_]+|'
    r'(?:password|secret|token)\s*[=:]\s*\S+|[\w.+-]+@[\w.-]+|https?://\S*\?\S+)'
)
BASE64_VALUE = re.compile(r'[A-Za-z0-9+/]{257,}={0,2}')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=120).strip()


def safe_archive_member(name):
    require(type(name) is str and name and '\x00' not in name and '\\' not in name,
            'Unsafe archive member name')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in path.parts),
            'Unsafe archive member path: ' + name)
    return path


def safe_output_path(name):
    require(type(name) is str and SAFE_OUTPUT.fullmatch(name), 'Unsafe review output path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in path.parts),
            'Unsafe review output path: ' + name)
    return path


def validate_file(value):
    require(type(value) is dict and value.get('kind') in KIND_FIELDS,
            'Malformed evidence file entry')
    kind = value['kind']
    require(set(value) == KIND_FIELDS[kind], 'Evidence file fields differ: ' + kind)
    member = safe_archive_member(value['member'])
    output = safe_output_path(value['output'])
    require(member.suffix.lower() in SUFFIXES[kind] and output.suffix.lower() in SUFFIXES[kind],
            'Evidence type and filename suffix differ')
    require(value['privacy_class'] == PRIVACY_CLASS[kind],
            'Evidence privacy class is not approved')
    require(type(value['bytes']) is int and 0 < value['bytes'] <= BOUNDS['max_export_bytes_each'],
            'Evidence file size is invalid')
    require(type(value['sha256']) is str and HEX64.fullmatch(value['sha256']),
            'Evidence file digest is invalid')
    if kind == 'png':
        require(type(value['width']) is int and 1 <= value['width'] <= 4096
                and type(value['height']) is int and 1 <= value['height'] <= 4096
                and value['width'] * value['height'] <= 16_777_216,
                'PNG dimensions are invalid')
    if kind == 'audio':
        require(value['format'] in {'mp3', 'wav', 'flac', 'm4a'}
                and output.suffix.lower() == '.' + value['format'],
                'Audio format is invalid')
    return value


def validate_manifest(value, require_ready=True):
    fields = {'schema', 'ready', 'review_only', 'repository', 'source_branch',
              'target_branch', 'bounds', 'artifacts'}
    require(type(value) is dict and set(value) == fields, 'Evidence export manifest fields differ')
    require(value['schema'] == SCHEMA and value['review_only'] is True
            and value['repository'] == REPOSITORY and value['source_branch'] == SOURCE_BRANCH
            and value['target_branch'] == TARGET_BRANCH and value['bounds'] == BOUNDS,
            'Evidence export identity or immutable bounds differ')
    require(type(value['ready']) is bool and type(value['artifacts']) is list,
            'Evidence export readiness is malformed')
    if not value['ready']:
        require(not value['artifacts'], 'Disabled export manifest must not pin artifacts')
        require(not require_ready, 'Evidence review export is disabled')
        return value
    require(1 <= len(value['artifacts']) <= BOUNDS['max_artifacts'],
            'Evidence artifact count is invalid')
    artifact_ids = set()
    outputs = set()
    file_count = 0
    total_archive = 0
    total_export = 0
    artifact_fields = {'artifact_id', 'run_id', 'run_attempt', 'head_sha', 'head_branch',
                       'workflow_path', 'event', 'name', 'archive_bytes',
                       'archive_sha256', 'screening', 'files'}
    for artifact in value['artifacts']:
        require(type(artifact) is dict and set(artifact) == artifact_fields,
                'Evidence artifact fields differ')
        require(type(artifact['artifact_id']) is int and artifact['artifact_id'] > 0
                and artifact['artifact_id'] not in artifact_ids,
                'Evidence artifact ID is invalid or duplicated')
        artifact_ids.add(artifact['artifact_id'])
        require(type(artifact['run_id']) is int and artifact['run_id'] > 0
                and type(artifact['run_attempt']) is int and artifact['run_attempt'] > 0,
                'Evidence run identity is invalid')
        require(type(artifact['head_sha']) is str and HEX40.fullmatch(artifact['head_sha'])
                and type(artifact['head_branch']) is str
                and re.fullmatch(r'codex/[a-z0-9][a-z0-9._/-]{0,199}', artifact['head_branch']),
                'Evidence run source identity is invalid')
        require(artifact['workflow_path'] in ALLOWED_WORKFLOWS and artifact['event'] == 'push',
                'Evidence workflow is not an approved qualification lane')
        require(type(artifact['name']) is str and SAFE_NAME.fullmatch(artifact['name']),
                'Evidence artifact name is invalid')
        require(type(artifact['archive_bytes']) is int
                and 0 < artifact['archive_bytes'] <= BOUNDS['max_archive_bytes_each']
                and type(artifact['archive_sha256']) is str
                and HEX64.fullmatch(artifact['archive_sha256']),
                'Evidence archive pin is invalid')
        require(artifact['screening'] == {'stage': 'producer-screened', 'transcript_free': True},
                'Evidence was not declared producer-screened and transcript-free')
        require(type(artifact['files']) is list and artifact['files'],
                'Evidence artifact has no selected files')
        total_archive += artifact['archive_bytes']
        members = set()
        for item in artifact['files']:
            validate_file(item)
            require(item['member'] not in members,
                    'Duplicate selected archive member: ' + item['member'])
            members.add(item['member'])
            require(item['output'] not in outputs, 'Duplicate review output: ' + item['output'])
            outputs.add(item['output'])
            total_export += item['bytes']
            file_count += 1
    require(total_archive <= BOUNDS['max_total_archive_bytes'], 'Total archive bound exceeded')
    require(file_count <= BOUNDS['max_export_files'], 'Export file count bound exceeded')
    require(total_export <= BOUNDS['max_total_export_bytes'], 'Total export byte bound exceeded')
    return value


def validate_activation(manifest_path):
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + SOURCE_BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
            'Requires the dedicated first-attempt GitHub-hosted review export lane')
    event = strict_json(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    marker = (ROOT / MARKER).read_text().strip()
    head = git('rev-parse', 'HEAD')
    require(HEX40.fullmatch(marker) and event.get('before') == marker
            and event.get('after') == os.environ.get('GITHUB_SHA') == head
            and git('rev-list', '--parents', '-n', '1', 'HEAD').split() == [head, marker]
            and git('diff', '--no-renames', '--name-only', marker, 'HEAD').splitlines() == [MARKER]
            and not git('status', '--porcelain'),
            'Evidence export activation is not the reviewed marker-only child')
    manifest = validate_manifest(strict_json(Path(manifest_path).read_text()))
    return manifest, marker, head


def fetch_json(endpoint):
    raw = subprocess.check_output(['gh', 'api', endpoint], timeout=120)
    return strict_json(raw.decode())


def download_archive(endpoint, destination, expected_bytes):
    def limit_output_size():
        resource.setrlimit(resource.RLIMIT_FSIZE, (expected_bytes, expected_bytes))
    with Path(destination).open('xb') as stream:
        subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=stream,
                       check=True, timeout=1200, preexec_fn=limit_output_size)
    require(Path(destination).stat().st_size == expected_bytes,
            'Downloaded artifact byte count differs from its pin')


def verify_remote_identity(artifact, metadata, run):
    require(type(metadata) is dict and metadata.get('id') == artifact['artifact_id']
            and metadata.get('name') == artifact['name'] and metadata.get('expired') is False
            and metadata.get('size_in_bytes') == artifact['archive_bytes']
            and metadata.get('digest') == 'sha256:' + artifact['archive_sha256'],
            'Remote artifact identity differs from its review pin')
    workflow_run = metadata.get('workflow_run')
    require(type(workflow_run) is dict and workflow_run.get('id') == artifact['run_id']
            and workflow_run.get('head_sha') == artifact['head_sha']
            and workflow_run.get('head_branch') == artifact['head_branch'],
            'Artifact workflow-run identity differs from its review pin')
    require(type(run) is dict and run.get('id') == artifact['run_id']
            and run.get('run_attempt') == artifact['run_attempt']
            and run.get('head_sha') == artifact['head_sha']
            and run.get('head_branch') == artifact['head_branch']
            and run.get('path') == artifact['workflow_path'] and run.get('event') == artifact['event']
            and run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'Qualification run is not the pinned successful completed run')


def inspect_png(raw):
    require(raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw) >= 24
            and raw[12:16] == b'IHDR', 'Invalid PNG evidence')
    return struct.unpack('>II', raw[16:24])


def inspect_audio(raw, fmt):
    signatures = {
        'mp3': raw.startswith(b'ID3') or (len(raw) >= 2 and raw[0] == 0xff and raw[1] & 0xe0 == 0xe0),
        'wav': raw.startswith(b'RIFF') and len(raw) >= 12 and raw[8:12] == b'WAVE',
        'flac': raw.startswith(b'fLaC'),
        'm4a': len(raw) >= 12 and raw[4:8] == b'ftyp',
    }
    require(signatures[fmt], 'Invalid ' + fmt + ' audio evidence')


def inspect_json_value(value, path='$'):
    if isinstance(value, dict):
        for key, child in value.items():
            require(type(key) is str and not SENSITIVE_JSON_KEY.search(key),
                    'Sensitive JSON field is not exportable: ' + path + '.' + key)
            inspect_json_value(child, path + '.' + key)
    elif isinstance(value, list):
        require(len(value) <= 10_000, 'Oversized JSON array')
        for index, child in enumerate(value):
            inspect_json_value(child, f'{path}[{index}]')
    elif isinstance(value, str):
        require(len(value) <= 2048 and not SENSITIVE_VALUE.search(value)
                and not BASE64_VALUE.fullmatch(value),
                'Sensitive or oversized JSON string is not exportable: ' + path)
    else:
        require(value is None or type(value) in (bool, int)
                or (type(value) is float and math.isfinite(value)), 'Unsupported JSON value')


def inspect_selected(raw, item):
    require(len(raw) == item['bytes'] and digest_bytes(raw) == item['sha256'],
            'Selected evidence bytes differ from their pin: ' + item['member'])
    if item['kind'] == 'png':
        require(inspect_png(raw) == (item['width'], item['height']),
                'PNG dimensions differ from their pin')
    elif item['kind'] == 'audio':
        inspect_audio(raw, item['format'])
    else:
        inspect_json_value(strict_json(raw.decode('utf-8')))


def extract_artifact(artifact, archive_path, output_root):
    require(archive_path.stat().st_size == artifact['archive_bytes']
            and digest_file(archive_path) == artifact['archive_sha256'],
            'Downloaded artifact archive differs from its pin')
    selected = {item['member']: item for item in artifact['files']}
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        require(len(infos) <= BOUNDS['max_zip_members_each'], 'Archive member bound exceeded')
        names = []
        total = 0
        for info in infos:
            safe_archive_member(info.filename.rstrip('/') if info.is_dir() else info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR),
                    'Archive contains a special file: ' + info.filename)
            names.append(info.filename)
            total += info.file_size
        require(len(names) == len(set(names)), 'Archive contains duplicate member names')
        require(total <= BOUNDS['max_uncompressed_bytes_each'], 'Archive expansion bound exceeded')
        require(set(selected) <= set(names), 'Selected evidence member is absent from archive')
        records = []
        for member, item in selected.items():
            info = archive.getinfo(member)
            require(not info.is_dir() and info.file_size == item['bytes'],
                    'Selected evidence member size differs from its pin')
            raw = archive.read(info)
            inspect_selected(raw, item)
            destination = output_root / item['output']
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(raw)
            records.append({key: item[key] for key in sorted(item)})
        return records


def export(manifest_path, output_path):
    manifest, parent, head = validate_activation(manifest_path)
    output_root = Path(output_path)
    output_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    records = []
    with tempfile.TemporaryDirectory(prefix='arctic-evidence-export-') as temp:
        for artifact in manifest['artifacts']:
            endpoint = f'repos/{REPOSITORY}/actions/artifacts/{artifact["artifact_id"]}'
            metadata = fetch_json(endpoint)
            run = fetch_json(f'repos/{REPOSITORY}/actions/runs/{artifact["run_id"]}')
            verify_remote_identity(artifact, metadata, run)
            archive_path = Path(temp) / f'{artifact["artifact_id"]}.zip'
            download_archive(endpoint, archive_path, artifact['archive_bytes'])
            files = extract_artifact(artifact, archive_path, output_root)
            records.append({
                'artifact_id': artifact['artifact_id'],
                'run_id': artifact['run_id'],
                'run_attempt': artifact['run_attempt'],
                'head_sha': artifact['head_sha'],
                'head_branch': artifact['head_branch'],
                'workflow_path': artifact['workflow_path'],
                'name': artifact['name'],
                'archive_bytes': artifact['archive_bytes'],
                'archive_sha256': artifact['archive_sha256'],
                'files': files,
            })
    receipt = {
        'schema': SCHEMA,
        'review_only': True,
        'repository': REPOSITORY,
        'source_branch': SOURCE_BRANCH,
        'target_branch': TARGET_BRANCH,
        'reviewed_parent_sha': parent,
        'activation_sha': head,
        'export_run_id': int(os.environ['GITHUB_RUN_ID']),
        'export_run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
        'artifacts': records,
    }
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    with (output_root / 'REVIEW-MANIFEST.json').open('xb') as stream:
        stream.write(raw)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('validate-manifest')
    check.add_argument('--manifest', default=MANIFEST)
    run = sub.add_parser('export')
    run.add_argument('--manifest', default=MANIFEST)
    run.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.command == 'validate-manifest':
        validate_manifest(strict_json(Path(args.manifest).read_text()))
    else:
        export(args.manifest, args.out)


if __name__ == '__main__':
    main()
