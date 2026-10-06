#!/usr/bin/env python3
"""Dedicated fixed-image native smoke; test preparation is not dispatch approval."""
import argparse
import base64
import binascii
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
import wave
import zlib

HERE = Path(__file__).resolve().parent
COMMON_SHA = '0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
COMMON_FILE = HERE.parent/'same-iso-recovery/vm-only-recovery-v2.py'
if hashlib.sha256(COMMON_FILE.read_bytes()).hexdigest() != COMMON_SHA:
    raise RuntimeError('Frozen common v2 driver changed before import')
_SPEC = importlib.util.spec_from_file_location('frozen_recovery_v2',COMMON_FILE)
R = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(R)

QUALIFICATION_BASE = 'ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
NATIVE_SOURCE_SHA = '2bf89d4771baad6c948c15d38379393c8c57488ff497a2c68e398f360b2d0489'
NATIVE_MANIFEST_SHA = 'ee488d7eaab28e5ff4c70ef25e7e9c8fb6d40971680c80d1ccf83490e6007413'
NATIVE_REVIEW_SHA = '8f4738796615750ceaa6ee60688f1a9cbc0d781fdf9abdcf2cba0777ca3a7988'
CHECKERS = {'native-functional': ('guest-check-native-v3.py','901b5ec41f37b5f62958492930f158f386fe63772f2800ba6ab3b1e50a5ac5b6')}
LAUNCHER_SHA = 'e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
GATES = {'fresh-defaults-and-isolation','archive-content-roundtrips','actual-role-file-manager-terminal-editor',
         'open-codec-content-and-player-state','portal-and-accessibility-reachability',
         'owned-process-cleanup-config-preservation','selinux-and-new-avcs','open-codec-lossless-command-decode'}
MAX_FILE = 4*1024*1024
MAX_TOTAL = 16*1024*1024
EXECUTION_FILES = {'.github/workflows/iso.yml','tools/test-install.sh','tools/test-iso.sh',
                   'tools/lib/container.sh','tools/lib/vmtest.py',
                   *('tools/native-functional-runner/'+name for name in (
                       'native-runner-v3.py','guest-check-native-v3.py','prepare-adapter-v3.py','adapter-parity-v3.json',
                       'native_smoke.py','native-manifest.json','native-independent-review.json','frozen-v2-pins-v3.json',
                       'test-install-native-audio-v3.patch','native-launcher-v3.py','test_native_runner_v3.py','README-v3.md'))}


def validate_ci(env):
    # Reuse the frozen supported-CI/Docker/identity checks without altering v2.
    translated = dict(env,RECOVERY_MODE='true')
    R.validate_ci(translated)
    R.require(env.get('NATIVE_SMOKE_MODE')=='true' and env.get('RECOVERY_MODE')=='false',
              'Native smoke must be selected alone; recovery/build modes must be off')
    R.require(env['GITHUB_SHA'] != QUALIFICATION_BASE and env['GITHUB_RUN_ID'] != '37520174911',
              'A separate native qualification execution head/run is mandatory')


def verify_sources(args):
    source, execution = args.source,args.bundle.parents[1]
    for folder,wanted in ((source,R.SOURCE),(execution,os.environ['GITHUB_SHA'])):
        actual=subprocess.check_output(['git','-C',str(folder),'rev-parse','HEAD'],text=True).strip()
        R.require(actual==wanted,'Source/execution head differs: '+str(folder))
        R.require(not subprocess.check_output(['git','-C',str(folder),'status','--porcelain'],text=True).strip(),
                  'Dirty source/execution checkout: '+str(folder))
    subprocess.run(['git','-C',str(execution),'merge-base','--is-ancestor',QUALIFICATION_BASE,os.environ['GITHUB_SHA']],
                   check=True,timeout=30)
    for relative,sha in R.SOURCE_PINS.items():R.pinned_file(source/relative,sha)
    manifest=json.loads((args.bundle/'execution-pins-v3.json').read_text())
    R.require(type(manifest.get('schema')) is int and manifest['schema']==3
              and manifest['candidate_source']==R.SOURCE and manifest['qualification_base']==QUALIFICATION_BASE
              and set(manifest['files'])==EXECUTION_FILES,'Native execution manifest identity/file set differs')
    for relative,sha in manifest['files'].items():
        R.require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,'Unsafe native execution path')
        R.pinned_file(execution/relative,sha)
    # All existing v2 files remain byte-identical, including its unchanged manifest.
    frozen=json.loads((args.bundle/'frozen-v2-pins-v3.json').read_text())
    R.require(frozen['qualification_base']==QUALIFICATION_BASE,'Frozen v2 base differs')
    for relative,sha in frozen['files'].items():R.pinned_file(execution/relative,sha)
    R.pinned_file(args.bundle/'native_smoke.py',NATIVE_SOURCE_SHA)
    R.pinned_file(args.bundle/'native-manifest.json',NATIVE_MANIFEST_SHA)
    R.pinned_file(args.bundle/'native-independent-review.json',NATIVE_REVIEW_SHA)
    name,sha=CHECKERS['native-functional'];R.pinned_file(args.bundle/name,sha)
    R.pinned_file(args.bundle/'native-launcher-v3.py',LAUNCHER_SHA)
    parity=json.loads((args.bundle/'adapter-parity-v3.json').read_text())
    R.require(parity['native_source_sha256']==NATIVE_SOURCE_SHA and parity['adapter_sha256']==sha
              and parity['all_other_top_level_bytes_and_ast_equal'] is True
              and parity['all_other_source_bytes_equal'] is True and parity['sole_changed_top_level_function']=='main',
              'Standalone adapter parity proof differs')
    return manifest


def checker_proof():
    name,sha=CHECKERS['native-functional']
    return dict(method='native-functional',name=name,sha256=sha,native_source_sha256=NATIVE_SOURCE_SHA,
                native_review_sha256=NATIVE_REVIEW_SHA,common_v2_sha256=COMMON_SHA,scope='limited native live/first-installed functional smoke')


def preflight(args):
    validate_ci(os.environ);verify_sources(args)
    R.require(not args.inputs.exists() and not args.evidence.exists(),'Fresh inputs/evidence paths must be unused')
    args.evidence.mkdir(parents=True)
    docker=R.require_docker()
    R.require(Path('/dev/kvm').is_char_device(),'Native KVM required; no TCG fallback or host chmod')
    R.require(shutil.disk_usage(args.evidence).free>=20_000_000_000,'At least 20 GB free needed')
    run=R.api('actions/runs/'+str(R.ORIGINAL_RUN))
    pages=R.api('actions/runs/'+str(R.ORIGINAL_RUN)+'/jobs?filter=all&per_page=100',paginate=True)
    artifact=R.api('actions/artifacts/'+str(R.ARTIFACT_ID))
    original=R.validate_original(run,[job for page in pages for job in page['jobs']],artifact)
    proof=dict(original_result=original,candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
               qualification_base=QUALIFICATION_BASE,checker=checker_proof(),driver_sha256=R.digest(Path(__file__)),
               execution_manifest_sha256=R.digest(args.bundle/'execution-pins-v3.json'),docker_server_version=docker,
               recovery_run=int(os.environ['GITHUB_RUN_ID']),recovery_attempt=int(os.environ['GITHUB_RUN_ATTEMPT']),
               artifact=dict(id=R.ARTIFACT_ID,name=R.ARTIFACT_NAME,original_run=R.ORIGINAL_RUN,
                             archive_bytes=R.ARCHIVE_BYTES,archive_digest=R.ARCHIVE_DIGEST))
    R.write_json(args.evidence/'preflight.json',proof)


def verify(args):
    validate_ci(os.environ);verify_sources(args)
    proof=json.loads((args.evidence/'preflight.json').read_text())
    R.require(proof['execution_checker_head']==os.environ['GITHUB_SHA'] and proof['checker']==checker_proof()
              and proof['execution_manifest_sha256']==R.digest(args.bundle/'execution-pins-v3.json'),
              'Preflight belongs to another native source/checker execution')
    proof['iso']=R.verify_iso(args.inputs)
    R.write_json(args.evidence/'verified-input.json',proof)
    for relative in R.METADATA_PINS:
        target=args.evidence/'input-metadata'/relative;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(args.inputs/relative,target)


def records(lines,prefix):
    return [json.loads(line[len(prefix):]) for line in lines if line.startswith(prefix)]


def native_block(serial,stage):
    lines=serial.splitlines()
    starts=[i for i,line in enumerate(lines) if line.startswith('ARCTIC-NATIVE-RUNNER-BEGIN ')]
    ends=[i for i,line in enumerate(lines) if line.startswith('ARCTIC-NATIVE-RUNNER-END ')]
    R.require(len(starts)==len(ends)==1 and starts[0]<ends[0],'Missing/duplicate/reversed native runner block')
    begin=json.loads(lines[starts[0]].split(' ',1)[1]);end=json.loads(lines[ends[0]].split(' ',1)[1])
    R.require(begin['stage']==end['stage']==stage and begin['native_source_sha256']==NATIVE_SOURCE_SHA
              and begin['checker_sha256']==CHECKERS['native-functional'][1]
              and begin['release_acceptance'] is False and end['release_acceptance'] is False,'Native block identity differs')
    return lines[starts[0]+1:ends[0]],begin,end


def extract_evidence(lines,stage,target):
    R.require(not target.exists(),'Native extracted evidence must be unused');target.mkdir(parents=True)
    manifests=records(lines,'ARCTIC-NATIVE-EVIDENCE-MANIFEST ')
    R.require(len(manifests)==1,'Missing/duplicate native evidence manifest')
    manifest=manifests[0]
    R.require(manifest['schema']=='arctic-native-evidence-v1' and manifest['stage']==stage
              and isinstance(manifest['files'],list) and len(manifest['files'])<=128,'Native evidence schema/bounds differ')
    chunks=records(lines,'ARCTIC-NATIVE-EVIDENCE-CHUNK ')
    known=set();total=0;copied={}
    for entry in manifest['files']:
        relative=entry['path'];parts=Path(relative).parts
        R.require(isinstance(relative,str) and relative and not Path(relative).is_absolute()
                  and '..' not in parts and '.' not in parts and relative==Path(relative).as_posix()
                  and relative not in known
                  and relative not in {'transport-manifest.json','serial-native-report.json','serial-native-provenance.json'}
                  and Path(relative).suffix.lower() in ('.json','.png','.log','.txt','.tsv'),
                  'Unsafe/duplicate native evidence path')
        known.add(relative)
        R.require(type(entry['bytes']) is int and 0<=entry['bytes']<=MAX_FILE
                  and type(entry['compressed_bytes']) is int and 0<entry['compressed_bytes']<=MAX_FILE+65536
                  and type(entry['chunks']) is int and 1<=entry['chunks']<=172
                  and entry['encoding']=='zlib+base64' and re.fullmatch('[0-9a-f]{64}',entry['sha256']),
                  'Native evidence byte/chunk bound differs')
        selected=[chunk for chunk in chunks if chunk['path']==relative]
        R.require(len(selected)==entry['chunks'] and [chunk['index'] for chunk in selected]==list(range(entry['chunks']))
                  and all(type(chunk['index']) is int for chunk in selected),'Missing/duplicate/reordered chunks')
        compressed=b''.join(base64.b64decode(chunk['data'],validate=True) for chunk in selected)
        R.require(len(compressed)==entry['compressed_bytes'],'Compressed byte count differs')
        decoder=zlib.decompressobj();data=decoder.decompress(compressed,MAX_FILE+1)
        R.require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
                  and len(data)==entry['bytes'] and hashlib.sha256(data).hexdigest()==entry['sha256'],
                  'Native evidence content/length/hash differs')
        total+=len(data);R.require(total<=MAX_TOTAL,'Native total evidence bound exceeded')
        output=target/relative;output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(data)
        copied[relative]=dict(bytes=len(data),sha256=entry['sha256'])
    R.require(all(chunk['path'] in known for chunk in chunks),'Unexpected evidence chunk')
    R.require(type(manifest['bytes']) is int and manifest['bytes']==total,'Manifest aggregate bytes differ')
    R.write_json(target/'transport-manifest.json',manifest)
    return copied


def check_native(serial,stage,target):
    lines,begin,end=native_block(serial,stage)
    copied=extract_evidence(lines,stage,target) # Preserve complete files before asserting success.
    reports=records(lines,'ARCTIC-NATIVE-FUNCTIONAL ')
    R.require(len(reports)==1,'Missing/duplicate actual native report')
    report=reports[0];R.write_json(target/'serial-native-report.json',report)
    provenance=records(lines,'ARCTIC-NATIVE-PROVENANCE ')
    R.require(len(provenance)==1,'Missing/duplicate native provenance')
    proof=provenance[0];R.write_json(target/'serial-native-provenance.json',proof)
    R.require(proof['stage']==stage and proof['native_source_sha256']==NATIVE_SOURCE_SHA
              and proof['checker_sha256']==begin['checker_sha256'] and proof['release_acceptance'] is False
              and type(proof['desktop_uid']) is int and proof['desktop_uid']>0
              and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',proof['boot_id']),'Native runtime provenance differs')
    launcher=proof['launcher']
    R.require(launcher['schema']=='arctic-native-launcher-v1' and launcher['stage']==stage
              and launcher['boot_id']==proof['boot_id'] and launcher['launcher_sha256']==LAUNCHER_SHA
              and launcher['owned_launcher_gone'] is True and isinstance(proof['active_desktop_session'],str)
              and bool(proof['active_desktop_session']),'Owned launcher same-boot disappearance proof missing')
    for name in ('shell','foot','probe'):
        item=launcher[name]
        R.require(all(type(item[k]) is int and item[k]>0 for k in ('pid','start_ticks'))
                  and type(item['uid']) is int and item['uid']>=0
                  and re.fullmatch('[0-9a-f]{64}',item['executable_sha256']),'Owned launcher process identity differs')
    R.require(launcher['foot']['uid']==launcher['shell']['uid']==proof['desktop_uid']
              and launcher['foot']['executable']=='/usr/bin/foot'
              and Path(launcher['shell']['executable']).name in {'bash','fish','zsh','dash','sh'}
              and launcher['probe']['uid']==0,'Owned launcher UID/ELF binding differs')
    R.require(('rd.live.image' in proof['cmdline'].split())==(stage=='live'),'Actual native stage command line differs')
    R.require(re.search(r'^\s*\d+\s+\[[^]]+\]',proof['virtual_audio_cards'],re.M),'Guest virtual audio card unobserved')
    if stage=='installed':
        R.require(proof['encrypted_root']['device'].startswith('/dev/mapper/')
                  and proof['encrypted_root']['type']=='LUKS2'
                  and re.search(r'^\s*type:\s+LUKS2\s*$',proof['encrypted_root']['status'],re.M),
                  'Installed root encryption proof is missing')
    R.require(report['schema']=='arctic-native-functional-smoke-v2' and report['stage']==stage
              and report['release_acceptance'] is False and isinstance(report['gates'],list),'Native report identity differs')
    names=[gate['check'] for gate in report['gates']]
    R.require(len(names)==len(set(names)) and set(names)==GATES,'Missing/extra/duplicate native gate')
    R.require('report.json' in copied and json.loads((target/'report.json').read_text())==report,
              'Guest temp report and actual serial report differ')
    R.require(end['status']=='passed' and end['error'] is None and end['evidence_export_complete'] is True
              and report['status']=='limited-smoke-passed' and all(gate['status']=='passed' for gate in report['gates']),
              'Native guard/collector/functional/GUI/cleanup gate failed')
    root=Path(report['evidence_root'])
    transport=json.loads((target/'transport-manifest.json').read_text())
    R.require(root.parent==Path('/tmp') and root.name.startswith('arctic-native-smoke-')
              and transport['evidence_root']==str(root),'Native report/transport evidence root differs')
    byname={gate['check']:gate for gate in report['gates']}
    screenshots=byname['actual-role-file-manager-terminal-editor']['value']['screenshots']+[byname['open-codec-content-and-player-state']['value']['screenshot']]
    R.require(len(screenshots)==3,'Required native screenshots missing')
    for shot in screenshots:
        relative=Path(shot['path']).relative_to(root).as_posix()
        R.require(relative in copied and relative.endswith('.png') and shot['sha256']==copied[relative]['sha256'],
                  'Actual native screenshot/report hash differs')
        R.require((target/relative).read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),'Native screenshot is not PNG')
    return dict(stage=stage,status='limited-smoke-passed',release_acceptance=False,files=copied,provenance=proof,
                screenshot_review='REQUIRED; no visual pass inferred')


def exactly_zero(serial,label):
    values=re.findall(r'^'+re.escape(label)+r'=(.*)$',serial,re.M)
    R.require(values==['0'],'Missing/duplicate/nonzero '+label)


def installed_scope(serial):
    lines=serial.splitlines()
    R.require(lines.count('ARCTIC-COLLECT-BEGIN')==lines.count('ARCTIC-COLLECT-END')==1
              and lines.index('ARCTIC-COLLECT-BEGIN')<lines.index('ARCTIC-COLLECT-END'),
              'Installed collection incomplete')
    return '\n'.join(lines[lines.index('ARCTIC-COLLECT-BEGIN')+1:lines.index('ARCTIC-COLLECT-END')])


def validate_harness_serial(vm,evidence):
    results={};errors=[];serials={}
    for stage,name in (('live','serial-install.log'),('installed','serial-boot.log')):
        try:
            serial=(vm/name).read_text(errors='replace')
            serials[stage]=serial
            scoped=installed_scope(serial) if stage=='installed' else serial
            results[stage]=check_native(scoped,stage,evidence/('native-'+stage))
            ready=records(serial.splitlines(),'ARCTIC-NATIVE-LAUNCHER-READY ')
            gone=records(serial.splitlines(),'ARCTIC-NATIVE-LAUNCHER-GONE ')
            proof=results[stage]['provenance']['launcher']
            expected_ready=dict(proof);expected_ready.pop('owned_launcher_gone')
            R.require(ready==[expected_ready] and gone==[proof]
                      and serial.index('ARCTIC-NATIVE-LAUNCHER-READY ')<serial.index('ARCTIC-NATIVE-LAUNCHER-GONE ')
                      <serial.index('ARCTIC-NATIVE-RUNNER-BEGIN ')
                      and 'ARCTIC-NATIVE-LAUNCHER-FAILED ' not in serial,
                      'Owned native launcher ready/disappearance/order evidence differs')
        except BaseException as error:errors.append(stage+': '+str(error))
    # A missing second stage never prevents preserving first-stage guest evidence.
    if 'live' in serials:
        try:
            live=serials['live']
            exactly_zero(live,'ARCTIC-LIVE-SMOKE-EXIT');exactly_zero(live,'ARCTIC-INSTALL-EXIT')
            R.require(re.findall(r'^ARCTIC-OFFLINE-HTTP-RESPONSE=(.*)$',live,re.M)==['000']
                      and re.findall(r'^ARCTIC-OFFLINE-GATE=(.*)$',live,re.M)==['passed: restricted QEMU network, no outside HTTP response'],
                      'Actual offline-install transport gate missing/failed')
            R.require(live.index('ARCTIC-OFFLINE-GATE=')<live.index('ARCTIC-NATIVE-RUNNER-BEGIN ')
                      <live.index('ARCTIC-NATIVE-RUNNER-END ')<live.index('ARCTIC-LIVE-SMOKE-EXIT=')
                      <live.index('ARCTIC-INSTALL-EXIT='),'Live native/install marker order differs')
        except BaseException as error:errors.append('live harness: '+str(error))
    if 'installed' in serials:
        try:
            installed=installed_scope(serials['installed'])
            exactly_zero(installed,'ARCTIC-INSTALLED-SMOKE-EXIT')
            R.require(installed.index('ARCTIC-NATIVE-RUNNER-END ')<installed.index('ARCTIC-INSTALLED-SMOKE-EXIT='),
                      'Installed native/probe exit marker order differs')
        except BaseException as error:errors.append('installed harness: '+str(error))
    if len(results)==2:
        try:R.require(results['live']['provenance']['boot_id']!=results['installed']['provenance']['boot_id'],
                      'Live/installed boot IDs are identical')
        except BaseException as error:errors.append('boot identity: '+str(error))
    R.write_json(evidence/'native-stages.json',dict(results=results,errors=errors,release_acceptance=False))
    R.require(not errors,'; '.join(errors))
    return results


def preserve_audio(path,target):
    R.require(path.is_file() and not path.is_symlink(),'Virtual output WAV absent: '+path.name)
    target.mkdir(parents=True,exist_ok=True)
    R.require(path.stat().st_size<=1_073_741_824,'Virtual WAV exceeds 1 GiB inspection bound')
    info=dict(source_name=path.name,source_bytes=path.stat().st_size,source_sha256=R.digest(path),
              scope='PCM delivered to an emulated output in this stage; attribution/perceived audio remains unqualified')
    try:
        with wave.open(str(path),'rb') as source:
            params=source.getparams();info.update(channels=params.nchannels,rate=params.framerate,width=params.sampwidth,
                                               frames=params.nframes,compression=params.comptype)
            R.require(params.nchannels==2 and params.framerate==48000 and params.sampwidth==2
                      and params.comptype=='NONE' and params.nframes>0,'Virtual WAV format/frames differ')
            first_nonzero=None;position=0;blocks=0;nonzero_blocks=0
            while data:=source.readframes(16384):
                if data!=b'\0'*len(data):
                    nonzero_blocks+=1
                    if first_nonzero is None:first_nonzero=position
                position+=len(data)//(params.nchannels*params.sampwidth);blocks+=1
            R.require(position==params.nframes,'Truncated virtual WAV PCM')
            info.update(blocks=blocks,nonzero_blocks=nonzero_blocks,first_nonzero_block_frame=first_nonzero)
            if path.stat().st_size<=32*1024*1024:
                shutil.copyfile(path,target/path.name);info['preserved_full']=True
            else:
                info['preserved_full']=False;info['excerpts']=[]
                offsets=sorted(set([0,max(0,params.nframes-2*params.framerate),first_nonzero or 0]))
                for index,offset in enumerate(offsets):
                    source.setpos(offset);pcm=source.readframes(2*params.framerate)
                    name=path.stem+'-excerpt-'+str(index)+'.wav'
                    with wave.open(str(target/name),'wb') as out:
                        out.setparams(params);out.writeframes(pcm)
                    info['excerpts'].append(dict(path=name,start_frame=offset,frames=len(pcm)//4,sha256=R.digest(target/name)))
            R.write_json(target/(path.stem+'.json'),info)
            R.require(first_nonzero is not None,'Virtual output contains only silent PCM; diagnose fixture/backend/app')
    except BaseException as error:
        with path.open('rb') as source:(target/(path.name+'.bounded-prefix.bin')).write_bytes(source.read(1024*1024))
        info['error']=str(error);R.write_json(target/(path.stem+'.json'),info)
        raise
    return info


def run(args):
    verify(args) # Rehash the actual unsplit ISO immediately before any VM.
    docker=R.require_docker();R.require(Path('/dev/kvm').is_char_device(),'KVM disappeared')
    vm=args.evidence.parent/'native-vm';R.require(not vm.exists(),'Native VM output must be unused')
    state=dict(status='prepared',candidate_iso_source=R.SOURCE,execution_checker_head=os.environ['GITHUB_SHA'],
               iso_bytes=R.ISO_BYTES,iso_sha256=R.ISO_SHA256,checker=checker_proof(),docker_server_version=docker,
               release_acceptance=False,original_runs_unchanged=[R.ORIGINAL_RUN,37520174911])
    prepared=None
    def save():
        state['recorded_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        R.write_json(args.evidence/'execution.json',state)
    def interrupted(signum,frame):raise InterruptedError('Native run interrupted by signal '+str(signum))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    try:
        save();container='arctic-paired-native-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        R.execute(['bash',str(args.source/'tools/performance/prepare-vm-tools.sh'),str(args.evidence)],
                  args.evidence/'provision.log',20*60,args.source,env,container)
        prepared=(args.evidence/'vm-prepared-image-id.txt').read_text().strip()
        R.require(re.fullmatch(r'(sha256:)?[0-9a-f]{64}',prepared),'Immutable test-tool image ID missing')
        state.update(status='running_live_install_first_boot',vm_tool_image_id=prepared);save()
        name,sha=CHECKERS['native-functional'];R.pinned_file(args.bundle/name,sha)
        container='arctic-paired-native-'+uuid.uuid4().hex
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container,
                 ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1',ARCTIC_NATIVE_AUDIO_FIXTURE='1',
                 ARCTIC_NATIVE_LAUNCHER=str(args.bundle/'native-launcher-v3.py'))
        argv=['bash',str(args.bundle.parents[1]/'tools/test-install.sh'),'--iso',str(args.inputs/'iso'/R.ISO),
              '--kvm','--memory','4096','--smp','2','--boot-append','','--install-timeout','2400',
              '--boot-network','offline','--guest-check',str(args.bundle/name),
              '--profile',str(args.source/'profiles/ci/offline.toml'),'--out',str(vm)]
        errors=[]
        try:R.execute(argv,args.evidence/'native-harness.log',110*60,args.bundle.parents[1],env,container)
        except BaseException as error:errors.append('harness: '+str(error))
        finally:state['harness_evidence']=R.preserve_phase(vm,args.evidence,'harness');save()
        # Extract complete available native files and bounded WAV even on failed probes.
        try:state['native_stages']=validate_harness_serial(vm,args.evidence)
        except BaseException as error:errors.append('native stages: '+str(error))
        state['audio']={}
        for stage in ('install','boot'):
            try:state['audio'][stage]=preserve_audio(vm/('native-audio-'+stage+'.wav'),args.evidence/'virtual-audio')
            except BaseException as error:errors.append(stage+' audio: '+str(error))
        R.require(not errors,'; '.join(errors))
        state['status']='limited_native_live_installed_smoke_passed_pending_visual_audio_review';save()
    except BaseException as error:
        state.update(status='failed_or_unrun',error=str(error));save();raise
    finally:
        if prepared:subprocess.run(['docker','image','rm',prepared],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase',choices=('preflight','verify','run'))
    for name in ('source','bundle','inputs','evidence'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    for name in ('source','bundle','inputs','evidence'):setattr(args,name,getattr(args,name).resolve())
    try:globals()[args.phase](args)
    except BaseException as error:
        if args.evidence.exists():R.write_json(args.evidence/('blocked-'+args.phase+'.json'),dict(error=str(error),phase=args.phase,release_acceptance=False))
        raise


if __name__=='__main__':main()
