"""Colour math for themegen: hex parsing, sRGB <-> OKLab/OKLCH, WCAG contrast, gamut mapping.

Only the standard library. Colours are passed around as floats:

  rgb      (r, g, b) gamma-encoded sRGB in 0..1
  lab      (L, a, b) OKLab (Björn Ottosson, 2020): L 0..1, a/b roughly -0.4..0.4
  lch      (L, C, h) OKLCH, h in degrees 0..360

Hex strings are #rrggbb or #rrggbbaa (the alpha is carried separately where it matters).
"""
import math
import re

HEX_RE = re.compile(r"^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")


# ---- hex ----------------------------------------------------------------------------------

def is_hex(value):
    return isinstance(value, str) and HEX_RE.match(value) is not None


def parse_hex(value):
    """'#rrggbb[aa]' -> ((r, g, b) as 0..255 ints, alpha 0..255 int or None)."""
    m = HEX_RE.match(value) if isinstance(value, str) else None
    if not m:
        raise ValueError("not a #rrggbb or #rrggbbaa colour: {!r}".format(value))
    h = m.group(1)
    rgb = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    alpha = int(m.group(2), 16) if m.group(2) else None
    return rgb, alpha


def to_hex(rgb8, alpha=None):
    """(r, g, b) 0..255 [+ alpha 0..255] -> '#rrggbb' / '#rrggbbaa' (lower case)."""
    s = "#{:02x}{:02x}{:02x}".format(*rgb8)
    if alpha is not None:
        s += "{:02x}".format(alpha)
    return s


def hex_to_rgb(value):
    """'#rrggbb[aa]' -> (r, g, b) floats 0..1 (alpha ignored)."""
    (r, g, b), _ = parse_hex(value)
    return (r / 255.0, g / 255.0, b / 255.0)


def rgb_to_hex(rgb, alpha=None):
    """(r, g, b) floats (clipped to 0..1) -> '#rrggbb' [+ alpha 0..255]."""
    return to_hex(tuple(int(round(min(1.0, max(0.0, c)) * 255)) for c in rgb), alpha)


def alpha_of(value):
    """The alpha byte of '#rrggbbaa', or None for '#rrggbb'."""
    return parse_hex(value)[1]


def with_alpha(value, alpha):
    """Replace/drop the alpha byte of a hex colour (alpha None -> #rrggbb)."""
    rgb, _ = parse_hex(value)
    return to_hex(rgb, alpha)


# ---- sRGB <-> linear <-> OKLab ------------------------------------------------------------

def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c):
    if c <= 0.0031308:
        return 12.92 * c
    return 1.055 * (c ** (1 / 2.4)) - 0.055 if c > 0 else 0.0


# Lookup table for the 256 possible 8-bit channel values (image pixels are 8-bit).
_LIN8 = [srgb_to_linear(i / 255.0) for i in range(256)]


def _cbrt(x):
    return math.copysign(abs(x) ** (1.0 / 3.0), x)


def linear_to_oklab(r, g, b):
    l = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    m = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    s = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = _cbrt(l), _cbrt(m), _cbrt(s)
    return (0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
            1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
            0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_)


def oklab_to_linear(L, a, b):
    l_ = L + 0.3963377774 * a + 0.2158037573 * b
    m_ = L - 0.1055613458 * a - 0.0638541728 * b
    s_ = L - 0.0894841775 * a - 1.2914855480 * b
    l, m, s = l_ ** 3, m_ ** 3, s_ ** 3
    return (4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
            -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
            -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s)


def rgb_to_oklab(rgb):
    return linear_to_oklab(*(srgb_to_linear(c) for c in rgb))


def rgb8_to_oklab(rgb8):
    return linear_to_oklab(_LIN8[rgb8[0]], _LIN8[rgb8[1]], _LIN8[rgb8[2]])


def oklab_to_rgb_unclipped(lab):
    return tuple(linear_to_srgb(c) if c >= 0 else -linear_to_srgb(-c) for c in oklab_to_linear(*lab))


def lab_to_lch(lab):
    L, a, b = lab
    C = math.hypot(a, b)
    h = math.degrees(math.atan2(b, a)) % 360.0 if C > 1e-9 else 0.0
    return (L, C, h)


def lch_to_lab(lch):
    L, C, h = lch
    r = math.radians(h)
    return (L, C * math.cos(r), C * math.sin(r))


def hex_to_oklab(value):
    return rgb_to_oklab(hex_to_rgb(value))


def hex_to_oklch(value):
    return lab_to_lch(hex_to_oklab(value))


# ---- gamut mapping ------------------------------------------------------------------------

_EPS = 1e-5


def in_gamut(lab):
    return all(-_EPS <= c <= 1 + _EPS for c in oklab_to_linear(*lab))


def oklch_to_rgb(lch):
    """OKLCH -> sRGB floats inside the gamut: chroma is reduced (lightness and hue kept) until
    the colour fits, which keeps the perceived lightness the contrast maths depends on."""
    L, C, h = lch
    L = min(1.0, max(0.0, L))
    if L >= 1.0 - 1e-9:
        return (1.0, 1.0, 1.0)
    if L <= 1e-9:
        return (0.0, 0.0, 0.0)
    if not in_gamut(lch_to_lab((L, C, h))):
        lo, hi = 0.0, C
        for _ in range(24):
            mid = (lo + hi) / 2
            if in_gamut(lch_to_lab((L, mid, h))):
                lo = mid
            else:
                hi = mid
        C = lo
    rgb = oklab_to_rgb_unclipped(lch_to_lab((L, C, h)))
    return tuple(min(1.0, max(0.0, c)) for c in rgb)


def oklch_to_hex(lch, alpha=None):
    return rgb_to_hex(oklch_to_rgb(lch), alpha)


def oklab_to_hex(lab, alpha=None):
    return oklch_to_hex(lab_to_lch(lab), alpha)


# ---- WCAG 2 contrast ----------------------------------------------------------------------

def relative_luminance(value):
    """WCAG relative luminance of a hex colour (alpha ignored)."""
    r, g, b = (srgb_to_linear(c) for c in hex_to_rgb(value))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    """WCAG 2 contrast ratio between two hex colours (1..21)."""
    ya, yb = relative_luminance(a), relative_luminance(b)
    if ya < yb:
        ya, yb = yb, ya
    return (ya + 0.05) / (yb + 0.05)


def ensure_contrast(fg, bg, ratio, direction=None):
    """Return fg (hex), moved in OKLab lightness (hue kept, chroma reduced only as the gamut
    requires) just far enough from bg to reach `ratio` against it. fg's alpha is kept.

    direction: +1 lighten, -1 darken, None = away from bg. When the target can't be reached in
    that direction, the other one is tried and the best result returned (it then still is the
    most contrasting colour possible: white or black)."""
    if contrast(fg, bg) >= ratio:
        return fg
    alpha = alpha_of(fg)
    L0, C0, h0 = hex_to_oklch(fg)
    if direction is None:
        direction = 1 if relative_luminance(fg) >= relative_luminance(bg) else -1
    best = None
    for d in (direction, -direction):
        end = 1.0 if d > 0 else 0.0
        cand = oklch_to_hex((end, C0, h0), alpha)
        if contrast(cand, bg) < ratio:
            if best is None or contrast(cand, bg) > contrast(best, bg):
                best = cand
            continue
        lo, hi = L0, end      # lo fails, hi passes
        for _ in range(30):
            mid = (lo + hi) / 2
            if contrast(oklch_to_hex((mid, C0, h0), alpha), bg) >= ratio:
                hi = mid
            else:
                lo = mid
        return oklch_to_hex((hi, C0, h0), alpha)
    return best


# ---- helpers --------------------------------------------------------------------------------

def hue_diff(a, b):
    """Signed shortest rotation from hue a to hue b, in degrees (-180..180]."""
    d = (b - a) % 360.0
    return d - 360.0 if d > 180.0 else d


def delta_e(a, b):
    """Euclidean distance in OKLab between two hex colours (a just-noticeable step is ~0.02)."""
    la, lb = hex_to_oklab(a), hex_to_oklab(b)
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(la, lb)))


def smoothstep(e0, e1, x):
    if x <= e0:
        return 0.0
    if x >= e1:
        return 1.0
    t = (x - e0) / (e1 - e0)
    return t * t * (3 - 2 * t)
