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


def validate(image, run, artifact):
    require(type(image['run_id']) is int and image['run_id'] > 0
            and type(image['artifact_id']) is int and image['artifact_id'] > 0,
            'Invalid artifact identities')
    require(run['id'] == image['run_id'] and run['head_sha'] == image['source_sha']
            and run['event'] == 'workflow_dispatch' and run['path'] == '.github/workflows/iso.yml'
            and run['status'] == 'completed' and run['conclusion'] == 'success',
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
        for entry in entries:
            path = Path(entry.filename)
            require(not path.is_absolute() and '..' not in path.parts and not entry.is_dir()
                    and (entry.external_attr >> 16 & 0o170000) in (0, 0o100000)
                    and (entry.filename == 'BUILD-INFO' or
                         (len(path.parts) == 2 and path.parts[0] == 'iso' and
                          (entry.filename == wanted or path.suffix in
                           ('.sha256', '.packages', '.build-info', '.tsv', '.txt')))), 'Unsafe artifact member')
            if entry.filename != wanted:
                require(entry.file_size < 5_000_000, 'Oversized metadata')
        require(archive.read(wanted + '.sha256').decode().strip().split() ==
                [image['sha256'], image['name']], 'Image checksum metadata differs')
        build = archive.read('BUILD-INFO').decode().splitlines()
        require([line for line in build if line.startswith('git_commit=')] ==
                ['git_commit=' + image['source_sha']], 'Package source metadata differs')
        require('arctic_repos=enabled' in build, 'Canonical signed Arctic updates are unavailable')
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
