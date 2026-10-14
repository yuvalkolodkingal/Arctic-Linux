"""Validation for the immutable segmented River narration receipt."""
from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path

HEX64 = re.compile(r"[0-9a-f]{64}")
HEX40 = re.compile(r"[0-9a-f]{40}")
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.mp3")
SAFE_VIDEO_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,126}\.mp4")
SAFE_TAG = re.compile(r"showcase-river-source-20[0-9]{2}-[01][0-9]-[0-3][0-9]")
SAFE_ID = re.compile(r"[A-Za-z0-9_-]{10,128}")
UTC = re.compile(r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z")
HTTPS_RUN = re.compile(
    r"https://github\.com/yuvalkolodkingal/Arctic-Linux/actions/runs/[1-9][0-9]*"
)
REPOSITORY = Path(__file__).resolve().parent.parent
ASSEMBLY_SAMPLE_RATE = 44_100
QUALIFICATION_MANIFEST_KEYS = {
    "ready", "release_acceptance", "publication_approved", "tag", "main_sha", "image",
    "performance", "reliability", "native", "taskbar_media_review", "dictation",
    "dictation_media_review", "installer", "installer_media_review", "installer_active",
    "installer_active_media_review", "update", "media_review", "execution_files",
}


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_segment_plan(receipt: dict, repository: Path = REPOSITORY) -> dict:
    """Validate that the bounded inputs reproduce the locked narration exactly."""
    revision = receipt.get("direct_voxtype_revision")
    if not isinstance(revision, dict):
        raise ValueError("direct-VoxType revision receipt is missing")
    attempt = revision.get("failed_full_narration_attempt")
    expected_attempt = {
        "flow_id": "Cy4mMtnohtJes0X2nAN9",
        "node_id": "89XLWvL8r6Kw473qr1C0",
        "session_id": "1i3Rl0dfqyey9flZ6U8A",
        "generation_id": "ifJ58S7jcPIhtJ62UNfy",
        "requested_characters": 9093,
        "connector_limit_characters": 5000,
        "outcome": "failed_input_too_long",
        "renderable_audio": False,
    }
    if attempt != expected_attempt:
        raise ValueError("failed full-narration attempt evidence differs")

    plan = revision.get("segmented_generation")
    if not isinstance(plan, dict):
        raise ValueError("segmented River generation plan is missing")
    limit = plan.get("connector_limit_characters")
    if limit != 5000:
        raise ValueError("River connector character limit differs")

    source = plan.get("locked_narration")
    if not isinstance(source, dict):
        raise ValueError("locked narration receipt is missing")
    source_path = repository / source.get("path", "")
    try:
        source_bytes = source_path.read_bytes()
        source_text = source_bytes.decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise ValueError("locked narration cannot be read as UTF-8") from error
    if source.get("characters") != len(source_text):
        raise ValueError("locked narration character count differs")
    if source.get("bytes") != len(source_bytes):
        raise ValueError("locked narration byte size differs")
    if source.get("sha256") != _digest(source_bytes):
        raise ValueError("locked narration digest differs")

    segments = plan.get("segments")
    if not isinstance(segments, list) or not segments:
        raise ValueError("River narration segments are missing")
    minimum = math.ceil(len(source_text) / limit)
    if plan.get("minimum_generation_calls") != minimum or len(segments) != minimum:
        raise ValueError("River narration is not split into the minimum number of calls")

    combined = bytearray()
    for index, segment in enumerate(segments, start=1):
        if not isinstance(segment, dict) or segment.get("index") != index:
            raise ValueError("River segment order differs")
        path = repository / segment.get("text_path", "")
        try:
            payload = path.read_bytes()
            text = payload.decode("utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise ValueError(f"River segment {index} cannot be read as UTF-8") from error
        if not text or len(text) > limit:
            raise ValueError(f"River segment {index} exceeds the connector limit")
        if segment.get("characters") != len(text) or segment.get("bytes") != len(payload):
            raise ValueError(f"River segment {index} size differs")
        if segment.get("sha256") != _digest(payload):
            raise ValueError(f"River segment {index} digest differs")
        if not isinstance(segment.get("first_scene"), str) or not isinstance(segment.get("last_scene"), str):
            raise ValueError(f"River segment {index} scene boundary is missing")
        combined.extend(payload)
    if bytes(combined) != source_bytes:
        raise ValueError("River segments do not reproduce the locked narration byte for byte")
    return plan


def _generation(segment: dict, index: int) -> dict:
    generation = segment.get("generation")
    if not isinstance(generation, dict):
        raise ValueError(f"River segment {index} generation is pending")
    required = {
        "flow_id", "node_id", "session_id", "generation_id", "asset", "bytes", "sha256",
        "reported_duration_seconds", "pyav_duration_seconds", "decoded_samples",
    }
    if set(generation) != required:
        raise ValueError(f"River segment {index} generation receipt fields differ")
    for key in ("flow_id", "node_id", "session_id", "generation_id"):
        if not isinstance(generation[key], str) or not SAFE_ID.fullmatch(generation[key]):
            raise ValueError(f"River segment {index} {key} is invalid")
    if not isinstance(generation["asset"], str) or not SAFE_NAME.fullmatch(generation["asset"]):
        raise ValueError(f"River segment {index} asset name is invalid")
    if not isinstance(generation["bytes"], int) or not 100_000 < generation["bytes"] < 100_000_000:
        raise ValueError(f"River segment {index} byte size is invalid")
    if not isinstance(generation["sha256"], str) or not HEX64.fullmatch(generation["sha256"]):
        raise ValueError(f"River segment {index} digest is invalid")
    for key in ("reported_duration_seconds", "pyav_duration_seconds"):
        if not isinstance(generation[key], (int, float)) or not 60 < generation[key] < 600:
            raise ValueError(f"River segment {index} duration is invalid")
    if abs(generation["reported_duration_seconds"] - generation["pyav_duration_seconds"]) > 1.0:
        raise ValueError(f"River segment {index} provider and PyAV durations differ")
    if not isinstance(generation["decoded_samples"], int) or generation["decoded_samples"] <= 0:
        raise ValueError(f"River segment {index} decoded sample count is invalid")
    decoded_duration = generation["decoded_samples"] / ASSEMBLY_SAMPLE_RATE
    if abs(decoded_duration - generation["pyav_duration_seconds"]) > 0.25:
        raise ValueError(f"River segment {index} duration and decoded sample count differ")
    return generation


def validate_assembled_master(receipt: dict, repository: Path = REPOSITORY) -> dict[str, str]:
    """Validate both generated segments and their sample-exact assembled master receipt."""
    plan = validate_segment_plan(receipt, repository)
    generations = [_generation(segment, index) for index, segment in enumerate(plan["segments"], 1)]
    master = receipt.get("direct_voxtype_revision", {}).get("new_master")
    required = {
        "draft_release_tag", "asset", "bytes", "sha256", "pyav_duration_seconds",
        "decoded_sample_rate_hz", "decoded_channels", "decoded_samples", "segment_audio_sha256s",
    }
    if not isinstance(master, dict) or set(master) != required:
        raise ValueError("assembled River master receipt fields differ")
    tag, asset = master["draft_release_tag"], master["asset"]
    if not isinstance(tag, str) or not SAFE_TAG.fullmatch(tag):
        raise ValueError("assembled River master tag is invalid")
    if not isinstance(asset, str) or not SAFE_NAME.fullmatch(asset):
        raise ValueError("assembled River master asset name is invalid")
    if not isinstance(master["bytes"], int) or not 1_000_000 < master["bytes"] < 100_000_000:
        raise ValueError("assembled River master byte size is invalid")
    if not isinstance(master["sha256"], str) or not HEX64.fullmatch(master["sha256"]):
        raise ValueError("assembled River master digest is invalid")
    duration = master["pyav_duration_seconds"]
    if not isinstance(duration, (int, float)) or not 300 < duration < 900:
        raise ValueError("assembled River master duration is invalid")
    if master["decoded_sample_rate_hz"] != ASSEMBLY_SAMPLE_RATE or master["decoded_channels"] != 1:
        raise ValueError("assembled River master PCM format differs")
    if master["segment_audio_sha256s"] != [item["sha256"] for item in generations]:
        raise ValueError("assembled River master segment digest binding differs")
    expected_samples = sum(item["decoded_samples"] for item in generations)
    if master["decoded_samples"] != expected_samples:
        raise ValueError("assembled River master is not a gapless decoded-sample concatenation")
    if abs(master["decoded_samples"] / ASSEMBLY_SAMPLE_RATE - duration) > 0.25:
        raise ValueError("assembled River master duration and decoded sample count differ")
    return {
        "source_tag": tag,
        "master_asset": asset,
        "master_bytes": str(master["bytes"]),
        "master_sha256": master["sha256"],
        "master_duration": f"{duration:.6f}",
    }


def _regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _safe_relative(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and ".." not in Path(value).parts
    )


def _qualified_iso(value: object) -> dict:
    keys = {"name", "bytes", "sha256", "source_commit", "workflow_run"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("qualified ISO receipt fields differ")
    if not isinstance(value["name"], str) or not value["name"].endswith(".iso"):
        raise ValueError("qualified ISO name is invalid")
    if not isinstance(value["bytes"], int) or not 0 < value["bytes"] < 2_000_000_000:
        raise ValueError("qualified ISO size is invalid")
    if not isinstance(value["sha256"], str) or not HEX64.fullmatch(value["sha256"]):
        raise ValueError("qualified ISO digest is invalid")
    if not isinstance(value["source_commit"], str) or not HEX40.fullmatch(value["source_commit"]):
        raise ValueError("qualified ISO source commit is invalid")
    if not isinstance(value["workflow_run"], str) or not HTTPS_RUN.fullmatch(value["workflow_run"]):
        raise ValueError("qualified ISO workflow run is invalid")
    return value


def _validate_source_archive(receipt: dict, master: dict[str, str]) -> None:
    archive = receipt.get("source_archive")
    keys = {
        "status", "release_id", "draft", "public", "target_commit", "tag",
        "asset_id", "asset", "bytes", "rest_digest", "download_sha256",
        "full_decode_errors",
    }
    if not isinstance(archive, dict) or set(archive) != keys:
        raise ValueError("private source archive receipt fields differ")
    source_commit = receipt.get("source_commit")
    if not isinstance(source_commit, str) or not HEX40.fullmatch(source_commit):
        raise ValueError("immutable source preparation commit is missing")
    if receipt.get("source_branch") != "codex/showcase-river-production":
        raise ValueError("trusted River production branch is not bound")
    if (
        archive["status"] != "verified_private_draft"
        or not isinstance(archive["release_id"], int)
        or archive["release_id"] <= 0
        or archive["draft"] is not True
        or archive["public"] is not False
        or archive["target_commit"] != source_commit
        or archive["tag"] != master["source_tag"]
        or not isinstance(archive["asset_id"], int)
        or archive["asset_id"] <= 0
        or archive["asset"] != master["master_asset"]
        or archive["bytes"] != int(master["master_bytes"])
        or archive["rest_digest"] != "sha256:" + master["master_sha256"]
        or archive["download_sha256"] != master["master_sha256"]
        or archive["full_decode_errors"] != 0
    ):
        raise ValueError("private source archive is not verified against the River master")


def _validate_publication_confirmation(receipt: dict, redistribute_source_audio: bool) -> str:
    confirmation = receipt.get("license", {}).get("publication_confirmation")
    keys = {"status", "confirmed_by", "confirmed_at", "scope"}
    if not isinstance(confirmation, dict) or set(confirmation) != keys:
        raise ValueError("publisher plan confirmation fields differ")
    if (
        confirmation["status"] != "confirmed"
        or not isinstance(confirmation["confirmed_by"], str)
        or not confirmation["confirmed_by"].strip()
        or not isinstance(confirmation["confirmed_at"], str)
        or not UTC.fullmatch(confirmation["confirmed_at"])
        or confirmation["scope"] not in {"public_video", "public_video_and_source_audio_redistribution"}
    ):
        raise ValueError("publisher has not confirmed the connected plan for public video use")
    if redistribute_source_audio and confirmation["scope"] != "public_video_and_source_audio_redistribution":
        raise ValueError("publisher has not confirmed source-audio redistribution")
    return confirmation["scope"]


def _validate_human_listening(receipt: dict, master: dict[str, str]) -> None:
    review = receipt.get("validation", {}).get("human_listening_review")
    keys = {"status", "reviewer", "reviewed_at", "master_sha256", "scope"}
    if not isinstance(review, dict) or set(review) != keys:
        raise ValueError("human listening review fields differ")
    if (
        review["status"] != "approved"
        or not isinstance(review["reviewer"], str)
        or not review["reviewer"].strip()
        or not isinstance(review["reviewed_at"], str)
        or not UTC.fullmatch(review["reviewed_at"])
        or review["master_sha256"] != master["master_sha256"]
        or review["scope"] != "full_master_and_segment_join"
    ):
        raise ValueError("human listening review is not approved for the exact River master")


def _qualification_pin(value: object, name: str) -> dict:
    required = {"run_id", "source_sha", "artifact_id", "archive_bytes", "archive_sha256"}
    if not isinstance(value, dict) or not required <= set(value):
        raise ValueError(f"qualification pin is missing: {name}")
    if (
        not isinstance(value["run_id"], int) or value["run_id"] <= 0
        or not isinstance(value["source_sha"], str) or not HEX40.fullmatch(value["source_sha"])
        or not isinstance(value["artifact_id"], int) or value["artifact_id"] <= 0
        or not isinstance(value["archive_bytes"], int) or value["archive_bytes"] <= 0
        or not isinstance(value["archive_sha256"], str) or not HEX64.fullmatch(value["archive_sha256"])
    ):
        raise ValueError(f"qualification pin is invalid: {name}")
    return value


def _hash_inventory(value: object, name: str) -> dict:
    if (
        not isinstance(value, dict) or not value
        or any(not isinstance(path, str) or not path or not isinstance(digest, str)
               or not HEX64.fullmatch(digest) for path, digest in value.items())
    ):
        raise ValueError(f"qualification media inventory is invalid: {name}")
    return value


def _visual_review(value: object, image: dict, pin: dict, archive_key: str, name: str) -> dict:
    required = {"visual_status", "image_sha256", archive_key, "images"}
    if not isinstance(value, dict) or not required <= set(value):
        raise ValueError(f"qualification media review is missing: {name}")
    if (
        value["visual_status"] != "passed"
        or value["image_sha256"] != image["sha256"]
        or value[archive_key] != pin["archive_sha256"]
    ):
        raise ValueError(f"qualification media review is not bound: {name}")
    _hash_inventory(value["images"], name + " images")
    return value


def _validate_release_binding(receipt: dict, repository: Path) -> tuple[dict, dict]:
    binding = receipt.get("release_binding")
    keys = {"status", "qualified_iso", "qualification_manifest"}
    if not isinstance(binding, dict) or set(binding) != keys:
        raise ValueError("release binding fields differ")
    if binding["status"] != "qualified_release_manifest_bound":
        raise ValueError("final image release manifest is not bound")
    image = _qualified_iso(binding["qualified_iso"])
    qualification = binding["qualification_manifest"]
    manifest_keys = {"path", "sha256", "status"}
    if not isinstance(qualification, dict) or set(qualification) != manifest_keys:
        raise ValueError("qualification manifest receipt fields differ")
    if (
        qualification["status"] != "ready"
        or qualification["path"] != "tools/qualified-release/manifest.json"
        or not isinstance(qualification["sha256"], str)
        or not HEX64.fullmatch(qualification["sha256"])
    ):
        raise ValueError("qualification manifest receipt is invalid")
    path = repository / qualification["path"]
    if not _regular_file(path) or _digest(path.read_bytes()) != qualification["sha256"]:
        raise ValueError("qualification manifest bytes differ")
    try:
        manifest = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("qualification manifest is not valid JSON") from error
    if not isinstance(manifest, dict) or set(manifest) != QUALIFICATION_MANIFEST_KEYS:
        raise ValueError("qualification manifest schema differs")
    if manifest["ready"] is not True or manifest["release_acceptance"] is not False:
        raise ValueError("qualification manifest is not ready for exact-image use")
    if (
        not isinstance(manifest["tag"], str) or not manifest["tag"].strip()
        or not isinstance(manifest["main_sha"], str) or not HEX40.fullmatch(manifest["main_sha"])
        or not isinstance(manifest["execution_files"], dict) or not manifest["execution_files"]
        or any(not _safe_relative(name) or not isinstance(digest, str) or not HEX64.fullmatch(digest)
               for name, digest in manifest["execution_files"].items())
    ):
        raise ValueError("qualification release identity or execution inventory is invalid")
    source = manifest["image"]
    if not isinstance(source, dict):
        raise ValueError("qualification manifest image is missing")
    expected_image = {
        "name": source.get("name"),
        "bytes": source.get("bytes"),
        "sha256": source.get("sha256"),
        "source_commit": source.get("source_sha"),
        "workflow_run": (
            "https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/"
            + str(source.get("run_id"))
        ),
    }
    if expected_image != image:
        raise ValueError("qualification manifest image differs from the bound ISO")

    pins = {
        "performance": _qualification_pin(manifest["performance"], "performance"),
        "native": _qualification_pin(manifest["native"], "native"),
        "installer": _qualification_pin(manifest["installer"], "installer"),
        "installer_active": _qualification_pin(manifest["installer_active"], "installer_active"),
        "update": _qualification_pin(manifest["update"], "update"),
    }
    reliability = manifest["reliability"]
    if not isinstance(reliability, dict) or set(reliability) != {"uefi", "bios"}:
        raise ValueError("both qualified reliability firmware lanes are required")
    for firmware, pin in reliability.items():
        _qualification_pin(pin, "reliability/" + firmware)
    dictation = manifest["dictation"]
    if not isinstance(dictation, dict) or set(dictation) != {"small-v2", "turbo-q5-v3"}:
        raise ValueError("both qualified dictation profiles are required")
    for profile, pin in dictation.items():
        _qualification_pin(pin, "dictation/" + profile)

    _visual_review(manifest["taskbar_media_review"], image, pins["native"],
                   "native_archive_sha256", "taskbar")
    native_review = _visual_review(manifest["media_review"], image, pins["native"],
                                   "native_archive_sha256", "native")
    if native_review.get("audio_status") != "passed":
        raise ValueError("qualification native audio review is not passed")
    _hash_inventory(native_review.get("audio"), "native audio")
    for profile, pin in dictation.items():
        reviews = manifest["dictation_media_review"]
        if not isinstance(reviews, dict) or set(reviews) != {"small-v2", "turbo-q5-v3"}:
            raise ValueError("dictation media review inventory differs")
        _visual_review(reviews[profile], image, pin, "dictation_archive_sha256",
                       "dictation/" + profile)
    _visual_review(manifest["installer_media_review"], image, pins["installer"],
                   "installer_archive_sha256", "installer")
    _visual_review(manifest["installer_active_media_review"], image, pins["installer_active"],
                   "installer_archive_sha256", "installer_active")
    return image, manifest


def _validate_captures(receipt: dict, repository: Path, image: dict) -> None:
    try:
        from .capture_contracts import REVIEWED, contracts_from_provenance
    except ImportError:
        from capture_contracts import REVIEWED, contracts_from_provenance
    provenance_path = repository / "showcase/asset-provenance.json"
    try:
        provenance = json.loads(provenance_path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("showcase asset provenance is unreadable") from error
    try:
        contracts = contracts_from_provenance(provenance, repository)
    except ValueError as error:
        raise ValueError(f"qualified showcase captures are invalid: {error}") from error
    if any(contract["status"] != REVIEWED for contract in contracts.values()):
        raise ValueError("all five qualified showcase captures require human review")
    if any(contract["qualified_iso"] != image for contract in contracts.values()):
        raise ValueError("showcase captures are not bound to the qualified release image")
    revision = receipt.get("direct_voxtype_revision", {})
    if revision.get("capture_evidence") != "reviewed_qualified_direct_voxtype_iso":
        raise ValueError("River receipt does not record reviewed qualified capture evidence")


def _validate_render_timing(repository: Path, master: dict[str, str]) -> None:
    root = repository / "showcase/timing.json"
    revision = repository / "showcase/revision-2026-10-12/timing.json"
    try:
        root_timing = json.loads(root.read_text())
        revision_timing = json.loads(revision.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("render timing receipt is unreadable") from error
    if root_timing != revision_timing:
        raise ValueError("root and revision render timing differ")
    if root_timing.get("render_ready") is not True:
        raise ValueError("aligned timing is not render-ready")
    if abs(float(root_timing.get("duration", -1)) - float(master["master_duration"])) > 0.08:
        raise ValueError("aligned timing does not match the River master")


def _validate_final_render_review(receipt: dict, master: dict[str, str]) -> dict:
    validation = receipt.get("validation")
    if not isinstance(validation, dict) or validation.get("final_render_verified") is not True:
        raise ValueError("final render is not verified")
    review = validation.get("final_render_review")
    keys = {"status", "source_commit", "render", "video", "checks", "human_frame_review"}
    if not isinstance(review, dict) or set(review) != keys or review["status"] != "approved":
        raise ValueError("final render review is not approved")
    if not isinstance(review["source_commit"], str) or not HEX40.fullmatch(review["source_commit"]):
        raise ValueError("final render source commit is invalid")

    render = review["render"]
    render_keys = {
        "workflow_run", "source_commit", "artifact_id", "artifact_name", "archive_bytes",
        "archive_sha256",
    }
    if (
        not isinstance(render, dict) or set(render) != render_keys
        or not isinstance(render["workflow_run"], str) or not HTTPS_RUN.fullmatch(render["workflow_run"])
        or render["source_commit"] != review["source_commit"]
        or not isinstance(render["artifact_id"], int) or render["artifact_id"] <= 0
        or render["artifact_name"] != "Arctic-Linux-Showcase-River-1080p-candidate"
        or not isinstance(render["archive_bytes"], int) or render["archive_bytes"] <= 0
        or not isinstance(render["archive_sha256"], str) or not HEX64.fullmatch(render["archive_sha256"])
    ):
        raise ValueError("final render workflow artifact receipt is invalid")

    video = review["video"]
    video_keys = {"name", "bytes", "sha256", "duration_seconds"}
    if (
        not isinstance(video, dict) or set(video) != video_keys
        or video["name"] != "Arctic-Linux-Showcase-River-1080p.mp4"
        or not SAFE_VIDEO_NAME.fullmatch(video["name"])
        or not isinstance(video["bytes"], int) or not 1_000_000 < video["bytes"] < 2_000_000_000
        or not isinstance(video["sha256"], str) or not HEX64.fullmatch(video["sha256"])
        or not isinstance(video["duration_seconds"], (int, float))
        or abs(float(video["duration_seconds"]) - float(master["master_duration"])) > 0.08
    ):
        raise ValueError("final render MP4 receipt is invalid")

    checks = review["checks"]
    if checks != {
        "full_decode_status": "passed",
        "subtitle_mux_status": "passed",
        "subtitle_codec": "mov_text",
        "subtitle_cues": 130,
        "duration_matches_master": True,
    }:
        raise ValueError("final render decode or subtitle checks are incomplete")

    human = review["human_frame_review"]
    human_keys = {"status", "reviewer", "reviewed_at", "video_sha256", "frames"}
    if not isinstance(human, dict) or set(human) != human_keys:
        raise ValueError("representative-frame review fields differ")
    expected_frames = {
        "frame-intro.png", "frame-files.png", "frame-dictationsetup.png",
        "frame-dictationrecord.png", "frame-dictationrecovery.png", "frame-winter.png",
        "frame-updates.png", "frame-outro.png",
    }
    frames = human.get("frames")
    if (
        human["status"] != "approved"
        or not isinstance(human["reviewer"], str) or not human["reviewer"].strip()
        or not isinstance(human["reviewed_at"], str) or not UTC.fullmatch(human["reviewed_at"])
        or human["video_sha256"] != video["sha256"]
        or not isinstance(frames, dict) or set(frames) != expected_frames
        or any(not isinstance(digest, str) or not HEX64.fullmatch(digest) for digest in frames.values())
    ):
        raise ValueError("representative-frame review is not approved for the exact final MP4")
    return review


def validate_render_readiness(receipt: dict, repository: Path = REPOSITORY) -> dict[str, str]:
    """Validate private candidate-render gates without granting publication."""
    master = validate_assembled_master(receipt, repository)
    if receipt.get("ready_for_render") is not True:
        raise ValueError("segmented direct-VoxType River master is not ready")
    _validate_source_archive(receipt, master)
    _validate_human_listening(receipt, master)
    image, _manifest = _validate_release_binding(receipt, repository)
    _validate_captures(receipt, repository, image)
    _validate_render_timing(repository, master)
    return master


def validate_publication_readiness(
    receipt: dict,
    repository: Path = REPOSITORY,
    *,
    redistribute_source_audio: bool = False,
) -> dict[str, str]:
    """Validate public-video approval and the stronger optional source-audio scope."""
    master = validate_render_readiness(receipt, repository)
    scope = _validate_publication_confirmation(receipt, redistribute_source_audio)
    _image, manifest = _validate_release_binding(receipt, repository)
    if manifest["publication_approved"] is not True:
        raise ValueError("qualified release publication is not approved")
    _validate_final_render_review(receipt, master)
    return {
        **master,
        "admission": "public_video",
        "publication_scope": scope,
        "source_audio_redistribution": "true" if redistribute_source_audio else "false",
    }


def resolve(receipt: dict, repository: Path = REPOSITORY) -> dict[str, str]:
    return {**validate_render_readiness(receipt, repository), "admission": "private_render"}


def resolve_publication(
    receipt: dict,
    repository: Path = REPOSITORY,
    *,
    redistribute_source_audio: bool = False,
) -> dict[str, str]:
    return validate_publication_readiness(
        receipt, repository, redistribute_source_audio=redistribute_source_audio
    )
