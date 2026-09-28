"""Consistency checks for the Settings app's QML (no display needed).

    python3 -m unittest discover -s settings/tests -v

- The components ported from the installer stay identical to installer-ui/components, so a
  fix or restyle there reaches Settings (the few adapted ones say why in their header).
- Every page in SearchIndex.js exists, and every search entry points at a row that exists.
- The desktop entry, launcher and keybind agree.
"""
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / 'settings'
INSTALLER = REPO / 'installer-ui' / 'components'

VERBATIM = ['AppTile', 'ArBanner', 'ArButton', 'ArCard', 'ArCheck', 'ArCheckIndicator', 'ArDialog', 'ArInput',
            'ArKbd', 'ArList', 'ArListRow', 'ArMeter', 'ArProgress', 'ArRadio', 'ArTag', 'ArText', 'ArToggle',
            'CornerMask', 'FocusRing', 'Mark', 'ShadowRect']
ADAPTED = {'Icon': 'SettingsIcons.js', 'ArSelect': 're-bound'}   # file: a phrase its header must contain


class ComponentsTest(unittest.TestCase):
    def test_ported_components_match_the_installer(self):
        for name in VERBATIM:
            with self.subTest(name):
                self.assertEqual((APP / 'components' / (name + '.qml')).read_text(),
                                 (INSTALLER / (name + '.qml')).read_text(),
                                 '{}.qml drifted from installer-ui/components; copy it again'.format(name))

    def test_adapted_components_say_so(self):
        for name, phrase in ADAPTED.items():
            self.assertIn(phrase, (APP / 'components' / (name + '.qml')).read_text())

    def test_design_icons_are_the_installers(self):
        self.assertEqual((APP / 'assets/Icons.js').read_text(), (REPO / 'installer-ui/assets/Icons.js').read_text())

    def test_qmldir_lists_every_component(self):
        listed = {line.split()[-1] for line in (APP / 'components/qmldir').read_text().splitlines() if line.strip()}
        present = {p.name for p in (APP / 'components').glob('*.qml')}
        self.assertEqual(listed, present)


class SearchIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = (APP / 'SearchIndex.js').read_text()
        self.pages = {p.name: p.read_text() for p in (APP / 'pages').glob('*.qml')}

    def test_pages_exist(self):
        files = re.findall(r'file: "([A-Za-z]+\.qml)"', self.index)
        self.assertEqual(len(files), 13)
        for name in files:
            self.assertIn(name, self.pages)

    def test_entries_point_at_rows(self):
        keys = set()
        for text in self.pages.values():
            keys |= set(re.findall(r'searchKey: "([a-z.]+)"', text))
            # generated keys ("apps." + role id)
            if 'searchKey: "apps." + modelData.id' in text:
                keys |= {'apps.' + r for r in ('browser', 'terminal', 'files', 'editor', 'video', 'music', 'images', 'pdf')}
            keys |= set(re.findall(r'\? "([a-z]+\.[a-z]+)" : ""', text))
        for page, key in re.findall(r'\["([a-z]+)", "([a-z.]+)",', self.index):
            with self.subTest(key):
                self.assertTrue(key.startswith(page + '.'), key)
                self.assertIn(key, keys)


class IntegrationFilesTest(unittest.TestCase):
    def test_desktop_entry(self):
        entry = (REPO / 'packaging/settings/org.arcticlinux.Settings.desktop').read_text()
        self.assertIn('Exec=arctic-settings', entry)
        self.assertIn('Icon=org.arcticlinux.Settings', entry)
        self.assertTrue((REPO / 'packaging/settings/org.arcticlinux.Settings.svg').is_file())

    def test_keybind_is_documented(self):
        binds = (REPO / 'dotfiles/.config/mango/arctic/binds.conf').read_text()
        self.assertIn('bind=SUPER,s,spawn,arctic-settings', binds)
        self.assertEqual(len(re.findall(r'^bind[a-z]*=SUPER,s,', binds, re.M)), 1)
        self.assertIn('Super + S', (REPO / 'dotfiles/.local/share/arctic/keys.txt').read_text())

    def test_browser_is_super_b(self):
        apps = (REPO / 'dotfiles/.config/mango/arctic/apps.conf').read_text()
        self.assertIn('bind=SUPER,b,spawn,arctic-open browser\n', apps)
        self.assertNotRegex(apps, r'(?m)^bind[a-z]*=SUPER,w,')
        self.assertIn('    Super + B                Browser\n', (REPO / 'dotfiles/.local/share/arctic/keys.txt').read_text())
        self.assertIn("keys='Super + B'", (APP / 'scripts/arctic_settings.py').read_text())

    def test_screenshot_keys(self):
        binds = (REPO / 'dotfiles/.config/mango/arctic/binds.conf').read_text()
        for line in ('bind=NONE,Print,spawn,arctic-screenshot area', 'bind=SUPER+SHIFT,s,spawn,arctic-screenshot area',
                     'bind=SHIFT,Print,spawn,arctic-screenshot screen', 'bind=SUPER,Print,spawn,arctic-screenshot window'):
            self.assertIn(line + '\n', binds)
        self.assertIn('    Super + Shift + S ', (REPO / 'dotfiles/.local/share/arctic/keys.txt').read_text())

    def test_window_rule_matches_the_title(self):
        rules = (REPO / 'dotfiles/.config/mango/arctic/rules.conf').read_text()
        self.assertIn('title:^Arctic Settings$', rules)
        self.assertIn('title: "Arctic Settings"', (APP / 'shell.qml').read_text())


def arctic_binds():
    """(keymode, mods, key, flags, line) for every key bind in Arctic's own Mango files."""
    out = []
    for name in ('apps.conf', 'binds.conf'):
        keymode = 'default'
        for line in (REPO / 'dotfiles/.config/mango/arctic' / name).read_text().splitlines():
            line = line.strip()
            if line.startswith('keymode='):
                keymode = line.split('=', 1)[1].strip()
            match = re.match(r'^bind([a-z]*)=([^,]*),([^,]+),', line)
            if match:
                mods = frozenset(m.upper().replace('CONTROL', 'CTRL').replace('LOGO', 'SUPER')
                                 for m in match.group(2).split('+') if m.strip().upper() not in ('', 'NONE'))
                key = match.group(3).strip().lower()
                out.append((keymode, mods, 'grave' if key == 'code:49' else key, match.group(1), line))
    return out


class KeybindsTest(unittest.TestCase):
    """Arctic's binds as Mango sees them: every key once, and none that also switches layouts."""

    def test_no_duplicate_binds(self):
        seen = {}
        for keymode, mods, key, flags, line in arctic_binds():
            combo = (mods, key, 'r' in flags)
            for mode in (['default', 'common'] if keymode == 'common' else [keymode]):
                other = seen.get((mode,) + combo) or seen.get(('common',) + combo)
                self.assertIsNone(other, 'two binds on the same keys:\n  {}\n  {}'.format(other, line))
                seen[(mode,) + combo] = line

    def test_binds_avoid_layout_switch_chords(self):
        # Alt + Shift switches layouts on every two-layout install (the installer's default), so no
        # Arctic shortcut may hold both; Ctrl + Shift and Alt + Space do under the other options
        # Settings offers, and only these keys use them (Settings warns about them).
        allowed = {(frozenset({'CTRL', 'SHIFT'}), 'escape'), (frozenset({'SUPER', 'ALT'}), 'space')}
        for _mode, mods, key, _flags, line in arctic_binds():
            with self.subTest(line):
                self.assertFalse({'ALT', 'SHIFT'} <= mods, 'Alt + Shift switches the keyboard layout')
                if {'CTRL', 'SHIFT'} <= mods or ('ALT' in mods and key == 'space'):
                    self.assertIn((mods, key), allowed)

    def test_user_example_keys_stay_free(self):
        # The wiki and Settings suggest these for your own shortcuts (Super + Alt + F opens Firefox,
        # Super + Alt + M a web app).
        combos = {(mods, key) for _mode, mods, key, _flags, _line in arctic_binds()}
        for key in ('f', 'm'):
            self.assertNotIn((frozenset({'SUPER', 'ALT'}), key), combos)
        self.assertIn('bind=SUPER+ALT,f,spawn,firefox', (REPO / 'docs/wiki/Themes-and-Customisation.md').read_text())

    def test_arctic_dispatchers_have_labels(self):
        text = (APP / 'scripts/arctic_settings.py').read_text()
        labels = set(re.findall(r"'([a-z_]+)': '", text[text.index('DISPATCHERS = {'):text.index('RE_KEY =')]))
        for _mode, _mods, _key, _flags, line in arctic_binds():
            action = line.split(',')[2].strip()
            if action not in ('spawn', 'spawn_shell'):
                with self.subTest(line):
                    self.assertIn(action, labels)


if __name__ == '__main__':
    unittest.main()
