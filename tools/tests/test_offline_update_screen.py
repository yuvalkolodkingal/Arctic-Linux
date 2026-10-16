"""The offline update may safely unlock the observed plain Plymouth prompt."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    'offline_update_screen', ROOT / 'tools/performance/offline_screen.py')
offline_screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(offline_screen)


class OfflineUpdateScreenTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'screen.png'

    def test_exact_failed_run_frame_is_the_plain_luks_prompt(self):
        path = ROOT / 'tools/tests/fixtures/plain-plymouth-password-prompt-38746835597.png'
        self.assertEqual(
            hashlib.sha256(path.read_bytes()).hexdigest(),
            '3fc13f1985fa902ab9e443a53c2f35dbe21a073f54a3bc6f122e94a0b00d07e0')
        self.assertTrue(offline_screen.looks_like_plain_luks_prompt(path))

    def test_unrelated_text_canvases_fail_closed(self):
        background = (46, 52, 54)
        for name, image in (
                ('dark', Image.new('RGB', (1280, 800), background)),
                ('wrong-position', Image.new('RGB', (1280, 800), background)),
                ('too-short', Image.new('RGB', (1280, 800), background)),
                ('extra-colour', Image.open(
                    ROOT / 'tools/tests/fixtures/plain-plymouth-password-prompt-38746835597.png'
                ).convert('RGB'))):
            draw = ImageDraw.Draw(image)
            if name == 'wrong-position':
                draw.rectangle((0, 500, 600, 530), fill=(255, 255, 255))
            elif name == 'too-short':
                draw.rectangle((0, 180, 100, 205), fill=(255, 255, 255))
            elif name == 'extra-colour':
                draw.rectangle((400, 300, 900, 360), fill=(246, 189, 85))
            with self.subTest(name=name):
                image.save(self.path)
                self.assertFalse(offline_screen.looks_like_plain_luks_prompt(self.path))

    def test_missing_or_small_frame_fails_closed(self):
        self.assertFalse(offline_screen.looks_like_plain_luks_prompt(
            self.path.with_name('missing.png')))
        Image.new('RGB', (320, 200), (46, 52, 54)).save(self.path)
        self.assertFalse(offline_screen.looks_like_plain_luks_prompt(self.path))


if __name__ == '__main__':
    unittest.main()
