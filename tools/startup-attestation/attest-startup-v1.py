"""Finite same-ISO post-startup prerequisite probe. No startup/session hook.

Only three fixed installed providers, our read-only CD and our owned synthetic
processes/descriptors are observed. No profile/whole-chain inventory is repeated.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import sys
import tempfile
import time
import zlib
sys.dont_write_bytecode=True
SOURCE='fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
ISO_SHA='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
MANGO_SHA='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866'
COMMON_SHA='e1da6bb2f07cb7014486e0f59c36973600e5dcd9a8063c684f461e099d3fc5e9'
HERE=Path(__file__).resolve().parent
PROVIDERS={'/usr/libexec/sddm-helper':'93ab003b0453179eb1f0e6a7a51a20ee322af4992300d095403c5f728b7a68e4',
           '/usr/bin/bash':'379c1bfc53d08815975c647ad7da5d19d8e8a8566ce8097c50231c8b116e5e7b',
           '/usr/bin/python3.14':'0d64bd6d66d68dac91cdadafc46e22d4f09f22bdc997aaae870f42865b024a3e'}
CD_FILES={'attest-startup-v1.py','guest-safe-collector-v1.py','toolkit.py','sealed_environment.py','guest-credential-primitive.py',
          'runtime-fixtures-v1.py','synthetic-handoff-observer.py','env-probe.c','env-seal-static-probe.c','argv-probe.c',
          'env-native-v1','env-seal-native-v1','argv-native-v1','bootstrap-attest-v1.sh'}

def require(value,message):
    if not value:raise RuntimeError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def emit(name,value):print('ARCTIC-ATTEST-'+name+' '+json.dumps(value,sort_keys=True),flush=True)
def stable_stat(value):
    return tuple(getattr(value,key) for key in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_size','st_mtime_ns','st_ctime_ns'))
def load(name):
    spec=importlib.util.spec_from_file_location('prerequisite_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def binary(path,expected_sha):
    p=Path(path);require(all(not v.is_symlink() for v in p.parents),'Provider parent symlink')
    before=p.lstat();require(stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0 and not before.st_mode&0o6022
                           and 0<before.st_size<=2*1024*1024,'Provider type/owner/mode/size differs')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        require(stable_stat(os.fstat(fd))==stable_stat(before),'Provider identity changed before read')
        data=os.pread(fd,before.st_size+1,0)
        require(len(data)==before.st_size and data.startswith(b'\x7fELF') and sha(data)==expected_sha
                and stable_stat(os.fstat(fd))==stable_stat(before) and stable_stat(p.lstat())==stable_stat(before),'Provider bytes/identity changed')
    finally:os.close(fd)
    return dict(path=str(p),uid=before.st_uid,gid=before.st_gid,mode=stat.S_IMODE(before.st_mode),bytes=len(data),sha256=sha(data),stable_identity=list(stable_stat(before)))

def verify_cd():
    config=HERE/'runtime-probe-pins-v1.json';require(not config.is_symlink() and config.lstat().st_uid==0 and config.stat().st_size<=65536,'Runtime fixture pins type/owner/bound')
    pins=json.loads(config.read_bytes());require(pins.get('schema')=='arctic-runtime-prerequisite-CD-v1' and pins.get('candidate_source')==SOURCE
          and pins.get('intended_iso_sha256')==ISO_SHA and set(pins.get('files',{}))==CD_FILES and set(pins.get('modes',{}))==CD_FILES,'Runtime fixture pins scope differs')
    for name,expected in pins['files'].items():
        p=HERE/name;before=p.lstat();require(stat.S_ISREG(before.st_mode) and before.st_uid==before.st_gid==0
            and type(pins['modes'][name]) is int and stat.S_IMODE(before.st_mode)==pins['modes'][name] and before.st_size<=65536,'Readonly CD file type/owner/mode/bound differs')
        data=p.read_bytes();require(sha(data)==expected and stable_stat(p.lstat())==stable_stat(before),'Readonly CD fixture bytes changed')
    return pins

def namespace_context():
    status=Path('/proc/self/status').read_bytes();mount=Path('/proc/self/mountinfo').read_bytes()
    require(len(status)<=65536 and len(mount)<=65536,'Own procfs context exceeds bound')
    fields={}
    for row in status.splitlines():
        if b':' in row:
            key,value=row.split(b':',1);require(key not in fields,'Duplicate own process status');fields[key]=value.strip()
    ns=os.readlink('/proc/self/ns/pid');init_ns=os.readlink('/proc/1/ns/pid')
    require(re.fullmatch(r'pid:\[[1-9][0-9]*\]',ns) and ns==init_ns,'Unknown/different actual PID namespace')
    nspid=[int(v) for v in fields.get(b'NSpid',b'').split()]
    require(nspid==[os.getpid()] and fields.get(b'Pid')==str(os.getpid()).encode()
            and fields.get(b'Uid')==b'0\t0\t0\t0' and fields.get(b'Gid')==b'0\t0\t0\t0','Own root procfs PID/credential namespace unavailable')
    proc=[]
    for row in mount.decode().splitlines():
        left,sep,right=row.partition(' - ');items=left.split();after=right.split()
        if len(items)>=6 and items[4]=='/proc':
            require(sep and len(after)>=3 and after[0]=='proc' and items[3]=='/','Unexpected /proc mount identity')
            proc.append(dict(mount_id=items[0],parent_id=items[1],device=items[2],root=items[3],target=items[4],filesystem=after[0]))
    require(len(proc)==1,'Actual procfs mount absent/ambiguous')
    return dict(observer_pid=os.getpid(),pid_namespace=ns,init_pid_namespace=init_ns,NSpid=nspid,proc_mount=proc[0],
                status_base64=base64.b64encode(status).decode(),status_sha256=sha(status),mountinfo_base64=base64.b64encode(mount).decode(),mountinfo_sha256=sha(mount),
                scope='Own current procfs/PID namespace only; independently sampled, not atomic process history')

def security(C,root,label):
    value=C.security(root,label)
    require(value['selinux']=='Enforcing' and not value['avc_records'] and value['journal_total_bytes']==value['journal_retained_bytes'],
            'Full current-boot journal/security incomplete or failed')
    return value

def collect(C,root,pins):
    begin=time.monotonic_ns();user,processes,environment=C.desktop()
    require(user.pw_uid==user.pw_gid==1000 and user.pw_dir=='/home/liveuser' and user.pw_shell=='/bin/bash','Exact previously observed live user/shell changed')
    require(processes['mango']['cmdline']==['mango'] and processes['mango']['executable_sha256']==MANGO_SHA,'Normal candidate Mango changed')
    normal_environment=C.environment(processes['mango']['pid'])
    before=security(C,root,'prereq-before');context_before=namespace_context()
    provider_before=[binary(path,expected) for path,expected in PROVIDERS.items()]
    F=load('runtime-fixtures-v1');K=load('guest-credential-primitive')
    added_begin=time.monotonic_ns()
    with tempfile.TemporaryDirectory(prefix='arctic-owned-runtime-') as name:
        owned=Path(name);seals=F.seal_controls()
        credentials=K.probe(owned/'credential-log','/usr/bin/python3.14',PROVIDERS['/usr/bin/python3.14'],user.pw_uid,user.pw_gid)
        environments=F.synthetic_environment_cases(owned,str(HERE/'env-native-v1'),str(HERE/'env-seal-native-v1'),'/usr/bin/bash')
        arguments=F.quoted_argv_control(owned,str(HERE/'argv-native-v1'),'/usr/bin/bash')
    require(time.monotonic_ns()-added_begin<=60*10**9,'Added runtime probes exceeded60s')
    added_end=time.monotonic_ns()
    provider_after=[binary(path,expected) for path,expected in PROVIDERS.items()]
    context_after=namespace_context();after=security(C,root,'prereq-after')
    require(provider_before==provider_after and all(context_before[k]==context_after[k] for k in ('observer_pid','pid_namespace','init_pid_namespace','NSpid','proc_mount')),'Provider/namespace bracket changed')
    require(C.environment(processes['mango']['pid'])==normal_environment and all(C.process(v['pid'])==v for v in processes.values()),'Normal desktop identity/environment changed during own probes')
    require(verify_cd()==pins,'Readonly CD fixture pins changed after probe')
    context=dict(before=context_before,after=context_after,non_atomic=True)
    data=json.dumps(context,sort_keys=True,indent=2).encode();require(len(data)<=256*1024,'Namespace output exceeds addedJSON cap');(root/'namespace-context.json').write_bytes(data)
    report=dict(schema='arctic-runtime-prerequisite-report-v1',status='runtime-prerequisite-collected',candidate_source=SOURCE,intended_iso_sha256=ISO_SHA,
        mango_executable_sha256=MANGO_SHA,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cmdline=Path('/proc/cmdline').read_text().strip(),
        begin_monotonic_ns=begin,end_monotonic_ns=time.monotonic_ns(),added_probe_begin_ns=added_begin,added_probe_end_ns=added_end,
        providers=provider_before,CD_pins_sha256=sha((HERE/'runtime-probe-pins-v1.json').read_bytes()),processes=processes,
        namespace_context_sha256=sha(data),observer_pid=context_before['observer_pid'],selected_user=dict(uid=user.pw_uid,gid=user.pw_gid,shell=user.pw_shell,home=user.pw_dir),
        seal_controls=seals,credential_control=credentials,environment_controls=environments,quoted_argument_control=arguments,
        security_before=before,security_after=after,own_fixture_attempts=11,own_fixture_processes=16,
        normal_environment_unchanged=True,normal_environment_sha256=sha(b'\0'.join(k.encode()+b'='+v.encode() for k,v in sorted(normal_environment.items()))),
        complete_startup_chain=False,exact_startup_target_bound=False,actual_final_startup_handoff_qualified=False,
        startup_hook_executed=False,Mango_launched_or_restarted=False,Mango_d=False,renderer='unobserved',active_scanout_pixels='unavailable',release_acceptance=False,safe_visual_gate='open',
        scope='Own runtime provider/namespace/memfd/credential and synthetic final-exec probes after ordinary startup only; no real user environment exported; all original oversized/dynamic/conditional/history blockers remain')
    raw=json.dumps(report,indent=2,sort_keys=True).encode();require(len(raw)+len(data)<=256*1024,'Added JSON exceeds256KiB');(root/'report.json').write_bytes(raw)
    return report

def transport(root,report):
    files=[];chunks=[];total=0
    require({p.name for p in root.iterdir()}=={'report.json','namespace-context.json','system-journal-prereq-before.log','system-journal-prereq-after.log'},'Unexpected own output set')
    for p in sorted(root.iterdir()):
        require(p.is_file() and not p.is_symlink(),'Unexpected runtime output type')
        data=p.read_bytes();require(len(data)<=4*1024*1024,'Runtime file exceeds bound');total+=len(data);require(total<=16*1024*1024,'Runtime transport exceeds total bound')
        packed=zlib.compress(data);parts=[packed[i:i+1200] for i in range(0,len(packed),1200)];require(0<len(parts)<=3600,'Runtime chunk bound')
        files.append(dict(path=p.name,bytes=len(data),sha256=sha(data),compressed_bytes=len(packed),chunks=len(parts)))
        chunks.extend(dict(path=p.name,index=i,data=base64.b64encode(part).decode()) for i,part in enumerate(parts))
    emit('REPORT',report);emit('MANIFEST',dict(schema='arctic-startup-attestation-files-v1',encoding='zlib+base64',files=files,bytes=total))
    for value in chunks:emit('CHUNK',value)

def main():
    error=None;armed=False
    emit('BEGIN',dict(collector_sha256=sha(Path(__file__).read_bytes()),candidate_source=SOURCE,release_acceptance=False))
    try:
        require(os.geteuid()==0 and Path(__file__).resolve()==Path('/run/arctic-safe/attest-startup-v1.py'),'Requires exact root readonlyCD collector path')
        common=HERE/'guest-safe-collector-v1.py';require(not common.is_symlink() and sha(common.read_bytes())==COMMON_SHA,'Original security collector pin differs')
        C=load('guest-safe-collector-v1')
        require(C.execute(['systemd-detect-virt']).decode().strip() in ('qemu','kvm'),'Requires disposable QEMU/KVM')
        cmd=Path('/proc/cmdline').read_text().split();require('rd.live.image' in cmd and 'nomodeset' in cmd,'Requires exact normal Safe mode')
        require(C.execute(['getenforce']).decode().strip()=='Enforcing','Requires Enforcing before own writes')
        require('ro' in C.execute(['findmnt','-n','-o','OPTIONS','/run/arctic-safe']).decode().strip().split(','),'Requires readonlyCD')
        pins=verify_cd()
        def alarm(signum,frame):raise TimeoutError('Runtime prerequisite110s alarm')
        signal.signal(signal.SIGALRM,alarm);signal.alarm(110);armed=True
        with tempfile.TemporaryDirectory(prefix='arctic-runtime-evidence-') as name:
            root=Path(name);report=collect(C,root,pins);transport(root,report)
    except BaseException as failed:error=type(failed).__name__+': '+str(failed)
    finally:
        if armed:signal.alarm(0)
    emit('END',dict(status='failed' if error else 'attestation-collected-unreviewed',error=error,release_acceptance=False))
    if error:raise SystemExit(1)

if __name__=='__main__':main()
