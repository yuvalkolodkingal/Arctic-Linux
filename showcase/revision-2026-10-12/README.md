# English showcase revision — current source

This directory holds the source and validation receipts for the English River replacement. The
published 3 October video remains public until a final-image render is qualified and deliberately
published.

- **Story:** 38 scenes and 130 cues. `storyboard.json` and `narration.txt` contain locked direct-
  VoxType copy. All cue and scene windows are aligned to the verified assembled River master.
- **Voice:** ElevenLabs River (`SAz9YHcvj6GT2YYXdXww`), `eleven_multilingual_v2`, English.
  The connector used provider-default voice settings with no explicit stability, similarity or style overrides;
  each returned source was 128 kbps MP3 decoding to 44.1 kHz mono.
  The earlier River master receipt is preserved as superseded evidence. It must not render this copy.
  The current master speaks official VoxType 1.1.1 throughout; no 1.1.0 audio was spliced.
  A full-script attempt failed before usable audio because the locked 9,093-character input exceeded
  the connector's 5,000-character limit. Its flow, node, session and generation IDs remain in
  `voice-timing.json` as explicitly non-renderable evidence.
- **Bounded inputs:** the exact UTF-8 narration is split at the paragraph boundary after `getapps`.
  Segment 1 is 4,451 characters (scenes `intro` through `getapps`); segment 2 is 4,642 characters
  (scenes `removeapps` through `outro`). Concatenating the two files byte for byte reproduces the
  9,093-byte locked narration with SHA-256
  `cbf466a4cccfd283bc7971c274a92f063e2bba57f93fd81a52aba9dfa498a3b5`.
- **Generation receipts:** `voice-timing.json` records exact flow, node, session and generation IDs,
  byte sizes, SHA-256 checksums, durations, estimated costs and the measured segment boundary. Neither
  source segment nor the assembled master is committed or public. Do not regenerate them.
- **Superseded local master:** 518.378980 seconds in PyAV; 12,442,896 bytes; SHA-256
  `ae4792c1877291a4815e48139b9ceec1b611e12fdacf27741a1238769762d765`. This is a
  preserved receipt for the prior custom-controller wording. The workflows now fail closed before
  using it. The replacement master described below remains unpublished and is not render-ready.
- **Assembly:** `assemble-river-segments.py` verifies both audio receipts, decodes them to
  44.1 kHz mono PCM, joins the decoded samples without inserted silence or a crossfade, encodes one
  master, and rejects it unless its decoded sample count equals the exact sum of the inputs. It emits
  the final byte size, SHA-256, PyAV duration and sample count for the immutable master receipt.
- **Generated segments:** both one-take River calls completed and are preserved outside Git. Segment
  1 is 4,562,057 bytes, SHA-256 `6603a56e76d191a5a88b78030a39f96a1884f61001bba7c99cda990aea5c68e9`,
  283.980045 seconds and 12,523,520 decoded samples. Segment 2 is 4,792,352 bytes, SHA-256
  `df3daf95762904230013a0435f8c58c3f42c097595dd34bbc715dcd2e4342d7b`, 298.376417 seconds
  and 13,158,400 decoded samples. Exact provider flow, node, session and generation IDs are in the
  receipt.
- **Assembled master:** the verified unpublished master is 13,978,270 bytes, SHA-256
  `f6852132fed3f97e3b6a6b69fe4543e6af1a26c8495c9243e2cccfbde7c7081b`, 582.356463 seconds and
  25,681,920 decoded mono samples at 44.1 kHz. The join inserted zero samples.
- **Alignment:** two local offline runs with faster-whisper 1.2.1 and `base.en` produced
  byte-identical outputs. Automated verification measured 4.1412% WER, 96.8940% sequence ratio
  and 97.4202% exact-token coverage. Every cue has at least 60.0000% exact-token coverage; no cue
  has zero exact tokens. The local-privacy and explicit CPU-recovery phrases have full token
  coverage. Human listening has not run.
- **Objective audio checks:** a complete FFmpeg decode reported zero errors; the master has no
  samples at or above 0.999, integrated loudness is -24.6 LUFS and true peak is -2.2 dBFS. The
  exact segment boundary lies inside 0.431905 seconds below -60 dBFS, and its sample step is
  0.000238 of the largest adjacent step in the surrounding 500 ms. These numeric checks do not
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
The script describes signature-checked official **VoxType 1.1.1** binaries, verified automatic
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
