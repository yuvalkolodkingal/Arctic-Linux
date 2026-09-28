# Arctic Linux 0.3 — Shortcuts, screenshots and capture tools

Part of the [0.3 plan](../PLAN-0.3.md).

This section covers user request #5 ("add a screenshot shortcut and change the browser shortcut to
win b") and the keyboard, capture and input parts of request #6. It implements decision D7 in
full, the capture and input items of D8, and D9 for every surface it adds. It ships in Arctic
Linux 0.3.0 (D1).

Gap items implemented here (priorities from `gap-list.json`, corrections from
`gap-verification.json` applied):

| Gap item | Priority | Where |
|---|---|---|
| `alt-tab-switcher` (with the Alt+Shift+Tab correction) | P0 | §18 |
| `emoji-picker` (with the colour-font correction) | P0 | §11 |
| `screen-share-picker` | P0 | §9 |
| `hardware-keys` (with the touchpad-state and logind corrections) | P0 | §17 |
| `screenshot-editor-overlay` | P1 | §5 |
| `color-picker` | P1 | §7 |
| `ocr-qr-capture` | P1 | §6 |
| `screen-recording` (with the Flatpak and free-codec corrections) | P1 | §8 |
| `clipboard-panel` | P1 | §12 |
| `generated-keys-sheet` | P1 | §13 |
| `dropdown-terminal` (with the `single_scratchpad` note) | P1 | §19 |
| `window-extras` (group bar settled) | P2 | §20 |
| `launch-or-focus` (focusid settled) | P2 | §21 |
| Missed gap: new default binds silently override users' own binds | P1 | §14 |
| Missed gap: layout-switch key vs Alt+Shift shortcuts | P1 | §15 |
| Missed gap: `togglejump` / `focuslast` unbound | P2 | §18 |
| Missed gap: compose key | P2 | §16 |

The command menu's Capture branch (`command-menu`, P1) is owned by the section that builds the
menu. §10 defines its rows. §3 is the one authoritative table of every new or changed key in
0.3.0, for every section.

Facts marked ✅ were checked on 2026-09-28 in the repository, in the Mango 0.17.3 docs
(`raw.githubusercontent.com/mangowm/mango/0.17.3/docs/…`) or in Fedora 44 metadata
(`mdapi.fedoraproject.org/f44/pkg/<name>`). Facts marked 🔍 are unverified; each names the check
that proves it.

---

### 1. Current state (0.2.1)

#### 1.1 Where binds live

- Mango reads only `~/.config/mango/config.conf`. It sources, in order (`dotfiles/.config/mango/config.conf:22-32`):
  `arctic/look.conf`, the theme's `mango-colors.conf`, `arctic/input.conf`,
  `/etc/arctic/mango/keyboard.conf`, **`arctic/apps.conf` (:26)**, **`arctic/binds.conf` (:27)**,
  `arctic/rules.conf`, `arctic/autostart.conf`, `motion.conf`, **`settings.conf` (:31)** and
  **`user.conf` (:32)**.
- Mango stops at the first bind that matches a key, unless that bind has the `c` flag ✅
  (keys.md "Flags"). Arctic's files come before `settings.conf` and `user.conf`, so a user bind on
  a key Arctic uses never runs. `config.conf:13-17` says so.
- `bind` turns the key name into a keycode. It resolves the name against the configured
  layouts, in order, and falls back to the `us` layout when none of them has the key.
  `code:N` binds a keycode directly ✅ (keys.md:15-17).
- Packaging: every `dotfiles/.config/mango/arctic/*.conf` is installed to
  `/usr/share/arctic/mango/` and `/etc/skel` links to it (`packaging/arctic-linux.spec:626-631`).
  The file list is a glob (`:705`), so new or edited `.conf` files need no spec change. People who
  replaced a link with a copy keep their copy.
- The Go installer writes no binds. It writes only `/etc/arctic/mango/keyboard.conf`
  (`internal/installer/installer.go:825`). `internal/`, `cmd/` and `modules/` need no change in
  this section.

#### 1.2 The browser key

- `dotfiles/.config/mango/arctic/apps.conf:7` `bind=SUPER,w,spawn,arctic-open browser`.
- `Super + B` is bound nowhere. The design reserved it for bar keyboard focus, which was never
  built (`dotfiles/README.md:139-140`, `docs/wiki/Release-Notes.md:340`).
- `docs/wiki/Themes-and-Customisation.md:218-219` teaches users to add
  `bind=SUPER,b,spawn,firefox` to `user.conf`. After the change that line silently does nothing.
- The only hard-coded "Super + W" in code is `ROLES[0].keys`
  (`settings/scripts/arctic_settings.py:1793`), shown by `settings/pages/AppsPage.qml:27`. It is
  also in a comment at `AppsPage.qml:3`, at `keys.txt:6` and in eight wiki pages (§26).

#### 1.3 Screenshots

- `binds.conf:81-84`: `Print` → `arctic-screenshot area`, `Shift + Print` → `screen`,
  `Super + Print` → `window`.
- `dotfiles/.local/bin/arctic-screenshot` (40 lines of bash):
  - It saves to `$(xdg-user-dir PICTURES)/Screenshots/Screenshot %Y-%m-%d %H.%M.%S.png` (:6-8).
  - `area` runs `slurp -d`; a cancelled selection exits 0.
  - `screen` runs `grim` over every output.
  - `window` parses `mmsg get focusing-client` with a recursive inline-Python `find()` (:17-33).
    Mango's geometry includes the 2 px border (`look.conf:5`).
  - It copies with `wl-copy --type image/png` (:39) and sends `notify-send` with no actions (:40).
- `rules.conf:21` has a layer rule for slurp's `selection` namespace.
- There is no editor, no freeze, no delay, no keyboard-only key for laptops without `Print`, and
  no OCR, QR, colour picker, recorder or share picker. Recording exists only as optional apps
  (`modules/recording/{obs,gpu-screen-recorder,kooha}`).
- The repo ships no xdg-desktop-portal-wlr config, so xdpw uses its hard-coded chooser list, in
  which slurp comes first. slurp can only pick outputs (`packaging/mangowm.spec:43`).

#### 1.4 Clipboard, emoji and input

- `Super + V` (`binds.conf:23`) pipes `cliphist list` through `fuzzel --dmenu`. It is text only,
  with no delete, pin or clear. `arctic-session clipboard` runs `wl-paste --watch cliphist store`
  (`dotfiles/.local/bin/arctic-session:37-39`).
- There is no emoji picker. The only emoji font is `google-noto-emoji-fonts` at
  `iso/kiwi/config.kiwi:154`, which is the black-and-white font ✅ (mdapi summary). The colour
  font is `google-noto-color-emoji-fonts` ✅.
- The layout-switch default is `grp:alt_shift_toggle`. The installer sets it for every
  two-layout install (`internal/wizard/locale.go:153`) and Settings uses it when a second layout is
  added (`settings/pages/InputPage.qml:36`). Settings offers eight switch options
  (`SWITCH_KEYS`, `arctic_settings.py:2053-2054`) and six Caps Lock options (`CAPS_OPTIONS`, `:2055`),
  but no compose key.

#### 1.5 Hardware keys

- `binds.conf:86-95` binds volume, mic mute, screen brightness and media keys (`bindl`).
- Keyboard backlight, touchpad toggle, calculator, search and the power button are unbound.
  logind handles the power button (Fedora default: power off).
- `arctic-osd mic mute` always goes through a notification (`arctic-osd:36-40`).

#### 1.6 The shortcut sheet and Settings

- `shell/KeysSheet.qml:8-38` and Settings' `parse_sheet` (`arctic_settings.py:869-882`) both parse
  the hand-kept `dotfiles/.local/share/arctic/keys.txt` (installed to `/usr/share/arctic/keys.txt`,
  spec `:657`). Row format: 4 spaces, keys, 2 or more spaces, description.
- `arctic-keys` (bash) toggles the shell sheet or falls back to `less` in kitty.
- Settings > Shortcuts (`settings/pages/ShortcutsPage.qml`) shows the sheet, "Your shortcuts"
  (`:49-72`) and every bind in the chain (`:113-144`). `cmd_bind_add` (`arctic_settings.py:910-939`)
  refuses a combo that is already bound in the `default` or `common` keymode (`:926-931`).
- `chain_binds` (`:838-866`) has no notion of a shadowed bind. `DISPATCHERS` (`:792-802`) names
  23 dispatchers; any other one is shown as its raw name.

#### 1.7 Mango features Arctic never binds

These were checked in the 0.17.3 docs ✅ (keys.md:94-214; scratchpad.md; overview.md):

- `switcher next|prev|all_tag_next|all_tag_prev|all_next|all_prev` (releasing a modifier selects);
- `togglejump`, `focuslast`;
- `toggle_special_tag`, `tag_special_tag`, `toggle_named_scratchpad appid,title,cmd`;
- `minimized`, `restore_minimized`, `toggleglobal`, `centerwin`;
- `groupjoin left|right|up|down`, `groupfocus prev|next`, `groupleave`;
- `toggle_trackpad_enable`, `setoption key,value`, `setlayout name`.

`mmsg dispatch` takes `<func>,<args> [client,<id>]` ✅ (ipc.md:75-85).

---

### 2. Design

**Principles**

1. **Helpers first.** Every key runs an `arctic-*` helper in `dotfiles/.local/bin`. The helper
   tries the shell over IPC and falls back to grim, slurp, fuzzel or a notification, so the same
   keys work in the waybar fallback session and when the shell has crashed. The
   `arctic-screenshot` precedent stays.
2. **One capture engine.** A new Python helper, `arctic-capture`, does the capture work for every
   front end: freezing outputs, the overlay handshake, slurp, cropping, geometry, OCR, QR and
   pixel reading. The front ends (`arctic-screenshot`, `arctic-colorpick`, `arctic-record`) are thin
   bash scripts that pick a mode and send the notification. The logic that needs tests lives in
   Python.
3. **The freeze is a file, not a live view.** At the moment of the key press, `arctic-capture`
   grabs every output with `grim -t ppm -o <output>` into `$XDG_RUNTIME_DIR/arctic/capture/`. The
   shell overlay shows those files as the frozen backdrop, and the final image is cropped from
   the same file with Pillow. The result is pixel-exact at any scale. It also doesn't depend on
   Quickshell's `ScreencopyView` in Fedora's `dacfa9d` snapshot, or on `grabToImage` scaling. This
   replaces the gap list's "ScreencopyView backdrop"; `ScreencopyView` is used only for the
   share picker's live previews.
4. **Keyboard first, never keyboard only.** Every overlay and picker works fully from the keyboard
   and has a visible focus ring (`FocusRing.qml`).
5. **Tokens only (D9).** Colours come from `Theme.qml`. Amber (`focus`, `accent*`) marks only the
   current selection and the one primary button. The screenshot selection border is `focus`,
   because it is the current selection. Window outlines at rest are `lineStrong`. The dim is
   `scrim`.
6. **Keys are data.** Every bind in Arctic's files carries a `#:` description. The sheet, Settings
   and `keys.txt` are generated from that one source (§13), and tests check each new key against
   every existing key and every layout-switch option (§3.1).

**Processes**

```
Mango bind ─► arctic-screenshot / arctic-colorpick / arctic-record      (bash, dotfiles/.local/bin)
                    │
                    └─► arctic-capture select <mode>                        (python3, dotfiles/.local/bin)
                           ├─ grim -t ppm -o <out> ×N  → $XDG_RUNTIME_DIR/arctic/capture/<out>.ppm
                           ├─ shell running? → request.json + FIFO → arctic-shell-ipc capture select
                           │      └─ shell/CaptureOverlay.qml (one layer per output) → reply on FIFO
                           ├─ else → arctic-capture rects | slurp …   (themed; windows clickable)
                           └─ crop with Pillow → PNG  → stdout: one-line JSON
                    ├─► wl-copy, notify-send -A … (background) → Open / Edit / Show in Files / Move to Trash
                    └─► tesseract | zxing-cpp | wf-recorder, per front end

xdg-desktop-portal-wlr ─► /usr/libexec/arctic/arctic-share-picker ─► shell/SharePicker.qml (FIFO)
                                                                   └─► fuzzel / slurp -or fallback
```

---

### 3. The authoritative keybind table

This table lists every Mango bind that is new, changed or removed in 0.3.0, for every section.
Where another section owns the feature, that section writes the command. **The key comes from
this table.** A section that wants a different key changes this table and the tests in §25.

#### 3.1 How every key was checked

1. **Against every existing bind.** Each combo is normalised to (keymode, set of modifiers,
   lower-cased key), with `code:49` treated as `grave`. It was compared with every `bind*=` line in
   `dotfiles/.config/mango/arctic/apps.conf:6-10` and `binds.conf:8-109`. `look.conf`,
   `input.conf`, `rules.conf` and `autostart.conf` have no binds. `keymode=common` (`binds.conf:8-9`)
   applies in every mode. It was also compared with every row of `keys.txt:3-50` (the same combos
   as text, plus mouse and gesture rows) and with every other new key in this table.
   `test_no_duplicate_binds` (§25.1) repeats this check on every build.
2. **Against the layout-switch options.** All eight options in `SWITCH_KEYS`
   (`arctic_settings.py:2053-2054`) were checked:

   | Option | Chord it steals | Keys in this table that contain it |
   |---|---|---|
   | `grp:alt_shift_toggle` (installer and Settings default), `grp:lalt_lshift_toggle` | Alt + Shift | **none** (that is why Alt + Shift + Tab is not used) |
   | `grp:ctrl_shift_toggle` | Ctrl + Shift | `Ctrl + Shift + Esc` (row 52) |
   | `grp:alt_space_toggle` | Alt + Space | `Super + Alt + Space` (row 46) |
   | `grp:caps_toggle`, `grp:alt_caps_toggle` | Caps Lock | none |
   | `grp:shifts_toggle` | both Shifts | none |
   | `grp:toggle` | Right Alt stops being Alt | Alt keys work with the left Alt only |

   The two clashes happen only when a user picks that option in Settings. Settings then says which
   keys also switch the layout (§15).
   - 🔍 That `grp:alt_space_toggle` fires with Super held as well. Test: `us,il` with that option,
     press Super + Alt + Space, and check the layout indicator.
   - `test_binds_avoid_layout_switch_chords` fails on any new Alt + Shift bind, and on any Ctrl +
     Shift or Alt + Space bind outside the two listed.
3. **Keys Arctic tells users to take stay free.** Settings' empty state suggests
   `Super + Alt + B` (`ShortcutsPage.qml:40`). The Settings tests use it
   (`test_arctic_settings.py:437-440`), and the new wiki example uses it (§4). The web-app section's
   `Web-Apps.md` example uses `Super + Alt + M`. `test_user_example_keys_stay_free` keeps both free.
   For this reason, the bar-focus key the gap list proposed on `Super + Alt + B` moves to
   `Super + Alt + P` (row 41).
4. **Alt + Print.** Mango binds match keycodes, so xkb's `Sys_Req` level doesn't matter ✅
   (keys.md:17; gap-verification). One risk remains: the kernel's sysrq input filter
   (`kernel.sysrq` is non-zero on Fedora) holds back `Alt + SysRq` and re-sends it when Alt is
   released. 🔍 On a Fedora 44 kernel, check whether `Alt + Print` starts the recording when the key
   is pressed or only when Alt is released. If Alt is held and then a letter is pressed, that
   letter's sysrq action may run. With the default mask 16, that is only `s` (sync). If the
   delivery is delayed, `Alt + Print` stays (it still works). If it doesn't arrive at all, delete
   row 9 and keep `Super + Alt + R`.

#### 3.2 The table

Files: `A` = `dotfiles/.config/mango/arctic/apps.conf`, `B` = `binds.conf`. All binds are in
`keymode=default` unless noted.

| # | Keys | Mango line | Does | Owner | Check |
|---|---|---|---|---|---|
| 1 | `Super + B` | A: `bind=SUPER,b,spawn,arctic-open browser` (replaces `:7`) | Open your browser | here (§4) | free in Arctic's files; users' own Super+B → shadow warning (§14) |
| 2 | `Super + W` | A `:7` removed | — (unbound, D7) | here | free for users; one-time notice (§14.3) |
| 3 | `Super + V` | B: `bind=SUPER,v,spawn,arctic-clipboard` (replaces `:23`) | Clipboard history, shell panel | here (§12) | same key |
| 4 | `Super + Shift + S` | B: `bind=SUPER+SHIFT,s,spawn,arctic-screenshot area` | Screenshot of an area | here (§5) | free; `Super + S` (Settings, `:20`) differs by Shift |
| 5 | `Ctrl + Print` | B: `bind=CTRL,Print,spawn,arctic-screenshot area --copy-only` | Area to the clipboard only | here | free; no Shift, so `ctrl_shift_toggle` doesn't touch it |
| 6 | `Super + Ctrl + Print` | B: `bind=SUPER+CTRL,Print,spawn,arctic-screenshot text` | Copy text (OCR) | here (§6) | free (Omarchy's key) |
| 7 | `Super + Shift + C` | B: `bind=SUPER+SHIFT,c,spawn,arctic-colorpick` | Pick a colour | here (§7) | free; Omarchy's `Super + Print` is Arctic's window shot |
| 8 | `Super + Alt + R` | B: `bind=SUPER+ALT,r,spawn,arctic-record toggle` | Record the screen / stop | here (§8) | free; `Super + Shift + R` (common) differs |
| 9 | `Alt + Print` | B: `bind=ALT,Print,spawn,arctic-record toggle` | Same | here | free; 🔍 sysrq filter (§3.1.4) |
| 10 | `Alt + Tab` | B: `bind=ALT,Tab,switcher,next` | Switch windows on this workspace | here (§18) | free; Arctic had no Alt binds |
| 11 | `` Alt + ` `` (the key above Tab) | B: `bind=ALT,code:49,switcher,prev` | Switch windows, backwards | here | replaces Alt + Shift + Tab (layout toggle) |
| 12 | `Super + Alt + Tab` | B: `bind=SUPER+ALT,Tab,switcher,all_next` | Switch windows on every workspace and monitor | here | free |
| 13 | `Super + J` | B: `bind=SUPER,j,togglejump` | Jump to a window by its letter | here (§18) | free |
| 14 | `Super + Backspace` | B: `bind=SUPER,BackSpace,focuslast` | Back to the previous window | here | free |
| 15 | `` Super + ` `` | B: `bind=SUPER,code:49,toggle_special_tag` | Show / hide the scratch workspace | here (§19) | free |
| 16 | `` Super + Shift + ` `` | B: `bind=SUPER+SHIFT,code:49,tag_special_tag` | Move the window to / from it | here | free |
| 17 | `Super + Alt + Enter` | A: `bind=SUPER+ALT,Return,toggle_named_scratchpad,org.arcticlinux.Dropdown,none,arctic-open terminal --app-id org.arcticlinux.Dropdown` | Drop-down terminal | here (§19) | free; `Super + Enter` differs by Alt |
| 18 | `Super + H` | B: `bind=SUPER,h,minimized` | Hide the window | here (§20) | free |
| 19 | `Super + Shift + H` | B: `bind=SUPER+SHIFT,h,restore_minimized` | Bring a hidden window back | here | free |
| 20 | `Super + Shift + P` | B: `bind=SUPER+SHIFT,p,spawn,arctic-window pin` | Pin a floating window to every workspace | here | free |
| 21-24 | `Super + Alt + ←` `→` `↑` `↓` | B: `bind=SUPER+ALT,Left,groupjoin,left` (and Right, Up, Down) | Tab the window into its neighbour's group | here | free (`Super + Ctrl + arrows` = mfact/nmaster, `Super + Shift + arrows` = swap) |
| 25 | `Super + Alt + G` | B: `bind=SUPER+ALT,g,groupleave` | Take the window out of its group | here | free |
| 26-27 | `Super + Alt + Page Up` / `Page Down` | B: `bind=SUPER+ALT,Page_Up,groupfocus,prev` / `…Page_Down,groupfocus,next` | Previous / next tab in the group | here | free |
| 28 | `Super + Ctrl + E` | B: `bind=SUPER+CTRL,e,spawn,arctic-emoji` | Emoji picker | here (§11) | free (`Super + .` is focusmon, `:69`) |
| 29-30 | Keyboard-light keys | B: `bindl=NONE,XF86KbdBrightnessUp,spawn,arctic-osd kbd up` / `…Down…down` | Keyboard backlight | here (§17) | free |
| 31 | Touchpad keys | B: `bind=NONE,XF86TouchpadToggle,spawn,arctic-touchpad toggle`, `…XF86TouchpadOn…on`, `…XF86TouchpadOff…off` | Touchpad on / off | here | free |
| 32 | Calculator key | B: `bind=NONE,XF86Calculator,spawn,arctic-launcher =` | Launcher in calculator mode | here | free |
| 33 | Search key | B: `bind=NONE,XF86Search,spawn,arctic-launcher` | Launcher | here | free |
| 34 | Power button | B: `bind=NONE,XF86PowerOff,spawn,arctic-power` | Power menu (logind held off by the shell) | here | free |
| 35 | `Super + A` | B | Quick settings | bar and quick-settings section (D5) | free (`Super + Shift + A` = Get apps) |
| 36-40 | `Super + Ctrl + A` / `W` / `B` / `D` / `P` | B | Audio / network / Bluetooth / display / power panels | bar section | free (only `Super + Ctrl + arrows` were taken) |
| 41 | `Super + Alt + P` | B | Focus the bar from the keyboard | bar section | **changed from the gap list's Super + Alt + B** (§3.1.3); follows KDE's Meta + Alt + P "walk through panels" |
| 42 | `Super + Alt + N` | B | Notification centre | notifications section (D6) | free |
| 43 | `Super + Delete`, `Super + Shift + Delete` | B `:74-75`, same keys, new command (`arctic-notify dismiss\|dismiss-all`) | Dismiss | notifications section | unchanged keys |
| 44 | `Super + Ctrl + N` | B | Night light | modes | free |
| 45 | `Super + Ctrl + I` | B | Keep awake | modes | free (`Super + I` = installer) |
| 46 | `Super + Alt + Space` | B | Command menu | command-menu owner | free; **also switches layout under `grp:alt_space_toggle`** (Settings warns) |
| 47 | `Super + Ctrl + C` | B | Capture menu (rows in §10) | command-menu owner | free; `Super + Shift + C` (row 7) differs |
| 48 | `Super + Ctrl + T` | B | Calendar | bar section | free |
| 49 | `Super + Ctrl + M` | B | Media | bar section | free |
| 50 | `Super + P` | B | Display mode | displays owner | free |
| 51 | `Super + Alt + K` | B | Keyboard pointer (wl-kbptr) | accessibility owner | free |
| 52 | `Ctrl + Shift + Esc` | B | Activity (btop) | system-tools owner | free; **also switches layout under `grp:ctrl_shift_toggle`** (Settings warns) |
| 53 | `Super + Ctrl + S` | B | Share menu | share owner | free; `Super + Shift + S` (row 4) differs |
| 54 | `Super + Ctrl + R` | B | Reminder | reminders owner | free |
| 55 | `Shift + Mute` | B: `bindl=SHIFT,XF86AudioMute,…` | Next audio output | audio (bar section) | free |

Rows 35-55 go into `binds.conf` in the section named in §13.3, each with a `#:` line
(`test_every_bind_is_described`, §25.1).

#### 3.3 Keys deliberately not used

| Keys | Why |
|---|---|
| `Alt + Shift + Tab` | It flips the layout on every two-layout install (V1 keymaps lock the group on press; libxkbcommon issue #92). `` Alt + ` `` replaces it. |
| `Super + Alt + B` | Settings (`ShortcutsPage.qml:40`) and the wiki suggest it for users' own shortcuts. |
| `Super + Alt + M` | `Web-Apps.md`'s example user bind. |
| `Super + W` | Left unbound (D7). |
| `Super + Print` for the colour picker (Omarchy) | Arctic's window screenshot is on it (`binds.conf:84`). |
| `Super + .` for emoji (Windows) | focusmon (`binds.conf:69`). |
| `Super + C` / `X` / `V` universal copy (Omarchy) | Skipped in `gap-list.json`; `Super + V` is clipboard history. |
| `Super + K` for the sheet (Omarchy) | Arctic's sheet is `Super + /` (unchanged). `Super + K` stays free. |

#### 3.4 Keys inside Arctic surfaces (not Mango binds)

These work only while an Arctic layer has exclusive keyboard focus, so no Mango bind can take
them. None uses Alt + Shift, Ctrl + Shift or Alt + Space.

| Surface | Keys |
|---|---|
| Capture overlay (§5.4) | drag / click, `Enter`, `Ctrl + Enter`, `Tab` / `Shift + Tab`, arrows, `Ctrl` + arrows, `Shift` + arrows, `R`, `Esc` |
| Colour loupe (§7) | arrows, `Ctrl` + arrows, `Enter`, `Esc` |
| Record dialog (§8.4) | `←` `→`, `Tab` / `Shift + Tab`, `↑` `↓`, `Enter`, `Esc` |
| Share picker (§9) | arrows, `Tab`, `Enter`, `Esc` |
| Emoji picker (§11) | type, arrows, `Enter`, `Shift + Enter`, `Alt + 1…6` (skin tone), `Esc` |
| Clipboard panel (§12) | type, `↑` `↓`, `Enter`, `Shift + Enter`, `Delete`, `Ctrl + P`, `Esc` |
| Shortcut sheet (§13) | type to filter, `↑` `↓`, `Esc` |

---

### 4. The browser on Super + B (request #5)

**Changes**

| File | Change |
|---|---|
| `dotfiles/.config/mango/arctic/apps.conf:7` | `bind=SUPER,b,spawn,arctic-open browser`, with `#: Browser` above it (full file in §13.3). No `SUPER,w` line. |
| `settings/scripts/arctic_settings.py:1793` | `keys='Super + B'`. `AppsPage.qml:27` shows it; nothing else changes there. |
| `settings/pages/AppsPage.qml:3` | Comment: `(Super + B, Super + Enter, Super + F, Super + E)`. |
| `dotfiles/.local/share/arctic/keys.txt` | Regenerated (§13): `    Super + B                Browser`. |
| `docs/wiki/Themes-and-Customisation.md:218-219` | `# An extra shortcut: Super + Alt + B opens Firefox` / `bind=SUPER+ALT,b,spawn,firefox`. |
| `dotfiles/README.md:139-140` | "**Bar keyboard access:** `Super + Alt + P` moves keyboard focus to the bar (the design's `Super + B` opens your browser instead)." The bar section builds bar focus. If it slips out of 0.3.0, keep "isn't there yet" and drop the key. |
| Other docs | §26. |

- `arctic-open` doesn't change for the key move: the key isn't in the script. It changes for
  `--focus` and `--raise-title` (§21).
- **Super + W** stays unbound (D7). The one-time login notice (§14.3) tells existing users where
  the browser went. People who want it back add `bind=SUPER,w,spawn,arctic-open browser` in
  Settings > Shortcuts (command `arctic-open browser`) or in `user.conf`.
- **Users who bound Super + B themselves**, following the wiki or through Settings, get the shadow
  warning in Settings and at login (§14).
- **Release notes** (0.3.0): "Super + B opens your browser (it was Super + W, which is now free
  for your own shortcut). If you had your own Super + B, Settings > Shortcuts shows that it no
  longer runs."

---

### 5. Screenshots (request #5 and `screenshot-editor-overlay`)

#### 5.1 Keys

| Keys | Mode | Result |
|---|---|---|
| `Print`, `Super + Shift + S` (new) | area | Overlay on a frozen screen: drag an area, click a window, or click empty space for the whole monitor. Saved and copied. |
| `Shift + Print` | screen | The **focused** monitor, saved and copied. It used to be every monitor combined; `--all` keeps that and is in the capture menu when there is more than one monitor. |
| `Super + Print` | window | The focused window without its 2 px border, saved and copied. |
| `Ctrl + Print` (new) | area, `--copy-only` | Copied only. The notification offers **Save**. |

`Super + Shift + S` is the Windows Snipping Tool key ("win" in the request). Many laptops' snip
key sends exactly Meta + Shift + S 🔍 (check on one such laptop with `wev`).

#### 5.2 `arctic-screenshot` (bash, stays the entry point; `dotfiles/.local/bin/arctic-screenshot`)

```
arctic-screenshot area   [--copy-only] [--edit]
arctic-screenshot screen [--all] [--delay SECONDS] [--copy-only] [--edit]
arctic-screenshot window [--pick] [--delay SECONDS] [--copy-only] [--edit]
arctic-screenshot text        # copy the text in an area (§6)
arctic-screenshot qr          # copy the QR code in an area (§6)
arctic-screenshot edit FILE   # open FILE in the editor, then copy and notify (the Edit action)
```

- **Exit codes**: 0 = saved, copied or cancelled; 1 = the capture failed (a notification says
  why); 2 = usage.
- **Press again to cancel**: the script takes `flock -n "$XDG_RUNTIME_DIR/arctic/capture.lock"`.
  If the lock is held, a selection is open. The script then runs
  `arctic-shell-ipc capture cancel; pkill -x slurp` and exits 0. This applies to every capture key.
- **Delay**: `--delay 1…10` sleeps before `screen` and `window` captures. No countdown
  notification is shown, because it would appear in the picture.
- **File names**:
  - `$(xdg-user-dir PICTURES)/Screenshots/Screenshot YYYY-MM-DD HH.MM.SS.png`, as today;
    ` (2)`, ` (3)`… is added on a clash.
  - `--copy-only`, `text` and `qr` write to `$XDG_RUNTIME_DIR/arctic/tmp/<mode>-<ts>.png` (0700
    folder) instead. `arctic-capture` removes its own `capture/` folder when it exits, so temp
    results never go there. A copy-only file is deleted when its notification closes, unless
    **Save** moved it; OCR and QR temp files are deleted as soon as they are read.
- **Flow** (bash, about 120 lines, `shellcheck -x` clean):
  1. `out="$(arctic-capture select <mode> --out "$file" [--all] [--pick])"`
  2. If the JSON has `"code":"cancelled"`, exit 0. On any other `ok:false`, notify its `error` and
     exit 1.
  3. `wl-copy --type image/png < "$file"`.
  4. Send the notification in a detached subshell (§5.6).
  5. With `--edit`, run `arctic-screenshot edit "$file"` instead of the plain notification.
- The header comment (`:2-3`) names every key and mode.

#### 5.3 `arctic-capture` (new; Python 3, standard library plus Pillow; `dotfiles/.local/bin/arctic-capture`)

Pillow is already a Requires of arctic-desktop-config (spec `:167`). `python3-zxing-cpp` is
optional (§6). Every command prints one line of JSON on stdout: `{"ok":true,…}` or
`{"ok":false,"code":"…","error":"One sentence."}`. The keys are snake_case, as in the web-app
engine (D4). Nothing else is written to stdout.

| Command | Does | Output |
|---|---|---|
| `select area [--out FILE] [--geometry-only]` | Freeze, overlay (shell) or slurp (fallback), crop | `{"ok":true,"kind":"area","file":"…","output":"eDP-1","x":100,"y":200,"width":640,"height":480,"scale":1.25}` (x/y in layout coordinates, logical px) |
| `select window [--pick] [--out FILE]` | Focused window (no UI); with `--pick`, the overlay in window mode or `slurp -r` over window rectangles | `kind:"window"`, plus `"window_id":42,"app_id":"firefox","title":"…"` |
| `select screen [--all] [--out FILE]` | Focused output (`mmsg get all-monitors`, `active`), or all | `kind:"screen"` |
| `select output [--geometry-only]` | Pick one output (recording, share fallback) | `kind:"output"` |
| `select point` | Colour pick (overlay point mode or `slurp -p`) | `{"ok":true,"kind":"point","hex":"#1e2a38","rgb":[30,42,56],"output":"eDP-1","x":…,"y":…}` |
| `rects [--output NAME]` | Visible windows as slurp's predefined rectangles (`"x,y wxh label"` lines, not JSON) | text |
| `windows` | Visible windows for the overlay and the share picker | `{"ok":true,"windows":[{"id":42,"foreign_toplevel_id":"…","app_id":"firefox","title":"…","output":"eDP-1","workspace":2,"x":…,"y":…,"width":…,"height":…,"floating":false}]}` |
| `ocr FILE` | tesseract (§6) | `{"ok":true,"text":"…","langs":["heb","eng"]}` |
| `qr FILE` | zxing-cpp, else zbarimg (§6) | `{"ok":true,"codes":["…"],"kind":"url"}` (kind: `url`, `otpauth`, `wifi`, `text`) |
| `swatch HEX OUT.svg` | A 64×64 rounded-square SVG for the colour notification | `{"ok":true,"file":"…"}` |
| `uri FILE` | `file://` URI, percent-encoded | `{"ok":true,"uri":"…"}` |

Error codes: `cancelled`, `busy`, `no_display`, `capture_failed`, `no_window`, `timeout`,
`missing_tool` (`"tool":"tesseract"`), `not_found` (no text or code), `usage`.

**Details**

- **Mango JSON**:
  - `mmsg get all-monitors` → `{"monitors":[{name, active, x, y, width, height, scale, …}]}`.
  - `mmsg get focusing-client` → a flat object, or `{"error":"no focused client"}` ✅ (research
    against ipc.c).
  - `mmsg get all-clients` → `{"clients":[…]}` (`arctic-settings:53-58` reads it this way).
  - 🔍 The field names used: `is_fullscreen`, `is_floating`, `is_global`, `is_minimized`,
    `is_visible` (or tags against the monitor's active tags), `foreign_toplevel_id`, and whether
    the monitor `x/y/width/height` are logical layout px. Prove it with `mmsg get all-clients` and
    `all-monitors` on Mango 0.17.3 at scale 1.25. The parser accepts `appid` and `app_id`.
- **Visible windows**:
  - A window counts when `is_visible` is true. Without that field, it counts when its tags
    intersect its monitor's active tags and it isn't minimised or in the scratchpad.
  - Order: floating windows first, then tiled. Within each group the list keeps Mango's order.
    🔍 Whether `all-clients` is in stacking order: open two overlapping floating windows and see
    which one a click picks.
- **Border inset** (window mode):
  - `borderpx` is the last value in the config chain. The chain is followed from
    `~/.config/mango/config.conf` through `source=`/`source-optional=`, as `read_chain` does
    (`arctic_settings.py:257-283`); the default is 2.
  - Fullscreen windows get no inset.
  - Geometry: `x+bw, y+bw, width-2bw, height-2bw`.
- **Scale**: grim's default scale is the highest of all outputs ✅ (grim(1) `-s`). Every grim call
  here therefore passes `-s <scale of the output>`. Crops from the frozen file use
  `sx = image.width / screen_width`, where `screen_width` comes from the overlay's logical screen,
  so the result is exact at 1, 1.25 and 2.
- **Freeze**:
  - One `grim -t ppm -s <scale> -o <name> <dir>/<name>.ppm` per output, run in parallel.
  - The directory is `$XDG_RUNTIME_DIR/arctic/capture/`, mode 0700. It is created fresh and
    removed on exit, even on errors (`try/finally`).
  - 🔍 Time from key press to overlay under 250 ms for one 1920×1080 output and under 400 ms for
    two 4K outputs. Measure with `ARCTIC_CAPTURE_DEBUG=1`, which prints timings to stderr. If it is
    slower, freeze the focused output first and the others in the background.
- **Overlay handshake** (shell running = `arctic-shell-ipc shell live` exits 0):
  1. Write `request.json` (§5.4).
  2. `mkfifo reply.fifo`.
  3. Open the read end `O_RDONLY|O_NONBLOCK`, then a dummy write end of our own, so no early EOF
     can arrive.
  4. `arctic-shell-ipc capture select <request path>`.
  5. `select()` with a 300 s timeout, then read one line.
  6. Timeout → `capture cancel` → `code:"timeout"`.
- **Fallback** (no shell):
  - `area`: `arctic-capture rects | slurp -d $SLURP_COLORS -F Figtree -w 2`. Clicking a window picks
    its rectangle ✅ (slurp(1) predefined rectangles on stdin). Then
    `grim -s <scale> -g "<geom>" <out>`. Nothing is frozen.
  - `point`: `slurp -p`, then `grim -s <scale> -g "X,Y 1x1" -t ppm -`. The top-left pixel is read
    without Pillow (P6 parser).
  - `output`: `slurp -or -f '%o'`.
  - `SLURP_COLORS` comes from `~/.config/arctic/current/capture-colors.env` (§5.8). Without it,
    slurp's own colours are used.
- `select` refuses to run on the lock screen: `arctic-shell-ipc lock isLocked` returns true →
  `code:"busy"`. Print binds aren't `bindl` anyway.

#### 5.4 The capture overlay (`shell/CaptureOverlay.qml`, new)

**Request** (`$XDG_RUNTIME_DIR/arctic/capture/request.json`, 0600, written by `arctic-capture`):

```json
{"version":1,"mode":"area","reply":"/run/user/1000/arctic/capture/reply.fifo",
 "outputs":[{"name":"eDP-1","frozen":"/run/user/1000/arctic/capture/eDP-1.ppm","scale":1.25}],
 "windows":[{"id":42,"app_id":"firefox","title":"Arctic Linux – Zen","output":"eDP-1",
             "x":8,"y":42,"width":944,"height":1150,"floating":false}],
 "last":{"output":"eDP-1","x":100,"y":200,"width":640,"height":480}}
```

- `mode` is one of `area`, `window` or `point`.
- Window rectangles are output-local, logical px.
- `last` is the previous area, kept in `~/.local/state/arctic/capture.json`.

**Reply** (one line, written to the FIFO):

```json
{"ok":true,"mode":"area","output":"eDP-1","x":100,"y":200,"width":640,"height":480,"screen_width":1536,"screen_height":960}
{"ok":true,"mode":"window","output":"eDP-1","window_id":42,"x":8,"y":42,"width":944,"height":1150,"screen_width":1536,"screen_height":960}
{"ok":true,"mode":"point","output":"eDP-1","x":733,"y":410,"screen_width":1536,"screen_height":960}
{"ok":false,"code":"cancelled"}
```

**IPC** (`shell/shell.qml`, after the `updates` handler at `:134-138`):

```qml
IpcHandler {
    target: 'capture'
    // arctic-capture writes request.json and waits for the reply on the FIFO it names.
    function select(request: string): void { capture.start(request); }
    function cancel(): void { capture.cancel(); }
    function active(): bool { return capture.active; }
}
```

- `start()` accepts only a path inside `Session.runtimeDir + '/arctic/capture/'`. It reads the file
  with `FileView` (`blockLoading: true`), calls `shell.closePopovers(null)` (the frozen image
  already shows any open popover), cancels an older request, and shows the overlay.
- The reply is written with
  `Quickshell.execDetached(['timeout','2','sh','-c','printf "%s\\n" "$1" > "$2"','sh', json, fifo])`.
  `FileView` would replace the FIFO with a file; `timeout` guards against a helper that died.
- One argument per IPC function, so the `IpcHandler` multi-argument question (🔍 in the Get apps
  section) doesn't arise here.

**Surface** (`shell/CaptureSurface.qml`, one per screen through `Variants`):

- `PanelWindow` on `WlrLayer.Overlay`, namespace `arctic-capture`, all four anchors, margins 0,
  `exclusionMode: ExclusionMode.Ignore`. It covers the bar.
- `WlrLayershell.keyboardFocus`: `Exclusive` on `Outputs.focused`, `None` on the others.
- **Backdrop**: `Image { source: 'file://' + frozen; smooth: false; cache: false; asynchronous: false }`
  filling the window. A screen without a frozen file (plugged in meanwhile) shows the dim only.
- **Dim**: four `Theme.scrim` rectangles around the selection. The selection itself is undimmed.
- **Selection**: a 2 px `Theme.focus` border, plus 8 px `Theme.focus` squares on the corners and
  edge midpoints (resize handles).
- **Hovered window** before any drag: a 2 px `Theme.lineStrong` outline, and a chip with the app
  name (`Theme.surfaceRaised`, `Theme.ink`, 12 px sans).
- **Size badge**: `640 × 480` in `Theme.fontMono` 12, tabular, on a `Theme.surfaceRaised` pill
  with a `Theme.line` border. It sits under the selection's bottom-right corner, flipped inside the
  screen.
- **Hint pill**, bottom centre, `Theme.frost`, 44 px from the edge like the OSD: "Drag an area ·
  Click a window · Enter captures · Esc cancels". It fades out on the first drag.
- **Cursor**: `Qt.CrossCursor`.
- **Motion**: the overlay appears without animation (the frozen frame must not move); the dim
  fades in over `Theme.fadeBase`. Reduced motion changes nothing.

**Mouse**

- Press, drag and release captures that area. A drag is clamped to the output where it started.
- A click (under 4 px of movement) on a window captures that window's rectangle. A click on empty
  space captures the whole output.
- Window mode: only clicks on windows count.
- Right click cancels.

**Keyboard** (area mode)

| Key | Does |
|---|---|
| `Tab` / `Shift + Tab` | Highlight the next / previous visible window on this output |
| `Enter` | Capture the highlighted window, or the keyboard rectangle |
| `Ctrl + Enter` | Capture the whole output (Omarchy's key) |
| `R` | Restore the last area as the keyboard rectangle |
| Arrows | Move the keyboard rectangle 1 px (`Ctrl`: 10 px) |
| `Shift` + arrows | Resize it 1 px from the bottom-right |
| `Esc` | Cancel |

In point mode, the arrows move a keyboard crosshair (§7) and `Enter` picks. None of these keys
uses Alt + Shift or Ctrl + Shift (§3.4).

- **Multi-monitor**: every output shows its own frozen frame. The keyboard works on the focused
  output; the mouse works on all of them.
- **Accessibility**: `Accessible.role: Accessible.Pane`, and `Accessible.name` set to the hint text
  and the current selection size.

#### 5.5 Without the shell

`arctic-capture` falls back to slurp (§5.3). The themed colours come from §5.8. Everything else is
the same: the save path, the clipboard, the notification and its actions.

#### 5.6 The notification and its actions (D7)

```bash
notify() {   # runs detached: ( notify ) </dev/null >/dev/null 2>&1 & disown
  local action actions=(-A default=Open)
  [[ -n "$editor" ]] && actions+=(-A edit=Edit)
  actions+=(-A folder="Show in Files" -A trash="Move to Trash")
  action="$(notify-send -a Screenshot -i "$file" -h "string:image-path:$file" "${actions[@]}" \
    "Screenshot saved" "Copied to the clipboard · ${file/#$HOME/\~}")" || return
  case "$action" in
    default) xdg-open "$file" ;;
    edit)    arctic-screenshot edit "$file" ;;
    folder)  show_in_files "$file" ;;
    trash)   gio trash -- "$file" ;;
  esac
}
```

- **Default action** (click the notification) is **Open**. `notify-send -A NAME=Label` blocks and
  prints the chosen name ✅, as `arctic-welcome:30-37` already relies on. So the notification runs
  in a detached subshell and the key's process exits at once.
- **Edit** is offered only when an editor is installed (§5.7).
- **Show in Files**:
  1. `gdbus call --session --timeout 2 --dest org.freedesktop.FileManager1
     --object-path /org/freedesktop/FileManager1 --method org.freedesktop.FileManager1.ShowItems
     "['<uri>']" ""`, with the URI from `arctic-capture uri`.
  2. If that fails, `xdg-open "$dir"`.
  - 🔍 Thunar and Nautilus both answer `FileManager1.ShowItems` on Fedora 44. Check with the call
    above.
- **Move to Trash** uses `gio trash`, which can be undone. It doesn't delete.
- `--copy-only` sends "Screenshot copied" with `-A save=Save` instead; **Save** moves the temp
  file into Screenshots. The temp file is removed when `notify-send` returns.
- **In the Quickshell session** the shell's NotificationServer (D6, notifications section) shows
  action buttons and the image. The notifications section must:
  - not show the `default` action as a button (freedesktop convention);
  - show `image-path` as a thumbnail;
  - keep a notification open (not closed over D-Bus) while it sits in the centre, so the actions
    still work from there. If it closes instead, the actions end when the toast goes, and nothing
    breaks.
- **In the waybar fallback**, mako shows it. Left click = Open (mako's default). The other actions
  are reached with a middle click: add
  `on-button-middle=exec makoctl menu -n "$id" -- fuzzel --dmenu --prompt "Action  "` to the global
  section of `design/themegen/templates/mako.ini.tmpl`, then regenerate both themes with
  `python3 design/tools/gen-desktop-themes.py`. mako 1.11.0 is in F44 ✅. 🔍 `makoctl menu` exists
  in 1.11 (`makoctl help`).

#### 5.7 The editor

- **satty is not in Fedora 44** ✅ (mdapi 400). **swappy 1.5.1 is** ✅ (`1.5.1-8.fc44`). Edit uses
  satty when it is on `PATH` (for example from Flathub or cargo), and swappy otherwise (D7).
- `arctic-screenshot edit FILE`:
  - satty: `satty --filename "$FILE" --output-filename "$OUT" --early-exit`.
    🔍 These flags on whatever satty version is found; the helper checks `satty --help`.
  - swappy: `swappy -f "$FILE" -o "$OUT"`. `-o` writes the final image when swappy exits ✅
    (swappy README).
  - `$OUT` is `<dir>/<name> (edited).png`. The original is never overwritten; an Esc after drawing
    doesn't destroy it.
  - After the editor exits:
    - if `$OUT` differs from `$FILE`: `wl-copy --type image/png < "$OUT"`, then the notification
      "Edited screenshot saved" with Open / Show in Files / Move to Trash;
    - if it is identical: delete `$OUT`.
- **`dotfiles/.config/swappy/config`** (new; `/etc/skel` gets it through the tar at spec `:621-625`):

  ```ini
  [Default]
  save_dir=$HOME/Pictures/Screenshots
  save_filename_format=Screenshot %Y-%m-%d %H.%M.%S (edited).png
  show_panel=true
  text_font=Figtree
  paint_mode=arrow
  early_exit=true
  ```

  The keys are swappy's documented ones ✅. Its UI is GTK 3 and follows adw-gtk3.
- **Icons**: swappy draws its panel icons with Font Awesome 5. F44 ships no FA5 font ✅; it has
  `fontawesome4-fonts` and `fontawesome-6-free-fonts` ✅, and swappy's own Requires pull neither ✅.
  - 🔍 Whether `fontawesome-6-free-fonts` draws swappy's glyphs. Install it in the F44 VM and open
    swappy.
  - If it does: add `Recommends: fontawesome-6-free-fonts`.
  - If it doesn't: set `show_panel=false` (swappy's keys still work: `a` arrow, `t` text,
    `r` rectangle, `d` blur, `Ctrl + S`, `Ctrl + C`) and note it in Troubleshooting.

#### 5.8 Themed slurp colours (fallback only)

A new template, `design/themegen/templates/capture-colors.env.tmpl`, rendered into every theme
folder. Templates are found automatically ✅ (`design/themegen/render.py:200`).

```sh
# Generated by arctic-themegen from the {{label}} palette — do not edit by hand.
# slurp colours for arctic-capture's fallback (no shell): dim, selection, windows.
SLURP_COLORS="-b #{{scrim|nohasha}} -c #{{focus|nohasha}} -s #00000000 -B #{{line-strong|nohash}}40"
```

Regenerate `dotfiles/.config/arctic/themes/{winter,polar-night}` with
`python3 design/tools/gen-desktop-themes.py`. The spec's `%check` diffs the Winter render
(`:816-821`).

---

### 6. Text (OCR) and QR codes (`ocr-qr-capture`)

**Text** (`Super + Ctrl + Print`, capture menu)

- Flow: `arctic-screenshot text` → `arctic-capture select area --out <tmp>` → `arctic-capture ocr <tmp>`
  → `wl-copy -- "$text"`.
- The text goes into clipboard history (it isn't secret).
- `ocr` runs `tesseract <file> - -l <langs>`. tesseract 5.5.3 is in F44 ✅.
- **Languages**:
  - The installed ones from `tesseract --list-langs`, minus `osd` and `equ`.
  - Order: the language of `LANG` first, then those of the configured keyboard layouts
    (`xkb_rules_layout` from the chain), then `eng`. At most three.
  - The mapping table is in the script: `he`/`il`→`heb`, `ar`/`ara`→`ara`, `ru`→`rus`,
    `uk`/`ua`→`ukr`, `el`/`gr`→`ell`, `de`→`deu`, `fr`→`fra`, `es`→`spa`, `it`→`ita`,
    `pt`→`por`, `nl`→`nld`, `pl`→`pol`, `tr`→`tur`, `ja`→`jpn`, `ko`→`kor`, `zh_CN`→`chi_sim`,
    `zh_TW`→`chi_tra`.
- **Notification** "Text copied": body = the first line, up to 80 characters, plus " (N lines)".
  Nothing found → "No text found in that area".
- **Missing language pack**: when the locale's pack (for example `tesseract-langpack-heb` ✅ in F44)
  isn't installed, add `-A lang="Add Hebrew"`. It runs
  `arctic-shell-ipc apps search dnf tesseract-langpack-heb`, the Get apps section's IPC. It is
  offered once per language (`~/.local/state/arctic/capture.json`).
- **tesseract missing**: "Text recognition isn't installed" with **Install**
  (`apps search dnf tesseract`).

**QR** (capture menu only; no key)

- Flow: `arctic-screenshot qr` → area → `arctic-capture qr <tmp>`.
- **Decoder**: `python3-zxing-cpp` 2.2.1 is in F44 ✅. It is used with Pillow:
  `zxingcpp.read_barcodes(Image.open(f), formats=zxingcpp.BarcodeFormat.QRCode)`.
  - 🔍 That call signature in 2.2.1. Test with a generated QR fixture (`shell/tests/fixtures/qr.png`,
    made once with `qrencode`, which is in F44).
  - Fallback: `zbarimg -q --raw -Sdisable -Sqrcode.enable <file>` (Omarchy's flags).
  - Not zbar by default: F44's `zbar` pulls GraphicsMagick and its image libraries ✅ (mdapi
    Requires). `python3-zxing-cpp` needs only libZXing.
- **Copy**: `wl-copy --sensitive`, so the code never enters cliphist ✅ (F44 wl-clipboard has
  `--sensitive`; cliphist 0.7.0 skips sensitive entries). QR codes often carry `otpauth://` secrets.
- **Notification** by kind (the secret is never shown):
  - `url`: "Link copied" + the URL cut to 60 characters + **Open link** (`xdg-open`, http and
    https only);
  - `otpauth`: "Sign-in code copied" / "It's kept out of clipboard history.";
  - `wifi`: "Wi-Fi details copied" / "Network “<SSID>”";
  - `text`: "QR code copied" + the first 60 characters.
  - Several codes: the first is copied, and the body adds "(2 codes found)".

---

### 7. Colour picker (`color-picker`, `Super + Shift + C`)

- `arctic-colorpick` (new bash helper):
  - Lock → `arctic-capture select point` → `wl-copy -- "#rrggbb"`. Lower case, like the tokens.
  - Pressing the key again cancels (§5.2).
  - hyprpicker and wl-color-picker aren't in F44 ✅.
- **Shell path, the overlay in point mode** (`CaptureSurface.qml`):
  - a loupe of 11×11 source px at ×10, drawn by `Image { sourceClipRect; smooth: false }` from the
    frozen file;
  - it has `Theme.radiusMd` corners and a `Theme.line` border, and the centre pixel is outlined 1 px
    in `Theme.focus`;
  - it follows the pointer at 24 px offset and flips at edges;
  - under it, a live hex label and a swatch. The label is read from an 11×11 `Canvas`
    (`drawImage`, `getImageData`).
    🔍 Canvas cost at 60 Hz on the F44 VM. If it is too slow, the hex appears only after the click.
  - The value copied is always the one `arctic-capture` reads from the frozen PPM at physical px.
  - Keys: arrows move 1 px, `Ctrl` + arrows 10 px, `Enter` picks, `Esc` cancels.
- **Fallback**: `slurp -p` and a 1×1 grim capture. On a scaled output grim returns scale×scale px
  (🔍 in gap-verification); the helper reads the top-left one.
- **Notification**:
  - app "Colour picker", icon `arctic-capture swatch`;
  - summary `#1e2a38 copied`, body `rgb(30, 42, 56) · hsl(212, 30%, 17%)`;
  - actions `rgb=Copy rgb()`, `hsl=Copy hsl()`.

---

### 8. Screen recording (`screen-recording`)

#### 8.1 Keys and entry points

- `Super + Alt + R` (Windows Game Bar) and `Alt + Print` (Omarchy) run `arctic-record toggle`.
- The capture menu has "Record the screen…" and, while recording, "Stop recording".
- The quick-settings tile (control-center, bar section) calls `arctic-record toggle`.
- The recording mode indicator (mode-indicators) stops it on click.

#### 8.2 `arctic-record` (new bash helper)

```
arctic-record toggle                                   # recording? stop : ask (shell dialog) or start with the last choice
arctic-record start area|window|screen [--audio none|desktop|mic] [--no-dialog]
arctic-record stop
arctic-record status [--json]
```

- **State**: `$XDG_RUNTIME_DIR/arctic/record.json`, written on start and removed on stop:
  `{"ok":true,"recording":true,"pid":4242,"file":"…","started":1727530000,"kind":"area","audio":"desktop","geometry":"0,0 1920x1200","codec":"libvpx-vp9"}`.
  `status --json` prints it, or `{"ok":true,"recording":false}`.
- **Region**: `area` → `arctic-capture select area --geometry-only`; `window` →
  `select window --pick --geometry-only`; `screen` → the focused output (`-o <name>`), or
  `select output` when there are several.
  - A window recording records the window's rectangle at start; it doesn't follow the window
    (wf-recorder records a region).
- **Backend**: wf-recorder 0.6.0 ✅ (`0.6.0-2.fc44`, wlr-screencopy, which Mango creates).
  Fedora patches wf-recorder to default to libvpx-vp9 ✅ (gap-verification), so the codec is
  always passed:

  | Try | Arguments | File |
  |---|---|---|
  | 1 | `-c h264_vaapi -d /dev/dri/renderD128 -F scale_vaapi=format=nv12:out_range=full` | `.mp4`, audio `-C aac` |
  | 2 | `-c av1_vaapi -d /dev/dri/renderD128 -F scale_vaapi=format=nv12:out_range=full` | `.webm`, audio `-C libopus` |
  | 3 | `-c vp9_vaapi -d …` (same filter) | `.webm` |
  | 4 | `-c libvpx-vp9 -p deadline=realtime -p cpu-used=8 -p row-mt=1` | `.webm` |

  - A try succeeds when wf-recorder is still running after 1.5 s and the file has grown. The
    winner is cached in `~/.cache/arctic/record-codec`, keyed by the render node's driver (the
    basename of `readlink /sys/class/drm/renderD128/device/driver`).
  - 🔍 Which VA-API encoders F44's `ffmpeg-free` 8.1.2 has, and whether Mesa enables H.264 encode.
    Probe on Intel and AMD VMs or hardware.
  - With the codecs module (RPM Fusion ffmpeg), try 1 usually wins.
- **Audio**:
  - `desktop` → `--audio=<default sink node.name>.monitor`; `mic` → `--audio=<default source node.name>`.
  - The names are read with `wpctl inspect @DEFAULT_AUDIO_SINK@` / `@DEFAULT_AUDIO_SOURCE@`
    (`node.name`). `pactl` isn't installed.
  - 🔍 The device naming with wf-recorder's pulse backend on pipewire-pulse.
- **Output**: `$(xdg-user-dir VIDEOS)/Screencasts/Screencast YYYY-MM-DD HH.MM.SS.<ext>`.
- **Start**:
  1. `setsid -f wf-recorder -y -f FILE …`, with the log in `$XDG_RUNTIME_DIR/arctic/record.log`.
  2. Write `record.json`.
  3. `arctic-shell-ipc record refresh`.
- **Watchdog** (a detached loop): every 10 s it checks `df --output=avail -B1 "$dir"`. Below 1 GiB
  it stops the recording and notifies "Recording stopped: the disk is nearly full".
- **Stop**:
  1. `grim -g <geometry> <thumb.png>` takes the last frame as the thumbnail (no ffmpeg CLI needed).
  2. `kill -INT <pid>`; wait up to 5 s for wf-recorder to finish the file.
  3. Remove `record.json`.
  4. Notify "Screen recording saved": body `1 min 23 s · 14 MB`, thumbnail as the image, actions
     default=Open, Show in Files, Move to Trash.
- **Failure**: wf-recorder exits within 1.5 s on every codec → notify "Couldn't start recording" +
  the last log line.
- **Without the shell**: `toggle` shows a fuzzel menu ("Record an area / a window / the screen"),
  with no audio.
  - While recording, a persistent notification says "Recording · press Super + Alt + R to stop"
    (`-t 0`, `-h string:x-canonical-private-synchronous:arctic-record`). Stop replaces it.

#### 8.3 Deferred, with reasons

| What | Why |
|---|---|
| Desktop sound and microphone together | wf-recorder takes one audio device ✅. Mixing needs a PipeWire combine graph that isn't verified 🔍. The dialog offers None / Desktop / Microphone. Revisit with a `pw-loopback` null-sink design in 0.3.x. |
| gpu-screen-recorder | Arctic installs it as the Flathub app `com.dec05eba.gpu_screen_recorder` ✅, not an RPM. Its wlroots capture inside Flatpak and its CLI through `flatpak run --command=` are unverified 🔍. |
| Webcam overlay (Omarchy) | P3 in the research; not in the gap list. |

#### 8.4 The record dialog (`shell/RecordDialog.qml`, new) and `shell/RecordService.qml` (new singleton)

- **Dialog**: `Popover`, placement `center`, `layerName: 'arctic-record'`, card 400 px, scrim on.
  - Title "Record the screen".
  - **What**: a segmented control (the Get apps section's `shell/getapps/Segmented.qml`; if both
    need it, move it to `shell/`) with Area · Window · Screen.
  - **Sound**: None · Desktop sound · Microphone.
  - Buttons: **Cancel** (ghost) and **Start recording** (the one amber primary).
  - The last choice is kept in `~/.local/state/arctic/record.json` (`{"kind":"area","audio":"none"}`).
  - Keys: `←`/`→` inside a row, `↑`/`↓` or `Tab` between rows, `Enter` starts, `Esc` cancels.
  - Start closes the dialog, then runs `arctic-record start <kind> --audio <a> --no-dialog`.
- **RecordService** watches `record.json` with `FileView { watchChanges: true }`. It exposes
  `recording`, `startedAt`, `elapsed` (1 s `Timer` only while recording), `file`, `kind`, `audio`
  and `stop()` (`execDetached(['arctic-record','stop'])`). mode-indicators and quick settings bind
  to it. The indicator itself ("Recording 01:23" in `error` with an icon and the word) is the
  mode-indicators section's.
- **IPC**:

  ```qml
  IpcHandler {
      target: 'record'
      function open(): void { shell.openRecordDialog(); }   // arctic-record toggle, when not recording
      function refresh(): void { RecordService.refresh(); }
  }
  ```

---

### 9. Screen-share picker (`screen-share-picker`)

- **Portal config** (new `packaging/desktop/xdg-desktop-portal-wlr.ini`, installed as
  `%{_sysconfdir}/xdg/xdg-desktop-portal-wlr/mango`, `%config(noreplace)`):

  ```ini
  # Arctic Linux: the screen-share picker for Mango sessions (xdg-desktop-portal-wlr(5)).
  [screencast]
  chooser_type=simple
  chooser_cmd=/usr/libexec/arctic/arctic-share-picker
  max_fps=60
  ```

  - xdpw reads `/etc/xdg/xdg-desktop-portal-wlr/$XDG_CURRENT_DESKTOP` for each element of a
    colon-separated list, before `config` ✅ (xdpw 0.8.4 man page). Sway sessions on the same
    machine are therefore not affected.
  - 🔍 `XDG_CURRENT_DESKTOP` contains `mango` in an SDDM-started Arctic session. Check it with
    `systemctl --user show-environment`. If it doesn't, install the file as `config` instead.
- **`/usr/libexec/arctic/arctic-share-picker`** (new bash; source
  `packaging/desktop/arctic-share-picker`; added to the CI ShellCheck list):
  1. `mkfifo "$XDG_RUNTIME_DIR/arctic/share-$$.fifo"`.
  2. `arctic-shell-ipc share pick <fifo>`.
  3. Read one line with `timeout 120`, and print it. It is `Monitor: <name>` or
     `Window: <foreign_toplevel_id>`; nothing means declined ✅ (xdpw(5)).
  4. Never exit 127.
  - **Without the shell**:
    - `fuzzel --dmenu` over "Screen · eDP-1 (1920 × 1200)" lines and "Window · <app> — <title>"
      lines (windows from `arctic-capture windows`), mapped back to the xdpw strings;
    - else `slurp -f 'Monitor: %o' -or` ✅ (xdpw's own example).
  - 🔍 xdpw's service environment has `MANGO_INSTANCE_SIGNATURE` (needed by `mmsg` in the fallback).
    If it doesn't, the fallback lists screens only. The shell path runs `arctic-capture windows`
    from the shell's own environment, so it isn't affected.
- **`shell/SharePicker.qml`** (new):
  - `Popover`, placement `center`, `layerName: 'arctic-share'`, card 640 px.
  - Title "Share your screen". Lede: "An app asked to share your screen. Pick what it can see."
    xdpw passes no app name.
  - **Screens**: a card per output with a `ScreencopyView { captureSource: screen; live: false }`
    preview (`captureFrame()` on open), the output name and its size.
    - 🔍 `ScreencopyView` loads and captures on Mango with Fedora's `dacfa9d` snapshot: a
      headless-sway step and one F44 VM check.
    - If it doesn't, the cards show the `monitor` glyph instead.
  - **Windows**: rows with the app icon, title and "Workspace 2" from `arctic-capture windows`. No
    thumbnails: Quickshell captures single windows only through hyprland-toplevel-export ✅
    (gap-verification). Sharing a window still works through xdpw 0.8.4 and Mango's
    ext-image-copy-capture ✅.
  - **Share** (amber primary, enabled once something is selected) and **Cancel**.
  - Keys: arrows move within the grid and list, `Tab` moves between groups, `Enter` shares, `Esc`
    cancels. Cancel and Esc write an empty line.
  - IPC `share pick(reply: string)`.
- **Icons**: the new `monitor` glyph (§22.3). Windows use `DesktopEntries.heuristicLookup(app_id)`
  icons, falling back to `Icons.tileFor`. 🔍 `heuristicLookup` in the `dacfa9d` snapshot; if it is
  missing, match `DesktopEntries.applications` by id.
- **Privacy**: xdpw's `exec_before`/`exec_after` ✅ could feed a "Sharing screen" indicator. The
  privacy-indicators section decides whether to use them or `PwNodeLinkTracker`. This config
  leaves them out until that section asks.

---

### 10. The Capture branch of the command menu (rows; the menu engine is the command-menu section's)

`Super + Ctrl + C` opens `menu open capture`. The menu closes before an action runs, so it isn't
in the picture.

| id | Label | Glyph | Action | Guard (`when`) |
|---|---|---|---|---|
| `capture.area` | Screenshot of an area | `camera` | `arctic-screenshot area` | — |
| `capture.window` | Screenshot of a window | `camera` | `arctic-screenshot window --pick` | — |
| `capture.screen` | Screenshot of the screen | `camera` | `arctic-screenshot screen` | — |
| `capture.screens` | Screenshot of all screens | `camera` | `arctic-screenshot screen --all` | more than one output |
| `capture.delay` | Screenshot in 5 seconds | `clock` | `arctic-screenshot screen --delay 5` | — |
| `capture.edit` | Screenshot of an area, then edit | `edit` | `arctic-screenshot area --edit` | `command -v swappy \|\| command -v satty` |
| `capture.record` | Record the screen… / Stop recording | `record` | `arctic-record toggle` | label from `arctic-record status --json` |
| `capture.text` | Copy text from the screen | `scan-text` (new) | `arctic-screenshot text` | — |
| `capture.qr` | Read a QR code | `qr-code` (new) | `arctic-screenshot qr` | — |
| `capture.color` | Pick a colour | `pipette` (new) | `arctic-colorpick` | — |
| `capture.folder` | Open the Screenshots folder | `folder` | `xdg-open "$(xdg-user-dir PICTURES)/Screenshots"` | — |

The launcher gets the same rows as specials when searched ("screenshot", "record", "colour",
"text", "qr") if the command-menu section surfaces menu rows in search. Otherwise the capture menu
is reached by its key.

---

### 11. Emoji picker (`emoji-picker`, `Super + Ctrl + E`)

- **Data** (`shell/scripts/emoji-index.py`, new, standard library):
  - Reads `/usr/share/unicode/emoji/emoji-test.txt` (unicode-emoji 18.0 ✅) for the characters,
    names, groups and subgroups. Only `fully-qualified` lines are used.
  - Reads `/usr/share/unicode/cldr/common/annotations/<lang>.xml` and `annotationsDerived/<lang>.xml`
    (cldr-emoji-annotation 48.2 ✅) for keywords. The derived files are needed for skin tones and
    flags (correction applied).
  - Languages: `en` plus the language of `LANG` (for example `he`).
  - It writes `~/.cache/arctic/emoji.json` when the file is missing, the source files are newer, or
    the language changed.

  ```json
  {"version":1,"langs":["en","he"],"unicode":"18.0",
   "emoji":[{"e":"👍","name":"thumbs up","group":"People & Body","keys":["+1","hand","like","אגודל"],
             "tones":["👍🏻","👍🏼","👍🏽","👍🏾","👍🏿"]}]}
  ```

  - Tone variants are folded into their base. `--lines` prints `emoji<TAB>name keywords` for fuzzel.
- **`shell/EmojiService.qml`** (singleton): it loads the index, and runs `emoji-index.py` first when
  it is stale. It exposes `search(text)` (the `LauncherSearch.rank` ranking over name and keys),
  the recent list (`~/.local/state/arctic/emoji-recent.json`, 24 entries, most recent first) and
  the skin tone (`~/.local/state/arctic/emoji.json`).
- **`shell/EmojiPicker.qml`** (new):
  - `Popover`, placement `dock` (like the launcher), `layerName: 'arctic-emoji'`, 520 px.
  - A search field (focused); category tabs (glyphs drawn as the first emoji of each group); a
    grid of 9 columns at 36 px, drawn in Noto Color Emoji.
  - A footer with the selected emoji's name and hints: `Enter` type · `Shift + Enter` copy ·
    `Alt + 1…6` skin tone.
  - Recent first when the search is empty.
- **Launcher mode**: `:` as the first character. `LauncherSearch.mode` (`shell/LauncherSearch.js:63-69`)
  returns `{mode:'emoji', text}`. `Launcher.qml` shows up to 50 `EmojiService.search` results as
  rows ("👍 thumbs up"). Enter types; Shift + Enter copies. The launcher footer shows the hint.
- **Typing**:
  1. Close the surface.
  2. Wait until its layer is unmapped (`Timer` 120 ms after `visible` goes false).
  3. `Quickshell.execDetached(['wtype', '--', emoji])`. wtype 0.4 is in F44 ✅, and Mango creates the
     virtual keyboard manager ✅.
  - 🔍 ZWJ sequences, flags and tone modifiers typed by wtype into GTK 4 (gnome-text-editor),
    Qt 6, Chromium/Electron, kitty and foot. For any toolkit that mangles them, switch that case
    to Omarchy's method: `wl-copy --sensitive`, then paste with `wtype -M shift -k Insert -m shift`
    (terminals: Ctrl + Shift + V; see §12).
- **Copy**: `wl-copy --sensitive -- "$emoji"`, so it isn't stored in history.
- **`arctic-emoji`** (new bash helper; the bind runs it):
  - `arctic-shell-ipc emoji toggle`;
  - else `python3 "$(arctic-shell --path)/scripts/emoji-index.py" --lines | fuzzel --dmenu --prompt "Emoji  "`
    → `cut -f1` → `wtype --`.
- **IPC**: `IpcHandler { target: 'emoji'; function toggle(): void { shell.toggleEmoji(); } }`.
  `closePopovers` (`shell.qml:20-22`) lists `emoji`.
- **Packages** (arctic-shell Requires): `wtype`, `unicode-emoji`, `cldr-emoji-annotation`,
  `google-noto-color-emoji-fonts`. `iso/kiwi/config.kiwi:154` becomes
  `google-noto-color-emoji-fonts` (correction applied).

---

### 12. Clipboard panel (`clipboard-panel`, `Super + V`)

- **`shell/scripts/clipboard.py`** (new; standard library + Pillow; one JSON line per command):

  | Command | Does |
  |---|---|
  | `list` | `cliphist list`, parsed. `{"ok":true,"items":[{"id":"124","kind":"image","mime":"image/png","width":800,"height":600,"size":"12 KiB","thumb":""},{"id":"123","kind":"text","preview":"…"}],"pins":[{"pin":"p-3f2a","kind":"text","preview":"…"}]}` |
  | `thumb ID` | `cliphist decode` → Pillow 160 px thumbnail in `~/.cache/arctic/clip-thumbs/<id>.png` → `{"ok":true,"thumb":"…"}` |
  | `copy ID` / `copy-pin PIN` | `cliphist decode ID \| wl-copy` (with `--type` for images) |
  | `delete ID` | Sends the full original line to `cliphist delete` on stdin |
  | `wipe` | `cliphist wipe`; pins stay |
  | `pin ID` / `unpin PIN` | Pinned content is copied into `~/.local/state/arctic/clipboard-pins/<pin>` (0600) plus `pins.json`, so pins survive a wipe |

  🔍 cliphist 0.7.0's image preview format (`[[ binary data 12 KiB png 800x600 ]]`). The parser has
  a fixture test and treats unknown previews as text.
- **`shell/ClipboardPanel.qml`** (new):
  - `Popover`, placement `dock`, `layerName: 'arctic-clipboard'`, 520 px.
  - A search field; pins first (with the `pin` glyph), then history.
  - Image rows show the thumbnail (made lazily when the row is visible).
  - Footer hints, and a **Clear history** ghost button that opens a confirm sheet
    ("Clear clipboard history? Pinned items stay."). The destructive button uses the `error` style.
- **Keys**:
  - `↑`/`↓` move.
  - `Enter` copies and closes.
  - `Shift + Enter` copies, closes, waits for the layer to unmap, then pastes. It runs
    `wtype -M ctrl v -m ctrl`, or `wtype -M ctrl -M shift v -m shift -m ctrl` when
    `mmsg get focusing-client` shows a terminal app id (`kitty`, `foot`, `Alacritty`,
    `org.wezfurlong.wezterm`, `com.mitchellh.ghostty`).
    - 🔍 Whether the virtual keyboard's Ctrl + Shift trips `grp:ctrl_shift_toggle`. wtype uploads
      its own keymap, so it shouldn't. Test with that option on.
  - `Delete` (with the cursor at the end of the search text) removes the entry.
  - `Ctrl + P` pins or unpins.
  - `Esc` clears the search, then closes.
- **`arctic-clipboard`** (new bash helper; the bind runs it): `arctic-shell-ipc clipboard toggle`,
  else today's pipeline, moved from `binds.conf:23`.
- **IPC**: `IpcHandler { target: 'clipboard'; function toggle(): void { shell.toggleClipboard(); } }`.
- **Secrets**:
  - Arctic helpers copy secrets with `wl-copy --sensitive` (§6 QR, §11 emoji).
  - rules.conf gets `layerrule=shield_when_capture:1,layer_name:^arctic-clipboard$`, which Mango
    supports as a layer rule ✅. The panel is then left out of screencasts and screenshots.
    🔍 That it also applies to wlr-screencopy (grim): take a Print screenshot with the panel open.
- **Settings** (Keyboard and mouse page, new group "Clipboard"):
  - "Keep clipboard history" switch;
  - "Clear history" button (confirm dialog).
  - Backend: `clipboard` → `{"ok":true,"history":true,"entries":37}`;
    `clipboard-set history on|off`, which writes `~/.config/arctic/clipboard.conf` (`history=off`)
    and runs `arctic-session clipboard --restart`; `clipboard-clear` runs `cliphist wipe`.
  - `arctic-session clipboard` (`:37-39`) reads `clipboard.conf`: with `history=off` it stops the
    watcher and doesn't start it.
  - SearchIndex: `["input", "input.clipboard", "Clipboard history", "cliphist privacy clear paste"]`.

---

### 13. The shortcut sheet generated from the binds (`generated-keys-sheet`)

#### 13.1 The grammar (comments Mango ignores)

| Line | Meaning |
|---|---|
| `#@ <Section>` | Following binds in this file go in that sheet section |
| `#: <What it does>` | Describes the next bind line; the keys column is the bind's own label (`combo_label`) |
| `#: <Keys> :: <What it does>` | Also names the keys (grouped rows such as `Super + ← → ↑ ↓`, gestures, `Print or Super + Shift + S`) |
| `#-` | The next bind is covered by the row above it and isn't listed |

- A description attaches to the next `bind*`, `mousebind`, `axisbind` or `gesturebind` line.
  Blank lines and ordinary comments between them are allowed.
- **Section order** is fixed in `arctic-keys`: Everyday, Your apps, Windows, Workspaces, Capture,
  System, Hardware keys, Mouse and touchpad, then any other titles in first-seen order, then Your
  shortcuts. Rows keep the order of the config chain.
- Every Arctic bind has `#:` or `#-` (`test_every_bind_is_described`).

#### 13.2 `arctic-keys` (rewritten in Python 3, standard library; `dotfiles/.local/bin/arctic-keys`)

```
arctic-keys                         toggle the sheet (shell, else a floating kitty running `arctic-keys --sheet | less`)
arctic-keys --sheet [--arctic-only] [--config FILE]    keys.txt-format text
arctic-keys --json  [--arctic-only] [--config FILE]    JSON for the shell and Settings
```

- It follows the chain from `~/.config/mango/config.conf` (or `--config`), exactly as
  `read_chain` does, and keeps comments.
- `--arctic-only` stops at `settings.conf` and `user.conf`.
- **User binds**:
  - in `settings.conf`: `spawn_shell gtk-launch ID` → "Open <Name>" (from the desktop file's
    `Name=`); `arctic-open --focus ID` → "Open or show <Name>"; otherwise the command;
  - in `user.conf`: its own `#:` if present, else the dispatcher label, else the command;
  - all go in "Your shortcuts".
- **Shadowed binds** (§14) are listed in `shadowed`, not in the sections.
- **JSON** (camelCase field names, because Settings passes this through to its QML, which already
  uses `customBinds`, `switchKeys` and so on):

  ```json
  {"ok":true,"source":"config",
   "sections":[{"title":"Everyday","rows":[{"keys":"Super + Space","what":"Apps (press again to close)","file":"binds.conf","mine":false}]}],
   "shadowed":[{"keys":"Super + B","what":"firefox","file":"settings.conf","shadowedBy":{"keys":"Super + B","what":"Browser","file":"apps.conf"}}]}
  ```

- When the chain can't be read, it falls back to parsing `keys.txt` (`"source":"keys.txt"`), as
  `KeysSheet.qml` does today.
- **`keys.txt` becomes generated**:
  - `arctic-keys --sheet --arctic-only --config dotfiles/.config/mango/config.conf`, with `HOME`
    set so the `source=` paths resolve into `dotfiles/`, writes `dotfiles/.local/share/arctic/keys.txt`.
  - Header line and format as today: 4 spaces, keys padded to 25 (or to the key length + 2), the
    description.
  - `test_keys_txt_is_generated` fails when the checked-in file is stale. The spec still installs it
    (`:657`) for the fallback.
- **`shell/KeysSheet.qml`** (`:8-38`):
  - runs `arctic-keys --json` with `Process` when it opens; the `FileView` stays as the fallback;
  - a search field at the top (focused), filtering on keys and text;
  - Esc clears the search, then closes; `↑`/`↓` still scroll;
  - "Your shortcuts" rows show the `mine` style (`Theme.inkMuted` file name);
  - a banner row for any `shadowed` entry: "Doesn't work: Arctic uses Super + B" (`alert` glyph,
    `Theme.warning`, with the word).
- **Settings**: `cmd_binds` (`arctic_settings.py:885-894`) takes `sheet` from
  `arctic-keys --json --arctic-only` when `which('arctic-keys')`. Otherwise it uses `parse_sheet` on
  `keys.txt` as today. The shape `{title, rows:[{keys, what}]}` is unchanged, so
  `ShortcutsPage.qml:81-111` needs no change for it.

#### 13.3 The new `apps.conf` and `binds.conf`

**`dotfiles/.config/mango/arctic/apps.conf`** (whole file):

```ini
# Arctic Linux — default app shortcuts.
# The keys are fixed; which app they open is not. arctic-open reads the apps you picked in the
# installer from /etc/arctic/default-apps (and ~/.config/arctic/default-apps if you change your mind),
# so choosing foot or Firefox in the installer changes what these keys open without new bindings.
# "#@" and "#:" lines make the shortcut sheet (Super + /); see binds.conf.

#@ Your apps
#: Terminal
bind=SUPER,Return,spawn,arctic-open terminal
#: Drop-down terminal (again to hide it)
bind=SUPER+ALT,Return,toggle_named_scratchpad,org.arcticlinux.Dropdown,none,arctic-open terminal --app-id org.arcticlinux.Dropdown
#: Browser
bind=SUPER,b,spawn,arctic-open browser
#: Code editor
bind=SUPER,e,spawn,arctic-open editor
#: Files
bind=SUPER,f,spawn,arctic-open files
#: Files in the terminal (yazi)
bind=SUPER+SHIFT,f,spawn,arctic-open files-tui
```

**`dotfiles/.config/mango/arctic/binds.conf`** (whole file). Lines are regrouped by sheet section.
Moving a line within the file changes nothing for Mango (every key is distinct). Other sections'
rows 35-55 go where the comments say; they are not written out here.

```ini
# Arctic Linux — key bindings. Keyboard first, never keyboard only.
# Global shortcuts from the design: Super+Space launcher, Super+Enter terminal, Super+L lock,
# Super+I install (live session). The full list is in `arctic-keys` (Super+/).
# The arctic-* helpers drive the shell over IPC (arctic-shell-ipc) and fall back to
# fuzzel / swaylock / notifications when it isn't running (ARCTIC_SHELL=waybar).
# Flags: bindl = also works on the lock screen (media keys).
#
# The shortcut sheet (Super + /, arctic-keys, Settings > Shortcuts, keys.txt) is made from:
#   #@ Title                  the sheet section of the binds that follow
#   #: What it does           describes the next bind ("#: Keys :: What it does" names the keys too)
#   #-                        the next bind is covered by the row above
# No key uses Alt + Shift: it switches the keyboard layout on two-layout systems. Ctrl + Shift
# and Alt + Space are used once each; Settings warns when one of them is the switch key.
# settings/tests check this, that every bind is described and that no key is used twice.

keymode=common
#@ System
#: Reload the desktop config
bind=SUPER+SHIFT,r,reload_config

keymode=default

# ---- Everyday ---------------------------------------------------------------
#@ Everyday
#: Apps (press again to close)
bind=SUPER,space,spawn,arctic-launcher
#: Clipboard history
bind=SUPER,v,spawn,arctic-clipboard
#: Emoji
bind=SUPER+CTRL,e,spawn,arctic-emoji
#: Get apps (install or remove apps)
bind=SUPER+SHIFT,a,spawn,arctic-shell-ipc apps install
#: Wallpapers
bind=SUPER+SHIFT,w,spawn,arctic-shell-ipc wallpapers toggle
#: This sheet
bind=SUPER,slash,spawn,arctic-keys
# (bar section: Super + A quick settings, Super + Ctrl + A/W/B/D/P panels, Super + Ctrl + T
#  calendar, Super + Ctrl + M media, Super + Alt + P bar focus; command menu: Super + Alt + Space)

# ---- Windows ------------------------------------------------------------------
#@ Windows
#: Close
bind=SUPER,q,killclient,
#: Super + ← → ↑ ↓ :: Move focus
bind=SUPER,Left,focusdir,left
#-
bind=SUPER,Right,focusdir,right
#-
bind=SUPER,Up,focusdir,up
#-
bind=SUPER,Down,focusdir,down
#: Super + Shift + ← → ↑ ↓ :: Swap with the neighbour
bind=SUPER+SHIFT,Left,exchange_client,left
#-
bind=SUPER+SHIFT,Right,exchange_client,right
#-
bind=SUPER+SHIFT,Up,exchange_client,up
#-
bind=SUPER+SHIFT,Down,exchange_client,down
#: Super + Ctrl + ← → :: Narrower / wider main area
bind=SUPER+CTRL,Left,setmfact,-0.05
#-
bind=SUPER+CTRL,Right,setmfact,+0.05
#: Super + Ctrl + ↑ ↓ :: More / fewer main windows
bind=SUPER+CTRL,Up,incnmaster,+1
#-
bind=SUPER+CTRL,Down,incnmaster,-1
#: Swap with the main window
bind=SUPER,z,zoom,
#: Float / tile
bind=SUPER,t,togglefloating,
#: Maximise
bind=SUPER,m,togglemaximizescreen,
#: Full screen
bind=SUPER+SHIFT,m,togglefullscreen,
#: Alt + Tab :: Switch windows (Alt + ` goes back; with Super: every workspace)
bind=ALT,Tab,switcher,next
#-
bind=ALT,code:49,switcher,prev
#-
bind=SUPER+ALT,Tab,switcher,all_next
#: Super + Tab :: Next window (Shift: previous)
bind=SUPER,Tab,focusstack,next
#-
bind=SUPER+SHIFT,Tab,focusstack,prev
#: Back to the previous window
bind=SUPER,BackSpace,focuslast
#: Jump to a window by its letter
bind=SUPER,j,togglejump
#: Overview
bind=SUPER,o,toggleoverview,
#: Next layout
bind=SUPER,n,switch_layout
#: Super + H :: Hide the window (Shift: bring it back)
bind=SUPER,h,minimized
#-
bind=SUPER+SHIFT,h,restore_minimized
#: Pin a floating window to every workspace
bind=SUPER+SHIFT,p,spawn,arctic-window pin
#: Super + Alt + ← → ↑ ↓ :: Join the neighbour's tab group
bind=SUPER+ALT,Left,groupjoin,left
#-
bind=SUPER+ALT,Right,groupjoin,right
#-
bind=SUPER+ALT,Up,groupjoin,up
#-
bind=SUPER+ALT,Down,groupjoin,down
#: Super + Alt + Page Up / Down :: Previous / next tab in the group
bind=SUPER+ALT,Page_Up,groupfocus,prev
#-
bind=SUPER+ALT,Page_Down,groupfocus,next
#: Leave the tab group
bind=SUPER+ALT,g,groupleave

# ---- Workspaces and monitors ------------------------------------------------------
#@ Workspaces
#: Super + 1 … 5 :: Go to workspace
bind=SUPER,1,view,1,0
#-
bind=SUPER,2,view,2,0
#-
bind=SUPER,3,view,3,0
#-
bind=SUPER,4,view,4,0
#-
bind=SUPER,5,view,5,0
#: Super + Shift + 1 … 5 :: Move window to workspace
bind=SUPER+SHIFT,1,tag,1,0
#-
bind=SUPER+SHIFT,2,tag,2,0
#-
bind=SUPER+SHIFT,3,tag,3,0
#-
bind=SUPER+SHIFT,4,tag,4,0
#-
bind=SUPER+SHIFT,5,tag,5,0
#: Super + Page Up / Down :: Previous / next workspace
bind=SUPER,Page_Up,viewtoleft,0
#-
bind=SUPER,Page_Down,viewtoright,0
#: Super + Shift + Page Up / Down :: Move window to the previous / next workspace
bind=SUPER+SHIFT,Page_Up,tagtoleft,0
#-
bind=SUPER+SHIFT,Page_Down,tagtoright,0
#: Super + ` :: Scratch workspace over this one (Shift: move the window there)
bind=SUPER,code:49,toggle_special_tag
#-
bind=SUPER+SHIFT,code:49,tag_special_tag
# Super + , / . move focus between monitors, as in dwl (so Settings is Super + S, not Super + ,).
#: Super + , / . :: Focus the other monitor
bind=SUPER,comma,focusmon,left
#-
bind=SUPER,period,focusmon,right
#: Super + Shift + , / . :: Move window to the other monitor
bind=SUPER+SHIFT,comma,tagmon,left
#-
bind=SUPER+SHIFT,period,tagmon,right

# ---- Capture ------------------------------------------------------------------
#@ Capture
#: Print or Super + Shift + S :: Screenshot of an area
bind=NONE,Print,spawn,arctic-screenshot area
#-
bind=SUPER+SHIFT,s,spawn,arctic-screenshot area
#: Screenshot of the screen
bind=SHIFT,Print,spawn,arctic-screenshot screen
#: Screenshot of the window
bind=SUPER,Print,spawn,arctic-screenshot window
#: An area to the clipboard only
bind=CTRL,Print,spawn,arctic-screenshot area --copy-only
#: Copy text from the screen
bind=SUPER+CTRL,Print,spawn,arctic-screenshot text
#: Pick a colour
bind=SUPER+SHIFT,c,spawn,arctic-colorpick
#: Super + Alt + R or Alt + Print :: Record the screen (again to stop)
bind=SUPER+ALT,r,spawn,arctic-record toggle
#-
bind=ALT,Print,spawn,arctic-record toggle
# (command menu: Super + Ctrl + C capture menu)

# ---- System -------------------------------------------------------------------
#@ System
#: Lock
bind=SUPER,l,spawn,arctic-lock
#: Power menu
bind=SUPER,Escape,spawn,arctic-power
#: Settings
bind=SUPER,s,spawn,arctic-settings
#: Install Arctic Linux (live USB)
bind=SUPER,i,spawn,arctic-start-installer
#: Super + Delete :: Dismiss notification (Shift: all)
bind=SUPER,Delete,spawn,makoctl dismiss
#-
bind=SUPER+SHIFT,Delete,spawn,makoctl dismiss --all
#: Do not disturb
bind=SUPER+SHIFT,n,spawn,arctic-dnd toggle
#: Switch Winter / Polar night
bind=SUPER+SHIFT,t,spawn,arctic-theme toggle
# (notifications: Super + Alt + N; modes: Super + Ctrl + N, Super + Ctrl + I; Super + P display
#  mode; Super + Alt + K keyboard pointer; Super + Ctrl + S share; Super + Ctrl + R reminder;
#  Ctrl + Shift + Esc activity)

# ---- Hardware keys (the bindl ones work on the lock screen too) ------------------
#@ Hardware keys
#: Volume keys :: Volume (with the on-screen display)
bindl=NONE,XF86AudioRaiseVolume,spawn,arctic-osd volume up
#-
bindl=NONE,XF86AudioLowerVolume,spawn,arctic-osd volume down
#: Mute key :: Mute or unmute
bindl=NONE,XF86AudioMute,spawn,arctic-osd volume mute
#: Microphone key :: Microphone off / on
bindl=NONE,XF86AudioMicMute,spawn,arctic-osd mic mute
#: Brightness keys :: Screen brightness
bindl=NONE,XF86MonBrightnessUp,spawn,arctic-osd brightness up
#-
bindl=NONE,XF86MonBrightnessDown,spawn,arctic-osd brightness down
#: Keyboard light keys :: Keyboard backlight
bindl=NONE,XF86KbdBrightnessUp,spawn,arctic-osd kbd up
#-
bindl=NONE,XF86KbdBrightnessDown,spawn,arctic-osd kbd down
#: Play/Pause, Next, Previous :: Music and video
bindl=NONE,XF86AudioPlay,spawn,playerctl play-pause
#-
bindl=NONE,XF86AudioNext,spawn,playerctl next
#-
bindl=NONE,XF86AudioPrev,spawn,playerctl previous
#: Touchpad key :: Touchpad off / on
bind=NONE,XF86TouchpadToggle,spawn,arctic-touchpad toggle
#-
bind=NONE,XF86TouchpadOn,spawn,arctic-touchpad on
#-
bind=NONE,XF86TouchpadOff,spawn,arctic-touchpad off
#: Calculator key :: Calculator in the launcher
bind=NONE,XF86Calculator,spawn,arctic-launcher =
#: Search key :: Launcher
bind=NONE,XF86Search,spawn,arctic-launcher
#: Power button :: Power menu
bind=NONE,XF86PowerOff,spawn,arctic-power
# (audio: Shift + Mute next output)

# ---- Mouse and touchpad -----------------------------------------------------
#@ Mouse and touchpad
#: Super + drag :: Move (left button) / resize (right button)
mousebind=SUPER,btn_left,moveresize,curmove
#-
mousebind=SUPER,btn_right,moveresize,curresize
#: Super + scroll :: Previous / next workspace with windows
axisbind=SUPER,UP,viewtoleft_have_client
#-
axisbind=SUPER,DOWN,viewtoright_have_client
#: 3 fingers :: Move focus
gesturebind=none,left,3,focusdir,left
#-
gesturebind=none,right,3,focusdir,right
#-
gesturebind=none,up,3,focusdir,up
#-
gesturebind=none,down,3,focusdir,down
#: 4 fingers ← → :: Previous / next workspace
gesturebind=none,right,4,viewprev_have_client
#-
gesturebind=none,left,4,viewnext_have_client
#: 4 fingers ↑ ↓ :: Overview
gesturebind=none,up,4,enteroverview
#-
gesturebind=none,down,4,leaveoverview
```

- `Super + Delete` / `Super + Shift + Delete` keep their `makoctl` commands until the notifications
  section swaps them for `arctic-notify` (row 43).
- The "Get apps" text is the Get apps section's wording (its `keys.txt:11` edit moves into this
  `#:` line).
- 🔍 `mango -p` accepts `code:49` keys, `switcher`, `groupjoin`, `groupfocus`, `togglejump`,
  `focuslast`, `toggle_special_tag`, `tag_special_tag` and the named-scratchpad line. The spec's
  `%check` runs `mango -c config.conf -p` when mango is in the build root (`:886-897`); run
  `tools/build-rpms.sh` once before merging.
- 🔍 `ALT,code:49` and `SUPER,code:49` fire on `us`, `us,il` (both groups active) and `de` (dead grave
  key). Check with the F44 VM and `Super + Shift + R`.

---

### 14. Shadowed binds (missed gap: new default binds silently override users' own)

#### 14.1 Detection (`settings/scripts/arctic_settings.py`)

- **`chain_binds`** (`:838-866`) gains a second pass. For each bind *i*, find the first earlier
  bind *j* with the same combo in the same keymode, or with either one in `common`. When one exists,
  set `out[i]['shadowedBy'] = {label, what, file: basename}`.
  - Combo = `(frozenset(mods), key)`, with `key.lower()` and `code:49` ≡ `grave`.
  - Flags matter:
    - a bind whose name has `c` (for example `bindc`) never shadows;
    - an `r` (release) bind and a press bind don't shadow each other;
    - `l` and `s` don't change the matching.
  - The flags come from the key: `bind`, `bindl`, `bindr`, `bindlr`, …
- **`cmd_binds`** (`:885-894`):
  - each `mine` entry gets `shadowedBy`, matched to its chain entry by `(mods, key, command)`;
  - the response gains `shadowed`: every shadowed bind that isn't in Arctic's own files
    (`settings.conf`, `user.conf`, anything else sourced), as
    `{label, what, file, shadowedBy}`.
- **`DISPATCHERS`** (`:792-802`) gains labels for every dispatcher Arctic now binds (correction
  from gap-verification):
  - `switcher`: "Switch windows";
  - `togglejump`: "Jump to a window";
  - `focuslast`: "Back to the previous window";
  - `toggle_special_tag`: "Scratch workspace";
  - `tag_special_tag`: "Move the window to the scratch workspace";
  - `toggle_named_scratchpad`: "Drop-down window";
  - `minimized`: "Hide the window";
  - `restore_minimized`: "Bring back a hidden window";
  - `groupjoin`: "Join a tab group";
  - `groupfocus`: "Next / previous tab in the group";
  - `groupleave`: "Leave the tab group";
  - `toggleglobal`: "Show the window on every workspace";
  - `centerwin`: "Centre the window";
  - `toggle_trackpad_enable`: "Touchpad on / off";
  - `toggle_scratchpad`: "Show hidden windows";
  - `setlayout`: "Layout".

  `test_arctic_dispatchers_have_labels` keeps it complete.
- **`KEY_NAMES`** (`:786-791`) gains an entry that labels `code:49` with the backtick character.
  `backspace` is already there, and XF86 keys are named by the existing rule (`:828-829`).

#### 14.2 Settings > Shortcuts (`settings/pages/ShortcutsPage.qml`)

- **Banner** at the top of the page (`ArBanner`, tone warning, `alert` glyph) when
  `binds.shadowed.length > 0`:
  - title "N of your shortcuts don't work";
  - body: "Arctic uses Super + B for your browser now, so your own Super + B doesn't run. Remove it and
    add it on another key." The first shadow's text is used, "and N more" is added, and user.conf
    ones get "It's in ~/.config/mango/user.conf.".
- **Your shortcuts rows** (`:49-72`): when `modelData.shadowedBy` is set, `desc` becomes
  "Doesn't work: Super + B opens your browser now." in `Theme.warning` with the `alert` glyph (a
  status carries an icon and a word). The command moves to the tooltip.
- **Raw list** (`:126-143`): the desc gains " · doesn't run (Super + B is Browser in apps.conf)".
- **`:35`** gains: "Arctic's own shortcuts come first: if Arctic later uses one of your keys,
  this page tells you."
- **`bind-add`** stays as it is: it already refuses keys Arctic uses (`:926-931`). With the new
  binds, `Super + B`, `Super + Shift + S`, `Alt + Tab` and the rest are refused, and `Super + W` is
  accepted.

#### 14.3 At login: `arctic-settings --check-binds`

- **autostart.conf** gets `exec-once=arctic-settings --check-binds`. It does nothing if Settings
  isn't installed. The file is shared with the notifications and modes sections.
- `dotfiles/.local/bin/arctic-settings` gains `--check-binds`:
  1. `sleep 8`, so the notification server is up;
  2. `python3 "$dir/scripts/arctic_settings.py" notices`;
  3. one `notify-send` per notice, detached, with its action.
  - It is skipped on the live USB (`arctic-is-live`).
- **Backend `notices`** (read-only for settings files; it writes only
  `~/.local/state/arctic/notices.json`). It returns
  `{"ok":true,"notices":[{"id":"…","summary":"…","body":"…","action":"arctic-settings shortcuts","actionLabel":"Open Shortcuts"}]}`
  and marks each notice as shown:

  | id | When | Text |
  |---|---|---|
  | `keys-0.3.0` | once per account | "Super + B opens your browser" / "It was Super + W. Super + Shift + S takes a screenshot, and Super + / shows every shortcut." → action `arctic-keys` "Show shortcuts" |
  | `shadowed-<hash>` | the set of shadowed user binds changed since the last notice and isn't empty | "A shortcut of yours doesn't work" / "Super + B now opens your browser, so your own Super + B (firefox) doesn't run. Pick another key." → `arctic-settings shortcuts` |
  | `copied-<file>-0.3.0` | `~/.config/mango/arctic/{apps,binds}.conf` is a regular file (not a link) that differs from `/usr/share/arctic/mango/<file>` | "Your copy of binds.conf doesn't have the new shortcuts" / "You replaced Arctic's binds.conf with your own copy, so 0.3.0's keys (Super + B browser, Super + Shift + S screenshot, Alt + Tab) aren't in it." → `xdg-open /usr/share/arctic/mango/binds.conf` "Show the new file" |

- **`docs/BUILD-SPEC.md` §3** (the autostart list at `:95-99`) names `arctic-settings --check-binds`.

---

### 15. Layout switch vs Alt + Shift (missed gap)

1. **Arctic's own keys** avoid Alt + Shift entirely (§3.1.2). A test enforces it.
2. **Settings warns** when the chosen switch key clashes:
   - `cmd_keyboard_data` (`arctic_settings.py:2079`) adds
     `switchClashes: {"grp:ctrl_shift_toggle": ["Ctrl + Shift + Esc (Activity)"], "grp:alt_space_toggle": ["Super + Alt + Space (Command menu)"]}`,
     computed from `chain_binds`, so users' binds are included.
   - `SWITCH_CHORDS` (new) maps each option to `(mods ⊆ bind mods, key or None)`:
     - `alt_shift` / `lalt_lshift` → `({ALT,SHIFT}, None)`;
     - `ctrl_shift` → `({CTRL,SHIFT}, None)`;
     - `alt_space` → `({ALT}, 'space')`;
     - `caps` / `alt_caps` → `(…, 'caps_lock')`;
     - `shifts` and `toggle` → none (warning text only).
   - `InputPage.qml` "Switch layouts with" row (`:130-141`): under the select, when
     `kb.switchClashes[switchKey]` isn't empty, show `ArText` (`Theme.warning`, `alert` glyph):
     "Also switches the layout: Ctrl + Shift + Esc (Activity)."
   - With `grp:toggle` selected: "Right Alt switches layouts, so Alt shortcuts use the left Alt."
3. **Settings refuses user binds** that contain the active chord. When `xkb_rules_layout` has two
   or more layouts, `cmd_bind_add` raises "Alt + Shift switches your keyboard layout, so this
   shortcut would switch it too. Pick another key, or change “Switch layouts with” on the Keyboard
   and mouse page."
4. **The shadow check** (§14) also runs over users' existing binds with such chords and lists them in
   the banner, with the text "switches the layout too".
5. **Deferred, with a test to settle it.** Two ways could remove the clash itself:
   - a Mango release bind such as `bindr=ALT+SHIFT,Shift_L,switch_keyboard_layout` instead of the xkb
     option (keys.md "Single Modifier Key Binding" ✅);
   - libxkbcommon's `lockOnRelease` with V2 keymaps. F44 has libxkbcommon 1.13.1 ✅ (≥ 1.11), but
     Mango/wlroots compile V1 keymaps.

   🔍 Test the first on Mango 0.17.3 with `us,il`. Hold Alt + Shift, press Tab, release: does the
   release bind still fire? If it doesn't, the installer (`internal/wizard/locale.go:153`), Settings
   (`InputPage.qml:36`), the login screen and the console would all need to change. That touches Go
   and SDDM and is a 0.3.x follow-up, not 0.3.0.
6. **Docs**: Keyboard-Shortcuts.md "In the installer" (`:141`) and a new "Keyboard layouts"
   paragraph: "Alt + Shift switches layouts, so no Arctic shortcut uses Alt + Shift."

---

### 16. Compose key (missed gap)

- **Settings > Keyboard and mouse**, new row "Compose key" after "Caps Lock key" (`InputPage.qml:142-153`):
  - an `ArSelect` with Off, Right Alt (`compose:ralt`), Menu (`compose:menu`), Right Ctrl
    (`compose:rctrl`), Caps Lock (`compose:caps`) and Scroll Lock (`compose:sclk`);
  - labels from `evdev.lst` where present;
  - desc "Press it, then two keys: ' then e types é, o then c types ©."
- `InputPage.save(list, sw, caps)` becomes `save(list, sw, caps, compose)`. It keeps the rest of
  `xkb_rules_options` as today (`:33-47`). `RE_XKBOPT` (`arctic_settings.py:341`) already accepts
  `compose:*`.
- **Exclusions** in the UI:
  - Compose on Caps Lock clears the Caps Lock option, disables that row ("Caps Lock is your Compose
    key."), and removes `grp:caps_toggle` / `grp:alt_caps_toggle` from the switch choices.
  - Compose on Right Alt removes `grp:toggle`. When the layouts include one that types with AltGr
    (`de fr es it pl pt se no dk fi cz sk hu ro tr ch be br ca`, or a variant containing `intl` or
    `altgr`), the row warns: "German types some characters with Right Alt; pick Menu or Right Ctrl."
  - A user bind on the chosen key (for example `Menu`, which `FREE_KEYS` allows alone,
    `arctic_settings.py:804`) is listed as clashing.
- `cmd_keyboard_data` returns `composeKeys` like `capsOptions`. `COMPOSE_OPTIONS` (new, next to
  `CAPS_OPTIONS` at `:2055`).
- **No `~/.XCompose` is shipped** (the deferred part, with a reason): the emoji picker (§11) covers
  Omarchy's compose snippets, and a wrong `include` in a shipped file would replace the locale's
  compose table for everyone. The wiki shows how to add one. GTK 4 reads `~/.XCompose`; Qt and
  Chromium read it through libxkbcommon.
- SearchIndex: `["input", "input.compose", "Compose key", "special characters accents multi key"]`.

---

### 17. Hardware keys (`hardware-keys`)

| Key | Bind | Behaviour |
|---|---|---|
| Keyboard light up / down | `bindl=NONE,XF86KbdBrightnessUp,spawn,arctic-osd kbd up` (and down) | `brightnessctl --device='*::kbd_backlight'` (wildcards allowed ✅). The step is `+1` raw when the max is ≤ 10, else 10 %. No such device → exit 0. The shell OSD shows it with the `keyboard` glyph. |
| Touchpad toggle / on / off | `bind=NONE,XF86TouchpadToggle,spawn,arctic-touchpad toggle` (+ On/Off) | `mmsg dispatch setoption,disable_trackpad,<0\|1>` (correction applied: keep the state in the helper). The state lives in `$XDG_RUNTIME_DIR/arctic/touchpad` and starts from the chain's `disable_trackpad` (Settings writes it, `InputPage.qml:316-324`). OSD "Touchpad off" / "Touchpad on" (icon-and-label kind). |
| Calculator | `bind=NONE,XF86Calculator,spawn,arctic-launcher =` | The launcher in `=` mode. wordexp splits the argument ✅. |
| Search | `bind=NONE,XF86Search,spawn,arctic-launcher` | The launcher |
| Power button | `bind=NONE,XF86PowerOff,spawn,arctic-power` | The power menu (toggle). |
| Mic mute | unchanged key | The shell OSD shows it (`arctic-shell-ipc osd mic`); the notification is the fallback only. |

- **Power button and logind** (correction applied: an inhibitor is valid; Omarchy uses a logind
  drop-in instead):
  - New `shell/PowerKeyService.qml` (singleton) runs
    `Process { command: ['systemd-inhibit','--what=handle-power-key','--mode=block','--who=Arctic shell','--why=Shows the power menu','cat']; stdinEnabled: true }`.
  - It runs while the shell is up and the screen isn't locked: `running: holding`, with
    `Binding { target: PowerKeyService; property: 'holding'; value: !lockScreen.secure }` in
    `shell.qml` (a singleton can't see the `lockScreen` id).
  - `cat` reads the shell's pipe. If the shell dies, `cat` gets EOF, the lock is released, and
    logind's `HandlePowerKey` applies again. A `sleep infinity` would leak the lock.
  - While locked, logind's default applies (Fedora: power off), as today.
  - polkit allows `inhibit-handle-power-key` for active sessions ✅.
  - 🔍 The ACPI power button reaches Mango as `XF86PowerOff`. Omarchy binds it, which suggests yes;
    check with `wev` on hardware.
- **`dotfiles/.local/bin/arctic-osd`**:
  - `kbd up|down` added;
  - `mic mute` (`:36-40`) tries `arctic-shell-ipc osd mic` first;
  - `:55` passes `kbd` too;
  - usage text updated.
- **`dotfiles/.local/bin/arctic-touchpad`** (new bash, `on|off|toggle|status`).
- **`shell/Osd.qml`**:
  - `showKeyboard()` reads `brightnessctl --device='*::kbd_backlight' -m`, like `showBrightness()`;
  - `showMic()` reads `AudioService`'s default source (add `source`, `sourceMuted`, `sourceVolume`
    to `AudioService.qml`; the audio section may add the same, so coordinate);
  - `showTouchpad(on)` uses the icon-and-label kind from `osd-kinds` if that has landed, else a
    minimal label pill here.
- **IPC** `osd`: `keyboard()`, `mic()`, `touchpadOn()`, `touchpadOff()`.
- Settings > Power and lock (`PowerPage.qml:90-94`, read-only lid text): add "Power button: opens
  the power menu" (read-only).

---

### 18. Alt + Tab, jump and the previous window (`alt-tab-switcher` + missed gap)

- **Binds** (rows 10-14): `Alt + Tab` next, `` Alt + ` `` prev (`code:49`, the key above Tab on
  every layout), `Super + Alt + Tab` everywhere, `Super + J` jump, `Super + Backspace` last window.
  `Super + Tab` stays `focusstack`.
- **Alt + Shift + Tab is not bound** (correction applied). Its layout flip happens whether or not
  it is bound. Not binding it means Arctic doesn't tell people to press it.
- **Look**:
  - Tiles use `focuscolor`/`bordercolor`, which are already themed
    (`design/themegen/templates/mango-colors.conf.tmpl:4-5`).
  - The switcher panel colour is hard-coded dark in Mango (`switcher.c:499`, `{0.09,0.09,0.11,0.92}`
    ✅). It is **not** patched in 0.3.0. That would need a fork patch in `packaging/mangowm.spec` and
    a config key that unpatched Mango builds reject in `mango -p`. The item is marked deferred:
    file an upstream request for a `switcher_panel_color` option and theme it once it exists. D9
    covers Arctic's own surfaces; this panel is Mango's.
  - The switcher has no animation code ✅, so reduced motion is moot.
- **Jump labels**: `jump_labels` stays Mango's default (letters resolve across layouts ✅). Colours
  come from themegen, added to `mango-colors.conf.tmpl`:
  - `jump_label_decorate_bg_color=0x{{surface-raised|nohasha}}`
  - `jump_label_decorate_fg_color=0x{{ink|nohasha}}`
  - `jump_label_decorate_border_color=0x{{line-strong|nohasha}}`
  - `jump_label_decorate_focus_bg_color=0x{{accent-soft|nohasha}}` (the current window = "here")
  - `jump_label_decorate_focus_fg_color=0x{{accent-text|nohasha}}`

  `look.conf` sets `jump_label_decorate_font_desc=Figtree Bold 14`,
  `jump_label_decorate_corner_radius=6`, `jump_label_decorate_padding_x=8`,
  `jump_label_decorate_padding_y=4` and `jump_label_decorate_border_width=1`. All ten keys are in
  `settings/tests/mango-0.17.3-keys.txt:149-159` ✅. 🔍 The colour format (`0xRRGGBBAA`) and
  `font_desc` syntax: `mango -p` plus a look at `togglejump`.
- 🔍 `focuslast` semantics ("focus the previously active window", keys.md:126 ✅) across
  workspaces: does it switch the tag? Test with two workspaces.

---

### 19. Scratch workspace and drop-down terminal (`dropdown-terminal`)

- **Binds**:
  - rows 15-16: `` Super + ` `` → `toggle_special_tag`; `` Super + Shift + ` `` → `tag_special_tag`;
  - row 17: `Super + Alt + Enter`, the named scratchpad `org.arcticlinux.Dropdown`.
- **`arctic-open terminal --app-id ID` without `-e`** opens the terminal's shell with that app id.
  The Get apps section adds `--app-id` (its §6.11) for `-e` commands; this section needs it to work
  without `-e` too. That is a shared edit to the same parser (`arctic-open:26-41`).
- **`rules.conf`** ("Arctic apps", after `:43`):
  `windowrule=isnamedscratchpad:1,appid:^org\.arcticlinux\.Dropdown$`. The size comes from
  `look.conf`.
- **`look.conf`** (new block after the overview block `:81-83`):

  ```ini
  # Scratch workspace (Super + `) and drop-down terminal (Super + Alt + Enter).
  special_dim=0.4
  special_gappih=8
  special_gappiv=8
  special_gappoh=32
  special_gappov=32
  scratchpad_width_ratio=0.8
  scratchpad_height_ratio=0.6
  ```

  - `single_scratchpad` stays Mango's default 1. Showing the drop-down hides other scratchpads,
    including windows hidden with `Super + H` (correction noted). Keys.txt says "Super + Shift + H
    brings a hidden window back".
  - 🔍 The ratios apply to named scratchpads without `width:`/`height:` in the rule. Open the
    drop-down on a 1920×1080 VM.
- `scratchpadcolor` is already themed (`mango-colors.conf.tmpl:8`).

---

### 20. Window extras (`window-extras`)

- **Hide** (`Super + H` / `Super + Shift + H`): Mango's `minimized` sends the window to the
  scratchpad pool ✅ (scratchpad.md). There is no taskbar, so the sheet names the way back.
- **Pin** (`Super + Shift + P`): new `dotfiles/.local/bin/arctic-window` (bash + inline Python for
  JSON), `pin`:
  - reads `mmsg get focusing-client`;
  - if it is floating **and** global → `togglefloating` + `toggleglobal` (unpin);
  - otherwise it toggles only the missing ones, then `centerwin`;
  - `mmsg dispatch <func>` ✅.
  - Plain toggles in a `spawn_shell` line (the gap proposal) would leave a half-pinned window when
    it was already floating.
  - 🔍 `is_floating` / `is_global` field names (§5.3).
- **Groups** (`Super + Alt + arrows`, `Super + Alt + G`, `Super + Alt + Page Up/Down`):
  - Mango draws a tabbed group bar ✅ (gap-verification: `mango_group_bar_create`).
  - Themed through `mango-colors.conf.tmpl`:
    - `group_bar_decorate_bg_color=0x{{surface|nohasha}}`
    - `group_bar_decorate_fg_color=0x{{ink-muted|nohasha}}`
    - `group_bar_decorate_border_color=0x{{line|nohasha}}`
    - `group_bar_decorate_focus_bg_color=0x{{surface-raised|nohasha}}`
    - `group_bar_decorate_focus_fg_color=0x{{ink|nohasha}}`
  - `look.conf`: `group_bar_height=28`, `group_bar_decorate_font_desc=Figtree 10`,
    `group_bar_decorate_corner_radius=6`, `group_bar_decorate_padding_x=10`,
    `group_bar_decorate_padding_y=4`, `group_bar_decorate_border_width=1`. The keys are in
    `mango-0.17.3-keys.txt:106-116` ✅.
  - The focused tab isn't amber: the window border already carries focus.
- **Hot corner**: Settings > Windows, "Focus" group (`WindowsPage.qml:213-252`), new row "Hot
  corner opens the overview":
  - a switch (`enable_hotarea`) plus a select Top left / Top right / Bottom left / Bottom right
    (`hotarea_corner` 0-3; Mango's default is 2 ✅ overview.md);
  - Arctic's default stays off. `OPTIONS` (`arctic_settings.py:298-330`) gains
    `'enable_hotarea': B + (0,)` and `'hotarea_corner': ('int', 0, 3, 2)`;
  - both keys are in `mango-0.17.3-keys.txt:81,124` ✅;
  - SearchIndex `["windows", "windows.hotcorner", "Hot corner", "overview corner mouse"]`.
- **Layout chip** (bar):
  - new `shell/LayoutChip.qml`, placed in `Bar.qml` after the workspaces. It shows only when the
    focused monitor's layout isn't `tile` (calm bar);
  - glyph `tiling` plus the name ("Scroller");
  - a click opens a small `Popover` (placement `point`) listing `LAYOUTS`, the same list as
    `arctic_settings.py:335-337`, with the current one checked (`accentSoft` + `accentEdge` + check).
    Enter/click runs `mmsg dispatch setlayout,<name>`;
  - `Super + N` (`switch_layout`) also shows an OSD with the layout name (icon-and-label kind);
  - data: `shell/scripts/workspaces.py focus` (`mango_focus`, `:73-86`) adds
    `"layouts":{"eDP-1":"tile"}` from `mmsg watch all-monitors`, and emits when the focused name
    or any layout changes (today only a name change emits, `:80-82`) (`layout_symbol` or `layout_name`
    🔍 field; gap-verification saw `layout_symbol` and `layout_index`). `Outputs.qml` exposes
    `layouts`;
  - `Bar.qml` and `workspaces.py` are shared with the bar and keyboard-layout sections.

---

### 21. Launch-or-focus (`launch-or-focus`)

**`dotfiles/.local/bin/arctic-open`** gains:

```
arctic-open --focus ROLE|DESKTOP-ID     bring back its window if one is open, else open it
arctic-open --raise-title TITLE         focus the window with this exact title; exit 1 if none
```

- **App ids to match**:
  - ROLE → its configured command (the resolution at `:51-56`). For `gtk-launch ID`, the ids are the
    desktop file's `StartupWMClass=`, `ID`, and the part after the last dot, lower-cased. For a bare
    command they are `basename argv0`.
  - DESKTOP-ID → the same, launched with `gtk-launch DESKTOP-ID`.
- **Find**: `mmsg get all-clients` → the first client whose `appid` or `app_id` (case-insensitive)
  is in the set → `mmsg dispatch focusid client,<id>` ✅ (keys.md:121) → exit 0. No match, or no
  `mmsg` → launch as today.
- The code moves here from `arctic-settings:48-59`. `arctic-settings` then calls
  `arctic-open --raise-title "Arctic Settings"`.
- 🔍 `focusid` switches to the client's workspace when it is on another one; `arctic-settings`
  relies on this today. Test with Settings on workspace 2.
- 🔍 Zen's and other Flatpak browsers' Wayland app ids (for example `zen` vs `app.zen_browser.zen`).
  The set-based match covers both; check with `mmsg get all-clients`.
- **The default keys keep launching a new window.** `Super + B` / `E` / `F` / `Enter` don't change
  behaviour.
- **Settings > Shortcuts, "Or pick an app to open"** (`ShortcutsPage.qml:266-271`, `:296-310`): an
  `ArCheck` "If it's open, bring its window back" (on by default) writes `arctic-open --focus <id>`
  instead of `gtk-launch <id>`.
- **Web apps**: `arctic-webapp run` is already launch-or-focus (web-app section §8.3). A user bind
  can use either form.

---

### 22. File-by-file changes

#### 22.1 New files

| Path | What |
|---|---|
| `dotfiles/.local/bin/arctic-capture` | Python capture engine (§5.3), ~550 lines |
| `dotfiles/.local/bin/arctic-colorpick` | bash front end (§7) |
| `dotfiles/.local/bin/arctic-record` | bash recorder (§8.2) |
| `dotfiles/.local/bin/arctic-clipboard` | bash: IPC, else fuzzel (§12) |
| `dotfiles/.local/bin/arctic-emoji` | bash: IPC, else fuzzel + wtype (§11) |
| `dotfiles/.local/bin/arctic-touchpad` | bash (§17) |
| `dotfiles/.local/bin/arctic-window` | bash, `pin` (§20) |
| `dotfiles/.config/swappy/config` | §5.7 |
| `packaging/desktop/arctic-share-picker` | xdpw chooser → `/usr/libexec/arctic/arctic-share-picker` (§9) |
| `packaging/desktop/xdg-desktop-portal-wlr.ini` | → `/etc/xdg/xdg-desktop-portal-wlr/mango` (§9) |
| `design/themegen/templates/capture-colors.env.tmpl` | §5.8 |
| `design/icons/{pipette,scan-text,qr-code,smile,clipboard,monitor,pin}.svg` | §22.3 |
| `shell/CaptureOverlay.qml`, `shell/CaptureSurface.qml` | §5.4, §7 |
| `shell/SharePicker.qml` | §9 |
| `shell/RecordDialog.qml`, `shell/RecordService.qml` | §8.4 |
| `shell/EmojiPicker.qml`, `shell/EmojiService.qml` | §11 |
| `shell/ClipboardPanel.qml` | §12 |
| `shell/PowerKeyService.qml` | §17 |
| `shell/LayoutChip.qml` | §20 |
| `shell/scripts/emoji-index.py`, `shell/scripts/clipboard.py` | §11, §12 |
| `shell/tests/test_capture.py`, `test_keys.py`, `test_emoji_index.py`, `test_clipboard.py` | §25 |
| `shell/tests/fixtures/` (emoji-test subset, CLDR XML subset, `qr.png`, PPM frames, mmsg JSON) | §25 |

#### 22.2 Changed files

| Path | Change |
|---|---|
| `dotfiles/.config/mango/arctic/apps.conf` | Whole file §13.3 (Super + B, drop-down, `#:` lines) |
| `dotfiles/.config/mango/arctic/binds.conf` | Whole file §13.3 |
| `dotfiles/.config/mango/arctic/look.conf` | Scratch/special block (§19), jump-label and group-bar options (§18, §20) |
| `dotfiles/.config/mango/arctic/rules.conf` | `:15` regex gains `capture\|share\|record\|emoji\|clipboard` (`^arctic-(frame\|…\|capture\|share\|record\|emoji\|clipboard)$`); new `layerrule=shield_when_capture:1,layer_name:^arctic-clipboard$`; drop-down rule after `:43`; the comment at `:19-21` says slurp's `selection` layer is the fallback only |
| `dotfiles/.config/mango/arctic/autostart.conf` | `exec-once=arctic-settings --check-binds` |
| `dotfiles/.local/bin/arctic-screenshot` | §5.2 |
| `dotfiles/.local/bin/arctic-keys` | Rewritten in Python (§13.2) |
| `dotfiles/.local/bin/arctic-open` | `--focus`, `--raise-title` (§21); `--app-id` without `-e` (§19; shared with the Get apps section) |
| `dotfiles/.local/bin/arctic-settings` | `--check-binds` (§14.3); `:48-59` → `arctic-open --raise-title` |
| `dotfiles/.local/bin/arctic-osd` | `kbd`, `mic` via IPC (§17) |
| `dotfiles/.local/bin/arctic-session` | `clipboard` reads `clipboard.conf`, `--restart` (§12) |
| `dotfiles/.local/bin/arctic-shell-ipc:6-8` | Targets: `capture select\|cancel\|active · share pick · record open\|refresh · emoji toggle · clipboard toggle · osd …\|keyboard\|mic\|touchpadOn\|touchpadOff` |
| `dotfiles/.local/share/arctic/keys.txt` | Generated (§13.2) |
| `dotfiles/install.sh:36-42` | `PACKAGES` adds `wtype swappy wf-recorder tesseract tesseract-langpack-eng python3-zxing-cpp unicode-emoji cldr-emoji-annotation google-noto-color-emoji-fonts fontawesome-6-free-fonts` |
| `dotfiles/README.md` | Helper table `:61-85` rows for every new helper; `:79` "`Print` or `Super + Shift + S`, `Shift + Print`, `Super + Print`, `Ctrl + Print`"; `:139-140` (§4) |
| `design/themegen/templates/mako.ini.tmpl` | `on-button-middle=exec makoctl menu …` (§5.6) |
| `design/themegen/templates/mango-colors.conf.tmpl` | Jump-label and group-bar colours (§18, §20) |
| `dotfiles/.config/arctic/themes/{winter,polar-night}/*` | Regenerated (`python3 design/tools/gen-desktop-themes.py`) |
| `shell/shell.qml` | Header `:7-15`; `closePopovers` `:20-22` adds `emoji, clipboard, recordDialog`; `toggleEmoji`, `toggleClipboard`, `openRecordDialog`; components after `:81` (`CaptureOverlay { id: capture }`, `SharePicker { id: sharePicker }`, `RecordDialog { id: recordDialog }`, `EmojiPicker { id: emoji }`, `ClipboardPanel { id: clipboard }`); IPC handlers `capture`, `share`, `record`, `emoji`, `clipboard`; `osd` (`:113-117`) gains four functions |
| `shell/qmldir` | `EmojiService`, `RecordService`, `PowerKeyService` singletons |
| `shell/KeysSheet.qml` | §13.2 |
| `shell/Launcher.qml` | `:` emoji mode rows and footer hint |
| `shell/LauncherSearch.js:63-69` | `:` → `{mode:'emoji'}` |
| `shell/Osd.qml` | §17 |
| `shell/AudioService.qml` | Default source (coordinate with the audio section) |
| `shell/Outputs.qml`, `shell/scripts/workspaces.py` | `layouts` (§20) |
| `shell/Bar.qml` | `LayoutChip` (§20) |
| `shell/README.md` | IPC table `:74-86`; files table |
| `shell/assets/design-data.js` | The seven new `ICONS` bodies (sorted), also added to the design bundle (§22.3) |
| `settings/scripts/arctic_settings.py` | `:1793` Super + B; `DISPATCHERS`, `KEY_NAMES`; `chain_binds` `shadowedBy`; `cmd_binds` `shadowed` + `arctic-keys` sheet; `cmd_bind_add` layout-chord refusal; `SWITCH_CHORDS`, `COMPOSE_OPTIONS`, `cmd_keyboard_data` (`switchClashes`, `composeKeys`); `OPTIONS` `enable_hotarea`, `hotarea_corner`; new commands `notices`, `clipboard`, `clipboard-set`, `clipboard-clear` (`COMMANDS` `:2546`; the last two in `WRITERS` `:2567`) |
| `settings/pages/ShortcutsPage.qml` | Banner, shadow rows, raw-list note, `:35` text, focus checkbox (§14.2, §21) |
| `settings/pages/InputPage.qml` | Switch-clash note, Compose row, Clipboard group (§15, §16, §12) |
| `settings/pages/WindowsPage.qml` | Hot corner row (§20) |
| `settings/pages/AppsPage.qml:3` | Comment (§4) |
| `settings/pages/PowerPage.qml:90-94` | Power-button text (§17) |
| `settings/SearchIndex.js` | Shortcuts page words `+ "screenshot print capture record"`; entries `input.compose`, `input.clipboard`, `windows.hotcorner` |
| `iso/kiwi/config.kiwi:154` | `google-noto-color-emoji-fonts` |
| `packaging/arctic-linux.spec` | §24 |
| `.github/workflows/ci.yml:52-54` | ShellCheck list adds `packaging/desktop/arctic-share-picker` |

#### 22.3 Icons (D9)

- New 24-grid line glyphs: 1.75 stroke, round caps and joins, `currentColor` fills only for
  dots, the same format as `design/icons/*.svg` and `shell/assets/design-data.js`.
- `design-data.js` is exported from the external design bundle (`shell/dev/export-design-assets.cjs:9-10`).
  The bodies must also go into that bundle, or the next export drops them (the same rule as the Get
  apps section's `layers` glyph).
- Proposed bodies (the design pass may refine them):

| Name | Body |
|---|---|
| `pipette` | `<path d="M14 7.5l2.5 2.5 M15.2 5.3l1.3-1.3a2.1 2.1 0 0 1 3 3l-1.3 1.3 M13.7 6.8L6 14.5l-1 3.5 3.5-1 7.7-7.7"/>` |
| `scan-text` | `<path d="M4 8V6.5A2.5 2.5 0 0 1 6.5 4H8 M16 4h1.5A2.5 2.5 0 0 1 20 6.5V8 M20 16v1.5a2.5 2.5 0 0 1-2.5 2.5H16 M8 20H6.5A2.5 2.5 0 0 1 4 17.5V16 M8 9.5h8 M8 12h8 M8 14.5h5"/>` |
| `qr-code` | `<rect x="4" y="4" width="6" height="6" rx="1.2"/><rect x="14" y="4" width="6" height="6" rx="1.2"/><rect x="4" y="14" width="6" height="6" rx="1.2"/><path d="M14 14h2.5v2.5 M20 14v.01 M14 20h.01 M17.5 17.5H20V20h-2.5z"/>` |
| `smile` | `<circle cx="12" cy="12" r="8.5"/><path d="M8.5 14a4.5 4.5 0 0 0 7 0 M9.5 9.5h.01 M14.5 9.5h.01"/>` |
| `clipboard` | `<rect x="5.5" y="5" width="13" height="16" rx="2.5"/><path d="M9 5V4.2A1.2 1.2 0 0 1 10.2 3h3.6A1.2 1.2 0 0 1 15 4.2V5 M9 11h6 M9 15h4"/>` |
| `monitor` | `<rect x="3" y="4.5" width="18" height="12" rx="2.5"/><path d="M9 20.5h6 M12 16.5v4"/>` |
| `pin` | `<path d="M9 3.5h6 M10 3.5v5.5l-3 3.5h10l-3-3.5V3.5 M12 12.5V20.5"/>` |

- Reused glyphs: `camera`, `record`, `folder`, `edit`, `clock`, `keyboard`, `copy`, `trash`,
  `alert`, `tiling`, `x`, `check`, `search`.
- Settings uses `settings/assets/Icons.js`, which must stay identical to the installer's
  (`test_design_icons_are_the_installers`). Settings uses only existing glyphs (`alert`, `keyboard`).

---

### 23. Data formats (summary)

| File or stream | Writer → reader | Shape |
|---|---|---|
| `arctic-capture …` stdout | helper → front ends | one line, `{"ok":…}` snake_case (§5.3) |
| `$XDG_RUNTIME_DIR/arctic/capture/request.json` | `arctic-capture` → shell | §5.4 |
| `$XDG_RUNTIME_DIR/arctic/capture/reply.fifo` | shell → `arctic-capture` | one JSON line (§5.4) |
| `$XDG_RUNTIME_DIR/arctic/capture/*.ppm` | grim → shell, Pillow | frozen outputs, removed after use |
| `$XDG_RUNTIME_DIR/arctic/tmp/*.png` | `arctic-screenshot` | copy-only, OCR and QR crops (§5.2) |
| `$XDG_RUNTIME_DIR/arctic/record.json` | `arctic-record` → `RecordService` | §8.2 |
| `$XDG_RUNTIME_DIR/arctic/touchpad` | `arctic-touchpad` | `on` / `off` |
| `$XDG_RUNTIME_DIR/arctic/share-<pid>.fifo` | shell → `arctic-share-picker` | `Monitor: NAME` / `Window: ID` / empty |
| `~/.local/state/arctic/capture.json` | `arctic-capture` | `{"last":{output,x,y,width,height},"ocr_offered":["heb"]}` |
| `~/.local/state/arctic/record.json` | `RecordDialog` | `{"kind":"area","audio":"none"}` |
| `~/.cache/arctic/record-codec` | `arctic-record` | `<driver>=<codec>` lines |
| `~/.cache/arctic/emoji.json` | `emoji-index.py` → `EmojiService` | §11 |
| `~/.local/state/arctic/emoji-recent.json`, `emoji.json` | `EmojiService` | `{"recent":["👍",…]}`, `{"tone":2}` |
| `~/.local/state/arctic/clipboard-pins/` + `pins.json` | `clipboard.py` | 0600 files; `[{"pin":"p-3f2a","kind":"text","mime":"text/plain","preview":"…"}]` |
| `~/.config/arctic/clipboard.conf` | Settings → `arctic-session` | `history=on\|off` |
| `~/.local/state/arctic/notices.json` | Settings backend | `{"shown":["keys-0.3.0","shadowed-9c1e…"]}` |
| `arctic-keys --json` | → `KeysSheet.qml`, Settings | §13.2 (camelCase) |
| `arctic_settings.py binds` | → `ShortcutsPage.qml` | adds `shadowed` and per-entry `shadowedBy` |
| `arctic_settings.py keyboard-data` | → `InputPage.qml` | adds `switchClashes`, `composeKeys` |

---

### 24. Packaging deltas (`packaging/arctic-linux.spec`)

| Where | Change |
|---|---|
| `:36` | `Version: 0.3.0` when the work lands (D1; the release work package owns the line). |
| `%package -n arctic-desktop-config` (`:157-220`) | Add `Requires: glib2` (`gio trash`, `gdbus` for Show in Files). Add `Recommends:` `swappy`, `wf-recorder`, `tesseract`, `tesseract-langpack-eng` (named explicitly: the `tesseract` package's Requires name no language data ✅ mdapi; whether its libraries pull `tesseract-common`, which requires the English data, is 🔍), `python3-zxing-cpp` and `fontawesome-6-free-fonts` (only if §5.7's 🔍 passes). `grim`, `slurp`, `wl-clipboard`, `cliphist`, `brightnessctl` and `libnotify` are already Required. |
| `%description -n arctic-desktop-config` | Mention the capture helpers and the screen-share picker. |
| `%package -n arctic-shell` (`:240-252`) | `Requires: wtype`, `unicode-emoji`, `cldr-emoji-annotation`, `google-noto-color-emoji-fonts`. |
| `%install`, arctic-desktop-config (after `:672`) | `install -Dpm 0644 packaging/desktop/xdg-desktop-portal-wlr.ini %{buildroot}%{_sysconfdir}/xdg/xdg-desktop-portal-wlr/mango` and `install -Dpm 0755 packaging/desktop/arctic-share-picker %{buildroot}%{_libexecdir}/arctic/arctic-share-picker`. New helpers in `dotfiles/.local/bin` and `.conf` files need no lines (globs `:642`, `:702-705`); `dotfiles/.config/swappy/config` reaches `/etc/skel` through the tar (`:621-625`). |
| `%files -n arctic-desktop-config` (`:1082-1122`) | `%dir %{_sysconfdir}/xdg/xdg-desktop-portal-wlr`, `%config(noreplace) %{_sysconfdir}/xdg/xdg-desktop-portal-wlr/mango`, `%{_libexecdir}/arctic/arctic-share-picker`. |
| `%check` (after `:824`) | `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s shell/tests -p 'test_capture.py'` and `-p 'test_keys.py'` (standard library; skip Pillow cases when it's absent). The loop at `:825-832` already `bash -n`s the new libexec script. `mango -p` (`:886-897`) validates the new binds and options. |
| `%package -n arctic-desktop` (`:402-480`) | No change: Recommends of arctic-desktop-config are installed with it, and it already Requires `xdg-desktop-portal-wlr` (`:443`). |
| `iso/kiwi/config.kiwi:154` | `google-noto-color-emoji-fonts`. The Recommends reach the ISO through `patternType="plusRecommended"` (`:58`). 🔍 ISO size with tesseract, leptonica, wf-recorder and the emoji data, against the 2 GiB budget: `tools/build-iso.sh`, then compare. If it overflows, drop `tesseract` from the ISO with a kiwi `<ignore>`; Text shows **Install**. |

---

### 25. Tests

#### 25.1 `settings/tests/test_app_files.py` (`IntegrationFilesTest`, after `:76-81`)

- `test_browser_is_super_b`: `apps.conf` has `bind=SUPER,b,spawn,arctic-open browser` and no
  `^bind[a-z]*=SUPER,w,`. `keys.txt` has `Super + B                Browser`. `ROLES` browser keys
  equal `Super + B`.
- `test_screenshot_keys`: `binds.conf` has `bind=SUPER+SHIFT,s,spawn,arctic-screenshot area` and the
  three Print lines. `keys.txt` mentions `Super + Shift + S`.
- `test_no_duplicate_binds`: parse every `bind*=` line of `apps.conf` + `binds.conf` per keymode
  (`common` collides with all). Normalise mods, lower-case the key, `code:49` ≡ `grave`, and
  separate `r` (release) binds. Assert each combo appears once.
- `test_binds_avoid_layout_switch_chords`: no bind has ALT+SHIFT; CTRL+SHIFT only in
  `{(CTRL,SHIFT,escape)}`; ALT with `space` only in `{(SUPER,ALT,space)}`. The allowlists match
  §3.1.2.
- `test_every_bind_is_described`: every bind line in Arctic's files is preceded by `#:` or `#-`.
- `test_keys_txt_is_generated`: run `dotfiles/.local/bin/arctic-keys --sheet --arctic-only` on the
  repo's config (with a temporary HOME whose `.config/mango` points at `dotfiles/.config/mango`) and
  compare with `keys.txt`.
- `test_user_example_keys_stay_free`: `Super + Alt + B` and `Super + Alt + M` are unbound.
- `test_arctic_dispatchers_have_labels`: every non-spawn dispatcher in Arctic's files is in
  `DISPATCHERS`.
- `test_capture_layers_have_rules`: `rules.conf`'s shell regex covers
  `arctic-capture|share|record|emoji|clipboard`; the `shield_when_capture` rule for
  `^arctic-clipboard$` exists.
- `test_xdpw_config`: `packaging/desktop/xdg-desktop-portal-wlr.ini` has `chooser_type=simple` and
  `chooser_cmd=/usr/libexec/arctic/arctic-share-picker`, and the spec installs both paths.

#### 25.2 `settings/tests/test_arctic_settings.py`

- **`ShortcutsTest`** (`:424-456`):
  - `bind-add SUPER b foot` fails, with `arctic-open browser` in the error;
  - `SUPER+SHIFT s` fails with `arctic-screenshot`;
  - `ALT Tab` fails with "Switch windows";
  - `SUPER w` succeeds;
  - shadowing: write `bind=SUPER,b,spawn_shell,firefox` into `settings.conf` → `mine[0].shadowedBy.label == 'Super + B'`
    and `shadowed` has it;
  - the same in `user.conf` → in `shadowed` with `file == 'user.conf'`;
  - a `bindc` doesn't shadow; a `bindr` on the same combo doesn't shadow a `bind`;
  - with `xkb_rules_layout=us,il`, `xkb_rules_options=grp:alt_shift_toggle`: `bind-add SUPER+ALT+SHIFT x`
    fails with "Alt + Shift switches"; with one layout it succeeds.
- **`notices`**:
  - the first run returns `keys-0.3.0` and writes `notices.json`; the second run returns nothing;
  - a new shadowed bind → `shadowed-*` once;
  - a copied `binds.conf` (a regular file differing from `share/mango/binds.conf`) →
    `copied-binds.conf-0.3.0`.
- **`MiscTest.test_keyboard_data`** (`:1205`):
  - `switchClashes['grp:ctrl_shift_toggle']` lists `Ctrl + Shift + Esc` when a fixture adds
    `bind=CTRL+SHIFT,Escape,spawn,x`;
  - `composeKeys` has `compose:ralt`.
- **`DefaultAppsTest`** (`:937-966`): `self.role(data,'browser')['keys'] == 'Super + B'`.
- **`OptionTableTest`**: `enable_hotarea` and `hotarea_corner` are in `mango-0.17.3-keys.txt`
  (automatic) and clamp correctly.
- **Clipboard**: `clipboard-set history off` writes `clipboard.conf` and calls the stub
  `arctic-session clipboard --restart`.
- **Sheet**: `binds` returns `sheet` from a stub `arctic-keys` on `PATH` when present, and from
  `keys.txt` otherwise.

#### 25.3 `shell/tests` (run by the `shell-tests` job, `ci.yml:65-100`)

- **`test_capture.py`**: fake `grim`, `slurp`, `mmsg`, `arctic-shell-ipc`, `tesseract`, `zbarimg`
  and `wf-recorder` on `PATH`, as `test_helpers.py:38-41` does. It covers:
  - window geometry inset from a config chain with `borderpx=3`; fullscreen means no inset;
    `{"error":"no focused client"}` → `code:"no_window"`;
  - focused output from `all-monitors` `active`;
  - visible-window filtering and order; `rects` output format;
  - crop maths at scale 1, 1.25 and 2 against generated PPM frames (pixel-exact corners);
  - the request JSON shape; the FIFO reply read, with a thread playing the shell; timeout →
    `timeout` code and a `capture cancel` call; cancel reply → `cancelled`;
  - fallback to slurp when `arctic-shell-ipc` exits 1;
  - the point pixel from a P6 buffer;
  - OCR language order from `LANG=he_IL.UTF-8` and `xkb_rules_layout=us,il` with installed
    `heb,eng`;
  - QR kinds (`url`, `otpauth` redacted, `wifi` SSID only) with a fake decoder; the swatch SVG.
- **`test_keys.py`**:
  - the `#@`/`#:`/`#-` grammar, section order, `Keys :: What` overrides, gestures and mousebinds;
  - user binds from `settings.conf` (`gtk-launch` → "Open <Name>" with a fixture desktop file) and
    `user.conf`;
  - shadowed entries; `--sheet` column widths;
  - fallback to `keys.txt` when `config.conf` is missing;
  - JSON shape.
- **`test_emoji_index.py`**: fixture subsets of `emoji-test.txt`, `he.xml` and
  `annotationsDerived/he.xml`; tone folding; fully-qualified only; cache rebuilt on newer sources
  and on a language change; `--lines`.
- **`test_clipboard.py`**: fake `cliphist`; text and image list parsing; `delete` passes the full
  line on stdin; `wipe` keeps pins; pin files are 0600; an unknown preview format is text.
- **`test-launcher.cjs`**: `mode(':thumb')` → `{mode:'emoji', text:'thumb'}`; `mode(' :x')` too;
  `=`/`>` unchanged.

#### 25.4 Lint, QML and headless

- **ShellCheck** (`ci.yml:41-63`): the new bash helpers are picked up by the
  `dotfiles/.local/bin/*` glob (Python ones are skipped by shebang), and
  `packaging/desktop/arctic-share-picker` is added explicitly.
- **qmllint** (`ci.yml:129-148`) lints the new QML automatically.
- **Headless** (`shell/dev/headless.sh`, screenshots in `shell/dev/screenshots/`). New shots:
  - `ipc capture select <fixture request>` with fixture PPMs: the overlay idle, with a drag, and in
    point mode with the loupe;
  - `ipc share pick <fifo>`; `ipc record open`; `ipc emoji toggle`; `ipc clipboard toggle` with a
    fake cliphist; `ipc keys toggle` (generated sheet, filter typed).

#### 25.5 Manual matrix (Fedora 44 VM and one laptop, under Mango, before the PR; D10)

- Every row of §3.2 fires. Also check:
  - `us,il`: `` Alt + ` `` and `` Super + ` `` in both groups; Alt + Tab doesn't flip the layout;
  - `de`: `` Super + ` `` (dead-grave layout).
- Print, Super + Shift + S, Shift + Print, Super + Print and Ctrl + Print at scale 1, 1.25 and 2,
  with two monitors: the output is pixel-exact, the selection is clamped, Tab/Enter/Ctrl+Enter/R
  work, and pressing the key again cancels.
- The notification actions in the shell and in the waybar fallback (mako middle-click menu); Edit
  with swappy (icons 🔍); Move to Trash is recoverable.
- OCR in English and Hebrew; the QR otpauth result isn't in `cliphist list`.
- The colour picker at scale 2 matches a known token colour.
- Recording on Intel and AMD (codec probe 🔍), with desktop sound and the mic; the stop thumbnail;
  the disk watchdog (a small tmpfs as the Videos folder).
- Screen share in Firefox (Meet test page) and OBS: a screen, then a window. Declining sends
  nothing.
- Emoji into GTK 4, Qt 6, Chromium, kitty and foot (ZWJ 🔍). The clipboard panel: image thumbnail,
  paste into kitty (Ctrl + Shift + V), pins survive Clear.
- Keyboard light, touchpad and calculator keys; the power button opens the menu, and after
  `pkill -9 quickshell` the button powers off again (the inhibitor is released).
- An old account with `bind=SUPER,b,spawn,firefox` in `user.conf`: the login notice and the
  Settings banner appear.

---

### 26. Docs to update

| File | Change |
|---|---|
| `docs/wiki/Keyboard-Shortcuts.md` | `:17` → `` `Super + B` ``; `:27` "`Super + Enter`, `B`, `E` and `F`"; Everyday adds `Super + Ctrl + E`; Windows (`:30-48`) adds Alt + Tab / `` Alt + ` `` / Super + Alt + Tab, Super + J, Super + Backspace, Super + H, Super + Shift + P, groups; Workspaces adds `` Super + ` ``; a new "Capture" table replaces the Print rows at `:74-76` (Print or Super + Shift + S, Shift + Print, Super + Print, Ctrl + Print, Super + Ctrl + Print, Super + Shift + C, Super + Alt + R / Alt + Print, Super + Ctrl + C); Hardware keys (`:78-88`) adds keyboard light, touchpad, calculator, search, power button; new "In the capture overlay", "In the emoji picker" and "In clipboard history" tables; Changing a shortcut (`:152-160`) adds the shadow warning; a "Keyboard layouts" note (§15); the rows other sections own (§3.2 rows 35-55) are written by them in the same file |
| `docs/wiki/First-Boot.md:61`, `:69` | `Super + W` → `Super + B` |
| `docs/wiki/Apps-and-Software.md:13`, `:420` | `Super + B` |
| `docs/wiki/Themes-and-Customisation.md` | `:160` `Super + B`; `:218-219` → Super + Alt + B example (§4); `:224-228` "…if Arctic later uses a key you bound, Settings > Shortcuts tells you"; a "Compose key" paragraph with an `~/.XCompose` example (`include "%L"` first) |
| `docs/wiki/Settings.md` | `:176-178` Keyboard bullet adds compose key and switch-key warnings, plus a Clipboard bullet; `:185-195` Shortcuts adds the banner, the shadow text and "bring its window back"; `:202` `Super + B`; Windows paragraph adds the hot corner |
| `docs/wiki/Troubleshooting.md` | `:280` `Super + B`; new entries: "A shortcut I made doesn't work" (shadowing, layout switch); "Screen sharing shows no picker" (`XDG_CURRENT_DESKTOP`, `/etc/xdg/xdg-desktop-portal-wlr/mango`); "Recording won't start" (the codec log at `$XDG_RUNTIME_DIR/arctic/record.log`); "The editor's buttons are empty boxes" (§5.7) |
| `docs/wiki/Try-Arctic-Linux.md:52` | `(Super + B)` |
| `docs/wiki/Desktop-Tour.md:204-208` | "Screenshots and the clipboard" becomes "Capture and the clipboard": the overlay, the actions, Edit, text, QR, colour, recording, share picker, the clipboard panel, emoji |
| `docs/wiki/Contributing.md:15` | "(`Print` or `Super + Shift + S` saves one to `~/Pictures/Screenshots`)" |
| `docs/wiki/Release-Notes.md` | The 0.3.0 section (shared; this section's bullets): Super + B; Super + Shift + S; Shift + Print is the focused monitor; screenshot actions and Edit; text, QR, colour and recording; the share picker; emoji; clipboard panel; Alt + Tab; the drop-down terminal; the generated sheet; the shadow warning; compose key; hardware keys. Leave `:340` as it is. |
| `docs/wiki/Terminal-and-Shell.md` | The drop-down terminal (Super + Alt + Enter) |
| `docs/BUILD-SPEC.md` | `:101-104` IPC targets add `capture`, `share`, `record`, `emoji`, `clipboard`; §3 autostart adds `arctic-settings --check-binds`; the desktop-config paragraph adds the xdpw chooser |
| `dotfiles/README.md` | §22.2 |
| `shell/README.md` | IPC table and components |
| `docs/wiki/images/keys.png` | `tools/screenshot-tour.sh --only keys` after keys.txt changes; new images `capture.png` and `share-picker.png` from the headless shots |
| `design/brand-book.md:87` (optional) | Add `Super + B` browser to the key list |

---

### 27. Work packages

| WP | Scope | Owns | Depends on | Size |
|---|---|---|---|---|
| K1 | Keys data and sheet: the `#:` grammar, the new `apps.conf`/`binds.conf` (this section's rows), `arctic-keys` in Python, `keys.txt` generation, `KeysSheet.qml`, and the file-level tests | `apps.conf`, `binds.conf`, `arctic-keys`, `keys.txt`, `KeysSheet.qml`, `shell/tests/test_keys.py` | — | M |
| K2 | Settings: Super + B role, `DISPATCHERS`/`KEY_NAMES`, shadow detection, `notices` + `arctic-settings --check-binds`, layout-chord checks, compose, hot corner, sheet from `arctic-keys`, focus checkbox | `arctic_settings.py` (these parts), `ShortcutsPage.qml`, `InputPage.qml` (switch and compose rows), `WindowsPage.qml`, `AppsPage.qml:3`, `SearchIndex.js`, `arctic-settings`, `settings/tests/*` additions | K1 | M |
| C1 | Capture engine and screenshots: `arctic-capture`, `arctic-screenshot`, the editor, notification actions, `capture-colors.env`, mako middle click, the swappy config | those files, `shell/tests/test_capture.py` + fixtures | K1 | M |
| C2 | Capture overlay in the shell | `CaptureOverlay.qml`, `CaptureSurface.qml`, the `capture` IPC | C1 | M |
| C3 | OCR, QR, colour | `arctic-colorpick`, the `ocr`/`qr`/`swatch`/point parts of `arctic-capture`, the loupe | C1, C2 | S |
| C4 | Recording | `arctic-record`, `RecordDialog.qml`, `RecordService.qml`, the `record` IPC | C1, C2 | M |
| C5 | Screen-share picker | `packaging/desktop/arctic-share-picker`, `packaging/desktop/xdg-desktop-portal-wlr.ini`, `SharePicker.qml`, the `share` IPC | C1 | M |
| I1 | Emoji | `emoji-index.py`, `EmojiService.qml`, `EmojiPicker.qml`, `arctic-emoji`, the `:` mode, tests | K1 | M |
| I2 | Clipboard panel | `clipboard.py`, `ClipboardPanel.qml`, `arctic-clipboard`, `arctic-session` clipboard, the Settings clipboard group and commands, tests | K1, K2 | M |
| H1 | Hardware keys | `arctic-osd`, `arctic-touchpad`, `PowerKeyService.qml`, the `Osd.qml` kinds | K1 | S |
| W1 | Windows: switcher, jump, last, scratch, drop-down, hide, pin, groups, `look.conf`, the `mango-colors` template, `arctic-window`, `arctic-open --focus/--raise-title`, the layout chip | those files | K1 | M |
| D1 | Docs, release notes, icons and packaging aggregation | wiki pages, READMEs, `design/icons/*`, `design-data.js`, spec lines in §24, `config.kiwi:154`, `install.sh` | all | S |

Order: K1 → (K2, C1, W1, H1, I1 in parallel) → (C2 → C3, C4), C5, I2 → D1. The PR merges once CI
is green (D10).

---

### 28. Open issues

1. 🔍 **Alt + Print and the kernel sysrq filter** (§3.1.4). If the key arrives late or not at all,
   drop row 9. `Super + Alt + R` stays.
2. 🔍 **Mango parsing and firing**: `code:49` keys on `us`, `us,il` and `de`; the new dispatchers and
   `look.conf`/`mango-colors` keys in `mango -p`; the jump-label and group-bar colour formats.
3. 🔍 **mmsg JSON fields**: `is_visible`, `is_floating`, `is_global`, `is_fullscreen`, `is_minimized`,
   `foreign_toplevel_id`, monitor coordinates (logical or physical), `all-clients` stacking order,
   and `layout_symbol`.
4. 🔍 **`focusid` across workspaces**, and the browsers' Wayland app ids, for `arctic-open --focus`.
5. 🔍 **`XDG_CURRENT_DESKTOP`** under SDDM contains `mango` (xdpw config name), and xdpw's service
   environment has `MANGO_INSTANCE_SIGNATURE` (fallback window list).
6. 🔍 **`ScreencopyView`** in the `dacfa9d` snapshot on Mango (share-picker previews only; the
   capture overlay doesn't use it).
7. 🔍 **swappy's icons**: F44 has no Font Awesome 5. Try `fontawesome-6-free-fonts`; else ship
   `show_panel=false`.
8. 🔍 **Recording codecs** in F44's `ffmpeg-free` 8.1.2 (VA-API H.264/AV1/VP9), and wf-recorder's
   audio device names on pipewire-pulse.
9. **Deferred**: desktop sound + mic in one recording (§8.3), the gpu-screen-recorder Flatpak path,
   the webcam overlay.
10. **Deferred**: theming Mango's switcher panel. It needs an upstream option; a fork patch would
    break `mango -p` for users on other Mango builds.
11. **Deferred**: switching layouts on key release (§15.5). Test `bindr` first; the change spans the
    installer, Settings, SDDM and the console.
12. **Not shipped**: a default `~/.XCompose` (§16).
13. 🔍 **wtype** and multi-codepoint emoji; the clipboard-paste fallback per toolkit.
14. 🔍 **The zxing-cpp 2.2.1 Python API**; the cliphist 0.7.0 image preview format.
15. 🔍 **`shield_when_capture`** also hides the clipboard panel from grim. This is intended; confirm
    it and note it in the docs.
16. 🔍 **Overlay latency** (freeze + map) under 250 ms at 1080p and 400 ms on two 4K outputs.
17. 🔍 **ISO size** with tesseract, wf-recorder and the emoji data against the 2 GiB budget.
18. **Bar focus key**: this table moves it to `Super + Alt + P` (from the gap list's
    `Super + Alt + B`). The bar section must use this key or change the table and its tests.
19. **Every section that adds a bind must add a `#:` line** and pass §25.1's tests. A bind without
    one fails CI. The Get apps section's `keys.txt:11` wording moves into the `#:` line above
    `Super + Shift + A`.
20. **`Segmented.qml`**: the record dialog reuses the Get apps section's control. Whichever section
    lands first moves it to `shell/`.
21. **Users with a copied `binds.conf`/`apps.conf`** get no new keys. The login notice (§14.3) says
    so once; Arctic doesn't edit their copy.
22. **The shell's notification server** (D6) must hide the `default` action button, show
    `image-path`, and ideally keep notifications open in the centre so actions keep working (§5.6).
