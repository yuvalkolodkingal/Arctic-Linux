"""arctic-themegen — the Arctic Linux theme engine CLI.

  arctic-themegen render --palette FILE --out DIR [--templates DIR]... [--force]
        render every template and generated file for a palette into DIR
  arctic-themegen palette --from-wallpaper IMG [--mode auto|dark|light] [--base NAME|FILE]
                          [--name NAME] [--label TEXT]
        print a palette derived from a picture (JSON)
  arctic-themegen builtin winter|polar-night
        print a static palette (JSON)
  arctic-themegen check --palette FILE [--json]
        validate a palette and report the contrast guarantees (exit 1 if one fails)

--palette takes a JSON file, '-' for stdin, or a built-in name. Exit status: 0 ok, 1 a
contrast check failed, 2 bad input (message on stderr).
"""
import argparse
import json
import sys

from . import __version__, derive, palette as pal, render as rnd
from .palette import ThemegenError


def _parser():
    p = argparse.ArgumentParser(prog="arctic-themegen", description="Arctic Linux theme engine")
    p.add_argument("--version", action="version", version="arctic-themegen " + __version__)
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    r = sub.add_parser("render", help="render a palette into a theme directory")
    r.add_argument("--palette", required=True, help="palette JSON file, '-' (stdin) or a built-in name")
    r.add_argument("--out", required=True, help="theme directory to write")
    r.add_argument("--templates", action="append", default=[], metavar="DIR",
                   help="extra template directory (may repeat; later ones override)")
    r.add_argument("--force", action="store_true", help="render into a directory that isn't a theme")
    r.add_argument("--quiet", "-q", action="store_true")

    w = sub.add_parser("palette", help="derive a palette from a wallpaper")
    w.add_argument("--from-wallpaper", required=True, metavar="IMG", dest="image")
    w.add_argument("--mode", default="auto", choices=("auto", "dark", "light"))
    w.add_argument("--base", default=None, help="static theme to build on (winter, polar-night or a palette file)")
    w.add_argument("--name", default="wallpaper")
    w.add_argument("--label", default="Wallpaper")

    b = sub.add_parser("builtin", help="print a static palette")
    b.add_argument("name", choices=sorted(pal.BUILTINS))

    c = sub.add_parser("check", help="validate a palette and check its contrast")
    c.add_argument("--palette", required=True)
    c.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = _parser().parse_args(argv)
    try:
        if args.command == "render":
            p = pal.load(args.palette)
            written = rnd.render(p, args.out, args.templates, force=args.force)
            if not args.quiet:
                print("{}: {} file(s) updated".format(args.out, len(written)))
        elif args.command == "palette":
            if args.name and not pal.NAME_RE.match(args.name):
                raise ThemegenError("--name must match [a-z0-9][a-z0-9._-]*")
            p = derive.from_wallpaper(args.image, args.mode, args.base, args.name, args.label)
            sys.stdout.write(pal.dumps(p))
        elif args.command == "builtin":
            sys.stdout.write(pal.dumps(pal.builtin(args.name)))
        elif args.command == "check":
            p = pal.load(args.palette)
            failures = derive.check(p)
            if args.json:
                print(json.dumps({"ok": not failures, "contrast": derive.contrast_report(p),
                                  "failures": [{"foreground": f, "background": b, "ratio": r, "required": q}
                                               for f, b, r, q in failures]}, indent=2))
            else:
                for pair, ratio in derive.contrast_report(p).items():
                    print("{:40s} {:5.2f}".format(pair, ratio))
                for f, b, r, q in failures:
                    print("FAIL {} on {}: {} < {}".format(f, b, r, q), file=sys.stderr)
            return 1 if failures else 0
        else:
            _parser().print_help()
            return 2
    except ThemegenError as e:
        print("arctic-themegen: {}".format(e), file=sys.stderr)
        return 2
    except BrokenPipeError:
        return 0
    return 0
