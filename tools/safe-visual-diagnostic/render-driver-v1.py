#!/usr/bin/env python3
"""Separately labelled observations only after all original 34 Safe captures."""
import base64
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import time
import struct
import zlib

COMMAND = "sudo sh -c 'exec >/dev/ttyS0 2>&1; exec python3 /run/arctic-safe/guest-render-collector-v1.py'"
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
CAPTURES = ['render-00-original-complete.png', 'render-01-before-framebuffer.png', 'render-02-after-framebuffer.png',
            'render-10-foot-01s.png', 'render-10-foot-05s.png', 'render-10-foot-60s.png',
            'render-20-before-grim.png', 'render-21-after-grim.png', 'render-99-final.png']


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load_original_validator():
    path = Path(__file__).parent / 'safe-runner-v1.py'
    spec = importlib.util.spec_from_file_location('render_original_validator', path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def records(serial, name):
    prefix = 'ARCTIC-RENDER-' + name + ' '
    return [json.loads(line[len(prefix):]) for line in serial.splitlines() if line.startswith(prefix)]


def validate_framebuffer_metadata(meta, image):
    path = Path(__file__).parent / 'guest-render-collector-v1.py'
    spec = importlib.util.spec_from_file_location('render_framebuffer_metadata', path)
    G = importlib.util.module_from_spec(spec); spec.loader.exec_module(G)
    var, fix = G.Variable(), G.Fixed()
    for target, fields in [(var, ('xres', 'yres', 'xres_virtual', 'yres_virtual', 'xoffset', 'yoffset', 'bits_per_pixel', 'grayscale', 'nonstd', 'rotate')),
                           (fix, ('smem_len', 'type', 'visual', 'line_length'))]:
        for key in fields:
            require(type(meta.get(key)) is int and 0 <= meta[key] < 2 ** 32, 'Exported framebuffer metadata type/range differs')
            setattr(target, key, meta[key])
    for channel in ('red', 'green', 'blue', 'transp'):
        for key in ('offset', 'length', 'msb_right'):
            value = meta['channels'][channel][key]
            require(type(value) is int and 0 <= value < 2 ** 32, 'Exported channel type/range differs')
            setattr(getattr(var, channel), key, value)
    G.metadata(var, fix)
    require(len(image) >= 33 and image[:8] == b'\x89PNG\r\n\x1a\n' and image[8:16] == b'\x00\x00\x00\x0dIHDR'
            and struct.unpack('>II', image[16:24]) == (meta['xres'], meta['yres']), 'Framebuffer PNG dimensions differ from getters')


def run(vm, out, clock=time.monotonic, sleep=time.sleep):
    out = Path(out)
    # This guard is before any input, QMP capture or new evidence file.
    H = load_original_validator()
    qualified = H.validate_events(out / 'safe-events.log')
    require(len(qualified['capture_names']) == 34 and all((out / name).is_file() for name in qualified['capture_names']), 'Original 34 images are incomplete')
    original = (out / 'safe-events.log').read_bytes()
    original_events = [json.loads(line) for line in original.splitlines()]
    require(original_events[-1]['event'] == 'diagnostic-complete', 'New arm requires original diagnostic-complete last')
    original_end = original_events[-1]['monotonic_seconds']
    log = out / 'render-events.log'
    require(not log.exists(), 'Render evidence must be unused')
    origin = clock(); require(origin >= original_end, 'New arm clock precedes original completion')

    def record(event, **values):
        # Arm begin and its elapsed origin share the actual one clock sample.
        now = origin if event == 'arm-begin' else clock()
        item = dict(event=event, monotonic_seconds=now, arm_elapsed_seconds=now-origin, **values)
        with log.open('a') as stream:
            stream.write(json.dumps(item, sort_keys=True) + '\n')
        return item

    def live():
        require(clock() - origin <= 180, 'Added render arm exceeded 180 seconds')
        require(vm.alive(), 'Owned VM exited during render arm')

    def serial():
        path = out / 'serial.log'
        require(path.is_file() and path.stat().st_size <= 96 * 1024 * 1024, 'Serial missing/over bounded stream')
        return path.read_text(errors='replace')

    def marker(name, index=0, count=1, timeout=30):
        end = clock() + timeout
        while clock() < end:
            live(); values = records(serial(), name)
            require(len(values) <= count, 'Duplicate render guest marker: ' + name)
            if len(values) > index:
                value = values[index]
                record('guest-marker', marker=name, index=index, value=value)
                return value
            sleep(.1)
        raise RuntimeError('Render guest marker timeout: ' + name)

    def capture(name):
        live(); path = vm.shot(name)
        require(path and Path(path).is_file(), 'Render QMP screenshot failed: ' + name)
        record('capture', name=name + '.png')

    record('arm-begin', original_complete_monotonic_seconds=original_end, original_events_sha256=hashlib.sha256(original).hexdigest(), release_acceptance=False, safe_visual_gate='open')
    try:
        capture('render-00-original-complete')
        record('collector-command', command=COMMAND, qualification='New displayed command is a labelled post-original stimulus')
        vm.type_text(COMMAND, gap=.2); vm.keys('ret')
        begin = marker('BEGIN')
        require(begin.get('release_acceptance') is False, 'Render collector cannot assert acceptance')
        ready = marker('FB-READY')
        require(ready.get('wait_seconds') == 10 and not records(serial(), 'FB-DONE'), 'Framebuffer read began before bracket')
        capture('render-01-before-framebuffer')
        require(not records(serial(), 'FB-DONE'), 'Framebuffer overlapped pre-bracket capture')
        marker('FB-DONE')
        require(not records(serial(), 'FOOT-START'), 'Owned client overlapped baseline post-bracket')
        capture('render-02-after-framebuffer')
        require(not records(serial(), 'FOOT-START'), 'Owned client overlapped baseline post-bracket')
        marker('FOOT-START')
        for index, seconds in enumerate((1, 5, 60)):
            value = marker('FOOT-FB', index=index, count=3, timeout=70)
            elapsed = value.get('seconds_after_owned_launch')
            require(value.get('label') == 'foot-%02ds' % seconds and type(elapsed) in (int, float) and math.isfinite(elapsed)
                    and elapsed >= seconds, 'Owned Foot sample absent/early/nonfinite')
            capture('render-10-foot-%02ds' % seconds)
        ready = marker('GRIM-READY')
        require(ready.get('wait_seconds') == 10 and not records(serial(), 'GRIM-BEGIN'), 'New Grim began before QMP pre-capture')
        capture('render-20-before-grim')
        require(not records(serial(), 'GRIM-BEGIN'), 'New Grim overlapped QMP pre-capture')
        marker('GRIM-BEGIN'); marker('GRIM-DONE'); capture('render-21-after-grim')
        end = marker('END', timeout=60)
        require(end.get('status') == 'collected-inconclusive' and end.get('error') is None and end.get('release_acceptance') is False, 'Added collector/security/cleanup failed')
        capture('render-99-final')
        require((out / 'safe-events.log').read_bytes() == original, 'Original event evidence was altered')
        record('arm-complete', release_acceptance=False, safe_visual_gate='open', result='diagnostic-only; framebuffer may be unavailable/active scanout unproven')
    except BaseException as exc:
        record('arm-failure', error=type(exc).__name__ + ': ' + str(exc))
        if vm.alive():
            try:
                capture('render-98-failure')
            except BaseException as capture_error:
                record('failure-capture-error', error=type(capture_error).__name__ + ': ' + str(capture_error))
        raise


def validate_events(path, original):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    require(rows and all(type(v.get('monotonic_seconds')) in (int, float) and math.isfinite(v['monotonic_seconds']) for v in rows), 'Missing/nonfinite render clocks')
    require(all(a['monotonic_seconds'] <= b['monotonic_seconds'] for a, b in zip(rows, rows[1:])), 'Render clocks reversed')
    require(rows[0]['event'] == 'arm-begin' and rows[-1]['event'] == 'arm-complete' and sum(v['event'] == 'arm-begin' for v in rows) == sum(v['event'] == 'arm-complete' for v in rows) == 1, 'Render arm begin/end differs')
    origin = rows[0]['monotonic_seconds']
    require(rows[-1]['monotonic_seconds'] - origin <= 180 and all(type(v.get('arm_elapsed_seconds')) in (int, float) and math.isfinite(v['arm_elapsed_seconds']) and abs(v['arm_elapsed_seconds'] - (v['monotonic_seconds'] - origin)) < 1e-6 for v in rows), 'Render bound/elapsed clocks differ')
    old = Path(original).read_bytes(); oldrows = [json.loads(line) for line in old.splitlines()]
    require(oldrows[-1]['event'] == 'diagnostic-complete' and rows[0]['original_complete_monotonic_seconds'] == oldrows[-1]['monotonic_seconds'] <= origin and rows[0]['original_events_sha256'] == hashlib.sha256(old).hexdigest(), 'New arm precedes/changes original phases')
    captures = [v['name'] for v in rows if v['event'] == 'capture']
    require(captures == CAPTURES, 'Added ordered captures differ')
    markers = [v for v in rows if v['event'] == 'guest-marker']
    expected = [('BEGIN', 0), ('FB-READY', 0), ('FB-DONE', 0), ('FOOT-START', 0), ('FOOT-FB', 0), ('FOOT-FB', 1), ('FOOT-FB', 2), ('GRIM-READY', 0), ('GRIM-BEGIN', 0), ('GRIM-DONE', 0), ('END', 0)]
    require([(v['marker'], v['index']) for v in markers] == expected, 'Added markers missing/duplicate/reordered')
    require(sum(v['event'] == 'collector-command' for v in rows) == 1 and next(v for v in rows if v['event'] == 'collector-command')['command'] == COMMAND, 'Unexpected added command')
    def token(row):
        if row['event'] == 'capture': return 'capture:' + row['name']
        if row['event'] == 'guest-marker': return 'marker:' + row['marker'] + ':' + str(row['index'])
        return row['event']
    order = ['arm-begin', 'capture:' + CAPTURES[0], 'collector-command', 'marker:BEGIN:0', 'marker:FB-READY:0',
             'capture:' + CAPTURES[1], 'marker:FB-DONE:0', 'capture:' + CAPTURES[2], 'marker:FOOT-START:0']
    for index in range(3): order += ['marker:FOOT-FB:' + str(index), 'capture:' + CAPTURES[3 + index]]
    order += ['marker:GRIM-READY:0', 'capture:' + CAPTURES[6], 'marker:GRIM-BEGIN:0', 'marker:GRIM-DONE:0',
              'capture:' + CAPTURES[7], 'marker:END:0', 'capture:' + CAPTURES[8], 'arm-complete']
    require([token(v) for v in rows] == order, 'Framebuffer/client/Grim marker-to-capture order differs')
    require(rows[-1].get('release_acceptance') is False and rows[-1].get('safe_visual_gate') == 'open', 'Diagnostic cannot close visual gate')
    return dict(capture_names=captures, result='diagnostic-only', safe_visual_gate='open')


def extract(serial, target, collector_sha):
    """Bounded separate protocol; original extract is called unchanged first."""
    target = Path(target); require(not target.exists(), 'Render target must be unused'); target.mkdir()
    names = ('BEGIN', 'REPORT', 'MANIFEST', 'END')
    values = {n: records(serial, n) for n in names}
    require(all(len(v) == 1 for v in values.values()), 'Missing/duplicate render protocol record')
    protocol = [(line.split(' ', 1)[0][len('ARCTIC-RENDER-'):], json.loads(line.split(' ', 1)[1])) for line in serial.splitlines() if line.startswith('ARCTIC-RENDER-')]
    core = [n for n, v in protocol if n in names or n == 'CHUNK']
    require(core[:3] == ['BEGIN', 'REPORT', 'MANIFEST'] and core[-1] == 'END' and all(n == 'CHUNK' for n in core[3:-1]), 'Render transport order differs')
    require(values['BEGIN'][0] == dict(collector_sha256=collector_sha, release_acceptance=False), 'Render collector identity differs')
    report, manifest, end = values['REPORT'][0], values['MANIFEST'][0], values['END'][0]
    require(manifest.get('schema') == 'arctic-render-files-v1' and manifest.get('encoding') == 'zlib+base64' and isinstance(manifest.get('files'), list) and len(manifest['files']) <= 128, 'Render transport schema/bounds differ')
    chunks = records(serial, 'CHUNK'); known = set(); total = 0; copied = {}
    for item in manifest['files']:
        name = item['path']
        require(isinstance(name, str) and name and Path(name).name == name and name not in ('.', '..', 'serial-report.json') and Path(name).suffix in ('.json', '.log', '.png', '.txt') and name not in known, 'Unsafe/duplicate render evidence name')
        known.add(name)
        require(type(item['bytes']) is int and 0 <= item['bytes'] <= MAX_FILE and type(item['compressed_bytes']) is int and 0 < item['compressed_bytes'] <= MAX_FILE + 65536 and type(item['chunks']) is int and 1 <= item['chunks'] <= 180 and isinstance(item['sha256'], str) and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'Render payload bounds differ')
        parts = [v for v in chunks if v.get('path') == name]
        require(len(parts) == item['chunks'] and [v['index'] for v in parts] == list(range(item['chunks'])) and all(type(v['index']) is int for v in parts), 'Render chunks missing/duplicate/reordered')
        packed = b''.join(base64.b64decode(v['data'], validate=True) for v in parts)
        require(len(packed) == item['compressed_bytes'], 'Render compressed bytes differ')
        decoder = zlib.decompressobj(); data = decoder.decompress(packed, MAX_FILE + 1)
        require(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data and len(data) == item['bytes'] and hashlib.sha256(data).hexdigest() == item['sha256'], 'Render payload checksum/length differs')
        total += len(data); require(total <= MAX_TOTAL, 'Render aggregate exceeds bound')
        (target / name).write_bytes(data); copied[name] = dict(bytes=len(data), sha256=item['sha256'])
    require(all(c.get('path') in known for c in chunks) and type(manifest.get('bytes')) is int and total == manifest['bytes'], 'Render unexpected chunks/total')
    require('report.json' in copied and json.loads((target / 'report.json').read_text()) == report, 'Render report mismatch')
    require(report.get('schema') == 'arctic-render-telemetry-v1' and report.get('collector_sha256') == collector_sha and report.get('status') == 'diagnostic-collected-inconclusive' and report.get('release_acceptance') is False and report.get('safe_visual_gate') == 'open' and report.get('effective_render_loop') == report.get('compositor_gl_renderer') == 'unobserved', 'Render meaning/identity differs')
    require(end == dict(status='collected-inconclusive', error=None, release_acceptance=False), 'Render security/cleanup failed')
    require(type(report.get('desktop_uid')) is int and report['desktop_uid'] > 0 and 'nomodeset' in report['cmdline'].split() and 'rd.live.image' in report['cmdline'].split(), 'Render guest/user identity differs')
    require(isinstance(report.get('boot_id'), str) and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', report['boot_id']), 'Render boot-id malformed')
    for name, label in [('security_before', 'render-before'), ('security_before_grim', 'render-before-grim'), ('security_after', 'render-after')]:
        security = report[name]; audit = dict(line.split(None, 1) for line in security['audit_status'].splitlines() if len(line.split(None, 1)) == 2)
        require(security['selinux'] == 'Enforcing' and security['avc_records'] == [] and audit.get('enabled') in ('1', '2') and audit.get('lost') == '0', 'Render SELinux/audit/AVC failed')
        journal = 'system-journal-' + label + '.log'
        require(journal in copied and security['journal_retained_bytes'] == copied[journal]['bytes'] and security['journal_retained_sha256'] == copied[journal]['sha256'] and type(security['current_boot_journal_records']) is int and security['current_boot_journal_records'] > 0, 'Render retained journal differs')
        journal_rows = [json.loads(line) for line in (target / journal).read_bytes().splitlines() if line]
        require(journal_rows and all(isinstance(v, dict) and v.get('_BOOT_ID') == report['boot_id'].replace('-', '') and 'MESSAGE' in v for v in journal_rows), 'Render retained journal boot/type differs')
        require(not any(v.get('_TRANSPORT') in ('kernel', 'audit') and re.search(r'\bavc:\s*denied\b|\btype=(?:USER_)?AVC\b', str(v['MESSAGE']), re.I) for v in journal_rows), 'Render raw retained journal contains trusted AVC')
    require(report.get('cleanup', {}).get('status') == 'owned-launch-exited', 'Owned Foot cleanup is incomplete')
    owned = report['owned_launch']
    foot, wrapper = owned['foot'], owned['wrapper']
    require(type(foot.get('pid')) is int and foot['pid'] > 0 and type(wrapper.get('pid')) is int and wrapper['pid'] > 0
            and type(foot.get('uid')) is int and foot['uid'] == report['desktop_uid']
            and type(wrapper.get('uid')) is int and wrapper['uid'] == 0
            and foot.get('executable') == '/usr/bin/foot' and wrapper.get('executable') in ('/usr/bin/runuser', '/usr/sbin/runuser')
            and type(foot.get('start_ticks')) is int and foot['start_ticks'] > 0
            and type(wrapper.get('start_ticks')) is int and wrapper['start_ticks'] > 0,
            'Owned diagnostic process identity differs')
    require(owned['argv'][-5] == '/usr/bin/foot' and re.fullmatch(r'--app-id=arctic-safe-render-arctic-render-evidence-[A-Za-z0-9_]+', owned['argv'][-4])
            and owned['argv'][-3:-1] == ['/usr/bin/python3', '/run/arctic-safe/fixed-rows-v1.py']
            and owned['argv'][-1] == owned['argv'][-4][len('--app-id='):]
            and foot['cmdline'] == owned['argv'][-5:], 'Owned launch includes unexpected client/config command')
    child = owned['rows']
    require(type(child.get('pid')) is int and child['pid'] > 0 and type(child.get('uid')) is int and child['uid'] == report['desktop_uid']
            and type(child.get('start_ticks')) is int and child['start_ticks'] > 0 and child['cmdline'] == owned['argv'][-3:]
            and re.fullmatch(r'/usr/bin/python3(?:\.[0-9]+)?', child['executable']), 'Owned fixed-row child identity differs')
    require(len({wrapper['pid'], foot['pid'], child['pid']}) == 3, 'Owned process identities overlap')
    require(type(owned.get('foot_process_group')) is int and owned['foot_process_group'] > 0, 'Owned Foot process group type differs')
    require(owned.get('fixed_rows_sha256') == hashlib.sha256((Path(__file__).parent / 'fixed-rows-v1.py').read_bytes()).hexdigest(), 'Actual fixed-row source differs')
    frames = report['framebuffers']
    require([v['label'] for v in frames] == ['baseline', 'foot-01s', 'foot-05s', 'foot-60s', 'after-grim'] and all(v.get('active_scanout') == 'unproven' for v in frames), 'Framebuffer sequence/meaning differs')
    for v in frames:
        require(type(v.get('guest_begin_ns')) is int and type(v.get('guest_end_ns')) is int and 0 <= v['guest_begin_ns'] <= v['guest_end_ns'], 'Framebuffer interval differs')
        if v['label'].startswith('foot-'):
            seconds = int(v['label'][5:7]); elapsed = v.get('seconds_after_owned_launch')
            require(type(elapsed) in (int, float) and math.isfinite(elapsed) and elapsed >= seconds, 'Framebuffer Foot sample absent/early/nonfinite')
        if v['status'] == 'read-only-snapshot':
            require(v.get('png') in copied and copied[v['png']]['sha256'] == v['png_sha256'] and copied[v['png']]['bytes'] == v['png_bytes'] and (target / v['png']).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') and isinstance(v.get('raw_sha256'), str) and re.fullmatch('[0-9a-f]{64}', v['raw_sha256']) and type(v.get('raw_bytes')) is int and 0 < v['raw_bytes'] <= 32 * 1024 * 1024, 'Framebuffer snapshot/hash differs')
            validate_framebuffer_metadata(v['metadata'], (target / v['png']).read_bytes())
            require(v['raw_bytes'] == v['metadata']['line_length'] * v['metadata']['yres_virtual'], 'Framebuffer raw byte allocation differs')
        else:
            require(v['status'] == 'unavailable' and isinstance(v.get('error'), str) and v['error'] and 'png' not in v and 'png_sha256' not in v, 'Unavailable framebuffer invented pixels')
    require(report['unavailable'] == [v['label'] for v in frames if v['status'] == 'unavailable'], 'Framebuffer missing evidence was concealed')
    require('render-grim.png' in copied and report['grim']['sha256'] == copied['render-grim.png']['sha256'], 'Added Grim pixels/hash absent')
    return dict(files=copied, report=report, status='diagnostic_only_inconclusive', release_acceptance=False)
