# Dictation image qualification

This helper exercises the installed controller and the verified Voxtype 1.1.0
CPU/Vulkan binaries and the actual hardware-selected multilingual Whisper model:
Small/baseline on the legacy profile, Turbo Q5/AVX2 on the modern profile. It has
no runtime/model download cache or readiness override. Its source controls do
not qualify an image. No dispatch or publication runs on import.

The host must first pin the built ISO bytes, full SHA-256, product source,
controller/child-guard hashes, checker tree, tool-container identity and prepared
FLEURS fixture digest. The ISO limit is strictly `2,000,000,000` bytes. Keep the
execution manifest disabled until the final image and exact execution code are
independently reviewed. Image and release publication gates remain separate.

## Test CD layout and API

The reviewed host runner stages these files on its read-only data CD:

```text
/run/t/dictation-context.json
/run/t/dictation-qualification/guest_check.py
/run/t/dictation-qualification/contract.py
/run/t/dictation-accuracy/accuracy.py
/run/t/dictation-accuracy/pins.json
/run/t/dictation-fixtures/fixtures.json
/run/t/dictation-fixtures/<ten pinned WAVs and private references>
```

Prepare the fixtures with the existing `tools/dictation-accuracy/accuracy.py
prepare` command. Omit its `--payload` option: no host speech executable or model
is copied into the guest. Keep the FLEURS CC-BY-4.0 attribution in that directory's
README. The first five test rows per language are fixed; failed rows cannot be
replaced with easier speech. The manifest itself is transcript-free.

The installed-image wrapper invokes:

```sh
python3 /run/t/dictation-qualification/guest_check.py live --disposable-guest
python3 /run/t/dictation-qualification/guest_check.py installed --disposable-guest
```

The wrapper must propagate the helper exit status. Guest guards require root,
QEMU/KVM, the reviewed `/run/t` location, the actual boot stage and exactly one
non-root Mango session. Every helper and installed controller/child guard is
hashed again against the supplied context before exercising setup or recording.
SELinux stays enforcing and audit enabled/lost counters plus the new journal
and audit-file interval are checked without changing policy.

Context schema `arctic-dictation-context-v2` has the exact `CONTEXT_KEYS` defined
in `contract.py`. All hash identities are full SHA-256 except `source_sha`, which
is the full 40-character Git commit. `installation_id` is the host's new UUID for
each fresh disk. `phase` is `online-installed`, `offline-installed`, `recovery`
or `recovered-offline`; the live invocation overrides only that field to `live`.
`hardware_profile` is pinned to `small-v2` or `turbo-q5-v3`. The guest checks the
actual all-processor CPU flags, root-owned profile selection, controller whitelist,
status descriptors and receipt against that expected profile. Controller and
child-guard hashes come from the source actually built into the ISO. The host
context is never a readiness receipt. Fixed file pins are independently defined
in the contract and checked against the actual controller; source controls reject
stale Small constants and substituted models, binaries, hashes or byte types.

## Required four invocations per hardware profile

Use two new encrypted disks, unique output directories and the ISO's shipped
installer. Supply no `--installer` override and do not use `--test-online` to
simulate network detection.

1. Fresh online install: `--stage all --install-network online --boot-network
   offline`, phase `online-installed`. The live probe rejects payload/model files
   in the immutable live root. The installer must download pinned binaries,
   dependencies and weights into its actual target. The installed probe must
   already be ready before it does anything that could install dependencies.
2. Fresh offline install: `--stage all --install-network offline --boot-network
   offline`, phase `offline-installed`. The installed OS must reach the real
   desktop, retain its enabled first-boot timer and pending setup, disclose
   the download size and reject recording. Model/dependency failure must not
   undo the OS installation.
3. Recovery of that same offline disk: `--stage boot --boot-network online`,
   phase `recovery`. The first-boot service may finish before the desktop is
   ready; this is accepted. The helper invokes the shipped fixed setup wrapper
   idempotently and waits for verified readiness and removal of the queue. This
   checks service recovery; the interactive polkit authorization dialog needs
   its own review.
4. Reboot that recovered disk: `--stage boot --boot-network offline`, phase
   `recovered-offline`. Repeat the real transcription and failure cases using
   the newly installed payload while the guest has no outside HTTP reachability.

Each profile executor requires six reports: the two live reports and four installed
reports. All six actual boot IDs must differ. Online/offline disk LUKS and root
filesystem UUIDs must differ. Offline installation, recovery and recovered boot
must share observed LUKS, filesystem and partition UUIDs as well as the declared
installation ID. A context UUID alone does not prove disk continuity.

The hosted workflow has two parallel matrix jobs and distinct artifacts:
`dictation-candidate-qualification-small-v2` and
`dictation-candidate-qualification-turbo-q5-v3`. Each job retains its own four-VM
budget and all six reports. The fixed host CPU fixture masks AVX/AVX2, FMA, F16C
and BMI1/2 from the original QEMU CPU model for Small; Turbo retains the original
CPU model and must expose the complete required v3 flag set. It cannot accept
arbitrary QEMU arguments. This tests the compatibility executable on a guest
without the optimized ISA. Both jobs use the same retained ISO, source, checker
and fixtures; final validation requires twelve distinct boot IDs and independent
profile installation disks.

`--install-network` and the bundle-copy/indicator-observer hook are host-runner
integration work; this helper does not modify the shared VM harness.

## Actual session and bounded fault cases

The guest uses its shipped `pw-loopback`, `pw-play`, `pw-dump` and `wpctl`. It
verifies required loopback options against the actual installed `--help`, creates
one disposable mono 16 kHz sink/source pair, observes those exact nodes, selects
the source, and verifies a real link to the owned speech process before playback.
The audio reaches the controller through ALSA/PipeWire, rather than through a
replacement speech engine or a fabricated transcript file. Default input is
restored, the fixture node/process is removed and private files are erased.
Missing tool flags or route proof fail the session prerequisites.

A disposable GTK3 Wayland text window receives actual `wtype` insertion. Its
fresh window, process identity and focus are observed through Mango. After
completion the receiver text must settle, be nonempty, contain Hebrew letters
for Hebrew samples, and contain no unintended Enter. Five fixed utterances per
language run through the CPU controller. The report includes reference/edit
counts and hashes, not transcript text. WER is `sum(word_edits) /
sum(reference_words)`; CER uses the corresponding character counts. Timing uses
integer `monotonic_ns` and includes recording, model startup and insertion. These
read-speech measurements establish neither general accuracy nor Whisper parity.
Automatic detection and mixed-language speech are not measured here.

The helper also checks active cancellation, broker parent death, model removal
and restoration, loss of the virtual microphone, genuine shell lock cancellation,
private transcript cleanup, and the published recording status. Loss of the
virtual source cannot certify a microphone-error path if another source remains
available; that case is `unrun`, not a product failure or a passing assertion.
The lock test emits the existing `ARCTIC-DESKTOP-UNLOCK-REQUESTED` marker only after
actual shell lock acquisition. The host's explicit interactive mode supplies
only the disposable test password. Fallback swaylock normal/crash handling is
outside this shell-lock case and needs separate coverage.

For GPU retry, a real guard-approved Vulkan recording must first start. A pidfd
then kills only the observed engine PID/start identity. The controller must
advertise CPU recovery, and actual Hebrew and English recordings must succeed
on CPU while the preference is still forced Vulkan. This tests runtime failure
recovery and does not prove physical GPU acceleration or a real driver-error
path. No fake render device, monkeypatched GPU check or readiness bypass is used.
For the modern Turbo lane, unavailable selectable Vulkan leaves the GPU gate
`unrun` and the session report failed, even if every CPU case passes. The legacy
Small lane has a separate `legacy-gpu-unsupported-cpu-retry` gate: it confirms
Vulkan recording is rejected with an actionable error, then completes the two
actual Hebrew/English CPU retry recordings. Its observations explicitly declare
`gpu_supported:false`; this result cannot substitute for the modern GPU-failure
gate. The final publisher must require both hardware executions.

The modern lane also requires `gpu-loader-fault-handling-new-cpu-retry`. After the
process-failure gate, the checker cancels capture and replaces only its owned
broker while holding the shipped launch lock. A fresh socket peer, broker
PID/start identity and actual Vulkan child environment must show the private
bad-ICD manifest and `VK_LOADER_DEBUG=error`. The manifest names an absent
library; no system driver, model, receipt or render device is changed. A child
that fails too quickly to be observed cannot pass. If recording legitimately
continues until on-demand loading completes, the checker routes the fixed
public English fixture and explicitly stops before awaiting a terminal result.

Arctic discards an attempt when its native diagnostic collector observes an
error. That branch must advertise CPU retry and leave the receiver empty.
The native library may instead complete locally after failing Vulkan
initialization; that branch must insert the actual fixed English transcription
without an unintended Enter. Its CPU execution is explicitly described as
inferred from the only ICD naming an absent library, never as a native GPU
device observation. The output is measured against the immutable fixture,
included in the private leakage scan, and cleared before the next activation.
Both outcomes are accepted and recorded distinctly; a GPU error is not assumed
to make the upstream process return nonzero.

Two new English/Hebrew CPU recordings must then insert text while the same broker
and bad-ICD environment remain. The failed-attempt branch retains the forced
Vulkan preference; the completed-continuation branch explicitly selects CPU.
Their two numeric/hash-only measurements, and the optional single continuation,
are
validated separately against the immutable fixtures and selected model/CPU
pins; the existing twelve canonical sample bound remains unchanged. Cleanup
stops the owned injected broker and removes the private manifest. This tests
an actual process-scoped loader configuration error, not a physical GPU driver
crash or acceleration. The unchanged forced-process-failure gate still requires
actual failed-engine cleanup followed by two explicitly activated CPU recordings
with the preference forced Vulkan. Both modern GPU gates remain required; legacy Small
continues to use its separate unsupported-Vulkan gate.

Before any playback/insertion, one recording-indicator marker per session phase
contains boot/installation/phase/user identity and `receiver_empty:true`. The
helper holds the real recording state until the host QMP screenshot observer
captures this empty scene and types its one-use random nonce into the owned
receiver. The helper verifies the nonce and clears the receiver before any
speech playback. A failed acknowledgement aborts the entire session, keeping a
late capture away from transcript insertion. The publisher separately binds
the nonce hash and reviews the screenshots. A status JSON and private screenshot
hash alone do not certify visibility.

For leakage, normalized rolling fragments of at least twelve characters from
the actual inserted hypotheses are searched privately in the new journal,
Quickshell notification history, any running mako fallback, current status and
captured status replies. Matching content is never printed. Shorter disclosures,
logs outside this interval, unrelated notification servers and untested crashes
remain limitations. The helper and children have core dumps disabled.

## Evidence and validator

The only public serial report marker is `ARCTIC-DICTATION-QUALIFICATION ` followed
by `arctic-dictation-image-v2` JSON. Required gates and their evidence kinds are
exact mappings in `contract.py`. Failed/unrun gates stay in the report and block
passing status; safe partial reports are retained for diagnosis. A collector
guard failure emits a fixed `ARCTIC-DICTATION-COLLECTOR-ERROR` code instead.

The host preserves only this validated report, transcript-free context/fixture
manifest, execution identities and explicitly empty indicator PNGs. Never upload
the audio/reference bundle, GTK receiver files, raw logs or private transcripts.

```python
# Preserve structurally valid failures before requiring a successful result.
contract.validate(report, expected_context, fixture_manifest=fixture_manifest)
contract.validate_report(report, expected_context, fixture_manifest=fixture_manifest)
contract.validate_execution(state, six_reports, fixture_manifest=fixture_manifest)
contract.validate_release_profiles({
    'small-v2': {'state': legacy_state, 'reports': legacy_six_reports},
    'turbo-q5-v3': {'state': modern_state, 'reports': modern_six_reports},
}, fixture_manifest=fixture_manifest)
```

The fixture manifest argument is its actual bytes or `Path`; its digest and each
sample's source WAV/reference/frame identity are checked. Unknown report fields,
text-bearing observations, incomplete languages, boolean timing values,
contradictory readiness, wrong evidence kinds, duplicate gates, reused boots and
changed recovery disks, missing hardware lanes and reused cross-profile
installations are rejected. Reports contain the five-field fixed profile
descriptor, CPU flag hash and hardware-selection result; each measured sample
also binds its actual CPU variant, executable hash and model hash. All validator results retain
`release_acceptance:false`; trusted collection, independent review and the full
release gates are still required.

Source controls only:

Final publication pins both distinct matrix artifacts,
`dictation-candidate-qualification-small-v2` and
`dictation-candidate-qualification-turbo-q5-v3`, from the same reviewed execution
commit, Actions run and fixture manifest. The publication manifest's `dictation`
and `dictation_media_review` maps use those two fixed profile keys. Each lane
keeps its strict six-report archive inventory and two recording indicator images;
its visual review binds the exact image, artifact and PNG hashes. The publisher
independently rebuilds source/hash contexts before calling the per-lane and
cross-profile validators. One successful lane, reused artifacts or mixed
checker/source identities cannot qualify the release.

```sh
python3 -m unittest discover -s tools/dictation-qualification -p 'test_*.py' -v
```
