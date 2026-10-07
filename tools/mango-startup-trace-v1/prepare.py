"""One fresh owned test boundary. No profile traversal, fallback or daemon restart."""
import sys
sys.dont_write_bytecode=True
import hashlib,json,os,pwd,stat
from pathlib import Path
ROOT=Path('/run/arctic-mango-trace')
OVERLAY=Path('/etc/sddm.conf.d/99-arctic-mango-trace.conf')
WRAPPER=ROOT/'session-wrapper'
ORIGINAL_SHA='a7a41d9996fd912af2b8b2dc0b5c33ca6d4530e8c45122f3e35f321bb620abfd'
PAYLOAD=('native-handoff','owned-logger.py','owned-log.py','sealed_environment.py','controller.py','prepare.py','transport.py','runtime-pins.json')

def require(v,m):
    if not v:raise RuntimeError(m)
def sha(v):return hashlib.sha256(v).hexdigest()
def identity(v):return (v.st_dev,v.st_ino,v.st_uid,v.st_gid,stat.S_IMODE(v.st_mode))
def stable(v):return identity(v)+(v.st_size,v.st_mtime_ns,v.st_ctime_ns)
def parents(p,user_output=False):
    require(p.is_absolute(),'Expected absolute path')
    for q in reversed(p.parents):
        v=q.lstat()
        own_user=user_output and q in (ROOT/'user',ROOT/'user/capture')
        require(stat.S_ISDIR(v.st_mode) and not q.is_symlink() and v.st_uid==(1000 if own_user else 0) and v.st_gid==(1000 if own_user else 0) and not v.st_mode&0o022 and (not own_user or stat.S_IMODE(v.st_mode)==0o700),'Unsafe parent type/owner/mode')
def read(p,limit=65536,uid=0,mode=None):
    p=Path(p);parents(p,user_output=uid==1000);a=p.lstat()
    require(stat.S_ISREG(a.st_mode) and a.st_uid==uid and a.st_gid==uid and not a.st_mode&0o022 and 0<a.st_size<=limit and (mode is None or stat.S_IMODE(a.st_mode)==mode),'Unsafe source file type/owner/mode/bound')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);primary=None
    try:
        b=os.fstat(fd);raw=os.pread(fd,a.st_size,0);c=os.fstat(fd);d=p.lstat()
        require(stable(a)==stable(b)==stable(c)==stable(d) and len(raw)==a.st_size,'Source identity/content changed')
    except BaseException as e:primary=e;raise
    finally:
        try:os.close(fd)
        except BaseException as e:
            if primary is None:raise
            primary.add_note('Source close also failed: '+str(e))
    return raw,dict(path=str(p),device=a.st_dev,inode=a.st_ino,uid=a.st_uid,gid=a.st_gid,mode=stat.S_IMODE(a.st_mode),bytes=a.st_size,mtime_ns=a.st_mtime_ns,ctime_ns=a.st_ctime_ns,sha256=sha(raw))
def wrapper(raw):
    require(sha(raw)==ORIGINAL_SHA and raw.count(b'\nexec $@\n')==1,'Unexpected selected SessionCommand bytes')
    # Retain actual unquoted expansion and shell branch. This changes $0/path
    # and the exec target, not a proof of identical earlier Bash semantics.
    return raw.replace(b'\nexec $@\n',b'\nexec /run/arctic-mango-trace/native-handoff $@\n')
def discover(expected):
    out=[]
    for item in expected['directories']:
        p=Path(item['path']);parents(p);a=p.lstat()
        require(stat.S_ISDIR(a.st_mode) and a.st_uid==0 and a.st_gid==0 and stat.S_IMODE(a.st_mode)==0o755,'Config directory identity unsafe')
        names=sorted(q.name for q in p.iterdir())
        require(names==item['children'] and len(names)<=64,'Unknown config entry or collision')
        out.append(dict(path=str(p),identity=list(identity(a)),children=names))
    for item in expected['files']:
        raw,proof=read(item['path'],mode=item['mode'])
        require(proof['sha256']==item['sha256'],'Actual boundary/config bytes differ')
        out.append(proof)
    # The captured existing files have no active SessionCommand key; therefore
    # ordering among them cannot choose an alternative wrapper. Highest /etc
    # file is pinned unchanged. No generic INI/default normalization is used.
    return out

def fresh_write(p,raw,mode,track=None):
    fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,mode);primary=None
    try:
        os.fchmod(fd,mode)
        if track is not None:track(dict(path=str(p),identity=identity(os.fstat(fd)),sha256=sha(raw)))
        done=0
        while done<len(raw):
            n=os.write(fd,raw[done:]);require(n>0,'Short owned write');done+=n
        v=os.fstat(fd)
        require(v.st_uid==0 and v.st_gid==0 and stat.S_IMODE(v.st_mode)==mode,'Owned write mode/owner differs')
    except BaseException as e:primary=e;raise
    finally:
        try:os.close(fd)
        except BaseException as e:
            if primary is None:raise
            primary.add_note('Owned output close also failed: '+str(e))
    return dict(path=str(p),identity=identity(p.lstat()),sha256=sha(raw))

def install(cd,cd_sha,cd_bytes,mount_identity):
    require(os.geteuid()==0,'Root preparation required')
    require(not ROOT.exists() and not ROOT.is_symlink() and not OVERLAY.exists() and not OVERLAY.is_symlink(),'Owned runtime/config collision')
    user=pwd.getpwnam('liveuser');require((user.pw_uid,user.pw_gid,user.pw_dir,user.pw_shell)==(1000,1000,'/home/liveuser','/bin/bash'),'Selected account route differs')
    pins=json.loads(read(cd/'runtime-pins.json')[0]);candidate=pins['candidate_boundary']
    before=discover(candidate)
    units=unit_binding(cd,cd_sha,cd_bytes,candidate)
    for item in candidate['providers']:
        _,v=read(item['path'],64*1024*1024,mode=item['mode']);require(v['sha256']==item['sha256'],'Candidate provider changed')
    raw,_=read('/etc/sddm/wayland-session',mode=0o755);changed=wrapper(raw)
    owned=[]
    try:
        parents(ROOT);ROOT.mkdir(mode=0o755);owned.append(dict(path=str(ROOT),identity=identity(ROOT.lstat())))
        os.chmod(ROOT,0o755);owned[-1]['identity']=identity(ROOT.lstat())
        # Only exact fresh objects in this namespace may be rolled back. Failed
        # partial install retains its bounded state for the independent controller.
        for name in PAYLOAD:
            data,proof=read(cd/name,64*1024*1024)
            if name!='runtime-pins.json':require(name in pins['runtime'] and proof['sha256']==pins['runtime'][name]['sha256'],'Runtime payload pin differs')
            fresh_write(ROOT/name,data,0o755 if name=='native-handoff' else 0o644,track=owned.append)
        fresh_write(WRAPPER,changed,0o755,track=owned.append)
        (ROOT/'user').mkdir(mode=0o700);owned.append(dict(path=str(ROOT/'user'),identity=identity((ROOT/'user').lstat())))
        try:os.chmod(ROOT/'user',0o700);os.chown(ROOT/'user',1000,1000)
        finally:
            # A successful chown followed by a reporting error is still our
            # same freshly created inode; capture that owned transition once.
            changed_owner=(ROOT/'user').lstat()
            require(identity(changed_owner)[:2]==tuple(owned[-1]['identity'])[:2] and changed_owner.st_uid in (0,1000) and changed_owner.st_gid in (0,1000),'Fresh user directory substituted during owner transition')
            owned[-1]['identity']=identity(changed_owner)
        value=b'[Wayland]\nSessionCommand=/run/arctic-mango-trace/session-wrapper\n'
        fresh_write(OVERLAY,value,0o644,track=owned.append)
        # Existing inputs must remain byte-identical. Directory gained only the one
        # declared new file. It is not a simultaneous atomic filesystem snapshot.
        after_expected=json.loads(json.dumps(candidate))
        for item in after_expected['directories']:
            if item['path']==str(OVERLAY.parent):item['children']=sorted(item['children']+[OVERLAY.name])
        after=discover(after_expected)
        security_before,journal_before=security()
        fresh_write(ROOT/'journal-before.log',journal_before,0o600,track=owned.append)
        if not security_before['qualified']:
            preserve_failure({'status':'failed-before-native-security','startup_perturbation':True,'release_acceptance':False,'safe_visual_gate':'OPEN','security_before':security_before},{'journal-before.log':journal_before},cd)
            raise RuntimeError('Before-activation security check failed; full raw journal exported as failed evidence')
        state=dict(generated_unit_binding=units,security_before=security_before,CD_sha256=cd_sha,CD_bytes=cd_bytes,mount_underlying_identity=mount_identity,schema='arctic-mango-trace-owned-boundary-v1',owned=owned,config_before=before,config_after=after,CD=str(cd),startup_perturbation=True,complete_chain=False,normal_fidelity=False,safe_visual_gate='OPEN')
        saved=json.dumps(state,sort_keys=True).encode()+b'\n'
        fresh_write(ROOT/'state.json',saved,0o600,track=owned.append)
        return json.loads(saved)
    except BaseException as primary:
        # Target has not launched: remove only recorded freshly created nodes.
        # Unknown/substituted paths are retained with fatal cleanup notes.
        for record in reversed(owned):
            node=Path(record['path'])
            try:
                v=node.lstat();require(identity(v)==tuple(record['identity']),'Partial installation ownership changed')
                node.rmdir() if stat.S_ISDIR(v.st_mode) else node.unlink()
            except BaseException as error:primary.add_note('Partial owned cleanup also failed: '+str(error))
        raise


# These helpers are used by the isolated prep/controller before any publication.
def execute(argv,seconds=20,limit=4194304):
    import subprocess
    r=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=seconds,env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')})
    require(len(r.stdout)<=limit and len(r.stderr)<=65536 and r.returncode==0,'Bounded read-only command failed: '+argv[0])
    return r.stdout

def security(loaded_helper=None):
    import importlib.util
    if loaded_helper is None:
        helper=Path('/run/arctic-mango-trace-cd/guest-safe-collector-v1.py')
        raw,proof=read(helper)
        require(proof['sha256']=='e1da6bb2f07cb7014486e0f59c36973600e5dcd9a8063c684f461e099d3fc5e9','Frozen security helper differs')
        spec=importlib.util.spec_from_file_location('unchanged_trace_security',helper);S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
    else:S=loaded_helper
    mode=execute(['getenforce']).decode().strip();audit=execute(['auditctl','-s']).decode();fields=dict(line.split(None,1) for line in audit.splitlines() if len(line.split(None,1))==2)
    whole=execute(['journalctl','-b','--no-pager','-o','json'],30)
    records=[json.loads(v) for v in whole.splitlines() if v];require(records and all(type(v) is dict and 'MESSAGE' in v for v in records),'Malformed whole current-boot journal')
    avcs=S.kernel_avcs(records)
    return dict(qualified=(mode=='Enforcing' and fields.get('enabled') in ('1','2') and fields.get('lost')=='0' and not avcs),selinux=mode,audit_status=audit,journal_total_bytes=len(whole),journal_retained_bytes=len(whole),journal_retained_sha256=sha(whole),current_boot_journal_records=len(records),avc_records=avcs,full_unfiltered=True),whole

def unit_binding(cd,cdsha,cdbytes,candidate):
    import importlib.util
    U=importlib.util.spec_from_file_location('trace_credential_contract',cd/'credential-units.py');module=importlib.util.module_from_spec(U);U.loader.exec_module(module)
    values=module.values(cdsha,cdbytes)
    names={module.DROP:Path('/run/systemd/generator.early/sddm.service.d/90-arctic-mango-trace.conf'),module.EXTRA:Path('/run/systemd/generator.early/arctic-mango-trace-collector.service')}
    result=[]
    for name,p in names.items():
        raw,v=read(p,mode=0o644);require(raw==values[name].encode(),'Generated credential unit content/route differs');result.append(v)
    for item in candidate['unit_files']:
        p=Path(item['path'])
        if item['status']=='absent':
            parents(p)
            try:p.lstat()
            except FileNotFoundError:continue
            raise RuntimeError('Expected optional SDDM unit environment path exists/link')
        _,v=read(p,mode=item['mode']);require(v['sha256']==item['sha256'],'Actual SDDM unit/optional environment bytes changed')
    props=execute(['systemctl','show','sddm.service','-p','FragmentPath','-p','DropInPaths','-p','ExecStart','-p','ExecStartPre','-p','EnvironmentFiles'])
    fields=dict(v.split('=',1) for v in props.decode().splitlines())
    require(fields['FragmentPath']=='/usr/lib/systemd/system/sddm.service' and set(fields['DropInPaths'].split())=={'/usr/lib/systemd/system/service.d/10-timeout-abort.conf',str(names[module.DROP])} and 'path=/usr/bin/sddm' in fields['ExecStart'],'Unexpected effective SDDM unit discovery/command')
    return dict(generated_files=result,effective_properties_raw=props.decode(),scope='Observed supported credential/SDDM execution config; not complete startup semantics')

def preserve_failure(report,bodies,cd):
    import importlib.util
    spec=importlib.util.spec_from_file_location('trace_failed_transport',cd/'transport.py');H=importlib.util.module_from_spec(spec);spec.loader.exec_module(H)
    H.send(H.export(report,bodies))

if __name__=='__main__':
    import signal
    def interrupted(number,frame):raise RuntimeError('Owned preparation interrupted: '+str(number))
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    require(len(sys.argv)==4,'Exact CD/mount identity required')
    import re
    require(re.fullmatch('[0-9a-f]{64}',sys.argv[1]) is not None and sys.argv[2].isdigit(),'Typed CD identity required')
    fields=sys.argv[3].split(':');require(len(fields)==5 and all(v.isdigit() for v in fields),'Typed underlying mount identity required')
    mounted=[int(fields[0]),int(fields[1]),int(fields[2]),int(fields[3]),int(fields[4],8)]
    require(mounted[0]>0 and mounted[1]>0 and mounted[2:]==[0,0,0o700],'Underlying owned mount identity differs')
    require('nomodeset' in Path('/proc/cmdline').read_text().split() and 'rd.live.image' in Path('/proc/cmdline').read_text().split(),'Fixed exact Safe live boot required')
    install(Path('/run/arctic-mango-trace-cd'),sys.argv[1],int(sys.argv[2]),mounted)
