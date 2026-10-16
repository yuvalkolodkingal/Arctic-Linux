# Private qualification media review exporter

This observer-only reader copies a bounded, declared subset of successful exact-image
qualification artifacts into a GitHub **draft** release. Draft releases in this public repository
are visible only to collaborators with repository write access. The helper never publishes the
draft, updates a release gate, or marks human review complete.

The initial manifest pins idle-installer run `38874179588`, attempt 1, and artifact
`12033829931` (`candidate-installer-restoration`, 1,001,204 archive bytes, SHA-256
`06e44634f252c77ea7ba9eb07caf8d0fb62fc8d57c27ee87eedf8f08aac130a2`), plus active-installer
run `38874201005`, attempt 1, and artifact `12035641163`
(`candidate-installer-active-restoration`, 433,734 archive bytes, SHA-256
`1efe81599bb06b836f1e7565de2250c7f122f1811644405e29124a018a95757c`). It exports only the
19 declared 1280×720 PNG captures and a generated `REVIEW-MANIFEST.json`. Logs, raw archives,
audio, transcripts and VM images are never copied to the draft release.

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
