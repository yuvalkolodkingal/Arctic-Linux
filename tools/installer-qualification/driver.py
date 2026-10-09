#!/usr/bin/env python3
"""Fresh live-ISO GUI restoration VM; never starts an OS installation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def stop_owned(vm, display):
    errors = []
    if vm is not None and getattr(vm, 'proc', None) is not None:
        for action in ('terminate', 'wait', 'kill', 'wait'):
            try:
                if vm.proc.poll() is None:
                    if action == 'wait': vm.proc.wait(timeout=5)
                    else: getattr(vm.proc, action)()
            except subprocess.TimeoutExpired:
                pass
            except BaseException as error:
                errors.append(type(error).__name__ + ': ' + str(error))
        try:
            if vm.proc.poll() is None: errors.append('owned QEMU remains alive')
        except BaseException as error:
            errors.append(type(error).__name__ + ': ' + str(error))
    if display is not None:
        try: display.close()
        except BaseException as error: errors.append(type(error).__name__ + ': ' + str(error))
    require(not errors, 'installer host cleanup failed: ' + '; '.join(errors))


def owned_vm_type(vmtest, display_module):
    """Local bounded fixture; inherited input/shot helpers use bounded cmd.

    Frozen vmtest.py is unchanged. A constructor failure always cleans its
    already recorded child, including failure before the caller receives self.
    """
    class OwnedVM(vmtest.VM):
        def __init__(self, argv, qmp_path, name):
            self.name, self.qmp_path = name, qmp_path
            self.proc = self.s = self.f = self.log = None
            require(not Path(qmp_path).exists(), 'owned installer QMP path already exists')
            try:
                with display_module.defer_signals():
                    self.log = open(Path(os.environ['OUT']) / ('qemu-' + name + '.log'), 'x')
                    self.proc = subprocess.Popen(argv, stdout=self.log, stderr=subprocess.STDOUT)
                deadline = time.monotonic() + 30
                while True:
                    require(self.proc.poll() is None, 'owned installer QEMU exited before QMP')
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, 'owned installer QMP acquisition timed out')
                    with display_module.defer_signals():
                        self.s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    self.s.settimeout(remaining)
                    try:
                        self.s.connect(qmp_path)
                        break
                    except (FileNotFoundError, ConnectionRefusedError):
                        self.s.close(); self.s = None; time.sleep(.05)
                greeting = bytearray()
                while b'\n' not in greeting:
                    remaining = deadline - time.monotonic()
                    require(remaining > 0, 'owned QMP greeting timed out')
                    self.s.settimeout(remaining)
                    data = self.s.recv(4096)
                    require(data and len(greeting) + len(data) <= 65536, 'owned QMP greeting absent or oversized')
                    greeting.extend(data)
                first, _, tail = greeting.partition(b'\n')
                require(not tail and type(json.loads(first)) is dict and 'QMP' in json.loads(first),
                        'unexpected owned QMP greeting')
                with display_module.defer_signals():
                    self.f = self.s.makefile('rw')
                self.s.settimeout(None)
                self.cmd('qmp_capabilities')
            except BaseException:
                with display_module.defer_signals():
                    try: stop_owned(self, None)
                    finally: self.close_handles()
                raise

        def cmd(self, name, **arguments):
            return {'return': display_module.qmp_query(self, name, arguments or None, seconds=10)}

        def close_handles(self):
            errors = []
            for stream in (self.f, self.s, self.log):
                if stream is not None:
                    try: stream.close()
                    except BaseException as error: errors.append(error)
            require(not errors, 'owned installer monitor/log handles failed to close')
    return OwnedVM


def prepare_vm(display, out, firmware):
    # No writable target disk, host filesystem share, networking, audio/input
    # passthrough, replacement compositor or replacement installer is exposed.
    argv = ['qemu-system-x86_64', '-machine', 'q35', '-accel', 'kvm', '-cpu', 'max',
            '-smp', '2', '-m', '4096', '-display', display.display_arg, '-vga', 'none',
            '-device', 'virtio-vga,id=arctic_taskbar_gpu,max_outputs=2', '-S',
            '-qmp', 'unix:' + str(out / 'qmp.sock') + ',server=on,wait=off',
            '-serial', 'file:' + str(out / 'serial.log'), '-monitor', 'none', '-no-reboot',
            '-drive', 'file=' + str(out / 'data.iso') + ',media=cdrom,readonly=on,if=none,id=data',
            '-device', 'ide-cd,drive=data,bus=ide.0',
            '-drive', 'file=/iso,media=cdrom,readonly=on,if=none,id=live',
            '-device', 'ide-cd,drive=live,bus=ide.1,bootindex=0',
            '-nic', 'none', '-device', 'qemu-xhci', '-device', 'usb-tablet', '-rtc', 'base=utc',
            '-chardev', 'file,id=installer_evidence,path=' + str(out / 'installer-port.log'),
            '-device', 'virtio-serial-pci,id=installer_serial', '-device',
            'virtserialport,bus=installer_serial.0,chardev=installer_evidence,name=arctic-installer-evidence']
    if firmware == 'uefi':
        shutil.copyfile('/usr/share/edk2/ovmf/OVMF_VARS.fd', out / 'OVMF_VARS.fd')
        argv.extend(['-drive', 'if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd',
                     '-drive', 'if=pflash,format=raw,unit=1,file=' + str(out / 'OVMF_VARS.fd')])
    return argv


def choose_install(vm, vmtest, out):
    deadline = time.monotonic() + 300
    while vm.alive() and time.monotonic() < deadline:
        path = vm.shot('boot-menu-probe')
        if path and vmtest.looks_like_boot_menu(path):
            os.replace(path, out / 'boot-menu.png')
            vm.keys('home', 'down', 'e'); time.sleep(.5)
            vm.keys('down', 'down', 'ctrl-e')
            vm.type_text(' console=tty0 console=ttyS0,115200 systemd.journald.forward_to_console=1', gap=.05)
            vm.shot('boot-entry-selected'); vm.keys('ctrl-x')
            return
        time.sleep(.5)
    raise RuntimeError('actual installer boot menu was not detected')


def authenticate_console(vm, startup, vmtest, out):
    # Give the real graphical session time to start. A unique real live UID
    # response is mandatory before sending the reviewed root test-CD command.
    deadline = time.monotonic() + 600
    serial = out / 'serial.log'
    while vm.alive() and time.monotonic() < deadline:
        if vmtest.serial_has(str(serial), 'live session mode: install'):
            break
        time.sleep(1)
    else:
        raise RuntimeError('actual live install session did not start')
    time.sleep(8)
    answer = vm.cmd('send-key', keys=[{'type': 'qcode', 'data': key} for key in ('ctrl', 'alt', 'f6')],
                    **{'hold-time': 100})
    require('error' not in answer, 'QEMU refused real VT6 keyboard activation')
    time.sleep(4)
    require(startup.console_screen(vm.shot('console-login')), 'real console not visible; refused GUI input')
    vm.type_text('liveuser', gap=.15); vm.keys('ret'); time.sleep(3); vm.keys('ret'); time.sleep(3)
    nonce = uuid.uuid4().hex
    vm.type_text(startup.console_auth_command(nonce), gap=.05); vm.keys('ret')
    for _ in range(30):
        if startup.console_authenticated(serial, nonce):
            break
        time.sleep(1)
    else:
        raise RuntimeError('live console UID authentication failed')
    return dict(nonce=nonce, status='exact_liveuser_uid_response', capture='console-login.png')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--firmware', choices=('uefi', 'bios'), default='uefi')
    args = parser.parse_args()
    out = args.out
    require(os.geteuid() == 0 and Path('/dev/kvm').is_char_device(), 'requires root disposable KVM container')
    require(out.is_dir() and not out.is_symlink(), 'invalid owned installer output directory')
    os.environ['OUT'] = str(out)
    sys.path.insert(0, '/execution/tools/lib')
    import vmtest
    import iso_startup as startup
    display_module = load('installer_display_fixture', '/execution/tools/native-functional/taskbar-display.py')
    controller_module = load('installer_output_controller', '/execution/tools/installer-qualification/controller.py')
    context = json.loads((out / 'data/installer-context.json').read_text())
    state = dict(schema='arctic-installer-host-execution-v1', status='failed_or_unrun',
                 context=context, firmware=args.firmware, release_acceptance=False, iso_booted=False,
                 execution_inputs={name: sha('/execution/' + name) for name in (
                     'tools/installer-qualification/driver.py', 'tools/installer-qualification/controller.py',
                     'tools/installer-qualification/run-live.sh', 'tools/native-functional/taskbar-display.py',
                     'tools/lib/vmtest.py', 'tools/lib/iso_startup.py')})
    vm = display = controller = None
    errors = []
    def interrupted(number, frame):
        raise InterruptedError('Installer VM signal ' + str(number))
    signal.signal(signal.SIGINT, interrupted)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        display = display_module.TaskbarDisplay()
        argv = prepare_vm(display, out, args.firmware)
        state['qemu_argv'] = argv
        vm = owned_vm_type(vmtest, display_module)(argv, str(out / 'qmp.sock'), 'installer-live')
        state['display_preparation'] = dict(display.enable(vm), controller_sha256=sha('/execution/tools/native-functional/taskbar-display.py'))
        display_module.qmp_query(vm, 'cont')
        require(display_module.qmp_query(vm, 'query-status')['running'] is True, 'owned installer VM did not run')
        choose_install(vm, vmtest, out)
        state['iso_booted'] = True
        state['console_authentication'] = authenticate_console(vm, startup, vmtest, out)
        controller = controller_module.InstallerController(vm, display, context, out)
        # The CD launcher returns to the discovered Wayland VT before the
        # checker observes the pre-existing packaged installer and engine.
        vm.type_text('sudo sh /dev/sr0', gap=.1); vm.keys('ret')
        deadline = time.monotonic() + 660
        while vm.alive() and time.monotonic() < deadline:
            controller.poll(out / 'serial.log')
            if vmtest.serial_has(str(out / 'serial.log'), 'ARCTIC-INSTALLER-PORT-END '):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('installer guest evidence did not complete in bound')
        state['host_transitions'] = controller.finish()
        state['status'] = 'host_completed_pending_guest_evidence_validation_and_visual_review'
    except BaseException as error:
        errors.append(type(error).__name__ + ': ' + str(error))
    finally:
        with controller_module.cleanup_signals() as pending:
            if controller is not None:
                try: state['output_cleanup'] = controller.restore()
                except BaseException as error: errors.append('output cleanup: ' + type(error).__name__ + ': ' + str(error))
            try:
                stop_owned(vm, display)
                state['owned_qemu_stopped'] = vm is None or vm.proc.poll() is not None
                state['owned_private_bus_closed'] = display is None or display.closed
            except BaseException as error:
                errors.append('host cleanup: ' + type(error).__name__ + ': ' + str(error))
            if vm is not None:
                try: vm.close_handles()
                except BaseException as error: errors.append('handle cleanup: ' + type(error).__name__ + ': ' + str(error))
            controller_module.persist_cleanup_state(out / 'host-execution.json', state, errors, pending)
    return int(bool(errors))


if __name__ == '__main__':
    raise SystemExit(main())
