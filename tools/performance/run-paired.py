#!/usr/bin/env python3
"""Sequential offline KVM installs and three interleaved boots of each image."""
import argparse
from contextlib import contextmanager
import contextlib
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import uuid
import types

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SHA256 = '054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f'
BASELINE_PROFILE_SHA256 = 'e6b9aa317521bdaaaf343629bc5de8b914b0a5f58387a0c9fe31754f17c0d20d'


@contextlib.contextmanager
def prepared_signal_transition():
    """Brief parent-only mask for atomic handler changes, never across spawn."""
    previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, previous)


@contextlib.contextmanager
def defer_prepared_signals():
    pending, previous = [], {}
    def queued(signum, frame):
        pending.append(signum)
    try:
        with prepared_signal_transition():
            for signum in (signal.SIGTERM, signal.SIGINT):
                previous[signum] = signal.signal(signum, queued)
        yield pending
    finally:
        with prepared_signal_transition():
            for signum, handler in previous.items():
                signal.signal(signum, handler)


def prepared_image_id(value):
    if not isinstance(value, str) or not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}', value):
        raise ValueError('Invalid prepared image identity')
    return 'sha256:' + value.removeprefix('sha256:')


def prepared_read(path, limit=4096):
    """Read only a small regular receipt; never follow a substituted symlink."""
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError('Unsafe prepared image receipt')
        content = source.read(limit + 1)
        if len(content) > limit:
            raise ValueError('Oversized prepared image receipt')
        return content


def prepared_json(content):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate prepared image JSON field')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite prepared image JSON field')
    return json.loads(content, object_pairs_hook=pairs, parse_constant=invalid)


def prepared_owner(folder, task_id):
    owner = prepared_json(prepared_read(folder/'vm-prepared-image-owner.json'))
    if (not re.fullmatch('[0-9a-f]{32}', task_id)
            or not isinstance(owner, dict)
            or set(owner) != {'schema', 'release_acceptance', 'task_id', 'container', 'base_id'}
            or owner['schema'] != 'arctic-paired-test-image-owner-v1'
            or owner['release_acceptance'] is not False or owner['task_id'] != task_id
            or not isinstance(owner['container'], str)
            or not re.fullmatch('arctic-paired-' + task_id + '-[0-9a-f]{8}', owner['container'])):
        raise ValueError('Prepared image ownership receipt differs from this task')
    prepared_image_id(owner['base_id'])
    return owner


def cleanup_prepared_image(engine, folder, task_id, known_id=None):
    """Recover only this task's immutable labeled image, including lost replies."""
    try:
        owner = prepared_owner(folder, task_id)
    except FileNotFoundError:
        if known_id is not None:
            raise ValueError('Acquired image has no prepared ownership receipt')
        return dict(status='not_acquired', image_id=None, errors=[])
    expected_labels = {'org.arctic.test.vm-tools.scope':'paired-v1',
        'org.arctic.test.vm-tools.task':task_id,
        'org.arctic.test.vm-tools.container':owner['container'],
        'org.arctic.test.vm-tools.base':owner['base_id']}
    def command(argv):
        result = subprocess.run([engine] + argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, timeout=30, check=True)
        if len(result.stdout) > 64*1024 or len(result.stderr) > 64*1024:
            raise ValueError('Oversized prepared image engine reply')
        return result.stdout
    identifiers = []
    try:
        raw_id = prepared_read(folder/'vm-prepared-image-id.txt', 80).decode('ascii')
        if not re.fullmatch(r'(?:sha256:)?[0-9a-f]{64}\n', raw_id):
            raise ValueError('Invalid prepared image ID receipt')
        identifiers.append(prepared_image_id(raw_id[:-1]))
    except FileNotFoundError:
        pass
    if known_id is not None:
        identifier = prepared_image_id(known_id)
        if identifiers and identifiers != [identifier]:
            raise ValueError('Prepared image identity handoff differs from receipt')
        identifiers = [identifier]
    if not identifiers:
        raw = command(['image', 'ls', '--no-trunc', '--quiet',
            '--filter', 'label=org.arctic.test.vm-tools.scope=paired-v1',
            '--filter', 'label=org.arctic.test.vm-tools.task=' + task_id])
        identifiers = list(dict.fromkeys(prepared_image_id(line) for line in raw.splitlines()))
        if not identifiers:
            # Intent was written immediately before commit. An interrupted
            # engine RPC may still finish later: absence is not ownership
            # settlement, and cannot be reported as successful cleanup.
            raise RuntimeError('Prepared image commit outcome unresolved; no exact labeled image found')
    if len(identifiers) != 1:
        raise ValueError('Ambiguous prepared image ownership; refusing removal')
    identifier = identifiers[0]
    inventory = prepared_json(command(['image', 'inspect', identifier]))
    if (not isinstance(inventory, list) or len(inventory) != 1
            or not isinstance(inventory[0], dict)
            or prepared_image_id(inventory[0].get('Id')) != identifier
            or not isinstance(inventory[0].get('Config'), dict)
            or not isinstance(inventory[0]['Config'].get('Labels'), dict)
            or any(inventory[0]['Config']['Labels'].get(key) != value
                   for key, value in expected_labels.items())):
        raise ValueError('Prepared image immutable ID or ownership labels differ; refusing removal')
    command(['image', 'rm', identifier])
    return dict(status='removed', image_id=identifier, errors=[])


def finalize_prepared_image(engine, folder, task_id, known_id, state, save):
    """Bound cleanup and retain failed status even after repeated cancellation."""
    pending, failure = [], None
    try:
        with defer_prepared_signals() as pending:
            try:
                state['vm_prepared_image_cleanup'] = cleanup_prepared_image(engine, folder, task_id, known_id)
            except BaseException as error:
                failure = error
                state['vm_prepared_image_cleanup'] = dict(status='blocked', image_id=None,
                    errors=[type(error).__name__])
            state['vm_prepared_image_cleanup']['deferred_signals'] = list(pending)
            if failure or pending:
                state['error'] = 'Prepared image cleanup failed or was interrupted'
                save('blocked')
            else:
                save(state['phase'])
    except BaseException as error:
        failure = error
    if pending and failure is None:
        failure = InterruptedError('Prepared image cleanup interrupted by signal ' + str(pending[0]))
    if failure is not None:
        # Includes signals delivered during restoration or after the yielded body.
        with defer_prepared_signals():
            state['error'] = 'Prepared image cleanup failed or was interrupted'
            state.setdefault('vm_prepared_image_cleanup', dict(status='blocked', image_id=None,
                errors=[type(failure).__name__]))['deferred_signals'] = list(pending)
            save('blocked')
        raise failure


def paired_boot_order():
    # Counterbalance whether an image runs first without adding or discarding
    # boots. Three pairs still provide only a small descriptive distribution.
    return [(number, name) for number in range(1, 4)
            for name in (('baseline', 'candidate') if number % 2 else ('candidate', 'baseline'))]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--candidate-source-root', type=Path)
    parser.add_argument('--candidate-source-sha')
    parser.add_argument('--external-context', type=Path)
    args = parser.parse_args()
    external = None
    candidate_root = ROOT
    candidate_sources = None
    if any((args.candidate_source_root, args.candidate_source_sha, args.external_context)):
        if not all((args.candidate_source_root, args.candidate_source_sha, args.external_context)):
            raise RuntimeError('External execution requires exact candidate source and context together')
        candidate_root = args.candidate_source_root.resolve()
        if subprocess.check_output(['git', '-C', str(candidate_root), 'rev-parse', 'HEAD'], text=True).strip() != args.candidate_source_sha:
            raise RuntimeError('Candidate source checkout differs from exact image source')
        if subprocess.check_output(['git', '-C', str(candidate_root), 'status', '--porcelain'], text=True).strip():
            raise RuntimeError('Candidate source checkout is dirty')
        external = json.loads(args.external_context.read_text())
        if external.get('schema') != 'arctic-external-paired-context-v1' or external.get('image_source_sha') != args.candidate_source_sha:
            raise RuntimeError('External execution context differs from source')
        contract = types.ModuleType('paired_contract')
        contract_path = ROOT/'tools/performance/contract.py'
        if not contract_path.is_file() or contract_path.is_symlink() or contract_path.resolve() != contract_path:
            raise RuntimeError('External contract must be a regular contained source file')
        execution_head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
        if execution_head != external.get('execution_source_sha'):
            raise RuntimeError('External contract execution checkout differs')
        expected_contract = subprocess.check_output(['git', '-C', str(ROOT), 'show', 'HEAD:tools/performance/contract.py'])
        contract_bytes = contract_path.read_bytes()
        if contract_bytes != expected_contract:
            raise RuntimeError('External contract bytes differ from Git HEAD')
        contract.__file__ = str(contract_path)
        exec(compile(contract_bytes, contract.__file__, 'exec'), contract.__dict__)
        candidate_sources = {name: sha256(candidate_root / name) for name in contract.CANDIDATE_SOURCE_FILES}
    if not Path('/dev/kvm').is_char_device():
        raise RuntimeError('Native KVM required; no silent TCG fallback')
    if args.baseline.stat().st_size != 2322073600 or sha256(args.baseline) != BASELINE_SHA256:
        raise RuntimeError('Original v1.2 baseline size/checksum differs')
    args.out = args.out.resolve()
    if args.out.exists() and any(args.out.iterdir()):
        raise RuntimeError('Use a new output directory; previous measurements must remain intact')
    args.out.mkdir(parents=True, exist_ok=True)
    probe = args.out / 'frozen-observer.py'
    subprocess.run([sys.executable, str(ROOT / 'tools/performance/compose-paired-probe.py'), str(probe)], check=True)
    if external and sha256(probe) != external['observer']['frozen_sha256']:
        raise RuntimeError('Frozen observer differs from reviewed external execution')
    images = {'baseline': args.baseline.resolve(), 'candidate': args.candidate.resolve()}
    state = dict(acceleration='kvm', memory_mib=4096, vcpus=2, restricted_network=True,
                 observer_sha256=sha256(probe), images={n: dict(path=str(p), bytes=p.stat().st_size,
                 sha256=sha256(p)) for n, p in images.items()}, runs=[],
                 planned_boot_order=[dict(image=name, boot=number) for number, name in paired_boot_order()])

    def save(phase):
        state['phase'] = phase
        state['timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.out / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
        print(phase, flush=True)

    def require_idle_vm_host():
        if external:
            for name, path in images.items():
                if path.stat().st_size != state['images'][name]['bytes'] or sha256(path) != state['images'][name]['sha256']:
                    raise RuntimeError('Input ISO changed before measurement: ' + name)
            if {name: sha256(candidate_root / name) for name in candidate_sources} != candidate_sources:
                raise RuntimeError('Candidate image-source inputs changed before measurement')
            if subprocess.check_output(['git', '-C', str(candidate_root), 'rev-parse', 'HEAD'], text=True).strip() != args.candidate_source_sha:
                raise RuntimeError('Candidate source HEAD changed before measurement')
            if subprocess.check_output(['git', '-C', str(candidate_root), 'status', '--porcelain'], text=True).strip():
                raise RuntimeError('Candidate source checkout became dirty before measurement')
        active = []
        for comm in Path('/proc').glob('[0-9]*/comm'):
            try:
                if comm.read_text().startswith('qemu-system'):
                    active.append(comm.parent.name)
            except OSError:
                continue
        if active:
            raise RuntimeError('Another QEMU is active; refusing concurrent VM measurements: ' + ','.join(active))
        state['host_loadavg_before_stage'] = Path('/proc/loadavg').read_text().strip()

    engine = os.environ.get('CONTAINER_ENGINE') or ('docker' if shutil.which('docker') else 'podman')
    prepared_id = None
    toolchain_sha = None
    state['task_id'] = uuid.uuid4().hex

    def interrupt(signum, frame):
        raise InterruptedError('Paired acceptance interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)

    def execute(argv, log, timeout, vm=False, provision=False):
        name = 'arctic-paired-' + state['task_id'] + '-' + uuid.uuid4().hex[:8]
        env = dict(os.environ)
        owns_container = vm or provision
        if owns_container:
            env['ARCTIC_VM_CONTAINER_NAME'] = name
        if vm:
            env.update(ARCTIC_FEDORA_IMAGE=prepared_id, ARCTIC_VM_TOOLS_PREPARED='1', ARCTIC_VM_CONTAINER_NAME=name)
        process = None
        failure = None
        code = None
        errors = []
        acquisition_signals = []
        cleanup_signals = []

        @contextmanager
        def signal_transition():
            # Mask only this parent's handler transition, never child creation.
            previous = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGTERM, signal.SIGINT})
            try:
                yield
            finally:
                signal.pthread_sigmask(signal.SIG_SETMASK, previous)

        @contextmanager
        def defer_signals():
            pending = []
            previous = {}
            def queued(signum, frame):
                pending.append(signum)
            try:
                with signal_transition():
                    for signum in (signal.SIGTERM, signal.SIGINT):
                        previous[signum] = signal.signal(signum, queued)
                yield pending
            finally:
                with signal_transition():
                    for signum, handler in previous.items():
                        signal.signal(signum, handler)

        def attempt(label, action):
            try:
                return action()
            except BaseException as error:
                if not isinstance(error, ProcessLookupError):
                    errors.append(label + ': ' + type(error).__name__)
                return None

        def stop_owned():
            if process is None:
                return
            if attempt('poll', process.poll) is None:
                attempt('TERM', lambda: os.killpg(process.pid, signal.SIGTERM))
            # A failed signal or evidence write must not suppress waits/KILL/reap.
            if attempt('wait', lambda: process.wait(timeout=15)) is None:
                if attempt('poll before KILL', process.poll) is None:
                    attempt('KILL', lambda: os.killpg(process.pid, signal.SIGKILL))
                attempt('reap', lambda: process.wait(timeout=15))

        def remove_owned(output):
            if not owns_container:
                return
            # --rm may already have removed it. Prove this exact name absent
            # rather than accepting every failed removal or failing on absence.
            try:
                subprocess.run([engine, 'rm', '--force', name], stdout=output, stderr=output, timeout=30)
            except BaseException:
                pass
            try:
                remaining = subprocess.run([engine, 'ps', '--all', '--filter', 'name=' + name,
                    '--format', '{{.Names}}'], stdout=subprocess.PIPE, stderr=output, timeout=30)
                if remaining.returncode or name.encode() in remaining.stdout.splitlines():
                    errors.append('owned container absence: not proved')
            except BaseException as error:
                errors.append('owned container absence: ' + type(error).__name__)

        def record_failure(output):
            if failure is None:
                return
            state['interrupted_command'] = dict(argv=argv, container=name if owns_container else None,
                error=str(failure), child_acquired=process is not None, cleanup_errors=list(errors),
                deferred_signals=list(acquisition_signals) + list(cleanup_signals))
            attempt('save failed command', lambda: save('command_timeout'
                if isinstance(failure, subprocess.TimeoutExpired) else 'command_interrupted'))
            # Preserve a bounded owned-log failure receipt even if status save fails.
            attempt('write owned failure log', lambda: output.write('ARCTIC-OWNED-COMMAND-CLEANUP=' +
                json.dumps(dict(schema='arctic-paired-owned-command-cleanup-v1', release_acceptance=False,
                    child_acquired=process is not None, failure_type=type(failure).__name__,
                    cleanup_errors=list(errors), deferred_signals=list(acquisition_signals) + list(cleanup_signals))) + '\n'))
            attempt('flush owned failure log', output.flush)

        with log.open('w') as output:
            try:
                # Own the Popen result before restoring a handler that can raise.
                with defer_signals() as acquisition_signals:
                    process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
                if acquisition_signals:
                    raise InterruptedError('Paired acceptance interrupted during owned child acquisition')
                code = process.wait(timeout=timeout)
                if code:
                    raise RuntimeError(f'{log}: harness exit {code}')
            except BaseException as error:
                failure = error
            finally:
                try:
                    with defer_signals() as cleanup_signals:
                        stop_owned()
                        remove_owned(output)
                        if cleanup_signals and failure is None:
                            failure = InterruptedError('Paired acceptance interrupted during owned cleanup')
                        if errors and failure is None:
                            failure = RuntimeError('Paired owned cleanup failed: ' + ', '.join(errors))
                        record_failure(output)
                except BaseException as error:
                    if failure is None:
                        failure = error
                # Include cancellation queued after the body's final check or
                # delivered when the old raising handler is restored at unmask.
                if cleanup_signals and failure is None:
                    failure = InterruptedError('Paired acceptance interrupted at owned cleanup boundary')
                if failure is not None:
                    with defer_signals():
                        record_failure(output)
        if failure is not None:
            raise failure

    def verify_toolchain(folder):
        nonlocal toolchain_sha
        current = sha256(folder / 'vm-toolchain.txt')
        if toolchain_sha is not None and current != toolchain_sha:
            raise RuntimeError('QEMU/firmware/tool inventory changed between stages')
        toolchain_sha = current
        state['vm_toolchain_sha256'] = current

    common = [str(ROOT / 'tools/test-install.sh'), '--kvm', '--memory', '4096', '--smp', '2',
              '--boot-append', '', '--collect-via', 'console']
    profiles = dict(baseline=ROOT/'tools/performance/fixtures/v1.2-offline.toml',
                    candidate=candidate_root/'profiles/ci/offline.toml')
    if sha256(profiles['baseline']) != BASELINE_PROFILE_SHA256:
        raise RuntimeError('Original baseline install profile changed')
    state['profiles'] = {name: dict(path=str(path), sha256=sha256(path)) for name, path in profiles.items()}
    pristine = {}
    try:
        save('prepare_immutable_vm_tools')
        execute(['bash', str(ROOT / 'tools/performance/prepare-vm-tools.sh'), str(args.out), state['task_id']],
                args.out / 'vm-tools-provision.log', 1200, provision=True)
        prepared_id = (args.out / 'vm-prepared-image-id.txt').read_text().strip()
        state['vm_prepared_image_id'] = prepared_id
        if external:
            state['vm_base_image_id'] = (args.out / 'vm-base-image-id.txt').read_text().strip()
        for name, image in images.items():
            require_idle_vm_host()
            save('offline_install_' + name)
            execute(common + ['--stage', 'install', '--iso', str(image), '--install-timeout', '2400',
                              '--profile', str(profiles[name]),
                              '--out', str(args.out / name)], args.out / (name + '-install-harness.log'), 3600, vm=True)
            verify_toolchain(args.out / name)
            if 'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean' not in (args.out/(name+'-install-harness.log')).read_text():
                raise RuntimeError('Installed source did not cleanly power off; first-use snapshot refused')
            pristine[name] = {file: sha256(args.out/name/file) for file in ('target.qcow2', 'OVMF_VARS.fd')}
        state['pristine_installed_sources'] = pristine
        for number, name in paired_boot_order():
            require_idle_vm_host()
            save(f'{name}_boot_{number}')
            archive = args.out / 'runs' / name / str(number)
            archive.mkdir(parents=True, exist_ok=True)
            context = dict(image=name, boot=number, fresh_installed_overlay=True, collector='console',
                           installed_base_sha256=pristine[name]['target.qcow2'],
                           firmware_variables_sha256=pristine[name]['OVMF_VARS.fd'],
                           install_profile_sha256=state['profiles'][name]['sha256'],
                           iso_sha256=state['images'][name]['sha256'])
            if external:
                context.update(external_execution=external, context_id=uuid.uuid4().hex)
            context_path = archive/'performance-context.json'
            context_path.write_text(json.dumps(context, indent=2)+'\n')
            try:
                execute(common + ['--stage', 'boot', '--guest-check', str(probe),
                        '--profile', str(profiles[name]), '--fresh-boot-from', str(args.out/name),
                        '--performance-context', str(context_path), '--out', str(archive)],
                        archive / 'harness.log', 2400, vm=True)
                verify_toolchain(archive)
                if not 'ARCTIC-PERFORMANCE-CONSOLE-RESTORED' in (archive/'serial-boot.log').read_text(errors='replace'):
                    raise RuntimeError('No console-to-desktop VT restoration evidence')
            finally:
                # Per-boot output is already independent. Keep logs on failure,
                # but discard only this fresh overlay/data CD to bound disk use.
                for file in ('target.qcow2', 'data.iso'):
                    (archive/file).unlink(missing_ok=True)
            state['runs'].append(dict(image=name, boot=number, archive=str(archive), harness_exit=0))
        for name, expected in pristine.items():
            if {file: sha256(args.out/name/file) for file in expected} != expected:
                raise RuntimeError('Pristine installed source changed during measurement: '+name)
        if external:
            for name, path in images.items():
                if path.stat().st_size != state['images'][name]['bytes'] or sha256(path) != state['images'][name]['sha256']:
                    raise RuntimeError('Input ISO changed during measurement: ' + name)
            state['input_images_rechecked'] = True
            if {name: sha256(candidate_root / name) for name in candidate_sources} != candidate_sources:
                raise RuntimeError('Candidate image-source inputs changed during measurement')
        argv = [sys.executable, str(ROOT / 'tools/performance/compare.py'),
                '--candidate-commit', (args.candidate_source_sha[:7] if external else
                    subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, text=True).strip()),
                '--candidate-catalog-sha256', sha256(candidate_root / 'shell/AppsService.qml'),
                '--candidate-battery-sha256', sha256(candidate_root / 'shell/BatteryService.qml'), '--out', str(args.out / 'comparison.json')]
        for name in images:
            for number in range(1, 4):
                argv += ['--' + name + '-log', str(args.out / 'runs' / name / str(number) / 'serial-boot.log')]
        result = subprocess.run(argv, cwd=ROOT)
        save('complete_regression_gate_passed' if result.returncode == 0 else 'complete_regression_gate_failed')
        return result.returncode
    except Exception as error:
        state['error'] = str(error)
        save('blocked')
        raise
    finally:
        finalize_prepared_image(engine, args.out, state['task_id'], prepared_id, state, save)


if __name__ == '__main__':
    raise SystemExit(main())
