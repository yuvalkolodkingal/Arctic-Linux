"""Read-only exact-ISO startup attestation; no installation, network or hooks.

Run only from the reviewed read-only test CD in a disposable Safe-mode guest.
Importing does not run collection. Raw source files are recorded verbatim; RPM
signature descriptions are reported, not promoted to new signature validation.
"""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import socket
import stat
import struct
import sys
import tempfile
import time
import zlib

# The helper is imported from a read-only data CD; do not attempt cache writes.
sys.dont_write_bytecode=True

SOURCE='fe4742c8b9414c45f0bcbb0a4191f116383c60d1'
ISO_SHA='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
COMMON_SHA='e1da6bb2f07cb7014486e0f59c36973600e5dcd9a8063c684f461e099d3fc5e9'
MANGO_SHA='ce11ee5cfd24b0393c933e22f7365910d498772e186bb078b9d63a2b42313866'
MAX_FILE=65536
MAX_SOURCE_BYTES=2*1024*1024
MAX_SOURCES=512
FIXED=('/usr/share/wayland-sessions/mango.desktop','/usr/share/sddm/scripts/wayland-session',
       '/usr/lib/systemd/system/sddm.service','/usr/lib/systemd/system/livesys.service',
       '/usr/lib/systemd/system/livesys-late.service','/usr/libexec/livesys/livesys-main',
       '/usr/libexec/livesys/livesys-arctic','/etc/sysconfig/livesys','/etc/profile','/etc/bashrc',
       '/etc/sddm.conf','/etc/passwd','/etc/systemd/system/sddm.service','/run/systemd/system/sddm.service',
       '/home/liveuser/.bash_profile','/home/liveuser/.bash_login',
       '/home/liveuser/.profile','/home/liveuser/.bashrc')
TREES=('/etc/profile.d','/etc/sddm.conf.d','/usr/lib/sddm/sddm.conf.d',
       '/usr/lib/systemd/system/sddm.service.d','/etc/systemd/system/sddm.service.d','/run/systemd/system/sddm.service.d')
PROFILE_TARGETS=(
    ('/etc/profile.d/70-systemd-shell-extra.sh','../../usr/lib/systemd/profile.d/70-systemd-shell-extra.sh','/usr/lib/systemd/profile.d/70-systemd-shell-extra.sh'),
    ('/etc/profile.d/80-systemd-osc-context.sh','../../usr/lib/systemd/profile.d/80-systemd-osc-context.sh','/usr/lib/systemd/profile.d/80-systemd-osc-context.sh'))
FOLLOWUP_FILES=('/etc/sddm/wayland-session','/usr/lib/systemd/system/service.d/10-timeout-abort.conf',
    '/etc/sysconfig/sddm','/usr/libexec/livesys/functions','/usr/libexec/livesys/sessions.d/livesys-arctic',
    '/usr/libexec/livesys/livesys-late','/var/lib/livesys/livesys-session-extra',
    '/usr/lib/systemd/profile.d/70-systemd-shell-extra.sh','/usr/lib/systemd/profile.d/80-systemd-osc-context.sh',
    '/etc/locale.conf','/home/liveuser/.i18n','/home/liveuser/.config/bash_completion',
    '/usr/share/bash-completion/bash_completion','/etc/sysconfig/bash-prompt-xterm',
    '/etc/sysconfig/bash-prompt-screen','/etc/sysconfig/bash-prompt-default','/usr/libexec/grepconf.sh','/usr/bin/lesspipe.sh')
FOLLOWUP_TREES=('/home/liveuser/.bashrc.d','/etc/debuginfod')
FIXED+=FOLLOWUP_FILES
TREES+=FOLLOWUP_TREES
UNIT_ARGV=['systemctl','show','sddm.service','--no-pager','--property=FragmentPath,DropInPaths,ExecStart,ExecStartPre,User,EnvironmentFiles']
DYNAMIC_BLOCKERS=(
    ('bash-env-inherited-startup','The noninteractive Bash BASH_ENV pathname and its value at original startup are not established; no variable-expanded source is followed.'),
    ('bash-conditional-runtime-state','PS1, TERM, stdin TTY and completion/prompt conditions at original startup are not established by a later environment hash.'),
    ('colorls-term-include-eval','TERM-dependent colour files and their data-dependent INCLUDE/eval branches are not recursively resolved or executed.'),
    ('debuginfod-recursive-discovery','Only the bounded top-level /etc/debuginfod inventory is observed; recursive find-selected data remains unreviewed.'),
    ('flatpak-helper-output','The original profile invokes Flatpak installation discovery; its prior output and command resolution are not reconstructed.'),
    ('nix-environment-dependent-data','Nix profile/certificate paths depend on inherited variables, links and prior filesystem state; no dynamic traversal is performed.'),
    ('helper-runtime-resolution','Conditional helper invocation and prior command/output state are not proven by raw script bytes.'),
    ('new-script-semantic-review','The newly collected actual SessionCommand/livesys/profile targets require independent semantic review; further includes remain unbound.'))

def require(value,message):
    if not value:raise RuntimeError(message)
def sha(data):return hashlib.sha256(data).hexdigest()
def emit(name,value):print('ARCTIC-ATTEST-'+name+' '+json.dumps(value,sort_keys=True),flush=True)
def stable_stat(value):
    # A read can advance atime; it is not source identity/content mutation.
    return tuple(getattr(value,key) for key in ('st_dev','st_ino','st_uid','st_gid','st_mode','st_size','st_mtime_ns','st_ctime_ns'))

def source_file(path):
    """No link following, subprocess, or file mutation; absence is explicit."""
    p=Path(path);value=dict(path=str(p));present=False
    try:
        require(all(not v.is_symlink() for v in p.parents),'Startup source parent symlink')
        v=p.lstat();present=True;value.update(uid=v.st_uid,gid=v.st_gid,mode=stat.S_IMODE(v.st_mode),device=v.st_dev,inode=v.st_ino,bytes=v.st_size)
        if stat.S_ISLNK(v.st_mode):return dict(**value,status='symlink-unread',target=os.readlink(p))
        require(stat.S_ISREG(v.st_mode),'Nonregular startup source')
        require(v.st_size<=MAX_FILE,'Startup source exceeds bound')
        fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            before=os.fstat(fd);require(stable_stat(before)==stable_stat(v),'Startup source identity changed before read')
            data=os.read(fd,MAX_FILE+1);after=os.fstat(fd)
            require(len(data)==v.st_size and len(data)<=MAX_FILE and stable_stat(before)==stable_stat(after),'Startup source changed/short/overbound')
        finally:os.close(fd)
        return dict(**value,status='read-raw',sha256=sha(data),base64=base64.b64encode(data).decode())
    except FileNotFoundError as error:
        return dict(**value,status='unavailable',error='Startup source disappeared after lstat: '+str(error)) if present else dict(**value,status='absent')
    except TimeoutError:raise
    except Exception as error:return dict(**value,status='unavailable',error=type(error).__name__+': '+str(error))

def selected_chain(user, environment):
    require(type(user.pw_uid) is int and user.pw_uid>0 and user.pw_dir=='/home/liveuser','Unexpected live user/home')
    require(environment.get('SHELL')==user.pw_shell,'Actual session/login shell mismatch')
    shell=Path(user.pw_shell).name
    require(shell in ('fish','bash'),'Unsupported actual login-shell startup chain: '+shell)
    require(environment.get('XDG_CONFIG_HOME',user.pw_dir+'/.config')==user.pw_dir+'/.config',
            'Unsupported actual configuration search path')
    extra=();directories=()
    if shell=='fish':
        extra=('/etc/fish/config.fish','/usr/share/fish/config.fish','/home/liveuser/.config/fish/config.fish',
               '/home/liveuser/.config/fish/fish_variables','/home/liveuser/.config/fish/config.local.fish',
               '/nix/var/nix/profiles/default/etc/profile.d/nix-daemon.fish')
        directories=('/etc/fish/conf.d','/usr/share/fish/vendor_conf.d','/home/liveuser/.config/fish/conf.d',
                     '/etc/fish/functions','/usr/share/fish/functions','/usr/share/fish/vendor_functions.d',
                     '/home/liveuser/.config/fish/functions')
    return dict(shell=user.pw_shell,uid=user.pw_uid,home=user.pw_dir,actual_SHELL=environment['SHELL'],
                invocation='Observed login/session shell; actual SessionCommand semantics remain independently unreviewed',extra_files=list(extra),directories=list(directories),
                chain_scope='Raw actual selected shell inputs/default search directories; semantic include/universal-path review still required',
                independently_reviewed_complete_chain=False,
                include_scope='Known declared Arctic Fish inputs included; dynamic source/eval/autoload/universal-variable paths remain unreviewed',
                unresolved_links_are_startup_binding_blockers=True)

def source_set(root=Path('/'), chain=None):
    root=Path(root);paths=set(FIXED);trees=[]
    if chain:paths.update(chain['extra_files'])
    for name in TREES+tuple(chain['directories'] if chain else ()):
        p=root/name.lstrip('/')
        require(all(not v.is_symlink() for v in p.parents),'Startup directory parent symlink differs')
        try:info=p.lstat()
        except FileNotFoundError:trees.append(dict(path=name,status='absent'));continue
        require(stat.S_ISDIR(info.st_mode) and not p.is_symlink(),'Startup source directory type/link differs')
        children=sorted(p.iterdir());require(len(children)<=512,'Startup source directory exceeds count')
        require(stable_stat(p.lstat())==stable_stat(info),'Startup source directory changed during listing')
        trees.append(dict(path=name,status='listed',children=[v.name for v in children],uid=info.st_uid,gid=info.st_gid,
                          mode=stat.S_IMODE(info.st_mode),device=info.st_dev,inode=info.st_ino,mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns))
        for child in children:
            require(child.name not in ('.','..') and '/' not in child.name,'Unsafe source basename')
            paths.add(name+'/'+child.name)
    require(len(paths)<=MAX_SOURCES,'Startup source aggregate count exceeds bound')
    values=[];total=0
    for path in sorted(paths):
        item=source_file(root/path.lstrip('/'));item['path']=path
        if item['status']=='read-raw':total+=item['bytes'];require(total<=MAX_SOURCE_BYTES,'Startup source aggregate byte bound exceeded')
        values.append(item)
    return dict(files=values,trees=trees,raw_source_bytes=total)

def chain_obstacles(sources):
    return [dict(path=v['path'],status=v['status'],error=v.get('error'),target=v.get('target'))
            for v in sources['files'] if v['status'] in ('symlink-unread','unavailable')]

def profile_target_proofs(root=Path('/'),expected_uid=0,expected_gid=0):
    """Observe explicit link nodes and independent regular targets, never follow links."""
    require(type(expected_uid) is int and expected_uid>=0 and type(expected_gid) is int and expected_gid>=0,'Invalid profile owner binding')
    root=Path(root);proofs=[]
    for node,literal,target in PROFILE_TARGETS:
        p=root/node.lstrip('/');t=root/target.lstrip('/')
        require(all(not v.is_symlink() for v in p.parents),'Profile node parent symlink')
        before=p.lstat();require(stat.S_ISLNK(before.st_mode) and before.st_uid==expected_uid and before.st_gid==expected_gid
                                and os.readlink(p)==literal,'Observed profile node type/owner/literal differs')
        target_before=t.lstat();item=source_file(t)
        require(item['status']=='read-raw' and item['uid']==expected_uid and item['gid']==expected_gid
                and not item['mode']&0o22,'Independent profile target not regular/readable/owned')
        target_after=t.lstat();after=p.lstat()
        require(stable_stat(before)==stable_stat(after) and os.readlink(p)==literal
                and stable_stat(target_before)==stable_stat(target_after),'Profile node/target identity changed')
        require(source_file(t)==item,'Independent profile target changed after link observation')
        alias=next((value['fixed_target'] for value in proofs if value['target_before'][:2]==list(stable_stat(target_before))[:2]),None)
        proofs.append(dict(node=node,literal_target=literal,fixed_target=target,node_before=list(stable_stat(before)),
                           node_after=list(stable_stat(after)),target_before=list(stable_stat(target_before)),
                           target_after=list(stable_stat(target_after)),target_sha256=item['sha256'],target_alias_of=alias))
    return proofs

def effective_unit(data):
    require(type(data) is bytes and len(data)<=1024*1024,'Effective unit output bound/type differs')
    lines=data.decode('utf-8').splitlines()
    for expected in ('FragmentPath=/usr/lib/systemd/system/sddm.service',
                     'DropInPaths=/usr/lib/systemd/system/service.d/10-timeout-abort.conf',
                     'EnvironmentFiles=/etc/sysconfig/sddm (ignore_errors=yes)'):
        require(lines.count(expected)==1 and sum(v.startswith(expected.split('=',1)[0]+'=') for v in lines)==1,
                'Effective unit outside narrowly observed fixed paths')
    return data

def binary(path, expected_uid=0):
    require(type(expected_uid) is int and expected_uid>=0,'Invalid executable owner binding')
    p=Path(path);v=p.lstat();require(stat.S_ISREG(v.st_mode) and not p.is_symlink() and v.st_uid==expected_uid and not v.st_mode&0o6022
                                  and 0<v.st_size<=64*1024*1024,'Executable type/owner/mode/size differs')
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        data=os.pread(fd,v.st_size+1,0);require(len(data)==v.st_size and stable_stat(os.fstat(fd))==stable_stat(v),'Executable bytes/identity changed')
    finally:os.close(fd)
    require(data.startswith(b'\x7fELF'),'Expected shipped ELF executable')
    return dict(path=str(p),uid=v.st_uid,gid=v.st_gid,mode=stat.S_IMODE(v.st_mode),bytes=v.st_size,sha256=sha(data))

def collect(C,root):
    begin=time.monotonic_ns();user,proofs,env=C.desktop()
    require(proofs['mango']['cmdline']==['mango'] and proofs['mango']['executable_sha256']==MANGO_SHA,'Requires unchanged normal candidate Mango')
    before=C.security(root,'attest-before');require(before['selinux']=='Enforcing' and not before['avc_records']
            and before['journal_total_bytes']==before['journal_retained_bytes'],'Security before incomplete/failed')
    actual_mango_environment=C.environment(proofs['mango']['pid']);chain=selected_chain(user,actual_mango_environment)
    require(chain['shell']=='/bin/bash','Missing-chain followup requires the actual previously observed Bash route')
    unit_before=effective_unit(C.execute(UNIT_ARGV,timeout=20));(root/'sddm-effective-unit.txt').write_bytes(unit_before)
    links_before=profile_target_proofs();sources=source_set(chain=chain)
    require(all(next(v for v in sources['files'] if v['path']==p['fixed_target'])['sha256']==p['target_sha256'] for p in links_before),
            'Inventory profile target differs from bracketed observation')
    executables=[binary(p) for p in dict.fromkeys(('/usr/bin/mango','/usr/bin/sddm','/usr/lib/systemd/systemd',
                 '/usr/lib/systemd/system-generators/systemd-debug-generator','/usr/bin/bash','/usr/bin/python3.14',str(Path(user.pw_shell).resolve())))]
    commands={'sddm-effective-unit':dict(argv=UNIT_ARGV,bytes=len(unit_before),sha256=sha(unit_before),path='sddm-effective-unit.txt')}
    for name,argv in [('uname',['uname','-a']),('systemd-version',['/usr/lib/systemd/systemd','--version']),
                     ('rpm-nevra',['rpm','-q','--qf','%{NAME}\t%{EPOCHNUM}:%{VERSION}-%{RELEASE}\t%{ARCH}\n','mangowm','sddm','systemd','bash','fish','python3','livesys-scripts','scenefx','wlroots','arctic-live']),
                     ('rpm-signature-descriptions',['rpm','-q','--qf','%{NAME}\t%{RSAHEADER:pgpsig}\t%{DSAHEADER:pgpsig}\t%{SIGPGP:pgpsig}\t%{SIGGPG:pgpsig}\n','mangowm','sddm','systemd','bash','fish','python3','livesys-scripts','scenefx','wlroots','arctic-live']),
                     ('rpm-file-digests',['rpm','-q','--qf','%{NAME}\t%{FILEDIGESTALGO}\n[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILEMODES:octal}\t%{FILEUSERNAME}\t%{FILEGROUPNAME}\n]','mangowm','sddm','systemd','bash','fish','livesys-scripts','arctic-live'])]:
        data=C.execute(argv,timeout=20);require(len(data)<=1024*1024,'Command output exceeds attestation bound')
        p=root/(name+'.txt');p.write_bytes(data);commands[name]=dict(argv=argv,bytes=len(data),sha256=sha(data),path=p.name)
        require(time.monotonic_ns()-begin<=90*10**9,'Attestation exceeded90s')
    links_after=profile_target_proofs();unit_after=effective_unit(C.execute(UNIT_ARGV,timeout=20))
    require(unit_before==unit_after and links_before==links_after,'Effective unit/profile observations changed during collection')
    (root/'sddm-effective-unit-after.txt').write_bytes(unit_after)
    commands['sddm-effective-unit-after']=dict(argv=UNIT_ARGV,bytes=len(unit_after),sha256=sha(unit_after),path='sddm-effective-unit-after.txt')
    after=C.security(root,'attest-after');require(after['selinux']=='Enforcing' and not after['avc_records']
            and after['journal_total_bytes']==after['journal_retained_bytes'],'Security after incomplete/failed')
    require(source_set(chain=chain)==sources and C.environment(proofs['mango']['pid'])==actual_mango_environment
            and all(C.process(v['pid'])==v for v in proofs.values()),'Sources/environment/desktop changed during attestation')
    report=dict(schema='arctic-startup-attestation-v1',status='exact-startup-attestation-collected',candidate_source=SOURCE,intended_iso_sha256=ISO_SHA,
                mango_executable_sha256=MANGO_SHA,source_files=sources,selected_startup_chain=chain,executables=executables,commands=commands,processes=proofs,
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),cmdline=Path('/proc/cmdline').read_text().strip(),
                begin_monotonic_ns=begin,end_monotonic_ns=time.monotonic_ns(),security_before=before,security_after=after,
                signature_scope='Installed RSAHEADER/DSAHEADER/legacy signature descriptions and file digests; no fresh archive cryptographic verification; unsigned preview headers are not a failure by themselves',
                source_scope='Exact raw bytes/UID/GID/mode, links/absence/errors explicit; immutable ISO/source trust and Fedora signature data require distinct independent review',
                startup_binding_blockers=chain_obstacles(sources)+[dict(path='semantic-startup-chain',status='unreviewed')],
                missing_chain_followup=dict(schema='arctic-missing-chain-raw-v1',actual_login_shell='/bin/bash',
                    raw_file_inventory=sorted(FOLLOWUP_FILES),directory_inventory=sorted(FOLLOWUP_TREES),
                    profile_target_proofs=links_before,effective_unit_before='sddm-effective-unit.txt',effective_unit_after='sddm-effective-unit-after.txt',
                    effective_unit_sha256=sha(unit_before),non_atomic_observations=True,complete_startup_chain=False,
                    unsupported_dynamic_chain=[dict(id=name,status='unreviewed',reason=reason) for name,reason in DYNAMIC_BLOCKERS]),
                mango_environment_sha256=sha(b'\0'.join(k.encode()+b'='+v.encode() for k,v in sorted(actual_mango_environment.items()))),
                quickshell_environment_sha256=sha(b'\0'.join(k.encode()+b'='+v.encode() for k,v in sorted(env.items()))),
                python_abi=dict(so_passcred=socket.SO_PASSCRED,scm_credentials=socket.SCM_CREDENTIALS,
                                ucred_size=struct.calcsize('3i'),cmsg_space=socket.CMSG_SPACE(struct.calcsize('3i')),
                                pidfd_open=hasattr(os,'pidfd_open'),pidfd_send_signal=hasattr(signal,'pidfd_send_signal'),
                                source='Actual guest Python constants/capability presence; stream semantics require owned runtime control'),
                release_acceptance=False,safe_visual_gate='open',startup_hook_executed=False,renderer='unobserved',active_scanout_pixels='unavailable')
    data=json.dumps(report,indent=2,sort_keys=True).encode();require(len(data)<=4*1024*1024,'Attestation report exceeds bound');(root/'report.json').write_bytes(data)
    return report

def transport(root,report):
    files=[];chunks=[];total=0
    for p in sorted(root.iterdir()):
        require(p.is_file() and not p.is_symlink() and p.suffix in ('.json','.txt','.log'),'Unexpected attestation output')
        data=p.read_bytes();require(len(data)<=4*1024*1024,'Attestation file exceeds bound');total+=len(data);require(total<=16*1024*1024,'Attestation transport exceeds total bound')
        packed=zlib.compress(data);parts=[packed[i:i+1200] for i in range(0,len(packed),1200)]
        require(0<len(parts)<=3600,'Attestation chunk count exceeds bound')
        files.append(dict(path=p.name,bytes=len(data),sha256=sha(data),compressed_bytes=len(packed),chunks=len(parts)))
        chunks.extend(dict(path=p.name,index=i,data=base64.b64encode(part).decode()) for i,part in enumerate(parts))
    emit('REPORT',report);emit('MANIFEST',dict(schema='arctic-startup-attestation-files-v1',encoding='zlib+base64',files=files,bytes=total))
    for value in chunks:emit('CHUNK',value)

def main():
    root=None;error=None;report=None;armed=False
    emit('BEGIN',dict(collector_sha256=sha(Path(__file__).read_bytes()),candidate_source=SOURCE,release_acceptance=False))
    try:
        require(os.geteuid()==0 and Path(__file__).resolve()==Path('/run/arctic-safe/attest-startup-v1.py'),'Requires exact root test-CD path')
        common=Path('/run/arctic-safe/guest-safe-collector-v1.py');require(not common.is_symlink() and sha(common.read_bytes())==COMMON_SHA,'Original security collector pin differs')
        spec=importlib.util.spec_from_file_location('startup_original_security',common);C=importlib.util.module_from_spec(spec);spec.loader.exec_module(C)
        require(C.execute(['systemd-detect-virt']).decode().strip() in ('qemu','kvm'),'Requires disposable QEMU/KVM')
        cmd=Path('/proc/cmdline').read_text().split();require('rd.live.image' in cmd and 'nomodeset' in cmd,'Requires exact Safe live mode')
        require(C.execute(['getenforce']).decode().strip()=='Enforcing','Requires Enforcing before any output')
        require('ro' in C.execute(['findmnt','-n','-o','OPTIONS','/run/arctic-safe']).decode().strip().split(','),'Requires read-only test CD')
        def alarm(signum,frame):raise TimeoutError('Startup attestation110s alarm')
        signal.signal(signal.SIGALRM,alarm);signal.alarm(110);armed=True
        root=Path(tempfile.mkdtemp(prefix='arctic-startup-attest-'));report=collect(C,root);transport(root,report)
    except BaseException as exc:error=type(exc).__name__+': '+str(exc)
    finally:
        if armed:signal.alarm(0)
    emit('END',dict(status='failed' if error else 'attestation-collected-unreviewed',error=error,release_acceptance=False))
    if error:raise SystemExit(1)

if __name__=='__main__':main()
