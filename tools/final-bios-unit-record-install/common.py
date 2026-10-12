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
BASE='bc938f05b2e484b9f40dd6e5545157f699f2fd19'
BRANCH='codex/final-bios-unit-record-install-20261012'
MARKER='.github/final-bios-unit-record-install-20261012.activate'
WORKFLOW='Final exact-image BIOS unit record family observation'
ADDITIONS={'.github/workflows/final-bios-unit-record-install-20261012.yml', 'tools/unit-record-observation-source/README.md', 'tools/unit-record-observation-source/diagnostic.py', 'tools/unit-record-observation-source/observer.py', 'tools/unit-record-observation-source/review-receipt.json', 'tools/unit-record-observation-source/source-manifest.json', 'tools/unit-record-observation-source/test_source.py', 'tools/final-bios-unit-record-install/README.md', 'tools/final-bios-unit-record-install/common.py', 'tools/final-bios-unit-record-install/composition.py', 'tools/final-bios-unit-record-install/execution-manifest.json', 'tools/final-bios-unit-record-install/run.py', 'tools/final-bios-unit-record-install/test_composition.py'}
CORRECTION_TEST_SHA256='a85318c55fb463de0606b070b2f831a820f4cda42a94f75dc5ec3398d24c7436'
FILES={'tools/configured-broker-target-observation-source/source-manifest.json', 'tools/bounded-complete-csi-source/match-diagnostic.py', 'tools/performance/producer-receipt.py', 'tools/complete-csi-boundary-source/source-manifest.json', 'tools/final-bios-format-compatible-install/scanner.py', 'tools/final-bios-dnf-uid-install/run.py', 'tools/final-bios-install/security.py', 'tools/configured-broker-target-observation-source/test_source.py', 'tools/final-bios-install/run.py', '.github/workflows/final-bios-fresh-transport-install-20261012.yml', 'tools/final-bios-dnf-uid-install/execution-manifest.json', 'tools/final-bios-failure-observer/execution-manifest.json', 'tools/final-bios-install/guest.py', 'tools/bounded-complete-csi-source/test_source.py', 'tools/final-bios-dnf-uid-observation-source/match-diagnostic.py', 'tools/final-bios-strict-observed-install/common.py', 'tools/final-bios-csi-boundary-install/test_composition.py', '.github/workflows/ci.yml', 'tools/final-bios-failure-observer/driver-entry.py', 'tools/final-bios-failure-evidence/execution-manifest.json', 'tools/final-bios-format-compatible-install/composition.py', 'tools/final-bios-csi-boundary-install/common.py', 'tools/final-bios-format-compatible-install/run.py', 'tools/lib/vmtest.py', 'tools/final-bios-fresh-transport-install/test_composition.py', 'tools/final-bios-public-shape-install/run.py', '.github/workflows/final-bios-configured-target-install-20261012.yml', 'tools/final-bios-install/common.py', 'tools/final-bios-general-csi-install/run.py', 'tools/final-bios-failure-observer/observer.py', 'tools/final-bios-retained-install/README.md', '.github/workflows/final-bios-observed-install-20261011.yml', 'tools/final-bios-same-match-public-shape-source/observer.py', '.github/final-bios-fresh-transport-install-20261012.activate', 'tools/final-bios-strict-screen-observer/test_observer.py', 'tools/final-bios-install/test_bios.py', 'tools/final-bios-strict-screen-observer/README.md', 'tools/complete-csi-boundary-source/test_source.py', 'tools/final-bios-dnf-uid-install/README.md', 'tools/final-bios-public-shape-install/composition.py', 'tools/final-bios-failure-evidence/evidence.py', 'tools/configured-broker-target-observation-source/diagnostic.py', '.github/workflows/final-bios-strict-observed-install-20261011.yml', 'tools/final-bios-general-csi-install/README.md', 'tools/final-bios-general-csi-install/test_composition.py', '.github/workflows/final-bios-general-csi-install-20261011.yml', 'tools/final-bios-fresh-transport-install/execution-manifest.json', 'tools/configured-broker-target-observation-source/observer.py', 'tools/native-functional/fetch-image.py', 'tools/final-bios-observed-install/run.py', 'tools/final-bios-dnf-uid-install/common.py', 'tools/final-bios-format-compatible-install/README.md', 'tools/final-bios-same-match-public-shape-source/source-manifest.json', '.github/final-bios-dnf-uid-install-20261012.activate', 'tools/final-bios-csi-boundary-install/composition.py', '.github/workflows/final-bios-retained-install-20261011.yml', 'tools/final-bios-same-match-public-shape-source/README.md', 'tools/final-bios-failure-evidence/test_evidence.py', 'tools/bounded-complete-csi-source/execution-manifest.json', '.github/workflows/final-bios-format-compatible-install-20261011.yml', 'tools/final-bios-strict-observed-install/test_composition.py', 'tools/final-bios-observed-install/common.py', 'tools/final-bios-configured-target-install/common.py', 'tools/final-bios-failure-evidence/README.md', 'tools/final-bios-dnf-uid-observation-source/source-manifest.json', 'tools/final-bios-fresh-transport-install/README.md', 'tools/final-bios-configured-target-install/README.md', 'tools/final-bios-strict-observed-install/README.md', '.github/workflows/final-bios-csi-boundary-install-20261011.yml', 'tools/final-bios-install/compose.py', 'tools/final-bios-public-shape-install/test_composition.py', 'tools/final-bios-same-match-public-shape-source/match-diagnostic.py', 'tools/complete-csi-boundary-source/README.md', 'tools/final-bios-dnf-uid-install/test_composition.py', 'tools/complete-csi-boundary-source/match-diagnostic.py', 'tools/final-bios-general-csi-install/execution-manifest.json', 'tools/final-bios-configured-target-install/test_composition.py', 'tools/final-bios-csi-boundary-install/run.py', 'tools/final-bios-observed-install/execution-manifest.json', 'tools/final-bios-fresh-transport-install/common.py', 'tools/final-bios-strict-observed-install/run.py', 'tools/final-bios-public-shape-install/README.md', 'tools/performance/prepare-vm-tools.sh', 'tools/final-bios-dnf-uid-observation-source/test_source.py', 'tools/final-bios-failure-observer/composition.py', 'tools/final-bios-configured-target-install/composition.py', 'tools/lib/container.sh', 'tools/final-bios-strict-screen-observer/observer.py', 'tools/native-functional/screen-evidence.py', 'tools/final-bios-general-csi-install/composition.py', 'tools/bounded-complete-csi-source/scanner.py', 'tools/final-bios-public-shape-install/execution-manifest.json', 'tools/bounded-complete-csi-source/README.md', 'tools/final-bios-csi-boundary-install/README.md', 'tools/complete-csi-boundary-source/scanner.py', 'tools/final-bios-same-match-public-shape-source/test_source.py', 'tools/final-bios-strict-screen-observer/execution-manifest.json', 'tools/final-bios-dnf-uid-observation-source/README.md', '.github/workflows/final-bios-install-20261011.yml', 'tools/final-bios-format-compatible-install/test_composition.py', 'tools/configured-broker-target-observation-source/README.md', 'tools/final-bios-retained-install/run.py', 'tools/final-bios-install/execution-manifest.json', 'tools/final-bios-strict-screen-observer/match-diagnostic.py', 'tools/final-bios-fresh-transport-install/run.py', 'tools/final-bios-fresh-transport-install/composition.py', 'tools/final-bios-strict-observed-install/execution-manifest.json', 'tools/final-bios-general-csi-install/common.py', 'tools/test-install.sh', 'tools/final-bios-dnf-uid-install/composition.py', 'tools/final-bios-configured-target-install/run.py', 'tools/final-bios-retained-install/execution-manifest.json', 'tools/final-bios-dnf-uid-observation-source/observer.py', 'tools/final-bios-public-shape-install/common.py', 'tools/final-bios-format-compatible-install/common.py', '.github/workflows/final-bios-public-shape-install-20261011.yml', 'tools/final-bios-retained-install/test_composition.py', 'tools/final-bios-format-compatible-install/execution-manifest.json', 'tools/final-bios-retained-install/common.py', '.github/workflows/final-bios-dnf-uid-install-20261012.yml', '.github/workflows/final-bios-unit-record-install-20261012.yml', 'tools/unit-record-observation-source/README.md', 'tools/unit-record-observation-source/diagnostic.py', 'tools/unit-record-observation-source/observer.py', 'tools/unit-record-observation-source/review-receipt.json', 'tools/unit-record-observation-source/source-manifest.json', 'tools/unit-record-observation-source/test_source.py', 'tools/final-bios-unit-record-install/README.md', 'tools/final-bios-unit-record-install/common.py', 'tools/final-bios-unit-record-install/composition.py', 'tools/final-bios-unit-record-install/run.py', 'tools/final-bios-unit-record-install/test_composition.py'}
SOURCE_FILES={'profiles/ci/offline.toml','tools/native-functional/native_smoke.py','tools/dictation-qualification/guest_check.py','tools/dictation-qualification/contract.py','internal/installer/installer.go','modules/catalog.toml'}
RETENTION_BINDING={'source_sha': 'f68c4a71987a234d0d95da6ec6bf299373b58ecd', 'source_tree': 'eed37e1f28d98f458e2b758c2f6a1774cf76e2c7', 'source_payload_sha256': '9d6a6a9bef0d29e9a1cadee109d4e35e21fffd4f0892ab982e3371a0ea142aab', 'source_manifest_sha256': '99929b81fcbd1d9e734f8d3604bae54b998bdcafffa8c10c595e498885638c68', 'author_receipt_sha256': 'd729d5627d51e84bfde3ada0e15df842bc3cfc896448150cf7a6bc62ccbf03cb', 'independent_receipt_sha256': '6f9555cc26c5535f4af873d31091eacd4e515daee45a3410817d32895007c73d'}
STRICT_SCREEN_BINDING={'source_sha': 'af135de280ceb33b6bea02d0d89929da7981acf4', 'source_tree': 'd4309f25e41ecec15ac3fc0a4daf53ee124d097b', 'source_payload_sha256': 'c4ca79bb033404dd8af094098e6f10e43f0fd570cca3429d95fac39a59d53b91', 'source_manifest_sha256': 'c630bc4da55fd42002daa293f2bd3618061c2aaccbdda4efaf088abb1d73b5fc', 'author_receipt_sha256': '6bfac1762109814e31ac8ce6b1a856c1161d7d99f7723d77e93072f181ffa0df', 'independent_receipt_sha256': '02b15cdcb0e56ce69d3f846744d439fe1fee120e750ce17a3be633421ccf6aba'}
SCANNER_BINDING={'format_coverage': 'unchanged-privacy-rules-bounded-complete-CSI-separation-with-retained-ESC-display-branch', 'original_operand_observed': False, 'release_acceptance': False, 'requested_path': 'tools/native-functional/screen-evidence.py', 'requested_sha256': '8754ad7f3a97803ce1d84fd889667853dd5d407a8907adfb52afd6a7d41067be', 'runtime_cause_proven': False, 'schema': 'arctic-bios-reviewed-bounded-complete-csi-map-v1', 'selected_Source_commit': '338c0ed87f5b975623c63ca81439a84023266dc3', 'selected_Source_path': 'tools/bounded-complete-csi-source/scanner.py', 'selected_git_blob': 'f95aba37009b242c1226afb6a8a6e8ba02a9f1bd', 'selected_path': 'tools/bounded-complete-csi-source/scanner.py', 'selected_sha256': '0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f', 'selected_Source_tree': 'cf32bc639e32a38955631915c819956f4b26f7e5', 'parent_scanner_sha256': '8b9fbbe3bb9241dca8232e7cee61e05fec10bfbb0bc1e9d0d62dbfb7bda8e8ea', 'source_author_receipt_sha256': 'd5c9535fc4f8bd96b9a1e8d5cd380d9ae113a22a16050c9d22953d236dbbc1b8', 'source_payload_sha256': '4666e5bdbc93ecd72ad4f9328a1b45fd2db8cc6185ea76927e2cd6e413b45bb5', 'source_independent_receipt_sha256': 'a3305b5495dbacee0ffb71437d5968ede524e9b8256a749ddeca179c6049a794', 'privacy_rules_preserved': True, 'raw_member_bytes_preserved': True, 'original_offsets_preserved': True, 'source_independent_supplement_sha256': '455d6fd33a2e0d49896153838752ccca6a93f3758e5940d61cf6b33b1542ec68', 'source_author_supplement_sha256': '317bf0006b32c79bbf81fdade8d6b6a7bb7b84e19236659000377b3c2c17eea3', 'source_prior_supplement_sha256': 'c931d6bef50603bf15cb4b1da0a12c07b07905229eb1e1bc8e24874d7ad9d5b1'}
PUBLIC_SHAPE_BINDING={'actual_operand_observed': False, 'author_receipt_sha256': 'e31509bfb60fcfe24de24ee5fb84d1666b391ee305e3b4cfce1d3e77d7be83ab', 'independent_receipt_sha256': '15a8ece86f121a06d69824a023ab29af88134ce30b9b1da7e9198e4cff894748', 'privacy_policy_changed': False, 'release_acceptance': False, 'requested_helper_path': 'tools/final-bios-strict-screen-observer/match-diagnostic.py', 'requested_helper_sha256': '93b3b5ea0a3dab1cb9d31d485c15495cde7315a05d3965caf02c39101e13e89f', 'requested_observer_path': 'tools/final-bios-strict-screen-observer/observer.py', 'requested_observer_sha256': '181aab4e9966c30c783be917d99aedf804185ce33be2648af4906e96f69521cb', 'runtime_cause_proven': False, 'schema': 'arctic-bios-same-match-exact-public-DNF-UID-dependency-map-v1', 'selected_helper_path': 'tools/final-bios-dnf-uid-observation-source/match-diagnostic.py', 'selected_helper_sha256': '0d96f7bb82c9b38b64da494113fed52476b4af3c67f34b86566cfe3cdfa5206e', 'selected_observer_path': 'tools/final-bios-dnf-uid-observation-source/observer.py', 'selected_observer_sha256': 'bf0e8c69558019bd41caffc9f7ed716daa55c9957ed6513ce468e18c655be994', 'source_payload_sha256': '947613c83bf1385e73e4c00c24ce08f5f9741b9945c6e5fe8dbf8b9404e3a58f', 'source_sha': '0b40234ebc8a8b6f4555175bce2a95bfd9ecb12d', 'source_tree': '7f6cf8ca67aacd1385a91ce34e86458c2ec942e7', 'alignment_Source_commit': '338c0ed87f5b975623c63ca81439a84023266dc3', 'alignment_Source_tree': 'cf32bc639e32a38955631915c819956f4b26f7e5', 'alignment_author_receipt_sha256': 'd5c9535fc4f8bd96b9a1e8d5cd380d9ae113a22a16050c9d22953d236dbbc1b8', 'alignment_payload_sha256': '4666e5bdbc93ecd72ad4f9328a1b45fd2db8cc6185ea76927e2cd6e413b45bb5', 'alignment_independent_receipt_sha256': 'a3305b5495dbacee0ffb71437d5968ede524e9b8256a749ddeca179c6049a794', 'parent_selected_helper_sha256': '1de427723ec027da1cfac79bff7eada7b875f631c2fab26745b8cad2f71c851b', 'alignment_independent_supplement_sha256': '455d6fd33a2e0d49896153838752ccca6a93f3758e5940d61cf6b33b1542ec68', 'alignment_author_supplement_sha256': '317bf0006b32c79bbf81fdade8d6b6a7bb7b84e19236659000377b3c2c17eea3', 'parent_selected_observer_sha256': '144dfd018190701e8888a07e3e16f807de493f59a5b7aa2afffa36bbc8b1c3ee', 'parent_shape_Source_commit': '4a884072e71354226b506f1057bb7f88f3934e24', 'parent_shape_Source_tree': 'fe92ecef8cdfb93a321cd4e947d6a513f75ebb2d', 'parent_shape_independent_receipt_sha256': '72ecb9abbd82f43cba31f36fd23319d0e265f7fbfe0cabc42926332116883f7a', 'public_DNF_format_proof_sha256': '03d813bff505d8ecc081713f7eed577cf3d779a18048676c76bfdee04ae9b378', 'same_owned_original_records_rejected_Match': True, 'one_fixed_boolean_only': True, 'runtime_DNF_process_or_locale_proven': False, 'privacy_allowance': False}
UNIT_RECORD_BINDING={'alignment_parent_helper_sha256': '1de427723ec027da1cfac79bff7eada7b875f631c2fab26745b8cad2f71c851b', 'diagnostic_path': 'tools/unit-record-observation-source/diagnostic.py', 'diagnostic_sha256': 'cc521c0e7d4fe4c6b95b62b3a53a930b916ffa1dd607eac601d4c200740fb5cc', 'enabled': True, 'privacy_admission_changed': False, 'private_excerpt_exported': False, 'private_numeric_field_exported': False, 'private_operand_digest_exported': False, 'private_operand_exported': False, 'private_operand_length_exported': False, 'record_family_id_count': 5, 'release_acceptance': False, 'requested_observer_path': 'tools/broker-shape-observation-source/observer.py', 'requested_observer_sha256': '0c6c2cc1543fbe8d92e93d0883b641c8f98a3bb27b9d7d2ebe2f56c6fddf4dfd', 'runtime_cause_proven': False, 'same_owned_rejection_only': True, 'scanner_changed': False, 'schema': 'arctic-bios-unit-record-family-dependency-map-v1', 'selected_helper_path': 'tools/final-bios-dnf-uid-observation-source/match-diagnostic.py', 'selected_helper_sha256': '0d96f7bb82c9b38b64da494113fed52476b4af3c67f34b86566cfe3cdfa5206e', 'selected_observer_path': 'tools/unit-record-observation-source/observer.py', 'selected_observer_sha256': '82bc6c8dda16282f068c936a6edc928924ff4160f6f51161ab2a2ec1430ac2b5', 'source_member_id_count': 2, 'unit_family_id_count': 1, 'whole_alignment_function_sha256': '64354580bd3b1f0304e4fc2d78d420f7690c47130f5a8a28ec945be9ba1311ce', 'source_commit': '6b2cc6325519fca979c7c42fd80890caaa1c9b75', 'source_tree': 'edeab87d75937c883342be28ce5ac534078b2e6c', 'source_manifest_path': 'tools/unit-record-observation-source/source-manifest.json', 'source_manifest_sha256': '2b54263f22156a18b61a3cf63a81489a9dd67c2c6f9f2f1121c3c20d45395045', 'source_review_receipt_path': 'tools/unit-record-observation-source/review-receipt.json', 'source_review_receipt_sha256': '5ec2354833e21604d8fe6cf748bb3bbf77a06caef5b58918e2cf8abeb3cd49af'}
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
    require(type(value) is dict and set(value)=={'schema','ready','release_acceptance','image','execution_files','source_files','firmware','install_network','boot_network','install_timeout','harness_seconds','max_png','security_binding','observer_binding','retention_binding','strict_screen_binding','scanner_binding','public_shape_binding','unit_record_binding'},'BIOS manifest fields differ')
    require(value['schema']=='arctic-final-bios-unit-record-install-v1' and type(value['ready']) is bool and value['release_acceptance'] is False and value['firmware']=='bios' and value['install_network']==value['boot_network']=='offline','BIOS firmware/network/acceptance differs')
    require(type(value['install_timeout']) is int and value['install_timeout']==2400 and type(value['harness_seconds']) is int and value['harness_seconds']==6600 and type(value['max_png']) is int and value['max_png']==4,'BIOS budgets differ')
    if operational:require(value['ready'] is True,'BIOS lane remains disabled')
    image=value['image']
    expected={'source_sha':'326690f173d4dc4f049f43e046c8380e66825a07','run_id':38102474066,'artifact_id':11689591362,'name':'Arctic-Linux-1.2-candidate-38102474066-1-x86_64.iso','bytes':1929719808,'sha256':'807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c','archive_bytes':1929907101,'archive_sha256':'3a8132aa4578fdb62b2aa1e3bf5c340229f1a483678d03ddf2c565fb39afadcd','producer_mode':'frozen-external-paired-v1','producer_receipt_sha256':'3034ea88d4ba1d1e434942f90c42b8057d3667ad2e7f6ee739b895ebdfc86d1d'}
    if image is None:
        require(value['ready'] is False and operational is False,'Disabled BIOS image placeholder differs')
    else:
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
    require(type(value['unit_record_binding'])is dict and value['unit_record_binding']==UNIT_RECORD_BINDING and all(type(value['unit_record_binding'][key])is type(item)for key,item in UNIT_RECORD_BINDING.items()),'Unit record Source dependency mapping differs')
    return value
