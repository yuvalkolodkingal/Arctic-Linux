#!/usr/bin/env python3
"""Guard one explicitly reviewed same-image Nix and signed offline-update run."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
FILES = {
    '.github/workflows/image-update-20261008.yml', 'tools/image-update/guard.py',
    'tools/image-update/verify-records.py', 'tools/native-functional/fetch-image.py',
    'tools/native-functional/screen-evidence.py', 'tools/test-install.sh',
    'tools/lib/container.sh', 'tools/lib/vmtest.py',
    'tools/performance/prepare-vm-tools.sh', 'tools/performance/offline-update-boot.py',
    'tools/performance/compose-nix-probe.py', 'tools/performance/guest.py',
    'tools/nix-acceptance/guest.py',
}


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True, timeout=30).strip()


def key_fingerprints(payload):
    """Return the full fingerprints in one bounded OpenPGP public-key payload."""
    require(type(payload) is bytes and 0 < len(payload) <= 65536, 'Invalid signing-key payload')
    with tempfile.TemporaryDirectory(prefix='arctic-update-key-') as folder:
        key = Path(folder) / 'RPM-GPG-KEY-arctic'
        key.write_bytes(payload)
        result = subprocess.run(
            ['gpg', '--batch', '--homedir', folder, '--with-colons',
             '--import-options', 'show-only', '--import', str(key)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30, check=False)
    require(result.returncode == 0, 'Cannot inspect Arctic signing key')
    return [line.split(':')[9].upper() for line in result.stdout.splitlines()
            if line.startswith('fpr:')]


def verify(manifest, source, inputs=None):
    require(manifest.get('ready') is True and manifest.get('release_acceptance') is False,
            'Update qualification is disabled until image and stable source are pinned and reviewed')
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == 'refs/heads/codex/image-update-20261010'
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_WORKFLOW') == 'Same-image Nix and signed update qualification'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Requires this owned GitHub-hosted first attempt')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    reviewed = (ROOT / '.github/qualification-20261010.update').read_text().strip()
    require(re.fullmatch('[0-9a-f]{40}', reviewed)
            and git(ROOT, 'rev-parse', 'HEAD') == os.environ['GITHUB_SHA'] == event['after']
            and git(ROOT, 'rev-parse', 'HEAD^') == reviewed == event['before']
            and git(ROOT, 'diff', '--name-only', reviewed, 'HEAD').splitlines()
                == ['.github/qualification-20261010.update'], 'Activation must change only its reviewed marker')
    require(not git(ROOT, 'status', '--porcelain') and not git(source, 'status', '--porcelain'),
            'Both tracked execution and image source must be clean')
    image, stable = manifest['image'], manifest['stable']
    require(re.fullmatch('[0-9a-f]{40}', image['source_sha'])
            and git(source, 'rev-parse', 'HEAD') == image['source_sha'], 'Image checkout source differs')
    require(set(manifest['execution_files']) == FILES, 'Execution file inventory differs')
    for name, expected in manifest['execution_files'].items():
        path = ROOT / name
        require(re.fullmatch('[0-9a-f]{64}', expected) and path.is_file()
                and not path.is_symlink() and sha(path) == expected, 'Execution source bytes differ: ' + name)
    require(set(stable) == {'run_id', 'source_sha', 'gpg_fingerprint',
                            'release_suffix', 'live_manifest_sha256'}
            and type(stable['run_id']) is int and stable['run_id'] > 0
            and re.fullmatch('[0-9a-f]{40}', stable['source_sha'])
            and re.fullmatch('[0-9A-F]{40}', stable['gpg_fingerprint'])
            and re.fullmatch(r'\.[0-9]{14}\.[0-9]{12}\.git[0-9a-f]{7}',
                             stable['release_suffix'])
            and re.fullmatch('[0-9a-f]{64}', stable['live_manifest_sha256']),
            'Invalid stable identity')
    fingerprint = stable['gpg_fingerprint']
    source_key = source / 'packaging/release/RPM-GPG-KEY-arctic'
    require(source_key.is_file() and not source_key.is_symlink()
            and key_fingerprints(source_key.read_bytes())[:1] == [fingerprint],
            'Candidate source does not pin the expected Arctic signing key')
    spec = importlib.util.spec_from_file_location('image_update_fetch', ROOT / 'tools/native-functional/fetch-image.py')
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    run = fetch.api('/actions/runs/' + str(stable['run_id']))
    require(run['head_sha'] == stable['source_sha'] and run['head_branch'] == 'main'
            and run['event'] == 'push' and run['path'] == '.github/workflows/repo.yml'
            and run['run_attempt'] == 1 and run['status'] == 'completed' and run['conclusion'] == 'success',
            'Canonical stable repository build and deployment did not pass')
    url = 'https://yuvalkolodkingal.github.io/Arctic-Linux/repo/stable/fedora-44/PUBLISH-INFO.json'
    with urllib.request.urlopen(url, timeout=30) as response:
        published = response.read(65537)
    require(len(published) <= 65536, 'Oversized stable metadata')
    published = json.loads(published)
    packages = published.get('packages')
    require(published['channel'] == 'stable' and published['git_commit'] == stable['source_sha']
            and published['run'] == 'https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/' + str(stable['run_id']),
            'Actual public stable channel no longer matches the pinned optimized source')
    require(published.get('release_suffix') == stable['release_suffix']
            and type(packages) is list and packages
            and all(type(name) is str and stable['release_suffix'] in name for name in packages),
            'Actual public stable package generation differs')
    manifest_url = 'https://yuvalkolodkingal.github.io/Arctic-Linux/manifest.json'
    with urllib.request.urlopen(manifest_url, timeout=30) as response:
        live_manifest = response.read(10_000_001)
    require(0 < len(live_manifest) <= 10_000_000
            and hashlib.sha256(live_manifest).hexdigest() == stable['live_manifest_sha256'],
            'Actual public repository manifest differs')
    key_url = 'https://yuvalkolodkingal.github.io/Arctic-Linux/RPM-GPG-KEY-arctic'
    with urllib.request.urlopen(key_url, timeout=30) as response:
        public_key = response.read(65537)
    require(key_fingerprints(public_key)[:1] == [fingerprint],
            'Published Arctic signing key fingerprint differs')
    if inputs is not None:
        iso = inputs / 'iso' / image['name']
        require(iso.is_file() and not iso.is_symlink() and 0 < iso.stat().st_size < 2_000_000_000
                and iso.stat().st_size == image['bytes'] and sha(iso) == image['sha256'],
                'Actual same-image ISO bytes differ')
    return dict(image=image, stable=stable, published=published,
                live_manifest_sha256=stable['live_manifest_sha256'], release_acceptance=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--inputs', type=Path)
    parser.add_argument('--proof', type=Path, required=True)
    args = parser.parse_args()
    proof = verify(json.loads(args.manifest.read_text()), args.source.resolve(),
                   args.inputs.resolve() if args.inputs else None)
    args.proof.parent.mkdir(parents=True, exist_ok=True)
    args.proof.write_text(json.dumps(proof, indent=2) + '\n')


if __name__ == '__main__':
    main()
