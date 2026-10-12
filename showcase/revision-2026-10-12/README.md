# English showcase revision — 12 October 2026

This directory is the source and validation receipt for the English River replacement candidate.
The published 3 October video remains public until the matching Arctic release is qualified and
this candidate is deliberately published.

- Story: 38 scenes and 128 sentence-aligned cues. `storyboard.json` and
  `caption-text-aligned.json` contain the approved current narration and its verified timing.
- Voice: ElevenLabs River (`SAz9YHcvj6GT2YYXdXww`), `eleven_multilingual_v2`, English.
  Three source generations were each run once. `voice-timing.json` records every session and
  generation ID, byte size, measured duration, splice boundary and SHA-256 checksum.
- River master: preserved as `narration-river-final.mp3` in the unpublished draft source release tagged
  `showcase-river-source-2026-10-12`; 507.559184 seconds, 12,182,090 bytes, SHA-256
  `d172dbfb691f51a88e02e1222300068b7a07d263ea63a11897142493fa8574cb`.
  The measured Winter splice replaces the obsolete hard-coded photo count.
- Alignment: [workflow run 38299503545](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38299503545)
  passed with 4.1328% word error rate, 97.048% exact-token coverage, full corrected-Winter phrase
  coverage and no obsolete phrase. `alignment-provenance.json`, `verifier-versions.json` and
  `whisper-verification.json` record the exact evidence and tool versions.
- Render: [workflow run 38300570733](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/38300570733)
  passed strict HyperFrames checks, rendered the complete 1920 × 1080 candidate at 30 fps, decoded
  every frame, verified H.264/AAC/selectable-English-subtitle streams and reviewed 15
  representative frames.
- Final MP4: 60,327,673 bytes, SHA-256
  `731fb8c58c1e4097c472f44c6ee2cd1280884af7b41b1c23e2a2cf296739a836`.
  `render-provenance.json` and `render-validation.json` record the artifact and media receipt.
- Publication: false. The matching Arctic ISO and release still need qualification before the
  public showcase download is replaced.

The composition uses GNOME Web, Foot, PCManFM, XArchiver, FeatherPad, Celluloid, Nano and
Fish/Bash. Authentic exact-candidate captures keep their qualification disclosure. Features
without a current admitted screenshot use clearly labelled evidence cards. Installer scenes use
labelled demonstration data; this is an animated screenshot showcase rather than a continuous
installation recording.

The source describes the **Both** wallpaper mode, the growing project photo collection and
per-account hide/restore behavior. The narration avoids a fixed wallpaper count. Transcript and
word-timestamp files are retained only in the 30-day workflow artifact so transcript excerpts do
not enter Git or CI logs. Whisper verification measures automated intelligibility and alignment;
it does not replace human listening.

Public operating instructions live in the
[Arctic Linux wiki](https://github.com/yuvalkolodkingal/Arctic-Linux/wiki).
