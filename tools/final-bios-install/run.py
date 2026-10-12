#!/usr/bin/env python3
"""One disposable exact-image encrypted offline BIOS install and disk boot."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time
import uuid
import struct
import zlib
import common as C
import compose

def recover_prepared_image(private,task,container):
    """Recover only this Source helper's exclusive pre-commit image intent."""
    path=private/'vm-prepared-image-owner.json'
    if not path.exists() and not path.is_symlink():return None
    intent=C.strict_json(C.regular(path,4096))
    C.require(type(intent) is dict and set(intent)=={'schema','release_acceptance','task_id','container','base_id'}
        and intent['schema']=='arctic-paired-test-image-owner-v1' and intent['release_acceptance'] is False
        and intent['task_id']==task and intent['container']==container
        and type(intent['base_id']) is str and re.fullmatch('sha256:[0-9a-f]{64}',intent['base_id']),
        'Prepared image recovery intent differs')
    result=subprocess.run(['docker','image','ls','--no-trunc','--quiet','--filter','label=org.arctic.test.vm-tools.task='+task,'--filter','label=org.arctic.test.vm-tools.container='+container],capture_output=True,timeout=30,check=True)
    C.require(len(result.stdout)<=4096,'Prepared image recovery inventory bound')
    values=set(result.stdout.decode('ascii').splitlines())
    C.require(len(values)<=1 and all(re.fullmatch('sha256:[0-9a-f]{64}',value) for value in values),'Prepared image recovery ambiguous')
    if not values:return None
    candidate=next(iter(values))
    labels=C.strict_json(subprocess.check_output(['docker','image','inspect','--format','{{json .Config.Labels}}',candidate],timeout=30))
    C.require(type(labels) is dict and labels.get('org.arctic.test.vm-tools.task')==task
        and labels.get('org.arctic.test.vm-tools.container')==container
        and labels.get('org.arctic.test.vm-tools.scope')=='paired-v1'
        and labels.get('org.arctic.test.vm-tools.base')==intent['base_id'],'Prepared image recovery owner differs')
    return candidate

def remove_owned_container(name, image, vm):
    """An immutable container ID, image and exact owned output mount bind cleanup."""
    value=subprocess.run(['docker','container','inspect',name],capture_output=True,timeout=30)
    if value.returncode==1:return  # Existing --rm cleanup already removed it.
    C.require(value.returncode==0 and len(value.stdout)<=1024*1024,'Container cleanup inventory unavailable')
    rows=C.strict_json(value.stdout)
    C.require(type(rows) is list and len(rows)==1 and rows[0]['Name']=='/'+name
        and rows[0]['Image']==image and re.fullmatch('[0-9a-f]{64}',rows[0]['Id'])
        and any(m.get('Source')==str(vm) and m.get('Destination')==str(vm)
                for m in rows[0].get('Mounts',[])),'Foreign container cleanup refused')
    subprocess.run(['docker','rm','--force',rows[0]['Id']],stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL,timeout=30,check=True)

def execute(argv, log, seconds, cwd, env):
    """Keep the acquired leader unreaped until its group is stopped."""
    child=None; primary=None; secondary=None; pending=False
    old={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    def interrupted(signum,frame):
        nonlocal pending
        # One handler stays installed through ownership transfer AND cleanup.
        # Repeated signals never raise in the middle of stopping/reaping a group.
        pending=True
    with Path(log).open('xb') as stream:
        try:
            for s in old: signal.signal(s,interrupted)
            child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            if pending: raise RuntimeError('Owned BIOS host invocation interrupted')
            end=time.monotonic()+seconds
            while True:
                if pending: raise RuntimeError('Owned BIOS host invocation interrupted')
                info=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if info is not None: break
                C.require(time.monotonic()<end and os.fstat(stream.fileno()).st_size<=256*1024*1024,
                          'BIOS host invocation deadline/output bound')
                time.sleep(.1)
            status=info.si_status if info.si_code==os.CLD_EXITED else 128+info.si_status
            C.require(status==0,'BIOS host invocation failed')
        except BaseException as error: primary=error
        finally:
            if child is not None:
                reserved=False
                try:
                    os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                    reserved=True
                except BaseException as error: secondary=error
                # A reaped leader no longer reserves this process-group ID.
                # Never signal it without the original child reservation.
                if reserved:
                    for sig in (signal.SIGTERM,signal.SIGKILL):
                        try: os.killpg(child.pid,sig)
                        except ProcessLookupError: pass
                        except BaseException as error:
                            if secondary is None:secondary=error
                        if sig==signal.SIGTERM:
                            try:time.sleep(1)
                            except BaseException as error:
                                if secondary is None:secondary=error
                    # A failed TERM/KILL attempt must not skip the next attempt
                    # or reaping. The original invocation error remains primary.
                    try:child.wait(timeout=5)
                    except BaseException as error:
                        if secondary is None:secondary=error
            # Restoration occurs only after the owned group has been stopped.
            for s,handler in old.items():
                try:signal.signal(s,handler)
                except BaseException as error:
                    if secondary is None:secondary=error
    if primary is not None: raise primary
    if secondary is not None: raise secondary
    if pending: raise RuntimeError('Owned BIOS host invocation interrupted')

PNG_NAMES=('install-20-live-desktop.png','install-40-finished.png','boot-51-desktop.png','boot-99-final.png')
SECURITY_SCOPE='journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit'

def argv(source,inputs,guest,vm,manifest):
    C.manifest(manifest,True)
    return ['bash',str(C.ROOT/'tools/test-install.sh'),'--firmware','bios','--stage','all','--iso',str(inputs/'iso'/manifest['image']['name']),'--kvm','--memory','4096','--smp','2','--boot-append','','--install-timeout','2400','--install-network','offline','--boot-network','offline','--profile',str(source/'profiles/ci/offline.toml'),'--guest-check',str(guest),'--out',str(vm)]


def validate_report(value,ctx,stage,guest_sha):
    C.require(type(value) is dict and set(value)=={'schema','context','stage','status','guest_sha256','proof','release_acceptance'} and value['schema']=='arctic-final-bios-report-v1' and value['context']==ctx and value['stage']==stage and value['status']=='passed' and value['guest_sha256']==guest_sha and value['release_acceptance'] is False,'Original BIOS report identity differs')
    p=value['proof'];required={'firmware','efi_present','live_medium','boot_id','desktop_uid','security'}|({'root','offline_queue'} if stage=='installed' else set())
    C.require(type(p) is dict and set(p)==required and p['firmware']=='bios' and p['efi_present'] is False and p['live_medium'] is (stage=='live') and type(p['boot_id']) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',p['boot_id']) and type(p['desktop_uid']) is int and p['desktop_uid']==1000,'Original BIOS boot proof differs')
    sec=p['security'];C.require(type(sec) is dict and set(sec)=={'selinux','audit','observed_new_avcs','audit_enabled','scope'} and sec['selinux']=='Enforcing' and type(sec['observed_new_avcs']) is int and sec['observed_new_avcs']==0 and type(sec['audit_enabled']) is bool and sec['scope']==SECURITY_SCOPE,'Original BIOS security proof differs')
    audit=sec['audit'];C.require(type(audit) is dict and set(audit)=={'enabled','lost'} and type(audit['enabled']) is int and audit['enabled'] in (0,1,2) and type(audit['lost']) is int and audit['lost']>=0 and sec['audit_enabled']==(audit['enabled'] in (1,2)),'Original audit proof differs')
    if stage=='installed':
        root=p['root'];C.require(type(root) is dict and set(root)=={'fstype','encrypted','target','luks_uuid'} and root['fstype']=='btrfs' and root['encrypted'] is True and root['target']=='vda' and type(root['luks_uuid']) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',root['luks_uuid']),'Original encrypted target root differs')
        q=p['offline_queue'];C.require(type(q) is dict and set(q)=={'ready','pending','state','version','timer_enabled','verified_payload','outside_http_response'} and q['ready'] is False and q['pending'] is True and q['state'] in ('queued','error') and q['version']=='1.1.0' and q['timer_enabled'] is True and q['verified_payload'] is False and q['outside_http_response'] is False,'Original offline queue proof differs')
    return value


def records(raw,ctx,stage,guest_sha,scanner):
    C.require(type(raw) is bytes and 0<len(raw)<=(16*1024*1024 if stage=='live' else 128*1024*1024),'BIOS original UART bound')
    C.require(scanner.external_text(raw)==raw,'Whole original BIOS UART privacy rejected')
    rows=[]
    for line in raw.decode('utf-8').splitlines():
        if line.startswith('ARCTIC-FINAL-BIOS '):
            C.require(len(line.encode())<=16384,'BIOS report line bound');rows.append(C.strict_json(line.split(' ',1)[1]))
    C.require(len(rows)==1,'Missing or duplicate original BIOS report')
    value=validate_report(rows[0],ctx,stage,guest_sha)
    lines=raw.decode('utf-8').splitlines()
    C.require('ARCTIC-FINAL-BIOS-FAILED' not in lines,'Original guest failed')
    report_at=next(i for i,x in enumerate(lines) if x.startswith('ARCTIC-FINAL-BIOS '))
    if stage=='live':
        C.require([x for x in lines if x.startswith('ARCTIC-LIVE-SMOKE-EXIT=')]==['ARCTIC-LIVE-SMOKE-EXIT=0'] and [x for x in lines if x.startswith('ARCTIC-INSTALL-EXIT=')]==['ARCTIC-INSTALL-EXIT=0'],'Original live/install completion missing')
        C.require(report_at<lines.index('ARCTIC-LIVE-SMOKE-EXIT=0')<lines.index('ARCTIC-INSTALL-EXIT=0'),'Original installation order differs')
        C.require([x for x in lines if x.startswith('ARCTIC-OFFLINE-HTTP-RESPONSE=')]==['ARCTIC-OFFLINE-HTTP-RESPONSE=000'] and lines.count('ARCTIC-OFFLINE-GATE=passed: restricted QEMU network, no outside HTTP response')==1 and not any(x.startswith('ARCTIC-OFFLINE-GATE=failed:') for x in lines),'Original live offline restriction unproven')
    else:
        C.require([x for x in lines if x.startswith('ARCTIC-INSTALLED-SMOKE-EXIT=')]==['ARCTIC-INSTALLED-SMOKE-EXIT=0'] and lines.count('ARCTIC-COLLECT-BEGIN')==1 and lines.count('ARCTIC-COLLECT-END')==1,'Original installed completion missing')
        C.require(lines.index('ARCTIC-COLLECT-BEGIN')<report_at<lines.index('ARCTIC-INSTALLED-SMOKE-EXIT=0')<lines.index('ARCTIC-COLLECT-END'),'Original installed collection order differs')
    return value


def original_png(data):
    C.require(type(data) is bytes and 0<len(data)<=8*1024*1024 and data.startswith(b'\x89PNG\r\n\x1a\n'),'Original PNG signature/bound')
    at=8;types=[]
    while at<len(data):
        C.require(at+12<=len(data),'Original PNG chunk truncated')
        size=struct.unpack('>I',data[at:at+4])[0];kind=data[at+4:at+8];end=at+12+size
        C.require(end<=len(data) and kind in (b'IHDR',b'PLTE',b'IDAT',b'IEND',b'tRNS',b'gAMA',b'sRGB',b'cHRM'),'Original PNG chunk type/bound')
        C.require(zlib.crc32(data[at+4:at+8+size])&0xffffffff==struct.unpack('>I',data[at+8+size:end])[0],'Original PNG CRC differs')
        types.append(kind);at=end
        if kind==b'IEND':
            C.require(size==0 and at==len(data),'Original PNG end/trailing bytes differ');break
    C.require(types and types[0]==b'IHDR' and types.count(b'IHDR')==1 and types[-1]==b'IEND' and types.count(b'IEND')==1 and b'IDAT' in types,'Original PNG structure differs')
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        C.require(image.format=='PNG' and 640<=image.width<=3840 and 480<=image.height<=2160,'Original screenshot geometry differs');image.verify()
    return data


def original_evidence(vm,ctx,guest_sha):
    scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','bios_source_screen',C.strict_json(C.regular(Path(__file__).with_name('execution-manifest.json'),1024*1024))['execution_files']['tools/native-functional/screen-evidence.py'])
    raw={name:C.regular(vm/name,bound) for name,bound in (('serial-install.log',16*1024*1024),('serial-boot.log',128*1024*1024))}
    live=records(raw['serial-install.log'],ctx,'live',guest_sha,scanner);boot=records(raw['serial-boot.log'],ctx,'installed',guest_sha,scanner)
    C.require(live['proof']['boot_id']!=boot['proof']['boot_id'],'Installed boot reused live guest')
    image_files={}
    for name in PNG_NAMES:
        image_files[name]=original_png(C.regular(vm/name,8*1024*1024))
    C.require(sum(map(len,raw.values()))+sum(map(len,image_files.values()))<=192*1024*1024,'Original evidence aggregate bound')
    return live,boot,{**raw,**image_files}


def publish(out,files):
    allowed={'host-status.json'}|set(PNG_NAMES)|{'serial-install.log.gz','serial-boot.log.gz'}
    C.require(type(files) is dict and 'host-status.json' in files and set(files)<=allowed and all(type(x) is bytes and x for x in files.values()),'Finite original publication inventory differs')
    public=out/'public';pending=out/'private/staged-public'
    C.require(not public.exists() and not public.is_symlink() and not pending.exists() and not pending.is_symlink(),'Publication output already exists')
    pending.mkdir(mode=0o700)
    for name,data in files.items():C.exclusive(pending/name,data)
    pending.rename(public)


def harness_environment(container,prepared=None):
    # No inherited optional Native/app/controller fixture may change this lane.
    env={k:v for k,v in os.environ.items() if not k.startswith('ARCTIC_') and k not in ('CONTAINER_ENGINE','GH_TOKEN','GITHUB_TOKEN','ACTIONS_RUNTIME_TOKEN')}
    env.update(CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
    if prepared is not None:env.update(ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1')
    return env


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','inputs','out'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.source=args.source.resolve();args.inputs=args.inputs.resolve();args.out=args.out.absolute()
    m=C.manifest(C.strict_json(C.regular(Path(__file__).with_name('execution-manifest.json'),1024*1024)),True)
    C.guard(m,args.source,args.inputs)
    C.require(Path('/dev/kvm').is_char_device(),'Real hosted KVM required')
    C.require(not args.out.exists() and not args.out.is_symlink() and args.out.parent.is_dir() and not args.out.parent.is_symlink(),'BIOS output must be unused')
    args.out.mkdir(mode=0o700);private=args.out/'private';private.mkdir(mode=0o700);payload=private/'payload';payload.mkdir(mode=0o700)
    task=uuid.uuid4().hex
    ctx={'schema':'arctic-final-bios-context-v1','nonce':task,'execution_sha':C.git('rev-parse','HEAD'),'source_sha':m['image']['source_sha'],'iso_sha256':m['image']['sha256'],'probe_sha256':C.digest_file(Path(__file__).with_name('guest.py')),'native_sha256':C.digest_file(args.source/'tools/native-functional/native_smoke.py'),'security_sha256':m['security_binding']['helper_sha256']}
    checker=C.load(Path(__file__).with_name('guest.py'),'bios_source_context');checker.context(ctx)
    guest_sha=compose.compose(args.source,Path(__file__).with_name('guest.py'),Path(__file__).with_name('security.py'),ctx,payload/'guest-check.py')
    prepared=None;container=None;provision_container=None;primary=None;phase='provision';result=None;originals=None;vm=private/'vm'
    handlers={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)};main_pending=False
    def defer_main_signal(signum,frame):
        nonlocal main_pending
        main_pending=True
    def check_main_signal():
        C.require(not main_pending,'Owned BIOS main invocation interrupted')
    try:
        for s in handlers:signal.signal(s,defer_main_signal)
        check_main_signal()
        container='arctic-paired-'+task+'-'+uuid.uuid4().hex[:8]
        provision_container=container
        env=harness_environment(container)
        execute(['bash',str(C.ROOT/'tools/performance/prepare-vm-tools.sh'),str(private),task],private/'provision.log',20*60,C.ROOT,env)
        check_main_signal()
        candidate=C.regular(private/'vm-prepared-image-id.txt',100).decode().strip();C.require(re.fullmatch('sha256:[0-9a-f]{64}',candidate),'Prepared tool image identity differs')
        labels=C.strict_json(subprocess.check_output(['docker','image','inspect','--format','{{json .Config.Labels}}',candidate],timeout=30))
        C.require(labels.get('org.arctic.test.vm-tools.task')==task and labels.get('org.arctic.test.vm-tools.container')==container and labels.get('org.arctic.test.vm-tools.scope')=='paired-v1','Prepared image owner differs');prepared=candidate
        phase='install-and-boot';container='arctic-paired-'+task+'-'+uuid.uuid4().hex[:8]
        env=harness_environment(container,prepared)
        C.guard(m,args.source,args.inputs)
        check_main_signal()
        execute(argv(args.source,args.inputs,payload/'guest-check.py',vm,m),private/'harness.log',m['harness_seconds'],C.ROOT,env)
        phase='strict-original-evidence';live,boot,originals=original_evidence(vm,ctx,guest_sha)
        result={'live':live,'installed':boot}
    except BaseException as error:primary=error
    finally:
        try:
            # Do not switch handlers here: the same deferred pair already owns
            # cancellation, including a second signal between cleanup steps.
            if container and prepared:
                try:remove_owned_container(container,prepared,vm)
                except BaseException as error:
                    if primary is None:primary=error;phase='cleanup'
            if prepared is None and provision_container:
                try:prepared=recover_prepared_image(private,task,provision_container)
                except BaseException as error:
                    if primary is None:primary=error;phase='cleanup'
            if prepared:
                try:subprocess.run(['docker','image','rm','--no-prune',prepared],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
                except BaseException as error:
                    if primary is None:primary=error;phase='cleanup'
        finally:
            for s,handler in handlers.items():
                try:signal.signal(s,handler)
                except BaseException as error:
                    if primary is None:primary=error;phase='cleanup'
        if main_pending and primary is None:
            primary=RuntimeError('Owned BIOS main invocation interrupted');phase='cleanup'
    scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','bios_host_screen',m['execution_files']['tools/native-functional/screen-evidence.py'])
    state={'schema':'arctic-final-bios-host-v1','context':ctx,'image':m['image'],'firmware':'bios','status':'passed_pending_original_image_review' if primary is None else 'failed','phase':phase,'error_class':type(primary).__name__ if primary is not None and type(primary).__name__ in {'RuntimeError','TimeoutError','OSError','FileNotFoundError','PermissionError','ValueError','KeyError','JSONDecodeError','CalledProcessError'} else 'none' if primary is None else 'OtherError','result':result if primary is None else None,'release_acceptance':False,'manual_original_image_review_required':True,'bios_active_GUI_restoration_tested':False,'safe_mode_installation_tested':False,'installer_wide_AVC_interval_proven':False,'complete_UART_published':primary is None,'security_scope':'Unchanged live and installed checker intervals only'}
    data=(json.dumps(state,sort_keys=True,indent=2)+'\n').encode();C.require(scanner.external_text(data)==data,'Host BIOS state privacy rejected')
    # All serialized originals and their bounds are validated before publication.
    exported={'host-status.json':data}
    if primary is None:
        for name,raw in originals.items():
            if name.endswith('.log'):
                packed=gzip.compress(raw,mtime=0);C.require(len(packed)<=32*1024*1024,'UART archive bound');exported[name+'.gz']=packed
            else:exported[name]=raw
    publish(args.out,exported)
    return int(primary is not None)


if __name__=='__main__':raise SystemExit(main())
