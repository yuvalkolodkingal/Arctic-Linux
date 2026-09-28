"""Tests for arctic-menu (dotfiles/.local/bin): the command menu's fallback without the shell.

Run: python3 -m unittest discover -s shell/tests
"""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-menu'
SHIPPED = REPO / 'shell' / 'menu' / 'arctic-menu.json'


def load():
    # No __pycache__ next to the helper: dotfiles/.local/bin is installed as it is.
    sys.dont_write_bytecode = True
    loader = importlib.machinery.SourceFileLoader('arctic_menu', str(HELPER))
    spec = importlib.util.spec_from_loader('arctic_menu', loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class ArcticMenuTests(unittest.TestCase):
    def setUp(self):
        self.menu = load()
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_reads_the_shipped_menu(self):
        entries = self.menu.load([str(SHIPPED)])
        ids = [e['id'] for e in entries]
        self.assertEqual([i for i in ids if '.' not in i],
                         ['apps', 'learn', 'capture', 'toggle', 'style', 'setup', 'install', 'remove', 'update', 'system'])

    def test_fallback_rows_need_their_command_and_no_shell(self):
        entries = self.menu.load([str(SHIPPED)])
        have = {'arctic-screenshot', 'arctic-power', 'sh', 'xdg-open', 'arctic-shell-ipc'}
        rows = self.menu.rows(entries, 'capture', False, which=lambda c: c in have)
        self.assertEqual([e['id'] for _, e in rows], ['capture.area', 'capture.window', 'capture.screen', 'capture.folder'])
        self.assertEqual(rows[0][0], 'Screenshot of an area')
        everything = self.menu.rows(entries, '', True, which=lambda c: c in have)
        labels = [label for label, _ in everything]
        self.assertIn('System › Restart', labels)
        self.assertNotIn('System › Lock screen', labels)        # live session
        self.assertFalse(any(e['run'][0] == 'arctic-shell-ipc' for _, e in everything))

    def test_your_file_changes_hides_and_adds_rows(self):
        mine = self.root / 'menu.json'
        mine.write_text(json.dumps({'capture.area': {'label': 'Snip'}, 'system': {'hidden': True},
                                    'mine': {'label': 'Mine'}, 'mine.hi': {'label': 'Hi', 'run': 'echo hi'},
                                    'mine.no': {'label': 'No', 'run': ['true'], 'test': 'false'}}))
        entries = self.menu.load([str(SHIPPED), str(mine), str(self.root / 'missing.json')])
        by_id = {e['id']: e for e in entries}
        self.assertEqual(by_id['capture.area']['label'], 'Snip')
        self.assertEqual(by_id['capture.area']['run'], ['arctic-screenshot', 'area'])
        self.assertNotIn('system.restart', by_id)
        rows = self.menu.rows(entries, 'mine', False, which=lambda c: True)
        self.assertEqual([label for label, _ in rows], ['Hi'])

    def test_list_prints_rows_without_the_shell(self):
        home = self.root / 'home'
        (home / '.config' / 'arctic').mkdir(parents=True)
        bin_ = self.root / 'bin'
        bin_.mkdir()
        # arctic-shell --path points at this checkout's shell; little else is installed.
        (bin_ / 'arctic-shell').write_text('#!/bin/sh\necho "%s"\n' % (REPO / 'shell'))
        (bin_ / 'arctic-power').write_text('#!/bin/sh\n')
        for name in ('arctic-shell', 'arctic-power'):
            (bin_ / name).chmod(0o755)
        env = dict(os.environ, HOME=str(home), XDG_CONFIG_HOME=str(home / '.config'), PATH=str(bin_))
        out = subprocess.run([sys.executable, str(HELPER), '--list', 'system'], env=env, capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertEqual(out.stdout.splitlines(), ['Lock screen\tsystem.lock', 'Log out\tsystem.logout', 'Suspend\tsystem.suspend',
                                                   'Restart\tsystem.restart', 'Shut down\tsystem.poweroff'])
        bad = subprocess.run([sys.executable, str(HELPER), '--list', 'no such'], env=env, capture_output=True, text=True)
        self.assertEqual(bad.returncode, 2)


if __name__ == '__main__':
    unittest.main()
