"""Image privacy, validation, commit failures and persisted shared wallpaper policy."""
import io
import json
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, PngImagePlugin

MODULE = runpy.run_path(str(Path(__file__).resolve().parents[2] / 'dotfiles/.local/bin/arctic-login-wallpaper'))
Store = MODULE['Store']
normalize = MODULE['normalize']
read_image = MODULE['read_image']


def picture(color='red', fmt='PNG', **kwargs):
    out = io.BytesIO()
    Image.new('RGB', (80, 60), color).save(out, format=fmt, **kwargs)
    return out.getvalue()


class SharedWallpaper(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'public')

    def tearDown(self):
        self.temp.cleanup()

    def test_upgrade_default_is_legacy_and_does_not_create_public_files(self):
        self.assertEqual(self.store.status()['mode'], 'legacy')
        self.assertFalse(self.store.root.exists())

    def test_normalization_strips_metadata_and_supports_three_raster_types(self):
        meta = PngImagePlugin.PngInfo()
        meta.add_text('Comment', 'private location')
        for fmt in ('PNG', 'JPEG', 'WEBP'):
            data = picture(fmt=fmt, **({'pnginfo': meta} if fmt == 'PNG' else {}))
            with Image.open(io.BytesIO(normalize(data))) as result:
                self.assertEqual(result.format, 'PNG')
                self.assertFalse(result.info)

    def test_rejects_bad_type_truncation_animation_and_size(self):
        for data in (b'<svg/>', b'not an image', picture()[:40], picture(fmt='BMP'),
                     b'x' * (MODULE['MAX_BYTES'] + 1)):
            with self.assertRaises(Exception):
                normalize(data)
        data = io.BytesIO()
        Image.new('RGB', (20, 20), 'red').save(data, format='PNG', save_all=True,
                                             append_images=[Image.new('RGB', (20, 20), 'blue')])
        with self.assertRaises(ValueError):
            normalize(data.getvalue())

    def test_bounds_and_exif_orientation(self):
        image = Image.new('RGB', (4000, 3000), 'blue')
        exif = Image.Exif()
        exif[274] = 6
        exif[34853] = {}  # GPS metadata must not be carried into the public file.
        data = io.BytesIO()
        image.save(data, format='JPEG', exif=exif)
        with Image.open(io.BytesIO(normalize(data.getvalue()))) as result:
            self.assertEqual(result.size, (1620, 2160))
            self.assertFalse(result.getexif())

    def test_regular_absolute_paths_no_symlinks_special_files_or_urls(self):
        source = self.root / 'private.png'
        source.write_bytes(picture())
        self.assertEqual(read_image(str(source)), normalize(picture()))
        link = self.root / 'link.png'
        link.symlink_to(source)
        folder = self.root / 'shortcut'
        folder.symlink_to(self.root, target_is_directory=True)
        for path in (str(link), str(folder / 'private.png'), 'private.png',
                     'https://example.org/image.png', '/dev/null', str(source) + '\n'):
            with self.assertRaises(Exception):
                read_image(path)
        fifo = self.root / 'pipe.png'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError):
            read_image(str(fifo))

    def test_atomic_generation_and_restart_owner_mode_no_source_path(self):
        state = self.store.commit('desktop', 1000, picture())
        restarted = Store(self.store.root)
        self.assertEqual(restarted.status(), state)
        text = (self.store.root / 'current/state.json').read_text()
        self.assertNotIn(str(self.root), text)
        for file in (self.store.root / 'current').iterdir():
            self.assertEqual(file.stat().st_mode & 0o777, 0o644)

    def test_validation_and_commit_failure_keep_previous_image_and_policy(self):
        previous = self.store.commit('separate', 1000, picture())
        for data in (b'bad image', picture('blue')):
            with patch('os.replace', side_effect=OSError('disk full')):
                with self.assertRaises(Exception):
                    self.store.commit('desktop', 1001, data)
            self.assertEqual(self.store.status(), previous)
        self.assertEqual(len(list(self.store.root.glob('generation-*'))), 1)

    def test_rapid_changes_bounded_history_undo_and_reset_remove_public_copies(self):
        for n in range(10):
            state = self.store.commit('separate', n, picture('red' if n % 2 else 'blue'))
        self.assertEqual(len(list(self.store.root.glob('generation-*'))), 3)
        undone = self.store.undo()
        self.assertEqual(undone['owner'], 8)
        self.assertNotEqual(undone['revision'], state['previous'].removeprefix('generation-'))
        self.store.commit('legacy', -1)
        self.assertFalse(self.store.status()['enabled'])
        self.assertEqual(list(self.store.root.rglob('wallpaper.png')), [])

    def test_missing_and_corrupt_state_remain_recoverable(self):
        for invalid in ({'enabled': True}, [], {'enabled': 'yes'}):
            current = self.store.commit('separate', 1000, picture())
            (self.store.root / 'current/state.json').write_text(json.dumps(invalid))
            self.assertIn('state_error', self.store.status())
            # A valid new choice succeeds even if old cleanup metadata is corrupt.
            recovered = self.store.commit('desktop', 1000, picture('blue'))
            self.assertEqual(self.store.status(), recovered)
        (self.store.root / 'current/wallpaper.png').unlink()
        self.assertTrue(self.store.status()['image_missing'])
        self.store.commit('legacy', -1)
        self.assertFalse(self.store.status()['enabled'])

    def test_undo_validates_previous_before_changing_pointer(self):
        old = self.store.commit('separate', 1000, picture())
        now = self.store.commit('desktop', 1000, picture('blue'))
        (self.store.root / ('generation-' + old['revision']) / 'wallpaper.png').unlink()
        with self.assertRaises(OSError):
            self.store.undo()
        self.assertEqual(self.store.status(), now)

    def test_reset_reports_partial_cleanup_and_can_retry(self):
        self.store.commit('separate', 1000, picture())
        with patch('shutil.rmtree', side_effect=OSError('permission denied')):
            result = self.store.commit('legacy', -1)
        self.assertFalse(result['enabled'])
        self.assertIn('cleanup_error', result)
        self.assertIn('cleanup_error', self.store.status())
        self.store.commit('legacy', -1)
        self.assertNotIn('cleanup_error', self.store.status())
        self.assertEqual(list(self.store.root.rglob('wallpaper.png')), [])

    def test_authorized_choice_repairs_invalid_pointer(self):
        self.store.root.mkdir()
        (self.store.root / 'current').symlink_to('generation-invalid')
        self.assertIn('state_error', self.store.status())
        repaired = self.store.commit('separate', 1000, picture())
        self.assertEqual(self.store.status(), repaired)


if __name__ == '__main__':
    unittest.main()
