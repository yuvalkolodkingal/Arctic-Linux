# Arctic Linux 0.3 — plan

This plan covers the 0.3.0 release: **Get apps** that opens to a choice of sources, a **web app
engine written in Go**, **Arctic menus for every bar item**, **Remove apps**, the **screenshot and
browser shortcuts**, and the desktop features that research into Omarchy, the Quickshell shells
and the mainstream desktops showed Arctic is missing. It was written on 2026-09-28 against the
0.2.1 tree (`51cce98`), so every `file:line` reference points at 0.2.1.

This file is the overview: scope, decisions, architecture, keys, packaging, tests, how the work
is split, rollout and risks. The detail — current state with line references, the design,
file-by-file changes, data formats, tests and open issues — is in one file per area under
[`plan-0.3/`](plan-0.3/). As in [PLAN.md](PLAN.md), facts marked ✅ were checked against a
primary source; facts marked 🔍 are unverified and name what must prove them.

---

## 1. Scope

| # | Request (as asked) | Where it is planned |
|---|---|---|
| 1 | "the get apps opens to multiple options, flatpak, dnf, and web app" | [01-get-remove-apps.md](plan-0.3/01-get-remove-apps.md) |
| 2 | "we code a custom engine in go to make any website into a web app" | [02-webapp-engine.md](plan-0.3/02-webapp-engine.md) |
| 3 | "all dropdowns are customized (wifi, bluetooth, etc)" | [03-bar-menus.md](plan-0.3/03-bar-menus.md) |
| 4 | "a remove apps option with other options flatpak webapp etc" | [01-get-remove-apps.md](plan-0.3/01-get-remove-apps.md) §2–§7 |
| 5 | "add a screenshot shortcut and change the browser shortcut to win b" | [04-shortcuts-capture.md](plan-0.3/04-shortcuts-capture.md) §3–§5 |
| 6 | "research all useful desktop and omarchy features we need to add" | [05-system.md](plan-0.3/05-system.md), [06-experience.md](plan-0.3/06-experience.md), the capture/input parts of 04, and the matrix in [07-feature-matrix.md](plan-0.3/07-feature-matrix.md) |

The research behind request 6 inventoried Omarchy (its source tree, menu, 469 `omarchy-*`
commands and default bindings), four Quickshell shells (DankMaterialShell, Noctalia, Caelestia,
end-4's illogical-impulse), GNOME, KDE Plasma, COSMIC, macOS and Windows, and what Arctic 0.2.1
already has. It produced 61 prioritised gaps (P0/P1/P2/skip), each checked twice: against the
repository (is it really missing, does its key clash?) and against outside sources (does the
Fedora 44 package exist under that name, does the tool work on a wlroots compositor?). Those
corrections are applied throughout; the matrix lists every feature considered and its fate.

## 2. Decisions

| # | Decision |
|---|---|
| D1 | This work ships as **Arctic Linux 0.3.0**. |
| D2 | **Get apps opens to a chooser** in the launcher: Flathub apps (Flatpak), Fedora packages (dnf), Web apps, Terminal apps, Remove apps and Console (the 0.2 PTY terminal, kept for people who type commands). Each source has its own search and install page with real metadata from local AppStream. Privileges don't change: dnf runs as `pkexec /usr/bin/dnf5` under `org.arcticlinux.pkexec.dnf`; Flatpak installs system-wide for wheel users without a password. |
| D3 | **Remove apps** has a tab per source and lists only apps people use (they have a desktop entry). Protected packages (the desktop itself, the shell, the kernel, dnf…) can't be removed. A dnf removal first shows every package it would take with it and asks. Delete on an app row in the launcher does the same (Omarchy's model). |
| D4 | **The web app engine is a split design**: `arctic-webapp`, a manager in pure Go (standard library, `CGO_ENABLED=0`) that finds a site's name, icons and scope, keeps the registry, writes desktop entries and speaks JSON to the shell; `arctic-webapp-host`, a window on WebKitGTK 6.0 and GTK 4 through a small hand-written cgo shim (every file `//go:build cgo && webkit`, in `/usr/libexec/arctic`); and, per app, a Chromium-family `--app` runtime for the sites WebKitGTK can't run (DRM video, some video calls). New subpackage `arctic-webapps`. |
| D5 | **Every bar item opens an Arctic menu** — network and Wi-Fi, Bluetooth, sound, notifications, calendar (clock), battery and power, media, display brightness, keyboard layout — and tray icons' menus are drawn in QML instead of Qt's stock menu. **Quick Settings** (`Super + A`) gathers the same panels. It all works on Fedora 44's Quickshell (the 0.2.1 snapshot `dacfa9d`): Wi-Fi through an `nmcli` helper that never puts a password on a command line, Bluetooth pairing through a small BlueZ agent. nm-connection-editor, blueman and pavucontrol stay installed behind "More settings…" and for the waybar session. Packaging Quickshell 0.3.1 ourselves is deferred (§11). |
| D6 | **The shell is the notification server** in its own session: toasts, a notification centre on the bell, do not disturb with durations and a schedule. mako stays for the waybar session. |
| D7 | **Keys**: the browser moves to `Super + B`; `Super + W` is left free; `Super + Shift + S` takes an area screenshot (Print, Shift + Print and Super + Print stay). Screenshot notifications get actions. Settings flags your own shortcuts that one of Arctic's shadows. Every new key is checked against every existing bind and against the Alt + Shift layout switch. |
| D8 | From the research: all P0 and P1 gaps are planned, and the P2 ones unless §11 defers them with a reason. Every correction from the verification passes is applied. |
| D9 | Design system: colours only from tokens; amber means "here" — focus, selection, the current thing — and is never decoration or a category colour. New icons follow the line style of `shell/assets/design-data.js`. |
| D10 | Go stays standard-library only. Only `arctic-webapp-host` uses cgo. |
| D11 | Every helper that Settings or the shell calls prints one JSON line: `{"ok": true, …}` or `{"ok": false, "error": "a sentence", …}` (what `settings/Backend.qml` expects), snake_case keys. |
| D12 | The work reaches `main` through a pull request, merged only when CI is green: every push to `main` publishes packages to every installed stable system. |

## 3. Architecture

```
                         Quickshell session (arctic-shell)
 ┌──────────────────────────────────────────────────────────────────────────────┐
 │ Bar ── BarMenu panels: network · bluetooth · sound · notifications · calendar │
 │        battery · media · display · keyboard · tray   ── Quick Settings (Super+A)│
 │ Launcher ── Get apps: chooser → Flathub · Fedora · Web apps · Terminal apps    │
 │             · Remove apps · Console        ── command menu (Super+Alt+Space)   │
 │ NotificationService (org.freedesktop.Notifications) · toasts · centre · DND    │
 │ Capture overlay · emoji · clipboard · OSD · lock screen · polkit dialog        │
 └───────┬──────────────────────┬──────────────────────┬───────────────┬─────────┘
         │ JSON lines           │ JSON lines           │ D-Bus          │ IPC
         ▼                      ▼                      ▼                ▼
  shell/scripts/*.py     arctic-webapp serve     BlueZ · UPower ·   arctic-shell-ipc
  network.py (nmcli)     (pure Go manager)       PowerProfiles ·    ← Mango binds,
  bt-agent.py (Agent1)        │                  PipeWire · MPRIS   arctic-* helpers
  apps.py / appslib.py        │ run
  install-terminal.py (PTY)   ▼
  keyboard.py · audio.py  arctic-webapp-host (cgo: GTK 4 + WebKitGTK 6.0, one app window)
         │                or a Chromium-family --app window (per-app fallback)
         ▼
  pkexec /usr/bin/dnf5 · flatpak · nmcli · wpctl · mmsg · grim · wf-recorder · tesseract …
```

The shell draws everything; helpers do the system work and speak JSON; nothing privileged runs
in the shell. Settings (`arctic-settings`) reaches the same helpers through
`settings/scripts/arctic_settings.py`.

## 4. The areas

**01 — Get apps and Remove apps** ([file](plan-0.3/01-get-remove-apps.md)). A router in
`shell/getapps/` replaces the single console view: a chooser of six cards, then per-source pages
(search with AppStream metadata, an app sheet, install), a Remove apps page with a tab per source,
and the old console moved as `ConsolePage.qml`. `AppsService.qml` owns every process: the PTY
runner (now also running structured jobs whose argv is built and validated in
`shell/scripts/appslib.py`), the package index (now with summaries), the new `apps.py` helper
(sources, catalogs, installed lists, remove previews, owner resolution) and `arctic-webapp serve`.
Jobs keep running when the launcher closes and report through a notification. dnf removals are
previewed unprivileged (`dnf5 remove --store`) and run with the same arguments under pkexec.
Protection is a pattern list (`protected-packages.conf`, extendable in
`/etc/arctic/protected-packages.d`), enforced in the list, the preview, the runner and the console.
Esc goes back one step at a time.

**02 — Web app engine** ([file](plan-0.3/02-webapp-engine.md)). `cmd/arctic-webapp` +
`internal/webapp/…` (registry, ids, desktop entries, discovery, Public Suffix List scope, icons,
manage operations, the `serve` protocol) and `cmd/arctic-webapp-host` + `internal/webkit` (the cgo
shim). Discovery fetches only http(s), with limits and a private-address guard, parses the page
with a small stdlib tokenizer, reads the Web App Manifest, and falls back to touch icons, favicons
and a token-coloured monogram. The window keeps its own profile, sends out-of-scope link clicks to
your browser (Epiphany's rule: redirects and form posts stay, so sign-in works), handles OAuth
pop-ups, notifications, downloads, zoom and find, and follows the Arctic theme. Each app has its
own Wayland app id (`org.arcticlinux.WebApp.<id>`), so the launcher and Mango match its icon.
Milestones M0–M8; the one-line `--json` shape and the `serve` contract are fixed first because
Get apps and Settings are written against them.

**03 — Bar menus and Quick Settings** ([file](plan-0.3/03-bar-menus.md)). One `BarMenu` popover
hosts every panel, built from a shared toolkit (rows, switch rows, sliders, sections, pages,
fields, spinner, signal icon; about 24 new icons). Wi-Fi scans, joins (hidden networks, 802.1X,
VPN/WireGuard, share as QR), forgets and switches radios through `network.py`: a profile is added
without its secret and brought up with `passwd-file` on a pipe, so the password never reaches an
argv. Bluetooth scans, pairs, connects and forgets; `bt-agent.py` registers the default BlueZ agent
and the shell asks "Does 123456 match?". Sound picks outputs and inputs and sets per-app volume.
Battery shows health, the power mode (PowerProfiles on D-Bus — tuned-ppd has no
`powerprofilesctl`), a charge limit and low-battery warnings. Calendar, media (MPRIS), display
brightness (backlight and DDC) and the keyboard layout chip complete it. Quick Settings reuses the
panels as sub-pages over a toggle registry that also feeds IPC and the bar's mode and privacy
indicators.

**04 — Shortcuts and capture** ([file](plan-0.3/04-shortcuts-capture.md)). The browser moves to
`Super + B` (`dotfiles/.config/mango/arctic/apps.conf:7`, `arctic_settings.py:1793`, `keys.txt`,
eight wiki pages); `Super + W` is freed. `Super + Shift + S` takes an area screenshot. Capture gets
a frozen-screen overlay in the shell with pixel-exact crops, notification actions (Open, Edit,
Show in Files), text and QR recognition, a colour picker, screen recording with a bar indicator
and a screen-share picker for xdg-desktop-portal-wlr. Input gets an emoji picker, a clipboard
panel, hardware keys, Mango's Alt + Tab switcher, jump labels, a scratch workspace and a drop-down
terminal. §3 is **the authoritative table of every new or changed key**. Settings flags your own
binds that Arctic's shadow, and refuses layout-switch chords that would eat Alt + Shift shortcuts.

**05 — System, power, hardware and network** ([file](plan-0.3/05-system.md)). Night light with a
schedule, keep awake, XDG autostart (a `Wants=` drop-in on `mango-session.target`), printing and
scanning, removable drives and phones in the file manager (gvfs backends), a date, time and
language page, Flatpak and firmware updates next to dnf, dim-before-lock, lid and clamshell through
Mango's `switchbind`, display modes on `Super + P`, lighter effects in VMs, game mode, GPU choice on
hybrid laptops, a Users page (avatar, fingerprint, security keys), input methods for CJK, the GNOME
SSH agent, snapshots, the Fedora release upgrade, "What's new", and a Sharing page (firewall, SSH,
LocalSend, KDE Connect). Hibernation is explained, not set up.

**06 — Launcher, command menu, theming, onboarding and accessibility**
([file](plan-0.3/06-experience.md)). An Omarchy-style command menu (`Super + Alt + Space`): a data
tree of Apps, Learn, Capture, Toggle, Style, Setup, Install, Remove, Update and System whose actions
are argv lists from an allowlist, with a dmenu-style mode for scripts. Launcher search learns
settings, open windows, files, units, a web search row and app actions. OSD gains notices (Caps
Lock and friends). Theming gets an automatic light/dark schedule, an opt-in palette gallery (Arctic
stays the default), font and text size, and high contrast; a new Accessibility page; a first-login
welcome; hiding the bar; a system monitor; optional weather; reminders; more user hooks.

**07 — Feature matrix** ([file](plan-0.3/07-feature-matrix.md)). Every notable Omarchy, Quickshell
shell and mainstream-desktop feature, what Arctic has today, and the decision with its section.

The sections cite research notes (`gap-list.json`, `gap-verification.json`, `engine-design.md`,
`engine-verdict.json`, `map-*.json`) that were working files and are not in the repository; the
facts the plan depends on are restated where they are used, with their sources.

## 5. Keys at a glance

The full table, with every clash check, is [04 §3](plan-0.3/04-shortcuts-capture.md). The
headline changes:

| Keys | Does | Notes |
|---|---|---|
| Super + B | Browser | was Super + W, which is now free |
| Super + Shift + S | Screenshot of an area | Print / Shift + Print / Super + Print unchanged |
| Super + A | Quick Settings | |
| Super + Ctrl + W / B / A / P / D / T / M | Network, Bluetooth, Sound, Battery, Display, Calendar, Media menu | |
| Super + Alt + N, Super + Alt + comma | Notification centre, run the newest notification's action | Super + Delete / Super + Shift + Delete / Super + Shift + N keep their keys |
| Super + Alt + Space, Super + Ctrl + C | Command menu, its Capture branch | |
| Super + Shift + C, Super + Ctrl + Print, Super + Alt + R | Colour picker, copy text from the screen, record the screen | |
| Super + Ctrl + E, Super + V | Emoji, clipboard history (new panel, same key) | |
| Alt + Tab, Super + J | Window switcher, jump to a window | not Alt + Shift + Tab: Alt + Shift switches layouts on two-layout installs |
| Super + Ctrl + N, Super + Ctrl + I, Super + P | Night light, keep awake, display mode | |

## 6. Packaging and ISO

- **New subpackage `arctic-webapps`**: `/usr/bin/arctic-webapp` (built in the existing
  `CGO_ENABLED=0` loop) and `/usr/libexec/arctic/arctic-webapp-host` (built with
  `CGO_ENABLED=1`, `-buildmode=pie` and Fedora's flags). BuildRequires `gcc`,
  `webkitgtk6.0-devel`, `gtk4-devel`; Requires `webkitgtk6.0` (at least the version it was built
  against), `gtk4`, `publicsuffix-list`. `%check` skips the host in the "no dynamic libraries"
  ELF check and asserts its libraries instead, and validates the desktop entry the built
  `arctic-webapp render-sample` writes. Details: [02 §11](plan-0.3/02-webapp-engine.md).
- **arctic-shell** gains `python3-dbus`, `python3-gobject-base`, `glib2`, `pipewire-utils` and the
  capture tools (`tesseract`, `wf-recorder`, `qrencode`, …) as Requires or Recommends per
  [03 §11](plan-0.3/03-bar-menus.md) and [04 §24](plan-0.3/04-shortcuts-capture.md).
- **arctic-desktop / arctic-desktop-config**: `mako`, `network-manager-applet`, `blueman` and
  `pavucontrol` move to Recommends (the waybar session and "More settings…" use them; the ISO
  keeps them through `plusRecommended`); `bluez` is Required. Printing, scanning, gvfs backends,
  fwupd, wlsunset and friends per [05 §11](plan-0.3/05-system.md).
- **The colour emoji font** is `google-noto-color-emoji-fonts` (`google-noto-emoji-fonts` is the
  black-and-white one), fixed in the spec and `iso/kiwi/config.kiwi`.
- **Version** 0.3.0 in `packaging/arctic-linux.spec` when the work lands.
- Watch the **ISO size**: CUPS, gvfs backends, fwupd and WebKitGTK add up; [05 §16](plan-0.3/05-system.md)
  names the fallbacks (online modules) if the 2 GiB budget is exceeded.

## 7. CI and tests

- The `go` job keeps running `go vet ./... && go test ./...` with `CGO_ENABLED=0`; the cgo host is
  invisible to it because every file is tagged. A new job compiles, vets and tests the host with
  `-tags 'cgo webkit'` in a Fedora 44 container with the WebKitGTK headers.
- New Python helpers get `unittest` suites on recorded fixtures (`shell/tests/test_apps.py`,
  `test_network.py`, `test_bt_agent.py`, `test_keyboard.py`, …), picked up by the existing
  `shell-tests` step; pure-JS logic gets Node tests (`test-menu-nav.cjs`,
  `test-notification-rules.cjs`, `test-calendar-grid.cjs`, …).
- Settings pages are covered by `settings/tests` and the headless Settings job; the shell's new
  surfaces are exercised with `shell/dev/headless.sh` IPC steps.
- A real-dnf5 harness pins what Remove apps relies on (`dnf5 remove --store` output, closures,
  `rpm -qf` owners).
- Everything that needs real hardware (Wi-Fi secrets, pairing, lid, DDC, fingerprint) is listed
  as 🔍 hands-on checks in its section.

## 8. How the work is split

The work runs as seven streams, each in its own git worktree, merged into one branch:

| Stream | Owns | Plan |
|---|---|---|
| 1 Web app engine | `cmd/arctic-webapp*`, `internal/webapp/…`, `internal/webkit/…`, the `arctic-webapps` subpackage, the cgo CI job, `docs/wiki/Web-Apps.md` | 02 |
| 2 Get apps and Remove apps | `shell/getapps/…`, `AppsService.qml`, `WebAppClient.qml`, `shell/scripts/apps*.py`, `install-terminal.py`, `package-index.py`, `PackageSearch.js`, the Get apps parts of `Launcher.qml` | 01 |
| 3a Bar menus | the menu toolkit, `BarMenu`, network/Bluetooth/sound/tray/calendar/battery/media/display panels and their helpers, Quick Settings, `Bar.qml` | 03 |
| 3b Notifications and keyboard layout | `NotificationService`, toasts, centre, DND, `arctic-notify`, the Notifications page, the layout chip | 03 |
| 4 Shortcuts and capture | the key files, capture tools, emoji, clipboard, window keys, shadowed-bind checks | 04 |
| 5 System | night light, keep awake, autostart, printing, drives, updates, lid/display, Users, Sharing… | 05 |
| 6 Experience | command menu, launcher modes, OSD, theming, accessibility, welcome, reminders, hooks | 06 |

Files several streams must touch — the spec, `config.kiwi`, `shell/shell.qml`, the Mango key
files, `keys.txt`, `arctic_settings.py`, the Settings page list, README, BUILD-SPEC and the wiki —
take small additive hunks only. The helpers streams call across each other have fixed names:
`arctic-shell-ipc apps install|remove`, `panel toggle <name>`, `quick toggle`;
`arctic-notify`, `arctic-dnd`; `arctic-screenshot`, `arctic-colorpick`, `arctic-ocr`,
`arctic-record`; `arctic-nightlight`, `arctic-keep-awake`, `arctic-display`; each UI hides a row
whose command is missing. Each section's own work-package list gives the finer order.

## 9. Rollout

1. Each stream lands with its tests green (Go, cgo, ShellCheck, Python, Node, qmllint, specs, the
   headless Settings and shell smoke tests) in a Fedora 44 container.
2. The streams merge into one branch; shared files are reconciled (keys against 04 §3, one copy of
   anything two streams both added); the whole set runs again, plus a full `tools/build-rpms.sh`.
3. A pull request to `main`; CI must be green before merging. The merge publishes 0.3.0 to every
   stable system, so a red check is fixed, never skipped.
4. The 🔍 hands-on checklists in 03, 04 and 05 run on real hardware (Wi-Fi, Bluetooth, lid, DDC,
   fingerprint, printing) and on an ISO (`tools/test-iso.sh`, `tools/test-install.sh`). Anything
   that fails there is fixed in a 0.3.x update.
5. Release notes in `docs/wiki/Release-Notes.md` cover the behaviour changes people will notice:
   the browser key, the bell (left click opens the centre), mako only in the waybar session,
   Get apps' new first page, and anything in §10 that needs a word.

## 10. Risks

| Risk | Mitigation |
|---|---|
| Fedora's Quickshell snapshot lacks fixes the menus would like (Wi-Fi network disappearing, PipeWire default-node crashes, `connectWithPsk`) | Wi-Fi goes through `nmcli`, not Quickshell.Networking; audio switching keeps the 0.2 code path; packaging 0.3.1 is the follow-up if crashes show up |
| Wi-Fi secrets without nm-applet's agent | profiles are created without secrets and brought up with `passwd-file` on a pipe; a request NetworkManager starts on its own becomes a "needs a password" toast that opens the menu (🔍 on hardware) |
| One default BlueZ agent | `bt-agent.py` re-claims the default from blueman-applet; blueman stays as the fallback |
| WebKitGTK can't play DRM video or some calls | the per-app Chromium-family runtime; the engine warns from a compatibility list |
| cgo in a pure-Go repository | build tags keep it out of `./...`; its own CI job; the manager stays pure Go |
| New default keys shadow keys people bound themselves | Settings shows which of your binds no longer work and why |
| Alt + Shift shortcuts fighting the layout switch | no new Alt + Shift binds; Settings warns about layout-switch chords |
| ISO over 2 GiB | printing and extras can move to online modules (05 §16) |
| The notification hand-over from mako | the shell checks who owns the name and falls back to mako if it can't take it |
| Removing a package that takes the desktop with it | the protected list, a preview of every package, and the same checks in the console |

## 11. Deferred and skipped

- **Packaging Quickshell 0.3.1** ourselves: the features planned here work on Fedora's snapshot;
  replacing the shell runtime on every system in the same release is a separate decision (03 §16).
- **A full NetworkManager secret agent** in the shell: 0.3 creates profiles without secrets; the
  agent follows if the hands-on checks show it's needed.
- **Nix as a Get apps source**: removing Nix apps needs root and a new polkit helper (01 §14).
- **Hibernation**: no disk swap, Secure Boot lockdown and an untested LUKS2 + btrfs resume path.
- **Dictation**: `voxtype` isn't in Fedora 44 and speech recognition is privacy-sensitive.
- **Skipped** from Omarchy and the shells (07 lists each with its reason): universal Super + C/V/X
  (Mango has no send-shortcut dispatcher), the magnifier (Mango has none), a dock and live window
  previews (not possible on Mango with this Quickshell), Omarchy's 22 themes as defaults (Arctic's
  identity stays; a gallery is opt-in), AI features, Arch-specific pieces (AUR, Limine, pacman
  hooks), time-boxed passwordless sudo, and the other items in 07.

## 12. Sources

The main outside sources, with more in each section:

- Omarchy source and manual: https://github.com/omacom/omarchy, https://omarchy.org/manual/
- Quickshell: https://quickshell.org/docs/ and https://github.com/quickshell-mirror/quickshell
  (Fedora's build: https://src.fedoraproject.org/rpms/quickshell)
- DankMaterialShell, Noctalia, Caelestia, illogical-impulse: their GitHub repositories
- WebKitGTK 6.0 API: https://webkitgtk.org/reference/webkitgtk/stable/
- Web App Manifest: https://www.w3.org/TR/appmanifest/
- Fedora 44 packages: https://packages.fedoraproject.org/ and https://mdapi.fedoraproject.org/f44/
- Mango 0.17.3: https://github.com/mangowm/mango
- NetworkManager, BlueZ, UPower, PipeWire, xdg-desktop-portal-wlr: their upstream documentation
