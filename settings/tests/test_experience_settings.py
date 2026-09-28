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
              list) echo '{{"ok": true, "current": "JetBrains Mono", "size": 10.5, "fonts": [{{"family": "Fira Code"}}, {{"family": "JetBrains Mono"}}], "symbols": true}}' ;;
              set) [ "$2" = "Fira Code" ] && echo '{{"ok": true, "family": "Fira Code", "changed": ["kitty"], "skipped": [{{"file": "~/.config/foot/foot.ini", "reason": "has a font of your own"}}]}}' \
                   || {{ echo '{{"ok": false, "error": "There is no monospace font called that here."}}'; exit 1; }} ;;
            esac
            '''.format(self.log))
        data = self.helper('fonts')
        self.assertEqual((data['current'], data['fonts']), ('JetBrains Mono', ['Fira Code', 'JetBrains Mono']))
        self.assertIs(data['symbols'], True)
        data = self.helper('font-set', 'Fira Code')
        self.assertEqual(data['skipped'][0]['reason'], 'has a font of your own')
        self.assertIn('There is no', self.helper('font-set', 'Comic Sans', ok=False)['error'])
        self.assertIn('arctic-font set Fira Code --json', self.calls())


class TextSizeTest(Home):
    def test_the_terminals_follow(self):
        state = self.home / 'scale'
        stub(self.bin, 'gsettings', '''\
            if [ "$1" = set ]; then echo "$4" > "{0}"; else cat "{0}" 2>/dev/null || echo 1.0; fi
            '''.format(state))
        self.assertNotIn('terminalPt', self.helper('text-scale'))       # no arctic-font: GTK only
        stub(self.bin, 'arctic-font', '''\
            echo "arctic-font $*" >> "{0}"
            echo '{{"ok": true, "family": "JetBrains Mono", "size": 13}}'
            '''.format(self.log))
        data = self.helper('text-scale', '1.25')
        self.assertEqual((data['value'], data['terminalPt']), (1.25, 13))
        self.helper('text-scale', '1')
        self.helper('text-scale', '1.1')
        self.assertEqual([c for c in self.calls() if ' size ' in c],
                         ['arctic-font size 13 --json', 'arctic-font size reset --json', 'arctic-font size 11.5 --json'])
        self.helper('text-scale', '3', ok=False)


class WeatherTest(Home):
    def test_options(self):
        data = self.helper('shell-options')
        self.assertEqual((data['weather'], data['weatherUnits'], data['barWeather']), (False, 'auto', False))
        self.helper('shell-option-set', 'weather', 'true')
        self.helper('shell-option-set', 'weatherUnits', 'imperial')
        stored = json.loads((self.home / '.config/arctic/shell.json').read_text())
        self.assertEqual(stored, {'weather': True, 'weatherUnits': 'imperial'})      # a real true
        for key, value in (('weather', 'yes'), ('weatherUnits', 'kelvin'), ('barWeather', '1')):
            self.helper('shell-option-set', key, value, ok=False)

    def test_place(self):
        zoneinfo = self.tmp / 'zoneinfo'
        zoneinfo.mkdir()
        (zoneinfo / 'zone1970.tab').write_text('IL\t+314650+0351326\tAsia/Jerusalem\n')
        self.env.update(ARCTIC_ZONEINFO=str(zoneinfo), ARCTIC_TIMEZONE='Asia/Jerusalem',
                        ARCTIC_GEOCODE_API='http://127.0.0.1:9/v1/search', no_proxy='*')
        self.assertEqual(self.helper('weather-place')['place'], {'name': 'Jerusalem', 'detail': 'Asia/Jerusalem', 'source': 'zone'})
        data = self.helper('weather-place', 'set', 'Haifa', '32.81841', '34.9885', 'Haifa District, Israel')
        self.assertEqual(data['place'], {'name': 'Haifa', 'detail': 'Haifa District, Israel', 'source': 'chosen'})
        saved = json.loads((self.home / '.config/arctic/location.json').read_text())
        self.assertEqual((saved['lat'], saved['lon']), (32.8184, 34.9885))
        self.assertEqual(self.helper('weather-place', 'zone')['place']['source'], 'zone')
        self.assertFalse((self.home / '.config/arctic/location.json').exists())
        for bad in (('set', 'X', '99', '0'), ('set', '', '1', '1'), ('set', 'X', 'north', '1'), ('move',)):
            self.helper('weather-place', *bad, ok=False)
        self.assertIn('reach', self.helper('weather-place', 'search', 'Haifa', ok=False)['error'])


class ThemeInstallTest(Home):
    def test_install_and_remove(self):
        state = self.home / 'themes.json'
        stub(self.bin, 'arctic-theme', '''\
            echo "arctic-theme $*" >> "{1}"
            case "$1" in
              list) cat "{0}" 2>/dev/null || echo '[{{"name": "winter", "label": "Winter", "mode": "light", "gallery": false}}]' ;;
              current) echo '{{"name": "polar-night"}}' ;;
              install)
                [ "$2" = https://github.com/o/omarchy-nord-theme ] || {{ echo "arctic-theme: use a GitHub, GitLab or Codeberg link" >&2; exit 1; }}
                echo '[{{"name": "nord", "label": "Nord", "mode": "dark", "gallery": true, "installed_from": "https://github.com/o/omarchy-nord-theme", "swatches": {{"ground": "#2e3440"}}}}]' > "{0}"
                echo '{{"ok": true, "name": "nord", "label": "Nord", "dropped": ["kitty.conf", "neovim.lua"], "backgrounds": 1}}' ;;
              remove) rm -f "{0}"; echo '{{"ok": true, "name": "nord"}}' ;;
            esac
            '''.format(state, self.log))
        data = self.helper('theme-install', 'https://github.com/o/omarchy-nord-theme')
        nord = [t for t in data['themes'] if t['id'] == 'nord'][0]
        self.assertEqual((nord['installedFrom'], nord['gallery']), ('https://github.com/o/omarchy-nord-theme', True))
        self.assertEqual(data['installed']['dropped'], ['kitty.conf', 'neovim.lua'])
        self.assertIn('arctic-theme install https://github.com/o/omarchy-nord-theme --json', self.calls())
        self.assertIn('Use a GitHub', self.helper('theme-install', 'https://example.com/x', ok=False)['error'])
        for bad in ('http://github.com/o/r', 'github.com/o/r', ''):
            self.helper('theme-install', bad, ok=False)
        data = self.helper('theme-remove', 'nord')
        self.assertNotIn('nord', [t['id'] for t in data['themes']])
        self.helper('theme-remove', '../x', ok=False)


class WallpaperRotateTest(Home):
    def test_rotate(self):
        self.assertEqual(self.helper('wallpaper-rotate')['available'], False)
        state = self.home / 'rotate.json'
        stub(self.bin, 'arctic-wallpaper', '''\
            echo "arctic-wallpaper $*" >> "{1}"
            [ "$1" = rotate ] || exit 2
            case "$2" in
              "") cat "{0}" 2>/dev/null || echo '{{"every": "off"}}' ;;
              off) rm -f "{0}" ;;
              *) [ "$3" = /nowhere ] && {{ echo "arctic-wallpaper: there is no folder /nowhere" >&2; exit 2; }}
                 s=false; [ "$4" = --shuffle ] && s=true
                 printf '{{"every": "%s", "folder": "%s", "shuffle": %s}}\\n' "$2" "$3" "$s" > "{0}" ;;
            esac
            '''.format(state, self.log))
        self.assertEqual(self.helper('wallpaper-rotate')['every'], 'off')
        data = self.helper('wallpaper-rotate', '1h', '/pics', 'shuffle')
        self.assertEqual((data['every'], data['folder'], data['shuffle']), ('1h', '/pics', True))
        self.assertIn('arctic-wallpaper rotate 1h /pics --shuffle', self.calls())
        self.assertEqual(self.helper('wallpaper-rotate', 'off')['every'], 'off')
        self.assertIn('There is no folder', self.helper('wallpaper-rotate', '30m', '/nowhere', ok=False)['error'])
        for bad in (('5m', '/pics'), ('30m',), ('off', '/pics'), ('1h', '/pics', 'twice')):
            self.helper('wallpaper-rotate', *bad, ok=False)


class AccessibilityTest(Home):
    def test_keyboard_pointer(self):
        self.assertFalse(self.helper('accessibility')['kbptr'])
        stub(self.bin, 'wl-kbptr', 'exit 0\n')
        self.assertTrue(self.helper('accessibility')['kbptr'])

    def test_high_contrast(self):
        self.assertIsNone(self.helper('accessibility')['contrast'])       # no arctic-theme: no row
        self.helper('contrast-set', 'on', ok=False)
        state = self.home / 'contrast'
        stub(self.bin, 'arctic-theme', '''\
            [ "$1" = contrast ] || exit 2
            case "$2" in
              on) echo high > "{0}" ;;
              off) echo normal > "{0}" ;;
              loud) echo "arctic-theme: no" >&2; exit 2 ;;
            esac
            printf '{{"ok": true, "contrast": "%s"}}\\n' "$(cat "{0}" 2>/dev/null || echo normal)"
            '''.format(state))
        self.assertIs(self.helper('accessibility')['contrast'], False)
        self.assertIs(self.helper('contrast-set', 'on')['contrast'], True)
        self.assertIs(self.helper('accessibility')['contrast'], True)
        self.assertIs(self.helper('contrast-set', 'off')['contrast'], False)
        for bad in ((), ('loud',), ('on', 'off')):
            self.helper('contrast-set', *bad, ok=False)


if __name__ == '__main__':
    unittest.main()
