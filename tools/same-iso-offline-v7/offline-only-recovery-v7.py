#!/usr/bin/env python3
"""Offline-only three-phase same-ISO runner. Preparation is not dispatch approval."""
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

HERE=Path(__file__).resolve().parent
BASE_SHA256='0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
OFFLINE_CHECKER_SHA256='967883e8467fb8bb5b5c6159707f8c9fd78d8d2850280344953c375df7ee3576'
base_path=HERE/'vm-only-recovery-v2.py'
if hashlib.sha256(base_path.read_bytes()).hexdigest()!=BASE_SHA256:
    raise RuntimeError('Frozen v2 primitive module changed')
spec=importlib.util.spec_from_file_location('offline_cycle_frozen_v2',base_path)
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)

LAYOUT={'.github/workflows/iso.yml','tools/lib/container.sh','tools/lib/vmtest.py',
    *('tools/same-iso-offline-v7/'+name for name in (
       'vm-only-recovery-v2.py','offline-only-recovery-v7.py','offline-update-cycle-v7.py',
       'test_offline_cycle_v7.py','README-v7.md','guest-check-offline-v1.py','README-v1.md',
       'review-ready-v1.json','independent-review-v1.json'))}
BRANCH='test/offline-cycle-same-iso-37507582946-v7'

def validate_ci(env):
    base.validate_ci(env)
    base.require(env.get('OFFLINE_CYCLE_RECOVERY_MODE')=='true'
        and env.get('SAME_ISO_RECOVERY_REQUESTED')=='false'
        and env.get('GITHUB_REF')=='refs/heads/'+BRANCH,
        'Only the separately reviewed offline-cycle branch and exclusive offline-only mode are allowed')

def verify_sources(args):
    for folder,wanted in ((args.source,base.SOURCE),(args.bundle.parents[1],os.environ['GITHUB_SHA'])):
        actual=subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()
        dirty=subprocess.check_output(['git','-C',str(folder),'status','--porcelain'],text=True).strip()
        base.require(actual==wanted and not dirty,'Source checkout identity/cleanliness mismatch')
    manifest=json.loads((args.bundle/'execution-pins-v7.json').read_text())
    base.require(manifest.get('schema')==7 and type(manifest.get('schema')) is int
        and manifest.get('candidate_source')==base.SOURCE and manifest.get('deployment_branch')==BRANCH
        and set(manifest.get('files',{}))==LAYOUT,'Exact v7 execution file manifest required')
    for relative,sha in manifest['files'].items():
        base.pinned_file(args.bundle.parents[1]/relative,sha)
    for relative,sha in base.SOURCE_PINS.items():base.pinned_file(args.source/relative,sha)
    for relative,sha in base.BUNDLE_PINS.items():base.pinned_file(args.bundle/relative,sha)
    base.pinned_file(args.bundle/'guest-check-offline-v1.py',OFFLINE_CHECKER_SHA256)
    # Independent reviewer supplies this only after source/control review.
    review=json.loads((args.bundle/'independent-review-v7.json').read_text())
    base.require(review.get('status')=='SOURCE_AND_HOST_CONTROLS_PASS_VM_UNRUN'
        and review.get('blocking_source_findings')==[] and review.get('all_controls_passed') is True
        and review.get('execution_manifest_sha256')==base.digest(args.bundle/'execution-pins-v7.json'),
        'Independent exact-v7 review evidence is absent or does not bind these execution pins')
    return manifest

def preflight(args):
    validate_ci(os.environ);verify_sources(args)
    base.require(not args.inputs.exists() and not args.evidence.exists(),'Fresh input/evidence paths required')
    args.evidence.mkdir(parents=True)
    docker_version=base.require_docker()
    base.require(Path('/dev/kvm').is_char_device(),'KVM required; no chmod or TCG fallback')
    base.require(shutil.disk_usage(args.evidence).free>=20_000_000_000,'At least 20 GB free required')
    run=base.api('actions/runs/'+str(base.ORIGINAL_RUN))
    pages=base.api('actions/runs/'+str(base.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    artifact=base.api('actions/artifacts/'+str(base.ARTIFACT_ID))
    original=base.validate_original(run,[job for page in pages for job in page['jobs']],artifact)
    base.write_json(args.evidence/'preflight.json',dict(original_result=original,
        original_outcomes_unchanged=True,execution_checker_head=os.environ['GITHUB_SHA'],
        execution_manifest_sha256=base.digest(args.bundle/'execution-pins-v7.json'),
        independent_review_sha256=base.digest(args.bundle/'independent-review-v7.json'),
        candidate_iso_source=base.SOURCE,checker_sha256=OFFLINE_CHECKER_SHA256,
        prior_offline_failure_run=37520174911,method='arctic-offline',docker_server_version=docker_version,
        recovery_run=int(os.environ['GITHUB_RUN_ID']),recovery_attempt=int(os.environ['GITHUB_RUN_ATTEMPT'])))

def verify(args):
    validate_ci(os.environ);verify_sources(args)
    proof=json.loads((args.evidence/'preflight.json').read_text())
    base.require(proof['execution_checker_head']==os.environ['GITHUB_SHA']
        and proof['checker_sha256']==OFFLINE_CHECKER_SHA256 and proof['method']=='arctic-offline'
        and proof['execution_manifest_sha256']==base.digest(args.bundle/'execution-pins-v7.json')
        and proof['independent_review_sha256']==base.digest(args.bundle/'independent-review-v7.json'),
        'Preflight belongs to another reviewed execution')
    proof['iso']=base.verify_iso(args.inputs)
    base.write_json(args.evidence/'verified-input.json',proof)
    for relative in base.METADATA_PINS:
        destination=args.evidence/'input-metadata'/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.inputs/relative,destination)

def acceptance_records(path):
    return [json.loads(line.split(' ',1)[1]) for line in path.read_text(errors='replace').splitlines()
            if line.startswith('ARCTIC-NIX-ACCEPTANCE ')]

def installed_success(vm,phase,bundle):
    base.probe_success(vm)
    rows=acceptance_records(vm/'serial-boot.log')
    base.require(rows and all(row.get('stage')=='installed' for row in rows),'Installed records absent/mixed')
    names=[row.get('check') for row in rows]
    base.require(len(names)==len(set(names)),'Duplicate installed check records')
    status={row['check']:row['status'] for row in rows}
    base.require(all(value=='passed' or name=='engine-version-change' and value=='unrun'
                     for name,value in status.items()),'Failed or unexpected unrun acceptance check')
    if phase=='first-boot':
        checker_spec=importlib.util.spec_from_file_location('frozen_offline_checker_required',bundle/'guest-check-offline-v1.py')
        checker=importlib.util.module_from_spec(checker_spec);checker_spec.loader.exec_module(checker)
        required=checker.recovery_required_checks('arctic-offline')|{'selinux','browser-acceptance-phase'}
        base.require(required.issubset(status),'Incomplete first-pass Nix/browser/trust/AVC/signed staging checks')
        live=acceptance_records(vm/'serial-install.log')
        base.require(live and all(row['stage']=='live' and row['status']=='passed' for row in live),
                     'Live acceptance incomplete or failed')
        live_names=[row.get('check') for row in live]
        live_required={'selinux','browser-acceptance-phase','non-chromium-browser','configured-browser-choice',
            'configured-files','configured-terminal','configured-editor','native-media-player',
            'native-archive-manager','native-archive-helpers','live-mutation-denied'}
        base.require(len(live_names)==len(set(live_names)) and live_required.issubset(live_names),
                     'Mandatory live checks missing or duplicated')
        text=(vm/'serial-install.log').read_text(errors='replace')
        for marker in ('ARCTIC-LIVE-SMOKE-EXIT','ARCTIC-INSTALL-EXIT'):
            base.require(re.findall(r'^'+marker+r'=(.*)$',text,re.M) in (['0'],['0\r']),
                         'Missing/duplicate/failed '+marker)
    elif phase=='third-boot':
        required={'selinux','browser-acceptance-phase','non-chromium-browser','configured-browser-choice',
            'configured-files','configured-terminal','configured-editor','native-media-player','native-archive-manager',
            'native-archive-helpers','daemon-socket-defaults','daemon-store-info','daemon','persistent-mount',
            'store-ownership','labels','mango-dodge-capability','desktop-customization','new-boot',
            'profile-persistence','hello-after-reboot','nix-engine-after-update','graphical-after-reboot',
            'signed-offline-update-completed','signed-offline-update-history','avc'}
        base.require(required.issubset(status),'Mandatory third-boot completion/history/Nix/browser/AVC checks missing')
    else:raise RuntimeError('Unknown mandatory installed phase')
    return dict(checks=status,meaning='Only this actual phase; original outcomes unchanged')

def cycle_success(vm,first_expected_sha):
    folder=vm/'offline-update-cycle'
    result=json.loads((folder/'cycle-result.json').read_text())
    spec=importlib.util.spec_from_file_location('offline_cycle_helper',HERE/'offline-update-cycle-v7.py')
    helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
    helper.validate_cycle(result)
    owner=dict(uid=os.getuid(),gid=os.getgid())
    base.require(result['disk_owner']==owner,'Cycle disk owner differs from the same-run host writer')
    for name in ('target.qcow2','OVMF_VARS.fd'):
        actual=(vm/name).stat();observed=result['disk_identity']['/out/'+name]
        base.require(actual.st_uid==owner['uid'] and actual.st_gid==owner['gid']
            and observed['uid']==actual.st_uid and observed['gid']==actual.st_gid
            and observed['mode']==actual.st_mode&0o7777 and not observed['mode']&0o022,
            'Actual retained disk/vars ownership differs from observed cycle input')
    base.require(result.get('status')=='guest_cycle_exit_observed_third_boot_required'
        and result.get('platform')=='QEMU_KVM' and result.get('network')=='restricted_offline'
        and result.get('transient_console_append')==helper.CONSOLE_APPEND,'Exact restricted observation failed')
    argv=result.get('actual_qemu_argv',[])
    base.require(argv==helper.qemu_argv(Path('/out/target.qcow2'),Path('/out/OVMF_VARS.fd'),
        Path('/out/offline-update-cycle'),Path('/usr/share/edk2/ovmf/OVMF_CODE.fd'),
        helper.serial_bindings(argv)[0],helper.serial_bindings(argv)[1]),
        'Actual cycle argv differs from KVM/no-reboot/restricted-network policy')
    events=[json.loads(line) for line in (folder/'qmp-events.jsonl').read_text().splitlines()]
    base.require(events==result['events'] and (folder/'serial-offline-cycle.log').is_file(),
                 'Actual raw QMP/serial evidence absent or differs')
    base.require(result['raw_serial_sha256']==base.digest(folder/'serial-offline-cycle.log')
        and result['raw_serial_bytes']==(folder/'serial-offline-cycle.log').stat().st_size,
        'Actual owned serial bytes differ from the helper evidence')
    base.require(result['first_install']['serial_install_sha256']==first_expected_sha
        and first_expected_sha==base.digest(vm/'serial-install.log')
        and result['unlock_prompt_evidence']['luks_uuid']==result['first_install']['luks_uuid'],
        'Update-cycle root differs from its passed same-run first install')
    first=helper.first_install_root(vm/'serial-install.log',result['first_install']['serial_install_sha256'])
    post=helper.serial_after_input((folder/'serial-offline-cycle.log').read_bytes(),first,
        result['serial_input_boundary'],final=True)
    base.require(first==result['first_install']
        and post['initial_prompt_evidence']==result['unlock_prompt_evidence']
        and post==result['serial_post_input_observation'],
        'Actual serial root/boot/request bytes differ from the declared input proof')
    return result

def preserve_cycle(vm,evidence):
    source=vm/'offline-update-cycle';destination=evidence/'offline-update-cycle'
    base.require(not destination.exists(),'Cycle evidence cannot be overwritten');destination.mkdir()
    copies={}
    if source.exists():
        for path in sorted(source.iterdir()):
            base.require(path.is_file() and not path.is_symlink() and path.suffix in ('.json','.jsonl','.log','.png','.txt'),
                         'Unexpected cycle evidence entry')
            shutil.copyfile(path,destination/path.name)
            copies[path.name]=dict(bytes=path.stat().st_size,sha256=base.digest(destination/path.name))
    base.write_json(destination/'manifest.json',copies)
    return copies

def cycle_command(args,vm,prepared,container):
    # No host network, privileged flag, policy mounts or guest data/checker CD.
    first=json.loads((args.evidence/'first-boot/manifest.json').read_text())['serial-install.log']['sha256']
    base.pinned_file(vm/'serial-install.log',first)
    return ['docker','run','--rm','--name',container,'--network','none','--device','/dev/kvm',
        '-v',str(vm)+':/out:rw','-v',str(args.source/'tools/lib')+':/arctic-lib:ro',
        '-v',str(args.bundle/'offline-update-cycle-v7.py')+':/arctic-cycle.py:ro',
        prepared,'python3','/arctic-cycle.py','--disk','/out/target.qcow2','--vars','/out/OVMF_VARS.fd',
        '--out','/out/offline-update-cycle','--timeout','5400',
        '--disk-owner-uid',str(os.getuid()),'--disk-owner-gid',str(os.getgid()),'--first-install-sha256',first]

def run(args):
    verify(args);docker_version=base.require_docker()
    base.require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    vm=args.evidence.parent/'vm';base.require(not vm.exists(),'Fresh same-run VM output required')
    checker=args.bundle/'guest-check-offline-v1.py';prepared=None;first_install_sha=None
    state=dict(status='prepared',method='arctic-offline',candidate_source=base.SOURCE,
        iso_sha256=base.ISO_SHA256,iso_bytes=base.ISO_BYTES,checker_sha256=OFFLINE_CHECKER_SHA256,
        execution_checker_head=os.environ['GITHUB_SHA'],docker_server_version=docker_version,
        coverage='OLD stable 2d5: signed staging, separate restricted update cycle, mandatory third boot/history',
        canonical_new_stable_qualification=False,original_outcomes_unchanged=True,phases=[])
    def save():
        state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        base.write_json(args.evidence/'execution.json',state)
    def interrupted(signum,frame):raise InterruptedError('Interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        save();container='arctic-paired-offline-v7-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        base.execute(['bash',str(args.source/'tools/performance/prepare-vm-tools.sh'),str(args.evidence)],
            args.evidence/'provision.log',20*60,args.source,env,container)
        prepared=(args.evidence/'vm-prepared-image-id.txt').read_text().strip()
        base.require(re.fullmatch(r'(sha256:)?[0-9a-f]{64}',prepared),'Invalid immutable VM tool image')
        state['vm_tool_image_id']=prepared
        common=['bash',str(args.source/'tools/test-install.sh'),'--kvm','--memory','4096','--smp','2',
            '--boot-append','','--boot-network','online','--guest-check',str(checker),
            '--profile',str(args.source/'profiles/ci/offline.toml'),'--out',str(vm)]
        for phase in ('first-boot','offline-update-cycle','third-boot'):
            base.pinned_file(checker,OFFLINE_CHECKER_SHA256)
            verify_sources(args)
            if phase=='first-boot':
                # Re-hash actual ISO/metadata after provisioning, immediately
                # before the first VM, rather than trusting the earlier label.
                base.verify_iso(args.inputs)
            container='arctic-paired-offline-v7-'+uuid.uuid4().hex
            env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_FEDORA_IMAGE=prepared,
                ARCTIC_VM_TOOLS_PREPARED='1',ARCTIC_VM_CONTAINER_NAME=container)
            if phase=='offline-update-cycle':
                argv=cycle_command(args,vm,prepared,container);limit=95*60
            else:
                argv=common+(['--iso',str(args.inputs/'iso'/base.ISO),'--install-timeout','2400']
                    if phase=='first-boot' else ['--stage','boot']);limit=100*60 if phase=='first-boot' else 60*60
            state['status']='running_'+phase;state['actual_host_argv']=argv;save()
            try:
                base.execute(argv,args.evidence/(phase+'-harness.log'),limit,args.source,env,container)
                proof=cycle_success(vm,first_install_sha) if phase=='offline-update-cycle' else installed_success(vm,phase,args.bundle)
                state['phases'].append(dict(phase=phase,status='passed_phase_only',proof=proof))
            finally:
                preserved=preserve_cycle(vm,args.evidence) if phase=='offline-update-cycle' else base.preserve_phase(vm,args.evidence,phase)
                state.setdefault('preserved_evidence',{})[phase]=preserved;save()
            if phase!='offline-update-cycle':
                base.require('vm-toolchain.txt' in preserved and 'serial-boot.log' in preserved,'Required actual phase evidence absent')
                if phase=='first-boot':
                    base.require('serial-install.log' in preserved,'Passed first install root evidence missing')
                    toolchain=preserved['vm-toolchain.txt']['sha256']
                    first_install_sha=preserved['serial-install.log']['sha256']
                    state['first_install_sha256']=first_install_sha;save()
                else:base.require(toolchain==preserved['vm-toolchain.txt']['sha256'],'VM toolchain changed across phases')
        base.require([phase['phase'] for phase in state['phases']]==['first-boot','offline-update-cycle','third-boot'],
                     'All three successful actual phases are mandatory')
        state['status']='old_stable_signed_offline_three_phase_vm_acceptance_passed';save()
    except BaseException as error:
        state.update(status='failed_or_unrun',error=str(error));save();raise
    finally:
        if prepared:subprocess.run(['docker','image','rm',prepared],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=('preflight','verify','run'))
    for name in ('source','bundle','inputs','evidence'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('source','bundle','inputs','evidence'):setattr(args,name,getattr(args,name).resolve())
    try:globals()[args.phase](args)
    except BaseException as error:
        if args.evidence.exists():base.write_json(args.evidence/('blocked-'+args.phase+'.json'),dict(error=str(error),
            qualification='Failed/unrun; original outcomes unchanged',original_run=base.ORIGINAL_RUN,method='arctic-offline'))
        raise

if __name__=='__main__':main()
