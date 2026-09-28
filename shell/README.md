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

It needs `quickshell`, `python3`, `python3-pillow` (wallpaper thumbnails) and `python3-pyte`
(the Get apps console); the bar uses NetworkManager (`nmcli`), PipeWire, UPower, BlueZ, mako
(`makoctl`) and `brightnessctl` when they are there and hides what isn't.

## What's in it

| Surface | Files | Notes |
|---|---|---|
| Top bar | `Bar.qml`, `BarItem.qml`, `BarTooltip.qml`, `Workspaces.qml`, `scripts/workspaces.py` | 34px frost, 1px `line` bottom. Fox mark (launcher), workspaces 1–5 (active amber pill, occupied ring, empty muted, urgent error ring), clock with tabular figures, notifications bell (do not disturb), Bluetooth, tray, network, volume, battery (hidden without one), power. Live USB: "Live session" tag and the amber Install item. Tooltips on every icon-only item. |
| Screen frame | `ScreenFrame.qml` | Ground-coloured surround with a `line` hairline. It reserves its width on each edge, so Mango keeps its 8px gap inside it and window corners are concentric with the frame's. `{"frame": false}` in `~/.config/arctic/shell.json` turns it off. |
| Launcher | `Launcher.qml`, `LauncherSearch.js`, `Calc.js`, `AppTile.qml` | Super+Space. 520px frosted card that hangs from the bar over a scrim; drag the grip to dock it to any edge. Apps (design app tiles for the Arctic apps), `=` calculator (a small parser: arithmetic only, never `eval`), `>` run a command (Shift+Enter: in your terminal, via `arctic-open terminal -e`). Empty query: Apps, Get apps, Remove apps, Wallpapers, Settings, Fetch (+ Install Arctic Linux on the live USB). Shift+Delete (or Delete at the end of the text), the row's trash button or a right-click removes an app after `getapps/RemoveSheet` shows what goes; a search with no app offers "Find … in Get apps". |
| Get apps | `AppsService.qml`, `WebAppClient.qml`, `getapps/` (`GetApps.qml` router, `ChooserPage`, `SourcePage`, `WebAppPage`, `TerminalAppPage`, `RemovePage`, `RemoveSheet`, `ConsolePage`, `GetApps.js`), `PackageSearch.js`, `scripts/apps.py`, `scripts/appslib.py`, `scripts/install-terminal.py`, `scripts/package-index.py`, `scripts/protected-packages.conf` | Super+Shift+A. A chooser (Flathub apps, Fedora packages, Web apps, Terminal apps, Remove apps, Console); Esc goes back one step. Installs and removals are jobs of `AppsService`, run one at a time in the runner's PTY (`install-terminal.py run`, commands built by `appslib.build_job`: `pkexec /usr/bin/dnf5 install|remove -y …`, `flatpak install|uninstall --system|--user -y --noninteractive …`), so they outlive the launcher; a notification says when one ends out of sight. `apps.py` answers the read-only questions as you: AppStream catalogues, installed apps per source, dnf removal previews (`dnf5 remove --store`, as you), launcher-entry owners (Delete in the launcher). Protected packages (`protected-packages.conf`, `/etc/arctic/protected-packages.d/`, the hard closure of `arctic-desktop`, your login shell, your only terminal) are never removed. Web apps go through `arctic-webapp serve`. The Console takes `dnf` / `flatpak` commands in a real PTY; typed removals list what goes and ask `[y/N]`. |
| Wallpapers | `Wallpapers.qml`, `scripts/wallpapers.py` | Searchable thumbnail grid. The Arctic wallpapers (from `~/.local/share/arctic/wallpapers` or `/usr/share/backgrounds/arctic`) show the active theme's variant and follow Winter / Polar night; your own pictures come from `~/Pictures/Wallpapers` or a folder you choose. Applies through `arctic-wallpaper`. The "Match colours to wallpaper" switch is `arctic-theme auto on\|off` (read from `~/.config/arctic/settings.json`). Thumbnails (Pillow; SVGs via rsvg-convert) in `~/.cache/arctic/thumbs`, settings in `~/.config/arctic/wallpapers.json`. |
| Updates | `UpdateIndicator.qml`, `UpdatePopover.qml`, `UpdateService.qml`, `UpdateStatus.js` | While updates wait for the next restart (`/var/lib/arctic/update-status.json` from `arctic-update` says `ready` and `/system-update` exists): the amber "Restart to update" pill on the bar, a card with the number and size of the updates and **Restart and install** (`arctic-power restart`), and one notification per download (remembered in `~/.cache/arctic/update-notified`). Never on the live USB. |
| Power menu | `PowerMenu.qml` | Under the power item or Super+Esc: Settings, Lock screen, Log out, Suspend, Restart, Shut down (live: Settings, Restart, Shut down). Runs `arctic-power <action>`; Settings runs `arctic-settings`. |
| Keyboard shortcuts | `KeysSheet.qml` | Super+/: `keys.txt` from `~/.local/share/arctic` or `/usr/share/arctic`. |
| OSD | `Osd.qml`, `AudioService.qml` | 280×48 frosted pill, bottom centre. Follows PipeWire volume changes directly; brightness when `arctic-osd` calls `arctic-shell-ipc osd brightness` (brightnessctl). 1.2 s, then fades. |
| Lock screen | `LockScreen.qml`, `pam/arctic-lock` | ext-session-lock (the session stays locked if the shell dies) + PAM (`pam_unix`, from this folder). Blurred wallpaper under frost, clock, avatar (`~/.face` or your initial), name, password field with focus / error / success rings, battery, Wi-Fi and power bottom-right. Off on the live USB. |
| Live welcome | `LiveWelcome.qml` | "You're trying Arctic Linux" card (Install Arctic Linux / Keep trying), once per boot via `arctic-welcome`, and the Install tile bottom-left. On the desktop layer, under windows. |
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
into fades.

Icons and app tiles come from the design system's bundle: `assets/design-data.js` is generated
by `node dev/export-design-assets.cjs <design>/components/bundle.js` and drawn in token colours
by `assets/Icons.js`.

## IPC

`arctic-shell-ipc <target> <function>` (wraps `quickshell ipc -p <shell> call`). Exits non-zero
when the shell isn't running, so the `arctic-*` helpers fall back to fuzzel, swaylock or
notifications.

| Target | Functions |
|---|---|
| `launcher` | `toggle`, `open`, `close`, `search <text>` (e.g. `"=12*4"`) |
| `apps` | `install` (Get apps), `remove` (Remove apps), `open <page>` / `source <name>` (flathub, fedora, web, terminal, remove[/tab], console), `search <page> <text>`, `uninstall <desktop-id>`, `toggle` |
| `wallpapers` | `toggle`, `open` |
| `power` | `toggle` |
| `keys` | `toggle` |
| `osd` | `volume`, `brightness` |
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
