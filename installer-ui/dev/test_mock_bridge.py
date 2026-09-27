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
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


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
        self.assertEqual([c["id"] for c in cats],
                         ["browser", "editor", "terminal", "shell", "files", "office", "video",
                          "music", "photos", "graphics", "recording", "chat", "email", "notes", "reading",
                          "gaming", "security", "sync", "dev", "containers", "utilities"])
        # The design's seven sections are open; the optional groups start collapsed.
        self.assertEqual([c["id"] for c in cats if not c["collapsed"]],
                         ["browser", "editor", "terminal", "shell", "files", "office", "video"])
        mods = {m["id"]: m for m in apps["options"]["modules"]}
        self.assertEqual(len(mods), 126)
        self.assertEqual((mods["steam"]["category"], mods["steam"]["source"], mods["steam"]["proprietary"]),
                         ("gaming", "RPM Fusion", True))
        self.assertEqual(mods["zen"]["source"], "Flathub")
        self.assertFalse(mods["zen"]["proprietary"])
        est = b.ok("EstimateDownload", {"selection": apps["data"]["selection"]})
        # The same numbers as the engine's catalog.EstimateDownload.
        self.assertEqual(est["label"], "8 apps · 2.1 GB download")
        self.assertEqual(est["bytes"], 2138 * 1000 * 1000)

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
        self.assertEqual(done["apps_installed"], len([m for c in sel.values() for m in c]))
        self.assertEqual(b.ok("GetWizard")["current"], "done")

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

    def test_summary_next_checks_the_disk_passphrase(self):
        # "Use this password for the disk passphrase too" with a weak password: the engine
        # refuses at Summary with the passphrase field (the UI points to Encryption).
        b = self.start(ARCTIC_MOCK_WIRED="1")
        self.walk_to("account")
        b.ok("SetStep", {"id": "account", "data": {"full_name": "Noa Levi", "username": "noa", "hostname": "noa-thinkpad"}})
        b.ok("SetSecrets", {"user_password": "iloveyou", "luks_passphrase": "iloveyou"})
        self.assertFalse(b.ok("CheckPassphrase", {"text": "iloveyou"})["ok"])
        b.ok("Next")
        b.ok("Next")
        self.assertEqual(b.ok("GetWizard")["current"], "summary")
        err = b.call("Next")["error"]
        self.assertEqual(err["code"], "invalid")
        self.assertIn("passphrase", err["fields"])

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
        before = b.ok("EstimateDownload", {"selection": sel})
        sel["office"] = []
        b.ok("SetStep", {"id": "apps", "data": {"selection": sel}})
        after = b.ok("EstimateDownload", {"selection": sel})
        self.assertEqual(after["apps"], before["apps"] - 1)
        for cid in ("browser", "terminal"):
            bad = dict(sel, **{cid: []})
            err = b.call("SetStep", {"id": "apps", "data": {"selection": bad}})["error"]
            self.assertIn(cid, err["fields"])

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
