"""UNBOUND startup logging toolkit; no VM, installation, or dispatch action.

The CLI cannot generate or launch a hook until a separately reviewed exact-ISO
attestation is pinned into this source. Host controls exercise pure helpers and
their own disposable children, never Mango or a display session.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import socket
import stat
import struct
import time

TARGET_ATTESTATION_SHA256 = None
CANDIDATE = 'fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
ISO_SHA = '84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
MANGO_SHA = 'ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866'
MAX_RAW = 4 * 1024 * 1024
MAX_RECORDS = 8192
MAX_SECONDS = 1200
UCRED = struct.Struct('3i')

def require(value, message):
    if not value: raise RuntimeError(message)

def sha(data): return hashlib.sha256(data).hexdigest()

def load_bound_attestation(path):
    require(type(TARGET_ATTESTATION_SHA256) is str and len(TARGET_ATTESTATION_SHA256)==64,
            'UNBOUND: exact candidate startup/profile/unit/ABI attestation is absent')
    p = Path(path); require(not p.is_symlink() and p.is_file() and p.stat().st_size<=4*1024*1024, 'Unsafe/overbound attestation')
    raw=p.read_bytes(); require(sha(raw)==TARGET_ATTESTATION_SHA256,'Attestation pin mismatch')
    v=json.loads(raw)
    require(v['candidate_source']==CANDIDATE and v['intended_iso_sha256']==ISO_SHA and v['mango_executable_sha256']==MANGO_SHA,
            'Candidate identity differs')
    require(v.get('status')=='exact-startup-attestation-collected' and v.get('release_acceptance') is False,
            'Attestation failed or claims acceptance')
    return v

def session_wrapper(original):
    """Preserve the shipped shell/profile chain; replace only its final exec."""
    require(type(original) is bytes and len(original)<=65536 and original.count(b'\nexec $@\n')==1,
            'Unsupported exact SDDM session ABI')
    return original.replace(b'\nexec $@\n',b'\nexec /usr/bin/python3 /run/arctic-startup-log/owned-logger.py "$@"\n')

def mango_argv(original):
    require(type(original) is list and original==['mango'] and all(type(x) is str for x in original),
            'Unexpected session command; no arbitrary argv forwarding')
    return ['mango','-d']

def proc(pid, inherited_metadata=True):
    require(type(pid) is int and pid>0,'Invalid process ID')
    p=Path('/proc')/str(pid); text=(p/'stat').read_text(); fields=text.rsplit(')',1)[1].split()
    result=dict(pid=pid,ppid=int(fields[1]),session=os.getsid(pid),pgrp=os.getpgid(pid),start_ticks=int(fields[19]),uid=p.stat().st_uid,executable=str((p/'exe').resolve()),executable_sha256=sha((p/'exe').read_bytes()),cmdline=[v.decode() for v in (p/'cmdline').read_bytes().split(b'\0') if v])
    if inherited_metadata:
        label=(p/'attr/current').read_bytes();require(len(label)<=4096,'Process security label exceeds bound');result['security_label']=label.decode(errors='strict').strip()
        result.update(cwd=str((p/'cwd').resolve()),stdin=os.readlink(p/'fd/0'),stdout=os.readlink(p/'fd/1'))
    return result

def pidfd_identity(fd,pid):
    require(type(fd) is int and fd>=0 and type(pid) is int and pid>0,'Invalid owned pidfd/PID')
    info=(Path('/proc/self/fdinfo')/str(fd)).read_bytes()
    require(len(info)<=8192,'Owned pidfd fdinfo bound exceeded')
    values=[line.split(b':',1)[1].strip() for line in info.splitlines() if line.startswith(b'Pid:')]
    require(len(values)==1 and values[0].isdigit() and int(values[0])==pid,'Owned pidfd kernel PID binding differs')
    signal.pidfd_send_signal(fd,0)
    return {'pid':pid,'kernel_fdinfo_bound':True,'signal0_permission_checked':True}

def credentials(ancillary, flags):
    """Default SCM credentials are supplied/validated by Linux, not JSON."""
    primary=None;identity=None
    try:
        require(not flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC), 'Truncated credential/data message')
        require(len(ancillary)==1,'Missing/ambiguous credential records')
        level,kind,data=ancillary[0]
        require(level==socket.SOL_SOCKET and kind==socket.SCM_CREDENTIALS and len(data)==UCRED.size,'Unexpected ancillary ABI')
        pid,uid,gid=UCRED.unpack(data)
        require(pid>0 and uid>=0 and gid>=0,'Invalid kernel credential values')
        identity=dict(pid=pid,uid=uid,gid=gid)
    except BaseException as error:primary=error
    # All unexpected received descriptors are owned by the receiver. Each close
    # is attempted exactly once even if another reports a post-close failure.
    close_errors=[]
    for level,kind,data in ancillary:
        if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:
            for (fd,) in struct.iter_unpack('i',data[:len(data)//4*4]):
                try:os.close(fd)
                except BaseException as error:close_errors.append(error)
    if primary is not None:
        for error in close_errors:primary.add_note('Received-FD cleanup also failed: '+str(error))
        raise primary
    if close_errors:
        for error in close_errors[1:]:close_errors[0].add_note('Additional received-FD cleanup failure: '+str(error))
        raise close_errors[0]
    return identity

class OwnedLog:
    """Own a fresh root/file set; attribution is per credential-bearing byte range.

    Pure host controls call capture() on their own fixture executable. Future
    guest use requires load_bound_attestation and runtime guards before capture.
    No new process group/session is created. stdout/env remain inherited.
    """
    def __init__(self, directory, max_raw=MAX_RAW, max_seconds=MAX_SECONDS):
        require(type(max_raw) is int and 0<max_raw<=MAX_RAW and type(max_seconds) in (int,float) and 0<max_seconds<=MAX_SECONDS,
                'Invalid logger numeric bounds')
        self.root=Path(directory)
        require(self.root.is_absolute() and self.root==self.root.resolve() and not self.root.exists() and not self.root.is_symlink(),
                'Logger output collision/parent symlink')
        self.root.mkdir(mode=0o700); self.identity=(self.root.stat().st_dev,self.root.stat().st_ino,os.getuid())
        self.max_raw=max_raw; self.max_seconds=max_seconds; self.pid=None; self.pidfd=None; self.reaped=False
        self.sender=None; self.receiver=None; self.gate_read=None; self.gate_write=None; self.launch_released=False
    def owned_root(self):
        v=self.root.lstat()
        require(stat.S_ISDIR(v.st_mode) and not self.root.is_symlink() and (v.st_dev,v.st_ino,v.st_uid)==self.identity
                and stat.S_IMODE(v.st_mode)==0o700,'Logger output identity/owner changed')
    def capture(self, executable, argv, expected_sha, expected_uid=0, environment=None, execution_identity=None, trace_stop=None, native_proof=None):
        require(trace_stop is None or callable(trace_stop),'Invalid owned stop reader')
        require(native_proof is None or callable(native_proof),'Invalid native proof reader')
        self.owned_root(); require(type(argv) is list and argv and all(type(v) is str for v in argv),'Invalid logger argv')
        require(type(expected_uid) is int and expected_uid>=0,'Invalid executable owner binding')
        require(environment is None or (type(environment) is dict and all(type(k) is bytes and type(v) is bytes and k and b'=' not in k and b'\0' not in k+v for k,v in environment.items())),
                'Unsupported explicit environment mapping')
        require(execution_identity is None or (os.geteuid()==0 and type(execution_identity) is dict and set(execution_identity)=={'uid','gid'} and all(type(v) is int and v>0 for v in execution_identity.values())),
                'Invalid fixture-only dropped execution identity')
        expected_sender=execution_identity or dict(uid=os.geteuid(),gid=os.getegid())
        fd=os.open(executable,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        outer_primary=None;cleanup_attempted=False
        try:
            info=os.fstat(fd); require(stat.S_ISREG(info.st_mode) and info.st_uid==expected_uid and not info.st_mode & 0o6022
                                      and 0<info.st_size<=64*1024*1024,'Unsafe executable owner/mode/size')
            require(sha(os.pread(fd,info.st_size,0))==expected_sha,'Executable bytes changed')
            self.receiver,self.sender=socket.socketpair(socket.AF_UNIX,socket.SOCK_STREAM)
            self.receiver.setsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED,1)
            require(self.receiver.getsockopt(socket.SOL_SOCKET,socket.SO_PASSCRED)==1,'SO_PASSCRED unavailable')
            probe=os.pidfd_open(os.getpid(),0); os.close(probe)
            self.gate_read,self.gate_write=os.pipe2(os.O_CLOEXEC)
            started=time.monotonic_ns(); self.pid=os.fork()
            if self.pid==0:
                try:
                    os.close(self.gate_write)
                    # No target exec until the parent owns a usable pidfd.
                    go=os.read(self.gate_read,1); os.close(self.gate_read)
                    if go!=b'G':os._exit(125)
                    self.receiver.close(); os.dup2(self.sender.fileno(),2); self.sender.close()
                    if execution_identity is not None:
                        os.setgroups([]);os.setgid(execution_identity['gid']);os.setuid(execution_identity['uid'])
                    # FD exec pins the exact open ELF; its CLOEXEC closes it.
                    os.execve(fd,argv,dict(os.environ) if environment is None else environment)
                except BaseException as error:
                    os.write(2,('Owned exec failed: '+type(error).__name__+': '+str(error)+'\n').encode())
                    os._exit(125)
            owned_sender=self.sender;self.sender=None;owned_sender.close()
            owned_gate_read=self.gate_read;self.gate_read=None;os.close(owned_gate_read)
            rows=[]; raw=bytearray(); eof=False; status=None; primary=None; controlled_stop=False; stop_origin=None; stop_kill=False; last_data=None; stream_end=None
            try:
                self.pidfd=os.pidfd_open(self.pid,0)
                owned_pidfd=pidfd_identity(self.pidfd,self.pid)
                before_release=proc(self.pid)
                require(type(before_release['pid']) is int and before_release['pid']==self.pid and type(before_release['start_ticks']) is int and before_release['start_ticks']>0,'Owned child start identity unavailable')
                require(os.write(self.gate_write,b'G')==1,'Owned child launch handshake failed')
                self.launch_released=True;owned_gate_write=self.gate_write;self.gate_write=None;os.close(owned_gate_write)
                native_identity=native_proof(self.pid,expected_sha,argv) if native_proof is not None else None
                with (self.root/'stderr.raw').open('xb') as output:
                    if trace_stop is not None:os.fchmod(output.fileno(),0o600)
                    while not eof:
                        require((time.monotonic_ns()-started)/1e9<=self.max_seconds,'Owned logger deadline exceeded')
                        self.owned_root()
                        if trace_stop is not None:
                            native_exit=os.waitid(os.P_PID,self.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                            require(native_exit is None or (native_exit.si_pid==self.pid and controlled_stop),'Native exited before explicit trace end')
                        if trace_stop is not None and not controlled_stop and trace_stop():
                            controlled_stop=True;stop_origin=time.monotonic_ns()
                            signal.pidfd_send_signal(self.pidfd,signal.SIGTERM)
                        if controlled_stop:
                            elapsed=(time.monotonic_ns()-stop_origin)/1e9
                            require(elapsed<=3,'Owned trace termination/drain exceeded bound')
                            if elapsed>=1 and not stop_kill:
                                still=os.waitid(os.P_PID,self.pid,os.WEXITED|os.WNOHANG|os.WNOWAIT)
                                if still is None:signal.pidfd_send_signal(self.pidfd,signal.SIGKILL)
                                stop_kill=True
                            if native_exit is not None and (time.monotonic_ns()-(last_data or stop_origin))/1e9>=.2:
                                # Keep the direct child's PID reserved through
                                # closure. Other inherited writers are not ours
                                # to signal; their future tail is unqualified.
                                stream_end='owned-native-exited-and-200ms-quiet';break
                        ready,_,_=select.select([self.receiver],[],[],.05)
                        if ready:
                            data,ancillary,flags,_=self.receiver.recvmsg(65536,socket.CMSG_SPACE(UCRED.size)+socket.CMSG_SPACE(4))
                            if not data:
                                eof=True;stream_end='socket-EOF';continue
                            identity=credentials(ancillary,flags)
                            if identity['pid']==self.pid:
                                require(identity['uid']==expected_sender['uid'] and identity['gid']==expected_sender['gid'],'Owned native sender UID/GID differs')
                            require(len(raw)+len(data)<=self.max_raw and len(rows)<MAX_RECORDS,'Owned logger output bound exceeded')
                            last_data=time.monotonic_ns();begin=len(raw); raw.extend(data); output.write(data); output.flush()
                            rows.append(dict(**identity,begin=begin,end=len(raw),received_monotonic_ns=time.monotonic_ns(),sha256=sha(data),
                                             origin='owned-launch-process' if identity['pid']==self.pid else 'other-sender-unqualified'))
                        # Do not reap while other inherited writers remain: the
                        # direct-child PID stays reserved until the socket EOF.
                    # Startup trace never treats early EOF/exit as success.
                    if trace_stop is not None:
                        require(controlled_stop,'Owned trace exited before explicit end')
                    # Fixture EOF follows the original verified cleanup route.
                    if status is None:
                        end=time.monotonic()+3
                        while time.monotonic()<end:
                            waited,value=os.waitpid(self.pid,os.WNOHANG)
                            if waited:status=value;self.reaped=True;break
                            time.sleep(.01)
                        require(status is not None,'Owned child survived stderr EOF')
                    if trace_stop is None:require(os.waitstatus_to_exitcode(status)==0,'Owned child exit failed')
                    else:require(os.waitstatus_to_exitcode(status) in (0,-signal.SIGTERM,-signal.SIGKILL),'Owned trace native exit failed')
                result=dict(native_identity=native_identity,status='owned-trace-collected' if controlled_stop else 'owned-log-collected',raw_bytes=len(raw),raw_sha256=sha(raw),rows=rows,child_pid=self.pid,
                            start_monotonic_ns=started,end_monotonic_ns=time.monotonic_ns(),cleanup='owned-child-reaped',
                            environment_sha256=sha(b'\0'.join(k.encode()+b'='+v.encode() for k,v in sorted(os.environ.items()))),
                            inherited_child_writes_qualified_as_mango=False,release_acceptance=False,controlled_stop=controlled_stop,stream_end=stream_end,unowned_inherited_writers_signalled=False,future_inherited_writer_tail_qualified=False,
                            owned_child_start_ticks=before_release['start_ticks'],owned_pidfd_identity=owned_pidfd,expected_sender_uid_gid=expected_sender,
                            native_environment_source='explicit-byte-mapping-unqualified-runtime' if environment is not None else 'logger-environment-unqualified',
                            native_environment_sha256=sha(b'\0'.join(k+b'='+v for k,v in environment.items())+b'\0') if environment is not None else None)
            except BaseException as exc:primary=exc;raise
            finally:
                cleanup_attempted=True
                try:self.cleanup()
                except BaseException as cleanup_error:
                    if primary is None:raise
                    primary.add_note('Owned cleanup also failed: '+str(cleanup_error))
            # Publish success only after the owned lifecycle has actually closed.
            self.owned_root()
            require(self.reaped and self.pidfd is None and self.receiver is None and self.sender is None
                    and self.gate_read is None and self.gate_write is None,'Owned lifecycle incomplete')
        except BaseException as error:
            outer_primary=error
            raise
        finally:
            errors=[]
            # Every owned close is attempted once, with no retry after ambiguous
            # close failure. Full success publication follows this outer scope.
            try:os.close(fd)
            except BaseException as error:errors.append(error)
            if not cleanup_attempted:
                cleanup_attempted=True
                try:self.cleanup()
                except BaseException as error:errors.append(error)
            if errors:
                if outer_primary is not None:
                    for error in errors:outer_primary.add_note('Outer owned cleanup also failed: '+str(error))
                else:
                    for error in errors[1:]:errors[0].add_note('Additional outer owned cleanup failure: '+str(error))
                    raise errors[0]
        self.owned_root()
        require(self.reaped and self.pidfd is None and self.receiver is None and self.sender is None
                and self.gate_read is None and self.gate_write is None,'Outer owned lifecycle incomplete')
        with (self.root/'log-report.json').open('x') as output:
            if trace_stop is not None:os.fchmod(output.fileno(),0o600)
            output.write(json.dumps(result,indent=2,sort_keys=True)+'\n')
        return result
    def cleanup(self):
        errors=[]
        def close_fd(name):
            value=getattr(self,name)
            if value is None:return
            # Do not retry close after an error: FD ownership may be ambiguous.
            setattr(self,name,None)
            try:os.close(value)
            except BaseException as error:errors.append(error)
        close_fd('gate_write');close_fd('gate_read')
        try:
            # EOF releases a still-gated child only to _exit, never target exec.
            if self.pid is not None and not self.reaped and not self.launch_released:
                end=time.monotonic()+3
                while time.monotonic()<end:
                    waited,_=os.waitpid(self.pid,os.WNOHANG)
                    if waited:self.reaped=True;break
                    time.sleep(.01)
                require(self.reaped,'Gated child failed to exit; no PID signal fallback')
            if self.pid is not None and not self.reaped:
                waited,_=os.waitpid(self.pid,os.WNOHANG)
                if waited:self.reaped=True
            if self.pid is not None and not self.reaped:
                require(self.pidfd is not None,'Owned child cleanup lacks pidfd; no PID signal fallback')
                signal.pidfd_send_signal(self.pidfd,signal.SIGTERM)
                end=time.monotonic()+1
                while time.monotonic()<end:
                    waited,_=os.waitpid(self.pid,os.WNOHANG)
                    if waited:self.reaped=True;break
                    time.sleep(.01)
                if not self.reaped:
                    signal.pidfd_send_signal(self.pidfd,signal.SIGKILL)
                    end=time.monotonic()+2
                    while time.monotonic()<end:
                        waited,_=os.waitpid(self.pid,os.WNOHANG)
                        if waited:self.reaped=True;break
                        time.sleep(.01)
                require(self.reaped,'Owned child could not be reaped')
        except BaseException as error:errors.append(error)
        finally:
            for name in ('sender','receiver'):
                value=getattr(self,name)
                if value is not None:
                    setattr(self,name,None)
                    try:value.close()
                    except BaseException as error:errors.append(error)
            close_fd('pidfd')
        if errors:
            for error in errors[1:]:errors[0].add_note('Additional owned cleanup failure: '+str(error))
            raise errors[0]

def authenticated_lines(raw, rows, writer):
    """No message/line is joined across different credential-bearing writers.

    This returns data provenance only. A future renderer parser must also bind
    actual binary/library/source origins and reject absent/conflicting values.
    """
    require(type(raw) is bytes and len(raw)<=MAX_RAW and type(rows) is list and len(rows)<=MAX_RECORDS,'Invalid log bounds')
    require(type(writer) is dict and set(writer)=={'pid','uid','gid'} and all(type(v) is int and v>=0 for v in writer.values())
            and writer['pid']>0,'Invalid writer identity')
    offset=0
    for row in rows:
        require(type(row) is dict and all(type(row.get(k)) is int and row[k]>=0 for k in ('pid','uid','gid','begin','end'))
                and row['pid']>0 and row['begin']==offset<row['end']<=len(raw)
                and row.get('sha256')==sha(raw[row['begin']:row['end']]),'Missing/overlapping/substituted credential ranges')
        offset=row['end']
    require(offset==len(raw),'Credential ranges do not cover raw bytes')
    output=[];start=0
    for line in raw.splitlines(keepends=True):
        stop=start+len(line);ranges=[r for r in rows if r['begin']<stop and r['end']>start]
        owned=bool(ranges) and all(all(r[k]==writer[k] for k in writer) for r in ranges)
        output.append(dict(begin=start,end=stop,complete=line.endswith(b'\n'),authenticated_writer=owned,
                           status='owned-complete-line' if owned and line.endswith(b'\n') else 'ambiguous-or-incomplete',
                           sha256=sha(line)))
        start=stop
    return output

def main():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('attestation',type=Path);args=parser.parse_args()
    load_bound_attestation(args.attestation)
    raise RuntimeError('Startup hook remains UNBOUND: generator/mount/drop-in/runtime source proof must be separately reviewed')

if __name__=='__main__':main()
