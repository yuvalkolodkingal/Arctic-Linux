# Arctic Linux 0.3 — Launcher, command menu, theming, onboarding and accessibility

Part of the [0.3 plan](../PLAN-0.3.md).

This section covers the experience part of request #6 ("research all useful desktop and omarchy
features we need to add"). It also builds two pieces other requests rely on: the command menu
that hosts the Install and Remove branches of requests #1 and #4 (the rows themselves belong to
the Get apps section), and the capture menu for keyboards without Print (request #5; the rows
belong to the shortcuts section). It implements D8 for the items below, D9 for every surface it
adds, and ships in Arctic Linux 0.3.0 (D1).

Gap items handled here (priorities from `gap-list.json`, corrections from
`gap-verification.json` applied; "missed" = found by the verification pass):

| Gap item | Priority | Where | Status in 0.3.0 |
|---|---|---|---|
| `command-menu` (menu tree, capture menu, dmenu mode) | P1 | §4 | implemented |
| `first-login-welcome` (and first-boot progress) | P1 | §9 | implemented |
| `launcher-search-modes` (settings, windows, web, files, units, app actions, ranking) | P2 | §5 | implemented |
| `osd-kinds` | P2 | §6 | implemented |
| `auto-dark-schedule` (with the `arctic-theme light\|dark` correction) | P2 | §7.1 | implemented |
| `theme-gallery` (allowlist, not denylist) | P2 | §7.2 | implemented; packaging `v2-walls/` deferred (§7.2.7) |
| `fonts-symbols` (Nerd symbols packaged by Arctic; emoji font correction) | P2 | §7.3 | implemented |
| `accessibility-page` | P2 | §8 | implemented |
| `weather` (optional, off by default) | P2 | §12 | implemented |
| `reminders` | P2 | §13 | implemented |
| `user-hooks` (theme hooks already exist; only the other events are new) | P2 | §14 | implemented |
| Missed: system resource monitor | P2 | §11 | implemented (off the bar by default) |
| Missed: show/hide the bar (and glances while it is hidden) | P2 | §10 | implemented |
| Missed: running-apps list (the "taskbar" objection to the skip list) | P1/P2 | §4.6 (Open windows branch), §5.4 | answered without a dock |
| Missed: wallpaper rotation | P3 | §15 | planned last; may slip to 0.3.1 without harm |
| Missed: dictation | P2/P3 | §16 | deferred, with the reasons |

Every other P2 item is owned elsewhere: `launcher-uninstall-key` and `tui-launchers` (Get apps
section), `chromium-theme-policy`, `launch-or-focus` and `default-app-roles` (web-app engine
section; the shortcuts section also plans launch-or-focus keys), the bar and quick-settings items
(bar section), the capture, clipboard, emoji, keys-sheet, hardware-key, Alt+Tab, drop-down and
window items (shortcuts section), and the system list (`display-mode-mirror`,
`power-menu-extras`, `game-mode`, `users-sign-in`, `firewall-ssh`,
`share-localsend-kdeconnect`, `snapshots-ui`, `system-tools`, `idle-dim`,
`fedora-upgrade-whats-new` and the P0/P1 system items) in the system section. The verification's
"reduced effects on VMs" note belongs with `game-mode` there.

Facts marked ✅ were checked on 2026-09-28 in the repository, in the Mango 0.17.3 source (tag
`0.17.3`, `f5b77ad`), in Quickshell at Fedora's snapshot commit `dacfa9de829a`, or in Fedora 44
metadata (`mdapi.fedoraproject.org/f44/pkg/<name>`). Facts marked 🔍 are unverified; each one
names the check that proves it. §25 lists them all.

---

### 1. Current state (0.2.1)

#### 1.1 The launcher

- `shell/Launcher.qml` (305 lines) is a `Popover` card, 520 px wide, with three views: `home`,
  `apps` and `get` (`:18`).
- With nothing typed, `home` shows the specials (`:47-56`): Install Arctic Linux (live only), Apps,
  Get apps, Wallpapers, Settings, Fetch.
- Typing ranks the specials and every `DesktopEntries.applications` entry that isn't `noDisplay`
  (`:57-61`, `:62-75`), capped at 50 rows. Settings' own desktop entry is filtered out because
  the Settings special exists (`:73-74`).
- `shell/LauncherSearch.js` (69 lines) is the ranking: name match (exact, prefix, word start,
  substring, initials), then keywords, then a fuzzy name match for three or more characters
  (`:11-47`). `mode()` (`:63-69`) knows two prefixes: `=` (calculator) and `>` (command).
- `shell/Calc.js` (128 lines) is a safe arithmetic parser (no `eval`). It has no units, currency
  or number bases. Enter copies the result with `wl-copy` (`Launcher.qml:99`).
- `>` runs `sh -c` detached, Shift+Enter in the terminal (`Launcher.qml:100-104`).
- There are no settings, window, file, web or app-action results, and no ranking by use.
- Keys (`:175-181`): ↑/↓ and Tab/Shift+Tab move, Enter opens, Shift+Enter is the alternate
  action, Esc clears the text in `home`, else goes back or closes.
- IPC `launcher toggle|open|close|search` (`shell/shell.qml:84-94`);
  `arctic-launcher [TEXT]` wraps it and falls back to fuzzel (`dotfiles/.local/bin/arctic-launcher:8-11`).

#### 1.2 No command menu

- There is no tree of system actions. The only menus are the power menu (`shell/PowerMenu.qml`,
  `Super + Escape`, `arctic-power`) and the launcher specials.
- Nothing can open a branch from a script, and there is no toggle, capture, style or setup menu.
- Helpers that need a picker use fuzzel directly (`arctic-power:28`, `binds.conf:23` for the
  clipboard). No helper can ask the shell for a choice or a line of text.
- `Super + Alt + Space` and `Super + Ctrl + C` are unbound (`binds.conf:8-109`, `apps.conf:6-10`);
  the shortcuts section's authoritative key table assigns them to this section (rows 46 and 47).

#### 1.3 On-screen display

- `shell/Osd.qml` (139 lines): one 280×48 frost pill, bottom centre, 44 px above the edge
  (`:72-86`). Two kinds: volume (follows every PipeWire change, `:50-53`) and brightness (read
  from `brightnessctl -m`, `:54-69`). Visible 1.2 s, then a fade (`:38-48`, `:70`).
- IPC `osd volume|brightness` (`shell.qml:113-117`).
- `arctic-osd mic mute` bypasses the shell and always sends a mako notification
  (`dotfiles/.local/bin/arctic-osd:36-40`).
- The bar and shortcuts sections add level and label kinds (`showPower`, `showLayout`,
  `brightnessLevel`, `showKeyboard`, `showMic`, `showTouchpad`) but no shared model and no
  generic "icon and label" kind; the shortcuts section waits for this one (its §17).

#### 1.4 Theming

- `dotfiles/.local/bin/arctic-theme` (Python, ~690 lines) switches between Winter, Polar night,
  the theme made from the wallpaper and the user's themes in `~/.config/arctic/themes`
  (`theme_dir`, `:114-121`). The contract is `docs/BUILD-SPEC.md` §10 (9.1-9.7).
- `arctic-theme light|dark` (`:679-684`) changes the wallpaper theme's mode when auto colours are
  on, else switches to Winter or Polar night. `toggle` (`:591-597`) does the same flip.
- `arctic-theme mode light|dark` only sets the wallpaper theme's mode (`cmd_mode`, `:561-574`); with
  auto colours off it does nothing to Winter or Polar night. That is why the schedule must call
  `arctic-theme light|dark` (correction applied, §7.1).
- There is no schedule. The switch is manual: `Super + Shift + T` (`binds.conf:79`), Settings >
  Appearance (`settings/pages/AppearancePage.qml:97-173`), or `arctic-theme toggle`.
- Only two static palettes ship (`design/themegen/palette.py:39-43`, `BUILTINS`). Named palettes
  (Nord, Catppuccin and others) exist only as wallpaper folders in `v2-walls/` (412 MB, 18
  folders), which no package installs and which carry no licence records.
- The theme engine checks contrast for every derived palette (`design/themegen/derive.py:52-57`,
  `GUARANTEES`; `arctic-themegen check`), but has no high-contrast variant.
- Theme hooks exist: `arctic-theme` runs every executable in
  `/usr/share/arctic/theme-hooks.d` and `~/.config/arctic/theme-hooks.d` after a switch
  (`HOOK_DIRS`, `:53`; `run_hooks`, `:456-496`), with `ARCTIC_THEME_DIR`, `ARCTIC_THEME_MODE`,
  `ARCTIC_THEME_NAME`, a 5 s limit, and the output passed on as a warning. A user file replaces
  the system hook of the same name. No other event has hooks.

#### 1.5 Fonts

- Figtree for the interface (`arctic-fonts`, spec `:126-135`), JetBrains Mono for code
  (`jetbrains-mono-fonts-all`, spec `:194`, `:449`), Noto Sans with Hebrew, Arabic and CJK
  (spec `:450-455`).
- The terminal font is written into each account's copy of the terminal config:
  `dotfiles/.config/kitty/kitty.conf:6-10`, `foot/foot.ini:5`, `alacritty/alacritty.toml:7-9`
  (10.5 pt). These files come from `/etc/skel`, so package updates never change them.
- GTK: `monospace-font-name='JetBrains Mono 10'` (`packaging/dconf/10-arctic:19`).
- The shell picks its mono family from the theme tokens (`shell/Theme.qml:68`).
- There is no font picker and no Nerd Font symbol fallback, so yazi and eza show boxes. Fedora 44
  has no symbols-only Nerd Font package (verification: `nerd-fonts`, `symbols-nerd-fonts`,
  `nerd-fonts-symbols`, `symbols-only-nerd-fonts` all return 400).
- The only emoji font in the ISO is the black-and-white `google-noto-emoji-fonts`
  (`iso/kiwi/config.kiwi:154`). The colour font is `google-noto-color-emoji-fonts` ✅ (mdapi
  200). The shortcuts section makes that kiwi change with its emoji picker (its §11).
- Text size: Settings sets GTK's `text-scaling-factor` only (`AppearancePage.qml:471-488`,
  `arctic_settings.py:2216-2239`). The row says "The bar and menus keep their size". The shell
  hard-codes 57 `font.pixelSize` values across `shell/*.qml`.

#### 1.6 Accessibility

- Reduce motion, GTK text size, pointer size and pointer style live in Settings > Appearance
  (`AppearancePage.qml:449-518`: "Text and motion" `:449-488`, "Pointer" `:490-518`).
- `design/exports/mango-arctic.conf:33` refers to "the Settings > Accessibility switch", which
  doesn't exist.
- There is no high-contrast mode, no keyboard-driven pointer, and nothing that says why a screen
  reader, magnifier or on-screen keyboard is missing.

#### 1.7 Onboarding

- `shell/LiveWelcome.qml` (191 lines) is the live USB's "You're trying Arctic Linux" card on the
  desktop layer (`:36-46`), opened by `arctic-welcome` through `arctic-shell-ipc welcome open`
  (`shell.qml:125-129`).
- `dotfiles/.local/bin/arctic-welcome:10` exits at once on an installed system
  (`arctic-is-live || exit 0`), so an installed system has no welcome.
- `packaging/firstboot/arctic-firstboot` (333 lines) installs the apps the installer put off. It
  runs as a root system service at boot (`packaging/systemd/arctic-firstboot.service`) and says
  nothing: it can't `notify-send` into the user's session (verification correction). It rewrites
  `/var/lib/arctic/pending.json` (`main`, `:303-333`) and nothing else.
- The pattern to copy exists: `arctic-update` writes `/var/lib/arctic/update-status.json` as root
  and `shell/UpdateService.qml` watches it (`:13`, `:56-60`) and raises notifications once.

#### 1.8 The bar and the wallpaper

- `shell/Bar.qml:14-27`: one `PanelWindow` per screen, anchored top, 34 px (`Theme.barHeight`),
  `exclusiveZone` bar + frame. It can't be hidden.
- The design fixes a calm 34 px top bar ("The bar is 34px", `design/brand-book.md:70`;
  "The bar stays 34 logical px", `design/guidelines/10-platforms.md:23`), and the gap list's skip
  list rules out repositioning, drag-to-reorder, transparency and resource graphs on the bar for
  that reason. Hiding it on demand changes neither its size nor its place, so it doesn't break the
  rule (§10).
- `shell/Popover.qml:40` and `shell/ScreenFrame.qml:23` start below the bar
  (`margins.top: Theme.barHeight`); the frame reserves left, right and bottom only
  (`ScreenFrame.qml:74-90`).
- `dotfiles/.local/bin/arctic-wallpaper` draws one saved choice with swaybg; there is no rotation.

#### 1.9 Missing entirely

Weather, reminders, a resource monitor, user hooks for anything but theme switches, and a way to
find an open window from the launcher.

#### 1.10 Corrections applied from the research

| Item | Correction (from `gap-verification.json`) | Applied in |
|---|---|---|
| `command-menu` | Omarchy builds the tree from dotted ids plus `target` links, not `children` arrays | §4.2 uses dotted ids and `target` |
| `command-menu` | `omarchy-menu-select` uses a selection file and a done file, not a FIFO | §4.9 uses a request file and a FIFO, the same handshake as the shortcuts section's capture overlay; the difference is noted |
| `command-menu` | Omarchy 4's root menu is `Super + Space` and `Super + Alt + Space` is its apps menu | Arctic keeps `Super + Space` = launcher (the design's key) and puts the menu on `Super + Alt + Space`; the launcher searches menu rows too (§5.5) |
| `command-menu` | `Super + Alt + Space` also switches the layout under `grp:alt_space_toggle` | Settings warns (shortcuts section §15); §3 |
| `launcher-search-modes` | focusing a window is `mmsg dispatch focusid client,<id>`; `ToplevelManager` is an alternative | §5.4 |
| `auto-dark-schedule` | the schedule must call `arctic-theme light\|dark`, not `mode` | §7.1 |
| `theme-gallery` | Omarchy's filter is a denylist; an allowlist of colour files is stricter | §7.2.5 |
| `fonts-symbols` | no Fedora package; Arctic packages the font | §7.3.2 |
| `fonts-symbols` / emoji | the colour emoji font is `google-noto-color-emoji-fonts`; fix kiwi | shortcuts section §11 makes the edit; §19 checks it |
| `first-login-welcome` | `arctic-welcome:10` exits on installed systems; firstboot can't notify | §9 |
| `weather` | Omarchy's bar weather uses wttr.in; Open-Meteo backs its Elsewhen panel | §12 (Open-Meteo chosen on its own merits) |
| `reminders` | Omarchy uses three keys (set, show, clear) | §13 uses one key that opens the Reminders branch |
| `user-hooks` | theme hooks exist; generalise that contract, no parallel `theme-set.d` | §14 |
| missed gaps | resource monitor, bar toggle and notices, wallpaper rotation, dictation, dock | §10, §11, §15, §16, §4.6 |

---

### 2. Design principles and shared pieces

1. **Helpers first.** Every key runs an `arctic-*` helper in `dotfiles/.local/bin`, which tries
   the shell over IPC and falls back to fuzzel or a notification, as `arctic-launcher` and
   `arctic-screenshot` do. The fallback session (`ARCTIC_SHELL=waybar`) keeps working.
2. **One JSON line.** Helper commands with `--json` print exactly one line:
   `{"ok":true,…}` or `{"ok":false,"code":"…","error":"One sentence."}`, keys in snake_case
   (the web-app engine's rule, D4; the shortcuts section's `arctic-capture`).
   `arctic_settings.py` keeps its own convention (camelCase for multi-word keys, as `switchKeys`,
   `customBinds`), because Settings passes its answers straight to QML.
3. **Data, not code, where users extend things.** The menu is JSON, hooks are executables in
   folders, themes are colour files. Shipped menu rows run argv lists, never shell strings.
4. **Nothing leaves the machine unless the person asked.** Weather is off by default, the web
   search sends nothing until Enter, a theme is downloaded only from a URL the person pasted,
   file search is local. No IP geolocation anywhere.
5. **Calm bar.** New bar content (weather, CPU and memory) is off by default. Hiding the bar is a
   key, not a setting that moves it.
6. **Tokens only; amber only for "here" (D9).** Amber appears on the selected row, the current
   theme card, today's date and the one primary button of a card. Meters, weather, OSD notices
   and the welcome's mark are never amber. The new first-login card draws the fox mark without
   the amber eyes the live card uses.
7. **Keyboard first, never keyboard only.** Every new surface is complete from the keyboard and
   shows a focus ring.

**Shared pieces this section adds (used by several parts below):**

| Piece | File | Used by |
|---|---|---|
| `Theme.fs(px)`, `Theme.rowH(px)`, `Theme.textScale` | `shell/Theme.qml` | every shell surface (§7.3.3) |
| `Theme.topInset` (0 when the bar is hidden, else `barHeight`) | `shell/Theme.qml` | `Popover.qml`, `ScreenFrame.qml`, the bar section's toasts and menus (§10) |
| `Theme.highContrast` (`theme.json` `"contrast": "high"`) | `shell/Theme.qml` | wider borders and focus rings (§8.2) |
| `Session.barHidden` and the new `shell.json` keys | `shell/Session.qml` | §5, §10, §11, §12 |
| New glyphs | `shell/assets/icons-extra.js` (the bar section creates the file) | §4-§13 |
| Location and sun times | `dotfiles/.local/bin/arctic-sun`, `~/.config/arctic/location.json` | §7.1, §12, night light (system section) |
| Hooks | `dotfiles/.local/bin/arctic-hook` | §14 |
| Windows list | `shell/WindowList.qml` | §4.6, §5.4 |

`shell.json` keys added here (camelCase, like the existing `frame`; this settles the bar
section's open question 15 for these keys, and `shell-set` in `arctic_settings.py` takes them
as written):

| Key | Type, default | Meaning |
|---|---|---|
| `textScale` | number, 1 | shell text scale, clamped to 1.0-1.25 by the shell |
| `monoFont` | string, "" | code font family for the shell (`arctic-font set` writes it) |
| `webSearch` | `duckduckgo`\|`startpage`\|`brave`\|`google`\|`bing`\|`kagi`\|`ecosia`\|`custom`, `duckduckgo` | launcher web search |
| `webSearchUrl` | string, "" | `https://…%s…`, used when `webSearch` is `custom` |
| `fileSearch` | bool, true | files in mixed launcher results (the `/` prefix always works) |
| `weather` | bool, false | weather on (§12) |
| `weatherUnits` | `auto`\|`metric`\|`imperial`, `auto` | |
| `barWeather` | bool, false | temperature item on the bar |
| `barSystem` | bool, false | CPU and memory item on the bar |

---

### 3. Keys

The shortcuts section's table (its §3.2) is the one authoritative list of Mango binds in 0.3.0.
This section uses four of its rows and adds three. The additions go into that table and its tests
(`test_no_duplicate_binds`, `test_binds_avoid_layout_switch_chords`,
`test_every_bind_is_described`) as rows 56-58.

| # | Keys | Mango line (`binds.conf`) | Does | Check |
|---|---|---|---|---|
| 46 | `Super + Alt + Space` | `bind=SUPER+ALT,space,spawn,arctic-menu` | Command menu (root) | free ✅; also switches layout under `grp:alt_space_toggle` (Settings warns) |
| 47 | `Super + Ctrl + C` | `bind=SUPER+CTRL,c,spawn,arctic-menu capture` | Capture menu | free ✅; `Super + Shift + C` (colour picker) differs by modifier |
| 51 | `Super + Alt + K` | `bind=SUPER+ALT,k,spawn,arctic-kbptr` | Keyboard pointer (wl-kbptr) | free ✅ |
| 54 | `Super + Ctrl + R` | `bind=SUPER+CTRL,r,spawn,arctic-menu remind` | Reminders branch (set, list, cancel) | free ✅; Omarchy's extra show/clear keys are not copied (`Super + Ctrl + Shift + R` holds Ctrl + Shift) |
| **56** | `Super + Shift + Space` | `bind=SUPER+SHIFT,space,spawn,arctic-shell-ipc bar toggleHidden` | Hide / show the top bar | free ✅ (only `SUPER,space` is bound, `binds.conf:14`); no layout option uses Shift + Space; Omarchy's key |
| **57** | Caps Lock (tap) | `bindrp=NONE,Caps_Lock,spawn,arctic-osd lock-keys` | Caps Lock OSD | free ✅; `r` = on release, `p` = the release still reaches the app; see §6.4 |
| **58** | Num Lock (tap) | `bindrp=NONE,Num_Lock,spawn,arctic-osd lock-keys` | Num Lock OSD | free ✅; same flags |

Checks done for rows 56-58, with the shortcuts section's method (its §3.1):

- Normalised as (keymode, modifier set, lower-cased key) against every `bind*=` in `apps.conf:6-10`,
  `binds.conf:8-109`, every other row of that table, and `keys.txt:3-50`: no match.
- Against the eight `SWITCH_KEYS` options (`arctic_settings.py:2053-2054`): no row holds
  Alt + Shift, Ctrl + Shift or Alt + Space, and no option uses Num Lock. Row 57 is the Caps key itself:
  - under `grp:caps_toggle` the key switches layouts; the bind still fires on release, the Caps
    Lock LED doesn't change, so `lock-keys` shows nothing (§6.4); the switch itself is untouched
    because the press is not bound and `p` passes the release;
  - under `grp:alt_caps_toggle` the release has Alt held, so `NONE` doesn't match;
  - under `caps:escape`, `ctrl:nocaps`, `caps:super` or `caps:backspace` (`CAPS_OPTIONS`,
    `:2055`) the bind resolves to keycode 66 through Mango's fallback to the `us` layout
    (Mango docs, bindings/keys.md), fires, and again finds no LED change.
- Mango facts ✅ (`src/config/parse_config.c:175-205`, `src/input/keyboard.c:560-608`):
  bind flags may come in any order; a release bind fires only when the released key is the last
  key pressed (`server.last_hold_keycode`). Mango compares binds with `wlr_keyboard_get_modifiers()`,
  which leaves locked modifiers out ✅ (wlroots 0.19 `types/wlr_keyboard.c:286-296`: depressed |
  latched only), so a locked Caps Lock or Num Lock never stops a `NONE` bind from matching.

`#:` lines for the generated sheet (the shortcuts section's §13 grammar):

```
# ---- in "Everyday", after the launcher row ----
#: Commands and settings (the Arctic menu)
bind=SUPER+ALT,space,spawn,arctic-menu
# ---- in "Capture" ----
#: Capture menu (every capture tool, for keyboards without Print)
bind=SUPER+CTRL,c,spawn,arctic-menu capture
# ---- in "System" ----
#: Reminders
bind=SUPER+CTRL,r,spawn,arctic-menu remind
#: Hide or show the top bar
bind=SUPER+SHIFT,space,spawn,arctic-shell-ipc bar toggleHidden
#: Keyboard pointer (move and click with the keyboard)
bind=SUPER+ALT,k,spawn,arctic-kbptr
# ---- in "System", changed line (binds.conf:79 today) ----
#: Switch Winter / Polar night
bind=SUPER+SHIFT,t,spawn,arctic-theme toggle --osd
# ---- in "Hardware keys" ----
#: Caps Lock, Num Lock :: Shows whether it is on
bindrp=NONE,Caps_Lock,spawn,arctic-osd lock-keys
#-
bindrp=NONE,Num_Lock,spawn,arctic-osd lock-keys
```

Keys inside this section's surfaces (not Mango binds; they work only while an Arctic layer has
exclusive keyboard focus, and none holds Alt + Shift, Ctrl + Shift or Alt + Space):

| Surface | Keys |
|---|---|
| Command menu (§4.8) | type, ↑ ↓, Tab / Shift + Tab, Enter, → (open branch), ← or Backspace on an empty field (up), Delete (on provider rows that allow it), Esc |
| Launcher additions (§5.11) | `/` `~` `?` prefixes; Shift + Enter on a file row (open its folder); Enter on a window row (focus); Delete on a window row (close) |
| First-login card (§9.2) | Tab / Shift + Tab, Enter, Space, digits 1-5 (steps), Esc |
| System panel (§11) | the bar section's `MenuList` keys; Enter on a process opens its actions |
| Settings (§8, §7.2) | standard Settings keys; theme grid: arrows, Enter |

---

### 4. Command menu (`command-menu`, P1)

#### 4.1 What it is

One keyboard-driven, searchable tree of every system action, openable at any branch from a key,
a script or another surface. It is drawn inside the launcher card (a fourth launcher view,
`menu`), so it looks like the launcher, shares its one-popover-at-a-time rule and its scrim, and
costs no new layer surface.

- `Super + Alt + Space` opens the root; `Super + Ctrl + C` opens `capture`; `Super + Ctrl + R`
  opens `remind`.
- `arctic-menu <route>` opens any branch from a script; routes are dotted ids (`style.theme`).
- The launcher's home gets a special row "Commands and settings" (kind `menu`, glyph `menu`,
  desc "Every system action · Super + Alt + Space").
- Typing in the plain launcher also finds menu rows (§5.5), so the menu is never the only way in.

Files (all new unless noted):

| File | What |
|---|---|
| `shell/CommandMenu.js` | Pure model (`.pragma library`, tested with Node): merge, tree, routes, guards, providers, search, validation |
| `shell/CommandMenuService.qml` | Singleton: reads `shell/menu/*.json` and `~/.config/arctic/menu.json` (`FileView`, watched), runs guard batches, provider processes and select/input requests |
| `shell/CommandMenu.qml` | The view embedded in `Launcher.qml` (like `GetApps` from the Get apps section) |
| `shell/LauncherRow.qml` | The launcher's row delegate moved out of `Launcher.qml:213-266`, with a `compact` (44 px) variant; the command menu and the launcher both use it |
| `shell/WindowList.qml` | Singleton: open windows from `mmsg get all-clients` (fallback `ToplevelManager`), `focus(id)`, `close(id)` |
| `shell/menu/00-arctic.json` | Root branches and this section's rows (§4.6) |
| `shell/menu/20-capture.json` | Capture rows — **owned by the shortcuts section** (its §10) |
| `shell/menu/30-apps.json` | Install and Remove rows — **owned by the Get apps section** (its §5) |
| `shell/menu/40-system.json` | Update, share, display and restart rows — **owned by the system section** |
| `dotfiles/.local/bin/arctic-menu` | Python 3 helper: open routes, dmenu-style `select` and `input`, `list`, fuzzel fallback |

One file per owning section keeps merges apart: files are merged in name order, then the user's
file. A section adds rows by adding its own file; no section edits another's.

#### 4.2 Data format

```json
{
  "version": 1,
  "entries": {
    "capture":          {"label": "Capture", "icon": "camera", "keys": "Super + Ctrl + C", "order": 30},
    "capture.area":     {"label": "Screenshot of an area", "icon": "camera", "keys": "Print",
                         "run": ["arctic-screenshot", "area"]},
    "style.theme":      {"label": "Theme", "icon": "palette", "provider": "themes"},
    "setup.display":    {"label": "Displays", "icon": "display", "run": ["arctic-settings", "displays"]},
    "apps":             {"label": "Apps", "icon": "grid", "shell": "openView", "args": ["apps"], "order": 10},
    "remove.flatpak":   {"label": "Flatpak apps", "icon": "package", "shell": "openGetApps",
                         "args": ["remove/flatpak"], "when": {"count": "flatpak"}},
    "system.restart":   {"label": "Restart", "icon": "restart", "run": ["arctic-power", "restart"],
                         "confirm": "Restart now? Apps that are open will close."}
  }
}
```

- **Ids** match `^[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)*$`. The dotted id is the tree
  (Omarchy's model, correction applied): `capture.area` is a child of `capture`; an id without a
  dot sits on the root. There is no `children` array and no `parent` field.
- **Fields**

  | Field | Meaning |
  |---|---|
  | `label` | Row text (required). One line, ≤ 80 characters |
  | `title` | Header when the branch is open; defaults to `label` |
  | `desc` | Second line; also searched |
  | `icon` | An Arctic glyph name (`design-data.js` or `icons-extra.js`); anything else is refused (D9) |
  | `keys` | Shortcut text shown as `Kbd` chips on the right ("Super + Ctrl + C") |
  | `order` | Integer; siblings sort by `order`, then by file order. Default 1000 |
  | `run` | argv list, started detached (`Quickshell.execDetached`) |
  | `shell` + `args` | A named in-process function from the allowlist below |
  | `target` | Another id to open instead (a link) |
  | `provider` | Rows come from a named provider at run time (§4.5) |
  | `when` | Guard: the row is hidden when it fails |
  | `checked` | Guard: a check mark when it passes (the current choice) |
  | `disabled` | Guard: listed, dimmed, skipped by the cursor and by search |
  | `confirm` | A sentence; the row asks before it runs (§4.8) |
  | `close` | Bool, default true: the launcher closes before the action runs |
  | `sh` | A shell string, run with `sh -c` — **only accepted from the user's file** |
- Kind is inferred as in Omarchy: `run`/`shell`/`sh` = action, `target` = link, `provider` = runtime
  branch, otherwise a branch. An entry with none of these and no children is dropped at load.
- **Merge** (`CommandMenu.merge(sources)`): files in name order, then
  `~/.config/arctic/menu.json`. Reusing an id replaces only the fields given, and the entry keeps
  its first position; new ids append. A user entry with `"hidden": true` removes a shipped row.
- **The user's file** has the same format; `sh` actions and `{"sh": …}` guards are allowed there.
  A file that fails to parse is ignored as a whole and the shell shows one toast per change:
  "Your menu.json has an error on line 12. The Arctic menu is shown without it."
- Shipped files are strict JSON (no comments), checked by `test-command-menu.cjs` (§20).

**`shell` verbs** (the allowlist; the service maps each to one function in `shell.qml`):

| Verb | Args | Calls |
|---|---|---|
| `openView` | `apps`\|`home` | `launcher.openView(name)` |
| `openGetApps` | page (`choose`, `flatpak`, `dnf`, `web`, `terminal`, `remove`, `remove/<tab>`, `console`) | `shell.openGetApps(null, page, '')` (Get apps section §5) |
| `openPanel` | panel id | `shell.openPanel(id, null)` (bar section §3.2) |
| `openQuick` | page | `shell.openQuick(page, null)` |
| `toggleWallpapers`, `toggleKeys`, `togglePower`, `lock` | — | existing `shell.qml` functions |
| `toggleBar` | — | §10 |
| `openWelcome` | — | §9 |
| `toggle` | registry key, `on`\|`off`\|`toggle` | `ToggleRegistry.set(key, mode, 'menu')` (bar section §5.11) |
| `settings` | page, optional search key | `arctic-settings PAGE [KEY]` (§5.3) |
| `url` | https URL | `xdg-open URL` (only `https://`) |

#### 4.3 Guards

A guard is an object; several keys in one object must all pass.

| Predicate | Passes when | Evaluated |
|---|---|---|
| `{"live": true\|false}` | `Session.live` equals it | in QML |
| `{"outputs": 2}` | at least that many screens | in QML |
| `{"battery": true}` | UPower reports a laptop battery | in QML |
| `{"toggle": "night-light", "state": "on"\|"off"\|"available"}` | the bar section's `ToggleRegistry` agrees | in QML |
| `{"count": "flatpak"\|"dnf"\|"web"\|"terminal"}` | the Get apps section's cached `apps.py counts` is > 0 | in QML (cache) |
| `{"command": "swappy"}` | `command -v` finds it | batched |
| `{"file": "/path"}` | the path exists | batched |
| `{"shell": true}` | the shell is running (always true inside it; used by `arctic-menu list --fallback`) | in QML / helper |
| `{"sh": "…"}` | the command exits 0 (user file only) | batched per open |

- **Batching**: at load and on `menu refresh`, one process answers every `command` and `file`
  guard of the whole tree:
  `sh -c 'for a; do case $a in c:*) command -v "${a#c:}" >/dev/null 2>&1;; f:*) test -e "${a#f:}";; esac && echo "$a"; done' sh c:swappy f:/usr/bin/foo …`.
  The answers are cached until the next refresh (and at most 60 s when the menu opens).
- User `sh` guards run in one `bash` per open, printing `<id>:<w|c|d>:<0|1>` lines; the menu opens
  at once on the previous answers (Omarchy's approach) and updates when the batch ends (2 s limit).
- Remove-style rows use `when` (hidden when there is nothing to remove); install-style catalog rows
  use `disabled` (shown as installed), as Omarchy's docs recommend.

#### 4.4 Actions

- A `run` row starts `Quickshell.execDetached({command: argv})`. `run[0]` must be an `arctic-*`
  helper, `xdg-open`, or a command on the shipped allowlist in `CommandMenu.js`
  (`RUN_ALLOW`: `arctic-*`, `xdg-open`, `playerctl`, `systemctl`, `loginctl`, `mmsg`, `qalc`);
  the test fails on anything else in a shipped file. A row that needs anything more (a pipeline,
  `pkexec`, two commands in a row) goes through an `arctic-*` helper, as every key does; widening
  `RUN_ALLOW` is a reviewed change to `CommandMenu.js`.
- By default the launcher closes first, then the action runs after the layer unmaps (a 120 ms
  `Timer`, as the emoji picker does), so screenshots never show the menu.
- `close: false` keeps it open (toggles, theme choices): the row updates in place.
- Actions never build shell text from labels or typed input.

#### 4.5 Providers

Providers fill a branch at run time. Names are fixed in `CommandMenuService.qml`; a user file can
point a branch at one but can't define a new one.

| Provider | Rows | Enter | Delete | Source |
|---|---|---|---|---|
| `toggles` | every `ToggleRegistry` entry that is `available`, "Night light" with detail "On until 07:00", ✓ when on | `ToggleRegistry.set(key, 'toggle', 'menu')`, menu stays open | — | bar section §5.11 |
| `themes` | every theme, gallery ones included, ✓ on the active one, detail "Dark · pairs with Catppuccin Latte" | `arctic-theme set NAME` | — | `arctic-theme list --json` (§7.2) |
| `schedule` | Off, Sunset to sunrise, Custom hours… (✓ current) | `arctic-theme schedule off\|sun`; Custom opens Settings at `appearance.schedule` | — | `arctic-theme schedule --json` |
| `fonts` | monospace families, ✓ current | `arctic-font set FAMILY` | — | `arctic-font list --json` (§7.3) |
| `text-size` | 100 %, 110 %, 125 %, 150 %, 175 %, 200 %, ✓ current | `arctic_settings.py text-size F` | — | §7.3.3 |
| `settings-pages` | one row per Settings page (from the generated index) | `arctic-settings ID` | — | §5.3 |
| `reminders` | queued reminders: "Tea", detail "15:40 · in 12 min" | opens a one-row page "Cancel this reminder" | cancel | `RemindService` (§13) |
| `windows` | open windows: title, detail "Firefox · workspace 2 · DP-1" or "Hidden" | `WindowList.focus(id)` | close the window (`mmsg dispatch killclient client,<id>`, a normal close request) | `WindowList` (§5.4) |

A provider re-runs each time its branch is entered (`themes`, `fonts` and `windows` change), never
per keystroke. Rows get ids `<branch>.<slug(value)>`; a clash gets `-2`.

#### 4.6 The tree

Rows owned here (`shell/menu/00-arctic.json`), in root order. Branch rows owned by other sections
are listed with their owner.

| Id | Label | Glyph | Action / contents | Guard |
|---|---|---|---|---|
| `apps` | Apps | `grid` | `shell openView apps` | — |
| `learn` | Learn | `help` | branch | — |
| `learn.keys` | Keyboard shortcuts | `keyboard` | `shell toggleKeys`; keys "Super + /" | — |
| `learn.welcome` | Show the welcome again | `snowflake` | `shell openWelcome` | `{"live": false}` |
| `learn.tour` | Desktop tour | `compass` | `url https://github.com/yuvalkolodkingal/Arctic-Linux/wiki/Desktop-Tour` | — |
| `learn.switching` | Coming from Windows or macOS | `compass` | `url …/wiki/Coming-from-Windows-or-macOS` (new page, §21) | — |
| `learn.wiki` | Arctic Linux wiki | `document` | `url …/wiki` | — |
| `learn.fedora` | Fedora documentation | `document` | `url https://docs.fedoraproject.org/en-US/docs/` | — |
| `learn.mango` | Mango window manager | `tiling` | `url https://github.com/mangowm/mango` 🔍 (a rendered docs site, if upstream has one) | — |
| `learn.about` | About this computer | `info` | `settings about` | — |
| `capture` | Capture | `camera` | branch; keys "Super + Ctrl + C"; rows from `20-capture.json` (shortcuts section §10) | — |
| `toggle` | Toggles | `toggle` | provider `toggles` | — |
| `remind` | Reminders | `timer` | branch; keys "Super + Ctrl + R" | — |
| `remind.add` | Set a reminder… | `plus` | input mode (§4.9): prompt "Remind me", placeholder "10m tea · 15:30 call Dana" → `arctic-remind add …` (§13) | — |
| `remind.list` | Waiting | `clock` | provider `reminders` | `{"toggle": "reminders", "state": "on"}` (on while any reminder waits) |
| `remind.clear` | Cancel all reminders | `x-circle` | `run arctic-remind cancel all`; confirm "Cancel every reminder?" | same |
| `style` | Style | `brush` | branch | — |
| `style.theme` | Theme | `palette` | provider `themes` | — |
| `style.dark` | Switch light and dark | `moon` | `run arctic-theme toggle`; keys "Super + Shift + T"; `close: false` | — |
| `style.schedule` | Switch automatically | `sun-moon` | provider `schedule` | — |
| `style.contrast` | High contrast | `contrast` | `run arctic-theme contrast toggle`; `checked` when on; `close: false` | — |
| `style.wallpaper` | Wallpaper… | `image` | `shell toggleWallpapers`; keys "Super + Shift + W" | — |
| `style.next-wallpaper` | Next wallpaper | `image` | `run arctic-wallpaper next`; `close: false` | rotation folder has pictures (§15) |
| `style.font` | Code font | `type` | provider `fonts` | — |
| `style.text` | Text size | `type` | provider `text-size` | — |
| `style.bar` | Show the top bar | `eye` | `shell toggleBar`; `checked` when shown; keys "Super + Shift + Space" | `{"shell": true}` |
| `style.gallery` | More themes… | `palette` | `settings appearance appearance.gallery` | — |
| `setup` | Settings | `sliders` | provider `settings-pages`, plus: | — |
| `setup.kbptr` | Keyboard pointer | `pointer` | `run arctic-kbptr`; keys "Super + Alt + K" | `{"command": "wl-kbptr"}` |
| `setup.hooks` | Open my hooks folder | `folder` | `run arctic-hook --open` (§14) | — |
| `install` | Install | `package` | branch; keys "Super + Shift + A"; rows from `30-apps.json` (Get apps section §5) | `{"live": false}` for rows that need it (theirs) |
| `remove` | Remove | `trash` | branch; rows from `30-apps.json` | theirs (`count` guards) |
| `update` | Update | `download` | branch; rows from `40-system.json` (system section: check now, Flatpak and firmware, channel, restart subsystems) | — |
| `windows` | Open windows | `window` | provider `windows` | — |
| `activity` | System activity | `activity` | `shell openPanel system` (§11); desc "CPU, memory and the busiest apps" | `{"shell": true}` |
| `system` | System | `power` | branch; keys "Super + Escape" | — |
| `system.lock` | Lock | `lock` | `shell lock`; keys "Super + L" | `{"live": false}` |
| `system.logout` | Log out | `log-out` | `run arctic-power logout`; confirm "Log out now? Apps that are open will close." | `{"live": false}` |
| `system.suspend` | Suspend | `sleep` | `run arctic-power suspend` | `{"live": false}` |
| `system.restart` | Restart | `restart` | `run arctic-power restart`; confirm | — |
| `system.shutdown` | Shut down | `power` | `run arctic-power poweroff`; confirm | — |

- The system section adds Hibernate and "Restart into firmware setup" to `40-system.json` with their
  logind guards, and its "app still installing" warning lives in `arctic-power`, so these rows get
  it for free.
- **Open windows** answers the verification's "running-apps taskbar or dock" missed gap without
  breaking the skip-list decision (no dock; §24): it is a keyboard task list of every window on
  every workspace, with Enter to focus and Delete to close, and the launcher finds windows by
  title (§5.4).

#### 4.7 Search across the tree

- At the root, typing searches every visible row of the tree (branches, actions, provider rows of
  branches already loaded), ranked with `LauncherSearch.rank` on `label` + `desc` + the last id
  segment. Results show a breadcrumb as their second line ("Style › Theme").
- Inside a branch, typing searches that branch's subtree only.
- Disabled rows are left out of results; hidden rows never appear.

#### 4.8 Look and keyboard

- The card is the launcher card (520 px). The query row shows the `menu` glyph and the
  placeholder "Search commands" (at the root) or "Search Capture" (in a branch). A 12 px
  `inkMuted` breadcrumb line sits under the query row ("Menu › Style").
- Rows are `LauncherRow { compact: true }`: 44 px, the glyph in a 28 px tile (the `system` tint,
  like the launcher specials), label 15/600, desc 12 `inkMuted`, and on the right either `Kbd`
  chips for `keys`, a `chevron-right` (`inkMuted`) for branches, or a `check` glyph (`ink`, with
  `Accessible.name` "current") for checked rows. The selected row has the launcher's `accentSoft`
  fill (the current row is "here"). Disabled rows use `inkDisabled`.
- A `confirm` row turns into an inline question in place: `alert` glyph in `warning`, the sentence,
  and hints "Enter confirms · Esc cancels". Nothing else is amber.
- Footer hints (as `Launcher.qml:281-302`): `↑ ↓` move · `Enter` run · `→` open · `←` back ·
  `Esc` close.

| Key | Does |
|---|---|
| type | filter (§4.7) |
| ↑ / ↓, Tab / Shift + Tab | move; wraps; skips disabled rows |
| Enter | run the action, open the branch, follow the link, or choose the provider row |
| → | open the selected branch (when the field is empty or the caret is at its end) |
| ← or Backspace on an empty field | up one level |
| Delete | on `reminders` and `windows` rows: cancel / close |
| Esc | clear the filter → up one level → close. At the level the menu was opened at (a route from a key), Esc closes |
| `Super + Alt + Space` again | closes the menu |
| `Super + Space` while the menu is open | switches to the launcher home |

Reduced motion: a branch change swaps the rows with a `durationFast` fade only.

#### 4.9 IPC and `arctic-menu`

`shell.qml` gets a new target (no function is named `show` or `list`, as `shell.qml:127` explains):

```qml
IpcHandler {
    target: 'menu'
    function toggle(route: string): void { shell.toggleMenu(null, route); }   // '' = root
    function open(route: string): void { shell.openMenu(null, route); }
    function close(): void { if (launcher.view === 'menu') launcher.close(); }
    function refresh(): void { CommandMenuService.refresh(); }
    function select(request: string): string { return CommandMenuService.select(request); }  // 'ok' | 'busy' | 'bad-request'
}
```

- **Routes**: an id, case-insensitive, `_` read as `-`. `''` = root. A route to a branch opens it; a
  route to an action runs it (Omarchy's rule); a route to a link opens its target; an unknown
  route opens the root with a one-row notice "No menu called “x”".
- `shell.toggleMenu(screen, route)`: if the launcher is open in `menu` view at that route, close;
  otherwise `launcher.openView('menu', route)` and present it.

`dotfiles/.local/bin/arctic-menu` (Python 3, standard library):

```
arctic-menu [ROUTE]                         toggle the menu (at ROUTE)
arctic-menu open ROUTE                      always open
arctic-menu select [--prompt T] [--placeholder T] [--json]
                                            one option per stdin line: "label" or "label<TAB>desc";
                                            prints the chosen label (JSON: {"ok":true,"value":"…","index":2})
arctic-menu input [--prompt T] [--placeholder T] [--json]
                                            prints one typed line
arctic-menu list [--json] [--fallback]      the merged tree (JSON lines for scripts); --fallback
                                            keeps only rows that work without the shell
```

- **Select/input handshake** (the same pattern as the shortcuts section's capture overlay, its
  §5.3; Omarchy polls a done file instead — correction noted):
  1. `mkdir -m 0700 -p $XDG_RUNTIME_DIR/arctic/menu`; write `req-<pid>.json`:
     `{"mode":"select","prompt":"Remind me","placeholder":"…","options":[{"label":"…","desc":"…"}],"reply":"…/reply-<pid>.fifo"}`
     (options ≤ 5000, labels ≤ 200 characters, no control characters).
  2. `mkfifo reply-<pid>.fifo`; open the read end non-blocking plus a dummy writer.
  3. `arctic-shell-ipc menu select <request path>`; `busy` → exit 3.
  4. Wait up to 300 s for one line: `{"ok":true,"value":"…","index":2}` or
     `{"ok":false,"code":"cancelled"}` (Esc, closing the launcher, or another popover opening).
  5. Exit 0 and print the value, or exit 1 on cancel. Files are removed on exit.
- In the shell, a select request opens the launcher in `menu` view with a temporary root built from
  the options; input mode shows one row "Use “<typed text>”" that follows the field.
- **Fallback without the shell** (`arctic-shell-ipc` fails, or `ARCTIC_SHELL=waybar`):
  - `arctic-menu [ROUTE]`: `arctic-menu list --fallback` rows for that branch piped to
    `fuzzel --dmenu --prompt "<title>  "`; branches descend by running again; `run` rows run;
    `shell` rows are hidden.
  - `select`: `fuzzel --dmenu`; `input`: `fuzzel --dmenu --lines 0` (🔍 fuzzel 1.13 prints the
    typed text when nothing matches; prove with `echo | fuzzel --dmenu --lines 0` on F44).
- Arctic's own user of `input` is `remind.add` (§13). Scripts can use `select` and `input` as a
  themed dmenu; the wiki documents both.
- `arctic-shell-ipc` usage text (`:6-8`) gains `menu toggle|open|close|refresh|select`.

#### 4.10 Changes to existing shell files (command menu)

| File:lines | Change |
|---|---|
| `shell/Launcher.qml:10-14` | Header comment: the `menu` view, the new result kinds. |
| `:18` | `view`: `home`, `apps`, `get`, `menu`. Add `property string menuRoute: ''`. |
| `:24-26` | `focusItem` / `cardWidth` / `cardHeight` for `menu` (520, content height up to 8 compact rows). |
| `:28-34` | `openView(name, arg, query)`: `menu` → `commandMenu.open(arg || '')`. (The Get apps section also changes this signature; one combined edit.) |
| `:47-56` | Special `{kind:'menu', name:'Commands and settings', …}` after Get apps / Remove apps. |
| `:83-106` | `case 'menu': openView('menu', '')`. |
| `:131-137` | Next to the Get apps component: `CommandMenu { id: commandMenu; visible: launcher.view === 'menu'; … onBackRequested: launcher.close() }`. |
| `:213-266` | Delegate moved to `LauncherRow.qml`; the Get apps section's trash button moves with it. |
| `shell/shell.qml:7-15` | Header and IPC list. |
| `:28-37` | `toggleLauncher` treats `menu` like `get` (a different view: switch, don't close); new `toggleMenu`, `openMenu`. |
| after `:143` | `IpcHandler { target: 'menu' … }`. |
| `shell/qmldir` | `singleton CommandMenuService 1.0 CommandMenuService.qml`, `singleton WindowList 1.0 WindowList.qml`, `CommandMenu 1.0 CommandMenu.qml`, `LauncherRow 1.0 LauncherRow.qml`. |

---

### 5. Launcher search modes (`launcher-search-modes`, P2)

One `Super + Space` box finds an app, a command, a Settings row, an open window, a file, a unit
conversion or a web search. Everything is computed locally except the web search, which sends
nothing until Enter.

#### 5.1 The query line

`LauncherSearch.mode()` (`shell/LauncherSearch.js:63-69`) learns three prefixes. The shortcuts
section adds `:` (emoji) in the same function; the table is the whole set.

| First character | Mode | Result |
|---|---|---|
| `=` | `calc` | `Calc.js`; when it can't parse, `qalc` (units, currency, bases, functions) (§5.7) |
| `>` | `command` | unchanged |
| `:` | `emoji` | shortcuts section §11 |
| `/` or `~` | `files` | file search under the home folder, or under the folder typed (§5.6) |
| `?` | `web` | "Search DuckDuckGo for …" (§5.8); `?` alone lists these prefixes as help rows |
| anything else | `search` | mixed results (§5.2) |

`mode()` returns `{mode, text, dir}` (`dir` only for `files`: `~/Documents/rep` → `dir: '~/Documents'`,
`text: 'rep'`). The placeholder (`Launcher.qml:182-188`) becomes "Search apps, settings, windows and
files"; the footer keeps its `=` and `>` hints and gains `?` "more".

#### 5.2 Mixed results

`LauncherSearch.compose(ctx)` (pure, tested) builds the list for `search` mode from candidate
lists the QML hands it:

```js
compose({ text, view, live,
          specials, apps, actions, commands, toggles, settings, windows, files,
          calc,            // a calc/qalc row or null (§5.7)
          remind,          // a parsed reminder row or null (§13)
          getSearch,       // the Get apps section's "Find “x” in Get apps" row, or null
          web,             // the web row (§5.8), or null
          usage })         // frecency table (§5.10)
→ [{kind:'header', name:'Settings'}, {kind:'setting', …}, …]
```

Order is fixed, so people learn where things are:

| # | Section | Rows | Cap |
|---|---|---|---|
| 1 | (no header) the calculation or reminder row, when the text is arithmetic, a conversion or a reminder | `calc`, `remind` | 1 |
| 2 | Apps | specials (`Launcher.qml:47-56`), apps, app actions (§5.9) | 6 (all in `apps` view) |
| 3 | Commands | menu rows (§5.5) and toggles | 4 |
| 4 | Settings | Settings pages and rows (§5.3) | 4 |
| 5 | Windows | open windows (§5.4) | 4 |
| 6 | Files | only after the text has stayed unchanged for 300 ms and is ≥ 3 characters, and `fileSearch` is on (§5.6) | 5 |
| 7 | (no header) fallback rows | "Find “x” in Get apps" when no app matched (Get apps section §5), then "Search the web for “x”" when the text is ≥ 2 characters | 2 |

- Section headers are 24 px, 11 px / 600, letter-spaced upper-case `inkSubtle`, not selectable,
  and appear only when at least two sections have rows. ↑/↓ skip them.
- A section's rows are ranked with `LauncherSearch.rank`; the cap applies after ranking.
- The empty home is unchanged: the specials, now including "Commands and settings" (§4.1) and the
  Get apps section's "Remove apps".
- The `apps` view (every app) is unchanged apart from frecency.

Result kinds and what Enter / Shift + Enter do (`Launcher.qml:83-106`, extended):

| `kind` | Enter | Shift + Enter |
|---|---|---|
| `app` | `entry.execute()` or in a terminal (unchanged) | — |
| `action` | `action.execute()` (§5.9) | — |
| `command` | `CommandMenuService.activate(id)` (the menu row's action) | open its branch in the menu, when it is a branch |
| `toggle` | `ToggleRegistry.set(key, 'toggle', 'launcher')` | — |
| `setting` | `arctic-settings PAGE KEY` (§5.3) | — |
| `window` | `WindowList.focus(id)` | — |
| `file` | `xdg-open PATH` | open the folder that holds it |
| `calc` | copy the result (`wl-copy --`) | copy the expression and result ("10 km = 6.214 mi") |
| `remind` | `arctic-remind add …` and an OSD notice "Reminder set for 15:40" | — |
| `web` | `xdg-open URL` | — |
| `help` | put the prefix into the field | — |
| `get-search`, `remove`, `menu`, specials | as their owners define | |

#### 5.3 Settings rows

- The shell can't import `settings/SearchIndex.js` by a relative path: `arctic-shell` may run a copy
  in `~/.config/quickshell/arctic` (`dotfiles/.local/bin/arctic-shell:11-15`), where `../settings`
  doesn't exist, and a failed QML import would break the whole launcher.
- So `shell/dev/export-settings-index.cjs` (new, Node) loads `settings/SearchIndex.js` the way the
  Node tests do (`shell/tests/test-launcher.cjs:4-9`) and writes `shell/assets/settings-index.js`
  (`.pragma library`, `var PAGES = […]; var ENTRIES = […];`, "Generated — do not edit").
  `shell/tests/test-settings-index.cjs` fails when the checked-in file is stale, as the keys sheet
  does for `keys.txt`. Every section that adds Settings rows re-runs the exporter.
- Candidates: pages (`{name: title, keywords: words, desc: 'Settings'}`) and entries
  (`{name: title, keywords: words + ' ' + pageTitle, desc: 'Settings › ' + pageTitle}`), glyph
  `sliders`.
- Enter runs `arctic-settings PAGE KEY`. `dotfiles/.local/bin/arctic-settings` learns a second
  argument (`:4-8` usage, `:29-34` parsing): KEY must match `^[a-z]+(\.[a-z]+)*$`; a running
  Settings gets `quickshell ipc -p "$dir" call settings reveal "$page" "$key"` (the handler exists,
  `settings/shell.qml:59-61`); a new one starts with `ARCTIC_SETTINGS_REVEAL="$key"`, which
  `settings/shell.qml:43-46` already reads.

#### 5.4 Windows

- `shell/WindowList.qml` (singleton) runs `mmsg get all-clients` when the launcher opens (and when
  the `windows` menu branch opens), parses `{"clients":[…]}` (the shape `arctic-settings:53-58`
  reads) and keeps `{id, title, appId, workspace (first tag), monitor, minimized}`.
  Mango 0.17.3 emits `id`, `title`, `appid`, `monitor`, `tags`, `is_minimized`, `is_scratchpad`
  and more ✅ (`src/ipc/ipc.c:556-590`, `build_client_json`).
- Without `mmsg` (another compositor, or it fails) it falls back to `ToplevelManager.toplevels`
  (`appId`, `title`, `activate()`, `close()`, all in the `dacfa9d` snapshot ✅).
- Rows: title (15/600), desc "Firefox · workspace 2" (+ " · DP-1" with several monitors, "Hidden"
  when minimised), the app's icon through `DesktopEntries.heuristicLookup(appId)` ✅ (in the
  snapshot). The launcher's own layer is not a client, so it never lists itself.
- Enter: `mmsg dispatch focusid client,<id>` as argv `['mmsg','dispatch','focusid','client,' + id]`
  (the form `arctic-settings:59` uses ✅). Mango's `focus_by_id` → `client_active()` switches to the
  window's tag and focuses it, and brings a minimised window back ✅ (`src/manage/client.c:2791-2814`).
- Delete on a window row (menu `windows` branch and launcher): `mmsg dispatch killclient client,<id>`
  — a normal close request, so apps can ask to save (verification: no `force`).
- Matching: title and app id; an exact app-id word ("firefox") ranks its windows first.

#### 5.5 Commands

- Candidates are every visible action and link row of the command menu (`CommandMenu.flatten`),
  with the breadcrumb as desc ("Capture › Screenshot of an area"), plus every available
  `ToggleRegistry` entry as a `toggle` row ("Night light", desc "On · Super + Ctrl + N").
- Provider rows are not searched from the launcher (they would need processes per keystroke),
  except `toggles`, which are in memory.
- This is also how the shortcuts section's capture rows become searchable ("screenshot",
  "record", "colour", "text", "qr"), which its §10 asks for.

#### 5.6 Files

- Tool: `fd` from `fd-find` 10.4.2 ✅ (mdapi 200), a Recommends of `arctic-shell` (§19).
- One `Process` at a time (`shell/FileSearch.qml`, new), restarted on every settled query and
  killed after 2 s:
  `['fd', '--absolute-path', '--color', 'never', '--max-results', '20', '--max-depth', '8',
    '--ignore-case', '--fixed-strings', '--exclude', '.cache', '--exclude', 'node_modules',
    '--', text, dir || Session.home]`.
  fd skips hidden files and honours `.gitignore` by default, so dot folders stay out.
- In mixed mode files come last and only after a 300 ms pause (§5.2). With the `/` or `~` prefix
  the list shows only files, up to 20.
- Rows: `folder` or `file` glyph (or the MIME icon through `Quickshell.iconPath` 🔍 whether the
  snapshot resolves `text-x-generic`-style names), name, desc = the folder with `~`.
- Without `fd`: one row "File search needs fd-find" → the Get apps section's
  `apps search dnf fd-find`.
- Settings > Default apps > Search: "Find files from the launcher" switch (`fileSearch`, §8.4).

#### 5.7 Units, currency and bases

- `Calc.js` stays the first try (instant, no process). The shell falls back to `qalc -t EXPR` from
  `qalculate` 5.9.0 ✅ (mdapi 200; `/usr/bin/qalc` ✅ in its file list), a Recommends of
  `arctic-shell`:
  - in `=` mode when `Calc.evaluate` fails;
  - in `search` mode when the text looks like a conversion: a number, a unit word or symbol, then
    ` to `, ` in ` or ` as ` and a unit (`Units.looksLikeConversion()` in `shell/Units.js`, new,
    tested: "10 km to mi", "100 usd in eur", "0xff to dec", "72 f to c" yes; "to do list",
    "set up in 5" no).
  - plain arithmetic without `=` ("2+2", "12*4") goes to `Calc.js` directly (`Units.looksLikeMath`).
- One `qalc` process at a time, 150 ms debounce, killed after 1.5 s. The row reads "6.2137 mi",
  desc "= 10 km to mi · Enter copies". `qalc` output lines starting with "error" become the
  `none` row "Can't work that out".
- Currency: `qalc` updates exchange rates by itself when a currency is used and its rates are old
  🔍 (prove on F44: `qalc -t "1 usd to eur"` with an empty `~/.local/share/qalculate`, and check the
  default interval). Nothing is fetched for other conversions. The wiki says where rates come from.

#### 5.8 Web search

- Always the last row when the text is ≥ 2 characters (mixed mode), or the only row after `?`.
- Label "Search DuckDuckGo for “rain radar”", glyph `globe`. Enter opens
  `xdg-open <url>` with the text percent-encoded (`encodeURIComponent`).
- Engines (`webSearch` in `shell.json`):

  | Id | Label | URL template |
  |---|---|---|
  | `duckduckgo` (default) | DuckDuckGo | `https://duckduckgo.com/?q=%s` |
  | `startpage` | Startpage | `https://www.startpage.com/do/search?q=%s` |
  | `brave` | Brave Search | `https://search.brave.com/search?q=%s` |
  | `google` | Google | `https://www.google.com/search?q=%s` |
  | `bing` | Bing | `https://www.bing.com/search?q=%s` |
  | `kagi` | Kagi | `https://kagi.com/search?q=%s` |
  | `ecosia` | Ecosia | `https://www.ecosia.org/search?q=%s` |
  | `custom` | the host of `webSearchUrl` | `webSearchUrl` (must start with `https://` and contain `%s`) |

- No suggestions are fetched while typing.
- Settings > Default apps gets a "Search" group (§8.4).

#### 5.9 App actions

- `DesktopEntry.actions` and `DesktopAction.execute()` are in the `dacfa9d` snapshot ✅
  (`src/core/desktopentry.hpp:87`, `:176-209`).
- Candidates `{kind:'action', name: action.name, desc: entry.name, keywords: entry.name, icon of the
  app}`: "New Private Window — Firefox". They join the Apps section only when the text is ≥ 3
  characters, at most two per app, and never outrank their own app for the same text.

#### 5.10 Ranking by use (frecency)

- `~/.local/state/arctic/launcher.json`:
  `{"version":1,"used":{"app:firefox.desktop":{"n":14,"t":1759070000},"setting:network.wifi":{"n":2,"t":…}}}`,
  keys `app:<desktop id>`, `action:<desktop id>/<action id>`, `setting:<key>`, `command:<menu id>`;
  at most 200 keys (the oldest dropped). Written once per activation through a `FileView`
  with `atomicWrites: true` ✅ (snapshot `src/io/fileview.hpp:207`, `setText` `:324`).
- `LauncherSearch.rank(candidates, query, usage)` adds
  `boost = min(150, 40 · ln(1 + n · 0.5^(age_days / 14)))` to matches only. Name matches score
  1000 and more (`LauncherSearch.js:41-42`), so use reorders similar matches and never lifts a
  weak match over an exact name. The `apps` view with no text stays alphabetical.
- Nothing is recorded on the live USB (the home folder is thrown away anyway, and it keeps the
  screenshots stable).

#### 5.11 Keyboard in the launcher (additions)

| Key | Does |
|---|---|
| `/`, `~`, `?` as the first character | files, files, web / help (§5.1) |
| Shift + Enter on a file | opens its folder |
| Shift + Enter on a calculation | copies "expression = result" |
| Delete on a window row | closes the window (the field's Delete is not accepted there, as the Get apps section does for app rows) |
| ↑ / ↓ | skip section headers |

Everything else is unchanged (`Launcher.qml:175-181`). No key holds Alt + Shift, Ctrl + Shift or
Alt + Space.

#### 5.12 Limits

- Everything but files and `qalc` is in-memory and ranked per keystroke (about 200 apps, 100
  Settings rows, 150 menu rows, 20 windows).
- Files and `qalc` run at most one process each, debounced and killed on a timer, so a slow disk
  can't stall typing.

---

### 6. More OSD kinds (`osd-kinds`, P2)

#### 6.1 One model, two kinds

`shell/Osd.qml` keeps its pill, place and fade, and gets a small model that every other section
calls into instead of adding its own kind:

| Kind | Shows | Duration |
|---|---|---|
| `level` | 20 px icon, 6 px bar, value in tabular figures, optional label (monitor name) — today's volume/brightness pill | 1.2 s after the last change (unchanged) |
| `notice` | 20 px icon, text 13/600 `ink`, optional detail 12 `inkMuted` after " · " | 1.6 s, plus 60 ms per character beyond 20, at most 3 s |

- New pure `shell/OsdModel.js` (tested): `duration(kind, text, detail)`, `width(kind, textWidth)`
  (level 280; notice between 200 and 420, text elided), `icon(name)` (unknown → `info`).
- `Osd.qml` functions:
  - `showLevel(icon, percent, label)` — `showVolume()` and `showBrightness()` (`:20-31`) become
    thin wrappers;
  - `showNotice(icon, text, detail)`.
- The bar section's `brightnessLevel`, `showPower`, `showLayout` and the shortcuts section's
  `showKeyboard`, `showMic`, `showTouchpad` are written as calls to these two (their files, their
  wording; no extra kinds).
- The level bar keeps its current colours (`Osd.qml:108-124`). A notice has no bar and no amber.
- `Accessible.name` is the text plus detail ("Caps Lock on"; "Volume 40 %" as today).
- Reduced motion: fades only, which is already true (`Osd.qml:38-48` animates opacity alone).

#### 6.2 IPC and the helper

`shell.qml:113-117`:

```qml
IpcHandler {
    target: 'osd'
    function volume(): void { osd.showVolume(); }                       // unchanged
    function brightness(): void { osd.showBrightness(); }               // unchanged
    function level(icon: string, percent: int, label: string): void { osd.showLevel(icon, percent, label); }
    function notice(icon: string, text: string, detail: string): void { osd.showNotice(icon, text, detail); }
}
```

- Three typed arguments: `IpcHandler` resolves a vector of argument types (string, int, bool,
  real, colour) ✅ (`src/io/ipchandler.hpp:40-49`, snapshot). Settings already declares a
  two-string function (`settings/shell.qml:59`, called by `settings/dev/headless.sh:135`, whose
  result isn't checked). 🔍 A headless step `ipc osd notice caps-lock "Caps Lock on" ""` proves
  three arguments (§20.4).
- `dotfiles/.local/bin/arctic-osd` gains:
  - `notice ICON TEXT [DETAIL]` → `arctic-shell-ipc osd notice …`, else the mako notification it
    already uses (`show()`, `:16-20`, with `x-canonical-private-synchronous:arctic-osd`);
  - `lock-keys` (§6.4).

#### 6.3 What shows a notice

| Event | Notice | Who calls |
|---|---|---|
| A toggle changed by a key, the command menu or IPC (not by its Quick Settings tile, which is already on screen) | "Night light on", detail "Until 07:00"; "Do not disturb on"; "Airplane mode on"; "Keep awake on", detail "Until 15:30"; "Game mode off" | `ToggleRegistry.set(key, mode, source)` in the bar section's registry, when `source !== 'tile'` and the toggle's `osd` is true (a shared edit, §23) |
| Power mode cycled | "Balanced" with `gauge` (`leaf`/`bolt` for the others) | the same registry path (`power-mode` is a registry toggle) |
| Keyboard layout changed | "Hebrew" with `keyboard` | bar section's `showLayout` → `showNotice` |
| Caps Lock, Num Lock | "Caps Lock on" / "Caps Lock off" (glyph `caps-lock`), "Num Lock on" / "off" (glyph `hash`) | `arctic-osd lock-keys` (§6.4) |
| Bar hidden | "Top bar hidden", detail "Super + Shift + Space shows it" | §10 |
| Reminder set | "Reminder set for 15:40" | §13 |
| Text copied from the launcher | "Copied 6.2137 mi" | §5.7 |
| Theme switched by `Super + Shift + T` | "Polar night" with `moon` / "Winter" with `sun` (the new theme's label) | `arctic-theme toggle --osd` (new flag, §7.1.4); `binds.conf:79` becomes `bind=SUPER+SHIFT,t,spawn,arctic-theme toggle --osd`. Settings and the schedule don't pass it: Settings shows its own toast, and a scheduled switch stays quiet |

#### 6.4 Caps Lock and Num Lock

- Binds (rows 57-58): `bindrp=NONE,Caps_Lock,…` and `bindrp=NONE,Num_Lock,…`, both running
  `arctic-osd lock-keys` on release, with the release passed through to the app.
- `arctic-osd lock-keys`:
  1. reads every `/sys/class/leds/*::capslock/brightness` and `*::numlock/brightness` (any
     non-zero = on);
  2. compares with `$XDG_RUNTIME_DIR/arctic/lock-keys` (`caps=0|1 num=0|1`);
  3. only for a state that changed: saves it and shows the notice. No LED devices (some VMs) or no
     change (a remapped Caps key, a layout-switch Caps key) → nothing.
- 🔍 The LED is already updated when the release arrives (wlroots updates LEDs as locked modifiers
  change). Prove with a USB keyboard and a laptop keyboard on F44; so that the first press after
  login isn't lost to a missing state file, `arctic-session shell` runs
  `arctic-osd lock-keys --seed` once.
- Mango's own `numlockon` option (Settings > Keyboard, `input.numlock`) turns Num Lock on at start
  without a key press, so no notice is shown then.
- The lock screen already needs a Caps Lock hint; the bar section adds it there (its §5.9).

---

### 7. Theming

#### 7.1 Switch between light and dark automatically (`auto-dark-schedule`, P2)

**7.1.1 Behaviour**

- Settings > Appearance > Theme gets "Switch automatically": **Off** (default), **Sunset to
  sunrise**, **Custom hours** (light from 07:00, dark from 19:30).
- At each boundary the schedule does exactly what `arctic-theme light` / `arctic-theme dark` do
  (correction applied: not `mode`), extended with pairs (§7.2.3):
  - auto colours on, or the wallpaper theme active → the wallpaper theme's light/dark mode;
  - the active theme has a `pair` (Winter ⇄ Polar night, Catppuccin Latte ⇄ Mocha, …) → its pair;
  - otherwise (a dark-only theme such as Nord) → Winter or Polar night. Settings says so under the
    row: "Nord has no light version, so Winter is used by day."
- A manual switch (key, Settings, menu) holds until the next boundary, then the schedule takes over
  again (Plasma's behaviour).
- Sunset and sunrise come from `arctic-sun` (§7.1.3), computed locally from the saved location.
  No location (the time zone is `UTC`, or has no coordinates) → "Sunset to sunrise" is disabled
  with "Set a place first" and a link to the Place row (§12.4).

**7.1.2 How it runs**

- `arctic-theme schedule` (new verbs, §7.1.4) keeps the setting in
  `~/.config/arctic/settings.json`:
  `"schedule": {"mode": "off"|"sun"|"hours", "light": "07:00", "dark": "19:30"}` (other keys kept,
  as `save_settings` already does, `arctic-theme:87-91`).
- State: `~/.local/state/arctic/theme-schedule.json` `{"period":"dark","since":1759080000}`.
- `arctic-theme schedule tick`:
  1. works out the current period (light or dark) and the next boundary;
  2. if the period differs from the saved one, applies it (the `light|dark` code path, under the
     theme lock) and saves it; if it is the same, does nothing — so a manual switch made after the
     last boundary is left alone;
  3. arms the next tick with a transient user timer:
     `systemctl --user stop arctic-theme-schedule.timer` (ignoring "not loaded"), then
     `systemd-run --user --unit=arctic-theme-schedule --collect --quiet
      --on-calendar='2026-09-28 18:24:00' --timer-property=AccuracySec=5s
      -- arctic-theme schedule tick`.
- Ticks also run: at login (`arctic-theme apply` calls `schedule tick` when the mode isn't `off`,
  `autostart.conf:10` already runs `apply`), when the setting changes, and when the screen unlocks
  (the shell's `LockScreen` runs `arctic-theme schedule tick` in the background after unlock, which
  covers a suspend across a boundary).
- 🔍 A realtime (`OnCalendar`) transient timer whose time passed during suspend fires on resume.
  Prove on F44: arm a timer 2 minutes ahead, suspend for 5, resume, check `journalctl --user -u
  arctic-theme-schedule`. The unlock tick makes the answer non-critical.
- Why not darkman (2.2.0 ✅ in F44): it installs its own `org.freedesktop.impl.portal` Settings
  backend (`/usr/share/xdg-desktop-portal/portals/darkman.portal` ✅ in its file list), which would
  compete with xdg-desktop-portal-gtk for `color-scheme`, and it needs geoclue or a manual
  location. Arctic already owns the switch (`arctic-theme`); a timer is enough.

**7.1.3 `arctic-sun` and the saved location (shared with weather and night light)**

`dotfiles/.local/bin/arctic-sun` (new, Python 3 standard library):

```
arctic-sun [--json] [--date YYYY-MM-DD]      sunrise and sunset for the saved location
arctic-sun location [--json]                 the saved location
arctic-sun location set timezone             follow the time zone (the default)
arctic-sun location set place NAME LAT LON   a place the person chose (Settings passes the geocoder's answer)
```

- `--json` output:
  `{"ok":true,"date":"2026-09-28","sunrise":"06:32","sunset":"18:24","polar":null,
    "location":{"mode":"timezone","name":"Jerusalem","lat":31.78,"lon":35.22,"tz":"Asia/Jerusalem"}}`
  (`polar`: `"day"` or `"night"` when the sun doesn't rise or set that day); errors
  `{"ok":false,"code":"no_location","error":"This time zone has no place to take sunrise and sunset from."}`.
- `~/.config/arctic/location.json` (written atomically):
  `{"mode":"timezone"}` or `{"mode":"place","name":"Haifa, Israel","lat":32.79,"lon":34.99}`.
- Time zone: `timedatectl show -p Timezone --value`, else the `/etc/localtime` link. Coordinates:
  `/usr/share/zoneinfo/zone1970.tab` from `tzdata` ✅ (`±DDMM±DDDMM` or `±DDMMSS±DDDMMSS`). A link
  name that isn't in `zone1970.tab` is resolved through the `L` lines of
  `/usr/share/zoneinfo/tzdata.zi` 🔍 (present in F44 tzdata; prove with `rpm -ql tzdata`).
- Sun times: the NOAA algorithm (solar declination and equation of time, −0.833° for refraction),
  local times through `zoneinfo`. Tested within ±2 minutes against published tables (§20).
- Coordinates are the time zone's main city (a big zone such as `America/New_York` gives New
  York's times in Miami); Settings says "From your time zone (Jerusalem)" so the person can pick a
  place instead.
- Night light (system section) should read the same file through `arctic-sun location --json`
  instead of keeping its own latitude and longitude, so there is one place setting (§23).

**7.1.4 `arctic-theme` changes**

| Command | Change |
|---|---|
| `arctic-theme schedule [--json]` | print `off`, `sun (06:32–18:24)` or `hours 07:00 19:30`; JSON `{"ok":true,"mode":"sun","light":"07:00","dark":"19:30","sunrise":"06:32","sunset":"18:24","period":"light","next":"2026-09-28T18:24:00+03:00","place":"Jerusalem"}` |
| `arctic-theme schedule off\|sun` / `schedule hours LIGHT DARK` | save, then `tick`; `off` also stops the timer. Times `HH:MM`, 24 h, different from each other |
| `arctic-theme schedule tick` | §7.1.2 |
| `arctic-theme light\|dark` (`:679-684`) and `toggle` (`:591-597`) | use the active theme's `pair` when it has one (§7.2.3); `--osd` shows the OSD notice (§6.3) |
| `arctic-theme apply` (`:600-610`) | runs `schedule tick` at the end when a schedule is set |
| `arctic-theme current --json` (`:613-621`) | adds `"schedule"` (the object above without `next`) and `"contrast"` (§8.2) |

`docs/BUILD-SPEC.md` §10 (9.6) gets these rows; the existing verbs keep their meaning ("extend,
don't change", BUILD-SPEC:656-657).

#### 7.2 Theme gallery (`theme-gallery`, P2)

**7.2.1 What ships**

An optional set of named palettes that still behave like Arctic: the same semantic roles, the
same contrast guarantees, and the accent keeps its "here" role (D9).

| Name | Label | Mode | Pair | Upstream (colour values; licence to confirm 🔍 before copying) |
|---|---|---|---|---|
| `nord` | Nord | dark | — | nordtheme/nord (MIT) |
| `catppuccin-mocha` | Catppuccin Mocha | dark | `catppuccin-latte` | catppuccin/catppuccin (MIT) |
| `catppuccin-latte` | Catppuccin Latte | light | `catppuccin-mocha` | same |
| `gruvbox-dark` | Gruvbox | dark | `gruvbox-light` | morhetz/gruvbox (MIT) |
| `gruvbox-light` | Gruvbox Light | light | `gruvbox-dark` | same |
| `tokyo-night` | Tokyo Night | dark | `tokyo-night-day` | folke/tokyonight.nvim (Apache-2.0 🔍) |
| `tokyo-night-day` | Tokyo Night Day | light | `tokyo-night` | same |
| `rose-pine` | Rosé Pine | dark | `rose-pine-dawn` | rose-pine/rose-pine-theme (MIT) |
| `rose-pine-dawn` | Rosé Pine Dawn | light | `rose-pine` | same |
| `everforest-dark` | Everforest | dark | `everforest-light` | sainnhe/everforest (MIT) |
| `everforest-light` | Everforest Light | light | `everforest-dark` | same |

- Each lives in `design/themes/<name>/colors.toml` with a `SOURCE` file (upstream URL, commit,
  licence). The package `arctic-themes-extra` installs them rendered (§19).
- Winter and Polar night stay the defaults and the identity; the gallery is opt-in in Settings.

**7.2.2 Palette source format: Omarchy's `colors.toml`**

Arctic reads the same `colors.toml` keys Omarchy 4 themes use (`omarchy/docs/theming.md`), so an
Omarchy theme repository can be installed as it is (§7.2.5):

```toml
mode = "dark"                          # dark | light
accent = "#81a1c1"                     # Omarchy's accent: becomes Arctic's `info`
selection = "#434c5e"
muted = "#4c566a"
background = "#2e3440"
dark_background = "#222730"
darker_background = "#191c23"
lighter_background = "#3b4252"
foreground = "#d8dee9"
dark_foreground = "#667080"
light_foreground = "#adb5c4"
bright_foreground = "#d8dee9"
red = "#bf616a"
yellow = "#ebcb8b"
orange = "#d5967a"
green = "#a3be8c"
cyan = "#88c0d0"
blue = "#81a1c1"
magenta = "#b48ead"
brown = "#6a4b3d"
bright_red = "#bf616a"
bright_yellow = "#ebcb8b"
bright_green = "#a3be8c"
bright_cyan = "#8fbcbb"
bright_blue = "#81a1c1"
bright_magenta = "#b48ead"

# Arctic-only keys (optional)
label = "Nord"
pair = ""                              # the other-mode theme's name
here = "yellow"                        # which colour key carries Arctic's "here" accent
```

(`nord` values from the Omarchy checkout, `themes/nord/colors.toml`.)

New module `design/themegen/named.py` — `from_colors(data, name, label=None)` → a palette with
every role in `ROLES` (`palette.py:24-32`):

| Arctic roles | From |
|---|---|
| `ground`, `surface`, `surface-raised`, `surface-sunken` | dark: `background` → `ground`, `lighter_background` → `surface-raised`, `dark_background` → `surface-sunken`, and `surface` is the OKLab midpoint of `ground` and `surface-raised`. Light: the same keys, but `surface` is the lightest step, as in Winter (ground `#eef2f5`, surface `#ffffff`) |
| `frost` | `surface-raised` with the base theme's frost alpha (Polar night's `d1`, or Winter's own) |
| `scrim`, `shadow` | the base theme's (by mode) |
| `line`, `line-strong` | `foreground` mixed over `ground` at the lightness distances Polar night / Winter use (`derive.py` keeps OKLab lightness offsets the same way) |
| `ink`, `ink-muted`, `ink-subtle`, `ink-disabled`, `ink-inverse` | `ink` ← the stronger of `bright_foreground` and `foreground`; `ink-muted` ← `light_foreground`; `ink-subtle` ← `dark_foreground`; `ink-disabled` ← `dark_foreground` mixed 40 % toward `ground`; `ink-inverse` ← `ground` |
| `accent` family (`accent`, `-hover`, `-pressed`, `on-accent`, `accent-text`, `accent-soft`, `accent-edge`, `focus`, `selection`) | the colour named by `here` (default: `yellow`, or `orange` when yellow's OKLCH hue is outside 60-100°), built with the same family builder the wallpaper path uses; `selection` from `selection` |
| `success`, `warning`, `error`, `info` (+ `-soft`, `on-error`, `error-hover`) | `green`; whichever of `yellow`/`orange` is **not** the `here` colour (so a warning never looks like "here"); `red`; Omarchy's `accent` (informative, not "here") |
| `warm`, `warm-soft` | the same colour as `warning` |
| `aurora-1..3` | `green`, `cyan`, `blue` |
| `term-*`, `ansi-0..15` | `background`/`foreground`, the named colours in ANSI order (`ansi-0` = `dark_background`, `ansi-8` = `muted`, brights from `bright_*`, missing brights = the normal colour) |

Then `derive.enforce()` and `derive.check()` (the existing guarantees) run as for wallpaper
palettes; a palette that can't meet them is refused with the failing pair named.

- The accent stays warm in every gallery theme, so "here" reads the same across themes
  (`design/guidelines/10-platforms.md` gets a paragraph).
- `mode`, `pair`, `label`, `here` validated; unknown keys ignored; values must be `#rrggbb`.

**7.2.3 Pairs**

- `palette.json` may carry `"pair": "<name>"` (optional; `palette.validate` accepts it; the two
  built-ins pair with each other in `palette.builtin`).
- `arctic-theme light|dark|toggle` switch to the pair when the active theme's mode differs from
  the wanted one (§7.1.4). Settings shows a pair as one card with a light and a dark half (§7.2.6).
- `arctic-theme list --json` adds `"pair"`, `"gallery": true|false`, `"installed_from": "https://…"|null`,
  and more swatches: `ground`, `surface`, `surface-raised`, `frost`, `line`, `ink`, `ink-muted`,
  `accent`, `on-accent`, `term-background` (existing fields unchanged).

**7.2.4 Where they live**

- Packaged gallery themes: `/usr/share/arctic/themes-extra/<name>/` (not `themes/`, which
  `arctic-desktop-config` owns recursively, spec `:1095`; a separate folder keeps the two
  packages' file lists apart).
- `arctic-theme`: `EXTRA_THEMES = os.path.join(SYSTEM, "themes-extra")`; `theme_dir()`
  (`:114-121`) searches user, then system, then extra (source `"gallery"`); `all_themes()`
  (`:162-174`) includes it; `link_current()` (`:331-347`) links extra themes absolutely, like
  system ones.
- Rendered in the spec's `%build` like Winter and Polar night:
  `arctic-themegen named --colors design/themes/<n>/colors.toml --name <n> | arctic-themegen render --palette - --out _build/themes-extra/<n>`,
  and `%check` runs `arctic-themegen check` on each (and the high-contrast check, §8.2).

**7.2.5 Install a theme from a URL (allowlist)**

```
arctic-theme install URL [--json]     download a theme repository and keep only its colours and pictures
arctic-theme update NAME|--all [--json]
arctic-theme remove NAME [--json]     your themes only; if it is active, switch to its mode's built-in first
```

- **URL**: `https://` only. GitHub (`https://github.com/<o>/<r>`), Codeberg and GitLab URLs are
  fetched as the host's source tarball over HTTPS with `urllib`
  (`https://codeload.github.com/<o>/<r>/tar.gz/HEAD`; Codeberg
  `https://codeberg.org/<o>/<r>/archive/HEAD.tar.gz` 🔍; GitLab
  `https://gitlab.com/<o>/<r>/-/archive/HEAD/<r>-HEAD.tar.gz` 🔍). Any other host needs `git`
  (`git clone --depth 1 --no-recurse-submodules -c core.symlinks=false`), which Arctic doesn't
  install; without it the error says "This site needs git. Install it from Get apps, or use a
  GitHub, GitLab or Codeberg link." Download limit 50 MB, 60 s.
- **Name**: the repository name without `omarchy-`/`arctic-` in front and `-theme` behind
  (`omarchy-nord-theme` → `nord`), checked against `NAME_RE`; a clash with any installed theme is
  an error ("A theme called nord is already installed. Remove it first.").
- **Kept** (everything else is dropped and listed; symlinks, hard links and devices always dropped;
  tar members with `..` or absolute paths refused — Python's `tarfile` `data` filter, plus our own
  allowlist):

  | File | Check |
  |---|---|
  | `colors.toml` | ≤ 16 KB, `tomllib`, known keys, `#rrggbb` values |
  | `palette.json` (an Arctic palette) | ≤ 64 KB, `palette.validate` |
  | `backgrounds/*.png`, `*.jpg`, `*.jpeg`, `*.webp` | regular files ≤ 25 MB, at most 24, opened and `verify()`d with Pillow |
  | `preview.png` | ≤ 2 MB, Pillow |

  Everything that can run code or name a program — terminal configs, `*.lua`, `vscode.json`,
  scripts, templates — is never copied. This is stricter than Omarchy's denylist
  (`INSTALLED_THEME_DENIED`; correction applied).
- The theme is rendered with Arctic's templates only (never the repository's) into
  `~/.config/arctic/themes/<name>/`, with `source.json`
  `{"url":"…","fetched":"<ETag or commit>","installed_at":"…"}`.
- A theme's `backgrounds/` show first in the wallpaper picker while that theme is active
  (`shell/scripts/wallpapers.py list` adds them as a "From the theme" group). Switching themes never
  changes the person's chosen wallpaper.
- JSON output: `{"ok":true,"name":"nord","label":"Nord","dropped":["kitty.conf","neovim.lua"],"backgrounds":3}`.

**7.2.6 Settings**

- Settings > Appearance > Theme: under the three cards (`AppearancePage.qml:102-143`), a
  "More themes" row with a grid of `ArThemePreview` cards (new
  `settings/components/ArThemePreview.qml`): a 16:10 miniature drawn from the swatches — ground,
  a bar strip in `frost`, a window in `surface-raised` with a 1 px `line`, two text lines in `ink`
  and `ink-muted`, a terminal strip in `term-background`, and one small dot in `accent` (the
  "here" mark). Title = label, second line "Dark · pairs with Catppuccin Latte". A pair is one card
  whose two halves switch to either theme.
- Selecting a card runs `theme-set NAME` (existing, `arctic_settings.py:2157-2185`). The selected
  card uses `ArCard`'s selected style (the current theme is "here").
- "Add a theme from the web…" opens a dialog: URL field, the allowlist in one sentence ("Only
  colours and pictures are kept"), Install. Result toast lists what was dropped.
- A card's context menu (and Delete) offers "Remove" for installed themes.
- Without `arctic-themes-extra`, the grid shows only the person's own themes and a row
  "Get more themes" (the Get apps section's `apps search dnf arctic-themes-extra`).
- New commands in `arctic_settings.py`: `theme-install URL`, `theme-remove NAME`,
  `theme-update NAME` (argv to `arctic-theme … --json`, the one line passed through);
  `cmd_theme` (`:2126-2154`) passes the new list fields through.
- Search entries: `appearance.gallery` "More themes" ("nord catppuccin gruvbox tokyo rose pine
  everforest palette colour scheme install").

**7.2.7 Deferred: the `v2-walls/` pictures**

The gap proposal also asked to package the per-theme backgrounds. `v2-walls/` holds 412 MB in 18
folders (anime, wallhaven downloads, …) with no licence or source records. Shipping them would
redistribute pictures Arctic has no right to. Deferred until each file has a recorded source and
licence; the gallery uses Arctic's own wallpapers and whatever an installed theme brings.

#### 7.3 Code font, Nerd Font symbols and one text size (`fonts-symbols`, P2)

**7.3.1 Code font: `arctic-font`**

`dotfiles/.local/bin/arctic-font` (new, Python 3 standard library):

```
arctic-font list [--json]           monospace families: fc-list :spacing=mono family
arctic-font current [--json]
arctic-font set FAMILY [--json]     the code font everywhere Arctic set it
arctic-font size PT|reset [--json]  the terminal font size (used by the text-size setting, §7.3.3)
```

- `list`: first name of each `fc-list :spacing=mono family` line, de-duplicated, sorted; the
  symbols font and emoji fonts left out. JSON
  `{"ok":true,"current":"JetBrains Mono","size":10.5,"fonts":[{"family":"JetBrains Mono"},…]}`.
- `set` writes, each only when the line still holds the value Arctic wrote last (recorded in
  `~/.config/arctic/fonts.json` `{"mono":"JetBrains Mono","size":10.5}`, seeded from the shipped
  defaults), so a line the person changed is left alone and reported:

  | File | Lines |
  |---|---|
  | `~/.config/kitty/kitty.conf` (`:6-10`) | `font_family FAMILY`, `bold_font auto`, `italic_font auto`, `bold_italic_font auto`; then `pkill -USR1 -u $UID -x kitty` (the reload `arctic-theme` uses) |
  | `~/.config/foot/foot.ini` (`:5`) | `font=FAMILY:size=PT` (foot applies it to new windows) |
  | `~/.config/alacritty/alacritty.toml` (`:7-9`) | `normal = { family = "FAMILY" }`, `size = PT` (live reload is on, `:5`) |
  | GTK | `gsettings set org.gnome.desktop.interface monospace-font-name "FAMILY 10"` |
  | the shell and Settings | `shell.json` `monoFont`; `shell/Theme.qml:68` and `settings/Theme.qml:83` try it first |

  JSON: `{"ok":true,"family":"Fira Code","changed":["kitty","foot","gtk","shell"],"skipped":[{"file":"~/.config/alacritty/alacritty.toml","reason":"has a font of your own"}]}`.
- Then `arctic-hook font FAMILY` (§14).
- Zed and other editors keep their own font settings; the wiki says where.
- Settings > Appearance, new group "Fonts": "Code font" (`ArSelect` of `fonts`, preview line in that
  font: "0O 1lI {} => ≠ 🦊 "), "Icons in the terminal" (read-only: "Symbols for yazi, eza and
  prompts are installed" or how to get them).

**7.3.2 Nerd Font symbols: `arctic-fonts-symbols`**

- Fedora 44 has no symbols-only Nerd Font (correction), so Arctic packages it: new subpackage
  `arctic-fonts-symbols` (noarch) from Source1, the upstream "Symbols Only" release of
  ryanoasis/nerd-fonts (`NerdFontsSymbolsOnly.tar.xz`, version and SHA-256 pinned in the spec 🔍
  latest release at packaging time; GitHub wasn't reachable from this session).
  `tools/build-rpms.sh` downloads it next to the Mango tarball (`:189-205` pattern) and `%prep`
  checks the SHA-256.
- Installs `SymbolsNerdFont-Regular.ttf` and `SymbolsNerdFontMono-Regular.ttf` into
  `/usr/share/fonts/arctic-symbols/`, and `packaging/fonts/66-arctic-nerd-symbols.conf` into
  `/usr/share/fontconfig/conf.avail/` with a link in `/etc/fonts/conf.d/`:

  ```xml
  <!-- Arctic Linux: Nerd Font symbols after the code font, so yazi, eza and prompts get icons. -->
  <fontconfig>
    <match target="pattern">
      <test name="family"><string>monospace</string></test>
      <edit name="family" mode="append" binding="weak"><string>Symbols Nerd Font Mono</string></edit>
    </match>
    <match target="pattern">
      <test name="family"><string>JetBrains Mono</string></test>
      <edit name="family" mode="append" binding="weak"><string>Symbols Nerd Font Mono</string></edit>
    </match>
  </fontconfig>
  ```
- License field: the combined licence of the symbol sets in that release (MIT for the patcher;
  the glyph sets include OFL-1.1, Apache-2.0 and CC-BY-4.0 icon fonts) 🔍 read the release's
  `LICENSE` and `readme` before writing the `License:` tag.
- 🔍 kitty ≥ 0.36 carries its own Nerd symbols; check whether Fedora's kitty build keeps them, and
  that foot and alacritty pick the fallback: `fc-match -s "JetBrains Mono" | head`, then `yazi` and
  `eza --icons` in each terminal.
- `arctic-desktop` Recommends it; `iso/kiwi/config.kiwi` lists it explicitly (the `:73-79`
  pattern for things arctic-desktop only recommends).
- The colour emoji font: the shortcuts section changes `config.kiwi:154` to
  `google-noto-color-emoji-fonts` and adds it to `arctic-shell` Requires (its §11). This section's
  test checks the kiwi line (§20.2), so the correction can't be lost.

**7.3.3 One text size**

- Settings moves "Text size" to Accessibility (§8.1) and makes it cover the whole desktop:

  | Where | Effect of 100 / 110 / 125 / 150 / 175 / 200 % |
  |---|---|
  | GTK and libadwaita apps | `text-scaling-factor` as today (`arctic_settings.py:2216-2239`) |
  | Terminals | `arctic-font size` = 10.5 pt × factor, rounded to 0.5 (13 pt at 125 %) |
  | The shell and Settings | `shell.json` `textScale` = the factor, clamped to 1.25 by the shell |
  | The bar | unchanged: the bar stays 34 px (design rule), and its text stays 13 px |

- `shell/Theme.qml` gains:
  ```qml
  readonly property real textScale: Math.max(1, Math.min(1.25, Number(Session.settings.textScale) || 1))
  function fs(px) { return Math.round(px * textScale); }       // font sizes
  function rowH(px) { return Math.round(px * textScale); }     // heights of rows that hold text
  ```
  and `settings/Theme.qml` the same (reading `shell.json` with a `FileView`); `settings/components/ArText.qml:14`
  becomes `font.pixelSize: Theme.fs(size)`.
- The sweep: every `font.pixelSize: N` in `shell/*.qml` (57 today) becomes `Theme.fs(N)` and fixed
  row heights that hold text (`Launcher.qml:219`, `:204`, list rows elsewhere) use `Theme.rowH`,
  except the bar's own files (`Bar.qml`, `BarItem.qml`, `Workspaces.qml`, `UpdateIndicator.qml`).
  A Node test fails on any literal `pixelSize` outside that list (§20.1). New files from every
  section use `Theme.fs` from the start (§23); the sweep of existing files is the last package
  (X5b), after the other sections have merged, to avoid conflicts.
- 🔍 Every surface at 125 % in the headless screenshots (launcher, menu, Get apps pages, bar
  menus, OSD, lock screen, Settings pages) without clipped text.
- `arctic_settings.py text-size [FACTOR]` (new; `text-scale` stays as an alias):
  `{"ok":true,"value":1.25,"shell":1.25,"terminalPt":13,"available":true}`.

---

### 8. Accessibility page (`accessibility-page`, P2) and the other Settings changes

#### 8.1 The page

New `settings/pages/AccessibilityPage.qml` (id `accessibility`, title "Accessibility", lede "Make
things bigger, calmer and easier to reach from the keyboard."). It takes the rows that sit in
Appearance today and adds three:

| Group | Row | Control | Backend | Search key |
|---|---|---|---|---|
| Seeing | High contrast | `RowSwitch` | `contrast-set on\|off` (§8.2) | `accessibility.contrast` |
| Seeing | Text size | `ArSelect` 100-200 % | `text-size F` (§7.3.3) | `accessibility.textsize` (was `appearance.textscale`) |
| Seeing | Pointer size | `ArSegmented` (moved from `AppearancePage.qml:492-502`) | `set cursor_size=…` (unchanged) | `accessibility.cursor` (was `appearance.cursor`) |
| Seeing | Pointer style | `ArSelect` (moved from `:503-517`) | unchanged | same |
| Motion | Reduce motion | `RowSwitch` (moved from `:451-470`) | `motion-set` (unchanged) | `accessibility.motion` (was `appearance.motion`) |
| Keyboard | Keyboard pointer | `Kbd` chips "Super + Alt + K" and a "Try it" button (runs `arctic-kbptr`) | `accessibility` → `kbptr: true` when `wl-kbptr` is installed | `accessibility.kbptr` |
| Not available yet | Screen reader | read-only: "Orca isn't reliable on this kind of desktop yet: wlroots compositors like Mango don't give it the key grabs it needs." | — | `accessibility.reader` |
| Not available yet | Magnifier | read-only: "Mango has no screen magnifier yet." | — | `accessibility.zoom` |
| Not available yet | On-screen keyboard | read-only: "No on-screen keyboard that works here is packaged for Fedora 44." | — | `accessibility.osk` |

- The "Not available yet" rows say plainly what is missing (skip list, §24) and link to the wiki's
  Accessibility section. They are rows, not errors.
- Appearance keeps a one-line pointer to the moved rows ("Text size, pointer and motion are in
  Accessibility", a link that runs `main.open("accessibility", "")`), so old habits still land.
- `design/exports/mango-arctic.conf:33` ("the Settings > Accessibility switch") becomes true; the
  comment stays.
- Registration: `settings/pages/qmldir`; `settings/SearchIndex.js` `PAGES` gets
  `{ id: "accessibility", title: "Accessibility", icon: "accessibility", file: "AccessibilityPage.qml", words: "a11y contrast bigger text zoom motion pointer cursor keyboard screen reader magnifier" }`
  after `power`; the old `appearance.motion`, `appearance.textscale` and `appearance.cursor`
  entries move to the new keys; `settings/assets/SettingsIcons.js` `EXTRA` gets `accessibility`
  (§17.4). `arctic-settings accessibility` works through the existing page argument
  (`dotfiles/.local/bin/arctic-settings:29-34`).
- `settings/tests/test_app_files.py:51-53` asserts exactly 13 pages; it changes to "every `PAGES`
  file exists and every page file is in `PAGES`", since several sections add pages (§23).

#### 8.2 High contrast

- **What changes**: a high-contrast variant of whatever theme is active (Winter, Polar night, the
  wallpaper theme, a gallery theme or the person's own).
- **Engine** (`design/themegen/derive.py`): new `high_contrast(palette)` and `GUARANTEES_HC`:

  | Pair | Ratio |
  |---|---|
  | `ink` on `ground`, `surface`, `surface-raised`, `surface-sunken` | ≥ 12:1 |
  | `ink-muted`, `ink-subtle` on the same | ≥ 7:1 |
  | `ink-disabled` on `ground` | ≥ 4.5:1 |
  | `line`, `line-strong` on `ground` and `surface` | ≥ 4.5:1 (non-text is 3:1 in WCAG; HC asks for more) |
  | `accent-text` on `ground`; `on-accent` on `accent` | ≥ 7:1 |
  | `ink` on `accent-soft` and on `selection` | ≥ 7:1 |
  | `focus` on `ground` and `surface` | ≥ 4.5:1 |
  | `success`, `warning`, `error`, `info` on `ground` | ≥ 7:1 |
  | ANSI 1-6 and 9-14 on `term-background` | ≥ 7:1 |

  It also makes `frost` opaque (the `surface-raised` colour with alpha `ff`), drops the surface
  steps to two (ground and raised), sets `scrim` alpha to 0.8, and records `"contrast": "high"` in
  the palette. Moves are in OKLab lightness only, like `derive.enforce`, so hues stay.
- `arctic-themegen contrast --palette FILE` prints the HC palette; `render … --contrast high` and
  `check … --contrast high` (exit 1 when an HC guarantee fails). `render.theme_json()`
  (`render.py:66-96`) writes `"contrast": "high"` into `theme.json` when the palette has it.
- **`arctic-theme contrast on|off|toggle` [`--json`]** (new): saves
  `settings.json` `"contrast": "high"|"normal"`; while high, `activate(name)` renders the active
  theme's HC variant into `~/.local/state/arctic/themes-hc/<name>/` (remade when the source
  palette's fingerprint changes, as the wallpaper theme is) and links `current` there; `STATE`
  still holds `<name>`, so the rest of `arctic-theme` and the shell's watch are unchanged. The
  hooks get `ARCTIC_THEME_DIR` = the HC folder.
- **The shell** (`Theme.highContrast`): cards and popovers draw 2 px `line` borders; the focus ring
  is 3 px; a selected row also gets a 2 px `focus` outline (its `accentSoft` fill alone may be
  close to the background); `Popover` card colour becomes `surfaceRaised` (already opaque).
  The bar section's `MenuRow` and Settings' `ArCard`/`ArListRow` read the same flag (§23).
- **GTK**: `arctic-theme` also sets `gsettings set org.gnome.desktop.a11y.interface high-contrast true|false`
  for libadwaita's high-contrast styles on top of Arctic's colours 🔍 (prove with
  gnome-text-editor under Mango: borders thicken while Arctic's colours stay). GTK 3 apps get the HC
  colours through `gtk.css`; F44 has no `gnome-themes-extra` (mdapi 400 ✅), so there is no separate
  GTK 3 HighContrast theme to switch to.
- **Qt**: the qt5ct/qt6ct palettes are rendered from the HC palette like every other template.
- **Mango**: window borders come from the theme's `mango-colors.conf`, so they follow; blur is
  irrelevant because `frost` is opaque.
- `settings/tests` and `design/themegen/tests` check the HC variant of Winter, Polar night, every
  gallery palette and a wallpaper-derived palette (§20).

#### 8.3 Keyboard pointer (`Super + Alt + K`)

- Tool: `wl-kbptr` 0.4.1 ✅ (mdapi 200; ships `/usr/share/doc/wl-kbptr/config.example` ✅). It
  needs the virtual-pointer protocol, which Mango creates ✅ (verification).
- `dotfiles/.local/bin/arctic-kbptr` (new, bash):
  ```bash
  command -v wl-kbptr >/dev/null || { arctic-osd notice alert "Keyboard pointer isn't installed" "Get apps: wl-kbptr"; exit 1; }
  pkill -u "$UID" -x wl-kbptr && exit 0          # the key again closes it
  conf="${XDG_CONFIG_HOME:-$HOME/.config}/arctic/current/wl-kbptr/config"
  [[ -r "$conf" ]] && exec wl-kbptr -c "$conf" -o modes=tile,bisect
  exec wl-kbptr -o modes=tile,bisect
  ```
  🔍 `-c`, `-o` and `modes=tile,bisect` against wl-kbptr 0.4.1's man page.
- Theme: new template `design/themegen/templates/wl-kbptr/config.tmpl` → `<theme>/wl-kbptr/config`:
  labels in `ink` on `surface-raised`, the chosen label in `on-accent` on `accent` (the pointer's
  target is "here"), selectable areas outlined in `focus`, the rest dimmed with `scrim`; keys
  copied from `config.example` 🔍.
- `dotfiles/.config/mango/arctic/rules.conf:15` region: add
  `layerrule=noblur:1,noanim:1,noshadow:1,layer_name:^wl-kbptr$` 🔍 (its layer namespace; check
  with `mmsg get all-layers` while it is open).
- `arctic-desktop` Recommends `wl-kbptr` (§19).

#### 8.4 Other Settings changes made here

| Page | Change |
|---|---|
| Appearance > Theme (`AppearancePage.qml:97-173`) | "Switch automatically" row (§7.1, key `appearance.schedule`); "More themes" grid and "Add a theme from the web…" (§7.2.6, `appearance.gallery`) |
| Appearance, new group "Fonts" | "Code font" (§7.3.1, `appearance.font`) |
| Appearance > Wallpaper (`:175-350`) | "Change the wallpaper" rotation row (§15, `appearance.rotate`) |
| Appearance, new group "Top bar and calendar" | "Weather in the calendar", "Place", "Units", "Show the temperature on the bar", "Show CPU and memory on the bar", and a "Hide the bar" row with the key and a "Hide it now" button (§10, §11, §12; keys `appearance.weather`, `appearance.place`, `appearance.barsystem`, `appearance.barhide`) |
| Appearance ("Text and motion" `:449-488`, "Pointer" `:490-518`) | moved to Accessibility (§8.1) |
| Default apps (`AppsPage.qml`, 70 lines), new group "Search" | "Search the web with" (`ArSelect` of §5.8's engines; Custom shows a URL field checked for `https://` and `%s`), "Find files from the launcher" (`fileSearch`) — keys `apps.websearch`, `apps.filesearch`. The web-app section also edits this page (roles); the group goes after theirs |

New `arctic_settings.py` commands (all print one JSON object; writers join `WRITERS`,
`:2565-2567`, so they take `settings_lock`):

| Command | Does |
|---|---|
| `accessibility` | `{ok, contrast, textScale, motion, kbptr}` in one call for the page |
| `contrast-set on\|off` | `arctic-theme contrast on\|off --json` |
| `text-size [F]` | §7.3.3 (`text-scale` kept as an alias) |
| `fonts` / `font-set FAMILY` | `arctic-font list\|set --json` |
| `theme-schedule` / `theme-schedule-set off\|sun\|hours L D` | `arctic-theme schedule …` |
| `theme-install URL` / `theme-remove NAME` / `theme-update NAME` | §7.2.6 |
| `location` / `location-search TEXT` / `location-set timezone\|place NAME LAT LON` | `arctic-sun location …`; `location-search` runs `weather.py geocode` (§12.2) — the only network call, made when the person searches |
| `weather-settings` | the `shell.json` weather keys and the last cached reading |
| `wallpaper-rotate off\|30m\|1h\|1d [FOLDER]` | §15 |
| `shell-set KEY VALUE` | the bar section's writer; its allowlist gains `textScale`, `monoFont`, `webSearch`, `webSearchUrl`, `fileSearch`, `weather`, `weatherUnits`, `barWeather`, `barSystem` with their types |

`TOOLS` (`:2519-2524`) gains `wlKbptr: 'wl-kbptr'`, `fd: 'fd'`, `qalc: 'qalc'`,
`arcticFont: 'arctic-font'`, `arcticSun: 'arctic-sun'`, `arcticMenu: 'arctic-menu'`.

---

### 9. First-login welcome and first-boot progress (`first-login-welcome`, P1)

#### 9.1 When it shows

- Only for accounts created from the 0.3.0 skeleton: `dotfiles/.config/arctic/first-login` (new,
  one comment line: "Arctic shows its welcome once, then deletes this file.") goes into
  `/etc/skel` through the existing tar (`packaging/arctic-linux.spec:621-625` excludes only
  `.config/arctic/themes` and `current`). The installer creates the account with
  `useradd --root /mnt --create-home` ✅ (`internal/installer/installer_test.go:158`), which copies
  the target's skeleton. Accounts that existed before 0.3.0 don't have the file, so an upgrade never
  greets an old user as new (the system section's "What's new" covers upgrades).
- `dotfiles/.local/bin/arctic-welcome` (`:10` today exits on installed systems — correction applied):

  ```bash
  if ! arctic-is-live; then
    marker="${XDG_CONFIG_HOME:-$HOME/.config}/arctic/first-login"
    [[ -e "$marker" ]] || exit 0
    if [[ "${ARCTIC_SHELL:-quickshell}" != waybar ]]; then
      for _ in $(seq 120); do
        if arctic-shell-ipc welcome firstLogin >/dev/null 2>&1; then rm -f "$marker"; exit 0; fi
        sleep 0.5
      done
    fi
    sleep 2
    logo="${XDG_DATA_HOME:-$HOME/.local/share}/arctic/logos/arctic-mark-polar-night.svg"
    [[ -f "$logo" ]] || logo=/usr/share/arctic/logos/arctic-mark-polar-night.svg
    notify-send -a "Arctic Linux" -t 0 -i "$logo" "Welcome to Arctic Linux" \
      "Super + Space: apps and search · Super + Alt + Space: every command · Super + /: all shortcuts"
    rm -f "$marker"; exit 0
  fi
  # … the live-session code below is unchanged (:11-38)
  ```
- `autostart.conf:16` already runs `arctic-welcome` at every login; nothing else changes there.
- The Learn branch's "Show the welcome again" calls `welcome again` at any time (§4.6).

#### 9.2 The card (`shell/FirstLoginWelcome.qml`, new)

- Same frame as `LiveWelcome.qml:36-137`: desktop layer (`WlrLayer.Bottom`, namespace
  `arctic-desktop`, already covered by `rules.conf:15`), `keyboardFocus: OnDemand`, 480 px, `frost`,
  `radiusXl`, fades with `fadeSlow`. The fox mark is drawn without amber eyes (D9).
- Title "Welcome to Arctic Linux" (28/600), lede "Five things to get going. Everything else is one
  search away." (15, `inkMuted`).
- Steps — one row each: glyph, title (15/600), one line (13, `inkMuted`), `Kbd` chips, and one
  ghost button; the digits 1-5 run the visible steps' buttons in order:

  | # | Step | Line | Keys | Button | Shown |
  |---|---|---|---|---|---|
  | 1 | Apps and search | "Apps, settings, windows, files and quick sums." | Super + Space | Try it → launcher | always |
  | 2 | Every command | "Capture, toggles, themes, the power menu and more." | Super + Alt + Space | Try it → command menu | always |
  | 3 | Connect to Wi-Fi | "You're offline. Pick a network to finish setting up." | Super + Ctrl + W | Choose a network → the bar section's `openPanel('network')` | only when `nm-online -q -t 0` fails 🔍 (exit status when offline; Omarchy's first run gates on `nm-online`) |
  | 4 | Get apps | "Flathub, Fedora packages and web apps." | Super + Shift + A | Get apps → `shell.openGetApps(null,'choose','')` (Get apps section) | not live |
  | 5 | Light or dark | two small theme cards, Winter and Polar night (the current one selected) | Super + Shift + T | (the cards themselves) → `arctic-theme set …` | always |

  Under the steps: "Every shortcut: Super + /" as a link (`shell.toggleKeys()`; the generated
  sheet, shortcuts section §13), and a "Finishing setup" line when `FirstbootService` reports work
  in progress (§9.3).
- Buttons: **Done** (primary) and **Take the tour** (ghost; opens the wiki's Desktop tour). Esc =
  Done. The card doesn't reopen on its own. Amber appears only on Done and on the current theme's
  card in step 5 (it is "here").
- Keyboard: Tab / Shift + Tab through step buttons, theme cards and the two buttons; Enter / Space
  activate; 1-5 run a step; Esc closes. The focus ring shows after the first key.
- IPC (`shell.qml:125-129`):
  ```qml
  IpcHandler {
      target: 'welcome'
      function open(): void { welcome.show(); }              // live card, unchanged
      function firstLogin(): void { firstLoginCard.show(); }
      function again(): void { firstLoginCard.show(); }      // "Show the welcome again" (Learn menu)
  }
  ```

#### 9.3 First-boot progress (`/var/lib/arctic/firstboot-status.json`)

`arctic-firstboot` runs as root at boot and can't reach the user's notification server, so it
writes a status file, and the shell (running as the user) turns it into notifications — the
`update-status.json` pattern.

- `packaging/firstboot/arctic-firstboot` writes (0644, atomic, next to `pending.json`):
  ```json
  {"version":1,"state":"installing","restart_needed":false,
   "apps":[{"id":"zed","name":"Zed","state":"done"},
           {"id":"steam","name":"Steam","state":"installing"},
           {"id":"spotify","name":"Spotify","state":"pending"}],
   "started_at":"2026-09-28T10:02:11Z","updated_at":"2026-09-28T10:04:40Z","next_try_at":""}
  ```
  - `state`: `installing` while `retry()` runs (`:278-301`), `waiting` when modules are left and
    the service will retry in 15 minutes (`next_try_at` set), `done` when `pending.json` is
    deleted (`main`, `:303-333`), `failed` for modules dropped as impossible ("no install methods
    known", `:285-287`).
  - `restart_needed`: true when `enroll_key()` queued a MOK enrolment (a driver needs the one-time
    code at the next restart).
  - Written at start, after each module, and at the end. Tests in
    `packaging/firstboot/test_arctic_firstboot.py` (§20.2).
  - The spec lists it as `%ghost %attr(0644,root,root) %verify(not md5 size mtime)
    %{_sharedstatedir}/arctic/firstboot-status.json` (as `update-status.json`, spec `:1122`).
- `shell/FirstbootService.qml` (new singleton) watches the file (`FileView`, `watchChanges`) and
  sends each notification once (keys kept in `~/.cache/arctic/firstboot-notified`); texts come from
  pure `shell/FirstbootStatus.js` (tested):

  | State | Title | Body |
  |---|---|---|
  | `installing` (first time for this `started_at`) | Finishing setup | "Installing 3 apps you picked: Zed, Steam and Spotify. You can keep working." |
  | `waiting` (once per boot) | Waiting for the internet | "2 apps will install when this computer is online." |
  | `done` | All set | "Zed, Steam and Spotify are installed." |
  | `failed` | 1 app couldn't be installed | "Steam: no way to install it was found. Try again from Get apps." — action "Open Get apps" |
  | `restart_needed` | Restart to finish | "The NVIDIA driver finishes installing at the next restart. Have the code from the end of installation ready." |

  App name "Arctic Linux", icon `package`. Lists of names use "A, B and C"; more than four become
  "Zed, Steam, Spotify and 3 more".
- The welcome card shows "Finishing setup: installing Steam (2 of 3)…" with the bar section's
  `Spinner` while `state` is `installing`.

---

### 10. Show and hide the bar (missed gap)

#### 10.1 The rule it keeps

The design fixes the bar at 34 px on the top edge of every display (`design/brand-book.md:70`,
`design/guidelines/10-platforms.md:11,23`), and the skip list refuses repositioning, reordering
and transparency for that reason (§24). Hiding the bar on demand keeps all three: when it is
shown, it is exactly the bar the design describes. It is a key (`Super + Shift + Space`, Omarchy's)
and a menu row, not a setting that changes the layout, and it is never automatic (no auto-hide).

#### 10.2 Behaviour

- `Super + Shift + Space` (row 56), the menu row `style.bar`, the Appearance row "Hide it now", and
  a `ToggleRegistry` entry `bar` (`label: "Top bar"`, icons `eye`/`eye-off`, `indicator: false`,
  no Quick Settings tile) all call `shell.toggleBar()`.
- State: `~/.local/state/arctic/bar-hidden` exists = hidden (a flag file, like Omarchy's toggle
  flags). Kept across restarts of the shell and logins. `Session.barHidden` reads it at start;
  `toggleBar()` flips the property and creates or removes the file (`touch` / `rm -f` via
  `execDetached`).
- On hide: OSD notice "Top bar hidden", detail "Super + Shift + Space shows it" (every time; it is
  short). On show: nothing.
- While hidden:
  - `Bar.qml` (`:14-27`): `visible: !Session.barHidden` — the layer surface goes away, its
    exclusive zone with it, and Mango lays windows out to the top frame edge.
  - `ScreenFrame.qml:23`: `margins.top: Theme.topInset`, and a fourth `Reserve` anchored top
    (`visible: Session.barHidden && Theme.frameWidth > 0`, next to `:87-89`), so windows keep the
    frame's gap at the top.
  - `Popover.qml:40`: `margins.top: Theme.topInset`. The launcher, menus and the power menu hang
    from the screen's top edge instead of the bar.
  - The bar section's toasts (`margins.top: barHeight + space2`, its §5.4.2) use `Theme.topInset`.
  - Bar menus still open by key (calendar `Super + Ctrl + T`, battery `Super + Ctrl + P`, Quick
    Settings `Super + A`, …). The bar section's `openPanel()` (its §3.2) returns early when an
    anchor is `null`; with the bar hidden it uses the item's last known x instead
    (`Bar.qml` caches `anchorFor(name)` for every item each time it lays out while visible), else
    the centre for `calendar`, `media` and `notifications` and the right edge
    (`width - space2 - frameWidth - panelWidth / 2`) for the rest. This gives Omarchy's "notices"
    (time, battery, weather) without new keys.
  - **Privacy stays visible**: while the bar is hidden and the bar section's `PrivacyService`
    reports the microphone, camera or screen sharing in use, or a toggle with `tone: 'error'` is on
    (screen recording, shortcuts section §8), `shell/PrivacyPeek.qml` (new) shows those pills alone
    in a small `PanelWindow` at the top-right corner (Overlay layer, namespace
    `arctic-indicators`, no input region). It reuses the bar section's `ModeIndicators` with a new
    `urgentOnly: true` property (§23). `rules.conf:15` adds `indicators` to its namespace list.
- The live USB never hides the bar (the Install item lives there): the key does nothing and the
  row is hidden (`{"live": false}`).
- IPC: the bar section's `bar` target (`focus()`) gains `toggleHidden(): string` (returns
  `hidden`/`shown`) and `shown(): bool`.
- In the waybar session the key's `arctic-shell-ipc` call fails and nothing happens. (waybar can
  hide itself on `SIGUSR1`, but the fallback session is for recovery; the wiki says the key needs
  the Arctic shell.)

---

### 11. System resource monitor (missed gap)

#### 11.1 What it is

A "System" panel with live CPU, memory, temperature, graphics, disk and network numbers and the
processes using the most, plus an optional compact bar item. Off the bar by default (calm bar; the
skip list's "resource graphs" stay out: no graphs, numbers and short meters only).

#### 11.2 Data: `shell/scripts/sysmon.py` (new, standard library)

```
sysmon.py watch [--interval 2] [--procs N] [--root DIR]    JSON lines, one per sample, until stdin closes
sysmon.py once [--procs N] [--root DIR]                    one line
sysmon.py kill PID [--force]                               end one of your own processes
```

```json
{"ok":true,"t":1759070000,
 "cpu":{"percent":12.5,"cores":8,"load":[0.52,0.61,0.70],"temp_c":54.0,"freq_mhz":2400},
 "memory":{"total_mb":15872,"used_mb":4210,"percent":26.5,"swap_total_mb":8192,"swap_used_mb":0},
 "gpus":[{"name":"AMD Radeon 780M","percent":7,"temp_c":48}],
 "disks":[{"mount":"/","total_gb":475.9,"used_gb":112.3,"percent":23.6}],
 "net":{"rx_bps":12000,"tx_bps":3400},
 "procs":[{"pid":1234,"name":"firefox","cpu":8.1,"mem_mb":812,"mine":true}]}
```

- CPU: `/proc/stat` deltas between samples; load from `/proc/loadavg`; frequency from
  `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq` (average).
- Memory: `/proc/meminfo` (`used = MemTotal − MemAvailable`; swap includes zram).
- Temperature: hwmon by name — `k10temp` (`Tctl`), `zenpower`, `coretemp` (`Package id 0`),
  then thermal zone `x86_pkg_temp`, then `acpitz`; none → the row is hidden. 🔍 labels on one Intel
  and one AMD laptop.
- Graphics: `amdgpu` `/sys/class/drm/card*/device/gpu_busy_percent` and its hwmon `edge`; NVIDIA
  through `nvidia-smi --query-gpu=name,utilization.gpu,temperature.gpu --format=csv,noheader,nounits`
  when installed, and only while the panel is open; Intel shows no percentage (no sysfs counter)
  and only appears with a temperature. 🔍 paths on F44 kernels.
- Disks: `os.statvfs` on `/` and `/home`, one row per device (`st_dev`), so the btrfs subvolumes
  show once.
- Network: `/proc/net/dev` deltas, loopback and virtual interfaces left out.
- Processes (only with `--procs`): `/proc/<pid>/stat` CPU deltas and `statm` RSS, top N by CPU;
  `mine` = the process's uid is the user's.
- `kill`: only processes owned by the user (else `{"ok":false,"code":"not_yours","error":"That
  process belongs to another user."}`); SIGTERM, or SIGKILL with `--force`.
- `--root` points `/proc` and `/sys` at test fixtures.

#### 11.3 Shell pieces

- `shell/SystemService.qml` (singleton): runs `sysmon.py watch` only while needed — the panel is
  open (`--interval 2 --procs 5`) or the bar item is on (`--interval 5`). Stops otherwise.
- `shell/SystemPanel.qml` (new bar-menu panel id `system`, width 340, hosted by the bar section's
  `BarMenu`):
  - rows (the bar section's `MenuRow`/`MenuSection`): CPU "12 %" with a 6 px meter and "8 cores ·
    2.4 GHz"; Memory "4.1 of 15.5 GB"; Temperature "54 °C"; Graphics per GPU; Disk "112 of 476 GB
    used"; Network "↓ 1.2 MB/s · ↑ 40 KB/s".
  - meters are `lineStrong` on `surfaceSunken`; above 90 % the meter turns `warning` and the row
    gains the word "High" (never colour alone). No amber.
  - "Using the most": five processes (name, CPU %, memory). Enter or click opens an actions page:
    "End process" (SIGTERM) and "Force quit" (SIGKILL, confirm "Force quit firefox? Unsaved work
    is lost."). Other users' processes show no actions.
  - footer: "Open Activity" (the system section's `Ctrl + Shift + Esc` btop window) and "Open
    Mission Center" when `io.missioncenter.MissionCenter` is installed (Arctic's optional module,
    `modules/extras/mission-center`).
- `shell/SystemItem.qml` (bar item, only when `shell.json` `barSystem` is true): `cpu` glyph and
  "12 %" (13 px tabular, `inkMuted`), tooltip "CPU 12 % · memory 4.1 of 15.5 GB · 54 °C". Left
  click → `togglePanel('system')`. It sits first in the right group of `Bar.qml` (`:99-103`),
  before the Install / update items.
- Reached also from: Quick Settings (a "System" row at the bottom with the CPU and memory summary,
  chevron → the `system` page; bar section §5.11), the command menu's root row `activity` "System
  activity" (§4.6), and the launcher ("cpu", "memory", "activity", "task manager" match that row).
- Settings: Appearance > Top bar and calendar > "Show CPU and memory on the bar" (`barSystem`).

---

### 12. Weather (`weather`, P2, optional, off by default)

#### 12.1 Behaviour

- Off until the person turns on Settings > Appearance > Top bar and calendar > "Weather in the
  calendar". Nothing is requested before that.
- Then the calendar panel (bar section §5.5) shows current conditions and five days under the
  month grid; optionally a small temperature item sits right of the clock ("Show the temperature
  on the bar", `barWeather`, off by default).
- Data: Open-Meteo, no account or key. (Omarchy's bar weather uses wttr.in; Open-Meteo backs its
  Elsewhen panel — correction noted. Open-Meteo is chosen here because it is a documented JSON API
  with no key, free for non-commercial use, and asks for attribution, which the card shows.)
  🔍 Open-Meteo's terms for a default-off OS feature used by many machines (non-commercial, under
  10 000 calls a day per machine — Arctic makes at most 24).
- Location: the saved location (§7.1.3) — the time zone's city by default, or a place the person
  searched for. No IP geolocation.
- Refresh: 10 s after the shell starts, then hourly, and when the calendar opens if the reading is
  older than 30 minutes. Skipped while offline (`NetworkService`, `shell/NetworkService.qml`, which the bar section extends).
  The last reading is cached, so the card shows it with "Updated 2 h ago" when offline.

#### 12.2 `shell/scripts/weather.py` (new, standard library)

```
weather.py now [--units metric|imperial|auto] [--max-age SECONDS] [--json]
weather.py geocode TEXT [--lang CODE] [--json]
```

- `now` request (coordinates rounded to 2 decimals, about 1 km):
  `https://api.open-meteo.com/v1/forecast?latitude=31.78&longitude=35.22&current=temperature_2m,apparent_temperature,weather_code,is_day,wind_speed_10m&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,sunrise,sunset&timezone=auto&forecast_days=5&temperature_unit=celsius&wind_speed_unit=kmh`
  (`fahrenheit` / `mph` for imperial; `auto` = imperial when `LC_MEASUREMENT` or `LANG` is `en_US`,
  `en_LR` or `my_MM`, else metric). `User-Agent: Arctic-Linux/0.3 (weather in the calendar)`,
  10 s timeout.
- Cache `~/.cache/arctic/weather.json`; `--max-age` (default 3600) returns the cache when fresh.
- Output:
  `{"ok":true,"place":"Jerusalem","units":"metric","fetched_at":1759070000,"attribution":"Open-Meteo.com",
    "current":{"temp":21.4,"feels":22.0,"code":2,"is_day":true,"wind":12},
    "daily":[{"date":"2026-09-28","code":3,"max":27,"min":19,"rain":10,"sunrise":"06:32","sunset":"18:24"}]}`;
  offline: `{"ok":false,"code":"offline","error":"Can't reach Open-Meteo.","cached":{…}}`.
- `geocode` (only from the Settings place search, on Enter):
  `https://geocoding-api.open-meteo.com/v1/search?name=<text>&count=6&language=<lang>&format=json` →
  `{"ok":true,"places":[{"name":"Haifa","detail":"Haifa District, Israel","lat":32.79,"lon":34.99}]}`.

#### 12.3 Shell

- `shell/Weather.js` (pure, tested): WMO weather code → glyph and words, day or night
  (0 "Clear" `sun`/`moon`; 1-2 "Partly cloudy" `cloud-sun`; 3 "Cloudy" `cloud`; 45, 48 "Fog"
  `fog`; 51-57 "Drizzle", 61-67 "Rain", 80-82 "Showers" `cloud-rain`; 71-77, 85-86 "Snow"
  `snowflake`; 95-99 "Thunderstorm" `cloud-lightning`); `tempText(t, units)` ("21°").
- `shell/WeatherService.qml` (singleton): runs `weather.py` on the schedule above; `enabled`,
  `current`, `daily`, `place`, `updatedText`, `showInBar`.
- `shell/WeatherCard.qml`: current (32 px glyph, "21°" 28/600 tabular, "Partly cloudy · feels 22°"
  13 `inkMuted`), five columns (day name, glyph, max / min), footer "Jerusalem · Open-Meteo.com ·
  updated 14:05" (12, `inkSubtle`). No amber. Enter on the card refreshes.
- The bar section's `CalendarPanel.qml` gets a slot under the grid:
  `Loader { active: WeatherService.enabled; sourceComponent: WeatherCard {} }` (§23).
- `shell/WeatherItem.qml` (bar item right of the clock, before the bar section's `MediaItem`, only
  when `barWeather` and a reading exist): glyph + "21°"; click → the calendar panel; tooltip "Partly
  cloudy, 21° in Jerusalem".

#### 12.4 Settings (Appearance > "Top bar and calendar")

| Row | Control |
|---|---|
| Weather in the calendar | switch → `shell-set weather true\|false` |
| Place | "Jerusalem (from your time zone)" + "Change…" → dialog: "From my time zone" / "A place I choose" with a search field (`location-search`, on Enter) and results; → `location-set …`. Also used by the automatic light/dark schedule and night light |
| Units | Automatic / °C / °F → `weatherUnits` |
| Show the temperature on the bar | switch (`barWeather`), enabled when weather is on |
| Show CPU and memory on the bar | switch (`barSystem`) (§11) |
| Hide the bar | "Super + Shift + Space hides and shows the top bar" + "Hide it now" (§10) |

---

### 13. Reminders (`reminders`, P2)

#### 13.1 `arctic-remind` (new, Python 3 standard library)

```
arctic-remind add WHEN TEXT…       WHEN: 90s, 10m, 1h, 1h30m, 1.5h, "10 min", "2 hours", or 15:30 (today, else tomorrow)
arctic-remind list [--json]
arctic-remind cancel ID|all
arctic-remind fire ID              run by the timer
arctic-remind restore              at login: re-arm the future ones, report the missed ones
```

- State `~/.local/state/arctic/reminders.json`:
  `{"version":1,"reminders":[{"id":"a1b2c3","text":"Tea","due":1759071600,"created":1759071000}]}`
  (atomic writes under a `flock`). Text: 1-200 characters, no control characters.
- `add` arms one transient timer per reminder with a calendar time, so a suspend doesn't delay it:
  `systemd-run --user --unit=arctic-reminder-<id> --collect --quiet
   --on-calendar='2026-09-28 15:40:00' --timer-property=AccuracySec=1s
   -- arctic-remind fire <id>` (Omarchy uses `systemd-run --user --on-active`; verification).
  The text stays in the state file, not on a command line.
- `fire`: `notify-send -a "Arctic Linux" -u critical -i appointment-soon -h boolean:x-arctic-alert:true
  -A snooze="In 5 minutes" -A done="Done" "Reminder" "Tea"` — the bar section's rule lets Arctic
  alerts through do not disturb (its §5.4.5), which a reminder the person set should do. "In 5
  minutes" re-adds it. Then the entry is removed.
- `cancel`: `systemctl --user stop arctic-reminder-<id>.timer` and remove the entry.
- `restore` (run by the shell's `RemindService` at start): future reminders whose timer unit is
  gone (logout, restart) are re-armed; past ones are notified once as "Missed while you were
  away: Tea (15:40)" and removed.
- JSON: `{"ok":true,"reminders":[{"id":"a1b2c3","text":"Tea","due":1759071600,"due_text":"15:40","in_text":"in 12 min"}]}`.

#### 13.2 Where people meet it

- **Key** `Super + Ctrl + R` (row 54) opens the command menu's Reminders branch: "Set a
  reminder…" (input mode, §4.9), the waiting ones (Delete cancels), "Cancel all reminders".
- **Launcher**: `shell/Reminders.js` (pure, tested) parses "remind 10m tea", "remind me in 10
  minutes to stretch", "remind 15:30 call Dana", "timer 5m" (text "Timer") into
  `{seconds|at, text}`; the launcher shows the row "Remind me at 15:40: tea" (§5.2) and Enter adds it
  with an OSD notice. English words only in 0.3.0; the wiki says so.
- **Indicator**: `shell/RemindService.qml` (singleton, watches the state file) registers a
  `ToggleRegistry` entry `reminders` of a new kind `status` (bar section §5.11: shown as a mode
  indicator while active, no Quick Settings tile, clicking opens `arctic-menu remind`), glyph
  `timer`, detail "Tea at 15:40".
- **Notification centre**: `shell/ReminderList.qml` rows (text, "15:40 · in 12 min", an `x`
  button / Delete) at the top of the bar section's `NotificationCenter` while any are waiting (§23).

---

### 14. User hooks (`user-hooks`, P2, with the correction)

#### 14.1 The contract (the existing theme-hooks contract, generalised)

`arctic-theme`'s hooks already do what the gap item asked for one event. New events follow the same
rules and the same naming, so there is one contract, documented once (BUILD-SPEC §10, 9.7):

| Event | Folders (system, then yours; yours win by file name) | Fired by | `$1` |
|---|---|---|---|
| `theme` | `/usr/share/arctic/theme-hooks.d`, `~/.config/arctic/theme-hooks.d` | `arctic-theme` (unchanged, `:456-496`) | — (`ARCTIC_THEME_DIR`, `ARCTIC_THEME_MODE`, `ARCTIC_THEME_NAME` as today) |
| `wallpaper` | `…/wallpaper-hooks.d` | `arctic-wallpaper` after it draws a new choice or a rotation step (not a plain redraw) | the picture's path |
| `font` | `…/font-hooks.d` | `arctic-font set` | the family |
| `lock` | `…/lock-hooks.d` | the shell, when `LockScreen.secure` becomes true | — |
| `unlock` | `…/unlock-hooks.d` | the shell, after the unlock timer (`LockScreen.qml:82`) | — |
| `battery-low` | `…/battery-low-hooks.d` | the bar section's `BatteryService`, with its low warning | the percentage |
| `post-update` | `…/post-update-hooks.d` | the shell's `UpdateService`, once per new `installed_at` (§14.3) | the Arctic version (`VERSION_ID`) |
| `login` | `…/login-hooks.d` | `autostart.conf`: `exec-once=arctic-hook login` (after the other lines) | — |

Rules, unchanged from theme hooks: every executable regular file runs in file-name order; a file of
yours replaces the system hook of the same name, and a non-executable one of yours disables it;
names starting with `.` or ending in `~`, `.rpmnew`, `.rpmsave`, `.rpmorig`, `.disabled` (and now
`.sample`) are skipped; stdin is `/dev/null`; each hook is stopped (its process group killed)
after 5 s; up to 4 KB of its output is passed on as a warning; a failing hook never fails the event.
New: `ARCTIC_HOOK_EVENT` and `ARCTIC_HOOK_VALUE` are set, the value is also `$1`, and warnings go
to the journal too (`syslog` with identifier `arctic-hook`, so `journalctl --user -t arctic-hook`
shows them), because events fired from the shell have no terminal. No parallel
`~/.config/arctic/hooks/theme-set.d` is added (correction applied).

#### 14.2 `arctic-hook` (new, Python 3 standard library)

```
arctic-hook EVENT [VALUE]      run EVENT's hooks (theme is refused: arctic-theme runs those)
arctic-hook --list [--json]    every event, its folders and the hooks that would run
arctic-hook --open             create ~/.config/arctic and open it in the file manager (menu row setup.hooks)
```

- One run per event at a time (`flock` on `$XDG_RUNTIME_DIR/arctic/hook-<event>.lock`); callers
  start it detached (`execDetached`, `&` in bash), so a slow hook never delays locking or drawing.
- The skip/replace/timeout logic is a copy of `arctic-theme`'s `run_hooks` with the same tests run
  against both (§20.2), so the two can't drift.
- Samples (not run: `.sample`) are installed as documentation in
  `/usr/share/doc/arctic-desktop-config/hooks/`: `lock-hooks.d/10-pause-media.sample`
  (`playerctl pause`), `battery-low-hooks.d/10-power-saver.sample`
  (`powerprofilesctl set power-saver`), `post-update-hooks.d/10-log.sample`,
  `wallpaper-hooks.d/10-copy.sample`, `login-hooks.d/10-example.sample`. Home folders stay clean.

#### 14.3 The post-update signal

- `dotfiles/.local/bin/arctic-update:282` (`installed)` branch of `check_last_install`) also sets
  `installed_at=@now` in the status file.
- `shell/UpdateStatus.js` `parse()` (`:16-35`) reads `installed_at`; `shell/UpdateService.qml`
  runs `arctic-hook post-update "$VERSION_ID"` when it sees a value it hasn't handled (kept in
  `~/.cache/arctic/post-update-hooked`, as `update-notified` is, `:33-39`).
- The system section's "What's new after updates" (`fedora-upgrade-whats-new`) can read the same
  field (§23).

---

### 15. Wallpaper rotation (missed gap, P3)

- Last package of this section; if time runs short it moves to 0.3.1 without affecting anything
  else.
- `arctic-wallpaper next` (new verb): picks the next picture (by name, or random without repeats in
  one pass) from the folder, records it in `~/.cache/arctic/wallpaper-current` as today
  (`arctic-wallpaper:127`), saves it as the wallpaper choice (`~/.config/arctic/wallpaper`) and lets
  the colours follow (`arctic-theme sync --no-redraw`, or `ARCTIC_WALLPAPER_NO_SYNC=1` to skip), so
  the desktop never keeps the colours of a wallpaper that is no longer on screen. Arctic's own
  wallpapers are saved by name, so they bring back Winter / Polar night like a manual choice does.
- `arctic-wallpaper rotate off|30m|1h|1d [FOLDER]` saves
  `~/.config/arctic/wallpaper-rotate.json` `{"every":"30m","folder":"~/Pictures/Wallpapers","shuffle":true}`
  and arms `systemd-run --user --unit=arctic-wallpaper-rotate --collect --quiet
  --on-active=30m --on-unit-active=30m -- arctic-wallpaper next`. `arctic-wallpaper rotate apply`
  re-arms it at login (`autostart.conf`, after `arctic-theme apply`).
- Settings > Appearance > Wallpaper: "Change the wallpaper" — Never / Every 30 minutes / Every hour
  / Every day, and "From" (your wallpaper folder, the design wallpapers, or a folder chosen with the
  portal file chooser). Description: "A new picture now and then, with the colours following it."
- Fires the `wallpaper` hook with each picture.

---

### 16. Dictation: not in 0.3.0

Decision: **deferred**, planned as an optional module after 0.3.0.

Why:

1. **No Fedora package for the tool Omarchy uses.** Voxtype is not in F44 (mdapi 404 in one
   verification pass, 400 in the other).
2. **The engine exists, the model doesn't.** `whisper-cpp` 1.8.1 is in F44 ✅, but no model is
   packaged. A useful model is a 150-500 MB download (English-only base up to multilingual small),
   and Arctic's installer offers Hebrew, Arabic and CJK, which need the larger multilingual models.
   That needs a consent screen, a pinned checksum, a storage location and an update story — a
   feature of its own, not a toggle.
3. **Latency and battery.** CPU transcription on a typical laptop is seconds per sentence 🔍; a
   dictation feature that feels slow does more harm than none.
4. **Priority.** The gap list files it under AI features to revisit later ("Revisit dictation later
   with whisper-cpp"); the verification rates it P2 (optional) or P3.

What it would take (for the follow-up, so the design isn't lost): a catalog module
`modules/accessibility/dictation` (Get apps and the installer) that installs `whisper-cpp`,
downloads a chosen model with its SHA-256; a helper `arctic-dictate toggle` (record with `pw-record`
at 16 kHz mono, transcribe with whisper-cpp's CLI, type with `wtype`, which the shortcuts section
already adds); `Super + Ctrl + X` (free today, kept free); the microphone privacy pill appears
automatically because it records through PipeWire (bar section's `PrivacyService`).

---

### 17. File-by-file changes

Work-package ids (X0-X13) are defined in §22.

#### 17.1 New files

| File | WP | What |
|---|---|---|
| `shell/CommandMenu.js` | X1 | pure menu model (§4) |
| `shell/CommandMenuService.qml` | X1 | loads menu files, guards, providers, select/input requests |
| `shell/CommandMenu.qml` | X1 | the `menu` view in the launcher card |
| `shell/LauncherRow.qml` | X1 | row delegate moved from `Launcher.qml:213-266`, `compact` variant |
| `shell/WindowList.qml` | X1 | open windows (`mmsg`, fallback `ToplevelManager`) |
| `shell/menu/00-arctic.json` | X1 | root branches and this section's rows (§4.6) |
| `dotfiles/.local/bin/arctic-menu` | X1 | routes, `select`, `input`, `list`, fuzzel fallback |
| `shell/FileSearch.qml` | X2 | one `fd` process at a time (§5.6) |
| `shell/Units.js` | X2 | `looksLikeConversion`, `looksLikeMath` (§5.7) |
| `shell/dev/export-settings-index.cjs` | X2 | writes `shell/assets/settings-index.js` |
| `shell/assets/settings-index.js` | X2 | generated from `settings/SearchIndex.js` |
| `shell/OsdModel.js` | X3 | durations, widths, icon fallback (§6.1) |
| `design/themegen/named.py` | X4 | `colors.toml` → palette (§7.2.2) |
| `design/themes/<name>/colors.toml`, `SOURCE` (11 themes) | X4 | gallery palettes (§7.2.1) |
| `design/themegen/templates/wl-kbptr/config.tmpl` | X4 | keyboard pointer colours (§8.3) |
| `dotfiles/.local/bin/arctic-sun` | X0 | location and sun times (§7.1.3) |
| `dotfiles/.local/bin/arctic-font` | X5 | code font and terminal size (§7.3.1) |
| `packaging/fonts/66-arctic-nerd-symbols.conf` | X5 | fontconfig fallback (§7.3.2) |
| `settings/pages/AccessibilityPage.qml` | X6 | §8.1 |
| `settings/components/ArThemePreview.qml` | X6 | gallery miniature (§7.2.6) |
| `dotfiles/.local/bin/arctic-kbptr` | X6 | §8.3 |
| `shell/FirstLoginWelcome.qml` | X7 | §9.2 |
| `shell/FirstbootService.qml`, `shell/FirstbootStatus.js` | X7 | §9.3 |
| `dotfiles/.config/arctic/first-login` | X7 | the one-time marker (§9.1) |
| `shell/PrivacyPeek.qml` | X8 | privacy pills while the bar is hidden (§10.2) |
| `shell/scripts/sysmon.py` | X8 | §11.2 |
| `shell/SystemService.qml`, `shell/SystemPanel.qml`, `shell/SystemItem.qml` | X8 | §11.3 |
| `shell/scripts/weather.py` | X9 | §12.2 |
| `shell/Weather.js`, `shell/WeatherService.qml`, `shell/WeatherCard.qml`, `shell/WeatherItem.qml` | X9 | §12.3 |
| `dotfiles/.local/bin/arctic-remind` | X10 | §13.1 |
| `shell/Reminders.js`, `shell/RemindService.qml`, `shell/ReminderList.qml` | X10 | §13.2 |
| `dotfiles/.local/bin/arctic-hook` | X11 | §14.2 |
| `packaging/hooks/*-hooks.d/*.sample` | X11 | documentation samples (§14.2) |
| `docs/wiki/Accessibility.md`, `docs/wiki/Coming-from-Windows-or-macOS.md` | X13 | §21 |
| Tests and fixtures | each WP | §20 |

#### 17.2 Changed files (shell)

| File:lines | WP | Change |
|---|---|---|
| `shell/Launcher.qml:10-14` | X1, X2 | header comment |
| `:18`, `:24-26`, `:28-34`, `:44` | X1 | `menu` view, `menuRoute`, focus, size, `openView(name, arg, query)` (one combined edit with the Get apps section) |
| `:47-56` | X1 | "Commands and settings" special |
| `:57-61` | X2 | app actions as candidates (§5.9); the Get apps / web-app tile skip stays theirs |
| `:62-75` | X2 | `results` = `LauncherSearch.compose(…)` (§5.2); the Get apps section's `get-search` row becomes its `getSearch` input |
| `:83-106` | X1, X2, X10 | `activate` cases of §5.2 (`menu`, `command`, `toggle`, `setting`, `window`, `file`, `calc` with qalc, `remind`, `web`, `help`, `action`); frecency record |
| `:131-137` | X1 | `CommandMenu` instance next to Get apps |
| `:159`, `:182-188`, `:190-197` | X2 | glyph per mode (`folder` for files, `globe` for web), placeholder, result count ignores headers |
| `:175-181` | X2 | Delete on window rows; ↑/↓ skip headers; Shift + Enter per kind |
| `:201-268` | X1, X2 | `ListView` delegate = `LauncherRow` (section headers, compact rows); literal sizes → `Theme.fs`/`rowH` |
| `:281-302` | X2 | footer `?` "more" hint |
| `shell/LauncherSearch.js:1-6` | X2 | header comment |
| `:49-60` | X2 | `rank(candidates, query, usage)` with the frecency boost (§5.10) |
| `:62-69` | X2 | `mode()` with `/`, `~`, `?` (the shortcuts section adds `:`) and `dir` |
| new functions | X2 | `compose()`, `boost()`, `helpRows()` |
| `shell/shell.qml:7-15` | X1-X10 | header comment and IPC list |
| `:20-22` | — | unchanged here (the launcher hosts the menu) |
| `:28-37` | X1 | `toggleLauncher` / `toggleMenu` / `openMenu` |
| `:64-81` | X7, X8 | instances: `FirstLoginWelcome { id: firstLoginCard }`, `PrivacyPeek {}` |
| `:113-117` | X3 | `osd` target: `level`, `notice` |
| `:125-129` | X7 | `welcome` target: `firstLogin`, `again` |
| after `:143` | X1 | `menu` target |
| new `toggleBar()` | X8 | §10.2 |
| `shell/Osd.qml:7-139` | X3 | the two-kind model (§6.1); the other sections' wrappers call into it |
| `shell/Theme.qml:64-72` | X5 | `fontMono` tries `Session.settings.monoFont` first |
| after `:97` | X0 | `textScale`, `fs()`, `rowH()`, `topInset`, `highContrast` |
| `shell/Session.qml:33-35` | X0 | `barHidden` (flag file, read at start), getters for the new `shell.json` keys |
| `shell/Bar.qml:14-27` | X8 | `visible: !Session.barHidden` |
| `:99-103` | X8, X9 | `SystemItem` first in the right group; `WeatherItem` right of the clock |
| the bar section's `anchorFor` | X8 | cache the last x per item for the hidden bar |
| `shell/ScreenFrame.qml:23`, `:87-89` | X8 | `margins.top: Theme.topInset`; top `Reserve` while hidden |
| `shell/Popover.qml:40` | X8 | `margins.top: Theme.topInset` |
| `shell/LockScreen.qml:28-29`, `:82` | X11 | `arctic-hook lock` when `secure` turns true; `arctic-hook unlock` and `arctic-theme schedule tick` after unlock |
| `shell/UpdateStatus.js:16-35` | X11 | parse `installed_at` |
| `shell/UpdateService.qml:19-40` | X11 | post-update hook once per `installed_at` |
| `shell/scripts/wallpapers.py` | X4 | the active theme's `backgrounds/` as a first group |
| `shell/qmldir` | all | the new types and singletons (`CommandMenuService`, `WindowList`, `SystemService`, `WeatherService`, `RemindService`, `FirstbootService`) |
| `shell/assets/icons-extra.js` | X0 | the glyphs of §17.4 |
| every `shell/*.qml` with `font.pixelSize: N` (57) | X5b | `Theme.fs(N)`, except the bar's files (§7.3.3) |
| `shell/README.md` | X13 | the new surfaces, IPC targets, files |

#### 17.3 Changed files (outside `shell/`)

| File:lines | WP | Change |
|---|---|---|
| `dotfiles/.local/bin/arctic-theme:1-30` | X4 | docstring: `schedule`, `contrast`, `install`, `update`, `remove`, `--osd` |
| `:50-60` | X4 | `EXTRA_THEMES`; HC folder under `~/.local/state/arctic/themes-hc` |
| `:114-121`, `:140-159`, `:162-174` | X4 | extra themes; `pair` in `theme_info`; `all_themes` |
| `:331-352` | X4 | link HC variants when contrast is high (§8.2) |
| `:456-496` | X11 | skip `.sample` (same rule as `arctic-hook`) |
| `:591-597`, `:679-684` | X4 | pairs; `--osd` |
| `:600-621` | X4 | `apply` ticks the schedule; `current --json` adds `schedule`, `contrast` |
| `:624-637` | X4 | list: `pair`, `gallery`, `installed_from`, more swatches |
| `:645-690` | X4 | new verbs |
| `dotfiles/.local/bin/arctic-wallpaper:1-22`, `:76-130` | X11, X12 | `next`, `rotate`; `arctic-hook wallpaper "$img" &` after drawing a new choice |
| `dotfiles/.local/bin/arctic-welcome:10` | X7 | the installed-system branch (§9.1) |
| `dotfiles/.local/bin/arctic-osd:1-10`, `:51-53` | X3 | `notice`, `lock-keys`, usage |
| `dotfiles/.local/bin/arctic-settings:4-8`, `:29-34`, `:50-51`, `:64` | X2 | optional search key (§5.3) |
| `dotfiles/.local/bin/arctic-shell-ipc:6-8` | X1 | usage: `menu …`, `osd level\|notice`, `welcome firstLogin\|again`, `bar toggleHidden\|shown` |
| `dotfiles/.local/bin/arctic-update:282` | X11 | `installed_at=@now` |
| `dotfiles/.local/bin/arctic-session` (`shell)` branch) | X3 | `arctic-osd lock-keys --seed` |
| `dotfiles/.config/mango/arctic/binds.conf` | X1, X3, X6, X8, X10 | the rows of §3, in the shortcuts section's generated layout; `:79` gains `--osd` |
| `dotfiles/.config/mango/arctic/autostart.conf:10-16` | X11, X12 | `exec-once=arctic-wallpaper rotate apply`, `exec-once=arctic-hook login` (last) |
| `dotfiles/.config/mango/arctic/rules.conf:15` | X6, X8 | `indicators` in the namespace list; the `wl-kbptr` rule |
| `dotfiles/README.md` | X13 | new helpers, `first-login`, hooks folders |
| `design/themegen/cli.py:1-89` | X4 | `named`, `contrast`, `--contrast high` on `render` and `check` |
| `design/themegen/derive.py:52-57`, `:128-156` | X4 | `GUARANTEES_HC`, `high_contrast()` |
| `design/themegen/palette.py:139-185` | X4 | optional `pair`, `contrast` fields validated; built-ins pair each other |
| `design/themegen/render.py:66-96` | X4 | `theme.json` `"contrast"` |
| `design/guidelines/10-platforms.md` | X13 | gallery accent rule, HC mapping, OSD kinds, fonts |
| `settings/pages/AppearancePage.qml` | X6 | §8.4 (Theme rows, Fonts, Wallpaper rotation, Top bar and calendar; Text/Pointer groups removed) |
| `settings/pages/AppsPage.qml` | X6 | "Search" group (§8.4) |
| `settings/pages/qmldir`, `settings/components/qmldir` | X6 | `AccessibilityPage`, `ArThemePreview` |
| `settings/SearchIndex.js:6-33`, `:35-105` | X6 | the Accessibility page; moved and new entries |
| `settings/Theme.qml:81-91` | X5 | `monoFont`, `textScale`, `fs()`, `highContrast` |
| `settings/components/ArText.qml:14` | X5b | `Theme.fs(size)` |
| `settings/assets/SettingsIcons.js` | X6 | `accessibility` glyph |
| `settings/scripts/arctic_settings.py:1-50`, `:2126-2239`, `:2519-2567` | X6 | docstring, commands of §8.4, `TOOLS`, `COMMANDS`, `WRITERS` |
| `settings/README.md` | X13 | commands and files |
| `packaging/firstboot/arctic-firstboot:1-32`, `:278-333` | X7 | status file (§9.3) |
| `packaging/arctic-linux.spec` | X4, X5, X7, X13 | §19 |
| `tools/build-rpms.sh:189-205` | X5 | download Source1 |
| `iso/kiwi/config.kiwi:73-90` | X13 | explicit packages (§19) |
| `docs/BUILD-SPEC.md`, `docs/PLAN.md`, `docs/wiki/*` | X13 | §21 |

#### 17.4 New glyphs (D9)

Added to `shell/assets/icons-extra.js` (the bar section creates it; same rules as its §3.5: 24-unit
grid, 1.75 stroke set by `Icons.icon`, round caps and joins, 2 px corner radius on shapes,
`currentColor` only for small dots). The Node icon test covers them.

| Name | Drawing (24 grid) | Used by |
|---|---|---|
| `menu` | three lines y 7, 12, 17 from x 5 to 19 | menu special, `menu` query glyph |
| `window` | rect 3,5 18×14 r 2 with a line y 9 | window rows, Open windows |
| `toggle` | pill 3,8 18×8 r 4, dot r 2.2 at 16,12 | Toggles branch |
| `timer` | circle r 7.5 at 12,13.5; hand 12,13.5→12,9.5; knob line 10,3.5→14,3.5 | reminders |
| `activity` | polyline 3,12 7,12 10,5 14,19 17,12 21,12 | System panel, `activity` row |
| `thermometer` | stem rect 10,3 4×12 r 2, bulb circle r 3.2 at 12,17.5 | temperature row |
| `memory` | rect 3,7 18×10 r 2, four short ticks under it | memory row |
| `palette` | palette outline with three small dots (`currentColor`) | Theme rows, gallery |
| `sun-moon` | left half of `sun` rays, right half a crescent | Switch automatically |
| `contrast` | circle r 8.5 with a vertical diameter and three short hatch lines on the right half (no fill) | High contrast |
| `type` | "A" 6,19→12,5→18,19 with a crossbar 8.5,14→15.5,14 | Code font, Text size |
| `pointer` | cursor arrow 6,3 → 6,19 → 10.5,15 → 13.5,21 → 16,20 → 13,14 → 19,14 z | Keyboard pointer |
| `caps-lock` | up-arrow house 12,4 19,11 15,11 15,15 9,15 9,11 5,11 z, line 9,19→15,19 | Caps Lock OSD |
| `cloud` | cloud from two arcs over a base line y 17 | weather |
| `cloud-sun` | small sun top-left (circle r 2.5, four rays) behind `cloud` | weather |
| `cloud-rain` | `cloud` plus three slanted lines below | weather |
| `cloud-lightning` | `cloud` plus a bolt 12,15 10,19 13,19 11,23 | weather |
| `fog` | three lines y 9, 13, 17 of different lengths | weather |
| `accessibility` | head dot at 12,5 (`currentColor`), arms 5,9→19,9, body 12,9→12,14, legs 12,14→8,20 and 12,14→16,20 | Settings rail (also in `SettingsIcons.js`, byte-identical; the bar section's copy test covers it) |

`sun` (weather, OSD "Winter") and `leaf`/`gauge`/`bolt` (power-mode OSD) come from the bar section's
list. `design-data.js` isn't edited (it is generated, `shell/dev/export-design-assets.cjs:1-10`).

---

### 18. Data formats and commands (summary)

| File | Written by | Read by | Shape |
|---|---|---|---|
| `shell/menu/*.json`, `~/.config/arctic/menu.json` | sections (shipped), the person | `CommandMenuService`, `arctic-menu` | §4.2 |
| `$XDG_RUNTIME_DIR/arctic/menu/req-<pid>.json` + `reply-<pid>.fifo` | `arctic-menu` / the shell | the shell / `arctic-menu` | §4.9 |
| `~/.local/state/arctic/launcher.json` | launcher | launcher | §5.10 |
| `~/.config/arctic/shell.json` (new keys) | Settings `shell-set` | `Session.qml` | §2 |
| `~/.config/arctic/settings.json` `schedule`, `contrast` | `arctic-theme` | `arctic-theme`, Settings | §7.1.2, §8.2 |
| `~/.local/state/arctic/theme-schedule.json` | `arctic-theme schedule tick` | same | §7.1.2 |
| `~/.config/arctic/location.json` | `arctic-sun location set` | `arctic-sun`, weather, night light | §7.1.3 |
| `design/themes/<n>/colors.toml`, `~/.config/arctic/themes/<n>/colors.toml` | Arctic, a theme repository | `themegen named` | §7.2.2 |
| `~/.config/arctic/themes/<n>/source.json` | `arctic-theme install` | `update` | §7.2.5 |
| `~/.local/state/arctic/themes-hc/<n>/` | `arctic-theme` | everything that reads `current` | §8.2 |
| `~/.config/arctic/fonts.json` | `arctic-font` | `arctic-font` | §7.3.1 |
| `$XDG_RUNTIME_DIR/arctic/lock-keys` | `arctic-osd lock-keys` | same | §6.4 |
| `~/.config/arctic/first-login` | `/etc/skel` | `arctic-welcome` (deletes it) | §9.1 |
| `/var/lib/arctic/firstboot-status.json` | `arctic-firstboot` (root) | `FirstbootService` | §9.3 |
| `~/.local/state/arctic/bar-hidden` | the shell | the shell | §10.2 |
| `~/.cache/arctic/weather.json` | `weather.py` | `weather.py`, `WeatherService` | §12.2 |
| `~/.local/state/arctic/reminders.json` | `arctic-remind` | `arctic-remind`, `RemindService` | §13.1 |
| `~/.config/arctic/<event>-hooks.d/` | the person | `arctic-hook` | §14.1 |
| `/var/lib/arctic/update-status.json` `installed_at` | `arctic-update` | `UpdateService` | §14.3 |
| `~/.config/arctic/wallpaper-rotate.json` | `arctic-wallpaper rotate` | same | §15 |

New commands: `arctic-menu`, `arctic-sun`, `arctic-font`, `arctic-kbptr`, `arctic-remind`,
`arctic-hook` (all in `/usr/bin` through the spec's helper list, `:702`); new verbs on
`arctic-theme` (§7.1.4, §7.2.5, §8.2), `arctic-themegen` (§7.2.2, §8.2), `arctic-osd` (§6.2),
`arctic-wallpaper` (§15), `arctic-settings` (§5.3); shell scripts `sysmon.py`, `weather.py`.
New IPC: `menu *`, `osd level|notice`, `welcome firstLogin|again`, `bar toggleHidden|shown`, panel
id `system`.

---

### 19. Packaging deltas

`packaging/arctic-linux.spec`:

1. Header list (`:7-27`): add
   `#   arctic-themes-extra    design/themes/*/colors.toml, rendered here → /usr/share/arctic/themes-extra`
   and `#   arctic-fonts-symbols   Nerd Fonts "Symbols Only" (Source1) + packaging/fonts`.
2. `Source1: https://github.com/ryanoasis/nerd-fonts/releases/download/v%{nerd_version}/NerdFontsSymbolsOnly.tar.xz`
   with `%global nerd_version` and `%global nerd_sha256` 🔍 (the release at packaging time);
   `%prep`: `echo "%{nerd_sha256}  %{SOURCE1}" | sha256sum -c -` and unpack into
   `_build/nerd-symbols/`.
3. **`arctic-shell`** (`:240-253`): `Recommends: fd-find`, `Recommends: qalculate`. Its
   `%description` (`:254-257`) mentions the command menu, search modes, the welcome and the System
   panel.
4. **`arctic-desktop`** (`:402-482`): `Recommends: wl-kbptr`, `Recommends: arctic-themes-extra =
   %{version}-%{release}`, `Recommends: arctic-fonts-symbols = %{version}-%{release}`.
5. New subpackage after `arctic-fonts` (`:126-135`):
   ```
   %package -n arctic-fonts-symbols
   Summary:        Nerd Font symbols for the terminal (icons in yazi, eza and prompts)
   BuildArch:      noarch
   License:        <from the release's LICENSE> 🔍
   Requires:       fontpackages-filesystem
   ```
6. New subpackage after `arctic-desktop-config`:
   ```
   %package -n arctic-themes-extra
   Summary:        More colour themes for Arctic Linux (Nord, Catppuccin, Gruvbox, …)
   BuildArch:      noarch
   License:        MIT AND Apache-2.0 🔍 (the palettes' upstream licences)
   Requires:       arctic-desktop-config = %{version}-%{release}
   ```
7. `%build`: after Winter and Polar night are rendered, for each `design/themes/*/`:
   `arctic-themegen named --colors …/colors.toml --name <n> > _build/palettes/<n>.json` and
   `arctic-themegen render --palette _build/palettes/<n>.json --out _build/themes-extra/<n>`.
8. `%install`: `cp -a _build/themes-extra/. %{buildroot}%{_datadir}/arctic/themes-extra/`;
   the two TTFs into `%{_datadir}/fonts/arctic-symbols/`;
   `install -Dpm 0644 packaging/fonts/66-arctic-nerd-symbols.conf %{buildroot}%{_datadir}/fontconfig/conf.avail/66-arctic-nerd-symbols.conf`
   and a link to it in `%{_sysconfdir}/fonts/conf.d/`;
   hook samples into `%{_docdir}/arctic-desktop-config/hooks/`.
9. `%check`: `arctic-themegen check` and `check --contrast high` on every gallery palette and on
   Winter and Polar night.
10. `%files`: `-n arctic-fonts-symbols` (the fonts, the conf, the link);
    `-n arctic-themes-extra` (`%{_datadir}/arctic/themes-extra/`); arctic-desktop-config gets
    `%ghost %attr(0644,root,root) %verify(not md5 size mtime) %{_sharedstatedir}/arctic/firstboot-status.json`
    next to `update-status.json` (`:1122`) and `%doc` for the hook samples. The new helpers in
    `dotfiles/.local/bin` are picked up by the existing list (`:702`).
11. `%changelog`/Version 0.3.0: the release integration owns the bump (D1).

`tools/build-rpms.sh`: download Source1 next to the Mango tarball (`:189-205` pattern, with a
retry); the CI "Build RPMs" job already has the network.

`iso/kiwi/config.kiwi` (explicitly, after `:79`, as for things `arctic-desktop` only recommends):
`arctic-themes-extra`, `arctic-fonts-symbols`, `wl-kbptr`, `fd-find`, `qalculate`.
🔍 ISO size against the 2 GiB budget (`tools/build-iso.sh`, compare with 0.2.1); `qalculate`
pulls `libqalculate` and is the first to drop (the launcher then says "Unit conversion needs
qalculate").

No new BuildRequires (Python 3 and Pillow are there, `:52-58`). No new Go code.

---

### 20. Tests

All of these run in the existing CI jobs: `shell-tests` discovers `shell/tests/test_*.py`,
`design/themegen/tests`, `packaging/firstboot`, `settings/tests` and every `shell/tests/*.cjs`
(`.github/workflows/ci.yml:65-98`); `shellcheck` covers the bash helpers; `qml` lints every new
QML file (`:128-149`); `settings-headless` opens every Settings page (`:151-169`), so the
Accessibility page is smoke-tested automatically.

#### 20.1 Node (`shell/tests`)

| File | Checks |
|---|---|
| `test-command-menu.cjs` (new) | `merge`: a later file replaces only the fields it gives and keeps the first position; new ids append; `hidden: true` removes. `tree`: dotted ids, `target` links, orphans reported. `resolve`: `''` = root, case and `_` normalised, leaf route = run, link = target, unknown = root + notice. Guards: batch plan de-duplicates `command`/`file`; `parseGuardOutput`; `disabled` rows skipped by the cursor and search; `when` hides a branch whose children are all hidden. Providers: re-running swaps only that branch's rows; id collisions get `-2`. Search: breadcrumbs, subtree-only inside a branch. `validate`: unknown glyph, verb outside the allowlist, `run[0]` outside `RUN_ALLOW`, `sh` in a shipped file, bad id — each refused. **Every `shell/menu/*.json` in the repository** validates (glyph names read from `design-data.js` and `icons-extra.js`) |
| `test-launcher.cjs` (extend; shared with the shortcuts section) | `mode('/notes')`, `mode('~/Documents/rep')` (`dir`), `mode('?rain')`, `mode('?')` (help); `compose` order and caps; headers only with two or more sections; `get-search` before `web`; `web` only at ≥ 2 characters; frecency `boost` capped at 150 and never lifting a fuzzy match over an exact name; app actions only at ≥ 3 characters and never above their app |
| `test-units.cjs` (new) | `looksLikeConversion` yes: "10 km to mi", "100 usd in eur", "0xff to dec", "72 f to c", "3 cups in ml"; no: "to do list", "set up in 5", "2 + 2", "remind 10m tea"; `looksLikeMath` yes: "2+2", "12 * 4", "(3+4)/2"; no: "2", "route 66" |
| `test-settings-index.cjs` (new) | running the exporter in memory gives exactly `shell/assets/settings-index.js` (stale file fails, with the command to fix it) |
| `test-osd.cjs` (new) | notice duration grows with length and is capped at 3 s; notice width 200-420; unknown icon → `info`; level width 280 |
| `test-weather.cjs` (new) | every WMO code 0-99 that Open-Meteo documents maps to a glyph and words; night variant for code 0-2; `tempText` rounding and unit sign |
| `test-reminders.cjs` (new) | "remind 10m tea" → 600 s "tea"; "remind me in 2 hours to stretch" → 7200 s "stretch"; "remind 15:30 call Dana" → an absolute time today or tomorrow (fake clock); "timer 5m" → "Timer"; "remind" alone → null; text over 200 characters refused |
| `test-firstboot-status.cjs` (new) | `parse` of each state; name lists ("Zed", "Zed and Steam", "Zed, Steam and Spotify", "Zed, Steam, Spotify and 3 more"); one notification per `started_at`; `restart_needed` text |
| `test-text-scale.cjs` (new) | no `font.pixelSize: <number>` literal in `shell/*.qml` outside `Bar.qml`, `BarItem.qml`, `Workspaces.qml`, `UpdateIndicator.qml` (after X5b; before it the test lists the files still to convert and only fails on new ones) |
| the bar section's `test-icons.cjs` | the §17.4 glyphs exist, don't shadow design names, and `accessibility` is identical in `SettingsIcons.js` |

#### 20.2 Python

| File | Checks |
|---|---|
| `shell/tests/test_arctic_menu.py` (new) | `select`: request JSON written 0600 in a 0700 folder, fake `arctic-shell-ipc` writes the reply into the FIFO → stdout value, exit 0; cancel → exit 1; `busy` → exit 3; timeout; options with control characters refused; fallback to a fake `fuzzel` when the IPC fails; `list --json --fallback` drops `shell` rows |
| `shell/tests/test_arctic_remind.py` (new) | duration parsing; `add` writes the state and calls a fake `systemd-run` with the exact argv (unit name, `--on-calendar`, `AccuracySec=1s`, `-- arctic-remind fire ID`); `cancel` stops the unit; `fire` calls a fake `notify-send` with `x-arctic-alert` and removes the entry; "In 5 minutes" re-adds; `restore` re-arms future ones and reports missed ones once; concurrent `add` under the lock |
| `shell/tests/test_arctic_hook.py` (new) | the contract table of §14.1, run against both `arctic-hook` and `arctic-theme`'s `run_hooks` where it applies: order, user replaces system, non-executable disables, skipped suffixes including `.sample`, 5 s limit kills the process group (a hook that forks `sleep 60`), output capped at 4 KB, env vars and `$1`, unknown event → exit 2, `theme` refused |
| `shell/tests/test_arctic_sun.py` (new) | `zone1970.tab` coordinates in both precisions; a link name through `tzdata.zi` (fixture files); sunrise/sunset within ±2 min for Asia/Jerusalem 2026-03-20, Europe/London 2026-06-21 and 2026-12-21, America/New_York 2026-09-28; polar day and night for Arctic/Longyearbyen; `UTC` → `no_location`; `location set place` validation (lat −90…90, lon −180…180, name ≤ 80) |
| `shell/tests/test_arctic_font.py` (new) | `fc-list` parsing (fake), symbols and emoji families left out; `set` edits the three configs only where the line matches `fonts.json`, reports `skipped` otherwise; gsettings and `shell.json` calls; `size` rounding to 0.5 pt; `kitty` reload signal sent through a fake `pkill` |
| `shell/tests/test_sysmon.py` (new) | fixture `/proc` and `/sys` trees under `--root`: CPU percent from two `/proc/stat` samples; `used = MemTotal − MemAvailable`; hwmon choice order (`k10temp` Tctl, `coretemp` Package id 0, `x86_pkg_temp`, `acpitz`, none); amdgpu busy percent; disks de-duplicated by device; network rate without `lo`; top processes by CPU; `kill` refuses another uid |
| `shell/tests/test_weather.py` (new) | URL built with rounded coordinates, units and `timezone=auto`; `auto` units by locale; fresh cache returned without a request (a fake `urlopen` that fails if called); offline → `code: offline` with the cache; geocode parsing; attribution field present |
| `shell/tests/test_helpers.py` (extend) | `wallpapers.py list` shows the active theme's `backgrounds/` first; `arctic-wallpaper next` doesn't change `~/.config/arctic/wallpaper` (§15) |
| `design/themegen/tests/test_named.py` (new) | every `design/themes/*/colors.toml` → a palette with all `ROLES` that passes `check`; the `here` accent is warm (OKLCH hue 40-110°) in every gallery palette; pairs are symmetric and of opposite modes; an Omarchy `colors.toml` (the Nord file quoted in §7.2.2) converts; bad values and unknown modes refused |
| `design/themegen/tests/test_contrast.py` (new) | `high_contrast()` of Winter, Polar night, every gallery palette and a wallpaper-derived palette meets `GUARANTEES_HC`; `frost` opaque; idempotent; hues kept (ΔH ≤ 2° for chromatic roles); `render --contrast high` writes `"contrast": "high"` |
| `design/themegen/tests/test_arctic_theme.py` (extend) | `light`/`dark`/`toggle` use pairs; `schedule` verbs save settings and call a fake `systemd-run`; `schedule tick` applies only when the period changed (a manual switch after the boundary survives the next tick); `apply` ticks; `contrast on` renders into `themes-hc/<name>` and links `current` there, hooks see that folder; `install` from a local tarball fixture keeps only allowlisted files, drops `kitty.conf`, `neovim.lua`, symlinks and `../` members, refuses oversized pictures and name clashes; `remove` of the active theme switches to the mode's built-in; `list --json` keeps every existing field |
| `packaging/firstboot/test_arctic_firstboot.py` (extend) | status file written at start, after each module and at the end; states `installing`, `waiting`, `done`, `failed`; `restart_needed` after `enroll_key` queues a key; mode 0644; atomic rename |
| `settings/tests/test_arctic_settings.py` (extend) | `accessibility`; `contrast-set`; `text-size` sets gsettings, `shell.json` (clamped) and calls `arctic-font size`; `fonts`/`font-set` pass-through; `theme-schedule(-set)` validation of `HH:MM`; `theme-install` refuses non-https; `location-set` validation; `shell-set` accepts the new keys with their types and refuses others; `wallpaper-rotate` values |
| `settings/tests/test_app_files.py` (extend) | page list check without a fixed count (§8.1); the Accessibility page's search keys exist; moved keys point at the new page; `dotfiles/.config/arctic/first-login` exists; `iso/kiwi/config.kiwi` lists `google-noto-color-emoji-fonts` and not `google-noto-emoji-fonts` |
| the shortcuts section's bind tests | rows 56-58 (§3) described, unique, and free of layout-switch chords |

#### 20.3 Lint

- `shellcheck -x` on `arctic-kbptr`, and on the edited `arctic-welcome`, `arctic-osd`,
  `arctic-settings`, `arctic-wallpaper`, `arctic-update`, `arctic-session`.
- `python3 -m py_compile` on the Python helpers (the spec's `%py_byte_compile` step already fails on
  syntax errors for `/usr/share/arctic`; the helpers in `/usr/bin` get a `%check` line).

#### 20.4 Headless shell steps (`shell/dev/headless.sh`, and the bar section's `shell-headless` CI job)

`--fixtures` also creates `~/Documents/notes-arctic.txt` and a two-window session (two `foot`
windows 🔍 whether the headless sway has foot; else `kitty`), then:

| Step | Proves |
|---|---|
| `ipc menu open ''` → shot `menu-root` | the menu renders, root rows present |
| `ipc menu open capture` → shot `menu-capture` | routes; the shortcuts section's rows are merged |
| `ipc launcher search wifi` → shot `launcher-mixed` | sections, Settings rows, Commands rows |
| `ipc launcher search /notes` → shot `launcher-files` | `fd` rows |
| `ipc launcher search "=10 km to mi"` → shot `launcher-units` | `qalc` fallback (when installed) |
| `ipc osd notice caps-lock "Caps Lock on" ""` → shot `osd-notice` | three-argument IPC (🔍 §6.2) and the notice kind |
| `ipc welcome firstLogin` → shot `welcome` | the card |
| `ipc bar toggleHidden` + `ipc panel open calendar` → shot `bar-hidden` | frame reserve, popover inset, anchor fallback |
| `ipc panel open system` → shot `system` | `sysmon.py` against the real `/proc` |
| `sh arctic-theme contrast on` → shot `hc` | the HC variant restyles the shell |
| `sh arctic-theme set catppuccin-latte` → shot `gallery` | a gallery theme renders |

Screenshots feed the tour (`tools/screenshot-tour.sh`) and the wiki.

#### 20.5 Hands-on (Fedora 44 under Mango, before the pull request; D10)

1. Caps Lock and Num Lock OSD on a laptop keyboard and a USB keyboard; Caps with `caps:escape`
   and with `grp:caps_toggle` (no OSD, layout still switches) (§6.4).
2. `Super + Alt + Space` with `grp:alt_space_toggle` (the known clash; Settings' warning shows).
3. A suspend across a schedule boundary (§7.1.2).
4. yazi and `eza --icons` in kitty, foot and alacritty (§7.3.2).
5. High contrast in gnome-text-editor (libadwaita), Thunar (GTK 3), VLC (Qt 5) and the shell.
6. `wl-kbptr` on Mango: hints, bisect, click, Esc; layer rule namespace (§8.3).
7. First login after a real install with an app deferred (unplug the network during installation):
   the welcome card, "Finishing setup" and "All set" notifications (§9).
8. The bar hidden: every `Super + Ctrl + …` panel opens at a sensible place; a video call shows
   the privacy pill (§10).
9. System panel temperatures on one Intel and one AMD machine (§11.2).
10. The launcher at 125 % text on a 1366×768 screen (§7.3.3).

---

### 21. Docs to update

Contract first (BUILD-SPEC is the contract between components; the wiki is for people).

| Doc | Change |
|---|---|
| `docs/BUILD-SPEC.md` §3 (Desktop session, `:92-105`) | the new helpers (`arctic-menu`, `arctic-sun`, `arctic-font`, `arctic-kbptr`, `arctic-remind`, `arctic-hook`) with one line each; the first-login marker; `firstboot-status.json` |
| `docs/BUILD-SPEC.md` §3.2 (Settings, `:180-275`) | the Accessibility page, the moved rows, the new commands and `shell-set` keys |
| `docs/BUILD-SPEC.md` §10 (Theming, `:654-831`) | 9.1: `themes-extra`, `themes-hc`, `location.json`; 9.2: optional `pair` and `contrast`; new 9.2a: the `colors.toml` format and its mapping; 9.4: the HC guarantees; 9.5: `named`, `contrast`, `--contrast high`; 9.6: `schedule`, `contrast`, `install/update/remove`, `--osd`, new `list`/`current` fields; 9.7: the generalised hook contract and its events |
| `docs/BUILD-SPEC.md`, new subsection under §3 | "Command menu data" (the JSON format, merge rules, verbs, guards, providers, IPC and the select/input handshake) |
| `docs/PLAN.md` | 0.3.0 scope lines for this section's items, the deferrals (§16, §7.2.7) |
| `docs/wiki/Desktop-Tour.md` (`:76-107` launcher, `:10-43` bar) | the command menu; search modes and prefixes; weather in the calendar; hiding the bar; the System panel; reminders |
| `docs/wiki/Keyboard-Shortcuts.md` | the rows of §3; "In the launcher" (`:100-110`) gains the prefixes; a new "In the command menu" block. (If the shortcuts section generates this page from the binds, only the in-surface tables are written here.) |
| `docs/wiki/Themes-and-Customisation.md` | "Light and dark on a schedule"; "More themes" (gallery, pairs, installing from a URL, what is kept); "Code font and icons"; "Hooks" (`:269-295` becomes the general contract with the event table and samples); "Your own menu entries" (`~/.config/arctic/menu.json` with an example); wallpaper rotation |
| `docs/wiki/Settings.md` | the Accessibility page (new section), Appearance's new groups, Default apps' Search group |
| `docs/wiki/First-Boot.md` (`:51-107`) | the welcome card; "Finishing setup" notifications replace "Apps that finish installing after first boot" wording |
| `docs/wiki/Accessibility.md` (new) | what exists (high contrast, text size, motion, pointer, keyboard pointer) and what doesn't yet, with reasons (§24) |
| `docs/wiki/Coming-from-Windows-or-macOS.md` (new; the Learn menu links it) | habit map: Spotlight/Start → `Super + Space`; Control Center / Action Center → `Super + A`; Task Manager → `Ctrl + Shift + Esc` / System panel; Snipping Tool → `Super + Shift + S`; App Store → Get apps; System Settings → `Super + S`; dark mode schedule; Alt + Tab |
| `docs/wiki/FAQ.md` | "Does the launcher send what I type anywhere?" (no; web search only on Enter); "Where does the weather come from?"; "Why no screen reader?" |
| `docs/wiki/Release-Notes.md` | 0.3.0 entries |
| `docs/wiki/_Sidebar.md` | the two new pages |
| `shell/README.md`, `settings/README.md`, `dotfiles/README.md` | files, IPC targets, commands |
| `design/guidelines/10-platforms.md` | the gallery accent rule ("here" stays warm), the HC mapping, the OSD notice kind, the code font |

---

### 22. Work packages and order

| WP | Name | Depends on | Size |
|---|---|---|---|
| X0 | Foundations: `Theme.fs/rowH/topInset/highContrast`, `Session` keys, glyphs, `arctic-sun` | bar section's `icons-extra.js` (A) | S |
| X1 | Command menu | X0; soft: bar section's `ToggleRegistry` (J), Get apps section's rows, shortcuts section's capture rows | M |
| X2 | Launcher search modes | X1 (menu rows in search), X0 | M |
| X3 | OSD kinds and Caps Lock | X0; bar section's registry (J) for toggle notices | S |
| X4 | Theme engine: schedule, gallery, pairs, high contrast, install | X0 (`arctic-sun`) | L |
| X5 | Code font, Nerd symbols package, one text size | X0 | M |
| X5b | The `Theme.fs` sweep of existing shell files | every other section merged | S |
| X6 | Settings: Accessibility page, Appearance and Default apps changes, keyboard pointer | X4, X5, X9 (weather rows), X12 (rotation row) | M |
| X7 | First-login welcome and first-boot progress | X0; shortcuts section's keys sheet (soft), bar section's network panel (soft), Get apps section (soft) | M |
| X8 | Bar hide and System monitor | X0, X3; bar section A (BarMenu), J (registry, indicators) | M |
| X9 | Weather | X0 (`arctic-sun`); bar section's calendar (G) | S |
| X10 | Reminders | X1, X3; bar section J and F (centre) | S |
| X11 | User hooks | X0; bar section H (battery) for `battery-low` | S |
| X12 | Wallpaper rotation (P3) | X11 | S |
| X13 | Docs, packaging, kiwi, tour | all | S |

Order: X0 → (X1, X4, X5, X11 in parallel) → X2, X3, X9 → X6, X7, X8, X10 → X12 → X13 → X5b last.
Each package lands with its tests and green CI; the merge to main is one pull request (D10).

Each package's edits to existing files are the rows of §17.2 and §17.3 tagged with its id; the
edits that land in other sections' new files are listed in §23.

---

### 23. Interfaces with other sections

| Section | What this section needs | What it gives |
|---|---|---|
| **Get apps / Remove apps (s1)** | `shell.openGetApps(screen, page, query)` and IPC `apps open`; `apps.py counts` (cached) for `count` guards; its `get-search` row as `compose()` input; its trash button moves into `LauncherRow.qml`; the combined `openView(name, arg, query)` edit | the `menu` view next to `get`; `shell/menu/30-apps.json` is theirs to write; the launcher's `Delete` rule for window rows mirrors theirs |
| **Web-app engine (s2)** | its Default apps rows (`AppsPage.qml`); web apps appear as ordinary apps in search | the "Search" group goes after its rows; nothing else |
| **Bar menus, Quick Settings, notifications (s3)** | `icons-extra.js` (A); `ToggleRegistry.set(key, mode, source)` with a `source` argument and a per-toggle `osd` flag (J); a new toggle kind `status` (J); `openPanel()` falling back to cached anchors while the bar is hidden (A); `Bar.anchorFor()` caching (A); a `system` panel id in `BarMenu` and the `panel` IPC list (A); a Quick Settings "System" row (J); `ModeIndicators.urgentOnly` (J); `CalendarPanel` weather slot (G); `NotificationCenter` reminders slot (F); `BatteryService` fires `arctic-hook battery-low` (H); toasts use `Theme.topInset` (F); `MenuRow`/`QuickTile` read `Theme.highContrast` and use `Theme.fs` (A); `shell-set` allowlist keys (their §9.4) | `Osd.showLevel`/`showNotice` for `showPower`, `showLayout`, `brightnessLevel`; `WindowList`; `Theme.fs`, `topInset`, `highContrast`; the glyphs of §17.4; resolves their `shell.json` spelling question for these keys (camelCase) |
| **Shortcuts and capture (s4)** | its key table gains rows 56-58 and `:79 … --osd`; rows 46, 47, 51, 54 as assigned; `shell/menu/20-capture.json` rows; the generated keys sheet for the welcome's link; `google-noto-color-emoji-fonts` in kiwi and arctic-shell (its §11); the `:` emoji prefix in `LauncherSearch.mode`; "Keys deliberately not used" gains `Super + Ctrl + X` (kept free for dictation, §16) | the menu engine its §10 waits for; the `notice` OSD kind its §17 waits for (`showTouchpad`); capture rows searchable from the launcher (§5.5) |
| **System (s5a)** | `shell/menu/40-system.json` (update, restart subsystems, share, display mode, hibernate, firmware setup); night light reads `arctic-sun location --json` instead of its own coordinates; `arctic-power`'s install warning covers the menu's power rows; "What's new" can read `installed_at` (§14.3); game mode's "reduced effects on VMs" is theirs; Activity (`Ctrl + Shift + Esc`) for the System panel footer | `arctic-sun`, `location.json`; the Settings "Place" row (Appearance) shared with night light's "Sunset to sunrise"; `arctic-hook` for any system event they want to expose later |
| **Release (D1, D10)** | Version 0.3.0; one pull request | two new subpackages (§19) |

Rules every section follows from this section: new QML uses `Theme.fs()` for font sizes and
`Theme.topInset` instead of `Theme.barHeight` for top margins; new Settings rows re-run
`shell/dev/export-settings-index.cjs`; new menu rows go in the section's own `shell/menu/NN-*.json`.

---

### 24. Skipped and deferred, with reasons

From the gap list's skip list (all kept; reasons shortened):

| Feature | Why not |
|---|---|
| Universal `Super + C/V/X` copy and paste (Omarchy) | needs Hyprland's send-shortcut; faking keys with wtype while Super is held is unproven on Mango; `Super + V` is clipboard history |
| Screen magnifier / zoom | Mango 0.17.3 has no magnifier (its `zoom` is a master swap); a Quickshell loupe over screencopy is heavy. The Accessibility page says so |
| Screen reader (Orca) | wlroots compositors lack the key grabs Orca relies on (secondary source; unverified for Mango). `orca` is in F44 for a later try. The Accessibility page says so |
| On-screen keyboard | wvkbd and squeekboard aren't in F44 |
| Hibernation setup | Fedora uses zram; Secure Boot lockdown blocks unencrypted hibernation |
| Power profile per AC/battery | tuned-ppd already maps balanced to balanced-battery |
| Omarchy shell plugins from git | a code-execution surface; menu extensions and hooks cover most needs |
| Bar repositioning, reordering, transparency, tray drawer, resource graphs, desktop widgets | the design fixes a calm 34 px top bar; the bar can now be hidden (§10) and the System panel shows numbers (§11) |
| Dock or taskbar | conflicts with the calm, keyboard-first layout. The verification disagreed (missed gap); the answer here is the launcher's window search (§5.4), the menu's Open windows list (§4.6) and the shortcuts section's Alt + Tab |
| Quickshell overview with live previews | Quickshell captures single windows only on Hyprland; Mango's overview stays |
| Omarchy's 22 themes as defaults | Arctic's identity is Winter, Polar night and amber "here"; the gallery (§7.2) is opt-in with warm "here" accents |
| Video wallpapers, ASCII screensaver | mpvpaper isn't in F44; battery; not calm |
| AI features (agent panel, coding agent, crash diagnosis, chat) and Voxtype dictation | out of scope, privacy; dictation deferred with a plan (§16) |
| Omarchy's commercial installers, install-on-first-use keys, 37signals web apps | Get apps and the installer catalog cover choosing apps; web apps are user-made (request #2) |
| mise installers, Docker databases, Windows VM through Docker | not in F44 / Arctic uses Nix, podman, Boxes and virt-manager |
| Time-boxed passwordless sudo, sudoless Docker | unsafe defaults |
| Limine snapshots, direct EFI boot, factory reset | Limine-specific; snapshots-ui covers restore |
| Arch-specific update pieces | Arctic's snapper actions and channels cover them |
| Transcode menu, yt-dlp and copy-URL extensions | niche; need native messaging and full ffmpeg |
| Webcam overlay, speaker tuning, hardware quirk detectors | device-specific |
| Unattended installs through cidata, deferred owner provisioning | installer scope |
| World clock, Tailscale/Dropbox panels, cellular, USBGuard, remote desktop, auto-rotate, ambient light, HDR, screen time, music recognition, lyrics, translator | niche for Arctic's audience; HDR needs Mango's non-scenefx branch |
| Scrolling screenshots, clipboard persistence after close | complex; wl-clip-persist isn't in F44 |
| Per-workspace layout toggle, three-tier resizing | Hyprland-specific; Mango's own binds cover them |

Added by this section:

| Feature | Why not (yet) |
|---|---|
| Dictation | §16 |
| Packaging the `v2-walls/` pictures | no licence or source records (§7.2.7) |
| Colour-blindness and greyscale filters | wlroots' gamma control is a per-channel curve and can't mix channels; Mango has no colour matrix |
| Sticky and slow keys | Mango has no AccessX handling 🔍 (whether xkbcommon's AccessX is usable in wlroots keyboards); revisit with upstream |
| Text-size and scale hotkeys (Omarchy `Super + /`) | P3; `Super + /` is the keys sheet; the text size is one Settings row away |
| Omarchy's time/battery/weather notice keys | the panels open by key even with the bar hidden (§10.2), which covers them without three more keys |
| Search suggestions from the web engine | would send every keystroke; the web row sends only on Enter |
| IP geolocation for weather and the schedule | privacy; the time zone or a chosen place is enough |
| Launcher provider plugins (Noctalia's `/` providers) | a plugin surface; the user menu file covers custom commands |
| A Weather or Reminders page in Settings | the Top bar group and the Reminders menu cover them |

---

### 25. Open issues and unverified points

**Open decisions** (each with a recommended answer)

1. **Menu inside the launcher card vs its own popover.** Recommended: inside (one surface, one
   look, no new layer). If the Get apps section's launcher changes make `Launcher.qml` too large,
   `CommandMenu.qml` is already a separate component and can move to its own `Popover` without
   changing its API.
2. **Gallery theme licences.** Confirm each upstream licence and record it in `SOURCE` before
   copying values; drop a palette whose licence is unclear (Tokyo Night's is the one to check).
3. **`shell.json` spelling.** This section uses camelCase keys (like `frame`). The bar section left
   the question open for `battery_warnings`; one rule for all keys should be written into
   BUILD-SPEC §3 in review.
4. **Default web search engine.** DuckDuckGo (no account, privacy-minded). The person's browser
   default can't be reached through a URL.
5. **Theme backgrounds switching the wallpaper.** Recommended: never automatically; the picker
   shows them (§7.2.5). Revisit if people expect Omarchy's behaviour.
6. **Currency rates in `qalc`.** Keep qalc's own update behaviour (network only when a currency is
   converted) or disable it and offer an explicit "update rates" row. Recommended: keep, document.
7. **`arctic-fonts-symbols` in the ISO.** Recommended yes (a few MB, and yazi is a default app).
8. **Text scale cap.** 1.25 for the shell and Settings; raise it only after the §20.5 #10 check at
   larger sizes.

**Unverified (🔍), and what proves each**

| # | Claim | Proof |
|---|---|---|
| 1 | `bindrp=NONE,Caps_Lock,…` / `Num_Lock` fire on release, pass the release on, and the LED is already updated | hands-on #1 (§20.5) |
| 2 | `IpcHandler` functions with three typed arguments work in the `dacfa9d` snapshot | headless `ipc osd notice …` (§20.4) |
| 3 | fuzzel prints typed text in `--dmenu --lines 0` when nothing matches | `echo | fuzzel --dmenu --lines 0` on F44 |
| 4 | A transient `OnCalendar` user timer that elapsed during suspend fires on resume | hands-on #3 |
| 5 | `/usr/share/zoneinfo/tzdata.zi` ships in F44 tzdata | `rpm -ql tzdata` |
| 6 | libadwaita apps react to `org.gnome.desktop.a11y.interface high-contrast` under Mango | hands-on #5 |
| 7 | wl-kbptr 0.4.1 options (`-c`, `-o modes=tile,bisect`), config keys, layer namespace | `man wl-kbptr`, `config.example`, `mmsg get all-layers` |
| 8 | Nerd Fonts "Symbols Only" latest release, file names, SHA-256 and licence set | the release page and its `LICENSE` |
| 9 | Fedora's kitty keeps or drops kitty's built-in Nerd symbols; foot and alacritty use the fontconfig fallback | hands-on #4 |
| 10 | `qalc` updates exchange rates by itself, and its default interval | `qalc -t "1 usd to eur"` with an empty qalculate folder |
| 11 | `Quickshell.iconPath` resolves MIME icon names for file rows | headless launcher-files shot |
| 12 | `nm-online -q -t 0` exits non-zero when offline | run offline and online |
| 13 | Codeberg and GitLab archive URL forms for `arctic-theme install` | fetch a known repository of each |
| 14 | Open-Meteo terms for an OS feature (non-commercial, attribution) | open-meteo.com terms page |
| 15 | hwmon labels and `gpu_busy_percent` paths on F44 kernels | hands-on #9 |
| 16 | The headless sway in CI can run `foot` or `kitty` for the window fixtures | CI log of the first run |
| 17 | Every surface is readable at 125 % text | hands-on #10 and the 125 % headless shots |
| 18 | `learn.mango` has a better docs URL than the repository | upstream README |
| 19 | CPU transcription speed for the dictation follow-up | measure `whisper-cli` base.en on a mid laptop (not needed for 0.3.0) |
| 20 | Sticky/slow keys possible through xkbcommon on wlroots | upstream wlroots/Mango issue search (not needed for 0.3.0) |
| 21 | ISO size with the new Recommends (qalculate first to drop) | `tools/build-iso.sh`, compare with 0.2.1 |
| 22 | Upstream licences of the 11 gallery palettes (Tokyo Night's in particular) | each repository's `LICENSE`, recorded in `design/themes/<name>/SOURCE` |
