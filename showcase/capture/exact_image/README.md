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
`38823208615`, attempt 1, source
`cfc39dad61125e4fa8fb7906ac14f4c360b58228`: ISO
`Arctic-Linux-1.2-candidate-38823208615-1-x86_64.iso`, size `1936271360`,
SHA-256
`c13c4589d7b522fec7dbd5eeafec00cf9088d8788cdfb6771a7382285846d7c7`.
The retained artifact is `12016177474`, archive size `1936459062`, archive
SHA-256
`5f77dbf607abdada5ed140ae8635314554d5d2f03f88f1f5831e3d53bc18cf23`,
producer mode `frozen-external-paired-v1`, and producer receipt SHA-256
`82d102432819e8cc2f9d27b020f54a21021a176daa930e675c75229273ab7330`.
The execution manifest is ready for a later marker-only activation and remains
`release_acceptance:false`.

The producer ran from the reviewed marker-only source
`cfc39dad61125e4fa8fb7906ac14f4c360b58228` by `workflow_dispatch` and passed
UEFI Try, BIOS Install and UEFI Safe startup. This preparation preserves the
existing showcase activation marker byte-for-byte, so its push does not
activate the workflow. A later marker-only child commit is still required.

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
GRUB's reviewed menu lasts five seconds. QMP pixel decoding is much faster than
OCR, so the controller recognizes the immutable 1920x1080 amber Try highlight
and immediately sends a fixed Home key with QEMU's 100 ms key-up timer. This
stops the countdown before OCR verifies the full menu. The first exact-candidate
retry showed why the ordering matters: OCR proved the menu at six seconds, but
the subsequent ten-second window never established an Install selection.
The controller then sends Down and requires both the ordered, fixed menu copy
and the amber Install-row highlight before it sends Enter. This prevents a
missed firmware key from silently leaving the default Try entry selected. The
earlier bounded failure projection proved that the menu and key sequence
preceded a 600-second Welcome timeout; because it exported no pixels or guest
mode, it did not establish which entry booted. After selection, the
controller still requires copy unique to the real installer Welcome page
(`Welcome to Arctic Linux`, `Keyboard`, `Time zone`, and `Summary`) before
switching to the private console. Neither the selection proof nor the boot
menu's own `Install Arctic Linux` label can satisfy that Welcome gate.

The Welcome gate remains the authoritative, unchanged 600-second acceptance
condition. If it times out, a diagnostic path runs only after that failure. It
reduces each already-private QMP frame to a fixed surface enum and bounded
elapsed seconds, then attempts one bounded VT6 probe. The probe reports only
whether the selected kernel mode is `install`, the Mango process is present,
and the exact packaged installer command is present. These untrusted facts can
separate a boot-menu/input failure, a slow graphical session, an absent or
stopped installer, a wrong visible surface, and an output/OCR mismatch. They
cannot turn a failed capture into a pass or authorize input or publication.
Every diagnostic screenshot and OCR string remains in the private runtime and
is deleted before the closed projection is written.

The only guest transport is the owned
`org.arctic.showcase.capture` virtio-serial channel. The live guest receives a
deterministic reviewed tooling archive over it, drives the real installer only
through its existing IPC, and chooses the fixed online, unencrypted, whole-disk
installation. The disposable `arcticshowcase` account uses autologin only inside
the isolated VM. After the installer's normal cleanup unmounts its target, the
reviewed live helper remounts only the unique Btrfs `Arctic root` partition below
the exact serial disk, seals its `@` subvolume, and unmounts it before reset. On
the installed boot, the root wrapper activates the unique Wayland VT before it
drops permanently to UID 1000 for scene work. It opens the one already-proved
root-owned virtio channel before that drop, passes only that held descriptor
through `runuser`, and the non-root helper verifies that the inherited device
identity still matches the fixed named character device before using it. The
helper also revalidates the exact graphical environment selected by the root
launcher instead of racing a second loginctl and `/proc` discovery. This keeps
scene bootstrap independent of a second uaccess open or session discovery
during the VT transition without broadening device access. After observing the exact
candidate's animated greeting, the host sends one empty command terminator. Its
3D renderer deliberately leaves that single ordinary byte queued for Fish,
which completes the empty command and establishes its line editor while the
rich greeting remains visible. After a fixed three-second handoff interval, the
host types one fixed nonsecret proof and then sends a fresh 128-bit challenge
over the held virtio-serial connection. The installed interactive Fish reads
that challenge from the root-owned character device. It emits a response only
after checking UID 1000, the exact account and hostname, interactive Fish state,
the device type and root ownership. The response binds those fixed facts to the
host nonce. The reviewed tooling archive is deliberately withheld until this
exchange passes, so no guest helper can answer it.

The same guarded Fish branch defines `fish_prompt` only in the disposable
session. It renders only the fixed `~>` suffix in bright white, then clears and
homes the VT before printing a bold marker. Fish itself invokes that prompt after
the proof command returns. The host keeps full-frame OCR for privacy screening,
then maps only nonblack glyph pixels
in the marker and prompt rows within the fixed left 640×32 pixels to white. It
reads each private row through an 8x nearest-neighbour enlargement and pinned
single-line PSM 7. Both transformed crops are always deleted; the
original 1280x800 frame remains the sole screen evidence and geometry gate.
Pinned PSM 7 can return an empty string for the isolated two-glyph prompt, so
the visual half requires the exact OCR marker together with one of the two
measured nonblack occupancy vectors for `~>` with or without the Fish cursor:
`542,364,20,8` or `542,364,20,24`, followed by twelve empty bands. This rejects
the former account prompt, any extra account or row, altered glyph geometry and
every non-1280x800 frame. The nonce-bound response proves the exact account,
hostname, UID and Fish shell without relying on OCR for that identity. A
missing marker, alternate occupancy, extra row, wrong nonce or different
session identity fails closed. A second unchanged exact frame is required
before the sudo launcher. Neither guest diagnostics, an echoed command, a
settling delay nor marker pixels alone can authorize input.

The installed session and visual prompt remain an authoritative bounded gate.
The channel response has a 30-second limit and the visual gate has a 90-second
limit. Its failure
projection reduces private frames to closed enums for fetch still visible,
exact prompt on a nonfinal row, the fixed proof marker, account-only or
suffix-only OCR, login/password, blank output, geometry mismatch, OCR-empty,
and other text, plus bounded integer timings. Each sample also retains four
independent booleans for the exact fixed marker, the account pattern with only
the acceptance-approved punctuation spacing, suffix and complete prompt, with
only their boolean seen/final aggregates exported. It records only the challenge
SHA-256 and a fixed closed identity enum for a successful transport proof. After
full-frame geometry and privacy validation, it also exports bounded
nonblack-pixel counts for
sixteen fixed 640x8 bands at the top left. Those integers can locate the VT
glyph rows but contain no pixels, text, crops, screens or identifiers. OCR
strings remain private. Only after a timeout, the
controller sends one interrupt and records
whether the exact prompt becomes visible within 30 seconds. That post-failure
probe cannot promote the attempt or authorize the proof or sudo commands. Its
screens and OCR strings stay private and are deleted with the runtime.

The installed helper must prove local dictation is fully ready
with one supported multilingual profile before the host will observe the
Dictation scene. A missing model, failed online setup, GPU/CPU mismatch, or timeout
fails the job; no fixture or alternate screen is substituted.
The readiness observer runs the fixed `arctic-dictation status` command in its
own process group with file-backed bounded output. Its existing 30-second
command timeout kills that complete group, so a surviving descendant cannot
hold a stdout pipe open past the unchanged 30-minute readiness gate.

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

The installed scene helper has the same fail-closed transport behavior. If it
fails before a readiness or capture request, it emits only the fixed prefix and
one of `bootstrap`, `dictationsetup`, `winter` or `updates`; exception text,
logs, transcript text and pixels never cross the channel. The host validates
that enum and ends the attempt immediately. Before each readiness gate the
helper also emits only a fixed scene-start prefix and the expected scene enum.
The host requires the enum in order and binds a later silent timeout to that
stage without accepting the scene or extending its deadline. It uses a
36-minute transport bound
for the online Dictation path so the unchanged 30-minute Dictation readiness
gate and unchanged two-minute Settings readiness gate can finish their bounded
subprocess calls and still deliver that fixed failure enum. Wallpaper retains
its five-minute bound, What's New its three-minute bound, and each
post-authorization diagnostic request its five-minute bound.
These bounds do not replace or relax any readiness, nonce, screen, privacy or
human-review gate; they only prevent a failed guest helper from inheriting the
outer 120-minute channel timeout while QEMU keeps the character device open.

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
and contains no guest text, error strings, logs, screenshots or pixels. Its
live-startup section, once the controller exists, contains only fixed enums and
integer seconds;
the contract rejects extra keys, flexible strings and out-of-range values. The
workflow first proves that all private runtime, image and capture paths were
removed. If that cleanup cannot be proved, it uploads no failure artifact.
The workflow installs Noble's exact `tesseract-ocr=5.3.4-1build5`; the binary,
version, language data and all three OCR invocations are pinned in the receipt
contract. Full-frame privacy and scene OCR stays on sparse-text PSM 11. Only the
two private normalized shell rows use single-line PSM 7 before their separate
privacy checks and guaranteed deletion.

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
