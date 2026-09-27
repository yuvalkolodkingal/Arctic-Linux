#!/usr/bin/env python3
"""GRUB theme assets for Arctic Linux (called by build-grub-theme.sh).

    grub_assets.py background WALLPAPER_PNG OUT_PNG       70 % nose overlay baked in
    grub_assets.py slices OUT_DIR                          select_*, item_*, terminal_box_*
    grub_assets.py pf2name PF2 NEW_NAME                    rename a PF2 font in place

Selected item (design BootMenu): amber #f6bd55, radius 10, 40 px tall, text
inset 16 px. GRUB draws the selection box as item_height + top pad + bottom
pad, where the pads are the heights of the n/s slices, and starts the text
after the w slice. So the slices are 16 px wide (text inset) and 10 px tall
(corner radius), and theme.txt uses item_height = 20 so the box is 40 px.
The item_* slices are transparent copies with the same pads, so selected and
unselected labels sit on the same baseline.
"""
import os
import subprocess
import sys
import tempfile

from PIL import Image

NOSE = (0x0C, 0x10, 0x15)
ACCENT = "#f6bd55"          # accent (polar night)
SURFACE_RAISED = "#232b36"
LINE = "#2f3945"


def background(src, dst):
    im = Image.open(src).convert("RGB")
    overlay = Image.new("RGB", im.size, NOSE)
    Image.blend(im, overlay, 0.70).save(dst, optimize=True)


def render(svg, w, h):
    with tempfile.TemporaryDirectory() as d:
        s, p = os.path.join(d, "s.svg"), os.path.join(d, "p.png")
        with open(s, "w") as f:
            f.write(svg)
        subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), "-o", p, s], check=True)
        return Image.open(p).convert("RGBA")


def nine(img, left, top, prefix, out):
    """Cut img into prefix_{nw,n,ne,w,c,e,sw,s,se}.png around a 1 px stretch row/column."""
    w, h = img.size
    xs = [(0, left), (left, left + 1), (left + 1, w)]
    ys = [(0, top), (top, top + 1), (top + 1, h)]
    names = [["nw", "n", "ne"], ["w", "c", "e"], ["sw", "s", "se"]]
    for r, (y0, y1) in enumerate(ys):
        for c, (x0, x1) in enumerate(xs):
            img.crop((x0, y0, x1, y1)).save(os.path.join(out, f"{prefix}_{names[r][c]}.png"), optimize=True)


def slices(out):
    os.makedirs(out, exist_ok=True)
    # selected item: 16 px inset, radius 10 -> 33 x 21 source
    w, h = 33, 21
    sel = render(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
                 f'<rect width="{w}" height="{h}" rx="10" fill="{ACCENT}"/></svg>', w, h)
    nine(sel, 16, 10, "select", out)
    nine(Image.new("RGBA", (w, h), (0, 0, 0, 0)), 16, 10, "item", out)
    # terminal box (command line / entry editor): surface-raised, 1 px line, radius 14
    w = h = 29
    term = render(f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}">'
                  f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="13.5" fill="{SURFACE_RAISED}" '
                  f'stroke="{LINE}"/></svg>', w, h)
    nine(term, 14, 14, "terminal_box", out)


def pf2name(path, new):
    """Rename a PF2 font without moving any data (the CHIX index holds absolute
    offsets), by writing the new name into the NAME section padded with NULs.
    grub2-mkfont always appends the style ("Figtree Medium Regular 17"), and
    GRUB matches theme font names exactly."""
    data = bytearray(open(path, "rb").read())
    i = data.find(b"NAME")
    n = int.from_bytes(data[i + 4:i + 8], "big")
    enc = new.encode() + b"\0"
    if len(enc) > n:
        sys.exit(f"{path}: new name longer than the NAME section ({len(enc)} > {n})")
    data[i + 8:i + 8 + n] = enc + b"\0" * (n - len(enc))
    open(path, "wb").write(data)


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "background" and len(sys.argv) == 4:
        background(sys.argv[2], sys.argv[3])
    elif cmd == "slices" and len(sys.argv) == 3:
        slices(sys.argv[2])
    elif cmd == "pf2name" and len(sys.argv) == 4:
        pf2name(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
