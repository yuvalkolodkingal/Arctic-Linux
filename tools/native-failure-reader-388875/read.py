#!/usr/bin/env python3
"""Read one exact failed Native artifact and emit only a closed diagnostic."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
REPO_API = 'repos/' + REPOSITORY
WORKFLOW = '.github/workflows/native-candidate-20261008.yml'
READER_WORKFLOW = Path('.github/workflows/read-native-failure-388875-v3.yml')
BRANCH = 'codex/read-native-failure-388875-v3-20261016'
ACTIVATION = Path('.github/native-failure-reader-388875-v3.activate')
READER = Path('tools/native-failure-reader-388875/read.py')
VALIDATOR = Path('tools/native-functional/screen-evidence.py')
QUALIFICATION = Path('tools/native-failure-reader-388875/qualification-execution-manifest.json')
SOURCE_PROVENANCE = Path('tools/native-functional/source-provenance.json')
RUN_ID = 38887521541
RUN_ATTEMPT = 1
RUN_HEAD = '02ea0f25863ef4918fadccd91684d016a910455a'
ARTIFACT_ID = 12039923342
ARTIFACT_NAME = 'native-candidate-qualification'
ARTIFACT_BYTES = 13610245
ARTIFACT_SHA256 = 'e24db7ee3b04d600973fd49efcf3921c4ebb8f43e083eb579f56b347a87b6154'
REQUIRED_MEMBERS = {
    'screening': ('upload-screening.json', 1024 * 1024),
    'execution': ('execution.json', 1024 * 1024),
    'harness': ('native-harness.log', 16 * 1024 * 1024),
}
OPTIONAL_MEMBERS = {
    'stop': ('harness/native-stop-install.json', 4096),
    'qemu': ('harness/qemu-install.log', 1024 * 1024),
    'display': ('harness/taskbar-display-install.json', 64 * 1024),
    'stage_log': ('harness/test-install-stage.log', 4 * 1024 * 1024),
    'current_stage_log': ('harness/test.log', 4 * 1024 * 1024),
    'host_frame_receipt': ('harness/native-host-frame-live.json', 128 * 1024),
    'host_frame_image': ('harness/native-host-celluloid-live.png', 4 * 1024 * 1024),
}
MEMBERS = REQUIRED_MEMBERS | OPTIONAL_MEMBERS
MANIFEST_FIELDS = {'schema', 'ready', 'repository', 'workflow', 'reader_workflow', 'branch',
                   'run_id', 'run_attempt', 'run_head', 'artifact', 'reader_sha256',
                   'validator_sha256', 'qualification_manifest_sha256',
                   'reader_workflow_sha256'}
ARTIFACT_FIELDS = {'id', 'name', 'bytes', 'sha256'}
REJECTION_STAGES = {'activation', 'manifest', 'run', 'jobs', 'artifact-metadata',
                    'download', 'archive', 'screening', 'execution', 'stop',
                    'harness', 'projection'}
REJECTION_STAGE = 'manifest'
ARCHIVE_ROLES = {'archive', *MEMBERS}
ARCHIVE_REASONS = {'missing-required', 'duplicate', 'type', 'encryption',
                   'compression', 'size', 'crc', 'read'}
ARCHIVE_ROLE = 'archive'
ARCHIVE_REASON = 'read'


class ArchiveReject(RuntimeError):
    pass


def archive_reject(role, reason):
    global ARCHIVE_ROLE, ARCHIVE_REASON
    if role not in ARCHIVE_ROLES:
        role = 'archive'
    if reason not in ARCHIVE_REASONS:
        reason = 'read'
    ARCHIVE_ROLE, ARCHIVE_REASON = role, reason
    raise ArchiveReject('safe Native reader rejected archive')


def require(value):
    if not value:
        raise RuntimeError('safe Native reader rejected evidence')


def checkpoint(stage):
    global REJECTION_STAGE
    require(stage in REJECTION_STAGES)
    REJECTION_STAGE = stage


def digest(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{' + str(length) + '}', value) is not None


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(type(key) is str and key not in result)
        result[key] = value
    return result


def strict_json(raw, maximum):
    require(type(raw) is bytes and 0 < len(raw) <= maximum)
    return json.loads(raw.decode('utf-8', errors='strict'), object_pairs_hook=unique,
                      parse_constant=lambda _value: (_ for _ in ()).throw(
                          RuntimeError('safe Native reader rejected evidence')))


def read_json_file(path, maximum):
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= maximum)
    return strict_json(path.read_bytes(), maximum)


def validate_manifest(value):
    require(type(value) is dict and set(value) == MANIFEST_FIELDS)
    require(value['schema'] == 'arctic-native-failure-reader-v3'
            and value['ready'] is True and value['repository'] == REPOSITORY
            and value['workflow'] == WORKFLOW
            and value['reader_workflow'] == READER_WORKFLOW.as_posix()
            and value['branch'] == BRANCH and value['run_id'] == RUN_ID
            and value['run_attempt'] == RUN_ATTEMPT and value['run_head'] == RUN_HEAD)
    artifact = value['artifact']
    require(type(artifact) is dict and set(artifact) == ARTIFACT_FIELDS
            and artifact == {'id': ARTIFACT_ID, 'name': ARTIFACT_NAME,
                             'bytes': ARTIFACT_BYTES, 'sha256': ARTIFACT_SHA256})
    files = {
        'reader_sha256': READER,
        'validator_sha256': VALIDATOR,
        'qualification_manifest_sha256': QUALIFICATION,
        'reader_workflow_sha256': READER_WORKFLOW,
    }
    for field, relative in files.items():
        require(digest(value[field]) and sha256((ROOT / relative).read_bytes()) == value[field])
    qualification = read_json_file(ROOT / QUALIFICATION, 128 * 1024)
    require(qualification.get('ready') is True
            and qualification.get('release_acceptance') is False
            and qualification.get('image', {}).get('source_sha') ==
                'f369b978aeb05a3310c512660811084fd5bc97d1'
            and qualification.get('execution_files', {}).get(VALIDATOR.as_posix()) ==
                value['validator_sha256'])
    load_source_provenance(qualification)
    return value, qualification


def load_source_provenance(qualification):
    execution_files = qualification.get('execution_files')
    require(type(execution_files) is dict)
    expected = execution_files.get(SOURCE_PROVENANCE.as_posix())
    path = ROOT / SOURCE_PROVENANCE
    require(digest(expected) and path.is_file() and not path.is_symlink()
            and sha256(path.read_bytes()) == expected)
    value = read_json_file(path, 512 * 1024)
    files = value.get('files')
    require(type(value) is dict and value.get('release_acceptance') is False
            and type(files) is dict
            and digest(files.get('guest-check-native-v6.py'))
            and digest(files.get('native_smoke.py'))
            and digest(value.get('native_source_sha256'))
            and value['native_source_sha256'] == files['native_smoke.py'])
    return {'checker_sha256': files['guest-check-native-v6.py'],
            'native_source_sha256': value['native_source_sha256'],
            'taskbar_display_sha256': execution_files.get(
                'tools/native-functional/taskbar-display.py')}


def activation_guard():
    checkpoint('activation')
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_WORKFLOW') ==
                'Read safe Native diagnostics v3 for run 38887521541'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1')
    child = os.environ.get('GITHUB_SHA', '')
    require(digest(child, 40))
    marker = ROOT / ACTIVATION
    require(marker.is_file() and not marker.is_symlink() and marker.stat().st_size == 41)
    parent = marker.read_text().strip()
    require(digest(parent, 40))
    event = read_json_file(Path(os.environ['GITHUB_EVENT_PATH']), 1024 * 1024)
    require(event.get('before') == parent and event.get('after') == child)
    parents = subprocess.check_output(
        ['git', '-C', str(ROOT), 'rev-list', '--parents', '-n', '1', child],
        text=True, timeout=30).split()
    changed = subprocess.check_output(
        ['git', '-C', str(ROOT), 'diff', '--name-only', parent, child],
        text=True, timeout=30).splitlines()
    require(parents == [child, parent] and changed == [ACTIVATION.as_posix()]
            and marker.read_bytes() == (parent + '\n').encode()
            and not subprocess.check_output(
                ['git', '-C', str(ROOT), 'status', '--porcelain'],
                text=True, timeout=30).strip())


def api(path):
    result = subprocess.run(['gh', 'api', REPO_API + path], stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, timeout=60, check=False)
    require(result.returncode == 0 and 0 < len(result.stdout) <= 20 * 1024 * 1024)
    return strict_json(result.stdout, 20 * 1024 * 1024)


def validate_run(run, jobs):
    checkpoint('run')
    require(type(run) is dict and run.get('id') == RUN_ID
            and run.get('run_attempt') == RUN_ATTEMPT and run.get('head_sha') == RUN_HEAD
            and run.get('head_branch') == 'codex/qualification-dispatch-20261010'
            and run.get('path') == WORKFLOW and run.get('event') == 'push'
            and run.get('status') == 'completed' and run.get('conclusion') == 'failure'
            and run.get('repository', {}).get('full_name') == REPOSITORY)
    checkpoint('jobs')
    require(type(jobs) is dict and jobs.get('total_count') == 1
            and type(jobs.get('jobs')) is list and len(jobs['jobs']) == 1)
    job = jobs['jobs'][0]
    require(job.get('name') == 'native' and job.get('status') == 'completed'
            and job.get('conclusion') == 'failure')
    steps = {step.get('name'): step.get('conclusion') for step in job.get('steps', [])
             if type(step) is dict and type(step.get('name')) is str}
    require(steps.get('Verify reviewed single-file activation and pinned source') == 'success'
            and steps.get('Fetch and verify retained ISO archive and actual image bytes') == 'success'
            and steps.get('Native live and encrypted offline installed acceptance') == 'failure'
            and steps.get('Screen bounded diagnostic files before upload') == 'success'
            and steps.get('Run actions/upload-artifact@v4') == 'success')


def validate_artifact(value):
    checkpoint('artifact-metadata')
    require(type(value) is dict and value.get('id') == ARTIFACT_ID
            and value.get('name') == ARTIFACT_NAME and value.get('expired') is False
            and value.get('size_in_bytes') == ARTIFACT_BYTES
            and value.get('digest') == 'sha256:' + ARTIFACT_SHA256
            and value.get('workflow_run', {}).get('id') == RUN_ID
            and value.get('workflow_run', {}).get('head_sha') == RUN_HEAD)


def download(target):
    checkpoint('download')
    require(not target.exists())
    with target.open('xb') as output:
        result = subprocess.run(
            ['gh', 'api', REPO_API + '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip'],
            stdout=output, stderr=subprocess.PIPE, timeout=180, check=False)
    require(result.returncode == 0 and target.stat().st_size == ARTIFACT_BYTES)
    with target.open('rb') as source:
        calculated = hashlib.file_digest(source, 'sha256').hexdigest()
    require(calculated == ARTIFACT_SHA256)


def fixed_members(archive):
    checkpoint('archive')
    if type(archive) is not zipfile.ZipFile:
        archive_reject('archive', 'type')
    if len(archive.infolist()) > 1002:
        archive_reject('archive', 'size')
    result = {}
    for role, (name, maximum) in MEMBERS.items():
        matches = [item for item in archive.infolist() if item.filename == name]
        if len(matches) > 1:
            archive_reject(role, 'duplicate')
        if not matches:
            if role not in OPTIONAL_MEMBERS:
                archive_reject(role, 'missing-required')
            continue
        item = matches[0]
        mode = item.external_attr >> 16
        if item.is_dir() or stat.S_IFMT(mode) not in (0, stat.S_IFREG):
            archive_reject(role, 'type')
        if item.flag_bits & 0x1:
            archive_reject(role, 'encryption')
        if item.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
            archive_reject(role, 'compression')
        if not (0 <= item.file_size <= maximum and 0 <= item.compress_size <= ARTIFACT_BYTES):
            archive_reject(role, 'size')
        try:
            raw = archive.read(item)
        except (zipfile.BadZipFile, zlib.error):
            archive_reject(role, 'crc')
        except (OSError, RuntimeError, ValueError):
            archive_reject(role, 'read')
        if len(raw) != item.file_size:
            archive_reject(role, 'read')
        result[role] = raw
    return result


def screening_record(screening, name, raw):
    require(type(screening) is dict and screening.get('scope') ==
            'Owned synthetic QEMU VM only; no host desktop, VM disks or credentials')
    files = screening.get('files')
    require(type(files) is dict)
    record = files.get(name)
    require(type(record) is dict and set(record) ==
            {'original_sha256', 'uploaded_sha256', 'bytes', 'redactions'}
            and digest(record['original_sha256']) and digest(record['uploaded_sha256'])
            and record['uploaded_sha256'] == sha256(raw) and record['bytes'] == len(raw)
            and type(record['redactions']) is int and 0 <= record['redactions'] <= 100000)
    return record


def validate_screening(raws):
    checkpoint('screening')
    screening = strict_json(raws['screening'], MEMBERS['screening'][1])
    records = {}
    for role in raws:
        if role == 'screening':
            continue
        records[role] = screening_record(screening, MEMBERS[role][0], raws[role])
    if 'stop' in records:
        require(records['stop']['redactions'] == 0
                and records['stop']['original_sha256'] == records['stop']['uploaded_sha256'])
    return records


def validate_execution(raw, qualification, stop_raw, pins=None):
    checkpoint('execution')
    value = strict_json(raw, MEMBERS['execution'][1])
    image = qualification['image']
    pins = pins or load_source_provenance(qualification)
    require(type(value) is dict and value.get('status') == 'failed_or_unrun'
            and value.get('release_acceptance') is False
            and value.get('candidate_iso_source') == image['source_sha']
            and value.get('execution_checker_head') == RUN_HEAD
            and value.get('iso_bytes') == image['bytes']
            and value.get('iso_sha256') == image['sha256']
            and value.get('source_image_run') == image['run_id'])
    checker = value.get('checker')
    require(type(checker) is dict and checker.get('method') == 'native-functional'
            and checker.get('checker_sha256') == pins['checker_sha256']
            and checker.get('native_source_sha256') == pins['native_source_sha256']
            and checker.get('release_acceptance') is False)
    error = value.get('error')
    require(type(error) is str and len(error.encode('utf-8')) <= 8192
            and '\r' not in error and '\n' not in error
            and re.search(r'(?:^|; )harness: Native command failed \(91\); '
                          r'see native-harness\.log(?:; |$)', error) is not None)
    evidence = value.get('harness_evidence')
    require(type(evidence) is dict)
    key = 'native-stop-install.json'
    if stop_raw is not None:
        receipt = evidence.get(key)
        require(type(receipt) is dict and set(receipt) ==
                {'bytes', 'sha256', 'private_original', 'release_acceptance'}
                and receipt['bytes'] == len(stop_raw) and receipt['sha256'] == sha256(stop_raw)
                and receipt['private_original'] is True
                and receipt['release_acceptance'] is False)
        retention = 'retained'
    elif key not in evidence:
        retention = 'not-recorded'
    else:
        receipt = evidence[key]
        require(type(receipt) is dict and receipt == {
            'retained': False, 'reason': 'closed-record-rejected',
            'release_acceptance': False})
        retention = 'closed-record-rejected'
    return 91, retention


def validate_stop(raw):
    checkpoint('stop')
    value = strict_json(raw, MEMBERS['stop'][1])
    fields = {'schema', 'phase', 'qemu_returncode', 'elapsed_seconds', 'deadline_seconds',
              'deadline_reached', 'exit_marker_present', 'reason', 'release_acceptance'}
    require(type(value) is dict and set(value) == fields
            and value['schema'] == 'arctic-native-harness-stop-v1'
            and value['phase'] == 'install' and value['deadline_seconds'] == 2400
            and type(value['deadline_reached']) is bool
            and value['exit_marker_present'] is False
            and value['release_acceptance'] is False)
    code, elapsed, deadline = (value['qemu_returncode'], value['elapsed_seconds'],
                               value['deadline_seconds'])
    require((code is None or type(code) is int and -255 <= code <= 255)
            and type(elapsed) in (int, float) and math.isfinite(elapsed)
            and 0 <= elapsed <= 10800
            and value['deadline_reached'] == (elapsed >= deadline))
    reason = ('process-exited' if code is not None else
              'deadline-expired' if elapsed >= deadline else 'exit-marker-missing')
    require(value['reason'] == reason)
    return {
        'present': True,
        'retention': 'retained',
        'phase': 'install',
        'qemu_returncode_present': code is not None,
        'qemu_returncode': code if code is not None else 0,
        'elapsed_seconds': round(float(elapsed), 3),
        'deadline_seconds': deadline,
        'deadline_reached': value['deadline_reached'],
        'exit_marker_present': False,
        'reason': reason,
    }


def load_validator(expected):
    path = ROOT / VALIDATOR
    require(sha256(path.read_bytes()) == expected)
    spec = importlib.util.spec_from_file_location('native_screen_evidence_for_reader', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_harness(raw, validator):
    checkpoint('harness')
    diagnostics = io.StringIO()
    with contextlib.redirect_stdout(diagnostics):
        checked = validator.external_text(raw)
    require(checked is raw and diagnostics.getvalue() == '')
    text = raw.decode('utf-8', errors='strict')
    text = validator.TERMINAL.sub('', text)
    require('\x1b' not in text)
    lines = text.splitlines()
    finished = []
    timed_out = 0
    stage_codes = []
    for line in lines:
        match = re.fullmatch(r'\[ *[0-9]{1,6}s\] install finished after '
                             r'([0-9]{1,6})s: exit (None|[0-9]{1,3})', line)
        if match:
            finished.append((int(match[1]), match[2]))
        if re.fullmatch(r'\[ *[0-9]{1,6}s\] install timed out', line):
            timed_out += 1
        match = re.fullmatch(r'\[ *[0-9]{1,6}s\] install stage: exit ([0-9]{1,3})', line)
        if match:
            stage_codes.append(int(match[1]))
    require(len(finished) == 1 and finished[0][1] == 'None'
            and timed_out == 1 and stage_codes == [91])
    return {
        'bytes': len(raw),
        'install_finished_line_present': True,
        'install_elapsed_seconds': finished[0][0],
        'install_exit_marker': 'missing',
        'install_timed_out_line_present': True,
        'install_stage_exit_code': 91,
    }


def validate_stage_log(raw, validator):
    """Project only fixed vmtest lifecycle records; never return a log line."""
    diagnostics = io.StringIO()
    with contextlib.redirect_stdout(diagnostics):
        checked = validator.external_text(raw)
    require(checked is raw and diagnostics.getvalue() == '')
    text = validator.TERMINAL.sub('', raw.decode('utf-8', errors='strict'))
    require('\x1b' not in text)
    events = []
    for line in text.splitlines():
        match = re.fullmatch(r'\[ *[0-9]{1,6}s\] (.+)', line)
        if not match:
            continue
        message = match[1]
        families = (
            (r'boot menu on screen: install-01-boot-menu\.png', 'boot-menu'),
            (r"selected 'Try Arctic Linux' with the journal on the serial port", 'live-selected'),
            (r'live session started after [0-9]{1,6}s', 'live-session'),
            (r"no 'live session mode' line in the serial log; trying the terminal anyway", 'live-unobserved'),
            (r'run\.sh started \(attempt [123]\)', 'guest-driver-started'),
            (r'run\.sh did not start \(attempt [123]\)', 'guest-driver-unobserved'),
            (r'owned native launcher failed; no retry', 'launcher-failed'),
            (r'install finished after [0-9]{1,6}s: exit (?:None|[0-9]{1,3})', 'install-finished'),
            (r'install timed out', 'missing-exit-marker'),
            (r'install stage: exit [0-9]{1,3}', 'install-stage-exit'),
        )
        for pattern, family in families:
            if re.fullmatch(pattern, message):
                events.append(family)
                break
    require(len(events) <= 128)
    return {'present': True, 'bytes': len(raw), 'recognized_events': len(events),
            'last_recognized_event': events[-1] if events else 'none'}


def validate_qemu(raw, validator):
    """Classify bounded QEMU stderr using a finite family vocabulary."""
    diagnostics = io.StringIO()
    with contextlib.redirect_stdout(diagnostics):
        checked = validator.external_text(raw)
    require(checked is raw and diagnostics.getvalue() == '')
    text = validator.TERMINAL.sub('', raw.decode('utf-8', errors='strict'))
    require('\x1b' not in text)
    families = set()
    for line in text.splitlines():
        lower = line.lower()
        if re.fullmatch(r'qemu-system-x86_64: terminating on signal [0-9]{1,3} from pid [0-9]{1,10}(?: \([^\r\n]{1,128}\))?', line):
            families.add('signal-termination')
        elif 'kvm' in lower and any(word in lower for word in ('error', 'failed', "doesn't support")):
            families.add('kvm-error')
        elif 'assert' in lower or 'aborted' in lower:
            families.add('assertion-or-abort')
        elif any(word in lower for word in ('input/output error', 'i/o error', 'no space left')):
            families.add('storage-io-error')
        elif 'audio' in lower and any(word in lower for word in ('error', 'failed', 'invalid')):
            families.add('audio-error')
        elif any(word in lower for word in ('display', 'egl', 'opengl')) and any(
                word in lower for word in ('error', 'failed', 'invalid')):
            families.add('display-error')
    if raw and not families:
        families.add('unclassified')
    return {'present': True, 'bytes': len(raw), 'nonempty': bool(raw),
            'families': sorted(families)}


def validate_display(raw, controller_sha256):
    value = strict_json(raw, MEMBERS['display'][1])
    require(type(value) is dict and value.get('schema') == 'arctic-qemu-taskbar-display-v1'
            and value.get('status') == 'uiinfo_applied_pending_guest_two_output_evidence'
            and type(value.get('qemu_pid')) is int and value['qemu_pid'] > 1
            and value.get('qemu_uid') == 0 and value.get('gpu_id') == 'arctic_taskbar_gpu'
            and type(value.get('bus_pid')) is int and value['bus_pid'] > 1
            and type(value.get('bus_owner')) is str
            and re.fullmatch(r':[0-9]+\.[0-9]+', value['bus_owner']) is not None
            and value.get('display_backend') == 'dbus'
            and value.get('guest_monitor_verification_required') is True
            and digest(controller_sha256)
            and value.get('controller_sha256') == controller_sha256)
    heads = value.get('heads')
    require(type(heads) is list and len(heads) == 2)
    projected = []
    console_ids = set()
    addresses = set()
    for head in heads:
        require(type(head) is dict
                and set(head) == {'console_id', 'head', 'device_address', 'width_mm',
                                  'height_mm', 'xoff', 'yoff', 'width', 'height'}
                and type(head['console_id']) is int and head['console_id'] >= 0
                and head['head'] in (0, 1)
                and type(head['device_address']) is str
                and re.fullmatch(r'pci/0000/[0-9a-f]{2}\.[0-7]', head['device_address'])
                and head['width_mm'] == 340 and head['height_mm'] == 190
                and head['xoff'] == head['head'] * 1280 and head['yoff'] == 0
                and head['width'] == 1280 and head['height'] == 720)
        projected.append(head['head'])
        require(head['console_id'] not in console_ids)
        console_ids.add(head['console_id'])
        addresses.add(head['device_address'])
    require(sorted(projected) == [0, 1] and len(console_ids) == 2 and len(addresses) == 1)
    return {'present': True, 'status': 'uiinfo-applied', 'heads': 2, 'geometry': '2560x720',
            'guest_monitor_verification_required': True}


def png_dimensions(raw):
    """Validate one bounded, complete non-interlaced RGB(A) PNG."""
    require(type(raw) is bytes and 57 <= len(raw) <= 4 * 1024 * 1024
            and raw[:8] == b'\x89PNG\r\n\x1a\n')
    offset, chunks, ihdr, idat, ended, phase = 8, 0, None, bytearray(), False, 'header'
    ancillary = {b'cHRM', b'gAMA', b'iCCP', b'sRGB', b'pHYs', b'tEXt', b'zTXt',
                 b'iTXt', b'eXIf', b'tIME'}
    while offset < len(raw):
        require(not ended and chunks < 4096 and offset + 12 <= len(raw))
        length = int.from_bytes(raw[offset:offset + 4], 'big')
        kind = raw[offset + 4:offset + 8]
        require(length <= 4 * 1024 * 1024 and re.fullmatch(b'[A-Za-z]{4}', kind) is not None)
        end = offset + 12 + length
        require(end <= len(raw))
        data = raw[offset + 8:offset + 8 + length]
        crc = int.from_bytes(raw[offset + 8 + length:end], 'big')
        require((zlib.crc32(kind + data) & 0xffffffff) == crc)
        if chunks == 0:
            require(kind == b'IHDR' and length == 13)
            width = int.from_bytes(data[:4], 'big'); height = int.from_bytes(data[4:8], 'big')
            require(0 < width <= 4096 and 0 < height <= 4096
                    and data[8] == 8 and data[9] in (2, 6)
                    and data[10:] == b'\x00\x00\x00')
            ihdr = (width, height, data[9])
            phase = 'before-idat'
        elif kind == b'IHDR':
            require(False)
        if kind == b'IDAT':
            require(ihdr is not None and phase in ('before-idat', 'idat')
                    and len(idat) + length <= 4 * 1024 * 1024)
            idat.extend(data)
            phase = 'idat'
        elif kind == b'IEND':
            require(length == 0 and ihdr is not None and idat
                    and phase in ('idat', 'after-idat'))
            ended = True
            phase = 'ended'
        elif kind != b'IHDR':
            require(kind in ancillary and phase in ('before-idat', 'idat', 'after-idat'))
            if phase == 'idat':
                phase = 'after-idat'
        offset = end; chunks += 1
    require(ended and offset == len(raw) and ihdr is not None)
    width, height, color = ihdr
    expected = (width * (3 if color == 2 else 4) + 1) * height
    inflater = zlib.decompressobj()
    pixels = inflater.decompress(bytes(idat), expected + 1)
    require(len(pixels) <= expected and not inflater.unconsumed_tail)
    pixels += inflater.flush(expected + 1 - len(pixels))
    require(len(pixels) == expected and inflater.eof and not inflater.unused_data
            and not inflater.unconsumed_tail)
    stride = width * (3 if color == 2 else 4) + 1
    require(all(pixels[row * stride] <= 4 for row in range(height)))
    return width, height


def validate_host_frame(raws, native_source_sha256):
    receipt_raw = raws.get('host_frame_receipt')
    image = raws.get('host_frame_image')
    if receipt_raw is None:
        require(image is None)
        return {'present': False}
    value = strict_json(receipt_raw, OPTIONAL_MEMBERS['host_frame_receipt'][1])
    require(type(value) is dict and value.get('schema') == 'arctic-native-host-frame-v1'
            and value.get('stage') == 'live' and value.get('release_acceptance') is False
            and value.get('product_change_authorized') is False
            and value.get('status') in ('captured', 'unknown'))
    if value['status'] == 'unknown':
        require(image is None and value.get('error') in
                ('json-error', 'filesystem-error', 'value-error', 'other-error'))
        return {'present': True, 'status': 'unknown', 'error_family': value['error']}
    capture = value.get('capture')
    require(type(capture) is dict and capture.get('path') == 'native-host-celluloid-live.png'
            and type(image) is bytes and capture.get('bytes') == len(image)
            and capture.get('sha256') == sha256(image)
            and capture.get('device') == 'arctic_taskbar_gpu'
            and capture.get('head') in (0, 1)
            and capture.get('physical_size') == [1280, 720]
            and capture.get('exported_crop') == [0, 0, 1280, 720]
            and png_dimensions(image) == (1280, 720))
    comparison = value.get('comparison')
    interpretations = {'host-matched-guest-unmatched': 'guest-screencopy-divergence-observed',
                       'host-and-guest-unmatched': 'vm-display-presentation-failure-observed'}
    require(comparison in interpretations and value.get('interpretation') == interpretations[comparison]
            and value.get('identical_palette_oracle') is True
            and value.get('same_paused_player_hold') == 20
            and digest(native_source_sha256)
            and value.get('native_oracle_source_sha256') == native_source_sha256)
    oracle = value.get('oracle')
    require(type(oracle) is dict and oracle.get('status') in ('matched', 'unmatched'))
    require(oracle['status'] == ('matched' if comparison == 'host-matched-guest-unmatched'
                                 else 'unmatched'))
    return {'present': True, 'status': 'captured', 'head': capture['head'],
            'comparison': comparison, 'interpretation': value['interpretation'],
            'oracle_status': oracle['status'], 'image_dimensions': [1280, 720]}


def inspect_archive(path, manifest, qualification):
    checkpoint('archive')
    if not path.is_file() or path.is_symlink():
        archive_reject('archive', 'type')
    if path.stat().st_size != ARTIFACT_BYTES:
        archive_reject('archive', 'size')
    try:
        with zipfile.ZipFile(path) as archive:
            raws = fixed_members(archive)
    except ArchiveReject:
        raise
    except zipfile.BadZipFile:
        archive_reject('archive', 'type')
    except (OSError, RuntimeError, ValueError):
        archive_reject('archive', 'read')
    records = validate_screening(raws)
    pins = load_source_provenance(qualification)
    require(digest(pins['taskbar_display_sha256']))
    runner_code, stop_retention = validate_execution(
        raws['execution'], qualification, raws.get('stop'), pins)
    stop = (validate_stop(raws['stop']) if 'stop' in raws
            else {'present': False, 'retention': stop_retention})
    validator = load_validator(manifest['validator_sha256'])
    harness = validate_harness(raws['harness'], validator)
    qemu = (validate_qemu(raws['qemu'], validator) if 'qemu' in raws
            else {'present': False})
    display = (validate_display(raws['display'], pins['taskbar_display_sha256'])
               if 'display' in raws else {'present': False})
    stage_logs = {}
    for role in ('stage_log', 'current_stage_log'):
        stage_logs[role] = (validate_stage_log(raws[role], validator) if role in raws
                            else {'present': False})
    host_frame = validate_host_frame(raws, pins['native_source_sha256'])
    checkpoint('projection')
    return {
        'schema': 'arctic-native-failure-safe-diagnostic-v1',
        'run_id': RUN_ID,
        'artifact_id': ARTIFACT_ID,
        'artifact_verified': True,
        'runner_failure_code': runner_code,
        'screened_log_redactions_present': records['harness']['redactions'] > 0,
        'stop': stop,
        'harness': harness,
        'qemu': qemu,
        'display': display,
        'stage_logs': stage_logs,
        'host_frame': host_frame,
        'release_acceptance': False,
    }


def emit(value, stream=None):
    stream = stream or os.sys.stdout
    require(type(value) is dict and value.get('schema') ==
            'arctic-native-failure-safe-diagnostic-v1'
            and value.get('release_acceptance') is False)
    stream.write('ARCTIC-NATIVE-SAFE-DIAGNOSTIC=' +
                 json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n')


def write_rejection(stage):
    if stage not in REJECTION_STAGES:
        stage = 'projection'
    output = os.environ.get('GITHUB_OUTPUT')
    if output:
        try:
            with open(output, 'a', encoding='utf-8') as stream:
                stream.write('rejection=' + stage + '\n')
        except OSError:
            pass
    suffix = (':' + ARCHIVE_ROLE + ':' + ARCHIVE_REASON) if stage == 'archive' else ''
    print('ARCTIC-NATIVE-READER-REJECTION=' + stage + suffix, flush=True)


def run(manifest_path):
    activation_guard()
    checkpoint('manifest')
    manifest, qualification = validate_manifest(read_json_file(manifest_path, 32768))
    validate_run(api('/actions/runs/' + str(RUN_ID)),
                 api('/actions/runs/' + str(RUN_ID) + '/jobs?per_page=100'))
    artifact = api('/actions/artifacts/' + str(ARTIFACT_ID))
    validate_artifact(artifact)
    with tempfile.TemporaryDirectory(prefix='arctic-native-safe-reader-') as temp:
        archive = Path(temp) / 'exact-artifact.zip'
        download(archive)
        result = inspect_archive(archive, manifest, qualification)
    emit(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    args = parser.parse_args()
    try:
        run(args.manifest)
    except Exception:
        write_rejection(REJECTION_STAGE)
        raise SystemExit(1)


if __name__ == '__main__':
    main()
