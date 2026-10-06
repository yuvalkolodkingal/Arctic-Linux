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
import re
import stat
import struct
import tempfile
import sys
import time

CONSOLE_APPEND='console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1'
PASSPHRASE='glacier lantern frost harbor'
VMTEST_SHA256='8b5136dee77373aee27ec3a695ab712b2b1997adb7fda03dfcb4371fe0414717'

def require(condition,message):
    if not condition:raise RuntimeError(message)

def input_identity(disk,variables):
    return {str(path):dict(device=path.stat().st_dev,inode=path.stat().st_ino,
        uid=path.stat().st_uid,gid=path.stat().st_gid,mode=stat.S_IMODE(path.stat().st_mode))
        for path in (disk,variables)}

def validate_paths(disk,variables,out,root=Path('/out'),owner=None):
    owner=owner if owner is not None else dict(uid=os.getuid(),gid=os.getgid())
    require(set(owner)=={'uid','gid'} and all(type(value) is int and 0<=value<2**32-1 for value in owner.values()),
            'Exact expected host UID/GID required')
    root=root.resolve()
    require(disk==root/'target.qcow2' and variables==root/'OVMF_VARS.fd'
            and out==root/'offline-update-cycle','Only the exact fresh-run disposable paths are allowed')
    for path in (root,disk,variables):
        require(not path.is_symlink(),'Linked disposable input is forbidden')
    require(root.is_dir() and disk.is_file() and variables.is_file(),'Fresh installed disk/vars are absent')
    require(all(path.stat().st_uid==owner['uid'] and path.stat().st_gid==owner['gid']
                and not stat.S_IMODE(path.stat().st_mode)&0o022
                for path in (disk,variables)),'Guest disk/vars must be owned and not writable by others')
    require(not out.exists() and not out.is_symlink(),'Cycle evidence destination must be unused')
    return input_identity(disk,variables)

def qemu_argv(disk,variables,out,firmware,qmp,serial):
    for path in (disk,variables,out,firmware,Path(qmp),Path(serial)):
        require(',' not in str(path),'Unsupported QEMU comma-containing path')
    return ['qemu-system-x86_64','-machine','q35','-accel','kvm','-cpu','max','-smp','2','-m','4096',
        '-display','none','-vga','virtio','-qmp',f'unix:{qmp},server=on,wait=off',
        '-serial',f'unix:{serial},server=on,wait=off','-monitor','none','-no-reboot',
        '-drive',f'file={disk},if=none,id=disk,discard=unmap','-device','virtio-blk-pci,drive=disk,bootindex=0',
        '-netdev','user,id=net0,restrict=on','-device','virtio-net-pci,netdev=net0',
        '-device','qemu-xhci','-device','usb-tablet','-rtc','base=utc',
        '-drive',f'if=pflash,format=raw,unit=0,readonly=on,file={firmware}',
        '-drive',f'if=pflash,format=raw,unit=1,file={variables}']

def serial_bindings(argv):
    roots=[item[5:].split(',',1)[0] for item in argv if item.startswith('unix:/tmp/arctic-offline-v6-')]
    require(len(roots)==2,'Exact QMP and guest serial socket bindings required')
    qmp,serial=map(Path,roots)
    require(qmp.parent==serial.parent and qmp.name=='qmp.sock' and serial.name=='serial.sock'
            and re.fullmatch(r'/tmp/arctic-offline-v6-[A-Za-z0-9_-]{8}',str(qmp.parent)),
            'Only a same-run private QMP/serial socket directory is allowed')
    return str(qmp),str(serial)

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
    owner=result.get('disk_owner',{});inputs=result.get('disk_identity',{})
    require(isinstance(owner,dict) and set(owner)=={'uid','gid'}
            and all(type(value) is int and 0<=value<2**32-1 for value in owner.values())
            and isinstance(inputs,dict) and set(inputs)=={'/out/target.qcow2','/out/OVMF_VARS.fd'}
            and all(isinstance(value,dict) and type(value.get('uid')) is int and type(value.get('gid')) is int
                and value.get('uid')==owner['uid'] and value.get('gid')==owner['gid']
                and type(value.get('mode')) is int and not value['mode']&0o022
                and type(value.get('inode')) is int and value['inode']>0
                and type(value.get('device')) is int and value['device']>=0 for value in inputs.values()),
            'Exact same-run host disk ownership/stat proof is required')
    require(result.get('unlock_prompt_seen') is True and result.get('passphrase_submitted') is True
            and result.get('serial_peer_verified') is True and result.get('unlock_attempts')==1
            and type(result.get('unlock_attempts')) is int and result.get('raw_serial_complete') is True
            and result.get('serial_eof_observed') is True and result.get('passphrase_echo_detected') is False,
            'Guest exit before verified unlock submission is not an expected cycle')
    first=result.get('first_install',{});proof=result.get('unlock_prompt_evidence',{})
    require(isinstance(first,dict) and isinstance(proof,dict)
            and re.fullmatch(UUID,str(first.get('luks_uuid','')))
            and re.fullmatch('[0-9a-f]{64}',str(first.get('serial_install_sha256','')))
            and proof.get('luks_uuid')==first['luks_uuid']
            and re.fullmatch('[0-9a-f]{32}',str(proof.get('boot_id','')))
            and proof.get('unique_current_prompt') is True
            and proof.get('transport')=='owned bidirectional ttyS0 serial',
            'Actual single current root password request is not bound to the passed first install')
    boundary=result.get('serial_input_boundary',{});post=result.get('serial_post_input_observation',{})
    require(isinstance(boundary,dict) and set(boundary)=={'bytes','sha256'}
            and type(boundary['bytes']) is int and boundary['bytes']>0
            and re.fullmatch('[0-9a-f]{64}',str(boundary['sha256']))
            and isinstance(post,dict) and post.get('initial_prompt_evidence')==proof
            and post.get('pending_fragment') is None and post.get('accepted_unlock') is False
            and post.get('additional_input_allowed') is False,
            'Pre-write proof and complete post-input observation required; redraw is not unlock')
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


UUID=r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
MAX_SERIAL=64*1024*1024

def first_install_root(path,expected_sha):
    require(not path.is_symlink() and path.is_file() and path.stat().st_size<=16*1024*1024,
            'Owned fresh first-install log absent or oversized')
    require(re.fullmatch('[0-9a-f]{64}',expected_sha) is not None,'First-install hash absent')
    data=path.read_bytes()
    require(hashlib.sha256(data).hexdigest()==expected_sha,'First-install log changed after the passed phase')
    text=data.decode(errors='strict')
    mappings=re.findall(r'^\$ cryptsetup open --allow-discards --key-file - /dev/vda4 luks-('+UUID+r') < \[secret: disk passphrase\]\r?$',text,re.M)
    formats=re.findall(r'^\$ cryptsetup luksFormat --batch-mode --type luks2 --pbkdf argon2id --label arctic-root --key-file - /dev/vda4 < \[secret: disk passphrase\]\r?$',text,re.M)
    require(len(mappings)==len(formats)==1,'Unique freshly formatted CI root mapping required')
    require(re.findall(r'^ARCTIC-INSTALL-EXIT=(.*)$',text,re.M) in (['0'],['0\r']),
            'Fresh install did not record exactly one successful exit')
    return dict(luks_uuid=mappings[0],serial_install_sha256=expected_sha,
                source='Same-run passed first install; exact /dev/vda4 cryptsetup format/open')

def qemu_identity(pid):
    proc=Path('/proc')/str(pid)
    uid=[int(item) for item in re.search(r'^Uid:\s+(.*)$',(proc/'status').read_text(),re.M)[1].split()]
    require(uid==[os.getuid()]*4,'Serial QEMU process is not owned by this test process')
    executable=str((proc/'exe').resolve(strict=True))
    require(executable==str(Path('/usr/bin/qemu-system-x86_64').resolve(strict=True)),
            'Serial peer is not the actual Fedora QEMU executable')
    fields=(proc/'stat').read_text().rsplit(')',1)[1].split()
    return dict(pid=pid,start_ticks=int(fields[19]),uid=os.getuid(),executable=executable)

def validate_peer(credentials,identity,current,path_stat,initial_stat):
    require(credentials==(identity['pid'],identity['uid'],identity['uid']) and current==identity,
            'Serial peer PID/UID/start/executable identity changed')
    require(stat.S_ISSOCK(path_stat.st_mode) and path_stat.st_uid==identity['uid']
            and (path_stat.st_dev,path_stat.st_ino)==(initial_stat.st_dev,initial_stat.st_ino),
            'Serial socket path is linked, stale or replaced')

def serial_prompt(data,first):
    text=data.decode(errors='replace')
    # These come from the current owned serial connection, never a saved log.
    boot_matches=list(re.finditer(r'bootid=([0-9a-f]{32});pid=1;.*?type=boot',text))
    command_matches=list(re.finditer(r'dracut-cmdline\[\d+\]: Using kernel command line parameters:([^\r\n]+)',text))
    prompt_matches=list(re.finditer(r'Please enter passphrase for disk Arctic root \(luks-('+UUID+r')\)::',text))
    boots=[match[1] for match in boot_matches]
    commands=[match[1] for match in command_matches]
    prompts=[match[1] for match in prompt_matches]
    if not prompts:
        return None
    require(1<=len(boots)<=2 and len(set(boots))==1 and len(commands)==len(prompts)==1,
            'Ambiguous/stale boot, kernel line or password request')
    require(boot_matches[0].end()<command_matches[0].start()
            and command_matches[0].end()<prompt_matches[0].start(),
            'Password request precedes its current boot/kernel identity')
    tokens=commands[0].split()
    require([item for item in tokens if item.startswith('rd.luks.uuid=')]==['rd.luks.uuid=luks-'+first['luks_uuid']],
            'Actual kernel root UUID differs from the passed fresh install')
    require(prompts==[first['luks_uuid']],'Actual password request is for another LUKS device')
    require([item for item in tokens if item.startswith('console=')]==['console=tty0','console=ttyS0,115200']
            and tokens.count('systemd.journald.forward_to_console=1')==1,
            'Actual serial input/console route differs from the reviewed route')
    require(not re.search(r'(?:login:|emergency mode|incorrect|No key available)',text,re.I),
            'Password request occurred after an unexpected login/error path')
    return dict(luks_uuid=prompts[0],boot_id=boots[0],transport='owned bidirectional ttyS0 serial',
                console_sequence=['tty0','ttyS0,115200'],unique_current_prompt=True)

class SerialOutputAmbiguous(RuntimeError):
    """Final unresolved terminal output is withheld without claiming echo."""

def assert_no_echo(data,final=False):
    # Never persist an unexpected echo, including ANSI-wrapped/split output.
    # Use the same complete CSI/OSC/simple-ESC recognition as rejection
    # classification. Pump and failure cleanup both call this shared guard.
    require(PASSPHRASE.encode() not in data,'Unexpected passphrase echo; output withheld')
    try:
        plain,pending=ansi_rejection_view(data)
    except RuntimeError:
        raise SerialOutputAmbiguous('Malformed ANSI output; post-input bytes withheld') from None
    require(PASSPHRASE.encode() not in data and PASSPHRASE.encode() not in plain
            and PASSPHRASE.encode()[:8] not in plain,'Unexpected passphrase echo; output withheld')
    if final and pending:
        raise SerialOutputAmbiguous('Unresolved ANSI output; post-input bytes withheld')

def ansi_rejection_view(data):
    """Recognition for rejection only; it never validates a redraw or input."""
    complete=re.compile(rb'(?:\x1b\[[0-?]*[ -/]*[@-~]|'
        rb'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[ -/]*[0-~])')
    pieces=[];offset=0
    while True:
        pos=data.find(b'\x1b',offset)
        if pos<0:
            pieces.append(data[offset:]);return b''.join(pieces),False
        pieces.append(data[offset:pos]);rest=data[pos:]
        # '[' and ']' need their complete CSI/OSC grammar, not the generic
        # two-byte ESC form. An unfinished sequence can collect output only.
        if rest.startswith(b'\x1b['):
            match=re.match(rb'\x1b\[[0-?]*[ -/]*[@-~]',rest)
            partial=re.fullmatch(rb'\x1b\[[0-?]*[ -/]*',rest)
        elif rest.startswith(b'\x1b]'):
            match=re.match(rb'\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)',rest)
            partial=re.fullmatch(rb'\x1b\][^\x07\x1b]*(?:\x1b)?',rest)
        else:
            match=complete.match(rest)
            partial=re.fullmatch(rb'\x1b[ -/]*',rest)
        if match is None:
            require(partial is not None,'Malformed ANSI sequence in post-input output')
            return b''.join(pieces),True
        offset=pos+len(match[0])

def serial_after_input(data,first,boundary,final=False):
    """Replay one submitted request's raw stream; masked repaint is not unlock."""
    require(isinstance(boundary,dict) and set(boundary)=={'bytes','sha256'}
            and type(boundary['bytes']) is int and 0<boundary['bytes']<=len(data)
            and re.fullmatch('[0-9a-f]{64}',str(boundary['sha256'])),
            'Exact pre-write serial boundary required')
    prefix=data[:boundary['bytes']];tail=data[boundary['bytes']:]
    require(hashlib.sha256(prefix).hexdigest()==boundary['sha256'],'Pre-write serial prefix changed')
    proof=serial_prompt(prefix,first);require(proof is not None,'Submitted request lacks original current proof')
    assert_no_echo(tail)
    rejection_view,ansi_pending=ansi_rejection_view(tail)
    rejection=(rb'(?:incorrect|No key available|authentication failed|bad password|wrong passphrase|'
            rb'failed to activate with specified passphrase|too many retries|too many attempts|'
            rb'failed to ask for password|password query was cancelled|maximum number of tries exceeded|'
            rb'Failed to start[^\r\n]*Cryptography Setup|login:|emergency mode)')
    require(not re.search(rejection,tail,re.I) and not re.search(rejection,rejection_view,re.I),
            'Explicit password rejection/cancellation after the single write')
    boots=re.findall(rb'bootid=([0-9a-f]{32});pid=1;[^\r\n]*?type=boot',data)
    require(boots and len(boots)<=2 and set(boots)=={proof['boot_id'].encode()},'Current boot changed after submission')
    require(b'Using kernel command line parameters:' not in tail,
            'Another kernel identity appeared after the single write')
    clear=b'\x1b[2K\r'
    prompt=b'Please enter passphrase for disk Arctic root (luks-'+first['luks_uuid'].encode()+b')::'
    anchor=b'Please enter passphrase';lengths=[]
    pending='incomplete ANSI sequence' if ansi_pending else None
    raw_anchors=list(re.finditer(re.escape(anchor),tail))
    require(len(list(re.finditer(re.escape(anchor),rejection_view,re.I)))==len(raw_anchors),
            'Decorated/changed password challenge after the single write')
    for match in raw_anchors:
        pos=match.start()
        require(pos>=len(clear) and tail[pos-len(clear):pos]==clear,
                'New/unmarked password challenge after the single write')
        available=tail[pos:pos+len(prompt)]
        require(prompt.startswith(available),'Redraw requests a changed root or prompt')
        if len(available)<len(prompt):
            pending='partial same-root repaint';continue
        rest=tail[pos+len(prompt):]
        mask=re.match(rb'\*+',rest)
        if mask is None:
            require(not rest,'New empty or anomalous password challenge after the single write')
            pending='complete repaint awaiting mask';continue
        count=len(mask[0])
        require(count<=len(PASSPHRASE.encode()),'Mask overflow is an ambiguous new password challenge')
        if lengths and count<lengths[-1]:
            # The latest recv() may end inside a growing mask run. Collect
            # bounded output only; a delimiter or EOF before it catches up
            # remains an ambiguous reset and cannot qualify the cycle.
            require(len(mask[0])==len(rest),'Mask reset is an ambiguous new password challenge')
            pending='partial mask below previous repaint';continue
        lengths.append(count)
    # A recv() boundary can split the clear-line sequence or prompt before
    # enough bytes arrive to contain the full anchor. It grants no input.
    for length in range(1,len(clear)+len(anchor)):
        if tail.endswith((clear+prompt)[:length]):
            pending='partial clear-line/prompt sequence';break
    for length in range(7,len(anchor)):
        if tail.endswith(anchor[:length]):
            pending='partial password text';break
        if rejection_view.lower().endswith(anchor[:length].lower()):
            pending='partial decorated password text';break
    require(not final or pending is None,'Incomplete/ambiguous password repaint at serial EOF')
    return dict(initial_prompt_evidence=proof,complete_masked_redraws=len(lengths),mask_lengths=lengths,
        pending_fragment=pending,accepted_unlock=False,additional_input_allowed=False,
        meaning='Redraw observation only; one input write remains final; third-boot history mandatory')

class SerialChannel:
    def __init__(self,path,process,log):
        require(not path.parent.is_symlink() and path.parent.stat().st_uid==os.getuid()
                and stat.S_IMODE(path.parent.stat().st_mode)==0o700,'Private owned serial directory required')
        self.path=path;self.process=process;self.identity=qemu_identity(process.pid)
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(2)
        self.stream=None;self.data=bytearray();self.after=bytearray();self.attempts=0
        self.closed=False;self.persisted=False;self.echo_rejected=False
        try:
            deadline=time.monotonic()+10
            while not path.exists() and process.poll() is None and time.monotonic()<deadline:
                time.sleep(0.1)
            require(not path.is_symlink() and path.exists() and stat.S_ISSOCK(path.lstat().st_mode),
                    'Current serial socket absent')
            self.initial_stat=path.lstat();self.sock.connect(str(path))
            self.credentials=struct.unpack('3i',self.sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            self.verify_peer();self.sock.settimeout(0.05)
            self.stream=log.open('xb')
        except BaseException:
            self.close()
            raise

    def verify_peer(self):
        require(not self.path.is_symlink(),'Linked serial socket rejected')
        validate_peer(self.credentials,self.identity,qemu_identity(self.process.pid),self.path.lstat(),self.initial_stat)

    def pump(self):
        if self.process.poll() is None:
            self.verify_peer()
        for _ in range(128):
            try:
                block=self.sock.recv(32768)
            except socket.timeout:
                break
            if not block:
                self.closed=True;break
            require(len(self.data)+len(block)<=MAX_SERIAL,'Serial output bound exceeded')
            self.data.extend(block)
            if self.attempts:
                self.after.extend(block)
                # Stop before any further output handling on a detected echo.
                assert_no_echo(bytes(self.after))
            else:
                self.stream.write(block);self.stream.flush()

    def submit_once(self,first,result):
        self.verify_peer()
        proof=serial_prompt(bytes(self.data),first)
        require(proof is not None and not self.closed and self.attempts==0,
                'One current owned password request is required before any input')
        boundary=dict(bytes=len(self.data),sha256=hashlib.sha256(self.data).hexdigest())
        self.attempts=1;result.update(unlock_attempts=1,unlock_prompt_seen=True,serial_input_boundary=boundary,
            unlock_prompt_evidence=proof,passphrase_submitted=False)
        # Only guest input is sent; it never enters argv, QMP, stdout or logs.
        self.sock.settimeout(2)
        try:
            self.sock.sendall(PASSPHRASE.encode()+b'\n')
        except OSError:
            raise RuntimeError('The single bounded serial unlock write failed') from None
        finally:
            self.sock.settimeout(0.05)
        result['passphrase_submitted']=True
        if self.process.poll() is None:
            self.verify_peer()

    def persist_safe(self):
        if not self.persisted:
            try:
                assert_no_echo(bytes(self.after),final=True)
            except SerialOutputAmbiguous:
                raise
            except RuntimeError:
                self.echo_rejected=True
                raise
            self.stream.write(self.after);self.stream.flush();self.persisted=True
        return dict(raw_serial_complete=True,serial_output_ambiguous=False,raw_serial_bytes=len(self.data),
                    raw_serial_sha256=hashlib.sha256(self.data).hexdigest(),passphrase_echo_detected=False,
                    serial_eof_observed=self.closed)

    def close(self):
        self.sock.close()
        if self.stream is not None:
            self.stream.close()

def observe(vm,vmtest,result,timeout,channel,first,clock=time.monotonic,pause=time.sleep):
    start=clock();deadline=start+timeout
    while vm.alive() and clock()<min(deadline,start+240):
        channel.pump();shot=vm.shot('01-menu-probe')
        if shot and vmtest.looks_like_boot_menu(shot):
            break
        pause(1)
    else:
        raise RuntimeError('Actual installed boot menu was not observed')
    vm.shot('02-boot-menu');vm.keys('e');pause(1);vm.keys('down','down','down','ctrl-e')
    vm.type_text(' '+CONSOLE_APPEND,gap=0.1);vm.shot('03-console-only-entry');vm.keys('ctrl-x')
    while vm.alive() and clock()<min(deadline,start+900):
        channel.pump()
        proof=serial_prompt(bytes(channel.data),first)
        if proof is not None:
            break
        require(not channel.closed,'Serial connection ended before the verified password request')
        pause(0.2)
    else:
        raise RuntimeError('Current serial root password request absent; no blind input or fallback')
    vm.shot('05-actual-serial-prompt');channel.submit_once(first,result)
    last=-30;closed_at=None
    while vm.alive() and clock()<deadline:
        channel.pump()
        result['serial_post_input_observation']=serial_after_input(bytes(channel.data),first,result['serial_input_boundary'])
        if channel.closed:
            closed_at=closed_at or clock()
            require(clock()-closed_at<=2,'Serial connection lost while the guest remains alive')
        elapsed=clock()-start
        if elapsed-last>=30:
            # No post-input screenshots: an unexpected terminal echo must not
            # become a saved image before the incoming byte check rejects it.
            last=elapsed
            vmtest.log(f'Observing restricted offline update cycle {elapsed:.0f}s; third boot remains mandatory')
        pause(0.2)
    channel.pump()
    result['serial_post_input_observation']=serial_after_input(bytes(channel.data),first,result['serial_input_boundary'],final=True)
    result.update(channel.persist_safe())
    result.update(guest_exited=not vm.alive(),timed_out=vm.alive(),elapsed_seconds=clock()-start,
                  qemu_exit_code=vm.proc.poll())
    vm.drain_events();result['events']=list(vm.events)
    result.update(validate_cycle(result))
    return result

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disk',type=Path,required=True);parser.add_argument('--vars',type=Path,required=True)
    parser.add_argument('--first-install-sha256',required=True)
    parser.add_argument('--disk-owner-uid',type=int,required=True);parser.add_argument('--disk-owner-gid',type=int,required=True)
    parser.add_argument('--out',type=Path,required=True);parser.add_argument('--timeout',type=int,default=5400)
    args=parser.parse_args()
    require(300<=args.timeout<=5400,'Cycle timeout must be 300..5400 seconds')
    owner=dict(uid=args.disk_owner_uid,gid=args.disk_owner_gid)
    identity=validate_paths(args.disk,args.vars,args.out,owner=owner)
    require(Path('/dev/kvm').is_char_device(),'Native KVM is mandatory; no TCG fallback')
    firmware=Path('/usr/share/edk2/ovmf/OVMF_CODE.fd');require(firmware.is_file(),'OVMF absent')
    helper=Path('/arctic-lib/vmtest.py')
    require(hashlib.sha256(helper.read_bytes()).hexdigest()==VMTEST_SHA256,'Exact candidate VM helper changed')
    first=first_install_root(args.disk.parent/'serial-install.log',args.first_install_sha256)
    args.out.mkdir();os.environ['OUT']=str(args.out);sys.path.insert(0,'/arctic-lib')
    import vmtest
    transport=tempfile.TemporaryDirectory(prefix='arctic-offline-v6-',dir='/tmp')
    socket_root=Path(transport.name);os.chmod(socket_root,0o700)
    qmp=str(socket_root/'qmp.sock');serial=str(socket_root/'serial.sock')
    argv=qemu_argv(args.disk,args.vars,args.out,firmware,qmp,serial)
    result=dict(status='running',platform='QEMU_KVM',network='restricted_offline',actual_qemu_argv=argv,
        transient_console_append=CONSOLE_APPEND,vmtest_sha256=VMTEST_SHA256,
        firmware_sha256=hashlib.sha256(firmware.read_bytes()).hexdigest(),
        first_install=first,unlock_attempts=0,disk_owner=owner,disk_identity=identity,
        update_qualification='UNRUN: this phase only observes the guest cycle exit')
    report=args.out/'cycle-result.json';vm=None;channel=None
    def save():report.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    try:
        save();VM=observed_vm_type(vmtest)
        vm=VM(argv,qmp,'offline-cycle',args.out/'qmp-events.jsonl')
        channel=SerialChannel(Path(serial),vm.proc,args.out/'serial-offline-cycle.log')
        channel.verify_peer()
        result['serial_peer_verified']=True;result['serial_peer']=channel.identity
        observe(vm,vmtest,result,args.timeout,channel,first)
        require(identity==input_identity(args.disk,args.vars),
                'Disposable installed disk/vars path identity changed')
        save()
    except BaseException as error:
        result.update(status='failed_or_unrun',error=str(error))
        if vm is not None:result['events']=list(vm.events)
        if channel is not None:
            try:
                result.update(channel.persist_safe())
            except SerialOutputAmbiguous as withholding:
                result.update(passphrase_echo_detected=None,serial_output_ambiguous=True,raw_serial_complete=False,
                    withheld_post_unlock_bytes=len(channel.after),error=str(withholding))
            except RuntimeError:
                result.update(passphrase_echo_detected=True,raw_serial_complete=False,
                    withheld_post_unlock_bytes=len(channel.after),error='Unexpected passphrase echo; post-input output withheld')
        save();raise
    finally:
        if channel is not None:channel.close()
        if vm is not None:vm.quit()
        transport.cleanup()

if __name__=='__main__':main()
