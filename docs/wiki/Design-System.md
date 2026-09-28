# Design system

Arctic Linux's look and voice come from one design system, drawn from the arctic fox: the white
winter coat, the blue-grey coat of the polar night, the brown-grey summer coat, charcoal nose and
paws, and the amber eyes, the only colour that ever asks for attention.

- **The full design system** (brand book, component specs and mockups of every screen in both
  themes): [the Arctic Linux design system artifact](https://claude.ai/artifact/8eUAobifhKCoecsG23Fb3i).
- **What the build uses** is copied into [`design/`](https://github.com/yuvalkolodkingal/O-Tism/tree/main/design):
  `tokens.json`, the [brand book](https://github.com/yuvalkolodkingal/O-Tism/blob/main/design/brand-book.md),
  guidelines, exports, fonts, logos, icons and wallpapers.

## Principles

1. **Calm like snow.** Quiet surfaces, soft neutrals, generous space. If a screen feels busy,
   remove something before restyling it.
2. **One clear action.** Each view has at most one amber primary action.
3. **Amber means "here".** The accent marks focus, the primary action and the current selection,
   never decoration.
4. **Keyboard first, never keyboard only.** Every action has a shortcut and a visible focus ring;
   everything also works with a mouse or touchpad.
5. **Say it plainly.** Titles are plain questions, help text explains why, buttons name the
   consequence. No jargon a non-expert would have to look up.
6. **Cold outside, warm inside.** The palette is cool; warmth comes from rounded shapes, the
   summer-coat neutral, friendly copy and the amber eyes.

## Voice

- Sentence case everywhere, including buttons and titles ("Choose your apps").
- Speak to the person as "you"; Arctic says "we" only in the installer ("We've ticked our
  favourites").
- Short sentences, contractions welcome, no exclamation marks, no emoji in the interface.
- Buttons start with a verb and say what will happen: "Erase disk and install", "Skip Steam",
  "Restart now". Never "OK", "Submit" or "Yes".
- Errors say what happened, whether anything is harmed, and what to do next.
- Keyboard shortcuts are written `Super + Space`.

## Themes and colour

Two themes share every token name: **Winter** (`light`) and **Polar night** (`dark`). Build with
the semantic tokens below; the raw colour ramps exist only to explain where they came from.

| Role | Token | Winter | Polar night |
|---|---|---|---|
| Desktop / backdrop | `ground` | `#eef2f5` | `#12171e` |
| Window, page | `surface` | `#fbfcfd` | `#1a212a` |
| Menus, dialogs, cards | `surface-raised` | `#ffffff` | `#232b36` |
| Bar, tracks, sidebars | `surface-sunken` | `#e8edf1` | `#0f141a` |
| Primary text | `ink` | `#151a21` | `#e9eef3` |
| Secondary text | `ink-muted` | `#4a5663` | `#aeb9c5` |
| Placeholder, timestamps | `ink-subtle` | `#5f6b79` | `#8f9cab` |
| Decorative hairline | `line` | `#d5dde4` | `#2f3945` |
| Control boundary | `line-strong` | `#7c8a99` | `#6b7a8a` |
| Accent fill | `accent` | `#efa637` | `#f6bd55` |
| Text on accent | `on-accent` | `#151a21` | `#151a21` |
| Amber as text, edge, focus | `accent-text`, `accent-edge`, `focus` | `#84500d`, `#a86812`, `#a86812` | `#f6bd55` |
| Selected row | `accent-soft` | `#fdf0d6` | `#3a2d16` |
| Warm neutral (summer coat) | `warm` on `warm-soft` | `#62564b` on `#f0eae3` | `#c9bcad` on `#2f2924` |
| Success · warning · error · info | `success`, `warning`, `error`, `info` | `#1d7350` · `#9a4812` · `#b3261e` · `#1f5f9e` | `#6fd3a3` · `#f4a270` · `#ff9189` · `#86bdf5` |

- **Contrast:** every text token passes WCAG AA (4.5:1) on the grounds it's meant for, in both
  themes; control boundaries and focus rings hold 3:1.
- **Amber is only for** the one primary button, keyboard focus and the focused window border, the
  current selection (checked controls, selected row, active workspace, current installer step),
  progress fills and the text cursor, and the fox's eyes. Never for headings, idle icons,
  decoration, warnings or large backgrounds. There's never white text on amber.
- **Status colours** always come with an icon and a word, never colour alone.
- **The aurora gradient** (green → teal → ice) is for special moments only: the installer's
  Welcome and Done screens, the boot splash glow and the wallpapers. Never on anything
  interactive.

## Typography

- **Interface:** Figtree (SIL OFL) 400, 500, 600 and
  700, falling back to Noto Sans (and Noto Sans Hebrew, Arabic and CJK for other scripts).
- **Monospace:** JetBrains Mono (SIL OFL) 400 and 700 with italic, for the terminal, code,
  keyboard chips and the boot menu.
- **Scale:** `clock` 72 · `display` 40 · `title-1` 28 · `title-2` 20 · `headline` 16 · `body` 15 ·
  `label` 13 · `caption` 12 · `overline` 11 (uppercase). Mono: `terminal` 14, `code` 13, `kbd` 12.
- One `title-1` per screen. Tabular figures for clocks, percentages and sizes.

## Space, shape and size

- **4px grid:** `space-1` 4px up to `space-16` 64px. Tiling gaps are `space-2`, 8px.
- **Radii**, rounded like the curled-up fox: `radius-md` 10px for controls and tiled windows,
  `radius-lg` 14px for cards and notifications, `radius-xl` 20px for dialogs, the launcher and the
  login card, `radius-full` for pills. Nothing is square.
- **Sizes:** controls 36px (`control-md`), 44px in the installer footer and login
  (`control-lg`), 28px compact in the bar; the bar is 34px; minimum pointer target 32px.
- **Borders:** 1px hairlines; 2px focus rings and window borders (amber when focused).

## Elevation and frost

Flat by default, with three shadows (`shadow-sm` for cards, `shadow-md` for menus and
notifications, `shadow-lg` for dialogs, the launcher and the login card). **Frost**, a translucent
surface with a backdrop blur (`blur-lg` 28px, `blur-md` 12px), is only for surfaces that float over
the wallpaper: the top bar, launcher, OSD, the login and lock card and the live welcome card.

## Motion

- `duration-fast` 120ms (hover, press, focus), `duration-base` 180ms (toggles, menus, window
  moves), `duration-slow` 280ms (dialogs, launcher, installer step change), `duration-ambient`
  2.4s (splash breathing, fetch loop).
- Easing: `ease-standard` for most, `ease-enter` for arrivals, `ease-exit` for departures. Fades and
  short slides only: no bounces, no parallax.
- **Reduced motion** (`arctic-motion off`, GTK's animation setting, `arctic.reduce_motion=1` for the
  splash): movement stops, only quick fades remain, the splash and the fetch fox stay still.

## Logo and icons

- **The mark** is a geometric arctic fox, curled up with its tail wrapped under its chin. Colour
  versions have amber eyes on a charcoal (Winter) or snow (Polar night) fox; at 16–20px there's a
  simpler drawing without eyes.
- **The wordmark** is "arctic linux" in lowercase Figtree. In running text the name is always
  "Arctic Linux".
- **System icons:** 24px grid, 1.75px stroke, round caps and joins.
- **App tiles** (in the installer and launcher): a rounded square in a category tint with one line
  glyph.

## How the tokens reach the system

`design/tokens.json` is the source of truth. From it:

| Output | Where | Used by |
|---|---|---|
| Flat exports and ready platform files | `design/exports/` (CSS, JSON, GTK, QML `Theme.qml`, kitty, waybar, Mango, GRUB, Plymouth) | Reference for every surface below |
| Desktop theme files, one folder per theme | `dotfiles/.config/arctic/themes/{winter,polar-night}/`, rendered by the theme engine (`design/themegen`, templates in `design/themegen/templates/`) through `python3 design/tools/gen-desktop-themes.py`; the packages render them again at build time and the tests check the committed copies are current | The shell and Settings (`theme.json`), kitty, foot, Alacritty, mako, fuzzel, waybar, swaylock, GTK, Qt (qt5ct/qt6ct), Mango, Zed, yazi, btop, fzf, zsh, Zen, `theme.env` |
| Installer theme | `installer-ui/Theme.qml` | The installer |
| Login screen theme | `branding/sddm/arctic/Theme.qml` | SDDM |
| Boot menu and splash | `branding/grub/arctic/`, `branding/plymouth/arctic/` (made by `branding/tools/`) | GRUB, Plymouth |

The same engine is installed as `arctic-themegen`: `arctic-theme` uses it to make a theme from the
wallpaper, keeping the semantic token names and enforcing the contrast guarantees (`ink` at least
7:1 on `ground` and `surface`; secondary text, the accent's text, text on the accent and the
terminal colours at least 4.5:1). See
[Themes and customisation](Themes-and-Customisation#colours-from-your-wallpaper).

To change a colour: edit `design/tokens.json`, re-export `design/exports/arctic-tokens.json` from the
design system, run `python3 design/tools/gen-desktop-themes.py`, and rebuild the branding with
`branding/tools/build-all.sh` if the login, boot menu or splash are affected.

Icons and app tiles for the shell and installer are exported from the design system's component
bundle (`shell/dev/export-design-assets.cjs`, `installer-ui/dev/export-assets.js`).
