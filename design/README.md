# Arctic Linux design system

The source files of the Arctic Linux design system, copied from the design system artifact
(https://claude.ai/artifact/8eUAobifhKCoecsG23Fb3i). The artifact holds the full brand book,
component specs and screen mockups; this folder holds what the OS build needs.

| Path | What |
|---|---|
| `brand-book.md` | Principles, voice, colour roles, type, space, motion, accessibility, logo, icons |
| `guidelines/` | Platforms (how tokens map to GTK, QML, kitty, waybar, Mango, GRUB, Plymouth), installer copy, terminal and fetch |
| `tokens.json` | The design tokens (source of truth) |
| `exports/` | Flat token exports and ready platform files from the design system (`arctic-tokens.json`, GTK, QML `Theme.qml`, kitty, waybar, Mango, GRUB, Plymouth) |
| `fonts/` | Figtree 400–700 and JetBrains Mono 400/700/italic (SIL OFL), WOFF2 |
| `logos/` | The fox mark: colour versions for Winter and Polar night, 16px versions |
| `icons/` | The system icons the desktop uses (24px grid, 1.75px stroke, charcoal ink) |
| `wallpapers/` | Snowfield, aurora and fox, each in Winter and Polar night (1920×1080 SVG) |
| `tools/gen-desktop-themes.py` | Generates the desktop theme files in `../dotfiles/.config/arctic/themes/` from `exports/arctic-tokens.json` |

Only the icons and logos the desktop uses are copied here; the full set (78 icons, 30 app tiles,
lockups) lives in the artifact.
