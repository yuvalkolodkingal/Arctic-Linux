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

## Causal lower-bound extension (unqualified until real calibration)

The replacement ISO run 37903438836 also failed precision: 20 of 36 baseline
brackets and 15 of 36 candidate brackets exceeded their original limits, although
all point regressions were within their limits and the enclosure check passed.
Candidate Foot cold brackets were 12.4–12.9 ms against 1.61–1.77 ms limits.
The original evidence is retained. A new observer cannot reclassify this image.

The v9 paired observer adds a read-only kernel return probe to the actual loaded
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
`mono` clock. It leaves scheduling, compositor source/binary files, preferences and SELinux
enforcement intact. Uprobes temporarily trap the observed function's return in
the kernel; that instrumentation and reader costs are included in the
measurement; a frozen combined source hash is shared by all six boots.

Unknown identifiers, wrong-process events, wrong clocks, stale/future receipts,
unsupported ELF layouts, absent tracing, lost events, bounded-reader overflow and
cleanup failure fail qualification. Kernel text timestamp precision is disclosed;
printed timestamps are conservatively floored, and resolution above 1 microsecond
is rejected by comparison. The root collector removes only its own event and
instance, and unmounts tracefs only if it mounted it. No persistent configuration
or SELinux relaxation is installed. Historical v8 role evidence remains rejected.

Source controls are not runtime calibration. Before another final-image build,
an explicitly unqualified research lane should try this instrument on the retained
failed image and preserve actual library/probe/loss/timing evidence. That lane must
not pass the native image fetch guard, mark a failed producer qualified, publish,
or supply final six-boot acceptance. The final image still requires six fresh paired
KVM boots and every unchanged precision, enclosure and regression check.
