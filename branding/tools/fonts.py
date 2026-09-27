#!/usr/bin/env python3
"""Convert the design system's WOFF2 fonts to TTF with clean names.

The Figtree WOFF2 files in design/fonts are static instances whose name table
says "Figtree Light" / "Figtree Light Medium" (an artefact of the instancer).
Qt, fontconfig and grub2-mkfont all read those names, so we rewrite them to the
standard RIBBI + typographic family layout:

    Figtree-Regular.ttf   family "Figtree"            style "Regular"   400
    Figtree-Medium.ttf    family "Figtree Medium"     style "Regular"   500  (typographic: Figtree / Medium)
    Figtree-SemiBold.ttf  family "Figtree SemiBold"   style "Regular"   600  (typographic: Figtree / SemiBold)
    Figtree-Bold.ttf      family "Figtree"            style "Bold"      700

JetBrains Mono already has correct names; it is only decompressed.

Usage: fonts.py DESIGN_FONTS_DIR OUT_DIR
"""
import os
import sys

from fontTools.ttLib import TTFont

FIGTREE = [
    # src, out, weight, style (typographic subfamily), ribbi family, ribbi style
    ("Figtree-400.woff2", "Figtree-Regular.ttf", 400, "Regular", "Figtree", "Regular"),
    ("Figtree-500.woff2", "Figtree-Medium.ttf", 500, "Medium", "Figtree Medium", "Regular"),
    ("Figtree-600.woff2", "Figtree-SemiBold.ttf", 600, "SemiBold", "Figtree SemiBold", "Regular"),
    ("Figtree-700.woff2", "Figtree-Bold.ttf", 700, "Bold", "Figtree", "Bold"),
]
JETBRAINS = [
    ("JetBrainsMono-400.woff2", "JetBrainsMono-Regular.ttf"),
    ("JetBrainsMono-700.woff2", "JetBrainsMono-Bold.ttf"),
    ("JetBrainsMono-400-italic.woff2", "JetBrainsMono-Italic.ttf"),
]


def set_names(font, family, style, typo_style, weight):
    name = font["name"]
    version = name.getDebugName(5) or "Version 2.002"
    copyright_ = name.getDebugName(0) or ""
    license_url = name.getDebugName(14) or "https://openfontlicense.org"
    full = "Figtree" if typo_style == "Regular" else f"Figtree {typo_style}"
    ps = "Figtree-" + typo_style
    # Drop every record, then write a consistent Windows-platform set.
    name.names = []
    records = {
        0: copyright_,
        1: family,
        2: style,
        3: f"{version.replace('Version ', '')};ARCTIC;{ps}",
        4: full,
        5: version,
        6: ps,
        13: "This Font Software is licensed under the SIL Open Font License, Version 1.1.",
        14: license_url,
    }
    if typo_style not in ("Regular", "Bold"):
        records[16] = "Figtree"
        records[17] = typo_style
    for nid, value in records.items():
        name.setName(value, nid, 3, 1, 0x409)

    os2 = font["OS/2"]
    os2.usWeightClass = weight
    use_typo = os2.fsSelection & (1 << 7)
    if style == "Bold":
        os2.fsSelection = (1 << 5) | use_typo
        font["head"].macStyle = 1
    else:
        os2.fsSelection = (1 << 6) | use_typo
        font["head"].macStyle = 0
    # The STAT table still names the instance "Light"; it is optional for
    # static fonts, so drop it rather than carry wrong names.
    if "STAT" in font:
        del font["STAT"]
    font["post"].formatType = 2.0


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    for src, out, weight, typo_style, family, style in FIGTREE:
        font = TTFont(os.path.join(src_dir, src), recalcTimestamp=False)  # reproducible
        font.flavor = None
        set_names(font, family, style, typo_style, weight)
        font.save(os.path.join(out_dir, out))
        print(f"{out}: {family} / {style} ({weight})")
    for src, out in JETBRAINS:
        font = TTFont(os.path.join(src_dir, src), recalcTimestamp=False)  # reproducible
        font.flavor = None
        font.save(os.path.join(out_dir, out))
        print(f"{out}: {font['name'].getDebugName(1)} / {font['name'].getDebugName(2)}")


if __name__ == "__main__":
    main()
