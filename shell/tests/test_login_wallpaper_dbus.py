"""Actual IPC, caller credentials, race rejection, restart and CLI sync in a private bus.
The session-only test daemon cannot disable authorization on the production system bus.
"""
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from PIL import Image

try:
    import dbus
    import gi
except ImportError:
    dbus = None

COMMAND = Path(__file__).resolve().parents[2] / 'dotfiles/.local/bin/arctic-login-wallpaper'


@unittest.skipUnless(dbus and shutil.which('dbus-daemon'), 'private D-Bus and GLib required')
class BrokerIPC(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.bus_process = subprocess.Popen(['dbus-daemon', '--session', '--nofork', '--print-address=1'],
                                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
        address = self.bus_process.stdout.readline().strip()
        self.env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=address,
                        ARCTIC_WALLPAPER_TEST_BUS='session', XDG_CACHE_HOME=str(self.root / 'cache'),
                        XDG_STATE_HOME=str(self.root / 'state'))
        self.bus = dbus.bus.BusConnection(address)
        self.start()

    def start(self):
        self.service = subprocess.Popen([sys.executable, str(COMMAND), 'serve', '--session', str(self.root / 'public')],
                                        env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(100):
            if self.bus.name_has_owner('org.arcticlinux.Wallpaper'):
                break
            if self.service.poll() is not None:
                self.fail('The private broker exited before claiming its bus name.')
            time.sleep(.02)
        self.remote = dbus.Interface(self.bus.get_object('org.arcticlinux.Wallpaper',
                                     '/org/arcticlinux/Wallpaper'), 'org.arcticlinux.Wallpaper')

    def tearDown(self):
        self.service.terminate()
        self.service.wait(timeout=5)
        self.bus.close()
        self.bus_process.terminate()
        self.bus_process.wait(timeout=5)
        self.bus_process.stdout.close()
        self.temp.cleanup()

    def image(self, color):
        out = io.BytesIO()
        Image.new('RGB', (200, 100), color).save(out, format='PNG')
        return dbus.ByteArray(out.getvalue())

    def cli(self, *args):
        result = subprocess.run([sys.executable, str(COMMAND), *args], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_credentials_stale_requests_freeze_reset_and_restart(self):
        self.assertEqual(json.loads(self.remote.Status())['mode'], 'legacy')
        first = json.loads(self.remote.Set('desktop', self.image('red')))
        self.assertEqual(first['owner'], os.getuid())
        second = json.loads(self.remote.Follow(first['revision'], self.image('blue')))
        with self.assertRaises(dbus.DBusException):
            self.remote.Follow(first['revision'], self.image('green'))
        self.assertEqual(json.loads(self.remote.Status()), second)
        # A new process reads the persisted policy and public image after a restart.
        self.service.terminate()
        self.service.wait(timeout=5)
        self.start()
        self.assertEqual(json.loads(self.remote.Status()), second)
        frozen = json.loads(self.remote.Change('freeze'))
        self.assertEqual(frozen['mode'], 'separate')
        with self.assertRaises(dbus.DBusException):
            self.remote.Follow(frozen['revision'], self.image('green'))
        self.assertEqual(json.loads(self.remote.Change('undo'))['mode'], 'desktop')
        self.remote.Change('reset')
        self.assertEqual(list((self.root / 'public').rglob('wallpaper.png')), [])

    def test_cli_follows_latest_desktop_and_missing_file_keeps_last_copy(self):
        cache = self.root / 'cache/arctic'
        cache.mkdir(parents=True)
        image = self.root / 'private.png'
        image.write_bytes(bytes(self.image('red')))
        (cache / 'wallpaper-current').write_text(str(image))
        initial = self.cli('sync-desktop')
        self.assertEqual(self.cli('follow')['revision'], initial['revision'])
        image.write_bytes(bytes(self.image('blue')))
        changed = self.cli('follow')
        self.assertNotEqual(changed['revision'], initial['revision'])
        image.unlink()
        result = subprocess.run([sys.executable, str(COMMAND), 'follow'], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.cli('status')['revision'], changed['revision'])
        self.assertTrue(self.cli('status')['sync_error'])

    def test_invalid_mode_payload_and_unowned_uid_cannot_change_state(self):
        initial = json.loads(self.remote.Set('desktop', self.image('red')))
        for mode, data in [('anything', self.image('red')), ('desktop', dbus.ByteArray(b'bad'))]:
            with self.assertRaises(dbus.DBusException):
                self.remote.Set(mode, data)
        # Change the on-disk test fixture owner: caller UID is resolved from D-Bus,
        # never supplied in request data. Even the latest revision cannot bypass ownership.
        state_path = self.root / 'public/current/state.json'
        state = json.loads(state_path.read_text())
        state['owner'] = os.getuid() + 1
        state_path.write_text(json.dumps(state))
        with self.assertRaises(dbus.DBusException):
            self.remote.Follow(initial['revision'], self.image('blue'))
        self.assertEqual(json.loads(self.remote.Status())['revision'], initial['revision'])


if __name__ == '__main__':
    unittest.main()
