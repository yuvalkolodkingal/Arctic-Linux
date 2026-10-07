"""Own finite synthetic fixtures only; no session, Mango, profile or device work."""
import errno
import fcntl
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time

HERE=Path(__file__).resolve().parent
def require(value,message):
    if not value:raise RuntimeError(message)
def sha(value):return hashlib.sha256(value).hexdigest()
def load(name):
    spec=importlib.util.spec_from_file_location('runtime_'+name,HERE/(name+'.py'))
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def fixture(argv,environment,cwd):
    """A newly created fixture session owns only its own fixed source children.

    No normal desktop process is moved or signalled. A child PID is not reaped
    before communicate finishes. Verified groups retain the original cleanup;
    acquisition failure permits only a kernel-proven direct-child reap, never
    unverified group signalling. Every pipe/pidfd close is attempted.
    """
    require(type(argv) is list and 1<=len(argv)<=64 and all(type(v) is str and '\0' not in v for v in argv),'Fixture argv type/bound')
    require(type(environment) is dict and all(type(k) is bytes and type(v) is bytes and k and b'=' not in k and b'\0' not in k+v for k,v in environment.items()),'Fixture byte environment type')
    process=None;pidfd=None;primary=None;result=None;group=None;errors=[];begin=time.monotonic_ns()
    try:
        process=subprocess.Popen(argv,env=environment,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        pidfd=os.pidfd_open(process.pid,0)
        group=os.getpgid(process.pid);require(group==process.pid and group!=os.getpgrp(),'Own synthetic process group unavailable')
        stdout,stderr=process.communicate(timeout=5)
        require(process.returncode==0,'Owned synthetic fixture nonzero exit')
        require(len(stdout)<=1024*1024 and len(stderr)<=65536 and stderr==b'','Owned fixture output bound/error')
        require(time.monotonic_ns()-begin<=5*10**9,'Owned synthetic fixture exceeded5s')
        result=stdout
    except BaseException as error:primary=error
    finally:
        # The new session/PGID belongs to this Popen, whose PID is reserved until
        # wait below. No lookup of an existing process or normal session occurs.
        if process is not None and process.returncode is None:
            try:
                verified_group=False
                if group==process.pid:
                    try:
                        require(os.getpgid(process.pid)==group,'Own fixture cleanup group changed')
                        verified_group=True
                    except BaseException as error:
                        # A failed later lookup remains fatal. Retained direct
                        # pidfd ownership still permits the child-only fallback.
                        errors.append(error)
                if verified_group:
                    try:os.killpg(group,signal.SIGTERM)
                    except ProcessLookupError:pass
                    # Keep the direct PID reserved until the entire verified
                    # owned group receives KILL; no poll/wait reaps it here.
                    time.sleep(.05)
                    try:os.killpg(group,signal.SIGKILL)
                    except ProcessLookupError:pass
                else:
                    # Acquisition failed before a group was proven. A retained
                    # pidfd binds the still-unreaped direct child. Without it,
                    # waitid proves direct-child ownership: None means running;
                    # WNOWAIT reserves even an exited child until wait below.
                    # This branch makes no group/descendant cleanup claim.
                    try:
                        if pidfd is not None:
                            # The descriptor was acquired while this direct
                            # Popen child was unreaped, before group inspection.
                            signal.pidfd_send_signal(pidfd,signal.SIGKILL)
                        else:
                            proof=os.waitid(os.P_PID,process.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                            require(proof is None or proof.si_pid==process.pid,'Own direct-child reservation changed')
                            process.kill()
                    except ProcessLookupError:pass
            except BaseException as error:errors.append(error)
            # Always attempt the finite direct-child reap, even when a proof
            # or signal failed. Failure stays fatal with the original primary.
            try:process.wait(timeout=2)
            except BaseException as error:errors.append(error)
        if process is not None:
            for stream in (process.stdout,process.stderr):
                if stream is not None and not stream.closed:
                    try:stream.close()
                    except BaseException as error:errors.append(error)
        if pidfd is not None:
            try:os.close(pidfd)
            except BaseException as error:errors.append(error)
        if primary is not None:
            for error in errors:primary.add_note('Own fixture cleanup also failed: '+str(error))
        elif errors:
            primary=errors[0]
            for error in errors[1:]:primary.add_note('Additional own fixture cleanup failure: '+str(error))
    if primary is not None:raise primary
    require(process is not None and process.returncode==0 and result is not None and process.stdout.closed and process.stderr.closed,'Own fixture lifecycle incomplete')
    return result

def seal_controls():
    E=load('sealed_environment');rows=[]
    cases=[('valid',E.MAGIC+b'PATH=/usr/bin:/bin\0',15,os.getuid(),None),
           ('duplicate',E.MAGIC+b'A=one\0A=two\0',15,os.getuid(),'Duplicate'),
           ('unterminated',E.MAGIC+b'A=one',15,os.getuid(),'Truncated'),
           ('unsealed',E.MAGIC+b'A=one\0',0,os.getuid(),'sealed'),
           ('wrong-owner',E.MAGIC+b'A=one\0',15,os.getuid()+1,'owner')]
    for label,data,seals,owner,expected in cases:
        fd=os.memfd_create('arctic-owned-prerequisite',os.MFD_ALLOW_SEALING)
        consumed=False;error=None;value=None
        try:
            require(os.write(fd,data)==len(data),'Own memfd short write')
            if seals:fcntl.fcntl(fd,getattr(fcntl,'F_ADD_SEALS',1033),seals)
            consumed=True
            try:value=E.consume(fd,owner)
            except RuntimeError as failed:error=str(failed)
            try:os.fstat(fd)
            except OSError as failed:require(failed.errno==errno.EBADF,'Own seal descriptor close unproven')
            else:raise RuntimeError('Own seal descriptor survived consumption')
            require((expected is None and value=={b'PATH':b'/usr/bin:/bin'} and error is None)
                    or (expected is not None and value is None and error is not None and expected.lower() in error.lower()),'Seal negative/positive outcome differs')
            rows.append(dict(label=label,status='accepted-exact' if expected is None else 'rejected-expected',FD_closed=True,error=error))
        finally:
            if not consumed:os.close(fd)
    return rows

def synthetic_environment_cases(root,provider,carrier,bash):
    root=Path(root);missing=root/'never-source';require(not missing.exists() and not missing.is_symlink(),'Synthetic BASH_ENV collision')
    cases=[('ordinary',{b'PATH':b'/usr/bin:/bin',b'LANG':b'C.UTF-8'},False),
           ('locale',{b'PATH':b'/usr/bin:/bin',b'LANG':b'he_IL.UTF-8',b'LC_ALL':b'C.UTF-8'},False),
           ('bytes',{b'PATH':b'/usr/bin:/bin',b'LANG':b'C.UTF-8',b'LITERAL':b'line1\n$(not-executed);`literal`',b'BYTE':b'\xff\xfe'},False),
           ('quoted-final-bash',{b'PATH':b'/usr/bin:/bin',b'LANG':b'C.UTF-8',b'SHELL':b'/bin/bash',b'HOME':os.fsencode(root),b'PWD':os.fsencode(root),b'BASH_ENV':os.fsencode(missing),b'_':b'synthetic-original'},True)]
    rows=[]
    for label,environment,through_bash in cases:
        prefix=[bash,'--noprofile','--norc','-c','exec "$@"','owned-final-exec-fixture'] if through_bash else []
        direct=fixture(prefix+[provider],environment,root)
        handed=fixture(prefix+[carrier],environment,root)
        require(direct==handed and direct.endswith(b'\0'),'Synthetic native byte parity differs')
        if not through_bash:require(direct==b''.join(k+b'='+v+b'\0' for k,v in environment.items()),'Direct synthetic environment changed')
        require(not missing.exists() and not missing.is_symlink(),'Synthetic BASH_ENV appeared')
        rows.append(dict(label=label,direct_sha256=sha(direct),handoff_sha256=sha(handed),bytes=len(direct),byte_exact=True,
                         boundary='owned-quoted-final-Bash-only' if through_bash else 'direct-native-only',actual_session_environment=False))
    return rows

def quoted_argv_control(root,provider,bash):
    root=Path(root);missing=root/'never-source';marker=root/'must-not-be-created'
    require(not marker.exists() and not marker.is_symlink() and not missing.exists() and not missing.is_symlink(),'Own argument fixture collision')
    arguments=['space value','line1\nline2','literal;$(touch '+str(marker)+');`echo literal`']
    environment={b'PATH':b'/usr/bin:/bin',b'LANG':b'C.UTF-8',b'HOME':os.fsencode(root),b'PWD':os.fsencode(root),b'BASH_ENV':os.fsencode(missing)}
    direct=fixture([provider,*arguments],environment,root)
    argv=[bash,'--noprofile','--norc','-c','exec "$@"','owned-final-exec-fixture',provider,*arguments]
    quoted=fixture(argv,environment,root)
    require(direct==quoted==b''.join(os.fsencode(v)+b'\0' for v in arguments),'Quoted final-exec synthetic argv differs')
    require(not marker.exists() and not marker.is_symlink() and not missing.exists() and not missing.is_symlink(),'Synthetic argv executed/changed missing path')
    return dict(status='owned-quoted-argv-byte-exact',arguments=arguments,bash_argv=argv,cwd=str(root),HOME=str(root),BASH_ENV=str(missing),
                absent_BASH_ENV=True,marker_absent=True,direct_sha256=sha(direct),quoted_sha256=sha(quoted),bytes=len(direct),
                actual_session_argument_fidelity=False,carrier_argument_forwarding=False)
