#!/usr/bin/env python3
"""Dedicated disposable update-cycle observation; never update qualification.

Runs only inside the prepared Fedora tools container, with /out a fresh owned
VM directory. No guest command, login, service or updater policy is changed.
The transient GRUB addition only routes actual kernel/journal output to serial.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time

CONSOLE_APPEND='console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1'
PASSPHRASE='glacier lantern frost harbor'
VMTEST_SHA256='8b5136dee77373aee27ec3a695ab712b2b1997adb7fda03dfcb4371fe0414717'

def require(condition,message):
    if not condition:raise RuntimeError(message)

def validate_paths(disk,variables,out,root=Path('/out')):
    root=root.resolve()
    require(disk==root/'target.qcow2' and variables==root/'OVMF_VARS.fd'
            and out==root/'offline-update-cycle','Only the exact fresh-run disposable paths are allowed')
    for path in (root,disk,variables):
        require(not path.is_symlink(),'Linked disposable input is forbidden')
    require(root.is_dir() and disk.is_file() and variables.is_file(),'Fresh installed disk/vars are absent')
    require(not out.exists() and not out.is_symlink(),'Cycle evidence destination must be unused')

def qemu_argv(disk,variables,out,firmware,qmp):
    for path in (disk,variables,out,firmware,Path(qmp)):
        require(',' not in str(path),'Unsupported QEMU comma-containing path')
    return ['qemu-system-x86_64','-machine','q35','-accel','kvm','-cpu','max','-smp','2','-m','4096',
        '-display','none','-vga','virtio','-qmp',f'unix:{qmp},server=on,wait=off',
        '-serial',f'file:{out}/serial-offline-cycle.log','-monitor','none','-no-reboot',
        '-drive',f'file={disk},if=none,id=disk,discard=unmap','-device','virtio-blk-pci,drive=disk,bootindex=0',
        '-netdev','user,id=net0,restrict=on','-device','virtio-net-pci,netdev=net0',
        '-device','qemu-xhci','-device','usb-tablet','-rtc','base=utc',
        '-drive',f'if=pflash,format=raw,unit=0,readonly=on,file={firmware}',
        '-drive',f'if=pflash,format=raw,unit=1,file={variables}']

def observed_vm_type(vmtest):
    # A local subclass retains QMP events; no monkeypatch of the shared helper.
    class ObservedVM(vmtest.VM):
        def __init__(self,argv,qmp,name,event_log):
            self.events=[];self.event_log=event_log
            super().__init__(argv,qmp,name)
            self.s.settimeout(5)
        def capture(self,reply):
            if 'event' in reply:
                entry=dict(received_monotonic=time.monotonic(),reply=reply)
                self.events.append(entry)
                with self.event_log.open('a') as stream:stream.write(json.dumps(entry)+'\n')
        def cmd(self,name,**args):
            message={'execute':name}
            if args:message['arguments']=args
            try:
                self.f.write(json.dumps(message)+'\n');self.f.flush()
                while True:
                    line=self.f.readline()
                    if not line:raise vmtest.QMPError('QMP closed')
                    reply=json.loads(line);self.capture(reply)
                    if 'return' in reply or 'error' in reply:return reply
            except (OSError,ValueError) as error:raise vmtest.QMPError(str(error))
        def drain_events(self):
            self.s.settimeout(2)
            try:
                while line:=self.f.readline():self.capture(json.loads(line))
            except (OSError,ValueError):pass
    return ObservedVM

def validate_cycle(result):
    require(result.get('unlock_prompt_seen') is True and result.get('passphrase_submitted') is True,
            'Guest exit before verified unlock submission is not an expected cycle')
    require(result.get('guest_exited') is True and result.get('qemu_exit_code')==0
            and type(result.get('qemu_exit_code')) is int,'Clean observed QEMU guest exit is required')
    require(result.get('timed_out') is False,'Timed-out/host-stopped update cycle cannot advance')
    events=result.get('events',[])
    shutdowns=[row['reply'] for row in events if row.get('reply',{}).get('event')=='SHUTDOWN']
    require(len(shutdowns)==1 and shutdowns[0].get('data',{}).get('guest') is True
            and shutdowns[0]['data'].get('reason') in ('guest-reset','guest-shutdown'),
            'Exactly one actual guest reboot/poweroff QMP event is required; host exit/panic is not a cycle')
    require(not any(row.get('reply',{}).get('event') in ('GUEST_PANICKED','WATCHDOG') for row in events),
            'Guest panic/watchdog is not an expected offline cycle')
    return dict(status='guest_cycle_exit_observed_third_boot_required',
                guest_exit_reason=shutdowns[0]['data']['reason'],update_qualification='UNRUN until mandatory third boot')

def observe(vm,vmtest,result,timeout,clock=time.monotonic,pause=time.sleep):
    start=clock();deadline=start+timeout
    def alive():return vm.alive()
    # The actual BLS menu is required; no blind typing into an unknown screen.
    while alive() and clock()<min(deadline,start+240):
        shot=vm.shot('01-menu-probe')
        if shot and vmtest.looks_like_boot_menu(shot):break
        pause(1)
    else:raise RuntimeError('Actual installed boot menu was not observed')
    vm.shot('02-boot-menu');vm.keys('e');pause(1);vm.keys('down','down','down','ctrl-e')
    vm.type_text(' '+CONSOLE_APPEND,gap=0.1);vm.shot('03-console-only-entry');vm.keys('ctrl-x')
    while alive() and clock()<min(deadline,start+900):
        shot=vm.shot('04-unlock-probe')
        if shot and vmtest.classify(shot)=='prompt':break
        pause(5)
    else:raise RuntimeError('Actual LUKS prompt absent; no blind unlock or login fallback')
    result['unlock_prompt_seen']=True;vm.shot('05-luks-prompt')
    vm.type_text(PASSPHRASE,gap=0.3);vm.shot('06-test-passphrase-typed');vm.keys('ret')
    result['passphrase_submitted']=True
    last=-30
    while alive() and clock()<deadline:
        elapsed=clock()-start
        if elapsed-last>=30:
            vm.shot(f'10-update-cycle-{int(elapsed):04d}s');last=elapsed
            vmtest.log(f'Observing restricted offline update cycle {elapsed:.0f}s; third boot remains mandatory')
        pause(2)
    result.update(guest_exited=not alive(),timed_out=alive(),elapsed_seconds=clock()-start,
                  qemu_exit_code=vm.proc.poll())
    vm.drain_events();result['events']=list(vm.events)
    result.update(validate_cycle(result))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk',type=Path,required=True);parser.add_argument('--vars',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--timeout',type=int,default=5400)
    args=parser.parse_args()
    require(300<=args.timeout<=5400,'Cycle timeout must be 300..5400 seconds')
    validate_paths(args.disk,args.vars,args.out)
    require(Path('/dev/kvm').is_char_device(),'Native KVM is mandatory; no TCG fallback')
    firmware=Path('/usr/share/edk2/ovmf/OVMF_CODE.fd');require(firmware.is_file(),'OVMF absent')
    helper=Path('/arctic-lib/vmtest.py')
    require(hashlib.sha256(helper.read_bytes()).hexdigest()==VMTEST_SHA256,'Exact candidate VM helper changed')
    args.out.mkdir();os.environ['OUT']=str(args.out);sys.path.insert(0,'/arctic-lib')
    import vmtest
    qmp='/tmp/arctic-offline-cycle-v4-'+str(os.getpid())+'.sock'
    argv=qemu_argv(args.disk,args.vars,args.out,firmware,qmp)
    identity={str(p):(p.stat().st_dev,p.stat().st_ino) for p in (args.disk,args.vars)}
    result=dict(status='running',platform='QEMU_KVM',network='restricted_offline',actual_qemu_argv=argv,
        transient_console_append=CONSOLE_APPEND,vmtest_sha256=VMTEST_SHA256,
        firmware_sha256=hashlib.sha256(firmware.read_bytes()).hexdigest(),
        update_qualification='UNRUN: this phase only observes the guest cycle exit')
    report=args.out/'cycle-result.json';vm=None
    def save():report.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    try:
        save();VM=observed_vm_type(vmtest)
        vm=VM(argv,qmp,'offline-cycle',args.out/'qmp-events.jsonl')
        observe(vm,vmtest,result,args.timeout)
        require(identity=={str(p):(p.stat().st_dev,p.stat().st_ino) for p in (args.disk,args.vars)},
                'Disposable installed disk/vars path identity changed')
        save()
    except BaseException as error:
        result.update(status='failed_or_unrun',error=str(error))
        if vm is not None:result['events']=list(vm.events)
        save();raise
    finally:
        if vm is not None:vm.quit()

if __name__=='__main__':main()
