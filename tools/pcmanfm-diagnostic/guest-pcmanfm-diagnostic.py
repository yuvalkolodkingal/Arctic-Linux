#!/usr/bin/env python3
"""Explicit disposable live guest diagnosis; never a release acceptance checker."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import zlib

NATIVE_SHA = 'ed382ab80a4918118370253c383b0fefde116ba34d55e977bcd34607ad2632d0'
LAUNCHER_SHA = 'e948f2ff9c7273f20b0d42e67cc891e3a3f6e0954dfc1ac3afca2aa7c3d7df4c'
HERE = Path(__file__).resolve().parent
MAX_FILE, MAX_TOTAL = 4*1024*1024, 16*1024*1024


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(name, path, expected):
    require(hashlib.sha256(path.read_bytes()).hexdigest() == expected, 'frozen dependency changed: '+str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


N = load('frozen_native_smoke_v4', HERE/'native_smoke.py', NATIVE_SHA)


def stable_client(before, after, proof):
    keys = ('id','pid','foreign_toplevel_id','appid','x','y','width','height','monitor','is_xwayland')
    require(before.get('pid') == after.get('pid') == proof['pid']
            and str(before.get('id')) == str(after.get('id')) == proof['client_id']
            and all(before.get(k) == after.get(k) for k in keys)
            and isinstance(before.get('foreign_toplevel_id'), str) and before['foreign_toplevel_id']
            and before.get('is_focused') is True and after.get('is_focused') is True
            and before.get('is_visible') is True and after.get('is_visible') is True
            and before.get('is_xwayland') is False, 'owned focused native client changed around observation')


def observe(smoke, proof, label):
    before = smoke.alive(proof)
    result = smoke.cmd(['python3','/run/t/atspi-snapshot.py',json.dumps(proof,sort_keys=True)],
                       original=True, timeout=6, allow_failure=True)
    after = smoke.alive(proof); stable_client(before,after,proof)
    require(len(result[1].encode()) <= 256*1024, 'owned snapshot exceeds bound')
    value = json.loads(result[1])
    require(value.get('status') in ('observed','unavailable') and result[0] == 0,
            'owned AT-SPI collector failed: '+str(value))
    if value['status'] == 'observed':
        require(value.get('process') == proof and value.get('entry',{}).get('description') == 'Folder location bar',
                'owned entry location identity differs')
    record = dict(label=label,monotonic_ns=time.monotonic_ns(),process=proof,before=before,after=after,snapshot=value)
    path = smoke.write(label+'.json',(json.dumps(record,indent=2)+'\n').encode())
    record['evidence_sha256'] = N.digest(path)
    smoke.trace('owned-entry-observation', **record)
    if hasattr(smoke,'diagnostic_roles'):
        smoke.trace('role-lifecycle',label=label,**role_lifecycle(smoke,smoke.diagnostic_roles))
    return record


def navigation_result(smoke, call, label):
    started = time.monotonic()
    try:
        call()
        result = dict(status='matched-directory',monotonic_start_seconds=started,monotonic_end_seconds=time.monotonic())
    except RuntimeError as exc:
        wanted = 'bounded functional gate timed out: PCManFM directory title after Return: files with spaces'
        require(str(exc) == wanted, 'unexpected navigation/collector failure: '+str(exc))
        result = dict(status='failed-30s-title-gate',error=str(exc),monotonic_start_seconds=started,
                      monotonic_end_seconds=time.monotonic())
        smoke.diagnostic(label+'-failure', required=True)
    return result


def scenario(smoke, observed):
    directory = smoke.root/'files with spaces'
    smoke.write('files with spaces/editor fixture.txt', b'Initial fixture; must change through GUI.\n')
    marker = smoke.root/'terminal-role.json'
    code = ('import json,os,pathlib,time;pathlib.Path('+repr(str(marker))+').write_text('
            'json.dumps(dict(uid=os.getuid(),nonce='+repr(smoke.root.name)+')));time.sleep(60)')
    if observed:
        # Declared instrumented-arm fixture difference; never changes the original literal fixture.
        code=code.replace('time.sleep(60)','time.sleep(180)')
    terminal = smoke.fresh_window(lambda:smoke.cmd(['/usr/bin/arctic-open','terminal','--app-id','arctic-native-role',
                          '-e','python3','-c',code]),'foot',r'^arctic-native-role$')
    smoke.wait(lambda:marker.is_file())
    require(json.loads(marker.read_text()) == dict(uid=smoke.uid,nonce=smoke.root.name), 'literal terminal marker differs')
    editor = smoke.fresh_window(lambda:smoke.cmd(['/usr/bin/arctic-open','editor']),'featherpad',r'featherpad')
    if observed:
        files = smoke.fresh_window(lambda:smoke.launch(['python3','/run/t/bounded-launch.py',str(smoke.root)]),
                                   'pcmanfm',r'^pcmanfm$',native=True)
    else:
        files = smoke.fresh_window(lambda:smoke.cmd(['/usr/bin/arctic-open','files']),
                                   'pcmanfm',r'^pcmanfm$',native=True)
    roles=dict(terminal=terminal,editor=editor,files=files)
    smoke.diagnostic_roles=roles
    smoke.trace('role-fixture',observed=observed,terminal_lifetime_seconds=180 if observed else 60,
                **role_lifecycle(smoke,roles))
    return directory,files,roles


def role_lifecycle(smoke, roles):
    clients=smoke.clients();items={}
    for name,proof in roles.items():
        try:
            current=N.identity(proof['pid'],smoke.uid)
            same=all(current[k]==proof[k] for k in ('pid','start_ticks','executable'))
            items[name]=dict(process=proof,current_identity=current,same_identity=same,
                             client=clients.get(proof['client_id']),status='owned' if same else 'changed')
        except (FileNotFoundError,ProcessLookupError,RuntimeError) as exc:
            items[name]=dict(process=proof,status='retired-or-unavailable',detail=str(exc))
    return dict(monotonic_ns=time.monotonic_ns(),roles=items)


def observed_navigate(smoke, proof, directory):
    # Frozen four literal inputs, pauses, warm-up and title gate are retained; observation time is declared separately.
    require(directory.is_dir() and not directory.is_symlink() and directory.resolve().is_relative_to(smoke.root),
            'navigation fixture is outside owned guest evidence')
    smoke.diagnostic('text-fixture-before-location')
    observe(smoke,proof,'entry-00-before-control-l')
    smoke.keys(proof,'-M','ctrl','-k','l','-m','ctrl')
    observe(smoke,proof,'entry-01-after-control-l')
    time.sleep(.3);smoke.diagnostic('text-fixture-location-focused')
    observe(smoke,proof,'entry-02-before-control-a')
    smoke.keys(proof,'-M','ctrl','-k','a','-m','ctrl')
    observe(smoke,proof,'entry-03-after-control-a')
    observe(smoke,proof,'entry-04-before-literal-path')
    smoke.keys(proof,str(directory))
    observe(smoke,proof,'entry-05-after-literal-path')
    time.sleep(.3);smoke.diagnostic('text-fixture-path-typed')
    observe(smoke,proof,'entry-06-before-virtual-return')
    smoke.keys(proof,'-k','Return')
    observe(smoke,proof,'entry-07-after-virtual-return')
    smoke.wait(lambda:directory.name in smoke.alive(proof).get('title',''),30,
               label='PCManFM directory title after Return: '+directory.name)
    smoke.diagnostic('text-fixture-navigation-confirmed')


def physical_precondition(value, proof, directory):
    snap = value.get('snapshot',{})
    if snap.get('status') != 'observed':
        return False
    entry = snap.get('entry',{})
    return (snap.get('process') == proof and entry.get('description') == 'Folder location bar'
            and entry.get('text') == str(directory) and entry.get('state',{}).get('focused') is True
            and entry['state'].get('showing') is True and entry['state'].get('visible') is True
            and len(snap.get('frames',[])) == 1 and snap['frames'][0] in entry.get('ancestors',[]))


def physical(smoke, proof, directory, virtual):
    if virtual['status'] != 'failed-30s-title-gate':
        return dict(status='unrun',reason='instrumented virtual title gate did not fail')
    fresh = observe(smoke,proof,'entry-08-physical-precondition')
    if not physical_precondition(fresh,proof,directory):
        return dict(status='unrun',reason='fresh exact focused location entry unavailable',precondition=fresh)
    smoke.diagnostic('physical-before-request')
    # Reobserve after the screenshot, immediately before publishing the only one-use request.
    fresh = observe(smoke,proof,'entry-09-physical-immediate-precondition')
    require(physical_precondition(fresh,proof,directory), 'physical binding changed after screenshot; no input authorized')
    request = dict(schema='arctic-pcmanfm-physical-request-v1',nonce=uuid.uuid4().hex,
                   arm='observed-route',
                   boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                   process=proof,client=fresh['after'],entry=fresh['snapshot']['entry'],
                   entry_evidence_sha256=fresh['evidence_sha256'],fixture_path=str(directory),
                   virtual_status=virtual['status'],monotonic_ns=time.monotonic_ns(),release_acceptance=False)
    print('ARCTIC-PCMANFM-PHYSICAL-REQUEST '+json.dumps(request,sort_keys=True),flush=True)
    started=time.monotonic()
    try:
        smoke.wait(lambda:directory.name in smoke.alive(proof).get('title',''),30,
                   label='separate physical Return directory title: '+directory.name)
        outcome='matched-directory-after-request'
    except RuntimeError as exc:
        require(str(exc)=='bounded functional gate timed out: separate physical Return directory title: files with spaces',
                'physical diagnostic failure: '+str(exc))
        outcome='title-unchanged-after-request'
    after=observe(smoke,proof,'entry-10-after-physical-request')
    smoke.diagnostic('physical-after-request')
    return dict(status=outcome,request=request,after=after,monotonic_start_seconds=started,
                monotonic_end_seconds=time.monotonic(),delivery='unknown until separately paired host acknowledgement',
                release_acceptance=False)


def target_environment(smoke, proof):
    before=N.identity(proof['pid'],smoke.uid)
    require(all(before[k]==proof[k] for k in ('pid','start_ticks','executable')),'target changed before environment/maps read')
    raw=(Path('/proc')/str(proof['pid'])/'environ').read_bytes()
    require(len(raw)<=1024*1024,'owned process environment bound exceeded')
    whitelist={'WAYLAND_DISPLAY','GDK_BACKEND','GTK_IM_MODULE','GTK_MODULES','XMODIFIERS','NO_AT_BRIDGE','LANG','LC_ALL','LC_MESSAGES'}
    selected={}
    for row in raw.split(b'\0'):
        if b'=' not in row:continue
        key,value=row.split(b'=',1)
        if key.decode(errors='replace') in whitelist:
            require(len(value)<=4096,'whitelisted environment field too long')
            selected[key.decode()]=value.decode(errors='replace')
    maps=(Path('/proc')/str(proof['pid'])/'maps').read_text()
    require(len(maps.encode())<=2*1024*1024,'owned mappings exceed bound')
    libraries=sorted(set(row.split()[-1] for row in maps.splitlines() if '/' in row
                         and re.search(r'libgtk|libgdk|libfm|immodules|ibus|fcitx',row)))
    after=N.identity(proof['pid'],smoke.uid)
    require(all(after[k]==proof[k] for k in ('pid','start_ticks','executable')),'target changed while reading environment/maps')
    return dict(whitelisted_environment=selected,input_tool_rpm=smoke.cmd(['rpm','-qf','/usr/bin/wtype'],original=True)[1],
                input_tool_verification=smoke.cmd(['rpm','-V','wtype'],original=True)[1],
                input_tool_sha256=N.digest(Path('/usr/bin/wtype')),actual_mapped_libraries=libraries,
                scope='actual owned process reads; no input-method changes or private GTK activation observation')


def control_keys(smoke, proof, argv, warmup):
    if warmup:
        smoke.keys(proof,*argv)
        return
    smoke.trace('control-input-before',proof=proof,argv=argv,warmup=False,client=smoke.alive(proof))
    answer=json.loads(smoke.cmd(['mmsg','dispatch','focusid','client,'+proof['client_id']])[1])
    require(answer.get('success') is True,'control focus dispatch failed')
    smoke.wait(lambda:smoke.alive(proof).get('is_focused') is True,10)
    smoke.cmd(['wtype','-s','200','-s','150',*argv],timeout=30)
    smoke.trace('control-input-after',proof=proof,argv=argv,warmup=False,client=smoke.alive(proof))


def gtk_control(smoke, warmup):
    probe=smoke.cmd(['python3','-c',"import gi;gi.require_version('Gtk','3.0');from gi.repository import Gtk;print(Gtk.get_major_version())"],
                    original=True,timeout=10,allow_failure=True)
    if probe[0]!=0:
        return dict(status='unavailable',reason='shipped Gtk3 GI capability probe failed',probe=probe)
    require(probe[1]=='3','Gtk3 probe returned another major version')
    appid='org.arctic.Diagnostic.Entry.a'+uuid.uuid4().hex[:16]
    proof=smoke.fresh_window(lambda:smoke.launch(['python3','/run/t/gtk-entry-control.py',str(smoke.root),appid]),
                             'python3',re.escape(appid),native=True)
    text='Arctic isolated GTK3 entry'
    smoke.diagnostic('gtk-before-input')
    for index,argv in enumerate((['-M','ctrl','-k','a','-m','ctrl'],[text],['-k','Return'])):
        control_keys(smoke,proof,argv,warmup)
        smoke.diagnostic('gtk-after-turn-'+str(index))
    log=smoke.root/'gtk-events.log'
    def activated():
        smoke.alive(proof)
        require(not (smoke.root/'gtk-control-error.json').exists(),'Gtk3 control log/preservation failed')
        require(log.is_file() and log.stat().st_size<=2*1024*1024,'Gtk3 own event log unavailable/unbounded')
        rows=[json.loads(row) for row in log.read_text().splitlines()]
        return next((row for row in rows if row.get('event')=='activate' and row.get('text')==text
                     and row.get('pid')==proof['pid'] and row.get('uid')==smoke.uid and row.get('has_focus') is True),None)
    try:
        value=smoke.wait(activated,30,label='isolated Gtk3 entry activation')
        status='own-entry-activated'
    except RuntimeError as exc:
        require(str(exc)=='bounded functional gate timed out: isolated Gtk3 entry activation','Gtk3 control failure: '+str(exc))
        value=None;status='own-entry-not-activated'
    smoke.diagnostic('gtk-final')
    return dict(status=status,warmup=warmup,process=proof,activation=value,
                scope='only own simple Gtk3 entry; no libfm/completion or PCManFM qualification')


def copy_evidence(smoke, aggregate, name):
    target=aggregate/name
    require(not target.is_symlink(),'aggregate arm target symlink refused')
    target.mkdir(exist_ok=True)
    require(not any(p.is_symlink() for p in target.rglob('*')),'aggregate arm evidence contains symlink')
    for path in sorted(smoke.root.rglob('*')):
        require(not path.is_symlink(),'owned arm evidence contains symlink')
        if not path.is_file() or path.suffix.lower() not in ('.json','.png','.log','.txt','.tsv'):continue
        require(path.stat().st_size<=MAX_FILE,'arm evidence file exceeds bound')
        destination=target/path.relative_to(smoke.root);destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,destination)


def write_arm_report(smoke,name,cleanup,phase='arm-cleanup'):
    smoke.write('arm-report.json',json.dumps(dict(name=name,steps=smoke.steps,owned=smoke.owned,cleanup=cleanup,preservation_phase=phase,
        trace=dict(bytes=smoke.trace_bytes,omitted_records=smoke.trace_omitted,bound_bytes=2*1024*1024,
                   required=True)),indent=2).encode())


def require_complete_trace(smoke):
    require(type(smoke.trace_omitted) is int and smoke.trace_omitted==0
            and type(smoke.trace_bytes) is int and 0<=smoke.trace_bytes<=2*1024*1024,
            'required diagnostic trace omitted records or exceeded 2 MiB')


def strict_security(value):
    audit=value.get('audit',{})
    require(value.get('selinux')=='Enforcing' and audit=={'enabled':1,'lost':0}
            and all(type(audit.get(k)) is int for k in ('enabled','lost')),
            'diagnostic requires actual Enforcing/audit enabled=1/lost=0 throughout')


def bounded_command(argv, root, name, limit, timeout):
    """Bound child file output before execution; no guest package/config changes."""
    require(root.is_dir() and not root.is_symlink() and re.fullmatch('[a-z0-9-]+',name), 'unsafe command evidence root/name')
    paths=[root/(name+suffix) for suffix in ('.stdout.log','.stderr.log')]
    def child_limit():
        resource.setrlimit(resource.RLIMIT_FSIZE,(limit,limit))
    started=time.monotonic();timed_out=False
    with paths[0].open('xb') as stdout, paths[1].open('xb') as stderr:
        child=subprocess.Popen(argv,stdout=stdout,stderr=stderr,preexec_fn=child_limit)
        try:
            try:code=child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out=True;child.kill();code=child.wait(timeout=3)
        finally:
            if child.poll() is None:
                child.kill();child.wait(timeout=3) # Only this direct unreaped child.
    sizes=[p.stat().st_size for p in paths]
    require(all(n<limit for n in sizes) and sum(sizes)<=limit,'bounded command output exceeded preservation limit: '+name)
    return dict(argv=argv,exit_status=code,timed_out=timed_out,timeout_seconds=timeout,combined_limit_bytes=limit,
                monotonic_start_seconds=started,monotonic_end_seconds=time.monotonic(),
                stdout=dict(path=paths[0].relative_to(root.parent).as_posix(),bytes=sizes[0],sha256=N.digest(paths[0])),
                stderr=dict(path=paths[1].relative_to(root.parent).as_posix(),bytes=sizes[1],sha256=N.digest(paths[1])))


def codec_diagnostic(prefix, aggregate):
    root=aggregate/'post-arm-codec';root.mkdir()
    binary=Path('/usr/bin/ffmpeg');fixture=HERE/'original-h264-aac-1s.mp4'
    require(fixture.stat().st_size==14443 and N.digest(fixture)=='24fcb595e3c63e836a9ebae43c05c902b88b954aea73abde35de8c6fc86497b8',
            'original codec fixture differs')
    manifest=json.loads((HERE/'codec-fixture-manifest.json').read_text())
    require(manifest['bytes']==14443 and manifest['sha256']==N.digest(fixture),'codec fixture manifest differs')
    verification=N.execute(['rpm','-Vf',str(binary)],allow_failure=True)
    identity=dict(path=str(binary),resolved_path=str(binary.resolve(strict=True)),bytes=binary.stat().st_size,
                  sha256=N.digest(binary),rpm=N.execute(['rpm','-qf',str(binary)])[1],
                  rpm_verification=dict(exit_status=verification[0],stdout=verification[1],stderr=verification[2]))
    records=[]
    for flag in ('-version','-buildconf','-decoders','-encoders'):
        records.append(bounded_command(prefix+[str(binary),'-nostdin',flag],root,'capability-'+flag[1:],256*1024,15))
        require(records[-1]['exit_status']==0 and not records[-1]['timed_out'],'native capability collector failed: '+flag)
    options={'video':['-map','0:v:0','-an','-sn','-dn','-pix_fmt','yuv420p','-f','rawvideo'],
             'audio':['-map','0:a:0','-vn','-sn','-dn','-acodec','pcm_s16le','-f','s16le']}
    decodes={}
    for stream,argv in options.items():
        decodes[stream]=bounded_command(prefix+[str(binary),'-nostdin','-v','error','-xerror','-err_detect','explode',
            '-i',str(fixture),*argv,'pipe:1'],root,'decode-'+stream,1024*1024,15)
        decodes[stream]['interpretation']='actual command decode only; unsupported codec/error is retained; no displayed media/audio claim'
    require(N.digest(binary)==identity['sha256'],'FFmpeg executable changed during post-arm diagnostics')
    value=dict(binary=identity,fixture=manifest,capabilities=records,decodes=decodes,after_all_navigation_arms=True,
               release_acceptance=False,scope='native shipped codec capability and one original H264/AAC sample; no playback or parity gate')
    (root/'codec-report.json').write_text(json.dumps(value,indent=2)+'\n')
    return value


def bounded_journals(prefix,aggregate):
    root=aggregate/'post-arm-journal';root.mkdir()
    values={}
    for name,argv in (('system',['journalctl','-b','--no-pager','-n','250','-o','json']),
                      ('user',prefix+['journalctl','--user','-b','--no-pager','-n','250','-o','json'])):
        values[name]=bounded_command(argv,root,name,1024*1024,15)
        require(values[name]['exit_status']==0 and not values[name]['timed_out'],'current-boot journal collector failed: '+name)
    return dict(records=values,scope='bounded final 250 records of current-boot system and actual desktop user journals; AVC interval separately strict')


def run_diagnosis(prefix, aggregate):
    arms=[]; security=N.SecurityInterval(); results=[]; errors=[]
    try:
        strict_security(security.before)
        for name, observed in (('original-route',False),('observed-route',True)):
            smoke=N.Smoke(prefix,'live');arms.append((name,smoke))
            try:
                setup=smoke.setup();directory,proof,roles=scenario(smoke,observed)
                environment=target_environment(smoke,proof)
                call=(lambda:observed_navigate(smoke,proof,directory)) if observed else (lambda:smoke.navigate(proof,directory,'text-fixture'))
                result=navigation_result(smoke,call,name)
                result.update(name=name,setup=setup,role_processes=roles,environment=environment,
                              role_lifecycle=role_lifecycle(smoke,roles),terminal_fixture_lifetime_seconds=180 if observed else 60,
                              observation='AT-SPI/native Wayland logging' if observed else 'unchanged frozen navigate/keys; no entry instrumentation')
                if observed:
                    result['physical']=physical(smoke,proof,directory,result)
                results.append(result)
            finally:
                cleanup=smoke.cleanup()
                require(not (smoke.root/'pcmanfm-wayland-error.json').exists(),'bounded Wayland output/child lifecycle failed')
                write_arm_report(smoke,name,cleanup)
                copy_evidence(smoke,aggregate,name)
                require_complete_trace(smoke)
            strict_security(security.state())
        for name,warmup in (('gtk-warmup',True),('gtk-no-warmup',False)):
            smoke=N.Smoke(prefix,'live');arms.append((name,smoke))
            try:
                smoke.setup();result=gtk_control(smoke,warmup);result['name']=name;results.append(result)
            finally:
                cleanup=smoke.cleanup()
                require(not (smoke.root/'gtk-control-error.json').exists(),'Gtk3 event log failed')
                write_arm_report(smoke,name,cleanup)
                copy_evidence(smoke,aggregate,name)
                require_complete_trace(smoke)
            strict_security(security.state())
        # Deliberately after every input arm; no decoder/library prewarming of the original route.
        codec=codec_diagnostic(prefix,aggregate)
    except BaseException as exc:
        errors.append(type(exc).__name__+': '+str(exc));traceback.print_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        for name,smoke in arms:
            try:
                cleanup=smoke.cleanup()
                write_arm_report(smoke,name,cleanup,phase='final-cleanup-preservation')
                copy_evidence(smoke,aggregate,name)
                require_complete_trace(smoke)
            except BaseException as exc:errors.append('cleanup/preservation '+name+': '+str(exc))
        try:
            security_value=security.finish();strict_security(security_value)
        except BaseException as exc:security_value=dict(error=str(exc));errors.append('security: '+str(exc))
        try: journals=bounded_journals(prefix,aggregate)
        except BaseException as exc:errors.append('bounded journals: '+str(exc))
    return dict(schema='arctic-pcmanfm-diagnostic-v1',status='diagnostic-collected' if not errors else 'failed',
                release_acceptance=False,original_run=37535425230,original_status='failed-7-of-8-live',
                arms=results,errors=errors,security=security_value,codec=locals().get('codec'),journals=locals().get('journals'),
                installed_checks='unrun; diagnostic never installs',
                evidence_root=str(aggregate),remaining=['actual reviewed VM evidence','PCManFM activation/IM internals remain unobserved',
                    'any repair needs independent review and full same-image qualification'])


def export(root):
    entries=[];encoded=[];total=0
    for path in sorted(root.rglob('*')):
        require(not path.is_symlink(),'diagnostic evidence symlink refused')
        if not path.is_file():continue
        require(path.suffix.lower() in ('.json','.png','.log','.txt','.tsv') and len(entries)<128
                and path.stat().st_size<=MAX_FILE,'diagnostic export type/count/file bound failed')
        data=path.read_bytes();total+=len(data);require(total<=MAX_TOTAL,'diagnostic total evidence bound exceeded')
        compressed=zlib.compress(data,9);chunks=[compressed[i:i+24576] for i in range(0,len(compressed),24576)]
        entry=dict(path=path.relative_to(root).as_posix(),bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                   compressed_bytes=len(compressed),chunks=len(chunks),encoding='zlib+base64')
        entries.append(entry);encoded.append((entry,chunks))
    for entry,chunks in encoded:
        for index,chunk in enumerate(chunks):
            print('ARCTIC-NATIVE-EVIDENCE-CHUNK '+json.dumps(dict(path=entry['path'],index=index,data=base64.b64encode(chunk).decode()),sort_keys=True),flush=True)
    print('ARCTIC-NATIVE-EVIDENCE-MANIFEST '+json.dumps(dict(schema='arctic-native-evidence-v1',stage='live',
          files=entries,bytes=total,evidence_root=str(root)),sort_keys=True),flush=True)


def main():
    error=None;report=None;aggregate=None;export_complete=False
    begin=dict(schema='arctic-pcmanfm-diagnostic-begin-v1',checker_sha256=N.digest(Path(__file__)),
               native_source_sha256=NATIVE_SHA,release_acceptance=False)
    print('ARCTIC-PCMANFM-DIAG-BEGIN '+json.dumps(begin,sort_keys=True),flush=True)
    try:
        require(Path(__file__).resolve()==Path('/run/t/guest-check.py') and len(sys.argv)==1,
                'requires exact reviewed read-only guest-check location and no arguments')
        N.guest_guard('live',True)
        runtime=json.loads((HERE/'runtime-pins.json').read_text())
        require(set(runtime)=={'guest-check.py','native_smoke.py','native-launcher.py','atspi-snapshot.py','gtk-entry-control.py','bounded-launch.py',
                              'bootstrap-diagnostic.sh','run.sh','original-h264-aac-1s.mp4','codec-fixture-manifest.json'},
                'runtime file set differs')
        for name,digest in runtime.items():require(N.digest(HERE/name)==digest,'runtime dependency hash differs: '+name)
        launcher=load('owned_native_launcher',HERE/'native-launcher.py',LAUNCHER_SHA)
        launch=launcher.verify_barrier('live',LAUNCHER_SHA)
        prefix=N.discover_desktop();uid=pwd.getpwnam(prefix[2]).pw_uid
        require(launch['foot']['uid']==uid,'launcher/desktop UID mismatch')
        aggregate=Path(tempfile.mkdtemp(prefix='arctic-pcmanfm-diagnostic-',dir='/tmp'));os.chown(aggregate,uid,pwd.getpwnam(prefix[2]).pw_gid)
        begin.update(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),desktop_uid=uid,
                     cmdline=Path('/proc/cmdline').read_text().strip(),launcher=launch,runtime_pins=runtime)
        (aggregate/'provenance.json').write_text(json.dumps(begin,indent=2)+'\n')
        signal.signal(signal.SIGALRM,lambda *_: (_ for _ in ()).throw(TimeoutError('guest 600-second diagnostic deadline')))
        signal.setitimer(signal.ITIMER_REAL,600)
        report=run_diagnosis(prefix,aggregate)
        (aggregate/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print('ARCTIC-PCMANFM-DIAG-REPORT '+json.dumps(report,sort_keys=True),flush=True)
        require(report['status']=='diagnostic-collected','diagnostic collector/security/cleanup failed')
    except BaseException as exc:
        error=type(exc).__name__+': '+str(exc);traceback.print_exc()
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)
        try:
            if aggregate is not None:export(aggregate);export_complete=True
        except BaseException as exc:error=(error+'; ' if error else '')+'export: '+str(exc);traceback.print_exc()
        print('ARCTIC-PCMANFM-DIAG-END '+json.dumps(dict(status='diagnostic-collected' if error is None and export_complete else 'failed',
              error=error,evidence_export_complete=export_complete,release_acceptance=False),sort_keys=True),flush=True)
    return 0 if error is None and export_complete else 1


if __name__=='__main__':
    raise SystemExit(main())
