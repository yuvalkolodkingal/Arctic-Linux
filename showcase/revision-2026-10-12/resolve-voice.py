#!/usr/bin/env python3
"""Validate the immutable direct-VoxType narration receipt for CI."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from voice_receipt import (  # noqa: E402,F401
    resolve,
    resolve_publication,
    validate_assembled_master,
    validate_segment_plan,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument(
        "--purpose",
        choices=("private-render", "publish-video", "publish-video-with-source-audio"),
        default="private-render",
        help=(
            "private-render admits an unpublished candidate; publishing requires publisher approval, "
            "and source-audio redistribution requires its broader explicit scope"
        ),
    )
    args = parser.parse_args()
    try:
        receipt = json.loads(args.receipt.read_text())
        if args.purpose == "private-render":
            values = resolve(receipt)
        else:
            values = resolve_publication(
                receipt,
                redistribute_source_audio=args.purpose == "publish-video-with-source-audio",
            )
    except (OSError, json.JSONDecodeError, ValueError) as error:
        raise SystemExit(f"{args.purpose} blocked: {error}") from error
    if args.github_output:
        with args.github_output.open("a") as output:
            for key, value in values.items():
                output.write(f"{key}={value}\n")
    print(json.dumps(values, sort_keys=True))


if __name__ == "__main__":
    main()
