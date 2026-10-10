"""Host negative controls for the additional installed-image taskbar gate."""
import copy
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
spec = importlib.util.spec_from_file_location('taskbar', HERE/'taskbar.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)


class Controls(unittest.TestCase):
    def inventory(self, mode='auto', frame=True):
        values = []
        for name in ('DP-1', 'DP-2'):
            values.append(dict(name='arctic-bar', monitor=name,
                               layer='top' if mode == 'always' else 'overlay'))
            if frame:
                values.append(dict(name='arctic-frame', monitor=name, layer='bottom'))
                values.extend(dict(name='arctic-frame-reserve', monitor=name, layer='bottom')
                              for _ in range(3 if mode == 'always' else 4))
        return values

    def test_actual_mapped_surface_counts_detect_duplicate_missing_and_cross_output_bars(self):
        original = self.inventory()
        self.assertEqual(t.validate_layers(original, ['DP-1', 'DP-2'], 'auto', True), original)
        for mutation in (
            original + [copy.deepcopy(original[0])],
            original[1:],
            [dict(x, monitor='missing-output') if x == original[0] else x for x in original],
            [dict(x, layer='top') if x == original[0] else x for x in original],
        ):
            with self.assertRaises(RuntimeError):
                t.validate_layers(mutation, ['DP-1', 'DP-2'], 'auto', True)

    def test_reserve_remapping_counts_are_required_in_both_modes(self):
        t.validate_layers(self.inventory('always'), ['DP-1', 'DP-2'], 'always', True)
        t.validate_layers(self.inventory('dodge'), ['DP-1', 'DP-2'], 'dodge', True)
        t.validate_layers(self.inventory(frame=False), ['DP-1', 'DP-2'], 'auto', False)
        for mode, frame, values in (
            ('always', True, self.inventory('auto')),
            ('auto', True, self.inventory('always')),
            ('auto', False, self.inventory('auto')),
        ):
            with self.assertRaises(RuntimeError):
                t.validate_layers(values, ['DP-1', 'DP-2'], mode, frame)

    def test_effective_geometry_detects_old_inset_duplicate_zone_and_bar_reservation(self):
        baseline = dict(x=-1016, y=8, width=1008, height=752)
        expected = {
            'top': dict(x=-1010, y=46, width=996, height=708),
            'bottom': dict(x=-1010, y=14, width=996, height=708),
            'left': dict(x=-978, y=14, width=964, height=740),
            'right': dict(x=-1010, y=14, width=964, height=740),
        }
        for edge in t.EDGES:
            self.assertEqual(t.reserved_rectangle(baseline, edge, 'always'), expected[edge])
            hidden = t.reserved_rectangle(baseline, edge, 'auto')
            self.assertEqual(hidden, dict(x=-1010, y=14, width=996, height=740))
            self.assertTrue(t.same_rectangle(hidden, t.reserved_rectangle(baseline, edge, 'dodge')))
            self.assertFalse(t.same_rectangle(hidden, expected[edge]))
            self.assertFalse(t.same_rectangle(hidden, dict(hidden, height=hidden['height']-6)))
            self.assertFalse(t.same_rectangle(hidden, dict(hidden, width=hidden['width']-32)))
        for malformed in (dict(baseline, width=True), dict(baseline, x=float('nan')),
                          dict(baseline, height=0)):
            with self.assertRaises(RuntimeError): t.rectangle(malformed)

    def test_fullscreen_visibility_oracle_covers_every_edge_and_fractional_scale(self):
        for scale in t.SCALES:
            for edge in t.EDGES:
                image = Image.new('RGB', (round(1024*scale), round(768*scale)), t.FOOT_COLOR)
                hidden = t.pixel_visibility(image, edge, scale)
                self.assertEqual(hidden['non_foot_fraction'], 0)
                self.assertGreaterEqual(hidden['sampled_pixels'], 25)
                draw = ImageDraw.Draw(image)
                x1,y1,x2,y2 = hidden['region']
                draw.rectangle((x1,y1,x2-1,y2-1), fill=(18,23,30))
                revealed = t.pixel_visibility(image, edge, scale)
                self.assertEqual(revealed['non_foot_fraction'], 1)
                # A handful of stale/antialiased pixels cannot fake a revealed bar.
                image = Image.new('RGB', image.size, t.FOOT_COLOR)
                image.putpixel((x1,y1), (18,23,30))
                self.assertLess(t.pixel_visibility(image, edge, scale)['non_foot_fraction'], .1)

    def test_covered_window_frame_and_gap_do_not_fake_a_visible_bar(self):
        for scale in t.SCALES:
            image = Image.new('RGB', (round(1024*scale), round(768*scale)), (18, 23, 30))
            inset = round((t.FRAME + 8) * scale)
            ImageDraw.Draw(image).rectangle((inset, inset, image.width-inset-1,
                                             image.height-inset-1), fill=t.FOOT_COLOR)
            for edge in t.EDGES:
                self.assertEqual(t.pixel_visibility(image, edge, scale)['non_foot_fraction'], 0)

    def test_cli_refuses_host_before_desktop_discovery_or_mutation(self):
        result = subprocess.run([sys.executable, str(HERE/'taskbar.py'),
                                 '--disposable-guest', '--pointer', '/run/t/virtual-pointer',
                                 '--capture', '/run/t/raw-screencopy'],
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('reviewed /run/t guest bundle', result.stderr)


if __name__ == '__main__':
    unittest.main()
