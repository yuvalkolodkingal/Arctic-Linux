# Themes and customisation

Arctic Linux looks the same across the bar, windows, terminal, notifications, lock screen and your
apps because everything reads its colours from one theme. The theme can be Winter, Polar night,
or one made from your wallpaper. This page covers themes, wallpapers, which apps follow the theme
and the settings files you can change safely.

Most of this can also be changed in **Arctic Settings** (`Super + S`, then **Appearance**); see
[Settings](Settings#appearance). This page shows the files and commands behind it.

## Winter and Polar night

![The desktop in the Winter theme](images/theme-winter.png)

There are two built-in themes:

- **Polar night** (dark), the blue-grey coat of the arctic fox in winter. It's the default.
- **Winter** (light), the fox's snow-white coat.

Press `Super + Shift + T` to switch between light and dark. The bar, launcher, window borders,
terminal, notifications, lock screen and your apps all change together, and the Arctic wallpapers
switch to their matching version.

## Colours from your wallpaper

When you use a picture of your own as the wallpaper, Arctic Linux makes a theme from it: the
accent colour (the amber of the built-in themes) takes the picture's main colour, and the
backgrounds and text get a hint of its tint. Everything that follows the theme changes with it.
This is on by default, and it's called **Match colours to wallpaper**: a switch at the bottom of
the wallpaper picker (`Super + Shift + W`), and also in Settings under **Appearance**.

- **Arctic's own wallpapers** (Snowfield, Aurora and Fox) keep the Winter and Polar night colours,
  so a new install looks exactly as designed.
- **Light or dark:** by default the picture decides (a bright picture gives a light theme, a dark
  one a dark theme). You can fix it to light or dark instead (`arctic-theme mode`, or **Light or
  dark** in Settings). `Super + Shift + T` flips it.
- **Always readable.** However colourful the picture, text keeps a contrast of at least 7:1 on its
  background, secondary text and the accent's text at least 4.5:1, and the terminal's colours at
  least 4.5:1 on the terminal background (the WCAG 2 contrast levels). Grey or nearly colourless
  pictures keep the built-in colours. The theme is only remade when you change the picture or the
  light/dark setting, and making it takes a fraction of a second.
- **Turning it off** keeps your picture but goes back to Winter or Polar night.

## The `arctic-theme` command

```sh
arctic-theme                     # the theme in use: winter, polar-night, wallpaper, or one of yours
arctic-theme list                # the themes you can switch to
arctic-theme set winter          # switch to Winter (also: polar-night, wallpaper, or your own)
arctic-theme auto on             # colours follow the wallpaper (off: back to Winter / Polar night)
arctic-theme mode dark           # light or dark for wallpaper colours: auto, dark or light
arctic-theme toggle              # light <-> dark, the same as Super + Shift + T
arctic-theme reload              # apply the theme to running apps again and run the hooks
arctic-theme current --json      # the theme's name, mode, colours and settings, as JSON
```

- `set` with any theme but `wallpaper` turns **Match colours to wallpaper** off. `set wallpaper`
  makes a theme from the current wallpaper now, even an Arctic one.
- `auto` and `mode` without a value print the current setting.
- The version 0.1 commands still work: `arctic-theme winter`, `arctic-theme polar-night`,
  `arctic-theme light` and `arctic-theme dark`.

Your choice is remembered and applied each time you log in. The live USB starts in Polar night,
and the login screen uses it too.

### Where it's kept

| File | Holds |
|---|---|
| `~/.config/arctic/settings.json` | `"auto_colors"` (on when missing), `"wallpaper_mode"` (`auto`, `dark` or `light`) and `"zen_theme"` (off). Other programs may add keys; `arctic-theme` keeps them. |
| `~/.config/arctic/current` | A link to the folder of the theme in use. Apps read their colours through it. |
| `~/.config/arctic/theme` | The name of the theme in use (the desktop shell watches it). |
| `~/.config/arctic/themes/wallpaper/` | The theme made from your wallpaper |
| `/usr/share/arctic/themes/` | Winter and Polar night |

## Which apps follow the theme

| What | How | When it changes |
|---|---|---|
| The Arctic shell (bar, launcher, pop-ups, lock screen), Arctic Settings | read the theme directly | at once |
| Mango (window borders), kitty, notifications (mako), the fallback bar, fuzzel and swaylock | colour files in the theme folder | at once |
| **GTK 3 apps** (Thunar, Inkscape, GIMP, Zen's menus, …) | the **adw-gtk3** theme, recoloured with the theme's colours | light/dark at once; colours when the app next starts |
| **GTK 4 / libadwaita apps** (Nautilus, Celluloid, GNOME apps) | the system's light/dark setting and the theme's colours | light/dark at once; colours when the app next starts |
| **Qt 5 and Qt 6 apps** (VLC, OBS, KDE apps) | **qt5ct** and **qt6ct**, with the theme's palette, Figtree and JetBrains Mono and Adwaita icons | within a few seconds |
| **Flatpak apps** | GTK Flatpaks read the same colours (Arctic gives every Flatpak read-only access to your GTK and font settings, and installs the adw-gtk3 theme for Flatpak) | as GTK |
| **Zed** (Flatpak or native) | an "Arctic" theme, copied into Zed's themes folder | at once |
| **yazi**, **btop** | theme files | next start |
| **zsh** prompt, completion menu, suggestions and syntax highlighting | a colour file in the theme folder | at the next prompt |
| **fzf** | an options file (your own `FZF_DEFAULT_OPTS` still apply on top) | every run |
| **fastfetch**, **neofetch** | layouts in the theme folder: the fox, keys and title in the theme's colours ([Terminal and shell](Terminal-and-Shell#fastfetch-and-neofetch)) | every run |
| **foot**, **Alacritty** | the same palette as kitty | new windows |
| **Zen Browser** | light/dark follows the system; the accent colour only with `arctic-theme zen on` | next start |
| Firefox, Chromium, Collabora Office, Electron apps | light/dark follows the system | at once |

Icons and the mouse pointer are Adwaita everywhere (the pointer size is set in Settings).

Some apps keep their own themes and aren't recoloured: Helix, Neovim, VSCodium, ONLYOFFICE,
Steam, mpv's on-screen controls and fish (which uses the terminal's colours).

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
`~/Pictures/Wallpapers`, or any folder you choose with **Choose folder…**) stay as they are, and
with **Match colours to wallpaper** on, the desktop takes its colours from them.

To add pictures, use **Settings → Appearance → Add pictures…** or drag them there from Files;
Settings copies them into your folder and can rename or delete them. **Settings → Appearance →
Wallhaven** finds wallpapers on [wallhaven.cc](https://wallhaven.cc) and sets one with a click
(it lands in `~/Pictures/Wallpapers/wallhaven`, so the picker lists it too). See
[Settings](Settings#appearance).

From a terminal:

```sh
arctic-wallpaper fox                       # an Arctic wallpaper: snowfield, aurora or fox
arctic-wallpaper ~/Pictures/mountains.jpg  # any picture of your own (the colours follow it)
arctic-wallpaper current                   # print the picture in use
```

PNG, JPEG, WebP, GIF, BMP, TIFF and SVG pictures all work.

## Reduced motion

If animations bother you, turn them off with **Reduce motion** in Settings (**Appearance**), or:

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

`Super + Enter`, `Super + B`, `Super + E`, `Super + F` and `Super + Shift + F` open your terminal,
browser, editor, file manager and terminal file manager. The installer writes your picks to
`/etc/arctic/default-apps`. The easiest way to change them is **Default apps** in Settings
(`Super + S`), which also sets the apps that open links and files. By hand, create
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
| `~/.config/arctic/settings.json` | Theme settings (see [Where it's kept](#where-its-kept)) |
| `~/.config/arctic/theme-hooks.d/` | Your own theme hooks (see [Theme hooks](#theme-hooks)) |

Arctic Settings writes its own file, `~/.config/mango/settings.conf`, for the window, keyboard,
mouse, shortcut, display and startup settings you change there. It's read before `user.conf`, so a
line in `user.conf` still wins; Settings says so next to a setting you've set there.

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

# An extra shortcut: Super + Alt + F opens Firefox
bind=SUPER+ALT,f,spawn,firefox
```

Press `Super + Shift + R` to reload.

### Changing a shortcut

Mango uses the first shortcut it reads for a key, so a `bind=` line in `user.conf` can add new
shortcuts but can't replace one of Arctic's. If a later update gives one of your keys to Arctic,
Settings > Shortcuts tells you that your shortcut no longer runs. To change Arctic's shortcuts,
replace the link to `binds.conf` with your own copy:

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

## Theme hooks

After every theme switch, `arctic-theme` runs the programs in `/usr/share/arctic/theme-hooks.d/`
and `~/.config/arctic/theme-hooks.d/`, in file-name order. This is how apps that can't read the
theme folder themselves are kept up to date. Arctic ships four:

| Hook | Does |
|---|---|
| `10-gtk` | copies the theme's GTK colours to `~/.config/gtk-3.0/` and `~/.config/gtk-4.0/` (Flatpak apps can't see the theme folder) |
| `20-qt` | makes running Qt apps read the new palette |
| `30-zed` | copies the Arctic theme into Zed's themes folder |
| `40-zen` | adds or removes the Zen Browser accent colour (only with `arctic-theme zen on`) |

To add your own, put an executable file in `~/.config/arctic/theme-hooks.d/`. It gets
`ARCTIC_THEME_DIR` (the theme folder), `ARCTIC_THEME_MODE` (`dark` or `light`) and
`ARCTIC_THEME_NAME`, for example:

```sh
#!/bin/sh
# ~/.config/arctic/theme-hooks.d/50-my-app
cp "$ARCTIC_THEME_DIR/kitty.conf" ~/.config/my-app/colors.conf
```

A file of yours with the same name as one of Arctic's replaces it, and a file of that name that
isn't executable turns Arctic's hook off. Hooks must be quick: each is stopped after 5 seconds,
and one that fails is reported but never stops the switch.

## Making your own theme

A theme is a folder: `theme.json` for the shell, `gtk.css`, and a colour file for each app,
all generated from one `palette.json` by the theme engine, `arctic-themegen`. To make your own,
start from a built-in palette, change the colours, and render it into
`~/.config/arctic/themes/<name>/`:

```sh
arctic-themegen builtin polar-night > ~/my-palette.json
# edit ~/my-palette.json: set "name" to "mine", "label" to "Mine", and change the colours
arctic-themegen check --palette ~/my-palette.json     # checks the contrast guarantees
arctic-themegen render --palette ~/my-palette.json --out ~/.config/arctic/themes/mine
arctic-theme set mine
```

A theme of yours with the same name as a built-in one (`winter` or `polar-night`) is used instead
of it. Your own app templates (files ending in `.tmpl`, using the same `{{role}}` placeholders)
go in `~/.config/arctic/templates/`; `arctic-theme` adds them to the themes it makes from your
wallpaper. To change the colours for everyone, see [Design system](Design-System).
