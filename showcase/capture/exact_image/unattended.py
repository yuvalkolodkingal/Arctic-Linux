#!/usr/bin/env python3
"""Fixed guest half of the unattended exact-image showcase controller.

The host owns every QMP input and capture decision.  This helper performs only
the reviewed installer IPC sequence and fixed scene commands, then supplies the
same explicitly untrusted diagnostics used by the operator-driven lane.
"""
from __future__ import annotations

import argparse
import json
import os
import pwd
import re
import select
import stat
import subprocess
import time
from pathlib import Path

try:
    from . import contract as c
    from . import guest
except ImportError:
    import contract as c
    import guest


PASSWORD = "ArcticShowcase-Disposable-2026-Only!!!"
USERNAME = c.CONTROLLER["account"]["username"]
HOSTNAME = c.CONTROLLER["account"]["hostname"]
MAX_LINE = 256_000


class InstallerIdentityChanged(RuntimeError):
    """The unique installer IPC endpoint changed after controller input began."""


class InstallerIpcFailure(c.Invalid):
    """Carry one reviewed, content-free installer readiness failure category."""

    def __init__(self, reason: str):
        c.require(reason in c.INSTALLER_IPC_FAILURE_REASONS,
                  "installer IPC failure category differs")
        self.reason = reason
        super().__init__(reason)


class Channel:
    def __init__(self, timeout: int, *, require_nonroot: bool):
        path = (Path("/dev/virtio-ports") / c.VM_CHANNEL).resolve(strict=True)
        info = path.lstat()
        c.require(stat.S_ISCHR(info.st_mode) and info.st_uid == 0
                  and not info.st_mode & 0o002
                  and ((os.geteuid() > 0) == require_nonroot),
                  "unattended private channel differs")
        self.fd = os.open(path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        self.timeout = timeout
        self.buffer = bytearray()

    def close(self):
        os.close(self.fd)

    def write(self, line: str):
        c.require(type(line) is str and "\n" not in line and len(line.encode()) <= MAX_LINE,
                  "unattended channel output invalid")
        data = (line + "\n").encode()
        while data:
            written = os.write(self.fd, data)
            c.require(written > 0, "unattended channel write failed")
            data = data[written:]

    def read(self):
        deadline = time.monotonic() + self.timeout
        while b"\n" not in self.buffer:
            remaining = deadline - time.monotonic()
            c.require(remaining > 0, "unattended channel timed out")
            readable, _, _ = select.select([self.fd], [], [], remaining)
            c.require(readable, "unattended channel timed out")
            block = os.read(self.fd, 4096)
            c.require(block, "unattended channel closed")
            self.buffer.extend(block)
            c.require(len(self.buffer) <= MAX_LINE, "unattended channel line oversized")
        line, _, rest = self.buffer.partition(b"\n")
        self.buffer = bytearray(rest)
        try:
            return line.decode("utf-8", "strict")
        except UnicodeError as error:
            raise c.Invalid("unattended channel is not UTF-8") from error


class InstallProgress:
    """Send only an enumerated, content-free lifecycle projection to the host."""

    def __init__(self, channel: Channel):
        self.channel = channel
        self.sequence = 0
        self.stage = None

    def emit(self, stage: str, status: str, failure_reason=None):
        value = {"schema": "arctic-showcase-install-progress-v1",
                 "sequence": self.sequence, "stage": stage, "status": status,
                 "release_acceptance": False}
        if failure_reason is not None:
            value["failure_reason"] = failure_reason
        c.install_progress(value)
        self.channel.write(c.INSTALL_PROGRESS_PREFIX
                           + json.dumps(value, sort_keys=True, separators=(",", ":")))
        self.sequence += 1

    def start(self, stage: str):
        self.stage = stage
        self.emit(stage, "started")

    def pass_stage(self, stage: str):
        c.require(self.stage == stage, "installation progress stage differs")
        self.emit(stage, "passed")

    def fail(self, failure_reason=None):
        if self.stage is not None and self.sequence < 64:
            self.emit(self.stage, "failed", failure_reason)


def _run(argv, *, env=None, timeout=30, maximum=256_000, check=True):
    c.require(type(argv) is list and argv and all(type(item) is str for item in argv),
              "unattended command differs")
    try:
        result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, env=env, timeout=timeout,
                                check=False)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise c.Invalid("unattended command failed") from error
    c.require(len(result.stdout) <= maximum and (not check or result.returncode == 0),
              "unattended command failed")
    return result


def _wait(function, seconds: int, message: str):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            value = function()
        except (c.Invalid, OSError, ValueError, KeyError):
            value = None
        if value:
            return value
        time.sleep(1)
    raise c.Invalid(message)


def _graphical_environment(username: str):
    account = pwd.getpwnam(username)
    if username == USERNAME:
        c.require(account.pw_uid == c.CONTROLLER["account"]["uid"],
                  "installed disposable UID differs")
    rows = _run(["/usr/bin/loginctl", "list-sessions", "--no-legend"], maximum=32_768) \
        .stdout.decode("utf-8", "strict").splitlines()
    sessions = []
    for row in rows:
        fields = row.split()
        if len(fields) >= 3 and fields[2] == username:
            sid = fields[0]
            kind = _run(["/usr/bin/loginctl", "show-session", sid, "-p", "Type", "--value"]) \
                .stdout.decode().strip()
            vt = _run(["/usr/bin/loginctl", "show-session", sid, "-p", "VTNr", "--value"]) \
                .stdout.decode().strip()
            # The host deliberately switches to a private VT before launching
            # this helper. The one Wayland session is therefore inactive until
            # the reviewed helper returns to its fixed VT.
            if kind == "wayland" and vt.isdigit() and int(vt) > 0:
                sessions.append((sid, int(vt)))
    c.require(len(sessions) == 1, "one active graphical session is required")
    runtime = Path("/run/user") / str(account.pw_uid)
    c.require(runtime.is_dir() and not runtime.is_symlink(), "graphical runtime differs")
    candidates = []
    for process in Path("/proc").glob("[0-9]*"):
        try:
            info = process.stat()
            raw = (process / "environ").read_bytes()
            if info.st_uid != account.pw_uid or len(raw) > 256_000:
                continue
            values = {}
            for entry in raw.split(b"\0"):
                if b"=" in entry:
                    key, value = entry.split(b"=", 1)
                    if key in (b"DBUS_SESSION_BUS_ADDRESS", b"WAYLAND_DISPLAY", b"XDG_RUNTIME_DIR"):
                        values[key.decode()] = value.decode("utf-8", "strict")
            if set(values) == {"DBUS_SESSION_BUS_ADDRESS", "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR"} \
                    and values["XDG_RUNTIME_DIR"] == str(runtime):
                candidates.append(values)
        except (OSError, UnicodeError):
            continue
    c.require(candidates and all(value == candidates[0] for value in candidates),
              "graphical session environment is absent or ambiguous")
    environment = {"PATH": "/usr/bin:/bin", "HOME": account.pw_dir, "USER": username,
                   "LOGNAME": username, "LC_ALL": "C", **candidates[0]}
    return account, sessions[0][1], environment


def _as_user(account, environment, argv, *, timeout=30, check=True):
    if os.geteuid() == account.pw_uid:
        return _run(argv, env=environment, timeout=timeout, check=check)
    command = ["/usr/sbin/runuser", "-u", account.pw_name, "--", "/usr/bin/env"]
    command.extend(f"{key}={value}" for key, value in sorted(environment.items()))
    command.extend(argv)
    return _run(command, timeout=timeout, check=check)


def _find_ipc(account, environment, target: str, method: str, proc_root=Path("/proc")):
    """Call only the one exact packaged Quickshell process.

    Probing every Quickshell PID makes readiness depend on unrelated shell IPC
    servers and lets one slow server consume most of the outer wait budget.
    Exact argv and executable matching gives each bounded readiness sample one
    candidate and still fails closed if two installer instances exist.
    """
    packaged_argv = {
        "installer": ["-p", "/usr/share/arctic/installer-ui"],
        "settings": ["-n", "-d", "-p", "/usr/share/arctic/settings"],
    }
    c.require(target in packaged_argv and re.fullmatch(r"[a-z]+", method),
              "IPC target or method differs")
    candidates = []
    for process in proc_root.glob("[0-9]*"):
        try:
            if (not re.fullmatch(r"[1-9][0-9]{0,9}", process.name)
                    or process.stat().st_uid != account.pw_uid
                    or (process / "comm").read_text().strip() != "quickshell"
                    or os.readlink(process / "exe") != "/usr/bin/quickshell"):
                continue
            raw = (process / "cmdline").read_bytes()
            c.require(0 < len(raw) <= 16_384, "Quickshell command line is oversized")
            argv = [value.decode("utf-8", "strict")
                    for value in raw.rstrip(b"\0").split(b"\0")]
            if argv and Path(argv[0]).name == "quickshell" \
                    and argv[1:] == packaged_argv[target]:
                candidates.append(process.name)
        except (FileNotFoundError, ProcessLookupError, OSError, UnicodeError):
            continue
    if not candidates:
        raise InstallerIpcFailure("installer-process-absent")
    if len(candidates) != 1:
        raise InstallerIpcFailure("installer-process-ambiguous")
    pid = candidates[0]
    try:
        before = _process_start_ticks(account, pid, proc_root)
        result = _as_user(account, environment,
                          ["/usr/bin/quickshell", "ipc", "--pid", pid,
                           "call", target, method], timeout=15, check=False)
        unchanged = _process_start_ticks(account, pid, proc_root) == before
    except (c.Invalid, OSError, ValueError, UnicodeError) as error:
        raise InstallerIpcFailure("installer-ipc-call-failed") from error
    if result.returncode != 0 or not unchanged:
        raise InstallerIpcFailure("installer-ipc-call-failed")
    try:
        output = result.stdout.decode("utf-8", "strict").strip()
    except UnicodeError as error:
        raise InstallerIpcFailure("installer-ipc-response-invalid") from error
    return pid, output


def _process_start_ticks(account, pid: str, proc_root=Path("/proc")):
    """Return a PID-reuse-safe identity component for one owned process."""
    c.require(re.fullmatch(r"[1-9][0-9]{0,9}", pid) is not None,
              "installer process identity differs")
    process = proc_root / pid
    info = process.stat()
    c.require(info.st_uid == account.pw_uid, "installer process owner differs")
    raw = (process / "stat").read_text(encoding="utf-8")
    end = raw.rfind(")")
    fields = raw[end + 2:].split() if end > 0 else []
    # starttime is field 22 in proc_pid_stat; fields[0] is field 3 here.
    c.require(len(fields) > 19 and fields[19].isdigit(),
              "installer process start identity differs")
    return int(fields[19])


def _installer_endpoint(account, environment):
    """Find the one live installer IPC target and bind it to process start time."""
    pid, raw = _find_ipc(account, environment, "installer", "state")
    _installer_response(raw)
    try:
        return pid, _process_start_ticks(account, pid)
    except (c.Invalid, OSError, ValueError) as error:
        raise InstallerIpcFailure("installer-ipc-call-failed") from error


def _installer_response(raw):
    """Validate one state reply without retaining or surfacing its text."""
    try:
        value = c.strict_json(raw)
        c.require(type(value) is dict
                  and {"page", "current", "ready", "connected", "busy", "failure"} <= set(value),
                  "installer IPC readiness response differs")
    except (c.Invalid, ValueError, TypeError, UnicodeError) as error:
        raise InstallerIpcFailure("installer-ipc-response-invalid") from error
    return value


def _stable_installer_endpoint(account, environment):
    """Require two consecutive ready observations of the same owned endpoint."""
    previous = None
    last_failure = "installer-never-ready"

    def stable():
        nonlocal previous, last_failure
        try:
            endpoint, value = _installer_state(account, environment)
        except InstallerIpcFailure as error:
            previous = None
            last_failure = error.reason
            return None
        except (c.Invalid, OSError, ValueError, KeyError):
            previous = None
            last_failure = "installer-ipc-response-invalid"
            return None
        ready = value.get("page") == value.get("current") == "welcome" \
            and value.get("ready") is True and value.get("connected") is True \
            and not value.get("busy") and not value.get("failure")
        if not ready:
            previous = None
            last_failure = "installer-never-ready"
            return None
        if endpoint != previous:
            previous = endpoint
            last_failure = "installer-never-ready"
            return None
        return endpoint

    try:
        return _wait(stable, 180, "stable real installer IPC unavailable")
    except c.Invalid as error:
        raise InstallerIpcFailure(last_failure) from error


def _installer_call(account, environment, pid: str, method: str, payload=None):
    c.require(method in ("state", "fill", "next"), "installer IPC method differs")
    argv = ["/usr/bin/quickshell", "ipc", "--pid", pid, "call", "installer", method]
    if payload is not None:
        argv.append(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    try:
        result = _as_user(account, environment, argv, timeout=45)
    except (c.Invalid, OSError, ValueError) as error:
        raise InstallerIpcFailure("installer-ipc-call-failed") from error
    try:
        return result.stdout.decode("utf-8", "strict").strip()
    except (AttributeError, UnicodeError) as error:
        raise InstallerIpcFailure("installer-ipc-response-invalid") from error


def _installer_state(account, environment, binding=None):
    """Read state from the current unique endpoint, rejecting post-input swaps."""
    endpoint = _installer_endpoint(account, environment)
    if binding is not None and endpoint != binding:
        raise InstallerIdentityChanged("installer IPC identity changed after input")
    value = _installer_response(_installer_call(
        account, environment, endpoint[0], "state"))
    try:
        unchanged = _process_start_ticks(account, endpoint[0]) == endpoint[1]
    except (c.Invalid, OSError, ValueError) as error:
        raise InstallerIpcFailure("installer-ipc-call-failed") from error
    if not unchanged:
        raise InstallerIpcFailure("installer-ipc-call-failed")
    return endpoint, value


def _installer_input(account, environment, binding, expected: str, method: str,
                     payload=None, *, require_valid: bool):
    """Recheck all page gates on a unique endpoint immediately before input."""
    def ready_for_input():
        endpoint, value = _installer_state(account, environment, binding)
        return endpoint if value.get("page") == value.get("current") == expected \
            and value.get("ready") is True and value.get("connected") is True \
            and not value.get("busy") and not value.get("failure") \
            and (not require_valid or value.get("valid") is True) else None

    endpoint = _wait(ready_for_input, 90, "installer state changed before input")
    result = _installer_call(account, environment, endpoint[0], method, payload)
    try:
        unchanged = _process_start_ticks(account, endpoint[0]) == endpoint[1]
    except OSError as error:
        raise c.Invalid("installer process disappeared during input") from error
    c.require(unchanged, "installer process changed during input")
    return endpoint, result


def _mount_installed_target(target=Path("/mnt/sysroot")):
    """Remount the unique unencrypted installer root after its normal cleanup."""
    c.require(os.geteuid() == 0 and target.is_absolute() and not target.is_symlink(),
              "installed target mount identity differs")
    disk = (Path("/dev/disk/by-id") / ("virtio-" + c.VM_DISK_SERIAL)).resolve(strict=True)
    c.require(disk.name.startswith("vd"), "fixed installed disk unavailable")
    report = c.strict_json(_run(["/usr/bin/lsblk", "-J", "-o",
        "PATH,NAME,PKNAME,TYPE,FSTYPE,LABEL,PARTLABEL,SERIAL", str(disk)]).stdout)
    rows = report.get("blockdevices")
    c.require(type(rows) is list and len(rows) == 1 and rows[0].get("path") == str(disk)
              and rows[0].get("type") == "disk" and rows[0].get("serial") == c.VM_DISK_SERIAL,
              "installed disk inventory differs")
    candidates = []

    def visit(node):
        c.require(type(node) is dict and type(node.get("children", [])) is list,
                  "installed disk node differs")
        if node.get("type") == "part" and node.get("pkname") == disk.name \
                and node.get("fstype") == "btrfs" and node.get("label") == "arctic" \
                and node.get("partlabel") == "Arctic root" \
                and type(node.get("path")) is str \
                and re.fullmatch(r"/dev/vd[a-z][0-9]{1,3}", node["path"]):
            candidates.append(node["path"])
        for child in node.get("children", []):
            visit(child)

    visit(rows[0])
    c.require(len(candidates) == 1, "unique installed root partition unavailable")
    mounted = _run(["/usr/bin/findmnt", "-n", "-o", "SOURCE", "--mountpoint", str(target)],
                   check=False, maximum=4096)
    c.require(mounted.returncode != 0, "installed target is already mounted")
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    c.require(target.is_dir() and not target.is_symlink() and not any(target.iterdir()),
              "installed target directory differs")
    _run(["/usr/bin/mount", "-o", "subvol=@,compress=zstd:1", candidates[0], str(target)],
         timeout=60)
    source = _run(["/usr/bin/findmnt", "-n", "-o", "SOURCE", "--mountpoint", str(target)],
                  maximum=4096).stdout.decode("utf-8", "strict").strip().split("[", 1)[0]
    c.require(source == candidates[0], "installed target mount source differs")
    return target


def live_install(timeout: int):
    c.require(os.geteuid() == 0 and len(PASSWORD) == 38, "live automation identity differs")
    channel = Channel(timeout, require_nonroot=False)
    progress = InstallProgress(channel)
    try:
        progress.start("live-helper")
        progress.pass_stage("live-helper")
        progress.start("graphical-session")
        account, vt, environment = _wait(lambda: _graphical_environment("liveuser"), 300,
                                         "live graphical session unavailable")
        _run(["/usr/bin/chvt", str(vt)])
        progress.pass_stage("graphical-session")
        progress.start("installer-ipc")
        _stable_installer_endpoint(account, environment)
        progress.pass_stage("installer-ipc")
        # The first IPC reply can race Quickshell/output settling after the
        # private-VT transition. Do not pin that early probe. Before the first
        # input, acquire the one endpoint that has the expected ready page; once
        # input begins, bind every later state read and action to its PID and
        # process start time so a replacement cannot silently lose wizard state.
        binding = None
        pages = ("welcome", "keyboard", "timezone", "disk", "encryption",
                 "account", "apps", "summary")
        values = {
            # Select the language explicitly.  The exact image can expose the
            # Welcome page before its suggested locale has reached the QML
            # page, so page readiness alone does not imply a valid choice.
            "welcome": {"language": "en_US.UTF-8"},
            "keyboard": {"layout": "us", "variant": ""},
            "network": {"offline": False},
            "disk": {"disk": "/dev/vda", "mode": "erase"},
            "encryption": {"enabled": False},
            "account": {"full_name": "Arctic Showcase", "username": USERNAME,
                        "hostname": HOSTNAME, "password": PASSWORD, "confirm": PASSWORD,
                        "autologin": True, "same_as_disk": False},
            "apps": {},
        }
        def complete_page(expected):
            nonlocal binding
            stage = "page-" + expected
            progress.start(stage)
            def ready():
                endpoint, value = _installer_state(account, environment, binding)
                return (endpoint, value) if value.get("page") == value.get("current") == expected \
                    and value.get("ready") is True and value.get("connected") is True \
                    and not value.get("busy") and not value.get("failure") else None
            endpoint, state = _wait(ready, 90, "installer page did not become ready")
            if expected in values:
                endpoint, result = _installer_input(
                    account, environment, binding, expected, "fill", values[expected],
                    require_valid=False)
                binding = endpoint
                c.require(result == "ok",
                          "installer fixed choice failed")
                def valid():
                    current, value = _installer_state(account, environment, binding)
                    return (current, value) if value.get("page") == value.get("current") == expected \
                        and value.get("ready") is True and value.get("valid") is True \
                        and not value.get("busy") and not value.get("failure") else None
                endpoint, state = _wait(valid, 90, "installer fixed choice did not become valid")
            c.require(state.get("valid") is True, "installer fixed choice is invalid")
            endpoint, result = _installer_input(
                account, environment, binding, expected, "next", require_valid=True)
            binding = endpoint
            c.require(result == "ok",
                      "installer Next failed")
            progress.pass_stage(stage)
        for expected in pages[:2]:
            complete_page(expected)
        # A wired online machine intentionally skips Network. If the shipped UI
        # shows it while connectivity settles, choose online and require validity.
        progress.start("online-route")
        def after_keyboard():
            endpoint, value = _installer_state(account, environment, binding)
            return (endpoint, value) if value.get("page") == value.get("current") \
                and value.get("page") in ("network", "timezone") \
                and value.get("ready") is True and value.get("connected") is True \
                and not value.get("busy") and not value.get("failure") else None
        _, next_state = _wait(after_keyboard, 90, "installer online route did not advance")
        progress.pass_stage("online-route")
        if next_state["page"] == "network":
            complete_page("network")
        for expected in pages[2:]:
            complete_page(expected)
        progress.start("installation")
        def finished():
            _, value = _installer_state(account, environment, binding)
            return value if value.get("page") == value.get("current") == "done" \
                and value.get("percent") == 100 and not value.get("failure") else None
        _wait(finished, min(timeout, 5100), "online installation did not complete")
        progress.pass_stage("installation")
        progress.start("target-mount")
        target = _mount_installed_target()
        progress.pass_stage("target-mount")
        progress.start("install-seal")
        try:
            seal = guest.seal_installation(target_root=target)
            c.install_seal(seal)
        finally:
            _run(["/usr/bin/umount", str(target)], timeout=60)
        progress.pass_stage("install-seal")
        progress.start("host-handoff")
        channel.write(c.INSTALL_PREFIX + json.dumps(seal, sort_keys=True, separators=(",", ":")))
        c.require(channel.read() == c.INSTALL_ACK, "host did not authorize installed boot")
    except Exception as error:
        try:
            reason = error.reason if (
                progress.stage == "installer-ipc" and isinstance(error, InstallerIpcFailure)
            ) else None
            progress.fail(reason)
        except Exception:
            pass
        raise
    finally:
        channel.close()


def _settings(account, environment, page: str, reveal: str = ""):
    _as_user(account, environment, ["/usr/bin/arctic-settings", page], check=True)
    pid, _ = _wait(lambda: _find_ipc(account, environment, "settings", "page"), 120,
                   "Settings IPC unavailable")
    if reveal:
        result = _as_user(account, environment,
                          ["/usr/bin/quickshell", "ipc", "--pid", pid, "call", "settings",
                           "reveal", page, reveal])
        c.require(result.stdout.decode().strip() == "ok", "Settings reveal failed")
    def ready():
        current = _as_user(account, environment,
                           ["/usr/bin/quickshell", "ipc", "--pid", pid, "call", "settings", "page"])
        loaded = _as_user(account, environment,
                          ["/usr/bin/quickshell", "ipc", "--pid", pid, "call", "settings", "ready"])
        return pid if current.stdout.decode().strip() == page and loaded.stdout.decode().strip() == "true" else None
    return _wait(ready, 120, "Settings page did not become ready")


def _quit_settings(account, environment):
    try:
        pid, _ = _find_ipc(account, environment, "settings", "page")
    except c.Invalid:
        return
    _as_user(account, environment,
             ["/usr/bin/quickshell", "ipc", "--pid", pid, "call", "settings", "quit"],
             check=False)
    _wait(lambda: not _run(["/usr/bin/kill", "-0", pid], check=False).returncode == 0,
          30, "Settings did not close")


def _dictation_ready(environment):
    result = _run(["/usr/bin/arctic-dictation", "status"], env=environment,
                  timeout=30, check=False, maximum=32_768)
    if result.returncode != 0:
        return None
    value = c.strict_json(result.stdout)
    profile = value.get("profile")
    descriptor = c.DICTATION_PROFILES.get(profile)
    if value.get("ok") is True and value.get("ready") is True \
            and value.get("state") == "ready" and value.get("version") == "1.1.1" \
            and descriptor is not None \
            and all(value.get(key) == expected for key, expected in descriptor.items()) \
            and value.get("compatibility_required") is False:
        return True
    return None


def _scene(channel: Channel, scene: str):
    channel.write(c.AUTOMATION_READY_PREFIX + scene)
    c.require(channel.read() == c.AUTOMATION_GO_PREFIX + scene,
              "host did not authorize fixed scene")
    facts, identity = guest.collect_untrusted(scene)
    session = guest.Session(scene, facts, identity)
    channel.write(session.marker())
    session.accept(channel.read())


def installed_scenes(timeout: int):
    c.require(os.geteuid() > 0 and pwd.getpwuid(os.geteuid()).pw_name == USERNAME,
              "installed automation account differs")
    account, vt, environment = _wait(lambda: _graphical_environment(USERNAME), 300,
                                     "installed graphical session unavailable")
    channel = _wait(lambda: Channel(timeout, require_nonroot=True), 60,
                    "installed channel ACL unavailable")
    try:
        _wait(lambda: _dictation_ready(environment), min(timeout, 1800),
              "online dictation did not become ready")
        _settings(account, environment, "dictation")
        _scene(channel, "dictationsetup")
        _quit_settings(account, environment)

        _settings(account, environment, "appearance", "appearance.wallpaper")
        _scene(channel, "winter")
        _quit_settings(account, environment)

        _as_user(account, environment, ["/usr/bin/arctic-shell-ipc", "whatsnew", "open"])
        _scene(channel, "updates")
    finally:
        channel.close()


def installed_root_launch(timeout: int):
    """Activate the installed GUI as root, then irrevocably run scenes as UID 1000."""
    c.require(os.geteuid() == 0, "installed launcher requires root")
    account, vt, environment = _wait(lambda: _graphical_environment(USERNAME), 300,
                                     "installed graphical session unavailable")
    _run(["/usr/bin/chvt", str(vt)], timeout=15)
    argv = ["/usr/sbin/runuser", "-u", USERNAME, "--", "/usr/bin/env"]
    argv.extend(f"{key}={value}" for key, value in sorted(environment.items()))
    argv.extend(["/usr/bin/python3", str(Path(__file__).resolve()), "installed-scenes",
                 "--timeout", str(timeout)])
    _run(argv, timeout=timeout + 60, maximum=32_768)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("mode", choices=("live-install", "installed-root-launch", "installed-scenes"))
    parser.add_argument("--timeout", type=int, default=3600)
    args = parser.parse_args(argv)
    try:
        c.require(60 <= args.timeout <= 7200, "unattended timeout differs")
        if args.mode == "live-install":
            live_install(args.timeout)
        elif args.mode == "installed-root-launch":
            installed_root_launch(args.timeout)
        else:
            installed_scenes(args.timeout)
        return 0
    except (c.Invalid, OSError, UnicodeError, KeyError, ValueError) as error:
        print("unattended showcase failed: " + str(error), file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
