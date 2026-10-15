#!/usr/bin/env python3
"""Fail-closed, temporary export of pinned screened qualification evidence."""

import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import resource
import stat
import struct
import subprocess
import tempfile
import wave
import zipfile

from PIL import Image, ImageDraw, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = 'yuvalkolodkingal/Arctic-Linux'
SOURCE_BRANCH = 'codex/evidence-review-export-20261015'
TARGET_BRANCH = 'codex/evidence-review-artifacts-20261015'
WORKFLOW = '.github/workflows/evidence-review-export-20261015.yml'
MARKER = '.github/evidence-review-export-20261015.activate'
MANIFEST = 'tools/evidence-review-export/manifest.json'
SCHEMA = 'arctic-screened-evidence-review-export-v1'

BOUNDS = {
    'max_artifacts': 12,
    'max_archive_bytes_each': 250_000_000,
    'max_total_archive_bytes': 900_000_000,
    'max_zip_members_each': 50_000,
    'max_uncompressed_bytes_each': 750_000_000,
    'max_export_files': 320,
    'max_export_bytes_each': 32_000_000,
    'max_total_export_bytes': 150_000_000,
    'max_contact_sheets': 8,
    'max_contact_sheet_members_each': 64,
    'max_contact_sheet_source_images': 512,
    'max_contact_sheet_exact_frames': 32,
    'max_contact_sheet_pixels_each': 16_777_216,
    'max_generated_png_bytes_each': 12_000_000,
}

ALLOWED_WORKFLOWS = {
    '.github/workflows/iso.yml',
    '.github/workflows/release-reliability-candidate.yml',
    '.github/workflows/installer-candidate-20261009.yml',
    '.github/workflows/installer-active-candidate-20261009.yml',
    '.github/workflows/dictation-candidate-20261009.yml',
    '.github/workflows/native-candidate-20261008.yml',
    '.github/workflows/paired-candidate-20261009.yml',
    '.github/workflows/image-update-20261008.yml',
    '.github/workflows/inspect-exact-image-mango-20261010.yml',
    '.github/workflows/showcase-exact-capture-20261014.yml',
    '.github/workflows/showcase-river-render.yml',
    '.github/workflows/showcase-river-verify.yml',
}

BASE_FILE_FIELDS = {'member', 'output', 'kind', 'privacy_class', 'bytes', 'sha256'}
NATIVE_AUDIO_FIELDS = {'member', 'output', 'kind', 'privacy_class', 'max_bytes', 'audio_class'}
KIND_FIELDS = {
    'png': BASE_FILE_FIELDS | {'width', 'height'},
    'json': BASE_FILE_FIELDS,
    'native-system-audio': NATIVE_AUDIO_FIELDS,
}
CONTACT_MEMBER_FIELDS = {'member', 'max_bytes', 'width', 'height'}
CONTACT_EXACT_FIELDS = {'member', 'output'}
CONTACT_SHEET_FIELDS = {'output', 'kind', 'privacy_class', 'members', 'columns',
                        'thumbnail_width', 'thumbnail_height', 'label_height',
                        'max_output_bytes', 'exact_frames'}
PRIVACY_CLASS = {
    'png': 'screened-vm-ui',
    'json': 'screened-summary',
}
AUDIO_CLASSES = {
    'native-virtual-output-boot': {
        'privacy_class': 'validated-native-system-audio',
        'workflow_path': '.github/workflows/native-candidate-20261008.yml',
        'member_suffix': 'virtual-audio/native-audio-boot.wav',
    },
    'native-virtual-output-install': {
        'privacy_class': 'validated-native-system-audio',
        'workflow_path': '.github/workflows/native-candidate-20261008.yml',
        'member_suffix': 'virtual-audio/native-audio-install.wav',
    },
}
SUFFIXES = {
    'png': {'.png'},
    'json': {'.json'},
    'native-system-audio': {'.wav'},
}
HEX40 = re.compile(r'[0-9a-f]{40}')
HEX64 = re.compile(r'[0-9a-f]{64}')
SAFE_NAME = re.compile(r'[A-Za-z0-9][A-Za-z0-9._ +()-]{0,199}')
SAFE_OUTPUT = re.compile(r'evidence/[a-z0-9][a-z0-9._/-]{0,239}')
SENSITIVE_JSON_KEY = re.compile(
    r'(?i)(authorization|clipboard|detail|email|hypothesis|inserted.?text|journal|log|message|'
    r'password|prompt|raw.?text|recognized|secret|stderr|stdout|text|token|transcri|username|utterance)'
)
SENSITIVE_VALUE = re.compile(
    r'(?i)(authorization\s*:|(?:gh[pousr]_|github_pat_)[a-z0-9_]+|'
    r'(?:password|secret|token)\s*[=:]\s*\S+|[\w.+-]+@[\w.-]+|https?://\S*\?\S+)'
)
BASE64_VALUE = re.compile(r'[A-Za-z0-9+/]{257,}={0,2}')
FORBIDDEN_AUDIO_NAME = re.compile(
    r'(?i)(dictat|microphone|recording|speech.?to.?text|transcri|utterance|voxtype|whisper)'
)


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON field: ' + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=120).strip()


def safe_archive_member(name):
    require(type(name) is str and name and '\x00' not in name and '\\' not in name,
            'Unsafe archive member name')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in path.parts),
            'Unsafe archive member path: ' + name)
    return path


def safe_output_path(name):
    require(type(name) is str and SAFE_OUTPUT.fullmatch(name), 'Unsafe review output path')
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in path.parts),
            'Unsafe review output path: ' + name)
    return path


def validate_file(value):
    require(type(value) is dict and value.get('kind') in KIND_FIELDS,
            'Malformed evidence file entry')
    kind = value['kind']
    require(set(value) == KIND_FIELDS[kind], 'Evidence file fields differ: ' + kind)
    member = safe_archive_member(value['member'])
    output = safe_output_path(value['output'])
    require(member.suffix.lower() in SUFFIXES[kind] and output.suffix.lower() in SUFFIXES[kind],
            'Evidence type and filename suffix differ')
    if kind != 'native-system-audio':
        require(value['privacy_class'] == PRIVACY_CLASS[kind],
                'Evidence privacy class is not approved')
        require(type(value['bytes']) is int
                and 0 < value['bytes'] <= BOUNDS['max_export_bytes_each'],
                'Evidence file size is invalid')
        require(type(value['sha256']) is str and HEX64.fullmatch(value['sha256']),
                'Evidence file digest is invalid')
    if kind == 'png':
        require(type(value['width']) is int and 1 <= value['width'] <= 4096
                and type(value['height']) is int and 1 <= value['height'] <= 4096
                and value['width'] * value['height'] <= 16_777_216,
                'PNG dimensions are invalid')
    if kind == 'native-system-audio':
        audio_class = AUDIO_CLASSES.get(value['audio_class'])
        require(audio_class is not None
                and value['privacy_class'] == audio_class['privacy_class']
                and output.suffix.lower() == '.wav'
                and value['member'].endswith(audio_class['member_suffix'])
                and not FORBIDDEN_AUDIO_NAME.search(value['member'])
                and not FORBIDDEN_AUDIO_NAME.search(value['output']),
                'Audio is not an approved native virtual-output class')
        require(type(value['max_bytes']) is int
                and 0 < value['max_bytes'] <= BOUNDS['max_export_bytes_each'],
                'Native system audio byte bound is invalid')
    return value


def validate_contact_member(value):
    require(type(value) is dict and set(value) == CONTACT_MEMBER_FIELDS,
            'Contact-sheet member fields differ')
    member = safe_archive_member(value['member'])
    require(member.suffix.lower() == '.png', 'Contact-sheet source is not PNG')
    require(type(value['max_bytes']) is int
            and 0 < value['max_bytes'] <= BOUNDS['max_export_bytes_each'],
            'Contact-sheet source byte bound is invalid')
    require(type(value['width']) is int and 1 <= value['width'] <= 4096
            and type(value['height']) is int and 1 <= value['height'] <= 4096
            and value['width'] * value['height'] <= BOUNDS['max_contact_sheet_pixels_each'],
            'Contact-sheet source dimensions are invalid')
    return value


def validate_contact_sheet(value):
    require(type(value) is dict and set(value) == CONTACT_SHEET_FIELDS
            and value.get('kind') == 'png-contact-sheet',
            'Malformed contact-sheet entry')
    output = safe_output_path(value['output'])
    require(output.suffix.lower() == '.png' and value['privacy_class'] == 'screened-vm-ui',
            'Contact-sheet output or privacy class is invalid')
    require(type(value['members']) is list
            and 1 <= len(value['members']) <= BOUNDS['max_contact_sheet_members_each'],
            'Contact-sheet source count is invalid')
    members = set()
    for member in value['members']:
        validate_contact_member(member)
        require(member['member'] not in members, 'Duplicate contact-sheet source member')
        members.add(member['member'])
    require(type(value['exact_frames']) is list
            and len(value['exact_frames']) <= BOUNDS['max_contact_sheet_exact_frames'],
            'Contact-sheet exact-frame selection is invalid')
    exact_members = set()
    exact_outputs = set()
    for exact in value['exact_frames']:
        require(type(exact) is dict and set(exact) == CONTACT_EXACT_FIELDS
                and exact['member'] in members and exact['member'] not in exact_members,
                'Exact frame is not a unique contact-sheet source')
        output = safe_output_path(exact['output'])
        require(output.suffix.lower() == '.png' and exact['output'] != value['output']
                and exact['output'] not in exact_outputs,
                'Exact-frame output is invalid or duplicated')
        exact_members.add(exact['member'])
        exact_outputs.add(exact['output'])
    for key, low, high in (
            ('columns', 1, 6), ('thumbnail_width', 160, 512),
            ('thumbnail_height', 90, 288), ('label_height', 16, 40)):
        require(type(value[key]) is int and low <= value[key] <= high,
                'Contact-sheet geometry is invalid: ' + key)
    rows = math.ceil(len(value['members']) / value['columns'])
    width = value['columns'] * value['thumbnail_width']
    height = rows * (value['thumbnail_height'] + value['label_height'])
    require(width <= 4096 and height <= 4096
            and width * height <= BOUNDS['max_contact_sheet_pixels_each'],
            'Contact-sheet output dimensions exceed bounds')
    require(type(value['max_output_bytes']) is int
            and 0 < value['max_output_bytes'] <= BOUNDS['max_generated_png_bytes_each'],
            'Contact-sheet output byte bound is invalid')
    return value


def validate_manifest(value, require_ready=True):
    fields = {'schema', 'ready', 'review_only', 'repository', 'source_branch',
              'target_branch', 'bounds', 'artifacts'}
    require(type(value) is dict and set(value) == fields, 'Evidence export manifest fields differ')
    require(value['schema'] == SCHEMA and value['review_only'] is True
            and value['repository'] == REPOSITORY and value['source_branch'] == SOURCE_BRANCH
            and value['target_branch'] == TARGET_BRANCH and value['bounds'] == BOUNDS,
            'Evidence export identity or immutable bounds differ')
    require(type(value['ready']) is bool and type(value['artifacts']) is list,
            'Evidence export readiness is malformed')
    if not value['ready']:
        require(not value['artifacts'], 'Disabled export manifest must not pin artifacts')
        require(not require_ready, 'Evidence review export is disabled')
        return value
    require(1 <= len(value['artifacts']) <= BOUNDS['max_artifacts'],
            'Evidence artifact count is invalid')
    artifact_ids = set()
    outputs = set()
    file_count = 0
    total_archive = 0
    total_export_budget = 0
    contact_sheets = 0
    contact_sources = 0
    contact_exact_frames = 0
    artifact_fields = {'artifact_id', 'run_id', 'run_attempt', 'head_sha', 'head_branch',
                       'workflow_path', 'event', 'name', 'archive_bytes',
                       'archive_sha256', 'screening', 'files'}
    for artifact in value['artifacts']:
        require(type(artifact) is dict and set(artifact) == artifact_fields,
                'Evidence artifact fields differ')
        require(type(artifact['artifact_id']) is int and artifact['artifact_id'] > 0
                and artifact['artifact_id'] not in artifact_ids,
                'Evidence artifact ID is invalid or duplicated')
        artifact_ids.add(artifact['artifact_id'])
        require(type(artifact['run_id']) is int and artifact['run_id'] > 0
                and type(artifact['run_attempt']) is int and artifact['run_attempt'] > 0,
                'Evidence run identity is invalid')
        require(type(artifact['head_sha']) is str and HEX40.fullmatch(artifact['head_sha'])
                and type(artifact['head_branch']) is str
                and re.fullmatch(r'codex/[a-z0-9][a-z0-9._/-]{0,199}', artifact['head_branch']),
                'Evidence run source identity is invalid')
        require(artifact['workflow_path'] in ALLOWED_WORKFLOWS and artifact['event'] == 'push',
                'Evidence workflow is not an approved qualification lane')
        require(type(artifact['name']) is str and SAFE_NAME.fullmatch(artifact['name']),
                'Evidence artifact name is invalid')
        require(type(artifact['archive_bytes']) is int
                and 0 < artifact['archive_bytes'] <= BOUNDS['max_archive_bytes_each']
                and type(artifact['archive_sha256']) is str
                and HEX64.fullmatch(artifact['archive_sha256']),
                'Evidence archive pin is invalid')
        screening = artifact['screening']
        require(type(screening) is dict
                and set(screening) == {'stage', 'transcript_free', 'inventory_member'}
                and screening['stage'] == 'producer-screened'
                and screening['transcript_free'] is True
                and (screening['inventory_member'] is None
                     or (type(screening['inventory_member']) is str
                         and safe_archive_member(screening['inventory_member']).suffix == '.json')),
                'Evidence was not declared producer-screened and transcript-free')
        require(type(artifact['files']) is list and artifact['files'],
                'Evidence artifact has no selected files')
        total_archive += artifact['archive_bytes']
        members = {}
        for item in artifact['files']:
            if type(item) is dict and item.get('kind') == 'png-contact-sheet':
                validate_contact_sheet(item)
                require(screening['inventory_member'] is not None,
                        'Contact sheets require the producer screening inventory')
                contact_sheets += 1
                contact_sources += len(item['members'])
                contact_exact_frames += len(item['exact_frames'])
                source_members = [source['member'] for source in item['members']]
                sources_by_name = {source['member']: source for source in item['members']}
                total_export_budget += item['max_output_bytes'] + sum(
                    sources_by_name[exact['member']]['max_bytes'] for exact in item['exact_frames'])
            else:
                validate_file(item)
                if item['kind'] == 'native-system-audio':
                    audio_class = AUDIO_CLASSES[item['audio_class']]
                    require(screening['inventory_member'] is not None
                            and artifact['workflow_path'] == audio_class['workflow_path'],
                            'Audio class is not valid for this qualification workflow')
                source_members = [item['member']]
                total_export_budget += item.get('bytes', item.get('max_bytes'))
            for member in source_members:
                source = (next(value for value in item['members'] if value['member'] == member)
                          if item.get('kind') == 'png-contact-sheet' else item)
                pin = (source.get('bytes', source.get('max_bytes')), source.get('sha256'),
                       source.get('width'), source.get('height'))
                if member in members:
                    require(member.endswith('.png') and members[member] == pin,
                            'Conflicting or non-image duplicate archive member: ' + member)
                else:
                    members[member] = pin
            item_outputs = [item['output']]
            if item.get('kind') == 'png-contact-sheet':
                item_outputs.extend(exact['output'] for exact in item['exact_frames'])
            for output in item_outputs:
                require(output not in outputs, 'Duplicate review output: ' + output)
                outputs.add(output)
            file_count += len(item_outputs)
    require(total_archive <= BOUNDS['max_total_archive_bytes'], 'Total archive bound exceeded')
    require(file_count <= BOUNDS['max_export_files'], 'Export file count bound exceeded')
    require(contact_sheets <= BOUNDS['max_contact_sheets'], 'Contact-sheet count bound exceeded')
    require(contact_sources <= BOUNDS['max_contact_sheet_source_images'],
            'Contact-sheet source image count bound exceeded')
    require(contact_exact_frames <= BOUNDS['max_contact_sheet_exact_frames'],
            'Contact-sheet exact-frame count bound exceeded')
    require(total_export_budget <= BOUNDS['max_total_export_bytes'],
            'Total export byte budget exceeded')
    return value


def validate_activation(manifest_path):
    require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == REPOSITORY
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + SOURCE_BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
            'Requires the dedicated first-attempt GitHub-hosted review export lane')
    event = strict_json(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    marker = (ROOT / MARKER).read_text().strip()
    head = git('rev-parse', 'HEAD')
    require(HEX40.fullmatch(marker) and event.get('before') == marker
            and event.get('after') == os.environ.get('GITHUB_SHA') == head
            and git('rev-list', '--parents', '-n', '1', 'HEAD').split() == [head, marker]
            and git('diff', '--no-renames', '--name-only', marker, 'HEAD').splitlines() == [MARKER]
            and not git('status', '--porcelain'),
            'Evidence export activation is not the reviewed marker-only child')
    manifest = validate_manifest(strict_json(Path(manifest_path).read_text()))
    return manifest, marker, head


def fetch_json(endpoint):
    raw = subprocess.check_output(['gh', 'api', endpoint], timeout=120)
    return strict_json(raw.decode())


def download_archive(endpoint, destination, expected_bytes):
    def limit_output_size():
        resource.setrlimit(resource.RLIMIT_FSIZE, (expected_bytes, expected_bytes))
    with Path(destination).open('xb') as stream:
        subprocess.run(['gh', 'api', endpoint + '/zip'], stdout=stream,
                       check=True, timeout=1200, preexec_fn=limit_output_size)
    require(Path(destination).stat().st_size == expected_bytes,
            'Downloaded artifact byte count differs from its pin')


def verify_remote_identity(artifact, metadata, run):
    require(type(metadata) is dict and metadata.get('id') == artifact['artifact_id']
            and metadata.get('name') == artifact['name'] and metadata.get('expired') is False
            and metadata.get('size_in_bytes') == artifact['archive_bytes']
            and metadata.get('digest') == 'sha256:' + artifact['archive_sha256'],
            'Remote artifact identity differs from its review pin')
    workflow_run = metadata.get('workflow_run')
    require(type(workflow_run) is dict and workflow_run.get('id') == artifact['run_id']
            and workflow_run.get('head_sha') == artifact['head_sha']
            and workflow_run.get('head_branch') == artifact['head_branch'],
            'Artifact workflow-run identity differs from its review pin')
    require(type(run) is dict and run.get('id') == artifact['run_id']
            and run.get('run_attempt') == artifact['run_attempt']
            and run.get('head_sha') == artifact['head_sha']
            and run.get('head_branch') == artifact['head_branch']
            and run.get('path') == artifact['workflow_path'] and run.get('event') == artifact['event']
            and run.get('status') == 'completed' and run.get('conclusion') == 'success',
            'Qualification run is not the pinned successful completed run')


def inspect_png(raw):
    require(raw.startswith(b'\x89PNG\r\n\x1a\n') and len(raw) >= 24
            and raw[12:16] == b'IHDR', 'Invalid PNG evidence')
    width, height = struct.unpack('>II', raw[16:24])
    require(1 <= width <= 4096 and 1 <= height <= 4096
            and width * height <= BOUNDS['max_contact_sheet_pixels_each'],
            'PNG evidence dimensions exceed bounds')
    Image.MAX_IMAGE_PIXELS = BOUNDS['max_contact_sheet_pixels_each']
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.verify()
            require(image.format == 'PNG' and image.size == (width, height),
                    'PNG decoder identity differs')
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise RuntimeError('Invalid PNG evidence') from error
    return width, height


def inspect_native_wav(raw):
    try:
        with wave.open(io.BytesIO(raw), 'rb') as source:
            require(source.getnchannels() == 2 and source.getframerate() == 48_000
                    and source.getsampwidth() == 2 and source.getcomptype() == 'NONE'
                    and source.getnframes() > 0,
                    'Native virtual-output WAV format differs')
            frames = 0
            nonzero = False
            while block := source.readframes(16_384):
                frames += len(block) // 4
                nonzero = nonzero or any(block)
            require(frames == source.getnframes() and nonzero,
                    'Native virtual-output WAV is truncated or silent')
    except (EOFError, wave.Error) as error:
        raise RuntimeError('Invalid native virtual-output WAV') from error


def inspect_json_value(value, path='$'):
    if isinstance(value, dict):
        for key, child in value.items():
            require(type(key) is str and not SENSITIVE_JSON_KEY.search(key),
                    'Sensitive JSON field is not exportable: ' + path + '.' + key)
            inspect_json_value(child, path + '.' + key)
    elif isinstance(value, list):
        require(len(value) <= 10_000, 'Oversized JSON array')
        for index, child in enumerate(value):
            inspect_json_value(child, f'{path}[{index}]')
    elif isinstance(value, str):
        require(len(value) <= 2048 and not SENSITIVE_VALUE.search(value)
                and not BASE64_VALUE.fullmatch(value),
                'Sensitive or oversized JSON string is not exportable: ' + path)
    else:
        require(value is None or type(value) in (bool, int)
                or (type(value) is float and math.isfinite(value)), 'Unsupported JSON value')


def inspect_selected(raw, item):
    require(len(raw) == item['bytes'] and digest_bytes(raw) == item['sha256'],
            'Selected evidence bytes differ from their pin: ' + item['member'])
    if item['kind'] == 'png':
        require(inspect_png(raw) == (item['width'], item['height']),
                'PNG dimensions differ from their pin')
    else:
        inspect_json_value(strict_json(raw.decode('utf-8')))


def load_screening_inventory(archive, member):
    try:
        info = archive.getinfo(member)
    except KeyError as error:
        raise RuntimeError('Producer screening inventory is absent') from error
    require(not info.is_dir() and 0 < info.file_size <= 16_000_000,
            'Producer screening inventory size is invalid')
    value = strict_json(archive.read(info).decode('utf-8'))
    require(type(value) is dict and type(value.get('scope')) is str
            and type(value.get('files')) is dict,
            'Producer screening inventory is malformed')
    return value['files']


def render_contact_sheet(archive, item, destination, screening_files, output_root):
    columns = item['columns']
    rows = math.ceil(len(item['members']) / columns)
    cell_width = item['thumbnail_width']
    image_height = item['thumbnail_height']
    cell_height = image_height + item['label_height']
    sheet = Image.new('RGB', (columns * cell_width, rows * cell_height), '#111827')
    draw = ImageDraw.Draw(sheet)
    cells = []
    source_raw = {}
    for index, source in enumerate(item['members'], start=1):
        info = archive.getinfo(source['member'])
        require(not info.is_dir() and 0 < info.file_size <= source['max_bytes'],
                'Contact-sheet source exceeds its byte bound')
        raw = archive.read(info)
        digest = digest_bytes(raw)
        screened = screening_files.get(source['member'])
        require(type(screened) is dict and screened.get('bytes') == len(raw)
                and screened.get('uploaded_sha256') == digest
                and inspect_png(raw) == (source['width'], source['height']),
                'Contact-sheet source is absent from the verified screening inventory')
        source_raw[source['member']] = raw
        with Image.open(io.BytesIO(raw)) as opened:
            frame = opened.convert('RGB')
            frame.thumbnail((cell_width, image_height), Image.Resampling.LANCZOS)
        cell = index - 1
        x = (cell % columns) * cell_width
        y = (cell // columns) * cell_height
        sheet.paste(frame, (x + (cell_width - frame.width) // 2,
                            y + (image_height - frame.height) // 2))
        draw.text((x + 4, y + image_height + 2), f'{index:03d}', fill='#f9fafb')
        cells.append({
            'index': index,
            'member': source['member'],
            'bytes': len(raw),
            'sha256': digest,
            'width': source['width'],
            'height': source['height'],
        })
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open('xb') as stream:
        sheet.save(stream, format='PNG', compress_level=6)
    output_bytes = destination.stat().st_size
    require(0 < output_bytes <= item['max_output_bytes'],
            'Generated contact sheet exceeds its declared byte bound')
    records = [{
        'kind': 'png-contact-sheet',
        'privacy_class': item['privacy_class'],
        'output': item['output'],
        'bytes': output_bytes,
        'sha256': digest_file(destination),
        'width': sheet.width,
        'height': sheet.height,
        'columns': columns,
        'cells': cells,
    }]
    total_bytes = output_bytes
    cells_by_member = {cell['member']: cell for cell in cells}
    for exact in item['exact_frames']:
        raw = source_raw[exact['member']]
        exact_destination = output_root / exact['output']
        exact_destination.parent.mkdir(parents=True, exist_ok=True)
        with exact_destination.open('xb') as stream:
            stream.write(raw)
        cell = cells_by_member[exact['member']]
        records.append({
            'kind': 'png-exact-frame',
            'privacy_class': item['privacy_class'],
            'output': exact['output'],
            'member': exact['member'],
            'bytes': cell['bytes'],
            'sha256': cell['sha256'],
            'width': cell['width'],
            'height': cell['height'],
        })
        total_bytes += len(raw)
    return records, total_bytes


def extract_artifact(artifact, archive_path, output_root):
    require(archive_path.stat().st_size == artifact['archive_bytes']
            and digest_file(archive_path) == artifact['archive_sha256'],
            'Downloaded artifact archive differs from its pin')
    selected = set()
    for item in artifact['files']:
        if item['kind'] == 'png-contact-sheet':
            selected.update(source['member'] for source in item['members'])
        else:
            selected.add(item['member'])
    with zipfile.ZipFile(archive_path) as archive:
        infos = archive.infolist()
        require(len(infos) <= BOUNDS['max_zip_members_each'], 'Archive member bound exceeded')
        names = []
        total = 0
        for info in infos:
            safe_archive_member(info.filename.rstrip('/') if info.is_dir() else info.filename)
            mode = (info.external_attr >> 16) & 0o170000
            require(mode in (0, stat.S_IFREG, stat.S_IFDIR),
                    'Archive contains a special file: ' + info.filename)
            names.append(info.filename)
            total += info.file_size
        require(len(names) == len(set(names)), 'Archive contains duplicate member names')
        require(total <= BOUNDS['max_uncompressed_bytes_each'], 'Archive expansion bound exceeded')
        require(selected <= set(names), 'Selected evidence member is absent from archive')
        screening_files = None
        if any(item['kind'] in ('png-contact-sheet', 'native-system-audio')
               for item in artifact['files']):
            screening_files = load_screening_inventory(
                archive, artifact['screening']['inventory_member'])
        records = []
        exported_bytes = 0
        for item in artifact['files']:
            destination = output_root / item['output']
            if item['kind'] == 'png-contact-sheet':
                contact_records, contact_bytes = render_contact_sheet(
                    archive, item, destination, screening_files, output_root)
                records.extend(contact_records)
                exported_bytes += contact_bytes
                continue
            member = item['member']
            info = archive.getinfo(member)
            if item['kind'] == 'native-system-audio':
                require(not info.is_dir() and 0 < info.file_size <= item['max_bytes'],
                        'Native system audio exceeds its byte bound')
                raw = archive.read(info)
                digest = digest_bytes(raw)
                screened = screening_files.get(member)
                require(type(screened) is dict and screened.get('bytes') == len(raw)
                        and screened.get('uploaded_sha256') == digest,
                        'Native system audio is absent from the verified screening inventory')
                inspect_native_wav(raw)
                destination.parent.mkdir(parents=True, exist_ok=True)
                with destination.open('xb') as stream:
                    stream.write(raw)
                records.append({
                    'kind': item['kind'], 'privacy_class': item['privacy_class'],
                    'audio_class': item['audio_class'], 'member': member,
                    'output': item['output'], 'bytes': len(raw), 'sha256': digest,
                    'channels': 2, 'rate': 48_000, 'sample_width': 2,
                })
                exported_bytes += len(raw)
                continue
            require(not info.is_dir() and info.file_size == item['bytes'],
                    'Selected evidence member size differs from its pin')
            raw = archive.read(info)
            inspect_selected(raw, item)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open('xb') as stream:
                stream.write(raw)
            records.append({key: item[key] for key in sorted(item)})
            exported_bytes += item['bytes']
        return records, exported_bytes


def export(manifest_path, output_path):
    manifest, parent, head = validate_activation(manifest_path)
    output_root = Path(output_path)
    output_root.mkdir(mode=0o700, parents=False, exist_ok=False)
    records = []
    total_exported_bytes = 0
    with tempfile.TemporaryDirectory(prefix='arctic-evidence-export-') as temp:
        for artifact in manifest['artifacts']:
            endpoint = f'repos/{REPOSITORY}/actions/artifacts/{artifact["artifact_id"]}'
            metadata = fetch_json(endpoint)
            run = fetch_json(f'repos/{REPOSITORY}/actions/runs/{artifact["run_id"]}')
            verify_remote_identity(artifact, metadata, run)
            archive_path = Path(temp) / f'{artifact["artifact_id"]}.zip'
            download_archive(endpoint, archive_path, artifact['archive_bytes'])
            files, exported_bytes = extract_artifact(artifact, archive_path, output_root)
            total_exported_bytes += exported_bytes
            require(total_exported_bytes <= BOUNDS['max_total_export_bytes'],
                    'Generated review export exceeds its total byte bound')
            records.append({
                'artifact_id': artifact['artifact_id'],
                'run_id': artifact['run_id'],
                'run_attempt': artifact['run_attempt'],
                'head_sha': artifact['head_sha'],
                'head_branch': artifact['head_branch'],
                'workflow_path': artifact['workflow_path'],
                'name': artifact['name'],
                'archive_bytes': artifact['archive_bytes'],
                'archive_sha256': artifact['archive_sha256'],
                'files': files,
            })
    receipt = {
        'schema': SCHEMA,
        'review_only': True,
        'repository': REPOSITORY,
        'source_branch': SOURCE_BRANCH,
        'target_branch': TARGET_BRANCH,
        'reviewed_parent_sha': parent,
        'activation_sha': head,
        'export_run_id': int(os.environ['GITHUB_RUN_ID']),
        'export_run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
        'artifacts': records,
    }
    raw = (json.dumps(receipt, indent=2, sort_keys=True) + '\n').encode()
    with (output_root / 'REVIEW-MANIFEST.json').open('xb') as stream:
        stream.write(raw)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)
    check = sub.add_parser('validate-manifest')
    check.add_argument('--manifest', default=MANIFEST)
    run = sub.add_parser('export')
    run.add_argument('--manifest', default=MANIFEST)
    run.add_argument('--out', required=True)
    args = parser.parse_args()
    if args.command == 'validate-manifest':
        validate_manifest(strict_json(Path(args.manifest).read_text()))
    else:
        export(args.manifest, args.out)


if __name__ == '__main__':
    main()
