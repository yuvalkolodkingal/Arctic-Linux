# Bounded same-ISO Safe visual diagnosis

This bundle is an audit-only proposal for one future fresh UEFI Safe VM. No VM, push,
dispatch, branch mutation, tracked source edit, ISO rebuild or product change was
performed to prepare it. Source and host controls are separate from actual guest
qualification. Every successful output keeps `release_acceptance=false` and
`safe_visual_gate=open`; visual review remains required. The original candidate and
recovery failures remain recorded and unchanged. A successful collection is not a
Safe graphics acceptance pass.

## Immutable provenance and separate execution

| Item | Exact identity |
| --- | --- |
| Repository | `yuvalkolodkingal/Arctic-Linux` |
| Candidate source | `fe4742c8b9414c45f0bcbb0a4191f116383c60d1` |
| Qualification base | `ae55fbc9d48cec5ecc786cf61994ed986296d1bb` |
| Original run / attempt | `37507582946` / `1` |
| Artifact ID / name | `11434226349` / `arctic-linux-iso` |
| Artifact ZIP bytes | `1880429588` |
| Artifact ZIP digest | `sha256:ea25d1ba5fc9b35b6141390825cf333b30b8bb3154b7bd3237a8d676d084740c` |
| ISO name | `Arctic-Linux-1.2-candidate-37507582946-1-x86_64.iso` |
| ISO bytes | `1880244224` |
| ISO SHA256 | `84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718` |
| Frozen v2 driver SHA256 | `0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633` |

A future registration must use a **separate execution commit based on ae55**, with
changes confined to `.github/workflows/iso.yml`, `tools/test-iso.sh`, and the new
`tools/safe-visual-diagnostic/` bundle. It must not modify an existing execution
branch, original/recovery/native/performance run, product source, or release tag.
`execution-tree/` is a staged file mapping, not a Git checkout and not an applied
patch. Its 11 pinned source files plus the self-excluded manifest are the exact
files to overlay in that separate checkout. Unchanged library files are included
as review references; their bytes equal ae55 and must remain unchanged.

The workflow checks out the candidate at fe4742c, the frozen v2 source at ae55, and
its own distinct execution head into three directories. The runner imports the
frozen driver only after checking its exact file hash. It calls the actual unchanged
`R.validate_original`, `R.verify_sources`, `R.verify_iso`, `R.require_docker`,
`R.execute` and `R.preserve_phase` primitives. It does not monkeypatch them or reuse
results as acceptance. The full candidate/artifact metadata pins, actual ISO bytes
and digest, original Nix step failure, and old source/review fingerprints are
verified by those primitives. An Actions ZIP digest is metadata evidence;
`R.verify_iso` separately hashes the actual downloaded ISO and all metadata files.

The separate execution checkout has `fetch-depth: 0` so local ae55 ancestry can be
verified. The runner also requires a clean checkout, exact execution manifest and
bounded changed file set. A manifest identifies source bytes; a future actual
`GITHUB_SHA` identifies the execution commit. No execution commit is invented here.

## Default-off workflow and exact future inputs

`safe_visual_diagnostic` defaults to false. When true it skips `iso`,
`same-iso-installs` and `same-iso-boot-evidence`, and selects one diagnostic job with
no matrix. All new action references are pinned. The diagnostic job has only
`contents:read` and `actions:read`, no release operation, a 55-minute workflow
limit, and a 35-minute owned subprocess limit.

Future reviewed dispatch inputs must be exactly: `safe_visual_diagnostic=true`,
`same_iso_recovery=false`, `release=false`, `nix_acceptance=false`,
`performance_acceptance=false`, and **`boot_test=false`**. The existing normal
workflow keeps its `boot_test=true` default; the Safe mode guard requires it to be
explicitly false. Mixed modes fail before artifact download or VM execution. The
original run ID and recovery run `37520174911` cannot be reused. Preparation does
not dispatch anything; root owns future registration/execution decisions.

## VM, inputs and device qualification

The harness hook is default off and its old collector block remains byte-identical
to ae55. Diagnostic mode requires actual KVM with no TCG fallback or host chmod,
UEFI without Secure Boot, Safe mode, 4096 MiB RAM, two vCPUs, virtio display, fixed
600/60 harness settings, and exactly the existing serial journal debug arguments.
The guest must actually have `rd.live.image` and `nomodeset` in its kernel command
line. The main ISO, blank installer disk, OVMF selection, display and restricted
network device choices retain the v2 harness settings.

The diagnosis **adds one read-only data CD** containing only its collector and
bootstrap. xorriso builds this small diagnostic transport inside the owned host
container; it does not rebuild or alter the candidate ISO. `sudo sh /dev/sr1`
mounts the second CD read-only at a fresh `/run/arctic-safe` after all separated
inputs and runs the exact pinned collector. This added device is a diagnostic
qualification, so this run is not claimed to have every device identical to old
v2. No arbitrary guest packages/downloads/network access are used. Only disposable
collector evidence and its read-only mount point are created.

`safe-toolchain.txt` records actual new QEMU/RPM versions and QEMU, OVMF, data-CD,
collector and driver hashes. Old v2 evidence did not preserve equivalent toolchain
hashes. Identical old/new compiled tool bytes are therefore not claimed.

## Captures and timing

1. Detect and select Safe; record actual GRUB boot-command send time. Record actual
   QEMU `/proc` start ticks, HZ, monotonic calibration and precision bounds.
2. Capture without further input through 600 seconds: each 10 seconds through 120,
   then each 60 seconds through 600. After the 600-second capture, keep an additional
   **at least 120 seconds without input**, with intermediate/final captures.
3. Capture, move only the absolute pointer to x/y 3000 with no key/click, then
   capture at target 1 and 5 seconds. Reject pointer failure; no fallback input.
4. Send Super+Enter alone; capture at target 1, 5 and 60 seconds.
5. Send Return alone; capture at target 1 and 5 seconds.
6. Type the read-only collector command; collect actual post-interaction telemetry.
   The guest signals GRIM-READY then waits 20 seconds. Preserve QMP pre-frame,
   actual user-session grim PNG, QMP post-frame and final frame separately.

There are 34 required diagnostic captures, in addition to the original menu
screens. File names are target offsets, not exact latency measurements. Event
records contain actual monotonic capture/input-call completion times, actual QEMU
and entry elapsed times, and the explicit input origin. The frozen keyboard helper
sleeps 0.3 seconds after sending; captures use the pre-send origin and record that
call's completion/lag. QEMU start is a host process estimate quantized to its HZ;
these clocks do not establish guest startup/performance or a frame presentation
time. A capture may itself request repaint. Guest grim is explicitly
post-interaction, and its coordinated QMP pairing qualifies observation order;
it does not establish how the untouched welcome was originally rendered.

## Actual read-only telemetry and security

The root collector first enforces its exact read-only CD path, QEMU/KVM guest,
actual Safe live kernel command line and **SELinux Enforcing** before writing any
/tmp evidence. It finds the actual `liveuser` Mango and shipped Arctic Quickshell
processes and records UID, PID, start tick, argv, executable path/hash and loaded
maps. It verifies identities around collection and screencopy; it never signals
or alters those processes. Wayland/Mango sockets must belong to the actual desktop
UID. Mango queries and grim run as that user with an explicit environment whitelist.
All unlisted environment fields are dropped. Exact `ARCTIC_REDUCE_MOTION` and
`ARCTIC_SHELL`, Qt/QSG/WLR/LIBGL settings and necessary session identity fields are
retained. The collector does not query or mutate live QML properties.

Actual settings, shell/effects/motion files, current theme/colors and ordered Mango
includes are read with path/status/hash/text, including unavailable optional files.
The observed config graph is checked again after collection. Current settings
inputs remain separate from live QML state. `effective_render_loop` and
`live_welcome_opacity` are explicitly **unobserved**, even if env/maps suggest a
renderer. No opacity, repaint cause, software-backend pass, or preference change is
inferred from those inputs.

Actual stdout/stderr targets are recorded; regular user-owned log tails are read.
Actual runtime/cache/state Quickshell locations are searched with ownership,
no-follow and size/count bounds. Their log bytes are preserved without pretending
to decode binary logs. The actual current-boot user journal retains its last 250
records. System journal snapshots before/after grim scan the whole current boot up
to a strict 32 MiB collector bound; each preserved raw system log is at most 4 MiB
with complete trailing JSON records, exact total/retained byte counts and digest.
Exceeding the whole scan bound fails rather than declaring security success.
`auditctl -s` must report enabled 1/2 and lost 0. Whole-current-boot AVC checks
require trusted `_TRANSPORT=kernel/audit`; a sudo command that merely contains AVC
search text is not a denial. Both security snapshots must remain Enforcing with no
actual AVC rows. Genuine unrelated boot denials still require review and fail the
collector gate; the runner does not change policy or filter them by app name.

All telemetry occurs after terminal input. It can explain observed state but does
not prove the exact pre-input render state or explain the cause of the old failure.

## Preservation, bounded failures and source controls

A fresh output directory is required. One unique `arctic-paired-safe-*` Docker
container is owned by the unchanged frozen `R.execute` cleanup, including TERM/KILL
and finally cleanup. No unrelated container/VM is touched. The runner always calls
unchanged `R.preserve_phase`, including on failure. Top-level `.log`, `.png` and
`.txt` files hold raw QMP/serial/event/tool evidence so that primitive preserves
them. Separately reviewed extraction transports flat guest `.json/.png/.txt/.log`
files through checksummed zlib/Base64 chunks with strict record order, unique
markers, reserved host names, no traversal/overwrite, per-file 4 MiB and aggregate
16 MiB bounds. The raw serial log retains failure records even if extraction fails.
Failed output never changes the old result or closes the Safe visual gate.

Reproduction from this audit directory:

```sh
python3 out/audit/consolidated-iso-37507582946/safe-visual-runner/prepare-safe-v1.py --out /tmp/unused-safe-reproduction
python3 out/audit/consolidated-iso-37507582946/safe-visual-runner/test_safe_v1.py
```

The first command writes only that explicit output directory. It checks the exact
base snapshots and reproduces both source patches. In a future registered checkout
it reads those same ae55 files through read-only `git show`; no fixture snapshots
need to be registered. Host controls require Python 3 and PyYAML, execute fake
clock/VM APIs and transport/source/security fixtures, and never run a VM, Docker
container, guest collector or Git mutation. Registered tests also depend on the
unchanged sibling `tools/same-iso-recovery/vm-only-recovery-v2.py` from ae55.

Owner host controls pass 18 tests, covering input timing, extra quiet duration with
screenshot latency, missing/failed evidence, source scope/frozen primitive reuse,
mode conflicts, transport ordering/checksums/bounds/traversal/reserved output,
security failures, actual motion whitelist and unchanged default collector bytes.
They are test fixtures, not actual GUI, hardware, rendering or security acceptance.
`host-controls.log`, `syntax-controls.log`, `execution-pins-safe-v1.json`,
`audit-manifest-v1.json` and `review-ready-v1.json` pin the supporting evidence.
Independent review is reported separately; review does not execute the VM.

## Remaining gates and follow-up

After independent source review, root must register the exact separate execution
head and run one fresh same-ISO Safe diagnosis. Review untouched 600-second and
quiet frames, separated input frames, qualified grim/QMP pair, actual renderer/log
state and security evidence. Collector success alone cannot close the current Safe
welcome visual blocker. If the failure reproduces, propose a narrowly evidenced
fix and rollback and test it in a separately approved candidate; no animation,
wallpaper, clock or feature preference is disabled here. This bundle neither
changes nor qualifies recovery boot, Secure Boot, native-app functionality,
performance, hardware or existing PC behavior.
