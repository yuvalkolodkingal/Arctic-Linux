#!/usr/bin/env python3
"""One KVM install, bounded production UI segment, original-only evidence."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import time
import uuid
import common as C
import compose


def screen(source, target):
    C.require(source.is_dir() and not source.is_symlink() and not target.exists()
              and not target.is_symlink(),'Screening owned paths differ')
    scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_final_screen')
    guest=C.load(Path(__file__).with_name('guest.py'),'ui_final_inventory')
    allowed={'host-status.json','original-ui/report.json','serial-install.log.gz','serial-boot.log.gz'} | {
        'original-ui/'+name for name in guest.PNG_NAMES}
    files={}; total=0
    for path in source.rglob('*'):
        C.require(not path.is_symlink(),'Original UI symlink rejected')
        if path.is_dir(): continue
        name=path.relative_to(source).as_posix()
        C.require(name in allowed,'Original UI inventory differs')
        data=C.regular(path,32*1024*1024); total+=len(data)
        if name.endswith('.gz'):
            import zlib
            limit=16*1024*1024 if name.startswith('serial-install') else 128*1024*1024
            obj=zlib.decompressobj(16+zlib.MAX_WBITS); wire=obj.decompress(data,limit+1)
            C.require(obj.eof and not obj.unconsumed_tail and not obj.unused_data
                      and len(wire)<=limit,'Original UART gzip expansion bound')
            C.require(scanner.external_text(wire)==wire,'Original UART privacy rejected')
        elif name.endswith('.json'):
            C.strict_json(data); C.require(scanner.external_text(data)==data,'Original JSON privacy rejected')
        else:
            guest.png(path)
        files[name]=data
    C.require(total<=192*1024*1024 and 'host-status.json' in files,'Original artifact byte/status bound')
    target.mkdir(mode=0o700)
    for name,data in files.items():
        output=target/name; output.parent.mkdir(exist_ok=True,mode=0o700); C.exclusive(output,data)


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
    child=None; primary=None; secondary=None; acquiring=True; pending=False
    old={s:signal.getsignal(s) for s in (signal.SIGTERM,signal.SIGINT)}
    def interrupted(signum,frame):
        nonlocal pending
        if acquiring: pending=True
        else: raise RuntimeError('Owned UI host invocation interrupted')
    with Path(log).open('xb') as stream:
        try:
            for s in old: signal.signal(s,interrupted)
            child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            acquiring=False
            if pending: raise RuntimeError('Owned UI host invocation interrupted')
            end=time.monotonic()+seconds
            while True:
                info=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if info is not None: break
                C.require(time.monotonic()<end and os.fstat(stream.fileno()).st_size<=256*1024*1024,
                          'UI host invocation deadline/output bound')
                time.sleep(.1)
            status=info.si_status if info.si_code==os.CLD_EXITED else 128+info.si_status
            C.require(status==0,'UI host invocation failed')
        except BaseException as error: primary=error
        finally:
            for s in old: signal.signal(s,lambda signum,frame:None)
            if child is not None:
                try:
                    os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                    for sig in (signal.SIGTERM,signal.SIGKILL):
                        try: os.killpg(child.pid,sig)
                        except ProcessLookupError: pass
                        if sig==signal.SIGTERM: time.sleep(1)
                    child.wait(timeout=5)
                except BaseException as error: secondary=error
            for s,handler in old.items(): signal.signal(s,handler)
    if primary is not None: raise primary
    if secondary is not None: raise secondary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screen',action='store_true')
    for name in ('source','inputs','out'): parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.screen:
        screen(args.source,args.out); return 0
    args.source=args.source.resolve(); args.inputs=args.inputs.resolve(); args.out=args.out.absolute()
    manifest=C.manifest(C.strict_json(C.regular(Path(__file__).with_name('execution-manifest.json'),1024*1024)),True)
    C.guard(manifest,args.source,args.inputs)
    C.require(Path('/dev/kvm').is_char_device(),'Real host KVM required')
    C.require(not args.out.exists() and not args.out.is_symlink(),'UI output must be unused')
    args.out.mkdir(mode=0o700); private=args.out/'private';private.mkdir(mode=0o700)
    public=args.out/'public'; public.mkdir(mode=0o700)
    payload=private/'payload';payload.mkdir(mode=0o700)
    task=uuid.uuid4().hex
    context=dict(schema='arctic-final-installed-ui-context-v1',nonce=task,execution_sha=C.git('rev-parse','HEAD'),
        source_sha=manifest['image']['source_sha'],iso_sha256=manifest['image']['sha256'],
        native_sha256=C.digest_file(args.source/'tools/native-functional/native_smoke.py'),
        ui_sha256=C.digest_file(Path(__file__).with_name('guest.py')))
    C.load(Path(__file__).with_name('guest.py'),'ui_guest_context').validate_context(context)
    C.exclusive(private/'context.json',(json.dumps(context,sort_keys=True)+'\n').encode())
    compose.compose(args.source,Path(__file__).with_name('guest.py'),context,payload/'guest-check.py')
    prepared=None; container=None; primary=None; report=None; inventory=None; phase='provision'
    status='failed'; error_class='none'; original_wire=None; primary_phase=None
    try:
        container='arctic-paired-'+task+'-'+uuid.uuid4().hex[:8]
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        execute(['bash',str(C.ROOT/'tools/performance/prepare-vm-tools.sh'),str(private),task],
                private/'provision.log',20*60,C.ROOT,env)
        candidate=C.regular(private/'vm-prepared-image-id.txt',100).decode().strip()
        C.require(re.fullmatch('sha256:[0-9a-f]{64}',candidate),'Owned prepared image differs')
        labels=json.loads(subprocess.check_output(['docker','image','inspect','--format','{{json .Config.Labels}}',candidate],timeout=30))
        C.require(labels.get('org.arctic.test.vm-tools.task')==task and
            labels.get('org.arctic.test.vm-tools.container')==container and
            labels.get('org.arctic.test.vm-tools.scope')=='paired-v1','Prepared image owner labels differ')
        prepared=candidate
        phase='harness'; container='arctic-paired-'+task+'-'+uuid.uuid4().hex[:8]
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container,
                 ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1')
        vm=private/'vm'
        C.guard(manifest,args.source,args.inputs)
        execute(['bash',str(C.ROOT/'tools/test-install.sh'),'--iso',
            str(args.inputs/'iso'/manifest['image']['name']),'--kvm','--memory','4096','--smp','2',
            '--boot-append','','--install-timeout','2400','--boot-network','offline',
            '--profile',str(args.source/'profiles/ci/offline.toml'),'--guest-check',str(payload/'guest-check.py'),
            '--guest-check-interactive','--out',str(vm)],private/'harness.log',70*60,C.ROOT,env)
    except BaseException as error: primary=error; primary_phase=phase
    finally:
        # Preserve complete available originals even when the harness failed.
        try:
            phase='original-screening'
            scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','final_ui_screen')
            live=C.regular(private/'vm/serial-install.log',16*1024*1024)
            C.require(scanner.external_text(live)==live and
                live.decode().count('ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS')==1,'Original live precheck differs')
            original_wire=C.regular(private/'vm/serial-boot.log',128*1024*1024)
            report,inventory=C.decode(original_wire,context,scanner,public/'original-ui')
            for name,wire in (('serial-install.log.gz',live),('serial-boot.log.gz',original_wire)):
                packed=gzip.compress(wire,mtime=0);C.require(len(packed)<=32*1024*1024,'Original UART archive bound')
                C.exclusive(public/name,packed)
            C.require(report['status']=='passed','Actual UI guest failed')
            if primary is None: status='passed_pending_manual_ui_review'; phase='complete'
        except BaseException as error:
            if primary is None: primary=error; primary_phase=phase
        finally:
            for s in (signal.SIGTERM,signal.SIGINT): signal.signal(s,lambda signum,frame:None)
            if container and prepared:
                try: remove_owned_container(container,prepared,private/'vm')
                except BaseException as error:
                    if primary is None:primary=error;primary_phase='cleanup'
            if prepared:
                try:
                    subprocess.run(['docker','image','rm','--no-prune',prepared],stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL,timeout=30,check=True)
                except BaseException as error:
                    if primary is None: primary=error; primary_phase='cleanup'
            if primary is not None:
                status='failed'; error_class=type(primary).__name__ if type(primary).__name__ in {
                    'RuntimeError','TimeoutError','OSError','FileNotFoundError','PermissionError',
                    'JSONDecodeError','KeyError','ValueError','CalledProcessError'} else 'OtherError'
            value=dict(schema='arctic-final-installed-ui-host-v1',context=context,status=status,phase=primary_phase or phase,
                error_class=error_class,image=manifest['image'],ui_seconds=720,max_png=16,
                original_uart_complete=original_wire is not None,original_members=inventory,
                visual_review_required=True,release_acceptance=False,
                battery_hardware_tested=False,signed_update_reboot_tested=False,
                capture_kind='original Wayland screencopy PNG; readback may force repaint',
                private_harness_qmp_frames_exported=False)
            data=(json.dumps(value,sort_keys=True,indent=2)+'\n').encode()
            scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_host_status_screen')
            C.require(scanner.external_text(data)==data,'Host status privacy rejected')
            C.exclusive(public/'host-status.json',data)
    return int(primary is not None)


if __name__=='__main__': raise SystemExit(main())
