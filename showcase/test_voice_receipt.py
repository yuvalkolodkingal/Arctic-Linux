import copy
import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from showcase.capture_contracts import CAPTURES, REVIEWED, pending_contract
SCRIPT = Path(__file__).resolve().parent / "revision-2026-10-12/resolve-voice.py"
SPEC = importlib.util.spec_from_file_location("resolve_voice", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)
RECEIPT = json.loads((SCRIPT.parent / "voice-timing.json").read_text())


def approved_receipt() -> dict:
    receipt = copy.deepcopy(RECEIPT)
    master = receipt["direct_voxtype_revision"]["new_master"]
    receipt["source_commit"] = "b" * 40
    receipt["source_branch"] = "codex/showcase-river-production"
    receipt["source_archive"] = {
        "status": "verified_private_draft",
        "release_id": 123,
        "draft": True,
        "public": False,
        "target_commit": receipt["source_commit"],
        "tag": master["draft_release_tag"],
        "asset_id": 456,
        "asset": master["asset"],
        "bytes": master["bytes"],
        "rest_digest": "sha256:" + master["sha256"],
        "download_sha256": master["sha256"],
        "full_decode_errors": 0,
    }
    receipt["license"]["publication_confirmation"] = {
        "status": "confirmed",
        "confirmed_by": "project publisher",
        "confirmed_at": "2026-10-14T12:00:00Z",
        "scope": "public_video",
    }
    receipt["validation"]["human_listening_review"] = {
        "status": "approved",
        "reviewer": "audio reviewer",
        "reviewed_at": "2026-10-14T12:10:00Z",
        "master_sha256": master["sha256"],
        "scope": "full_master_and_segment_join",
    }
    video_sha256 = "9" * 64
    render_source = "e" * 40
    receipt["validation"]["final_render_verified"] = True
    receipt["validation"]["final_render_review"] = {
        "status": "approved",
        "source_commit": render_source,
        "render": {
            "workflow_run": "https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/500",
            "source_commit": render_source,
            "artifact_id": 501,
            "artifact_name": "Arctic-Linux-Showcase-River-1080p-candidate",
            "archive_bytes": 80_000_000,
            "archive_sha256": "8" * 64,
        },
        "video": {
            "name": "Arctic-Linux-Showcase-River-1080p.mp4",
            "bytes": 75_000_000,
            "sha256": video_sha256,
            "duration_seconds": master["pyav_duration_seconds"],
        },
        "checks": {
            "full_decode_status": "passed",
            "subtitle_mux_status": "passed",
            "subtitle_codec": "mov_text",
            "subtitle_cues": 130,
            "duration_matches_master": True,
        },
        "human_frame_review": {
            "status": "approved",
            "reviewer": "video reviewer",
            "reviewed_at": "2026-10-14T12:30:00Z",
            "video_sha256": video_sha256,
            "frames": {
                "frame-intro.png": "1" * 64,
                "frame-files.png": "2" * 64,
                "frame-dictationsetup.png": "3" * 64,
                "frame-dictationrecord.png": "4" * 64,
                "frame-dictationrecovery.png": "5" * 64,
                "frame-winter.png": "6" * 64,
                "frame-updates.png": "7" * 64,
                "frame-outro.png": "a" * 64,
            },
        },
    }
    image = {
        "name": "Arctic-Linux-final-x86_64.iso",
        "bytes": 1_500_000_000,
        "sha256": "a" * 64,
        "source_commit": "c" * 40,
        "workflow_run": "https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/123",
    }
    receipt["release_binding"] = {
        "status": "qualified_release_manifest_bound",
        "qualified_iso": image,
        "qualification_manifest": {
            "path": "tools/qualified-release/manifest.json",
            "sha256": None,
            "status": "ready",
        },
    }
    receipt["direct_voxtype_revision"]["capture_evidence"] = "reviewed_qualified_direct_voxtype_iso"
    receipt["ready_for_render"] = True
    return receipt


class VoiceReceiptTest(unittest.TestCase):
    def ready_repository(self, receipt: dict) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        revision = root / "showcase/revision-2026-10-12"
        revision.mkdir(parents=True)
        source_root = SCRIPT.parents[2]
        for name in ("showcase/narration.txt",):
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source_root / name).read_bytes())
        for name in ("narration-river-segment-01.txt", "narration-river-segment-02.txt"):
            (revision / name).write_bytes((SCRIPT.parent / name).read_bytes())

        image = receipt["release_binding"]["qualified_iso"]
        # Start from the repository's real qualified-release schema so this
        # fixture cannot silently drift into a showcase-only manifest shape.
        manifest = json.loads((source_root / "tools/qualified-release/manifest.json").read_text())
        manifest.update({
            "ready": True,
            "release_acceptance": False,
            "publication_approved": True,
            "tag": "v1.2.1",
            "main_sha": "d" * 40,
            "image": {
                "name": image["name"], "bytes": image["bytes"], "sha256": image["sha256"],
                "source_sha": image["source_commit"], "run_id": 123, "artifact_id": 900,
            },
            "execution_files": {"tools/qualified-release/prepare.py": "f" * 64},
        })
        def pin(index: int) -> dict:
            return {
                "run_id": 200 + index,
                "source_sha": format(index + 1, "040x"),
                "artifact_id": 1000 + index,
                "archive_bytes": 10_000 + index,
                "archive_sha256": format(index + 1, "064x"),
            }
        manifest["performance"] = pin(1)
        manifest["native"] = pin(2)
        manifest["installer"] = pin(3)
        manifest["installer_active"] = pin(4)
        manifest["update"] = pin(5)
        manifest["reliability"] = {"uefi": pin(6), "bios": pin(7)}
        manifest["dictation"] = {"small-v2": pin(8), "turbo-q5-v3": pin(9)}
        def visual(pin_value: dict, archive_key: str, label: str) -> dict:
            return {
                "visual_status": "passed",
                "image_sha256": image["sha256"],
                archive_key: pin_value["archive_sha256"],
                "images": {label + ".png": hashlib.sha256(label.encode()).hexdigest()},
            }
        manifest["taskbar_media_review"] = visual(manifest["native"], "native_archive_sha256", "taskbar")
        manifest["media_review"] = {
            **visual(manifest["native"], "native_archive_sha256", "native"),
            "audio_status": "passed",
            "audio": {"native.wav": hashlib.sha256(b"native audio").hexdigest()},
        }
        manifest["dictation_media_review"] = {
            profile: visual(value, "dictation_archive_sha256", "dictation-" + profile)
            for profile, value in manifest["dictation"].items()
        }
        manifest["installer_media_review"] = visual(
            manifest["installer"], "installer_archive_sha256", "installer"
        )
        manifest["installer_active_media_review"] = visual(
            manifest["installer_active"], "installer_archive_sha256", "installer-active"
        )
        manifest_path = root / receipt["release_binding"]["qualification_manifest"]["path"]
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        receipt["release_binding"]["qualification_manifest"]["sha256"] = hashlib.sha256(
            manifest_path.read_bytes()
        ).hexdigest()

        provenance = []
        for index, scene in enumerate(CAPTURES):
            contract = pending_contract(scene)
            outputs = contract["output"]
            if isinstance(outputs, dict):
                sources = {}
                digests = {}
                for key, output_name in outputs.items():
                    output = root / output_name
                    output.parent.mkdir(parents=True, exist_ok=True)
                    Image.new("RGB", (1280, 800), (20 + index, 30, 40)).save(output)
                    sources[key] = f"qualification/{scene}-{key}.png"
                    digests[key] = hashlib.sha256(output.read_bytes()).hexdigest()
            else:
                output = root / outputs
                output.parent.mkdir(parents=True, exist_ok=True)
                Image.new("RGB", (1280, 800), (20 + index, 30, 40)).save(output)
                sources = f"qualification/{scene}.png"
                digests = hashlib.sha256(output.read_bytes()).hexdigest()
            contract.update({
                "status": REVIEWED,
                "source": sources,
                "sha256": digests,
                "qualified_iso": image,
                "human_review": {
                    "status": "approved",
                    "reviewer": "visual reviewer",
                    "reviewed_at": "2026-10-14T12:20:00Z",
                },
            })
            provenance.append({"scene": scene, "capture_contract": contract})
        (root / "showcase/asset-provenance.json").write_text(json.dumps(provenance) + "\n")

        timing = {
            "duration": receipt["direct_voxtype_revision"]["new_master"]["pyav_duration_seconds"],
            "render_ready": True,
        }
        (root / "showcase/timing.json").write_text(json.dumps(timing) + "\n")
        (revision / "timing.json").write_text(json.dumps(timing) + "\n")
        return root

    def test_current_receipt_stays_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "not ready"):
            MODULE.resolve(RECEIPT)

    def test_resolver_cli_exposes_separate_admission_modes(self):
        help_text = subprocess.check_output(["python3", str(SCRIPT), "--help"], text=True)
        self.assertIn("private-render", help_text)
        self.assertIn("publish-video", help_text)
        self.assertIn("publish-video-with-source-audio", help_text)

    def test_current_assembled_master_receipt_is_exact(self):
        values = MODULE.validate_assembled_master(RECEIPT)
        self.assertEqual(values["master_bytes"], "13978270")
        self.assertEqual(values["master_sha256"], "f6852132fed3f97e3b6a6b69fe4543e6af1a26c8495c9243e2cccfbde7c7081b")
        self.assertEqual(values["master_duration"], "582.356463")

    def test_current_private_draft_archive_receipt_is_exact(self):
        master = MODULE.validate_assembled_master(RECEIPT)
        MODULE.validate_source_archive(RECEIPT, master)

    def test_two_segments_reproduce_locked_narration_exactly(self):
        plan = MODULE.validate_segment_plan(RECEIPT)
        self.assertEqual(plan["minimum_generation_calls"], 2)
        self.assertEqual([item["characters"] for item in plan["segments"]], [4451, 4642])
        root = Path(__file__).resolve().parent.parent
        pieces = [(root / item["text_path"]).read_bytes() for item in plan["segments"]]
        self.assertEqual(b"".join(pieces), (root / "showcase/narration.txt").read_bytes())

    def test_bare_ready_boolean_cannot_unlock_current_receipt(self):
        receipt = copy.deepcopy(RECEIPT)
        receipt["ready_for_render"] = True
        with self.assertRaisesRegex(ValueError, "final image release manifest"):
            MODULE.resolve(receipt)

    def test_fully_bound_ready_receipt_exports_private_render_admission(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        values = MODULE.resolve(receipt, root)
        self.assertEqual(values["master_bytes"], "13978270")
        self.assertEqual(values["master_duration"], "582.356463")
        self.assertEqual(values["admission"], "private_render")

    def test_private_render_admits_pending_human_listening_for_candidate_review(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["validation"]["human_listening_review"] = copy.deepcopy(
            RECEIPT["validation"]["human_listening_review"]
        )
        self.assertEqual(MODULE.resolve(receipt, root)["admission"], "private_render")
        with self.assertRaisesRegex(ValueError, "human listening review"):
            MODULE.resolve_publication(receipt, root)

    def test_private_render_does_not_require_publication_confirmation(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["license"]["publication_confirmation"]["status"] = "pending"
        self.assertEqual(MODULE.resolve(receipt, root)["admission"], "private_render")

    def test_public_video_requires_publication_confirmation(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["license"]["publication_confirmation"]["status"] = "pending"
        with self.assertRaisesRegex(ValueError, "connected plan"):
            MODULE.resolve_publication(receipt, root)

    def test_publication_checks_private_render_review_before_plan_confirmation(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["license"]["publication_confirmation"] = copy.deepcopy(
            RECEIPT["license"]["publication_confirmation"]
        )
        receipt["validation"]["final_render_verified"] = False
        receipt["validation"]["final_render_review"] = copy.deepcopy(
            RECEIPT["validation"]["final_render_review"]
        )
        with self.assertRaisesRegex(ValueError, "final render is not verified"):
            MODULE.resolve_publication(receipt, root)

    def test_public_video_accepts_video_only_scope(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        values = MODULE.resolve_publication(receipt, root)
        self.assertEqual(values["publication_scope"], "public_video")
        self.assertEqual(values["source_audio_redistribution"], "false")

    def test_source_audio_redistribution_requires_broader_scope(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        with self.assertRaisesRegex(ValueError, "source-audio redistribution"):
            MODULE.resolve_publication(receipt, root, redistribute_source_audio=True)
        receipt["license"]["publication_confirmation"]["scope"] = (
            "public_video_and_source_audio_redistribution"
        )
        values = MODULE.resolve_publication(receipt, root, redistribute_source_audio=True)
        self.assertEqual(values["source_audio_redistribution"], "true")

    def test_publication_requires_release_publication_approval(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        binding = receipt["release_binding"]["qualification_manifest"]
        path = root / binding["path"]
        manifest = json.loads(path.read_text())
        manifest["publication_approved"] = False
        path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        self.assertEqual(MODULE.resolve(receipt, root)["admission"], "private_render")
        with self.assertRaisesRegex(ValueError, "release publication"):
            MODULE.resolve_publication(receipt, root)

    def test_publication_rejects_unverified_final_render(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["validation"]["final_render_verified"] = False
        receipt["validation"]["final_render_review"] = copy.deepcopy(
            RECEIPT["validation"]["final_render_review"]
        )
        with self.assertRaisesRegex(ValueError, "final render is not verified"):
            MODULE.resolve_publication(receipt, root)
        self.assertEqual(MODULE.resolve(receipt, root)["admission"], "private_render")

    def test_publication_rejects_frame_review_for_another_mp4(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["validation"]["final_render_review"]["human_frame_review"]["video_sha256"] = "b" * 64
        with self.assertRaisesRegex(ValueError, "exact final MP4"):
            MODULE.resolve_publication(receipt, root)

    def test_publication_rejects_render_run_from_another_source(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        receipt["validation"]["final_render_review"]["render"]["source_commit"] = "f" * 40
        with self.assertRaisesRegex(ValueError, "workflow artifact"):
            MODULE.resolve_publication(receipt, root)

    def test_ready_receipt_rejects_pending_capture(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        path = root / "showcase/asset-provenance.json"
        provenance = json.loads(path.read_text())
        provenance[0]["capture_contract"] = pending_contract(provenance[0]["scene"])
        path.write_text(json.dumps(provenance) + "\n")
        with self.assertRaisesRegex(ValueError, "all five qualified showcase captures"):
            MODULE.resolve(receipt, root)

    def test_ready_receipt_rejects_timing_that_remains_closed(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        timing = json.loads((root / "showcase/timing.json").read_text())
        timing["render_ready"] = False
        for path in (root / "showcase/timing.json", root / "showcase/revision-2026-10-12/timing.json"):
            path.write_text(json.dumps(timing) + "\n")
        with self.assertRaisesRegex(ValueError, "timing is not render-ready"):
            MODULE.resolve(receipt, root)

    def test_ready_receipt_rejects_missing_update_lane(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        binding = receipt["release_binding"]["qualification_manifest"]
        path = root / binding["path"]
        manifest = json.loads(path.read_text())
        manifest["update"] = None
        path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "qualification pin is missing: update"):
            MODULE.resolve(receipt, root)

    def test_ready_receipt_rejects_missing_active_installer_review(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        binding = receipt["release_binding"]["qualification_manifest"]
        path = root / binding["path"]
        manifest = json.loads(path.read_text())
        manifest["installer_active_media_review"] = None
        path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "media review is missing: installer_active"):
            MODULE.resolve(receipt, root)

    def test_ready_receipt_rejects_incomplete_native_media_review(self):
        receipt = approved_receipt()
        root = self.ready_repository(receipt)
        binding = receipt["release_binding"]["qualification_manifest"]
        path = root / binding["path"]
        manifest = json.loads(path.read_text())
        manifest["media_review"]["audio"] = {}
        path.write_text(json.dumps(manifest, sort_keys=True) + "\n")
        binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "native audio"):
            MODULE.resolve(receipt, root)

    def test_ready_receipt_rejects_unsafe_asset(self):
        receipt = approved_receipt()
        receipt["direct_voxtype_revision"]["new_master"]["asset"] = "../voice.mp3"
        with self.assertRaisesRegex(ValueError, "asset name"):
            MODULE.resolve(receipt)

    def test_ready_receipt_rejects_non_gapless_sample_count(self):
        receipt = approved_receipt()
        receipt["direct_voxtype_revision"]["new_master"]["decoded_samples"] += 1
        with self.assertRaisesRegex(ValueError, "gapless decoded-sample concatenation"):
            MODULE.resolve(receipt)

    def test_ready_receipt_rejects_segment_digest_binding_change(self):
        receipt = approved_receipt()
        receipt["direct_voxtype_revision"]["new_master"]["segment_audio_sha256s"].reverse()
        with self.assertRaisesRegex(ValueError, "segment digest binding"):
            MODULE.resolve(receipt)


if __name__ == "__main__":
    unittest.main()
