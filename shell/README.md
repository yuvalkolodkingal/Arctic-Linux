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

It needs `quickshell`, `python3`, `python3-pillow` (wallpaper thumbnails), `python3-pyte`
(the Get apps terminal) and `glib2` (`gdbus`, to check who owns notifications); the bar uses
NetworkManager (`nmcli`), PipeWire, UPower, BlueZ, Mango (`mmsg`, the keyboard layout) and
`brightnessctl` when they are there and hides what isn't. The shell is the notification server;
mako is only the fallback (the waybar session, or when the shell can't take the name).

## What's in it

| Surface | Files | Notes |
|---|---|---|
| Top bar | `Bar.qml`, `BarItem.qml`, `BarTooltip.qml`, `Workspaces.qml`, `scripts/workspaces.py` | 34px frost, 1px `line` bottom. Fox mark (launcher), workspaces 1–5 (active amber pill, occupied ring, empty muted, urgent error ring), clock with tabular figures, notifications bell (the notification centre; right click: do not disturb), keyboard layout (with two or more), Bluetooth, tray, network, volume, battery (hidden without one), power. Live USB: "Live session" tag and the amber Install item. Tooltips on every icon-only item. |
| Screen frame | `ScreenFrame.qml` | Ground-coloured surround with a `line` hairline. It reserves its width on each edge, so Mango keeps its 8px gap inside it and window corners are concentric with the frame's. `{"frame": false}` in `~/.config/arctic/shell.json` turns it off. |
| Launcher | `Launcher.qml`, `LauncherSearch.js`, `Calc.js`, `AppTile.qml` | Super+Space. 520px frosted card that hangs from the bar over a scrim; drag the grip to dock it to any edge. Apps (design app tiles for the Arctic apps), `=` calculator (a small parser: arithmetic only, never `eval`), `>` run a command (Shift+Enter: in your terminal, via `arctic-open terminal -e`). Empty query: Apps, Get apps, Wallpapers, Settings, Fetch (+ Install Arctic Linux on the live USB). |
| Get apps | `InstallConsole.qml`, `PackageSearch.js`, `scripts/install-terminal.py`, `scripts/package-index.py` | Type an app name to install it, or a `dnf` / `flatpak` command. `dnf install|remove|upgrade` run as `sudo dnf …`, queries without sudo, `flathub:<id>` or `flatpak install flathub …` through Flatpak — in a real PTY, so sudo's password and dnf's `[y/N]` are answered in the console. Password input is masked, never logged or stored; a reply typed for a prompt that has since changed is refused. Ctrl+C stops the job. Tab completes names from a cached index (`~/.cache/arctic/packages.txt` from `dnf5 repoquery`, `flathub.txt` from `flatpak remote-ls`), refreshed in the background once a day. |
| Wallpapers | `Wallpapers.qml`, `scripts/wallpapers.py` | Searchable thumbnail grid. The Arctic wallpapers (from `~/.local/share/arctic/wallpapers` or `/usr/share/backgrounds/arctic`) show the active theme's variant and follow Winter / Polar night; your own pictures come from `~/Pictures/Wallpapers` or a folder you choose. Applies through `arctic-wallpaper`. The "Match colours to wallpaper" switch is `arctic-theme auto on\|off` (read from `~/.config/arctic/settings.json`). Thumbnails (Pillow; SVGs via rsvg-convert) in `~/.cache/arctic/thumbs`, settings in `~/.config/arctic/wallpapers.json`. |
| Updates | `UpdateIndicator.qml`, `UpdatePopover.qml`, `UpdateService.qml`, `UpdateStatus.js` | While updates wait for the next restart (`/var/lib/arctic/update-status.json` from `arctic-update` says `ready` and `/system-update` exists): the amber "Restart to update" pill on the bar, a card with the number and size of the updates and **Restart and install** (`arctic-power restart`), and one notification per download (remembered in `~/.cache/arctic/update-notified`). Never on the live USB. |
| Notifications | `NotificationService.qml`, `NotificationRules.js`, `Toasts.qml`, `ToastCard.qml`, `NotificationCard.qml`, `NotificationCenter.qml`, `DndService.qml` | Owns `org.freedesktop.Notifications` (stops a D-Bus-activated mako, starts `arctic-session mako --fallback` if nobody could take the name, leaves dunst/swaync alone and says so). Toasts: 340px cards top-right on the focused screen, newest on top, 3 plus "N more"; low 5 s, normal 8 s, urgent until closed (red edge + "Urgent"), the app's own timeout; hover pauses; click = default action or the app's window. Centre under the bell (Super+Alt+N): do not disturb (1 hour, until tomorrow, until turned off; schedule from Settings), notifications grouped by app (three newest open), clear per app / all, full keyboard use. History (50) in `~/.local/state/arctic/notifications/` (0700): `history.json`, `dnd.json`, `apps.json`; Settings writes `~/.config/arctic/notifications.json` (schedule, per-app rules). Do not disturb lets urgent notifications, Arctic's alerts (`-h boolean:x-arctic-alert:true`) and allowed apps through (`NotificationRules.js`). |
| Keyboard layout | `KeyboardService.qml`, `KeyboardItem.qml`, `KeyboardPanel.qml`, `scripts/keyboard.py` | The bar chip (`EN`, only with two or more layouts): click = next layout, right click = the layout menu. Layouts from Mango's config (installer's `/etc/arctic/mango/keyboard.conf`, Settings' `settings.conf`, `user.conf`) with names from `evdev.xml`; the active one from `mmsg watch keyboardlayout`; switching with `mmsg dispatch switch_keyboard_layout,N` (N from 1; 0 cycles). |
| Power menu | `PowerMenu.qml` | Under the power item or Super+Esc: Settings, Lock screen, Log out, Suspend, Restart, Shut down (live: Settings, Restart, Shut down). Runs `arctic-power <action>`; Settings runs `arctic-settings`. |
| Keyboard shortcuts | `KeysSheet.qml` | Super+/: `keys.txt` from `~/.local/share/arctic` or `/usr/share/arctic`. |
| OSD | `Osd.qml`, `AudioService.qml` | 280×48 frosted pill, bottom centre. Follows PipeWire volume changes directly; brightness when `arctic-osd` calls `arctic-shell-ipc osd brightness` (brightnessctl); the keyboard layout's name when it changes (not the lock screen's reset). 1.2 s, then fades. |
| Lock screen | `LockScreen.qml`, `pam/arctic-lock` | ext-session-lock (the session stays locked if the shell dies) + PAM (`pam_unix`, from this folder). Blurred wallpaper under frost, clock, avatar (`~/.face` or your initial), name, password field with focus / error / success rings, battery, Wi-Fi and power bottom-right, how many notifications arrived while locked, the keyboard layout beside the field (locking switches to the first layout), "Caps Lock is on". Off on the live USB. |
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
| `apps` | `install` (Get apps), `toggle` |
| `wallpapers` | `toggle`, `open` |
| `power` | `toggle` |
| `keys` | `toggle` |
| `osd` | `volume`, `brightness` |
| `lock` | `lock`, `isLocked` (true once the compositor confirms the lock covers every screen) |
| `welcome` | `open` |
| `dnd` | `refresh` (for arctic-dnd with mako) |
| `notifications` | `center` / `toggle`, `open`, `close`, `dismiss` (newest pop-up), `dismissAll`, `invoke` (newest), `count`, `history` (JSON lines), `clearHistory`, `reload` (Settings wrote notifications.json), `dnd <on\|off\|toggle\|1h\|tomorrow\|status>` → `on`/`off`, or `unowned` when another daemon has notifications |
| `keyboard` | `next`, `set <index>`, `menu` |
| `updates` | `toggle` (the updates card, only while updates wait), `refresh` |
| `shell` | `reload` (theme, motion, settings), `live` |

## Developing

```sh
python3 -m unittest discover -s shell/tests     # PTY console, command building, package index, wallpapers
node shell/tests/test-package-search.cjs        # completion
node shell/tests/test-launcher.cjs              # launcher ranking, calculator
node shell/tests/test-update-status.cjs         # the "Restart to update" logic
node shell/tests/test-notification-rules.cjs    # do not disturb, per-app rules, history, grouping
/usr/lib64/qt6/bin/qmllint -I /usr/lib64/qt6/qml shell/*.qml
shell/dev/headless.sh --fixtures demo ipc launcher search ze sleep 1 shot launcher
```

`dev/headless.sh` runs the shell in a headless sway (1280×800) with a throwaway HOME (the
dotfiles installed with `install.sh --target`) and saves screenshots to `dev/screenshots/`
(`--theme winter`, `--live` = `ARCTIC_FORCE_LIVE=1`, which exists only for such tests;
`ARCTIC_UPDATE_STATUS=<file>` shows the updates pill from a status file of your own, with a
`/system-update` link in place; `--mako` starts mako first, to test the hand-over of the
notification name; `sh notify-send …` steps show toasts).

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
