"""Tests for arctic-font (dotfiles/.local/bin): the code font in Arctic's terminal configs, GTK and
the shell, leaving a font someone chose themselves alone.

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-font'
DOTFILES = REPO / 'dotfiles' / '.config'


class FontTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.config = root / 'config'
        for app, name in (('kitty', 'kitty.conf'), ('foot', 'foot.ini'), ('alacritty', 'alacritty.toml')):
            (self.config / app).mkdir(parents=True)
            shutil.copy(DOTFILES / app / name, self.config / app / name)
        self.bin = root / 'bin'
        self.bin.mkdir()
        self.log = root / 'log'

        def stub(name, body):
            (self.bin / name).write_text('#!/bin/sh\n' + body + '\n')
            (self.bin / name).chmod(0o755)
        stub('fc-list', 'printf "JetBrains Mono,JetBrains Mono NL\\nFira Code\\nSymbols Nerd Font Mono\\nNoto Color Emoji\\nFira Code\\nHack Nerd Font Mono\\n"')
        for name in ('gsettings', 'pkill', 'arctic-hook'):
            stub(name, 'echo "{} $*" >> "{}"'.format(name, self.log))
        self.env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(self.config), PATH=str(self.bin) + ':/usr/bin:/bin')

    def tearDown(self):
        self.tmp.cleanup()

    def font(self, *args, code=0):
        out = subprocess.run([sys.executable, str(HELPER)] + list(args) + ['--json'], env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stdout + out.stderr)
        return json.loads(out.stdout)

    def read(self, app, name):
        return (self.config / app / name).read_text()

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def test_list(self):
        data = self.font('list')
        self.assertEqual([f['family'] for f in data['fonts']], ['Fira Code', 'Hack Nerd Font Mono', 'JetBrains Mono'])
        self.assertEqual((data['current'], data['size']), ('JetBrains Mono', 10.5))
        self.assertIs(data['symbols'], True)          # fc-list finds "Symbols Nerd Font Mono"

    def test_set_everywhere_arctic_wrote_it(self):
        data = self.font('set', 'Fira Code')
        self.assertEqual(sorted(data['changed']), ['alacritty', 'foot', 'gtk', 'kitty', 'shell'])
        self.assertEqual(data['skipped'], [])
        kitty = self.read('kitty', 'kitty.conf')
        self.assertIn('font_family      Fira Code\n', kitty)
        self.assertIn('bold_font        auto\n', kitty)
        self.assertIn('italic_font      auto\n', kitty)
        self.assertIn('font=Fira Code:size=10.5', self.read('foot', 'foot.ini'))
        self.assertIn('normal = { family = "Fira Code" }', self.read('alacritty', 'alacritty.toml'))
        self.assertEqual(json.loads((self.config / 'arctic' / 'shell.json').read_text())['monoFont'], 'Fira Code')
        self.assertIn('gsettings set org.gnome.desktop.interface monospace-font-name Fira Code 10', self.calls())
        self.assertTrue(any(c.startswith('pkill -USR1') for c in self.calls()))
        # Back again works too: the recorded value follows.
        self.font('set', 'JetBrains Mono')
        self.assertIn('font_family      JetBrains Mono\n', self.read('kitty', 'kitty.conf'))

    def test_a_font_of_your_own_is_left_alone(self):
        foot = self.config / 'foot' / 'foot.ini'
        foot.write_text(foot.read_text().replace('font=JetBrains Mono:size=10.5', 'font=Iosevka:size=12'))
        data = self.font('set', 'Fira Code')
        self.assertNotIn('foot', data['changed'])
        self.assertEqual(data['skipped'], [{'file': '~/config/foot/foot.ini', 'reason': 'has a font of your own'}])
        self.assertIn('font=Iosevka:size=12', foot.read_text())

    def test_size(self):
        data = self.font('size', '12.3')
        self.assertEqual(data['size'], 12.5)
        self.assertIn('font_size        12.5\n', self.read('kitty', 'kitty.conf'))
        self.assertIn('font=JetBrains Mono:size=12.5', self.read('foot', 'foot.ini'))
        self.assertIn('size = 12.5', self.read('alacritty', 'alacritty.toml'))
        self.font('size', 'reset')
        self.assertIn('font_size        10.5\n', self.read('kitty', 'kitty.conf'))

    def test_refusals(self):
        self.assertFalse(self.font('set', 'Comic Sans', code=1)['ok'])            # not installed
        self.assertFalse(self.font('set', 'x"; rm -rf ~', code=1)['ok'])
        self.assertFalse(self.font('size', '99', code=1)['ok'])
        self.assertFalse(self.font('size', 'big', code=1)['ok'])


if __name__ == '__main__':
    unittest.main()
