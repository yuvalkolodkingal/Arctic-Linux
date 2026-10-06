#!/usr/bin/env python3
"""Sequential offline KVM installs and three interleaved boots of each image."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
BASELINE_SHA256 = '054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f'


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
    args = parser.parse_args()
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
    images = {'baseline': args.baseline.resolve(), 'candidate': args.candidate.resolve()}
    state = dict(acceleration='kvm', memory_mib=4096, vcpus=2, restricted_network=True,
                 observer_sha256=sha256(probe), images={n: dict(path=str(p), bytes=p.stat().st_size,
                 sha256=sha256(p)) for n, p in images.items()}, runs=[])

    def save(phase):
        state['phase'] = phase
        state['timestamp_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (args.out / 'status.json').write_text(json.dumps(state, indent=2) + '\n')
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
                    subprocess.run([engine, 'rm', '--force', name], stdout=output, stderr=output, timeout=30)
        if code:
            raise RuntimeError(f'{log}: harness exit {code}')

    def verify_toolchain(folder):
        nonlocal toolchain_sha
        current = sha256(folder / 'vm-toolchain.txt')
        if toolchain_sha is not None and current != toolchain_sha:
            raise RuntimeError('QEMU/firmware/tool inventory changed between stages')
        toolchain_sha = current
        state['vm_toolchain_sha256'] = current

    common = [str(ROOT / 'tools/test-install.sh'), '--kvm', '--memory', '4096', '--smp', '2', '--boot-append', '']
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
                              '--out', str(args.out / name)], args.out / (name + '-install-harness.log'), 3600, vm=True)
            verify_toolchain(args.out / name)
        for number in range(1, 4):
            for name in images:
                require_idle_vm_host()
                save(f'{name}_boot_{number}')
                folder = args.out / name
                archive = args.out / 'runs' / name / str(number)
                archive.mkdir(parents=True, exist_ok=True)
                try:
                    execute(common + ['--stage', 'boot', '--guest-check', str(probe), '--out', str(folder)],
                            archive / 'harness.log', 2400, vm=True)
                    verify_toolchain(folder)
                finally:
                    # Keep terminal evidence even when the harness fails. Disk
                    # images and sockets stay local and are excluded from uploads.
                    for path in folder.iterdir():
                        if path.is_file() and path.suffix in ('.log', '.json', '.png', '.txt'):
                            shutil.copy2(path, archive / path.name)
                state['runs'].append(dict(image=name, boot=number, archive=str(archive), harness_exit=0))
        argv = [sys.executable, str(ROOT / 'tools/performance/compare.py'),
                '--candidate-commit', subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD'], cwd=ROOT, text=True).strip(),
                '--candidate-catalog-sha256', sha256(ROOT / 'shell/AppsService.qml'),
                '--candidate-battery-sha256', sha256(ROOT / 'shell/BatteryService.qml'), '--out', str(args.out / 'comparison.json')]
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
        if prepared_id:
            # The image was created uniquely by this run and was never pushed.
            subprocess.run([engine, 'image', 'rm', prepared_id], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


if __name__ == '__main__':
    raise SystemExit(main())
