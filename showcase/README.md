# Arctic Linux showcase

The published showcase is the 6 minute 47 second, 1920 × 1080 edition from 3 October 2026.
It uses Kokoro's `af_heart` narration and documents the earlier app set.

[Download the published video, captions, and editable source](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/tag/showcase-2026-10-03).

[![Arctic Linux showcase](poster.png)](https://github.com/yuvalkolodkingal/Arctic-Linux/releases/download/showcase-2026-10-03/Arctic-Linux-Showcase-1080p.mp4)

## River replacement source

The [current source and receipts](revision-2026-10-12/) describe the native app set, project
photo backgrounds, separate Remove apps, Voxtype 1.1.0 local dictation, signed stable updates,
the one-time What's New summary, and per-account hide/restore for packaged wallpapers.

The source is 8 minutes 38.38 seconds long, with 38 scenes and 130 sentence-aligned caption
cues. Two bounded ElevenLabs River patches add only the new What's New and wallpaper
hide/restore narration. The earlier River material remains unchanged around measured splice
points.

Local source validation passed with faster-whisper 1.2.1: 3.6770% word error rate, 97.6208%
exact-token coverage, and full phrase coverage for both new sentences. This is automated
alignment evidence, not a human listening review.

The new source has **not** been rendered or published. Final-image captures for dictation,
wallpaper management and What's New remain explicitly pending until the matching Arctic image
finishes qualification. Full decode, subtitle mux, representative-frame review, human listening,
release binding and public download verification must then run on the final render. The public
link above therefore continues to point to the 3 October edition.

## What the source shows

The app scenes cover GNOME Web, Foot, PCManFM, XArchiver, FeatherPad, Celluloid, Nano and
Fish/Bash. Dictation uses Voxtype 1.1.0 with local multilingual Whisper and shows the online
setup and offline recovery contract. Evidence cards label features whose final-image capture is
still pending; installer screens retain their demonstration-data disclosure.

The Winter scene explains that Delete hides a packaged wallpaper only for the current account,
Restore brings hidden defaults back, and personal wallpaper choices remain untouched. The
Updates scene explains that What's New appears once after each installed update and can be
reopened from Settings.

This is an animated screenshot and evidence-card showcase, rather than a continuous installation
recording. [`asset-provenance.json`](asset-provenance.json) records admitted images and
transformations. The [project wiki](https://github.com/yuvalkolodkingal/Arctic-Linux/wiki) remains
the full operating guide.

## Preview and final render

For source-only layout work:

```sh
cd showcase
python -m pip install Pillow==11.3.0
python prepare-assets.py
python build-composition.py
npm run check -- --samples 38 --strict
```

The prior River master remains in the unpublished draft source release tagged
`showcase-river-source-2026-10-12`. The two new patch binaries and locally assembled master are
not committed or public. The remote workflows now require the non-public draft asset
`narration-river-final-2026-10-13.mp3` with the recorded SHA-256 and will fail closed until it is
preserved. [`voice-timing.json`](revision-2026-10-12/voice-timing.json) records
their exact River voice/model, flow, node, session and generation IDs, bytes, SHA-256 checksums,
measured durations, splice points, cost and license basis. Preserve those exact binaries in a
non-public source archive before remote rendering; do not regenerate them.

After final captures are admitted, use the source workflow to rebuild the composition, run
HyperFrames 0.8.114 in strict mode, render 1080p at 30 fps, embed captions and chapters, decode
the complete output, and review representative frames. The final MP4 size, SHA-256, release URL
and matching ISO fields remain pending qualification.

## Source and verification records

[`storyboard.json`](storyboard.json) contains the 38-scene story. [`timing.json`](timing.json),
[`captions.srt`](captions.srt), [`captions.vtt`](captions.vtt) and [`chapters.txt`](chapters.txt)
contain the locally aligned 518.378980-second source. The local verifier pins faster-whisper
1.2.1 and PyAV 16.0.1. Transcript-bearing files stay outside Git and logs.

ElevenLabs River is voice ID `SAz9YHcvj6GT2YYXdXww`; both new patches use
`eleven_multilingual_v2`. Generated-audio use is governed by the connected workspace plan and
the [ElevenLabs Terms of Service](https://elevenlabs.io/terms-of-use). The final publisher must
confirm that plan permits the intended public video. No standalone license file accompanied the
generations.

The Arctic artwork and repository screenshots follow this project's license. Figtree and
JetBrains Mono use the SIL Open Font License; GSAP uses its upstream Standard License.
