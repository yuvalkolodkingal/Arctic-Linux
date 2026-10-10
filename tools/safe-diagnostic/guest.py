#!/usr/bin/env python3
"""Read-only Safe rendering observation in one authenticated disposable guest."""
import hashlib
import configparser
import copy
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import select
import shlex
import signal
import stat
import subprocess
import sys
import time


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BASE = Path('/run/t')
c = load('safe_common', BASE / 'common.py')


def bounded(argv, timeout=20, limit=1024**2):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    c.require(result.returncode == 0 and len(result.stdout) + len(result.stderr) <= limit,
              'Guest observation command failed or exceeded bound')
    return result.stdout.decode().strip()


ALLOWED_RENDERER_ENV = {'WLR_RENDERER', 'WLR_RENDERER_ALLOW_SOFTWARE', 'WLR_RENDERER_FORCE_SOFTWARE',
    'WLR_NO_HARDWARE_CURSORS', 'WLR_DRM_NO_ATOMIC', 'WLR_SCENE_DEBUG_DAMAGE',
    'LIBGL_ALWAYS_SOFTWARE', 'MESA_LOADER_DRIVER_OVERRIDE', 'GALLIUM_DRIVER',
    'WLR_BACKENDS', 'WLR_DRM_DEVICES', 'WLR_HEADLESS_OUTPUTS'}


def protected(path, executable=False):
    path=Path(path)
    info=path.lstat()
    c.require(stat.S_ISREG(info.st_mode) and info.st_uid==os.geteuid()
              and not info.st_mode & 0o022 and (not executable or info.st_mode & 0o005==0o005),
              'Trusted session file protection differs')
    return dict(bytes=info.st_size,sha256=c.sha(path),mode=stat.S_IMODE(info.st_mode),uid=info.st_uid)


def sddm_configuration(root=Path('/')):
    """Read SDDM's documented precedence; reject ambiguous or foreign files."""
    root=Path(root); paths=[]
    for relative in ('usr/lib/sddm/sddm.conf.d','etc/sddm.conf.d'):
        directory=root/relative
        if not directory.exists():
            c.require(not directory.is_symlink(),'SDDM configuration directory is a symlink')
            continue
        info=directory.lstat()
        c.require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid()
                  and not info.st_mode & 0o022,'SDDM configuration directory protection differs')
        paths.extend(sorted(directory.glob('*.conf')))
    final=root/'etc/sddm.conf'
    if final.exists() or final.is_symlink(): paths.append(final)
    effective={}; inventory=[]
    for path in paths:
        record=protected(path)
        raw=c.read_regular(path,limit=65536).decode('utf-8')
        parser=configparser.ConfigParser(interpolation=None,strict=True)
        parser.optionxform=str; parser.read_string(raw)
        c.require(not parser.defaults(),'SDDM defaults ambiguity differs')
        for section in parser.sections():
            effective.setdefault(section,{}).update(dict(parser.items(section,raw=True)))
        inventory.append(dict(path=str(path.relative_to(root)),**record))
    return effective,inventory


def session_contract(root=Path('/'), query=bounded):
    root=Path(root); effective,inventory=sddm_configuration(root)
    c.require(effective.get('General',{}).get('DisplayServer')=='wayland'
              and effective.get('Autologin',{}).get('User')=='liveuser'
              and effective.get('Autologin',{}).get('Session')=='mango.desktop'
              and effective.get('Autologin',{}).get('Relogin','false').lower()=='false',
              'Original live SDDM session contract differs')
    # /etc/sddm.conf is read last and may override every drop-in. Fail closed.
    final=root/'etc/sddm.conf'
    if final.exists():
        parser=configparser.ConfigParser(interpolation=None,strict=True);parser.optionxform=str
        parser.read_string(c.read_regular(final,65536).decode())
        c.require(not parser.has_option('Wayland','SessionCommand'),
                  'Higher-priority SessionCommand conflict')
    listing=query(['rpm','-ql','sddm']).splitlines()
    defaults=configparser.ConfigParser(interpolation=None,strict=True);defaults.optionxform=str
    defaults.read_string(query(['sddm','--example-config']))
    compiled=defaults.get('Wayland','SessionCommand')
    c.require(compiled in listing and compiled in
        ('/usr/share/sddm/scripts/wayland-session','/usr/libexec/sddm/wayland-session','/etc/sddm/wayland-session'),
        'Actual compiled packaged Wayland session script differs')
    command=effective.get('Wayland',{}).get('SessionCommand',compiled)
    c.require(command==compiled,'Original SessionCommand differs from actual compiled script')
    script=root/command.lstrip('/');script_record=protected(script,True)
    owner=query(['rpm','-qf',str(script)])
    c.require(re.fullmatch(r'sddm-0\.21\.0-13\.fc44\.x86_64',owner),
              'Exact image SDDM script package differs')
    session=root/'usr/share/wayland-sessions/mango.desktop'
    session_record=protected(session)
    desktop=configparser.ConfigParser(interpolation=None,strict=True);desktop.optionxform=str
    desktop.read_string(c.read_regular(session,65536).decode())
    argv=shlex.split(desktop.get('Desktop Entry','Exec'))
    c.require(argv and argv[0] in ('mango','/usr/bin/mango')
              and all(re.fullmatch(r'[A-Za-z0-9_./=-]+',v) for v in argv),
              'Trusted Mango desktop argv differs')
    directory=root/'etc/sddm.conf.d'
    c.require(directory.is_dir() and not directory.is_symlink(), 'Original SDDM drop-in directory required')
    return dict(schema='arctic-safe-session-contract-v1',script=command,script_record=script_record,
                script_directory=str(Path(command).parent),
                script_security_label=security_label(script,query),
                script_owner=owner,session_record=session_record,session_argv=argv,
                configuration=inventory,profile_initialization='original packaged script; original argv chained')


def security_label(path,query=bounded):
    expected=query(['matchpathcon','-n',str(path)])
    observed=query(['stat','-c','%C','--',str(path)])
    c.require(all(re.fullmatch('[A-Za-z0-9_:.,-]{1,160}',v) and len(v.split(':'))>=4
                  for v in (expected,observed)),'Known SELinux context syntax required')
    return dict(policy_expected=expected,observed=observed)


def label_owned(wrapper,configuration,reference,reference_record,query=bounded,verify=None):
    """Only the acquired temporary wrapper can share the original script label."""
    c.require(protected(reference,True)==reference_record,'Trusted script changed before label handoff')
    original=security_label(reference,query)
    c.require(original['policy_expected']==original['observed'],'Original trusted script SELinux label differs')
    if verify:verify()
    query(['restorecon','-F','--',str(wrapper),str(configuration)])
    if verify:verify()
    script=security_label(wrapper,query);config=security_label(configuration,query)
    action='ordinary-policy-restore'
    if script['observed']!=original['observed']:
        # Fedora policy may name only the canonical basename. This gives only
        # our exact trusted-script chain the same existing entrypoint label;
        # no policy module, permission change or Enforcing exception is added.
        if verify:verify()
        query(['chcon','--reference='+str(reference),'--',str(wrapper)])
        if verify:verify()
        script=security_label(wrapper,query);action='owned-trusted-script-reference'
    c.require(script['observed']==original['observed']
              and config['observed']==config['policy_expected']
              and protected(reference,True)==reference_record,'Owned label handoff differs')
    return dict(script={**script,'reference':original['observed'],'action':action},configuration=config)


class OwnedSessionOverride:
    """Temporary diagnostic files retain acquired FD/inode/UID identities."""
    def __init__(self,root,nonce,arm,contract,labeler=None):
        c.require(re.fullmatch('[0-9a-f]{32}',nonce) and arm in c.ARMS,'Owned restart selector differs')
        self.root,self.files,self.contents=Path(root),{},{}
        self.wrapper=self.root/contract['script_directory'].lstrip('/')/('arctic-safe-'+nonce+'-'+arm+'.sh')
        self.configuration=self.root/('etc/sddm.conf.d/zzzz-arctic-safe-'+nonce+'.conf')
        self.contract,self.arm,self.labeler=contract,arm,labeler or label_owned

    def acquire(self,path,raw,mode):
        info=path.parent.lstat()
        c.require(stat.S_ISDIR(info.st_mode) and info.st_uid==os.geteuid()
                  and not info.st_mode & 0o022,'Owned override directory differs')
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,mode)
        self.files[path]=(fd,os.fstat(fd))
        c.require(os.write(fd,raw)==len(raw),'Owned override write was incomplete')
        self.contents[path]=hashlib.sha256(raw).hexdigest()
        os.fchmod(fd,mode)
        owned=os.fstat(fd);self.files[path]=(fd,owned);self.verify(path)
        # A retained writable FD makes executable scripts fail with ETXTBSY.
        # Pin the same acquired inode using O_PATH before closing that writer.
        retained=os.open(path,os.O_PATH|os.O_NOFOLLOW)
        held=os.fstat(retained)
        if (held.st_dev,held.st_ino,held.st_uid,held.st_mode)!=(owned.st_dev,owned.st_ino,owned.st_uid,owned.st_mode):
            os.close(retained);raise RuntimeError('Owned override handoff inode differs')
        self.files[path]=(retained,held);os.close(fd);self.verify(path)

    def verify(self,path):
        fd,owned=self.files[path];current=path.lstat();held=os.fstat(fd)
        c.require(stat.S_ISREG(current.st_mode) and
            (current.st_dev,current.st_ino,current.st_uid,current.st_mode)==
            (owned.st_dev,owned.st_ino,owned.st_uid,owned.st_mode)==
            (held.st_dev,held.st_ino,held.st_uid,held.st_mode),'Owned override inode differs')
        if path in self.contents:
            c.require(current.st_size==held.st_size==owned.st_size and c.sha(path)==self.contents[path],
                      'Owned override bytes differ')

    def install(self):
        # A later lexicographic drop-in could silently override the diagnostic.
        c.require(all(p.name<self.configuration.name for p in self.configuration.parent.glob('*.conf')),
                  'Higher-priority SDDM drop-in conflict')
        selector='unset WLR_SCENE_DEBUG_DAMAGE' if self.arm=='default-restart' else 'export WLR_SCENE_DEBUG_DAMAGE=rerender'
        raw=('#!/bin/sh\n'+selector+'\nexec '+shlex.quote(self.contract['script'])+' "$@"\n').encode()
        self.acquire(self.wrapper,raw,0o755)
        path='/'+str(self.wrapper.relative_to(self.root))
        self.acquire(self.configuration,('[Wayland]\nSessionCommand='+path+'\n').encode(),0o644)
        reference=self.root/self.contract['script'].lstrip('/')
        def verify():self.verify(self.wrapper);self.verify(self.configuration)
        labels=self.labeler(self.wrapper,self.configuration,reference,self.contract['script_record'],verify=verify)
        self.verify(self.wrapper);self.verify(self.configuration)
        effective,_=sddm_configuration(self.root)
        c.require(effective.get('Wayland',{}).get('SessionCommand')==path,'Effective diagnostic SessionCommand differs')
        return dict(arm=self.arm,wrapper=protected(self.wrapper,True),configuration=protected(self.configuration),
                    original_script=self.contract['script_record'],security_labels=labels,
                    selector='unset' if self.arm=='default-restart' else 'rerender')

    def close(self):
        errors=[]
        for path in (self.configuration,self.wrapper):
            if path not in self.files:continue
            fd,_=self.files[path]
            try:self.verify(path);path.unlink()
            except BaseException as error:errors.append(error)
            finally:os.close(fd)
        self.files.clear();self.contents.clear()
        if errors:raise errors[0]


def arm_desktop(native,arm,previous,original):
    """Rediscover the session after restart; never reuse an IPC prefix/socket."""
    mangos=[]
    for p in Path('/proc').glob('[0-9]*'):
        try:
            if p.stat().st_uid==1000 and (p/'comm').read_text().strip()=='mango':mangos.append(p)
        except OSError:pass
    c.require(len(mangos)==1,'One new live Mango required')
    mango=mangos[0];identity=native.identity(int(mango.name),1000)
    c.require(identity['executable']=='/usr/bin/mango' and identity!=previous,
              'Fresh actual Mango identity required')
    c.require(mango_argv(identity)==original['actual_mango_argv'],'Restart Mango argv differs')
    env=dict(v.split('=',1) for v in (mango/'environ').read_bytes().decode().split('\0') if '=' in v)
    observed={k:env[k] for k in sorted(ALLOWED_RENDERER_ENV) if k in env}
    expected=dict(original['renderer_environment'])
    if arm=='rerender-restart':expected['WLR_SCENE_DEBUG_DAMAGE']='rerender'
    c.require(observed==expected,'Actual restart renderer environment differs')
    c.require(c.sha('/usr/bin/mango')==original['mango']['sha256'],'Restart Mango binary differs')
    maps=(mango/'maps').read_text();c.require(len(maps)<1024**2,'Restart renderer maps exceed bound')
    mapped=sorted({str(Path(line.split()[-1]).resolve(strict=True)) for line in maps.splitlines()
        if line.split()[-1].startswith('/usr/') and
        re.search(r'/(?:lib[^/]*(?:EGL|GL|gbm|scenefx|wlroots|pixman|gallium|LLVM|drm|wayland)[^/]*\.so[^/]*|[^/]*dri\.so)$',line.split()[-1])})
    c.require(mapped==sorted(v['path'] for v in original['libraries'])
              and all(c.sha(v['path'])==v['sha256'] for v in original['libraries']),
              'Restart mapped renderer library identities differ')
    prefix=native.discover_desktop()
    monitors=c.strict(bounded([*prefix,'mmsg','get','all-monitors']))
    c.require(monitors==original['monitors'] and bounded(['getenforce'])=='Enforcing',
              'Restart output or security differs')
    # Bind the freshly discovered IPC prefix to this process's actual login
    # session, rather than selecting an unrelated liveuser Wayland session.
    session=env.get('XDG_SESSION_ID')
    c.require(type(session) is str and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',session)
              and prefix[:5]==['runuser','-u','liveuser','--','env']
              and [v for v in prefix[5:] if v.startswith('XDG_SESSION_ID=')]==['XDG_SESSION_ID='+session],
              'Restart Mango and fresh IPC prefix session differ')
    for key,expected in (('Id',session),('User','1000'),('Type','wayland')):
        c.require(bounded(['loginctl','show-session',session,'-p',key,'--value'])==expected,
                  'Restart login session identity differs')
    vt=bounded(['loginctl','show-session',session,'-p','VTNr','--value'])
    c.require(re.fullmatch('[1-9][0-9]?',vt),'Restart desktop VT differs')
    bounded(['chvt',vt])
    c.require(bounded(['loginctl','show-session',session,'-p','Active','--value'])=='yes',
              'Restart bound Wayland session is not active')
    binding=dict(id=session,uid=1000,type='wayland',vt=int(vt),active=True,prefix_bound=True)
    return prefix,dict(**identity,sha256=c.sha('/usr/bin/mango')),observed,monitors,int(vt),binding


def cpu_observation(identity):
    p=Path('/proc')/str(identity['pid']);fields=(p/'stat').read_text().rsplit(')',1)[1].split()
    c.require(int(fields[19])==identity['start_ticks'] and fields[0] not in ('Z','X'),'Observed Mango CPU identity differs')
    cpu=Path('/proc/stat').read_text().splitlines()[0].split()
    c.require(cpu[0]=='cpu' and all(v.isdigit() for v in cpu[1:]),'Aggregate CPU observation differs')
    return dict(guest_ns=time.monotonic_ns(),pid=identity['pid'],start_ticks=identity['start_ticks'],
                user_ticks=int(fields[11]),system_ticks=int(fields[12]),rss_pages=int(fields[21]),
                guest_cpu_ticks=[int(v) for v in cpu[1:]],clock_ticks=os.sysconf('SC_CLK_TCK'),page_bytes=os.sysconf('SC_PAGE_SIZE'))


def compositor_configuration():
    relative=['mango/config.conf','mango/settings.conf','mango/user.conf',
        *('mango/arctic/'+v+'.conf' for v in ('apps','autostart','binds','input','look','rules')),
        'arctic/current/mango-colors.conf','arctic/motion.conf','arctic/effects.conf']
    records={}
    for name in relative:
        path=Path('/home/liveuser/.config')/name
        if not path.exists():
            c.require(not path.is_symlink(),'Compositor configuration link is broken')
            records[name]=None;continue
        target=path.resolve(strict=True);info=target.stat()
        c.require(any(str(target).startswith(prefix) for prefix in
            ('/home/liveuser/.config/','/usr/share/arctic/')) and stat.S_ISREG(info.st_mode)
            and info.st_uid in (0,1000) and not info.st_mode & 0o022 and info.st_size<=65536,
            'Compositor configuration protection differs')
        records[name]=dict(bytes=info.st_size,sha256=c.sha(target))
    path=Path('/etc/arctic/mango/keyboard.conf')
    records['system-keyboard']=protected(path) if path.exists() else None
    return records


def mango_argv(identity):
    raw=(Path('/proc')/str(identity['pid'])/'cmdline').read_bytes()
    c.require(len(raw)<=4096 and raw.endswith(b'\0'),'Observed Mango argv bound differs')
    argv=raw[:-1].decode().split('\0')
    c.require(argv and argv[0] in ('mango','/usr/bin/mango')
              and all(re.fullmatch('[A-Za-z0-9_./=-]+',v) for v in argv),
              'Observed synthetic-session Mango argv differs')
    return argv


def _open_duplex_port(runtime):
    alias = Path('/dev/virtio-ports') / runtime.PORT_NAME
    canonical = alias.resolve(strict=True)
    runtime.require(canonical.parent == Path('/dev') and re.fullmatch('vport[0-9]+p[0-9]+', canonical.name),
            'taskbar named virtio port resolves outside the canonical device namespace')
    attrs = Path('/sys/class/virtio-ports') / canonical.name
    # Sysfs class entries are kernel-owned symlinks; their attributes bind the
    # named channel to the exact opened device, rather than trusting a dev alias.
    for path in (alias.parent, attrs / 'name', attrs / 'dev'):
        info = path.stat()
        runtime.require(info.st_uid == 0 and not info.st_mode & 0o022, 'taskbar device/sysfs metadata is unprotected')
    name = (attrs / 'name').read_text().strip()
    device = (attrs / 'dev').read_text().strip()
    runtime.require(name == runtime.PORT_NAME and re.fullmatch('[0-9]{1,5}:[0-9]{1,5}', device),
            'taskbar sysfs channel name/device differs')
    major, minor = (int(v) for v in device.split(':'))
    fd = os.open(canonical, os.O_RDWR | os.O_NOFOLLOW | os.O_NOCTTY | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        runtime.require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and (os.major(info.st_rdev), os.minor(info.st_rdev)) == (major, minor),
                'taskbar virtio device type/owner/protection/sysfs identity differs')
        receipt = dict(schema='arctic-taskbar-virtio-port-v1', name=runtime.PORT_NAME, device=str(canonical),
                       major=major, minor=minor, uid=info.st_uid, mode=stat.S_IMODE(info.st_mode))
        return runtime.PortWriter(fd), receipt
    except BaseException:
        os.close(fd)
        raise

def _duplex_fd(writer):
    """Duplicate the acquired file description; never open the device twice."""
    fd = None
    try:
        fd = os.dup(writer.fd)
        info, other = os.fstat(fd), os.fstat(writer.fd)
        c.require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                  and info.st_rdev == other.st_rdev and info.st_ino == other.st_ino,
                  'Duplex virtio identity differs')
        writer.close()
        return fd
    except BaseException:
        # Only descriptors acquired by this setup, preserving its primary failure.
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        try:
            writer.close()
        except OSError:
            pass
        raise


_guest_phase = 'entry'
_guest_context = None
_guest_primary = None


def _stage(phase):
    global _guest_phase
    c.require(phase in c.GUEST_PHASES, 'Guest source phase differs')
    _guest_phase = phase


def _observed(phase, action):
    _stage(phase)
    return action()


def _emit_status(phase, status, error):
    if _guest_context is None:
        return False
    try:
        value = c.guest_status(phase, status, error, _guest_context)
        print(c.GUEST_STATUS_PREFIX + json.dumps(value, sort_keys=True, allow_nan=False), flush=True)
        return True
    except Exception:
        # A reporting failure cannot replace the primary failure or publish text.
        return False


def execute():
    global _guest_phase, _guest_context, _guest_primary
    _guest_phase, _guest_context, _guest_primary = 'entry', None, None
    try:
        main()
    except Exception as error:
        phase, klass = _guest_primary or (_guest_phase, c.guest_exception_class(error))
        _emit_status(phase, 'exception', klass)
        try:
            print('ARCTIC-SAFE-DIAGNOSTIC-FAILED', flush=True)
        except Exception:
            pass
        return 1
    return 0 if _emit_status('complete', 'completed', None) else 1


def main():
    global _guest_context, _guest_primary
    _stage('entry')
    c.require(sys.argv[1:] == ['--disposable-guest'] and Path(__file__).resolve() == BASE / 'guest.py'
              and os.geteuid() == 0, 'Protected disposable guest entry required')
    _stage('context')
    runtime = load('safe_transport', BASE / 'taskbar-runtime.py')
    screen = load('safe_privacy', BASE / 'screen-evidence.py')
    ctx = c.context(c.strict(runtime.read_regular(BASE / 'context.json', root_owned=True)))
    _guest_context = ctx
    _stage('bundle')
    for name, expected in ctx['bundle'].items():
        raw = runtime.read_regular(BASE / name, root_owned=True)
        c.require(hashlib.sha256(raw).hexdigest() == expected, 'Protected guest bundle hash differs')
    _stage('native-import')
    native = load('safe_native', BASE / 'native_smoke.py')
    _stage('native-guard')
    native.guest_guard('live', True)
    _stage('boot-flags')
    tokens = Path('/proc/cmdline').read_text().strip().split()
    c.require('nomodeset' in tokens and 'arctic.mode=try' in tokens,
              'Requires original Safe Try boot flags')
    _stage('desktop-discovery')
    prefix = native.discover_desktop()
    _stage('mango-identity')
    mangos = []
    for p in Path('/proc').glob('[0-9]*'):
        try:
            if p.stat().st_uid == 1000 and (p / 'comm').read_text().strip() == 'mango':
                mangos.append(p)
        except OSError:
            pass
    c.require(len(mangos) == 1 and pwd.getpwuid(1000).pw_name == 'liveuser', 'Unique real live Mango identity required')
    mango = mangos[0]
    mango_identity = native.identity(int(mango.name), 1000)
    c.require(mango_identity['executable'] == '/usr/bin/mango', 'Actual Mango executable differs')
    _stage('renderer-environment')
    full_env = dict(v.split('=', 1) for v in (mango / 'environ').read_bytes().decode().split('\0') if '=' in v)
    allowed_env = {'WLR_RENDERER', 'WLR_RENDERER_ALLOW_SOFTWARE', 'WLR_RENDERER_FORCE_SOFTWARE',
                   'WLR_NO_HARDWARE_CURSORS', 'WLR_DRM_NO_ATOMIC', 'WLR_SCENE_DEBUG_DAMAGE',
                   'LIBGL_ALWAYS_SOFTWARE', 'MESA_LOADER_DRIVER_OVERRIDE', 'GALLIUM_DRIVER',
                   'WLR_BACKENDS', 'WLR_DRM_DEVICES', 'WLR_HEADLESS_OUTPUTS'}
    observed_env = {k: full_env[k] for k in sorted(allowed_env) if k in full_env}
    c.require(observed_env.get('WLR_RENDERER_FORCE_SOFTWARE') == '1'
              and observed_env.get('LIBGL_ALWAYS_SOFTWARE') == '1'
              and 'WLR_SCENE_DEBUG_DAMAGE' not in observed_env
              and 'WLR_RENDERER' not in observed_env, 'Safe baseline renderer environment differs')
    _stage('renderer-maps')
    maps = (mango / 'maps').read_text()
    c.require(len(maps) < 1024**2, 'Mango map observation exceeds bound')
    mapped = sorted({line.split()[-1] for line in maps.splitlines() if line.split()[-1].startswith('/usr/')
                     and re.search(r'/(?:lib[^/]*(?:EGL|GL|gbm|scenefx|wlroots|pixman|gallium|LLVM|drm|wayland)[^/]*\.so[^/]*|[^/]*dri\.so)$', line.split()[-1])})
    libraries = []
    for name in mapped:
        _stage('library-resolution')
        path = Path(name).resolve(strict=True)
        c.require(str(path).startswith('/usr/') and path.is_file(), 'Mapped renderer library path differs')
        libraries.append(dict(path=str(path), bytes=path.stat().st_size, sha256=c.sha(path),
                              rpm=_observed('library-owner-query', lambda: bounded(['rpm', '-qf', str(path)])).splitlines()))
    _stage('drm-fds')
    dri_fds = []
    for fd in (mango / 'fd').iterdir():
        try:
            target = os.readlink(fd)
            if re.fullmatch('/dev/dri/(?:card|renderD)[0-9]+', target):
                dri_fds.append(dict(fd=int(fd.name), device=target))
        except OSError:
            pass
    _stage('kernel-framebuffer')
    kernel_display = {}
    for name in ('name', 'virtual_size', 'stride', 'bits_per_pixel'):
        path = Path('/sys/class/graphics/fb0') / name
        if path.is_file():
            raw = path.read_bytes()
            c.require(len(raw) < 4096, 'Framebuffer attribute exceeds bound')
            kernel_display[str(path)] = raw.decode().strip()
    _stage('kernel-drm')
    drm = {}
    for path in sorted(Path('/sys/class/drm').glob('card*/*')):
        if path.name not in ('status', 'modes', 'enabled', 'uevent') or not path.is_file():
            continue
        raw = path.read_bytes()
        c.require(len(raw) <= 16384, 'DRM attribute exceeds bound')
        drm[str(path)] = raw.decode().strip()
    _stage('existing-debugfs')
    debugfs = {}
    for path in sorted(Path('/sys/kernel/debug/dri').glob('*/framebuffer')):
        if path.is_file():
            raw = path.read_bytes()
            c.require(len(raw) < 65536, 'Existing debugfs framebuffer exceeds bound')
            debugfs[str(path)] = raw.decode().strip()
    _stage('renderer-journal')
    journal = bounded(['journalctl', '--no-pager', '--boot=0', '-o', 'short-monotonic',
                       '_COMM=mango', '_PID='+mango.name, '-n', '400'])
    renderer_lines = [line for line in journal.splitlines()
                      if re.search(r'renderer|allocator|EGL|GLES|OpenGL|DRM|dmabuf|buffer|stride|damage|llvmpipe|softpipe', line, re.I)]
    _stage('monitor-query')
    monitors = c.strict(bounded([*prefix, 'mmsg', 'get', 'all-monitors']))
    c.require(type(monitors) is dict and len(monitors.get('monitors', [])) == 1, 'Single original output required')
    _stage('output-validation')
    output = monitors['monitors'][0]
    name = output.get('name')
    c.require(type(name) is str and re.fullmatch('[A-Za-z0-9_.-]{1,63}', name), 'Output name differs')
    # Geometry is also independently attested by the Wayland output listener.
    _stage('workspace')
    root = Path('/tmp') / ('arctic-native-smoke-safe-' + ctx['binding_id'])
    root.mkdir(mode=0o700)
    os.chown(root, 1000, 1000)
    _stage('port-open')
    runtime.PORT_NAME = 'arctic-safe-evidence'
    writer, port = _open_duplex_port(runtime)
    _stage('port-duplex')
    fd = _duplex_fd(writer)
    channel = c.Channel(fd, ctx['binding_id'])
    report = dict(schema='arctic-safe-guest-observation-v1', context=ctx,
                  release_acceptance=False, image_qualified=False, performance_acceptance=False,
                  observer_profile_admitted=False, cmdline_tokens=tokens,
                  mango={**mango_identity, 'sha256': c.sha('/usr/bin/mango')},
                  renderer_environment=observed_env, libraries=libraries, drm_fds=dri_fds,
                  kernel_display=kernel_display, drm=drm, existing_debugfs=debugfs,
                  renderer_journal_lines=renderer_lines,
                  renderer_journal_scope=dict(boot='current',pid=int(mango.name),comm='mango',
                                               last_records=400,output='short-monotonic'),
                  monitors=monitors, port=port,
                  packages=_observed('package-query', lambda: bounded(['rpm', '-q', 'mangowm', 'scenefx', 'wlroots', 'mesa-dri-drivers', 'foot'])).splitlines(),
                  selinux_before=_observed('selinux-before', lambda: bounded(['getenforce'])), samples=[], interventions=[],
                  limitations=['Renderer/allocator facts are observations; absent journal or kernel fields remain unknown.',
                               'wl_shm readback can trigger repaint; QMP frames bracket every readback.',
                               'Guest/host monotonic clocks are separate; protocol establishes causal ordering.'])
    original=copy.deepcopy(report)
    original['compositor_configuration']=compositor_configuration()
    original['actual_mango_argv']=mango_argv(mango_identity)
    _stage('hello-send')
    channel.send('HELLO', dict(context=ctx,guest_ns=time.monotonic_ns(),output=name,original=original))
    _stage('hello-ack')
    channel.expect('HELLO-ACK',dict(execution_sha=ctx['execution_sha']))
    contract=_observed('session-contract',session_contract)
    c.require(original['actual_mango_argv'][1:]==contract['session_argv'][1:],
              'Original desktop/session argv differs')
    previous=dict(mango_identity)
    try:
        for arm in c.ARMS:
            _stage('session-handoff')
            override=OwnedSessionOverride(Path('/'),ctx['binding_id'],arm,contract)
            primary=None;old_fd=None
            try:
                handoff=override.install()
                old_fd=os.pidfd_open(previous['pid'])
                c.require(native.identity(previous['pid'],1000)==previous,'Old Mango changed before restart')
                request_ns=time.monotonic_ns()
                bounded(['systemctl','restart','sddm.service'],timeout=40)
                c.require(select.select([old_fd],[],[],60)[0],'Original Mango did not end after owned service restart')
                old_exit_ns=time.monotonic_ns()
                deadline=time.monotonic()+60
                while True:
                    try:
                        prefix,new_mango,environment,monitors,vt,session=arm_desktop(native,arm,previous,original)
                        break
                    except (OSError,RuntimeError,UnicodeError):
                        c.require(time.monotonic()<deadline,'New attested desktop readiness deadline')
                        time.sleep(.2)
                c.require(compositor_configuration()==original['compositor_configuration'],
                          'Restart compositor configuration changed')
                ready_ns=time.monotonic_ns()
                report=copy.deepcopy(original)
                # These observations belonged to the initial process. Keep
                # their attribution explicit instead of presenting old FDs or
                # journal records as facts about the restarted compositor.
                report['pre_restart_observation']=dict(mango=original['mango'],
                    **{key:report.pop(key) for key in ('drm_fds','kernel_display','drm',
                        'existing_debugfs','renderer_journal_lines','renderer_journal_scope')})
                report.update(arm=arm,mango=new_mango,renderer_environment=environment,monitors=monitors,
                    session=session,samples=[],interventions=[dict(kind='owned-SDDM-SessionCommand-restart',
                        restart_request_ns=request_ns,old_mango=previous,old_identity_ended_ns=old_exit_ns,
                        new_mango=new_mango,desktop_vt=vt,ready_guest_ns=ready_ns)],session_contract=contract,
                    session_handoff=handoff,cpu_observations=[])
                arm_root=root/arm;arm_root.mkdir(mode=0o700);os.chown(arm_root,1000,1000)
                idle_before=cpu_observation(new_mango)
                _stage('arm-ready')
                channel.send('ARM-READY',dict(arm=arm,guest_ns=ready_ns,mango=new_mango,
                    renderer_environment=environment,output=name,session_handoff=handoff,session=session))
                _stage('arm-baseline')
                ack=channel.expect('ARM-BASELINE-DONE',dict(arm=arm,frames=3),timeout=150)
                report['cpu_observations'].append(dict(kind='unobstructed-arm-idle',
                    before=idle_before,after=cpu_observation(new_mango)))
                active_before=cpu_observation(new_mango)
                # The original raw capture operations, delays and synthetic text are retained.
                capture_arm(native,prefix,name,arm_root,report,channel,screen,arm,active_before)
                previous={k:new_mango[k] for k in ('pid','start_ticks','executable')}
            except BaseException as error:
                primary=error
                if _guest_primary is None:
                    _guest_primary=(_guest_phase,c.guest_exception_class(error))
                raise
            finally:
                if old_fd is not None:os.close(old_fd)
                try:override.close()
                except BaseException:
                    if primary is None:raise
            c.require(sddm_configuration()[1]==contract['configuration'],
                      'Original SDDM configuration was not restored')
        print('ARCTIC-SAFE-DIAGNOSTIC-COMPLETE',flush=True)
    finally:
        os.close(fd)


def capture_arm(native,prefix,name,root,report,channel,screen,arm,active_before=None):
    global _guest_primary
    foot = None
    foot_fd = None
    try:
        time.sleep(3)
        _stage('capture')
        for label in c.PAIRS:
            if label == 'terminal-initial':
                # Only synthetic public text. No stdin/audio, shell history, or user data.
                script = "printf 'Arctic Safe rendering diagnostic\\n'; sleep 8; i=0; while [ $i -lt 12 ]; do printf 'Synthetic repaint %02d\\n' $i; i=$((i+1)); sleep 1; done; sleep 120"
                foot = subprocess.Popen([*prefix, '/usr/bin/foot', '--title', 'Arctic-Safe-Diagnostic', '/bin/sh', '-c', script],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
                report['interventions'].append(dict(kind='owned-synthetic-Foot-launch', guest_ns=time.monotonic_ns(), wrapper_pid=foot.pid,
                           executable_sha256=c.sha('/usr/bin/foot')))
                time.sleep(2)
                c.require(foot.poll() is None, 'Owned Foot exited before terminal observation')
                deadline = time.monotonic()+10
                clients = []
                while time.monotonic()<deadline:
                    before_clients = c.strict(bounded([*prefix, 'mmsg', 'get', 'all-clients']))
                    clients = [v for v in before_clients.get('clients', []) if v.get('title') == 'Arctic-Safe-Diagnostic'
                               and v.get('is_visible') is True]
                    if clients: break
                    time.sleep(.2)
                c.require(len(clients) == 1 and clients[0].get('is_visible') is True
                          and clients[0].get('is_xwayland') is False and clients[0].get('monitor') == name,
                          'Unique synthetic native Foot window is not mapped on the observed output')
                owned = native.identity(clients[0]['pid'], 1000)
                ancestry = [owned['pid']]
                while ancestry[-1] != foot.pid and len(ancestry)<16:
                    status = Path('/proc')/str(ancestry[-1])/'status'
                    ppid = re.search(r'^PPid:\s+([0-9]+)$', status.read_text(), re.M)
                    c.require(ppid and int(ppid[1])>1, 'Mapped Foot ancestry does not reach the owned wrapper')
                    ancestry.append(int(ppid[1]))
                c.require(owned['executable'] == '/usr/bin/foot' and ancestry[-1] == foot.pid,
                          'Mapped Foot differs from the acquired child tree')
                foot_fd = os.pidfd_open(owned['pid'])
                c.require(native.identity(owned['pid'],1000)==owned, 'Mapped Foot identity changed at pidfd acquisition')
                report['terminal_window'] = dict(identity=owned, monitor=name, title='Arctic-Safe-Diagnostic',
                          visible=True, native_wayland=True, width=clients[0]['width'], height=clients[0]['height'],
                          owned_ancestry=ancestry)
            elif label == 'terminal-repaint':
                time.sleep(22)
            before_request = time.monotonic_ns()
            channel.send('CAPTURE-REQUEST', dict(label=label, guest_ns=before_request))
            ack = channel.expect('QMP-BEFORE', timeout=30)
            c.require(set(ack) == {'label', 'host_ns'} and ack['label'] == label and type(ack['host_ns']) is int,
                      'QMP-before acknowledgement differs')
            start_ns = time.monotonic_ns()
            path = root / (label + '-wayland.rgb')
            capture = subprocess.run([*prefix, str(BASE / 'raw-screencopy'), name, str(path)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=20)
            end_ns = time.monotonic_ns()
            c.require(capture.returncode == 0 and not capture.stdout and len(capture.stderr) <= 16384,
                      'Wayland readback failed or exceeds bounds')
            screen.external_text(capture.stderr)
            (root / (label + '-wayland.log')).write_bytes(capture.stderr)
            descriptor = c.strict(c.regular(Path(str(path)+'.json'), owner=1000).read_bytes())
            c.require(descriptor['width'] == descriptor['output_width'] == 1920
                      and descriptor['height'] == descriptor['output_height'] == 1080
                      and descriptor['output_scale'] == 1 and descriptor['output_transform'] == 0
                      and descriptor['selected_output'] == name and descriptor['outputs_seen'] == 1
                      and descriptor['raw_bytes'] == descriptor['stride'] * descriptor['height']
                      and descriptor['flags'] in (0, 1), 'Original physical output or raw descriptor differs')
            files = {p.name: dict(bytes=c.regular(p).stat().st_size, sha256=c.sha(p))
                     for p in root.iterdir() if p.name.startswith(label + '-wayland')}
            channel.send('CAPTURE-DONE', dict(label=label, guest_ns=end_ns))
            after = channel.expect('QMP-AFTER', timeout=30)
            c.require(set(after) == {'label', 'host_ns'} and after['label'] == label and type(after['host_ns']) is int,
                      'QMP-after acknowledgement differs')
            report['samples'].append(dict(label=label, request_ns=before_request, capture_start_ns=start_ns,
                         capture_end_ns=end_ns, qmp_before_ack=ack, qmp_after_ack=after,
                         descriptor=descriptor, files=files))
        report['cpu_observations'].append(dict(kind='original-fixed-Foot-capture-window',
            before=active_before,after=cpu_observation(report['mango'])))
        _stage('export')
        report['selinux_after'] = bounded(['getenforce'])
        c.require(report['selinux_before'] == report['selinux_after'] == 'Enforcing', 'SELinux observation differs')
        raw = (json.dumps(report, sort_keys=True, allow_nan=False) + '\n').encode()
        screen.external_text(raw)
        (root / 'guest-report.json').write_bytes(raw)
        # All text members are screened before any byte enters the transport.
        for path in root.iterdir():
            if path.suffix in ('.json', '.log'):
                screen.external_text(c.regular(path).read_bytes())
        c.export_files(channel, root)
        channel.expect('RECEIVED', dict(files=len(c.GUEST_FILES), arm=arm), timeout=30)
        return report
    except BaseException as error:
        _guest_primary = (_guest_phase, c.guest_exception_class(error))
        raise
    finally:
        if foot_fd is not None:
            try:
                signal.pidfd_send_signal(foot_fd, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if foot is not None and foot.poll() is None:
            # This process group was acquired by this exact Popen invocation.
            os.killpg(foot.pid, signal.SIGTERM)
            try:
                foot.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(foot.pid, signal.SIGKILL); foot.wait(timeout=5)
        if foot_fd is not None:
            try:
                signal.pidfd_send_signal(foot_fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.close(foot_fd)


if __name__ == '__main__':
    raise SystemExit(execute())
