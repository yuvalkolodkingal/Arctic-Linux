Arctic Linux is a calm, keyboard-first Fedora desktop on the Mango tiling compositor. Its whole identity comes from the arctic fox: the white winter coat, the blue-morph coat of the polar night, the brown-grey summer coat, charcoal nose and paws, and the amber eyes — the only colour that ever asks for attention.

## Principles

1. **Calm like snow.** Quiet surfaces, soft neutrals, generous space. If a screen feels busy, remove something before restyling it.
2. **One clear action.** Each view has at most one amber primary action. Everything else is secondary, ghost or a link.
3. **Amber means "here".** The accent marks focus, the primary action and the current selection — never decoration, never a category colour.
4. **Keyboard first, never keyboard only.** Every action has a shortcut and a visible focus ring; everything also works with a mouse or touchpad.
5. **Say it plainly.** Titles are plain questions, help text explains *why*, buttons name the consequence. No jargon a non-expert would have to look up.
6. **Cold outside, warm inside.** The palette is cool; warmth comes from rounded shapes, the summer-coat neutral, friendly copy and the amber eyes.

## Voice and copy

- Sentence case everywhere, including buttons and titles ("Choose your apps").
- Speak to the person as "you"; Arctic speaks as "we" only in the installer ("We've ticked our favourites").
- Short sentences, contractions welcome, no exclamation marks, no emoji in UI.
- Buttons start with a verb and say what will happen: "Erase disk and install", "Skip Steam", "Restart now". Never "OK", "Submit" or "Yes".
- Errors say what happened, whether anything is harmed, and what to do next: "Steam couldn't be downloaded. Everything else is fine — Steam is optional and you can add it later."
- Help text explains why a step exists: "Arctic Linux downloads the apps you pick and the latest security updates while it installs."
- Keyboard shortcuts are written `Super + Space` and shown as `kbd` chips.

## Colour

Two themes share every token name: **Winter** (`light`, the snow-white coat) and **Polar night** (`dark`, the blue-morph coat). Build with the semantic tokens; the raw ramps (`snow-*`, `slate-*`, `tundra-*`, `amber-*`, `aurora-*`, `nose`) exist only to explain where they came from.

| Role | Token | Winter | Polar night |
|---|---|---|---|
| Desktop / backdrop | `ground` | #eef2f5 | #12171e |
| Window, page | `surface` | #fbfcfd | #1a212a |
| Menus, dialogs, cards | `surface-raised` | #ffffff | #232b36 |
| Bar, tracks, sidebars | `surface-sunken` | #e8edf1 | #0f141a |
| Primary text | `ink` | #151a21 | #e9eef3 |
| Secondary text | `ink-muted` | #4a5663 | #aeb9c5 |
| Placeholder, timestamps | `ink-subtle` | #5f6b79 | #8f9cab |
| Decorative hairline | `line` | #d5dde4 | #2f3945 |
| Control boundary | `line-strong` | #7c8a99 | #6b7a8a |
| Accent fill | `accent` | #efa637 | #f6bd55 |
| Text on accent | `on-accent` | #151a21 | #151a21 |
| Amber as text / edge / focus | `accent-text`, `accent-edge`, `focus` | #84500d, #a86812, #a86812 | #f6bd55 |
| Selected row | `accent-soft` | #fdf0d6 | #3a2d16 |
| Warm neutral (summer coat) | `warm` on `warm-soft` | #62564b on #f0eae3 | #c9bcad on #2f2924 |
| Success · warning · error · info | `success`, `warning`, `error`, `info` | #1d7350 · #9a4812 · #b3261e · #1f5f9e | #6fd3a3 · #f4a270 · #ff9189 · #86bdf5 |

**Contrast.** Every text token passes WCAG AA (4.5:1) on every ground its usage note names, in both themes: `ink`/`ink-muted` on all four grounds plus `accent-soft` and `warm-soft`; `ink-subtle`, `accent-text` and `warm` on `surface` and `surface-raised`; each status colour on `surface`, `surface-raised` and its own `-soft`; `on-accent` on `accent`, `accent-hover` and `accent-pressed`; `on-error` on `error`. Boundaries (`line-strong`, `accent-edge`, `focus`) hold 3:1 on every surface. `ink-disabled` is deliberately below AA and is only for disabled controls.

**The amber accent — allowed only for:**
- the one primary button in a view (`accent` fill, `on-accent` label — never white on amber);
- keyboard focus (`focus-ring`) and the focused window border (`accent-edge`);
- the current selection: checked controls, the selected row or card (`accent-soft` + `accent-edge`), the active workspace, the current installer step;
- progress fills and the text cursor;
- the fox's eyes in the mark and the fetch greeting.
Never for headings, icons at rest, illustrations, category colour, warnings (that is `warning`, cloudberry) or large backgrounds. In Winter an amber fill always carries its 1px `accent-edge` so it holds 3:1 on white.

**Status colours** always travel with an icon and a word (check-circle "Connected", alert "Battery at 10%"), never colour alone. Success and error also differ in lightness in both themes.

**The aurora gradient** (`aurora-1` → `aurora-2` → `aurora-3`, green → teal → ice) is for special moments only: the installer's Welcome and Done screens (a band fading down from the top edge), the boot splash glow, and wallpapers. Never on buttons, bars, cards, text, focus, progress or anything interactive, and never more than one aurora element on screen.

## Typography

- **UI:** Figtree (SIL OFL) 400/500/600/700, fallback Noto Sans (and Noto Sans Hebrew / CJK for scripts Figtree lacks).
- **Mono:** JetBrains Mono (SIL OFL) 400/700 + italic, for the terminal, code, keyboard chips and GRUB.
- Scale: `clock` 72, `display` 40, `title-1` 28, `title-2` 20, `headline` 16, `body` 15, `label` 13, `caption` 12, `overline` 11 (uppercase, +0.08em); mono `terminal` 14, `code` 13, `kbd` 12.
- One `title-1` per screen. Body text runs 15/22 with a 560–640px measure. Use tabular figures for clocks, percentages and sizes.
- Display sizes tighten tracking (−0.02em); nothing below 12px except the overline.

## Space, shape and layout

- 4px grid: `space-1` 4 … `space-16` 64. Tiling gaps are `space-2` (8px) inner and outer.
- Rounded like the curled-up fox: `radius-md` 10px for controls and tiled windows, `radius-lg` 14px for cards and notifications, `radius-xl` 20px for dialogs, the launcher and the login card, `radius-full` for pills (toggles, workspaces, OSD, avatars). Nothing is square; nothing is a blob.
- Sizes: controls 36px (`control-md`), 44px in the installer footer and login (`control-lg`), 28px compact in the bar. The bar is 34px.

## Elevation and frost

- Flat by default. `shadow-sm` for resting cards, `shadow-md` for menus, toasts and notifications, `shadow-lg` for dialogs, the launcher and the installer/login card. Dark theme shadows are deeper and carry a 1px inner highlight.
- **Frost** (`frost` colour + `blur-lg` 28px / `blur-md` 12px backdrop blur) is allowed only on surfaces that float over the wallpaper: the top bar, launcher, OSD, the login and lock card, the live-session welcome card. Never over windows full of text, never inside an app, never stacked frost-on-frost. Where blur is unavailable (GRUB, software rendering) use `surface-raised` at full opacity.

## Motion

- `duration-fast` 120ms (hover, press, focus), `duration-base` 180ms (toggles, menus, toasts, window moves), `duration-slow` 280ms (dialogs, launcher, installer step change), `duration-ambient` 2.4s (splash breathing, fetch loop).
- Easing: `ease-standard` for most, `ease-enter` for arrivals, `ease-exit` for departures. Motion is fades and short slides (≤8px) — no bounces, no parallax.
- **Reduced motion** (`prefers-reduced-motion`, GTK `gtk-enable-animations=false`, Mango `animations=0`, kernel `arctic.reduce_motion=1`): all durations become 0 except opacity fades at `duration-fast`; the splash, fetch fox and indeterminate progress stop on a still frame; the login shake is removed.

## Accessibility

- **Contrast:** text 4.5:1 (3:1 at 24px+ or bold 19px+), control boundaries, icons and focus rings 3:1 — in both themes (see Colour).
- **Focus:** every interactive element shows `focus-ring` on keyboard focus: a 2px gap in the surface colour, then 2px solid amber (`focus`). Never remove it; never show it on mouse click only.
- **Keyboard:** everything is reachable with Tab / Shift+Tab, arrows move inside groups and lists, Enter activates, Space toggles, Esc closes. Global: `Super + Space` launcher, `Super + Enter` terminal, `Super + L` lock, `Super + I` install (live session). Installer: Enter = Next when valid, `Alt + ←` = Back, `F1` = help.
- **Targets:** at least 32×32px hit area for pointer (`target-min`), 44px on touch screens; spacing between adjacent targets ≥ 4px.
- **Never colour alone:** status carries an icon and a word; selection carries a check or a notch; the strength meter carries a word.
- **Text:** respect the system font scale; layouts reflow to 200% without clipping. Hebrew and other RTL languages mirror the installer rail and Back/Next.
- **Screen readers:** installer steps use `aria-current="step"`; progress, meters and toasts expose live values; icon-only buttons have names (their tooltip text).

## Logo

- The mark is a geometric arctic fox curled up asleep-awake: a rounded fox face with soft ears, its big tail wrapped under the chin and up the right side. The gap between head and tail is part of the mark.
- Colour versions put amber eyes on a charcoal (`arctic-mark-winter`) or snow (`arctic-mark-polar-night`) fox; one-colour versions cut the eyes out (`mono-charcoal` on light, `mono-snow` on dark). At 16–20px use the `-16` drawings: no eyes, a wider gap.
- The wordmark is "arctic linux" in lowercase Figtree — "arctic" 600, "linux" 400 in `ink-muted` (same colour in the one-colour lockups). In running text the name is always "Arctic Linux".
- Clear space: the height of one ear (¼ of the mark) on all sides. Minimum size 16px for the mark, 96px wide for the lockup. Don't recolour the eyes, outline, rotate, add aurora behind the mark in UI, or place it on busy wallpaper without a frost surface.

## Iconography

- **System icons:** 24px grid, 1.75px stroke, round caps and joins, 2px corner radius on shapes, open and friendly; same stroke at 16 and 20px (don't scale strokes). Colour `ink` or `ink-muted`; `accent-text` only for a selected state; status colours only for status icons. Delivered as symbolic SVGs (`assets/Icons`, charcoal ink; GTK recolours `-symbolic` icons automatically).
- **App tiles:** a rounded square (30% corner radius) in a category tint — browser `info-soft`, editor/extras `surface-sunken`, terminal `slate-900`, shell `warm-soft`, files `accent-soft`, office `success-soft`, video `warning-soft` — with one line glyph in `ink` (snow on the terminal tile). The installer and launcher use these for a calm, uniform list; apps keep their own upstream icons once installed.

## Imagery

- Wallpapers: snowfield, the blue-morph fox (the mark as a pale silhouette with amber eyes on a snow drift) and aurora, each in Winter and Polar night (`assets/Wallpapers`, 1920×1080 SVG, render to PNG at the display size). Default: snowfield for Winter, aurora for Polar night; the fox is the login/live-session wallpaper.
- Landscapes are layered, soft drifts and sky — no photos, no busy detail, no text on wallpapers.

## Building with it

- Tokens: `tokens.json` (the source), `assets/Exports/arctic-tokens.css` and `.json` (flat), plus ready mappings for GTK, Qt/QML, kitty, waybar, Mango, GRUB and Plymouth — see **Platforms**.
- Components: `components/bundle.css` (classes `ar-*`, every value a token) and `components/bundle.js` (`window.Arctic`, framework-free builders that return reference markup). They are specs to port, not a runtime for the desktop.
- Every screen — boot menu, splash, login, lock, all 12 installer steps, live desktop, desktop, launcher, terminal and fetch — has a mockup in both themes under Components → Screens.
