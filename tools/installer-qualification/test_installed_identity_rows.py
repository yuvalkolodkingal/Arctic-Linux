"""Original-scale physical-row OCR; no VM qualification or private fixtures."""
import importlib.util
import io
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('identity_rows_driver', HERE / 'driver.py')
D = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(D)


class PhysicalRowControls(unittest.TestCase):
    nonce = '1234567890abcdef1234567890abcdef'

    def fixture(self, root, size=(1280, 720), mode='RGB'):
        path = root / 'console.png'
        image = Image.new(mode, size, 'black')
        draw = ImageDraw.Draw(image)
        for index, box in enumerate(D.IDENTITY_RECORD_BOXES):
            # Each physical row has a distinct marker cell and byte-identical
            # response cells after translation into the fixed row canvas.
            draw.rectangle((72, box[1] + 5, 79, box[1] + 14), fill=(index + 30, 50, 70))
            draw.rectangle((80, box[1] + 5, 230, box[1] + 14), fill=(30, 50, 70))
        # The next console prompt begins in the cell immediately below row3.
        draw.rectangle((64, 194, 240, 207), fill='white')
        image.save(path)
        return path, image

    def test_three_distinct_original_pixel_regions_and_no_resizing(self):
        expected = D.installed_user_records(self.nonce)
        with tempfile.TemporaryDirectory() as directory:
            path, image = self.fixture(Path(directory)); original = path.read_bytes(); calls = []
            def ocr(argv, **kwargs):
                index = len(calls); calls.append(argv)
                self.assertEqual(argv, ['tesseract', 'stdin', 'stdout', '-l', 'eng', '--psm', '7',
                                       '-c', 'tessedit_char_whitelist=0123456789'])
                with Image.open(io.BytesIO(kwargs['input'])) as row:
                    self.assertEqual(row.size, (176, 24)); self.assertEqual(row.mode, 'RGB')
                    wanted = Image.new('RGB', (176, 24), 'black')
                    wanted.paste(image.crop(D.IDENTITY_RECORD_BOXES[index]), (0, 0))
                    self.assertEqual(row.tobytes(), wanted.tobytes())
                    if index == 2:
                        self.assertEqual(row.crop((0, 20, 176, 24)).getbbox(), None)
                self.assertLessEqual(kwargs['timeout'], 10)
                return types.SimpleNamespace(stdout=(expected[index] + '\n').encode())
            with patch.object(D.subprocess, 'run', side_effect=ocr), \
                    patch.object(Image.Image, 'resize', side_effect=AssertionError('response pixels cannot be scaled')):
                stdout, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
            self.assertEqual(len(calls), 3); self.assertTrue(physical); self.assertTrue(identical)
            self.assertTrue(D._identity_ocr_observation(stdout, expected, True)[0])
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual({p.name for p in Path(directory).iterdir()}, {'console.png'})

    def test_swapped_physical_markers_are_not_replaced_by_a_text_only_consensus(self):
        expected = D.installed_user_records(self.nonce)
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory))
            outputs = [types.SimpleNamespace(stdout=expected[i].encode()) for i in (1, 0, 2)]
            with patch.object(D.subprocess, 'run', side_effect=outputs):
                stdout, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
            self.assertTrue(D._identity_ocr_observation(stdout, expected, True)[0])
            self.assertFalse(physical)
            self.assertTrue(identical)

    def test_empty_multiple_or_wrong_width_rows_withhold_physical_proof(self):
        expected = D.installed_user_records(self.nonce)
        for changed in (b'', expected[0].encode() + b'\n' + expected[0].encode(), expected[0][:-1].encode()):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                path, _ = self.fixture(Path(directory))
                outputs = [types.SimpleNamespace(stdout=x) for x in (changed, expected[1].encode(), expected[2].encode())]
                with patch.object(D.subprocess, 'run', side_effect=outputs):
                    _, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
                self.assertFalse(physical)
                self.assertTrue(identical)

    def test_one_exact_row_and_identical_response_pixels_survive_correlated_ocr_error(self):
        expected = D.installed_user_records(self.nonce)
        wrong = expected[0][1:7] + ('8' if expected[0][7] != '8' else '9') + expected[0][8:]
        outputs = [expected[0], expected[1][0] + wrong, expected[2][0] + wrong]
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory))
            with patch.object(D.subprocess, 'run', side_effect=[
                    types.SimpleNamespace(stdout=(value + '\n').encode()) for value in outputs]):
                stdout, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
        self.assertTrue(physical); self.assertTrue(identical)
        accepted, observation = D._identity_ocr_observation(
            stdout, expected, True, physical and identical)
        self.assertTrue(accepted)
        self.assertEqual(observation[2], 'one')

    def test_zero_exact_rows_never_pass_from_identical_pixels(self):
        expected = D.installed_user_records(self.nonce)
        position = 7
        replacement = '8' if expected[0][position] != '8' else '9'
        outputs = [record[:position] + replacement + record[position + 1:]
                   for record in expected]
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory))
            with patch.object(D.subprocess, 'run', side_effect=[
                    types.SimpleNamespace(stdout=(value + '\n').encode()) for value in outputs]):
                stdout, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
        self.assertTrue(physical); self.assertTrue(identical)
        accepted, observation = D._identity_ocr_observation(
            stdout, expected, True, physical and identical)
        self.assertFalse(accepted)
        self.assertEqual(observation[2], 'zero')

    def test_changed_response_pixels_disable_one_exact_row_fallback(self):
        expected = D.installed_user_records(self.nonce)
        wrong = expected[0][1:7] + ('8' if expected[0][7] != '8' else '9') + expected[0][8:]
        outputs = [expected[0], expected[1][0] + wrong, expected[2][0] + wrong]
        with tempfile.TemporaryDirectory() as directory:
            path, image = self.fixture(Path(directory))
            image.putpixel((100, D.IDENTITY_RECORD_BOXES[1][1] + 8), (255, 0, 0)); image.save(path)
            with patch.object(D.subprocess, 'run', side_effect=[
                    types.SimpleNamespace(stdout=(value + '\n').encode()) for value in outputs]):
                stdout, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
        self.assertTrue(physical); self.assertFalse(identical)
        self.assertFalse(D._identity_ocr_observation(
            stdout, expected, True, physical and identical)[0])

    def test_duplicate_and_swapped_markers_cannot_use_identical_pixels(self):
        expected = D.installed_user_records(self.nonce)
        cases = ([expected[0], expected[0], expected[2]],
                 [expected[1], expected[0], expected[2]])
        for outputs in cases:
            with self.subTest(outputs=outputs), tempfile.TemporaryDirectory() as directory:
                path, _ = self.fixture(Path(directory))
                with patch.object(D.subprocess, 'run', side_effect=[
                        types.SimpleNamespace(stdout=(value + '\n').encode()) for value in outputs]):
                    stdout, physical, identical = D.installed_identity_ocr(path, D.time.monotonic() + 30)
            self.assertFalse(physical); self.assertTrue(identical)
            accepted, _ = D._identity_ocr_observation(
                stdout, expected, True, physical and identical)
            # The production caller retains its mandatory per-position marker
            # conjunction for both the original OCR consensus and this proof.
            self.assertFalse(accepted and physical)

    def test_wrong_physical_dimensions_mode_and_format_deny_before_ocr(self):
        for size, mode, file_format in (((1280, 721), 'RGB', 'PNG'), ((1280, 720), 'RGBA', 'PNG'),
                                        ((1280, 720), 'RGB', 'JPEG')):
            with self.subTest(size=size, mode=mode, format=file_format), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'console.png'; Image.new(mode, size).save(path, format=file_format)
                with patch.object(D.subprocess, 'run') as ocr, self.assertRaises(RuntimeError):
                    D.installed_identity_ocr(path, D.time.monotonic() + 30)
                ocr.assert_not_called()

    def test_changed_original_during_ocr_withholds_all_proof(self):
        expected = D.installed_user_records(self.nonce)
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory)); calls = []
            def mutate(*_args, **_kwargs):
                index = len(calls); calls.append(index)
                if index == 0: Image.new('RGB', (1280, 720), 'red').save(path)
                return types.SimpleNamespace(stdout=expected[index].encode())
            with patch.object(D.subprocess, 'run', side_effect=mutate), self.assertRaisesRegex(RuntimeError, 'ownership differs'):
                D.installed_identity_ocr(path, D.time.monotonic() + 30)

    def test_deadline_and_ocr_bounds_are_not_extended(self):
        with tempfile.TemporaryDirectory() as directory:
            path, _ = self.fixture(Path(directory))
            with patch.object(D.time, 'monotonic', return_value=100), patch.object(D.subprocess, 'run') as ocr, \
                    self.assertRaisesRegex(RuntimeError, 'deadline exceeded'):
                D.installed_identity_ocr(path, 100)
            ocr.assert_not_called()
            with patch.object(D.subprocess, 'run', return_value=types.SimpleNamespace(stdout=b'x' * 65537)), \
                    self.assertRaisesRegex(RuntimeError, 'OCR exceeds bound'):
                D.installed_identity_ocr(path, D.time.monotonic() + 30)

    def test_cancellation_is_same_primary_and_creates_no_sidecar_or_crop_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); path, _ = self.fixture(root); error = KeyboardInterrupt('public cancellation fixture')
            with patch.object(D.subprocess, 'run', side_effect=error), self.assertRaises(KeyboardInterrupt) as caught:
                D.installed_identity_ocr(path, D.time.monotonic() + 30)
            self.assertIs(caught.exception, error)
            self.assertEqual({p.name for p in root.iterdir()}, {'console.png'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
