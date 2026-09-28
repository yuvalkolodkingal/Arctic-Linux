# Arctic Linux dotfiles (Mango desktop)

The Arctic Linux desktop, built from the design system in [`../design`](../design)
([brand book](../design/brand-book.md), [platforms](../design/guidelines/10-platforms.md),
[terminal and fetch](../design/guidelines/30-terminal-and-fetch.md)).
It covers the Mango window manager, the desktop shell, notifications, kitty, zsh with the
animated fox greeting, GTK colours, wallpapers, and switching between the two themes:
**Winter** (light) and **Polar night** (dark).

The shell — bar, launcher with Get apps, wallpaper picker, power menu, OSD, lock screen, polkit
dialog and the live welcome card — is the Quickshell shell in [`../shell`](../shell), which
grew out of the user's own Quickshell setup. These dotfiles start it (`arctic-session shell`)
and every `arctic-*` helper drives it over IPC (`arctic-shell-ipc`), falling back to the
waybar / fuzzel / swaylock / notification versions kept here when it isn't running.

## Install

```sh
./install.sh --deps             # Fedora: installs the packages, then the dotfiles into $HOME
./install.sh                    # dotfiles only (replaced files are backed up first)
./install.sh --theme winter     # start in Winter instead of Polar night
./install.sh --target /etc/skel # packaging: copy for new users (never copies the shell)
./install.sh --no-shell         # into $HOME, but use the packaged shell in /usr/share/arctic/shell
```

Installing into `$HOME` also copies [`../shell`](../shell) to `~/.config/quickshell/arctic`, so
the desktop works without the `arctic-shell` package; `arctic-shell` prefers that copy.

Then log in to the **Mango** session, or press `Super + Shift + R` in a running one.

## What's where

| Path | What it does | Design spec |
|---|---|---|
| `.config/mango/config.conf` | Entry point: sources the files below in order, then `user.conf` last (packaged: the files below live in `/usr/share/arctic/mango`, see below) | — |
| `.config/mango/arctic/look.conf` | 2px borders, 10px radius, 8px gaps, 5 workspaces, frost blur on the bar, launcher and OSD, shadows on floating windows only, 180/120ms fade + scale motion | WindowFrame, Motion, Elevation and frost |
| `.config/mango/arctic/binds.conf` | Every shortcut (cheat sheet: `Super + /`) | Accessibility → Keyboard |
| `.config/mango/arctic/apps.conf` | `Super+Enter/W/E/F` → your terminal, browser, editor, file manager via `arctic-open` | — |
| `.config/mango/arctic/rules.conf` | Floating dialogs, full-screen installer, layer rules for blur and animation | — |
| `.config/mango/arctic/autostart.conf` | Theme, the shell (bar, launcher, OSD, lock, polkit agent), notifications, network applet, clipboard, idle lock, live welcome | — |
| `.config/arctic/shell.json` | Shell settings: `{"frame": true}` (the rounded screen frame) | — |
| `.config/waybar/` | **Fallback bar** (`ARCTIC_SHELL=waybar`): the same TopBar in waybar | TopBar, LiveDesktop |
| `.config/fuzzel/fuzzel.ini` | **Fallback launcher**: 520px frosted card, 20px radius, amber-soft selection | Launcher |
| `.config/mako/config` | Notifications: 340px raised cards, 14px radius, critical = red edge and no timeout; OSD pill | Notification, OSD |
| `.config/swaylock/config` | **Fallback lock**: ring amber while typing, red when wrong, green when accepted | LockScreen |
| `.config/fontconfig/conf.d/60-arctic-figtree.conf` | Finds the design's Figtree files, which name their family "Figtree Light" | Typography |
| `.config/kitty/` | JetBrains Mono 10.5, amber block cursor, the Arctic palette | Terminal |
| `.config/gtk-3.0`, `gtk-4.0` | GTK (adw-gtk3) and libadwaita colours from `arctic-colors.css` (a link to the theme's `gtk.css`, which the theme hook turns into a copy that Flatpak apps can read), amber focus ring, Adwaita icons and cursor, Figtree | Platforms → GTK |
| `.config/qt5ct`, `.config/qt6ct` | Qt 5 (VLC) and Qt 6 apps: Fusion with the active theme's palette (`QT_QPA_PLATFORMTHEME=qt6ct`, set in `mango/arctic/look.conf` and `environment.d`) | Platforms |
| `.config/zed/settings.json` | Zed: the "Arctic" theme (the theme hook puts it in Zed's themes folder, also for the Flatpak) and the Arctic fonts | — |
| `.config/yazi/theme.toml`, `.config/btop/` | Links to the active theme's yazi and btop themes | — |
| `.config/fastfetch/config.jsonc` | Link to the active theme's fastfetch layout (the theme folder also has `fastfetch/neofetch.jsonc`, for `neofetch`) | — |
| `.config/foot`, `.config/alacritty` | The other terminals, with kitty's palette from the active theme | Terminal |
| `.zshrc`, `.zprofile`, `.bashrc.d/arctic.sh` | Prompt (`~ ❯`, amber arrow; the theme's `zsh/colors.zsh`), history, completion, fzf colours (`fzf/fzfrc`), the fox greeting | Terminal |
| `.config/arctic/themes/{winter,polar-night}/` | **Generated** (by the theme engine, `design/themegen`) colour files for every app above, `theme.json` (every token) for the shell and `palette.json` | tokens |
| `.config/arctic/current` | Symlink to the active theme; every app reads its colours through it | Theme switching |
| `.local/bin/arctic-*` | The helper commands below | — |

## Commands

| Command | Does |
|---|---|
| `arctic-shell [--foreground\|--restart\|--stop\|--path]` | Start the desktop shell (Quickshell) |
| `arctic-shell-ipc <target> <function>` | Talk to the shell, e.g. `arctic-shell-ipc launcher toggle` (targets in [`../shell/README.md`](../shell/README.md)) |
| `arctic-theme [set <theme>\|toggle\|auto on\|off\|mode auto\|dark\|light\|list\|current]` | Switch the whole desktop's theme (`Super + Shift + T` toggles light / dark); the shell restyles live. With auto colours on (the default) your own wallpapers colour the desktop |
| `arctic-themegen render\|palette\|builtin\|check` | The theme engine: render a palette into a theme folder, make a palette from a picture |
| `arctic-wallpaper [snowfield\|aurora\|fox\|<picture>]` | Pick a wallpaper; the Arctic ones follow theme switches, your pictures set the colours when auto colours are on. Also the shell's picker (`Super + Shift + W`, with a "Match colours to wallpaper" switch) |
| `arctic-fetch [--static]` | The animated fox greeting (runs when a terminal opens; any key skips it); its lines are fastfetch's (`.local/share/arctic/fastfetch/greeting.jsonc`) |
| `arctic-fetch --info os\|base\|wm\|shell\|theme\|updates` | One line for the fastfetch layouts, e.g. "Arctic Linux 0.2 (Fedora 44)" |
| `fastfetch`, `neofetch` | The fox and a system summary, in the active theme's colours (`.config/fastfetch/config.jsonc` links to the theme's layout); `neofetch` is fastfetch with neofetch's layout |
| `arctic-motion [on\|off]` | Reduced motion: no animations anywhere, still fox |
| `arctic-launcher ["=12*4"]` | Open or close the launcher (`Super + Space`), optionally with something typed |
| `arctic-open terminal\|browser\|editor\|files\|files-tui` | Open the app you picked for a role |
| `arctic-open terminal [--hold] -e <command…>` | Run a command in the terminal you picked (the launcher's terminal apps, Fetch, Shift+Enter) |
| `arctic-lock` | Lock the screen (`Super + L`); off in the live session |
| `arctic-power [lock\|logout\|suspend\|restart\|poweroff]` | The power menu (`Super + Esc`), or do it now |
| `arctic-osd volume\|brightness up\|down`, `volume mute`, `mic mute` | Hardware keys with the on-screen display |
| `arctic-dnd [toggle]` | Do not disturb (`Super + Shift + N`) |
| `arctic-screenshot area\|screen\|window` | `Print`, `Shift + Print`, `Super + Print` |
| `arctic-keys` | Keyboard cheat sheet (`Super + /`) |
| `arctic-settings [page]` | Settings (`Super + S`): appearance, windows, displays, keyboard and mouse, shortcuts, default apps, network, sound, updates, power, startup apps ([`../settings/README.md`](../settings/README.md)) |
| `arctic-shell-ipc apps install|remove` | Get apps: install or remove apps (`Super + Shift + A`) |
| `arctic-session shell\|mako\|…` | Start one session service once (used by autostart) |
| `arctic-welcome` | The live USB's welcome card, once per boot |
| `arctic-start-installer` | Start the installer from the live USB (`Super + I`) |

## Changing things

- **Settings** (`Super + S`) writes what you change there to `~/.config/mango/settings.conf`,
  which `config.conf` reads just before `user.conf`.
- **Your own settings** go in files Arctic never overwrites: `~/.config/mango/user.conf`,
  `~/.config/kitty/user.conf`, `~/.zshrc.local`, `~/.config/arctic/default-apps`.
- **Colours** come from the design tokens. Change `design/tokens.json`, re-export
  `design/exports/arctic-tokens.json` from the design system, then run
  `python3 design/tools/gen-desktop-themes.py` to regenerate both themes (the per-app files
  are templates in `design/themegen/templates/`).
- **Colours from your wallpaper** are on by default (`arctic-theme auto on|off`): a picture of
  yours becomes the `wallpaper` theme in `~/.config/arctic/themes/wallpaper`; Arctic's own
  wallpapers keep Winter / Polar night. Scripts in `~/.config/arctic/theme-hooks.d/` run after
  every theme change (with `ARCTIC_THEME_DIR` and `ARCTIC_THEME_MODE`); extra templates of
  your own go in `~/.config/arctic/templates/`.
- **Default apps** are read by `arctic-open` from `/etc/arctic/default-apps` (written by the
  installer) and `~/.config/arctic/default-apps`, as `role=command` lines, e.g.
  `browser=gtk-launch org.mozilla.firefox`.

## How this plugs into the OS

The package `arctic-desktop-config` puts this tree into `/etc/skel`, so every new account starts
with it. The parts Arctic keeps up to date are installed once, in `/usr/share/arctic`, and the
home directory only points at them, so `dnf upgrade` reaches accounts that already exist:

| In the home directory | Is |
|---|---|
| `~/.config/mango/arctic/*.conf` | links to `/usr/share/arctic/mango/*.conf`. To change one of these files, replace its link with a copy (see `config.conf`); a copy stays as you leave it |
| `~/.config/arctic/current` | a link to `/usr/share/arctic/themes/<theme>` (`arctic-theme` switches it; a theme folder of your own in `~/.config/arctic/themes/` is used first) |
| `keys.txt` | not copied: the cheat sheet is read from `/usr/share/arctic/keys.txt` unless `~/.local/share/arctic/keys.txt` exists |

The other files (kitty, GTK, Qt, Zed, btop, waybar, fuzzel, mako, zsh) are ordinary copies that
are yours to edit. The links into `~/.config/arctic/current` (yazi's `theme.toml`, btop's
`themes/arctic.theme`, GTK's `arctic-colors.css`) follow the theme; replace one with a copy to
keep it as you leave it. After a theme switch, the hooks in `/usr/share/arctic/theme-hooks.d`
update what can't follow a link (GTK for Flatpak apps, running Qt apps, Zed; docs/BUILD-SPEC.md
§3.1). `install.sh` (no packages) copies everything, including the files above, into the home
directory. The installer also writes `/etc/arctic/mango/keyboard.conf` (your keyboard layout)
and `/etc/arctic/default-apps` (the apps you ticked); both are read at login.

## The fallback desktop

Put `env=ARCTIC_SHELL,waybar` in `~/.config/mango/user.conf` (or leave Quickshell uninstalled)
and the session starts waybar, uses fuzzel as the launcher and power menu, swaylock as the lock
screen, lxqt-policykit for passwords and a notification for the live welcome. Every helper
tries the shell first and falls back on its own, so keybinds are the same either way.

## Where this differs from the design

- **Launcher and popovers** hang from the bar and can be docked to any screen edge (from the
  original Quickshell setup) rather than floating 120px below it; the screen frame is also the
  original shell's.
- **Bar keyboard access:** the design's `Super + B` bar focus isn't there yet. Everything on the
  bar also has its own shortcut.
- **Lock screen:** "N notifications hidden" isn't shown, because mako can't count hidden
  notifications.
- **Fallback only:** waybar's workspaces use `ext/workspaces` (Fedora's waybar 0.15 has no
  `mango/workspaces` module); fuzzel has no `=` / `>` modes.

## Not yet verified on a running system

These configs are built from the design and checked against the Mango (0.17.3), waybar and
mako sources and docs. The shell was run and screenshotted under a headless sway on Fedora 44
(`../shell/dev/headless.sh`), but not yet on real Fedora + Mango. Check in the first VM boot:

- The shell's layer rules (`rules.conf`, `^arctic-…$` regexes): the bar blurred, the frame and
  popovers not; the frame's exclusive zones keeping tiled windows 8px inside it.
- `mmsg watch all-tags` / `watch all-monitors` driving the workspaces and the focused screen.
- The lock screen's PAM service (`pam_unix` from the shell's `pam/` folder) on a real account.
- Frost blur on waybar, fuzzel and the OSD (fallback desktop): blur strength vs the design's
  28px, and whether `blur_layer` also blurs notifications (harmless, since they're opaque).
- mako: `anchor=` inside the `[app-name=arctic-osd]` section (needs mako ≥ 1.5), and the progress
  bar in the OSD.
- fuzzel: `include=`, `placeholder=` and `y-margin=` (needs fuzzel ≥ 1.9).
- Fonts: Figtree ships as `.woff2` from the design; FreeType on Fedora reads WOFF2, but check
  that `fc-list | grep Figtree` finds it. JetBrains Mono comes from `jetbrains-mono-fonts-all`.
