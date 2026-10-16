#!/usr/bin/env python3
"""Run the private host/guest protocol for exact-image showcase captures."""
from __future__ import annotations

import argparse
import base64
import ctypes
import gzip
import hashlib
import io
import json
import os
import select
import shutil
import signal
import socket
import stat
import struct
import subprocess
import sys
import tarfile
import time
from pathlib import Path

try:
    from . import contract as c
    from . import guest
except ImportError:
    import contract as c
    import guest


TOOLING_PREFIX = "ARCTIC-SHOWCASE-TOOLING-V1 "
READY_PREFIX = "ARCTIC-SHOWCASE-PROBE-READY "
GO_PREFIX = "ARCTIC-SHOWCASE-CAPTURE-GO "
QEMU = Path("/usr/bin/qemu-system-x86_64")
MAX_LINE = 256_000
TOOLING_FILES = ("capture_vm.py", "contract.py", "guest.py", "capture_probe.py", "unattended.py")
# The Dictation transport ceiling includes the unchanged 1,800-second readiness
# gate, Settings' unchanged 120-second readiness gate, their bounded subprocess
# overruns, and enough time for the guest to deliver its fixed failure enum.  It
# does not extend either readiness gate or any screen/acceptance predicate.
SCENE_READY_TIMEOUTS = {"dictationsetup": 2_160, "winter": 300, "updates": 180}
SCENE_REQUEST_TIMEOUT = 300
FIRST_LOGIN_SIGNAL_TIMEOUT = 120


class GuestSceneFailure(c.Invalid):
    """One content-free failure stage received over the owned guest channel."""

    def __init__(self, stage: str):
        c.require(stage in c.SCENE_FAILURE_STAGES,
                  "installed scene failure projection differs")
        self.stage = stage
        super().__init__("guest scene reported a bounded failure")


def _tooling_payload():
    """Build the deterministic reviewed guest helper sent over the owned channel."""
    root = Path(__file__).resolve().parent
    probe = root / "capture_probe.py"
    info = _owned_regular(probe, 64 * 1024, root_owner=False)
    c.require(info.st_size == c.PROBE_IDENTITY["bytes"]
              and c.sha256(probe) == c.PROBE_IDENTITY["sha256"],
              "reviewed scene probe source differs")
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        for name in TOOLING_FILES:
            path = root / name
            _owned_regular(path, 256_000)
            data = path.read_bytes()
            entry = tarfile.TarInfo(name)
            entry.size, entry.mode, entry.uid, entry.gid, entry.mtime = len(data), 0o555, 0, 0, 0
            archive.addfile(entry, io.BytesIO(data))
    compressed = gzip.compress(archive_buffer.getvalue(), compresslevel=9, mtime=0)
    encoded = base64.b64encode(compressed).decode("ascii")
    c.require(len(encoded) + len(TOOLING_PREFIX) <= MAX_LINE, "reviewed guest tooling is oversized")
    return encoded, hashlib.sha256(compressed).hexdigest()


def _owned_regular(path: Path, maximum: int, *, private=False, root_owner=False):
    try:
        info = path.lstat()
    except OSError as error:
        raise c.Invalid("input file unavailable") from error
    owners = {0} if root_owner else {0, os.geteuid()}
    c.require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_nlink == 1
              and info.st_uid in owners and not info.st_mode & 0o022
              and (not private or not info.st_mode & 0o077)
              and 0 < info.st_size <= maximum, "input is not one protected regular file")
    return info


def _read_json(path: Path, maximum=256_000, *, private=False):
    _owned_regular(path, maximum, private=private)
    try:
        return c.strict_json(path.read_bytes())
    except OSError as error:
        raise c.Invalid("input file read failed") from error


def _fd_sha256(fd: int) -> str:
    with os.fdopen(os.dup(fd), "rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    os.lseek(fd, 0, os.SEEK_SET)
    return digest


def _open_candidate(path: Path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        info = os.fstat(fd)
        c.require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                  and info.st_uid in (0, os.geteuid()) and not info.st_mode & 0o022
                  and info.st_size == c.IMAGE["bytes"] and _fd_sha256(fd) == c.IMAGE["sha256"],
                  "candidate ISO identity differs")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _create_blank_disk(path: Path):
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.ftruncate(fd, c.VM_DISK_BYTES)
        info = os.fstat(fd)
        c.require(stat.S_ISREG(info.st_mode) and info.st_uid == os.geteuid()
                  and info.st_size == c.VM_DISK_BYTES and not info.st_mode & 0o077,
                  "new installed disk identity differs")
        return fd
    except BaseException:
        os.close(fd)
        raise


def _qemu_identity():
    info = _owned_regular(QEMU, 64 * 1024 * 1024, root_owner=True)
    c.require(info.st_mode & 0o111 and os.access(QEMU, os.X_OK), "trusted QEMU unavailable")
    return {"path": str(QEMU), "bytes": info.st_size, "sha256": c.sha256(QEMU)}


def vm_provenance(qemu_identity, argv):
    encoded_argv = json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode()
    value = {"schema": "arctic-showcase-capture-vm-v1", "qemu": qemu_identity,
             "candidate": {"name": c.IMAGE["name"], "bytes": c.IMAGE["bytes"],
                           "sha256": c.IMAGE["sha256"], "handoff": "verified held file descriptor"},
             "installed_disk": {"format": "raw", "bytes": c.VM_DISK_BYTES,
                                "serial": c.VM_DISK_SERIAL, "bootindex": 0,
                                "initial_state": "new zero-filled sparse file",
                                "handoff": "new held file descriptor"},
             "channel": {"name": c.VM_CHANNEL, "transport": "virtio-serial over owned AF_UNIX",
                         "host_role": "server"},
             "lifecycle": "one QEMU process from blank-disk exact-ISO boot through all captures",
             "qemu_argv": list(argv),
             "qemu_argv_sha256": hashlib.sha256(encoded_argv).hexdigest(),
             "qemu_argv_bytes": len(encoded_argv)}
    c.vm_provenance(value)
    return value


def _qemu_command(qmp: Path, channel: Path, iso_fd: int, disk_fd: int, display: str, accel: str):
    c.require(display in ("gtk,gl=off", "sdl,gl=off", "none") and accel in ("kvm", "tcg"),
              "VM display or accelerator differs")
    cpu = "host" if accel == "kvm" else "max"
    return [str(QEMU), "-machine", f"q35,accel={accel}", "-cpu", cpu, "-smp", "4", "-m", "4096",
            "-display", display, "-device",
            "virtio-vga,max_outputs=1,edid=on,xres=1280,yres=800",
            "-qmp", f"unix:{qmp},server=on,wait=off",
            "-serial", f"file:{qmp.parent / 'serial.log'}", "-monitor", "none",
            "-drive", f"file=/proc/self/fd/{iso_fd},format=raw,media=cdrom,readonly=on,if=none,id=arcticiso",
            "-device", "ide-cd,drive=arcticiso,id=arcticcd,bootindex=1",
            "-drive", f"file=/proc/self/fd/{disk_fd},format=raw,if=none,id=arcticdisk",
            "-device", f"virtio-blk-pci,drive=arcticdisk,serial={c.VM_DISK_SERIAL},bootindex=0",
            "-netdev", "user,id=arcticnet", "-device", "virtio-net-pci,netdev=arcticnet",
            "-device", "qemu-xhci", "-device", "usb-tablet", "-rtc", "base=utc",
            "-chardev", f"socket,id=arcticshowcase,path={channel},server=off",
            "-device", "virtio-serial-pci,id=arcticserial",
            "-device", f"virtserialport,bus=arcticserial.0,chardev=arcticshowcase,name={c.VM_CHANNEL}"]


def _validate_qemu_command(argv, qmp, channel, iso_fd, disk_fd, display, accel):
    expected = _qemu_command(qmp, channel, iso_fd, disk_fd, display, accel)
    c.require(argv == expected and argv[0] == str(QEMU)
              and argv.count("-qmp") == argv.count("-chardev") == 1
              and sum(c.VM_CHANNEL in item for item in argv) == 1,
              "VM command is not the fixed exact-image capture topology")


class Lines:
    def __init__(self, file_descriptor: int, timeout: int):
        self.fd = file_descriptor
        self.timeout = timeout
        self.buffer = bytearray()

    def read(self, timeout=None):
        duration = self.timeout if timeout is None else min(self.timeout, timeout)
        c.require(type(duration) is int and 1 <= duration <= 7200,
                  "private capture channel timeout differs")
        deadline = time.monotonic() + duration
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            c.require(remaining > 0, "private capture channel timed out")
            readable, _, _ = select.select([self.fd], [], [], remaining)
            c.require(readable, "private capture channel timed out")
            block = os.read(self.fd, 4096)
            c.require(block, "private capture channel closed")
            self.buffer.extend(block)
            c.require(len(self.buffer) <= MAX_LINE, "private capture channel line is oversized")
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        try:
            return line.decode("utf-8", "strict")
        except UnicodeError as error:
            raise c.Invalid("private capture channel is not UTF-8") from error

    def write(self, line: str):
        c.require(type(line) is str and "\n" not in line and len(line.encode()) <= MAX_LINE,
                  "private capture channel output invalid")
        data = (line + "\n").encode()
        at = 0
        while at < len(data):
            written = os.write(self.fd, data[at:])
            c.require(written > 0, "private capture channel write failed")
            at += written


def _installed_shell_exchange(lines, random=os.urandom):
    """Issue one fresh bounded challenge over the owned QEMU channel."""
    raw = random(16)
    c.require(type(raw) is bytes and len(raw) == 16,
              "installed shell challenge differs")
    nonce = raw.hex()
    lines.write(c.SHELL_CHALLENGE_PREFIX + nonce)
    return nonce, lines.read(timeout=30)


def _scene_line(lines: Lines, timeout: int) -> str:
    """Read one scene line while recognizing only the fixed safe failure signal."""
    line = lines.read(timeout=timeout)
    if line.startswith(c.SCENE_FAILURE_PREFIX):
        raise GuestSceneFailure(c.scene_failure_line(line))
    return line


def _scene_ready(lines: Lines, expected_scene: str, timeout: int,
                 clock=time.monotonic) -> str:
    """Bind a long silent readiness wait to one fixed guest scene stage."""
    c.require(expected_scene in c.SCENES and type(timeout) is int and timeout > 1,
              "installed scene readiness contract differs")
    deadline = clock() + timeout
    stage = c.scene_stage_line(_scene_line(lines, timeout))
    c.require(stage == expected_scene, "installed scene stage order differs")
    remaining = deadline - clock()
    c.require(remaining > 0, "private capture channel timed out")
    try:
        return _scene_line(lines, max(1, int(remaining)))
    except c.Invalid as error:
        if str(error) == "private capture channel timed out":
            raise GuestSceneFailure(stage) from error
        raise


def _first_login_ready(lines: Lines, controller) -> None:
    """Accept only the fixed pre-Settings signal, then use host pixels/input."""
    signal = _scene_line(lines, FIRST_LOGIN_SIGNAL_TIMEOUT)
    c.require(signal == c.FIRST_LOGIN_READY,
              "fresh-account welcome readiness differs")
    controller.dismiss_first_login()
    lines.write(c.FIRST_LOGIN_ACK)


class QMP:
    def __init__(self, path: Path, process: subprocess.Popen, startup_timeout: int):
        self.socket = self.file = None
        deadline = time.monotonic() + startup_timeout
        try:
            self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            while True:
                try:
                    self.socket.connect(str(path))
                    break
                except OSError as error:
                    if process.poll() is not None:
                        raise c.Invalid("capture VM exited before QMP became ready") from error
                    if time.monotonic() >= deadline:
                        raise c.Invalid("capture VM QMP timed out") from error
                    time.sleep(0.1)
            self.socket.settimeout(15)
            self.file = self.socket.makefile("rwb", buffering=0)
            greeting = self._message()
            c.require(type(greeting) is dict and set(greeting) >= {"QMP"}, "QMP greeting differs")
            self.command("qmp_capabilities")
        except BaseException:
            try:
                self.close()
            except BaseException:
                pass
            raise

    def _message(self):
        raw = self.file.readline(MAX_LINE + 1)
        c.require(raw.endswith(b"\n") and len(raw) <= MAX_LINE, "QMP response unavailable or oversized")
        return c.strict_json(raw)

    def command(self, name: str, arguments=None):
        request = {"execute": name}
        if arguments is not None:
            request["arguments"] = arguments
        self.file.write((json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode())
        while True:
            response = self._message()
            if type(response) is dict and "event" in response:
                continue
            c.require(type(response) is dict and set(response) == {"return"}, "QMP command failed")
            return response["return"]

    def screendump(self, path: Path):
        c.require(path.is_absolute() and not path.exists(), "QMP capture path invalid")
        self.command("screendump", {"filename": str(path), "format": "png"})

    def eject_iso(self):
        # ``arcticcd`` is the fixed guest-device/QOM ID.  QMP's deprecated
        # ``device`` member names a block backend instead, so passing the
        # frontend ID there deterministically returns DeviceNotFound.
        self.command("eject", {"id": "arcticcd", "force": True})

    def quit(self):
        try:
            self.command("quit")
        except (c.Invalid, OSError, socket.timeout):
            pass

    def close(self):
        first = None
        for resource in (self.file, self.socket):
            if resource is not None:
                try:
                    resource.close()
                except BaseException as error:
                    first = first or error
        if first is not None:
            raise first


def _accept_qemu(listener, process, timeout):
    listener.settimeout(timeout)
    connection, _ = listener.accept()
    try:
        pid, uid, _ = struct.unpack("3i", connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        c.require(pid == process.pid and uid == os.geteuid(),
                  "private channel peer is not the owned QEMU process")
        connection.setblocking(True)
        return connection
    except BaseException:
        connection.close()
        raise


def _group_exists(pgid: int):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


def _become_subreaper():
    try:
        result = ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0)
    except (AttributeError, OSError) as error:
        raise c.Invalid("process subreaper unavailable") from error
    c.require(result == 0, "process subreaper unavailable")


def _reap_group_children(pgid: int):
    while True:
        try:
            pid, _ = os.waitpid(-pgid, os.WNOHANG)
        except ChildProcessError:
            return
        if pid == 0:
            return


def _wait_group_gone(pgid: int, process, seconds: float):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        process.poll()
        _reap_group_children(pgid)
        if not _group_exists(pgid):
            return True
        time.sleep(0.05)
    process.poll()
    _reap_group_children(pgid)
    return not _group_exists(pgid)


def _stop_process_group(process, term_timeout=10, kill_timeout=10):
    if process is None:
        return
    pgid = process.pid
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    if not _wait_group_gone(pgid, process, term_timeout):
        try:
            os.killpg(pgid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        c.require(_wait_group_gone(pgid, process, kill_timeout), "capture VM process group did not stop")
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired as error:
        raise c.Invalid("capture VM leader was not reaped") from error


def _close_independently(actions):
    first = None
    for action in actions:
        try:
            action()
        except BaseException as error:
            first = first or error
    return first


def _remove_path(path: Path):
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink(missing_ok=True)


def _install_seal(lines: Lines, progress: list) -> str:
    """Consume only strict lifecycle projections until the install seal arrives."""
    c.require(type(progress) is list and not progress, "installation progress already exists")
    while True:
        if not progress:
            stage_timeout = 300
        elif progress[-1]["status"] == "passed":
            stage_timeout = 60
        else:
            stage_timeout = {
                "live-helper": 300, "graphical-session": 360, "installer-ipc": 240,
                "page-welcome": 180, "page-keyboard": 180, "online-route": 180,
                "page-network": 180, "page-timezone": 180, "page-disk": 180,
                "page-encryption": 180, "page-account": 180, "page-apps": 180,
                "page-summary": 180, "installation": 5400, "target-mount": 180,
                "install-seal": 180, "host-handoff": 60,
            }[progress[-1]["stage"]]
        line = lines.read(stage_timeout)
        if line.startswith(c.INSTALL_PROGRESS_PREFIX):
            value = c.strict_json(line[len(c.INSTALL_PROGRESS_PREFIX):])
            c.install_progress(value)
            c.require(value["sequence"] == len(progress) and len(progress) < 63,
                      "installation progress sequence differs")
            if progress:
                previous = progress[-1]
                c.require(previous["status"] != "failed",
                          "installation progress continued after failure")
                if value["status"] == "passed":
                    c.require(previous["stage"] == value["stage"]
                              and previous["status"] == "started",
                              "installation progress completion differs")
                elif value["status"] == "failed":
                    c.require(previous["stage"] == value["stage"]
                              and previous["status"] == "started",
                              "installation progress failure differs")
                else:
                    c.require(previous["status"] == "passed",
                              "installation progress transition differs")
                    started = [item["stage"] for item in progress
                               if item["status"] == "started"]
                    if previous["stage"] == "online-route":
                        expected = {"page-network", "page-timezone"}
                    elif previous["stage"] == "page-network":
                        expected = {"page-timezone"}
                    else:
                        order = ["live-helper", "graphical-session", "installer-ipc",
                                 "page-welcome", "page-keyboard", "online-route",
                                 "page-timezone", "page-disk", "page-encryption",
                                 "page-account", "page-apps", "page-summary", "installation",
                                 "target-mount", "install-seal", "host-handoff"]
                        c.require(previous["stage"] in order[:-1],
                                  "installation progress has no next stage")
                        expected = {order[order.index(previous["stage"]) + 1]}
                    c.require(value["stage"] in expected and value["stage"] not in started,
                              "installation progress stage order differs")
            else:
                c.require(value["stage"] == "live-helper"
                          and value["status"] in ("started", "failed"),
                          "installation progress start differs")
            progress.append(value)
            if value["status"] == "failed":
                raise c.Invalid("guest installation reported a bounded failure")
            continue
        c.require(line.startswith(c.INSTALL_PREFIX), "installed image seal missing")
        c.require(progress and progress[-1]["stage"] == "host-handoff"
                  and progress[-1]["status"] == "started",
                  "installed image seal arrived before completed lifecycle")
        return line


def _failure_code(error, cleanup_failure) -> str:
    if cleanup_failure is not None:
        return "cleanup-failed"
    message = str(error)
    if message == "private capture channel timed out":
        return "private-channel-timeout"
    if message == "guest installation reported a bounded failure":
        return "guest-install-failed"
    if isinstance(error, GuestSceneFailure):
        return "guest-scene-failed"
    if message.startswith("capture VM exited"):
        return "vm-exited"
    if isinstance(error, OSError):
        return "host-io-failed"
    return "capture-contract-failed"


def _write_failure_report(path: Path, phase: str, progress: list, error, cleanup_failure,
                          live_startup, installed_startup):
    failure_code = _failure_code(error, cleanup_failure)
    value = {"schema": "arctic-showcase-capture-failure-v1", "status": "failed",
             "release_acceptance": False, "image": dict(c.IMAGE), "host_phase": phase,
             "failure_code": failure_code,
             "guest_scene_stage": (error.stage if failure_code == "guest-scene-failed" else None),
             "guest_progress": list(progress), "private_runtime_removed": True,
             "live_startup": live_startup,
             "installed_startup": installed_startup,
             "screens_exported": False, "logs_exported": False, "pixels_exported": False,
             "privacy": {"content": "no guest text, logs, screenshots or pixels exported",
                         "human_review": "not_applicable"}}
    c.capture_failure(value)
    data = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    c.require(len(data) <= 32_768, "capture failure projection is oversized")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                 | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        at = 0
        while at < len(data):
            written = os.write(fd, data[at:])
            c.require(written > 0, "capture failure projection write failed")
            at += written
        os.fsync(fd)
    finally:
        os.close(fd)


def _open_guest_channel(path=None):
    """Open the protected virtio port as the active non-root desktop user."""
    channel = Path(path) if path is not None else Path("/dev/virtio-ports") / c.VM_CHANNEL
    resolved = channel.resolve(strict=True)
    info = resolved.lstat()
    c.require(os.geteuid() > 0 and stat.S_ISCHR(info.st_mode) and info.st_uid == 0
              and not info.st_mode & 0o002,
              "private capture channel is not an ACL-protected root character device")
    try:
        return os.open(resolved, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise c.Invalid("active desktop session cannot open private capture channel") from error


def host_mode(args) -> int:
    try:
        from . import automation, bundle, host
    except ImportError:
        import automation
        import bundle
        import host

    destination = Path(args.output).absolute()
    archive_path = destination.with_name(destination.name + ".tar")
    digest_path = destination.with_name(destination.name + ".digest.json")
    capture_source = destination.with_name(destination.name + ".screened-source")
    for path in (destination, archive_path, digest_path, capture_source):
        c.require(not path.exists() and not path.is_symlink(), "refusing to replace capture output")
    failure_path = Path(args.failure_report).absolute() if args.failure_report else None
    if failure_path is not None:
        c.require(failure_path not in (destination, archive_path, digest_path, capture_source)
                  and not failure_path.exists() and not failure_path.is_symlink(),
                  "refusing to replace capture failure projection")
    execution = dict(c.REVIEWED_EXECUTION)
    c.execution(execution)
    runtime = destination.with_name(destination.name + ".private-runtime")
    c.require(not runtime.exists() and not runtime.is_symlink(), "private runtime path exists")
    runtime.mkdir(mode=0o700)
    qmp_path, channel_path = runtime / "qmp.sock", runtime / "channel.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    process = qmp = connection = controller = None
    iso_fd = disk_fd = log_fd = None
    failure = cleanup_failure = None
    receipts = []
    exported = False
    process_group_stopped = False
    success = None
    tooling_sha256 = None
    guest_progress = []
    phase = "vm-start"
    try:
        listener.bind(str(channel_path))
        os.chmod(channel_path, 0o600)
        listener.listen(1)
        iso_fd = _open_candidate(Path(args.candidate_iso))
        disk_fd = _create_blank_disk(runtime / "installed.raw")
        identity = _qemu_identity()
        argv = _qemu_command(qmp_path, channel_path, iso_fd, disk_fd, args.display, args.accel)
        _validate_qemu_command(argv, qmp_path, channel_path, iso_fd, disk_fd, args.display, args.accel)
        provenance = vm_provenance(identity, argv)
        log_fd = os.open(runtime / "qemu.log", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        _become_subreaper()
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=log_fd, stderr=log_fd,
                                   close_fds=True, pass_fds=(iso_fd, disk_fd), start_new_session=True)
        os.close(log_fd)
        log_fd = None
        qmp = QMP(qmp_path, process, args.timeout)
        connection = _accept_qemu(listener, process, args.timeout)
        lines = Lines(connection.fileno(), args.timeout)
        tooling, tooling_sha256 = _tooling_payload()
        lines.write(TOOLING_PREFIX + tooling)
        fragments = bundle.read_private_fragments(args.private_fragments)
        ocr_identity = bundle.approved_ocr_identity()
        ocr = lambda path: bundle.tesseract_ocr(path, args.ocr_timeout)
        shell_focus_ocr = lambda path: bundle.tesseract_shell_focus_ocr(
            path, args.ocr_timeout)
        c.require(args.unattended and args.display == "none" and args.accel == "kvm",
                  "exact capture requires the reviewed unattended KVM controller")
        controller = automation.Controller(qmp, runtime, ocr, shell_focus_ocr, fragments,
                                           tooling_sha256)
        phase = "live-boot"
        try:
            controller.boot_live_and_start()
        except automation.LiveInstallerGateTimeout as error:
            try:
                if controller.start_live_failure_probe():
                    controller.accept_live_failure_probe(lines.read(timeout=90))
            except (c.Invalid, OSError):
                controller.live_startup.probe("channel-unavailable")
            raise error
        phase = "live-install"
        seal_line = _install_seal(lines, guest_progress)
        # This is an operator transition signal. Its JSON is guest-supplied
        # context and is deliberately not an acceptance/capture predicate.
        seal_context = c.strict_json(seal_line[len(c.INSTALL_PREFIX):])
        c.require(type(seal_context) is dict, "installed image context is not an object")
        phase = "install-screen-verification"
        controller.verify_install_complete()
        phase = "installed-transition"
        qmp.eject_iso()
        controller.qmp_event("installed-transition", "eject-exact-iso")
        lines.write(c.INSTALL_ACK)
        qmp.command("system_reset")
        controller.qmp_event("installed-transition", "system-reset")
        phase = "installed-boot"
        controller.boot_installed_and_start(
            lambda: _installed_shell_exchange(lines))
        # /run is a different filesystem after the installed boot. Deliver the
        # same reviewed helper only after the authenticated shell proves its
        # nonce-bound session over the owned channel. The installed probe came
        # from and remains bound to the immutable live-install marker.
        lines.write(TOOLING_PREFIX + tooling)
        phase = "capture-scenes"
        capture = host.Capture(runtime / "captures", execution, provenance, ocr_identity,
                               qmp.screendump, ocr, fragments)
        for expected_scene in c.SCENES:
            if expected_scene == "dictationsetup":
                _first_login_ready(lines, controller)
            ready = _scene_ready(lines, expected_scene,
                                 SCENE_READY_TIMEOUTS[expected_scene])
            c.require(ready == c.AUTOMATION_READY_PREFIX + expected_scene,
                      "installed unattended scene readiness missing")
            if expected_scene == "dictationsetup":
                controller.verify_first_login_dismissed()
            controller.authorize_scene(expected_scene)
            lines.write(c.AUTOMATION_GO_PREFIX + expected_scene)
            request = _scene_line(lines, SCENE_REQUEST_TIMEOUT)
            # The request is synchronization only. Recheck the fixed surface
            # after every guest diagnostic has finished and immediately before
            # the host-owned QMP capture so diagnostics cannot choose pixels.
            controller.verify_scene(expected_scene)
            ack, receipt = capture.consume(request, expected_scene)
            lines.write(ack)
            receipts.append(receipt)
        c.require(process.poll() is None, "capture VM exited before bundle export")
        phase = "cleanup"
        qmp.quit()
        controller.qmp_event("shutdown", "quit")
        _stop_process_group(process)
        process_group_stopped = True
        qmp.close()
        qmp = None
        connection.close()
        connection = None
        listener.close()
        for descriptor_name in ("iso_fd", "disk_fd"):
            descriptor = iso_fd if descriptor_name == "iso_fd" else disk_fd
            os.close(descriptor)
            if descriptor_name == "iso_fd":
                iso_fd = None
            else:
                disk_fd = None
        # Preserve only the three already screened normalized PNGs. Remove the
        # disk, logs, sockets and all decision screenshots before receipts are
        # finalized, so the controller trace can bind actual private cleanup.
        os.replace(runtime / "captures", capture_source)
        _remove_path(runtime)
        retained = list(capture_source.iterdir())
        c.require(not runtime.exists()
                  and {path.name for path in retained} == {scene + ".png" for scene in c.SCENES}
                  and all(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink()
                          for path in retained),
                  "private capture runtime cleanup failed")
        controller.record("shutdown", "cleanup", {
            "private_runtime_removed": True,
            "process_group_stopped": True,
            "open_image_descriptors": 0,
            "retained_source": "screened-normalized-pngs-only",
        })
        trace = controller.trace()
        receipts = [host.finalize_receipt(receipt, trace) for receipt in receipts]
        bundle.export(capture_source, receipts, destination, archive_path, digest_path,
                      args.ocr_timeout, fragments)
        exported = True
        success = {"ok": True, "bundle": str(destination), "archive": str(archive_path),
                   "digest_contract": str(digest_path),
                   "digest_contract_sha256": c.sha256(digest_path),
                   "guest_tooling_gzip_sha256": tooling_sha256,
                   "release_acceptance": False, "human_review": "pending"}
    except BaseException as error:
        failure = error
    finally:
        actions = [lambda: _stop_process_group(process) if not process_group_stopped else None,
                   lambda: qmp.close() if qmp is not None else None,
                   lambda: connection.close() if connection is not None else None,
                   listener.close]
        for fd in (log_fd, iso_fd, disk_fd):
            if fd is not None:
                actions.append(lambda fd=fd: os.close(fd))
        actions.append(lambda: _remove_path(runtime))
        actions.append(lambda: _remove_path(capture_source))
        cleanup_failure = _close_independently(actions)
        if failure is not None or cleanup_failure is not None:
            _close_independently([lambda path=path: _remove_path(path)
                                  for path in (destination, archive_path, digest_path)])
            safe_projection = (not runtime.exists() and not capture_source.exists()
                               and not any(path.exists() for path in
                                           (destination, archive_path, digest_path)))
            if failure_path is not None and safe_projection:
                report_error = failure if failure is not None else cleanup_failure
                try:
                    live_startup = (controller.live_startup.projection()
                                    if controller is not None else None)
                    installed_startup = (controller.installed_startup.projection()
                                         if controller is not None else None)
                    _write_failure_report(failure_path, phase, guest_progress,
                                          report_error, cleanup_failure, live_startup,
                                          installed_startup)
                except BaseException as error:
                    if failure is None:
                        failure = error
    if failure is not None:
        raise failure
    if cleanup_failure is not None:
        raise cleanup_failure
    c.require(exported, "capture transport was not exported")
    print(json.dumps(success, sort_keys=True, separators=(",", ":")))
    return 0


def guest_mode(args) -> int:
    descriptor = _open_guest_channel()
    try:
        lines = Lines(descriptor, args.timeout)
        lines.write(READY_PREFIX + args.scene)
        c.require(lines.read() == GO_PREFIX + args.scene, "host capture authorization missing")
        facts, identity = guest.collect_untrusted(args.scene)
        session = guest.Session(args.scene, facts, identity)
        lines.write(session.marker())
        session.accept(lines.read())
    finally:
        os.close(descriptor)
    print(json.dumps({"ok": True, "scene": args.scene, "release_acceptance": False,
                      "human_review": "pending"}, sort_keys=True, separators=(",", ":")))
    return 0


def seal_mode(args) -> int:
    seal = guest.seal_installation()
    c.install_seal(seal)
    channel = (Path("/dev/virtio-ports") / c.VM_CHANNEL).resolve(strict=True)
    info = channel.lstat()
    c.require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o002,
              "private capture channel is not a protected character device")
    descriptor = os.open(channel, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
    try:
        lines = Lines(descriptor, args.timeout)
        lines.write(c.INSTALL_PREFIX + json.dumps(seal, sort_keys=True, separators=(",", ":")))
        c.require(lines.read() == c.INSTALL_ACK, "host did not switch to installed disk boot")
    finally:
        os.close(descriptor)
    print(json.dumps({"ok": True, "installed_disk_boot": "requested",
                      "release_acceptance": False}, sort_keys=True, separators=(",", ":")))
    return 0


def parser():
    value = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    subparsers = value.add_subparsers(dest="mode", required=True)
    host_parser = subparsers.add_parser("host", help="boot exact ISO into a new disk and capture",
                                        allow_abbrev=False)
    host_parser.add_argument("--output", required=True)
    host_parser.add_argument("--candidate-iso", required=True)
    host_parser.add_argument("--display", choices=("gtk,gl=off", "sdl,gl=off", "none"),
                             default="gtk,gl=off")
    host_parser.add_argument("--accel", choices=("kvm", "tcg"), default="kvm")
    host_parser.add_argument("--private-fragments")
    host_parser.add_argument("--unattended", action="store_true")
    host_parser.add_argument("--timeout", type=int, default=1800)
    host_parser.add_argument("--ocr-timeout", type=int, default=60)
    host_parser.add_argument("--failure-report")
    guest_parser = subparsers.add_parser("guest", help="request one prepared scene capture",
                                         allow_abbrev=False)
    guest_parser.add_argument("--scene", choices=c.SCENES, required=True)
    guest_parser.add_argument("--timeout", type=int, default=1800)
    seal_parser = subparsers.add_parser("seal-install", help="seal the installed root and reboot from disk",
                                        allow_abbrev=False)
    seal_parser.add_argument("--timeout", type=int, default=1800)
    return value


def main(argv=None) -> int:
    try:
        args = parser().parse_args(argv)
        c.require_active()
        c.require(1 <= args.timeout <= 7200, "capture timeout invalid")
        if args.mode == "host":
            c.require(1 <= args.ocr_timeout <= 300, "OCR timeout invalid")
            return host_mode(args)
        if args.mode == "guest":
            return guest_mode(args)
        return seal_mode(args)
    except (c.Invalid, OSError, socket.timeout) as error:
        print(f"exact-image capture failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
