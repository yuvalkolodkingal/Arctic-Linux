#!/usr/bin/env python3
"""Admit bounded, transcript-free VoxType qualification frames for showcase review.

The dictation qualification lane already drives the official VoxType binary with
the public audio fixture and binds host screenshots to its checked report.  This
module imports only those exact screenshots and closed receipts.  It never runs
VoxType, accepts transcript output, or grants release/publication acceptance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import io
import json
import os
import shutil
import stat
import tarfile
import zipfile
from pathlib import Path, PurePosixPath

try:
    from . import bundle
    from . import contract as c
    from . import host
except ImportError:
    import bundle
    import contract as c
    import host


PIN_SCHEMA = "arctic-showcase-dictation-evidence-pin-v1"
BUNDLE_SCHEMA = "arctic-showcase-dictation-capture-bundle-v1"
DIGEST_SCHEMA = "arctic-showcase-dictation-capture-digest-v1"
WORKFLOW = ".github/workflows/dictation-candidate-20261009.yml"
BRANCH = "codex/qualification-dispatch-20261010"
ARTIFACT_NAME = "dictation-candidate-qualification-turbo-q5-v3"
QUALIFICATION_CONTRACT_SHA256 = "5a86ba1643d5bf90374750d394acfa92a83a1ea7cd2cee0a04e28b40883f1884"
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_MEMBER_COUNT = 20

REPORTS = (
    "online-installed-live.json", "online-installed.json",
    "offline-installed-live.json", "offline-installed.json",
    "recovery.json", "recovered-offline.json",
)
INDICATORS = (
    "dictation-indicator-online-installed.png",
    "dictation-indicator-recovered-offline.png",
)
RECOVERY = tuple(
    "dictation-recovery-" + phase + "-" + stage + ".png"
    for phase in ("online-installed", "recovered-offline")
    for stage in ("gpu-failure", "cpu-ready")
)
EVIDENCE_MEMBERS = frozenset(("execution.json", "fixtures.json", *REPORTS,
                              *INDICATORS, *RECOVERY))
SELECTED = {
    "dictationrecord": {"recording": "dictation-indicator-online-installed.png"},
    "dictationrecovery": {
        "gpu_failure": "dictation-recovery-online-installed-gpu-failure.png",
        "cpu_ready": "dictation-recovery-online-installed-cpu-ready.png",
    },
}


def _regular(path: Path, maximum: int, *, private: bool = False):
    try:
        info = path.lstat()
    except OSError as error:
        raise c.Invalid("dictation evidence member unavailable") from error
    c.require(stat.S_ISREG(info.st_mode) and not path.is_symlink() and info.st_nlink == 1
              and info.st_uid == os.geteuid() and not info.st_mode & 0o022
              and (not private or not info.st_mode & 0o077)
              and 0 < info.st_size <= maximum,
              "dictation evidence member is not one bounded owned regular file")
    return info


def _read_json(path: Path, maximum=MAX_JSON_BYTES):
    _regular(path, maximum)
    try:
        return c.strict_json(path.read_bytes())
    except OSError as error:
        raise c.Invalid("dictation evidence JSON unavailable") from error


def evidence_pin(value) -> dict:
    keys = {
        "schema", "run_id", "run_attempt", "workflow", "branch", "source_sha",
        "artifact_id", "artifact_name", "archive_bytes", "archive_sha256",
        "hardware_profile", "fixture_manifest_sha256", "qualification_contract_sha256",
        "image",
    }
    c.require(type(value) is dict and set(value) == keys and value["schema"] == PIN_SCHEMA
              and type(value["run_id"]) is int and value["run_id"] > 0
              and value["run_attempt"] == 1 and value["workflow"] == WORKFLOW
              and value["branch"] == BRANCH and c.fullmatch(c.HEX40, value["source_sha"])
              and type(value["artifact_id"]) is int and value["artifact_id"] > 0
              and value["artifact_name"] == ARTIFACT_NAME
              and type(value["archive_bytes"]) is int
              and 0 < value["archive_bytes"] <= MAX_ARCHIVE_BYTES
              and c.fullmatch(c.HEX64, value["archive_sha256"])
              and value["hardware_profile"] == "turbo-q5-v3"
              and c.fullmatch(c.HEX64, value["fixture_manifest_sha256"])
              and value["qualification_contract_sha256"] == QUALIFICATION_CONTRACT_SHA256
              and value["image"] == c.IMAGE,
              "dictation qualification evidence pin differs")
    return value


def verify_metadata(pin, run, artifact) -> None:
    """Bind the GitHub run and artifact metadata before archive download."""
    evidence_pin(pin)
    c.require(type(run) is dict
              and run.get("id") == pin["run_id"]
              and run.get("run_attempt") == 1
              and run.get("event") == "push"
              and run.get("head_branch") == pin["branch"]
              and run.get("head_sha") == pin["source_sha"]
              and run.get("status") == "completed"
              and run.get("conclusion") == "success"
              and type(run.get("path")) is str
              and run["path"].split("@", 1)[0] == pin["workflow"]
              and run.get("repository", {}).get("full_name") == "yuvalkolodkingal/Arctic-Linux",
              "dictation qualification workflow metadata differs")
    workflow_run = artifact.get("workflow_run", {}) if type(artifact) is dict else {}
    c.require(type(artifact) is dict
              and artifact.get("id") == pin["artifact_id"]
              and artifact.get("name") == pin["artifact_name"]
              and artifact.get("size_in_bytes") == pin["archive_bytes"]
              and artifact.get("digest") == "sha256:" + pin["archive_sha256"]
              and artifact.get("expired") is False
              and workflow_run.get("id") == pin["run_id"]
              and workflow_run.get("head_sha") == pin["source_sha"],
              "dictation qualification artifact metadata differs")


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    name = info.filename
    path = PurePosixPath(name)
    mode = (info.external_attr >> 16) & 0xffff
    file_type = mode & 0o170000
    c.require(type(name) is str and name and "\\" not in name and not path.is_absolute()
              and len(path.parts) == 1 and path.parts[0] not in (".", "..")
              and not info.is_dir() and not info.flag_bits & 1
              and file_type in (0, stat.S_IFREG),
              "dictation qualification archive member is unsafe")
    return name


def extract_archive(pin, archive: Path, output: Path) -> None:
    """Verify the exact GitHub archive, then extract its closed member set."""
    evidence_pin(pin)
    info = _regular(archive, MAX_ARCHIVE_BYTES, private=True)
    c.require(info.st_size == pin["archive_bytes"] and c.sha256(archive) == pin["archive_sha256"],
              "dictation qualification archive bytes differ")
    c.require(not output.exists() and not output.is_symlink(),
              "refusing to replace dictation qualification evidence")
    created = False
    try:
        with zipfile.ZipFile(archive) as zipped:
            infos = zipped.infolist()
            names = [_zip_member_name(item) for item in infos]
            c.require(0 < len(infos) <= MAX_MEMBER_COUNT and len(names) == len(set(names))
                      and set(names) == EVIDENCE_MEMBERS,
                      "dictation qualification archive inventory differs")
            total = 0
            for item in infos:
                maximum = host.MAX_PNG_BYTES if item.filename.endswith(".png") else MAX_JSON_BYTES
                c.require(0 < item.file_size <= maximum and item.compress_size > 0
                          and item.file_size <= max(item.compress_size * 250, 1024 * 1024),
                          "dictation qualification archive member size differs")
                total += item.file_size
            c.require(total <= MAX_ARCHIVE_BYTES, "dictation qualification archive expands too far")
            output.mkdir(mode=0o700)
            created = True
            for item in infos:
                data = zipped.read(item)
                c.require(len(data) == item.file_size,
                          "dictation qualification archive member was truncated")
                target = output / item.filename
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                                     | getattr(os, "O_NOFOLLOW", 0), 0o600)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
        c.require({path.name for path in output.iterdir()} == EVIDENCE_MEMBERS,
                  "dictation qualification extraction inventory differs")
    except BaseException:
        if created:
            shutil.rmtree(output, ignore_errors=True)
        raise


def _load_qualification_contract(repository: Path):
    path = repository / "tools/dictation-qualification/contract.py"
    c.require(path.is_file() and not path.is_symlink()
              and c.sha256(path) == QUALIFICATION_CONTRACT_SHA256,
              "dictation qualification contract identity differs")
    spec = importlib.util.spec_from_file_location("showcase_dictation_contract", path)
    c.require(spec is not None and spec.loader is not None,
              "dictation qualification contract unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _gate(report, name):
    rows = [row for row in report.get("gates", [])
            if type(row) is dict and row.get("id") == name and row.get("status") == "passed"]
    c.require(len(rows) == 1, "required dictation qualification gate is absent")
    return rows[0]


def _indicator_proof(proof, report, pin, evidence: Path):
    request = proof.get("request") if type(proof) is dict else None
    keys = {"boot_id", "installation_id", "phase", "desktop_uid", "receiver_empty",
            "capture_nonce"}
    c.require(type(proof) is dict
              and set(proof) == {"request", "path", "sha256", "iso_sha256", "installation_id"}
              and type(request) is dict and set(request) == keys
              and request["phase"] == "online-installed" and request["receiver_empty"] is True
              and request["desktop_uid"] == c.CONTROLLER["account"]["uid"]
              and c.fullmatch(c.HEX32, request["capture_nonce"])
              and request["boot_id"] == report["boot_id"]
              and request["installation_id"] == report["context"]["installation_id"]
              and request["installation_id"] == proof["installation_id"]
              and proof["iso_sha256"] == pin["image"]["sha256"]
              and proof["path"] == SELECTED["dictationrecord"]["recording"]
              and c.fullmatch(c.HEX64, proof["sha256"]),
              "recording indicator proof differs")
    observed = _gate(report, "recording-status-published").get("observations", {})
    c.require(observed.get("sha256") == c.hashed(request["capture_nonce"]),
              "recording indicator acknowledgement differs")
    path = evidence / proof["path"]
    _regular(path, host.MAX_PNG_BYTES, private=True)
    c.require(c.sha256(path) == proof["sha256"], "recording indicator screenshot differs")
    return proof, path


def _recovery_proofs(proofs, report, pin, evidence: Path):
    c.require(type(proofs) is dict and set(proofs) == {"gpu_failure", "cpu_ready"},
              "dictation recovery proof inventory differs")
    gate = _gate(report, "gpu-failure-explicit-cpu-fallback")
    observed = gate.get("observations", {})
    result = {}
    for stage in ("gpu_failure", "cpu_ready"):
        proof = proofs[stage]
        request = proof.get("request") if type(proof) is dict else None
        expected_state = "error" if stage == "gpu_failure" else "ready"
        expected_name = SELECTED["dictationrecovery"][stage]
        keys = {"boot_id", "installation_id", "phase", "desktop_uid", "receiver_empty",
                "stage", "state", "backend", "language", "capture_nonce"}
        c.require(type(proof) is dict
                  and set(proof) == {"request", "path", "sha256", "iso_sha256", "installation_id"}
                  and type(request) is dict and set(request) == keys
                  and request["phase"] == "online-installed" and request["stage"] == stage
                  and request["state"] == expected_state and request["backend"] == "cpu"
                  and request["language"] == "he" and request["receiver_empty"] is True
                  and request["desktop_uid"] == c.CONTROLLER["account"]["uid"]
                  and c.fullmatch(c.HEX32, request["capture_nonce"])
                  and request["boot_id"] == report["boot_id"]
                  and request["installation_id"] == report["context"]["installation_id"]
                  and request["installation_id"] == proof["installation_id"]
                  and proof["iso_sha256"] == pin["image"]["sha256"]
                  and proof["path"] == expected_name and c.fullmatch(c.HEX64, proof["sha256"])
                  and observed.get(stage + "_capture_ack_sha256") == c.hashed(request["capture_nonce"]),
                  "dictation recovery screenshot proof differs")
        path = evidence / expected_name
        _regular(path, host.MAX_PNG_BYTES, private=True)
        c.require(c.sha256(path) == proof["sha256"], "dictation recovery screenshot differs")
        result[stage] = (proof, path)
    c.require(result["gpu_failure"][0]["sha256"] != result["cpu_ready"][0]["sha256"],
              "dictation recovery screenshots are byte-identical")
    return result


def validate_evidence(pin, evidence: Path, repository: Path):
    evidence_pin(pin)
    c.require(evidence.is_dir() and not evidence.is_symlink()
              and {path.name for path in evidence.iterdir()} == EVIDENCE_MEMBERS,
              "dictation qualification evidence inventory differs")
    state = _read_json(evidence / "execution.json")
    fixtures = evidence / "fixtures.json"
    c.require(c.sha256(fixtures) == pin["fixture_manifest_sha256"],
              "dictation fixture manifest digest differs")
    reports = {name[:-5]: _read_json(evidence / name) for name in REPORTS}
    qualification = _load_qualification_contract(repository)
    qualification.validate_execution(state, reports, fixture_manifest=fixtures)
    expected_context = {
        "iso_sha256": pin["image"]["sha256"],
        "iso_bytes": pin["image"]["bytes"],
        "source_sha": pin["image"]["source_sha"],
        "contract_sha256": QUALIFICATION_CONTRACT_SHA256,
    }
    c.require(all(type(report.get("context")) is dict
                  and all(report["context"].get(key) == expected
                          for key, expected in expected_context.items())
                  for report in reports.values()),
              "dictation qualification report provenance differs")
    c.require(state.get("schema") == "arctic-voxtype-execution-v3"
              and state.get("status") == "exact_image_dictation_online_offline_local_sessions_passed"
              and state.get("release_acceptance") is False
              and state.get("hardware_profile") == pin["hardware_profile"]
              and state.get("image") == pin["image"]
              and state.get("execution_checker_head") == pin["source_sha"]
              and state.get("fixture_manifest_sha256") == pin["fixture_manifest_sha256"],
              "dictation qualification execution identity differs")
    report = reports["online-installed"]
    c.require(state.get("reports", {}).get("online-installed", {}).get("path")
              == "online-installed.json"
              and state["reports"]["online-installed"].get("sha256")
              == c.sha256(evidence / "online-installed.json"),
              "online dictation report receipt differs")
    indicator = _indicator_proof(state.get("indicators", {}).get("online-installed"),
                                 report, pin, evidence)
    recovery = _recovery_proofs(state.get("recovery_screens", {}).get("online-installed"),
                                report, pin, evidence)
    return state, report, indicator, recovery


def _json_bytes(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode()


def _write_new(path: Path, data: bytes):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                         | getattr(os, "O_NOFOLLOW", 0), 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def _inventory(root: Path):
    rows = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        info = _regular(path, MAX_JSON_BYTES if path.suffix == ".json" else host.MAX_PNG_BYTES)
        rows[relative] = {"bytes": info.st_size, "sha256": c.sha256(path)}
    return rows


def _archive(root: Path, target: Path):
    with target.open("xb") as stream:
        with tarfile.open(fileobj=stream, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            for path in sorted(root.rglob("*")):
                relative = path.relative_to(root).as_posix()
                info = path.lstat()
                c.require(not path.is_symlink()
                          and (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)),
                          "dictation bundle contains unsupported member")
                entry = tarfile.TarInfo(relative)
                entry.uid = entry.gid = entry.mtime = 0
                entry.uname = entry.gname = ""
                if stat.S_ISDIR(info.st_mode):
                    entry.type, entry.mode = tarfile.DIRTYPE, 0o700
                    archive.addfile(entry)
                else:
                    data = path.read_bytes()
                    entry.size, entry.mode = len(data), 0o600
                    archive.addfile(entry, io.BytesIO(data))
    os.chmod(target, 0o600)
    info = _regular(target, 128 * 1024 * 1024, private=True)
    return {"name": target.name, "format": "ustar", "bytes": info.st_size,
            "sha256": c.sha256(target)}


def _source_receipt(proof, source: Path, normalized, report: Path, pin):
    request = proof["request"]
    return {
        "source": {"artifact": copy.deepcopy(pin), "member": source.name,
                   "bytes": source.stat().st_size, "sha256": proof["sha256"]},
        "binding": {"phase": "online-installed", "report": report.name,
                    "report_sha256": c.sha256(report),
                    "request_sha256": c.json_hash(request),
                    "boot_id_sha256": c.hashed(request["boot_id"]),
                    "installation_id_sha256": c.hashed(request["installation_id"]),
                    "receiver_empty": True},
        "output": normalized,
    }


def export(pin, evidence: Path, repository: Path, destination: Path, archive_path: Path,
           digest_path: Path, ocr_timeout=60, private_fragments=()):
    """Create the two-scene, three-frame human-review supplement."""
    _state, _report, indicator, recovery = validate_evidence(pin, evidence, repository)
    for path in (destination, archive_path, digest_path):
        c.require(not path.exists() and not path.is_symlink(),
                  "refusing to replace dictation capture transport")
    created = []
    try:
        destination.mkdir(mode=0o700)
        created.append(destination)
        captures = destination / "captures"
        receipts = destination / "receipts"
        captures.mkdir(mode=0o700)
        receipts.mkdir(mode=0o700)
        report_path = evidence / "online-installed.json"

        admitted = {}
        selected = {
            "dictationrecord": {"recording": indicator},
            "dictationrecovery": recovery,
        }
        for scene, frames in selected.items():
            admitted[scene] = {}
            for label, (proof, source) in frames.items():
                output = captures / (scene + ("" if scene == "dictationrecord" else "-" + label.replace("_", "-")) + ".png")
                # The source artifact is private input.  OCR both it and the
                # normalized copy before retaining only the latter.
                c.privacy_text(bundle.tesseract_ocr(source, ocr_timeout), private_fragments)
                normalized = host.normalize(source, output)
                c.privacy_text(bundle.tesseract_ocr(output, ocr_timeout), private_fragments)
                admitted[scene][label] = _source_receipt(proof, source, normalized,
                                                         report_path, pin)

        scene_receipts = {
            "dictationrecord": {
                "schema": "arctic-showcase-qualified-dictation-capture-v1",
                "scene": "dictationrecord", "status": "captured_unreviewed",
                "release_acceptance": False, "image": copy.deepcopy(c.IMAGE),
                "scene_contract": copy.deepcopy(c.DICTATION_EVIDENCE_CONTRACTS["dictationrecord"]),
                "qualification_gate": "recording-status-published",
                "frames": admitted["dictationrecord"],
                "privacy": {"automated": "passed", "human": "pending", "redactions": []},
                "limitations": ["This showcase capture is not release acceptance.",
                                "Human review of the exact normalized pixels remains pending.",
                                "The public fixture receiver was empty when the official VoxType recording state was captured."],
            },
            "dictationrecovery": {
                "schema": "arctic-showcase-qualified-dictation-capture-v1",
                "scene": "dictationrecovery", "status": "captured_unreviewed",
                "release_acceptance": False, "image": copy.deepcopy(c.IMAGE),
                "scene_contract": copy.deepcopy(c.DICTATION_EVIDENCE_CONTRACTS["dictationrecovery"]),
                "qualification_gate": "gpu-failure-explicit-cpu-fallback",
                "frames": admitted["dictationrecovery"],
                "privacy": {"automated": "passed", "human": "pending", "redactions": []},
                "limitations": ["This showcase capture is not release acceptance.",
                                "Human review of both exact normalized frames remains pending.",
                                "The non-GPU VM proves failure and explicit CPU recovery, not physical GPU acceleration."],
            },
        }
        for scene, receipt in scene_receipts.items():
            _write_new(receipts / (scene + ".json"), _json_bytes(receipt))

        scenes = {}
        for scene, receipt in scene_receipts.items():
            receipt_path = receipts / (scene + ".json")
            outputs = {label: {"path": "captures/" + value["output"]["path"],
                               "repository_target": (c.DICTATION_EVIDENCE_OUTPUTS[scene]
                                   if scene == "dictationrecord"
                                   else c.DICTATION_EVIDENCE_OUTPUTS[scene][label]),
                               "bytes": value["output"]["bytes"],
                               "sha256": value["output"]["sha256"]}
                       for label, value in receipt["frames"].items()}
            scenes[scene] = {"receipt": "receipts/" + receipt_path.name,
                             "receipt_bytes": receipt_path.stat().st_size,
                             "receipt_sha256": c.sha256(receipt_path), "outputs": outputs}
        manifest = {
            "schema": BUNDLE_SCHEMA, "status": "captured_unreviewed",
            "release_acceptance": False, "human_review": "pending",
            "image": copy.deepcopy(c.IMAGE), "evidence": copy.deepcopy(pin),
            "ocr": copy.deepcopy(c.OCR_IDENTITY),
            "privacy": {"automated": "passed_and_rechecked_after_export", "human": "pending"},
            "scenes": scenes,
        }
        _write_new(destination / "bundle.json", _json_bytes(manifest))
        created.append(archive_path)
        archive_record = _archive(destination, archive_path)
        members = _inventory(destination)
        core = {"manifest": members["bundle.json"], "ocr": c.OCR_IDENTITY,
                "members": members, "archive": archive_record}
        digest = {"schema": DIGEST_SCHEMA, "bundle_schema": BUNDLE_SCHEMA,
                  "release_acceptance": False, "human_review": "pending", **core,
                  "aggregate_sha256": c.json_hash(core)}
        created.append(digest_path)
        _write_new(digest_path, _json_bytes(digest))
        validate(destination, digest, archive_path, ocr_timeout, private_fragments)
        return manifest, digest
    except BaseException:
        for path in reversed(created):
            try:
                shutil.rmtree(path) if path.is_dir() and not path.is_symlink() else path.unlink(missing_ok=True)
            except OSError:
                pass
        raise


def validate(root: Path, digest, archive_path: Path, ocr_timeout=60, private_fragments=()):
    measured_ocr = bundle.approved_ocr_identity()
    c.require(root.is_dir() and not root.is_symlink()
              and {path.name for path in root.iterdir()} == {"bundle.json", "captures", "receipts"},
              "dictation capture bundle inventory differs")
    manifest = _read_json(root / "bundle.json")
    c.require(type(manifest) is dict
              and set(manifest) == {"schema", "status", "release_acceptance", "human_review",
                                    "image", "evidence", "ocr", "privacy", "scenes"}
              and manifest["schema"] == BUNDLE_SCHEMA
              and manifest["status"] == "captured_unreviewed"
              and manifest["release_acceptance"] is False
              and manifest["human_review"] == "pending"
              and manifest["image"] == c.IMAGE
              and manifest["ocr"] == measured_ocr
              and manifest["privacy"] == {"automated": "passed_and_rechecked_after_export",
                                           "human": "pending"}
              and set(manifest["scenes"]) == set(c.DICTATION_EVIDENCE_SCENES),
              "dictation capture bundle manifest differs")
    evidence_pin(manifest["evidence"])
    c.require(type(digest) is dict and digest.get("schema") == DIGEST_SCHEMA
              and digest.get("bundle_schema") == BUNDLE_SCHEMA
              and digest.get("release_acceptance") is False
              and digest.get("human_review") == "pending",
              "dictation capture digest contract differs")
    archive = digest.get("archive")
    c.require(type(archive) is dict and set(archive) == {"name", "format", "bytes", "sha256"}
              and archive["name"] == archive_path.name and archive["format"] == "ustar",
              "dictation capture archive receipt differs")
    info = _regular(archive_path, 128 * 1024 * 1024, private=True)
    c.require(info.st_size == archive["bytes"] and c.sha256(archive_path) == archive["sha256"],
              "dictation capture archive differs")
    members = _inventory(root)
    core = {"manifest": members["bundle.json"], "ocr": c.OCR_IDENTITY,
            "members": members, "archive": archive}
    c.require(digest.get("manifest") == members["bundle.json"]
              and digest.get("ocr") == c.OCR_IDENTITY and digest.get("members") == members
              and digest.get("aggregate_sha256") == c.json_hash(core),
              "dictation capture transport digest differs")

    expected_captures = {"dictationrecord.png", "dictationrecovery-gpu-failure.png",
                         "dictationrecovery-cpu-ready.png"}
    c.require({path.name for path in (root / "captures").iterdir()} == expected_captures
              and {path.name for path in (root / "receipts").iterdir()}
              == {scene + ".json" for scene in c.DICTATION_EVIDENCE_SCENES},
              "dictation capture scene files differ")
    for scene in c.DICTATION_EVIDENCE_SCENES:
        entry = manifest["scenes"][scene]
        receipt_path = root / entry["receipt"]
        receipt = _read_json(receipt_path)
        labels = {"recording"} if scene == "dictationrecord" else {"gpu_failure", "cpu_ready"}
        expected_gate = ("recording-status-published" if scene == "dictationrecord"
                         else "gpu-failure-explicit-cpu-fallback")
        c.require(set(entry) == {"receipt", "receipt_bytes", "receipt_sha256", "outputs"}
                  and entry["receipt"] == "receipts/" + scene + ".json"
                  and receipt_path.stat().st_size == entry["receipt_bytes"]
                  and c.sha256(receipt_path) == entry["receipt_sha256"]
                  and type(receipt) is dict
                  and set(receipt) == {"schema", "scene", "status", "release_acceptance",
                                       "image", "scene_contract", "qualification_gate", "frames",
                                       "privacy", "limitations"}
                  and receipt.get("schema") == "arctic-showcase-qualified-dictation-capture-v1"
                  and receipt.get("scene") == scene and receipt.get("status") == "captured_unreviewed"
                  and receipt.get("release_acceptance") is False and receipt.get("image") == c.IMAGE
                  and receipt.get("scene_contract") == c.DICTATION_EVIDENCE_CONTRACTS[scene]
                  and receipt.get("qualification_gate") == expected_gate
                  and receipt.get("privacy") == {"automated": "passed", "human": "pending",
                                                  "redactions": []}
                  and type(receipt.get("limitations")) is list
                  and len(receipt["limitations"]) == 3
                  and all(type(item) is str and item for item in receipt["limitations"])
                  and set(receipt.get("frames", {})) == labels and set(entry["outputs"]) == labels,
                  "dictation capture scene receipt differs")
        for label in labels:
            output = entry["outputs"][label]
            frame = receipt["frames"][label]
            output_path = root / output["path"]
            expected_member = SELECTED[scene][label]
            target = (c.DICTATION_EVIDENCE_OUTPUTS[scene] if scene == "dictationrecord"
                      else c.DICTATION_EVIDENCE_OUTPUTS[scene][label])
            source = frame.get("source") if type(frame) is dict else None
            binding = frame.get("binding") if type(frame) is dict else None
            normalized = frame.get("output") if type(frame) is dict else None
            c.require(set(output) == {"path", "repository_target", "bytes", "sha256"}
                      and type(frame) is dict and set(frame) == {"source", "binding", "output"}
                      and type(source) is dict
                      and set(source) == {"artifact", "member", "bytes", "sha256"}
                      and source["artifact"] == manifest["evidence"]
                      and source["member"] == expected_member
                      and type(source["bytes"]) is int and 0 < source["bytes"] <= host.MAX_PNG_BYTES
                      and c.fullmatch(c.HEX64, source["sha256"])
                      and type(binding) is dict
                      and set(binding) == {"phase", "report", "report_sha256", "request_sha256",
                                           "boot_id_sha256", "installation_id_sha256", "receiver_empty"}
                      and binding["phase"] == "online-installed"
                      and binding["report"] == "online-installed.json"
                      and all(c.fullmatch(c.HEX64, binding[key]) for key in
                              ("report_sha256", "request_sha256", "boot_id_sha256",
                               "installation_id_sha256"))
                      and binding["receiver_empty"] is True
                      and type(normalized) is dict
                      and set(normalized) == {"path", "bytes", "sha256", "pixel_sha256", "format",
                                              "width", "height", "transformation", "pillow_version"}
                      and output["repository_target"] == target
                      and output["bytes"] == output_path.stat().st_size
                      and output["sha256"] == c.sha256(output_path)
                      and normalized["path"] == output_path.name
                      and normalized["sha256"] == output["sha256"]
                      and normalized["bytes"] == output["bytes"]
                      and normalized["format"] == "PNG"
                      and normalized["width"] == 1280 and normalized["height"] == 800
                      and normalized["transformation"] ==
                          "Pillow RGB lossless PNG re-encode; metadata stripped; no crop/resize/redaction"
                      and c.fullmatch(c.HEX64, normalized["pixel_sha256"]),
                      "dictation capture output binding differs")
            decoded = host._decode(output_path)
            c.require(hashlib.sha256(decoded.tobytes()).hexdigest() == normalized["pixel_sha256"],
                      "dictation capture pixel digest differs")
            c.privacy_text(bundle.tesseract_ocr(output_path, ocr_timeout), private_fragments)
    recovery = manifest["scenes"]["dictationrecovery"]["outputs"]
    c.require(recovery["gpu_failure"]["sha256"] != recovery["cpu_ready"]["sha256"],
              "dictation recovery normalized frames are byte-identical")
    return manifest


def _manifest_pin(path: Path):
    manifest = _read_json(path)
    c.require(type(manifest) is dict and manifest.get("image") == c.IMAGE,
              "showcase execution manifest image differs")
    return evidence_pin(manifest.get("dictation_evidence"))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    metadata = commands.add_parser("verify-metadata")
    metadata.add_argument("--manifest", type=Path, required=True)
    metadata.add_argument("--run-json", type=Path, required=True)
    metadata.add_argument("--artifact-json", type=Path, required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("--manifest", type=Path, required=True)
    extract.add_argument("--archive", type=Path, required=True)
    extract.add_argument("--output", type=Path, required=True)
    export_parser = commands.add_parser("export")
    export_parser.add_argument("--manifest", type=Path, required=True)
    export_parser.add_argument("--evidence", type=Path, required=True)
    export_parser.add_argument("--repository", type=Path, required=True)
    export_parser.add_argument("--output", type=Path, required=True)
    export_parser.add_argument("--archive", type=Path, required=True)
    export_parser.add_argument("--digest", type=Path, required=True)
    export_parser.add_argument("--ocr-timeout", type=int, default=60)
    validate_parser = commands.add_parser("validate")
    validate_parser.add_argument("--bundle", type=Path, required=True)
    validate_parser.add_argument("--archive", type=Path, required=True)
    validate_parser.add_argument("--digest", type=Path, required=True)
    validate_parser.add_argument("--ocr-timeout", type=int, default=60)
    args = parser.parse_args(argv)
    try:
        if args.command == "verify-metadata":
            pin = _manifest_pin(args.manifest)
            verify_metadata(pin, _read_json(args.run_json), _read_json(args.artifact_json))
        elif args.command == "extract":
            extract_archive(_manifest_pin(args.manifest), args.archive, args.output)
        elif args.command == "export":
            export(_manifest_pin(args.manifest), args.evidence, args.repository.resolve(),
                   args.output, args.archive, args.digest, args.ocr_timeout)
        else:
            validate(args.bundle, _read_json(args.digest), args.archive, args.ocr_timeout)
        return 0
    except (c.Invalid, OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as error:
        print("dictation capture bundle failed: " + str(error), file=os.sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
