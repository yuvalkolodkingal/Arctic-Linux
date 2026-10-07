#!/usr/bin/env python3
"""Dedicated same-ISO Startup attestation diagnostic. Preparation is not dispatch approval."""
import argparse
import base64
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import uuid
import zlib

sys.dont_write_bytecode = True
BASE = 'ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
COMMON_SHA = '0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
SCHEMA = 'arctic-startup-execution-v1'
BUNDLE_FILES = {'attestation-runner-v1.py','attestation-driver-v1.py','attest-startup-v1.py','attest-host-v1.py',
                'guest-safe-collector-v1.py','original-safe-driver-v1.py','bootstrap-attest-v1.sh',
                'prepare-attestation-v1.py','prepare-safe-source.py','test_execution.py','test_attestation.py','test_attest_host.py','README.md',
                'base-test-iso.sh','base-iso.yml'}
EXECUTION_FILES = {'.github/workflows/iso.yml', 'tools/test-iso.sh', 'tools/lib/container.sh',
                   'tools/lib/vmtest.py', *('tools/startup-attestation/' + p for p in BUNDLE_FILES)}
CHANGED_FILES = EXECUTION_FILES - {'tools/lib/container.sh', 'tools/lib/vmtest.py'} | {
    'tools/startup-attestation/execution-pins-attestation-v1.json'}
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024


def require(value, message):
    if not value:
        raise RuntimeError(message)


def recovery(args):
    path = args.recovery_bundle / 'vm-only-recovery-v2.py'
    require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == COMMON_SHA,
            'Frozen v2 driver changed before import')
    spec = importlib.util.spec_from_file_location('startup_frozen_recovery_v2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_ci(env, R):
    # Translate only the declared mode for the original immutable CI validator.
    # No v2 function, constant, environment or manifest is patched.
    R.validate_ci(dict(env, RECOVERY_MODE='true'))
    require(env.get('STARTUP_ATTESTATION_MODE') == 'true' and env.get('RECOVERY_MODE') == 'false'
            and all(env.get(name) == 'false' for name in ('NATIVE_SMOKE_MODE','SAFE_DIAGNOSTIC_MODE','NIX_REQUESTED',
                    'PERFORMANCE_REQUESTED', 'BOOT_TEST_REQUESTED')), 'Startup attestation mode must be selected alone')
    require(env['GITHUB_SHA'] != BASE and env['GITHUB_RUN_ID'] != '37520174911',
            'Separate reviewed Startup attestation execution head/run required')


def verify_sources(args, R):
    # Preserve the exact original source and original v2 execution verification.
    R.verify_sources(args.source, args.recovery_bundle, BASE)
    execution = args.bundle.parents[1]
    head = subprocess.check_output(['git', '-C', str(execution), 'rev-parse', 'HEAD'], text=True).strip()
    require(head == os.environ['GITHUB_SHA'], 'Startup attestation execution checkout identity differs')
    require(not subprocess.check_output(['git', '-C', str(execution), 'status', '--porcelain'], text=True).strip(),
            'Dirty Startup attestation execution checkout')
    subprocess.run(['git', '-C', str(execution), 'merge-base', '--is-ancestor', BASE, head], check=True, timeout=30)
    changed = set(subprocess.check_output(['git', '-C', str(execution), 'diff', '--name-only', BASE, head], text=True).splitlines())
    require(changed <= CHANGED_FILES and 'tools/test-iso.sh' in changed and '.github/workflows/iso.yml' in changed,
            'Execution changes outside the reviewed Startup attestation-only file set')
    manifest = json.loads((args.bundle / 'execution-pins-attestation-v1.json').read_text())
    require(manifest['schema'] == SCHEMA and manifest['candidate_source'] == R.SOURCE
            and manifest['qualification_base'] == BASE and set(manifest['files']) == EXECUTION_FILES
            and set(manifest['modes']) == EXECUTION_FILES,
            'Startup attestation execution manifest identity/file set differs')
    for relative, expected in manifest['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Unsafe Startup attestation manifest path')
        R.pinned_file(execution / relative, expected)
        require(type(manifest['modes'][relative]) is int and stat.S_IMODE((execution/relative).lstat().st_mode)==manifest['modes'][relative],
                'Execution source file mode differs: '+relative)
    return manifest


def proof(args, R):
    return dict(schema=SCHEMA, candidate_source=R.SOURCE, qualification_base=BASE,
                execution_checker_head=os.environ['GITHUB_SHA'], common_v2_sha256=COMMON_SHA,
                collector_sha256=R.digest(args.bundle / 'attest-startup-v1.py'),
                original_security_collector_sha256=R.digest(args.bundle / 'guest-safe-collector-v1.py'),
                execution_manifest_sha256=R.digest(args.bundle / 'execution-pins-attestation-v1.json'),
                original_result_unchanged=True, release_acceptance=False, safe_visual_gate='open')


def preflight(args, R):
    validate_ci(os.environ, R); verify_sources(args, R)
    require(not args.inputs.exists() and not args.evidence.exists(), 'Inputs/evidence paths must be unused')
    args.evidence.mkdir(parents=True)
    docker = R.require_docker()
    require(Path('/dev/kvm').is_char_device(), 'KVM required; no TCG fallback or host chmod')
    require(shutil.disk_usage(args.evidence).free >= 20_000_000_000, 'At least 20 GB free required')
    run = R.api('actions/runs/' + str(R.ORIGINAL_RUN))
    pages = R.api('actions/runs/' + str(R.ORIGINAL_RUN) + '/jobs?filter=all&per_page=100', paginate=True)
    artifact = R.api('actions/artifacts/' + str(R.ARTIFACT_ID))
    original = R.validate_original(run, [j for p in pages for j in p['jobs']], artifact)
    value = proof(args, R)
    value.update(original_result=original, docker_server_version=docker,
                 artifact=dict(id=R.ARTIFACT_ID, name=R.ARTIFACT_NAME, original_run=R.ORIGINAL_RUN,
                               archive_bytes=R.ARCHIVE_BYTES, archive_digest=R.ARCHIVE_DIGEST))
    R.write_json(args.evidence / 'preflight.json', value)


def verify(args, R):
    validate_ci(os.environ, R); verify_sources(args, R)
    value = json.loads((args.evidence / 'preflight.json').read_text())
    require(all(value.get(k) == v for k, v in proof(args, R).items()), 'Preflight belongs to another execution')
    value['iso'] = R.verify_iso(args.inputs)
    R.write_json(args.evidence / 'verified-input.json', value)
    for relative in R.METADATA_PINS:
        target = args.evidence / 'input-metadata' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.inputs / relative, target)










def run(args, R):
    verify(args,R)
    docker=R.require_docker();require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    base=args.evidence.parent/'startup-attestation-vm';require(not base.exists(),'Fresh VM output collision')
    vm=base/'uefi-safe';container='arctic-paired-startup-'+uuid.uuid4().hex
    env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
    state=dict(**proof(args,R),status='running',docker_server_version=docker)
    def save():
        state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        R.write_json(args.evidence/'execution.json',state)
    def interrupted(signum,frame):raise InterruptedError('Attestation interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted);save()
    try:
        argv=['bash',str(args.bundle.parents[1]/'tools/test-iso.sh'),'--iso',str(args.inputs/'iso'/R.ISO),
              '--kvm','--firmware','uefi','--mode','safe','--memory','4096','--smp','2','--timeout','600',
              '--interval','60','--debug','--startup-attestation',str(args.bundle),'--out',str(base)]
        try:R.execute(argv,args.evidence/'attestation-harness.log',15*60,args.bundle.parents[1],env,container)
        finally:state['evidence']=R.preserve_phase(vm,args.evidence,'boot');save()
        require('attestation-toolchain.txt' in state['evidence'] and 'attestation-events.log' in state['evidence'],'Actual tools/events missing')
        raw=(args.evidence/'boot/serial.log').read_text(errors='replace')
        require(len(re.findall(r'^ARCTIC-STARTUP-BOOTSTRAP-BEGIN\r?$',raw,re.M))==1
                and len(re.findall(r'^ARCTIC-STARTUP-BOOTSTRAP-MOUNTED\r?$',raw,re.M))==1,'Actual bootstrap start/mount proof missing or duplicate')
        devices=re.findall(r'^ARCTIC-STARTUP-BOOTSTRAP-DEVICE=(/dev/sr[0-9]+)\r?$',raw,re.M)
        require(len(devices)==1,'Actual unique labelled device proof missing or duplicate')
        spec=importlib.util.spec_from_file_location('actual_startup_protocol',args.bundle/'attest-host-v1.py')
        H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
        state['guest']=H.extract(raw,args.evidence/'startup-telemetry',R.digest(args.bundle/'attest-startup-v1.py'))
        spec=importlib.util.spec_from_file_location('actual_startup_events',args.bundle/'attestation-driver-v1.py')
        D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)
        state['events']=D.validate_events(args.evidence/'boot/attestation-events.log')
        require(all(n in state['evidence'] for n in state['events']['capture_names']),'Event screenshot absent')
        state.update(status='startup-attestation-collected-unreviewed',exact_startup_target_bound=False,renderer='unobserved',active_scanout_pixels='unavailable');save()
    except BaseException as error:
        state.update(status='failed_or_unrun',error=type(error).__name__+': '+str(error));save();raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'verify', 'run'))
    for name in ('source', 'bundle', 'recovery-bundle', 'inputs', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('source', 'bundle', 'recovery_bundle', 'inputs', 'evidence'):
        setattr(args, name, getattr(args, name).resolve())
    R = recovery(args)
    try:
        globals()[args.phase](args, R)
    except BaseException as exc:
        if args.evidence.exists():
            R.write_json(args.evidence / ('blocked-' + args.phase + '.json'), dict(error=str(exc), release_acceptance=False,
                         safe_visual_gate='open', original_result_unchanged=True))
        raise


if __name__ == '__main__':
    main()
