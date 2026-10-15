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

from PIL import Image, ImageChops

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
        self.controller = automation.Controller(
            self.qmp, self.root, lambda path: "clean", lambda path: "clean", (), "f" * 64)

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

    def test_control_l_redraw_uses_bounded_hold_without_return_or_text_byte(self):
        self.controller.press_held("installed-console", "ctrl-l", gap=0)
        self.assertEqual(len(self.qmp.commands), 1)
        name, arguments = self.qmp.commands[0]
        self.assertEqual(name, "send-key")
        self.assertEqual(arguments, {
            "keys": [
                {"type": "qcode", "data": "ctrl"},
                {"type": "qcode", "data": "l"},
            ],
            "hold-time": 100,
        })
        self.assertNotIn("ret", repr(arguments))
        self.assertEqual(self.controller.events, [{
            "index": 0, "stage": "installed-console", "kind": "keys",
            "detail": {"names": ["ctrl-l"]},
        }])

    def test_held_key_uses_qemu_timer_and_records_only_reviewed_names(self):
        self.controller.press_held("live-boot", "home", "down", gap=0)
        self.assertEqual(self.qmp.commands, [
            ("send-key", {"keys": [{"type": "qcode", "data": "home"}],
                          "hold-time": 100}),
            ("send-key", {"keys": [{"type": "qcode", "data": "down"}],
                          "hold-time": 100}),
        ])
        self.assertEqual(self.controller.events, [{
            "index": 0, "stage": "live-boot", "kind": "keys",
            "detail": {"names": ["home", "down"]},
        }])

    def test_install_selection_requires_exact_firmware_geometry_and_amber_row(self):
        def frame(top):
            image = Image.new("RGB", (1920, 1080), "#101820")
            for y in range(top, top + 40):
                for x in range(750, 1168):
                    image.putpixel((x, y), (250, 190, 84))
            return image

        self.assertTrue(automation._boot_entry_selected(frame(235), "try"))
        self.assertFalse(automation._boot_entry_selected(frame(235), "install"))
        self.assertTrue(automation._boot_entry_selected(frame(279), "install"))
        self.assertFalse(automation._boot_entry_selected(frame(279), "try"))
        self.assertFalse(automation._boot_entry_selected(
            Image.new("RGB", (1280, 800), (250, 190, 84)), "install"))

    def test_install_selection_records_only_fixed_menu_and_pixel_proof(self):
        path = self.root / "selected.png"
        image = Image.new("RGB", (1920, 1080), "#101820")
        for y in range(279, 319):
            for x in range(750, 1168):
                image.putpixel((x, y), (250, 190, 84))
        image.save(path)
        text = ("Try Arctic Linux\nSafe graphics mode\nCheck USB for errors\n"
                "Boot from first disk")
        self.controller._shot = mock.Mock(return_value=(path, path.lstat(), image, text))
        self.controller.wait_install_boot_selection(seconds=1)
        self.assertFalse(path.exists())
        self.assertEqual(self.controller.events[0]["detail"]["expectation"],
                         "install-boot-menu-selected")
        self.assertEqual((self.controller.events[0]["detail"]["width"],
                          self.controller.events[0]["detail"]["height"]), (1920, 1080))

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

    def test_installed_shell_ocr_focus_is_fixed_private_and_does_not_replace_frame(self):
        observations = []

        source = Image.new("RGB", (1280, 800), "black")
        source.putpixel((10, 12), (0, 32, 96))
        source.putpixel((11, 12), (224, 224, 224))

        def screendump(path):
            source.save(path)

        def ocr(path):
            with Image.open(path) as image:
                observations.append({
                    "name": path.name,
                    "size": image.size,
                    "background": image.getpixel((0, 0)),
                    "blue_glyph": image.getpixel((40, 48)),
                    "white_glyph": image.getpixel((44, 48)),
                })
            return ("ARCTIC - SHOWCASE - SHELL - READY\n"
                    "arcticshowcase@arctic-showcase ~>")

        self.qmp.screendump = screendump
        self.controller.ocr = ocr
        self.controller.shell_focus_ocr = ocr
        path, info, image, text = self.controller._shot(
            "installed-shell-ready", shell_ocr_focus=True)
        self.assertEqual(observations, [
            {"name": "controller-001-installed-shell-ready.png", "size": (1280, 800),
             "background": (0, 0, 0), "blue_glyph": (0, 0, 0),
             "white_glyph": (0, 0, 0)},
            {"name": "controller-001-installed-shell-ready-ocr.png", "size": (5120, 512),
             "background": (0, 0, 0), "blue_glyph": (255, 255, 255),
             "white_glyph": (255, 255, 255)},
        ])
        self.assertEqual((path.stat().st_size, info.st_size, image.size),
                         (info.st_size, info.st_size, (1280, 800)))
        self.assertEqual(image.getpixel((10, 12)), (0, 32, 96))
        self.assertEqual(image.getpixel((11, 12)), (224, 224, 224))
        self.assertEqual(text.splitlines()[-1], "arcticshowcase@arctic-showcase ~>")
        self.assertFalse((self.root / "controller-001-installed-shell-ready-ocr.png").exists())
        path.unlink()

    def test_installed_shell_ocr_focus_is_deleted_when_private_ocr_fails(self):
        source = Image.new("RGB", (1280, 800), "black")
        source.putpixel((10, 12), (0, 32, 96))
        self.qmp.screendump = lambda path: source.save(path)
        calls = 0

        def ocr(_path):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise c.Invalid("private focus OCR failed")
            return "clean"

        self.controller.ocr = ocr
        self.controller.shell_focus_ocr = ocr
        with self.assertRaisesRegex(c.Invalid, "private focus OCR failed"):
            self.controller._shot("installed-shell-ready", shell_ocr_focus=True)
        self.assertFalse((self.root / "controller-001-installed-shell-ready-ocr.png").exists())

    def test_installed_shell_focus_output_is_privacy_checked_and_deleted(self):
        private = "private-fragment-0123456789"
        source = Image.new("RGB", (1280, 800), "black")
        source.putpixel((10, 12), (0, 32, 96))
        self.qmp.screendump = lambda path: source.save(path)
        self.controller.fragments = (private,)
        self.controller.ocr = lambda _path: "clean"
        self.controller.shell_focus_ocr = lambda _path: private

        with self.assertRaisesRegex(c.Invalid, "private transcript fragment in capture"):
            self.controller._shot("installed-shell-ready", shell_ocr_focus=True)
        self.assertFalse((self.root / "controller-001-installed-shell-ready-ocr.png").exists())

    def test_full_frame_privacy_precedes_shell_focus_creation(self):
        private = "private-fragment-0123456789"
        source = Image.new("RGB", (1280, 800), "black")
        source.putpixel((10, 12), (0, 32, 96))
        self.qmp.screendump = lambda path: source.save(path)
        self.controller.fragments = (private,)
        self.controller.ocr = lambda _path: private
        self.controller.shell_focus_ocr = mock.Mock(return_value="clean")

        with self.assertRaisesRegex(c.Invalid, "private transcript fragment in capture"):
            self.controller._shot("installed-shell-ready", shell_ocr_focus=True)
        self.controller.shell_focus_ocr.assert_not_called()
        self.assertFalse((self.root / "controller-001-installed-shell-ready-ocr.png").exists())

    def test_shell_ocr_focus_whitens_only_nonblack_glyph_pixels(self):
        source = Image.new("RGB", (1280, 800), "black")
        source.putpixel((7, 9), (0, 1, 0))
        source.putpixel((8, 9), (12, 34, 56))
        source.putpixel((7, 130), (255, 255, 255))
        unchanged = source.copy()
        expected = Image.new("RGB", (1280, 128), "black")
        expected.putpixel((7, 9), (255, 255, 255))
        expected.putpixel((8, 9), (255, 255, 255))
        expected = expected.resize((5120, 512), Image.Resampling.NEAREST)

        focused = automation._shell_ocr_focus(source)

        self.assertEqual(source.size, (1280, 800))
        self.assertIsNone(ImageChops.difference(source, unchanged).getbbox())
        self.assertEqual(focused.size, (5120, 512))
        self.assertIsNone(ImageChops.difference(focused, expected).getbbox())

    def test_boot_countdown_is_held_after_decode_and_before_ocr(self):
        order = []
        image = Image.new("RGB", (1920, 1080), "#101820")
        for y in range(235, 275):
            for x in range(750, 1168):
                image.putpixel((x, y), (250, 190, 84))

        def screendump(path):
            image.save(path)

        def ocr(_path):
            order.append("ocr")
            self.assertTrue(self.controller.boot_countdown_held)
            return "Try Arctic Linux Install Arctic Linux"

        self.qmp.screendump = screendump
        self.controller.ocr = ocr
        original = self.controller.press_held

        def held(*args, **kwargs):
            order.append("home")
            return original(*args, **kwargs)

        self.controller.press_held = held
        self.controller.wait_screen(
            "live-boot", "install-boot-menu", ("Arctic", "Install"), seconds=1,
            before_ocr=self.controller.hold_boot_countdown_before_ocr)
        self.assertEqual(order, ["home", "ocr"])
        self.assertEqual([event["kind"] for event in self.controller.events],
                         ["keys", "screen"])

    def test_screen_gate_fails_closed_on_missing_phrase_or_private_text(self):
        self.controller.ocr = lambda path: "wrong screen"
        with mock.patch.object(automation.time, "sleep"):
            with self.assertRaisesRegex(
                    c.Invalid, "controller screen expectation whats-new-layer absent"):
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

    def test_live_boot_proves_the_real_installer_before_switching_vt(self):
        operations = []

        def boot_frame():
            image = Image.new("RGB", (1920, 1080), "#101820")
            for y in range(235, 275):
                for x in range(750, 1168):
                    image.putpixel((x, y), (250, 190, 84))
            return image

        def wait(stage, expectation, phrases=(), **kwargs):
            if expectation == "install-boot-menu":
                kwargs["before_ocr"](boot_frame())
            operations.append(("screen", stage, expectation, phrases, kwargs))
            return None, ""

        def press(stage, *names, **_kwargs):
            operations.append(("keys", stage, names))

        def selection(*_args, **_kwargs):
            operations.append(("selection", "live-boot", "install-boot-menu-selected"))

        def text(stage, command_id, _value, **_kwargs):
            operations.append(("text", stage, command_id))

        self.controller.wait_screen = wait
        self.controller.press = press
        self.controller.press_held = press
        self.controller.wait_install_boot_selection = selection
        self.controller.type_text = text
        with mock.patch.object(automation.time, "sleep"):
            self.controller.boot_live_and_start()

        self.assertEqual(operations[0], ("keys", "live-boot", ("home",)))
        self.assertEqual(operations[1][:4],
                         ("screen", "live-boot", "install-boot-menu",
                          ("Arctic", "Install")))
        self.assertEqual(operations[2], ("keys", "live-boot", ("down",)))
        self.assertEqual(operations[3],
                         ("selection", "live-boot", "install-boot-menu-selected"))
        self.assertEqual(operations[4], ("keys", "live-boot", ("ret",)))
        installer = operations[5]
        self.assertEqual(installer[:4], (
            "screen", "live-boot", "live-installer-visible",
            ("Welcome to Arctic Linux", "Keyboard", "Time zone", "Summary"),
        ))
        self.assertEqual(installer[4], {
            "seconds": 600, "visible": True, "exact_output": True,
        })
        self.assertFalse(all(phrase.casefold() in "Try Arctic Linux Install Arctic Linux".casefold()
                             for phrase in installer[3]))
        self.assertEqual(operations[6], ("keys", "live-console", ("ctrl-alt-f6",)))

    def test_live_startup_surface_projection_uses_only_fixed_enums(self):
        image = Image.new("RGB", (1280, 800))
        # At least sixteen sampled colours makes this a visible frame under the
        # exact same rule as the authoritative gate.
        pixels = image.load()
        for y in range(800):
            for x in range(1280):
                pixels[x, y] = ((x // 40) % 32, (y // 40) % 20, (x + y) % 251)
        cases = {
            "Try Arctic Linux\nInstall Arctic Linux\nSafe graphics mode": "boot-menu",
            "Starting Arctic Linux": "boot-progress",
            "Install Arctic Linux": "live-desktop",
            "Welcome to Arctic Linux\nKeyboard": "installer-partial",
            "The installer isn't on this USB": "installer-error",
            "You are in emergency mode": "console-or-emergency",
            "unrecognized private-looking words": "other-text",
            "": "ocr-empty",
            "Welcome to Arctic Linux\nKeyboard\nTime zone\nSummary": "installer-welcome",
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(automation._live_surface_class(image, text), expected)
        self.assertEqual(automation._live_surface_class(
            Image.new("RGB", (1280, 800), "black"), "private"), "blank-output")
        self.assertEqual(automation._live_surface_class(
            Image.new("RGB", (1024, 768), "black"), "private"), "geometry-mismatch")

    def test_live_startup_failure_probe_accepts_only_fixed_result(self):
        for character in automation.Controller.LIVE_STARTUP_PROBE:
            automation.chord_for(character)
        self.assertLessEqual(len(automation.Controller.LIVE_STARTUP_PROBE), 4096)
        self.controller.live_startup.boot_observed()
        self.controller.live_startup.selection_sent()
        self.controller.live_startup.gate_started = automation.time.monotonic()
        self.controller.live_startup.gate_end("timed-out")
        self.controller.accept_live_failure_probe(
            "ARCTIC-SHOWCASE-LIVE-STARTUP-V1 install running absent")
        value = self.controller.live_startup.projection()
        c.live_startup_diagnostic(value)
        self.assertEqual(value["post_failure_probe"], {
            "status": "completed", "boot_mode": "install",
            "graphical_session": "running", "installer_process": "absent",
        })
        self.assertNotIn("ARCTIC-SHOWCASE-LIVE-STARTUP-V1", repr(value))
        for forged in (
            "ARCTIC-SHOWCASE-LIVE-STARTUP-V1 private running absent",
            "ARCTIC-SHOWCASE-LIVE-STARTUP-V1 install running absent private",
            "private guest output",
        ):
            with self.subTest(forged=forged), self.assertRaises(c.Invalid):
                self.controller.accept_live_failure_probe(forged)

    def test_live_startup_diagnostic_is_bounded_and_rejects_flexible_content(self):
        diagnostic = automation.LiveStartupDiagnostic()
        diagnostic.boot_observed()
        diagnostic.selection_sent()
        diagnostic.gate_start()
        diagnostic.observe("boot-menu")
        diagnostic.observe("ocr-empty")
        diagnostic.gate_end("timed-out")
        diagnostic.probe("channel-unavailable")
        value = diagnostic.projection()
        c.live_startup_diagnostic(value)
        self.assertEqual(value["welcome_gate"]["timeout_seconds"], 600)
        self.assertLessEqual(value["welcome_gate"]["samples"], 301)
        forged = copy.deepcopy(value)
        forged["welcome_gate"]["private_ocr"] = "do not export"
        with self.assertRaises(c.Invalid):
            c.live_startup_diagnostic(forged)
        forged = copy.deepcopy(value)
        forged["welcome_gate"]["last_observation"] = "guest-selected"
        with self.assertRaises(c.Invalid):
            c.live_startup_diagnostic(forged)

    def test_installed_shell_surface_projection_uses_only_fixed_enums(self):
        image = Image.new("RGB", (1280, 800))
        pixels = image.load()
        for y in range(800):
            for x in range(1280):
                pixels[x, y] = ((x // 40) % 32, (y // 40) % 20, (x + y) % 251)
        account = "arcticshowcase@arctic-showcase"
        suffixes = ("~>", "~ >")
        cases = {
            account + " ~>": "prompt-exact",
            account + " ~>\ntrailing fetch row": "prompt-not-final",
            "ARCTIC-SHOWCASE-SHELL-READY": "proof-marker",
            "ARCTIC - SHOWCASE- SHELL -READY": "proof-marker",
            "Arctic Linux\nshell fish 4.6\n" + account: "fetch-greeting",
            account: "account-only",
            "~ >": "suffix-only",
            "arctic-showcase login:": "login-or-password",
            "unrecognized private-looking words": "other-text",
            "": "ocr-empty",
        }
        for text, expected in cases.items():
            with self.subTest(expected=expected):
                self.assertEqual(automation._installed_shell_surface_class(
                    image, text, account, suffixes), expected)
        self.assertEqual(automation._installed_shell_surface_class(
            Image.new("RGB", (1280, 800), "black"), "private", account, suffixes),
            "blank-output")
        self.assertEqual(automation._installed_shell_surface_class(
            Image.new("RGB", (1280, 800), "black"), account + " ~>", account, suffixes),
            "prompt-exact")
        low_color_cases = {
            account + " ~>\ntrailing row": "prompt-not-final",
            "ARCTIC - SHOWCASE- SHELL -READY": "proof-marker",
            "Arctic Linux\nshell fish 4.6": "fetch-greeting",
            account: "account-only",
            "~ >": "suffix-only",
            "Password:": "login-or-password",
        }
        for text, expected in low_color_cases.items():
            with self.subTest(low_color=expected):
                self.assertEqual(automation._installed_shell_surface_class(
                    Image.new("RGB", (1280, 800), "black"), text, account, suffixes),
                    expected)
        self.assertEqual(automation._installed_shell_surface_class(
            Image.new("RGB", (1024, 768), "black"), "private", account, suffixes),
            "geometry-mismatch")

    def test_installed_shell_signals_are_independent_fixed_booleans(self):
        account = "arcticshowcase@arctic-showcase"
        suffixes = ("~>", "~ >")
        marker = "ARCTIC - SHOWCASE - SHELL - READY"
        self.assertEqual(automation._installed_shell_signals(
            marker + "\nunreadable ~>", account, suffixes), {
                "marker": True, "account-pattern": False,
                "suffix": True, "exact": False,
            })
        self.assertEqual(automation._installed_shell_signals(
            account + " ~>", account, suffixes), {
                "marker": False, "account-pattern": True,
                "suffix": True, "exact": True,
            })
        self.assertEqual(automation._installed_shell_signals(
            marker + "\n" + account + " ~>", account, suffixes), {
                "marker": True, "account-pattern": True,
                "suffix": True, "exact": True,
            })
        self.assertEqual(automation._installed_shell_signals(
            marker + "\narcticshowcase @ arctic - showcase\n~ >",
            account, suffixes), {
                "marker": True, "account-pattern": True,
                "suffix": True, "exact": False,
            })
        self.assertEqual(automation._installed_shell_signals(
            "arcticshowcase @ arctic - showcase ~ >", account, suffixes), {
                "marker": False, "account-pattern": True,
                "suffix": True, "exact": True,
            })
        self.assertEqual(automation._installed_shell_signals(
            "arcticsh0wcase @ arctic - showcase ~ >", account, suffixes), {
                "marker": False, "account-pattern": False,
                "suffix": True, "exact": False,
            })

    def test_installed_startup_diagnostic_is_bounded_and_rejects_private_content(self):
        diagnostic = automation.InstalledStartupDiagnostic()
        diagnostic.start()
        diagnostic.login_observed()
        diagnostic.authentication_sent()
        diagnostic.fetch_observed()
        diagnostic.dismissal_sent()
        diagnostic.gate_start()
        diagnostic.observe("fetch-greeting", {
            "marker": False, "account-pattern": False,
            "suffix": False, "exact": False,
        })
        diagnostic.observe("account-only", {
            "marker": True, "account-pattern": True,
            "suffix": False, "exact": False,
        })
        diagnostic.gate_end("timed-out")
        diagnostic.interrupt("sent-no-prompt")
        value = diagnostic.projection()
        c.installed_startup_diagnostic(value)
        self.assertEqual(value["shell_ready_gate"]["timeout_seconds"], 90)
        self.assertLessEqual(value["shell_ready_gate"]["samples"], 46)
        self.assertEqual(value["shell_ready_gate"]["signal_samples"], [
            {"marker": False, "account-pattern": False,
             "suffix": False, "exact": False},
            {"marker": True, "account-pattern": True,
             "suffix": False, "exact": False},
        ])
        self.assertEqual(value["shell_ready_gate"]["signal_seen"],
                         {"marker": True, "account-pattern": True,
                          "suffix": False, "exact": False})
        self.assertEqual(value["shell_ready_gate"]["signal_final"],
                         value["shell_ready_gate"]["signal_samples"][-1])
        forged = copy.deepcopy(value)
        forged["shell_ready_gate"]["private_ocr"] = "do not export"
        with self.assertRaises(c.Invalid):
            c.installed_startup_diagnostic(forged)
        forged = copy.deepcopy(value)
        forged["post_failure_interrupt"] = "guest-selected"
        with self.assertRaises(c.Invalid):
            c.installed_startup_diagnostic(forged)
        forged = copy.deepcopy(value)
        forged["shell_ready_gate"]["signal_samples"][0]["raw_ocr"] = "private"
        with self.assertRaises(c.Invalid):
            c.installed_startup_diagnostic(forged)
        forged = copy.deepcopy(value)
        forged["shell_ready_gate"]["signal_seen"]["suffix"] = True
        with self.assertRaises(c.Invalid):
            c.installed_startup_diagnostic(forged)

    def test_installed_signal_samples_are_bounded_and_fit_failure_projection(self):
        diagnostic = automation.InstalledStartupDiagnostic()
        diagnostic.start()
        diagnostic.login_observed()
        diagnostic.authentication_sent()
        diagnostic.fetch_observed()
        diagnostic.dismissal_sent()
        diagnostic.gate_start()
        empty = {"marker": False, "account-pattern": False,
                 "suffix": False, "exact": False}
        for _ in range(46):
            diagnostic.observe("ocr-empty", empty)
        with self.assertRaisesRegex(c.Invalid, "installed startup signals differ"):
            diagnostic.observe("ocr-empty", empty)
        diagnostic.gate_end("timed-out")
        diagnostic.interrupt("sent-no-prompt")
        value = diagnostic.projection()
        c.installed_startup_diagnostic(value)
        self.assertLess(len(json.dumps(value).encode()), 32_768)

    def test_installed_proof_timeout_interrupts_only_after_failure_and_never_types_secret(self):
        operations = []

        def wait(_stage, expectation, phrases=(), **kwargs):
            operations.append(("screen", expectation, phrases, kwargs))
            if expectation == "installed-shell-ready":
                raise automation.InstalledShellReadyTimeout(
                    "controller screen expectation installed-shell-ready absent")
            return None, ""

        def press(_stage, *names, **_kwargs):
            operations.append(("keys", names))

        def press_held(_stage, *names, **_kwargs):
            operations.append(("held-keys", names))

        def text(_stage, command_id, _value, **_kwargs):
            operations.append(("text", command_id))

        self.controller.wait_screen = wait
        self.controller.press = press
        self.controller.press_held = press_held
        self.controller.type_text = text
        self.controller.type_secret = mock.Mock()
        with mock.patch.object(automation.time, "sleep"), self.assertRaisesRegex(
                automation.InstalledShellReadyTimeout, "installed-shell-ready absent"):
            self.controller.boot_installed_and_start()
        timeout_at = operations.index((
            "screen", "installed-shell-ready",
            ("ARCTIC-SHOWCASE-SHELL-READY", "arcticshowcase@arctic-showcase"),
            {"seconds": 90, "exact_output": True, "ordered": True,
             "prompt_contract": ("arcticshowcase@arctic-showcase", ("~>", "~ >"))},
        ))
        self.assertEqual(operations[timeout_at + 1], ("held-keys", ("ctrl-c",)))
        self.assertEqual(operations[timeout_at + 2][1], "installed-diagnostic-shell-ready")
        self.assertIn(("text", "installed-shell-proof"), operations)
        self.controller.type_secret.assert_called_once_with("installed-console")
        self.assertEqual(self.controller.installed_startup.interrupt_status,
                         "recovered-prompt")

    def test_shell_proof_typed_bytes_do_not_contain_the_required_ocr_marker(self):
        self.assertNotIn("ARCTIC-SHOWCASE-SHELL-READY", automation.Controller.SHELL_PROOF)
        prefix, rendered_command = automation.Controller.SHELL_PROOF.rsplit("printf ", 1)
        self.assertEqual(prefix, (
            "function fish_prompt; set_color brwhite; "
            "printf 'arcticshowcase@arctic-showcase ~> '; "
            "set_color normal; end; "
        ))
        self.assertNotIn("set -U", prefix)
        self.assertNotIn("funcsave", prefix)
        self.assertNotIn("functions --copy", prefix)
        account = (c.CONTROLLER["account"]["username"] + "@"
                   + c.CONTROLLER["account"]["hostname"])
        self.assertEqual(prefix.count(account), 1)
        self.assertIn(account + " " + c.CONTROLLER["account"]["prompt"]["rendered"],
                      prefix)
        rendered = subprocess.run(
            ["/bin/sh", "-c", "printf " + rendered_command],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, timeout=5, check=True,
        )
        self.assertEqual(rendered.stderr, b"")
        self.assertEqual(
            rendered.stdout,
            b"\x1b[2J\x1b[H\x1b[1mARCTIC-SHOWCASE-SHELL-READY\x1b[0m\n",
        )

    def test_shell_proof_and_final_prompt_gate_precede_sudo_launcher(self):
        self.controller.wait_screen = mock.Mock(return_value=(None, ""))
        self.controller.press = mock.Mock()
        self.controller.type_text = mock.Mock()
        self.controller.type_secret = mock.Mock()
        with mock.patch.object(automation.time, "sleep"):
            self.controller.boot_installed_and_start()

        ready = [call for call in self.controller.wait_screen.call_args_list
                 if call.args[1] == "installed-shell-ready"]
        shell = [call for call in self.controller.wait_screen.call_args_list
                 if call.args[1] == "installed-shell"]
        self.assertEqual((len(ready), len(shell)), (1, 1))
        prompt = (c.CONTROLLER["account"]["username"] + "@"
                  + c.CONTROLLER["account"]["hostname"])
        self.assertEqual(ready[0].args[2],
                         ("ARCTIC-SHOWCASE-SHELL-READY", prompt))
        self.assertEqual(ready[0].kwargs,
                         {"seconds": 90, "exact_output": True, "ordered": True,
                          "prompt_contract": (prompt, ("~>", "~ >"))})
        self.assertEqual(shell[0].args[2], ("ARCTIC-SHOWCASE-SHELL-READY", prompt))
        self.assertEqual(shell[0].kwargs,
                         {"seconds": 90, "exact_output": True, "ordered": True,
                          "prompt_contract": (prompt, ("~>", "~ >"))})
        proof = [call for call in self.controller.type_text.call_args_list
                 if call.args[1] == "installed-shell-proof"]
        self.assertEqual(len(proof), 1)
        self.assertEqual(proof[0].args[2], automation.Controller.SHELL_PROOF)
        self.assertEqual(proof[0].kwargs, {"gap": .08})
        self.assertFalse(all(phrase.casefold()
                             in "ARCTIC-SHOWCASE-SHELL-READY".casefold()
                             for phrase in shell[0].args[2]))

    def test_preproof_prompt_gate_rejects_realistic_full_fetch_greeting(self):
        account = "arcticshowcase@arctic-showcase"
        greeting = """\
arcticshowcase@arctic-showcase
------------------------------
os       Arctic Linux 1.2.1
base     Fedora 44
kernel   Linux 7.2.10
wm       Mango
shell    fish 4.6
term     linux
theme    Polar night
uptime   2 mins
"""
        suffixes = ("~>", "~ >")
        self.assertFalse(automation._fixed_fish_prompt_present(
            greeting, account, suffixes))
        # Account text and a valid suffix on different rows cannot mimic one
        # complete final prompt line.
        self.assertFalse(automation._fixed_fish_prompt_present(
            greeting + account + "\n~ >\n", account, suffixes))
        # A prompt-like row inside a still-active greeting is not the final OCR
        # row and therefore cannot authorize input.
        self.assertFalse(automation._fixed_fish_prompt_present(
            greeting + account + " ~>\nos       Arctic Linux 1.2.1\n", account, suffixes))
        for forged in ("other@arctic-showcase ~>", account + "~>",
                       account + " ~>>", account + " ~> command",
                       "prefix " + account + " ~>"):
            with self.subTest(forged=forged):
                self.assertFalse(automation._fixed_fish_prompt_present(
                    forged + "\n", account, suffixes))
        for spelling in suffixes:
            with self.subTest(spelling=spelling):
                self.assertTrue(automation._fixed_fish_prompt_present(
                    greeting + "\n" + account + " " + spelling + "\n",
                    account, suffixes))
                self.assertTrue(automation._fixed_fish_prompt_present(
                    account + " " + spelling + " _|\n", account, suffixes))
        for observed in (
            "arcticshowcase @ arctic-showcase ~>",
            "arcticshowcase@arctic - showcase ~ >",
            "arcticshowcase  @  arctic  -  showcase   ~  >",
        ):
            with self.subTest(observed=observed):
                self.assertTrue(automation._fixed_fish_prompt_present(
                    observed + "\n", account, suffixes))
        for rejected in (
            "arctic show case@arctic-showcase ~>",
            "arcticshowcase@arct1c-showcase ~>",
            "arcticshowcase@arctic-showcas3 ~>",
            "other@arctic-showcase ~>",
            "arcticshowcase@arctic-showcase $>",
            "ARCTIC-SHOWCASE-PROBE-READY updates",
            account + " ~>\nARCTIC-SHOWCASE-PROBE-READY updates",
        ):
            with self.subTest(rejected=rejected):
                self.assertFalse(automation._fixed_fish_prompt_present(
                    rejected + "\n", account, suffixes))

    def test_fixed_shell_proof_accepts_only_marker_before_real_account(self):
        marker = "ARCTIC-SHOWCASE-SHELL-READY"
        prompt = "arcticshowcase@arctic-showcase"
        suffixes = ("~>", "~ >")
        old_prompt_only = prompt + " ~> printf octal-marker\n" + marker
        returned_prompt = old_prompt_only + "\n" + prompt + " ~>"
        spaced = "ARCTIC - SHOWCASE- SHELL -READY\n" + prompt + " ~>"
        punctuation_spaced = ("ARCTIC - SHOWCASE- SHELL -READY\n"
                              "arcticshowcase @ arctic - showcase ~ >")
        self.assertFalse(automation._fixed_shell_proof_present(
            old_prompt_only, prompt, suffixes))
        self.assertTrue(automation._fixed_shell_proof_present(
            returned_prompt, prompt, suffixes))
        self.assertTrue(automation._fixed_shell_proof_present(
            spaced, prompt, suffixes))
        self.assertTrue(automation._fixed_shell_proof_present(
            punctuation_spaced, prompt, suffixes))
        for forged in (
            "ARCTIC SHOWCASE SHELL READY\n" + prompt,
            "ARCTIC-SHOWCASE-SHELL-READY extra\n" + prompt,
            "ARCTIC-SHOWCASE-SHELL-WRONG\n" + prompt,
            marker + "\nother@arctic-showcase ~>",
            marker + "\n" + prompt + " ~>\ntrailing guest signal",
            marker + "\nARCTIC-SHOWCASE-PROBE-READY updates",
        ):
            with self.subTest(forged=forged):
                self.assertFalse(automation._fixed_shell_proof_present(
                    forged, prompt, suffixes))

    def test_installed_shell_gate_uses_focused_ocr_and_fixed_marker_spacing(self):
        prompt = "arcticshowcase@arctic-showcase"
        source = Image.new("RGB", (1280, 800), "black")
        source.putpixel((10, 12), (255, 255, 255))
        self.qmp.screendump = lambda path: source.save(path)
        self.controller.ocr = lambda _path: (
            "ARCTIC - SHOWCASE - SHELL - READY\n"
            "arcticshowcase @ arctic - showcase ~ >")
        self.controller.shell_focus_ocr = self.controller.ocr
        path, text = self.controller.wait_screen(
            "installed-console", "installed-shell-ready",
            ("ARCTIC-SHOWCASE-SHELL-READY", prompt), seconds=1,
            exact_output=True, ordered=True,
            prompt_contract=(prompt, ("~>", "~ >")))
        self.assertIsNone(path)
        self.assertEqual(text.splitlines()[-1],
                         "arcticshowcase @ arctic - showcase ~ >")
        self.assertEqual(list(self.root.glob("controller-*.png")), [])

    def test_installed_sudo_proof_is_executed_not_typed_and_invalidates_cache(self):
        marker = "ARCTIC-SHOWCASE-AUTH-READY"
        self.assertNotIn(marker, automation.Controller.INSTALLED_COMMAND)
        self.assertNotIn(automation.Controller.PASSWORD, automation.Controller.INSTALLED_COMMAND)
        self.assertIn("exec sudo -k sh -c", automation.Controller.INSTALLED_COMMAND)
        prefix = automation.Controller.INSTALLED_COMMAND.split("; exec sudo", 1)[0]
        rendered = subprocess.run(["/bin/sh", "-c", prefix], stdin=subprocess.DEVNULL,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=5, check=True)
        self.assertEqual(rendered.stdout.decode(), marker + ": ")
        self.controller.wait_screen = mock.Mock(return_value=(None, ""))
        self.controller.press = mock.Mock()
        self.controller.type_text = mock.Mock()
        self.controller.type_secret = mock.Mock()
        with mock.patch.object(automation.time, "sleep"):
            self.controller.boot_installed_and_start()
        sudo = [call for call in self.controller.wait_screen.call_args_list
                if call.args[1] == "installed-sudo-password"]
        self.assertEqual(len(sudo), 1)
        self.assertEqual(sudo[0].args[2], (marker, "password"))
        self.controller.type_secret.assert_called_with("installed-console")

    def test_installed_shell_completes_empty_handoff_before_nonsecret_proof(self):
        operations = []

        def wait(_stage, expectation, phrases=(), **kwargs):
            operations.append(("screen", expectation, phrases, kwargs))
            return None, ""

        def press(_stage, *names, **_kwargs):
            operations.append(("keys", names))

        def press_held(_stage, *names, **_kwargs):
            operations.append(("held-keys", names))

        def text(_stage, command_id, _value, **_kwargs):
            operations.append(("text", command_id))

        def secret(_stage):
            operations.append(("secret",))

        self.controller.wait_screen = wait
        self.controller.press = press
        self.controller.press_held = press_held
        self.controller.type_text = text
        self.controller.type_secret = secret
        with mock.patch.object(automation.time, "sleep",
                               side_effect=lambda seconds: operations.append(
                                   ("sleep", seconds))):
            self.controller.boot_installed_and_start()

        greeting = ("screen", "installed-fetch-greeting", ("Arctic Linux", "fish 4.6"),
                    {"seconds": 90})
        ready = ("screen", "installed-shell-ready",
                 ("ARCTIC-SHOWCASE-SHELL-READY",
                  "arcticshowcase@arctic-showcase"),
                 {"seconds": 90, "exact_output": True, "ordered": True,
                      "prompt_contract": ("arcticshowcase@arctic-showcase",
                                          ("~>", "~ >"))})
        proof = ("text", "installed-shell-proof")
        at = operations.index(greeting)
        self.assertEqual(operations[at + 1], ("held-keys", ("ret",)))
        self.assertEqual(operations[at + 2], ("sleep", 3))
        self.assertEqual(operations[at + 3], proof)
        self.assertEqual(operations[at + 4], ("keys", ("ret",)))
        self.assertEqual(operations[at + 5], ready)
        self.assertNotIn(("held-keys", ("ctrl-l",)), operations)
        self.assertEqual(operations[at + 1:at + 5].count(("held-keys", ("ret",))), 1)
        self.assertLess(operations.index(("secret",)), at)
        self.assertEqual(operations[at + 6],
                         ("screen", "installed-shell",
                          ("ARCTIC-SHOWCASE-SHELL-READY",
                           "arcticshowcase@arctic-showcase"),
                          {"seconds": 90, "exact_output": True, "ordered": True,
                           "prompt_contract": ("arcticshowcase@arctic-showcase",
                                               ("~>", "~ >"))}))
        self.assertEqual(operations[at + 7], ("text", "installed-scenes"))


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
        selected = next(index for index, event in enumerate(value["events"])
                        if event["kind"] == "screen"
                        and event["detail"].get("expectation") == "install-boot-menu-selected")
        welcome = next(index for index, event in enumerate(value["events"])
                       if event["kind"] == "screen"
                       and event["detail"].get("expectation") == "live-installer-visible")
        value["events"][selected], value["events"][welcome] = (
            value["events"][welcome], value["events"][selected])
        for index, event in enumerate(value["events"]):
            event["index"] = index
        with self.assertRaises(c.Invalid):
            c.controller_trace(value)

    def test_enter_before_install_selection_proof_is_rejected(self):
        value = controller_trace()
        selected = next(index for index, event in enumerate(value["events"])
                        if event["kind"] == "screen"
                        and event["detail"].get("expectation") == "install-boot-menu-selected")
        enter = next(index for index, event in enumerate(value["events"])
                     if event["stage"] == "live-boot" and event["kind"] == "keys"
                     and event["detail"] == {"names": ["ret"]})
        value["events"][selected], value["events"][enter] = (
            value["events"][enter], value["events"][selected])
        for index, event in enumerate(value["events"]):
            event["index"] = index
        with self.assertRaisesRegex(c.Invalid, "boot selection proof sequence"):
            c.controller_trace(value)


class GuestAutomation(unittest.TestCase):
    @staticmethod
    def _ipc_process(root, pid, *, argv, executable="/usr/bin/quickshell",
                     comm="quickshell"):
        process = root / str(pid)
        process.mkdir()
        (process / "comm").write_text(comm + "\n")
        (process / "exe").symlink_to(executable)
        (process / "cmdline").write_bytes(
            b"/usr/bin/quickshell\0" + b"\0".join(value.encode() for value in argv) + b"\0")
        # proc_pid_stat fields 3..22; index 19 below is starttime.
        (process / "stat").write_text(
            f"{pid} (quickshell) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 {1000 + int(pid)}\n")
        return process

    def test_ipc_discovery_selects_one_stable_exact_packaged_process(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._ipc_process(root, 101, argv=["-p", "/usr/share/arctic/installer-ui"])
            self._ipc_process(root, 102, argv=["-p", "/usr/share/arctic/shell"])
            account = types.SimpleNamespace(pw_uid=os.getuid(), pw_name="fixture")
            result = types.SimpleNamespace(returncode=0, stdout=b'{"page":"welcome"}\n')
            with mock.patch.object(unattended, "_as_user", return_value=result) as invoke:
                self.assertEqual(unattended._find_ipc(
                    account, {}, "installer", "state", root),
                    ("101", '{"page":"welcome"}'))
            self.assertEqual(invoke.call_args.kwargs["timeout"], 15)
            self.assertEqual(invoke.call_args.args[2][3:5], ["101", "call"])

            self._ipc_process(root, 103, argv=["-p", "/usr/share/arctic/installer-ui"])
            with mock.patch.object(unattended, "_as_user") as ambiguous:
                with self.assertRaises(unattended.InstallerIpcFailure) as caught:
                    unattended._find_ipc(account, {}, "installer", "state", root)
                self.assertEqual(caught.exception.reason, "installer-process-ambiguous")
                ambiguous.assert_not_called()

    def test_ipc_diagnostic_distinguishes_absent_ambiguous_and_call_failure(self):
        account = types.SimpleNamespace(pw_uid=os.getuid(), pw_name="fixture")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaises(unattended.InstallerIpcFailure) as absent:
                unattended._find_ipc(account, {}, "installer", "state", root)
            self.assertEqual(absent.exception.reason, "installer-process-absent")

            self._ipc_process(root, 101, argv=["-p", "/usr/share/arctic/installer-ui"])
            failed = types.SimpleNamespace(returncode=1, stdout=b"private failure text")
            with mock.patch.object(unattended, "_as_user", return_value=failed), \
                 self.assertRaises(unattended.InstallerIpcFailure) as call:
                unattended._find_ipc(account, {}, "installer", "state", root)
            self.assertEqual(call.exception.reason, "installer-ipc-call-failed")
            self.assertNotIn("private failure text", str(call.exception))

    def test_ipc_discovery_rejects_identity_change_during_bounded_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            process = self._ipc_process(
                root, 201, argv=["-p", "/usr/share/arctic/installer-ui"])
            account = types.SimpleNamespace(pw_uid=os.getuid(), pw_name="fixture")

            def replace(*_args, **_kwargs):
                stat_path = process / "stat"
                stat_path.write_text(stat_path.read_text().replace("1201\n", "1202\n"))
                return types.SimpleNamespace(returncode=0, stdout=b'{}\n')

            with mock.patch.object(unattended, "_as_user", side_effect=replace):
                with self.assertRaises(unattended.InstallerIpcFailure) as caught:
                    unattended._find_ipc(account, {}, "installer", "state", root)
            self.assertEqual(caught.exception.reason, "installer-ipc-call-failed")

    def test_installer_readiness_requires_same_endpoint_twice(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")
        ready = {"page": "welcome", "current": "welcome", "ready": True,
                 "connected": True, "busy": False, "failure": ""}
        samples = iter([(("101", 10), ready), (("202", 20), ready),
                        (("202", 20), ready)])
        with mock.patch.object(unattended, "_installer_state",
                               side_effect=lambda *_args: next(samples)), \
             mock.patch.object(unattended.time, "sleep"):
            self.assertEqual(unattended._stable_installer_endpoint(account, {}),
                             ("202", 20))

    def test_ipc_diagnostic_distinguishes_invalid_response_and_never_ready(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")
        with mock.patch.object(unattended, "_find_ipc",
                               return_value=("101", "private malformed response")):
            with self.assertRaises(unattended.InstallerIpcFailure) as invalid:
                unattended._installer_endpoint(account, {})
        self.assertEqual(invalid.exception.reason, "installer-ipc-response-invalid")
        self.assertNotIn("private malformed response", str(invalid.exception))

        not_ready = {"page": "welcome", "current": "welcome", "ready": False,
                     "connected": True, "busy": False, "failure": ""}
        def once(function, _seconds, message):
            self.assertIsNone(function())
            raise c.Invalid(message)
        with mock.patch.object(unattended, "_installer_state",
                               return_value=(("101", 10), not_ready)), \
             mock.patch.object(unattended, "_wait", side_effect=once), \
             self.assertRaises(unattended.InstallerIpcFailure) as never:
            unattended._stable_installer_endpoint(account, {})
        self.assertEqual(never.exception.reason, "installer-never-ready")

        with mock.patch.object(unattended, "_installer_state",
                               side_effect=c.Invalid("private invalid detail")), \
             mock.patch.object(unattended, "_wait", side_effect=once), \
             self.assertRaises(unattended.InstallerIpcFailure) as invalid_sample:
            unattended._stable_installer_endpoint(account, {})
        self.assertEqual(invalid_sample.exception.reason,
                         "installer-ipc-response-invalid")
        self.assertNotIn("private invalid detail", str(invalid_sample.exception))

    def test_second_state_call_preserves_call_failure_and_rejects_non_object(self):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser")
        with mock.patch.object(unattended, "_installer_endpoint",
                               return_value=("101", 10)), \
             mock.patch.object(unattended, "_as_user",
                               side_effect=c.Invalid("private command failure")), \
             self.assertRaises(unattended.InstallerIpcFailure) as call:
            unattended._installer_state(account, {})
        self.assertEqual(call.exception.reason, "installer-ipc-call-failed")
        self.assertNotIn("private command failure", str(call.exception))

        with mock.patch.object(unattended, "_installer_endpoint",
                               return_value=("101", 10)), \
             mock.patch.object(unattended, "_installer_call", return_value="[]"), \
             self.assertRaises(unattended.InstallerIpcFailure) as invalid:
            unattended._installer_state(account, {})
        self.assertEqual(invalid.exception.reason, "installer-ipc-response-invalid")

    def test_installer_ipc_failure_exports_only_closed_reason(self):
        rows = []

        class Channel:
            def __init__(self, *args, **kwargs): pass
            def write(self, value): rows.append(value)
            def close(self): pass

        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser",
                                        pw_dir="/home/liveuser")
        failure = unattended.InstallerIpcFailure("installer-process-absent")
        with mock.patch.object(unattended.os, "geteuid", return_value=0), \
             mock.patch.object(unattended, "Channel", Channel), \
             mock.patch.object(unattended, "_graphical_environment",
                               return_value=(account, 2, {})), \
             mock.patch.object(unattended, "_run"), \
             mock.patch.object(unattended, "_stable_installer_endpoint",
                               side_effect=failure), \
             self.assertRaises(unattended.InstallerIpcFailure):
            unattended.live_install(600)
        progress = [c.strict_json(row[len(c.INSTALL_PROGRESS_PREFIX):]) for row in rows]
        self.assertEqual(progress[-1], {
            "schema": "arctic-showcase-install-progress-v1", "sequence": 5,
            "stage": "installer-ipc", "status": "failed",
            "failure_reason": "installer-process-absent", "release_acceptance": False,
        })
        c.install_progress(progress[-1])
        self.assertNotIn("private", repr(progress))

        for reason in c.INSTALLER_IPC_FAILURE_REASONS:
            changed = dict(progress[-1], failure_reason=reason)
            c.install_progress(changed)
        for forged in (
            dict(progress[-1], failure_reason="guest-selected"),
            dict(progress[-1], stage="page-welcome"),
            dict(progress[-1], status="passed"),
        ):
            with self.assertRaises(c.Invalid):
                c.install_progress(forged)

    def _run_installer(self, pages):
        account = types.SimpleNamespace(pw_uid=1000, pw_name="liveuser", pw_dir="/home/liveuser")
        index = {"value": 0}
        fills = []
        filled = set()
        channel_rows = []

        def ipc(_account, _environment, _pid, method, payload=None):
            if method == "state":
                page = pages[index["value"]]
                return json.dumps({"page": page, "current": page, "ready": True,
                                   "connected": True, "busy": False, "failure": "",
                                   # Reproduce the exact-image race: Welcome
                                   # can be ready before its suggested locale
                                   # makes the page valid.
                                   "valid": page != "welcome" or page in filled,
                                   "percent": 100 if page == "done" else 0})
            if method == "fill":
                fills.append((pages[index["value"]], payload))
                filled.add(pages[index["value"]])
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
             mock.patch.object(unattended, "_installer_endpoint", return_value=("123", 456)), \
             mock.patch.object(unattended, "_process_start_ticks", return_value=456), \
             mock.patch.object(unattended, "_stable_installer_endpoint",
                               return_value=("123", 456)), \
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
        self.assertEqual(choices["welcome"], {"language": "en_US.UTF-8"})
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
                c.Invalid("private capture channel timed out"), None,
                automation.LiveStartupDiagnostic().projection(),
                automation.InstalledStartupDiagnostic().projection())
            self.assertLessEqual(path.stat().st_size, 32768)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            value = c.strict_json(path.read_bytes())
            c.capture_failure(value)
            self.assertEqual(value["failure_code"], "private-channel-timeout")
            self.assertEqual(value["live_startup"]["release_acceptance"], False)
            self.assertEqual(value["installed_startup"]["release_acceptance"], False)
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
