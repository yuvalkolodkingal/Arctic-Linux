#!/usr/bin/env python3
"""Explicit single fixed-ISO diagnostic, with unchanged v2 execution primitives."""
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
import sys
import uuid

sys.dont_write_bytecode=True
BASE='085fb11617a3d27960481d4dcb6f16631b723bd4'
RECOVERY_BASE='ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
COMMON_SHA='0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
V4_LIBRARY_SHA='eb75ee7a0eded71b99f1742940e1ccbf5546f7203ccd62c57e2447c8dbd9a4ac'
BUNDLE_FILES={'diagnostic-runner.py','pcmanfm-controller.py','guest-pcmanfm-diagnostic.py','atspi-snapshot.py',
              'gtk-entry-control.py','bounded-launch.py','native_smoke.py','native-launcher.py','runtime-pins.json',
              'bootstrap-diagnostic.sh','prepare-diagnostic.py','test_diagnostic.py','README.md','frozen-base-pins.json',
              'original-h264-aac-1s.mp4','codec-fixture-manifest.json'}
EXECUTION_FILES={'.github/workflows/iso.yml','tools/test-iso.sh','tools/lib/container.sh','tools/lib/vmtest.py',
                 'tools/native-functional-v4/native-runner-v4.py','tools/same-iso-recovery/vm-only-recovery-v2.py',
                 *('tools/pcmanfm-diagnostic/'+name for name in BUNDLE_FILES)}
CHANGED_FILES={'.github/workflows/iso.yml','tools/test-iso.sh',
               *('tools/pcmanfm-diagnostic/'+name for name in BUNDLE_FILES),
               'tools/pcmanfm-diagnostic/execution-pins.json'}


def require(value,message):
    if not value:raise RuntimeError(message)


def dependencies(args):
    file=args.bundle.parent/'native-functional-v4/native-runner-v4.py'
    require(file.is_file() and not file.is_symlink() and hashlib.sha256(file.read_bytes()).hexdigest()==V4_LIBRARY_SHA,
            'frozen v4 transport library changed')
    common=args.bundle.parent/'same-iso-recovery/vm-only-recovery-v2.py'
    require(common.is_file() and not common.is_symlink() and hashlib.sha256(common.read_bytes()).hexdigest()==COMMON_SHA,
            'frozen common execution driver changed')
    spec=importlib.util.spec_from_file_location('unchanged_native_v4_library',file)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.R,module


def validate_ci(env,R):
    R.validate_ci(dict(env,RECOVERY_MODE='true'))
    require(env.get('PCMANFM_DIAGNOSTIC_MODE')=='true' and all(env.get(name)=='false' for name in
            ('RECOVERY_MODE','NATIVE_SMOKE_MODE','NIX_REQUESTED','PERFORMANCE_REQUESTED','BOOT_TEST_REQUESTED')),
            'diagnostic must be selected alone')
    require(env['GITHUB_SHA']!=BASE and env['GITHUB_RUN_ID'] not in ('37525639962','37535425230'),
            'separate reviewed diagnostic head/run required')


def verify_sources(args,R):
    # This original routine verifies candidate source and the separate clean ae55 recovery checkout verbatim.
    R.verify_sources(args.source,args.recovery_bundle,RECOVERY_BASE)
    execution=args.bundle.parents[1]
    head=subprocess.check_output(['git','-C',str(execution),'rev-parse','HEAD'],text=True).strip()
    require(head==os.environ['GITHUB_SHA'] and not subprocess.check_output(
        ['git','-C',str(execution),'status','--porcelain'],text=True).strip(),'dirty/wrong diagnostic execution checkout')
    subprocess.run(['git','-C',str(execution),'merge-base','--is-ancestor',BASE,head],check=True,timeout=30)
    changed=set(subprocess.check_output(['git','-C',str(execution),'diff','--name-only',BASE,head],text=True).splitlines())
    require(changed<=CHANGED_FILES and {'.github/workflows/iso.yml','tools/test-iso.sh'}<=changed,
            'diagnostic changes outside reviewed default-off test file set')
    manifest=json.loads((args.bundle/'execution-pins.json').read_text())
    require(manifest['schema']=='arctic-pcmanfm-execution-v1' and manifest['execution_base']==BASE
            and manifest['candidate_source']==R.SOURCE and manifest['recovery_base']==RECOVERY_BASE
            and set(manifest['files'])==EXECUTION_FILES,'diagnostic manifest file set/base differs')
    for relative,digest in manifest['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'unsafe execution pin path')
        R.pinned_file(execution/relative,digest)
    frozen=json.loads((args.bundle/'frozen-base-pins.json').read_text())
    require(frozen['base']==BASE and frozen['allowed_changed_existing']==['.github/workflows/iso.yml','tools/test-iso.sh'],
            'frozen predecessor scope differs')
    for relative,digest in frozen['files'].items():R.pinned_file(execution/relative,digest)
    return manifest


def proof(args,R):
    return dict(schema='arctic-pcmanfm-execution-v1',candidate_source=R.SOURCE,execution_base=BASE,
                execution_head=os.environ['GITHUB_SHA'],iso_bytes=R.ISO_BYTES,iso_sha256=R.ISO_SHA256,
                checker_sha256=R.digest(args.bundle/'guest-pcmanfm-diagnostic.py'),common_v2_sha256=COMMON_SHA,
                frozen_v4_transport_sha256=V4_LIBRARY_SHA,execution_manifest_sha256=R.digest(args.bundle/'execution-pins.json'),
                original_native_run=37535425230,original_failure_unchanged=True,release_acceptance=False)


def preflight(args,R,V):
    validate_ci(os.environ,R);verify_sources(args,R)
    require(not args.inputs.exists() and not args.evidence.exists(),'fresh inputs/evidence paths required')
    args.evidence.mkdir(parents=True)
    docker=R.require_docker();require(Path('/dev/kvm').is_char_device(),'KVM required; no host changes or TCG fallback')
    require(shutil.disk_usage(args.evidence).free>=20_000_000_000,'20 GB free required')
    run=R.api('actions/runs/'+str(R.ORIGINAL_RUN))
    pages=R.api('actions/runs/'+str(R.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    artifact=R.api('actions/artifacts/'+str(R.ARTIFACT_ID))
    value=proof(args,R);value['original_result']=R.validate_original(run,[job for page in pages for job in page['jobs']],artifact)
    value['docker_server_version']=docker;R.write_json(args.evidence/'preflight.json',value)


def verify(args,R,V):
    validate_ci(os.environ,R);verify_sources(args,R)
    value=json.loads((args.evidence/'preflight.json').read_text())
    for name,item in proof(args,R).items():require(value[name]==item,'preflight source identity differs: '+name)
    value['iso']=R.verify_iso(args.inputs);R.write_json(args.evidence/'verified-input.json',value)
    for relative in R.METADATA_PINS:
        target=args.evidence/'input-metadata'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.inputs/relative,target)


def verify_before_vm(args,R,V):
    # Provisioning is bounded but can last 20 minutes. Revalidate actual inputs afterwards.
    validate_ci(os.environ,R)
    manifest=verify_sources(args,R)
    actual=R.verify_iso(args.inputs)
    previous=json.loads((args.evidence/'verified-input.json').read_text())
    for name,item in proof(args,R).items():require(previous[name]==item,'pre-VM source identity differs: '+name)
    require(actual==previous['iso'],'pre-VM actual ISO/metadata differs from verified input')
    return dict(status='actual-source-iso-and-metadata-reverified-immediately-before-vm',iso=actual,
                execution_manifest_sha256=R.digest(args.bundle/'execution-pins.json'),
                source_pins=len(manifest['files']),release_acceptance=False)


def checked_report(serial,target,events,expected,R,V,expected_runtime):
    rows=serial.splitlines()
    def marked(prefix):return [(index,json.loads(line[len(prefix):])) for index,line in enumerate(rows) if line.startswith(prefix)]
    begin,=marked('ARCTIC-PCMANFM-DIAG-BEGIN ');end,=marked('ARCTIC-PCMANFM-DIAG-END ')
    reports=marked('ARCTIC-PCMANFM-DIAG-REPORT ')
    require(begin[0]<end[0] and begin[1]['checker_sha256']==expected and begin[1]['release_acceptance'] is False,
            'diagnostic source/marker order differs')
    block=rows[begin[0]+1:end[0]]
    chunks=[i for i,row in enumerate(rows) if row.startswith('ARCTIC-NATIVE-EVIDENCE-CHUNK ')]
    manifests=marked('ARCTIC-NATIVE-EVIDENCE-MANIFEST ')
    require(len(manifests)==1 and all(begin[0]<i<manifests[0][0]<end[0] for i in chunks)
            and len(reports)==1 and begin[0]<reports[0][0]<manifests[0][0]<end[0],
            'transport/report order or unknown outer chunks differ')
    copied=V.extract_evidence(block,'live',target) # Unchanged reviewed zlib/hash/path/bounds implementation.
    report=reports[0][1]
    require(json.loads((target/'report.json').read_text())==report,'transported/serial report differs')
    provenance=json.loads((target/'provenance.json').read_text())
    require(provenance['checker_sha256']==expected and provenance['native_source_sha256']==V.NATIVE_SOURCE_SHA
            and provenance['release_acceptance'] is False and 'rd.live.image' in provenance['cmdline'].split()
            and provenance['runtime_pins']==expected_runtime
            and type(provenance['desktop_uid']) is int and provenance['desktop_uid']>0
            and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',provenance['boot_id']),
            'actual live checker/source provenance differs')
    launcher=provenance['launcher']
    gone,=marked('ARCTIC-NATIVE-LAUNCHER-GONE ')
    require(gone[0]<begin[0] and launcher==gone[1] and launcher['owned_launcher_gone'] is True
            and launcher['launcher_sha256']==V.LAUNCHER_SHA and launcher['boot_id']==provenance['boot_id']
            and launcher['foot']['uid']==launcher['shell']['uid']==provenance['desktop_uid']>0
            and launcher['foot']['executable']=='/usr/bin/foot' and launcher['probe']['uid']==0,
            'owned native launcher same-boot/UID disappearance differs')
    require(launcher['schema']=='arctic-native-launcher-v1' and launcher['stage']=='live','launcher schema/stage differs')
    for name in ('shell','foot','probe'):
        item=launcher[name]
        require(all(type(item[k]) is int and item[k]>0 for k in ('pid','start_ticks'))
                and type(item['uid']) is int and item['uid']>=0
                and re.fullmatch('[0-9a-f]{64}',item['executable_sha256']),'launcher actual process identity differs')
    require(Path(launcher['shell']['executable']).name in {'bash','fish','zsh','dash','sh'},'launcher shell differs')
    require(report['schema']=='arctic-pcmanfm-diagnostic-v1' and report['original_run']==37535425230
            and report['original_status']=='failed-7-of-8-live' and report['release_acceptance'] is False,
            'diagnostic changed original acceptance claim')
    require(report['security']['selinux']=='Enforcing' and report['security']['audit']=={'enabled':1,'lost':0}
            and all(type(report['security']['audit'][k]) is int for k in ('enabled','lost'))
            and type(report['security']['observed_new_avcs']) is int and report['security']['observed_new_avcs']==0,'security evidence differs')
    root=Path(report['evidence_root'])
    require(root.parent==Path('/tmp') and root.name.startswith('arctic-pcmanfm-diagnostic-')
            and json.loads((target/'transport-manifest.json').read_text())['evidence_root']==str(root),
            'diagnostic report/transport temp root differs')
    require([arm['name'] for arm in report['arms']]==['original-route','observed-route','gtk-warmup','gtk-no-warmup'],
            'bounded diagnostic arm order/completeness differs')
    for name in ('original-route','observed-route','gtk-warmup','gtk-no-warmup'):
        arm=json.loads((target/name/'arm-report.json').read_text())
        require(arm['name']==name and arm['cleanup']['only_proved_new_processes_signalled'] is True
                and arm['cleanup']['original_copied_configs_unchanged'] is True
                and arm['preservation_phase']=='final-cleanup-preservation'
                and type(arm['trace']['omitted_records']) is int and arm['trace']['omitted_records']==0
                and type(arm['trace']['bytes']) is int and 0<=arm['trace']['bytes']<=2*1024*1024,
                'arm owned cleanup/config/mandatory trace proof differs')
        trace=json.loads((target/name/'gui-trace-summary.json').read_text())
        require(trace['omitted_records']==arm['trace']['omitted_records']==0 and trace['bytes']==arm['trace']['bytes']
                and type(trace['omitted_records']) is int and type(trace['bytes']) is int
                and (target/name/'gui-trace.log').stat().st_size==trace['bytes'],
                'arm transported final trace counters differ')
    requests=marked('ARCTIC-PCMANFM-PHYSICAL-REQUEST ')
    acks=[e for e in events if e.get('event')=='physical-host-ack']
    physical=report['arms'][1]['physical']
    require(len(requests)==len(acks)<=1,'physical request/host acknowledgement unmatched/duplicate')
    if requests:
        request=requests[0][1];ack=acks[0]
        from_path=Path(__file__).parent/'pcmanfm-controller.py'
        spec=importlib.util.spec_from_file_location('diagnostic_physical_validator',from_path)
        C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
        C.physical_request(request)
        require(begin[0]<requests[0][0]<reports[0][0] and request==physical['request']
                and ack['nonce']==request['nonce'] and ack['boot_id']==request['boot_id']==provenance['boot_id']
                and ack['process']==request['process'] and ack['request_sha256']==C.canonical(request)
                and ack['exactly_one_press_release'] is True and ack['release_acceptance'] is False
                and ack['input_start_monotonic_seconds']>=ack['receipt_monotonic_seconds']
                and ack['input_start_monotonic_seconds']-ack['receipt_monotonic_seconds']<=2,
                'strict one-use physical host delivery proof differs')
        C.qmp_return(ack['response'])
        source=target/'observed-route/entry-09-physical-immediate-precondition.json'
        require(R.digest(source)==request['entry_evidence_sha256'],'physical immediate snapshot pin differs')
        entry_record=json.loads(source.read_text())
        require(entry_record['process']==request['process'] and entry_record['after']==request['client']
                and entry_record['snapshot']['entry']==request['entry']
                and entry_record['snapshot']['process']==request['process']
                and entry_record['snapshot']['status']=='observed'
                and len(entry_record['snapshot']['frames'])==1
                and entry_record['snapshot']['frames'][0] in request['entry']['ancestors'],
                'transported immediate entry/client/frame binding differs')
        physical_delivery='observed one-use strict QMP host delivery, separately paired; never virtual-route acceptance'
    else:require(physical['status']=='unrun','physical route lacks request/host proof')
    require(report['status']=='diagnostic-collected' and report['errors']==[]
            and end[1]['status']=='diagnostic-collected' and end[1]['error'] is None
            and end[1]['evidence_export_complete'] is True and end[1]['release_acceptance'] is False,
            'actual diagnostic collector/cleanup/preservation failed')
    return dict(report=report,provenance=provenance,files=copied,physical_host_delivery=locals().get('physical_delivery','unrun'),
                scope='diagnosis only; original GUI/release gates remain open')


def run(args,R,V):
    verify(args,R,V);R.require_docker();require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    base=args.evidence.parent/'diagnostic-vm';require(not base.exists(),'VM output must be unused')
    state=dict(**proof(args,R),status='prepared');prepared=None
    def save():
        state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();R.write_json(args.evidence/'execution.json',state)
    def interrupted(signum,_):raise InterruptedError('diagnostic interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        save();container='arctic-paired-pcmanfm-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        R.execute(['bash',str(args.source/'tools/performance/prepare-vm-tools.sh'),str(args.evidence)],
                  args.evidence/'provision.log',20*60,args.source,env,container)
        prepared=(args.evidence/'vm-prepared-image-id.txt').read_text().strip()
        require(re.fullmatch('(sha256:)?[0-9a-f]{64}',prepared),'immutable tool-image ID absent')
        state.update(status='running_single_live_diagnostic',vm_tool_image_id=prepared);save()
        container='arctic-paired-pcmanfm-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container,
                 ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1')
        argv=['bash',str(args.bundle.parents[1]/'tools/test-iso.sh'),'--iso',str(args.inputs/'iso'/R.ISO),
              '--kvm','--firmware','uefi','--mode','try','--memory','4096','--smp','2','--timeout','900','--debug',
              '--pcmanfm-diagnostic',str(args.bundle),'--out',str(base)]
        state['immediate_pre_vm_verification']=verify_before_vm(args,R,V);save()
        errors=[]
        try:R.execute(argv,args.evidence/'diagnostic-harness.log',900,args.bundle.parents[1],env,container)
        except BaseException as exc:errors.append('harness: '+str(exc))
        finally:state['harness']=R.preserve_phase(base/'uefi-try',args.evidence,'boot');save()
        try:
            events=[json.loads(row) for row in (args.evidence/'boot/pcmanfm-host-events.log').read_text().splitlines()]
            state['diagnostic']=checked_report((args.evidence/'boot/serial.log').read_text(errors='replace'),
                args.evidence/'guest',events,R.digest(args.bundle/'guest-pcmanfm-diagnostic.py'),R,V,
                json.loads((args.bundle/'runtime-pins.json').read_text()))
        except BaseException as exc:errors.append('evidence: '+str(exc))
        require(not errors,'; '.join(errors));state['status']='diagnostic_collected_original_qualification_open';save()
    except BaseException as exc:state.update(status='failed_or_unrun',error=str(exc));save();raise
    finally:
        if prepared:subprocess.run(['docker','image','rm',prepared],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('phase',choices=('preflight','verify','run'))
    for name in ('source','bundle','recovery-bundle','inputs','evidence'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('source','bundle','recovery_bundle','inputs','evidence'):setattr(args,name,getattr(args,name).resolve())
    R,V=dependencies(args)
    try:globals()[args.phase](args,R,V)
    except BaseException as exc:
        if args.evidence.exists():R.write_json(args.evidence/('blocked-'+args.phase+'.json'),dict(error=str(exc),release_acceptance=False))
        raise


if __name__=='__main__':main()
