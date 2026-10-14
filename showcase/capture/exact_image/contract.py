#!/usr/bin/env python3
"""Strict contract shared by the exact-image showcase guest and host."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
from pathlib import Path


class Invalid(RuntimeError):
    pass


IMAGE = {
    "name": "Arctic-Linux-1.2-candidate-38536710765-1-x86_64.iso",
    "bytes": 1_936_279_552,
    "sha256": "b6bbbea37bc761d783e71417878d047bf4d1805feb60d7bbaf2cf0c5a94d05ea",
    "source_sha": "a13d91118fb90b99dbbf1899fadc3e184ea213ca",
    "run_id": 38_536_710_765,
    "artifact_id": 11_883_891_542,
    "archive_bytes": 1_936_466_960,
    "archive_sha256": "83d86c18089e23ce76a0e93616f1b2b677feae2c7530b71b577ce46e6555752c",
    "producer_mode": "frozen-external-paired-v1",
    "producer_receipt_sha256": "11abed9b44a83d253b51c57fab54f19ede0b9eb335cb5637e9b0c5f93501db23",
}
SCENES = ("dictationsetup", "winter", "updates")
OUTPUTS = {
    "dictationsetup": "showcase/assets/dictation-setup-current.png",
    "winter": "showcase/assets/wallpaper-hide-restore-current.png",
    "updates": "showcase/assets/whats-new-current.png",
}
DICTATION_PROFILES = {
    "small-v2": {"model": "small", "cpu_variant": "baseline",
                 "model_download_bytes": 487_601_967, "download_bytes": 506_181_191},
    "turbo-q5-v3": {"model": "large-v3-turbo-q5_0", "cpu_variant": "avx2",
                    "model_download_bytes": 574_041_195, "download_bytes": 678_117_115},
}
WALLPAPER_SHA256 = "7c5d713468aff0be216a3f1c10c18492d495ce9d329fd7f18e674740f572e5fb"
WHATS_NEW_SHA256 = "ac4575f4505b2e82094e7bc1aa3f38b74ce3277db37e33b02c9f9366c5c74b12"
VM_DISK_BYTES = 64 * 1024 * 1024 * 1024
VM_CHANNEL = "org.arctic.showcase.capture"
VM_DISK_SERIAL = "ARCTICSHOWCASE121"
INSTALL_MARKER = "/var/lib/arctic/installed-image-provenance.json"
CHANNEL_RULE_PATH = "/etc/udev/rules.d/70-arctic-showcase-capture.rules"
CHANNEL_RULE = (b'SUBSYSTEM=="virtio-ports", ATTR{name}=="org.arctic.showcase.capture", '
                b'TAG+="uaccess", MODE="0600"\n')
CHANNEL_ACCESS = {"path": CHANNEL_RULE_PATH, "bytes": 98,
                  "sha256": "eb50da9f3435957e04c47c633247785223c1fc8774e47b28bb245cbb79ffa83d",
                  "policy": "root-owned udev uaccess for the active installed desktop session"}
PROBE_IDENTITY = {
    "path": "/usr/libexec/arctic-showcase-capture-probe",
    "bytes": 10_555,
    "sha256": "35f25b5299e18c106078bc2b3e2dcd27327ddc5a78ce62b174796da20c2678be",
}
SCENE_CONTRACTS = {
    "dictationsetup": {"target": "Arctic Settings / Dictation setup",
                       "review": "mandatory human visual review of normalized QMP pixels"},
    "winter": {"target": "Arctic Settings / packaged wallpaper hide and restore",
               "review": "mandatory human visual review of normalized QMP pixels"},
    "updates": {"target": "Arctic What's New",
                "review": "mandatory human visual review of normalized QMP pixels"},
}
REQUEST_PREFIX = "ARCTIC-SHOWCASE-CAPTURE-REQUEST "
ACK_PREFIX = "ARCTIC-SHOWCASE-CAPTURE-ACK "
INSTALL_PREFIX = "ARCTIC-SHOWCASE-INSTALL-SEALED "
INSTALL_ACK = "ARCTIC-SHOWCASE-INSTALL-BOOT-ACK"
AUTOMATION_READY_PREFIX = "ARCTIC-SHOWCASE-AUTOMATION-READY "
AUTOMATION_GO_PREFIX = "ARCTIC-SHOWCASE-AUTOMATION-GO "
HEX32 = re.compile(r"[0-9a-f]{32}")
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
EMAIL = re.compile(r"(?i)\b[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+\b")
MAC = re.compile(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b")
HOME = re.compile(r"/(?:var/)?home/[^\s]+|/root(?:/[^\s]+)?(?=$|[\s)\]}>,'\"])")


def require(condition: object, message: str) -> None:
    if not condition:
        raise Invalid(message)


def fullmatch(pattern, value) -> bool:
    return type(value) is str and pattern.fullmatch(value) is not None


def strict_object(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def strict_json(raw: str | bytes):
    try:
        return json.loads(raw, object_pairs_hook=strict_object)
    except (UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise Invalid("invalid JSON") from error


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hashed(value: str) -> str:
    require(type(value) is str and value != "", "missing private identity")
    return hashlib.sha256(value.encode()).hexdigest()


def image_identity(value) -> None:
    require(type(value) is dict and set(value) == set(IMAGE)
            and all(type(value[key]) is type(expected) and value[key] == expected
                    for key, expected in IMAGE.items()), "exact image identity differs")


REVIEWED_EXECUTION = {
    "repository": "yuvalkolodkingal/Arctic-Linux",
    "workflow": ".github/workflows/iso.yml",
    "run_id": IMAGE["run_id"],
    "source_sha": IMAGE["source_sha"],
    "artifact_id": IMAGE["artifact_id"],
    "artifact_digest": "sha256:" + IMAGE["archive_sha256"],
    "evidence": "reviewed exact candidate build; capture remains human-review pending",
}

CONTROLLER = {
    "schema": "arctic-showcase-unattended-controller-v1",
    "mode": "fixed-qmp-and-owned-virtio-serial",
    "display": "none",
    "accelerator": "kvm",
    "output": {"width": 1280, "height": 800, "scale": 1, "count": 1},
    "account": {"username": "arcticshowcase", "uid": 1000, "hostname": "arctic-showcase",
                "autologin": True, "disposable": True},
    "network_control": "none; QEMU user networking has no host forwarding",
    "input_authority": "host QMP only; guest diagnostics cannot select or authorize input or capture",
    "guest_transport": "owned org.arctic.showcase.capture virtio-serial channel only",
    "release_acceptance": False,
}

OCR_IDENTITY = {
    "path": "/usr/bin/tesseract", "bytes": 39_320,
    "sha256": "9f831cab7525c3dab04af41bda35182af7ea1df9dceeaaa2f3bf207ac45c06a5",
    "version": "tesseract 5.3.4", "languages": ["eng", "osd"],
    "traineddata": {
        "eng": {"path": "/usr/share/tesseract-ocr/5/tessdata/eng.traineddata",
                "bytes": 4_113_088,
                "sha256": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2"},
        "osd": {"path": "/usr/share/tesseract-ocr/5/tessdata/osd.traineddata",
                "bytes": 10_562_727,
                "sha256": "9cf5d576fcc47564f11265841e5ca839001e7e6f38ff7f7aacf46d15a96b00ff"},
    },
    "invocation": ["stdout", "-l", "eng", "--oem", "1", "--psm", "11",
                   "-c", "user_defined_dpi=96"],
    "controller_invocation": ["stdout", "-l", "eng", "--oem", "1", "--psm", "11",
                              "-c", "user_defined_dpi=96", "tsv"],
}


def controller_trace(value) -> None:
    """Validate host-observed unattended input and screen evidence.

    Guest messages never enter this object.  The host controller records only
    its reviewed fixed commands, QMP input, QMP screenshots and approved OCR.
    """
    keys = {"schema", "contract", "tooling_sha256", "events", "status",
            "guest_diagnostics_used", "release_acceptance"}
    require(type(value) is dict and set(value) == keys
            and value["schema"] == "arctic-showcase-unattended-trace-v1"
            and value["contract"] == CONTROLLER
            and fullmatch(HEX64, value["tooling_sha256"])
            and value["status"] == "completed"
            and value["guest_diagnostics_used"] is False
            and value["release_acceptance"] is False,
            "unattended controller trace differs")
    events = value["events"]
    require(type(events) is list and 12 <= len(events) <= 128, "controller event count differs")
    stages = {"live-boot", "live-console", "live-install", "install-complete",
              "installed-transition", "installed-boot", "installed-console", "installed-scenes",
              "dictation-readiness", "dictationsetup", "winter", "updates", "shutdown"}
    screen_expectations = {
        "live-boot": {"install-boot-menu", "live-installer-visible"},
        "live-console": {"live-console-login"},
        "install-complete": {"installer-done"},
        "installed-boot": {"installed-login-ready", "first-login-welcome",
                           "first-login-dismissed"},
        "installed-console": {"installed-console-login", "installed-password-prompt",
                              "installed-shell", "installed-sudo-password"},
        "dictationsetup": {"dictation-ready-page"},
        "winter": {"wallpaper-page", "wallpaper-hide-dialog"},
        "updates": {"whats-new-layer"},
    }
    text_commands = {
        "live-username": (8, "4f8841fb7db59dee76d1f5b74e14010bb1beabce549fa6da7b790f5497dd0f94"),
        "live-install": (359, "611f82bcad1908fa9f9ac8ab51af345364198eb25da419a694821d464436b95e"),
        "installed-username": (14, "b8214c27644e8af628d5030b053746bea3f72aca7325a066a912de18aef48c0a"),
        "installed-shell-proof": (119, "d4e0d2a1ef814035fdc94ff2ff81ebddd74658f5ea8389a4784c75a2bca36466"),
        "installed-scenes": (417, "fdc5975a8303234e9099a11187a3616a6ea59d3b7e8cd83e080b0793efc6b735"),
    }
    key_events = {
        "live-boot": {("home", "down", "ret")},
        "live-console": {("ctrl-alt-f6",), ("ret",)},
        "live-install": {("ret",)},
        "installed-console": {("ctrl-alt-f6",), ("ret",)},
        "installed-boot": {("esc",)},
        "installed-scenes": {("ret",)},
    }
    command_events = {(name, name) for name in ("live-install", "installed-scenes",
                      "dictation-readiness", "dictationsetup", "winter", "updates")}
    qmp_events = {("installed-transition", "eject-exact-iso"),
                  ("installed-transition", "system-reset"), ("shutdown", "quit")}
    sequence = []
    for index, event in enumerate(events):
        require(type(event) is dict and set(event) == {"index", "stage", "kind", "detail"}
                and event["index"] == index and type(event["stage"]) is str
                and event["stage"] in stages
                and event["kind"] in ("screen", "keys", "text", "secret", "pointer", "command", "qmp", "cleanup")
                and type(event["detail"]) is dict,
                "controller event fields differ")
        stage, kind, detail = event["stage"], event["kind"], event["detail"]
        if kind == "screen":
            exact_geometry = detail.get("expectation") in {
                "installer-done", "first-login-welcome", "first-login-dismissed",
                "dictation-ready-page", "wallpaper-page", "wallpaper-hide-dialog",
                "whats-new-layer",
            }
            require(set(detail) == {"bytes", "sha256", "ocr_sha256", "expectation", "width", "height"}
                    and type(detail["bytes"]) is int and 0 < detail["bytes"] <= 10 * 1024 * 1024
                    and fullmatch(HEX64, detail["sha256"])
                    and fullmatch(HEX64, detail["ocr_sha256"])
                    and type(detail["width"]) is int and 640 <= detail["width"] <= 3840
                    and type(detail["height"]) is int and 480 <= detail["height"] <= 2160
                    and (not exact_geometry or (detail["width"], detail["height"]) == (1280, 800))
                    and detail["expectation"] in screen_expectations.get(stage, set()),
                    "controller screen record differs")
        elif kind == "keys":
            require(set(detail) == {"names"} and type(detail["names"]) is list
                    and 1 <= len(detail["names"]) <= 8
                    and all(type(item) is str and re.fullmatch(r"[a-z0-9-]{1,32}", item)
                            for item in detail["names"])
                    and tuple(detail["names"]) in key_events.get(stage, set()),
                    "controller key record differs")
        elif kind == "text":
            require(set(detail) == {"command", "characters", "sha256"}
                    and type(detail["command"]) is str and detail["command"] in text_commands
                    and type(detail["characters"]) is int and fullmatch(HEX64, detail["sha256"])
                    and (detail["characters"], detail["sha256"])
                        == text_commands[detail["command"]]
                    and stage in ("live-console", "live-install", "installed-console",
                                  "installed-scenes"), "controller text record differs")
        elif kind == "secret":
            require(detail == {"source": "reviewed-disposable-controller-constant",
                               "characters": 38} and stage == "installed-console",
                    "controller credential record differs")
        elif kind == "pointer":
            require(set(detail) == {"x", "y", "button", "target"}
                    and all(type(detail[key]) is int for key in ("x", "y"))
                    and 300 <= detail["x"] <= 1180 and 80 <= detail["y"] <= 700
                    and detail["button"] == "left" and detail["target"] == "wallpaper-hide-button"
                    and stage == "winter", "controller pointer record differs")
        elif kind == "command":
            require(set(detail) == {"id"} and (stage, detail["id"]) in command_events,
                    "controller command record differs")
        elif kind == "qmp":
            require(set(detail) == {"operation"} and (stage, detail["operation"]) in qmp_events,
                    "controller QMP record differs")
        else:
            require(stage == "shutdown" and detail == {
                "private_runtime_removed": True,
                "process_group_stopped": True,
                "open_image_descriptors": 0,
                "retained_source": "screened-normalized-pngs-only",
            }, "controller cleanup record differs")
        sequence.append((stage, kind))
    required = [("live-boot", "screen"), ("live-console", "keys"),
                ("live-install", "command"), ("install-complete", "screen"),
                ("installed-boot", "screen"), ("dictation-readiness", "command"),
                ("dictationsetup", "screen"), ("winter", "pointer"),
                ("winter", "screen"), ("updates", "screen"), ("shutdown", "qmp"),
                ("shutdown", "cleanup")]
    cursor = 0
    for wanted in required:
        while cursor < len(sequence) and sequence[cursor] != wanted:
            cursor += 1
        require(cursor < len(sequence), "controller required event sequence differs")
        cursor += 1
    require(any(event["stage"] == "installed-boot" and event["kind"] == "screen"
                and event["detail"].get("expectation") == "first-login-welcome"
                for event in events)
            and any(event["stage"] == "installed-boot" and event["kind"] == "keys"
                    and event["detail"] == {"names": ["esc"]} for event in events)
            and any(event["stage"] == "installed-boot" and event["kind"] == "screen"
                    and event["detail"].get("expectation") == "first-login-dismissed"
                    for event in events),
            "fresh-account welcome dismissal evidence differs")
    screen_sequence = [(event["stage"], event["detail"]["expectation"])
                       for event in events if event["kind"] == "screen"]
    required_screens = [
        ("live-boot", "install-boot-menu"), ("live-boot", "live-installer-visible"),
        ("live-console", "live-console-login"), ("install-complete", "installer-done"),
        ("installed-boot", "installed-login-ready"),
        ("installed-console", "installed-password-prompt"),
        ("installed-console", "installed-shell"),
        ("installed-console", "installed-sudo-password"),
        ("installed-boot", "first-login-welcome"),
        ("installed-boot", "first-login-dismissed"),
        ("dictationsetup", "dictation-ready-page"),
        ("dictationsetup", "dictation-ready-page"),
        ("winter", "wallpaper-page"), ("winter", "wallpaper-hide-dialog"),
        ("winter", "wallpaper-hide-dialog"),
        ("updates", "whats-new-layer"), ("updates", "whats-new-layer"),
    ]
    cursor = 0
    for wanted in required_screens:
        while cursor < len(screen_sequence) and screen_sequence[cursor] != wanted:
            cursor += 1
        require(cursor < len(screen_sequence), "controller screen sequence differs")
        cursor += 1
    require([event["detail"]["command"] for event in events if event["kind"] == "text"]
            == ["live-username", "live-install", "installed-username",
                "installed-shell-proof", "installed-scenes"]
            and sum(event["kind"] == "secret" for event in events) == 2
            and [event["detail"]["id"] for event in events if event["kind"] == "command"]
            == ["live-install", "installed-scenes", "dictation-readiness",
                "dictationsetup", "winter", "updates"]
            and [event["detail"]["operation"] for event in events if event["kind"] == "qmp"]
            == ["eject-exact-iso", "system-reset", "quit"]
            and sum(event["kind"] == "pointer" for event in events) == 1
            and sum(event["kind"] == "cleanup" for event in events) == 1,
            "controller exact input or operation inventory differs")
    keys = [(event["stage"], tuple(event["detail"]["names"]))
            for event in events if event["kind"] == "keys"]
    require(keys.count(("live-boot", ("home", "down", "ret"))) == 1
            and keys.count(("live-console", ("ctrl-alt-f6",))) == 1
            and keys.count(("live-console", ("ret",))) == 2
            and keys.count(("live-install", ("ret",))) == 1
            and 1 <= keys.count(("installed-console", ("ctrl-alt-f6",))) <= 70
            and keys.count(("installed-console", ("ret",))) == 4
            and keys.count(("installed-scenes", ("ret",))) == 1
            and keys.count(("installed-boot", ("esc",))) == 1,
            "controller exact key inventory differs")


def execution(value) -> None:
    require(type(value) is dict and value == REVIEWED_EXECUTION
            and all(type(value[key]) is type(expected)
                    for key, expected in REVIEWED_EXECUTION.items()),
            "execution is not the reviewed candidate evidence")


def ocr_identity(value) -> None:
    require(type(value) is dict and value == OCR_IDENTITY, "OCR identity differs")


def probe_identity(value) -> None:
    require(type(value) is dict and value == PROBE_IDENTITY, "scene probe identity differs")


def channel_access(value) -> None:
    require(type(value) is dict and value == CHANNEL_ACCESS, "capture channel access differs")


def installed(value) -> None:
    keys = {"disk_serial", "root_device", "root_chain", "live", "marker_path", "probe",
            "channel_access",
            "marker_sha256", "marker_immutable", "image", "installation_id_sha256"}
    require(type(value) is dict and set(value) == keys, "installed proof fields differ")
    require(value["disk_serial"] == VM_DISK_SERIAL
            and type(value["root_device"]) is str
            and re.fullmatch(r"/dev/[A-Za-z0-9._/+:-]{1,180}", value["root_device"])
            and type(value["root_chain"]) is list and 1 <= len(value["root_chain"]) <= 16
            and all(type(item) is str and re.fullmatch(r"[A-Za-z0-9._:+-]{1,128}", item)
                    for item in value["root_chain"])
            and value["live"] is False and value["marker_path"] == INSTALL_MARKER
            and fullmatch(HEX64, value["marker_sha256"])
            and value["marker_immutable"] is True
            and fullmatch(HEX64, value["installation_id_sha256"]),
            "guest is not proved on the installed capture disk")
    image_identity(value["image"])
    probe_identity(value["probe"])
    channel_access(value["channel_access"])


def install_marker(value) -> None:
    require(type(value) is dict and set(value) == {"schema", "image", "disk_serial", "probe",
            "channel_access",
            "installation_id", "source_device", "release_acceptance"}
            and value["schema"] == "arctic-installed-image-provenance-v1"
            and value["disk_serial"] == VM_DISK_SERIAL
            and fullmatch(HEX32, value["installation_id"])
            and value["source_device"] == "/dev/sr0"
            and value["release_acceptance"] is False, "installed marker differs")
    image_identity(value["image"])
    probe_identity(value["probe"])
    channel_access(value["channel_access"])


def install_seal(value) -> None:
    require(type(value) is dict and set(value) == {"schema", "live", "root_source", "probe",
            "channel_access",
            "target_disk_serial", "iso", "marker_sha256", "release_acceptance"}
            and value["schema"] == "arctic-showcase-install-seal-v1"
            and value["live"] is True and value["root_source"] in ("overlay", "LiveOS_rootfs")
            and value["target_disk_serial"] == VM_DISK_SERIAL
            and fullmatch(HEX64, value["marker_sha256"])
            and value["release_acceptance"] is False, "installation seal differs")
    image_identity(value["iso"])
    probe_identity(value["probe"])
    channel_access(value["channel_access"])


def vm_provenance(value) -> None:
    keys = {"schema", "qemu", "candidate", "installed_disk", "channel", "lifecycle",
            "qemu_argv", "qemu_argv_sha256", "qemu_argv_bytes"}
    require(type(value) is dict and set(value) == keys
            and value["schema"] == "arctic-showcase-capture-vm-v1", "VM provenance fields differ")
    qemu = value["qemu"]
    require(type(qemu) is dict and set(qemu) == {"path", "bytes", "sha256"}
            and qemu["path"] == "/usr/bin/qemu-system-x86_64"
            and type(qemu["bytes"]) is int and 0 < qemu["bytes"] <= 64 * 1024 * 1024
            and fullmatch(HEX64, qemu["sha256"]), "QEMU provenance differs")
    candidate = value["candidate"]
    require(type(candidate) is dict and set(candidate) == {"name", "bytes", "sha256", "handoff"}
            and candidate == {"name": IMAGE["name"], "bytes": IMAGE["bytes"],
                              "sha256": IMAGE["sha256"], "handoff": "verified held file descriptor"},
            "VM candidate handoff differs")
    disk = value["installed_disk"]
    require(type(disk) is dict and set(disk) == {"format", "bytes", "serial", "bootindex",
                                                "initial_state", "handoff"}
            and disk == {"format": "raw", "bytes": VM_DISK_BYTES,
                         "serial": VM_DISK_SERIAL, "bootindex": 0,
                         "initial_state": "new zero-filled sparse file",
                         "handoff": "new held file descriptor"}, "VM installed disk provenance differs")
    channel = value["channel"]
    require(type(channel) is dict and set(channel) == {"name", "transport", "host_role"}
            and channel == {"name": VM_CHANNEL, "transport": "virtio-serial over owned AF_UNIX",
                            "host_role": "server"}, "VM private channel differs")
    require(value["lifecycle"] == "one QEMU process from blank-disk exact-ISO boot through all captures",
            "VM lifecycle provenance differs")
    argv = value["qemu_argv"]
    require(type(argv) is list and len(argv) == 43
            and all(type(item) is str and 0 < len(item) <= 4096
                    and not re.search(r"[\x00-\x1f\x7f]", item) for item in argv)
            and argv[:14] == [qemu["path"], "-machine", "q35,accel=kvm", "-cpu", "host",
                              "-smp", "4", "-m", "4096", "-display", "none", "-device",
                              "virtio-vga,max_outputs=1,edid=on,xres=1280,yres=800", "-qmp"]
            and argv[15] == "-serial" and argv[17:20] == ["-monitor", "none", "-drive"]
            and argv[21:24] == ["-device", "ide-cd,drive=arcticiso,id=arcticcd,bootindex=1",
                                "-drive"]
            and argv[25:] == ["-device",
                "virtio-blk-pci,drive=arcticdisk,serial=ARCTICSHOWCASE121,bootindex=0",
                "-netdev", "user,id=arcticnet", "-device", "virtio-net-pci,netdev=arcticnet",
                "-device", "qemu-xhci", "-device", "usb-tablet", "-rtc", "base=utc",
                "-chardev", argv[38], "-device", "virtio-serial-pci,id=arcticserial", "-device",
                "virtserialport,bus=arcticserial.0,chardev=arcticshowcase,name=" + VM_CHANNEL],
            "QEMU argv topology differs")
    qmp_match = re.fullmatch(r"unix:(/[A-Za-z0-9_./-]+/qmp\.sock),server=on,wait=off", argv[14])
    iso_match = re.fullmatch(
        r"file=/proc/self/fd/([0-9]+),format=raw,media=cdrom,readonly=on,if=none,id=arcticiso",
        argv[20])
    disk_match = re.fullmatch(
        r"file=/proc/self/fd/([0-9]+),format=raw,if=none,id=arcticdisk", argv[24])
    channel_match = re.fullmatch(
        r"socket,id=arcticshowcase,path=(/[A-Za-z0-9_./-]+/channel\.sock),server=off", argv[38])
    require(qmp_match is not None and iso_match is not None and disk_match is not None
            and channel_match is not None and iso_match.group(1) != disk_match.group(1)
            and argv[16] == "file:" + str(Path(qmp_match.group(1)).with_name("serial.log"))
            and Path(qmp_match.group(1)).parent == Path(channel_match.group(1)).parent,
            "QEMU argv dynamic resources differ")
    encoded = json.dumps(argv, ensure_ascii=False, separators=(",", ":")).encode()
    require(fullmatch(HEX64, value["qemu_argv_sha256"])
            and value["qemu_argv_sha256"] == hashlib.sha256(encoded).hexdigest()
            and type(value["qemu_argv_bytes"]) is int
            and value["qemu_argv_bytes"] == len(encoded) <= 32_768,
            "QEMU argv provenance differs")


def output(value) -> None:
    require(type(value) is dict and set(value) == {"name", "width", "height", "scale", "count"},
            "output fields differ")
    require(type(value["name"]) is str and re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value["name"]),
            "output name invalid")
    require(all(type(value[key]) is int for key in ("width", "height", "scale", "count"))
            and value["width"] == 1280 and value["height"] == 800 and value["scale"] == 1
            and value["count"] == 1, "capture output is not one 1280x800 scale-1 output")


def surface(value, scene: str) -> None:
    require(type(value) is dict and set(value) == {"kind", "identity", "count", "focused"},
            "surface fields differ")
    require(type(value["identity"]) is str and 0 < len(value["identity"]) <= 128
            and type(value["count"]) is int and value["count"] == 1
            and value["focused"] is True, "surface identity differs")
    expected = "Arctic Settings" if scene in ("dictationsetup", "winter") else "arctic-whats-new"
    expected_kind = "client-title" if scene in ("dictationsetup", "winter") else "layer-namespace"
    require(value["kind"] == expected_kind and value["identity"] == expected,
            "wrong capture surface")


def request(value) -> None:
    keys = {"schema", "scene", "nonce", "diagnostics", "release_acceptance"}
    require(type(value) is dict and set(value) == keys, "request fields differ")
    require(value["schema"] == "arctic-showcase-capture-request-v1" and value["scene"] in SCENES
            and fullmatch(HEX32, value["nonce"])
            and value["release_acceptance"] is False and type(value["diagnostics"]) is dict
            and len(json.dumps(value["diagnostics"], sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode()) <= 32_768,
            "request identity differs")


def ack(value, request_value) -> None:
    require(type(value) is dict and set(value) == {"schema", "scene", "nonce", "capture_sha256",
                                                  "release_acceptance"}, "ack fields differ")
    require(value["schema"] == "arctic-showcase-capture-ack-v1"
            and value["scene"] == request_value["scene"] and value["nonce"] == request_value["nonce"]
            and fullmatch(HEX64, value["capture_sha256"])
            and value["release_acceptance"] is False, "ack binding differs")


def privacy_text(text: str, private_fragments=()) -> None:
    require(type(text) is str and len(text) <= 256_000, "OCR text invalid")
    require(not EMAIL.search(text) and not MAC.search(text) and not HOME.search(text),
            "private text pattern in capture")
    for token in re.findall(r"(?<![0-9A-Fa-f:])(?:\d{1,3}\.){3}\d{1,3}(?![0-9A-Fa-f:])", text):
        try:
            ipaddress.ip_address(token)
        except ValueError:
            continue
        raise Invalid("IP address in capture")
    for token in re.findall(r"(?i)(?<![0-9a-f:])[0-9a-f]*:[0-9a-f:.]+(?![0-9a-f:])", text):
        try:
            ipaddress.ip_address(token.strip("[](),.;"))
        except ValueError:
            continue
        raise Invalid("IP address in capture")
    lowered = text.casefold()
    require("private_sentinel" not in lowered, "private sentinel in capture")
    for fragment in private_fragments:
        require(type(fragment) is str and len(fragment) >= 12, "private fragment too short")
        require(fragment.casefold() not in lowered, "private transcript fragment in capture")


def json_hash(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False).encode()).hexdigest()


def _sha_record(value, keys, label):
    require(type(value) is dict and set(value) == set(keys), f"{label} fields differ")
    require(type(value["path"]) is str and re.fullmatch(r"[a-z0-9-]+(?:-qmp-original)?\.png",
                                                        value["path"])
            and type(value["bytes"]) is int and 0 < value["bytes"] <= 10 * 1024 * 1024
            and fullmatch(HEX64, value["sha256"]), f"{label} identity differs")


def receipt(value) -> None:
    """Validate the exact, completed guest/host receipt schema.

    This is deliberately shared by the producer and exported-bundle verifier so
    the latter cannot silently accept a parallel or weaker evidence shape.
    """
    keys = {"schema", "scene", "status", "release_acceptance", "image", "execution", "vm", "ocr", "controller",
            "scene_contract", "guest_context", "capture", "output", "privacy", "limitations"}
    require(type(value) is dict and set(value) == keys, "receipt fields differ")
    scene = value["scene"]
    require(value["schema"] == "arctic-showcase-exact-capture-v1" and scene in SCENES
            and value["status"] == "captured_unreviewed"
            and value["release_acceptance"] is False, "receipt identity differs")
    image_identity(value["image"])
    execution(value["execution"])
    vm_provenance(value["vm"])
    ocr_identity(value["ocr"])
    controller_trace(value["controller"])
    require(value["scene_contract"] == SCENE_CONTRACTS[scene],
            "host reviewed scene contract differs")
    require(value["guest_context"] == {
        "trust": "untrusted diagnostic input; excluded from this acceptance receipt",
        "used_for_capture_gate": False, "used_for_release_acceptance": False,
        "installed_marker": "guest-local contextual evidence only",
    }, "guest trust boundary differs")
    capture = value["capture"]
    require(type(capture) is dict and set(capture) == {"method", "bytes", "sha256", "pixel_sha256",
            "format", "width", "height", "retained", "exported", "evidence_scope"},
            "capture fields differ")
    require(capture["method"] == "host QMP screendump format=png for fixed reviewed scene contract"
            and type(capture["bytes"]) is int and 0 < capture["bytes"] <= 10 * 1024 * 1024
            and fullmatch(HEX64, capture["sha256"])
            and fullmatch(HEX64, capture["pixel_sha256"]) and capture["format"] == "PNG"
            and type(capture["width"]) is int and capture["width"] == 1280
            and type(capture["height"]) is int and capture["height"] == 800
            and capture["retained"] is False and capture["exported"] is False
            and capture["evidence_scope"] == "procedural source record only; raw QMP PNG omitted after lossless normalization",
            "capture record differs")
    normalized = value["output"]
    _sha_record(normalized, {"path", "bytes", "sha256", "pixel_sha256", "format", "width",
                                    "height", "transformation", "pillow_version"}, "output")
    require(normalized["path"] == scene + ".png" and fullmatch(HEX64, normalized["pixel_sha256"])
            and normalized["format"] == "PNG" and type(normalized["width"]) is int
            and normalized["width"] == 1280 and type(normalized["height"]) is int
            and normalized["height"] == 800
            and normalized["transformation"] == "Pillow RGB lossless PNG re-encode; metadata stripped; no crop/resize/redaction"
            and type(normalized["pillow_version"]) is str
            and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}(?:[A-Za-z0-9.+-]*)?", normalized["pillow_version"]),
            "normalized output record differs")
    require(capture["pixel_sha256"] == normalized["pixel_sha256"],
            "raw and normalized pixel binding differs")
    require(value["privacy"] == {"automated": "passed", "human": "pending", "redactions": []},
            "receipt privacy state differs")
    require(value["limitations"] == ["This showcase capture is not release acceptance.",
            "Human review of the exact normalized pixels remains pending.",
            "Guest facts and the installed marker are untrusted diagnostics and do not satisfy a capture or acceptance gate.",
            "The raw QMP PNG is omitted; only its procedural record and normalized review object remain."],
            "receipt limitations differ")
