#!/usr/bin/env python3
"""Generate the Arctic Linux static desktop themes (Winter, Polar night) with the theme engine.

The engine is design/themegen (arctic-themegen on an installed system): it renders a palette
into a theme folder — per-app files from design/themegen/templates, plus theme.json, gtk.css,
theme.env, palette.json and the recoloured icons. This wrapper renders the two static palettes
(built from design/exports/arctic-tokens.json) into

  dotfiles/.config/arctic/themes/{winter,polar-night}/

and writes shell/assets/theme-defaults.js, the shell's built-in Polar night (used until a
theme.json can be read). The packages build the same themes with the engine at build time and
check that these committed copies are current (design/themegen/tests).

Run from anywhere:  python3 design/tools/gen-desktop-themes.py [--out DIR] [--no-shell-defaults]
Only the Python standard library is used.
"""
import argparse
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "design"))

from themegen import palette, render  # noqa: E402

OUT = os.path.join(ROOT, "dotfiles", ".config", "arctic", "themes")
SHELL_DEFAULTS = os.path.join(ROOT, "shell", "assets", "theme-defaults.js")
THEMES = ("winter", "polar-night")


def shell_defaults(p):
    return ".pragma library\n// {}\n// Polar night, the default theme, used until a theme.json can be read.\nvar THEME = {};\n".format(
        render.header(p), render.theme_json(p).rstrip())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=OUT, help="themes folder (default: dotfiles/.config/arctic/themes)")
    ap.add_argument("--no-shell-defaults", action="store_true", help="don't write shell/assets/theme-defaults.js")
    args = ap.parse_args()
    for name in THEMES:
        p = palette.builtin(name)
        d = os.path.join(args.out, name)
        render.render(p, d, force=True)
        print("wrote", os.path.relpath(d, ROOT))
        if name == "polar-night" and not args.no_shell_defaults:
            with open(SHELL_DEFAULTS, "w", encoding="utf-8") as f:
                f.write(shell_defaults(p))
            print("wrote", os.path.relpath(SHELL_DEFAULTS, ROOT))


if __name__ == "__main__":
    main()
