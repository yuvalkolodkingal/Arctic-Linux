#!/usr/bin/env python3
"""Guest-side diagnostics and one-use showcase capture trigger protocol.

The execution harness supplies facts read from the installed VM.  These helpers
never turn capture evidence into release acceptance and never contain transcript
text.  Commands for collecting the facts are documented in README.md.
"""
from __future__ import annotations

import hashlib
import fcntl
import json
import os
import stat
import subprocess
from pathlib import Path

try:
    from . import contract as c
except ImportError:
    import contract as c


def dictation(facts):
    keys = {"phase", "status", "settings_ready", "settings_page", "settings_clients",
            "recording", "transcribing", "receiver_empty", "transcript_files"}
    c.require(type(facts) is dict and set(facts) == keys, "dictation fact fields differ")
    status = facts["status"]
    c.require(type(status) is dict, "dictation status missing")
    profile = status.get("profile")
    descriptor = c.DICTATION_PROFILES.get(profile)
    c.require(facts["phase"] == "online-installed" and status.get("ok") is True
              and status.get("ready") is True and status.get("state") == "ready"
              and status.get("version") == "1.1.1" and descriptor is not None
              and {key: status.get(key) for key in descriptor} == descriptor
              and all(type(status.get(key)) is type(expected) for key, expected in descriptor.items())
              and status.get("compatibility_required") is False
              and facts["settings_ready"] is True and facts["settings_page"] == "dictation"
              and type(facts["settings_clients"]) is int and facts["settings_clients"] == 1
              and facts["recording"] is False
              and facts["transcribing"] is False and facts["receiver_empty"] is True
              and type(facts["transcript_files"]) is int and facts["transcript_files"] == 0,
              "dictation diagnostic check failed")
    return {"phase": facts["phase"], "status_ok": True, "ready": True, "state": "ready",
            "version": "1.1.1", "profile": profile,
            "model": descriptor["model"], "cpu_variant": descriptor["cpu_variant"],
            "model_download_bytes": descriptor["model_download_bytes"],
            "download_bytes": descriptor["download_bytes"], "compatibility_required": False,
            "settings_ready": True, "settings_page": "dictation",
            "settings_clients": 1, "recording": False, "transcribing": False,
            "receiver_empty": True, "transcript_files": 0}


def wallpaper(facts):
    keys = {"target", "before", "hidden", "restored", "file_hashes", "dialog"}
    c.require(type(facts) is dict and set(facts) == keys, "wallpaper fact fields differ")
    target, before, hidden, restored = facts["target"], facts["before"], facts["hidden"], facts["restored"]
    c.require(target == {"slug": "butterfly-in-gold", "name": "Butterfly in Gold"},
              "wallpaper target differs")
    for value in (before, hidden, restored):
        c.require(type(value) is dict and type(value.get("items")) is list
                  and type(value.get("hiddenArctic")) is list and type(value.get("current")) is str,
                  "wallpaper state invalid")
    find = lambda state: [row for row in state["items"] if type(row) is dict
                           and row.get("slug") == target["slug"]]
    initial = find(before)
    c.require(len(initial) == 1 and before["items"][0].get("slug") == target["slug"]
              and not before["hiddenArctic"]
              and initial[0].get("name") == target["name"]
              and initial[0].get("arctic") is True and initial[0].get("hideable") is True
              and before["current"] != initial[0].get("key"), "wallpaper is not deterministic and hideable")
    hidden_rows = [row for row in hidden["hiddenArctic"] if type(row) is dict
                   and row.get("slug") == target["slug"]]
    restored_rows = find(restored)
    c.require(not find(hidden) and len(hidden_rows) == len(hidden["hiddenArctic"]) == 1
              and restored_rows == initial
              and not restored["hiddenArctic"]
              and before["current"] == hidden["current"] == restored["current"],
              "wallpaper hide/restore diagnostic check failed")
    hashes = facts["file_hashes"]
    c.require(hashes == [c.WALLPAPER_SHA256] * 3, "packaged wallpaper bytes changed or differ from exact source")
    c.require(facts["dialog"] == {
        "title": "Hide “Butterfly in Gold”?",
        "body": "This packaged picture is hidden from the picker and automatic changes. You can restore it below.",
    }, "real wallpaper dialog text differs")
    return {"target_slug": target["slug"], "target_name": target["name"],
            "target_not_current": True, "hideable": True,
            "before_json_sha256": c.json_hash(before), "hidden_json_sha256": c.json_hash(hidden),
            "restored_json_sha256": c.json_hash(restored), "packaged_sha256_before": hashes[0],
            "packaged_sha256_hidden": hashes[1], "packaged_sha256_restored": hashes[2],
            "absent_after_hide": True, "hidden_once": True, "returned_after_restore": True,
            "hidden_empty": True, "current_unchanged": True,
            "dialog_title": facts["dialog"]["title"], "dialog_body": facts["dialog"]["body"]}


def updates(facts):
    keys = {"installed", "live", "notes_source_sha256", "notes_installed_sha256", "ipc",
            "surface"}
    c.require(type(facts) is dict and set(facts) == keys, "What's New fact fields differ")
    c.require(facts["installed"] is True and facts["live"] is False
              and facts["notes_source_sha256"] == c.WHATS_NEW_SHA256
              and facts["notes_installed_sha256"] == facts["notes_source_sha256"]
              and facts["ipc"] == "arctic-shell-ipc whatsnew open"
              and facts["surface"] == "arctic-whats-new", "What's New diagnostic check failed")
    return {"installed": True, "live": False,
            "notes_source_sha256": facts["notes_source_sha256"],
            "notes_installed_sha256": facts["notes_installed_sha256"], "notes_match": True,
            "ipc": facts["ipc"], "layer_namespace": facts["surface"],
            "manual_reopen": True, "automatic_trigger_proved": False}


DIAGNOSTIC_CHECKS = {"dictationsetup": dictation, "winter": wallpaper, "updates": updates}

PROBE = Path(c.PROBE_IDENTITY["path"])
PROBE_SOURCE = Path(__file__).with_name("capture_probe.py")


def verify_channel_access_rule(path=None):
    """Verify the root-owned rule that grants the active desktop session access."""
    path = Path(c.CHANNEL_RULE_PATH if path is None else path)
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise c.Invalid("installed capture channel access rule unavailable") from error
    try:
        info = os.fstat(fd)
        data = os.read(fd, c.CHANNEL_ACCESS["bytes"] + 1)
        c.require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and info.st_nlink == 1
                  and stat.S_IMODE(info.st_mode) == 0o644
                  and len(data) == c.CHANNEL_ACCESS["bytes"] and data == c.CHANNEL_RULE
                  and hashlib.sha256(data).hexdigest() == c.CHANNEL_ACCESS["sha256"],
                  "installed capture channel access rule differs")
    finally:
        os.close(fd)
    return dict(c.CHANNEL_ACCESS)


def _fd_sha256(fd):
    digest = hashlib.sha256()
    os.lseek(fd, 0, os.SEEK_SET)
    while True:
        block = os.read(fd, 1024 * 1024)
        if not block:
            break
        digest.update(block)
    os.lseek(fd, 0, os.SEEK_SET)
    return digest.hexdigest()


def _verified_probe(path, *, root_owner=True):
    try:
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as error:
        raise c.Invalid("reviewed scene probe unavailable") from error
    try:
        info = os.fstat(fd)
        owners = {0} if root_owner else {0, os.geteuid()}
        c.require(stat.S_ISREG(info.st_mode) and info.st_uid in owners and info.st_nlink == 1
                  and not info.st_mode & (0o222 if root_owner else 0o022) and info.st_mode & 0o111
                  and info.st_size == c.PROBE_IDENTITY["bytes"]
                  and _fd_sha256(fd) == c.PROBE_IDENTITY["sha256"],
                  "reviewed scene probe identity differs")
        named = os.stat(path, follow_symlinks=False)
        c.require((named.st_dev, named.st_ino, named.st_mode, named.st_uid, named.st_nlink,
                   named.st_size) == (info.st_dev, info.st_ino, info.st_mode, info.st_uid,
                                      info.st_nlink, info.st_size),
                  "reviewed scene probe changed while opening")
        try:
            sealed = os.memfd_create("arctic-showcase-capture-probe",
                                     os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
            while True:
                block = os.read(fd, 64 * 1024)
                if not block:
                    break
                at = 0
                while at < len(block):
                    written = os.write(sealed, block[at:])
                    c.require(written > 0, "reviewed scene probe snapshot failed")
                    at += written
            os.fchmod(sealed, 0o500)
            add_seals = getattr(fcntl, "F_ADD_SEALS", 1033)
            seals = (getattr(fcntl, "F_SEAL_SEAL", 0x0001)
                     | getattr(fcntl, "F_SEAL_SHRINK", 0x0002)
                     | getattr(fcntl, "F_SEAL_GROW", 0x0004)
                     | getattr(fcntl, "F_SEAL_WRITE", 0x0008))
            fcntl.fcntl(sealed, add_seals, seals)
            c.require(_fd_sha256(sealed) == c.PROBE_IDENTITY["sha256"],
                      "reviewed scene probe snapshot differs")
        except BaseException:
            try:
                os.close(sealed)
            except (OSError, UnboundLocalError):
                pass
            raise
        os.close(fd)
        return sealed
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        raise


def _flatten_lsblk(nodes):
    result = []
    for node in nodes:
        c.require(type(node) is dict, "lsblk node differs")
        result.append(node)
        result.extend(_flatten_lsblk(node.get("children", [])))
    return result


def installed_from_snapshot(snapshot):
    """Derive installed provenance from kernel/block facts, never operator identity."""
    keys = {"cmdline", "root_device", "lsblk", "marker_bytes", "marker_mode", "marker_uid",
            "marker_immutable", "boot_id", "desktop_uid", "output", "surface"}
    c.require(type(snapshot) is dict and set(snapshot) == keys, "system snapshot fields differ")
    cmdline = snapshot["cmdline"]
    root_device = snapshot["root_device"].split("[", 1)[0]
    tokens = cmdline.split() if type(cmdline) is str else []
    c.require(type(cmdline) is str and not any(token == "rd.live.image"
              or token.startswith("rd.live.image=") or token.startswith("root=live:")
              for token in tokens),
              "live kernel cannot produce installed capture proof")
    c.require(type(root_device) is str and root_device.startswith("/dev/")
              and root_device not in ("/dev/root", "/dev/loop0"),
              "root filesystem is not backed by the capture disk")
    nodes = _flatten_lsblk(snapshot["lsblk"])
    by_name = {str(node.get("kname") or node.get("name")): node for node in nodes}
    current = Path(os.path.realpath(root_device)).name
    chain = []
    seen = set()
    while current:
        c.require(current not in seen and current in by_name, "root backing chain is incomplete")
        seen.add(current)
        node = by_name[current]
        chain.append(current)
        parent = node.get("pkname")
        if not parent:
            c.require(node.get("type") == "disk" and node.get("serial") == c.VM_DISK_SERIAL,
                      "root is not on the fixed capture disk")
            break
        c.require(type(parent) is str, "root backing chain parent differs")
        current = parent
    marker_bytes = snapshot["marker_bytes"]
    c.require(type(marker_bytes) is bytes and 0 < len(marker_bytes) <= 16_384
              and snapshot["marker_uid"] == 0
              and stat.S_IMODE(snapshot["marker_mode"]) == 0o444
              and snapshot["marker_immutable"] is True,
              "installed provenance marker is not immutable and root-owned")
    marker = c.strict_json(marker_bytes)
    c.install_marker(marker)
    c.require(marker["disk_serial"] == by_name[chain[-1]].get("serial"),
              "installed marker disk differs from root backing disk")
    proof = {"disk_serial": c.VM_DISK_SERIAL, "root_device": root_device,
             "root_chain": chain, "live": False, "marker_path": c.INSTALL_MARKER,
             "marker_sha256": hashlib.sha256(marker_bytes).hexdigest(),
             "marker_immutable": True, "image": marker["image"], "probe": marker["probe"],
             "channel_access": marker["channel_access"],
             "installation_id_sha256": c.hashed(marker["installation_id"])}
    c.installed(proof)
    return proof


def _run(command, *, maximum=256_000, desktop=False, pass_fds=()):
    environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
    if desktop:
        for key in ("DBUS_SESSION_BUS_ADDRESS", "HOME", "USER", "WAYLAND_DISPLAY",
                    "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_RUNTIME_DIR"):
            if key in os.environ:
                environment[key] = os.environ[key]
    try:
        result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL, timeout=30, check=False,
                                env=environment, pass_fds=pass_fds)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise c.Invalid("system provenance probe failed") from error
    c.require(result.returncode == 0 and len(result.stdout) <= maximum,
              "system provenance probe failed")
    return result.stdout


def collect_system(scene):
    """Collect guest-local diagnostics; host acceptance never trusts this report."""
    channel_access = verify_channel_access_rule()
    probe_fd = _verified_probe(PROBE)
    marker_path = Path(c.INSTALL_MARKER)
    marker_info = marker_path.lstat()
    c.require(stat.S_ISREG(marker_info.st_mode) and not marker_path.is_symlink()
              and marker_info.st_nlink == 1 and 0 < marker_info.st_size <= 16_384,
              "installed provenance marker is not one regular file")
    lsattr = _run(["/usr/bin/lsattr", "-d", str(marker_path)]).decode("utf-8", "strict")
    try:
        probe = c.strict_json(_run([f"/proc/self/fd/{probe_fd}", scene], desktop=True,
                                   pass_fds=(probe_fd,)))
    finally:
        os.close(probe_fd)
    c.require(type(probe) is dict and set(probe) == {"facts", "output", "surface"},
              "installed scene probe output differs")
    snapshot = {"cmdline": Path("/proc/cmdline").read_text(),
                "root_device": _run(["/usr/bin/findmnt", "-n", "-o", "SOURCE", "/"])
                               .decode().strip(),
                "lsblk": c.strict_json(_run(["/usr/bin/lsblk", "-J", "-o",
                                              "NAME,KNAME,TYPE,SERIAL,PKNAME"]))["blockdevices"],
                "marker_bytes": marker_path.read_bytes(), "marker_mode": marker_info.st_mode,
                "marker_uid": marker_info.st_uid,
                "marker_immutable": "i" in lsattr.split()[0],
                "boot_id": Path("/proc/sys/kernel/random/boot_id").read_text().strip(),
                "desktop_uid": os.getuid(), "output": probe["output"], "surface": probe["surface"]}
    installed = installed_from_snapshot(snapshot)
    c.require(installed["channel_access"] == channel_access,
              "installed marker and channel access rule differ")
    identity = {"image": installed["image"], "installed": installed,
                "boot_id": snapshot["boot_id"], "desktop_uid": snapshot["desktop_uid"],
                "output": snapshot["output"], "surface": snapshot["surface"]}
    return probe["facts"], identity


def collect_untrusted(scene):
    """Best-effort diagnostics: collection failure must never become a host gate."""
    try:
        return collect_system(scene)
    except (c.Invalid, OSError, UnicodeError):
        return ({"available": False, "trust": "untrusted_guest_diagnostic"},
                {"available": False, "trust": "untrusted_guest_diagnostic"})


def seal_installation(random=os.urandom, target_root=Path("/mnt/sysroot")):
    """Seal exact ISO provenance into the newly installed root before its first boot."""
    c.require(os.geteuid() == 0, "installation seal requires root")
    root_source = _run(["/usr/bin/findmnt", "-n", "-o", "SOURCE", "/"]).decode().strip()
    cmdline = Path("/proc/cmdline").read_text()
    c.require(root_source in ("overlay", "LiveOS_rootfs") and "rd.live.image" in cmdline.split(),
              "installation seal is not running from the exact live environment")
    disk_link = Path("/dev/disk/by-id") / ("virtio-" + c.VM_DISK_SERIAL)
    disk_device = disk_link.resolve(strict=True)
    c.require(disk_device.name.startswith("vd"), "fixed target disk unavailable")
    target_source = _run(["/usr/bin/findmnt", "-n", "-o", "SOURCE", str(target_root)]) \
                    .decode().strip().split("[", 1)[0]
    c.require(target_source.startswith("/dev/"), "installed target root is not block backed")
    current = Path(os.path.realpath(target_source))
    for _ in range(16):
        device_type = _run(["/usr/bin/lsblk", "-ndo", "TYPE", str(current)]).decode().strip()
        if device_type == "disk":
            serial = _run(["/usr/bin/lsblk", "-ndo", "SERIAL", str(current)]).decode().strip()
            c.require(current == disk_device and serial == c.VM_DISK_SERIAL,
                      "installed target root is on the wrong disk")
            break
        parent = _run(["/usr/bin/lsblk", "-ndo", "PKNAME", str(current)]).decode().strip()
        c.require(parent, "installed target root backing chain is incomplete")
        current = Path("/dev") / parent
    else:
        raise c.Invalid("installed target root backing chain is unbounded")
    iso = Path("/dev/sr0")
    iso_size = _run(["/usr/bin/blockdev", "--getsize64", str(iso)]).decode().strip()
    c.require(iso_size.isdigit(), "mounted ISO byte size unavailable")
    iso_bytes = int(iso_size)
    c.require(iso.exists() and iso_bytes == c.IMAGE["bytes"]
              and c.sha256(iso) == c.IMAGE["sha256"], "mounted ISO identity differs")
    source_fd = _verified_probe(PROBE_SOURCE, root_owner=False)
    installed_probe = target_root / c.PROBE_IDENTITY["path"].lstrip("/")
    installed_probe.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    target_base = target_root.resolve(strict=True)
    expected_parent = target_base / "usr/libexec"
    actual_parent = installed_probe.parent.resolve(strict=True)
    parent_info = actual_parent.lstat()
    c.require(actual_parent == expected_parent and stat.S_ISDIR(parent_info.st_mode)
              and parent_info.st_uid == 0 and not parent_info.st_mode & 0o022,
              "installed scene probe directory differs")
    target_fd = os.open(installed_probe, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0), 0o555)
    try:
        while True:
            block = os.read(source_fd, 1024 * 1024)
            if not block:
                break
            at = 0
            while at < len(block):
                written = os.write(target_fd, block[at:])
                c.require(written > 0, "installed scene probe copy failed")
                at += written
        os.fsync(target_fd)
    finally:
        os.close(source_fd)
        os.close(target_fd)
    os.chmod(installed_probe, 0o555)
    check_fd = _verified_probe(installed_probe)
    os.close(check_fd)
    rule = target_root / c.CHANNEL_RULE_PATH.lstrip("/")
    rule.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    rule_fd = os.open(rule, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                      | getattr(os, "O_NOFOLLOW", 0), 0o644)
    try:
        c.require(os.write(rule_fd, c.CHANNEL_RULE) == len(c.CHANNEL_RULE),
                  "installed capture channel rule copy failed")
        os.fsync(rule_fd)
    finally:
        os.close(rule_fd)
    os.chmod(rule, 0o644)
    rule_info = rule.lstat()
    c.require(stat.S_ISREG(rule_info.st_mode) and rule_info.st_uid == 0
              and rule_info.st_nlink == 1 and stat.S_IMODE(rule_info.st_mode) == 0o644
              and c.sha256(rule) == c.CHANNEL_ACCESS["sha256"],
              "installed capture channel rule differs")
    marker = {"schema": "arctic-installed-image-provenance-v1", "image": c.IMAGE,
              "disk_serial": c.VM_DISK_SERIAL, "installation_id": random(16).hex(),
              "source_device": "/dev/sr0", "probe": c.PROBE_IDENTITY,
              "channel_access": c.CHANNEL_ACCESS,
              "release_acceptance": False}
    c.install_marker(marker)
    target = target_root / c.INSTALL_MARKER.lstrip("/")
    target.parent.mkdir(parents=True, mode=0o755, exist_ok=True)
    os.chmod(target.parent, 0o755)
    parent = target.parent.lstat()
    c.require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == 0
              and stat.S_IMODE(parent.st_mode) == 0o755,
              "installed marker directory is not readable and root-owned")
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o444)
    data = (json.dumps(marker, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(target, 0o444)
    _run(["/usr/bin/chattr", "+i", str(target)])
    return {"schema": "arctic-showcase-install-seal-v1", "live": True,
            "root_source": root_source, "target_disk_serial": c.VM_DISK_SERIAL,
            "iso": c.IMAGE, "probe": c.PROBE_IDENTITY,
            "channel_access": c.CHANNEL_ACCESS,
            "marker_sha256": hashlib.sha256(data).hexdigest(),
            "release_acceptance": False}


class Session:
    """One guest process owns one scene request and accepts one bound ACK."""

    def __init__(self, scene, facts, identity, random=os.urandom):
        c.require(scene in c.SCENES, "unknown scene")
        report = {"facts": facts, "identity": identity}
        report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False).encode()
        c.require(len(report_bytes) <= 256_000, "guest diagnostic report is oversized")
        diagnostics = {"trust": "untrusted_guest_diagnostic", "bytes": len(report_bytes),
                       "sha256": hashlib.sha256(report_bytes).hexdigest(),
                       "installed_marker": "contextual_only", "acceptance_effect": "none"}
        nonce = random(16).hex()
        c.require(c.fullmatch(c.HEX32, nonce), "nonce generator differs")
        self.value = {"schema": "arctic-showcase-capture-request-v1", "scene": scene, "nonce": nonce,
                      "diagnostics": diagnostics, "release_acceptance": False}
        c.request(self.value)
        self.emitted = False
        self.used = False

    def marker(self):
        c.require(not self.used and not self.emitted, "capture request already emitted or consumed")
        self.emitted = True
        return c.REQUEST_PREFIX + json.dumps(self.value, sort_keys=True, separators=(",", ":"))

    def accept(self, line):
        c.require(self.emitted and not self.used and type(line) is str and len(line) <= 4096
                  and line.startswith(c.ACK_PREFIX),
                  "capture ACK unavailable or duplicated")
        value = c.strict_json(line[len(c.ACK_PREFIX):])
        c.ack(value, self.value)
        self.used = True
        return {"scene": self.value["scene"], "capture_sha256": value["capture_sha256"],
                "release_acceptance": False}
