"""Root receipt survives only the logger-owned user compositor termination.

This component does not change services, security, drivers, or renderer choice.
Its separate ephemeral unit, CD bootstrap, and host integration are separately
source-gated; it may not be invoked on a normal machine.
"""
import sys
sys.dont_write_bytecode=True
import importlib.util,json,os,select,signal,stat,time
from pathlib import Path
ROOT=Path('/run/arctic-mango-trace')

def require(v,m):
    if not v:raise RuntimeError(m)
def module(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def pidfd(pid):
    require(type(pid) is int and pid>0,'Typed logger PID required')
    fd=os.pidfd_open(pid,0)
    try:
        info=Path('/proc/self/fdinfo',str(fd)).read_text();values=[x.split(':',1)[1].strip() for x in info.splitlines() if x.startswith('Pid:')]
        require(values==[str(pid)],'Logger pidfd namespace/identity differs');signal.pidfd_send_signal(fd,0)
    except BaseException as primary:
        try:os.close(fd)
        except BaseException as e:primary.add_note('Pidfd close also failed: '+str(e))
        raise
    return fd

def observed_logger():
    matches=[]
    folders=list(Path('/proc').iterdir());require(len(folders)<=8192,'Process observation exceeds bound')
    for folder in folders:
        if not folder.name.isdigit():continue
        try:
            if folder.stat().st_uid!=1000:continue
            raw=(folder/'cmdline').read_bytes()
            argv=raw.split(b'\0')[:-1]
            if len(argv)==6 and argv[:4]==[b'python3.14',b'-I',b'-S',str(ROOT/'owned-logger.py').encode()]:
                proof=module('trace_process',ROOT/'owned-log.py').proc(int(folder.name))
                require(proof['executable_sha256']=='0d64bd6d66d68dac91cdadafc46e22d4f09f22bdc997aaae870f42865b024a3e' and proof['uid']==1000 and all(a.isdigit() for a in argv[4:]),'Logger executable/argument identity differs')
                T=module('trace_parent',ROOT/'owned-log.py')
                parent=T.proc(proof['ppid'],inherited_metadata=False)
                require(parent['executable_sha256']=='93ab003b0453179eb1f0e6a7a51a20ee322af4992300d095403c5f728b7a68e4','Selected SDDM helper parent identity differs')
                proof['selected_helper_parent']=parent
                matches.append(proof)
        except FileNotFoundError:continue
    require(len(matches)<=1,'Multiple diagnostic loggers')
    return matches[0] if matches else None

def rollback(state):
    # Controller reads/exports user payloads before entering this fixed owned
    # path cleanup. Never recursively follow a user-created path or guess it.
    P=module('trace_prepare',ROOT/'prepare.py')
    user=ROOT/'user';capture=user/'capture'
    expected={'attempt','terminal.json','capture'}
    require(set(p.name for p in user.iterdir())==expected,'Unexpected user output set')
    require(set(p.name for p in capture.iterdir())=={'stderr.raw','log-report.json'},'Unexpected capture output set')
    proof=[]
    for p in [capture/'stderr.raw',capture/'log-report.json',user/'attempt',user/'terminal.json',capture]:
        v=p.lstat();require(v.st_uid==1000 and v.st_gid==1000 and not p.is_symlink(),'Output identity/type/owner differs')
        require((stat.S_ISDIR(v.st_mode) and stat.S_IMODE(v.st_mode)==0o700) if p==capture else (stat.S_ISREG(v.st_mode) and stat.S_IMODE(v.st_mode)==0o600),'Unexpected output type/mode')
        proof.append((p,P.identity(v)))
    # Check the full static owned set before deleting anything. Separate checks
    # are non-atomic. A changed/missing node stops deletion, never broad cleanup.
    for record in state['owned']:
        p=Path(record['path']);require(P.identity(p.lstat())==tuple(record['identity']),'Owned rollback identity changed')
        if 'sha256' in record:require(P.read(p,64*1024*1024)[1]['sha256']==record['sha256'],'Owned rollback content changed')
    stop=ROOT/'stop';stopraw,stopproof=P.read(stop,mode=0o644)
    require(stopraw==b'ARCTIC_TRACE_END_V1\n','Root-owned stop content differs')
    for p,v in proof:
        require(P.identity(p.lstat())==v,'Output changed during rollback')
        p.rmdir() if p==capture else p.unlink()
    for record in reversed(state['owned']):
        p=Path(record['path']);require(P.identity(p.lstat())==tuple(record['identity']),'Owned rollback node changed')
        if p==ROOT:continue
        p.rmdir() if p==user else p.unlink()
    require(P.identity(stop.lstat())==(stopproof['device'],stopproof['inode'],0,0,0o644),'Stop identity changed');stop.unlink()
    statepath=ROOT/'state.json';v=statepath.lstat();require(v.st_uid==0 and v.st_gid==0 and stat.S_ISREG(v.st_mode),'State identity unsafe');statepath.unlink()
    require(not list(ROOT.iterdir()),'Owned runtime directory not empty');ROOT.rmdir()
    return dict(runtime_and_one_config_removed=True,normal_target_replacement=False,renderer_or_security_change=False)

def collect():
    require(os.geteuid()==0,'Root collector required')
    P=module('trace_prepare',ROOT/'prepare.py')
    raw,_=P.read(ROOT/'state.json',mode=0o600);state=json.loads(raw)
    end=time.monotonic()+1200;observed=None;fd=None;primary=None
    try:
        # Bind the current native logger process before waiting for terminal
        # output. This is one target boundary, not startup/global-first proof.
        while observed is None and time.monotonic()<end:
            observed=observed_logger()
            if observed is None:time.sleep(.01)
        require(observed is not None,'Logger never observed')
        fd=pidfd(observed['pid']);poll=select.poll();poll.register(fd,select.POLLIN)
        current=module('trace_bound_logger',ROOT/'owned-log.py').proc(observed['pid'])
        require(all(current[k]==observed[k] for k in ('pid','start_ticks','uid','executable_sha256','cmdline')),'Logger changed before pidfd binding')
        while time.monotonic()<end and not poll.poll(100):pass
        require(poll.poll(0),'Logger exceeded finite completion deadline')
        final,_=P.read(ROOT/'user/terminal.json',1048576,uid=1000,mode=0o600)
        # Python exclusive open respects its inherited umask; explicit output
        # mode is fixed by logger source before publication, not inferred.
        report=json.loads(final)
        require(report.get('status')=='owned-trace-collected' and report.get('controlled_stop') is True and report.get('startup_perturbation') is True and report.get('normal_session_fidelity') is False and report.get('safe_visual_gate')=='OPEN','Missing/contradictory trace completion')
        require(all(report['native_identity'][k]==observed[k] for k in ('session','pgrp','cwd','stdin','stdout')),'Native/logger boundary inheritance mismatch')
        require(report['native_identity']['ppid']==observed['pid'],'Native/logger parent mismatch')
        require(type(report.get('child_pid')) is int and report['native_identity']['pid']==report['child_pid'] and report['native_identity']['cmdline']==['mango','-d'] and report['native_identity']['executable_sha256']==P.sha(Path('/usr/bin/mango').read_bytes()),'Native target identity differs')
        log,_=P.read(ROOT/'user/capture/stderr.raw',4194304,uid=1000,mode=0o600)
        require(len(log)==report['raw_bytes'] and P.sha(log)==report['raw_sha256'],'Raw log substituted')
        ranges_raw,_=P.read(ROOT/'user/capture/log-report.json',4194304,uid=1000,mode=0o600)
        require(len(ranges_raw)==report['sender_ranges_body']['bytes'] and P.sha(ranges_raw)==report['sender_ranges_body']['sha256'],'Sender range body reference differs')
        ranges=json.loads(ranges_raw);require(len(ranges['rows'])==report['sender_ranges_body']['rows'],'Sender range count differs')
        T=module('trace_authentication',ROOT/'owned-log.py')
        require(log.count(b'\n')<=8192,'Authenticated line proof exceeds finite bound; full raw log retained')
        lines=T.authenticated_lines(log,ranges['rows'],dict(pid=report['child_pid'],uid=1000,gid=1000))
        line_raw=json.dumps(lines,sort_keys=True).encode()+b'\n';require(len(line_raw)<=4194304,'Line proof body exceeds unchanged export cap')
        result=dict(schema='arctic-one-mango-trace-v1',status='collected-pending-root-cleanup',logger_identity=observed,native_report=report,line_proofs=dict(path='line-proofs.json',bytes=len(line_raw),sha256=P.sha(line_raw),count=len(lines),authenticated_complete_lines=sum(v['status']=='owned-complete-line' for v in lines)),startup_perturbation=True,normal_session_fidelity=False,complete_chain=False,release_acceptance=False,safe_visual_gate='OPEN',active_scanout_pixels='UNAVAILABLE')
    except BaseException as e:primary=e;raise
    finally:
        if fd is not None:
            try:os.close(fd)
            except BaseException as e:
                if primary is None:raise
                primary.add_note('Root logger pidfd close also failed: '+str(e))
    # Root unit transport/whole journals and owned CD/generated-unit cleanup are
    # integration prerequisites. No terminal success is emitted by this core.
    return result,dict(**{'terminal.json':final,'log-report.json':ranges_raw,'stderr.raw':log,'line-proofs.json':line_raw}),state



def final_cleanup(P,state):
    # Static unit files remain in PID1/SDDM caches until the test VM ends. Only
    # disk nodes are removed; no daemon reload, session replacement or restart.
    generated=state['generated_unit_binding']['generated_files']
    for row in generated:
        _,proof=P.read(row['path'],mode=0o644)
        require(proof==row,'Generated unit file changed before rollback')
    result=rollback(state)
    for row in generated:
        p=Path(row['path']);v=p.lstat()
        require((v.st_dev,v.st_ino)==(row['device'],row['inode']),'Generated unit inode changed')
        p.unlink()
    cd=Path(state['CD'])
    raw=P.execute(['findmnt','-n','-o','TARGET,SOURCE,OPTIONS,FSTYPE','--mountpoint',str(cd)])
    fields=raw.decode().strip().split()
    require(len(fields)==4 and fields[0]==str(cd) and fields[3]=='iso9660' and {'ro','nosuid','nodev','noexec'}<=set(fields[2].split(',')),'Owned readonly CD mount changed')
    P.execute(['umount',str(cd)])
    require(P.identity(cd.lstat())==tuple(state['mount_underlying_identity']),'Underlying owned mount directory identity changed')
    cd.rmdir()
    return dict(owned_runtime_config_removed=True,owned_generated_files_removed=True,owned_readonly_CD_unmounted=True,underlying_owned_mount_directory_removed=True,root_owned_descriptors_closed=True,normal_SDDM_cache_restored=False,normal_target_replacement=False)

def success(P,H,retained):
    require(os.geteuid()==0,'Root receipt unit required')
    result,bodies,state=collect()
    # These already-read bounded bodies remain owned in memory after on-disk
    # cleanup. Failure publication must never replace them with rereads of
    # paths intentionally removed by that cleanup.
    retained.update(result=result,bodies=bodies,state=state)
    prior,_=P.read(ROOT/'journal-before.log',mode=0o600)
    require(len(prior)==state['security_before']['journal_total_bytes'] and P.sha(prior)==state['security_before']['journal_retained_sha256'],'Before whole journal changed')
    bodies['journal-before.log']=prior
    body=json.dumps(state,sort_keys=True).encode()+b'\n';require(len(body)<=262144,'Owned-state body exceeds existing row cap')
    bodies['owned-state.json']=body
    runtime=json.loads(P.read(ROOT/'runtime-pins.json')[0])
    candidate=runtime['candidate_boundary']
    for item in candidate['directories']:
        if item['path']=='/etc/sddm.conf.d':item['children']=sorted(item['children']+['99-arctic-mango-trace.conf'])
    result['config_after_capture']=P.discover(candidate)
    require(result['config_after_capture']==state['config_after'],'Target/config discovery changed during captures')
    result['effective_unit_after_capture']=P.unit_binding(Path(state['CD']),state['CD_sha256'],state['CD_bytes'],candidate)
    result['root_cleanup']=final_cleanup(P,state)
    retained['root_cleanup']=result['root_cleanup']
    # security() uses the frozen helper after CD unmount only if loaded first;
    # caller supplies the already verified helper module to the finite getter.
    after,journal=P.security(loaded_helper=SECURITY_HELPER)
    bodies['journal-after.log']=journal
    retained['security_after']=after
    require(after['qualified'],'Final whole-boot security check failed')
    result.update(status='diagnostic-collected-visual-open',security_before=state['security_before'],security_after=after,boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),candidate_source='fe4742c8b9414c45f0bcbb0a4191f116383c60d1',intended_iso_sha256='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718')
    frames=H.export(result,bodies)
    # Decode and validate the exact wire in memory before publishing any frame.
    decoded,all_bodies=H.decode(b''.join(frames).decode());H.validate_evidence(decoded,all_bodies)
    H.send(frames)

def failure(P,H,primary,retained=None):
    # Failures retain full bounded semantic bodies in the same serial channel.
    # They never satisfy the success decoder. Unknown/substituted resources
    # remain fatal rather than becoming guessed cleanup targets.
    retained={} if retained is None else retained
    errors=[repr(primary),*getattr(primary,'__notes__',[])];bodies=dict(retained.get('bodies',{}));state=retained.get('state')
    cleaned=retained.get('root_cleanup')
    try:
        if cleaned is None:
            stop=ROOT/'stop'
            if not stop.exists() and not stop.is_symlink():P.fresh_write(stop,b'ARCTIC_TRACE_END_V1\n',0o644)
            observed=observed_logger()
            if observed is not None:
                fd=pidfd(observed['pid'])
                try:
                    poll=select.poll();poll.register(fd,select.POLLIN)
                    require(poll.poll(6000),'Owned logger did not complete after bounded root stop')
                finally:os.close(fd)
    except BaseException as e:errors.append('Failure stop/completion: '+repr(e))
    for name,path,uid,limit in [('owned-state.json',ROOT/'state.json',0,262144),('journal-before.log',ROOT/'journal-before.log',0,4194304),('terminal.json',ROOT/'user/terminal.json',1000,262144),('log-report.json',ROOT/'user/capture/log-report.json',1000,4194304),('stderr.raw',ROOT/'user/capture/stderr.raw',1000,4194304)]:
        if name in bodies:continue
        try:
            raw,_=P.read(path,limit,uid=uid,mode=0o600);bodies[name]=raw
            if name=='owned-state.json':state=json.loads(raw)
        except BaseException as e:errors.append('Failure body '+name+': '+repr(e))
    cleanup=cleaned
    if state is not None and cleanup is None:
        try:cleanup=final_cleanup(P,state)
        except BaseException as e:errors.append('Failure owned cleanup: '+repr(e))
    security=retained.get('security_after')
    if security is None:
        try:security,journal=P.security(loaded_helper=SECURITY_HELPER);bodies['journal-after.log']=journal
        except BaseException as e:errors.append('Failure whole journal/security: '+repr(e))
    report=dict(schema='arctic-one-mango-trace-v1',status='failed-owned-trace',errors=errors,root_cleanup=cleanup,security_after=security,startup_perturbation=True,normal_session_fidelity=False,complete_chain=False,release_acceptance=False,safe_visual_gate='OPEN',active_scanout_pixels='UNAVAILABLE')
    try:H.send(H.export(report,bodies))
    except BaseException as e:primary.add_note('Failed evidence transport also failed: '+repr(e))

def main():
    require(os.geteuid()==0,'Root receipt unit required')
    P=module('trace_preparation',ROOT/'prepare.py');H=module('trace_transport',ROOT/'transport.py')
    retained={}
    try:success(P,H,retained)
    except BaseException as primary:
        failure(P,H,primary,retained)
        raise

if __name__=='__main__':
    def interrupted(number,frame):raise RuntimeError('Owned root controller interrupted: '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    # Hold the verified unchanged helper's code before removing its owned CD.
    source=Path('/run/arctic-mango-trace-cd/guest-safe-collector-v1.py')
    import hashlib
    require(hashlib.sha256(source.read_bytes()).hexdigest()=='e1da6bb2f07cb7014486e0f59c36973600e5dcd9a8063c684f461e099d3fc5e9','Frozen security helper changed')
    SECURITY_HELPER=module('trace_frozen_security',source)
    main()
