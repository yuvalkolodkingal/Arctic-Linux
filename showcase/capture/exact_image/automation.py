#!/usr/bin/env python3
"""Host-owned unattended QMP controller for exact-image showcase capture."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
import subprocess
import struct
import time
import zlib
from pathlib import Path

from PIL import Image

try:
    from . import bundle
    from . import contract as c
    from . import host
except ImportError:
    import bundle
    import contract as c
    import host


QCODE = {" ": "spc", "=": "equal", ",": "comma", ".": "dot", "-": "minus",
         "/": "slash", ";": "semicolon", "'": "apostrophe", "\\": "backslash",
         "`": "grave_accent", "[": "bracket_left", "]": "bracket_right", "\n": "ret"}
SHIFTED = {"_": "minus", ":": "semicolon", "+": "equal", '"': "apostrophe",
           ">": "dot", "<": "comma", "|": "backslash", "&": "7", "*": "8",
           "(": "9", ")": "0", "$": "4", "~": "grave_accent", "!": "1",
           "@": "2", "#": "3", "%": "5", "^": "6", "{": "bracket_left",
           "}": "bracket_right", "?": "slash"}

BOOTSTRAP_FAILURE = {"schema": "arctic-showcase-install-progress-v1", "sequence": 0,
                     "stage": "live-helper", "status": "failed",
                     "release_acceptance": False}
c.install_progress(BOOTSTRAP_FAILURE)
BOOTSTRAP_FAILURE_LINE = (c.INSTALL_PROGRESS_PREFIX
                          + json.dumps(BOOTSTRAP_FAILURE, sort_keys=True,
                                       separators=(",", ":")))
# One unquoted shell word: the only space and JSON quotes are escaped. The
# fixed value contains none of the expansion characters accepted by the shell.
BOOTSTRAP_FAILURE_WORD = BOOTSTRAP_FAILURE_LINE.replace(" ", "\\ ").replace('"', '\\"')
c.require(not re.search(r"[`$';&|<>()[\]*?]", BOOTSTRAP_FAILURE_WORD),
          "bootstrap failure shell projection differs")


def chord_for(character: str):
    if character.isalnum() and character.isascii():
        return ["shift", character.lower()] if character.isupper() else [character]
    if character in QCODE:
        return [QCODE[character]]
    if character in SHIFTED:
        return ["shift", SHIFTED[character]]
    raise c.Invalid("unattended text contains an unsupported character")


def controller_decode(path: Path):
    """Decode a metadata-free host QMP RGB PNG at a bounded firmware/desktop size."""
    data = path.read_bytes()
    c.require(8 < len(data) <= host.MAX_PNG_BYTES and data.startswith(b"\x89PNG\r\n\x1a\n"),
              "controller screenshot is not a bounded PNG")
    at, state, idats, dimensions = 8, "ihdr", 0, None
    while at < len(data):
        c.require(state != "end" and at + 12 <= len(data),
                  "controller PNG framing differs")
        length = struct.unpack(">I", data[at:at + 4])[0]
        c.require(length <= host.MAX_PNG_BYTES - 12 and at + 12 + length <= len(data),
                  "controller PNG chunk length differs")
        end = at + 12 + length
        kind, body = data[at + 4:at + 8], data[at + 8:end - 4]
        crc = struct.unpack(">I", data[end - 4:end])[0]
        c.require(zlib.crc32(kind + body) & 0xffffffff == crc, "controller PNG CRC differs")
        if kind == b"IHDR":
            c.require(state == "ihdr" and at == 8 and length == 13,
                      "controller PNG IHDR differs")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(
                ">IIBBBBB", body)
            c.require(640 <= width <= 3840 and 480 <= height <= 2160
                      and (depth, color, compression, filtering, interlace) == (8, 2, 0, 0, 0),
                      "controller PNG geometry or mode differs")
            dimensions, state = (width, height), "idat"
        elif kind == b"IDAT":
            c.require(state == "idat" and length > 0, "controller PNG IDAT differs")
            idats += 1
        elif kind == b"IEND":
            c.require(state == "idat" and idats > 0 and length == 0,
                      "controller PNG IEND differs")
            state = "end"
        else:
            raise c.Invalid("controller PNG contains metadata or an unapproved chunk")
        at = end
    c.require(state == "end" and at == len(data), "controller PNG trailing bytes differ")
    try:
        with Image.open(path) as image:
            c.require(image.format == "PNG" and image.mode == "RGB"
                      and image.size == dimensions and image.info == {},
                      "controller PNG decode differs")
            image.load()
            return image.copy()
    except (OSError, ValueError) as error:
        raise c.Invalid("controller PNG decode failed") from error


def _phrases_present(text: str, phrases, *, ordered: bool) -> bool:
    """Match reviewed OCR phrases, optionally requiring their screen order."""
    folded = text.casefold()
    if not ordered:
        return all(phrase.casefold() in folded for phrase in phrases)
    offset = 0
    for phrase in phrases:
        needle = phrase.casefold()
        found = folded.find(needle, offset)
        if found < 0:
            return False
        offset = found + len(needle)
    return True


def _fixed_fish_prompt_present(text: str, account: str, suffixes) -> bool:
    """Accept only a complete final OCR line for the fixed Fish prompt."""
    if (type(text) is not str or type(account) is not str or not account
            or type(suffixes) not in (tuple, list) or not suffixes
            or any(type(item) is not str or not item for item in suffixes)):
        return False
    lines = [line.strip().rstrip("_| ") for line in text.splitlines() if line.strip()]
    accepted = {account + " " + suffix for suffix in suffixes}
    return bool(lines) and lines[-1] in accepted


def _fixed_shell_marker_match(text: str):
    """Find only the fixed proof marker, allowing OCR space around hyphens."""
    if type(text) is not str:
        return None
    return re.search(
        r"(?im)^[ \t]*ARCTIC[ \t]*-[ \t]*SHOWCASE[ \t]*-[ \t]*SHELL"
        r"[ \t]*-[ \t]*READY[ \t]*$", text)


def _fixed_shell_transport_visual_present(text: str, image) -> bool:
    """Require the exact marker and measured suffix-only VT occupancy."""
    if _fixed_shell_marker_match(text) is None:
        return False
    if image.mode != "RGB" or image.size != (1280, 800):
        return False
    return _shell_nonbackground_occupancy(image) in SHELL_TRANSPORT_OCCUPANCY


SHELL_OCCUPANCY_WIDTH = 640
SHELL_OCCUPANCY_BAND_HEIGHT = 8
SHELL_OCCUPANCY_BANDS = 16
SHELL_TRANSPORT_OCCUPANCY = (
    (542, 364, 20, 8) + (0,) * 12,
    (542, 364, 20, 24) + (0,) * 12,
)


def _shell_nonbackground_occupancy(image):
    """Count nonblack pixels in fixed private bands without retaining pixels."""
    c.require(image.mode == "RGB" and image.size == (1280, 800),
              "controller shell occupancy source geometry differs")
    pixels = image.load()
    return tuple(
        sum(pixels[x, y] != (0, 0, 0)
            for y in range(band * SHELL_OCCUPANCY_BAND_HEIGHT,
                           (band + 1) * SHELL_OCCUPANCY_BAND_HEIGHT)
            for x in range(SHELL_OCCUPANCY_WIDTH))
        for band in range(SHELL_OCCUPANCY_BANDS)
    )


LIVE_SURFACES = (
    "capture-error", "geometry-mismatch", "blank-output", "ocr-empty",
    "boot-menu", "boot-progress", "live-desktop", "installer-partial",
    "installer-error", "console-or-emergency", "other-text", "installer-welcome",
)


def _live_surface_class(image, text: str) -> str:
    """Reduce a private live-boot frame to one reviewed public enum."""
    if image.size != (1280, 800):
        return "geometry-mismatch"
    colors = image.resize((32, 20)).getcolors(maxcolors=640)
    if colors is None or len(colors) < 16:
        return "blank-output"
    folded = text.casefold().strip()
    if not folded:
        return "ocr-empty"
    welcome = ("Welcome to Arctic Linux", "Keyboard", "Time zone", "Summary")
    if _phrases_present(text, welcome, ordered=False):
        return "installer-welcome"
    if any(item.casefold() in folded for item in welcome):
        return "installer-partial"
    if (("try arctic linux" in folded and "install arctic linux" in folded)
            or ("safe graphics mode" in folded and "install arctic linux" in folded)):
        return "boot-menu"
    if any(item in folded for item in (
            "the installer isn't on this usb", "installer has stopped",
            "installer could not start", "application problem detected")):
        return "installer-error"
    if any(item in folded for item in ("emergency mode", "dracut", " login:")):
        return "console-or-emergency"
    if "install arctic linux" in folded:
        return "live-desktop"
    if any(item in folded for item in ("starting arctic linux", "starting version",
                                        "reached target", "loading linux")):
        return "boot-progress"
    return "other-text"


class LiveInstallerGateTimeout(c.Invalid):
    """The authoritative 600-second Welcome-page gate did not pass."""


class LiveStartupDiagnostic:
    """Bounded, privacy-safe projection of the otherwise private live startup."""

    def __init__(self):
        self.started = time.monotonic()
        self.boot_status = "not-observed"
        self.boot_seconds = None
        self.selection_status = "not-sent"
        self.selection_seconds = None
        self.gate_status = "not-started"
        self.gate_started = None
        self.gate_seconds = None
        self.samples = 0
        self.last = "capture-error"
        self.first = {item: None for item in LIVE_SURFACES}
        self.probe_status = "not-run"
        self.mode = self.session = self.installer = "unknown"

    @staticmethod
    def _seconds(start, limit):
        return min(limit, max(0, int(time.monotonic() - start)))

    def boot_observed(self):
        self.boot_status = "observed"
        self.boot_seconds = self._seconds(self.started, 300)

    def selection_sent(self):
        self.selection_status = "sent"
        self.selection_seconds = self._seconds(self.started, 300)

    def gate_start(self):
        self.gate_status = "waiting"
        self.gate_started = time.monotonic()

    def observe(self, surface):
        c.require(surface in LIVE_SURFACES, "live startup surface differs")
        self.samples = min(301, self.samples + 1)
        self.last = surface
        if self.first[surface] is None:
            self.first[surface] = self._seconds(self.gate_started, 600)

    def gate_end(self, status):
        c.require(status in ("passed", "timed-out"), "live startup gate status differs")
        self.gate_status = status
        self.gate_seconds = self._seconds(self.gate_started, 600)

    def probe(self, status, mode="unknown", session="unknown", installer="unknown"):
        c.require(status in ("not-run", "console-unavailable", "command-sent",
                             "channel-unavailable", "completed"),
                  "live startup probe status differs")
        c.require(mode in ("unknown", "install", "other")
                  and session in ("unknown", "running", "absent")
                  and installer in ("unknown", "running", "absent"),
                  "live startup probe value differs")
        self.probe_status, self.mode = status, mode
        self.session, self.installer = session, installer

    def projection(self):
        return {
            "schema": "arctic-showcase-live-startup-diagnostic-v1",
            "release_acceptance": False,
            "boot_menu": {"status": self.boot_status,
                          "elapsed_seconds": self.boot_seconds},
            "selection": {"status": self.selection_status,
                          "elapsed_seconds": self.selection_seconds},
            "welcome_gate": {
                "expectation": "live-installer-visible", "timeout_seconds": 600,
                "status": self.gate_status, "elapsed_seconds": self.gate_seconds,
                "samples": self.samples, "last_observation": self.last,
                "first_observation_seconds": dict(self.first),
            },
            "post_failure_probe": {
                "status": self.probe_status, "boot_mode": self.mode,
                "graphical_session": self.session,
                "installer_process": self.installer,
            },
        }


INSTALLED_SHELL_SURFACES = (
    "capture-error", "geometry-mismatch", "blank-output", "ocr-empty",
    "fetch-greeting", "proof-marker", "prompt-exact", "prompt-not-final", "account-only",
    "suffix-only", "login-or-password", "other-text",
)


def _installed_shell_surface_class(image, text: str, account: str, suffixes) -> str:
    """Reduce a private installed-console frame to one reviewed public enum."""
    if image.size != (1280, 800):
        return "geometry-mismatch"
    if _fixed_shell_transport_visual_present(text, image):
        return "proof-marker"
    colors = image.resize((32, 20)).getcolors(maxcolors=640)
    if colors is None or len(colors) < 16:
        return "blank-output"
    folded = text.casefold().strip()
    if not folded:
        return "ocr-empty"
    if _fixed_fish_prompt_present(text, account, suffixes):
        return "prompt-exact"
    lines = [line.strip().rstrip("_| ") for line in text.splitlines() if line.strip()]
    accepted = {account + " " + suffix for suffix in suffixes}
    if any(line in accepted for line in lines):
        return "prompt-not-final"
    if "arctic linux" in folded and "fish 4.6" in folded:
        return "fetch-greeting"
    if account.casefold() in folded:
        return "account-only"
    if any(line.endswith(tuple(suffixes)) for line in lines):
        return "suffix-only"
    if "login:" in folded or "password:" in folded:
        return "login-or-password"
    return "other-text"


class InstalledShellReadyTimeout(c.Invalid):
    """The authoritative 90-second installed Fish prompt gate did not pass."""


class InstalledStartupDiagnostic:
    """Bounded, privacy-safe projection of installed login and Fish readiness."""

    def __init__(self):
        self.started = None
        self.login_status = "not-observed"
        self.login_seconds = None
        self.authentication = "not-sent"
        self.fetch_status = "not-observed"
        self.fetch_seconds = None
        self.dismissal = "not-sent"
        self.gate_status = "not-started"
        self.gate_started = None
        self.gate_seconds = None
        self.samples = 0
        self.last = "capture-error"
        self.first = {item: None for item in INSTALLED_SHELL_SURFACES}
        self.session_status = "not-proved"
        self.session_challenge_sha256 = None
        self.interrupt_status = "not-run"

    @staticmethod
    def _seconds(start, limit):
        return min(limit, max(0, int(time.monotonic() - start)))

    def start(self):
        c.require(self.started is None, "installed startup diagnostic was restarted")
        self.started = time.monotonic()

    def login_observed(self):
        self.login_status = "observed"
        self.login_seconds = self._seconds(self.started, 900)

    def authentication_sent(self):
        self.authentication = "sent"

    def fetch_observed(self):
        self.fetch_status = "observed"
        self.fetch_seconds = self._seconds(self.started, 1035)

    def dismissal_sent(self):
        self.dismissal = "sent"

    def gate_start(self):
        self.gate_status = "waiting"
        self.gate_started = time.monotonic()

    def session_proved(self, nonce):
        c.require(self.session_status == "not-proved"
                  and type(nonce) is str and c.HEX32.fullmatch(nonce) is not None,
                  "installed shell session proof state differs")
        self.session_status = "proved"
        self.session_challenge_sha256 = hashlib.sha256(nonce.encode()).hexdigest()

    def observe(self, surface):
        c.require(surface in INSTALLED_SHELL_SURFACES,
                  "installed startup surface differs")
        self.samples = min(46, self.samples + 1)
        self.last = surface
        if self.first[surface] is None:
            self.first[surface] = self._seconds(self.gate_started, 90)

    def gate_end(self, status):
        c.require(status in ("passed", "timed-out"),
                  "installed startup gate status differs")
        self.gate_status = status
        self.gate_seconds = self._seconds(self.gate_started, 90)

    def interrupt(self, status):
        c.require(status in ("not-run", "sent-no-prompt", "recovered-prompt",
                             "controller-unavailable"),
                  "installed startup interrupt status differs")
        self.interrupt_status = status

    def projection(self):
        return {
            "schema": "arctic-showcase-installed-startup-diagnostic-v1",
            "release_acceptance": False,
            "login": {"status": self.login_status,
                      "elapsed_seconds": self.login_seconds},
            "authentication": self.authentication,
            "fetch": {"status": self.fetch_status,
                      "elapsed_seconds": self.fetch_seconds},
            "dismissal": self.dismissal,
            "session_transport": {
                "status": self.session_status,
                "transport": "owned-root-virtio-serial",
                "challenge_sha256": self.session_challenge_sha256,
                "identity": "uid-1000-arcticshowcase-at-arctic-showcase-fish",
            },
            "shell_ready_gate": {
                "expectation": "installed-shell-ready", "timeout_seconds": 90,
                "status": self.gate_status, "elapsed_seconds": self.gate_seconds,
                "samples": self.samples, "last_observation": self.last,
                "first_observation_seconds": dict(self.first),
            },
            "post_failure_interrupt": self.interrupt_status,
        }


class Controller:
    """Finite host state machine. Guest JSON and messages never choose actions."""

    LIVE_COMMAND = (
        "sudo sh -c 'set -eu; fail(){ echo " + BOOTSTRAP_FAILURE_WORD
        + " >/dev/virtio-ports/org.arctic.showcase.capture || :; }; trap fail EXIT; "
        "d=/run/arctic-showcase-tooling; install -d -m 0700 $d; "
        "IFS= read -r line </dev/virtio-ports/org.arctic.showcase.capture; "
        "case \"$line\" in \"ARCTIC-SHOWCASE-TOOLING-V1 \"*) ;; *) exit 1;; esac; "
        "printf %s \"${line#ARCTIC-SHOWCASE-TOOLING-V1 }\" | base64 -d | gzip -d | tar -x -C $d; "
        "cd $d; exec python3 unattended.py live-install --timeout 5400'"
    )
    INSTALLED_COMMAND = (
        # Emit a fixed public marker only after the shell executes the command,
        # immediately before sudo's password prompt.  The typed bytes do not
        # contain the marker, so echoed input cannot satisfy the host OCR gate.
        # -k also makes a cached credential unable to skip this proof.
        "printf '\\101\\122\\103\\124\\111\\103\\055\\123\\110\\117\\127\\103\\101\\123\\105"
        "\\055\\101\\125\\124\\110\\055\\122\\105\\101\\104\\131\\072\\040'; exec sudo -k sh -c "
        "'set -eu; d=/run/user/1000/arctic-showcase-tooling; install -d -m 0700 -o 1000 -g 1000 $d; "
        "IFS= read -r line </dev/virtio-ports/org.arctic.showcase.capture; "
        "case \"$line\" in \"ARCTIC-SHOWCASE-TOOLING-V1 \"*) ;; *) exit 1;; esac; "
        "printf %s \"${line#ARCTIC-SHOWCASE-TOOLING-V1 }\" | base64 -d | gzip -d | tar -x -C $d; "
        "chown -R 1000:1000 $d; cd $d; exec python3 unattended.py installed-root-launch --timeout 5400'"
    )
    PASSWORD = "ArcticShowcase-Disposable-2026-Only!!!"
    # A fresh host nonce must be read by the authenticated installed Fish. The
    # guarded branch proves the exact account, host, UID, shell and root-owned
    # character device before it emits a response. The prompt itself contains
    # only the suffix; identity comes from the nonce-bound response, not OCR.
    SHELL_PROOF = (
        "read -l arctic_challenge </dev/virtio-ports/org.arctic.showcase.capture; "
        "if string match -qr '^ARCTIC-SHOWCASE-SHELL-CHALLENGE [0-9a-f]{32}$' "
        "-- $arctic_challenge; and test (id -u) -eq 1000; "
        "and test (id -un) = arcticshowcase; and test (hostname) = arctic-showcase; "
        "and status is-interactive; "
        "and test -c /dev/virtio-ports/org.arctic.showcase.capture; "
        "and test (stat -Lc %u -- /dev/virtio-ports/org.arctic.showcase.capture) -eq 0; "
        "set -l arctic_nonce (string replace 'ARCTIC-SHOWCASE-SHELL-CHALLENGE ' '' "
        "-- $arctic_challenge); "
        "printf 'ARCTIC-SHOWCASE-INSTALLED-SHELL-V1 %s %s %s %s fish\\n' "
        "$arctic_nonce (id -u) (id -un) (hostname) "
        ">/dev/virtio-ports/org.arctic.showcase.capture; "
        "function fish_prompt; set_color brwhite; printf ' ~> '; "
        "set_color normal; end; "
        "printf '\\033[2J\\033[H\\033[1m\\101\\122\\103\\124\\111\\103\\055\\123\\110\\117\\127"
        "\\103\\101\\123\\105\\055\\123\\110\\105\\114\\114\\055\\122"
        "\\105\\101\\104\\131\\033[0m\\n'; end")
    LIVE_STARTUP_PROBE = (
        "m=other; grep -qw arctic.mode=install /proc/cmdline && m=install; "
        "s=absent; pgrep -x mango >/dev/null 2>&1 && s=running; "
        "i=absent; pgrep -u $(id -u) -f 'quickshell.* [-]p /usr/share/arctic/installer-ui' "
        ">/dev/null 2>&1 && i=running; printf 'ARCTIC-SHOWCASE-LIVE-STARTUP-V1 %s %s %s\\n' "
        "$m $s $i >/dev/virtio-ports/org.arctic.showcase.capture"
    )

    def __init__(self, qmp, runtime: Path, ocr, private_fragments, tooling_sha256: str):
        c.require(tooling_sha256 and c.fullmatch(c.HEX64, tooling_sha256),
                  "unattended tooling identity missing")
        self.qmp = qmp
        self.runtime = runtime
        self.ocr = ocr
        self.fragments = tuple(private_fragments)
        self.tooling_sha256 = tooling_sha256
        self.events = []
        self.counter = 0
        self.live_startup = LiveStartupDiagnostic()
        self.installed_startup = InstalledStartupDiagnostic()

    def record(self, stage, kind, detail):
        c.require(type(stage) is str and re.fullmatch(r"[a-z0-9-]{1,64}", stage),
                  "controller stage differs")
        self.events.append({"index": len(self.events), "stage": stage,
                            "kind": kind, "detail": detail})

    def _input(self, events):
        self.qmp.command("input-send-event", {"events": events})

    def press(self, stage: str, *names: str, gap=.18):
        c.require(names and len(names) <= 8, "unattended key sequence differs")
        for name in names:
            chord = name.split("-") if "-" in name else [name]
            down = [{"type": "key", "data": {"down": True,
                     "key": {"type": "qcode", "data": item}}} for item in chord]
            up = [{"type": "key", "data": {"down": False,
                   "key": {"type": "qcode", "data": item}}} for item in reversed(chord)]
            self._input(down + up)
            time.sleep(gap)
        self.record(stage, "keys", {"names": list(names)})

    def type_text(self, stage: str, command_id: str, value: str, gap=.012):
        c.require(1 <= len(value) <= 4096, "unattended typed text length differs")
        for character in value:
            chord = chord_for(character)
            down = [{"type": "key", "data": {"down": True,
                     "key": {"type": "qcode", "data": item}}} for item in chord]
            up = [{"type": "key", "data": {"down": False,
                   "key": {"type": "qcode", "data": item}}} for item in reversed(chord)]
            self._input(down + up)
            time.sleep(gap)
        self.record(stage, "text", {"command": command_id, "characters": len(value),
                    "sha256": hashlib.sha256(value.encode()).hexdigest()})

    def type_secret(self, stage: str):
        c.require(len(self.PASSWORD) == 38, "reviewed disposable credential differs")
        for character in self.PASSWORD:
            chord = chord_for(character)
            down = [{"type": "key", "data": {"down": True,
                     "key": {"type": "qcode", "data": item}}} for item in chord]
            up = [{"type": "key", "data": {"down": False,
                   "key": {"type": "qcode", "data": item}}} for item in reversed(chord)]
            self._input(down + up)
            time.sleep(.025)
        self.record(stage, "secret", {"source": "reviewed-disposable-controller-constant",
                    "characters": 38})

    def _shot(self, label):
        self.counter += 1
        path = self.runtime / f"controller-{self.counter:03d}-{label}.png"
        c.require(not path.exists(), "controller screenshot path reused")
        self.qmp.screendump(path)
        info = host._regular_new(path, host.MAX_PNG_BYTES)
        image = controller_decode(path)
        text = self.ocr(path)
        c.privacy_text(text, self.fragments)
        return path, info, image, text

    def wait_screen(self, stage: str, expectation: str, phrases=(), *, seconds=300,
                    visible=False, retain=False, exact_output=False, ordered=False,
                    prompt_contract=None, transport_prompt=False):
        startup_gate = expectation == "live-installer-visible"
        installed_gate = expectation == "installed-shell-ready"
        if startup_gate:
            self.live_startup.gate_start()
        if installed_gate:
            self.installed_startup.gate_start()
        deadline = time.monotonic() + seconds
        last = None
        while time.monotonic() < deadline:
            path = None
            try:
                path, info, image, text = self._shot(expectation)
                colors = image.resize((32, 20)).getcolors(maxcolors=640)
                nonblank = colors is not None and len(colors) >= 16
                if startup_gate:
                    self.live_startup.observe(_live_surface_class(image, text))
                if installed_gate:
                    account, suffixes = prompt_contract
                    self.installed_startup.observe(
                        _installed_shell_surface_class(image, text, account, suffixes))
                prompt_ok = (prompt_contract is None
                             or (_fixed_shell_transport_visual_present(
                                    text, image)
                                 if transport_prompt else
                                 _fixed_fish_prompt_present(text, *prompt_contract)))
                phrase_ok = (not phrases or _phrases_present(
                    text, phrases, ordered=ordered))
                if (expectation in {"installed-shell-ready", "installed-shell"}
                        and prompt_contract is not None and transport_prompt):
                    phrase_ok = _fixed_shell_transport_visual_present(
                        text, image)
                if (phrase_ok
                        and prompt_ok
                        and (not exact_output or image.size == (1280, 800))
                        and (not visible or nonblank)):
                    detail = {"bytes": info.st_size, "sha256": c.sha256(path),
                              "ocr_sha256": hashlib.sha256(text.encode()).hexdigest(),
                              "expectation": expectation, "width": image.width,
                              "height": image.height}
                    self.record(stage, "screen", detail)
                    if startup_gate:
                        self.live_startup.gate_end("passed")
                    if installed_gate:
                        self.installed_startup.gate_end("passed")
                    kept = path if retain else None
                    if retain:
                        path = None
                    else:
                        path.unlink(missing_ok=True)
                        path = None
                    return kept, text
                last = "screen expectation absent"
            except (c.Invalid, OSError) as error:
                last = str(error)
                if startup_gate:
                    self.live_startup.observe("capture-error")
                if installed_gate:
                    self.installed_startup.observe("capture-error")
            finally:
                if path is not None and path.exists():
                    path.unlink(missing_ok=True)
            time.sleep(2)
        # Expectation is a reviewed public enum.  Do not surface OCR text or a
        # decoder detail in Actions logs when private screenshots are removed.
        if startup_gate:
            self.live_startup.gate_end("timed-out")
            raise LiveInstallerGateTimeout(
                f"controller screen expectation {expectation} absent")
        if installed_gate:
            self.installed_startup.gate_end("timed-out")
            raise InstalledShellReadyTimeout(
                f"controller screen expectation {expectation} absent")
        raise c.Invalid(f"controller screen expectation {expectation} absent")

    def pointer_click(self, stage: str, x: int, y: int):
        c.require(0 <= x < 1280 and 0 <= y < 800, "controller pointer is outside output")
        move = [{"type": "abs", "data": {"axis": "x", "value": x * 0x7fff // 1279}},
                {"type": "abs", "data": {"axis": "y", "value": y * 0x7fff // 799}}]
        self._input(move)
        time.sleep(.4)
        self._input([{"type": "btn", "data": {"down": True, "button": "left"}}])
        time.sleep(.15)
        self._input([{"type": "btn", "data": {"down": False, "button": "left"}}])
        self.record(stage, "pointer", {"x": x, "y": y, "button": "left",
                    "target": "wallpaper-hide-button"})

    def _tsv(self, path: Path):
        bundle.approved_ocr_identity()
        argv = [c.OCR_IDENTITY["path"], str(path), *c.OCR_IDENTITY["controller_invocation"]]
        try:
            result = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=60, check=False,
                                    env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"})
        except (OSError, subprocess.TimeoutExpired) as error:
            raise c.Invalid("controller coordinate OCR failed") from error
        c.require(result.returncode == 0 and len(result.stdout) <= 512_000,
                  "controller coordinate OCR failed")
        rows = list(csv.DictReader(io.StringIO(result.stdout.decode("utf-8", "strict")),
                                   delimiter="\t"))
        c.require(1 <= len(rows) <= 20_000, "controller OCR row count differs")
        return rows

    def wallpaper_hide(self):
        path, _ = self.wait_screen("winter", "wallpaper-page",
                                   ("Wallpaper", "Butterfly", "Gold"), seconds=120, retain=True,
                                   exact_output=True)
        # Acquire coordinates from host OCR only. Guest diagnostics cannot
        # identify the target or influence the fixed geometric offset.
        try:
            rows = [row for row in self._tsv(path) if row.get("text")]
        finally:
            path.unlink(missing_ok=True)
        words = [row for row in rows if row.get("text", "").strip().casefold()
                 in ("butterfly", "in", "gold")]
        targets = []
        for first in words:
            if first["text"].strip().casefold() != "butterfly":
                continue
            line = [row for row in rows if row.get("block_num") == first.get("block_num")
                    and row.get("par_num") == first.get("par_num")
                    and row.get("line_num") == first.get("line_num")]
            sequence = " ".join(row["text"].strip() for row in line).casefold()
            if "butterfly in gold" in sequence:
                targets.append(first)
        c.require(len(targets) == 1, "wallpaper target OCR is absent or ambiguous")
        target = targets[0]
        left, top = int(target["left"]), int(target["top"])
        x, y = left + 133, top - 71
        c.require(300 <= x <= 1180 and 80 <= y <= 700,
                  "derived wallpaper control is outside reviewed window")
        self.pointer_click("winter", x, y)
        self.wait_screen("winter", "wallpaper-hide-dialog",
                         ("Hide", "Butterfly", "Gold", "packaged picture", "restore"),
                         seconds=60, exact_output=True)

    def boot_live_and_start(self):
        self.wait_screen("live-boot", "install-boot-menu", ("Arctic", "Install"), seconds=300)
        self.live_startup.boot_observed()
        self.press("live-boot", "home", "down", "ret")
        self.live_startup.selection_sent()
        # "Install Arctic Linux" is also present in the boot menu.  Requiring
        # that text here let the just-selected GRUB frame satisfy this gate and
        # moved to VT6 before the graphical installer had actually started.
        # Use copy unique to the real Welcome page so the following VT switch
        # cannot race live-session's one-shot installer launch.
        self.wait_screen("live-boot", "live-installer-visible",
                         ("Welcome to Arctic Linux", "Keyboard", "Time zone", "Summary"),
                         seconds=600, visible=True, exact_output=True)
        self.press("live-console", "ctrl-alt-f6")
        self.wait_screen("live-console", "live-console-login", ("login",), seconds=60)
        self.type_text("live-console", "live-username", "liveuser")
        self.press("live-console", "ret")
        time.sleep(2)
        self.press("live-console", "ret")
        self.type_text("live-install", "live-install", self.LIVE_COMMAND)
        self.press("live-install", "ret")
        self.record("live-install", "command", {"id": "live-install"})

    def start_live_failure_probe(self):
        """Run a fixed console probe only after the Welcome gate has failed."""
        c.require(self.live_startup.gate_status == "timed-out",
                  "live startup probe preceded authoritative gate failure")
        self.press("live-diagnostic", "ctrl-alt-f6")
        try:
            self.wait_screen("live-diagnostic", "live-diagnostic-login", ("login",), seconds=45)
        except c.Invalid:
            self.live_startup.probe("console-unavailable")
            return False
        self.type_text("live-diagnostic", "live-diagnostic-username", "liveuser")
        self.press("live-diagnostic", "ret")
        time.sleep(2)
        self.press("live-diagnostic", "ret")
        self.type_text("live-diagnostic", "live-startup-probe", self.LIVE_STARTUP_PROBE)
        self.press("live-diagnostic", "ret")
        self.live_startup.probe("command-sent")
        return True

    def accept_live_failure_probe(self, line):
        match = re.fullmatch(
            r"ARCTIC-SHOWCASE-LIVE-STARTUP-V1 (install|other) (running|absent) (running|absent)",
            line)
        c.require(match is not None, "live startup diagnostic response differs")
        self.live_startup.probe("completed", *match.groups())

    def accept_installed_shell_session(self, nonce, line):
        c.installed_shell_session_proof(nonce, line)
        self.installed_startup.session_proved(nonce)
        self.record("installed-console", "session", {
            "transport": "owned-root-virtio-serial",
            "challenge_sha256": hashlib.sha256(nonce.encode()).hexdigest(),
            "identity": "uid-1000-arcticshowcase-at-arctic-showcase-fish",
        })

    def verify_install_complete(self):
        self.wait_screen("install-complete", "installer-done",
                         ("Arctic Linux is ready", "Remove the USB stick"), seconds=5400,
                         exact_output=True)

    def boot_installed_and_start(self, session_exchange):
        c.require(callable(session_exchange), "installed shell session exchange differs")
        self.installed_startup.start()
        # A generic nonblank frame can be firmware or Plymouth. Retry the fixed
        # VT chord until OCR sees the installed system's real login prompt.
        deadline = time.monotonic() + 900
        while True:
            c.require(time.monotonic() < deadline, "installed console login timed out")
            self.press("installed-console", "ctrl-alt-f6")
            try:
                self.wait_screen("installed-boot", "installed-login-ready", ("login",), seconds=10)
                self.installed_startup.login_observed()
                break
            except c.Invalid:
                time.sleep(3)
        self.type_text("installed-console", "installed-username", c.CONTROLLER["account"]["username"])
        self.press("installed-console", "ret")
        self.installed_startup.authentication_sent()
        self.wait_screen("installed-console", "installed-password-prompt", ("Password",), seconds=45)
        self.type_secret("installed-console")
        self.press("installed-console", "ret")
        # Fish starts the packaged animated arctic-fetch before presenting its
        # prompt.  A command sent during that animation can be consumed as the
        # keypress that dismisses it.  First prove the exact installed greeting,
        # then send one Ctrl-L.  The exact candidate's renderer deliberately
        # leaves a single ordinary byte queued for Fish; Ctrl-L cannot submit a
        # command and makes Fish clear the retained greeting before redrawing
        # its prompt.  If the renderer has already returned, the same Fish
        # binding only clears and redraws.  A later bounded exact-frame gate,
        # rather than elapsed time, proves that its input loop and terminal
        # restoration have completed.
        self.wait_screen("installed-console", "installed-fetch-greeting",
                         ("Arctic Linux", "fish 4.6"), seconds=90)
        self.installed_startup.fetch_observed()
        self.press("installed-console", "ctrl-l")
        self.installed_startup.dismissal_sent()
        # The fetch renderer can remain visible after it has accepted the
        # dismissal key.  Do not type even the nonsecret proof command until a
        # later exact frame contains the fixed installed account's real Fish
        # prompt.  This makes readiness a pixel observation instead of a fixed
        # settling delay.
        shell_prompt = (c.CONTROLLER["account"]["username"] + "@"
                        + c.CONTROLLER["account"]["hostname"])
        prompt_contract = c.CONTROLLER["account"]["prompt"]
        installed_prompt = (shell_prompt, tuple(prompt_contract["ocr_suffixes"]))
        self.wait_screen("installed-console", "installed-prompt-ready",
                         (), seconds=90, exact_output=True,
                         prompt_contract=installed_prompt)
        self.type_text("installed-console", "installed-shell-proof", self.SHELL_PROOF)
        self.press("installed-console", "ret")
        nonce, response = session_exchange()
        self.accept_installed_shell_session(nonce, response)
        # Require the nonce-authenticated session's marker and suffix twice on
        # independent exact frames before entering the longer sudo launcher.
        try:
            self.wait_screen("installed-console", "installed-shell-ready",
                             ("ARCTIC-SHOWCASE-SHELL-READY",),
                             seconds=90, exact_output=True, ordered=True,
                             prompt_contract=installed_prompt, transport_prompt=True)
        except InstalledShellReadyTimeout as error:
            try:
                self.press("installed-diagnostic", "ctrl-c")
            except (c.Invalid, OSError):
                self.installed_startup.interrupt("controller-unavailable")
                raise error
            try:
                self.wait_screen("installed-diagnostic", "installed-diagnostic-shell-ready",
                                 (), seconds=30, exact_output=True,
                                 prompt_contract=installed_prompt,
                                 transport_prompt=True)
                self.installed_startup.interrupt("recovered-prompt")
            except (c.Invalid, OSError):
                self.installed_startup.interrupt("sent-no-prompt")
            raise error
        self.wait_screen("installed-console", "installed-shell",
                         ("ARCTIC-SHOWCASE-SHELL-READY",),
                         seconds=90, exact_output=True, ordered=True,
                         prompt_contract=installed_prompt, transport_prompt=True)
        self.type_text("installed-scenes", "installed-scenes", self.INSTALLED_COMMAND)
        self.press("installed-scenes", "ret")
        self.wait_screen("installed-console", "installed-sudo-password",
                         ("ARCTIC-SHOWCASE-AUTH-READY", "password"), seconds=45)
        self.type_secret("installed-console")
        self.press("installed-console", "ret")
        self.record("installed-scenes", "command", {"id": "installed-scenes"})

    def authorize_scene(self, scene: str):
        c.require(scene in c.SCENES, "controller scene differs")
        self.record(scene, "command", {"id": scene})
        if scene == "dictationsetup":
            self.wait_screen(scene, "dictation-ready-page",
                             ("Dictation is ready", "Local setup", "Recording", "Audio stays here"),
                             seconds=1800, exact_output=True)
        elif scene == "winter":
            self.wallpaper_hide()
        else:
            self.wait_screen(scene, "whats-new-layer",
                             ("What", "new", "Arctic Linux", "Local dictation"), seconds=120,
                             exact_output=True)

    def dismiss_first_login(self):
        """Dismiss the fresh account's top-layer welcome using host pixels/input."""
        self.wait_screen("installed-boot", "first-login-welcome",
                         ("Welcome", "Arctic Linux"), seconds=300, exact_output=True)
        self.press("installed-boot", "esc")
        self.wait_screen("installed-boot", "first-login-dismissed",
                         ("Dictation is ready", "Local setup", "Recording", "Audio stays here"),
                         seconds=120, exact_output=True)
        self.record("dictation-readiness", "command", {"id": "dictation-readiness"})

    def verify_scene(self, scene: str):
        """Recheck host pixels after untrusted guest diagnostics have completed."""
        c.require(scene in c.SCENES, "controller scene differs")
        if scene == "dictationsetup":
            expectation = "dictation-ready-page"
            phrases = ("Dictation is ready", "Local setup", "Recording", "Audio stays here")
        elif scene == "winter":
            expectation = "wallpaper-hide-dialog"
            phrases = ("Hide", "Butterfly", "Gold", "packaged picture", "restore")
        else:
            expectation = "whats-new-layer"
            phrases = ("What", "new", "Arctic Linux", "Local dictation")
        self.wait_screen(scene, expectation, phrases, seconds=120, exact_output=True)

    def qmp_event(self, stage, operation):
        c.require(operation in ("eject-exact-iso", "system-reset", "quit"),
                  "controller QMP operation differs")
        self.record(stage, "qmp", {"operation": operation})

    def trace(self):
        value = {"schema": "arctic-showcase-unattended-trace-v1",
                 "contract": dict(c.CONTROLLER), "tooling_sha256": self.tooling_sha256,
                 "events": self.events, "status": "completed",
                 "guest_diagnostics_used": False, "release_acceptance": False}
        c.controller_trace(value)
        return value
