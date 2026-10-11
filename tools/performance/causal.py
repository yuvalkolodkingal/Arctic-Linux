"""Read-only causal mapping bounds, only in the disposable measurement guest.

The wlroots handle return preserves identity provenance. Audited instructions
immediately before and after Mango's managed client-list insertion bracket
that same transition. All use the kernel raw clock; none is a frame timestamp
or an IPC response-delivery timestamp. Probe work remains in the measurements.
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
METHOD = 'wlroots-0.20-and-mango-managed-list-original-appid-preinsert-bracket-raw-v5'
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
         native_audit_sha256='dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c',
         function_file_offset=0x430d0, function_size=4109,
         function_sha256='d48615861b8819d95e30fbbf74db46e24f8e3d738e20824e0e598578972004a2',
         instruction_file_offset=0x435de, client_ext_offset=1584,
         lower_instruction_file_offsets=dict(tail=0x435d9, head=0x43733, scroller=0x43d63),
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='2f1107221157f47418cfda87dd091a3bb81ecd97dc2945184d0c42de7bbd254b',
         native_audit_sha256='dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c',
         function_file_offset=0x43110, function_size=4109,
         function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
         instruction_file_offset=0x4361e, client_ext_offset=1584,
         lower_instruction_file_offsets=dict(tail=0x43619, head=0x43773, scroller=0x43da3),
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35',
         native_audit_sha256='dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c',
         function_file_offset=0x430d0, function_size=4109,
         function_sha256='11a56d467fe7e444f46fa6da1f91a88ecf1a26bc3c54e4965727438e078a47dd',
         instruction_file_offset=0x435de, client_ext_offset=1584,
         lower_instruction_file_offsets=dict(tail=0x435d9, head=0x43733, scroller=0x43d63),
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='98582eccb610fc83282d1e64e975968aff2ddcfd5124d783a2bab78b98f681ca',
         native_audit_sha256='eef982194692b3a10412de30a47afcb3bdc675dec00d29f7840bdaf01d54d80c',
         function_file_offset=0x43110, function_size=4109,
         function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc',
         instruction_file_offset=0x4361e, client_ext_offset=1584,
         lower_instruction_file_offsets=dict(tail=0x43619, head=0x43773, scroller=0x43da3),
         ipc_function_file_offset=0x6b00, ipc_function_size=1234,
         ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead',
         client_type_offset=0, client_surface_offset=328, xdg_type=0,
         xdg_toplevel_offset=56, xdg_appid_offset=192,
         xwayland_type=2, xwayland_class_offset=144),
    dict(executable_sha256='52e6072d93970d48c067b148a696edd5cb85a3504f1f855fdffaf123b8f7a58f', native_audit_sha256='8b2b265bce2765cfc43a60605fae714c9bae7f0cd3659d1839df84e58708afa8', function_file_offset=0x43110, function_size=4109, function_sha256='3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc', instruction_file_offset=0x4361e, client_ext_offset=1584, lower_instruction_file_offsets=dict(tail=0x43619, head=0x43773, scroller=0x43da3), ipc_function_file_offset=0x6b00, ipc_function_size=1234, ipc_function_sha256='11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead', client_type_offset=0, client_surface_offset=328, xdg_type=0, xdg_toplevel_offset=56, xdg_appid_offset=192, xwayland_type=2, xwayland_class_offset=144),)


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
        lower = profile.get('lower_instruction_file_offsets')
        sites = [profile['instruction_file_offset']]
        if (type(lower) is not dict or set(lower) != {'tail', 'head', 'scroller'}
                or any(type(value) is not int for value in lower.values())):
            raise RuntimeError('Incomplete audited managed-insertion branch profile')
        sites += list(lower.values())
        if (len(set(sites)) != 4 or any(type(value) is not int or not start <= value < start+size
                for value in sites)):
            raise RuntimeError('Audited managed-insertion sites lack distinct bounded instructions')
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


def native_probe_commands(group, executable, profile, sites):
    """Keep the selected original FIRST at each type-specific native site.

    Exact-byte CFG and destination proofs bind these sites to server.clients,
    assuming valid compositor lists and SysV callee-preserved RBX/R12/R14.
    Argument fetching and trap/preemption costs are never subtracted.
    """
    common = (f'foreign_id=+0(+{IDENTIFIER_OFFSET}(+{profile["client_ext_offset"]}(%bx))):string '
        f'app_id=+0(+{APPID_OFFSET}(+{profile["client_ext_offset"]}(%bx))):string '
        f'client=%bx:x64 handle=+{profile["client_ext_offset"]}(%bx):x64 '
        f'owner=+{HANDLE_DATA_OFFSET}(+{profile["client_ext_offset"]}(%bx)):x64')
    surface = f'+{profile["client_surface_offset"]}(%bx)'
    chains = dict(xdg=f'+0(+{profile["xdg_appid_offset"]}(+{profile["xdg_toplevel_offset"]}({surface})))',
                  x11=f'+0(+{profile["xwayland_class_offset"]}({surface}))')
    return {name+'_'+kind: f'p:{group}/{name}_{kind} {executable}:0x{offset:x} '
            + f'client_type=+{profile["client_type_offset"]}(%bx):u32 '
            + 'original_app_id=' + chain + ':string ' + common + '\n'
            for name, offset in sites.items() for kind, chain in chains.items()}


def upper_probe_commands(group, executable, profile):
    return native_probe_commands(group, executable, profile,
        dict(map_listed=profile['instruction_file_offset']))


def lower_probe_commands(group, executable, profile):
    return native_probe_commands(group, executable, profile,
        {'map_before_'+branch: offset for branch, offset in profile['lower_instruction_file_offsets'].items()})


def kernel_readbacks_valid(readbacks, pid):
    """Validate literal kernel schemas and effective filters, without tracefs IO."""
    if type(pid) is not int or not 0 < pid < 2**31 or not isinstance(readbacks, dict):
        return False
    names = {'map_create', 'map_listed_xdg', 'map_listed_x11'} | {
        'map_before_' + branch + '_' + kind
        for branch in ('tail', 'head', 'scroller') for kind in ('xdg', 'x11')}
    if set(readbacks) != names:
        return False
    common = [('unsigned short', 'common_type', 0, 2, 0),
              ('unsigned char', 'common_flags', 2, 1, 0),
              ('unsigned char', 'common_preempt_count', 3, 1, 0),
              ('int', 'common_pid', 4, 4, 1)]
    identity = [('unsigned long', '__probe_func', 8, 8, 0),
                ('unsigned long', '__probe_ret_ip', 16, 8, 0),
                ('__data_loc char[]', 'foreign_id', 24, 4, 1)]
    native = [('unsigned long', '__probe_ip', 8, 8, 0),
              ('u32', 'client_type', 16, 4, 0),
              ('__data_loc char[]', 'original_app_id', 20, 4, 1),
              ('__data_loc char[]', 'foreign_id', 24, 4, 1),
              ('__data_loc char[]', 'app_id', 28, 4, 1),
              ('u64', 'client', 32, 8, 0), ('u64', 'handle', 40, 8, 0),
              ('u64', 'owner', 48, 8, 0)]
    event_ids = set()
    field_pattern = re.compile(
        r'[ \t]*field:([^;\n]+);[ \t]*offset:([0-9]{1,5});[ \t]*'
        r'size:([0-9]{1,5});[ \t]*signed:([01]);[ \t]*')
    for name, record in readbacks.items():
        if (not isinstance(record, dict) or set(record) != {
                'format_text', 'format_sha256', 'filter_text', 'filter_sha256'}):
            return False
        for key, limit in (('format', 16384), ('filter', 1024)):
            raw = record[key + '_text']
            if (not isinstance(raw, str) or not 0 < len(raw) <= limit or not raw.endswith('\n')
                    or any(char != '\n' and char != '\t' and not ' ' <= char <= '~' for char in raw)
                    or record[key + '_sha256'] != hashlib.sha256(raw.encode('ascii')).hexdigest()):
                return False
        lines = record['format_text'].splitlines()
        if (len(lines) < 5 or lines[0] != 'name: ' + name
                or not re.fullmatch(r'ID: [1-9][0-9]{0,4}', lines[1])
                or lines[2] != 'format:'):
            return False
        event_id = int(lines[1][4:])
        if event_id > 65535 or event_id in event_ids:
            return False
        event_ids.add(event_id)
        fields, footer = [], None
        for line in lines[3:]:
            if footer is not None:
                return False
            if not line.strip(' \t'):
                continue
            if line.startswith('print fmt: '):
                if footer is not None or not re.fullmatch(r'print fmt: "(?:[^"\\]|\\.)*"(?:, [^\n]+)?', line):
                    return False
                footer = line
                continue
            match = field_pattern.fullmatch(line)
            if footer is not None or not match:
                return False
            declaration = match[1].rsplit(' ', 1)
            if len(declaration) != 2:
                return False
            fields.append((declaration[0], declaration[1], int(match[2]), int(match[3]), int(match[4])))
        expected_footer = (r'print fmt: "(%lx <- %lx) foreign_id=\"%s\"", REC->__probe_func, REC->__probe_ret_ip, __get_str(foreign_id)'
                           if name == 'map_create' else
                           r'print fmt: "(%lx) client_type=%u original_app_id=\"%s\" foreign_id=\"%s\" app_id=\"%s\" client=0x%Lx handle=0x%Lx owner=0x%Lx", REC->__probe_ip, REC->client_type, __get_str(original_app_id), __get_str(foreign_id), __get_str(app_id), REC->client, REC->handle, REC->owner')
        if footer != expected_footer or fields != common + (identity if name == 'map_create' else native):
            return False
        expected_filter = 'common_pid==' + str(pid)
        if name != 'map_create':
            expected_filter += '&&client_type==' + ('0' if name.endswith('_xdg') else '2')
        filter_text = record['filter_text']
        if ('\n' in filter_text[:-1]
                or re.sub(r'[ \t\n]', '', filter_text) != expected_filter
                or not re.fullmatch(r'[ \t]*common_pid[ \t]*==[ \t]*' + str(pid)
                                    + (r'[ \t]*&&[ \t]*client_type[ \t]*==[ \t]*'
                                       + ('0' if name.endswith('_xdg') else '2')
                                       if name != 'map_create' else '') + r'[ \t]*\n', filter_text)):
            return False
    return True

def original_appid_matches(event, window, pattern):
    # An intermediate pointer-dereference fault can leave the original data_loc
    # pointing at the following foreign identifier. No admitted role may alias it.
    if any(re.fullmatch('[0-9a-f]{32}', appid) for appid in pattern):
        return False
    if type(event.get('client_type')) is not int or event['client_type'] not in (0, 2):
        return False
    kind = 'xdg' if event['client_type'] == 0 else 'x11'
    if event.get('event') not in ({'map_listed_'+kind} | {
            'map_before_'+branch+'_'+kind for branch in ('tail', 'head', 'scroller')}):
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
    match = re.search(r'-(\d+)\s+\[\d+\].*?\s(\d+)\.(\d{1,9}):\s+(map_create|map_listed_(?:xdg|x11)|map_before_(?:tail|head|scroller)_(?:xdg|x11)):\s+(.*)$', line)
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
            raise RuntimeError('Malformed managed-list-insertion native receipt')
        event.update(foreign_toplevel_id=body[4],
                     instruction_address=int(body[1],16), app_id=body[5],
                     client_address=int(body[6],16), handle_address=int(body[7],16),
                     handle_owner_address=int(body[8],16), client_type=int(body[2]),
                     original_app_id=body[3])
        if match[4].startswith('map_before_'):
            event.update(lower_monotonic_ns=timestamp-resolution)
        else:
            event.update(upper_monotonic_ns=timestamp+resolution)
        expected_type = 0 if match[4].endswith('_xdg') else 2
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


class OuterBoundProbe:
    def __init__(self, prefix):
        self.prefix = prefix
        self.root = None
        self.instance = None
        self.group = 'arctic_map_' + uuid.uuid4().hex
        self.events = {}
        self.lower_events = {}
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
            lower_mappings = {branch: instruction_mapping(executable, (proc/'maps').read_text(), offset)
                for branch, offset in profile['lower_instruction_file_offsets'].items()}
            self.proof = dict(upper_mapping_profile=profile, upper_executable_mapping=mapping,
                lower_executable_mappings=lower_mappings,
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
            commands.update(lower_probe_commands(self.group, executable, profile))
            commands.update(upper_probe_commands(self.group, executable, profile))
            readbacks = {}
            for name, command in commands.items():
                with deferred_termination():
                    self.requested_events.add(name)
                    write_uprobe_command(self.root, command)
                event = self.instance / 'events' / self.group / name
                expression = 'common_pid == ' + str(self.pid)
                if name.endswith('_xdg'):
                    expression += ' && client_type == ' + str(profile['xdg_type'])
                elif name.endswith('_x11'):
                    expression += ' && client_type == ' + str(profile['xwayland_type'])
                (event / 'filter').write_text(expression)
                readbacks[name] = self._readback(event)
                (event / 'enable').write_text('1')
            if not kernel_readbacks_valid(readbacks, self.pid):
                raise RuntimeError('Registered causal kernel format or PID/type filter differs')
            self.proof['kernel_event_readbacks'] = readbacks
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
                        target = (self.events if event['event'] == 'map_create' else
                                  self.lower_events if event['event'].startswith('map_before_') else self.upper_events)
                        if key in target or len(self.events)+len(self.lower_events)+len(self.upper_events) >= MAX_EVENTS:
                            raise RuntimeError('Duplicate or unbounded causal kernel events')
                        target[key] = event
                        self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.error = str(error)
                self.condition.notify_all()

    @staticmethod
    def _readback(event):
        # Preserve exact kernel bytes in machine receipts. A successful write
        # alone does not prove the running kernel's layout or active filter.
        with (event / 'format').open('rb') as stream:
            format_raw = stream.read(16385)
        with (event / 'filter').open('rb') as stream:
            filter_raw = stream.read(1025)
        if len(format_raw) > 16384 or len(filter_raw) > 1024:
            raise RuntimeError('Unbounded causal kernel format/filter readback')
        return dict(format_text=format_raw.decode('ascii'),
            format_sha256=hashlib.sha256(format_raw).hexdigest(),
            filter_text=filter_raw.decode('ascii'),
            filter_sha256=hashlib.sha256(filter_raw).hexdigest())

    def _check_readbacks(self):
        actual = {name: self._readback(self.instance / 'events' / self.group / name)
                  for name in self.requested_events}
        if actual != self.proof['kernel_event_readbacks'] or not kernel_readbacks_valid(actual, self.pid):
            raise RuntimeError('Registered causal kernel format or PID/type filter changed')

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
        self._check_readbacks()
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
            while not all(key in self.events and key in self.lower_events and key in self.upper_events for key in identities):
                if self.error:
                    raise RuntimeError(self.error)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RuntimeError('Matched causal kernel receipt is missing; no weaker fallback')
                self.condition.wait(remaining)
            if self.error:
                raise RuntimeError(self.error)
            identity_events = [dict(self.events[key]) for key in identities]
            events = [dict(self.lower_events[key]) for key in identities]
            upper_events = [dict(self.upper_events[key]) for key in identities]
        self._check_owner()
        self._check_readbacks()
        if (any(type(window.get('id')) is not int or window['id'] <= 0 for window in windows)
                or len({window['id'] for window in windows}) != len(windows)
                or len({event['client_address'] for event in upper_events}) != len(windows)
                or len({event['handle_address'] for event in upper_events}) != len(windows)):
            raise RuntimeError('Mapped native and IPC clients have duplicate object identities')
        for window, identity, lower, upper in zip(windows, identity_events, events, upper_events):
            branch = lower['event'].split('_')[2]
            expected_lower = self.proof['lower_executable_mappings'].get(branch, {}).get('instruction_address')
            if (not started_ns <= identity['lower_monotonic_ns'] <= lower['lower_monotonic_ns'] <= upper['upper_monotonic_ns']
                    or identity['foreign_toplevel_id'] != window['foreign_toplevel_id']
                    or lower['foreign_toplevel_id'] != window['foreign_toplevel_id']
                    or upper['foreign_toplevel_id'] != window['foreign_toplevel_id']
                    or lower['lower_monotonic_ns'] > ipc_upper_ns
                    or upper['kernel_text_monotonic_ns']-upper['timestamp_rounding_allowance_ns'] > ipc_upper_ns
                    or upper['instruction_address'] != self.proof['upper_instruction_address']
                    or lower['instruction_address'] != expected_lower
                    or upper['handle_owner_address'] != upper['client_address']
                    or any(lower[key] != upper[key] for key in ('foreign_toplevel_id', 'client_type',
                        'original_app_id', 'app_id', 'client_address', 'handle_address', 'handle_owner_address'))
                    or not original_appid_matches(lower, window, pattern)
                    or not original_appid_matches(upper, window, pattern)):
                raise RuntimeError('Causal receipt ordering, callsite or current launch is invalid')
        # The original predicate succeeds when ANY newly matched client enters
        # the managed list. Each matched pair brackets that same transition;
        # take the earliest upper and earliest lower, then intersect with IPC.
        lower = max(ipc_lower_ns, min(event['lower_monotonic_ns'] for event in events))
        upper = min(ipc_upper_ns, min(event['upper_monotonic_ns'] for event in upper_events))
        if not started_ns <= lower <= upper <= ipc_upper_ns:
            raise RuntimeError('Native and IPC mapping brackets do not intersect')
        return lower, upper, dict(self.proof, matched_events=events, matched_identity_events=identity_events,
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


# Whole providers from both frozen ISO images, independently decoded and reviewed.
# wl_list_insert's forward publication is +15; its immediate following IP is +19.
# The +23 backward-neighbor store and original Mango completion remain witnessed.
FORWARD_AUDIT_SHA256 = 'd9344fb1fb3a7129871f5a36c710951085e9fe07faa490cf04fd168afe1d00e9'
FORWARD_PEER_SHA256 = 'a3dedf94835b8ab4190d639d6a3c17350e6ada860f7b764a0fdb0facd0bdc3ff'
FORWARD_METHOD = 'wlroots-mango-original-appid-wayland-forward-store-bracket-raw-v6'
FORWARD_PROFILES = (
    dict(path='/usr/lib64/libwayland-server.so.0.26.0', bytes=87160,
         sha256='6f27c2fc1589f9d8e5525ea7729fbf35cbd27d5501f36b068cad4213a665736d',
         owner='libwayland-server\t0\t1.26.0\t1.fc44\tx86_64', offset=0x4290),
    dict(path='/usr/lib64/libwayland-client.so.0.26.0', bytes=66168,
         sha256='cb517c02f6e808257932a4b3f1a4bd1232ce415cdd8e41a854ff0f0e918b51c9',
         owner='libwayland-client\t0\t1.26.0\t1.fc44\tx86_64', offset=0x2f90),
)
FORWARD_BYTES = bytes.fromhex('f30f1efa488b470848893e4889460848897708488b4608488930c3')


class StoreProofError(RuntimeError):
    """Fixed failure labels; no new traceback-cause admission or weaker fallback."""


def forward_callers(proof):
    return [proof['lower_executable_mappings'][branch]['instruction_address'] + 5
            for branch in ('tail', 'head', 'scroller')]


def forward_readbacks_valid(readbacks, pid, callers):
    """Validate all nine original schemas and four exact store/PID/type/caller schemas."""
    names = {'map_store_' + phase + '_' + kind for phase in ('before', 'after') for kind in ('xdg', 'x11')}
    if (type(readbacks) is not dict or type(callers) is not list or len(callers) != 3
            or len(set(callers)) != 3 or any(type(value) is not int or not 0 < value < 2**64 for value in callers)):
        return False
    outer = {name: record for name, record in readbacks.items() if name not in names}
    if set(readbacks) != set(outer) | names or not kernel_readbacks_valid(outer, pid):
        return False
    ids = [re.search(r'^ID: ([0-9]+)$', record['format_text'], re.M) for record in readbacks.values()]
    if any(value is None for value in ids) or len({value[1] for value in ids}) != 13:
        return False
    old_footer = r'print fmt: "(%lx) client_type=%u original_app_id=\"%s\" foreign_id=\"%s\" app_id=\"%s\" client=0x%Lx handle=0x%Lx owner=0x%Lx", REC->__probe_ip, REC->client_type, __get_str(original_app_id), __get_str(foreign_id), __get_str(app_id), REC->client, REC->handle, REC->owner'
    new_footer = old_footer.replace('owner=0x%Lx"', 'owner=0x%Lx position=0x%Lx link=0x%Lx caller=0x%Lx"') + ', REC->position, REC->link, REC->caller'
    for name in sorted(names):
        record = readbacks[name]
        if type(record) is not dict or set(record) != {'format_text', 'format_sha256', 'filter_text', 'filter_sha256'}:
            return False
        for key, maximum in (('format', 16384), ('filter', 1024)):
            text = record[key + '_text']
            if (type(text) is not str or not 0 < len(text) <= maximum or not text.endswith('\n')
                    or any(c not in '\n\t' and not ' ' <= c <= '~' for c in text)
                    or hashlib.sha256(text.encode('ascii')).hexdigest() != record[key + '_sha256']):
                return False
        kind = name.rsplit('_', 1)[1]
        expected = 'common_pid==' + str(pid) + '&&client_type==' + ('0' if kind == 'xdg' else '2')
        expected += '&&(' + '||'.join('caller==' + str(value) for value in callers) + ')'
        if re.sub(r'[ \t\n]', '', record['filter_text']) != expected or '\n' in record['filter_text'][:-1]:
            return False
        text = record['format_text']
        for field, offset in (('position', 56), ('link', 64), ('caller', 72)):
            pattern = r'^[ \t]*field:u64 ' + field + r';[ \t]*offset:' + str(offset) + r';[ \t]*size:8;[ \t]*signed:0;[ \t]*\n'
            text, count = re.subn(pattern, '', text, flags=re.M)
            if count != 1:
                return False
        if text.count(new_footer) != 1:
            return False
        text = text.replace(new_footer, old_footer).replace('name: ' + name + '\n', 'name: map_listed_' + kind + '\n', 1)
        filter_text = 'common_pid == ' + str(pid) + ' && client_type == ' + ('0' if kind == 'xdg' else '2') + '\n'
        trial = dict(outer)
        trial['map_listed_' + kind] = dict(format_text=text, format_sha256=hashlib.sha256(text.encode()).hexdigest(),
            filter_text=filter_text, filter_sha256=hashlib.sha256(filter_text.encode()).hexdigest())
        if not kernel_readbacks_valid(trial, pid):
            return False
    return True


def forward_probe_commands(group, mango, provider):
    commands = native_probe_commands(group, Path(provider['profile']['path']), mango,
        dict(map_store_before=provider['profile']['offset'] + 15, map_store_after=provider['profile']['offset'] + 19))
    return {name: command[:-1] + ' position=%di:x64 link=%si:x64 caller=+0(%sp):x64\n'
            for name, command in commands.items()}


def forward_trace_receipt(line, pid):
    token = re.search(r': (map_store_(before|after)_(xdg|x11)):', line)
    if token is None:
        return trace_receipt(line, pid)
    fields = re.search(r' position=(0x[0-9a-f]+) link=(0x[0-9a-f]+) caller=(0x[0-9a-f]+)\s*$', line)
    if not fields or any(not 0 < int(value, 16) < 2**64 for value in fields.groups()):
        raise StoreProofError('Forward-store receipt fields are malformed')
    alias = 'map_before_tail_' if token[2] == 'before' else 'map_listed_'
    event = trace_receipt(line[:fields.start()].replace(token[1], alias + token[3], 1), pid)
    event.update(event=token[1], position_address=int(fields[1], 16), link_address=int(fields[2], 16), caller_address=int(fields[3], 16))
    return event


def forward_jump_slot(raw):
    """Decode the exact ELF64 JUMP_SLOT symbol; no guessed runtime GOT address."""
    try:
        header = struct.unpack_from('<16sHHIQQQIHHHHHH', raw)
        if raw[:6] != b'\x7fELF\x02\x01' or header[2] != 62 or header[11] != 64 or not 0 < header[12] <= 4096:
            raise StoreProofError('Forward-store Mango ELF layout differs')
        sections = [struct.unpack_from('<IIQQQQIIQQ', raw, header[6] + index*64) for index in range(header[12])]
        found = []
        for section in sections:
            if section[1] != 4 or section[9] != 24 or section[5] % 24:
                continue
            symbols = sections[section[6]]
            strings = sections[symbols[6]]
            if symbols[1] != 11 or symbols[9] != 24 or strings[4] + strings[5] > len(raw):
                continue
            for offset in range(section[4], section[4] + section[5], 24):
                address, info, addend = struct.unpack_from('<QQq', raw, offset)
                if info & 0xffffffff != 7 or (info >> 32)*24 >= symbols[5]:
                    continue
                symbol = struct.unpack_from('<IBBHQQ', raw, symbols[4] + (info >> 32)*24)
                start = strings[4] + symbol[0]
                end = raw.find(b'\0', start, strings[4] + strings[5])
                if end >= start and raw[start:end] == b'wl_list_insert':
                    if addend != 0 or symbol[3] != 0:
                        raise StoreProofError('Forward-store relocation is not an imported JUMP_SLOT')
                    found.append(address)
        if len(found) != 1:
            raise StoreProofError('Forward-store relocation is absent or ambiguous')
        return found[0]
    except (IndexError, struct.error) as error:
        raise StoreProofError('Forward-store ELF tables are malformed') from error


def forward_memory_word(proc, address):
    fd = os.open(proc / 'mem', os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        raw = os.pread(fd, 8, address)
        if len(raw) != 8:
            raise StoreProofError('Forward-store resolved target is unreadable')
        return struct.unpack('<Q', raw)[0]
    finally:
        os.close(fd)


def forward_mango_file(executable, mango):
    import stat
    fd = os.open(executable, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 64 * 1024 * 1024:
            raise StoreProofError('Forward-store Mango is not one bounded regular file')
        raw = os.pread(fd, info.st_size + 1, 0)
        if (len(raw) != info.st_size or identity(os.fstat(fd)) != identity(info)
                or hashlib.sha256(raw).hexdigest() != mango['executable_sha256']):
            raise StoreProofError('Forward-store Mango identity changed')
        return raw, identity(info)
    finally:
        os.close(fd)


def forward_provider(proc, executable, mango):
    import stat
    maps = (proc / 'maps').read_text()
    raw, mango_identity = forward_mango_file(executable, mango)
    mango_rows = [line.split(None, 5) for line in maps.splitlines() if len(line.split(None, 5)) == 6]
    mango_rows = [row for row in mango_rows if row[5] == str(executable)]
    mango_device = f'{os.major(mango_identity[0]):02x}:{os.minor(mango_identity[0]):02x}'
    if not mango_rows or any(row[3] != mango_device or int(row[4]) != mango_identity[1] for row in mango_rows):
        raise StoreProofError('Forward-store Mango mapping differs from verified file')
    virtual = forward_jump_slot(raw)
    # Derive the text load bias and the separate data-load file offset. Mango's
    # writable LOAD has a real +0x1000 virtual/file difference; never assume zero.
    segments = [struct.unpack_from('<IIQQQQQQ', raw, struct.unpack_from('<Q', raw, 32)[0] + n*56)
                for n in range(struct.unpack_from('<H', raw, 56)[0])]
    text_loads = [segment for segment in segments if segment[0] == 1 and segment[1] & 1
        and segment[2] <= mango['instruction_file_offset'] < segment[2] + segment[5]]
    data_loads = [segment for segment in segments if segment[0] == 1 and segment[1] & 4
        and segment[3] <= virtual and virtual + 8 <= segment[3] + segment[5]]
    if len(text_loads) != 1 or len(data_loads) != 1 or text_loads[0][2] != text_loads[0][3]:
        raise StoreProofError('Forward-store Mango load bias ABI differs')
    got_file_offset = virtual - data_loads[0][3] + data_loads[0][2]
    mapping = instruction_mapping(executable, maps, mango['instruction_file_offset'])
    address = mapping['start'] - mapping['file_offset'] + virtual
    got_maps = [line.split(None, 5) for line in maps.splitlines() if len(line.split(None, 5)) == 6]
    got_maps = [row for row in got_maps if row[5] == str(executable) and row[1].startswith('r')
                and int(row[0].split('-')[0], 16) <= address and address + 8 <= int(row[0].split('-')[1], 16)]
    if len(got_maps) != 1:
        raise StoreProofError('Forward-store GOT lacks one readable Mango mapping')
    got_row = got_maps[0]
    got_mapping = dict(start=int(got_row[0].split('-')[0], 16), end=int(got_row[0].split('-')[1], 16),
        file_offset=int(got_row[2], 16), address=address)
    if got_mapping['start'] + got_file_offset - got_mapping['file_offset'] != address:
        raise StoreProofError('Forward-store GOT virtual/file mapping differs')
    target = forward_memory_word(proc, address)
    matched = []
    for profile in FORWARD_PROFILES:
        path = Path(profile['path'])
        if not any(line.endswith(' ' + str(path)) for line in maps.splitlines()):
            continue
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            info = os.fstat(fd)
            data = os.pread(fd, profile['bytes'] + 1, 0)
            if (not stat.S_ISREG(info.st_mode) or info.st_size != profile['bytes'] or len(data) != profile['bytes']
                    or hashlib.sha256(data).hexdigest() != profile['sha256']
                    or data[profile['offset']:profile['offset'] + 27] != FORWARD_BYTES):
                raise StoreProofError('Forward-store provider whole ELF differs')
            rows = [line.split(None, 5) for line in maps.splitlines() if len(line.split(None, 5)) == 6]
            rows = [row for row in rows if row[5] == str(path)]
            device = f'{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x}'
            if any(row[3] != device or int(row[4]) != info.st_ino for row in rows):
                raise StoreProofError('Forward-store mapping inode differs from verified file')
            entry = instruction_mapping(path, maps, profile['offset'])
            if entry['instruction_address'] != target:
                continue
            owner = subprocess.check_output(['rpm', '-qf', '--qf', '%{NAME}\t%{EPOCHNUM}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\n', str(path)], text=True, timeout=30).strip()
            checked = subprocess.run(['rpm', '-Vf', str(path)], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
            if owner != profile['owner'] or checked.returncode or checked.stdout or checked.stderr:
                raise StoreProofError('Forward-store provider full RPM verification failed')
            matched.append(dict(profile=dict(profile), entry_mapping=entry,
                before_mapping=instruction_mapping(path, maps, profile['offset'] + 15),
                after_mapping=instruction_mapping(path, maps, profile['offset'] + 19),
                got_address=address, got_virtual_address=virtual, got_file_offset=got_file_offset,
                got_mapping=got_mapping, resolved_target=target,
                inode=info.st_ino, device=device, rpm_owner=owner,
                audit_sha256=FORWARD_AUDIT_SHA256, peer_sha256=FORWARD_PEER_SHA256))
        finally:
            os.close(fd)
    current_maps = (proc / 'maps').read_text()
    relevant = {str(executable)} | {profile['path'] for profile in FORWARD_PROFILES}
    selected = lambda value: [line for line in value.splitlines() if len(line.split(None, 5)) == 6 and line.split(None, 5)[5] in relevant]
    _, current_identity = forward_mango_file(executable, mango)
    if (len(matched) != 1 or current_identity != mango_identity or selected(current_maps) != selected(maps)
            or forward_memory_word(proc, address) != target):
        raise StoreProofError('Forward-store provider resolution is unknown or changed')
    return matched[0]


def forward_bound(probe, outer, windows, started, ipc_lower, ipc_upper, timeout):
    provider = probe.proof.get('forward_provider')
    if type(provider) is not dict:
        raise StoreProofError('Forward-store provider proof is mandatory')
    identities = [window['foreign_toplevel_id'] for window in windows]
    deadline = time.monotonic() + timeout
    with probe.condition:
        while not all(key in probe.store_events['before'] and key in probe.store_events['after'] for key in identities):
            if probe.error:
                raise StoreProofError('Forward-store reader failed')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise StoreProofError('Forward-store receipts are missing; no weaker fallback')
            probe.condition.wait(remaining)
        if probe.error:
            raise StoreProofError('Forward-store reader failed')
        before = [dict(probe.store_events['before'][key]) for key in identities]
        after = [dict(probe.store_events['after'][key]) for key in identities]
    probe._check_owner()
    probe._check_readbacks()
    current = forward_provider(Path('/proc') / str(probe.pid), probe.executable, probe.proof['upper_mapping_profile'])
    probe._check_owner()
    if current != provider:
        raise StoreProofError('Forward-store provider changed during launch')
    proof = dict(outer[2], method=FORWARD_METHOD, matched_store_before_events=before, matched_store_after_events=after)
    lower = max(ipc_lower, min(event['lower_monotonic_ns'] for event in before))
    upper = min(ipc_upper, min(event['upper_monotonic_ns'] for event in after))
    # Reuse the independently identical validator also required by the comparator.
    if not forward_events_valid(proof, started, lower, upper):
        raise StoreProofError('Forward-store identity, nesting or completion witness differs')
    return lower, upper, dict(proof, loss_counts=loss_counts(probe.instance))


def forward_events_valid(proof, started, lower, upper):
    """Strict shared producer/replay validation; outer caller/identity checks are additional."""
    provider = proof.get('forward_provider')
    if (type(provider) is not dict or set(provider) != {'profile', 'entry_mapping', 'before_mapping', 'after_mapping',
            'got_address', 'got_virtual_address', 'got_file_offset', 'got_mapping', 'resolved_target', 'inode', 'device', 'rpm_owner', 'audit_sha256', 'peer_sha256'}
            or provider.get('profile') not in FORWARD_PROFILES
            or proof.get('mango_sha256') not in {'67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35',
                '52e6072d93970d48c067b148a696edd5cb85a3504f1f855fdffaf123b8f7a58f'}
            or provider.get('audit_sha256') != FORWARD_AUDIT_SHA256 or provider.get('peer_sha256') != FORWARD_PEER_SHA256
            or provider.get('rpm_owner') != provider['profile']['owner']
            or any(type(provider.get(key)) is not int or provider[key] <= 0 for key in
                   ('got_address', 'got_virtual_address', 'got_file_offset', 'resolved_target', 'inode'))
            or not isinstance(provider.get('device'), str) or not re.fullmatch('[0-9a-f]{2,8}:[0-9a-f]{2,8}', provider['device'])
            or provider['got_virtual_address'] != 0x7ddb8 or provider['got_file_offset'] != 0x7cdb8):
        return False
    got = provider['got_mapping']
    if (type(got) is not dict or set(got) != {'start', 'end', 'file_offset', 'address'}
            or any(type(value) is not int or value < 0 for value in got.values())
            or not (0 < got['start'] <= got['address'] and got['address'] + 8 <= got['end'])
            or got['address'] != provider['got_address']
            or got['address'] != got['start'] + provider['got_file_offset'] - got['file_offset']):
        return False
    for key, delta in (('entry_mapping', 0), ('before_mapping', 15), ('after_mapping', 19)):
        mapping = provider.get(key)
        offset = provider['profile']['offset'] + delta
        if (type(mapping) is not dict or set(mapping) != {'start', 'end', 'file_offset', 'instruction_address'}
                or any(type(value) is not int or value < 0 for value in mapping.values())
                or not 0 < mapping['start'] <= mapping['instruction_address'] < mapping['end']
                or not mapping['file_offset'] <= offset < mapping['file_offset'] + mapping['end'] - mapping['start']
                or mapping['instruction_address'] != mapping['start'] + offset - mapping['file_offset']
                or any(mapping[field] != provider['entry_mapping'][field] for field in ('start', 'end', 'file_offset'))):
            return False
    mango = proof.get('upper_executable_mapping', {})
    if (provider['resolved_target'] != provider['entry_mapping']['instruction_address']
            or provider['got_address'] != mango.get('start', 0) - mango.get('file_offset', 0) + provider['got_virtual_address']
            or not forward_readbacks_valid(proof.get('kernel_event_readbacks'), proof.get('kernel_pid'), forward_callers(proof))):
        return False
    outer_before, outer_after = proof.get('matched_events'), proof.get('matched_upper_events')
    before, after = proof.get('matched_store_before_events'), proof.get('matched_store_after_events')
    if (any(type(events) is not list for events in (outer_before, outer_after, before, after))
            or not 0 < len(before) <= 64 or len({len(events) for events in (outer_before, outer_after, before, after)}) != 1):
        return False
    for old_before, old_after, first, second in zip(outer_before, outer_after, before, after):
        if any(type(event) is not dict for event in (old_before, old_after, first, second)):
            return False
        branch = re.fullmatch('map_before_(tail|head|scroller)_(xdg|x11)', old_before.get('event', ''))
        if not branch:
            return False
        for phase, edge, event in (('before', 'lower', first), ('after', 'upper', second)):
            text = event.get('kernel_timestamp_text')
            token = re.fullmatch(r'([0-9]{1,20})\.([0-9]{1,9})', text) if type(text) is str else None
            if not token:
                return False
            resolution = 10 ** (9 - len(token[2]))
            literal = int(token[1])*1_000_000_000 + int(token[2].ljust(9, '0'))
            if (resolution > 1000 or event.get('event') != 'map_store_' + phase + '_' + branch[2]
                    or any(type(event.get(key)) is not int for key in ('kernel_pid', 'instruction_address', 'client_type',
                        'client_address', 'handle_address', 'handle_owner_address', 'position_address', 'link_address', 'caller_address',
                        'kernel_text_monotonic_ns', 'timestamp_resolution_ns', 'timestamp_rounding_allowance_ns', edge + '_monotonic_ns'))
                    or event['kernel_text_monotonic_ns'] != literal or event['timestamp_resolution_ns'] != resolution
                    or event['timestamp_rounding_allowance_ns'] != resolution
                    or event[edge + '_monotonic_ns'] != literal + (resolution if edge == 'upper' else -resolution)
                    or event['instruction_address'] != provider[phase + '_mapping']['instruction_address']
                    or event['caller_address'] != proof['lower_executable_mappings'][branch[1]]['instruction_address'] + 5
                    or event['link_address'] != old_before['client_address'] + 280
                    or not 0 < event['position_address'] < 2**64
                    or (branch[1] == 'head' and event['position_address'] != mango['start'] - mango['file_offset'] + 0x7f348)
                    or any(event.get(key) != old_before.get(key) for key in ('kernel_pid', 'foreign_toplevel_id',
                        'client_type', 'original_app_id', 'app_id', 'client_address', 'handle_address', 'handle_owner_address'))):
                return False
        if (first['position_address'] != second['position_address']
                or not old_before['kernel_text_monotonic_ns'] <= first['kernel_text_monotonic_ns'] <= second['kernel_text_monotonic_ns'] <= old_after['kernel_text_monotonic_ns']):
            return False
    expected_lower = max(proof['ipc_lower_monotonic_ns'], min(event['lower_monotonic_ns'] for event in before))
    expected_upper = min(proof['ipc_upper_monotonic_ns'], min(event['upper_monotonic_ns'] for event in after))
    return (all(type(value) is int for value in (started, lower, upper))
            and started <= lower <= upper <= proof['ipc_upper_monotonic_ns']
            and lower == expected_lower and upper == expected_upper)


class LowerBoundProbe(OuterBoundProbe):
    """Add an audited store bracket; inherit every original outer/security/cleanup gate."""
    def __init__(self, prefix):
        super().__init__(prefix)
        self.store_events = {'before': {}, 'after': {}}

    def __enter__(self):
        super().__enter__()  # Original setup handles its own complete failure unwind.
        try:
            self._check_owner()
            (self.instance / 'tracing_on').write_text('0')
            provider = forward_provider(Path('/proc') / str(self.pid), self.executable, self.proof['upper_mapping_profile'])
            self.proof['forward_provider'] = provider
            commands = forward_probe_commands(self.group, self.proof['upper_mapping_profile'], provider)
            readbacks = dict(self.proof['kernel_event_readbacks'])
            for name, command in commands.items():
                with deferred_termination():
                    self.requested_events.add(name)
                    write_uprobe_command(self.root, command)
                event = self.instance / 'events' / self.group / name
                kind = '0' if name.endswith('_xdg') else '2'
                expression = 'common_pid == ' + str(self.pid) + ' && client_type == ' + kind
                expression += ' && (' + ' || '.join('caller == ' + str(value) for value in forward_callers(self.proof)) + ')'
                (event / 'filter').write_text(expression)
                readbacks[name] = self._readback(event)
                (event / 'enable').write_text('1')
            if not forward_readbacks_valid(readbacks, self.pid, forward_callers(self.proof)):
                raise StoreProofError('Forward-store registered kernel schema differs')
            self.proof['kernel_event_readbacks'] = readbacks
            self._check_owner()
            (self.instance / 'tracing_on').write_text('1')
            loss_counts(self.instance)
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def _check_readbacks(self):
        actual = {name: self._readback(self.instance / 'events' / self.group / name)
                  for name in self.requested_events}
        if (actual != self.proof['kernel_event_readbacks']
                or not forward_readbacks_valid(actual, self.pid, forward_callers(self.proof))):
            raise StoreProofError('Forward-store registered kernel schema changed')

    def bound(self, windows, started_ns, ipc_lower_ns, ipc_upper_ns, pattern, timeout=2):
        deadline = time.monotonic() + timeout
        outer = super().bound(windows, started_ns, ipc_lower_ns, ipc_upper_ns, pattern, timeout)
        return forward_bound(self, outer, windows, started_ns, ipc_lower_ns, ipc_upper_ns, max(0, deadline - time.monotonic()))

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
                    raise StoreProofError('Unbounded causal kernel line')
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    if not line or line.startswith(b'#'):
                        continue
                    event = forward_trace_receipt(line.decode('ascii'), self.pid)
                    key = event['foreign_toplevel_id']
                    with self.condition:
                        target = (self.store_events['before' if event['event'].startswith('map_store_before_') else 'after'] if event['event'].startswith('map_store_') else self.events if event['event'] == 'map_create' else
                                  self.lower_events if event['event'].startswith('map_before_') else self.upper_events)
                        if key in target or len(self.events)+len(self.lower_events)+len(self.upper_events)+sum(map(len, self.store_events.values())) >= MAX_EVENTS:
                            raise StoreProofError('Duplicate or unbounded causal kernel events')
                        target[key] = event
                        self.condition.notify_all()
        except BaseException as error:
            with self.condition:
                self.error = str(error)
                self.condition.notify_all()
