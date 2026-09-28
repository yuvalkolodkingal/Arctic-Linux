"""Tests for the system helpers Settings drives: arctic-nightlight (night light on wlsunset) and
arctic-keep-awake (no lock or suspend for a while), and their Settings commands.

    python3 -m unittest discover -s settings/tests -v

Each test uses the throwaway home of test_arctic_settings.Home, with the real helpers from
dotfiles/.local/bin and stand-ins for wlsunset, notify-send, swayidle and arctic-session that
record how they were called. Time and time zone come from ARCTIC_NOW and TZ.
"""
import json
import os
import signal
import subprocess
import time
import unittest

from test_arctic_settings import DOTFILES, Home, stub

BIN = DOTFILES / '.local/bin'
ZONES = 'CH\t+4723+00832\tEurope/Zurich\nDE,DK,NO,SE,SJ\t+5230+01322\tEurope/Berlin\tmost of Germany\n'


def local(*fields):
    """Epoch seconds of a local time (in the TZ the test set)."""
    return int(time.mktime(tuple(fields) + (0,) * (6 - len(fields)) + (0, 0, -1)))


class HelperHome(Home):
    def setUp(self):
        super().setUp()
        for name in ('arctic-nightlight', 'arctic-keep-awake'):
            (self.bin / name).symlink_to(BIN / name)
        self.run_dir = self.tmp / 'run'
        self.run_dir.mkdir()
        self.env['XDG_RUNTIME_DIR'] = str(self.run_dir)
        self.env['ARCTIC_NIGHTLIGHT_SETTLE'] = '0.3'
        self.env['TZ'] = 'Europe/Berlin'
        zoneinfo = self.tmp / 'zoneinfo'
        zoneinfo.mkdir()
        (zoneinfo / 'zone1970.tab').write_text(ZONES)
        self.env['ARCTIC_ZONEINFO'] = str(zoneinfo)
        os.environ['TZ'] = 'Europe/Berlin'
        time.tzset()
        stub(self.bin, 'notify-send', 'echo "notify-send $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'arctic-session', 'echo "arctic-session $*" >> "{}"\n'.format(self.log))
        self.wlsunset_log = self.tmp / 'wlsunset.log'
        stub(self.bin, 'wlsunset', '''\
            echo "$*" >> "{}"
            trap 'exit 0' TERM
            while :; do sleep 0.1; done
            '''.format(self.wlsunset_log))

    def tearDown(self):
        state = self.run_dir / 'arctic/nightlight.json'
        if state.exists():
            data = json.loads(state.read_text())
            for key in ('pid', 'timer'):
                if data.get(key):
                    try:
                        os.kill(int(data[key]), signal.SIGKILL)
                    except OSError:
                        pass
        os.environ.pop('TZ', None)
        time.tzset()
        super().tearDown()

    def tool(self, *args, at=None, ok=True):
        env = dict(self.env)
        if at is not None:
            env['ARCTIC_NOW'] = str(at)
        result = subprocess.run([str(self.bin / args[0])] + [str(a) for a in args[1:]], env=env,
                                capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout.strip().splitlines()[-1])
        self.assertEqual(bool(data.get('ok')), ok, (data, result.stderr))
        self.assertEqual(result.returncode, 0 if ok else 1)
        return data

    def wlsunset_calls(self):
        return self.wlsunset_log.read_text().splitlines() if self.wlsunset_log.exists() else []

    def wlsunset_running(self):
        data = json.loads((self.run_dir / 'arctic/nightlight.json').read_text())
        pid = data.get('pid')
        try:
            with open('/proc/{}/stat'.format(pid)) as stat:
                return bool(pid) and stat.read().rsplit(')', 1)[1].split()[0] != 'Z'
        except OSError:
            return False


class NightLightTest(HelperHome):
    def test_off_by_default(self):
        data = self.tool('arctic-nightlight', 'status', '--json')
        self.assertEqual((data['mode'], data['active'], data['temp'], data['available']), ('off', False, 4000, True))
        self.assertEqual(data['location'], 'Europe/Berlin')

    def test_custom_hours_and_overrides(self):
        noon = local(2026, 6, 21, 12, 0)
        data = self.tool('arctic-nightlight', 'set', 'mode=hours', 'from=21:30', 'to=6:30', 'temp=3500', at=noon)
        self.assertEqual((data['mode'], data['from'], data['to'], data['active']), ('hours', '21:30', '06:30', False))
        self.assertEqual(data['nextChange'], local(2026, 6, 21, 21, 30))
        self.assertEqual(self.wlsunset_calls(), ['-t 3500 -T 6500 -S 06:30 -s 21:30 -d 1800'])
        self.assertIn('temp=3500', (self.home / '.config/arctic/nightlight.conf').read_text())

        # On now: warm until the evening fade would have finished anyway.
        data = self.tool('arctic-nightlight', 'toggle', at=noon)
        self.assertEqual((data['active'], data['override']), (True, 'on'))
        self.assertEqual(data['until'], local(2026, 6, 21, 22, 15))
        self.assertEqual(self.wlsunset_calls()[-1], '-t 3500 -T 3501 -S 00:00 -s 23:59 -d 0')
        self.assertIn('notify-send -a arctic-osd', self.calls()[-1])
        self.assertTrue(self.calls()[-1].endswith('Night light on until 22:15'))
        # Toggling back follows the schedule again.
        data = self.tool('arctic-nightlight', 'toggle', '--quiet', at=noon)
        self.assertEqual((data['active'], data['override']), (False, ''))
        self.assertEqual(self.wlsunset_calls()[-1], '-t 3500 -T 6500 -S 06:30 -s 21:30 -d 1800')
        self.assertTrue(self.wlsunset_running())

        # At night, off stops wlsunset until the morning; once that has passed, apply restarts it.
        night = local(2026, 6, 21, 23, 0)
        self.assertTrue(self.tool('arctic-nightlight', 'status', '--json', at=night)['active'])
        data = self.tool('arctic-nightlight', 'off', at=night)
        self.assertEqual((data['active'], data['override'], data['untilText']), (False, 'off', '06:30'))
        self.assertFalse(self.wlsunset_running())
        data = self.tool('arctic-nightlight', 'apply', at=local(2026, 6, 22, 7, 0))
        self.assertEqual(data['override'], '')
        self.assertTrue(self.wlsunset_running())
        # Off in the Settings sense (mode=off) stops it for good.
        self.tool('arctic-nightlight', 'set', 'mode=off', at=noon)
        self.assertFalse(self.wlsunset_running())

    def test_no_schedule(self):
        data = self.tool('arctic-nightlight', 'on', '--quiet')
        self.assertEqual((data['active'], data['override'], data['until']), (True, 'on', 0))
        self.assertEqual(self.wlsunset_calls(), ['-t 4000 -T 4001 -S 00:00 -s 23:59 -d 0'])
        self.assertFalse(self.tool('arctic-nightlight', 'toggle', '--quiet')['active'])
        self.assertFalse(self.wlsunset_running())
        data = self.tool('arctic-nightlight', 'set', 'mode=always')
        self.assertTrue(data['active'])
        data = self.tool('arctic-nightlight', 'off', '--quiet')
        self.assertEqual((data['active'], data['override'], data['until']), (False, 'off', 0))

    def test_sunset_follows_the_time_zone(self):
        data = self.tool('arctic-nightlight', 'set', 'mode=sunset', at=local(2026, 6, 21, 12, 0))
        self.assertEqual((data['location'], data['fallback'], data['active']), ('Europe/Berlin', False, False))
        self.assertEqual(self.wlsunset_calls(), ['-t 4000 -T 6500 -l 52.5 -L 13.3667'])
        self.assertEqual(data['nextChangeText'], '21:34')      # sunset in Berlin at midsummer
        self.assertTrue(self.tool('arctic-nightlight', 'status', '--json', at=local(2026, 6, 21, 23, 0))['active'])
        self.assertFalse(self.tool('arctic-nightlight', 'status', '--json', at=local(2026, 6, 22, 5, 0))['active'])
        # A manual location wins; a zone without one falls back to the custom hours.
        data = self.tool('arctic-nightlight', 'set', 'lat=47.3769', 'lon=8.5417')
        self.assertEqual(data['location'], 'manual')
        self.assertEqual(self.wlsunset_calls()[-1], '-t 4000 -T 6500 -l 47.3769 -L 8.5417')
        self.env['TZ'] = 'UTC'
        data = self.tool('arctic-nightlight', 'set', 'lat=', 'lon=')
        self.assertTrue(data['fallback'])
        self.assertEqual(self.wlsunset_calls()[-1], '-t 4000 -T 6500 -S 07:00 -s 20:00 -d 1800')

    def test_bad_values(self):
        for arg in ('mode=dusk', 'temp=9000', 'temp=warm', 'from=25:00', 'lat=91', 'colour=red'):
            with self.subTest(arg):
                self.assertTrue(self.tool('arctic-nightlight', 'set', arg, ok=False)['error'])
        self.assertIn('evening', self.tool('arctic-nightlight', 'set', 'from=06:00', 'to=07:00', ok=False)['error'])
        self.assertIn('both', self.tool('arctic-nightlight', 'set', 'lat=10', ok=False)['error'])
        self.assertFalse((self.home / '.config/arctic/nightlight.conf').exists())
        # A broken hand edit falls back to the default.
        (self.home / '.config/arctic/nightlight.conf').write_text('mode=sometimes\ntemp=3000\n')
        data = self.tool('arctic-nightlight', 'status', '--json')
        self.assertEqual((data['mode'], data['temp']), ('off', 3000))

    def test_screen_without_gamma_control(self):
        stub(self.bin, 'wlsunset', 'echo "failed to create gamma control" >&2; exit 1\n')
        data = self.tool('arctic-nightlight', 'on', '--quiet')
        self.assertIn('change its colours', data['error'])
        self.assertFalse(data['running'])
        # wlsunset 0.4 keeps running when every screen refuses; one screen that works is enough.
        stub(self.bin, 'wlsunset', '''\
            echo "registry: adding output 51"; echo "registry: adding output 52"
            echo "gamma control of output HEADLESS-1 (51) failed"
            [ -n "$ALL" ] && echo "gamma control of output HEADLESS-2 (52) failed"
            trap 'exit 0' TERM
            while :; do sleep 0.1; done
            ''')
        data = self.tool('arctic-nightlight', 'set', 'mode=always')
        self.assertEqual((data['error'], data['running']), ('', True))
        self.env['ALL'] = '1'
        data = self.tool('arctic-nightlight', 'set', 'temp=3000')
        self.assertIn('change its colours', data['error'])
        self.assertFalse(data['running'])

    def test_settings_commands(self):
        data = self.helper('nightlight')
        self.assertEqual((data['helper'], data['mode']), (True, 'off'))
        data = self.helper('nightlight-set', 'mode=always', 'temp=3000')
        self.assertEqual((data['mode'], data['temp'], data['active']), ('always', 3000, True))
        self.assertTrue(self.helper('nightlight-set', 'now', 'off')['override'] == 'off')
        self.assertIn('warmth', self.helper('nightlight-set', 'temp=100', ok=False)['error'])
        self.helper('nightlight-set', 'wlsunset=-x', ok=False)
        self.helper('nightlight-set', 'now', 'maybe', ok=False)
        self.assertFalse(any('notify-send' in c for c in self.calls()))   # Settings is quiet
        (self.bin / 'arctic-nightlight').unlink()
        self.assertFalse(self.helper('nightlight')['helper'])


class KeepAwakeTest(HelperHome):
    def setUp(self):
        super().setUp()
        # The expiry timer is recorded, not started; everything else runs.
        stub(self.bin, 'setsid', '''\
            case "$*" in *_expire*) echo "setsid $*" >> "{}"; exit 0 ;; esac
            shift; exec "$@"
            '''.format(self.log))

    @property
    def state(self):
        return self.run_dir / 'arctic/keep-awake'

    def test_on_off_and_idle(self):
        self.assertFalse(self.tool('arctic-keep-awake', 'status', '--json')['on'])
        data = self.tool('arctic-keep-awake', 'on', 30)
        self.assertTrue(data['on'])
        self.assertIn(data['minutesLeft'], (30, 31))
        self.assertEqual(int(self.state.read_text()), data['until'])
        self.assertIn('arctic-session idle --restart', self.calls())
        self.assertTrue(any(c.startswith('setsid -f') and c.endswith('_expire {}'.format(data['until'])) for c in self.calls()))
        self.assertTrue(self.calls()[-1].startswith('notify-send') and 'Keep awake on until' in self.calls()[-1])
        # swayidle keeps only "lock before sleep" while it's on.
        ran = self.tmp / 'swayidle.log'
        (self.bin / 'arctic-session').unlink()
        (self.bin / 'arctic-session').symlink_to(BIN / 'arctic-session')
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'swayidle', 'echo "$*" >> "{}"\n'.format(ran))
        subprocess.run(['bash', str(BIN / 'arctic-session'), 'idle'], env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().strip(), '-w before-sleep arctic-lock')
        data = self.tool('arctic-keep-awake', 'toggle', '--quiet')
        self.assertFalse(data['on'])
        self.assertFalse(self.state.exists())
        self.assertEqual(ran.read_text().splitlines()[-1],
                         '-w timeout 300 arctic-lock timeout 900 systemctl suspend before-sleep arctic-lock')

    def test_until_turned_off_and_expiry(self):
        data = self.tool('arctic-keep-awake', 'toggle')
        self.assertEqual((data['on'], data['until']), (True, 0))
        self.assertFalse(any('_expire' in c for c in self.calls()))
        # The timer only ends the run it was started for.
        self.state.write_text('{}\n'.format(int(time.time()) - 5))
        self.assertFalse(self.tool('arctic-keep-awake', 'status', '--json')['on'])
        past = int(time.time()) - 1
        self.state.write_text('{}\n'.format(past + 3600))
        subprocess.run([str(self.bin / 'arctic-keep-awake'), '_expire', str(past)], env=self.env, check=True, timeout=10)
        self.assertTrue(self.state.exists())
        self.state.write_text('{}\n'.format(past))
        subprocess.run([str(self.bin / 'arctic-keep-awake'), '_expire', str(past)], env=self.env, check=True, timeout=10)
        self.assertFalse(self.state.exists())

    def test_bad_minutes(self):
        self.tool('arctic-keep-awake', 'on', 'soon', ok=False)
        self.tool('arctic-keep-awake', 'on', 5000, ok=False)
        self.assertFalse(self.state.exists())

    def test_settings_command(self):
        self.assertFalse(self.helper('keep-awake')['on'])
        self.assertTrue(self.helper('keep-awake', 'on', 60)['on'])
        self.assertFalse(self.helper('keep-awake', 'off')['on'])
        self.helper('keep-awake', 'on', 'x', ok=False)
        self.assertFalse(any(c.startswith('notify-send') for c in self.calls()))


if __name__ == '__main__':
    unittest.main()
