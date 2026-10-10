#!/usr/bin/env python3
"""Download a reviewed, retained Arctic ISO artifact; never build or publish."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import zipfile

REPO = 'repos/yuvalkolodkingal/Arctic-Linux'
# In the pinned iso.yml this one fail-closed step runs Try, Install and Safe
# sequentially. A skipped step cannot satisfy the three startup prerequisites.
BOOT_STEPS = ('Boot test in QEMU (UEFI, Try mode)',)
PAIRED_STEP = 'Paired KVM performance acceptance'
LEGACY_MODE = 'in-producer-paired-v1'
EXTERNAL_MODE = 'frozen-external-paired-v1'
RECEIPT_NAME = 'PERFORMANCE-PLAN.json'
RECEIPT_STEP = 'Write external performance producer receipt'
EXTERNAL_UPLOAD_STEP = 'Upload external-mode ISO and producer receipt (workflow artifact)'
SIZE_STEP = 'Required optimized ISO size'
STARTUP_LANES = {'uefi-try': ('uefi', 'try'), 'bios-install': ('bios', 'install'),
                 'uefi-safe': ('uefi', 'safe')}
INPUT_TYPES = {'expected_source_sha': str, 'release': bool, 'tag': str,
               'prerelease': bool, 'draft': bool, 'nix_acceptance': bool,
               'performance_acceptance': bool, 'boot_test': bool, 'performance_mode': str}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', REPO + path], timeout=60))


def producer_mode(image):
    mode = image.get('producer_mode', LEGACY_MODE)
    require(type(mode) is str and mode in (LEGACY_MODE, EXTERNAL_MODE), 'Unknown producer mode')
    if mode == EXTERNAL_MODE:
        require(type(image.get('producer_receipt_sha256')) is str
                and re.fullmatch('[0-9a-f]{64}', image['producer_receipt_sha256']),
                'External producer receipt must be explicitly pinned')
    else:
        require('producer_receipt_sha256' not in image, 'Legacy producer cannot use an external receipt')
    return mode


def validate_external_inputs(inputs, source_sha):
    require(isinstance(inputs, dict) and set(inputs) == set(INPUT_TYPES)
            and all(type(inputs[key]) is kind for key, kind in INPUT_TYPES.items()),
            'External producer dispatch input fields or types differ')
    require(type(source_sha) is str and re.fullmatch('[0-9a-f]{40}', source_sha)
            and inputs['expected_source_sha'] == source_sha
            and inputs['release'] is False and inputs['boot_test'] is True
            and inputs['performance_acceptance'] is False
            and inputs['performance_mode'] == EXTERNAL_MODE,
            'External producer dispatch is not explicit artifact-only startup qualification')
    require(len(inputs['tag']) <= 200 and not any(ord(char) < 32 or ord(char) == 127 for char in inputs['tag']),
            'Invalid producer release tag input')
    return inputs


def validate_external_receipt(receipt, image):
    """Typed provenance only; this does not qualify an image or a performance run."""
    require(producer_mode(image) == EXTERNAL_MODE, 'Receipt requires explicitly pinned external mode')
    fields = {'schema', 'repository', 'workflow', 'event', 'source_sha', 'run_id',
              'run_attempt', 'mode', 'release_acceptance', 'inputs', 'image', 'startup_results'}
    require(isinstance(receipt, dict) and set(receipt) == fields, 'Producer receipt fields differ')
    require(receipt['schema'] == 'arctic-producer-performance-receipt-v1'
            and receipt['repository'] == 'yuvalkolodkingal/Arctic-Linux'
            and receipt['workflow'] == '.github/workflows/iso.yml'
            and receipt['event'] == 'workflow_dispatch' and receipt['mode'] == EXTERNAL_MODE
            and receipt['release_acceptance'] is False,
            'Producer receipt workflow, mode or scope differs')
    require(type(receipt['run_id']) is int and receipt['run_id'] > 0
            and receipt['run_id'] == image['run_id'] and receipt['source_sha'] == image['source_sha']
            and type(receipt['run_attempt']) is int and receipt['run_attempt'] == 1,
            'Producer receipt source, run or first attempt differs')
    validate_external_inputs(receipt['inputs'], image['source_sha'])
    expected = {key: image[key] for key in ('name', 'bytes', 'sha256')}
    require(isinstance(receipt['image'], dict) and set(receipt['image']) == set(expected)
            and all(type(receipt['image'][key]) is type(value) and receipt['image'][key] == value
                    for key, value in expected.items())
            and type(image['bytes']) is int and 0 < image['bytes'] < 2_000_000_000
            and re.fullmatch('[0-9a-f]{64}', image['sha256'])
            and image['name'] == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso",
            'Producer receipt actual ISO identity differs')
    require(isinstance(receipt['startup_results'], dict)
            and set(receipt['startup_results']) == set(STARTUP_LANES), 'Producer startup inventory differs')
    for name, (firmware, mode) in STARTUP_LANES.items():
        result = receipt['startup_results'][name]
        require(isinstance(result, dict) and set(result) ==
                {'firmware', 'mode', 'status', 'serial_bytes', 'serial_sha256'}
                and result['firmware'] == firmware and result['mode'] == mode
                and result['status'] == 'passed' and type(result['serial_bytes']) is int
                and 0 < result['serial_bytes'] <= 10_000_000
                and type(result['serial_sha256']) is str
                and re.fullmatch('[0-9a-f]{64}', result['serial_sha256']),
                'Producer startup receipt is missing, malformed or unsuccessful: ' + name)
    return receipt


def read_receipt(raw, image):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 32_768
            and hashlib.sha256(raw).hexdigest() == image['producer_receipt_sha256'],
            'Actual producer receipt bytes differ')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate producer receipt JSON field')
            result[key] = value
        return result
    return validate_external_receipt(json.loads(raw, object_pairs_hook=unique), image)


def validate(image, run, artifact):
    producer_mode(image)
    require(type(image['run_id']) is int and image['run_id'] > 0
            and type(image['artifact_id']) is int and image['artifact_id'] > 0,
            'Invalid artifact identities')
    require(run['id'] == image['run_id'] and run['head_sha'] == image['source_sha']
            and run['event'] == 'workflow_dispatch' and run['path'] == '.github/workflows/iso.yml'
            and run['status'] == 'completed' and run['conclusion'] == 'success'
            and type(run.get('run_attempt')) is int and run['run_attempt'] == 1,
            'Image build and required boot lanes have not passed at the pinned source')
    require(artifact['id'] == image['artifact_id'] and artifact['name'] == 'arctic-linux-iso'
            and artifact['expired'] is False and artifact['workflow_run']['id'] == image['run_id']
            and artifact['workflow_run']['head_sha'] == image['source_sha']
            and artifact['digest'] == 'sha256:' + image['archive_sha256']
            and artifact['size_in_bytes'] == image['archive_bytes'], 'Retained artifact identity differs')
    require(re.fullmatch('[0-9a-f]{40}', image['source_sha'])
            and re.fullmatch('[0-9a-f]{64}', image['sha256'])
            and re.fullmatch('[0-9a-f]{64}', image['archive_sha256'])
            and image['name'] == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso"
            and type(image['bytes']) is int and 0 < image['bytes'] < 2_000_000_000,
            'Invalid pinned ISO identity or size')


def extract(archive_path, target, image):
    require(not target.exists(), 'Inputs must be unused')
    with zipfile.ZipFile(archive_path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        require(len(entries) <= 20 and len(names) == len(set(names)), 'Unexpected or duplicate members')
        require(sum(entry.file_size for entry in entries) < 2_010_000_000, 'Oversized image archive')
        wanted = 'iso/' + image['name']
        require(wanted in names and wanted + '.sha256' in names and 'BUILD-INFO' in names,
                'Required image and checksum metadata are missing')
        external = producer_mode(image) == EXTERNAL_MODE
        require((RECEIPT_NAME in names) == external, 'Producer receipt and explicitly pinned mode differ')
        for entry in entries:
            path = Path(entry.filename)
            require(not path.is_absolute() and '..' not in path.parts and not entry.is_dir()
                    and (entry.external_attr >> 16 & 0o170000) in (0, 0o100000)
                    and (entry.filename == 'BUILD-INFO' or (external and entry.filename == RECEIPT_NAME) or
                         (len(path.parts) == 2 and path.parts[0] == 'iso' and
                          (entry.filename == wanted or path.suffix in
                           ('.sha256', '.packages', '.build-info', '.tsv', '.txt')))), 'Unsafe artifact member')
            if entry.filename != wanted:
                require(entry.file_size < 5_000_000, 'Oversized metadata')
            if entry.filename == RECEIPT_NAME:
                require(0 < entry.file_size <= 32_768, 'Oversized producer receipt member')
        require(archive.read(wanted + '.sha256').decode().strip().split() ==
                [image['sha256'], image['name']], 'Image checksum metadata differs')
        build = archive.read('BUILD-INFO').decode().splitlines()
        require([line for line in build if line.startswith('git_commit=')] ==
                ['git_commit=' + image['source_sha']], 'Package source metadata differs')
        require('arctic_repos=enabled' in build, 'Canonical signed Arctic updates are unavailable')
        if external:
            read_receipt(archive.read(RECEIPT_NAME), image)
        target.mkdir(parents=True)
        for entry in entries:
            output = target / entry.filename
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry) as source, output.open('xb') as destination:
                for block in iter(lambda: source.read(1024 * 1024), b''):
                    destination.write(block)
        path = target / wanted
        require(path.stat().st_size == image['bytes'] and digest(path) == image['sha256'],
                'Actual unsplit ISO bytes or SHA256 differ')


def producer_job(image, jobs):
    matches = [job for job in jobs if job['name'] == 'iso' and type(job['run_attempt']) is int and job['run_attempt'] == 1]
    require(len(matches) == 1 and matches[0]['head_sha'] == image['source_sha']
            and matches[0]['status'] == 'completed' and matches[0]['conclusion'] == 'success',
            'Pinned first-attempt ISO job is absent or failed')
    return matches[0]


def require_step(job, name, conclusion):
    steps = [step for step in job['steps'] if step['name'] == name]
    require(len(steps) == 1 and steps[0]['status'] == 'completed'
            and steps[0]['conclusion'] == conclusion, 'Required producer step differs: ' + name)


def validate_external_producer_steps(image, jobs):
    require(producer_mode(image) == EXTERNAL_MODE, 'External producer step checks require an explicit mode')
    job = producer_job(image, jobs)
    for name in (*BOOT_STEPS, SIZE_STEP, RECEIPT_STEP, EXTERNAL_UPLOAD_STEP):
        require_step(job, name, 'success')
    require_step(job, PAIRED_STEP, 'skipped')
    publish = [job for job in jobs if job['name'] == 'Publish the completed ISO']
    require(len(publish) == 1 and publish[0]['head_sha'] == image['source_sha']
            and type(publish[0]['run_attempt']) is int and publish[0]['run_attempt'] == 1
            and publish[0]['status'] == 'completed' and publish[0]['conclusion'] == 'skipped',
            'External artifact-only producer publication was not skipped')


def validate_boot_steps(image, jobs):
    if producer_mode(image) == EXTERNAL_MODE:
        return validate_external_producer_steps(image, jobs)
    job = producer_job(image, jobs)
    for name in (*BOOT_STEPS, PAIRED_STEP):
        require_step(job, name, 'success')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    require(manifest.get('ready') is True and manifest.get('release_acceptance') is False,
            'Image fetch is disabled until the rebuilt candidate is pinned and reviewed')
    image = manifest['image']
    run = api('/actions/runs/' + str(image['run_id']))
    artifact = api('/actions/artifacts/' + str(image['artifact_id']))
    validate(image, run, artifact)
    require(run['run_attempt'] == 1, 'Image run attempt differs from the pinned candidate')
    page = api('/actions/runs/' + str(image['run_id']) + '/jobs?filter=all&per_page=100')
    require(page['total_count'] == len(page['jobs']), 'Incomplete image-job inventory')
    validate_boot_steps(image, page['jobs'])
    archive = args.out.parent / 'candidate-artifact.zip'
    require(not archive.exists(), 'Download path must be unused')
    try:
        with archive.open('xb') as output:
            # gh follows the approved GitHub artifact redirect without exposing its URL/token.
            subprocess.run(['gh', 'api', REPO + '/actions/artifacts/' + str(image['artifact_id']) + '/zip'],
                           stdout=output, check=True, timeout=15 * 60)
        require(archive.stat().st_size == image['archive_bytes']
                and digest(archive) == image['archive_sha256'], 'Actual artifact archive differs')
        extract(archive, args.out, image)
    finally:
        archive.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
