"""Tests for arctic-hook (dotfiles/.local/bin): the theme-hooks contract for the other desktop
events (order, yours replacing Arctic's, skipped names, the time limit, what a hook is told).

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-hook'


class HookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.system = root / 'share'
        self.mine = root / 'config' / 'arctic'
        self.log = root / 'log'
        self.env = dict(os.environ, ARCTIC_DATA_DIR=str(self.system), XDG_CONFIG_HOME=str(root / 'config'),
                        XDG_RUNTIME_DIR=str(root / 'run'), ARCTIC_HOOK_TIMEOUT='1')

    def tearDown(self):
        self.tmp.cleanup()

    def hook(self, where, event, name, body, executable=True):
        folder = (self.system if where == 'system' else self.mine) / (event + '-hooks.d')
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755 if executable else 0o644)
        return path

    def run_hook(self, *args, code=0):
        out = subprocess.run([sys.executable, str(HELPER)] + list(args), env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stderr)
        return out

    def ran(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_order_value_and_environment(self):
        self.hook('system', 'wallpaper', '20-b', 'echo "b $1 $ARCTIC_HOOK_EVENT $ARCTIC_HOOK_VALUE" >> {}'.format(self.log))
        self.hook('mine', 'wallpaper', '10-a', 'echo "a $1" >> {}'.format(self.log))
        self.run_hook('wallpaper', '/home/me/Pictures/sea.jpg')
        self.assertEqual(self.ran(), ['a /home/me/Pictures/sea.jpg', 'b /home/me/Pictures/sea.jpg wallpaper /home/me/Pictures/sea.jpg'])

    def test_yours_replaces_or_turns_off_arctics(self):
        self.hook('system', 'lock', '10-pause', 'echo system >> {}'.format(self.log))
        self.hook('system', 'lock', '20-other', 'echo other >> {}'.format(self.log))
        self.hook('mine', 'lock', '10-pause', 'echo mine >> {}'.format(self.log))
        self.hook('mine', 'lock', '20-other', 'echo never >> {}'.format(self.log), executable=False)
        self.run_hook('lock')
        self.assertEqual(self.ran(), ['mine'])

    def test_skipped_names(self):
        for name in ('.hidden', 'x~', 'x.rpmnew', 'x.rpmsave', 'x.disabled', '10-pause-media.sample'):
            self.hook('mine', 'login', name, 'echo {} >> {}'.format(name, self.log))
        self.hook('mine', 'login', 'ok', 'echo ok >> {}'.format(self.log))
        self.run_hook('login')
        self.assertEqual(self.ran(), ['ok'])

    def test_a_slow_or_failing_hook_never_fails_the_event(self):
        self.hook('mine', 'unlock', '10-slow', 'sleep 30; echo late >> {}'.format(self.log))
        self.hook('mine', 'unlock', '20-fails', 'echo complaint; exit 3')
        self.hook('mine', 'unlock', '30-after', 'echo after >> {}'.format(self.log))
        started = time.monotonic()
        out = self.run_hook('unlock')
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(self.ran(), ['after'])
        self.assertIn('stopped', out.stderr)
        self.assertIn('complaint', out.stderr)
        self.assertIn('exit 3', out.stderr)

    def test_events(self):
        self.run_hook('theme', code=2)             # arctic-theme runs those
        self.run_hook('reboot', code=2)
        self.run_hook('battery-low', '9')          # no hooks: nothing to do
        self.hook('mine', 'post-update', 'log', 'true')
        listing = json.loads(self.run_hook('--list', '--json').stdout)
        events = {e['event']: e for e in listing['events']}
        self.assertEqual(sorted(events), sorted(['wallpaper', 'font', 'lock', 'unlock', 'battery-low', 'post-update', 'login', 'theme']))
        self.assertEqual(len(events['post-update']['hooks']), 1)
        self.assertEqual(events['theme']['folders'][1], str(self.mine / 'theme-hooks.d'))


if __name__ == '__main__':
    unittest.main()
