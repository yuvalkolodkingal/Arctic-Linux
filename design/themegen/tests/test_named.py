"""The theme gallery: named palettes from design/themes/*/colors.toml (themegen/named.py), and
arctic-theme switching to them and between a pair.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DESIGN)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from themegen import color, derive, named, palette, render  # noqa: E402
from themegen.palette import ThemegenError  # noqa: E402

THEMES = sorted(glob.glob(os.path.join(DESIGN, "themes", "*", "colors.toml")))


def build(path):
    name = os.path.basename(os.path.dirname(path))
    with open(path, encoding="utf-8") as f:
        return named.from_colors(named.load_colors(f.read(), path), name)


class NamedPaletteTests(unittest.TestCase):
    def test_the_gallery(self):
        self.assertGreaterEqual(len(THEMES), 10)
        built = {}
        for path in THEMES:
            name = os.path.basename(os.path.dirname(path))
            with self.subTest(name):
                p = build(path)
                built[name] = p
                self.assertEqual(derive.check(p), [], "the engine's contrast guarantees")
                self.assertTrue(p["gallery"])
                self.assertEqual(p["base"], "polar-night" if p["mode"] == "dark" else "winter")
                # "Here" is warm in every theme (an amber to yellow hue), so it reads the same.
                hue = color.hex_to_oklch(p["colors"]["accent"])[2]
                self.assertTrue(40 <= hue <= 110, "accent hue {:.0f}".format(hue))
                # A warning never looks like "here".
                self.assertGreater(color.delta_e(p["colors"]["warning"], p["colors"]["accent"]), 0.05)
                with open(os.path.join(os.path.dirname(path), "SOURCE"), encoding="utf-8") as f:
                    source = f.read()
                self.assertRegex(source, r"Upstream: https://")
                self.assertRegex(source, r"Licence: (MIT|Apache-2\.0)")
        # Pairs point at each other and differ in mode.
        for name, p in built.items():
            pair = p.get("pair")
            if pair:
                with self.subTest(pair=name):
                    self.assertIn(pair, built)
                    self.assertEqual(built[pair].get("pair"), name)
                    self.assertNotEqual(built[pair]["mode"], p["mode"])

    def test_refusals(self):
        with open(THEMES[0], encoding="utf-8") as f:
            good = f.read()
        for bad, why in ((good.replace('mode = "', 'mode = "sepia'), "mode"),
                         (good.replace('background = "#', 'background = "#zz'), "background"),
                         ('mode = "dark"\nforeground = "#ffffff"\n', "missing"),
                         (good + 'here = "gold"\n', "TOML"),       # a key twice
                         (good.replace('here = "yellow"', 'here = "gold"'), "here"),
                         (re.sub(r'pair = "[^"]*"', 'pair = "../x"', good), "pair"),
                         # A label that ends the CSS comment or Zed's JSON string it's written into.
                         (re.sub(r'label = "[^"]*"', r'label = "Evil */ x { } /* \\" "', good), "label"),
                         (re.sub(r'label = "[^"]*"', 'label = "Line break"', good), "label"),
                         ("not toml = = 1", "TOML")):
            with self.subTest(why):
                with self.assertRaises(ThemegenError):
                    named.from_colors(named.load_colors(bad), "x")
        with self.assertRaises(ThemegenError):
            named.from_colors(named.load_colors(good), "Bad Name")

    def test_renders(self):
        with tempfile.TemporaryDirectory() as out:
            render.render(build(THEMES[0]), out)
            with open(os.path.join(out, "palette.json"), encoding="utf-8") as f:
                self.assertTrue(json.load(f)["gallery"])
            self.assertTrue(os.path.isfile(os.path.join(out, "theme.json")))


# The module, not its class: a TestCase imported by name would be collected (and run) here too.
try:
    import test_arctic_theme as base
except ImportError:  # pragma: no cover
    base = None


@unittest.skipIf(base is None or base.Image is None, "Pillow (python3-pillow) is not installed")
@unittest.skipIf(shutil.which("bash") is None, "bash is needed")
class GalleryThemeTests(unittest.TestCase):
    """arctic-theme with the gallery installed (share/arctic/themes-extra)."""

    @classmethod
    def setUpClass(cls):
        cls.share_tmp = tempfile.TemporaryDirectory()
        cls.share = os.path.join(cls.share_tmp.name, "share", "arctic")
        for name in ("winter", "polar-night"):
            render.render(palette.builtin(name), os.path.join(cls.share, "themes", name))
        for path in THEMES:
            name = os.path.basename(os.path.dirname(path))
            if name in ("catppuccin-mocha", "catppuccin-latte", "nord"):
                render.render(build(path), os.path.join(cls.share, "themes-extra", name))
        os.makedirs(os.path.join(cls.share, "theme-hooks.d"))

    @classmethod
    def tearDownClass(cls):
        cls.share_tmp.cleanup()

    # The arctic-theme test home (fakes, a fresh account on Polar night) and its helpers.
    def setUp(self):
        base.ArcticThemeTests.setUp(self)

    def tearDown(self):
        base.ArcticThemeTests.tearDown(self)

    def theme(self, *args, ok=True):
        return base.ArcticThemeTests.theme(self, *args, ok=ok)

    def current(self):
        return base.ArcticThemeTests.current(self)

    def linked(self):
        return base.ArcticThemeTests.linked(self)

    def test_list_set_and_pairs(self):
        themes = {t["name"]: t for t in json.loads(self.theme("list", "--json").stdout)}
        self.assertTrue(themes["nord"]["gallery"])
        self.assertFalse(themes["winter"]["gallery"])
        self.assertEqual(themes["catppuccin-mocha"]["pair"], "catppuccin-latte")
        self.assertIn("term-background", themes["nord"]["swatches"])
        self.theme("set", "catppuccin-mocha")
        self.assertEqual(self.linked(), os.path.join(self.share, "themes-extra", "catppuccin-mocha"))
        # Light and dark keep to the pair; a theme without one goes to Winter / Polar night.
        self.theme("light")
        self.assertEqual(self.current()["name"], "catppuccin-latte")
        self.theme("toggle")
        self.assertEqual(self.current()["name"], "catppuccin-mocha")
        self.theme("set", "nord")
        self.theme("toggle")
        self.assertEqual(self.current()["name"], "winter")


if __name__ == "__main__":
    unittest.main()
