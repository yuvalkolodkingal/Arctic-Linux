# Temporary final qualification media review export

This observer-only helper copies a bounded allowlist from the three successful final-image
qualification artifacts into a new ephemeral Git branch. It exists because this review
environment cannot reach the Actions artifact blob host. It cannot alter the product, qualify an
image, fill a release review field, or publish a release.

The manifest pins these exact successful artifacts:

- native run `38830684742`, artifact `12017679100`, archive SHA-256
  `25f07dc38952d06c2c153de3acc102b9ca7e5facd4475aa7928dfd2399ed6f7f`;
- prepared-installer run `38830679610`, artifact `12017450791`, archive SHA-256
  `b3f56c254637aaf86ab3de685d55c7fc03803ad09eec31b0d31a17bf7ae68101`;
- active-installer run `38834124836`, artifact `12018832093`, archive SHA-256
  `1841dc56fe6f1e6a86fa56f6780cf08335c06cf2cc42ff8c5701b76dedf859c3`.

It exports only producer-screened PNGs and the two validated native virtual-output WAV files. It
never exports logs, dictation recordings, microphones, VoxType/Whisper audio, transcripts,
narration sources, secrets, or arbitrary archive members. The exact allowlist contains:

- all 480 taskbar frames as eight numbered contact sheets and 32 representative full-resolution
  frames;
- the eight native app/media images as one contact sheet and exact full-resolution copies;
- all 12 prepared-installer images and all seven active-installer images, each as a contact sheet
  plus exact full-resolution copies;
- native install and installed-boot virtual-output WAV files.

Every source is checked against the pinned artifact archive and its producer
`upload-screening.json` inventory. The exporter validates archive paths/types/bounds, PNG decode,
WAV format/non-silence and every output digest, then writes `REVIEW-MANIFEST.json`.

Activation is a two-commit control. First push the reviewed preparation to
`codex/final-evidence-review-export-20261016`. Then add only
`.github/final-evidence-review-export-20261016.activate` containing that preparation commit SHA
and push the marker-only child. The workflow refuses to replace the target
`codex/final-evidence-review-artifacts-20261016` branch. Delete both temporary branches after the
review records are bound into the release manifest.
