#!/usr/bin/env python3
"""Static, read-only ABI evidence; never execute an extracted program."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import signal
import stat
import struct
import subprocess
import tempfile
import time
import uuid
import zipfile
from urllib.parse import urlsplit

REPO = 'yuvalkolodkingal/Arctic-Linux'
API = 'repos/' + REPO
BRANCH = 'codex/inspect-exact-image-mango-20261010'
WORKFLOW = '.github/workflows/inspect-exact-image-mango-20261010.yml'
MARKER = '.github/exact-image-mango-20261010.activate'
EXECUTION_FILES = {WORKFLOW, 'tools/exact-image-inspection/inspect.py',
                   'tools/native-functional/fetch-image.py'}
SOURCE_FILES = {'packaging/mangowm.spec', 'iso/kiwi/config.kiwi', '.github/workflows/iso.yml',
                'tools/build-iso.sh', 'packaging/patches/mango-client-geometry-events.patch',
                'packaging/patches/mango-software-renderer-dmabuf.patch',
                'packaging/patches/mango-output-teardown.patch'}
LIMIT = 31 * 1024 * 1024
FEDORA_BASE = 'docker.io/library/fedora@sha256:43b29f65a41eb9c35e1cd5323e3bdf3b655c2357a9f4f1ff2f9c2798e5045d80'
FEDORA_BASE_ID = 'sha256:ccb55df1d2413428166d80b08aa37a4bdcb61a63d09fff6f8abc0d561f311053'
EROFS_NEVRA = 'erofs-utils-1.9.4-1.fc44.x86_64'
XZ_NEVRA = 'xz-libs-1:5.8.2-2.fc44.x86_64'
WLROOTS_LIBRARY_PATH = r'/usr/lib64/libwlroots-0\.20\.so(?:\.[0-9]+)*'
READER = None
OUTPUT = None
ALLOWED = set()
REPORT = {'schema': 'arctic-exact-image-mango-static-v1', 'release_acceptance': False,
          'performance_acceptance': False, 'observer_profile_admitted': False,
          'scope': 'Static extraction only; no target execution, boot, benchmark or qualification',
          'status': 'failed_or_unrun', 'images': {}, 'tools': {}}

def require(condition, message):
    if not condition:
        raise ValueError(message)


def capture(argv, *, timeout=90, limit=2 * 1024 * 1024, allow_failure=False, include_stderr=False):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, env={**os.environ, 'LC_ALL': 'C'})
    require(len(result.stdout) <= limit and len(result.stderr) <= limit, 'Command output bound exceeded')
    if not allow_failure:
        require(result.returncode == 0, 'Static command failed: ' + Path(argv[0]).name)
    # Never copy API/transport stderr or temporary redirect URLs into evidence.
    data = result.stdout + (result.stderr if include_stderr else b'')
    return result.returncode, data.decode('utf-8', errors='strict')


def read_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'Duplicate JSON field')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON value')))


def api(path):
    return read_json(capture(['gh', 'api', API + path], limit=4 * 1024 * 1024)[1])


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def put(name, data):
    relative = PurePosixPath(name)
    require(re.fullmatch(r'[a-z0-9_./-]+', name) and not relative.is_absolute() and '..' not in relative.parts,
            'Unsafe evidence name')
    path = OUTPUT / name
    require(path.resolve().is_relative_to(OUTPUT.resolve()), 'Evidence output escapes its owned directory')
    require(sum((OUTPUT / p).stat().st_size for p in ALLOWED) + len(data) < LIMIT - 512 * 1024,
            'Small-artifact budget exceeded; partial static evidence only')
    path.parent.mkdir(parents=True, exist_ok=True)
    require(not path.exists() and not path.is_symlink(), 'Evidence output already exists')
    path.write_bytes(data)
    ALLOWED.add(name)
    return path


def write_report():
    path = OUTPUT / 'report.json'
    REPORT['files'] = {p: {'bytes': (OUTPUT / p).stat().st_size, 'sha256': sha(OUTPUT / p)}
                       for p in sorted(ALLOWED)}
    path.write_text(json.dumps(REPORT, sort_keys=True, indent=2) + '\n')


def safe_regular(root, relative):
    path = root / relative
    require(path.is_file() and not path.is_symlink(), 'Expected regular extracted file')
    require(path.resolve().is_relative_to(root.resolve()), 'Extracted symlink escape')
    return path


def reader_command(executable, mounts=(), *, name=None):
    require(READER is not None and re.fullmatch(r'sha256:[0-9a-f]{64}', READER), 'Prepared reader missing')
    command = ['docker', 'run', '--rm', '--network=none', '--read-only', '--cap-drop=ALL',
               '--security-opt=no-new-privileges', '--user', str(os.geteuid()) + ':' + str(os.getegid()),
               '--env', 'LC_ALL=C', '--entrypoint', executable]
    if name is not None:
        command += ['--name', name]
    for host, guest, readonly in mounts:
        require(',' not in str(host) and host.resolve().is_relative_to(Path(os.environ['RUNNER_TEMP']).resolve()),
                'Unsafe reader mount')
        command += ['--mount', 'type=bind,src=' + str(host) + ',dst=' + guest + (',readonly' if readonly else '')]
    return command + [READER]


def reader_capture(executable, arguments, mounts=(), **options):
    name = 'arctic-static-read-' + uuid.uuid4().hex
    try:
        return capture(reader_command(executable, mounts, name=name) + arguments, **options)
    finally:
        # Also stops a timed-out container; killing only the Docker client is insufficient.
        capture(['docker', 'rm', '-f', name], timeout=30, allow_failure=True)


def canonical_reader_digest(value):
    if not isinstance(value, str):
        return None
    repository, separator, digest = value.partition('@')
    if separator and repository in {'fedora', 'docker.io/library/fedora'} and digest == FEDORA_BASE.split('@')[1]:
        return FEDORA_BASE
    return None


def sanitized_pull_diagnostic(text):
    # This receipt is limited to a public, pinned Docker image pull. API/archive
    # stderr remains excluded. Strip credentials and every URL path/query.
    for name in ('GH_TOKEN', 'GITHUB_TOKEN'):
        token = os.environ.get(name)
        if token:
            text = text.replace(token, '<redacted>')
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    text = re.sub(r'\b(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)\b', '<redacted>', text)
    text = re.sub(r'(?i)\b(?:Bearer|Basic)\s+[^\s]+', '<redacted>', text)
    def public_host(match):
        try:
            parsed = urlsplit(match.group(0))
            return parsed.scheme + '://' + (parsed.hostname or '<url>')
        except ValueError:
            return '<url>'
    text = re.sub(r'https?://[^\s\"\'<>]+', public_host, text)
    text = re.sub(r'(?i)\b(?:token|access_token|refresh_token|signature|sig|credential|password|secret|authorization)\s*[:=]\s*[^\s,;]+', '<redacted>', text)
    return ''.join(character for character in text if character in '\n\t' or ord(character) >= 32)[:16000]


def pull_reader_base():
    receipt = {'image_reference': FEDORA_BASE, 'timeout_seconds': 600, 'status': 'unrun'}
    REPORT['tools']['reader_pull'] = receipt
    try:
        code, diagnostic = capture(['docker', 'pull', FEDORA_BASE], timeout=600,
            limit=256 * 1024, allow_failure=True, include_stderr=True)
    except subprocess.TimeoutExpired as error:
        receipt['status'] = 'timed_out'
        partial = []
        for value in (error.stdout, error.stderr):
            if value:
                partial.append(value.decode('utf-8', errors='replace') if isinstance(value, bytes) else value)
        receipt['diagnostic'] = sanitized_pull_diagnostic('\n'.join(partial))
        raise
    receipt.update(exit_code=code, status='passed' if code == 0 else 'failed',
                   diagnostic=sanitized_pull_diagnostic(diagnostic))
    require(code == 0, 'Pinned Docker Hub Fedora reader pull failed; see sanitized reader_pull receipt')


def prepare_reader():
    global READER
    pull_reader_base()
    metadata = json.loads(capture(['docker', 'image', 'inspect', FEDORA_BASE])[1])[0]
    matched_digests = [value for value in metadata['RepoDigests'] if canonical_reader_digest(value) == FEDORA_BASE]
    require(matched_digests and metadata['Id'] == FEDORA_BASE_ID, 'Official Docker Hub Fedora digest/config identity mismatch')
    name = 'arctic-static-erofs-' + uuid.uuid4().hex
    created = False
    try:
        capture(['docker', 'create', '--name', name, FEDORA_BASE, 'dnf', '-y',
                 '--setopt=gpgcheck=1', '--setopt=install_weak_deps=False', 'install', EROFS_NEVRA, XZ_NEVRA])
        created = True
        capture(['docker', 'start', '--attach', name], timeout=600, limit=4 * 1024 * 1024)
        require(capture(['docker', 'inspect', '--format', '{{.State.ExitCode}}', name])[1].strip() == '0',
                'Signed reader dependency installation failed')
        READER = capture(['docker', 'commit', name])[1].strip()
        require(re.fullmatch(r'sha256:[0-9a-f]{64}', READER), 'Invalid installed reader image identity')
    finally:
        if created:
            capture(['docker', 'rm', '-f', name], allow_failure=True)
    packages = reader_capture('/usr/bin/rpm', ['--noplugins', '-q', '--qf', '%{NEVRA}\n',
                                              'erofs-utils', 'xz-libs'])[1].splitlines()
    require(packages == [EROFS_NEVRA, XZ_NEVRA], 'Reader package pin mismatch')
    version = reader_capture('/usr/bin/fsck.erofs', ['-V'])[1]
    _, help_text = reader_capture('/usr/bin/fsck.erofs', ['--help'], include_stderr=True)
    require(re.search(r'\blzma\b', help_text, re.I) is not None and '--path=' in help_text,
            'Reader does not advertise required filtered LZMA support')
    REPORT['tools']['reader'] = {'base_repo_digest': FEDORA_BASE, 'base_image_id': metadata['Id'], 'observed_base_repo_digests': matched_digests,
        'prepared_image_id': READER, 'packages': packages, 'version': version, 'help': help_text,
        'dependency_installation': 'Official Fedora44 repositories, gpgcheck=1, exact erofs/xz NEVRAs',
        'extraction_isolation': 'Network none, root filesystem read-only, all capabilities dropped, no new privileges, actual runner UID/GID'}


def elf_sections(data):
    require(len(data) >= 64 and data[:6] == b'\x7fELF\x02\x01', 'Invalid ELF section inventory')
    offset = struct.unpack_from('<Q', data, 40)[0]
    entry_size, count, names_index = struct.unpack_from('<HHH', data, 58)
    require(entry_size == 64 and 1 <= count <= 256 and 0 < names_index < count
            and offset + count * entry_size <= len(data), 'Unsupported ELF section table')
    rows = [struct.unpack_from('<IIQQQQIIQQ', data, offset + index * 64) for index in range(count)]
    names = rows[names_index]
    require(names[1] == 3 and names[4] + names[5] <= len(data), 'Invalid ELF section names')
    strings = data[names[4]:names[4] + names[5]]
    result = {}
    for index, row in enumerate(rows):
        name_offset, kind, flags, address, file_offset, size, link, info, alignment, element_size = row
        require(name_offset < len(strings), 'Invalid ELF section name offset')
        end = strings.find(b'\0', name_offset)
        require(end >= name_offset, 'Unterminated ELF section name')
        name = strings[name_offset:end].decode('ascii', errors='strict')
        require(name not in result, 'Duplicate ELF section name')
        require(kind == 8 or file_offset + size <= len(data), 'ELF section exceeds file')
        result[name] = {'index': index, 'type': kind, 'flags': flags, 'address': address,
                        'file_offset': file_offset, 'bytes': size, 'link': link, 'info': info,
                        'alignment': alignment, 'entry_bytes': element_size,
                        'allocated': bool(flags & 2), 'executable': bool(flags & 4),
                        'sha256': None if kind == 8 else hashlib.sha256(data[file_offset:file_offset + size]).hexdigest()}
    return result


def fetch_module():
    path = Path(__file__).resolve().parents[1] / 'native-functional/fetch-image.py'
    # Execute the verified source directly, bypassing ignored stale bytecode.
    module = type(importlib.util)('exact_image_fetch')
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def validate_manifest(manifest):
    require(type(manifest) is dict and set(manifest) == {
        'schema', 'ready', 'release_acceptance', 'performance_acceptance',
        'observer_profile_admitted', 'image', 'source_files', 'execution_files'}, 'Manifest fields differ')
    require(manifest['schema'] == 'arctic-exact-image-mango-inspection-v1'
            and manifest['ready'] is True and manifest['release_acceptance'] is False
            and manifest['performance_acceptance'] is False and manifest['observer_profile_admitted'] is False,
            'Static inspection is disabled until exact image pins are reviewed; it cannot admit a profile')
    image = manifest['image']
    require(type(image) is dict and set(image) == {'source_sha', 'run_id', 'artifact_id', 'name',
        'bytes', 'sha256', 'archive_bytes', 'archive_sha256', 'producer_mode', 'producer_receipt_sha256'},
        'Exact external image pin fields differ')
    for key in ('run_id', 'artifact_id', 'bytes', 'archive_bytes'):
        require(type(image[key]) is int and image[key] > 0, 'Invalid image numeric identity')
    require(image['bytes'] < 2_000_000_000 and image['archive_bytes'] < 2_010_000_000,
            'Candidate or archive exceeds size limit')
    require(type(image['source_sha']) is str and re.fullmatch('[0-9a-f]{40}', image['source_sha']),
            'Invalid exact image source')
    for key in ('sha256', 'archive_sha256', 'producer_receipt_sha256'):
        require(type(image[key]) is str and re.fullmatch('[0-9a-f]{64}', image[key]), 'Invalid image checksum')
    require(image['name'] == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso"
            and image['producer_mode'] == 'frozen-external-paired-v1', 'Wrong first-attempt candidate identity')
    require(type(manifest['execution_files']) is dict and set(manifest['execution_files']) == EXECUTION_FILES
            and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                    for value in manifest['execution_files'].values()), 'Execution pin inventory differs')
    require(type(manifest['source_files']) is dict and set(manifest['source_files']) == SOURCE_FILES,
            'Source pin inventory differs')
    for pin in manifest['source_files'].values():
        require(type(pin) is dict and set(pin) == {'blob_sha', 'sha256', 'bytes', 'mode'}
                and type(pin['bytes']) is int and 0 < pin['bytes'] < 1_000_000
                and pin['mode'] in ('100644', '100755')
                and type(pin['blob_sha']) is str and re.fullmatch('[0-9a-f]{40}', pin['blob_sha'])
                and type(pin['sha256']) is str and re.fullmatch('[0-9a-f]{64}', pin['sha256']),
                'Invalid exact source blob pin')
    return image


def activation_guard(manifest, root):
    image = validate_manifest(manifest)  # Fail disabled before API access or extraction.
    require(os.environ.get('GITHUB_REPOSITORY') == REPO and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Requires the exact hosted first-attempt lane')
    event = read_json(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    head = capture(['git', '-C', str(root), 'rev-parse', 'HEAD'])[1].strip()
    parents = capture(['git', '-C', str(root), 'show', '-s', '--format=%P', 'HEAD'])[1].strip().split()
    require(len(parents) == 1 and re.fullmatch('[0-9a-f]{40}', parents[0]), 'Sole reviewed parent required')
    parent = parents[0]
    require(event['before'] == parent and event['after'] == os.environ['GITHUB_SHA'] == head,
            'Activation event differs from sole reviewed parent')
    require(capture(['git', '-C', str(root), 'diff', '--name-only', parent, head])[1].splitlines() == [MARKER],
            'Sole activation-marker child required')
    require(safe_regular(root, MARKER).read_bytes() == (parent + '\n').encode(), 'Activation marker differs')
    require(not capture(['git', '-C', str(root), 'status', '--porcelain'])[1].strip(), 'Clean checkout required')
    manifest_name = 'tools/exact-image-inspection/execution-manifest.json'
    raw_manifest = safe_regular(root, manifest_name).read_bytes()
    tracked_manifest = subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + manifest_name], timeout=60)
    require(raw_manifest == tracked_manifest and read_json(raw_manifest) == manifest,
            'Inspection manifest differs from its reviewed tracked blob')
    for name, expected in manifest['execution_files'].items():
        path = safe_regular(root, name)
        row = capture(['git', '-C', str(root), 'ls-tree', 'HEAD', '--', name])[1].strip().split()
        require(len(row) == 4 and row[0] in ('100644', '100755') and row[1] == 'blob',
                'Execution file is not one tracked regular blob')
        blob = subprocess.check_output(['git', '-C', str(root), 'show', 'HEAD:' + name], timeout=60)
        require(path.read_bytes() == blob and hashlib.sha256(blob).hexdigest() == expected,
                'Execution file differs from exact reviewed bytes')
    ref = api('/git/ref/heads/' + BRANCH)
    require(ref['ref'] == 'refs/heads/' + BRANCH and ref['object']['sha'] == head,
            'Inspection branch advanced before execution')
    REPORT['diagnostic'] = {'parent_sha': parent, 'execution_sha': head,
                           'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': 1}
    return image


def verify_source(manifest):
    source = manifest['image']['source_sha']
    commit = api('/git/commits/' + source)
    require(commit['sha'] == source, 'Exact candidate source commit differs')
    tree = api('/git/trees/' + commit['tree']['sha'] + '?recursive=1')
    require(tree['truncated'] is False and len(tree['tree']) <= 10000, 'Source tree is incomplete')
    entries = {item['path']: item for item in tree['tree']}
    require(len(entries) == len(tree['tree']), 'Duplicate source tree entries')
    for name, expected in manifest['source_files'].items():
        item = entries[name]
        require(item['type'] == 'blob' and item['sha'] == expected['blob_sha'] and item['mode'] == expected['mode'],
                'Packaged source blob differs')
        blob = api('/git/blobs/' + expected['blob_sha'])
        require(blob['encoding'] == 'base64', 'Unexpected source blob encoding')
        raw = base64.b64decode(''.join(blob['content'].split()), validate=True)
        require(len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256']
                and hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest() == expected['blob_sha'],
                'Actual source blob checksums differ')
        put('candidate/source/' + name, raw)
    return {'commit': source, 'tree': commit['tree']['sha'], 'files': manifest['source_files']}


def download_candidate(image, folder):
    fetch = fetch_module()
    run = api('/actions/runs/' + str(image['run_id']))
    artifact = api('/actions/artifacts/' + str(image['artifact_id']))
    fetch.validate(image, run, artifact)
    page = api('/actions/runs/' + str(image['run_id']) + '/jobs?filter=all&per_page=100')
    require(type(page['total_count']) is int and page['total_count'] == len(page['jobs']), 'Incomplete producer jobs')
    fetch.validate_boot_steps(image, page['jobs'])
    archive = folder / 'candidate.zip'
    # gh handles the official redirect without logging signed archive URLs or tokens.
    with archive.open('xb') as output:
        result = subprocess.run(['gh', 'api', API + '/actions/artifacts/' + str(image['artifact_id']) + '/zip'],
                                stdout=output, stderr=subprocess.PIPE, timeout=1200)
    require(result.returncode == 0 and archive.stat().st_size == image['archive_bytes']
            and sha(archive) == image['archive_sha256'], 'Actual retained archive checksum differs')
    with zipfile.ZipFile(archive) as retained:
        zip_inventory = [{'path': item.filename, 'bytes': item.file_size,
                          'compressed_bytes': item.compress_size, 'crc32': f'{item.CRC:08x}',
                          'flags': item.flag_bits, 'compression': item.compress_type,
                          'external_attributes': item.external_attr} for item in retained.infolist()]
    inputs = folder / 'inputs'
    fetch.extract(archive, inputs, image)  # Includes CRC reads, receipt, BUILD-INFO, exact ISO hash.
    archive.unlink()
    inventory = []
    # extract() read every ZIP member; preserve the original artifact/API identities
    # and producer step outcomes without copying redirects or large image bytes.
    selected = fetch.producer_job(image, page['jobs'])
    for step in selected['steps']:
        if step['name'] in (*fetch.BOOT_STEPS, fetch.SIZE_STEP, fetch.RECEIPT_STEP,
                            fetch.EXTERNAL_UPLOAD_STEP, fetch.PAIRED_STEP):
            inventory.append({key: step[key] for key in ('name', 'status', 'conclusion')})
    put('candidate/performance-plan.json', (inputs / fetch.RECEIPT_NAME).read_bytes())
    return inputs / 'iso' / image['name'], {'image': image, 'producer': {
        'run_id': run['id'], 'source_sha': run['head_sha'], 'run_attempt': run['run_attempt'],
        'event': run['event'], 'workflow_path': run['path'], 'conclusion': run['conclusion'],
        'steps': inventory}, 'artifact': {'id': artifact['id'], 'name': artifact['name'],
        'bytes': artifact['size_in_bytes'], 'digest': artifact['digest'], 'expired': artifact['expired'],
        'original_zip_inventory': zip_inventory, 'all_members_crc_verified': True}}


def extract_selected(filesystem, selected, source, destination, provenance, deadline):
    require((source in ('/usr/bin/mango', '/usr/lib/sysimage/rpm') or re.fullmatch(WLROOTS_LIBRARY_PATH, source))
            and re.fullmatch('[a-z0-9_-]+', destination), 'Unexpected filtered extraction path')
    remaining = deadline - time.monotonic()
    require(remaining > 30, 'Aggregate filtered extraction budget exceeded')
    code, diagnostic = reader_capture('/usr/bin/fsck.erofs', ['--path=' + source, '--extract=/output/' + destination,
        '--no-preserve', '/input/rootfs.image'], mounts=[(filesystem, '/input/rootfs.image', True),
        (selected, '/output', False)], timeout=remaining - 30, allow_failure=True,
        include_stderr=True, limit=64000)
    provenance.setdefault('filtered_extractions', []).append({'source_path': source,
        'selected_destination': destination, 'exit_code': code,
        'diagnostic': diagnostic.replace(os.environ['RUNNER_TEMP'], '<runner-temp>')})
    require(code == 0, 'Pinned filtered EROFS extraction failed')


def rpm_query(root, args):
    return reader_capture('/usr/bin/rpm', ['--noplugins', '--root', '/proof',
        '--dbpath', '/usr/lib/sysimage/rpm'] + args, mounts=[(root, '/proof', True)])[1]


def library_record(root):
    rows = rpm_query(root, ['-qa', '--qf', '%{NAME}\t%{VERSION}\t%{ARCH}\n']).splitlines()
    matched = [row.split('\t') for row in rows if re.fullmatch(r'wlroots(?:0\.20)?\t0\.20\.2\tx86_64', row)]
    observed = [row.split('\t') for row in rows if re.fullmatch(
        r'wlroots(?:0\.20)?\t[0-9][0-9A-Za-z.+~:_-]{0,79}\tx86_64', row)]
    diagnostic = {'status': 'package_selection_pending', 'required_version': '0.20.2',
        'matching_package_count': len(matched), 'observed_package_count': len(observed),
        'observed_packages': [dict(zip(('name', 'version', 'arch'), row)) for row in observed[:8]]}
    REPORT['tools']['wlroots_library_selection'] = diagnostic
    diagnostic['status'] = 'package_rejected' if len(matched) != 1 else 'file_selection_pending'
    require(len(matched) == 1, 'Exactly one required wlroots 0.20.2 RPM is needed for ABI evidence')
    package = matched[0][0]
    files = rpm_query(root, ['-q', package, '--qf', '[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILEMODES}\n]']).splitlines()
    libraries = [row.split('\t') for row in files
                 if re.fullmatch(WLROOTS_LIBRARY_PATH + r'\t[0-9a-f]{64}\t[0-9]{1,6}', row)
                 and stat.S_IFMT(int(row.rsplit('\t', 1)[1])) == stat.S_IFREG]
    candidates = [row.split('\t') for row in files if re.fullmatch(
        WLROOTS_LIBRARY_PATH, row.split('\t', 1)[0])]
    diagnostic.update(regular_match_count=len(libraries), candidate_count=len(candidates),
        candidates=[{'path': row[0][:160],
            'sha256': row[1] if len(row) == 3 and re.fullmatch('[0-9a-f]{64}', row[1]) else 'invalid',
            'rpm_file_mode': row[2] if len(row) == 3 and re.fullmatch('[0-9]{1,6}', row[2]) else 'invalid'}
            for row in candidates[:8]], candidate_samples_omitted=max(0, len(candidates) - 8),
        status='file_rejected' if len(libraries) != 1 else 'selected_pending_payload_hash_and_ELF_ABI_verification')
    require(len(libraries) == 1, 'Exactly one actual regular wlroots shared library is needed')
    return package, libraries[0][0]


def rpm_identity(root, path, target, package, version):
    fields = rpm_query(root, ['-q', package, '--qf', '%{NAME}\t%{VERSION}\t%{RELEASE}\t%{ARCH}\t%{FILEDIGESTALGO}\n']).strip().split('\t')
    require(len(fields) == 5 and fields[:2] == [package, version] and fields[3:] == ['x86_64', '8'],
            'Unexpected target RPM identity or file digest algorithm')
    rows = rpm_query(root, ['-q', package, '--qf', '[%{FILENAMES}\t%{FILEDIGESTS}\t%{FILEMODES}\n]']).splitlines()
    matches = [row.split('\t') for row in rows if row.startswith(target + '\t')]
    require(len(matches) == 1 and len(matches[0]) == 3
            and re.fullmatch('[0-9a-f]{64}', matches[0][1])
            and stat.S_IFMT(int(matches[0][2])) == stat.S_IFREG and sha(path) == matches[0][1],
            'Actual extracted ELF differs from unique RPMDB regular-file digest')
    return {'nevra': '-'.join(fields[:3]) + '.' + fields[3], 'file_path': target,
            'file_digest_algorithm': 'sha256', 'file_sha256': matches[0][1], 'file_digest_verified': True,
            'verification_scope': 'This extracted ELF equals its image RPMDB digest; RPM signatures and other files are not verified'}


def save_elf(label, path, max_size):
    raw = path.read_bytes()
    require(4096 <= len(raw) <= max_size and raw[:6] == b'\x7fELF\x02\x01'
            and struct.unpack_from('<H', raw, 18)[0] == 62, 'Expected bounded little-endian x86_64 ELF')
    put('candidate/' + label + '.elf', raw)
    result = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'machine': 'x86_64',
              'sections': elf_sections(raw), 'profile_status': 'requires_independent_machine_code_and_abi_review'}
    for filename, argv in [('headers', ['readelf', '-hW', '-lW', '-SW', '-nW', '-dW', '-sW', str(path)]),
                           ('unwind', ['readelf', '--debug-dump=frames', '-W', str(path)]),
                           ('disassembly', ['objdump', '-d', '-w', str(path)])]:
        text = capture(argv, limit=12 * 1024 * 1024)[1]
        put('candidate/' + label + '-' + filename + '.txt', text.encode())
    return result


def inspect_iso(iso, provenance, folder):
    # Data-only extraction: no mounts, loop devices, target execution or appliance.
    listing = capture(['xorriso', '-indev', str(iso), '-find', '/LiveOS', '-type', 'f', '-exec', 'echo', '--'],
                      limit=1024 * 1024)[1]
    paths = [shlex.split(line) for line in listing.splitlines() if line.strip()]
    require(len(paths) <= 16 and all(len(p) == 1 for p in paths), 'Unexpected LiveOS inventory')
    members = [p[0] for p in paths if p[0].endswith(('.img', '.erofs', '.squashfs'))]
    require(len(members) == 1 and re.fullmatch(r'/LiveOS/[A-Za-z0-9._-]+', members[0]),
            'Unique regular LiveOS root filesystem required')
    filesystem = folder / 'rootfs.image'
    capture(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', members[0], str(filesystem)], timeout=600)
    require(filesystem.is_file() and not filesystem.is_symlink()
            and 1024 < filesystem.stat().st_size < 2_000_000_000, 'Unexpected root filesystem size or type')
    with filesystem.open('rb') as stream:
        require(stream.read(2048)[1024:1028] == b'\xe2\xe1\xf5\xe0', 'Expected Kiwi EROFS format')
    identity = {'iso_member': members[0], 'format': 'erofs', 'bytes': filesystem.stat().st_size,
                'sha256': sha(filesystem)}
    provenance['filesystem'] = identity
    selected = folder / 'selected'; selected.mkdir(mode=0o700)
    deadline = time.monotonic() + 900
    for source, destination in [('/usr/bin/mango', 'mango'), ('/usr/lib/sysimage/rpm', 'rpmdb')]:
        extract_selected(filesystem, selected, source, destination, identity, deadline)
    mango = safe_regular(selected, 'mango')
    database = selected / 'rpmdb'
    require(database.is_dir() and not database.is_symlink(), 'Selected image RPMDB missing')
    entries = list(database.iterdir())
    require({entry.name for entry in entries} <= {'rpmdb.sqlite', 'rpmdb.sqlite-wal', 'rpmdb.sqlite-shm', '.rpm.lock'}
            and 'rpmdb.sqlite' in {entry.name for entry in entries}
            and all(entry.is_file() and not entry.is_symlink() for entry in entries)
            and sum(entry.stat().st_size for entry in entries) < 128 * 1024 * 1024,
            'Unexpected selected image RPMDB inventory or size')
    root = folder / 'root'; db_target = root / 'usr/lib/sysimage/rpm'; db_target.mkdir(parents=True)
    identity['selected_rpmdb'] = {}
    for entry in entries:
        shutil.copyfile(entry, db_target / entry.name)
        identity['selected_rpmdb'][entry.name] = {'bytes': entry.stat().st_size, 'sha256': sha(entry)}
    package, library_target = library_record(root)
    extract_selected(filesystem, selected, library_target, 'wlroots', identity, deadline)
    library = safe_regular(selected, 'wlroots')
    provenance['mango_rpm'] = rpm_identity(root, mango, '/usr/bin/mango', 'mangowm', '0.17.3')
    provenance['wlroots_rpm'] = rpm_identity(root, library, library_target, package, '0.20.2')
    provenance['mango_elf'] = save_elf('mango', mango, 4 * 1024 * 1024)
    provenance['wlroots_elf'] = save_elf('wlroots', library, 8 * 1024 * 1024)
    provenance['abi_review'] = {'status': 'pending_independent_review',
        'evidence': 'Exact complete ELF bytes, sections, dynamic symbols, dependencies, unwind and disassembly',
        'limitations': ['Compiled source-header structure offsets are not independently measured by this lane',
                       'No comparator profile is created or admitted', 'No runtime mapping, calibration or performance result']}


def main():
    global OUTPUT
    root = Path(__file__).resolve().parents[2]
    manifest_path = Path(__file__).with_name('execution-manifest.json')
    manifest = read_json(manifest_path.read_text())
    image = activation_guard(manifest, root)
    OUTPUT = Path(os.environ['RUNNER_TEMP']) / 'arctic-exact-image-mango-evidence'
    OUTPUT.mkdir(mode=0o700)
    put('execution-manifest.json', manifest_path.read_bytes())
    def deadline(signum, frame):
        raise ValueError('Static inspection time budget exceeded')
    signal.signal(signal.SIGTERM, deadline)
    try:
        for name in ('gh', 'xorriso', 'readelf', 'objdump', 'docker'):
            code, text = capture([name, '--version'], allow_failure=True, include_stderr=True, limit=100000)
            REPORT['tools'][name] = {'exit_code': code, 'version': text[:4000]}
        source = verify_source(manifest)
        prepare_reader()
        require(shutil.disk_usage(os.environ['RUNNER_TEMP']).free > 8 * 1024**3, 'Insufficient hosted temporary disk')
        with tempfile.TemporaryDirectory(prefix='arctic-static-exact-mango-', dir=os.environ['RUNNER_TEMP']) as temp:
            folder = Path(temp)
            iso, provenance = download_candidate(image, folder)
            provenance['source'] = source
            REPORT['images']['candidate'] = provenance
            inspect_iso(iso, provenance, folder)
        REPORT['status'] = 'static_evidence_complete_pending_independent_review'
    except Exception as error:
        REPORT['failure'] = {'type': type(error).__name__,
            'reason': str(error) if isinstance(error, ValueError) else 'Static inspection failed; no qualification claim'}
        raise
    finally:
        write_report()
        if READER is not None:
            capture(['docker', 'image', 'rm', READER], timeout=30, allow_failure=True)
        actual = {str(p.relative_to(OUTPUT)) for p in OUTPUT.rglob('*') if p.is_file()}
        require(actual == ALLOWED | {'report.json'} and all(not p.is_symlink() for p in OUTPUT.rglob('*')),
                'Evidence inventory mismatch')
        require(sum(p.stat().st_size for p in OUTPUT.rglob('*') if p.is_file()) < LIMIT,
                'Evidence exceeds small-artifact limit')


if __name__ == '__main__':
    main()
