#!/usr/bin/env python3
"""Verify and assemble two bounded River generations without adding a join gap.

Generated audio stays outside Git. Each source MP3 is checked against its immutable receipt,
decoded to the same 44.1 kHz mono PCM format, and concatenated at the exact sample boundary.
The single encoded MP3 is decoded again; it is accepted only when its sample count equals the
sum of the two inputs. The emitted candidate receipt supplies the exact fields that must be
reviewed and copied into ``direct_voxtype_revision.new_master`` before rendering can unblock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REVISION = Path(__file__).resolve().parent
SHOWCASE = REVISION.parent
REPOSITORY = SHOWCASE.parent
sys.path.insert(0, str(SHOWCASE))
from voice_receipt import SAFE_TAG, _generation, validate_segment_plan  # noqa: E402

SAMPLE_RATE = 44_100
CHANNELS = 1
SAMPLE_BYTES = 2


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def media_duration(path: Path) -> float:
    try:
        import av
    except ImportError as error:
        raise SystemExit("PyAV 16.0.1 is required; install showcase/requirements-voice.txt") from error
    with av.open(str(path)) as container:
        if container.duration is None:
            raise ValueError(f"audio container has no duration: {path.name}")
        return float(container.duration / av.time_base)


def decode_pcm(source: Path, destination: Path) -> int:
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(source),
        "-vn", "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE), "-f", "s16le",
        str(destination),
    ], check=True)
    size = destination.stat().st_size
    frame_bytes = CHANNELS * SAMPLE_BYTES
    if size == 0 or size % frame_bytes:
        raise ValueError(f"decoded PCM size is invalid: {source.name}")
    return size // frame_bytes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--audio-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--draft-release-tag", required=True)
    parser.add_argument("--output-receipt", type=Path)
    args = parser.parse_args()

    if not SAFE_TAG.fullmatch(args.draft_release_tag):
        raise SystemExit("draft release tag is invalid")
    data = json.loads(args.receipt.read_text())
    plan = validate_segment_plan(data, REPOSITORY)
    generations = [_generation(segment, index) for index, segment in enumerate(plan["segments"], 1)]

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="arctic-river-pcm-") as temporary:
        temporary = Path(temporary)
        pcm_paths: list[Path] = []
        sample_counts: list[int] = []
        for index, generation in enumerate(generations, 1):
            source = args.audio_dir / generation["asset"]
            if source.parent.resolve() != args.audio_dir.resolve():
                raise SystemExit(f"segment {index} audio path escapes the audio directory")
            if source.stat().st_size != generation["bytes"] or digest(source) != generation["sha256"]:
                raise SystemExit(f"segment {index} audio receipt mismatch")
            duration = media_duration(source)
            if abs(duration - generation["pyav_duration_seconds"]) > 0.001:
                raise SystemExit(f"segment {index} PyAV duration mismatch: {duration:.6f}")
            pcm = temporary / f"segment-{index:02}.s16le"
            samples = decode_pcm(source, pcm)
            if samples != generation["decoded_samples"]:
                raise SystemExit(f"segment {index} decoded sample count mismatch: {samples}")
            pcm_paths.append(pcm)
            sample_counts.append(samples)

        joined = temporary / "joined.s16le"
        with joined.open("wb") as destination:
            for pcm in pcm_paths:
                destination.write(pcm.read_bytes())
        expected_samples = sum(sample_counts)
        if joined.stat().st_size != expected_samples * CHANNELS * SAMPLE_BYTES:
            raise SystemExit("joined PCM byte count differs")

        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", str(CHANNELS),
            "-i", str(joined), "-c:a", "libmp3lame", "-b:a", "192k", str(args.output),
        ], check=True)
        decoded_master = temporary / "master.s16le"
        master_samples = decode_pcm(args.output, decoded_master)
        if master_samples != expected_samples:
            raise SystemExit(
                f"assembled MP3 is not sample-exact at the join: {master_samples} != {expected_samples}"
            )

    candidate = {
        "draft_release_tag": args.draft_release_tag,
        "asset": args.output.name,
        "bytes": args.output.stat().st_size,
        "sha256": digest(args.output),
        "pyav_duration_seconds": round(media_duration(args.output), 6),
        "decoded_sample_rate_hz": SAMPLE_RATE,
        "decoded_channels": CHANNELS,
        "decoded_samples": expected_samples,
        "segment_audio_sha256s": [item["sha256"] for item in generations],
    }
    pinned = data["direct_voxtype_revision"].get("new_master")
    if pinned is not None and pinned != candidate:
        raise SystemExit("assembled master differs from the pinned receipt")
    if args.output_receipt:
        args.output_receipt.write_text(json.dumps(candidate, indent=2) + "\n")
    print(json.dumps({
        "status": "verified_unpublished_segmented_master",
        "inserted_join_samples": 0,
        "segment_decoded_samples": sample_counts,
        "new_master": candidate,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
