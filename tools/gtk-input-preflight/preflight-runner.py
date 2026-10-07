#!/usr/bin/env python3
"""Explicit single fixed-ISO diagnostic, with unchanged v2 execution primitives."""
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
import subprocess
import sys
import uuid

sys.dont_write_bytecode=True
BASE='aee90aea1c8f6cb827f2044f62a6b47eff475145'
RECOVERY_BASE='ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
COMMON_SHA='0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
V4_LIBRARY_SHA='eb75ee7a0eded71b99f1742940e1ccbf5546f7203ccd62c57e2447c8dbd9a4ac'
OLD_RUNNER_SHA='bd7766788f918946d5ec88fa1b0cbfc20ba1df6cf7168ac4c19fb4f973cc0836'
BUNDLE_FILES={'extract-preflight.py','base-test-iso.sh','base-iso.yml','gtk-entry-control.py', 'prepare-integration.py', 'guest-preflight.py', 'generate-helper.py', 'security-collector.py', 'build-payload-pins.json', 'preflight-controller.py', 'candidate-rpm-receipts.json', 'bootstrap-diagnostic.sh', 'preflight-runner.py', 'README.md', 'arctic-wtype-sentinel', 'runtime-pins.json', 'candidate-input-libraries.json', 'native_smoke.py', 'checked-preflight.py', 'test_integration.py', 'original-wtype-v0.4.c', 'preflight-proof.py', 'test_preflight.py', 'arctic-proof.h', 'virtual-keyboard-unstable-v1.xml', 'core-provenance.json', 'input-collector.py','wire-input.py', 'frozen-base-pins.json', 'native-launcher.py', 'bulk-channel.py', 'sentinel-wtype.c', 'preflight-core.py'}
EXECUTION_FILES={'.github/workflows/iso.yml','tools/test-iso.sh','tools/lib/container.sh','tools/lib/vmtest.py','tools/native-functional-v4/native-runner-v4.py','tools/same-iso-recovery/vm-only-recovery-v2.py','tools/pcmanfm-diagnostic/diagnostic-runner.py',*('tools/gtk-input-preflight/'+n for n in BUNDLE_FILES)}
CHANGED_FILES={'.github/workflows/iso.yml','tools/test-iso.sh',*('tools/gtk-input-preflight/'+n for n in BUNDLE_FILES),'tools/gtk-input-preflight/execution-pins.json'}


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
    require(env.get('GTK_INPUT_PREFLIGHT_MODE')=='true' and all(env.get(name)=='false' for name in
            ('PCMANFM_DIAGNOSTIC_MODE','RECOVERY_MODE','NATIVE_SMOKE_MODE','NIX_REQUESTED','PERFORMANCE_REQUESTED','BOOT_TEST_REQUESTED')),
            'diagnostic must be selected alone')
    require(env['GITHUB_SHA']!=BASE and env['GITHUB_RUN_ID'] not in ('37525639962','37535425230','37543716623','37548983381','37557409933'),
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
    require(manifest['schema']=='arctic-gtk-preflight-execution-v1' and manifest['execution_base']==BASE
            and manifest['candidate_source']==R.SOURCE and manifest['recovery_base']==RECOVERY_BASE
            and set(manifest['files'])==EXECUTION_FILES,'diagnostic manifest file set/base differs')
    for relative,digest in manifest['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'unsafe execution pin path')
        R.pinned_file(execution/relative,digest)
    require(set(manifest.get('modes',{}))==EXECUTION_FILES,'exact execution file modes absent')
    for relative,mode in manifest['modes'].items():
        expected='100755' if relative in ('tools/test-iso.sh','tools/gtk-input-preflight/arctic-wtype-sentinel') else '100644'
        require(mode==expected and subprocess.check_output(['git','-C',str(execution),'ls-tree',head,relative],text=True).split()[0]==mode,
                'actual Git execution mode differs: '+relative)
    frozen=json.loads((args.bundle/'frozen-base-pins.json').read_text())
    require(frozen['base']==BASE and frozen['allowed_changed_existing']==['.github/workflows/iso.yml','tools/test-iso.sh'],
            'frozen predecessor scope differs')
    for relative,digest in frozen['files'].items():R.pinned_file(execution/relative,digest)
    return manifest


def proof(args,R):
    return dict(schema='arctic-gtk-preflight-execution-v1',candidate_source=R.SOURCE,execution_base=BASE,
                execution_head=os.environ['GITHUB_SHA'],iso_bytes=R.ISO_BYTES,iso_sha256=R.ISO_SHA256,
                checker_sha256=R.digest(args.bundle/'guest-preflight.py'),common_v2_sha256=COMMON_SHA,
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


def checked_security(target, value, boot):
    """Pair mandatory transported raw proofs with the successful guest summary."""
    spec=importlib.util.spec_from_file_location('security_evidence_parser',Path(__file__).parent/'security-collector.py')
    S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
    root=target/'security-interval'
    require(root.is_dir() and S.strict_json((root/'security-report.json').read_bytes())==value,
            'raw security summary missing/different')
    def unsigned(item,limit):return type(item) is int and 0<=item<=limit
    framing=(root/'small-commands.log').read_bytes()
    require(len(framing)<=S.SMALL_COMMAND_BYTES and framing.endswith(b'\n'), 'small security raw framing bound/EOF differs')
    small={}
    names={*(('state-%02d-%s'%(i,k)) for i in range(6) for k in ('selinux','audit')),'start-cursor','end-cursor'}
    for line in framing[:-1].split(b'\n'):
        row=S.strict_json(line)
        require(isinstance(row,dict) and set(row)=={'name','command','stdout_base64','stderr_base64'}
                and row['name'] in names and row['name'] not in small, 'small security raw name/duplicate/schema differs')
        data={}
        for stream in ('stdout','stderr'):
            encoded=row[stream+'_base64']
            require(isinstance(encoded,str), 'small security raw byte encoding differs')
            decoded=base64.b64decode(encoded,validate=True)
            require(base64.b64encode(decoded).decode()==encoded and len(decoded)<=65536,'small security raw encoding/bound differs')
            data[stream]=decoded
        small[row['name']]=(row['command'],data)
    require(set(small)==names, 'mandatory raw small security command absent')
    def command(name,argv,limit,timeout,raw=True):
        if raw:
            record,streams=small[name]
        else:
            record=S.strict_json((root/(name+'.json')).read_bytes())
            streams={'stderr':(root/(name+'.stderr.log')).read_bytes()}
        require(record['argv']==argv and record['complete'] is True and record['error'] is None
                and record['timed_out'] is False and type(record['exit_status']) is int and record['exit_status']==0
                and record['only_owned_child_reaped'] is True
                and record['stdout_bound_bytes']==limit and record['stderr_bound_bytes']==65536
                and record['timeout_seconds']==timeout
                and type(record.get('child_pid')) is int and record['child_pid']>1
                and all(type(record.get(k)) in (int,float) and math.isfinite(record[k]) for k in
                        ('monotonic_start_seconds','monotonic_end_seconds'))
                and 0<=record['monotonic_start_seconds']<=record['monotonic_end_seconds']
                and unsigned(record['stdout_observed_bytes'],limit)
                and type(record['stderr_observed_bytes']) is int and record['stderr_observed_bytes']==0
                and type(record['stderr_retained_bytes']) is int and record['stderr_retained_bytes']==0
                and re.fullmatch('[0-9a-f]{64}',record['stdout_observed_sha256'])
                and record['stderr_observed_sha256']==hashlib.sha256(b'').hexdigest()
                and streams['stderr']==b'', 'raw security command incomplete: '+name)
        if raw:
            data=streams['stdout']
            require(len(data)==record['stdout_observed_bytes'] and hashlib.sha256(data).hexdigest()==record['stdout_observed_sha256'],
                    'raw security command bytes/hash differ: '+name)
            return record,data
        return record,None
    states=S.strict_json((root/'states.json').read_bytes())
    require(states==value['states'] and len(states)==6,'all six initial/inter-arm/final raw security states absent')
    for index,state in enumerate(states):
        first,enforcing=command('state-%02d-selinux'%index,['getenforce'],65536,15)
        second,audit=command('state-%02d-audit'%index,['auditctl','-s'],65536,15)
        fields=re.findall(r'^(enabled|lost)\s+([0-9]+)\s*$',audit.decode('utf-8',errors='strict'),re.M)
        require(len(fields)==2 and dict(fields)=={'enabled':'1','lost':'0'}
                and enforcing==b'Enforcing\n' and state['commands']==[first,second]
                and state['selinux']=='Enforcing' and state['audit']=={'enabled':1,'lost':0}
                and all(type(state['audit'][k]) is int for k in ('enabled','lost')),
                'raw Enforcing/audit state differs')
    cursors={}
    for name in ('start','end'):
        _,data=command(name+'-cursor',['journalctl','-b','--no-pager','--all','-n','1','-o','json'],65536,15)
        require(data.endswith(b'\n') and data.count(b'\n')==1,'raw security cursor framing differs')
        row=S.strict_json(data[:-1]);require(row['_BOOT_ID']==boot.replace('-','') and isinstance(row['__CURSOR'],str) and row['__CURSOR'],
                                             'raw cursor/current boot differs')
        cursors[name]=row['__CURSOR']
    scan=value['journal'];limits=dict(scan_bytes=S.SCAN_BYTES,records=S.SCAN_RECORDS,newline_record_bytes=S.RECORD_BYTES,
                                    retained_trusted_or_denial_bytes=S.PRESERVE_BYTES,chunk_bytes=S.CHUNK_BYTES)
    require(scan['complete'] is True and scan['limits']==limits and scan['start_cursor']==cursors['start']
            and scan['end_cursor']==cursors['end'] and unsigned(scan['observed_records'],8192)
            and unsigned(scan['trusted_kernel_audit_records'],scan['observed_records'])
            and type(scan['matching_denial_records']) is int and scan['matching_denial_records']==0
            and type(scan['unfinished_record_bytes']) is int and scan['unfinished_record_bytes']==0
            and unsigned(scan['retained_bytes'],S.PRESERVE_BYTES)
            and (scan['fixed_end_cursor_seen'] is True or
                 (scan['no_new_records'] is True and scan['observed_records']==0 and cursors['start']==cursors['end'])),
            'complete current-boot journal/cursor counters differ')
    whole,_=command('whole-interval-command',['journalctl','-b','--no-pager','--all','--after-cursor',cursors['start'],'-o','json'],S.SCAN_BYTES,60,raw=False)
    require(scan['retained_bytes']<=whole['stdout_observed_bytes']
            and ((scan['observed_records']==0 and whole['stdout_observed_bytes']==0
                  and whole['stdout_observed_sha256']==hashlib.sha256(b'').hexdigest())
                 or (scan['observed_records']>0 and whole['stdout_observed_bytes']>=scan['observed_records'])),
            'whole stream byte/hash counters do not agree with parsed records')
    total=trusted=0
    seen=set()
    require(isinstance(scan['parts'],list) and len(scan['parts'])<=11,'required security chunk count differs')
    for index,part in enumerate(scan['parts']):
        require(part['path']=='trusted-or-denial-%02d.log'%index and unsigned(part['bytes'],S.CHUNK_BYTES),'unsafe security chunk/count')
        data=(root/part['path']).read_bytes();require(len(data)==part['bytes'] and hashlib.sha256(data).hexdigest()==part['sha256']
                                                   and data.endswith(b'\n'),'security raw chunk hash/framing differs')
        total+=len(data)
        for line in data[:-1].split(b'\n'):
            require(len(line)+1<=S.RECORD_BYTES,'raw security newline record bound differs')
            row=S.strict_json(line);messages=S.message_values(row.get('MESSAGE'))
            require(row['_BOOT_ID']==boot.replace('-','') and row['_TRANSPORT'] in ('audit','kernel')
                    and isinstance(row.get('__CURSOR'),str) and row['__CURSOR'] and row['__CURSOR']!=cursors['start']
                    and row['__CURSOR'] not in seen and not any(S.AVC.search(message) for message in messages),
                    'raw trusted security record/denial differs')
            seen.add(row['__CURSOR'])
            trusted+=1
    require(total==scan['retained_bytes'] and trusted==scan['trusted_kernel_audit_records'],'required trusted raw record preservation counters differ')
    audit=S.strict_json((root/'audit-interval.json').read_bytes())
    require(audit['complete'] is True and audit['limit_bytes']==S.AUDIT_BYTES and unsigned(audit['bytes'],S.AUDIT_BYTES)
            and type(audit['observed_matching_denials']) is int and audit['observed_matching_denials']==0,
            'complete audit-file interval metadata differs')
    if audit['after'] is None:
        require(audit['before'] is None and audit['bytes']==0,'audit-file disappearance differs')
    else:
        after=audit['after'];before=audit['before'];offset=before['offset'] if before else 0
        require(all(type(after[k]) is int and after[k]>=0 for k in ('device','inode','offset'))
                and (before is None or ((before['device'],before['inode'])==(after['device'],after['inode'])
                     and all(type(before[k]) is int and before[k]>=0 for k in ('device','inode','offset'))))
                and after['offset']-offset==audit['bytes'],'audit inode/device/offset continuity differs')
        data=(root/'audit-interval.log').read_bytes()
        require(len(data)==audit['bytes'] and hashlib.sha256(data).hexdigest()==audit['sha256']
                and (not data or data.endswith(b'\n')) and not S.AVC.search(data.decode(errors='replace')),
                'complete raw audit interval differs/contains denial')


def console_observations(data):
    """Keep raw kernel-looking anomaly offsets; never attest trusted provenance here."""
    require(type(data) is bytes and len(data)<=128*1024*1024,'raw console byte bound differs')
    pattern=re.compile(rb'watchdog: BUG: soft lockup|hardIRQ|softIRQ|BUG:')
    matches=[]
    for item in pattern.finditer(data):
        require(len(matches)<256,'raw console anomaly observation bound exceeded')
        left=data.rfind(b'\n',0,item.start())+1;right=data.find(b'\n',item.end())
        if right<0:right=len(data)
        raw=data[left:right]
        matches.append(dict(pattern=item.group().decode(),byte_offset=item.start(),line_start_byte=left,
            line_bytes=len(raw),line_sha256=hashlib.sha256(raw).hexdigest(),
            bounded_excerpt=raw[max(0,item.start()-left-120):min(len(raw),item.end()-left+400)].decode(errors='replace')))
    return dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),matches=matches,
                raw_console_unchanged=True,release_acceptance=False,
                scope='raw console pattern observations only; not IRQ ownership, causality, trusted AVC absence or post-export security qualification')


def run(args,R,V):
    verify(args,R,V);R.require_docker();require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    base=args.evidence.parent/'diagnostic-vm';require(not base.exists(),'VM output must be unused')
    state=dict(**proof(args,R),status='prepared');prepared=None
    def save():
        state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat();R.write_json(args.evidence/'execution.json',state)
    def interrupted(signum,_):raise InterruptedError('diagnostic interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        save();container='arctic-paired-gtk-preflight-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        R.execute(['bash',str(args.source/'tools/performance/prepare-vm-tools.sh'),str(args.evidence)],
                  args.evidence/'provision.log',20*60,args.source,env,container)
        prepared=(args.evidence/'vm-prepared-image-id.txt').read_text().strip()
        require(re.fullmatch('(sha256:)?[0-9a-f]{64}',prepared),'immutable tool-image ID absent')
        state.update(status='running_single_live_diagnostic',vm_tool_image_id=prepared);save()
        container='arctic-paired-gtk-preflight-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container,
                 ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1')
        argv=['bash',str(args.bundle.parents[1]/'tools/test-iso.sh'),'--iso',str(args.inputs/'iso'/R.ISO),
              '--kvm','--firmware','uefi','--mode','try','--memory','4096','--smp','2','--timeout','900','--debug',
              '--gtk-input-preflight',str(args.bundle),'--out',str(base)]
        state['immediate_pre_vm_verification']=verify_before_vm(args,R,V);save()
        errors=[]
        try:R.execute(argv,args.evidence/'diagnostic-harness.log',900,args.bundle.parents[1],env,container)
        except BaseException as exc:errors.append('harness: '+str(exc))
        finally:state['harness']=R.preserve_phase(base/'uefi-try',args.evidence,'boot');save()
        try:
            events=[json.loads(row) for row in (args.evidence/'boot/pcmanfm-host-events.log').read_text().splitlines()]
            console_raw=(args.evidence/'boot/serial.log').read_bytes()
            state['console_observations']=console_observations(console_raw);save()
            console=console_raw.decode(errors='replace')
            # Preserve the old strict decoder's result on the untouched console; never repair/filter it.
            try:
                old_decoder(args).checked_report(console,args.evidence/'old-console-strict',events,R.digest(args.bundle/'guest-preflight.py'),R,V,
                    json.loads((args.bundle/'runtime-pins.json').read_text()))
                state['console_strict_decode']=dict(status='unexpectedly-accepted',release_acceptance=False)
            except BaseException as exc:
                state['console_strict_decode']=dict(status='rejected',error=type(exc).__name__+': '+str(exc),
                    scope='unchanged console; payload intentionally uses separate bulk channel; no repaired serial')
            spec=importlib.util.spec_from_file_location('bulk_raw_validator',args.bundle/'bulk-channel.py')
            B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
            data=(args.evidence/'boot/bulk-evidence.log').read_bytes()
            channel=B.strict_json((args.evidence/'boot/bulk-channel.txt').read_bytes());B.validate(data,channel)
            state['bulk_channel']=channel
            state['diagnostic']=checker(args).checked(data.decode('utf-8',errors='strict'),console,
                args.evidence/'guest',events,R.digest(args.bundle/'guest-preflight.py'),R,V,
                json.loads((args.bundle/'runtime-pins.json').read_text()),checked_security)
        except BaseException as exc:errors.append('evidence: '+str(exc))
        require(not errors,'; '.join(errors));state['status']='finite_preflight_collected_native_qualification_open';save()
        require(state['diagnostic']['report']['status']=='preflight-passed','finite corrected GTK input preflight failed; original/native acceptance remains open')
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


def old_decoder(args):
    path=args.bundle.parent/'pcmanfm-diagnostic/diagnostic-runner.py'
    require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest()==OLD_RUNNER_SHA,'original strict decoder changed')
    spec=importlib.util.spec_from_file_location('frozen_original_console_decoder',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def checker(args):
    path=args.bundle/'checked-preflight.py'
    spec=importlib.util.spec_from_file_location('strict_finite_preflight_pairing',path)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

if __name__=='__main__':main()
