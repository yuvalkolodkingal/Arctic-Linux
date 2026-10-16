"""Fail-closed controls for the private exact-qualification media exporter."""

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

from PIL import Image, PngImagePlugin


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "private_media_review", ROOT / "tools/private-media-review/export.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


def png(width=16, height=9, color=(22, 44, 66), metadata=False):
    output = io.BytesIO()
    info = None
    if metadata:
        info = PngImagePlugin.PngInfo(); info.add_text("Comment", "private")
    Image.new("RGB", (width, height), color).save(output, "PNG", pnginfo=info)
    return output.getvalue()


def artifact(raw=None):
    raw = raw or png()
    return {
        "lane": "installer-idle", "run_id": 123, "run_attempt": 1,
        "head_sha": "b" * 40, "head_branch": "codex/qualification-dispatch-20261010",
        "workflow_id": 456, "workflow_name": "Candidate installer restoration qualification",
        "workflow_path": ".github/workflows/installer-candidate-20261009.yml", "event": "push",
        "artifact_id": 789, "artifact_name": "candidate-installer-restoration",
        "archive_bytes": 100, "archive_sha256": "a" * 64,
        "screening_inventory": "upload-screening.json",
        "screening_scope": "Owned synthetic QEMU VM only; no host desktop, VM disks or credentials",
        "archive_members": ["screened/desktop.png", "diagnostic.log", "upload-screening.json"],
        "exports": [{
            "member": "screened/desktop.png", "asset_name": "installer-idle-desktop.png",
            "kind": "png", "privacy_class": "screened-synthetic-vm-ui",
            "max_bytes": len(raw) + 100, "width": 16, "height": 9,
            "ocr_languages": "eng+heb",
        }],
    }


def manifest(artifacts=None):
    return {
        "schema": exporter.SCHEMA, "ready": True, "review_only": True,
        "repository": exporter.REPOSITORY, "repository_id": exporter.REPOSITORY_ID,
        "source_branch": exporter.SOURCE_BRANCH, "bounds": copy.deepcopy(exporter.BOUNDS),
        "draft_release": {
            "tag": "private-qualification-review-20261016", "name": "Private review",
            "draft": True, "prerelease": False, "public": False,
            "human_review": "pending", "release_acceptance": False,
        },
        "artifacts": artifacts or [artifact()],
    }


class ManifestControls(unittest.TestCase):
    def test_repository_manifest_pins_only_the_new_idle_installer_artifact(self):
        value = exporter.strict_json((ROOT / exporter.MANIFEST).read_text())
        self.assertEqual(exporter.validate_manifest(value), value)
        self.assertEqual(len(value["artifacts"]), 1)
        item = value["artifacts"][0]
        self.assertEqual((item["run_id"], item["run_attempt"], item["artifact_id"]),
                         (38874179588, 1, 12033829931))
        self.assertEqual(item["head_sha"], "81f1fb2357f31e66200ced556ea56a4c253ef40f")
        self.assertEqual((item["workflow_id"], item["workflow_path"]),
                         (380362453, ".github/workflows/installer-candidate-20261009.yml"))
        self.assertEqual((item["archive_bytes"], item["archive_sha256"]),
                         (1001204, "06e44634f252c77ea7ba9eb07caf8d0fb62fc8d57c27ee87eedf8f08aac130a2"))
        self.assertEqual(len(item["archive_members"]), 29)
        self.assertEqual(len(item["exports"]), 12)
        self.assertEqual({entry["kind"] for entry in item["exports"]}, {"png"})
        self.assertFalse((ROOT / exporter.MARKER).exists())

    def test_private_pending_draft_fixed_bounds_and_allowlists_are_required(self):
        value = manifest()
        self.assertEqual(exporter.validate_manifest(value), value)
        cases = []
        bad = copy.deepcopy(value); bad["review_only"] = False; cases.append(bad)
        bad = copy.deepcopy(value); bad["bounds"]["max_exports"] += 1; cases.append(bad)
        bad = copy.deepcopy(value); bad["draft_release"]["draft"] = False; cases.append(bad)
        bad = copy.deepcopy(value); bad["draft_release"]["public"] = True; cases.append(bad)
        bad = copy.deepcopy(value); bad["draft_release"]["human_review"] = "passed"; cases.append(bad)
        bad = copy.deepcopy(value); bad["artifacts"][0]["workflow_path"] = ".github/workflows/ci.yml"; cases.append(bad)
        bad = copy.deepcopy(value); bad["artifacts"][0]["archive_sha256"] = "a" * 63; cases.append(bad)
        bad = copy.deepcopy(value); bad["artifacts"][0]["exports"][0]["kind"] = "wav"; cases.append(bad)
        bad = copy.deepcopy(value); bad["artifacts"][0]["exports"][0]["ocr_languages"] = "eng"; cases.append(bad)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                exporter.validate_manifest(case)

    def test_duplicate_lanes_assets_and_unsafe_members_fail_closed(self):
        first = artifact(); second = copy.deepcopy(first); second["artifact_id"] += 1
        with self.assertRaises(RuntimeError):
            exporter.validate_manifest(manifest([first, second]))
        for unsafe in ("../escape.png", "/absolute.png", "bad\\path.png", "file.exe"):
            value = manifest(); value["artifacts"][0]["archive_members"][0] = unsafe
            with self.subTest(unsafe=unsafe), self.assertRaises(RuntimeError):
                exporter.validate_manifest(value)


class RemoteIdentityControls(unittest.TestCase):
    def test_run_workflow_repository_and_artifact_must_match_every_pin(self):
        item = artifact()
        metadata = {
            "id": 789, "name": item["artifact_name"], "expired": False,
            "size_in_bytes": 100, "digest": "sha256:" + "a" * 64,
            "workflow_run": {"id": 123, "repository_id": exporter.REPOSITORY_ID,
                             "head_repository_id": exporter.REPOSITORY_ID,
                             "head_sha": "b" * 40, "head_branch": item["head_branch"]},
        }
        run = {
            "id": 123, "run_attempt": 1, "head_sha": "b" * 40,
            "head_branch": item["head_branch"], "workflow_id": 456,
            "name": item["workflow_name"], "path": item["workflow_path"], "event": "push",
            "status": "completed", "conclusion": "success",
            "repository": {"id": exporter.REPOSITORY_ID},
            "head_repository": {"id": exporter.REPOSITORY_ID},
        }
        exporter.verify_remote_identity(item, metadata, run)
        for field, value in (("workflow_id", 999), ("path", ".github/workflows/ci.yml"),
                             ("conclusion", "failure"), ("head_sha", "c" * 40)):
            changed = copy.deepcopy(run); changed[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                exporter.verify_remote_identity(item, metadata, changed)
        changed = copy.deepcopy(metadata); changed["digest"] = "sha256:" + "c" * 64
        with self.assertRaises(RuntimeError):
            exporter.verify_remote_identity(item, changed, run)


class ArchiveAndPrivacyControls(unittest.TestCase):
    def make_archive(self, root, raw=None, *, extra=None, mismatch=False, symlink=False):
        raw = raw or png()
        members = {"screened/desktop.png": raw, "diagnostic.log": b"bounded public diagnostics\n"}
        if extra:
            members[extra] = b"unexpected"
        inventory = {name: {
            "original_sha256": hashlib.sha256(content).hexdigest(),
            "uploaded_sha256": ("0" * 64 if mismatch and name == "screened/desktop.png"
                                else hashlib.sha256(content).hexdigest()),
            "bytes": len(content), "redactions": 0,
        } for name, content in members.items()}
        screening = json.dumps({"scope": artifact()["screening_scope"], "files": inventory}).encode()
        path = root / "artifact.zip"
        with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in members.items():
                if symlink and name == "screened/desktop.png":
                    info = zipfile.ZipInfo(name); info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                    archive.writestr(info, content)
                else:
                    archive.writestr(name, content)
            archive.writestr("upload-screening.json", screening)
        return path, raw

    def pinned(self, path, raw):
        item = artifact(raw)
        item["archive_bytes"] = path.stat().st_size
        item["archive_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        return item

    def test_exact_schema_complete_inventory_crc_and_only_declared_png_are_exported(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); archive, raw = self.make_archive(root)
            item = self.pinned(archive, raw); output = root / "out"; output.mkdir()
            with patch.object(exporter, "screen_png_ocr") as ocr:
                records, total = exporter.extract_artifact(item, archive, output)
            ocr.assert_called_once_with(raw, "eng+heb")
            self.assertEqual(total, len(raw))
            self.assertEqual([path.name for path in output.iterdir()], ["installer-idle-desktop.png"])
            self.assertEqual((output / "installer-idle-desktop.png").read_bytes(), raw)
            self.assertEqual(records[0]["human_review"] if "human_review" in records[0] else "pending",
                             "pending")
            self.assertEqual(records[0]["screening"],
                             ["producer-inventory-exact", "png-metadata-absent",
                              "ocr-sensitive-shapes-absent"])

    def test_extra_member_inventory_mismatch_and_symlink_are_rejected(self):
        for case in ("extra", "mismatch", "symlink"):
            with tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                archive, raw = self.make_archive(root, extra="extra.log" if case == "extra" else None,
                                                 mismatch=case == "mismatch", symlink=case == "symlink")
                item = self.pinned(archive, raw); output = root / "out"; output.mkdir()
                with self.subTest(case=case), patch.object(exporter, "screen_png_ocr"), \
                        self.assertRaises(RuntimeError):
                    exporter.extract_artifact(item, archive, output)

    def test_png_decoder_rejects_metadata_trailing_bytes_and_sensitive_ocr(self):
        raw = png()
        exporter.inspect_png(raw, 16, 9)
        for changed in (png(metadata=True), raw + b"trailing"):
            with self.subTest(size=len(changed)), self.assertRaises(RuntimeError):
                exporter.inspect_png(changed, 16, 9)
        completed = subprocess.CompletedProcess([], 0, stdout=b"token=private-secret\n", stderr=b"")
        with patch("subprocess.run", return_value=completed), self.assertRaises(RuntimeError):
            exporter.screen_png_ocr(raw, "eng+heb")


class ActivationAndWorkflowControls(unittest.TestCase):
    def test_activation_requires_marker_only_child_on_the_fixed_branch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(["git", "-C", str(root), "init", "-q"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.name", "test"], check=True)
            subprocess.run(["git", "-C", str(root), "config", "user.email", "test@example.invalid"], check=True)
            path = root / exporter.MANIFEST; path.parent.mkdir(parents=True)
            path.write_text(json.dumps(manifest()))
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "prepare"], check=True)
            preparation = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            marker = root / exporter.MARKER; marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(preparation + "\n")
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "activate"], check=True)
            activation = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
            event = root / "event.json"; (root / ".git/info/exclude").write_text("event.json\n")
            event.write_text(json.dumps({"before": preparation, "after": activation}))
            env = {"GITHUB_ACTIONS": "true", "RUNNER_ENVIRONMENT": "github-hosted",
                   "GITHUB_REPOSITORY": exporter.REPOSITORY,
                   "GITHUB_REF": "refs/heads/" + exporter.SOURCE_BRANCH,
                   "GITHUB_EVENT_NAME": "push", "GITHUB_RUN_ATTEMPT": "1",
                   "GITHUB_SHA": activation, "GITHUB_EVENT_PATH": str(event)}
            with patch.object(exporter, "ROOT", root), patch.dict(os.environ, env, clear=False):
                actual, parent, head = exporter.validate_activation(path)
            self.assertEqual((actual, parent, head), (manifest(), preparation, activation))

    def test_workflow_can_only_create_a_pending_draft_and_has_no_activation_marker(self):
        text = (ROOT / exporter.WORKFLOW).read_text()
        self.assertIn("branches: [codex/private-media-review-exporter-20261016]", text)
        self.assertIn("paths: [.github/private-media-review-export-20261016.activate]", text)
        self.assertIn("actions: read", text); self.assertIn("contents: write", text)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("tesseract-ocr-eng tesseract-ocr-heb", text)
        self.assertIn("publish-draft", text)
        for forbidden in ("workflow_dispatch:", "actions/upload-artifact", "gh release",
                          "--force", "refs/heads/main", "tools/build-iso.sh"):
            self.assertNotIn(forbidden, text)
        self.assertFalse((ROOT / exporter.MARKER).exists())

    def test_publisher_creates_and_rechecks_only_a_draft_with_exact_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            image = output / "installer-idle-desktop.png"; image.write_bytes(b"png-bytes")
            review = {
                "schema": exporter.REVIEW_SCHEMA, "preparation_sha": "a" * 40,
                "activation_sha": "b" * 40, "human_review": "pending",
                "release_acceptance": False,
                "assets": [{"asset_name": image.name, "bytes": image.stat().st_size,
                            "sha256": hashlib.sha256(image.read_bytes()).hexdigest()}],
            }
            review_path = output / "REVIEW-MANIFEST.json"
            review_path.write_text(json.dumps(review))
            expected = {
                image.name: (image.stat().st_size, hashlib.sha256(image.read_bytes()).hexdigest()),
                review_path.name: (review_path.stat().st_size,
                                   hashlib.sha256(review_path.read_bytes()).hexdigest()),
            }
            created = {"id": 42, "draft": True, "prerelease": False,
                       "tag_name": manifest()["draft_release"]["tag"],
                       "target_commitish": "b" * 40}
            uploads = [{"name": name, "size": size, "digest": "sha256:" + digest}
                       for name, (size, digest) in sorted(expected.items())]
            final = created | {"name": manifest()["draft_release"]["name"]}
            existing = Mock(returncode=1)
            gh_responses = [created, *uploads]
            fetched = [final, uploads]
            with patch.object(exporter, "validate_activation",
                              return_value=(manifest(), "a" * 40, "b" * 40)), \
                    patch.object(subprocess, "run", return_value=existing), \
                    patch.object(exporter, "gh_json", side_effect=gh_responses) as gh, \
                    patch.object(exporter, "fetch_json", side_effect=fetched):
                exporter.publish_draft(Path("unused"), output)
            create_payload = gh.call_args_list[0].args[1]
            self.assertIs(create_payload["draft"], True)
            self.assertIs(create_payload["prerelease"], False)
            self.assertEqual(create_payload["target_commitish"], "b" * 40)
            self.assertEqual(gh.call_count, 3)


if __name__ == "__main__":
    unittest.main()
