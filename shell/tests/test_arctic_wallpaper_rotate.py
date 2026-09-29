"""arctic-wallpaper rotate / next (dotfiles/.local/bin): a new picture every so often, from your
folder or Arctic's, without changing the saved choice or the colours; fake swaybg, systemd-run,
systemctl and arctic-hook log what they're asked.

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-wallpaper'


@unittest.skipIf(shutil.which('bash') is None or shutil.which('setsid') is None or shutil.which('shuf') is None,
                 'bash, setsid and shuf are needed')
class RotateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.config = root / 'config' / 'arctic'
        self.config.mkdir(parents=True)
        self.cache = root / 'cache' / 'arctic'
        self.pictures = root / 'Pictures' / 'Wallpapers'
        self.pictures.mkdir(parents=True)
        for name in ('a.png', 'b.jpg', 'c.webp', 'notes.txt'):
            (self.pictures / name).write_bytes(b'x')
        self.backgrounds = root / 'backgrounds'
        self.backgrounds.mkdir()
        for stem in ('aurora', 'fox', 'snowfield'):
            (self.backgrounds / (stem + '-polar-night.png')).write_bytes(b'x')
            (self.backgrounds / (stem + '-winter.png')).write_bytes(b'x')
        self.log = root / 'log'
        fakes = root / 'fakes'
        fakes.mkdir()
        for name in ('swaybg', 'systemd-run', 'systemctl', 'arctic-hook'):
            (fakes / name).write_text('#!/bin/sh\necho "{} $*" >> "{}"\n'.format(name, self.log))
            (fakes / name).chmod(0o755)
        # systemd-run --scope runs its command (in a scope of its own, for the real one).
        with (fakes / 'systemd-run').open('a') as f:
            f.write('case " $* " in *" --scope "*) while [ "$1" != -- ]; do shift; done; shift; exec "$@" ;; esac\n')
        self.fakes = fakes
        (fakes / 'xdg-user-dir').write_text('#!/bin/sh\necho "{}"\n'.format(root / 'Pictures'))
        (fakes / 'xdg-user-dir').chmod(0o755)
        (fakes / 'pgrep').write_text('#!/bin/sh\nexit 1\n')
        (fakes / 'pgrep').chmod(0o755)
        (self.config / 'wallpaper').write_text('fox\n')
        self.env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'),
                        XDG_CACHE_HOME=str(root / 'cache'), XDG_DATA_HOME=str(root / 'data'),
                        ARCTIC_BACKGROUNDS_DIR=str(self.backgrounds),
                        PATH=str(fakes) + ':/usr/bin:/bin')

    def tearDown(self):
        # The hooks run in the background (setsid): let them finish writing first.
        deadline = time.monotonic() + 5
        while len(self.calls('arctic-hook')) < len(self.calls('swaybg')) and time.monotonic() < deadline:
            time.sleep(0.1)
        time.sleep(0.2)
        self.tmp.cleanup()

    def wallpaper(self, *args, code=0):
        out = subprocess.run(['bash', str(HELPER)] + list(args), env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stderr)
        return out

    def drawn(self):
        return Path((self.cache / 'wallpaper-current').read_text().strip()).name

    def calls(self, prefix):
        return [l for l in (self.log.read_text().splitlines() if self.log.exists() else []) if l.startswith(prefix)]

    def test_rotate_saves_and_arms_the_timer(self):
        self.assertEqual(json.loads(self.wallpaper('rotate').stdout), {'every': 'off'})
        self.wallpaper('rotate', '30m')
        saved = json.loads(self.wallpaper('rotate').stdout)
        self.assertEqual(saved, {'every': '30m', 'folder': str(self.pictures.resolve()), 'shuffle': False})
        self.assertEqual(self.calls('systemd-run'), ['systemd-run --user --unit=arctic-wallpaper-rotate --collect --quiet '
                                                     '--property=KillMode=process '
                                                     '--on-active=30m --on-unit-active=30m -- arctic-wallpaper next'])
        self.wallpaper('rotate', 'apply')
        self.assertEqual(len(self.calls('systemd-run')), 2)
        self.wallpaper('rotate', '1d', 'arctic', '--shuffle')
        self.assertEqual(json.loads(self.wallpaper('rotate').stdout), {'every': '1d', 'folder': 'arctic', 'shuffle': True})
        self.wallpaper('rotate', 'off')
        self.assertFalse((self.config / 'wallpaper-rotate.json').exists())
        self.assertIn('systemctl --user stop arctic-wallpaper-rotate.timer arctic-wallpaper-rotate.service', self.calls('systemctl'))
        self.wallpaper('rotate', 'apply')                   # nothing to start
        self.assertEqual(len(self.calls('systemd-run')), 3)

    def test_refusals(self):
        self.wallpaper('rotate', '5m', code=2)
        self.wallpaper('rotate', '1h', str(self.pictures / 'nowhere'), code=2)
        empty = Path(self.tmp.name) / 'empty'
        empty.mkdir()
        self.wallpaper('rotate', '1h', str(empty), code=2)
        self.wallpaper('rotate', '1h', 'a', 'b', code=2)
        self.assertFalse((self.config / 'wallpaper-rotate.json').exists())

    def test_next_in_order_keeps_the_choice_and_the_colours(self):
        self.wallpaper('rotate', '1h', str(self.pictures))
        seen = []
        for _ in range(4):
            self.wallpaper('next')
            seen.append(self.drawn())
        self.assertEqual(seen, ['a.png', 'b.jpg', 'c.webp', 'a.png'])
        self.assertEqual((self.config / 'wallpaper').read_text(), 'fox\n')        # the choice stays
        self.assertEqual(len(self.calls('swaybg')), 4)
        # swaybg runs in a scope of its own: the timer's service must not take it along when it ends.
        self.assertEqual(len([c for c in self.calls('systemd-run --user --scope') if ' -- setsid -f swaybg ' in c]), 4)
        # Each picture runs the wallpaper hooks (in the background).
        deadline = time.monotonic() + 5
        while len(self.calls('arctic-hook')) < 4 and time.monotonic() < deadline:
            time.sleep(0.1)
        self.assertIn('arctic-hook wallpaper {}'.format((self.pictures / 'b.jpg').resolve()), self.calls('arctic-hook'))

    def test_pictures_with_the_same_name(self):
        (self.pictures / 'a.jpg').write_bytes(b'x')
        self.wallpaper('rotate', '1h', str(self.pictures))
        seen = []
        for _ in range(5):
            self.wallpaper('next')
            seen.append(self.drawn())
        self.assertEqual(seen, ['a.jpg', 'a.png', 'b.jpg', 'c.webp', 'a.jpg'])

    def test_without_a_user_manager(self):
        # systemd-run can't reach one: swaybg still starts (plain setsid).
        (self.fakes / 'systemd-run').write_text('#!/bin/sh\necho "systemd-run $*" >> "{}"\nexit 1\n'.format(self.log))
        self.wallpaper('snowfield')
        self.assertEqual(len(self.calls('swaybg')), 1)

    def test_shuffle_shows_each_picture_once_a_round(self):
        self.wallpaper('rotate', '30m', str(self.pictures), '--shuffle')
        first = [None]
        for _ in range(3):
            self.wallpaper('next')
            first.append(self.drawn())
        self.assertEqual(sorted(first[1:]), ['a.png', 'b.jpg', 'c.webp'])
        self.wallpaper('next')                                  # a new round, not the same twice
        self.assertNotEqual(self.drawn(), first[-1])

    def test_arctics_own(self):
        self.wallpaper('rotate', '1h', 'arctic')
        names = set()
        for _ in range(3):
            self.wallpaper('next')
            names.add(self.drawn())
        self.assertEqual(names, {'aurora-polar-night.png', 'fox-polar-night.png', 'snowfield-polar-night.png'})


if __name__ == '__main__':
    unittest.main()
