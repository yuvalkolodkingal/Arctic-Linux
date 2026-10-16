import copy
import hashlib
import json
import os
import stat
import sys
import tempfile
import types
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from PIL import Image

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import contract as c
import dictation_bundle as db


class DictationEvidenceFixture:
    def build(self, root: Path):
        evidence = root / "evidence"
        evidence.mkdir(mode=0o700)
        fixtures = b'{"schema":"public-fixture"}\n'
        (evidence / "fixtures.json").write_bytes(fixtures)
        fixture_sha = hashlib.sha256(fixtures).hexdigest()
        installation = "1" * 32
        boot = "boot-online"

        def proof(path, nonce, **extra):
            request = {"boot_id": boot, "installation_id": installation,
                       "phase": "online-installed", "desktop_uid": 1000,
                       "receiver_empty": True, "capture_nonce": nonce, **extra}
            return {"request": request, "path": path, "sha256": None,
                    "iso_sha256": c.IMAGE["sha256"], "installation_id": installation}

        indicator = proof("dictation-indicator-online-installed.png", "a" * 32)
        gpu = proof("dictation-recovery-online-installed-gpu-failure.png", "b" * 32,
                    stage="gpu_failure", state="error", backend="cpu", language="he")
        cpu = proof("dictation-recovery-online-installed-cpu-ready.png", "c" * 32,
                    stage="cpu_ready", state="ready", backend="cpu", language="he")
        for index, name in enumerate(sorted((*db.INDICATORS, *db.RECOVERY)), 1):
            path = evidence / name
            Image.new("RGB", (1280, 800), (index * 20 % 255, 30, 40)).save(path)
            os.chmod(path, 0o600)
        for value in (indicator, gpu, cpu):
            value["sha256"] = c.sha256(evidence / value["path"])

        report = {
            "boot_id": boot,
            "context": {"installation_id": installation},
            "gates": [
                {"id": "recording-status-published", "status": "passed",
                 "observations": {"sha256": c.hashed("a" * 32)}},
                {"id": "gpu-failure-explicit-cpu-fallback", "status": "passed",
                 "observations": {"gpu_failure_capture_ack_sha256": c.hashed("b" * 32),
                                  "cpu_ready_capture_ack_sha256": c.hashed("c" * 32)}},
            ],
        }
        for name in db.REPORTS:
            (evidence / name).write_text(json.dumps(report) + "\n")
        state = {
            "schema": "arctic-voxtype-execution-v3", "hardware_profile": "turbo-q5-v3",
            "status": "exact_image_dictation_online_offline_local_sessions_passed",
            "release_acceptance": False, "image": copy.deepcopy(c.IMAGE),
            "execution_checker_head": "d" * 40,
            "fixture_manifest_sha256": fixture_sha,
            "reports": {"online-installed": {"path": "online-installed.json",
                                               "sha256": c.sha256(evidence / "online-installed.json")}},
            "indicators": {"online-installed": indicator},
            "recovery_screens": {"online-installed": {"gpu_failure": gpu, "cpu_ready": cpu}},
        }
        (evidence / "execution.json").write_text(json.dumps(state) + "\n")
        os.chmod(evidence / "execution.json", 0o600)
        for path in evidence.iterdir():
            os.chmod(path, 0o600)
        pin = {
            "schema": db.PIN_SCHEMA, "run_id": 123, "run_attempt": 1,
            "workflow": db.WORKFLOW, "branch": db.BRANCH, "source_sha": "d" * 40,
            "artifact_id": 456, "artifact_name": db.ARTIFACT_NAME,
            "archive_bytes": 1, "archive_sha256": "e" * 64,
            "hardware_profile": "turbo-q5-v3", "fixture_manifest_sha256": fixture_sha,
            "qualification_contract_sha256": db.QUALIFICATION_CONTRACT_SHA256,
            "image": copy.deepcopy(c.IMAGE),
        }
        return evidence, pin


class DictationEvidenceTests(unittest.TestCase, DictationEvidenceFixture):
    def test_metadata_requires_successful_first_attempt_exact_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            _evidence, pin = self.build(Path(temp))
            run = {"id": 123, "run_attempt": 1, "event": "push", "head_branch": db.BRANCH,
                   "head_sha": "d" * 40, "status": "completed", "conclusion": "success",
                   "path": db.WORKFLOW + "@refs/heads/" + db.BRANCH,
                   "repository": {"full_name": "yuvalkolodkingal/Arctic-Linux"}}
            artifact = {"id": 456, "name": db.ARTIFACT_NAME, "size_in_bytes": 1,
                        "digest": "sha256:" + "e" * 64, "expired": False,
                        "workflow_run": {"id": 123, "head_sha": "d" * 40}}
            db.verify_metadata(pin, run, artifact)
            self.assertEqual(c.sha256(HERE.parents[2] / "tools/dictation-qualification/contract.py"),
                             pin["qualification_contract_sha256"])
            for field, changed in (("conclusion", "failure"), ("run_attempt", 2),
                                   ("head_sha", "f" * 40)):
                altered = copy.deepcopy(run); altered[field] = changed
                with self.assertRaises(c.Invalid):
                    db.verify_metadata(pin, altered, artifact)

    def test_archive_extractor_rejects_extra_and_traversal_members(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence, pin = self.build(root)
            for suffix, extra in (("valid", None), ("extra", "unexpected.txt"),
                                  ("traversal", "../outside")):
                archive = root / (suffix + ".zip")
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as zipped:
                    for path in sorted(evidence.iterdir()):
                        zipped.write(path, path.name)
                    if extra:
                        zipped.writestr(extra, "bad")
                os.chmod(archive, 0o600)
                current = copy.deepcopy(pin)
                current["archive_bytes"] = archive.stat().st_size
                current["archive_sha256"] = c.sha256(archive)
                output = root / (suffix + "-out")
                if extra:
                    with self.assertRaises(c.Invalid):
                        db.extract_archive(current, archive, output)
                    self.assertFalse(output.exists())
                else:
                    db.extract_archive(current, archive, output)
                    self.assertEqual({path.name for path in output.iterdir()}, db.EVIDENCE_MEMBERS)

    def test_evidence_and_bundle_bind_three_frames_without_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            evidence, pin = self.build(root)
            validated = mock.Mock()
            qualification = types.SimpleNamespace(validate_execution=validated)
            with mock.patch.object(db, "_load_qualification_contract", return_value=qualification):
                _state, report, indicator, recovery = db.validate_evidence(pin, evidence, HERE.parents[2])
            validated.assert_called_once()
            self.assertEqual(report["boot_id"], "boot-online")
            self.assertEqual(indicator[1].name, "dictation-indicator-online-installed.png")
            self.assertNotEqual(recovery["gpu_failure"][0]["sha256"],
                                recovery["cpu_ready"][0]["sha256"])

            target = root / "bundle"
            archive = root / "bundle.tar"
            digest = root / "bundle.digest.json"
            with mock.patch.object(db, "_load_qualification_contract", return_value=qualification), \
                    mock.patch.object(db.bundle, "tesseract_ocr", return_value="clean"), \
                    mock.patch.object(db.bundle, "approved_ocr_identity",
                                      return_value=copy.deepcopy(c.OCR_IDENTITY)):
                manifest, contract = db.export(pin, evidence, HERE.parents[2], target,
                                               archive, digest)
            self.assertFalse(manifest["release_acceptance"])
            self.assertEqual(manifest["human_review"], "pending")
            self.assertEqual(set(manifest["scenes"]), set(c.DICTATION_EVIDENCE_SCENES))
            self.assertEqual({path.name for path in (target / "captures").iterdir()},
                             {"dictationrecord.png", "dictationrecovery-gpu-failure.png",
                              "dictationrecovery-cpu-ready.png"})
            self.assertEqual(contract["release_acceptance"], False)


if __name__ == "__main__":
    unittest.main()
