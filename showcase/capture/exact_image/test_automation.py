import copy
import tempfile
import unittest
import json
import os
import shlex
import subprocess
import types
from pathlib import Path
from unittest import mock

from PIL import Image

import sys
HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import automation
import capture_vm
import contract as c
import unattended
from test_capture import controller_trace


class QMP:
    def __init__(self):
        self.commands = []

    def command(self, name, arguments=None):
        self.commands.append((name, arguments))
        return {}

    def screendump(self, path):
        Image.new("RGB", (1280, 800), "#233041").save(path)


class UnattendedController(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.qmp = QMP()
        self.controller = automation.Controller(self.qmp, self.root, lambda path: "clean",
                                                (), "f" * 64)

    def tearDown(self):
        self.temp.cleanup()

    def test_text_and_secret_use_only_qmp_and_secret_receipt_has_no_value_or_hash(self):
        self.controller.type_text("live-console", "live-username", "Ab-1", gap=0)
        self.controller.type_secret("installed-console")
        self.assertTrue(all(name == "input-send-event" for name, _ in self.qmp.commands))
        self.assertEqual(self.controller.events[0]["detail"]["sha256"],
                         __import__("hashlib").sha256(b"Ab-1").hexdigest())
        secret = self.controller.events[1]["detail"]
        self.assertEqual(secret, {"source": "reviewed-disposable-controller-constant",
                                  "characters": 38})
        self.assertNotIn(automation.Controller.PASSWORD, repr(self.controller.events))

    def test_screen_gate_records_host_qmp_pixels_and_deletes_probe(self):
        self.controller.ocr = lambda path: "Arctic Linux is ready Remove the USB stick"
        path, _ = self.controller.wait_screen("install-complete", "installer-done",
                                              ("Arctic Linux is ready", "Remove the USB stick"),
                                              seconds=1)
        self.assertIsNone(path)
        self.assertEqual(list(self.root.glob("controller-*.png")), [])
        event = self.controller.events[0]
        self.assertEqual(event["kind"], "screen")
        self.assertEqual(event["detail"]["expectation"], "installer-done")

    def test_screen_gate_fails_closed_on_missing_phrase_or_private_text(self):
        self.controller.ocr = lambda path: "wrong screen"
        with mock.patch.object(automation.time, "sleep"):
            with self.assertRaises(c.Invalid):
                self.controller.wait_screen("updates", "whats-new-layer", ("Local dictation",),
                                            seconds=0)
        self.controller.ocr = lambda path: "/home/private-user/secret"
        with self.assertRaises(c.Invalid):
            self.controller._shot("private")

    def test_wallpaper_click_is_host_ocr_derived_and_dialog_is_rechecked(self):
        image = self.root / "wallpaper.png"
        Image.new("RGB", (1280, 800), "#233041").save(image)
        screens = [(image, "Wallpaper Butterfly in Gold"), (None, "Hide dialog")]
        self.controller.wait_screen = mock.Mock(side_effect=screens)
        self.controller._tsv = mock.Mock(return_value=[
            {"text": "Butterfly", "block_num": "1", "par_num": "1", "line_num": "1",
             "left": "400", "top": "300"},
            {"text": "in", "block_num": "1", "par_num": "1", "line_num": "1",
             "left": "450", "top": "300"},
            {"text": "Gold", "block_num": "1", "par_num": "1", "line_num": "1",
             "left": "470", "top": "300"},
        ])
        self.controller.wallpaper_hide()
        pointer = [event for event in self.controller.events if event["kind"] == "pointer"]
        self.assertEqual(pointer[0]["detail"], {"x": 533, "y": 229, "button": "left",
                                                "target": "wallpaper-hide-button"})
        self.assertEqual(self.controller.wait_screen.call_args_list[1].args[1],
                         "wallpaper-hide-dialog")

    def test_scene_authorization_is_fixed_and_receives_no_guest_diagnostics(self):
        self.controller.wait_screen = mock.Mock(return_value=(None, ""))
        for scene in ("dictationsetup", "updates"):
            self.controller.authorize_scene(scene)
            self.controller.verify_scene(scene)
        commands = [event["detail"]["id"] for event in self.controller.events
                    if event["kind"] == "command"]
        self.assertEqual(commands, ["dictationsetup", "updates"])
        with self.assertRaises(c.Invalid):
            self.controller.authorize_scene("guest-selected")
        with self.assertRaises(c.Invalid):
            self.controller.verify_scene("guest-selected")

    def test_first_login_is_host_observed_dismissed_and_rechecked(self):
        self.controller.wait_screen = mock.Mock(return_value=(None, ""))
        self.controller.dismiss_first_login()
        self.assertEqual(self.controller.wait_screen.call_args_list[0].args[1],
                         "first-login-welcome")
        self.assertEqual(self.controller.events[0], {
            "index": 0, "stage": "installed-boot", "kind": "keys",
            "detail": {"names": ["esc"]},
        })
        self.assertEqual(self.controller.wait_screen.call_args_list[1].args[1],
                         "first-login-dismissed")

    def test_shell_proof_typed_bytes_do_not_contain_the_required_ocr_marker(self):
        self.assertNotIn("ARCTIC-SHOWCASE-SHELL-READY", automation.Controller.SHELL_PROOF)
        self.assertEqual(len(automation.Controller.SHELL_PROOF), 119)

    def test_installed_shell_waits_for_fetch_and_dismisses_it_with_one_key(self):
        operations = []

        def wait(_stage, expectation, phrases=(), **_kwargs):
            operations.append(("screen", expectation, phrases))
            return None, ""

        def press(_stage, *names, **_kwargs):
            operations.append(("keys", names))

        def text(_stage, command_id, _value, **_kwargs):
            operations.append(("text", command_id))

        def secret(_stage):
            operations.append(("secret",))

        self.controller.wait_screen = wait
        self.controller.press = press
        self.controller.type_text = text
        self.controller.type_secret = secret
        with mock.patch.object(automation.time, "sleep"):
            self.controller.boot_installed_and_start()

        greeting = ("screen", "installed-fetch-greeting", ("Arctic Linux", "fish 4.6"))
        proof = ("text", "installed-shell-proof")
        at = operations.index(greeting)
        self.assertEqual(operations[at + 1], ("keys", ("ret",)))
        self.assertEqual(operations[at + 2], proof)
        self.assertLess(operations.index(("secret",)), at)
        self.assertEqual(operations[at + 4],
                         ("screen", "installed-shell", ("ARCTIC-SHOWCASE-SHELL-READY",)))

class TraceContract(unittest.TestCase):
    def test_guest_fields_cannot_enter_or_promote_trace(self):
        value = controller_trace()
        for mutate in (
            lambda row: row.update(guest_diagnostics_used=True),
            lambda row: row.update(release_acceptance=True),
            lambda row: row["events"][0]["detail"].update(guest={"ready": True}),
            lambda row: row["events"].pop(),
            lambda row: row["events"][9]["detail"].update(target="guest-target"),
        ):
            changed = copy.deepcopy(value)
            mutate(changed)
            with self.assertRaises(c.Invalid):
                c.controller_trace(changed)

    def test_required_event_order_is_fail_closed(self):
        value = controller_trace()
        value["events"][8], value["events"][11] = value["events"][11], value["events"][8]
        for index, event in enumerate(value["events"]):
            event["index"] = index
        with self.assertRaises(c.Invalid):
            c.controller_trace(value)


class GuestAutomation(unittest.TestCase):
    def _run_installer(self, pages):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser", pw_dir="/home/liveuser")
        index = {"value": 0}
        fills = []
        channel_rows = []

        def ipc(_account, _environment, _pid, method, payload=None):
            if method == "state":
                page = pages[index["value"]]
                return json.dumps({"page": page, "current": page, "ready": True,
                                   "connected": True, "busy": False, "failure": "",
                                   "valid": True, "percent": 100 if page == "done" else 0})
            if method == "fill":
                fills.append((pages[index["value"]], payload))
                return "ok"
            index["value"] += 1
            return "ok"

        class Channel:
            def __init__(self, *args, **kwargs): pass
            def write(self, value): channel_rows.append(value)
            def read(self): return c.INSTALL_ACK
            def close(self): pass

        with mock.patch.object(unattended.os, "geteuid", return_value=0), \
             mock.patch.object(unattended, "_graphical_environment",
                               return_value=(account, 2, {"PATH": "/usr/bin:/bin"})), \
             mock.patch.object(unattended, "_find_ipc", return_value=("123", "{}")), \
             mock.patch.object(unattended, "_process_start_ticks", return_value=456), \
             mock.patch.object(unattended, "_installer_call", side_effect=ipc), \
             mock.patch.object(unattended, "_run"), \
             mock.patch.object(unattended, "_mount_installed_target", return_value=Path("/mnt/sysroot")), \
             mock.patch.object(unattended.guest, "seal_installation", return_value={}), \
             mock.patch.object(unattended.c, "install_seal"), \
             mock.patch.object(unattended, "Channel", Channel):
            unattended.live_install(600)
        return fills, channel_rows

    @staticmethod
    def _ready_state(**changed):
        value = {"page": "welcome", "current": "welcome", "ready": True,
                 "connected": True, "busy": False, "failure": "", "valid": True}
        value.update(changed)
        return json.dumps(value)

    def test_unique_installer_ipc_rejects_ambiguous_targets(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")

        def run(argv, **_kwargs):
            self.assertEqual(argv[:5], ["/usr/bin/pgrep", "-u", "1000", "-x", "quickshell"])
            return types.SimpleNamespace(returncode=0, stdout=b"101\n202\n")

        with mock.patch.object(unattended, "_run", side_effect=run), \
             mock.patch.object(unattended, "_as_user",
                               return_value=types.SimpleNamespace(returncode=0, stdout=b"{}")):
            with self.assertRaisesRegex(c.Invalid, "absent or ambiguous"):
                unattended._find_ipc(account, {}, "installer", "state")

    def test_installer_reacquires_a_replacement_before_first_input(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")
        calls = []

        def call(_account, _environment, pid, method, payload=None):
            calls.append((pid, method, payload))
            if method == "state":
                return self._ready_state(ready=pid == "303")
            return "ok"

        with mock.patch.object(unattended, "_installer_endpoint",
                               side_effect=[("101", 10), ("202", 20), ("303", 30)]), \
             mock.patch.object(unattended, "_process_start_ticks",
                               side_effect=lambda _account, pid: {"202": 20, "303": 30}[pid]), \
             mock.patch.object(unattended.time, "sleep"), \
             mock.patch.object(unattended, "_installer_call", side_effect=call):
            early = unattended._installer_endpoint(account, {})
            endpoint, result = unattended._installer_input(
                account, {}, None, "welcome", "next", require_valid=True)
        self.assertEqual(early, ("101", 10))
        self.assertEqual(endpoint, ("303", 30))
        self.assertEqual(result, "ok")
        self.assertEqual(calls, [("202", "state", None), ("303", "state", None),
                                 ("303", "next", None)])

    def test_installer_rejects_pid_or_start_time_swap_after_input(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")
        for replacement in (("202", 20), ("101", 20)):
            with self.subTest(replacement=replacement), \
                 mock.patch.object(unattended, "_installer_endpoint",
                                   return_value=replacement), \
                 mock.patch.object(unattended, "_installer_call") as call:
                with self.assertRaisesRegex(unattended.InstallerIdentityChanged,
                                            "changed after input"):
                    unattended._installer_input(
                        account, {}, ("101", 10), "welcome", "next",
                        require_valid=True)
                call.assert_not_called()

    def test_installer_input_rechecks_every_existing_page_gate(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")
        def once(function, _seconds, message):
            value = function()
            if value:
                return value
            raise c.Invalid(message)
        invalid = (
            {"page": "keyboard"}, {"current": "keyboard"}, {"ready": False},
            {"connected": False}, {"busy": True}, {"failure": "failed"},
            {"valid": False},
        )
        for changed in invalid:
            calls = []
            def call(_account, _environment, pid, method, payload=None):
                calls.append((pid, method, payload))
                return self._ready_state(**changed) if method == "state" else "ok"
            with self.subTest(changed=changed), \
                 mock.patch.object(unattended, "_installer_endpoint",
                                   return_value=("101", 10)), \
                 mock.patch.object(unattended, "_process_start_ticks", return_value=10), \
                 mock.patch.object(unattended, "_wait", side_effect=once), \
                 mock.patch.object(unattended, "_installer_call", side_effect=call):
                with self.assertRaisesRegex(c.Invalid, "changed before input"):
                    unattended._installer_input(
                        account, {}, ("101", 10), "welcome", "next",
                        require_valid=True)
            self.assertEqual(calls, [("101", "state", None)])

    def test_live_installer_uses_fixed_online_real_gui_choices(self):
        pages = list(("welcome", "keyboard", "network", "timezone", "disk", "encryption",
                      "account", "apps", "summary", "done"))
        fills, rows = self._run_installer(pages)
        choices = dict(fills)
        self.assertEqual(choices["network"], {"offline": False})
        self.assertEqual(choices["disk"], {"disk": "/dev/vda", "mode": "erase"})
        self.assertEqual(choices["encryption"], {"enabled": False})
        self.assertTrue(choices["account"]["autologin"])
        self.assertEqual(choices["account"]["username"], c.CONTROLLER["account"]["username"])
        self.assertEqual(choices["account"]["password"], unattended.PASSWORD)
        progress = [c.strict_json(row[len(c.INSTALL_PROGRESS_PREFIX):]) for row in rows[:-1]]
        for value in progress:
            c.install_progress(value)
        self.assertEqual([value["sequence"] for value in progress], list(range(len(progress))))
        self.assertEqual(progress[-1], {
            "schema": "arctic-showcase-install-progress-v1",
            "sequence": len(progress) - 1, "stage": "host-handoff", "status": "started",
            "release_acceptance": False,
        })
        self.assertTrue(rows[-1].startswith(c.INSTALL_PREFIX))
        self.assertNotIn(unattended.PASSWORD, repr(progress))

    def test_live_installer_accepts_the_real_wired_online_network_auto_skip(self):
        pages = list(("welcome", "keyboard", "timezone", "disk", "encryption",
                      "account", "apps", "summary", "done"))
        fills, rows = self._run_installer(pages)
        fills = dict(fills)
        self.assertNotIn("network", fills)
        self.assertEqual(fills["disk"], {"disk": "/dev/vda", "mode": "erase"})
        stages = [c.strict_json(row[len(c.INSTALL_PROGRESS_PREFIX):])["stage"]
                  for row in rows[:-1]]
        self.assertNotIn("page-network", stages)

    def test_host_consumes_strict_progress_and_rejects_guest_failure_early(self):
        def row(sequence, stage, status):
            value = {"schema": "arctic-showcase-install-progress-v1",
                     "sequence": sequence, "stage": stage, "status": status,
                     "release_acceptance": False}
            return c.INSTALL_PROGRESS_PREFIX + json.dumps(value, separators=(",", ":"))

        class Lines:
            def __init__(self, rows): self.rows = iter(rows)
            def read(self, _timeout=None): return next(self.rows)

        progress = []
        with self.assertRaisesRegex(c.Invalid, "bounded failure"):
            capture_vm._install_seal(Lines([
                row(0, "live-helper", "started"),
                row(1, "live-helper", "failed"),
            ]), progress)
        self.assertEqual(progress[-1]["status"], "failed")
        forged = []
        with self.assertRaisesRegex(c.Invalid, "stage order"):
            capture_vm._install_seal(Lines([
                row(0, "live-helper", "started"),
                row(1, "live-helper", "passed"),
                row(2, "page-summary", "started"),
            ]), forged)

    def test_host_accepts_complete_ordered_progress_with_optional_network_skip(self):
        stages = ["live-helper", "graphical-session", "installer-ipc", "page-welcome",
                  "page-keyboard", "online-route", "page-timezone", "page-disk",
                  "page-encryption", "page-account", "page-apps", "page-summary",
                  "installation", "target-mount", "install-seal"]
        rows = []
        for stage in stages:
            for status in ("started", "passed"):
                value = {"schema": "arctic-showcase-install-progress-v1",
                         "sequence": len(rows), "stage": stage, "status": status,
                         "release_acceptance": False}
                rows.append(c.INSTALL_PROGRESS_PREFIX
                            + json.dumps(value, separators=(",", ":")))
        handoff = {"schema": "arctic-showcase-install-progress-v1",
                   "sequence": len(rows), "stage": "host-handoff", "status": "started",
                   "release_acceptance": False}
        rows.extend([c.INSTALL_PROGRESS_PREFIX + json.dumps(handoff, separators=(",", ":")),
                     c.INSTALL_PREFIX + "{}"])

        class Lines:
            def __init__(self): self.rows = iter(rows)
            def read(self, _timeout=None): return next(self.rows)

        progress = []
        self.assertEqual(capture_vm._install_seal(Lines(), progress), c.INSTALL_PREFIX + "{}")
        self.assertEqual(len(progress), len(rows) - 1)
        self.assertEqual(progress[-1], handoff)

    def test_unexpected_guest_exception_emits_terminal_failure_and_host_stops(self):
        rows = []

        class Channel:
            def __init__(self, *args, **kwargs): pass
            def write(self, value): rows.append(value)
            def close(self): pass

        with mock.patch.object(unattended.os, "geteuid", return_value=0), \
             mock.patch.object(unattended, "Channel", Channel), \
             mock.patch.object(unattended, "_graphical_environment",
                               side_effect=AttributeError("unexpected private detail")):
            with self.assertRaises(AttributeError):
                unattended.live_install(600)
        progress = [c.strict_json(row[len(c.INSTALL_PROGRESS_PREFIX):]) for row in rows]
        self.assertEqual([(value["stage"], value["status"]) for value in progress], [
            ("live-helper", "started"), ("live-helper", "passed"),
            ("graphical-session", "started"), ("graphical-session", "failed"),
        ])
        self.assertNotIn("unexpected private detail", repr(rows))

        class Lines:
            def __init__(self): self.rows = iter(rows)
            def read(self, _timeout=None): return next(self.rows)

        consumed = []
        with self.assertRaisesRegex(c.Invalid, "bounded failure"):
            capture_vm._install_seal(Lines(), consumed)
        self.assertEqual(consumed[-1]["status"], "failed")

    def test_pre_python_bootstrap_has_fixed_failure_projection(self):
        self.assertEqual(automation.BOOTSTRAP_FAILURE, {
            "schema": "arctic-showcase-install-progress-v1", "sequence": 0,
            "stage": "live-helper", "status": "failed", "release_acceptance": False,
        })
        self.assertIn("trap fail EXIT", automation.Controller.LIVE_COMMAND)
        self.assertIn(automation.BOOTSTRAP_FAILURE_WORD, automation.Controller.LIVE_COMMAND)

        timeouts = []
        class Lines:
            def read(self, timeout=None):
                timeouts.append(timeout)
                return automation.BOOTSTRAP_FAILURE_LINE

        consumed = []
        with self.assertRaisesRegex(c.Invalid, "bounded failure"):
            capture_vm._install_seal(Lines(), consumed)
        self.assertEqual(consumed, [automation.BOOTSTRAP_FAILURE])
        self.assertEqual(timeouts, [300])

        with tempfile.TemporaryDirectory() as temp:
            port = Path(temp) / "channel"
            port.write_text("invalid tooling line\n")
            tooling = Path(temp) / "tooling"
            inner = shlex.split(automation.Controller.LIVE_COMMAND)[3]
            inner = inner.replace("/dev/virtio-ports/org.arctic.showcase.capture", str(port))
            inner = inner.replace("/run/arctic-showcase-tooling", str(tooling))
            result = subprocess.run(["/bin/sh", "-c", inner], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    timeout=10, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(port.read_text(), automation.BOOTSTRAP_FAILURE_LINE + "\n")

    def test_failure_projection_is_bounded_and_contains_no_guest_content(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "failure.json"
            progress = [{"schema": "arctic-showcase-install-progress-v1", "sequence": 0,
                         "stage": "live-helper", "status": "started",
                         "release_acceptance": False}]
            capture_vm._write_failure_report(
                path, "live-install", progress,
                c.Invalid("private capture channel timed out"), None)
            self.assertLessEqual(path.stat().st_size, 32768)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            value = c.strict_json(path.read_bytes())
            c.capture_failure(value)
            self.assertEqual(value["failure_code"], "private-channel-timeout")
            self.assertNotIn("private capture channel timed out", path.read_text())

    def test_graphical_environment_accepts_unique_wayland_session_while_vt_is_inactive(self):
        account = types.SimpleNamespace(pw_uid=os.geteuid(), pw_name="liveuser",
                                        pw_dir="/home/liveuser")
        with tempfile.TemporaryDirectory() as temp:
            process = Path(temp) / "123"
            process.mkdir()
            runtime = f"/run/user/{account.pw_uid}"
            (process / "environ").write_bytes(
                (f"DBUS_SESSION_BUS_ADDRESS=unix:path={runtime}/bus\0"
                 f"WAYLAND_DISPLAY=wayland-1\0XDG_RUNTIME_DIR={runtime}\0").encode())
            calls = []

            def run(argv, **_kwargs):
                calls.append(argv)
                if argv[1] == "list-sessions":
                    output = b"7 1000 liveuser seat0\n"
                elif "Type" in argv:
                    output = b"wayland\n"
                elif "VTNr" in argv:
                    output = b"2\n"
                else:
                    raise AssertionError(argv)
                return types.SimpleNamespace(returncode=0, stdout=output)

            with mock.patch.object(unattended.pwd, "getpwnam", return_value=account), \
                 mock.patch.object(unattended, "_run", side_effect=run), \
                 mock.patch.object(unattended.Path, "glob", return_value=[process]), \
                 mock.patch.object(unattended.Path, "is_dir", return_value=True), \
                 mock.patch.object(unattended.Path, "is_symlink", return_value=False):
                _, vt, environment = unattended._graphical_environment("liveuser")
        self.assertEqual(vt, 2)
        self.assertEqual(environment["WAYLAND_DISPLAY"], "wayland-1")
        self.assertFalse(any("Active" in argv for argv in calls))

    def test_installed_root_launcher_activates_vt_before_irrevocable_uid_drop(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name=c.CONTROLLER["account"]["username"],
                                        pw_dir="/home/" + c.CONTROLLER["account"]["username"])
        environment = {"PATH": "/usr/bin:/bin", "XDG_RUNTIME_DIR": "/run/user/1000",
                       "WAYLAND_DISPLAY": "wayland-1"}
        calls = []

        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            return types.SimpleNamespace(returncode=0, stdout=b"")

        with mock.patch.object(unattended.os, "geteuid", return_value=0), \
             mock.patch.object(unattended, "_graphical_environment",
                               return_value=(account, 2, environment)), \
             mock.patch.object(unattended, "_run", side_effect=run):
            unattended.installed_root_launch(600)
        self.assertEqual(calls[0][0], ["/usr/bin/chvt", "2"])
        self.assertEqual(calls[1][0][:5],
                         ["/usr/sbin/runuser", "-u", c.CONTROLLER["account"]["username"],
                          "--", "/usr/bin/env"])
        self.assertIn("installed-scenes", calls[1][0])
        self.assertNotIn("/usr/bin/chvt", calls[1][0])

    def test_completed_install_remounts_only_unique_fixed_disk_root_subvolume(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "target"
            calls = []
            report = {"blockdevices": [{"path": "/dev/vda", "name": "vda",
                "type": "disk", "serial": c.VM_DISK_SERIAL, "children": [
                    {"path": "/dev/vda3", "name": "vda3", "pkname": "vda",
                     "type": "part", "fstype": "btrfs", "label": "arctic",
                     "partlabel": "Arctic root"}]}]}
            findmnt = {"count": 0}

            def run(argv, **_kwargs):
                calls.append(argv)
                if argv[0] == "/usr/bin/lsblk":
                    return types.SimpleNamespace(returncode=0, stdout=json.dumps(report).encode())
                if argv[0] == "/usr/bin/findmnt":
                    findmnt["count"] += 1
                    if findmnt["count"] == 1:
                        return types.SimpleNamespace(returncode=1, stdout=b"")
                    return types.SimpleNamespace(returncode=0, stdout=b"/dev/vda3[/@]\n")
                if argv[0] == "/usr/bin/mount":
                    return types.SimpleNamespace(returncode=0, stdout=b"")
                raise AssertionError(argv)

            with mock.patch.object(unattended.os, "geteuid", return_value=0), \
                 mock.patch.object(unattended.Path, "resolve", return_value=Path("/dev/vda")), \
                 mock.patch.object(unattended, "_run", side_effect=run):
                self.assertEqual(unattended._mount_installed_target(target), target)
        self.assertIn(["/usr/bin/mount", "-o", "subvol=@,compress=zstd:1",
                       "/dev/vda3", str(target)], calls)

    def test_dictation_readiness_is_exact_and_never_substituted(self):
        good = {"ok": True, "ready": True, "state": "ready", "version": "1.1.1",
                "profile": "small-v2", "model": "small", "cpu_variant": "baseline",
                "model_download_bytes": 487601967, "download_bytes": 506440871,
                "compatibility_required": False}
        result = types.SimpleNamespace(returncode=0, stdout=json.dumps(good).encode())
        with mock.patch.object(unattended, "_run", return_value=result):
            self.assertTrue(unattended._dictation_ready({}))
        for field, value in (("ready", False), ("state", "error"),
                             ("download_bytes", 9), ("compatibility_required", True)):
            bad = dict(good, **{field: value})
            result = types.SimpleNamespace(returncode=0, stdout=json.dumps(bad).encode())
            with mock.patch.object(unattended, "_run", return_value=result):
                self.assertIsNone(unattended._dictation_ready({}))


if __name__ == "__main__":
    unittest.main()
