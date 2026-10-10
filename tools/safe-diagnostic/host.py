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
import subprocess
import sys
import time
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common as c


def record(path, value):
    path.write_text(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')


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
            self.close(); raise

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
        if self.proc is not None and self.proc.poll() is None:
            os.killpg(self.proc.pid, signal.SIGTERM)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(self.proc.pid, signal.SIGKILL); self.proc.wait(timeout=5)
        if self.f is not None:
            self.f.close()
        if self.s is not None:
            self.s.close()
        self.log.close()


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


def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(); out=args.out
    def interrupted(signum, frame):
        raise RuntimeError('Bounded diagnostic interrupted')
    signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
    c.require(os.geteuid()==0 and Path('/dev/kvm').is_char_device() and out.is_dir() and not out.is_symlink(),
              'Requires owned disposable root KVM container')
    ctx=c.context(c.strict((out/'data/context.json').read_bytes()))
    c.require(Path('/iso').stat().st_size==c.IMAGE['bytes'] and c.sha('/iso')==c.IMAGE['sha256'], 'Exact image differs at VM handoff')
    sys.path.insert(0, '/execution/tools/lib')
    import vmtest
    import iso_startup as startup
    state=dict(schema='arctic-safe-host-observation-v1', context=ctx, status='failed_or_unrun',
               release_acceptance=False,image_qualified=False,performance_acceptance=False,observer_profile_admitted=False,
               baseline=[],brackets=[],interventions=[],
               fixture_differences=['One additional root-owned read-only test CD and duplex virtio evidence channel.',
                   'Baseline original captures are after exact Safe menu selection, before any VT/terminal interaction.'])
    vm=None; port=None
    try:
        shutil.copyfile('/usr/share/edk2/ovmf/OVMF_VARS.fd',out/'OVMF_VARS.fd')
        subprocess.run(['qemu-img','create','-q','-f','qcow2',str(out/'target.qcow2'),'64G'],check=True,timeout=30)
        argv=['qemu-system-x86_64','-machine','q35','-accel','kvm','-cpu','max','-smp','4','-m','4096',
              '-display','none','-vga','virtio','-qmp','unix:'+str(out/'qmp.sock')+',server=on,wait=off',
              '-serial','file:'+str(out/'serial.log'),'-monitor','none','-no-reboot',
              '-drive','file=/iso,media=cdrom,readonly=on,if=none,id=cd', '-device','ide-cd,drive=cd,bootindex=0',
              '-drive','file='+str(out/'data.iso')+',media=cdrom,readonly=on,if=none,id=data','-device','ide-cd,drive=data',
              '-drive','file='+str(out/'target.qcow2')+',if=none,id=disk','-device','virtio-blk-pci,drive=disk,bootindex=1',
              '-netdev','user,id=net0,restrict=on','-device','virtio-net-pci,netdev=net0','-device','qemu-xhci','-device','usb-tablet','-rtc','base=utc',
              '-drive','if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd',
              '-drive','if=pflash,format=raw,unit=1,file='+str(out/'OVMF_VARS.fd'),
              '-chardev','socket,id=evidence,path='+str(out/'evidence.sock')+',server=on,wait=off',
              '-device','virtio-serial-pci','-device','virtserialport,chardev=evidence,name=arctic-safe-evidence']
        state['qemu_argv']=argv; state['data_cd']=dict(bytes=(out/'data.iso').stat().st_size,sha256=c.sha(out/'data.iso'))
        state['qemu_binary_sha256']=c.sha('/usr/bin/qemu-system-x86_64')
        vm=OwnedVM(argv,out/'qmp.sock',out); port=connect_port(out/'evidence.sock')
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
        vm.type_text('sudo sh /dev/sr1 '+ctx['binding_id']); vm.keys('ret')
        channel=c.Channel(port.fileno(),ctx['binding_id'])
        hello=channel.expect('HELLO',timeout=60)
        c.require(set(hello)=={'context','guest_ns','output'} and hello['context']==ctx
                  and type(hello['guest_ns']) is int and type(hello['output']) is str,'Authenticated guest hello differs')
        state['hello']=hello; channel.send('HELLO-ACK',dict(execution_sha=ctx['execution_sha']))
        for label in c.PAIRS:
            request=channel.expect('CAPTURE-REQUEST',timeout=60)
            c.require(set(request)=={'label','guest_ns'} and request['label']==label and type(request['guest_ns']) is int,
                      'Capture request order differs')
            before_ns=time.monotonic_ns(); before=proof(vm.shot(label+'-qmp-before'))
            channel.send('QMP-BEFORE',dict(label=label,host_ns=before_ns))
            done=channel.expect('CAPTURE-DONE',timeout=25)
            c.require(set(done)=={'label','guest_ns'} and done['label']==label and type(done['guest_ns']) is int,
                      'Capture completion identity differs')
            after_start_ns=time.monotonic_ns(); after=proof(vm.shot(label+'-qmp-after')); after_ns=time.monotonic_ns()
            c.require(after_ns-before_ns<25*1000000000 and (before['width'],before['height'])==(1920,1080)
                      and (after['width'],after['height'])==(1920,1080),'Readback bracket time or geometry differs')
            channel.send('QMP-AFTER',dict(label=label,host_ns=after_ns))
            state['brackets'].append(dict(label=label,guest_request=request,guest_done=done,
                     host_before_ns=before_ns,host_after_start_ns=after_start_ns,host_after_ns=after_ns,before=before,after=after))
        state['guest_inventory']=c.receive_files(channel,out)
        report=c.strict((out/'guest-report.json').read_bytes()); c.require(report['context']==ctx,'Returned guest context differs')
        for bracket,sample in zip(state['brackets'],report['samples']):
            c.require(sample['label']==bracket['label'] and sample['request_ns']==bracket['guest_request']['guest_ns']
                      and sample['capture_end_ns']==bracket['guest_done']['guest_ns']
                      and sample['qmp_before_ack']==dict(label=bracket['label'],host_ns=bracket['host_before_ns'])
                      and sample['qmp_after_ack']==dict(label=bracket['label'],host_ns=bracket['host_after_ns']),
                      'Dual path causal timing binding differs')
        state['derived_readbacks']=validate_readbacks(out,report)
        channel.send('RECEIVED',dict(files=len(c.GUEST_FILES)))
        state['transport']=dict(original_member_inventory=state['guest_inventory'],
                  wire_read_bytes=channel.read_bytes,wire_read_sha256=channel.read_sha256.hexdigest(),
                  wire_write_bytes=channel.write_bytes,
                  policy='Decoded original guest members are retained byte-exact; encoded transport is hashed, not duplicated.')
        state['status']='DIAGNOSTIC_CAPTURED_UNQUALIFIED'
        state['limitations']=['No rendering acceptance or cause inference; visual independent review is required.',
                'VT restore and screencopy are interventions; only the initial three baseline QMP captures precede them.',
                'Host/guest monotonic clocks are separate; compare protocol order, not absolute clock values.']
    finally:
        if vm is not None: vm.close()
        if port is not None: port.close()
        for name in ('qmp.sock','evidence.sock','target.qcow2','OVMF_VARS.fd'):
            path=out/name
            if path.exists(): path.unlink()
        record(out/'host-report.json',state)


if __name__=='__main__':
    main()
