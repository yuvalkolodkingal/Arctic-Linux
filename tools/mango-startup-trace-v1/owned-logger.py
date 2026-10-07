"""Only the selected sealed final-boundary command; no CLI restart/fallback."""
import sys
sys.dont_write_bytecode=True
import importlib.util
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
ROOT=Path('/run/arctic-mango-trace')
MANGO_SHA='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866'
ENV_MAGIC=b'ARCTIC_ENV_V1\0'
ARGV_MAGIC=b'ARCTIC_TRACE_ARGV_V1\0'

def require(v,m):
    if not v:raise RuntimeError(m)
def sha(v):return hashlib.sha256(v).hexdigest()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v);return v

def consume_pair(envfd,argfd,uid):
    require(type(envfd) is int and type(argfd) is int and envfd>=3 and argfd>=3 and envfd!=argfd,'Invalid distinct sealed FDs')
    results=[];primary=None
    # Both received descriptors are attempted once even after first validation
    # failure. No target can be opened/launched until all closes succeed.
    for fd,magic,limit in ((envfd,ENV_MAGIC,1048576),(argfd,ARGV_MAGIC,128)):
        try:
            info=os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and info.st_uid==uid and 0<info.st_size<=limit,'Snapshot type/owner/bound differs')
            require(fcntl.fcntl(fd,1034)&15==15,'Snapshot not completely sealed')
            raw=os.pread(fd,info.st_size,0)
            require(len(raw)==info.st_size and os.pread(fd,1,info.st_size)==b'' and raw.startswith(magic),'Snapshot size/magic differs')
            results.append(raw)
        except BaseException as error:
            if primary is None:primary=error
            else:primary.add_note('Additional snapshot validation: '+str(error))
        finally:
            try:os.close(fd)
            except BaseException as error:
                if primary is None:primary=error
                else:primary.add_note('Snapshot close also failed: '+str(error))
    if primary is not None:raise primary
    require(results[1]==ARGV_MAGIC+b'mango\0','Unapproved boundary argv')
    S=module('trace_env',ROOT/'sealed_environment.py')
    env=S.parse_payload(results[0])
    require(env.get(b'SHELL')==b'/bin/bash' and b'BASH_ENV' not in env,'Unsupported Bash boundary environment')
    return env,dict(boundary_argv=['mango'],boundary_argv_sha256=sha(results[1]),boundary_environment_sha256=sha(results[0]),
                    native_environment_body_sha256=sha(results[0][len(ENV_MAGIC):]),
                    underscore_value_sha256=sha(env[b'_']) if b'_' in env else None,
                    locale_keys_count=sum(k==b'LANG' or k.startswith(b'LC_') for k in env),locale_key_names_sha256=sha(b'\0'.join(k for k in env if k==b'LANG' or k.startswith(b'LC_'))))

def owned_stop():
    p=ROOT/'stop'
    try:v=p.lstat()
    except FileNotFoundError:return False
    require(stat.S_ISREG(v.st_mode) and v.st_uid==0 and v.st_gid==0 and stat.S_IMODE(v.st_mode)==0o644 and v.st_size==len(b'ARCTIC_TRACE_END_V1\n'),'Invalid root-owned trace stop')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);primary=None
    try:
        a=os.fstat(fd);raw=os.read(fd,128);b=os.fstat(fd)
        require((a.st_dev,a.st_ino,a.st_mode,a.st_uid,a.st_gid,a.st_size,a.st_mtime_ns,a.st_ctime_ns)==(v.st_dev,v.st_ino,v.st_mode,v.st_uid,v.st_gid,v.st_size,v.st_mtime_ns,v.st_ctime_ns)==(b.st_dev,b.st_ino,b.st_mode,b.st_uid,b.st_gid,b.st_size,b.st_mtime_ns,b.st_ctime_ns) and raw==b'ARCTIC_TRACE_END_V1\n','Changed stop identity/content')
    except BaseException as error:primary=error;raise
    finally:
        try:os.close(fd)
        except BaseException as error:
            if primary is None:raise
            primary.add_note('Stop close also failed: '+str(error))
    return True

def native_proof(pid,expected_sha,argv):
    # Only the gated owned PID can reach this FD exec. A bounded procfs
    # observation confirms the current native image; it is not whole-history
    # or an atomic claim about all prior writes.
    T=module('native_identity_reader',ROOT/'owned-log.py')
    end=time.monotonic()+2
    while time.monotonic()<end:
        p=T.proc(pid)
        if p['executable_sha256']==expected_sha:
            parent=T.proc(os.getpid())
            require(p['uid']==1000 and p['ppid']==os.getpid() and p['cmdline']==argv and p['executable']=='/usr/bin/mango','Native image/argv/parent identity differs')
            require(all(p[k]==parent[k] for k in ('session','pgrp','cwd','stdin','stdout')),'Undeclared native boundary inheritance difference')
            return dict(**p,observed_monotonic_ns=time.monotonic_ns(),scope='current owned native FD-exec identity; not global first/history')
        time.sleep(.005)
    raise RuntimeError('Owned native image not observed before initialization log drain')

def absent_selected_mango():
    entries=[p for p in Path('/proc').iterdir() if p.name.isdigit()]
    require(len(entries)<=4096,'Process absence observation exceeds bound')
    for p in entries:
        try:
            if p.stat().st_uid!=1000:continue
            exe=p/'exe'
            if exe.resolve().name=='mango':raise RuntimeError('Selected-user Mango already present at final boundary')
        except FileNotFoundError:continue
    return dict(observed_monotonic_ns=time.monotonic_ns(),scope='current finite procfs observation only; no earlier exited history')

def main():
    require(len(sys.argv)==3 and all(s.isascii() and s.isdigit() for s in sys.argv[1:]),'Invalid native carrier FD arguments')
    require(os.getuid()==1000 and os.getgid()==1000,'Unexpected selected live identity')
    r=ROOT.lstat();require(stat.S_ISDIR(r.st_mode) and r.st_uid==0 and r.st_gid==0 and stat.S_IMODE(r.st_mode)==0o755 and not ROOT.is_symlink(),'Unsafe root trace boundary')
    env,boundary=consume_pair(int(sys.argv[1]),int(sys.argv[2]),os.getuid())
    # Exclusive one-attempt token is never cleared for a second session launch.
    token=ROOT/'user'/'attempt'
    fd=os.open(token,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600)
    primary=None
    try:os.fchmod(fd,0o600)
    except BaseException as error:primary=error;raise
    finally:
        try:os.close(fd)
        except BaseException as error:
            if primary is None:raise
            primary.add_note('Attempt token close also failed: '+str(error))
    absence=absent_selected_mango()
    T=module('trace_ownership',ROOT/'owned-log.py')
    logger=T.OwnedLog(ROOT/'user'/'capture',max_seconds=1200)
    result=logger.capture('/usr/bin/mango',['mango','-d'],MANGO_SHA,environment=env,trace_stop=owned_stop,native_proof=native_proof)
    result.update(all_owned_FDs_closed=True,boundary=boundary,boundary_absence=absence,native_argv=['mango','-d'],startup_perturbation=True,normal_session_fidelity=False,complete_chain=False,safe_visual_gate='OPEN',renderer='requires-authenticated-raw-log-review')
    # capture() has closed outer ELF+socket+gate+pidfd and reaped its direct child.
    full=(ROOT/'user/capture/log-report.json').read_bytes()
    require(0<len(full)<=4194304,'Full native receipt exceeds existing body cap')
    result={k:v for k,v in result.items() if k!='rows'}
    result['sender_ranges_body']={'path':'log-report.json','bytes':len(full),'sha256':sha(full),'rows':len(json.loads(full)['rows'])}
    encoded=json.dumps(result,sort_keys=True).encode()+b'\n'
    require(len(encoded)<=262144,'Terminal receipt exceeds unchanged marker cap')
    temporary=ROOT/'user'/'terminal.tmp'
    with temporary.open('x') as f:
        os.fchmod(f.fileno(),0o600);f.write(encoded.decode())
    # A successful close precedes the only final receipt publication.
    temporary.rename(ROOT/'user'/'terminal.json')
if __name__=='__main__':
    import signal
    def interrupted(number,frame):raise RuntimeError('Owned native logger interrupted: '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    main()
