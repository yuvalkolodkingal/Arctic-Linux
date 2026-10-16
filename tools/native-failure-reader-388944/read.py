#!/usr/bin/env python3
"""Read one exact failed Native artifact and emit only a closed diagnostic."""
import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import selectors
import stat
import subprocess
import tempfile
import time
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
REPO_API = 'repos/' + REPOSITORY
WORKFLOW = '.github/workflows/native-candidate-20261008.yml'
PRODUCER_WORKFLOW = Path(WORKFLOW)
READER_WORKFLOW = Path('.github/workflows/read-native-failure-388944.yml')
BRANCH = 'codex/read-native-failure-388944-20261016'
ACTIVATION = Path('.github/native-failure-reader-388944.activate')
READER = Path('tools/native-failure-reader-388944/read.py')
VALIDATOR = Path('tools/native-functional/screen-evidence.py')
QUALIFICATION = Path('tools/native-failure-reader-388944/qualification-execution-manifest.json')
SOURCE_PROVENANCE = Path('tools/native-functional/source-provenance.json')
RUN_ID = 38894423903
RUN_ATTEMPT = 1
RUN_HEAD = 'cc1b00d297817399b60beb37aba2c275d9456144'
JOB_ID = 116951373862
ACTION_RESOLUTIONS = {
    'actions/checkout': '11d5960a326750d5838078e36cf38b85af677262',
    'actions/upload-artifact': 'ea165f8d65b6e75b540449e92b4886f43607fa02',
}
JOB_LOG_MAX = 32 * 1024 * 1024
API_JSON_MAX = 20 * 1024 * 1024
COMMAND_STDOUT_MAX = 512 * 1024 * 1024
ARTIFACT_ID = 12044990488
ARTIFACT_NAME = 'native-candidate-qualification'
ARTIFACT_BYTES = 47945673
ARTIFACT_SHA256 = '3d9cf44af41bf01b3b5e836548bccff0bb8ea2cc7824f6b1412371f456d1a40c'
REQUIRED_MEMBERS = {
    'screening': ('upload-screening.json', 1024 * 1024),
    'execution': ('execution.json', 1024 * 1024),
    'harness': ('native-harness.log', 16 * 1024 * 1024),
    'native_stages': ('native-stages.json', 32 * 1024 * 1024),
    'taskbar_prefix': ('harness/taskbar-boot.log.bounded-prefix.bin', 64 * 1024),
}
OPTIONAL_MEMBERS = {
    'serial_boot': ('harness/serial-boot.log', 128 * 1024 * 1024),
}
MEMBERS = REQUIRED_MEMBERS | OPTIONAL_MEMBERS
MANIFEST_FIELDS = {'schema', 'ready', 'repository', 'workflow', 'reader_workflow', 'branch',
                   'run_id', 'run_attempt', 'run_head', 'artifact', 'reader_sha256',
                   'validator_sha256', 'qualification_manifest_sha256',
                   'reader_workflow_sha256', 'job_id', 'producer_actions'}
ARTIFACT_FIELDS = {'id', 'name', 'bytes', 'sha256'}
REJECTION_STAGES = {'activation', 'manifest', 'run', 'jobs', 'artifact-metadata',
                    'producer-actions', 'download', 'archive', 'screening', 'execution',
                    'harness', 'native-stages', 'taskbar-prefix', 'serial-boot',
                    'projection'}
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
    require(value['schema'] == 'arctic-native-failure-reader-v1'
            and value['ready'] is True and value['repository'] == REPOSITORY
            and value['workflow'] == WORKFLOW
            and value['reader_workflow'] == READER_WORKFLOW.as_posix()
            and value['branch'] == BRANCH and value['run_id'] == RUN_ID
            and value['run_attempt'] == RUN_ATTEMPT and value['run_head'] == RUN_HEAD
            and value['job_id'] == JOB_ID
            and value['producer_actions'] == ACTION_RESOLUTIONS)
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
    execution_files = qualification.get('execution_files', {})
    producer = ROOT / PRODUCER_WORKFLOW
    require(digest(execution_files.get(PRODUCER_WORKFLOW.as_posix()))
            and producer.is_file() and not producer.is_symlink()
            and sha256(producer.read_bytes()) == execution_files[PRODUCER_WORKFLOW.as_posix()])
    producer_text = producer.read_text(encoding='utf-8')
    require(producer_text.count('uses: actions/checkout@v4') == 2
            and producer_text.count('uses: actions/upload-artifact@v4') == 1)
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
            'native_source_sha256': value['native_source_sha256']}


def activation_guard():
    checkpoint('activation')
    require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_WORKFLOW') ==
                'Read safe Native diagnostics for run 38894423903'
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


def api_endpoint(endpoint):
    require(type(endpoint) is str and re.fullmatch(r'[A-Za-z0-9_./?=&-]{1,256}', endpoint))
    with tempfile.TemporaryDirectory(prefix='arctic-native-api-') as temp:
        target = Path(temp) / 'response.json'
        bounded_command_to_file(['gh', 'api', endpoint], target, API_JSON_MAX, 60)
        return strict_json(target.read_bytes(), API_JSON_MAX)


def api(path):
    require(type(path) is str and path.startswith('/'))
    return api_endpoint(REPO_API + path)


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
    require(job.get('id') == JOB_ID and job.get('run_id') == RUN_ID
            and job.get('run_attempt') == RUN_ATTEMPT
            and job.get('head_sha') == RUN_HEAD
            and job.get('name') == 'native' and job.get('status') == 'completed'
            and job.get('conclusion') == 'failure')
    steps = [(step.get('name'), step.get('conclusion')) for step in job.get('steps', [])
             if type(step) is dict and type(step.get('name')) is str]
    require(steps.count(('Run actions/checkout@v4', 'success')) == 2
            and steps.count(('Post Run actions/checkout@v4', 'success')) == 2
            and steps.count(('Run actions/upload-artifact@v4', 'success')) == 1
            and ('Verify reviewed single-file activation and pinned source', 'success') in steps
            and ('Fetch and verify retained ISO archive and actual image bytes', 'success') in steps
            and ('Native live and encrypted offline installed acceptance', 'failure') in steps
            and ('Screen bounded diagnostic files before upload', 'success') in steps)


def bounded_command_to_file(argv, target, maximum, timeout_seconds=180):
    """Capture a fixed command without allowing stdout or stderr to grow unbounded."""
    require(type(argv) is list and argv and all(type(item) is str for item in argv)
            and not target.exists() and 0 < maximum <= COMMAND_STDOUT_MAX
            and type(timeout_seconds) is int and 1 <= timeout_seconds <= 300)
    process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, close_fds=True)
    selector = selectors.DefaultSelector()
    stdout_bytes = stderr_bytes = 0
    try:
        for stream, role in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, role)
        deadline = time.monotonic() + timeout_seconds
        with target.open('xb') as output:
            while selector.get_map():
                require(time.monotonic() < deadline)
                events = selector.select(timeout=min(0.25, max(0, deadline-time.monotonic())))
                if not events:
                    continue
                for key, _ in events:
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if key.data == 'stdout':
                        stdout_bytes += len(chunk)
                        require(stdout_bytes <= maximum)
                        output.write(chunk)
                    else:
                        stderr_bytes += len(chunk)
                        require(stderr_bytes <= 64 * 1024)
        require(process.wait(timeout=5) == 0 and 0 < stdout_bytes <= maximum)
    except BaseException:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        raise
    finally:
        selector.close()
        for stream in (process.stdout, process.stderr):
            stream.close()
    return stdout_bytes


def download_job_log(target):
    checkpoint('producer-actions')
    return bounded_command_to_file(
        ['gh', 'api', REPO_API + '/actions/jobs/' + str(JOB_ID) + '/logs'],
        target, JOB_LOG_MAX)


def validate_action_resolution(raw):
    """Verify only fixed runner action-resolution records from the exact job log."""
    checkpoint('producer-actions')
    require(type(raw) is bytes and 0 < len(raw) <= JOB_LOG_MAX and b'\x00' not in raw)
    text = raw.decode('utf-8-sig', errors='strict')
    prefix = re.compile(r"(?:\ufeff)?[0-9]{4}-[0-9]{2}-[0-9]{2}T"
                        r"[0-9]{2}:[0-9]{2}:[0-9]{2}\.[0-9]+Z "
                        r"Download action repository '([^']+)' \(SHA:([0-9a-f]{40})\)")
    observed = []
    for line in text.splitlines():
        if 'Download action repository ' not in line:
            continue
        match = prefix.fullmatch(line)
        require(match is not None)
        observed.append((match.group(1), match.group(2)))
    expected = [(name + '@v4', sha) for name, sha in ACTION_RESOLUTIONS.items()]
    require(observed == expected)
    return True


def validate_action_commits():
    checkpoint('producer-actions')
    for name, expected in ACTION_RESOLUTIONS.items():
        repository = name.split('/', 1)[1]
        value = api_endpoint('repos/actions/' + repository + '/git/commits/' + expected)
        require(type(value) is dict and value.get('sha') == expected)
    return True


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
    captured = bounded_command_to_file(
        ['gh', 'api', REPO_API + '/actions/artifacts/' + str(ARTIFACT_ID) + '/zip'],
        target, ARTIFACT_BYTES, 180)
    require(captured == ARTIFACT_BYTES and target.stat().st_size == ARTIFACT_BYTES)
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
    return records


def validate_execution(raw, qualification, taskbar_raw, pins=None):
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
    require(error == ('harness: Native command failed (1); see native-harness.log; '
                      'native stages: installed harness: Missing/duplicate/nonzero '
                      'ARCTIC-INSTALLED-SMOKE-EXIT; taskbar: '
                      'missing/extra/duplicate/reordered taskbar records'))
    evidence = value.get('harness_evidence')
    require(type(evidence) is dict)
    taskbar_receipt = evidence.get('taskbar-boot.log.bounded-prefix.bin')
    require(type(taskbar_receipt) is dict and set(taskbar_receipt) ==
            {'bytes', 'sha256', 'original_bytes', 'original_sha256'}
            and taskbar_receipt['bytes'] == len(taskbar_raw)
            and taskbar_receipt['sha256'] == sha256(taskbar_raw)
            and type(taskbar_receipt['original_bytes']) is int
            and len(taskbar_raw) <= taskbar_receipt['original_bytes'] <= 210 * 1024 * 1024
            and digest(taskbar_receipt['original_sha256']))
    return 1


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
    require(len(finished) == 1 and finished[0][1] == '1'
            and timed_out == 0 and stage_codes == [1])
    return {
        'bytes': len(raw),
        'install_finished_line_present': True,
        'install_elapsed_seconds': finished[0][0],
        'install_exit_marker': 'nonzero',
        'install_timed_out_line_present': False,
        'install_stage_exit_code': 1,
    }


def validate_native_stages(raw):
    """Project only stage completion and the one already-public fixed failure."""
    checkpoint('native-stages')
    value = strict_json(raw, MEMBERS['native_stages'][1])
    require(type(value) is dict and set(value) ==
            {'results', 'errors', 'release_acceptance'}
            and value['release_acceptance'] is False
            and value['errors'] == [
                'installed harness: Missing/duplicate/nonzero ARCTIC-INSTALLED-SMOKE-EXIT'])
    results = value['results']
    require(type(results) is dict and set(results) == {'live', 'installed'})
    projected = {}
    for stage in ('live', 'installed'):
        result = results[stage]
        require(type(result) is dict
                and result.get('stage') == stage
                and result.get('status') == 'limited-smoke-passed'
                and result.get('release_acceptance') is False
                and type(result.get('files')) is dict
                and type(result.get('provenance')) is dict)
        projected[stage] = 'passed'
    return {'present': True, 'results': projected,
            'installed_smoke_exit_validation': 'missing-duplicate-or-nonzero'}


TASKBAR_KINDS = ('BEGIN', 'PROVENANCE', 'REPORT', 'EVIDENCE-CHUNK',
                 'EVIDENCE-MANIFEST', 'END')


def validate_taskbar_prefix(raw):
    """Classify the retained 64 KiB prefix without exposing any payload byte."""
    checkpoint('taskbar-prefix')
    require(type(raw) is bytes and len(raw) <= MEMBERS['taskbar_prefix'][1]
            and b'\x00' not in raw and b'\r' not in raw)
    try:
        text = raw.decode('ascii', errors='strict')
    except UnicodeDecodeError:
        require(False)
    records = []
    lines = text.splitlines(keepends=True)
    partial = 'none'
    for index, line in enumerate(lines):
        complete = line.endswith('\n')
        body = line[:-1] if complete else line
        match = re.match(r'^ARCTIC-TASKBAR-([A-Z-]+) ', body)
        require(match is not None and match.group(1) in TASKBAR_KINDS)
        kind = match.group(1)
        if complete:
            require(len(body.encode('ascii')) <= 4 * 1024 * 1024 + 256)
            records.append(kind)
        else:
            require(index == len(lines) - 1)
            partial = kind
    require(len(records) <= 64 and (not raw or lines))
    expected = ['BEGIN', 'PROVENANCE', 'REPORT']
    require(records[:min(3, len(records))] == expected[:min(3, len(records))])
    phase = 'header' if len(records) < 3 else 'chunks'
    if len(records) >= 3:
        for kind in records[3:]:
            if phase == 'chunks' and kind == 'EVIDENCE-CHUNK':
                continue
            if phase == 'chunks' and kind == 'EVIDENCE-MANIFEST':
                phase = 'manifest'
                continue
            if phase == 'manifest' and kind == 'END':
                phase = 'end'
                continue
            require(False)
    if partial != 'none':
        if phase == 'header':
            allowed = {expected[len(records)]}
        elif phase == 'chunks':
            allowed = {'EVIDENCE-CHUNK', 'EVIDENCE-MANIFEST'}
        elif phase == 'manifest':
            allowed = {'END'}
        else:
            allowed = set()
        require(partial in allowed)
    return {'bytes': len(raw), 'nonempty': bool(raw),
            'complete_record_kinds': records, 'partial_record_kind': partial}


def validate_serial_boot(raw, validator):
    """Count only fixed protocol records in the screened installed UART."""
    checkpoint('serial-boot')
    diagnostics = io.StringIO()
    with contextlib.redirect_stdout(diagnostics):
        checked = validator.external_text(raw)
    require(checked is raw and diagnostics.getvalue() == '')
    text = validator.TERMINAL.sub('', raw.decode('utf-8', errors='strict'))
    require('\x1b' not in text)
    lines = text.splitlines()
    smoke = [line.split('=', 1)[1] for line in lines
             if line.startswith('ARCTIC-INSTALLED-SMOKE-EXIT=')]
    if not smoke:
        smoke_status = 'missing'
    elif len(smoke) != 1:
        smoke_status = 'ambiguous'
    elif smoke[0] == '0':
        smoke_status = 'zero'
    elif re.fullmatch(r'[0-9]{1,3}', smoke[0]) and int(smoke[0]) <= 255:
        smoke_status = 'nonzero'
    else:
        smoke_status = 'malformed'
    native_end = []
    collector_failures = []
    port_end = []
    for line in lines:
        if line.startswith('ARCTIC-NATIVE-RUNNER-END '):
            item = strict_json(line.split(' ', 1)[1].encode(), 16384)
            require(type(item) is dict and set(item) ==
                    {'stage', 'status', 'error', 'evidence_export_complete',
                     'release_acceptance'}
                    and item['stage'] == 'installed'
                    and item['status'] in ('passed', 'failed')
                    and type(item['evidence_export_complete']) is bool
                    and ((item['status'] == 'passed') == (item['error'] is None))
                    and item['release_acceptance'] is False)
            native_end.append(item['status'])
        elif line.startswith('ARCTIC-TASKBAR-COLLECTOR-ERROR '):
            item = strict_json(line.split(' ', 1)[1].encode(), 4096)
            require(type(item) is dict and set(item) ==
                    {'schema', 'stage', 'status', 'release_acceptance'}
                    and item['schema'] == 'arctic-taskbar-preflight-v1'
                    and item['stage'] in {
                        'runtime-path', 'runtime-authorization', 'context',
                        'bundle-taskbar', 'bundle-runtime', 'bundle-native',
                        'bundle-pointer', 'bundle-capture', 'helpers', 'guest-guard',
                        'desktop', 'account', 'session', 'session-type',
                        'session-active', 'session-user', 'boot-id', 'port-alias',
                        'port-metadata', 'port-identity', 'port-open', 'port-device',
                        'begin-write', 'provenance-write'}
                    and item['status'] == 'failed'
                    and item['release_acceptance'] is False)
            collector_failures.append(item['stage'])
        elif line.startswith('ARCTIC-TASKBAR-PORT-END '):
            # Its payload contains per-run identity. Count it without publishing it.
            require(len(line.encode('utf-8')) <= 16384)
            port_end.append('present')
    require(len(native_end) <= 1 and len(collector_failures) <= 1 and len(port_end) <= 1)
    return {'present': True, 'bytes': len(raw),
            'collect_begin_count': lines.count('ARCTIC-COLLECT-BEGIN'),
            'collect_end_count': lines.count('ARCTIC-COLLECT-END'),
            'installed_smoke_exit': smoke_status,
            'native_end_statuses': native_end,
            'taskbar_preflight_failure_stages': collector_failures,
            'taskbar_port_end_count': len(port_end)}


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
    runner_code = validate_execution(
        raws['execution'], qualification, raws['taskbar_prefix'], pins)
    validator = load_validator(manifest['validator_sha256'])
    harness = validate_harness(raws['harness'], validator)
    native_stages = validate_native_stages(raws['native_stages'])
    taskbar_prefix = validate_taskbar_prefix(raws['taskbar_prefix'])
    serial_boot = (validate_serial_boot(raws['serial_boot'], validator)
                   if 'serial_boot' in raws else {'present': False})
    checkpoint('projection')
    return {
        'schema': 'arctic-native-failure-safe-diagnostic-v1',
        'run_id': RUN_ID,
        'artifact_id': ARTIFACT_ID,
        'artifact_verified': True,
        'runner_failure_code': runner_code,
        'screened_log_redactions_present': records['harness']['redactions'] > 0,
        'harness': harness,
        'native_stages': native_stages,
        'taskbar_prefix': taskbar_prefix,
        'serial_boot': serial_boot,
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
    validate_action_commits()
    with tempfile.TemporaryDirectory(prefix='arctic-native-safe-reader-') as temp:
        job_log = Path(temp) / 'exact-job.log'
        download_job_log(job_log)
        validate_action_resolution(job_log.read_bytes())
        artifact = api('/actions/artifacts/' + str(ARTIFACT_ID))
        validate_artifact(artifact)
        archive = Path(temp) / 'exact-artifact.zip'
        download(archive)
        result = inspect_archive(archive, manifest, qualification)
    result['producer_actions_verified'] = True
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
