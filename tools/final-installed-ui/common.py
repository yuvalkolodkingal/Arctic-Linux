#!/usr/bin/env python3
"""Strict first-activation, pinned final-image and bounded original UI transport."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import zlib

ROOT = Path(__file__).resolve().parents[2]
BASE = '1a5c3cb0dc6783fc088b40e414fa7c766df99449'
BRANCH = 'codex/final-installed-ui-20261011'
MARKER = '.github/final-installed-ui-20261011.activate'
WORKFLOW = 'Final installed UI feature qualification'
PREFIX = 'tools/final-installed-ui/'
ADDITIONS = {'.github/workflows/final-installed-ui-20261011.yml'} | {
    PREFIX + n for n in ('common.py', 'compose.py', 'guest.py', 'run.py', 'test_final_ui.py',
                        'execution-manifest.json', 'README.md')}
FILES = {'.github/workflows/final-installed-ui-20261011.yml'} | {
    PREFIX + n for n in ('common.py', 'compose.py', 'guest.py', 'run.py')} | {
    'tools/test-install.sh', 'tools/lib/container.sh', 'tools/lib/vmtest.py',
    'tools/performance/prepare-vm-tools.sh', 'tools/native-functional/fetch-image.py',
    'tools/performance/producer-receipt.py', 'tools/native-functional/screen-evidence.py'}
SOURCE_FILES = {'profiles/ci/offline.toml', 'tools/native-functional/native_smoke.py',
    'shell/shell.qml', 'shell/Launcher.qml', 'shell/LockScreen.qml', 'shell/Wallpapers.qml',
    'shell/UpdateService.qml', 'shell/UpdateStatus.js', 'shell/scripts/wallpapers.py',
    'shell/scripts/apps.py', 'shell/getapps/GetApps.qml', 'shell/getapps/ChooserPage.qml',
    'shell/getapps/RemovePage.qml', 'settings/Main.qml', 'settings/Backend.qml',
    'settings/SearchIndex.js', 'settings/shell.qml', 'settings/pages/AppearancePage.qml', 'dotfiles/.local/bin/arctic-theme',
    'dotfiles/.local/bin/arctic-shell-ipc'}
IMAGE_KEYS = {'source_sha', 'run_id', 'artifact_id', 'name', 'bytes', 'sha256', 'archive_bytes',
              'archive_sha256', 'producer_mode', 'producer_receipt_sha256'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=30).strip()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON field')
            result[key] = value
        return result
    return json.loads(data, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def regular(path, limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        info=os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= limit,
                'Missing/nonregular/oversized owned file')
        with os.fdopen(fd,'rb',closefd=False) as stream:data=stream.read(limit+1)
        after=os.fstat(fd)
        require(len(data)==info.st_size and (after.st_dev,after.st_ino,after.st_size)==
                (info.st_dev,info.st_ino,info.st_size),'Acquired original changed during read')
        return data
    finally:os.close(fd)


def manifest(value, operational=False):
    require(type(value) is dict and set(value) == {'schema', 'ready', 'release_acceptance',
            'image', 'execution_files', 'source_files', 'ui_seconds', 'max_png'}, 'Manifest schema differs')
    require(value['schema'] == 'arctic-final-installed-ui-v1' and type(value['ready']) is bool
            and value['release_acceptance'] is False and value['ui_seconds'] == 720
            and type(value['ui_seconds']) is int and value['max_png'] == 16
            and type(value['max_png']) is int, 'UI limits/acceptance differ')
    if operational: require(value['ready'] is True, 'Installed UI qualification remains disabled')
    image = value['image']
    require(type(image) is dict and set(image) == IMAGE_KEYS and image['source_sha'] ==
            '326690f173d4dc4f049f43e046c8380e66825a07' and image['bytes'] == 1929719808
            and image['sha256'] == '807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c'
            and image['run_id'] == 38102474066 and image['artifact_id'] == 11689591362
            and type(image['run_id']) is int and type(image['artifact_id']) is int
            and type(image['bytes']) is int and type(image['archive_bytes']) is int
            and 0 < image['bytes'] < 2000000000
            and image['archive_bytes'] == 1929907101 and image['archive_sha256'] ==
            '3a8132aa4578fdb62b2aa1e3bf5c340229f1a483678d03ddf2c565fb39afadcd'
            and image['name'] == 'Arctic-Linux-1.2-candidate-38102474066-1-x86_64.iso'
            and image['producer_mode'] == 'frozen-external-paired-v1'
            and image['producer_receipt_sha256'] ==
            '3034ea88d4ba1d1e434942f90c42b8057d3667ad2e7f6ee739b895ebdfc86d1d', 'Exact final F10 differs')
    require(type(value['execution_files']) is dict and set(value['execution_files']) == FILES,
            'Execution inventory differs')
    require(type(value['source_files']) is dict and set(value['source_files']) == SOURCE_FILES,
            'Image source inventory differs')
    for group in ('execution_files', 'source_files'):
        require(all(type(name) is str and name == Path(name).as_posix() and not Path(name).is_absolute()
                and '..' not in Path(name).parts and type(sha) is str and re.fullmatch('[0-9a-f]{64}', sha)
                for name, sha in value[group].items()), 'Unsafe source pin')
    return value


def guard(value, source, inputs=None):
    manifest(value, True)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_WORKFLOW') == WORKFLOW
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Requires owned first hosted push')
    event = strict_json(regular(Path(os.environ['GITHUB_EVENT_PATH']), 1024*1024))
    head = git('rev-parse', 'HEAD'); prep = git('rev-parse', 'HEAD^')
    require(git('rev-list', '--parents', '-n', '1', head).split() == [head, prep]
            and head == os.environ.get('GITHUB_SHA') == event.get('after') and prep == event.get('before')
            and regular(ROOT / MARKER, 41) == (prep + '\n').encode()
            and git('ls-tree', head, '--', MARKER).split()[0] == '100644'
            and git('diff', '--no-renames', '--name-status', prep, head) == 'A\t' + MARKER,
            'Requires sole first marker ADD')
    require(git('rev-list', '--parents', '-n', '1', prep).split() == [prep, BASE], 'Preparation base differs')
    paths = set(git('diff', '--no-renames', '--name-only', BASE, prep).splitlines())
    require(paths == ADDITIONS | {'.github/workflows/ci.yml'}, 'Preparation scope differs')
    require(set(git('diff', '--no-renames', '--name-status', BASE, prep).splitlines()) ==
            {'A\t'+name for name in ADDITIONS} | {'M\t.github/workflows/ci.yml'},
            'Preparation modes/change kinds differ')
    expected_raw = set()
    for name in ADDITIONS | {'.github/workflows/ci.yml'}:
        entry = git('ls-tree', prep, '--', name).split()
        require(len(entry) == 4 and entry[:2] == ['100644', 'blob'] and entry[3] == name,
                'Preparation regular mode/type differs')
        if name in ADDITIONS:
            expected_raw.add(':000000 100644 ' + '0'*40 + ' ' + entry[2] + ' A\t' + name)
        else:
            original = git('ls-tree', BASE, '--', name).split()
            require(len(original) == 4 and original[:2] == ['100644', 'blob'] and original[3] == name,
                    'Original CI regular mode/type differs')
            expected_raw.add(':100644 100644 ' + original[2] + ' ' + entry[2] + ' M\t' + name)
    require(set(git('diff', '--raw', '--no-abbrev', '--no-renames', BASE, prep).splitlines()) == expected_raw,
            'Preparation raw modes/change kinds differ')
    before = subprocess.check_output(['git','-C',str(ROOT),'show',BASE+':.github/workflows/ci.yml'])
    after = regular(ROOT/'.github/workflows/ci.yml', 1024*1024)
    require(after.replace(('      - '+BRANCH+'\n').encode(), b'', 1) == before
            and after.count(('      - '+BRANCH+'\n').encode()) == 1,
            'CI differs beyond the one owned branch exclusion')
    require(not git('status', '--porcelain') and not subprocess.check_output(
            ['git', '-C', str(source), 'status', '--porcelain'], text=True), 'Tracked checkout dirty')
    require(subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
            == value['image']['source_sha'], 'Image source checkout differs')
    for group, tree in (('execution_files', ROOT), ('source_files', source)):
        for name, expected in value[group].items():
            require(digest_file(tree/name) == expected, 'Pinned execution/source bytes differ')
    fetch = load(ROOT/'tools/native-functional/fetch-image.py', 'final_ui_fetch')
    image = value['image']
    run = fetch.api('/actions/runs/'+str(image['run_id']))
    artifact = fetch.api('/actions/artifacts/'+str(image['artifact_id']))
    fetch.validate(image, run, artifact)
    jobs = fetch.api('/actions/runs/'+str(image['run_id'])+'/jobs?filter=all&per_page=100')
    require(jobs['total_count'] == len(jobs['jobs']), 'Producer job inventory incomplete')
    fetch.validate_boot_steps(image, jobs['jobs'])
    if inputs is not None:
        image = inputs/'iso'/value['image']['name']
        require(image.is_file() and not image.is_symlink() and image.stat().st_size == value['image']['bytes']
                and digest_file(image) == value['image']['sha256'], 'Actual ISO bytes differ')
    return dict(image=value['image'], execution_sha=head, release_acceptance=False)


def digest_file(path):
    require(path.is_file() and not path.is_symlink(), 'Pinned source must be regular')
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for part in iter(lambda: stream.read(1024*1024), b''): value.update(part)
    return value.hexdigest()


def exclusive(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as stream: stream.write(data)


def report(value, context, png_names):
    require(type(value) is dict and set(value) == {'schema', 'context', 'status', 'phase', 'error_class',
        'checks', 'selinux', 'visual_review_required', 'release_acceptance'}, 'Report fields differ')
    require(value['schema'] == 'arctic-final-installed-ui-report-v1' and value['context'] == context
        and value['status'] in ('passed','failed') and value['phase'] in
        {'appearance','winner','custom','remove-apps','updates','lock','restore','complete'}
        and value['error_class'] in {'none','RuntimeError','TimeoutError','OSError','FileNotFoundError',
            'PermissionError','JSONDecodeError','KeyError','ValueError','OtherError'}
        and value['selinux'] == 'Enforcing' and value['visual_review_required'] is True
        and value['release_acceptance'] is False, 'Report context/security/status differs')
    checks = value['checks']; require(type(checks) is list and len(checks) <= 5, 'Report check bound differs')
    kinds = {
        'winner-keyboard-ui-selection': {'check','status','master_sha256','catalog_photos'},
        'custom-choice-survives-mode-change': {'check','status'},
        'remove-apps-routing-and-read-only-preview': {'check','status','preview_packages',
            'transaction_committed','original_ui_review_required'},
        'genuine-update-indicator-observation': {'check','status','ready','staged_packages',
            'signed_stage_and_cleared_reboot_proven'},
        'production-lock-clock-and-pam': {'check','status','secure','expected_clock_before',
            'expected_clock_after','original_clock_visual_review_required','authenticated_by_existing_host_fixture'}}
    seen = set()
    for item in checks:
        require(type(item) is dict and item.get('check') in kinds and item['check'] not in seen
            and set(item) == kinds[item['check']], 'Closed check fields differ')
        seen.add(item['check']); kind=item['check']
        require(item['status'] == ('observed' if kind == 'genuine-update-indicator-observation' else 'passed'),
                'Check status differs')
        if kind == 'winner-keyboard-ui-selection':
            require(item['catalog_photos'] == 19 and type(item['catalog_photos']) is int and item['master_sha256'] ==
                '7af8cb5ce0d87773109d759afdd1d14ef22ce7e84fdc1533da1539083cd11b0b', 'Winner identity differs')
        if kind == 'remove-apps-routing-and-read-only-preview':
            require(type(item['preview_packages']) is int and 0 <= item['preview_packages'] <= 10000
                and item['transaction_committed'] is False and item['original_ui_review_required'] is True,
                'Removal preview scope differs')
        if kind == 'genuine-update-indicator-observation':
            require(type(item['ready']) is bool and type(item['staged_packages']) is int
                and 0 <= item['staged_packages'] <= 10000 and item['signed_stage_and_cleared_reboot_proven'] is False,
                'Update observation scope differs')
        if kind == 'production-lock-clock-and-pam':
            require(item['secure'] is True and item['original_clock_visual_review_required'] is True
                and item['authenticated_by_existing_host_fixture'] is True
                and all(type(item[k]) is str and re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',item[k])
                        for k in ('expected_clock_before','expected_clock_after'))
                and item['expected_clock_before'] != item['expected_clock_after'], 'Lock proof differs')
    if value['status'] == 'passed':
        require(seen == set(kinds) and value['phase'] == 'complete' and value['error_class'] == 'none'
                and set(png_names) == set(load(ROOT/PREFIX/'guest.py','ui_guest_validation').PNG_NAMES),
                'Complete UI proof/capture inventory missing')
    return value


def decode(wire, context, scanner, output):
    """Screen the COMPLETE original UART before reading any protocol record."""
    require(type(wire) is bytes and 0 < len(wire) <= 256*1024*1024, 'UART bound differs')
    require(scanner.external_text(wire) == wire, 'Whole original screening altered bytes')
    rows = {'BEGIN': [], 'CHUNK': [], 'MANIFEST': [], 'END': []}
    for line in wire.decode('utf-8').splitlines():
        if line.startswith('ARCTIC-FINAL-UI-'):
            match = re.fullmatch(r'ARCTIC-FINAL-UI-(BEGIN|CHUNK|MANIFEST|END) (.+)', line)
            require(match is not None and len(line) <= 50000, 'Unknown/oversized transport record')
            rows[match[1]].append(strict_json(match[2]))
    require(rows['BEGIN'] == [context] and rows['END'] == [context] and len(rows['MANIFEST']) == 1,
            'Missing/duplicate/bad-bound original transport')
    inventory = rows['MANIFEST'][0]; guest=load(ROOT/PREFIX/'guest.py','ui_guest_inventory')
    require(type(inventory) is list and 1 <= len(inventory) <= 17, 'Member inventory bound differs')
    allowed = {'report.json'} | set(guest.PNG_NAMES)
    names = set(); decoded = {}; chunks = {}
    for row in rows['CHUNK']:
        require(type(row) is dict and set(row) == {'name','index','data'} and row['name'] in allowed
            and type(row['index']) is int and 0 <= row['index'] < 4096 and type(row['data']) is str,
            'Transport chunk fields differ')
        key=(row['name'],row['index']); require(key not in chunks, 'Duplicate original chunk')
        chunks[key]=base64.b64decode(row['data'],validate=True)
        require(0 < len(chunks[key]) <= 32768, 'Chunk bytes bound differs')
    total=0; consumed=set()
    for item in inventory:
        require(type(item) is dict and set(item) == {'name','bytes','sha256','compressed_bytes','chunks'}
            and item['name'] in allowed and item['name'] not in names and type(item['bytes']) is int
            and 0 < item['bytes'] <= (128*1024 if item['name']=='report.json' else guest.MAX_PNG)
            and type(item['compressed_bytes']) is int and 0 < item['compressed_bytes'] <= 9*1024*1024
            and type(item['chunks']) is int and 0 < item['chunks'] <= 4096
            and type(item['sha256']) is str and re.fullmatch('[0-9a-f]{64}',item['sha256']), 'Unsafe member')
        keys=[(item['name'],i) for i in range(item['chunks'])]
        require(all(k in chunks for k in keys), 'Missing original chunk')
        compressed=b''.join(chunks[k] for k in keys); consumed.update(keys)
        require(len(compressed)==item['compressed_bytes'], 'Compressed bytes differ')
        stream=zlib.decompressobj(); data=stream.decompress(compressed,item['bytes']+1)
        require(stream.eof and not stream.unused_data and not stream.unconsumed_tail
                and len(data)==item['bytes'] and hashlib.sha256(data).hexdigest()==item['sha256'],
                'Original expansion/hash/bound differs')
        if item['name']=='report.json': require(scanner.external_text(data)==data, 'Report screening altered bytes')
        decoded[item['name']]=data; names.add(item['name']); total+=len(data)
    require(set(chunks)==consumed and 'report.json' in decoded and total <= guest.MAX_TOTAL,
            'Unconsumed original chunks/missing report/aggregate bound')
    value=report(strict_json(decoded['report.json']),context,names-{'report.json'})
    # Validate all originals before creating the exclusively owned output folder.
    import io
    from PIL import Image
    for name,data in decoded.items():
        if name.endswith('.png'):
            require(data.startswith(b'\x89PNG\r\n\x1a\n'),'PNG signature differs')
            with Image.open(io.BytesIO(data)) as image:
                require(image.format=='PNG' and 640<=image.width<=3840 and 480<=image.height<=2160,
                        'PNG geometry differs'); image.verify()
    output.mkdir(mode=0o700)
    for name,data in decoded.items(): exclusive(output/name,data)
    return value, inventory
