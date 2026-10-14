#!/usr/bin/env python3
"""Align the verified River master to the approved showcase caption text.

The ASR transcript is written only to the ephemeral job workspace and is never uploaded. Standard output contains a
numeric summary so CI logs do not reproduce the narration.
"""
from __future__ import annotations

import argparse
import difflib
import json
import logging
import re
import av
from pathlib import Path

from faster_whisper import WhisperModel

TOKEN_RE = re.compile(r"[a-z0-9]+(?:'[a-z0-9]+)*")


def tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower().replace("’", "'"))


def media_duration(path: Path) -> float:
    with av.open(str(path)) as container:
        if container.duration is None:
            raise SystemExit("audio container has no measured duration")
        return float(container.duration / av.time_base)


def edit_distance(reference: list[str], hypothesis: list[str]) -> int:
    previous = list(range(len(hypothesis) + 1))
    for i, left in enumerate(reference, 1):
        current = [i]
        for j, right in enumerate(hypothesis, 1):
            current.append(min(
                current[-1] + 1,
                previous[j] + 1,
                previous[j - 1] + (left != right),
            ))
        previous = current
    return previous[-1]


def stamp(seconds: float, srt: bool) -> str:
    millis = max(0, round(seconds * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    separator = "," if srt else "."
    return f"{hours:02}:{minutes:02}:{secs:02}{separator}{millis:03}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--captions", type=Path, required=True)
    parser.add_argument("--storyboard", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="base.en")
    parser.add_argument("--expected-duration", type=float, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    approved = json.loads(args.captions.read_text())
    cues = approved["cues"]
    storyboard = json.loads(args.storyboard.read_text())
    duration = media_duration(args.audio)
    if not 300 < args.expected_duration < 900:
        raise SystemExit("expected master duration is outside the showcase bounds")
    if abs(duration - args.expected_duration) > 0.08:
        raise SystemExit(f"unexpected master duration: {duration:.6f}")

    logging.getLogger("faster_whisper").setLevel(logging.ERROR)
    logging.getLogger("ctranslate2").setLevel(logging.ERROR)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(args.audio),
        language="en",
        beam_size=5,
        word_timestamps=True,
        vad_filter=True,
        condition_on_previous_text=False,
    )

    asr_words: list[dict] = []
    transcript_parts: list[str] = []
    for segment in segments:
        transcript_parts.append(segment.text.strip())
        for word in segment.words or []:
            normalized = tokens(word.word)
            if not normalized:
                continue
            span = max(0.01, float(word.end) - float(word.start))
            for index, token in enumerate(normalized):
                asr_words.append({
                    "token": token,
                    "start": float(word.start) + span * index / len(normalized),
                    "end": float(word.start) + span * (index + 1) / len(normalized),
                })

    expected_words: list[str] = []
    cue_ranges: list[tuple[int, int]] = []
    for cue in cues:
        start = len(expected_words)
        expected_words.extend(tokens(cue["text"]))
        cue_ranges.append((start, len(expected_words)))

    hypothesis_words = [item["token"] for item in asr_words]
    matcher = difflib.SequenceMatcher(None, expected_words, hypothesis_words, autojunk=False)
    mapping: dict[int, int] = {}
    matched = 0
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            mapping[block.a + offset] = block.b + offset
            matched += 1

    aligned: list[dict] = []
    for cue, (left, right) in zip(cues, cue_ranges):
        pairs = [(expected_index, mapping[expected_index])
                 for expected_index in range(left, right) if expected_index in mapping]
        if pairs:
            first_expected, first_asr = pairs[0]
            last_expected, last_asr = pairs[-1]
            cue_start = asr_words[first_asr]["start"] - min(1.0, 0.23 * (first_expected - left))
            cue_end = asr_words[last_asr]["end"] + min(1.0, 0.23 * (right - 1 - last_expected))
        else:
            cue_start = duration * left / len(expected_words)
            cue_end = duration * right / len(expected_words)
        aligned.append({
            "scene": cue["scene"],
            "sentence": cue["sentence"],
            "text": cue["text"],
            "start": max(0.0, cue_start),
            "end": min(duration, cue_end),
            "matched_tokens": len(pairs),
            "expected_tokens": right - left,
        })

    # Place cue boundaries in the available gaps and guarantee monotonic, non-overlapping timing.
    for index, cue in enumerate(aligned):
        if index == 0:
            cue["start"] = 0.0
        else:
            previous = aligned[index - 1]
            if cue["start"] < previous["end"]:
                boundary = (cue["start"] + previous["end"]) / 2
                previous["end"] = max(previous["start"] + 0.35, boundary - 0.015)
                cue["start"] = previous["end"] + 0.03
        if cue["end"] <= cue["start"] + 0.35:
            cue["end"] = min(duration, cue["start"] + 0.35)
    for index in range(len(aligned) - 1):
        aligned[index]["end"] = min(aligned[index]["end"], aligned[index + 1]["start"] - 0.03)
    aligned[-1]["end"] = min(duration, max(aligned[-1]["end"], aligned[-1]["start"] + 0.35))

    scene_first: dict[str, float] = {}
    for cue in aligned:
        scene_first.setdefault(cue["scene"], cue["start"])
    timed_scenes = []
    for index, scene in enumerate(storyboard):
        start = 0.0 if index == 0 else scene_first[scene["id"]]
        end = duration if index + 1 == len(storyboard) else scene_first[storyboard[index + 1]["id"]]
        timed_scenes.append({**scene, "start": round(start, 3), "duration": round(end - start, 3)})

    caption_output = [{k: round(v, 3) if k in {"start", "end"} else v
                       for k, v in cue.items() if k not in {"matched_tokens", "expected_tokens"}}
                      for cue in aligned]
    timing = {
        "duration": round(duration, 6),
        "scenes": timed_scenes,
        "captions": caption_output,
        "timing_status": "verified_direct_voxtype_river_alignment",
        "render_ready": False,
        "timing_basis": (
            "All scene and caption windows are aligned to the verified assembled direct-VoxType "
            "River master. Rendering remains blocked by human listening, qualified final-image "
            "captures and release binding."
        ),
    }
    (args.output / "timing.json").write_text(json.dumps(timing, indent=2) + "\n")
    (args.output / "caption-text-aligned.json").write_text(json.dumps({
        "language": "en",
        "timing_status": "whisper_base_en_word_aligned",
        "cues": caption_output,
    }, indent=2) + "\n")

    srt_lines = []
    vtt_lines = ["WEBVTT", ""]
    for index, cue in enumerate(caption_output, 1):
        srt_lines += [str(index), f"{stamp(cue['start'], True)} --> {stamp(cue['end'], True)}",
                      cue["text"], ""]
        vtt_lines += [f"{stamp(cue['start'], False)} --> {stamp(cue['end'], False)}",
                      cue["text"], ""]
    (args.output / "captions.srt").write_text("\n".join(srt_lines))
    (args.output / "captions.vtt").write_text("\n".join(vtt_lines))

    chapter_lines = []
    seen_chapters = set()
    for scene in timed_scenes:
        chapter = scene["chapter"]
        if chapter in seen_chapters:
            continue
        seen_chapters.add(chapter)
        chapter_lines += [f"[CHAPTER]", "TIMEBASE=1/1000",
                          f"START={round(scene['start'] * 1000)}",
                          f"END={round(duration * 1000)}", f"title={chapter}"]
    # Fill chapter ends from the next chapter start.
    starts = [i for i, line in enumerate(chapter_lines) if line == "[CHAPTER]"]
    for pos, item_index in enumerate(starts[:-1]):
        next_start = int(chapter_lines[starts[pos + 1] + 2].split("=", 1)[1])
        chapter_lines[item_index + 3] = f"END={next_start}"
    (args.output / "chapters.txt").write_text("\n".join(chapter_lines) + "\n")

    transcript = " ".join(part for part in transcript_parts if part)
    (args.output / "whisper-transcript.txt").write_text(transcript + "\n")
    (args.output / "whisper-words.json").write_text(json.dumps(asr_words, indent=2) + "\n")

    errors = edit_distance(expected_words, hypothesis_words)
    wer = errors / max(1, len(expected_words))
    sequence_ratio = matcher.ratio()
    coverage = matched / max(1, len(expected_words))
    normalized_transcript = " ".join(hypothesis_words)
    targets = {
        "corrected_winter_phrase_token_coverage": "wallpaper picker includes the project's growing photo collection",
        "wallpaper_hide_restore_phrase_token_coverage": "built-in wallpapers can be deleted from your view and restored later",
        "whats_new_phrase_token_coverage": "what's new shows the changes once with release notes ready to reopen later",
    }
    targets.update({
        "explicit_cpu_recovery_phrase_token_coverage": "explicitly switch voxtype to cpu",
        "local_privacy_phrase_token_coverage": "without sending audio to a service",
    })
    target_ratios = {
        key: difflib.SequenceMatcher(None, tokens(value), hypothesis_words, autojunk=False)
        .find_longest_match().size / len(tokens(value))
        for key, value in targets.items()
    }
    banned = "nineteen project photos" in normalized_transcript
    cue_coverages = [
        cue["matched_tokens"] / max(1, cue["expected_tokens"])
        for cue in aligned
    ]
    report = {
        "audio_duration_seconds": round(duration, 6),
        "model": args.model,
        "detected_language": info.language,
        "detected_language_probability": round(info.language_probability, 6),
        "expected_words": len(expected_words),
        "asr_words": len(hypothesis_words),
        "edit_distance": errors,
        "word_error_rate": round(wer, 6),
        "sequence_ratio": round(sequence_ratio, 6),
        "exact_token_coverage": round(coverage, 6),
        "minimum_cue_exact_token_coverage": round(min(cue_coverages), 6),
        "cues_below_half_exact_token_coverage": sum(value < 0.5 for value in cue_coverages),
        "cues_without_exact_tokens": sum(value == 0 for value in cue_coverages),
        **{key: round(value, 6) for key, value in target_ratios.items()},
        "banned_old_phrase_detected": banned,
        "caption_cues": len(caption_output),
        "scenes": len(timed_scenes),
        "transcript_in_ci_log": False,
    }
    (args.output / "whisper-verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, sort_keys=True))

    if wer > 0.12 or sequence_ratio < 0.90 or coverage < 0.85:
        raise SystemExit("Whisper verification thresholds failed")
    if min(target_ratios.values()) < 0.75 or banned:
        raise SystemExit("Required patched wording verification failed")


if __name__ == "__main__":
    main()
