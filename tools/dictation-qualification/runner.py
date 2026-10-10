#!/usr/bin/env python3
"""Run separate online/offline dictation tests against one exact retained ISO.

This lane never installs a replacement controller, runtime or model from its
data CD. Audio fixtures are public FLEURS samples. Only transcript-free checked
reports are copied to upload evidence; raw harness logs remain private.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = {'.github/workflows/dictation-candidate-20261009.yml',
         'tools/dictation-qualification/runner.py', 'tools/dictation-qualification/guest_check.py',
         'tools/dictation-qualification/contract.py', 'tools/dictation-accuracy/accuracy.py',
         'tools/dictation-accuracy/pins.json', 'tools/test-install.sh', 'tools/lib/vmtest.py',
         'tools/lib/container.sh', 'tools/performance/prepare-vm-tools.sh',
         'tools/native-functional/fetch-image.py'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def verify(args):
    manifest = json.loads(args.manifest.read_text())
    require(manifest.get('ready') is True and manifest.get('release_acceptance') is False,
            'Dictation qualification is disabled until exact image, fixtures and execution are reviewed')
    expected_env = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
                        GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',
                        GITHUB_REF='refs/heads/codex/qualification-dispatch-20261010',
                        GITHUB_WORKFLOW='Candidate dictation image qualification',
                        GITHUB_EVENT_NAME='push', GITHUB_RUN_ATTEMPT='1')
    require(all(os.environ.get(key) == value for key, value in expected_env.items()),
            'Requires reviewed disposable dictation Actions lane')
    require(manifest.get('hardware_profiles') == ['small-v2', 'turbo-q5-v3']
            and args.hardware_profile in manifest['hardware_profiles'], 'Unreviewed dictation hardware profile')
    image = manifest['image']
    require(re.fullmatch('[0-9a-f]{40}', image['source_sha'])
            and re.fullmatch('[0-9a-f]{64}', image['sha256'])
            and type(image['bytes']) is int and 0 < image['bytes'] < 2_000_000_000
            and type(image['run_id']) is int and image['run_id'] > 0
            and image['name'] == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso",
            'Invalid exact candidate image identity')
    for tree, head in ((args.source, image['source_sha']), (ROOT, os.environ['GITHUB_SHA'])):
        require(subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True).strip() == head
                and not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain'], text=True).strip(),
                'Changed/dirty exact dictation source or execution checkout')
    require(set(manifest['execution_files']) == FILES, 'Dictation execution inventory differs')
    for name, expected in manifest['execution_files'].items():
        path = ROOT / name
        require(re.fullmatch('[0-9a-f]{64}', expected) and path.is_file()
                and not path.is_symlink() and sha(path) == expected, 'Changed dictation execution file: ' + name)
    iso = args.inputs / 'iso' / image['name']
    require(iso.is_file() and not iso.is_symlink() and iso.stat().st_size == image['bytes']
            and sha(iso) == image['sha256'], 'Actual ISO differs from reviewed image')
    require(re.fullmatch('[0-9a-f]{64}', manifest['fixture_manifest_sha256']), 'Unpinned dictation fixtures')
    accuracy = load_module('dictation_accuracy_fixture_guard', ROOT / 'tools/dictation-accuracy/accuracy.py')
    accuracy.load_fixtures(args.fixtures, manifest['fixture_manifest_sha256'])
    controller = args.source / 'packaging/dictation/dictation.py'
    require(controller.is_file() and not controller.is_symlink(), 'Built source lacks installed dictation controller')
    return manifest


def execute(argv, log, timeout, env, container):
    require(re.fullmatch('arctic-paired-dictation-[0-9a-f]{32}', container), 'Invalid owned VM container')
    with Path(log).open('xb') as output:
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            require(child.wait(timeout=timeout) == 0, 'Private dictation harness command failed')
        except BaseException:
            try:
                subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass  # Still attempt owned host-process cleanup if Docker is unresponsive.
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
            raise


def context(manifest, installation_id, phase, source, hardware_profile):
    image = manifest['image']
    return dict(schema='arctic-dictation-context-v2', phase=phase, hardware_profile=hardware_profile,
                source_sha=image['source_sha'], iso_sha256=image['sha256'], iso_bytes=image['bytes'],
                installation_id=installation_id, fixture_manifest_sha256=manifest['fixture_manifest_sha256'],
                checker_sha256=sha(HERE / 'guest_check.py'), contract_sha256=sha(HERE / 'contract.py'),
                accuracy_sha256=sha(ROOT / 'tools/dictation-accuracy/accuracy.py'),
                pins_sha256=sha(ROOT / 'tools/dictation-accuracy/pins.json'),
                child_exec_sha256=sha(source / 'packaging/dictation/child_exec.py'),
                controller_sha256=sha(source / 'packaging/dictation/dictation.py'))


def reports(vm, stage, ctx, evidence, contract, fixture_manifest=None):
    path = vm / ('serial-install.log' if stage == 'live' else 'serial-boot.log')
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 128 * 1024 * 1024,
            'Missing or oversized private dictation serial log')
    prefix = 'ARCTIC-DICTATION-QUALIFICATION '
    selected = [line[len(prefix):] for line in path.read_text(errors='strict').splitlines() if line.startswith(prefix)]
    require(len(selected) == 1 and len(selected[0]) < 2_000_000, 'Missing/duplicate/oversized dictation report')
    report = json.loads(selected[0])
    expected = dict(ctx, phase='live') if stage == 'live' else ctx
    # Preserve a structurally safe failed report for measured results and fixed
    # error codes; it still cannot satisfy the strict passing execution gate.
    contract.validate(report, expected, require_passed=False, fixture_manifest=fixture_manifest)
    name = ctx['phase'] + ('-live' if stage == 'live' else '') + '.json'
    write_json(evidence / name, report)
    contract.validate_report(report, expected, fixture_manifest=fixture_manifest)
    return dict(path=name, sha256=sha(evidence / name), phase=expected['phase'],
                installation_id=ctx['installation_id'], boot_id=report['boot_id'], status=report['status'])


def indicator(vm, ctx, evidence):
    receipt = vm / 'dictation-indicator-receipt.json'
    require(receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size < 16 * 1024,
            'Missing dictation indicator receipt')
    proof = json.loads(receipt.read_text())
    report = json.loads((evidence / (ctx['phase'] + '.json')).read_text())
    request = proof['request']
    require(set(proof) == {'request', 'path', 'sha256', 'iso_sha256', 'installation_id'}
            and set(request) == {'boot_id', 'installation_id', 'phase', 'desktop_uid', 'receiver_empty', 'capture_nonce'}
            and re.fullmatch('[0-9a-f]{32}', request['capture_nonce'])
            and request['phase'] == ctx['phase'] and request['installation_id'] == ctx['installation_id']
            and request['boot_id'] == report['boot_id'] and request['receiver_empty'] is True
            and proof['iso_sha256'] == ctx['iso_sha256'] and proof['installation_id'] == ctx['installation_id']
            and proof['path'] == 'dictation-indicator-' + ctx['phase'] + '.png'
            and any(gate['id'] == 'recording-status-published' and gate['status'] == 'passed'
                    and gate['observations'].get('sha256') == hashlib.sha256(request['capture_nonce'].encode()).hexdigest()
                    for gate in report['gates']), 'Indicator receipt/report binding differs')
    image = vm / proof['path']
    require(image.is_file() and not image.is_symlink() and image.stat().st_size < 4 * 1024 * 1024
            and sha(image) == proof['sha256'] and image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),
            'Indicator screenshot bytes differ')
    shutil.copyfile(image, evidence / image.name)
    return proof


def run(args):
    manifest = verify(args)
    require(Path('/dev/kvm').is_char_device(), 'KVM unavailable')
    subprocess.check_output(['docker', 'info', '--format', '{{.ServerVersion}}'], timeout=30)
    contract = load_module('dictation_image_contract', HERE / 'contract.py')
    private = args.evidence.parent / ('dictation-private-' + args.hardware_profile)
    require(not private.exists(), 'Private dictation output must be unused')
    private.mkdir(mode=0o700)
    state = dict(schema='arctic-dictation-execution-v2', hardware_profile=args.hardware_profile,
                 status='prepared', release_acceptance=False,
                 image=manifest['image'], execution_checker_head=os.environ['GITHUB_SHA'],
                 fixture_manifest_sha256=manifest['fixture_manifest_sha256'], reports={}, installations={}, indicators={})
    prepared = None
    def save():
        state['recorded_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(args.evidence / 'execution.json', state)
    def interrupted(signum, _):
        raise InterruptedError('Dictation qualification interrupted: ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        shutil.copyfile(args.fixtures / 'fixtures.json', args.evidence / 'fixtures.json')
        save()
        container = 'arctic-paired-dictation-' + uuid.uuid4().hex
        env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container)
        execute(['bash', str(ROOT / 'tools/performance/prepare-vm-tools.sh'), str(private)],
                private / 'provision.log', 20 * 60, env, container)
        prepared = (private / 'vm-prepared-image-id.txt').read_text().strip()
        require(re.fullmatch('(sha256:)?[0-9a-f]{64}', prepared), 'Unpinned VM tool image')
        state['vm_tool_image_id'] = prepared
        for kind in ('online', 'offline'):
            state['installations'][kind] = str(uuid.uuid4())
        phases = [('online-installed', 'online', 'all', 'online', 'offline', 85 * 60),
                  ('offline-installed', 'offline', 'all', 'offline', 'offline', 65 * 60),
                  ('recovery', 'offline', 'boot', 'offline', 'online', 40 * 60),
                  ('recovered-offline', 'offline', 'boot', 'offline', 'offline', 65 * 60)]
        for phase, kind, stage, install_network, boot_network, limit in phases:
            verify(args)  # Exact ISO/source are rehashed immediately before every VM phase.
            payload = private / ('payload-' + phase)
            payload.mkdir(mode=0o700)
            shutil.copytree(HERE, payload / 'dictation-qualification', ignore=shutil.ignore_patterns('__pycache__', 'test_*.py'))
            shutil.copytree(ROOT / 'tools/dictation-accuracy', payload / 'dictation-accuracy',
                            ignore=shutil.ignore_patterns('__pycache__', 'test_*.py'))
            shutil.copytree(args.fixtures, payload / 'dictation-fixtures')
            ctx = context(manifest, state['installations'][kind], phase, args.source, args.hardware_profile)
            write_json(payload / 'dictation-context.json', ctx)
            checker = payload / 'guest-check.py'
            checker.write_text('import os,sys\nos.execv("/usr/bin/python3", ["/usr/bin/python3", '
                               '"/run/t/dictation-qualification/guest_check.py", sys.argv[1], "--disposable-guest"])\n')
            container = 'arctic-paired-dictation-' + uuid.uuid4().hex
            env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container,
                       ARCTIC_FEDORA_IMAGE=prepared, ARCTIC_VM_TOOLS_PREPARED='1',
                       ARCTIC_DICTATION_BUNDLE=str(payload), ARCTIC_NATIVE_AUDIO_FIXTURE='1',
                       ARCTIC_NATIVE_DICTATION_CPU_PROFILE=args.hardware_profile)
            vm = private / ('vm-' + kind)
            # Reusing the same target and firmware variables proves offline recovery,
            # rather than substituting a second ready image or fresh disk.
            argv = ['bash', str(ROOT / 'tools/test-install.sh'), '--iso', str(args.inputs / 'iso' / manifest['image']['name']),
                    '--kvm', '--memory', '4096', '--smp', '2', '--boot-append', '', '--install-timeout', '2400',
                    '--stage', stage, '--install-network', install_network, '--boot-network', boot_network,
                    '--guest-check', str(checker), '--guest-check-interactive',
                    '--profile', str(args.source / 'profiles/ci/offline.toml'), '--out', str(vm)]
            state.update(status='running', current_phase=phase)
            save()
            errors = []
            try:
                execute(argv, private / (phase + '.log'), limit, env, container)
            except BaseException:
                errors.append('harness-failed')
            # Preserve structurally safe reports even when the collector's
            # nonzero exit correctly prevents acceptance.
            for observed_stage in (('live', 'installed') if stage == 'all' else ('installed',)):
                key = phase + '-live' if observed_stage == 'live' else phase
                try:
                    state['reports'][key] = reports(vm, observed_stage, ctx, args.evidence, contract,
                                                   args.fixtures / 'fixtures.json')
                except BaseException:
                    errors.append(key + '-failed-or-unrun')
            if phase in ('online-installed', 'recovered-offline'):
                try:
                    state['indicators'][phase] = indicator(vm, ctx, args.evidence)
                except BaseException:
                    errors.append(phase + '-indicator-failed-or-unrun')
            save()
            require(not errors, 'Exact image dictation phase failed')
        contract.validate_execution(state, {name: json.loads((args.evidence / item['path']).read_text())
                                           for name, item in state['reports'].items()},
                                    fixture_manifest=args.fixtures / 'fixtures.json')
        state.update(status='exact_image_dictation_online_offline_local_sessions_passed', current_phase=None)
        save()
    except BaseException:
        # Do not include arbitrary command stderr, journals or a transcript in public evidence.
        state.update(status='failed_or_unrun', error='Qualification failed; inspect private Actions harness logs')
        save()
        raise
    finally:
        if prepared:
            subprocess.run(['docker', 'image', 'rm', prepared], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'inputs', 'evidence', 'manifest', 'fixtures'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hardware-profile', choices=('small-v2', 'turbo-q5-v3'), required=True)
    args = parser.parse_args()
    for name in ('source', 'inputs', 'evidence', 'manifest', 'fixtures'):
        setattr(args, name, getattr(args, name).resolve())
    require(not args.evidence.exists(), 'Dictation evidence output must be unused')
    verify(args)
    args.evidence.mkdir(parents=True)
    run(args)


if __name__ == '__main__':
    main()
