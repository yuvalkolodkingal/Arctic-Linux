#!/usr/bin/env python3
"""Prepare exact qualified ISO assets; all GitHub calls here are read-only."""
import argparse
from contextlib import ExitStack
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[2]
REPO = 'repos/yuvalkolodkingal/Arctic-Linux'
FILES = {'.github/workflows/publish-qualified-20261008.yml', 'tools/qualified-release/prepare.py',
         'tools/native-functional/fetch-image.py', 'tools/qualified-release/torrent.py',
         'tools/dictation-qualification/contract.py', 'tools/installer-qualification/contract.py',
         'tools/installer-qualification/active-contract.py',
         'tools/native-functional/apps.py'}
BUILD_INPUTS = {'.github/workflows/iso.yml',
                'tools/build-rpms.sh', 'tools/build-iso.sh', 'tools/build-cache.py',
                'tools/lib/container.sh', 'tools/lib/arcticrepo.py'}
DOCUMENTATION = {'README.md', 'iso/kiwi/README.md'}
# arctic-linux.spec excludes shell/dev from the installed shell payload. This
# private compositor fixture has no runtime or image-build invocation.
TEST_ONLY = {'shell/dev/test-lock-clock.py'}
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
            not (name in DOCUMENTATION or name in TEST_ONLY
                 or name.startswith(('docs/', '.github/', 'tools/')))]


def changed_product_files(source, target):
    # A rename must retain its removed source path, including when its new
    # destination is documentation or a qualification helper.
    return product_changes(git('diff', '--no-renames', '--name-only', source, target).splitlines())


def main_checks(source, stable_source):
    runs = api('/actions/runs?head_sha=' + source + '&event=push&per_page=100')['workflow_runs']
    result = {}
    for name, path in (('ci', '.github/workflows/ci.yml'), ('stable', '.github/workflows/repo.yml')):
        matches = [run for run in runs if run['head_sha'] == source and run['head_branch'] == 'main'
                   and run['event'] == 'push' and run['path'] == path and run['run_attempt'] == 1]
        if name == 'stable' and not matches and stable_source != source:
            changes = git('diff', '--no-renames', '--name-only', stable_source, source).splitlines()
            # repo.yml deliberately ignores these exact docs/Markdown paths.
            # Never use this fallback for a pending/failed current-source run,
            # another helper change, or an unverified publication source.
            require(changes and all(name.startswith('docs/') or name.endswith('.md') for name in changes),
                    'Current main requires a new stable repository deployment')
            prior = api('/actions/runs?head_sha=' + stable_source + '&event=push&per_page=100')['workflow_runs']
            matches = [run for run in prior if run['head_sha'] == stable_source and run['head_branch'] == 'main'
                       and run['event'] == 'push' and run['path'] == path and run['run_attempt'] == 1]
        require(len(matches) == 1 and matches[0]['status'] == 'completed' and matches[0]['conclusion'] == 'success',
                'Current main source checks or stable repository deployment have not passed: ' + name)
        result[name] = matches[0]['id']
        if name == 'stable':
            result['stable_source_sha'] = matches[0]['head_sha']
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


def source_hash(ref, name):
    require(re.fullmatch('[0-9a-f]{40}', ref) and not Path(name).is_absolute()
            and '..' not in Path(name).parts, 'Unsafe qualification source identity')
    return hashlib.sha256(subprocess.check_output(
        ['git', '-C', str(ROOT), 'show', ref + ':' + name], timeout=120)).hexdigest()


EXTERNAL_PERFORMANCE_MODE = 'frozen-external-paired-v1'
LEGACY_PERFORMANCE_MODE = 'in-producer-paired-v1'
EXTERNAL_PERFORMANCE_WORKFLOW = '.github/workflows/paired-candidate-20261009.yml'
EXTERNAL_PERFORMANCE_MARKER = '.github/qualification-20261009.performance'
EXTERNAL_PERFORMANCE_PLAN = 'tools/performance/execution-manifest.json'


def performance_mode(manifest):
    mode = manifest['image'].get('producer_mode', LEGACY_PERFORMANCE_MODE)
    require(mode in (LEGACY_PERFORMANCE_MODE, EXTERNAL_PERFORMANCE_MODE),
            'Unknown image performance mode')
    require(manifest['performance'].get('performance_mode', LEGACY_PERFORMANCE_MODE) == mode,
            'Image and performance lane modes differ')
    return mode


def source_bytes(ref, name):
    require(re.fullmatch('[0-9a-f]{40}', ref) and not Path(name).is_absolute()
            and '..' not in Path(name).parts, 'Unsafe qualification source identity')
    return subprocess.check_output(['git', '-C', str(ROOT), 'show', ref + ':' + name], timeout=120)


def performance_contract(expected_sha):
    path = ROOT / 'tools/performance/contract.py'
    require(path.is_file() and not path.is_symlink()
            and type(expected_sha) is str and re.fullmatch('[0-9a-f]{64}', expected_sha) and sha(path) == expected_sha,
            'External performance validator is absent, unsafe or differs from the reviewed source')
    # Compile the verified bytes directly: ignored Python bytecode must never
    # substitute a timestamp/size-matched stale validator for the pinned source.
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == expected_sha, 'Performance validator changed before loading')
    spec = importlib.util.spec_from_file_location('qualified_performance_contract', path)
    result = importlib.util.module_from_spec(spec)
    exec(compile(data, str(path), 'exec'), result.__dict__)
    return result


def publication_files(manifest):
    if performance_mode(manifest) == LEGACY_PERFORMANCE_MODE:
        return FILES
    return FILES | set(performance_contract(manifest['execution_files'].get('tools/performance/contract.py')).EXECUTION_FILES)


def validate_performance_lane(manifest, jobs, fetch):
    """Require exactly one successful producer mode; failures are never rescued."""
    image, pin = manifest['image'], manifest['performance']
    if performance_mode(manifest) == LEGACY_PERFORMANCE_MODE:
        steps = [step for job in jobs if job['name'] == 'iso'
                 for step in job['steps'] if step['name'] == 'Paired KVM performance acceptance']
        require(len(steps) == 1 and steps[0]['conclusion'] == 'success',
                'Actual paired same-image measurements did not pass')
        require(pin['run_id'] == image['run_id'] and pin['source_sha'] == image['source_sha'],
                'Performance image/run differs')
        return validate_artifact(pin, 'paired-performance')
    fetch.validate_external_producer_steps(image, jobs)
    require(re.fullmatch('[0-9a-f]{40}', pin.get('reviewed_parent_sha', ''))
            and re.fullmatch('[0-9a-f]{64}', pin.get('plan_sha256', ''))
            and re.fullmatch('[0-9a-f]{64}', pin.get('execution_json_sha256', ''))
            and pin['run_id'] != image['run_id'], 'Invalid frozen external performance pin')
    artifact = validate_lane(pin, EXTERNAL_PERFORMANCE_WORKFLOW, 'external-paired-performance')
    run = api('/actions/runs/' + str(pin['run_id']))
    require(run['head_branch'] == 'codex/qualification-dispatch-20261008'
            and run['head_sha'] == pin['source_sha'] and run['path'] == EXTERNAL_PERFORMANCE_WORKFLOW
            and run['event'] == 'push' and type(run['run_attempt']) is int and run['run_attempt'] == 1
            and run['status'] == 'completed' and run['conclusion'] == 'success',
            'External performance branch or first-attempt execution differs')
    parent, source = pin['reviewed_parent_sha'], pin['source_sha']
    require(git('rev-list', '--parents', '-n', '1', source).split() == [source, parent]
            and source_bytes(source, EXTERNAL_PERFORMANCE_MARKER) == (parent + '\n').encode()
            and git('diff', '--no-renames', '--name-only', parent, source).splitlines() == [EXTERNAL_PERFORMANCE_MARKER],
            'External performance activation is not the reviewed marker-only child')
    return artifact


def performance_proof(evidence, manifest, fetch):
    image, pin = manifest['image'], manifest['performance']
    if performance_mode(manifest) == LEGACY_PERFORMANCE_MODE:
        state, comparison = read_json(evidence, 'status.json'), read_json(evidence, 'comparison.json')
        require(state['phase'] == 'complete_regression_gate_passed' and state['acceleration'] == 'kvm'
                and state['memory_mib'] == 4096 and state['vcpus'] == 2 and state['restricted_network'] is True
                and state['images']['candidate']['sha256'] == image['sha256']
                and len(state['runs']) == 6 and all(row['harness_exit'] == 0 for row in state['runs'])
                and comparison['status'] == 'regression_gate_passed'
                and comparison['measurement_precision']['valid'] is True
                and comparison['measurement_precision']['threshold_enclosure_valid'] is True,
                'Same-image paired precision/regression evidence failed')
        return dict(pin)
    contract = performance_contract(source_hash(pin['source_sha'], 'tools/performance/contract.py'))
    raw_plan = source_bytes(pin['source_sha'], EXTERNAL_PERFORMANCE_PLAN)
    require(len(raw_plan) < 128 * 1024
            and hashlib.sha256(raw_plan).hexdigest() == pin['plan_sha256'],
            'Frozen external plan differs from the reviewed source')
    plan = contract.parse_json(raw_plan)
    require(plan['ready'] is True, 'External performance plan is unreviewed')
    require(evidence.getinfo('execution.json').file_size <= 4_000_000
            and hashlib.sha256(evidence.read('execution.json')).hexdigest() == pin['execution_json_sha256'],
            'External performance execution receipt differs')
    expected_files = {name: source_hash(pin['source_sha'], name) for name in contract.EXECUTION_FILES}
    for name, expected in expected_files.items():
        path = ROOT / name
        require(path.is_file() and not path.is_symlink() and sha(path) == expected,
                'Frozen performance execution helper drift: ' + name)
    candidate_sources = {name: source_hash(image['source_sha'], name)
                         for name in contract.CANDIDATE_SOURCE_FILES}
    observer = contract.observer_hashes_from_sources(
        source_bytes(pin['source_sha'], 'tools/performance/guest.py'),
        source_bytes(pin['source_sha'], 'tools/performance/causal.py'))
    observer['comparator_sha256'] = source_hash(pin['source_sha'], 'tools/performance/compare.py')
    contract.validate_plan(plan, candidate_source_files=candidate_sources,
                           execution_files=expected_files, observer=observer)
    require(plan['image'] == image, 'Frozen performance plan image differs')
    require(0 < evidence.getinfo('producer-receipt.json').file_size <= 32_768,
            'Oversized external producer receipt')
    receipt_raw = evidence.read('producer-receipt.json')
    require(hashlib.sha256(receipt_raw).hexdigest() == image['producer_receipt_sha256'],
            'External producer receipt bytes differ')
    receipt = fetch.read_receipt(receipt_raw, image)
    spec = importlib.util.spec_from_file_location('qualified_frozen_comparator', ROOT / 'tools/performance/compare.py')
    comparator = importlib.util.module_from_spec(spec)
    comparator_bytes = (ROOT / 'tools/performance/compare.py').read_bytes()
    require(hashlib.sha256(comparator_bytes).hexdigest() == observer['comparator_sha256'],
            'Frozen comparator changed before loading')
    exec(compile(comparator_bytes, str(ROOT / 'tools/performance/compare.py'), 'exec'), comparator.__dict__)
    replay = contract.validate_evidence(evidence, plan=plan, plan_sha256=pin['plan_sha256'], image=image,
        execution_source_sha=pin['source_sha'], reviewed_parent_sha=pin['reviewed_parent_sha'],
        execution_run_id=pin['run_id'], comparator=comparator, producer_receipt=receipt)
    return dict(pin=pin, replay=replay, candidate_source_files=candidate_sources, observer=observer)


def dictation_lane_proof(archive, manifest, hardware_profile):
    """Check one complete hardware lane without substituting another profile."""
    state = read_json(archive, 'execution.json')
    image, pin = manifest['image'], manifest['dictation'][hardware_profile]
    require(state['schema'] == 'arctic-dictation-execution-v2' and state['hardware_profile'] == hardware_profile
            and state['status'] == 'exact_image_dictation_online_offline_local_sessions_passed'
            and state['image'] == image and state['execution_checker_head'] == pin['source_sha']
            and state['release_acceptance'] is False
            and state['fixture_manifest_sha256'] == pin['fixture_manifest_sha256']
            and re.fullmatch('[0-9a-f]{64}', pin['fixture_manifest_sha256']),
            'Dictation execution does not qualify this exact image')
    path = ROOT / 'tools/dictation-qualification/contract.py'
    require(sha(path) == source_hash(pin['source_sha'], 'tools/dictation-qualification/contract.py'),
            'Publication dictation validator differs from reviewed execution')
    spec = importlib.util.spec_from_file_location('qualified_dictation_contract', path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    required = {'online-installed-live', 'offline-installed-live', 'online-installed',
                'offline-installed', 'recovery', 'recovered-offline'}
    require(set(state['reports']) == required and set(state['installations']) == {'online', 'offline'},
            'Missing/extra dictation installation or report phases')
    indicator_names = {'dictation-indicator-' + phase + '.png' for phase in ('online-installed', 'recovered-offline')}
    require({entry.filename for entry in archive.infolist() if not entry.is_dir()}
            == {'execution.json', 'fixtures.json'} | {name + '.json' for name in required} | indicator_names,
            'Dictation evidence contains unexpected or missing files')
    require(archive.getinfo('fixtures.json').file_size < 128 * 1024, 'Oversized dictation fixture manifest')
    fixtures = archive.read('fixtures.json')
    require(hashlib.sha256(fixtures).hexdigest() == pin['fixture_manifest_sha256'],
            'Public dictation fixture manifest differs')
    hashes = {key: source_hash(pin['source_sha'], name) for key, name in (
        ('checker_sha256', 'tools/dictation-qualification/guest_check.py'),
        ('contract_sha256', 'tools/dictation-qualification/contract.py'),
        ('accuracy_sha256', 'tools/dictation-accuracy/accuracy.py'),
        ('pins_sha256', 'tools/dictation-accuracy/pins.json'))}
    hashes['controller_sha256'] = source_hash(image['source_sha'], 'packaging/dictation/dictation.py')
    hashes['child_exec_sha256'] = source_hash(image['source_sha'], 'packaging/dictation/child_exec.py')
    reports = {}
    for name in sorted(required):
        info = state['reports'][name]
        require(info['path'] == name + '.json' and info['status'] == 'passed'
                and re.fullmatch('[0-9a-f]{64}', info['sha256'])
                and archive.getinfo(info['path']).file_size < 128 * 1024
                and hashlib.sha256(archive.read(info['path'])).hexdigest() == info['sha256'],
                'Dictation checked report path, bytes or status differs')
        phase = 'live' if name.endswith('-live') else name
        kind = 'online' if name.startswith('online-') else 'offline'
        expected = dict(schema='arctic-dictation-context-v2', phase=phase, hardware_profile=hardware_profile,
                        source_sha=image['source_sha'], iso_sha256=image['sha256'], iso_bytes=image['bytes'],
                        installation_id=state['installations'][kind],
                        fixture_manifest_sha256=pin['fixture_manifest_sha256'], **hashes)
        report = read_json(archive, info['path'])
        contract.validate_report(report, expected, fixture_manifest=fixtures)
        require(info['phase'] == phase and info['installation_id'] == expected['installation_id']
                and info['boot_id'] == report['boot_id'], 'Dictation report/host provenance differs')
        reports[name] = report
    contract.validate_execution(state, reports, fixture_manifest=fixtures)
    required_images = {}
    require(set(state['indicators']) == {'online-installed', 'recovered-offline'}, 'Missing dictation indicator phases')
    for phase, info in state['indicators'].items():
        request = info['request']
        name = 'dictation-indicator-' + phase + '.png'
        require(info['path'] == name and info['iso_sha256'] == image['sha256']
                and info['installation_id'] == reports[phase]['context']['installation_id']
                and request['boot_id'] == reports[phase]['boot_id'] and request['phase'] == phase
                and request['installation_id'] == info['installation_id'] and request['receiver_empty'] is True
                and re.fullmatch('[0-9a-f]{32}', request['capture_nonce'])
                and any(gate['id'] == 'recording-status-published' and gate['status'] == 'passed'
                        and gate['observations'].get('sha256') == hashlib.sha256(request['capture_nonce'].encode()).hexdigest()
                        for gate in reports[phase]['gates'])
                and type(request['desktop_uid']) is int and request['desktop_uid'] > 0
                and archive.getinfo(name).file_size < 4 * 1024 * 1024
                and hashlib.sha256(archive.read(name)).hexdigest() == info['sha256']
                and archive.read(name).startswith(b'\x89PNG\r\n\x1a\n'), 'Dictation indicator provenance/bytes differ')
        required_images[name] = info['sha256']
    review = manifest['dictation_media_review'][hardware_profile]
    require(review['image_sha256'] == image['sha256'] and review['dictation_archive_sha256'] == pin['archive_sha256']
            and review['visual_status'] == 'passed' and review['images'] == required_images,
            'Exact-image dictation recording indicator visual review is absent')
    measurements = {}
    for phase in ('online-installed', 'recovered-offline'):
        measurements[phase] = {}
        for language in ('en', 'he'):
            rows = [sample for sample in reports[phase]['samples']
                    if sample['language'] == language and sample['purpose'] == 'cpu-session']
            words = sum(row['reference_words'] for row in rows)
            characters = sum(row['reference_chars'] for row in rows)
            measurements[phase][language] = dict(samples=len(rows),
                wer=sum(row['word_edits'] for row in rows) / words,
                cer=sum(row['char_edits'] for row in rows) / characters,
                elapsed_ns=sum(row['elapsed_ns'] for row in rows),
                audio_seconds=sum(row['audio_frames'] for row in rows) / 16000)
    proof = dict(run_id=pin['run_id'], source_sha=pin['source_sha'], artifact_sha256=pin['archive_sha256'],
                hardware_profile=hardware_profile, profile=contract.PROFILES[hardware_profile],
                fixture_manifest_sha256=pin['fixture_manifest_sha256'],
                gates='online and offline installations; same-disk recovery; real local Hebrew/English CPU sessions and failure retry',
                limitations=reports['online-installed']['limitations'], reports=state['reports'],
                indicator_review=review, measurements=measurements)
    return proof, {'state': state, 'reports': reports}, fixtures


def dictation_proof(archives, manifest):
    """Both six-boot hardware lanes are required for the same final image."""
    profiles = {'small-v2', 'turbo-q5-v3'}
    pins = manifest['dictation']
    require(type(pins) is dict and set(pins) == profiles and type(archives) is dict and set(archives) == profiles,
            'Dictation execution hardware profile inventory differs')
    require(len({pin['source_sha'] for pin in pins.values()}) == 1
            and len({pin['run_id'] for pin in pins.values()}) == 1
            and len({pin['fixture_manifest_sha256'] for pin in pins.values()}) == 1
            and len({pin['artifact_id'] for pin in pins.values()}) == 2
            and len({pin['archive_sha256'] for pin in pins.values()}) == 2,
            'Dictation execution profile source, run, fixture or distinct artifact identities differ')
    proofs, executions, fixture_bytes = {}, {}, None
    for profile in sorted(profiles):
        proof, execution, fixtures = dictation_lane_proof(archives[profile], manifest, profile)
        require(fixture_bytes is None or fixtures == fixture_bytes, 'Dictation profile fixture bytes differ')
        fixture_bytes = fixtures
        proofs[profile], executions[profile] = proof, execution
    path = ROOT / 'tools/dictation-qualification/contract.py'
    spec = importlib.util.spec_from_file_location('qualified_dictation_profiles', path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    cross = contract.validate_release_profiles(executions, fixture_manifest=fixture_bytes)
    return dict(hardware_profiles=proofs, cross_profile=cross,
                gates='two complete six-boot hardware lanes; distinct actual CPU/installed payloads and encrypted recovery disks',
                release_acceptance=False)


def installer_archive_records(archive, state, allowed_files, evidence):
    """Bind the public archive and decoded aliases to the protected collector."""
    names = {entry.filename for entry in archive.infolist() if not entry.is_dir()}
    require(names == set(allowed_files), 'Installer public archive inventory differs')
    screening = read_json(archive, 'upload-screening.json')
    require(set(screening) == {'scope', 'files'}
            and screening['scope'] == 'Owned synthetic QEMU VM only; no host desktop, VM disks or credentials'
            and set(screening['files']) == names - {'upload-screening.json'},
            'Installer upload screening inventory differs')
    diagnostics = {'provision.log', 'capture-build.log', 'installer-harness.log'}
    for name, item in screening['files'].items():
        data = archive.read(name)
        require(set(item) == {'original_sha256', 'uploaded_sha256', 'bytes', 'redactions'}
                and type(item['bytes']) is int and item['bytes'] == len(data)
                and re.fullmatch('[0-9a-f]{64}', item['original_sha256'])
                and item['uploaded_sha256'] == hashlib.sha256(data).hexdigest()
                and type(item['redactions']) is int and item['redactions'] >= 0
                and (name in diagnostics or item['redactions'] == 0)
                and (item['redactions'] > 0 or item['original_sha256'] == item['uploaded_sha256']),
                'Installer uploaded evidence changed or screening receipt differs: ' + name)
    guest, report = state['guest'], state['guest']['report']
    files = guest['files']
    require(set(files) == {Path(name).name for name in names if name.startswith('installer/')}
            - {'installer-state.json', 'transport-manifest.json', 'installer-provenance.json',
               'serial-installer-report.json'}, 'Installer transported payload inventory differs')
    for name, info in files.items():
        data = archive.read('installer/' + name)
        require(Path(name).name == name and set(info) == {'bytes', 'sha256'}
                and type(info['bytes']) is int and 0 < info['bytes'] <= 4 * 1024 * 1024
                and len(data) == info['bytes'] and hashlib.sha256(data).hexdigest() == info['sha256'],
                'Installer transported file bytes or hash differ: ' + name)
    canonical = lambda value: json.dumps(value, sort_keys=True, allow_nan=False).encode('ascii')
    for name, expected in (('installer-state.json', guest), ('installer-provenance.json', guest['provenance']),
                           ('installer-report.json', report), ('serial-installer-report.json', report)):
        require(canonical(read_json(archive, 'installer/' + name)) == canonical(expected),
                'Installer decoded transport alias differs: ' + name)
    transport = read_json(archive, 'installer/transport-manifest.json')
    require(set(transport) == {'schema', 'binding_id', 'evidence_root', 'files', 'bytes'}
            and transport['schema'] == 'arctic-installer-evidence-v1'
            and transport['binding_id'] == state['context']['binding_id']
            and transport['evidence_root'] == report['evidence_root']
            and re.fullmatch('/tmp/arctic-native-smoke-installer-[A-Za-z0-9_-]+', transport['evidence_root'])
            and type(transport['files']) is list and 1 <= len(transport['files']) <= 32,
            'Installer decoded transport manifest identity differs')
    paths = []
    for item in transport['files']:
        require(set(item) == {'path', 'bytes', 'sha256', 'compressed_bytes', 'chunks', 'encoding'}
                and item['path'] in files and item['bytes'] == files[item['path']]['bytes']
                and type(item['bytes']) is int and item['sha256'] == files[item['path']]['sha256']
                and type(item['compressed_bytes']) is int and 0 < item['compressed_bytes'] <= 4 * 1024 * 1024 + 65536
                and type(item['chunks']) is int and item['chunks'] == math.ceil(item['compressed_bytes'] / (18 * 1024))
                and item['encoding'] == 'zlib+base64', 'Installer decoded transport manifest file differs')
        paths.append(item['path'])
    require(paths == sorted(files) and type(transport['bytes']) is int
            and transport['bytes'] == sum(item['bytes'] for item in files.values()) <= 32 * 1024 * 1024,
            'Installer decoded transport manifest inventory or byte total differs')
    require(state['transport']['report_sha256'] == files['installer-report.json']['sha256'],
            'Installer original transport does not bind the actual report bytes')
    streams = state['diagnostic_streams']
    active = state['context']['schema'] == 'arctic-installer-active-context-v1'
    required_streams = {'serial.log', 'installer-port.log', 'qemu-installer-live.log'} | ({'serial-installed.log', 'qemu-installer-installed.log'} if active else set())
    require(set(streams) == required_streams
            and streams['serial.log'] == guest['serial'] and streams['installer-port.log'] == guest['port']
            and streams['installer-port.log']['sha256'] == state['transport']['port_sha256'],
            'Installer complete original diagnostic stream identity differs')
    bounds = [('serial.log', 8 * 1024 * 1024), ('installer-port.log', 64 * 1024 * 1024), ('qemu-installer-live.log', 4 * 1024 * 1024)]
    if active:
        bounds += [('serial-installed.log', 8 * 1024 * 1024), ('qemu-installer-installed.log', 4 * 1024 * 1024)]
        require(streams['serial-installed.log'] == state['host']['installed_boot']['serial'],
                'Installer installed serial differs from fresh boot receipt')
    for name, bound in bounds:
        item = streams[name]
        require(set(item) == {'bytes', 'sha256'} and type(item['bytes']) is int
                and (0 <= item['bytes'] <= bound if name.startswith('qemu-') else 0 < item['bytes'] <= bound)
                and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'Installer diagnostic stream bounds differ')
        if name not in ('serial.log', 'serial-installed.log'):
            require(archive.getinfo('host/' + name + '.bounded-prefix.bin').file_size == min(item['bytes'], 64 * 1024),
                    'Installer diagnostic stream prefix length differs')
        else:
            data = archive.read('host/' + name)
            require(len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'],
                    'Installer complete original serial byte identity differs')
    prefix = archive.read('host/installer-port.log.bounded-prefix.bin')
    for line, kind, expected in zip(prefix.splitlines(keepends=True)[:2], ('BEGIN', 'PROVENANCE'),
                                    (guest['begin'], guest['provenance'])):
        actual_kind, actual = evidence.record(line.decode('ascii'), {'BEGIN', 'PROVENANCE'}, 4 * 1024 * 1024 + 512)
        require(actual_kind == kind and canonical(actual) == canonical(expected),
                'Installer retained protected-port prefix identity differs')
    require(len(prefix.splitlines()) >= 2, 'Installer retained protected-port prefix is incomplete')
    begin, proof, end = guest['begin'], guest['provenance'], guest['collector']
    evidence.exact(begin, {'schema', 'stage', 'context', 'transport', 'release_acceptance'} | evidence.IDENTITY,
                   'Installer BEGIN fields differ')
    evidence.exact(proof, {'schema', 'stage', 'context', 'transport', 'cmdline', 'virtualization',
                          'release_acceptance'} | evidence.IDENTITY, 'Installer provenance fields differ')
    evidence.exact(end, {'binding_id', 'status', 'error', 'evidence_export_complete', 'release_acceptance'} | evidence.IDENTITY,
                   'Installer collector fields differ')
    require(begin['schema'] == 'arctic-installer-runner-v1' and proof['schema'] == 'arctic-installer-provenance-v1'
            and begin['stage'] == proof['stage'] == 'live'
            and canonical(begin['context']) == canonical(proof['context']) == canonical(state['context'])
            and begin['release_acceptance'] is proof['release_acceptance'] is end['release_acceptance'] is False
            and end['binding_id'] == state['context']['binding_id'] and end['status'] == 'passed' and end['error'] is None
            and end['evidence_export_complete'] is True
            and all(type(record[k]) is type(report[k]) and record[k] == report[k]
                    for record in (begin, proof, end) for k in evidence.IDENTITY),
            'Installer actual collector context, boot or completion differs')
    channel = begin['transport']
    evidence.exact(channel, {'schema', 'name', 'device', 'major', 'minor', 'uid', 'mode'},
                   'Installer protected port fields differ')
    require(canonical(channel) == canonical(proof['transport'])
            and channel['schema'] == 'arctic-installer-virtio-port-v1'
            and channel['name'] == 'arctic-installer-evidence'
            and type(channel['device']) is str and re.fullmatch('/dev/vport[0-9]+p[0-9]+', channel['device'])
            and type(channel['uid']) is int and channel['uid'] == 0
            and type(channel['mode']) is int and 0 <= channel['mode'] <= 0o7777 and not channel['mode'] & 0o022
            and type(channel['major']) is int and 0 < channel['major'] <= 99999
            and type(channel['minor']) is int and 0 <= channel['minor'] <= 99999
            and type(proof['cmdline']) is str and len(proof['cmdline']) <= 16384
            and {'rd.live.image', 'arctic.mode=install'} <= set(proof['cmdline'].split())
            and proof['virtualization'] in ('qemu', 'kvm'),
            'Installer actual live boot or protected evidence port differs')
    uart = [evidence.record(line, {'REQUEST', 'PORT-END'}, 16448)
            for line in archive.read('host/serial.log').decode('utf-8').splitlines(keepends=True)
            if line.startswith(evidence.PREFIX)]
    order = evidence.active_request_order(state['context'])
    require(len(uart) == len(order) + 1 and [kind for kind, value in uart] == ['REQUEST'] * len(order) + ['PORT-END'],
            'Installer original UART request/completion sequence differs')
    requests = [value for kind, value in uart[:-1]]
    evidence.validate_requests(requests, begin, report)
    require(canonical(requests) == canonical(guest['requests']),
            'Installer original UART requests differ from transported guest receipts')
    marker = uart[-1][1]
    evidence.exact(marker, {'schema', 'binding_id', 'status', 'end_sha256', 'release_acceptance'} | evidence.IDENTITY,
                   'Installer UART completion fields differ')
    require(canonical(marker) == canonical(guest['port_end'])
            and marker['schema'] == 'arctic-installer-port-end-v1'
            and marker['binding_id'] == state['context']['binding_id'] and marker['status'] == end['status']
            and marker['release_acceptance'] is False
            and all(type(marker[k]) is type(begin[k]) and marker[k] == begin[k] for k in evidence.IDENTITY)
            and marker['end_sha256'] == evidence.digest(evidence.canonical(end)),
            'Installer original UART completion does not bind the actual collector')
    return files


def installer_proof(archive, manifest, active=False):
    """Require the fresh live image's actual GUI restoration matrix and review."""
    image, pin = manifest['image'], manifest['installer_active' if active else 'installer']
    contract_name = 'active-contract.py' if active else 'contract.py'
    path = ROOT / 'tools/installer-qualification' / contract_name
    require(sha(path) == source_hash(pin['source_sha'], 'tools/installer-qualification/' + contract_name),
            'Publication installer validator differs from reviewed execution')
    # Imported producer/transport validation code must match the reviewed lane,
    # even when publication runs on a later helper-only source commit.
    helpers = ('guest.py', 'evidence.py', 'contract.py', 'active-guest.py', 'installed-guest.py') if active else ('guest.py', 'evidence.py')
    for name in helpers:
        require(sha(ROOT / 'tools/installer-qualification' / name)
                == source_hash(pin['source_sha'], 'tools/installer-qualification/' + name),
                'Publication installer helper differs from reviewed execution: ' + name)
    spec = importlib.util.spec_from_file_location('qualified_installer_contract', path)
    contract = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(contract)
    spec = importlib.util.spec_from_file_location('qualified_installer_transport', path.with_name('evidence.py'))
    evidence = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evidence)
    state = read_json(archive, 'execution.json')
    execution = contract.validate_execution(state, image, pin['source_sha'],
        archive.read('host/serial.log'), archive.read)
    require(state.get('errors') == [], 'Installer execution contains failures despite its status')
    require(type(state['execution']['run_id']) is int and state['execution']['run_id'] == pin['run_id'],
            'Installer embedded execution run differs from its archived workflow')
    require(set(state['source_inputs']) == set(contract.EXECUTION_FILES),
            'Installer execution source inventory differs')
    for name, expected in state['source_inputs'].items():
        require(expected == source_hash(pin['source_sha'], name),
                'Installer execution source bytes differ: ' + name)
    build = state['build']
    require(build['schema'] == 'arctic-taskbar-tools-v1' and build['release_acceptance'] is False
            and set(build['sources']) == {'shell/dev/virtual-pointer.c',
                'tools/native-functional/taskbar-screencopy.c', 'shell/dev/wlr-screencopy-unstable-v1.xml'}
            and set(build['binaries']) == {'virtual-pointer', 'raw-screencopy'},
            'Installer native capture build inventory differs')
    for name, expected in build['sources'].items():
        require(expected == source_hash(pin['source_sha'], name),
                'Installer native capture source bytes differ: ' + name)
    context = state['context']
    expected = dict(schema='arctic-installer-context-v1', source_sha=image['source_sha'],
        iso_sha256=image['sha256'], iso_bytes=image['bytes'], execution_sha=pin['source_sha'],
        binding_id=context['binding_id'], checker_sha256=source_hash(pin['source_sha'], 'tools/installer-qualification/guest.py'),
        runtime_sha256=source_hash(pin['source_sha'], 'tools/native-functional/taskbar-runtime.py'),
        native_sha256=source_hash(pin['source_sha'], 'tools/native-functional/native_smoke.py'),
        capture_sha256=build['binaries']['raw-screencopy'])
    if active:
        expected.update(schema='arctic-installer-active-context-v1',
            active_checker_sha256=source_hash(pin['source_sha'], 'tools/installer-qualification/active-guest.py'),
            installed_checker_sha256=source_hash(pin['source_sha'], 'tools/installer-qualification/installed-guest.py'),
            disk_serial=context['disk_serial'], disk_bytes=64 * 1024 ** 3, disk_node='target0', write_bps=8 * 1024 ** 2)
    require(context == expected and re.fullmatch('[0-9a-f]{64}', expected['capture_sha256']),
            'Installer exact-image helper or compiled capture context differs')
    guest = read_json(archive, 'installer/installer-state.json')
    host = read_json(archive, 'host/host-execution.json')
    report = read_json(archive, 'installer/installer-report.json')
    transitions = read_json(archive, 'host/installer-host-transitions.json')
    require(guest == state['guest'] and host == state['host'],
            'Installer independently checked guest/host records differ from archive')
    require(transitions['schema'] == 'arctic-installer-host-transitions-v1'
            and transitions['context'] == expected and transitions['boot_id'] == report['boot_id']
            and transitions['release_acceptance'] is False
            and transitions['receipts'] == host['host_transitions'],
            'Installer actual host transition record or live boot differs')
    files = installer_archive_records(archive, state, contract.ARCHIVE_FILES, evidence)
    actual_guest = {entry.filename.removeprefix('installer/') for entry in archive.infolist()
                    if not entry.is_dir() and entry.filename.startswith('installer/')}
    require(actual_guest == set(files) | {'installer-state.json', 'transport-manifest.json',
            'installer-provenance.json', 'serial-installer-report.json'},
            'Installer transported payload contains unexpected or missing files')
    # The publish checkout is sparse. Reconstruct only the declared source
    # inputs from the ISO's actual commit before deriving installed-file hashes.
    with tempfile.TemporaryDirectory(prefix='arctic-installer-source-') as temp:
        source = Path(temp)
        require(not git('ls-tree', '--name-only', image['source_sha'], '--',
                'dotfiles/.local/bin/arctic-installer'), 'Alternate built installer wrapper needs review')
        for name in set(contract.PACKAGED_SOURCES.values()):
            require(not Path(name).is_absolute() and '..' not in Path(name).parts,
                    'Unsafe installer packaged source path')
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(subprocess.check_output(['git', '-C', str(ROOT), 'show',
                image['source_sha'] + ':' + name], timeout=120))
        sources = contract.packaged_source_hashes(source)
    summary = contract.validate_report(report, expected, files,
        lambda name: archive.read('installer/' + name), sources)
    if active:
        catalog_bytes = subprocess.check_output(['git', '-C', str(ROOT), 'show', image['source_sha'] + ':modules/catalog.toml'], timeout=120)
        contract.validate_catalog_selection(report, catalog_bytes)
    require([row['request'] for row in transitions['receipts']] == summary['requests'],
            'Installer independently observed guest requests and host actions differ')
    guest_images = {'installer/' + name for name in contract.GUEST_IMAGES}
    host_images = set(contract.REQUIRED_IMAGES) - guest_images
    required_images = state['required_images']
    require(set(required_images) == guest_images | host_images,
            'Installer complete physical-capture visual inventory differs')
    for name, expected_sha in required_images.items():
        require(0 < archive.getinfo(name).file_size <= 4 * 1024 * 1024
                and archive.read(name).startswith(b'\x89PNG\r\n\x1a\n')
                and hashlib.sha256(archive.read(name)).hexdigest() == expected_sha,
                'Installer restoration screenshot bytes or hash differ: ' + name)
    require({name for name in actual_guest if name.endswith('.png')}
            == {Path(name).name for name in guest_images}, 'Installer guest capture matrix differs')
    review = manifest['installer_active_media_review' if active else 'installer_media_review']
    require(review['visual_status'] == 'passed' and review['image_sha256'] == image['sha256']
            and review['installer_archive_sha256'] == pin['archive_sha256']
            and review['images'] == required_images,
            'Exact-image installer baseline, disruption and restoration visual review is absent')
    return dict(run_id=pin['run_id'], source_sha=pin['source_sha'], archive_sha256=pin['archive_sha256'],
        execution=execution, restoration=summary, visual_review=review,
        scope=('original copy writer preserved through VT and hosting-output loss; same unencrypted offline UEFI install and fresh enforcing installed boot'
               if active else 'prepared Hebrew keyboard wizard; no active installation progress claim'), release_acceptance=False)


def taskbar_proof(archive, manifest):
    """Independently check the actual-image taskbar matrix, inputs and captures."""
    names = [entry.filename for entry in archive.infolist() if not entry.is_dir()
             and Path(entry.filename).name == 'taskbar-report.json']
    require(len(names) == 1, 'Missing/duplicate actual-image taskbar report')
    execution = read_json(archive, 'execution.json')
    state = read_json(archive, 'taskbar/taskbar-state.json')
    transport = execution['taskbar_transport']
    require(set(transport) == {'name', 'bytes', 'sha256', 'kind'}
            and transport['name'] == 'taskbar-boot.log'
            and transport['kind'] == 'root-owned named virtio-serial output bound to original installed native boot'
            and type(transport['bytes']) is int and 0 < transport['bytes'] <= 210 * 1024 * 1024
            and re.fullmatch('[0-9a-f]{64}', transport['sha256']), 'Taskbar original port transport identity differs')
    prefix_name = 'taskbar-boot.log.bounded-prefix.bin'
    prefix_info = execution['harness_evidence'][prefix_name]
    require(prefix_info['original_bytes'] == transport['bytes']
            and prefix_info['original_sha256'] == transport['sha256']
            and prefix_info['bytes'] == min(64 * 1024, transport['bytes'])
            and archive.getinfo('harness/' + prefix_name).file_size == prefix_info['bytes']
            and hashlib.sha256(archive.read('harness/' + prefix_name)).hexdigest() == prefix_info['sha256'],
            'Taskbar retained original transport bytes/hash or bounded prefix differs')
    context = execution['taskbar_context']
    image, pin = manifest['image'], manifest['native']
    require(set(context) == {'schema', 'source_sha', 'iso_sha256', 'iso_bytes', 'execution_sha', 'token',
            'checker_sha256', 'runtime_sha256', 'native_sha256', 'pointer_sha256', 'capture_sha256'}
            and context['schema'] == 'arctic-taskbar-context-v1'
            and context['source_sha'] == image['source_sha'] and context['iso_sha256'] == image['sha256']
            and context['iso_bytes'] == image['bytes'] and context['execution_sha'] == pin['source_sha']
            and re.fullmatch('[0-9a-f]{32}', context['token']), 'Taskbar exact-image execution context differs')
    for key, name in (('checker_sha256', 'taskbar.py'), ('runtime_sha256', 'taskbar-runtime.py'),
                      ('native_sha256', 'native_smoke.py')):
        require(context[key] == source_hash(pin['source_sha'], 'tools/native-functional/' + name),
                'Taskbar executed checker bytes differ: ' + name)
    build = execution['taskbar_build']
    require(build['schema'] == 'arctic-taskbar-tools-v1' and build['release_acceptance'] is False
            and set(build['sources']) == {'shell/dev/virtual-pointer.c',
                 'tools/native-functional/taskbar-screencopy.c', 'shell/dev/wlr-screencopy-unstable-v1.xml'}
            and set(build['binaries']) == {'virtual-pointer', 'raw-screencopy'}, 'Taskbar tool build inventory differs')
    for name, sha in build['sources'].items():
        require(sha == source_hash(pin['source_sha'], name), 'Taskbar compiled source bytes differ: ' + name)
    require(context['pointer_sha256'] == build['binaries']['virtual-pointer']
            and context['capture_sha256'] == build['binaries']['raw-screencopy']
            and all(re.fullmatch('[0-9a-f]{64}', sha) for sha in build['binaries'].values()),
            'Taskbar compiled ELF identity differs')
    require(execution['taskbar'] == state and state['schema'] == 'arctic-taskbar-state-v1'
            and state['stage'] == 'installed' and state['status'] == 'passed'
            and state['release_acceptance'] is False and state['required_pngs'] == 480
            and state['context'] == context, 'Taskbar runtime/transport proof failed or differs')
    provenance = state['provenance']
    native = read_json(archive, 'native-installed/serial-native-provenance.json')
    require(provenance['context'] == context and provenance['stage'] == 'installed'
            and provenance['schema'] == 'arctic-taskbar-provenance-v1'
            and provenance['release_acceptance'] is False
            and all(provenance[key] == native[key] for key in ('boot_id', 'desktop_uid',
                    'active_desktop_session', 'cmdline')) and native['stage'] == 'installed'
            and native['native_source_sha256'] == context['native_sha256']
            and provenance['virtualization'] in ('qemu', 'kvm')
            and 'rd.live.image' not in provenance['cmdline'].split(), 'Taskbar installed boot/session identity differs')
    collector = state['collector']
    require(collector['status'] == 'passed' and collector['error'] is None
            and collector['evidence_export_complete'] is True and collector['release_acceptance'] is False
            and collector['token'] == context['token']
            and all(collector[key] == provenance[key] for key in ('boot_id', 'desktop_uid', 'active_desktop_session')),
            'Taskbar collector completion proof differs')
    channel = provenance['transport']
    require(set(channel) == {'schema', 'name', 'device', 'major', 'minor', 'uid', 'mode'}
            and channel['schema'] == 'arctic-taskbar-virtio-port-v1'
            and channel['name'] == 'arctic-taskbar-evidence'
            and re.fullmatch('/dev/vport[0-9]+p[0-9]+', channel['device'])
            and type(channel['uid']) is int and channel['uid'] == 0
            and type(channel['mode']) is int and 0 <= channel['mode'] <= 0o7777 and not channel['mode'] & 0o022
            and type(channel['major']) is int and 0 < channel['major'] <= 99999
            and type(channel['minor']) is int and 0 <= channel['minor'] <= 99999,
            'Taskbar actual guarded transport device proof differs')
    report = read_json(archive, names[0])
    require(report['schema'] == 'arctic-installed-taskbar-v1' and report['stage'] == 'installed'
            and report['status'] == 'passed' and report['release_acceptance'] is False
            and report['reservation_observer'] == 'Mango maximized-client rectangles; IPC does not expose raw exclusive-zone values',
            'Taskbar report identity, status or measurement scope differs')
    required_cleanup = {'settings_bytes_restored', 'outputs_restored', 'original_windows_retained',
                        'bars_restored', 'only_proved_owned_processes_stopped'}
    require(set(report['cleanup']) == required_cleanup and all(report['cleanup'][key] is True for key in required_cleanup)
            and report['security']['selinux'] == 'Enforcing' and report['security']['observed_new_avcs'] == 0,
            'Taskbar cleanup or security interval failed')
    for name in ('Bar.qml', 'ScreenFrame.qml', 'Session.qml', 'Theme.qml', 'VerticalBar.qml', 'shell.qml',
                 'BarVisibility.js', 'scripts/window_geometry.py'):
        require(report['installed_inputs']['/usr/share/arctic/shell/' + name]
                == source_hash(manifest['image']['source_sha'], 'shell/' + name),
                'Actual taskbar shell bytes differ from built source: ' + name)
    require(re.fullmatch('[0-9a-f]{64}', report['installed_inputs']['/usr/bin/foot']), 'Taskbar Foot executable unbound')
    require(all(re.fullmatch('[0-9a-f]{64}', report['installed_inputs'][name])
                for name in ('/usr/bin/mango', '/usr/bin/mmsg'))
            and report['installed_inputs']['/run/t/virtual-pointer'] == context['pointer_sha256']
            and report['installed_inputs']['/run/t/raw-screencopy'] == context['capture_sha256'],
            'Taskbar installed compositor or probe executable unbound')
    window = report['owned_window']
    require(type(window['pid']) is int and window['pid'] > 1 and type(window['start_ticks']) is int
            and window['start_ticks'] > 0 and type(window['client_id']) is str and bool(window['client_id'])
            and window['uid'] == provenance['desktop_uid'] and window['is_xwayland'] is False
            and window['executable'] == '/usr/bin/foot'
            and window['executable_sha256'] == report['installed_inputs']['/usr/bin/foot'],
            'Taskbar fresh native Foot ownership proof differs')
    cases = report['results']
    require(type(cases) is list and len(cases) == 24, 'Taskbar case count differs')
    outputs = {case['output'] for case in cases}
    require(len(outputs) == 2 and {(case['output'], case['scale'], case['edge']) for case in cases}
            == {(output, scale, edge) for output in outputs for scale in (1, 1.5, 2)
                for edge in ('top', 'bottom', 'left', 'right')}, 'Taskbar output/scale/edge coverage incomplete')
    evidence_root = Path(report['evidence_root'])
    require(evidence_root.is_absolute() and evidence_root.parent == Path('/tmp')
            and evidence_root.name.startswith('arctic-native-smoke-'), 'Unexpected taskbar guest evidence root')
    prefix = Path(names[0]).parent
    require(prefix == Path('taskbar'), 'Taskbar archive transport path differs')
    for name, item in state['files'].items():
        relative = Path(name)
        require(not relative.is_absolute() and '..' not in relative.parts and relative.as_posix() == name
                and relative.suffix in ('.png', '.json', '.log'), 'Unsafe taskbar transported file path')
        entry = archive.getinfo((prefix / relative).as_posix())
        require(entry.file_size == item['bytes'] and entry.file_size <= 4 * 1024 * 1024
                and hashlib.sha256(archive.read(entry)).hexdigest() == item['sha256'],
                'Taskbar transported file bytes differ')
    require(len(state['files']) <= 512 and sum(item['bytes'] for item in state['files'].values()) <= 128 * 1024 * 1024,
            'Taskbar transported archive bounds differ')
    captures = {}
    def capture(item, shown=None):
        relative = Path(item['path']).relative_to(evidence_root)
        require('..' not in relative.parts and relative.suffix == '.png', 'Unsafe taskbar capture path')
        name = (prefix / relative).as_posix()
        require(archive.getinfo(name).file_size < 4 * 1024 * 1024
                and hashlib.sha256(archive.read(name)).hexdigest() == item['sha256']
                and archive.read(name).startswith(b'\x89PNG\r\n\x1a\n'), 'Taskbar physical capture bytes differ')
        if shown is not None:
            fraction = item['non_foot_fraction']
            require(item['visible'] is shown and type(fraction) in (int, float)
                    and 0 <= fraction <= 1 and (fraction >= .6 if shown else fraction <= .1),
                    'Taskbar actual pixel visibility gate failed')
        captures[name] = item['sha256']
    for case in cases:
        baseline = case['baseline']
        require(set(baseline) == {'x', 'y', 'width', 'height'}
                and all(type(value) in (int, float) and math.isfinite(value) for value in baseline.values())
                and baseline['width'] > 0 and baseline['height'] > 0, 'Invalid taskbar baseline geometry')
        for mode, actual in (('always', case['always_geometry']), ('dodge', case['hiding_geometry'])):
            insets = dict.fromkeys(('top', 'bottom', 'left', 'right'), 6)
            if mode == 'always': insets[case['edge']] += 32
            expected = dict(x=baseline['x'] + insets['left'], y=baseline['y'] + insets['top'],
                            width=baseline['width'] - insets['left'] - insets['right'],
                            height=baseline['height'] - insets['top'] - insets['bottom'])
            require(set(actual) == set(expected)
                    and all(type(actual[key]) in (int, float) and math.isfinite(actual[key])
                            and abs(actual[key] - value) <= 1 for key, value in expected.items()),
                    'Taskbar effective frame/exclusive geometry failed')
        require([row['mode'] for row in case['covered_windows']] == ['auto', 'dodge']
                and [row['mode'] for row in case['transitions']] == ['auto', 'dodge', 'always', 'auto', 'dodge'],
                'Taskbar covered/fullscreen transitions incomplete')
        for row in case['covered_windows'] + case['transitions']:
            capture(row['rest'], False)
            if row['mode'] != 'always': capture(row['reveal'], True)
            if row in case['covered_windows']:
                require(set(row['geometry']) == set(case['hiding_geometry'])
                        and all(abs(row['geometry'][key] - value) <= 1
                                for key, value in case['hiding_geometry'].items()),
                        'Taskbar covered Auto/Dodge effective geometry differs')
            layers = row['layers']
            for namespace, count, layer in (('arctic-bar', 1, 'top' if row['mode'] == 'always' else 'overlay'),
                                           ('arctic-frame', 1, 'bottom'),
                                           ('arctic-frame-reserve', 3 if row['mode'] == 'always' else 4, 'bottom')):
                members = [item for item in layers if item.get('name') == namespace]
                require(all(sum(item.get('monitor') == output for item in members) == count for output in outputs)
                        and all(item.get('monitor') in outputs and item.get('layer') == layer for item in members),
                        'Taskbar actual mapped layer counts differ')
        capture(case['exposed_frame'])
    images = {'taskbar/' + name: item['sha256'] for name, item in state['files'].items()
              if Path(name).suffix == '.png'}
    require(len(images) >= 480 and all(name in images for name in captures),
            'Taskbar complete visual review inventory missing')
    review = manifest['taskbar_media_review']
    require(review['visual_status'] == 'passed' and review['image_sha256'] == image['sha256']
            and review['native_archive_sha256'] == pin['archive_sha256'] and review['images'] == images,
            'Exact taskbar screenshot visual review is absent')
    return dict(schema=report['schema'], cases=24, outputs=sorted(outputs),
                reservation_observer=report['reservation_observer'], captures=captures,
                visual_review=review, transport=transport, transport_prefix=prefix_info, release_acceptance=False)


def native_apps_proof(archive, manifest, state):
    """Repeat the additive exact-source RPM/GTK3/GIO check for both real boots."""
    image, pin = manifest['image'], manifest['native']
    path = ROOT / 'tools/native-functional/apps.py'
    require(sha(path) == source_hash(pin['source_sha'], 'tools/native-functional/apps.py'),
            'Publication app-defaults validator differs from reviewed execution')
    spec = importlib.util.spec_from_file_location('qualified_native_apps', path)
    apps = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(apps)
    expected = dict(source_sha=image['source_sha'], iso_sha256=image['sha256'], iso_bytes=image['bytes'],
        checker_sha256=source_hash(pin['source_sha'], 'tools/native-functional/apps.py'),
        native_sha256=source_hash(pin['source_sha'], 'tools/native-functional/native_smoke.py'),
        manifest_sha256=source_hash(image['source_sha'], 'iso/kiwi/config.kiwi'),
        mimeapps_sha256=source_hash(image['source_sha'], 'packaging/desktop/live-mimeapps.list'))
    require(state['app_defaults_context'] == expected and type(state['apps']) is dict
            and set(state['apps']) == {'live', 'installed'},
            'Native requested-apps context or actual two-boot inventory differs')
    def source(name):
        return subprocess.check_output(['git', '-C', str(ROOT), 'show', image['source_sha'] + ':' + name], timeout=120)
    mimes = apps.mime_defaults(source('packaging/desktop/live-mimeapps.list'))
    packages = {item.attrib['name'] for item in ET.fromstring(source('iso/kiwi/config.kiwi')).iter('package')}
    require(set(apps.PACKAGES) - {'bash'} <= packages, 'Exact image manifest requested applications differ')
    proofs, boots = {}, set()
    for stage in ('live', 'installed'):
        provenance = read_json(archive, 'native-' + stage + '/serial-native-provenance.json')
        require(provenance['stage'] == state['apps'][stage]['stage'] == stage
                and provenance['native_source_sha256'] == expected['native_sha256']
                and provenance['release_acceptance'] is False
                and ('rd.live.image' in provenance['cmdline'].split()) == (stage == 'live'),
                'Application defaults original native source or actual boot medium differs')
        proofs[stage] = apps.validate_report(state['apps'][stage], expected, mimes, provenance)
        boots.add(state['apps'][stage]['boot_id'])
    require(len(boots) == 2, 'Requested-apps live and installed probes must be actual separate boots')
    return dict(context=expected, stages=proofs,
                scope='Actual installed application inventory, GTK3 RPM requirements and fresh desktop GIO defaults',
                release_acceptance=False)


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
    taskbar = taskbar_proof(archive, manifest)
    apps = native_apps_proof(archive, manifest, state)
    return dict(run_id=pin['run_id'], source_sha=pin['source_sha'], artifact_sha256=pin['archive_sha256'],
                native_gates='all eight passed in live and encrypted offline installed phases',
                media_review=review, photos='passed in live and installed phases', taskbar=taskbar, apps=apps)


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
    require(set(manifest['execution_files']) == publication_files(manifest), 'Publication execution inventory differs')
    for name, expected in manifest['execution_files'].items():
        require(re.fullmatch('[0-9a-f]{64}', expected) and not (ROOT / name).is_symlink()
                and sha(ROOT / name) == expected, 'Publication source bytes differ: ' + name)
    require(manifest['tag'] == 'v1.2.1' and re.fullmatch('[0-9a-f]{40}', manifest['main_sha']), 'Invalid release identity')
    release_main = api('/git/ref/heads/main')['object']['sha']
    require(re.fullmatch('[0-9a-f]{40}', release_main), 'Invalid current main source')
    require(not api('/pulls?state=open&per_page=100'), 'Arctic PRs remain open')
    require(type(manifest['dictation']) is dict and set(manifest['dictation']) == {'small-v2', 'turbo-q5-v3'},
            'Both dictation hardware qualification pins are required')
    require(type(manifest['installer']) is dict and type(manifest['installer_media_review']) is dict,
            'Actual installer restoration qualification and visual review pins are required')
    require(type(manifest.get('installer_active')) is dict and type(manifest.get('installer_active_media_review')) is dict,
            'Actual in-flight installer restoration, completion, installed boot and visual review pins are required')
    for ref in {manifest['image']['source_sha'], manifest['main_sha'], release_main,
                manifest['native']['source_sha'], manifest['installer']['source_sha'],
                manifest['installer_active']['source_sha'],
                manifest['performance']['source_sha'],
                *(pin['source_sha'] for pin in manifest['dictation'].values())}:
        subprocess.run(['git', '-C', str(ROOT), 'fetch', '--filter=blob:none', 'origin', ref], check=True, timeout=120)
    subprocess.run(['git', '-C', str(ROOT), 'merge-base', '--is-ancestor', manifest['main_sha'], release_main], check=True)
    current_checks = main_checks(release_main, manifest['main_sha'])
    require(not changed_product_files(manifest['image']['source_sha'], release_main),
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
    perf = manifest['performance']
    validate_performance_lane(manifest, jobs['jobs'], fetch)
    validate_lane(manifest['native'], '.github/workflows/native-candidate-20261008.yml', 'native-candidate-qualification')
    for profile, pin in manifest['dictation'].items():
        validate_lane(pin, '.github/workflows/dictation-candidate-20261009.yml',
                      'dictation-candidate-qualification-' + profile)
    validate_lane(manifest['installer'], '.github/workflows/installer-candidate-20261009.yml',
                  'candidate-installer-restoration')
    validate_lane(manifest['installer_active'], '.github/workflows/installer-active-candidate-20261009.yml',
                  'candidate-installer-active-restoration')
    validate_lane(manifest['update'], '.github/workflows/image-update-20261008.yml', 'same-image-nix-signed-update')
    require(not out.exists(), 'Prepared release assets must be unused')
    with tempfile.TemporaryDirectory(prefix='arctic-qualified-') as temp:
        temp = Path(temp)
        with archive(perf, temp / 'performance.zip') as evidence:
            performance = performance_proof(evidence, manifest, fetch)
        with archive(manifest['native'], temp / 'native.zip') as evidence:
            native = native_proof(evidence, manifest)
        with ExitStack() as stack:
            dictation_archives = {profile: stack.enter_context(archive(pin, temp / ('dictation-' + profile + '.zip')))
                                  for profile, pin in manifest['dictation'].items()}
            dictation = dictation_proof(dictation_archives, manifest)
        with archive(manifest['installer'], temp / 'installer.zip') as evidence:
            installer = installer_proof(evidence, manifest)
        with archive(manifest['installer_active'], temp / 'installer-active.zip') as evidence:
            installer_active = installer_proof(evidence, manifest, active=True)
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
        torrent_spec = importlib.util.spec_from_file_location('qualified_torrent', ROOT / 'tools/qualified-release/torrent.py')
        torrent = importlib.util.module_from_spec(torrent_spec)
        torrent_spec.loader.exec_module(torrent)
        transport = torrent.create(out / name, out / (name + '.torrent'), manifest['tag'])
        require(transport['iso_sha256'] == image['sha256'], 'Torrent image checksum differs')
        (out / (name + '.torrent.sha256')).write_text(transport['torrent_sha256'] + '  ' + name + '.torrent\n')
        proof = dict(tag=manifest['tag'], main_sha=manifest['main_sha'], release_main_sha=release_main,
                     release_main_checks=current_checks, image=image,
                     performance=performance, native=native, dictation=dictation, installer=installer, installer_active=installer_active,
                     update=manifest['update'], release_acceptance='qualified',
                     measured_speed_or_ram_gain_claim=False, torrent=transport)
        (out / 'qualification.json').write_text(json.dumps(proof, indent=2) + '\n')
        (out / 'release-notes.md').write_text(
            'Arctic Linux 1.2.1 for x86_64, with UEFI and BIOS boot.\n\n'
            'Lightweight defaults: GNOME Web, Foot, GTK3 PCManFM, XArchiver, Celluloid, FeatherPad, Nano and Fish/Bash. '
            'Includes the covered/fractional screen-frame fix and the author\'s photo wallpapers, with City Afterglow as the fresh default.\n\n'
            'The exact retained ISO passed Try/Install/Safe startup, enforcing encrypted offline installation, native app/media checks, '
            'six live graphical installer restoration cycles retaining the prepared Hebrew keyboard wizard, '
            'VT and hosting-output restoration while the original root-copy writer continued, completion of that same unencrypted offline install and a fresh installed boot, '
            'paired KVM precision/regression checks and a signed optimized stable Arctic update with offline apply and subsequent reboot. '
            'These checks make no physical hardware, substantial speed or RAM improvement claim.\n\n'
            f"ISO bytes: {image['bytes']}. SHA-256: `{image['sha256']}`.\n\n"
            'Download the ISO and checksum, then run `sha256sum -c Arctic-Linux-1.2.1-x86_64.iso.sha256`. '
            'A single-file torrent is included with the immutable GitHub Release URL as its HTTP seed. '
            'Its piece hashes describe the exact ISO; no active peer or tracker availability is claimed. '
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
