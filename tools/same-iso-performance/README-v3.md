# Fixed-image performance recovery preparation

This is an audit-only proposal. No tracked files, existing runs, ISO, main branch,
release or guest have been changed by this bundle. Promotion/dispatch requires
parent review and independent source/control review. It is based on qualification
commit `ae55fbc9d48cec5ecc786cf61994ed986296d1bb`, not the native branch.

Candidate image source remains `fe4742c8b9414c45f0bcbb0a4191f116383c60d1`.
Candidate artifact 11434226349 belongs to run 37507582946 attempt 1; actual ISO is
1880244224 bytes, SHA256
`84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718`.
The released baseline remains 2322073600 bytes, SHA256
`054db5c43cae47fb60f8f43efc8e052b569aa1b14e8f15adcb15cdc48265182f`.
The candidate source and future execution-checker commit are recorded separately.

## Preserved actual failures

Official paired-performance artifact 11442027656 was verified and preserved in
`../qualification-monitor/paired-performance-11442027656/`. Baseline boot 1
completed; candidate boot 1 stopped before application timing/idle sampling with
`Configured program is not owned by the declared role RPM: gnome-web`. The
remaining four planned boots did not run; no full comparison completed.
Seven of the twelve baseline mapped-window brackets failed the unchanged precision
limit. Fixing only ownership would therefore not establish a valid comparison.
Historical Kitty subsequent-mapping medians 0.140385157 to 0.169684455 seconds
(20.870652%) remain a failed 10% regression gate; overlapping ranges never excuse it.

## Narrow proposed changes

`guest.py` accepts exactly the GNOME Web Fedora frontend/runtime family:
`epiphany` and `epiphany-runtime` must have identical epoch, version, release and
architecture; `rpm -qf` must name that exact runtime. `/usr/bin/epiphany` must be
the canonical non-symlink regular file, with the independently verified signed
RPM header's expected native ELF digest and no link target. Prelaunch checks are
metadata only: no magic, full digest or other executable content is read. Actual
ELF magic and whole-file SHA256 must match that header immediately after the
first GUI-role measurement, with unchanged device/inode/size/mtime/ctime through
path and opened descriptor before and after hashing. The mandatory proof binds
the same actual boot, image/boot-number/desktop UID and browser launch/map endpoint;
its raw interval follows that first measurement and precedes every preconditioning
launch. Missing, changed-file, wrong-digest, stale, early or late proof blocks DONE
and comparison acceptance. Other role ownership guards
are unchanged. `epiphany-ownership-evidence.json` records independently checked
cached signed Fedora RPM headers/payloads and the saved matching guest inventories.
There is no claim a new guest ownership query was performed after the aborted run.

The observer records integer absolute monotonic timestamps inside the actual
desktop-user socket worker: request start, immediately before send, and immediately
after response EOF. Each is checked inside the enclosing root-parent request
envelope. The last negative send remains a conservative lower bound even when an
old negative response arrives after mapping. First positive socket EOF becomes the
upper bound. Cached UID lookup, parent JSON normalization and later window filtering
cannot enlarge that upper timestamp. Raw positive/negative proofs and all query
envelopes are exported, with UID bound to the declared desktop user.

The query worker's final return code is mandatory: natural EOF exit 3 or forced
termination after valid measurements is fatal before completion. If a query/body
exception already exists, it stays the primary failure instead of being replaced
with cleanup noise. Actual Python-child controls cover normal completion, EOF3,
forced cleanup/reaping, and original query/body error preservation.

An inherited synthetic fixture initially stored a child timestamp before its marker
file became visible; a correctly negative socket snapshot could follow that timestamp.
Its 1.18 microsecond failure and the initial cleanup-negative fixture are preserved
in `historical-pre-worker-cleanup/`. The corrected oracle defines/timestamps the
synthetic logical client-map state inside the server before sending its first
positive response. It never uses response receipt as truth. The independent delayed
negative/map-before-old-response-receipt control remains unchanged. This test-oracle
repair does not reinterpret any actual VM bracket or alter observer gates.

Original evidence contains durations only; its critical negative/positive query
cannot be reconstructed. Root-pipe overhead maxima include seed and persistence
queries, so they do not prove a particular failed bracket's cause. No per-map
`/proc` PID identity scan existed on that critical path. Worker/compositor response
latency and inter-query scheduling remain inside the new brackets. This proposal
does not promise every KVM bracket will meet precision or claim application gains.
The preceding reviewed full-prelaunch-hash bundle is preserved byte for byte in
`historical-before-cache-bias-fix/` with ready e4241f97 and manifest 92b64b5c. It
was not executed: candidate-only prefetch could bias first-role observations.
The superseding metadata-only prelaunch policy explicitly records zero bytes read,
and the comparator rejects old prehashed or magic-read declarations.
The protocol name advances to `mango-socket-worker-v2-worker-clock`; both images use
one identical newly frozen observer. Old results are never relabeled or overwritten.

The controller takes an explicit clean `--candidate-source-root` for image commit,
catalog and Battery hashes; revised execution tools no longer pretend their commit
is the image source. Default controller use still selects its own checkout. The
fixed-image wrapper supplies only the immutable `fe4742c` checkout and pins unchanged
original install/VM helpers; source core preferences are not edited.

## Gates and meaningful controls

The plan remains AB, BA, AB: exactly three unique fresh overlays per image from
clean powered-off installed snapshots. Pristine idle precedes every GUI role and
workload helper; first-use role launches precede all 45-second preconditioning.
Thirty raw CPU intervals and six paired PSS/private snapshots remain required in
each idle phase. The helper's CPU ticks remain separately reported for normalized
idle. Role identities/defaults, offline fixtures, actual user/session, source,
ISO/profile and pristine-overlay proofs, KeepAwake restoration and cleanup remain
mandatory.

Memory thresholds remain 5%; app/shell latency thresholds remain 10%. Every map
bracket must be at most min(5 ms, 2.5% of its observed upper time). Monotone median
enclosures must prove candidate upper <= 1.10 * baseline lower; a straddle is an
uncertainty failure, and a point regression remains a regression. No gate is relaxed.

Controls cover foreign RPM owners, epoch/version/architecture mismatch, duplicate
or missing runtime, unexpected paths/symlinks/non-ELF/forged header digest; malformed
or forged socket clocks/UIDs/order/relative bounds; a real socket response with
delayed parent normalization; and a delayed negative snapshot whose true transition
must remain inside a deliberately wide, failing bracket. Prior threshold, raw CPU,
memory, role/cold ordering, worker reaping and historical failure controls remain.
Synthetic control ranges around the exact reported Kitty medians are declared as
synthetic, never substituted for historical boot evidence.

## Review and future promotion

Replay `python3 -W error::ResourceWarning -m unittest discover -s tools/tests
-p 'test_performance*.py' -v` in this audit tree and
`python3 -W error::ResourceWarning test_performance_runner_v3.py -v`.
Review diffs against `fe4742c` for guest/comparator/controller/tests and against
`ae55fbc` for `iso-performance-v3.yml`; verify all frozen v2 pins remain unchanged.
After independent PASS, use a separate future qualification checkout based on ae55.
Copy the files listed in `execution-pins-v3.json`, mapping the workflow copy to
`.github/workflows/iso.yml`, this bundle's top-level files to
`tools/same-iso-performance/`, and its tools/ files to the same repository paths.
Copy the manifest itself to `tools/same-iso-performance/execution-pins-v3.json`.
Verify all exact hashes and clean execution/source identities before committing.
Do not amend the active native branch or register a new workflow on main.

The existing registered ISO workflow receives boolean `same_iso_performance`,
default false. Only that mode runs the new job. The ISO build is skipped and both
old recovery jobs are skipped; release or combined recovery/performance requests
fail preflight. New jobs use only contents/actions read and ordinary fixed-ID
`actions/download-artifact`; the candidate ISO is hashed before any VM. The original
released baseline is downloaded only inside supported CI for the actual VM tests,
reassembled by exact part names and independently byte/hash verified. ISO/qcow/socket
files are excluded from output artifacts; original results remain untouched.

The registered performance job fetches full execution history so the unchanged
`merge-base --is-ancestor ae55fbc...` guard can prove its actual ancestry. Its sparse
execution checkout includes `profiles/ci`: the unmodified harness resolves the
default offline profile even in host controls that use a fake container engine.
The earlier reviewed ready `da7316b7` and manifest `45c64601`, plus the independent
cache-bias PASS report, are preserved byte for byte in
`historical-before-workflow-checkout-fix/`. They were promoted as execution commit
`c19a83a4246adb6f005e85d58efeb123019953d4`, but no ISO qualification was dispatched
before the parent caught those two workflow setup gaps. The subsequent commit must
retain that published history; this revision does not amend it.

Before the unchanged 40,000,000,000-byte free-space preflight, a fresh GitHub-hosted
Linux runner removes seven fixed unused SDK paths already named in the normal ISO
job. It records actual byte-space values before and after cleanup as an output
artifact. It deletes no dynamic tool cache, workspace, image or container; there
is no Docker pruning or guest/service/security change. Cleanup makes no promise
that the space gate will pass. Host controls execute the exact preparation shell
using fake `sudo`/`df`, verify its fixed argv, and reject non-hosted/non-Linux or
non-Actions environments before deletion. Additional controls reproduce missing
profile rejection in the actual harness and the actual shallow-history ancestry
failure, then demonstrate the corrected inputs pass.

The controller has a 180-minute total cap inside a 230-minute job. Each install,
boot and provisioning command retains its bounded timeout and unique container.
SIGTERM gets up to 100 seconds for controller cleanup before forced child reaping.
Emergency container cleanup requires current task UUID, frozen observer and image
pair proof, then validates every exact returned Docker name before any removal.
It never prunes images or kills arbitrary QEMU/application processes. An outer
runner termination can still interrupt finalization; incomplete evidence remains
failed/unrun, never an acceptance pass.

Rollback is to discard the unmerged qualification checkout, or run its default
mode with the new input false. The immutable image/source/release and all previously
collected artifacts are unchanged. Runtime KVM precision and six-boot acceptance
remain unqualified until a separately authorized actual run completes.
