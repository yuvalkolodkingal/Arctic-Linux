#!/usr/bin/env python3
"""The Arctic fox as terminal text art, for fastfetch and neofetch.

    fastfetch_logo.py [--svg MARK.svg] [--out FILE]

Draws design/logos/arctic-mark-polar-night.svg (the fox mark with its amber eyes) with
Unicode quadrant blocks (▘▝▖▗▀▄▌▐▚▞▙▟▛▜█): 14 rows × 29 columns, each character cell
2 × 2 samples of the mark (the viewBox 4.5,4 → 48,46, so the head's axis falls on a cell
boundary and the ears come out mirror images). Cells the eyes cover are full blocks in
colour 2; everything else is colour 1 — fastfetch's `$1` / `$2` placeholders:

    fastfetch --file /usr/share/arctic/fastfetch/logo.txt --logo-color-1 white --logo-color-2 yellow

The committed copy is dotfiles/.local/share/arctic/fastfetch/logo.txt (→ /usr/share/arctic/fastfetch);
the fastfetch templates in design/themegen/templates/fastfetch carry the same text
(design/themegen/tests/test_fastfetch.py checks). Needs rsvg-convert and Pillow
(branding/tools/lib.sh runs the branding tools in a Fedora container when they are missing).
"""
import argparse
import os
import subprocess
import sys
import tempfile

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
MARK = os.path.join(REPO, "design", "logos", "arctic-mark-polar-night.svg")
OUT = os.path.join(REPO, "dotfiles", ".local", "share", "arctic", "fastfetch", "logo.txt")

ROWS, COLS = 14, 29
VIEW = (4.5, 4.0, 48.0, 46.0)      # the part of the 48 × 48 viewBox that is drawn
SCALE = 20                         # rendering pixels per viewBox unit
THRESHOLD = 0.5                    # a sample is ink when at least half covered

# (top-left, top-right, bottom-left, bottom-right) → block character
QUADRANTS = {
    (0, 0, 0, 0): " ", (1, 0, 0, 0): "▘", (0, 1, 0, 0): "▝", (1, 1, 0, 0): "▀",
    (0, 0, 1, 0): "▖", (1, 0, 1, 0): "▌", (0, 1, 1, 0): "▞", (1, 1, 1, 0): "▛",
    (0, 0, 0, 1): "▗", (1, 0, 0, 1): "▚", (0, 1, 0, 1): "▐", (1, 1, 0, 1): "▜",
    (0, 0, 1, 1): "▄", (1, 0, 1, 1): "▙", (0, 1, 1, 1): "▟", (1, 1, 1, 1): "█",
}


def is_eye(rgba):
    """The mark's eyes are amber (#f6bd55); its fur is snow (#e9eef3)."""
    r, g, b, a = rgba
    return a > 100 and r > 200 and 120 < g < 220 and b < 140


def render(svg):
    with tempfile.TemporaryDirectory() as tmp:
        png = os.path.join(tmp, "mark.png")
        subprocess.run(["rsvg-convert", "-w", str(48 * SCALE), "-h", str(48 * SCALE), "-o", png, svg],
                       check=True)
        image = Image.open(png).convert("RGBA")
        image.load()
    x0, y0, x1, y1 = (round(v * SCALE) for v in VIEW)
    return image.crop((x0, y0, x1, y1)).resize((COLS * 2, ROWS * 2), Image.BOX)


def logo(svg=MARK):
    """The logo text: one line per row, `$1` fur and `$2` eyes, no trailing spaces."""
    px = render(svg).load()
    lines = []
    for row in range(ROWS):
        cells = []
        for col in range(COLS):
            samples = [px[col * 2 + dx, row * 2 + dy] for dy in (0, 1) for dx in (0, 1)]
            if sum(is_eye(s) for s in samples) >= 2:
                cells.append(("2", "█"))
            else:
                key = tuple(1 if s[3] / 255 >= THRESHOLD else 0 for s in samples)
                cells.append(("1", QUADRANTS[key]))
        text, colour = "", None
        while cells and cells[-1][1] == " ":
            cells.pop()
        for c, ch in cells:
            if c != colour:
                text += "$" + c
                colour = c
            text += ch
        lines.append(text)
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--svg", default=MARK, help="the mark to draw (default: %(default)s)")
    ap.add_argument("--out", help="write here (default: stdout; '-' for %s)" % os.path.relpath(OUT, REPO))
    args = ap.parse_args()
    text = logo(args.svg)
    if not args.out:
        sys.stdout.write(text)
        return
    out = OUT if args.out == "-" else args.out
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote", os.path.relpath(out, REPO))


if __name__ == "__main__":
    main()
