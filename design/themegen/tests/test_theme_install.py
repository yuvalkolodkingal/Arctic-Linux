"""arctic-theme install / remove: a theme repository's colours and pictures kept, everything else
left out (configs, scripts, links, '..'), names from the repository, links only to the forges,
and removing the active theme.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import io
import json
import os
import shutil
import sys
import tarfile
import tempfile
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DESIGN)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from themegen import palette, render  # noqa: E402

try:
    import test_arctic_theme as base      # the module: its TestCase would be collected here too
except ImportError:  # pragma: no cover
    base = None

with open(os.path.join(DESIGN, "themes", "nord", "colors.toml"), encoding="utf-8") as f:
    NORD = f.read().split("# Arctic")[0]           # as an Omarchy theme has it: no Arctic keys


def png():
    from PIL import Image
    out = io.BytesIO()
    Image.new("RGB", (8, 8), (40, 50, 60)).save(out, "PNG")
    return out.getvalue()


def archive(path, top, files, links=()):
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo((top + "/" if top else "") + name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        for name, target in links:
            info = tarfile.TarInfo(top + "/" + name)
            info.type = tarfile.SYMTYPE
            info.linkname = target
            tar.addfile(info)


@unittest.skipIf(base is None or base.Image is None, "Pillow (python3-pillow) is not installed")
@unittest.skipIf(shutil.which("bash") is None, "bash is needed")
class InstallTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.share_tmp = tempfile.TemporaryDirectory()
        cls.share = os.path.join(cls.share_tmp.name, "share", "arctic")
        for name in ("winter", "polar-night"):
            render.render(palette.builtin(name), os.path.join(cls.share, "themes", name))
        os.makedirs(os.path.join(cls.share, "theme-hooks.d"))

    @classmethod
    def tearDownClass(cls):
        cls.share_tmp.cleanup()

    def setUp(self):
        base.ArcticThemeTests.setUp(self)
        self.env["XDG_STATE_HOME"] = os.path.join(self.root, "state")

    def tearDown(self):
        base.ArcticThemeTests.tearDown(self)

    def theme(self, *args, ok=True):
        return base.ArcticThemeTests.theme(self, *args, ok=ok)

    def current(self):
        return base.ArcticThemeTests.current(self)

    def repo(self, name="omarchy-nord-theme.tar.gz", top="omarchy-nord-theme-main", **extra):
        files = {"colors.toml": NORD.encode(), "backgrounds/1-fjord.png": png(), "backgrounds/2-notes.txt": b"hello",
                 "backgrounds/3-fake.jpg": b"not a picture", "preview.png": png(), "kitty.conf": b"font_family x",
                 "neovim.lua": b"os.execute('x')", "hooks/theme-set": b"#!/bin/sh\nrm -rf ~"}
        files.update(extra)
        path = os.path.join(self.root, name)
        archive(path, top, files, links=[("backgrounds/0-link.png", "/etc/passwd")])
        return path

    def test_install_keeps_colours_and_pictures_only(self):
        out = json.loads(self.theme("install", self.repo(), "--json").stdout)
        self.assertEqual((out["name"], out["label"], out["mode"], out["backgrounds"]), ("nord", "Nord", "dark", 1))
        for dropped in ("kitty.conf", "neovim.lua", "hooks/theme-set", "backgrounds/2-notes.txt",
                        "backgrounds/3-fake.jpg", "backgrounds/0-link.png"):
            self.assertIn(dropped, out["dropped"])
        folder = os.path.join(self.config, "themes", "nord")
        kept = sorted(os.path.relpath(os.path.join(d, f), folder) for d, _s, fs in os.walk(folder) for f in fs)
        self.assertIn("backgrounds/1-fjord.png", kept)
        self.assertIn("preview.png", kept)
        self.assertIn("theme.json", kept)
        for never in ("neovim.lua", "hooks/theme-set", "backgrounds/0-link.png", "colors.toml"):
            self.assertNotIn(never, kept)
        # kitty.conf there is Arctic's own rendering, not the repository's.
        with open(os.path.join(folder, "kitty.conf"), encoding="utf-8") as f:
            self.assertNotIn("font_family x", f.read())
        listing = {t["name"]: t for t in json.loads(self.theme("list", "--json").stdout)}
        self.assertTrue(listing["nord"]["gallery"])
        self.assertTrue(listing["nord"]["installed_from"].endswith("omarchy-nord-theme.tar.gz"))
        self.assertIsNone(listing["winter"]["installed_from"])
        # Use it, then remove it: the mode's built-in takes over.
        self.theme("set", "nord")
        self.assertEqual(self.current()["name"], "nord")
        self.assertIn("already installed", self.theme("install", self.repo(), ok=False).stderr)
        self.theme("remove", "nord")
        self.assertEqual(self.current()["name"], "polar-night")
        self.assertFalse(os.path.exists(folder))
        self.assertEqual(self.theme("remove", "winter", ok=False).returncode, 2)

    def test_light_mode_and_bad_archives(self):
        path = self.repo(name="arctic-dawn.tar.gz", top="arctic-dawn-HEAD",
                         **{"colors.toml": NORD.replace('mode = "dark"\n', '').replace("#2e3440", "#eceff4")
                            .replace("#d8dee9", "#2e3440").replace("#eceff4\"", "#2e3440\"").encode(),
                            "light.mode": b""})
        out = json.loads(self.theme("install", path, "--json").stdout)
        self.assertEqual((out["name"], out["mode"]), ("dawn", "light"))
        # No colours, '..' members, not an archive at all.
        empty = os.path.join(self.root, "empty-theme.tar.gz")
        archive(empty, "empty-theme", {"README.md": b"hi"})
        self.assertIn("colors.toml", self.theme("install", empty, ok=False).stderr)
        evil = os.path.join(self.root, "evil-theme.tar.gz")
        archive(evil, "", {"../../colors.toml": NORD.encode()})
        self.assertIn("colors.toml", self.theme("install", evil, ok=False).stderr)
        junk = os.path.join(self.root, "junk-theme.tar.gz")
        with open(junk, "wb") as f:
            f.write(b"not a tarball")
        self.assertIn("archive", self.theme("install", junk, ok=False).stderr)

    def test_links(self):
        for url in ("http://github.com/o/r", "https://example.com/o/r", "https://github.com/o", "file:///etc/x",
                    "https://github.com/o/r$(x)"):
            r = self.theme("install", url, ok=False)
            self.assertNotEqual(r.returncode, 0, url)
        # A forge link is turned into its source tarball (the download itself fails here).
        self.env["https_proxy"] = self.env["HTTPS_PROXY"] = "http://127.0.0.1:9"
        r = self.theme("install", "https://github.com/basecamp/omarchy-nord-theme", ok=False)
        self.assertIn("couldn't download", r.stderr)


if __name__ == "__main__":
    unittest.main()
