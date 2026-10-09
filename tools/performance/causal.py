"""Read-only causal mapping bounds, only in the disposable measurement guest.

The wlroots handle return precedes Mango's managed client-list insertion. Its
kernel timestamp is a LOWER bound, never an exact mapping or frame timestamp.
No compositor code, configuration, scheduling or SELinux setting is changed.
"""
import hashlib
import os
from pathlib import Path
import re
import select
import signal
import struct
import subprocess
import threading
import time
import uuid

SYMBOL = 'wlr_ext_foreign_toplevel_handle_v1_create'
IDENTIFIER_OFFSET = 56  # x86_64 wlroots 0.20 public header, three pointers + two wl_lists
HEADER_SHA256 = '9253b1ac1b68011cb304c0c9b84a6678779acc820994131a31f170d26945d0f3'
SOURCE_SHA256 = '5580d4b6c803fb3548bbe104f5b0bdbfd5a17b42dd173358aa526ca0e958a088'
METHOD = 'wlroots-0.20-return-before-mango-list-insertion-v1'
MAX_EVENTS = 8192


def elf_symbol_offset(path, name=SYMBOL):
    """Locate the exported function's file offset; refuse other ELF ABIs."""
    raw = path.read_bytes()
    if len(raw) > 64 * 1024 * 1024 or raw[:6] != b'\x7fELF\x02\x01':
        raise RuntimeError('Causal probe requires bounded little-endian ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    if header[2] != 62 or header[9] != 56 or header[11] != 64:
        raise RuntimeError('Causal probe requires the audited x86_64 ELF layout')
    segments = [struct.unpack_from('<IIQQQQQQ', raw, header[5] + n * 56)
                for n in range(header[10])]
    sections = [struct.unpack_from('<IIQQQQIIQQ', raw, header[6] + n * 64)
                for n in range(header[12])]
    values = []
    for section in sections:
        if section[1] != 11:  # SHT_DYNSYM; never guess from a stripped symbol table
            continue
        if (section[9] != 24 or section[5] % 24 or section[6] >= len(sections)
                or section[4] > len(raw) or section[5] > len(raw) - section[4]):
            raise RuntimeError('Malformed dynamic symbol table')
        strings = sections[section[6]]
        if strings[4] > len(raw) or strings[5] > len(raw) - strings[4]:
            raise RuntimeError('Malformed dynamic symbol string table')
        table = raw[strings[4]:strings[4] + strings[5]]
        for offset in range(section[4], section[4] + section[5], 24):
            string, info, _, index, address, _ = struct.unpack_from('<IBBHQQ', raw, offset)
            end = table.find(b'\0', string)
            if end < 0:
                raise RuntimeError('Malformed dynamic symbol name')
            if table[string:end] == name.encode() and index and info & 15 == 2:
                values.append(address)
    if len(values) != 1:
        raise RuntimeError('Expected one exported causal function')
    loads = [segment for segment in segments if segment[0] == 1 and segment[1] & 1
             and segment[3] <= values[0] < segment[3] + segment[5]]
    if len(loads) != 1:
        raise RuntimeError('Causal function is not in one executable file mapping')
    return values[0] - loads[0][3] + loads[0][2]


def trace_receipt(line, pid):
    match = re.search(r'-(\d+)\s+\[\d+\].*?\s(\d+)\.(\d{1,9}):\s+map_create:\s+(?:\([^\n]*\)\s+)?foreign_id="([0-9a-f]{32})"\s*$', line)
    if not match or int(match[1]) != pid:
        raise RuntimeError('Unexpected or unbound causal kernel event')
    digits = match[3]
    resolution = 10 ** (9 - len(digits))
    timestamp = int(match[2]) * 1_000_000_000 + int(digits.ljust(9, '0'))
    # tracefs may print fewer than nine digits. Floor the printed timestamp to
    # preserve a conservative lower endpoint instead of claiming lost digits.
    return dict(foreign_toplevel_id=match[4], lower_monotonic_ns=timestamp,
                timestamp_resolution_ns=resolution, kernel_pid=pid)


def loss_counts(root):
    result = {}
    for path in sorted((root / 'per_cpu').glob('cpu*/stats')):
        counts = {}
        for line in path.read_text().splitlines():
            if ':' in line:
                name, value = line.split(':', 1)
                if name.strip() in ('overrun', 'commit overrun', 'dropped events'):
                    counts[name.strip()] = int(value.strip())
        if set(counts) != {'overrun', 'commit overrun', 'dropped events'} or any(counts.values()):
            raise RuntimeError('Causal kernel event loss or incomplete loss accounting')
        result[path.parent.name] = counts
    if not result:
        raise RuntimeError('Missing causal per-CPU loss accounting')
    return result


class LowerBoundProbe:
    def __init__(self, prefix):
        self.prefix = prefix
        self.root = None
        self.instance = None
        self.group = 'arctic_map_' + uuid.uuid4().hex
        self.events = {}
        self.condition = threading.Condition()
        self.stopped = threading.Event()
        self.error = None
        self.thread = None
        self.fd = None
        self.proof = None

    def __enter__(self):
        try:
            if os.geteuid() != 0 or Path(__file__).parent != Path('/run/t'):
                raise RuntimeError('Causal instrumentation requires the disposable root collector')
            if subprocess.check_output(['systemd-detect-virt', '--vm'], text=True).strip() not in ('qemu', 'kvm'):
                raise RuntimeError('Causal instrumentation requires a disposable QEMU guest')
            if subprocess.check_output(['getenforce'], text=True).strip() != 'Enforcing':
                raise RuntimeError('Causal instrumentation requires SELinux enforcing')
            if self.prefix[:2] != ['runuser', '-u']:
                raise RuntimeError('Causal instrumentation requires the actual desktop user')
            self.old_sigterm = signal.getsignal(signal.SIGTERM)
            def interrupted(signum, frame):
                raise InterruptedError('Owned causal instrumentation interrupted')
            signal.signal(signal.SIGTERM, interrupted)
            import pwd
            uid = pwd.getpwnam(self.prefix[2]).pw_uid
            candidates = []
            for proc in Path('/proc').glob('[0-9]*'):
                try:
                    if proc.stat().st_uid == uid and (proc / 'comm').read_text().strip() == 'mango':
                        candidates.append(proc)
                except OSError:
                    continue
            if len(candidates) != 1:
                raise RuntimeError('Expected one desktop-owned production Mango')
            proc = candidates[0]
            self.pid = int(proc.name)
            libraries = {line.split()[-1] for line in (proc / 'maps').read_text().splitlines()
                         if re.search(r'/libwlroots-0\.20\.so(?:\.[0-9]+)*$', line)}
            if len(libraries) != 1:
                raise RuntimeError('Expected the audited production wlroots 0.20 library')
            library = Path(libraries.pop())
            if not library.is_file() or library.is_symlink() or not re.fullmatch(r'/usr/lib64/libwlroots-0\.20\.so(?:\.[0-9]+)*', str(library)):
                raise RuntimeError('Unexpected production wlroots library path')
            owner = subprocess.check_output(['rpm', '-qf', str(library)], text=True).strip()
            if not re.fullmatch(r'wlroots(?:0\.20)?-0\.20\.2-[A-Za-z0-9._+]+\.x86_64', owner):
                raise RuntimeError('Unexpected wlroots package identity')
            verified = subprocess.run(['rpm', '-Vf', str(library)], text=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if verified.returncode or verified.stdout or verified.stderr:
                raise RuntimeError('Production wlroots package verification failed')
            offset = elf_symbol_offset(library)
            executable = (proc / 'exe').resolve(strict=True)
            mango_owner = subprocess.check_output(['rpm', '-qf', str(executable)], text=True).strip()
            if executable != Path('/usr/bin/mango') or not re.fullmatch(r'mangowm-0\.17\.3-[A-Za-z0-9._+]+\.x86_64', mango_owner):
                raise RuntimeError('Causal ordering requires the audited production Mango 0.17.3')
            mango_verified = subprocess.run(['rpm', '-Vf', str(executable)], text=True,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if mango_verified.returncode or mango_verified.stdout or mango_verified.stderr:
                raise RuntimeError('Production Mango package verification failed')
            self.proof = dict(method=METHOD, clock='mono', kernel_pid=self.pid,
                desktop_uid=uid, mango_start_ticks=int((proc / 'stat').read_text().rsplit(')', 1)[1].split()[19]),
                mango_sha256=hashlib.sha256(executable.read_bytes()).hexdigest(), mango_rpm=mango_owner,
                library_path=str(library), library_rpm=owner,
                library_sha256=hashlib.sha256(library.read_bytes()).hexdigest(),
                exported_symbol=SYMBOL, exported_file_offset=offset,
                identifier_offset=IDENTIFIER_OFFSET, audited_header_sha256=HEADER_SHA256,
                audited_source_sha256=SOURCE_SHA256)
            self.root = Path('/sys/kernel/tracing')
            if not (self.root / 'uprobe_events').is_file():
                # Mount only at the guest's standard tracefs mount point, and
                # undo only this mount on exit. No host/device passthrough exists.
                subprocess.run(['mount', '-t', 'tracefs', 'tracefs', str(self.root)], check=True, timeout=15)
                self.mounted = True
            self.instance = self.root / 'instances' / self.group
            self.instance.mkdir()
            (self.instance / 'tracing_on').write_text('0')
            (self.instance / 'trace_clock').write_text('mono')
            if '[mono]' not in (self.instance / 'trace_clock').read_text():
                raise RuntimeError('Causal trace clock is not monotonic')
            (self.instance / 'buffer_size_kb').write_text('128')
            (self.instance / 'options/overwrite').write_text('0')
            (self.instance / 'options/context-info').write_text('1')
            if (self.instance / 'options/record-tgid').exists():
                (self.instance / 'options/record-tgid').write_text('0')
            if (self.instance / 'options/nsecs').exists():
                (self.instance / 'options/nsecs').write_text('1')
            command = (f'r:{self.group}/map_create {library}:0x{offset:x} '
                       f'foreign_id=+0(+{IDENTIFIER_OFFSET}($retval)):string\n')
            with (self.root / 'uprobe_events').open('a') as output:
                output.write(command)
            self.registered = True
            event = self.instance / 'events' / self.group / 'map_create'
            (event / 'filter').write_text('common_pid == ' + str(self.pid))
            (event / 'enable').write_text('1')
            self.fd = os.open(self.instance / 'trace_pipe', os.O_RDONLY | os.O_NONBLOCK)
            self.thread = threading.Thread(target=self._read, daemon=True)
            self.thread.start()
            (self.instance / 'tracing_on').write_text('1')
            loss_counts(self.instance)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _read(self):
        pending = b''
        try:
            while not self.stopped.is_set():
                if not select.select([self.fd], [], [], .05)[0]:
                    continue
                try:
                    pending += os.read(self.fd, 65536)
                except BlockingIOError:
                    continue
                if len(pending) > 128 * 1024:
                    raise RuntimeError('Unbounded causal kernel line')
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    if not line or line.startswith(b'#'):
                        continue
                    event = trace_receipt(line.decode('ascii'), self.pid)
                    key = event['foreign_toplevel_id']
                    with self.condition:
                        if key in self.events or len(self.events) >= MAX_EVENTS:
                            raise RuntimeError('Duplicate or unbounded causal kernel events')
                        self.events[key] = event
                        self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.error = str(error)
                self.condition.notify_all()

    def bound(self, windows, started_ns, upper_ns, timeout=2):
        identities = [window.get('foreign_toplevel_id') for window in windows]
        if not identities or len(set(identities)) != len(identities) or any(not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key) for key in identities):
            raise RuntimeError('Mapped IPC clients lack unique causal identities')
        deadline = time.monotonic() + timeout
        with self.condition:
            while not all(key in self.events for key in identities):
                if self.error:
                    raise RuntimeError(self.error)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Matched causal kernel receipt is missing; no weaker fallback')
                self.condition.wait(remaining)
            if self.error:
                raise RuntimeError(self.error)
            events = [dict(self.events[key]) for key in identities]
        if any(not started_ns <= event['lower_monotonic_ns'] <= upper_ns for event in events):
            raise RuntimeError('Causal event is outside the current launch clock interval')
        lower = min(event['lower_monotonic_ns'] for event in events)
        return lower, dict(self.proof, matched_events=events,
            loss_counts=loss_counts(self.instance), status='bound-before-mapping')

    def __exit__(self, *unused):
        errors = []
        def cleanup(action):
            try:
                action()
            except BaseException as error:
                errors.append(str(error))
        self.stopped.set()
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                errors.append('Owned causal reader did not stop')
        if self.error:
            errors.append(self.error)
        if self.fd is not None:
            cleanup(lambda: os.close(self.fd))
            self.fd = None
        if self.instance and self.instance.exists():
            cleanup(lambda: (self.instance / 'tracing_on').write_text('0'))
            cleanup(lambda: loss_counts(self.instance))
            event = self.instance / 'events' / self.group / 'map_create' / 'enable'
            if event.exists():
                cleanup(lambda: event.write_text('0'))
            cleanup(self.instance.rmdir)
        if getattr(self, 'registered', False):
            def unregister():
                with (self.root / 'uprobe_events').open('a') as output:
                    output.write('-:' + self.group + '/map_create\n')
            cleanup(unregister)
            self.registered = False
        if getattr(self, 'mounted', False):
            cleanup(lambda: subprocess.run(['umount', str(self.root)], check=True, timeout=15))
            self.mounted = False
        if hasattr(self, 'old_sigterm'):
            cleanup(lambda: signal.signal(signal.SIGTERM, self.old_sigterm))
            del self.old_sigterm
        if errors:
            raise RuntimeError('Owned causal instrumentation cleanup failed: ' + '; '.join(errors))
