# Same-image Safe restart and visibility experiment

This diagnostic compares two fresh sessions on the original A2 ISO from run
38032256030. It builds no ISO and makes no product change. The original display
corruption remains a release blocker; this experiment alone cannot establish
cause, rendering acceptance, optimization or release qualification. All four
acceptance/profile flags remain false. The disabled source has `ready=false`.

The dedicated branch is `codex/safe-rerender-v6-20261010`. The preparation must be
a sole child of the exact operational base recorded in `common.PREPARATION_BASE`,
adding only this workflow and the eight diagnostic files. Publication alone
cannot start it. Root owns the first, sole marker child that adds
`.github/safe-rerender-v6-20261010.activate`, containing its reviewed parent SHA
plus a newline. First push/attempt, exact live branch/head, nine ADD paths,
14 execution hashes, eight original source blobs and ten image/producer pins
are checked. No old lane is enabled or repinned by this source preparation.

The unchanged frozen image fetcher verifies the original successful producer,
archive and ISO SHA-256, producer receipt, strict byte-size and startup gates.
The VM uses real KVM, q35, virtio VGA, four vCPUs, 4096 MiB, original UEFI and
the exact Safe Try entry (`arctic.mode=try nomodeset`). The original blank
64 GiB disk, boot CD and boot order are preserved. Only the existing root-owned
read-only diagnostic data CD on `ide.1` and duplex virtio evidence port are
added. The host VM container has no network. SELinux must stay Enforcing;
software-renderer, hardware and security settings are preserved.

Original QMP captures at 35, 80 and 125 seconds after Safe selection precede
any VT login, terminal, readback or restart. After authenticated VT6 login and
read-only `ARCTICSAFE` CD setup, the guest records the original actual Mango
PID/start ticks, argv, software environment, mapped renderer hashes, output and
configuration hashes. The original baseline cannot be presented as a restart
arm or as evidence that the selector affected the initial boot.

Arms run in a fixed order: `default-restart`, then `visibility-restart`.
Each uses a temporary, exclusively acquired SDDM SessionCommand wrapper that
chains the actual packaged trusted Wayland script and original argv. The
Both arms unset `WLR_SCENE_DEBUG_DAMAGE`. The default arm also unsets
`WLR_SCENE_DISABLE_VISIBILITY`; the second exports its exact source-supported
value `1` before the new Mango process creates its scene. This tests visibility
culling separately from full-output damage. The previous rerender experiment
retains its original failed run and mixed visual results. Profiles run through the original script. The compiled script path,
RPM owner, effective SDDM precedence, autologin session, protected files and
original desktop argv are verified before restart. Conflicts fail closed.
The matching Fedora `sddm-0.21.0-13.fc44` package builds its canonical script
at `/etc/sddm/wayland-session`; that fixed path is admitted alongside the
existing two packaged paths. RPM membership/owner, protected regular-file
mode, compiled/effective equality and higher-priority conflict checks still
apply. The earlier run reported only the broader `session-contract` phase;
source packaging proves the missing-path incompatibility, not its exact
runtime failing expression.

The retained v2 first attempt passed that session contract and failed in the
broader `session-handoff` phase before either arm became ready. Its individual
condition is unknown. The prior v3 source added only closed observations around the
existing handoff operations. The earlier fixed guest status schema v2 carried an
optional primary ID only for an exact, source-owned RuntimeError literal in a
handoff phase. Unknown messages, subclasses, command stderr, paths and errno
remain unobserved. Original exceptions, guarded operations, retries already
present in desktop discovery, timeouts and cleanup stay unchanged. A retained
primary phase/class/ID survives a secondary cleanup or reporting failure.
The original serial privacy oracle still rejects arbitrary private text;
projecting a fixed status cannot sanitize or bypass that whole-text check.

Only the owned wrapper/configuration receive targeted `restorecon`. Expected
policy and actual full public SELinux labels are attested. If ordinary policy
labels the nonce sibling differently, only that newly acquired wrapper may
receive `chcon --reference` from the unchanged packaged script. Its original
dev/inode/UID/mode/bytes are rechecked before and after the handoff. The original
script must already match policy. No policy module, permission expansion or
Enforcing exception is used. A writable acquisition FD is replaced by an O_PATH
FD for the same inode before execution; cleanup refuses foreign replacements.

The old Mango identity is held with an acquired pidfd. After each SDDM restart,
the new desktop, session, VT, Wayland socket and IPC environment are rediscovered.
No previous authentication prefix is reused. New PID/start ticks, exact executable,
argv, mapped libraries, selector, preserved software flags, output and unchanged
compositor configuration are verified before an arm-ready acknowledgement.
The actual Mango XDG_SESSION_ID must match the fresh prefix and exact loginctl
session ID, UID 1000 and Wayland type. After selecting that session's VT,
loginctl must confirm Active=yes. The closed session binding is attested before
the ready clock and bound again in the returned arm report.

Each arm gets QMP-only captures 35, 80 and 125 seconds after that attested
acknowledgement, before its Foot/readback phase. Exact scene-creation time is
unmeasured. Later samples retain the original three-second restoration delay,
synthetic Foot text, two-second launch delay and 22-second repaint delay.
Each `restored-desktop`, `terminal-initial` and `terminal-repaint` sample
brackets original raw Wayland capture with QMP-before and QMP-after, bounded
to 25 seconds. Readback can itself force repaint; a clean raw/post image cannot
alone isolate scanout or prove a cause.

Original wl_shm stride×height bytes, format/stride/flags, output metadata,
packed P6 RGB and QMP PNGs are retained. The unchanged C helper and independent
host raw conversion verify hashes, channel packing and protocol y-inversion.
Derived PNGs are labelled and never replace originals. Only the synthetic
owned Foot child/pidfd tree is cleaned up. The named virtio port has one guarded
O_RDWR open and an owned dup; the shared protected runtime is unchanged.

Guest Mango user/system CPU ticks, RSS and aggregate guest CPU ticks bracket
each idle and original Foot-capture interval. These are observations from one
ordered experiment. Warm caches, minute boundaries, restart order and readback
perturbation remain confounders. No performance acceptance or negligible-cost
claim follows from these counters.

Three separately closed artifacts retain context and each arm:
`unqualified-safe-rerender-context`,
`unqualified-safe-rerender-default-restart`, and
`unqualified-safe-rerender-visibility-restart`.
Each has at most 40 members, 32 MiB per member and 128 MiB expanded bytes.
The guest transport retains its 200 MiB wire limit. Archives are separate to
keep retrieval practical; no compressed-size guarantee is asserted.

The original whole serial/text privacy oracle must pass before any arm export.
No transcript, audio, full environment, history, credentials or arbitrary
exception message is collected or projected. Fixed statuses accept only known
phases/classes and the validated execution/image/nonce context. Original bytes
are preserved or rejected. Private stage command output stays excluded.
Missing context can still expose a strictly screened fixed early-stage report;
restart members always require the original validated context.

The additional arm time uses a reviewed 15-minute inner diagnostic deadline.
The existing 19-minute wrapper, 20-minute workflow step and 40-minute job bounds
remain. Product, startup and performance acceptance limits are unchanged.
Owned process-group cleanup retains the unreaped leader identity through TERM/KILL.
Firmware/disk temporaries retain acquired descriptors and inode identities.
Primary failures survive cleanup, reporting and privacy-screen failures; a
secondary failure still fails a zero-primary run. No retry is hidden.

Relevant source tests exercise the actual controller/export/guard functions,
real tiny executable wrappers and labelled synthetic desktop/KVM/image adapters.
They provide no real OS, renderer, SELinux policy, KVM or rescue result. Cached
historical ownership/topology controls are retained with their original limits;
this preparation does not repeat those container controls. Actual compiler,
KVM captures, original archive authentication and independent visual review
remain prerequisites for interpreting the experiment.

The inherited v4 discovery authenticates the freshly attested UID1000 compositor through Linux AF_UNIX SO_PEERCRED on its Wayland and PID-named Mango IPC endpoints, with unchanged process start identity before and after discovery. Prefix fields come from that new process and children in the same XDG_SESSION_ID only. Unrelated old sockets and children cannot select another session. The original shared Native helper and every inherited source plan remain unchanged. The last exact trusted discovery guard is a closed diagnostic label alongside the original readiness deadline; neither this label nor the earlier v3 deadline proves the underlying runtime cause. Original host, capture sequence, renderer controls, CPU counters, security and acceptance limits are retained.


This v5 namespace corrects only the restart fixture's use of whole desktop
state as output identity. The retained actual v4 report has the official
Mango 0.17.3 nineteen-field monitor record. Exactly one output, its name,
x/y, width/height, scale, HDR and VRR values must still equal the original.
The configured tag count (`tag_num = config.tag_num`) is also retained.
The selected-monitor `active` flag remains an independent equality check;
it is not a hardware property or loginctl session Active. The later bound
VT restoration and loginctl Active=yes check remain unchanged.

`layout_index`, `layout_symbol`, `hide_clients`, `tags`,
`active_tags`, `active_client`, `last_open_surface`, `keymode` and
`keyboardlayout` describe mutable desktop, client or input state. Their
full values stay in the original and returned monitor observations; they
are excluded from output-configuration equality. Official mmsg reports
no separate output mode, transform, make/model or connector identity.
Existing original-image/source binding, single output, exact1920×1080
readback mode, scale1, transform0, renderer/library/configuration, security,
session, timing and capture checks remain unchanged. No missing hardware
field is invented or represented as observed.

The closed fixed guest schema v4 derives a failure role from a source-known
operation phase: output-command, output-parse, output-configuration,
selected-output or selinux-enforcing. This labels the observed operation;
it does not claim an exact raising call or reveal exception text, monitor
values, command output or errno. Whole serial privacy screening remains
mandatory. The actual v4 failed operand is unknown; only its broader
output/security phase and readiness deadline were observed. Targeted source
controls show that the original whole comparison rejects a changed client
or tag despite unchanged output configuration. The correction and roles
provide no rendering rescue, CPU cost or image qualification result.

The new compositor is bound before each arm-ready acknowledgement to the actual
PID/start ticks, character-device major/minor and a closed kernel-driver enum.
Only exact source-known allocator/backend journal marker booleans are projected
from that same PID. Missing, timed out or undecodable logs stay unknown; markers do not independently
identify an allocator object or establish cause. Raw journal text and unrecognised
driver strings are excluded from the added binding. Original initial diagnostic
fields remain attributed to the pre-restart process. No debug logging is enabled.
The extra bounded journal query can take up to 20 seconds before the arm-ready
clock. It adds diagnostic preconditioning; the subsequent 35/80/125-second frame
times and CPU intervals retain their original definitions.
