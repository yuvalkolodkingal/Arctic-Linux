"""Colour math: hex, OKLab/OKLCH, WCAG contrast, gamut mapping, contrast enforcement.

Run: python3 -m unittest discover -s design/themegen/tests
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from themegen import color  # noqa: E402


class HexTests(unittest.TestCase):
    def test_parse_and_format(self):
        self.assertEqual(color.parse_hex("#1A212A"), ((26, 33, 42), None))
        self.assertEqual(color.parse_hex("#1a212ad1"), ((26, 33, 42), 0xd1))
        self.assertEqual(color.to_hex((26, 33, 42)), "#1a212a")
        self.assertEqual(color.to_hex((26, 33, 42), 0xd1), "#1a212ad1")
        self.assertEqual(color.with_alpha("#1a212ad1", None), "#1a212a")
        for bad in ("1a212a", "#1a212", "#1a212ag", "#1a212ad", "", None, 12):
            self.assertFalse(color.is_hex(bad))
            with self.assertRaises(ValueError):
                color.parse_hex(bad)


class OklabTests(unittest.TestCase):
    def assertTupleClose(self, a, b, places=4):
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=places)

    def test_reference_values(self):
        # Björn Ottosson's reference conversions (https://bottosson.github.io/posts/oklab/).
        self.assertTupleClose(color.hex_to_oklab("#ffffff"), (1.0, 0.0, 0.0))
        self.assertTupleClose(color.hex_to_oklab("#000000"), (0.0, 0.0, 0.0))
        self.assertTupleClose(color.hex_to_oklab("#ff0000"), (0.62796, 0.22486, 0.12585), places=3)
        self.assertTupleClose(color.hex_to_oklab("#00ff00"), (0.86644, -0.23389, 0.17950), places=3)
        self.assertTupleClose(color.hex_to_oklab("#0000ff"), (0.45201, -0.03246, -0.31153), places=3)

    def test_round_trip_every_8bit_step(self):
        steps = range(0, 256, 17)
        for r in steps:
            for g in steps:
                for b in steps:
                    h = color.to_hex((r, g, b))
                    self.assertEqual(color.oklab_to_hex(color.hex_to_oklab(h)), h)
                    self.assertEqual(color.oklch_to_hex(color.hex_to_oklch(h)), h)

    def test_lch(self):
        L, C, h = color.hex_to_oklch("#808080")
        self.assertAlmostEqual(C, 0.0, places=4)
        L, C, h = color.hex_to_oklch("#f6bd55")   # Polar night amber
        self.assertAlmostEqual(h, 79.9, delta=0.2)
        self.assertAlmostEqual(C, 0.136, delta=0.002)

    def test_gamut_mapping_keeps_lightness_and_hue(self):
        for lch in ((0.9, 0.35, 264.0), (0.5, 0.4, 30.0), (0.75, 0.3, 145.0), (0.3, 0.2, 300.0)):
            self.assertFalse(color.in_gamut(color.lch_to_lab(lch)))
            rgb = color.oklch_to_rgb(lch)
            self.assertTrue(all(0.0 <= c <= 1.0 for c in rgb))
            L, C, h = color.lab_to_lch(color.rgb_to_oklab(rgb))
            self.assertAlmostEqual(L, lch[0], delta=0.01)
            self.assertLess(abs(color.hue_diff(h, lch[2])), 3.0)
            self.assertLess(C, lch[1])
        self.assertEqual(color.oklch_to_hex((1.2, 0.1, 10)), "#ffffff")
        self.assertEqual(color.oklch_to_hex((-0.1, 0.1, 10)), "#000000")


class ContrastTests(unittest.TestCase):
    def test_known_ratios(self):
        self.assertAlmostEqual(color.contrast("#000000", "#ffffff"), 21.0, places=6)
        self.assertAlmostEqual(color.contrast("#ffffff", "#000000"), 21.0, places=6)
        self.assertAlmostEqual(color.contrast("#777777", "#ffffff"), 4.48, places=2)
        self.assertAlmostEqual(color.contrast("#12171e", "#12171e"), 1.0)
        # alpha is ignored
        self.assertEqual(color.contrast("#e9eef3", "#12171e"), color.contrast("#e9eef3cc", "#12171e"))

    def test_ensure_contrast_reaches_the_ratio(self):
        grounds = ("#12171e", "#eef2f5", "#808080", "#3c78c8", "#ffffff", "#000000", "#f6bd55")
        fgs = ("#12171e", "#eef2f5", "#808080", "#f6bd55", "#b3261e", "#2f5f9a", "#7fcf9b")
        for bg in grounds:
            for fg in fgs:
                for ratio in (3.0, 4.5, 7.0):
                    out = color.ensure_contrast(fg, bg, ratio)
                    best = max(color.contrast("#ffffff", bg), color.contrast("#000000", bg))
                    if best >= ratio:
                        self.assertGreaterEqual(color.contrast(out, bg), ratio, (fg, bg, ratio, out))
                    else:
                        self.assertAlmostEqual(color.contrast(out, bg), best, places=2)
                    if color.contrast(fg, bg) >= ratio:
                        self.assertEqual(out, fg)

    def test_ensure_contrast_keeps_hue_and_alpha(self):
        out = color.ensure_contrast("#f6bd55cc", "#fbfcfd", 4.5)
        self.assertTrue(out.endswith("cc"))
        self.assertGreaterEqual(color.contrast(out, "#fbfcfd"), 4.5)
        self.assertLess(abs(color.hue_diff(color.hex_to_oklch(out)[2], color.hex_to_oklch("#f6bd55")[2])), 8)
        # Moves the least needed: just past the threshold.
        self.assertLess(color.contrast(out, "#fbfcfd"), 4.7)

    def test_hue_diff(self):
        self.assertEqual(color.hue_diff(350, 10), 20)
        self.assertEqual(color.hue_diff(10, 350), -20)
        self.assertEqual(color.hue_diff(0, 180), 180)


if __name__ == "__main__":
    unittest.main()
