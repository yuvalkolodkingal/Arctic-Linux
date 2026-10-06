#!/usr/bin/env python3
"""Dedicated same-ISO Safe diagnostic. Preparation is not dispatch approval."""
import argparse
import base64
import datetime
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import uuid
import zlib

sys.dont_write_bytecode = True
BASE = 'ae55fbc9d48cec5ecc786cf61994ed986296d1bb'
COMMON_SHA = '0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633'
SCHEMA = 'arctic-safe-execution-v1'
BUNDLE_FILES = {'safe-runner-v1.py', 'safe-driver-v1.py', 'guest-safe-collector-v1.py',
                'bootstrap-safe-v1.sh', 'prepare-safe-v1.py', 'test_safe_v1.py', 'README-v1.md',
                'render-driver-v1.py', 'guest-render-collector-v1.py', 'fixed-rows-v1.py', 'test_render_v1.py'}
# Exact source-only CI correction; this path is not copied into the guest.
SOURCE_CI_INPUTS = {'tools/tests/test_performance_observer.py': '2c91f921438d312b3462517ffede7d5854b77f3df208a3a5f10eb719428e33d2'}
EXECUTION_FILES = {'.github/workflows/iso.yml', 'tools/test-iso.sh', 'tools/lib/container.sh',
                   'tools/lib/vmtest.py', *SOURCE_CI_INPUTS, *('tools/safe-visual-diagnostic/' + p for p in BUNDLE_FILES)}
CHANGED_FILES = EXECUTION_FILES - {'tools/lib/container.sh', 'tools/lib/vmtest.py'} | {
    'tools/safe-visual-diagnostic/execution-pins-safe-v1.json'}
MAX_FILE = 4 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024


def require(value, message):
    if not value:
        raise RuntimeError(message)


def recovery(args):
    path = args.recovery_bundle / 'vm-only-recovery-v2.py'
    require(path.is_file() and not path.is_symlink() and hashlib.sha256(path.read_bytes()).hexdigest() == COMMON_SHA,
            'Frozen v2 driver changed before import')
    spec = importlib.util.spec_from_file_location('safe_frozen_recovery_v2', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_ci(env, R):
    # Translate only the declared mode for the original immutable CI validator.
    # No v2 function, constant, environment or manifest is patched.
    R.validate_ci(dict(env, RECOVERY_MODE='true'))
    require(env.get('SAFE_DIAGNOSTIC_MODE') == 'true' and env.get('RECOVERY_MODE') == 'false'
            and all(env.get(name) == 'false' for name in ('NATIVE_SMOKE_MODE', 'NIX_REQUESTED',
                    'PERFORMANCE_REQUESTED', 'BOOT_TEST_REQUESTED')), 'Safe mode must be selected alone')
    require(env['GITHUB_SHA'] != BASE and env['GITHUB_RUN_ID'] != '37520174911',
            'Separate reviewed Safe execution head/run required')


def verify_sources(args, R):
    # Preserve the exact original source and original v2 execution verification.
    R.verify_sources(args.source, args.recovery_bundle, BASE)
    execution = args.bundle.parents[1]
    head = subprocess.check_output(['git', '-C', str(execution), 'rev-parse', 'HEAD'], text=True).strip()
    require(head == os.environ['GITHUB_SHA'], 'Safe execution checkout identity differs')
    require(not subprocess.check_output(['git', '-C', str(execution), 'status', '--porcelain'], text=True).strip(),
            'Dirty Safe execution checkout')
    subprocess.run(['git', '-C', str(execution), 'merge-base', '--is-ancestor', BASE, head], check=True, timeout=30)
    changed = set(subprocess.check_output(['git', '-C', str(execution), 'diff', '--name-only', BASE, head], text=True).splitlines())
    require(changed <= CHANGED_FILES and 'tools/test-iso.sh' in changed and '.github/workflows/iso.yml' in changed,
            'Execution changes outside the reviewed Safe-only file set')
    manifest = json.loads((args.bundle / 'execution-pins-safe-v1.json').read_text())
    require(manifest['schema'] == SCHEMA and manifest['candidate_source'] == R.SOURCE
            and manifest['qualification_base'] == BASE and set(manifest['files']) == EXECUTION_FILES,
            'Safe execution manifest identity/file set differs')
    require(all(manifest['files'].get(relative) == expected
                for relative, expected in SOURCE_CI_INPUTS.items()),
            'Reviewed source-CI input identity differs')
    for relative, expected in manifest['files'].items():
        require(not Path(relative).is_absolute() and '..' not in Path(relative).parts, 'Unsafe Safe manifest path')
        R.pinned_file(execution / relative, expected)
    return manifest


def proof(args, R):
    return dict(schema=SCHEMA, candidate_source=R.SOURCE, qualification_base=BASE,
                execution_checker_head=os.environ['GITHUB_SHA'], common_v2_sha256=COMMON_SHA,
                collector_sha256=R.digest(args.bundle / 'guest-safe-collector-v1.py'),
                render_collector_sha256=R.digest(args.bundle / 'guest-render-collector-v1.py'),
                execution_manifest_sha256=R.digest(args.bundle / 'execution-pins-safe-v1.json'),
                original_result_unchanged=True, release_acceptance=False, safe_visual_gate='open')


def preflight(args, R):
    validate_ci(os.environ, R); verify_sources(args, R)
    require(not args.inputs.exists() and not args.evidence.exists(), 'Inputs/evidence paths must be unused')
    args.evidence.mkdir(parents=True)
    docker = R.require_docker()
    require(Path('/dev/kvm').is_char_device(), 'KVM required; no TCG fallback or host chmod')
    require(shutil.disk_usage(args.evidence).free >= 20_000_000_000, 'At least 20 GB free required')
    run = R.api('actions/runs/' + str(R.ORIGINAL_RUN))
    pages = R.api('actions/runs/' + str(R.ORIGINAL_RUN) + '/jobs?filter=all&per_page=100', paginate=True)
    artifact = R.api('actions/artifacts/' + str(R.ARTIFACT_ID))
    original = R.validate_original(run, [j for p in pages for j in p['jobs']], artifact)
    value = proof(args, R)
    value.update(original_result=original, docker_server_version=docker,
                 artifact=dict(id=R.ARTIFACT_ID, name=R.ARTIFACT_NAME, original_run=R.ORIGINAL_RUN,
                               archive_bytes=R.ARCHIVE_BYTES, archive_digest=R.ARCHIVE_DIGEST))
    R.write_json(args.evidence / 'preflight.json', value)


def verify(args, R):
    validate_ci(os.environ, R); verify_sources(args, R)
    value = json.loads((args.evidence / 'preflight.json').read_text())
    require(all(value.get(k) == v for k, v in proof(args, R).items()), 'Preflight belongs to another execution')
    value['iso'] = R.verify_iso(args.inputs)
    R.write_json(args.evidence / 'verified-input.json', value)
    for relative in R.METADATA_PINS:
        target = args.evidence / 'input-metadata' / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(args.inputs / relative, target)


def records(serial, name):
    prefix = 'ARCTIC-SAFE-' + name + ' '
    return [json.loads(line[len(prefix):]) for line in serial.splitlines() if line.startswith(prefix)]


def extract(serial, target, collector_sha):
    require(not target.exists(), 'Guest evidence target must be unused')
    target.mkdir()
    begin, end, reports, manifests = [records(serial, n) for n in ('BEGIN', 'END', 'REPORT', 'MANIFEST')]
    require(all(len(v) == 1 for v in (begin, end, reports, manifests)), 'Missing/duplicate guest protocol record')
    protocol_order = [(i, line.split(' ', 1)[0]) for i, line in enumerate(serial.splitlines())
                      if line.startswith('ARCTIC-SAFE-')]
    positions = {name: [i for i, value in protocol_order if value == 'ARCTIC-SAFE-' + name]
                 for name in ('BEGIN', 'REPORT', 'MANIFEST', 'CHUNK', 'END')}
    require(positions['BEGIN'][0] < positions['REPORT'][0] < positions['MANIFEST'][0] < positions['END'][0]
            and all(positions['MANIFEST'][0] < i < positions['END'][0] for i in positions['CHUNK']),
            'Guest protocol order differs')
    require(begin[0]['collector_sha256'] == collector_sha and begin[0]['release_acceptance'] is False,
            'Guest collector identity differs')
    report, manifest = reports[0], manifests[0]
    require(manifest['schema'] == 'arctic-safe-files-v1' and manifest['encoding'] == 'zlib+base64'
            and isinstance(manifest['files'], list) and len(manifest['files']) <= 128, 'Guest transport schema/bounds differ')
    chunks = records(serial, 'CHUNK'); known = set(); total = 0; copied = {}
    for item in manifest['files']:
        name = item['path']
        require(isinstance(name, str) and name and Path(name).name == name and name not in ('.', '..')
                and name != 'serial-report.json' and Path(name).suffix in ('.json', '.png', '.txt', '.log') and name not in known,
                'Unsafe/duplicate guest evidence name')
        known.add(name)
        require(type(item['bytes']) is int and 0 <= item['bytes'] <= MAX_FILE
                and type(item['compressed_bytes']) is int and 0 < item['compressed_bytes'] <= MAX_FILE + 65536
                and type(item['chunks']) is int and 1 <= item['chunks'] <= 180
                and isinstance(item['sha256'], str) and re.fullmatch('[0-9a-f]{64}', item['sha256']), 'Guest content bounds differ')
        parts = [c for c in chunks if c['path'] == name]
        require(len(parts) == item['chunks'] and [p['index'] for p in parts] == list(range(item['chunks']))
                and all(type(p['index']) is int for p in parts), 'Missing/reordered/duplicate guest chunks')
        packed = b''.join(base64.b64decode(p['data'], validate=True) for p in parts)
        require(len(packed) == item['compressed_bytes'], 'Compressed content length differs')
        decode = zlib.decompressobj(); data = decode.decompress(packed, MAX_FILE + 1)
        require(decode.eof and not decode.unused_data and not decode.unconsumed_tail and len(data) == item['bytes']
                and hashlib.sha256(data).hexdigest() == item['sha256'], 'Guest content checksum/length differs')
        total += len(data); require(total <= MAX_TOTAL, 'Guest aggregate content bound exceeded')
        (target / name).write_bytes(data); copied[name] = dict(bytes=len(data), sha256=item['sha256'])
    require(all(c['path'] in known for c in chunks) and type(manifest['bytes']) is int and total == manifest['bytes'],
            'Unexpected chunks or aggregate length differs')
    (target / 'serial-report.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    require('report.json' in copied and json.loads((target / 'report.json').read_text()) == report,
            'Actual guest report and serial report differ')
    require(report['schema'] == 'arctic-safe-telemetry-v1' and report['collector_sha256'] == collector_sha
            and report['release_acceptance'] is False and report['safe_visual_gate'] == 'open'
            and report['live_welcome_opacity'] == report['effective_render_loop'] == 'unobserved', 'Telemetry meaning/identity differs')
    require(end[0]['status'] == 'collected' and end[0]['error'] is None and end[0]['release_acceptance'] is False
            and report['status'] == 'read-only-telemetry-collected-visual-gate-open', 'Guest guard/collector/security failed')
    require('nomodeset' in report['cmdline'].split() and 'rd.live.image' in report['cmdline'].split()
            and type(report['desktop_uid']) is int and report['desktop_uid'] > 0, 'Actual Safe/user identity differs')
    for name in ('security_before_grim', 'security_after_grim'):
        security = report[name]
        require(isinstance(security, dict) and security.get('selinux') == 'Enforcing'
                and security.get('avc_records') == [] and isinstance(security.get('audit_status'), str),
                'Actual security/AVC evidence failed')
        audit = dict(line.split(None, 1) for line in security['audit_status'].splitlines() if len(line.split(None, 1)) == 2)
        require(security['selinux'] == 'Enforcing' and security['avc_records'] == []
                and audit.get('enabled') in ('1', '2') and audit.get('lost') == '0', 'Actual security/AVC evidence failed')
        logfile = 'system-journal-' + ('before-grim' if name == 'security_before_grim' else 'after-grim') + '.log'
        require(logfile in copied and security['journal_retained_bytes'] == copied[logfile]['bytes']
                and security['journal_retained_sha256'] == copied[logfile]['sha256']
                and type(security['current_boot_journal_records']) is int and security['current_boot_journal_records'] > 0
                and type(security['journal_total_bytes']) is int and security['journal_total_bytes'] >= copied[logfile]['bytes'],
                'Bounded system-journal evidence absent or differs')
    require('guest-grim.png' in copied and (target / 'guest-grim.png').read_bytes().startswith(b'\x89PNG\r\n\x1a\n')
            and report['grim']['sha256'] == copied['guest-grim.png']['sha256'], 'Guest screenshot content/hash absent')
    return dict(files=copied, report=report, status='collected_visual_gate_open', release_acceptance=False)


def validate_events(path):
    events = [json.loads(line) for line in path.read_text().splitlines()]
    require(events and all(type(e.get('monotonic_seconds')) in (int, float) and math.isfinite(e['monotonic_seconds'])
                           for e in events), 'Missing/nonfinite event monotonic clocks')
    require(all(a['monotonic_seconds'] <= b['monotonic_seconds'] for a, b in zip(events, events[1:])), 'Event clocks reverse')
    names = [e['event'] for e in events]
    unique = ('passive-begin', 'passive-end', 'quiet-end', 'pointer-only', 'super-enter', 'return-only', 'collector-command', 'diagnostic-complete')
    require(all(names.count(n) == 1 for n in unique) and [names.index(n) for n in unique] == sorted(names.index(n) for n in unique),
            'Missing/duplicate/reordered input phase')
    by = {n: events[names.index(n)] for n in unique}
    origin = by['passive-begin']['entry_selection_monotonic_origin']
    qemu = by['passive-begin']['qemu_origin']['monotonic_estimate_seconds']
    require(all(type(v) in (int, float) and math.isfinite(v) for v in (origin, qemu))
            and qemu <= origin <= by['passive-begin']['monotonic_seconds'], 'Actual event origin differs')
    require(all(type(e.get(k)) in (int, float) and math.isfinite(e[k])
                and abs(e[k] - (e['monotonic_seconds'] - value)) < 1e-6
                for e in events for k, value in (('entry_elapsed_seconds', origin), ('qemu_elapsed_seconds', qemu))),
            'Event elapsed clocks differ from actual origins')
    require(by['passive-end']['entry_elapsed_seconds'] >= 600 and by['quiet-end']['entry_elapsed_seconds'] >= 720,
            'Required untouched passive/quiet interval too short')
    require(by['quiet-end']['monotonic_seconds'] - by['passive-end']['monotonic_seconds'] >= 120
            and by['pointer-only']['monotonic_seconds'] >= by['quiet-end']['monotonic_seconds'],
            'Required 120-second post-passive quiet interval too short')
    require(all(by[n].get('no_input') is True for n in ('passive-begin', 'passive-end', 'quiet-end')),
            'No-input interval declaration missing')
    rows = [e for e in events if e['event'] == 'capture']
    captures = [e['name'] for e in rows]
    expected = ['safe-passive-%04ds.png' % s for s in list(range(0, 121, 10)) + list(range(180, 601, 60))]
    expected += ['safe-quiet-%04ds.png' % s for s in (660, 720)] + ['safe-10-before-pointer.png']
    for phase, prefix, targets in (('pointer-only', 'safe-11-pointer', (1, 5)),
                                   ('super-enter', 'safe-20-super-enter', (1, 5, 60)),
                                   ('return-only', 'safe-30-return', (1, 5))):
        completed = [e for e in events if e['event'] == 'input-complete' and e.get('phase') == phase]
        require(len(completed) == 1 and completed[0]['input_origin_monotonic_seconds'] == by[phase]['monotonic_seconds']
                and abs(completed[0]['call_elapsed_seconds'] - (completed[0]['monotonic_seconds'] - by[phase]['monotonic_seconds'])) < 1e-6,
                'Input call origin/completion differs')
        for seconds in targets:
            name = '%s-%02ds.png' % (prefix, seconds); expected.append(name)
            matches = [e for e in rows if e['name'] == name]
            require(len(matches) == 1 and matches[0]['monotonic_seconds'] >= by[phase]['monotonic_seconds'] + seconds,
                    'Required separated input capture absent/early')
    expected += ['safe-40-qmp-before-grim.png', 'safe-41-qmp-after-grim.png', 'safe-99-final.png']
    require(captures == expected, 'Required ordered passive/separated/paired captures differ')
    markers = [e for e in events if e['event'] == 'guest-marker']
    require([e.get('marker') for e in markers] == ['GRIM-READY', 'GRIM-DONE', 'END']
            and markers[0]['value'].get('wait_seconds') == 20, 'Required ordered guest screencopy markers differ')
    require(markers[0]['monotonic_seconds'] <= next(e for e in rows if e['name'] == 'safe-40-qmp-before-grim.png')['monotonic_seconds']
            <= markers[1]['monotonic_seconds'] <= next(e for e in rows if e['name'] == 'safe-41-qmp-after-grim.png')['monotonic_seconds']
            <= markers[2]['monotonic_seconds'] <= rows[-1]['monotonic_seconds'], 'Required QMP/guest screencopy separation differs')
    return dict(events=len(events), capture_names=captures, visual_review='Required; telemetry success never closes Safe visual gate')


def run(args, R):
    verify(args, R)
    docker = R.require_docker(); require(Path('/dev/kvm').is_char_device(), 'KVM disappeared')
    base = args.evidence.parent / 'safe-vm'
    require(not base.exists(), 'Fresh Safe VM output must be unused')
    vm = base / 'uefi-safe'
    container = 'arctic-paired-safe-' + uuid.uuid4().hex
    env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container)
    state = dict(**proof(args, R), status='running', docker_server_version=docker)
    def save():
        state['recorded_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        R.write_json(args.evidence / 'execution.json', state)
    def interrupted(signum, frame):
        raise InterruptedError('Safe diagnosis interrupted by signal ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted); signal.signal(signal.SIGINT, interrupted)
    save()
    try:
        argv = ['bash', str(args.bundle.parents[1] / 'tools/test-iso.sh'), '--iso', str(args.inputs / 'iso' / R.ISO),
                '--kvm', '--firmware', 'uefi', '--mode', 'safe', '--memory', '4096', '--smp', '2',
                '--timeout', '600', '--interval', '60', '--debug', '--safe-diagnostic', str(args.bundle), '--out', str(base)]
        try:
            R.execute(argv, args.evidence / 'safe-harness.log', 35*60, args.bundle.parents[1], env, container)
        finally:
            state['evidence'] = R.preserve_phase(vm, args.evidence, 'boot')
            save()
        require('safe-toolchain.txt' in state['evidence'] and 'safe-events.log' in state['evidence'], 'Actual tools/events missing')
        state['guest'] = extract((args.evidence / 'boot/serial.log').read_text(errors='replace'),
                                 args.evidence / 'guest-telemetry', R.digest(args.bundle / 'guest-safe-collector-v1.py'))
        state['events'] = validate_events(args.evidence / 'boot/safe-events.log')
        require(all(name in state['evidence'] for name in state['events']['capture_names']), 'Recorded capture lacks actual preserved image')
        render_spec = importlib.util.spec_from_file_location('safe_render_parser_v1', args.bundle / 'render-driver-v1.py')
        render = importlib.util.module_from_spec(render_spec); render_spec.loader.exec_module(render)
        state['render_guest'] = render.extract((args.evidence / 'boot/serial.log').read_text(errors='replace'),
                                              args.evidence / 'render-telemetry', R.digest(args.bundle / 'guest-render-collector-v1.py'))
        state['render_events'] = render.validate_events(args.evidence / 'boot/render-events.log', args.evidence / 'boot/safe-events.log')
        require(all(name in state['evidence'] for name in state['render_events']['capture_names']), 'Added capture lacks preserved pixels')
        require(sum(v['bytes'] for phase in ('guest', 'render_guest') for v in state[phase]['files'].values()) <= MAX_TOTAL
                and sum(len(state[phase]['files']) for phase in ('guest', 'render_guest')) <= 128, 'Combined telemetry exceeds original bounds')
        require(state['render_guest']['report']['boot_id'] == state['guest']['report']['boot_id'], 'Added collector boot differs')
        state['status'] = 'diagnostic_collected_visual_gate_open'; save()
    except BaseException as exc:
        state['status'] = 'failed_or_unrun'; state['error'] = str(exc); save(); raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('preflight', 'verify', 'run'))
    for name in ('source', 'bundle', 'recovery-bundle', 'inputs', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    for name in ('source', 'bundle', 'recovery_bundle', 'inputs', 'evidence'):
        setattr(args, name, getattr(args, name).resolve())
    R = recovery(args)
    try:
        globals()[args.phase](args, R)
    except BaseException as exc:
        if args.evidence.exists():
            R.write_json(args.evidence / ('blocked-' + args.phase + '.json'), dict(error=str(exc), release_acceptance=False,
                         safe_visual_gate='open', original_result_unchanged=True))
        raise


if __name__ == '__main__':
    main()
