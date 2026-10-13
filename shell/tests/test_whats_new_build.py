import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "render_whats_new", ROOT / "tools" / "render-whats-new.py"
)
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


class WhatsNewBuildTests(unittest.TestCase):
    def render(self, update_id, source=None):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "whats-new.json"
            RENDERER.render(source or ROOT / "shell" / "whats-new.json", output, update_id)
            return output.read_bytes(), json.loads(output.read_text(encoding="utf-8"))

    def test_each_package_release_gets_a_distinct_runtime_id(self):
        first_bytes, first = self.render("arctic-1.2.1-1.202610130900.git1234567.fc44")
        second_bytes, second = self.render("arctic-1.2.1-1.202610131000.git7654321.fc44")

        self.assertNotEqual(first["update_id"], second["update_id"])
        self.assertNotEqual(first_bytes, second_bytes)
        self.assertEqual(first["items"], second["items"])
        self.assertEqual(first["schema"], 1)

    def test_source_id_is_a_required_build_placeholder(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "notes.json"
            notes = json.loads((ROOT / "shell" / "whats-new.json").read_text(encoding="utf-8"))
            notes["update_id"] = "forgotten-static-id"
            source.write_text(json.dumps(notes), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "source update_id"):
                self.render("arctic-1.2.1-1.fc44", source)

    def test_rejects_ids_the_runtime_will_not_accept(self):
        for update_id in ("", "has a space", "../path", "a" * 129):
            with self.subTest(update_id=update_id):
                with self.assertRaisesRegex(ValueError, "update id"):
                    self.render(update_id)

    def test_rejects_empty_or_insecure_notes(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "notes.json"
            for change in (
                {"items": []},
                {"items": [{"title": "", "text": "details"}]},
                {"notes_url": "http://example.org/notes"},
            ):
                notes = json.loads((ROOT / "shell" / "whats-new.json").read_text(encoding="utf-8"))
                notes.update(change)
                source.write_text(json.dumps(notes), encoding="utf-8")
                with self.subTest(change=change), self.assertRaises(ValueError):
                    self.render("arctic-1.2.1-1.fc44", source)


if __name__ == "__main__":
    unittest.main()
