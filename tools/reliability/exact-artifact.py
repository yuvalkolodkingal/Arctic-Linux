#!/usr/bin/env python3
"""Fail-closed contract for exact-artifact pre-publication install/reboot evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = '.github/workflows/release-reliability-candidate.yml'
MARKER = '.github/qualification-20261010.reliability'
MANIFEST = 'tools/reliability/exact-artifact-manifest.json'
BRANCH = 'codex/qualification-dispatch-20261010'
EXECUTION_FILES = tuple(sorted({
    WORKFLOW,
    'tools/reliability/exact-artifact.py',
    'tools/reliability/report.py',
    'tools/reliability/guest.py',
    'tools/reliability/profiles/lightweight.toml',
    'tools/native-functional/fetch-image.py',
    'tools/test-install.sh',
    'tools/lib/container.sh',
    'tools/lib/vmtest.py',
    'tools/lib/iso_startup.py',
}))
FIRMWARE = ('uefi', 'bios')
SCHEMA = 'arctic-exact-artifact-reliability-v1'
IMAGE_KEYS = {'run_id', 'artifact_id', 'archive_bytes', 'archive_sha256', 'source_sha',
              'name', 'bytes', 'sha256', 'producer_mode', 'producer_receipt_sha256'}
LIVE = {'identity', 'desktop', 'app-terminal', 'app-files', 'app-browser', 'app-editor',
        'app-settings', 'app-media', 'wallpapers'}
INSTALLED = LIVE | {'network'}
AUTOMATED = ({('live', name) for name in LIVE} |
             {('installed', name) for name in INSTALLED} |
             {('install', 'installer-exit'), ('reboot', 'harness-exit')})
UNRUN = {('live', 'network'), ('physical-hardware', 'manual-or-unsupported'),
         ('visual-content-audio-calls', 'manual-or-unsupported'),
         ('fedora-major-upgrade', 'manual-or-unsupported'), ('upgrade', 'previous-release')}
EVIDENCE_FILES = {key: ('serial-install.log' if key[0] in ('live', 'install')
                        else 'serial-boot.log' if key[0] == 'installed' else 'test.log')
                  for key in AUTOMATED}


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
    return json.loads(raw, object_pairs_hook=unique, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=120).strip()


def validate_manifest(value, source_hashes=None):
    require(type(value) is dict and set(value) ==
            {'ready', 'release_acceptance', 'version', 'app_profile', 'image', 'execution_files'},
            'Exact-artifact reliability manifest fields differ')
    require(value['ready'] is True and value['release_acceptance'] is False
            and value['version'] == '1.2' and value['app_profile'] == 'lightweight',
            'Exact-artifact reliability is disabled or its fixed test profile differs')
    image = value['image']
    require(type(image) is dict and set(image) == IMAGE_KEYS
            and type(image['run_id']) is int and image['run_id'] > 0
            and type(image['artifact_id']) is int and image['artifact_id'] > 0
            and type(image['archive_bytes']) is int and 0 < image['archive_bytes'] < 2_010_000_000
            and type(image['bytes']) is int and 0 < image['bytes'] < 2_000_000_000
            and re.fullmatch('[0-9a-f]{40}', image['source_sha'])
            and all(re.fullmatch('[0-9a-f]{64}', image[key]) for key in
                    ('archive_sha256', 'sha256', 'producer_receipt_sha256'))
            and image['producer_mode'] == 'frozen-external-paired-v1'
            and image['name'] == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso",
            'Pinned exact artifact identity is malformed')
    files = value['execution_files']
    require(type(files) is dict and set(files) == set(EXECUTION_FILES)
            and all(type(item) is str and re.fullmatch('[0-9a-f]{64}', item) for item in files.values()),
            'Exact-artifact execution inventory differs')
    if source_hashes is not None:
        require(files == source_hashes, 'Exact-artifact execution source hashes differ')
    return value


def validate_activation(manifest_path):
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
            'Requires the reviewed first-attempt exact-artifact reliability lane')
    event = strict_json(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    marker = (ROOT / MARKER).read_text().strip()
    head = git('rev-parse', 'HEAD')
    require(re.fullmatch('[0-9a-f]{40}', marker) and event.get('before') == marker
            and event.get('after') == os.environ.get('GITHUB_SHA') == head
            and git('rev-list', '--parents', '-n', '1', 'HEAD').split() == [head, marker]
            and git('diff', '--no-renames', '--name-only', marker, 'HEAD').splitlines() == [MARKER]
            and not git('status', '--porcelain'),
            'Reliability activation is not the reviewed marker-only child')
    hashes = {name: digest_file(ROOT / name) for name in EXECUTION_FILES}
    manifest = validate_manifest(strict_json(Path(manifest_path).read_text()), hashes)
    return manifest, marker, head


def write_github_output(path, manifest):
    """Expose only the already validated, filename-safe candidate identity."""
    image = manifest['image']
    name = image['name']
    require(name == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso"
            and Path(name).name == name,
            'Pinned candidate filename is unsafe')
    with Path(path).open('a', encoding='utf-8') as output:
        output.write('candidate_name=' + name + '\n')


def validate_results(value):
    require(type(value) is list and len(value) == len(AUTOMATED) + len(UNRUN),
            'Reliability result inventory differs')
    found = {}
    for row in value:
        require(type(row) is dict and set(row).issubset({'stage', 'check', 'status', 'evidence', 'detail'})
                and {'stage', 'check', 'status'} <= set(row)
                and all(type(row[key]) is str for key in ('stage', 'check', 'status')),
                'Malformed reliability result')
        key = (row['stage'], row['check'])
        require(key not in found, 'Duplicate reliability result: ' + '/'.join(key))
        found[key] = row
    require(set(found) == AUTOMATED | UNRUN, 'Missing or extra reliability result')
    for key in AUTOMATED:
        row = found[key]
        require(row['status'] == 'passed' and row.get('evidence') == EVIDENCE_FILES[key],
                'Required reliability result did not pass: ' + '/'.join(key))
    for key in UNRUN:
        require(found[key]['status'] == 'unrun' and 'evidence' not in found[key],
                'Manual/unsupported reliability scope was misreported: ' + '/'.join(key))
    return value


def collect(manifest_path, results_path, public_results_path, output_path, firmware):
    require(firmware in FIRMWARE, 'Unsupported firmware')
    manifest, parent, head = validate_activation(manifest_path)
    raw = Path(results_path).read_bytes()
    require(0 < len(raw) <= 4_000_000, 'Reliability results are empty or oversized')
    results = validate_results(strict_json(raw.decode()))
    public_results = []
    for key in sorted(AUTOMATED | UNRUN):
        row = {'stage': key[0], 'check': key[1],
               'status': 'passed' if key in AUTOMATED else 'unrun'}
        if key in AUTOMATED:
            row['evidence'] = EVIDENCE_FILES[key]
        public_results.append(row)
    public_raw = (json.dumps(public_results, indent=2, sort_keys=True) + '\n').encode()
    receipt = {
        'schema': SCHEMA,
        'status': 'blank_disk_install_reboot_passed',
        'release_acceptance': False,
        'firmware': firmware,
        'app_profile': manifest['app_profile'],
        'version': manifest['version'],
        'image': manifest['image'],
        'execution_source_sha': head,
        'reviewed_parent_sha': parent,
        'run_id': int(os.environ['GITHUB_RUN_ID']),
        'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
        'vm': {'acceleration': 'kvm', 'memory_mib': 4096, 'vcpus': 2,
               'disk': 'new-blank-sparse-qcow2', 'boot_network': 'online'},
        'results': {'path': 'results.json', 'bytes': len(public_raw), 'sha256': digest_bytes(public_raw),
                    'automated_passed': len(AUTOMATED), 'unrun': len(UNRUN)},
    }
    require(receipt['run_id'] > 0 and receipt['run_attempt'] == 1, 'Invalid workflow execution identity')
    with Path(public_results_path).open('xb') as stream:
        stream.write(public_raw)
    with Path(output_path).open('x') as stream:
        stream.write(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
    return receipt, results


def validate_evidence(execution, results_raw, *, image, firmware, source_sha, run_id):
    require(type(execution) is dict and set(execution) ==
            {'schema', 'status', 'release_acceptance', 'firmware', 'app_profile', 'version', 'image',
             'execution_source_sha', 'reviewed_parent_sha', 'run_id', 'run_attempt', 'vm', 'results'},
            'Reliability execution receipt fields differ')
    require(execution['schema'] == SCHEMA and execution['status'] == 'blank_disk_install_reboot_passed'
            and execution['release_acceptance'] is False and execution['firmware'] == firmware
            and execution['app_profile'] == 'lightweight' and execution['version'] == '1.2'
            and execution['image'] == image and execution['execution_source_sha'] == source_sha
            and execution['run_id'] == run_id and execution['run_attempt'] == 1
            and re.fullmatch('[0-9a-f]{40}', execution['reviewed_parent_sha']),
            'Reliability execution does not qualify the pinned image/run/firmware')
    require(execution['vm'] == {'acceleration': 'kvm', 'memory_mib': 4096, 'vcpus': 2,
                               'disk': 'new-blank-sparse-qcow2', 'boot_network': 'online'},
            'Reliability VM or blank-disk scope differs')
    require(type(results_raw) is bytes and 0 < len(results_raw) <= 4_000_000,
            'Reliability result bytes are empty or oversized')
    result = execution['results']
    require(result == {'path': 'results.json', 'bytes': len(results_raw),
                       'sha256': digest_bytes(results_raw), 'automated_passed': len(AUTOMATED),
                       'unrun': len(UNRUN)}, 'Reliability result receipt differs')
    rows = validate_results(strict_json(results_raw.decode()))
    require(all(set(row) == ({'stage', 'check', 'status', 'evidence'} if (row['stage'], row['check']) in AUTOMATED
                              else {'stage', 'check', 'status'}) for row in rows),
            'Reliability public results contain nonpublic or missing fields')
    return {'firmware': firmware, 'status': execution['status'], 'vm': execution['vm'],
            'automated_passed': len(AUTOMATED), 'unrun': len(UNRUN)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    verify = sub.add_parser('verify')
    verify.add_argument('--manifest', type=Path, required=True)
    verify.add_argument('--github-output', type=Path)
    collect_parser = sub.add_parser('collect')
    collect_parser.add_argument('--manifest', type=Path, required=True)
    collect_parser.add_argument('--results', type=Path, required=True)
    collect_parser.add_argument('--public-results', type=Path, required=True)
    collect_parser.add_argument('--out', type=Path, required=True)
    collect_parser.add_argument('--firmware', choices=FIRMWARE, required=True)
    args = parser.parse_args()
    if args.command == 'verify':
        manifest, _, _ = validate_activation(args.manifest)
        if args.github_output is not None:
            write_github_output(args.github_output, manifest)
        print(manifest['image']['source_sha'])
    else:
        collect(args.manifest, args.results, args.public_results, args.out, args.firmware)


if __name__ == '__main__':
    main()
