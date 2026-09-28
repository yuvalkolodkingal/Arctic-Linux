"""Palettes and rendering: built-in palettes, validation, theme folders, committed outputs.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import filecmp
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(DESIGN)
sys.path.insert(0, DESIGN)

from themegen import palette, render  # noqa: E402
from themegen.palette import ThemegenError  # noqa: E402

COMMITTED = os.path.join(REPO, "dotfiles", ".config", "arctic", "themes")

# The colour roles every palette has (docs/BUILD-SPEC.md, Theming).
INTERFACE_ROLES = """ground surface surface-raised surface-sunken frost scrim line line-strong ink
ink-muted ink-subtle ink-disabled ink-inverse accent accent-hover accent-pressed on-accent
accent-text accent-soft accent-edge focus selection warm warm-soft success success-soft warning
warning-soft error error-soft on-error error-hover info info-soft aurora-1 aurora-2 aurora-3
term-background term-foreground term-cursor term-cursor-text-color term-selection-background
term-selection-foreground""".split() + ["ansi-{}".format(i) for i in range(16)]


def files_in(d):
    out = set()
    for root, _dirs, fns in os.walk(d):
        for fn in fns:
            out.add(os.path.relpath(os.path.join(root, fn), d))
    return out


class PaletteTests(unittest.TestCase):
    def test_roles_match_the_interface_and_the_tokens(self):
        self.assertEqual(list(palette.ROLES), INTERFACE_ROLES)
        tok = palette.tokens()
        for mode in ("dark", "light"):
            self.assertEqual(list(tok["themes"][mode]), INTERFACE_ROLES)

    def test_builtins(self):
        pn = palette.builtin("polar-night")
        self.assertEqual((pn["name"], pn["label"], pn["mode"], pn["base"]), ("polar-night", "Polar night", "dark", "polar-night"))
        self.assertEqual((pn["wallpaper"], pn["lock_wallpaper"]), ("aurora-polar-night", "fox-polar-night"))
        self.assertEqual(pn["colors"]["accent"], "#f6bd55")
        self.assertEqual(pn["colors"]["shadow"], "#000000cc")
        w = palette.builtin("winter")
        self.assertEqual((w["label"], w["mode"]), ("Winter", "light"))
        self.assertEqual(w["colors"]["shadow"], "#12171e33")
        self.assertEqual(palette.validate(w), w)
        with self.assertRaises(ThemegenError):
            palette.builtin("summer")

    def test_validation(self):
        good = palette.builtin("winter")

        def broken(**changes):
            p = json.loads(json.dumps(good))
            for k, v in changes.items():
                if k.startswith("c_"):
                    p["colors"][k[2:].replace("_", "-")] = v
                elif v is None:
                    p.pop(k)
                else:
                    p[k] = v
            return p

        for p in (broken(name="Bad Name"), broken(name="../x"), broken(mode="dim"), broken(colors=[]),
                  broken(c_ink="red"), broken(c_ink="#12345"), broken(label="two\nlines"),
                  broken(wallpaper="a\nb"), broken(label=""), "not an object"):
            with self.assertRaises(ThemegenError):
                palette.validate(p)
        p = broken()
        del p["colors"]["ansi-15"]
        with self.assertRaisesRegex(ThemegenError, "missing ansi-15"):
            palette.validate(p)
        # Optional fields default; shadow is added; extra roles are kept.
        p = broken(label=None, base=None, wallpaper=None, lock_wallpaper=None)
        del p["colors"]["shadow"]
        p["colors"]["glow"] = "#ffffff80"
        v = palette.validate(p)
        self.assertEqual((v["label"], v["base"], v["wallpaper"], v["lock_wallpaper"]),
                         ("winter", "winter", "snowfield-winter", "fox-winter"))
        self.assertEqual(v["colors"]["shadow"], "#12171e33")
        self.assertEqual(v["colors"]["glow"], "#ffffff80")

    def test_palette_json_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "p.json")
            with open(path, "w") as f:
                f.write(palette.dumps(palette.builtin("polar-night")))
            self.assertEqual(palette.load(path), palette.builtin("polar-night"))
            with open(path) as f:
                self.assertEqual(list(json.load(f)["colors"])[:len(palette.ROLES)], list(palette.ROLES))
        self.assertEqual(palette.load("winter"), palette.builtin("winter"))


class RenderTests(unittest.TestCase):
    def test_committed_themes_are_current(self):
        """dotfiles/.config/arctic/themes must be what the engine renders (re-run
        design/tools/gen-desktop-themes.py after changing templates, tokens or the engine)."""
        with tempfile.TemporaryDirectory() as d:
            for name in ("winter", "polar-night"):
                out = os.path.join(d, name)
                render.render(palette.builtin(name), out)
                committed = os.path.join(COMMITTED, name)
                self.assertEqual(files_in(out), files_in(committed), name)
                for rel in sorted(files_in(out)):
                    self.assertTrue(filecmp.cmp(os.path.join(out, rel), os.path.join(committed, rel), shallow=False),
                                    "{}/{} is out of date: run design/tools/gen-desktop-themes.py".format(name, rel))

    def test_shell_defaults_are_current(self):
        spec = importlib.util.spec_from_file_location("gen", os.path.join(DESIGN, "tools", "gen-desktop-themes.py"))
        gen = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(gen)
        with open(os.path.join(REPO, "shell", "assets", "theme-defaults.js"), encoding="utf-8") as f:
            self.assertEqual(f.read(), gen.shell_defaults(palette.builtin("polar-night")),
                             "shell/assets/theme-defaults.js is out of date: run design/tools/gen-desktop-themes.py")

    def test_theme_folder_contents(self):
        with tempfile.TemporaryDirectory() as d:
            render.render(palette.builtin("polar-night"), d)
            names = files_in(d)
            for f in ("theme.json", "gtk.css", "theme.env", "palette.json", "kitty.conf", "mango-colors.conf",
                      "waybar-colors.css", "mako.ini", "fuzzel-colors.ini", "swaylock.conf",
                      os.path.join("icons", "mark.svg"), os.path.join("icons", "download-on-accent.svg")):
                self.assertIn(f, names)
            with open(os.path.join(d, "theme.json")) as f:
                tj = json.load(f)
            self.assertEqual(tj["colors"]["frost"], "#d11a212a")        # QML #AARRGGBB
            self.assertEqual(tj["colors"]["snow100"], "#f3f6f8")        # ramps are there too
            self.assertEqual(tj["radius"]["radiusMd"], 10)
            with open(os.path.join(d, "gtk.css")) as f:
                gtk = f.read()
            self.assertIn("@define-color arctic_frost rgba(26, 33, 42, 0.82);", gtk)
            self.assertNotRegex(gtk, r"#[0-9a-f]{8}\b")

    def test_rerender_updates_in_place_and_drops_stale_files(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "t")
            self.assertTrue(render.render(palette.builtin("winter"), out))
            self.assertEqual(render.render(palette.builtin("winter"), out), [])   # nothing changed
            with open(os.path.join(out, "stale.conf"), "w") as f:
                f.write("left over")
            os.makedirs(os.path.join(out, "old", "dir"))
            open(os.path.join(out, "old", "dir", "x"), "w").close()
            written = render.render(palette.builtin("polar-night"), out)
            self.assertIn("theme.json", written)
            self.assertEqual(written[-1], "theme.json")                           # last, for the shell
            self.assertFalse(os.path.exists(os.path.join(out, "stale.conf")))
            self.assertFalse(os.path.exists(os.path.join(out, "old")))
            with open(os.path.join(out, "theme.json")) as f:
                self.assertEqual(json.load(f)["id"], "polar-night")

    def test_refuses_folders_that_are_not_themes(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "important.txt"), "w").close()
            with self.assertRaises(ThemegenError):
                render.render(palette.builtin("winter"), d)
            self.assertTrue(os.path.exists(os.path.join(d, "important.txt")))
            render.render(palette.builtin("winter"), d, force=True)
            self.assertTrue(os.path.exists(os.path.join(d, "theme.json")))

    def test_extra_template_dirs(self):
        with tempfile.TemporaryDirectory() as d:
            tdir = os.path.join(d, "templates", "qt6ct", "colors")
            os.makedirs(tdir)
            with open(os.path.join(tdir, "arctic.conf.tmpl"), "w") as f:
                f.write("[ColorScheme]\nwindow={{surface|argb}}\ndark={{is_dark}}\n")
            out = os.path.join(d, "theme")
            render.render(palette.builtin("polar-night"), out, [os.path.join(d, "templates")])
            with open(os.path.join(out, "qt6ct", "colors", "arctic.conf")) as f:
                self.assertEqual(f.read(), "[ColorScheme]\nwindow=#ff1a212a\ndark=true\n")

    def test_theme_env_is_shell_safe(self):
        p = palette.builtin("winter")
        p.update(name="mine", label='Evil "$(touch pwned)" `x` \\ $HOME', wallpaper="/tmp/a b/$(touch pwned).png",
                 lock_wallpaper="it's")
        with tempfile.TemporaryDirectory() as d:
            render.render(p, os.path.join(d, "t"))
            out = subprocess.run(
                ["bash", "-c", 'set -u; source t/theme.env; printf "%s\\n" "$ARCTIC_THEME" "$ARCTIC_THEME_NAME" '
                               '"$ARCTIC_WALLPAPER" "$ARCTIC_LOCK_WALLPAPER" "$ARCTIC_GTK_PREFER_DARK" "$ARCTIC_THEME_MODE"'],
                cwd=d, capture_output=True, text=True, check=True).stdout.splitlines()
            self.assertEqual(out, ["mine", p["label"], p["wallpaper"], "it's", "0", "light"])
            self.assertFalse(os.path.exists(os.path.join(d, "pwned")))


if __name__ == "__main__":
    unittest.main()
