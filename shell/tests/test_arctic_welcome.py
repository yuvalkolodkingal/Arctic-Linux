"""Tests for arctic-welcome (dotfiles/.local/bin) on an installed system: the first-login
welcome shows once for a new account (the /etc/skel marker), and again only when asked.

Run: python3 -m unittest discover -s shell/tests
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-welcome'
MARKER = REPO / 'dotfiles' / '.local' / 'state' / 'arctic' / 'first-login'


class FirstLoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / 'home'
        self.state = self.home / '.local' / 'state' / 'arctic'
        self.state.mkdir(parents=True)
        self.bin = root / 'bin'
        self.bin.mkdir()
        self.log = root / 'calls'

        def stub(name, body):
            (self.bin / name).write_text('#!/bin/sh\n' + body + '\n')
            (self.bin / name).chmod(0o755)
        stub('arctic-is-live', 'exit 1')
        stub('arctic-shell-ipc', 'echo "ipc $*" >> "{}"'.format(self.log))
        stub('notify-send', 'echo "notify $*" >> "{}"'.format(self.log))
        stub('sleep', 'exit 0')
        self.env = dict(os.environ, HOME=str(self.home), PATH=str(self.bin) + ':/usr/bin:/bin',
                        XDG_RUNTIME_DIR=str(root))
        self.env.pop('XDG_STATE_HOME', None)
        self.env.pop('ARCTIC_SHELL', None)

    def tearDown(self):
        self.tmp.cleanup()

    def run_welcome(self, *args, env=None):
        subprocess.run(['bash', str(HELPER)] + list(args), env=env or self.env, check=True, timeout=30)
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_skel_has_the_marker(self):
        self.assertTrue(MARKER.is_file())

    def test_a_new_account_sees_it_once(self):
        (self.state / 'first-login').write_text(MARKER.read_text())
        self.assertEqual(self.run_welcome(), ['ipc welcome firstLogin'])
        self.assertFalse((self.state / 'first-login').exists())
        self.assertEqual(self.run_welcome(), ['ipc welcome firstLogin'], 'not a second time')

    def test_an_account_from_before_never_does(self):
        self.assertEqual(self.run_welcome(), [])

    def test_again_shows_it_now(self):
        self.assertEqual(self.run_welcome('--again'), ['ipc welcome firstLogin'])

    def test_without_the_shell_a_notification(self):
        (self.state / 'first-login').write_text('')
        env = dict(self.env, ARCTIC_SHELL='waybar')
        calls = self.run_welcome(env=env)
        self.assertTrue(calls[0].startswith('notify ') and 'Welcome to Arctic Linux' in calls[0])
        self.assertFalse([c for c in calls if c.startswith('ipc ')])


if __name__ == '__main__':
    unittest.main()
