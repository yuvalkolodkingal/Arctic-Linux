#!/usr/bin/env python3
"""Disabled exact-final-image BIOS install/installed-boot source contract."""
import hashlib
import types
import sys
import json
import os
from pathlib import Path
import re
import stat
import subprocess
ROOT=Path(__file__).resolve().parents[2]
BASE='1a5c3cb0dc6783fc088b40e414fa7c766df99449'
BRANCH='codex/final-bios-install-20261011'
MARKER='.github/final-bios-install-20261011.activate'
WORKFLOW='Final exact-image BIOS install and installed boot'
PREFIX='tools/final-bios-install/'
ADDITIONS={'.github/workflows/final-bios-install-20261011.yml'} | {PREFIX+n for n in ('README.md','common.py','guest.py','compose.py','run.py','security.py','test_bios.py','execution-manifest.json')}
FILES={'.github/workflows/final-bios-install-20261011.yml'} | {PREFIX+n for n in ('common.py','guest.py','compose.py','run.py','security.py')} | {'tools/test-install.sh','tools/lib/container.sh','tools/lib/vmtest.py','tools/performance/prepare-vm-tools.sh','tools/native-functional/fetch-image.py','tools/performance/producer-receipt.py','tools/native-functional/screen-evidence.py'}
SOURCE_FILES={'profiles/ci/offline.toml','tools/native-functional/native_smoke.py','tools/dictation-qualification/guest_check.py','tools/dictation-qualification/contract.py','internal/installer/installer.go','modules/catalog.toml'}
IMAGE_KEYS={'source_sha','run_id','artifact_id','name','bytes','sha256','archive_bytes','archive_sha256','producer_mode','producer_receipt_sha256'}


def require(value, message):
    if not value:
        raise RuntimeError(message)

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True, timeout=30).strip()

def load(path, name, expected=None):
    raw=regular(path,1024*1024)
    if expected is not None:require(hashlib.sha256(raw).hexdigest()==expected,'Loaded pinned source bytes differ')
    module=types.ModuleType(name);module.__file__=str(path);sys.modules[name]=module
    exec(compile(raw,str(path),'exec'),module.__dict__)
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

def guard(value, source, inputs=None):
    manifest(value, True)
    require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_WORKFLOW') == WORKFLOW
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'Requires owned first hosted BIOS push')
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
    fetch = load(ROOT/'tools/native-functional/fetch-image.py', 'final_bios_fetch', value['execution_files']['tools/native-functional/fetch-image.py'])
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

def manifest(value, operational=False):
    require(type(value) is dict and set(value)=={'schema','ready','release_acceptance','image','execution_files','source_files','firmware','install_network','boot_network','install_timeout','harness_seconds','max_png','security_binding'},'BIOS manifest fields differ')
    require(value['schema']=='arctic-final-bios-install-v1' and type(value['ready']) is bool and value['release_acceptance'] is False and value['firmware']=='bios' and value['install_network']==value['boot_network']=='offline','BIOS firmware/network/acceptance differs')
    require(type(value['install_timeout']) is int and value['install_timeout']==2400 and type(value['harness_seconds']) is int and value['harness_seconds']==6600 and type(value['max_png']) is int and value['max_png']==4,'BIOS budgets differ')
    if operational:require(value['ready'] is True,'BIOS lane remains disabled')
    image=value['image']
    expected={'source_sha':'326690f173d4dc4f049f43e046c8380e66825a07','run_id':38102474066,'artifact_id':11689591362,'name':'Arctic-Linux-1.2-candidate-38102474066-1-x86_64.iso','bytes':1929719808,'sha256':'807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c','archive_bytes':1929907101,'archive_sha256':'3a8132aa4578fdb62b2aa1e3bf5c340229f1a483678d03ddf2c565fb39afadcd','producer_mode':'frozen-external-paired-v1','producer_receipt_sha256':'3034ea88d4ba1d1e434942f90c42b8057d3667ad2e7f6ee739b895ebdfc86d1d'}
    require(type(image) is dict and set(image)==IMAGE_KEYS and image==expected and all(type(image[k]) is int for k in ('run_id','artifact_id','bytes','archive_bytes')),'BIOS exact final F10 differs')
    require(type(value['execution_files']) is dict and set(value['execution_files'])==FILES and type(value['source_files']) is dict and set(value['source_files'])==SOURCE_FILES,'BIOS source inventories differ')
    for group in ('execution_files','source_files'):
        require(all(type(n) is str and not Path(n).is_absolute() and '..' not in Path(n).parts and n==Path(n).as_posix() and type(d) is str and re.fullmatch('[0-9a-f]{64}',d) for n,d in value[group].items()),'BIOS unsafe source pin')
    binding=value['security_binding']
    require(type(binding) is dict and set(binding)=={'source_sha','helper_sha256','independent_receipt_sha256'} and type(binding['source_sha']) is str and re.fullmatch('[0-9a-f]{40}',binding['source_sha']) and all(type(binding[k]) is str and re.fullmatch('[0-9a-f]{64}',binding[k]) for k in ('helper_sha256','independent_receipt_sha256')),'BIOS accepted security binding absent')
    return value
