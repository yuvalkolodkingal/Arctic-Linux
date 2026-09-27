# Themes and customisation

Arctic Linux looks the same across the bar, windows, terminal, notifications and lock screen
because everything reads its colours from one theme. This page covers the theme, wallpapers and
the settings files you can change safely.

## Winter and Polar night

![The desktop in the Winter theme](images/theme-winter.png)

There are two themes:

- **Polar night** (dark), the blue-grey coat of the arctic fox in winter. It's the default.
- **Winter** (light), the fox's snow-white coat.

Press `Super + Shift + T` to switch. The bar, launcher, window borders, terminal, notifications,
lock screen and GTK apps all change together, and the Arctic wallpapers switch to their matching
version. Apps that follow the system's light or dark setting switch too.

From a terminal:

```sh
arctic-theme                  # show the current theme
arctic-theme winter           # switch to Winter
arctic-theme polar-night      # switch to Polar night
arctic-theme toggle           # switch to the other one
```

Your choice is remembered (`~/.config/arctic/theme`) and applied each time you log in. The live
USB starts in Polar night, and the login screen uses it too.

## Wallpapers

![The wallpaper picker](images/wallpapers.png)

`Super + Shift + W` opens the wallpaper picker. Arctic Linux has three wallpapers, each in a
Winter and a Polar night version:

| Wallpaper | Used by default for |
|---|---|
| **Snowfield** | Winter |
| **Aurora** | Polar night |
| **Fox** | The login screen |

An Arctic wallpaper follows the theme when you switch. Your own pictures (from
`~/Pictures/Wallpapers`, or any folder you choose with **Choose folder…**) stay as they are.

From a terminal:

```sh
arctic-wallpaper fox                       # an Arctic wallpaper: snowfield, aurora or fox
arctic-wallpaper ~/Pictures/mountains.jpg  # any picture of your own
arctic-wallpaper current                   # print the picture in use
```

## Reduced motion

If animations bother you, turn them off:

```sh
arctic-motion off     # no window animations, the shell only fades, the terminal fox stays still
arctic-motion on      # normal motion again
arctic-motion         # show the current setting
```

This also turns off animations in GTK apps. For the start-up screen, add `arctic.reduce_motion=1`
to the kernel command line; the fox and its dots then stay still.

## The screen frame

The rounded frame around the screen is a setting in `~/.config/arctic/shell.json`:

```json
{
  "frame": false
}
```

Save the file and the frame goes away at once; set it back to `true` to bring it back.

## Default apps

`Super + Enter`, `Super + W`, `Super + E`, `Super + F` and `Super + Shift + F` open your terminal,
browser, editor, file manager and terminal file manager. The installer writes your picks to
`/etc/arctic/default-apps`. To change one for your account, create
`~/.config/arctic/default-apps` with `role=command` lines:

```ini
terminal=foot
browser=gtk-launch org.mozilla.firefox
editor=gtk-launch com.vscodium.codium
files=nautilus
files-tui=kitty -e yazi
```

The roles are `terminal`, `browser`, `editor`, `files` and `files-tui`. Use the app's command, or
`gtk-launch <desktop id>` for Flatpak apps. Lines in your file win over the system file. If the app
you set isn't installed, Arctic falls back to another app that is. The change applies the next
time you press the shortcut.

A terminal set here should accept `-e command` and `--hold`, as kitty, foot and Alacritty do: the
launcher uses it to run commands.

## Your own settings files

Arctic keeps its own settings in `/usr/share/arctic` and updates them there. Put your changes in
these files, which Arctic never overwrites:

| File | For |
|---|---|
| `~/.config/mango/user.conf` | Window manager settings, extra shortcuts and window rules |
| `~/.config/kitty/user.conf` | The kitty terminal |
| `~/.zshrc.local` | zsh |
| `~/.config/arctic/default-apps` | Which app each shortcut opens |
| `~/.config/arctic/shell.json` | Desktop shell settings (the screen frame) |

### Mango settings in `user.conf`

`user.conf` is read last, so a `name=value` line there wins over Arctic's. Some examples:

```ini
# Bigger gaps between windows
gappih=16
gappiv=16
gappoh=16
gappov=16

# Square corners
border_radius=0

# A different keyboard layout for your session
xkb_rules_layout=gb

# An extra shortcut: Super + B opens Firefox
bind=SUPER,b,spawn,firefox
```

Press `Super + Shift + R` to reload.

### Changing a shortcut

Mango uses the first shortcut it reads for a key, so a `bind=` line in `user.conf` can add new
shortcuts but can't replace one of Arctic's. To change Arctic's shortcuts, replace the link to
`binds.conf` with your own copy:

```sh
cp --remove-destination /usr/share/arctic/mango/binds.conf ~/.config/mango/arctic/binds.conf
```

Edit the copy and press `Super + Shift + R`. From then on it stays as you leave it, and Arctic's
updates to that file no longer reach you. To go back to Arctic's version, delete your copy and
restore the link:

```sh
rm ~/.config/mango/arctic/binds.conf
ln -s /usr/share/arctic/mango/binds.conf ~/.config/mango/arctic/
```

The same works for the other files in `~/.config/mango/arctic/`: `look.conf` (borders, gaps,
blur, animations), `input.conf` (keyboard repeat, touchpad), `apps.conf` (app shortcuts),
`rules.conf` (floating windows) and `autostart.conf` (what starts at login).

## Keyboard layout

The installer writes your keyboard layout to `/etc/arctic/mango/keyboard.conf` for your session,
`/etc/arctic/sddm-keyboard.conf` for the login screen, and `/etc/vconsole.conf` for the disk
passphrase prompt. To use a different layout just for your session, put `xkb_rules_layout=` (and
`xkb_rules_variant=` if needed) in `~/.config/mango/user.conf`.

## The fallback desktop

If you'd rather not use the Arctic shell, or it isn't working, Arctic Linux keeps a simpler
desktop built from standard tools: waybar for the bar, fuzzel for the launcher and power menu,
swaylock for the lock screen, and notifications for the rest. Your shortcuts stay the same.

Add this line to `~/.config/mango/user.conf`, then log out and back in:

```ini
env=ARCTIC_SHELL,waybar
```

Delete the line to go back. The fallback has no `=` calculator, `>` commands, Get apps console or
wallpaper picker; those are part of the Arctic shell.

## Changing the colours themselves

The theme files in `/usr/share/arctic/themes/` are generated from the design system's tokens. To
make your own variant, copy a theme folder to `~/.config/arctic/themes/` under the same name
(`winter` or `polar-night`) and edit it; `arctic-theme` uses your copy first. To change the colours
for everyone, see [Design system](Design-System).
