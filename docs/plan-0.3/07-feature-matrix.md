# Arctic Linux 0.3 — Omarchy and desktop feature matrix

Part of the [0.3 plan](../PLAN-0.3.md).

Request #6: "just research all useful desktop and omarchy features we need to add and add them too
to the plan". This section is the reference that shows every feature was considered. It has one row
per notable Omarchy feature and per notable feature of the other Quickshell shells and the mainstream
desktops, what Arctic 0.2.1 has for it, and what 0.3.0 does with it: which plan section builds it, or
why it is deferred or skipped. It is not a design; the designs are in the sections the rows point to.

It follows D8 (every P0 and P1 gap item, and every P2 item unless it is marked deferred with a
reason; every correction in `gap-verification.json`), D1 (all of it is Arctic Linux 0.3.0) and D9
where this section adds anything visible. The matrix also found three things no section owns and
one key two sections disagree on; §7, §9 and §11 deal with them.

Facts marked ✅ were checked on 2026-09-28 in the repository at `51cce98` (Arctic Linux 0.2.1), in
the Omarchy clone at `b18ab49` (branch `quattro`, the line after v4.0.4), in Mango 0.17.3's docs or in
Fedora 44's package metadata (mdapi). 🔍 marks a claim that still needs a check; each one names what
proves it. Every file:line reference in the "Arctic today" column was re-read in the repository.

---

### 1. How to read the matrix

#### 1.1 Plan sections

| Code | Section | Draft (scratchpad `plan/`) | Implementation stream |
|---|---|---|---|
| S1 | Get apps chooser (Flatpak / dnf / Web app) and Remove apps | `s1-get-remove-apps.md` | 2 (Get apps) |
| S2 | Web app engine (Go) | `s2-webapp-engine.md` | 1 (web apps) |
| S3 | Custom bar menus and Quick Settings (includes notifications, D6) | `s3-bar-menus.md` | 3a (bar menus), 3b (notifications) |
| S4 | Shortcuts, screenshots and capture tools | `s4-shortcuts-capture.md` | 4 (shortcuts) |
| S5a | System, power, hardware and network features | `s5a-system.md` | 5 (system) |
| S5b | Launcher, command menu, theming, onboarding and accessibility | `s5b-experience.md` | 6 (experience) |
| S6 | This matrix and the work no other section owns (§9) | `s6-omarchy-matrix.md` | assigned by the lead (§9.5) |

"S3 §5.1" means section 5.1 of that draft. The doc editor renumbers the sections when they are
joined into `docs/PLAN-0.3.md`; the codes stay valid through this table.

#### 1.2 Columns

| Column | Meaning |
|---|---|
| # | Row id: group letter and number. Other sections and the open issues cite rows by id (for example H10). |
| Feature | What the person gets, in plain words. Several research entries that describe the same thing share one row. |
| From | Where the feature comes from: Omarchy (4.x unless marked "Omarchy 3"), DMS (DankMaterialShell 1.6), Noctalia (5.x, now a native C++ shell; its docs still specify features well), Caelestia, end-4 (dots-hyprland `ii`), GNOME, KDE (Plasma), macOS, Windows, COSMIC, or "request #n" for the user's own requests. "(unreleased)" = on Omarchy's `quattro` branch but not in v4.0.4. |
| Arctic today (0.2.1) | **full** (Arctic has it natively), **partial** (some of it, natively), **external-app** (a third-party GUI or an optional catalog app does it), **missing**, **n/a** (does not apply to Arctic's stack), then the file:line where the fact is. |
| Plan decision (0.3.0) | The section and paragraph that builds it, with the gap id from `gap-list.json` in backticks; or **keep** (already there, nothing to do); **defer:** the reason and where it is written; **skip:** the reason. "(correction)" marks a place where `gap-verification.json` changed the gap list's proposal (§6 lists them). |
| Pri | P0-P3 from `gap-list.json`, or from `gap-verification.json` for the gaps it found ("(missed)"). "(#n)" = part of user request n. **have** = already in Arctic; **skip** = not planned at any priority; "—" = nothing to decide. |
| Sources | Keys into §12. Every key is a URL an earlier research pass read (Omarchy source files, shell docs, desktop release notes, mdapi pages). "repo" = the fact is in this repository only. |

#### 1.3 Rules used to decide

- Anything in `gap-list.json` with P0 or P1 is planned. P2 is planned unless a section defers it
  and writes down why. P3 and the gap list's skip list are not planned; the reasons are in S5b §24
  (the consolidated skip list) or in the row.
- A row that no section owned got a decision here (§7.3). A row whose work nobody owned became a
  work package here (§9).
- Nothing in the matrix overrides a section. Where a row and a section disagree, the section wins
  and the row is a bug in this matrix.

---

### 2. Current state (Arctic 0.2.1 at `51cce98`)

Arctic is already built like Omarchy 4: one Quickshell process (`shell/shell.qml`) draws the bar
(`shell/Bar.qml:1-240`), the launcher with its calculator and command modes
(`shell/Launcher.qml:1-305`, `shell/Calc.js:1-128`), the Get apps console
(`shell/InstallConsole.qml:1-316`), the wallpaper picker (`shell/Wallpapers.qml:1-317`), the power
menu (`shell/PowerMenu.qml:1-90`), the shortcut sheet (`shell/KeysSheet.qml:1-116`), the OSD
(`shell/Osd.qml:1-139`), the lock screen (`shell/LockScreen.qml:1-310`) and the polkit dialog
(`shell/PolkitDialog.qml:1-115`). Other jobs are still handed to outside programs:

| Job | Today | Where |
|---|---|---|
| Notifications, do not disturb | mako | `dotfiles/.config/mango/arctic/autostart.conf:12`, `shell/DndService.qml`, `binds.conf:74-76` |
| Clipboard history | cliphist through fuzzel | `binds.conf:23` |
| Idle, lock timers | swayidle | `dotfiles/.local/bin/arctic-session:40-64` |
| Wi-Fi joining | nm-applet's menu, nm-connection-editor | `shell/Bar.qml:179-199`, `autostart.conf:13` |
| Bluetooth pairing | blueman-manager | `shell/Bar.qml:144` |
| Sound devices, per-app volume | pavucontrol | `shell/Bar.qml:206` |
| Tray menus | Qt Widgets QMenu through `QsMenuAnchor` | `shell/Bar.qml:149-177` |
| Screen-share chooser | xdg-desktop-portal-wlr's default (slurp, outputs only) | no `xdg-desktop-portal-wlr` config in the repo |

Over the matrix's 293 rows, Arctic today is: 173 **missing**, 57 **partial**, 30 **full**, 20 **external-app**, 10 **n/a**, and one each of 🔍 (B16), "issue" (H10) and "snapshot" (N19).
Most "missing" rows are the modes and small tools Omarchy 4 and the other shells added in 2025-2026
(night light, keep awake, capture tools, calendar, media, panels); most "partial" rows are things
Arctic does in Settings but not from the bar or a key.

Three 0.2.1 facts matter for many rows:

1. **Keys.** Arctic has 82 bind lines: 77 in `binds.conf:8-109` (keys, mouse, scroll and
   gestures) and 5 in `apps.conf:6-10`. The layout switch the
   installer writes is `grp:alt_shift_toggle` (`internal/wizard/locale.go:153`), which also fires
   on every Alt + Shift + key under V1 keymaps (row H10), so no new Alt + Shift bind is allowed.
   Mango uses the first bind it reads for a key and Arctic's files are read before the user's
   (`dotfiles/.config/mango/config.conf:26-32`), so a new Arctic key hides a user's own (row Q2).
2. **Quickshell.** Fedora 44 ships the `0.2.1^git20260209.dacfa9d` snapshot and the three
   subpackages require it unversioned (`packaging/arctic-linux.spec:243`, `:263`, `:292`). It has
   IdleInhibitor, IdleMonitor, NotificationServer, Mpris, PowerProfiles and PipeWire link tracking;
   it lacks Networking PSK support and wired devices, and 0.3.1's crash fixes (row N19).
3. **No window thumbnails.** Quickshell captures single windows only through
   `hyprland-toplevel-export`, so anything that needs live window previews on Mango is out (rows
   I17, J18, J19). Whole outputs can be captured.

---

### 3. Method and coverage

**Inputs** (research files in the scratchpad `research/` folder):

| File | What it holds | Used for |
|---|---|---|
| `omarchy.json` | 166 Omarchy entries read from the source at `b18ab49`: the 51-chapter manual, `default/omarchy/omarchy-menu.jsonc`, every `default/hypr/bindings/*.lua`, the 469 `omarchy-*` commands | Omarchy rows and their sources |
| `desktop-quickshell.json` | 151 entries from DMS 1.6, Noctalia 5.2.0, Caelestia, end-4, GNOME 42-50, Plasma 6.5-6.7, macOS Tahoe, COSMIC, Windows 11 | the other rows |
| `arctic-inventory.json` | 61 Arctic features with status and files, every keybind, every helper | the "Arctic today" column (each reference re-read in the repo) |
| `gap-list.json` | 61 gap items (10 P0, 24 P1, 27 P2) and 25 skips | gap ids, priorities, skip reasons |
| `gap-verification.json` | 122 checks of those items (repo and external) and 29 missed gaps | corrections (§6), "(missed)" rows |
| the six plan drafts | the decisions | the "Plan decision" column |

**Merging.** One row per feature a person would recognise. When Omarchy and another shell describe
the same thing, the row lists both origins and both sources. When one research entry bundles
several features (for example Omarchy's "Touchpad, touchscreen and haptics toggles"), it is split
into rows H12-H14 and each gets its own decision.

**Coverage.** Every one of the 166 Omarchy entries and 151 desktop entries is referenced by at least
one row; the cross-index in §12.1 maps each entry number to its rows. The tables were generated from
a row list and checked mechanically: no research entry unreferenced, no duplicate row id, and each
of the 61 gap ids appears in backticks in at least one row. The 29 missed gaps (13 from the repo
check, 16 from the external check, several the same) were mapped by hand:

| Missed gap (`gap-verification.json`) | Rows |
|---|---|
| Input methods (Fcitx 5) | H7 |
| Hibernation setup; suspend on/off | E5, E6 |
| Layout switch vs Alt + Shift binds | H10, J11 |
| New default binds hide users' own | Q2, G15 |
| Compose key | H6 |
| Hybrid-GPU laptops | D13 |
| Scanning | N2 |
| `togglejump` / `focuslast` unbound | J12 |
| Touchscreen and 2-in-1 (rotate, touch toggle, on-screen keyboard) | H13, D10, H18 |
| Hide or move the bar; glance notices | A21, A22, A23 |
| Portal idle inhibit off (`Inhibit=none`) | E13 |
| SSH agent | L9 |
| Dictation | O16 |
| Running-apps taskbar or dock | J19 |
| Resource monitor on the bar | N12, N11, N13 |
| Lighter effects in VMs | D11 |
| Phones, cameras, network shares (gvfs) | N4 |
| Laptop speaker tuning | C18 |
| Universal copy and paste | H4 |
| Lid close and clamshell | D4 |
| Notification keys (newest action, history) | F5 |
| DNS picker, Wi-Fi band pinning | B11, B12 |
| Reset computer | L14 |
| World clock, speed tests, webcam overlay, hardware menu | O4, B13, I13, H13 |
| Wallpaper rotation, desktop widgets | K8, A27 |

**Omarchy versions.** Omarchy 4 ("Quattro", v4.0.0 on 2026-08-14, v4.0.4 on 2026-09-15) moved its
desktop into one Quickshell process, which makes it the closest peer to Arctic. Its menu is on
`Super + Space` and its apps list on `Super + Alt + Space`; the Omarchy 3 manual on
learn.omacom.io has the old layout. Three things on `quattro` are not released yet: Omasnap
(scrolling capture, pinned preview), video wallpapers and two new apps. Rows that depend on them
say "(unreleased)".

---

### 4. Summary

| Group | Rows | Planned for 0.3.0 | Already there (keep) | Deferred | Skipped | Other |
|---|---|---|---|---|---|---|
| A. Menus, the bar, panels and the shell itself | 34 | 22 | 4 | 3 | 5 | 0 |
| B. Network, Bluetooth and sharing | 23 | 17 | 0 | 2 | 3 | 1 |
| C. Sound and media | 18 | 7 | 0 | 2 | 9 | 0 |
| D. Displays, colour and graphics | 13 | 8 | 1 | 0 | 4 | 0 |
| E. Power, battery and idle | 16 | 10 | 1 | 3 | 2 | 0 |
| F. Notifications | 8 | 7 | 0 | 0 | 1 | 0 |
| G. Launcher, apps and web apps | 31 | 19 | 4 | 0 | 8 | 0 |
| H. Clipboard, keyboard and input | 20 | 11 | 2 | 1 | 6 | 0 |
| I. Screenshots, recording and capture | 20 | 13 | 1 | 1 | 5 | 0 |
| J. Windows and workspaces | 23 | 8 | 5 | 0 | 10 | 0 |
| K. Theming and appearance | 14 | 6 | 6 | 0 | 2 | 0 |
| L. Security and privacy | 15 | 5 | 4 | 0 | 6 | 0 |
| M. Updates and recovery | 9 | 4 | 4 | 0 | 1 | 0 |
| N. System, session and hardware | 19 | 11 | 2 | 1 | 4 | 1 |
| O. Clock, calendar and everyday tools | 16 | 4 | 0 | 2 | 10 | 0 |
| P. Accessibility | 4 | 1 | 1 | 0 | 2 | 0 |
| Q. Onboarding and help | 5 | 5 | 0 | 0 | 0 | 0 |
| R. Development tools | 5 | 0 | 0 | 0 | 5 | 0 |
| **All** | **293** | **158** | **35** | **15** | **83** | **2** |

Planned rows by priority: P0 15, P1 66, P2 75, P3 2.

"Planned" rows include rows where a section builds the main feature and skips a minor part (for
example A9: the dmenu mode is built, Noctalia's script providers are not). Every P0 and P1 gap item
is planned except `quickshell-031`, which D5 defers (row N19).

---

### 5. The matrix

#### A. Menus, the bar, panels and the shell itself

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| A1 | Nested command menu (Apps, Learn, Trigger, Style, Setup, Install, Remove, Update, System) | Omarchy | **missing** · launcher specials only: Install (live), Apps, Get apps, Wallpapers, Settings, Fetch (`shell/Launcher.qml:46-55`) | S5b §4 `command-menu`: tree as data in `shell/menu/*.json`, `arctic-menu`, `Super + Alt + Space` | P1 | [O-doc-menu] [O-menu-jsonc] |
| A2 | Learn branch (shortcut sheet, manual, wikis) | Omarchy | **missing** · the manual is `docs/wiki/`; nothing in the desktop links to it | S5b §4.6 Learn rows: shortcut sheet, Arctic wiki, Fedora docs, "Coming from Windows or macOS" | P1 | [O-menu-jsonc] |
| A3 | Trigger branch (capture, share, toggles, hardware, reminders, emoji) | Omarchy | **missing** | S5b §4.6; rows come from S4 §10 (capture), S5a §8.4 (share), S3 §5.11 (toggles), S5b §13 (reminders), S4 §11 (emoji) | P1 | [O-menu-jsonc] |
| A4 | Style branch (theme, background, font, look and feel) | Omarchy | **partial** · Settings > Appearance (`settings/pages/AppearancePage.qml:98-175`), picker on `Super + Shift + W` (`binds.conf:22`) | S5b §4.6 `style.*` rows, backed by S5b §7 | P1 | [O-menu-jsonc] |
| A5 | Setup branch (monitors, keybindings, input, network, default apps) | Omarchy | **partial** · `arctic-settings <page>` opens any Settings page (`dotfiles/.local/bin/arctic-settings:29-34`) | S5b §4.6 Setup rows = deep links into Settings pages | P1 | [O-menu-jsonc] |
| A6 | Update branch (update, channel, restarts, firmware, passwords, time) | Omarchy | **partial** · update pill and popover (`shell/UpdateIndicator.qml`, `shell/UpdatePopover.qml`), Settings > Updates | S5b §4.6; rows in `shell/menu/40-system.json` written by S5a (check now, Flathub, firmware, `arctic-restart …`) | P1 | [O-menu-jsonc] |
| A7 | Open any menu branch from a key or a script | Omarchy | **missing** | S5b §4.9 `arctic-menu <route>`; `Super + Ctrl + C` = `arctic-menu capture`, `Super + Ctrl + R` = `arctic-menu remind` | P1 | [O-doc-menu] |
| A8 | User menu entries, merged by id | Omarchy | **missing** | S5b §4.2 `~/.config/arctic/menu.json` (a shipped id overrides only the fields given) | P1 | [O-man31] |
| A9 | One themed picker for scripts (dmenu mode) | Omarchy, Noctalia | **external-app** · helpers pipe through `fuzzel --dmenu` (`binds.conf:23`) | S5b §4.9 `arctic-menu select` (fuzzel stays the fallback); Noctalia's script providers: skip, S5b §24 (plugin surface) | P1 | [O-doc-menu] [N-launcher] |
| A10 | Bar items act on left, middle, right click and scroll | Omarchy, DMS | **partial** · `BarItem` has clicked, rightClicked, middleClicked, scrolled (`shell/BarItem.qml:18-21`); Bluetooth, network and volume clicks start third-party GUIs (`shell/Bar.qml:144`, `:179-199`, `:206`) | S3 §7.2: every item opens an Arctic menu; right click keeps its quick action (mute, radio) | P1 (#3) | [O-man05] |
| A11 | A hotkey per bar menu; full keyboard use inside | Omarchy | **missing** · popovers close with Esc only (`shell/Popover.qml:99`) | S3 §8.1-8.2 `panel-hotkeys-bar-focus`: `Super + Ctrl + W / B / A / P / D / T / M` | P1 | [O-bind-utilities] [O-man05] |
| A12 | Walk the bar with the keyboard | Arctic design | **missing** · planned on `Super + B`, never built (`dotfiles/README.md:139`) | S3 §8.3; the key is disputed: S3 uses `Super + Alt + B`, S4 §3.2 row 41 uses `Super + Alt + P` (open issue 1) | P1 | repo |
| A13 | Numbered menu keys (`Super + Ctrl + 1…9`) | Omarchy | **missing** | defer: S3 §16 (item order differs per machine; the named keys reach every menu) | P3 | [O-bind-utilities] |
| A14 | Quick settings hub | Windows (Win + A), GNOME 43, macOS, Noctalia, DMS | **missing** · each toggle sits on its own Settings page | S3 §5.11 `control-center`, `Super + A`: sliders, tiles, sub-pages hosting the bar menus | P1 | [N-control-center] [Windows-keys] [macOS-Tahoe] |
| A15 | Toggle tiles | Noctalia, DMS, end-4 | **missing** | S3 §5.11: Wi-Fi, Bluetooth, do not disturb, power mode, dark mode, airplane, mic, VPN; night light, keep awake, game mode added by S5a §5.1, §4.1, §5.3; recording by S4 §8. Not added: wallpaper, session, clipboard and layout tiles (each has its own key) | P1 | [N-control-center-shortcuts] |
| A16 | One toggle model: key, menu row, command, indicator | Omarchy | **missing** | S3 §5.11 `ToggleRegistry` + IPC `toggle set\|get\|states`; menu rows S5b §4.6; OSD notice S5b §6.3 | P1 | [O-man13] |
| A17 | Edit and reorder the tile set | DMS, macOS | **missing** | defer: S3 §16 (fixed order; tiles hide when their hardware is missing) | P3 | [N-control-center] |
| A18 | Mode indicators left of the clock; inactive ones revealed on hover | Omarchy | **missing** · only the bell (`shell/Bar.qml:125-134`) | S3 §5.12 `mode-indicators` | P1 | [O-man13] [O-man05] |
| A19 | Tray menus drawn by the shell | request #3 (D5) | **partial** · icons native; menus through `QsMenuAnchor`, i.e. a Qt Widgets QMenu (`shell/Bar.qml:149-177`) | S3 §5.10 `TrayPanel.qml` (QsMenuOpener) | P1 (#3) | repo |
| A20 | Tray drawer for rarely used icons | Omarchy, KDE 6.7 | **missing** | defer: S3 §16; skip in S5b §24 (calm bar) | P3 | [O-man42] [O-man05] |
| A21 | Hide and show the bar | Omarchy | **missing** · the bar is always there (`shell/Bar.qml:14-27`) | S5b §10 `Super + Shift + Space`; menus still open by key; privacy pills stay visible (`PrivacyPeek.qml`) | P2 (missed) | [O-man05] [O-man07] |
| A22 | Bar on any edge, drag to reorder, transparency | Omarchy, Noctalia, DMS, end-4 | **n/a** · fixed 34 px top bar by design (`design/guidelines/10-platforms.md`) | skip: S5b §24 (calm top bar; popovers already dock to any edge) | skip | [O-man05] |
| A23 | Glance keys for time, battery, weather | Omarchy | **missing** | skip: S5b §24 (menus open by key even while the bar is hidden) | P3 | [O-man10] |
| A24 | Update-available badge | Omarchy, DMS | **full** · `shell/UpdateIndicator.qml`, `shell/UpdatePopover.qml`, `shell/UpdateService.qml` | keep; the counts add Flathub and firmware (S5a §7.1) | have | [O-plug-bar-widgets-SystemUpdate] |
| A25 | Workspaces on the bar; active window title | Omarchy, Caelestia | **full** workspaces (`shell/Workspaces.qml:1-98`); title **missing** | keep workspaces; skip the title (calm bar): windows are named in Alt + Tab (S4 §18) and the launcher's window rows (S5b §5.4) | have | [O-plug-README] [C-repo] |
| A26 | Script widgets on the bar | Noctalia | **missing** | skip: a plugin surface; menu entries (S5b §4.2) and hooks (S5b §14) cover scripting | skip | [N-bar-widgets] |
| A27 | Desktop widgets | Noctalia, DMS, Caelestia | **missing** | skip: S5b §24 | skip | [N-desktop-widgets] |
| A28 | One shell process for bar, menus, notifications, OSD, lock, polkit, clipboard and pickers | Omarchy 4 | **partial** · the shell draws bar, launcher, OSD, lock and polkit (`shell/shell.qml`); mako, fuzzel and swayidle run beside it (`dotfiles/.config/mango/arctic/autostart.conf:12-15`) | S3 §5.4 (notifications, D6), S4 §11-12 (emoji, clipboard), S4 §9 (share picker), S5a §4.4 (idle); the tools stay for the waybar session | P1 | [O-doc-omarchy-shell] |
| A29 | Plugin system (plugins from git) | Omarchy, DMS, Noctalia | **missing** | skip: S5b §24 (code-execution surface) | skip | [O-man32] [O-doc-omarchy-shell] |
| A30 | Every panel and toggle scriptable | Omarchy, DMS, Noctalia | **partial** · `arctic-shell-ipc` targets launcher, apps, wallpapers, power, keys, osd, lock, welcome, dnd, updates, shell (`dotfiles/.local/bin/arctic-shell-ipc`) | every section adds IPC: S1 `apps`, S3 `panel`/`quick`/`toggle`/`bar`/`notifications`, S4 `capture`/`share`/`emoji`/`clipboard`/`record`, S5b `menu`/`osd`; no single `arctic` router (the `arctic-*` helpers stay) | P1 | [O-man14] [O-man13] |
| A31 | User hooks on desktop events | Omarchy, Noctalia | **partial** · theme hooks only, system and user folders (`dotfiles/.local/bin/arctic-theme:26-30`, `:53`) | S5b §14 `user-hooks`: the theme-hook contract generalised to wallpaper, battery-low, post-update, lock, unlock (correction applied) | P2 | [O-man31] [N-automation-hooks] |
| A32 | Configuration as user-owned files, reload after edits | Omarchy | **full** · `~/.config/mango/*.conf`, `Super + Shift + R` (`binds.conf:9`); Settings writes `settings.conf` | keep | have | [O-man31] |
| A33 | OSD for more than volume and brightness | Omarchy, DMS | **partial** · volume and brightness (`shell/Osd.qml:14-105`); mic mute is a notification (`dotfiles/.local/bin/arctic-osd:36-40`) | S5b §6 `osd-kinds` (level and notice kinds: toggles, power mode, layout, Caps Lock, theme); S4 §17 keyboard light, touchpad, mic | P2 | [O-plug-README] [D-OSD] |
| A34 | Omarchy 3 stack (Walker, Waybar, Mako, SwayOSD, hyprlock), for comparison | Omarchy 3 | **full** as Arctic's fallback session (`ARCTIC_SHELL=waybar`: waybar, fuzzel, mako, swaylock) | keep the fallback working; every section names its "without the shell" path | have | [O3-utilities] |

#### B. Network, Bluetooth and sharing

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| B1 | Wi-Fi list with an inline password (replaces nm-applet) | Omarchy 4, DMS, Caelestia, end-4, GNOME, Windows | **external-app** · click opens nm-applet's menu or nm-connection-editor (`shell/Bar.qml:179-199`); Settings shows the radio switch only (`settings/pages/NetworkPage.qml:89-97`) | S3 §5.1 + §6.1 `network.py` (nmcli; the password goes on stdin, never argv); nm-connection-editor stays as "More settings…" | P1 (#3) | [O-v4.0.0] [O-man35] |
| B2 | Hidden networks, forget, connection details | DMS, Noctalia | **external-app** · nm-connection-editor | S3 §5.1 `wifi-extras` | P2 | [O-man35] |
| B3 | Enterprise Wi-Fi (802.1X) form | Omarchy, Noctalia, DMS | **external-app** · nm-connection-editor | S3 §5.1 (PEAP and TTLS with a CA certificate; EAP-TLS stays in the editor) | P2 | [O-v4.0.0] [N-control-center] |
| B4 | Share the Wi-Fi as a QR code | Omarchy, DMS, KDE 6.5 | **missing** | S3 §5.1 `WifiShare.qml` (qrencode; PSK read through polkit; `wl-copy --sensitive`; hidden for WPA-EAP; layer shielded from capture) | P2 | [O-man35] |
| B5 | Hotspot | DMS, GNOME 43 | **missing** | S3 §5.1 row 9 (only when the device supports AP mode) | P2 | [D-v1-6-release] |
| B6 | Airplane mode | Windows, GNOME, Noctalia | **missing** | S3 §5.1 + toggle `airplane` (rfkill wlan, bluetooth, wwan; restores what was on) | P2 | [N-control-center-shortcuts] |
| B7 | Wired connection row | Quickshell 0.3 changelog | **partial** · state from nmcli in `shell/NetworkService.qml` (Quickshell's Networking knows Wi-Fi only, `:8`) | S3 §5.1 wired row through nmcli; Quickshell 0.3 wired support waits for `quickshell-031` (row N19) | P1 | [QS-v0.3.1] |
| B8 | Mobile data (WWAN) card | Noctalia, DMS | **missing** | skip: S5b §24 (niche); airplane mode still blocks WWAN (S3 §5.1) | P3 | [N-control-center] |
| B9 | VPN list, connect, import `.ovpn` / WireGuard `.conf` | DMS, Caelestia, GNOME 43, Omarchy (installers) | **external-app** · nm-connection-editor (`settings/pages/NetworkPage.qml:89-90`); Proton VPN module (`modules/security/protonvpn`) | S3 §5.1 `vpn-quick-connect`, toggle `vpn` with an indicator; NetworkManager-openvpn Recommends | P2 | [O-man24] [D-vpn] |
| B10 | Tailscale status and exit node | Omarchy, DMS | **missing** · `tailscale` is in F44 but not shipped | S3 §5.1 Tailscale row (only when installed); the full panel and Taildrop: skip, S5b §24 | P2 | [O-man35] |
| B11 | DNS provider picker | Omarchy | **external-app** · nm-connection-editor | defer: S3 §16 (P3) | P3 | [O-man35] |
| B12 | Wi-Fi band pinning | Omarchy | **external-app** · nm-connection-editor | defer: S3 §16 (P3) | P3 | [O-man35] |
| B13 | Network and disk speed test | Omarchy | **missing** | skip: P3; Omarchy's speed-test backend is unverified and a test sends traffic to a third party | P3 | [O-man35] |
| B14 | Live download and upload rates | Omarchy | **missing** | S5b §11 System panel row "Network ↓ … · ↑ …" (`/proc/net/dev`); ping not planned | P2 | [O-v4.0.0] |
| B15 | Bluetooth menu with pairing and a code dialog (replaces blueman) | Omarchy 4, DMS, Noctalia, end-4, COSMIC | **partial** · Settings connects and forgets paired devices (`settings/pages/BluetoothPage.qml:1-93`); scanning and pairing in blueman-manager (`shell/Bar.qml:144`) | S3 §5.2 + §6.2 `bluetooth-pairing-agent`: `bt-agent.py` (python3-dbus BlueZ Agent1; Quickshell has no agent); blueman stays for the waybar session and "More settings…" | P1 (#3) | [O-v4.0.0] [N-control-center] |
| B16 | Bluetooth on/off kept across reboots | Omarchy | 🔍 · Arctic sets nothing; Fedora's systemd-rfkill restores soft-block state at boot | no change; 🔍 turn Bluetooth off in the new menu, reboot, check `rfkill` (§11, unverified 1) | — | [O-v4.0.0] |
| B17 | Bluetooth audio profile (A2DP / HFP) | DMS | **external-app** · pavucontrol | S3 §5.3 device page (ports and profiles) | P3 | [D-Details] |
| B18 | Battery levels of mice, keyboards, headsets | Noctalia, Omarchy | **partial** · Settings > Bluetooth shows a level for paired devices (`settings/pages/BluetoothPage.qml`) | S3 §5.2 rows + §5.6 "Other devices" + one notification at 10 % | P2 | [O-v4.0.0] [N-services-battery] |
| B19 | LocalSend share menu (AirDrop-like) | Omarchy | **external-app** · optional Flathub module (`modules/sync/localsend/module.toml`), no firewall allow | S5a §8.4 `share-localsend-kdeconnect`: `arctic-share`, `SharePanel.qml`, `Super + Ctrl + S`, a Thunar action, the firewall allow | P2 | [O-man22] |
| B20 | Phone integration (KDE Connect) | KDE, GNOME (GSConnect) | **missing** | S5a §8.4 `share-localsend-kdeconnect`: catalog module `kdeconnect` (kdeconnectd) + the firewalld `kdeconnect` service | P2 | [KDE-KDEConnect] |
| B21 | Remote desktop server | GNOME 50, KDE 6.5 | **missing** | skip: S5b §24 (their RDP servers are tied to their compositors) | skip | [xdpw] |
| B22 | Firewall status and one-click allows | Omarchy | **missing** UI · firewalld is enabled by preset (`packaging/release/90-default.preset:70`) | S5a §8.3 `firewall-ssh`: Settings > Sharing (`arctic-system-helper firewall-allow localsend\|kdeconnect\|mdns\|ssh`) | P2 | [O-man35] [O-man48] |
| B23 | Remote login (SSH), key-only | Omarchy | **missing** · sshd off on purpose (`packaging/release/80-arctic.preset:41-45`) | S5a §8.3 `firewall-ssh` (`ssh on\|off`, `ssh-password on\|off`) | P2 | [O-man35] [O-man48] |

#### C. Sound and media

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| C1 | Output and input pickers with sliders (replaces pavucontrol) | Omarchy, DMS, Noctalia, end-4, Caelestia, GNOME 43 | **partial** · Settings > Sound picks the default devices (`settings/pages/SoundPage.qml:1-130`); the bar click opens pavucontrol (`shell/Bar.qml:206`) | S3 §5.3; pavucontrol moves to Recommends behind "Volume control…" | P1 (#3) | [O-man05] [N-control-center] |
| C2 | Per-app volume | Omarchy, end-4, Noctalia, Windows | **external-app** · pavucontrol | S3 §5.3 `audio-panel-scope`: "Apps" sliders (`PwNode.isStream`) | P1 | [O-man05] |
| C3 | Send one app to another output | Windows 11 (Win + Ctrl + V) | **external-app** · pavucontrol | defer: S3 §16 (`pw-metadata target.object` unverified on WirePlumber 0.5) | P2 | [O-man05] [Windows-keys] |
| C4 | Microphone mute, input level and mute indicator | Omarchy, Noctalia | **partial** · the mic key toggles and posts a notification (`dotfiles/.local/bin/arctic-osd:36-40`) | S3 §5.3 input slider, §5.11 `mic` toggle (indicator while muted); S4 §17 mic OSD in the shell; no separate bar mic item (the privacy pill shows use) | P1 | [O-man05] [N-control-center-shortcuts] |
| C5 | Live microphone meter | KDE 6.7 | **missing** | defer: S3 §16 (`PwNodePeakMonitor` crashes in the F44 snapshot; appears with Quickshell ≥ 0.3) | P2 | [KDE-6.7.0] |
| C6 | Volume above 100 % | Noctalia, KDE 6.5 | **missing** · capped at 100 % (`dotfiles/.local/bin/arctic-osd:31`, `wpctl set-volume -l 1.0`) | skip: P3 (speaker-damage risk); pavucontrol stays installed for it | P3 | [N-services-audio] |
| C7 | "Output changed" toast | Caelestia | **missing** | S3 §5.3 ("Sound now plays on Headphones") | P2 | [C-Audio] |
| C8 | Next-output key (`Shift + Mute`) | Omarchy | **missing** | S3 §8.1 `audio-panel-scope`: `bindl=SHIFT,XF86AudioMute,spawn,arctic-osd output next` | P1 | [O-bind-media] [C-Audio] |
| C9 | Next media source (`Shift + Play`), 1 % volume steps (`Alt` + volume keys) | Omarchy | **missing** | skip: P3; the media menu switches players (S3 §5.7); 5 % steps stay | P3 | [O-bind-media] |
| C10 | Push-to-talk key | KDE 6.7 | **missing** | skip: P3; apps can't register global shortcuts on Mango (row N18) | P3 | [C-Audio] |
| C11 | UI sounds | Noctalia, DMS | **missing** | skip: P3 (not in the gap list; calm) | P3 | [N-services-audio] |
| C12 | EasyEffects toggle | end-4 | **external-app** · optional module (`modules/music/easyeffects/module.toml`) | skip: the app is in the catalog; no tile | P3 | [E4-services] |
| C13 | Now playing on the bar; media menu | Omarchy, Noctalia, DMS, GNOME | **partial** · media keys run playerctl (`binds.conf:93-95`) | S3 §5.7 `media-controls`, `Super + Ctrl + M` (left = menu, middle = play/pause, scroll = next/previous; not presented as Omarchy's mapping, correction) | P0 | [O-bind-media] [N-control-center] [O-plug-services-media-BarWidget] |
| C14 | Media controls on the lock screen | GNOME 49 | **missing** | S3 §5.7 (one row in `LockScreen.qml`) | P0 | [N-control-center] [GNOME-49] |
| C15 | OSD on track change | DMS | **missing** | skip: P3 (a toast per track is noise; the bar item shows the title) | P3 | [N-control-center] |
| C16 | Visualiser, lyrics, album-art accent | DMS, Caelestia, Noctalia | **missing** | skip: S5b §24 (an album-art accent would also break D9) | skip | [C-repo] |
| C17 | Music recognition | end-4 | **missing** | skip: S5b §24 | skip | [E4-musicRecognition] |
| C18 | Per-laptop speaker tuning | Omarchy | **missing** | skip: S5b §24 (device-specific) | skip | [O-man45] |

#### D. Displays, colour and graphics

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| D1 | Night light with a schedule | Omarchy, Noctalia, DMS, end-4, GNOME, KDE, Windows, macOS | **missing** | S5a §5.1 `night-light`: `arctic-nightlight` supervises wlsunset (restarted on change; `-d` only with custom hours, correction), `Super + Ctrl + N`, tile, indicator | P0 | [O-man13] [N-services-night-light] [man-wlsunset] |
| D2 | Brightness sliders incl. external monitors (DDC/CI); keys act on the focused screen | Omarchy, Noctalia | **partial** · keys and OSD through brightnessctl (`binds.conf:91-92`, `arctic-osd:41-50`) | S3 §5.8 `external-brightness-ddc` (ddcutil; Fedora's package already ships the i2c-dev and udev files, correction) | P2 | [O-man05] [O-bind-media] [N-services-brightness] |
| D3 | Display mode: laptop only, duplicate, extend, other screen only | Omarchy, Windows (Win + P) | **missing** · Settings arranges outputs and turns them on or off (`settings/pages/DisplaysPage.qml`) | S5a §5.2 `display-mode-mirror`: `arctic-display`, `Super + P` and `XF86Display`, wl-mirror for Duplicate | P2 | [O-man33] [Windows-keys] |
| D4 | Lid close with an external screen (clamshell) | Omarchy | **partial** · read-only text (`settings/pages/PowerPage.qml:88-95`) | S5a §4.5: Mango `switchbind=fold\|unfold` → `arctic-display lid` (correction: Mango has lid binds), a Settings choice | P1 (missed) | [O-man33] [Mango-0.17.3-switchbind] |
| D5 | Display profiles for docked and undocked | DMS | **partial** · Settings saves a `monitorrule` per output name (`settings/scripts/arctic_settings.py` display commands, `:1371-1666`) | skip: not planned; Mango applies a saved rule whenever that output connects 🔍 (dock, undock, check the modes) | P2 | [D-BuiltinPlugins] |
| D6 | Scale and text-size keys; scale presets | Omarchy | **partial** · Settings > Displays (scale) and Appearance (text size) | skip: S5b §24 (P3; `Super + /` is the shortcut sheet) | P3 | [O-man33] [O-man05] |
| D7 | One text size for the shell, GTK and terminals | Omarchy | **partial** · GTK text scale only (`settings/pages/AppearancePage.qml:450-519`) | S5b §7.3 `fonts-symbols` (`Theme.fs`, terminal size; shell capped at 1.25) | P2 | [O-bin-display-text-size] |
| D8 | VRR, HDR, ICC profiles | GNOME 48/50, DMS | **partial** · VRR per monitor (`settings/pages/DisplaysPage.qml`) | keep VRR; HDR: skip, S5b §24 (needs Mango's non-scenefx branch); ICC: skip (P3) | P3 | [Mango-monitors] |
| D9 | Lower refresh rate on battery | DMS | **missing** | skip: P3 (tuned-ppd's battery profile handles power) | P3 | [D-v1-6-release] |
| D10 | Automatic brightness, auto-rotate | KDE 6.6 | **missing** | skip: S5b §24 | skip | [KDE-6.6.0] |
| D11 | Lighter effects in VMs and without a GPU driver | Omarchy (commit b18ab49) | **missing** | S5a §5.3 `arctic-effects` (`systemd-detect-virt`, llvmpipe → no animations, blur, shadows) | P2 (missed) | [O-commit-b18ab49] |
| D12 | Game mode (animations, blur, shadows, gaps off) | Caelestia, end-4, Omarchy | **missing** · one setting at a time in Settings > Windows (`settings/pages/WindowsPage.qml`) | S5a §5.3 `game-mode` (`mmsg dispatch setoption`, settings.conf untouched), tile | P2 | [O-man13] [C-GameMode] |
| D13 | Run an app on the discrete GPU | GNOME, Omarchy (hybrid GPU) | **missing** · environment variables only (`packaging/desktop/arctic-graphics.sh:13-19`) | S5a §5.4 `arctic-gpu` (switcheroo-control, `PrefersNonDefaultGPU`, `Shift + Enter` in the launcher); moving the whole desktop to the dGPU: defer, S5a §17 | P2 (missed) | [O-menu-jsonc] [F44-switcheroo-control] |

#### E. Power, battery and idle

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| E1 | Power menu | Omarchy | **full** · `shell/PowerMenu.qml:1-90`, `Super + Escape` (`binds.conf:17`) | keep; extras in E2-E4 | have | [O-bind-utilities] |
| E2 | Close windows politely before log out, restart, shut down | Omarchy | **missing** | S5a §4.6 `power-menu-extras`: `arctic-power prepare` (`mmsg dispatch killclient client,<id>`, never `force`) | P2 | [O-bind-utilities] |
| E3 | Warn when an install is running | end-4 | **missing** | S5a §4.6 `power-menu-extras` (Get apps' `AppsService.busy`, `pgrep -x dnf5\|rpm\|flatpak`) | P2 | [E4-services] |
| E4 | Hibernate, restart into firmware setup, boot another entry, switch user | Omarchy, DMS | **missing** | S5a §4.6 `power-menu-extras`: Hibernate only when logind allows it; firmware setup when `CanRebootToFirmwareSetup`; BootNext and switch user: skip (P3) | P2 | [O-bind-utilities] [D-BootEntryService] |
| E5 | Set up hibernation | Omarchy | **missing** · the installer makes no swap and no `resume=` | defer: S5a §4.7 (zram only, Secure Boot lockdown, untested on LUKS2 + btrfs) | P2 | [O-man36] |
| E6 | Suspend on/off switch | Omarchy | **missing** | defer: S5a §17 ("Suspend after: Never" and the lid's "Keep running" cover it) | P3 | [O-man36] |
| E7 | Power mode from the bar | Omarchy, Noctalia, Windows | **partial** · Settings > Power and lock (`settings/pages/PowerPage.qml:68-85`, tuned-ppd over D-Bus) | S3 §5.6 radio rows + `power-mode` tile through Quickshell `PowerProfiles` (tuned-ppd has no `powerprofilesctl`, correction) | P1 | [O-man05] [O-man36] |
| E8 | Power mode remembered per charger state | Omarchy | **n/a** | skip: S5b §24 (tuned-ppd already maps balanced to balanced-battery on battery) | skip | [O-man36] [tuned-ppd.conf] |
| E9 | Low and critical battery warnings | Omarchy, Noctalia, end-4, Caelestia | **partial** · the icon turns red at 10 % or less (`shell/Bar.qml:225`) | S3 §5.6 (menu, notifications) + S5a §4.2 (logic, waybar-session watcher) `low-battery-warnings`; the critical text names UPower's real action (correction: `Auto` calls logind `Sleep()`, usually suspend here) | P0 | [O-plug-services-battery-Service] [N-services-battery] [UPower-backend] |
| E10 | Battery health and an 80 % charge limit | GNOME 48, Noctalia | **missing** | S3 §5.6 + S5a §4.3 `battery-health-limit` (`UPowerDevice.healthPercentage`, `EnableChargeThreshold`; polkit 🔍) | P1 | [UPower-Device] |
| E11 | Battery details and history chart | DMS, Omarchy | **partial** · tooltip with time to full or empty (`shell/Bar.qml:227-228`) | S3 §5.6 header (time, state, limit); chart: skip, S5b §24 (no graphs) | P2 | [O-man05] [D-Popouts] |
| E12 | Keep awake, with durations | Omarchy, DMS, Caelestia | **missing** · swayidle locks at 300 s and suspends at 900 s (`dotfiles/.local/bin/arctic-session:40-64`) | S5a §4.1 `keep-awake`: Quickshell `IdleInhibitor` on the bar, `Super + Ctrl + I`, tile, indicator | P0 | [O-man13] [N-bar-widgets-caffeine] |
| E13 | Apps keep the screen awake (video calls, players) | Caelestia | **missing** · Mango's `mango-portals.conf` sets `Inhibit=none` (packaged at `packaging/mangowm.spec:82`) | S5a §4.1 `scripts/screensaver-bridge.py` (`org.freedesktop.ScreenSaver`) | P2 (missed) | [N-bar-widgets-caffeine] |
| E14 | Idle: dim first, lock, screen off; battery and AC times | Omarchy, DMS, Noctalia | **partial** · swayidle, no dim (`arctic-session:40-64`; times in `settings/pages/PowerPage.qml:44-66`) | S5a §4.4 `idle-dim` (Quickshell `IdleMonitor`; swayidle stays as the backstop) | P2 | [O-man13] [N-services-idle] |
| E15 | Screensaver | Omarchy, DMS | **missing** | skip: S5b §24 (not calm; battery) | skip | [O-man13] |
| E16 | Apps in their own systemd scopes, so oomd ends one app, not the session | Omarchy 4 | **partial** · `systemd-oomd-defaults` in the image (`iso/kiwi/config.kiwi:110`); apps share Mango's cgroup | defer (S6): not in the gap list; needs `systemd-run --user --scope` in `arctic-open`, the launcher and every spawn bind; 🔍 what oomd kills under pressure today | P2 | [O-v4.0.0] |

#### F. Notifications

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| F1 | Notification server, centre and history in the shell (replaces mako) | Omarchy 4, DMS, Noctalia, end-4, Caelestia | **partial** · mako (`autostart.conf:12`); right-click on the bell runs `makoctl restore` (`shell/Bar.qml:132`) | S3 §5.4 `notification-center` (D6); mako moves to Recommends in both subpackages (correction) | P1 | [O-doc-notifications] |
| F2 | Grouping per app | GNOME 48, DMS | **missing** | S3 §5.4 | P1 | [GNOME-48] |
| F3 | Do not disturb with durations, a schedule and a missed list | Omarchy, DMS, KDE 6.5, GNOME 49 | **partial** · a mako mode, bell and `Super + Shift + N` (`shell/DndService.qml`, `dotfiles/.local/bin/arctic-dnd`) | S3 §5.4; Arctic alerts (`x-arctic-alert`) still show — Arctic's own rule (correction: Omarchy lets through only its own toasts and `notify-send` criticals) | P1 | [O-doc-notifications] [O-man13] |
| F4 | Per-app rules (no toast, no history, allowed in DND) | Noctalia, DMS | **missing** | S3 §5.4 + §9.5 `settings/pages/NotificationsPage.qml` | P2 | [N-services-notifications] |
| F5 | Keys: dismiss, dismiss all, run the newest action, open the centre | Omarchy | **partial** · `Super + Delete`, `Super + Shift + Delete` through makoctl (`binds.conf:74-75`) | S3 §8.1 `arctic-notify`: same keys; `Super + Alt + N` centre, `Super + Alt + ,` newest action; Omarchy's history key holds Alt + Shift, not copied | P1 | [O-bind-utilities] [O-man07] |
| F6 | Toast position and monitor | Noctalia | **n/a** · mako's config | skip: P3; top right, 340 px (`design/guidelines/10-platforms.md`) | P3 | [O-man07] |
| F7 | "N notifications" on the lock screen | GNOME, DMS | **missing** · mako can't count (`dotfiles/README.md:141-142`) | S3 §5.4 | P1 | [N-lockscreen-widgets] |
| F8 | Actions on the screenshot notification | request #5 (D7) | **missing** · plain `notify-send` (`dotfiles/.local/bin/arctic-screenshot:40`) | S4 §5.6 (Open, Edit, Show in Files, Move to Trash); needs the server's `actions` capability (S3 §5.4.1) | P1 (#5) | repo |

#### G. Launcher, apps and web apps

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| G1 | App launcher | Omarchy, all shells | **full** · `shell/Launcher.qml:1-305`, `Super + Space` (`binds.conf:14`) | keep; search modes in G21-G26 | have | [O-bin-remove-launcher-entry] |
| G2 | Delete on a launcher row removes the app the right way | Omarchy | **missing** | S1 §3.9 + §6.12 `launcher-uninstall-key` (web app → engine; own .desktop → file; Flatpak; `rpm -qf` → dnf; protected packages refused) | P1 (#4) | [O-bin-remove-launcher-entry] |
| G3 | Install by source: Flathub, Fedora packages, web app, terminal app | Omarchy | **partial** · one PTY console (`shell/InstallConsole.qml:1-316`, `shell/scripts/install-terminal.py:1-318`) | S1 §3.1-3.5 chooser (D2); the console stays (§3.8) | P1 (#1) | [O-menu-jsonc] |
| G4 | Package search with details before installing | Omarchy | **partial** · Tab completion in the console (`shell/PackageSearch.js:1-145`) | S1 §3.2-3.3 (AppStream metadata where available) | P1 (#1) | [O-bin-pkg-install] |
| G5 | Remove by source, showing everything that goes | Omarchy | **partial** · typed `dnf remove` / `flatpak uninstall` (`shell/scripts/install-terminal.py:11-13`) | S1 §3.6-3.7 (D3; the dnf preview lists every package; protected packages §6.8) | P1 (#4) | [O-menu-jsonc] [O-bin-pkg-install] |
| G6 | Installed catalog items stay listed, marked | Omarchy | **missing** | S1 §3.2 ("Installed" chip) | P1 | [O-doc-menu] [O-menu-jsonc] |
| G7 | Web app creator: any site becomes an app | Omarchy | **missing** · nothing (`grep webapp` finds none) | S2 (D4): `arctic-webapp` (Go, stdlib) + `arctic-webapp-host` (WebKitGTK 6.0, cgo) + Chromium `--app` fallback; S1 §3.4 page; subpackage `arctic-webapps` | P1 (#2) | [O-bin-webapp-install] [O-man25] |
| G8 | Preinstalled web apps with keys | Omarchy | **missing** | skip: S5b §24, S2 §1 (web apps are yours to make) | skip | [O-bind-applications] |
| G9 | Web apps as link handlers (mailto, zoommtg) | Omarchy | **missing** | S2 §8.15 `default-app-roles` (opt-in `mailto:` for listed mail sites; Zoom not done, calls don't work in WebKit) | P2 | [O-bind-applications] [O-man25] |
| G10 | Copy the current page address (`Alt + Shift + L`) | Omarchy | **missing** | skip: S5b §24 (a browser extension); `Alt + Shift` also flips the layout (row H10) | skip | [O-man23] [O-man25] |
| G11 | Terminal programs as launcher apps | Omarchy | **missing** | S1 §3.5 + §6.11 `tui-launchers` | P2 | [O-bin-tui-install] |
| G12 | Install-on-first-use keys | Omarchy | **missing** | skip: S5b §24 | skip | [O-man24] |
| G13 | Remove or restore every preinstalled app | Omarchy | **n/a** · Arctic installs only what the installer ticked | skip: S5b §24 | skip | [O-bin-install-preinstalls] |
| G14 | Default apps per role | Omarchy, GNOME, KDE | **full** · Settings > Default apps (`settings/pages/AppsPage.qml`; `ROLES`, `settings/scripts/arctic_settings.py:1790-1804`) | `default-app-roles`: S4 §4 fixes the browser row's key text; Email and Calendar roles have no owner → S6 WP-M3; image-editor role: defer (S6) | P2 | [O-man23] |
| G15 | Browser on a Super key | request #5 (D7), Omarchy (`Super + Shift + Return`) | **full** on `Super + W` (`dotfiles/.config/mango/arctic/apps.conf:7`) | S4 §4: `Super + B`; `Super + W` unbound; a user's own `Super + B` gets the shadow warning (S4 §14) | P0 (#5) | [O-bind-applications] |
| G16 | Chromium-family browsers follow the theme (managed policy) | Omarchy | **missing** · theme hooks cover GTK, Qt, Zed, Zen (`packaging/theme-hooks.d/`) | S2 §8.14 `chromium-theme-policy` relies on it for Chromium-runtime web apps; the hook has no owner (S2 says the theming section, S5b says S2) → S6 WP-M2 (`50-chromium`, opt-in) | P2 | [O-bin-theme-set-browser] [O-man23] [Chrome-policies] |
| G17 | Editors and terminals follow the theme | Omarchy | **full** · themegen templates for kitty, foot, alacritty, Zed, btop, yazi (`design/themegen/templates/`) | keep | have | [O-man18] |
| G18 | Service, gaming and AI app installers | Omarchy | **external-app** · the installer and Get apps catalog (`modules/`) | skip: S5b §24 (the catalog covers choosing apps) | skip | [O-man24] [O-man26] |
| G19 | Windows VM | Omarchy | **external-app** · `modules/containers/gnome-boxes`, `virt-manager` | skip: S5b §24 | skip | [O-man28] |
| G20 | Curated preinstalled apps | Omarchy | **partial** · the installer's picks; kitty, Thunar, vlc, btop in the image (`iso/kiwi/config.kiwi:75-90`) | keep | have | [O-man22] |
| G21 | Calculator with units, currency and bases; calculator key | Noctalia, Caelestia, Omarchy | **partial** · `=` arithmetic (`shell/Calc.js:1-128`) | S5b §5.7 `launcher-search-modes` (`qalc` fallback; qalculate Recommends); S4 §17 `XF86Calculator` → `arctic-launcher =` | P2 | [O-man22] [N-launcher] |
| G22 | File search | DMS, macOS Spotlight | **missing** | S5b §5.6 `launcher-search-modes` (fd-find, `~` prefix) | P2 | [D-overview] [macOS-Tahoe] |
| G23 | Web search row | DMS, end-4 | **missing** | S5b §5.8 `launcher-search-modes` (sent only on Enter) | P2 | [D-overview] |
| G24 | Window search | Noctalia, DMS | **missing** | S5b §5.4 `launcher-search-modes` (`mmsg get all-clients`, `focusid`) | P2 | [N-launcher] |
| G25 | Settings and menus searchable from the launcher | Noctalia, DMS | **missing** · Settings has its own index (`settings/SearchIndex.js`) | S5b §5.3 `launcher-search-modes` (generated `shell/assets/settings-index.js`) | P2 | [N-launcher] |
| G26 | Ranking by use, app actions; favourites and categories | Noctalia, Caelestia | **partial** · name and keyword ranking (`shell/LauncherSearch.js:1-69`) | S5b §5.9-5.10 `launcher-search-modes` (desktop actions, frecency); pinned favourites and category filters: skip (P3) | P2 | [N-launcher] |
| G27 | Launch or focus | Omarchy | **partial** · only Settings does it (`dotfiles/.local/bin/arctic-settings:48-59`) | S4 §21 `launch-or-focus`: `arctic-open --focus`; S2 §8.3 web apps focus themselves | P2 | [O-bin-launch-or-focus] |
| G28 | Emoji picker | Omarchy, Noctalia, end-4, Windows (Win + .), KDE 6.6 | **missing** · the image ships the black-and-white Noto Emoji (`iso/kiwi/config.kiwi:154`) | S4 §11 `emoji-picker`: `Super + Ctrl + E` and the `:` prefix; `google-noto-color-emoji-fonts` (correction) | P0 | [O-man07] [O-plug-README] [Windows-keys] [F44-google-noto-color-emoji-fonts] |
| G29 | Translator | Noctalia, end-4 | **missing** | skip: S5b §24 | skip | [E4-sidebarLeft] |
| G30 | Ask which browser opens a link | DMS | **missing** | skip: P3 (the browser role decides) | P3 | [D-Modals] |
| G31 | Flatpak permissions and a store | KDE 6.5 | **external-app** · Flatseal and Bazaar modules (`modules/extras/flatseal`, `modules/extras/bazaar`) | keep in the catalog; Get apps' Flathub page (S1 §3.2) is the built-in store | P3 | [KDE-6.5.0] |

#### H. Clipboard, keyboard and input

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| H1 | Clipboard history panel with images, pins, delete | Omarchy, DMS, Noctalia, end-4, KDE 6.5, macOS, Windows (Win + V) | **partial** · cliphist through fuzzel, text only (`binds.conf:23`) | S4 §12 `clipboard-panel`: `Super + V`, `arctic-clipboard`, shielded from capture | P1 | [O-man08] [N-configuration-shell] [Windows-keys] [macOS-Tahoe] |
| H2 | Secrets stay out of clipboard history | Omarchy | **partial** · cliphist 0.7.0 already skips `CLIPBOARD_STATE=sensitive` | S4 §12 and §6 (QR with `wl-copy --sensitive`); S3 §5.1 (Wi-Fi share) | P1 | [O-man08] [O-man12] [cliphist] |
| H3 | Encrypted clipboard history | Noctalia | **missing** | skip: P3 | P3 | [cliphist] |
| H4 | Universal copy and paste (`Super + C / V / X`) | Omarchy | **missing** | skip: S5b §24, S4 §3.3 (Mango has no send-shortcut dispatcher; `Super + V` is history) | skip | [O-bind-clipboard] [O-man08] |
| H5 | Clipboard survives the app closing | Noctalia | **missing** | skip: S5b §24 (wl-clip-persist is not in F44) | skip | [Mango-xdg-portals] |
| H6 | Compose key and snippets | Omarchy | **missing** · no `compose:*` in `CAPS_OPTIONS` (`settings/scripts/arctic_settings.py:2055`) | S4 §16 (Settings choice; no default `~/.XCompose`) | P2 (missed) | [O-man07] |
| H7 | Input methods (Fcitx 5) for Chinese, Japanese, Korean | Omarchy | **missing** · CJK fonts and langpacks ship, no input method | S5a §6.4 | P1 (missed) | [O-man34] [F44-fcitx5] |
| H8 | Keyboard layout on the bar; first layout on the lock screen | Omarchy, Noctalia, DMS | **missing** · layouts come from the installer (`/etc/arctic/mango/keyboard.conf`) and Settings (`settings/pages/InputPage.qml`) | S3 §5.9 `keyboard-layout-indicator` (`mmsg watch keyboardlayout`; chip only with 2+ layouts; reset on lock) | P0 | [O-man46] [O-bin-system-lock] [N-bar-widgets-lock-keys] |
| H9 | Caps Lock indicator | Noctalia, DMS | **missing** | S5b §6.4 (`bindrp=NONE,Caps_Lock,spawn,arctic-osd lock-keys`); Num Lock not shown (S5b §24) | P2 | [N-bar-widgets-lock-keys] |
| H10 | Layout switch must not swallow Alt + Shift shortcuts | Arctic (gap-verification) | **issue** · default `grp:alt_shift_toggle` (`internal/wizard/locale.go:153`, `settings/pages/InputPage.qml:36`) fires on Alt + Shift + any key under V1 keymaps | S4 §15 (no Alt + Shift binds; Settings names the keys each option takes); switching on release: defer (S4 open issue 11) | P1 (missed) | [libxkbcommon-92] |
| H11 | Keyboard, mouse and touchpad settings | Omarchy | **full** · `settings/pages/InputPage.qml:1-398` | keep; Alt-as-Super and per-app scroll speed: skip (P3) | have | [O-man34] |
| H12 | Touchpad on/off key | Omarchy | **partial** · Settings switch only | S4 §17 `hardware-keys`: `arctic-touchpad` on `XF86TouchpadToggle` (the helper keeps the state and uses `setoption disable_trackpad`, correction) | P0 | [O-man13] [O-menu-jsonc] |
| H13 | Touchscreen on/off | Omarchy | **missing** | defer (S6): no Mango dispatcher for touch devices found 🔍 (Mango 0.17.3 keys.md, `mango -p`), and no 2-in-1 in any hands-on matrix | P3 | [O-man13] [O-menu-jsonc] [Mango-0.17.3-keys] |
| H14 | Touchpad haptics strength | Omarchy | **missing** | skip: S5b §24 (device-specific) | skip | [O-man13] |
| H15 | Keyboard backlight keys with OSD | Omarchy | **missing** | S4 §17 `hardware-keys`: `arctic-osd kbd up\|down` (`bindl`) | P0 | [O-bind-media] |
| H16 | Calculator, search and power keys | Omarchy | **missing** · logind handles the power key | S4 §17 `hardware-keys` (`XF86Calculator`, `XF86Search`, `XF86PowerOff` → power menu while the shell holds a `handle-power-key` inhibitor) | P0 | [O-man22] |
| H17 | Touchpad gestures | all | **full** · `binds.conf:102-109` | keep | have | [Mango-mouse-gestures] |
| H18 | On-screen keyboard | end-4, KDE 6.6 | **missing** | skip: S5b §24 (wvkbd and squeekboard are not in F44) | skip | [E4-onScreenKeyboard] |
| H19 | Keyboard-driven pointer | wl-kbptr | **missing** | S5b §8.3 `arctic-kbptr`, `Super + Alt + K` | P2 | [F44-wl-kbptr] |
| H20 | Show key presses on screen | wshowkeys | **missing** | skip: P3, not planned (wshowkeys 🔍 how it gets input-device access on F44) | P3 | [F44-wshowkeys] |

#### I. Screenshots, recording and capture

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| I1 | Screenshot keys: area, screen, window | Omarchy, GNOME | **full** · `Print`, `Shift + Print`, `Super + Print` (`binds.conf:82-84`, `dotfiles/.local/bin/arctic-screenshot:1-40`) | keep (S4 §5.1); adds `Ctrl + Print` = area to the clipboard only | have | [O-man12] |
| I2 | Screenshot key for keyboards without Print | Windows (Win + Shift + S), request #5 | **missing** | S4 §5.1 `Super + Shift + S` (D7) | P0 (#5) | [Windows-keys] |
| I3 | Capture overlay on a frozen screen: region, window, whole monitor | Omarchy, Noctalia, DMS, GNOME 42 | **missing** · slurp region only (`binds.conf:82`) | S4 §5.3-5.4 `screenshot-editor-overlay`: `arctic-capture` + `CaptureOverlay.qml` (frozen grim frames, not ScreencopyView) | P1 | [O-man12] |
| I4 | Keyboard-driven capture picker | Omarchy | **missing** | S4 §5.4 (Enter, Ctrl + Enter, Tab, arrows, R, Esc) | P1 | [O-bind-utilities] |
| I5 | Annotate after capturing | Omarchy, Noctalia | **missing** | S4 §5.7 `screenshot-editor-overlay` (swappy 1.5.1; satty only when on PATH, it is not in F44) | P1 | [O-man12] |
| I6 | Preview and pin a screenshot | Omarchy, end-4 | **missing** | S4 §5.6 notification with the image and actions; a floating pinned image: skip (P3) | P2 | [O-man12] |
| I7 | Scrolling screenshot | DMS, Omarchy (unreleased) | **missing** | skip: S5b §24 | skip | [D-v1-6-release] |
| I8 | Copy text from the screen (OCR) | Omarchy, end-4, KDE 6.6 | **missing** | S4 §6 `ocr-qr-capture`: `Super + Ctrl + Print` (`arctic-screenshot text`; tesseract; languages from locale and layouts) | P1 | [O-man11] |
| I9 | Decode a QR code on screen | Omarchy | **missing** | S4 §6 `ocr-qr-capture`, capture menu only (python3-zxing-cpp, `zbarimg` fallback; `wl-copy --sensitive`) | P1 | [O-man12] |
| I10 | Colour picker | Omarchy, DMS, end-4, PowerToys | **missing** | S4 §7 `color-picker`: `Super + Shift + C` (`arctic-colorpick`, a loupe; hyprpicker is not in F44) | P1 | [O-bind-utilities] [D-cli-color-picker] |
| I11 | Screen recording with a bar indicator | Omarchy, Caelestia, end-4, GNOME 42, Windows Game Bar | **external-app** · OBS, Kooha, gpu-screen-recorder modules (`modules/recording/`) | S4 §8 `screen-recording`: `arctic-record`, `Super + Alt + R` and `Alt + Print` (🔍 sysrq), wf-recorder with an explicit codec (correction); indicator S3 §5.12 | P1 | [O-man12] [Windows-GameBar] |
| I12 | Desktop sound and microphone in one recording | Omarchy | **missing** | defer: S4 §8.3 (wf-recorder takes one audio device) | P2 | [O-man12] |
| I13 | Webcam overlay while recording | Omarchy | **missing** | skip: S4 §8.3, S5b §24 | skip | [O-man12] |
| I14 | Replay buffer | Noctalia | **missing** | skip: P3 (gpu-screen-recorder is Flathub-only) | P3 | [N-plugins-official-plugins] |
| I15 | Capture menu: every capture tool in one list | Omarchy | **missing** | S5b §4 `arctic-menu capture`, `Super + Ctrl + C`; rows S4 §10 | P1 | [O-man07] |
| I16 | Convert media for sharing | Omarchy | **missing** | skip: S5b §24 | skip | [O-man12] |
| I17 | Screen-share picker: monitors and windows | Omarchy, DMS | **missing** · xdg-desktop-portal-wlr falls back to slurp (outputs only) | S4 §9 `screen-share-picker`: `arctic-share-picker` + `SharePicker.qml` (monitor previews; windows listed without thumbnails) | P0 | [O-cfg-hyprland-preview-share-picker-config] [Mango-xdg-portals] [man-xdpw-5] |
| I18 | Download the video on the page | Omarchy | **missing** | skip: S5b §24 | skip | [O-man23] |
| I19 | Mic, camera and screen-sharing indicators | Noctalia, DMS, end-4, macOS, Windows, GNOME | **missing** | S3 §5.12 `privacy-indicators` (PipeWire link tracking) | P1 | [N-bar-widgets-privacy] |
| I20 | Keep secret surfaces out of captures | Mango (`shield_when_capture`) | **missing** | S3 §5.12 + S4 §12 (polkit, pairing, Wi-Fi share, clipboard layers; KeePassXC and Bitwarden windows) | P1 | [Mango-0.17.3-rules] |

#### J. Windows and workspaces

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| J1 | Tiling controls | Omarchy | **full** · `binds.conf:26-49` | keep | have | [O-bind-tiling] |
| J2 | Keyboard resizing in three step sizes | Omarchy | **partial** · `setmfact ±0.05` (`binds.conf:45-46`) | skip: S5b §24 (Hyprland-specific) | skip | [O-bind-tiling] |
| J3 | Remember and restore a window's width | Omarchy | **missing** | skip: P3 (a Hyprland scrolling-layout feature; not in the gap list) | P3 | [O-bind-tiling] |
| J4 | Layout per workspace | Omarchy | **partial** · `Super + N` cycles layouts (`binds.conf:49`) | skip: S5b §24; the layout chip (J5) shows the current one | skip | [O-man04] |
| J5 | Layout indicator and picker | DMS | **missing** | S4 §20 `window-extras` (chip from `layout_symbol`; the picker runs `setlayout`) | P2 | [Mango-ipc] |
| J6 | Window groups (tabs) | Omarchy | **missing** | S4 §20 `window-extras` (`groupjoin`, `groupleave`, `groupfocus`; `Super + Alt + arrows / G / PgUp / PgDn`) | P2 | [O-bind-tiling] |
| J7 | Pop a window out and pin it | Omarchy | **missing** | S4 §20 `window-extras`: `arctic-window pin`, `Super + Shift + P` | P2 | [O-bin-hyprland-window-pop] |
| J8 | Minimise and restore | DMS, Windows | **missing** | S4 §20 `window-extras`: `Super + H` / `Super + Shift + H` (Mango parks the window in its scratchpad pool) | P2 | [N-dock] |
| J9 | Scratch workspace and drop-down terminal | Omarchy, DMS | **missing** · `scratchpadcolor` is themed but nothing is bound (`design/themegen/templates/mango-colors.conf.tmpl:8`) | S4 §19 `dropdown-terminal`: `` Super + ` ``, `` Super + Shift + ` ``, `Super + Alt + Enter` | P1 | [O-man04] [Mango-repo] |
| J10 | Workspace navigation | Omarchy | **full** · `binds.conf:52-65`, `:100-101`, `:106-107` | keep | have | [O-bind-tiling] |
| J11 | Alt + Tab switcher | Omarchy, Windows, GNOME, Noctalia | **missing** · `Super + Tab` cycles focus without a list (`binds.conf:30-31`) | S4 §18 `alt-tab-switcher`, Mango `switcher`: `Alt + Tab`, `` Alt + ` `` backwards (not Alt + Shift + Tab, row H10), `Super + Alt + Tab` | P0 | [O-bind-tiling] [N-launcher] |
| J12 | Jump to a window by letter; back to the previous window | Mango (unbound) | **missing** | S4 §18 `Super + J` (`togglejump`), `Super + Backspace` (`focuslast`) | P2 (missed) | [Mango-0.17.3-keys] |
| J13 | Focus and move across monitors | Omarchy | **full** · `binds.conf:68-71` | keep | have | [O-bind-tiling] |
| J14 | Screen magnifier | Omarchy, KDE 6.6, COSMIC | **missing** | skip: S5b §24 (Mango has no magnifier; the Accessibility page says so) | skip | [O-bind-utilities] [KDE-6.6.0] |
| J15 | Floating rules for dialogs and small tools | Omarchy | **full** · `dotfiles/.config/mango/arctic/rules.conf:28-34` | keep; new tools add their rules in their sections | have | [O-app-system] |
| J16 | Picture-in-picture floats on every workspace | Omarchy | **full** · `rules.conf:34` | keep | have | [O-app-pip] |
| J17 | New terminal in the focused terminal's folder | Omarchy | **missing** | skip: P3 (each terminal would have to report its folder; not in the gap list) | P3 | [O-man22] |
| J18 | Overview with live window previews | end-4, DMS | **partial** · Mango's own overview on `Super + O` (`binds.conf:32`) | skip: S5b §24 (Quickshell captures single windows only on Hyprland) | skip | [QS-screencopy] [QS-docs-ScreencopyView] |
| J19 | Dock or taskbar | DMS, Noctalia, end-4, Windows | **missing** | skip: S5b §24; answered by Alt + Tab (S4 §18), the menu's Open windows branch (S5b §4.6) and window search (S5b §5.4) | skip | [N-dock] |
| J20 | Workspace names, OSD, rename | DMS | **missing** · five numbered tags | skip: P3 | P3 | [D-Modals] |
| J21 | Window details; a rule from the focused window | Caelestia, DMS | **missing** · Settings > Windows edits global options | skip: P3 | P3 | [C-repo] |
| J22 | Hot corner | Noctalia, Mango | **missing** · `enable_hotarea` unused | S4 §20 `window-extras`: Settings > Windows switch (opens Mango's overview) | P2 | [Mango-overview] |
| J23 | Look-and-feel keys: gaps, window transparency, square aspect, full-screen desktop | Omarchy | **partial** · Settings > Windows (global values) | skip: P3; game mode (D12) and hiding the bar (A21) cover the common cases | P3 | [O-bind-utilities] [O-man07] |

#### K. Theming and appearance

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| K1 | More themes, picked from a visual grid | Omarchy (22 themes), DMS | **partial** · Winter, Polar night and a wallpaper theme (`dotfiles/.local/bin/arctic-theme:4-6`) | S5b §7.2 `theme-gallery` (opt-in palettes mapped to Arctic's tokens; the accent keeps "here"); Omarchy's 22 as defaults: skip, S5b §24 | P2 | [O-themes] [O-v4.0.0] |
| K2 | One palette themes every app | Omarchy, DMS, Noctalia | **full** · themegen (`design/themegen/`) and theme hooks (`packaging/theme-hooks.d/`) | keep | have | [O-doc-theming] [N-theming-templates] |
| K3 | User templates for any app | Omarchy, Noctalia | **partial** · user themes (`~/.config/arctic/themes`) and user theme hooks | keep; S5b §14 generalises the hook contract | have | [O-man43] [N-theming-templates] |
| K4 | Install themes from a git URL | Omarchy | **missing** | S5b §7.2.5 `arctic-theme install` (an allowlist of colour files, stricter than Omarchy's denylist, correction) | P2 | [O-doc-theming] [O-v4.0.0] [O-bin-theme-set] |
| K5 | Light themes | Omarchy | **full** · Winter; `arctic-theme mode` | keep | have | [O-bin-theme-set-gnome] |
| K6 | Light and dark on a schedule | KDE 6.5, DMS, Noctalia | **missing** · `Super + Shift + T` by hand (`binds.conf:79`) | S5b §7.1 `auto-dark-schedule` (calls `arctic-theme light\|dark`, correction; `arctic-sun`) | P2 | [KDE-6.5.0] |
| K7 | Theme made from a wallpaper | Omarchy (Aether) | **full** · "Match colours to the wallpaper" (`arctic-themegen palette --from-wallpaper`) | keep | have | [O-man22] |
| K8 | Wallpaper picker; rotation; per-monitor wallpapers | Omarchy, DMS, Caelestia, Noctalia | **full** picker (`shell/Wallpapers.qml:1-317`, `Super + Shift + W`, Wallhaven) | keep; rotation S5b §15 (P3, may slip to 0.3.1); theme backgrounds in the picker S5b §7.2; per-monitor: skip (P3) | have | [O-man39] [D-overview] |
| K9 | Video wallpapers | Omarchy (unreleased), Noctalia | **missing** | skip: S5b §24 (mpvpaper is not in F44; battery) | skip | [O-man39] [N-plugins-official-plugins] |
| K10 | Login and boot-unlock screens follow the desktop | Omarchy, DMS, Noctalia | **partial** · a fixed Arctic SDDM theme (`branding/sddm/arctic/`) | the avatar reaches SDDM through AccountsService (S5a §6.3); theme sync to SDDM and Plymouth: skip (the greeter runs as `sddm` and can't read the user's theme) | P2 | [O-man41] [D-repo] |
| K11 | Monospace font switcher; Nerd Font symbols | Omarchy | **partial** · JetBrains Mono fixed; no symbols font, so yazi's icons show as boxes | S5b §7.3 `arctic-font` and a packaged symbols-only Nerd Font (none in F44) | P2 | [O-man38] |
| K12 | Personal branding (logo, screensaver, About) | Omarchy | **n/a** | skip: P3; the mark is fixed by the brand book (`design/`) | P3 | [O-man41] |
| K13 | About screen | Omarchy | **full** · `arctic-fetch`, the launcher's Fetch row (`shell/Launcher.qml:53`) | keep | have | [O-man41] |
| K14 | High contrast | Noctalia | **missing** | S5b §8.2 (a high-contrast themegen variant) | P2 | [N-configuration-shell] |

#### L. Security and privacy

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| L1 | Lock screen with password, avatar, battery, network | Omarchy | **full** · `shell/LockScreen.qml:1-310`, PAM service `shell/pam/arctic-lock` | keep; extras in L2 | have | [O-bin-system-lock] |
| L2 | Lock screen extras: media, notification count, layout chip, power buttons | GNOME 49, Omarchy, DMS, Noctalia | **missing** | S3 §5.7 (media), §5.4 (count), §5.9 (layout chip and reset); power buttons and a widget editor: skip (P3) | P2 | [N-lockscreen-widgets] |
| L3 | Fingerprint unlock and enrolment | Omarchy, Caelestia, DMS | **missing** · `pam_unix` only (`shell/pam/arctic-lock`) | S5a §6.3 `users-sign-in` (fprintd, fprintd-pam, a second PamContext, `authselect … with-fingerprint`) | P2 | [O-man37] |
| L4 | Security key (FIDO2) for sudo and polkit | Omarchy, DMS | **missing** | S5a §6.3 `users-sign-in` (`pam-u2f`, `authselect … with-pam-u2f`) | P2 | [O-man37] |
| L5 | Polkit dialog in the shell | Omarchy | **full** · `shell/PolkitDialog.qml:1-115` | keep; shielded from capture (S3 §5.12) | have | [O-plug-README] |
| L6 | Full-disk encryption by default | Omarchy | **full** · the installer encrypts by default (`internal/wizard/wizard.go:141`) | keep | have | [O-man48] |
| L7 | Time-limited passwordless sudo | Omarchy | **n/a** | skip: S5b §24 (while on, anything running as you is root) | skip | [O-man48] |
| L8 | Sudoless Docker | Omarchy | **n/a** · Arctic offers podman modules | skip: S5b §24 | skip | [O-man18] |
| L9 | SSH agent that asks once per session | Omarchy (gcr-ssh-agent) | **missing** | S5a §6.5 (gcr-ssh-agent socket) | P2 (missed) | [O-man18] [O-man48] |
| L10 | Keyring unlocked at login | Omarchy | **full** · gnome-keyring and gnome-keyring-pam (`packaging/arctic-linux.spec:457-458`) | keep | have | [O-cfg-chromium-flags.conf] |
| L11 | Keyring health check | Noctalia, end-4 | **missing** | skip: P3 | P3 | [N-configuration-secret-service] |
| L12 | Change password, disk passphrase and picture | Omarchy, DMS | **missing** · set in the installer; `~/.face` by hand | S5a §6.3 `users-sign-in`: Settings > Users and sign-in | P2 | [O-menu-jsonc] [O-man48] [D-UsersService] |
| L13 | Ask before a new USB device works | KDE 6.6 | **missing** | skip: S5b §24 | skip | [KDE-6.6.0] |
| L14 | Reset the computer | Omarchy | **missing** | skip: S5b §24 (Limine-specific) | skip | [O-man48] |
| L15 | Boot straight to the unlock screen (EFI entry) | Omarchy | **n/a** · GRUB | skip: S5b §24 | skip | [O-man47] |

#### M. Updates and recovery

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| M1 | One guarded update | Omarchy | **full** · `arctic-update` (offline dnf5; snapper around every transaction, `packaging/updates/snapper.actions`) | keep | have | [O-bin-update] |
| M2 | Flathub and firmware updates next to dnf | Omarchy, DMS | **partial** · dnf only; `docs/wiki/Updates.md:232-239` says to run `flatpak update` | S5a §7.1 + S1 §6.14 `unified-updates` (daily timers for system and per-user Flatpaks; fwupd list and install) | P1 | [O-man30] [D-cli-system-updater] |
| M3 | Package-manager guard | Omarchy | **n/a** · snapper runs on every dnf transaction | skip: S5b §24 | skip | [O-man30] |
| M4 | Release channels | Omarchy | **full** · stable and testing (`arctic-update channel`) | keep | have | [O-man30] |
| M5 | Snapshots before updates; undo from Settings | Omarchy | **partial** · snapper pre/post; restore from the command line (`docs/wiki/Updates.md:170-230`) | S5a §7.2 `snapshots-ui` (list, undo, take one now); booting into a snapshot: skip (grub-btrfs is not in F44) | P2 | [O-man47] |
| M6 | Reset a configuration to defaults | Omarchy | **partial** · Settings `reset`, `undo` and backups (`settings/scripts/arctic_settings.py:2546-2567`) | keep | have | [O-man31] |
| M7 | What's new after an update | DMS | **missing** | S5a §7.3 `WhatsNew.qml` | P2 | [D-Modals] |
| M8 | Upgrade to the next Fedora release | Fedora (dnf system-upgrade) | **missing** · `docs/PLAN.md` §10 says later | S5a §7.3 `fedora-upgrade-whats-new` (`arctic-update upgrade`; the helper's ownership check extended, correction) | P2 | [Fedora-upgrade-docs] |
| M9 | Personal backups | GNOME (Déjà Dup) | **external-app** · Pika Backup module (`modules/extras/pika-backup`) | keep in the catalog | P3 | [F44-deja-dup] |

#### N. System, session and hardware

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| N1 | Printing | Omarchy, DMS, GNOME, KDE | **missing** · no CUPS; ghostscript excluded (`iso/kiwi/config.kiwi:183`) | S5a §8.1 `printing` (cups, cups-filters, ghostscript, ipp-usb, avahi, nss-mdns, cups-pk-helper, system-config-printer; Printers page) | P1 | [O-man46] [D-CupsService] |
| N2 | Scanning | GNOME, KDE | **missing** | S5a §8.1 (sane-airscan, simple-scan) | P2 (missed) | [F44-sane-airscan] |
| N3 | USB drives mount; eject from the bar | Omarchy, DMS | **missing** · Thunar mounts on click (only `udisks2-btrfs` in `iso/kiwi/config.kiwi:147`) | S5a §8.2 `removable-drives` (`scripts/drives.py` over Gio; a bar item while something is mounted) | P1 | [O-man46] [N-repo] |
| N4 | Phones, cameras and network shares in Files | Omarchy | **missing** · Thunar pulls only `gvfs` | S5a §8.2 (gvfs-mtp, gvfs-afc, gvfs-gphoto2, gvfs-smb) | P2 (missed) | [O-inst-omarchy-base.packages] [F44-Thunar] |
| N5 | Time zone, automatic time, 24/12-hour clock | Omarchy, DMS | **missing** · set in the installer only (`internal/wizard/locale.go`); the clock hard-codes `hh:mm` (`shell/Bar.qml:90`) | S5a §6.2 `date-time-region` (Settings > Date and time) | P1 | [O-man46] [O-menu-jsonc] |
| N6 | System language | DMS, GNOME | **missing** | S5a §6.2; a per-user language: defer, S5a §17 | P1 | [O-menu-jsonc] |
| N7 | Create users, admin rights | DMS | **missing** | skip: P3 (Settings > Users edits the signed-in user, S5a §6.3) | P3 | [D-UsersService] |
| N8 | Apps' "Start on login" works (XDG autostart) | GNOME, KDE | **missing** · `~/.config/autostart` is ignored (`settings/pages/StartupPage.qml:1-3`) | S5a §6.1 `xdg-autostart`: `mango-session.target` drop-in `Wants=xdg-desktop-autostart.target` (correction: the target refuses manual start) | P1 | [systemd-xdg-autostart] [systemd-special] |
| N9 | Restart sound, Wi-Fi, Bluetooth or the shell | Omarchy, DMS | **missing** | S5a §6.6 `system-tools`: `arctic-restart sound\|wifi\|bluetooth\|shell` (menu and Settings rows) | P2 | [O-man45] [O-menu-jsonc] [D-cli-doctor] |
| N10 | Diagnostics bundle | Omarchy, DMS (`dms doctor`) | **partial** · Settings > About "Report a problem" | keep | P3 | [O-man45] [D-cli-doctor] |
| N11 | Task manager key | Windows (Ctrl + Shift + Esc), Omarchy (`Super + Ctrl + T`) | **external-app** · btop is a Recommends with no key | S5a §6.6 `system-tools`: `Ctrl + Shift + Esc` (Activity); S5b §11 System panel (top processes, end or force quit) | P2 | [O-man21] [D-ProcessList] [Windows-keys] |
| N12 | CPU, memory and temperature on the bar | Noctalia, DMS | **missing** | S5b §11 `SystemItem.qml` (off by default; numbers, no graphs) | P2 (missed) | [N-bar-widgets-sysmon] |
| N13 | Disk usage | DMS | **missing** | S5b §11 disk rows (`/`, `/home`); an analyser is a catalog app | P3 | [D-Widgets] |
| N14 | Hardware detection and quirk fixes | Omarchy | **partial** · hardware-detected driver modules (`modules/drivers/`) | skip: S5b §24 (device-specific) | skip | [O-inst-hardware] |
| N15 | Unattended install | Omarchy | **full** · `arctic-install unattended --profile FILE` (`cmd/arctic-install/main.go:47`) | keep | have | [O-man51] |
| N16 | Install now, the owner sets up at first boot | Omarchy | **missing** | skip: S5b §24 (installer scope) | skip | [O-man02] |
| N17 | Terminal toolbelt with keys (lazydocker, disk usage, music) | Omarchy | **external-app** · catalog modules (lazygit and others) | skip: P3 beyond the Activity key (N11) | P3 | [O-man21] |
| N18 | Apps can't register global shortcuts | GNOME 48 (portal) | **n/a** · xdg-desktop-portal-wlr has no GlobalShortcuts portal | constraint: app shortcuts are Mango binds (Settings > Shortcuts) | n/a | [GNOME-48] |
| N19 | Quickshell version | Quickshell 0.3.1 | **snapshot** · F44 `quickshell 0.2.1^git20260209.dacfa9d`, required unversioned (`packaging/arctic-linux.spec:243`, `:263`, `:292`) | defer: S3 §16 (D5); follow-up `packaging/quickshell.spec` with `-DCRASH_HANDLER=OFF` or a vendored cpptrace (correction). Corrects the research: the snapshot lacks Networking PSK support | P1 | [QS-v0.3.1] [F44-quickshell] |

#### O. Clock, calendar and everyday tools

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| O1 | Calendar on the clock | Omarchy, Noctalia, DMS, Windows (Win + N), GNOME | **missing** · plain text (`shell/Bar.qml:88-96`); the waybar fallback has a tooltip calendar (`dotfiles/.config/waybar/config.jsonc:47-57`) | S3 §5.5 `calendar-popover`, `Super + Ctrl + T` (ISO weeks; today in accent-soft = "here") | P0 | [O-man46] [N-services-calendar] [Windows-keys] |
| O2 | Calendar events (CalDAV, khal) | Noctalia, DMS | **missing** | defer: S3 §5.5 (room left in the panel; not in 0.3.0) | P2 | [N-services-calendar] |
| O3 | Clock formats (12/24 hours, date on the bar) | Omarchy | **missing** · `ddd d MMM · hh:mm` fixed (`shell/Bar.qml:90`) | S5a §6.2 (clock rows written to `shell.json`) | P1 | [O-man46] |
| O4 | World clock | Omarchy (Elsewhen), Noctalia, KDE 6.7 | **missing** | skip: S5b §24 | skip | [O-doc-elsewhen] |
| O5 | Weather | Omarchy, DMS, Noctalia, Caelestia | **missing** | S5b §12 `weather` (Open-Meteo, off by default, no IP geolocation; Omarchy uses Open-Meteo only for Elsewhen, correction) | P2 | [O-man10] [N-services-weather] |
| O6 | Reminders and timers | Omarchy, Noctalia, end-4 | **missing** | S5b §13 `reminders`: `arctic-remind` (systemd-run user timers), `Super + Ctrl + R`; pomodoro and stopwatch: skip (P3) | P2 | [O-man09] |
| O7 | To-do list, notepad | end-4, DMS | **missing** | skip: P3 (apps do this; Get apps installs them) | P3 | [D-Notepad] |
| O8 | Screen time, parental controls | Noctalia, GNOME 48/50 | **missing** | skip: S5b §24 | skip | [N-control-center] |
| O9 | QR code generator | DMS | **partial** · qrencode is used for Wi-Fi sharing only (S3 §5.1) | skip: P3 | P3 | [D-cli-qr] |
| O10 | Dropbox and Sunshine panels | Omarchy | **missing** | skip: S5b §24 | skip | [O-man05] |
| O11 | AI chat sidebar | end-4 | **missing** | skip: S5b §24 (privacy: end-4's Lens flow uploads screenshots to uguu.se) | skip | [E4-services] |
| O12 | AI coding-agent usage panel | Omarchy | **missing** | skip: S5b §24 | skip | [O-man17] [O-plug-agents] |
| O13 | Default coding agent; agent skill | Omarchy | **missing** | skip: S5b §24 | skip | [O-man17] |
| O14 | AI crash diagnosis | Omarchy | **missing** | skip: S5b §24 | skip | [O-man17] |
| O15 | AI desktop apps and local models | Omarchy | **external-app** · Flathub apps through Get apps | skip: S5b §24 | skip | [O-man17] |
| O16 | Dictation, live captions | Omarchy (Voxtype), Windows | **missing** | defer: S5b §16 (no Fedora package for Voxtype; a whisper-cpp model needs consent and storage); `Super + Ctrl + X` stays free | P2 | [O-man11] |

#### P. Accessibility

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| P1 | Accessibility page | GNOME, KDE, Windows, macOS | **partial** · motion, text size, pointer in Appearance (`settings/pages/AppearancePage.qml:450-519`); `design/exports/mango-arctic.conf:33` names a page that doesn't exist | S5b §8.1 `accessibility-page` (with "Not available yet" rows) | P2 | repo |
| P2 | Reduce motion | GNOME, macOS | **full** · `dotfiles/.local/bin/arctic-motion` | keep; moves to the Accessibility page | have | repo |
| P3 | Screen reader | GNOME, KDE | **missing** | skip: S5b §24 (Orca unreliable on wlroots; a "Not available yet" row) | skip | [a11y-notes] |
| P4 | Colour filters; sticky and slow keys | KDE 6.6 | **missing** | skip: S5b §24 (gamma control is per channel; no AccessX in Mango 🔍) | skip | [KDE-6.6.0] |

#### Q. Onboarding and help

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| Q1 | Shortcut sheet built from the real binds, searchable | Omarchy, DMS | **partial** · static `keys.txt` (`shell/KeysSheet.qml:8-36`, `dotfiles/.local/share/arctic/keys.txt:1-50`) | S4 §13 `generated-keys-sheet` (`#:` comments, `arctic-keys --json`) | P1 | [O-man07] [D-cli-keybinds-cheatsheets] |
| Q2 | Warn when a new default key hides a user's own | Arctic (gap-verification) | **missing** · Mango uses the first bind it reads (`dotfiles/.config/mango/config.conf:13-17`, `:26-32`) | S4 §14 (Settings > Shortcuts, a one-time login notice) | P1 (missed) | repo |
| Q3 | First-login welcome and first-boot progress | Omarchy, KDE 6.6 | **partial** · live-USB welcome only (`dotfiles/.local/bin/arctic-welcome:10`); `arctic-firstboot` is silent | S5b §9 `first-login-welcome` (a status file the shell reads, correction) | P1 | [O-bin-provision-first-run] [KDE-6.6.0] |
| Q4 | "Coming from Windows or macOS" guide | Omarchy | **missing** | S5b §21 `docs/wiki/Coming-from-Windows-or-macOS.md` | P2 | [O-man03] |
| Q5 | "Coming from Omarchy" guide (keys that differ, what Arctic skipped) | this matrix | **missing** | S6 WP-M1 `docs/wiki/Coming-from-Omarchy.md` | P2 | repo |

#### R. Development tools

| # | Feature | From | Arctic today (0.2.1) | Plan decision (0.3.0) | Pri | Sources |
|---|---|---|---|---|---|---|
| R1 | Language installers (mise) | Omarchy | **missing** · Nix is always installed (`modules/_system/nix/module.toml`) | skip: S5b §24 (mise is not in F44) | skip | [O-bin-install-dev-env] |
| R2 | Docker databases | Omarchy | **missing** · podman modules | skip: S5b §24 | skip | [O-bin-install-docker-dbs] |
| R3 | tmux setup and dev layouts | Omarchy | **missing** | skip: P3 (not in the gap list) | P3 | [O-man15] |
| R4 | Shell functions and aliases | Omarchy | **partial** · zsh setup (`dotfiles/.zshrc`) | skip: P3 | P3 | [O-man20] |
| R5 | Neovim distribution, Starship prompt | Omarchy | **missing** · Zed is the default editor; zsh prompt | skip: P3 | P3 | [O-man16] |

---

### 6. Corrections from `gap-verification.json` that change rows

D8 asks for every correction to be applied. The sections apply them in their designs; this table
shows where each one lands, so a reader of the matrix sees the corrected fact, not the gap list's.

| Gap item (verdict) | What was wrong or incomplete | Corrected fact | Rows | Applied in |
|---|---|---|---|---|
| `alt-tab-switcher` (wrong) | `Alt + Shift + Tab` for backwards | Clashes with the default `grp:alt_shift_toggle`: every press also flips the layout (libxkbcommon #92). Backwards is `` Alt + ` ``; `switcher` goes into `DISPATCHERS` (`arctic_settings.py:792`); the switcher has no animation code | J11, H10 | S4 §18, §15 |
| `display-mode-mirror` (wrong, both checks) | "Mango has no lid binds; watch logind's LidClosed" | Mango 0.17.3 has `switchbind=fold\|unfold,<dispatcher>` | D3, D4 | S5a §4.5, §5.2 |
| `user-hooks` (wrong) | a new `~/.config/arctic/hooks/theme-set.d` | theme hooks already exist (`arctic-theme:26-30`, `:53`); generalise that contract, don't add a parallel one | A31 | S5b §14 |
| `low-battery-warnings` (wrong) | "Auto = HybridSleep, then Hibernate, then PowerOff"; "Arctic will hibernate at 2 %" | UPower 1.91.4 `Auto` calls logind `Sleep()`, which follows `SleepOperation=`; Arctic has no swap, so it is usually suspend. The text names the real action; thresholds come from `WarningLevel` over D-Bus | E9, E5 | S3 §5.6, S5a §4.2 |
| `media-controls` (wrong) | the click mapping was credited to Omarchy | Omarchy: left = play/pause, middle = next, right = popup. Arctic keeps its own mapping without the credit | C13 | S3 §5.7 |
| `emoji-picker` (wrong) | `google-noto-emoji-fonts` | that is the black-and-white font; the colour one is `google-noto-color-emoji-fonts` (fix `iso/kiwi/config.kiwi:154` too); also parse `annotationsDerived` | G28 | S4 §11 |
| `notification-center` (wrong) | "Omarchy lets critical notifications through DND" | Omarchy lets through only its own action toasts and `notify-send` criticals, because chat apps abuse critical. Arctic's punch-through (`x-arctic-alert`) is Arctic's own rule. mako is a hard Requires in two subpackages (spec `:177`, `:427`) | F1, F3 | S3 §5.4 |
| `control-center` (wrong) | "cycle `powerprofilesctl`" | tuned-ppd ships no `powerprofilesctl` (`arctic_settings.py:1690`); use Quickshell `PowerProfiles` or D-Bus. pavucontrol, blueman and network-manager-applet move from Requires to Recommends (spec `:439-442`) | E7, A14, C1 | S3 §5.6, §5.11, §11.2 |
| `xdg-autostart` (wrong) | `systemctl --user start xdg-desktop-autostart.target` | the target has `RefuseManualStart=yes`; use a `mango-session.target` drop-in with `Wants=`; `XDG_CURRENT_DESKTOP=mango` | N8 | S5a §6.1 |
| `night-light` | `-d 1800`, "send SIGUSR1 twice" | `-d` works only with manual times; SIGUSR1 cycles modes and the state can't be read, so restart wlsunset with new arguments | D1 | S5a §5.1 |
| `quickshell-031` | "the snapshot has Networking with PSK" (desktop research) | the snapshot lacks PSK, saved connections and wired devices; packaging 0.3.x needs `-DCRASH_HANDLER=OFF` or a vendored cpptrace | N19, B1, B7 | S3 §2.6, §16 |
| `screen-recording` | "gpu-screen-recorder when installed"; libx264 | the module is a Flatpak; Fedora's wf-recorder defaults to VP9 (ffmpeg-free); pass the codec | I11 | S4 §8 |
| `ocr-qr-capture` | zbar flags | `zbarimg -q --raw -Sdisable -Sqrcode.enable`; QR copied with `--sensitive` | I9, H2 | S4 §6 |
| `hardware-keys` | touchpad state; "GNOME opens a power menu" | keep the touchpad state in the helper (`setoption disable_trackpad`); GNOME's default is suspend; the inhibitor approach is valid | H12, H16 | S4 §17 |
| `external-brightness-ddc` | ship modules-load and udev files | Fedora's ddcutil already ships them | D2 | S3 §5.8 |
| `auto-dark-schedule` | `arctic-theme mode light\|dark` | that only sets the wallpaper-colour mode; call `arctic-theme light\|dark` | K6 | S5b §7.1 |
| `theme-gallery` | Omarchy's denylist | use an allowlist of colour files (stricter) | K4 | S5b §7.2 |
| `first-login-welcome` | `arctic-welcome --first-login`; notify from firstboot | `arctic-welcome` exits on installed systems (`:10`); the system service writes a status file the shell reads | Q3 | S5b §9 |
| `fedora-upgrade-whats-new` | run `dnf system-upgrade` | `arctic-update-helper` ignores transactions whose releasever differs; extend it | M8 | S5a §7.3 |
| `firewall-ssh` | "firewalld only through @core, unverified" | firewalld is enabled by preset (`90-default.preset:70`); sshd is off on purpose (`80-arctic.preset:41-45`); the firewalld service is `kdeconnect` | B22, B23, B20 | S5a §8.3 |
| `printing` | Omarchy's "security" reason | Omarchy's FAQ gives none; ghostscript is mandatory for cups-filters; add cups-pk-helper | N1 | S5a §8.1 |
| `power-menu-extras` | Hibernate row | rarely shown (no swap); `killclient client,<id>` without `force` is a polite close | E2, E4 | S5a §4.6 |
| `window-extras` | group drawing unverified | Mango draws a group bar; `minimized` parks windows in the scratchpad pool | J6, J8 | S4 §20 |
| `launch-or-focus`, `launcher-search-modes` | focus dispatch unverified | `mmsg dispatch focusid client,<id>`, already used in `arctic-settings:48-59` | G24, G27 | S4 §21, S5b §5.4 |
| `keyboard-layout-indicator` | `input.conf:4` | real layouts are in `/etc/arctic/mango/keyboard.conf`; IPC reports the layout name, not an index | H8 | S3 §5.9 |
| `weather` | Open-Meteo credited to Omarchy's bar | Omarchy's bar uses wttr.in; Open-Meteo backs only Elsewhen | O5 | S5b §12 |
| `game-mode` | — | Omarchy's new no-animations mode in VMs (b18ab49) belongs with it | D11, D12 | S5a §5.3 |
| `calendar-popover` | "no calendar anywhere" | the waybar fallback already shows one in the clock tooltip | O1 | S3 §5.5 |
| `unified-updates` | fwupd presence unverified | fwupd is a default of @core; `fwupdmgr` authorises through polkit itself | M2 | S5a §7.1 |
| `battery-health-limit` | "80 %" | the limit is UPower's `ChargeEndThreshold` (or the firmware's); polkit for `EnableChargeThreshold` 🔍 | E10 | S3 §5.6, S5a §4.3 |

Line numbers in the verification that are off in the repository: the screenshot notification is at
`dotfiles/.local/bin/arctic-screenshot:40` (the file has 40 lines), not `:100` (row F8).

---

### 7. What the matrix found across sections

#### 7.1 Work no section owns (becomes §9)

| Row | Work | Why it has no owner |
|---|---|---|
| G16 | `packaging/theme-hooks.d/50-chromium` and its root helper | S2 §8.14 and §10.6 say "the theming section" writes it; S5b (the theming section) lists `chromium-theme-policy` as owned by S2 |
| G14 | Email and Calendar roles in Settings > Default apps | S2 §8.15 says "the default-apps section"; there is no such section, and S5b lists `default-app-roles` as S2's |
| Q5 | A "Coming from Omarchy" page | new: the matrix is the source for it; S5b §21 writes only "Coming from Windows or macOS" |

#### 7.2 Where sections disagree

1. **Bar keyboard focus.** S3 §8.1 and §8.3 bind `Super + Alt + B` (and the implementation rules
   give it to stream 3a). S4 §3.2 row 41 moves it to `Super + Alt + P`, because Settings' empty
   state suggests `Super + Alt + B` for the user's own shortcut
   (`settings/pages/ShortcutsPage.qml:40` ✅) and S4's `test_user_example_keys_stay_free` asserts it
   is unbound. Both can't merge: one of the two CI tests fails. Recommendation in §11, issue 1.
2. **Helper names.** The implementation rules' cross-stream contracts (scratchpad
   `impl-rules.md`) name `arctic-keep-awake`, `arctic-ocr [--qr]` and `arctic-sysmon`; the drafts name `arctic-awake` (S5a §4.1.3), `arctic-screenshot text|qr`
   (S4 §6) and no `arctic-sysmon` (S5a §6.6 opens btop on `Ctrl + Shift + Esc`, S5b §11 has the
   System panel). The command menu (S5b), the Quick Settings tiles (S3) and `keys.txt` call these
   by name, so one name each has to be fixed before the branches are joined (§11, issue 2).
3. **`shell.json` key spelling.** S5b uses camelCase (`barSystem`), S5a snake_case, S3 left it
   open. One rule has to go into BUILD-SPEC §3 (§11, issue 3).

The matrix itself uses the drafts' names and keys.

#### 7.3 Decisions made only here

These rows had no decision in any section; the matrix decides them so nothing is left open. The
lead can promote any of them to a later release.

| Rows | Decision | Reason |
|---|---|---|
| E16 | defer | apps in their own systemd scopes need `systemd-run --user --scope` in `arctic-open`, the launcher's `execute()` path and every spawn bind; not in the gap list; 🔍 what oomd kills today |
| H13 | defer | no Mango dispatcher for touch devices found; no 2-in-1 in any hands-on matrix |
| D5 | skip | Mango applies a saved `monitorrule` when that output connects, which covers docked/undocked 🔍 |
| B16 | no change | Fedora's systemd-rfkill already restores the radio state 🔍 |
| B13, C6, C9-C11, C15, D9, F6, G30, H3, H20, I14, J3, J17, J20, J21, J23, K12, L11, N7, O7, O9, R3-R5 | skip (P3) | small, niche or an app's job; each row gives its reason |
| A25 (title), A26, K10 (SDDM theme sync), I6 (pinned image), L2 (power buttons) | skip that part | calm bar; the greeter can't read the user's theme; P3 extras |
| G14 (image-editor role) | defer | the only consumer would be the screenshot Edit action, which S4 §5.7 already resolves (satty, then swappy); a role that one action uses adds a Settings row with no other effect |

---

### 8. Keyboard behaviour

The matrix adds no key. Every new or changed key in 0.3.0 is in S4 §3.2 (rows 1-55) and S5b §3
(rows 56-57); the work packages in §9 add none.

#### 8.1 Omarchy keys an Omarchy user will reach for

Checked against Omarchy's `default/hypr/bindings/*.lua` at `b18ab49` ✅ and against Arctic's 0.3.0
keys as S4 §3.2 and S5b §3 define them. This is the table §9.1 puts on the wiki.

| Omarchy key | Omarchy does | Same thing in Arctic 0.3.0 | That key in Arctic 0.3.0 |
|---|---|---|---|
| `Super + Space` | Omarchy menu | `Super + Alt + Space` (command menu) | launcher |
| `Super + Alt + Space` | apps menu | `Super + Space` | command menu |
| `Super + K` | shortcut sheet | `Super + /` | free |
| `Super + /` | monitor scaling up | Settings > Displays | shortcut sheet |
| `Super + L` | workspace layout | `Super + N` (next Mango layout) | lock |
| `Super + Ctrl + L` | lock | `Super + L` | free |
| `Super + W`, `Super + Q` | close window | `Super + Q` | `Super + W` free (D7) |
| `Super + Shift + Return`, `Super + Shift + B` | browser | `Super + B` | free |
| `Super + S` | scratchpad | `` Super + ` `` | Settings |
| `Super + C / V / X / A` | copy, paste, cut, select all everywhere | not in Arctic (H4) | `Super + V` clipboard history, `Super + A` Quick Settings, `Super + C` and `Super + X` free |
| `Super + Ctrl + V` | clipboard history | `Super + V` | free |
| `Super + ,` / `Super + Shift + ,` | dismiss / dismiss all | `Super + Delete` / `Super + Shift + Delete` | focus / move to the left monitor |
| `Super + Shift + Alt + ,` | notification history | `Super + Alt + N` | unbound (holds Alt + Shift) |
| `Super + Ctrl + ,` | silence notifications | `Super + Shift + N` | free |
| `Super + Print` | colour picker | `Super + Shift + C` | window screenshot |
| `Print` | screenshot overlay | `Print` (area), `Shift + Print`, `Super + Print`, `Super + Shift + S` | — |
| `Super + Ctrl + T` | Activity (btop) | `Ctrl + Shift + Esc` | calendar |
| `Super + Ctrl + Alt + D` | calendar | `Super + Ctrl + T` | free |
| `Super + Ctrl + Alt + T / B / W` | time, battery, weather notices | not in Arctic (A23) | free |
| `Super + Shift + N` | editor | `Super + E` | do not disturb |
| `Super + Shift + F` | file manager | `Super + F` | files in a terminal (yazi) |
| `Super + F` | full screen | `Super + Shift + M` | files |
| `Super + Tab` | next workspace | `Super + Page Down` | next window on the workspace |
| `Super + J` | toggle split | none (Mango layouts differ) | jump to a window |
| `Super + P` | pseudo-tile | none | display mode |
| `Super + O` | pop a window out | `Super + Shift + P` | overview |
| `Super + G` | group windows | `Super + Alt + arrows` | free |
| `Super + Backspace` | window transparency | not in Arctic (J23) | previous window |
| `Super + Ctrl + Delete` | laptop screen on/off | `Super + P` | free |
| `Super + Ctrl + Z` | zoom | not in Arctic (J14) | free |
| `Super + Ctrl + X` | dictation | not in 0.3.0 (O16) | free, kept for it |
| `Super + Ctrl + Q` | calculator | `Super + Space` then `=`, or the Calculator key | free |
| `Super + Ctrl + O` / `Super + Ctrl + H` | toggle menu / hardware menu | `Super + A`; the command menu's Toggles branch | free |
| `Super + Shift + A / C / E / P / S / W …` | web apps and Omarchy apps | your own keys (S2 §9.4, Settings > Shortcuts) | Get apps, colour picker, free, pin window, area screenshot, wallpapers |

The same in both: `Super + Return`, `Super + Escape` (power menu), the power key, `Super + T`
(float), `Alt + Tab`, `Alt + Print`, `Super + Ctrl + Print`, `Super + Ctrl + C / E / S / R / N / I`,
`Super + Ctrl + A / W / B / D / P`, `Super + Alt + arrows` and `Super + Alt + G` (groups),
`Super + Shift + Space`, `Shift + Mute`, `` Super + ` `` and `` Super + Shift + ` ``, `Super + Alt + ,`.

#### 8.2 Keys inside surfaces

None new. The web-app window keys are S2 §9; the menu keys S3 §8.2; the command menu S5b §4.8.

---

### 9. Work packages owned by this section

#### 9.1 WP-M1: `docs/wiki/Coming-from-Omarchy.md` and its key check

**What.** A wiki page for people who know Omarchy, built from this matrix. The user asked for the
Omarchy research to be in the plan; this page is where it reaches users.

**New file `docs/wiki/Coming-from-Omarchy.md`**, in the wiki's voice (see
`docs/wiki/Keyboard-Shortcuts.md`):

1. `## What's the same` — one Quickshell process; the panel keys; capture, emoji, share,
   reminder, night-light and keep-awake keys; the scratchpad on `` Super + ` ``; web apps; the menu
   tree (as the command menu).
2. `## Keys that differ` — the table of §8.1, verbatim.
3. `## What Arctic does its own way` — Fedora with dnf and Flathub instead of pacman and the AUR
   (Get apps, S1); Mango instead of Hyprland (layouts on `Super + N`, the overview on `Super + O`);
   snapper around every dnf transaction and undo from Settings instead of Limine boot entries
   (M5); the Settings app instead of opening config files; web apps in WebKitGTK with a Chromium
   fallback (S2).
4. `## Not in Arctic, and why` — one line per skipped or deferred row a migrating user would look
   for (H4, J14, A22, A29, L7, E5, O11-O16, K9, B13, G8), with its reason from §5.
5. `## Making Arctic feel more like Omarchy` — a `~/.config/mango/user.conf` block with keys that
   are free in 0.3.0:

   ```
   # Omarchy habits, added to Arctic's own keys (Mango uses the first bind for a key,
   # so these work only on keys Arctic leaves free).
   bind=SUPER,k,spawn,arctic-keys
   bind=SUPER+CTRL,l,spawn,arctic-lock
   bind=SUPER+CTRL,v,spawn,arctic-clipboard
   bind=SUPER+CTRL+ALT,d,spawn,arctic-shell-ipc panel toggle calendar
   ```

   `arctic-clipboard` is S4 §12's helper; the `panel` IPC is S3 §7.1's.

**Changed files**

| File | Change |
|---|---|
| `docs/wiki/_Sidebar.md` | a "Coming from Omarchy" link next to S5b's "Coming from Windows or macOS" |
| `docs/wiki/Keyboard-Shortcuts.md` | one line under the title: "Used Omarchy before? [Coming from Omarchy](Coming-from-Omarchy) lists the keys that differ." |
| `docs/wiki/Coming-from-Windows-or-macOS.md` (S5b's new page) | a "See also" line |

**Test: `settings/tests/test_wiki_keys.py`** (new; found by the `settings/tests` discovery step,
`.github/workflows/ci.yml:89-90`, and by the spec's build check, `packaging/arctic-linux.spec:824`):

- `load_binds()`: reads every `bind*=` line of `dotfiles/.config/mango/arctic/apps.conf` and
  `binds.conf` in `keymode=default` and `common` and normalises it to
  `(frozenset(mods), key.lower())`, with `NONE` read as no modifier and `code:49` as `grave`.
  About 25 lines of its own, so the test does not depend on another test module.
- `human_to_combo("Super + Ctrl + N")`: `Super`→`SUPER`, `Ctrl`→`CTRL`, `Alt`→`ALT`,
  `Shift`→`SHIFT`; keys: letters lower-cased, `Enter`/`Return`→`return`, `Esc`→`escape`,
  `/`→`slash`, `,`→`comma`, `` ` ``→`grave`, `Space`→`space`, `Backspace`→`backspace`,
  `Print`→`print`, `Delete`→`delete`, `Tab`→`tab`, `Page Down`→`page_down`,
  `Mute`→`xf86audiomute`.
- Cell parsing: only code spans count. `Super + Ctrl + Alt + T / B / W` expands the last key over
  the slash list (three combos); `Super + Alt + arrows` expands to Left, Right, Up and Down; a
  span with words after the combo (`Super + Space` then `=`) counts the combo only; a span that
  doesn't parse ("Settings > Displays" is not even a code span) is ignored.
- `test_arctic_keys_in_the_omarchy_table_are_bound`: every combo in the table's third column is
  bound in Arctic's files.
- `test_free_keys_in_the_omarchy_table_are_free`: in every row whose fourth column starts with the
  word "free", every combo in the first column is unbound in Arctic's files.
- `test_user_conf_example_uses_free_keys`: every `bind=` line in the page's code block is unbound
  in Arctic's files (otherwise Mango would ignore it, `config.conf:13-17`).
- Each test calls `skipTest` when `docs/wiki/Coming-from-Omarchy.md` is absent, so a source
  tarball without `docs/` still builds.

**Depends on** S4 K1 (the new `binds.conf`), S3 L (panel keys), S5b X1 (command menu key), and
the §11 issue 1 decision on the bar-focus key.

#### 9.2 WP-M2: Chromium-family browsers follow the Arctic theme (`chromium-theme-policy`, hook part)

**What.** With a switch on, Chromium (and Google Chrome and Brave when installed as vendor RPMs)
takes a seed colour from the Arctic theme and follows light and dark, through Chromium's managed
policies — Omarchy's `omarchy-theme-set-browser` ✅. S2's Chromium-runtime web apps inherit it
(S2 §8.14). Off by default, like the Zen accent (`arctic-theme zen on|off`,
`dotfiles/.local/bin/arctic-theme:577-588`).

**Colour (D9).** The seed is the theme's `ground` (Winter `#eef2f5`), never `accent`: a seed
colours the whole browser frame, and amber is only for "here". Omarchy also seeds with each theme's
background (`themes/*/chromium.theme`, e.g. Flexoki Light `242,240,229`) ✅. 🔍 Chromium's palette
from `ground` reads as Winter and Polar night (screenshots of Chromium in both themes).

**Processes**

```
arctic-theme set|light|dark|toggle → run_hooks → /usr/share/arctic/theme-hooks.d/50-chromium
    "browser_theme": false (default) → if an arctic-theme.json policy exists: pkexec … clear
    "browser_theme": true            → read $ARCTIC_THEME_DIR/chromium/policy.json
                                       (fallback: palette.json colors["ground"])
                                     → if every installed file already has it: nothing
                                     → pkexec /usr/libexec/arctic/arctic-browser-policy set '#eef2f5' device
                                     → each running browser (pgrep -x): <binary> --refresh-platform-policy
                                       --no-startup-window, started detached so the hook ends
                                       within arctic-theme's 5 s hook limit (arctic-theme:62)
```

**Data formats and commands**

- Rendered per theme by themegen (new template
  `design/themegen/templates/chromium/policy.json.tmpl`):

  ```json
  {"BrowserThemeColor": "{{ground|hex}}", "BrowserColorScheme": "device"}
  ```

  The same two policies and values Omarchy's `omarchy-theme-set-browser` writes ✅; 🔍 both are in
  Fedora 44's Chromium (`chrome://policy` shows them as valid).
- `arctic-browser-policy` (new, python3 standard library, run as root by pkexec; argv lists, no
  shell; logs one line with `logger -t arctic-browser-policy`):

  ```
  arctic-browser-policy set COLOUR SCHEME   COLOUR ^#[0-9a-f]{6}$, SCHEME device|light|dark
      → writes {"BrowserThemeColor": COLOUR, "BrowserColorScheme": SCHEME} (0644 root, atomic),
        only for browsers that are installed (their binary exists):
        /etc/chromium/policies/managed/arctic-theme.json      chromium-browser (Fedora 🔍 path)
        /etc/opt/chrome/policies/managed/arctic-theme.json    google-chrome-stable (vendor RPM)
        /etc/brave/policies/managed/arctic-theme.json         brave-browser (vendor RPM)
        Every parent directory must be root-owned 0755 and not a symlink (Omarchy's
        browser-policy.sh rule ✅); otherwise that browser is skipped and named in the answer.
      → {"ok":true,"written":["/etc/chromium/policies/managed/arctic-theme.json"],"skipped":[]}
  arctic-browser-policy clear   → removes the three files → {"ok":true,"removed":[…]}
  arctic-browser-policy status  → {"ok":true,"files":[{"path":"…","color":"#eef2f5","scheme":"device"}]}
  errors → {"ok":false,"error":"That isn't a colour like #eef2f5.","code":"bad_color"}
  ```

  `--root DIR` (tests only; refused when running as root) prefixes every path.
- `arctic-theme browser on|off` (new verb, same shape as `cmd_zen`): saves `"browser_theme"` in
  `~/.config/arctic/settings.json` and runs the hooks; `arctic-theme browser` prints `on`/`off`;
  `current --json` gains `"browser_theme"`.
- Polkit action `org.arcticlinux.browser-policy` (new
  `packaging/polkit/org.arcticlinux.browser-policy.policy`): `allow_any` no, `allow_inactive` no,
  `allow_active` **yes**, `exec.path` = `/usr/libexec/arctic/arctic-browser-policy`. A theme can
  switch at sunset (S5b §7.1), so a password prompt is not acceptable. What it allows: a program
  running as the active local user can set one colour and a light/dark choice in three fixed files.
  Nothing else is reachable through it; BUILD-SPEC says so.

**Not covered.** Arctic's catalog installs Chrome, Brave, Vivaldi and ungoogled-chromium as
Flatpaks (`modules/browser/*/module.toml`). A Flatpak sees the host's `/etc` only under
`/run/host`; Flathub's Chromium-based apps read policies from their own `*.Policy` extension
points 🔍. They are left out of 0.3.0 and named in the wiki; S2 §16 already lists this as the
hook's open issue.

**Files**

| File | New / changed | What |
|---|---|---|
| `design/themegen/templates/chromium/policy.json.tmpl` | new | the template above |
| `packaging/theme-hooks.d/50-chromium` | new | python3, the 40-zen pattern (docstring, never fails, quick); installed by the existing glob (`packaging/arctic-linux.spec:691`) and syntax-checked by the loop at `:825-830` |
| `packaging/desktop/arctic-browser-policy` | new | the root helper |
| `packaging/polkit/org.arcticlinux.browser-policy.policy` | new | the action above |
| `dotfiles/.local/bin/arctic-theme` | changed | docstring (`:1-30`): the `browser on\|off` verb; after `cmd_zen` (`:581-588`): `browser_theme()` and `cmd_browser()`; the verb in the dispatcher next to `zen` (`:668`); `cmd_current` (`:613-621`) adds `browser_theme` |
| `dotfiles/.config/arctic/themes/winter/`, `polar-night/` | changed | re-rendered so each gains `chromium/policy.json` (the build diffs a fresh render against them, spec `:820-821`) |
| `design/themegen/tests/test_app_templates.py` | changed | `APP_TEMPLATES` (`:45-51`) gains `"chromium/policy.json"`; the hook list (`:572`) gains `"50-chromium"`; new tests below |
| `design/themegen/tests/test_browser_policy.py` | new | the helper's tests (found by the `design/themegen/tests` discovery step, `ci.yml:76-77`) |

**Packaging deltas (`packaging/arctic-linux.spec`, arctic-desktop-config)**

- `%install`, next to `:677`: `install -Dpm 0755 packaging/desktop/arctic-browser-policy %{buildroot}%{_libexecdir}/arctic/arctic-browser-policy`
- `%install`, next to `:730-731`: `install -Dpm 0644 packaging/polkit/org.arcticlinux.browser-policy.policy %{buildroot}%{_datadir}/polkit-1/actions/org.arcticlinux.browser-policy.policy`
- `%files` of arctic-desktop-config, after `:1113`: `%{_libexecdir}/arctic/arctic-browser-policy` and
  `%{_datadir}/polkit-1/actions/org.arcticlinux.browser-policy.policy`
- No new Requires and no new Fedora package: `pkexec` comes with polkit, which arctic-shell (`:251`)
  and arctic-desktop (`:456`) require; the hook does nothing when `pkexec` is missing.

**Tests**

| Test | Checks |
|---|---|
| `test_chromium_policy_json` (in `test_app_templates.py`) | for every palette: valid JSON, exactly the two keys, colour = the palette's `ground`, colour ≠ `accent` |
| `test_chromium_hook_off_does_nothing` | a fake `pkexec` on `PATH` records its argv; with `browser_theme` off and no policy file, no call |
| `test_chromium_hook_on_sets_colour` | with it on: one call `set #xxxxxx device`; a second switch to the same theme with the file already matching: no call; a fake running `chromium-browser` gets `--refresh-platform-policy --no-startup-window` |
| `test_chromium_hook_off_clears` | on, then off with a policy file present: one `clear` call |
| `test_browser_policy_set_clear_status` (`test_browser_policy.py`) | with `--root` and fake binaries: only installed browsers' files written, 0644, exact JSON; a symlinked or group-writable parent is skipped; `status` reads them; `clear` removes them |
| `test_browser_policy_rejects_bad_input` | `#abc`, `red`, `#12345g`, a fourth argument, a scheme outside the three: `{"ok":false,…}` and exit code 2, nothing written |
| `test_arctic_theme_browser_verb` (in `test_arctic_theme.py`, the existing file) | `browser on` saves the setting and runs the hooks; `current --json` shows it |
| Hands-on (Fedora 44 VM) | `dnf install chromium`; `arctic-theme browser on`; `chrome://policy` lists both policies; switch Winter ↔ Polar night with Chromium open; 🔍 Fedora's chromium accepts `--refresh-platform-policy` |

**Docs**: `docs/BUILD-SPEC.md` app-theming table (a Chromium row after the Zen row, `:144`) and
hook list (`:165`), plus the new polkit action; `docs/wiki/Themes-and-Customisation.md` hook table
(`:280`) and a "Chromium, Chrome and Brave" paragraph with the Flatpak limit.

#### 9.3 WP-M3: Email and Calendar in Settings > Default apps (`default-app-roles`, non-web-app part)

**What.** Two more rows in Settings > Default apps: which app opens `mailto:` links and which
opens `.ics` invitations. S2 §8.15 already makes a mail web app a `mailto:` handler when the
person turns "Open email links in this app" on; this row is where they choose it.

**Change: `settings/scripts/arctic_settings.py`**, `ROLES` (`:1790-1804`), two entries after `pdf`:

```python
dict(id='email', label='Email', open='', icon='mail', categories=[],
     mimes=['x-scheme-handler/mailto']),
dict(id='calendar', label='Calendar', open='', icon='calendar', categories=[],
     mimes=['text/calendar']),
```

- `categories=[]` on purpose: `role_candidates` (`:1819`) matches categories *or* MIME types, and a
  web app with `Categories=…;Calendar;` (S2 D-12) but no `MimeType` must not be offered for
  `.ics` files it can't open. Only entries that declare the MIME type are candidates.
- No other code changes: `cmd_apps` (`:1936-1958`) already hides a role with no candidates and
  reads `current` from `mimeapps.list`; `cmd_app_set` (`:1961`) already writes
  `[Default Applications]` for the role's MIME types the entry handles. `mail` and `calendar` are
  in the design icon bundle (`settings/assets/Icons.js`) ✅.
- JSON (unchanged shape, from `arctic_settings.py apps`):
  `{"ok":true,"roles":[…,{"id":"email","label":"Email","icon":"mail","keys":"","current":"org.mozilla.Thunderbird","command":"","overridden":false,"candidates":[{"id":"org.mozilla.Thunderbird","name":"Thunderbird","icon":"…","comment":"…"},{"id":"org.arcticlinux.WebApp.gmail","name":"Gmail","icon":"…","comment":""}]}]}`
  (the web-app id prefix is S2's, §10.3).

**Other files**

| File | Change |
|---|---|
| `settings/SearchIndex.js` | after `:86`: `["apps", "apps.email", "Email", "mail mailto thunderbird links"]`, `["apps", "apps.calendar", "Calendar", "ics invitations events"]` (the row keys are `"apps." + id`, `AppsPage.qml:24`). 🔍 what Settings does when a search hit's row is hidden (no candidates): it must open the page without an error |
| `settings/pages/AppsPage.qml` | the header comment (`:1-4`) mentions email and calendar links |
| `settings/tests/test_arctic_settings.py` | fixtures (`:940-951`) gain a Thunderbird entry (`MimeType=x-scheme-handler/mailto;text/calendar;`), a web app `org.arcticlinux.WebApp.gmail` (`MimeType=x-scheme-handler/mailto;`, `Categories=Network;Email;X-Arctic-WebApp;`) and `org.arcticlinux.WebApp.cal` (`Categories=Office;Calendar;X-Arctic-WebApp;`, no MimeType) |
| `docs/wiki/Settings.md` | the Default apps paragraph (`:197-205`) names Email and Calendar |
| `docs/BUILD-SPEC.md` | the Settings `apps` command's role list |

**Tests** (in `DefaultAppsTest`, `settings/tests/test_arctic_settings.py:937`):

- `test_email_role_lists_mailto_handlers`: candidates = Thunderbird and the Gmail web app.
- `test_calendar_role_ignores_category_only_web_apps`: candidates = Thunderbird only.
- `test_set_email_writes_mailto_default`: `app-set email org.arcticlinux.WebApp.gmail` writes
  `x-scheme-handler/mailto=org.arcticlinux.WebApp.gmail.desktop` and nothing for `text/calendar`.
- `test_roles_without_candidates_hidden` (existing `:969` pattern): with no mail app, no `email` role.

The image-editor role from the gap proposal is deferred (§7.3).

#### 9.4 WP-M4: keep the matrix true at release

**What.** When the streams report (implementation rules, "Final report"), the lead updates §5: each
planned row gets its result (shipped / partial / slipped to 0.3.1) and slipped rows move to the
release notes' "Not yet" list. The matrix then goes into `docs/PLAN-0.3.md` with the other sections.

**Files**: `docs/PLAN-0.3.md` (this section), `docs/wiki/Release-Notes.md` (0.3.0 entry: what
shipped, grouped like §5; what slipped, with the row id).

**Check**: rows marked shipped whose key or command is missing from `binds.conf` or
`dotfiles/.local/bin/` are wrong; `settings/tests/test_wiki_keys.py` (WP-M1) catches the keys that
the wiki page repeats.

#### 9.5 Owners and order

| WP | Suggested stream | Depends on | Size |
|---|---|---|---|
| M3 Email and Calendar roles | 1 (web apps): it writes the `mailto` side (S2 §8.15) and already edits `AppsPage.qml` rows | — | S |
| M2 Chromium theme policy | 6 (experience): it owns theming and `arctic-theme` edits (S5b X4) | — (its own helper and polkit action) | S |
| M1 Coming from Omarchy | 6 (experience), with S5b X13 docs | S4 K1, S3 L, S5b X1; §11 issue 1 | S |
| M4 Matrix at release | lead | every stream's report | S |

Order: M3 and M2 in parallel with their streams; M1 after the key tables are final; M4 last, before
the pull request (D10).

---

### 10. Docs to update

| Doc | Change | WP |
|---|---|---|
| `docs/PLAN-0.3.md` | this section, with the S-codes mapped to final section numbers | M4 |
| `docs/wiki/Coming-from-Omarchy.md` (new) | §9.1 | M1 |
| `docs/wiki/_Sidebar.md`, `docs/wiki/Keyboard-Shortcuts.md`, `docs/wiki/Coming-from-Windows-or-macOS.md` | links | M1 |
| `docs/wiki/Themes-and-Customisation.md` (`:280` hook table) | `50-chromium`, the Flatpak limit | M2 |
| `docs/BUILD-SPEC.md` (`:144`, `:165`, the polkit actions, the Settings `apps` roles) | Chromium row, hook, `org.arcticlinux.browser-policy`, email/calendar roles | M2, M3 |
| `docs/wiki/Settings.md` (`:197-205`) | Email and Calendar rows | M3 |
| `docs/wiki/Release-Notes.md` | 0.3.0: shipped and slipped rows | M4 |

---

### 11. Open issues and unverified points

**Decisions for the lead** (each with a recommendation)

1. **Bar focus key** (§7.2.1). *Recommendation*: `Super + Alt + P` as S4 §3.2 row 41 has it: S4's
   table is the one list every section's tests read, and `Super + Alt + B` stays the example key
   Settings suggests to users. The change is one line in stream 3a's `binds.conf` block, the
   `keys.txt` row, S3 §8.1/§8.3 text and `dotfiles/README.md:139`.
2. **Helper names** (§7.2.2). *Recommendation*: keep the drafts' names (`arctic-awake`,
   `arctic-screenshot text|qr`; Activity as S5a §6.6 has it) and correct the implementation
   contract, because the drafts' names are already used in their menus, tiles and tests.
3. **`shell.json` spelling** (§7.2.3). *Recommendation*: camelCase, like the existing `frame` key and
   S5b; S5a and S3 rename their keys.
4. **Owners for M2 and M3** (§9.5): confirm, or move them.
5. **Promoting a P3 row** (§7.3): none recommended for 0.3.0.

**Unverified (🔍), and what proves each**

| # | Claim | Proof |
|---|---|---|
| 1 | Fedora's systemd-rfkill keeps Bluetooth off across a reboot (B16) | turn it off from the new menu, reboot, `rfkill list` |
| 2 | Mango re-applies a saved `monitorrule` on hotplug (D5) | dock with an external monitor at a non-default mode, unplug, replug |
| 3 | What systemd-oomd kills under memory pressure while apps share Mango's cgroup (E16) | `stress-ng --vm` in a terminal on a 4 GB VM; `journalctl -u systemd-oomd` |
| 4 | No Mango 0.17.3 dispatcher disables a touchscreen (H13) | `mango -p` and `src/config/parse_config.c` dispatcher list |
| 5 | How wshowkeys gets input access on F44 (H20) | `rpm -q --filecaps wshowkeys`, `ls -l /usr/bin/wshowkeys` |
| 6 | Mango has no AccessX sticky/slow keys (P4) | Mango issues, wlroots keyboard code |
| 7 | Fedora's chromium reads `/etc/chromium/policies/managed/` (M2) | `rpm -ql chromium`, `chrome://policy` after `set` |
| 8 | Fedora's chromium applies a changed policy on `--refresh-platform-policy` (M2) | change the theme with Chromium open, watch `chrome://policy` |
| 9 | Chromium's palette seeded from `ground` reads as Winter and Polar night (M2) | screenshots in both themes |
| 10 | Flathub Chromium-based browsers ignore host `/etc` policies (M2) | Flatpak Brave, `chrome://policy` |
| 11 | Settings opens the page cleanly for a search hit whose role row is hidden (M3) | search "email" with no mail app installed |
| 12 | The Omarchy key table stays right after the streams merge (M1) | `settings/tests/test_wiki_keys.py` in CI |

---

### 12. Sources

Keys used in the Sources column. Each URL was read by one of the research passes (Omarchy
`quattro` files through the local clone at `b18ab49`); `basecamp/omarchy` links redirect to
`omacom/omarchy`.

| Key | URL |
|---|---|
| a11y-notes | <https://github.com/splondike/wayland-accessibility-notes/blob/main/README.md> |
| C-Audio | <https://github.com/caelestia-dots/shell/blob/main/services/Audio.qml> |
| C-GameMode | <https://github.com/caelestia-dots/shell/blob/main/services/GameMode.qml> |
| C-repo | <https://github.com/caelestia-dots/shell> |
| Chrome-policies | <https://chromeenterprise.google/policies/> |
| cliphist | <https://github.com/sentriz/cliphist/blob/master/cliphist.go> |
| D-BootEntryService | <https://github.com/AvengeMedia/DankMaterialShell/blob/master/quickshell/Services/BootEntryService.qml> |
| D-BuiltinPlugins | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ControlCenter/BuiltinPlugins> |
| D-cli-color-picker | <https://danklinux.com/docs/dankmaterialshell/cli-color-picker> |
| D-cli-doctor | <https://danklinux.com/docs/dankmaterialshell/cli-doctor> |
| D-cli-keybinds-cheatsheets | <https://danklinux.com/docs/dankmaterialshell/cli-keybinds-cheatsheets> |
| D-cli-qr | <https://danklinux.com/docs/dankmaterialshell/cli-qr> |
| D-cli-system-updater | <https://danklinux.com/docs/dankmaterialshell/cli-system-updater> |
| D-CupsService | <https://github.com/AvengeMedia/DankMaterialShell/blob/master/quickshell/Services/CupsService.qml> |
| D-Details | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ControlCenter/Details> |
| D-Modals | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modals> |
| D-Notepad | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/Notepad> |
| D-OSD | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/OSD> |
| D-overview | <https://danklinux.com/docs/dankmaterialshell/overview> |
| D-Popouts | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/DankBar/Popouts> |
| D-ProcessList | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ProcessList> |
| D-repo | <https://github.com/AvengeMedia/DankMaterialShell> |
| D-UsersService | <https://github.com/AvengeMedia/DankMaterialShell/blob/master/quickshell/Services/UsersService.qml> |
| D-v1-6-release | <https://danklinux.com/blog/v1-6-release> |
| D-vpn | <https://danklinux.com/docs/dankmaterialshell/vpn> |
| D-Widgets | <https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ControlCenter/Widgets> |
| E4-musicRecognition | <https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/scripts/musicRecognition> |
| E4-onScreenKeyboard | <https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/modules/ii/onScreenKeyboard> |
| E4-services | <https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/services> |
| E4-sidebarLeft | <https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/modules/ii/sidebarLeft> |
| F44-deja-dup | <https://mdapi.fedoraproject.org/f44/pkg/deja-dup> |
| F44-fcitx5 | <https://mdapi.fedoraproject.org/f44/pkg/fcitx5> |
| F44-google-noto-color-emoji-fonts | <https://mdapi.fedoraproject.org/f44/pkg/google-noto-color-emoji-fonts> |
| F44-quickshell | <https://mdapi.fedoraproject.org/f44/pkg/quickshell> |
| F44-sane-airscan | <https://mdapi.fedoraproject.org/f44/pkg/sane-airscan> |
| F44-switcheroo-control | <https://mdapi.fedoraproject.org/f44/pkg/switcheroo-control> |
| F44-Thunar | <https://mdapi.fedoraproject.org/f44/pkg/Thunar> |
| F44-wl-kbptr | <https://mdapi.fedoraproject.org/f44/pkg/wl-kbptr> |
| F44-wshowkeys | <https://mdapi.fedoraproject.org/f44/pkg/wshowkeys> |
| Fedora-upgrade-docs | <https://docs.fedoraproject.org/en-US/quick-docs/upgrading-fedora-offline/> |
| GNOME-48 | <https://release.gnome.org/48/> |
| GNOME-49 | <https://release.gnome.org/49/> |
| KDE-6.5.0 | <https://kde.org/announcements/plasma/6/6.5.0/> |
| KDE-6.6.0 | <https://kde.org/announcements/plasma/6/6.6.0/> |
| KDE-6.7.0 | <https://kde.org/announcements/plasma/6/6.7.0/> |
| KDE-KDEConnect | <https://userbase.kde.org/KDEConnect> |
| libxkbcommon-92 | <https://github.com/xkbcommon/libxkbcommon/issues/92> |
| macOS-Tahoe | <https://support.apple.com/en-us/122868> |
| man-wlsunset | <https://man.archlinux.org/man/extra/wlsunset/wlsunset.1.en> |
| man-xdpw-5 | <https://man.archlinux.org/man/extra/xdg-desktop-portal-wlr/xdg-desktop-portal-wlr.5.en> |
| Mango-0.17.3-keys | <https://raw.githubusercontent.com/mangowm/mango/0.17.3/docs/bindings/keys.md> |
| Mango-0.17.3-rules | <https://raw.githubusercontent.com/mangowm/mango/0.17.3/docs/window-management/rules.md> |
| Mango-0.17.3-switchbind | <https://raw.githubusercontent.com/mangowm/mango/0.17.3/docs/bindings/mouse-gestures.md> |
| Mango-ipc | <https://github.com/DreamMaoMao/mangowc/blob/main/docs/ipc.md> |
| Mango-monitors | <https://github.com/DreamMaoMao/mangowc/blob/main/docs/configuration/monitors.md> |
| Mango-mouse-gestures | <https://github.com/DreamMaoMao/mangowc/blob/main/docs/bindings/mouse-gestures.md> |
| Mango-overview | <https://github.com/DreamMaoMao/mangowc/blob/main/docs/window-management/overview.md> |
| Mango-repo | <https://github.com/DreamMaoMao/mangowc> |
| Mango-xdg-portals | <https://github.com/DreamMaoMao/mangowc/blob/main/docs/configuration/xdg-portals.md> |
| N-automation-hooks | <https://docs.noctalia.dev/noctalia/automation/hooks/> |
| N-bar-widgets | <https://docs.noctalia.dev/noctalia/bar/widgets/> |
| N-bar-widgets-caffeine | <https://docs.noctalia.dev/noctalia/bar/widgets/caffeine/> |
| N-bar-widgets-lock-keys | <https://docs.noctalia.dev/noctalia/bar/widgets/lock-keys/> |
| N-bar-widgets-privacy | <https://docs.noctalia.dev/noctalia/bar/widgets/privacy/> |
| N-bar-widgets-sysmon | <https://docs.noctalia.dev/noctalia/bar/widgets/sysmon/> |
| N-configuration-secret-service | <https://docs.noctalia.dev/noctalia/configuration/secret-service/> |
| N-configuration-shell | <https://docs.noctalia.dev/noctalia/configuration/shell/> |
| N-control-center | <https://docs.noctalia.dev/noctalia/control-center/> |
| N-control-center-shortcuts | <https://docs.noctalia.dev/noctalia/control-center/shortcuts/> |
| N-desktop-widgets | <https://docs.noctalia.dev/noctalia/desktop/widgets/> |
| N-dock | <https://docs.noctalia.dev/noctalia/dock/> |
| N-launcher | <https://docs.noctalia.dev/noctalia/launcher/> |
| N-lockscreen-widgets | <https://docs.noctalia.dev/noctalia/lockscreen/widgets/> |
| N-plugins-official-plugins | <https://docs.noctalia.dev/noctalia/plugins/official-plugins/> |
| N-repo | <https://github.com/noctalia-dev/noctalia-shell> |
| N-services-audio | <https://docs.noctalia.dev/noctalia/services/audio/> |
| N-services-battery | <https://docs.noctalia.dev/noctalia/services/battery/> |
| N-services-brightness | <https://docs.noctalia.dev/noctalia/services/brightness/> |
| N-services-calendar | <https://docs.noctalia.dev/noctalia/services/calendar/> |
| N-services-idle | <https://docs.noctalia.dev/noctalia/services/idle/> |
| N-services-night-light | <https://docs.noctalia.dev/noctalia/services/night-light/> |
| N-services-notifications | <https://docs.noctalia.dev/noctalia/services/notifications/> |
| N-services-weather | <https://docs.noctalia.dev/noctalia/services/weather/> |
| N-theming-templates | <https://docs.noctalia.dev/noctalia/theming/templates/> |
| O-app-pip | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/apps/pip.lua> |
| O-app-system | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/apps/system.lua> |
| O-bin-display-text-size | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-display-text-size> |
| O-bin-hyprland-window-pop | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-hyprland-window-pop> |
| O-bin-install-dev-env | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-install-dev-env> |
| O-bin-install-docker-dbs | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-install-docker-dbs> |
| O-bin-install-preinstalls | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-install-preinstalls> |
| O-bin-launch-or-focus | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-launch-or-focus> |
| O-bin-pkg-install | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-pkg-install> |
| O-bin-provision-first-run | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-provision-first-run> |
| O-bin-remove-launcher-entry | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-remove-launcher-entry> |
| O-bin-system-lock | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-system-lock> |
| O-bin-theme-set | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-theme-set> |
| O-bin-theme-set-browser | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-theme-set-browser> |
| O-bin-theme-set-gnome | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-theme-set-gnome> |
| O-bin-tui-install | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-tui-install> |
| O-bin-update | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-update> |
| O-bin-webapp-install | <https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-webapp-install> |
| O-bind-applications | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/applications.lua> |
| O-bind-clipboard | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/clipboard.lua> |
| O-bind-media | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/media.lua> |
| O-bind-tiling | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/tiling.lua> |
| O-bind-utilities | <https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/utilities.lua> |
| O-cfg-chromium-flags.conf | <https://github.com/omacom/omarchy/blob/quattro/config/chromium-flags.conf> |
| O-cfg-hyprland-preview-share-picker-config | <https://github.com/omacom/omarchy/blob/quattro/config/hyprland-preview-share-picker/config.yaml> |
| O-commit-b18ab49 | <https://github.com/omacom/omarchy/commit/b18ab4952b88b95efe7758ee5f9bd3bb47483875> |
| O-doc-elsewhen | <https://github.com/omacom/omarchy/blob/quattro/docs/elsewhen.md> |
| O-doc-menu | <https://github.com/omacom/omarchy/blob/quattro/docs/menu.md> |
| O-doc-notifications | <https://github.com/omacom/omarchy/blob/quattro/docs/notifications.md> |
| O-doc-omarchy-shell | <https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md> |
| O-doc-theming | <https://github.com/omacom/omarchy/blob/quattro/docs/theming.md> |
| O-inst-hardware | <https://github.com/omacom/omarchy/tree/quattro/install/hardware> |
| O-inst-omarchy-base.packages | <https://github.com/omacom/omarchy/blob/quattro/install/omarchy-base.packages> |
| O-man02 | <https://github.com/omacom/omarchy/blob/quattro/manual/02-getting-started.md> |
| O-man03 | <https://github.com/omacom/omarchy/blob/quattro/manual/03-coming-from-mac-or-windows.md> |
| O-man04 | <https://github.com/omacom/omarchy/blob/quattro/manual/04-navigation.md> |
| O-man05 | <https://github.com/omacom/omarchy/blob/quattro/manual/05-the-top-bar.md> |
| O-man07 | <https://github.com/omacom/omarchy/blob/quattro/manual/07-hotkeys.md> |
| O-man08 | <https://github.com/omacom/omarchy/blob/quattro/manual/08-unified-clipboard-history.md> |
| O-man09 | <https://github.com/omacom/omarchy/blob/quattro/manual/09-reminders.md> |
| O-man10 | <https://github.com/omacom/omarchy/blob/quattro/manual/10-notices.md> |
| O-man11 | <https://github.com/omacom/omarchy/blob/quattro/manual/11-text-extraction-dictation.md> |
| O-man12 | <https://github.com/omacom/omarchy/blob/quattro/manual/12-screenshots-recording.md> |
| O-man13 | <https://github.com/omacom/omarchy/blob/quattro/manual/13-toggles-idle-screensaver.md> |
| O-man14 | <https://github.com/omacom/omarchy/blob/quattro/manual/14-omarchy-cli.md> |
| O-man15 | <https://github.com/omacom/omarchy/blob/quattro/manual/15-terminal.md> |
| O-man16 | <https://github.com/omacom/omarchy/blob/quattro/manual/16-neovim.md> |
| O-man17 | <https://github.com/omacom/omarchy/blob/quattro/manual/17-ai.md> |
| O-man18 | <https://github.com/omacom/omarchy/blob/quattro/manual/18-development-tools.md> |
| O-man20 | <https://github.com/omacom/omarchy/blob/quattro/manual/20-shell-functions.md> |
| O-man21 | <https://github.com/omacom/omarchy/blob/quattro/manual/21-tuis.md> |
| O-man22 | <https://github.com/omacom/omarchy/blob/quattro/manual/22-guis.md> |
| O-man23 | <https://github.com/omacom/omarchy/blob/quattro/manual/23-browsers.md> |
| O-man24 | <https://github.com/omacom/omarchy/blob/quattro/manual/24-commercial-apps-services.md> |
| O-man25 | <https://github.com/omacom/omarchy/blob/quattro/manual/25-web-apps.md> |
| O-man26 | <https://github.com/omacom/omarchy/blob/quattro/manual/26-gaming.md> |
| O-man28 | <https://github.com/omacom/omarchy/blob/quattro/manual/28-windows-vm.md> |
| O-man30 | <https://github.com/omacom/omarchy/blob/quattro/manual/30-updates.md> |
| O-man31 | <https://github.com/omacom/omarchy/blob/quattro/manual/31-dotfiles.md> |
| O-man32 | <https://github.com/omacom/omarchy/blob/quattro/manual/32-shell-plugins.md> |
| O-man33 | <https://github.com/omacom/omarchy/blob/quattro/manual/33-monitors.md> |
| O-man34 | <https://github.com/omacom/omarchy/blob/quattro/manual/34-keyboard-mouse-trackpad.md> |
| O-man35 | <https://github.com/omacom/omarchy/blob/quattro/manual/35-networking.md> |
| O-man36 | <https://github.com/omacom/omarchy/blob/quattro/manual/36-system-sleep.md> |
| O-man37 | <https://github.com/omacom/omarchy/blob/quattro/manual/37-hardware-authentication.md> |
| O-man38 | <https://github.com/omacom/omarchy/blob/quattro/manual/38-fonts.md> |
| O-man39 | <https://github.com/omacom/omarchy/blob/quattro/manual/39-backgrounds.md> |
| O-man41 | <https://github.com/omacom/omarchy/blob/quattro/manual/41-branding.md> |
| O-man42 | <https://github.com/omacom/omarchy/blob/quattro/manual/42-common-tweaks.md> |
| O-man43 | <https://github.com/omacom/omarchy/blob/quattro/manual/43-making-your-own-theme.md> |
| O-man45 | <https://github.com/omacom/omarchy/blob/quattro/manual/45-troubleshooting.md> |
| O-man46 | <https://github.com/omacom/omarchy/blob/quattro/manual/46-faq.md> |
| O-man47 | <https://github.com/omacom/omarchy/blob/quattro/manual/47-system-snapshots.md> |
| O-man48 | <https://github.com/omacom/omarchy/blob/quattro/manual/48-security.md> |
| O-man51 | <https://github.com/omacom/omarchy/blob/quattro/manual/51-unattended-installs.md> |
| O-menu-jsonc | <https://github.com/omacom/omarchy/blob/quattro/default/omarchy/omarchy-menu.jsonc> |
| O-plug-agents | <https://github.com/omacom/omarchy/tree/quattro/shell/plugins/agents> |
| O-plug-bar-widgets-SystemUpdate | <https://github.com/omacom/omarchy/blob/quattro/shell/plugins/bar/widgets/SystemUpdate.qml> |
| O-plug-README | <https://github.com/omacom/omarchy/blob/quattro/shell/plugins/README.md> |
| O-plug-services-battery-Service | <https://github.com/omacom/omarchy/blob/quattro/shell/plugins/services/battery/Service.qml> |
| O-plug-services-media-BarWidget | <https://github.com/omacom/omarchy/blob/quattro/shell/plugins/services/media/BarWidget.qml> |
| O-themes | <https://github.com/omacom/omarchy/tree/quattro/themes> |
| O-v4.0.0 | <https://github.com/basecamp/omarchy/releases/tag/v4.0.0> |
| O3-utilities | <https://github.com/omacom/omarchy/blob/v3.8.4/default/hypr/bindings/utilities.conf> |
| QS-docs-ScreencopyView | <https://quickshell.org/docs/v0.2.1/types/Quickshell.Wayland/ScreencopyView/> |
| QS-screencopy | <https://github.com/quickshell-mirror/quickshell/tree/master/src/wayland/screencopy> |
| QS-v0.3.1 | <https://github.com/quickshell-mirror/quickshell/blob/master/changelog/v0.3.1.md> |
| systemd-special | <https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.special.xml> |
| systemd-xdg-autostart | <https://www.freedesktop.org/software/systemd/man/latest/systemd-xdg-autostart-generator.html> |
| tuned-ppd.conf | <https://github.com/redhat-performance/tuned/blob/master/tuned/ppd/ppd.conf> |
| UPower-backend | <https://gitlab.freedesktop.org/upower/upower/-/raw/v1.91.4/src/linux/up-backend.c> |
| UPower-Device | <https://upower.freedesktop.org/docs/Device.html> |
| Windows-GameBar | <https://support.microsoft.com/en-us/windows/keyboard-shortcuts-for-xbox-game-bar-85d97243-c89b-1ae1-6402-0faf35d6489d> |
| Windows-keys | <https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec> |
| xdpw | <https://github.com/emersion/xdg-desktop-portal-wlr> |

[a11y-notes]: https://github.com/splondike/wayland-accessibility-notes/blob/main/README.md
[C-Audio]: https://github.com/caelestia-dots/shell/blob/main/services/Audio.qml
[C-GameMode]: https://github.com/caelestia-dots/shell/blob/main/services/GameMode.qml
[C-repo]: https://github.com/caelestia-dots/shell
[Chrome-policies]: https://chromeenterprise.google/policies/
[cliphist]: https://github.com/sentriz/cliphist/blob/master/cliphist.go
[D-BootEntryService]: https://github.com/AvengeMedia/DankMaterialShell/blob/master/quickshell/Services/BootEntryService.qml
[D-BuiltinPlugins]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ControlCenter/BuiltinPlugins
[D-cli-color-picker]: https://danklinux.com/docs/dankmaterialshell/cli-color-picker
[D-cli-doctor]: https://danklinux.com/docs/dankmaterialshell/cli-doctor
[D-cli-keybinds-cheatsheets]: https://danklinux.com/docs/dankmaterialshell/cli-keybinds-cheatsheets
[D-cli-qr]: https://danklinux.com/docs/dankmaterialshell/cli-qr
[D-cli-system-updater]: https://danklinux.com/docs/dankmaterialshell/cli-system-updater
[D-CupsService]: https://github.com/AvengeMedia/DankMaterialShell/blob/master/quickshell/Services/CupsService.qml
[D-Details]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ControlCenter/Details
[D-Modals]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modals
[D-Notepad]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/Notepad
[D-OSD]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/OSD
[D-overview]: https://danklinux.com/docs/dankmaterialshell/overview
[D-Popouts]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/DankBar/Popouts
[D-ProcessList]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ProcessList
[D-repo]: https://github.com/AvengeMedia/DankMaterialShell
[D-UsersService]: https://github.com/AvengeMedia/DankMaterialShell/blob/master/quickshell/Services/UsersService.qml
[D-v1-6-release]: https://danklinux.com/blog/v1-6-release
[D-vpn]: https://danklinux.com/docs/dankmaterialshell/vpn
[D-Widgets]: https://github.com/AvengeMedia/DankMaterialShell/tree/master/quickshell/Modules/ControlCenter/Widgets
[E4-musicRecognition]: https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/scripts/musicRecognition
[E4-onScreenKeyboard]: https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/modules/ii/onScreenKeyboard
[E4-services]: https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/services
[E4-sidebarLeft]: https://github.com/end-4/dots-hyprland/tree/main/dots/.config/quickshell/ii/modules/ii/sidebarLeft
[F44-deja-dup]: https://mdapi.fedoraproject.org/f44/pkg/deja-dup
[F44-fcitx5]: https://mdapi.fedoraproject.org/f44/pkg/fcitx5
[F44-google-noto-color-emoji-fonts]: https://mdapi.fedoraproject.org/f44/pkg/google-noto-color-emoji-fonts
[F44-quickshell]: https://mdapi.fedoraproject.org/f44/pkg/quickshell
[F44-sane-airscan]: https://mdapi.fedoraproject.org/f44/pkg/sane-airscan
[F44-switcheroo-control]: https://mdapi.fedoraproject.org/f44/pkg/switcheroo-control
[F44-Thunar]: https://mdapi.fedoraproject.org/f44/pkg/Thunar
[F44-wl-kbptr]: https://mdapi.fedoraproject.org/f44/pkg/wl-kbptr
[F44-wshowkeys]: https://mdapi.fedoraproject.org/f44/pkg/wshowkeys
[Fedora-upgrade-docs]: https://docs.fedoraproject.org/en-US/quick-docs/upgrading-fedora-offline/
[GNOME-48]: https://release.gnome.org/48/
[GNOME-49]: https://release.gnome.org/49/
[KDE-6.5.0]: https://kde.org/announcements/plasma/6/6.5.0/
[KDE-6.6.0]: https://kde.org/announcements/plasma/6/6.6.0/
[KDE-6.7.0]: https://kde.org/announcements/plasma/6/6.7.0/
[KDE-KDEConnect]: https://userbase.kde.org/KDEConnect
[libxkbcommon-92]: https://github.com/xkbcommon/libxkbcommon/issues/92
[macOS-Tahoe]: https://support.apple.com/en-us/122868
[man-wlsunset]: https://man.archlinux.org/man/extra/wlsunset/wlsunset.1.en
[man-xdpw-5]: https://man.archlinux.org/man/extra/xdg-desktop-portal-wlr/xdg-desktop-portal-wlr.5.en
[Mango-0.17.3-keys]: https://raw.githubusercontent.com/mangowm/mango/0.17.3/docs/bindings/keys.md
[Mango-0.17.3-rules]: https://raw.githubusercontent.com/mangowm/mango/0.17.3/docs/window-management/rules.md
[Mango-0.17.3-switchbind]: https://raw.githubusercontent.com/mangowm/mango/0.17.3/docs/bindings/mouse-gestures.md
[Mango-ipc]: https://github.com/DreamMaoMao/mangowc/blob/main/docs/ipc.md
[Mango-monitors]: https://github.com/DreamMaoMao/mangowc/blob/main/docs/configuration/monitors.md
[Mango-mouse-gestures]: https://github.com/DreamMaoMao/mangowc/blob/main/docs/bindings/mouse-gestures.md
[Mango-overview]: https://github.com/DreamMaoMao/mangowc/blob/main/docs/window-management/overview.md
[Mango-repo]: https://github.com/DreamMaoMao/mangowc
[Mango-xdg-portals]: https://github.com/DreamMaoMao/mangowc/blob/main/docs/configuration/xdg-portals.md
[N-automation-hooks]: https://docs.noctalia.dev/noctalia/automation/hooks/
[N-bar-widgets]: https://docs.noctalia.dev/noctalia/bar/widgets/
[N-bar-widgets-caffeine]: https://docs.noctalia.dev/noctalia/bar/widgets/caffeine/
[N-bar-widgets-lock-keys]: https://docs.noctalia.dev/noctalia/bar/widgets/lock-keys/
[N-bar-widgets-privacy]: https://docs.noctalia.dev/noctalia/bar/widgets/privacy/
[N-bar-widgets-sysmon]: https://docs.noctalia.dev/noctalia/bar/widgets/sysmon/
[N-configuration-secret-service]: https://docs.noctalia.dev/noctalia/configuration/secret-service/
[N-configuration-shell]: https://docs.noctalia.dev/noctalia/configuration/shell/
[N-control-center]: https://docs.noctalia.dev/noctalia/control-center/
[N-control-center-shortcuts]: https://docs.noctalia.dev/noctalia/control-center/shortcuts/
[N-desktop-widgets]: https://docs.noctalia.dev/noctalia/desktop/widgets/
[N-dock]: https://docs.noctalia.dev/noctalia/dock/
[N-launcher]: https://docs.noctalia.dev/noctalia/launcher/
[N-lockscreen-widgets]: https://docs.noctalia.dev/noctalia/lockscreen/widgets/
[N-plugins-official-plugins]: https://docs.noctalia.dev/noctalia/plugins/official-plugins/
[N-repo]: https://github.com/noctalia-dev/noctalia-shell
[N-services-audio]: https://docs.noctalia.dev/noctalia/services/audio/
[N-services-battery]: https://docs.noctalia.dev/noctalia/services/battery/
[N-services-brightness]: https://docs.noctalia.dev/noctalia/services/brightness/
[N-services-calendar]: https://docs.noctalia.dev/noctalia/services/calendar/
[N-services-idle]: https://docs.noctalia.dev/noctalia/services/idle/
[N-services-night-light]: https://docs.noctalia.dev/noctalia/services/night-light/
[N-services-notifications]: https://docs.noctalia.dev/noctalia/services/notifications/
[N-services-weather]: https://docs.noctalia.dev/noctalia/services/weather/
[N-theming-templates]: https://docs.noctalia.dev/noctalia/theming/templates/
[O-app-pip]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/apps/pip.lua
[O-app-system]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/apps/system.lua
[O-bin-display-text-size]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-display-text-size
[O-bin-hyprland-window-pop]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-hyprland-window-pop
[O-bin-install-dev-env]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-install-dev-env
[O-bin-install-docker-dbs]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-install-docker-dbs
[O-bin-install-preinstalls]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-install-preinstalls
[O-bin-launch-or-focus]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-launch-or-focus
[O-bin-pkg-install]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-pkg-install
[O-bin-provision-first-run]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-provision-first-run
[O-bin-remove-launcher-entry]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-remove-launcher-entry
[O-bin-system-lock]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-system-lock
[O-bin-theme-set]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-theme-set
[O-bin-theme-set-browser]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-theme-set-browser
[O-bin-theme-set-gnome]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-theme-set-gnome
[O-bin-tui-install]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-tui-install
[O-bin-update]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-update
[O-bin-webapp-install]: https://github.com/omacom/omarchy/blob/quattro/bin/omarchy-webapp-install
[O-bind-applications]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/applications.lua
[O-bind-clipboard]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/clipboard.lua
[O-bind-media]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/media.lua
[O-bind-tiling]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/tiling.lua
[O-bind-utilities]: https://github.com/omacom/omarchy/blob/quattro/default/hypr/bindings/utilities.lua
[O-cfg-chromium-flags.conf]: https://github.com/omacom/omarchy/blob/quattro/config/chromium-flags.conf
[O-cfg-hyprland-preview-share-picker-config]: https://github.com/omacom/omarchy/blob/quattro/config/hyprland-preview-share-picker/config.yaml
[O-commit-b18ab49]: https://github.com/omacom/omarchy/commit/b18ab4952b88b95efe7758ee5f9bd3bb47483875
[O-doc-elsewhen]: https://github.com/omacom/omarchy/blob/quattro/docs/elsewhen.md
[O-doc-menu]: https://github.com/omacom/omarchy/blob/quattro/docs/menu.md
[O-doc-notifications]: https://github.com/omacom/omarchy/blob/quattro/docs/notifications.md
[O-doc-omarchy-shell]: https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md
[O-doc-theming]: https://github.com/omacom/omarchy/blob/quattro/docs/theming.md
[O-inst-hardware]: https://github.com/omacom/omarchy/tree/quattro/install/hardware
[O-inst-omarchy-base.packages]: https://github.com/omacom/omarchy/blob/quattro/install/omarchy-base.packages
[O-man02]: https://github.com/omacom/omarchy/blob/quattro/manual/02-getting-started.md
[O-man03]: https://github.com/omacom/omarchy/blob/quattro/manual/03-coming-from-mac-or-windows.md
[O-man04]: https://github.com/omacom/omarchy/blob/quattro/manual/04-navigation.md
[O-man05]: https://github.com/omacom/omarchy/blob/quattro/manual/05-the-top-bar.md
[O-man07]: https://github.com/omacom/omarchy/blob/quattro/manual/07-hotkeys.md
[O-man08]: https://github.com/omacom/omarchy/blob/quattro/manual/08-unified-clipboard-history.md
[O-man09]: https://github.com/omacom/omarchy/blob/quattro/manual/09-reminders.md
[O-man10]: https://github.com/omacom/omarchy/blob/quattro/manual/10-notices.md
[O-man11]: https://github.com/omacom/omarchy/blob/quattro/manual/11-text-extraction-dictation.md
[O-man12]: https://github.com/omacom/omarchy/blob/quattro/manual/12-screenshots-recording.md
[O-man13]: https://github.com/omacom/omarchy/blob/quattro/manual/13-toggles-idle-screensaver.md
[O-man14]: https://github.com/omacom/omarchy/blob/quattro/manual/14-omarchy-cli.md
[O-man15]: https://github.com/omacom/omarchy/blob/quattro/manual/15-terminal.md
[O-man16]: https://github.com/omacom/omarchy/blob/quattro/manual/16-neovim.md
[O-man17]: https://github.com/omacom/omarchy/blob/quattro/manual/17-ai.md
[O-man18]: https://github.com/omacom/omarchy/blob/quattro/manual/18-development-tools.md
[O-man20]: https://github.com/omacom/omarchy/blob/quattro/manual/20-shell-functions.md
[O-man21]: https://github.com/omacom/omarchy/blob/quattro/manual/21-tuis.md
[O-man22]: https://github.com/omacom/omarchy/blob/quattro/manual/22-guis.md
[O-man23]: https://github.com/omacom/omarchy/blob/quattro/manual/23-browsers.md
[O-man24]: https://github.com/omacom/omarchy/blob/quattro/manual/24-commercial-apps-services.md
[O-man25]: https://github.com/omacom/omarchy/blob/quattro/manual/25-web-apps.md
[O-man26]: https://github.com/omacom/omarchy/blob/quattro/manual/26-gaming.md
[O-man28]: https://github.com/omacom/omarchy/blob/quattro/manual/28-windows-vm.md
[O-man30]: https://github.com/omacom/omarchy/blob/quattro/manual/30-updates.md
[O-man31]: https://github.com/omacom/omarchy/blob/quattro/manual/31-dotfiles.md
[O-man32]: https://github.com/omacom/omarchy/blob/quattro/manual/32-shell-plugins.md
[O-man33]: https://github.com/omacom/omarchy/blob/quattro/manual/33-monitors.md
[O-man34]: https://github.com/omacom/omarchy/blob/quattro/manual/34-keyboard-mouse-trackpad.md
[O-man35]: https://github.com/omacom/omarchy/blob/quattro/manual/35-networking.md
[O-man36]: https://github.com/omacom/omarchy/blob/quattro/manual/36-system-sleep.md
[O-man37]: https://github.com/omacom/omarchy/blob/quattro/manual/37-hardware-authentication.md
[O-man38]: https://github.com/omacom/omarchy/blob/quattro/manual/38-fonts.md
[O-man39]: https://github.com/omacom/omarchy/blob/quattro/manual/39-backgrounds.md
[O-man41]: https://github.com/omacom/omarchy/blob/quattro/manual/41-branding.md
[O-man42]: https://github.com/omacom/omarchy/blob/quattro/manual/42-common-tweaks.md
[O-man43]: https://github.com/omacom/omarchy/blob/quattro/manual/43-making-your-own-theme.md
[O-man45]: https://github.com/omacom/omarchy/blob/quattro/manual/45-troubleshooting.md
[O-man46]: https://github.com/omacom/omarchy/blob/quattro/manual/46-faq.md
[O-man47]: https://github.com/omacom/omarchy/blob/quattro/manual/47-system-snapshots.md
[O-man48]: https://github.com/omacom/omarchy/blob/quattro/manual/48-security.md
[O-man51]: https://github.com/omacom/omarchy/blob/quattro/manual/51-unattended-installs.md
[O-menu-jsonc]: https://github.com/omacom/omarchy/blob/quattro/default/omarchy/omarchy-menu.jsonc
[O-plug-agents]: https://github.com/omacom/omarchy/tree/quattro/shell/plugins/agents
[O-plug-bar-widgets-SystemUpdate]: https://github.com/omacom/omarchy/blob/quattro/shell/plugins/bar/widgets/SystemUpdate.qml
[O-plug-README]: https://github.com/omacom/omarchy/blob/quattro/shell/plugins/README.md
[O-plug-services-battery-Service]: https://github.com/omacom/omarchy/blob/quattro/shell/plugins/services/battery/Service.qml
[O-plug-services-media-BarWidget]: https://github.com/omacom/omarchy/blob/quattro/shell/plugins/services/media/BarWidget.qml
[O-themes]: https://github.com/omacom/omarchy/tree/quattro/themes
[O-v4.0.0]: https://github.com/basecamp/omarchy/releases/tag/v4.0.0
[O3-utilities]: https://github.com/omacom/omarchy/blob/v3.8.4/default/hypr/bindings/utilities.conf
[QS-docs-ScreencopyView]: https://quickshell.org/docs/v0.2.1/types/Quickshell.Wayland/ScreencopyView/
[QS-screencopy]: https://github.com/quickshell-mirror/quickshell/tree/master/src/wayland/screencopy
[QS-v0.3.1]: https://github.com/quickshell-mirror/quickshell/blob/master/changelog/v0.3.1.md
[systemd-special]: https://raw.githubusercontent.com/systemd/systemd/main/man/systemd.special.xml
[systemd-xdg-autostart]: https://www.freedesktop.org/software/systemd/man/latest/systemd-xdg-autostart-generator.html
[tuned-ppd.conf]: https://github.com/redhat-performance/tuned/blob/master/tuned/ppd/ppd.conf
[UPower-backend]: https://gitlab.freedesktop.org/upower/upower/-/raw/v1.91.4/src/linux/up-backend.c
[UPower-Device]: https://upower.freedesktop.org/docs/Device.html
[Windows-GameBar]: https://support.microsoft.com/en-us/windows/keyboard-shortcuts-for-xbox-game-bar-85d97243-c89b-1ae1-6402-0faf35d6489d
[Windows-keys]: https://support.microsoft.com/en-us/windows/keyboard-shortcuts-in-windows-dcc61a57-8ff0-cffe-9796-cb9706c75eec
[xdpw]: https://github.com/emersion/xdg-desktop-portal-wlr

#### 12.1 Cross-index: research entry → matrix rows

Entry numbers are 0-based positions in each file's `features` array (scratchpad `research/`).

**omarchy.json** (entry → rows): 0 → A1, G6; 1 → G1, G2; 2 → A2; 3 → A3, D13; 4 → A4; 5 → A5; 6 → G3, G6; 7 → G5; 8 → A6, L12, N9; 9 → E1, E2, E4; 10 → A7, A9; 11 → A8; 12 → Q1; 13 → K13; 14 → A10; 15 → A22; 16 → A21; 17 → A11, A13; 18 → C1, C2; 19 → C4; 20 → B1, B3, B14; 21 → B15, B16, B18; 22 → D2, D6; 23 → E7, E11; 24 → N5, O1, O3; 25 → O4; 26 → O5; 27 → C9, C13; 28 → A20; 29 → A18; 30 → H8; 31 → A24; 32 → A25; 33 → O12; 34 → B10; 35 → O10; 36 → J16; 37 → A28; 38 → A29; 39 → A31; 40 → A30; 41 → F1; 42 → F5; 43 → F3; 44 → A23; 45 → A33; 46 → H4; 47 → H1, H2; 48 → G10; 49 → G28; 50 → H6; 51 → H7; 52 → G21, H16; 53 → I1, I3, I5; 54 → I4; 55 → I11, I12; 56 → I13; 57 → I10; 58 → I8; 59 → H2, I9; 60 → I15; 61 → I16; 62 → I17; 63 → I18; 64 → B19; 65 → K1; 66 → K2; 67 → G16; 68 → K8, K9; 69 → K3; 70 → K4; 71 → K5; 72 → K7; 73 → K10; 74 → K11; 75 → D7; 76 → J23; 77 → K12; 78 → J1; 79 → J2; 80 → J3; 81 → J4; 82 → J6; 83 → J7; 84 → J9; 85 → J10; 86 → J11, J13; 87 → J14; 88 → G27; 89 → J15; 90 → J17; 91 → D6; 92 → D3, D4; 93 → D2; 94 → C8, C9; 95 → C18; 96 → N9; 97 → H11; 98 → H12, H13, H14; 99 → H15; 100 → B4; 101 → B11; 102 → B12; 103 → B13; 104 → B9; 105 → E8; 106 → E9; 107 → E5, E6; 108 → E14; 109 → E12; 110 → E15; 111 → D1; 112 → H8, L1; 113 → A16, D12; 114 → L6; 115 → B22, B23; 116 → L3; 117 → L4; 118 → L5; 119 → L7; 120 → L8, L9; 121 → L10; 122 → M5; 123 → M1; 124 → M3; 125 → M4; 126 → M2; 127 → M6; 128 → L14; 129 → L15; 130 → N5; 131 → G4, G5; 132 → G7; 133 → G8, G9; 134 → G11; 135 → G12; 136 → G13; 137 → G14; 138 → G16; 139 → G17; 140 → G18; 141 → G18; 142 → G19; 143 → G20; 144 → N11, N17; 145 → N1, N3; 146 → O13; 147 → O13; 148 → O14; 149 → O16; 150 → O15; 151 → R1; 152 → R2; 153 → R3; 154 → R4; 155 → R5; 156 → Q3; 157 → N16; 158 → N15; 159 → Q4; 160 → N14; 161 → N10; 162 → O6; 163 → E16; 164 → A32; 165 → A34.

**desktop-quickshell.json** (entry → rows): 0 → A14, A17; 1 → A15, B6, C4; 2 → A10, A11; 3 → B1, B2; 4 → B3; 5 → B4; 6 → B5; 7 → B8; 8 → B9; 9 → B10; 10 → B11, B12; 11 → B13; 12 → B15; 13 → B17; 14 → B18; 15 → C1; 16 → C2, C3; 17 → C5; 18 → C6; 19 → C7, C8, C10; 20 → C11; 21 → C12; 22 → C13, C14, C15; 23 → C16; 24 → C17; 25 → D2; 26 → D1; 27 → K6; 28 → D5; 29 → D3; 30 → D6; 31 → D8; 32 → D9; 33 → D10; 34 → D13, H12, H13; 35 → E7, E8; 36 → E10; 37 → E11; 38 → E9; 39 → E5; 40 → E14; 41 → E12, E13; 42 → E15; 43 → F7, L2; 44 → L3, L4; 45 → K10; 46 → E4; 47 → E3; 48 → F1; 49 → F2; 50 → F3; 51 → F4; 52 → F5, F6; 53 → A23; 54 → O1, O2; 55 → O4; 56 → O5; 57 → O6; 58 → O7; 59 → O8; 60 → G21; 61 → G28; 62 → G22; 63 → G23; 64 → G24, J11; 65 → G25; 66 → G26; 67 → A9; 68 → A1; 69 → G27; 70 → G29; 71 → H1; 72 → H2, H3; 73 → H4; 74 → H5; 75 → I3; 76 → I5, I6; 77 → I7; 78 → I8; 79 → I9; 80 → I10; 81 → I11; 82 → I14; 83 → I16; 84 → I17; 85 → H20; 86 → I19; 87 → B22; 88 → B23, L7, L9; 89 → L13; 90 → L11; 91 → L12; 92 → L14; 93 → B19; 94 → B20; 95 → B21; 96 → O10; 97 → M2; 98 → M5; 99 → M9; 100 → M7; 101 → G3, G5; 102 → G7, G9, G10; 103 → G31; 104 → G30; 105 → N9, N10; 106 → J8, J19; 107 → J18; 108 → J5; 109 → J20; 110 → A25, J21; 111 → J9; 112 → J22; 113 → D12; 114 → A21, J23; 115 → H17; 116 → K2, K3; 117 → K1, K4; 118 → K8; 119 → K9; 120 → A27; 121 → A22; 122 → A18; 123 → H8, H9; 124 → A33; 125 → A20; 126 → A26; 127 → N12; 128 → N11; 129 → N13; 130 → N3; 131 → N1; 132 → K14; 133 → P3; 134 → J14; 135 → H18; 136 → P4; 137 → H19; 138 → O16; 139 → O11; 140 → O12; 141 → A29; 142 → A31; 143 → A16, A30; 144 → Q1; 145 → Q3; 146 → O9; 147 → L12, N7; 148 → N5, N6; 149 → N18; 150 → N19.
