#!/usr/bin/env python3
"""Emoji for the shell's picker (Super + Ctrl + E) and arctic-emoji's fuzzel fallback, from
unicode-emoji's emoji-test.txt (standard library only).

    emoji-index.py             {"ok": true, "unicode": "18.0", "recent": ["👍", …],
                                "emoji": [{"e": "👍", "name": "thumbs up", "group": "People & Body",
                                           "keys": "hand prop", "tones": ["👍🏻", …]}, …]}
    emoji-index.py --lines     "👍<TAB>thumbs up  hand prop" lines for fuzzel
    emoji-index.py --used 👍   put it first in the recent emoji (~/.local/state/arctic/emoji.json)

Only fully-qualified emoji are listed; skin-tone variants are folded into their base emoji
(`tones`). CLDR keywords are added when cldr-emoji-annotation is installed. The list is cached
in ~/.cache/arctic/emoji.json and rebuilt when its sources change.
"""
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HOME = Path.home()
SOURCE = Path(os.environ.get('ARCTIC_EMOJI_TEST') or '/usr/share/unicode/emoji/emoji-test.txt')
CLDR = Path(os.environ.get('ARCTIC_EMOJI_CLDR') or '/usr/share/unicode/cldr/common/annotations')
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or HOME / '.cache') / 'arctic' / 'emoji.json'
STATE = Path(os.environ.get('XDG_STATE_HOME') or HOME / '.local/state') / 'arctic' / 'emoji.json'
RECENT = 24
# Fedora 44's Noto Color Emoji (20250623) draws Emoji 16.0; newer ones would show as boxes.
NEWEST = float(os.environ.get('ARCTIC_EMOJI_NEWEST') or 16.0)
TONES = re.compile('[\U0001F3FB-\U0001F3FF]')
LINE = re.compile(r'^[0-9A-F ]+;\s*fully-qualified\s*#\s*(\S+)\s+E(\d+\.\d+)\s+(.+)$')
VERSION = 3     # of the cache's layout


def languages():
    lang = (os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG') or '').split('.')[0]
    return ['en'] + ([lang.split('_')[0]] if lang and not lang.startswith(('en', 'C', 'POSIX')) else [])


def parse(text):
    """emoji-test.txt → (emoji list, newest Unicode emoji version)."""
    out, bases, group, subgroup, newest = [], {}, '', '', 0.0
    for line in text.splitlines():
        if line.startswith('# group:'):
            group = line.split(':', 1)[1].strip()
            continue
        if line.startswith('# subgroup:'):
            subgroup = line.split(':', 1)[1].strip()
            continue
        match = LINE.match(line)
        if not match or group == 'Component':
            continue
        char, version, name = match.group(1), float(match.group(2)), match.group(3).strip()
        if version > NEWEST:
            continue
        newest = max(newest, version)
        if TONES.search(char):
            base = bases.get(name.split(':')[0].strip())
            if base is not None and ',' not in name:     # one tone for the whole emoji
                base['tones'].append(char)
            continue
        entry = dict(e=char, name=name, group=group, keys=subgroup.replace('-', ' '), tones=[])
        bases[name] = entry
        out.append(entry)
    return out, '{:.1f}'.format(newest) if newest else ''


def add_keywords(emoji, langs):
    """CLDR annotations (and the derived ones, for flags and tones) as extra search words."""
    by_char = {e['e'].replace('️', ''): e for e in emoji}
    for lang in langs:
        for folder in (CLDR, CLDR.parent / 'annotationsDerived'):
            try:
                root = ET.parse(folder / (lang + '.xml')).getroot()
            except (OSError, ET.ParseError):
                continue
            for node in root.iter('annotation'):
                entry = by_char.get((node.get('cp') or '').replace('️', ''))
                if entry is not None and node.text and node.get('type') != 'tts':
                    words = ' '.join(w.strip() for w in node.text.split('|') if w.strip())
                    entry['keys'] = (entry['keys'] + ' ' + words).strip()


def sources_mtime():
    times = [SOURCE.stat().st_mtime]
    for folder in (CLDR, CLDR.parent / 'annotationsDerived'):
        for lang in languages():
            try:
                times.append((folder / (lang + '.xml')).stat().st_mtime)
            except OSError:
                pass
    return max(times)


def index():
    langs = languages()
    try:
        cached = json.loads(CACHE.read_text(encoding='utf-8'))
        if cached.get('version') == VERSION and cached.get('langs') == langs and \
                cached.get('mtime', 0) >= sources_mtime():
            return cached
    except (OSError, ValueError):
        pass
    emoji, unicode_version = parse(SOURCE.read_text(encoding='utf-8'))
    add_keywords(emoji, langs)
    data = dict(version=VERSION, langs=langs, mtime=sources_mtime(), unicode=unicode_version, emoji=emoji)
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        tmp = CACHE.with_suffix('.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, CACHE)
    except OSError:
        pass     # works uncached
    return data


def recent():
    try:
        value = json.loads(STATE.read_text(encoding='utf-8')).get('recent', [])
        return [e for e in value if isinstance(e, str)][:RECENT]
    except (OSError, ValueError, AttributeError):
        return []


def used(char):
    if not char or len(char) > 16:
        return
    state = {}
    try:
        state = json.loads(STATE.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        pass
    state = state if isinstance(state, dict) else {}
    state['recent'] = ([char] + [e for e in recent() if e != char])[:RECENT]
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(state, ensure_ascii=False), encoding='utf-8')
    os.replace(tmp, STATE)


def main(argv):
    if argv[:1] == ['--used']:
        used(argv[1] if len(argv) > 1 else '')
        return 0
    try:
        data = index()
    except OSError:
        print(json.dumps(dict(ok=False, error='The emoji list (unicode-emoji) isn’t installed.')))
        return 1
    if argv[:1] == ['--lines']:
        for e in data['emoji']:
            sys.stdout.write('{}\t{}  {}\n'.format(e['e'], e['name'], e['keys']))
        return 0
    print(json.dumps(dict(ok=True, unicode=data['unicode'], recent=recent(), emoji=data['emoji']), ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
