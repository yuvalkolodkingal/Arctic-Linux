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
  text in reading order. `caption-text.json` supplies sentence text with deliberately unset
  times. Sentence alignment, captions and scene timing still require verification against the
  measured River master before rendering.
- Keep `../DESIGN.md` colours, fonts, restrained motion and readable screens. The installer
  uses labelled demo screens; combined app captures retain their composed-layout disclosure.
  No continuous installation or newly qualified release is claimed.
- New pictures must show Foot/Fish, PCManFM, the current app picker, separate Remove apps,
  photo backgrounds, the bar's modes and Dictation's setup/recording/error states. Use current
  repository assets or separately admitted new captures, never closed runtime evidence.
- The existing composition generator hard-codes the former app cards and Kitty/Nautilus
  tiling captures. Update those with the new assets when preparing the rendered revision.
- Generate sentence/scene timings from the final River audio, then embed captions and ship
  SRT/VTT. Do not reuse or proportionally scale the old Kokoro caption times.
- Before publication, run the full HyperFrames check, inspect representative frames, verify
  video/audio/caption/chapter timing, and replace download links only after the new assets exist.

The **Both** wallpaper source, twenty-eight-photo collection and per-account hide/restore
behavior are implemented on the source base for this revision. The spoken text intentionally says
“the project's growing photo collection” so the replacement video does not hard-code a count.
