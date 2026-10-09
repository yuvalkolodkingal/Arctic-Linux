#!/usr/bin/env python3
"""Bounded host extraction for the separate exact-image live installer gate.

Checks transport identity, report completeness and physical PNG arithmetic.
Independent behavior/security validation and manual image review are still
required; this module never grants release acceptance.
"""
import base64
import hashlib
import importlib.util
import io
import json
import math
from pathlib import Path
import re
import zlib

from PIL import Image, ImageColor

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('installer_transport_guest_primitives', HERE / 'guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)
require, strict_json, validate_context = guest.require, guest.strict_json, guest.validate_context
MAX_FILE, MAX_TOTAL, MAX_FILES, CHUNK = guest.MAX_FILE, guest.MAX_TOTAL, guest.MAX_FILES, guest.CHUNK
MAX_PORT = 64 * 1024 * 1024
MAX_UART = 16 * 1024 * 1024
PREFIX = 'ARCTIC-INSTALLER-'
IDENTITY = {'boot_id', 'desktop_uid', 'active_desktop_session'}
SHA = re.compile('[0-9a-f]{64}')
UUID = re.compile('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
PNG_NAMES = {'baseline.png', 'vt-0.png', 'vt-1.png', 'vt-2.png',
             'output-0.png', 'output-1.png', 'output-2.png',
             'output-0-relocated.png', 'output-2-relocated.png'}
RESERVED = {'transport-manifest.json', 'installer-state.json', 'installer-provenance.json',
            'serial-installer-report.json'}
REQUEST_ORDER = [('vt-away', i) for i in range(3)] + [
    (kind, i) for i in range(3) for kind in ('output-disconnect', 'output-restore')]
CASE_ORDER = [('vt', i) for i in range(3)] + [('output', i) for i in range(3)]


def canonical(value):
    return json.dumps(value, sort_keys=True, allow_nan=False).encode('ascii')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact(value, fields, message):
    require(type(value) is dict and set(value) == set(fields), message)


def relative(value):
    require(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]+\.(png|json)', value)
            and value not in RESERVED and value in PNG_NAMES | {'installer-report.json'},
            'unsafe, unexpected, or reserved installer evidence path')
    return value


def record(line, allowed, limit):
    require(line.endswith('\n') and line.startswith(PREFIX) and ' ' in line and len(line) <= limit,
            'malformed, incomplete, or oversized installer record')
    kind, text = line[len(PREFIX):].rstrip('\r\n').split(' ', 1)
    require(kind in allowed, 'unknown installer record')
    return kind, strict_json(text)


def block(port_data, serial_data, context):
    validate_context(context)
    require(type(port_data) is bytes and 0 < len(port_data) <= MAX_PORT,
            'installer port input exceeds bound')
    require(type(serial_data) is bytes and 0 < len(serial_data) <= MAX_UART,
            'installer UART input exceeds bound')
    # Producer writes ASCII JSON on the dedicated port. UART kernel/login
    # diagnostics may be UTF-8; all installer control records must be complete.
    port_text = port_data.decode('ascii')
    serial_text = serial_data.decode('utf-8')
    rows = [record(line, {'BEGIN', 'PROVENANCE', 'REPORT', 'EVIDENCE-CHUNK', 'EVIDENCE-MANIFEST', 'END'},
                   MAX_FILE + 512) for line in port_text.splitlines(keepends=True)]
    kinds = [kind for kind, _ in rows]
    require(len(rows) >= 6 and kinds[:3] == ['BEGIN', 'PROVENANCE', 'REPORT']
            and kinds[-2:] == ['EVIDENCE-MANIFEST', 'END']
            and all(kind == 'EVIDENCE-CHUNK' for kind in kinds[3:-2]),
            'missing, duplicate, or reordered installer port records')
    begin, proof, report, manifest, end = [rows[i][1] for i in (0, 1, 2, -2, -1)]
    exact(begin, {'schema', 'stage', 'context', 'transport', 'release_acceptance'} | IDENTITY,
          'installer BEGIN schema differs')
    exact(proof, {'schema', 'stage', 'context', 'transport', 'cmdline', 'virtualization',
                  'release_acceptance'} | IDENTITY, 'installer provenance schema differs')
    exact(end, {'token', 'status', 'error', 'evidence_export_complete', 'release_acceptance'} | IDENTITY,
          'installer END schema differs')
    validate_context(begin['context'])
    validate_context(proof['context'])
    require(begin['schema'] == 'arctic-installer-runner-v1'
            and proof['schema'] == 'arctic-installer-provenance-v1'
            and begin['stage'] == proof['stage'] == 'live'
            and canonical(begin['context']) == canonical(proof['context']) == canonical(context)
            and begin['release_acceptance'] is proof['release_acceptance'] is end['release_acceptance'] is False,
            'installer exact-image context or release scope differs')
    require(type(begin['boot_id']) is str and UUID.fullmatch(begin['boot_id'])
            and type(begin['desktop_uid']) is int and 1000 <= begin['desktop_uid'] <= 2147483647
            and type(begin['active_desktop_session']) is str
            and re.fullmatch('[A-Za-z0-9_-]{1,64}', begin['active_desktop_session'])
            and all(type(proof[k]) is type(begin[k]) and type(end[k]) is type(begin[k])
                    and begin[k] == proof[k] == end[k] for k in IDENTITY)
            and end['token'] == context['token'], 'installer boot, UID, session, or token differs')
    require(type(proof['cmdline']) is str and len(proof['cmdline']) <= 16384
            and {'rd.live.image', 'arctic.mode=install'} <= set(proof['cmdline'].split())
            and proof['virtualization'] in ('qemu', 'kvm'), 'installer actual live boot identity differs')
    channel = begin['transport']
    exact(channel, ('schema', 'name', 'device', 'major', 'minor', 'uid', 'mode'),
          'installer transport receipt differs')
    require(canonical(channel) == canonical(proof['transport']) and channel['schema'] == 'arctic-installer-virtio-port-v1'
            and channel['name'] == 'arctic-installer-evidence'
            and type(channel['device']) is str and re.fullmatch('/dev/vport[0-9]+p[0-9]+', channel['device'])
            and type(channel['uid']) is int and channel['uid'] == 0
            and type(channel['mode']) is int and 0 <= channel['mode'] <= 0o7777 and not channel['mode'] & 0o022
            and type(channel['major']) is int and 0 < channel['major'] <= 99999
            and type(channel['minor']) is int and 0 <= channel['minor'] <= 99999,
            'installer protected named port identity differs')
    require(end['status'] in ('passed', 'failed') and type(end['evidence_export_complete']) is bool
            and (end['error'] is None or type(end['error']) is str and len(end['error']) <= 4096),
            'installer collector status malformed')
    uart = [record(line, {'REQUEST', 'PORT-END'}, 16448)
            for line in serial_text.splitlines(keepends=True) if line.startswith(PREFIX)]
    require(bool(uart) and uart[-1][0] == 'PORT-END'
            and all(kind == 'REQUEST' for kind, _ in uart[:-1]),
            'missing, duplicate, or reversed installer UART completion')
    marker = uart[-1][1]
    exact(marker, {'schema', 'token', 'status', 'end_sha256', 'release_acceptance'} | IDENTITY,
          'installer UART completion schema differs')
    require(marker['schema'] == 'arctic-installer-port-end-v1' and marker['token'] == context['token']
            and marker['status'] == end['status'] and marker['release_acceptance'] is False
            and all(type(marker[k]) is type(begin[k]) and marker[k] == begin[k] for k in IDENTITY)
            and marker['end_sha256'] == digest(canonical(end)), 'installer port END/UART receipt differs')
    require(type(report) is dict and report.get('schema') == guest.SCHEMA
            and report.get('stage') == 'live' and report.get('release_acceptance') is False
            and report.get('status') in ('passed', 'failed') and canonical(report.get('context')) == canonical(context)
            and all(type(report.get(k)) is type(begin[k]) and report[k] == begin[k] for k in IDENTITY), 'installer REPORT identity differs')
    requests = [value for _, value in uart[:-1]]
    validate_requests(requests, begin, report)
    return begin, proof, report, [value for _, value in rows[3:-2]], manifest, end, marker, requests


def validate_requests(requests, begin, report):
    require(type(requests) is list and len(requests) <= len(REQUEST_ORDER), 'too many installer requests')
    for index, value in enumerate(requests):
        common = {'schema', 'kind', 'token', 'boot_id', 'cycle'}
        require(type(value) is dict and type(value.get('cycle')) is int
                and (value.get('kind'), value['cycle']) == REQUEST_ORDER[index],
                'duplicate, missing, or reordered installer request')
        extra = ({'away', 'original_vt', 'engine_sha256'} if value['kind'] == 'vt-away' else
                 {'mode', 'hosting_output', 'hosting_head', 'enabled_outputs', 'engine_sha256'} |
                 ({'enabled_output_count', 'outputs_sha256', 'outputs'} if value['kind'] == 'output-restore' else set()))
        exact(value, common | extra, 'installer request fields differ')
        require(value['schema'] == 'arctic-installer-request-v1' and value['token'] == begin['context']['token']
                and value['boot_id'] == begin['boot_id'] and type(value['engine_sha256']) is str
                and SHA.fullmatch(value['engine_sha256']), 'installer request token, boot, or engine digest differs')
        if value['kind'] == 'vt-away':
            away = value['away']
            exact(away, ('session', 'uid', 'vt', 'active', 'foreground'), 'installer away-VT state differs')
            require(type(value['original_vt']) is int and 1 <= value['original_vt'] <= 63
                    and value['original_vt'] != 6 and value['original_vt'] == report.get('original_vt')
                    and away['session'] == begin['active_desktop_session'] and away['uid'] == begin['desktop_uid']
                    and type(away['vt']) is int and type(away['uid']) is int and away['vt'] == value['original_vt'] and away['active'] is False
                    and away['foreground'] == 'tty6', 'actual installer away VT/session differs')
        else:
            require(value['mode'] == ('all' if value['cycle'] == 1 else 'hosting-only')
                    and value['hosting_output'] in ('Virtual-1', 'Virtual-2')
                    and type(value['hosting_head']) is int
                    and value['hosting_head'] == int(value['hosting_output'][-1]) - 1
                    and value['enabled_outputs'] == ['Virtual-1', 'Virtual-2'], 'installer output/head request differs')
            if value['kind'] == 'output-restore':
                outputs = guest.enabled_outputs(value['outputs'])
                count = 0 if value['mode'] == 'all' else 1
                require(len(value['outputs']) <= 2 and type(value['enabled_output_count']) is int
                        and value['enabled_output_count'] == len(outputs) == count
                        and all(o['name'] != value['hosting_output'] for o in outputs)
                        and type(value['outputs_sha256']) is str
                        and value['outputs_sha256'] == digest(canonical(value['outputs'])),
                        'installer restore precedes actual hosting/all-output loss')


def decode(chunks, manifest, context, report):
    exact(manifest, ('schema', 'token', 'evidence_root', 'files', 'bytes'), 'installer manifest schema differs')
    require(manifest['schema'] == 'arctic-installer-evidence-v1' and manifest['token'] == context['token']
            and type(manifest['evidence_root']) is str
            and re.fullmatch('/tmp/arctic-native-smoke-installer-[A-Za-z0-9_-]+', manifest['evidence_root'])
            and report.get('evidence_root') == manifest['evidence_root']
            and type(manifest['files']) is list and 1 <= len(manifest['files']) <= MAX_FILES
            and type(manifest['bytes']) is int and 0 <= manifest['bytes'] <= MAX_TOTAL,
            'installer manifest identity or aggregate bound differs')
    paths, decoded, position, total, compressed_total = [], {}, 0, 0, 0
    for entry in manifest['files']:
        exact(entry, ('path', 'bytes', 'sha256', 'compressed_bytes', 'chunks', 'encoding'),
              'installer file entry differs')
        name = relative(entry['path'])
        require(name not in paths, 'duplicate installer evidence path')
        paths.append(name)
        require(type(entry['bytes']) is int and 0 <= entry['bytes'] <= MAX_FILE
                and type(entry['compressed_bytes']) is int and 0 < entry['compressed_bytes'] <= MAX_FILE + 65536
                and type(entry['chunks']) is int and entry['chunks'] == math.ceil(entry['compressed_bytes'] / CHUNK)
                and entry['encoding'] == 'zlib+base64' and type(entry['sha256']) is str
                and SHA.fullmatch(entry['sha256']), 'installer file byte/chunk/hash bound differs')
        selected = chunks[position:position + entry['chunks']]
        position += entry['chunks']
        require(len(selected) == entry['chunks'], 'missing installer chunks')
        pieces = []
        for index, chunk in enumerate(selected):
            exact(chunk, ('token', 'path', 'index', 'data'), 'installer chunk schema differs')
            require(chunk['token'] == context['token'] and chunk['path'] == name
                    and type(chunk['index']) is int and chunk['index'] == index
                    and type(chunk['data']) is str and 0 < len(chunk['data']) <= 24576,
                    'duplicate, reordered, foreign, or oversized installer chunk')
            part = base64.b64decode(chunk['data'], validate=True)
            require(base64.b64encode(part).decode('ascii') == chunk['data']
                    and len(part) == (CHUNK if index + 1 < entry['chunks'] else entry['compressed_bytes'] - index * CHUNK),
                    'noncanonical or incorrectly sized installer chunk')
            pieces.append(part)
        compressed = b''.join(pieces)
        compressed_total += len(compressed)
        require(len(compressed) == entry['compressed_bytes']
                and compressed_total <= MAX_TOTAL + MAX_FILES * 65536, 'installer compressed aggregate differs')
        decoder = zlib.decompressobj()
        data = decoder.decompress(compressed, entry['bytes'] + 1)
        require(decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail
                and len(data) == entry['bytes'] and digest(data) == entry['sha256'],
                'installer expansion, trailing stream, content, or hash differs')
        total += len(data)
        require(total <= MAX_TOTAL, 'installer expanded aggregate bound exceeded')
        decoded[name] = data
    require(paths == sorted(paths) and position == len(chunks) and total == manifest['bytes'],
            'installer manifest ordering, unknown chunks, or total differs')
    require('installer-report.json' in decoded and canonical(strict_json(decoded['installer-report.json'])) == canonical(report),
            'exported installer report differs from authoritative port REPORT')
    return decoded


def validate_capture(value, visible, name, decoded):
    exact(value, ('path', 'bytes', 'sha256', 'size', 'background', 'pixels', 'region', 'tolerance'),
          'installer capture metadata differs')
    require(value['path'] == name and name in decoded and name in PNG_NAMES
            and type(value['bytes']) is int and value['bytes'] == len(decoded[name])
            and value['sha256'] == digest(decoded[name]) and value['tolerance'] == 3
            and type(value['tolerance']) is int, 'installer PNG reference or tolerance differs')
    data = decoded[name]
    require(data.startswith(b'\x89PNG\r\n\x1a\n'), 'installer capture is not PNG')
    with Image.open(io.BytesIO(data)) as image:
        require(image.format == 'PNG' and getattr(image, 'n_frames', 1) == 1
                and 640 <= image.width <= 8192 and 360 <= image.height <= 8192
                and image.width * image.height <= 16_777_216, 'installer PNG dimensions or frame count exceed bound')
        image.load()
        rgb = image.convert('RGB')
        require(value['size'] == visible['physical_size'] == [rgb.width, rgb.height],
                'installer PNG physical dimensions differ')
        background = list(ImageColor.getrgb(visible['window']['background'])[:3])
        x, y = rgb.width - 10, rgb.height // 2
        pixels = [list(rgb.getpixel((xx, yy))) for yy in range(y - 1, y + 2) for xx in range(x - 1, x + 2)]
        require(value['background'] == background and value['pixels'] == pixels
                and value['region'] == [x - 1, y - 1, x + 2, y + 2]
                and all(max(abs(a - b) for a, b in zip(pixel, background)) <= 3 for pixel in pixels),
                'installer independent PNG pixel gate differs')


def validate_pass(report, begin, end, requests, decoded):
    require(report['status'] == end['status'] == 'passed' and end['error'] is None
            and end['evidence_export_complete'] is True and report.get('errors') == []
            and type(report.get('captures')) is int and report['captures'] == 9,
            'installer checker, collector, export, or cleanup failed')
    require(set(decoded) == PNG_NAMES | {'installer-report.json'}, 'installer complete nine-PNG inventory differs')
    require(type(report.get('cases')) is list and len(report['cases']) == 6
            and all(type(v) is dict and type(v.get('cycle')) is int and v.get('status') == 'passed'
                    for v in report['cases'])
            and [(v.get('kind'), v['cycle']) for v in report['cases']] == CASE_ORDER,
            'installer six-cycle matrix is incomplete or duplicated')
    require(len(requests) == len(REQUEST_ORDER), 'installer UART nine-request matrix incomplete')
    baseline = report['baseline']
    visible = guest.window_proof(baseline['state'], baseline['visible']['layers'], baseline['outputs'])
    require(visible == baseline['visible'], 'installer baseline visible geometry differs')
    validate_capture(baseline['capture'], visible, 'baseline.png', decoded)
    expected_requests = []
    for case in report['cases']:
        kind, cycle, disruption = case['kind'], case['cycle'], case['disruption']
        visible = guest.window_proof(case['state'], case['visible']['layers'], case['outputs'])
        require(visible == case['visible'], 'installer restored visible geometry differs')
        validate_capture(case['capture'], visible, kind + '-' + str(cycle) + '.png', decoded)
        if kind == 'vt':
            request = disruption['request']
            require(request['away'] == disruption['away']
                    and request['engine_sha256'] == digest(canonical(disruption['prepared_state']['engine']))
                    and disruption['returned_vt'] == report['original_vt'], 'installer VT receipt/report state differs')
            expected_requests.append(request)
        else:
            unavailable = disruption['unavailable']
            restore = disruption['restore_request']
            require(restore['outputs'] == unavailable['outputs']
                    and restore['enabled_output_count'] == unavailable['enabled_output_count']
                    and restore['outputs_sha256'] == digest(canonical(unavailable['outputs']))
                    and restore['engine_sha256'] == digest(canonical(unavailable['engine']))
                    and disruption['disconnect_request']['engine_sha256'] == digest(canonical(baseline['engine'])),
                    'installer output-loss receipt/report state differs')
            if cycle in (0, 2):
                visible = guest.window_proof(unavailable['state'], unavailable['visible']['layers'],
                                             unavailable['outputs'], expected_count=1)
                require(visible == unavailable['visible']
                        and visible['window']['screen'] != disruption['hosting_output'],
                        'installer hosting-loss relocation geometry differs')
                validate_capture(unavailable['capture'], visible, 'output-' + str(cycle) + '-relocated.png', decoded)
            else:
                require(unavailable['enabled_output_count'] == 0
                        and not guest.enabled_outputs(unavailable['outputs']) and unavailable['installer_layers'] == [],
                        'installer complete output loss was not observed')
            expected_requests.extend((disruption['disconnect_request'], restore))
    require(canonical(requests) == canonical(expected_requests), 'actual UART requests differ from embedded report disruptions')


def write_json(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n')


def extract(port_path, serial_path, destination, context):
    """Return state/manifest/files/report/names and preserve valid failed archives.

    Malformed transport raises before any destination is created. Complete
    but failed checker evidence is extracted safely with state.status=failed.
    A passed extraction still requires independent acceptance and manual review.
    """
    port_data = guest.read_regular(port_path, MAX_PORT)
    serial_data = guest.read_regular(serial_path, MAX_UART)
    try:
        begin, proof, report, chunks, manifest, end, marker, requests = block(port_data, serial_data, context)
        decoded = decode(chunks, manifest, context, report)
    except (ValueError, UnicodeError, zlib.error) as exc:
        raise RuntimeError('malformed installer transport: ' + type(exc).__name__) from exc
    state = dict(schema='arctic-installer-evidence-state-v1', status='failed', context=context,
                 **{key: begin[key] for key in IDENTITY}, release_acceptance=False,
                 begin=begin, provenance=proof, report=report, collector=end, port_end=marker,
                 requests=requests, files={}, required_pngs=9, received_pngs=sum(name.endswith('.png') for name in decoded),
                 received_requests=len(requests), errors=[],
                 port=dict(bytes=len(port_data), sha256=digest(port_data)),
                 serial=dict(bytes=len(serial_data), sha256=digest(serial_data)),
                 scope='transport identity, guest completeness and PNG arithmetic; independent behavior/security and manual review required')
    try:
        validate_pass(report, begin, end, requests, decoded)
        state['status'] = 'passed'
    except (RuntimeError, ValueError, KeyError, TypeError, OSError, Image.DecompressionBombError) as exc:
        state['errors'].append(type(exc).__name__ + ': ' + str(exc)[:2000])
    target = Path(destination).absolute()
    require(not target.exists() and not target.is_symlink(), 'installer output destination must be unused')
    require(all(not p.is_symlink() for p in [target.parent, *target.parent.parents]),
            'installer output parent is a symlink')
    target.parent.mkdir(parents=True, exist_ok=True)
    require(all(not p.is_symlink() for p in [target.parent, *target.parent.parents]),
            'installer output parent became a symlink')
    target.mkdir()
    copied = {}
    for name, data in decoded.items():
        with (target / name).open('xb') as stream:
            stream.write(data)
        copied[name] = dict(bytes=len(data), sha256=digest(data))
    state['files'] = copied
    write_json(target / 'transport-manifest.json', manifest)
    write_json(target / 'installer-provenance.json', proof)
    write_json(target / 'serial-installer-report.json', report)
    write_json(target / 'installer-state.json', state)
    return dict(state=state, manifest=manifest, files=copied, report=report, names=sorted(copied),
                requests=requests, begin=begin, provenance=proof, end=end, port_end=marker)
