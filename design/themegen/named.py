"""Named palettes (the theme gallery): an Arctic palette from a colors.toml.

colors.toml uses the keys Omarchy 4 themes use, so such a theme's colours can be read as they
are, plus three of Arctic's own:

    mode = "dark"                 # dark | light
    background, dark_background, darker_background, lighter_background, selection, muted,
    foreground, dark_foreground, light_foreground, bright_foreground, accent (#rrggbb)
    red, yellow, orange, green, cyan, blue, magenta (+ bright_*; brown)
    label = "Nord"                # Arctic: the name people see
    pair = "nord-light"           # Arctic: the theme of the other mode (light <-> dark)
    here = "yellow"               # Arctic: which colour key is the "here" accent

The theme keeps Arctic's structure: every surface, line and ink takes its OKLab lightness step
from Polar night (dark) or Winter (light), measured from the theme's own background and
foreground, so the design's steps and contrast survive while the colours are the theme's. The
accent is the "here" colour (yellow by default, orange when the yellow isn't a warm yellow),
built like the wallpaper path's accent family, so "here" reads the same in every theme; the
status colours come from the theme's green, red and the other of yellow/orange (a warning never
looks like "here"), and information from its own accent. Then the engine's contrast guarantees
are enforced and checked (derive.enforce / check); a theme that can't meet them is refused.
"""
import re
import tomllib

from . import color, derive
from .palette import NAME_RE, ROLES, ThemegenError, builtin, validate

KEYS = (
    "background", "dark_background", "darker_background", "lighter_background", "selection", "muted",
    "foreground", "dark_foreground", "light_foreground", "bright_foreground", "accent",
    "red", "yellow", "orange", "green", "cyan", "blue", "magenta", "brown",
    "bright_red", "bright_yellow", "bright_green", "bright_cyan", "bright_blue", "bright_magenta",
)
REQUIRED = ("background", "foreground", "red", "yellow", "green", "cyan", "blue", "magenta")
# A label is written into comments and strings of every config (a CSS comment, Zed's JSON): a
# downloaded theme's may hold letters, digits, spaces and a little punctuation, nothing that ends one.
LABEL_RE = re.compile(r"[\w .,'()+&!-]{1,80}")
STRUCTURE = ("ground", "surface", "surface-raised", "surface-sunken", "line", "line-strong")
INKS = ("ink-muted", "ink-subtle", "ink-disabled")


def load_colors(text, where="colors.toml"):
    """The checked colors.toml as a dict (unknown keys dropped)."""
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as e:
        raise ThemegenError("{}: not valid TOML ({})".format(where, e))
    out = {}
    for key in KEYS:
        if key in data:
            value = data[key]
            if not (isinstance(value, str) and color.is_hex(value) and len(value) == 7):
                raise ThemegenError("{}: {} must be #rrggbb (got {!r})".format(where, key, value))
            out[key] = value.lower()
    missing = [k for k in REQUIRED if k not in out]
    if missing:
        raise ThemegenError("{}: missing {}".format(where, ", ".join(missing)))
    mode = data.get("mode", "dark")
    if mode not in ("dark", "light"):
        raise ThemegenError("{}: mode must be dark or light (got {!r})".format(where, mode))
    out["mode"] = mode
    for key in ("label", "pair", "here"):
        value = data.get(key, "")
        if not isinstance(value, str) or len(value) > 80 or any(ord(ch) < 32 for ch in value):
            raise ThemegenError("{}: {} must be one short line".format(where, key))
        out[key] = value
    if out["label"] and not LABEL_RE.fullmatch(out["label"]):
        raise ThemegenError("{}: label may only hold letters, digits, spaces and . , ' ( ) + & ! -".format(where))
    if out["pair"] and not NAME_RE.match(out["pair"]):
        raise ThemegenError("{}: pair must be a theme name".format(where))
    if out["here"] and out["here"] not in out:
        raise ThemegenError("{}: here names a colour that isn't there ({})".format(where, out["here"]))
    return out


def _step(value, anchor_from, anchor_to):
    """`value` (a base colour) moved so its lightness sits as far from anchor_to as it sat from
    anchor_from, with anchor_to's hue and a chroma near its own (the theme's tint)."""
    L, _c, _h = color.hex_to_oklch(value)
    L0 = color.hex_to_oklch(anchor_from)[0]
    L1, c1, h1 = color.hex_to_oklch(anchor_to)
    return color.oklch_to_hex((min(1.0, max(0.0, L1 + (L - L0))), c1, h1))


def _hue_of(value):
    return color.hex_to_oklch(value)[2]


def here_key(c):
    """Which colour is "here": `here`, else yellow when it is a warm yellow (hue 60-100), else orange."""
    if c.get("here"):
        return c["here"]
    h = _hue_of(c["yellow"])
    return "yellow" if 60.0 <= h <= 100.0 or "orange" not in c else "orange"


def from_colors(data, name, label=None):
    """A validated palette (with contrast enforced) from load_colors() data."""
    if not NAME_RE.match(name or ""):
        raise ThemegenError("the theme name must match [a-z0-9][a-z0-9._-]* (got {!r})".format(name))
    mode = data["mode"]
    base_palette = builtin("polar-night" if mode == "dark" else "winter")
    base = base_palette["colors"]
    c = dict(base)
    bg, fg = data["background"], data["foreground"]
    ink = fg
    if data.get("bright_foreground"):
        brighter = data["bright_foreground"]
        if color.contrast(brighter, bg) > color.contrast(fg, bg):
            ink = brighter

    # Structure: Arctic's lightness steps from ground, in the theme's own tint.
    for role in STRUCTURE:
        c[role] = _step(base[role], base["ground"], bg)
    c["ground"] = bg
    if data.get("lighter_background") and mode == "dark":
        c["surface-raised"] = data["lighter_background"]
    if data.get("dark_background") and mode == "dark":
        c["surface-sunken"] = data["dark_background"]
    c["frost"] = color.with_alpha(c["surface"], color.alpha_of(base["frost"]))
    c["term-background"] = bg
    # Inks: the theme's foreground, and Arctic's steps down from it.
    c["ink"] = ink
    for role in INKS:
        c[role] = _step(base[role], base["ink"], ink)
    if data.get("light_foreground") and mode == "dark":
        c["ink-muted"] = data["light_foreground"]
    c["ink-inverse"] = bg
    c["term-foreground"] = fg
    c["term-selection-foreground"] = ink
    c["term-cursor-text-color"] = bg

    # "Here": the accent family rebuilt on the here colour's hue (as the wallpaper path does).
    here = data[here_key(data)]
    _l, here_c, here_h = color.hex_to_oklch(here)
    _bl, base_c, base_h = color.hex_to_oklch(base["accent"])
    scale = min(max(here_c, derive.ACCENT_CHROMA[0]), derive.ACCENT_CHROMA[1]) / base_c if base_c > 1e-6 else 1.0
    for role in derive.ACCENT:
        c[role] = derive._rehue(base[role], here_h + color.hue_diff(base_h, _hue_of(base[role])), scale)
    if data.get("selection"):
        c["selection"] = data["selection"]
        c["term-selection-background"] = data["selection"]

    # Status colours: never the "here" colour.
    other = "orange" if here_key(data) == "yellow" else "yellow"
    status = {"success": data["green"], "warning": data.get(other, data["red"]), "error": data["red"],
              "info": data.get("accent") or data["blue"]}
    for role, value in status.items():
        c[role] = value
        c[role + "-soft"] = derive._rehue(base[role + "-soft"], _hue_of(value))
    c["error-hover"] = derive._rehue(base["error-hover"], _hue_of(data["red"]))
    c["warm"] = derive._rehue(base["warm"], _hue_of(status["warning"]))
    c["warm-soft"] = derive._rehue(base["warm-soft"], _hue_of(status["warning"]))
    for role, key in (("aurora-1", "green"), ("aurora-2", "cyan"), ("aurora-3", "blue")):
        c[role] = derive._rehue(base[role], _hue_of(data[key]))

    # The terminal's sixteen colours, in ANSI order.
    normal = ("red", "green", "yellow", "blue", "magenta", "cyan")
    c["ansi-0"] = data.get("dark_background") or c["surface-sunken"]
    c["ansi-8"] = data.get("muted") or c["ink-subtle"]
    c["ansi-7"] = data.get("light_foreground") or fg
    c["ansi-15"] = data.get("bright_foreground") or ink
    for i, key in enumerate(normal):
        c["ansi-{}".format(i + 1)] = data[key]
        c["ansi-{}".format(i + 9)] = data.get("bright_" + key) or data[key]
    if mode == "light":      # a light terminal's "black" and "white" are both dark, as in Winter
        c["ansi-0"], c["ansi-7"] = fg, c["ink-subtle"]
        c["ansi-15"] = data.get("dark_foreground") or c["ink-subtle"]

    derive.enforce(c)
    derive._meet_guarantees(c, mode)
    p = {
        "name": name,
        "label": label or data.get("label") or name,
        "mode": mode,
        "base": base_palette["name"],
        "colors": {r: c[r] for r in ROLES},
        "wallpaper": base_palette["wallpaper"],
        "lock_wallpaper": base_palette["lock_wallpaper"],
    }
    p["colors"]["shadow"] = base["shadow"]
    if data.get("pair"):
        p["pair"] = data["pair"]
    p["gallery"] = True
    return validate(p)
