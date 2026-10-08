"""A broken private harness must never count as baseline defect reproduction."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

SCRIPT = Path(__file__).resolve().parents[1] / 'dev/test-screen-frame.py'
spec = importlib.util.spec_from_file_location('frame_replay', SCRIPT)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


class HarnessValidationTests(unittest.TestCase):
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
