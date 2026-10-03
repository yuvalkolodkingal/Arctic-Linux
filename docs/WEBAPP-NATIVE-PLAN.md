# Arctic web app native experience plan

This plan covers the six requested areas: window behavior, chrome, files, notifications,
background operation, and media. All six are required scope. WhatsApp Web is the first
complete application workflow; the compatibility matrix below remains part of delivery.

Status: implementation plan, based on source inspection on 2026-10-03. See the
[verification report](WEBAPP-COMPATIBILITY.md) for delivered behavior, automated evidence and
remaining acceptance work. Account-based application tests were deferred by the user. Acceptance criteria below are targets,
not claims that the current engine passes. Runtime limitations must be measured against
the packages actually shipped by Arctic.

## Existing foundation

Keep the Go manager and policy packages, isolated profiles, GTK4 host, and small cgo
boundary. Extend them in reviewable changes rather than replacing working profile and
installation code. Preserve existing app IDs, desktop entries, sign-ins and permissions.

| Area | Observed source | Work required |
|---|---|---|
| Window | `internal/webkit/shim.c`, `cmd/arctic-webapp-host/controller.go`: GTK app identity, saved dimensions and maximize state, activation, fullscreen hooks | Verify compositor behavior; preserve normal dimensions across tiling/fullscreen; cover mixed scale displays |
| Chrome | `internal/webkit/shim.c`, `internal/webapp/theme/`: GTK header, menu, fixed navigation buttons, theme updates | Compact header and contextual controls; accessibility and visual acceptance |
| Files | Controller chooses Downloads destination; shim sends completion/failure notifications and offers Open/Show in folder | Asynchronous save selection, progress/cancel UI, upload/clipboard/drop verification |
| Notifications | Shim forwards WebKit notifications through GNotification and invokes WebKit click callbacks | Verify conversation activation and DND; handle hidden windows and stale actions |
| Background | `close_request_cb` saves state and allows destruction; options lack background/autostart settings | Explicit lifecycle, separate Quit, startup integration and cleanup |
| Media | Permission callbacks and audio mute button; `shell/MediaService.qml` already consumes MPRIS | Runtime capability probes, screen sharing verification and per-app media service |

The older [0.3 engine plan](plan-0.3/02-webapp-engine.md) contains historical statements
such as “Nothing web-app related exists.” Use current source as the implementation baseline.
This document proposes extending its scope; it does not rewrite historical release claims.

## Runtime decision before implementation

Run the priority workflows on the shipped WebKitGTK build and one installed Chromium-family
runtime. Record WebRTC, codecs, screen capture, Media Session, notifications and DRM separately.
The existing documentation describes Fedora WebKitGTK WebRTC/DRM limitations; those statements
are inputs to verification, not substitutes for measurements.

Prefer the existing GTK host when it meets the workflow. External Chromium app mode remains
a compatibility option, but does not provide the same native GTK chrome or host callbacks.
Track native integration and website functionality as separate scores for each runtime.
Do not mark the six-area native experience complete merely because a website works in Chrome.

If priority workflows require Chromium and the external window cannot meet the native
requirements, produce an embedded Chromium feasibility prototype before committing to it.
Measure Wayland embedding, sandboxing, distribution size, update ownership, media support
and integration cost. This is a decision gate, not a promise to ship a second embedded engine.

Replace silent fallback after a runtime disappears with an actionable runtime selection
screen. Explain that switching runtimes may require signing in again. Never copy cookie
databases between engines or erase the previous profile during the switch.

## Window behavior

Use the app ID consistently for GtkApplication, Wayland identity, desktop entry and icon.
Keep page titles useful without losing the installed app identity. Launching again presents
the existing app, including when hidden, and forwards an authorized deep link once.

Save normal logical width/height and maximize state. Do not overwrite normal dimensions
with tiled or fullscreen allocation. Wayland owns placement: do not promise restoration of
absolute coordinates or force a workspace against compositor policy. Clamp restored size
to the available display. Fullscreen returns to the preceding state and restores the header.

Acceptance:

- Launcher, task switcher and notification use the correct app icon, including two accounts.
- Ten launches produce one main window and preserve the primary instance record.
- Floating, tiled, maximized and fullscreen transitions restore usable dimensions.
- Moving between 100%, 125%, 150% and 200% displays preserves sharp chrome and input alignment.
- Monitor removal, restart and suspend/resume leave an accessible window.
- Activation from a launcher or notification follows Wayland activation rules.

## Chrome and navigation

Use a compact Arctic header with app identity and one menu. Show Back when history makes
it useful; put Forward and Reload in the menu, retaining shortcuts. Show loading progress
without permanently occupying a browser toolbar. Keep download/media indicators contextual.
Show the real origin during authentication or out-of-scope navigation and retain Return to
app. Permission and security prompts stay outside website content.

The menu exposes Find, zoom, Reload, Open in browser, Copy address, Downloads, app settings,
fullscreen and Quit. Close window remains distinct from Quit. Adopt Arctic design tokens
and existing GTK theme infrastructure; do not recolor entire websites with generic CSS.

Acceptance: Winter/Polar night switches live without a white flash; narrow tiles remain
usable; keyboard focus and accessible labels cover every action; Hebrew/Arabic RTL and IME
input work. Existing authentication/pop-up rules must remain correct after chrome changes.

## Files and downloads

Use GTK native dialogs and the desktop portal where supported/configured. Verify WebKit's
default upload picker before replacing it. Add “Ask where to save” while retaining the
existing Downloads behavior for migrated apps. Support multi-file selection and cancellation.

The current synchronous `DownloadDestination` callback cannot wait for an asynchronous
dialog. Introduce a download ID and pending destination completion path in the shim/Go
boundary. Retain native objects until completion or cancellation, and release them on every
terminal path. Never block the GTK main loop or write bytes before destination selection.

Add a compact downloads view with progress, indeterminate progress, cancel, failure/retry
where supported, Open and Show in folder. Keep safe filenames; prevent races from replacing
an existing file. Explicitly confirm intentional overwrite in the save dialog. Clean partial
files owned by the failed/cancelled transfer without deleting unrelated files.

Acceptance: upload a photo and multiple files; paste a screenshot; drag files from Thunar;
download duplicate filenames; cancel selection and transfer; interrupt the network; simulate
disk full; reveal the completed file. Include Unicode names, blob downloads, and concurrent
downloads. Verify clipboard behavior through actual user gestures.

## Notifications

Retain the desktop notification service as owner of DND, history and app rules. Supply the
installed app identity, icon and appropriate replacement identifiers. Honor live changes to
the engine's notification setting as well as desktop suppression rules.

Clicking presents the existing view and invokes the website's notification action so the
site can open its conversation. Test that exact conversation; presenting the app alone is
not enough. Never invent a deep link by scraping notification text. Expired native notification
objects must not be dereferenced. After a crash/restart, restore a specific target only when
the runtime/site supplies a valid durable action; otherwise open the app safely and classify
the lost targeting as a limitation. Do not claim universal cold-start conversation routing.

Acceptance: two conversations, two accounts, notification replacement, click while visible
and hidden, DND on/off, blocked permissions, logout and stale clicks after process restart.
Test the installed Arctic notification service, not only a mocked D-Bus endpoint.

## Background operation and startup

Add separate per-app settings for “Keep running when closed” and “Start at login”, both off
by default, including for existing apps. When both are enabled, login starts hidden; when
only startup is enabled, login opens the window. Expose these in WebApps settings and keep
startup state consistent with the existing Startup apps page and XDG autostart entries.

Model lifecycle explicitly as stopped, visible, hidden and quitting. With keep-running off,
Close quits as today. With it on, Close saves geometry and hides the window while retaining
its WebView/session and a balanced GApplication hold. Verify timers, connections and message
delivery in a hidden WebView; process survival alone does not establish background support.

Launcher activation and notification activation restore the same window. Quit always exits,
releases application holds, stops capture/media and cleans process state. Do not add automatic
restart after explicit Quit. Disabling keep-running while hidden exits cleanly. App removal
stops hidden instances and removes startup entries even when sign-in data is retained.

Make background apps discoverable in settings with Open and Quit actions. Do not require a
tray icon for lifecycle control. Clearly explain that closing may continue active media or
capture; preserve desktop privacy indicators and an accessible stop action.

Acceptance: visible → close → hidden → message → notification click → visible → Quit;
repeat ten times without leaked windows/holds. Test login, settings changes, removal,
network loss, sleep/wake and logout. Observe message delivery for 30 minutes while hidden.
Notifications after full process exit are a separate push capability, not promised here.

## Media and desktop integration

Probe camera/microphone and screen capture on the actual shipped build. A permission prompt
does not prove capture support. On supported runtimes, exercise PipeWire and the configured
screen-cast portal end to end: select a source, see remote output, stop sharing, revoke access.
Test microphone and camera independently and together, device removal and output switching.

Expose one MPRIS player per app instance when media is available. First inspect whether the
runtime already exports it; avoid duplicate players. Advertise only supported actions and
accurate metadata. Prefer supported runtime APIs; prototype Media Session integration if
required. A page bridge, if unavoidable, must be narrow, origin-checked, navigation-scoped
and unable to execute arbitrary native commands. Site adapters need independent regression
coverage and must fail safely when a site changes.

Keep Go standard-library-only and confine native integration to the GTK/GLib boundary.
GLib GDBus can export MPRIS without adding a Go D-Bus dependency. Use the existing shell
MPRIS service and playerctl selection policy. Support play/pause and metadata first, then
seek/next/previous only when the media source supports them. Unregister on exit and reflect
logout/navigation. Calls must not be treated as music players by default.

Acceptance: YouTube/YouTube Music playback and hardware keys; two simultaneous media apps;
metadata changes; hidden playback; seeking when available; no stale player after Quit.
For Meet/Teams/Discord, verify two-party audio/video and screen share when supported by
both service and runtime. Record DRM support separately for Spotify.

## Common application acceptance matrix

This is a practical coverage shortlist, not a measured popularity ranking. All rows start
untested. Each workflow gets its own result; a working landing page is not an app pass.

| Order | Applications | Required workflows |
|---|---|---|
| 1 | WhatsApp Web | QR pairing, persistent session, send/receive, photo/file upload and download, screenshot paste, voice note, notifications opening the right chat, hidden delivery, reconnect, restart |
| 2 | Gmail, Outlook | Login/MFA, compose, attachments, save/download, mailto, notifications, independent second account |
| 2 | Telegram Web, Discord | Login, messaging, files, notifications, hidden delivery; calls when offered |
| 3 | Slack, Teams, Google Meet | Authentication, messaging where applicable, device permissions, calls, screen sharing |
| 3 | Google Docs/Drive, Notion | Editing, shortcuts, clipboard, file picker/drop, export/download, print |
| 3 | YouTube, YouTube Music, Spotify | Playback, background media, MPRIS/keys, metadata, codec/DRM behavior |
| 4 | ChatGPT, GitHub, Home Assistant | Login, streaming/updates, uploads, external links, local-network connections |

For WhatsApp calls, first establish whether the service exposes calling to the tested account
and browser. Use a working regular-browser baseline to separate service restrictions from
runtime and Arctic failures. Use dedicated accounts and controlled test recipients. Account
owners handle QR pairing and MFA; do not place session credentials or message content in CI
artifacts. Do not send test messages to unrelated contacts.

## Test execution and evidence

1. Extend pure-Go tests for migration, lifecycle policy, permission policy, destination safety
   and startup cleanup. Add native-host fixtures for notification actions, downloads, media,
   authentication redirects and hidden operation. Exercise the shipped WebKitGTK host;
   Playwright's bundled WebKit is not an equivalent runtime.
2. Extend `cmd/arctic-webapp-host/dev/smoke.sh` and the existing `go-webkit` CI job. Keep
   deterministic fixtures independent of commercial sites and account login. The current
   container smoke disables the WebKit sandbox; it cannot certify production sandbox behavior.
3. Run packaged tests in Fedora + Mango with sandbox enabled and actual portals. Include
   Intel/AMD/NVIDIA where hardware is available, mixed-scale displays, monitor hotplug and
   suspend/resume. Missing hardware coverage stays explicitly untested.
4. Run live acceptance separately, using supported automation where available and a manual
   checklist for QR/MFA, hardware keys, calls and screen sharing. Capture sanitized evidence.

Record app/workflow, result (pass, fail, blocked, not offered, untested), date, commit,
runtime/package versions, desktop/GPU, account prerequisites, reproduction steps, expected
and observed behavior, screenshot/log references and issue. Classify failures as Arctic,
runtime, service, or environment. Never convert blocked/untested into a pass.

Measure cold/warm time to an interactive window, whole-process-tree memory, idle CPU,
notification delay and background resource use on the same machine/profile before and after.
Proposed investigation thresholds: more than 10% slower median launch or 15% more idle memory
over five comparable runs. Investigate noise and explain accepted tradeoffs. Hidden app
resource use is reported separately from a fully exited baseline.

## Implementation sequence and release gates

| Change | Main code surfaces | Exit evidence |
|---|---|---|
| 1. Baseline and capability probes | Existing smoke fixtures, compatibility data, packaged test harness | WhatsApp/Gmail/Discord and media baseline; runtime decision documented |
| 2. Settings and lifecycle | `internal/webapp/app.go`, `manage/`, API, host controller, shim, `settings/pages/WebAppsPage.qml`, startup integration | Existing records migrate safely; Close/Hide/Open/Quit/startup/remove tests pass |
| 3. Native window and chrome | Shim, theme package, saved state policy | Identity, contextual header, geometry, scaling, fullscreen and keyboard checks pass |
| 4. Files | Shim callbacks/exports, download policy, downloads UI | Native dialog, progress, cancellation, clipboard/drop and failure cases pass |
| 5. Notifications | Shim and controller, existing shell notification integration | WhatsApp hidden message opens correct chat; DND and stale actions pass |
| 6. Media | Capability layer, shim/GDBus, narrow runtime integration | MPRIS and keys pass; verified call/share results for supported configurations |
| 7. Compatibility and release | Full matrix, packaging/CI, wiki and build contract | All priority workflows have evidence; upgrade/rollback and production sandbox verified |

Complete one WhatsApp journey across changes 2–5 before broad site-specific work. All six
native areas stay in scope. A blocked capability requires an explicit runtime/design decision,
not silent removal of the requirement. Do not label a runtime fully native while required
integration remains absent; publish exact supported combinations and outstanding blockers.

Keep configuration additions backward-compatible where practical; version incompatible
changes and retain a migration backup. Test old-profile upgrade and rollback without profile
loss, including startup entries and hidden processes. Update `docs/BUILD-SPEC.md`, CLI help,
settings copy and `docs/wiki/Web-Apps.md` alongside implementation, describing only verified
behavior. This planning change itself does not alter current application behavior.
