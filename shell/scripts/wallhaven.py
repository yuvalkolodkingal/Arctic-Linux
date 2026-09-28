#!/usr/bin/env python3
"""Wallhaven (https://wallhaven.cc) for the wallpaper pickers: search, preview, download, set.

    wallhaven.py search [--q TEXT] [--categories 111] [--purity 100] [--sorting toplist]
                        [--range 1M] [--page N] [--seed SEED] [--fit|--no-fit]
    wallhaven.py preview ID URL      the large thumbnail (th.wallhaven.cc/lg/…), cached
    wallhaven.py download ID URL     the picture (w.wallhaven.cc/full/…) → <folder>/wallhaven/
    wallhaven.py set ID URL          download, then apply it through wallpapers.py (arctic-wallpaper)
    wallhaven.py state               API key present (never the key), saved filters, your screens
    wallhaven.py key --set KEY|--clear
    wallhaven.py prefs [--categories …] [--purity …] [--sorting …] [--range …] [--fit on|off]

Every command prints one JSON object ({"ok": false, "error": …} on failure; "offline": true when
Wallhaven can't be reached, "wait": seconds when the rate limit is reached).

Search uses the public API (https://wallhaven.cc/help/api): SFW only unless you choose more;
NSFW needs your API key. "Fit my screens" asks for pictures at least as large as your largest
screen (atleast=WxH) in your screens' aspect ratios (ratios=16x9,…), from `wlr-randr --json`.
The API allows 45 requests a minute per client: every API call (search, key check) is counted
in ~/.cache/arctic/wallhaven/api-calls.json under a lock, shared by every process; at the
limit a call waits up to 8 s, else it fails with how long to wait. Pictures and thumbnails come
from Wallhaven's image servers, which the limit doesn't count. Searches are cached for 15
minutes, thumbnails in ~/.cache/arctic/wallhaven/.

Downloads go to <your wallpaper folder>/wallhaven/ (default ~/Pictures/Wallpapers/wallhaven),
which the pickers list with your other pictures (same list and thumbnail cache, wallpapers.py).
Settings: ~/.config/arctic/wallhaven.json, mode 600 (it may hold your API key).
"""
import argparse
import concurrent.futures
import contextlib
import fcntl
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wallpapers  # noqa: E402  (same folder: the wallpaper list, thumbnails, apply)

API = 'https://wallhaven.cc/api/v1'
USER_AGENT = 'ArcticLinux-Settings/0.2 (+https://github.com/yuvalkolodkingal/Arctic-Linux)'
SETTINGS = wallpapers.CONFIG / 'wallhaven.json'
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or wallpapers.HOME / '.cache') / 'arctic' / 'wallhaven'
RATE_LIMIT = 45          # API requests per minute (Wallhaven's limit)
RATE_WINDOW = 60.0
RATE_MAX_WAIT = 8.0      # wait this long for a free slot, else say how long to wait
SEARCH_TTL = 15 * 60
TIMEOUT = 20
THUMBS_KEPT = 600
PREVIEWS_KEPT = 40

SORTINGS = ('toplist', 'date_added', 'random', 'relevance', 'views', 'favorites', 'hot')
RANGES = ('1d', '3d', '1w', '1M', '3M', '6M', '1y')
DEFAULTS = dict(categories='111', purity='100', sorting='toplist', range='1M', fit=True)
# Wallhaven's aspect ratios (the `ratios` parameter) and their values.
RATIOS = {'16x9': 16 / 9, '16x10': 16 / 10, '21x9': 64 / 27, '32x9': 32 / 9, '48x9': 48 / 9,
          '9x16': 9 / 16, '10x16': 10 / 16, '9x18': 9 / 18, '1x1': 1.0, '3x2': 3 / 2, '4x3': 4 / 3, '5x4': 5 / 4}
RE_ID = re.compile(r'[a-z0-9]{4,12}')
RE_FULL = re.compile(r'https://w\.wallhaven\.cc/full/[a-z0-9]{2}/wallhaven-([a-z0-9]{4,12})\.(jpg|jpeg|png|webp)')
RE_THUMB = re.compile(r'https://th\.wallhaven\.cc/(small|lg|orig)/[a-z0-9]{2}/([a-z0-9]{4,12})\.(jpg|jpeg|png|webp)')
RE_KEY = re.compile(r'[A-Za-z0-9]{8,64}')


class Failure(Exception):
    """A sentence for the person; extra fields go into the JSON answer."""

    def __init__(self, message, **extra):
        super().__init__(message)
        self.extra = extra


OFFLINE = 'Wallhaven can’t be reached right now. Check your internet connection and try again.'


# ---- settings -----------------------------------------------------------------------------------

def load_settings():
    try:
        data = json.loads(SETTINGS.read_text())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_settings(data):
    """Atomically, mode 600 from the start (the file may hold the API key)."""
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.wallhaven.', dir=str(SETTINGS.parent))
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(json.dumps(data, indent=2) + '\n')
        os.replace(temp, SETTINGS)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    os.chmod(SETTINGS, 0o600)


def prefs(data=None):
    data = load_settings() if data is None else data
    out = dict(DEFAULTS)
    for key in DEFAULTS:
        if key in data:
            out[key] = data[key]
    out['categories'] = clean_bits(out['categories'], DEFAULTS['categories'])
    out['purity'] = clean_bits(out['purity'], DEFAULTS['purity'])
    if not data.get('api_key'):
        out['purity'] = out['purity'][:2] + '0'   # NSFW needs a key
        if out['purity'] == '000':
            out['purity'] = '100'
    if out['sorting'] not in SORTINGS:
        out['sorting'] = DEFAULTS['sorting']
    if out['range'] not in RANGES:
        out['range'] = DEFAULTS['range']
    out['fit'] = bool(out['fit'])
    return out


def clean_bits(value, default):
    value = str(value)
    return value if re.fullmatch(r'[01]{3}', value) and value != '000' else default


def api_key():
    key = load_settings().get('api_key') or ''
    return key if RE_KEY.fullmatch(key) else ''


# ---- screens --------------------------------------------------------------------------------------

def nearest_ratio(width, height):
    """Wallhaven's ratio name for a screen, or '' when none is within 3%."""
    if width <= 0 or height <= 0:
        return ''
    value = width / height
    name, best = min(RATIOS.items(), key=lambda kv: abs(kv[1] - value) / kv[1])
    return name if abs(best - value) / best <= 0.03 else ''


def screens(outputs=None):
    """The enabled screens' sizes as the picture should cover them (rotation applied), from
    `wlr-randr --json`; [] outside a Wayland session."""
    if outputs is None:
        try:
            result = subprocess.run(['wlr-randr', '--json'], capture_output=True, text=True, timeout=5)
            outputs = json.loads(result.stdout) if result.returncode == 0 else []
        except (OSError, subprocess.SubprocessError, ValueError):
            outputs = []
    out = []
    for o in outputs if isinstance(outputs, list) else []:
        if not isinstance(o, dict) or o.get('enabled') is False:
            continue
        mode = next((m for m in o.get('modes') or [] if isinstance(m, dict) and m.get('current')), None)
        if not mode:
            continue
        w, h = int(mode.get('width') or 0), int(mode.get('height') or 0)
        if str(o.get('transform', 'normal')).replace('flipped-', '').replace('flipped', 'normal') in ('90', '270'):
            w, h = h, w
        if w > 0 and h > 0:
            out.append(dict(name=str(o.get('name') or ''), width=w, height=h))
    return out


def fit_filters(screen_list):
    """atleast (the largest screen) and ratios (every screen's, in order) for the search."""
    if not screen_list:
        return {}
    largest = max(screen_list, key=lambda s: s['width'] * s['height'])
    ratios = []
    for s in screen_list:
        r = nearest_ratio(s['width'], s['height']) or ('portrait' if s['height'] > s['width'] else 'landscape')
        if r not in ratios:
            ratios.append(r)
    return dict(atleast='{}x{}'.format(largest['width'], largest['height']), ratios=','.join(ratios))


# ---- the API, with the rate limit -----------------------------------------------------------------

@contextlib.contextmanager
def locked(name):
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / name, 'a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def take_slot(now=time.time, sleep=time.sleep):
    """Count one API request against the shared limit (45 a minute); wait for a free slot up
    to RATE_MAX_WAIT seconds, else fail with how long to wait."""
    path = CACHE / 'api-calls.json'
    with locked('.rate.lock'):
        try:
            calls = [float(t) for t in json.loads(path.read_text())]
        except (OSError, ValueError, TypeError):
            calls = []
        t = now()
        calls = [c for c in calls if t - RATE_WINDOW < c <= t]
        if len(calls) >= RATE_LIMIT:
            wait = calls[0] + RATE_WINDOW - t + 0.05
            if wait > RATE_MAX_WAIT:
                raise Failure('Wallhaven allows {} searches a minute. Try again in {} seconds.'.format(
                    RATE_LIMIT, int(wait + 0.999)), wait=int(wait + 0.999))
            sleep(wait)
            t = now()
            calls = [c for c in calls if t - RATE_WINDOW < c <= t]
        calls.append(t)
        path.write_text(json.dumps(calls))


def fetch(url, timeout=TIMEOUT):
    """GET url → bytes. Network failures become Failure(OFFLINE, offline=True)."""
    request = urllib.request.Request(url, headers={'User-Agent': USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 429:
            raise Failure('Wallhaven is busy with too many requests from here. Wait a minute and try again.',
                          wait=60) from None
        if error.code == 401:
            raise Failure('Wallhaven didn’t accept your API key. Check it in Settings, or remove it.',
                          unauthorized=True) from None
        if error.code == 404:
            raise Failure('That picture isn’t on Wallhaven any more.') from None
        raise Failure('Wallhaven answered with an error ({}). Try again later.'.format(error.code)) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as error:
        raise Failure(OFFLINE, offline=True, detail=str(getattr(error, 'reason', error))) from None


def api(endpoint, params, key=None):
    """One counted API request → the decoded JSON."""
    params = {k: v for k, v in params.items() if v not in (None, '')}
    if key:
        params['apikey'] = key
    take_slot()
    body = fetch('{}/{}?{}'.format(API, endpoint, urllib.parse.urlencode(params)))
    try:
        return json.loads(body)
    except ValueError:
        raise Failure('Wallhaven sent something Settings couldn’t read. Try again later.') from None


# ---- files ------------------------------------------------------------------------------------------

def download(url, dest, validate=True):
    """Download url to dest atomically (a .part file, then a rename); with validate, Pillow must
    read it as a picture."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    data = fetch(url, timeout=120)
    fd, temp = tempfile.mkstemp(prefix='.' + dest.name + '.', suffix='.part', dir=str(dest.parent))
    try:
        with os.fdopen(fd, 'wb') as f:
            f.write(data)
        if validate:
            wallpapers.check_image(Path(temp))
        os.chmod(temp, 0o644)
        os.replace(temp, dest)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(temp)
        raise
    return dest


def prune(folder, keep):
    try:
        files = sorted((p for p in folder.iterdir() if p.is_file()), key=lambda p: p.stat().st_mtime, reverse=True)
    except OSError:
        return
    for p in files[keep:]:
        with contextlib.suppress(OSError):
            p.unlink()


def cached_thumb(url):
    """The small thumbnail of a search result, downloaded once; '' when it can't be had."""
    m = RE_THUMB.fullmatch(url or '')
    if not m:
        return ''
    dest = CACHE / 'thumbs' / '{}.{}'.format(m.group(2), m.group(3))
    if dest.is_file():
        return str(dest)
    try:
        download(url, dest, validate=False)
    except Failure:
        return ''
    return str(dest)


def item(raw):
    thumbs = raw.get('thumbs') or {}
    return dict(id=str(raw.get('id') or ''), url=str(raw.get('url') or ''), path=str(raw.get('path') or ''),
                small=str(thumbs.get('small') or ''), large=str(thumbs.get('large') or ''),
                resolution=str(raw.get('resolution') or ''), width=int(raw.get('dimension_x') or 0),
                height=int(raw.get('dimension_y') or 0), size=int(raw.get('file_size') or 0),
                type=str(raw.get('file_type') or ''), category=str(raw.get('category') or ''),
                purity=str(raw.get('purity') or ''), colors=[c for c in raw.get('colors') or [] if isinstance(c, str)][:5],
                favorites=int(raw.get('favorites') or 0), views=int(raw.get('views') or 0),
                source=str(raw.get('source') or ''), thumb='')


def downloaded(ident):
    folder = wallhaven_folder()
    for suffix in ('.jpg', '.png', '.webp', '.jpeg'):
        p = folder / ('wallhaven-' + ident + suffix)
        if p.is_file():
            return p
    return None


def wallhaven_folder():
    data = wallpapers.settings()
    return Path(data.get('folder') or wallpapers.default_folder()).expanduser() / 'wallhaven'


# ---- commands -------------------------------------------------------------------------------------

def search_params(args, saved):
    p = dict(saved)
    for name in ('categories', 'purity', 'sorting', 'range'):
        value = getattr(args, name, None)
        if value is not None:
            p[name] = value
    if args.fit is not None:
        p['fit'] = args.fit
    p = prefs(dict(p, api_key=api_key()))
    params = dict(q=(args.q or '').strip()[:200], categories=p['categories'], purity=p['purity'],
                  sorting=p['sorting'], order='desc', page=str(max(1, min(int(args.page or 1), 10000))))
    if p['sorting'] == 'toplist':
        params['topRange'] = p['range']
    if p['sorting'] == 'random' and args.seed:
        if not re.fullmatch(r'[A-Za-z0-9]{6}', args.seed):
            raise Failure('That isn’t a search seed.')
        params['seed'] = args.seed
    filters = fit_filters(screens()) if p['fit'] else {}
    params.update(filters)
    return params, p, filters


def cmd_search(args):
    key = api_key()
    params, p, filters = search_params(args, load_settings())
    cache_key = hashlib.sha256(json.dumps([params, bool(key)], sort_keys=True).encode()).hexdigest()[:24]
    cache = CACHE / 'search' / (cache_key + '.json')
    cacheable = not (p['sorting'] == 'random' and 'seed' not in params)
    data = None
    if cacheable:
        try:
            if time.time() - cache.stat().st_mtime < SEARCH_TTL:
                data = json.loads(cache.read_text())
        except (OSError, ValueError):
            data = None
    if data is None:
        data = api('search', params, key)
        if cacheable and isinstance(data, dict):
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data))
            prune(cache.parent, 200)
    items = [item(r) for r in data.get('data') or [] if isinstance(r, dict) and RE_ID.fullmatch(str(r.get('id') or ''))]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for it, thumb in zip(items, pool.map(lambda it: cached_thumb(it['small']), items)):
            it['thumb'] = thumb
            got = downloaded(it['id'])
            it['downloaded'] = str(got) if got else ''
    prune(CACHE / 'thumbs', THUMBS_KEPT)
    meta = data.get('meta') or {}
    return dict(ok=True, items=items, page=int(meta.get('current_page') or 1), last_page=int(meta.get('last_page') or 1),
                total=int(meta.get('total') or 0), seed=str(meta.get('seed') or ''), filters=filters, prefs=p,
                has_key=bool(key), current=wallpapers.current())


def checked_url(ident, url, pattern):
    if not RE_ID.fullmatch(ident or ''):
        raise Failure('That isn’t a Wallhaven picture.')
    m = pattern.fullmatch(url or '')
    if not m or ident not in url:
        raise Failure('That link isn’t a Wallhaven picture.')
    return m


def cmd_preview(args):
    m = checked_url(args.id, args.url, RE_THUMB)
    dest = CACHE / 'previews' / '{}-{}.{}'.format(m.group(2), m.group(1), m.group(3))
    if not dest.is_file():
        download(args.url, dest, validate=False)
        prune(dest.parent, PREVIEWS_KEPT)
    return dict(ok=True, id=args.id, preview=str(dest))


def cmd_download(args):
    m = checked_url(args.id, args.url, RE_FULL)
    existing = downloaded(args.id)
    if existing:
        return dict(ok=True, id=args.id, path=str(existing), existed=True)
    dest = wallhaven_folder() / 'wallhaven-{}.{}'.format(args.id, 'jpg' if m.group(2) == 'jpeg' else m.group(2))
    download(args.url, dest)
    with contextlib.suppress(Exception):
        wallpapers.thumbnail(dest)
    return dict(ok=True, id=args.id, path=str(dest), existed=False)


def cmd_set(args):
    got = cmd_download(args)
    applied = wallpapers.apply(got['path'])
    return dict(got, current=applied)


def state():
    data = load_settings()
    key = api_key()
    scr = screens()
    return dict(ok=True, has_key=bool(key), key_hint=('…' + key[-4:]) if key else '', prefs=prefs(data),
                account=data.get('account') or {}, screens=scr, filters=fit_filters(scr),
                folder=str(wallhaven_folder()))


def cmd_state(_args):
    return state()


def cmd_key(args):
    data = load_settings()
    if args.clear:
        data.pop('api_key', None)
        data.pop('account', None)
        if 'purity' in data:
            data['purity'] = clean_bits(data['purity'], DEFAULTS['purity'])[:2] + '0'
        save_settings(data)
        return state()
    key = (args.set or '').strip()
    if not RE_KEY.fullmatch(key):
        raise Failure('An API key is letters and digits (Wallhaven → Settings → Account → API key).')
    answer = api('settings', {}, key)
    account = answer.get('data') if isinstance(answer, dict) else None
    if not isinstance(account, dict):
        raise Failure('Wallhaven didn’t accept your API key.')
    data['api_key'] = key
    # The account's own filters become the defaults here (purity and categories).
    purity = account.get('purity') or []
    categories = account.get('categories') or []
    if isinstance(purity, list) and purity:
        data['purity'] = ''.join('1' if p in purity else '0' for p in ('sfw', 'sketchy', 'nsfw'))
    if isinstance(categories, list) and categories:
        data['categories'] = ''.join('1' if c in categories else '0' for c in ('general', 'anime', 'people'))
    data['account'] = dict(purity=purity, categories=categories,
                           toplist_range=str(account.get('toplist_range') or ''))
    if data['account']['toplist_range'] in RANGES:
        data['range'] = data['account']['toplist_range']
    save_settings(data)
    return state()


def cmd_prefs(args):
    data = load_settings()
    for name in ('categories', 'purity'):
        value = getattr(args, name)
        if value is not None:
            if not re.fullmatch(r'[01]{3}', value) or value == '000':
                raise Failure('Choose at least one.')
            if name == 'purity' and value[2] == '1' and not api_key():
                raise Failure('NSFW pictures need your Wallhaven API key.')
            data[name] = value
    if args.sorting is not None:
        if args.sorting not in SORTINGS:
            raise Failure('Unknown order.')
        data['sorting'] = args.sorting
    if args.range is not None:
        if args.range not in RANGES:
            raise Failure('Unknown time range.')
        data['range'] = args.range
    if args.fit is not None:
        data['fit'] = args.fit
    save_settings(data)
    return state()


def parser():
    ap = argparse.ArgumentParser(prog='wallhaven.py', add_help=False)
    sub = ap.add_subparsers(dest='cmd')
    s = sub.add_parser('search')
    s.add_argument('--q', default='')
    s.add_argument('--categories')
    s.add_argument('--purity')
    s.add_argument('--sorting')
    s.add_argument('--range')
    s.add_argument('--page', type=int, default=1)
    s.add_argument('--seed', default='')
    s.add_argument('--fit', dest='fit', action='store_true', default=None)
    s.add_argument('--no-fit', dest='fit', action='store_false')
    for name in ('preview', 'download', 'set'):
        p = sub.add_parser(name)
        p.add_argument('id')
        p.add_argument('url')
    sub.add_parser('state')
    k = sub.add_parser('key')
    g = k.add_mutually_exclusive_group(required=True)
    g.add_argument('--set')
    g.add_argument('--clear', action='store_true')
    p = sub.add_parser('prefs')
    p.add_argument('--categories')
    p.add_argument('--purity')
    p.add_argument('--sorting')
    p.add_argument('--range')
    p.add_argument('--fit', type=lambda v: {'on': True, 'off': False}[v])
    return ap


COMMANDS = {'search': cmd_search, 'preview': cmd_preview, 'download': cmd_download, 'set': cmd_set,
            'state': cmd_state, 'key': cmd_key, 'prefs': cmd_prefs}


class _ArgError(Exception):
    pass


def main(argv=None):
    ap = parser()
    ap.error = lambda message: (_ for _ in ()).throw(_ArgError(message))
    try:
        args = ap.parse_args(sys.argv[1:] if argv is None else argv)
        if args.cmd not in COMMANDS:
            raise _ArgError('usage: wallhaven.py search|preview|download|set|state|key|prefs …')
        result = COMMANDS[args.cmd](args)
    except _ArgError as error:
        print(json.dumps(dict(ok=False, error=str(error))))
        return 2
    except Failure as error:
        print(json.dumps(dict(ok=False, error=str(error), **error.extra)))
        return 1
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps(dict(ok=False, error=str(error) or error.__class__.__name__)))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
