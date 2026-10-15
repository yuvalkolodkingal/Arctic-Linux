# Temporary screened evidence review export

This helper exists only to move a small, reviewed subset of already-screened qualification
evidence through GitHub itself when the artifact blob host is unreachable from the review
environment. It cannot qualify or publish a release.

The manifest starts disabled. To prepare one export:

1. Create `codex/evidence-review-export-20261015` from the reviewed source commit.
2. Fill `manifest.json` with completed, successful qualification run and artifact identities.
   Pin every run, head, artifact name, archive byte count and digest. Select ordinary files by
   exact member path, byte count, digest and media metadata. Contact-sheet frames and native audio
   use exact names and bounds plus the producer's digest inventory inside that pinned archive.
   Only producer-screened PNGs,
   transcript-free summary JSON and the two validated native virtual-output WAV classes are
   accepted. Dictation, microphone, VoxType, Whisper, transcript and narration-source audio are
   not exportable.
3. Put the complete taskbar PNG census into at most eight `png-contact-sheet` entries of at most
   64 exactly named source frames each, bound to the artifact's `upload-screening.json` inventory.
   Use each sheet's `exact_frames` list for the small full-resolution selection. The exporter
   labels every sheet cell by index and writes the measured digest, byte count and source mapping
   into `REVIEW-MANIFEST.json`.
4. Set `ready` to `true`, commit the preparation and run the local tests.
5. Confirm that `codex/evidence-review-artifacts-20261015` does not exist.
6. In a child commit, add `.github/evidence-review-export-20261015.activate` containing only the
   40-character preparation commit SHA and push that marker-only child.

The workflow verifies the marker, successful run identities, artifact API metadata, downloaded
archive digests, zip bounds and every selected file. It creates a new orphan review branch with
only the selected media and `REVIEW-MANIFEST.json`. It uses a non-force push, so it cannot replace
an earlier review branch. Delete both temporary branches after review.
