#!/usr/bin/python3
"""Collect exact showcase scene facts from the installed Arctic desktop."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SCENES = ("dictationsetup", "winter", "updates")
WALLPAPER_SHA256 = "7c5d713468aff0be216a3f1c10c18492d495ce9d329fd7f18e674740f572e5fb"
WHATS_NEW_SHA256 = "ac4575f4505b2e82094e7bc1aa3f38b74ce3277db37e33b02c9f9366c5c74b12"
MAX_OUTPUT = 256_000


class Invalid(RuntimeError):
    pass


def require(condition, message):
    if not condition:
        raise Invalid(message)


def strict_pairs(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, "duplicate JSON key")
        value[key] = item
    return value


def strict_json(raw):
    try:
        return json.loads(raw, object_pairs_hook=strict_pairs)
    except (UnicodeError, json.JSONDecodeError, TypeError) as error:
        raise Invalid("invalid command JSON") from error


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


class System:
    def run(self, command, timeout=120):
        environment = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}
        environment.update({key: value for key, value in os.environ.items() if key in {
            "DBUS_SESSION_BUS_ADDRESS", "HOME", "USER", "WAYLAND_DISPLAY", "XDG_CONFIG_HOME",
            "XDG_DATA_HOME", "XDG_RUNTIME_DIR"}})
        try:
            result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, timeout=timeout, check=False,
                                    env=environment)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Invalid("scene command failed") from error
        require(result.returncode == 0 and len(result.stdout) <= MAX_OUTPUT, "scene command failed")
        return result.stdout

    def json(self, command, timeout=120):
        return strict_json(self.run(command, timeout))

    def read(self, path, maximum=MAX_OUTPUT):
        value = Path(path)
        try:
            data = value.read_bytes()
        except OSError as error:
            raise Invalid("scene file unavailable") from error
        require(0 < len(data) <= maximum and value.is_file() and not value.is_symlink(),
                "scene file differs")
        return data

    def glob(self, path, pattern):
        return list(Path(path).glob(pattern))


def output(system):
    rows = system.json(["/usr/bin/wlr-randr", "--json"])
    require(type(rows) is list, "output report differs")
    enabled = [row for row in rows if type(row) is dict and row.get("enabled") is True]
    require(len(enabled) == 1, "capture output count differs")
    row = enabled[0]
    modes = row.get("modes")
    current = row.get("current_mode")
    if current is None and type(modes) is list:
        matches = [mode for mode in modes if type(mode) is dict and mode.get("current") is True]
        require(len(matches) == 1, "capture output mode differs")
        current = matches[0]
    require(type(current) is dict, "capture output mode differs")
    scale = row.get("scale")
    require(type(scale) in (int, float) and float(scale) == 1.0,
            "capture output scale differs")
    value = {"name": row.get("name"), "width": current.get("width"),
             "height": current.get("height"), "scale": 1, "count": 1}
    require(type(value["name"]) is str and type(value["width"]) is int
            and type(value["height"]) is int and value["width"] == 1280
            and value["height"] == 800, "capture output geometry differs")
    return value


def surface(system, scene):
    if scene == "updates":
        value = system.json(["/usr/bin/mmsg", "get", "all-layers"])
        rows = value.get("layers") if type(value) is dict else None
        require(type(rows) is list, "layer report differs")
        matched = [row for row in rows if type(row) is dict
                   and row.get("name") == "arctic-whats-new"
                   and row.get("is_visible", row.get("mapped", True)) is True]
        require(len(matched) == 1, "What's New layer differs")
        return {"kind": "layer-namespace", "identity": "arctic-whats-new",
                "count": 1, "focused": True}
    value = system.json(["/usr/bin/mmsg", "get", "all-clients"])
    rows = value.get("clients") if type(value) is dict else None
    require(type(rows) is list, "client report differs")
    matched = [row for row in rows if type(row) is dict
               and row.get("title") == "Arctic Settings" and row.get("is_visible") is True]
    require(len(matched) == 1 and matched[0].get("is_focused") is True,
            "Settings surface differs")
    return {"kind": "client-title", "identity": "Arctic Settings",
            "count": 1, "focused": True}


def settings_helper(system):
    root = system.run(["/usr/bin/arctic-settings", "--path"]).decode("utf-8", "strict").strip()
    require(root.startswith("/") and not re.search(r"[\r\n\x00]", root), "Settings path differs")
    helper = Path(root) / "scripts/arctic_settings.py"
    require(helper.is_absolute(), "Settings helper differs")
    return str(helper)


def wallpaper_state(system, helper):
    value = system.json(["/usr/bin/python3", helper, "wallpapers"])
    require(type(value) is dict and type(value.get("items")) is list
            and type(value.get("hiddenArctic")) is list and type(value.get("current")) is str,
            "wallpaper state differs")
    return {"items": value["items"], "hiddenArctic": value["hiddenArctic"],
            "current": value["current"]}


def wallpaper(system):
    helper = settings_helper(system)
    before = wallpaper_state(system, helper)
    target = {"slug": "butterfly-in-gold", "name": "Butterfly in Gold"}
    rows = [item for item in before["items"] if type(item) is dict
            and item.get("slug") == target["slug"]]
    require(len(rows) == 1 and rows[0].get("name") == target["name"], "wallpaper target differs")
    path = Path(rows[0].get("path", ""))
    hashes = [digest(path)]
    system.json(["/usr/bin/python3", helper, "wallpaper-hide", target["slug"]])
    hidden = wallpaper_state(system, helper)
    hashes.append(digest(path))
    system.json(["/usr/bin/python3", helper, "wallpaper-restore", target["slug"]])
    restored = wallpaper_state(system, helper)
    hashes.append(digest(path))
    require(hashes == [WALLPAPER_SHA256] * 3, "wallpaper bytes differ")
    qml_candidates = (Path("/usr/share/arctic/settings/pages/AppearancePage.qml"),
                      Path("/usr/share/arctic-settings/pages/AppearancePage.qml"))
    qml = next((candidate for candidate in qml_candidates if candidate.is_file()), None)
    require(qml is not None, "installed wallpaper dialog source unavailable")
    text = system.read(qml).decode("utf-8", "strict")
    title, body = "Hide “Butterfly in Gold”?", "This packaged picture is hidden from the picker and automatic changes. You can restore it below."
    require('title: (item && item.arctic ? "Hide “" : "Delete “")' in text and body in text,
            "installed wallpaper dialog text differs")
    return {"target": target, "before": before, "hidden": hidden, "restored": restored,
            "file_hashes": hashes, "dialog": {"title": title, "body": body}}


def dictation(system):
    status = system.json(["/usr/bin/arctic-dictation", "status"])
    page = system.run(["/usr/bin/quickshell", "ipc", "call", "settings", "page"]) \
                 .decode("utf-8", "strict").strip()
    ready = system.run(["/usr/bin/quickshell", "ipc", "call", "settings", "ready"]) \
                  .decode("utf-8", "strict").strip()
    clients = system.json(["/usr/bin/mmsg", "get", "all-clients"])
    settings_clients = [row for row in clients.get("clients", []) if type(row) is dict
                        and row.get("title") == "Arctic Settings"
                        and row.get("is_visible") is True]
    require(page == "dictation" and ready == "true" and len(settings_clients) == 1,
            "Settings dictation page is not ready")
    runtime_root = Path(os.environ.get("XDG_RUNTIME_DIR", ""))
    require(runtime_root.is_absolute(), "runtime directory unavailable")
    runtime = strict_json(system.read(runtime_root / "arctic/dictation.json", 16_384))
    private = runtime_root / "arctic/dictation"
    transcripts = []
    if private.is_dir():
        transcripts = [path for pattern in ("transcript*", ".transcript*")
                       for path in system.glob(private, pattern)]
    return {"phase": "online-installed", "status": status, "settings_ready": True,
            "settings_page": page, "settings_clients": len(settings_clients),
            "recording": runtime.get("state") == "recording",
            "transcribing": runtime.get("state") == "transcribing",
            "receiver_empty": len(transcripts) == 0, "transcript_files": len(transcripts)}


def updates(system):
    notes_candidates = (Path("/usr/share/arctic/shell/whats-new.json"),
                        Path("/usr/share/arctic-shell/whats-new.json"))
    notes = next((candidate for candidate in notes_candidates if candidate.is_file()), None)
    require(notes is not None and digest(notes) == WHATS_NEW_SHA256, "installed What's New notes differ")
    system.run(["/usr/bin/arctic-shell-ipc", "whatsnew", "open"])
    return {"installed": True, "live": False, "notes_source_sha256": WHATS_NEW_SHA256,
            "notes_installed_sha256": WHATS_NEW_SHA256,
            "ipc": "arctic-shell-ipc whatsnew open", "surface": "arctic-whats-new"}


def collect(scene, system):
    require(scene in SCENES, "unknown scene")
    facts = {"dictationsetup": dictation, "winter": wallpaper, "updates": updates}[scene](system)
    return {"facts": facts, "output": output(system), "surface": surface(system, scene)}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    try:
        require(len(argv) == 1 and argv[0] in SCENES,
                "usage: arctic-showcase-capture-probe SCENE")
        print(json.dumps(collect(argv[0], System()), sort_keys=True, separators=(",", ":")))
        return 0
    except (Invalid, OSError, UnicodeError) as error:
        print("showcase probe failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
