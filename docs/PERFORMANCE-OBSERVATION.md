# Mapped-window observation

The paired performance run uses an unmodified Mango 0.17.3 session and a frozen
collector/toolchain shared by all three pristine boots of each image. Different
configured apps are compared by declared desktop role. No host cache flush,
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
