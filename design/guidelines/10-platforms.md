# Platforms

How the tokens land on each part of the system. Ready files are in `assets/Exports/`; everything is generated from `tokens.json`, so change a value there and regenerate.

| Surface | Tech | File | Notes |
|---|---|---|---|
| Any CSS (web, docs) | CSS custom properties | `arctic-tokens.css` | `:root`/`[data-theme="light"]` = Winter, `[data-theme="dark"]` = Polar night; spacing, radii, motion on `:root`. |
| Everything else | Flat JSON | `arctic-tokens.json` | `themes.light` / `themes.dark` colour maps, `ramps`, `type`, `spacing`, `radius`, `shadow`, `duration`, `easing`, `terminal`. Feed it to your template tool (Jinja, matugen-style templates, a Python script). |
| GTK 3/4, libadwaita | `@define-color` | `gtk-arctic-winter.css`, `gtk-arctic-polar-night.css` | All tokens as `arctic_*` plus the libadwaita names (`accent_bg_color` → `accent`, `accent_fg_color` → `on-accent`, `window_bg_color` → `surface`…). Radii: buttons/entries 10px, popovers/cards 14px, dialogs 20px. Focus: `outline: 2px solid @arctic_focus; outline-offset: 2px`. |
| Qt6 / QML (SDDM, Qt apps) | QML singleton | `Theme.qml` | `Theme.dark` switches every colour. QML colours are `#AARRGGBB` (already converted). Frost = `MultiEffect { blurEnabled: true; blur: 1.0; blurMax: 28 }` under a `Theme.frost` rectangle. Fonts: bundle Figtree and JetBrains Mono with `FontLoader`. |
| Top bar | waybar CSS | `waybar-arctic.css` | Height 34 in `config.jsonc`; modules left: `custom/launcher`, `ext/workspaces`; centre: `clock`; right: `tray`, `network`, `pulseaudio`, `battery`, `custom/power`. |
| Compositor | Mango config | `mango-arctic.conf` | `borderpx=2`, `border_radius=10`, gaps 8, `focuscolor` = `accent-edge`, `bordercolor` = `line`, `urgentcolor` = `error`, animation curves from the easing tokens. Check key names against your Mango release. |
| Terminal | kitty | `kitty-arctic-winter.conf`, `kitty-arctic-polar-night.conf` | Includes the 16 ANSI colours, cursor, selection, tab and border colours, JetBrains Mono 10.5pt, 10×12 padding. |
| Boot menu | GRUB 2 theme | `grub-theme.txt` | Only background image, PF2 fonts, the list and labels. Selected item = amber 9-slice pixmap (radius 10). Generate PF2 with `grub2-mkfont`. |
| Boot splash | Plymouth script | `plymouth-arctic.script` | Mark breathing + eye blink + three amber dots; honours `arctic.reduce_motion=1`. Passphrase prompt uses the Input (lg) look. |
| Notifications | mako / swaync | from JSON | `background-color` = `surface-raised`, `text-color` = `ink`, `border-color` = `line`, `border-radius=14`, `width=340`, `margin=12`, critical border = `error`. |
| OSD | swayosd | from JSON | 280×48 pill, `frost`, progress fill `accent`, track `surface-sunken`. |
| Launcher | fuzzel / anyrun / custom | from JSON | 520px, `frost` + blur 28, `radius-xl`, selection `accent-soft`, match highlight `accent-text`. |
| Lock | swaylock-effects / QML | `Theme.qml` | Same card as SDDM without user picker and session menu. Ring colours: `focus` while typing, `error` on wrong, `success` on verified. |

**Theme switching.** One setting (`org.gnome.desktop.interface color-scheme`: `prefer-light` = Winter, `prefer-dark` = Polar night) drives GTK, Qt (via the portal), kitty (`kitten themes` or include swap), waybar and Mango. The live USB and the login screen default to Polar night; the installed system follows the user's choice.

**HiDPI.** Everything is specified in logical pixels; render SVG assets at 1× and 2×. The bar stays 34 logical px.
