"""Tests for arctic-osd's lock-keys and notice (dotfiles/.local/bin): Caps Lock and Num Lock say
only what changed, from the keyboard lights, and a notice falls back to a notification.

Run: python3 -m unittest discover -s shell/tests
"""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-osd'


class LockKeysTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.leds = root / 'leds'
        for name in ('input3::capslock', 'input3::numlock', 'input9::capslock'):
            (self.leds / name).mkdir(parents=True)
            (self.leds / name / 'brightness').write_text('0\n')
        self.bin = root / 'bin'
        self.bin.mkdir()
        self.log = root / 'calls'
        (self.bin / 'arctic-shell-ipc').write_text('#!/bin/sh\necho "ipc $*" >> "{}"\n'.format(self.log))
        (self.bin / 'arctic-shell-ipc').chmod(0o755)
        self.env = dict(os.environ, ARCTIC_LEDS_DIR=str(self.leds), XDG_RUNTIME_DIR=str(root / 'run'),
                        PATH=str(self.bin) + ':/usr/bin:/bin')

    def tearDown(self):
        self.tmp.cleanup()

    def light(self, name, on):
        (self.leds / name / 'brightness').write_text('1\n' if on else '0\n')

    def osd(self, *args):
        subprocess.run(['bash', str(HELPER)] + list(args), env=self.env, check=True, timeout=30)
        calls = self.log.read_text().splitlines() if self.log.exists() else []
        self.log.write_text('')
        return calls

    def test_says_what_changed(self):
        self.assertEqual(self.osd('lock-keys', '--seed'), [])
        self.light('input9::capslock', True)       # any keyboard's light counts
        self.assertEqual(self.osd('lock-keys'), ['ipc osd notice keyboard Caps Lock on '])
        self.light('input3::numlock', True)
        self.assertEqual(self.osd('lock-keys'), ['ipc osd notice hash Num Lock on '])
        self.light('input9::capslock', False)
        self.assertEqual(self.osd('lock-keys'), ['ipc osd notice keyboard Caps Lock off '])
        # A key that changed no light (Caps remapped, or switching layouts): nothing.
        self.assertEqual(self.osd('lock-keys'), [])

    def test_waits_for_the_light(self):
        # Num Lock runs it on the key press; the light goes off only when the key is let go.
        self.light('input3::numlock', True)
        self.assertEqual(self.osd('lock-keys', '--seed'), [])
        run = subprocess.Popen(['bash', str(HELPER), 'lock-keys'], env=self.env)
        time.sleep(0.4)
        self.light('input3::numlock', False)
        self.assertEqual(run.wait(timeout=30), 0)
        self.assertEqual(self.log.read_text().splitlines(), ['ipc osd notice hash Num Lock off '])

    def test_no_state_yet_or_no_lights(self):
        self.light('input3::capslock', True)
        self.assertEqual(self.osd('lock-keys'), [], 'the first run only records')
        for name in os.listdir(self.leds):
            (self.leds / name / 'brightness').unlink()
        self.assertEqual(self.osd('lock-keys'), [])

    def test_notice(self):
        self.assertEqual(self.osd('notice', 'bell-off', 'Do not disturb on', 'Until 09:00'),
                         ['ipc osd notice bell-off Do not disturb on Until 09:00'])


if __name__ == '__main__':
    unittest.main()
