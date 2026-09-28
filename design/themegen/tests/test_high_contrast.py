"""High contrast (Settings > Accessibility): derive.high_contrast over every theme Arctic ships,
and arctic-theme contrast on|off linking the active theme's high-contrast take.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import glob
import json
import os
import shutil
import sys
import tempfile
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DESIGN)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from themegen import color, derive, named, palette, render  # noqa: E402

GALLERY = sorted(glob.glob(os.path.join(DESIGN, "themes", "*", "colors.toml")))


def gallery(path):
    name = os.path.basename(os.path.dirname(path))
    with open(path, encoding="utf-8") as f:
        return named.from_colors(named.load_colors(f.read(), path), name)


def shipped():
    out = {name: palette.builtin(name) for name in ("winter", "polar-night")}
    for path in GALLERY:
        out[os.path.basename(os.path.dirname(path))] = gallery(path)
    return out


class EngineTests(unittest.TestCase):
    def test_every_shipped_theme_has_a_high_contrast_take(self):
        for name, p in shipped().items():
            with self.subTest(name):
                hc = derive.high_contrast(p)
                c, before = hc["colors"], p["colors"]
                self.assertEqual(derive.check(hc), [])
                self.assertEqual(derive.check_high_contrast(hc), [])
                self.assertEqual(hc["contrast"], "high")
                self.assertEqual(hc["mode"], p["mode"])
                # Two surface steps and opaque glass.
                self.assertEqual(c["surface"], c["ground"])
                self.assertEqual(c["surface-sunken"], c["ground"])
                self.assertEqual(color.alpha_of(c["frost"]), 255)
                # "Here" keeps its hue (amber stays amber); ink is at least as strong as before.
                self.assertLess(color.hue_diff(color.hex_to_oklch(c["accent"])[2],
                                               color.hex_to_oklch(before["accent"])[2]), 8)
                self.assertGreaterEqual(color.contrast(c["ink"], c["ground"]), 12)
                self.assertGreaterEqual(color.contrast(c["line"], c["ground"]), 4.5)
                self.assertNotIn("contrast", p)          # the palette it came from is untouched

    def test_theme_json_says_so_only_when_high(self):
        with tempfile.TemporaryDirectory() as out:
            render.render(palette.builtin("winter"), os.path.join(out, "normal"))
            render.render(derive.high_contrast(palette.builtin("winter")), os.path.join(out, "high"))
            with open(os.path.join(out, "normal", "theme.json"), encoding="utf-8") as f:
                self.assertNotIn("contrast", json.load(f))
            with open(os.path.join(out, "high", "theme.json"), encoding="utf-8") as f:
                self.assertEqual(json.load(f)["contrast"], "high")


try:
    import test_arctic_theme as base      # the module: its TestCase would be collected here too
except ImportError:  # pragma: no cover
    base = None


@unittest.skipIf(base is None or base.Image is None, "Pillow (python3-pillow) is not installed")
@unittest.skipIf(shutil.which("bash") is None, "bash is needed")
class ContrastSwitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.share_tmp = tempfile.TemporaryDirectory()
        cls.share = os.path.join(cls.share_tmp.name, "share", "arctic")
        for name in ("winter", "polar-night"):
            render.render(palette.builtin(name), os.path.join(cls.share, "themes", name))
        for path in GALLERY:
            if os.path.basename(os.path.dirname(path)) == "nord":
                render.render(gallery(path), os.path.join(cls.share, "themes-extra", "nord"))
        os.makedirs(os.path.join(cls.share, "theme-hooks.d"))

    @classmethod
    def tearDownClass(cls):
        cls.share_tmp.cleanup()

    def setUp(self):
        base.ArcticThemeTests.setUp(self)
        self.state = os.path.join(self.root, "state")
        self.env["XDG_STATE_HOME"] = self.state

    def tearDown(self):
        base.ArcticThemeTests.tearDown(self)

    def theme(self, *args, ok=True):
        return base.ArcticThemeTests.theme(self, *args, ok=ok)

    def current(self):
        return base.ArcticThemeTests.current(self)

    def linked(self):
        return base.ArcticThemeTests.linked(self)

    def theme_json(self):
        with open(os.path.join(self.config, "current", "theme.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_on_follows_the_theme_and_off_goes_back(self):
        self.assertEqual(self.theme("contrast").stdout.strip(), "off")
        out = json.loads(self.theme("contrast", "on", "--json").stdout)
        self.assertEqual(out, {"ok": True, "contrast": "high"})
        hc = os.path.join(self.state, "arctic", "themes-hc")
        self.assertEqual(self.linked(), os.path.join(hc, "polar-night"))
        self.assertEqual(self.theme_json()["contrast"], "high")
        self.assertEqual(self.current()["name"], "polar-night")
        self.assertEqual(self.current()["contrast"], "high")
        with open(self.log, encoding="utf-8") as f:
            self.assertIn("org.gnome.desktop.a11y.interface high-contrast true", f.read())
        # Switching themes keeps it: the gallery theme and light/dark too.
        self.theme("set", "nord")
        self.assertEqual(self.linked(), os.path.join(hc, "nord"))
        self.theme("light")
        self.assertEqual(self.linked(), os.path.join(hc, "winter"))
        self.assertEqual(self.current()["mode"], "light")
        # Made once: a second switch keeps the folder as it is.
        stamp = os.stat(os.path.join(hc, "winter", "theme.json")).st_mtime_ns
        self.theme("reload")
        self.theme("set", "winter")
        self.assertEqual(os.stat(os.path.join(hc, "winter", "theme.json")).st_mtime_ns, stamp)
        self.theme("contrast", "toggle")
        self.assertEqual(self.linked(), os.path.join(self.share, "themes", "winter"))
        self.assertNotIn("contrast", self.theme_json())
        self.assertEqual(self.theme("contrast").stdout.strip(), "off")
        self.assertEqual(self.theme("contrast", "loud", ok=False).returncode, 2)


if __name__ == "__main__":
    unittest.main()
