#!/usr/bin/env python3
"""Unlock one disposable installed disk and wait for its offline-update reboot.

This intermediate boot deliberately makes no desktop/update success claim.
Verify actual versions, updater state and persistence on the subsequent boot.
Runs in the Fedora QEMU tools container; accepts only files under this repo's out/.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--disk', type=Path, required=True)
parser.add_argument('--vars', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--timeout', type=int, default=5400)
args = parser.parse_args()
for name in ('disk', 'vars', 'out'):
    value = getattr(args, name).resolve()
    if not value.is_relative_to(root/'out'):
        parser.error(f'--{name} must be under the disposable repo out/ directory')
    setattr(args, name, value)
if not args.disk.is_file() or args.disk.suffix != '.qcow2' or not args.vars.is_file():
    parser.error('Requires an existing disposable qcow2 disk and its OVMF vars')
if not 300 <= args.timeout <= 7200:
    parser.error('--timeout must be between 300 and 7200 seconds')
firmware = Path('/usr/share/edk2/ovmf/OVMF_CODE.fd')
if not firmware.is_file():
    parser.error('Requires the Fedora QEMU tools container with OVMF')
args.out.mkdir(parents=True, exist_ok=True)
os.environ['OUT'] = str(args.out)
sys.path.insert(0, str(root/'tools/lib'))
import vmtest

qmp = f'/tmp/arctic-offline-update-{os.getpid()}.sock'
argv = ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'tcg,thread=multi',
        '-cpu', 'max', '-smp', '2', '-m', '4096', '-display', 'none', '-vga', 'virtio',
        '-qmp', f'unix:{qmp},server=on,wait=off', '-serial', f'file:{args.out}/serial.log',
        '-monitor', 'none', '-no-reboot',
        '-drive', f'file={args.disk},if=none,id=disk,discard=unmap',
        '-device', 'virtio-blk-pci,drive=disk,bootindex=0',
        '-netdev', 'user,id=net0,restrict=on', '-device', 'virtio-net-pci,netdev=net0',
        '-device', 'qemu-xhci', '-device', 'usb-tablet', '-rtc', 'base=utc',
        '-drive', f'if=pflash,format=raw,unit=0,readonly=on,file={firmware}',
        '-drive', f'if=pflash,format=raw,unit=1,file={args.vars}']
result = {'status': 'running', 'network': 'restricted_offline',
          'platform': 'QEMU_TCG', 'disk': str(args.disk),
          'acceptance': 'Subsequent boot must prove actual update completion'}
report = args.out/'intermediate-boot.json'
def save(**changes):
    result.update(changes)
    report.write_text(json.dumps(result, indent=2)+'\n')

vm = None
start = time.monotonic()
try:
    save()
    devices = subprocess.check_output(['qemu-system-x86_64', '-device', 'help'],
                                      text=True, stderr=subprocess.STDOUT)
    if 'name "virtio-vga"' not in devices:
        raise RuntimeError('QEMU runtime is missing virtio-vga; install the same '
                           'qemu-device-display-virtio-{vga,gpu,gpu-pci} packages '
                           'used by tools/test-install.sh before running offline')
    vm = vmtest.VM(argv, qmp, 'offline-update')
    time.sleep(6)
    vm.shot('01-default-boot-menu')
    vm.keys('ret')
    prompt = None
    while vm.alive() and time.monotonic()-start < 300:
        prompt = vm.shot('02-unlock-probe')
        if prompt and vmtest.classify(prompt) == 'prompt':
            break
        time.sleep(10)
    if not vm.alive() or not prompt or vmtest.classify(prompt) != 'prompt':
        raise RuntimeError('No encryption prompt; inspect screenshots/serial')
    vm.shot('03-encryption-prompt')
    # The same known disposable-test passphrase used by test-install.sh.
    vm.type_text(os.environ.get('ARCTIC_TEST_LUKS_PASSPHRASE',
                               'glacier lantern frost harbor'), gap=0.3)
    vm.keys('ret')
    save(encryption_password_typed=True)
    last_shot = 0
    while vm.alive() and time.monotonic()-start < args.timeout:
        elapsed = time.monotonic()-start
        if elapsed-last_shot >= 30:
            vm.shot(f'10-transaction-{int(elapsed):04d}s')
            last_shot = elapsed
            vmtest.log(f'Waiting for offline transaction/reboot: {elapsed:.0f}s')
        time.sleep(5)
    if vm.alive():
        raise RuntimeError('Intermediate offline-update boot timed out; no completion claim')
    if vm.proc.returncode != 0:
        raise RuntimeError(f'QEMU exited with {vm.proc.returncode}')
    save(status='guest_exited_subsequent_boot_required',
         elapsed_seconds=time.monotonic()-start, qemu_exit_code=vm.proc.returncode)
    vmtest.log('Guest exited with -no-reboot; verify the transaction on the subsequent boot')
except (Exception, SystemExit) as error:
    save(status='failed', reason=str(error), elapsed_seconds=time.monotonic()-start)
    raise
finally:
    if vm is not None:
        vm.quit()
