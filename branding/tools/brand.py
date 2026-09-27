#!/usr/bin/env python3
"""Arctic Linux brand SVG generator.

A Python port of the design system builders (components/bundle.js `mark()` and
`wordmark()`), so the build does not need node or the design bundle. It writes
every logo variant the OS needs as standalone SVG:

    arctic-mark-{winter,polar-night}.svg          colour fox, amber eyes
    arctic-mark-mono-{charcoal,snow}.svg          one colour, eyes cut out
    arctic-mark-16-{charcoal,snow}.svg            16-20 px drawing: no eyes, wider gap
    arctic-mark-polar-night-blink.svg             eyes closed (boot splash blink frame)
    arctic-lockup-{winter,polar-night}.svg        mark + "arctic linux" (outlined Figtree)
    arctic-lockup-mono-{charcoal,snow}.svg
    arctic-logo-icon.svg / arctic-logo-icon-16.svg   app-icon tile (os-release LOGO)

Usage: brand.py OUT_DIR FONTS_DIR
FONTS_DIR holds the TTFs made by fonts.py (Figtree-SemiBold.ttf, Figtree-Regular.ttf).
"""
import os
import sys

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

# ---- colours (design/tokens.json) -------------------------------------------
CHARCOAL = "#151a21"      # ink (winter)
SNOW = "#e9eef3"          # ink (polar night)
EYE_WINTER = "#d98b1f"    # amber-500, logo eyes on light
EYE_NIGHT = "#f6bd55"     # amber-300, logo eyes on dark
MUTED_WINTER = "#4a5663"  # ink-muted (winter)
MUTED_NIGHT = "#aeb9c5"   # ink-muted (polar night)
TILE = "#1a212a"          # slate-900, the dark tile behind the icon

# ---- the fox mark, 48-unit grid (bundle.js) ---------------------------------
FOX_HEAD = "M14 6.5 L20 13 H28 L34 6.5 L38.5 20.5 L24 31.5 L9.5 20.5 Z"
FOX_HEAD_SMALL = "M13.5 7 L20 13.5 H28 L34.5 7 L38.5 21 L24 31 L9.5 21 Z"
FOX_TAIL = "M9.5 38.5 C 15 43.5, 27 44, 34.5 39.5 C 41.5 35, 44.5 26, 41 16.5"
FOX_FLUFF = "M27 41.2 C 33 39.5, 39 34.5, 40.6 27"
FOX_EYES = [(18.2, 20.2, 12), (29.8, 20.2, -12)]


def mark_body(ink, eye=None, small=False, blink=False, uid="m"):
    """Inner SVG (defs + paths) of the mark on the 48x48 grid."""
    gap = 16 if small else 14
    cut = f'<path d="{FOX_TAIL}" fill="none" stroke="#000" stroke-width="{gap}" stroke-linecap="round"/>'
    if not small:
        cut += f'<path d="{FOX_FLUFF}" fill="none" stroke="#000" stroke-width="15" stroke-linecap="round"/>'
    eyes_mask = eyes_fill = ""
    if not small:
        for cx, cy, rot in FOX_EYES:
            ry = 0.38 if blink else 1.35
            el = (f'<ellipse cx="{cx}" cy="{cy}" rx="2" ry="{ry}" '
                  f'transform="rotate({rot} {cx} {cy})" fill="')
            if eye:
                eyes_fill += el + eye + '"/>'
            else:
                eyes_mask += el + '#000"/>'
    head = FOX_HEAD_SMALL if small else FOX_HEAD
    out = (f'<defs><mask id="{uid}h" maskUnits="userSpaceOnUse" x="0" y="0" width="48" height="48">'
           f'<rect width="48" height="48" fill="#fff"/>{cut}{eyes_mask}</mask></defs>'
           f'<path mask="url(#{uid}h)" d="{head}" fill="{ink}" stroke="{ink}" stroke-width="5" stroke-linejoin="round"/>'
           f'<path d="{FOX_TAIL}" fill="none" stroke="{ink}" stroke-width="{10 if small else 9}" stroke-linecap="round"/>')
    if not small:
        out += f'<path d="{FOX_FLUFF}" fill="none" stroke="{ink}" stroke-width="10.5" stroke-linecap="round"/>'
    return out + eyes_fill


def svg_doc(w, h, body, title="Arctic Linux"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {fmt(w)} {fmt(h)}" '
            f'width="{fmt(w)}" height="{fmt(h)}" role="img"><title>{title}</title>{body}</svg>\n')


def fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def mark_svg(ink, eye=None, small=False, blink=False, size=48):
    body = mark_body(ink, eye, small, blink)
    if size != 48:
        body = f'<g transform="scale({fmt(size / 48)})">{body}</g>'
    return svg_doc(size, size, body)


# ---- outlined text -----------------------------------------------------------
class Face:
    def __init__(self, path):
        self.font = TTFont(path)
        self.upm = self.font["head"].unitsPerEm
        self.cmap = self.font.getBestCmap()
        self.gs = self.font.getGlyphSet()
        self.hmtx = self.font["hmtx"]
        hhea = self.font["hhea"]
        os2 = self.font["OS/2"]
        if os2.fsSelection & (1 << 7):
            self.ascent, self.descent, self.gap = os2.sTypoAscender, -os2.sTypoDescender, os2.sTypoLineGap
        else:
            self.ascent, self.descent, self.gap = hhea.ascent, -hhea.descent, hhea.lineGap
        self._kern = self._load_kerning()

    def _load_kerning(self):
        """Pair adjustments from the GPOS 'kern' feature (PairPos formats 1 and 2)."""
        pairs, classes = {}, []
        if "GPOS" not in self.font:
            return pairs, classes
        gpos = self.font["GPOS"].table
        lookup_ids = set()
        for fr in gpos.FeatureList.FeatureRecord:
            if fr.FeatureTag == "kern":
                lookup_ids.update(fr.Feature.LookupListIndex)
        for li in sorted(lookup_ids):
            lookup = gpos.LookupList.Lookup[li]
            for st in lookup.SubTable:
                if lookup.LookupType == 9:
                    if st.ExtensionLookupType != 2:
                        continue
                    st = st.ExtSubTable
                elif lookup.LookupType != 2:
                    continue
                cov = st.Coverage.glyphs
                if st.Format == 1:
                    for i, first in enumerate(cov):
                        for pvr in st.PairSet[i].PairValueRecord:
                            v = getattr(pvr.Value1, "XAdvance", 0) if pvr.Value1 else 0
                            pairs.setdefault((first, pvr.SecondGlyph), v)
                elif st.Format == 2:
                    classes.append((set(cov), st.ClassDef1.classDefs, st.ClassDef2.classDefs, st.Class1Record))
        return pairs, classes

    def kern(self, a, b):
        pairs, classes = self._kern
        if (a, b) in pairs:
            return pairs[(a, b)]
        for cov, cd1, cd2, recs in classes:
            if a in cov:
                c1, c2 = cd1.get(a, 0), cd2.get(b, 0)
                v = recs[c1].Class2Record[c2].Value1
                return getattr(v, "XAdvance", 0) if v else 0
        return 0

    def glyph(self, ch):
        return self.cmap[ord(ch)]


def text_paths(runs, size, tracking_em, x0, baseline, fill_default):
    """runs = [(Face, text, fill)] -> (svg path elements, advance width)."""
    out, x = [], x0
    prev = None
    for face, text, fill in runs:
        scale = size / face.upm
        for ch in text:
            g = face.glyph(ch)
            if prev is not None and prev[0] is face:
                x += face.kern(prev[1], g) * scale
            pen = SVGPathPen(face.gs)
            tpen = TransformPen(pen, (scale, 0, 0, -scale, x, baseline))
            face.gs[g].draw(tpen)
            d = pen.getCommands()
            if d:
                out.append(f'<path d="{d}" fill="{fill or fill_default}"/>')
            x += face.hmtx[g][0] * scale + tracking_em * size
            prev = (face, g)
    return "".join(out), x - x0


def lockup_svg(bold, regular, ink, muted, eye, size=40.0):
    """The wordmark lockup: mark (1.25 x font size) + 0.3em gap + "arctic linux".

    Mirrors `.ar-wordmark` in bundle.css: weight 600 "arctic", weight 400
    " linux" in ink-muted, letter-spacing -0.02em, items centred vertically.
    """
    mark = round(size * 1.25)
    gap = 0.3 * size
    line = (bold.ascent + bold.descent + bold.gap) / bold.upm * size
    height = max(mark, line)
    text_top = (height - line) / 2
    baseline = text_top + (bold.gap / 2 + bold.ascent) / bold.upm * size
    paths, width = text_paths([(bold, "arctic", ink), (regular, " linux", muted)],
                              size, -0.02, mark + gap, baseline, ink)
    total = mark + gap + width + 0.02 * size  # drop the trailing tracking
    mark_y = (height - mark) / 2
    body = (f'<g transform="translate(0 {fmt(mark_y)}) scale({fmt(mark / 48)})">{mark_body(ink, eye)}</g>'
            f'<g>{paths}</g>')
    return svg_doc(round(total, 2), round(height, 2), body)


def icon_svg(small=False):
    """App icon: the polar-night mark on a dark rounded tile (30% radius, like app tiles)."""
    inset = 2 if small else 3
    side = 48 - 2 * inset
    r = side * 0.3
    m = 36 if not small else 38
    off = (48 - m) / 2
    body = (f'<rect x="{inset}" y="{inset}" width="{side}" height="{side}" rx="{fmt(r)}" fill="{TILE}"/>'
            f'<g transform="translate({fmt(off)} {fmt(off + (0.4 if small else 0.6))}) scale({fmt(m / 48)})">'
            f'{mark_body(SNOW, None if small else EYE_NIGHT, small=small, uid="i")}</g>')
    return svg_doc(48, 48, body)


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    out, fonts = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    bold = Face(os.path.join(fonts, "Figtree-SemiBold.ttf"))
    regular = Face(os.path.join(fonts, "Figtree-Regular.ttf"))
    files = {
        "arctic-mark-winter.svg": mark_svg(CHARCOAL, EYE_WINTER),
        "arctic-mark-polar-night.svg": mark_svg(SNOW, EYE_NIGHT),
        "arctic-mark-polar-night-blink.svg": mark_svg(SNOW, EYE_NIGHT, blink=True),
        "arctic-mark-mono-charcoal.svg": mark_svg(CHARCOAL),
        "arctic-mark-mono-snow.svg": mark_svg(SNOW),
        "arctic-mark-mono-white.svg": mark_svg("#ffffff"),
        "arctic-mark-16-charcoal.svg": mark_svg(CHARCOAL, small=True),
        "arctic-mark-16-snow.svg": mark_svg(SNOW, small=True),
        "arctic-lockup-winter.svg": lockup_svg(bold, regular, CHARCOAL, MUTED_WINTER, EYE_WINTER),
        "arctic-lockup-polar-night.svg": lockup_svg(bold, regular, SNOW, MUTED_NIGHT, EYE_NIGHT),
        "arctic-lockup-mono-charcoal.svg": lockup_svg(bold, regular, CHARCOAL, CHARCOAL, None),
        "arctic-lockup-mono-snow.svg": lockup_svg(bold, regular, SNOW, SNOW, None),
        "arctic-lockup-mono-white.svg": lockup_svg(bold, regular, "#ffffff", "#ffffff", None),
        "arctic-logo-icon.svg": icon_svg(),
        "arctic-logo-icon-16.svg": icon_svg(small=True),
    }
    for name, data in files.items():
        with open(os.path.join(out, name), "w") as f:
            f.write(data)
    print(f"wrote {len(files)} SVGs to {out}")


if __name__ == "__main__":
    main()
