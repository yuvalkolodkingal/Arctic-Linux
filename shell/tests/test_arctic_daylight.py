"""Tests for arctic-daylight (dotfiles/.local/bin): sunrise and sunset from the time zone, what the
schedule wants when, and applying it with stand-ins for arctic-theme, systemd-run and systemctl.

Run: python3 -m unittest discover -s shell/tests
"""
import importlib.machinery
import importlib.util
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-daylight'
ZONE1970 = ('# tzdb timezone descriptions\n'
            'IL\t+314650+0351326\tAsia/Jerusalem\n'
            'DE,DK,NO,SE,SJ\t+5230+01322\tEurope/Berlin\n'
            'NO\t+6940+01858\tArctic/Tromso\n')


def load():
    sys.dont_write_bytecode = True     # nothing written next to the helper
    loader = importlib.machinery.SourceFileLoader('arctic_daylight', str(HELPER))
    spec = importlib.util.spec_from_loader('arctic_daylight', loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def utc(ts):
    return datetime.fromtimestamp(ts, timezone.utc)


class SunTests(unittest.TestCase):
    def assertNear(self, ts, hour, minute, slack=6):
        got = utc(ts)
        self.assertLessEqual(abs((got.hour * 60 + got.minute) - (hour * 60 + minute)), slack, got)

    def test_known_places(self):
        d = load()
        # Jerusalem, 28 September 2026: about 03:33 and 15:30 UTC (06:33 and 18:30 local), a day
        # just under 12 hours long, a few days after the equinox.
        rise, fall = d.sun_times(date(2026, 9, 28), 31.78, 35.22)
        self.assertNear(rise, 3, 33)
        self.assertNear(fall, 15, 30)
        # Berlin at midsummer: about 02:43 and 19:33 UTC.
        rise, fall = d.sun_times(date(2026, 6, 21), 52.5, 13.37)
        self.assertNear(rise, 2, 43)
        self.assertNear(fall, 19, 33)
        # Tromsø: the midnight sun in June, polar night in December.
        self.assertEqual(d.sun_times(date(2026, 6, 21), 69.67, 18.97), (None, None))
        self.assertEqual(d.sun_times(date(2026, 12, 21), 69.67, 18.97), (None, None))

    def test_coordinates(self):
        d = load()
        lat, lon = d.parse_coordinates('+314650+0351326')
        self.assertAlmostEqual(lat, 31.7806, places=3)
        self.assertAlmostEqual(lon, 35.2239, places=3)
        self.assertEqual(d.parse_coordinates('-3352+15113'), (-(33 + 52 / 60), 151 + 13 / 60))
        self.assertIsNone(d.parse_coordinates('nonsense'))


class ScheduleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'zoneinfo').mkdir()
        (root / 'zoneinfo' / 'zone1970.tab').write_text(ZONE1970)
        self.bin = root / 'bin'
        self.bin.mkdir()
        self.log = root / 'calls'
        self.mode = root / 'mode'
        self.mode.write_text('dark')

        def stub(name, body):
            (self.bin / name).write_text('#!/bin/sh\n' + body + '\n')
            (self.bin / name).chmod(0o755)
        stub('arctic-theme', 'echo "arctic-theme $*" >> "{0}"\n'
                             'case "$1" in current) echo "{{\\"mode\\": \\"$(cat {1})\\"}}" ;; light|dark) echo "$1" > {1} ;; esac'
             .format(self.log, self.mode))
        stub('systemd-run', 'echo "systemd-run $*" >> "{}"'.format(self.log))
        stub('systemctl', 'echo "systemctl $*" >> "{}"'.format(self.log))
        self.env = dict(os.environ, XDG_CONFIG_HOME=str(root / 'config'), PATH=str(self.bin) + ':/usr/bin:/bin',
                        ARCTIC_ZONEINFO=str(root / 'zoneinfo'), ARCTIC_TIMEZONE='Asia/Jerusalem', TZ='Asia/Jerusalem')

    def tearDown(self):
        self.tmp.cleanup()

    def daylight(self, *args, code=0):
        out = subprocess.run([sys.executable, str(HELPER)] + list(args), env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stdout + out.stderr)
        return json.loads(out.stdout) if out.stdout.startswith('{') else out.stdout

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_off_by_default(self):
        info = self.daylight('--json')
        self.assertEqual((info['mode'], info['want'], info['next']), ('off', None, None))
        self.assertTrue(info['located'])

    def test_hours_switch_now_and_set_the_next_change(self):
        # Light from 00:00 to 23:59 means light now, whatever the time.
        info = self.daylight('hours', '00:00', '23:59')
        self.assertEqual((info['mode'], info['want']), ('hours', 'light'))
        self.assertEqual(self.mode.read_text().strip(), 'light')
        self.assertIn('arctic-theme light', self.calls())
        timer = [c for c in self.calls() if c.startswith('systemd-run')][-1]
        self.assertIn('--unit arctic-daylight', timer)
        self.assertIn('--on-calendar', timer)
        self.assertTrue(timer.endswith('arctic-daylight apply'))
        # Already light: applying again doesn't switch again.
        before = len([c for c in self.calls() if c in ('arctic-theme light', 'arctic-theme dark')])
        self.daylight('apply')
        self.assertEqual(len([c for c in self.calls() if c in ('arctic-theme light', 'arctic-theme dark')]), before)

    def test_off_stops_the_timer_and_leaves_the_theme(self):
        self.daylight('sun')
        self.log.write_text('')
        info = self.daylight('off')
        self.assertEqual(info['want'], None)
        self.assertEqual(self.calls(), ['systemctl --user stop arctic-daylight.timer'])

    def test_sun_where_the_zone_is(self):
        info = self.daylight('sun')
        self.assertEqual(info['zone'], 'Asia/Jerusalem')
        light, dark = info['today']['light'], info['today']['dark']
        self.assertTrue('04:00' < light < '08:00' and '16:00' < dark < '20:30', info)
        # An unknown zone: the custom hours, and it says why.
        self.env['ARCTIC_TIMEZONE'] = 'Mars/Olympus'
        info = self.daylight('--json')
        self.assertFalse(info['located'])
        self.assertEqual(info['today'], {'light': '07:00', 'dark': '19:00'})
        self.assertIn('time zone', info['message'])

    def test_plan_across_midnight(self):
        d = load()
        data = {'mode': 'hours', 'light': '07:00', 'dark': '19:00'}
        want, nxt, _ = d.plan(data, datetime(2026, 9, 28, 23, 0), None)
        self.assertEqual((want, nxt), ('dark', datetime(2026, 9, 29, 7, 0)))
        want, nxt, _ = d.plan(data, datetime(2026, 9, 28, 12, 0), None)
        self.assertEqual((want, nxt), ('light', datetime(2026, 9, 28, 19, 0)))

    def test_refuses_bad_hours(self):
        self.assertFalse(self.daylight('hours', '25:00', '07:00', code=1)['ok'])
        self.assertFalse(self.daylight('hours', '07:00', '07:00', code=1)['ok'])
        self.assertFalse(self.daylight('sometimes', code=1)['ok'])


if __name__ == '__main__':
    unittest.main()
