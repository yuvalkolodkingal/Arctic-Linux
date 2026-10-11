#!/usr/bin/env python3
"""Exact fresh all-ADD admission for accepted BIOS strict evidence observation."""
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
BASE='0d2671e703cf6fe87e54d18604d50c10cc816a88'
BRANCH='codex/final-bios-csi-boundary-install-20261011'
MARKER='.github/final-bios-csi-boundary-install-20261011.activate'
WORKFLOW='Final exact-image BIOS with corrected complete CSI boundary'
ADDITIONS=set(['.github/workflows/final-bios-csi-boundary-install-20261011.yml', 'tools/complete-csi-boundary-source/README.md', 'tools/complete-csi-boundary-source/match-diagnostic.py', 'tools/complete-csi-boundary-source/scanner.py', 'tools/complete-csi-boundary-source/source-manifest.json', 'tools/complete-csi-boundary-source/test_source.py', 'tools/final-bios-csi-boundary-install/README.md', 'tools/final-bios-csi-boundary-install/common.py', 'tools/final-bios-csi-boundary-install/composition.py', 'tools/final-bios-csi-boundary-install/execution-manifest.json', 'tools/final-bios-csi-boundary-install/run.py', 'tools/final-bios-csi-boundary-install/test_composition.py'])
CORRECTION_TEST_SHA256='a85318c55fb463de0606b070b2f831a820f4cda42a94f75dc5ec3398d24c7436'
FILES=set(['.github/workflows/ci.yml', '.github/workflows/final-bios-csi-boundary-install-20261011.yml', '.github/workflows/final-bios-format-compatible-install-20261011.yml', '.github/workflows/final-bios-install-20261011.yml', '.github/workflows/final-bios-observed-install-20261011.yml', '.github/workflows/final-bios-public-shape-install-20261011.yml', '.github/workflows/final-bios-retained-install-20261011.yml', '.github/workflows/final-bios-strict-observed-install-20261011.yml', 'tools/complete-csi-boundary-source/README.md', 'tools/complete-csi-boundary-source/match-diagnostic.py', 'tools/complete-csi-boundary-source/scanner.py', 'tools/complete-csi-boundary-source/source-manifest.json', 'tools/complete-csi-boundary-source/test_source.py', 'tools/final-bios-csi-boundary-install/README.md', 'tools/final-bios-csi-boundary-install/common.py', 'tools/final-bios-csi-boundary-install/composition.py', 'tools/final-bios-csi-boundary-install/run.py', 'tools/final-bios-csi-boundary-install/test_composition.py', 'tools/final-bios-failure-evidence/README.md', 'tools/final-bios-failure-evidence/evidence.py', 'tools/final-bios-failure-evidence/execution-manifest.json', 'tools/final-bios-failure-evidence/test_evidence.py', 'tools/final-bios-failure-observer/composition.py', 'tools/final-bios-failure-observer/driver-entry.py', 'tools/final-bios-failure-observer/execution-manifest.json', 'tools/final-bios-failure-observer/observer.py', 'tools/final-bios-format-compatible-install/README.md', 'tools/final-bios-format-compatible-install/common.py', 'tools/final-bios-format-compatible-install/composition.py', 'tools/final-bios-format-compatible-install/execution-manifest.json', 'tools/final-bios-format-compatible-install/run.py', 'tools/final-bios-format-compatible-install/scanner.py', 'tools/final-bios-format-compatible-install/test_composition.py', 'tools/final-bios-install/common.py', 'tools/final-bios-install/compose.py', 'tools/final-bios-install/execution-manifest.json', 'tools/final-bios-install/guest.py', 'tools/final-bios-install/run.py', 'tools/final-bios-install/security.py', 'tools/final-bios-install/test_bios.py', 'tools/final-bios-observed-install/common.py', 'tools/final-bios-observed-install/execution-manifest.json', 'tools/final-bios-observed-install/run.py', 'tools/final-bios-public-shape-install/README.md', 'tools/final-bios-public-shape-install/common.py', 'tools/final-bios-public-shape-install/composition.py', 'tools/final-bios-public-shape-install/execution-manifest.json', 'tools/final-bios-public-shape-install/run.py', 'tools/final-bios-public-shape-install/test_composition.py', 'tools/final-bios-retained-install/README.md', 'tools/final-bios-retained-install/common.py', 'tools/final-bios-retained-install/execution-manifest.json', 'tools/final-bios-retained-install/run.py', 'tools/final-bios-retained-install/test_composition.py', 'tools/final-bios-same-match-public-shape-source/README.md', 'tools/final-bios-same-match-public-shape-source/match-diagnostic.py', 'tools/final-bios-same-match-public-shape-source/observer.py', 'tools/final-bios-same-match-public-shape-source/source-manifest.json', 'tools/final-bios-same-match-public-shape-source/test_source.py', 'tools/final-bios-strict-observed-install/README.md', 'tools/final-bios-strict-observed-install/common.py', 'tools/final-bios-strict-observed-install/execution-manifest.json', 'tools/final-bios-strict-observed-install/run.py', 'tools/final-bios-strict-observed-install/test_composition.py', 'tools/final-bios-strict-screen-observer/README.md', 'tools/final-bios-strict-screen-observer/execution-manifest.json', 'tools/final-bios-strict-screen-observer/match-diagnostic.py', 'tools/final-bios-strict-screen-observer/observer.py', 'tools/final-bios-strict-screen-observer/test_observer.py', 'tools/lib/container.sh', 'tools/lib/vmtest.py', 'tools/native-functional/fetch-image.py', 'tools/native-functional/screen-evidence.py', 'tools/performance/prepare-vm-tools.sh', 'tools/performance/producer-receipt.py', 'tools/test-install.sh'])
SOURCE_FILES={'profiles/ci/offline.toml','tools/native-functional/native_smoke.py','tools/dictation-qualification/guest_check.py','tools/dictation-qualification/contract.py','internal/installer/installer.go','modules/catalog.toml'}
RETENTION_BINDING={'source_sha': 'f68c4a71987a234d0d95da6ec6bf299373b58ecd', 'source_tree': 'eed37e1f28d98f458e2b758c2f6a1774cf76e2c7', 'source_payload_sha256': '9d6a6a9bef0d29e9a1cadee109d4e35e21fffd4f0892ab982e3371a0ea142aab', 'source_manifest_sha256': '99929b81fcbd1d9e734f8d3604bae54b998bdcafffa8c10c595e498885638c68', 'author_receipt_sha256': 'd729d5627d51e84bfde3ada0e15df842bc3cfc896448150cf7a6bc62ccbf03cb', 'independent_receipt_sha256': '6f9555cc26c5535f4af873d31091eacd4e515daee45a3410817d32895007c73d'}
STRICT_SCREEN_BINDING={'source_sha': 'af135de280ceb33b6bea02d0d89929da7981acf4', 'source_tree': 'd4309f25e41ecec15ac3fc0a4daf53ee124d097b', 'source_payload_sha256': 'c4ca79bb033404dd8af094098e6f10e43f0fd570cca3429d95fac39a59d53b91', 'source_manifest_sha256': 'c630bc4da55fd42002daa293f2bd3618061c2aaccbdda4efaf088abb1d73b5fc', 'author_receipt_sha256': '6bfac1762109814e31ac8ce6b1a856c1161d7d99f7723d77e93072f181ffa0df', 'independent_receipt_sha256': '02b15cdcb0e56ce69d3f846744d439fe1fee120e750ce17a3be633421ccf6aba'}
SCANNER_BINDING={'format_coverage': 'unchanged-b3-format-plus-complete-CSI-at-control-ordinary-boundary', 'original_operand_observed': False, 'release_acceptance': False, 'requested_path': 'tools/native-functional/screen-evidence.py', 'requested_sha256': '8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be', 'runtime_cause_proven': False, 'schema': 'arctic-bios-reviewed-complete-csi-boundary-map-v1', 'selected_Source_commit': '840756e6a64e30ec2f737c91bb7ebca9b4f2930f', 'selected_Source_path': 'tools/complete-csi-boundary-source/scanner.py', 'selected_git_blob': '2d362ccf2b8be2d915b8e57e0e92afe6f320cd34', 'selected_path': 'tools/complete-csi-boundary-source/scanner.py', 'selected_sha256': '8b9fbbe3bb9241dca8232e7cee61e05fec10bfbb0bc1e9d0d62dbfb7bda8e8ea', 'selected_Source_tree': 'ff99ac438b158de46d34660d05abe21ef2291c2f', 'parent_scanner_sha256': 'b3d56536397ff1c46caf082b97a070ff3eae383c2c277898c572cb34eb76f336', 'source_author_receipt_sha256': '748e8ec00a5f7db652acf51a1724856c39d8dd9983cf8398483be44738485d70', 'source_payload_sha256': 'aa05905785c83d0bac5ce6f79f4633511090be35a123d6b4fe1a53702b102340', 'source_independent_receipt_sha256': '49e2c600eba57e6fffe4616c0b9231a92561d53744343b4ec00004b2fd610e74', 'privacy_rules_preserved': True, 'raw_member_bytes_preserved': True, 'original_offsets_preserved': True, 'source_independent_supplement_sha256': 'c931d6bef50603bf15cb4b1da0a12c07b07905229eb1e1bc8e24874d7ad9d5b1'}
PUBLIC_SHAPE_BINDING={'actual_operand_observed': False, 'author_receipt_sha256': 'c6ccebb21155233cf0144f548680f7e17a1783fb546d7ad32b25c36426087a58', 'independent_receipt_sha256': '72ecb9abbd82f43cba31f36fd23319d0e265f7fbfe0cabc42926332116883f7a', 'privacy_policy_changed': False, 'release_acceptance': False, 'requested_helper_path': 'tools/final-bios-strict-screen-observer/match-diagnostic.py', 'requested_helper_sha256': '93b3b5ea0a3dab1cb9d31d485c15495cde7315a05d3965caf02c39101e13e89f', 'requested_observer_path': 'tools/final-bios-strict-screen-observer/observer.py', 'requested_observer_sha256': '181aab4e9966c30c783be917d99aedf804185ce33be2648af4906e96f69521cb', 'runtime_cause_proven': False, 'schema': 'arctic-bios-same-match-public-shape-csi-dependency-map-v1', 'selected_helper_path': 'tools/complete-csi-boundary-source/match-diagnostic.py', 'selected_helper_sha256': 'a92c57e53172efe8fbed8fce076341184e293ff9d525c1fda87678d6a9ba36c6', 'selected_observer_path': 'tools/final-bios-same-match-public-shape-source/observer.py', 'selected_observer_sha256': '144dfd018190701e8888a07e3e16f807de493f59a5b7aa2afffa36bbc8b1c3ee', 'source_payload_sha256': '6ce5b1c0d3819966a8fb4eaeb832484d93a0799f906295c8dcfcf9d1ad683774', 'source_sha': '4a884072e71354226b506f1057bb7f88f3934e24', 'source_tree': 'fe92ecef8cdfb93a321cd4e947d6a513f75ebb2d', 'alignment_Source_commit': '840756e6a64e30ec2f737c91bb7ebca9b4f2930f', 'alignment_Source_tree': 'ff99ac438b158de46d34660d05abe21ef2291c2f', 'alignment_author_receipt_sha256': '748e8ec00a5f7db652acf51a1724856c39d8dd9983cf8398483be44738485d70', 'alignment_payload_sha256': 'aa05905785c83d0bac5ce6f79f4633511090be35a123d6b4fe1a53702b102340', 'alignment_independent_receipt_sha256': '49e2c600eba57e6fffe4616c0b9231a92561d53744343b4ec00004b2fd610e74', 'parent_selected_helper_sha256': '2514be1c3ebcb3e5243cedb4dc221d850d2835c20b2b56e2db48b42843699505'}
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
    require(paths == ADDITIONS, 'Preparation scope differs')
    require(set(git('diff', '--no-renames', '--name-status', BASE, prep).splitlines()) ==
            {'A\t'+name for name in ADDITIONS}, 'Preparation modes/change kinds differ')
    expected_raw = set()
    for name in ADDITIONS:
        require(not git('ls-tree', BASE, '--', name), 'Preparation new path already exists')
        entry = git('ls-tree', prep, '--', name).split()
        require(len(entry) == 4 and entry[:2] == ['100644', 'blob'] and entry[3] == name,
                'Preparation regular mode/type differs')
        expected_raw.add(':000000 100644 ' + '0'*40 + ' ' + entry[2] + ' A\t' + name)
    require(not git('ls-tree', BASE, '--', MARKER) and not git('ls-tree', prep, '--', MARKER),
            'Preparation marker must be absent')
    require(set(git('diff', '--raw', '--no-abbrev', '--no-renames', BASE, prep).splitlines()) == expected_raw,
            'Preparation raw modes/change kinds differ')
    require(digest_file(ROOT/'tools/final-bios-install/test_bios.py') == CORRECTION_TEST_SHA256,
            'Corrected pending fixture bytes differ')
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
    require(type(value) is dict and set(value)=={'schema','ready','release_acceptance','image','execution_files','source_files','firmware','install_network','boot_network','install_timeout','harness_seconds','max_png','security_binding','observer_binding','retention_binding','strict_screen_binding','scanner_binding','public_shape_binding'},'BIOS manifest fields differ')
    require(value['schema']=='arctic-final-bios-csi-boundary-install-v1' and type(value['ready']) is bool and value['release_acceptance'] is False and value['firmware']=='bios' and value['install_network']==value['boot_network']=='offline','BIOS firmware/network/acceptance differs')
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
    require(value['observer_binding']=={'source_sha':'5c74a95aaf0d6dc4276b00c95473193540a03632','independent_receipt_sha256':'6cbd6f6f15aa8e74cbc1d4669bafd2a690546b844dd2407d04f3f920fd2d47b6','original_execution_sha':'1800239a3078d85f8e2cf666ba5ba702db352a09'},'Accepted finite Source observer binding differs')
    require(value['retention_binding']==RETENTION_BINDING,'Accepted retained Source binding differs')
    require(value['strict_screen_binding']==STRICT_SCREEN_BINDING,'Accepted strict screen Source binding differs')
    require(type(value['scanner_binding']) is dict and value['scanner_binding']==SCANNER_BINDING and all(type(value['scanner_binding'][k]) is type(v) for k,v in SCANNER_BINDING.items()),'Reviewed scanner Source mapping differs')
    require(type(value['public_shape_binding']) is dict and value['public_shape_binding']==PUBLIC_SHAPE_BINDING and all(type(value['public_shape_binding'][k]) is type(v) for k,v in PUBLIC_SHAPE_BINDING.items()),'Finite public Source shape dependency mapping differs')
    return value
