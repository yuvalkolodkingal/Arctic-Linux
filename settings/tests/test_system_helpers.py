"""Tests for the system features Settings drives: arctic-nightlight (night light on wlsunset),
arctic-keep-awake (no lock or suspend for a while), XDG autostart, printers (CUPS) and date,
time and language (timedatectl, localectl), with their Settings commands.

    python3 -m unittest discover -s settings/tests -v

Each test uses the throwaway home of test_arctic_settings.Home, with the real helpers from
dotfiles/.local/bin and stand-ins for wlsunset, notify-send, swayidle, arctic-session, lpstat,
timedatectl and the like that record how they were called. Time and time zone come from
ARCTIC_NOW and TZ.
"""
import json
import os
import signal
import subprocess
import textwrap
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


class AutostartTest(Home):
    """Apps' own "start on login" entries (XDG autostart) in Settings > Startup apps."""

    def entry(self, folder, name, *lines):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (name + '.desktop')
        path.write_text('[Desktop Entry]\nType=Application\n' + ''.join(line + '\n' for line in lines))
        return path

    def test_list_and_switch(self):
        system = self.tmp / 'xdg/autostart'
        self.env['XDG_CONFIG_DIRS'] = str(self.tmp / 'xdg')
        discord = self.entry(system, 'discord', 'Name=Discord', 'Exec=/usr/bin/discord --start-minimized %U')
        self.entry(system, 'nm-applet', 'Name=NetworkManager Applet', 'Exec=nm-applet', 'NotShowIn=KDE;GNOME;')
        self.entry(system, 'gnome-keyring-ssh', 'Name=SSH Key Agent', 'Exec=gnome-keyring-daemon', 'OnlyShowIn=GNOME;Unity;MATE;')
        self.entry(system, 'xdg-user-dirs', 'Name=User folders', 'Exec=xdg-user-dirs-update', 'X-systemd-skip=true')
        self.entry(system, 'gone', 'Name=Gone', 'Exec=gone', 'TryExec=/nonexistent/gone')
        self.entry(system, 'off-by-vendor', 'Name=Off', 'Exec=off', 'Hidden=true')
        self.entry(system, 'fcitx5', 'Name=Fcitx 5', 'Exec=/usr/bin/fcitx5', 'OnlyShowIn=mango;KDE;',
                   '', '[Desktop Action Quit]', 'Name=Quit')
        user = self.home / '.config/autostart'
        self.entry(user, 'syncthing', 'Name=Syncthing', 'Exec=syncthing serve --no-browser', 'Comment=Sync files')
        data = self.helper('autostart')
        self.assertEqual([e['id'] for e in data['entries']], ['discord', 'fcitx5', 'syncthing'])
        self.assertEqual(data['entries'][0]['exec'], '/usr/bin/discord --start-minimized')
        self.assertTrue(all(e['enabled'] for e in data['entries']))

        # Off: a copy with Hidden=true in ~/.config/autostart, in [Desktop Entry] only.
        data = self.helper('autostart-set', 'fcitx5', 'off')
        copy = (user / 'fcitx5.desktop').read_text()
        self.assertEqual(copy.split('[Desktop Action Quit]')[0].count('Hidden=true'), 1)
        self.assertNotIn('Hidden', copy.split('[Desktop Action Quit]')[1])
        self.assertFalse(next(e for e in data['entries'] if e['id'] == 'fcitx5')['enabled'])
        # On again: nothing of yours is left, so the copy goes and the app's own file counts.
        self.helper('autostart-set', 'fcitx5', 'on')
        self.assertFalse((user / 'fcitx5.desktop').exists())
        # Your own entries are edited in place.
        self.helper('autostart-set', 'syncthing', 'off')
        self.assertIn('Hidden=true', (user / 'syncthing.desktop').read_text())
        self.helper('autostart-set', 'syncthing', 'on')
        self.assertNotIn('Hidden', (user / 'syncthing.desktop').read_text())
        self.assertTrue(discord.exists())

        self.helper('autostart-set', 'nm-applet', 'off', ok=False)      # Arctic starts it itself
        self.helper('autostart-set', '../evil', 'off', ok=False)
        self.helper('autostart-set', 'discord', 'maybe', ok=False)

    def test_packaging(self):
        """The drop-ins the spec installs: the session wants the autostart target, and the
        entries Settings hides are the ones Arctic switches off."""
        import arctic_system as S
        root = DOTFILES.parent / 'packaging/desktop/autostart'
        self.assertIn('Wants=xdg-desktop-autostart.target', (root / 'mango-session-autostart.conf').read_text())
        self.assertIn('ConditionEnvironment=!XDG_CURRENT_DESKTOP=mango', (root / 'arctic-starts-it.conf').read_text())
        spec = (DOTFILES.parent / 'packaging/arctic-linux.spec').read_text()
        self.assertIn('mango-session.target.d/arctic-autostart.conf', spec)
        for ident in S.ARCTIC_AUTOSTART:
            self.assertIn("'{}'".format(ident.replace('-', '\\x2d')), spec)


LSBLK = {'blockdevices': [
    {'name': 'nvme0n1', 'path': '/dev/nvme0n1', 'type': 'disk', 'rm': False, 'hotplug': False, 'size': 512110190592,
     'children': [{'name': 'nvme0n1p1', 'path': '/dev/nvme0n1p1', 'type': 'part', 'mountpoints': ['/boot/efi']}]},
    {'name': 'sda', 'path': '/dev/sda', 'type': 'disk', 'rm': True, 'hotplug': True, 'size': 31914983424,
     'vendor': 'SanDisk ', 'model': 'Ultra', 'tran': 'usb', 'mountpoints': [None],
     'children': [{'name': 'sda1', 'path': '/dev/sda1', 'type': 'part', 'label': 'PHOTOS',
                   'mountpoints': ['/run/media/you/PHOTOS']}]},
    {'name': 'sdb', 'path': '/dev/sdb', 'type': 'disk', 'rm': True, 'hotplug': True, 'size': 0},   # empty card reader
]}


class DrivesTest(HelperHome):
    def setUp(self):
        super().setUp()
        (self.bin / 'arctic-drives').symlink_to(BIN / 'arctic-drives')
        (self.tmp / 'lsblk.json').write_text(json.dumps(LSBLK))
        stub(self.bin, 'lsblk', '''\
            echo "lsblk $*" >> "{0}"
            case "$*" in
              *" /dev/sda") echo '{{"blockdevices": [{{"path": "/dev/sda", "mountpoint": null}}, {{"path": "/dev/sda1", "mountpoint": "/run/media/you/PHOTOS"}}]}}' ;;
              *) cat "{1}" ;;
            esac
            '''.format(self.log, self.tmp / 'lsblk.json'))
        stub(self.bin, 'udisksctl', '''\
            echo "udisksctl $*" >> "{}"
            if [ -n "$BUSY" ] && [ "$1" = unmount ]; then echo "Error unmounting /dev/sda1: target is busy" >&2; exit 1; fi
            '''.format(self.log))

    def test_list_and_eject(self):
        data = self.tool('arctic-drives', 'list')
        self.assertEqual(data['drives'], [dict(device='/dev/sda', name='PHOTOS', model='SanDisk Ultra', size=31914983424,
                                               bus='usb', mounts=['/run/media/you/PHOTOS'])])
        data = self.tool('arctic-drives', 'eject', '/dev/sda')
        self.assertEqual((data['name'], data['poweredOff']), ('PHOTOS', True))
        self.assertIn('udisksctl unmount --block-device /dev/sda1 --no-user-interaction', self.calls())
        self.assertEqual(self.calls()[-1], 'udisksctl power-off --block-device /dev/sda --no-user-interaction')
        self.env['BUSY'] = '1'
        self.assertIn('still using PHOTOS', self.tool('arctic-drives', 'eject', '/dev/sda', ok=False)['error'])
        self.tool('arctic-drives', 'eject', '/dev/nvme0n1', ok=False)     # not removable
        self.tool('arctic-drives', 'eject', '/dev/../etc', ok=False)

    def test_session_starts_udiskie(self):
        ran = self.tmp / 'udiskie.log'
        stub(self.bin, 'udiskie', 'echo "$*" >> "{}"\n'.format(ran))
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        session = ['bash', str(BIN / 'arctic-session'), 'drives']
        subprocess.run(session, env=self.env, check=True, timeout=10)
        (self.home / '.config/arctic/drives.conf').write_text('automount=off\n')
        subprocess.run(session, env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().splitlines(), ['--automount --notify --no-tray', '--no-automount --notify --no-tray'])
        stub(self.bin, 'arctic-is-live', 'exit 0\n')          # never in the live session
        subprocess.run(session, env=self.env, check=True, timeout=10)
        self.assertEqual(len(ran.read_text().splitlines()), 2)


WLR_RANDR = [{'name': 'eDP-1', 'description': 'BOE 0x0BCA', 'enabled': True},
             {'name': 'HDMI-A-1', 'description': 'Dell U2720Q', 'enabled': True}]


class DisplayTest(HelperHome):
    def setUp(self):
        super().setUp()
        for name in ('arctic-display', 'arctic-effects'):
            (self.bin / name).symlink_to(BIN / name)
        self.outputs = self.tmp / 'wlr-randr.json'
        self.outputs.write_text(json.dumps(WLR_RANDR))
        stub(self.bin, 'wlr-randr', 'cat "{}"\n'.format(self.outputs))
        self.lid = self.tmp / 'lid/LID0/state'
        self.lid.parent.mkdir(parents=True)
        self.lid.write_text('state:      open\n')
        self.env['ARCTIC_LID_GLOB'] = str(self.tmp / 'lid/*/state')
        stub(self.bin, 'arctic-lock', 'echo "arctic-lock" >> "{}"\n'.format(self.log))

    def dispatches(self):
        return [c.split(' ', 2)[2] for c in self.calls() if c.startswith('mmsg dispatch')]

    def test_modes(self):
        data = self.tool('arctic-display', 'status', '--json')
        self.assertEqual((data['mode'], data['choices']), ('extend', ['laptop', 'extend', 'external']))
        self.tool('arctic-display', 'mode', 'laptop')
        self.assertEqual(self.dispatches(), ['enable_monitor,eDP-1', 'disable_monitor,HDMI-A-1'])
        self.assertTrue(self.calls()[-1].endswith('Laptop screen only'))
        self.tool('arctic-display', 'mode', 'external')
        self.assertEqual(self.dispatches()[-2:], ['enable_monitor,HDMI-A-1', 'disable_monitor,eDP-1'])
        self.assertIn('Duplicating needs wl-mirror', self.tool('arctic-display', 'mode', 'mirror', ok=False)['error'])
        stub(self.bin, 'wl-mirror', 'echo "wl-mirror $*" >> "{}"\nexec sleep 30\n'.format(self.log))
        data = self.tool('arctic-display', 'mode', 'mirror')
        self.assertEqual(data['mode'], 'mirror')
        state = json.loads((self.run_dir / 'arctic/display.json').read_text())
        self.assertEqual(len(state['mirrors']), 1)
        for pid in state['mirrors']:
            os.kill(pid, signal.SIGKILL)
        self.tool('arctic-display', 'mode', 'sideways', ok=False)
        self.outputs.write_text(json.dumps(WLR_RANDR[:1]))
        self.assertIn('Only one screen', self.tool('arctic-display', 'mode', 'laptop', ok=False)['error'])

    def test_lid(self):
        # Not really closed (a tablet-mode switch fires the same binding): nothing happens.
        self.assertEqual(self.tool('arctic-display', 'lid-closed')['done'], 'nothing')
        self.lid.write_text('state:      closed\n')
        self.assertEqual(self.tool('arctic-display', 'lid-closed')['done'], 'laptop screen off')
        self.assertEqual(self.dispatches(), ['disable_monitor,eDP-1'])
        self.assertEqual(self.tool('arctic-display', 'lid-opened')['done'], 'laptop screen on')
        self.assertEqual(self.dispatches()[-1], 'enable_monitor,eDP-1')
        # Alone: what lid.conf says (suspend = logind's job, nothing here).
        self.outputs.write_text(json.dumps([WLR_RANDR[0], dict(WLR_RANDR[1], enabled=False)]))
        self.assertEqual(self.tool('arctic-display', 'lid-closed')['done'], 'nothing')
        self.helper('lid-set', 'lock')
        self.assertIn('arctic-session lid --restart', self.calls())
        self.assertEqual(self.tool('arctic-display', 'lid-closed')['done'], 'locked')
        self.assertIn('arctic-lock', self.calls())
        self.assertEqual(self.dispatches()[-1], 'sleep_monitor,eDP-1')
        self.assertEqual(self.tool('arctic-display', 'lid-opened')['done'], 'screen on')
        self.assertEqual(self.dispatches()[-1], 'wakeup_monitor,eDP-1')
        self.env['ARCTIC_FORCE_LID'] = '1'
        self.assertEqual(self.helper('lid')['whenClosed'], 'lock')
        self.helper('lid-set', 'hibernate', ok=False)

    def test_session_holds_the_lid_switch(self):
        ran = self.tmp / 'inhibit.log'
        stub(self.bin, 'systemd-inhibit', 'echo "$*" >> "{}"\n'.format(ran))
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        session = ['bash', str(BIN / 'arctic-session'), 'lid']
        subprocess.run(session, env=self.env, check=True, timeout=10)
        self.assertFalse(ran.exists())                       # suspend: logind's default
        (self.home / '.config/arctic/lid.conf').write_text('when_closed=screen-off\n')
        subprocess.run(session, env=self.env, check=True, timeout=10)
        self.assertIn('--what=handle-lid-switch --who=Arctic Linux', ran.read_text())

    def test_effects(self):
        mango = self.home / '.config/mango/config.conf'
        old = mango.read_text().replace('source-optional=~/.config/arctic/effects.conf\n', '')
        mango.write_text(old)
        stub(self.bin, 'systemd-detect-virt', 'exit 0\n')
        data = self.tool('arctic-effects', 'lighter', 'auto')
        self.assertEqual((data['lighter_active'], data['reason']), (True, 'vm'))
        lines = mango.read_text().splitlines()
        self.assertEqual(lines.index('source-optional=~/.config/arctic/effects.conf') + 1,
                         lines.index('source-optional=~/.config/mango/user.conf'))
        self.assertTrue(list((self.home / '.local/state/arctic/settings-backups').glob('config.conf.*')))
        conf = (self.home / '.config/arctic/effects.conf').read_text()
        self.assertIn('# Lighter effects (virtual machine)\nanimations=0', conf)
        self.assertIn('mmsg dispatch reload_config', self.calls())
        # Game mode adds no gaps; a login (apply) turns it off again.
        self.assertTrue(self.helper('effects-set', 'game', 'on')['game'])
        self.assertIn('gappih=0', (self.home / '.config/arctic/effects.conf').read_text())
        reloads = self.calls().count('mmsg dispatch reload_config')
        self.tool('arctic-effects', 'game', 'on', '--quiet')
        self.assertEqual(self.calls().count('mmsg dispatch reload_config'), reloads)   # nothing changed
        self.assertFalse(self.tool('arctic-effects', 'apply')['game'])
        stub(self.bin, 'systemd-detect-virt', 'exit 1\n')
        self.env['ARCTIC_EFFECTS_DRI'] = str(self.tmp)                       # no renderD* here
        self.assertEqual(self.tool('arctic-effects', 'status', '--json')['reason'], 'software')
        (self.tmp / 'renderD128').write_text('')
        data = self.helper('effects-set', 'lighter', 'off')
        self.assertEqual((data['lighter_active'], data['reason']), (False, ''))
        self.assertNotIn('animations=0', (self.home / '.config/arctic/effects.conf').read_text())
        self.assertEqual(mango.read_text().count('source-optional=~/.config/arctic/effects.conf'), 1)
        self.helper('effects-set', 'game', 'maybe', ok=False)


class MoreUpdatesTest(Home):
    def test_missing(self):
        data = self.helper('more-updates')
        self.assertEqual((data['available'], data['firmware']['available']), (False, False))
        self.helper('more-update-run', 'apps', ok=False)

    def test_apps_and_firmware(self):
        stub(self.bin, 'arctic-update', '''\
            echo "arctic-update $*" >> "{}"
            case "$1 $2" in
              "status --json") echo '{{"state": "idle", "auto": "download-and-install-on-reboot", "apps": {{"state": "idle", "checked_at": "2026-09-28T10:00:00+00:00", "updated": 2, "message": "2 apps updated."}}}}' ;;
              "firmware --json") echo '{{"available": true, "devices": [{{"name": "System Firmware", "version": "0.1.40", "update": "0.1.42", "summary": "", "vendor": "", "reboot": true}}], "error": ""}}' ;;
            esac
            '''.format(self.log))
        stub(self.bin, 'flatpak', 'exit 0\n')
        data = self.helper('more-updates')
        self.assertEqual((data['flatpak'], data['auto'], data['apps']['updated']), (True, True, 2))
        self.assertEqual(data['firmware']['devices'][0]['update'], '0.1.42')
        self.helper('more-update-run', 'apps')
        self.helper('more-update-run', 'firmware')
        self.helper('more-update-run', 'kernel', ok=False)
        for _ in range(50):
            if 'arctic-update firmware install' in self.calls():
                break
            time.sleep(0.1)
        self.assertIn('arctic-update flatpak --notify', self.calls())
        self.assertIn('arctic-update firmware install', self.calls())

    def test_upgrade(self):
        self.assertFalse(self.helper('upgrade')['available'])
        stub(self.bin, 'arctic-update', '''\
            echo '{"ok": true, "available": true, "current": 44, "next": 45, "notes": "https://example.org"}'
            ''')
        data = self.helper('upgrade', 'check')
        self.assertEqual((data['available'], data['next']), (True, 45))
        stub(self.bin, 'arctic-open', 'echo "arctic-open $*" >> "{}"\n'.format(self.log))
        self.helper('upgrade', 'download')
        for _ in range(50):
            if self.calls():
                break
            time.sleep(0.1)
        self.assertEqual(self.calls(), ['arctic-open terminal --hold -e arctic-update upgrade download'])
        self.helper('upgrade', 'now', ok=False)


LPSTAT = r'''
echo "lpstat $* LC_ALL=$LC_ALL" >> "{log}"
case "$*" in
  "-l -p") printf 'printer Brother disabled since Mon Sep 28 20:16:11 2026 -\n\tPaused\n\tForm mounted:\n\tDescription: Brother HL\n\tLocation: \nprinter Office_Laser is idle.  enabled since Mon Sep 28 20:16:11 2026\n\tDescription: HP LaserJet Pro M404\n\tLocation: Office\n' ;;
  "-d") echo "system default destination: Office_Laser" ;;
  "-o") printf 'Brother-1               you              1024   Mon Sep 28 20:16:11 2026\nBrother-2   you   1   Mon\n' ;;
  "-e") printf 'Brother\nOffice_Laser\nCanon_TS5300_series\n' ;;
esac
'''


class PrintersTest(Home):
    def test_missing(self):
        self.assertFalse(self.helper('printers')['available'])

    def test_list_default_cancel(self):
        stub(self.bin, 'lpstat', LPSTAT.format(log=self.log))
        stub(self.bin, 'lpoptions', 'echo "lpoptions $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'cancel', 'echo "cancel $*" >> "{}"\n'.format(self.log))
        stub(self.bin, 'system-config-printer', 'exit 0\n')
        data = self.helper('printers')
        self.assertEqual([(p['name'], p['state'], p['default'], p['jobs']) for p in data['printers']],
                         [('Brother', 'paused', False, 2), ('Office_Laser', 'idle', True, 0)])
        self.assertEqual(data['printers'][1]['location'], 'Office')
        self.assertEqual(data['network'], [dict(name='Canon_TS5300_series', default=False)])
        self.assertEqual((data['canAdd'], data['scan']), (True, False))
        self.assertTrue(all(c.endswith('LC_ALL=C') for c in self.calls() if c.startswith('lpstat')))
        self.helper('printer-default', 'Brother')
        self.helper('printer-cancel', 'Brother')
        self.assertIn('lpoptions -d Brother', self.calls())
        self.assertIn('cancel -a Brother', self.calls())
        self.helper('printer-default', 'a b', ok=False)
        self.helper('printer-cancel', '../x', ok=False)


class DateTimeTest(Home):
    def setUp(self):
        super().setUp()
        stub(self.bin, 'timedatectl', textwrap.dedent('''\
            echo "timedatectl $*" >> "{}"
            case "$1" in
              show) printf 'Timezone=Europe/Berlin\\nNTP=yes\\nNTPSynchronized=yes\\nCanNTP=yes\\n' ;;
              list-timezones) printf 'Asia/Jerusalem\\nEurope/Berlin\\nAmerica/Argentina/Buenos_Aires\\nUTC\\n' ;;
              set-*) if [ -n "$DENY" ]; then echo "Failed to set time zone: Access denied" >&2; exit 1; fi ;;
            esac
            exit 0
            ''').format(self.log))
        stub(self.bin, 'localectl', textwrap.dedent('''\
            echo "localectl $*" >> "{}"
            case "$1" in
              status) printf '   System Locale: LANG=en_US.UTF-8\\n       VC Keymap: us\\n' ;;
              list-locales) printf 'C.UTF-8\\nde_DE.UTF-8\\nen_US.UTF-8\\nhe_IL.UTF-8\\nsr_RS.UTF-8@latin\\n' ;;
            esac
            exit 0
            ''').format(self.log))

    def test_read(self):
        data = self.helper('datetime', 'zones', 'locales')
        self.assertEqual((data['timezone'], data['ntp'], data['ntpSynced'], data['locale']),
                         ('Europe/Berlin', True, True, 'en_US.UTF-8'))
        self.assertIn('America/Argentina/Buenos_Aires', data['zones'])
        self.assertEqual(data['locales'], ['de_DE.UTF-8', 'en_US.UTF-8', 'he_IL.UTF-8'])
        self.assertEqual(self.helper('datetime')['zones'], [])

    def test_changes(self):
        self.helper('datetime-set', 'timezone', 'Asia/Jerusalem')
        self.helper('datetime-set', 'ntp', 'off')
        self.helper('datetime-set', 'locale', 'he_IL.UTF-8')
        for expected in ('timedatectl set-timezone Asia/Jerusalem', 'timedatectl set-ntp false',
                         'localectl set-locale LANG=he_IL.UTF-8'):
            self.assertIn(expected, self.calls())
        self.assertIn('Turn off', self.helper('datetime-set', 'time', '2026-09-28 21:30', ok=False)['error'])
        for args in (('timezone', 'Mars/Olympus'), ('timezone', '../../etc/passwd'), ('locale', 'xx_XX.UTF-8'),
                     ('time', 'tomorrow'), ('ntp', 'maybe'), ('colour', 'red')):
            with self.subTest(args):
                self.helper('datetime-set', *args, ok=False)
        self.env['DENY'] = '1'
        self.assertIn('password', self.helper('datetime-set', 'timezone', 'UTC', ok=False)['error'])


if __name__ == '__main__':
    unittest.main()
