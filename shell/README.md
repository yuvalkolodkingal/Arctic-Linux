# Arctic shell

The Arctic Linux desktop shell, written for [Quickshell](https://quickshell.org): the top bar,
the screen frame, the launcher with Get apps and Remove apps, the wallpaper picker, the power menu,
the keyboard-shortcut sheet, the volume/brightness OSD, the lock screen, the polkit password
dialog and the live USB's welcome card. It runs on Mango (Arctic's compositor) and also on
Hyprland and sway.

It grew out of a personal Quickshell setup — a bar with a Rofi-style launcher (Install, Apps,
Fetch), a PTY install console with masked password prompts, a wallpaper picker, popovers that
unfold from the bar and dock to any screen edge, an event-driven workspace bridge and a rounded
frame around the screen — and keeps all of that, rebuilt on the Arctic design system
([`../design`](../design)): every colour, radius, size and duration comes from the design tokens,
and each surface follows its component spec (TopBar, Launcher, OSD, LockScreen, LiveDesktop).

## Running it

```sh
arctic-shell                  # start it in the background (does nothing if it already runs)
arctic-shell --foreground     # run it here with its log
arctic-shell --restart        # after editing files
arctic-shell-ipc launcher toggle
```

`arctic-shell` runs the first shell folder it finds: `$ARCTIC_SHELL_DIR`,
`~/.config/quickshell/arctic`, `/usr/share/arctic/shell` (package `arctic-shell`), then this
checkout. Mango starts it at login (`arctic-session shell` in the dotfiles' autostart); with
`env=ARCTIC_SHELL,waybar` in `~/.config/mango/user.conf` the session uses the waybar + fuzzel +
lxqt-policykit fallback instead.

It needs `quickshell`, `python3`, `python3-pillow` (wallpaper thumbnails), `python3-pyte`
(the Get apps console), `glib2` (`gdbus`, to check who owns notifications) and `python3-dbus`
with `python3-gobject-base` (the Bluetooth pairing agent, battery details); the bar uses
NetworkManager (`nmcli`), PipeWire, UPower and power-profiles (tuned-ppd), BlueZ, MPRIS players,
Mango (`mmsg`, the keyboard layout), `brightnessctl` and `ddcutil` when they are there and hides
what isn't. The shell is the notification server; mako is only the fallback (the waybar session,
or when the shell can't take the name).

## What's in it

| Surface | Files | Notes |
|---|---|---|
| Top bar | `Bar.qml`, `BarItem.qml`, `BarTooltip.qml`, `Workspaces.qml`, `scripts/workspaces.py` | 34px frost, 1px `line` bottom. Fox mark (launcher), workspaces 1–5 (active amber pill, occupied ring, empty muted, urgent error ring), clock with tabular figures, notifications bell (the notification centre; right click: do not disturb), keyboard layout (with two or more), Bluetooth, tray, network, volume, battery (hidden without one), power. Live USB: "Live session" tag and the amber Install item. Tooltips on every icon-only item. |
| Bar menus | `BarMenu.qml`, `NetworkPanel.qml`, `BluetoothPanel.qml`, `SoundPanel.qml`, `BatteryPanel.qml`, `CalendarPanel.qml`, `MediaPanel.qml`, `TrayPanel.qml`, `DisplayPanel.qml`, services (`NetworkService`, `BluetoothService`, `AudioService`, `BatteryService`, `PowerService`, `MediaService`, `BrightnessService`, `PrivacyService`), `scripts/network.py`, `scripts/battery.py`, `scripts/brightness.py` | Every bar item opens Arctic's own menu in one host (one menu at a time; Ctrl+Tab moves to the neighbouring item's). Network: Wi-Fi on/off, wired, nearby networks (scanned only while open), joining with the password asked under the network (to nmcli through a pipe, never a command line), hidden networks, forget, connect automatically, VPN switches. Bluetooth: power, your devices, pairing. Sound: output/input devices and volume, a volume per app. Battery: power mode, the charge limit UPower offers, health, other devices; low and critical warnings. Clock: calendar with week numbers. Media (right of the clock, while a player exists). Tray icons: their DBusMenu drawn by the shell (QsMenuOpener). "Edit connections…", "More Bluetooth options…" and "Volume control…" open the stock tools. Toolkit: `MenuList.qml` (+ `MenuNav.js`), `MenuRow`, `MenuSwitchRow`, `MenuSlider`, `MenuSection`, `MenuHeader`, `MenuPage`, `MenuField`, `Spinner`, `SignalIcon`, `ShadowLayers`; extra glyphs in `assets/icons-extra.js`. |
| Quick Settings | `QuickSettingsPanel.qml`, `QuickTile.qml`, `Toggle.qml`, `HelperToggle.qml`, `ToggleRegistry.qml`, `ModeIndicators.qml` | Super+A: battery, Settings / Lock / Power, volume and brightness, a tile per registry toggle (Wi-Fi, Bluetooth, do not disturb, night light and keep awake when their helpers are installed, dark style, power mode, microphone, VPN), what is playing; chevrons open the menus above as pages. Left of the clock: "Mic" / "Camera" / "Sharing" pills while something records, and the modes that are on. |
| Bluetooth pairing | `BluetoothPairDialog.qml`, `scripts/bt-agent.py` | BlueZ's default agent (python3-dbus): confirmation codes, passkeys, PINs and service requests in a design dialog, shielded in screen captures. |
| Screen frame | `ScreenFrame.qml` | Ground-coloured surround with a `line` hairline. It reserves its width on each edge, so Mango keeps its 8px gap inside it and window corners are concentric with the frame's. `{"frame": false}` in `~/.config/arctic/shell.json` turns it off. |
| Launcher | `Launcher.qml`, `LauncherSearch.js`, `Calc.js`, `AppTile.qml` | Super+Space. 520px frosted card that hangs from the bar over a scrim; drag the grip to dock it to any edge. Apps (design app tiles for the Arctic apps), `=` calculator (a small parser: arithmetic only, never `eval`), `>` run a command (Shift+Enter: in your terminal, via `arctic-open terminal -e`). Empty query: Apps, Get apps, Remove apps, Wallpapers, Settings, Fetch (+ Install Arctic Linux on the live USB). Shift+Delete (or Delete at the end of the text), the row's trash button or a right-click removes an app after `getapps/RemoveSheet` shows what goes; a search with no app offers "Find … in Get apps" (before the files and the web search). On a laptop with two graphics chips (`arctic-gpu status`), Shift+Enter on an app runs it on the discrete one (`arctic-gpu run`). `LauncherSources.qml` adds Settings pages and settings (from Settings' `SearchIndex.js`, via `SettingsIndex.qml`), open windows (ToplevelManager), apps' desktop actions, files under ~ (`fd`), unit conversions (`qalc`) and a web search (`?`; engine in shell.json `webSearch`), ranks what you open often higher (`~/.local/state/arctic/launcher.json`), and sets reminders (`remind 10m tea` → `arctic-remind`, Super+Ctrl+R). Tests: `tests/test-launcher.cjs`, `tests/test-launcher-sources.cjs`. |
| Get apps | `AppsService.qml`, `WebAppClient.qml`, `WebAppProtocol.js`, `getapps/` (`GetApps.qml` router, `ChooserPage`, `SourcePage`, `WebAppPage`, `TerminalAppPage`, `RemovePage`, `RemoveSheet`, `ConsolePage`, `GetApps.js`), `PackageSearch.js`, `scripts/apps.py`, `scripts/appslib.py`, `scripts/install-terminal.py`, `scripts/package-index.py`, `scripts/protected-packages.conf`, `assets/featured.json` (Arctic picks, from `arctic-install catalog --featured`) | Super+Shift+A. A chooser (Flathub apps, Fedora packages, Web apps, Terminal apps, Remove apps, Console); Esc goes back one step. Installs and removals are jobs of `AppsService`, run one at a time in the runner's PTY (`install-terminal.py run`, commands built by `appslib.build_job`: `pkexec /usr/bin/dnf5 install|remove -y …`, `flatpak install|uninstall --system|--user -y --noninteractive …`), so they outlive the launcher; a notification says when one ends out of sight. `apps.py` answers the read-only questions as you: AppStream catalogues, installed apps per source, dnf removal previews (`dnf5 remove --store`, as you), launcher-entry owners (Delete in the launcher). Protected packages (`protected-packages.conf`, `/etc/arctic/protected-packages.d/`, the hard closure of `arctic-desktop`, your login shell, your only terminal) are never removed. Web apps go through `arctic-webapp serve`. The Console takes `dnf` / `flatpak` commands in a real PTY; typed removals list what goes and ask `[y/N]`. |
| Wallpapers | `Wallpapers.qml`, `scripts/wallpapers.py` | Searchable thumbnail grid. The Arctic wallpapers (from `~/.local/share/arctic/wallpapers` or `/usr/share/backgrounds/arctic`) show the active theme's variant and follow Winter / Polar night; your own pictures come from `~/Pictures/Wallpapers` or a folder you choose. Applies through `arctic-wallpaper`. The "Match colours to wallpaper" switch is `arctic-theme auto on\|off` (read from `~/.config/arctic/settings.json`). Thumbnails (Pillow; SVGs via rsvg-convert) in `~/.cache/arctic/thumbs`, settings in `~/.config/arctic/wallpapers.json`. |
| Updates | `UpdateIndicator.qml`, `UpdatePopover.qml`, `UpdateService.qml`, `UpdateStatus.js` | While updates wait for the next restart (`/var/lib/arctic/update-status.json` from `arctic-update` says `ready` and `/system-update` exists): the amber "Restart to update" pill on the bar, a card with the number and size of the updates and **Restart and install** (`arctic-power restart`), and one notification per download (remembered in `~/.cache/arctic/update-notified`). Never on the live USB. |
| Notifications | `NotificationService.qml`, `NotificationRules.js`, `Toasts.qml`, `ToastCard.qml`, `NotificationCard.qml`, `NotificationCenter.qml`, `DndService.qml` | Owns `org.freedesktop.Notifications` (stops a D-Bus-activated mako, starts `arctic-session mako --fallback` if nobody could take the name, leaves dunst/swaync alone and says so). Toasts: 340px cards top-right on the focused screen, newest on top, 3 plus "N more"; low 5 s, normal 8 s, urgent until closed (red edge + "Urgent"), the app's own timeout; hover pauses; click = default action or the app's window. Centre under the bell (Super+Alt+N): do not disturb (1 hour, until tomorrow, until turned off; schedule from Settings), notifications grouped by app (three newest open), clear per app / all, full keyboard use. History (50) in `~/.local/state/arctic/notifications/` (0700): `history.json`, `dnd.json`, `apps.json`; Settings writes `~/.config/arctic/notifications.json` (schedule, per-app rules). Do not disturb lets urgent notifications, Arctic's alerts (`-h boolean:x-arctic-alert:true`) and allowed apps through (`NotificationRules.js`). |
| Keyboard layout | `KeyboardService.qml`, `KeyboardItem.qml`, `KeyboardPanel.qml`, `scripts/keyboard.py` | The bar chip (`EN`, only with two or more layouts): click = next layout, right click = the layout menu. Layouts from Mango's config (installer's `/etc/arctic/mango/keyboard.conf`, Settings' `settings.conf`, `user.conf`) with names from `evdev.xml`; the active one from `mmsg watch keyboardlayout`; switching with `mmsg dispatch switch_keyboard_layout,N` (N from 1; 0 cycles). |
| Power menu | `PowerMenu.qml` | Under the power item or Super+Esc: Settings, Lock screen, Log out, Suspend, Restart, Shut down (live: Settings, Restart, Shut down). Runs `arctic-power <action>`; Settings runs `arctic-settings`. |
| Command menu | `CommandMenu.qml`, `MenuModel.js`, `menu/*.json` (`00-arctic.json`; another part of Arctic adds rows with a file of its own, read in name order), `SettingsIndex.qml` | Super+Alt+Space (Super+Ctrl+C: Capture). Every system action in one keyboard-driven tree: Apps, Learn, Capture, Toggle, Style, Setup (every Settings page, from Settings' own `SearchIndex.js`), Install, Remove, Update, System. The rows are data, merged with `~/.config/arctic/menu.json` by id; one `sh` script per open checks which commands and IPC functions exist (a row that can't run is hidden) and reads the toggles' states. Type to search the branch. `arctic-menu` falls back to fuzzel without the shell. Tests: `tests/test-command-menu.cjs`, `tests/test_arctic_menu.py`. |
| Keyboard shortcuts | `KeysSheet.qml` | Super+/: `keys.txt` from `~/.local/share/arctic` or `/usr/share/arctic`. Type to filter by keys or text; ↑/↓ scroll, Esc clears, then closes. |
| Clipboard history | `ClipboardPanel.qml`, `scripts/clipboard.py` | Super+V: cliphist's history, newest first, pictures with a thumbnail (`~/.cache/arctic/clip-thumbs`). Enter copies, Shift+Enter also pastes (wtype; Ctrl+Shift+V in terminals), Delete removes, Clear asks first. The `arctic-clipboard` layer is shielded from screenshots and screencasts (rules.conf). |
| Emoji | `EmojiPicker.qml`, `scripts/emoji-index.py` | Super+Ctrl+E: unicode-emoji's fully-qualified emoji (up to the version Noto Color Emoji draws; tones folded into their base), CLDR keywords in your language when installed, recent ones first (`~/.local/state/arctic/emoji.json`). Enter types it (wtype, after the layer has gone), Shift+Enter copies it. Cached in `~/.cache/arctic/emoji.json`. |
| OSD | `Osd.qml`, `AudioService.qml` | 280×48 frosted pill, bottom centre. Follows PipeWire volume changes directly; brightness when `arctic-osd` calls `arctic-shell-ipc osd brightness` (brightnessctl); the keyboard layout's name when it changes (not the lock screen's reset). 1.2 s, then fades. `OsdModel.js` adds two kinds for everything else: a level (any icon, a bar, an optional label; `osd level ICON PERCENT LABEL`) and a notice (an icon, a few words and an optional detail, no bar, 200-420 px wide, longer text stays longer; `osd notice ICON TEXT DETAIL`, `arctic-osd notice …`), e.g. Caps Lock / Num Lock on or off (`arctic-osd lock-keys`, from their keys and the keyboard's lights). |
| Lock screen | `LockScreen.qml`, `pam/arctic-lock`, `pam/arctic-lock-fingerprint` | ext-session-lock (the session stays locked if the shell dies) + PAM (`pam_unix`, from this folder). A saved fingerprint unlocks too (a second PAM context, `pam_fprintd`) while the lid is open, unless `{"lock_fingerprint": false}` is in `~/.config/arctic/shell.json`. Blurred wallpaper under frost, clock, avatar (`~/.face` or your initial), name, password field with focus / error / success rings, battery, Wi-Fi and power bottom-right, how many notifications arrived while locked, the keyboard layout beside the field (locking switches to the first layout), "Caps Lock is on". Off on the live USB. |
| Live welcome | `LiveWelcome.qml` | "You're trying Arctic Linux" card (Install Arctic Linux / Keep trying), once per boot via `arctic-welcome`, and the Install tile bottom-left. On the desktop layer, under windows. |
| Weather | `WeatherService.qml`, `WeatherCard.qml`, `WeatherItem.qml`, `Weather.js`, `scripts/weather.py` | Off until shell.json `weather` is true (Settings > Appearance > Weather). `weather.py` asks Open-Meteo (no key; coordinates rounded to 2 decimals) for the place in `~/.config/arctic/location.json` or the time zone's city, caches `~/.cache/arctic/weather.json` for an hour and returns the last reading when offline. `WeatherCard` (now + five days, "Jerusalem · Open-Meteo.com · updated 14:05") sits under the month in `CalendarPanel.qml`; `WeatherItem` (glyph + "21°") sits on the bar right of the clock while shell.json `barWeather` is true and there is a reading (`WeatherService.showInBar`); a click opens the calendar. Its glyphs live in `Weather.js` until the design has weather icons. Tests: `tests/test-weather.cjs`, `tests/test_weather.py`. |
| First-login welcome | `FirstLogin.qml` | Installed system, once per new account (`arctic-welcome`: /etc/skel's `~/.local/state/arctic/first-login` marker; `arctic-welcome --again`, or the command menu's Learn › Welcome, shows it again): the keys that get you everywhere, Connect (only while offline), Get apps, Light / Dark, and "Finishing setup" while `/var/lib/arctic/pending.json` lists apps arctic-firstboot still installs (a notification says "All set" when it's gone). |
| Share your screen | `SharePicker.qml` | When an app asks to share the screen, xdg-desktop-portal-wlr runs `/usr/libexec/arctic/arctic-share-picker`, which opens this card (`share pick <fifo>`): every monitor and window (`arctic-capture sources --json`); Share writes `Monitor: <name>` / `Window: <id>` to the FIFO, Cancel or Esc an empty line (nothing is shared). |
| Record the screen | `RecordDialog.qml`, `RecordService.qml` | Super+Alt+R (`arctic-record toggle`) when nothing records: Area (then click a screen or drag) · Window · Screen, and No sound · Desktop sound · Microphone; Enter starts with the last choice (`~/.local/state/arctic/record.json`). `RecordService` exposes `recording`, `elapsed` and `stop()` for a bar indicator. |
| Frozen screen | `FrozenScreens.qml` | While you select an area for a screenshot, `arctic-screenshot` shows every monitor as it was at the key press (`arctic-capture freeze` → `capture freeze <dir>`, one click-through overlay layer per screen, `arctic-freeze`), and cuts the screenshot from that picture; `capture thaw`, or two minutes, takes them away. |
| Power button | `PowerKey.qml` | Holds a `handle-power-key` inhibitor (`systemd-inhibit … cat`) while the shell runs and the screen is unlocked, so the power button opens the power menu (Mango bind → `arctic-power`); when the shell exits, `cat` gets EOF and logind handles the button again. |
| Polkit agent | `PolkitDialog.qml` | Password dialog for system changes. If it can't register (another agent runs), the shell starts `arctic-session polkit`. |
| Tokens and state | `Theme.qml`, `Session.qml`, `Outputs.qml`, `NetworkService.qml`, `DndService.qml` | See below. |
| Building blocks | `Popover.qml`, `PopupSurface.qml`, `DockPosition.qml`, `DragHandle.qml`, `ArcticButton.qml`, `ArcticField.qml`, `ArcticSwitch.qml`, `Icon.qml`, `Mark.qml`, `Kbd.qml`, `Tip.qml`, `FocusRing.qml`, `RoundedImage.qml` | Popovers unfold from the edge they're docked to (fade + 0.98 scale, duration-slow, ease-standard; reduced motion: fades only) and can be dragged to another edge. |

## Theme

`Theme.qml` reads `~/.config/arctic/current/theme.json` — written for each theme by the theme
engine (`design/themegen`: `design/tools/gen-desktop-themes.py` for Winter and Polar night,
`arctic-theme` for the one made from your wallpaper) and switched by `arctic-theme` — and falls back to
`/usr/share/arctic/themes/polar-night/theme.json`, then to the built-in Polar night
(`assets/theme-defaults.js`, generated too). `arctic-theme toggle` restyles the shell live: the
shell watches `~/.config/arctic/theme` and `arctic-theme` also calls `arctic-shell-ipc shell
reload`. Fonts: Figtree and JetBrains Mono. Reduced motion (`arctic-motion off`) turns movement
into fades. High contrast (`arctic-theme contrast on`) links the theme's high-contrast take, whose
`theme.json` has `"contrast": "high"`: `Theme.highContrast` then makes popover edges
(`Theme.lineWidth`) and focus rings heavier and gives the selected row an edge.

Icons and app tiles come from the design system's bundle: `assets/design-data.js` is generated
by `node dev/export-design-assets.cjs <design>/components/bundle.js` and drawn in token colours
by `assets/Icons.js`.

## IPC

`arctic-shell-ipc <target> <function>` (wraps `quickshell ipc -p <shell> call`). Exits non-zero
when the shell isn't running, so the `arctic-*` helpers fall back to fuzzel, swaylock or
notifications.

| Target | Functions |
|---|---|
| `launcher` | `toggle`, `open`, `close`, `search <text>` (e.g. `"=12*4"`), `apps` (every app) |
| `apps` | `install` (Get apps), `remove` (Remove apps), `open <page>` / `source <name>` (flathub, fedora, web, terminal, remove[/tab], console), `search <page> <text>`, `uninstall <desktop-id>`, `toggle` |
| `wallpapers` | `toggle`, `open` |
| `power` | `toggle` |
| `menu` | `toggle`, `toggleAt <branch>` (e.g. `capture`), `open <branch>`, `search <text>`, `close` |
| `keys` | `toggle` |
| `osd` | `volume`, `brightness`, `level <icon> <percent> <label>`, `notice <icon> <text> <detail>` |
| `lock` | `lock`, `isLocked` (true once the compositor confirms the lock covers every screen) |
| `welcome` | `open` |
| `dnd` | `refresh` (for arctic-dnd with mako) |
| `notifications` | `center` / `toggle`, `open`, `close`, `dismiss` (newest pop-up), `dismissAll`, `invoke` (newest), `count`, `history` (JSON lines), `clearHistory`, `reload` (Settings wrote notifications.json), `dnd <on\|off\|toggle\|1h\|tomorrow\|status>` → `on`/`off`, or `unowned` when another daemon has notifications |
| `keyboard` | `next`, `set <index>`, `menu` |
| `updates` | `toggle` (the updates card, only while updates wait), `refresh` |
| `panel` | `toggle <menu>`, `open <menu>`, `close` — network, bluetooth, sound, battery, calendar, media, display |
| `quick` | `toggle`, `open <page>` (network, bluetooth, sound, battery, display, media; empty for the main page) |
| `toggle` | `set <key> on\|off\|toggle`, `get <key>`, `states` (JSON), `refresh [key]` — keys: wifi, bluetooth, dnd, night-light, keep-awake, dark-mode, power-mode, mic, vpn |
| `bar` | `focus` (keyboard mode: ← → move, Enter opens, Esc leaves) |
| `bluetooth` | `pair` (the Bluetooth menu on its pairing page) |
| `media` | `playPause`, `next`, `previous` |
| `audio` | `nextOutput` |
| `shell` | `reload` (theme, motion, settings), `live` |
| `clipboard` | `toggle` (clipboard history, Super + V) |
| `emoji` | `toggle` (the emoji picker, Super + Ctrl + E) |
| `record` | `open` (the "Record the screen" card), `refresh` (arctic-record started or stopped a recording; `RecordService` re-reads it) |
| `share` | `pick <fifo>` (the screen-share portal's chooser, arctic-share-picker, waits on the FIFO) |
| `capture` | `freeze <dir>` (show the frozen monitors; true when shown), `thaw` |

## Developing

```sh
python3 -m unittest discover -s shell/tests     # PTY console, command building, package index, wallpapers
node shell/tests/test-package-search.cjs        # completion
node shell/tests/test-launcher.cjs              # launcher ranking, calculator
node shell/tests/test-update-status.cjs         # the "Restart to update" logic
node shell/tests/test-menu-nav.cjs              # keyboard movement in the bar menus
node shell/tests/test-calendar-grid.cjs         # the calendar's month grid and ISO weeks
node shell/tests/test-icons.cjs                 # every icon name in the QML resolves
node shell/tests/test-notification-rules.cjs    # do not disturb, per-app rules, history, grouping
/usr/lib64/qt6/bin/qmllint -I /usr/lib64/qt6/qml shell/*.qml
shell/dev/headless.sh --fixtures demo ipc launcher search ze sleep 1 shot launcher
```

`dev/headless.sh` runs the shell in a headless sway (1280×800) with a throwaway HOME (the
dotfiles installed with `install.sh --target`) and saves screenshots to `dev/screenshots/`
(`--theme winter`, `--live` = `ARCTIC_FORCE_LIVE=1`, which exists only for such tests;
`ARCTIC_UPDATE_STATUS=<file>` shows the updates pill from a status file of your own, with a
`/system-update` link in place; `--mako` starts mako first, to test the hand-over of the
notification name; `sh notify-send …` steps show toasts). `--fixtures` also points the network
menu at `tests/fixtures/network.json` (`ARCTIC_NETWORK_FIXTURE`: network.py answers from the file
and changes nothing) and adds the test tray icon `tests/fixtures/sni-menu.py`.

## Design notes

- **Where it differs from the mockups on purpose:** the launcher and the other popovers hang
  from the bar and dock to screen edges (the original shell's behaviour) instead of floating
  120px below it; the screen frame is the original shell's; the Install tile and welcome card
  sit on the desktop layer, so windows cover them.
- **Blur:** Mango blurs the bar (a plain rectangle). The shell's other surfaces are full-screen
  or rounded, where compositor blur would cover the screen or show square corners, so they use
  the `frost` colour without blur (`noblur` layer rules). The lock screen blurs the wallpaper
  itself.
- **Not shown when unknown:** battery without a battery, network without NetworkManager,
  Bluetooth without an adapter, the bell without a notification service, the layout chip with
  one layout, the lock screen's count at 0.
