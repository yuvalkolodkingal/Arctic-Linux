import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
import wave


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("accuracy", HERE / "accuracy.py")
accuracy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(accuracy)


class ScoringTests(unittest.TestCase):
    def test_hebrew_marks_bidi_and_english_case_punctuation(self):
        self.assertEqual(accuracy.normalize("\u202bשָׁלוֹם, עוֹלָם!\u202c"), "שלום עולם")
        self.assertEqual(accuracy.normalize("DON’T; stop—now."), "dont stop now")
        self.assertEqual(accuracy.normalize("א׳ ך כ"), "א ך כ")
        self.assertEqual(accuracy.metrics("שָׁלוֹם עולם", "שלום עולם")["character_edits"], 0)

    def test_real_edit_counts_and_micro_average(self):
        first = accuracy.metrics("one two three", "one four")
        second = accuracy.metrics("שלום עולם", "שלום עולם נוסף")
        self.assertEqual(first["word_edits"], 2)
        self.assertEqual(second["word_edits"], 1)
        totals = accuracy.aggregate([first, second])
        self.assertEqual(totals["reference_words"], 5)
        self.assertEqual(totals["wer"], 3 / 5)
        self.assertEqual(accuracy.edit_distance("kitten", "sitting"), 3)
        self.assertEqual(accuracy.edit_distance("", "hello"), 5)
        self.assertEqual(accuracy.edit_distance("abc", ""), 3)
        with self.assertRaises(accuracy.Invalid):
            accuracy.metrics("!!", "one")

    def test_pinned_stdout_parser_rejects_logging_and_wrong_audio(self):
        raw = ('Loading audio file: "/private/en-00.wav"\n'
               'Audio format: 16000 Hz, 1 channel(s), Int\n'
               'Processing 16000 samples (1.00s)...\n\nשלום עולם\n')
        self.assertEqual(accuracy.parse_stdout(raw, 16000), "שלום עולם")
        for changed in ("INFO transcript excerpt\n" + raw, raw.replace("16000 samples", "15999 samples"),
                        raw.replace("שלום עולם", ""), raw.replace("Int", "Float")):
            with self.assertRaises(accuracy.Invalid):
                accuracy.parse_stdout(changed, 16000)


class ProvenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.samples = []
        for language in ("en", "he"):
            for row in range(5):
                name = f"{language}-{row:02d}"
                wav = self.root / (name + ".wav")
                with wave.open(str(wav), "wb") as stream:
                    stream.setnchannels(1)
                    stream.setsampwidth(2)
                    stream.setframerate(16000)
                    stream.writeframes(b"\0\0" * 16000)
                ref = self.root / (name + ".txt")
                ref.write_text("reference fixture")
                self.samples.append({"sample": name, "language": language, "source_row": row,
                    "wav": wav.name, "wav_bytes": wav.stat().st_size, "wav_sha256": accuracy.sha(wav),
                    "reference": ref.name, "reference_bytes": ref.stat().st_size,
                    "reference_sha256": accuracy.sha(ref), **accuracy.wav_metadata(wav)})

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self):
        path = self.root / "fixtures.json"
        path.write_text(json.dumps({"schema": "arctic-dictation-fixtures-v1",
                                   "dataset": accuracy.PINS["dataset"], "samples": self.samples}))
        return accuracy.sha(path)

    def test_tampering_hash_selection_and_escape_negative_controls(self):
        pinned = self.manifest()
        self.assertEqual(len(accuracy.load_fixtures(self.root, pinned)), 10)
        with self.assertRaisesRegex(accuracy.Invalid, "fixture-manifest-sha256"):
            accuracy.load_fixtures(self.root, "0" * 64)
        (self.root / self.samples[0]["reference"]).write_text("different fixture")
        with self.assertRaises(accuracy.Invalid):
            accuracy.load_fixtures(self.root, pinned)
        self.samples.reverse()
        with self.assertRaisesRegex(accuracy.Invalid, "fixture-selection"):
            accuracy.load_fixtures(self.root, self.manifest())
        with self.assertRaisesRegex(accuracy.Invalid, "fixture-path-escape"):
            accuracy.fixture_path(self.root, "../private.txt")
        (self.root / "symlink").symlink_to(self.root / self.samples[0]["wav"])
        with self.assertRaises(accuracy.Invalid):
            accuracy.fixture_path(self.root, "symlink")

    def test_private_permissions_and_partial_pin_mismatch(self):
        private = self.root / "private"
        accuracy.private_dir(private, fresh=True)
        accuracy.write_private(private / "text", b"private")
        self.assertEqual(private.stat().st_mode & 0o777, 0o700)
        self.assertEqual((private / "text").stat().st_mode & 0o777, 0o600)
        private.chmod(0o755)
        with self.assertRaisesRegex(accuracy.Invalid, "private-directory-permissions"):
            accuracy.private_dir(private)
        with self.assertRaises(accuracy.Invalid):
            accuracy.verify(private / "text", {"bytes": 7, "sha256": "0" * 64})

    def test_child_failure_and_stderr_are_never_forwarded(self):
        executable = self.root / "fail"
        executable.write_text("#!/bin/sh\nprintf 'SENSITIVE_TRANSCRIPT'\nprintf 'SENSITIVE_TRANSCRIPT' >&2\nexit 7\n")
        executable.chmod(0o700)
        output = accuracy.private_dir(self.root / "output", fresh=True)
        sample = self.samples[0]
        with self.assertRaisesRegex(accuracy.Invalid, "transcribe-process-failed") as failure:
            accuracy.run_transcription(executable, self.root / "model", sample, self.root, output, 2, 10)
        self.assertNotIn("SENSITIVE", str(failure.exception))
        self.assertEqual((output / "en-00.stdout.private").read_text(), "SENSITIVE_TRANSCRIPT")
        self.assertEqual((output / "en-00.stderr.private").stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
