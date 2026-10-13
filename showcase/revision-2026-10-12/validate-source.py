#!/usr/bin/env python3
"""Validate parity and fail-closed publication state for the current River source."""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path

REV = Path(__file__).resolve().parent
SHOWCASE = REV.parent
REPO = SHOWCASE.parent


def load(path: Path):
    return json.loads(path.read_text())


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    root_story = load(SHOWCASE / "storyboard.json")
    revision_story = load(REV / "storyboard.json")
    scene_narration = load(REV / "scene-narration.json")
    caption_source = load(REV / "caption-text.json")
    caption_aligned = load(REV / "caption-text-aligned.json")
    root_timing = load(SHOWCASE / "timing.json")
    revision_timing = load(REV / "timing.json")
    voice = load(REV / "voice-timing.json")

    ids = [scene["id"] for scene in root_story]
    assert len(ids) == len(set(ids)) == 38
    assert ids == [scene["id"] for scene in revision_story]
    assert ids == [scene["id"] for scene in scene_narration]
    assert ids == [scene["id"] for scene in root_timing["scenes"]]
    assert root_timing == revision_timing

    root_by_id = {scene["id"]: scene for scene in root_story}
    revision_by_id = {scene["id"]: scene for scene in revision_story}
    for item in scene_narration:
        scene_id = item["id"]
        assert item["text"] == root_by_id[scene_id]["narration"]
        assert item["text"] == revision_by_id[scene_id]["narration"]

    source_cues = caption_source["cues"]
    aligned_cues = caption_aligned["cues"]
    timed_cues = root_timing["captions"]
    assert len(source_cues) == len(aligned_cues) == len(timed_cues) == 130
    source_text = [(cue["scene"], cue["sentence"], cue["text"]) for cue in source_cues]
    assert source_text == [(cue["scene"], cue["sentence"], cue["text"]) for cue in aligned_cues]
    assert source_text == [(cue["scene"], cue["sentence"], cue["text"]) for cue in timed_cues]

    grouped: dict[str, list[str]] = defaultdict(list)
    for cue in source_cues:
        grouped[cue["scene"]].append(cue["text"])
    for scene_id in ids:
        assert " ".join(grouped[scene_id]) == root_by_id[scene_id]["narration"]

    duration = root_timing["duration"]
    assert abs(duration - 518.37898) < 0.000001
    previous_end = 0.0
    for cue in timed_cues:
        assert 0.0 <= cue["start"] < cue["end"] <= duration
        assert cue["start"] >= previous_end
        previous_end = cue["end"]

    for name in ("captions.srt", "captions.vtt", "chapters.txt", "narration.txt"):
        assert digest(SHOWCASE / name) == digest(REV / name)

    required = {
        "Voxtype 1.1.0": "dictationsetup",
        "Built-in wallpapers can be deleted from your view and restored later, without affecting another account.": "winter",
        "After each update, What's New shows the changes once, with release notes ready to reopen later.": "updates",
    }
    index = (SHOWCASE / "index.html").read_text()
    combined = "\n".join((SHOWCASE / name).read_text() for name in (
        "storyboard.json", "narration.txt", "captions.srt", "captions.vtt", "timing.json", "index.html"
    ))
    assert "Voxtype 0.5.1" not in combined
    for phrase, scene_id in required.items():
        assert phrase in index
        assert phrase in combined
        assert scene_id in ids

    assert voice["generated_audio_binaries_committed"] is False
    assert voice["assembly"]["published"] is False
    assert voice["validation"]["final_render_verified"] is False
    assert voice["validation"]["public_video_published"] is False
    assert not (SHOWCASE / "audio/narration-river-final-2026-10-13.mp3").exists()

    result = {
        "status": "PASSED_SOURCE_ONLY",
        "scenes": len(ids),
        "caption_cues": len(timed_cues),
        "duration_seconds": duration,
        "story_narration_caption_parity": True,
        "root_revision_timing_parity": True,
        "required_current_phrases": list(required),
        "voxtype_version": "1.1.0",
        "generated_audio_binaries_committed": False,
        "final_render_verified": False,
        "public_video_published": False,
    }
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
