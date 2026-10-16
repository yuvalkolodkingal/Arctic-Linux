#!/usr/bin/env python3
"""Export a fixed, screened subset of exact qualification media to a draft release."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import resource
import stat
import struct
import subprocess
import tempfile
import zipfile
import zlib

from PIL import Image, UnidentifiedImageError


ROOT = Path(__file__).resolve().parents[2]
REPOSITORY = "yuvalkolodkingal/Arctic-Linux"
REPOSITORY_ID = 1390608717
SOURCE_BRANCH = "codex/private-media-review-exporter-20261016"
WORKFLOW = ".github/workflows/private-media-review-export-20261016.yml"
MARKER = ".github/private-media-review-export-20261016.activate"
MANIFEST = "tools/private-media-review/manifest.json"
SCHEMA = "arctic-private-qualification-media-review-v1"
REVIEW_SCHEMA = "arctic-private-qualification-media-review-result-v1"

BOUNDS = {
    "max_artifacts": 8,
    "max_archive_bytes_each": 250_000_000,
    "max_total_archive_bytes": 900_000_000,
    "max_zip_members_each": 50_000,
    "max_member_bytes": 128_000_000,
    "max_uncompressed_bytes_each": 750_000_000,
    "max_exports": 256,
    "max_png_bytes": 32_000_000,
    "max_png_pixels": 16_777_216,
    "max_total_export_bytes": 250_000_000,
    "max_ocr_bytes": 1_000_000,
}

ALLOWED_WORKFLOWS = {
    ".github/workflows/installer-candidate-20261009.yml": "installer-idle",
    ".github/workflows/installer-active-candidate-20261009.yml": "installer-active",
    ".github/workflows/native-candidate-20261008.yml": "native",
    ".github/workflows/dictation-candidate-20261009.yml": "dictation",
    ".github/workflows/showcase-exact-capture-20261014.yml": "showcase",
}
ALLOWED_ARCHIVE_SUFFIXES = {".bin", ".json", ".log", ".png", ".rgb", ".txt", ".tsv", ".wav"}
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
SAFE_ARTIFACT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._ +()-]{0,199}")
SAFE_ASSET_NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,199}")
SENSITIVE_OCR = re.compile(
    r"(?i)(?:gh[pousr]_|github_pat_)[a-z0-9_]+"
    r"|AKIA[A-Z0-9]{16}"
    r"|authorization[ \t]*:[ \t]*\S+"
    r"|[\w.+-]+@[\w.-]+\.[a-z]{2,}"
    r"|https?://\S*\?\S+"
    r"|(?:password|passwd|token|access[_ -]?token|api[_ -]?key|client[_ -]?secret|secret)[ \t]*[:=][ \t]*\S+"
    r"|(?:transcript|transcription|recognized[ \t]+text|dictation[ \t]+(?:text|result)|תמלול|תמליל)[ \t]*[:=]"
)
PNG_CHUNKS = {b"IHDR", b"IDAT", b"IEND"}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def strict_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(type(key) is str and key not in result, "Duplicate or invalid JSON field")
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest_file(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def git(*args):
    return subprocess.check_output(["git", "-C", str(ROOT), *args], text=True,
                                   timeout=120).strip()


def safe_member(name):
    require(type(name) is str and name and "\x00" not in name and "\\" not in name,
            "Unsafe archive member name")
    path = PurePosixPath(name)
    require(not path.is_absolute() and all(part not in ("", ".", "..") for part in path.parts),
            "Unsafe archive member path")
    require(path.suffix.lower() in ALLOWED_ARCHIVE_SUFFIXES, "Archive member type is not approved")
    return path


def safe_asset(name, suffix=None):
    require(type(name) is str and SAFE_ASSET_NAME.fullmatch(name), "Unsafe draft asset name")
    if suffix is not None:
        require(name.endswith(suffix), "Draft asset type differs")
    return name


def validate_manifest(value, require_ready=True):
    fields = {"schema", "ready", "review_only", "repository", "repository_id",
              "source_branch", "bounds", "draft_release", "artifacts"}
    require(type(value) is dict and set(value) == fields, "Private review manifest fields differ")
    require(value["schema"] == SCHEMA and value["review_only"] is True
            and value["repository"] == REPOSITORY and value["repository_id"] == REPOSITORY_ID
            and value["source_branch"] == SOURCE_BRANCH and value["bounds"] == BOUNDS,
            "Private review manifest identity or bounds differ")
    release = value["draft_release"]
    require(type(release) is dict and set(release) == {
        "tag", "name", "draft", "prerelease", "public", "human_review", "release_acceptance"
    }, "Draft release fields differ")
    require(type(release["tag"]) is str and re.fullmatch(r"private-qualification-review-[0-9]{8}", release["tag"])
            and type(release["name"]) is str and 1 <= len(release["name"]) <= 120
            and release["draft"] is True and release["prerelease"] is False
            and release["public"] is False and release["human_review"] == "pending"
            and release["release_acceptance"] is False,
            "Review destination is not a private pending draft")
    require(type(value["ready"]) is bool and type(value["artifacts"]) is list,
            "Private review readiness is malformed")
    if not value["ready"]:
        require(not value["artifacts"] and not require_ready, "Private review export is disabled")
        return value
    require(1 <= len(value["artifacts"]) <= BOUNDS["max_artifacts"],
            "Private review artifact count is invalid")
    artifact_fields = {"lane", "run_id", "run_attempt", "head_sha", "head_branch",
                       "workflow_id", "workflow_name", "workflow_path", "event",
                       "artifact_id", "artifact_name", "archive_bytes", "archive_sha256",
                       "screening_inventory", "screening_scope", "archive_members", "exports"}
    export_fields = {"member", "asset_name", "kind", "privacy_class", "max_bytes",
                     "width", "height", "ocr_languages"}
    ids, lanes, assets = set(), set(), {"REVIEW-MANIFEST.json"}
    total_archives = total_exports = export_budget = 0
    for artifact in value["artifacts"]:
        require(type(artifact) is dict and set(artifact) == artifact_fields,
                "Artifact declaration fields differ")
        expected_lane = ALLOWED_WORKFLOWS.get(artifact["workflow_path"])
        require(expected_lane == artifact["lane"] and artifact["lane"] not in lanes,
                "Qualification lane is not approved or is duplicated")
        lanes.add(artifact["lane"])
        require(type(artifact["run_id"]) is int and artifact["run_id"] > 0
                and type(artifact["run_attempt"]) is int and artifact["run_attempt"] > 0
                and type(artifact["artifact_id"]) is int and artifact["artifact_id"] > 0
                and artifact["artifact_id"] not in ids, "Pinned run or artifact ID is invalid")
        ids.add(artifact["artifact_id"])
        require(type(artifact["head_sha"]) is str and HEX40.fullmatch(artifact["head_sha"])
                and type(artifact["head_branch"]) is str
                and re.fullmatch(r"codex/[a-z0-9][a-z0-9._/-]{0,199}", artifact["head_branch"]),
                "Pinned source identity is invalid")
        require(type(artifact["workflow_id"]) is int and artifact["workflow_id"] > 0
                and type(artifact["workflow_name"]) is str and 1 <= len(artifact["workflow_name"]) <= 200
                and artifact["event"] == "push", "Pinned workflow identity is invalid")
        require(type(artifact["artifact_name"]) is str
                and SAFE_ARTIFACT_NAME.fullmatch(artifact["artifact_name"]),
                "Pinned artifact name is invalid")
        require(type(artifact["archive_bytes"]) is int
                and 0 < artifact["archive_bytes"] <= BOUNDS["max_archive_bytes_each"]
                and type(artifact["archive_sha256"]) is str
                and HEX64.fullmatch(artifact["archive_sha256"]), "Pinned archive identity is invalid")
        inventory = safe_member(artifact["screening_inventory"])
        require(inventory.suffix == ".json" and type(artifact["screening_scope"]) is str
                and 1 <= len(artifact["screening_scope"]) <= 500,
                "Producer screening declaration is invalid")
        require(type(artifact["archive_members"]) is list
                and 1 <= len(artifact["archive_members"]) <= BOUNDS["max_zip_members_each"],
                "Archive schema is invalid")
        members = set()
        for member in artifact["archive_members"]:
            safe_member(member)
            require(member not in members, "Archive schema contains duplicate members")
            members.add(member)
        require(artifact["screening_inventory"] in members, "Screening inventory is absent from schema")
        require(type(artifact["exports"]) is list and artifact["exports"],
                "Artifact has no declared review exports")
        selected = set()
        for item in artifact["exports"]:
            require(type(item) is dict and set(item) == export_fields
                    and item["kind"] == "png" and item["privacy_class"] == "screened-synthetic-vm-ui",
                    "Review export is not an approved PNG class")
            member = safe_member(item["member"])
            asset = safe_asset(item["asset_name"], ".png")
            require(member.suffix == ".png" and item["member"] in members
                    and item["member"] not in selected and asset not in assets,
                    "Review PNG member or asset is invalid or duplicated")
            selected.add(item["member"]); assets.add(asset)
            require(type(item["max_bytes"]) is int and 0 < item["max_bytes"] <= BOUNDS["max_png_bytes"]
                    and type(item["width"]) is int and type(item["height"]) is int
                    and 1 <= item["width"] <= 4096 and 1 <= item["height"] <= 4096
                    and item["width"] * item["height"] <= BOUNDS["max_png_pixels"],
                    "Review PNG bounds are invalid")
            require(item["ocr_languages"] == "eng+heb", "Review PNG OCR languages differ")
            total_exports += 1; export_budget += item["max_bytes"]
        total_archives += artifact["archive_bytes"]
    require(total_archives <= BOUNDS["max_total_archive_bytes"], "Total archive byte bound exceeded")
    require(total_exports <= BOUNDS["max_exports"], "Review export count bound exceeded")
    require(export_budget <= BOUNDS["max_total_export_bytes"], "Review export byte bound exceeded")
    return value


def validate_activation(manifest_path):
    require(os.environ.get("GITHUB_ACTIONS") == "true"
            and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
            and os.environ.get("GITHUB_REPOSITORY") == REPOSITORY
            and os.environ.get("GITHUB_REF") == "refs/heads/" + SOURCE_BRANCH
            and os.environ.get("GITHUB_EVENT_NAME") == "push"
            and os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "Requires the dedicated first-attempt GitHub-hosted private review lane")
    event = strict_json(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
    preparation = (ROOT / MARKER).read_text().strip()
    activation = git("rev-parse", "HEAD")
    require(HEX40.fullmatch(preparation) and event.get("before") == preparation
            and event.get("after") == os.environ.get("GITHUB_SHA") == activation
            and git("rev-list", "--parents", "-n", "1", "HEAD").split() == [activation, preparation]
            and git("diff", "--no-renames", "--name-only", preparation, activation).splitlines() == [MARKER]
            and not git("status", "--porcelain"),
            "Private review activation is not the reviewed marker-only child")
    manifest = validate_manifest(strict_json(Path(manifest_path).read_text()))
    return manifest, preparation, activation


def fetch_json(endpoint):
    raw = subprocess.check_output(["gh", "api", endpoint], timeout=120)
    return strict_json(raw.decode())


def verify_remote_identity(artifact, metadata, run):
    require(type(metadata) is dict and metadata.get("id") == artifact["artifact_id"]
            and metadata.get("name") == artifact["artifact_name"]
            and metadata.get("expired") is False
            and metadata.get("size_in_bytes") == artifact["archive_bytes"]
            and metadata.get("digest") == "sha256:" + artifact["archive_sha256"],
            "Remote artifact identity differs from its pin")
    link = metadata.get("workflow_run")
    require(type(link) is dict and link.get("id") == artifact["run_id"]
            and link.get("repository_id") == REPOSITORY_ID
            and link.get("head_repository_id") == REPOSITORY_ID
            and link.get("head_sha") == artifact["head_sha"]
            and link.get("head_branch") == artifact["head_branch"],
            "Artifact workflow-run identity differs from its pin")
    require(type(run) is dict and run.get("id") == artifact["run_id"]
            and run.get("run_attempt") == artifact["run_attempt"]
            and run.get("head_sha") == artifact["head_sha"]
            and run.get("head_branch") == artifact["head_branch"]
            and run.get("workflow_id") == artifact["workflow_id"]
            and run.get("name") == artifact["workflow_name"]
            and run.get("path") == artifact["workflow_path"]
            and run.get("event") == artifact["event"]
            and run.get("status") == "completed" and run.get("conclusion") == "success"
            and run.get("repository", {}).get("id") == REPOSITORY_ID
            and run.get("head_repository", {}).get("id") == REPOSITORY_ID,
            "Qualification run is not the pinned successful repository workflow")


def download_archive(artifact, destination):
    expected = artifact["archive_bytes"]
    def limit_output_size():
        resource.setrlimit(resource.RLIMIT_FSIZE, (expected + 1, expected + 1))
    with Path(destination).open("xb") as stream:
        subprocess.run(["gh", "api",
                        f"repos/{REPOSITORY}/actions/artifacts/{artifact['artifact_id']}/zip"],
                       stdout=stream, check=True, timeout=1200, preexec_fn=limit_output_size)
    require(Path(destination).stat().st_size == expected
            and digest_file(destination) == artifact["archive_sha256"],
            "Downloaded artifact archive differs from its exact pin")


def inspect_png(raw, expected_width, expected_height):
    require(raw.startswith(b"\x89PNG\r\n\x1a\n"), "Review image is not PNG")
    offset, chunks, saw_iend = 8, [], False
    while offset < len(raw):
        require(offset + 12 <= len(raw), "PNG chunk is truncated")
        size = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        end = offset + 12 + size
        require(kind in PNG_CHUNKS and end <= len(raw), "PNG contains metadata or unknown chunks")
        payload = raw[offset + 8:offset + 8 + size]
        crc = struct.unpack(">I", raw[offset + 8 + size:end])[0]
        require(zlib.crc32(kind + payload) & 0xffffffff == crc, "PNG chunk checksum differs")
        chunks.append(kind)
        offset = end
        if kind == b"IEND":
            require(size == 0 and offset == len(raw), "PNG has trailing bytes")
            saw_iend = True
            break
    require(saw_iend and chunks[0] == b"IHDR" and chunks[-1] == b"IEND"
            and chunks.count(b"IHDR") == 1 and chunks.count(b"IEND") == 1
            and b"IDAT" in chunks, "PNG chunk order is invalid")
    Image.MAX_IMAGE_PIXELS = BOUNDS["max_png_pixels"]
    try:
        with Image.open(io.BytesIO(raw)) as image:
            require(not image.info and image.format == "PNG"
                    and image.size == (expected_width, expected_height),
                    "PNG identity, dimensions or metadata differ")
            image.verify()
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            require(image.mode in ("RGB", "RGBA"), "PNG color mode is not approved")
    except (UnidentifiedImageError, OSError, SyntaxError) as error:
        raise RuntimeError("Review image cannot be decoded") from error


def screen_png_ocr(raw, languages):
    result = subprocess.run(["tesseract", "stdin", "stdout", "-l", languages, "--psm", "6"],
                            input=raw, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            timeout=45, check=False)
    require(result.returncode == 0 and len(result.stdout) <= BOUNDS["max_ocr_bytes"],
            "Bounded PNG OCR failed")
    try:
        text = result.stdout.decode("utf-8")
    except UnicodeDecodeError as error:
        raise RuntimeError("PNG OCR is not UTF-8") from error
    for line in text.splitlines():
        # The active-installer lane deliberately reviews a real getty password
        # prompt. A cursor-only prompt contains no entered value; keep this
        # exact line reviewable without granting a general password exception.
        if line in ("Password: _", "Password: |"):
            continue
        require(SENSITIVE_OCR.search(line) is None,
                "Sensitive text shape detected in review PNG")


def validate_zip_info(info):
    name = info.filename.rstrip("/") if info.is_dir() else info.filename
    safe_member(name)
    mode = (info.external_attr >> 16) & 0o170000
    require(mode in (0, stat.S_IFREG, stat.S_IFDIR), "Archive contains a special member")
    require(not info.flag_bits & 0x1, "Encrypted archive members are forbidden")
    require(info.compress_type in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED),
            "Archive compression method is not approved")
    require(0 <= info.file_size <= BOUNDS["max_member_bytes"], "Archive member byte bound exceeded")
    if info.is_dir():
        require(info.file_size == 0, "Archive directory has content")
    elif info.file_size:
        require(info.compress_size > 0 and info.file_size <= max(1024, info.compress_size * 200),
                "Archive member expansion ratio exceeded")
    return name


def read_inventory(archive, artifact, infos):
    member = artifact["screening_inventory"]
    info = infos[member]
    require(not info.is_dir() and 0 < info.file_size <= 16_000_000,
            "Producer screening inventory size is invalid")
    value = strict_json(archive.read(info).decode("utf-8"))
    require(type(value) is dict and set(value).issubset({"scope", "files", "rejected_files", "source_formats"})
            and set(value) >= {"scope", "files"} and value["scope"] == artifact["screening_scope"]
            and type(value["files"]) is dict,
            "Producer screening inventory schema or scope differs")
    require(set(value["files"]) == set(infos) - {member},
            "Producer screening inventory does not cover the exact archive")
    for name, record in value["files"].items():
        require(type(record) is dict and set(record) == {
            "original_sha256", "uploaded_sha256", "bytes", "redactions"
        } and type(record["bytes"]) is int and record["bytes"] == infos[name].file_size
                and type(record["redactions"]) is int and record["redactions"] == 0
                and type(record["original_sha256"]) is str and HEX64.fullmatch(record["original_sha256"])
                and record["original_sha256"] == record["uploaded_sha256"],
                "Producer screening record is not exact and unredacted")
    return value["files"]


def extract_artifact(artifact, archive_path, output):
    require(archive_path.stat().st_size == artifact["archive_bytes"]
            and digest_file(archive_path) == artifact["archive_sha256"],
            "Local artifact archive differs from its pin")
    records, exported_bytes = [], 0
    with zipfile.ZipFile(archive_path) as archive:
        listed = archive.infolist()
        require(len(listed) <= BOUNDS["max_zip_members_each"], "Archive member bound exceeded")
        infos, total = {}, 0
        for info in listed:
            name = validate_zip_info(info)
            require(name not in infos, "Archive contains duplicate members")
            infos[name] = info; total += info.file_size
        require(set(infos) == set(artifact["archive_members"]), "Archive schema differs from its pin")
        require(total <= BOUNDS["max_uncompressed_bytes_each"], "Archive expansion bound exceeded")
        screening = read_inventory(archive, artifact, infos)
        # Stream every member. This verifies every CRC before selected media is exported.
        observed = {}
        for name, info in infos.items():
            digest = hashlib.sha256(); count = 0
            with archive.open(info) as stream:
                while block := stream.read(1024 * 1024):
                    count += len(block); digest.update(block)
            require(count == info.file_size, "Archive member is truncated")
            observed[name] = digest.hexdigest()
            if name != artifact["screening_inventory"]:
                require(screening[name]["uploaded_sha256"] == observed[name],
                        "Archive member differs from producer screening inventory")
        for item in artifact["exports"]:
            raw = archive.read(infos[item["member"]])
            require(0 < len(raw) <= item["max_bytes"], "Review PNG exceeds its byte bound")
            inspect_png(raw, item["width"], item["height"])
            screen_png_ocr(raw, item["ocr_languages"])
            destination = output / item["asset_name"]
            with destination.open("xb") as stream:
                stream.write(raw)
            destination.chmod(0o600)
            record = {
                "artifact_id": artifact["artifact_id"], "asset_name": item["asset_name"],
                "bytes": len(raw), "height": item["height"], "kind": "png",
                "lane": artifact["lane"], "member": item["member"],
                "privacy_class": item["privacy_class"], "sha256": digest_bytes(raw),
                "width": item["width"],
                "screening": ["producer-inventory-exact", "png-metadata-absent",
                              "ocr-sensitive-shapes-absent"],
            }
            records.append(dict(sorted(record.items()))); exported_bytes += len(raw)
    return records, exported_bytes


def export(manifest_path, output):
    manifest, preparation, activation = validate_activation(manifest_path)
    output = Path(output)
    require(not output.exists() and not output.is_symlink(), "Private review output already exists")
    output.mkdir(mode=0o700)
    all_records, archive_records, total = [], [], 0
    try:
        with tempfile.TemporaryDirectory(prefix="arctic-private-media-", dir=os.environ.get("RUNNER_TEMP")) as temp:
            private = Path(temp); private.chmod(0o700)
            for artifact in manifest["artifacts"]:
                metadata = fetch_json(f"repos/{REPOSITORY}/actions/artifacts/{artifact['artifact_id']}")
                run = fetch_json(f"repos/{REPOSITORY}/actions/runs/{artifact['run_id']}")
                verify_remote_identity(artifact, metadata, run)
                archive = private / f"{artifact['artifact_id']}.zip"
                download_archive(artifact, archive); archive.chmod(0o600)
                records, exported = extract_artifact(artifact, archive, output)
                all_records.extend(records); total += exported
                archive_records.append({
                    "archive_bytes": artifact["archive_bytes"],
                    "archive_sha256": artifact["archive_sha256"],
                    "artifact_id": artifact["artifact_id"], "artifact_name": artifact["artifact_name"],
                    "head_sha": artifact["head_sha"], "lane": artifact["lane"],
                    "run_attempt": artifact["run_attempt"], "run_id": artifact["run_id"],
                    "workflow_id": artifact["workflow_id"], "workflow_path": artifact["workflow_path"],
                })
        require(total <= BOUNDS["max_total_export_bytes"], "Exported review bytes exceed bound")
        result = {
            "schema": REVIEW_SCHEMA, "review_only": True, "release_acceptance": False,
            "human_review": "pending", "repository": REPOSITORY,
            "preparation_sha": preparation, "activation_sha": activation,
            "draft_release": manifest["draft_release"], "artifacts": archive_records,
            "assets": all_records, "asset_count": len(all_records) + 1,
            "png_count": len(all_records), "png_bytes": total,
            "privacy": {"audio_exported": False, "logs_exported": False,
                        "transcripts_exported": False, "raw_archives_exported": False},
        }
        review = output / "REVIEW-MANIFEST.json"
        review.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        review.chmod(0o600)
        require(set(path.name for path in output.iterdir()) ==
                {item["asset_name"] for item in all_records} | {"REVIEW-MANIFEST.json"},
                "Private review output contains undeclared assets")
        return result
    except BaseException:
        for path in output.iterdir():
            if path.is_file() and not path.is_symlink():
                path.unlink()
        output.rmdir()
        raise


def bundle_review(output, bundle, github_output):
    """Create the sole hash-bound handoff to the write-capable publication job."""
    output, bundle = Path(output), Path(bundle)
    require(output.is_dir() and not output.is_symlink()
            and not bundle.exists() and not bundle.is_symlink(), "Screened bundle paths are invalid")
    review_path = output / "REVIEW-MANIFEST.json"
    result = strict_json(review_path.read_text())
    require(result.get("schema") == REVIEW_SCHEMA and result.get("human_review") == "pending"
            and result.get("release_acceptance") is False and result.get("review_only") is True,
            "Screened result is not a pending review object")
    expected = {item["asset_name"]: (item["bytes"], item["sha256"])
                for item in result.get("assets", [])}
    require(len(expected) == len(result.get("assets", [])), "Screened assets are duplicated")
    expected[review_path.name] = (review_path.stat().st_size, digest_file(review_path))
    require(set(path.name for path in output.iterdir()) == set(expected),
            "Screened directory contains undeclared assets")
    with zipfile.ZipFile(bundle, "x", compression=zipfile.ZIP_STORED, allowZip64=False) as archive:
        for name in sorted(expected):
            if name == review_path.name:
                require(name == "REVIEW-MANIFEST.json", "Review manifest asset name differs")
            else:
                safe_asset(name, ".png")
            path = output / name
            require(path.is_file() and not path.is_symlink()
                    and path.stat().st_size == expected[name][0]
                    and digest_file(path) == expected[name][1],
                    "Screened asset differs before bundling")
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, path.read_bytes())
    require(0 < bundle.stat().st_size <= BOUNDS["max_total_export_bytes"] + 2_000_000,
            "Screened bundle byte bound exceeded")
    digest = digest_file(bundle)
    with Path(github_output).open("a") as stream:
        stream.write(f"bundle_sha256={digest}\nbundle_bytes={bundle.stat().st_size}\n")
    return digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-manifest")
    validate.add_argument("--manifest", type=Path, required=True)
    export_parser = sub.add_parser("export")
    export_parser.add_argument("--manifest", type=Path, required=True)
    export_parser.add_argument("--out", type=Path, required=True)
    bundle = sub.add_parser("bundle")
    bundle.add_argument("--input", type=Path, required=True)
    bundle.add_argument("--out", type=Path, required=True)
    bundle.add_argument("--github-output", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "validate-manifest":
        validate_manifest(strict_json(args.manifest.read_text()))
    elif args.command == "export":
        export(args.manifest, args.out)
    else:
        bundle_review(args.input, args.out, args.github_output)


if __name__ == "__main__":
    main()
