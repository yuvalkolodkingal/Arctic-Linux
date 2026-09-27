# Arctic Linux dotfiles (Mango desktop)

The Arctic Linux desktop, built from the design system in [`../design`](../design)
([brand book](../design/brand-book.md), [platforms](../design/guidelines/10-platforms.md),
[terminal and fetch](../design/guidelines/30-terminal-and-fetch.md)).
It covers the Mango window manager, the top bar, launcher, notifications and on-screen display,
lock screen, kitty, zsh with the animated fox greeting, GTK colours, wallpapers, and switching
between the two themes: **Winter** (light) and **Polar night** (dark).

## Install

```sh
./install.sh --deps             # Fedora: installs the packages, then the dotfiles into $HOME
./install.sh                    # dotfiles only (replaced files are backed up first)
./install.sh --theme winter     # start in Winter instead of Polar night
./install.sh --target /etc/skel # packaging: copy for new users
```

Then log in to the **Mango** session, or press `Super + Shift + R` in a running one.

## What's where

| Path | What it does | Design spec |
|---|---|---|
| `.config/mango/config.conf` | Entry point: sources the files below in order, then `user.conf` last | — |
| `.config/mango/arctic/look.conf` | 2px borders, 10px radius, 8px gaps, 5 workspaces, frost blur on the bar, launcher and OSD, shadows on floating windows only, 180/120ms fade + scale motion | WindowFrame, Motion, Elevation and frost |
| `.config/mango/arctic/binds.conf` | Every shortcut (cheat sheet: `Super + /`) | Accessibility → Keyboard |
| `.config/mango/arctic/apps.conf` | `Super+Enter/W/E/F` → your terminal, browser, editor, file manager via `arctic-open` | — |
| `.config/mango/arctic/rules.conf` | Floating dialogs, full-screen installer, layer rules for blur and animation | — |
| `.config/mango/arctic/autostart.conf` | Wallpaper, bar, notifications, polkit agent, network applet, clipboard, idle lock | — |
| `.config/waybar/` | 34px frost bar: fox mark, workspaces 1–5, clock, notifications, Bluetooth, tray, network, volume, battery, power; live session adds "Live session" and an amber Install item | TopBar, LiveDesktop |
| `.config/fuzzel/fuzzel.ini` | Launcher: 520px frosted card, 20px radius, amber-soft selection | Launcher |
| `.config/mako/config` | Notifications: 340px raised cards, 14px radius, critical = red edge and no timeout; OSD pill | Notification, OSD |
| `.config/swaylock/config` | Lock screen ring: amber while typing, red when wrong, green when accepted | LockScreen |
| `.config/kitty/` | JetBrains Mono 10.5, amber block cursor, the Arctic palette | Terminal |
| `.config/gtk-3.0`, `gtk-4.0` | GTK and libadwaita colours, amber focus ring | Platforms → GTK |
| `.zshrc`, `.zprofile`, `.bashrc.d/arctic.sh` | Prompt (`~ ❯`, amber arrow), history, completion, the fox greeting | Terminal |
| `.config/arctic/themes/{winter,polar-night}/` | **Generated** colour files for every app above | tokens |
| `.config/arctic/current` | Symlink to the active theme; every app reads its colours through it | Theme switching |
| `.local/bin/arctic-*` | The helper commands below | — |

## Commands

| Command | Does |
|---|---|
| `arctic-theme [winter\|polar-night\|toggle]` | Switch the whole desktop's theme (`Super + Shift + T`) |
| `arctic-wallpaper [snowfield\|aurora\|fox]` | Pick a wallpaper; it follows theme switches |
| `arctic-fetch [--static]` | The animated fox greeting (runs when a terminal opens; any key skips it) |
| `arctic-motion [on\|off]` | Reduced motion: no animations anywhere, still fox |
| `arctic-launcher` | Open or close the launcher (`Super + Space`) |
| `arctic-open terminal\|browser\|editor\|files\|files-tui` | Open the app you picked for a role |
| `arctic-lock` | Lock the screen (`Super + L`) |
| `arctic-power` | Lock, log out, suspend, restart, shut down (`Super + Esc`) |
| `arctic-osd volume\|brightness up\|down`, `volume mute`, `mic mute` | Hardware keys with the on-screen display |
| `arctic-dnd [toggle]` | Do not disturb (`Super + Shift + N`) |
| `arctic-screenshot area\|screen\|window` | `Print`, `Shift + Print`, `Super + Print` |
| `arctic-keys` | Keyboard cheat sheet (`Super + /`) |
| `arctic-start-installer` | Start the installer from the live USB (`Super + I`) |

## Changing things

- **Your own settings** go in files Arctic never overwrites: `~/.config/mango/user.conf`,
  `~/.config/kitty/user.conf`, `~/.zshrc.local`, `~/.config/arctic/default-apps`.
- **Colours** come from the design tokens. Change `design/tokens.json`, re-export
  `design/exports/arctic-tokens.json` from the design system, then run
  `python3 design/tools/gen-desktop-themes.py` to regenerate both themes.
- **Default apps** are read by `arctic-open` from `/etc/arctic/default-apps` (written by the
  installer) and `~/.config/arctic/default-apps`, as `role=command` lines, e.g.
  `browser=gtk-launch org.mozilla.firefox`.

## How this plugs into the OS

The installer copies this tree into `/etc/skel` (package `arctic-desktop-config`), so every new
account starts with it. The installer also writes `/etc/arctic/mango/keyboard.conf` (your keyboard
layout) and `/etc/arctic/default-apps` (the apps you ticked); both are read at login.

## Where this differs from the design

- **Launcher:** fuzzel finds and opens apps. The design's `=` calculator, `>` command mode and file
  or settings results need a custom launcher.
- **Bar keyboard access:** waybar can't be driven from the keyboard, so the design's `Super + B`
  bar focus isn't available. Everything on the bar also has its own shortcut.
- **Lock screen:** swaylock shows the ring over the fox wallpaper. The design's clock, avatar and
  name card, and the blur, need a custom lock screen (planned with the SDDM theme, same QML).
- **Live welcome card:** shown as a notification (click it to install) rather than the frosted
  card in the mockup.
- **Workspaces:** uses waybar's `ext/workspaces`. Fedora's waybar 0.15 has no `mango/workspaces`
  module yet.

## Not yet verified on a running system

These configs are built from the design and checked against the Mango (0.17.3), waybar and
mako sources and docs, but haven't been run on real Fedora + Mango yet. Check in the first VM
boot:

- Frost blur on waybar, fuzzel and the OSD: blur strength vs the design's 28px, and whether
  `blur_layer` also blurs notifications (harmless, since they're opaque).
- mako: `anchor=` inside the `[app-name=arctic-osd]` section (needs mako ≥ 1.5), and the progress
  bar in the OSD.
- fuzzel: `include=`, `placeholder=` and `y-margin=` (needs fuzzel ≥ 1.9).
- Fonts: Figtree ships as `.woff2` from the design; FreeType on Fedora reads WOFF2, but check
  that `fc-list | grep Figtree` finds it. JetBrains Mono comes from `jetbrains-mono-fonts-all`.
