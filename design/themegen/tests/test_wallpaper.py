"""Wallpaper palettes: contrast guarantees over synthetic pictures and the design wallpapers,
greyscale fallback, auto mode, determinism, ANSI distinguishability and speed.

Needs Pillow (python3-pillow); the design wallpapers also need rsvg-convert.
ARCTIC_PERF_BUDGET (seconds, default 1.0) sets the speed limit for a 3840×2160 picture.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import json
import math
import os
import random
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

DESIGN = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, DESIGN)

from themegen import color, derive, palette, render  # noqa: E402

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover
    Image = None

ANSI_NORMAL = ["ansi-{}".format(i) for i in range(1, 7)]
ANSI_BRIGHT = ["ansi-{}".format(i) for i in range(9, 15)]
BUDGET = float(os.environ.get("ARCTIC_PERF_BUDGET", "1.0"))


def hsv(h, s, v):
    import colorsys
    return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(h / 360.0, s, v))


def synthetic(folder):
    """{name: path} of test pictures covering the cases the derivation must survive."""
    W, H = 320, 180
    rnd = random.Random(20260927)
    pics = {}

    def save(name, img, ext="png", **kw):
        path = os.path.join(folder, name + "." + ext)
        img.save(path, **kw)
        pics[name] = path

    for h in range(0, 360, 30):                         # saturated solids around the wheel
        save("solid-h{:03d}".format(h), Image.new("RGB", (W, H), hsv(h, 0.85, 0.8)))
    for h in (60, 200, 300):                            # pale and deep variants
        save("pale-h{:03d}".format(h), Image.new("RGB", (W, H), hsv(h, 0.25, 0.97)))
        save("deep-h{:03d}".format(h), Image.new("RGB", (W, H), hsv(h, 1.0, 0.25)))
    for v in (0, 24, 128, 200, 255):                    # greys, black, white
        save("grey-{:03d}".format(v), Image.new("RGB", (W, H), (v, v, v)))
    img = Image.new("RGB", (W, H))                      # hue gradient
    d = ImageDraw.Draw(img)
    for x in range(W):
        d.line([(x, 0), (x, H)], fill=hsv(x * 360.0 / W, 0.8, 0.9))
    save("gradient-hue", img)
    img = Image.new("RGB", (W, H))                      # dark → light blue gradient
    d = ImageDraw.Draw(img)
    for y in range(H):
        t = y / (H - 1)
        d.line([(0, y), (W, y)], fill=(int(10 + 200 * t), int(20 + 210 * t), int(60 + 190 * t)))
    save("gradient-vertical", img)
    img = Image.new("L", (W, H))                        # greyscale noise
    img.putdata([rnd.randrange(256) for _ in range(W * H)])
    save("noise-grey", img)
    img = Image.new("RGB", (W, H))                      # colour noise
    img.putdata([(rnd.randrange(256), rnd.randrange(256), rnd.randrange(256)) for _ in range(W * H)])
    save("noise-colour", img)
    img = Image.new("RGB", (W, H), (250, 248, 244))     # very bright with a small colour spot
    ImageDraw.Draw(img).ellipse([140, 70, 180, 110], fill=(230, 60, 120))
    save("very-bright", img)
    img = Image.new("RGB", (W, H), (6, 7, 10))          # very dark with faint stars
    d = ImageDraw.Draw(img)
    for _ in range(80):
        x, y = rnd.randrange(W), rnd.randrange(H)
        d.point((x, y), fill=(200, 210, 255))
    save("very-dark", img)
    img = Image.new("RGB", (W, H), (30, 90, 200))       # complementary halves (cast cancels)
    ImageDraw.Draw(img).rectangle([W // 2, 0, W, H], fill=(230, 140, 40))
    save("complementary", img)
    img = Image.new("RGB", (W, H), (40, 90, 50))        # forest with orange flowers
    d = ImageDraw.Draw(img)
    for _ in range(40):
        x, y = rnd.randrange(W), rnd.randrange(H)
        d.ellipse([x, y, x + 8, y + 8], fill=(240, 140, 30))
    save("forest", img)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))       # transparent with a colour block
    ImageDraw.Draw(img).rectangle([0, 0, W // 3, H], fill=(200, 50, 50, 255))
    save("transparent", img)
    save("photo-jpeg", Image.open(pics["gradient-hue"]).convert("RGB"), ext="jpg", quality=85)
    save("palette-gif", Image.open(pics["forest"]).convert("P", palette=Image.Palette.ADAPTIVE), ext="gif")
    img16 = Image.new("I;16", (W, H))
    img16.putdata([int(65535 * x / W) for _y in range(H) for x in range(W)])
    save("grey-16bit", img16)
    return pics


def hue(value):
    return color.hex_to_oklch(value)[2]


def min_pairwise(colors):
    return min(color.delta_e(a, b) for i, a in enumerate(colors) for b in colors[i + 1:])


@unittest.skipIf(Image is None, "Pillow (python3-pillow) is not installed")
class WallpaperPaletteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.pics = synthetic(cls.tmp.name)
        cls.base = {m: palette.builtin(palette.BUILTIN_FOR_MODE[m]) for m in ("dark", "light")}

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def assertGuarantees(self, p, where):
        c = p["colors"]
        self.assertEqual(derive.check(p), [], where)
        # The guarantees spelled out (docs/BUILD-SPEC.md, Theming).
        for bg in ("ground", "surface"):
            self.assertGreaterEqual(color.contrast(c["ink"], c[bg]), 7.0, where)
            self.assertGreaterEqual(color.contrast(c["ink-muted"], c[bg]), 4.5, where)
        self.assertGreaterEqual(color.contrast(c["accent-text"], c["ground"]), 4.5, where)
        self.assertGreaterEqual(color.contrast(c["on-accent"], c["accent"]), 4.5, where)
        self.assertGreaterEqual(color.contrast(c["focus"], c["ground"]), 3.0, where)
        for a in ANSI_NORMAL + ANSI_BRIGHT:
            self.assertGreaterEqual(color.contrast(c[a], c["term-background"]), 4.5, where + " " + a)

    def assertDistinguishableAnsi(self, p, where):
        base = self.base[p["mode"]]["colors"]
        c = p["colors"]
        for group in (ANSI_NORMAL, ANSI_BRIGHT):
            # No two of the six colours come closer than 60% of the static palette's closest pair.
            self.assertGreater(min_pairwise([c[a] for a in group]), 0.6 * min_pairwise([base[a] for a in group]), where)
        for a in ANSI_NORMAL + ANSI_BRIGHT:
            # Hues move toward the wallpaper by at most 15° (plus gamut/rounding slack).
            self.assertLess(abs(color.hue_diff(hue(base[a]), hue(c[a]))), 20.0, where + " " + a)

    def test_guarantees_for_every_synthetic_picture_and_mode(self):
        for name, path in sorted(self.pics.items()):
            for mode in ("auto", "dark", "light"):
                where = "{} --mode {}".format(name, mode)
                with self.subTest(where):
                    p = derive.from_wallpaper(path, mode)
                    palette.validate(p)
                    if mode != "auto":
                        self.assertEqual(p["mode"], mode)
                    self.assertEqual(p["base"], palette.BUILTIN_FOR_MODE[p["mode"]])
                    self.assertGuarantees(p, where)
                    self.assertDistinguishableAnsi(p, where)

    def test_greyscale_falls_back_to_the_base_palette(self):
        for name in ("grey-000", "grey-128", "grey-255", "noise-grey", "grey-16bit"):
            for mode in ("dark", "light"):
                p = derive.from_wallpaper(self.pics[name], mode)
                self.assertTrue(p["source"]["fallback"], name)
                base = self.base[mode]["colors"]
                self.assertEqual(p["colors"]["accent"], base["accent"], name)
                self.assertEqual(p["colors"], base, name)     # nothing to tint with either

    def test_colourful_pictures_seed_the_accent(self):
        for h in range(0, 360, 30):
            p = derive.from_wallpaper(self.pics["solid-h{:03d}".format(h)], "dark")
            self.assertFalse(p["source"]["fallback"])
            seed_hue = hue(p["source"]["seed"])
            self.assertLess(abs(color.hue_diff(seed_hue, hue(p["colors"]["accent"]))), 8.0, h)
            # Neutrals are tinted toward the picture, but stay near-neutral.
            L, C, gh = color.hex_to_oklch(p["colors"]["ground"])
            self.assertLess(C, 0.045)
            self.assertLess(abs(color.hue_diff(gh, seed_hue)), 25.0, h)
            # Structure (lightness) stays the design's.
            base_L = color.hex_to_oklch(self.base["dark"]["colors"]["ground"])[0]
            self.assertAlmostEqual(L, base_L, delta=0.01)
        red = derive.from_wallpaper(self.pics["very-bright"], "auto")
        self.assertEqual(red["mode"], "light")
        self.assertLess(abs(color.hue_diff(hue(red["source"]["seed"]), hue("#e63c78"))), 10)

    def test_auto_mode_follows_the_picture(self):
        for name in ("grey-255", "grey-200", "very-bright", "pale-h060", "pale-h200"):
            self.assertEqual(derive.from_wallpaper(self.pics[name], "auto")["mode"], "light", name)
        for name in ("grey-000", "grey-024", "very-dark", "deep-h300", "forest", "solid-h240"):
            self.assertEqual(derive.from_wallpaper(self.pics[name], "auto")["mode"], "dark", name)

    def test_base_option(self):
        p = derive.from_wallpaper(self.pics["forest"], "auto", "winter")
        self.assertEqual((p["mode"], p["base"]), ("light", "winter"))
        with self.assertRaises(palette.ThemegenError):
            derive.from_wallpaper(self.pics["forest"], "dark", "winter")

    def test_deterministic(self):
        for name in ("noise-colour", "gradient-hue", "forest", "photo-jpeg"):
            a = palette.dumps(derive.from_wallpaper(self.pics[name]))
            b = palette.dumps(derive.from_wallpaper(self.pics[name]))
            self.assertEqual(a, b, name)
        cli = subprocess.run([sys.executable, "-m", "themegen", "palette", "--from-wallpaper", self.pics["forest"]],
                             cwd=DESIGN, capture_output=True, text=True, check=True).stdout
        self.assertEqual(cli, palette.dumps(derive.from_wallpaper(self.pics["forest"])))

    def test_renders(self):
        with tempfile.TemporaryDirectory() as d:
            p = derive.from_wallpaper(self.pics["forest"])
            render.render(p, d)
            with open(os.path.join(d, "theme.json")) as f:
                tj = json.load(f)
            self.assertEqual(tj["id"], "wallpaper")
            self.assertEqual(tj["wallpaper"], self.pics["forest"])
            with open(os.path.join(d, "palette.json")) as f:
                self.assertEqual(json.load(f)["source"]["image"], self.pics["forest"])

    def test_unreadable_pictures_are_errors(self):
        with tempfile.TemporaryDirectory() as d:
            bad = os.path.join(d, "bad.png")
            with open(bad, "wb") as f:
                f.write(b"not a png")
            for path in (bad, os.path.join(d, "missing.jpg")):
                with self.assertRaises(palette.ThemegenError):
                    derive.from_wallpaper(path)

    def test_design_wallpapers(self):
        if not shutil.which("rsvg-convert"):
            self.skipTest("rsvg-convert (librsvg2-tools) is not installed")
        folder = os.path.join(DESIGN, "wallpapers")
        svgs = sorted(f for f in os.listdir(folder) if f.endswith(".svg"))
        self.assertTrue(svgs)
        for f in svgs:
            for mode in ("auto", "dark", "light"):
                p = derive.from_wallpaper(os.path.join(folder, f), mode)
                self.assertGuarantees(p, f + " " + mode)
                self.assertDistinguishableAnsi(p, f + " " + mode)
            auto = derive.from_wallpaper(os.path.join(folder, f), "auto")["mode"]
            if f.endswith("-polar-night.svg"):
                self.assertEqual(auto, "dark", f)

    def test_speed_on_a_4k_picture(self):
        """< 1 s (ARCTIC_PERF_BUDGET) for a 3840×2160 picture: a noisy PNG (slow to decode) and a
        JPEG, analysis and palette only (what arctic-theme runs before rendering)."""
        with tempfile.TemporaryDirectory() as d:
            W, H = 3840, 2160
            small = Image.open(self.pics["noise-colour"]).resize((W // 8, H // 8))
            big = small.resize((W, H), Image.Resampling.NEAREST)
            noise = Image.frombytes("L", (W, H), random.Random(1).randbytes(W * H))
            big = Image.merge("RGB", [Image.blend(ch, noise, 0.3) for ch in big.split()])
            png, jpg = os.path.join(d, "big.png"), os.path.join(d, "big.jpg")
            big.save(png, compress_level=6)
            big.save(jpg, quality=90)
            for path in (png, jpg):
                t = time.perf_counter()
                p = derive.from_wallpaper(path)
                elapsed = time.perf_counter() - t
                self.assertEqual(derive.check(p), [])
                self.assertLess(elapsed, BUDGET, "{}: {:.2f}s".format(os.path.basename(path), elapsed))
            t = time.perf_counter()
            render.render(derive.from_wallpaper(jpg), os.path.join(d, "theme"))
            self.assertLess(time.perf_counter() - t, BUDGET * 1.5, "palette + render")


class EnforcementTests(unittest.TestCase):
    def test_base_palettes_already_meet_every_guarantee(self):
        for name in ("winter", "polar-night"):
            p = palette.builtin(name)
            self.assertEqual(derive.check(p), [])
            c = dict(p["colors"])
            self.assertEqual(derive.enforce(dict(c)), c, name)    # enforcing changes nothing

    def test_enforce_repairs_a_bad_palette(self):
        p = palette.builtin("polar-night")
        c = p["colors"]
        c.update({"ink": "#30343a", "ink-muted": "#202428", "accent": "#303030", "on-accent": "#383838",
                  "accent-text": "#222222", "focus": "#1a1a1a", "ansi-1": "#301010", "ansi-12": "#101830"})
        self.assertTrue(derive.check(p))
        derive.enforce(c)
        self.assertEqual(derive.check(p), [])

    def test_greyscale_analysis_is_the_base(self):
        from themegen import wallpaper
        a = wallpaper.analyse_colors([(100, (128, 128, 128)), (50, (20, 20, 20)), (10, (240, 240, 240))])
        self.assertIsNone(a.seed)
        self.assertAlmostEqual(a.cast_strength, 0.0, places=6)
        for name in ("winter", "polar-night"):
            base = palette.builtin(name)
            self.assertEqual(derive.derive(a, base)["colors"], base["colors"])

    def test_kmeans_is_deterministic_and_weighted(self):
        from themegen import wallpaper
        pts = [(5, (0.5, 0.1, 0.0)), (5, (0.52, 0.11, 0.0)), (1, (0.2, -0.1, 0.1)), (1, (0.21, -0.1, 0.1))]
        a = wallpaper.kmeans(pts, k=2)
        self.assertEqual(a, wallpaper.kmeans(list(reversed(pts)), k=2))
        self.assertAlmostEqual(a[0][0], 10)
        self.assertAlmostEqual(a[0][1][0], 0.51, places=6)
        self.assertTrue(math.isclose(a[1][0], 2))


if __name__ == "__main__":
    unittest.main()
