# PCManFM same-image diagnostic successor, default off

This audit-only packet derives from the failed diagnostic head
84fa7410c728e355a507054d7e7a944c51e76753. Original run 37543716623, its artifact
11449673824 and the earlier native failures remain unchanged. It does not rebuild
or modify the 1,880,244,224-byte ISO (SHA256
84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718). Native run
37535425230 remains failed, seven of eight live gates; F4/save/archive and all
installed checks remain unrun. Every diagnostic report has release_acceptance=false.

Only a separately promoted, independently reviewed execution may select the
workflow's default-false same_iso_pcmanfm_diagnostic input. Build/release/install,
recovery, native-smoke and performance jobs are skipped. Candidate fe4742c and the
clean ae55 recovery checkout remain pinned; metadata and actual ISO bytes are
rechecked immediately before the VM after provisioning. Unchanged v2 execution,
Docker and owned cleanup primitives and frozen v4 extraction are reused without
monkeypatching. This owner performs no VM, push, dispatch or product edits.

## Four demonstrated harness corrections

The original arm keeps arctic-open, frozen four literal wtype turns (including
Shift_L warm-up), pauses, 30-second title wait and sleep(60) terminal fixture.
There is no additional retry, delay-until-pass, CLI navigation or acceptance
fallback. The observed arm keeps the same inputs and title gate, its explicitly
instrumented sleep(180) terminal and bounded AT-SPI observations. Its only launch
change is a direct owned /usr/bin/pcmanfm child, with no folder/CLI arguments,
under copied HOME/XDG. The signed/generated role helper resolves files=pcmanfm
and no extra arguments. Direct launch preserves stdout/stderr that arctic-open's
setsid/detach/redirection discarded in the failed diagnostic.

The helper guard targets the actual regular0755 RPM-owned /usr/bin/arctic-open,
SHA e44586b3b3d738888a6e12f58c6cf7cc6bbf980412d80c79d7cecaff539b1b75, exact
candidate owner/NEVRA/epoch. Replacing ONLY the raw source shebang yields that
same-image fingerprint; remaining role/argument/redirection bytes are identical.
That relation is source/evidence proof, not a fresh RPM-signature replay. The
actual native child PID/start/UID/ELF/hash must equal the mapped native client,
selected role/PATH/RPM proof and current owned WAYLAND_DEBUG=client environment.
Before/after focus/visibility/geometry/client identity are verified. Global
Wayland environment or backend settings are never changed. Complete nonempty
stderr with registry/keyboard initialization is mandatory under the unchanged
combined2MiB/180s bound; partial newline/overflow/producer error fails. A key-event
count of zero is a valid observed diagnostic result, never activation success.

The two isolated GTK3 controls set GLib's nonce program name before importing or
initializing Gtk/Gdk. Each requires exact nonce appid/title, native Wayland, unique
owned PID/start/UID/ELF and matching own mapped log. Their own key/state/focus/text/
activate records compare the original warm-up with no-warm-up. They cannot qualify
PCManFM, private GTK activation or input-method state.

The new security collector preserves complete finite after-cursor evidence rather
than treating the old bounded journal tail as complete. Failed collection keeps
primary errors, actual states and observed counts; host validation rejects an
incomplete schema explicitly instead of indexing a missing selinux field.

## Evidence bounds and security preservation

The journal command is journalctl -b --no-pager --all --after-cursor <initial>
-o json. --all avoids journalctl's default replacement of long fields with null.
A fixed current-boot initial/end cursor pair bounds the exercised interval; the
finite EOF scan must include the end cursor, or prove an empty unchanged interval.
Duplicate JSON keys, nonfinite data, missing/wrong boot/cursor/transport, malformed
MESSAGE representations, ambiguous/non-UTF8 binary messages, truncated newline
records, stderr, nonzero exit or timeout fail. String, byte-octet and repeated
MESSAGE values are parsed strictly. All trusted _TRANSPORT kernel/audit rows and
all matched denial rows from any transport are preserved, without splitting a
JSON record. Full command stream digest/count/bytes are recorded; untrusted,
non-denial rows are counted/hashed but not all copied. Trusted rows cannot be
omitted merely because their current message is not a denial.

| Evidence | Finite bound |
| --- | --- |
| Whole journal stdout / records / record / deadline |16MiB /8192 /256KiB newline record /60s |
| Trusted or denial raw rows / chunk |8MiB /1MiB; at most11 chunks |
| Exact audit-file interval |4MiB, original bound |
| Fourteen small state/cursor commands |64KiB stdout and stderr each,15s each; reversible raw framing in one3MiB JSONL member |
| Owned PCManFM stdout + stderr |2MiB combined,180s |
| Mandatory raw GUI trace |2MiB per arm, zero omissions |
| Frozen guest export |128 files,4MiB/file,16MiB aggregate |

Six initial/inter-arm/final Enforcing/audit states are retained. Their exact raw
getenforce/auditctl commands, stdout/stderr Base64, counters/digests/errors and
owned-child reap records share one bounded newline-framed member. Names must be
unique and recognized; malformed/truncated/noncanonical framing fails. Initial/
final cursor commands are in the same reversible framing. Whole-stream metadata,
raw trusted chunks, states/report and audit metadata remain separate. Host pairing
requires all mandatory members, raw state values, hashes/lengths/counters/commands,
current boot/cursors and exact summary agreement. Missing raw proof cannot be
waived by a successful guest summary.

Audit-file inode/device/offset continuity includes absent-to-present, rotation,
truncation and read/path races. The strict gates remain SELinux Enforcing,
audit enabled=1/lost=0 and zero observed new matching AVCs across the complete
trusted interval plus audit-file delta. Incomplete evidence never asserts zero
AVCs. Actual before/final state survives a later collector error. All stream
setup/deadline/callback/interruption failures reap only the direct owned child.

The audit budget fixture proves98 planned mandatory files including both GTK
arms, a possible physical branch, all codec records and11 full trusted chunks;
actual copied GVFS/application files consume additional slots. Fourteen maximum
small stdout records fit their single3MiB framing member. Independent byte caps
cannot all coexist within16MiB: the unchanged exporter demonstrably fails an
actual aggregate excess. No guarantee that a future VM interval fits every cap,
no enlarged transport and no truncation of required evidence. Actual preservation
overflow remains diagnostic failure requiring review.

## Unchanged conditional physical route and post-arm media scope

AT-SPI remains at its actual enabled state. There is no enabling, global key
listener, mutating accessibility operation or toolkit configuration change.
Current a11y-bus unique-owner→PID/start/UID/ELF/client bindings surround snapshots;
unexported/unrecognized location identity is unavailable, valid optional missing
methods are unsupported, while malformed/timeout/changed identities fail.

The single physical Return requires a fresh exact owned focused location entry
containing the fixture path after the observed virtual timeout. It uses one
output-only guest request and separate one-use host QMP press/release proof, with
no focus repair/resend. Actual IsEnabled=false in all nine old samples made this
arm unrun; it will remain unavailable if that precondition remains unobservable.
The successor does not introduce a full physical-key navigation alternative.
Neither GTK nor conditional physical results replace the original failed gate.

Only after all four arms, exact native FFmpeg binary/RPM identity, capability
listings and the original generated14,443-byte H264/AAC fixture are exercised.
Each listing has256KiB/15s; each mapped stream decode has1MiB/15s and retained
count/hash/exit/stderr. Unsupported decode errors remain separate diagnostic
results. Host hashes are references, not cross-version success requirements.
Listing/command decode does not prove displayed motion/audio or broad codec parity.
The final250 system/user journal records are supplementary, explicitly bounded
logs; they never substitute for the complete security interval.

## Reproduction and limits

Run prepare-diagnostic.py --repository <read-only repo containing84fa>. It exports
the24-file execution map,11 runtime pins, exact modes (test-iso.sh100755, others
100644), pure harness/workflow patches and19 frozen predecessor pins. The
registered workflow maps to .github/workflows/iso.yml without a duplicate under
tools. The self-excluded execution manifest is deployed beside the packet.
The common native/recovery libraries keep byte-identical hashes. The only
existing harness change from84fa is adding the collector to the diagnostic data
CD; default behavior remains unchanged. The workflow updates only diagnostic
text/output namespace; the input/guards remain default off.

Run python3 -W error::ResourceWarning -m unittest discover -s <packet> -p
 'test*.py' -v in the audit and mapped layouts. Missing-host-dbus is an explicit
runtime-binding skip; mapped layout also skips audit-only base-snapshot generation
replay. Real framed streams, overflow/partial EOF, binary denials, audit races,
owned interruption/reap, raw-pair negatives and helper/GTK identity controls are
host evidence only; synthetic UI/boot/bus authority never claims guest success.

The host VM remains900s, the guest600s, each original wait30s, and no owner run
occurs before independent source review/root promotion. Device/ISO choices and
read-only diagnostic CD placement follow the frozen native harness; actual new
QEMU/firmware/tool/argv hashes are collected without assuming prior tool parity.
No installed/recovery/SecureBoot/audio/hardware qualification occurs here. Actual
VM collection, causal diagnosis and full native acceptance remain open.

Independent successor source corrections: role records now separate only at LF,
matching the pinned Bash helper and preserving/rejecting CR/control separators
rather than normalizing another configured value. Successful raw command proofs
require actual typed child PID>1 and finite nonnegative ordered monotonic times.
Original82 controls/history and initial blocker report are preserved; two new
adverse controls exercise the demonstrated guard cases. Workloads/caps unchanged.
