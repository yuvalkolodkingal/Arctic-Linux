"""Tests for the shell's Python helpers that don't need a desktop:
scripts/package-index.py (the Get apps package index) and scripts/wallpapers.py (the picker).

Run: python3 -m unittest discover -s shell/tests
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import contextlib
import subprocess
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'


def load(name, env):
    """Import a script fresh with its paths computed from `env`."""
    old = {k: os.environ.get(k) for k in env}
    os.environ.update(env)
    try:
        spec = importlib.util.spec_from_file_location(name.replace('-', '_'), SCRIPTS / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for k, v in old.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def fake_command(folder, name, script):
    path = Path(folder) / name
    path.write_text('#!/bin/sh\n' + script + '\n')
    path.chmod(0o755)


class PackageIndexTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.cache = self.root / 'cache'
        # A fake dnf5 that lists three packages (neovim twice, as for two architectures) and a
        # fake flatpak whose system installation has the flathub remote.
        fake_command(self.bin, 'dnf5', 'printf "neovim\\tfedora\\tVim-fork focused on extensibility\\nhtop\\tupdates\\tInteractive process viewer\\n'
                                       'neovim\\tfedora\\tsecond arch\\nfish\\tfedora\\tFriendly interactive shell\\n'
                                       'not a name\\tfedora\\tx\\n"; printf "%s\\n" "$*" > "$(dirname "$0")/dnf-args"')
        fake_command(self.bin, 'flatpak', 'echo "$@" >> "$(dirname "$0")/flatpak-args"\n'
                                          'case "$1 $2" in "remotes --system") echo flathub ;; "remotes --user") ;; '
                                          '"remote-ls --system") printf "org.gimp.GIMP\\tGIMP\\tCreate images and edit photographs\\n'
                                          'app.zen_browser.zen\\tZen Browser\\tA calmer internet\\n" ;; *) exit 1 ;; esac')

    def tearDown(self):
        self.tmp.cleanup()

    def run_index(self, *args):
        env = dict(os.environ, XDG_CACHE_HOME=str(self.cache), PATH=str(self.bin) + ':/usr/bin:/bin')
        out = subprocess.run([sys.executable, str(SCRIPTS / 'package-index.py'), *args], env=env,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, 0, out.stderr)
        return [json.loads(line) for line in out.stdout.splitlines()]

    def test_first_run_reports_empty_then_refreshed_names(self):
        lines = self.run_index()
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], {'packages': [], 'refreshing': True, 'error': ''})
        self.assertEqual(lines[1]['packages'], ['fish', 'htop', 'neovim', 'flathub:app.zen_browser.zen', 'flathub:org.gimp.GIMP'])
        self.assertFalse(lines[1]['refreshing'])
        self.assertIn('repoquery --available --qf %{name}\t%{repoid}\t%{summary}\\n', (self.bin / 'dnf-args').read_text())
        self.assertIn('remote-ls --system --app --columns=application,name,description flathub', (self.bin / 'flatpak-args').read_text())

    def test_details_keep_summaries(self):
        lines = self.run_index('--details')
        self.assertEqual(lines[1]['details']['dnf'][2], ['neovim', 'fedora', 'Vim-fork focused on extensibility'])
        self.assertEqual(lines[1]['details']['flathub'][1], ['org.gimp.GIMP', 'GIMP', 'Create images and edit photographs'])
        self.assertNotIn('details', self.run_index()[0])

    def test_fresh_cache_is_not_refreshed_unless_forced(self):
        self.run_index()
        (self.bin / 'dnf-args').unlink()
        lines = self.run_index()
        self.assertEqual(len(lines), 1)
        self.assertFalse(lines[0]['refreshing'])
        self.assertEqual(len(lines[0]['packages']), 5)
        self.assertFalse((self.bin / 'dnf-args').exists())
        self.assertEqual(len(self.run_index('--force')), 2)
        self.assertTrue((self.bin / 'dnf-args').exists())

    def test_stale_cache_is_shown_then_refreshed(self):
        self.run_index()
        old = time.time() - 3 * 24 * 3600
        for f in (self.cache / 'arctic').glob('*.tsv'):
            os.utime(f, (old, old))
        lines = self.run_index()
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0]['refreshing'])
        self.assertEqual(len(lines[0]['packages']), 5)   # the old list right away

    def test_old_name_caches_are_read(self):
        folder = self.cache / 'arctic'
        folder.mkdir(parents=True)
        (folder / 'packages.txt').write_text('gimp\nneovim\n')
        (folder / 'flathub.txt').write_text('org.gimp.GIMP\n')
        fake_command(self.bin, 'dnf5', 'exit 1')
        lines = self.run_index('--details')
        self.assertEqual(lines[0]['packages'], ['gimp', 'neovim', 'flathub:org.gimp.GIMP'])
        self.assertEqual(lines[0]['details']['dnf'][0], ['gimp', '', ''])

    def test_failing_commands_report_an_error_sentence(self):
        fake_command(self.bin, 'dnf5', 'echo "Cannot download metadata" >&2; exit 1')
        self.assertEqual(self.run_index()[-1]['error'], 'Could not read the dnf package list.')
        fake_command(self.bin, 'flatpak', 'case "$1 $2" in "remotes --system") echo flathub ;; *) exit 1 ;; esac')
        self.assertEqual(self.run_index('--force')[-1]['error'],
                         'Could not read the dnf package list. Could not read the Flathub app list.')

    def test_no_flathub_remote_is_not_an_error(self):
        fake_command(self.bin, 'flatpak', 'exit 0')
        lines = self.run_index()
        self.assertEqual(lines[-1]['error'], '')
        self.assertEqual(lines[-1]['packages'], ['fish', 'htop', 'neovim'])
        self.assertEqual(len(self.run_index()), 1)   # and the empty Flathub list counts as fresh


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        from PIL import Image
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = dict(XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache'),
                        XDG_DATA_HOME=str(root / 'data'), HOME=str(root / 'home'))
        self.data = root / 'data' / 'arctic' / 'wallpapers'
        self.data.mkdir(parents=True)
        for stem in ('aurora-polar-night', 'aurora-winter', 'fox-polar-night', 'fox-winter'):
            Image.new('RGB', (64, 36), (20, 30, 40)).save(self.data / (stem + '.png'))
        self.pictures = root / 'home' / 'Pictures' / 'Wallpapers'
        self.pictures.mkdir(parents=True)
        Image.new('RGB', (80, 50), (200, 100, 50)).save(self.pictures / 'my-dog_photo.jpg')
        (self.pictures / 'notes.txt').write_text('not a picture')
        (self.pictures / 'broken.png').write_bytes(b'not really a png')
        self.config = root / 'config' / 'arctic'
        self.config.mkdir(parents=True)
        self.module = load('wallpapers', self.env)
        self.module.SYSTEM = [self.data]          # keep /usr/share out of the test

    def tearDown(self):
        self.tmp.cleanup()

    def test_arctic_wallpapers_first_in_the_active_theme_then_your_pictures(self):
        (self.config / 'theme').write_text('winter\n')
        result = self.module.library()
        keys = [item['key'] for item in result['items']]
        self.assertEqual(keys[:2], ['aurora', 'fox'])        # snowfield isn't installed here
        self.assertTrue(result['items'][0]['path'].endswith('aurora-winter.png'))
        self.assertEqual(result['items'][2]['name'], 'my dog photo')
        self.assertEqual(len(keys), 3)                        # text file and broken image skipped
        for item in result['items']:
            self.assertTrue(Path(item['thumb']).is_file())
        self.assertEqual(result['current'], 'snowfield')      # nothing saved: the theme default

    def test_theme_made_from_a_picture_shows_its_base_drawing(self):
        # arctic-theme's 'wallpaper' theme: the Arctic wallpapers follow its base / mode.
        (self.config / 'theme').write_text('wallpaper\n')
        current = self.config / 'current'
        current.mkdir()
        (current / 'theme.env').write_text('ARCTIC_THEME=wallpaper\nARCTIC_THEME_MODE=light\nARCTIC_THEME_BASE=winter\n')
        self.assertEqual(self.module.theme(), 'winter')
        (current / 'theme.env').write_text('ARCTIC_THEME=mine\nARCTIC_THEME_MODE=dark\nARCTIC_THEME_BASE=mine\n')
        self.assertEqual(self.module.theme(), 'polar-night')
        (current / 'theme.env').write_text('ARCTIC_THEME=mine\nARCTIC_THEME_MODE=light\n')
        self.assertEqual(self.module.theme(), 'winter')
        self.assertTrue(self.module.library()['items'][0]['path'].endswith('aurora-winter.png'))

    def test_current_follows_the_saved_choice(self):
        (self.config / 'wallpaper').write_text('fox\n')
        self.assertEqual(self.module.library()['current'], 'fox')

    def test_folder_is_saved(self):
        other = Path(self.tmp.name) / 'elsewhere'
        other.mkdir()
        with contextlib.redirect_stdout(io.StringIO()) as out:
            sys.argv = ['wallpapers.py', 'folder', 'file://' + str(other)]
            self.module.main()
        self.assertTrue(json.loads(out.getvalue())['ok'])
        self.assertEqual(json.loads((self.config / 'wallpapers.json').read_text())['folder'], str(other))
        with self.assertRaises(ValueError):
            sys.argv = ['wallpapers.py', 'folder', str(other / 'missing')]
            self.module.main()

    def test_apply_refuses_unknown_pictures(self):
        with self.assertRaises(ValueError):
            sys.argv = ['wallpapers.py', 'apply', '/nonexistent/picture.png']
            self.module.main()


if __name__ == '__main__':
    unittest.main()
