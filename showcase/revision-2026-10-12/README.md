# English showcase revision — current source

This directory holds the source and validation receipts for the English River replacement. The
published 3 October video remains public until a final-image render is qualified and deliberately
published.

- **Story:** 38 scenes and 130 sentence-aligned cues. `storyboard.json`, `narration.txt` and
  `caption-text-aligned.json` contain the current narration and local alignment.
- **Voice:** ElevenLabs River (`SAz9YHcvj6GT2YYXdXww`), `eleven_multilingual_v2`, English.
  The earlier River master is preserved. Two one-time, one-variation patches add only What's New
  and packaged-wallpaper hide/restore narration.
- **Patch receipts:** `voice-timing.json` records exact flow, node, session and generation IDs,
  byte sizes, SHA-256 checksums, durations, costs and measured splice points. Neither patch nor
  the assembled master is committed or public. Do not regenerate them.
- **Local master:** 518.378980 seconds in PyAV; 12,442,896 bytes; SHA-256
  `ae4792c1877291a4815e48139b9ceec1b611e12fdacf27741a1238769762d765`. This is an
  unpublished workspace candidate and still needs preservation in the non-public draft as
  `narration-river-final-2026-10-13.mp3`; verification workflows fail closed until it exists.
- **Alignment:** faster-whisper 1.2.1 passed locally with 3.6770% word error rate, 97.6208%
  exact-token coverage and full phrase coverage for both patch sentences. `alignment-provenance.json`
  records the exact outputs and limitations.
- **Publication:** false. Human listening, final-image captures, strict HyperFrames validation,
  full render/decode, subtitle mux, representative-frame review, release binding and public
  download verification remain pending.

The source uses GNOME Web, Foot, PCManFM, XArchiver, FeatherPad, Celluloid, Nano and Fish/Bash.
Voxtype is shown as version **1.1.0**. Final captures for dictation, wallpaper Delete/Restore and
What's New are not invented: those scenes use clearly labelled evidence cards until captures from
the qualified image are admitted.

Generated-audio use is governed by the connected ElevenLabs workspace plan and the
[ElevenLabs Terms of Service](https://elevenlabs.io/terms-of-use). No standalone license file was
supplied; the final publisher must confirm the plan permits the intended public video.

Transcript and word-timestamp files remain outside Git and CI logs. Whisper supplies automated
intelligibility and alignment evidence; it does not replace human listening. Public operating
instructions live in the [Arctic Linux wiki](https://github.com/yuvalkolodkingal/Arctic-Linux/wiki).
