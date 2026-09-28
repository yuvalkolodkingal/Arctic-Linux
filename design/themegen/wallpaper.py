"""Wallpaper analysis: the colours a palette is derived from (Pillow).

The approach follows the tools that do this well, simplified for one job — an accent and a
tint that keep the Arctic look:

  matugen / Material You   Wu quantiser + weighted k-means in L*a*b*, then colours scored by
                           chroma and by how much of the image shares their hue; the winner
                           seeds tonal palettes whose tones (≈ lightness) fix the contrast.
  wallust                  k-means / histogram backends in Lab or LCH, palettes sorted by
                           lightness, optional WCAG contrast correction against the background.
  pywal                    ImageMagick colour reduction to 16 colours (median cut) in RGB,
                           darkest as background — no perceptual space, no contrast guarantee.

Here: the image is downscaled (JPEG decodes at 1/2..1/8 scale directly), reduced to 128 colours
by Pillow's median cut (C, fast; like the Wu stage), and those are clustered by weighted k-means
in OKLab. The seed (accent) is the cluster with the best mix of chroma and "hue share" — the
fraction of the image, weighted by colourfulness, within ±15° of its hue — as in Material's
scoring. The tint for the neutral colours is the image's mean OKLab (a, b): its direction is the
overall colour cast, its length how strong the cast is (opposite colours cancel out). Everything
is deterministic: no random initialisation, stable sort orders.
"""
import math
import os
import shutil
import subprocess
import tempfile

from . import color
from .palette import ThemegenError

MAX_SIDE = 256          # analysis size (long side, pixels)
QUANT_COLORS = 128      # median-cut colours before clustering
CLUSTERS = 10           # k-means clusters in OKLab
MIN_SEED_CHROMA = 0.04  # OKLCH chroma below this is not an accent candidate (greys, beiges)
MIN_HUE_SHARE = 0.01    # a candidate hue must cover >= 1% of the (colourfulness-weighted) image
HUE_WINDOW = 15         # degrees either side when measuring a hue's share
LIGHT_THRESHOLD = 0.62  # mean OKLab L above which --mode auto picks a light theme

SVG_SUFFIXES = (".svg", ".svgz")


class Analysis:
    """What the palette derivation needs to know about an image."""

    def __init__(self, mean_l, cast, seed, clusters, pixels):
        self.mean_l = mean_l            # count-weighted mean OKLab L (0..1)
        self.cast = cast                # (a, b): mean OKLab chroma vector — the colour cast
        self.seed = seed                # (L, C, h) OKLCH of the accent seed, or None (greyscale)
        self.clusters = clusters        # [(weight 0..1, (L, a, b))], heaviest first
        self.pixels = pixels            # pixels analysed

    @property
    def mode(self):
        return "light" if self.mean_l > LIGHT_THRESHOLD else "dark"

    @property
    def cast_strength(self):
        return math.hypot(*self.cast)

    @property
    def cast_hue(self):
        a, b = self.cast
        return math.degrees(math.atan2(b, a)) % 360.0

    def as_dict(self):
        return {
            "mean_lightness": round(self.mean_l, 4),
            "mode": self.mode,
            "cast": {"hue": round(self.cast_hue, 1), "chroma": round(self.cast_strength, 4)},
            "seed": None if self.seed is None else color.oklch_to_hex(self.seed),
        }


def _open(path):
    from PIL import Image
    return Image.open(path)


def load_small(path, max_side=MAX_SIDE):
    """The image as a small RGBA Pillow image (long side <= max_side)."""
    try:
        from PIL import Image
    except ImportError:
        raise ThemegenError("Pillow (python3-pillow) is needed to read wallpapers")
    if not os.path.isfile(path):
        raise ThemegenError("no such picture: {}".format(path))
    tmp = None
    try:
        if path.lower().endswith(SVG_SUFFIXES):
            if not shutil.which("rsvg-convert"):
                raise ThemegenError("{}: SVG wallpapers need rsvg-convert (librsvg2-tools)".format(path))
            fd, tmp = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            r = subprocess.run(["rsvg-convert", "-w", str(max_side * 2), "-o", tmp, path],
                               capture_output=True, timeout=30)
            if r.returncode:
                raise ThemegenError("{}: could not render the SVG".format(path))
            path_to_open = tmp
        else:
            path_to_open = path
        try:
            with _open(path_to_open) as img:
                try:
                    img.seek(0)
                except EOFError:
                    pass
                # draft() lets JPEG decode at 1/2, 1/4 or 1/8 scale: most of the speed-up.
                img.draft("RGB", (max_side * 2, max_side * 2))
                if img.mode in ("I", "F") or img.mode.startswith("I;"):
                    # 16-bit / float greyscale: scale to 8 bits before converting.
                    img = img.convert("I").point(lambda v: v * (1 / 256.0)).convert("L")
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGBA" if ("transparency" in img.info or img.mode in ("LA", "PA", "RGBa")) else "RGB")
                img.thumbnail((max_side, max_side), Image.Resampling.BOX, reducing_gap=2.0)
                return img.copy() if img.mode == "RGBA" else img.convert("RGB")
        except ThemegenError:
            raise
        except Exception as e:  # Pillow raises many types for unreadable files
            raise ThemegenError("{}: not a picture Pillow can read ({})".format(path, e))
    finally:
        if tmp:
            try:
                os.unlink(tmp)
            except OSError:
                pass


def weighted_colors(img):
    """[(count, (r, g, b) 0..255)] after median-cut reduction; transparent pixels are ignored."""
    from PIL import Image
    alpha = None
    if img.mode == "RGBA":
        alpha = img.getchannel("A")
        rgb = img.convert("RGB")
    else:
        rgb = img
    q = rgb.quantize(colors=QUANT_COLORS, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    pal = q.getpalette() or []
    mask = None
    if alpha is not None and alpha.getextrema()[0] < 128:
        mask = alpha.point(lambda a: 255 if a >= 128 else 0)
    hist = q.histogram(mask=mask)
    items = [(i, n) for i, n in enumerate(hist[:len(pal) // 3])]
    return [(n, (pal[3 * i], pal[3 * i + 1], pal[3 * i + 2])) for i, n in items if n > 0]


def kmeans(points, k=CLUSTERS, iterations=25):
    """Weighted k-means in OKLab. points: [(weight, (L, a, b))]. Deterministic seeding:
    the heaviest point, then repeatedly the point with the largest weight × distance²."""
    if not points:
        return []
    pts = sorted(points, key=lambda p: (-p[0], p[1]))
    centers = [pts[0][1]]
    while len(centers) < min(k, len(pts)):
        best, best_score = None, 0.0
        for w, lab in pts:
            d = min(sum((x - y) ** 2 for x, y in zip(lab, c)) for c in centers)
            s = math.sqrt(w) * d
            if s > best_score:
                best, best_score = lab, s
        if best is None:
            break
        centers.append(best)
    assign = None
    for _ in range(iterations):
        new = []
        for w, lab in pts:
            new.append(min(range(len(centers)), key=lambda i: sum((x - y) ** 2 for x, y in zip(lab, centers[i]))))
        if new == assign:
            break
        assign = new
        sums = [[0.0, 0.0, 0.0, 0.0] for _ in centers]
        for (w, lab), i in zip(pts, assign):
            s = sums[i]
            s[0] += w
            s[1] += w * lab[0]
            s[2] += w * lab[1]
            s[3] += w * lab[2]
        centers = [(s[1] / s[0], s[2] / s[0], s[3] / s[0]) if s[0] else c for s, c in zip(sums, centers)]
    weights = [0.0] * len(centers)
    for (w, _lab), i in zip(pts, assign):
        weights[i] += w
    clusters = [(w, c) for w, c in zip(weights, centers) if w > 0]
    clusters.sort(key=lambda t: (-t[0], t[1]))
    return clusters


def colourfulness(c):
    """0 for greys, 1 from OKLCH chroma 0.06 up."""
    return color.smoothstep(0.02, 0.06, c)


def analyse_colors(weighted):
    """Analysis from [(count, (r, g, b))]."""
    total = float(sum(n for n, _ in weighted))
    if total <= 0:
        return Analysis(0.0, (0.0, 0.0), None, [], 0)
    labs = [(n / total, color.rgb8_to_oklab(rgb)) for n, rgb in weighted]
    mean_l = sum(w * lab[0] for w, lab in labs)
    cast = (sum(w * lab[1] for w, lab in labs), sum(w * lab[2] for w, lab in labs))

    # Hue histogram (1° bins), weighted by share of the image and colourfulness.
    hist = [0.0] * 360
    for w, lab in labs:
        L, C, h = color.lab_to_lch(lab)
        cf = colourfulness(C)
        if cf > 0:
            hist[int(h) % 360] += w * cf

    def share(h):
        c = int(round(h)) % 360
        return sum(hist[(c + d) % 360] for d in range(-HUE_WINDOW, HUE_WINDOW + 1))

    clusters = kmeans(labs)
    candidates = []
    for w, lab in clusters:
        L, C, h = color.lab_to_lch(lab)
        if C < MIN_SEED_CHROMA or not 0.12 <= L <= 0.97:
            continue
        s = share(h)
        if s < MIN_HUE_SHARE:
            continue
        candidates.append((s, C, h, L))
    seed = None
    if candidates:
        top_share = max(c[0] for c in candidates)
        scored = []
        for s, C, h, L in candidates:
            score = 0.7 * (s / top_share) + 0.3 * min(C / 0.16, 1.0)
            scored.append((round(score, 9), round(s, 9), round(C, 9), -round(h, 6), (L, C, h)))
        scored.sort(reverse=True)
        L, C, h = scored[0][4]
        # Refine the hue: colourfulness-weighted circular mean of the colours near it.
        x = y = cw = 0.0
        for w, lab in labs:
            Lp, Cp, hp = color.lab_to_lch(lab)
            if abs(color.hue_diff(h, hp)) <= HUE_WINDOW:
                wt = w * colourfulness(Cp) * Cp
                x += wt * math.cos(math.radians(hp))
                y += wt * math.sin(math.radians(hp))
                cw += wt
        if cw > 0:
            h = math.degrees(math.atan2(y, x)) % 360.0
        seed = (L, C, h)
    return Analysis(mean_l, cast, seed, clusters, int(total))


def analyse(path):
    """Analyse the picture at `path`."""
    return analyse_colors(weighted_colors(load_small(path)))
