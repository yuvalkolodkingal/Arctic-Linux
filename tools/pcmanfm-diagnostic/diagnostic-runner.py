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
BASE='92aa52c0ef324a2cb5ad4af9f0c47c5e8b273bec'
RECOVERY_BASE='ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
COMMON_SHA='0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
V4_LIBRARY_SHA='eb75ee7a0eded71b99f1742940e1ccbf5546f7203ccd62c57e2447c8dbd9a4ac'
BUNDLE_FILES={'diagnostic-runner.py','pcmanfm-controller.py','guest-pcmanfm-diagnostic.py','atspi-snapshot.py',
              'gtk-entry-control.py','bounded-launch.py','native_smoke.py','native-launcher.py','runtime-pins.json',
              'bootstrap-diagnostic.sh','prepare-diagnostic.py','test_diagnostic.py','README.md','frozen-base-pins.json',
              'original-h264-aac-1s.mp4','codec-fixture-manifest.json','security-collector.py','test_security_collector.py','bulk-channel.py','gtk-physical.py','test_v3.py'}
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
    require(env['GITHUB_SHA']!=BASE and env['GITHUB_RUN_ID'] not in ('37525639962','37535425230','37543716623','37548983381'),
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
    require(set(manifest.get('modes',{}))==EXECUTION_FILES,'exact execution file modes absent')
    for relative,mode in manifest['modes'].items():
        expected='100755' if relative=='tools/test-iso.sh' else '100644'
        require(mode==expected and subprocess.check_output(['git','-C',str(execution),'ls-tree',head,relative],text=True).split()[0]==mode,
                'actual Git execution mode differs: '+relative)
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
    security=report.get('security')
    require(isinstance(security,dict) and security.get('complete') is True and security.get('error') is None,
            'guest security interval incomplete: '+str(security)+'; primary guest errors: '+str(report.get('errors')))
    require(security.get('selinux')=='Enforcing' and security.get('audit')=={'enabled':1,'lost':0}
            and all(type(report['security']['audit'][k]) is int for k in ('enabled','lost'))
            and type(report['security']['observed_new_avcs']) is int and report['security']['observed_new_avcs']==0,'security evidence differs')
    checked_security(target,security,provenance['boot_id'])
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


def checked_bulk_report(serial,console,target,events,expected,R,V,expected_runtime):
    spec=importlib.util.spec_from_file_location('strict_bulk_record_parser',Path(__file__).parent/'bulk-channel.py')
    B=importlib.util.module_from_spec(spec);spec.loader.exec_module(B)
    rows=serial.splitlines()
    def marked(prefix):return [(index,B.strict_json(line[len(prefix):])) for index,line in enumerate(rows) if line.startswith(prefix)]
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
    require(B.strict_json((target/'report.json').read_text())==report,'transported/serial report differs')
    provenance=B.strict_json((target/'provenance.json').read_text())
    require(provenance['checker_sha256']==expected and provenance['native_source_sha256']==V.NATIVE_SOURCE_SHA
            and provenance['release_acceptance'] is False and 'rd.live.image' in provenance['cmdline'].split()
            and provenance['runtime_pins']==expected_runtime
            and type(provenance['desktop_uid']) is int and provenance['desktop_uid']>0
            and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',provenance['boot_id']),
            'actual live checker/source provenance differs')
    port=provenance.get('bulk_port',{})
    require(type(port) is dict and port.get('name')==port.get('sysfs_name')=='org.arctic.diagnostic.bulk'
            and port.get('named_path')=='/dev/virtio-ports/org.arctic.diagnostic.bulk'
            and isinstance(port.get('resolved_device'),str) and re.fullmatch(r'/dev/vport[0-9]+p[0-9]+',port['resolved_device'])
            and port.get('kind')=='character-device' and type(port.get('device_major')) is int and port['device_major']>0
            and type(port.get('device_minor')) is int and port['device_minor']>=0,
            'actual guest named bulk device provenance differs')
    launcher=provenance['launcher']
    console_rows=console.splitlines()
    gone,=[(i,B.strict_json(row[len('ARCTIC-NATIVE-LAUNCHER-GONE '):])) for i,row in enumerate(console_rows)
           if row.startswith('ARCTIC-NATIVE-LAUNCHER-GONE ')]
    # Raw console and bulk stream have separate origins; no synthetic merged serial.
    require(launcher==gone[1] and launcher['owned_launcher_gone'] is True
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
    security=report.get('security')
    require(isinstance(security,dict) and security.get('complete') is True and security.get('error') is None,
            'guest security interval incomplete: '+str(security)+'; primary guest errors: '+str(report.get('errors')))
    require(security.get('selinux')=='Enforcing' and security.get('audit')=={'enabled':1,'lost':0}
            and all(type(report['security']['audit'][k]) is int for k in ('enabled','lost'))
            and type(report['security']['observed_new_avcs']) is int and report['security']['observed_new_avcs']==0,'security evidence differs')
    checked_security(target,security,provenance['boot_id'])
    root=Path(report['evidence_root'])
    require(root.parent==Path('/tmp') and root.name.startswith('arctic-pcmanfm-diagnostic-')
            and B.strict_json((target/'transport-manifest.json').read_text())['evidence_root']==str(root),
            'diagnostic report/transport temp root differs')
    require([arm['name'] for arm in report['arms']]==['original-route','observed-route','gtk-warmup','gtk-no-warmup'],
            'bounded diagnostic arm order/completeness differs')
    for name in ('original-route','observed-route','gtk-warmup','gtk-no-warmup'):
        arm=B.strict_json((target/name/'arm-report.json').read_text())
        require(arm['name']==name and arm['cleanup']['only_proved_new_processes_signalled'] is True
                and arm['cleanup']['original_copied_configs_unchanged'] is True
                and arm['preservation_phase']=='final-cleanup-preservation'
                and type(arm['trace']['omitted_records']) is int and arm['trace']['omitted_records']==0
                and type(arm['trace']['bytes']) is int and 0<=arm['trace']['bytes']<=2*1024*1024,
                'arm owned cleanup/config/mandatory trace proof differs')
        trace=B.strict_json((target/name/'gui-trace-summary.json').read_text())
        require(trace['omitted_records']==arm['trace']['omitted_records']==0 and trace['bytes']==arm['trace']['bytes']
                and type(trace['omitted_records']) is int and type(trace['bytes']) is int
                and (target/name/'gui-trace.log').stat().st_size==trace['bytes'],
                'arm transported final trace counters differ')
    requests=[(i,B.strict_json(row[len('ARCTIC-PCMANFM-PHYSICAL-REQUEST '):])) for i,row in enumerate(console_rows)
              if row.startswith('ARCTIC-PCMANFM-PHYSICAL-REQUEST ')]
    acks=[e for e in events if e.get('event')=='physical-host-ack']
    physical=report['arms'][1]['physical']
    require(len(requests)==len(acks)<=1,'physical request/host acknowledgement unmatched/duplicate')
    if requests:
        request=requests[0][1];ack=acks[0]
        from_path=Path(__file__).parent/'pcmanfm-controller.py'
        spec=importlib.util.spec_from_file_location('diagnostic_physical_validator',from_path)
        C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
        C.physical_request(request)
        require(gone[0]<requests[0][0] and request==physical['request']
                and ack['nonce']==request['nonce'] and ack['boot_id']==request['boot_id']==provenance['boot_id']
                and ack['process']==request['process'] and ack['request_sha256']==C.canonical(request)
                and ack['exactly_one_press_release'] is True and ack['release_acceptance'] is False
                and ack['input_start_monotonic_seconds']>=ack['receipt_monotonic_seconds']
                and ack['input_start_monotonic_seconds']-ack['receipt_monotonic_seconds']<=2,
                'strict one-use physical host delivery proof differs')
        C.qmp_return(ack['response'])
        source=target/'observed-route/entry-09-physical-immediate-precondition.json'
        require(R.digest(source)==request['entry_evidence_sha256'],'physical immediate snapshot pin differs')
        entry_record=B.strict_json(source.read_text())
        require(entry_record['process']==request['process'] and entry_record['after']==request['client']
                and entry_record['snapshot']['entry']==request['entry']
                and entry_record['snapshot']['process']==request['process']
                and entry_record['snapshot']['status']=='observed'
                and len(entry_record['snapshot']['frames'])==1
                and entry_record['snapshot']['frames'][0] in request['entry']['ancestors'],
                'transported immediate entry/client/frame binding differs')
        physical_delivery='observed one-use strict QMP host delivery, separately paired; never virtual-route acceptance'
    else:require(physical['status']=='unrun','physical route lacks request/host proof')
    gtk_requests=[B.strict_json(row[len('ARCTIC-GTK-PHYSICAL-REQUEST '):]) for row in console_rows
                  if row.startswith('ARCTIC-GTK-PHYSICAL-REQUEST ')]
    gtk_acks=[e for e in events if e.get('event')=='gtk-physical-host-ack']
    require(len(gtk_requests)==len(gtk_acks)<=1,'GTK physical host delivery unmatched/duplicate')
    gtk=report['arms'][3].get('physical')
    require(type(gtk) is dict,'cold GTK separately labelled physical outcome missing')
    if gtk_requests:
        spec=importlib.util.spec_from_file_location('gtk_physical_proof',Path(__file__).parent/'gtk-physical.py')
        K=importlib.util.module_from_spec(spec);spec.loader.exec_module(K)
        request=K.validate(gtk_requests[0]);ack=gtk_acks[0]
        require(request==gtk['request'] and report['arms'][3]['status']=='own-entry-not-activated'
                and report['arms'][3].get('process')==request['process']
                and ack['nonce']==request['nonce'] and ack['boot_id']==request['boot_id']==provenance['boot_id']
                and ack['process']==request['process'] and ack['request_sha256']==K.canonical(request)
                and ack['exactly_one_press_release'] is True and ack['release_acceptance'] is False
                and all(type(ack.get(k)) in (int,float) and math.isfinite(ack[k]) for k in
                    ('input_start_monotonic_seconds','input_end_monotonic_seconds','receipt_monotonic_seconds'))
                and 0<=ack['input_start_monotonic_seconds']-ack['receipt_monotonic_seconds']<=2
                and ack['input_end_monotonic_seconds']>=ack['input_start_monotonic_seconds'],
                'GTK physical host nonce/boot/owned/timing proof differs')
        spec=importlib.util.spec_from_file_location('gtk_qmp_result',Path(__file__).parent/'pcmanfm-controller.py')
        C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C);C.qmp_return(ack['response'])
        source=target/'gtk-no-warmup/gtk-immediate-proof.json'
        require(R.digest(source)==request['widget_evidence_sha256'],'GTK physical immediate proof hash differs')
        raw=B.strict_json(source.read_text())
        require(raw['process']==request['process'] and raw['after']==request['client'] and raw['widget']==request['widget']
                and raw['before'].get('is_focused') is True and raw['before'].get('is_visible') is True
                and all(raw['before'].get(k)==raw['after'].get(k) for k in
                    ('id','pid','foreign_toplevel_id','appid','x','y','width','height','monitor','is_xwayland'))
                and request['widget']['uid']==provenance['desktop_uid'], 'GTK immediate transported ownership/widget differs')
        widget_file=target/'gtk-no-warmup/gtk-widget-snapshot.json'
        event_file=target/'gtk-no-warmup/gtk-events.log'
        require(B.strict_json(widget_file.read_text())==request['widget'], 'transported own widget snapshot differs')
        require(event_file.is_file() and event_file.stat().st_size<=2*1024*1024, 'required owned GTK events absent/unbounded')
        event_rows=[B.strict_json(row) for row in event_file.read_text().splitlines()]
        mapped=[row for row in event_rows if row.get('event')=='mapped']
        snapshots=[row for row in event_rows if row.get('event')=='owned-widget-snapshot']
        require(len(mapped)==1 and len(snapshots)==1
                and all(type(mapped[0].get(k)) is int and mapped[0][k]==request['widget'][k] for k in ('pid','start_ticks','uid'))
                and mapped[0].get('appid')==mapped[0].get('program_name')==request['appid']
                and mapped[0].get('backend')=='GdkWaylandDisplay'
                and snapshots[0].get('snapshot')==request['widget'], 'raw mapped GTK/widget owner proof differs')
        gtk_delivery='one strict separately labelled GTK QMP Return; never PCManFM or native acceptance'
    else:
        require(gtk.get('status')=='unrun','GTK physical outcome lacks actual host request')
    require(report['status']=='diagnostic-collected' and report['errors']==[]
            and end[1]['status']=='diagnostic-collected' and end[1]['error'] is None
            and end[1]['evidence_export_complete'] is True and end[1]['release_acceptance'] is False,
            'actual diagnostic collector/cleanup/preservation failed')
    return dict(report=report,provenance=provenance,files=copied,physical_host_delivery=locals().get('physical_delivery','unrun'),
                gtk_physical_host_delivery=locals().get('gtk_delivery','unrun'),
                scope='diagnosis only; original GUI/release gates remain open; added virtio data device perturbation')



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
            console_raw=(args.evidence/'boot/serial.log').read_bytes()
            state['console_observations']=console_observations(console_raw);save()
            console=console_raw.decode(errors='replace')
            # Preserve the old strict decoder's result on the untouched console; never repair/filter it.
            try:
                checked_report(console,args.evidence/'old-console-strict',events,R.digest(args.bundle/'guest-pcmanfm-diagnostic.py'),R,V,
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
            state['diagnostic']=checked_bulk_report(data.decode('utf-8',errors='strict'),console,
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
