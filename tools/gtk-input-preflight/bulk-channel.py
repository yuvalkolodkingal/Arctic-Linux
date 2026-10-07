#!/usr/bin/env python3
"""One diagnostic-only virtio port; exact newline records, bounded stream, real EOF.

The kernel console is not opened, rewritten or filtered by this module.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import select
import socket
import stat
import struct
import time

NAME = 'org.arctic.diagnostic.bulk'
MAX_STREAM = 24*1024*1024  # Encoded envelope only; unchanged decoded 16 MiB limit applies separately.
MAX_LINE = 256*1024
WRITE_SECONDS = 60


def require(value, message):
    if not value: raise RuntimeError(message)


def strict_json(data):
    def pairs(items):
        value = {}
        for key,item in items:
            require(key not in value, 'duplicate bulk JSON key')
            value[key] = item
        return value
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda x: (_ for _ in ()).throw(RuntimeError('nonfinite bulk JSON')))


class Writer:
    def __init__(self, port=Path('/dev/virtio-ports')/NAME):
        self.fd = None; self.bytes = 0; self.lines = 0; self.digest = hashlib.sha256(); self.export_deadline=None
        require(os.geteuid()==0, 'guest bulk port requires guarded root collector')
        require(port.is_symlink(), 'named virtio data port must be a device symlink')
        device = port.resolve(strict=True)
        require(device.parent == Path('/dev') and re.fullmatch(r'vport[0-9]+p[0-9]+',device.name)
                and stat.S_ISCHR(device.stat().st_mode), 'resolved bulk device differs')
        actual = (Path('/sys/class/virtio-ports')/device.name/'name').read_text().strip()
        require(actual == NAME, 'actual virtio port name differs')
        self.identity=dict(name=NAME,named_path=str(port),resolved_device=str(device),device_major=os.major(device.stat().st_rdev),
                           device_minor=os.minor(device.stat().st_rdev),kind='character-device',sysfs_name=actual)
        self.fd = os.open(device, os.O_WRONLY|os.O_NONBLOCK|os.O_NOCTTY|os.O_NOFOLLOW)
        try:
            require(os.fstat(self.fd).st_rdev == device.stat().st_rdev, 'opened bulk device identity differs')
        except BaseException:
            os.close(self.fd); self.fd = None; raise

    def write(self, prefix, value):
        require(self.fd is not None and isinstance(prefix,str) and prefix.endswith(' '), 'closed/invalid bulk writer')
        row = (prefix+json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode()
        require(len(row) <= MAX_LINE and self.bytes+len(row) <= MAX_STREAM, 'bulk encoded bound exceeded')
        deadline = time.monotonic()+WRITE_SECONDS
        if self.export_deadline is not None: deadline=min(deadline,self.export_deadline)
        offset = 0
        while offset < len(row):
            require(time.monotonic() < deadline, 'bulk write deadline; no console fallback')
            if not select.select([], [self.fd], [], min(.2,deadline-time.monotonic()))[1]: continue
            try: count = os.write(self.fd,row[offset:])
            except BlockingIOError: continue
            require(count > 0, 'bulk write made no progress')
            offset += count
        self.bytes += len(row); self.lines += 1; self.digest.update(row)

    def start_export(self):
        require(self.export_deadline is None, 'bulk export deadline already started')
        self.export_deadline=time.monotonic()+WRITE_SECONDS

    def close(self):
        if self.fd is not None: os.close(self.fd); self.fd = None


class Receiver:
    """Own exactly one socket connection and one unused raw evidence file."""
    def __init__(self, root, expected_pid, clock=time.monotonic):
        self.root = Path(root); self.clock = clock; self.socket = None; self.stream = None
        require(type(expected_pid) is int and expected_pid>1, 'actual owned QEMU PID required')
        self.expected_pid=expected_pid
        self.start_ticks=self.process_start()
        self.peer=None; self.closed=False; self.shutting_down=False; self.owned_vm_exit_status=None
        self.bytes = 0; self.lines = 0; self.pending = b''; self.eof = False; self.digest = hashlib.sha256()
        self.path = self.root/'bulk-evidence.log'; self.record = self.root/'bulk-channel.txt'
        require(not self.path.exists() and not self.record.exists(), 'bulk outputs must be unused')
        self.stream = self.path.open('xb')

    def process_start(self):
        value=(Path('/proc')/str(self.expected_pid)/'stat').read_text()
        return int(value[value.rindex(')')+2:].split()[19])

    def connect(self):
        require(self.socket is None, 'bulk connection is one-use')
        path = self.root/'bulk.sock'
        require(stat.S_ISSOCK(path.lstat().st_mode) and path.lstat().st_uid == os.getuid(), 'owned QEMU bulk socket absent')
        sock = socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        try:
            sock.settimeout(2); sock.connect(str(path))
            pid,uid,gid=struct.unpack('3i',sock.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
            require(pid==self.expected_pid and uid==os.getuid() and self.process_start()==self.start_ticks,
                    'actual bulk socket peer is not the owned current QEMU process')
            self.peer=dict(pid=pid,uid=uid,gid=gid,start_ticks=self.start_ticks)
            sock.setblocking(False); self.socket = sock
        except BaseException: sock.close(); raise

    def pump(self):
        require(self.socket is not None, 'bulk connection absent')
        if self.eof: return
        # Bound each pump too, so a producer cannot starve controller deadline checks.
        for _ in range(32):
            try: data = self.socket.recv(65536)
            except BlockingIOError: break
            if not data:
                self.eof = True
                require(self.shutting_down, 'unexpected bulk socket EOF before owned QEMU shutdown')
                require(not self.pending, 'bulk EOF with partial final newline record')
                break
            self.bytes += len(data); self.digest.update(data); self.stream.write(data); self.stream.flush()
            require(self.bytes <= MAX_STREAM, 'bulk raw stream exceeded bound')
            self.pending += data
            while b'\n' in self.pending:
                row,self.pending = self.pending.split(b'\n',1)
                require(row and len(row)+1 <= MAX_LINE, 'bulk empty/oversized newline record')
                row.decode('utf-8',errors='strict'); self.lines += 1
            require(len(self.pending) < MAX_LINE, 'bulk unfinished newline exceeds bound')

    def text(self):
        self.pump()
        data = self.path.read_bytes()
        end = data.rfind(b'\n')+1
        return data[:end].decode('utf-8',errors='strict')

    def begin_shutdown(self):
        self.shutting_down=True

    def observed_vm_exit(self, status):
        require(self.shutting_down and type(status) is int, 'owned QEMU exit status not observed')
        self.owned_vm_exit_status=status

    def close(self):
        if self.closed: return
        self.closed=True; errors=[]
        stream,self.stream=self.stream,None
        sock,self.socket=self.socket,None
        if stream is not None:
            try: stream.close()
            except BaseException as exc:
                errors.append('raw stream close: '+type(exc).__name__+': '+str(exc))
                # Writes were explicitly flushed in pump. Close the same owned raw
                # descriptor even if BufferedWriter.close fails; never another fd.
                try:
                    if not stream.closed: stream.raw.close()
                except BaseException as inner:errors.append('owned raw fallback close: '+str(inner))
        if sock is not None:
            try: sock.close()
            except BaseException as exc:
                errors.append('socket close: '+type(exc).__name__+': '+str(exc))
                try: socket.socket.close(sock) # Exact same owned socket, no reconnect.
                except BaseException as inner:errors.append('owned socket fallback close: '+str(inner))
        resources_closed=(stream is None or stream.closed) and (sock is None or sock.fileno()==-1)
        with self.record.open('x') as output: output.write(json.dumps(dict(schema='arctic-bulk-channel-v1',port_name=NAME,
            bytes=self.bytes,lines=self.lines,sha256=self.digest.hexdigest(),actual_socket_eof=self.eof,
            unfinished_record_bytes=len(self.pending),encoded_limit_bytes=MAX_STREAM,
            newline_limit_bytes=MAX_LINE,console_unchanged=True,added_diagnostic_device=True,
            socket_peer=self.peer,eof_origin='owned-QEMU-exit',owned_vm_exit_status=self.owned_vm_exit_status,
            shutdown_started=self.shutting_down,resources_closed=resources_closed,close_errors=errors,
            release_acceptance=False),sort_keys=True)+'\n')
        require(resources_closed and not errors,'bulk resource cleanup failed: '+'; '.join(errors))


def run_owned(vm,root,action,remaining_seconds,clock=time.monotonic,sleep=time.sleep):
    """Protect all setup/shutdown/EOF resources and preserve primary failures."""
    receiver=None;primary=None;cleanup=[];deadline=0
    try:
        deadline=clock()
        require(type(remaining_seconds) in (int,float) and 0<=remaining_seconds<=900,'remaining harness deadline differs')
        deadline+=remaining_seconds # Anchor the absolute allowance before controller work.
        receiver=Receiver(root,vm.proc.pid)
        receiver.connect()
        action(receiver)
    except BaseException as exc:primary=exc
    finally:
        try:
            if receiver is not None:receiver.begin_shutdown()
            vm.quit() # Unchanged owned QEMU primitive, no alternate process signalling.
            if receiver is not None:
                receiver.observed_vm_exit(vm.proc.poll())
                until=min(clock()+5,deadline)
                while not receiver.eof and clock()<until:
                    receiver.pump();sleep(.02)
                require(receiver.eof,'real data socket EOF absent after owned QEMU exit')
        except BaseException as exc:cleanup.append('owned VM shutdown/EOF: '+type(exc).__name__+': '+str(exc))
        finally:
            if receiver is not None:
                try:receiver.close()
                except BaseException as exc:cleanup.append('bulk close: '+type(exc).__name__+': '+str(exc))
        with (Path(root)/'bulk-shutdown.txt').open('x') as output:
            output.write(json.dumps(dict(primary_error=None if primary is None else type(primary).__name__+': '+str(primary),
                cleanup_errors=cleanup,release_acceptance=False,only_owned_resources=True),sort_keys=True)+'\n')
    if primary is not None:raise primary
    require(not cleanup,'; '.join(cleanup))



def validate(data, record):
    require(type(data) is bytes and 0 < len(data) <= MAX_STREAM and data.endswith(b'\n'), 'bulk raw EOF/size differs')
    require(record.get('schema') == 'arctic-bulk-channel-v1' and record.get('port_name') == NAME
            and record.get('actual_socket_eof') is True and type(record.get('bytes')) is int
            and record['bytes'] == len(data) and record.get('sha256') == hashlib.sha256(data).hexdigest()
            and type(record.get('unfinished_record_bytes')) is int and record['unfinished_record_bytes'] == 0
            and record.get('encoded_limit_bytes') == MAX_STREAM and record.get('newline_limit_bytes') == MAX_LINE
            and record.get('console_unchanged') is True and record.get('added_diagnostic_device') is True
            and record.get('release_acceptance') is False and record.get('eof_origin')=='owned-QEMU-exit'
            and record.get('resources_closed') is True and record.get('close_errors')==[]
            and record.get('shutdown_started') is True and type(record.get('owned_vm_exit_status')) is int
            and type(record.get('socket_peer')) is dict
            and type(record['socket_peer'].get('pid')) is int and record['socket_peer']['pid']>1
            and type(record['socket_peer'].get('start_ticks')) is int and record['socket_peer']['start_ticks']>0
            and type(record['socket_peer'].get('uid')) is int and record['socket_peer']['uid']>=0,
            'bulk raw channel provenance differs')
    allowed = ('ARCTIC-PCMANFM-DIAG-BEGIN ', 'ARCTIC-PCMANFM-DIAG-REPORT ',
               'ARCTIC-NATIVE-EVIDENCE-CHUNK ', 'ARCTIC-NATIVE-EVIDENCE-MANIFEST ', 'ARCTIC-PCMANFM-DIAG-END ')
    phase = 0; rows = []
    for row in data[:-1].split(b'\n'):
        require(0 < len(row)+1 <= MAX_LINE, 'bulk newline bound/blank record')
        text = row.decode('utf-8',errors='strict')
        matches = [i for i,prefix in enumerate(allowed) if text.startswith(prefix)]
        require(len(matches) == 1, 'unknown bulk protocol record')
        index = matches[0]
        expected = (0,) if phase == 0 else (1,) if phase == 1 else (2,3) if phase == 2 else (4,) if phase == 3 else ()
        require(index in expected, 'bulk record order/duplicate differs')
        value = strict_json(text[len(allowed[index]):]); require(type(value) is dict, 'bulk JSON object absent')
        if index != 2: phase += 1
        rows.append((allowed[index],value))
    require(phase == 4 and type(record.get('lines')) is int and record['lines'] == len(rows), 'bulk protocol/count incomplete')
    return rows
