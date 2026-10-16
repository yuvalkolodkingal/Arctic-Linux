#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("showcase_failure_reader", HERE / "read.py")
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


class Contract:
    @staticmethod
    def capture_failure(value):
        assert value["schema"] == "arctic-showcase-capture-failure-v1"


def failure():
    return {
        "schema": "arctic-showcase-capture-failure-v1", "status": "failed",
        "release_acceptance": False, "image": {"private": "must-not-emit"},
        "host_phase": "capture-scenes", "failure_code": "guest-scene-failed",
        "guest_scene_stage": "dictationsetup", "guest_progress": [],
        "private_runtime_removed": True, "screens_exported": False,
        "logs_exported": False, "pixels_exported": False,
        "privacy": {"content": "private arbitrary content", "human_review": "not_applicable"},
        "live_startup": {"private": "startup details"},
        "installed_startup": {"private": "installed details"},
    }


def archive(extra=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(reader.MEMBER, json.dumps(failure(), sort_keys=True))
        if extra:
            bundle.writestr(extra, b"private transcript")
    return output.getvalue()


class SafeReaderTests(unittest.TestCase):
    def test_strict_json_rejects_duplicates_and_nonfinite(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff'):
            with self.subTest(raw=raw), self.assertRaisesRegex(RuntimeError, "rejected"):
                reader.strict_json(raw, 100)

    def test_projection_and_output_contain_only_closed_fields(self):
        projected = reader.safe_projection(failure(), Contract)
        self.assertEqual(projected["guest_scene_stage"], "dictationsetup")
        self.assertTrue(projected["installed_startup_present"])
        stream = io.StringIO()
        reader.emit(projected, stream)
        emitted = stream.getvalue()
        self.assertTrue(emitted.startswith("ARCTIC-SHOWCASE-SAFE-FAILURE "))
        for private in ("must-not-emit", "arbitrary content", "startup details",
                        "installed details", "schema", "image"):
            self.assertNotIn(private, emitted)

    def test_archive_requires_one_exact_regular_member(self):
        raw = archive(extra="private.log")
        with zipfile.ZipFile(io.BytesIO(raw)) as bundle:
            self.assertEqual(len(bundle.infolist()), 2)
        good = archive()
        with zipfile.ZipFile(io.BytesIO(good)) as bundle:
            items = bundle.infolist()
            self.assertEqual(len(items), 1)
            reader.safe_member(items[0])

    def test_inspect_pins_artifact_and_never_returns_raw_value(self):
        raw = archive()
        pin = dict(reader.ARTIFACT)
        pin.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        artifact = {"id": pin["id"], "name": pin["name"], "expired": False,
                    "size_in_bytes": pin["bytes"], "digest": "sha256:" + pin["sha256"],
                    "workflow_run": {"id": reader.RUN_ID, "head_sha": reader.SOURCE_SHA}}
        run = {"id": reader.RUN_ID, "run_attempt": 1, "head_sha": reader.SOURCE_SHA,
               "head_branch": reader.SOURCE_BRANCH, "path": reader.SOURCE_WORKFLOW,
               "event": "push", "status": "completed", "conclusion": "failure"}
        jobs = {"total_count": 1, "jobs": [{"name": "capture", "status": "completed",
            "conclusion": "failure", "steps": [
                {"name": "Install once and capture three host-screened exact-image scenes", "conclusion": "failure"},
                {"name": "Validate bounded privacy-safe failure projection", "conclusion": "success"},
                {"name": "Upload bounded showcase failure projection", "conclusion": "success"}]}]}

        def api(path):
            if path.startswith("/actions/artifacts/"):
                return artifact
            if "/jobs?" in path:
                return jobs
            return run

        def download(_artifact_id, target):
            target.write_bytes(raw)

        manifest = {"sentinel": True}
        with mock.patch.object(reader, "ARTIFACT", pin), \
                mock.patch.object(reader, "validate_manifest"), \
                mock.patch.object(reader, "load_contract", return_value=Contract):
            projected = reader.inspect(manifest, api, download)
        self.assertEqual(projected["failure_code"], "guest-scene-failed")
        self.assertNotIn("image", projected)

    def test_manifest_pins_reader_contract_workflow_and_exact_artifact(self):
        manifest = reader.read_json_file(HERE / "execution-manifest.json", 32_768)
        reader.validate_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
