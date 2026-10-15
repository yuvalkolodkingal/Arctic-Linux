# Exact-image showcase capture

This lane creates three of the five pending showcase images from one installed
copy of the reviewed ISO: Dictation setup, wallpaper hide/restore and What's New.
It is capture evidence only. Every receipt remains
`release_acceptance:false`, `status:captured_unreviewed`, and
`privacy.human:pending` until a person reviews the exported pixels.

The recording/text-insertion and GPU-failure/CPU-recovery dictation scenes are
outside this unattended lane. They remain pending exact-image captures with
their own complete receipts and human pixel review before the source can render.

The preparation is bound to the reviewed candidate from producer run
`38707130991`, attempt 1, source
`fc501fdf90c17c617b15b8b13038d062d519fcc6`: ISO
`Arctic-Linux-1.2-candidate-38707130991-1-x86_64.iso`, size `1936185344`,
SHA-256
`92fe2a1bcb9a67b8ed72e7b38d065e7e68ae26a38e930042a752aae7146e8d66`.
The retained artifact is `11961831325`, archive size `1936373046`, archive
SHA-256
`1c1e3e34e240b9e6ec592e3bce23330378e6bc2a7815ab295080fa61925082c3`,
producer mode `frozen-external-paired-v1`, and producer receipt SHA-256
`9d755876dc45d143506da8b52cf98d92205ab1d2f014355de612db0bb04bc9b4`.
The execution manifest is ready for a later marker-only activation and remains
`release_acceptance:false`.

The producer ran directly from final `main`
`fc501fdf90c17c617b15b8b13038d062d519fcc6` by `workflow_dispatch`.
The activation marker remains byte-for-byte identical to the fixed remote lane.

When activated, the workflow downloads the newly bound artifact with the
existing strict `fetch-image.py` verifier. It checks the producer workflow,
first attempt, source, startup lanes, artifact archive, ISO, BUILD-INFO,
checksum, and producer receipt before QEMU starts.

## Unattended trust boundary

`capture_vm.py` creates one protected 64 GiB blank raw disk, opens the exact ISO
through a held file descriptor, and starts one `/usr/bin/qemu-system-x86_64`
process. The disk has serial `ARCTICSHOWCASE121`, boot index 0, and no backing
file. The fixed virtio VGA exposes one EDID-backed 1280×800 output. The ISO has
boot index 1. The same QEMU process is kept from the blank-disk
ISO boot through installation, ISO ejection, reset, installed boot, all three
captures, and shutdown. There is no test CD, writable host share, SSH, VNC,
tmate, host-forwarded port, or external control service.

The host owns all input through QMP. `automation.py` permits only fixed bounded
key sequences, reviewed command text, one disposable credential input, and the
wallpaper pointer click derived from host OCR of the exact QMP framebuffer. Each
transition has a finite timeout. Screens used for a decision are strict 1280×800
RGB QMP PNGs, pass the same automated privacy rules as final captures, and are
deleted. Their byte, pixel-source, and OCR hashes are recorded in the controller
trace. The full QEMU argv hash, exact ISO/disk/channel topology, fixed scene
commands, QMP events, input events, and final pixels are bound into each receipt.

The only guest transport is the owned
`org.arctic.showcase.capture` virtio-serial channel. The live guest receives a
deterministic reviewed tooling archive over it, drives the real installer only
through its existing IPC, and chooses the fixed online, unencrypted, whole-disk
installation. The disposable `arcticshowcase` account uses autologin only inside
the isolated VM. After the installer's normal cleanup unmounts its target, the
reviewed live helper remounts only the unique Btrfs `Arctic root` partition below
the exact serial disk, seals its `@` subvolume, and unmounts it before reset. On
the installed boot, the root wrapper activates the unique Wayland VT before it
drops permanently to UID 1000 for scene work. The host proves the Fish session
with its fixed `ARCTIC-SHOWCASE-SHELL-READY` command before starting that wrapper.
The installed helper must prove local dictation is fully ready
with one supported multilingual profile before the host will observe the
Dictation scene. A missing model, failed online setup, GPU/CPU mismatch, or timeout
fails the job; no fixture or alternate screen is substituted.

Guest diagnostics remain untrusted. They cannot choose an input, scene, OCR
expectation, pointer target, screenshot, receipt field, or acceptance state. The
host follows the fixed scene order `dictationsetup`, `winter`, `updates`, checks
each visible surface independently from QMP pixels, and only then authorizes the
one-use request. Changing or forging guest diagnostic JSON produces the same
host receipt for the same pixels. The guest-local installed marker is contextual
evidence and never release acceptance.

The live installer helper also emits a fixed, content-free lifecycle projection
over the same owned channel. Each message contains only a sequence number, one
reviewed stage name and `started`, `passed` or `failed`; the host rejects skipped,
reordered, duplicated or post-failure messages. This projection does not enter a
successful capture receipt and cannot relax an installer, screen, scene, privacy
or human-review gate. It lets a guest-side IPC, installer or seal failure end the
host wait promptly instead of leaving QEMU's still-open character device silent
until the outer channel timeout. The pre-Python shell has a fixed EXIT trap that
can emit only the sequence-zero `live-helper:failed` projection when archive
validation, extraction or Python launch fails. The host also limits the first
bootstrap record to five minutes and applies reviewed per-stage deadlines after
that; only the real installation stage retains its 90-minute allowance. An
unexpected Python `Exception` is re-raised after a best-effort fixed failure
record, so its message and guest content never cross the private channel.

The fresh disposable account's top-layer welcome is expected. After the
Dictation page is open behind it, the host requires `Welcome to Arctic Linux`
pixels, sends one QMP Escape, and requires both `Dictation is ready` and the
reviewed Dictation page copy. The same ready screen is checked again after guest
diagnostics and immediately before capture.

The winter pointer target is found by the approved Tesseract binary and fixed TSV
invocation from the unique visible `Butterfly in Gold` title. A fixed geometric
offset selects its Hide control. The controller then independently requires the
real `Hide “Butterfly in Gold”?` dialog text before capture. The dialog remains
visible while the guest performs the packaged hide/restore diagnostic.

## Pixel and privacy contract

Every trigger nonce is one-use. The host takes one new QMP PNG, rejects any
metadata, unexpected PNG chunk, wrong mode, wrong size, CRC error, trailing byte,
or privacy match, and losslessly re-encodes the unchanged RGB pixels without
metadata. Email addresses, IP and MAC addresses, `/home`, `/var/home`, `/root`,
private sentinels, and optional private transcript fragments are blocked. Raw QMP
PNGs and controller decision screenshots are deleted. Final normalized images
are rechecked during export and independent validation.

After the three captures, the host quits QEMU, stops the complete process group,
closes the QMP/channel and image descriptors, retains exactly the three screened
normalized PNGs, and removes the private disk/log/socket/runtime tree before it
finalizes receipts. That cleanup event and the literal QEMU argv plus its hash
are present in every receipt. The screened source directory is removed after
the deterministic bundle is exported.

The deterministic USTAR bundle contains exactly three normalized PNGs, three
receipts, and `bundle.json`. An external digest contract binds every member, the
archive, OCR identity, controller trace, image identity, and VM provenance. The
validator requires the published digest-contract SHA-256 and reruns all pixel and
privacy checks. Human review remains mandatory after download.

## Workflow

`.github/workflows/showcase-exact-capture-20261014.yml` runs only on the trusted
`codex/showcase-exact-capture-20261014` branch when the sole activation marker
changes, and only on attempt 1. The activation commit must be a direct child of
the reviewed preparation commit and may change only
`.github/qualification-20261014.showcase-capture`. The workflow has read-only
repository and Actions permissions, verifies every execution-file hash, uses a
GitHub-hosted Ubuntu 24.04 KVM runner, and uploads a successfully validated,
bounded `exact-image-showcase-captures-unreviewed` artifact for 14 days. A failed
host attempt may instead upload one separately validated failure projection. It
is at most 32 KiB, mode 0600 before upload, remains `release_acceptance:false`,
and contains no guest text, error strings, logs, screenshots or pixels. The
workflow first proves that all private runtime, image and capture paths were
removed. If that cleanup cannot be proved, it uploads no failure artifact.
The workflow installs Noble's exact `tesseract-ocr=5.3.4-1build5`; the binary,
version, language data and both OCR invocations are pinned in the receipt contract.

The host invocation is:

```sh
showcase/capture/exact_image/capture_vm.py host \
  --candidate-iso /private/Arctic-Linux-1.2-candidate-${RUN_ID}-1-x86_64.iso \
  --output /private/arctic-showcase-captures \
  --failure-report /private/showcase-failure-projection.json \
  --display none --accel kvm --unattended --timeout 7200
```

Validate a transported result using the digest SHA printed by the host:

```sh
showcase/capture/exact_image/validate_bundle.py \
  /private/arctic-showcase-captures \
  /private/arctic-showcase-captures.digest.json \
  /private/arctic-showcase-captures.tar \
  --expected-contract-sha256 '<64 lowercase hex>'
```

Run local contract and controller tests with:

```sh
python3 -m unittest discover -s showcase/capture/exact_image -p 'test_*.py' -v
```

Earlier run `38501272459` reached the real live installer with the superseded
candidate but produced no installed-image seal within the original 90-minute
private-channel wait. Run `38509763052` used the extended timeout and was
cancelled during capture; neither run produced an artifact. The prepared final
candidate keeps the same 85-minute online-install completion budget used by the
dictation qualification lane and gives the private host channel 120 minutes.
Acceptance rules and capture predicates are unchanged.

Final-candidate run `38627574077` later timed out on the first host channel read,
before the installed-disk seal, ISO ejection, reset, installed boot or any scene
capture. The old protocol exported no partial state and discarded the private
runtime, so that run cannot identify which guest-side installer, IPC, mount or
seal operation stopped. Its roughly 120-minute wait proves only that QEMU kept
the virtio-serial connection open after the helper stopped or became silent.
The bounded lifecycle projection fixes that observability and early-termination
defect. A fresh exact-image run is still required to establish whether the
underlying operation succeeds; the old timeout is not reusable capture evidence.

These tests cover the transport, fixed VM topology, QMP input records, OCR-derived
pointer, exact online installer choices, dictation readiness gate, guest-forgery
isolation, pixel/privacy checks, cleanup, deterministic export, and external
digest validation. A fresh attempt-1 Actions run is still required for the pinned
final candidate to test boot timing, online dictation download, installer UI,
installed session and OCR geometry. Passing mocks alone does not qualify the
images.
