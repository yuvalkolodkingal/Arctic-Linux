#!/usr/bin/env python3
"""Import only verified photo masters from a pinned Wallpapers checkout.

The source checkout is read only. Originals, edits, previews, duplicate resolutions,
and Hyprland configurations are not part of the Arctic package.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
DEST = ROOT / 'design/backgrounds'
AUTHOR = 'Yuval Kolodkin-Gal'
REPOSITORY = 'https://github.com/yuvalkolodkingal/Wallpapers'


def verify_metadata(image, path):
    # A strict allowlist also rejects Exif/GPS IFD pointers, so nested dates and
    # camera identifiers cannot pass hidden beneath the top-level dictionary.
    exif = image.getexif()
    assert set(exif).issubset({315, 33432, 305}), 'Unapproved EXIF metadata: ' + str(path)
    assert not exif.get(315) or exif[315] == AUTHOR, path
    assert not exif.get(33432) or AUTHOR in str(exif[33432]), path
    assert not {'xmp', 'XML:com.adobe.xmp', 'comment'}.intersection(image.info), path


def verify(folder):
    collection = json.loads((folder / 'collection.json').read_text())
    assert collection['author'] == AUTHOR
    assert re.fullmatch('[0-9a-f]{40}', collection['revision'])
    assert collection['repository'] == REPOSITORY
    slugs = set()
    for item in collection['wallpapers']:
        slug = item['slug']
        assert re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', slug) and slug not in slugs
        slugs.add(slug)
        assert item['file'] == slug + '.jpg' and item['photographer'] == AUTHOR
        path = folder / item['file']
        assert not path.is_symlink()
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], path
        with Image.open(path) as image:
            assert image.format == 'JPEG' and image.size == (item['width'], item['height'])
            assert image.width * 9 == image.height * 16, path
            verify_metadata(image, path)
            image.load()
    assert collection['default'] in slugs
    assert {p.name for p in folder.glob('*.jpg')} == {s + '.jpg' for s in slugs}
    return collection


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--revision')
    parser.add_argument('--default', default='city-afterglow')
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--png', type=Path, help='Build the compatibility default PNG after verification')
    args = parser.parse_args()
    if args.source:
        assert args.revision and re.fullmatch('[0-9a-f]{40}', args.revision)
        source = args.source.resolve()
        head = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
        assert head == args.revision, 'Source checkout does not match the requested pin'
        assert not subprocess.check_output(['git', '-C', str(source), 'status', '--porcelain'], text=True)
        upstream = json.loads((source / 'metadata/collection.json').read_text())
        assert upstream['author'] == AUTHOR
        items = []
        for item in upstream['wallpapers']:
            assert re.fullmatch('[a-z0-9]+(?:-[a-z0-9]+)*', item['slug'])
            assert item['master'] == 'wallpapers/master/' + item['slug'] + '.jpg'
            photo = source / item['master']
            assert photo.resolve().is_relative_to(source) and not photo.is_symlink()
            entry = {key: item[key] for key in ('slug', 'title', 'theme', 'description',
                                                'width', 'height', 'sha256', 'photographer')}
            entry['file'] = item['slug'] + '.jpg'
            items.append(entry)
        collection = dict(schema=1, repository=REPOSITORY, revision=head, author=AUTHOR,
                          default=args.default, wallpapers=items)
        # Validate the complete import in a temporary directory before replacing exports.
        import tempfile
        with tempfile.TemporaryDirectory(dir=DEST.parent) as work:
            staged = Path(work)
            for item in upstream['wallpapers']:
                shutil.copyfile(source / item['master'], staged / (item['slug'] + '.jpg'))
            (staged / 'collection.json').write_text(json.dumps(collection, indent=2) + '\n')
            shutil.copyfile(source / 'COPYRIGHT', staged / 'COPYRIGHT')
            verify(staged)
            DEST.mkdir(exist_ok=True)
            for previous in DEST.glob('*.jpg'):
                previous.unlink()
            for path in staged.iterdir():
                shutil.copyfile(path, DEST / path.name)
    collection = verify(DEST)
    if args.png:
        args.png.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(DEST / (collection['default'] + '.jpg')) as image:
            image.convert('RGB').save(args.png, format='PNG')
    print('{} verified photo masters; source {}; {} bytes'.format(
        len(collection['wallpapers']), collection['revision'],
        sum((DEST / item['file']).stat().st_size for item in collection['wallpapers'])))


if __name__ == '__main__':
    main()
