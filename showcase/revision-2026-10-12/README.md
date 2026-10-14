# English showcase revision — current source

This directory holds the source and validation receipts for the English River replacement. The
published 3 October video remains public until a final-image render is qualified and deliberately
published.

- **Story:** 38 scenes and 130 cues. `storyboard.json` and `narration.txt` contain locked direct-
  VoxType copy. All cue and scene windows are aligned to the verified assembled River master.
- **Voice:** ElevenLabs River (`SAz9YHcvj6GT2YYXdXww`), `eleven_multilingual_v2`, English.
  The earlier River master receipt is preserved as superseded evidence. It must not render this copy.
  A full-script attempt failed before usable audio because the locked 9,093-character input exceeded
  the connector's 5,000-character limit. Its flow, node, session and generation IDs remain in
  `voice-timing.json` as explicitly non-renderable evidence.
- **Bounded inputs:** the exact UTF-8 narration is split at the paragraph boundary after `getapps`.
  Segment 1 is 4,451 characters (scenes `intro` through `getapps`); segment 2 is 4,642 characters
  (scenes `removeapps` through `outro`). Concatenating the two files byte for byte reproduces the
  9,093-byte locked narration with SHA-256
  `23d1eab240865ea3230a1448a098abaed2b3e5fa9a1ee58e0a4eaab12e96215e`.
- **Patch receipts:** `voice-timing.json` records exact flow, node, session and generation IDs,
  byte sizes, SHA-256 checksums, durations, costs and measured splice points. Neither patch nor
  the assembled master is committed or public. Do not regenerate them.
- **Superseded local master:** 518.378980 seconds in PyAV; 12,442,896 bytes; SHA-256
  `ae4792c1877291a4815e48139b9ceec1b611e12fdacf27741a1238769762d765`. This is a
  preserved receipt for the prior custom-controller wording. The workflows now fail closed before
  using it. The replacement master described below remains unpublished and is not render-ready.
- **Assembly:** `assemble-river-segments.py` verifies both audio receipts, decodes them to
  44.1 kHz mono PCM, joins the decoded samples without inserted silence or a crossfade, encodes one
  master, and rejects it unless its decoded sample count equals the exact sum of the inputs. It emits
  the final byte size, SHA-256, PyAV duration and sample count for the immutable master receipt.
- **Generated segments:** both one-take River calls completed and are preserved outside Git. Segment
  1 is 4,491,422 bytes, SHA-256 `312930f1b1d759bb42271be4437b968c5053371c7c75cbe96483011a52e49fa6`,
  279.568254 seconds and 12,328,960 decoded samples. Segment 2 is 4,344,718 bytes, SHA-256
  `d9da67e9db12cc9866a689accc7a7257137de90f9c6ccf3c026c6feee4e8231a`, 270.419592 seconds
  and 11,925,504 decoded samples. Exact provider flow, node, session and generation IDs are in the
  receipt.
- **Assembled master:** the verified unpublished master is 13,201,492 bytes, SHA-256
  `90d573f80bba1365b97ac0162be5028ded235e481665b58acbcedbb8792507d5`, 549.987846 seconds and
  24,254,464 decoded mono samples at 44.1 kHz. The join inserted zero samples.
- **Alignment:** two local offline runs with faster-whisper 1.2.1 and `base.en` produced
  byte-identical outputs. Automated verification measured 3.9375% WER, 96.9246% sequence ratio
  and 97.3523% exact-token coverage. Every cue has at least 66.6667% exact-token coverage; no cue
  has zero exact tokens. The local-privacy and explicit CPU-recovery phrases have full token
  coverage. Human listening has not run.
- **Objective audio checks:** a complete FFmpeg decode reported zero errors; the master has no
  samples at or above 0.999, integrated loudness is -24.5 LUFS and true peak is -1.9 dBFS. The
  exact segment boundary lies inside 0.382290 seconds below -60 dBFS, and its sample step is
  0.001369 of the largest adjacent step in the surrounding 500 ms. These numeric checks do not
  replace listening.
- **Publication:** false. Human listening, final-image captures, strict HyperFrames validation,
  full render/decode, subtitle mux, representative-frame review, release binding and public
  download verification remain pending.

`resolve-voice.py --purpose private-render` gates an unpublished candidate without treating a
publisher license confirmation as render evidence. It binds to the repository's real
`tools/qualified-release/manifest.json`, including the update lane, active-installer lane and all
media reviews. `--purpose publish-video` separately requires release publication approval, a
confirmed public-video scope, and a reviewed final-render receipt binding the source commit, render
run and artifact, exact MP4, full decode/subtitle checks and eight human-reviewed representative
frames. Only `--purpose publish-video-with-source-audio` permits the source MP3 to be redistributed,
after the broader `public_video_and_source_audio_redistribution` scope is explicitly confirmed.

The source uses GNOME Web, Foot, PCManFM, XArchiver, FeatherPad, Celluloid, Nano and Fish/Bash.
The script describes signature-checked official **VoxType 1.1.0** binaries, verified automatic
online setup, offline not-ready retry, local Hebrew and English, the guarded Mango shortcut and
Arctic's VoxType-backed indicator. It reports 7.77% English WER and 42.0% Hebrew WER on the
hosted Westmere CPU fixture, together with its slower-than-real-time factors. The two obsolete
custom-controller images were removed. Five
capture contracts keep those scenes as labelled evidence cards until manually reviewed captures
from the qualified image are admitted. GPU recovery deliberately requires two captures: the visible
Vulkan failure and the later CPU-ready Hebrew/English state. Selecting CPU clears the failure, so
combining both claims into one screenshot would be misleading.

Generated-audio use is governed by the connected ElevenLabs workspace plan and the
[ElevenLabs Terms of Service](https://elevenlabs.io/terms-of-use). No standalone license file was
supplied; the final publisher must confirm the plan permits the intended public video.

Transcript and word-timestamp files remain outside Git and CI logs and are excluded from uploaded
workflow artifacts. Whisper supplies automated intelligibility and alignment evidence; it does not
replace human listening. Public operating instructions live in the
[Arctic Linux wiki](https://github.com/yuvalkolodkingal/Arctic-Linux/wiki).

Final source checks install HyperFrames 0.8.114 and its transitive dependencies from the committed
npm integrity lock. The preparation step verifies the exact committed GSAP 3.14.2 size and SHA-256
before use, and the showcase workflows pin official Actions to full reviewed commit SHAs.
