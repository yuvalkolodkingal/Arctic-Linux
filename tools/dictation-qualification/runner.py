#!/usr/bin/env python3
"""Run separate online/offline dictation tests against one exact retained ISO.

This lane never installs a replacement controller, runtime or model from its
data CD. Audio fixtures are public FLEURS samples. Only transcript-free checked
reports are copied to upload evidence; raw harness logs remain private.
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FILES = {'.github/workflows/dictation-candidate-20261009.yml',
         'tools/dictation-qualification/runner.py', 'tools/dictation-qualification/guest_check.py',
         'tools/dictation-qualification/contract.py', 'tools/dictation-accuracy/accuracy.py',
         'tools/dictation-accuracy/pins.json', 'tools/test-install.sh', 'tools/lib/vmtest.py',
         'tools/lib/container.sh', 'tools/performance/prepare-vm-tools.sh',
         'tools/native-functional/fetch-image.py'}

# Failure diagnostics are fixed labels, never exception text or command output.
HOST_STAGES = frozenset({
    'host-data', 'host-container', 'container-packages', 'container-audio',
    'container-data', 'container-disk', 'container-profile', 'container-driver',
    'container-complete', 'install-acquire', 'install-menu', 'install-live',
    'install-settle', 'install-terminal', 'install-start-marker',
    'install-start-observed', 'install-not-started', 'install-engine',
    'install-exit-observed', 'install-exit-missing-vm-running',
    'install-exit-missing-vm-exited', 'install-shutdown', 'install-cleanup',
    'boot-acquire', 'boot-menu', 'boot-unlock', 'boot-login', 'boot-settle',
    'boot-terminal', 'boot-collect', 'boot-collect-observed',
    'boot-collect-missing', 'boot-shutdown', 'boot-cleanup',
    'install-live-observed', 'install-live-unobserved',
    'install-terminal-attempt-one', 'install-terminal-attempt-two', 'install-terminal-attempt-three',
    'install-command-type-before', 'install-command-type-after',
    'install-command-enter-before', 'install-command-enter-after',
    'install-marker-wait-observed', 'install-marker-wait-unobserved',
    'install-marker-vm-running', 'install-marker-vm-exited', 'install-marker-vm-unknown',
    'install-command-shot-before', 'install-command-shot-after',
    'install-preterminal-capture-preserved', 'install-preterminal-capture-unavailable',
    'vm-acquire-qemu-exited', 'vm-acquire-no-qmp', 'vm-acquire-system-exit',
    'vm-acquire-file-missing', 'vm-acquire-permission-error', 'vm-acquire-os-error',
    'vm-acquire-json-error', 'vm-acquire-qmp-error', 'vm-acquire-keyboard-interrupt',
    'vm-acquire-other-error', 'vm-acquire-stderr-unobserved',
    'vm-acquire-enforce-host-unavailable', 'vm-acquire-enforce-only-spec-ctrl',
    'vm-acquire-enforce-floor-unavailable', 'vm-acquire-enforce-tcg-unavailable'})
PHASES = frozenset({'online-installed', 'offline-installed', 'recovery', 'recovered-offline'})
CATCH_STAGES = frozenset({'harness', 'report-live', 'report-installed', 'indicator'})
TRUSTED_ERRORS = {
    'Private dictation harness command failed': 'command-failed',
    'Missing or oversized private dictation serial log': 'serial-missing-or-oversized',
    'Missing/duplicate/oversized dictation report': 'report-missing-duplicate-or-oversized',
    'Missing dictation indicator receipt': 'indicator-receipt-missing',
    'Indicator receipt/report binding differs': 'indicator-binding-differs',
    'Indicator screenshot bytes differ': 'indicator-image-differs'}
TRUSTED_CONTRACT_ERRORS = frozenset({
    'report-fields', 'report-schema-scope', 'report-context-boot', 'report-controller',
    'report-profile-descriptor', 'report-hardware-fields', 'report-hardware-profile',
    'report-payload-pins', 'report-payload-pin-types', 'report-disk-type',
    'report-missing-duplicate-extra-gates', 'gate-fields', 'gate-status',
    'gate-safe-code', 'gate-observation-fields', 'report-status-derived',
    'image-dictation-gates-incomplete'})


def diagnostic(phase, stage, error, contract):
    if phase not in PHASES or stage not in CATCH_STAGES:
        return
    classes = {subprocess.TimeoutExpired: 'timeout-expired',
               subprocess.CalledProcessError: 'command-error', FileNotFoundError: 'file-not-found',
               PermissionError: 'permission-error', OSError: 'os-error',
               UnicodeDecodeError: 'unicode-error', json.JSONDecodeError: 'json-error',
               KeyError: 'key-error', TypeError: 'type-error', ValueError: 'value-error',
               RuntimeError: 'runtime-error', InterruptedError: 'interrupted-error',
               KeyboardInterrupt: 'keyboard-interrupt', SystemExit: 'system-exit'}
    code = 'contract-invalid' if type(error) is contract.Invalid else classes.get(type(error), 'other-error')
    args = BaseException.args.__get__(error)
    if type(args) is tuple and len(args) == 1 and type(args[0]) is str:
        if type(error) is RuntimeError and args[0] in TRUSTED_ERRORS:
            code = TRUSTED_ERRORS[args[0]]
        elif type(error) is contract.Invalid:
            code = args[0] if args[0] in TRUSTED_CONTRACT_ERRORS else 'contract-invalid'
    try:
        print('ARCTIC-DICTATION-HOST-FAILURE ' + phase + ' ' + stage + ' ' + code, flush=True)
    except (OSError, ValueError):
        pass  # Closed diagnostic stdout cannot change state or owned cleanup.


def relay_host_stages(path, token, phase):
    if phase not in PHASES or type(token) is not str or re.fullmatch('[0-9a-f]{32}', token) is None:
        return
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > 16 * 1024 * 1024:
            return
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            raw = stream.read(16 * 1024 * 1024 + 1)
        if len(raw) > 16 * 1024 * 1024:
            return
        prefix = b'ARCTIC-DICTATION-HOST-STAGE ' + token.encode('ascii') + b' '
        seen = set()
        allowed = {value.encode('ascii') for value in HOST_STAGES}
        for line in raw.splitlines(keepends=True):
            if not line.endswith(b'\n') or line.endswith(b'\r\n') or not line.startswith(prefix):
                continue
            code = line[len(prefix):-1]
            if code not in allowed or code in seen:
                continue
            seen.add(code)
            print('ARCTIC-DICTATION-HOST-PROGRESS ' + phase + ' ' + code.decode('ascii'), flush=True)
    except (OSError, ValueError):
        pass  # No private bytes, paths or errors are exported.
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def launch_diagnostic_read(root, name, maximum):
    """Read a fixed private regular file without following links or accepting races."""
    require(type(name) is str and name not in ('', '.', '..') and '/' not in name
            and type(maximum) is int and 0 < maximum <= 16 * 1024 * 1024, '')
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parent = os.fstat(directory)
        require(parent.st_uid in (0, os.geteuid()) and not parent.st_mode & 0o022, '')
        descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, 'rb') as stream:
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_uid in (0, os.geteuid())
                    and not before.st_mode & 0o022 and 0 < before.st_size <= maximum, '')
            data = stream.read(maximum + 1)
            after = os.fstat(stream.fileno())
        fields = lambda info: (info.st_dev, info.st_ino, info.st_uid, info.st_mode,
                               info.st_size, info.st_mtime_ns, info.st_ctime_ns)
        require(fields(before) == fields(after) == fields(os.stat(name, dir_fd=directory, follow_symlinks=False))
                and len(data) == before.st_size, '')
        current = os.stat(root, follow_symlinks=False)
        require((parent.st_dev, parent.st_ino, parent.st_uid, parent.st_mode)
                == (current.st_dev, current.st_ino, current.st_uid, current.st_mode)
                and stat.S_ISDIR(current.st_mode), '')
        return data
    finally:
        os.close(directory)


def launch_diagnostic_png(data):
    """Accept bounded, metadata-free RGB/RGBA PNGs; preserve their original bytes."""
    import struct
    import zlib
    require(type(data) is bytes and 8 < len(data) <= 4 * 1024 * 1024
            and data.startswith(b'\x89PNG\r\n\x1a\n'), '')
    at, compressed, dimensions, ended = 8, bytearray(), None, False
    while at < len(data):
        require(at + 12 <= len(data) and not ended, '')
        size, kind = struct.unpack('>I4s', data[at:at + 8])
        end = at + 12 + size
        require(end <= len(data) and kind in (b'IHDR', b'IDAT', b'IEND'), '')
        body = data[at + 8:end - 4]
        require(zlib.crc32(kind + body) & 0xffffffff == struct.unpack('>I', data[end - 4:end])[0], '')
        if kind == b'IHDR':
            require(at == 8 and dimensions is None and size == 13, '')
            width, height, depth, color, compression, filtering, interlace = struct.unpack('>IIBBBBB', body)
            require(0 < width <= 1920 and 0 < height <= 1080 and width * height <= 1920 * 1080
                    and depth == 8 and color in (2, 6) and (compression, filtering, interlace) == (0, 0, 0), '')
            dimensions = (width, height, 3 if color == 2 else 4)
        elif kind == b'IDAT':
            require(dimensions is not None and size > 0, '')
            compressed.extend(body)
        else:
            require(size == 0 and dimensions is not None and compressed, '')
            ended = True
        at = end
    require(ended, '')
    width, height, channels = dimensions
    row = width * channels + 1
    decoder = zlib.decompressobj()
    raw = decoder.decompress(compressed, row * height + 1)
    require(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data
            and len(raw) == row * height and all(raw[index] <= 4 for index in range(0, len(raw), row)), '')
    return width, height


def preserve_launch_diagnostic(vm, private_log, token, ctx, evidence, contract):
    """Failure-only pre-command diagnostic; it cannot satisfy any acceptance gate."""
    try:
        require(ctx['phase'] == 'online-installed' and type(token) is str
                and re.fullmatch('[0-9a-f]{32}', token), '')
        contract.context(ctx)
        raw = launch_diagnostic_read(private_log.parent, private_log.name, 16 * 1024 * 1024)
        prefix = b'ARCTIC-DICTATION-HOST-STAGE ' + token.encode() + b' '
        codes = {line[len(prefix):-1] for line in raw.splitlines(keepends=True)
                 if line.startswith(prefix) and line.endswith(b'\n') and not line.endswith(b'\r\n')}
        require(b'install-preterminal-capture-preserved' in codes
                and not codes & {b'install-marker-wait-observed', b'install-start-observed', b'install-engine', b'install-exit-observed'}, '')
        def strict_object(pairs):
            result = {}
            for key, value in pairs:
                require(key not in result, '')
                result[key] = value
            return result
        proof = json.loads(launch_diagnostic_read(vm, 'dictation-launch-desktop-receipt.json', 4096),
                           object_pairs_hook=strict_object)
        require(type(proof) is dict and set(proof) == {'schema', 'capture_stage', 'path', 'bytes', 'sha256', 'token_sha256'}
                and proof['schema'] == 'arctic-dictation-preterminal-capture-v1'
                and proof['capture_stage'] == 'before-first-terminal' and proof['path'] == 'dictation-launch-desktop.png'
                and type(proof['bytes']) is int and 8 < proof['bytes'] <= 4 * 1024 * 1024
                and type(proof['sha256']) is str and re.fullmatch('[0-9a-f]{64}', proof['sha256'])
                and proof['token_sha256'] == hashlib.sha256(token.encode()).hexdigest(), '')
        image = launch_diagnostic_read(vm, proof['path'], 4 * 1024 * 1024)
        require(len(image) == proof['bytes'] and hashlib.sha256(image).hexdigest() == proof['sha256'], '')
        width, height = launch_diagnostic_png(image)
        record = dict(schema='arctic-dictation-launch-diagnostic-v1', status='diagnostic_only', release_acceptance=False,
                      context=ctx, capture_stage=proof['capture_stage'], capture_nonce_sha256=proof['token_sha256'],
                      guest_command_start='unobserved',
                      execution_files={name: sha(ROOT / name) for name in
                                       ('tools/test-install.sh', 'tools/dictation-qualification/runner.py')},
                      image=dict(path='launch-preterminal-online-installed.png', bytes=len(image),
                                 sha256=proof['sha256'], width=width, height=height))
        created = []
        try:
            for name, content in ((record['image']['path'], image), ('launch-preterminal-online-installed.json',
                                   (json.dumps(record, sort_keys=True) + '\n').encode())):
                descriptor = os.open(evidence / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
                created.append(name)
                with os.fdopen(descriptor, 'wb') as stream:
                    stream.write(content)
        except BaseException:
            for name in created:
                (evidence / name).unlink(missing_ok=True)
            raise
        return True
    except Exception:
        return False  # Optional evidence cannot alter the original failure, cleanup or limits.


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def verify(args):
    manifest = json.loads(args.manifest.read_text())
    require(manifest.get('ready') is True and manifest.get('release_acceptance') is False,
            'Dictation qualification is disabled until exact image, fixtures and execution are reviewed')
    expected_env = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted',
                        GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',
                        GITHUB_REF='refs/heads/codex/qualification-dispatch-20261010',
                        GITHUB_WORKFLOW='Candidate dictation image qualification',
                        GITHUB_EVENT_NAME='push', GITHUB_RUN_ATTEMPT='1')
    require(all(os.environ.get(key) == value for key, value in expected_env.items()),
            'Requires reviewed disposable dictation Actions lane')
    require(manifest.get('hardware_profiles') == ['small-v2', 'turbo-q5-v3']
            and args.hardware_profile in manifest['hardware_profiles'], 'Unreviewed dictation hardware profile')
    image = manifest['image']
    require(re.fullmatch('[0-9a-f]{40}', image['source_sha'])
            and re.fullmatch('[0-9a-f]{64}', image['sha256'])
            and type(image['bytes']) is int and 0 < image['bytes'] < 2_000_000_000
            and type(image['run_id']) is int and image['run_id'] > 0
            and image['name'] == f"Arctic-Linux-1.2-candidate-{image['run_id']}-1-x86_64.iso",
            'Invalid exact candidate image identity')
    for tree, head in ((args.source, image['source_sha']), (ROOT, os.environ['GITHUB_SHA'])):
        require(subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True).strip() == head
                and not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain'], text=True).strip(),
                'Changed/dirty exact dictation source or execution checkout')
    require(set(manifest['execution_files']) == FILES, 'Dictation execution inventory differs')
    for name, expected in manifest['execution_files'].items():
        path = ROOT / name
        require(re.fullmatch('[0-9a-f]{64}', expected) and path.is_file()
                and not path.is_symlink() and sha(path) == expected, 'Changed dictation execution file: ' + name)
    iso = args.inputs / 'iso' / image['name']
    require(iso.is_file() and not iso.is_symlink() and iso.stat().st_size == image['bytes']
            and sha(iso) == image['sha256'], 'Actual ISO differs from reviewed image')
    require(re.fullmatch('[0-9a-f]{64}', manifest['fixture_manifest_sha256']), 'Unpinned dictation fixtures')
    accuracy = load_module('dictation_accuracy_fixture_guard', ROOT / 'tools/dictation-accuracy/accuracy.py')
    accuracy.load_fixtures(args.fixtures, manifest['fixture_manifest_sha256'])
    controller = args.source / 'packaging/dictation/dictation.py'
    require(controller.is_file() and not controller.is_symlink(), 'Built source lacks installed dictation controller')
    return manifest


def execute(argv, log, timeout, env, container):
    require(re.fullmatch('arctic-paired-dictation-[0-9a-f]{32}', container), 'Invalid owned VM container')
    with Path(log).open('xb') as output:
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT,
                                 start_new_session=True)
        try:
            require(child.wait(timeout=timeout) == 0, 'Private dictation harness command failed')
        except BaseException:
            try:
                subprocess.run(['docker', 'rm', '-f', container], stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=30)
            except (OSError, subprocess.TimeoutExpired):
                pass  # Still attempt owned host-process cleanup if Docker is unresponsive.
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=15)
            raise


def context(manifest, installation_id, phase, source, hardware_profile):
    image = manifest['image']
    return dict(schema='arctic-dictation-context-v2', phase=phase, hardware_profile=hardware_profile,
                source_sha=image['source_sha'], iso_sha256=image['sha256'], iso_bytes=image['bytes'],
                installation_id=installation_id, fixture_manifest_sha256=manifest['fixture_manifest_sha256'],
                checker_sha256=sha(HERE / 'guest_check.py'), contract_sha256=sha(HERE / 'contract.py'),
                accuracy_sha256=sha(ROOT / 'tools/dictation-accuracy/accuracy.py'),
                pins_sha256=sha(ROOT / 'tools/dictation-accuracy/pins.json'),
                child_exec_sha256=sha(source / 'packaging/dictation/child_exec.py'),
                controller_sha256=sha(source / 'packaging/dictation/dictation.py'))


def reports(vm, stage, ctx, evidence, contract, fixture_manifest=None):
    path = vm / ('serial-install.log' if stage == 'live' else 'serial-boot.log')
    require(path.is_file() and not path.is_symlink() and path.stat().st_size < 128 * 1024 * 1024,
            'Missing or oversized private dictation serial log')
    prefix = 'ARCTIC-DICTATION-QUALIFICATION '
    selected = [line[len(prefix):] for line in path.read_text(errors='strict').splitlines() if line.startswith(prefix)]
    require(len(selected) == 1 and len(selected[0]) < 2_000_000, 'Missing/duplicate/oversized dictation report')
    report = json.loads(selected[0])
    expected = dict(ctx, phase='live') if stage == 'live' else ctx
    # Preserve a structurally safe failed report for measured results and fixed
    # error codes; it still cannot satisfy the strict passing execution gate.
    contract.validate(report, expected, require_passed=False, fixture_manifest=fixture_manifest)
    name = ctx['phase'] + ('-live' if stage == 'live' else '') + '.json'
    write_json(evidence / name, report)
    contract.validate_report(report, expected, fixture_manifest=fixture_manifest)
    return dict(path=name, sha256=sha(evidence / name), phase=expected['phase'],
                installation_id=ctx['installation_id'], boot_id=report['boot_id'], status=report['status'])


def indicator(vm, ctx, evidence):
    receipt = vm / 'dictation-indicator-receipt.json'
    require(receipt.is_file() and not receipt.is_symlink() and receipt.stat().st_size < 16 * 1024,
            'Missing dictation indicator receipt')
    proof = json.loads(receipt.read_text())
    report = json.loads((evidence / (ctx['phase'] + '.json')).read_text())
    request = proof['request']
    require(set(proof) == {'request', 'path', 'sha256', 'iso_sha256', 'installation_id'}
            and set(request) == {'boot_id', 'installation_id', 'phase', 'desktop_uid', 'receiver_empty', 'capture_nonce'}
            and re.fullmatch('[0-9a-f]{32}', request['capture_nonce'])
            and request['phase'] == ctx['phase'] and request['installation_id'] == ctx['installation_id']
            and request['boot_id'] == report['boot_id'] and request['receiver_empty'] is True
            and proof['iso_sha256'] == ctx['iso_sha256'] and proof['installation_id'] == ctx['installation_id']
            and proof['path'] == 'dictation-indicator-' + ctx['phase'] + '.png'
            and any(gate['id'] == 'recording-status-published' and gate['status'] == 'passed'
                    and gate['observations'].get('sha256') == hashlib.sha256(request['capture_nonce'].encode()).hexdigest()
                    for gate in report['gates']), 'Indicator receipt/report binding differs')
    image = vm / proof['path']
    require(image.is_file() and not image.is_symlink() and image.stat().st_size < 4 * 1024 * 1024
            and sha(image) == proof['sha256'] and image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'),
            'Indicator screenshot bytes differ')
    shutil.copyfile(image, evidence / image.name)
    return proof


def run(args):
    manifest = verify(args)
    require(Path('/dev/kvm').is_char_device(), 'KVM unavailable')
    subprocess.check_output(['docker', 'info', '--format', '{{.ServerVersion}}'], timeout=30)
    contract = load_module('dictation_image_contract', HERE / 'contract.py')
    private = args.evidence.parent / ('dictation-private-' + args.hardware_profile)
    require(not private.exists(), 'Private dictation output must be unused')
    private.mkdir(mode=0o700)
    state = dict(schema='arctic-dictation-execution-v2', hardware_profile=args.hardware_profile,
                 status='prepared', release_acceptance=False,
                 image=manifest['image'], execution_checker_head=os.environ['GITHUB_SHA'],
                 fixture_manifest_sha256=manifest['fixture_manifest_sha256'], reports={}, installations={}, indicators={})
    prepared = None
    def save():
        state['recorded_at_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_json(args.evidence / 'execution.json', state)
    def interrupted(signum, _):
        raise InterruptedError('Dictation qualification interrupted: ' + str(signum))
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        shutil.copyfile(args.fixtures / 'fixtures.json', args.evidence / 'fixtures.json')
        save()
        container = 'arctic-paired-dictation-' + uuid.uuid4().hex
        env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container)
        execute(['bash', str(ROOT / 'tools/performance/prepare-vm-tools.sh'), str(private)],
                private / 'provision.log', 20 * 60, env, container)
        prepared = (private / 'vm-prepared-image-id.txt').read_text().strip()
        require(re.fullmatch('(sha256:)?[0-9a-f]{64}', prepared), 'Unpinned VM tool image')
        state['vm_tool_image_id'] = prepared
        for kind in ('online', 'offline'):
            state['installations'][kind] = str(uuid.uuid4())
        phases = [('online-installed', 'online', 'all', 'online', 'offline', 85 * 60),
                  ('offline-installed', 'offline', 'all', 'offline', 'offline', 65 * 60),
                  ('recovery', 'offline', 'boot', 'offline', 'online', 40 * 60),
                  ('recovered-offline', 'offline', 'boot', 'offline', 'offline', 65 * 60)]
        for phase, kind, stage, install_network, boot_network, limit in phases:
            verify(args)  # Exact ISO/source are rehashed immediately before every VM phase.
            payload = private / ('payload-' + phase)
            payload.mkdir(mode=0o700)
            shutil.copytree(HERE, payload / 'dictation-qualification', ignore=shutil.ignore_patterns('__pycache__', 'test_*.py'))
            shutil.copytree(ROOT / 'tools/dictation-accuracy', payload / 'dictation-accuracy',
                            ignore=shutil.ignore_patterns('__pycache__', 'test_*.py'))
            shutil.copytree(args.fixtures, payload / 'dictation-fixtures')
            ctx = context(manifest, state['installations'][kind], phase, args.source, args.hardware_profile)
            write_json(payload / 'dictation-context.json', ctx)
            checker = payload / 'guest-check.py'
            checker.write_text('import os,sys\nos.execv("/usr/bin/python3", ["/usr/bin/python3", '
                               '"/run/t/dictation-qualification/guest_check.py", sys.argv[1], "--disposable-guest"])\n')
            container = 'arctic-paired-dictation-' + uuid.uuid4().hex
            diagnostic_token = uuid.uuid4().hex
            env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container,
                       ARCTIC_FEDORA_IMAGE=prepared, ARCTIC_VM_TOOLS_PREPARED='1',
                       ARCTIC_DICTATION_BUNDLE=str(payload), ARCTIC_NATIVE_AUDIO_FIXTURE='1',
                       ARCTIC_NATIVE_DICTATION_CPU_PROFILE=args.hardware_profile,
                       ARCTIC_DICTATION_HOST_TOKEN=diagnostic_token)
            vm = private / ('vm-' + kind)
            # Reusing the same target and firmware variables proves offline recovery,
            # rather than substituting a second ready image or fresh disk.
            argv = ['bash', str(ROOT / 'tools/test-install.sh'), '--iso', str(args.inputs / 'iso' / manifest['image']['name']),
                    '--kvm', '--memory', '4096', '--smp', '2', '--boot-append', '', '--install-timeout', '2400',
                    '--stage', stage, '--install-network', install_network, '--boot-network', boot_network,
                    '--guest-check', str(checker), '--guest-check-interactive',
                    '--profile', str(args.source / 'profiles/ci/offline.toml'), '--out', str(vm)]
            state.update(status='running', current_phase=phase)
            save()
            errors = []
            try:
                execute(argv, private / (phase + '.log'), limit, env, container)
            except BaseException as error:
                errors.append('harness-failed')
                diagnostic(phase, 'harness', error, contract)
                relay_host_stages(private / (phase + '.log'), diagnostic_token, phase)
                preserve_launch_diagnostic(vm, private / (phase + '.log'), diagnostic_token, ctx, args.evidence, contract)
            # Preserve structurally safe reports even when the collector's
            # nonzero exit correctly prevents acceptance.
            for observed_stage in (('live', 'installed') if stage == 'all' else ('installed',)):
                key = phase + '-live' if observed_stage == 'live' else phase
                try:
                    state['reports'][key] = reports(vm, observed_stage, ctx, args.evidence, contract,
                                                   args.fixtures / 'fixtures.json')
                except BaseException as error:
                    errors.append(key + '-failed-or-unrun')
                    diagnostic(phase, 'report-' + observed_stage, error, contract)
            if phase in ('online-installed', 'recovered-offline'):
                try:
                    state['indicators'][phase] = indicator(vm, ctx, args.evidence)
                except BaseException as error:
                    errors.append(phase + '-indicator-failed-or-unrun')
                    diagnostic(phase, 'indicator', error, contract)
            save()
            require(not errors, 'Exact image dictation phase failed')
        contract.validate_execution(state, {name: json.loads((args.evidence / item['path']).read_text())
                                           for name, item in state['reports'].items()},
                                    fixture_manifest=args.fixtures / 'fixtures.json')
        state.update(status='exact_image_dictation_online_offline_local_sessions_passed', current_phase=None)
        save()
    except BaseException:
        # Do not include arbitrary command stderr, journals or a transcript in public evidence.
        state.update(status='failed_or_unrun', error='Qualification failed; inspect private Actions harness logs')
        save()
        raise
    finally:
        if prepared:
            subprocess.run(['docker', 'image', 'rm', prepared], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source', 'inputs', 'evidence', 'manifest', 'fixtures'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hardware-profile', choices=('small-v2', 'turbo-q5-v3'), required=True)
    args = parser.parse_args()
    for name in ('source', 'inputs', 'evidence', 'manifest', 'fixtures'):
        setattr(args, name, getattr(args, name).resolve())
    require(not args.evidence.exists(), 'Dictation evidence output must be unused')
    verify(args)
    args.evidence.mkdir(parents=True)
    run(args)


if __name__ == '__main__':
    main()
