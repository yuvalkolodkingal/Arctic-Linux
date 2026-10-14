#!/usr/bin/env python3
"""Assemble the River showcase reference from the preserved master and two bounded patches.

The three audio inputs are deliberately kept out of Git. This script verifies their immutable
receipts before decoding and re-encoding one 44.1 kHz mono MP3. The output is a local source
candidate until the final image captures, alignment, render and publication gates pass.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

INPUTS = {
    "base": {
        "bytes": 12_182_090,
        "sha256": "d172dbfb691f51a88e02e1222300068b7a07d263ea63a11897142493fa8574cb",
    },
    "wallpaper": {
        "bytes": 102_015,
        "sha256": "8d6aba63182933ecfd1b5c8c7fa6b178a29c2f7e25666f6e6250fc968a87a1d5",
    },
    "whats_new": {
        "bytes": 108_285,
        "sha256": "07608b53381c306d7dc81409e1f8aaaa16533a6ff1264503de0dfa7012817664",
    },
}
CUT_WALLPAPER_SECONDS = 391.63
CUT_WHATS_NEW_SECONDS = 468.06


def receipt(path: Path) -> dict[str, int | str]:
    return {"bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", type=Path, required=True)
    parser.add_argument("--wallpaper", type=Path, required=True)
    parser.add_argument("--whats-new", dest="whats_new", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()

    paths = {name: getattr(args, name) for name in INPUTS}
    for name, path in paths.items():
        observed = receipt(path)
        if observed != INPUTS[name]:
            raise SystemExit(f"{name} input receipt mismatch: {observed}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    graph = (
        f"[0:a]atrim=start=0:end={CUT_WALLPAPER_SECONDS},asetpts=PTS-STARTPTS[a0];"
        "[1:a]aresample=44100,asetpts=PTS-STARTPTS[a1];"
        f"[0:a]atrim=start={CUT_WALLPAPER_SECONDS}:end={CUT_WHATS_NEW_SECONDS},asetpts=PTS-STARTPTS[a2];"
        "[2:a]aresample=44100,asetpts=PTS-STARTPTS[a3];"
        f"[0:a]atrim=start={CUT_WHATS_NEW_SECONDS},asetpts=PTS-STARTPTS[a4];"
        "[a0][a1][a2][a3][a4]concat=n=5:v=0:a=1[out]"
    )
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(args.base), "-i", str(args.wallpaper), "-i", str(args.whats_new),
        "-filter_complex", graph, "-map", "[out]", "-ac", "1", "-ar", "44100",
        "-b:a", "192k", str(args.output),
    ], check=True)
    result = {
        "status": "local_unpublished_source_candidate",
        "inputs": {name: {"path": path.name, **receipt(path)} for name, path in paths.items()},
        "cuts_on_base_seconds": {
            "wallpaper_hide_restore": CUT_WALLPAPER_SECONDS,
            "whats_new": CUT_WHATS_NEW_SECONDS,
        },
        "output": {"path": args.output.name, **receipt(args.output)},
    }
    if args.receipt:
        args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
