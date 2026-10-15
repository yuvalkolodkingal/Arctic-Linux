#!/usr/bin/env python3
"""Audit-only native app checks; never runs merely by being imported.

Run ONLY as root at /run/t/native_smoke.py in an explicitly disposable QEMU/KVM
guest, before installing a Nix alternative on the desktop user's PATH. No package
install, network request, service restart, policy change or production edit.
Import run_checks(prefix, stage, disposable_guest=True) into a separately reviewed
checker, or use the explicit CLI. See README.md for the limits of each gate.
"""
import argparse
import ast
import configparser
import hashlib
import json
import math
import os
from pathlib import Path
import pwd
import re
import shlex
import shutil
import signal
import selectors
import socket
import stat
import struct
import subprocess
import tempfile
import threading
import time


SCHEMA = 'arctic-native-functional-smoke-v4'
ROLES = dict(terminal='foot', browser='gtk-launch org.gnome.Epiphany', editor='featherpad', files='pcmanfm')
MIMES = {'inode/directory': 'pcmanfm.desktop', 'text/plain': 'featherpad.desktop',
         'video/x-matroska': 'io.github.celluloid_player.Celluloid.desktop',
         'application/zip': 'xarchiver.desktop'}
AVC = re.compile(r'avc:\s*denied|type=(?:USER_)?AVC\b', re.I)
LIMIT = 4 * 1024 * 1024
JOURNAL_LINE_LIMIT = 1024 * 1024
JOURNAL_RECORD_LIMIT = 250000
JOURNAL_STDERR_LIMIT = 64 * 1024
JOURNAL_READ_SIZE = 64 * 1024
# BEGIN STREAMING_AUDIT_FILE_INTERVAL
AUDIT_LINE_LIMIT = 1024 * 1024
AUDIT_RECORD_LIMIT = 500000
AUDIT_TOTAL_LIMIT = 128 * 1024 * 1024
AUDIT_READ_SIZE = 64 * 1024
AUDIT_AVC = re.compile(br'avc:\s*denied|type=(?:USER_)?AVC\b', re.I)
# END STREAMING_AUDIT_FILE_INTERVAL


def require(value, message):
    if not value:
        raise RuntimeError(message)


def execute(argv, *, cwd=None, input_bytes=None, stdout_path=None, timeout=45,
            allow_failure=False):
    """No shell interpolation; optional binary streams for compressor fixtures."""
    stream = open(stdout_path, 'wb') if stdout_path else subprocess.PIPE
    try:
        result = subprocess.run(argv, cwd=cwd, input=input_bytes, stdout=stream,
                                stderr=subprocess.PIPE, timeout=timeout, check=False)
    finally:
        if stdout_path:
            stream.close()
    output = result.stdout or b''
    require(len(output) + len(result.stderr) <= LIMIT, 'command output exceeded audit bound')
    if not allow_failure:
        require(result.returncode == 0,
                f'command failed ({result.returncode}): {argv!r}: '
                + result.stderr[-12000:].decode(errors='replace'))
    return result.returncode, output.decode(errors='replace').strip(), result.stderr.decode(errors='replace')


def digest(path):
    value = hashlib.sha256()
    with open(path, 'rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def tree_hashes(root):
    """Compare every directory/file path and type, plus each regular file's bytes.

    The implicit extraction root itself is excluded: archive entries '.'/'./'
    refer to that same root. No named wrapper directory or empty member is ignored.
    """
    root = Path(root)
    require(root.is_dir() and not root.is_symlink(), 'invalid or symlink fixture root')
    result = {}
    for path in sorted(root.rglob('*')):
        mode = path.lstat().st_mode
        require(stat.S_ISDIR(mode) or stat.S_ISREG(mode), 'non-regular extracted archive member')
        key = path.relative_to(root).as_posix()
        if stat.S_ISDIR(mode):
            result[key] = dict(type='directory')
        else:
            result[key] = dict(type='file', bytes=path.stat().st_size, sha256=digest(path))
    require(result, 'empty fixture tree cannot pass')
    return result


def verify_tree(expected, root):
    actual = tree_hashes(root)
    require(actual == expected, f'extracted content mismatch: {actual!r}')
    return actual


def identity(pid, uid, proc_root=Path('/proc')):
    require(type(pid) is int and pid > 1, 'missing reliable window PID')
    proc = proc_root / str(pid)
    require(proc.stat().st_uid == uid, 'window process has a different owner')
    fields = (proc / 'stat').read_text().rsplit(')', 1)[1].split()
    require(fields[0] not in ('Z', 'X'), 'window process is dead')
    return dict(pid=pid, start_ticks=int(fields[19]),
                executable=str((proc / 'exe').resolve(strict=True)))


def process_snapshot(uid):
    result = set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            value = identity(int(proc.name), uid)
            result.add((value['pid'], value['start_ticks']))
        except (OSError, ValueError, IndexError, RuntimeError):
            pass
    return result


def window_proof(client, uid, expected_executable, before, native=True, proc_root=Path('/proc')):
    require(client.get('is_visible') is True and client.get('width', 0) > 0
            and client.get('height', 0) > 0, 'window is not visibly mapped')
    require(type(client.get('is_xwayland')) is bool, 'missing Wayland/Xwayland evidence')
    if native:
        require(client['is_xwayland'] is False, 'expected a native Wayland window')
    value = identity(client.get('pid'), uid, proc_root)
    require((value['pid'], value['start_ticks']) not in before, 'window belongs to a pre-existing process')
    require(value['executable'] == str(Path(expected_executable).resolve(strict=True)),
            'mapped PID runs a different executable')
    with open(value['executable'], 'rb') as binary:
        require(binary.read(4) == b'\x7fELF', 'mapped PID has not executed the native ELF')
    return dict(client_id=str(client['id']), **value, is_xwayland=client['is_xwayland'])


def parse_audit_status(text):
    fields = dict(line.split(None, 1) for line in text.splitlines() if len(line.split(None, 1)) == 2)
    require(fields.get('enabled') in ('0', '1', '2'), 'kernel audit status unobserved')
    require('lost' in fields and fields['lost'].isdigit(), 'missing audit loss counter')
    return dict(enabled=int(fields['enabled']), lost=int(fields['lost']))


def _unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate journal JSON key')
        result[key] = value
    return result


def _invalid_json_constant(_value):
    raise ValueError('nonfinite journal JSON number')


def journal_avc_count(cursor, timeout=60):
    """Scan every bounded journal JSON record without retaining message text."""
    process = None
    try:
        if (type(cursor) is not str or re.fullmatch(r'[A-Za-z0-9_=.;:-]{1,4096}', cursor) is None
                or type(timeout) not in (int, float) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or not 0 < timeout <= 600):
            raise ValueError('invalid journal stream request')
        process = subprocess.Popen(
            ['journalctl', '-b', '--no-pager', '--after-cursor', cursor,
             '-o', 'json', '--output-fields=MESSAGE', '--all'],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            start_new_session=True)
        if process.stdout is None or process.stderr is None:
            raise RuntimeError('journal stream pipes unavailable')
        streams = {process.stdout.fileno(): ('stdout', bytearray()),
                   process.stderr.fileno(): ('stderr', bytearray())}
        for descriptor in streams:
            os.set_blocking(descriptor, False)
        deadline = time.monotonic() + timeout
        records = avcs = stderr_bytes = 0
        with selectors.DefaultSelector() as poller:
            for descriptor in streams:
                poller.register(descriptor, selectors.EVENT_READ)
            while poller.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise subprocess.TimeoutExpired('journalctl', timeout)
                for key, _mask in poller.select(min(1.0, remaining)):
                    descriptor = key.fd
                    try:
                        chunk = os.read(descriptor, JOURNAL_READ_SIZE)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        poller.unregister(descriptor)
                        continue
                    kind, buffer = streams[descriptor]
                    if kind == 'stderr':
                        stderr_bytes += len(chunk)
                        if stderr_bytes > JOURNAL_STDERR_LIMIT:
                            raise ValueError('journal stderr exceeded bound')
                        continue
                    buffer.extend(chunk)
                    while b'\n' in buffer:
                        line, _, remainder = buffer.partition(b'\n')
                        buffer[:] = remainder
                        if len(line) > JOURNAL_LINE_LIMIT:
                            raise ValueError('journal record exceeded bound')
                        if not line:
                            continue
                        records += 1
                        if records > JOURNAL_RECORD_LIMIT:
                            raise ValueError('journal record count exceeded bound')
                        record = json.loads(
                            line.decode('utf-8'), object_pairs_hook=_unique_json_object,
                            parse_constant=_invalid_json_constant)
                        if type(record) is not dict:
                            raise ValueError('journal record is not an object')
                        message = record.get('MESSAGE', '')
                        if type(message) is list:
                            if (len(message) > JOURNAL_LINE_LIMIT
                                    or any(type(value) is not int or not 0 <= value <= 255
                                           for value in message)):
                                raise ValueError('invalid binary journal message')
                            message = bytes(message).decode(errors='replace')
                        if type(message) is not str:
                            raise ValueError('invalid journal message')
                        if len(message.encode('utf-8')) > JOURNAL_LINE_LIMIT:
                            raise ValueError('journal message exceeded bound')
                        if AVC.search(message):
                            avcs += 1
                    if len(buffer) > JOURNAL_LINE_LIMIT:
                        raise ValueError('journal record exceeded bound')
        if streams[process.stdout.fileno()][1]:
            raise ValueError('unterminated journal record')
        remaining = deadline - time.monotonic()
        if remaining <= 0 or process.wait(timeout=remaining) != 0:
            raise RuntimeError('journalctl failed')
        return dict(records=records, avcs=avcs)
    except (OSError, ValueError, TypeError, UnicodeError, subprocess.SubprocessError, RuntimeError):
        raise RuntimeError('journal stream validation failed') from None
    finally:
        if process is not None:
            # The journalctl leader may exit while an inherited pipe is held by
            # a descendant. The process group is ours because Popen created a
            # new session; always terminate that owned group before returning.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            cleanup_deadline = time.monotonic() + 5
            try:
                process.wait(timeout=5)
            except (OSError, subprocess.SubprocessError):
                pass
            group_live = True
            while time.monotonic() < cleanup_deadline:
                group_live = False
                for member in Path('/proc').glob('[0-9]*'):
                    try:
                        fields = member.joinpath('stat').read_text().rpartition(')')[2].split()
                    except FileNotFoundError:
                        continue
                    except (OSError, UnicodeError):
                        group_live = True
                        break
                    if len(fields) < 3:
                        group_live = True
                        break
                    try:
                        member_group = int(fields[2])
                    except ValueError:
                        group_live = True
                        break
                    if member_group == process.pid and fields[0] not in ('Z', 'X'):
                        group_live = True
                        break
                if not group_live:
                    break
                time.sleep(.01)
            for stream in (process.stdout, process.stderr):
                if stream is not None:
                    try:
                        stream.close()
                    except OSError:
                        pass
            if group_live:
                raise RuntimeError('journal stream validation failed')


# BEGIN STREAMING_AUDIT_FILE_VERIFICATION
def verify_security(before, after, journal_avcs, audit_summary):
    require(before['selinux'] == after['selinux'] == 'Enforcing', 'SELinux must remain Enforcing')
    require(after['audit']['enabled'] == before['audit']['enabled'], 'kernel audit mode changed during checks')
    require(after['audit']['lost'] == before['audit']['lost'], 'audit records were lost during checks')
    require(type(journal_avcs) is int and journal_avcs >= 0, 'invalid journal AVC projection')
    require(type(audit_summary) is dict and set(audit_summary) == {'bytes','records','sha256','avcs'}
            and all(type(audit_summary[key]) is int and audit_summary[key] >= 0
                    for key in ('bytes','records','avcs'))
            and re.fullmatch('[0-9a-f]{64}', audit_summary['sha256']), 'invalid audit interval summary')
    require(journal_avcs + audit_summary['avcs'] == 0, 'new AVC requires investigation')
    return dict(selinux=after['selinux'], audit=after['audit'], observed_new_avcs=0,
                audit_interval={key:audit_summary[key] for key in ('bytes','records','sha256')},
                audit_enabled=after['audit']['enabled'] in (1,2),
                scope='journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit')
# END STREAMING_AUDIT_FILE_VERIFICATION


# BEGIN STREAMING_AUDIT_FILE_SCANNER
def scan_audit_interval(stream, byte_count):
    """Scan an exact bounded file interval without retaining its record text."""
    require(type(byte_count) is int and 0 <= byte_count <= AUDIT_TOTAL_LIMIT,
            'audit interval total byte bound exceeded')
    digestor = hashlib.sha256()
    pending = bytearray()
    scanned = records = avcs = 0

    def record(line):
        nonlocal records, avcs
        require(len(line) <= AUDIT_LINE_LIMIT, 'audit record exceeded line bound')
        records += 1
        require(records <= AUDIT_RECORD_LIMIT, 'audit record count exceeded bound')
        if AUDIT_AVC.search(line):
            avcs += 1

    while scanned < byte_count:
        chunk = stream.read(min(AUDIT_READ_SIZE, byte_count - scanned))
        require(type(chunk) is bytes and chunk, 'audit interval ended before declared byte count')
        require(len(chunk) <= byte_count - scanned, 'audit interval reader exceeded declared byte count')
        scanned += len(chunk)
        digestor.update(chunk)
        pending.extend(chunk)
        while True:
            newline = pending.find(b'\n')
            if newline < 0:
                break
            record(bytes(pending[:newline]))
            del pending[:newline + 1]
        require(len(pending) <= AUDIT_LINE_LIMIT, 'audit record exceeded line bound')
    if pending:
        record(bytes(pending))
    return dict(bytes=scanned, records=records, sha256=digestor.hexdigest(), avcs=avcs)
# END STREAMING_AUDIT_FILE_SCANNER


class SecurityInterval:
    def __init__(self):
        self.before = self.state()
        journal = execute(['journalctl', '-b', '--no-pager', '-n', '1', '-o', 'json'])[1]
        entries = [json.loads(line) for line in journal.splitlines() if line]
        require(len(entries) == 1 and entries[0].get('__CURSOR'), 'journal cursor unavailable')
        self.cursor = entries[0]['__CURSOR']
        self.audit_file = Path('/var/log/audit/audit.log')
        self.audit_offset = None
        if self.audit_file.exists():
            info = self.audit_file.stat()
            self.audit_offset = (info.st_dev, info.st_ino, info.st_size)

    @staticmethod
    def state():
        return dict(selinux=execute(['getenforce'])[1],
                    audit=parse_audit_status(execute(['auditctl', '-s'])[1]))

    # BEGIN STREAMING_AUDIT_FILE_FINISH
    def finish(self):
        after = self.state()
        journal = journal_avc_count(self.cursor, timeout=60)
        audit_summary = dict(bytes=0, records=0, sha256=hashlib.sha256(b'').hexdigest(), avcs=0)
        if self.audit_offset:
            info = self.audit_file.stat()
            dev, ino, offset = self.audit_offset
            require((info.st_dev, info.st_ino) == (dev, ino) and info.st_size >= offset,
                    'audit log rotated/truncated; interval must be reviewed separately')
            with self.audit_file.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                require((opened.st_dev, opened.st_ino) == (dev, ino) and opened.st_size >= info.st_size,
                        'audit log rotated/truncated; interval must be reviewed separately')
                stream.seek(offset)
                audit_summary = scan_audit_interval(stream, info.st_size - offset)
        elif self.audit_file.exists():
            # The new file may include records not forwarded to the journal.
            info = self.audit_file.stat()
            with self.audit_file.open('rb') as stream:
                opened = os.fstat(stream.fileno())
                require((opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino)
                        and opened.st_size >= info.st_size,
                        'audit log rotated/truncated; interval must be reviewed separately')
                audit_summary = scan_audit_interval(stream, info.st_size)
        return verify_security(self.before, after, journal['avcs'], audit_summary)
    # END STREAMING_AUDIT_FILE_FINISH

def discover_desktop():
    """Actual login environment, including post-exec Mango IPC and Xwayland DISPLAY."""
    sessions = []
    fields = ('PATH', 'XDG_DATA_DIRS', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME',
              'DISPLAY', 'XAUTHORITY', 'LANG', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_ID',
              'QT_QPA_PLATFORM', 'GDK_BACKEND', 'GSK_RENDERER', 'MANGO_SOCKET')
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if (proc / 'comm').read_text().strip() != 'mango' or proc.stat().st_uid == 0:
                continue
            user = pwd.getpwuid(proc.stat().st_uid)
            env = dict(x.split('=', 1) for x in (proc / 'environ').read_bytes().decode().split('\0') if '=' in x)
            runtime = Path('/run/user') / str(user.pw_uid)
            displays = [p.name for p in runtime.glob('wayland-*') if p.is_socket()]
            require(len(displays) == 1, 'ambiguous Wayland session')
            children = []
            for child in Path('/proc').glob('[0-9]*'):
                try:
                    if child.stat().st_uid != user.pw_uid:
                        continue
                    child_env = dict(x.split('=', 1) for x in (child/'environ').read_bytes().decode().split('\0') if '=' in x)
                    if child_env.get('XDG_RUNTIME_DIR') == str(runtime) and child_env.get('WAYLAND_DISPLAY') == displays[0]:
                        children.append(child_env)
                except (OSError, UnicodeError):
                    pass
            signatures = {c['MANGO_INSTANCE_SIGNATURE'] for c in [env, *children] if c.get('MANGO_INSTANCE_SIGNATURE')}
            require(len(signatures) == 1, 'ambiguous or absent actual Mango IPC signature')
            for key in ('DISPLAY', 'XAUTHORITY'):
                values = {c[key] for c in children if c.get(key)}
                if key not in env and len(values) == 1:
                    env[key] = values.pop()
            require(env.get('PATH') and env.get('XDG_DATA_DIRS'), 'missing desktop PATH/XDG_DATA_DIRS')
            sessions.append(['runuser', '-u', user.pw_name, '--', 'env',
                f'HOME={user.pw_dir}', f'XDG_RUNTIME_DIR={runtime}', f'WAYLAND_DISPLAY={displays[0]}',
                f'DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus', 'XDG_SESSION_TYPE=wayland',
                'MANGO_INSTANCE_SIGNATURE=' + signatures.pop(),
                *[f'{key}={env[key]}' for key in fields if env.get(key)]])
        except (OSError, UnicodeError):
            pass
    require(len(sessions) == 1, 'requires exactly one non-root Mango desktop')
    return sessions[0]


def guest_guard(stage, explicit):
    require(explicit and stage in ('live', 'installed'), 'explicit disposable guest authorization required')
    require(os.geteuid() == 0 and execute(['systemd-detect-virt'])[1] in ('qemu', 'kvm'),
            'requires root in a disposable QEMU/KVM guest')
    require(execute(['getenforce'])[1] == 'Enforcing', 'SELinux must already be Enforcing')
    live = 'rd.live.image' in Path('/proc/cmdline').read_text().split()
    require(live == (stage == 'live'), 'stage differs from actual boot mode')


def visual_reference_frame():
    """16 distinct flat color cells; diagnostic fixture, no motion-render claim."""
    palette = ((224,24,192),(24,208,48),(24,48,224),(232,208,24),
               (32,208,216),(224,48,32),(120,48,208),(208,128,24),
               (48,128,24),(24,128,176),(176,24,88),(176,176,176),
               (88,176,208),(208,88,152),(120,208,88),(208,208,88))
    return bytes(channel for y in range(120) for x in range(160)
                 for channel in palette[(y//30)*4+x//40])


def visual_reference_stream():
    """Twenty bounded palette frames that keep the actual GL surface damaged.

    A stream of byte-identical frames can advance the libmpv clock without
    causing GTK's GL surface to repaint after a compositor fullscreen resize.
    Alternating every RGB channel by four keeps both deterministic phases well
    inside the unchanged oracle tolerances while requiring real frame damage.
    """
    base=visual_reference_frame()
    pulse=bytes(channel+4 for channel in base)
    require(len(base)==len(pulse)==160*120*3 and all(b-a==4 for a,b in zip(base,pulse)),
            'visual reference pulse differs')
    return b''.join(base if index%2==0 else pulse for index in range(20))


def visual_reference_cadence():
    return dict(schema='arctic-native-visual-cadence-v1',frames=20,frames_per_second=10,
                alternating_rgb_delta=4,changes_every_frame=True,
                oracle_thresholds_unchanged=True,release_acceptance=False)


def visual_capture_geometry(client, monitors):
    """Validate an observed focused client and scale1 SDR monitor before cropping."""
    require(isinstance(client,dict) and client.get('is_focused') is True
            and client.get('is_visible') is True
            and type(client.get('id')) is int and type(client.get('pid')) is int,
            'actual visual capture client is unfocused/unmapped or has invalid identity')
    name=client.get('monitor')
    require(isinstance(name,str) and 0<len(name)<=128,'invalid actual visual monitor name')
    require(isinstance(monitors,dict) and isinstance(monitors.get('monitors'),list),
            'invalid actual visual monitor collection')
    matches=[m for m in monitors['monitors'] if isinstance(m,dict) and m.get('name')==name]
    require(len(matches)==1,'exact player monitor is unobserved/ambiguous')
    monitor=matches[0]
    scale=monitor.get('scale')
    require(type(scale) in (int,float) and math.isfinite(scale) and scale==1
            and monitor.get('is_hdr') is False,
            'visual oracle requires finite numeric scale1 SDR output; other geometry remains open')
    require(all(type(monitor.get(key)) is int for key in ('x','y','width','height'))
            and -32768<=monitor['x']<=32768 and -32768<=monitor['y']<=32768
            and 80<=monitor['width']<=8192 and 60<=monitor['height']<=8192,
            'invalid/unbounded actual monitor coordinates/dimensions')
    geometry={key:client.get(key) for key in ('x','y','width','height')}
    require(all(type(v) is int for v in geometry.values()),'nonintegral/unobserved client geometry')
    x=geometry['x']-monitor['x']; y=geometry['y']-monitor['y']; w=geometry['width']; h=geometry['height']
    require(0<=x and 0<=y and 80<=w<=2048 and 60<=h<=2048
            and x+w<=monitor['width'] and y+h<=monitor['height'] and w*h*3<=LIMIT,
            'owned player client is clipped/too small/unbounded')
    return monitor,geometry,dict(x=x,y=y,width=w,height=h)


def evaluate_reference_rgb(data, width, height, reference):
    """Match actual pixels inside an exact owned client, with a bounded ROI search.

    Candidate origins/scales derive from a connected region of the first unique
    color. All 16 cells then need matching interior pixels; a black pane or a few
    colored UI controls cannot pass. No IPC-state or configuration substitution.
    """
    require(type(width) is int and type(height) is int and 80 <= width <= 2048
            and 60 <= height <= 2048 and len(data) == width*height*3 <= LIMIT,
            'unbounded/malformed actual RGB client frame')
    require(len(reference) == 160*120*3, 'visual reference RGB format differs')
    targets = [tuple(reference[((r*30+15)*160+c*40+20)*3:((r*30+15)*160+c*40+20)*3+3])
               for r in range(4) for c in range(4)]
    palette=visual_reference_frame()
    originals=[tuple(palette[((r*30+15)*160+c*40+20)*3:((r*30+15)*160+c*40+20)*3+3])
               for r in range(4) for c in range(4)]
    require(len(set(targets)) == 16 and all(max(abs(a-b) for a,b in zip(actual,wanted))<=6
            for actual,wanted in zip(targets,originals)), 'decoded reference differs from the exact diagnostic palette')
    def close(pixel, color): return max(abs(pixel[k]-color[k]) for k in range(3)) <= 30
    mask = bytearray(width*height)
    for i in range(width*height):
        offset=i*3
        if close(data[offset:offset+3],targets[0]): mask[i]=1
    boxes=[]
    for i in range(len(mask)):
        if not mask[i]: continue
        mask[i]=0; todo=[i]; count=0; left=width; top=height; right=bottom=0
        while todo:
            point=todo.pop(); x,y=point%width,point//width; count+=1
            left=min(left,x); right=max(right,x); top=min(top,y); bottom=max(bottom,y)
            for next_point in (point-1 if x else -1,point+1 if x+1<width else -1,
                               point-width if y else -1,point+width if y+1<height else -1):
                if next_point>=0 and mask[next_point]: mask[next_point]=0; todo.append(next_point)
        if count>=100 and right-left+1>=10 and bottom-top+1>=8:
            boxes.append((left,top,right-left+1,bottom-top+1,count))
            require(len(boxes)<=64,'visual ROI candidates exceed bound')
    tested=0
    for left,top,cell_w,cell_h,count in boxes:
        for roi_w in sorted(range(max(80,cell_w*4-12),min(width,cell_w*4+12)+1), key=lambda v:abs(v-cell_w*4)):
            roi_h=round(roi_w*.75)
            if roi_h<60 or roi_h>height or abs(roi_h-cell_h*4)>16: continue
            for x0 in sorted(range(max(0,left-3),min(width-roi_w,left+3)+1), key=lambda v:abs(v-left)):
                for y0 in sorted(range(max(0,top-3),min(height-roi_h,top+3)+1), key=lambda v:abs(v-top)):
                    tested+=1; require(tested<=100000,'visual search exceeds bound')
                    probe=[]
                    for r in range(4):
                        for c in range(4):
                            px=x0+min(roi_w-1,int((c+.5)*roi_w/4)); py=y0+min(roi_h-1,int((r+.5)*roi_h/4))
                            offset=(py*width+px)*3; probe.append(close(data[offset:offset+3],targets[r*4+c]))
                    if not all(probe): continue
                    pixels=bad=error=0
                    for r in range(4):
                        ya=y0+math.ceil((r+.15)*roi_h/4); yb=y0+math.floor((r+.85)*roi_h/4)
                        for c in range(4):
                            xa=x0+math.ceil((c+.15)*roi_w/4); xb=x0+math.floor((c+.85)*roi_w/4)
                            color=targets[r*4+c]
                            for y in range(ya,yb):
                                for x in range(xa,xb):
                                    offset=(y*width+x)*3; delta=[abs(data[offset+k]-color[k]) for k in range(3)]
                                    pixels+=1; bad+=max(delta)>30; error+=sum(delta)
                    if pixels>=2000 and bad/pixels<=.01 and error/(pixels*3)<=15:
                        return dict(status='matched',roi_client_pixels=dict(x=x0,y=y0,width=roi_w,height=roi_h),
                                    reference_size=[160,120],scale=[roi_w/160,roi_h/120],
                                    checked_interior_pixels=pixels,mismatched_pixels=bad,
                                    mean_channel_error=error/(pixels*3),channel_tolerance=30,
                                    maximum_bad_fraction=.01,maximum_mean_error=15,minimum_checked_pixels=2000,
                                    candidate_color_components=len(boxes),tested_candidates=tested,
                                    scope='deterministic static fixture content only; no motion/perceived audio/hardware claim')
    return dict(status='unmatched',candidate_color_components=len(boxes),tested_candidates=tested,
                reason='No bounded 16-color reference ROI with sufficient matching visible content')


# BEGIN NATIVE_PROTOCOL_DIAGNOSTICS
class NativeProtocolProjection:
    """Closed numeric projection of one client stderr stream, never raw text.

    These are client-side requests/events, not proof that a compositor displayed
    a buffer. A unique xdg root is structural; GTK GLArea identity remains open.
    """
    MAX_INPUT = 1024 * 1024
    MAX_LINE = 2048
    MAX_RECORDS = 512
    INTERFACES = {'wl_compositor', 'wl_subcompositor', 'xdg_wm_base',
                  'wp_viewporter', 'wl_shm', 'zwp_linux_dmabuf_v1'}
    HEADER = re.compile(r'^\[(?:\s*[0-9]{1,12}\.[0-9]{1,6}|'
                        r'(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{6})\]\s*'
                        r'(?:\{[^{}\r\n]{1,80}\}\s*)?'
                        r'(?P<send>->\s*)?(?P<iface>[a-z][a-z0-9_]{0,63})[@#](?P<id>[0-9]{1,8})\.'
                        r'(?P<op>[a-z_]{1,64})\((?P<args>[^\r\n]*)\)$')
    def __init__(self):
        self.objects = {1:'wl_display'}
        self.surfaces, self.xdg, self.toplevels, self.children = {}, {}, {}, {}
        self.viewports, self.buffers, self.pools = {}, {}, {}
        self.records = []
        self.rejected = self.capped = False
        self.input_bytes = self.omitted = 0

    @staticmethod
    def number(text, low=0, high=1048576):
        if not re.fullmatch(r'-?[0-9]{1,10}', text): raise ValueError()
        value=int(text)
        if not low<=value<=high: raise ValueError()
        return value

    def object(self, text, interface, new=False):
        match=re.fullmatch(r'(?:new id )?([a-z][a-z0-9_]{0,63}|\[unknown\])[@#]([0-9]{1,8})',text)
        if not match or match[1] not in (interface,'[unknown]'): raise ValueError()
        value=self.number(match[2],2)
        if new:
            if len(self.objects)>=1024: self.capped=True; raise ValueError()
            if not text.startswith('new id ') or value in self.objects: raise ValueError()
            self.objects[value]=interface
        elif self.objects.get(value)!=interface: raise ValueError()
        return value

    def feed(self, line):
        self.input_bytes+=len(line)
        if self.input_bytes>self.MAX_INPUT or len(line)>self.MAX_LINE:
            self.capped=True; return
        if self.rejected or self.capped: return
        try:
            text=line.decode('ascii').rstrip('\n')
        except UnicodeDecodeError:
            self.omitted+=1; return
        match=self.HEADER.fullmatch(text)
        if not match:
            self.omitted+=1; return
        iface,op=match['iface'],match['op']; args=match['args']; send=bool(match['send'])
        key=(iface,op)
        selected={('wl_display','get_registry'),('wl_registry','bind'),('wl_compositor','create_surface'),
            ('wl_subcompositor','get_subsurface'),('xdg_wm_base','get_xdg_surface'),('xdg_surface','get_toplevel'),
            ('xdg_toplevel','configure'),('xdg_surface','configure'),('xdg_surface','ack_configure'),
            ('wl_surface','attach'),('wl_surface','commit'),('wl_surface','set_buffer_scale'),
            ('wl_surface','set_buffer_transform'),('wp_viewporter','get_viewport'),('wp_viewport','set_source'),
            ('wp_viewport','set_destination'),('wl_subsurface','set_position'),('wl_subsurface','set_sync'),
            ('wl_subsurface','set_desync'),('wl_shm','create_pool'),('wl_shm_pool','create_buffer'),
            ('zwp_linux_dmabuf_v1','create_params'),('zwp_linux_buffer_params_v1','create_immed')}
        if key not in selected:
            # Account for opaque new objects without exporting their names.
            for match_id in re.finditer(r'new id (?:[a-z][a-z0-9_]{0,63}|\[unknown\])[@#]([0-9]{1,8})',args):
                value=int(match_id[1])
                if not 2<=value<=1048576 or value in self.objects: self.rejected=True; return
                if len(self.objects)>=1024: self.capped=True; return
                self.objects[value]='unsupported'
            self.omitted+=1; return
        try:
            receiver=self.number(match['id'],1)
            if self.objects.get(receiver)!=iface: raise ValueError()
            event=key in {('xdg_toplevel','configure'),('xdg_surface','configure')}
            if send==event: raise ValueError()
            values=args.split(', ') if args else []
            row=dict(interface=iface,object_id=receiver,operation=op,direction='request' if send else 'event')
            if key==('wl_display','get_registry'):
                if len(values)!=1 or any(v=='wl_registry' for v in self.objects.values()): raise ValueError()
                row['created_id']=self.object(values[0],'wl_registry',True)
            elif key==('wl_registry','bind'):
                if len(values)!=4: raise ValueError()
                interface=values[1][1:-1] if re.fullmatch(r'"[a-z][a-z0-9_]{0,63}"',values[1]) else None
                if interface not in self.INTERFACES:
                    match_id=re.fullmatch(r'new id (?:[a-z][a-z0-9_]{0,63}|\[unknown\])[@#]([0-9]{1,8})',values[3])
                    if not match_id: raise ValueError()
                    opaque=self.number(match_id[1],2)
                    if len(self.objects)>=1024: self.capped=True; raise ValueError()
                    if opaque in self.objects: raise ValueError()
                    self.objects[opaque]='unsupported'
                    self.omitted+=1; return
                row.update(global_id=self.number(values[0],1),version=self.number(values[2],1,64),
                           created_id=self.object(values[3],interface,True),bound_interface=interface)
            elif key==('wl_compositor','create_surface'):
                if len(values)!=1 or len(self.surfaces)>=64: raise ValueError()
                surface=self.object(values[0],'wl_surface',True); self.surfaces[surface]={}
                row['created_id']=surface
            elif key==('xdg_wm_base','get_xdg_surface'):
                if len(values)!=2: raise ValueError()
                surface=self.object(values[1],'wl_surface'); child=self.object(values[0],'xdg_surface',True)
                if surface in self.xdg.values() or surface in self.children: raise ValueError()
                self.xdg[child]=surface; row.update(created_id=child,surface_id=surface)
            elif key==('xdg_surface','get_toplevel'):
                if len(values)!=1 or receiver not in self.xdg: raise ValueError()
                if self.xdg[receiver] in self.toplevels.values(): raise ValueError()
                top=self.object(values[0],'xdg_toplevel',True); self.toplevels[top]=self.xdg[receiver]
                row.update(created_id=top,surface_id=self.xdg[receiver])
            elif key==('wl_subcompositor','get_subsurface'):
                if len(values)!=3: raise ValueError()
                child=self.object(values[1],'wl_surface'); parent=self.object(values[2],'wl_surface')
                if child==parent or child in self.children or child in self.xdg.values(): raise ValueError()
                # Reject loops and ambiguity, never identify a video widget by guess.
                cursor=parent
                for _ in range(64):
                    if cursor==child: raise ValueError()
                    if cursor not in self.children: break
                    cursor=self.children[cursor]['parent_id']
                else: raise ValueError()
                sub=self.object(values[0],'wl_subsurface',True)
                self.children[child]={'parent_id':parent,'subsurface_id':sub}
                row.update(created_id=sub,surface_id=child,parent_id=parent)
            elif key in {('xdg_surface','configure'),('xdg_surface','ack_configure')}:
                if len(values)!=1 or receiver not in self.xdg: raise ValueError()
                serial=self.number(values[0],1,4294967295); surface=self.xdg[receiver]
                if serial==self.surfaces[surface].get('configure_serial') and op=='configure': raise ValueError()
                if op=='ack_configure' and serial!=self.surfaces[surface].get('configure_serial'): raise ValueError()
                self.surfaces[surface]['configure_serial' if op=='configure' else 'ack_serial']=serial
                row.update(surface_id=surface,serial=serial)
            elif key==('xdg_toplevel','configure'):
                if len(values)!=3 or not re.fullmatch(r'array\[[0-9]{1,4}\]',values[2]): raise ValueError()
                surface=self.toplevels[receiver]; w=self.number(values[0],0,16384); h=self.number(values[1],0,16384)
                self.surfaces[surface]['requested_size']=[w,h]; row.update(surface_id=surface,width=w,height=h)
            elif key==('wp_viewporter','get_viewport'):
                if len(values)!=2: raise ValueError()
                surface=self.object(values[1],'wl_surface')
                if surface in self.viewports.values(): raise ValueError()
                viewport=self.object(values[0],'wp_viewport',True); self.viewports[viewport]=surface
                row.update(created_id=viewport,surface_id=surface)
            elif iface=='wp_viewport':
                surface=self.viewports[receiver]
                if op=='set_destination':
                    if len(values)!=2: raise ValueError()
                    pair=[self.number(v,-1,16384) for v in values]
                    if pair!=[-1,-1] and min(pair)<1: raise ValueError()
                    self.surfaces[surface]['viewport_destination']=pair; row.update(surface_id=surface,dimensions=pair)
                else:
                    if len(values)!=4 or any(not re.fullmatch(r'-?[0-9]{1,6}(?:\.[0-9]{1,8})?',v) for v in values): raise ValueError()
                    box=[float(v) for v in values]
                    if any(not math.isfinite(v) or not -1<=v<=16384 for v in box): raise ValueError()
                    if box!=[-1.0]*4 and (min(box[:2])<0 or min(box[2:])<=0): raise ValueError()
                    self.surfaces[surface]['viewport_source']=box; row.update(surface_id=surface,rectangle=box)
            elif iface=='wl_subsurface':
                matches=[s for s,v in self.children.items() if v['subsurface_id']==receiver]
                if len(matches)!=1: raise ValueError()
                surface=matches[0]; row['surface_id']=surface
                if op=='set_position':
                    if len(values)!=2: raise ValueError()
                    pair=[self.number(v,-32768,32768) for v in values]
                    self.surfaces[surface]['position']=pair; row['position']=pair
                else:
                    if values: raise ValueError()
                    self.surfaces[surface]['synchronized']=op=='set_sync'
            elif key==('wl_shm','create_pool'):
                if len(values)!=3 or not re.fullmatch(r'fd [0-9]{1,8}|[0-9]{1,8}',values[1]): raise ValueError()
                pool=self.object(values[0],'wl_shm_pool',True); size=self.number(values[2],1,268435456)
                self.pools[pool]=size; row.update(created_id=pool,pool_bytes=size)
            elif key==('wl_shm_pool','create_buffer'):
                if len(values)!=6: raise ValueError()
                buf=self.object(values[0],'wl_buffer',True)
                offset,w,h,stride,fmt=[self.number(v,0,4294967295) for v in values[1:]]
                if not 1<=w<=16384 or not 1<=h<=16384 or not w<=stride<=262144 or offset+stride*h>self.pools[receiver]: raise ValueError()
                if fmt in (0,1) and stride<w*4: raise ValueError()
                self.buffers[buf]=dict(width=w,height=h,stride=stride,format=fmt,transport='shm')
                row.update(created_id=buf,**self.buffers[buf])
            elif key==('zwp_linux_dmabuf_v1','create_params'):
                if len(values)!=1: raise ValueError()
                row['created_id']=self.object(values[0],'zwp_linux_buffer_params_v1',True)
            elif key==('zwp_linux_buffer_params_v1','create_immed'):
                if len(values)!=5: raise ValueError()
                buf=self.object(values[0],'wl_buffer',True); w,h,fmt,flags=[self.number(v,0,4294967295) for v in values[1:]]
                if not 1<=w<=16384 or not 1<=h<=16384: raise ValueError()
                self.buffers[buf]=dict(width=w,height=h,format=fmt,transport='dmabuf',plane_stride_observed=False)
                row.update(created_id=buf,**self.buffers[buf])
            elif iface=='wl_surface':
                surface=self.surfaces[receiver]; row['surface_id']=receiver
                if op=='attach':
                    if len(values)!=3: raise ValueError()
                    buf=None if values[0]=='nil' else self.object(values[0],'wl_buffer')
                    surface.update(buffer_id=buf,attach_offset=[self.number(v,-32768,32768) for v in values[1:]])
                    row.update(buffer_id=buf,attach_offset=surface['attach_offset'])
                elif op=='set_buffer_scale':
                    if len(values)!=1: raise ValueError()
                    surface['buffer_scale']=self.number(values[0],1,16); row['scale']=surface['buffer_scale']
                elif op=='set_buffer_transform':
                    if len(values)!=1: raise ValueError()
                    surface['buffer_transform']=self.number(values[0],0,7); row['transform']=surface['buffer_transform']
                elif op=='commit':
                    if values: raise ValueError()
                    row['client_transaction']=dict(surface)
            if len(self.records)>=self.MAX_RECORDS: self.capped=True; return
            self.records.append(row)
        except (ValueError,KeyError,IndexError,OverflowError):
            self.rejected=True

    def snapshot(self):
        roots=sorted(set(self.toplevels.values()))
        status='rejected' if self.rejected else 'incomplete' if self.capped else 'observed' if len(roots)==1 else 'unknown'
        return dict(status=status,records=list(self.records),input_bytes=self.input_bytes,
                    omitted_lines=self.omitted,unique_xdg_root_id=roots[0] if len(roots)==1 else None,
                    structural_surfaces=[dict(surface_id=s,**v,**self.children.get(s,{})) for s,v in sorted(self.surfaces.items())],
                    video_surface_identified=False,compositor_commit_or_display_proven=False)


class NativeRendererProjection:
    """GTK 4.22.5 successful realization messages; no arbitrary log export.

    gsk_renderer_new_for_surface_full emits this literal only after successful
    realization, through gdk_debug_message's unprefixed stderr line. A requested
    environment variable alone is never a renderer observation. The message
    identifies a GSK toplevel renderer, not GtkGLArea or an mpv framebuffer.
    """
    LINE=re.compile(rb"Using renderer '(GskGLRenderer|GskVulkanRenderer|GskCairoRenderer)' for surface 'GdkWaylandToplevel'\n")
    TYPES={b'GskGLRenderer':'gl',b'GskVulkanRenderer':'vulkan',b'GskCairoRenderer':'cairo'}
    MAX_BYTES=256*1024
    def __init__(self):
        self.types=set(); self.messages=0; self.bytes=0; self.capped=False
    def feed(self,line):
        if type(line) is not bytes: return
        self.bytes+=len(line)
        if self.bytes>self.MAX_BYTES:
            self.capped=True; return
        if len(line)>256: return
        match=self.LINE.fullmatch(line)
        if match:
            if self.messages>=16: self.capped=True; return
            self.types.add(self.TYPES[match[1]]); self.messages+=1
    def snapshot(self):
        observed=len(self.types)==1 and not self.capped
        return dict(status='reported-realized' if observed else 'unknown',
                    renderer=next(iter(self.types)) if observed else None,
                    message_count=self.messages,capped=self.capped,
                    gtk_source_version='4.22.5',surface_kind='wayland-toplevel',
                    video_widget_or_framebuffer_attested=False,release_acceptance=False)


class NativeProtocolDrain:
    """One bounded private capture; drain excess until original app cleanup.

    No raw file is inside the guest export tree. A descriptor identity, actual
    app fd2 and start-ticks bind the stream; wrapper PID is never app ownership.
    """
    RAW_CAP=256*1024
    def __init__(self,renderer=False):
        self.stream=None; self.projection=NativeProtocolProjection(); self.lock=threading.Lock()
        self.renderer=NativeRendererProjection() if renderer is True else None
        self.stop=threading.Event(); self.eof=False; self.failed=False; self.partial=False
        self.pending_bytes=0; self.timed_out=False
        self.binding=None; self.raw_bytes=0; self.raw_fd=None
        private=Path(tempfile.mkdtemp(prefix='arctic-native-protocol-private-',dir='/tmp'))
        self.raw_path=private/'stderr.private'
        directory=os.open(private,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            info=os.fstat(directory)
            if info.st_uid!=os.geteuid() or info.st_mode&0o077:
                raise RuntimeError('private protocol directory identity differs')
            self.raw_fd=os.open('stderr.private',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=directory)
        finally: os.close(directory)
        info=os.fstat(self.raw_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_nlink!=1 or info.st_mode&0o077:
            self._close_capture(); raise RuntimeError('private protocol file identity differs')
        self.thread=None

    def _close_capture(self):
        # One owner may close repeatedly after setup failure or normal EOF.
        descriptor=self.raw_fd; self.raw_fd=None
        if descriptor is not None:
            try: os.close(descriptor)
            except OSError: self.failed=True
        if self.stream is not None:
            try: self.stream.close()
            except OSError: self.failed=True

    def start(self,stream):
        self.stream=stream
        self.thread=threading.Thread(target=self._drain,daemon=True)
        try: self.thread.start()
        except Exception:
            self.failed=True; self.thread=None; self._close_capture()
            raise RuntimeError('owned protocol drainage unavailable') from None

    def _drain(self):
        pending=b''; deadline=time.monotonic()+300
        try:
            os.set_blocking(self.stream.fileno(),False)
            with selectors.DefaultSelector() as selector:
                selector.register(self.stream,selectors.EVENT_READ)
                while not self.stop.is_set() and time.monotonic()<deadline:
                    if not selector.select(.1): continue
                    block=os.read(self.stream.fileno(),4096)
                    if not block: self.eof=True; break
                    with self.lock:
                        kept=block[:max(0,self.RAW_CAP-self.raw_bytes)]
                        if kept:
                            offset=0
                            while offset<len(kept):
                                count=os.write(self.raw_fd,kept[offset:])
                                if count<=0: raise OSError()
                                offset+=count
                            self.raw_bytes+=len(kept)
                        pending+=block
                        while b'\n' in pending:
                            line,pending=pending.split(b'\n',1); self.projection.feed(line+b'\n')
                            if self.renderer is not None: self.renderer.feed(line+b'\n')
                        if len(pending)>self.projection.MAX_LINE:
                            self.projection.capped=True; pending=b''
                        self.pending_bytes=len(pending)
                if pending: self.partial=True
                if not self.eof and not self.stop.is_set(): self.timed_out=True
        except (OSError,ValueError): self.failed=True
        finally:
            self._close_capture()

    def bind(self,proof,uid):
        try:
            current=identity(proof['pid'],uid)
            if any(current[k]!=proof[k] for k in ('pid','start_ticks','executable')): return False
            if digest(current['executable'])!=proof['executable_sha256']: return False
            pipe=os.fstat(self.stream.fileno()); actual=os.stat(Path('/proc')/str(proof['pid'])/'fd/2')
            if not stat.S_ISFIFO(pipe.st_mode) or (pipe.st_dev,pipe.st_ino)!=(actual.st_dev,actual.st_ino): return False
            self.binding={k:proof[k] for k in ('pid','start_ticks','executable_sha256')}
            self.binding.update(uid=uid,client_id=int(proof['client_id']),pipe_device=pipe.st_dev,pipe_inode=pipe.st_ino)
            return True
        except (OSError,ValueError,KeyError,RuntimeError): return False

    def snapshot(self,proof,uid):
        matched=self.bind(proof,uid)
        with self.lock:
            value=self.projection.snapshot()
        value.update(owner=self.binding if matched else None,ownership_verified=matched,
                     private_raw_bytes=self.raw_bytes,drain_failed=self.failed,partial_line=self.partial or self.pending_bytes>0,
                     private_raw_truncated=self.raw_bytes>=self.RAW_CAP,time_cap_reached=self.timed_out,
                     input_complete=self.eof,private_raw_exported=False,release_acceptance=False,
                     scope='owned client protocol observations only; GTK GLArea/framebuffer identity remains unknown')
        value['protocol_sender_authenticated']=False
        value['exclusive_stderr_writer_proven']=False
        if not matched or self.failed or self.partial or self.pending_bytes: value['status']='unknown'
        elif self.timed_out: value['status']='incomplete'
        if not matched:
            value.update(records=[],structural_surfaces=[],unique_xdg_root_id=None)
        if self.renderer is not None:
            with self.lock: realized=self.renderer.snapshot()
            if not matched or self.failed or self.timed_out:
                realized.update(status='unknown',renderer=None)
            realized.update(owned_stderr_binding_verified=matched,
                            exclusive_writer_proven=False,environment_request_is_not_attestation=True)
            value['realized_renderer']=realized
        return value

    def finish(self):
        self.stop.set()
        if self.thread is not None: self.thread.join(timeout=1)
        else: self._close_capture()
# END NATIVE_PROTOCOL_DIAGNOSTICS


def rename_noreplace(source_directory,source_name,target_directory,target_name):
    """Atomically quarantine one directory entry without replacing another."""
    import ctypes
    import errno
    require(all(type(value) is int and value>=0 for value in (source_directory,target_directory))
            and all(isinstance(name,str) and name and '/' not in name and name not in ('.','..')
                    for name in (source_name,target_name)),
            'invalid atomic quarantine request')
    libc=ctypes.CDLL(None,use_errno=True)
    operation=libc.renameat2
    operation.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
    operation.restype=ctypes.c_int
    if operation(source_directory,os.fsencode(source_name),target_directory,
                 os.fsencode(target_name),1)==0:  # RENAME_NOREPLACE
        return
    code=ctypes.get_errno()
    if code==errno.ENOENT: raise FileNotFoundError(code,os.strerror(code))
    if code==errno.EEXIST: raise FileExistsError(code,os.strerror(code))
    raise OSError(code,os.strerror(code))


class Smoke:
    def __init__(self, prefix, stage):
        require(prefix[:2] == ['runuser', '-u'] and prefix[3:5] == ['--', 'env'], 'invalid desktop prefix')
        self.original_prefix = list(prefix)
        self.user = pwd.getpwnam(prefix[2])
        self.uid = self.user.pw_uid
        require(self.uid != 0, 'apps must run as the desktop user')
        self.stage = stage
        self.root = Path(tempfile.mkdtemp(prefix='arctic-native-smoke-', dir='/tmp'))
        os.chown(self.root, self.uid, self.user.pw_gid)
        self.prefix = prefix + [f'HOME={self.root}/home', f'XDG_CONFIG_HOME={self.root}/config',
                               f'XDG_DATA_HOME={self.root}/data', f'XDG_CACHE_HOME={self.root}/cache']
        self.steps, self.gates, self.owned, self.launches = [], [], [], []
        self.trace_bytes = self.trace_omitted = self.client_observations = 0
        self.last_client_digest = None
        self.active_gate = None
        self.capture_count = 0

    def cmd(self, argv, *, original=False, **kwargs):
        prefix = self.original_prefix if original else self.prefix
        result = execute(prefix + argv, **kwargs)
        self.steps.append(dict(argv=argv, returncode=result[0], stdout=result[1][-12000:],
                               stderr=result[2][-12000:]))
        return result

    def gate(self, name, fn):
        self.active_gate = name
        self.trace('gate-begin', gate=name)
        try:
            value = fn()
            self.gates.append(dict(check=name, status='passed', value=value))
            self.trace('gate-passed', gate=name)
            return value
        except Exception as exc:
            self.trace('gate-failed', gate=name, error=str(exc))
            evidence = self.diagnostic('failure-'+name, required=False)
            self.gates.append(dict(check=name, status='failed', detail=str(exc), diagnostic=evidence))
            return None

    def launch(self, argv):
        """GUI command may stay foreground; never turn that into a fake failure."""
        log = self.root / ('gui-launch-'+str(len(self.launches))+'.log')
        with log.open('ab') as stream:
            child = subprocess.Popen(self.prefix+argv, stdout=stream, stderr=stream)
        self.launches.append(child)
        self.steps.append(dict(argv=argv, status='started-asynchronously', log=str(log)))

    def launch_protocol_player(self, argv):
        # Exercise the installed product launcher. The private GTK diagnostic is
        # mandatory because the environment request alone cannot prove realization.
        require(argv[0]=='/usr/libexec/arctic/arctic-celluloid' and getattr(self,'gui_v6',False),
                'native product Celluloid launcher selection differs')
        drain=None; reader=None; writer=None
        try:
            drain=NativeProtocolDrain(renderer=True)
            read,writer=os.pipe()
            try: reader=os.fdopen(read,'rb',buffering=0)
            except BaseException:
                os.close(read); raise
            # Capture setup finishes before the product app is launched.
            drain.start(reader)
        except (OSError,RuntimeError):
            if drain is not None: drain.finish()
            if reader is not None: reader.close()
            if writer is not None: os.close(writer)
            raise RuntimeError('product renderer attestation setup unavailable') from None
        log=self.root/('gui-launch-'+str(len(self.launches))+'.log')
        try:
            with log.open('ab') as stream:
                child=subprocess.Popen(self.prefix+['GSK_DEBUG=renderer','WAYLAND_DEBUG=client']+argv,
                                       stdout=stream,stderr=writer)
        except BaseException:
            drain.finish(); raise
        finally: os.close(writer)
        self.launches.append(child)
        self.steps.append(dict(argv=argv,status='started-asynchronously',log=str(log)))
        self.native_protocol_drain=drain

    def product_launch_contract(self, player, route):
        require(route in ('file-manager-mime','gio-new-window','gio-enqueue','enqueue-target'),
                'Celluloid product launch route differs')
        launcher=Path('/usr/libexec/arctic/arctic-celluloid')
        desktop=Path('/usr/share/arctic/applications/io.github.celluloid_player.Celluloid.desktop')
        require(player['executable']=='/usr/bin/celluloid' and player['is_xwayland'] is False,
                'product launcher did not retain native Wayland upstream Celluloid')
        environ=Path('/proc')/str(player['pid'])/'environ'
        require(environ.stat().st_uid==self.uid,'product renderer process owner differs')
        with environ.open('rb') as stream: raw=stream.read(65537)
        require(len(raw)<=65536,'product renderer environment exceeded bound')
        self.alive(player)
        values=raw.split(b'\0')
        require([x for x in values if x.startswith(b'GSK_RENDERER=')]==[b'GSK_RENDERER=gl'],
                'product renderer request is not exactly gl')
        return dict(schema='arctic-celluloid-product-launch-v1',route=route,
                    launcher=str(launcher),desktop_file=str(desktop),requested_renderer='gl',
                    upstream_executable=player['executable'],native_wayland=True,
                    process={key:player[key] for key in ('pid','start_ticks','executable','executable_sha256','client_id','is_xwayland')},
                    release_acceptance=True)

    def gio_desktop_action(self, action):
        require(action in ('new-window','enqueue'),'unsupported Celluloid desktop action')
        code=('from gi.repository import Gio; import sys; '
              'a=Gio.DesktopAppInfo.new("io.github.celluloid_player.Celluloid.desktop"); '
              'assert a is not None and set(a.list_actions())=={"new-window","enqueue"}; '
              'assert a.get_string("Exec")=="/usr/libexec/arctic/arctic-celluloid %U"; '
              'assert a.get_string("TryExec")=="/usr/bin/celluloid"; '
              'a.launch_action(sys.argv[1],Gio.AppLaunchContext())')
        # The launched app inherits the helper's descriptors. Use the existing
        # regular-file GUI launch path so waiting for the helper cannot wait for
        # the long-lived Celluloid process to close a captured PIPE.
        self.launch(['/usr/bin/python3','-c',code,action])
        helper=self.launches[-1]
        try:
            returncode=helper.wait(timeout=15)
        except subprocess.TimeoutExpired:
            helper.terminate()
            try: helper.wait(timeout=2)
            except subprocess.TimeoutExpired: helper.kill();helper.wait(timeout=2)
            raise RuntimeError('Gio DesktopAppInfo action helper timed out') from None
        self.steps[-1].update(status='launch-helper-completed',returncode=returncode)
        require(returncode==0,'Gio DesktopAppInfo action launch failed')

    def product_renderer_contract(self, player):
        launcher=Path('/usr/libexec/arctic/arctic-celluloid')
        desktop=Path('/usr/share/arctic/applications/io.github.celluloid_player.Celluloid.desktop')
        for path,mode in ((launcher,0o111),(desktop,0)):
            info=path.stat()
            require(info.st_uid==0 and stat.S_ISREG(info.st_mode) and not info.st_mode&0o022
                    and (not mode or info.st_mode&mode), 'Celluloid product launch file identity differs')
        text=desktop.read_text()
        require('Exec=/usr/libexec/arctic/arctic-celluloid %U\n' in text
                and 'TryExec=/usr/bin/celluloid\n' in text
                and 'DBusActivatable=false\n' in text
                and text.count('Exec=/usr/libexec/arctic/arctic-celluloid')==3,
                'Celluloid desktop/MIME/action launch contract differs')
        require(player['executable']=='/usr/bin/celluloid' and player['is_xwayland'] is False,
                'product launcher did not retain native Wayland upstream Celluloid')
        environ=Path('/proc')/str(player['pid'])/'environ'
        require(environ.stat().st_uid==self.uid,'product renderer process owner differs')
        with environ.open('rb') as stream: raw=stream.read(65537)
        require(len(raw)<=65536,'product renderer environment exceeded bound')
        values=raw.split(b'\0')
        require([x for x in values if x.startswith(b'GSK_RENDERER=')]==[b'GSK_RENDERER=gl'],
                'product renderer request is not exactly gl')
        def realized():
            proof=self.native_protocol_drain.snapshot(player,self.uid)
            renderer=proof.get('realized_renderer',{})
            if renderer.get('status')=='reported-realized':
                require(renderer.get('renderer')=='gl','GTK realized a renderer other than requested GL')
                return proof
            return None
        proof=self.wait(realized,10,'owned GTK GL renderer realization')
        return dict(schema='arctic-celluloid-product-renderer-v1',launcher=str(launcher),
                    desktop_file=str(desktop),requested_renderer='gl',realized_renderer='gl',
                    upstream_executable=player['executable'],native_wayland=True,
                    user_override_policy='an explicitly set GSK_RENDERER is preserved by the launcher',
                    protocol=proof,release_acceptance=True)

    def native_protocol_diagnostic(self, player, state, screenshot, client):
        value=dict(schema='arctic-native-owned-protocol-viewport-v1',stage=self.stage if self.stage in ('live','installed') else 'unknown',
                   observed_monotonic_ns=time.monotonic_ns(),
                   release_acceptance=False,video_widget_and_framebuffer_dimensions=None,rendering_cause_proven=False)
        try:
            sha=screenshot['sha256']
            if not isinstance(sha,str) or not re.fullmatch('[0-9a-f]{64}',sha): raise ValueError()
            value['primary_screenshot_sha256']=sha
            value['checker_sha256']=digest(Path(__file__))
            if (any(type(client.get(k)) is not int for k in ('id','pid','x','y','width','height'))
                    or type(client.get('is_fullscreen')) is not bool
                    or not 1<=client['width']<=16384 or not 1<=client['height']<=16384
                    or not all(-32768<=client[k]<=32768 for k in ('x','y'))): raise ValueError()
            if client['pid']!=player['pid'] or client['id']!=int(player['client_id']): raise ValueError()
            value['primary_capture_intended_geometry']={k:client[k] for k in ('id','pid','x','y','width','height','is_fullscreen')}
            value['geometry_scope']='existing owned client snapshot immediately before primary PNG; protocol prefix sampled after unchanged oracle'
            value['protocol']=self.native_protocol_drain.snapshot(player,self.uid)
            params=state.get('video-params',{})
            value['decoded_video_dimensions']={k:params[k] for k in ('w','h')
                 if type(params.get(k)) is int and 1<=params[k]<=16384}
            value['optional_mpv_output_and_osd_dimensions']='not_collected'
        except Exception:
            value['protocol']=dict(status='unknown',ownership_verified=False,release_acceptance=False)
        # One exclusive regular typed projection, not an app-controlled log.
        try:
            data=(json.dumps(value,sort_keys=True)+'\n').encode()
            if len(data)>256*1024: return
            directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
            try:
                info=os.fstat(directory)
                if info.st_uid!=self.uid: return
                descriptor=os.open('0-native-protocol-viewport.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                                   0o600,dir_fd=directory)
                with os.fdopen(descriptor,'wb') as stream: stream.write(data)
            finally: os.close(directory)
        except (OSError,ValueError):
            # No arbitrary exception text or diagnostic failure replaces the gate.
            pass

    def finish_native_protocol(self):
        drain=getattr(self,'native_protocol_drain',None)
        if drain is not None:
            try: drain.finish()
            except Exception: pass

    def controlled_renderer_trials(self,fixture,expected,source_sha,primary):
        """Failure-only diagnostics. Primary oracle/error and overall FAIL stand."""
        rows=[dict(intervention=mode,status='unrun',release_acceptance=False)
              for mode in ('default','gl')]
        value=dict(schema='arctic-native-controlled-renderers-v1',stage=self.stage,
            primary_screenshot_sha256=primary['screenshot']['sha256'],
            primary_oracle_status='unmatched',primary_failure_preserved=True,
            same_fixture_sha256=primary['fixture_sha256'],same_expected_rgb_sha256=primary['expected_rgb_sha256'],
            trials=rows,release_acceptance=False,rendering_cause_proven=False,
            controls=dict(order=['default','gl'],fresh_owned_app_each=True,settle_seconds=.5,
                same_static_oracle=True,shared_isolated_config_and_cache=True,
                preceding_primary_and_default_warm_cache_confound=True,
                gsk_debug_renderer_both=True,wayland_debug_client_both=True,
                GPU_acceleration_or_software_rendering_proven=False))
        try:
            require(primary['oracle']['status']=='unmatched','controlled trials require the failed primary oracle')
            require(digest(fixture)==primary['fixture_sha256'] and digest(expected)==primary['expected_rgb_sha256'],
                    'controlled fixture identity changed')
            self.finish_native_protocol()
            # Retire only the two already-proved fresh Celluloid processes.
            # Other baseline apps/configuration stay as observed; no global kill.
            players=[p for p in self.owned if p.get('executable')=='/usr/bin/celluloid']
            require(1<=len(players)<=2,'controlled primary player inventory differs')
            for player in players: retire_renderer_player(player,self.uid)
            for index,mode in enumerate(('default','gl')):
                trial=None
                try:
                    trial=RendererTrialSmoke(self,mode)
                    rows[index]=trial.observe(fixture,expected,source_sha)
                except Exception as error:
                    rows[index].update(status='unknown',error=renderer_trial_error(error))
                finally:
                    if trial is not None:
                        # Parent cleanup retains every fresh proof even after a
                        # trial failure; bounded private stderr never enters export.
                        self.owned.extend(trial.owned); self.launches.extend(trial.launches)
                        trial.finish_native_protocol()
                        cleanup=True
                        for player in trial.owned:
                            try: retire_renderer_player(player,self.uid)
                            except Exception: cleanup=False
                        rows[index]['owned_trial_cleanup_completed']=cleanup
        except Exception as error:
            value['preparation_error']=renderer_trial_error(error)
        # Failures of this optional receipt cannot replace the primary error.
        try:
            write_renderer_receipt(self.root,self.uid,value)
        except (OSError,ValueError,RuntimeError): pass

    # BEGIN CONTROLLED_CONTROLS_INVOCATION
    def controlled_controls_trials(self,fixture,expected,source_sha,primary):
        """Two failure-only default players; the original primary remains failed."""
        states=('transition','hidden')
        rows=[dict(intervention=state,status='unrun',release_acceptance=False) for state in states]
        value=dict(schema='arctic-native-controls-state-v1',stage=self.stage,
            primary_screenshot_sha256=primary['screenshot']['sha256'],
            primary_oracle_status='unmatched',primary_failure_preserved=True,
            primary_capture_precondition=primary['capture_precondition'],
            same_fixture_sha256=primary['fixture_sha256'],same_expected_rgb_sha256=primary['expected_rgb_sha256'],
            trials=rows,release_acceptance=False,rendering_cause_proven=False,
            controls=dict(order=list(states),initial_controls_visible=[True,False],
                fresh_owned_app_each=True,requested_gsk_renderer='unset',
                settle_seconds=.5,diagnostic_time_bound_seconds_each=120,
                same_static_oracle=True,shared_isolated_config_and_cache=True,
                original_primary_and_ordered_warm_cache_confound=True,
                preceding_primary_player_environment_not_fully_attested=True,
                gsk_debug_renderer_both=True,wayland_debug_client_both=True,
                video_widget_or_framebuffer_attested=False,
                GUI_controls_visibility_is_setting_readback_not_pixel_attestation=True))
        try:
            require(primary['oracle']['status']=='unmatched','controls trials require the failed primary oracle')
            require(digest(fixture)==primary['fixture_sha256'] and digest(expected)==primary['expected_rgb_sha256'],
                    'controls trial fixture identity changed')
            self.finish_native_protocol()
            players=[p for p in self.owned if p.get('executable')=='/usr/bin/celluloid']
            require(1<=len(players)<=2,'controls trial primary player inventory differs')
            for player in players: retire_renderer_player(player,self.uid)
            seen=set()
            for index,state in enumerate(states):
                trial=None
                try:
                    trial=ControlsTrialSmoke(self,state)
                    rows[index]=trial.observe(fixture,expected,source_sha)
                    player=rows[index].get('player')
                    if player is not None:
                        identity_key=(player['pid'],player['start_ticks'])
                        require(identity_key not in seen and not any(identity_key==(p.get('pid'),p.get('start_ticks'))
                                for p in players),'controls trial player is not a new process')
                        seen.add(identity_key)
                except Exception as error:
                    rows[index].update(status='unknown',error=renderer_trial_error(error))
                finally:
                    if trial is not None:
                        self.owned.extend(trial.owned); self.launches.extend(trial.launches)
                        trial.finish_native_protocol()
                        cleanup=True
                        for player in trial.owned:
                            try: retire_renderer_player(player,self.uid)
                            except Exception: cleanup=False
                        rows[index]['owned_trial_cleanup_completed']=cleanup
                require(trial is None or cleanup,'controls trial owned retirement incomplete')
        except Exception as error:
            value['preparation_error']=renderer_trial_error(error)
        try: write_controls_receipt(self.root,self.uid,value)
        except (OSError,ValueError,RuntimeError): pass
    # END CONTROLLED_CONTROLS_INVOCATION

    def setup(self):
        require(Path('/etc/arctic/default-apps').is_file(), 'system role file unavailable')
        config = Path(next((x.split('=',1)[1] for x in self.original_prefix[5:]
                            if x.startswith('XDG_CONFIG_HOME=')), self.user.pw_dir + '/.config'))
        roles = {}
        for path in (Path('/etc/arctic/default-apps'), config/'arctic/default-apps'):
            if path.exists():
                for line in path.read_text().splitlines():
                    if '=' in line and not line.lstrip().startswith('#'):
                        key, value = line.split('=',1)
                        roles[key] = value
        require(all(roles.get(key) == value for key, value in ROLES.items()),
                'requires fresh approved defaults; never overwrite existing choices')
        copied = {}
        for relative in ('libfm/libfm.conf', 'pcmanfm/default/pcmanfm.conf', 'arctic/default-apps', 'mimeapps.list'):
            source = config/relative
            if source.exists():
                require(source.is_file() and not source.is_symlink(), 'unexpected config symlink')
                target = self.root/'config'/relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                copied[str(source)] = digest(source)
        for relative in ('home','cache','data','config','files with spaces'):
            (self.root/relative).mkdir(parents=True, exist_ok=True)
        for path in [self.root, *self.root.rglob('*')]:
            os.chown(path, self.uid, self.user.pw_gid)
        self.copied = copied
        for mime, desktop_id in MIMES.items():
            require(self.cmd(['xdg-mime','query','default',mime], original=True)[1] == desktop_id,
                    'actual user MIME handler differs from fresh default: ' + mime)
            require(self.cmd(['xdg-mime','query','default',mime])[1] == desktop_id,
                    'isolated test MIME handler differs: ' + mime)
        # Avoid killing or sending synthetic keys to a pre-existing instance.
        require(not any(re.search(r'foot|pcmanfm|featherpad|celluloid|xarchiver',
                    str(c.get('appid',c.get('app_id',''))),re.I) for c in self.clients().values()),
                'close pre-existing test apps in this disposable guest before running')
        rpms = execute(['rpm','-q','foot','pcmanfm','xarchiver','featherpad','celluloid','epiphany','fish','nano',
                        '7zip','zip','unzip','tar','xz','bzip2','zstd','cpio','gzip','ffmpeg-free','mpv-libs','wtype',
                        'audit','audit-rules','glib2','at-spi2-core','grim','xdg-desktop-portal'])[1]
        return dict(roles=roles, copied_config_hashes=copied, rpms=rpms,
                    fixture_root=str(self.root), isolation='HOME/XDG config/data/cache in owned guest tmp')

    def write(self, relative, data):
        path = self.root/relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        for item in [path, *[p for p in path.parents if p.is_relative_to(self.root)]]:
            os.chown(item, self.uid, self.user.pw_gid)
        return path

    def user_mkdir(self, path):
        self.cmd(['mkdir','-p',str(path)])

    def owned_media_directory(self):
        path=self.root/'media file opener'
        self.user_mkdir(path)
        info=path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid==self.uid
                and not info.st_mode&0o022 and path.resolve()==path,
                'file-manager media fixture directory owner/type differs')
        return path

    def trace(self, event, **values):
        item = dict(event=event, monotonic_ns=time.monotonic_ns(), gate=self.active_gate)
        item.update(values)
        row = (json.dumps(item,ensure_ascii=False,sort_keys=True)+'\n').encode()
        path = self.root/'gui-trace.log'
        if self.trace_bytes+len(row)<=2*1024*1024:
            with path.open('ab') as stream: stream.write(row)
            self.trace_bytes += len(row)
        else:
            self.trace_omitted += 1
        # Last record and summary remain available even if the optional trace fills.
        (self.root/'gui-trace-summary.json').write_text(json.dumps(dict(
            bytes=self.trace_bytes,omitted_records=self.trace_omitted,last=item,
            bound_bytes=2*1024*1024,client_observations=self.client_observations),ensure_ascii=False))

    def clients(self):
        raw = execute(self.prefix+['mmsg','get','all-clients'])[1]
        data = json.loads(raw)
        require(isinstance(data.get('clients'),list), 'invalid compositor client data')
        require(len({str(c['id']) for c in data['clients']})==len(data['clients']), 'duplicate compositor client ID')
        self.client_observations += 1
        (self.root/'final-clients.json').write_text(raw+'\n')
        fingerprint = hashlib.sha256(raw.encode()).hexdigest()
        self.trace('client-snapshot', raw=data, snapshot_sha256=fingerprint,
                   changed=fingerprint != self.last_client_digest)
        self.last_client_digest = fingerprint
        return {str(c['id']):c for c in data['clients']}

    def wait(self, fn, timeout=30, label='functional observation'):
        origin=time.monotonic(); until=origin+timeout; polls=0
        while time.monotonic() < until:
            polls+=1
            value = fn()
            if value:
                self.trace('wait-passed',label=label,polls=polls,elapsed_seconds=time.monotonic()-origin,timeout_seconds=timeout)
                return value
            time.sleep(.2)
        self.trace('wait-timeout',label=label,polls=polls,elapsed_seconds=time.monotonic()-origin,timeout_seconds=timeout)
        raise RuntimeError('bounded functional gate timed out: '+label)

    def diagnostic(self, label, required=True):
        result=dict(label=label,monotonic_ns=time.monotonic_ns())
        try:
            result['clients']=self.clients()
            name='gui-%02d-' % self.capture_count+re.sub('[^a-zA-Z0-9_-]','_',label)[:90]
            self.capture_count+=1
            result['screenshot']=self.screenshot(name)
        except Exception as exc:
            result['collector_error']=type(exc).__name__+': '+str(exc)
        self.trace('diagnostic',**result)
        require(not required or 'collector_error' not in result, 'required GUI diagnostic failed: '+str(result.get('collector_error')))
        return result

    def navigate(self, proof, directory, label):
        require(directory.is_dir() and not directory.is_symlink() and directory.resolve().is_relative_to(self.root),
                'navigation fixture is outside owned guest evidence')
        self.diagnostic(label+'-before-location')
        self.physical_pcmanfm(proof,'navigate',str(directory))
        self.wait(lambda:directory.name in self.alive(proof).get('title',''),30,
                  label='PCManFM directory title after physical Return: '+directory.name)
        self.diagnostic(label+'-navigation-confirmed')

    def fresh_window(self, trigger, program, pattern, native=True):
        expected = str(Path('/usr/bin')/program)
        actual = json.loads(self.cmd(['python3','-c',
            'import json,os,shutil,sys; p=shutil.which(sys.argv[1]); print(json.dumps(os.path.realpath(p) if p else None))',program])[1])
        require(actual == str(Path(expected).resolve(strict=True)), 'PATH resolves a different/non-native app')
        before_clients = set(self.clients())
        before_processes = process_snapshot(self.uid)
        trigger()
        def found():
            matches = [c for key,c in self.clients().items() if key not in before_clients
                       and re.search(pattern,str(c.get('appid',c.get('app_id',''))),re.I)
                       and c.get('is_visible') is True]
            require(len(matches) <= 1, 'ambiguous newly mapped app')
            if not matches:
                return None
            return window_proof(matches[0],self.uid,expected,before_processes,native)
        value = self.wait(found,45)
        self.owned.append(value)
        value['executable_sha256'] = digest(value['executable'])
        return value

    def alive(self, proof):
        current = identity(proof['pid'],self.uid)
        require(all(current[key] == proof[key] for key in ('pid','start_ticks','executable')),
                'GUI PID exited or was recycled')
        client = self.clients().get(proof['client_id'])
        require(client and client.get('pid') == proof['pid'] and client.get('is_visible') is True,
                'proved GUI is no longer mapped')
        return client

    def physical_pcmanfm(self, proof, action, path=None):
        self.alive(proof)
        require(proof['executable']=='/usr/bin/pcmanfm' and proof['is_xwayland'] is False,
                'physical route requires exact owned native PCManFM')
        response=self.cmd(['mmsg','dispatch','focusid','client,'+proof['client_id']])[1]
        require(json.loads(response).get('success') is True,'compositor did not acknowledge owned physical focus')
        self.wait(lambda:self.alive(proof).get('is_focused') is True,10)
        self.native_physical_count=getattr(self,'native_physical_count',0)+1
        require(self.native_physical_count<=7 and action in ('navigate','f4','open-first'),'physical route count/action differs')
        if action=='navigate':
            require(path in (str(self.root/'files with spaces'),str(self.root/'archive file opener'),str(self.root/'media file opener'))
                    and len(path)<=128 and path.isascii(),'physical path is not an exact bounded ASCII fixture')
        else:require(path is None,'physical shortcut cannot carry text')
        observed=time.monotonic_ns();client=self.alive(proof)
        require(client.get('is_focused') is True and client.get('is_xwayland') is False,
                'fresh physical owned native focus changed')
        request=dict(schema='arctic-native-pcmanfm-physical-v1',stage=self.stage,nonce=os.urandom(16).hex(),
                     boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),desktop_uid=self.uid,
                     process=dict(proof,uid=self.uid,executable_sha256=digest(Path(proof['executable']))),client=client,action=action,path=path,evidence_root=str(self.root),
                     monotonic_ns=time.monotonic_ns(),client_monotonic_ns=observed,
                     release_acceptance=False,accessibility_proof=False)
        self.trace('physical-request',request=request)
        print('ARCTIC-NATIVE-PCMANFM-PHYSICAL '+json.dumps(request,sort_keys=True),flush=True)

    def keys(self, proof, *argv):
        if proof.get('executable')=='/usr/bin/pcmanfm':
            require(tuple(argv) in (('-k','F4'),('-k','Home','-k','Return')),'unsupported PCManFM physical shortcut')
            return self.physical_pcmanfm(proof,'f4' if tuple(argv)==('-k','F4') else 'open-first')
        self.alive(proof)
        self.trace('input-turn-before', proof=proof, argv=list(argv), client=self.alive(proof))
        response=self.cmd(['mmsg','dispatch','focusid','client,'+proof['client_id']])[1]
        require(json.loads(response).get('success') is True, 'compositor did not acknowledge owned focus target')
        self.wait(lambda:self.alive(proof).get('is_focused') is True,10)
        # Known virtual-keyboard first-event loss: warm up with a harmless modifier.
        self.cmd(['wtype','-s','200','-k','Shift_L','-s','150',*argv],timeout=30)
        self.trace('input-turn-after', proof=proof, argv=list(argv), client=self.alive(proof))


    def physical_editor_save(self, proof, fixture):
        # The Unicode turn already established focus; no dispatch/focus repair here.
        require(proof['executable']=='/usr/bin/featherpad' and proof['is_xwayland'] is False,
                'physical save requires owned native FeatherPad')
        observed=time.monotonic_ns();client=self.alive(proof)
        require(client.get('is_focused') is True and client.get('is_visible') is True
                and client.get('is_xwayland') is False and client.get('appid')=='featherpad'
                and client.get('title','').lstrip('*')==str(fixture),
                'physical save requires fresh focused exact fixture editor')
        require(fixture==self.root/'files with spaces/editor fixture.txt'
                and not getattr(self,'editor_save_emitted',False),'only one exact editor-save request')
        self.editor_save_emitted=True
        request=dict(schema='arctic-native-editor-save-v1',stage=self.stage,nonce=os.urandom(16).hex(),
            boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),desktop_uid=self.uid,
            process=dict(proof,uid=self.uid,executable_sha256=digest(Path(proof['executable']))),client=client,
            action='save-editor',path=str(fixture),evidence_root=str(self.root),
            monotonic_ns=time.monotonic_ns(),client_monotonic_ns=observed,
            release_acceptance=False,accessibility_proof=False)
        self.trace('editor-physical-request',request=request)
        print('ARCTIC-NATIVE-EDITOR-PHYSICAL '+json.dumps(request,sort_keys=True),flush=True)

    def player_fullscreen(self, proof, enabled, ipc):
        require(type(enabled) is bool and proof['executable']=='/usr/bin/celluloid'
                and proof['is_xwayland'] is False,'owned native player fullscreen only')
        before=self.alive(proof)
        monitors_before=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
        visual_capture_geometry(before,monitors_before)
        require(before.get('is_fullscreen') is (not enabled),'fullscreen must change exactly once')
        origin=time.monotonic_ns()
        action=mpv_celluloid_fullscreen(ipc,proof['pid'],self.uid,enabled)
        self.wait(lambda:self.alive(proof).get('is_fullscreen') is enabled,10,'owned player fullscreen state')
        after=self.alive(proof)
        monitors_after=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
        monitor,_,crop=visual_capture_geometry(after,monitors_after)
        require(all(after.get(k)==before.get(k) for k in ('id','pid','appid','foreign_toplevel_id','monitor')),
                'owned player identity changed during fullscreen')
        if enabled:
            require(crop==dict(x=0,y=0,width=monitor['width'],height=monitor['height']),
                    'fullscreen did not provide the complete observed monitor viewport')
        receipt=dict(player=dict(proof,uid=self.uid),enabled=enabled,before=before,after=after,
            monitors_before=monitors_before,monitors_after=monitors_after,action=action,
            monotonic_ns=origin,completed_monotonic_ns=time.monotonic_ns(),release_acceptance=False)
        self.trace('owned-player-fullscreen',receipt=receipt)
        self.fullscreen_receipts=getattr(self,'fullscreen_receipts',[])+[receipt]
        (self.root/'fullscreen-player-receipts.json').write_text(json.dumps(self.fullscreen_receipts,indent=2))
        return receipt

    def fullscreen_capture_pair(self, proof, before, after, screenshot):
        require(all(before.get(k)==after.get(k) for k in ('id','pid','appid','foreign_toplevel_id','monitor',
                'is_focused','is_visible','is_fullscreen','x','y','width','height'))
                and after.get('is_focused') is True and after.get('is_visible') is True
                and after.get('is_fullscreen') is True,'owned fullscreen capture identity/geometry changed')
        value=dict(player=dict(proof,uid=self.uid),before=before,after=after,screenshot=screenshot,release_acceptance=False)
        self.trace('owned-fullscreen-capture',receipt=value)
        self.fullscreen_captures=getattr(self,'fullscreen_captures',[])+[value]
        (self.root/'fullscreen-player-captures.json').write_text(json.dumps(self.fullscreen_captures,indent=2))

    def screenshot(self, name):
        path = self.root/(name+'.png')
        self.cmd(['grim',str(path)])
        require(path.stat().st_size > 0, 'empty screenshot')
        return dict(path=str(path),sha256=digest(path),review='human content review still required')

    def archives(self, formats=None):
        source = self.root/'archive source'
        self.write('archive source/nested directory/hello world.txt', b'Arctic archive roundtrip\n\x00\xff\n')
        self.write('archive source/Unicode-\u05e9.txt', '\u05e9\u05dc\u05d5\u05dd \u03bb \u65e5\u672c\u8a9e\n'.encode())
        self.user_mkdir(source/'empty directory'/'nested empty')
        expected = tree_hashes(source)
        result = []
        selected = formats or ('zip','7z','tar','tar.gz','tar.bz2','tar.xz','tar.zst','cpio',
                               'gzip','bzip2','xz','zstd','7z-encrypted')
        seven = next((name for name in ('7z','7zz') if self.cmd(['sh','-c','command -v "$1"','probe',name],
                       allow_failure=True)[0] == 0),None) if any(x.startswith('7z') for x in selected) else None
        if any(x.startswith('7z') for x in selected):
            require(seven, '7zip helper not available')
        for kind in selected:
            archive = self.root/('roundtrip.'+kind)
            target = self.root/('extracted '+kind)
            self.user_mkdir(target)
            if kind == 'zip':
                self.cmd(['zip','-q','-r',str(archive),'.'],cwd=source)
                self.cmd(['unzip','-q',str(archive),'-d',str(target)])
            elif kind.startswith('7z'):
                password = ['-pArcticSmokeFixtureOnly-42','-mhe=on'] if kind.endswith('encrypted') else []
                self.cmd([seven,'a','-y','-t7z',*password,str(archive),'.'],cwd=source)
                self.cmd([seven,'x','-y',*password[:1],str(archive),'-o'+str(target)])
                if password:
                    wrong = self.root/'wrong-password-control'
                    self.user_mkdir(wrong)
                    require(self.cmd([seven,'x','-y','-pIncorrectFixturePassword',str(archive),'-o'+str(wrong)],
                                     allow_failure=True)[0] != 0, 'incorrect password accepted')
                    require(not any(p.is_file() and p.stat().st_size for p in wrong.rglob('*')),
                            'incorrect password leaked nonempty plaintext')
            elif kind.startswith('tar'):
                flag = {'tar': [], 'tar.gz':['--gzip'], 'tar.bz2':['--bzip2'],
                        'tar.xz':['--xz'], 'tar.zst':['--zstd']}[kind]
                self.cmd(['tar',*flag,'-cf',str(archive),'-C',str(source),'.'])
                self.cmd(['tar',*flag,'-xf',str(archive),'-C',str(target)])
            elif kind == 'cpio':
                listing = b'\0'.join(str(p.relative_to(source)).encode() for p in sorted(source.rglob('*'))) + b'\0'
                self.cmd(['cpio','--null','-o','-H','newc'],cwd=source,input_bytes=listing,stdout_path=archive)
                self.cmd(['cpio','-i','-d','--no-absolute-filenames'],cwd=target,input_bytes=archive.read_bytes())
            else:
                original = source/'nested directory/hello world.txt'
                output = target/'payload'
                self.cmd([kind,'-c',str(original)],stdout_path=archive)
                self.cmd([kind,'-d','-c',str(archive)],stdout_path=output)
                require(digest(original)==digest(output) and original.stat().st_size==output.stat().st_size,
                        'single-file decompression mismatch')
                result.append(dict(format=kind,sha256=digest(output),bytes=output.stat().st_size,
                                   archive_sha256=digest(archive)))
                continue
            result.append(dict(format=kind,members=verify_tree(expected,target),archive_sha256=digest(archive)))
        return dict(roundtrips=result,scope='helper content tests; GUI archive creation/edit still unqualified')

    def gui_files_editor_terminal(self):
        directory = self.root/'files with spaces'
        fixture = self.write('files with spaces/editor fixture.txt',b'Initial fixture; must change through GUI.\n')
        wanted = ('Arctic GUI saved fixture '+self.root.name+'\nUnicode: \u05e9\u05dc\u05d5\u05dd \u03bb \u65e5\u672c\u8a9e\n').encode()
        system = configparser.ConfigParser(interpolation=None)
        system.read('/usr/share/libfm/terminals.list')
        require(system.has_section('foot') and system['foot'].get('open_arg') == '-e'
                and system['foot'].get('noclose_arg') == '--hold -e'
                and system['foot'].get('desktop_id') == 'foot.desktop', 'Foot system terminal definition missing')
        libfm = configparser.ConfigParser(interpolation=None)
        libfm.read(self.root/'config/libfm/libfm.conf')
        require(libfm.has_section('config') and libfm['config'].get('terminal') == 'foot',
                'copied actual libfm terminal choice is not Foot')
        role_marker = self.root/'terminal-role.json'
        role_code = ('import json,os,pathlib,time;pathlib.Path('+repr(str(role_marker))+').write_text('
                     'json.dumps(dict(uid=os.getuid(),nonce='+repr(self.root.name)+')));time.sleep(60)')
        role_terminal = self.fresh_window(lambda:self.cmd(['/usr/bin/arctic-open','terminal',
            '--app-id','arctic-native-role','-e','python3','-c',role_code]),'foot',r'^arctic-native-role$')
        self.wait(lambda:role_marker.is_file())
        require(json.loads(role_marker.read_text()) == dict(uid=self.uid,nonce=self.root.name),
                'terminal role did not execute literal supplied arguments')
        # The role creates the editor; the file manager must then open our fixture in it.
        editor = self.fresh_window(lambda:self.cmd(['/usr/bin/arctic-open','editor']),
                                   'featherpad',r'featherpad')
        files = self.fresh_window(lambda:self.cmd(['/usr/bin/arctic-open','files']),
                                  'pcmanfm',r'pcmanfm',native=False)
        self.navigate(files,directory,'text-fixture')
        terminal = self.fresh_window(lambda:self.keys(files,'-k','F4'),'foot',r'^foot$')
        self.diagnostic('file-manager-F4-mapped')
        marker = self.root/'file-manager-terminal.json'
        code = ('import json,os,pathlib;pathlib.Path('+repr(str(marker))+').write_text('
                'json.dumps(dict(uid=os.getuid(),cwd=os.getcwd(),nonce='+repr(self.root.name)+')))')
        command = shlex.join(['python3','-c',code])
        self.keys(terminal,command,'-k','Return')
        self.wait(lambda:marker.is_file())
        proof = json.loads(marker.read_text())
        require(proof == dict(uid=self.uid,cwd=str(directory),nonce=self.root.name),
                'file-manager terminal did not execute in the current folder as the desktop user')
        # Upstream Ctrl+L always changes directory; it does not launch files.
        # This folder contains exactly our one text fixture. Activate its file view.
        require(list(directory.iterdir()) == [fixture], 'ambiguous file-manager text fixture')
        self.keys(files,'-k','Home','-k','Return')
        self.wait(lambda:fixture.name in self.alive(editor).get('title',''))
        if getattr(self,'gui_v6',False):
            self.keys(editor,'-M','ctrl','-k','a','-m','ctrl',wanted.decode())
            self.physical_editor_save(editor,fixture)
        else:
            self.keys(editor,'-M','ctrl','-k','a','-m','ctrl',wanted.decode(),
                      '-M','ctrl','-k','s','-m','ctrl')
        self.wait(lambda:fixture.read_bytes() == wanted)
        self.alive(editor)
        editor_shot = self.screenshot('editor-saved')
        self.diagnostic('editor-save-confirmed')
        archive_source = self.root/'roundtrip.zip'
        require(archive_source.is_file(), 'ZIP content gate did not provide its fixture')
        archive = self.write('archive file opener/roundtrip.zip',archive_source.read_bytes())
        self.navigate(files,archive.parent,'archive-fixture')
        require(list(archive.parent.iterdir()) == [archive], 'ambiguous file-manager ZIP fixture')
        archiver = self.fresh_window(lambda:self.keys(files,'-k','Home','-k','Return'),
                                     'xarchiver',r'xarchiver',native=False)
        self.wait(lambda:archive.name in self.alive(archiver).get('title',''))
        media_dir=self.owned_media_directory()
        source=self.write('file-manager-media-input.raw',visual_reference_frame()*10)
        media_file=media_dir/'file-manager-reference.mkv'
        self.cmd(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-f','rawvideo',
                  '-pixel_format','rgb24','-video_size','160x120','-framerate','10','-i',str(source),
                  '-an','-c:v','ffv1','-level','3','-pix_fmt','yuv420p','-t','1',str(media_file)])
        require(list(media_dir.iterdir())==[media_file],'ambiguous file-manager media fixture')
        self.navigate(files,media_dir,'media-fixture')
        media_player=self.fresh_window(lambda:self.keys(files,'-k','Home','-k','Return'),
                                       'celluloid',r'celluloid')
        media_route=self.product_launch_contract(media_player,'file-manager-mime')
        retire_renderer_player(media_player,self.uid)
        return dict(role_terminal=role_terminal,role_editor=editor,role_files=files,
                    file_manager_foot=terminal,file_manager_zip_opener=archiver,
                    file_manager_media_opener=dict(player=media_player,product_launch=media_route,
                        fixture=str(media_file),mime='video/x-matroska',retired_after_proof=True),
                    terminal_execution=proof,gui_saved=dict(path=str(fixture),sha256=digest(fixture),bytes=len(wanted)),
                    screenshots=[editor_shot,self.screenshot('files-opened-zip')],
                    scope='actual role launch + PCManFM text/ZIP/media openers/F4 + GUI Unicode edit/save; mount/network/a11y remain separate')

    def retire_moving_player(self,player,ipc):
        """Retire the proved moving player before creating the static oracle player."""
        require(isinstance(ipc,Path) and ipc==self.root/'celluloid-ipc.sock'
                and sum(item is player for item in self.owned)==1,
                'moving player retirement target differs')
        # A pathname-bound Unix socket normally survives its listener. Pin the
        # live endpoint before signalling, then atomically quarantine it in a
        # root-owned directory. The desktop UID cannot replace the quarantined
        # entry between its held-fd identity check and unlink.
        fields=('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink')
        directory=os.open(self.root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            root_info=os.fstat(directory)
            require(root_info.st_uid==self.uid and stat.S_ISDIR(root_info.st_mode)
                    and not root_info.st_mode&0o077,
                    'moving player IPC directory is not private')
            root_identity=(root_info.st_dev,root_info.st_ino)
            held=os.open(ipc.name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=directory)
            try:
                before=os.fstat(held)
                require(stat.S_ISSOCK(before.st_mode) and before.st_uid==self.uid and before.st_nlink==1,
                        'moving player IPC owner/type differs')
                ipc_identity=tuple(getattr(before,key) for key in fields)
                with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
                    peer.settimeout(2);peer.connect(str(ipc))
                    pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                    require((pid,uid)==(player['pid'],self.uid),'moving player IPC peer differs')
                after=os.stat(ipc.name,dir_fd=directory,follow_symlinks=False)
                require(tuple(getattr(after,key) for key in fields)==ipc_identity,
                        'moving player IPC identity changed during proof')
                retire_renderer_player(player,self.uid)
                quarantine=Path(tempfile.mkdtemp(prefix='.celluloid-ipc-retired-',dir=self.root))
                quarantine_info=quarantine.lstat()
                require(stat.S_ISDIR(quarantine_info.st_mode)
                        and quarantine_info.st_uid==os.geteuid() and not quarantine_info.st_mode&0o077,
                        'moving player IPC quarantine is not private')
                quarantine_directory=os.open(quarantine,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
                try:
                    retired_name='endpoint.sock'
                    try: rename_noreplace(directory,ipc.name,quarantine_directory,retired_name)
                    except FileNotFoundError: pass
                    else:
                        retired=os.open(retired_name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,
                                        dir_fd=quarantine_directory)
                        try:
                            retired_info=os.fstat(retired)
                            if tuple(getattr(retired_info,key) for key in fields)!=ipc_identity:
                                try: rename_noreplace(quarantine_directory,retired_name,directory,ipc.name)
                                except (FileNotFoundError,FileExistsError,OSError): pass
                                raise RuntimeError('moving player IPC identity changed before quarantine')
                            os.unlink(retired_name,dir_fd=quarantine_directory)
                        finally: os.close(retired)
                finally: os.close(quarantine_directory)
            finally: os.close(held)
            def fully_retired():
                path_info=self.root.lstat()
                require(stat.S_ISDIR(path_info.st_mode) and path_info.st_uid==self.uid
                        and not path_info.st_mode&0o077
                        and (path_info.st_dev,path_info.st_ino)==root_identity,
                        'moving player IPC directory identity changed after quarantine')
                try: os.stat(ipc.name,dir_fd=directory,follow_symlinks=False)
                except FileNotFoundError: socket_absent=True
                else:
                    require(False,'moving player IPC path was recreated after quarantine')
                    socket_absent=False
                return socket_absent and self.clients().get(player['client_id']) is None
            self.wait(fully_retired,5,'moving player process/socket/compositor retirement')
            return dict(process_identity_retired=True,owned_ipc_absent=True,
                        compositor_client_absent=True,release_acceptance=False)
        finally: os.close(directory)

    def media(self):
        fixture,decoder = self.media_fixture()
        self.gates.append(dict(check='open-codec-lossless-command-decode',status='passed',value=decoder))
        action_routes=[]
        for action in ('new-window','enqueue'):
            player=self.fresh_window(lambda action=action:self.gio_desktop_action(action),
                                     'celluloid',r'celluloid')
            action_routes.append(self.product_launch_contract(player,'gio-'+action))
            retire_renderer_player(player,self.uid)
        enqueue_ipc=self.root/'celluloid-enqueue-ipc.sock'
        enqueue_target=self.fresh_window(lambda:self.launch(['/usr/libexec/arctic/arctic-celluloid',
            '--mpv-input-ipc-server='+str(enqueue_ipc),'--mpv-loop-file=inf',str(fixture)]),
            'celluloid',r'celluloid')
        enqueue_route=self.product_launch_contract(enqueue_target,'enqueue-target')
        self.wait(lambda:enqueue_ipc.is_socket())
        require(mpv_property(enqueue_ipc,'playlist-count',enqueue_target['pid'],self.uid)==1,
                'Celluloid enqueue target initial playlist differs')
        enqueue_fixture=self.root/'enqueue-reference.mkv';enqueue_fixture.write_bytes(fixture.read_bytes())
        before_enqueue=self.alive(enqueue_target)
        self.cmd(['/usr/libexec/arctic/arctic-celluloid','--enqueue',str(enqueue_fixture)],timeout=15)
        self.wait(lambda:mpv_property(enqueue_ipc,'playlist-count',enqueue_target['pid'],self.uid)==2,
                  10,'Celluloid enqueue playlist count')
        require(mpv_property(enqueue_ipc,'playlist/1/filename',enqueue_target['pid'],self.uid)==str(enqueue_fixture)
                and self.alive(enqueue_target).get('id')==before_enqueue.get('id'),
                'Celluloid enqueue did not preserve target window and append exact file')
        enqueue_semantics=dict(product_launch=enqueue_route,initial_playlist_count=1,
            final_playlist_count=2,appended_path=str(enqueue_fixture),target_window_preserved=True,
            release_acceptance=True)
        retire_renderer_player(enqueue_target,self.uid)
        ipc = self.root/'celluloid-ipc.sock'
        player = self.fresh_window(lambda:self.launch_reference_player(['/usr/libexec/arctic/arctic-celluloid','--no-existing-session',
            '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)],
            self.launch_protocol_player if getattr(self,'gui_v6',False) else self.launch),
            'celluloid',r'celluloid')
        renderer=self.product_renderer_contract(player) if getattr(self,'gui_v6',False) else None
        self.wait(lambda:ipc.is_socket())
        def ready():
            try:
                return (mpv_property(ipc,'video-params',player['pid'],self.uid)
                        and mpv_property(ipc,'audio-out-params',player['pid'],self.uid))
            except RuntimeError as exc:
                if str(exc).startswith('mpv property unavailable:'):
                    return None
                raise
        self.wait(ready)
        samples = []
        for sample_index in range(8):
            sample = {key:mpv_property(ipc,key,player['pid'],self.uid)
                      for key in ('path','time-pos','pause','video-params','audio-params','audio-out-params','current-vo','current-ao')}
            samples.append(sample)
            self.alive(player)
            # Preserve all seven sample-to-sample intervals.  The eighth sleep
            # never contributed another sample, so retain that exact bounded
            # settle below after the final fullscreen geometry is established.
            if sample_index < 7: time.sleep(.35)
        validate_player_samples(samples,str(fixture))
        maps = Path('/proc')/str(player['pid'])/'maps'
        require('libmpv.so' in maps.read_text(), 'Celluloid PID has no mapped libmpv')
        if getattr(self,'gui_v6',False):
            self.player_fullscreen(player,True,ipc)
            moving_before=self.alive(player)
        time.sleep(.35)
        moving_shot=self.screenshot('celluloid-playing')
        if getattr(self,'gui_v6',False):
            self.fullscreen_capture_pair(player,moving_before,self.alive(player),moving_shot)
        moving_proof=dict(decoder=decoder,player=player,player_samples=samples,screenshot=moving_shot,
                          product_renderer=renderer,
                          client=self.alive(player),scope='original moving testsrc2 decode/advancing AV state retained; this frame still requires visual review; the same visibly proved renderer is reused for the sequential static oracle')
        reuse=dict(schema='arctic-native-player-fixture-continuity-v1',player=player,
                   ipc=str(ipc),moving_fixture=str(fixture),moving_screenshot_sha256=moving_shot['sha256'],
                   product_renderer=renderer,
                   same_process_renderer_required=True,release_acceptance=False)
        moving_proof['static_oracle_reuse']=reuse
        (self.root/'moving-player-proof.json').write_text(json.dumps(moving_proof,indent=2))
        if getattr(self,'gui_v6',False): self.player_fullscreen(player,False,ipc)
        visual=self.visual_media(reuse if getattr(self,'gui_v6',False) else None)
        return dict(moving_proof, visual_reference=visual,desktop_action_launches=action_routes,
                    enqueue_semantics=enqueue_semantics,
                    scope='product file-manager/MIME and Gio desktop actions plus enqueue semantics; one owned product player proves the original moving fixture and then an authenticated exact-file transition to the strict static oracle; motion/perceived audio/hardware remain unqualified')

    def visual_fixture(self):
        source=self.write('visual-reference-input.raw',visual_reference_stream())
        fixture=self.root/'visual-reference.mkv'
        expected=self.root/'visual-reference-frame.rgb'
        common=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        self.cmd(common+['-f','rawvideo','-pixel_format','rgb24','-video_size','160x120','-framerate','10',
            '-i',str(source),'-an','-c:v','ffv1','-level','3','-pix_fmt','yuv420p','-t','2',str(fixture)])
        self.cmd(common+['-i',str(fixture),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo',str(expected)])
        require(expected.stat().st_size==160*120*3,'reference decoded RGB frame size differs')
        return fixture,expected,digest(source)

    def launch_reference_player(self, argv, launch):
        # Only this owned reference window uses private keyfile settings. Its
        # supported UI action must not write the desktop user's dconf database.
        diagnostic=isinstance(self,(RendererTrialSmoke,ControlsTrialSmoke))
        expected='/usr/bin/celluloid' if diagnostic else '/usr/libexec/arctic/arctic-celluloid'
        require(argv[0]==expected, 'reference controls Celluloid launcher selection differs')
        if not getattr(self,'gui_v6',False):
            launch(argv)
            return
        self.reference_settings_config()
        original=self.prefix
        require(not any(x.startswith('GSETTINGS_BACKEND=') for x in original),
                'reference settings backend already selected')
        self.prefix=original+['GSETTINGS_BACKEND=keyfile']
        try:
            launch(argv)
        finally:
            self.prefix=original

    def reference_settings_config(self):
        configs=[x.split('=',1)[1] for x in self.prefix if x.startswith('XDG_CONFIG_HOME=')]
        # GNU env applies the final assignment after the discovered desktop
        # config. Renderer trials intentionally share the primary private config.
        require(configs, 'reference settings config is absent')
        config=Path(configs[-1])
        expected=(self.root.parent if isinstance(self,RendererTrialSmoke) else self.root)/'config'
        info=config.lstat()
        require(config==expected and config.is_absolute() and stat.S_ISDIR(info.st_mode)
                and info.st_uid==self.uid and not info.st_mode&0o022 and config.resolve()==config,
                'reference settings config is not exact private owned directory')
        return config

    def hide_reference_controls(self, player, ipc):
        require(player['executable']=='/usr/bin/celluloid' and player['is_xwayland'] is False,
                'reference controls require owned native Celluloid')
        before=self.alive(player)
        require(before.get('is_focused') is True and before.get('is_fullscreen') is True,
                'reference controls require fresh focused fullscreen player')
        config=self.reference_settings_config()
        environ=Path('/proc')/str(player['pid'])/'environ'
        require(environ.stat().st_uid==self.uid, 'reference settings process owner differs')
        with environ.open('rb') as stream: raw=stream.read(65537)
        require(len(raw)<=65536, 'reference settings environment exceeded bound')
        values=raw.split(b'\0')
        require([x for x in values if x.startswith(b'GSETTINGS_BACKEND=')]==[b'GSETTINGS_BACKEND=keyfile']
                and [x for x in values if x.startswith(b'XDG_CONFIG_HOME=')]==[
                    b'XDG_CONFIG_HOME='+os.fsencode(config)], 'reference settings process/config binding differs')
        query=['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings','get',
               'io.github.celluloid-player.Celluloid.window-state','show-controls']
        initial=self.cmd(query,timeout=5)[1]
        require(initial in ('true','false'), 'reference controls initial state is not boolean')
        mpv_hide_reference_controls(ipc,player['pid'],self.uid)
        def hidden():
            result=self.cmd(query,timeout=5)[1]
            require(result in ('true','false'), 'reference controls readback is not boolean')
            return result=='false'
        self.wait(hidden,5,'owned reference controls hidden readback')
        after=self.alive(player)
        require(all(after.get(k)==before.get(k) for k in ('id','pid','appid','foreign_toplevel_id',
                'monitor','is_focused','is_visible','is_fullscreen','x','y','width','height')),
                'reference controls player identity/focus/geometry changed')
        value=dict(action='win.set-controls-visible(false)',transport='owned mpv IPC SO_PEERCRED',
                   settings_backend='keyfile',private_config_process_bound=True,
                   before_visible=initial=='true',after_visible=False,
                   readback_scope='supported action writes private setting after GTK control-box visibility update',
                   release_acceptance=False)
        self.trace('reference-controls-hidden',receipt=value)
        return value

    def visual_media(self,reuse=None):
        fixture,expected,source_sha=self.visual_fixture()
        # The GUI release gate admits only the already proved product-wrapper
        # player. A failed or unmatched capture cannot create another path.
        player_attempt=1
        player_attempt_limit=1
        common=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        ipc=self.root/'visual-reference-ipc.sock'
        transition=None
        if getattr(self,'gui_v6',False):
            require(type(reuse) is dict and set(reuse)=={'schema','player','ipc','moving_fixture',
                    'moving_screenshot_sha256','product_renderer','same_process_renderer_required','release_acceptance'}
                    and reuse['schema']=='arctic-native-player-fixture-continuity-v1'
                    and type(reuse['product_renderer']) is dict
                    and reuse['same_process_renderer_required'] is True and reuse['release_acceptance'] is False,
                    'visual oracle requires exact moving-player continuity')
            player=reuse['player'];renderer=reuse['product_renderer']
            old_ipc=Path(reuse['ipc'])
            require(old_ipc==self.root/'celluloid-ipc.sock' and old_ipc.is_socket()
                    and reuse['moving_fixture']==str(self.root/'open-codec-fixture.mkv')
                    and re.fullmatch(r'[0-9a-f]{64}',reuse['moving_screenshot_sha256']) is not None,
                    'moving-player continuity paths/evidence differ')
            ipc=old_ipc
            before=self.alive(player)
            require(before.get('is_fullscreen') is False and before.get('is_focused') is True,
                    'moving player was not restored before static fixture transition')
            source_path=mpv_property(ipc,'path',player['pid'],self.uid)
            require(source_path==reuse['moving_fixture'],'moving player source changed before static transition')
            transition=mpv_replace_fixture(ipc,player['pid'],self.uid,Path(source_path),fixture)
        else:
            require(reuse is None,'non-GUI visual fixture cannot reuse a GUI player')
            player=self.fresh_window(lambda:self.launch_reference_player(['/usr/libexec/arctic/arctic-celluloid','--no-existing-session',
                '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)],self.launch),
                'celluloid',r'celluloid')
            renderer=None
            self.wait(lambda:ipc.is_socket())
        def ready_reference():
            try:
                return (mpv_property(ipc,'path',player['pid'],self.uid)==str(fixture)
                        and mpv_property(ipc,'video-params',player['pid'],self.uid))
            except RuntimeError as exc:
                if str(exc).startswith('mpv property unavailable:'): return None
                raise
        self.wait(ready_reference)
        state={key:mpv_property(ipc,key,player['pid'],self.uid)
               for key in ('path','pause','video-params','current-vo','time-pos')}
        require(state['path']==str(fixture) and state['pause'] is False and state['current-vo']=='libmpv'
                and state['video-params'].get('w')==160 and state['video-params'].get('h')==120,
                'exact visual reference file/GUI renderer state differs')
        # Focus only our proved new window; no renderer/GPU/configuration flag.
        response=self.cmd(['mmsg','dispatch','focusid','client,'+player['client_id']])[1]
        require(json.loads(response).get('success') is True,'visual player focus failed')
        self.wait(lambda:self.alive(player).get('is_focused') is True,10)
        if getattr(self,'gui_v6',False):
            self.player_fullscreen(player,True,ipc)
            controls=self.hide_reference_controls(player,ipc)
        pre_geometry_time=state['time-pos']
        require(type(pre_geometry_time) in (int,float) and not isinstance(pre_geometry_time,bool)
                and math.isfinite(pre_geometry_time) and 0<=pre_geometry_time<=2,
                'pre-geometry visual playback clock is invalid')
        # Anchor readiness after the fullscreen and controls transitions.  A
        # clock sampled before those transitions can satisfy the old delta as
        # soon as the window enters fullscreen, while its GL content is still
        # unpainted.  The exact same owned player must advance for a bounded
        # interval in its final capture geometry before the sole screenshot.
        initial_time=mpv_property(ipc,'time-pos',player['pid'],self.uid)
        require(type(initial_time) in (int,float) and not isinstance(initial_time,bool)
                and math.isfinite(initial_time) and 0<=initial_time<=2,
                'post-geometry visual playback clock is invalid')
        minimum_post_geometry_advance=.5
        def playback_advanced():
            observed=mpv_property(ipc,'time-pos',player['pid'],self.uid)
            require(type(observed) in (int,float) and not isinstance(observed,bool)
                    and math.isfinite(observed) and 0<=observed<=2,
                    'visual playback clock is invalid')
            delta=observed-initial_time
            if delta<0: delta+=2
            return observed if delta>=minimum_post_geometry_advance else None
        advanced_time=self.wait(playback_advanced,5,'owned visual playback clock advancement')
        # The pulsed fixture above proves post-fullscreen presentation work, but
        # capturing while the software GL path is replacing that texture can
        # expose a transient tiled buffer rather than one complete frame. Pause
        # this same proved player, require the clock to settle, and keep the
        # sole screenshot/oracle and every acceptance threshold unchanged.
        mpv_pause_reference(ipc,player['pid'],self.uid)
        def paused_reference():
            value=mpv_property(ipc,'pause',player['pid'],self.uid)
            require(type(value) is bool, 'visual pause state is not Boolean')
            return value
        self.wait(paused_reference,3,'owned visual playback pause')
        paused_time=mpv_property(ipc,'time-pos',player['pid'],self.uid)
        require(type(paused_time) in (int,float) and not isinstance(paused_time,bool)
                and math.isfinite(paused_time) and 0<=paused_time<=2,
                'paused visual playback clock is invalid')
        time.sleep(.5)
        settled_time=mpv_property(ipc,'time-pos',player['pid'],self.uid)
        require(type(settled_time) in (int,float) and not isinstance(settled_time,bool)
                and math.isfinite(settled_time) and 0<=settled_time<=2
                and abs(settled_time-paused_time)<=.05,
                'paused visual playback clock did not settle')
        client=self.alive(player)
        monitors=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
        self.trace('visual-capture-before',player=player,client=client,monitors=monitors)
        require(str(client.get('id'))==player['client_id'] and client.get('pid')==player['pid'],
                'visual capture client identity differs from owned proof')
        monitor,geometry,crop=visual_capture_geometry(client,monitors)
        x,y,w,h=[crop[key] for key in ('x','y','width','height')]
        image=self.root/'celluloid-reference.png'
        rgb=self.root/'visual-owned-window.rgb'
        attempt_limit=1
        capture_command_timeout_seconds=3
        retry_settle_seconds=.5
        capture_deadline_seconds=(attempt_limit * 2 * capture_command_timeout_seconds
                                  + (attempt_limit-1) * retry_settle_seconds + 3.5)
        capture_deadline=time.monotonic()+capture_deadline_seconds
        attempts=[]; after=None; monitors_after=None; size=None; screenshot=None
        oracle=dict(status='unmatched',reason='No capture attempted')
        for attempt in range(1,attempt_limit+1):
            if attempt>1:
                remaining=capture_deadline-time.monotonic()
                require(remaining>.5,'visual capture retry deadline exhausted')
                time.sleep(retry_settle_seconds)
                client_now=self.alive(player)
                monitors_now=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
                monitor_now,geometry_now,crop_now=visual_capture_geometry(client_now,monitors_now)
                require(all(client_now.get(key)==client.get(key) for key in ('id','pid','is_visible','is_focused','monitor'))
                        and geometry_now==geometry and crop_now==crop
                        and all(monitor_now.get(key)==monitor.get(key) for key in ('name','x','y','width','height','scale','is_hdr')),
                        'owned player identity/geometry/focus or monitor changed before recapture')
            remaining=capture_deadline-time.monotonic()
            require(remaining>.1,'visual capture retry deadline exhausted')
            self.cmd(['grim','-o',monitor['name'],str(image)],timeout=min(capture_command_timeout_seconds,remaining))
            screenshot=dict(path=str(image),sha256=digest(image),
                review='static content oracle plus human review; screencopy can request repaint')
            # The PNG header supplies actual physical pixel dimensions, not a config guess.
            header=image.read_bytes()[:24]
            require(header[:8]==b'\x89PNG\r\n\x1a\n' and header[12:16]==b'IHDR','invalid reference capture PNG')
            size=list(struct.unpack('>II',header[16:24]))
            require(size==[monitor['width'],monitor['height']],'actual screencopy/monitor dimensions differ')
            after=self.alive(player)
            monitors_after=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
            self.trace('visual-capture-after',player=player,client=after,monitors=monitors_after,attempt=attempt)
            monitor_after,geometry_after,crop_after=visual_capture_geometry(after,monitors_after)
            require(all(after.get(key)==client.get(key) for key in ('id','pid','is_visible','is_focused','monitor'))
                    and geometry_after==geometry and crop_after==crop
                    and all(monitor_after.get(key)==monitor.get(key) for key in ('name','x','y','width','height','scale','is_hdr')),
                    'owned player identity/geometry/focus or monitor changed across capture')
            remaining=capture_deadline-time.monotonic()
            require(remaining>.1,'visual capture retry deadline exhausted')
            self.cmd(common+['-i',str(image),'-frames:v','1','-vf',f'crop={w}:{h}:{x}:{y}',
                             '-pix_fmt','rgb24','-f','rawvideo',str(rgb)],timeout=min(capture_command_timeout_seconds,remaining))
            try:
                oracle=evaluate_reference_rgb(rgb.read_bytes(),w,h,expected.read_bytes())
            except Exception as exc:
                oracle=dict(status='failed',error=type(exc).__name__+': '+str(exc))
            attempt_time=mpv_property(ipc,'time-pos',player['pid'],self.uid)
            require(type(attempt_time) in (int,float) and not isinstance(attempt_time,bool)
                    and math.isfinite(attempt_time) and 0<=attempt_time<=2,
                    'capture-attempt playback clock is invalid')
            attempts.append(dict(attempt=attempt,screenshot_sha256=screenshot['sha256'],
                actual_rgb_sha256=digest(rgb),oracle=oracle,playback_time_seconds=attempt_time,
                owned_identity_geometry_unchanged=True))
            # Preserve bounded, content-free attempt evidence even when a later
            # deadline check fails before the final full oracle is assembled.
            (self.root/'visual-oracle.json').write_text(json.dumps(dict(
                schema='arctic-native-visual-attempts-v1',release_acceptance=False,
                capture_attempts=attempts,capture_attempt_limit=attempt_limit,
                capture_deadline_seconds=capture_deadline_seconds),indent=2)+'\n')
            if oracle.get('status')=='matched': break
        if getattr(self,'gui_v6',False):
            self.fullscreen_capture_pair(player,client,after,screenshot)
        info=dict(player=player,player_state=state,client_before=client,client_after=after,monitors=monitors,monitors_after=monitors_after,screenshot=screenshot,
                  fixture_sha256=digest(fixture),input_rgb_sha256=source_sha,expected_rgb_sha256=digest(expected),actual_rgb_sha256=digest(rgb),
                  expected_rgb_path=str(expected),actual_rgb_path=str(rgb),capture_pixels=size,
                  client_pixel_crop=dict(x=x,y=y,width=w,height=h),default_render_options=True,
                  playback_clock=dict(pre_geometry_seconds=pre_geometry_time,initial_seconds=initial_time,
                                      advanced_seconds=advanced_time,paused_seconds=paused_time,
                                      settled_seconds=settled_time,capture_paused=True,
                                      presentation_refresh='frame-step',
                                      maximum_settled_drift_seconds=.05,
                                      minimum_advance_seconds=minimum_post_geometry_advance,
                                      anchor='after fullscreen and controls transitions'),
                  capture_attempts=attempts,capture_attempt_limit=attempt_limit,capture_deadline_seconds=capture_deadline_seconds,
                  accepted_capture_attempt=len(attempts) if oracle.get('status')=='matched' else None,
                  player_attempt=player_attempt,player_attempt_limit=player_attempt_limit,
                  product_renderer=renderer,fixture_transition=transition,fixture_cadence=visual_reference_cadence(),
                  command_options=['--no-existing-session','--new-window','--mpv-input-ipc-server=<owned socket>','--mpv-loop-file=inf'],
                  scope='separate pulsed 16-color FFV1 visual fixture; strict captured-frame content only, not perceived motion, audio or hardware')
        if getattr(self,'gui_v6',False):
            info['capture_precondition']=controls
        info['oracle']=oracle
        player_receipt={key:info[key] for key in ('player_attempt','player','player_state','fixture_sha256','input_rgb_sha256',
            'expected_rgb_sha256','actual_rgb_sha256','playback_clock','capture_attempts','capture_attempt_limit',
            'capture_deadline_seconds','accepted_capture_attempt','oracle','screenshot','product_renderer','fixture_transition')}
        player_receipt.update(owned_player_cleanup_completed=False,restart_eligible=False,release_acceptance=False)
        info['player_attempts']=[player_receipt]
        info['accepted_player_attempt']=1 if oracle.get('status')=='matched' else None
        (self.root/'visual-oracle.json').write_text(json.dumps(info,indent=2))
        self.trace('visual-oracle',proof=info)
        if getattr(self,'gui_v6',False):
            self.native_protocol_diagnostic(player,state,screenshot,client)
            self.player_fullscreen(player,False,ipc)
            self.finish_native_protocol()
        require(info['oracle']['status']=='matched',
                'actual static visual fixture content unmatched; rendered-content gate remains open')
        return info

    def media_fixture(self):
        """Content check is independently runnable without any compositor or guest."""
        video,audio,fixture = [self.root/name for name in ('source.yuv','source.pcm','open-codec-fixture.mkv')]
        common = ['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        self.cmd(common+['-f','lavfi','-i','testsrc2=size=160x120:rate=10','-frames:v','20',
                         '-pix_fmt','yuv420p','-f','rawvideo',str(video)])
        self.cmd(common+['-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=2',
                         '-ac','1','-c:a','pcm_s16le','-f','s16le',str(audio)])
        self.cmd(common+['-f','rawvideo','-pixel_format','yuv420p','-video_size','160x120','-framerate','10',
            '-i',str(video),'-f','s16le','-ar','48000','-ac','1','-i',str(audio),
            '-c:v','ffv1','-level','3','-c:a','pcm_s16le','-t','2','-f','matroska',str(fixture)])
        decoded_video,decoded_audio = self.root/'decoded.yuv',self.root/'decoded.pcm'
        self.cmd(common+['-i',str(fixture),'-map','0:v:0','-pix_fmt','yuv420p','-f','rawvideo',str(decoded_video)])
        self.cmd(common+['-i',str(fixture),'-map','0:a:0','-ac','1','-ar','48000','-f','s16le',str(decoded_audio)])
        require(video.stat().st_size == 576000 and audio.stat().st_size == 192000,
                'generated fixture duration/format mismatch')
        require(digest(video)==digest(decoded_video) and digest(audio)==digest(decoded_audio),
                'FFV1/PCM decoder content differs from generated source')
        decoder = dict(video_sha256=digest(video),audio_sha256=digest(audio),
                       fixture_sha256=digest(fixture),scope='FFmpeg CPU decode; no GUI or proprietary-codec claim')
        return fixture,decoder

    def desktop_services(self):
        portal = {}
        for interface in ('FileChooser','OpenURI'):
            answer = self.cmd(['gdbus','call','--session','--dest','org.freedesktop.portal.Desktop',
                '--object-path','/org/freedesktop/portal/desktop','--method','org.freedesktop.DBus.Properties.Get',
                'org.freedesktop.portal.'+interface,'version'],original=True,timeout=20)[1]
            require(re.search(r'uint32\s+[1-9][0-9]*',answer), 'portal did not expose a positive interface version')
            portal[interface] = answer
        enabled = self.cmd(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus',
            '--method','org.freedesktop.DBus.Properties.Get','org.a11y.Status','IsEnabled'],original=True,timeout=15)[1]
        reply = self.cmd(['gdbus','call','--session','--dest','org.a11y.Bus','--object-path','/org/a11y/bus',
            '--method','org.a11y.Bus.GetAddress'],original=True,timeout=15)[1]
        address = ast.literal_eval(reply)[0]
        require(isinstance(address,str) and address.startswith('unix:') and ';' not in address and len(address)<2048,
                'unexpected accessibility bus address')
        registry = self.cmd(['gdbus','call','--address',address,'--dest','org.a11y.atspi.Registry',
            '--object-path','/org/a11y/atspi/accessible/root','--method','org.a11y.atspi.Accessible.GetChildren'],
            original=True,timeout=15)[1]
        return dict(portal_versions=portal,a11y_enabled=enabled,a11y_registry_children=registry,
                    scope='read-only live DBus reachability; no chooser roundtrip, app-tree or screen-reader qualification',
                    safe_baseline='original v1.2 Safe/TCG already timed out starting the portal; current failure still requires review')

    def cleanup(self):
        errors = []
        for proof in reversed(self.owned):
            try:
                # Pin the process before the final identity read, preventing a
                # PID recycle between comparison and signal from hitting another app.
                descriptor = os.pidfd_open(proof['pid'])
                try:
                    current = identity(proof['pid'],self.uid)
                    if all(current[key] == proof[key] for key in ('pid','start_ticks','executable')):
                        signal.pidfd_send_signal(descriptor,signal.SIGTERM)
                finally:
                    os.close(descriptor)
                def retired():
                    try:
                        now = identity(proof['pid'],self.uid)
                        return any(now[key] != proof[key] for key in ('pid','start_ticks','executable'))
                    except (FileNotFoundError,ProcessLookupError,RuntimeError):
                        return True
                self.wait(retired,5)
            except (FileNotFoundError,ProcessLookupError):
                pass
            except Exception as exc:
                errors.append(str(exc))
        for child in self.launches:
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                # This is our own direct runuser wrapper, never a searched user PID.
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    errors.append('GUI wrapper did not exit; retained for guest diagnosis')
        for source,wanted in getattr(self,'copied',{}).items():
            require(digest(source)==wanted, 'original user config changed: '+source)
        require(not errors, 'cleanup identity review required: '+repr(errors))
        return dict(only_proved_new_processes_signalled=True,original_copied_configs_unchanged=True,
                    retained_tmp_evidence=str(self.root))


# BEGIN CONTROLLED_RENDERER_TRIALS
def renderer_trial_error(error):
    return {RuntimeError:'guard-error',OSError:'os-error',ValueError:'value-error',
            TypeError:'type-error',KeyError:'key-error',subprocess.TimeoutExpired:'timeout'}.get(type(error),'other-error')


def write_renderer_receipt(root,uid,value):
    raw=(json.dumps(value,sort_keys=True)+'\n').encode()
    require(len(raw)<=512*1024,'controlled renderer receipt exceeded bound')
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        require(os.fstat(directory).st_uid==uid,'controlled receipt directory owner differs')
        fd=os.open('0-controlled-renderer-trials.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                   0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:
            os.fchown(stream.fileno(),uid,-1)
            info=os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid==uid and info.st_nlink==1
                    and not info.st_mode&0o077,'controlled receipt file identity differs')
            stream.write(raw)
    finally: os.close(directory)


def retire_renderer_player(proof,uid):
    require(type(uid) is int and uid>0 and proof.get('executable')=='/usr/bin/celluloid'
            and all(type(proof.get(k)) is int and proof[k]>0 for k in ('pid','start_ticks')),
            'controlled cleanup requires proved native player identity')
    try: descriptor=os.pidfd_open(proof['pid'])
    except ProcessLookupError: return
    try:
        current=identity(proof['pid'],uid)
        require(all(current[k]==proof[k] for k in ('pid','start_ticks','executable'))
                and digest(current['executable'])==proof['executable_sha256'],
                'controlled cleanup player identity changed')
        signal.pidfd_send_signal(descriptor,signal.SIGTERM)
    finally: os.close(descriptor)
    until=time.monotonic()+5
    while time.monotonic()<until:
        try:
            current=identity(proof['pid'],uid)
            if any(current[k]!=proof[k] for k in ('pid','start_ticks','executable')): return
        except (FileNotFoundError,ProcessLookupError,RuntimeError): return
        time.sleep(.1)
    raise RuntimeError('controlled cleanup player survived bounded retirement')


class RendererTrialSmoke(Smoke):
    """One owned default/GL diagnostic, isolated from the primary receipt state."""
    def __init__(self,parent,mode):
        require(mode in ('default','gl'),'unsupported controlled renderer intervention')
        self.mode=mode; self.user=parent.user; self.uid=parent.uid; self.stage=parent.stage
        self.root=parent.root/('renderer-trial-'+mode)
        self.root.mkdir(mode=0o700); os.chown(self.root,self.uid,self.user.pw_gid)
        self.prefix=list(parent.prefix); self.original_prefix=list(parent.original_prefix)
        self.owned=[]; self.launches=[]; self.gui_v6=True
        self.deadline=time.monotonic()+120

    def trace(self,*args,**kwargs):
        pass  # No arbitrary client snapshots, stdout, stderr, argv or labels.

    def remaining(self):
        value=self.deadline-time.monotonic()
        require(value>0,'controlled renderer diagnostic time bound')
        return value

    def cmd(self,argv,*,original=False,**kwargs):
        require(original is False,'controlled renderer commands use isolated prefix')
        kwargs['timeout']=min(kwargs.get('timeout',45),self.remaining())
        return execute(self.prefix+argv,**kwargs)

    def clients(self):
        data=json.loads(self.cmd(['mmsg','get','all-clients'])[1])
        require(type(data) is dict and type(data.get('clients')) is list,
                'controlled renderer client collection differs')
        require(all(type(c) is dict and type(c.get('id')) is int for c in data['clients'])
                and len({c['id'] for c in data['clients']})==len(data['clients']),
                'controlled renderer client identities differ')
        return {str(c['id']):c for c in data['clients']}

    def wait(self,fn,timeout=30,label='functional observation'):
        return Smoke.wait(self,fn,min(timeout,self.remaining()),'controlled renderer observation')

    def launch_renderer(self,argv):
        require(argv[0]=='/usr/bin/celluloid','controlled renderer executable differs')
        drain=NativeProtocolDrain(renderer=True); reader=None; writer=None
        self.native_protocol_drain=drain
        try:
            read,writer=os.pipe()
            try: reader=os.fdopen(read,'rb',buffering=0)
            except BaseException:
                os.close(read); raise
            drain.start(reader)
            options=['env','-u','GSK_RENDERER','GSK_DEBUG=renderer','WAYLAND_DEBUG=client']
            if self.mode=='gl': options.append('GSK_RENDERER=gl')
            child=subprocess.Popen(self.prefix+options+argv,stdout=subprocess.DEVNULL,stderr=writer)
            self.launches.append(child)
        except BaseException:
            drain.finish(); raise
        finally:
            if writer is not None: os.close(writer)

    def fullscreen(self,player):
        before=self.alive(player)
        require(before.get('is_fullscreen') is False,'controlled player was not a fresh window')
        response=self.cmd(['mmsg','dispatch','togglefullscreen','client,'+player['client_id']])
        require(response[0]==0 and json.loads(response[1])=={'success':True},'controlled fullscreen action failed')
        self.wait(lambda:self.alive(player).get('is_fullscreen') is True,10)

    def gtk_binding(self,player):
        require(self.cmd(['rpm','-q','--qf','%{VERSION}','gtk4'])[1]=='4.22.5',
                'controlled renderer GTK source version differs')
        path=Path('/proc')/str(player['pid'])/'maps'
        require(path.stat().st_uid==self.uid,'controlled GTK maps owner differs')
        with path.open() as stream: raw=stream.read(LIMIT+1)
        require(len(raw)<=LIMIT,'controlled GTK maps exceeded bound')
        paths={Path(line.split(maxsplit=5)[5]).resolve(strict=True) for line in raw.splitlines()
               if len(line.split(maxsplit=5))==6 and Path(line.split(maxsplit=5)[5]).name.startswith('libgtk-4.so.')}
        require(len(paths)==1,'controlled player GTK mapping absent or ambiguous')
        library=paths.pop(); info=library.stat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid==0 and not info.st_mode&0o022,
                'controlled mapped GTK library unsafe')
        require(self.cmd(['rpm','-qf','--qf','%{NAME}:%{VERSION}',str(library)])[1]=='gtk4:4.22.5',
                'controlled mapped GTK package differs')
        self.alive(player)
        return dict(package='gtk4',version='4.22.5',mapped_library_sha256=digest(library))

    def observe(self,fixture,expected,source_sha):
        value=dict(intervention=self.mode,status='unknown',release_acceptance=False,
            requested_gsk_renderer='unset' if self.mode=='default' else 'gl',
            recording_flags=['GSK_DEBUG=renderer','WAYLAND_DEBUG=client'],
            command_options=['--no-existing-session','--new-window','--mpv-input-ipc-server=<owned socket>','--mpv-loop-file=inf'],
            settle_seconds=.5,diagnostic_time_bound_seconds=120,rendering_cause_proven=False)
        private=None
        try:
            ipc=self.root/'player.sock'
            player=self.fresh_window(lambda:self.launch_reference_player(['/usr/bin/celluloid','--no-existing-session',
                '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)],self.launch_renderer),'celluloid',r'celluloid')
            require(self.native_protocol_drain.bind(player,self.uid),'controlled owned stderr binding unavailable')
            value['player']={k:player[k] for k in ('pid','start_ticks','executable_sha256')}
            value['player'].update(uid=self.uid,client_id=int(player['client_id']),executable='/usr/bin/celluloid')
            value['gtk']=self.gtk_binding(player)
            self.wait(lambda:ipc.is_socket())
            def ready():
                try: return mpv_property(ipc,'video-params',player['pid'],self.uid)
                except RuntimeError as error:
                    args=BaseException.args.__get__(error)
                    if type(args) is tuple and len(args)==1 and type(args[0]) is str and args[0]=='mpv property unavailable: video-params': return None
                    raise
            self.wait(ready)
            state={k:mpv_property(ipc,k,player['pid'],self.uid)
                   for k in ('path','pause','video-params','current-vo','time-pos')}
            require(state['path']==str(fixture) and state['pause'] is False and state['current-vo']=='libmpv'
                    and type(state['video-params']) is dict and type(state['video-params'].get('w')) is int
                    and type(state['video-params'].get('h')) is int
                    and state['video-params']['w']==160 and state['video-params']['h']==120,
                    'controlled exact media state differs')
            require(type(state['time-pos']) in (int,float) and math.isfinite(state['time-pos'])
                    and 0<=state['time-pos']<=100000,'controlled playback time invalid')
            value['media']=dict(fixture_sha256=digest(fixture),expected_rgb_sha256=digest(expected),
                input_rgb_sha256=source_sha,decoded_video_dimensions=[160,120],pause=False,current_vo='libmpv',
                observed_time_seconds=state['time-pos'])
            require(json.loads(self.cmd(['mmsg','dispatch','focusid','client,'+player['client_id']])[1]).get('success') is True,
                    'controlled focus action failed')
            self.wait(lambda:self.alive(player).get('is_focused') is True,10)
            self.fullscreen(player)
            value['capture_precondition']=self.hide_reference_controls(player,ipc)
            time.sleep(.5)
            before=self.alive(player); monitors=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
            monitor,geometry,crop=visual_capture_geometry(before,monitors)
            require(before.get('is_fullscreen') is True and crop==dict(x=0,y=0,width=monitor['width'],height=monitor['height']),
                    'controlled capture requires full owned fullscreen viewport')
            image=self.root/'reference.png'
            require(not image.exists() and not image.is_symlink(),'controlled PNG path already exists')
            self.cmd(['grim','-o',monitor['name'],str(image)])
            info=image.lstat()
            require(stat.S_ISREG(info.st_mode) and info.st_uid==self.uid and info.st_nlink==1
                    and 0<info.st_size<=LIMIT,'controlled PNG identity or bound differs')
            header=image.read_bytes()[:24]
            require(header[:8]==b'\x89PNG\r\n\x1a\n' and header[12:16]==b'IHDR'
                    and list(struct.unpack('>II',header[16:24]))==[monitor['width'],monitor['height']],
                    'controlled PNG dimensions differ')
            after=self.alive(player); monitors_after=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
            monitor_after,geometry_after,crop_after=visual_capture_geometry(after,monitors_after)
            require(all(after.get(k)==before.get(k) for k in ('id','pid','is_visible','is_focused','is_fullscreen','monitor'))
                    and geometry_after==geometry and crop_after==crop
                    and all(monitor_after.get(k)==monitor.get(k) for k in ('name','x','y','width','height','scale','is_hdr')),
                    'controlled capture identity or geometry changed')
            value['capture']=dict(path='renderer-trial-'+self.mode+'/reference.png',sha256=digest(image),
                bytes=info.st_size,dimensions=[monitor['width'],monitor['height']],client_geometry=geometry,
                client_pixel_crop=crop,complete_owned_viewport=True,screencopy_may_request_repaint=True)
            private=Path(tempfile.mkdtemp(prefix='arctic-renderer-rgb-private-',dir='/tmp'))
            os.chown(private,self.uid,self.user.pw_gid)
            rgb=private/'frame.private'
            x,y,w,h=[crop[k] for k in ('x','y','width','height')]
            self.cmd(['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y','-i',str(image),'-frames:v','1',
                      '-vf',f'crop={w}:{h}:{x}:{y}','-pix_fmt','rgb24','-f','rawvideo',str(rgb)])
            require(rgb.stat().st_size==w*h*3<=LIMIT,'controlled raw RGB frame bound differs')
            value['actual_rgb_sha256']=digest(rgb)
            require(digest(fixture)==value['media']['fixture_sha256'] and digest(expected)==value['media']['expected_rgb_sha256'],
                    'controlled fixture changed during capture')
            value['oracle']=evaluate_reference_rgb(rgb.read_bytes(),w,h,expected.read_bytes())
            value['protocol']=self.native_protocol_drain.snapshot(player,self.uid)
            value['realized_renderer']=value['protocol']['realized_renderer']
            value['status']='observed' if value['realized_renderer']['status']=='reported-realized' else 'unknown'
            value['requested_renderer_matched']=value['realized_renderer']['renderer']=='gl' if self.mode=='gl' else None
        except Exception as error:
            value['error']=renderer_trial_error(error)
        finally:
            if private is not None:
                try: shutil.rmtree(private)
                except OSError: value['private_rgb_cleanup_completed']=False
        return value
# END CONTROLLED_RENDERER_TRIALS


# BEGIN CONTROLLED_CONTROLS_STUDY
def write_controls_receipt(root,uid,value):
    raw=(json.dumps(value,sort_keys=True)+'\n').encode()
    require(len(raw)<=512*1024,'controlled renderer receipt exceeded bound')
    directory=os.open(root,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
    try:
        require(os.fstat(directory).st_uid==uid,'controlled receipt directory owner differs')
        fd=os.open('0-controls-state-trials.json',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                   0o600,dir_fd=directory)
        with os.fdopen(fd,'wb') as stream:
            os.fchown(stream.fileno(),uid,-1)
            info=os.fstat(stream.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid==uid and info.st_nlink==1
                    and not info.st_mode&0o077,'controlled receipt file identity differs')
            stream.write(raw)
    finally: os.close(directory)



class ControlsTrialSmoke(RendererTrialSmoke):
    """Same default renderer/capture, changing only private initial controls state."""
    def __init__(self,parent,state):
        require(type(state) is str and state in ('transition','hidden'),
                'unsupported controls state intervention')
        self.mode='default'; self.state=state
        self.initial_visible=state=='transition'
        self.user=parent.user; self.uid=parent.uid; self.stage=parent.stage
        self.root=parent.root/('controls-trial-'+state)
        self.root.mkdir(mode=0o700); os.chown(self.root,self.uid,self.user.pw_gid)
        self.prefix=list(parent.prefix); self.original_prefix=list(parent.original_prefix)
        self.owned=[]; self.launches=[]; self.gui_v6=True
        self.deadline=time.monotonic()+120

    def seed_controls(self):
        self.reference_settings_config()
        require(not any(x.startswith('GSETTINGS_BACKEND=') for x in self.prefix),
                'controls trial settings backend already selected')
        key=['/usr/bin/env','GSETTINGS_BACKEND=keyfile','/usr/bin/gsettings']
        schema=['io.github.celluloid-player.Celluloid.window-state','show-controls']
        wanted='true' if self.initial_visible else 'false'
        result=self.cmd(key+['set']+schema+[wanted],timeout=5)
        require(result[0]==0,'controls trial private setting write failed')
        result=self.cmd(key+['get']+schema,timeout=5)
        require(result[0]==0 and result[1]==wanted,'controls trial private initial state differs')
        return dict(initial_visible=self.initial_visible,settings_backend='keyfile',
                    private_config_verified=True,seed_readback_matched=True,
                    setting='window-state show-controls',release_acceptance=False)

    def hide_reference_controls(self,player,ipc):
        value=super().hide_reference_controls(player,ipc)
        require(type(value.get('before_visible')) is bool and value['before_visible']==self.initial_visible
                and value.get('after_visible') is False and value.get('private_config_process_bound') is True,
                'controls trial process-bound initial or hidden state differs')
        return value

    def observe(self,fixture,expected,source_sha):
        # A failed seed aborts before launch; no fallback or guessed initial state.
        seed=self.seed_controls()
        value=super().observe(fixture,expected,source_sha)
        value['intervention']=self.state
        value['controls_seed']=seed
        value['controls_history']=dict(initial_visible=self.initial_visible,action='win.set-controls-visible(false)',
            desired_final_visible=False,comparison='true-to-false' if self.initial_visible else 'false-to-false',
            setting_readback_not_framebuffer_attestation=True,release_acceptance=False)
        if 'capture' in value:
            # Inherited capture writes this exact owned directory; this is its
            # source-controlled relative filename, not a new image or conversion.
            value['capture']['path']='controls-trial-'+self.state+'/reference.png'
        return value
# END CONTROLLED_CONTROLS_STUDY


def mpv_replace_fixture(path, expected_pid, expected_uid, source, target):
    """Replace one exact owned fixture on the already presented Celluloid player."""
    require(type(expected_pid) is int and expected_pid>1 and type(expected_uid) is int and expected_uid>0
            and isinstance(source,Path) and isinstance(target,Path)
            and source.is_absolute() and target.is_absolute() and source.parent==target.parent
            and source.name=='open-codec-fixture.mkv' and target.name=='visual-reference.mkv',
            'Celluloid fixture transition identity/path is invalid')
    info=Path(path).lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid==expected_uid,
            'Celluloid fixture transition IPC path owner/type differs')
    request_id=48;command=['loadfile',str(target),'replace']
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
        peer.settimeout(2);peer.connect(str(path))
        pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require((pid,uid)==(expected_pid,expected_uid),'Celluloid fixture transition IPC peer differs')
        peer.sendall(json.dumps(dict(command=command,request_id=request_id),separators=(',',':')).encode()+b'\n')
        data=b'';deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            chunk=peer.recv(4096)
            require(chunk,'Celluloid fixture transition IPC disconnected before acknowledgement')
            data+=chunk;require(len(data)<=4096,'Celluloid fixture transition IPC reply exceeded bound')
            while b'\n' in data:
                line,data=data.split(b'\n',1)
                def pairs(items):
                    value={}
                    for key,item in items:
                        require(key not in value,'Celluloid fixture transition IPC duplicate field')
                        value[key]=item
                    return value
                message=json.loads(line,object_pairs_hook=pairs)
                require(type(message) is dict,'Celluloid fixture transition IPC reply is not an object')
                if message.get('request_id')==request_id:
                    require(type(message['request_id']) is int and message.get('error')=='success'
                            and message.get('data') is None,'Celluloid fixture transition IPC command failed')
                    return dict(schema='arctic-native-fixture-transition-v1',
                        transport='owned mpv IPC SO_PEERCRED',source=str(source),target=str(target),
                        command=command,request_id=request_id,acknowledgement=message,
                        same_process_renderer_required=True,release_acceptance=False)
        raise RuntimeError('Celluloid fixture transition IPC acknowledgement timed out')


def mpv_celluloid_fullscreen(path, expected_pid, expected_uid, enabled):
    """Use Celluloid's supported per-window fullscreen action on its owned IPC."""
    require(type(expected_pid) is int and expected_pid>1 and type(expected_uid) is int and expected_uid>0
            and type(enabled) is bool, 'Celluloid fullscreen IPC identity/state is invalid')
    info=Path(path).lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid==expected_uid,
            'Celluloid fullscreen IPC path owner/type differs')
    request_id=46 if enabled else 47
    action='win.enter-fullscreen' if enabled else 'win.leave-fullscreen'
    command=['script-message','celluloid-action',action]
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(str(path))
        pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require((pid,uid)==(expected_pid,expected_uid), 'Celluloid fullscreen IPC peer differs')
        peer.sendall(json.dumps(dict(command=command,request_id=request_id),separators=(',',':')).encode()+b'\n')
        data=b''; deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            chunk=peer.recv(4096)
            require(chunk, 'Celluloid fullscreen IPC disconnected before acknowledgement')
            data+=chunk
            require(len(data)<=4096, 'Celluloid fullscreen IPC reply exceeded bound')
            while b'\n' in data:
                line,data=data.split(b'\n',1)
                def pairs(items):
                    value={}
                    for key,item in items:
                        require(key not in value, 'Celluloid fullscreen IPC duplicate field')
                        value[key]=item
                    return value
                message=json.loads(line,object_pairs_hook=pairs)
                require(type(message) is dict, 'Celluloid fullscreen IPC reply is not an object')
                if message.get('request_id')==request_id:
                    require(type(message['request_id']) is int and message.get('error')=='success'
                            and message.get('data') is None, 'Celluloid fullscreen IPC command failed')
                    return dict(transport='owned mpv IPC SO_PEERCRED',command=command,
                                request_id=request_id,acknowledgement=message)
        raise RuntimeError('Celluloid fullscreen IPC acknowledgement timed out')


def mpv_hide_reference_controls(path, expected_pid, expected_uid):
    """The sole supported fixed per-window UI command; never an arbitrary action."""
    require(type(expected_pid) is int and expected_pid>1 and type(expected_uid) is int and expected_uid>0,
            'reference controls IPC identity is invalid')
    info=Path(path).lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid==expected_uid,
            'reference controls IPC path owner/type differs')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(str(path))
        pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require((pid,uid)==(expected_pid,expected_uid), 'reference controls IPC peer differs')
        peer.sendall(b'{"command":["script-message","celluloid-action","win.set-controls-visible(false)"],"request_id":43}\n')
        data=b''; deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            chunk=peer.recv(4096)
            require(chunk, 'reference controls IPC disconnected before acknowledgement')
            data+=chunk
            require(len(data)<=4096, 'reference controls IPC reply exceeded bound')
            while b'\n' in data:
                line,data=data.split(b'\n',1)
                def pairs(items):
                    value={}
                    for key,item in items:
                        require(key not in value, 'reference controls IPC duplicate field')
                        value[key]=item
                    return value
                message=json.loads(line,object_pairs_hook=pairs)
                require(type(message) is dict, 'reference controls IPC reply is not an object')
                if message.get('request_id')==43:
                    require(type(message['request_id']) is int and message.get('error')=='success'
                            and message.get('data') is None, 'reference controls IPC command failed')
                    return
        raise RuntimeError('reference controls IPC acknowledgement timed out')


def mpv_pause_reference(path, expected_pid, expected_uid):
    """Pause and present one complete frame through the proved player's IPC."""
    require(type(expected_pid) is int and expected_pid>1 and type(expected_uid) is int and expected_uid>0,
            'reference pause IPC identity is invalid')
    info=Path(path).lstat()
    require(stat.S_ISSOCK(info.st_mode) and info.st_uid==expected_uid,
            'reference pause IPC path owner/type differs')
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(str(path))
        pid,uid,_=struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require((pid,uid)==(expected_pid,expected_uid), 'reference pause IPC peer differs')
        # Process both controls on the same authenticated, ordered connection.
        # frame-step keeps mpv paused but forces the GL video surface to present
        # a complete post-fullscreen frame instead of retaining a blank buffer.
        peer.sendall(b'{"command":["set_property","pause",true],"request_id":44}\n'
                     b'{"command":["frame-step"],"request_id":45}\n')
        data=b''; deadline=time.monotonic()+3
        acknowledged=set()
        while time.monotonic()<deadline:
            chunk=peer.recv(4096)
            require(chunk, 'reference pause IPC disconnected before acknowledgement')
            data+=chunk
            require(len(data)<=4096, 'reference pause IPC reply exceeded bound')
            while b'\n' in data:
                line,data=data.split(b'\n',1)
                def pairs(items):
                    value={}
                    for key,item in items:
                        require(key not in value, 'reference pause IPC duplicate field')
                        value[key]=item
                    return value
                message=json.loads(line,object_pairs_hook=pairs)
                require(type(message) is dict, 'reference pause IPC reply is not an object')
                if message.get('request_id') in (44,45):
                    require(type(message['request_id']) is int and message.get('error')=='success'
                            and message.get('data') is None, 'reference pause IPC command failed')
                    require(message['request_id'] not in acknowledged,
                            'reference pause IPC duplicate acknowledgement')
                    acknowledged.add(message['request_id'])
                    if acknowledged=={44,45}: return
        raise RuntimeError('reference pause IPC acknowledgement timed out')


def mpv_property(path, key, expected_pid, expected_uid):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as peer:
        peer.settimeout(2)
        peer.connect(str(path))
        pid,uid,_ = struct.unpack('3i',peer.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        require((pid,uid)==(expected_pid,expected_uid), 'player IPC belongs to a different process/user')
        peer.sendall(json.dumps(dict(command=['get_property',key],request_id=42)).encode()+b'\n')
        data=b''
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            chunk=peer.recv(65536)
            require(chunk, 'player IPC disconnected before reply')
            data+=chunk
            require(len(data)<LIMIT,'unbounded player IPC reply')
            while b'\n' in data:
                line,data=data.split(b'\n',1)
                message=json.loads(line)
                if message.get('request_id')==42:
                    require(message.get('error')=='success', 'mpv property unavailable: '+key)
                    return message.get('data')
        raise RuntimeError('player IPC request timed out')


def validate_player_samples(samples, fixture):
    require(len(samples)>=2, 'no advancing playback evidence')
    for sample in samples:
        require(sample.get('path')==fixture and sample.get('pause') is False, 'wrong file or paused player')
        require(sample.get('current-vo')=='libmpv', 'player is not using its GUI renderer')
        require(sample.get('current-ao') not in (None,'','null'), 'no real audio output backend opened')
        require(isinstance(sample.get('video-params'),dict) and sample['video-params'].get('w')==160
                and sample['video-params'].get('h')==120, 'no decoded video parameters')
        for key in ('audio-params','audio-out-params'):
            require(isinstance(sample.get(key),dict) and sample[key].get('samplerate',0)>0,
                    'no decoded/input-output audio parameters')
        require(type(sample.get('time-pos')) in (int,float)
                and math.isfinite(sample['time-pos']) and 0 <= sample['time-pos'] <= 2.1,
                'invalid or missing fixture playback clock')
    values=[s['time-pos'] for s in samples]
    require(max(values)-min(values)>.2, 'playback clock did not advance')


def run_checks(prefix, stage, *, disposable_guest=False, gui_v6=False):
    guest_guard(stage,disposable_guest)
    security=SecurityInterval()
    require(type(gui_v6) is bool, "explicit native GUI diagnostic switch must be Boolean")
    smoke=Smoke(prefix,stage)
    smoke.gui_v6=gui_v6
    try:
        ready=smoke.gate('fresh-defaults-and-isolation',smoke.setup)
        if ready:
            smoke.gate('archive-content-roundtrips',smoke.archives)
            smoke.gate('actual-role-file-manager-terminal-editor',smoke.gui_files_editor_terminal)
            smoke.gate('open-codec-content-and-player-state',smoke.media)
            smoke.gate('portal-and-accessibility-reachability',smoke.desktop_services)
    finally:
        smoke.gate('owned-process-cleanup-config-preservation',smoke.cleanup)
        smoke.gate('selinux-and-new-avcs',security.finish)
        smoke.finish_native_protocol()
    report=dict(schema=SCHEMA,stage=stage,status='failed' if any(g['status']=='failed' for g in smoke.gates)
                else 'limited-smoke-passed',release_acceptance=False,gates=smoke.gates,steps=smoke.steps,
                proven_new_processes=smoke.owned,diagnostic_trace=dict(path=str(smoke.root/'gui-trace.log'),
                    bytes=smoke.trace_bytes,omitted_records=smoke.trace_omitted,client_observations=smoke.client_observations),
                evidence_root=str(smoke.root),remaining=['GUI archive create/edit/encryption UX',
                'portal chooser actual returned-file roundtrip','screen reader and per-app accessible trees',
                'perceived video/audio and additional codecs','offline live/install/reboot phases',
                'browser sandbox existing independent gate','hardware/gaming and recovery boot/Secure Boot'])
    if gui_v6:
        report['diagnostic_controls']=dict(gui_v6=True,editor_physical_save=True,owned_player_fullscreen=True,accessibility_proof=False)
    (smoke.root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(report,ensure_ascii=False,separators=(',',':')),flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage',choices=('live','installed'),required=True)
    parser.add_argument('--disposable-guest',action='store_true',required=True)
    args=parser.parse_args()
    require(Path(__file__).resolve()==Path('/run/t/native_smoke.py'), 'copy only into the reviewed /run/t guest bundle')
    report=run_checks(discover_desktop(),args.stage,disposable_guest=args.disposable_guest)
    return int(report['status']=='failed')


if __name__=='__main__':
    raise SystemExit(main())
