"""Boot input detection must distinguish login controls from amber wallpaper."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('vmtest_screen', ROOT / 'tools/lib/vmtest.py')
vmtest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vmtest)


class ScreenDetectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'screen.png'

    def classify(self, image):
        image.save(self.path)
        return vmtest.classify(self.path)

    def password_changed(self, before, after):
        before_path = self.path.with_name('before.png')
        after_path = self.path.with_name('after.png')
        before.save(before_path)
        after.save(after_path)
        return vmtest.login_password_changed(before_path, after_path)

    def password_cleared(self, before, after):
        before_path = self.path.with_name('before.png')
        after_path = self.path.with_name('after.png')
        before.save(before_path)
        after.save(after_path)
        return vmtest.login_password_cleared(before_path, after_path)

    def login(self, warm=False, scale=1):
        # Original, unretouched password/button pixels from the retained candidate
        # capture, crop (479,478,797,526), excluding the avatar and test user's name.
        # Full capture SHA256: 0fa6941815a5db897aaf6e33af861a85f7d309a7772c26532f861485b718444e.
        controls = Image.open(ROOT / 'tools/tests/fixtures/sddm-password-controls.png').convert('RGB')
        controls = controls.resize((round(controls.width * scale), round(controls.height * scale)),
                                   Image.Resampling.NEAREST)
        image = Image.new('RGB', (round(1280 * scale), round(800 * scale)), (24, 28, 34))
        if warm:
            # Wide amber rows, like the actual sunset, defeat the old global run count.
            ImageDraw.Draw(image).rectangle((0, 80, image.width - 1, 200), fill=vmtest.AMBER)
        image.paste(controls, (image.width // 2 - round(161 * scale), round(478 * scale)))
        return image

    def test_captured_controls_with_amber_background_are_login(self):
        self.assertEqual(self.classify(self.login(warm=True)), 'login')

    def test_captured_controls_with_dark_background_are_login(self):
        self.assertEqual(self.classify(self.login()), 'login')

    def test_control_geometry_at_multiple_scales(self):
        for scale in (0.75, 1.5, 2):
            with self.subTest(scale=scale):
                self.assertEqual(self.classify(self.login(warm=True, scale=scale)), 'login')

    def test_grub_filled_selection_remains_grub(self):
        image = Image.new('RGB', (1280, 800), (24, 28, 34))
        ImageDraw.Draw(image).rectangle((430, 350, 850, 390), fill=vmtest.AMBER)
        self.assertEqual(self.classify(image), 'grub')

    def test_plymouth_outline_without_button_remains_prompt(self):
        image = Image.new('RGB', (1280, 800), (24, 28, 34))
        ImageDraw.Draw(image).rectangle((430, 380, 850, 424), outline=vmtest.AMBER, width=2)
        self.assertEqual(self.classify(image), 'prompt')

    def test_button_without_password_edges_is_not_login(self):
        image = Image.new('RGB', (1280, 800), (24, 28, 34))
        ImageDraw.Draw(image).rectangle((752, 480, 795, 523), fill=vmtest.AMBER)
        self.assertNotEqual(self.classify(image), 'login')

    def test_password_edge_missing_is_not_login(self):
        image = self.login()
        ImageDraw.Draw(image).rectangle((479, 522, 748, 526), fill=(24, 28, 34))
        self.assertNotEqual(self.classify(image), 'login')

    def test_misaligned_edges_are_not_login(self):
        image = Image.new('RGB', (1280, 800), (24, 28, 34))
        draw = ImageDraw.Draw(image)
        draw.rectangle((752, 480, 795, 523), fill=vmtest.AMBER)
        draw.rectangle((492, 479, 735, 480), fill=vmtest.AMBER)
        draw.rectangle((442, 523, 685, 524), fill=vmtest.AMBER)
        self.assertNotEqual(self.classify(image), 'login')

    def test_amber_background_alone_is_not_login(self):
        self.assertNotEqual(self.classify(Image.new('RGB', (1280, 800), vmtest.AMBER)), 'login')

    def test_dark_and_missing_screens(self):
        self.assertEqual(self.classify(Image.new('RGB', (1280, 800))), 'dark')
        self.assertEqual(vmtest.classify(self.path.with_name('absent.png')), 'none')

    def test_password_roi_detects_bounded_bullet_change(self):
        before = self.login()
        after = before.copy()
        draw = ImageDraw.Draw(after)
        for x in (550, 565, 580):
            draw.ellipse((x, 496, x + 7, 503), fill=(235, 238, 242))
        self.assertTrue(self.password_changed(before, after))
        self.assertFalse(self.password_cleared(before, after))

    def test_identical_password_roi_is_rejected(self):
        before = self.login()
        self.assertFalse(self.password_changed(before, before.copy()))
        self.assertTrue(self.password_cleared(before, before.copy()))

    def test_change_outside_password_roi_is_rejected(self):
        before = self.login()
        after = before.copy()
        ImageDraw.Draw(after).rectangle((20, 20, 300, 100), fill=(255, 255, 255))
        self.assertFalse(self.password_changed(before, after))
        self.assertTrue(self.password_cleared(before, after))

    def test_password_change_requires_login_geometry_in_both_frames(self):
        before = self.login()
        after = before.copy()
        ImageDraw.Draw(after).rectangle((752, 480, 795, 523), fill=(24, 28, 34))
        self.assertFalse(self.password_changed(before, after))
        self.assertFalse(self.password_cleared(before, after))

    def test_password_target_is_inside_the_observed_field(self):
        image = self.login()
        image.save(self.path)
        x, y, width, height = vmtest.login_password_target(self.path)
        field, _ = vmtest._login_geometry(image)
        self.assertEqual((width, height), image.size)
        self.assertTrue(field[0] < x < field[2])
        self.assertTrue(field[1] < y < field[3])

    def test_password_target_requires_login_geometry(self):
        Image.new('RGB', (1280, 800), (24, 28, 34)).save(self.path)
        self.assertIsNone(vmtest.login_password_target(self.path))


if __name__ == '__main__':
    unittest.main()
