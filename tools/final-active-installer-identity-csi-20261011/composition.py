#!/usr/bin/env python3
"""Additive, fail-closed admission for one exact active diagnostic lane."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import types

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BASE = 'c1463f3ecb8c8ec0a28801be3e649aad3ea5e9fe'
PREFIX = 'tools/final-active-installer-identity-csi-20261011/'
WORKFLOW = 'Candidate active installer fixed identity comparisons and bounded CSI qualification'
BRANCH = 'refs/heads/codex/active-installer-identity-csi-20261011'
OWN_FILES = tuple(PREFIX + n for n in ('composition.py', 'driver-entry.py',
    'driver-observed.py', 'run-live-observed.sh', 'privacy-entry.py',
    'match-diagnostic.py', 'source-ownership.py', 'scanner.py', 'test_composition.py', 'README.md')) + (
    '.github/workflows/active-installer-identity-csi-20261011.yml',)
RETAINED_EXTRA = ('tools/final-active-installer-greeting-csi-20261011/execution-manifest.json',
    '.github/qualification-20261011.active-greeting-csi')
MANIFEST_KEYS = {'schema', 'ready', 'release_acceptance', 'base', 'image',
    'execution_files', 'retained_execution_files', 'component_bindings', 'limits'}
COMPONENT_BINDINGS = {
    'qmp_source_sha': '3326d063d411ccc0ae791b02f85fa87fa209c143',
    'retained_qmp_driver_sha256': 'a01fd85e8207c879000bc8f706c820ae3dd7b4e7f3bddc8f5a98e227398abd84',
    'greeting_source_sha': 'bf0f051792ccaf7f34cae7f33d5220e8ebfc0b4d',
    'greeting_driver_sha256': '87f89f967174a8b8f7a982f2d28ae3beaa408725759c2cd54f3671b5abb3d6fd',
    'greeting_peer_sha256': 'e808ac3c20175a40b43d2b5e5272066b1c01cbf5fa5e300c79802567d53e256b',
    'identity_source_sha': 'c707dcf91a17e87677f6d2bbde034e2706add2e3',
    'identity_driver_sha256': '6d330c7e6257632b225abe587ab4a58de8734d3127ca3dbde17af4c633665094',
    'identity_peer_sha256': 'e73f417fda37b2b6915fb0794d842452bcfe11db0f12681f27ab4bdee884bf11',
    'qmp_peer_sha256': '1dae473946717f66ace59b63e29731d6fd2403a2fc2f3eeb09185a224d3e8569',
    'retained_readiness_driver_sha256': 'befc22c2f0226127c03df2261d33e23348b2e40059646911414ba21f29b871db',
    'readiness_peer_sha256': 'c8fe7c0a92485069a9097a5a7853e0f2d5f03a836cfd8b89c391958259d0dd8e',
    'privacy_source_sha': '338c0ed87f5b975623c63ca81439a84023266dc3',
    'privacy_scanner_sha256': '0c2176c4892e45e485eeac32f564fdfe9fb1619f142ac0b60babeed52924075f',
    'privacy_helper_sha256': '1de427723ec027da1cfac79bff7eada7b875f631c2fab26745b8cad2f71c851b',
    'privacy_ownership_sha256': '144dfd018190701e8888a07e3e16f807de493f59a5b7aa2afffa36bbc8b1c3ee',
    'privacy_peer_sha256': 'a3305b5495dbacee0ffb71437d5968ede524e9b8256a749ddeca179c6049a794',
    'privacy_peer_supplement_sha256': '455d6fd33a2e0d49896153838752ccca6a93f3758e5940d61cf6b33b1542ec68',
}
LIMITS = {'firmware': 'uefi', 'active_profile': True, 'harness_seconds': 4800,
    'workflow_timeout_minutes': 155, 'run_step_timeout_minutes': 130,
    'copy_write_bps': 8388608, 'console_identity_seconds': 45,
    'privacy_exemptions_added': 0}


def require(value):
    if not value:
        raise RuntimeError('Active diagnostic Source composition differs')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def raw_file(root, name):
    path = root / name
    require(type(name) is str and re.fullmatch(r'[.A-Za-z0-9_/-]+', name)
        and not name.startswith('/') and '..' not in name.split('/')
        and path.is_file() and not path.is_symlink())
    return path.read_bytes()


def load(raw, filename, name):
    module = types.ModuleType(name)
    module.__file__ = str(filename)
    exec(compile(raw, str(filename), 'exec', optimize=0), module.__dict__)
    return module


def checked(manifest, root=ROOT, ready=False):
    require(type(manifest) is dict and set(manifest) == MANIFEST_KEYS
        and manifest['schema'] == 'arctic-active-installer-identity-csi-composition-v1'
        and type(ready) is bool and type(manifest['ready']) is bool
        and manifest['ready'] is ready and manifest['release_acceptance'] is False
        and manifest['base'] == BASE and manifest['component_bindings'] == COMPONENT_BINDINGS
        and manifest['limits'] == LIMITS
        and all(type(manifest['limits'][k]) is type(v) for k, v in LIMITS.items()))
    retained = manifest['retained_execution_files']
    require(type(retained) is dict)
    old = json.loads(raw_file(root, RETAINED_EXTRA[0]))
    require(type(old) is dict and set(old) == MANIFEST_KEYS
        and old['schema'] == 'arctic-active-installer-greeting-csi-composition-v1'
        and old['ready'] is True and old['release_acceptance'] is False
        and manifest['image'] == old['image'])
    expected = dict(old['execution_files'])
    expected.update({name: sha(raw_file(root, name)) for name in RETAINED_EXTRA})
    require(retained == expected)
    files = manifest['execution_files']
    require(type(files) is dict and set(files) == set(expected) | set(OWN_FILES)
        and all(files.get(k) == v for k, v in expected.items()))
    for name, digest in files.items():
        require(type(digest) is str and re.fullmatch('[0-9a-f]{64}', digest)
            and sha(raw_file(root, name)) == digest)
    require(files[PREFIX + 'driver-observed.py'] == COMPONENT_BINDINGS['identity_driver_sha256']
        and files[PREFIX + 'scanner.py'] == COMPONENT_BINDINGS['privacy_scanner_sha256']
        and files[PREFIX + 'match-diagnostic.py'] == COMPONENT_BINDINGS['privacy_helper_sha256']
        and files[PREFIX + 'source-ownership.py'] == COMPONENT_BINDINGS['privacy_ownership_sha256'])
    old_shell = raw_file(root, 'tools/installer-qualification/run-live.sh')
    adapted_shell = raw_file(root, PREFIX + 'run-live-observed.sh')
    old_entry = b'python3 /execution/tools/installer-qualification/driver.py --out "$OUT" --firmware "$FIRMWARE"'
    new_entry = b'python3 /execution/tools/final-active-installer-identity-csi-20261011/driver-entry.py --out "$OUT" --firmware "$FIRMWARE"'
    require(old_shell.count(old_entry) == 1 and adapted_shell.count(new_entry) == 1
        and adapted_shell.replace(new_entry, old_entry, 1) == old_shell)
    return manifest


def driver(root=ROOT):
    # This canonical filename preserves the original sibling-controller and
    # exact caller checks. It does not claim the canonical old file was run.
    return load(raw_file(root, PREFIX + 'driver-observed.py'),
        root / 'tools/installer-qualification/driver.py', 'active_observed_driver')


def runner(manifest, root=ROOT, ready=False):
    checked(manifest, root, ready)
    old_dir = root / 'tools/installer-qualification'
    previous = {n: sys.modules.get(n) for n in ('contract', 'controller', 'evidence')}
    missing = {n for n in previous if n not in sys.modules}
    path_before = sys.path[:]
    try:
        sys.path.insert(0, str(old_dir))
        for name in previous:
            sys.modules[name] = load(raw_file(root, 'tools/installer-qualification/' + name + '.py'),
                old_dir / (name + '.py'), 'active_retained_' + name)
        original = load(raw_file(root, 'tools/installer-qualification/runner.py'),
            old_dir / 'runner.py', 'active_retained_runner')
    finally:
        sys.path[:] = path_before
        for name, value in previous.items():
            if name in missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value
    contract = original.E.active_contract()
    # Only the exact new Source inventory is substituted. Every acceptance
    # function Code and all original report/boot/security predicates remain.
    contract.EXECUTION_FILES = tuple(sorted(manifest['execution_files']))
    original.E.active_contract = lambda: contract
    original._driver = driver(root)
    original_execute = original.execute
    original_shell = str(old_dir / 'run-live.sh')
    new_shell = str(root / (PREFIX + 'run-live-observed.sh'))

    def execute(argv, log, seconds, cwd, env):
        if type(argv) is list and len(argv) > 1 and argv[:2] == ['bash', original_shell]:
            require(len(argv) == 9 and seconds == LIMITS['harness_seconds']
                and Path(cwd) == root)
            argv = ['bash', new_shell, *argv[2:]]
        return original_execute(argv, log, seconds, cwd, env)

    def verify(args, execution):
        require(getattr(args, 'active_profile', False) is True and execution == root
            and args.manifest == root / (PREFIX + 'execution-manifest.json'))
        current = json.loads(args.manifest.read_bytes())
        checked(current, root, True)
        require(current == manifest)
        require(os.environ.get('GITHUB_ACTIONS') == 'true'
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux'
            and os.environ.get('GITHUB_REF') == BRANCH
            and os.environ.get('GITHUB_WORKFLOW') == WORKFLOW
            and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1')
        image = current['image']
        original.C.require(original.C.is_hash(image['source_sha'], 40)
            and original.C.is_hash(image['sha256']) and type(image['bytes']) is int
            and 0 < image['bytes'] < 2_000_000_000
            and re.fullmatch(r'Arctic-Linux-1\.2-candidate-[0-9]+-1-x86_64\.iso', image['name']),
            'Invalid pinned image')
        for tree, expected in ((args.source, image['source_sha']), (execution, os.environ['GITHUB_SHA'])):
            original.C.require(subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'],
                text=True, timeout=30).strip() == expected and not subprocess.check_output(
                ['git', '-C', str(tree), 'status', '--porcelain'], text=True, timeout=30).strip(),
                'Dirty or changed image/execution checkout')
        iso = args.inputs / 'iso' / image['name']
        original.C.require(iso.is_file() and not iso.is_symlink()
            and iso.stat().st_size == image['bytes'] and original.sha(iso) == image['sha256'],
            'Actual final ISO bytes differ')
        return current, iso

    original.execute, original.verify = execute, verify
    return original


def main():
    manifest = json.loads((HERE / 'execution-manifest.json').read_bytes())
    original = runner(manifest, ready=True)
    return original.main()


if __name__ == '__main__':
    raise SystemExit(main())
