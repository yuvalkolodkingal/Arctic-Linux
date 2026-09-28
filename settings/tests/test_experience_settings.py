"""Tests for the Settings backend's 0.3 "experience" commands (settings/scripts/arctic_settings.py):
the shell's options, the light/dark schedule, fonts and accessibility.

    python3 -m unittest discover -s settings/tests -v
"""
import json
import unittest

from test_arctic_settings import Home, stub


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


class DaylightTest(Home):
    def test_missing(self):
        self.assertFalse(self.helper('daylight')['available'])
        self.helper('daylight-set', 'sun', ok=False)

    def test_passes_through(self):
        stub(self.bin, 'arctic-daylight', '''\
            echo "arctic-daylight $*" >> "{}"
            case "$1" in
              --json|sun|off|hours) echo '{{"ok": true, "mode": "sun", "light": "07:00", "dark": "19:00", "today": {{"light": "06:33", "dark": "18:30"}}}}' ;;
              *) echo '{{"ok": false, "error": "Give two different times of day, like 07:00 19:00."}}'; exit 1 ;;
            esac
            '''.format(self.log))
        data = self.helper('daylight')
        self.assertEqual((data['available'], data['mode'], data['today']['light']), (True, 'sun', '06:33'))
        self.helper('daylight-set', 'sun')
        self.helper('daylight-set', 'hours', '07:00', '19:00')
        self.assertEqual(self.calls(), ['arctic-daylight --json', 'arctic-daylight sun', 'arctic-daylight hours 07:00 19:00'])
        for bad in (['sometimes'], ['hours', '07:00'], ['sun', 'now'], []):
            self.helper('daylight-set', *bad, ok=False)


class FontsTest(Home):
    def test_missing(self):
        self.assertFalse(self.helper('fonts')['available'])
        self.helper('font-set', 'Fira Code', ok=False)

    def test_list_and_set(self):
        stub(self.bin, 'arctic-font', '''\
            echo "arctic-font $*" >> "{}"
            case "$1" in
              list) echo '{{"ok": true, "current": "JetBrains Mono", "size": 10.5, "fonts": [{{"family": "Fira Code"}}, {{"family": "JetBrains Mono"}}]}}' ;;
              set) [ "$2" = "Fira Code" ] && echo '{{"ok": true, "family": "Fira Code", "changed": ["kitty"], "skipped": [{{"file": "~/.config/foot/foot.ini", "reason": "has a font of your own"}}]}}' \
                   || {{ echo '{{"ok": false, "error": "There is no monospace font called that here."}}'; exit 1; }} ;;
            esac
            '''.format(self.log))
        data = self.helper('fonts')
        self.assertEqual((data['current'], data['fonts']), ('JetBrains Mono', ['Fira Code', 'JetBrains Mono']))
        data = self.helper('font-set', 'Fira Code')
        self.assertEqual(data['skipped'][0]['reason'], 'has a font of your own')
        self.assertIn('There is no', self.helper('font-set', 'Comic Sans', ok=False)['error'])
        self.assertIn('arctic-font set Fira Code --json', self.calls())


class AccessibilityTest(Home):
    def test_keyboard_pointer(self):
        self.assertFalse(self.helper('accessibility')['kbptr'])
        stub(self.bin, 'wl-kbptr', 'exit 0\n')
        self.assertTrue(self.helper('accessibility')['kbptr'])


if __name__ == '__main__':
    unittest.main()
