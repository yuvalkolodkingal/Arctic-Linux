#!/usr/bin/env python3
import configparser
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
WRAPPER = ROOT / 'packaging/desktop/arctic-celluloid'
DESKTOP = ROOT / 'packaging/desktop/io.github.celluloid_player.Celluloid.desktop'
VENDOR_DESKTOP_SHA256 = '29375bae7cef0d2c0f803112b79d445a714cf729454bbfc6ab5eba1321e0063d'
CELLULOID_LICENSE_SHA256 = 'ca372a7d92560b1fa9f6d832b440e8bcd62d9adfa8870c98287deab66d98310e'
PROVENANCE = (
    '# Arctic launch override derived from Fedora 44 celluloid-0.30-1.fc44.x86_64.\n'
    '# Vendor desktop SHA-256: 29375bae7cef0d2c0f803112b79d445a714cf729454bbfc6ab5eba1321e0063d\n'
    '# Fedora RPM SHA-256: f6fa48f333c0664bb3f5a6efae0ab3643e3688b4304dd938911df8a4efd63f32\n'
    '# Celluloid is GPL-3.0-or-later; translations and desktop metadata are retained.\n'
    '# Arctic adds TryExec so removing the optional Celluloid package hides this override.\n'
)


class CelluloidProductLaunchTest(unittest.TestCase):
    def test_wrapper_defaults_unset_renderer_and_preserves_override_and_arguments(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            capture = root / 'capture'
            target = root / 'celluloid'
            target.write_text('#!/bin/sh\nprintf "%s\\n" "$GSK_RENDERER" "$@" >"$CAPTURE"\n')
            target.chmod(0o755)
            wrapper = root / 'arctic-celluloid'
            wrapper.write_text(WRAPPER.read_text().replace('/usr/bin/celluloid', str(target)))
            wrapper.chmod(0o755)
            base = {**os.environ, 'CAPTURE': str(capture)}
            base.pop('GSK_RENDERER', None)
            subprocess.run([wrapper, '--new-window', 'a b.mkv'], env=base, check=True)
            self.assertEqual(capture.read_text().splitlines(), ['gl', '--new-window', 'a b.mkv'])
            subprocess.run([wrapper, '--enqueue', 'movie.mkv'],
                           env={**base, 'GSK_RENDERER': 'vulkan'}, check=True)
            self.assertEqual(capture.read_text().splitlines(), ['vulkan', '--enqueue', 'movie.mkv'])

    def test_same_id_override_changes_only_launch_keys_from_pinned_localized_vendor_file(self):
        text = DESKTOP.read_text()
        self.assertTrue(text.startswith(PROVENANCE))
        restored = text[len(PROVENANCE):]
        self.assertEqual(restored.count('TryExec=/usr/bin/celluloid\n'), 1)
        restored = restored.replace('TryExec=/usr/bin/celluloid\n', '')
        replacements = (
            ('Exec=/usr/libexec/arctic/arctic-celluloid %U', 'Exec=celluloid %U'),
            ('DBusActivatable=false', 'DBusActivatable=true'),
            ('Exec=/usr/libexec/arctic/arctic-celluloid --new-window', 'Exec=celluloid --new-window'),
            ('Exec=/usr/libexec/arctic/arctic-celluloid --enqueue %U', 'Exec=celluloid --enqueue %U'),
        )
        for new, old in replacements:
            self.assertEqual(restored.count(new), 1)
            restored = restored.replace(new, old)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), VENDOR_DESKTOP_SHA256)
        for required in ('Name[ar]=', 'GenericName[de]=', 'Comment[zh_CN]=',
                         'Keywords[fr]=', 'Name[ja]=新しいウィンドウ',
                         'Name[ar]=أضِف إلى قائمة التشغيل'):
            self.assertIn(required, text)

    def test_same_id_desktop_override_covers_main_and_actions_without_dbus_bypass(self):
        data = configparser.ConfigParser(interpolation=None, strict=True)
        data.optionxform = str
        data.read(DESKTOP)
        main = data['Desktop Entry']
        self.assertEqual(main['Exec'], '/usr/libexec/arctic/arctic-celluloid %U')
        self.assertEqual(main['TryExec'], '/usr/bin/celluloid')
        self.assertEqual(main['DBusActivatable'], 'false')
        self.assertIn('video/x-matroska;', main['MimeType'])
        self.assertEqual(data['Desktop Action new-window']['Exec'],
                         '/usr/libexec/arctic/arctic-celluloid --new-window')
        self.assertEqual(data['Desktop Action enqueue']['Exec'],
                         '/usr/libexec/arctic/arctic-celluloid --enqueue %U')
        self.assertEqual(DESKTOP.name, 'io.github.celluloid_player.Celluloid.desktop')

    def test_upstream_gpl_license_is_pinned_declared_and_shipped(self):
        license_path = ROOT / 'packaging/desktop/COPYING.celluloid'
        self.assertEqual(hashlib.sha256(license_path.read_bytes()).hexdigest(),
                         CELLULOID_LICENSE_SHA256)
        self.assertIn('GNU GENERAL PUBLIC LICENSE\n                       Version 3',
                      license_path.read_text())
        spec = (ROOT / 'packaging/arctic-linux.spec').read_text()
        self.assertIn('License:        MIT AND LGPL-2.1-or-later AND OFL-1.1 AND ISC AND GPL-3.0-or-later', spec)
        self.assertIn('%license LICENSE packaging/desktop/COPYING.celluloid', spec)

    def _xdg(self, value):
        script = ROOT / 'packaging/desktop/arctic-nix.sh'
        with tempfile.TemporaryDirectory() as home:
            prefix = f'HOME={home!s} '
            if value is not None:
                prefix += "XDG_DATA_DIRS='" + value + "' "
            command = prefix + f'. {script!s}; printf "%s" "$XDG_DATA_DIRS"'
            return subprocess.run(['/bin/sh', '-c', command], text=True,
                                  capture_output=True, check=True).stdout.split(':')

    def test_xdg_precedence_default_insert_dedupe_and_wrong_order_repair(self):
        cases = (
            (None, ['/usr/local/share', '/var/lib/flatpak/exports/share',
                    '/usr/share/arctic', '/usr/share']),
            ('/opt/admin/share:/var/lib/flatpak/exports/share:/usr/share',
             ['/opt/admin/share', '/var/lib/flatpak/exports/share',
              '/usr/share/arctic', '/usr/share']),
            ('/opt/admin/share:/usr/share/arctic:/usr/share',
             ['/opt/admin/share', '/usr/share/arctic', '/usr/share']),
            ('/opt/admin/share:/usr/share:/usr/share/arctic:/usr/share/arctic',
             ['/opt/admin/share', '/usr/share/arctic', '/usr/share']),
        )
        nix = ['/nix/var/nix/profiles/default/share']
        for value, tail in cases:
            with self.subTest(value=value):
                actual = self._xdg(value)
                self.assertEqual(actual[-len(tail):], tail)
                self.assertEqual(actual.count('/usr/share/arctic'), 1)
                self.assertLess(actual.index('/opt/admin/share'), actual.index('/usr/share/arctic')) if value else None
                self.assertTrue(all(actual.index(item) < actual.index('/usr/share/arctic')
                                    for item in actual if item.startswith('/nix/') or item.startswith('/tmp/')))

    def test_xdg_explicit_vendor_exclusion_is_preserved(self):
        actual = self._xdg('/opt/kiosk/share:/var/lib/flatpak/exports/share')
        self.assertNotIn('/usr/share', actual)
        self.assertNotIn('/usr/share/arctic', actual)
        self.assertEqual(actual[-2:], ['/opt/kiosk/share', '/var/lib/flatpak/exports/share'])


if __name__ == '__main__':
    unittest.main()
