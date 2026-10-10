"""Test-only host controls for the exact live installer's real virtual outputs."""
from contextlib import contextmanager
import hashlib
import signal
import json
from pathlib import Path
import re
import time
import sys
from types import CodeType, FunctionType

_COLLECTION_GUARD_TOKEN = object()

REQUEST_PREFIX = 'ARCTIC-INSTALLER-REQUEST '
EXPECTED = [('vt-away', cycle) for cycle in range(3)] + [
    (kind, cycle) for cycle in range(3) for kind in ('output-disconnect', 'output-restore')]
ACTIVE_EXPECTED = [('vt-away', 0), ('output-disconnect', 0), ('output-restore', 0)]


def require(value, message):
    if not value:
        error = RuntimeError(message)
        try:
            _mint_collection_guard(error)
        except Exception:
            pass  # Optional source identity cannot replace the original failure.
        raise error


def _mint_collection_guard(error):
    frame = sys._getframe(2)
    try:
        if frame.f_globals is globals() and any(frame.f_code is code for code in _COLLECTION_GUARD_OWNERS):
            code = _COLLECTION_GUARD_SITES.get((frame.f_code.co_qualname,
                        frame.f_lineno - frame.f_code.co_firstlineno))
            if code is not None:
                error._arctic_installer_collection_guard = (_COLLECTION_GUARD_TOKEN, code)
    finally:
        del frame


@contextmanager
def cleanup_signals():
    """Finish bounded owned cleanup and let the caller record cancellation."""
    pending, previous = [], {}
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.getsignal(number)
            signal.signal(number, lambda number, frame: pending.append(number))
        yield pending
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


def persist_cleanup_state(path, state, errors, pending):
    """Called under cleanup_signals; cancellation during IO persists failure."""
    reason = 'cancelled during bounded owned cleanup'
    state['errors'] = errors
    if pending and reason not in errors:
        errors.append(reason)
    if errors:
        state['status'] = 'failed'
    Path(path).write_text(json.dumps(state, sort_keys=True, allow_nan=False) + '\n')
    if pending and reason not in errors:
        errors.append(reason)
        state['status'] = 'failed'
        Path(path).write_text(json.dumps(state, sort_keys=True, allow_nan=False) + '\n')


def strict_json(text):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'duplicate installer request field')
            result[key] = value
        return result
    def constant(value):
        raise RuntimeError('nonfinite installer request value')
    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def head_for_output(name):
    # Linux virtgpu_display.c creates the only virtio GPU's Virtual connectors
    # in scanout index order. The guest also verifies the real sysfs card,
    # virtio_gpu driver, PCI device and exactly these connector names.
    require(name in ('Virtual-1', 'Virtual-2'), 'unsupported actual virtio connector mapping')
    return int(name.rsplit('-', 1)[1]) - 1


class InstallerController:
    def __init__(self, vm, display, context, out):
        self.vm, self.display, self.context = vm, display, context
        self.out = Path(out)
        self.position = 0
        self.boot_id = None
        self.disconnected = set()
        self.receipts = []
        self.failed = False
        self.active = context.get('schema') == 'arctic-installer-active-context-v1'
        self.expected = ACTIVE_EXPECTED if self.active else EXPECTED
        proof = display.proof
        require(proof['gpu_id'] == 'arctic_taskbar_gpu' and proof['guest_monitor_verification_required'] is True,
                'installer controller requires the reviewed owned GPU fixture')
        self.heads = {row['head']: dict(row) for row in proof['heads']}
        require(set(self.heads) == {0, 1}, 'installer controller requires two exact heads')

    def set_heads(self, enabled):
        require(type(enabled) is set and enabled <= {0, 1}, 'invalid enabled head set')
        self.display.deadline = time.monotonic() + 40
        status = self.display._query(self.vm, 'query-status')
        require(status.get('running') is True, 'installer display changes require the actual running VM')
        owner = self.display._owner(self.vm)
        gpu = self.display._gpu(self.vm)
        require(all(row['device_address'] == gpu for row in self.heads.values()), 'owned fixture GPU address changed')
        applied, errors = [], []
        # A failed call can still change one physical head. Mark the owned
        # outputs uncertain before mutating so cleanup always retries both.
        self.disconnected = {0, 1}
        # Attempt both heads even if the first call fails. Failure never creates
        # a successful proof and final cleanup retries restoration of both.
        for index in (0, 1):
            row = self.heads[index]
            width, height = (1280, 720) if index in enabled else (0, 0)
            try:
                require(self.display._owner(self.vm) == owner, 'owned QEMU bus owner changed')
                result = self.display._call('/org/qemu/Display1/Console_' + str(row['console_id']),
                    'org.qemu.Display1.Console.SetUIInfo', 'uint16 340', 'uint16 190',
                    'int32 ' + str(index * 1280), 'int32 0', 'uint32 ' + str(width),
                    'uint32 ' + str(height), destination=owner)
                require(result.strip() == '()', 'unexpected output UIInfo completion')
                applied.append(dict(head=index, width=width, height=height, xoff=index * 1280, yoff=0))
            except BaseException as error:
                errors.append(error)
        require(self.display._owner(self.vm) == owner, 'owned QEMU display owner changed after transition')
        if errors:
            self.failed = True
            raise errors[0]
        self.disconnected = {0, 1} - enabled
        return dict(schema='arctic-installer-host-output-v1', qemu_pid=self.vm.proc.pid,
                    qemu_uid=0, gpu_id='arctic_taskbar_gpu', bus_owner=owner,
                    applied=applied, enabled_heads=sorted(enabled),
                    observation='supported QEMU UIInfo; actual guest output inventory required')

    def capture(self, name):
        path = self.out / (name + '.png')
        require(not path.exists(), 'installer host capture name reused')
        result = self.display._query(self.vm, 'screendump', {'filename': str(path), 'format': 'png',
                                      'device': 'arctic_taskbar_gpu', 'head': 0})
        require(type(result) is dict and path.is_file() and not path.is_symlink()
                and 8 <= path.stat().st_size <= 4 * 1024 * 1024,
                'installer host capture failed or exceeds bound')
        content = path.read_bytes()
        require(content.startswith(b'\x89PNG\r\n\x1a\n'), 'installer host capture is not PNG')
        from PIL import Image
        with Image.open(path) as image:
            require(image.size == (1280, 720), 'away-VT capture physical size differs')
            histogram = image.convert('L').histogram()
            require(sum(histogram[:17]) / (image.width * image.height) > .90 and sum(histogram[160:]) >= 30,
                    'away-VT capture does not show the real console pixel pattern')
        return dict(path=path.name, bytes=len(content), sha256=hashlib.sha256(content).hexdigest(),
                    console_pixel_guard_passed=True, manual_console_review_required=True)

    def poll(self, serial):
        content = Path(serial).read_bytes()
        require(len(content) <= 8 * 1024 * 1024, 'installer serial request stream exceeds bound')
        complete, _, pending = content.rpartition(b'\n')
        require(len(pending) <= 16384, 'installer serial pending line exceeds bound')
        lines = complete.decode('utf-8').splitlines()
        requests = [line[len(REQUEST_PREFIX):] for line in lines if line.startswith(REQUEST_PREFIX)]
        require(len(requests) <= len(self.expected), 'duplicate or additional installer host request')
        active = False
        while self.position < len(requests):
            text = requests[self.position]
            require(len(text) <= 16384, 'installer request exceeds bound')
            value = strict_json(text)
            require(type(value) is dict and value.get('schema') == 'arctic-installer-request-v1'
                    and value.get('binding_id') == self.context['binding_id'] and type(value.get('cycle')) is int
                    and (value.get('kind'), value['cycle']) == self.expected[self.position],
                    'installer request identity, order or cycle differs')
            boot = value.get('boot_id')
            require(type(boot) is str and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', boot),
                    'installer request boot identity missing')
            require(self.boot_id is None or self.boot_id == boot, 'installer requests span boots')
            self.boot_id = boot
            common = {'schema', 'kind', 'binding_id', 'boot_id', 'cycle'}
            extra = ({'away', 'original_vt', 'engine_sha256'} if value['kind'] == 'vt-away' else
                     {'mode', 'hosting_output', 'hosting_head', 'enabled_outputs', 'engine_sha256'} |
                     ({'enabled_output_count', 'outputs_sha256', 'outputs'} if value['kind'] == 'output-restore' else set()))
            if self.active:
                extra |= {'elapsed_ns'}
                require(type(value.get('elapsed_ns')) is int and value['elapsed_ns'] > 0,
                        'active request lacks an observation timestamp')
            require(set(value) == common | extra and re.fullmatch('[0-9a-f]{64}', value['engine_sha256']),
                    'installer request field inventory differs')
            receipt = dict(request=value, request_sha256=hashlib.sha256(text.encode()).hexdigest())
            if self.active:
                receipt['disk_io'] = self.active_write_proof()
            if value['kind'] == 'vt-away':
                away = value.get('away', {})
                require(type(away) is dict and away.get('foreground') == 'tty6' and away.get('active') is False
                        and type(value.get('original_vt')) is int and value['original_vt'] != 6,
                        'installer did not report an actual inactive desktop and tty6')
                self.display.deadline = time.monotonic() + 15
                receipt['capture'] = self.capture('installer-vt-away-' + str(value['cycle']))
            elif value['kind'] == 'output-disconnect':
                require(not self.disconnected, 'installer outputs already disconnected')
                mode = 'all' if value['cycle'] == 1 else 'hosting-only'
                require(value.get('mode') == mode, 'installer output loss mode differs')
                hosting = head_for_output(value.get('hosting_output'))
                require(value.get('hosting_head') == hosting and value.get('enabled_outputs') == ['Virtual-1', 'Virtual-2'],
                        'installer actual hosting connector or two-output inventory differs')
                removed = {0, 1} if mode == 'all' else {hosting}
                receipt['display'] = self.set_heads({0, 1} - removed)
            else:
                require(bool(self.disconnected), 'installer reconnect did not follow disconnect')
                mode = 'all' if value['cycle'] == 1 else 'hosting-only'
                expected_count = 0 if mode == 'all' else 1
                require(value.get('mode') == mode and value.get('enabled_output_count') == expected_count
                        and type(value.get('outputs_sha256')) is str
                        and re.fullmatch('[0-9a-f]{64}', value['outputs_sha256'])
                        and type(value.get('outputs')) is list and len(value['outputs']) <= 2
                        and hashlib.sha256(json.dumps(value['outputs'], sort_keys=True).encode()).hexdigest() == value['outputs_sha256']
                        and all(output.get('name') in ('Virtual-1', 'Virtual-2') and type(output.get('enabled')) is bool for output in value['outputs'])
                        and len({output['name'] for output in value['outputs']}) == len(value['outputs'])
                        and {head_for_output(output['name']) for output in value['outputs'] if output['enabled']} == {0, 1} - self.disconnected
                        and sum(output.get('enabled') is True for output in value['outputs']) == expected_count
                        and value.get('enabled_outputs') == ['Virtual-1', 'Virtual-2']
                        and value.get('hosting_head') == head_for_output(value.get('hosting_output')),
                        'installer did not report actual disconnected output inventory')
                receipt['display'] = self.set_heads({0, 1})
            self.receipts.append(receipt)
            self.position += 1
            active = True
            (self.out / 'installer-host-transitions.json').write_text(json.dumps(
                dict(schema='arctic-installer-host-transitions-v1', context=self.context,
                     boot_id=self.boot_id, receipts=self.receipts, release_acceptance=False), sort_keys=True) + '\n')
        return active

    def finish(self):
        require(self.position == len(self.expected) and not self.disconnected and not self.failed,
                'installer host transition matrix incomplete or failed')
        return self.receipts

    def active_write_proof(self):
        """Two actual QMP counters on only the freshly acquired target node."""
        def sample():
            rows = self.display._query(self.vm, 'query-block')
            owned = [row['inserted'] for row in rows if row.get('inserted', {}).get('node-name') == 'target0']
            require(len(owned) == 1 and owned[0].get('file') == str(self.out / 'target.qcow2')
                    and owned[0].get('ro') is False, 'QMP target is not this invocation’s writable disk')
            stats = self.display._query(self.vm, 'query-blockstats', {'query-nodes': True})
            selected = [row['stats'] for row in stats if row.get('node-name') == 'target0']
            require(len(selected) == 1 and all(type(selected[0].get(k)) is int and selected[0][k] >= 0
                    for k in ('wr_bytes', 'wr_operations')), 'actual owned target counters absent')
            return dict(wr_bytes=selected[0]['wr_bytes'], wr_operations=selected[0]['wr_operations'],
                        monotonic_ns=time.monotonic_ns())
        # Btrfs can initially buffer a real copy. Wait for observed writes within
        # a fixed bound instead of treating half a second without a flush as failure.
        self.display.deadline = time.monotonic() + 22
        before = sample(); end = time.monotonic() + 20
        after = before
        while time.monotonic() < end:
            time.sleep(.5); after = sample()
            if after['wr_bytes'] > before['wr_bytes'] and after['wr_operations'] > before['wr_operations']:
                break
        require(after['wr_bytes'] > before['wr_bytes'] and after['wr_operations'] > before['wr_operations']
                and after['monotonic_ns'] > before['monotonic_ns'], 'genuine target writes did not continue during disruption')
        if self.receipts:
            require(before['wr_bytes'] >= self.receipts[-1]['disk_io']['after']['wr_bytes'], 'target write counters regressed')
        return dict(node_name='target0', before=before, after=after, write_bps=self.context['write_bps'],
                    target_file=str(self.out / 'target.qcow2'), target_serial=self.context['disk_serial'],
                    inserted_node_name='target0', inserted_readonly=False)

    def restore(self):
        if self.disconnected and self.vm.proc.poll() is None:
            return self.set_heads({0, 1})
        return None


# Closed IDs bind original require call sites, not arbitrary exception strings.
_COLLECTION_GUARD_SITES = {
    ('strict_json.<locals>.pairs', 3): 'collection-001',
    ('head_for_output', 4): 'collection-002',
    ('InstallerController.__init__', 11): 'collection-003',
    ('InstallerController.__init__', 14): 'collection-004',
    ('InstallerController.set_heads', 1): 'collection-005',
    ('InstallerController.set_heads', 4): 'collection-006',
    ('InstallerController.set_heads', 7): 'collection-007',
    ('InstallerController.set_heads', 18): 'collection-008',
    ('InstallerController.set_heads', 23): 'collection-009',
    ('InstallerController.set_heads', 27): 'collection-010',
    ('InstallerController.capture', 2): 'collection-011',
    ('InstallerController.capture', 5): 'collection-012',
    ('InstallerController.capture', 9): 'collection-013',
    ('InstallerController.capture', 12): 'collection-014',
    ('InstallerController.capture', 14): 'collection-015',
    ('InstallerController.poll', 2): 'collection-016',
    ('InstallerController.poll', 4): 'collection-017',
    ('InstallerController.poll', 7): 'collection-018',
    ('InstallerController.poll', 11): 'collection-019',
    ('InstallerController.poll', 13): 'collection-020',
    ('InstallerController.poll', 18): 'collection-021',
    ('InstallerController.poll', 20): 'collection-022',
    ('InstallerController.poll', 28): 'collection-023',
    ('InstallerController.poll', 30): 'collection-024',
    ('InstallerController.poll', 37): 'collection-025',
    ('InstallerController.poll', 43): 'collection-026',
    ('InstallerController.poll', 45): 'collection-027',
    ('InstallerController.poll', 47): 'collection-028',
    ('InstallerController.poll', 52): 'collection-029',
    ('InstallerController.poll', 55): 'collection-030',
    ('InstallerController.finish', 1): 'collection-031',
    ('InstallerController.active_write_proof.<locals>.sample', 3): 'collection-032',
    ('InstallerController.active_write_proof.<locals>.sample', 7): 'collection-033',
    ('InstallerController.active_write_proof', 22): 'collection-034',
    ('InstallerController.active_write_proof', 25): 'collection-035',
}

def _collection_owned_codes(function):
    pending, result = [function.__code__], set()
    while pending:
        code = pending.pop(); result.add(code)
        pending.extend(value for value in code.co_consts if type(value) is CodeType)
    return result

_COLLECTION_GUARD_OWNERS = set()
for _collection_function in (strict_json, head_for_output, *[value for value in vars(InstallerController).values() if type(value) is FunctionType]):
    _COLLECTION_GUARD_OWNERS.update(_collection_owned_codes(_collection_function))
del _collection_function

_COLLECTION_GUARD_PHASES = {
    'strict_json': 'request-json',
    'strict_json.<locals>.pairs': 'request-json-fields',
    'strict_json.<locals>.constant': 'request-json-constant',
    'head_for_output': 'output-head',
    'InstallerController.poll': 'request-poll',
    'InstallerController.capture': 'console-capture',
    'InstallerController.set_heads': 'output-transition',
    'InstallerController.active_write_proof': 'target-write-progress',
    'InstallerController.active_write_proof.<locals>.sample': 'target-write-sample',
}
