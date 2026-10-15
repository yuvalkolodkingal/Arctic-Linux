# Temporary screened evidence review export

This helper exists only to move a small, reviewed subset of already-screened qualification
evidence through GitHub itself when the artifact blob host is unreachable from the review
environment. It cannot qualify or publish a release.

The manifest starts disabled. To prepare one export:

1. Create `codex/evidence-review-export-20261015` from the reviewed source commit.
2. Fill `manifest.json` with completed, successful qualification run and artifact identities.
   Pin every run, head, artifact name, archive byte count and digest. Select individual files by
   exact member path, byte count, digest and media metadata. Only producer-screened PNGs,
   transcript-free summary JSON and public narration audio are accepted.
3. Set `ready` to `true`, commit the preparation and run the local tests.
4. Confirm that `codex/evidence-review-artifacts-20261015` does not exist.
5. In a child commit, add `.github/evidence-review-export-20261015.activate` containing only the
   40-character preparation commit SHA and push that marker-only child.

The workflow verifies the marker, successful run identities, artifact API metadata, downloaded
archive digests, zip bounds and every selected file. It creates a new orphan review branch with
only the selected media and `REVIEW-MANIFEST.json`. It uses a non-force push, so it cannot replace
an earlier review branch. Delete both temporary branches after review.
