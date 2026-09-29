"""The Web apps page's backend commands (arctic_settings.py webapp-*), with a stand-in
arctic-webapp on PATH that records its argv and answers one line of --json.

    python3 -m unittest discover -s settings/tests -p 'test_webapps.py' -v
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'settings' / 'scripts' / 'arctic_settings.py'
APP = 'org.arcticlinux.WebApp.YouTubeMusic_4c1a9e'


class WebAppCommands(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.log = self.tmp / 'argv.log'
        self.answer = self.tmp / 'answer.json'
        self.answer.write_text('{"ok":true,"apps":[],"kept":[]}\n')
        fake = self.bin / 'arctic-webapp'
        fake.write_text(textwrap.dedent('''\
            #!/bin/sh
            printf '%s\\n' "$*" >> "{log}"
            cat "{answer}"
            ''').format(log=self.log, answer=self.answer))
        fake.chmod(0o755)
        self.env = dict(HOME=str(self.tmp), PATH=str(self.bin) + ':/usr/bin:/bin', XDG_RUNTIME_DIR=str(self.tmp))

    def tearDown(self):
        subprocess.run(['rm', '-rf', str(self.tmp)], check=False)

    def run_helper(self, *args, env=None):
        proc = subprocess.run([sys.executable, str(HELPER)] + list(args), capture_output=True, text=True,
                              env=env or self.env, timeout=30)
        self.assertEqual(proc.stdout.count('\n'), 1, proc.stdout)
        return json.loads(proc.stdout)

    def argv(self):
        return self.log.read_text().splitlines()

    def test_list_passes_through(self):
        self.answer.write_text('{"ok":true,"apps":[{"id":"%s","name":"YouTube Music"}],"kept":[]}\n' % APP)
        r = self.run_helper('webapps')
        self.assertTrue(r['ok'])
        self.assertEqual(r['apps'][0]['name'], 'YouTube Music')
        self.assertEqual(self.argv(), ['list --kept --sizes --json'])

    def test_errors_pass_through_as_sentences(self):
        self.answer.write_text('{"ok":false,"code":"state","error":"YouTube Music is still open. Close it and try again."}\n')
        r = self.run_helper('webapp-remove', APP, 'keep')
        self.assertFalse(r['ok'])
        self.assertEqual(r['error'], 'YouTube Music is still open. Close it and try again.')
        self.assertEqual(self.argv(), ['remove %s --keep-data --json' % APP])

    def test_set_uses_the_allowlist(self):
        self.answer.write_text('{"ok":true,"app":{},"applied":"live"}\n')
        r = self.run_helper('webapp-set', APP, 'links', 'app')
        self.assertTrue(r['ok'])
        self.run_helper('webapp-set', APP, 'name', '--evil value')
        self.assertEqual(self.argv(), ['set %s --links=app --json' % APP, 'set %s --name=--evil value --json' % APP])
        r = self.run_helper('webapp-set', APP, 'exec', 'rm -rf ~')
        self.assertFalse(r['ok'])
        self.assertIn('can’t change', r['error'])
        self.assertEqual(len(self.argv()), 2)

    def test_ids_are_checked(self):
        for bad in ('../../x', 'org.arcticlinux.WebApp.X_1; rm', '--all'):
            r = self.run_helper('webapp-clear', bad)
            self.assertFalse(r['ok'])
            self.assertEqual(r['error'], 'That isn’t a web app.')
        self.assertFalse(self.log.exists())

    def test_other_commands(self):
        self.answer.write_text('{"ok":true}\n')
        for args, want in ((('webapp-forget', APP), 'forget %s --json'), (('webapp-clear', APP), 'clear-data %s --json'),
                           (('webapp-refresh', APP), 'update %s --json'), (('webapp-open', APP), 'launch %s --json'),
                           (('webapp-reset-permissions', APP), 'set %s --reset-permissions --json'),
                           (('webapp-remove', APP, 'delete'), 'remove %s --json')):
            self.assertTrue(self.run_helper(*args)['ok'])
            self.assertEqual(self.argv()[-1], want % APP)

    def test_missing_binary(self):
        env = dict(self.env, PATH=str(self.tmp / 'nowhere'))
        r = self.run_helper('webapps', env=env)
        self.assertEqual(r, {'ok': False, 'error': 'Web apps aren’t installed (package arctic-webapps).'})

    def test_unreadable_answer(self):
        self.answer.write_text('progress…\n')
        r = self.run_helper('webapps')
        self.assertFalse(r['ok'])

    def test_caps_reports_the_manager(self):
        r = self.run_helper('caps')
        self.assertTrue(r['arcticWebapp'])
        r = self.run_helper('caps', env=dict(self.env, PATH=str(self.tmp / 'nowhere')))
        self.assertFalse(r['arcticWebapp'])


class WebAppsPage(unittest.TestCase):
    """An app whose browser was uninstalled still opens (in the Arctic engine) and can switch
    engine, so the page keeps its Open button and settings; only a launcher entry or record
    problem leaves Remove alone."""

    def setUp(self):
        self.qml = (REPO / 'settings' / 'pages' / 'WebAppsPage.qml').read_text()
        m = re.search(r'function usable\(a\) \{(.*?)\n    \}', self.qml, re.S)
        self.assertIsNotNone(m, 'WebAppsPage.qml has usable(a)')
        self.usable = m.group(1)

    def test_runtime_missing_is_usable(self):
        self.assertEqual(sorted(re.findall(r'a\.problem === "([^"]*)"', self.usable)), ['', 'runtime-missing'])

    def test_buttons_and_settings_follow_usable(self):
        # Open, Settings and (for the others) Remove on each row, and the settings group below;
        # nothing else decides by problem === "" any more.
        self.assertEqual(self.qml.count('page.usable(appRow.modelData)'), 3)
        self.assertIn('visible: !page.usable(appRow.modelData)', self.qml)
        self.assertIn('visible: page.usable(page.app)', self.qml)
        self.assertNotIn('problem === ""', self.qml.replace(self.usable, ''))


if __name__ == '__main__':
    unittest.main()
