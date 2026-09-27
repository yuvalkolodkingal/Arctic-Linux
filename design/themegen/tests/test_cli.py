"""arctic-themegen command line (python3 -m themegen and dotfiles/.local/bin/arctic-themegen).

Run: python3 -m unittest discover -s design/themegen/tests
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REPO = os.path.dirname(DESIGN)
WRAPPER = os.path.join(REPO, "dotfiles", ".local", "bin", "arctic-themegen")
sys.path.insert(0, DESIGN)

from themegen import palette  # noqa: E402


def run(*args, stdin=None):
    return subprocess.run([sys.executable, WRAPPER] + list(args), capture_output=True, text=True, input=stdin)


class CliTests(unittest.TestCase):
    def test_builtin(self):
        for name in ("winter", "polar-night"):
            r = run("builtin", name)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout), palette.builtin(name))
        self.assertEqual(run("builtin", "summer").returncode, 2)

    def test_render_and_check(self):
        with tempfile.TemporaryDirectory() as d:
            pfile = os.path.join(d, "p.json")
            with open(pfile, "w") as f:
                f.write(run("builtin", "winter").stdout)
            out = os.path.join(d, "theme")
            r = run("render", "--palette", pfile, "--out", out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertTrue(os.path.isfile(os.path.join(out, "theme.json")))
            r = run("render", "--palette", "-", "--out", out, "--quiet", stdin=run("builtin", "polar-night").stdout)
            self.assertEqual((r.returncode, r.stdout), (0, ""), r.stderr)
            with open(os.path.join(out, "theme.env")) as f:
                self.assertIn("ARCTIC_THEME=polar-night\n", f.read())
            r = run("check", "--palette", pfile, "--json")
            self.assertEqual(r.returncode, 0)
            self.assertTrue(json.loads(r.stdout)["ok"])
            bad = palette.builtin("winter")
            bad["colors"]["ink"] = bad["colors"]["ground"]
            with open(pfile, "w") as f:
                json.dump(bad, f)
            r = run("check", "--palette", pfile)
            self.assertEqual(r.returncode, 1)
            self.assertIn("FAIL ink on ground", r.stderr)

    def test_errors_exit_2_with_a_message(self):
        with tempfile.TemporaryDirectory() as d:
            broken = os.path.join(d, "broken.json")
            with open(broken, "w") as f:
                f.write("{not json")
            for args in (("render", "--palette", os.path.join(d, "missing.json"), "--out", d),
                         ("render", "--palette", broken, "--out", os.path.join(d, "o")),
                         ("palette", "--from-wallpaper", os.path.join(d, "missing.png")),
                         ("palette", "--from-wallpaper", broken, "--name", "Bad Name")):
                r = run(*args)
                self.assertEqual(r.returncode, 2, args)
                self.assertTrue(r.stderr.startswith("arctic-themegen: "), r.stderr)

    def test_palette_from_wallpaper(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        with tempfile.TemporaryDirectory() as d:
            img = os.path.join(d, "sea.png")
            Image.new("RGB", (64, 36), (20, 90, 160)).save(img)
            r = run("palette", "--from-wallpaper", img, "--mode", "light", "--name", "sea", "--label", "Sea")
            self.assertEqual(r.returncode, 0, r.stderr)
            p = json.loads(r.stdout)
            self.assertEqual((p["name"], p["label"], p["mode"], p["base"], p["wallpaper"]), ("sea", "Sea", "light", "winter", img))
            self.assertEqual(p["source"]["image"], img)
            self.assertFalse(p["source"]["fallback"])
            r = run("palette", "--from-wallpaper", img, "--mode", "dark", "--base", "winter")
            self.assertEqual(r.returncode, 2)
            self.assertIn("light theme", r.stderr)


if __name__ == "__main__":
    unittest.main()
