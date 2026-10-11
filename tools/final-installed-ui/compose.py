#!/usr/bin/env python3
"""Compose only pinned image-source desktop functions and this owned UI checker."""
import argparse
import hashlib
import json
from pathlib import Path


def compose(source, checker, context, output):
    native = source / 'tools/native-functional/native_smoke.py'
    body = native.read_text()
    actual = hashlib.sha256(body.encode()).hexdigest()
    if context.get('native_sha256') != actual:
        raise RuntimeError('Image-native helper bytes differ')
    ui = checker.read_text()
    if context.get('ui_sha256') != hashlib.sha256(ui.encode()).hexdigest():
        raise RuntimeError('UI helper bytes differ')
    with output.open('x') as stream:
        stream.write('#!/usr/bin/env python3\n'
                      'native={"__name__":"owned_final_ui_native","__file__":__file__}\n'
                      + f'exec(compile({body!r},__file__,"exec"),native)\n'
                      + 'ui={"__name__":"owned_final_ui","__file__":__file__}\n'
                      + f'exec(compile({ui!r},__file__,"exec"),ui)\n'
                      + f'context={context!r}\n'
                      + 'raise SystemExit(ui["main"](native,context))\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    compose(args.source, Path(__file__).with_name('guest.py'), json.loads(args.context.read_text()), args.out)


if __name__ == '__main__':
    main()
