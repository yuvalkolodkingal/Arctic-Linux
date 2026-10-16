# Private qualification media review exporter

This observer-only reader copies a bounded, declared subset of successful exact-image
qualification artifacts into a GitHub **draft** release. Draft releases in this public repository
are visible only to collaborators with repository write access. The helper never publishes the
draft, updates a release gate, or marks human review complete.

The exact-image manifest pins successful idle-installer run `38887504669`, attempt 1,
head `dc6e20313a48b2b2240518f0731f21e06aa18161`, and artifact `12040551529`
(`candidate-installer-restoration`, 998,501 archive bytes, SHA-256
`d0ad8f3c13865227ea932add6659f56873773efa1e5dc58ea77c647cc9c00f5e`), plus successful
active-installer run `38887511889`, attempt 1, head
`3b264391a2b57682863f876695633dffb5b6d587`, and artifact `12040099765`
(`candidate-installer-active-restoration`, 433,134 archive bytes, SHA-256
`2aa001157b7d6180ec60e9b3b9f81fef88cba1eef6466263b6d4a30ad781aacf`). The producer upload
logs confirm the declared complete schemas still contain exactly 29 and 27 files. The exporter
selects only the fixed 12 idle and 7 active 1280×720 PNG allowlists plus a generated
`REVIEW-MANIFEST.json`. Logs, raw archives, audio, transcripts and VM images are never copied to
the draft release.

Before export, the reader verifies the repository, completed successful run, attempt, head branch
and SHA, workflow ID/name/path/event, artifact ID/name/size/digest, and producer screening scope.
It rejects unsafe, duplicated, encrypted, special, oversized, undeclared or high-expansion ZIP
members. Every member is streamed to verify its CRC and SHA-256 against the producer's complete
`upload-screening.json` inventory. Selected PNGs must decode at their declared dimensions, contain
only `IHDR`/`IDAT`/`IEND` chunks, carry no metadata or trailing bytes, and pass bounded English and
Hebrew OCR screening for credential, identity, queried-URL and transcript shapes.
The active getty capture may contain only the exact cursor-only OCR line `Password: _` (or
`Password: |`); any value-shaped password text still fails closed.

The manifest format accepts additional fixed artifact declarations for the active-installer,
native, dictation and showcase workflow paths. Each addition must pin the new successful run and
artifact identity, exact complete ZIP member schema, and an explicit PNG allowlist. The global
file, archive, expansion and export limits remain fixed.

Activation uses a marker-only child commit on
`codex/private-media-review-exporter-20261016`. The marker
`.github/private-media-review-export-20261016.activate` must contain the reviewed preparation
commit. A read-only job owns artifact download, Pillow/Tesseract decoding and privacy screening.
It writes a new deterministic ZIP containing only the screened PNGs and metadata, and passes its
SHA-256 through the workflow dependency. A separate publication job has write permission, does not
install or invoke any image or OCR decoder, and rejects any bundle that differs from that hash or
its internal file hashes.

The publication job requires structured HTTP 404 responses for both the release and Git ref before
it creates anything. It creates the new tag at the activation commit, proves that tag resolves to
that commit, creates only a draft release, uploads only the declared files, verifies every asset
size and GitHub SHA-256 digest, then rechecks the tag and draft state. Any later failure deletes and
verifies absence of both the confirmed-new release and tag. If the release-create response is lost,
the publisher recovers it by tag only when draft state, name, body and activation identity all match
exactly. A nonidentical or unverifiable object is never deleted; the workflow fails and reports that
the private draft may need manual removal.

After the workflow succeeds, an authenticated collaborator can inspect the hidden draft with:

```sh
gh api repos/yuvalkolodkingal/Arctic-Linux/releases/tags/private-qualification-review-20261016
```

Download an asset using its numeric asset ID from the draft response:

```sh
gh api -H 'Accept: application/octet-stream' \
  repos/yuvalkolodkingal/Arctic-Linux/releases/assets/ASSET_ID > review-asset
```

The downloaded `REVIEW-MANIFEST.json` deliberately records `human_review: pending` and
`release_acceptance: false`. Review decisions belong in the later exact-image release manifest;
this transport cannot make them.
