#!/usr/bin/env python3
"""Wallpaper picker backend: list wallpapers with thumbnails, choose a folder, apply one.

    wallpapers.py list              JSON {items: [...], current, folder, theme}
    wallpapers.py folder <path|url> remember an extra folder of your own pictures
    wallpapers.py apply <key>       apply a wallpaper through `arctic-wallpaper <key>`
    wallpapers.py import <path|url>…  copy pictures into your folder (checked with Pillow)
    wallpapers.py delete <path>     delete one of your pictures (not the one in use)
    wallpapers.py rename <path> <name>  rename one of your pictures (same folder and type)

Items are the packaged Arctic photo collection followed by the pictures in your folder
(default ~/Pictures/Wallpapers). Older installations without a collection keep the legacy
illustrations, and saved choices continue to take precedence over fresh defaults.

Thumbnails (480×300 JPEG, Pillow; SVGs rendered with rsvg-convert) are cached in
~/.cache/arctic/thumbs. Settings live in ~/.config/arctic/wallpapers.json ({"folder": …}).
The applied choice is kept by arctic-wallpaper in ~/.config/arctic/wallpaper.

Import, delete and rename only touch files inside your folder (pictures downloaded from
Wallhaven are in its wallhaven/ subfolder, see wallhaven.py): a picture from elsewhere (a
drag from Thunar, the file chooser) is copied in, never moved, after Pillow has read it all.
"""
import contextlib
import hashlib
import json
import os
import re
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
SYSTEM = [DATA, Path(os.environ.get('ARCTIC_BACKGROUNDS_DIR') or '/usr/share/backgrounds/arctic')]
SETTINGS = CONFIG / 'wallpapers.json'
DESIGN = [('snowfield', 'Snowfield'), ('aurora', 'Aurora'), ('fox', 'Fox')]
IMAGES = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif', '.svg'}
THUMB = (480, 300)
# Pillow formats a copied picture may have, and the file suffix it gets.
FORMATS = {'JPEG': '.jpg', 'PNG': '.png', 'WEBP': '.webp', 'BMP': '.bmp', 'GIF': '.gif'}
MAX_BYTES = 200 * 1024 * 1024
MAX_PIXELS = 400_000_000


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
    """Which drawing of the Arctic wallpapers fits the active theme: winter or polar-night.
    A theme made from a picture (or your own) uses its base, else its light / dark mode."""
    env = {}
    try:
        for line in (CONFIG / 'current' / 'theme.env').read_text().splitlines():
            key, sep, value = line.partition('=')
            if sep and key.startswith('ARCTIC_'):
                env[key] = value.strip().strip('"\'')
    except OSError:
        pass
    for name in (env.get('ARCTIC_THEME_BASE'), env.get('ARCTIC_THEME')):
        if name in ('winter', 'polar-night'):
            return name
    if env.get('ARCTIC_THEME_MODE') in ('dark', 'light'):
        return 'winter' if env['ARCTIC_THEME_MODE'] == 'light' else 'polar-night'
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
        drawn_path = Path((CACHE.parent / 'wallpaper-current').read_text().strip())
        drawn = drawn_path.stem
    except OSError:
        drawn_path = None
        drawn = ''
    for name, _label in DESIGN:
        if drawn.startswith(name + '-'):
            return name
    photos, default = photo_collection()
    if photos:
        for item in photos:
            if drawn_path and drawn_path.resolve() == item['path'].resolve():
                return str(item['path'])
        return str(default)
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
    thumb = CACHE / (cache_key(path) + '.jpg')
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


def cache_key(path):
    stat = path.stat()
    return hashlib.sha256('{}\0{}\0{}'.format(path, stat.st_mtime_ns, stat.st_size).encode()).hexdigest()[:32]


def check_image(path):
    """Pillow must recognise and fully decode the picture; returns its format (JPEG, PNG, …).
    Raises ValueError with a sentence otherwise."""
    from PIL import Image
    try:
        size = path.stat().st_size
    except OSError:
        raise ValueError('That file can’t be read.') from None
    if size > MAX_BYTES:
        raise ValueError('That picture is larger than 200 MB.')
    try:
        with Image.open(path) as img:
            fmt = img.format
            if img.width * img.height > MAX_PIXELS:
                raise ValueError('That picture has too many pixels to use as a wallpaper.')
            img.verify()
        with Image.open(path) as img:      # verify() leaves the image unusable: decode it again
            img.seek(0)
            img.load()
    except ValueError:
        raise
    except Exception:
        raise ValueError('{} isn’t a picture Arctic can use (JPEG, PNG, WebP, BMP or GIF).'.format(path.name)) from None
    if fmt not in FORMATS:
        raise ValueError('{} is a {} picture; use JPEG, PNG, WebP, BMP or GIF.'.format(path.name, fmt or 'unknown'))
    return fmt


def user_folder():
    return Path(settings().get('folder') or default_folder()).expanduser()


def own_file(raw):
    """A picture inside your folder (resolved), else ValueError: design wallpapers and files
    elsewhere are never deleted or renamed."""
    path = Path(unquote(urlparse(raw).path) if raw.startswith('file:') else raw).expanduser()
    folder = user_folder().resolve()
    try:
        real = path.resolve()
        real.relative_to(folder)
    except (OSError, ValueError):
        raise ValueError('Only pictures in your wallpaper folder can be changed here.') from None
    if not real.is_file() or real.suffix.lower() not in IMAGES:
        raise ValueError('That picture is missing. Refresh the list and try again.')
    return real


def forget_thumb(path):
    try:
        (CACHE / (cache_key(path) + '.jpg')).unlink()
    except OSError:
        pass


def free_name(folder, stem, suffix):
    stem = re.sub(r'[\x00-\x1f/\\]', '', stem).strip().strip('.') or 'wallpaper'
    stem = stem[:120]
    candidate = folder / (stem + suffix)
    n = 2
    while candidate.exists():
        candidate = folder / '{} ({}){}'.format(stem, n, suffix)
        n += 1
    return candidate


def import_pictures(sources):
    """Copy pictures (paths or file:// URLs, e.g. dropped from Thunar) into your folder."""
    folder = user_folder()
    folder.mkdir(parents=True, exist_ok=True)
    added, errors = [], []
    for raw in sources:
        raw = raw.strip()
        if not raw:
            continue
        src = Path(unquote(urlparse(raw).path) if raw.startswith('file:') else raw).expanduser()
        try:
            if not src.is_file():
                raise ValueError('{} isn’t a file.'.format(src.name or raw))
            fmt = check_image(src)
            real = src.resolve()
            if real.parent == folder.resolve():
                added.append(str(real))       # already there
                continue
            dest = free_name(folder, src.stem, FORMATS[fmt])
            fd, temp = tempfile.mkstemp(prefix='.import.', dir=str(folder))
            os.close(fd)
            try:
                shutil.copyfile(src, temp)
                os.chmod(temp, 0o644)
                os.replace(temp, dest)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(temp)
                raise
            with contextlib.suppress(Exception):
                thumbnail(dest)
            added.append(str(dest))
        except (ValueError, OSError) as error:
            errors.append(str(error) if isinstance(error, ValueError) else '{}: {}'.format(src.name, error.strerror or error))
    return dict(ok=bool(added) or not errors, added=added, errors=errors, folder=str(folder),
                error=' '.join(errors) if errors and not added else '')


def is_current(path):
    chosen = current()
    try:
        return chosen.startswith(('/', '~')) and Path(chosen).expanduser().resolve() == path
    except OSError:
        return False


def delete_picture(raw):
    path = own_file(raw)
    if is_current(path):
        raise ValueError('That picture is your wallpaper now. Choose another one first.')
    forget_thumb(path)
    path.unlink()
    return dict(ok=True, deleted=str(path))


def rename_picture(raw, name):
    path = own_file(raw)
    stem = name.strip()
    if stem.lower().endswith(path.suffix.lower()):
        stem = stem[:-len(path.suffix)]
    if not stem or re.search(r'[\x00-\x1f/\\]', stem) or stem.startswith('.') or len(stem) > 120:
        raise ValueError('Use a name without slashes, up to 120 characters.')
    dest = path.with_name(stem + path.suffix)
    if dest == path:
        return dict(ok=True, path=str(path))
    if dest.exists():
        raise ValueError('There is already a picture called {}.'.format(dest.name))
    was_current = is_current(path)
    forget_thumb(path)
    path.rename(dest)
    if was_current:
        # arctic-wallpaper keeps the choice as a path: point it at the new name.
        (CONFIG / 'wallpaper').write_text(str(dest) + '\n')
    with contextlib.suppress(Exception):
        thumbnail(dest)
    return dict(ok=True, path=str(dest), current=was_current)


def apply(key):
    if key not in {n for n, _ in DESIGN} and not Path(key).is_file():
        raise ValueError('That picture is missing. Refresh the list and try again.')
    result = subprocess.run(['arctic-wallpaper', key], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-300:] or 'The wallpaper could not be set.')
    return key


def design_file(stem):
    """The design wallpaper <stem> (e.g. aurora-winter): a rendered PNG if shipped, else the SVG."""
    for folder in SYSTEM:
        for suffix in ('.png', '.svg'):
            candidate = folder / (stem + suffix)
            if candidate.is_file():
                return candidate
    return None


def photo_collection():
    """Only manifest-listed, local JPEG exports; aliases and legacy art aren't gallery entries."""
    for folder in SYSTEM:
        try:
            collection = json.loads((folder / 'collection.json').read_text())
            if collection.get('schema') != 1:
                continue
            photos = []
            for item in collection['wallpapers']:
                slug = item['slug']
                if not re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', slug) or item['file'] != slug + '.jpg':
                    continue
                path = folder / item['file']
                if path.is_symlink() or not path.is_file():
                    continue
                photos.append(dict(path=path, name=item['title'], photographer=item['photographer'],
                                   collectionTheme=item['theme']))
            default = folder / (collection['default'] + '.jpg')
            if photos and any(item['path'] == default for item in photos):
                return photos, default
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return [], None


def library():
    active = theme()
    items = []
    photos, _default = photo_collection()
    candidates = photos or [dict(path=design_file('{}-{}'.format(name, active)), key=name, name=label)
                            for name, label in DESIGN]
    for item in candidates:
        path = item['path']
        if path is None:
            continue
        try:
            thumb = thumbnail(path)
        except (OSError, ValueError):
            thumb = ''
        items.append(dict(item, key=item.get('key', str(path)), path=str(path), thumb=thumb, arctic=True))
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
                              path=str(path), thumb=thumb, arctic=False,
                              wallhaven=path.parent.name == 'wallhaven' and path.stem.startswith('wallhaven-')))
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
        print(json.dumps(dict(ok=True, current=apply(sys.argv[2]))))
    elif action == 'import':
        result = import_pictures(sys.argv[2:])
        print(json.dumps(result))
        if not result['ok']:
            sys.exit(1)
    elif action == 'delete':
        print(json.dumps(delete_picture(sys.argv[2])))
    elif action == 'rename':
        print(json.dumps(rename_picture(sys.argv[2], sys.argv[3])))
    else:
        raise ValueError('usage: wallpapers.py list | folder <path> | apply <key> | import <path>… | delete <path> | rename <path> <name>')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:  # report every failure to the picker as a sentence
        print(json.dumps(dict(ok=False, error=str(error) or error.__class__.__name__)))
        sys.exit(1)
