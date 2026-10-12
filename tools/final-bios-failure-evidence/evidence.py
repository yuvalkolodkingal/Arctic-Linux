#!/usr/bin/env python3
"""Disabled failure-only snapshots; original bytes and closed Source causes."""
import gzip
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import types

UARTS={'serial-install.log':('live',16*1024*1024),
       'serial-boot.log':('installed',128*1024*1024)}
PNGS=('install-20-live-desktop.png','install-40-finished.png',
      'boot-51-desktop.png','boot-99-final.png')
PREFIX=b'ARCTIC-FINAL-BIOS-CAUSE '
FIELDS=('st_dev','st_ino','st_uid','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
FAILED_TAIL=b'  if (( rc != 0 )); then tail -n 120 "$OUT"/serial-*.log || true; fi'
PRIVATE_TAIL=b'  : # Failed whole original UART remains private until strict screening.'

def require(value):
    if not value:raise ValueError('Failure original acquisition rejected')

def same(left,right):return all(getattr(left,n)==getattr(right,n) for n in FIELDS)

def close_owned(descriptor):
    """Linux releases the FD on close errors; never retry a reused FD number."""
    try:os.close(descriptor);return
    except BaseException:pass

def directory_owner(info):return (info.st_dev,info.st_ino,info.st_uid,info.st_mode)

@contextmanager
def snapshot_directory(private):
    """Reserve the one new holder inode until every failure member finishes."""
    descriptor=None;saved=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
    try:
        descriptor=os.open(private,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        info=os.fstat(descriptor)
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid() and info.st_mode&0o777==0o700
                and directory_owner(info)==directory_owner(os.stat(private,follow_symlinks=False)))
        yield directory_owner(info)
        require(directory_owner(os.fstat(descriptor))==directory_owner(info)
                and directory_owner(os.stat(private,follow_symlinks=False))==directory_owner(info))
    finally:
        try:
            if descriptor is not None:close_owned(descriptor)
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK,saved)

def read_original(vm,name,limit,uid,retain=False,retained_owner=None):
    """Anchor each directory and member; signals resume only after FD cleanup."""
    require(isinstance(vm,Path))
    require(vm.is_absolute() and vm.name=='vm' and vm.parent.name=='private'
            and name in set(UARTS)|set(PNGS) and type(limit) is int and limit>0
            and type(uid) is int and uid>=0)
    owned=[None,None,None,None,None,None]
    saved=signal.pthread_sigmask(signal.SIG_BLOCK,{signal.SIGINT,signal.SIGTERM})
    try:
        # Every acquired descriptor is assigned while cancellation is blocked.
        owned[0]=os.open(vm.parent.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        root=owned[0]
        for at,name_part in enumerate(('private','vm'),1):
            current=os.fstat(owned[at-1])
            require(stat.S_ISDIR(current.st_mode) and current.st_uid==uid and not current.st_mode&0o022)
            owned[at]=os.open(name_part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=owned[at-1])
        directory=os.fstat(owned[2])
        require(stat.S_ISDIR(directory.st_mode) and directory.st_uid==uid and not directory.st_mode&0o022)
        before_path=os.stat(name,dir_fd=owned[2],follow_symlinks=False)
        owned[3]=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=owned[2])
        descriptor=owned[3]
        before=os.fstat(descriptor)
        require(same(before_path,before) and stat.S_ISREG(before.st_mode) and before.st_uid==uid
                and before.st_nlink==1 and not before.st_mode&0o022 and 0<before.st_size<=limit)
        data=bytearray()
        while len(data)<=limit:
            part=os.read(descriptor,min(1024*1024,limit+1-len(data)))
            if not part:break
            data.extend(part)
        after=os.fstat(descriptor)
        require(same(before,after) and same(after,os.stat(name,dir_fd=owned[2],follow_symlinks=False))
                and len(data)==before.st_size)
        # A detached/replaced directory never supplies admissible original bytes.
        require(same(os.fstat(root),os.stat(vm.parent.parent,follow_symlinks=False))
                and same(os.fstat(owned[1]),os.stat('private',dir_fd=root,follow_symlinks=False))
                and same(directory,os.stat('vm',dir_fd=owned[1],follow_symlinks=False)))
        if retain:
            owned[4]=os.open('failed-originals',os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=owned[1])
            holder=os.fstat(owned[4])
            require(stat.S_ISDIR(holder.st_mode) and holder.st_uid==uid and holder.st_mode&0o777==0o700
                    and same(holder,os.stat('failed-originals',dir_fd=owned[1],follow_symlinks=False))
                    and (retained_owner is None or directory_owner(holder)==retained_owner))
            pending=name+'.pending'
            owned[5]=os.open(pending,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=owned[4])
            at=0;view=memoryview(data)
            while at<len(view):
                count=os.write(owned[5],view[at:]);require(count>0);at+=count
            written=os.fstat(owned[5])
            require(stat.S_ISREG(written.st_mode) and written.st_uid==uid and written.st_nlink==1
                    and written.st_mode&0o777==0o600 and written.st_size==len(data))
            # link() atomically refuses an existing final name; rename() could
            # overwrite a same-UID canary appearing after the pending open.
            os.link(pending,name,src_dir_fd=owned[4],dst_dir_fd=owned[4],follow_symlinks=False)
            os.unlink(pending,dir_fd=owned[4])
            final=os.fstat(owned[5])
            require(final.st_nlink==1 and (final.st_dev,final.st_ino,final.st_uid,final.st_mode,final.st_size)==
                    (written.st_dev,written.st_ino,written.st_uid,written.st_mode,written.st_size)
                    and same(final,os.stat(name,dir_fd=owned[4],follow_symlinks=False))
                    and directory_owner(os.fstat(owned[4]))==directory_owner(holder)
                    and directory_owner(os.stat('failed-originals',dir_fd=owned[1],follow_symlinks=False))==directory_owner(holder)
                    and same(os.fstat(root),os.stat(vm.parent.parent,follow_symlinks=False))
                    and same(os.fstat(owned[1]),os.stat('private',dir_fd=root,follow_symlinks=False))
                    and same(os.fstat(owned[2]),os.stat('vm',dir_fd=owned[1],follow_symlinks=False)))
        return bytes(data)
    finally:
        try:
            for descriptor in reversed(owned):
                if descriptor is None:continue
                close_owned(descriptor)
        finally:signal.pthread_sigmask(signal.SIG_SETMASK,saved)

def finite_guest(raw,context,allowed,adapter):
    """Project only exact context and Source-vocabulary records; no operand data."""
    require(type(raw) is bytes and len(raw)<=128*1024*1024)
    rows=[];offset=0
    while offset<len(raw):
        end=raw.find(b'\n',offset)
        if end<0:break # An unfinished record never supplies an attestation.
        if raw.startswith(PREFIX,offset):
            require(end-offset<=8192 and len(rows)<1)
            def pairs(items):
                result={}
                for key,item in items:
                    require(key not in result);result[key]=item
                return result
            value=json.loads(raw[offset+len(PREFIX):end],object_pairs_hook=pairs,
                             parse_constant=lambda ignored:(_ for _ in ()).throw(ValueError()))
            require(type(value) is dict and set(value)=={'schema','context','cause','release_acceptance'}
                    and value['schema']=='arctic-final-bios-finite-cause-v1'
                    and value['context']==context and value['release_acceptance'] is False)
            cause=value['cause']
            require(type(cause) is dict and set(cause)=={'event','site','retained_original_primary_site'}
                    and cause['event']=='escaping-source-exception'
                    and adapter.finite_site(cause['site'],allowed)
                    and cause['site']['source'] in ('bios-probe','native-source')
                    and cause['site']['site_kind'] in ('raise','require'))
            primary=cause['retained_original_primary_site']
            require(primary is None or adapter.finite_site(primary,allowed)
                    and primary['source'] in ('bios-probe','native-source')
                    and primary['site_kind'] in ('raise','require'))
            rows.append(value)
        offset=end+1
    return rows

def ocr_original(raw):
    """Decode the same admitted original buffer; no path or re-encoded image."""
    result=subprocess.run(['tesseract','stdin','stdout','--psm','11'],input=raw,
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=False)
    require(result.returncode==0 and len(result.stdout)<=256*1024 and len(result.stderr)<=64*1024)
    return result.stdout

def private_failure_tail(shell,source_raw,old):
    """Remove only the optional unscreened tail from the exact staged shell."""
    raw=old.C.regular(shell,1024*1024)
    launch=b'python3 -c "$DRIVER" || rc=$?'
    staged=source_raw.replace(launch,b'python3 /arctic-lib/driver-entry.py || rc=$?',1)
    require(source_raw.count(launch)==1 and raw==staged and raw.count(FAILED_TAIL)==1)
    changed=raw.replace(FAILED_TAIL,PRIVATE_TAIL,1)
    require(changed.replace(PRIVATE_TAIL,FAILED_TAIL,1)==raw)
    pending=shell.with_name('test-install-private-tail.pending')
    old.C.exclusive(pending,changed);pending.replace(shell)

def snapshot(vm,context,old,scanner,allowed,adapter,ocr=ocr_original):
    """Called only after original execute group cleanup, before main cleanup."""
    private=vm.parent/'failed-originals'
    require(not private.exists() and not private.is_symlink())
    private.mkdir(mode=0o700)
    with snapshot_directory(private) as retained_owner:
        return snapshot_members(vm,context,old,scanner,allowed,adapter,ocr,retained_owner)

def snapshot_members(vm,context,old,scanner,allowed,adapter,ocr,retained_owner):
    public={};status={};causes={};total=0
    for name in (*UARTS,*PNGS):
        limit=UARTS[name][1] if name in UARTS else 8*1024*1024
        try:raw=read_original(vm,name,limit,os.geteuid(),retain=True,retained_owner=retained_owner)
        except FileNotFoundError:status[name]='missing';continue
        except BaseException:status[name]='acquisition-rejected';continue
        total+=len(raw)
        if total>192*1024*1024:status[name]='aggregate-rejected';continue
        if name in UARTS:
            stage=UARTS[name][0]
            try:causes[stage]=finite_guest(raw,context,allowed,adapter)
            except BaseException:causes[stage]=[]
            try:
                require(scanner.external_text(raw)==raw)
                packed=gzip.compress(raw,mtime=0);require(len(packed)<=32*1024*1024)
                public[name+'.gz']=packed;status[name]='screened'
            except BaseException:status[name]='privacy-rejected'
        else:
            try:
                require(old.original_png(raw)==raw)
                text=ocr(raw);require(type(text) is bytes and scanner.external_text(text)==text)
                public[name]=raw;status[name]='screened'
            except BaseException:status[name]='png-or-ocr-rejected'
    finite={'schema':'arctic-bios-failure-originals-v1','context':context,'member_status':status,
            'guest_source_causes':causes,'release_acceptance':False,
            'qualification_supplied':False,'manual_original_png_review_required':bool(set(public)&set(PNGS))}
    return public,finite

def attach(exact,old,channel,source_manifest,observer_adapter,scanner,ocr=ocr_original,source_shell=None):
    """Explicit failure dependencies only; retain original main code identity."""
    require(type(exact) is types.FunctionType and exact.__code__ is old.main.__code__)
    dependencies=exact.__globals__.copy();state={'context':None,'files':{},'diagnostic':None}
    original_compose=dependencies['compose'].compose
    original_execute=dependencies['execute'];original_publish=dependencies['publish']
    def compose(source,probe,security,context,output):
        result=original_compose(source,probe,security,context,output)
        if source_shell is not None:
            require(channel['shell'] is not None)
            private_failure_tail(channel['shell'],source_shell,old)
        state['context']=dict(context)
        return result
    def execute(command,log,seconds,cwd,env):
        try:return original_execute(command,log,seconds,cwd,env)
        except BaseException:
            # No retry, deadline change, error replacement or new VM operation.
            try:
                if (state['context'] is not None and channel['shell'] is not None
                        and command[:2]==['bash',str(channel['shell'])] and Path(log).name=='harness.log'
                        and command.count('--out')==1):
                    vm=Path(command[command.index('--out')+1])
                    require(vm==Path(log).parent/'vm')
                    state['files'],state['diagnostic']=snapshot(vm,state['context'],old,scanner,
                        source_manifest['allowed_sites'],observer_adapter,ocr)
            except BaseException:pass
            raise
    def publish(out,files):
        changed=files
        try:
            value=old.C.strict_json(files['host-status.json'])
            if value['status']=='failed' and state['diagnostic'] is not None:
                extra=dict(value,strict_failed_originals=state['diagnostic'])
                raw=(json.dumps(extra,sort_keys=True,indent=2)+'\n').encode()
                require(scanner.external_text(raw)==raw)
                changed=dict(files,**state['files'],**{'host-status.json':raw})
        except BaseException:pass
        return original_publish(out,changed)
    dependencies.update(compose=types.SimpleNamespace(compose=compose),execute=execute,publish=publish)
    return types.FunctionType(exact.__code__,dependencies,exact.__name__,exact.__defaults__,exact.__closure__),state

def build(manifest):
    """Bind the complete published f23 runtime closure; this never dispatches."""
    here=Path(__file__).resolve().parent;root=here.parents[1]
    require(type(manifest) is dict and set(manifest)=={'schema','ready','release_acceptance','operational_cli','base',
        'published_execution_files','source_files','image','firmware','install_network','boot_network','install_timeout',
        'harness_seconds','failure_uart_bounds','failure_png_max','failure_png_bound','failure_aggregate_bound',
        'ocr_timeout_seconds_per_image','qualification_supplied','self_execution_files'}
            and manifest['schema']=='arctic-bios-failure-originals-disabled-source-v1' and manifest['ready'] is False
            and manifest['release_acceptance'] is False and manifest['operational_cli'] is False
            and manifest['base']=='f23be8b034cfb58b171541e77f79c8fab1d43913'
            and manifest['firmware']=='bios' and manifest['install_network']==manifest['boot_network']=='offline'
            and type(manifest['install_timeout']) is int and manifest['install_timeout']==2400
            and type(manifest['harness_seconds']) is int and manifest['harness_seconds']==6600
            and manifest['failure_uart_bounds']=={name:value[1] for name,value in UARTS.items()}
            and type(manifest['failure_png_max']) is int and manifest['failure_png_max']==4
            and type(manifest['failure_png_bound']) is int and manifest['failure_png_bound']==8*1024*1024
            and type(manifest['failure_aggregate_bound']) is int and manifest['failure_aggregate_bound']==192*1024*1024
            and type(manifest['ocr_timeout_seconds_per_image']) is int and manifest['ocr_timeout_seconds_per_image']==20
            and manifest['qualification_supplied'] is False)
    require(type(manifest['self_execution_files']) is dict and set(manifest['self_execution_files'])==
            {'tools/final-bios-failure-evidence/'+n for n in ('evidence.py','test_evidence.py','README.md')})
    for name,digest in manifest['self_execution_files'].items():
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}',digest)
                and hashlib.sha256((root/name).read_bytes()).hexdigest()==digest)
    pins=manifest['published_execution_files']
    declared=json.loads((root/'tools/final-bios-observed-install/execution-manifest.json').read_bytes())
    original=dict(declared['execution_files'])
    own='tools/final-bios-observed-install/execution-manifest.json'
    original[own]=hashlib.sha256((root/own).read_bytes()).hexdigest()
    require(pins==original and manifest['source_files']==declared['source_files'] and manifest['image']==declared['image'])
    for name,digest in pins.items():
        require(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest)
    def load(name,key):
        path=root/name;raw=path.read_bytes();require(hashlib.sha256(raw).hexdigest()==pins[name])
        module=types.ModuleType(key);module.__file__=str(path)
        exec(compile(raw,str(path),'exec'),module.__dict__)
        return module
    previous=sys.modules.get('common');absent='common' not in sys.modules
    try:
        common=load('tools/final-bios-observed-install/common.py','published_bios_f23_common')
        sys.modules['common']=common
        published=load('tools/final-bios-observed-install/run.py','published_bios_f23_run')
    finally:
        if absent:sys.modules.pop('common',None)
        else:sys.modules['common']=previous
    value=common.manifest(common.strict_json((root/'tools/final-bios-observed-install/execution-manifest.json').read_bytes()),True)
    exact,old,channel=published.main_adapter(value)
    source=old.C.strict_json((root/'tools/final-bios-failure-observer/execution-manifest.json').read_bytes())
    _,_,_,_,adapter,_=published.owned_modules(value)
    scanner=load('tools/native-functional/screen-evidence.py','published_bios_f23_screen')
    return attach(exact,old,channel,source,adapter,scanner,source_shell=(root/'tools/test-install.sh').read_bytes())

def main():raise SystemExit('BIOS failure originals observer is disabled Source preparation')
if __name__=='__main__':main()
