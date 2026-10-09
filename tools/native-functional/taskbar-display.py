#!/usr/bin/env python3
"""Prepare two heads through QEMU's supported private D-Bus display UI API.

Start the owned QEMU with -S, virtio-vga,id=arctic_taskbar_gpu,max_outputs=2
and display_arg; enable(vm), then explicitly continue it. This is host fixture
preparation only: installed Mango must still observe two enabled outputs.
QEMU 10.2: ui/dbus-display1.xml Console.SetUIInfo(qqiiuu), ui/dbus-console.c,
hw/display/virtio-gpu-base.c virtio_gpu_ui_info. No display listener is used.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import stat
import struct
import subprocess
import tempfile
import time

GPU_ID = 'arctic_taskbar_gpu'


class DisplayError(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise DisplayError(message)


@contextmanager
def defer_signals():
    """Defer raising handlers during resource handoff; child masks stay normal."""
    pending, previous = [], {}
    try:
        for number in (signal.SIGINT, signal.SIGTERM):
            previous[number] = signal.getsignal(number)
            signal.signal(number, lambda number, frame: pending.append((number, frame)))
        yield
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)
        if pending:
            number, frame = pending[0]
            handler = previous[number]
            if callable(handler):
                handler(number, frame)
            elif handler != signal.SIG_IGN:
                if number == signal.SIGINT:
                    raise KeyboardInterrupt()
                raise SystemExit(128 + number)


def uint32_reply(text, variant=False):
    pattern = r'\(<uint32 ([0-9]+)>,\)' if variant else r'\(uint32 ([0-9]+),\)'
    match = re.fullmatch(pattern, text.strip())
    require(match is not None, 'unexpected D-Bus unsigned reply')
    value = int(match.group(1))
    require(value <= 0xffffffff, 'D-Bus unsigned reply overflow')
    return value


def string_reply(text, variant=False):
    pattern = r"\(<'([A-Za-z0-9_:./-]{1,160})'>,\)" if variant else r"\('([A-Za-z0-9_:./-]{1,160})',\)"
    match = re.fullmatch(pattern, text.strip())
    require(match is not None, 'unexpected D-Bus string reply')
    return match.group(1)


def console_ids_reply(text):
    match = re.fullmatch(r'\(<\[uint32 ([0-9]+(?:, [0-9]+)*)\]>,\)', text.strip())
    require(match is not None, 'unexpected D-Bus console list')
    values = [int(value) for value in match.group(1).split(', ')]
    require(2 <= len(values) <= 16 and len(set(values)) == len(values)
            and all(value <= 0xffffffff for value in values), 'invalid D-Bus console list')
    return values


def qmp_query(vm, command, arguments=None, seconds=10):
    """Bound the existing owned QMP client without editing frozen VM helpers.

    A socket chardev has one active monitor client, so use vm.f (including its
    already buffered events) rather than opening a second monitor connection.
    SIGALRM provides an absolute deadline even if bytes arrive continuously.
    """
    require(vm.proc.poll() is None and type(vm.proc.pid) is int and vm.proc.pid > 1,
            'owned QEMU is not alive')
    entry = Path(vm.qmp_path).lstat()
    require(stat.S_ISSOCK(entry.st_mode) and entry.st_uid == 0, 'QMP is not a root-owned socket')
    pid, uid, _ = struct.unpack('3i', vm.s.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
    require(pid == vm.proc.pid and uid == 0, 'QMP peer differs from the owned root QEMU')
    require(signal.getitimer(signal.ITIMER_REAL) == (0.0, 0.0), 'another host alarm already owns QMP timing')
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timeout = vm.s.gettimeout()
    request = {'execute': command, 'id': 'arctic-taskbar-' + command}
    if arguments is not None:
        request['arguments'] = arguments
    deadline = time.monotonic() + seconds
    def expired(number, frame):
        raise DisplayError('owned QMP absolute deadline exceeded')
    try:
        signal.signal(signal.SIGALRM, expired)
        signal.setitimer(signal.ITIMER_REAL, seconds)
        vm.s.settimeout(seconds)
        vm.f.write(json.dumps(request) + '\n'); vm.f.flush()
        total = 0
        for _ in range(32):
            remaining = deadline - time.monotonic()
            require(remaining > 0, 'owned QMP absolute deadline exceeded')
            vm.s.settimeout(remaining)
            line = vm.f.readline(65537)
            total += len(line.encode('utf-8'))
            require(line.endswith('\n') and total <= 65536, 'owned QMP reply missing or exceeds byte bound')
            reply = json.loads(line)
            require(type(reply) is dict, 'unexpected owned QMP record')
            if 'event' in reply:
                continue
            require(reply.get('id') == request['id'] and 'return' in reply and 'error' not in reply,
                    'owned QMP command failed or response identity differs')
            return reply['return']
        raise DisplayError('owned QMP message limit exceeded')
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        vm.s.settimeout(previous_timeout)


class TaskbarDisplay:
    """Own only a private root bus, log and directory; no host desktop bus."""
    def __init__(self):
        require(os.geteuid() == 0, 'taskbar display fixture requires container root')
        for program in ('dbus-daemon', 'gdbus'):
            require(shutil.which(program) is not None, 'missing host tool: ' + program)
        self.root = self.bus = self.log = self.raw_fd = None
        self.closed = False
        self.proof = self.deadline = None
        try:
            with defer_signals():
                self.root = Path(tempfile.mkdtemp(prefix='arctic-tb-display-', dir='/tmp'))
                os.chmod(self.root, 0o700)
                require(len(os.fsencode(self.root / 'bus')) < 100, 'private socket path too long')
                self.address = 'unix:path=' + str(self.root / 'bus')
                self.display_arg = 'dbus,addr=' + self.address + ',gl=off'
                self.raw_fd = os.open(self.root / 'bus.log', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                self.log = os.fdopen(self.raw_fd, 'w')
                self.raw_fd = None
                env = dict(os.environ); env.pop('DBUS_SESSION_BUS_ADDRESS', None)
                self.bus = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--nosyslog',
                                             '--address=' + self.address], env=env,
                                            stdout=self.log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 10
            while True:
                require(self.bus.poll() is None, 'private D-Bus daemon exited')
                try:
                    entry = (self.root / 'bus').lstat()
                except FileNotFoundError:
                    require(time.monotonic() < deadline, 'private D-Bus socket timed out')
                    time.sleep(.05); continue
                require(stat.S_ISSOCK(entry.st_mode) and entry.st_uid == 0, 'invalid private D-Bus socket')
                break
            self._private_root()
        except BaseException:
            self.close()
            raise

    def _private_root(self):
        entry = self.root.lstat()
        require(stat.S_ISDIR(entry.st_mode) and entry.st_uid == 0
                and stat.S_IMODE(entry.st_mode) == 0o700 and not self.closed, 'private bus directory changed')
        require(self.bus is not None and self.bus.poll() is None, 'private bus is not alive')

    def _budget(self, maximum=10):
        remaining = maximum if self.deadline is None else min(maximum, self.deadline - time.monotonic())
        require(remaining > 0, 'taskbar display preparation deadline exceeded')
        return remaining

    def _call(self, path, method, *arguments, destination='org.qemu'):
        self._private_root()
        result = subprocess.run(['gdbus', 'call', '--address', self.address, '--dest', destination,
                                 '--object-path', path, '--method', method, *arguments],
                                text=True, capture_output=True, timeout=self._budget())
        require(result.returncode == 0 and len(result.stdout) <= 8192 and len(result.stderr) <= 8192,
                'private QEMU D-Bus call failed: ' + method)
        return result.stdout

    def _property(self, index, name, owner):
        return self._call('/org/qemu/Display1/Console_' + str(index),
                          'org.freedesktop.DBus.Properties.Get', 'org.qemu.Display1.Console', name, destination=owner)

    def _owner(self, vm):
        require(vm.proc.poll() is None, 'owned QEMU process exited')
        path, interface = '/org/freedesktop/DBus', 'org.freedesktop.DBus.'
        owner = string_reply(self._call(path, interface + 'GetNameOwner', 'org.qemu', destination='org.freedesktop.DBus'))
        require(re.fullmatch(r':[0-9]+\.[0-9]+', owner) is not None, 'invalid QEMU bus owner')
        pid = uint32_reply(self._call(path, interface + 'GetConnectionUnixProcessID', owner, destination='org.freedesktop.DBus'))
        uid = uint32_reply(self._call(path, interface + 'GetConnectionUnixUser', owner, destination='org.freedesktop.DBus'))
        require(pid == vm.proc.pid and uid == os.geteuid() == 0, 'display owner differs from owned root QEMU')
        return owner

    def _query(self, vm, command, arguments=None):
        return qmp_query(vm, command, arguments, seconds=self._budget())

    def _paused(self, vm):
        value = self._query(vm, 'query-status')
        require(type(value) is dict and value.get('running') is False
                and value.get('status') in ('prelaunch', 'paused'), 'prepare taskbar heads before the VM runs')

    def _gpu(self, vm):
        children = self._query(vm, 'qom-list', {'path': '/machine/peripheral'})
        require(type(children) is list and sum(value.get('name') == GPU_ID and value.get('type') == 'child<virtio-vga>'
                for value in children if type(value) is dict) == 1, 'owned fixture virtio-vga identity missing')
        outputs = self._query(vm, 'qom-get', {'path': '/machine/peripheral/' + GPU_ID, 'property': 'max_outputs'})
        require(type(outputs) is int and outputs == 2, 'fixture GPU scanout count differs')
        buses = self._query(vm, 'query-pci')
        require(type(buses) is list, 'owned GPU PCI inventory missing')
        devices = [device for bus in buses if type(bus) is dict and bus.get('bus') == 0
                   for device in bus.get('devices', []) if type(device) is dict and device.get('qdev_id') == GPU_ID]
        require(len(devices) == 1 and devices[0].get('bus') == 0
                and type(devices[0].get('slot')) is int and 0 <= devices[0]['slot'] <= 31
                and type(devices[0].get('function')) is int and 0 <= devices[0]['function'] <= 7,
                'fixture GPU must be a unique root-bus PCI device')
        return 'pci/0000/' + format(devices[0]['slot'], '02x') + '.' + str(devices[0]['function'])

    def enable(self, vm):
        require(self.proof is None, 'display fixture already enabled')
        self.deadline = time.monotonic() + 120
        self._paused(vm)
        gpu_address = self._gpu(vm)
        self._private_root()
        result = subprocess.run(['gdbus', 'wait', '--address', self.address, '--timeout', '15', 'org.qemu'],
                                text=True, capture_output=True, timeout=self._budget(20))
        require(result.returncode == 0, 'owned QEMU D-Bus display did not become ready')
        owner = self._owner(vm)
        values = console_ids_reply(self._call('/org/qemu/Display1/VM', 'org.freedesktop.DBus.Properties.Get',
                                  'org.qemu.Display1.VM', 'ConsoleIDs', destination=owner))
        graphics = []
        for index in values:
            kind = string_reply(self._property(index, 'Type', owner), variant=True)
            require(kind in ('Graphic', 'Text'), 'unsupported QEMU console type')
            if kind == 'Graphic':
                graphics.append({'console_id': index, 'head': uint32_reply(self._property(index, 'Head', owner), variant=True),
                                 'device_address': string_reply(self._property(index, 'DeviceAddress', owner), variant=True)})
        require(len(graphics) == 2 and {value['head'] for value in graphics} == {0, 1}
                and all(value['device_address'] == gpu_address for value in graphics), 'two heads of owned fixture GPU required')
        graphics.sort(key=lambda value: value['head'])
        for value in graphics:
            require(self._owner(vm) == owner, 'QEMU bus owner changed before UIInfo')
            value.update(width_mm=340, height_mm=190, xoff=value['head'] * 1280, yoff=0, width=1280, height=720)
            answer = self._call('/org/qemu/Display1/Console_' + str(value['console_id']),
                                'org.qemu.Display1.Console.SetUIInfo', 'uint16 340', 'uint16 190',
                                'int32 ' + str(value['xoff']), 'int32 0', 'uint32 1280', 'uint32 720', destination=owner)
            require(answer.strip() == '()', 'unexpected SetUIInfo completion')
        require(self._owner(vm) == owner, 'QEMU bus owner changed after UIInfo')
        self._paused(vm)
        require(self._gpu(vm) == gpu_address, 'owned fixture GPU changed')
        self.proof = {'schema': 'arctic-qemu-taskbar-display-v1', 'status': 'uiinfo_applied_pending_guest_two_output_evidence',
                      'qemu_pid': vm.proc.pid, 'qemu_uid': 0, 'gpu_id': GPU_ID, 'bus_pid': self.bus.pid,
                      'bus_owner': owner, 'heads': graphics, 'display_backend': 'dbus', 'guest_monitor_verification_required': True}
        return self.proof

    def close(self):
        if self.closed:
            return
        errors, interrupts = [], []
        def attempt(action):
            try:
                action()
            except BaseException as exc:
                (errors if isinstance(exc, Exception) else interrupts).append(exc)
        with defer_signals():
            if self.bus is not None:
                for action in ('terminate', 'wait', 'kill', 'wait'):
                    def stop(action=action):
                        if self.bus.poll() is None:
                            if action == 'wait':
                                try: self.bus.wait(timeout=5)
                                except subprocess.TimeoutExpired: pass
                            else: getattr(self.bus, action)()
                    attempt(stop)
                attempt(lambda: require(self.bus.poll() is not None, 'private daemon remains alive'))
            if self.log is not None:
                attempt(self.log.close)
            if self.raw_fd is not None:
                attempt(lambda: os.close(self.raw_fd))
                self.raw_fd = None
            if self.root is not None and self.root.exists():
                attempt(lambda: shutil.rmtree(self.root))
            self.closed = (self.bus is None or self.bus.poll() is not None) and (self.log is None or self.log.closed) \
                          and self.raw_fd is None and (self.root is None or not self.root.exists())
        if interrupts:
            raise interrupts[0]
        require(not errors, 'owned display cleanup failed: ' + ', '.join(type(error).__name__ for error in errors))

    def __enter__(self):
        return self

    def __exit__(self, exception_type, exception, traceback):
        self.close()
        return False
