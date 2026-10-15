#!/usr/bin/env python3
import configparser
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / 'packaging/desktop/arctic-epiphany'
DESKTOP = ROOT / 'packaging/desktop/org.gnome.Epiphany.desktop'
VENDOR_DESKTOP_SHA256 = '640ef9c330f0cde40e87db2499c251c00c418833a1f60ad81e723dfc957e5dfb'
PROVENANCE = (
    '# Arctic launch override derived from Fedora 44 epiphany-50.6-1.fc44.x86_64.\n'
    '# Vendor desktop SHA-256: 640ef9c330f0cde40e87db2499c251c00c418833a1f60ad81e723dfc957e5dfb\n'
    '# Fedora RPM SHA-256: b3543b27d1732f2a480b129788694f8414a8108393df169c53231075fe3ee260\n'
    '# Epiphany is GPL-3.0-or-later; translations and desktop metadata are retained.\n'
    '# Arctic adds TryExec so removing the optional Epiphany package hides this override.\n'
)


class EpiphanyProductLaunchTest(unittest.TestCase):
    def test_installer_profiles_live_default_and_benchmark_use_product_route(self):
        command = 'gtk-launch org.gnome.Epiphany'
        module = tomllib.loads((ROOT / 'modules/browser/gnome-web/module.toml').read_text())
        catalog = tomllib.loads((ROOT / 'modules/catalog.toml').read_text())
        self.assertEqual(module['defaults']['command'], command)
        browser = next(category for category in catalog['category'] if category['id'] == 'browser')
        self.assertIn(module['id'], browser['modules'])
        for relative in ('profiles/defaults.toml', 'profiles/ci/offline.toml',
                         'tools/reliability/profiles/lightweight.toml'):
            profile = tomllib.loads((ROOT / relative).read_text())
            self.assertEqual(profile['apps']['browser'], [module['id']], relative)
        defaults = dict(line.split('=', 1) for line in
                        (ROOT / 'packaging/desktop/live-default-apps').read_text().splitlines()
                        if line and not line.startswith('#'))
        self.assertEqual(defaults['browser'], command)
        spec = importlib.util.spec_from_file_location(
            'epiphany_product_performance_guest', ROOT / 'tools/performance/guest.py')
        guest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guest)
        self.assertEqual(guest.ROLE_APPS[module['id']]['configured'], (command,))

    def test_wrapper_preserves_renderer_override_and_every_launch_mode(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            capture = root / 'capture'
            target = root / 'epiphany'
            target.write_text('#!/bin/sh\nprintf "%s\\n" "$GSK_RENDERER" "$@" >"$CAPTURE"\n')
            target.chmod(0o755)
            wrapper = root / 'arctic-epiphany'
            wrapper.write_text(WRAPPER.read_text().replace('/usr/bin/epiphany', str(target)))
            wrapper.chmod(0o755)
            base = {**os.environ, 'CAPTURE': str(capture)}
            base.pop('GSK_RENDERER', None)
            for arguments in (('https://example.invalid/',),
                              ('--new-window', 'https://example.invalid/new'),
                              ('--incognito-mode', 'https://example.invalid/private')):
                subprocess.run([wrapper, *arguments], env=base, check=True)
                self.assertEqual(capture.read_text().splitlines(), ['gl', *arguments])
            subprocess.run([wrapper, '--new-window'],
                           env={**base, 'GSK_RENDERER': 'vulkan'}, check=True)
            self.assertEqual(capture.read_text().splitlines(), ['vulkan', '--new-window'])

    def test_wrapper_delegates_existing_instance_policy_to_epiphany(self):
        text = WRAPPER.read_text()
        self.assertEqual(text.count('exec /usr/bin/epiphany "$@"'), 1)
        for forbidden in ('pkill', 'killall', 'pgrep', 'busctl', 'gdbus'):
            self.assertNotIn(forbidden, text)

    def test_same_id_override_changes_only_launch_integration(self):
        text = DESKTOP.read_text()
        self.assertTrue(text.startswith(PROVENANCE))
        restored = text[len(PROVENANCE):]
        self.assertEqual(restored.count('TryExec=/usr/bin/epiphany\n'), 1)
        restored = restored.replace('TryExec=/usr/bin/epiphany\n', '')
        replacements = (
            ('Exec=/usr/libexec/arctic/arctic-epiphany %U', 'Exec=epiphany %U'),
            ('DBusActivatable=false\n', ''),
            ('Exec=/usr/libexec/arctic/arctic-epiphany --new-window %U',
             'Exec=epiphany --new-window %U'),
            ('Exec=/usr/libexec/arctic/arctic-epiphany --incognito-mode %U',
             'Exec=epiphany --incognito-mode %U'),
        )
        for new, old in replacements:
            self.assertEqual(restored.count(new), 1)
            restored = restored.replace(new, old)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), VENDOR_DESKTOP_SHA256)
        for localized in ('Name[ar]=', 'GenericName[de]=', 'Comment[zh_CN]=',
                          'Keywords[fr]=', 'Name[he]=חלון חדש',
                          'Name[he]=חלון גלישת סתר חדש'):
            self.assertIn(localized, text)

    def test_desktop_override_covers_mime_gio_and_both_actions(self):
        data = configparser.ConfigParser(interpolation=None, strict=True)
        data.optionxform = str
        data.read(DESKTOP)
        main = data['Desktop Entry']
        self.assertEqual(main['Exec'], '/usr/libexec/arctic/arctic-epiphany %U')
        self.assertEqual(main['TryExec'], '/usr/bin/epiphany')
        self.assertEqual(main['DBusActivatable'], 'false')
        for mime in ('text/html;', 'x-scheme-handler/http;', 'x-scheme-handler/https;'):
            self.assertIn(mime, main['MimeType'])
        self.assertEqual(data['Desktop Action new-window']['Exec'],
                         '/usr/libexec/arctic/arctic-epiphany --new-window %U')
        self.assertEqual(data['Desktop Action Incognito']['Exec'],
                         '/usr/libexec/arctic/arctic-epiphany --incognito-mode %U')
        self.assertEqual(DESKTOP.name, 'org.gnome.Epiphany.desktop')

    def test_package_wires_launcher_and_override(self):
        spec = (ROOT / 'packaging/arctic-linux.spec').read_text()
        self.assertIn('packaging/desktop/arctic-epiphany %{buildroot}%{_libexecdir}/arctic/arctic-epiphany', spec)
        self.assertIn('packaging/desktop/org.gnome.Epiphany.desktop', spec)
        self.assertIn('%{_datadir}/arctic/applications/org.gnome.Epiphany.desktop', spec)
        self.assertIn('desktop-file-validate %{buildroot}%{_datadir}/arctic/applications/org.gnome.Epiphany.desktop', spec)
        self.assertIn('sh -n %{buildroot}%{_libexecdir}/arctic/arctic-epiphany', spec)


if __name__ == '__main__':
    unittest.main()
