#!/usr/bin/env python3
"""Fail-closed staging and public verification for the reviewed River video."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import quote

try:
    from .voice_receipt import resolve, resolve_publication
except ImportError:
    from voice_receipt import resolve, resolve_publication

REPOSITORY = Path(__file__).resolve().parent.parent
RECEIPT_PATH = "showcase/revision-2026-10-12/voice-timing.json"
RESOLVER_PATH = "showcase/revision-2026-10-12/resolve-voice.py"
RELEASE_TAG = "showcase-2026-10-16"
RELEASE_TITLE = "Arctic Linux 1.2.1 showcase"
REPOSITORY_SLUG = "yuvalkolodkingal/Arctic-Linux"
VIDEO_NAME = "Arctic-Linux-Showcase-River-1080p.mp4"
PUBLIC_NAMES = {
    f"renders/{VIDEO_NAME}": VIDEO_NAME,
    "captions.srt": "captions.srt",
    "captions.vtt": "captions.vtt",
    "chapters.txt": "chapters.txt",
}
FRAMES = {
    "frame-intro.png", "frame-files.png", "frame-dictationsetup.png",
    "frame-dictationrecord.png", "frame-dictationrecovery.png", "frame-winter.png",
    "frame-updates.png", "frame-outro.png",
}
EVIDENCE_NAMES = {
    "renders/validation/ffprobe.json",
    "renders/validation/muxed-captions.srt",
    "renders/validation/render-validation.json",
    "renders/validation/frames.tsv",
    "timing.json",
    "asset-provenance.json",
    "revision-2026-10-12/alignment-provenance.json",
    "revision-2026-10-12/voice-timing.json",
} | {f"renders/validation/{name}" for name in FRAMES}
EXPECTED_MEMBERS = set(PUBLIC_NAMES) | EVIDENCE_NAMES
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text())
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{label} is not readable JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def _safe_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    total = 0
    for info in archive.infolist():
        name = info.filename.rstrip("/")
        path = PurePosixPath(name)
        mode = info.external_attr >> 16
        if info.is_dir():
            continue
        if (
            not name or path.is_absolute() or ".." in path.parts or "\\" in name
            or stat.S_ISLNK(mode) or stat.S_IFMT(mode) not in (0, stat.S_IFREG)
            or name in members
        ):
            raise ValueError(f"unsafe or duplicate candidate member: {info.filename}")
        if info.file_size > 2_000_000_000 or info.compress_size > 2_000_000_000:
            raise ValueError(f"candidate member is unbounded: {name}")
        total += info.file_size
        if total > 2_200_000_000:
            raise ValueError("candidate expands beyond the publication limit")
        members[name] = info
    if set(members) != EXPECTED_MEMBERS:
        missing = sorted(EXPECTED_MEMBERS - set(members))
        extra = sorted(set(members) - EXPECTED_MEMBERS)
        raise ValueError(f"candidate member inventory differs (missing={missing}, extra={extra})")
    if any(name.lower().endswith(".mp3") for name in members):
        raise ValueError("candidate contains source MP3 audio")
    return members


def _extract(archive: zipfile.ZipFile, members: dict[str, zipfile.ZipInfo], root: Path) -> None:
    root.mkdir(parents=True, exist_ok=False)
    for name, info in members.items():
        target = root.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("xb") as output:
            shutil.copyfileobj(source, output, length=1024 * 1024)


def _png_dimensions(path: Path) -> tuple[int, int]:
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError(f"{path.name} is not a PNG")
    return struct.unpack(">II", header[16:24])


def _srt_texts(path: Path) -> list[str]:
    blocks = [block for block in re.split(r"\r?\n\s*\r?\n", path.read_text().strip()) if block]
    result = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            raise ValueError(f"invalid SRT cue in {path.name}")
        result.append("\n".join(lines[2:]))
    return result


def _vtt_texts(path: Path) -> list[str]:
    blocks = [block for block in re.split(r"\r?\n\s*\r?\n", path.read_text().strip()) if block]
    if not blocks or blocks[0].strip() != "WEBVTT":
        raise ValueError("captions.vtt has no WEBVTT header")
    result = []
    for block in blocks[1:]:
        lines = block.splitlines()
        timing = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timing is None or timing + 1 >= len(lines):
            raise ValueError("invalid VTT cue")
        result.append("\n".join(lines[timing + 1:]))
    return result


def _validate_live_artifact(artifact: dict, run: dict, review: dict) -> None:
    expected = review["render"]
    run_id = int(expected["workflow_run"].rsplit("/", 1)[1])
    if (
        artifact.get("id") != expected["artifact_id"]
        or artifact.get("name") != expected["artifact_name"]
        or artifact.get("size_in_bytes") != expected["archive_bytes"]
        or artifact.get("digest") != "sha256:" + expected["archive_sha256"]
        or artifact.get("expired") is not False
        or artifact.get("workflow_run", {}).get("id") != run_id
        or artifact.get("workflow_run", {}).get("head_sha") != expected["source_commit"]
    ):
        raise ValueError("live candidate artifact metadata differs from the reviewed receipt")
    if (
        run.get("id") != run_id or run.get("html_url") != expected["workflow_run"]
        or run.get("head_sha") != expected["source_commit"]
        or run.get("status") != "completed" or run.get("conclusion") != "success"
        or run.get("run_attempt") != 1
    ):
        raise ValueError("live render workflow run differs from the reviewed receipt")


def _validate_archived_receipt(archived_path: Path, current: dict, repository: Path) -> None:
    archived = load_json(archived_path, "archived render voice receipt")
    resolve(archived, repository)
    archived_comparable = json.loads(json.dumps(archived))
    current_comparable = json.loads(json.dumps(current))
    for value in (archived_comparable, current_comparable):
        value["license"].pop("publication_confirmation", None)
        validation = value["validation"]
        validation.pop("human_listening_review", None)
        validation.pop("final_render_verified", None)
        validation.pop("final_render_review", None)
    if archived_comparable != current_comparable:
        raise ValueError("archived render receipt differs outside post-render approval fields")


def stage_candidate(
    *, repository: Path, receipt_path: Path, artifact_path: Path,
    artifact_metadata_path: Path, run_metadata_path: Path, target_commit: str,
    stage: Path, invoke_resolver: bool = True,
) -> dict:
    if not HEX40.fullmatch(target_commit):
        raise ValueError("release target commit is invalid")
    if invoke_resolver:
        resolver = repository / RESOLVER_PATH
        subprocess.run(
            [sys.executable, str(resolver), "--receipt", str(receipt_path),
             "--purpose", "publish-video"],
            cwd=repository, check=True,
        )
    receipt = load_json(receipt_path, "voice receipt")
    admission = resolve_publication(receipt, repository, redistribute_source_audio=False)
    if admission != {
        **{key: admission[key] for key in ("source_tag", "master_asset", "master_bytes",
                                           "master_sha256", "master_duration")},
        "admission": "public_video",
        "publication_scope": admission["publication_scope"],
        "source_audio_redistribution": "false",
    }:
        raise ValueError("public video resolver output differs")
    if admission["publication_scope"] not in {
        "public_video", "public_video_and_source_audio_redistribution"
    }:
        raise ValueError("public video license scope is invalid")

    qualification = load_json(repository / "tools/qualified-release/manifest.json", "qualification manifest")
    if qualification.get("main_sha") != target_commit:
        raise ValueError("release target is not the qualified main commit")
    review = receipt["validation"]["final_render_review"]
    artifact = load_json(artifact_metadata_path, "artifact metadata")
    run = load_json(run_metadata_path, "workflow run metadata")
    _validate_live_artifact(artifact, run, review)
    if artifact_path.stat().st_size != review["render"]["archive_bytes"]:
        raise ValueError("candidate archive byte size differs from the reviewed receipt")
    if digest(artifact_path) != review["render"]["archive_sha256"]:
        raise ValueError("candidate archive digest differs from the reviewed receipt")

    extracted = stage.parent / (stage.name + "-candidate")
    if extracted.exists() or stage.exists():
        raise ValueError("publication staging paths must not already exist")
    with zipfile.ZipFile(artifact_path) as archive:
        members = _safe_members(archive)
        _extract(archive, members, extracted)

    video = extracted / f"renders/{VIDEO_NAME}"
    expected_video = review["video"]
    if video.stat().st_size != expected_video["bytes"] or digest(video) != expected_video["sha256"]:
        raise ValueError("candidate MP4 differs from the reviewed receipt")
    for name, expected in review["human_frame_review"]["frames"].items():
        frame = extracted / "renders/validation" / name
        if digest(frame) != expected or _png_dimensions(frame) != (1920, 1080):
            raise ValueError(f"reviewed representative frame differs: {name}")

    render = load_json(extracted / "renders/validation/render-validation.json", "render validation")
    if (
        render.get("source_commit") != review["source_commit"]
        or render.get("workflow_run") != review["render"]["workflow_run"]
        or render.get("published") is not False
        or render.get("full_decode_errors") != 0
        or render.get("video", {}).get("bytes") != expected_video["bytes"]
        or render.get("video", {}).get("sha256") != expected_video["sha256"]
        or abs(float(render.get("video", {}).get("duration_seconds", -1))
               - float(expected_video["duration_seconds"])) > 0.001
        or render.get("video", {}).get("subtitle_codec") != "mov_text"
        or render.get("video", {}).get("subtitle_cues") != 130
    ):
        raise ValueError("render validation does not reproduce the reviewed final render")

    exact_repository_files = {
        "captions.srt": "showcase/captions.srt",
        "captions.vtt": "showcase/captions.vtt",
        "chapters.txt": "showcase/chapters.txt",
        "timing.json": "showcase/timing.json",
        "asset-provenance.json": "showcase/asset-provenance.json",
        "revision-2026-10-12/alignment-provenance.json": "showcase/revision-2026-10-12/alignment-provenance.json",
    }
    for member, source in exact_repository_files.items():
        if (extracted / member).read_bytes() != (repository / source).read_bytes():
            raise ValueError(f"candidate file differs from reviewed source: {member}")
    _validate_archived_receipt(
        extracted / "revision-2026-10-12/voice-timing.json", receipt, repository
    )
    poster = repository / "showcase/poster.png"
    if not poster.is_file() or poster.is_symlink() or _png_dimensions(poster) != (1920, 1080):
        raise ValueError("showcase poster dimensions differ")
    source_cues = _srt_texts(extracted / "captions.srt")
    muxed_cues = _srt_texts(extracted / "renders/validation/muxed-captions.srt")
    vtt_cues = _vtt_texts(extracted / "captions.vtt")
    if len(source_cues) != 130 or source_cues != muxed_cues or source_cues != vtt_cues:
        raise ValueError("published and muxed caption text differs")
    if not (extracted / "chapters.txt").read_text().strip():
        raise ValueError("chapter file is empty")

    stage.mkdir(parents=True)
    assets = {}
    for source_name, public_name in PUBLIC_NAMES.items():
        source = extracted / source_name
        target = stage / public_name
        shutil.copyfile(source, target)
        assets[public_name] = {"bytes": target.stat().st_size, "sha256": digest(target)}
    public_poster = stage / "Arctic-Linux-Showcase-Poster.png"
    shutil.copyfile(poster, public_poster)
    assets[public_poster.name] = {
        "bytes": public_poster.stat().st_size, "sha256": digest(public_poster)
    }
    manifest = {
        "schema": 1,
        "repository": REPOSITORY_SLUG,
        "tag": RELEASE_TAG,
        "title": RELEASE_TITLE,
        "target_commit": target_commit,
        "source_audio_included": False,
        "render_workflow_run": review["render"]["workflow_run"],
        "candidate_archive_sha256": review["render"]["archive_sha256"],
        "video_reviewed_sha256": expected_video["sha256"],
        "assets": assets,
    }
    (stage / "publication-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    shutil.rmtree(extracted)
    return manifest


def verify_downloaded(manifest_path: Path, downloaded: Path) -> None:
    manifest = load_json(manifest_path, "publication manifest")
    expected = manifest["assets"]
    if {path.name for path in downloaded.iterdir()} != set(expected):
        raise ValueError("downloaded public asset inventory differs")
    for name, identity in expected.items():
        path = downloaded / name
        if not path.is_file() or path.is_symlink():
            raise ValueError(f"downloaded public asset is missing: {name}")
        if path.stat().st_size != identity["bytes"] or digest(path) != identity["sha256"]:
            raise ValueError(f"downloaded public asset differs: {name}")


def verify_release(release_path: Path, manifest_path: Path, downloaded: Path) -> None:
    release = load_json(release_path, "release metadata")
    manifest = load_json(manifest_path, "publication manifest")
    if (
        release.get("tagName") != manifest["tag"]
        or release.get("isDraft") is not False
        or release.get("isPrerelease") is not False
        or release.get("targetCommitish") != manifest["target_commit"]
    ):
        raise ValueError("public release identity differs")
    expected = manifest["assets"]
    assets = release.get("assets")
    if not isinstance(assets, list) or {item.get("name") for item in assets} != set(expected):
        raise ValueError("public release asset inventory differs")
    base = f"https://github.com/{manifest['repository']}/releases/download/{quote(manifest['tag'])}/"
    for item in assets:
        name = item["name"]
        expected_url = base + quote(name)
        if item.get("size") != expected[name]["bytes"] or item.get("url") != expected_url:
            raise ValueError(f"public release metadata differs: {name}")
    verify_downloaded(manifest_path, downloaded)


def fetch_urls(release_path: Path, manifest_path: Path, output: Path) -> None:
    release = load_json(release_path, "release metadata")
    manifest = load_json(manifest_path, "publication manifest")
    assets = release.get("assets")
    if not isinstance(assets, list) or {item.get("name") for item in assets} != set(manifest["assets"]):
        raise ValueError("public release asset inventory differs before URL download")
    output.mkdir(parents=True, exist_ok=False)
    for item in assets:
        name = item["name"]
        with urllib.request.urlopen(item["url"], timeout=120) as source, (output / name).open("xb") as target:
            if source.status != 200:
                raise ValueError(f"public asset URL returned HTTP {source.status}: {name}")
            shutil.copyfileobj(source, target, length=1024 * 1024)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    stage = subparsers.add_parser("stage")
    stage.add_argument("--repository", type=Path, default=REPOSITORY)
    stage.add_argument("--receipt", type=Path, required=True)
    stage.add_argument("--artifact", type=Path, required=True)
    stage.add_argument("--artifact-metadata", type=Path, required=True)
    stage.add_argument("--run-metadata", type=Path, required=True)
    stage.add_argument("--target-commit", required=True)
    stage.add_argument("--output", type=Path, required=True)
    verify = subparsers.add_parser("verify-release")
    verify.add_argument("--release", type=Path, required=True)
    verify.add_argument("--manifest", type=Path, required=True)
    verify.add_argument("--downloaded", type=Path, required=True)
    files = subparsers.add_parser("verify-files")
    files.add_argument("--manifest", type=Path, required=True)
    files.add_argument("--downloaded", type=Path, required=True)
    fetch = subparsers.add_parser("fetch-urls")
    fetch.add_argument("--release", type=Path, required=True)
    fetch.add_argument("--manifest", type=Path, required=True)
    fetch.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "stage":
            result = stage_candidate(
                repository=args.repository.resolve(), receipt_path=args.receipt.resolve(),
                artifact_path=args.artifact.resolve(),
                artifact_metadata_path=args.artifact_metadata.resolve(),
                run_metadata_path=args.run_metadata.resolve(), target_commit=args.target_commit,
                stage=args.output.resolve(),
            )
            print(json.dumps(result, sort_keys=True))
        elif args.command == "verify-release":
            verify_release(args.release, args.manifest, args.downloaded)
            print("public release assets verified")
        elif args.command == "verify-files":
            verify_downloaded(args.manifest, args.downloaded)
            print("release asset files verified")
        else:
            fetch_urls(args.release, args.manifest, args.output)
            print("public release asset URLs downloaded")
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.CalledProcessError) as error:
        raise SystemExit(f"showcase publication blocked: {error}") from error


if __name__ == "__main__":
    main()
