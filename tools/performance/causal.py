"""Read-only causal mapping bounds, only in the disposable measurement guest.

The wlroots handle return precedes Mango's managed client-list insertion.
An audited Mango instruction after that insertion supplies a native upper
bound. Both use the kernel raw clock; neither is a frame timestamp.
No compositor code, configuration, scheduling or SELinux setting is changed.
"""
import hashlib
from contextlib import contextmanager
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
METHOD = 'wlroots-0.20-and-mango-managed-list-original-appid-native-bracket-raw-v4'
MAX_EVENTS = 8192
APPID_OFFSET = 48
HANDLE_DATA_OFFSET = 80
MANGO_SOURCE_SHA256 = '586627878578a2545655d4accb790a73112be7eaf6b1dab9d162b4195d962eef'
MANGO_HEADER_SHA256 = '0c76fd2a2f677170ad9ef27df9296444bfdf1c69cb40a05dadadd51e050d3428'
ORIGINAL_APPID_AUDIT_SHA256 = '3c6e8e8582215a02b16ebc24e85c8ca807df70dd6bc1c33f57684f656fc9b692'
# Exact audited machine code, including every managed-list insertion branch.
# Each admitted whole executable is independently audited. Changed build IDs,
# machine code or ABI require a new explicit profile, with no guessed fallback.
MAPPING_PROFILES = (
    dict(executable_sha256='1c66767fc0d814e9002306c983524b476edc671de544f3b2a6f755ea7a52dcb1',
         function_file_offset=0x430d0, function_size=4109,
         function_sha256='d48615861b8819d95e30fbbf74db46e24f8e3d738e20824e0e598578972004a2',
         instruction_file_offset=0x435ef, client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='2f1107221157f47418cfda87dd091a3bb81ecd97dc2945184d0c42de7bbd254b',
         native_audit_sha256='c263158a0e29ee302bed2f09a24c43e9017ce7d87ceb53d22b86398b39dcd2aa',
         function_file_offset=0x43110, function_size=4109,
         function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
         instruction_file_offset=0x4362f, client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35',
         native_audit_sha256='c263158a0e29ee302bed2f09a24c43e9017ce7d87ceb53d22b86398b39dcd2aa',
         function_file_offset=0x430d0, function_size=4109,
         function_sha256='11a56d467fe7e444f46fa6da1f91a88ecf1a26bc3c54e4965727438e078a47dd',
         instruction_file_offset=0x435ef, client_ext_offset=1584,
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
)


def mapping_profile(path):
    raw = path.read_bytes()
    if len(raw) > 64*1024*1024 or raw[:6] != b'\x7fELF\x02\x01':
        raise RuntimeError('Native upper probe requires bounded ELF64')
    header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
    if header[2] != 62 or header[9] != 56:
        raise RuntimeError('Native upper probe requires the audited x86_64 ELF ABI')
    segments = [struct.unpack_from('<IIQQQQQQ', raw, header[5]+n*56)
                for n in range(header[10])]
    executable_sha256 = hashlib.sha256(raw).hexdigest()
    matched = []
    for profile in MAPPING_PROFILES:
        start, size = profile['function_file_offset'], profile['function_size']
        if (executable_sha256 != profile['executable_sha256'] or start+size > len(raw)
                or hashlib.sha256(raw[start:start+size]).hexdigest() != profile['function_sha256']):
            continue
        getter_start, getter_size = profile['ipc_function_file_offset'], profile['ipc_function_size']
        if (getter_start+getter_size > len(raw) or hashlib.sha256(
                raw[getter_start:getter_start+getter_size]).hexdigest() != profile['ipc_function_sha256']):
            raise RuntimeError('Audited original app-ID getter bytes differ')
        loads = [segment for segment in segments if segment[0] == 1 and segment[1] & 1
                 and segment[2] <= start and start+size <= segment[2]+segment[5]]
        if len(loads) != 1:
            raise RuntimeError('Audited mapping function is not in one executable ELF load')
        getter_loads = [segment for segment in segments if segment[0] == 1 and segment[1] & 1
            and segment[2] <= getter_start and getter_start+getter_size <= segment[2]+segment[5]]
        if len(getter_loads) != 1:
            raise RuntimeError('Audited original app-ID getter is not in one executable ELF load')
        matched.append(dict(profile))
    if len(matched) != 1:
        raise RuntimeError('Unknown or ambiguous Mango mapping machine code; reaudit required')
    return matched[0]


def instruction_mapping(path, maps, offset):
    matches = []
    for line in maps.splitlines():
        fields = line.split(None, 5)
        if len(fields) != 6 or fields[5] != str(path) or 'x' not in fields[1]:
            continue
        start, end = (int(value, 16) for value in fields[0].split('-'))
        file_offset = int(fields[2], 16)
        if file_offset <= offset < file_offset+end-start:
            matches.append(dict(start=start, end=end, file_offset=file_offset,
                                instruction_address=start+offset-file_offset))
    if len(matches) != 1:
        raise RuntimeError('Native upper instruction lacks one actual executable process mapping')
    return matches[0]


def upper_probe_commands(group, executable, profile):
    """Capture the exact getter branch; the other Client kind is not recorded."""
    common = (f'foreign_id=+0(+{IDENTIFIER_OFFSET}(+{profile["client_ext_offset"]}(%bx))):string '
        f'app_id=+0(+{APPID_OFFSET}(+{profile["client_ext_offset"]}(%bx))):string '
        f'client=%bx:x64 handle=+{profile["client_ext_offset"]}(%bx):x64 '
        f'owner=+{HANDLE_DATA_OFFSET}(+{profile["client_ext_offset"]}(%bx)):x64')
    surface = f'+{profile["client_surface_offset"]}(%bx)'
    chains = dict(map_listed_xdg=f'+0(+{profile["xdg_appid_offset"]}(+{profile["xdg_toplevel_offset"]}({surface})))',
                  map_listed_x11=f'+0(+{profile["xwayland_class_offset"]}({surface}))')
    return {name: f'p:{group}/{name} {executable}:0x{profile["instruction_file_offset"]:x} '
            + f'client_type=+{profile["client_type_offset"]}(%bx):u32 '
            + 'original_app_id=' + chain + ':string ' + common + '\n' for name, chain in chains.items()}


def original_appid_matches(event, window, pattern):
    # An intermediate pointer-dereference fault can leave the original data_loc
    # pointing at the following foreign identifier. No admitted role may alias it.
    if any(re.fullmatch('[0-9a-f]{32}', appid) for appid in pattern):
        return False
    if (type(event.get('client_type')) is not int or event['client_type'] not in (0, 2)
            or event.get('event') != ('map_listed_xdg' if event['client_type'] == 0 else 'map_listed_x11')):
        return False
    values = (event.get('original_app_id'), event.get('app_id'), window.get('appid'))
    return (all(isinstance(value, str) and re.fullmatch('[A-Za-z0-9._-]{1,128}', value) for value in values)
        and values[0] == values[1] == values[2] and values[0].lower() in pattern)



@contextmanager
def deferred_termination():
    """Deliver cancellation only after ownership handoff or complete unwind."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


def write_uprobe_command(root, command):
    """Issue one bounded command without seeking or clearing global events."""
    if not isinstance(command, str) or not command.endswith('\n') or '\n' in command[:-1]:
        raise RuntimeError('Expected exactly one causal tracefs command')
    data = command.encode('ascii')
    if not 1 < len(data) <= 4096:
        raise RuntimeError('Causal tracefs command exceeds the bounded write')
    # Python append mode seeks to SEEK_END, which Linux seq_lseek rejects.
    # Truncation instead deletes every registered uprobe, including unrelated
    # events. The tracefs command interface needs neither operation.
    with deferred_termination():
        fd = os.open(root / 'uprobe_events', os.O_WRONLY | os.O_CLOEXEC)
        try:
            if os.write(fd, data) != len(data):
                raise RuntimeError('Incomplete causal tracefs command write')
        finally:
            os.close(fd)


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
    match = re.search(r'-(\d+)\s+\[\d+\].*?\s(\d+)\.(\d{1,9}):\s+(map_create|map_listed_xdg|map_listed_x11):\s+(.*)$', line)
    if not match or int(match[1]) != pid:
        raise RuntimeError('Unexpected or unbound causal kernel event')
    digits = match[3]
    resolution = 10 ** (9 - len(digits))
    if resolution > 1000:
        raise RuntimeError('Causal kernel timestamp text is too coarse')
    timestamp = int(match[2]) * 1_000_000_000 + int(digits.ljust(9, '0'))
    # Linux rounds six-digit text to the nearest microsecond. Enclose its
    # literal display by one full unit on EACH side, never invent precision.
    event = dict(event=match[4], kernel_text_monotonic_ns=timestamp,
                 kernel_timestamp_text=match[2]+'.'+digits,
                 timestamp_rounding_allowance_ns=resolution,
                 timestamp_resolution_ns=resolution, kernel_pid=pid)
    if match[4] == 'map_create':
        body = re.fullmatch(r'(?:\([^\n]*\)\s+)?foreign_id="([0-9a-f]{32})"\s*', match[5])
        if not body:
            raise RuntimeError('Malformed before-mapping identity receipt')
        event.update(foreign_toplevel_id=body[1], lower_monotonic_ns=timestamp-resolution)
    else:
        body = re.fullmatch(r'\((0x[0-9a-f]+)\)\s+client_type=(0|2)\s+original_app_id="([A-Za-z0-9._-]{1,128})"\s+foreign_id="([0-9a-f]{32})"\s+app_id="([A-Za-z0-9._-]{1,128})"\s+client=(0x[0-9a-f]+)\s+handle=(0x[0-9a-f]+)\s+owner=(0x[0-9a-f]+)\s*', match[5])
        if not body or any(not 0 < int(body[n], 16) < 2**64 for n in (1,6,7,8)):
            raise RuntimeError('Malformed after-list-insertion native receipt')
        event.update(foreign_toplevel_id=body[4], upper_monotonic_ns=timestamp+resolution,
                     instruction_address=int(body[1],16), app_id=body[5],
                     client_address=int(body[6],16), handle_address=int(body[7],16),
                     handle_owner_address=int(body[8],16), client_type=int(body[2]),
                     original_app_id=body[3])
        expected_type = 0 if match[4] == 'map_listed_xdg' else 2
        if event['client_type'] != expected_type or event['original_app_id'] != event['app_id']:
            raise RuntimeError('Original app-ID getter kind or copied metadata disagrees')
        if event['handle_owner_address'] != event['client_address']:
            raise RuntimeError('Native mapping handle does not belong to captured client')
    return event


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
        self.upper_events = {}
        self.condition = threading.Condition()
        self.stopped = threading.Event()
        self.error = None
        self.thread = None
        self.fd = None
        self.proof = None
        self.requested_events = set()

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
            self.executable = executable
            mango_owner = subprocess.check_output(['rpm', '-qf', str(executable)], text=True).strip()
            if executable != Path('/usr/bin/mango') or not re.fullmatch(r'mangowm-0\.17\.3-[A-Za-z0-9._+]+\.x86_64', mango_owner):
                raise RuntimeError('Causal ordering requires the audited production Mango 0.17.3')
            mango_verified = subprocess.run(['rpm', '-Vf', str(executable)], text=True,
                                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if mango_verified.returncode or mango_verified.stdout or mango_verified.stderr:
                raise RuntimeError('Production Mango package verification failed')
            profile = mapping_profile(executable)
            mapping = instruction_mapping(executable, (proc/'maps').read_text(), profile['instruction_file_offset'])
            self.proof = dict(upper_mapping_profile=profile, upper_executable_mapping=mapping,
                upper_instruction_address=mapping['instruction_address'],
                upper_appid_offset=APPID_OFFSET, upper_handle_data_offset=HANDLE_DATA_OFFSET,
                audited_original_appid_sha256=ORIGINAL_APPID_AUDIT_SHA256,
                audited_mango_source_sha256=MANGO_SOURCE_SHA256, audited_mango_header_sha256=MANGO_HEADER_SHA256,
                method=METHOD, clock='mono_raw', userspace_clock='CLOCK_MONOTONIC_RAW', kernel_pid=self.pid,
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
                if os.path.ismount(self.root):
                    raise RuntimeError('Refusing to cover an existing tracing mount')
                self.mount_requested = True
                with deferred_termination():
                    subprocess.run(['mount', '-t', 'tracefs', 'tracefs', str(self.root)], check=True, timeout=15)
                    self.mounted = True
            self.instance = self.root / 'instances' / self.group
            with deferred_termination():
                self.instance.mkdir()
                self.instance_created = True
            (self.instance / 'tracing_on').write_text('0')
            (self.instance / 'trace_clock').write_text('mono_raw')
            if '[mono_raw]' not in (self.instance / 'trace_clock').read_text():
                raise RuntimeError('Causal trace clock is not the common monotonic raw clock')
            (self.instance / 'buffer_size_kb').write_text('128')
            (self.instance / 'options/overwrite').write_text('0')
            (self.instance / 'options/context-info').write_text('1')
            if (self.instance / 'options/record-tgid').exists():
                (self.instance / 'options/record-tgid').write_text('0')
            if (self.instance / 'options/nsecs').exists():
                (self.instance / 'options/nsecs').write_text('1')
            if (self.root / 'events' / self.group).exists():
                raise RuntimeError('Refusing to reuse an existing causal event group')
            commands = dict(map_create=(f'r:{self.group}/map_create {library}:0x{offset:x} '
                f'foreign_id=+0(+{IDENTIFIER_OFFSET}($retval)):string\n'))
            commands.update(upper_probe_commands(self.group, executable, profile))
            for name, command in commands.items():
                with deferred_termination():
                    self.requested_events.add(name)
                    write_uprobe_command(self.root, command)
                event = self.instance / 'events' / self.group / name
                expression = 'common_pid == ' + str(self.pid)
                if name == 'map_listed_xdg':
                    expression += ' && client_type == ' + str(profile['xdg_type'])
                elif name == 'map_listed_x11':
                    expression += ' && client_type == ' + str(profile['xwayland_type'])
                (event / 'filter').write_text(expression)
                (event / 'enable').write_text('1')
            with deferred_termination():
                self.fd = os.open(self.instance / 'trace_pipe', os.O_RDONLY | os.O_NONBLOCK)
            self.thread = threading.Thread(target=self._read, daemon=True)
            # The only collector worker inherits blocked cancellation signals.
            # Process-directed TERM/INT must remain pending on the main thread
            # during its ownership handoffs and complete bounded unwind.
            with deferred_termination():
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
                        target = self.events if event['event'] == 'map_create' else self.upper_events
                        if key in target or len(self.events)+len(self.upper_events) >= MAX_EVENTS:
                            raise RuntimeError('Duplicate or unbounded causal kernel events')
                        target[key] = event
                        self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.error = str(error)
                self.condition.notify_all()

    def _check_owner(self):
        proc = Path('/proc') / str(self.pid)
        try:
            start = int((proc/'stat').read_text().rsplit(')', 1)[1].split()[19])
            if (proc.stat().st_uid != self.proof['desktop_uid']
                    or start != self.proof['mango_start_ticks']
                    or (proc/'exe').resolve(strict=True) != self.executable):
                raise RuntimeError('Causal Mango owner changed during the launch')
        except (OSError, ValueError, IndexError) as error:
            raise RuntimeError('Causal Mango owner is absent or unreadable') from error

    def bound(self, windows, started_ns, ipc_lower_ns, ipc_upper_ns, pattern, timeout=2):
        self._check_owner()
        if (not isinstance(pattern, tuple) or not 0 < len(pattern) <= 8
                or len(set(pattern)) != len(pattern) or any(not isinstance(appid, str)
                    or not re.fullmatch('[a-z0-9._-]{1,128}', appid)
                    or re.fullmatch('[0-9a-f]{32}', appid) for appid in pattern)):
            raise RuntimeError('Native mapping bounds require the original exact application-ID predicate')
        identities = [window.get('foreign_toplevel_id') for window in windows]
        if not 0 < len(identities) <= 64 or len(set(identities)) != len(identities) or any(not isinstance(key, str) or not re.fullmatch('[0-9a-f]{32}', key) for key in identities):
            raise RuntimeError('Mapped IPC clients lack unique causal identities')
        if not started_ns <= ipc_lower_ns <= ipc_upper_ns:
            raise RuntimeError('IPC mapping interval does not belong to this launch')
        deadline = time.monotonic() + timeout
        with self.condition:
            while not all(key in self.events and key in self.upper_events for key in identities):
                if self.error:
                    raise RuntimeError(self.error)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Matched causal kernel receipt is missing; no weaker fallback')
                self.condition.wait(remaining)
            if self.error:
                raise RuntimeError(self.error)
            events = [dict(self.events[key]) for key in identities]
            upper_events = [dict(self.upper_events[key]) for key in identities]
        self._check_owner()
        if (any(type(window.get('id')) is not int or window['id'] <= 0 for window in windows)
                or len({window['id'] for window in windows}) != len(windows)
                or len({event['client_address'] for event in upper_events}) != len(windows)
                or len({event['handle_address'] for event in upper_events}) != len(windows)):
            raise RuntimeError('Mapped native and IPC clients have duplicate object identities')
        for window, lower, upper in zip(windows, events, upper_events):
            if (not started_ns <= lower['lower_monotonic_ns'] <= upper['upper_monotonic_ns']
                    or lower['lower_monotonic_ns'] > ipc_upper_ns
                    or upper['kernel_text_monotonic_ns']-upper['timestamp_rounding_allowance_ns'] > ipc_upper_ns
                    or upper['instruction_address'] != self.proof['upper_instruction_address']
                    or upper['handle_owner_address'] != upper['client_address']
                    or not original_appid_matches(upper, window, pattern)):
                raise RuntimeError('Causal receipt ordering, callsite or current launch is invalid')
        # The original predicate succeeds when ANY newly matched client enters
        # the managed list. Each matched pair brackets that same transition;
        # take the earliest upper and earliest lower, then intersect with IPC.
        lower = max(ipc_lower_ns, min(event['lower_monotonic_ns'] for event in events))
        upper = min(ipc_upper_ns, min(event['upper_monotonic_ns'] for event in upper_events))
        if not started_ns <= lower <= upper <= ipc_upper_ns:
            raise RuntimeError('Native and IPC mapping brackets do not intersect')
        return lower, upper, dict(self.proof, matched_events=events,
            matched_upper_events=upper_events, matched_ipc_clients=[dict(window) for window in windows],
            application_id_predicate=list(pattern), ipc_lower_monotonic_ns=ipc_lower_ns,
            ipc_upper_monotonic_ns=ipc_upper_ns,
            loss_counts=loss_counts(self.instance), status='bounded-managed-list-insertion')

    def __exit__(self, *unused):
        # A second TERM/INT must not interrupt bounded cleanup. Restore the old
        # handlers before unmasking; pending cancellation then acts only after
        # every owned resource has had its cleanup attempt.
        with deferred_termination():
            self._cleanup()

    def _cleanup(self):
        errors = []
        def cleanup(action):
            try:
                action()
            except BaseException as error:
                errors.append(str(error))
        self.stopped.set()
        if self.thread:
            cleanup(lambda: self.thread.join(timeout=2))
            if self.thread.is_alive():
                errors.append('Owned causal reader did not stop')
        if self.error:
            errors.append(self.error)
        if self.fd is not None:
            cleanup(lambda: os.close(self.fd))
            self.fd = None
        if getattr(self, 'instance_created', False) and self.instance.exists():
            cleanup(lambda: (self.instance / 'tracing_on').write_text('0'))
            cleanup(lambda: loss_counts(self.instance))
            for name in self.requested_events:
                event = self.instance / 'events' / self.group / name / 'enable'
                if event.exists():
                    cleanup(lambda event=event: event.write_text('0'))
            cleanup(self.instance.rmdir)
        for name in sorted(self.requested_events):
            event = self.root / 'events' / self.group / name if self.root else None
            if event and event.exists():
                cleanup(lambda name=name: write_uprobe_command(self.root, '-:' + self.group + '/' + name + '\n'))
        self.requested_events.clear()
        if (getattr(self, 'mounted', False) or getattr(self, 'mount_requested', False)) and os.path.ismount(self.root):
            cleanup(lambda: subprocess.run(['umount', str(self.root)], check=True, timeout=15))
            self.mounted = False
        if hasattr(self, 'old_sigterm'):
            cleanup(lambda: signal.signal(signal.SIGTERM, self.old_sigterm))
            del self.old_sigterm
        if errors:
            raise RuntimeError('Owned causal instrumentation cleanup failed: ' + '; '.join(errors))
