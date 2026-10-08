"""Palettes: the JSON a theme is rendered from (docs/BUILD-SPEC.md, Theming).

    {"name": "polar-night", "label": "Polar night", "mode": "dark", "base": "polar-night",
     "colors": {<every role in ROLES>: "#rrggbb" | "#rrggbbaa", ...},
     "wallpaper": "aurora-polar-night", "lock_wallpaper": "fox-polar-night"}

Static themes (Winter, Polar night) are palettes built from design/exports/arctic-tokens.json.
"""
import copy
import json
import os
import re

from . import color

PKG_DIR = os.path.dirname(os.path.abspath(__file__))


class ThemegenError(Exception):
    """A user-facing error (bad palette, bad template, missing file). exit status 2."""


# Every colour role a palette must define, in the order of the design tokens.
ROLES = (
    "ground", "surface", "surface-raised", "surface-sunken", "frost", "scrim", "line",
    "line-strong", "ink", "ink-muted", "ink-subtle", "ink-disabled", "ink-inverse", "accent",
    "accent-hover", "accent-pressed", "on-accent", "accent-text", "accent-soft", "accent-edge",
    "focus", "selection", "warm", "warm-soft", "success", "success-soft", "warning",
    "warning-soft", "error", "error-soft", "on-error", "error-hover", "info", "info-soft",
    "aurora-1", "aurora-2", "aurora-3", "term-background", "term-foreground", "term-cursor",
    "term-cursor-text-color", "term-selection-background", "term-selection-foreground",
) + tuple("ansi-{}".format(i) for i in range(16))

# Colours the engine adds when a palette leaves them out (templates may use them).
#   shadow  window/drop shadow colour (Mango shadowscolor): the design's shadow-lg colour
OPTIONAL_ROLES = ("shadow",)

MODES = ("dark", "light")
BUILTINS = {
    # Packaged photo defaults retain the accessible Winter / Polar night colours.
    "winter": ("light", "/usr/share/backgrounds/arctic/default.jpg", "/usr/share/backgrounds/arctic/default.jpg"),
    "polar-night": ("dark", "/usr/share/backgrounds/arctic/default.jpg", "/usr/share/backgrounds/arctic/default.jpg"),
}
BUILTIN_FOR_MODE = {"light": "winter", "dark": "polar-night"}

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$")
ROLE_RE = re.compile(r"^[a-z][a-z0-9-]*$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


# ---- design data ----------------------------------------------------------------------------

def data_dir():
    """The design data the engine reads (tokens, GTK exports, icons, logos).

    $ARCTIC_THEMEGEN_DATA, else <package>/data (installed: /usr/share/arctic/themegen/data),
    else the package's parent (the repository: design/)."""
    for d in (os.environ.get("ARCTIC_THEMEGEN_DATA"), os.path.join(PKG_DIR, "data"),
              os.path.dirname(PKG_DIR)):
        if d and os.path.isfile(os.path.join(d, "exports", "arctic-tokens.json")):
            return d
    raise ThemegenError("design data not found (exports/arctic-tokens.json); set ARCTIC_THEMEGEN_DATA")


_TOKENS = {}


def tokens():
    """design/exports/arctic-tokens.json (cached)."""
    path = os.path.join(data_dir(), "exports", "arctic-tokens.json")
    if path not in _TOKENS:
        with open(path, encoding="utf-8") as f:
            _TOKENS[path] = json.load(f)
    return _TOKENS[path]


def shadow_color(mode):
    """The design's large shadow colour for a mode: the most opaque colour in shadow-lg,
    ignoring inset layers (dark #000000cc, light #12171e33)."""
    spec = tokens().get("shadow", {}).get(mode, {}).get("shadow-lg", "")
    best = None
    for layer in spec.split(","):
        if "inset" in layer:
            continue
        for c in re.findall(r"#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?\b", layer):
            a = color.alpha_of(c)
            a = 255 if a is None else a
            if best is None or a > best[0]:
                best = (a, c.lower())
    if best:
        return best[1]
    return "#000000cc" if mode == "dark" else "#12171e33"


# ---- builtins ---------------------------------------------------------------------------------

def builtin(name):
    """The static palette `name` (winter | polar-night) from the design tokens."""
    if name not in BUILTINS:
        raise ThemegenError("unknown built-in theme '{}' (winter or polar-night)".format(name))
    mode, wallpaper, lock_wallpaper = BUILTINS[name]
    tok = tokens()
    colors = dict(tok["themes"][mode])
    colors["shadow"] = shadow_color(mode)
    return {
        "name": name,
        "label": tok["themeNames"][mode],
        "mode": mode,
        "base": name,
        "colors": colors,
        "wallpaper": wallpaper,
        "lock_wallpaper": lock_wallpaper,
    }


def load(path_or_name):
    """A palette from a JSON file ('-' = stdin) or, when no such file exists, a built-in name."""
    if path_or_name == "-":
        import sys
        text = sys.stdin.read()
        where = "stdin"
    elif os.path.isfile(path_or_name):
        with open(path_or_name, encoding="utf-8") as f:
            text = f.read()
        where = path_or_name
    elif path_or_name in BUILTINS:
        return builtin(path_or_name)
    else:
        raise ThemegenError("no such palette file: {}".format(path_or_name))
    try:
        data = json.loads(text)
    except ValueError as e:
        raise ThemegenError("{}: not valid JSON ({})".format(where, e))
    return validate(data, where)


# ---- validation -------------------------------------------------------------------------------

def _text(value, key, where, allow_empty=True):
    if not isinstance(value, str):
        raise ThemegenError("{}: '{}' must be a string".format(where, key))
    if _CONTROL_RE.search(value):
        raise ThemegenError("{}: '{}' must be a single line without control characters".format(where, key))
    if not allow_empty and not value.strip():
        raise ThemegenError("{}: '{}' must not be empty".format(where, key))
    if len(value) > 4096:
        raise ThemegenError("{}: '{}' is too long".format(where, key))
    return value


def validate(data, where="palette"):
    """Check a palette and return a normalised copy: every role present and a valid colour,
    optional roles filled in, missing optional fields defaulted. Raises ThemegenError."""
    if not isinstance(data, dict):
        raise ThemegenError("{}: a palette is a JSON object".format(where))
    p = copy.deepcopy(data)
    name = p.get("name")
    if not isinstance(name, str) or not NAME_RE.match(name):
        raise ThemegenError("{}: 'name' must match [a-z0-9][a-z0-9._-]* (got {!r})".format(where, name))
    mode = p.get("mode")
    if mode not in MODES:
        raise ThemegenError("{}: 'mode' must be dark or light (got {!r})".format(where, mode))
    p["label"] = _text(p.get("label", name), "label", where, allow_empty=False)
    base = p.get("base", BUILTIN_FOR_MODE[mode])
    if not isinstance(base, str) or not NAME_RE.match(base):
        raise ThemegenError("{}: 'base' must be a theme name (got {!r})".format(where, base))
    p["base"] = base
    defaults = BUILTINS.get(base) if base in BUILTINS and BUILTINS[base][0] == mode else BUILTINS[BUILTIN_FOR_MODE[mode]]
    p["wallpaper"] = _text(p.get("wallpaper", defaults[1]), "wallpaper", where)
    p["lock_wallpaper"] = _text(p.get("lock_wallpaper", defaults[2]), "lock_wallpaper", where)
    colors = p.get("colors")
    if not isinstance(colors, dict):
        raise ThemegenError("{}: 'colors' must be an object of role: \"#rrggbb\"".format(where))
    missing = [r for r in ROLES if r not in colors]
    if missing:
        raise ThemegenError("{}: colors is missing {}".format(where, ", ".join(missing)))
    for role, value in colors.items():
        if not isinstance(role, str) or not ROLE_RE.match(role):
            raise ThemegenError("{}: bad colour role name {!r}".format(where, role))
        if not color.is_hex(value):
            raise ThemegenError("{}: colors.{} must be #rrggbb or #rrggbbaa (got {!r})".format(where, role, value))
    if "shadow" not in colors:
        colors["shadow"] = shadow_color(mode)
    return p


def dumps(p):
    """Palette -> JSON text (roles in design order, then any extra roles)."""
    colors = p["colors"]
    ordered = {r: colors[r] for r in ROLES}
    for r in colors:
        if r not in ordered:
            ordered[r] = colors[r]
    out = {k: p[k] for k in ("name", "label", "mode", "base") if k in p}
    out["colors"] = ordered
    for k in ("wallpaper", "lock_wallpaper"):
        out[k] = p.get(k, "")
    for k, v in p.items():
        if k not in out:
            out[k] = v
    return json.dumps(out, indent=2, ensure_ascii=False) + "\n"
