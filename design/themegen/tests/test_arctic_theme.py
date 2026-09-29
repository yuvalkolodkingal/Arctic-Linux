"""arctic-theme and arctic-wallpaper (dotfiles/.local/bin) against the engine, in a throwaway
home with fake gsettings / pkill / makoctl / mmsg / arctic-shell-ipc that log their calls.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(DESIGN)
BIN = os.path.join(REPO, "dotfiles", ".local", "bin")
sys.path.insert(0, DESIGN)

from themegen import palette, render  # noqa: E402

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None

FAKES = {
    "gsettings": 'echo "gsettings $*" >> "$ARCTIC_TEST_LOG"; [ "$1" = get ] && echo "\'adw-gtk3-dark\'"; exit 0',
    "pkill": 'echo "pkill $*" >> "$ARCTIC_TEST_LOG"; exit 1',
    "makoctl": 'echo "makoctl $*" >> "$ARCTIC_TEST_LOG"',
    "mmsg": 'echo "mmsg $*" >> "$ARCTIC_TEST_LOG"; echo \'{"success":true}\'',
    "arctic-shell-ipc": 'echo "arctic-shell-ipc $*" >> "$ARCTIC_TEST_LOG"',
    "swaybg": 'exit 0',
}
REDRAW_STUB = 'echo "arctic-wallpaper $*" >> "$ARCTIC_TEST_LOG"'


def write_exec(path, body, shebang="#!/bin/sh"):
    with open(path, "w") as f:
        f.write(shebang + "\n" + body + "\n")
    os.chmod(path, os.stat(path).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


@unittest.skipIf(Image is None, "Pillow (python3-pillow) is not installed")
@unittest.skipIf(shutil.which("bash") is None, "bash is needed")
class ArcticThemeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # The packaged static themes, rendered once.
        cls.share_tmp = tempfile.TemporaryDirectory()
        cls.share = os.path.join(cls.share_tmp.name, "share", "arctic")
        for name in ("winter", "polar-night"):
            render.render(palette.builtin(name), os.path.join(cls.share, "themes", name))
        os.makedirs(os.path.join(cls.share, "theme-hooks.d"))

    @classmethod
    def tearDownClass(cls):
        cls.share_tmp.cleanup()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.tmp.name
        self.root = root
        self.config = os.path.join(root, "config", "arctic")
        os.makedirs(self.config)
        self.fakes = os.path.join(root, "fakes")
        os.makedirs(self.fakes)
        for name, body in FAKES.items():
            write_exec(os.path.join(self.fakes, name), body)
        self.stubs = os.path.join(root, "stubs")        # a logging arctic-wallpaper for redraws
        os.makedirs(self.stubs)
        write_exec(os.path.join(self.stubs, "arctic-wallpaper"), REDRAW_STUB)
        write_exec(os.path.join(self.stubs, "arctic-theme"), 'exec "{}" "$@"'.format(os.path.join(BIN, "arctic-theme")))
        self.backgrounds = os.path.join(root, "backgrounds")
        os.makedirs(self.backgrounds)
        for stem, rgb in (("aurora-polar-night", (18, 23, 30)), ("aurora-winter", (238, 242, 245)),
                          ("fox-polar-night", (20, 25, 32)), ("fox-winter", (230, 236, 240))):
            Image.new("RGB", (32, 18), rgb).save(os.path.join(self.backgrounds, stem + ".png"))
        self.pictures = os.path.join(root, "pictures")
        os.makedirs(self.pictures)
        self.sea = os.path.join(self.pictures, "sea.png")            # dark, blue
        Image.new("RGB", (64, 36), (10, 60, 120)).save(self.sea)
        self.dunes = os.path.join(self.pictures, "dunes.png")        # bright, orange
        Image.new("RGB", (64, 36), (250, 200, 140)).save(self.dunes)
        self.log = os.path.join(root, "log")
        open(self.log, "w").close()
        self.env = dict(
            os.environ, HOME=os.path.join(root, "home"), XDG_CONFIG_HOME=os.path.join(root, "config"),
            XDG_DATA_HOME=os.path.join(root, "data"), XDG_CACHE_HOME=os.path.join(root, "cache"),
            XDG_DATA_DIRS=os.path.join(root, "sysdata"),
            ARCTIC_DATA_DIR=self.share, ARCTIC_BACKGROUNDS_DIR=self.backgrounds,
            ARCTIC_THEMEGEN_DIR=os.path.join(DESIGN, "themegen"), ARCTIC_TEST_LOG=self.log,
            MANGO_INSTANCE_SIGNATURE="/nonexistent", ARCTIC_THEME_HOOK_TIMEOUT="1",
            PATH=os.pathsep.join([self.fakes, self.stubs, "/usr/bin", "/bin"]))
        self.env.pop("ARCTIC_THEMEGEN_DATA", None)
        for name in ("adw-gtk3", "adw-gtk3-dark"):     # installed, as the image has them
            os.makedirs(os.path.join(root, "sysdata", "themes", name, "gtk-3.0"))
        # A new account: current -> polar-night, as /etc/skel has it.
        os.symlink(os.path.join(self.share, "themes", "polar-night"), os.path.join(self.config, "current"))
        with open(os.path.join(self.config, "theme"), "w") as f:
            f.write("polar-night\n")

    def tearDown(self):
        self.tmp.cleanup()

    # -- helpers --
    def theme(self, *args, ok=True):
        r = subprocess.run([os.path.join(BIN, "arctic-theme")] + list(args), env=self.env,
                           capture_output=True, text=True, timeout=60)
        if ok:
            self.assertEqual(r.returncode, 0, "arctic-theme {}: {}".format(" ".join(args), r.stderr))
        return r

    def current(self):
        return json.loads(self.theme("current", "--json").stdout)

    def linked(self):
        return os.path.realpath(os.path.join(self.config, "current"))

    def calls(self):
        with open(self.log) as f:
            return f.read().splitlines()

    def settings(self):
        with open(os.path.join(self.config, "settings.json")) as f:
            return json.load(f)

    def choose(self, wallpaper):
        with open(os.path.join(self.config, "wallpaper"), "w") as f:
            f.write(wallpaper + "\n")

    # -- tests --
    def test_defaults(self):
        self.assertEqual(self.theme().stdout, "polar-night\n")
        info = self.current()
        self.assertEqual((info["name"], info["label"], info["mode"], info["source"]), ("polar-night", "Polar night", "dark", "system"))
        self.assertTrue(info["auto_colors"])                  # on for new accounts
        self.assertEqual(info["wallpaper_mode"], "auto")
        self.assertEqual(info["colors"]["accent"], "#f6bd55")
        self.assertEqual(self.theme("auto").stdout, "on\n")
        self.assertEqual(self.theme("mode").stdout, "auto\n")

    def test_set_static_theme_and_reload(self):
        r = self.theme("set", "winter")
        self.assertIn("auto colours are off", r.stderr)
        self.assertEqual(self.linked(), os.path.join(self.share, "themes", "winter"))
        self.assertEqual(os.readlink(os.path.join(self.config, "current")), os.path.join(self.share, "themes", "winter"))
        with open(os.path.join(self.config, "theme")) as f:
            self.assertEqual(f.read(), "winter\n")
        self.assertFalse(self.settings()["auto_colors"])
        calls = self.calls()
        uid = str(os.getuid())
        for expected in ("gsettings set org.gnome.desktop.interface color-scheme prefer-light",
                         "gsettings set org.gnome.desktop.interface gtk-theme adw-gtk3",
                         "mmsg dispatch reload_config", "pkill -USR1 -u {} -x kitty".format(uid),
                         "pkill -USR2 -u {} -x waybar".format(uid), "makoctl reload"):
            self.assertIn(expected, calls)
        for _ in range(50):          # the shell and wallpaper redraws run in the background
            if {"arctic-shell-ipc shell reload", "arctic-wallpaper "} <= set(self.calls()):
                break
            time.sleep(0.05)
        self.assertIn("arctic-shell-ipc shell reload", self.calls())
        self.assertIn("arctic-wallpaper ", self.calls())

    def test_same_gtk_theme_is_flipped_to_force_a_reload(self):
        self.theme("set", "polar-night")      # the fake gsettings reports adw-gtk3-dark already
        calls = [c for c in self.calls() if "gtk-theme" in c and c.startswith("gsettings set")]
        self.assertEqual(calls, ["gsettings set org.gnome.desktop.interface gtk-theme ",
                                 "gsettings set org.gnome.desktop.interface gtk-theme adw-gtk3-dark"])

    def test_plain_adwaita_without_adw_gtk3(self):
        shutil.rmtree(os.path.join(self.root, "sysdata"))
        self.theme("set", "winter")
        calls = [c for c in self.calls() if "gtk-theme" in c and c.startswith("gsettings set")]
        self.assertEqual(calls, ["gsettings set org.gnome.desktop.interface gtk-theme Adwaita"])

    def test_old_verbs_still_work(self):
        self.theme("winter")
        self.assertEqual(self.theme().stdout, "winter\n")
        self.theme("toggle")
        self.assertEqual(self.theme().stdout, "polar-night\n")
        self.theme("light")
        self.assertEqual(self.theme().stdout, "winter\n")
        self.theme("dark")
        self.assertEqual(self.theme().stdout, "polar-night\n")
        self.theme("apply")
        self.assertEqual(self.linked(), os.path.join(self.share, "themes", "polar-night"))
        self.assertEqual(self.theme("--help").returncode, 0)
        self.assertEqual(self.theme("nonsense", ok=False).returncode, 2)
        r = self.theme("set", "summer", ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown theme 'summer'", r.stderr)
        self.assertEqual(self.theme("set", "../../etc", ok=False).returncode, 2)

    def test_a_theme_of_your_own_wins_and_is_linked_relatively(self):
        mine = palette.builtin("winter")
        mine.update(name="mine", label="Mine")
        render.render(mine, os.path.join(self.config, "themes", "mine"))
        self.theme("set", "mine")
        self.assertEqual(os.readlink(os.path.join(self.config, "current")), os.path.join("themes", "mine"))
        names = {t["name"]: t for t in json.loads(self.theme("list", "--json").stdout)}
        self.assertEqual(set(names), {"winter", "polar-night", "mine"})
        self.assertTrue(names["mine"]["active"])
        self.assertEqual(names["mine"]["source"], "user")
        self.assertEqual(names["winter"]["swatches"]["accent"], "#efa637")
        self.assertIn("* mine\tMine\tlight\tuser", self.theme("list").stdout)

    def test_light_and_dark_come_back_to_a_theme_without_a_pair(self):
        # Like Nord or Tokyo Night: no light take, so Winter by day and the theme again at night.
        mine = palette.builtin("polar-night")
        mine.update(name="mine", label="Mine")
        render.render(mine, os.path.join(self.config, "themes", "mine"))
        self.theme("set", "mine")
        self.theme("light")
        self.assertEqual(self.theme().stdout, "winter\n")
        self.theme("dark")
        self.assertEqual(self.theme().stdout, "mine\n")
        self.theme("toggle")
        self.theme("toggle")
        self.assertEqual(self.theme().stdout, "mine\n")
        # Gone: Polar night again.
        self.theme("light")
        shutil.rmtree(os.path.join(self.config, "themes", "mine"))
        self.theme("dark")
        self.assertEqual(self.theme().stdout, "polar-night\n")

    def test_auto_colours_follow_your_pictures(self):
        self.choose(self.sea)
        self.theme("auto", "on")
        self.assertEqual(self.theme().stdout, "wallpaper\n")
        folder = os.path.join(self.config, "themes", "wallpaper")
        self.assertEqual(self.linked(), os.path.realpath(folder))
        with open(os.path.join(folder, "theme.json")) as f:
            tj = json.load(f)
        self.assertEqual((tj["id"], tj["dark"], tj["wallpaper"]), ("wallpaper", True, self.sea))
        info = self.current()
        self.assertEqual((info["mode"], info["base"], info["source"]), ("dark", "polar-night", "user"))
        # Up to date: a second sync changes nothing and tells nobody.
        before = len(self.calls())
        self.theme("sync")
        self.assertEqual(len(self.calls()), before)
        # A new picture: remade (bright -> light) and reloaded.
        self.choose(self.dunes)
        self.theme("sync", "--no-redraw")
        info = self.current()
        self.assertEqual((info["name"], info["mode"], info["base"]), ("wallpaper", "light", "winter"))
        self.assertNotEqual(info["colors"]["accent"], "#efa637")
        self.assertIn("makoctl reload", self.calls()[before:])
        self.assertNotIn("arctic-wallpaper ", self.calls()[before:])
        # Light / dark for wallpaper colours.
        self.theme("mode", "dark")
        info = self.current()
        self.assertEqual((info["name"], info["mode"]), ("wallpaper", "dark"))
        self.assertEqual(self.settings()["wallpaper_mode"], "dark")
        self.theme("toggle")
        self.assertEqual(self.current()["mode"], "light")
        self.assertEqual(self.settings()["wallpaper_mode"], "light")
        # Off: back to the static theme of the same mode.
        self.theme("auto", "off")
        self.assertEqual(self.theme().stdout, "winter\n")
        self.assertFalse(self.settings()["auto_colors"])

    def test_arctic_wallpapers_keep_the_design_palettes(self):
        self.choose("fox")
        self.theme("auto", "on")
        self.assertEqual(self.theme().stdout, "polar-night\n")      # first boot looks like the design
        self.assertFalse(os.path.exists(os.path.join(self.config, "themes", "wallpaper")))
        self.theme("mode", "light")
        self.assertEqual(self.theme().stdout, "winter\n")
        self.choose(os.path.join(self.backgrounds, "fox-polar-night.png"))  # a design file by path, too
        self.theme("mode", "auto")
        self.assertEqual(self.theme().stdout, "winter\n")
        # set wallpaper makes colours from the wallpaper anyway (an explicit request).
        self.theme("set", "wallpaper")
        self.assertEqual(self.theme().stdout, "wallpaper\n")

    def test_login_survives_a_broken_picture(self):
        broken = os.path.join(self.pictures, "broken.png")
        with open(broken, "wb") as f:
            f.write(b"not a picture")
        self.choose(broken)
        r = self.theme("apply")                 # auto colours on by default
        self.assertIn("keeping polar-night", r.stderr)
        self.assertEqual(self.linked(), os.path.join(self.share, "themes", "polar-night"))
        self.assertIn("makoctl reload", self.calls())
        r = self.theme("sync", ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("broken.png", r.stderr)

    def test_login_keeps_wallpaper_colours_when_the_picture_is_not_there_yet(self):
        pic = os.path.join(self.pictures, "usb-sea.png")
        shutil.copy(self.sea, pic)
        self.choose(pic)
        self.theme("sync")
        self.assertEqual(self.theme().stdout, "wallpaper\n")
        os.rename(pic, pic + ".away")             # its drive is not mounted yet
        r = self.theme("apply")
        self.assertIn("keeping its colours", r.stderr)
        self.assertEqual(self.theme().stdout, "wallpaper\n")
        self.assertEqual(self.linked(), os.path.join(self.config, "themes", "wallpaper"))
        self.theme("sync")
        self.assertEqual(self.theme().stdout, "wallpaper\n")
        self.theme("sync", "--force")             # asked for: Arctic's colours
        self.assertEqual(self.theme().stdout, "polar-night\n")

    def test_an_engine_update_remakes_the_wallpaper_theme(self):
        engine = os.path.join(self.root, "engine", "themegen")
        shutil.copytree(os.path.join(DESIGN, "themegen"), engine, ignore=shutil.ignore_patterns("tests", "__pycache__"))
        self.env.update(ARCTIC_THEMEGEN_DIR=engine, ARCTIC_THEMEGEN_DATA=DESIGN)
        self.choose(self.sea)
        self.theme("sync")
        palette_json = os.path.join(self.config, "themes", "wallpaper", "palette.json")
        with open(palette_json) as f:
            before = json.load(f)["source"]["fingerprint"]
        derive_py = os.path.join(engine, "derive.py")
        st = os.stat(derive_py)
        os.utime(derive_py, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))   # an RPM update of derive.py
        self.theme("sync")
        with open(palette_json) as f:
            self.assertNotEqual(json.load(f)["source"]["fingerprint"], before)

    def test_settings_keep_other_keys(self):
        with open(os.path.join(self.config, "settings.json"), "w") as f:
            json.dump({"other_app": {"x": 1}}, f)
        self.theme("auto", "off")
        self.assertEqual(self.settings(), {"other_app": {"x": 1}, "auto_colors": False})

    def test_hooks(self):
        out = os.path.join(self.root, "hook-out")
        system_hooks = os.path.join(self.share, "theme-hooks.d")
        user_hooks = os.path.join(self.config, "theme-hooks.d")
        os.makedirs(user_hooks)
        try:
            write_exec(os.path.join(system_hooks, "10-env"),
                       'echo "$ARCTIC_THEME_NAME $ARCTIC_THEME_MODE $ARCTIC_THEME_DIR" >> "{}"'.format(out))
            write_exec(os.path.join(system_hooks, "20-replaced"), 'echo system >> "{}"'.format(out))
            write_exec(os.path.join(user_hooks, "20-replaced"), 'echo user >> "{}"'.format(out))
            write_exec(os.path.join(user_hooks, "30-fails"), "exit 3")
            write_exec(os.path.join(user_hooks, "40-slow"), "sleep 30")
            write_exec(os.path.join(user_hooks, "50-after"), 'echo after >> "{}"'.format(out))
            with open(os.path.join(user_hooks, "60-not-executable"), "w") as f:
                f.write('#!/bin/sh\necho no >> "{}"\n'.format(out))
            t = time.monotonic()
            r = self.theme("set", "winter")
            self.assertLess(time.monotonic() - t, 15)
            self.assertIn("30-fails failed (exit 3)", r.stderr)
            self.assertIn("40-slow took longer", r.stderr)
            with open(out) as f:
                lines = f.read().splitlines()
            self.assertEqual(lines, ["winter light " + os.path.join(self.share, "themes", "winter"), "user", "after"])
        finally:
            for fn in os.listdir(system_hooks):
                os.unlink(os.path.join(system_hooks, fn))

    def test_hook_background_programs_do_not_hold_the_output(self):
        user_hooks = os.path.join(self.config, "theme-hooks.d")
        os.makedirs(user_hooks)
        write_exec(os.path.join(user_hooks, "10-daemon"), "sleep 30 &\necho started a daemon")
        t = time.monotonic()
        r = self.theme("reload")           # captured output: waits for EOF on arctic-theme's pipes
        self.assertLess(time.monotonic() - t, 5)
        self.assertIn("10-daemon: started a daemon", r.stderr)

    @unittest.skipUnless(shutil.which("setsid"), "arctic-wallpaper needs setsid (util-linux)")
    def test_arctic_wallpaper_switches_the_colours(self):
        env = dict(self.env, PATH=os.pathsep.join([self.fakes, BIN, "/usr/bin", "/bin"]))
        run = lambda *a: subprocess.run([os.path.join(BIN, "arctic-wallpaper")] + list(a), env=env,  # noqa: E731
                                        capture_output=True, text=True, timeout=60)
        r = run(self.dunes)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.theme().stdout, "wallpaper\n")
        self.assertEqual(self.current()["mode"], "light")
        with open(os.path.join(self.root, "cache", "arctic", "wallpaper-current")) as f:
            self.assertEqual(f.read().strip(), self.dunes)
        # An Arctic wallpaper: the static palette of the same mode, drawn in its variant.
        r = run("aurora")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.theme().stdout, "winter\n")
        with open(os.path.join(self.root, "cache", "arctic", "wallpaper-current")) as f:
            self.assertEqual(f.read().strip(), os.path.join(self.backgrounds, "aurora-winter.png"))
        # Auto colours off: the wallpaper changes, the colours don't.
        self.theme("auto", "off")
        r = run(self.sea)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.theme().stdout, "winter\n")


if __name__ == "__main__":
    unittest.main()
