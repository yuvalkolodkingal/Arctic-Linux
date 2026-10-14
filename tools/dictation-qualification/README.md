# Direct VoxType image qualification

This lane qualifies Arctic's integration of the official VoxType 1.1.0 release.
Arctic may select, verify and configure the upstream binaries, but it does not own
recording, transcription or insertion. Every recording control in this checker
invokes `/usr/bin/voxtype record start|stop|toggle|cancel` and every state check
reads `$XDG_RUNTIME_DIR/voxtype/state`.

The exact upstream release is fixed to source commit
`e2638ca63f566f1682bcedc0abea8e4b25211c21`. Release checksums must have a valid
signature from fingerprint `9CCF7915B750CAE8B095ED1AA3FC9F33FD209279`.
The contract pins every selected binary and model by byte size and SHA-256. The
qualification CD contains public FLEURS audio and private references only. It
never supplies a runtime, model, readiness marker, configuration or transcript.

The execution manifest remains disabled until an exact image under
`2,000,000,000` bytes, fixture manifest and execution tree have been reviewed.
Source checks cannot qualify an image and this lane never claims release
acceptance.

## Direct integration contract

The installed integration must provide:

- `/usr/bin/voxtype`, a small selector for the verified official binary.
- `/opt/arctic/voxtype/1.1.0/voxtype-{baseline,avx2,vulkan}` for selected,
  verified upstream executables and `/opt/arctic/voxtype/models/` for the
  selected verified multilingual model. Initial setup installs one CPU binary
  and one model; Vulkan remains an explicit later opt-in.
- `/usr/bin/arctic-dictation`, limited to setup status, retry, language and
  backend configuration. The checker requires it to reject recording verbs.
- `/usr/libexec/arctic/arctic-voxtype-setup`, the privileged pinned downloader.
- `/usr/libexec/arctic/arctic-voxtype-host-profile`, the common all-logical-CPU
  compatibility/AVX2 selector used by setup, status and the runtime selector.
- `/usr/libexec/arctic/arctic-voxtype-configure`, the bounded per-user managed
  config writer used by setup.
- `/usr/lib/systemd/user/voxtype.service`, running the canonical per-user config
  through `/usr/bin/voxtype ... -q daemon`, with a private umask, AF_UNIX-only
  sockets and inherited config/log overrides removed.
- Per-user `~/.config/voxtype/config.toml` with local Whisper, constrained Hebrew
  and English, `state_file = "auto"`, upstream evdev hotkeys disabled, wtype as
  the only insertion driver and transcript notifications disabled.
- Mango activation through the transcript-suppressing
  `/usr/bin/arctic-dictation-toggle` readiness guard, which invokes upstream
  `record toggle`, plus a direct upstream `record cancel` binding.
- `/var/lib/arctic/dictation/upstream-direct-v1` plus the flat
  `/var/lib/arctic/dictation/verified.json` receipt only after both selected
  payload files pass their pinned size and SHA-256 checks.
- A desktop user outside the `input` group.

The setup receipt binds version, upstream source commit, signing fingerprint,
selected user/profile/backend, exact binary and exact model. Configuration and
receipt files cannot substitute for the installed bytes: the guest rehashes the
real executable and model before any speech session.

## Required installations and boots

Each hardware profile performs six distinct boots and produces six reports:

1. A fresh online install live boot proves the live root has no VoxType payload
   or Whisper weights.
2. Its installed boot must already be ready. The installer must have downloaded
   and verified the selected upstream binary and multilingual model without
   copying them from the test CD.
3. A separate fresh offline install live boot repeats the absence proof.
4. Its installed boot must retain a clear retry queue, disclose exact download
   bytes, keep the OS healthy and reject recording.
5. The same encrypted disk boots online; the retry path completes setup.
6. That recovered disk reboots without outside network access and repeats the
   complete local session.

All boot IDs are unique. Online and offline installation disks must differ. The
offline install, recovery and recovered boot share the same LUKS, filesystem and
partition identities. The Small lane masks AVX/AVX2/FMA/F16C/BMI and exercises
the baseline binary. The modern lane exposes the complete optimized CPU feature
set. Both lanes use the same retained ISO and reviewed checker.

## Session gates

The guest creates a private mono 16 kHz PipeWire source and routes public audio
through the real upstream daemon. A disposable GTK3 Wayland window receives
actual wtype output under Mango. Five fixed English and five fixed Hebrew rows
are measured. Reports retain hashes, edit counts and `monotonic_ns` durations;
they never retain transcript text. These read-speech measurements do not prove
general accuracy or Whisper parity.

The complete installed session requires:

- Direct upstream start, stop, toggle and cancel command support.
- Native `idle`, `recording`, `transcribing` and bounded state handling from the
  upstream state file.
- Exact local-only Hebrew/English configuration and no broad input-device access.
- English and Hebrew transcription with actual focused-window insertion.
- Active cancellation, lock cancellation, missing-model and microphone-loss
  handling without inserted text.
- A visible recording indicator captured while the receiver is empty. The host
  screenshot nonce binds the PNG to the exact boot and report.
- No surviving private transcript files.
- No twelve-character rolling fragment of an actual hypothesis in the bounded
  journal interval, notification history, setup status or state surfaces.
- Offline transcription after outside HTTP reachability has been disproved.

The modern lane injects a private Vulkan ICD that names an absent library. The
failed attempt must insert no text. The checker then **explicitly** selects CPU,
restarts the upstream user service and completes new English and Hebrew
recordings. A GPU error never counts as automatic CPU fallback. This VM fixture
does not certify physical GPU acceleration or a physical driver failure. The
legacy lane separately proves that Vulkan selection is rejected and that an
explicit CPU selection succeeds.

## Evidence and privacy

The serial marker is `ARCTIC-DICTATION-QUALIFICATION ` followed by an
`arctic-voxtype-image-v3` JSON object. Unknown fields, arbitrary diagnostic text,
transcript-bearing observations, duplicate gates, changed pins, incomplete
language samples, reused boots/disks and a single hardware profile all fail the
contract.

Only validated transcript-free JSON, fixture provenance, execution identities
and the two empty-receiver indicator PNGs per hardware lane may be uploaded.
Raw serial logs, journals, audio, references, GTK receiver files and hypotheses
remain private.

Run source controls with:

```sh
python3 -m unittest discover -s tools/dictation-qualification -p 'test_*.py' -v
```
