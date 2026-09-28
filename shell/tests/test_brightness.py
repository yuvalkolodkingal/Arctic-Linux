"""Tests for scripts/brightness.py (display brightness in Quick Settings): parsing and the DDC
cool-down, without real hardware.

Run: python3 -m unittest discover -s shell/tests -p 'test_brightness.py'
"""
import contextlib
import importlib.util
import io
import json
import os
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
            self.assertEqual(brightness.main(['step', 'focused', '5']), 1)

    def test_monitors(self):
        text = json.dumps({'monitors': [{'name': 'eDP-1', 'active': False}, {'name': 'DP-1', 'active': True}]})
        self.assertEqual(brightness.parse_monitors(text), 'DP-1')
        self.assertEqual(brightness.parse_monitors('{"monitors": [{"name": "eDP-1"}]}'), '')
        self.assertEqual(brightness.parse_monitors('not json'), '')


FAKE_BIN = {
    'mmsg': 'cat "$FAKE_DIR/monitors.json"\n',
    'brightnessctl': ('echo "brightnessctl $*" >> "$FAKE_DIR/log"\n'
                      'if [ "$*" = "-m -c backlight" ]; then echo intel_backlight,backlight,19200,40%,48000; fi\n'),
    'ddcutil': ('echo "ddcutil $*" >> "$FAKE_DIR/log"\n'
                'case "$*" in "detect --terse") cat "$FAKE_DIR/detect.txt" ;; *getvcp*) echo "VCP 10 C 60 100" ;; esac\n'),
}


class Step(unittest.TestCase):
    """`step focused ±N` (the brightness keys) with stand-ins for mmsg, brightnessctl and ddcutil."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        for name, body in FAKE_BIN.items():
            path = self.dir / name
            path.write_text('#!/bin/sh\n' + body)
            path.chmod(0o755)
        (self.dir / 'detect.txt').write_text(DETECT)
        (self.dir / 'card1-eDP-1').mkdir()
        self.saved = (os.environ.get('PATH'), os.environ.get('FAKE_DIR'), brightness.DRM, brightness.CACHE)
        os.environ['PATH'] = '%s:%s' % (self.dir, os.environ.get('PATH', ''))
        os.environ['FAKE_DIR'] = str(self.dir)
        brightness.DRM = str(self.dir)
        brightness.CACHE = str(self.dir / 'ddc.json')

    def tearDown(self):
        path, fake, brightness.DRM, brightness.CACHE = self.saved
        os.environ['PATH'] = path or ''
        if fake is None:
            os.environ.pop('FAKE_DIR', None)
        self.tmp.cleanup()

    def focus(self, name):
        (self.dir / 'monitors.json').write_text(json.dumps({'monitors': [
            {'name': 'eDP-1', 'active': name == 'eDP-1'}, {'name': 'DP-1', 'active': name == 'DP-1'},
            {'name': 'HDMI-A-1', 'active': name == 'HDMI-A-1'}]}))
        (self.dir / 'log').write_text('')

    def log(self):
        return (self.dir / 'log').read_text().splitlines()

    def test_external_monitor(self):
        self.focus('DP-1')
        self.assertEqual(brightness.step_brightness('focused', 5),
                         {'ok': True, 'output': 'DP-1', 'percent': 65, 'label': 'DELL U2723QE'})
        self.assertIn('ddcutil --bus 5 setvcp 10 65', self.log())
        self.assertNotIn('ddcutil --bus 9 getvcp 10 --terse', self.log())     # only the focused one is asked

    def test_laptop_panel(self):
        self.focus('eDP-1')
        self.assertEqual(brightness.step_brightness('focused', -5),
                         {'ok': True, 'output': 'eDP-1', 'percent': 35, 'label': 'Built-in display'})
        self.assertIn('brightnessctl -q -d intel_backlight set 35%', self.log())
        self.assertFalse(any(line.startswith('ddcutil') for line in self.log()))

    def test_monitor_without_control_steps_the_panel(self):
        self.focus('HDMI-A-1')
        self.assertEqual(brightness.step_brightness('focused', 5)['output'], 'eDP-1')

    def test_floor(self):
        self.focus('eDP-1')
        self.assertEqual(brightness.step_brightness('eDP-1', -100)['percent'], 1)


if __name__ == '__main__':
    unittest.main()
