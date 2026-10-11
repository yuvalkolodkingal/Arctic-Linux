#!/usr/bin/env python3
"""One exact-image Safe VM; QMP baseline precedes all desktop interventions."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c


def record(path, value):
    c.exclusive_json(path, value)


class OwnedTemporaries:
    """Retain acquired inode identities; names never confer ownership."""
    def __init__(self, out):
        self.directory=os.open(out,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        self.files={}

    def create(self, name):
        fd=os.open(name,os.O_RDWR|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o644,
                   dir_fd=self.directory)
        self.files[name]=(fd,os.fstat(fd))
        return fd

    def socket(self, name):
        fd=os.open(name,os.O_PATH|os.O_NOFOLLOW,dir_fd=self.directory)
        info=os.fstat(fd)
        if not stat.S_ISSOCK(info.st_mode) or info.st_uid!=os.geteuid():
            os.close(fd);raise RuntimeError('Owned VM socket identity differs')
        self.files[name]=(fd,info)

    def verify(self, name):
        _,owned=self.files[name]
        current=os.stat(name,dir_fd=self.directory,follow_symlinks=False)
        c.require((current.st_dev,current.st_ino,current.st_uid,stat.S_IFMT(current.st_mode))==
                  (owned.st_dev,owned.st_ino,owned.st_uid,stat.S_IFMT(owned.st_mode)),
                  'Owned temporary inode differs')

    def close(self, *, sockets_reaped=False):
        c.require(type(sockets_reaped) is bool,'Owned socket reap proof differs')
        error=None
        for name,(fd,owned) in sorted(self.files.items()):
            fd_owned=False
            try:
                retained=os.fstat(fd)
                c.require((retained.st_dev,retained.st_ino,retained.st_uid,stat.S_IFMT(retained.st_mode))==
                          (owned.st_dev,owned.st_ino,owned.st_uid,stat.S_IFMT(owned.st_mode)),
                          'Owned retained temporary inode differs')
                fd_owned=True
                try:
                    self.verify(name)
                except FileNotFoundError:
                    # QEMU unlinks acquired listening AF_UNIX endpoints on exit.
                    # Admit only exact retained owned SOCK inodes after its child
                    # has been reaped; missing files and every present replacement
                    # remain failures. Names alone never confer ownership.
                    if not (sockets_reaped and stat.S_ISSOCK(owned.st_mode)
                            and owned.st_uid==os.geteuid()):raise
                else:
                    os.unlink(name,dir_fd=self.directory)
            except BaseException as failure:
                error=failure if error is None else error
            finally:
                if fd_owned:
                    try:os.close(fd)
                    except BaseException as failure:error=failure if error is None else error
        try:os.close(self.directory)
        except BaseException as failure:error=failure if error is None else error
        if error is not None:raise error


def proof(path):
    c.regular(path)
    with Image.open(path) as image:
        image.load()
        c.require(image.format == 'PNG', 'QMP original capture is not PNG')
        geometry = dict(width=image.width, height=image.height)
    return dict(path=path.name, bytes=path.stat().st_size, sha256=c.sha(path), **geometry)


class OwnedVM:
    """Acquire one QEMU child, bounded QMP commands and immediate owned cleanup."""
    def __init__(self, argv, qmp, out):
        self.out, self.proc, self.s, self.f = out, None, None, None
        self.reaped = False
        self.log = (out / 'qemu.log').open('xb')
        try:
            self.proc = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=self.log,
                                         stderr=subprocess.STDOUT, start_new_session=True)
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                c.require(self.proc.poll() is None, 'Owned QEMU exited before QMP acquisition')
                candidate = socket.socket(socket.AF_UNIX)
                candidate.settimeout(10)
                try:
                    candidate.connect(str(qmp)); self.s = candidate; break
                except OSError:
                    candidate.close(); time.sleep(.1)
            c.require(self.s is not None, 'QMP acquisition deadline')
            self.f = self.s.makefile('rwb')
            c.strict(self.f.readline(65537))
            self.cmd('qmp_capabilities')
        except BaseException:
            try:self.close()
            except BaseException:pass
            # An existing constructor failure remains primary even when its
            # attempted owned cleanup also fails. Execution still fails closed.
            raise

    def cmd(self, name, **arguments):
        self.f.write((json.dumps(dict(execute=name, arguments=arguments))+'\n').encode()); self.f.flush()
        deadline = time.monotonic()+10
        while time.monotonic() < deadline:
            line = self.f.readline(65537)
            c.require(line and len(line) <= 65536, 'QMP closed or exceeded bound')
            answer = c.strict(line)
            c.require('error' not in answer, 'Owned QMP command failed')
            if 'return' in answer:
                return answer
        raise RuntimeError('QMP command deadline')

    def shot(self, name):
        path = self.out / (name+'.png')
        # The sole menu probe is explicitly temporary; final captures are exclusive.
        c.require(not path.exists(), 'Refusing to replace an original QMP capture')
        self.cmd('screendump', filename=str(path), format='png')
        return path

    def press(self, chord):
        events = [dict(type='key', data=dict(down=True, key=dict(type='qcode', data=x))) for x in chord]
        events += [dict(type='key', data=dict(down=False, key=dict(type='qcode', data=x))) for x in reversed(chord)]
        self.cmd('input-send-event', events=events)

    def keys(self, *names, gap=.15):
        for name in names:
            self.press(name.split('-') if len(name)>1 and '-' in name else [name]); time.sleep(gap)

    def type_text(self, text, gap=.05):
        import vmtest
        for char in text:
            self.press(vmtest.chord_for(char)); time.sleep(gap)

    def close(self):
        error=None
        try:
            if self.proc is not None and self.proc.poll() is None:
                os.killpg(self.proc.pid, signal.SIGTERM)
                try:
                    self.proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(self.proc.pid, signal.SIGKILL); self.proc.wait(timeout=5)
            if self.proc is not None:
                self.proc.wait(timeout=5)
                self.reaped = self.proc.returncode is not None
        except BaseException as failure:error=failure
        for resource in (self.f,self.s,self.log):
            if resource is not None:
                try:resource.close()
                except BaseException as failure:error=failure if error is None else error
        if error is not None:raise error


def connect_port(path):
    deadline = time.monotonic()+20
    while time.monotonic() < deadline:
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.connect(str(path)); sock.setblocking(False); return sock
        except OSError:
            sock.close(); time.sleep(.1)
    raise RuntimeError('Owned evidence socket acquisition deadline')


def validate_readbacks(out, report):
    c.require(type(report) is dict and report.get('schema') == 'arctic-safe-guest-observation-v1'
              and all(report.get(k) is False for k in ('release_acceptance','image_qualified',
                       'performance_acceptance','observer_profile_admitted'))
              and report.get('selinux_before') == report.get('selinux_after') == 'Enforcing'
              and [v['label'] for v in report['samples']] == list(c.PAIRS), 'Guest report scope differs')
    derived = []
    for sample in report['samples']:
        label, descriptor = sample['label'], sample['descriptor']
        base = label+'-wayland.rgb'
        c.require(type(descriptor) is dict and set(descriptor) == {'schema','format','width','height','stride','flags',
                  'raw_bytes','selected_output','output_x','output_y','output_transform','output_width','output_height',
                  'output_refresh_mhz','output_scale','outputs_seen'}
                  and descriptor['schema']=='arctic-safe-screencopy-v1'
                  and all(type(descriptor[k]) is int for k in set(descriptor)-{'schema','selected_output'})
                  and type(descriptor['selected_output']) is str
                  and c.strict((out/(base+'.json')).read_bytes()) == descriptor
                  and descriptor['width'] == descriptor['output_width'] == 1920
                  and descriptor['height'] == descriptor['output_height'] == 1080
                  and descriptor['output_transform'] == 0 and descriptor['output_scale'] == 1
                  and descriptor['outputs_seen'] == 1
                  and descriptor['stride'] >= 1920*4 and descriptor['flags'] in (0,1)
                  and descriptor['format'] in (0,1,0x34324258,0x34324241), 'Raw readback descriptor differs')
        for name, pin in sample['files'].items():
            c.require(name in c.GUEST_FILES and name.startswith(label+'-wayland')
                      and (out/name).stat().st_size == pin['bytes'] and c.sha(out/name) == pin['sha256'],
                      'Guest sample original member hash differs')
        raw = (out/(base+'.shm.rgb')).read_bytes()
        ppm = (out/base).read_bytes()
        header = b'P6\n1920 1080\n255\n'
        c.require(len(raw) == descriptor['raw_bytes'] == descriptor['stride']*1080
                  and ppm.startswith(header) and len(ppm) == len(header)+1920*1080*3,
                  'Original raw stride buffer or packed RGB length differs')
        # Independently reconstruct RGB from the exact stride buffer, flags, format.
        image = Image.frombytes('RGBA', (1920,1080), raw, 'raw',
                 'BGRA' if descriptor['format'] in (0,1) else 'RGBA', descriptor['stride'], 1)
        if descriptor['flags'] & 1:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        image = image.convert('RGB')
        c.require(image.tobytes() == ppm[len(header):], 'Raw-to-RGB channel/orientation derivation differs')
        target = out/(label+'-wayland-derived.png')
        c.require(not target.exists(), 'Derived PNG already exists')
        image.save(target, format='PNG')
        derived.append(dict(**proof(target), derived=True, raw_stride_path=base+'.shm.rgb',
                       original_rgb_path=base, operation='lossless channel packing; y-invert only from protocol flags; no resize',
                       pixel_sha256=hashlib.sha256(image.tobytes()).hexdigest()))
    return derived


def validate_arm_ready(ready,arm,hello,previous):
    original=hello['original']
    c.require(arm in c.ARMS and type(ready) is dict and
              set(ready)=={'arm','guest_ns','mango','renderer_environment','output','session_handoff','session','display_binding','renderer_debug','readonly_drm'}
              and ready['arm']==arm and type(ready['guest_ns']) is int and ready['output']==hello['output'],
              'Restart arm identity/order differs')
    expected=dict(original['renderer_environment'])
    if arm=='legacy-restart':expected.update(WLR_DRM_NO_ATOMIC='1')
    c.require(ready['renderer_environment']==expected and type(ready['mango']) is dict
              and set(ready['mango'])=={'pid','start_ticks','executable','sha256'}
              and all(type(ready['mango'][k]) is int for k in ('pid','start_ticks'))
              and ready['mango']['pid']>1 and ready['mango']['start_ticks']>previous['start_ticks']
              and ready['mango']['executable']==previous['executable']=='/usr/bin/mango'
              and ready['mango']['sha256']==previous['sha256'],
              'New attested arm compositor differs')
    c.validate_display_binding(ready['display_binding'],ready['mango'])
    c.validate_renderer_debug(ready['renderer_debug'],ready['mango'])
    c.drm_validate_snapshot(ready['readonly_drm'],ready['mango'])
    session=ready['session']
    c.require(type(session) is dict and set(session)=={'id','uid','type','vt','active','prefix_bound'}
              and type(session['id']) is str and __import__('re').fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,63}',session['id'])
              and type(session['uid']) is int and session['uid']==1000 and session['type']=='wayland'
              and type(session['vt']) is int and 1<=session['vt']<=99
              and session['active'] is True and session['prefix_bound'] is True,
              'New attested arm login session differs')
    handoff=ready['session_handoff']
    c.require(type(handoff) is dict and set(handoff)=={'arm','wrapper','configuration','original_script','security_labels','selector'}
              and handoff['arm']==arm and handoff['selector']==('unset' if arm=='default-restart' else 'legacy-drm-only'),
              'Owned session handoff fields differ')
    for key in ('wrapper','configuration','original_script'):
        value=handoff[key]
        c.require(type(value) is dict and set(value)=={'bytes','sha256','mode','uid'}
                  and type(value['bytes']) is int and 0<value['bytes']<=c.MAX_FILE
                  and type(value['mode']) is int and type(value['uid']) is int and value['uid']==0
                  and type(value['sha256']) is str and __import__('re').fullmatch('[0-9a-f]{64}',value['sha256']),
                  'Owned session file record differs')
    c.require(handoff['wrapper']['mode']==0o755 and handoff['configuration']['mode']==0o644
              and not handoff['original_script']['mode'] & 0o022
              and handoff['original_script']['mode'] & 0o005==0o005,'Trusted session execution mode differs')
    labels=handoff['security_labels']
    c.require(type(labels) is dict and set(labels)=={'script','configuration'}
              and type(labels['script']) is dict and set(labels['script'])=={'policy_expected','observed','reference','action'}
              and type(labels['configuration']) is dict and set(labels['configuration'])=={'policy_expected','observed'},
              'Owned SELinux label fields differ')
    for record in labels.values():
        for key,value in record.items():
            if key!='action':c.require(type(value) is str and __import__('re').fullmatch('[A-Za-z0-9_:.,-]{1,160}',value)
                and len(value.split(':'))>=4,'Known SELinux label syntax required')
    c.require(labels['script']['observed']==labels['script']['reference']
              and labels['script']['action'] in ('ordinary-policy-restore','owned-trusted-script-reference')
              and (labels['script']['action']!='ordinary-policy-restore'
                   or labels['script']['policy_expected']==labels['script']['observed'])
              and labels['configuration']['policy_expected']==labels['configuration']['observed'],
              'Observed trusted-script label handoff differs')
    return ready


def observe_arm(vm,channel,out,ctx,hello,previous,arm,state):
    ready=channel.expect('ARM-READY',timeout=150)
    validate_arm_ready(ready,arm,hello,previous)
    arm_out=out/arm;arm_out.mkdir(mode=0o755)
    ready_host_ns=time.monotonic_ns()
    entry=dict(arm=arm,context=ctx,ready=ready,scene_ready_host_ns=ready_host_ns,baseline=[],brackets=[],
               release_acceptance=False,image_qualified=False,performance_acceptance=False,
               observer_profile_admitted=False,
               time_origin='first attested new-scene-ready acknowledgement; exact scene creation unmeasured')
    state['arms'].append(entry)
    for seconds in (35,80,125):
        while time.monotonic_ns()<ready_host_ns+seconds*1000000000:
            c.require(vm.proc.poll() is None,'VM exited during unobstructed arm baseline');time.sleep(.1)
        before=time.monotonic_ns();path=vm.shot(arm+'/arm-baseline-%03ds'%seconds);after=time.monotonic_ns()
        frame=proof(path);c.require((frame['width'],frame['height'])==(1920,1080),'Original arm geometry differs')
        entry['baseline'].append(dict(requested_seconds=seconds,host_before_ns=before,host_after_ns=after,**frame))
    channel.send('ARM-BASELINE-DONE',dict(arm=arm,frames=3))
    for label in c.PAIRS:
        request=channel.expect('CAPTURE-REQUEST',timeout=60)
        c.require(set(request)=={'label','guest_ns'} and request['label']==label and type(request['guest_ns']) is int,
                  'Capture request order differs')
        before_ns=time.monotonic_ns(); before=proof(vm.shot(arm+'/'+label+'-qmp-before'))
        channel.send('QMP-BEFORE',dict(label=label,host_ns=before_ns))
        done=channel.expect('CAPTURE-DONE',timeout=25)
        c.require(set(done)=={'label','guest_ns'} and done['label']==label and type(done['guest_ns']) is int,
                  'Capture completion identity differs')
        after_start_ns=time.monotonic_ns(); after=proof(vm.shot(arm+'/'+label+'-qmp-after')); after_ns=time.monotonic_ns()
        c.require(after_ns-before_ns<25*1000000000 and (before['width'],before['height'])==(1920,1080)
                  and (after['width'],after['height'])==(1920,1080),'Readback bracket time or geometry differs')
        channel.send('QMP-AFTER',dict(label=label,host_ns=after_ns))
        entry['brackets'].append(dict(label=label,guest_request=request,guest_done=done,
                 host_before_ns=before_ns,host_after_start_ns=after_start_ns,host_after_ns=after_ns,before=before,after=after))
    entry['guest_inventory']=c.receive_files(channel,arm_out)
    report=c.strict((arm_out/'guest-report.json').read_bytes()); c.require(report['context']==ctx and report['arm']==arm and report['mango']==ready['mango'] and report['renderer_environment']==ready['renderer_environment'] and report['session']==ready['session'] and report['display_binding']==ready['display_binding'] and report['renderer_debug']==ready['renderer_debug'] and report['readonly_drm']==ready['readonly_drm'],'Returned guest context differs')
    for bracket,sample in zip(entry['brackets'],report['samples']):
        c.require(sample['label']==bracket['label'] and sample['request_ns']==bracket['guest_request']['guest_ns']
                  and sample['capture_end_ns']==bracket['guest_done']['guest_ns']
                  and sample['qmp_before_ack']==dict(label=bracket['label'],host_ns=bracket['host_before_ns'])
                  and sample['qmp_after_ack']==dict(label=bracket['label'],host_ns=bracket['host_after_ns']),
                  'Dual path causal timing binding differs')
    entry['derived_readbacks']=validate_readbacks(arm_out,report)
    channel.send('RECEIVED',dict(files=len(c.GUEST_FILES),arm=arm))
    record(arm_out/'arm-host-report.json',entry)
    return ready['mango']


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); out=args.out
    def interrupted(signum, frame):
        raise RuntimeError('Bounded diagnostic interrupted')
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    state=dict(schema='arctic-safe-host-observation-v1', context=None, status='failed_or_unrun',
               release_acceptance=False,image_qualified=False,performance_acceptance=False,observer_profile_admitted=False,
               baseline=[],brackets=[],arms=[],interventions=[],
               fixture_differences=['One additional root-owned read-only test CD and duplex virtio evidence channel.',
                   'Baseline original captures are after exact Safe menu selection, before any VT/terminal interaction.'])
    phase='entry'
    vm=None; port=None; owned_temporaries=None
    try:
        phase='root-kvm'
        c.require(os.geteuid()==0 and Path('/dev/kvm').is_char_device() and out.is_dir() and not out.is_symlink(),
                  'Requires owned disposable root KVM container')
        phase='context'
        ctx=c.context(c.strict((out/'data/context.json').read_bytes()))
        state['context']=ctx
        phase='image'
        c.require(Path('/iso').stat().st_size==c.IMAGE['bytes'] and c.sha('/iso')==c.IMAGE['sha256'], 'Exact image differs at VM handoff')
        phase='libraries'
        sys.path.insert(0, '/execution/tools/lib')
        import vmtest
        import iso_startup as startup
        phase='vm-capture'
        for name in ('qmp.sock','evidence.sock','target.qcow2','OVMF_VARS.fd'):
            c.require(not (out/name).exists() and not (out/name).is_symlink(),
                      'Owned VM temporary must be new')
        owned_temporaries=OwnedTemporaries(out)
        firmware=owned_temporaries.create('OVMF_VARS.fd')
        with open('/usr/share/edk2/ovmf/OVMF_VARS.fd','rb') as source:
            with os.fdopen(os.dup(firmware),'wb') as destination:
                shutil.copyfileobj(source,destination)
        disk=owned_temporaries.create('target.qcow2')
        subprocess.run(['qemu-img','create','-q','-f','qcow2','/proc/self/fd/'+str(disk),'64G'],
                       pass_fds=(disk,),check=True,timeout=30)
        owned_temporaries.verify('OVMF_VARS.fd');owned_temporaries.verify('target.qcow2')
        argv=['qemu-system-x86_64','-machine','q35','-accel','kvm','-cpu','max','-smp','4','-m','4096',
              '-display','none','-vga','virtio','-qmp','unix:'+str(out/'qmp.sock')+',server=on,wait=off',
              '-serial','file:'+str(out/'serial.log'),'-monitor','none','-no-reboot',
              '-drive','file=/iso,media=cdrom,readonly=on,if=none,id=cd', '-device','ide-cd,drive=cd,bootindex=0',
              '-drive','file='+str(out/'data.iso')+',media=cdrom,readonly=on,if=none,id=data','-device','ide-cd,drive=data,bus=ide.1',
              '-drive','file='+str(out/'target.qcow2')+',if=none,id=disk','-device','virtio-blk-pci,drive=disk,bootindex=1',
              '-netdev','user,id=net0,restrict=on','-device','virtio-net-pci,netdev=net0','-device','qemu-xhci','-device','usb-tablet','-rtc','base=utc',
              '-drive','if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd',
              '-drive','if=pflash,format=raw,unit=1,file='+str(out/'OVMF_VARS.fd'),
              '-chardev','socket,id=evidence,path='+str(out/'evidence.sock')+',server=on,wait=off',
              '-device','virtio-serial-pci','-device','virtserialport,chardev=evidence,name=arctic-safe-evidence']
        state['qemu_argv']=argv; state['data_cd']=dict(bytes=(out/'data.iso').stat().st_size,sha256=c.sha(out/'data.iso'))
        state['qemu_binary_sha256']=c.sha('/usr/bin/qemu-system-x86_64')
        vm=OwnedVM(argv,out/'qmp.sock',out)
        owned_temporaries.socket('qmp.sock');owned_temporaries.socket('evidence.sock')
        port=connect_port(out/'evidence.sock')
        deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            probe=vm.shot('menu-probe')
            if vmtest.looks_like_boot_menu(probe):
                os.rename(probe,out/'boot-menu.png'); break
            probe.unlink(); time.sleep(.5)
        else:
            raise RuntimeError('Actual Safe menu not observed')
        vm.keys('home','down','down'); vm.shot('safe-menu-selected'); vm.keys('ret')
        boot_ns=time.monotonic_ns(); state['safe_menu_boot_ns']=boot_ns
        for seconds in (35,80,125):
            while time.monotonic_ns()<boot_ns+seconds*1000000000:
                c.require(vm.proc.poll() is None,'VM exited during unperturbed baseline'); time.sleep(.1)
            before=time.monotonic_ns(); path=vm.shot('baseline-%03ds'%seconds); after=time.monotonic_ns()
            frame=proof(path); c.require((frame['width'],frame['height'])==(1920,1080),'Original Safe geometry differs')
            state['baseline'].append(dict(requested_seconds=seconds,host_before_ns=before,host_after_ns=after,**frame))
        state['interventions'].append(dict(kind='VT6-login-and-readonly-CD-setup',host_ns=time.monotonic_ns()))
        vm.cmd('send-key',keys=[dict(type='qcode',data=x) for x in ('ctrl','alt','f6')],**{'hold-time':100})
        time.sleep(4)
        c.require(startup.console_screen(vm.shot('console-login')),'Refused unauthenticated graphical shell input')
        vm.type_text('liveuser',gap=.15); vm.keys('ret'); time.sleep(3); vm.keys('ret'); time.sleep(3)
        vm.type_text(startup.console_auth_command(ctx['binding_id'])); vm.keys('ret')
        deadline=time.monotonic()+30
        while time.monotonic()<deadline and not startup.console_authenticated(out/'serial.log',ctx['binding_id']):
            time.sleep(.5)
        c.require(startup.console_authenticated(out/'serial.log',ctx['binding_id']),'Actual live console authentication failed')
        c.require(('user=liveuser uid=1000').encode() in (out/'serial.log').read_bytes(),'Exact live UID differs')
        state['console_authentication']=dict(binding_id=ctx['binding_id'],status='unique-liveuser-uid1000')
        vm.type_text('sudo sh -c \'d=$(blkid -t LABEL=ARCTICSAFE -o device) && [ -b "$d" ] && label=$(blkid -s LABEL -o value "$d") && [ "$label" = ARCTICSAFE ] && exec sh "$d" "$1"\' sh '+ctx['binding_id']); vm.keys('ret')
        channel=c.Channel(port.fileno(),ctx['binding_id'])
        hello=channel.expect('HELLO',timeout=60)
        c.require(set(hello)=={'context','guest_ns','output','original'} and hello['context']==ctx
                  and type(hello['guest_ns']) is int and type(hello['output']) is str,'Authenticated guest hello differs')
        state['hello']=hello; channel.send('HELLO-ACK',dict(execution_sha=ctx['execution_sha']))
        original=hello['original']
        c.require(type(original) is dict and original.get('context')==ctx
                  and all(original.get(k) is False for k in ('release_acceptance','image_qualified',
                      'performance_acceptance','observer_profile_admitted'))
                  and 'WLR_SCENE_DEBUG_DAMAGE' not in original['renderer_environment']
                  and 'WLR_SCENE_DISABLE_VISIBILITY' not in original['renderer_environment']
                  and 'WLR_DRM_NO_ATOMIC' not in original['renderer_environment']
                  and 'WLR_DRM_FORCE_LIBLIFTOFF' not in original['renderer_environment'],
                  'Original guest observation scope differs')
        c.validate_display_binding(original['display_binding'],original['mango'])
        record(out/'original-guest-observation.json',original)
        previous=original['mango']
        for arm in c.ARMS:
            previous=observe_arm(vm,channel,out,ctx,hello,previous,arm,state)
        state['transport']=dict(original_member_inventories=[v['guest_inventory'] for v in state['arms']],
                  wire_read_bytes=channel.read_bytes,wire_read_sha256=channel.read_sha256.hexdigest(),
                  wire_write_bytes=channel.write_bytes,
                  policy='Decoded original guest members are retained byte-exact; encoded transport is hashed, not duplicated.')
        state['status']='DIAGNOSTIC_CAPTURED_UNQUALIFIED'
        phase='complete'
        state['limitations']=['No rendering acceptance or cause inference; visual independent review is required.',
                'Original baseline precedes VT; arm baselines follow explicit session restarts and VT activation but precede Foot/readback.',
                'Ordered arms, warm caches, minute boundaries and single-run CPU counters do not establish performance acceptance.',
                'Host/guest monotonic clocks are separate; compare protocol order, not absolute clock values.']
    finally:
        primary=sys.exc_info()[1]
        errors=[]
        def cleanup(name, action):
            try: action()
            except BaseException as error:
                errors.append(dict(stage=name,exception_class=c.exception_class(error)))
        if vm is not None: cleanup('vm-close',vm.close)
        if port is not None: cleanup('port-close',port.close)
        if owned_temporaries is not None: cleanup('temporary-cleanup',lambda:owned_temporaries.close(sockets_reaped=vm is not None and vm.reaped))
        if primary is not None:
            state['diagnostic_failure']=dict(stage=phase,exception_class=c.exception_class(primary))
        state['cleanup_errors']=errors
        cleanup('host-report',lambda:record(out/'host-report.json',state))
        status=c.fixed_status(phase,'exception' if primary else 'cleanup-exception' if errors else 'completed',
              None if primary or errors else 0,c.exception_class(primary) if primary else None,
              cleanup_errors=errors)
        cleanup('host-status',lambda:c.exclusive_json(out/'host-entry-status.json',status))
        # Preserve the original exception and its stage even if cleanup/reporting
        # encounters a second failure. A new cleanup failure still fails the job.
        if primary is None and errors:
            raise RuntimeError('Owned diagnostic cleanup or reporting failed')



if __name__=='__main__':
    main()
