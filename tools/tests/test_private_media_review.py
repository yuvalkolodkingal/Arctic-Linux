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
from unittest.mock import patch
import zipfile

from PIL import Image, PngImagePlugin


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "private_media_review", ROOT / "tools/private-media-review/export.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
PUBLISH_SPEC = importlib.util.spec_from_file_location(
    "private_media_publish", ROOT / "tools/private-media-review/publish.py")
publisher = importlib.util.module_from_spec(PUBLISH_SPEC)
PUBLISH_SPEC.loader.exec_module(publisher)


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


def screened_bundle(root, value=None):
    value = value or manifest()
    output = root / "screened"; output.mkdir()
    raw = b"already-screened-png-bytes"
    asset_name = "installer-idle-desktop.png"
    (output / asset_name).write_bytes(raw)
    projection = [publisher.artifact_projection(item) for item in value["artifacts"]]
    record = {
        "artifact_id": value["artifacts"][0]["artifact_id"], "asset_name": asset_name,
        "bytes": len(raw), "height": 9, "kind": "png", "lane": "installer-idle",
        "member": "screened/desktop.png", "privacy_class": "screened-synthetic-vm-ui",
        "sha256": hashlib.sha256(raw).hexdigest(), "width": 16,
        "screening": ["producer-inventory-exact", "png-metadata-absent",
                      "ocr-sensitive-shapes-absent"],
    }
    review = {
        "schema": exporter.REVIEW_SCHEMA, "review_only": True, "release_acceptance": False,
        "human_review": "pending", "repository": exporter.REPOSITORY,
        "preparation_sha": "a" * 40, "activation_sha": "b" * 40,
        "draft_release": value["draft_release"], "artifacts": projection,
        "assets": [dict(sorted(record.items()))], "asset_count": 2, "png_count": 1,
        "png_bytes": len(raw),
        "privacy": {"audio_exported": False, "logs_exported": False,
                    "transcripts_exported": False, "raw_archives_exported": False},
    }
    (output / "REVIEW-MANIFEST.json").write_text(json.dumps(review, indent=2, sort_keys=True) + "\n")
    bundle = root / "screened.zip"; github_output = root / "github-output"
    digest = exporter.bundle_review(output, bundle, github_output)
    return bundle, digest, value


def forge_bundle(root, original, change):
    with zipfile.ZipFile(original) as archive:
        files = {info.filename: archive.read(info) for info in archive.infolist()}
    review = json.loads(files["REVIEW-MANIFEST.json"])
    change(files, review)
    files["REVIEW-MANIFEST.json"] = (json.dumps(review, indent=2, sort_keys=True) + "\n").encode()
    forged = root / "forged.zip"
    with zipfile.ZipFile(forged, "w", compression=zipfile.ZIP_STORED) as archive:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3; info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, raw)
    return forged, hashlib.sha256(forged.read_bytes()).hexdigest()


class ManifestControls(unittest.TestCase):
    def test_repository_manifest_pins_the_new_idle_and_active_installer_artifacts(self):
        value = exporter.strict_json((ROOT / exporter.MANIFEST).read_text())
        self.assertEqual(exporter.validate_manifest(value), value)
        self.assertEqual(len(value["artifacts"]), 2)
        item, active = value["artifacts"]
        self.assertEqual((item["run_id"], item["run_attempt"], item["artifact_id"]),
                         (38887504669, 1, 12040551529))
        self.assertEqual(item["head_sha"], "dc6e20313a48b2b2240518f0731f21e06aa18161")
        self.assertEqual((item["workflow_id"], item["workflow_path"]),
                         (380362453, ".github/workflows/installer-candidate-20261009.yml"))
        self.assertEqual((item["archive_bytes"], item["archive_sha256"]),
                         (998501, "d0ad8f3c13865227ea932add6659f56873773efa1e5dc58ea77c647cc9c00f5e"))
        self.assertEqual(len(item["archive_members"]), 29)
        self.assertEqual(len(item["exports"]), 12)
        self.assertEqual({entry["kind"] for entry in item["exports"]}, {"png"})
        self.assertEqual((active["run_id"], active["run_attempt"], active["artifact_id"]),
                         (38887511889, 1, 12040099765))
        self.assertEqual(active["head_sha"], "3b264391a2b57682863f876695633dffb5b6d587")
        self.assertEqual((active["archive_bytes"], active["archive_sha256"]),
                         (433134, "2aa001157b7d6180ec60e9b3b9f81fef88cba1eef6466263b6d4a30ad781aacf"))
        self.assertEqual((len(active["archive_members"]), len(active["exports"])), (27, 7))
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
        cursor = subprocess.CompletedProcess([], 0, stdout=b"Password: _\n", stderr=b"")
        with patch("subprocess.run", return_value=cursor):
            exporter.screen_png_ocr(raw, "eng+heb")
        entered = subprocess.CompletedProcess([], 0, stdout=b"Password: entered-value\n", stderr=b"")
        with patch("subprocess.run", return_value=entered), self.assertRaises(RuntimeError):
            exporter.screen_png_ocr(raw, "eng+heb")
        oversized = subprocess.CompletedProcess([], 0,
                                                stdout=b"x" * (exporter.BOUNDS["max_ocr_bytes"] + 1),
                                                stderr=b"")
        with patch("subprocess.run", return_value=oversized), self.assertRaises(RuntimeError):
            exporter.screen_png_ocr(raw, "eng+heb")

    def test_encrypted_and_high_expansion_zip_members_fail_closed(self):
        encrypted = zipfile.ZipInfo("diagnostic.log")
        encrypted.flag_bits = 1; encrypted.file_size = encrypted.compress_size = 10
        with self.assertRaises(RuntimeError):
            exporter.validate_zip_info(encrypted)
        expanded = zipfile.ZipInfo("diagnostic.log")
        expanded.file_size = 500_000; expanded.compress_size = 1
        expanded.compress_type = zipfile.ZIP_DEFLATED
        with self.assertRaises(RuntimeError):
            exporter.validate_zip_info(expanded)


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
        self.assertIn("screen:\n", text); self.assertIn("publish:\n", text)
        screen, publish = text.split("  publish:\n", 1)
        self.assertIn("actions: read", screen); self.assertIn("contents: read", screen)
        self.assertNotIn("contents: write", screen)
        self.assertIn("actions: read", publish); self.assertIn("contents: write", publish)
        self.assertNotIn("python3-pil", publish); self.assertNotIn("tesseract", publish)
        self.assertIn("persist-credentials: false", text)
        self.assertIn("tesseract-ocr-eng tesseract-ocr-heb", text)
        self.assertIn("bundle_sha256", text)
        self.assertIn("actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02", screen)
        self.assertIn("actions/download-artifact@d3f86a106a0bac45b974a628896c90dbdf5c8093", publish)
        self.assertIn("tools/private-media-review/publish.py", publish)
        publisher_source = (ROOT / "tools/private-media-review/publish.py").read_text()
        self.assertNotIn("from PIL", publisher_source)
        self.assertNotIn("tesseract", publisher_source)
        for forbidden in ("workflow_dispatch:", "gh release", "--force", "refs/heads/main",
                          "tools/build-iso.sh"):
            self.assertNotIn(forbidden, text)
        self.assertFalse((ROOT / exporter.MARKER).exists())

    def test_hash_bound_bundle_rejects_tampering_and_extracts_only_screened_assets(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); bundle, digest, value = screened_bundle(root)
            destination = root / "publish"
            records = publisher.unpack_bundle(bundle, digest, value, "a" * 40, "b" * 40,
                                               destination)
            self.assertEqual(set(records), {"installer-idle-desktop.png", "REVIEW-MANIFEST.json"})
            self.assertEqual(set(path.name for path in destination.iterdir()), set(records))
            with self.assertRaises(RuntimeError):
                publisher.unpack_bundle(bundle, "0" * 64, value, "a" * 40, "b" * 40,
                                        root / "tampered")

    def test_self_consistent_forged_bundle_cannot_expand_or_relabel_committed_exports(self):
        def extra_png(files, review):
            raw = b"forged-screened-png"
            record = copy.deepcopy(review["assets"][0])
            record.update(asset_name="unexpected-safe.png", bytes=len(raw),
                          sha256=hashlib.sha256(raw).hexdigest())
            files[record["asset_name"]] = raw
            review["assets"].append(record); review["asset_count"] += 1
            review["png_count"] += 1; review["png_bytes"] += len(raw)
        def extra_log(files, review):
            files["unexpected.log"] = b"self-consistent but undeclared"
        def change(field, value):
            return lambda files, review: review["assets"][0].__setitem__(field, value)
        cases = {
            "unexpected-png": extra_png, "unexpected-log": extra_log,
            "lane": change("lane", "installer-active"),
            "artifact": change("artifact_id", 999999),
            "member": change("member", "screened/other.png"),
            "dimensions": change("width", 17),
        }
        for name, mutation in cases.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary); original, _, value = screened_bundle(root)
                forged, digest = forge_bundle(root, original, mutation)
                with self.assertRaises(RuntimeError):
                    publisher.unpack_bundle(forged, digest, value, "a" * 40, "b" * 40,
                                            root / "publish")

    def test_structured_absence_rejects_non_404_and_preexisting_tag(self):
        with patch.object(publisher, "api_request", return_value=(403, b"{}")):
            with self.assertRaisesRegex(RuntimeError, "HTTP 403"):
                publisher.require_absent("endpoint", "Private review release")
        with patch.object(publisher, "api_request", return_value=(200, b"{}")):
            with self.assertRaisesRegex(RuntimeError, "release already exists"):
                publisher.require_absent("endpoint", "Private review release")
        with patch.object(publisher, "validate_activation",
                          return_value=(manifest(), "a" * 40, "b" * 40)), \
                patch.object(publisher, "api_request",
                             side_effect=[(404, b"{}"), (200, b"{}")]) as request:
            with self.assertRaisesRegex(RuntimeError, "tag already exists"):
                publisher.publish(Path("manifest"), Path("bundle"), "0" * 64)
            self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "GET"])
        with patch.object(publisher, "validate_activation",
                          return_value=(manifest(), "a" * 40, "b" * 40)), \
                patch.object(publisher, "api_request",
                             side_effect=[(404, b"{}"), (503, b"{}")]):
            with self.assertRaisesRegex(RuntimeError, "HTTP 503"):
                publisher.publish(Path("manifest"), Path("bundle"), "0" * 64)

    def test_failure_cleanup_deletes_and_verifies_new_release_and_tag(self):
        tag = manifest()["draft_release"]["tag"]
        responses = [(204, b""), (200, b"{}"), (204, b""), (404, b"{}"), (404, b"{}")]
        with patch.object(publisher, "api_request", side_effect=responses) as request:
            publisher.cleanup_created(42, tag, True)
        methods = [call.args[0] for call in request.call_args_list]
        self.assertEqual(methods, ["DELETE", "GET", "DELETE", "GET", "GET"])
        endpoints = [call.args[1] for call in request.call_args_list]
        self.assertIn("/releases/42", endpoints[0])
        self.assertIn("/git/refs/tags/", endpoints[2])

    def test_cleanup_attempts_tag_and_both_absence_checks_after_release_delete_error(self):
        tag = manifest()["draft_release"]["tag"]
        responses = [(500, b"{}"), (200, b"{}"), (204, b""), (404, b"{}"), (404, b"{}")]
        with patch.object(publisher, "api_request", side_effect=responses) as request, \
                self.assertRaisesRegex(RuntimeError, "release deletion returned HTTP 500"):
            publisher.cleanup_created(42, tag, True)
        self.assertEqual([call.args[0] for call in request.call_args_list],
                         ["DELETE", "GET", "DELETE", "GET", "GET"])

    def test_cleanup_never_deletes_an_unconfirmed_racing_tag(self):
        tag = manifest()["draft_release"]["tag"]
        with patch.object(publisher, "api_request",
                          side_effect=[(404, b"{}"), (200, b"{}")]) as request, \
                self.assertRaisesRegex(RuntimeError, "absence verification failed"):
            publisher.cleanup_created(None, tag, False)
        self.assertEqual([call.args[0] for call in request.call_args_list], ["GET", "GET"])

    def test_publish_failure_always_invokes_verified_cleanup(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); bundle, digest, value = screened_bundle(root)
            created_ref = {"ref": "refs/tags/" + value["draft_release"]["tag"]}
            with patch.object(publisher, "validate_activation",
                              return_value=(value, "a" * 40, "b" * 40)), \
                    patch.object(publisher, "require_absent"), \
                    patch.object(publisher, "resolve_tag"), \
                    patch.object(publisher, "api_json",
                                 side_effect=[created_ref, RuntimeError("release failed")]), \
                    patch.object(publisher, "recover_exact_draft", return_value=42), \
                    patch.object(publisher, "cleanup_created") as cleanup, \
                    self.assertRaisesRegex(RuntimeError, "release failed"):
                publisher.publish(Path("manifest"), bundle, digest)
            cleanup.assert_called_once_with(42, value["draft_release"]["tag"], True)

    def test_lost_create_response_recovers_only_the_exact_private_draft(self):
        value = manifest(); release = value["draft_release"]; tag = release["tag"]
        exact = {"id": 42, "draft": True, "prerelease": False, "tag_name": tag,
                 "name": release["name"], "body": publisher.DRAFT_BODY,
                 "target_commitish": "b" * 40}
        with patch.object(publisher, "api_request",
                          return_value=(200, json.dumps(exact).encode())), \
                patch.object(publisher, "resolve_tag") as resolve:
            self.assertEqual(publisher.recover_exact_draft(tag, release, "b" * 40), 42)
        resolve.assert_called_once_with(tag, "b" * 40)
        for field, changed in (("draft", False), ("name", "racing draft"),
                               ("body", "different"), ("target_commitish", "c" * 40)):
            hostile = exact | {field: changed}
            with self.subTest(field=field), patch.object(
                    publisher, "api_request", return_value=(200, json.dumps(hostile).encode())), \
                    self.assertRaisesRegex(RuntimeError, "nonidentical"):
                publisher.recover_exact_draft(tag, release, "b" * 40)

    def test_successful_publisher_creates_only_draft_and_verifies_uploaded_digests(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary); bundle, digest, value = screened_bundle(root)
            tag = value["draft_release"]["tag"]; uploaded = []
            def api(method, endpoint, status, **kwargs):
                self.assertIn(status, (200, 201))
                if endpoint.endswith("/git/refs"):
                    self.assertEqual(kwargs["payload"], {"ref": "refs/tags/" + tag,
                                                          "sha": "b" * 40})
                    return {"ref": "refs/tags/" + tag}
                if endpoint.endswith("/releases") and method == "POST":
                    self.assertIs(kwargs["payload"]["draft"], True)
                    self.assertIs(kwargs["payload"]["prerelease"], False)
                    return {"id": 42, "draft": True, "prerelease": False,
                            "tag_name": tag, "target_commitish": "b" * 40}
                if "uploads.github.com" in endpoint:
                    name = endpoint.split("name=", 1)[1]
                    raw = kwargs["raw"]
                    record = {"name": name, "size": len(raw),
                              "digest": "sha256:" + hashlib.sha256(raw).hexdigest()}
                    uploaded.append(record); return record
                if endpoint.endswith("/releases/42"):
                    return {"draft": True, "prerelease": False, "tag_name": tag,
                            "name": value["draft_release"]["name"],
                            "target_commitish": "b" * 40}
                if "/releases/42/assets?" in endpoint:
                    return uploaded
                self.fail("unexpected API endpoint " + endpoint)
            with patch.object(publisher, "validate_activation",
                              return_value=(value, "a" * 40, "b" * 40)), \
                    patch.object(publisher, "require_absent") as absent, \
                    patch.object(publisher, "resolve_tag") as resolve, \
                    patch.object(publisher, "api_json", side_effect=api), \
                    patch.object(publisher, "cleanup_created") as cleanup, \
                    patch("builtins.print"):
                publisher.publish(Path("manifest"), bundle, digest)
            self.assertEqual(absent.call_count, 2)
            self.assertEqual(resolve.call_count, 3)
            self.assertEqual(len(uploaded), 2)
            cleanup.assert_not_called()

    def test_tag_resolution_must_end_at_the_activation_commit(self):
        ref = {"object": {"type": "commit", "sha": "c" * 40}}
        with patch.object(publisher, "api_json", return_value=ref), \
                self.assertRaisesRegex(RuntimeError, "does not resolve"):
            publisher.resolve_tag("private-qualification-review-20261016", "b" * 40)


if __name__ == "__main__":
    unittest.main()
