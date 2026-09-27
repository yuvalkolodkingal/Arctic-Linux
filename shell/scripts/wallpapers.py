#!/usr/bin/env python3
"""Wallpaper picker backend: list wallpapers with thumbnails, choose a folder, apply one.

    wallpapers.py list              JSON {items: [...], current, folder, theme}
    wallpapers.py folder <path|url> remember an extra folder of your own pictures
    wallpapers.py apply <key>       apply a wallpaper through `arctic-wallpaper <key>`

Items are the Arctic design wallpapers (snowfield, aurora, fox) — shown in the active theme's
variant and applied by name, so they follow Winter / Polar night switches — followed by the
pictures in your folder (default ~/Pictures/Wallpapers). Design wallpapers are looked up in
~/.local/share/arctic/wallpapers, then /usr/share/backgrounds/arctic.

Thumbnails (480×300 JPEG, Pillow; SVGs rendered with rsvg-convert) are cached in
~/.cache/arctic/thumbs. Settings live in ~/.config/arctic/wallpapers.json ({"folder": …}).
The applied choice is kept by arctic-wallpaper in ~/.config/arctic/wallpaper.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import unquote, urlparse

HOME = Path.home()
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME') or HOME / '.config') / 'arctic'
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or HOME / '.cache') / 'arctic' / 'thumbs'
DATA = Path(os.environ.get('XDG_DATA_HOME') or HOME / '.local/share') / 'arctic' / 'wallpapers'
SYSTEM = [DATA, Path('/usr/share/backgrounds/arctic')]
SETTINGS = CONFIG / 'wallpapers.json'
DESIGN = [('snowfield', 'Snowfield'), ('aurora', 'Aurora'), ('fox', 'Fox')]
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.svg'}
THUMB = (480, 300)


def settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save(data):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    temp = SETTINGS.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2) + '\n')
    temp.replace(SETTINGS)


def theme():
    try:
        name = (CONFIG / 'theme').read_text().strip()
    except OSError:
        name = ''
    return name if name in ('winter', 'polar-night') else 'polar-night'


def current():
    """The saved choice (a design name or a path); with none saved, the design wallpaper drawn
    now (arctic-wallpaper records it), else the theme's default."""
    try:
        saved = (CONFIG / 'wallpaper').read_text().strip()
    except OSError:
        saved = ''
    if saved:
        return saved
    try:
        drawn = Path((CACHE.parent / 'wallpaper-current').read_text().strip()).stem
    except OSError:
        drawn = ''
    for name, _label in DESIGN:
        if drawn.startswith(name + '-'):
            return name
    return 'snowfield' if theme() == 'winter' else 'aurora'


def default_folder():
    pictures = HOME / 'Pictures'
    try:
        out = subprocess.run(['xdg-user-dir', 'PICTURES'], capture_output=True, text=True, timeout=2,
                             env=dict(os.environ, HOME=str(HOME))).stdout.strip()
        if out and Path(out) != HOME:   # xdg-user-dir answers $HOME when the folder isn't set up
            pictures = Path(out)
    except (OSError, subprocess.SubprocessError):
        pass
    return pictures / 'Wallpapers'


def thumbnail(path):
    """Cached thumbnail for an image, as a file path, or '' when it can't be read."""
    from PIL import Image, ImageOps
    stat = path.stat()
    key = hashlib.sha256('{}\0{}\0{}'.format(path, stat.st_mtime_ns, stat.st_size).encode()).hexdigest()[:32]
    thumb = CACHE / (key + '.jpg')
    if thumb.exists():
        return str(thumb)
    CACHE.mkdir(parents=True, exist_ok=True)
    source = path
    temp = None
    if path.suffix.lower() == '.svg':
        if not shutil.which('rsvg-convert'):
            return ''
        temp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        temp.close()
        result = subprocess.run(['rsvg-convert', '-w', str(THUMB[0] * 2), '-o', temp.name, str(path)], capture_output=True)
        if result.returncode:
            os.unlink(temp.name)
            return ''
        source = Path(temp.name)
    try:
        with Image.open(source) as img:
            img.seek(0)
            ImageOps.fit(img.convert('RGB'), THUMB, Image.LANCZOS).save(thumb, quality=85)
    finally:
        if temp:
            os.unlink(temp.name)
    return str(thumb)


def design_file(stem):
    """The design wallpaper <stem> (e.g. aurora-winter): a rendered PNG if shipped, else the SVG."""
    for folder in SYSTEM:
        for suffix in ('.png', '.svg'):
            candidate = folder / (stem + suffix)
            if candidate.is_file():
                return candidate
    return None


def library():
    active = theme()
    items = []
    for name, label in DESIGN:
        path = design_file('{}-{}'.format(name, active))
        if path is None:
            continue
        try:
            thumb = thumbnail(path)
        except (OSError, ValueError):
            thumb = ''
        items.append(dict(key=name, name=label, path=str(path), thumb=thumb, arctic=True))
    data = settings()
    folder = Path(data.get('folder') or default_folder()).expanduser()
    system = {p.resolve() for p in SYSTEM if p.is_dir()}
    if folder.is_dir() and folder.resolve() not in system:
        for path in sorted(folder.rglob('*')):
            if path.suffix.lower() not in IMAGES or not path.is_file():
                continue
            try:
                thumb = thumbnail(path)
            except (OSError, ValueError, SyntaxError):
                continue
            if not thumb:
                continue
            items.append(dict(key=str(path), name=path.stem.replace('-', ' ').replace('_', ' '),
                              path=str(path), thumb=thumb, arctic=False))
    return dict(items=items, current=current(), folder=str(folder), folderExists=folder.is_dir(), theme=active)


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else 'list'
    if action == 'list':
        print(json.dumps(library()))
    elif action == 'folder':
        raw = sys.argv[2]
        path = Path(unquote(urlparse(raw).path) if raw.startswith('file:') else raw).expanduser().resolve()
        if not path.is_dir():
            raise ValueError('Choose an existing folder.')
        data = settings()
        data['folder'] = str(path)
        save(data)
        print(json.dumps(dict(ok=True, folder=str(path))))
    elif action == 'apply':
        key = sys.argv[2]
        if key not in {n for n, _ in DESIGN} and not Path(key).is_file():
            raise ValueError('That picture is missing. Refresh the list and try again.')
        result = subprocess.run(['arctic-wallpaper', key], capture_output=True, text=True, timeout=30)
        if result.returncode:
            raise RuntimeError((result.stderr or result.stdout).strip()[-300:] or 'The wallpaper could not be set.')
        print(json.dumps(dict(ok=True, current=key)))
    else:
        raise ValueError('usage: wallpapers.py list | folder <path> | apply <key>')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # report every failure to the picker as a sentence
        print(json.dumps(dict(ok=False, error=str(error) or error.__class__.__name__)))
        sys.exit(1)
