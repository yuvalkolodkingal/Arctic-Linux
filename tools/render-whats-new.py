#!/usr/bin/python3
"""Render the packaged What's New notes with this RPM build's identity.

The source notes deliberately use ``package-build`` as a development identity.  Every
published Arctic build has a different Version-Release, so replacing that identity while
building arctic-shell makes the per-user seen marker advance for every actual update.
"""

import argparse
import json
import re
from pathlib import Path


SOURCE_ID = "package-build"
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+~^-]{0,127}\Z")


def render(source: Path, destination: Path, update_id: str) -> dict:
    if not ID_RE.fullmatch(update_id):
        raise ValueError("update id must be a bounded RPM-safe identifier")

    try:
        notes = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read What's New notes: {error}") from error

    if not isinstance(notes, dict) or notes.get("schema") != 1:
        raise ValueError("What's New notes must use schema 1")
    if notes.get("update_id") != SOURCE_ID:
        raise ValueError(f"source update_id must be {SOURCE_ID!r}; RPM builds replace it")
    if not isinstance(notes.get("title"), str) or not notes["title"].strip():
        raise ValueError("What's New notes need a title")
    items = notes.get("items")
    if not isinstance(items, list) or not items or len(items) > 6:
        raise ValueError("What's New notes need one to six items")
    for item in items:
        if not isinstance(item, dict) or not all(
                isinstance(item.get(key), str) and item[key].strip()
                for key in ("title", "text")):
            raise ValueError("every What's New item needs non-empty title and text")
    url = notes.get("notes_url", "")
    if not isinstance(url, str) or (url and not url.startswith("https://")):
        raise ValueError("notes_url must be empty or HTTPS")

    notes["update_id"] = update_id
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(notes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return notes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--update-id", required=True)
    args = parser.parse_args()
    try:
        render(args.source, args.output, args.update_id)
    except ValueError as error:
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
