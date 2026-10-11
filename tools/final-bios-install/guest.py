#!/usr/bin/env python3
"""Fixed BIOS boot/root/offline-queue checks only, never invokes native app checks."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import time

UUID=re.compile('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
CONTEXT_KEYS={'schema','nonce','execution_sha','source_sha','iso_sha256','probe_sha256','native_sha256','security_sha256'}
QUEUE_PROFILES = {'small-v2': 'd4b9326169fe0773b36857ce4b2c52d31294c4c421933c5fbb41422227e92756', 'turbo-q5-v3': 'dfc1e2252ca033888fd0262f73fd4643066c736b9d696e4b7481875e76ed4191'}

def require(value,code):
    if not value:raise RuntimeError(code)


def strict_json(raw):
    def fields(pairs):
        value={}
        for key,item in pairs:
            require(key not in value,'duplicate-json-field');value[key]=item
        return value
    return json.loads(raw,object_pairs_hook=fields,parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite-json')))


def context(value):
    require(type(value) is dict and set(value)==CONTEXT_KEYS and value['schema']=='arctic-final-bios-context-v1' and value['source_sha']=='326690f173d4dc4f049f43e046c8380e66825a07' and value['iso_sha256']=='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c','context-identity')
    require(type(value['nonce']) is str and re.fullmatch('[0-9a-f]{32}',value['nonce']) and type(value['execution_sha']) is str and re.fullmatch('[0-9a-f]{40}',value['execution_sha']) and all(type(value[k]) is str and re.fullmatch('[0-9a-f]{64}',value[k]) for k in ('probe_sha256','native_sha256','security_sha256')),'context-pins')
    return value


def protected(path,limit=4096,owner=True):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        before=os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and (not owner or before.st_uid==0) and not before.st_mode&0o022 and 0<before.st_size<=limit,'protected-record')
        data=os.read(fd,limit+1);after=os.fstat(fd)
        require(len(data)==before.st_size and (after.st_dev,after.st_ino,after.st_size)==(before.st_dev,before.st_ino,before.st_size),'protected-record-changed')
        return data
    finally:os.close(fd)


def command(argv,seconds=10,allowed=(0,)):
    p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=seconds,check=False)
    require(p.returncode in allowed and len(p.stdout)+len(p.stderr)<=65536,'command-outcome-or-bound')
    return p


def text(argv):return command(argv).stdout.decode('utf-8').strip()


def firmware(stage,sys_root=Path('/sys'),proc_root=Path('/proc')):
    require(stage in ('live','installed') and not (sys_root/'firmware/efi').exists() and not (sys_root/'firmware/efi').is_symlink(),'not-legacy-bios')
    cmdline=(proc_root/'cmdline').read_text().split()
    require(('rd.live.image' in cmdline)==(stage=='live'),'boot-medium')
    boot=(proc_root/'sys/kernel/random/boot_id').read_text().strip();require(UUID.fullmatch(boot),'boot-id')
    return {'firmware':'bios','efi_present':False,'live_medium':stage=='live','boot_id':boot}


def encrypted_root(sys_root=Path('/sys')):
    source=text(['findmnt','--raw','--nofsroot','--noheadings','-o','SOURCE','--mountpoint','/'])
    require(re.fullmatch('/dev/mapper/[A-Za-z0-9_.+-]{1,64}',source) and text(['findmnt','--raw','--noheadings','-o','FSTYPE','--mountpoint','/'])=='btrfs','encrypted-btrfs-root')
    status=text(['cryptsetup','status',source]);match=re.search(r'^\s*device:\s+(/dev/vda[1-9][0-9]*)\s*$',status,re.M)
    require(match is not None and re.search(r'^\s*type:\s+LUKS[12]\s*$',status,re.M),'owned-luks-backing-device')
    name=Path(match[1]).name
    require((sys_root/'class/block'/name).resolve(strict=True).parent==(sys_root/'class/block/vda').resolve(strict=True),'foreign-root-partition')
    require((sys_root/'class/block/vda/device/driver').resolve(strict=True).name=='virtio_blk','foreign-root-driver')
    luks=text(['cryptsetup','luksUUID',match[1]]);require(UUID.fullmatch(luks),'luks-uuid')
    return {'fstype':'btrfs','encrypted':True,'target':'vda','luks_uuid':luks}


def queue_predicate(status,pending,verified_exists,timer):
    require(type(status) is dict and type(status.get('ok')) is bool and status.get('ready') is False and status.get('state') in ('queued','error'),'offline-not-queued')
    valid_pending=(type(pending) is dict and set(pending)=={'version','profile','profile_sha256'}
                   and all(type(pending[key]) is str for key in pending)
                   and pending['version']=='1.1.0' and pending['profile'] in QUEUE_PROFILES
                   and pending['profile_sha256']==QUEUE_PROFILES[pending['profile']])
    require(valid_pending and not verified_exists and timer=='enabled','offline-pending-proof')
    require(type(status.get('download_bytes')) is int and status['download_bytes'] in (506181191,678117115),'offline-download-disclosure')
    return {'ready':False,'pending':True,'state':status['state'],'version':'1.1.0','timer_enabled':True,'verified_payload':False,'outside_http_response':False}


def offline_queue(prefix,system=Path('/var/lib/arctic/dictation')):
    outside=command(['curl','--noproxy','*','-s','-o','/dev/null','-w','%{http_code}','--connect-timeout','3','--max-time','5','http://fedoraproject.org/'],seconds=10,allowed=(0,5,6,7,28))
    require(outside.stdout==b'000' and not outside.stderr,'offline-outside-response')
    payload=Path('/opt/arctic/voxtype/1.1.0')
    require(not any((payload/name).exists() or (payload/name).is_symlink() for name in ('voxtype-cpu','voxtype-cpu-avx2','voxtype-vulkan','ggml-small.bin','ggml-large-v3-turbo-q5_0.bin')),'offline-payload-present')
    deadline=time.monotonic()+660
    while True:
        p=command(prefix+['/usr/bin/arctic-dictation','status'],allowed=(0,1));require(not p.stderr and len(p.stdout)<=16384,'dictation-status-bound')
        value=strict_json(p.stdout)
        require(type(value) is dict and type(value.get('ok')) is bool and ((p.returncode==0 and value['ok'] is True) or (p.returncode==1 and value['ok'] is False and value.get('state')=='error')),'dictation-status-outcome')
        require(value.get('ready') is False,'offline-false-ready')
        if value.get('state')!='downloading':break
        require(time.monotonic()<deadline,'offline-queue-deadline');time.sleep(2)
    pending=strict_json(protected(system/'pending.json'))
    timer=text(['systemctl','is-enabled','arctic-dictation-setup.timer'])
    return queue_predicate(value,pending,(system/'verified.json').exists() or (system/'verified.json').is_symlink(),timer)


def main(stage,ctx,native,interval_type):
    context(ctx);require(stage in ('live','installed') and os.geteuid()==0 and Path(__file__).parent==Path('/run/t') and text(['systemd-detect-virt']) in ('qemu','kvm'),'disposable-root')
    interval=interval_type();primary=None;proof={}
    try:
        proof.update(firmware(stage))
        require(text(['getenforce'])=='Enforcing','selinux-enforcing')
        prefix=native.discover_desktop()
        expected='liveuser' if stage=='live' else 'ci'
        require(prefix[:2]==['runuser','-u'] and prefix[2]==expected and pwd.getpwnam(expected).pw_uid==1000 and text(prefix+['id','-u'])=='1000','actual-desktop-user')
        proof['desktop_uid']=1000
        if stage=='installed':
            proof['root']=encrypted_root();proof['offline_queue']=offline_queue(prefix)
    except BaseException as error:primary=error
    finally:
        try:proof['security']=interval.finish()
        except BaseException as error:
            if primary is None:primary=error
    require(primary is None,'bios-check-failed')
    require(text(['findmnt','--noheadings','-o','FSTYPE','--target',__file__])=='iso9660' and 'ro' in text(['findmnt','--noheadings','-o','OPTIONS','--target',__file__]).split(','),'read-only-source-cd')
    raw=protected(Path(__file__),1024*1024,owner=False)
    report={'schema':'arctic-final-bios-report-v1','context':ctx,'stage':stage,'status':'passed','guest_sha256':hashlib.sha256(raw).hexdigest(),'proof':proof,'release_acceptance':False}
    print('ARCTIC-FINAL-BIOS '+json.dumps(report,sort_keys=True,separators=(',',':')),flush=True)
    return 0
