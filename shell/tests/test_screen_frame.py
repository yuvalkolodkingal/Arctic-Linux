"""A broken private harness must never count as baseline defect reproduction."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[1] / 'dev/test-screen-frame.py'
spec = importlib.util.spec_from_file_location('frame_replay', SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class HarnessValidationTests(unittest.TestCase):
    def test_retained_native_pixels_sample_beyond_the_hairline(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/frame-inner-edge-native.json').read_text())
        for sample in fixture['samples']:
            points = replay.inner_frame_probe_points(sample['surface'], sample['surface']['devicePixelRatio'],
                                                      sample['frameWidth'], *sample['capture'])
            for point, edge in zip(points, ('right', 'bottom')):
                row = next(row for row in sample[edge] if (row['x'], row['y']) == point)
                self.assertEqual(row['rgb'], sample['ground'], sample['member'])

    def test_one_physical_pixel_of_frame_thinning_still_fails(self):
        fixture = json.loads((Path(__file__).parent / 'fixtures/frame-inner-edge-native.json').read_text())
        for sample in fixture['samples']:
            points = replay.inner_frame_probe_points(sample['surface'], sample['surface']['devicePixelRatio'],
                                                      sample['frameWidth'], *sample['capture'])
            for (x, y), edge in zip(points, ('right', 'bottom')):
                # Move the recorded inner boundary one physical pixel outwards.
                # This smaller shift than the reported one-logical-pixel defect
                # must still fail the unchanged native RGB tolerance.
                previous = (x - 1, y) if edge == 'right' else (x, y - 1)
                row = next(row for row in sample[edge] if (row['x'], row['y']) == previous)
                self.assertGreater(max(abs(a - b) for a, b in zip(row['rgb'], sample['ground'])), 3)

    def test_qml_error_cannot_be_reported_as_geometry_reproduction(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / 'shell.log'
            log.write_text('TypeError: Cannot read property width of undefined\n')
            with self.assertRaises(AssertionError) as raised:
                replay.validate_preview(Mock(poll=Mock(return_value=None)), log)
            self.assertNotIsInstance(raised.exception, replay.FrameGeometryError)

    def test_exited_preview_cannot_be_reported_as_geometry_reproduction(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / 'shell.log'
            log.write_text('preview stopped\n')
            with self.assertRaises(AssertionError) as raised:
                replay.validate_preview(Mock(poll=Mock(return_value=1)), log)
            self.assertNotIsInstance(raised.exception, replay.FrameGeometryError)


if __name__ == '__main__':
    unittest.main()
