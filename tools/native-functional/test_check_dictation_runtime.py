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
            "voxtype-baseline", 18579224,
            "1c9d78b4f6805e4f12ba3670949d3c22788269bdbc54215afffa42cafd0b4a7a"))
        self.assertEqual(PROBE.PINS["turbo-q5-v3"]["binary"], (
            "voxtype-avx2", 19153728,
            "e7d5de68cc8fc610c3c961c47f879451db9bee4a2df152e9a66f1078072e7f28"))
        source = PATH.read_text()
        self.assertIn('/opt/arctic/voxtype/1.1.0', source)
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
