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
import socket
import stat
import struct
import subprocess
import tempfile
import time


SCHEMA = 'arctic-native-functional-smoke-v4'
ROLES = dict(terminal='foot', browser='epiphany', editor='featherpad', files='pcmanfm')
MIMES = {'inode/directory': 'pcmanfm.desktop', 'text/plain': 'featherpad.desktop',
         'video/x-matroska': 'io.github.celluloid_player.Celluloid.desktop',
         'application/zip': 'xarchiver.desktop'}
AVC = re.compile(r'avc:\s*denied|type=(?:USER_)?AVC\b', re.I)
LIMIT = 4 * 1024 * 1024


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


def verify_security(before, after, new_messages):
    require(before['selinux'] == after['selinux'] == 'Enforcing', 'SELinux must remain Enforcing')
    require(after['audit']['enabled'] == before['audit']['enabled'], 'kernel audit mode changed during checks')
    require(after['audit']['lost'] == before['audit']['lost'], 'audit records were lost during checks')
    denied = [line for line in new_messages.splitlines() if AVC.search(line)]
    require(not denied, 'new AVC requires investigation: ' + '\n'.join(denied[:20]))
    return dict(selinux=after['selinux'], audit=after['audit'], observed_new_avcs=0,
                audit_enabled=after['audit']['enabled'] in (1,2),
                scope='journal cursor and available audit-file interval; disabled kernel audit is a recorded telemetry limit')


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

    def finish(self):
        after = self.state()
        journal = execute(['journalctl', '-b', '--no-pager', '--after-cursor', self.cursor,
                           '-o', 'json'], timeout=60)[1]
        messages = '\n'.join(str(json.loads(line).get('MESSAGE', ''))
                             for line in journal.splitlines() if line)
        if self.audit_offset:
            info = self.audit_file.stat()
            dev, ino, offset = self.audit_offset
            require((info.st_dev, info.st_ino) == (dev, ino) and info.st_size >= offset,
                    'audit log rotated/truncated; interval must be reviewed separately')
            require(info.st_size - offset <= LIMIT, 'audit interval exceeded evidence bound')
            with self.audit_file.open('rb') as stream:
                stream.seek(offset)
                messages += '\n' + stream.read(LIMIT).decode(errors='replace')
        elif self.audit_file.exists():
            # The new file may include records not forwarded to the journal.
            require(self.audit_file.stat().st_size <= LIMIT, 'new audit log exceeded evidence bound')
            messages += '\n' + self.audit_file.read_text(errors='replace')
        return verify_security(self.before, after, messages)


def discover_desktop():
    """Actual login environment, including post-exec Mango IPC and Xwayland DISPLAY."""
    sessions = []
    fields = ('PATH', 'XDG_DATA_DIRS', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME',
              'DISPLAY', 'XAUTHORITY', 'LANG', 'XDG_CURRENT_DESKTOP', 'XDG_SESSION_ID',
              'QT_QPA_PLATFORM', 'GDK_BACKEND', 'MANGO_SOCKET')
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
        self.keys(proof,'-M','ctrl','-k','l','-m','ctrl')
        time.sleep(.3)
        self.diagnostic(label+'-location-focused')
        self.keys(proof,'-M','ctrl','-k','a','-m','ctrl')
        self.keys(proof,str(directory))
        time.sleep(.3)
        self.diagnostic(label+'-path-typed')
        self.keys(proof,'-k','Return')
        self.wait(lambda:directory.name in self.alive(proof).get('title',''),30,
                  label='PCManFM directory title after Return: '+directory.name)
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

    def keys(self, proof, *argv):
        self.alive(proof)
        self.trace('input-turn-before', proof=proof, argv=list(argv), client=self.alive(proof))
        response=self.cmd(['mmsg','dispatch','focusid','client,'+proof['client_id']])[1]
        require(json.loads(response).get('success') is True, 'compositor did not acknowledge owned focus target')
        self.wait(lambda:self.alive(proof).get('is_focused') is True,10)
        # Known virtual-keyboard first-event loss: warm up with a harmless modifier.
        self.cmd(['wtype','-s','200','-k','Shift_L','-s','150',*argv],timeout=30)
        self.trace('input-turn-after', proof=proof, argv=list(argv), client=self.alive(proof))

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
        return dict(role_terminal=role_terminal,role_editor=editor,role_files=files,
                    file_manager_foot=terminal,file_manager_zip_opener=archiver,
                    terminal_execution=proof,gui_saved=dict(path=str(fixture),sha256=digest(fixture),bytes=len(wanted)),
                    screenshots=[editor_shot,self.screenshot('files-opened-zip')],
                    scope='actual role launch + PCManFM file opener/F4 + GUI Unicode edit/save; mount/network/a11y remain separate')

    def media(self):
        fixture,decoder = self.media_fixture()
        self.gates.append(dict(check='open-codec-lossless-command-decode',status='passed',value=decoder))
        ipc = self.root/'celluloid-ipc.sock'
        player = self.fresh_window(lambda:self.launch(['/usr/bin/celluloid','--no-existing-session',
            '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)]),
            'celluloid',r'celluloid')
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
        for _ in range(8):
            sample = {key:mpv_property(ipc,key,player['pid'],self.uid)
                      for key in ('path','time-pos','pause','video-params','audio-params','audio-out-params','current-vo','current-ao')}
            samples.append(sample)
            self.alive(player)
            time.sleep(.35)
        validate_player_samples(samples,str(fixture))
        maps = Path('/proc')/str(player['pid'])/'maps'
        require('libmpv.so' in maps.read_text(), 'Celluloid PID has no mapped libmpv')
        moving_shot=self.screenshot('celluloid-playing')
        moving_proof=dict(decoder=decoder,player=player,player_samples=samples,screenshot=moving_shot,
                          client=self.alive(player),scope='original moving testsrc2 decode/advancing AV state retained; this frame still requires visual review')
        (self.root/'moving-player-proof.json').write_text(json.dumps(moving_proof,indent=2))
        visual=self.visual_media()
        return dict(moving_proof, visual_reference=visual,
                    scope='original moving fixture lossless decode/advancing AV state plus separate static rendered-content oracle; motion/perceived audio/hardware remain unqualified')

    def visual_fixture(self):
        source=self.write('visual-reference-input.raw',visual_reference_frame()*20)
        fixture=self.root/'visual-reference.mkv'
        expected=self.root/'visual-reference-frame.rgb'
        common=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        self.cmd(common+['-f','rawvideo','-pixel_format','rgb24','-video_size','160x120','-framerate','10',
            '-i',str(source),'-an','-c:v','ffv1','-level','3','-pix_fmt','yuv420p','-t','2',str(fixture)])
        self.cmd(common+['-i',str(fixture),'-frames:v','1','-pix_fmt','rgb24','-f','rawvideo',str(expected)])
        require(expected.stat().st_size==160*120*3,'reference decoded RGB frame size differs')
        return fixture,expected,digest(source)

    def visual_media(self):
        fixture,expected,source_sha=self.visual_fixture()
        common=['ffmpeg','-nostdin','-hide_banner','-loglevel','error','-y']
        ipc=self.root/'visual-reference-ipc.sock'
        player=self.fresh_window(lambda:self.launch(['/usr/bin/celluloid','--no-existing-session',
            '--new-window','--mpv-input-ipc-server='+str(ipc),'--mpv-loop-file=inf',str(fixture)]),
            'celluloid',r'celluloid')
        self.wait(lambda:ipc.is_socket())
        def ready_reference():
            try:
                return mpv_property(ipc,'video-params',player['pid'],self.uid)
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
        time.sleep(.5)
        client=self.alive(player)
        monitors=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
        self.trace('visual-capture-before',player=player,client=client,monitors=monitors)
        require(str(client.get('id'))==player['client_id'] and client.get('pid')==player['pid'],
                'visual capture client identity differs from owned proof')
        monitor,geometry,crop=visual_capture_geometry(client,monitors)
        x,y,w,h=[crop[key] for key in ('x','y','width','height')]
        image=self.root/'celluloid-reference.png'
        self.cmd(['grim','-o',monitor['name'],str(image)])
        screenshot=dict(path=str(image),sha256=digest(image),review='static content oracle plus human review; screencopy can request repaint')
        # The PNG header supplies actual physical pixel dimensions, not a config guess.
        header=image.read_bytes()[:24]
        require(header[:8]==b'\x89PNG\r\n\x1a\n' and header[12:16]==b'IHDR','invalid reference capture PNG')
        size=list(struct.unpack('>II',header[16:24]))
        require(size==[monitor['width'],monitor['height']],'actual screencopy/monitor dimensions differ')
        after=self.alive(player)
        monitors_after=json.loads(self.cmd(['mmsg','get','all-monitors'])[1])
        self.trace('visual-capture-after',player=player,client=after,monitors=monitors_after)
        monitor_after,geometry_after,crop_after=visual_capture_geometry(after,monitors_after)
        require(all(after.get(key)==client.get(key) for key in ('id','pid','is_visible','is_focused','monitor'))
                and geometry_after==geometry and crop_after==crop
                and all(monitor_after.get(key)==monitor.get(key) for key in ('name','x','y','width','height','scale','is_hdr')),
                'owned player identity/geometry/focus or monitor changed across capture')
        rgb=self.root/'visual-owned-window.rgb'
        self.cmd(common+['-i',str(image),'-frames:v','1','-vf',f'crop={w}:{h}:{x}:{y}',
                         '-pix_fmt','rgb24','-f','rawvideo',str(rgb)])
        info=dict(player=player,player_state=state,client_before=client,client_after=after,monitors=monitors,monitors_after=monitors_after,screenshot=screenshot,
                  fixture_sha256=digest(fixture),input_rgb_sha256=source_sha,expected_rgb_sha256=digest(expected),actual_rgb_sha256=digest(rgb),
                  expected_rgb_path=str(expected),actual_rgb_path=str(rgb),capture_pixels=size,
                  client_pixel_crop=dict(x=x,y=y,width=w,height=h),default_render_options=True,
                  command_options=['--no-existing-session','--new-window','--mpv-input-ipc-server=<owned socket>','--mpv-loop-file=inf'],
                  scope='separate static16-color FFV1 visual fixture; does not prove moving frames, audio or hardware')
        try:
            info['oracle']=evaluate_reference_rgb(rgb.read_bytes(),w,h,expected.read_bytes())
        except Exception as exc:
            info['oracle']=dict(status='failed',error=type(exc).__name__+': '+str(exc))
        (self.root/'visual-oracle.json').write_text(json.dumps(info,indent=2))
        self.trace('visual-oracle',proof=info)
        require(info['oracle']['status']=='matched','actual static visual fixture content unmatched; rendered-content gate remains open')
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


def run_checks(prefix, stage, *, disposable_guest=False):
    guest_guard(stage,disposable_guest)
    security=SecurityInterval()
    smoke=Smoke(prefix,stage)
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
    report=dict(schema=SCHEMA,stage=stage,status='failed' if any(g['status']=='failed' for g in smoke.gates)
                else 'limited-smoke-passed',release_acceptance=False,gates=smoke.gates,steps=smoke.steps,
                proven_new_processes=smoke.owned,diagnostic_trace=dict(path=str(smoke.root/'gui-trace.log'),
                    bytes=smoke.trace_bytes,omitted_records=smoke.trace_omitted,client_observations=smoke.client_observations),
                evidence_root=str(smoke.root),remaining=['GUI archive create/edit/encryption UX',
                'portal chooser actual returned-file roundtrip','screen reader and per-app accessible trees',
                'perceived video/audio and additional codecs','offline live/install/reboot phases',
                'browser sandbox existing independent gate','hardware/gaming and recovery boot/Secure Boot'])
    (smoke.root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print('ARCTIC-NATIVE-FUNCTIONAL '+json.dumps(report,ensure_ascii=False),flush=True)
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
