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

# BEGIN SOURCE-CLOSED FAILURE OBSERVATION
import ast
import contextlib
import inspect
import io
import textwrap
import types

HOST_STAGES = ('host-data','host-container','container-packages','container-audio',
    'container-data','container-disk','container-profile','container-driver','container-complete',
    'install-acquire','install-menu','install-live','install-settle','install-terminal',
    'install-start-marker','install-start-observed','install-not-started','install-engine',
    'install-exit-observed','install-exit-missing-vm-running','install-exit-missing-vm-exited',
    'install-shutdown','install-cleanup','boot-acquire','boot-menu','boot-unlock','boot-login',
    'boot-settle','boot-terminal','boot-collect','boot-collect-observed','boot-collect-missing',
    'boot-shutdown','boot-cleanup','install-live-observed','install-live-unobserved',
    'install-terminal-attempt-one','install-terminal-attempt-two','install-terminal-attempt-three',
    'install-command-type-before','install-command-type-after','install-command-enter-before',
    'install-command-enter-after','install-marker-wait-observed','install-marker-wait-unobserved',
    'install-marker-vm-running','install-marker-vm-exited','install-marker-vm-unknown',
    'install-command-shot-before','install-command-shot-after',
    'install-preterminal-capture-preserved','install-preterminal-capture-unavailable',
    'vm-acquire-qemu-exited','vm-acquire-no-qmp','vm-acquire-system-exit',
    'vm-acquire-file-missing','vm-acquire-permission-error','vm-acquire-os-error',
    'vm-acquire-json-error','vm-acquire-qmp-error','vm-acquire-keyboard-interrupt',
    'vm-acquire-other-error','vm-acquire-stderr-unobserved',
    'vm-acquire-enforce-host-unavailable','vm-acquire-enforce-only-spec-ctrl',
    'vm-acquire-enforce-floor-unavailable','vm-acquire-enforce-tcg-unavailable')
ERROR_TYPES = (RuntimeError, TimeoutError, OSError, FileNotFoundError, PermissionError,
               json.JSONDecodeError, KeyError, ValueError, subprocess.CalledProcessError)


def guard_sites():
    """Bind labels to loaded, pinned code objects and actual require call spans."""
    result = {}
    for name, function in (('execute',execute),('guard',C.guard),('regular',C.regular),
                           ('manifest',C.manifest),('digest-file',C.digest_file)):
        lines, start = inspect.getsourcelines(function)
        tree = ast.parse(textwrap.dedent(''.join(lines)))
        calls = sorted((n for n in ast.walk(tree) if isinstance(n,ast.Call) and
            ((isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name)
              and n.func.value.id=='C' and n.func.attr=='require') or
             (isinstance(n.func,ast.Name) and n.func.id=='require'))),key=lambda n:n.lineno)
        rows=[(start+n.lineno-1,start+n.end_lineno-1,name+'-'+format(i+1,'03d'),True)
              for i,n in enumerate(calls)]
        if function is execute:
            rows.extend((start+n.lineno-1,start+n.end_lineno-1,'execute-deferred-interrupted',False)
                for n in ast.walk(tree) if isinstance(n,ast.Raise) and isinstance(n.exc,ast.Call)
                and isinstance(n.exc.func,ast.Name) and n.exc.func.id=='RuntimeError'
                and len(n.exc.args)==1 and isinstance(n.exc.args[0],ast.Constant)
                and n.exc.args[0].value=='Owned UI host invocation interrupted')
        result[function.__code__] = (function.__globals__,tuple(rows))
    return result


def primary_guard(error):
    """Never read exception args, repr, text, paths or arbitrary frame locals."""
    if type(error) is not RuntimeError:return 'unknown'
    try:
        sites=guard_sites()
        interrupt_codes={c for c in execute.__code__.co_consts
                         if isinstance(c,types.CodeType) and c.co_name=='interrupted'}
        tb=BaseException.__traceback__.__get__(error,type(error)); seen=0
        while tb is not None and seen<64:
            frame=tb.tb_frame; following=tb.tb_next; seen+=1
            if frame.f_code in interrupt_codes and frame.f_globals is globals():
                return 'execute-interrupted'
            entry=sites.get(frame.f_code)
            if entry is not None and frame.f_globals is entry[0]:
                trusted_require=(following is not None and
                    following.tb_frame.f_code is C.require.__code__ and
                    following.tb_frame.f_globals is C.__dict__)
                matches=[label for first,last,label,needs_require in entry[1]
                         if first<=tb.tb_lineno<=last and (not needs_require or trusted_require)]
                if len(matches)==1:return matches[0]
            tb=following
    except Exception:pass
    return 'unknown'


def invocation(role):
    C.require(role in ('provision','harness'),'Diagnostic invocation role differs')
    return dict(role=role,stage='not-started',failed_stage='none',exit_status=None,
                acquired=False,reaped=False,primary_guard='unknown')


def private_checkpoints(path,nonce,scanner):
    """Whole private bytes are screened first; no private bytes/hashes exported."""
    empty=dict(privacy='unavailable',bytes=0,host_stages={},guest_fixed_stages={},
               install_exit_count=0,install_exit_status=None)
    try:data=C.regular(path,16*1024*1024)
    except Exception:return empty
    empty['bytes']=len(data)
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            C.require(scanner.external_text(data)==data,'Private original screening differs')
    except Exception:
        empty['privacy']='rejected';return empty
    empty['privacy']='passed';text=data.decode('utf-8')
    allowed=set(HOST_STAGES);host={};guest={};exits=[]
    for line in text.splitlines():
        prefix='ARCTIC-DICTATION-HOST-STAGE '+nonce+' '
        if line.startswith(prefix):
            label=line[len(prefix):]
            if label in allowed:host[label]=host.get(label,0)+1
        if line in ('ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS','ARCTIC-DESKTOP-UNLOCK-REQUESTED'):
            guest[line]=guest.get(line,0)+1
        match=re.fullmatch(r'ARCTIC-INSTALL-EXIT=([0-9]{1,3})',line)
        if match and 0<=int(match[1])<=255:exits.append(int(match[1]))
    if any(v>256 for v in [*host.values(),*guest.values()]) or len(exits)>256:return empty
    empty.update(host_stages=host,guest_fixed_stages=guest,install_exit_count=len(exits),
                 install_exit_status=exits[0] if len(exits)==1 else None)
    return empty


def validate_failure(value):
    fields={'schema','context','status','phase','error_class','primary_guard','invocations',
            'private_logs','raw_private_exported','ui_acceptance','release_acceptance'}
    C.require(type(value) is dict and set(value)==fields,'Failure observation fields differ')
    C.load(Path(__file__).with_name('guest.py'),'ui_failure_context').validate_context(value['context'])
    C.require(value['schema']=='arctic-final-installed-ui-host-failure-v1'
        and value['status']=='failed' and value['phase'] in
        ('provision','harness','original-screening','cleanup') and value['error_class'] in
        {c.__name__ for c in ERROR_TYPES}|{'OtherError'} and value['raw_private_exported'] is False
        and value['ui_acceptance'] is False and value['release_acceptance'] is False,
        'Failure observation acceptance differs')
    labels={'unknown','execute-interrupted'}|{row[2] for _,rows in guard_sites().values() for row in rows}
    C.require(value['primary_guard'] in labels,'Foreign failure guard label')
    C.require(type(value['invocations']) is list and len(value['invocations'])==2
        and type(value['private_logs']) is dict and set(value['private_logs'])=={'provision','harness'},
        'Failure invocation inventory differs')
    for role,item in zip(('provision','harness'),value['invocations']):
        C.require(type(item) is dict and set(item)=={'role','stage','failed_stage','exit_status',
            'acquired','reaped','primary_guard'} and item['role']==role and item['stage'] in
            ('not-started','acquisition','observation','cleanup','complete') and item['failed_stage'] in
            ('none','acquisition','observation','cleanup') and type(item['acquired']) is bool
            and type(item['reaped']) is bool and (not item['reaped'] or item['acquired'])
            and item['primary_guard'] in labels and (item['exit_status'] is None or
            type(item['exit_status']) is int and 0<=item['exit_status']<=255),
            'Failure invocation fields differ')
        log=value['private_logs'][role]
        C.require(type(log) is dict and set(log)=={'privacy','bytes','host_stages','guest_fixed_stages',
            'install_exit_count','install_exit_status'} and log['privacy'] in
            ('unavailable','passed','rejected') and type(log['bytes']) is int
            and 0<=log['bytes']<=16*1024*1024 and type(log['host_stages']) is dict
            and set(log['host_stages'])<=set(HOST_STAGES) and type(log['guest_fixed_stages']) is dict
            and set(log['guest_fixed_stages'])<= {'ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS',
                                              'ARCTIC-DESKTOP-UNLOCK-REQUESTED'}
            and all(type(n) is int and 1<=n<=256 for n in
                    [*log['host_stages'].values(),*log['guest_fixed_stages'].values()])
            and type(log['install_exit_count']) is int and 0<=log['install_exit_count']<=256
            and ((log['install_exit_count']==1 and type(log['install_exit_status']) is int
                  and 0<=log['install_exit_status']<=255) or
                 (log['install_exit_count']!=1 and log['install_exit_status'] is None))
            and (log['privacy']=='passed' or (not log['host_stages'] and not log['guest_fixed_stages']
                and log['install_exit_count']==0 and log['install_exit_status'] is None)),
            'Private checkpoint projection differs')
    return value


def failure_observation(error,phase,context,observations,private,scanner):
    value=dict(schema='arctic-final-installed-ui-host-failure-v1',context=context,status='failed',
        phase=phase,error_class=type(error).__name__ if type(error) in ERROR_TYPES else 'OtherError',
        primary_guard=primary_guard(error),invocations=observations,
        private_logs={role:private_checkpoints(private/(role+'.log'),context['nonce'],scanner)
                      for role in ('provision','harness')},raw_private_exported=False,
        ui_acceptance=False,release_acceptance=False)
    return validate_failure(value)
# END SOURCE-CLOSED FAILURE OBSERVATION


def screen(source, target):
    C.require(source.is_dir() and not source.is_symlink() and not target.exists()
              and not target.is_symlink(),'Screening owned paths differ')
    scanner=C.load(C.ROOT/'tools/native-functional/screen-evidence.py','ui_final_screen')
    guest=C.load(Path(__file__).with_name('guest.py'),'ui_final_inventory')
    allowed={'host-status.json','host-failure.json','original-ui/report.json','serial-install.log.gz','serial-boot.log.gz'} | {
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
            if name=='host-failure.json':validate_failure(C.strict_json(data))
        else:
            guest.png(path)
        files[name]=data
    C.require(total<=192*1024*1024 and 'host-status.json' in files,'Original artifact byte/status bound')
    if 'host-failure.json' in files:
        status=C.strict_json(files['host-status.json']);failure=C.strict_json(files['host-failure.json'])
        C.require(status.get('status')=='failed' and status.get('context')==failure['context']
            and status.get('phase')==failure['phase'] and status.get('error_class')==failure['error_class'],
            'Failure-only diagnostic differs from original failed host status')
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


def execute(argv, log, seconds, cwd, env, observation=None):
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
            if observation is not None:observation['stage']='acquisition'
            child=subprocess.Popen(argv,cwd=cwd,env=env,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
            acquiring=False
            if observation is not None:observation.update(acquired=True,stage='observation')
            if pending: raise RuntimeError('Owned UI host invocation interrupted')
            end=time.monotonic()+seconds
            while True:
                info=os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                if info is not None: break
                C.require(time.monotonic()<end and os.fstat(stream.fileno()).st_size<=256*1024*1024,
                          'UI host invocation deadline/output bound')
                time.sleep(.1)
            status=info.si_status if info.si_code==os.CLD_EXITED else 128+info.si_status
            if observation is not None:observation['exit_status']=status
            C.require(status==0,'UI host invocation failed')
        except BaseException as error:
            primary=error
            if observation is not None:observation.update(failed_stage=observation['stage'],primary_guard=primary_guard(error))
        finally:
            for s in old: signal.signal(s,lambda signum,frame:None)
            if child is not None:
                if observation is not None:observation['stage']='cleanup'
                try:
                    os.waitid(os.P_PID,child.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                    for sig in (signal.SIGTERM,signal.SIGKILL):
                        try: os.killpg(child.pid,sig)
                        except ProcessLookupError: pass
                        if sig==signal.SIGTERM: time.sleep(1)
                    child.wait(timeout=5)
                    if observation is not None:observation['reaped']=True
                except BaseException as error: secondary=error
            for s,handler in old.items(): signal.signal(s,handler)
    if observation is not None and primary is None and secondary is None:observation['stage']='complete'
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
    observations=[invocation('provision'),invocation('harness')]
    try:
        container='arctic-paired-'+task+'-'+uuid.uuid4().hex[:8]
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container)
        execute(['bash',str(C.ROOT/'tools/performance/prepare-vm-tools.sh'),str(private),task],
                private/'provision.log',20*60,C.ROOT,env,observations[0])
        candidate=C.regular(private/'vm-prepared-image-id.txt',100).decode().strip()
        C.require(re.fullmatch('sha256:[0-9a-f]{64}',candidate),'Owned prepared image differs')
        labels=json.loads(subprocess.check_output(['docker','image','inspect','--format','{{json .Config.Labels}}',candidate],timeout=30))
        C.require(labels.get('org.arctic.test.vm-tools.task')==task and
            labels.get('org.arctic.test.vm-tools.container')==container and
            labels.get('org.arctic.test.vm-tools.scope')=='paired-v1','Prepared image owner labels differ')
        prepared=candidate
        phase='harness'; container='arctic-paired-'+task+'-'+uuid.uuid4().hex[:8]
        env=dict(os.environ,CONTAINER_ENGINE='docker',ARCTIC_VM_CONTAINER_NAME=container,
                 ARCTIC_FEDORA_IMAGE=prepared,ARCTIC_VM_TOOLS_PREPARED='1',ARCTIC_DICTATION_HOST_TOKEN=task)
        vm=private/'vm'
        C.guard(manifest,args.source,args.inputs)
        execute(['bash',str(C.ROOT/'tools/test-install.sh'),'--iso',
            str(args.inputs/'iso'/manifest['image']['name']),'--kvm','--memory','4096','--smp','2',
            '--boot-append','','--install-timeout','2400','--boot-network','offline',
            '--profile',str(args.source/'profiles/ci/offline.toml'),'--guest-check',str(payload/'guest-check.py'),
            '--guest-check-interactive','--out',str(vm)],private/'harness.log',70*60,C.ROOT,env,observations[1])
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
            if primary is not None:
                try:
                    diagnostic=failure_observation(primary,primary_phase,context,observations,private,scanner)
                    data=(json.dumps(diagnostic,sort_keys=True,indent=2)+'\n').encode()
                    C.require(scanner.external_text(data)==data,'Failure observation privacy rejected')
                    C.exclusive(public/'host-failure.json',data)
                except BaseException:pass  # Reporting cannot replace the original failed result.
    return int(primary is not None)


if __name__=='__main__': raise SystemExit(main())
