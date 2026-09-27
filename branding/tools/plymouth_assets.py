#!/usr/bin/env python3
"""Plymouth theme images for Arctic Linux (called by build-plymouth-theme.sh).

    plymouth_assets.py SRC_SVG_DIR FONTS_DIR OUT_DIR

The script theme scales everything from the 960x600 BootSplash mockup, so
images are drawn at 2x mockup size (4x for the mark) and scaled down at run
time; glow.png is soft, so 1x is enough.

    mark.png, mark@2x.png            fox, snow-100 with amber eyes (224 / 448 px)
    mark-blink.png, mark-blink@2x.png  same, eyes closed
    dot.png                          12 px amber dot
    glow.png                         the aurora glow: 520x220 ellipse, blur 60, 35 %
    entry.png                        Input (lg), focused: 640x88
    lock.png                         lock icon for the entry (36 px)
    bullet.png, caret.png            passphrase bullets (16 px) and the amber caret
    prompt.png                       "Enter your disk passphrase" (Figtree 500, 2x)
    capslock.png                     "Caps Lock is on" hint (warning colour, 2x)
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

SNOW_100 = "#f3f6f8"
EYE = "#f6bd55"
ACCENT = (0xF6, 0xBD, 0x55)
INK = (0xE9, 0xEE, 0xF3)
INK_MUTED = (0xAE, 0xB9, 0xC5)
WARNING = (0xF4, 0xA2, 0x70)
SURFACE_RAISED = "#232b36"
AURORA = [(0x3F, 0xBF, 0x8F), (0x2F, 0x9F, 0xB0), (0x2F, 0x5F, 0x9A)]

LOCK = ("M7.5 10.5H16.5A2.5 2.5 0 0 1 19 13V18A2.5 2.5 0 0 1 16.5 20.5H7.5A2.5 2.5 0 0 1 5 18V13"
        "A2.5 2.5 0 0 1 7.5 10.5Z M8 10.5V8a4 4 0 0 1 8 0v2.5 M12 14.5v2")
ALERT = "M12 4.2l8.8 15.3H3.2z M12 10v4.2 M12 17h.01"


def rsvg(svg, w, h):
    with tempfile.TemporaryDirectory() as d:
        s, p = os.path.join(d, "i.svg"), os.path.join(d, "o.png")
        open(s, "w").write(svg)
        subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", p, s], check=True)
        return Image.open(p).convert("RGBA")


def recolour_mark(src_svg, colour):
    return open(src_svg).read().replace("#e9eef3", colour)


def icon_svg(path, colour, size, stroke):
    k = 24 / size
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="{size}" height="{size}">'
            f'<path d="{path}" fill="none" stroke="{colour}" stroke-width="{stroke * k}" '
            f'stroke-linecap="round" stroke-linejoin="round"/></svg>')


def text_image(text, font_path, px, colour):
    font = ImageFont.truetype(font_path, px)
    l, t, r, b = font.getbbox(text)
    asc, desc = font.getmetrics()
    im = Image.new("RGBA", (r - l + 4, asc + desc + 4), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((2 - l, 2), text, font=font, fill=colour + (255,))
    return im


def glow():
    # 520x220 ellipse with the aurora gradient (left to right), CSS blur(60px),
    # opacity .35 (Splash, dark) -> padded canvas so the blur is not clipped.
    pad = 180
    w, h = 520 + 2 * pad, 220 + 2 * pad
    grad = Image.new("RGB", (w, h))
    px = grad.load()
    for x in range(w):
        t = min(max((x - pad) / 520, 0), 1)
        if t < 0.5:
            a, b, f = AURORA[0], AURORA[1], t / 0.5
        else:
            a, b, f = AURORA[1], AURORA[2], (t - 0.5) / 0.5
        c = tuple(round(a[i] + (b[i] - a[i]) * f) for i in range(3))
        for y in range(h):
            px[x, y] = c
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).ellipse((pad, pad, pad + 520, pad + 220), fill=round(255 * 0.35))
    mask = mask.filter(ImageFilter.GaussianBlur(60))
    out = grad.convert("RGBA")
    out.putalpha(mask)
    return out


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    src, fonts, out = sys.argv[1:]
    os.makedirs(out, exist_ok=True)
    save = lambda im, name: im.save(os.path.join(out, name), optimize=True)

    for name, svg in (("mark", "arctic-mark-polar-night.svg"), ("mark-blink", "arctic-mark-polar-night-blink.svg")):
        data = recolour_mark(os.path.join(src, svg), SNOW_100)
        save(rsvg(data, 224, 224), f"{name}.png")
        save(rsvg(data, 448, 448), f"{name}@2x.png")

    save(rsvg(f'<svg xmlns="http://www.w3.org/2000/svg" width="12" height="12">'
              f'<circle cx="6" cy="6" r="6" fill="{EYE}"/></svg>', 12, 12), "dot.png")
    save(glow(), "glow.png")

    # Input (lg), focused: 320x44 at 1x -> 640x88. Fill surface-raised, 1 px
    # focus border + 1 px focus ring (box-shadow 0 0 0 1px), radius 10.
    w, h = 640, 88
    save(rsvg(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
              f'<rect x="2" y="2" width="{w - 4}" height="{h - 4}" rx="20" fill="{SURFACE_RAISED}" '
              f'stroke="#f6bd55" stroke-width="4"/></svg>', w, h), "entry.png")
    save(rsvg(icon_svg(LOCK, "#aeb9c5", 36, 3.5), 36, 36), "lock.png")
    save(rsvg(f'<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
              f'<circle cx="8" cy="8" r="7" fill="#e9eef3"/></svg>', 16, 16), "bullet.png")
    save(Image.new("RGBA", (3, 36), ACCENT + (255,)), "caret.png")

    medium = os.path.join(fonts, "Figtree-Medium.ttf")
    save(text_image("Enter your disk passphrase", medium, 30, INK), "prompt.png")
    # "Caps Lock is on" with the alert icon, in `warning` (status = icon + word)
    txt = text_image("Caps Lock is on", medium, 26, WARNING)
    ic = rsvg(icon_svg(ALERT, "#f4a270", 28, 3.5), 28, 28)
    cap = Image.new("RGBA", (ic.width + 10 + txt.width, max(ic.height, txt.height)), (0, 0, 0, 0))
    cap.alpha_composite(ic, (0, (cap.height - ic.height) // 2))
    cap.alpha_composite(txt, (ic.width + 10, (cap.height - txt.height) // 2))
    save(cap, "capslock.png")
    print(f"plymouth images written to {out}")


if __name__ == "__main__":
    main()
