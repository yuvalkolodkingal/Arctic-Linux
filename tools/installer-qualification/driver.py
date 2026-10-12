#!/usr/bin/env python3
"""Owned live-ISO restoration VM, with an explicit genuine-installation profile."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import uuid
from types import FunctionType, ModuleType

DIAGNOSTIC_STAGES = (
    'run-live-init', 'run-live-context', 'run-live-payload', 'run-live-credentials',
    'run-live-permissions', 'run-live-bootstrap', 'run-live-container-binding',
    'run-live-container-run', 'container-packages', 'container-display', 'container-data',
    'container-driver', 'driver-unhandled', 'driver-display', 'driver-prepare',
    'driver-acquire', 'driver-enable', 'driver-menu', 'driver-console', 'driver-controller',
    'driver-launch', 'driver-collect', 'driver-transitions', 'driver-live-report',
    'driver-live-stop', 'driver-installed-prepare', 'driver-installed-acquire',
    'driver-installed-enable', 'driver-installed-proof', 'driver-persist',
    'driver-output-cleanup', 'driver-host-cleanup', 'driver-handle-cleanup')
DIAGNOSTIC_ERROR_TYPES = ((subprocess.TimeoutExpired, 'timeout'),
    (subprocess.CalledProcessError, 'command-error'), (InterruptedError, 'interrupted'),
    (OSError, 'os-error'), (RuntimeError, 'runtime-error'), (ValueError, 'value-error'),
    (KeyError, 'key-error'), (TypeError, 'type-error'),
    (KeyboardInterrupt, 'keyboard-interrupt'), (SystemExit, 'system-exit'))
DIAGNOSTIC_LITERALS = {
    'driver-acquire': (('owned installer QEMU exited before QMP', 'qemu-exited'),
        ('owned installer QMP acquisition timed out', 'qmp-timeout')),
    'driver-enable': (('owned installer VM did not run', 'not-running'),),
    'driver-menu': (('actual installer boot menu was not detected', 'menu-absent'),),
    'driver-console': (('actual live install session did not start', 'session-absent'),
        ('real console not visible; refused GUI input', 'console-absent'),
        ('live console UID authentication failed', 'uid-authentication')),
    'driver-collect': (('installer guest evidence did not complete in bound', 'evidence-incomplete'),),
    'driver-live-report': (('active live collector did not pass', 'collector-failed'),),
    'driver-installed-proof': (('fresh installed login display did not appear', 'login-absent'),
        ('fresh installed proof did not complete', 'proof-incomplete')),
}
DIAGNOSTIC_CODES = frozenset(
    'installer-inner-' + stage + '-' + label for stage in DIAGNOSTIC_STAGES
    for label in ('other-error', *(label for _, label in DIAGNOSTIC_ERROR_TYPES),
                  *(code for _, code in DIAGNOSTIC_LITERALS.get(stage, ()))))

COLLECTION_GUARD_LABELS = ('collection-001', 'collection-002', 'collection-003', 'collection-004', 'collection-005', 'collection-006', 'collection-007', 'collection-008', 'collection-009', 'collection-010', 'collection-011', 'collection-012', 'collection-013', 'collection-014', 'collection-015', 'collection-016', 'collection-017', 'collection-018', 'collection-019', 'collection-020', 'collection-021', 'collection-022', 'collection-023', 'collection-024', 'collection-025', 'collection-026', 'collection-027', 'collection-028', 'collection-029', 'collection-030', 'collection-031', 'collection-032', 'collection-033', 'collection-034', 'collection-035')
DIAGNOSTIC_CODES = DIAGNOSTIC_CODES | frozenset(
    'installer-inner-driver-collect-guard-' + code for code in COLLECTION_GUARD_LABELS)
MAX_COLLECTION_DIAGNOSTIC_FRAMES = 64
WRITE_OBSERVATION_LABELS = (
    ('bytes', ('true', 'false', 'unknown')),
    ('operations', ('true', 'false', 'unknown')),
    ('clock', ('true', 'false', 'unknown')),
    ('vm', ('running', 'not-running', 'process-exited', 'unknown')),
    ('phase', ('vt-away', 'output-disconnect', 'output-restore', 'unknown')),
    ('cycle', ('zero', 'unknown')),
)
DIAGNOSTIC_CODES = DIAGNOSTIC_CODES | frozenset(
    'installer-inner-driver-collect-write-' + field + '-' + label
    for field, labels in WRITE_OBSERVATION_LABELS for label in labels)
COLLECTION_PHASE_LABELS = ('request-json', 'request-json-fields', 'request-json-constant',
    'output-head', 'request-poll', 'console-capture', 'output-transition',
    'target-write-progress', 'target-write-sample')
DIAGNOSTIC_CODES = DIAGNOSTIC_CODES | frozenset(
    'installer-inner-driver-collect-phase-' + code + '-runtime-error' for code in COLLECTION_PHASE_LABELS)


def collection_guard_code(error, controller_source):
    """Only a pinned controller's source-minted identity; no exception text."""
    if type(error) is not RuntimeError or type(controller_source) is not ModuleType:
        return None
    source = controller_source.__dict__
    function = source.get('require')
    if type(function) is not FunctionType or function.__globals__ is not source or \
            source.get('__file__') != str(Path(__file__).with_name('controller.py')) or \
            function.__code__.co_filename != source['__file__']:
        return None
    proof = error.__dict__.get('_arctic_installer_collection_guard')
    if type(proof) is tuple and len(proof) == 2 and proof[0] is source.get('_COLLECTION_GUARD_TOKEN') and \
            type(proof[1]) is str and proof[1] in COLLECTION_GUARD_LABELS:
        return 'installer-inner-driver-collect-guard-' + proof[1]
    # A nested owned operation can fail before one of the controller's guards.
    # Project the deepest exact source code object, never exception text/locals.
    traceback, phase = error.__traceback__, None
    owners, phases = source.get('_COLLECTION_GUARD_OWNERS'), source.get('_COLLECTION_GUARD_PHASES')
    if type(owners) is set and type(phases) is dict:
        for _ in range(MAX_COLLECTION_DIAGNOSTIC_FRAMES):
            if traceback is None:
                break
            frame = traceback.tb_frame
            if frame.f_globals is source and any(frame.f_code is code for code in owners):
                candidate = phases.get(frame.f_code.co_qualname)
                if type(candidate) is str and candidate in COLLECTION_PHASE_LABELS:
                    phase = candidate
            traceback = traceback.tb_next
        if traceback is not None:
            return None  # Never present a truncated prefix as the deepest phase.
        if phase is not None:
            return 'installer-inner-driver-collect-phase-' + phase + '-runtime-error'
    return None


def write_observation_codes(error, controller_source):
    if collection_guard_code(error, controller_source) != 'installer-inner-driver-collect-guard-collection-034':
        return ()
    observation = error.__dict__.get('_arctic_installer_write_observation')
    source = controller_source.__dict__
    if type(observation) is not tuple or len(observation) != 7 or observation[0] is not source.get('_COLLECTION_GUARD_TOKEN'):
        return ()
    if not all(type(value) is str and value in labels
            for value, (_, labels) in zip(observation[1:], WRITE_OBSERVATION_LABELS)):
        return ()
    return tuple('installer-inner-driver-collect-write-' + field + '-' + value
                 for value, (field, _) in zip(observation[1:], WRITE_OBSERVATION_LABELS))


def diagnostic_code(stage, error, controller_source=None):
    require(type(stage) is str and stage in DIAGNOSTIC_STAGES, 'Unknown installer inner stage')
    if stage == 'driver-collect':
        try:
            guarded = collection_guard_code(error, controller_source)
        except Exception:
            guarded = None  # Optional identity cannot replace the original failure.
        if guarded is not None:
            return guarded
    if isinstance(error, RuntimeError) and type(error.args) is tuple and len(error.args) == 1 and type(error.args[0]) is str:
        for message, label in DIAGNOSTIC_LITERALS.get(stage, ()):
            if error.args[0] == message:
                return 'installer-inner-' + stage + '-' + label
    for error_class, label in DIAGNOSTIC_ERROR_TYPES:
        if isinstance(error, error_class):
            return 'installer-inner-' + stage + '-' + label
    return 'installer-inner-' + stage + '-other-error'


def diagnose(stage, error, controller_source=None):
    # This host-only nonce is never copied into the test CD, guest or context.
    token = os.environ.get('ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN', '')
    if type(token) is str and re.fullmatch('[0-9a-f]{32}', token):
        code = diagnostic_code(stage, error, controller_source)
        try:
            print('ARCTIC-INSTALLER-INNER ' + token + ' ' + code, flush=True)
            if code == 'installer-inner-driver-collect-guard-collection-034':
                try:
                    observed = write_observation_codes(error, controller_source)
                except Exception:
                    observed = ()
                for observation in observed:
                    print('ARCTIC-INSTALLER-INNER ' + token + ' ' + observation, flush=True)
        except Exception:
            pass


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


def prepare_vm(display, out, firmware, context=None, installed=False):
    # Both profiles exclude networking, host shares, audio/input passthrough and
    # replacement product processes. Only the explicit active profile adds its
    # newly acquired standalone guest target disk.
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
        if not installed:
            require(not (out / 'OVMF_VARS.fd').exists() and not (out / 'OVMF_VARS.fd').is_symlink(),
                    'owned variable store already exists')
            shutil.copyfile('/usr/share/edk2/ovmf/OVMF_VARS.fd', out / 'OVMF_VARS.fd')
        else:
            require((out / 'OVMF_VARS.fd').is_file() and not (out / 'OVMF_VARS.fd').is_symlink(),
                    'installed boot requires the original owned variable store')
        argv.extend(['-drive', 'if=pflash,format=raw,unit=0,readonly=on,file=/usr/share/edk2/ovmf/OVMF_CODE.fd',
                     '-drive', 'if=pflash,format=raw,unit=1,file=' + str(out / 'OVMF_VARS.fd')])
    if context and context.get('schema') == 'arctic-installer-active-context-v1':
        require(firmware == 'uefi', 'active install requires the separately reviewed UEFI fixture')
        target = out / 'target.qcow2'
        if not installed:
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            subprocess.run(['qemu-img', 'create', '-f', 'qcow2', str(target), str(context['disk_bytes'])],
                           check=True, timeout=30, stdout=subprocess.DEVNULL)
        info = json.loads(subprocess.check_output(['qemu-img', 'info', '--output=json', str(target)], timeout=30))
        require(target.is_file() and not target.is_symlink() and info['format'] == 'qcow2'
                and info['virtual-size'] == context['disk_bytes'] and 'backing-filename' not in info,
                'active target is not a fresh standalone owned qcow2')
        argv.extend(['-drive', 'file=' + str(target) + ',if=none,id=active_target,node-name=target0,format=qcow2,bps_wr=' +
                     str(context['write_bps']), '-device', 'virtio-blk-pci,drive=active_target,serial=' + context['disk_serial'] +
                     (',bootindex=0' if installed else '')])
        if installed:
            live_drive = argv.index('file=/iso,media=cdrom,readonly=on,if=none,id=live')
            del argv[live_drive-1:live_drive+1]
            live_device = argv.index('ide-cd,drive=live,bus=ide.1,bootindex=0')
            del argv[live_device-1:live_device+1]
            argv[argv.index('-serial')+1] = 'file:' + str(out / 'serial-installed.log')
            argv[argv.index('-qmp')+1] = 'unix:' + str(out / 'qmp-installed.sock') + ',server=on,wait=off'
            # Installed proof uses only UART, never the already completed live port.
            argv[argv.index('-chardev')+1] = 'file,id=installer_evidence,path=' + str(out / 'installed-unused-port.log')
    return argv


def console_prompt(vm, startup, out, label, expected, private_password, archive=True):
    """Observe a strict last console line before permitting any secret input."""
    kinds = {'installed-getty-password': 'getty-auth',
             'installed-sudo-password': 'sudo-auth', 'installed-login-shell': 'installed-user-shell'}
    require(label in kinds, 'unreviewed installed console prompt kind')
    deadline = time.monotonic() + 45
    while vm.alive() and time.monotonic() < deadline:
        path = vm.shot(label + '-probe')
        require(path and startup.console_screen(path), 'actual password console disappeared')
        result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', '6'],
                                capture_output=True, timeout=10, check=True)
        require(len(result.stdout) <= 65536, 'prompt OCR exceeds bound')
        text = result.stdout.decode()
        # A failed login must not make a secret-bearing probe a public image.
        require(private_password not in text.lower(), 'private input unexpectedly appeared in console; image withheld')
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        observed_line = lines[-1].rstrip('_| ') if lines else None
        if observed_line == expected:
            from PIL import Image
            with Image.open(path) as image:
                require(image.size == (1280,720), 'installed prompt physical dimensions differ')
            record = dict(path=label+'.png', bytes=Path(path).stat().st_size, sha256=sha(path),
                          size=[1280,720], prompt_kind=kinds[label],
                          observed_line_sha256=hashlib.sha256(observed_line.encode('utf-8')).hexdigest(),
                          observed_ns=time.monotonic_ns())
            if archive:
                require(not (out/(label+'.png')).exists(), 'password prompt capture reused')
                os.replace(path, out/(label+'.png'))
            else:
                Path(path).unlink()
            return record
        time.sleep(.5)
    raise RuntimeError('exact console prompt was not observed; secret input refused')


def ocr_provenance():
    trained = [path for path in subprocess.check_output(['rpm','-ql','tesseract-langpack-eng'],text=True,timeout=10).splitlines()
               if path.endswith('/eng.traineddata')]
    require(len(trained)==1, 'English prompt OCR model is ambiguous')
    return dict(packages=subprocess.check_output(['rpm','-q','tesseract','tesseract-langpack-eng'],text=True,timeout=10).splitlines(),
                program_sha256=sha('/usr/bin/tesseract'), traineddata_sha256=sha(trained[0]),
                version=subprocess.check_output(['tesseract','--version'],text=True,stderr=subprocess.DEVNULL,timeout=10).splitlines()[0])


def boot_installed(vm, startup, vmtest, out, context):
    """Authenticate on a new QEMU boot of the same disk, with hidden TTY secrets."""
    deadline = time.monotonic() + 900
    while vm.alive() and time.monotonic() < deadline:
        shot = vm.shot('installed-login-probe')
        if shot and vmtest.looks_like_boot_menu(shot):
            vm.keys('ret')
        if shot and vmtest.classify(shot) == 'login':
            break
        time.sleep(2)
    else:
        raise RuntimeError('fresh installed login display did not appear')
    vm.cmd('send-key', keys=[{'type': 'qcode', 'data': k} for k in ('ctrl', 'alt', 'f6')], **{'hold-time': 100})
    time.sleep(4)
    require(startup.console_screen(vm.shot('installed-console-login')), 'fresh installed console was not visible')
    private = json.loads((out / 'data/active-credentials.json').read_text())
    password = private['password']
    require(set(private) == {'password'} and re.fullmatch('[a-z0-9]{32}', password), 'private credential fixture differs')
    # Permit secret input only at the observed shipped getty/sudo password prompt.
    # No secret appears in shell command text, argv or public receipts.
    vm.type_text('arcticqual', gap=.15); vm.keys('ret')
    getty = console_prompt(vm,startup,out,'installed-getty-password','Password:',password)
    vm.type_text(password, gap=.1); vm.keys('ret')
    shell = console_prompt(vm,startup,out,'installed-login-shell','arcticqual@arctic-qual ~ >',password,archive=False)
    nonce = uuid.uuid4().hex
    vm.type_text('sudo sh /dev/sr0 ' + nonce, gap=.08); vm.keys('ret')
    sudo = console_prompt(vm,startup,out,'installed-sudo-password','[sudo] password for arcticqual:',password)
    vm.type_text(password, gap=.1); vm.keys('ret')
    password = None; private.clear()
    serial = out / 'serial-installed.log'
    deadline = time.monotonic() + 120
    while vm.alive() and time.monotonic() < deadline:
        data = serial.read_bytes()
        require(len(data) <= 8*1024*1024, 'installed UART exceeds bound')
        lines = data.decode().splitlines()
        require('ARCTIC-ACTIVE-INSTALLED-FAILED' not in lines, 'installed guest proof failed')
        records = [line[len('ARCTIC-ACTIVE-INSTALLED '):] for line in lines if line.startswith('ARCTIC-ACTIVE-INSTALLED ')]
        if records:
            require(len(records) == 1 and
                    lines.count('ARCTIC-ACTIVE-INSTALLED-READY=' + nonce + ' user=arcticqual uid=1000') == 1,
                    'fresh installed authentication/receipt is ambiguous')
            checker = load('active_boot_strict_base', '/execution/tools/installer-qualification/guest.py')
            report = checker.strict_json(records[0])
            require(report['context'] == context and report['authentication']['nonce'] == nonce,
                    'fresh installed helper context/authentication differs')
            prompts = dict(schema='arctic-active-password-prompts-v1',engine=ocr_provenance(),getty=getty,sudo=sudo,
                login_shell={key: shell[key] for key in ('prompt_kind','observed_line_sha256','observed_ns')},
                private_input_policy='Only after exact last console line; no secret-bearing screenshots or command text')
            return report, dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()), prompts
        time.sleep(.5)
    raise RuntimeError('fresh installed proof did not complete')


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
    diagnostic_stage = 'driver-display'
    try:
        display = display_module.TaskbarDisplay()
        active = context.get('schema') == 'arctic-installer-active-context-v1'
        diagnostic_stage = 'driver-prepare'
        argv = prepare_vm(display, out, args.firmware, context)
        state['qemu_argv'] = argv
        if active:
            state['target_proof'] = dict(path='target.qcow2', virtual_bytes=context['disk_bytes'], serial=context['disk_serial'],
                                        backing_file=False, node_name='target0', write_bps=context['write_bps'])
        diagnostic_stage = 'driver-acquire'
        vm = owned_vm_type(vmtest, display_module)(argv, str(out / 'qmp.sock'), 'installer-live')
        diagnostic_stage = 'driver-enable'
        state['display_preparation'] = dict(display.enable(vm), controller_sha256=sha('/execution/tools/native-functional/taskbar-display.py'))
        display_module.qmp_query(vm, 'cont')
        require(display_module.qmp_query(vm, 'query-status')['running'] is True, 'owned installer VM did not run')
        diagnostic_stage = 'driver-menu'
        choose_install(vm, vmtest, out)
        state['iso_booted'] = True
        diagnostic_stage = 'driver-console'
        state['console_authentication'] = authenticate_console(vm, startup, vmtest, out)
        diagnostic_stage = 'driver-controller'
        controller = controller_module.InstallerController(vm, display, context, out)
        # The CD launcher returns to the discovered Wayland VT before the
        # checker observes the pre-existing packaged installer and engine.
        diagnostic_stage = 'driver-launch'
        vm.type_text('sudo sh /dev/sr0', gap=.1); vm.keys('ret')
        diagnostic_stage = 'driver-collect'
        deadline = time.monotonic() + (56*60 if active else 660)
        while vm.alive() and time.monotonic() < deadline:
            controller.poll(out / 'serial.log')
            if vmtest.serial_has(str(out / 'serial.log'), 'ARCTIC-INSTALLER-PORT-END '):
                break
            time.sleep(.1)
        else:
            raise RuntimeError('installer guest evidence did not complete in bound')
        diagnostic_stage = 'driver-transitions'
        state['host_transitions'] = controller.finish()
        if active:
            # Read the protected report directly from the original port before
            # stopping this owned live VM; extraction is independently repeated later.
            diagnostic_stage = 'driver-live-report'
            reports = [controller_module.strict_json(line.split(' ',1)[1]) for line in
                       (out/'installer-port.log').read_text().splitlines() if line.startswith('ARCTIC-INSTALLER-REPORT ')]
            require(len(reports) == 1 and reports[0]['status'] == 'passed', 'active live collector did not pass')
            live_boot, live_pid = reports[0]['boot_id'], vm.proc.pid
            diagnostic_stage = 'driver-live-stop'
            state['output_cleanup'] = controller.restore()
            stop_owned(vm, display); vm.close_handles()
            state['live_qemu_stopped_before_installed_boot'] = vm.proc.poll() is not None
            controller = None
            diagnostic_stage = 'driver-installed-prepare'
            display = display_module.TaskbarDisplay()
            argv = prepare_vm(display, out, args.firmware, context, installed=True)
            diagnostic_stage = 'driver-installed-acquire'
            vm = owned_vm_type(vmtest, display_module)(argv, str(out/'qmp-installed.sock'), 'installer-installed')
            require(vm.proc.pid != live_pid, 'installed boot reused the live QEMU process')
            diagnostic_stage = 'driver-installed-enable'
            display.enable(vm); display_module.qmp_query(vm, 'cont')
            diagnostic_stage = 'driver-installed-proof'
            report, serial_proof, prompts = boot_installed(vm, startup, vmtest, out, context)
            state['password_prompt_evidence'] = prompts
            require(report['boot_id'] != live_boot, 'installed boot reused the live guest boot')
            state['installed_boot'] = dict(status='passed', live_qemu_pid=live_pid, installed_qemu_pid=vm.proc.pid,
                qemu_argv=argv, target={k: state['target_proof'][k] for k in ('path','virtual_bytes','serial','backing_file')},
                boot_id=report['boot_id'], parent_live_boot_id=live_boot, selinux=report['selinux'],
                root=report['root'], keyboard=report['keyboard'], authentication=report['authentication'],
                serial=serial_proof, receipt_sha256=hashlib.sha256(json.dumps(report,sort_keys=True,allow_nan=False).encode()).hexdigest())
            diagnostic_stage = 'driver-persist'
            (out/'installed-boot.json').write_text(json.dumps(report,sort_keys=True,allow_nan=False)+'\n')
        state['status'] = 'host_completed_pending_guest_evidence_validation_and_visual_review'
    except BaseException as error:
        diagnose(diagnostic_stage, error, controller_module)
        errors.append(type(error).__name__ + ': ' + str(error))
    finally:
        with controller_module.cleanup_signals() as pending:
            if controller is not None:
                try: state['output_cleanup'] = controller.restore()
                except BaseException as error:
                    diagnose('driver-output-cleanup', error)
                    errors.append('output cleanup: ' + type(error).__name__ + ': ' + str(error))
            try:
                stop_owned(vm, display)
                state['owned_qemu_stopped'] = vm is None or vm.proc.poll() is not None
                state['owned_private_bus_closed'] = display is None or display.closed
            except BaseException as error:
                diagnose('driver-host-cleanup', error)
                errors.append('host cleanup: ' + type(error).__name__ + ': ' + str(error))
            if vm is not None:
                try: vm.close_handles()
                except BaseException as error:
                    diagnose('driver-handle-cleanup', error)
                    errors.append('handle cleanup: ' + type(error).__name__ + ': ' + str(error))
            controller_module.persist_cleanup_state(out / 'host-execution.json', state, errors, pending)
    return int(bool(errors))


if __name__ == '__main__':
    try:
        result = main()
    except BaseException as error:
        if not isinstance(error, SystemExit) or error.code != 0:
            diagnose('driver-unhandled', error)
        raise
    raise SystemExit(result)
