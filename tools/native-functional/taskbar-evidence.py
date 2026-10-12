#!/usr/bin/env python3
"""Host validation of separately framed, bounded actual-installed taskbar evidence."""
import base64
from collections import Counter
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import zlib

from PIL import Image

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('taskbar_transport_primitives', HERE / 'taskbar-runtime.py')
runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
require, strict_json, validate_context = runtime.require, runtime.strict_json, runtime.validate_context
MAX_FILE, MAX_TOTAL, MAX_FILES, CHUNK = runtime.MAX_FILE, runtime.MAX_TOTAL, runtime.MAX_FILES, runtime.CHUNK
PREFIX = 'ARCTIC-TASKBAR-'
EDGES = ('top', 'bottom', 'left', 'right')
SCALES = (1, 1.5, 2)
FOOT = (33, 131, 79)
SHA = re.compile('[0-9a-f]{64}')
UUID = re.compile('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')


def write_json(path, value):
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def exact(value, fields, message):
    require(type(value) is dict and set(value) == set(fields), message)


def relative(value):
    require(type(value) is str and 0 < len(value) <= 256 and '\\' not in value
            and re.fullmatch('[A-Za-z0-9_./-]+', value), 'unsafe taskbar evidence path')
    path = Path(value)
    require(not path.is_absolute() and all(p not in ('.', '..') for p in value.split('/'))
            and value == path.as_posix() and path.suffix in ('.png', '.json', '.log')
            and value not in {'transport-manifest.json', 'taskbar-state.json', 'serial-taskbar-report.json',
                              'serial-taskbar-provenance.json'}, 'unsafe/reserved taskbar evidence path')
    return value


def block(serial, context, transport_serial=None):
    validate_context(context)
    require(type(serial) is str and len(serial.encode()) <= 210 * 1024 * 1024, 'taskbar serial exceeds bound')
    native_lines = serial.splitlines()
    if transport_serial is not None:
        require(type(transport_serial) is str and len(transport_serial.encode()) <= 210 * 1024 * 1024,
                'taskbar virtio serial exceeds bound')
    lines = native_lines if transport_serial is None else transport_serial.splitlines()
    records = []
    native = []
    markers = []
    for index, line in enumerate(native_lines):
        if line.startswith('ARCTIC-NATIVE-PROVENANCE '):
            require(len(line) <= MAX_FILE, 'native taskbar bootstrap exceeds bound')
            native.append((index, strict_json(line.split(' ', 1)[1])))
        if transport_serial is not None and line.startswith(PREFIX):
            require(line.startswith(PREFIX+'PORT-END ') and len(line) <= 16384,
                    'taskbar actual guest placed evidence or malformed status on UART')
            markers.append((index, strict_json(line.split(' ', 1)[1])))
    for index, line in enumerate(lines):
        if line.startswith(PREFIX):
            require(' ' in line and len(line) <= MAX_FILE + 256, 'malformed taskbar serial record')
            kind, payload = line[len(PREFIX):].split(' ', 1)
            require(kind in {'BEGIN', 'PROVENANCE', 'REPORT', 'EVIDENCE-CHUNK', 'EVIDENCE-MANIFEST', 'END'},
                    'unknown taskbar serial record')
            records.append((index, kind, strict_json(payload)))
    kinds = [kind for _, kind, _ in records]
    require(len(records) >= 6 and kinds[:3] == ['BEGIN', 'PROVENANCE', 'REPORT']
            and kinds[-2:] == ['EVIDENCE-MANIFEST', 'END']
            and all(k == 'EVIDENCE-CHUNK' for k in kinds[3:-2]),
            'missing/extra/duplicate/reordered taskbar records')
    begin, proof, report, manifest, end = [records[i][2] for i in (0, 1, 2, -2, -1)]
    identity_fields = {'boot_id', 'desktop_uid', 'active_desktop_session'}
    transport_fields = {'transport'} if transport_serial is not None else set()
    exact(begin, {'schema', 'stage', 'context', 'release_acceptance'} | identity_fields | transport_fields,
          'taskbar begin schema differs')
    exact(proof, {'schema', 'stage', 'context', 'cmdline', 'virtualization', 'release_acceptance'} | identity_fields | transport_fields,
          'taskbar provenance schema differs')
    exact(end, {'token', 'status', 'error', 'evidence_export_complete', 'release_acceptance'} | identity_fields,
          'taskbar end schema differs')
    require(begin['schema'] == 'arctic-taskbar-runner-v1'
            and proof['schema'] == 'arctic-taskbar-provenance-v1'
            and begin['stage'] == proof['stage'] == 'installed'
            and begin['context'] == proof['context'] == context
            and begin['release_acceptance'] is proof['release_acceptance'] is end['release_acceptance'] is False,
            'taskbar context/exact-image identity differs')
    require(type(begin['boot_id']) is str and UUID.fullmatch(begin['boot_id'])
            and type(begin['desktop_uid']) is int and begin['desktop_uid'] > 0
            and type(begin['active_desktop_session']) is str
            and re.fullmatch('[A-Za-z0-9_-]{1,64}', begin['active_desktop_session'])
            and all(begin[k] == proof[k] == end[k] for k in identity_fields)
            and end['token'] == context['token'], 'taskbar boot/session/UID/token differs')
    require(type(proof['cmdline']) is str and len(proof['cmdline']) <= 16384
            and 'rd.live.image' not in proof['cmdline'].split()
            and proof['virtualization'] in ('qemu', 'kvm'), 'taskbar actual installed guest differs')
    require(len(native) == 1 and (transport_serial is not None or native[0][0] < records[0][0]),
            'taskbar installed native bootstrap missing/ambiguous/reversed')
    boot = native[0][1]
    require(type(boot) is dict and boot.get('stage') == 'installed'
            and boot.get('release_acceptance') is False and boot.get('native_source_sha256') == context['native_sha256']
            and all(boot.get(k) == begin[k] for k in identity_fields)
            and boot.get('cmdline') == proof['cmdline'], 'taskbar/native same-boot bootstrap identity differs')
    require(end['status'] in ('passed', 'failed') and type(end['evidence_export_complete']) is bool
            and (end['error'] is None or (type(end['error']) is str and len(end['error']) <= 4096)),
            'taskbar collector status malformed')
    if transport_serial is not None:
        require(len(markers) == 1 and native[0][0] < markers[0][0],
                'taskbar UART completion marker missing/duplicate/reversed')
        marker = markers[0][1]
        exact(marker, {'schema', 'token', 'status', 'end_sha256', 'release_acceptance'} | identity_fields,
              'taskbar UART completion schema differs')
        require(marker['schema'] == 'arctic-taskbar-port-end-v1' and marker['token'] == context['token']
                and marker['release_acceptance'] is False and marker['status'] == end['status']
                and all(marker[k] == begin[k] for k in identity_fields)
                and marker['end_sha256'] == hashlib.sha256(json.dumps(end, sort_keys=True, allow_nan=False).encode('ascii')).hexdigest(),
                'taskbar port END/UART completion identity differs')
        channel = begin['transport']
        exact(channel, ('schema', 'name', 'device', 'major', 'minor', 'uid', 'mode'),
              'taskbar port device receipt schema differs')
        require(channel == proof['transport'] and channel['schema'] == 'arctic-taskbar-virtio-port-v1'
                and channel['name'] == runtime.PORT_NAME and type(channel['device']) is str
                and re.fullmatch('/dev/vport[0-9]+p[0-9]+', channel['device'])
                and type(channel['uid']) is int and channel['uid'] == 0
                and type(channel['mode']) is int and 0 <= channel['mode'] <= 0o7777 and not channel['mode'] & 0o022
                and type(channel['major']) is int and 0 < channel['major'] <= 99999
                and type(channel['minor']) is int and 0 <= channel['minor'] <= 99999,
                'taskbar protected canonical named port identity differs')
    return begin, proof, report, [r[2] for r in records[3:-2]], manifest, end


def extract(chunks, manifest, context, target):
    exact(manifest, {'schema', 'token', 'evidence_root', 'files', 'bytes'}, 'taskbar manifest schema differs')
    require(manifest['schema'] == 'arctic-taskbar-evidence-v1' and manifest['token'] == context['token']
            and type(manifest['files']) is list and 1 <= len(manifest['files']) <= MAX_FILES
            and type(manifest['bytes']) is int and 0 <= manifest['bytes'] <= MAX_TOTAL,
            'taskbar manifest identity/bounds differ')
    root = manifest['evidence_root']
    require(type(root) is str and re.fullmatch('/tmp/arctic-native-smoke-[A-Za-z0-9_-]+', root),
            'taskbar original evidence root differs')
    paths, total, compressed_total, position, decoded = [], 0, 0, 0, []
    for entry in manifest['files']:
        exact(entry, {'path', 'bytes', 'sha256', 'compressed_bytes', 'chunks', 'encoding'}, 'taskbar entry schema differs')
        name = relative(entry['path'])
        require(name not in paths, 'duplicate taskbar evidence file')
        paths.append(name)
        require(type(entry['bytes']) is int and 0 <= entry['bytes'] <= MAX_FILE
                and type(entry['compressed_bytes']) is int and 0 < entry['compressed_bytes'] <= MAX_FILE + 65536
                and type(entry['chunks']) is int and entry['chunks'] == math.ceil(entry['compressed_bytes'] / CHUNK)
                and entry['encoding'] == 'zlib+base64'
                and type(entry['sha256']) is str and SHA.fullmatch(entry['sha256']),
                'taskbar file byte/chunk/hash bound differs')
        selected = chunks[position:position + entry['chunks']]
        position += entry['chunks']
        require(len(selected) == entry['chunks'], 'missing taskbar chunks')
        pieces = []
        for index, chunk in enumerate(selected):
            exact(chunk, {'token', 'path', 'index', 'data'}, 'taskbar chunk schema differs')
            require(chunk['token'] == context['token'] and chunk['path'] == name
                    and type(chunk['index']) is int and chunk['index'] == index
                    and type(chunk['data']) is str and 0 < len(chunk['data']) <= 24576,
                    'duplicate/reordered/oversized taskbar chunk')
            part = base64.b64decode(chunk['data'], validate=True)
            require(base64.b64encode(part).decode() == chunk['data'] and len(part) == (
                CHUNK if index + 1 < entry['chunks'] else entry['compressed_bytes'] - index * CHUNK),
                'noncanonical or incorrectly sized taskbar chunk')
            pieces.append(part)
        compressed = b''.join(pieces)
        compressed_total += len(compressed)
        require(len(compressed) == entry['compressed_bytes'] and compressed_total <= MAX_TOTAL + MAX_FILES * 65536,
                'taskbar compressed size differs')
        decoder = zlib.decompressobj()
        data = decoder.decompress(compressed, entry['bytes'] + 1)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
                and len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'],
                'taskbar expansion/content/hash differs')
        total += len(data)
        require(total <= MAX_TOTAL, 'taskbar expanded aggregate bound exceeded')
        decoded.append((name, data, entry['sha256']))
    require(paths == sorted(paths) and position == len(chunks) and total == manifest['bytes'],
            'taskbar manifest ordering/unknown chunks/aggregate differs')
    target = Path(target)
    require(not target.exists() and not target.is_symlink(), 'taskbar output target must be unused')
    target.parent.mkdir(parents=True, exist_ok=True)
    require(all(not p.is_symlink() for p in [target.parent, *target.parent.parents]), 'taskbar output parent is a symlink')
    target.mkdir()
    copied = {}
    # Nothing is written until the complete transport has been checked.
    for name, data, sha in decoded:
        path = target / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)
        copied[name] = dict(bytes=len(data), sha256=sha)
    write_json(target / 'transport-manifest.json', manifest)
    return copied


def rectangle(value):
    exact(value, ('x', 'y', 'width', 'height'), 'taskbar rectangle schema differs')
    require(all(type(v) in (int, float) and math.isfinite(v) for v in value.values())
            and value['width'] > 0 and value['height'] > 0, 'taskbar rectangle values differ')
    return value


def geometry(baseline, edge, mode):
    value = dict(rectangle(baseline))
    inset = dict.fromkeys(EDGES, 6)
    if mode == 'always':
        inset[edge] += 32
    value['x'] += inset['left']; value['y'] += inset['top']
    value['width'] -= inset['left'] + inset['right']; value['height'] -= inset['top'] + inset['bottom']
    return value


def same_rectangle(actual, expected):
    require(all(abs(rectangle(actual)[k] - rectangle(expected)[k]) <= 1 for k in expected),
            'taskbar reserve geometry differs')


def layers(value, outputs, mode):
    require(type(value) is list and len(value) <= 32 and all(type(v) is dict for v in value),
            'taskbar layer inventory malformed')
    for name, count, layer in (('arctic-bar', 1, 'top' if mode == 'always' else 'overlay'),
                               ('arctic-frame', 1, 'bottom'),
                               ('arctic-frame-reserve', 3 if mode == 'always' else 4, 'bottom')):
        members = [v for v in value if v.get('name') == name]
        counts = Counter(v.get('monitor') for v in members)
        require(set(counts) == set(outputs) and all(counts[o] == count for o in outputs)
                and all(v.get('layer') == layer for v in members), 'taskbar missing/duplicate/wrong-layer surface')


def image_bytes(name, target, copied):
    require(name in copied and name.endswith('.png'), 'required taskbar PNG absent')
    data = (target / name).read_bytes()
    require(data.startswith(b'\x89PNG\r\n\x1a\n'), 'taskbar capture is not PNG')
    with Image.open(io.BytesIO(data)) as image:
        require(image.format == 'PNG' and 64 <= image.width <= 8192 and 64 <= image.height <= 8192
                and image.width * image.height <= 16_777_216, 'taskbar PNG dimensions exceed bound')
        image.load()
        return image.convert('RGB')


def check_visibility(name, target, copied, edge, scale, shown, observation=None):
    image = image_bytes(name, target, copied)
    offset = max(4, round(22 * scale))
    x, y = {'top': (image.width // 2, offset), 'bottom': (image.width // 2, image.height - 1 - offset),
            'left': (offset, image.height // 2), 'right': (image.width - 1 - offset, image.height // 2)}[edge]
    radius = max(2, round(3 * scale))
    require(radius <= x < image.width - radius and radius <= y < image.height - radius,
            'taskbar PNG too small for visibility oracle')
    values = [image.getpixel((xx, yy)) for yy in range(y-radius, y+radius+1)
              for xx in range(x-radius, x+radius+1)]
    fraction = sum(max(abs(a-b) for a, b in zip(v, FOOT)) > 10 for v in values) / len(values)
    require(fraction >= .6 if shown else fraction <= .1, 'taskbar independent PNG visibility gate failed')
    if observation is not None:
        exact(observation, ('path', 'sha256', 'visible', 'non_foot_fraction', 'sampled_pixels', 'region'),
              'taskbar pixel observation schema differs')
        require(observation['visible'] is shown and type(observation['non_foot_fraction']) in (int, float)
                and observation['non_foot_fraction'] == fraction
                and type(observation['sampled_pixels']) is int and observation['sampled_pixels'] == len(values)
                and observation['region'] == [x-radius, y-radius, x+radius+1, y+radius+1],
                'taskbar claimed pixel observation differs from PNG')


def validate_pass(report, proof, context, target, copied):
    require(type(report) is dict and report.get('schema') == 'arctic-installed-taskbar-v1'
            and report.get('stage') == 'installed' and report.get('release_acceptance') is False
            and report.get('status') == 'passed' and not any(k in report for k in ('error', 'cleanup_error', 'security_error')),
            'actual taskbar report failed or identity differs')
    exact(report['cleanup'], ('settings_bytes_restored', 'outputs_restored', 'original_windows_retained',
                             'bars_restored', 'only_proved_owned_processes_stopped'), 'taskbar restoration proof differs')
    require(all(v is True for v in report['cleanup'].values()), 'taskbar restoration failed')
    security = report['security']
    require(type(security) is dict and security.get('selinux') == 'Enforcing'
            and type(security.get('observed_new_avcs')) is int and security['observed_new_avcs'] == 0
            and security.get('audit_enabled') is True and type(security.get('audit')) is dict
            and type(security['audit'].get('enabled')) is int and security['audit']['enabled'] in (1, 2)
            and type(security['audit'].get('lost')) is int and security['audit']['lost'] >= 0,
            'taskbar SELinux/audit interval failed or telemetry incomplete')
    inputs = report['installed_inputs']
    require(type(inputs) is dict and all(type(k) is str and type(v) is str and SHA.fullmatch(v) for k,v in inputs.items())
            and inputs.get('/run/t/virtual-pointer') == context['pointer_sha256']
            and inputs.get('/run/t/raw-screencopy') == context['capture_sha256'], 'taskbar installed input hashes differ')
    required_inputs = {'/usr/share/arctic/shell/' + x for x in ('Bar.qml', 'ScreenFrame.qml', 'Session.qml', 'Theme.qml',
                        'VerticalBar.qml', 'BarVisibility.js', 'scripts/window_geometry.py')} | {
                        '/usr/bin/foot', '/run/t/virtual-pointer', '/run/t/raw-screencopy'}
    optional_inputs = {'/usr/bin/mango', '/usr/bin/mmsg', '/usr/share/arctic/shell/shell.qml'}
    extra = set(inputs) - required_inputs
    optional = extra & optional_inputs
    themes = extra - optional_inputs
    require(required_inputs <= set(inputs) and optional in (set(), optional_inputs) and len(themes) == 1
            and re.fullmatch(r'/home/[^/]+/\.config/arctic/current/theme\.json', next(iter(themes))),
            'taskbar installed source inventory differs')
    if 'owned_window' in report:
        owner = report['owned_window']
        require(type(owner) is dict and type(owner.get('pid')) is int and owner['pid'] > 1
                and type(owner.get('start_ticks')) is int and owner['start_ticks'] > 0
                and type(owner.get('client_id')) is str and re.fullmatch('[0-9]+', owner['client_id'])
                and owner.get('executable') == '/usr/bin/foot' and owner.get('is_xwayland') is False
                and ('uid' not in owner or owner['uid'] == proof['desktop_uid']),
                'taskbar owned actual Foot process identity differs')
    results = report['results']
    require(type(results) is list and len(results) == 24 and all(type(v) is dict for v in results), 'taskbar matrix incomplete')
    outputs = sorted({v.get('output') for v in results if type(v.get('output')) is str})
    require(len(outputs) == 2 and all(re.fullmatch('[A-Za-z0-9_.-]{1,128}', o) for o in outputs), 'taskbar output matrix differs')
    expected_cases = {(o, s, e) for o in outputs for s in SCALES for e in EDGES}
    require(all(type(v.get('scale')) in (int, float) for v in results)
            and len({(v.get('output'), v.get('scale'), v.get('edge')) for v in results}) == 24
            and {(v.get('output'), v.get('scale'), v.get('edge')) for v in results} == expected_cases,
            'taskbar edge/fractional-scale/output coverage differs')
    root = Path(report['evidence_root'])
    expected_pngs = set()
    def png_name(label):
        name = re.sub('[^a-zA-Z0-9_-]', '_', label) + '.png'
        expected_pngs.add(name)
        return name
    def observation(value, name, edge, scale, shown):
        require(type(value) is dict and value.get('path') == str(root / name)
                and name in copied and value.get('sha256') == copied[name]['sha256'],
                'taskbar report PNG path/hash differs')
        check_visibility(name, target, copied, edge, scale, shown, value)
    for case in results:
        exact(case, ('output', 'scale', 'edge', 'baseline', 'always_geometry', 'hiding_geometry', 'transitions',
                     'covered_windows', 'exposed_frame'), 'taskbar case schema differs')
        name, scale, edge = case['output'], case['scale'], case['edge']
        label = f'{name}-{scale}-{edge}'
        same_rectangle(case['always_geometry'], geometry(case['baseline'], edge, 'always'))
        hidden = geometry(case['baseline'], edge, 'auto')
        same_rectangle(case['hiding_geometry'], hidden)
        require(type(case['covered_windows']) is list and len(case['covered_windows']) == 2
                and [v.get('mode') for v in case['covered_windows']] == ['auto', 'dodge'], 'taskbar covered-window modes differ')
        for value in case['covered_windows']:
            exact(value, ('mode', 'geometry', 'rest', 'reveal', 'layers'), 'taskbar covered-window schema differs')
            mode = value['mode']; same_rectangle(value['geometry'], hidden); layers(value['layers'], outputs, mode)
            for suffix, shown in (('rest', False), ('reveal', True)):
                observation(value[suffix], png_name(label+'-'+mode+'-covered-'+suffix), edge, scale, shown)
            check_visibility(png_name(label+'-'+mode+'-covered-conceal'), target, copied, edge, scale, False)
        require(type(case['transitions']) is list and len(case['transitions']) == 5
                and [v.get('mode') for v in case['transitions']] == ['auto', 'dodge', 'always', 'auto', 'dodge'],
                'taskbar fullscreen transition coverage differs')
        for index, value in enumerate(case['transitions']):
            exact(value, ('mode', 'rest', 'reveal', 'layers'), 'taskbar fullscreen schema differs')
            mode = value['mode']; label2 = label+'-fullscreen-'+str(index)+'-'+mode
            layers(value['layers'], outputs, mode)
            observation(value['rest'], png_name(label2+'-rest'), edge, scale, False)
            if mode == 'always':
                require(value['reveal'] is None, 'fullscreen Always must be covered by actual fullscreen client')
            else:
                observation(value['reveal'], png_name(label2+'-reveal'), edge, scale, True)
                check_visibility(png_name(label2+'-conceal'), target, copied, edge, scale, False)
        exposed = case['exposed_frame']; exposed_name = png_name(label+'-frame-exposed')
        exact(exposed, ('path', 'sha256', 'scale'), 'taskbar exposed frame schema differs')
        require(exposed['path'] == str(root/exposed_name) and exposed_name in copied
                and exposed['sha256'] == copied[exposed_name]['sha256']
                and type(exposed['scale']) in (int, float) and exposed['scale'] == scale, 'taskbar exposed frame path/hash/scale differs')
        image_bytes(exposed_name, target, copied)
    require(len(expected_pngs) == 480 and expected_pngs <= set(copied), 'taskbar concealed/revealed/frame PNG inventory incomplete')
    require({'gui-trace.log', 'gui-trace-summary.json', 'final-clients.json'} <= set(copied), 'taskbar actual trace evidence missing')
    summary = strict_json((target / 'gui-trace-summary.json').read_bytes())
    trace = (target / 'gui-trace.log').read_bytes()
    require(type(summary) is dict and type(summary.get('omitted_records')) is int and summary['omitted_records'] == 0
            and type(summary.get('bytes')) is int and summary['bytes'] == len(trace), 'taskbar trace omitted/truncated')
    rows = [strict_json(line) for line in trace.splitlines()]
    require(len(rows) <= 20000 and all(type(r) is dict for r in rows)
            and [r['case'] for r in rows if r.get('event') == 'taskbar-case-passed'] == results,
            'taskbar trace and reported case matrix differ')
    return expected_pngs


def check_taskbar(serial, context, target, transport_serial=None):
    """Preserve authenticated failed reports before asserting all actual-image gates passed."""
    begin, proof, report, chunks, manifest, end = block(serial, context, transport_serial)
    copied = extract(chunks, manifest, context, target)
    target = Path(target)
    write_json(target / 'serial-taskbar-report.json', report)
    write_json(target / 'serial-taskbar-provenance.json', proof)
    require('taskbar-report.json' in copied and strict_json((target / 'taskbar-report.json').read_bytes()) == report
            and type(report) is dict and report.get('evidence_root') == manifest['evidence_root']
            and report.get('release_acceptance') is False, 'taskbar complete file/serial report/root differs')
    state = dict(schema='arctic-taskbar-state-v1', stage='installed', status='failed', release_acceptance=False,
                 context=context, provenance=proof, collector=end, files=copied,
                 screenshot_review='REQUIRED; actual PNG arithmetic does not replace visual review')
    write_json(target / 'taskbar-state.json', state)
    require(end['status'] == 'passed' and end['error'] is None and end['evidence_export_complete'] is True,
            'taskbar runtime/checker/collector failed; preserved bounded evidence requires review')
    pngs = validate_pass(report, proof, context, target, copied)
    state.update(status='passed', required_pngs=len(pngs))
    write_json(target / 'taskbar-state.json', state)
    return state
