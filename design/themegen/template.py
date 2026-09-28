"""The template language: {{placeholder}} and {{role|filter}}, nothing else.

    {{role}}              the palette value as written (#rrggbb or #rrggbbaa)
    {{role|hex}}          #rrggbb (alpha dropped)
    {{role|hexa}}         #rrggbbaa (ff when the palette has no alpha)
    {{role|nohash}}       rrggbb
    {{role|nohasha}}      rrggbbaa
    {{role|rgb}}          r, g, b
    {{role|rgba}}         rgba(r, g, b, a)  a from the palette alpha (1 if none), up to 3 decimals
    {{role|alpha:0.35}}   rgba(r, g, b, 0.35)
    {{role|argb}}         #aarrggbb (Qt)
    {{name}} {{label}} {{mode}} {{scheme}} {{is_dark}} {{wallpaper}} {{lock_wallpaper}}
    {{font.sans}} {{font.mono}}

An unknown placeholder or filter, whitespace inside the braces, a filter on a scalar or an
unterminated {{ is an error (TemplateError, with file and line).
"""
import re

from . import color
from .palette import ThemegenError

PLACEHOLDER_RE = re.compile(r"\{\{(.*?)\}\}")
BODY_RE = re.compile(r"^(?P<name>[a-z][a-z0-9_.-]*)(?:\|(?P<filter>[a-z]+)(?::(?P<arg>[^|]+))?)?$")
FILTERS = ("hex", "hexa", "nohash", "nohasha", "rgb", "rgba", "alpha", "argb")
SCALARS = ("name", "label", "mode", "scheme", "is_dark", "wallpaper", "lock_wallpaper",
           "font.sans", "font.mono")


class TemplateError(ThemegenError):
    pass


def _alpha_text(a):
    """0..1 float -> '0.82', '0.8', '1', '0' (up to 3 decimals, no trailing zeros)."""
    s = "{:.3f}".format(round(a, 3)).rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


def apply_filter(value, filt, arg=None):
    """Format a hex colour with one of FILTERS."""
    (r, g, b), a = color.parse_hex(value)
    hx = "{:02x}{:02x}{:02x}".format(r, g, b)
    aa = "{:02x}".format(255 if a is None else a)
    if filt == "hex":
        return "#" + hx
    if filt == "hexa":
        return "#" + hx + aa
    if filt == "nohash":
        return hx
    if filt == "nohasha":
        return hx + aa
    if filt == "rgb":
        return "{}, {}, {}".format(r, g, b)
    if filt == "rgba":
        return "rgba({}, {}, {}, {})".format(r, g, b, "1" if a is None else _alpha_text(a / 255.0))
    if filt == "alpha":
        return "rgba({}, {}, {}, {})".format(r, g, b, arg)
    if filt == "argb":
        return "#" + aa + hx
    raise TemplateError("unknown filter '{}'".format(filt))


def context(palette, fonts):
    """The values a template can use: every palette colour plus the scalars."""
    dark = palette["mode"] == "dark"
    scalars = {
        "name": palette["name"],
        "label": palette["label"],
        "mode": palette["mode"],
        "scheme": "prefer-dark" if dark else "prefer-light",
        "is_dark": "true" if dark else "false",
        "wallpaper": palette.get("wallpaper", ""),
        "lock_wallpaper": palette.get("lock_wallpaper", ""),
        "font.sans": fonts.get("sans", ""),
        "font.mono": fonts.get("mono", ""),
    }
    return dict(palette["colors"]), scalars


def render(text, colors, scalars, where="template"):
    """Substitute every placeholder in `text`."""
    out = []
    for lineno, line in enumerate(text.splitlines(keepends=True), 1):
        def sub(m, lineno=lineno):
            body = m.group(1)
            loc = "{}:{}".format(where, lineno)
            if not body or any(c.isspace() for c in body):
                raise TemplateError("{}: no whitespace allowed inside {{{{…}}}}: {}".format(loc, m.group(0)))
            mb = BODY_RE.match(body)
            if not mb:
                raise TemplateError("{}: malformed placeholder {}".format(loc, m.group(0)))
            name, filt, arg = mb.group("name"), mb.group("filter"), mb.group("arg")
            if name in colors:
                value = colors[name]
                if filt is None:
                    if arg is not None:
                        raise TemplateError("{}: malformed placeholder {}".format(loc, m.group(0)))
                    return value
                if filt not in FILTERS:
                    raise TemplateError("{}: unknown filter '{}' in {}".format(loc, filt, m.group(0)))
                if filt == "alpha":
                    try:
                        ok = arg is not None and re.match(r"^(0|1|0?\.[0-9]+|[01]\.[0-9]*)$", arg) and 0.0 <= float(arg) <= 1.0
                    except ValueError:
                        ok = False
                    if not ok:
                        raise TemplateError("{}: alpha needs a number 0..1, e.g. {{{{{}|alpha:0.35}}}}".format(loc, name))
                elif arg is not None:
                    raise TemplateError("{}: filter '{}' takes no argument in {}".format(loc, filt, m.group(0)))
                return apply_filter(value, filt, arg)
            if name in scalars:
                if filt is not None:
                    raise TemplateError("{}: '{}' is not a colour; filters only apply to colours".format(loc, name))
                return scalars[name]
            raise TemplateError("{}: unknown placeholder {}".format(loc, m.group(0)))
        rendered = PLACEHOLDER_RE.sub(sub, line)
        # Anything left that opens a placeholder was never closed (on this line).
        rest = PLACEHOLDER_RE.sub("", line)
        if "{{" in rest:
            raise TemplateError("{}:{}: unterminated '{{{{'".format(where, lineno))
        out.append(rendered)
    return "".join(out)
