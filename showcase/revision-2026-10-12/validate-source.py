#!/usr/bin/env python3
"""Validate parity and fail-closed state for direct official VoxType showcase source."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REV = Path(__file__).resolve().parent
SHOWCASE = REV.parent
sys.path.insert(0, str(SHOWCASE))
from capture_contracts import PENDING, contracts_from_provenance  # noqa: E402
from voice_receipt import validate_assembled_master, validate_segment_plan  # noqa: E402


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root_story = load(SHOWCASE / "storyboard.json")
    revision_story = load(REV / "storyboard.json")
    scene_narration = load(REV / "scene-narration.json")
    caption_source = load(REV / "caption-text.json")
    caption_aligned = load(REV / "caption-text-aligned.json")
    root_timing = load(SHOWCASE / "timing.json")
    revision_timing = load(REV / "timing.json")
    voice = load(REV / "voice-timing.json")
    alignment = load(REV / "alignment-provenance.json")
    whisper = load(REV / "whisper-verification.json")
    validation = load(REV / "validation-source.json")
    provenance = load(SHOWCASE / "asset-provenance.json")

    ids = [scene["id"] for scene in root_story]
    assert len(ids) == len(set(ids)) == 38
    assert ids == [scene["id"] for scene in revision_story]
    assert ids == [scene["id"] for scene in scene_narration]
    assert ids == [scene["id"] for scene in root_timing["scenes"]]
    assert root_timing == revision_timing
    assert root_timing["render_ready"] is False
    assert root_timing["timing_status"] == "verified_direct_voxtype_river_alignment"

    root_by_id = {scene["id"]: scene for scene in root_story}
    revision_by_id = {scene["id"]: scene for scene in revision_story}
    for item in scene_narration:
        scene_id = item["id"]
        assert item["text"] == root_by_id[scene_id]["narration"]
        assert item["text"] == revision_by_id[scene_id]["narration"]

    source_cues = caption_source["cues"]
    aligned_cues = caption_aligned["cues"]
    timed_cues = root_timing["captions"]
    assert len(source_cues) == len(aligned_cues) == len(timed_cues) == 130
    source_text = [(cue["scene"], cue["sentence"], cue["text"]) for cue in source_cues]
    assert source_text == [(cue["scene"], cue["sentence"], cue["text"]) for cue in aligned_cues]
    assert source_text == [(cue["scene"], cue["sentence"], cue["text"]) for cue in timed_cues]
    assert caption_source["timing_status"] == "pending_direct_voxtype_river_alignment"
    assert caption_aligned["timing_status"] == "whisper_base_en_word_aligned"
    assert all(cue["start"] is None and cue["end"] is None for cue in source_cues)
    assert all(0.0 <= cue["start"] < cue["end"] for cue in aligned_cues)
    assert aligned_cues == timed_cues

    grouped: dict[str, list[str]] = defaultdict(list)
    for cue in source_cues:
        grouped[cue["scene"]].append(cue["text"])
    for scene_id in ids:
        assert " ".join(grouped[scene_id]) == root_by_id[scene_id]["narration"]

    # Every numeric slot comes from the pinned local word alignment.
    duration = root_timing["duration"]
    assert abs(duration - 582.356463) < 0.000001
    previous_end = 0.0
    for cue in timed_cues:
        assert 0.0 <= cue["start"] < cue["end"] <= duration
        assert cue["start"] >= previous_end
        previous_end = cue["end"]

    for name in ("captions.srt", "captions.vtt", "chapters.txt", "narration.txt"):
        assert digest(SHOWCASE / name) == digest(REV / name)

    required = {
        "signature-checked official VoxType 1.1.1 binaries": "dictationsetup",
        "arctic-dictation-toggle → voxtype record toggle": "dictationrecord",
        "Arctic's dictation pill follows VoxType's recording": "dictationrecord",
        "arctic-dictation set-backend vulkan|cpu": "dictationrecovery",
        "7.77 percent English word error": "dictationrecovery",
        "42.0 percent Hebrew word error": "dictationrecovery",
        "CPU result was not real time": "dictationrecovery",
        "Built-in wallpapers can be deleted from your view and restored later": "winter",
        "After each update, What's New shows the changes once": "updates",
    }
    source_files = (
        "storyboard.json", "narration.txt", "captions.srt", "captions.vtt", "timing.json", "index.html"
    )
    combined = "\n".join((SHOWCASE / name).read_text() for name in source_files)
    for phrase, scene_id in required.items():
        assert phrase in combined, phrase
        assert scene_id in ids

    banned = (
        "Arctic discards that recording and selects the CPU",
        "Dictation has its own setup queue",
        "Recording indicators remain visible",
        "Voxtype 0.5.1",
        "Mango invokes VoxType directly",
        "voxtype record start / stop",
        "VoxType's native indicator",
        "voxtype configure",
        "voxtype setup gpu",
    )
    for phrase in banned:
        assert phrase not in combined, phrase

    for scene_id in ("dictationsetup", "dictationrecord", "dictationrecovery", "winter", "updates"):
        scene = root_by_id[scene_id]
        assert scene["type"] == "evidence"
        assert scene["capture_required"] is True
        assert "image" not in scene and "source" not in scene
    for scene_id in ("dictationsetup", "dictationrecord", "dictationrecovery"):
        assert root_by_id[scene_id]["tag"] == "Qualified direct-VoxType ISO capture required"
    for scene_id in ("winter", "updates"):
        assert root_by_id[scene_id]["tag"] == "Final-image capture pending"
    contracts = contracts_from_provenance(provenance, SHOWCASE.parent)
    assert all(contract["status"] == PENDING for contract in contracts.values())
    assert all(
        contract["source"] is None and contract["sha256"] is None
        and contract["qualified_iso"] is None
        and contract["human_review"]["status"] == "pending"
        for contract in contracts.values()
    )
    assert not (SHOWCASE / "assets/dictation-recording-current.png").exists()
    assert not (SHOWCASE / "assets/dictation-recovery-gpu-failure-current.png").exists()
    assert not (SHOWCASE / "assets/dictation-recovery-cpu-ready-current.png").exists()

    ember = root_by_id["ember"]
    assert ember["source"] == "design/backgrounds/ember-clouds-city-silhouette.jpg"
    ember_master = SHOWCASE.parent / ember["source"]
    assert digest(ember_master) == "7af8cb5ce0d87773109d759afdd1d14ef22ce7e84fdc1533da1539083cd11b0b"

    assert voice["status"] == "direct_voxtype_1_1_1_master_aligned_capture_listening_pending"
    assert voice["ready_for_render"] is False
    assert voice["assembly"]["local_reference"]["status"] == "superseded_custom_controller_wording"
    assert voice["validation"]["local_speech_to_text_alignment"] == "passed_faster_whisper_1.2.1_base_en_word_alignment"
    assert voice["validation"]["transcript_leakage_review"] == "passed_automated_log_safety_ephemeral_transcript_not_uploaded"
    assert voice["validation"]["human_listening_review"] == {
        "status": "pending",
        "reviewer": None,
        "reviewed_at": None,
        "master_sha256": None,
        "scope": None,
    }
    assert voice["license"]["publication_confirmation"] == {
        "status": "pending",
        "confirmed_by": None,
        "confirmed_at": None,
        "scope": None,
    }
    assert voice["source_commit"] == "c9ac983c8d54aec109f0ebbbf3633d26b7cf8b9d"
    assert voice["source_archive"] == {
        "status": "verified_private_draft",
        "release_id": 413658818,
        "draft": True,
        "public": False,
        "target_commit": voice["source_commit"],
        "tag": "showcase-river-source-2026-10-15",
        "asset_id": 643686786,
        "asset": "narration-river-arctic-1.2.1-voxtype-1.1.1-2026-10-15.mp3",
        "bytes": 13_978_270,
        "rest_digest": "sha256:f6852132fed3f97e3b6a6b69fe4543e6af1a26c8495c9243e2cccfbde7c7081b",
        "download_sha256": "f6852132fed3f97e3b6a6b69fe4543e6af1a26c8495c9243e2cccfbde7c7081b",
        "full_decode_errors": 0,
    }
    assert voice["release_binding"] == {
        "status": "pending",
        "qualified_iso": None,
        "qualification_manifest": {
            "path": "tools/qualified-release/manifest.json",
            "sha256": None,
            "status": "pending",
        },
    }
    assert voice["generated_audio_binaries_committed"] is False
    assert voice["assembly"]["published"] is False
    assert voice["validation"]["final_render_verified"] is False
    assert voice["validation"]["final_render_review"] == {
        "status": "pending",
        "source_commit": None,
        "render": {
            "workflow_run": None,
            "source_commit": None,
            "artifact_id": None,
            "artifact_name": "Arctic-Linux-Showcase-River-1080p-candidate",
            "archive_bytes": None,
            "archive_sha256": None,
        },
        "video": {
            "name": "Arctic-Linux-Showcase-River-1080p.mp4",
            "bytes": None,
            "sha256": None,
            "duration_seconds": None,
        },
        "checks": {
            "full_decode_status": "pending",
            "subtitle_mux_status": "pending",
            "subtitle_codec": None,
            "subtitle_cues": None,
            "duration_matches_master": False,
        },
        "human_frame_review": {
            "status": "pending",
            "reviewer": None,
            "reviewed_at": None,
            "video_sha256": None,
            "frames": None,
        },
    }
    assert voice["validation"]["public_video_published"] is False
    segment_plan = validate_segment_plan(voice, SHOWCASE.parent)
    assert segment_plan["minimum_generation_calls"] == 2
    assert [item["characters"] for item in segment_plan["segments"]] == [4451, 4642]
    assert all(isinstance(item["generation"], dict) for item in segment_plan["segments"])
    assert voice["direct_voxtype_revision"]["failed_full_narration_attempt"]["renderable_audio"] is False
    master = validate_assembled_master(voice, SHOWCASE.parent)
    assert master == {
        "source_tag": "showcase-river-source-2026-10-15",
        "master_asset": "narration-river-arctic-1.2.1-voxtype-1.1.1-2026-10-15.mp3",
        "master_bytes": "13978270",
        "master_sha256": "f6852132fed3f97e3b6a6b69fe4543e6af1a26c8495c9243e2cccfbde7c7081b",
        "master_duration": "582.356463",
    }
    assert alignment["status"] == "verified_direct_voxtype_1_1_1_master_locally_aligned"
    assert alignment["determinism"] == {
        "runs": 2,
        "same_audio_sha256_each_run": True,
        "all_alignment_outputs_byte_identical": True,
        "network_during_transcription": False,
        "model_cache_mode": "offline",
    }
    assert alignment["audio"]["sha256"] == master["master_sha256"]
    assert alignment["audio"]["bytes"] == int(master["master_bytes"])
    assert alignment["audio"]["decoded_samples"] == 25_681_920
    assert alignment["log_privacy"]["transcript_in_ci_log"] is False
    assert alignment["log_privacy"]["transcript_outputs_public"] is False
    assert alignment["log_privacy"]["transcript_outputs_uploaded"] is False
    workflow_dir = SHOWCASE.parent / ".github/workflows"
    showcase_workflows = {
        path.name: path.read_text()
        for path in workflow_dir.glob("showcase-*.yml")
    }
    expected_showcase_workflows = {
        "showcase-exact-capture-20261014.yml",
        "showcase-river-render.yml",
        "showcase-river-verify.yml",
    }
    assert set(showcase_workflows) == expected_showcase_workflows
    verify_workflow = showcase_workflows["showcase-river-verify.yml"]
    render_workflow = showcase_workflows["showcase-river-render.yml"]
    upload_block = verify_workflow.split("- name: Upload alignment evidence", 1)[1]
    assert "whisper-transcript.txt" not in upload_block
    assert "whisper-words.json" not in upload_block
    assert verify_workflow.index("Pillow==11.3.0") < verify_workflow.index("--purpose private-render")
    assert render_workflow.index("Pillow==11.3.0") < render_workflow.index("--purpose private-render")
    assert "-map 0:s:0 -f srt" in render_workflow
    assert "assert len(source_cues) == len(muxed_cues) == 130" in render_workflow
    assert "assert muxed_cues == source_cues" in render_workflow
    package = load(SHOWCASE / "package.json")
    package_lock = load(SHOWCASE / "package-lock.json")
    assert package["devDependencies"] == {"hyperframes": "0.8.114"}
    assert all("npx" not in command for command in package["scripts"].values())
    assert digest(SHOWCASE / "package-lock.json") == "aea7f3a9d7a12d95b4a3d13f2f2d899762e6f66d1315d19c93ca368d6ecba50e"
    locked_hyperframes = package_lock["packages"]["node_modules/hyperframes"]
    assert locked_hyperframes["version"] == "0.8.114"
    assert locked_hyperframes["integrity"] == (
        "sha512-dIHdDQ//Wapovreuc0q2B+xLS5gbDUSles3ysXafkvxC4YXzZjc3NPvMqweEi5IZQDXefxZOJws5AgDByOiRAQ=="
    )
    assert "npm ci --ignore-scripts --no-audit --no-fund" in render_workflow
    assert digest(SHOWCASE / "assets/gsap.min.js") == "19e3ad578c9c583ddf9bdca2ad87bb55c3d70b331058e28abacab898f799b2ee"
    assert (SHOWCASE / "assets/gsap.min.js").stat().st_size == 72_777
    action_pins = {
        "checkout": ("34e114876b0b11c390a56381ad16ebd13914f8d5", "4.3.1"),
        "setup-python": ("a26af69be951a213d495a4c3e4e4022e16d87065", "5.6.0"),
        "setup-node": ("49933ea5288caeca8642d1e84afbd3f7d6820020", "4.4.0"),
        "upload-artifact": ("ea165f8d65b6e75b540449e92b4886f43607fa02", "4.6.2"),
    }
    combined_workflows = "\n".join(showcase_workflows.values())
    action_pattern = re.compile(
        r"uses:\s+actions/([a-z-]+)@([0-9a-f]{40})\s+#\s+v([0-9.]+)$",
        re.MULTILINE,
    )
    found_actions = {
        action: (commit, version)
        for action, commit, version in action_pattern.findall(combined_workflows)
    }
    assert found_actions == action_pins
    assert "actions/checkout@v" not in combined_workflows
    assert "actions/setup-python@v" not in combined_workflows
    assert "actions/setup-node@v" not in combined_workflows
    assert "actions/upload-artifact@v" not in combined_workflows
    assert validation["hyperframes_source_check"]["workflow_action_files"] == sorted(
        str(path.relative_to(SHOWCASE.parent))
        for path in workflow_dir.glob("showcase-*.yml")
    )
    execution_manifest_path = SHOWCASE / "capture/exact_image/execution-manifest.json"
    execution_manifest = load(execution_manifest_path)
    # A source-only video must stay fail closed until it is rebound to the
    # replacement qualified ISO.  In particular, do not retain stale image or
    # execution-file pins from the superseded candidate.
    assert execution_manifest["ready"] is False
    assert execution_manifest["image"] is None
    assert execution_manifest["execution_files"] == {}
    assert execution_manifest["release_acceptance"] is False
    execution_receipt = validation["exact_capture_execution_manifest"]
    assert execution_receipt == {
        "path": "showcase/capture/exact_image/execution-manifest.json",
        "sha256": digest(execution_manifest_path),
        "execution_files": 0,
        "all_hashes_recomputed": True,
    }
    supply = validation["hyperframes_source_check"]
    assert supply["package_lock"]["sha256"] == digest(SHOWCASE / "package-lock.json")
    assert supply["package_lock"]["registry_packages_require_sha512_integrity"] is True
    assert supply["gsap"]["sha256"] == digest(SHOWCASE / "assets/gsap.min.js")
    assert validation["validation_tests"]["supply_chain_unit_tests"] == 8
    assert validation["validation_tests"]["capture_and_voice_contract_unit_tests"] == 29
    assert validation["validation_tests"]["total_unit_tests"] == 37
    assert validation["local_whisper_alignment"]["ephemeral_outputs_not_uploaded"] == [
        "whisper-transcript.txt", "whisper-words.json"
    ]
    assert validation["workflow_privacy"] == {
        "transcript_in_ci_log": False,
        "transcript_outputs_uploaded": False,
        "uploaded_alignment_evidence_transcript_free": True,
        "resolver_runs_after_pinned_pillow_install": True,
    }
    admission = validation["voice_master_contract"]["admission_contract"]
    assert admission["qualification_manifest_path"] == "tools/qualified-release/manifest.json"
    assert admission["all_media_reviews_required"] is True
    assert admission["final_render_review_required"] == {
        "source_binding": [
            "source_commit", "workflow_run", "artifact_id", "artifact_name", "archive_bytes",
            "archive_sha256",
        ],
        "video_binding": ["name", "bytes", "sha256", "duration_seconds"],
        "automated_checks": [
            "full_decode_status", "subtitle_mux_status", "subtitle_codec", "subtitle_cues",
            "duration_matches_master",
        ],
        "human_review": "eight named representative frames bound to the exact MP4 SHA-256",
    }
    assert whisper["word_error_rate"] == 0.041412
    assert whisper["exact_token_coverage"] == 0.974202
    assert whisper["minimum_cue_exact_token_coverage"] >= 0.6
    assert whisper["cues_below_half_exact_token_coverage"] == 0
    assert whisper["cues_without_exact_tokens"] == 0
    assert whisper["explicit_cpu_recovery_phrase_token_coverage"] == 1.0
    assert whisper["local_privacy_phrase_token_coverage"] == 1.0
    assert whisper["transcript_in_ci_log"] is False
    objective = alignment["objective_audio_checks"]
    assert objective["full_ffmpeg_decode_errors"] == 0
    assert objective["hard_clipped_samples_ge_0_999"] == 0
    assert objective["join"]["join_contiguous_below_minus_60_dbfs_seconds"] >= 0.38
    assert objective["join"]["join_boundary_delta_fraction_of_window_max"] < 0.002

    result = {
        "status": "PASSED_DIRECT_VOXTYPE_ALIGNED_SOURCE_ONLY",
        "scenes": len(ids),
        "caption_cues": len(timed_cues),
        "aligned_duration_seconds": duration,
        "story_narration_caption_parity": True,
        "root_revision_timing_parity": True,
        "capture_contracts": len(contracts),
        "aligned_cue_times": len(aligned_cues),
        "alignment_runs": 2,
        "alignment_outputs_byte_identical": True,
        "word_error_rate": whisper["word_error_rate"],
        "exact_token_coverage": whisper["exact_token_coverage"],
        "human_listening_review": "pending",
        "narration_characters": 9093,
        "river_segment_characters": [4451, 4642],
        "river_generation_calls_pending": 0,
        "failed_full_narration_attempt_renderable": False,
        "new_river_master": True,
        "new_river_master_published": False,
        "new_river_master_sha256": master["master_sha256"],
        "new_river_master_duration_seconds": float(master["master_duration"]),
        "render_ready": False,
        "final_render_verified": False,
        "public_video_published": False,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
