# Arctic Linux showcase

The published showcase is the 6 minute 47 second, 1920 × 1080 edition from 3 October 2026.
It uses Kokoro's `af_heart` narration and documents the earlier app set.

[Download the published video, captions, and editable source](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/showcase-2026-10-03).

[![Arctic Linux showcase](poster.png)](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/Arctic-Linux-Showcase-1080p.mp4)

## River replacement candidate

The [12 October source and validation receipt](revision-2026-10-12/) describe the current native
apps, project photo backgrounds, separate Remove apps, local dictation and signed stable updates.
The English River candidate is 8 minutes 27.53 seconds long and contains 38 scenes and 128
sentence-aligned caption cues.

The candidate passed:

- [local Whisper verification](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38299503545):
  4.1328% word error rate, 97.048% exact-token coverage, the corrected Winter wording present and
  the obsolete count absent;
- [strict render validation](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38300570733):
  complete decode with no errors, H.264 video, AAC audio, selectable English subtitles and
  representative-frame review.

The resulting MP4 is 60,327,673 bytes with SHA-256
`731fb8c58c1e4097c472f44c6ee2cd1280884af7b41b1c23e2a2cf296739a836`.
It remains an unpublished candidate until the matching Arctic release finishes qualification.
The public download link therefore still points to the October 3 edition.

## What the candidate shows

The current source uses admitted repository screenshots from the exact ISO qualification work.
Where a current screenshot was unavailable, the composition uses a clearly labelled
**QUALIFICATION EVIDENCE** card. Installer screens retain their demonstration-data disclosure,
and QEMU qualification captures retain their evidence labels.

The app scenes cover GNOME Web, Foot, PCManFM, XArchiver, FeatherPad, Celluloid, Nano and
Fish/Bash. Dictation scenes show the online setup and offline recovery states from authentic
qualification captures. The Winter scene uses the repository's current wallpaper-picker capture;
the adjoining Ember scene shows the published original photograph.

This is an animated screenshot and evidence-card showcase, rather than a continuous installation
recording. [`asset-provenance.json`](asset-provenance.json) records every admitted image and
transformation. The [project wiki](https://github.com/yuvalkolodkingal/Arctic-Linux/wiki) remains
the full operating guide.

## Preview and render

The reproducible path is [`showcase-river-render.yml`](../.github/workflows/showcase-river-render.yml).
It installs FFmpeg, Python 3.12, Pillow 11.3.0 and Node.js 22, verifies the River master by
SHA-256, rebuilds the assets and composition, runs HyperFrames 0.8.114 in strict mode, renders
1080p at 30 fps, embeds captions and chapters, decodes the complete result, and uploads the
candidate plus its validation evidence.

For source-only layout work:

```sh
cd showcase
python -m pip install Pillow==11.3.0
python prepare-assets.py
python build-composition.py
npm run check -- --samples 38 --strict
```

For a local media render, place the verified River master at `showcase/audio/narration.mp3`.
Its required SHA-256 is
`d172dbfb691f51a88e02e1222300068b7a07d263ea63a11897142493fa8574cb`.
Then run:

```sh
cd showcase
npm run render -- \
  --output renders/Arctic-Linux-Showcase-River-1080p.mp4 \
  --quality high --fps 30
python finalize-video.py renders/Arctic-Linux-Showcase-River-1080p.mp4
```

## Edit and verification records

[`storyboard.json`](storyboard.json) contains the 38-scene story.
[`timing.json`](timing.json), [`captions.srt`](captions.srt),
[`captions.vtt`](captions.vtt) and [`chapters.txt`](chapters.txt) are the verified alignment
used by the candidate. [`voice-timing.json`](revision-2026-10-12/voice-timing.json) records the
three one-time ElevenLabs River generation IDs, measured splice, checksums and exact model.
Do not rerun those nodes unless a named source segment is proven unusable.

The local verifier pins faster-whisper 1.2.1 and PyAV 16.0.1. Transcript-bearing verification
files remain only in the private workflow artifact; Git contains the log-safe metrics, timings and
captions. Whisper supplies an automated intelligibility check and alignment evidence, not a human
listening review.

The Arctic artwork and repository screenshots follow this project's license. Figtree and
JetBrains Mono use the SIL Open Font License; GSAP uses its upstream Standard License.
