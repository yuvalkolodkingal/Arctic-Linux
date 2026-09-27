# Arctic Linux branding

Login screen, boot menu, boot splash and the system logo set, built from the
design system in `design/` (tokens, brand book, `exports/`, fonts, logos,
wallpapers) and the component specs (LoginScreen, BootMenu, BootSplash).

| Path | Installs to (package) | What |
|---|---|---|
| `sddm/arctic/` | `/usr/share/sddm/themes/arctic/` (arctic-sddm-theme) | SDDM Qt 6 QML theme, Theme-API 2.0, `QtVersion=6` |
| `grub/arctic/` | `/boot/grub2/themes/arctic/` (arctic-grub-theme) | GRUB theme for the live ISO and the installed system |
| `plymouth/arctic/` | `/usr/share/plymouth/themes/arctic/` (arctic-plymouth-theme) | Plymouth script theme |
| `plymouth/dracut/90arctic-plymouth/` | `/usr/lib/dracut/modules.d/90arctic-plymouth/` (arctic-plymouth-theme) | initrd hook for `arctic.reduce_motion=1` |
| `logos/` | `/` (arctic-logos): the tree mirrors install paths | what fedora-logos / generic-logos ship, Arctic-branded |
| `fonts/` | `/usr/share/fonts/arctic/` (arctic-fonts) | Figtree + JetBrains Mono as TTF with fixed names, `OFL.txt` |
| `src/` | — | generated brand SVGs (marks, outlined lockups, app icon) |
| `tools/` | — | generators and preview/test scripts |
| `*/preview/` | — | screenshots from the preview scripts + design mockup renders |

Everything under `sddm/arctic/fonts`, `sddm/arctic/background.png`, `grub/arctic/`,
`plymouth/arctic/*.png`, `logos/`, `fonts/` and `src/` is generated and committed;
the QML, `arctic.script`, `arctic.plymouth`, `theme.conf` and `metadata.desktop`
are hand-written.

## Build

```sh
branding/tools/build-all.sh           # everything below, in one container if needed
branding/tools/render-logos.sh        # fonts/, src/, logos/
branding/tools/build-sddm-theme.sh    # sddm/arctic/fonts, sddm/arctic/background.png
branding/tools/build-grub-theme.sh    # grub/arctic/* (theme.txt, PNGs, PF2)
branding/tools/build-plymouth-theme.sh  # plymouth/arctic/*.png
```

The scripts need `rsvg-convert`, `python3-fonttools` + `python3-brotli`,
`python3-pillow` and `grub2-mkfont`. When they are missing and docker or podman
is available, a script re-runs itself in `registry.fedoraproject.org/fedora:44`
(proxy / CA settings are passed through only when present, so it also works on
GitHub runners). No node or design bundle is needed: `tools/brand.py` ports the
design's `mark()` and `wordmark()` builders.

## Preview / test

All three boot the real thing and take screenshots:

```sh
branding/tools/preview-sddm.sh      # sddm-greeter-qt6 --test-mode in headless sway -> sddm/preview/
branding/tools/preview-grub.sh      # grub2-mkrescue ISO in QEMU -> grub/preview/
branding/tools/preview-plymouth.sh  # Fedora kernel + dracut initrd in QEMU -> plymouth/preview/
```

`preview-sddm.sh` and `preview-plymouth.sh` add users / install the theme
system-wide, so they only run inside a throwaway container (they start one).
In `--test-mode` the theme answers every login with a failure after 450 ms so
the error state (and its shake) can be previewed; power buttons are shown even
though the test greeter has no daemon.

## SDDM theme

- Files: `Main.qml`, `Theme.qml` (copy of `design/exports/Theme.qml` plus a few
  tokens it lacks), `components/` (Avatar, FocusRing, FrostPanel, Icon, IconButton,
  Kbd, SessionSelect, TextField, Tooltip), bundled TTF fonts via `FontLoader`,
  `background.png` (fox, Polar night, 2560x1440).
- Imports only `QtQuick`, `QtQuick.Effects` (MultiEffect blur, RectangularShadow)
  and `QtQuick.Shapes` (icons) — all in `qt6-qtdeclarative`. With the software
  scene graph (`QT_QUICK_BACKEND=software`) the frost falls back to opaque
  `surface-raised`, as the brand book asks; checked.
- Behaviour: clock block; 360 px frosted card; user picker when there are several
  users (selected 64 px with the amber ring, others 40 px); a user-name field
  when SDDM lists no users; password with lock icon, amber caret, error state
  "That password didn't work" + a 6 px double shake (none with `reduceMotion`);
  empty passwords are sent as-is (live user); Caps Lock hint (inferred from typed
  letters, because SDDM's Wayland greeter reports no LED state); session menu
  bottom-left; keyboard layout + suspend / restart / shut down bottom-right with
  tooltips. Keyboard: the password field has focus on start; Tab order is
  password → users (←/→ switch) → log in → session → suspend → restart → shut
  down; Enter/Space activate; Esc clears the field or closes the menu; focus rings
  show only after keyboard use.
- `theme.conf` keys (override in `theme.conf.user` next to it): `background`,
  `colorScheme` (`polar-night` | `winter`), `reduceMotion`, `timeFormat`,
  `dateFormat`, `keyboardLayout` (shown next to the keyboard icon — SDDM cannot
  report the layout on Wayland, so the installer should write the chosen XKB
  layout here).

## GRUB theme

`theme.txt` follows `design/exports/grub-theme.txt` and the BootMenu mockup:
aurora background with the 70 % `#0c1015` overlay baked in, the polar-night
lockup, a 420 px list of 40 px rows (Figtree Medium 17 / SemiBold 17 for the
selection) with the amber 9-slice (radius 10, 16 px text inset), the countdown
and the key hints in JetBrains Mono. The geometry notes are in the file header.
`grub.cfg` must `loadfont` every `*.pf2` in the theme directory and use `gfxterm`
(`grub2-mkconfig`'s `00_header` does both when `GRUB_THEME` is set).

## Plymouth theme

`arctic.script` draws the BootSplash: the fox (snow-100, amber eyes) breathing
1 → 1.035 over 2.4 s, a blink about every 5 s, three pulsing amber dots and the
aurora glow; the disk passphrase prompt is the Input (lg) look with bullets, a
caret and a Caps Lock hint. Everything scales with the screen height (mockup
960x600). Script themes cannot read the kernel command line, so
`90arctic-plymouth` adds an `ExecStartPre` to `plymouth-start.service` in the
initrd that links `/run/arctic/reduce-motion.png` when `arctic.reduce_motion=1`
is set; the script then shows a still mark with solid dots.
