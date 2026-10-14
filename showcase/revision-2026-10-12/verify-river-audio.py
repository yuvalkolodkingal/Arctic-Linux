#!/usr/bin/env python3
"""Measure the pinned River master without making a subjective listening claim."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from pathlib import Path

import av
import numpy as np

REV = Path(__file__).resolve().parent
SHOWCASE = REV.parent
sys.path.insert(0, str(SHOWCASE))
from voice_receipt import validate_assembled_master, validate_segment_plan  # noqa: E402


def run_ffmpeg(audio: Path, *arguments: str) -> str:
    environment = {**os.environ, "LC_ALL": "C"}
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-nostats", "-i", str(audio), *arguments],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        env=environment,
    )
    return result.stderr


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_text())
    master = validate_assembled_master(receipt, SHOWCASE.parent)
    plan = validate_segment_plan(receipt, SHOWCASE.parent)
    if args.audio.is_symlink() or not args.audio.is_file():
        raise SystemExit("River master must be a regular file")
    if args.audio.stat().st_size != int(master["master_bytes"]):
        raise SystemExit("River master size does not match its receipt")
    if hashlib.sha256(args.audio.read_bytes()).hexdigest() != master["master_sha256"]:
        raise SystemExit("River master SHA-256 does not match its receipt")

    chunks: list[np.ndarray] = []
    with av.open(str(args.audio)) as container:
        stream = next(item for item in container.streams if item.type == "audio")
        codec = stream.codec_context.name
        sample_rate = stream.codec_context.sample_rate
        channels = stream.codec_context.channels
        for frame in container.decode(stream):
            samples = frame.to_ndarray()
            if samples.ndim == 2:
                samples = samples[0]
            if np.issubdtype(samples.dtype, np.integer):
                samples = samples.astype(np.float64) / max(abs(np.iinfo(samples.dtype).min), np.iinfo(samples.dtype).max)
            else:
                samples = samples.astype(np.float64, copy=False)
            chunks.append(samples)
    decoded = np.concatenate(chunks)

    expected_samples = receipt["direct_voxtype_revision"]["new_master"]["decoded_samples"]
    if sample_rate != 44_100 or channels != 1 or len(decoded) != expected_samples:
        raise SystemExit("decoded River master shape does not match its receipt")
    join = plan["segments"][0]["generation"]["decoded_samples"]
    window = sample_rate // 4
    around_join = decoded[join - window:join + window]
    adjacent_steps = np.abs(np.diff(around_join))
    boundary_step = float(abs(decoded[join] - decoded[join - 1]))
    largest_step = float(np.max(adjacent_steps))

    threshold = 10 ** (-60 / 20)
    left = join
    while left > 0 and abs(decoded[left - 1]) < threshold:
        left -= 1
    right = join
    while right < len(decoded) and abs(decoded[right]) < threshold:
        right += 1

    # A complete null decode catches demuxer/decoder failures. EBU R128 supplies level metrics.
    run_ffmpeg(args.audio, "-loglevel", "error", "-f", "null", "-")
    loudness_log = run_ffmpeg(args.audio, "-filter_complex", "ebur128=peak=true", "-f", "null", "-")
    integrated = re.findall(r"Integrated loudness:\s+I:\s+(-?[0-9.]+) LUFS", loudness_log)
    loudness_range = re.findall(r"Loudness range:\s+LRA:\s+([0-9.]+) LU", loudness_log)
    true_peak = re.findall(r"True peak:\s+Peak:\s+(-?[0-9.]+) dBFS", loudness_log)
    if not (integrated and loudness_range and true_peak):
        raise SystemExit("could not parse FFmpeg EBU R128 summary")

    peak = float(np.max(np.abs(decoded)))
    rms = float(np.sqrt(np.mean(decoded * decoded)))
    pre = decoded[join - window:join]
    post = decoded[join:join + window]
    report = {
        "full_ffmpeg_decode_errors": 0,
        "codec": codec,
        "sample_rate_hz": sample_rate,
        "channels": channels,
        "decoded_samples": int(len(decoded)),
        "decoded_duration_seconds": round(len(decoded) / sample_rate, 6),
        "integrated_loudness_lufs": float(integrated[-1]),
        "loudness_range_lu": float(loudness_range[-1]),
        "true_peak_dbfs": float(true_peak[-1]),
        "sample_peak_dbfs": round(20 * math.log10(peak), 3),
        "rms_dbfs": round(20 * math.log10(rms), 3),
        "dc_offset": round(float(np.mean(decoded)), 12),
        "hard_clipped_samples_ge_0_999": int(np.sum(np.abs(decoded) >= 0.999)),
        "join": {
            "join_sample_index": join,
            "join_seconds": round(join / sample_rate, 6),
            "join_boundary_sample_delta": round(boundary_step, 9),
            "join_window_max_adjacent_delta": round(largest_step, 9),
            "join_boundary_delta_fraction_of_window_max": round(boundary_step / largest_step, 6),
            "join_pre_250ms_rms_dbfs": round(20 * math.log10(max(float(np.sqrt(np.mean(pre * pre))), 1e-15)), 3),
            "join_post_250ms_rms_dbfs": round(20 * math.log10(max(float(np.sqrt(np.mean(post * post))), 1e-15)), 3),
            "join_contiguous_below_minus_60_dbfs_seconds": round((right - left) / sample_rate, 6),
            "join_contiguous_below_minus_60_dbfs_start_seconds": round(left / sample_rate, 6),
            "join_contiguous_below_minus_60_dbfs_end_seconds": round(right / sample_rate, 6),
        },
        "interpretation": (
            "Numeric checks found no decode errors or hard-clipped samples; the exact join lies "
            "inside a below-minus-60-dBFS interval and its sample step is below the largest adjacent "
            "step in the surrounding 500 ms. Human listening remains pending."
        ),
    }
    if report["hard_clipped_samples_ge_0_999"] != 0:
        raise SystemExit("hard-clipped samples detected")
    if report["join"]["join_contiguous_below_minus_60_dbfs_seconds"] < 0.3:
        raise SystemExit("segment join is not contained in the required low-level interval")
    if report["join"]["join_boundary_delta_fraction_of_window_max"] >= 0.01:
        raise SystemExit("segment join step is unexpectedly large")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
