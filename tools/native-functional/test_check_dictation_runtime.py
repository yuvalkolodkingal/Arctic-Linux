"""Source controls for the supplemental direct upstream runtime probe."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


PATH = Path(__file__).with_name("check-dictation-runtime.py")
SPEC = importlib.util.spec_from_file_location("check_direct_voxtype_runtime", PATH)
PROBE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)


class DirectRuntimeProbeControls(unittest.TestCase):
    def test_exact_official_pins_and_split_production_paths(self):
        self.assertEqual(PROBE.PINS["small-v2"]["binary"], (
            "voxtype-baseline", 18838904,
            "cc051aac0870e21d7378edbcde3ceff10238af12a11650ab897d0ad9195225af"))
        self.assertEqual(PROBE.PINS["turbo-q5-v3"]["binary"], (
            "voxtype-avx2", 19415936,
            "3462262980e5a75391ffdeb7d3b63f9f638d6261df042f04f9119dfb7aab7770"))
        source = PATH.read_text()
        self.assertIn('/opt/arctic/voxtype/1.1.1', source)
        self.assertIn('/opt/arctic/voxtype/models', source)
        self.assertNotIn('dictation.py', source)
        self.assertNotIn('child_exec.py', source)
        self.assertNotIn('Broker(', source)

    def test_probe_config_is_local_multilingual_private_and_wtype_only(self):
        config = PROBE.config_text(Path('/opt/arctic/voxtype/models/ggml-small.bin'))
        for expected in ('mode = "local"', 'language = ["he", "en"]',
                         'driver_order = ["wtype"]', 'fallback_to_clipboard = false',
                         'on_transcription = false', 'enabled = false'):
            self.assertIn(expected, config)
        self.assertNotIn('remote', config)

    def test_verification_rejects_wrong_name_size_hash_and_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'voxtype-test'
            path.write_bytes(b'official fixture')
            pin = (path.name, path.stat().st_size, PROBE.sha256(path))
            PROBE.verify_file(path, pin)
            for changed in (("wrong", pin[1], pin[2]),
                            (pin[0], pin[1] + 1, pin[2]),
                            (pin[0], pin[1], "0" * 64)):
                with self.assertRaises(SystemExit):
                    PROBE.verify_file(path, changed)
            path.chmod(0o600)
            with self.assertRaises(SystemExit):
                PROBE.verify_file(path, pin, executable=True)
            path.chmod(0o700)
            PROBE.verify_file(path, pin, executable=True)


if __name__ == "__main__":
    unittest.main()
