"""Tests for the notification commands in dotfiles/.local/bin: arctic-notify and arctic-dnd talk
to the shell when it owns notifications and to mako otherwise, and `arctic-session mako` only
starts mako outside the shell's session (or as the shell's fallback). The shell, makoctl and
mako are stand-ins that record how they were called.

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

BIN = Path(__file__).resolve().parents[2] / 'dotfiles' / '.local' / 'bin'


class NotifyCommandsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.log'
        self.fake('makoctl', 'case "$1" in mode) echo default ;; esac')

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, name, body=''):
        path = self.bin / name
        path.write_text('#!/bin/sh\necho "{} $*" >> "{}"\n{}\n'.format(name, self.log, body))
        path.chmod(0o755)

    def shell(self, dnd_answer):
        """A running shell whose `notifications dnd …` answers dnd_answer (on, off, unowned)."""
        self.fake('arctic-shell-ipc', 'case "$1 $2" in "notifications dnd") echo {} ;; esac'.format(dnd_answer))

    def run_bin(self, *args, env=None):
        full = dict(os.environ, PATH='{}:/usr/bin:/bin'.format(self.bin), HOME=str(self.root))
        full.update(env or {})
        result = subprocess.run(['bash', str(BIN / args[0])] + list(args[1:]), env=full, capture_output=True,
                                text=True, timeout=30)
        return result.returncode, result.stdout

    def calls(self, prefix=''):
        lines = self.log.read_text().splitlines() if self.log.exists() else []
        return [line for line in lines if line.startswith(prefix)]

    def test_dnd_through_the_shell(self):
        self.shell('on')
        self.run_bin('arctic-dnd', 'toggle')
        self.run_bin('arctic-dnd', 'for', '1h')
        self.run_bin('arctic-dnd', 'until-tomorrow')
        self.assertEqual(self.calls('arctic-shell-ipc'), [
            'arctic-shell-ipc notifications dnd toggle', 'arctic-shell-ipc notifications dnd 1h',
            'arctic-shell-ipc notifications dnd tomorrow'])
        self.assertEqual(self.calls('makoctl'), [])
        code, out = self.run_bin('arctic-dnd', 'status')
        self.assertEqual(json.loads(out)['class'], 'dnd')
        self.assertEqual(self.run_bin('arctic-dnd', 'for', '2h')[0], 2)

    def test_dnd_with_mako(self):
        # No shell (the IPC call fails), or a shell that doesn't own notifications: makoctl.
        self.fake('arctic-shell-ipc', 'exit 1')
        self.run_bin('arctic-dnd', 'toggle')
        self.shell('unowned')
        self.run_bin('arctic-dnd', 'on')
        self.run_bin('arctic-dnd', 'for', '1h')          # mako has no timer: simply on
        self.assertEqual(self.calls('makoctl mode -'), ['makoctl mode -t do-not-disturb', 'makoctl mode -a do-not-disturb',
                                                        'makoctl mode -a do-not-disturb'])
        code, out = self.run_bin('arctic-dnd', 'status')
        self.assertEqual(json.loads(out)['class'], 'on')

    def test_notify_through_the_shell(self):
        self.shell('off')
        for verb in ('dismiss', 'dismiss-all', 'center', 'invoke', 'history', 'count'):
            self.run_bin('arctic-notify', verb)
        self.assertEqual([c for c in self.calls('arctic-shell-ipc') if ' dnd ' not in c], [
            'arctic-shell-ipc notifications dismiss', 'arctic-shell-ipc notifications dismissAll',
            'arctic-shell-ipc notifications center', 'arctic-shell-ipc notifications invoke',
            'arctic-shell-ipc notifications history', 'arctic-shell-ipc notifications count'])
        self.assertEqual(self.calls('makoctl'), [])
        self.assertEqual(self.run_bin('arctic-notify', 'shout')[0], 2)

    def test_notify_with_mako(self):
        self.shell('unowned')
        for verb in ('dismiss', 'dismiss-all', 'center', 'invoke', 'history'):
            self.run_bin('arctic-notify', verb)
        self.assertEqual(self.calls('makoctl'), ['makoctl dismiss', 'makoctl dismiss --all', 'makoctl restore',
                                                 'makoctl invoke', 'makoctl history'])

    def session(self):
        """Stand-ins for a shell session; setsid records what would be started (no process
        is started, so nothing lingers for run_once's pgrep)."""
        self.fake('mako')
        self.fake('setsid')
        self.fake('quickshell')
        self.fake('arctic-shell', 'echo /usr/share/arctic/shell')

    def test_session_starts_mako_only_outside_the_shell(self):
        self.session()
        self.run_bin('arctic-session', 'mako')
        self.assertEqual(self.calls('setsid'), [])                 # the shell is the notification server
        self.run_bin('arctic-session', 'mako', '--fallback')
        self.assertEqual(self.calls('setsid'), ['setsid -f mako'])  # the shell couldn't take the name
        self.run_bin('arctic-session', 'mako', env={'ARCTIC_SHELL': 'waybar'})
        self.assertEqual(self.calls('setsid'), ['setsid -f mako'] * 2)   # the waybar session


if __name__ == '__main__':
    unittest.main()
