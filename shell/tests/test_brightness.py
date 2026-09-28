"""Tests for scripts/brightness.py (display brightness in Quick Settings): parsing and the DDC
cool-down, without real hardware.

Run: python3 -m unittest discover -s shell/tests -p 'test_brightness.py'
"""
import contextlib
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('brightness', SCRIPTS / 'brightness.py')
brightness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(brightness)

DETECT = """Display 1
   I2C bus:  /dev/i2c-5
   DRM connector:           card1-DP-1
   Monitor:                 DEL:DELL U2723QE:ABC123

Invalid display
   I2C bus:  /dev/i2c-7
   DRM connector:           card1-HDMI-A-1
   Monitor:                 GSM:LG ULTRA:XYZ

Display 2
   I2C bus:  /dev/i2c-9
   Monitor:                 AOC::
"""


class Parsing(unittest.TestCase):
    def test_brightnessctl(self):
        text = 'intel_backlight,backlight,19200,40%,48000\nkbd,leds,1,50%,2\nbad line\n'
        self.assertEqual(brightness.parse_brightnessctl(text), [{'device': 'intel_backlight', 'percent': 40}])
        self.assertEqual(brightness.parse_brightnessctl(''), [])

    def test_detect(self):
        self.assertEqual(brightness.parse_detect(DETECT), [
            {'bus': 5, 'output': 'DP-1', 'label': 'DELL U2723QE'},
            {'bus': 9, 'output': 'bus 9', 'label': 'AOC'},
        ])

    def test_vcp(self):
        self.assertEqual(brightness.parse_vcp('VCP 10 C 50 100'), 50)
        self.assertEqual(brightness.parse_vcp('VCP 10 C 30 75'), 40)
        self.assertIsNone(brightness.parse_vcp('VCP 10 ERR'))
        self.assertIsNone(brightness.parse_vcp('VCP 10 C 5 0'))

    def test_internal_output(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ('card1-DP-1', 'card1-eDP-1', 'card1-HDMI-A-1', 'card1'):
                (Path(d) / name).mkdir()
            old = brightness.DRM
            brightness.DRM = d
            try:
                self.assertEqual(brightness.internal_output(), 'eDP-1')
            finally:
                brightness.DRM = old

    def test_cooldown_after_three_failures(self):
        cache = {}
        for t in (100, 101, 102):
            self.assertFalse(brightness.cooling(cache, 5, t))
            brightness.note(cache, 5, False, t)
        self.assertTrue(brightness.cooling(cache, 5, 110))
        self.assertFalse(brightness.cooling(cache, 5, 140))       # 30 s later it is tried again
        brightness.note(cache, 5, True, 141)
        self.assertEqual(cache['failures'], {})

    def test_usage(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(brightness.main(['set', 'DP-1', 'lots']), 1)


if __name__ == '__main__':
    unittest.main()
