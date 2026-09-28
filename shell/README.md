# Arctic shell

The Arctic Linux desktop shell, written for [Quickshell](https://quickshell.org): the top bar,
the screen frame, the launcher with its Get apps console, the wallpaper picker, the power menu,
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

It needs `quickshell`, `python3`, `python3-pillow` (wallpaper thumbnails) and `python3-pyte`
(the Get apps terminal); the bar uses NetworkManager (`nmcli`), PipeWire, UPower, BlueZ, mako
(`makoctl`) and `brightnessctl` when they are there and hides what isn't.

## What's in it

| Surface | Files | Notes |
|---|---|---|
| Top bar | `Bar.qml`, `BarItem.qml`, `BarTooltip.qml`, `Workspaces.qml`, `scripts/workspaces.py` | 34px frost, 1px `line` bottom. Fox mark (launcher), workspaces 1–5 (active amber pill, occupied ring, empty muted, urgent error ring), clock with tabular figures, notifications bell (do not disturb), Bluetooth, tray, network, volume, battery (hidden without one), power. Live USB: "Live session" tag and the amber Install item. Tooltips on every icon-only item. |
| Screen frame | `ScreenFrame.qml` | Ground-coloured surround with a `line` hairline. It reserves its width on each edge, so Mango keeps its 8px gap inside it and window corners are concentric with the frame's. `{"frame": false}` in `~/.config/arctic/shell.json` turns it off. |
| Launcher | `Launcher.qml`, `LauncherSearch.js`, `Calc.js`, `AppTile.qml` | Super+Space. 520px frosted card that hangs from the bar over a scrim; drag the grip to dock it to any edge. Apps (design app tiles for the Arctic apps), `=` calculator (a small parser: arithmetic only, never `eval`), `>` run a command (Shift+Enter: in your terminal, via `arctic-open terminal -e`). Empty query: Apps, Get apps, Wallpapers, Settings, Fetch (+ Install Arctic Linux on the live USB). `LauncherSources.qml` adds Settings pages and settings (from Settings' `SearchIndex.js`, via `SettingsIndex.qml`), open windows (ToplevelManager), apps' desktop actions, files under ~ (`fd`), unit conversions (`qalc`) and a web search (`?`; engine in shell.json `webSearch`), ranks what you open often higher (`~/.local/state/arctic/launcher.json`), and sets reminders (`remind 10m tea` → `arctic-remind`, Super+Ctrl+R). Tests: `tests/test-launcher.cjs`, `tests/test-launcher-sources.cjs`. |
| Get apps | `InstallConsole.qml`, `PackageSearch.js`, `scripts/install-terminal.py`, `scripts/package-index.py` | Type an app name to install it, or a `dnf` / `flatpak` command. `dnf install|remove|upgrade` run as `sudo dnf …`, queries without sudo, `flathub:<id>` or `flatpak install flathub …` through Flatpak — in a real PTY, so sudo's password and dnf's `[y/N]` are answered in the console. Password input is masked, never logged or stored; a reply typed for a prompt that has since changed is refused. Ctrl+C stops the job. Tab completes names from a cached index (`~/.cache/arctic/packages.txt` from `dnf5 repoquery`, `flathub.txt` from `flatpak remote-ls`), refreshed in the background once a day. |
| Wallpapers | `Wallpapers.qml`, `scripts/wallpapers.py` | Searchable thumbnail grid. The Arctic wallpapers (from `~/.local/share/arctic/wallpapers` or `/usr/share/backgrounds/arctic`) show the active theme's variant and follow Winter / Polar night; your own pictures come from `~/Pictures/Wallpapers` or a folder you choose. Applies through `arctic-wallpaper`. The "Match colours to wallpaper" switch is `arctic-theme auto on\|off` (read from `~/.config/arctic/settings.json`). Thumbnails (Pillow; SVGs via rsvg-convert) in `~/.cache/arctic/thumbs`, settings in `~/.config/arctic/wallpapers.json`. |
| Updates | `UpdateIndicator.qml`, `UpdatePopover.qml`, `UpdateService.qml`, `UpdateStatus.js` | While updates wait for the next restart (`/var/lib/arctic/update-status.json` from `arctic-update` says `ready` and `/system-update` exists): the amber "Restart to update" pill on the bar, a card with the number and size of the updates and **Restart and install** (`arctic-power restart`), and one notification per download (remembered in `~/.cache/arctic/update-notified`). Never on the live USB. |
| Power menu | `PowerMenu.qml` | Under the power item or Super+Esc: Settings, Lock screen, Log out, Suspend, Restart, Shut down (live: Settings, Restart, Shut down). Runs `arctic-power <action>`; Settings runs `arctic-settings`. |
| Command menu | `CommandMenu.qml`, `MenuModel.js`, `menu/*.json` (`00-arctic.json`; another part of Arctic adds rows with a file of its own, read in name order), `SettingsIndex.qml` | Super+Alt+Space (Super+Ctrl+C: Capture). Every system action in one keyboard-driven tree: Apps, Learn, Capture, Toggle, Style, Setup (every Settings page, from Settings' own `SearchIndex.js`), Install, Remove, Update, System. The rows are data, merged with `~/.config/arctic/menu.json` by id; one `sh` script per open checks which commands and IPC functions exist (a row that can't run is hidden) and reads the toggles' states. Type to search the branch. `arctic-menu` falls back to fuzzel without the shell. Tests: `tests/test-command-menu.cjs`, `tests/test_arctic_menu.py`. |
| Keyboard shortcuts | `KeysSheet.qml` | Super+/: `keys.txt` from `~/.local/share/arctic` or `/usr/share/arctic`. |
| OSD | `Osd.qml`, `AudioService.qml` | 280×48 frosted pill, bottom centre. Follows PipeWire volume changes directly; brightness when `arctic-osd` calls `arctic-shell-ipc osd brightness` (brightnessctl). 1.2 s, then fades. `OsdModel.js` adds two kinds for everything else: a level (any icon, a bar, an optional label; `osd level ICON PERCENT LABEL`) and a notice (an icon, a few words and an optional detail, no bar, 200-420 px wide, longer text stays longer; `osd notice ICON TEXT DETAIL`, `arctic-osd notice …`), e.g. Caps Lock / Num Lock on or off (`arctic-osd lock-keys`, from their keys and the keyboard's lights). |
| Lock screen | `LockScreen.qml`, `pam/arctic-lock` | ext-session-lock (the session stays locked if the shell dies) + PAM (`pam_unix`, from this folder). Blurred wallpaper under frost, clock, avatar (`~/.face` or your initial), name, password field with focus / error / success rings, battery, Wi-Fi and power bottom-right. Off on the live USB. |
| Live welcome | `LiveWelcome.qml` | "You're trying Arctic Linux" card (Install Arctic Linux / Keep trying), once per boot via `arctic-welcome`, and the Install tile bottom-left. On the desktop layer, under windows. |
| Weather | `WeatherService.qml`, `WeatherCard.qml`, `WeatherItem.qml`, `Weather.js`, `scripts/weather.py` | Off until shell.json `weather` is true (Settings > Appearance > Weather). `weather.py` asks Open-Meteo (no key; coordinates rounded to 2 decimals) for the place in `~/.config/arctic/location.json` or the time zone's city, caches `~/.cache/arctic/weather.json` for an hour and returns the last reading when offline. `WeatherCard` (now + five days, "Jerusalem · Open-Meteo.com · updated 14:05") is for the calendar panel: `Loader { active: WeatherService.enabled; sourceComponent: WeatherCard {} }`; `WeatherItem` (glyph + "21°") for the bar right of the clock, `visible: WeatherService.showInBar` (shell.json `barWeather`). Its glyphs live in `Weather.js` until the design has weather icons. Tests: `tests/test-weather.cjs`, `tests/test_weather.py`. |
| First-login welcome | `FirstLogin.qml` | Installed system, once per new account (`arctic-welcome`: /etc/skel's `~/.local/state/arctic/first-login` marker; `arctic-welcome --again`, or the command menu's Learn › Welcome, shows it again): the keys that get you everywhere, Connect (only while offline), Get apps, Light / Dark, and "Finishing setup" while `/var/lib/arctic/pending.json` lists apps arctic-firstboot still installs (a notification says "All set" when it's gone). |
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
| `apps` | `install` (Get apps), `toggle` |
| `wallpapers` | `toggle`, `open` |
| `power` | `toggle` |
| `menu` | `toggle`, `toggleAt <branch>` (e.g. `capture`), `open <branch>`, `search <text>`, `close` |
| `keys` | `toggle` |
| `osd` | `volume`, `brightness`, `level <icon> <percent> <label>`, `notice <icon> <text> <detail>` |
| `lock` | `lock`, `isLocked` (true once the compositor confirms the lock covers every screen) |
| `welcome` | `open` |
| `dnd` | `refresh` |
| `updates` | `toggle` (the updates card, only while updates wait), `refresh` |
| `shell` | `reload` (theme, motion, settings), `live` |

## Developing

```sh
python3 -m unittest discover -s shell/tests     # PTY console, command building, package index, wallpapers
node shell/tests/test-package-search.cjs        # completion
node shell/tests/test-launcher.cjs              # launcher ranking, calculator
node shell/tests/test-update-status.cjs         # the "Restart to update" logic
/usr/lib64/qt6/bin/qmllint -I /usr/lib64/qt6/qml shell/*.qml
shell/dev/headless.sh --fixtures demo ipc launcher search ze sleep 1 shot launcher
```

`dev/headless.sh` runs the shell in a headless sway (1280×800) with a throwaway HOME (the
dotfiles installed with `install.sh --target`) and saves screenshots to `dev/screenshots/`
(`--theme winter`, `--live` = `ARCTIC_FORCE_LIVE=1`, which exists only for such tests;
`ARCTIC_UPDATE_STATUS=<file>` shows the updates pill from a status file of your own, with a
`/system-update` link in place).

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
  Bluetooth without an adapter, the bell without mako, "N notifications hidden" on the lock
  screen (mako can't count hidden notifications).
