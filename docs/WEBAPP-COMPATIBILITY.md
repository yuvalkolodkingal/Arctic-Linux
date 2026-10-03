# Native web app verification

The native integration changes were exercised on Fedora 44 with GTK 4.22.5 and WebKitGTK
2.54.0 in a headless Sway session on 2026-10-03. This verifies the shipped GTK host against
local fixtures. It does not certify third-party applications or a physical Arctic desktop.
The user explicitly deferred account-based acceptance tests.

## Arctic Linux 1.1 verification

The native page now follows light → dark → light live through `prefers-color-scheme`,
without navigation or reload, as does a real Chromium 154 app window using Arctic's GTK
Settings portal preference. The Chromium fixture also delivered a real WebRTC data channel,
audio RTP and decoded video between two local peers. These generated-media loopback checks
do not certify physical capture or an authenticated WhatsApp call.

Chromium is a required dependency of arctic-webapps. WhatsApp Web previews recommend an
available Chromium-family runtime; both Get apps and terminal installs honor that choice.
Existing apps can change engines in Settings without deleting their original profile.

## Verified behavior

| Area | Evidence and result |
|---|---|
| Identity and activation | Native smoke checks Wayland app ID, title, favicon upgrade, single window and stable primary PID |
| Chrome and theme | Light/dark screenshots; compact contextual navigation, keyboard fullscreen, and a 125% output-scale transition |
| State | Shutdown/restart persists state; regression test rejects non-finite zoom and retains normal dimensions while maximized |
| Upload | Native multi-select-capable GTK chooser selects a local file and delivers it to a WebKit file input |
| Save | Native asynchronous chooser saves the exact expected bytes; cancelled selection does not complete the download |
| Downloads | Successful and interrupted transfers are distinguished; progress, Cancel, Dismiss, Open and Show in folder are implemented |
| Image paste | A PNG on the Wayland clipboard is pasted as an image into editable page content; see the event limitation below |
| Notifications | Test notification daemon receives the app identity; clicking a notification restores the hidden view and invokes the page's conversation handler |
| Background | Close hides without exiting, activation restores the same instance, hidden startup stays hidden, disabling background stops a hidden process, and Quit/SIGTERM stop the app |
| Startup and migration | Go tests cover absent-field defaults, explicit enable, external Hidden=true, repair/rename preservation and removal while keeping profile data |
| Media | Actual WebKit audio fixture exposes MPRIS metadata; playerctl play, pause, seek and volume work; navigation removes the player |
| Permissions | Stored notification grants cannot override Block; screen sharing asks again; combined camera/microphone requests check both permissions |
| Runtime selection | Missing browser returns an actionable error and preserves its profile instead of silently switching engines |

The native smoke writes window, chooser, clipboard and scaled-window screenshots, capability
results, clipboard observations, and saved-state evidence to its `--out` directory. Its
notification service is a fixture, so these results do not establish Arctic DND or notification
history behavior.

## Runtime findings and limits

The capability probe returned `RTCPeerConnection=undefined`, while `getUserMedia` and
`getDisplayMedia` are functions and Media Session is present. API presence is not proof of
successful capture. Calls cannot be certified on this WebKitGTK build; keep the existing
Chromium-family option for applications that require WebRTC or DRM. That option has its own
browser chrome and does not gain the GTK host's native integrations from this change.

In the paste fixture, WebKit inserted an image into contenteditable, but the synchronous
paste event exposed an empty DataTransfer file list. Applications that require a File in that
event need their own live compatibility test. No synthetic paste event or blanket clipboard
permission was added to hide this distinction.

MPRIS currently controls ordinary main-page HTML audio/video, excluding srcObject call streams.
Cross-origin embedded players and site-specific next/previous actions are not supported.
Save dialogs deliberately require a new filename; existing files are never overwritten.
Notification conversation targeting depends on the site's live notification callback. Durable
conversation routing after a full process exit and push delivery while fully quit are not
implemented.

## Application acceptance matrix

All authenticated workflows below are pending by user choice. Loading a login page would not
establish messaging, editing, playback, notification or calling compatibility.

| Applications | Pending workflows |
|---|---|
| WhatsApp Web | QR pairing, session retention, send/receive, attachments, screenshot paste, voice notes, notification conversation routing, hidden delivery, reconnect |
| Telegram Web, Discord | Login, messaging, files, notifications, background delivery; calls where the service offers them |
| Gmail, Outlook | Login/MFA, compose, attachments, mailto, notifications and independent accounts |
| Slack, Teams, Google Meet | Login, messaging where applicable, microphone/camera, two-party calls and screen sharing |
| Google Docs/Drive, Notion | Editing, shortcuts, clipboard, uploads, export and printing |
| YouTube, YouTube Music, Spotify | Site playback, MPRIS behavior, metadata, media keys, codecs and DRM |
| ChatGPT, GitHub, Home Assistant | Login, updates/streaming, uploads, external links and local-network connections |

Use dedicated accounts and controlled recipients. Record app, workflow, commit, runtime,
desktop/GPU, date, result, reproduction and sanitized evidence. Classify a failure as Arctic,
runtime, service or environment. Do not mark blocked or untested workflows as passing.

## Checks still requiring a desktop or hardware

- Fedora + Mango with the production sandbox enabled. The container smoke disables WebKit's
  sandbox, as the existing test did; production launch still removes that override.
- Arctic's real notification daemon, DND/history and notification activation under its policy.
- Functional portal-backed capture and file sharing. The container lacks the document FUSE
  mount and a fully configured desktop portal session; chooser tests exercise GTK's fallback.
- Physical camera/microphone, screen-share source selection, device removal and privacy UI.
- Cross-application drag/drop, multiple-file selection, IME, RTL and screen-reader acceptance.
- Mixed-DPI monitors, hotplug, suspend/resume and Intel/AMD/NVIDIA rendering.
- Thirty-minute hidden messaging delivery and resource use on a target machine.
- Comparable baseline startup/CPU/process-tree memory benchmarks and an installed RPM
  upgrade/rollback exercise. No performance improvement or binary rollback claim is made.

## Reproducing automated verification

```sh
CGO_ENABLED=0 GOPROXY=off go test ./...
CGO_ENABLED=1 GOPROXY=off go vet -tags webkit ./...
CGO_ENABLED=1 GOPROXY=off go test -tags webkit ./internal/webapp/... ./internal/webkit/... ./cmd/arctic-webapp/... ./cmd/arctic-webapp-host/...
cmd/arctic-webapp-host/dev/smoke.sh --out /tmp/webapp-native-results
cmd/arctic-webapp-host/dev/chromium-smoke.sh --out /tmp/webapp-chromium-results
shellcheck cmd/arctic-webapp-host/dev/smoke.sh
qmllint -I settings settings/pages/WebAppsPage.qml
python3 -m unittest discover -s settings/tests -p test_webapps.py
```

The existing `go-webkit` CI job installs the added fixture/input tools: python3-gobject,
playerctl, wtype and wl-clipboard. The Go manager keeps its standard-library-only build.
