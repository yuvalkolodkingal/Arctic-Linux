# English showcase revision — 12 October 2026

This is the source draft for the replacement showcase. The published 3 October video and its
Kokoro timing, captions, screenshots and validation remain intact until the replacement is
rendered and checked.

- Story: 38 scenes. `storyboard.json` keeps the current scene fields; `capture_required: true`
  marks screens that must be refreshed before rendering. Future paths name intended captures,
  rather than asserting those files exist or passed review.
- Voice: ElevenLabs River (`SAz9YHcvj6GT2YYXdXww`), `eleven_multilingual_v2`, English.
  Three source generations were each run once. `voice-timing.json` records their complete
  session and generation IDs, byte sizes, measured durations and SHA-256 checksums.
- The measured master is 507.559184 seconds and 12,182,090 bytes. Its SHA-256 is
  `d172dbfb691f51a88e02e1222300068b7a07d263ea63a11897142493fa8574cb`.
  The corrected `winter` paragraph replaces the earlier hard-coded 19-photo wording.
- `scene-narration.json` contains the spoken text for each scene. `narration.txt` is the same
  text in reading order. `caption-text.json` preserves the approved untimed source;
  `caption-text-aligned.json`, `timing.json`, SRT, VTT and chapters contain the verified
  local-Whisper alignment used by the rendered candidate.
- Keep `../DESIGN.md` colours, fonts, restrained motion and readable screens. The installer
  uses labelled demo screens; combined app captures retain their composed-layout disclosure.
  No continuous installation or newly qualified release is claimed.
- New pictures must show Foot/Fish, PCManFM, the current app picker, separate Remove apps,
  photo backgrounds, the bar's modes and Dictation's setup/recording/error states. Use current
  repository assets or separately admitted new captures, never closed runtime evidence.
- The composition uses GNOME Web, Foot, PCManFM, XArchiver, FeatherPad, Celluloid, Nano and
  Fish/Bash. Exact-candidate captures keep their qualification disclosure; features without a
  current admitted screen use labelled evidence cards.
- Workflow run 38300570733 passed strict HyperFrames checks, rendered the full candidate, decoded
  every frame and verified H.264/AAC/selectable-English-subtitle streams. Fifteen representative
  scenes were visually reviewed.
- Publication remains pending the matching Arctic release qualification. Replace public download
  links only after the candidate is deliberately published.

The **Both** wallpaper source, twenty-eight-photo collection and per-account hide/restore
behavior are implemented on the source base for this revision. The spoken text intentionally says
“the project's growing photo collection” so the replacement video does not hard-code a count.
