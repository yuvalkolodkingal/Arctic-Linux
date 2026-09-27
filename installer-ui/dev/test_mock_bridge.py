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
        self.assertEqual([c["id"] for c in apps["options"]["categories"]],
                         ["browser", "editor", "terminal", "shell", "files", "office", "video", "extras"])
        est = b.ok("EstimateDownload", {"selection": apps["data"]["selection"]})
        self.assertRegex(est["label"], r"^\d+ apps? · [\d.]+ (GB|MB) download$")

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
        sel["extras"] = ["steam"]
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
