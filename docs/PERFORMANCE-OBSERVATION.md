# Mapped-window observation

The paired performance run keeps each image's production Mango session and
settings, with a frozen collector/toolchain shared by all three pristine boots
of each image. The optimized image includes the reviewed Mango 0.17.3 output
teardown recovery patch; no compositor substitution is made for measurement.
Different configured apps are compared by declared desktop role. No host cache flush,
service change, alternate compositor, or application preference is introduced.

The v2 autonomous observer enters the actual desktop user's environment once,
checks that native socket and production CLI client identities agree, and then
polls Mango's read-only `get all-clients` protocol without parent handoffs between
polls. Each one-shot query has a fresh socket. The parent arms observation before
its original application `Popen`; launch overhead remains included. Both worker
and parent use the same guest monotonic clock. The last negative query's **start**
is the conservative lower bound; the first positive query's completion is the
upper bound. A delayed parent read does not change either endpoint. Mapping is
still followed by the original persistence hold and actual client check. Cleanup
only closes observed newly launched matching clients and reaps owned processes.

Role polling sleeps 50 microseconds between socket queries. The worker's CPU,
allocations, scheduling, socket processing and compositor response time are
measurement costs, not free instrumentation. Whole-guest counters include
collector helpers; parent-only CPU counters do not. Up to 32,768 query traces,
4 MiB of raw Mango data, and 4 MiB for the complete encoded worker reply are
allowed. Mapping replies include matched identities rather than duplicated
client metadata; the persistence query retrieves actual metadata afterward.
The total envelope is checked before any pipe write; count and query ceilings
do not guarantee that the combined envelope fits. Exceeding a bound, a UID mismatch, malformed
response, duplicate client identity, timeout or disconnect fails observation.
Cancellation closes stdin and the parent's stdout read end so the wrapper can
reap its worker even while a bounded large reply is being written.

The qualification limits remain unchanged: every mapping bracket must be at
most `min(5ms, 2.5% of its observed launch time)`, and the candidate median upper
bound must be at most `1.10 * baseline median lower bound`. All six boots must
use the same current observer and source hash. Neither discarding imprecise
samples nor widening a threshold is allowed. Historical results are not
reclassified by a new observer version.

The comparison JSON retains every bracket, precision result and regression
result. Diagnostic per-query traces remain in raw guest logs; each comparison
trace is represented by its count, canonical JSON SHA-256 and socket-duration
summary. This keeps the report within the release preparer's existing 4 MiB
limit. Summarization occurs after gate computation and never modifies input logs.

Local Unix-socket fixtures check fragmented and malformed transport, actual UID,
independent mapping brackets, postponed parent reads, timeouts, cancellation and
owned-process cleanup. The disposable native frame VM additionally records four
Foot launches against the same unchanged precision limit before its full frame
matrix. It retains all raw observations and marks each invalid bracket and the
overall precision result as failed. That diagnostic is separate from the original
frame geometry/pixel gate: this fixture forces software GLES with two headless
outputs and does not reproduce the ISO's graphics/session environment.

The first two actual v2 fixture runs mapped Foot, but their final queries took
212 and 375 ms, giving failed 213 and 377 ms mapping brackets. Removing parent
handoffs did not resolve this fixture's precision limitation. Mango 0.17.3 handles
client scene creation, insertion and resize synchronously before returning to
queued IPC; its watch notifications do not provide an authoritative timestamp.
The failed experiments are retained rather than converted into passes. Observer
transport controls and frame success cannot qualify precision or speed/RAM gains.
The rebuilt ISO's full six-boot paired gate remains mandatory with every original
precision, enclosure and regression threshold unchanged.

## Historical v10 causal lower-bound extension

The replacement ISO run 37903438836 also failed precision: 20 of 36 baseline
brackets and 15 of 36 candidate brackets exceeded their original limits, although
all point regressions were within their limits and the enclosure check passed.
Candidate Foot cold brackets were 12.4–12.9 ms against 1.61–1.77 ms limits.
The original evidence is retained. A new observer cannot reclassify this image.

The v10 paired observer added a read-only kernel return probe to the actual loaded
wlroots library. It retains the same socket observer and unchanged upper bound.
The kernel event tightens only the lower endpoint when its unique foreign-toplevel
identifier matches a newly observed IPC client. It is a bound before mapping,
not an exact mapping, scene visibility, presentation or first-frame timestamp.

The causal ordering is specific to the audited Mango 0.17.3 and wlroots 0.20.2:

1. [Mango's `handle_client_map`](https://github.com/mangowm/mango/blob/0.17.3/src/manage/client.c)
   assigns the return of `wlr_ext_foreign_toplevel_handle_v1_create` to
   `c->ext_foreign_toplevel` before any branch inserts `c->link` into
   `server.clients`. Scene allocation and foreign-protocol announcements are
   separate; neither is used as proof that the client is already visible.
2. The [wlroots 0.20.2 creation function](https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/0.20.2/types/wlr_ext_foreign_toplevel_list_v1.c)
   allocates the identifier before returning a successful handle. The kernel
   return-probe timestamp precedes the caller's assignment and later insertion.
3. [Mango `get all-clients`](https://github.com/mangowm/mango/blob/0.17.3/src/ipc/ipc.c)
   enumerates only `server.clients`; `build_client_json` reports that handle's
   identifier as `foreign_toplevel_id`. Therefore a matching return event must
   precede the first possible positive result under the existing IPC predicate.
   The final socket completion remains the conservative upper bound.

The exact audited x86_64 [header](https://gitlab.freedesktop.org/wlroots/wlroots/-/blob/0.20.2/include/wlr/types/wlr_ext_foreign_toplevel_list_v1.h)
has `identifier` at byte 56. Header SHA-256 is
`9253b1ac1b68011cb304c0c9b84a6678779acc820994131a31f170d26945d0f3`;
creation-source SHA-256 is
`5580d4b6c803fb3548bbe104f5b0bdbfd5a17b42dd173358aa526ca0e958a088`.
The interface is unstable: a different wlroots version is rejected until audited.
The observer resolves the exported function from the actual ELF's dynamic symbol
table and records both production executable/library hashes and RPM identities.
Package verification must pass. It uses the actual desktop-owned Mango PID and
start ticks, a unique 128 KiB tracefs instance, PID filtering and the kernel's
`mono_raw` clock. It leaves scheduling, compositor source/binary files, preferences and SELinux
enforcement intact. Uprobes temporarily trap the observed function's return in
the kernel; that instrumentation and reader costs are included in the
measurement; a frozen combined source hash is shared by all six boots.

The tracefs command interface uses a write-only, close-on-exec descriptor with
one complete command of at most 4096 bytes per write and an exact byte-count
check. It never seeks, appends, creates or truncates the command file. Python
[FileIO append mode](https://github.com/python/cpython/blob/v3.14.0/Modules/_io/fileio.c)
explicitly seeks to `SEEK_END`, which Linux
[seq_lseek](https://github.com/torvalds/linux/blob/master/fs/seq_file.c) rejects.
Opening `uprobe_events` with `O_TRUNC` would instead remove unrelated global
events. Both registration and removal use the bounded command writer; failed
writes close the owned descriptor and cleanup still attempts every owned resource.

Unknown identifiers, wrong-process events, wrong clocks, stale/future receipts,
unsupported ELF layouts, absent tracing, lost events, bounded-reader overflow and
cleanup failure fail qualification. Kernel text timestamp precision is disclosed.
Linux [trace output](https://github.com/torvalds/linux/blob/master/kernel/trace/trace_output.c)
uses [ns2usecs](https://github.com/torvalds/linux/blob/master/kernel/trace/trace.c),
which adds 500 ns before division: six-digit timestamps are rounded to the nearest
microsecond, not floored. The receipt retains the literal displayed time and
subtracts one full displayed unit (1 microsecond for six digits) to preserve a
conservative lower bound. The decimal token is retained; comparison independently
derives its integer value and displayed resolution and requires exactly that allowance/arithmetic
and rejects resolution above 1 microsecond. The root collector removes only its own event and
instance, and unmounts tracefs only if it mounted it. No persistent configuration
or SELinux relaxation is installed. Cancellation is deferred across resource
ownership handoffs and bounded cleanup; the sole reader thread inherits blocked
termination signals so repeat cancellation cannot bypass that unwind. Historical
v8 role evidence remains rejected.

The paired IPC worker and launch collector use Python
`clock_gettime_ns(CLOCK_MONOTONIC_RAW)` without a decimal text conversion;
kernel receipts use ftrace `mono_raw` (`ktime_get_raw_fast_ns()`). They share
Linux's raw timekeeper base, with no offset conversion or assumed boot timestamp.
Only their within-launch differences form app latency. Operational timeouts keep
normal monotonic time, and systemd boot-startup metrics retain their original
separate source. Linux ftrace's adjusted `mono` clock and `bpf_ktime_get_ns()`
both use `ktime_get_mono_fast_ns()`. The official
[timekeeping documentation](https://github.com/torvalds/linux/blob/master/Documentation/core-api/timekeeping.rst)
allows adjusted fast-clock jumps during timekeeper updates or suspend. The
[raw-clock implementation](https://github.com/torvalds/linux/blob/master/kernel/time/timekeeping.c)
avoids the NTP/PTP slope change and explicitly describes raw fast access as
correct. Mixed raw/adjusted evidence and prior v9 samples are rejected.
Calibration records the actual guest kernel config, clocksource and lockdown
state. This measures guest raw-clock latency, not universal host clock accuracy,
and cannot qualify this source without actual runtime evidence. The display
allowance covers rounding and does not invent a cross-clock accuracy margin.

Source controls are not runtime calibration. Before another final-image build,
an explicitly unqualified research lane should try this instrument on the retained
failed image and preserve actual library/probe/loss/timing evidence. That lane must
not pass the native image fetch guard, mark a failed producer qualified, publish,
or supply final six-boot acceptance. The final image still requires six fresh paired
KVM boots and every unchanged precision, enclosure and regression check.

The first actual [retained-image calibration](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37951719419)
installed and booted kernel `7.2.9-200.fc44.x86_64` with SELinux enforcing,
all five required tracing features enabled, lockdown `none` and `kvm-clock`.
It failed before any launch measurement because Python append-mode opening of
`uprobe_events` returned `EINVAL`. Its original failed report is retained.
The nonseeking writer correction has source controls, but needs a new reviewed
calibration activation and actual runtime result; it is not timing evidence.


## Historical native managed-list bracket (v12, failed calibration)

Retained-image research run 37971533836 restored the actual active Wayland VT
and output, initialized both raw clocks and matched all four lower receipts
without kernel event loss. It still failed all four precision checks: widths
were 11.416, 5.390, 2.024 and 2.063 ms against limits 1.552, 1.334, 1.292 and
1.136 ms. The positive socket roundtrips were 10.967, 5.044, 1.384 and 2.496 ms.
Those failures remain failures; a changed observer cannot reclassify that run.

The v12 observer retains the original app launch, exact application-ID match,
positive socket query, five-second persistence check, measurement order and
fresh installed boot requirements. It adds a temporary instruction uprobe to
an independently audited production Mango ELF, immediately after the common
focus-stack insertion returns and before window rules run. At that point all
managed client-list insertion branches have completed. Unmanaged early-return
paths never reach the hook. The existing foreign-handle return remains the
conservative lower endpoint. This measures eligibility under the original
managed-list/application-ID predicate; it does not measure scene visibility,
pixels, presentation or first frame.

Each admitted profile pins the whole executable SHA-256, the complete mapping
function bytes, its file offset and length, the upper instruction offset and
compiled client ABI and actual IPC getter function bytes. The initial signed stable ELF audit identifies
`handle_client_map` at file offset `0x430d0`, length 4109, code SHA-256
`d48615861b8819d95e30fbbf74db46e24f8e3d738e20824e0e598578972004a2`.
Its upper instruction is `0x435ef`, after the focus-stack insertion at `0x435ea`.
The default, master/head and scroller insertion paths all converge before it.
The SysV callee-saved RBX still points to the mapped client. `Client`'s
foreign-handle pointer is at byte 1584; its identifier, app ID and client owner
are at handle bytes 56, 48 and 80. Actual retained, baseline and rebuilt ELF
profiles must be independently audited before those images are admitted;
unknown or changed executables fail instead of guessing a symbol or offset.
No extra debug package is installed. The hook's trap cost remains included.

Read-only static inspector run 37988626533 subsequently recovered the exact
retained and immutable baseline Mango files. Independent native and provenance
reviews admitted these two additional instrumentation profiles:

| Image | Whole executable SHA-256 | Map offset / upper / map SHA-256 |
| --- | --- | --- |
| Retained failed producer 37903438836 | `2f1107221157f47418cfda87dd091a3bb81ecd97dc2945184d0c42de7bbd254b` | `0x43110` / `0x4362f` / `3955d4a7db3fac1b5f0f17833562299ab299b2250eb2a4a66e7ac390f2dcb9bc` |
| Immutable v1.2.0 baseline | `67ba9d6d7831e35d028f15acad4cb71575489d26d3e23462f3879b6efa1f7b35` | `0x430d0` / `0x435ef` / `11a56d467fe7e444f46fa6da1f91a88ecf1a26bc3c54e4965727438e078a47dd` |

Each complete 4109-byte map received its own branch/register audit. The shared
1234-byte original getter and compiled field chains are separately pinned in
each profile. The profile's native audit SHA-256 is
`c263158a0e29ee302bed2f09a24c43e9017ce7d87ceb53d22b86398b39dcd2aa`.
Extracted file hashes agree with each image's RPMDB file records; this is not a
verification of target RPM signatures or all installed files. The retained
producer remains failed and unqualified. Actual library/readiness, kernel
format/filter, precision and paired-boot checks remain necessary. A rebuilt ISO
with changed code, packaging notes or build ID needs a separate exact audit;
neither identical source nor a matching map function admits an unknown ELF.

The type-specific upper receipt records the kernel's literal instruction
address, the client and handle pointers, the handle's owner, the same foreign
identifier, the original application ID and the foreign-handle copy. Linux's
entry formatter emits `event: (0x%lx)`, its `x64` formatter emits `0x%Lx` and
its `u32` formatter emits decimal `%u`. The parser requires those literal forms
instead of silently interpreting a different event format. The instruction address must match the unique
actual executable mapping in the desktop-owned Mango process. The handle owner
must equal the captured client. The collector rechecks PID, UID, start ticks and
executable before and after receiving each launch's receipts. All hooks use
PID filtering in the same owned `mono_raw` trace instance, bounded readers,
zero-loss checks and cancellation-safe cleanup. All three registered events are
removed; unrelated trace events are preserved.

The exact short ASCII application-ID predicate is required in this lane;
legacy title/substring matching does not receive a native upper. The original,
copied and later positive IPC app IDs must be equal, with case preserved, and
satisfy the original role predicate. The comparator binds that predicate to the
independently validated declared role IDs. The previous v11 assumption that a
long app ID could not clamp to a short accepted copy was incorrect: Mango's
UTF-8 boundary backtracking can manufacture such a copy from malformed input,
and wlroots does not validate app-ID UTF-8. A copied ID alone therefore cannot
establish the predicate at insertion.

The frozen IPC getter at `0x6b00`, length 1234, SHA-256
`11c0701eafb910c98f526a26d1926077f94bd411c7739db7066b6ba0742f7ead`
proves the original field chains. Client type 0 uses surface byte 328, XDG
toplevel byte 56 and app-ID byte 192; type 2 uses surface byte 328 and X11 class
byte 144. Two hooks at the same audited instruction capture only their selected
getter chain, with PID and client-type filters. The selected original is the
first dynamic string, followed by foreign identifier and copied ID. Each
accepted ID is 1–128 ASCII bytes; missing, invalid, escaped, overlong and
changed metadata fail. No request dispatch or metadata mutation occurs between
foreign-handle creation and this pre-rules instruction. The original getter
audit SHA-256 is
`3c6e8e8582215a02b16ebc24e85c8ca807df70dd6bc1c33f57684f656fc9b692`.

Kernel string capture does not guarantee that every failed fetch prints
`(fault)`. Its declaration-order allocator gives each string the remaining
dynamic budget. Forced truncation of the first string consumes that entire
budget, so the required subsequent nonempty foreign identifier and copied ID
cannot qualify. This remains true when an over-`PATH_MAX` original contributes
zero during size calculation; the first string's budget is not always large.
An intermediate pointer-chain fault can instead leave its data location
pointing at the subsequent 32-hex foreign identifier. Exact three-way equality
and explicit exclusion of 32-hex role IDs reject that alias. Source controls
cover near-page and over-`PATH_MAX` truncation, intermediate-chain aliasing and
final-string faults. Actual event-format/filter receipts and these hooks on the
target kernel remain pending runtime calibration.

For every retained window, both unique same-PID, same-ID receipts are mandatory.
The displayed timestamp receives one full text unit of rounding allowance:
subtract it for the lower event and add it for the upper event. Every receipt
must belong to the current launch, including the original positive IPC endpoint.
The collector intersects the original IPC bracket with the native bracket:
`lower = max(IPC lower, earliest native lower)` and
`upper = min(IPC upper, earliest native upper)`. The earliest endpoints preserve
the original predicate that any newly matching client is sufficient. A reversed
or disjoint intersection fails. The complete original IPC endpoints and query
roundtrips remain in the report; their latency is never silently subtracted.

The sample is the conservative upper of that intersection. The unchanged
precision budget is `min(5 ms, 2.5% of that sample)`; a shorter corrected sample
also has a tighter relative precision budget. Every original point regression,
10% enclosure limit and six paired boot requirement remains mandatory. No
sample is discarded to obtain a pass. Historical v10 and v11 evidence is rejected by
the versioned sampler. Actual retained-image calibration and the rebuilt image's
full paired test still decide whether this measurement method is usable.

## Managed-list insertion bracket (v13, pending fresh calibration)

Actual retained-image calibration
[37997321166](https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37997321166)
failed the original cold Foot sample's precision check. Its foreign-handle
creation at `250.819655` and historical upper at `250.826593` span 6.938 ms,
or 6.940 ms including display rounding, above that sample's 1.126084475 ms
limit. The other three native widths including rounding were 0.220, 0.220 and
0.393 ms. These observations do not identify which call or scheduling interval
caused the cold width. That image and run remain failed and unqualified.

The v13 role sampler uses method
`wlroots-0.20-and-mango-managed-list-original-appid-preinsert-bracket-raw-v5`
and observer `mango-socket-worker-v6-original-appid-preinsert-bracket-raw-clock-autonomous`.
It keeps the foreign-handle return receipt as separate identity provenance,
and brackets the same managed-client-list membership transition with probes
immediately before each actual `wl_list_insert` call and at their common return
successor. Focus-stack work after this successor is outside the membership
bracket. The original negative/positive IPC interval is still required and
intersected with the native interval. This measures availability under the same
managed-list/app-ID predicate; it is neither response delivery nor first frame.

The independently replayed exact-byte CFG audit covers all three admitted ELFs,
including the cold helper's real jump back into the error path and 69 static
negative controls. Its report SHA-256 is
`dacb0de958e7ba90099a70b2e66f49756916ed3d42f4e70ac6280f7d4b6a571c`.
Whole-ELF, complete map function, original getter, ABI and original app-ID audit
pins remain mandatory. No new executable is admitted by matching source alone.

| Exact executable | Tail pre-call | Head pre-call | Scroller pre-call | Common post-call |
| --- | --- | --- | --- | --- |
| Retained `2f110722…` | `0x43619` | `0x43773` | `0x43da3` | `0x4361e` |
| Immutable baseline `67ba9d6d…` | `0x435d9` | `0x43733` | `0x43d63` | `0x435de` |
| Previously audited stable `1c66767f…` | `0x435d9` | `0x43733` | `0x43d63` | `0x435de` |

At every call, RSI is `Client.link` at client byte 280. RDI is the correct
position in `server.clients`: its tail predecessor, head, or the selected
scroller client's link with a tail fallback. Exact IPC loop bytes enumerate
this list at `0x7f348`, distinct from the focus stack at `0x7f358`. RBX is the
client, R12 the client listener at byte 360 and R14 its link; the proof explicitly
assumes the SysV callee-preserved RBX/R12/R14 ABI and valid compositor list,
monitor selection and scroller state. It is not a complete heap-integrity proof.
Each managed path reaches exactly one selected pre-call and the common post-call;
unmanaged and error paths cannot reach them.

Six type-specific pre-call events and two post-call events preserve the selected
original-first string capture and every original identity, ownership and fault
guard. All three same-ID receipts must belong to the current launch and agree
with the later IPC metadata. The collector archives literal `format` and
`filter` readbacks with SHA-256 for all nine events, checks their exact field
types/layouts and PID/type filters before tracing, and rereads them before and
after receipt collection. Missing, changed, malformed or coherently resealed
incompatible schemas fail. Cleanup removes every owned hook.

Official Linux v7.2 `trace_uprobe.c` fetches probe arguments before reserving the
event timestamp. The user thread remains trapped until the pre-call timestamp,
and the post-call timestamp follows insertion, so this fetch order preserves
the conservative bracket. Probe fetching, timestamp reservation, trap and
preemption costs remain in the measured sample or interval; none is subtracted.
That supporting source is not an exact audit of Fedora
`7.2.9-200.fc44.x86_64`. Actual target-kernel format/filter and fresh cold timing
must still validate this implementation. Source replay cannot promise that the
next cold sample passes. The first sample is not warmed, discarded or replaced,
and all precision, enclosure, regression and paired-boot limits remain unchanged.

The research calibration composer embeds the same new recorder and validator
into its unchanged four sequential Foot launches. Its source and comparator
hashes update from those literal sources; the paired composer independently
freezes the new source and exact composed-script hashes. Old v12 receipts cannot
qualify the new lane. A separately reviewed independent calibration reader must
also bind the new identity/pre/post fields and nine archived kernel readbacks
before any new research run is interpreted. No activation or image qualification
is implied by this source change.

## Frozen external qualification of an unchanged ISO

The artifact-only producer embeds its Actions run ID in preview RPM versions.
Mango's allocated packaging note consequently changes between a source-check
RPM and a new ISO, even when native instructions match. Whole-ELF admission is
retained. Packaging notes, build IDs, layouts and code are never normalized to
admit an executable that has not been independently audited.

The explicit `frozen-external-paired-v1` producer mode first completes the
original UEFI Try, BIOS Install and UEFI Safe startup checks and the strict
2,000,000,000-byte limit. It produces a typed byte-pinned performance-plan
receipt, with paired performance deliberately skipped and publication skipped.
The producer itself must succeed on attempt one. A failed historical producer,
including run 37903438836, cannot use this mode to become eligible.

After extraction and review of the exact candidate and immutable baseline
executables, a separate execution manifest freezes the observer, comparator,
harness, container helpers, baseline profile and image-source file hashes. A
sole-marker child of that reviewed source activates one first-attempt push
lane. Its candidate source checkout is clean at the ISO's full source SHA;
that checkout supplies the installer profile, catalog, battery source and RPM
commit expectation. The separate execution checkout supplies the frozen
measurement tools. Image source and execution source are distinct identities.

The lane performs both original offline installations and all six interleaved
boots, in order baseline-1, candidate-1, candidate-2, baseline-2, baseline-3,
candidate-3. It retains the original 120-minute runner timeout, KVM, 4 GiB RAM,
two vCPUs, restricted networking, pristine powered-off installation sources,
fresh overlays, console restoration and every original precision, regression
and enclosure limit. Actual input ISO and candidate-source hashes are checked
again before each VM stage. The same prepared container, QEMU and firmware
inventory is required throughout. No alternate boots or partial run can pass.

Every guest binds its unique context to the expected observer source and hashes
the actual frozen probe file. Complete original serial logs, contexts, install
exits, pristine source identities, tool inventories, original byte hashes and
the exact producer receipt are retained. Qualification and publication both
replay all six unredacted serial logs with the byte-pinned comparator and require
type-sensitive equality of the full recomputed result. Equal self-declared
observer hashes, a passing summary, duplicate canonical records, non-finite
numbers, reruns, omitted boots or redacted/truncated inputs cannot qualify.

The legacy in-producer paired mode continues requiring its successful paired
step and same producer/source binding. The external mode is an explicit
alternative evidence contract; it does not weaken the legacy contract or claim
optimization from a regression pass. The prepared manifest is disabled until
actual images, admitted executable profiles and reviewed source are available.
