"""Derive a palette from a wallpaper, keeping the Arctic look and guaranteeing contrast.

The base palette (Polar night for dark, Winter for light, or --base) supplies the structure:
every role keeps its OKLab lightness, so the design's contrast steps survive. From the
wallpaper come:

  neutrals  grounds, surfaces, lines, inks, terminal background/foreground: tinted toward the
            wallpaper's colour cast (their small chroma rotated to its hue, more as the cast is
            stronger) — still near-neutral, as Arctic's slate greys are
  accent    the accent family (accent, hover, pressed, text, soft, edge, focus, selection,
            terminal cursor/selection): the seed's hue, its chroma (kept between 0.10 and 0.19)
  aurora    the three aurora colours rotated with the seed
  ANSI      1-6 and 9-14 harmonised toward the seed (hue moved by half the difference, at most
            15°), so they stay distinguishable; 0, 7, 8, 15 tinted like the neutrals

Status colours (success, warning, error, info), on-error and warm stay as in the base.
Greyscale / low-chroma wallpapers keep the base accent (and barely tint anything).

Then contrast is enforced (lightness moved, hue kept) — see GUARANTEES — and checked: when the
foregrounds alone can't reach it (a mid-grey --base), the backgrounds are moved toward black
(dark) or white (light) until they can; a palette that still fails raises ThemegenError.
"""
import math
import os

from . import color, wallpaper
from .palette import BUILTIN_FOR_MODE, BUILTINS, ROLES, ThemegenError, builtin, validate

NEUTRAL = (
    "ground", "surface", "surface-raised", "surface-sunken", "frost", "scrim", "line",
    "line-strong", "ink", "ink-muted", "ink-subtle", "ink-disabled", "ink-inverse", "on-accent",
    "term-background", "term-foreground", "term-cursor-text-color", "term-selection-foreground",
    "ansi-0", "ansi-7", "ansi-8", "ansi-15",
)
ACCENT = (
    "accent", "accent-hover", "accent-pressed", "accent-text", "accent-soft", "accent-edge",
    "focus", "selection", "term-cursor", "term-selection-background",
)
AURORA = ("aurora-1", "aurora-2", "aurora-3")
ANSI_COLORS = tuple("ansi-{}".format(i) for i in (1, 2, 3, 4, 5, 6, 9, 10, 11, 12, 13, 14))
BACKGROUNDS = ("ground", "surface", "surface-raised", "surface-sunken")

TINT_GAIN = 1.3          # neutral chroma, relative to the base's, at full cast strength
TINT_MAX = 0.04          # ... but never more than this (OKLCH chroma)
CAST_NONE, CAST_FULL = 0.004, 0.03   # cast strength (|mean a,b|) → tint amount 0..1
ACCENT_CHROMA = (0.10, 0.19)
HARMONIZE_MAX = 15.0     # degrees
SEPARATION_KEPT = 0.8    # neighbouring ANSI hues keep >= 80% of their distance

# The contrast every derived palette meets (WCAG 2 ratios): (foreground, backgrounds, ratio).
GUARANTEES = (
    ("ink", ("ground", "surface"), 7.0),
    ("ink-muted", ("ground", "surface"), 4.5),
    ("accent-text", ("ground",), 4.5),
    ("on-accent", ("accent",), 4.5),
    ("focus", ("ground",), 3.0),
) + tuple((a, ("term-background",), 4.5) for a in ANSI_COLORS)


def _tint(value, hue, amount):
    """Rotate a near-neutral colour's chroma toward `hue` (blend in OKLab a/b, so a partial
    tint passes through grey, not through other hues). Lightness and alpha are kept."""
    if amount <= 0:
        return value
    alpha = color.alpha_of(value)
    L, a, b = color.hex_to_oklab(value)
    c0 = math.hypot(a, b)
    ct = min(c0 * TINT_GAIN, TINT_MAX)
    ta, tb = ct * math.cos(math.radians(hue)), ct * math.sin(math.radians(hue))
    return color.oklab_to_hex((L, a + (ta - a) * amount, b + (tb - b) * amount), alpha)


def _rehue(value, hue, chroma_scale=1.0):
    alpha = color.alpha_of(value)
    L, C, _h = color.hex_to_oklch(value)
    return color.oklch_to_hex((L, C * chroma_scale, hue % 360.0), alpha)


def _rotate(value, degrees):
    alpha = color.alpha_of(value)
    L, C, h = color.hex_to_oklch(value)
    return color.oklch_to_hex((L, C, (h + degrees) % 360.0), alpha)


def harmonize_ansi(base, seed_hue):
    """{ansi role: hue rotation} moving each chromatic ANSI colour toward the seed hue by half
    the difference, at most HARMONIZE_MAX (Material's "harmonize"). Colours on either side of
    the seed would drift together, so the rotations are scaled down (all by the same factor)
    until every pair of neighbouring hues keeps at least SEPARATION_KEPT of its distance."""
    hues = {r: color.hex_to_oklch(base[r])[2] for r in ANSI_COLORS}
    wanted = {}
    for r, h in hues.items():
        d = color.hue_diff(h, seed_hue)
        wanted[r] = math.copysign(min(abs(d) * 0.5, HARMONIZE_MAX), d)

    def ok(f):
        for group in (ANSI_COLORS[:6], ANSI_COLORS[6:]):
            before = sorted((hues[r] % 360.0, r) for r in group)
            for i, (h, r) in enumerate(before):
                h2, r2 = before[(i + 1) % len(before)]
                gap = (h2 - h) % 360.0
                moved = (h2 + f * wanted[r2] - h - f * wanted[r]) % 360.0
                if gap > 1e-6 and (moved > gap and moved - gap > 180.0 or moved < SEPARATION_KEPT * gap):
                    return False
        return True

    f = 1.0
    if not ok(f):
        lo, hi = 0.0, 1.0
        for _ in range(20):
            mid = (lo + hi) / 2
            if ok(mid):
                lo = mid
            else:
                hi = mid
        f = lo
    return {r: f * w for r, w in wanted.items()}


def _contrast_pair(c, fg, bg, ratio, move="fg"):
    """Make c[fg] vs c[bg] >= ratio, moving `move` first and the other one if that's not enough."""
    first, other = (fg, bg) if move == "fg" else (bg, fg)
    c[first] = color.ensure_contrast(c[first], c[other], ratio)
    if color.contrast(c[fg], c[bg]) < ratio:
        c[other] = color.ensure_contrast(c[other], c[first], ratio)


def enforce(c):
    """Enforce GUARANTEES (plus a few more pairs the desktop relies on) in place."""
    for bg in BACKGROUNDS:
        c["ink"] = color.ensure_contrast(c["ink"], c[bg], 7.0)
        c["ink-muted"] = color.ensure_contrast(c["ink-muted"], c[bg], 4.5)
        c["ink-subtle"] = color.ensure_contrast(c["ink-subtle"], c[bg], 4.5)
    # Buttons: one on-accent for the accent and its hover/pressed states.
    _contrast_pair(c, "on-accent", "accent", 4.5, move="fg")
    for state in ("accent-hover", "accent-pressed"):
        c[state] = color.ensure_contrast(c[state], c["on-accent"], 4.5)
    for bg in BACKGROUNDS:
        c["accent-text"] = color.ensure_contrast(c["accent-text"], c[bg], 4.5)
        c["focus"] = color.ensure_contrast(c["focus"], c[bg], 3.0)
        c["accent-edge"] = color.ensure_contrast(c["accent-edge"], c[bg], 3.0)
        for status in ("success", "warning", "error", "info"):
            c[status] = color.ensure_contrast(c[status], c[bg], 4.5)
    # Selected text and highlighted rows keep readable ink.
    _contrast_pair(c, "ink", "selection", 4.5, move="bg")
    _contrast_pair(c, "ink", "accent-soft", 7.0, move="bg")
    _contrast_pair(c, "on-error", "error", 4.5, move="bg")
    # Terminal.
    c["term-foreground"] = color.ensure_contrast(c["term-foreground"], c["term-background"], 7.0)
    for a in ANSI_COLORS:
        c[a] = color.ensure_contrast(c[a], c["term-background"], 4.5)
    c["term-cursor"] = color.ensure_contrast(c["term-cursor"], c["term-background"], 3.0)
    _contrast_pair(c, "term-cursor-text-color", "term-cursor", 4.5, move="bg")
    _contrast_pair(c, "term-selection-foreground", "term-selection-background", 4.5, move="bg")
    return c


def _meet_guarantees(c, mode, rounds=12, step=0.25):
    """enforce() moves foregrounds; with a mid-grey base (--base) no foreground can reach the
    ratio. Then move the backgrounds' lightness toward the mode's extreme (darker for dark,
    lighter for light) a step at a time and enforce again. Raises ThemegenError if GUARANTEES
    still fail, so a palette that breaks them is never returned."""
    target = 0.0 if mode == "dark" else 1.0
    for _ in range(rounds):
        failures = check({"colors": c})
        if not failures:
            return
        for r in BACKGROUNDS + ("term-background",):
            alpha = color.alpha_of(c[r])
            L, C, h = color.hex_to_oklch(c[r])
            c[r] = color.oklch_to_hex((L + (target - L) * step, C, h), alpha)
        enforce(c)
    failures = check({"colors": c})
    if failures:
        raise ThemegenError("the palette can't meet its contrast guarantees: " + ", ".join(
            "{} on {} {:.2f} < {:g}".format(fg, bg, r, need) for fg, bg, r, need in failures))


def check(palette):
    """[(foreground, background, ratio, required)] for every GUARANTEES pair that fails."""
    c = palette["colors"]
    failures = []
    for fg, bgs, ratio in GUARANTEES:
        for bg in bgs:
            r = color.contrast(c[fg], c[bg])
            if r < ratio:
                failures.append((fg, bg, round(r, 3), ratio))
    return failures


def contrast_report(palette):
    """{"fg on bg": ratio} for every GUARANTEES pair."""
    c = palette["colors"]
    return {"{} on {}".format(fg, bg): round(color.contrast(c[fg], c[bg]), 2)
            for fg, bgs, _ in GUARANTEES for bg in bgs}


def resolve_base(mode, base, analysis=None):
    """(mode, base palette) for --mode/--base. Without --base the base is the built-in theme of
    the mode; with --base, --mode auto takes the base's mode and a clash is an error."""
    if base is None:
        if mode == "auto":
            mode = analysis.mode if analysis else "dark"
        return mode, builtin(BUILTIN_FOR_MODE[mode])
    if isinstance(base, dict):
        base_palette = validate(base)
    elif base in BUILTINS:
        base_palette = builtin(base)
    else:
        from .palette import load
        base_palette = load(base)
    if mode == "auto":
        mode = base_palette["mode"]
    elif mode != base_palette["mode"]:
        raise ThemegenError("--base {} is a {} theme; use --mode {} or another base".format(
            base_palette["name"], base_palette["mode"], base_palette["mode"]))
    return mode, base_palette


def derive(analysis, base_palette, name="wallpaper", label="Wallpaper", image=None):
    """The palette for an Analysis on top of base_palette (whose mode it takes)."""
    base = base_palette["colors"]
    c = dict(base)
    amount = color.smoothstep(CAST_NONE, CAST_FULL, analysis.cast_strength)
    hue = analysis.cast_hue
    for r in NEUTRAL:
        c[r] = _tint(base[r], hue, amount)
    seed = analysis.seed
    if seed is not None:
        _sl, sc, sh = seed
        _al, base_c, base_h = color.hex_to_oklch(base["accent"])
        target = min(max(sc, ACCENT_CHROMA[0]), ACCENT_CHROMA[1])
        scale = target / base_c if base_c > 1e-6 else 1.0
        for r in ACCENT:
            _l, _c, h = color.hex_to_oklch(base[r])
            # Keep each role's small hue offset from the accent (hover is a touch yellower…).
            c[r] = _rehue(base[r], sh + color.hue_diff(base_h, h), scale)
        delta = color.hue_diff(color.hex_to_oklch(base["aurora-2"])[2], sh)
        for r in AURORA:
            c[r] = _rotate(base[r], delta)
        for r, degrees in harmonize_ansi(base, sh).items():
            c[r] = _rotate(base[r], degrees)
    mode = base_palette["mode"]
    enforce(c)
    _meet_guarantees(c, mode)
    p = {
        "name": name,
        "label": label,
        "mode": mode,
        "base": base_palette["name"],
        "colors": {r: c[r] for r in ROLES},
        "wallpaper": os.path.abspath(image) if image else base_palette.get("wallpaper", ""),
        "lock_wallpaper": base_palette.get("lock_wallpaper", ""),
    }
    for extra, value in base.items():
        if extra not in p["colors"]:
            p["colors"][extra] = value
    return validate(p)


def from_wallpaper(image, mode="auto", base=None, name="wallpaper", label="Wallpaper"):
    """arctic-themegen palette --from-wallpaper IMAGE: the palette dict, with a "source" entry
    describing where it came from (image, file size and mtime, seed, cast, fallback)."""
    if mode not in ("auto", "dark", "light"):
        raise ThemegenError("--mode must be auto, dark or light")
    analysis = wallpaper.analyse(image)
    resolved, base_palette = resolve_base(mode, base, analysis)
    p = derive(analysis, base_palette, name=name, label=label, image=image)
    st = os.stat(image)
    info = analysis.as_dict()
    p["source"] = {
        "image": os.path.abspath(image),
        "size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
        "mode_setting": mode,
        "seed": info["seed"],
        "fallback": analysis.seed is None,
        "cast": info["cast"],
        "mean_lightness": info["mean_lightness"],
    }
    return p
