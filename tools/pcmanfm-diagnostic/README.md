# Finite GTK keymap observation and separate bulk channel, default off

This audit-only successor derives from diagnostic head
92aa52c0ef324a2cb5ad4af9f0c47c5e8b273bec. Actual diagnostic run 37548983381
failed strict JSON transport: a watchdog line was inserted inline into one
serial chunk and one AAC output chunk was absent. Both PCManFM title gates and
both simple GTK activation gates failed. AT-SPI IsEnabled was false in nine
samples; the conditional PCManFM physical route was unrun. Those failures,
artifacts, raw kernel anomalies and the earlier native failures remain intact.
This packet makes no product changes or native/release acceptance claim.

The fixed ISO remains 1,880,244,224 bytes, SHA256
84c9c88ebcbcaf69dbabf56509a9ceb2db58e5dc41d7bae12093edba12f60718, from source
fe4742c8b9414c45f0bcbb0a4191f116383c60d1. No rebuild, package/configuration or
security change is made. An actual successor run requires independent source
review and root promotion/approval; this owner does not push or dispatch.

## Original workloads and added observations

The frozen native library, launcher and complete security collector remain
byte-identical. Original arctic-open launch, four literal PCManFM wtype inputs,
Shift_L prefix, pauses, 30-second directory-title wait, terminal sleep(60) and
cleanup remain exact. The observed PCManFM route retains its separately declared
native debug launch, sleep(180), AT-SPI observations, four inputs and 30-second
wait. Neither route gets an activation call, CLI navigation, retry, IM override
or delay-until-pass. Original conditional physical Return is unchanged and
remains unavailable when its fresh AT-SPI location entry cannot be observed.

Both GTK controls retain their original three virtual input turns and 30-second
activation wait. The existing owned key callback now records group, modifier and
send-event fields, current Gdk.Keymap translation of event hardware/state/group,
Return keycode/group/level enumeration, keymap-change sequence, and exposed
Gtk.Settings IM/accel values. Map-change and IM-setting-notify records are bounded
by the unchanged 2 MiB GTK event log. The callback returns False and never calls
binding activation, IM filtering, emit, or a settings setter. A missing or broken
required API becomes an explicit collector failure, never invented telemetry.

Current-map reads happen in the callback before the normal parent handler; they
do not observe the parent's later lookup or private IM consumption. Gtk.Settings
values do not prove which private context consumed an event. Logging can perturb
scheduling, so a matching/mismatching translation is a bounded observation, not
by itself a causal proof or a repair. The preceding raw log shows a 35,356-byte
map following the final key release by 5.972 ms; its bytes and identity were not
captured. The host US-map model remains an explicitly separate model.

Only the no-warmup GTK control is eligible for one separately labelled physical
Return, after its unchanged virtual activation gate has failed. A disclosed
100 ms read-only owned-widget observer responds to one nonce request. Before
publication, the guest rechecks unique native client, current PID/start/UID/ELF,
exact nonce title/appID, geometry, compositor focus, and its own entry's exact
text, widget focus/window-active state, zero activations, boot and positive monotonic snapshot age
(at most 1 s). The host also binds widget UID to both launcher desktop identities
before input. An unfocused client is unrun; changed/malformed bindings fail.
There is no focus repair. The host consumes the nonce before one strict QMP
press/release, rejects a stale handling interval over 2 s, and records its
acknowledgement separately. A separate 30-second GTK-only observation follows;
no activation is emitted. Host delivery requires matching raw widget evidence,
boot/nonce/process and an exact empty QMP result. This cannot qualify PCManFM or
replace either original virtual-input failure. No additional physical navigation
arm is introduced.

## Separate diagnostic bulk channel

The diagnostic branch adds one virtio-serial-pci device and named virtserialport
org.arctic.diagnostic.bulk, connected to a distinct one-use QEMU Unix socket.
This is an explicit device/channel perturbation. Main disk, OVMF/display/network/
audio choices, ttyS0 device, original console kernel arguments and launcher
remain unchanged; no serial repair, filtering, IRQ/security disable or 9P host
write is used. Actual tool/argv hashes are recorded, not assumed equal to earlier
runs. Device addition prevents an unqualified same-workload performance claim.

Only native evidence CHUNK/MANIFEST payload moves from stdout to the new channel.
BEGIN/REPORT/END are duplicated byte-for-byte in format to that channel; original
console control records and kernel output remain raw. Bulk protocol allows one
BEGIN, one REPORT, ordered CHUNK records, one MANIFEST and one END, all complete
UTF-8 newline JSON objects. Duplicate JSON keys, nonfinite values, unknown/blank/
reordered/truncated records fail. Existing zlib/Base64, path, content hash,
compressed/uncompressed count and extraction checks stay in the frozen v4
extractor. Console launcher proof and physical requests are paired from their
actual separate origin; no merged or fabricated serial stream is constructed.

The guest verifies the exact named character device, sysfs port name and opened
major/minor identity. Guarded root/live location checks precede opening it.
The host binds SO_PEERCRED to the actual current owned QEMU PID/start/UID,
retains raw stream count/SHA/line count, and requires physical socket EOF only
after owned QEMU shutdown/observed exit. Guest fd close is not EOF proof. EOF allowance is anchored before controller work, and failed controller/bulk
imports retain owned VM cleanup. Setup,
VM-quit, EOF and raw/socket-close failures retain primary and cleanup errors;
both owned resources are closed independently. No reconnect or console fallback.

| Evidence bound | Value |
| --- | --- |
| Decoded native evidence | 128 files, 4 MiB/file, 16 MiB aggregate, unchanged |
| Encoded bulk raw stream / newline | 24 MiB / 256 KiB, additional finite limits |
| Guest export writer | 60 s total; blocked/partial writes fail |
| Receiver pump | at most 32 reads of 64 KiB per turn |
| Post-owned-QEMU socket EOF | at most 5 s, capped by remaining harness deadline |
| Original guest / host | 600 s / 900 s, unchanged |
| GTK event log / required per-arm trace | 2 MiB each, zero trace omissions |

A real incompressible 16 MiB/four-file fixture roundtrips through the unchanged
export and frozen extractor under the new encoded limit. This does not promise
that all independent caps or arbitrary long-path headers fit simultaneously.
Actual excess fails without truncation or expanded limits. The earlier mandatory
file budget was 98; the one GTK request/snapshot/proof/extra frame adds four,
for 102 planned files. Dynamically copied application files consume more slots.
The old 128-file/4 MiB/16 MiB exporter remains the final gate.

The old strict console decoder is kept verbatim and run against untouched new
console bytes, with its error preserved. It is expected to reject a console that
intentionally lacks the bulk CHUNK/MANIFEST records. That expected absence is not
a repaired historical serial failure or proof of an IRQ cause. Raw console
pattern observations retain exact anomaly offsets/line hashes and bounded
excerpts, never trusted AVC absence or inferred driver ownership. The complete
raw log is preserved independently.

## Security, codec and qualification limits

All previous complete journal-after-cursor and audit-file gates are unchanged:
SELinux Enforcing, audit enabled=1/lost=0, strict boot/cursor/framing/typed raw
command proofs, complete trusted kernel/audit preservation and zero observed
new matching AVCs. Whole-journal bounds remain 16 MiB/8192 records/256 KiB per
newline/60 s, trusted rows 8 MiB split into at most 11 files, audit delta 4 MiB.
Failure preserves incomplete/error state and primary errors, never a synthetic
selinux pass. The exercised interval ends before export; later console/kernel
anomalies remain outside that security interval and must be reviewed separately.

Codec capability and the original 14,443-byte H264/AAC diagnostic remain after
all four navigation arms, with unchanged 256 KiB/15 s listings and 1 MiB/15 s
stream-decode bounds. H264 decoder errors are retained; no packages or backend
are changed. AAC qualification requires the complete raw member, not a guest
summary. Listing/decode do not prove displayed media/audio or baseline parity.
Final 250-record system/user journals are supplementary, never a complete gate.

Native navigation, F4/editor-save/GUI archive and installed checks remain open.
This packet does not repeat installer/recovery/SecureBoot, physical hardware,
gaming, broad accessibility, media parity or performance qualification.

## Source reproduction and host controls

Run prepare-diagnostic.py --repository <read-only repo containing 92aa52c0>.
The pure generator maps 27 execution files plus the self-excluded manifest and
13 runtime files; 19 frozen predecessor pins are preserved. Actual workflow maps
to .github/workflows/iso.yml, without an audit duplicate in the deployed subtree.
Git mode is 100755 for tools/test-iso.sh and 100644 for other mapped files.
Default-off workflow inputs/other-job exclusions remain unchanged; only explicit
selected diagnostic device/adapter edits and diagnostic text/output names change.
Actual source/ISO metadata are rechecked immediately before runtime.

Run python3 -W error::ResourceWarning -m unittest discover -s <packet> -p
 'test*.py' -v in audit and mapped layouts. The host lacks dbus and GI; those
runtime-binding checks are explicit skips. Mapped layout additionally skips three
prior AST/base-Git snapshot methods that are audit-only, while exact deployed pins and
workflow controls run. Unix streams/EOF, owned-child boundaries, cleanup errors,
full payload extraction and all adverse typed/framing cases are real host controls;
widget/compositor/QMP fixtures are synthetic authority, never guest success.
No dependency install merely removes a skip. Actual observation remains unrun.

The first exact v3 freeze is preserved as pcmanfm-navigation-diagnostic-v3-prior-ready-c3e533c2. The independent four-case blocker is retained: corrected positive GTK monotonic fields, pre-input widget/launcher UID pairing, successful-import cleanup ownership, and pre-action absolute EOF allowance. Original workloads, channel/payload caps, callback observations and security/codec code are unchanged.
