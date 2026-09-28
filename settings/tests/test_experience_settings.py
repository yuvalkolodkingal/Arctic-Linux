"""Tests for the Settings backend's 0.3 "experience" commands (settings/scripts/arctic_settings.py):
the shell's options, the light/dark schedule, fonts and accessibility.

    python3 -m unittest discover -s settings/tests -v
"""
import json
import unittest

from test_arctic_settings import Home


class ShellOptionsTest(Home):
    def shell_json(self):
        return json.loads((self.home / '.config/arctic/shell.json').read_text())

    def test_defaults_without_a_file(self):
        data = self.helper('shell-options')
        self.assertEqual(data['webSearch'], 'duckduckgo')
        self.assertIn('startpage', [e['id'] for e in data['engines']])

    def test_set_keeps_other_keys(self):
        (self.home / '.config/arctic/shell.json').write_text('{"frame": false}\n')
        data = self.helper('shell-option-set', 'webSearch', 'startpage')
        self.assertEqual(data['webSearch'], 'startpage')
        self.assertEqual(self.shell_json(), {'frame': False, 'webSearch': 'startpage'})
        self.helper('shell-option-set', 'webSearch', 'https://search.example.org/?q=%s')
        self.assertEqual(self.shell_json()['webSearch'], 'https://search.example.org/?q=%s')

    def test_refuses_what_the_shell_cant_use(self):
        for value in ('altavista', 'http://example.org/?q=%s', 'https://example.org/', 'javascript:alert(%s)',
                      'https://e.org/?q=%s" onload'):
            self.helper('shell-option-set', 'webSearch', value, ok=False)
        self.helper('shell-option-set', 'frame', 'true', ok=False)
        self.assertFalse((self.home / '.config/arctic/shell.json').exists())

    def test_a_broken_file_is_replaced_not_fatal(self):
        (self.home / '.config/arctic/shell.json').write_text('{not json')
        self.assertEqual(self.helper('shell-options')['webSearch'], 'duckduckgo')
        self.helper('shell-option-set', 'webSearch', 'brave')
        self.assertEqual(self.shell_json(), {'webSearch': 'brave'})


if __name__ == '__main__':
    unittest.main()
