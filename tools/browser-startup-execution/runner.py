#!/usr/bin/env python3
"""Disabled exact-image browser diagnostic on a wholly separate owned VM disk."""
import argparse
import base64
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import types
import uuid

REPO = 'yuvalkolodkingal/Arctic-Linux'
BRANCH = 'codex/browser-startup-diagnostic-20261011'
MARKER = '.github/browser-startup-diagnostic-20261011.activate'
WORKFLOW = '.github/workflows/browser-startup-diagnostic-20261011.yml'
MANIFEST = 'tools/browser-startup-execution/execution-manifest.json'
SOURCE = '326690f173d4dc4f049f43e046c8380e66825a07'
OBSERVER = '0e9df53b9d101ea74acbaaa318c0d35d4330b25d'
MAX_UART = 64 * 1024 * 1024
MAX_REPORT = 16 * 1024 * 1024
PREFIX = 'ARCTIC-BROWSER-STARTUP-REPORT'
IMAGE = {'archive_bytes': 1929907101,
         'archive_sha256': '3a8132aa4578fdb62b2aa1e3bf5c340229f1a483678d03ddf2c565fb39afadcd',
         'artifact_id': 11689591362, 'bytes': 1929719808,
         'name': 'Arctic-Linux-1.2-candidate-38102474066-1-x86_64.iso',
         'producer_mode': 'frozen-external-paired-v1',
         'producer_receipt_sha256': '3034ea88d4ba1d1e434942f90c42b8057d3667ad2e7f6ee739b895ebdfc86d1d',
         'run_id': 38102474066,
         'sha256': '807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',
         'source_sha': SOURCE}
CONDITIONS = {'firmware': 'uefi', 'memory_mib': 4096, 'vcpus': 2, 'cpu': 'max',
              'machine': 'q35', 'vga': 'virtio', 'acceleration': 'kvm',
              'boot_append': '', 'install_network': 'offline', 'boot_network': 'offline',
              'collector': 'console', 'profile': 'profiles/ci/offline.toml',
              'precondition_seconds': 45, 'repeated_launches': 3,
              'persistence_seconds': 5, 'browser': ['epiphany', '--new-window'],
              'workload': 'SourceA326_loopback_role_workload',
              'disk_scope': 'new_install_and_one_new_overlay_diagnostic_only'}
EXECUTION_FILES = {WORKFLOW, 'tools/browser-startup-execution/runner.py',
                   'tools/browser-startup-execution/guest-wrapper.py',
                   'tools/browser-startup-execution/test_runner.py',
                   'tools/browser-startup-execution/README.md'}
OBSERVER_FILES = {'tools/browser-startup/' + name for name in
                  ('profile.py', 'test_profile.py', 'README.md', 'execution-context.json', 'upstream-source.json')}
SOURCE_FILES = {'tools/test-install.sh', 'tools/performance/prepare-vm-tools.sh',
                'tools/performance/run-paired.py', 'tools/native-functional/fetch-image.py',
                'tools/native-functional/screen-evidence.py', 'profiles/ci/offline.toml',
                *{'tools/lib/' + name for name in ('arcticrepo.py', 'container.sh', 'iso_startup.py',
                                                 'tour-agent.sh', 'tour.py', 'vmtest.py')}}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def typed_equal(left, right):
    if type(left) is not type(right): return False
    if type(right) is dict:
        return set(left) == set(right) and all(typed_equal(left[key], value) for key, value in right.items())
    if type(right) is list:
        return len(left) == len(right) and all(typed_equal(a, b) for a, b in zip(left, right))
    return left == right


def read_json(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            require(key not in value, 'duplicate_json')
            value[key] = item
        return value
    def reject(_):
        raise RuntimeError('nonfinite_json')
    return json.loads(raw, object_pairs_hook=unique, parse_constant=reject)


def sha(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def safe_file(root, relative, limit):
    root = Path(root).absolute()
    path = root / relative
    require(path.resolve() == path and root.resolve() == root and path.is_relative_to(root), 'contained_file')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        before = os.fstat(source.fileno())
        require(stat.S_ISREG(before.st_mode) and before.st_uid == os.geteuid()
                and 0 < before.st_size <= limit, 'owned_file')
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())
        identity = lambda st: (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)
        require(len(raw) == before.st_size and identity(before) == identity(after), 'stable_file')
    return raw


def capture(argv, timeout=60, limit=2 * 1024 * 1024):
    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=True)
    require(len(result.stdout) <= limit and len(result.stderr) <= limit, 'command_bound')
    return result.stdout


def validate_manifest(manifest, executable=False):
    require(type(manifest) is dict and set(manifest) == {'schema', 'ready', 'release_acceptance',
        'performance_acceptance', 'image', 'observer', 'profile_binding', 'conditions', 'source_files',
        'execution_files', 'helper_files', 'observer_files', 'upstream_abi_limit'}, 'manifest_schema')
    require(manifest['schema'] == 'arctic-browser-startup-execution-v1'
            and type(manifest['ready']) is bool and manifest['release_acceptance'] is False
            and manifest['performance_acceptance'] is False and typed_equal(manifest['image'], IMAGE)
            and typed_equal(manifest['conditions'], CONDITIONS), 'manifest_identity')
    require(typed_equal(manifest['observer'], {'source_leaf': OBSERVER,
        'payload_sha256': '857fce0bcd269c2ceb16d0081ce3312dab994f827b4ed660a88ba09ee0bba4df',
        'peer_receipt_sha256': '4406662f6084fb944c5c3f971c63ec1c43bb47312d802d83ed4a635269226685'}), 'observer_identity')
    for key, paths in (('execution_files', EXECUTION_FILES), ('observer_files', OBSERVER_FILES)):
        require(type(manifest[key]) is dict and set(manifest[key]) == paths
                and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                        for value in manifest[key].values()), 'file_pin_inventory')
    require(type(manifest['source_files']) is dict and set(manifest['source_files']) == SOURCE_FILES
            and all(type(name) is str and re.fullmatch(r'(tools|profiles)/[A-Za-z0-9_./-]+', name)
                    and '..' not in Path(name).parts and type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                    for name, value in manifest['source_files'].items()), 'source_pins')
    require(type(manifest['helper_files']) is dict and set(manifest['helper_files']) == {'guest.py', 'causal.py'}
            and all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value)
                    for value in manifest['helper_files'].values()), 'helper_pins')
    require(manifest['upstream_abi_limit'] == 'GLib_2.88.0_header_byte_provenance_unretained_exact_Fedora_2.88.3_runtime_ABI_unmeasured', 'abi_limit')
    profile = manifest['profile_binding']
    if profile is not None:
        require(type(profile) is dict and set(profile) == {'mango_sha256', 'audit_sha256', 'helper_leaf',
                'peer_receipt_sha256', 'causal_sha256'}
                and type(profile['helper_leaf']) is str and re.fullmatch('[0-9a-f]{40}', profile['helper_leaf'])
                and all(type(profile[key]) is str and re.fullmatch('[0-9a-f]{64}', profile[key])
                        for key in profile if key != 'helper_leaf')
                and profile['causal_sha256'] == manifest['helper_files']['causal.py'], 'profile_binding')
    if executable:
        require(manifest['ready'] is True and profile is not None, 'disabled_or_profile_not_admitted')
    return manifest


def verify_tracked(root, name, expected=None, revision='HEAD'):
    raw = safe_file(root, name, 2 * 1024 * 1024)
    tracked = capture(['git', '-C', str(root), 'show', revision + ':' + name])
    row = capture(['git', '-C', str(root), 'ls-tree', revision, '--', name]).decode().strip().split()
    require(len(row) == 4 and row[0] in ('100644', '100755') and row[1] == 'blob'
            and raw == tracked and (expected is None or hashlib.sha256(raw).hexdigest() == expected), 'tracked_bytes')
    return raw


def activation_guard(root, manifest):
    validate_manifest(manifest, executable=True)  # No API/container/image acquisition before this.
    require(os.environ.get('GITHUB_REPOSITORY') == REPO and os.environ.get('GITHUB_EVENT_NAME') == 'push'
            and os.environ.get('GITHUB_REF') == 'refs/heads/' + BRANCH
            and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
            and os.environ.get('GITHUB_RUN_ATTEMPT') == '1', 'hosted_lane')
    event = read_json(Path(os.environ['GITHUB_EVENT_PATH']).read_bytes())
    head = capture(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip()
    parents = capture(['git', '-C', str(root), 'show', '-s', '--format=%P', 'HEAD']).decode().split()
    require(len(parents) == 1 and event['before'] == parents[0]
            and event['after'] == head == os.environ['GITHUB_SHA'], 'sole_reviewed_parent')
    require(not capture(['git', '-C', str(root), 'ls-tree', parents[0], '--', MARKER]).strip(),
            'activation_marker_must_be_new')
    addition = capture(['git', '-C', str(root), 'diff', '--raw', '--no-abbrev', parents[0], head, '--', MARKER])
    require(re.fullmatch(rb':000000 100644 0{40} [0-9a-f]{40} A\t' + re.escape(MARKER.encode()) + rb'\n', addition),
            'activation_marker_regular_add')
    require(capture(['git', '-C', str(root), 'diff', '--name-only', parents[0], head]).decode().splitlines() == [MARKER]
            and verify_tracked(root, MARKER) == (parents[0] + '\n').encode(), 'sole_activation_child')
    require(not capture(['git', '-C', str(root), 'status', '--porcelain']).strip(), 'clean_execution')
    require(read_json(verify_tracked(root, MANIFEST)) == manifest, 'manifest_blob')
    for key in ('execution_files', 'observer_files'):
        for name, checksum in manifest[key].items():
            verify_tracked(root, name, checksum)
    for name, checksum in manifest['helper_files'].items():
        verify_tracked(root, 'tools/performance/' + name, checksum)
    ref = read_json(capture(['gh', 'api', 'repos/' + REPO + '/git/ref/heads/' + BRANCH]))
    require(ref['ref'] == 'refs/heads/' + BRANCH and ref['object']['sha'] == head, 'unchanged_branch')
    return {'schema': 'arctic-browser-diagnostic-activation-v1', 'parent_sha': parents[0],
            'execution_sha': head, 'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': 1,
            'release_acceptance': False, 'performance_acceptance': False}


def verify_source(root, manifest):
    require(capture(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip() == SOURCE
            and not capture(['git', '-C', str(root), 'status', '--porcelain']).strip(), 'exact_clean_image_source')
    for name, checksum in manifest['source_files'].items():
        verify_tracked(root, name, checksum)


def verify_execution(root, manifest, activation):
    require(capture(['git', '-C', str(root), 'rev-parse', 'HEAD']).decode().strip() == activation['execution_sha']
            and not capture(['git', '-C', str(root), 'status', '--porcelain']).strip(), 'execution_source_unchanged')
    require(read_json(verify_tracked(root, MANIFEST)) == manifest, 'manifest_unchanged')
    for key in ('execution_files', 'observer_files'):
        for name, checksum in manifest[key].items(): verify_tracked(root, name, checksum)
    for name, checksum in manifest['helper_files'].items():
        verify_tracked(root, 'tools/performance/' + name, checksum)


def frozen_module(path, expected, name):
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected and not path.is_symlink(), 'frozen_module')
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def compose(root, manifest, activation, output):
    template_path = 'tools/browser-startup-execution/guest-wrapper.py'
    template = verify_tracked(root, template_path, manifest['execution_files'][template_path]).decode()
    sentinel = 'PAYLOAD = None  # HOST_COMPOSE_PINNED_PAYLOAD'
    require(template.count(sentinel) == 1, 'wrapper_template')
    context = read_json(verify_tracked(root, 'tools/browser-startup/execution-context.json',
                                     manifest['observer_files']['tools/browser-startup/execution-context.json']))
    require(context['ready'] is False and context['image'] is None, 'disabled_original_context')
    context.update(ready=True, image=manifest['image'], modules=manifest['helper_files'])
    blobs = {'profile.py': verify_tracked(root, 'tools/browser-startup/profile.py',
                                       manifest['observer_files']['tools/browser-startup/profile.py']),
             **{name: verify_tracked(root, 'tools/performance/' + name, checksum)
                for name, checksum in manifest['helper_files'].items()},
             'browser-startup-context.json': (json.dumps(context, sort_keys=True) + '\n').encode()}
    payload = {'context': context, 'execution': activation, 'files': {name:
               {'base64': base64.b64encode(raw).decode(), 'sha256': hashlib.sha256(raw).hexdigest(),
                'bytes': len(raw)} for name, raw in blobs.items()}}
    output.write_text(template.replace(sentinel, 'PAYLOAD = ' + repr(payload)))
    output.chmod(0o600)
    return context, {name: {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'mode': '0600', 'uid': 0}
                     for name, raw in blobs.items()}


def extract_report(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_UART, 'uart_bound')
    records = [line for line in raw.splitlines() if line.startswith(PREFIX.encode())]
    require(len(records) >= 3, 'missing_report')
    begin = re.fullmatch(PREFIX.encode() + rb' BEGIN ([1-9][0-9]{0,7}) ([0-9a-f]{64})', records[0])
    end = re.fullmatch(PREFIX.encode() + rb' END ([0-9a-f]{64})', records[-1])
    require(begin and end and begin[2] == end[1] and int(begin[1]) <= MAX_REPORT, 'report_envelope')
    pieces = []
    for index, line in enumerate(records[1:-1]):
        match = re.fullmatch(PREFIX.encode() + rb' DATA ([0-9]{1,6}) ([A-Za-z0-9+/]{1,1024}={0,2})', line)
        require(match and match[1] == str(index).encode() and (index == len(records)-3 or len(match[2]) == 1024), 'report_sequence')
        pieces.append(match[2])
    body = base64.b64decode(b''.join(pieces), validate=True)
    require(len(body) == int(begin[1]) and hashlib.sha256(body).hexdigest().encode() == begin[2], 'report_checksum')
    return body, read_json(body)


def bind_report(report, manifest, activation, staged):
    require(type(report) is dict and report.get('schema') == 'arctic-browser-startup-diagnostic-v1'
            and report.get('diagnostic_only') is True and report.get('benchmark_acceptance') is False
            and typed_equal(report.get('image'), manifest['image']) and report.get('modules') == manifest['helper_files']
            and report.get('collector_sha256') == manifest['observer_files']['tools/browser-startup/profile.py']
            and report.get('diagnostic_execution') == activation and report.get('staged_sources') == staged
            and type(report.get('repeated_launches')) is list and len(report['repeated_launches']) == 3,
            'report_execution_binding')
    for launch in [report['precondition']] + report['repeated_launches']:
        require(launch['mapping']['mango_sha256'] == manifest['profile_binding']['mango_sha256'], 'actual_mango_binding')


@contextmanager
def deferred_signals():
    pending = []; previous = {}
    def queued(signum, _): pending.append(signum)
    @contextmanager
    def transition():
        before = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
        try: yield
        finally: signal.pthread_sigmask(signal.SIG_SETMASK, before)
    try:
        with transition():
            for sig in (signal.SIGTERM, signal.SIGINT):
                previous[sig] = signal.signal(sig, queued)
        yield pending
    finally:
        with transition():
            for sig, handler in previous.items(): signal.signal(sig, handler)


def execute(argv, log, cwd, env, timeout, name=None):
    process = None; failed = False; pending = []; cleanup_errors = []
    with log.open('x') as output:
        os.chmod(log, 0o600)
        try:
            with deferred_signals() as pending:
                process = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output,
                                           stderr=subprocess.STDOUT, start_new_session=True)
            require(not pending, 'cancelled_acquisition')
            require(process.wait(timeout=timeout) == 0, 'owned_command_failed')
        except BaseException:
            failed = True
        finally:
            with deferred_signals() as cleanup_pending:
                if process is not None:
                    if process.poll() is None:
                        try: os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError: pass
                        except BaseException: cleanup_errors.append('term_failed')
                    try: process.wait(timeout=15)
                    except BaseException:
                        try: os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError: pass
                        except BaseException: cleanup_errors.append('kill_failed')
                        try: process.wait(timeout=15)
                        except BaseException: cleanup_errors.append('reap_failed')
                if name:
                    try:
                        subprocess.run(['docker', 'rm', '--force', name], stdout=output, stderr=output, timeout=30)
                        names = capture(['docker', 'ps', '--all', '--filter', 'name=' + name, '--format', '{{.Names}}'])
                        require(name.encode() not in names.splitlines(), 'owned_container_remains')
                    except BaseException: cleanup_errors.append('container_absence_unproved')
                failed |= bool(cleanup_pending or cleanup_errors)
    require(not failed, 'owned_command_or_cleanup_failed')


def idle_host():
    require(Path('/dev/kvm').is_char_device(), 'kvm_required')
    for entry in Path('/proc').glob('[0-9]*/comm'):
        try: require(not entry.read_text().startswith('qemu-system'), 'other_qemu_active')
        except OSError: pass


def private_original_receipts(work):
    # Original bytes stay private. Even on failure the receipt records their
    # actual identities; no raw UART, screenshots or arbitrary file names copy.
    names = ('image-fetch.log', 'tools.log', 'install-harness.log', 'boot-harness.log',
             'privacy-screen.log', 'installed-base/serial-install.log',
             'installed-base/qemu-install.log', 'installed-base/test.log',
             'diagnostic-boot/serial-boot.log', 'diagnostic-boot/qemu-boot.log',
             'diagnostic-boot/test.log')
    result = {}
    for name in names:
        path = work / name
        if not path.exists(): continue
        require(not path.is_symlink() and path.resolve() == path and path.is_file()
                and path.stat().st_size <= MAX_UART, 'private_original_bound')
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, 'rb') as source:
            before = os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode), 'private_original_type')
            checksum = hashlib.file_digest(source, 'sha256').hexdigest()
            after = os.fstat(source.fileno())
            identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
            require(identity(before) == identity(after), 'private_original_changed')
        result[name] = {'bytes': before.st_size, 'sha256': checksum, 'uploaded': False}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--guard-only', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = read_json(safe_file(root, MANIFEST, 32768))
    activation = activation_guard(root, manifest)
    if args.guard_only:
        print('ARCTIC-BROWSER-STARTUP-HOST exact_activation_admitted', flush=True)
        return
    require(args.source_root is not None, 'image_source_required')
    source_root = args.source_root.resolve(strict=True)
    verify_source(source_root, manifest)
    work = Path(os.environ['RUNNER_TEMP']) / 'arctic-browser-startup-private'
    publish = Path(os.environ['RUNNER_TEMP']) / 'arctic-browser-startup-screened'
    require(not work.exists() and not publish.exists(), 'new_diagnostic_output_required')
    work.mkdir(mode=0o700)
    state = {'schema': 'arctic-browser-startup-host-receipt-v1', 'release_acceptance': False,
             'performance_acceptance': False, 'diagnostic_only': True, 'activation': activation,
             'image': manifest['image'], 'conditions': manifest['conditions'], 'profile_binding': manifest['profile_binding'],
             'raw_originals_uploaded': False, 'source_sha': SOURCE, 'phase': 'created'}
    def save(phase):
        state['phase'] = phase
        (work / 'host-receipt.json').write_text(json.dumps(state, sort_keys=True) + '\n')
        (work / 'host-receipt.json').chmod(0o600)
        print('ARCTIC-BROWSER-STARTUP-HOST ' + phase, flush=True)
    def interrupt(*_): raise InterruptedError('owned_cancelled')
    for sig in (signal.SIGTERM, signal.SIGINT): signal.signal(sig, interrupt)
    tool_module = frozen_module(source_root / 'tools/performance/run-paired.py',
        manifest['source_files']['tools/performance/run-paired.py'], 'browser_owned_vm_cleanup')
    task_id = uuid.uuid4().hex; prepared = None; failure = None
    state['task_id'] = task_id
    baseline = dict(os.environ)
    # Remove optional diagnostic, renderer and preload variables. QEMU devices
    # and the desktop/browser environment remain the frozen Source defaults.
    for name in list(baseline):
        if name.startswith(('ARCTIC_', 'WLR_', 'WEBKIT_', 'GTK_', 'GDK_', 'LIBGL_')) or name == 'LD_PRELOAD':
            del baseline[name]
    baseline.update(CONTAINER_ENGINE='docker',
        ARCTIC_FEDORA_IMAGE='docker.io/library/fedora@sha256:43b29f65a41eb9c35e1cd5323e3bdf3b655c2357a9f4f1ff2f9c2798e5045d80')
    def vm_command(argv, label, timeout, prepared_tools=False):
        name = 'arctic-paired-' + task_id + '-' + uuid.uuid4().hex[:8]
        env = dict(baseline, ARCTIC_VM_CONTAINER_NAME=name)
        if prepared_tools: env.update(ARCTIC_FEDORA_IMAGE=prepared, ARCTIC_VM_TOOLS_PREPARED='1')
        execute(argv, work / (label + '.log'), source_root, env, timeout, name=name)
    try:
        save('fetch_exact_image')
        fetch_manifest = work / 'fetch-manifest.json'
        fetch_manifest.write_text(json.dumps({'ready': True, 'release_acceptance': False, 'image': manifest['image']}))
        execute([sys.executable, '-B', str(source_root / 'tools/native-functional/fetch-image.py'),
                 '--manifest', str(fetch_manifest), '--out', str(work / 'inputs')], work / 'image-fetch.log', source_root, baseline, 1200)
        iso = work / 'inputs' / 'iso' / IMAGE['name']
        require(iso.stat().st_size == IMAGE['bytes'] and sha(iso) == IMAGE['sha256'], 'whole_image_binding')
        idle_host(); save('prepare_private_vm_tools')
        vm_command(['bash', str(source_root / 'tools/performance/prepare-vm-tools.sh'), str(work), task_id], 'tools', 1200)
        prepared = safe_file(work, 'vm-prepared-image-id.txt', 80).decode().strip()
        state['prepared_image_id'] = prepared
        common = ['bash', str(source_root / 'tools/test-install.sh'), '--kvm', '--firmware', 'uefi',
                  '--memory', '4096', '--smp', '2', '--boot-append', '', '--collect-via', 'console',
                  '--profile', str(source_root / 'profiles/ci/offline.toml'),
                  '--install-network', 'offline', '--boot-network', 'offline']
        idle_host(); save('separate_offline_install')
        vm_command(common + ['--stage', 'install', '--iso', str(iso), '--install-timeout', '2400',
                             '--out', str(work / 'installed-base')], 'install-harness', 3600, True)
        require(b'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean' in safe_file(work, 'install-harness.log', MAX_UART), 'clean_install_poweroff')
        pristine = {name: sha(work / 'installed-base' / name) for name in ('target.qcow2', 'OVMF_VARS.fd')}
        state['pristine_installed_sources'] = pristine
        state['toolchain_sha256'] = sha(work / 'installed-base/vm-toolchain.txt')
        wrapper = work / 'guest-check.py'
        verify_execution(root, manifest, activation)
        context, staged = compose(root, manifest, activation, wrapper)
        context_path = work / 'diagnostic-context.json'; context_path.write_text(json.dumps(context, sort_keys=True) + '\n')
        state['composed_wrapper_sha256'] = sha(wrapper); state['staged_sources'] = staged
        idle_host(); save('separate_diagnostic_boot')
        vm_command(common + ['--stage', 'boot', '--guest-check', str(wrapper), '--fresh-boot-from', str(work / 'installed-base'),
            '--performance-context', str(context_path), '--out', str(work / 'diagnostic-boot')], 'boot-harness', 2400, True)
        require(sha(work / 'diagnostic-boot/vm-toolchain.txt') == state['toolchain_sha256'], 'unchanged_vm_toolchain')
        require({name: sha(work / 'installed-base' / name) for name in pristine} == pristine, 'pristine_base_unchanged')
        uart = safe_file(work, 'diagnostic-boot/serial-boot.log', MAX_UART)
        require(uart.count(b'ARCTIC-COLLECT-BEGIN') == 1 and uart.count(b'ARCTIC-COLLECT-END') == 1
                and uart.count(b'ARCTIC-INSTALLED-SMOKE-EXIT=0') == 1
                and b'ARCTIC-PERFORMANCE-CONSOLE-RESTORED' in uart, 'owned_guest_completion')
        body, report = extract_report(uart); bind_report(report, manifest, activation, staged)
        require(iso.stat().st_size == IMAGE['bytes'] and sha(iso) == IMAGE['sha256'], 'whole_image_unchanged')
        verify_source(source_root, manifest)
        verify_execution(root, manifest, activation)
        state['private_uart'] = {'bytes': len(uart), 'sha256': hashlib.sha256(uart).hexdigest()}
        state['collector_report'] = {'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
        picked = work / 'picked'; picked.mkdir(mode=0o700)
        (picked / 'report.json').write_bytes(body)
        save('collected_diagnostic_only')
    except BaseException as error:
        failure = error
        state['failure_type'] = type(error).__name__
        save('blocked_fixed_observation_only')
    finally:
        try:
            with deferred_signals() as pending:
                state['prepared_image_cleanup'] = tool_module.cleanup_prepared_image('docker', work, task_id, prepared)
                require(not pending, 'cleanup_interrupted')
                save(state['phase'])
        except BaseException as error:
            failure = error; state['failure_type'] = type(error).__name__
            state['prepared_image_cleanup'] = {'status': 'blocked'}
            save('blocked_cleanup_unproved')
        try:
            state['private_originals'] = private_original_receipts(work)
            save(state['phase'])
        except BaseException as error:
            failure = error; state['failure_type'] = type(error).__name__
            save('blocked_private_original_binding')
    if failure is not None: raise RuntimeError('diagnostic_blocked')
    save('source_bound_diagnostic_no_qualification')
    shutil.copyfile(work / 'host-receipt.json', work / 'picked/host-receipt.json')
    execute([sys.executable, '-B', str(source_root / 'tools/native-functional/screen-evidence.py'), '--preserve-original',
        '--source', str(work / 'picked'), '--out', str(publish)], work / 'privacy-screen.log', source_root, baseline, 120)
    require(publish.is_dir(), 'screened_output_required')


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('ARCTIC-BROWSER-STARTUP-HOST blocked', flush=True)
        sys.exit(1)
