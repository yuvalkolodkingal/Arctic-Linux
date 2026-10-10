#!/usr/bin/env python3
"""Disabled-until-pinned additive exact live-image installer restoration lane."""
import argparse
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import uuid

import contract as C
import controller as H
import evidence as E

HERE = Path(__file__).resolve().parent
_display_spec = importlib.util.spec_from_file_location('installer_runner_signal_guard', HERE.parent / 'native-functional/taskbar-display.py')
_display = importlib.util.module_from_spec(_display_spec)
_display_spec.loader.exec_module(_display)

DIAGNOSTIC_STAGES = ('docker-info', 'provision', 'capture-build', 'build-binding', 'context',
                     'source-verify', 'run-live', 'extract', 'report-validation',
                     'execution-validation', 'cleanup')
DIAGNOSTIC_ERROR_TYPES = ((subprocess.TimeoutExpired, 'timeout'),
                          (subprocess.CalledProcessError, 'command-error'),
                          (InterruptedError, 'interrupted'), (OSError, 'os-error'),
                          (RuntimeError, 'runtime-error'), (ValueError, 'value-error'),
                          (KeyError, 'key-error'), (TypeError, 'type-error'),
                          (KeyboardInterrupt, 'keyboard-interrupt'), (SystemExit, 'system-exit'))
PREPARATION_DIAGNOSTICS = (
    ('Owned preparation container already exists', 'owned-container-exists'),
    ('Immutable owned prepared image missing', 'prepared-image-missing'))
DIAGNOSTIC_LITERALS = {
    'provision': PREPARATION_DIAGNOSTICS,
    'capture-build': PREPARATION_DIAGNOSTICS,
    'build-binding': (('Actual physical capture build differs', 'capture-build-binding'),),
    'context': (('installer context fields differ', 'context-fields'),
                ('installer context identities differ', 'context-identities'),
                ('active installer context fields differ', 'context-fields'),
                ('active installer context schema differs', 'context-schema'),
                ('active installer owned target or write throttle differs', 'context-target')),
    'source-verify': (
        ('Installer lane disabled until the final image and execution code are reviewed', 'manifest-disabled'),
        ('Requires the reviewed disposable installer Actions lane', 'actions-identity'),
        ('Invalid pinned image', 'image-pin'),
        ('Dirty or changed image/execution checkout', 'checkout-changed'),
        ('Installer execution inventory differs', 'execution-inventory'),
        ('Actual final ISO bytes differ', 'iso-bytes')),
    'extract': (('installer output destination must be unused', 'output-used'),
                ('installer output parent is a symlink', 'output-symlink'),
                ('installer output parent became a symlink', 'output-symlink'),
                ('installer port input exceeds bound', 'port-bound'),
                ('installer UART input exceeds bound', 'uart-bound')),
    'report-validation': (('Host and guest actual transitions differ', 'transition-binding'),),
    'execution-validation': (('installer execution identity/status differs', 'execution-identity'),
                             ('active installer execution identity/status differs', 'execution-identity')),
}


def diagnostic_code(stage, error):
    """Select fixed stage/class/literal codes without formatting private errors."""
    C.require(type(stage) is str and stage in DIAGNOSTIC_STAGES, 'Unknown installer diagnostic stage')
    if isinstance(error, RuntimeError) and type(error.args) is tuple and len(error.args) == 1 and type(error.args[0]) is str:
        for message, code in DIAGNOSTIC_LITERALS.get(stage, ()):
            if error.args[0] == message:
                return 'installer-' + stage + '-' + code
    for error_class, label in DIAGNOSTIC_ERROR_TYPES:
        if isinstance(error, error_class):
            return 'installer-' + stage + '-' + label
    return 'installer-' + stage + '-other-error'


def diagnose(stage, error):
    code = diagnostic_code(stage, error)
    try:
        print('ARCTIC-INSTALLER-DIAGNOSTIC=' + code, flush=True)
    except (OSError, ValueError):
        # Closed Actions stdout must not interrupt original failure cleanup.
        pass


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, sort_keys=True, allow_nan=False) + '\n')


def execute(argv, log, seconds, cwd, env):
    """Bound and stop only this invocation's host process group."""
    with Path(log).open('xb') as output:
        child = None
        try:
            with _display.defer_signals():
                child = subprocess.Popen(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            status = child.wait(timeout=seconds)
            C.require(status == 0, 'installer command failed (' + str(status) + '); see ' + str(log))
        except BaseException:
            with H.cleanup_signals():
                if child is not None and child.poll() is None:
                    for sig in (signal.SIGTERM, signal.SIGKILL):
                        try: os.killpg(child.pid, sig)
                        except ProcessLookupError: pass
                        try: child.wait(timeout=45)
                        except subprocess.TimeoutExpired: continue
                        break
            raise


def verify(args, execution):
    active_profile = getattr(args, 'active_profile', False)
    contract = E.active_contract() if active_profile else C
    manifest = json.loads(args.manifest.read_text())
    C.require(manifest.get('ready') is True and manifest.get('release_acceptance') is False,
              'Installer lane disabled until the final image and execution code are reviewed')
    C.require(os.environ.get('GITHUB_ACTIONS') == 'true' and os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted' and
              os.environ.get('GITHUB_REPOSITORY') == 'yuvalkolodkingal/Arctic-Linux' and
              os.environ.get('GITHUB_REF') == 'refs/heads/codex/qualification-dispatch-20261010' and
              os.environ.get('GITHUB_WORKFLOW') == ('Candidate active installer restoration qualification' if active_profile else 'Candidate installer restoration qualification') and
              os.environ.get('GITHUB_EVENT_NAME') == 'push' and os.environ.get('GITHUB_RUN_ATTEMPT') == '1',
              'Requires the reviewed disposable installer Actions lane')
    image = manifest['image']
    C.require(C.is_hash(image['source_sha'], 40) and C.is_hash(image['sha256']) and
              type(image['bytes']) is int and 0 < image['bytes'] < 2_000_000_000 and
              re.fullmatch(r'Arctic-Linux-1\.2-candidate-[0-9]+-1-x86_64\.iso', image['name']), 'Invalid pinned image')
    for tree, expected in ((args.source, image['source_sha']), (execution, os.environ['GITHUB_SHA'])):
        C.require(subprocess.check_output(['git', '-C', str(tree), 'rev-parse', 'HEAD'], text=True, timeout=30).strip() == expected and
                  not subprocess.check_output(['git', '-C', str(tree), 'status', '--porcelain'], text=True, timeout=30).strip(), 'Dirty or changed image/execution checkout')
    inputs = manifest['execution_files']
    C.require(set(inputs) == set(contract.EXECUTION_FILES), 'Installer execution inventory differs')
    for name, expected in inputs.items():
        path = execution / name
        C.require(path.is_file() and not path.is_symlink() and sha(path) == expected, 'Pinned installer execution bytes differ: ' + name)
    iso = args.inputs / 'iso' / image['name']
    C.require(iso.is_file() and not iso.is_symlink() and iso.stat().st_size == image['bytes'] and sha(iso) == image['sha256'], 'Actual final ISO bytes differ')
    return manifest, iso


def preserve_host(vm, target, active=False):
    target.mkdir()
    for name in ('host-execution.json', 'installer-host-transitions.json',
                 *('installer-vt-away-' + str(n) + '.png' for n in range(3))):
        path = vm / name
        if path.is_file() and not path.is_symlink():
            C.require(path.stat().st_size <= 4 * 1024 * 1024, 'Oversized host receipt/capture')
            shutil.copyfile(path, target / name)
    if active:
        for name in ('installed-boot.json', 'serial-installed.log', 'installed-getty-password.png', 'installed-sudo-password.png'):
            path = vm / name
            if path.is_file() and not path.is_symlink():
                C.require(path.stat().st_size <= 8*1024*1024, 'Oversized installed boot proof')
                shutil.copyfile(path, target / name)
        path = vm / 'qemu-installer-installed.log'
        if path.is_file() and not path.is_symlink():
            C.require(path.stat().st_size <= 4*1024*1024, 'Oversized installed QEMU diagnostic')
            with path.open('rb') as stream:
                (target / 'qemu-installer-installed.log.bounded-prefix.bin').write_bytes(stream.read(64*1024))
    # UART and transport contain bounded framed data. Keep diagnostic prefixes
    # rather than uploading duplicate base64 payloads; record complete hashes.
    records = {}
    streams = [('serial.log', 8 * 1024 * 1024), ('installer-port.log', 64 * 1024 * 1024), ('qemu-installer-live.log', 4 * 1024 * 1024)]
    if active:
        streams += [('serial-installed.log', 8*1024*1024), ('qemu-installer-installed.log', 4*1024*1024)]
    for name, bound in streams:
        path = vm / name
        if path.is_file() and not path.is_symlink():
            C.require(path.stat().st_size <= bound, 'Oversized installer diagnostic stream')
            records[name] = dict(bytes=path.stat().st_size, sha256=sha(path))
            if name in ('serial.log', 'serial-installed.log'):
                shutil.copyfile(path, target / name)
            else:
                with path.open('rb') as stream:
                    (target / (name + '.bounded-prefix.bin')).write_bytes(stream.read(64 * 1024))
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, default=HERE / 'execution-manifest.json')
    parser.add_argument('--evidence', type=Path, required=True)
    parser.add_argument('--active-profile', action='store_true', help='Additive real GUI install on its owned target disk')
    args = parser.parse_args()
    if args.active_profile and args.manifest == HERE / 'execution-manifest.json':
        args.manifest = HERE / 'active-execution-manifest.json'
    contract = E.active_contract() if args.active_profile else C
    execution = HERE.parents[1]
    manifest, iso = verify(args, execution)
    C.require(not args.evidence.exists(), 'Installer evidence output must be unused')
    args.evidence.mkdir(parents=True)
    state = dict(schema='arctic-installer-active-execution-v1' if args.active_profile else 'arctic-installer-execution-v1',
                 status='failed_or_unrun', release_acceptance=False,
                 image=manifest['image'], execution=dict(source_sha=os.environ['GITHUB_SHA'], run_id=int(os.environ['GITHUB_RUN_ID']),
                 manifest_sha256=sha(args.manifest)), source_inputs=manifest['execution_files'], errors=[],
                 limitations=['Prepared idle Hebrew keyboard wizard; no in-flight installation preservation claim',
                              'All twelve physical restoration captures require independent manual review',
                              'Separate original native, security and actual CLI install lanes remain required'])
    if args.active_profile:
        state['limitations'] = ['Owned offline UEFI installation with encryption explicitly disabled through the shipped GUI',
            'QEMU target writes capped at 8 MiB/s to retain genuine copy across both disruptions; no performance claim',
            'All seven active restoration and pre-input console captures require independent manual review; original idle/native/CLI gates remain required']
    owned_images = []
    vm = args.evidence.parent / ('installer-vm-' + uuid.uuid4().hex)
    payload = args.evidence.parent / ('installer-tools-' + uuid.uuid4().hex)
    errors = []
    def save(): write(args.evidence / 'execution.json', state)
    def interrupted(number, frame): raise InterruptedError('Installer qualification signal ' + str(number))
    signal.signal(signal.SIGINT, interrupted); signal.signal(signal.SIGTERM, interrupted)
    diagnostic_stage = 'docker-info'
    try:
        save()
        subprocess.check_output(['docker', 'info', '--format', '{{.ServerVersion}}'], timeout=30)
        for script, argument, seconds, name, extra in (
                ('tools/performance/prepare-vm-tools.sh', args.evidence, 20 * 60, 'provision', {}),
                ('tools/native-functional/prepare-taskbar-tools.sh', None, 15 * 60, 'capture-build', None)):
            diagnostic_stage = name
            container = 'arctic-paired-native-' + uuid.uuid4().hex
            check = subprocess.run(['docker', 'container', 'inspect', container], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
            C.require(check.returncode != 0, 'Owned preparation container already exists')
            env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME=container,
                       ARCTIC_INSTALLER_ACTIVE='1' if args.active_profile else '0')
            if argument is None:
                payload.mkdir(); env['ARCTIC_FEDORA_IMAGE'] = prepared
                argv = ['bash', str(execution / script), str(execution), str(payload)]
            else: argv = ['bash', str(execution / script), str(argument)]
            execute(argv, args.evidence / (name + '.log'), seconds, execution, env)
            receipt = (args.evidence / 'vm-prepared-image-id.txt' if argument is not None else payload / 'taskbar-vm-prepared-image-id.txt')
            prepared = receipt.read_text().strip()
            C.require(re.fullmatch(r'(sha256:)?[0-9a-f]{64}', prepared), 'Immutable owned prepared image missing')
            owned_images.append(prepared)
        diagnostic_stage = 'build-binding'
        build = json.loads((payload / 'build-provenance.json').read_text())
        C.require(build['schema'] == 'arctic-taskbar-tools-v1' and build['release_acceptance'] is False and
                  set(build['sources']) == {'shell/dev/virtual-pointer.c', 'tools/native-functional/taskbar-screencopy.c', 'shell/dev/wlr-screencopy-unstable-v1.xml'} and
                  all(build['sources'][name] == state['source_inputs'][name] for name in build['sources']) and
                  build['binaries']['raw-screencopy'] == sha(payload / 'raw-screencopy') and
                  (payload / 'raw-screencopy').read_bytes()[:4] == b'\x7fELF', 'Actual physical capture build differs')
        state['build'], state['vm_tool_image_id'] = build, prepared
        diagnostic_stage = 'context'
        context = dict(schema='arctic-installer-context-v1', source_sha=manifest['image']['source_sha'],
                       iso_sha256=manifest['image']['sha256'], iso_bytes=manifest['image']['bytes'], execution_sha=os.environ['GITHUB_SHA'],
                       binding_id=uuid.uuid4().hex, checker_sha256=state['source_inputs']['tools/installer-qualification/guest.py'],
                       runtime_sha256=state['source_inputs']['tools/native-functional/taskbar-runtime.py'],
                       native_sha256=state['source_inputs']['tools/native-functional/native_smoke.py'], capture_sha256=sha(payload / 'raw-screencopy'))
        if args.active_profile:
            context.update(schema='arctic-installer-active-context-v1',
                active_checker_sha256=state['source_inputs']['tools/installer-qualification/active-guest.py'],
                installed_checker_sha256=state['source_inputs']['tools/installer-qualification/installed-guest.py'],
                disk_serial='arctic-a-' + uuid.uuid4().hex[:11], disk_bytes=64*1024**3,
                disk_node='target0', write_bps=8*1024**2)
        contract.context_check(context); state['context'] = context
        context_file = payload / 'installer-context.json'; write(context_file, context)
        diagnostic_stage = 'source-verify'
        verify(args, execution); save()
        env = dict(os.environ, CONTAINER_ENGINE='docker', ARCTIC_VM_CONTAINER_NAME='arctic-paired-native-' + uuid.uuid4().hex,
                   ARCTIC_FEDORA_IMAGE=prepared)
        try:
            diagnostic_stage = 'run-live'
            execute(['bash', str(HERE / 'run-live.sh'), str(args.source), str(execution), str(iso), str(payload),
                     str(context_file), 'uefi', str(vm)], args.evidence / 'installer-harness.log',
                    (80 if args.active_profile else 35) * 60, execution, env)
        except BaseException as error:
            diagnose(diagnostic_stage, error)
            errors.append('harness: ' + type(error).__name__ + ': ' + str(error))
        finally:
            diagnostic_stage = 'extract'
            state['diagnostic_streams'] = preserve_host(vm, args.evidence / 'host', args.active_profile)
        result = E.extract(vm / 'installer-port.log', vm / 'serial.log', args.evidence / 'installer', context)
        report = result['report']; state['guest'] = result['state']
        state['host'] = json.loads((args.evidence / 'host/host-execution.json').read_text())
        diagnostic_stage = 'report-validation'
        contract.validate_report(report, context, result['files'], lambda name: (args.evidence / 'installer' / name).read_bytes(), contract.packaged_source_hashes(args.source))
        if args.active_profile:
            contract.validate_catalog_selection(report, (args.source / 'modules/catalog.toml').read_bytes())
        C.require(state['host']['host_transitions'] == json.loads((args.evidence / 'host/installer-host-transitions.json').read_text())['receipts'] and
                  [row['request'] for row in state['host']['host_transitions']] == result['requests'], 'Host and guest actual transitions differ')
        state['transport'] = dict(status='passed', report_path='installer/installer-report.json',
                                  report_sha256=sha(args.evidence / 'installer/installer-report.json'),
                                  port_sha256=sha(vm / 'installer-port.log'), serial_sha256=sha(vm / 'serial.log'))
        state['required_images'] = {name: sha(args.evidence / name) for name in contract.REQUIRED_IMAGES}
        state['status'] = ('live_installer_active_restoration_completed_and_installed_boot_passed_pending_manual_visual_review'
                           if args.active_profile else 'live_installer_restoration_passed_pending_manual_visual_review')
        diagnostic_stage = 'execution-validation'
        contract.validate_execution(state, manifest['image'], os.environ['GITHUB_SHA'], (vm / 'serial.log').read_bytes(),
                             lambda name: (args.evidence / name).read_bytes())
    except BaseException as error:
        diagnose(diagnostic_stage, error)
        errors.append(type(error).__name__ + ': ' + str(error))
    finally:
        diagnostic_stage = 'cleanup'
        with H.cleanup_signals() as pending:
            for image in owned_images:
                try:
                    subprocess.run(['docker', 'image', 'rm', image], check=True, timeout=30, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                except BaseException as error:
                    diagnose(diagnostic_stage, error)
                    errors.append('owned image cleanup: ' + type(error).__name__ + ': ' + str(error))
            H.persist_cleanup_state(args.evidence / 'execution.json', state, errors, pending)
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
