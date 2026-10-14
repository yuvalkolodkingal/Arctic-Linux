"""Fail-closed contracts for final-image showcase captures."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from PIL import Image

PENDING = "pending_qualified_direct_voxtype_iso"
REVIEWED = "reviewed_qualified_direct_voxtype_iso"
ACCEPTANCE = (
    "Capture must come from the qualified release candidate and be manually reviewed "
    "before render readiness is enabled."
)
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
HTTPS_RUN = re.compile(
    r"https://github\.com/yuvalkolodkingal/Arctic-Linux/actions/runs/[1-9][0-9]*"
)

CAPTURES = {
    "dictationsetup": {
        "output": "showcase/assets/dictation-setup-current.png",
        "required_evidence": [
            "signature-checked official VoxType 1.1.0 identity and ready status",
            "verified automatic online setup",
            "offline not-ready state with retry",
        ],
    },
    "dictationrecord": {
        "output": "showcase/assets/dictation-recording-current.png",
        "required_evidence": [
            "readiness helper invoking official voxtype record toggle",
            "Arctic indicator following official VoxType runtime state",
            "successful local text insertion",
        ],
    },
    "dictationrecovery": {
        # A single truthful frame cannot show both the Vulkan failure and the
        # later CPU-ready state: selecting CPU clears the runtime error. Keep
        # the two moments independently reviewable and bind both exact images
        # into one scene contract.
        "output": {
            "gpu_failure": "showcase/assets/dictation-recovery-gpu-failure-current.png",
            "cpu_ready": "showcase/assets/dictation-recovery-cpu-ready-current.png",
        },
        "required_evidence": [
            "visible GPU setup failure",
            "explicit CPU selection and ready status",
            "Hebrew and English multilingual configuration",
        ],
    },
    "winter": {
        "output": "showcase/assets/wallpaper-hide-restore-current.png",
        "required_evidence": [
            "Delete hiding one packaged wallpaper for the current account",
            "Restore making the hidden packaged wallpaper available again",
            "personal wallpaper choice remaining unchanged",
        ],
    },
    "updates": {
        "output": "showcase/assets/whats-new-current.png",
        "required_evidence": [
            "What's New appearing once after an installed update",
            "release notes reopening from Settings",
            "signed stable update state",
        ],
    },
}


class CaptureContractError(ValueError):
    """A capture receipt is incomplete, stale, or inconsistent with its bytes."""


def pending_contract(scene: str) -> dict:
    spec = CAPTURES[scene]
    return {
        "status": PENDING,
        "required_evidence": spec["required_evidence"],
        "source": None,
        "output": spec["output"],
        "sha256": None,
        "qualified_iso": None,
        "human_review": {"status": "pending", "reviewer": None, "reviewed_at": None},
        "acceptance": ACCEPTANCE,
    }


def _regular_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _safe_source(value: object) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and not value.startswith("/")
        and ".." not in Path(value).parts
    )


def _capture_files(scene: str, contract: dict) -> list[tuple[str, str]]:
    """Return (output, digest) pairs for a reviewed single or paired capture."""
    output = contract["output"]
    source = contract["source"]
    digest = contract["sha256"]
    if isinstance(output, str):
        if not _safe_source(source):
            raise CaptureContractError(f"{scene}: unsafe capture source")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            raise CaptureContractError(f"{scene}: invalid capture digest")
        return [(output, digest)]

    keys = set(output) if isinstance(output, dict) else set()
    if (
        not keys
        or not isinstance(source, dict)
        or not isinstance(digest, dict)
        or set(source) != keys
        or set(digest) != keys
    ):
        raise CaptureContractError(f"{scene}: paired capture fields differ")
    if not all(_safe_source(source[key]) for key in keys):
        raise CaptureContractError(f"{scene}: unsafe paired capture source")
    if not all(isinstance(digest[key], str) and HEX64.fullmatch(digest[key]) for key in keys):
        raise CaptureContractError(f"{scene}: invalid paired capture digest")
    return [(output[key], digest[key]) for key in sorted(keys)]


def validate_contract(scene: str, contract: dict, repo: Path, *, require_asset: bool = True) -> dict:
    """Validate one fixed scene contract and return it unchanged."""
    if scene not in CAPTURES or not isinstance(contract, dict):
        raise CaptureContractError(f"unknown capture scene: {scene}")
    expected_keys = {
        "status", "required_evidence", "source", "output", "sha256",
        "qualified_iso", "human_review", "acceptance",
    }
    if set(contract) != expected_keys:
        raise CaptureContractError(f"{scene}: capture contract fields differ")
    spec = CAPTURES[scene]
    if contract["required_evidence"] != spec["required_evidence"]:
        raise CaptureContractError(f"{scene}: required evidence differs")
    if contract["output"] != spec["output"] or contract["acceptance"] != ACCEPTANCE:
        raise CaptureContractError(f"{scene}: output or acceptance text differs")

    if contract["status"] == PENDING:
        if contract["source"] is not None or contract["sha256"] is not None or contract["qualified_iso"] is not None:
            raise CaptureContractError(f"{scene}: pending capture contains evidence claims")
        if contract["human_review"] != {"status": "pending", "reviewer": None, "reviewed_at": None}:
            raise CaptureContractError(f"{scene}: pending capture claims human approval")
        return contract

    if contract["status"] != REVIEWED:
        raise CaptureContractError(f"{scene}: unknown capture status")
    files = _capture_files(scene, contract)
    image = contract["qualified_iso"]
    if not isinstance(image, dict) or set(image) != {"name", "bytes", "sha256", "source_commit", "workflow_run"}:
        raise CaptureContractError(f"{scene}: qualified ISO receipt fields differ")
    if not isinstance(image["name"], str) or not image["name"].endswith(".iso"):
        raise CaptureContractError(f"{scene}: qualified ISO name differs")
    if not isinstance(image["bytes"], int) or not 0 < image["bytes"] < 2_000_000_000:
        raise CaptureContractError(f"{scene}: qualified ISO size is invalid")
    if not isinstance(image["sha256"], str) or not HEX64.fullmatch(image["sha256"]):
        raise CaptureContractError(f"{scene}: qualified ISO digest is invalid")
    if not isinstance(image["source_commit"], str) or not HEX40.fullmatch(image["source_commit"]):
        raise CaptureContractError(f"{scene}: qualified ISO commit is invalid")
    if not isinstance(image["workflow_run"], str) or not HTTPS_RUN.fullmatch(image["workflow_run"]):
        raise CaptureContractError(f"{scene}: qualified ISO workflow is invalid")
    review = contract["human_review"]
    if not isinstance(review, dict) or set(review) != {"status", "reviewer", "reviewed_at"}:
        raise CaptureContractError(f"{scene}: review fields differ")
    if review["status"] != "approved" or not isinstance(review["reviewer"], str) or not review["reviewer"].strip():
        raise CaptureContractError(f"{scene}: human review is not approved")
    if not isinstance(review["reviewed_at"], str) or not re.fullmatch(
        r"20[0-9]{2}-[01][0-9]-[0-3][0-9]T[0-2][0-9]:[0-5][0-9]:[0-5][0-9]Z",
        review["reviewed_at"],
    ):
        raise CaptureContractError(f"{scene}: review timestamp is invalid")

    if require_asset:
        for output, digest in files:
            path = repo / output
            if not _regular_file(path):
                raise CaptureContractError(f"{scene}: reviewed capture asset is missing")
            if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise CaptureContractError(f"{scene}: reviewed capture digest differs")
            with Image.open(path) as picture:
                if picture.format != "PNG" or picture.mode != "RGB" or picture.size != (1280, 800):
                    raise CaptureContractError(f"{scene}: capture must be metadata-free 1280x800 RGB PNG")
                if picture.info:
                    raise CaptureContractError(f"{scene}: capture contains image metadata")
    return contract


def contracts_from_provenance(provenance: list, repo: Path, *, require_assets: bool = True) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for entry in provenance:
        if not isinstance(entry, dict) or "capture_contract" not in entry:
            continue
        scene = entry.get("scene")
        if scene in found:
            raise CaptureContractError(f"{scene}: duplicate capture contract")
        found[scene] = validate_contract(scene, entry["capture_contract"], repo, require_asset=require_assets)
    if set(found) != set(CAPTURES):
        raise CaptureContractError("capture contract set differs")
    return found


def preserve_reviewed_contracts(provenance: list, repo: Path) -> dict[str, dict]:
    """Migrate pending records while retaining only fully valid reviewed records."""
    preserved: dict[str, dict] = {}
    for entry in provenance:
        if not isinstance(entry, dict) or "capture_contract" not in entry:
            continue
        scene = entry.get("scene")
        if scene not in CAPTURES or scene in preserved:
            raise CaptureContractError(f"invalid or duplicate capture contract: {scene!r}")
        contract = entry["capture_contract"]
        status = contract.get("status") if isinstance(contract, dict) else None
        if status == PENDING:
            preserved[scene] = pending_contract(scene)
        elif status == REVIEWED:
            preserved[scene] = validate_contract(scene, contract, repo)
        else:
            raise CaptureContractError(f"{scene}: unknown capture contract status")
    return preserved
