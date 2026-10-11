# Browser startup diagnostic preparation

This is a disabled diagnostic preparation for a **separate installed-image VM
boot after the final paired benchmark**. It does not change product code,
browser options, acceptance limits or the benchmark. There is no workflow or
activation marker and nothing is dispatched by these files.

## Finding from the existing diagnostic

The six old A2 paired boots reported a first mapped browser window after
45-second preconditioning of 1.098881139 seconds for baseline Zen and
1.362563450 seconds for candidate Epiphany: +23.995526%, above the unchanged
10% gate. These are quarantined-run diagnostics, not accepted benchmark proof.
One separate cold browser mapping bracket was 8.551 milliseconds, above the
unchanged 5-millisecond precision limit. The complete final image includes a
different SceneFX product patch, so its final paired run remains necessary.

The source-defined workload calls `epiphany --new-window` directly with a
loopback HTML page containing no external resources. Optimizing arctic-open,
GTK desktop launchers, shell IPC or app discovery would not explain this
workload. Each trial closes the new window before the next process launch.
The candidate already ships both GTK and wlr portal backends and GNOME Keyring
and sets Mango's portal preference to GTK for Settings/file dialogs and wlr for
screen capture. No concrete missing-service or launch-wrapper bug was found.

Reaching the 10% gate for the reported medians would require about 154
milliseconds of savings. Matching the baseline would require about 264
milliseconds. Source inspection does not establish that such savings exist.
No product optimization is proposed without an observed cause.

## Upstream source binding

Official GNOME Epiphany release **50.6**, matching the image's
`epiphany-runtime-1:50.6-1.fc44.x86_64`:

- Tag object: `288a17f15afc022a8abe84c905ed710951dce4c0`.
- Peeled commit: `6eaf573ea9838bcaeb33c52388d0b763373f012a`.
- Source: <https://github.com/GNOME/epiphany/tree/6eaf573ea9838bcaeb33c52388d0b763373f012a>.

The exact files fetched at the tag and peeled commit matched byte for byte:

| File | SHA-256 |
| --- | --- |
| src/ephy-main.c | fadff40557029628c2aed54ca7e1645c241a34795047f841564c6fd920dbaf94 |
| src/ephy-shell.c | a09768a74b4ef58a0b06cb7e9b63e9339488935bb5788374977e6e55ce4cf897 |
| embed/ephy-embed-shell.c | a8d58064d79af58a710a730ba095c4800d80e543fff43819d2e620d4272a4ab1 |
| embed/ephy-embed-prefs.c | 8a268918818b9beab5337c36f77584ef957830ba598b991422afb242fff0e7df |

The normal browser path runs profile migration before `g_application_run`.
Application startup then initializes GTK/libadwaita, WebKit context and network
session, password handling, history/session services and asynchronous session
resume before opening the requested window. `ephy-shell.c`'s `portal_check`
checks a **captive network portal**, not an xdg permission/settings portal.
Fedora downstream patch identity was not inspected, so these source paths are
potential phase explanations, not proofs of the exact installed machine code.

## Diagnostic design

`profile.py` registers uprobes and return probes on existing exported x86_64
functions in verified installed GLib, GTK4, libadwaita, WebKitGTK and libsecret
ELFs. It resolves real dynamic-symbol offsets from those full files and records
their actual SHA-256, bytes, exact RPM owner and offset. Missing exports are
reported; no offset or replacement function is guessed.

A stopped desktop-owned helper establishes the original process before exec.
The private tracing instance's PID filter and event-fork option limit collection
to that process and its descendants/threads. Timing starts immediately before
resuming it to exec the normal browser. This excludes the Python/runuser setup
and therefore **cannot substitute for the paired launch timing**. The existing
audited Mango managed-list insertion observer supplies the actual mapped-window
bracket using CLOCK_MONOTONIC_RAW. It still requires an explicitly admitted,
independently reviewed exact final Mango ELF profile.

RPM verification, full ELF hashing and symbol resolution read application
libraries before launch. They can warm storage caches; this preparation makes
no cold-cache or pristine-first-use timing claim.

The helper's one numeric PID line is flushed before its stdout is redirected
to `/dev/null`; the browser receives `/dev/null` for stdin/stdout/stderr. Browser
output cannot fill an unread handshake pipe. The wrapper is created in a new
owned POSIX session under cancellation deferral. Before closing the new UI,
the collector binds the live process tree and same-session processes by PID,
UID and start ticks, then resumes/stops only those still-matching generations
and verifies their exit and wrapper reaping. This extra process isolation is
another diagnostic condition, not a paired benchmark condition. Completely
detached descendants which have left both the current tree and session before
the census are not proven by that census; the host must terminate the owned
disposable VM after collection.

The diagnostic opens the same loopback workload, retains a 45-second
preconditioning window, then collects three repeated launches with five-second
persistence checks. It changes no browser preference, renderer, service,
sandbox, security policy, accessibility support or scheduler setting; it never
flushes caches or preloads application files. SELinux must remain Enforcing.
Uprobe and observer work remains in the diagnostic's elapsed times.

Only finite phase names, identifier classifications, numeric timestamps,
durations, PIDs, hashes and package/source bindings enter the report. Kernel
string fields are limited to DBus service/interface/method identifiers. They
are grammar checked in memory and reduced to explicit known enums or
`other_identifier`; no raw trace, DBus body, URL, title, text, microphone input
or transcript is saved or echoed. Invalid records fail with a fixed label.
The report is created under `/run/arctic-browser-startup/` with directory mode
0700 and file mode 0600. Original helpers' arbitrary exception text is not
printed by the collector.

Synchronous call entry/return spans can expose actual blocked intervals. Async
DBus/secret-service calls expose dispatch points only. These probes do not
attribute every static Epiphany function, asynchronous callback, shader
compilation or first content paint. Nested durations are not additive budgets.
Missing optional exports are reported. An unmatched return, event loss or
failed owned cleanup fails collection. Entry-only spans are explicitly
incomplete and never receive a completed latency; `g_application_run` normally
remains incomplete because tracing stops before closing the observed window.

## Future hosted execution

Root must first complete the final paired run. If a browser regression remains,
prepare and independently review a **separate diagnostic branch/workflow**
binding the full authenticated ten-field final image tuple, exact helper and
collector bytes and the same image's exact RPM NEVRAs. The host must verify the
whole ISO size and SHA-256 before booting it. The guest context alone is not
proof that the host used that ISO.

Copy reviewed `profile.py`, `guest.py`, `causal.py` and the ready context into
root-owned `/run/t`. The causal module must contain the exact reviewed final
Mango ELF profile, with separately pinned bytes if observer preparation changes.
Run `python3 /run/t/profile.py` in the original installed desktop session.
No additional Epiphany option or environment override is required. In
particular, no sandbox-disable, private-instance, renderer, portal or logging
flag is allowed by this diagnostic. Keep all output private until the unchanged
privacy scanner accepts the whole report. Shut down the owned VM afterwards;
do not resume benchmark acceptance from this instrumented boot or disk state.

`execution-context.json` remains `ready: false` and `image: null`. It is not an
execution request. There has been no VM execution or measurement from this
preparation.

## Distinguishing causes

- A long `profile_helper_spawn` span before application startup would justify
  investigating profile migration and the actual spawned helper, preserving
  all required migrations and user data.
- A long synchronous portal/secret-service call, classified by known destination
  and interface, would justify investigating real service readiness and DBus
  activation. It does not justify disabling portals, keyring or accessibility.
- A long GTK/libadwaita initialization or WebKit context/network-session span
  would identify the runtime region to profile further, including actual CPU
  and graphics backend evidence. It does not justify forcing a renderer or
  dropping GPU/media support from source reasoning alone.
- If exported calls finish quickly but the actual managed map is late, inspect
  asynchronous session restore, WebKit child startup and the original mapping
  path. These probes alone cannot identify which is responsible.

After any evidence-grounded product fix, independently review it, build a new
image, and repeat the entire unchanged final qualification. A diagnostic
improvement or a passing regression gate alone is not proof of optimization.
