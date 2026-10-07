#!/usr/bin/env python3
"""Two fresh same-candidate native argv arms; no performance qualification."""
import argparse
import datetime
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
ARMS = ('historical-new-window', 'native-product-argv')
PROFILE_SHA256 = '6f65135a62c397c374f367de459aed784519c2040195ee41d88300996c9b7b2b'


def paired_boot_order():
    # Two distinct pristine installs, fixed arm order; never a paired performance run.
    return [(1, arm) for arm in ARMS]


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(8 * 1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def cleanup_owned_container(engine,name,task,output):
    if not re.fullmatch('[0-9a-f]{32}',task) or not re.fullmatch('arctic-paired-'+task+'-[0-9a-f]{8}',name):
        raise RuntimeError('Refuse cleanup outside the exact owned task name')
    names=subprocess.check_output([engine,'ps','--all','--format','{{.Names}}',
        '--filter','name=^/'+name+'$'],text=True,timeout=30).splitlines()
    if names==[]:
        return dict(container=name,status='owned-name-confirmed-absent')
    if names!=[name]:
        raise RuntimeError('Owned exact-name lookup returned foreign/duplicate resources')
    raw=subprocess.check_output([engine,'inspect','--type','container','--format','{{.Id}} {{.Name}}',name],
        text=True,timeout=30).strip()
    match=re.fullmatch('([0-9a-f]{64}) /'+re.escape(name),raw)
    if match is None:
        raise RuntimeError('Owned present container immutable ID/name differs')
    subprocess.run([engine,'rm','--force',match[1]],stdout=output,stderr=output,timeout=30,check=True)
    return dict(container=name,status='owned-immutable-id-removed',immutable_id=match[1])


def candidate_source_identity(source):
    source = source.resolve()
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=source,text=True).strip()
    if not re.fullmatch('[0-9a-f]{40}',commit) or subprocess.check_output(
            ['git','status','--porcelain'],cwd=source,text=True).strip():
        raise RuntimeError('Candidate image source checkout is not clean/pinned')
    return dict(commit=commit, short_commit=subprocess.check_output(
        ['git','rev-parse','--short','HEAD'],cwd=source,text=True).strip(),
        catalog_sha256=sha256(source/'shell/AppsService.qml'),
        battery_sha256=sha256(source/'shell/BatteryService.qml'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--candidate-source-root', type=Path, default=ROOT,
                        help='Clean image source checkout, separate from the execution checker checkout')
    args = parser.parse_args()
    candidate_identity = candidate_source_identity(args.candidate_source_root)
    if candidate_identity['commit'] != 'fe4742c8b9414c45f0bcbb0a4191f116383c60d1':
        raise RuntimeError('Fixed candidate source changed')
    if args.candidate.stat().st_size != 1880244224 or sha256(args.candidate) != '84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718':
        raise RuntimeError('Fixed candidate bytes/checksum differ')
    if not Path('/dev/kvm').is_char_device():
        raise RuntimeError('Native KVM required; no silent TCG fallback')
    args.out = args.out.resolve()
    if args.out.exists() and any(args.out.iterdir()):
        raise RuntimeError('Use a new output directory; previous measurements must remain intact')
    args.out.mkdir(parents=True, exist_ok=True)
    probe = args.out / 'frozen-observer.py'
    subprocess.run([sys.executable, str(ROOT / 'tools/browser-route/compose-browser-route.py'), str(probe), '--identity-out', str(args.out / 'observer-identity.json')], check=True)
    composed = json.loads((args.out / 'observer-identity.json').read_text())
    if composed['frozen_probe_sha256'] != sha256(probe):
        raise RuntimeError('Composed observer byte identity differs')
    images = {arm: args.candidate.resolve() for arm in ARMS}
    ownership=json.loads(os.environ.get('ARCTIC_BROWSER_ROUTE_OWNERSHIP','null'))
    if (not isinstance(ownership,dict) or ownership.get('schema')!='arctic-browser-route-task-v2'
            or ownership.get('mode')!='browser-native-argv-diagnostic'
            or ownership.get('candidate_source')!=candidate_identity['commit']
            or ownership.get('execution_checker_head')!=os.environ.get('GITHUB_SHA')
            or ownership.get('github_run_id')!=os.environ.get('GITHUB_RUN_ID')
            or ownership.get('github_run_attempt')!=os.environ.get('GITHUB_RUN_ATTEMPT')
            or ownership.get('arms')!=list(ARMS) or ownership.get('observer_sha256')!=sha256(probe)
            or ownership.get('candidate_iso_path')!=str(args.candidate.resolve())
            or type(ownership.get('candidate_iso_bytes')) is not int or ownership['candidate_iso_bytes']!=1880244224
            or ownership.get('candidate_iso_sha256')!='84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718'
            or not isinstance(ownership.get('task_id'),str) or not re.fullmatch('[0-9a-f]{32}',ownership['task_id'])):
        raise RuntimeError('Exact caller-owned browser task scope differs')
    state = dict(mode='browser-native-argv-diagnostic',full_six_boot_performance_acceptance=False,
                 release_acceptance=False,observer_composition=composed,candidate_image_source=candidate_identity,
                 execution_checker_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                 acceleration='kvm', memory_mib=4096, vcpus=2, restricted_network=True,
                 observer_sha256=sha256(probe), images={n: dict(path=str(p), bytes=p.stat().st_size,
                 sha256=sha256(p)) for n, p in images.items()}, runs=[],
                 planned_boot_order=[dict(image=name, boot=number) for number, name in paired_boot_order()])
    state.update(ownership=ownership,owned_container_names=[])

    def save(phase):
        state['phase'] = phase
        state['timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        temporary=args.out/'status.json.tmp'
        if temporary.is_symlink():raise RuntimeError('Owned status temporary path is linked')
        temporary.write_text(json.dumps(state, indent=2) + '\n')
        temporary.replace(args.out/'status.json')
        print(phase, flush=True)

    def require_idle_vm_host():
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

    if os.environ.get('CONTAINER_ENGINE') != 'docker' or not shutil.which('docker'):
        raise RuntimeError('Owned Docker cleanup contract is mandatory')
    engine = 'docker'
    prepared_id = None
    toolchain_sha = None
    state['task_id'] = ownership['task_id']

    def interrupt(signum, frame):
        raise InterruptedError('Paired acceptance interrupted by signal ' + str(signum))

    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)

    def execute(argv, log, timeout, vm=False, provision=False):
        name = 'arctic-paired-' + state['task_id'] + '-' + uuid.uuid4().hex[:8]
        env = dict(os.environ)
        owns_container = vm or provision
        if owns_container:
            state['owned_container_names'].append(name)
            save(state.get('phase','owned_container_registered'))
            env['ARCTIC_VM_CONTAINER_NAME'] = name
        if vm:
            env.update(ARCTIC_FEDORA_IMAGE=prepared_id, ARCTIC_VM_TOOLS_PREPARED='1', ARCTIC_VM_CONTAINER_NAME=name)
        with log.open('w') as output:
            process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except BaseException as error:
                state['interrupted_command'] = dict(argv=argv, container=name if owns_container else None, error=str(error))
                save('command_timeout' if isinstance(error, subprocess.TimeoutExpired) else 'command_interrupted')
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=15)
                raise
            finally:
                if owns_container:
                    # Only this uniquely named task container can be stopped.
                    # Docker's processes do not belong to the host CLI's group.
                    primary = sys.exc_info()[0] is not None
                    try:
                        observation=cleanup_owned_container(engine,name,state['task_id'],output)
                        state.setdefault('container_cleanup_observations',[]).append(observation)
                        save(state.get('phase','owned_container_cleanup_observed'))
                    except BaseException as error:
                        state.setdefault('cleanup_errors', []).append(dict(container=name,error=str(error)))
                        save('owned_cleanup_failed')
                        if not primary:
                            raise RuntimeError('Owned Docker cleanup failed: '+name) from error
        if code:
            raise RuntimeError(f'{log}: harness exit {code}')

    def verify_toolchain(folder):
        nonlocal toolchain_sha
        current = sha256(folder / 'vm-toolchain.txt')
        if toolchain_sha is not None and current != toolchain_sha:
            raise RuntimeError('QEMU/firmware/tool inventory changed between stages')
        toolchain_sha = current
        state['vm_toolchain_sha256'] = current

    common = [str(ROOT / 'tools/test-install.sh'), '--kvm', '--memory', '4096', '--smp', '2',
              '--boot-append', '', '--collect-via', 'console']
    profiles = {arm: args.candidate_source_root/'profiles/ci/offline.toml' for arm in ARMS}
    if any(sha256(path) != PROFILE_SHA256 for path in profiles.values()):
        raise RuntimeError('Fixed candidate offline profile changed')
    state['profiles'] = {name: dict(path=str(path), sha256=sha256(path)) for name, path in profiles.items()}
    pristine = {}
    try:
        save('prepare_immutable_vm_tools')
        execute(['bash', str(ROOT / 'tools/performance/prepare-vm-tools.sh'), str(args.out)],
                args.out / 'vm-tools-provision.log', 1200, provision=True)
        prepared_id = (args.out / 'vm-prepared-image-id.txt').read_text().strip()
        state['vm_prepared_image_id'] = prepared_id
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
            context = dict(image='candidate', boot=number, browser_route_arm=name,
                           browser_route_schema='arctic-browser-native-argv-v1',
                           fresh_installed_overlay=True, collector='console',
                           installed_base_sha256=pristine[name]['target.qcow2'],
                           firmware_variables_sha256=pristine[name]['OVMF_VARS.fd'],
                           install_profile_sha256=state['profiles'][name]['sha256'],
                           iso_sha256=state['images'][name]['sha256'])
            context_path = archive/'performance-context.json'
            context_path.write_text(json.dumps(context, indent=2)+'\n')
            try:
                execute(common + ['--stage', 'boot', '--guest-check', str(probe),
                        '--profile', str(profiles[name]), '--fresh-boot-from', str(args.out/name),
                        '--performance-context', str(context_path), '--out', str(archive)],
                        archive / 'harness.log', 2400, vm=True)
                verify_toolchain(archive)
                if (archive/'data/guest-check.py').read_bytes() != probe.read_bytes():
                    raise RuntimeError('Actual copied guest probe differs from the composed bytes')
                if json.loads((archive/'data/performance-context.json').read_text()) != context:
                    raise RuntimeError('Actual copied fresh-arm context differs')
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
        argv = [sys.executable, str(ROOT / 'tools/browser-route/check-browser-route.py'),
                '--identity', str(args.out/'observer-identity.json'), '--out', str(args.out / 'browser-route.json')]
        for name, flag in zip(ARMS, ('--historical-log','--native-log')):
            argv += [flag, str(args.out / 'runs' / name / '1' / 'serial-boot.log')]
        result = subprocess.run(argv, cwd=ROOT)
        save('complete_browser_route_gates_passed' if result.returncode == 0 else 'complete_browser_route_gates_failed')
        return result.returncode
    except Exception as error:
        state['error'] = str(error)
        save('blocked')
        raise
    finally:
        if prepared_id:
            # The image was created uniquely by this run and was never pushed.
            primary = sys.exc_info()[0] is not None
            try:
                result = subprocess.run([engine, 'image', 'rm', prepared_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
                if result.returncode:
                    raise RuntimeError('Owned prepared Docker image cleanup failed')
            except BaseException as error:
                state.setdefault('cleanup_errors', []).append(dict(prepared_image=prepared_id,error=str(error)))
                save('owned_image_cleanup_failed')
                if not primary:
                    raise


if __name__ == '__main__':
    raise SystemExit(main())
