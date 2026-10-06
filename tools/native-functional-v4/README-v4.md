# Audit-only native functional v4 proposal

This is a separately reviewed checker correction and instrumentation proposal for
one future fresh run of the **same unchanged ISO**. No VM, push, dispatch, product
edit, rebuild, Nix installation, security/network/renderer setting change, or user
PC modification occurred while preparing it. The existing failed run stays failed.
Parent owns registration and any actual rerun after final independent source review.

## Immutable inputs and actual failure

The execution base is `2ba880086263f64edd7ba382288fcb8b90cc61d9`; its original native
checker SHA256 is `2bf89d4771baad6c948c15d38379393c8c57488ff497a2c68e398f360b2d0489`.
Candidate source remains `fe4742c8b9414c45f0bcbb0a4191f116383c60d1`, qualification
base remains `ae55fbc9d48cec5ecc786cf61994ed986296d1bb`, and frozen common v2 driver
SHA256 remains `0193c13bb9e17ac24bbf10681581262a2d3f2ec7512cab10a4ce92ac897d0633`.
The new branch must descend from 2ba, with only the reviewed v4 subtree, workflow
routing and separately reviewed AST test correction changed. Old v2/v3 files and
runtime harnesses remain unchanged. `execution-tree/` is a staged overlay, not an
applied Git checkout or a registered execution commit.

Original image run/attempt: 37507582946/1; artifact 11434226349 `arctic-linux-iso`.
ISO name: `Arctic-Linux-1.2-candidate-37507582946-1-x86_64.iso`.
ISO bytes:1880244224; SHA256:
`84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718`.
All original authenticated artifact metadata, actual ISO bytes/hash, source and
metadata checks continue through the unchanged frozen v2 primitives.

Actual native run 37525639962/artifact 11442800449 had seven of eight live gates
passing and the combined GUI gate failing; installed phase was unrun. Official ZIP
SHA256: `39fe124bd25b6adad6b4b6ab206056e8f3e88bc057b908411412caa3037f4e11`.
PCManFM PID 3046/client 4 was newly proved and successfully focused; the single
Ctrl+L/path/Return wtype command returned0, then the unchanged30-second directory
basename/title wait timed out. No F4, editor save or GUI ZIP-open commands were
reached. The original text fixture was unchanged. The actual later screenshot
shows home folders while the location entry contains the fixture path; that
observation does not prove why Return/navigation failed.

The same actual `celluloid-playing.png` (SHA256
`e3ac65df481e435fb3c044ffd325e6b45e8efaa2ec2552495acd35fa6f6535ae`) shows a black
video interior despite advancing libmpv/PipeWire state. Independent review counted
74375 pixels in ROI(660,605,1255,730):62769 RGB0,11606 RGB1, maximum channel1.
This one image cannot identify the renderer/capture cause or establish every frame.
The old player-state pass does not clear rendered-content acceptance. The exact
original evidence and independent actual review remain separate frozen dependencies.

## Narrow interaction correction and retained gates

All eight original gate names remain mandatory. Archives, source/tree bytes,
process/ELF/PID-start proofs, launch isolation, portal/a11y reachability, cleanup,
security interval and the original moving media fixture function remain unchanged.
The existing30-second navigation/title gate, F4 current-directory execution gate,
actual editor GUI Unicode save/content hash, and PCManFM ZIP-opener gate remain.
No gate is skipped, relaxed, substituted with config, or inferred from command exit.

Upstream PCManFM connects its location GtkEntry `activate` signal to chdir and
updates the title on chdir; Ctrl+L focuses the entry. V4 separates these requests:
Ctrl+L, explicit Ctrl+A, literal owned fixture path, and Return. Each is a distinct
wtype turn with actual mapped-process identity, focus acknowledgement and observed
window focus before/after. Small bounded settling intervals and decisive captures
separate activation/text/Return. There is no blind retry or navigator replacement.
A capture labelled location-focused means after the requested shortcut and proved
window focus; it is not an assertion that the GtkEntry's internal focus property
was queried. If navigation still fails, the same strict functional gate fails.

Every repeated raw compositor client snapshot has a monotonic trace record,
including whether its data changed. Inputs, focus, bounded waits and decisive/failure
frames are recorded. The optional trace caps at2 MiB and explicitly records omitted
rows; the latest complete raw client snapshot and a summary remain preserved even
if that trace fills. Decisive diagnostics are mandatory: collection failure fails
the gate. An already-failed gate keeps its original failure and separately records
any failure-frame collector error before owned cleanup. No pre-existing app receives
keys or signals, and cleanup retains the exact pidfd/start/UID/ELF protections.

## Separate rendered-content strengthening

The original moving testsrc2 workload remains byte-identical:160 x120,10 fps,
20 frames/2s, FFV1 level3 plus48000 Hz mono PCM; CPU decode must still equal its source.
The eight original advancing AV samples, exact player/socket UID/PID checks,
libmpv mapping, GUI renderer, real audio backend and original moving screenshot
remain. A separate `moving-player-proof.json` preserves successful state evidence
before any later visual failure. Its moving screenshot still needs human review;
this proposal does not retrospectively accept the old black frame.

A **separate additional static diagnostic fixture** contains a known16 -color4 x4
pattern for20 frames/2s, encoded FFV1/yuv420p without audio. It opens in another
proved new Celluloid PID using the same existing default render options; only
`--no-existing-session`, `--new-window`, owned IPC socket and loop-file options are
used. No GPU/backend/VO/hardware/decoder/config setting is changed. The original
moving audio player remains running; recorded virtual audio retains its existing
qualification limits. No motion rendering or perceived audio is claimed from the
static fixture.

The exact owned static window is focused, and actual Mango monitor/client geometry
is captured around its grim screencopy. This bounded diagnostic supports actual
scale1 SDR outputs only; clipped, smaller, nonintegral, HDR or unobserved geometry
fails/open rather than using a guessed ROI. PNG header dimensions must equal the
actual selected monitor. Client geometry/focus and PID identity must remain stable
across capture. FFmpeg converts only that actual screenshot's bounded client crop
to RGB24. Exact expected decoded RGB, actual cropped RGB, source/fixture/capture
hashes, default options, scale, raw geometry and capture qualification are exported.
Grim can itself request repaint; this is actual post-input rendered evidence, not
a claim about the untouched desktop or physical display.

The pixel oracle searches within the proved client crop using a connected region
of the first unique reference color, then matches all16 cells. Expected reference
colors must be within6 levels/channel of the exact generated palette. Bounded ROI
candidates need at least80 x60 content and2000 checked interior pixels; maximum
per-channel tolerance30, bad fraction1%, and mean channel error15. Grid edges are
excluded to qualify scaling/encoding interpolation. The returned content ROI and
scale are an inferred matching region, not a queried GTK video-widget boundary.
Black, flat, wrong orientation, sparse colored controls, corrupted/clipped frames,
malformed dimensions/reference and missing evidence fail. Unknown or unmatched
pixels leave rendered-content open. The host re-evaluates the actual exported RGB
and requires it to equal the guest oracle result; IPC/hashes alone cannot pass.
`visual-oracle.json`, RGB files, static PNG and moving proof are mandatory on success.

This strengthening is inside the existing media gate, keeping exactly eight gate
names. A static visual failure makes that gate fail while the independent original
CPU-decode gate and the separate moving-state proof remain available for diagnosis.
It cannot establish moving frame rendering, portal chooser roundtrips, complete
app accessibility, browser sandbox coverage, extra/proprietary codecs, physical
hardware/gaming, recovery boot, Secure Boot or perceived audio.

## Adapter, transport, source and CI constraints

`prepare-adapter-v4.py` reproducibly replaces only `main` in the new v4 native
source. Every other function/class/source byte and AST remains equal between v4
library and adapter. Ancestor native manifest/review are explicitly named historical
inputs; they are not presented as review of new v4 code. New source provenance,
execution pins and independent review identify this proposal separately.

The existing owned Foot launcher barrier is byte-identical and proves its Foot and
shell have actually exited before checks. The existing QEMU audio fixture,
offline/encrypted install/first boot harness, owned containers, deadlines, preservation
and frozen v2 checks remain. The native pipeline uses one fresh same-ISO VM; live
failure still prevents installation. V4 never waives the original failure or forces
installation after failed native gates.

The unchanged guest/host transport remains checksummed zlib/Base64 with flat-or-owned
relative paths, no symlinks/traversal/reserved overwrites,128-file maximum,4 MiB/file
and16 MiB total. Only `.rgb` is added to the reviewed evidence suffix allowlist for
actual/expected binary pixel evidence. Existing bounds are unchanged. Complete
available failure evidence is extracted before host success assertions. No transport
record or screenshot is promoted to release acceptance; every report keeps
`release_acceptance=false`.

The proposed workflow routes the existing default-off native-only boolean to v4,
skips build/recovery jobs in that mode, and preserves the fixed original artifact.
Release, recovery, Nix, performance and boot-test flags must all be false. It uses a
separate clean full-SHA checkout with2ba ancestry, exact file pins and restricted
changed-file allowlist. The runner still requires KVM/Docker without TCG fallback,
host chmod, security weakening or arbitrary package installation in the guest.

The inherited CI correction is separate: only
`tools/tests/test_performance_harness.py` is copied byte-for-byte from
`fd7a5b56bab06d529fed0f1d3e232c774a40b9b6`, SHA256
`5a9b35e0dea7ba476f013376c8da301f32ac44788743e50cc3cf3804d43faca3`.
It places the unchanged actual collector loop inside FunctionDef for its test
control, preserving successful True and strict native failure behavior. It changes
no runtime harness and does not alter original CI/VM results. Its independent
review is separately pinned in provenance. No corrected-CI success is invented here.

## Reproduction and remaining work

Host-only controls:

```sh
python3 out/audit/consolidated-iso-37507582946/native-functional-v4/test_native_smoke.py
python3 out/audit/consolidated-iso-37507582946/native-functional-v4/test_native_v4.py
python3 out/audit/consolidated-iso-37507582946/native-functional-v4/test_native_runner_v4.py
```

Current owner results:16 core/codec controls attempted,14 pass and2 explicit host
helper skips (7zip/cpio remain mandatory in the guest);13 new behavior/source/
visual controls pass;33 adapter/transport/lifecycle controls pass. Tests execute
real host FFmpeg/helper roundtrips and bounded subprocess/PIDfd/WAV controls where
available, with explicit GUI/IPC/clock fixtures. They run no guest, VM, Docker,
network request, app, service, or Git branch mutation. Harness patches are applied
only to private temporary file fixtures. These results do not qualify actual GUI
behavior. Supporting command/output/source hashes are pinned in the audit manifest.

The first owner freeze (`13fcb385...`) is retained byte-identically in sibling
`native-functional-v4-prior-owner-13fcb385/` with historical manifest SHA256
`10d4f1434c2e9d3d24b747b20e65413e0074edd7cb20bf387cfbdebd59f79f4e`.
Independent real FFmpeg host controls reproduced three false passes there:
unfocused before / focused after capture, boolean scale `true`, and boolean
monitor coordinate `true`. These GUI/window/IPC authorities are synthetic host
fixtures, not actual VM findings. The corrected checker requires focus/visibility
and owned client identity at both observed capture boundaries, numeric finite
scale 1 excluding booleans, strict integer monitor coordinates and positive
bounded dimensions, and equal client/monitor geometry across the capture.
Both raw client and monitor observations are retained. This proves those two
observed boundaries, not continuous focus between snapshots. Owner adverse
controls exercise the actual visual method with real FFmpeg fixture/PNG/crop;
before/after focus loss, invalid scale/coordinate, changed monitor, and changed
identity fail, while the known reference still passes and black pixels still fail.
`interim-stale-provenance-controls.log` preserves one owner regeneration-stage
failure: source changed while the old provenance hash was still present. The
strict guard correctly failed; the final rerun uses refreshed provenance.

The corrected capture-guard owner freeze (`04a22431...`) and its independent
PASS report (`455566e9...`) are retained in sibling
`native-functional-v4-prior-deployment-04a22431/`, historical manifest SHA256
`c88e3e433237b2578d5777d7881cb2a4ca8697ce39c259fa83f046ddbd80eb3d`.
Root's actual uncommitted mapped execution checkout ran 29 of 30 runner controls
successfully; the workflow check failed because its audit-only workflow copy was
not deployed (correctly, the manifest deploys `.github/workflows/iso.yml` once).
The preserved `root-runner-controls.log` records the exact FileNotFoundError;
root's inherited AST check was not reached after that failure. This differs from
the prior owner's six completed inherited AST controls.

The test helper now uses `registered-iso-native-v4.yml` when that audit copy exists,
otherwise the actual repository `.github/workflows/iso.yml` two parent levels
above the deployed checker directory. Missing both raises FileNotFoundError.
An adverse selected workflow fails the original unchanged YAML assertions;
it cannot fall back to a more permissive copy. Three new controls exercise
mapped-only success, audit precedence, missing-both/audit-only behavior, and
adverse selected workflows. A separate complete 33-control replay uses the actual
21-file mapped layout plus its manifest and unchanged v2 library, with no duplicate
workflow in the checker directory. No runtime, guest, adapter, launcher or
workflow source changed in this layout correction.

Remaining: independent final source review, parent registration of exact separate
execution head plus actual source CI, and one fresh same-ISO native live/offline
LUKS install/first-boot qualification. Both stages must pass all8 gates with real
navigation/save/opener/visual evidence, Enforcing/AVC and owned cleanup checks.
Original Safe welcome, native GUI and rendered-content release gates remain open
until actual qualified evidence supports them. Rollback is to stop using the new
checker branch; the candidate ISO and all existing PCs remain unchanged.
