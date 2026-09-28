#!/usr/bin/env python3
"""Clipboard history for the shell's panel (Super + V), from cliphist (standard library, and
Pillow for image thumbnails).

    clipboard.py list        {"ok": true, "items": [{"id": "124", "kind": "text", "preview": "…"},
                              {"id": "123", "kind": "image", "format": "png", "width": 800,
                               "height": 600, "size": "12 KiB", "thumb": "…/123.png" or ""}]}
    clipboard.py thumb ID    {"ok": true, "thumb": "…"}: a small copy of an image entry
    clipboard.py copy ID     put the entry back on the clipboard
    clipboard.py paste ID    the same, then paste it into the window that has the focus (wtype)
    clipboard.py delete ID   remove the entry from the history
    clipboard.py wipe        clear the history

Every command prints one JSON line: {"ok": true, …} or {"ok": false, "error": "One sentence."}.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'arctic' / 'clip-thumbs'
LIMIT = 200         # the panel lists the newest entries only
THUMB = 160         # px, the longer side
IMAGE = re.compile(r'^\[\[ binary data (\d+(?:\.\d+)? \w+) (\w+) (\d+)x(\d+) \]\]$')
TERMINALS = {'kitty', 'foot', 'footclient', 'alacritty', 'org.wezfurlong.wezterm', 'com.mitchellh.ghostty',
             'org.kde.konsole', 'org.gnome.ptyxis', 'xterm'}
MAGIC = [(b'\x89PNG\r\n\x1a\n', 'image/png'), (b'\xff\xd8\xff', 'image/jpeg'), (b'GIF8', 'image/gif'),
         (b'RIFF', 'image/webp'), (b'BM', 'image/bmp')]


class Failure(Exception):
    pass


def cliphist(*args, data=None):
    try:
        result = subprocess.run(['cliphist'] + list(args), input=data, capture_output=True, timeout=10)
    except FileNotFoundError:
        raise Failure('Clipboard history (cliphist) isn’t installed.') from None
    except subprocess.TimeoutExpired:
        raise Failure('Clipboard history didn’t answer.') from None
    if result.returncode != 0:
        message = result.stderr.decode('utf-8', 'replace').strip()
        if 'not found' in message:
            raise Failure('That entry is no longer in the history.')
        raise Failure('Clipboard history failed: {}.'.format(message.rstrip('.') or 'no reason given'))
    return result.stdout


def entry_id(text):
    if not re.fullmatch(r'\d{1,20}', text or ''):
        raise Failure('usage: clipboard.py copy|thumb|delete ID')
    return text


def thumb_path(ident):
    return CACHE / (ident + '.png')


def parse(listing):
    """cliphist list → items. An image entry's preview is "[[ binary data 12 KiB png 800x600 ]]";
    anything else (older formats included) is shown as text."""
    items = []
    for line in listing.decode('utf-8', 'replace').splitlines():
        ident, sep, preview = line.partition('\t')
        if not sep or not ident.isdigit():
            continue
        image = IMAGE.match(preview.strip())
        if image:
            thumb = thumb_path(ident)
            items.append(dict(id=ident, kind='image', size=image.group(1), format=image.group(2),
                              width=int(image.group(3)), height=int(image.group(4)),
                              thumb=str(thumb) if thumb.exists() else ''))
        else:
            items.append(dict(id=ident, kind='text', preview=preview))
        if len(items) >= LIMIT:
            break
    return items


def cmd_list(_args):
    return dict(items=parse(cliphist('list')))


def cmd_thumb(args):
    ident = entry_id(args[0] if args else '')
    out = thumb_path(ident)
    if not out.exists():
        from PIL import Image
        import io
        try:
            with Image.open(io.BytesIO(cliphist('decode', ident))) as image:
                image.thumbnail((THUMB, THUMB))
                CACHE.mkdir(parents=True, exist_ok=True)
                image.save(out.with_suffix('.tmp'), 'PNG')
                os.replace(out.with_suffix('.tmp'), out)
        except OSError:
            raise Failure('That entry isn’t a picture Arctic can show.') from None
    return dict(thumb=str(out))


def cmd_copy(args):
    data = cliphist('decode', entry_id(args[0] if args else ''))
    mime = next((m for magic, m in MAGIC if data.startswith(magic)), '')
    # wl-copy stays behind to serve the clipboard: it must not hold our output open.
    subprocess.run(['wl-copy'] + (['--type', mime] if mime else []), input=data,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    return dict(kind='image' if mime else 'text')


def cmd_paste(args):
    """Copy, then press the paste keys in the window that has the focus once the panel is gone:
    Ctrl + V, or Ctrl + Shift + V in terminals (wtype types through its own keymap, so the
    layout-switch chords don't fire)."""
    result = cmd_copy(args)
    time.sleep(0.25)
    try:
        client = json.loads(subprocess.run(['mmsg', 'get', 'focusing-client'], capture_output=True,
                                           timeout=5).stdout or b'{}')
    except (OSError, ValueError, subprocess.TimeoutExpired):
        client = {}
    app = str(client.get('appid') or client.get('app_id') or '').lower() if isinstance(client, dict) else ''
    keys = ['-M', 'ctrl', '-M', 'shift', 'v', '-m', 'shift', '-m', 'ctrl'] if app in TERMINALS \
        else ['-M', 'ctrl', 'v', '-m', 'ctrl']
    try:
        subprocess.run(['wtype'] + keys, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        raise Failure('Copied: wtype isn’t installed, so press Ctrl + V to paste.') from None
    return result


def cmd_delete(args):
    ident = entry_id(args[0] if args else '')
    cliphist('delete', data=(ident + '\t\n').encode())
    thumb_path(ident).unlink(missing_ok=True)
    return {}


def cmd_wipe(_args):
    cliphist('wipe')
    for thumb in CACHE.glob('*.png'):
        thumb.unlink(missing_ok=True)
    return {}


COMMANDS = {'list': cmd_list, 'thumb': cmd_thumb, 'copy': cmd_copy, 'paste': cmd_paste, 'delete': cmd_delete,
            'wipe': cmd_wipe}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        sys.stderr.write(__doc__)
        return 2
    try:
        result = COMMANDS[argv[0]](argv[1:])
    except Failure as failure:
        print(json.dumps(dict(ok=False, error=str(failure)), ensure_ascii=False))
        return 1
    print(json.dumps(dict(ok=True, **result), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
