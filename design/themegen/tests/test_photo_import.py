"""Sensitive nested EXIF must not enter the publicly packaged photo collection."""
import importlib.util
import io
from pathlib import Path
import unittest

from PIL import Image

SPEC = importlib.util.spec_from_file_location('photo_import', Path(__file__).parents[2] / 'tools/import-wallpapers.py')
IMPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORT)


class PhotoMetadataTests(unittest.TestCase):
    def encoded(self, exif):
        data = io.BytesIO()
        Image.new('RGB', (16, 9)).save(data, format='JPEG', exif=exif)
        data.seek(0)
        return Image.open(data)

    def test_credit_only_exports_are_accepted(self):
        exif = Image.Exif()
        exif[315] = IMPORT.AUTHOR
        exif[33432] = 'Copyright 2026 ' + IMPORT.AUTHOR
        with self.encoded(exif) as image:
            IMPORT.verify_metadata(image, 'fixture')

    def test_nested_capture_date_and_camera_serial_are_rejected(self):
        exif = Image.Exif()
        exif[34665] = {36867: '2026:10:08 12:00:00', 42033: 'camera-private-serial'}
        with self.encoded(exif) as image:
            # The sensitive values really are nested rather than top-level.
            self.assertNotIn(36867, image.getexif())
            self.assertIn(36867, image.getexif().get_ifd(34665))
            with self.assertRaisesRegex(AssertionError, 'Unapproved EXIF'):
                IMPORT.verify_metadata(image, 'fixture')
