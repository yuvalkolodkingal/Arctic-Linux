#!/usr/bin/env python3
"""Protocol tests for dev/mock-bridge.py (docs/BUILD-SPEC.md §4).

Runs the mock as a subprocess and talks newline-delimited JSON to it, the way
the Quickshell UI does. No GUI needed:  python3 -m unittest dev/test_mock_bridge.py
The same checks can be pointed at the Go engine:
    ARCTIC_TEST_BRIDGE="arctic-install bridge --mock" python3 dev/test_mock_bridge.py
"""
import json
import os
import queue
import re
import shlex
import subprocess
import sys
import shutil
import threading
import time
import tomllib
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, "..", ".."))
MODULES_DIR = os.path.join(ROOT, "modules")


def catalog_app_ids():
    """Every app the picker lists, straight from modules/catalog.toml (not the drivers:
    a hardware category offers only what was detected)."""
    with open(os.path.join(MODULES_DIR, "catalog.toml"), "rb") as f:
        cat = tomllib.load(f)
    return [mid for c in cat["category"] if not c.get("hardware") for mid in c["modules"]]


_ENGINE = []


def engine_catalog():
    """`arctic-install catalog --json` (the engine's own catalog, defaults and estimate), or
    None without a Go toolchain."""
    if not _ENGINE:
        doc = None
        if shutil.which("go"):
            r = subprocess.run(["go", "run", "./cmd/arctic-install", "catalog", "--json", "--catalog", MODULES_DIR],
                               cwd=ROOT, capture_output=True, text=True, timeout=300)
            if r.returncode == 0:
                doc = json.loads(r.stdout)
            else:
                print("arctic-install catalog failed:", r.stderr, file=sys.stderr)
        _ENGINE.append(doc)
    return _ENGINE[0]


class Bridge:
    def __init__(self, **env):
        cmd = os.environ.get("ARCTIC_TEST_BRIDGE")
        argv = shlex.split(cmd) if cmd else [sys.executable, os.path.join(HERE, "mock-bridge.py")]
        e = dict(os.environ, ARCTIC_MOCK_SPEED="20", **env)
        self.p = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, env=e)
        self.q = queue.Queue()
        self.events = []
        self.next_id = 1
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        for line in self.p.stdout:
            msg = json.loads(line)
            if "event" in msg:
                self.events.append(msg)
            else:
                self.q.put(msg)

    def call(self, method, params=None, timeout=10):
        rid = self.next_id
        self.next_id += 1
        req = {"id": rid, "method": method}
        if params is not None:
            req["params"] = params
        self.p.stdin.write(json.dumps(req) + "\n")
        self.p.stdin.flush()
        msg = self.q.get(timeout=timeout)
        assert msg["id"] == rid, msg
        return msg

    def ok(self, method, params=None):
        msg = self.call(method, params)
        assert "result" in msg, msg
        return msg["result"]

    def wait_event(self, kind, timeout=30, pred=lambda e: True):
        end = time.time() + timeout
        seen = 0
        while time.time() < end:
            for e in self.events[seen:]:
                if e["event"] == kind and pred(e):
                    return e
            time.sleep(0.05)
        raise AssertionError(f"no {kind} event; got {[e['event'] for e in self.events[-5:]]}")

    def close(self):
        self.p.stdin.close()
        self.p.wait(timeout=5)
        self.p.stdout.close()


class MockBridgeTest(unittest.TestCase):
    def setUp(self):
        self.b = None

    def tearDown(self):
        if self.b:
            self.b.close()

    def start(self, **env):
        self.b = Bridge(**env)
        hello = self.b.ok("Hello", {"client": "installer-ui", "version": "test"})
        self.assertIn(hello["firmware"], ("uefi", "bios"))
        self.assertEqual(self.b.ok("Subscribe"), {"ok": True})
        return self.b

    def walk_to(self, target):
        b = self.b
        while b.ok("GetWizard")["current"] != target:
            cur = b.ok("GetWizard")["current"]
            if cur == "network":
                b.ok("ConnectWifi", {"ssid": "Tundra-5G", "password": "polarnight"})
            elif cur == "encryption":
                b.ok("SetSecrets", {"luks_passphrase": "correct horse battery staple"})
            elif cur == "account":
                b.ok("SetStep", {"id": "account", "data": {"full_name": "Noa Levi", "username": "noa", "hostname": "noa-thinkpad"}})
                b.ok("SetSecrets", {"user_password": "snowy-owl-42"})
            b.ok("Next")

    def test_wizard_steps_and_defaults(self):
        b = self.start()
        w = b.ok("GetWizard")
        ids = [s["id"] for s in w["steps"]]
        self.assertEqual(ids, ["welcome", "keyboard", "network", "timezone", "disk", "encryption", "account", "apps", "summary", "install", "done"])
        self.assertEqual(w["current"], "welcome")
        disk = b.ok("GetStep", {"id": "disk"})
        self.assertFalse(any(d["install_media"] for d in disk["options"]["disks"]))
        self.assertEqual(disk["data"]["mode"], "erase")
        apps = b.ok("GetStep", {"id": "apps"})
        cats = apps["options"]["categories"]
        # The mock is an NVIDIA hybrid laptop: its drivers lead, marked as hardware.
        self.assertEqual([c["id"] for c in cats],
                         ["drivers", "browser", "editor", "terminal", "shell", "files", "office", "video",
                          "music", "photos", "graphics", "recording", "chat", "email", "notes", "reading",
                          "gaming", "security", "sync", "dev", "containers", "extras"])
        self.assertEqual([c["id"] for c in cats if c.get("hardware")], ["drivers"])
        # Drivers and the design's seven sections are open; the optional groups start collapsed.
        self.assertEqual([c["id"] for c in cats if not c["collapsed"]],
                         ["drivers", "browser", "editor", "terminal", "shell", "files", "office", "video"])
        mods = {m["id"]: m for m in apps["options"]["modules"]}
        drivers = [m for m in apps["options"]["modules"] if m["category"] == "drivers"]
        self.assertEqual([m["id"] for m in drivers], ["nvidia", "intel-media"])
        nvidia = drivers[0]
        self.assertEqual((nvidia["id"], nvidia["tile"], nvidia["device"], nvidia["default"], nvidia["source"]),
                         ("nvidia", "driver-gpu", "NVIDIA GeForce RTX 4060 Max-Q / Mobile", True, "RPM Fusion"))
        self.assertIn("your NVIDIA GeForce RTX 4060 Max-Q / Mobile", nvidia["summary"])
        app_ids = sorted(i for i, m in mods.items() if m["category"] != "drivers")
        self.assertEqual(app_ids, sorted(catalog_app_ids()))
        self.assertEqual((mods["steam"]["category"], mods["steam"]["source"], mods["steam"]["proprietary"]),
                         ("gaming", "RPM Fusion", True))
        self.assertEqual(mods["zen"]["source"], "Flathub")
        self.assertFalse(mods["zen"]["proprietary"])
        sel = apps["data"]["selection"]
        self.assertEqual(sel["drivers"], ["nvidia", "intel-media"])
        est = b.ok("EstimateDownload", {"selection": sel})
        self.assertEqual(est["apps"], sum(1 for i in app_ids if mods[i]["default"]))
        self.assertEqual(est["drivers"], 2)
        self.assertRegex(est["label"], r"^\d+ apps \+ 2 drivers · [\d.]+ [MG]B download$")
        # Without the drivers, the same numbers as the engine's catalog.EstimateDownload (which
        # detects nothing here), when Go is here.
        est_apps = b.ok("EstimateDownload", {"selection": {k: v for k, v in sel.items() if k != "drivers"}})
        self.assertRegex(est_apps["label"], r"^\d+ apps · [\d.]+ [MG]B download$")
        self.assertNotIn("drivers", est_apps)
        eng = engine_catalog()
        if eng is None:
            print("SKIPPED: engine estimate comparison (no Go toolchain)", file=sys.stderr)
        else:
            self.assertEqual(est_apps, eng["estimate"])
            self.assertEqual(app_ids, sorted(m["id"] for m in eng["modules"]
                                             if not m.get("hidden") and m["category"] != "drivers"))

    def test_no_drivers_detected(self):
        b = self.start(ARCTIC_MOCK_HW="none")
        apps = b.ok("GetStep", {"id": "apps"})
        cats = [c["id"] for c in apps["options"]["categories"]]
        self.assertEqual(cats[0], "browser")
        self.assertNotIn("drivers", cats)
        self.assertFalse(any(m["category"] == "drivers" for m in apps["options"]["modules"]))
        est = b.ok("EstimateDownload", {"selection": apps["data"]["selection"]})
        self.assertRegex(est["label"], r"^\d+ apps · [\d.]+ [MG]B download$")

    def test_network_blocks_next_until_online(self):
        b = self.start()
        b.ok("Next"), b.ok("Next")
        self.assertEqual(b.ok("GetWizard")["current"], "network")
        err = b.call("Next")["error"]
        self.assertEqual(err["code"], "offline")
        bad = b.call("ConnectWifi", {"ssid": "Tundra-5G", "password": "nope"})["error"]
        self.assertEqual(bad["code"], "auth")
        b.ok("ConnectWifi", {"ssid": "Tundra-5G", "password": "polarnight"})
        self.assertTrue(b.ok("NetworkState")["online"])
        self.assertEqual(b.ok("Next")["current"], "timezone")

    def test_wired_skips_network(self):
        b = self.start(ARCTIC_MOCK_WIRED="1")
        b.ok("Next")
        self.assertEqual(b.ok("Next")["current"], "timezone")
        self.assertEqual(b.ok("Back")["current"], "keyboard")

    def test_explicit_offline_choice_survives_back_without_fake_connectivity(self):
        b = self.start()
        b.ok("Next"), b.ok("Next")
        b.ok("SetStep", {"id": "network", "data": {"offline": True}})
        self.assertEqual(b.ok("Next")["current"], "timezone")
        self.assertFalse(b.ok("NetworkState")["online"])
        self.assertEqual(b.ok("Back")["current"], "network")
        self.assertTrue(b.ok("GetStep", {"id": "network"})["data"]["offline"])
        b.ok("SetStep", {"id": "network", "data": {"offline": False}})
        self.assertEqual(b.call("Next")["error"]["code"], "offline")

    def test_offline_choice_rejects_nonboolean_inputs(self):
        b = self.start()
        b.ok("SetStep", {"id": "network", "data": {"offline": True}})
        for value in (None, "true", 1, {}, []):
            self.assertEqual(b.call("SetStep", {"id": "network", "data": {"offline": value}})["error"]["code"], "bad_request")
            self.assertTrue(b.ok("GetStep", {"id": "network"})["data"]["offline"])
        for data in ({"Offline": None}, {"OFFLINE": None}, {"Offline": False}, {"offline": True, "OFFLINE": False}, {"online": True}):
            self.assertEqual(b.call("SetStep", {"id": "network", "data": data})["error"]["code"], "bad_request")
            self.assertTrue(b.ok("GetStep", {"id": "network"})["data"]["offline"])

    def test_validation_errors_have_fields(self):
        b = self.start()
        err = b.call("SetStep", {"id": "account", "data": {"full_name": "Noa", "username": "Noa!", "hostname": "x"}})["error"]
        self.assertEqual(err["code"], "invalid")
        self.assertEqual(err["fields"]["username"], "Use lowercase letters, numbers, - and _.")
        weak = b.ok("CheckPassphrase", {"text": "abc"})
        self.assertEqual((weak["score"], weak["label"], weak["ok"]), (0, "Too short", False))
        strong = b.ok("CheckPassphrase", {"text": "correct horse battery staple"})
        self.assertTrue(strong["ok"])
        self.assertEqual(strong["words"], 4)
        self.assertEqual(len(b.ok("SuggestPassphrase")["text"].split()), 4)
        self.assertEqual(b.ok("SuggestAccount", {"full_name": "Noa Levi"}), {"username": "noa", "hostname": "noa-thinkpad"})

    def test_install_with_optional_failure_and_retry(self):
        b = self.start()
        self.walk_to("apps")
        sel = b.ok("GetStep", {"id": "apps"})["data"]["selection"]
        sel["gaming"] = ["steam"]
        b.ok("SetStep", {"id": "apps", "data": {"selection": sel}})
        b.ok("Next")
        summary = b.ok("GetSummary")
        self.assertEqual(summary["rows"][-1]["label"], "Drivers")
        self.assertIn("NVIDIA driver for your NVIDIA GeForce RTX 4060", summary["rows"][-1]["value"])
        self.assertEqual(summary["primary_label"], "Erase disk and install")
        self.assertIn("erase everything on Samsung SSD 980", summary["warning"])
        self.assertEqual(b.ok("Next")["current"], "install")
        b.ok("Start")
        att = b.wait_event("attention")
        self.assertEqual(att["module"]["id"], "steam")
        self.assertTrue(att["optional"])
        prog = [e for e in b.events if e["event"] == "progress"]
        self.assertTrue(all(len(e["substeps"]) == 4 for e in prog))
        b.ok("RetryModule", {"id": "steam"})
        done = b.wait_event("done", timeout=60)
        self.assertEqual(done["first_name"], "Noa")
        self.assertEqual(done["apps_installed"], len([m for k, c in sel.items() if k != "drivers" for m in c]))
        self.assertEqual([d["id"] for d in done["drivers"]], ["nvidia", "intel-media"])
        self.assertRegex(done["secure_boot"]["code"], r"^\d{8}$")
        self.assertIn(done["secure_boot"]["code"], done["secure_boot"]["steps"][2])
        done_step = b.ok("GetStep", {"id": "done"})
        self.assertEqual(done_step["options"]["secure_boot"], done["secure_boot"])
        self.assertEqual(b.ok("GetWizard")["current"], "done")

    def test_offline_secure_boot_shows_the_later_key_steps(self):
        # As the engine: offline, an akmod driver is put off to first boot and the code's hash
        # is kept for arctic-firstboot, so the Done step shows SecureBootSteps(code, later).
        b = self.start(ARCTIC_MOCK_WIRED="1", ARCTIC_MOCK_DROP="1", ARCTIC_MOCK_FAIL="none")
        self.walk_to("summary")
        b.ok("Next")
        b.ok("Start")
        done = b.wait_event("done", timeout=60)
        self.assertEqual({d["status"] for d in done["drivers"]}, {"deferred"})
        sb = done["secure_boot"]
        self.assertEqual(sb["title"], "One more step once your driver is installed")
        self.assertTrue(sb["steps"][0].startswith("Restart once the driver is installed."))
        self.assertIn(sb["code"], sb["steps"][2])

    def test_core_failure_then_skip(self):
        b = self.start(ARCTIC_MOCK_FATAL="1", ARCTIC_MOCK_WIRED="1")
        self.walk_to("summary")
        b.ok("Next")
        b.ok("Start")
        failed = b.wait_event("failed")
        self.assertTrue(failed["fatal"])
        self.assertTrue(b.ok("SaveLog")["path"])
        b.ok("Start")
        att = b.wait_event("attention", timeout=60)
        b.ok("SkipModule", {"id": att["module"]["id"]})
        b.wait_event("module", pred=lambda e: e["status"] == "skipped")
        b.wait_event("done", timeout=60)

    def test_core_failure_then_change_answers(self):
        # After a core failure, Back returns to the Summary with every answer and secret
        # kept (the UI's "Change your answers"); another disk can then be picked.
        b = self.start(ARCTIC_MOCK_FATAL="1", ARCTIC_MOCK_WIRED="1")
        self.walk_to("summary")
        b.ok("Next")
        b.ok("Start")
        failed = b.wait_event("failed")
        self.assertTrue(failed.get("details"))
        self.assertTrue(failed.get("can_change"))
        self.assertEqual(b.call("SetStep", {"id": "disk", "data": {"disk": "/dev/sda"}})["error"]["code"], "state")
        self.assertEqual(b.ok("Back")["current"], "summary")
        self.assertEqual(b.ok("Goto", {"id": "disk"})["current"], "disk")
        disk = b.ok("GetStep", {"id": "disk"})
        other = next(d for d in disk["options"]["disks"]
                     if d["path"] != disk["data"]["disk"] and not d.get("too_small") and d["size_bytes"] >= 40 * 1000 ** 3)
        b.ok("SetStep", {"id": "disk", "data": {"disk": other["path"], "mode": "erase"}})
        self.assertTrue(b.ok("GetStep", {"id": "encryption"})["options"]["passphrase_set"])
        self.assertTrue(b.ok("GetStep", {"id": "account"})["options"]["password_set"])
        self.assertEqual(b.ok("Next")["current"], "summary")    # Change → Next returns to Summary
        self.assertIn(other["model"] or other["path"], b.ok("GetSummary")["warning"])
        self.assertEqual(b.ok("Next")["current"], "install")
        b.ok("Start")
        att = b.wait_event("attention", timeout=60)
        b.ok("SkipModule", {"id": att["module"]["id"]})
        b.wait_event("done", timeout=60)

    def test_weak_secrets_only_warn(self):
        # As the engine: a short or weak disk passphrase or password passes every step and
        # the Summary, which notes it in the Disk and Account rows; an empty one is still refused.
        b = self.start(ARCTIC_MOCK_WIRED="1")
        self.walk_to("account")
        b.ok("SetStep", {"id": "account", "data": {"full_name": "Noa Levi", "username": "noa", "hostname": "noa-thinkpad"}})
        b.ok("SetSecrets", {"user_password": ""})
        self.assertIn("password", b.call("Next")["error"]["fields"])
        b.ok("SetSecrets", {"user_password": "x", "luks_passphrase": "abc"})
        self.assertFalse(b.ok("CheckPassphrase", {"text": "abc"})["ok"])
        opts = b.ok("GetStep", {"id": "account"})["options"]
        self.assertEqual((opts["min_score"], opts["strength"]["label"]), (1, "Too short"))
        self.assertTrue(opts["weak_warning"].startswith("This password is easy to guess"))
        self.assertEqual(b.ok("Next")["current"], "apps")
        self.assertEqual(b.ok("Next")["current"], "summary")
        summary = b.ok("GetSummary")
        rows = {r["label"]: r["value"] for r in summary["rows"]}
        self.assertTrue(rows["Disk"].endswith(", encrypted, easy-to-guess passphrase"))
        self.assertEqual(rows["Account"], "Noa Levi (noa) on noa-thinkpad, easy-to-guess password")
        self.assertTrue(summary["warning"].endswith("This can't be undone."))
        self.assertEqual(b.ok("Next")["current"], "install")
        b.ok("Start")

    def test_back_from_install_before_start(self):
        # Summary's Next moves to the install step; until Start, Back returns to Summary
        # (the UI does that when Start is refused, or when it reconnects there).
        b = self.start(ARCTIC_MOCK_WIRED="1")
        self.walk_to("summary")
        self.assertEqual(b.ok("Next")["current"], "install")
        self.assertEqual(b.ok("Hello", {"client": "installer-ui", "version": "test"})["state"], "wizard")
        self.assertEqual(b.ok("Back")["current"], "summary")
        self.assertEqual(b.ok("Next")["current"], "install")
        b.ok("Start")
        self.assertEqual(b.call("Back")["error"]["code"], "state")
        att = b.wait_event("attention", timeout=60)
        b.ok("SkipModule", {"id": att["module"]["id"]})
        b.wait_event("done", timeout=60)

    def test_optional_pick_one_category_can_be_empty(self):
        b = self.start()
        apps = b.ok("GetStep", {"id": "apps"})
        cats = {c["id"]: c for c in apps["options"]["categories"]}
        self.assertEqual([k for k, c in cats.items() if c["required"]], ["browser", "terminal", "shell"])
        self.assertEqual(cats["office"]["choice"], "one")
        sel = apps["data"]["selection"]
        # The lightweight catalog starts with no office app. Select one first
        # so removal still proves that an optional one-choice category may empty.
        sel["office"] = [next(m["id"] for m in apps["options"]["modules"] if m["category"] == "office")]
        b.ok("SetStep", {"id": "apps", "data": {"selection": sel}})
        before = b.ok("EstimateDownload", {"selection": sel})
        sel["office"] = []
        b.ok("SetStep", {"id": "apps", "data": {"selection": sel}})
        after = b.ok("EstimateDownload", {"selection": sel})
        self.assertEqual(after["apps"], before["apps"] - 1)
        for cid in ("browser", "terminal"):
            bad = dict(sel, **{cid: []})
            err = b.call("SetStep", {"id": "apps", "data": {"selection": bad}})["error"]
            self.assertIn(cid, err["fields"])

    def test_requires_and_conflicts_like_the_engine(self):
        # catalog.Validate's messages, keyed by the app's group.
        b = self.start()
        sel = b.ok("GetStep", {"id": "apps"})["data"]["selection"]
        for cid, ids, msg in (("containers", ["podman-desktop"], "Podman Desktop needs Podman. Tick it too."),
                              ("dev", ["lazygit"], "lazygit needs Git. Tick it too.")):
            err = b.call("SetStep", {"id": "apps", "data": {"selection": dict(sel, **{cid: ids})}})["error"]
            self.assertEqual(err["code"], "invalid")
            self.assertEqual(err["fields"], {cid: msg})
        ok = dict(sel, containers=["podman", "podman-desktop"], dev=["git", "lazygit"])
        b.ok("SetStep", {"id": "apps", "data": {"selection": ok}})

    def test_disk_options_have_labels(self):
        # The UI shows the engine's label (the path when there is no model, e.g. virtio)
        # and alongside wording.
        b = self.start()
        disks = b.ok("GetStep", {"id": "disk"})["options"]["disks"]
        for d in disks:
            self.assertEqual(d["label"], f"{d['model'].strip() or d['path']} · {d['size_label']}")
            if d["alongside_possible"]:
                self.assertTrue(d["alongside_title"].startswith("Install alongside "), d)
                self.assertTrue(d["alongside_description"], d)
        self.assertTrue(any(d["alongside_possible"] for d in disks))

    def test_change_language_from_summary_shows_keyboard(self):
        b = self.start(ARCTIC_MOCK_WIRED="1")
        self.walk_to("summary")
        self.assertEqual(b.ok("Goto", {"id": "timezone"})["current"], "timezone")
        self.assertEqual(b.ok("Next")["current"], "summary")
        self.assertEqual(b.ok("Goto", {"id": "welcome"})["current"], "welcome")
        b.ok("SetStep", {"id": "welcome", "data": {"language": "de_DE.UTF-8"}})
        self.assertEqual(b.ok("Next")["current"], "keyboard")   # a new language: check the layout
        self.assertEqual(b.ok("Next")["current"], "summary")

    def test_keyboard_follows_language_until_picked(self):
        b = self.start()
        b.ok("SetStep", {"id": "welcome", "data": {"language": "he_IL.UTF-8"}})
        self.assertEqual(b.ok("GetStep", {"id": "keyboard"})["data"]["layout"], "il")
        b.ok("SetStep", {"id": "keyboard", "data": {"layout": "us", "variant": "intl"}})
        b.ok("SetStep", {"id": "keyboard", "data": {"layout": "de"}})
        kb = b.ok("GetStep", {"id": "keyboard"})["data"]
        self.assertEqual((kb["layout"], kb["variant"]), ("de", ""))
        b.ok("SetStep", {"id": "welcome", "data": {"language": "fr_FR.UTF-8"}})
        self.assertEqual(b.ok("GetStep", {"id": "keyboard"})["data"]["layout"], "de")

    def test_keyboard_xkb_for_the_live_session(self):
        # The engine says what the layout becomes (the UI applies it to the live session):
        # non-Latin layouts get "us" first and a switch.
        b = self.start()
        kb = b.ok("SetStep", {"id": "keyboard", "data": {"layout": "il", "variant": ""}})["data"]
        self.assertEqual((kb["xkb"]["layout"], kb["xkb"]["options"], kb["xkb"]["latin"]), ("us,il", "grp:alt_shift_toggle", False))
        kb = b.ok("SetStep", {"id": "keyboard", "data": {"layout": "de", "variant": "nodeadkeys"}})["data"]
        self.assertEqual((kb["xkb"]["layout"], kb["xkb"]["variant"], kb["xkb"]["latin"]), ("de", "nodeadkeys", True))
        self.assertEqual(b.ok("GetStep", {"id": "keyboard"})["data"]["xkb"]["layout"], "de")

    def test_progress_counts_apps_in_the_substep(self):
        b = self.start(ARCTIC_MOCK_WIRED="1")
        self.walk_to("summary")
        b.ok("Next")
        b.ok("Start")
        att = b.wait_event("attention", timeout=60)
        self.assertTrue(att.get("details"))
        labels = [e["substeps"][2]["label"] for e in b.events if e["event"] == "progress" and e["substeps"][2]["state"] == "active"]
        self.assertTrue(labels)
        self.assertTrue(all(re.fullmatch(r"Installing your apps · \d+ of \d+", lbl) for lbl in labels), labels[:3])
        b.ok("SkipModule", {"id": att["module"]["id"]})
        b.wait_event("done", timeout=60)


if __name__ == "__main__":
    unittest.main(verbosity=2)
