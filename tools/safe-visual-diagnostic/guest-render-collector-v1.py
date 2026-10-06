#!/usr/bin/env python3
"""Post-original-34 diagnostic only. Getter reads; one owned Foot and Grim.

No device writes, permission changes, renderer overrides or config mutations.
Importing this module performs no guest actions. Missing framebuffer evidence is
explicitly unavailable, never a substitute pixel image or a visual pass.
"""
import base64
import ctypes
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import stat
import struct
import subprocess
import sys
import tempfile
import time
import zlib

sys.dont_write_bytecode = True
MAX_RAW = 32 * 1024 * 1024
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
ORIGINAL_COLLECTOR_SHA = 'e1da6bb2f07cb7014486e0f59c36973600e5dcd9a8063c684f461e099d3fc5e9'
FBIOGET_VSCREENINFO = 0x4600
FBIOGET_FSCREENINFO = 0x4602


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def emit(name, value):
    print('ARCTIC-RENDER-' + name + ' ' + json.dumps(value, sort_keys=True), flush=True)


class Bitfield(ctypes.Structure):
    _fields_ = [('offset', ctypes.c_uint32), ('length', ctypes.c_uint32), ('msb_right', ctypes.c_uint32)]


class Variable(ctypes.Structure):
    _fields_ = [(k, ctypes.c_uint32) for k in ('xres', 'yres', 'xres_virtual', 'yres_virtual', 'xoffset', 'yoffset', 'bits_per_pixel', 'grayscale')]
    _fields_ += [(k, Bitfield) for k in ('red', 'green', 'blue', 'transp')]
    _fields_ += [(k, ctypes.c_uint32) for k in ('nonstd', 'activate', 'height', 'width', 'accel_flags', 'pixclock', 'left_margin', 'right_margin', 'upper_margin', 'lower_margin', 'hsync_len', 'vsync_len', 'sync', 'vmode', 'rotate', 'colorspace')]
    _fields_ += [('reserved', ctypes.c_uint32 * 4)]


class Fixed(ctypes.Structure):
    _fields_ = [('id', ctypes.c_char * 16), ('smem_start', ctypes.c_ulong), ('smem_len', ctypes.c_uint32), ('type', ctypes.c_uint32), ('type_aux', ctypes.c_uint32), ('visual', ctypes.c_uint32), ('xpanstep', ctypes.c_uint16), ('ypanstep', ctypes.c_uint16), ('ywrapstep', ctypes.c_uint16), ('line_length', ctypes.c_uint32), ('mmio_start', ctypes.c_ulong), ('mmio_len', ctypes.c_uint32), ('accel', ctypes.c_uint32), ('capabilities', ctypes.c_uint16), ('reserved', ctypes.c_uint16 * 2)]


def metadata(var, fix):
    require(sys.byteorder == 'little' and ctypes.sizeof(ctypes.c_ulong) == 8 and ctypes.sizeof(Variable) == 160 and ctypes.sizeof(Fixed) == 80, 'Unsupported framebuffer getter ABI')
    value = {k: int(getattr(var, k)) for k in ('xres', 'yres', 'xres_virtual', 'yres_virtual', 'xoffset', 'yoffset', 'bits_per_pixel', 'grayscale', 'nonstd', 'rotate')}
    value.update({k: int(getattr(fix, k)) for k in ('smem_len', 'type', 'visual', 'line_length')})
    value['id'] = bytes(fix.id).decode(errors='replace')
    value['channels'] = {k: {f: int(getattr(getattr(var, k), f)) for f in ('offset', 'length', 'msb_right')} for k in ('red', 'green', 'blue', 'transp')}
    require(value['bits_per_pixel'] == 32 and value['type'] == 0 and value['visual'] == 2
            and value['grayscale'] == value['nonstd'] == value['rotate'] == 0, 'Unsupported framebuffer pixel format')
    require(1 <= value['xres'] <= 4096 and 1 <= value['yres'] <= 2160
            and value['xres'] + value['xoffset'] <= value['xres_virtual']
            and value['yres'] + value['yoffset'] <= value['yres_virtual'], 'Invalid framebuffer dimensions/offsets')
    require(0 < value['line_length'] <= 65536 and value['line_length'] % 4 == 0
            and value['xres_virtual'] * 4 <= value['line_length'], 'Invalid framebuffer stride/alignment')
    bound = value['line_length'] * value['yres_virtual']
    require(0 < bound <= value['smem_len'] <= MAX_RAW, 'Framebuffer allocation exceeds bounds')
    rgb = [value['channels'][k] for k in ('red', 'green', 'blue')]
    require(all(c['length'] == 8 and c['msb_right'] == 0 for c in rgb)
            and {c['offset'] for c in rgb} in ({0, 8, 16}, {8, 16, 24}), 'Unsupported framebuffer RGB channel masks')
    return value


def png(raw, meta):
    width, height, stride = meta['xres'], meta['yres'], meta['line_length']
    require(len(raw) == stride * meta['yres_virtual'], 'Short framebuffer read')
    channels = [meta['channels'][k]['offset'] // 8 for k in ('red', 'green', 'blue')]
    rows = bytearray()
    for y in range(height):
        start = (y + meta['yoffset']) * stride + meta['xoffset'] * 4
        row = raw[start:start + width * 4]
        require(len(row) == width * 4, 'Short visible framebuffer row')
        rows.append(0)
        for x in range(width):
            rows.extend(row[x * 4 + c] for c in channels)
    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)
    value = b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    value += chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b'')
    require(len(value) <= MAX_FILE, 'Framebuffer PNG exceeds export bound')
    return value


def framebuffer(root, label):
    """Normal existing /dev/fb0 permissions; getters only, no guessed format."""
    result = dict(label=label, status='unavailable', active_scanout='unproven', device='/dev/fb0', guest_begin_ns=time.monotonic_ns())
    fd = None
    try:
        info = os.lstat('/dev/fb0')
        require(stat.S_ISCHR(info.st_mode) and os.major(info.st_rdev) == 29 and os.minor(info.st_rdev) == 0, 'Framebuffer device identity differs')
        sysdev = Path('/sys/class/graphics/fb0/dev').read_text().strip()
        require(sysdev == '29:0', 'Framebuffer sysfs device identity differs')
        fd = os.open('/dev/fb0', os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        current = os.fstat(fd)
        require(current.st_rdev == info.st_rdev and current.st_ino == info.st_ino and stat.S_ISCHR(current.st_mode), 'Framebuffer identity changed during open')
        var_buf, fix_buf = bytearray(ctypes.sizeof(Variable)), bytearray(ctypes.sizeof(Fixed))
        fcntl.ioctl(fd, FBIOGET_VSCREENINFO, var_buf, True)
        fcntl.ioctl(fd, FBIOGET_FSCREENINFO, fix_buf, True)
        meta = metadata(Variable.from_buffer_copy(var_buf), Fixed.from_buffer_copy(fix_buf))
        length = meta['line_length'] * meta['yres_virtual']
        raw = bytearray()
        while len(raw) < length:
            block = os.pread(fd, min(1024 * 1024, length - len(raw)), len(raw))
            require(block, 'Short framebuffer read')
            raw.extend(block)
        # Reread getter bytes to reject a changing geometry/pan, never issue PUT.
        after_var, after_fix = bytearray(len(var_buf)), bytearray(len(fix_buf))
        fcntl.ioctl(fd, FBIOGET_VSCREENINFO, after_var, True)
        fcntl.ioctl(fd, FBIOGET_FSCREENINFO, after_fix, True)
        require(after_var == var_buf and after_fix == fix_buf, 'Framebuffer mode changed during read')
        image = png(raw, meta)
        name = 'framebuffer-' + label + '.png'
        (root / name).write_bytes(image)
        result.update(status='read-only-snapshot', metadata=meta, raw_bytes=len(raw), raw_sha256=sha(raw), png=name, png_sha256=sha(image), png_bytes=len(image), sysfs_device=sysdev)
    except (OSError, RuntimeError, ValueError) as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    finally:
        if fd is not None:
            os.close(fd)
    result['guest_end_ns'] = time.monotonic_ns()
    return result


def load_original():
    path = Path(__file__).parent / 'guest-safe-collector-v1.py'
    require(not path.is_symlink() and sha(path.read_bytes()) == ORIGINAL_COLLECTOR_SHA, 'Original collector bytes differ')
    spec = importlib.util.spec_from_file_location('original_safe_guest', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def read_fd_records(C, proof):
    base = Path('/proc') / str(proof['pid'])
    result = []
    paths = sorted((base / 'fd').iterdir(), key=lambda p: int(p.name))
    require(len(paths) <= 256, 'Process descriptor count exceeds bound')
    for path in paths:
        try:
            target = os.readlink(path)
            if not re.fullmatch(r'/dev/(?:dri/(?:card|renderD)[0-9]+|fb[0-9]+)', target):
                continue
            data = (base / 'fdinfo' / path.name).read_bytes()
            require(len(data) <= 65536, 'DRM fdinfo exceeds bound')
            info = Path(target).stat()
            result.append(dict(fd=int(path.name), target=target, device_major=os.major(info.st_rdev), device_minor=os.minor(info.st_rdev), fdinfo=data.decode(errors='replace')))
        except FileNotFoundError:
            continue
    require(C.process(proof['pid']) == proof, 'Process identity changed during descriptor read')
    return result


def elf_build_id(path):
    """Read bounded ELF64 getter metadata without executing library/tool code."""
    with path.open('rb') as stream:
        size = os.fstat(stream.fileno()).st_size
        head = stream.read(64)
        require(head[:6] == b'\x7fELF\x02\x01' and len(head) == 64, 'Unsupported mapped-library ELF')
        phoff = struct.unpack_from('<Q', head, 32)[0]
        phsize, phnum = struct.unpack_from('<HH', head, 54)
        require(phsize == 56 and 0 < phnum <= 128 and phoff + phsize * phnum <= size, 'ELF program-header bounds differ')
        stream.seek(phoff); headers = stream.read(phsize * phnum)
        ids = []
        for n in range(phnum):
            kind, flags, offset, vaddr, paddr, length, memsz, align = struct.unpack_from('<IIQQQQQQ', headers, n * 56)
            if kind != 4:
                continue
            require(length <= 65536 and offset + length <= size, 'ELF note bounds differ')
            stream.seek(offset); notes = stream.read(length); i = 0
            while i + 12 <= len(notes):
                namesz, descsz, note_type = struct.unpack_from('<III', notes, i); i += 12
                name_end = i + namesz; desc_start = i + ((namesz + 3) & ~3); desc_end = desc_start + descsz
                require(name_end <= len(notes) and desc_end <= len(notes), 'ELF note record bounds differ')
                if notes[i:name_end] == b'GNU\0' and note_type == 3:
                    require(1 <= descsz <= 64, 'ELF build-id size differs')
                    ids.append(notes[desc_start:desc_end].hex())
                i = desc_start + ((descsz + 3) & ~3)
        require(ids and len(set(ids)) == 1, 'Missing/ambiguous ELF GNU build-id')
        return ids[0]


def libraries(proof):
    data = (Path('/proc') / str(proof['pid']) / 'maps').read_bytes()
    require(len(data) <= MAX_FILE, 'Process maps exceeds bound')
    paths = set()
    for line in data.decode().splitlines():
        values = line.split(None, 5)
        if len(values) == 6 and values[5].startswith('/usr/lib64/') and re.search(r'/(?:libwlroots|libscenefx|libEGL|libGLES|libGLdispatch|libgallium|libQt6Quick|libQt6Gui|libpixman)[^/]*\.so', values[5]):
            paths.add(values[5])
    require(len(paths) <= 32, 'Relevant mapped-library count exceeds bound')
    result = []
    for name in sorted(paths):
        record = dict(path=name, status='unavailable')
        try:
            path = Path(name).resolve(strict=True)
            require(path.is_file() and path.is_relative_to('/usr/lib64'), 'Mapped-library resolves outside allowed regular library root')
            record.update(status='read-build-id', resolved=str(path), gnu_build_id=elf_build_id(path))
        except (OSError, RuntimeError, ValueError) as exc:
            record['error'] = type(exc).__name__ + ': ' + str(exc)
        result.append(record)
    return result


def identities(C, user):
    result = []
    for folder in Path('/proc').glob('[0-9]*'):
        try:
            if folder.stat().st_uid == user.pw_uid and (folder / 'exe').resolve(strict=True).name in ('mango', 'quickshell', 'foot'):
                proof = C.process(int(folder.name))
                fds = read_fd_records(C, proof); libs = libraries(proof)
                require(C.process(proof['pid']) == proof, 'Process identity changed during library read')
                proof.update(display_fds=fds, mapped_library_build_ids=libs)
                result.append(proof)
                require(len(result) <= 32, 'Display process count exceeds bound')
        except (FileNotFoundError, ProcessLookupError):
            continue
    devices = []
    for base in (Path('/sys/class/drm'), Path('/sys/class/graphics')):
        if not base.exists():
            continue
        for path in sorted(base.iterdir()):
            if not re.fullmatch(r'(?:card[0-9]+|renderD[0-9]+|fb[0-9]+|card[0-9]+-[A-Za-z0-9-]+)', path.name):
                continue
            entry = dict(path=str(path), resolved=str(path.resolve()))
            for field in ('dev', 'name', 'modes', 'status', 'enabled', 'virtual_size', 'bits_per_pixel', 'stride', 'uevent'):
                p = path / field
                if p.exists():
                    data = p.read_bytes(); require(len(data) <= 65536, 'Display sysfs record exceeds bound')
                    entry[field] = data.decode(errors='replace')
            for field in ('device', 'device/driver', 'device/subsystem'):
                p = path / field
                if p.exists():
                    entry[field] = str(p.resolve())
            devices.append(entry); require(len(devices) <= 64, 'Display sysfs count exceeds bound')
    return dict(processes=result, devices=devices, active_scanout='unproven; no framebuffer/QMP root-cause attribution is authorized by collection alone')


def renderer_log_tail(C, proof, root):
    result = dict(pid=proof['pid'], status='unavailable', qualification='Actual fd2 target may be shared; raw log text alone does not identify each writer or compositor GL backend')
    target = os.readlink(Path('/proc') / str(proof['pid']) / 'fd/2'); result['fd2_target'] = target
    try:
        path = Path(target); info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_uid == proof['uid'], 'Renderer stderr is not an existing owned regular file')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, 'rb') as stream:
            opened = os.fstat(stream.fileno())
            require(opened.st_ino == info.st_ino and opened.st_uid == proof['uid'] and stat.S_ISREG(opened.st_mode), 'Renderer stderr identity changed')
            stream.seek(max(0, opened.st_size - 65536)); data = stream.read(65536)
        (root / 'mango-render-stderr-tail.log').write_bytes(data)
        result.update(status='bounded-tail-read', original_bytes=opened.st_size, retained_bytes=len(data), sha256=sha(data), path='mango-render-stderr-tail.log')
    except (OSError, RuntimeError) as exc:
        result['error'] = type(exc).__name__ + ': ' + str(exc)
    require(C.process(proof['pid']) == proof, 'Mango identity changed during stderr read')
    return result


def signal_owned(C, proof):
    """Pin the signal target before the final identity check; never PID fallback."""
    require(hasattr(os, 'pidfd_open') and hasattr(signal, 'pidfd_send_signal'), 'Owned cleanup requires Linux pidfd support')
    fd = os.pidfd_open(proof['pid'], 0)
    try:
        require(C.process(proof['pid']) == proof, 'Signal target was reused/changed after pidfd open')
        signal.pidfd_send_signal(fd, signal.SIGTERM, None, 0)
    finally:
        os.close(fd)


class OwnedFoot:
    def __init__(self, C, user, env, token):
        self.C, self.user, self.env, self.token = C, user, env, token
        self.child = None; self.wrapper = None; self.foot = None; self.rows = None; self.foot_group = None
        self.stderr = bytearray()

    def drain_stderr(self):
        if self.child is None or self.child.stderr is None or self.child.stderr.closed:
            return
        while True:
            try:
                data = os.read(self.child.stderr.fileno(), 65536)
            except BlockingIOError:
                return
            if not data:
                return
            self.stderr.extend(data)
            require(len(self.stderr) <= 65536, 'Owned Foot stderr exceeds bound')

    def launch(self):
        script = Path(__file__).parent / 'fixed-rows-v1.py'
        require(script.is_file() and not script.is_symlink(), 'Owned fixed rows script missing')
        require(self.child is None, 'Only one owned diagnostic Foot allowed')
        # This is a distinct client, without --server, settings or renderer flags.
        argv = self.C.session_prefix(self.user, self.env) + ['/usr/bin/foot', '--app-id=' + self.token, '/usr/bin/python3', str(script), self.token]
        self.child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, start_new_session=True)
        self.wrapper = self.C.process(self.child.pid)
        os.set_blocking(self.child.stderr.fileno(), False)
        require(self.wrapper['uid'] == 0 and self.wrapper['executable'] == str(Path('/usr/sbin/runuser').resolve(strict=True)), 'Owned launch wrapper identity differs')
        end = time.monotonic() + 5
        while time.monotonic() < end:
            self.drain_stderr()
            require(self.child.poll() is None, 'Owned Foot launch exited before identification: ' + self.stderr.decode(errors='replace'))
            matches = []; rows = []
            for folder in Path('/proc').glob('[0-9]*'):
                try:
                    if folder.stat().st_uid != self.user.pw_uid:
                        continue
                    p = self.C.process(int(folder.name))
                    if p['executable'] == '/usr/bin/foot' and '--app-id=' + self.token in p['cmdline']:
                        matches.append(p)
                    if p['executable'] == str(Path('/usr/bin/python3').resolve(strict=True)) and p['cmdline'] == ['/usr/bin/python3', str(script), self.token]:
                        rows.append(p)
                except (FileNotFoundError, ProcessLookupError):
                    continue
            require(len(matches) <= 1 and len(rows) <= 1, 'Duplicate owned diagnostic Foot/rows process')
            if matches and rows:
                self.foot = matches[0]
                self.rows = rows[0]
                self.foot_group = os.getpgid(self.foot['pid'])
                foot_parent = (Path('/proc') / str(self.foot['pid']) / 'stat').read_text().rsplit(')', 1)[1].split()[1]
                require(int(foot_parent) == self.child.pid, 'Identified Foot is not owned by the launch wrapper')
                parent = (Path('/proc') / str(self.rows['pid']) / 'stat').read_text().rsplit(')', 1)[1].split()[1]
                require(int(parent) == self.foot['pid'], 'Fixed-row child is not owned by the identified Foot')
                require(self.C.process(self.foot['pid']) == self.foot, 'Owned Foot identity changed')
                require(self.C.process(self.rows['pid']) == self.rows, 'Fixed-row child identity changed')
                return dict(wrapper=self.wrapper, foot=self.foot, rows=self.rows, foot_process_group=self.foot_group, argv=argv, guest_monotonic_ns=time.monotonic_ns(), fixed_rows_sha256=sha(script.read_bytes()))
            time.sleep(.05)
        raise RuntimeError('Owned Foot identity timeout')

    def cleanup(self):
        try:
            return self._cleanup()
        finally:
            primary_error = sys.exc_info()[0] is not None
            if self.child is not None and self.child.stderr is not None:
                try:
                    self.child.stderr.close()
                except BaseException:
                    if not primary_error:
                        raise

    def _cleanup(self):
        if self.child is None:
            return dict(status='not-launched')
        if self.child.poll() is not None:
            self.drain_stderr()
            return dict(status='already-exited', returncode=self.child.returncode, stderr=self.stderr.decode(errors='replace'))
        # Never signal by name, PGID or stale PID. Every target has an owned proof.
        require(self.C.process(self.child.pid) == self.wrapper, 'Owned launch wrapper reused/changed; refuse cleanup')
        if self.foot is not None:
            require(self.C.process(self.foot['pid']) == self.foot and self.foot['uid'] == self.user.pw_uid
                    and os.getpgid(self.foot['pid']) == self.foot_group, 'Owned Foot reused/changed; refuse cleanup')
            signal_owned(self.C, self.foot)
            if self.rows is not None:
                try:
                    current = self.C.process(self.rows['pid'])
                except (FileNotFoundError, ProcessLookupError):
                    current = None
                if current is not None:
                    require(current == self.rows and current['uid'] == self.user.pw_uid, 'Fixed-row child reused/changed; refuse cleanup')
                    signal_owned(self.C, self.rows)
        else:
            # A failed pre-identification launch may only signal its own wrapper.
            signal_owned(self.C, self.wrapper)
        try:
            self.child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            raise RuntimeError('Owned Foot cleanup did not finish; VM harness retains failure')
        for folder in Path('/proc').glob('[0-9]*'):
            try:
                require(os.getpgid(int(folder.name)) != self.child.pid, 'Owned launch group still has a process; cleanup incomplete')
            except ProcessLookupError:
                continue
        if self.rows is not None:
            try:
                current = self.C.process(self.rows['pid'])
            except (FileNotFoundError, ProcessLookupError):
                current = None
            require(current is None, 'Owned fixed-row child still exists after cleanup')
        self.drain_stderr()
        return dict(status='owned-launch-exited', returncode=self.child.returncode, stderr=self.stderr.decode(errors='replace'))


def export(root):
    files, payloads, total = [], [], 0
    for path in sorted(root.iterdir()):
        require(path.is_file() and not path.is_symlink() and path.name != 'serial-report.json', 'Unexpected render evidence type/name')
        data = path.read_bytes(); total += len(data)
        require(len(data) <= MAX_FILE and total <= MAX_TOTAL and len(files) < 128, 'Render evidence exceeds transport bounds')
        packed = zlib.compress(data); pieces = [packed[n:n + 24000] for n in range(0, len(packed), 24000)]
        files.append(dict(path=path.name, bytes=len(data), sha256=sha(data), compressed_bytes=len(packed), chunks=len(pieces)))
        payloads.append((path.name, pieces))
    emit('MANIFEST', dict(schema='arctic-render-files-v1', encoding='zlib+base64', files=files, bytes=total))
    for name, pieces in payloads:
        for index, data in enumerate(pieces):
            emit('CHUNK', dict(path=name, index=index, data=base64.b64encode(data).decode()))


def main():
    report = dict(schema='arctic-render-telemetry-v1', status='failed', release_acceptance=False, safe_visual_gate='open', collector_sha256=sha(Path(__file__).read_bytes()), effective_render_loop='unobserved', compositor_gl_renderer='unobserved')
    root = None; owned = None; error = None; C = None
    emit('BEGIN', dict(collector_sha256=report['collector_sha256'], release_acceptance=False))
    try:
        require(os.geteuid() == 0 and Path(__file__).resolve() == Path('/run/arctic-safe/guest-render-collector-v1.py'), 'Requires exact root read-only test-CD path')
        C = load_original()
        require(C.execute(['systemd-detect-virt']).decode().strip() in ('qemu', 'kvm'), 'Requires disposable QEMU/KVM')
        cmdline = Path('/proc/cmdline').read_text().split()
        require('rd.live.image' in cmdline and 'nomodeset' in cmdline, 'Requires actual Safe live mode')
        require(C.execute(['getenforce']).decode().strip() == 'Enforcing', 'Requires Enforcing before any diagnostic write')
        require('ro' in C.execute(['findmnt', '-n', '-o', 'OPTIONS', '/run/arctic-safe']).decode().strip().split(','), 'Test-CD is not read-only')
        user, proofs, env = C.desktop()
        root = Path(tempfile.mkdtemp(prefix='arctic-render-evidence-'))
        report.update(boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), cmdline=' '.join(cmdline), desktop_uid=user.pw_uid, processes=proofs, identities_before=identities(C, user))
        config = Path(env.get('XDG_CONFIG_HOME', user.pw_dir + '/.config'))
        configs = [C.read_config(config / p) for p in ('mango/config.conf', 'mango/settings.conf', 'mango/user.conf', 'arctic/motion.conf', 'arctic/settings.json', 'foot/foot.ini', 'arctic/current/foot/colors.ini')]
        configs.append(C.read_config(Path('/etc/xdg/foot/foot.ini')))
        sources = C.mango_sources(config / 'mango/config.conf', user.pw_dir)
        report['security_before'] = C.security(root, 'render-before')
        require(not report['security_before']['avc_records'], 'Existing trusted AVC requires review')
        emit('FB-READY', dict(wait_seconds=10, guest_monotonic_ns=time.monotonic_ns()))
        time.sleep(10)
        report['framebuffers'] = [framebuffer(root, 'baseline')]
        emit('FB-DONE', report['framebuffers'][-1])
        time.sleep(5)  # Host QMP post-bracket precedes the new client.
        require(C.execute(['/usr/bin/rpm', '-V', '--noscripts', 'foot']) == b'', 'Candidate Foot RPM verification failed')
        owned = OwnedFoot(C, user, env, 'arctic-safe-render-' + root.name)
        report['owned_launch'] = owned.launch(); launch_origin = time.monotonic()
        emit('FOOT-START', report['owned_launch'])
        for seconds in (1, 5, 60):
            time.sleep(max(0, launch_origin + seconds - time.monotonic()))
            owned.drain_stderr()
            require(owned.child.poll() is None and C.process(owned.foot['pid']) == owned.foot, 'Owned Foot exited/changed during observation')
            value = framebuffer(root, 'foot-%02ds' % seconds)
            value['seconds_after_owned_launch'] = time.monotonic() - launch_origin
            report['framebuffers'].append(value); emit('FOOT-FB', value)
        report['security_before_grim'] = C.security(root, 'render-before-grim')
        require(not report['security_before_grim']['avc_records'], 'New trusted AVC before crossover')
        emit('GRIM-READY', dict(wait_seconds=10, guest_monotonic_ns=time.monotonic_ns()))
        time.sleep(10); emit('GRIM-BEGIN', dict(guest_monotonic_ns=time.monotonic_ns()))
        image = C.execute(C.session_prefix(user, env) + ['/usr/bin/grim', '-'], timeout=15)
        require(image.startswith(b'\x89PNG\r\n\x1a\n'), 'Grim did not return PNG')
        (root / 'render-grim.png').write_bytes(image)
        report['grim'] = dict(bytes=len(image), sha256=sha(image), guest_monotonic_ns=time.monotonic_ns())
        report['framebuffers'].append(framebuffer(root, 'after-grim')); emit('GRIM-DONE', report['grim'])
        time.sleep(5)  # Keep owned Foot alive for the paired host QMP capture.
        report['cleanup'] = owned.cleanup(); owned = None
        require(report['cleanup']['status'] == 'owned-launch-exited', 'Owned Foot cleanup did not finish normally')
        report['security_after'] = C.security(root, 'render-after')
        require(not report['security_after']['avc_records'], 'New trusted AVC after diagnostic arm')
        require(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == report['boot_id'], 'Guest boot identity changed')
        require(all(C.process(p['pid']) == p for p in proofs.values()), 'Original desktop process changed')
        require([C.read_config(Path(v['path'])) for v in configs] == configs and C.mango_sources(config / 'mango/config.conf', user.pw_dir) == sources, 'Observed configuration/include graph changed')
        report.update(identities_after=identities(C, user), configs=configs, declared_sources=sources, status='diagnostic-collected-inconclusive', renderer_log=renderer_log_tail(C, proofs['mango'], root))
        report['unavailable'] = [v['label'] for v in report['framebuffers'] if v['status'] != 'read-only-snapshot']
    except BaseException as exc:
        error = type(exc).__name__ + ': ' + str(exc); report['status'] = 'failed'; report['error'] = error
    finally:
        if owned is not None:
            try:
                report['cleanup'] = owned.cleanup()
            except BaseException as exc:
                report['cleanup_error'] = type(exc).__name__ + ': ' + str(exc)
                error = error or report['cleanup_error']; report['status'] = 'failed'
        if error and root is not None and C is not None:
            try:
                report['security_on_failure'] = C.security(root, 'render-failure')
            except BaseException as exc:
                report['security_on_failure_error'] = type(exc).__name__ + ': ' + str(exc)
    if root:
        (root / 'report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    emit('REPORT', report)
    try:
        if root:
            export(root)
        else:
            emit('MANIFEST', dict(schema='arctic-render-files-v1', encoding='zlib+base64', files=[], bytes=0))
    except BaseException as exc:
        error = error or type(exc).__name__ + ': ' + str(exc)
    emit('END', dict(status='failed' if error else 'collected-inconclusive', error=error, release_acceptance=False))
    return 1 if error else 0


if __name__ == '__main__':
    sys.exit(main())
