#!/usr/bin/env python3
"""Validate and project one exact external ISO producer receipt."""
from io import BytesIO
import hashlib
import json
import os
from pathlib import PurePosixPath
import re
import stat
import subprocess
import sys
import zipfile

REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
RUN_ID = 38879661832
RUN_ATTEMPT = 1
WORKFLOW_ID = 368518403
WORKFLOW_PATH = '.github/workflows/iso.yml'
SOURCE_BRANCH = 'codex/final-source-candidate-20261015'
SOURCE_SHA = 'f369b978aeb05a3310c512660811084fd5bc97d1'
ARTIFACT_ID = 12039394376
ARTIFACT_NAME = 'arctic-external-producer-receipt'
ARTIFACT_BYTES = 1700
ARTIFACT_SHA256 = '4f8858390a875d84c49928aebda5d3b4a15e737307e1d8e37b2f9c7b99f50302'
RECEIPT_MEMBER = 'PERFORMANCE-PLAN.json'
IMAGE_NAME = f'Arctic-Linux-1.2-candidate-{RUN_ID}-{RUN_ATTEMPT}-x86_64.iso'
HEX64 = re.compile(r'[0-9a-f]{64}')
TOP_LEVEL = {
    'schema', 'repository', 'workflow', 'event', 'source_sha', 'run_id',
    'run_attempt', 'mode', 'release_acceptance', 'inputs', 'image',
    'startup_results',
}
INPUTS = {
    'expected_source_sha': SOURCE_SHA,
    'release': False,
    'tag': '',
    'prerelease': True,
    'draft': False,
    'nix_acceptance': False,
    'performance_acceptance': False,
    'boot_test': True,
    'performance_mode': 'frozen-external-paired-v1',
}
LANES = {
    'uefi-try': ('uefi', 'try'),
    'bios-install': ('bios', 'install'),
    'uefi-safe': ('uefi', 'safe'),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate JSON field')
        result[key] = value
    return result


def api(endpoint):
    return json.loads(subprocess.check_output(
        ['gh', 'api', f'repos/{REPOSITORY}/{endpoint}'], timeout=60),
        object_pairs_hook=unique)


def validate_run(run):
    require(run.get('id') == RUN_ID and run.get('run_attempt') == RUN_ATTEMPT,
            'producer run identity differs')
    require(run.get('name') == 'ISO' and run.get('workflow_id') == WORKFLOW_ID
            and run.get('path') == WORKFLOW_PATH, 'producer workflow differs')
    require(run.get('head_branch') == SOURCE_BRANCH and run.get('head_sha') == SOURCE_SHA,
            'producer source differs')
    require(run.get('event') == 'workflow_dispatch' and run.get('status') == 'completed'
            and run.get('conclusion') == 'success', 'producer execution differs')
    require(run.get('repository', {}).get('full_name') == REPOSITORY
            and run.get('head_repository', {}).get('full_name') == REPOSITORY,
            'producer repository differs')


def validate_artifact_metadata(artifact):
    require(artifact.get('id') == ARTIFACT_ID and artifact.get('name') == ARTIFACT_NAME,
            'producer artifact identity differs')
    require(artifact.get('expired') is False and artifact.get('size_in_bytes') == ARTIFACT_BYTES,
            'producer artifact availability or size differs')
    require(artifact.get('digest') == 'sha256:' + ARTIFACT_SHA256,
            'producer artifact digest differs')
    workflow = artifact.get('workflow_run', {})
    require(workflow.get('id') == RUN_ID and workflow.get('head_sha') == SOURCE_SHA
            and workflow.get('head_branch') == SOURCE_BRANCH,
            'producer artifact source differs')


def strict_receipt(raw):
    require(0 < len(raw) <= 32_768 and raw.endswith(b'\n'), 'receipt size or framing differs')
    text = raw.decode('utf-8', errors='strict')
    require('\x00' not in text and len(text.splitlines()) <= 500
            and not any(ord(char) < 32 and char not in '\n\r\t' for char in text),
            'receipt text is not bounded UTF-8')
    receipt = json.loads(text, object_pairs_hook=unique)
    require(type(receipt) is dict and set(receipt) == TOP_LEVEL, 'receipt fields differ')
    require(receipt['schema'] == 'arctic-producer-performance-receipt-v1'
            and receipt['repository'] == REPOSITORY and receipt['workflow'] == WORKFLOW_PATH
            and receipt['event'] == 'workflow_dispatch' and receipt['source_sha'] == SOURCE_SHA,
            'receipt provenance differs')
    require(type(receipt['run_id']) is int and receipt['run_id'] == RUN_ID
            and type(receipt['run_attempt']) is int and receipt['run_attempt'] == RUN_ATTEMPT,
            'receipt execution differs')
    require(receipt['mode'] == 'frozen-external-paired-v1'
            and receipt['release_acceptance'] is False, 'receipt mode differs')
    inputs = receipt['inputs']
    require(type(inputs) is dict and set(inputs) == set(INPUTS), 'receipt inputs differ')
    require(all(type(inputs[key]) is type(value) and inputs[key] == value
                for key, value in INPUTS.items()), 'receipt input value differs')

    image = receipt['image']
    require(type(image) is dict and set(image) == {'name', 'bytes', 'sha256'},
            'receipt image fields differ')
    require(image['name'] == IMAGE_NAME and type(image['bytes']) is int
            and 0 < image['bytes'] < 2_000_000_000
            and type(image['sha256']) is str and HEX64.fullmatch(image['sha256']),
            'receipt image identity differs')

    startup = receipt['startup_results']
    require(type(startup) is dict and set(startup) == set(LANES),
            'receipt startup lanes differ')
    for lane, (firmware, mode) in LANES.items():
        result = startup[lane]
        require(type(result) is dict and set(result) == {
            'firmware', 'mode', 'status', 'serial_bytes', 'serial_sha256'},
            f'receipt startup fields differ: {lane}')
        require(result['firmware'] == firmware and result['mode'] == mode
                and result['status'] == 'passed' and type(result['serial_bytes']) is int
                and 0 < result['serial_bytes'] <= 10_000_000
                and type(result['serial_sha256']) is str
                and HEX64.fullmatch(result['serial_sha256']),
                f'receipt startup result differs: {lane}')
    canonical = (json.dumps(receipt, sort_keys=True, indent=2) + '\n').encode()
    require(raw == canonical, 'receipt encoding differs from producer contract')
    return receipt


def validate_archive(raw_archive):
    require(len(raw_archive) == ARTIFACT_BYTES
            and hashlib.sha256(raw_archive).hexdigest() == ARTIFACT_SHA256,
            'downloaded artifact bytes differ')
    with zipfile.ZipFile(BytesIO(raw_archive)) as archive:
        require(archive.comment == b'' and archive.testzip() is None, 'artifact ZIP differs')
        members = archive.infolist()
        require(len(members) == 1 and members[0].filename == RECEIPT_MEMBER,
                'artifact member inventory differs')
        item = members[0]
        path = PurePosixPath(item.filename)
        kind = stat.S_IFMT(item.external_attr >> 16)
        require(not path.is_absolute() and list(path.parts) == [RECEIPT_MEMBER]
                and '\\' not in item.filename and '\x00' not in item.filename
                and not item.is_dir() and kind in (0, stat.S_IFREG)
                and not item.flag_bits & 0x1 and 0 < item.file_size <= 32_768,
                'artifact member is unsafe')
        receipt_raw = archive.read(item)
    return strict_receipt(receipt_raw), receipt_raw


def public_projection(receipt, receipt_raw):
    return {
        'artifact': {
            'id': ARTIFACT_ID,
            'name': ARTIFACT_NAME,
            'bytes': ARTIFACT_BYTES,
            'sha256': ARTIFACT_SHA256,
        },
        'receipt_sha256': hashlib.sha256(receipt_raw).hexdigest(),
        'receipt': receipt,
    }


def main():
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY,
            'reader repository differs')
    run = api(f'actions/runs/{RUN_ID}')
    artifact = api(f'actions/artifacts/{ARTIFACT_ID}')
    validate_run(run)
    validate_artifact_metadata(artifact)
    download = subprocess.run(
        ['gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{ARTIFACT_ID}/zip'],
        stdout=subprocess.PIPE, check=True, timeout=60)
    receipt, receipt_raw = validate_archive(download.stdout)
    projection = public_projection(receipt, receipt_raw)
    encoded = json.dumps(projection, sort_keys=True, separators=(',', ':'))
    require(len(encoded.encode()) <= 4096 and '\n' not in encoded,
            'public receipt projection is unbounded')
    print('ARCTIC-EXTERNAL-PRODUCER-RECEIPT ' + encoded)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('ARCTIC-EXTERNAL-PRODUCER-RECEIPT-REJECTED ' + type(error).__name__,
              file=sys.stderr)
        raise SystemExit(1)
