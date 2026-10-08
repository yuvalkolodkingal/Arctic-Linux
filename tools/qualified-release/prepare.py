#!/usr/bin/env python3
"""Prepare exact qualified ISO assets; all GitHub calls here are read-only."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPO = 'repos/yuvalkolodkingal/Arctic-Linux'
FILES = {'.github/workflows/publish-qualified-20261008.yml', 'tools/qualified-release/prepare.py',
         'tools/native-functional/fetch-image.py'}
BUILD_INPUTS = {'tools/build-rpms.sh', 'tools/build-iso.sh', 'tools/lib/container.sh', 'tools/lib/arcticrepo.py'}
NATIVE_GATES = set('fresh-defaults-and-isolation archive-content-roundtrips actual-role-file-manager-terminal-editor '
                   'open-codec-content-and-player-state portal-and-accessibility-reachability '
                   'owned-process-cleanup-config-preservation selinux-and-new-avcs open-codec-lossless-command-decode'.split())


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', REPO + path], timeout=60))


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=120).strip()


def product_changes(names):
    # Unknown roots are product changes too: a new vendor/go.sum/runtime asset
    # cannot silently evade the rebuild gate. Only helper/docs paths are exempt.
    return [name for name in names if name in BUILD_INPUTS or
            not (name == 'README.md' or name.startswith(('docs/', '.github/', 'tools/')))]


def main_checks(source):
    runs = api('/actions/runs?head_sha=' + source + '&event=push&per_page=100')['workflow_runs']
    result = {}
    for name, path in (('ci', '.github/workflows/ci.yml'), ('stable', '.github/workflows/repo.yml')):
        matches = [run for run in runs if run['head_sha'] == source and run['head_branch'] == 'main'
                   and run['event'] == 'push' and run['path'] == path and run['run_attempt'] == 1]
        require(len(matches) == 1 and matches[0]['status'] == 'completed' and matches[0]['conclusion'] == 'success',
                'Current main source checks or stable repository deployment have not passed: ' + name)
        result[name] = matches[0]['id']
    jobs = api('/actions/runs/' + str(result['ci']) + '/jobs?per_page=100')
    require(jobs['total_count'] == len(jobs['jobs']) and len(jobs['jobs']) >= 15
            and all(job['status'] == 'completed' and job['conclusion'] == 'success' for job in jobs['jobs']),
            'Current main required source/native checks are incomplete')
    return result


def validate_lane(pin, workflow, artifact_name):
    require(type(pin['run_id']) is int and pin['run_id'] > 0
            and re.fullmatch('[0-9a-f]{40}', pin['source_sha']), 'Invalid qualification run/source')
    run = api('/actions/runs/' + str(pin['run_id']))
    require(run['head_sha'] == pin['source_sha'] and run['path'] == workflow
            and run['event'] == 'push' and run['run_attempt'] == 1
            and run['status'] == 'completed' and run['conclusion'] == 'success',
            'Pinned native/update lane did not complete successfully')
    return validate_artifact(pin, artifact_name)


def validate_artifact(pin, name):
    require(type(pin['artifact_id']) is int and pin['artifact_id'] > 0
            and type(pin['archive_bytes']) is int and 0 < pin['archive_bytes'] <= 550_000_000
            and re.fullmatch('[0-9a-f]{64}', pin['archive_sha256']), 'Invalid diagnostic artifact bounds')
    artifact = api('/actions/artifacts/' + str(pin['artifact_id']))
    require(artifact['workflow_run']['id'] == pin['run_id'] and artifact['workflow_run']['head_sha'] == pin['source_sha']
            and artifact['name'] == name and artifact['expired'] is False
            and artifact['size_in_bytes'] == pin['archive_bytes']
            and artifact['digest'] == 'sha256:' + pin['archive_sha256'], 'Qualification artifact identity differs')
    return artifact


def archive(pin, target):
    with target.open('xb') as output:
        subprocess.run(['gh', 'api', REPO + '/actions/artifacts/' + str(pin['artifact_id']) + '/zip'],
                       stdout=output, check=True, timeout=15 * 60)
    require(target.stat().st_size == pin['archive_bytes'] and sha(target) == pin['archive_sha256'],
            'Actual qualification archive bytes differ')
    result = zipfile.ZipFile(target)
    entries = result.infolist()
    require(len(entries) <= 1000 and sum(entry.file_size for entry in entries) <= 550_000_000
            and len({entry.filename for entry in entries}) == len(entries), 'Unbounded/duplicate diagnostic archive')
    for entry in entries:
        path = Path(entry.filename)
        require(not path.is_absolute() and '..' not in path.parts
                and (entry.external_attr >> 16 & 0o170000) in (0, 0o100000, 0o040000), 'Unsafe diagnostic member')
    return result


def read_json(archive, name):
    require(archive.getinfo(name).file_size <= 4_000_000, 'Oversized qualification JSON')
    return json.loads(archive.read(name))


def native_proof(archive, manifest):
    state = read_json(archive, 'execution.json')
    image, pin = manifest['image'], manifest['native']
    require(state['status'] == 'limited_native_live_installed_smoke_passed_pending_visual_audio_review'
            and state['iso_sha256'] == image['sha256'] and state['iso_bytes'] == image['bytes']
            and state['candidate_iso_source'] == image['source_sha'] and state['source_image_run'] == image['run_id']
            and state['execution_checker_head'] == pin['source_sha'], 'Native report does not qualify this image')
    required_images = {}
    for stage in ('live', 'installed'):
        report = read_json(archive, 'native-' + stage + '/report.json')
        require(report['stage'] == stage and report['status'] == 'limited-smoke-passed'
                and len(report['gates']) == len(NATIVE_GATES)
                and {gate['check'] for gate in report['gates']} == NATIVE_GATES
                and all(gate['status'] == 'passed' for gate in report['gates']), 'Native functional gate failed/missing')
        values = {gate['check']: gate['value'] for gate in report['gates']}
        shots = values['actual-role-file-manager-terminal-editor']['screenshots']
        media = values['open-codec-content-and-player-state']
        shots = shots + [media['screenshot'], media['visual_reference']['screenshot']]
        require(len(shots) == 4, 'Required native visual evidence differs')
        for shot in shots:
            relative = Path(shot['path']).relative_to(Path(report['evidence_root']))
            name = 'native-' + stage + '/' + relative.as_posix()
            require(archive.getinfo(name).file_size < 4_000_000
                    and hashlib.sha256(archive.read(name)).hexdigest() == shot['sha256'], 'Native screenshot hash differs')
            required_images[name] = shot['sha256']
        require(state['photos'][stage]['status'] == 'passed', 'Actual image photo verification did not pass')
    review = manifest['media_review']
    require(review['image_sha256'] == image['sha256'] and review['native_archive_sha256'] == pin['archive_sha256']
            and review['visual_status'] == 'passed' and review['audio_status'] == 'passed'
            and review['images'] == required_images, 'Exact native image/audio review is absent')
    required_audio = {}
    for stage in ('install', 'boot'):
        info = state['audio'][stage]
        require(info['nonzero_blocks'] > 0 and info['frames'] > 0, 'Actual virtual audio is silent/missing')
        files = ([dict(path=info['source_name'], sha256=info['source_sha256'])] if info['preserved_full']
                 else info['excerpts'])
        for item in files:
            name = 'virtual-audio/' + item['path']
            require(archive.getinfo(name).file_size <= 32 * 1024 * 1024
                    and hashlib.sha256(archive.read(name)).hexdigest() == item['sha256'], 'Reviewed audio bytes differ')
            required_audio[name] = item['sha256']
    require(review['audio'] == required_audio and bool(required_audio), 'Exact audio review inventory differs')
    return dict(run_id=pin['run_id'], source_sha=pin['source_sha'], artifact_sha256=pin['archive_sha256'],
                native_gates='all eight passed in live and encrypted offline installed phases',
                media_review=review, photos='passed in live and installed phases')


def prepare(manifest, out):
    require(manifest.get('ready') is True and manifest.get('publication_approved') is True
            and manifest.get('release_acceptance') is False, 'Publication disabled until exact qualification is reviewed')
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == 'refs/heads/codex/publish-qualified-20261008'
            and os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
            'Requires the reviewed owned publication lane')
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    parent = (ROOT / '.github/qualification-20261008.publish').read_text().strip()
    require(re.fullmatch('[0-9a-f]{40}', parent) and event['before'] == parent == git('rev-parse', 'HEAD^')
            and event['after'] == os.environ['GITHUB_SHA'] == git('rev-parse', 'HEAD')
            and git('diff', '--name-only', parent, 'HEAD').splitlines() == ['.github/qualification-20261008.publish']
            and not git('status', '--porcelain'), 'Publication activation/source differs')
    require(set(manifest['execution_files']) == FILES, 'Publication execution inventory differs')
    for name, expected in manifest['execution_files'].items():
        require(re.fullmatch('[0-9a-f]{64}', expected) and not (ROOT / name).is_symlink()
                and sha(ROOT / name) == expected, 'Publication source bytes differ: ' + name)
    require(manifest['tag'] == 'v1.2.1' and re.fullmatch('[0-9a-f]{40}', manifest['main_sha']), 'Invalid release identity')
    release_main = api('/git/ref/heads/main')['object']['sha']
    require(re.fullmatch('[0-9a-f]{40}', release_main), 'Invalid current main source')
    require(not api('/pulls?state=open&per_page=100'), 'Arctic PRs remain open')
    current_checks = main_checks(release_main)
    for ref in (manifest['image']['source_sha'], manifest['main_sha'], release_main):
        subprocess.run(['git', '-C', str(ROOT), 'fetch', '--filter=blob:none', 'origin', ref], check=True, timeout=120)
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', manifest['main_sha'], release_main], check=True)
    require(not product_changes(git('diff', '--name-only', manifest['image']['source_sha'], release_main).splitlines()),
            'Product changed after the qualified ISO was built; rebuild required')
    spec = importlib.util.spec_from_file_location('qualified_fetch', ROOT / 'tools/native-functional/fetch-image.py')
    fetch = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fetch)
    image = manifest['image']
    run = fetch.api('/actions/runs/' + str(image['run_id']))
    fetch.validate(image, run, fetch.api('/actions/artifacts/' + str(image['artifact_id'])))
    jobs = fetch.api('/actions/runs/' + str(image['run_id']) + '/jobs?filter=all&per_page=100')
    require(jobs['total_count'] == len(jobs['jobs']), 'Incomplete build-job inventory')
    fetch.validate_boot_steps(image, jobs['jobs'])
    steps = [step for job in jobs['jobs'] if job['name'] == 'iso'
             for step in job['steps'] if step['name'] == 'Paired KVM performance acceptance']
    require(len(steps) == 1 and steps[0]['conclusion'] == 'success', 'Actual paired same-image measurements did not pass')
    perf = manifest['performance']
    require(perf['run_id'] == image['run_id'] and perf['source_sha'] == image['source_sha'], 'Performance image/run differs')
    validate_artifact(perf, 'paired-performance')
    validate_lane(manifest['native'], '.github/workflows/native-candidate-20261008.yml', 'native-candidate-qualification')
    validate_lane(manifest['update'], '.github/workflows/image-update-20261008.yml', 'same-image-nix-signed-update')
    require(not out.exists(), 'Prepared release assets must be unused')
    with tempfile.TemporaryDirectory(prefix='arctic-qualified-') as temp:
        temp = Path(temp)
        with archive(perf, temp / 'performance.zip') as evidence:
            state, comparison = read_json(evidence, 'status.json'), read_json(evidence, 'comparison.json')
            require(state['phase'] == 'complete_regression_gate_passed' and state['acceleration'] == 'kvm'
                    and state['memory_mib'] == 4096 and state['vcpus'] == 2 and state['restricted_network'] is True
                    and state['images']['candidate']['sha256'] == image['sha256']
                    and len(state['runs']) == 6 and all(row['harness_exit'] == 0 for row in state['runs'])
                    and comparison['status'] == 'regression_gate_passed'
                    and comparison['measurement_precision']['valid'] is True
                    and comparison['measurement_precision']['threshold_enclosure_valid'] is True,
                    'Same-image paired precision/regression evidence failed')
        with archive(manifest['native'], temp / 'native.zip') as evidence:
            native = native_proof(evidence, manifest)
        with archive(manifest['update'], temp / 'update.zip') as evidence:
            update = read_json(evidence, 'update-result.json')
            pins = read_json(evidence, 'pre-final-boot.json')
            require(update['status'] == 'same_image_nix_signed_offline_update_reboot_passed'
                    and pins['image'] == image and pins['stable']['source_sha'] == manifest['main_sha']
                    and update['release_acceptance'] is False, 'Same-image optimized signed update/reboot evidence differs')
        fetch_manifest = temp / 'image.json'
        fetch_manifest.write_text(json.dumps(dict(ready=True, release_acceptance=False, image=image)))
        subprocess.run(['python3', '-B', str(ROOT / 'tools/native-functional/fetch-image.py'),
                        '--manifest', str(fetch_manifest), '--out', str(temp / 'inputs')], check=True, timeout=20 * 60)
        out.mkdir()
        name = 'Arctic-Linux-1.2.1-x86_64.iso'
        shutil.copyfile(temp / 'inputs/iso' / image['name'], out / name)
        require((out / name).stat().st_size == image['bytes'] and sha(out / name) == image['sha256'], 'Prepared ISO bytes differ')
        (out / (name + '.sha256')).write_text(image['sha256'] + '  ' + name + '\n')
        proof = dict(tag=manifest['tag'], main_sha=manifest['main_sha'], release_main_sha=release_main,
                     release_main_checks=current_checks, image=image,
                     performance=perf, native=native, update=manifest['update'], release_acceptance='qualified',
                     measured_speed_or_ram_gain_claim=False)
        (out / 'qualification.json').write_text(json.dumps(proof, indent=2) + '\n')
        (out / 'release-notes.md').write_text(
            'Arctic Linux 1.2.1 for x86_64, with UEFI and BIOS boot.\n\n'
            'Lightweight defaults: GNOME Web, Foot, GTK3 PCManFM, XArchiver, Celluloid, FeatherPad, Nano and Fish/Bash. '
            'Includes the covered/fractional screen-frame fix and 18 approved photo wallpapers, with City Afterglow as the fresh default.\n\n'
            'The exact retained ISO passed Try/Install/Safe startup, enforcing encrypted offline installation, native app/media checks, '
            'paired KVM precision/regression checks and a signed optimized stable Arctic update with offline apply and subsequent reboot. '
            'These checks make no physical hardware, substantial speed or RAM improvement claim.\n\n'
            f"ISO bytes: {image['bytes']}. SHA-256: `{image['sha256']}`.\n\n"
            'Download the ISO and checksum, then run `sha256sum -c Arctic-Linux-1.2.1-x86_64.iso.sha256`. '
            'Write the ISO using Fedora Media Writer and boot the USB drive. '
            'Updates use the signed stable Arctic and Fedora repositories. See qualification.json for exact source, artifact and check identities.\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    prepare(json.loads(args.manifest.read_text()), args.out)


if __name__ == '__main__':
    main()
