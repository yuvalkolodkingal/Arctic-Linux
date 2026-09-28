"""Tests for scripts/wallhaven.py (the Wallhaven browser's backend) and the picture files part of
scripts/wallpapers.py (import, delete, rename). No network: HTTP is faked.

Run: python3 -m unittest discover -s shell/tests
"""
import io
import json
import os
import stat
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).parent))
from test_helpers import load  # noqa: E402


def jpeg_bytes(size=(64, 40), color=(10, 120, 200)):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', size, color).save(buf, 'JPEG')
    return buf.getvalue()


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = self.root = Path(self.tmp.name)
        self.env = dict(XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache'),
                        XDG_DATA_HOME=str(root / 'data'), HOME=str(root / 'home'))
        self.config = root / 'config' / 'arctic'
        self.config.mkdir(parents=True)
        self.pictures = root / 'home' / 'Pictures' / 'Wallpapers'
        self.pictures.mkdir(parents=True)
        self.elsewhere = root / 'Downloads'
        self.elsewhere.mkdir()
        old = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v) for k, v in old.items()])
        sys.modules.pop('wallpapers', None)
        self.wp = load('wallpapers', self.env)
        self.wp.SYSTEM = [root / 'data' / 'arctic' / 'wallpapers']
        self.wp.default_folder = lambda: self.pictures

    def tearDown(self):
        self.tmp.cleanup()


class PictureFileTests(Env):
    def test_import_copies_checks_and_renames_on_collision(self):
        src = self.elsewhere / 'Sunset at sea.jpg'
        src.write_bytes(jpeg_bytes())
        first = self.wp.import_pictures(['file://' + str(src).replace(' ', '%20')])
        self.assertTrue(first['ok'], first)
        self.assertEqual(Path(first['added'][0]), self.pictures / 'Sunset at sea.jpg')
        self.assertTrue(src.exists(), 'the original is copied, never moved')
        second = self.wp.import_pictures([str(src)])
        self.assertEqual(Path(second['added'][0]).name, 'Sunset at sea (2).jpg')
        # The listing (shared with the shell's picker) has them, with thumbnails.
        names = [i['name'] for i in self.wp.library()['items']]
        self.assertIn('Sunset at sea', names)

    def test_import_takes_the_real_type_and_refuses_non_pictures(self):
        from PIL import Image
        disguised = self.elsewhere / 'photo.jpg'
        Image.new('RGB', (30, 20)).save(disguised, 'PNG')
        text = self.elsewhere / 'notes.png'
        text.write_text('hello')
        truncated = self.elsewhere / 'cut.jpg'
        truncated.write_bytes(jpeg_bytes()[:200])
        result = self.wp.import_pictures([str(disguised), str(text), str(truncated), str(self.elsewhere / 'missing.jpg')])
        self.assertEqual([Path(p).name for p in result['added']], ['photo.png'])
        self.assertEqual(len(result['errors']), 3)
        self.assertEqual(sorted(p.name for p in self.pictures.iterdir()), ['photo.png'], 'no temporary files left')
        only_bad = self.wp.import_pictures([str(text)])
        self.assertFalse(only_bad['ok'])
        self.assertIn('notes.png', only_bad['error'])

    def test_delete_only_your_pictures_and_not_the_current_one(self):
        pic = self.pictures / 'a.jpg'
        pic.write_bytes(jpeg_bytes())
        thumb = Path(self.wp.thumbnail(pic))
        other = self.elsewhere / 'b.jpg'
        other.write_bytes(jpeg_bytes())
        with self.assertRaises(ValueError):
            self.wp.delete_picture(str(other))
        with self.assertRaises(ValueError):
            self.wp.delete_picture(str(self.pictures / '..' / '..' / '..' / 'Downloads' / 'b.jpg'))
        (self.config / 'wallpaper').write_text(str(pic) + '\n')
        with self.assertRaises(ValueError):
            self.wp.delete_picture(str(pic))
        (self.config / 'wallpaper').write_text('aurora\n')
        self.assertTrue(self.wp.delete_picture('file://' + str(pic))['ok'])
        self.assertFalse(pic.exists())
        self.assertFalse(thumb.exists(), 'its thumbnail goes too')
        self.assertTrue(other.exists())

    def test_rename_keeps_the_type_and_follows_the_current_choice(self):
        pic = self.pictures / 'wallhaven' / 'wallhaven-abc123.jpg'
        pic.parent.mkdir()
        pic.write_bytes(jpeg_bytes())
        (self.pictures / 'Taken.jpg').write_bytes(jpeg_bytes())
        (self.config / 'wallpaper').write_text(str(pic) + '\n')
        item = [i for i in self.wp.library()['items'] if i['path'] == str(pic)][0]
        self.assertTrue(item['wallhaven'])
        with self.assertRaises(ValueError):
            self.wp.rename_picture(str(pic), 'a/b')
        with self.assertRaises(ValueError):
            self.wp.rename_picture(str(pic), '.hidden')
        result = self.wp.rename_picture(str(pic), 'Mountain dawn.jpg')
        new = pic.with_name('Mountain dawn.jpg')
        self.assertEqual(result['path'], str(new))
        self.assertTrue(result['current'])
        self.assertEqual((self.config / 'wallpaper').read_text().strip(), str(new))
        with self.assertRaises(ValueError):
            self.wp.rename_picture(str(self.pictures / 'Taken.jpg'), 'wallhaven/../Mountain dawn')

    def test_command_line(self):
        src = self.elsewhere / 'x.jpg'
        src.write_bytes(jpeg_bytes())
        out = io.StringIO()
        with mock.patch.object(sys, 'argv', ['wallpapers.py', 'import', str(src)]), mock.patch('sys.stdout', out):
            self.wp.main()
        self.assertEqual(json.loads(out.getvalue())['added'], [str(self.pictures / 'x.jpg')])


class FakeHTTP:
    """Answers urlopen: API URLs from `api`, image URLs with a JPEG; records every URL."""

    def __init__(self, api):
        self.api = api
        self.urls = []

    def __call__(self, request, timeout=None):
        url = request.full_url
        self.urls.append(url)
        if url.startswith('https://wallhaven.cc/api/v1/'):
            body = self.api(url)
            if isinstance(body, Exception):
                raise body
            data = json.dumps(body).encode()
        else:
            data = jpeg_bytes()
        response = mock.MagicMock()
        response.read.return_value = data
        response.__enter__.return_value = response
        return response


def result(ident, sub='ab'):
    return {'id': ident, 'url': 'https://wallhaven.cc/w/' + ident, 'purity': 'sfw', 'category': 'general',
            'dimension_x': 3840, 'dimension_y': 2160, 'resolution': '3840x2160', 'file_size': 1234,
            'file_type': 'image/jpeg', 'colors': ['#112233'],
            'path': 'https://w.wallhaven.cc/full/{}/wallhaven-{}.jpg'.format(sub, ident),
            'thumbs': {'small': 'https://th.wallhaven.cc/small/{}/{}.jpg'.format(sub, ident),
                       'large': 'https://th.wallhaven.cc/lg/{}/{}.jpg'.format(sub, ident)}}


SEARCH = {'data': [result('abc123'), result('xyz789', 'xy')],
          'meta': {'current_page': 1, 'last_page': 7, 'per_page': 24, 'total': 150, 'seed': None}}
WLR = [{'name': 'eDP-1', 'enabled': True, 'transform': 'normal',
        'modes': [{'width': 2560, 'height': 1600, 'refresh': 120.0, 'current': True}]},
       {'name': 'DP-1', 'enabled': True, 'transform': '90',
        'modes': [{'width': 1920, 'height': 1080, 'refresh': 60.0, 'current': True}]},
       {'name': 'HDMI-A-1', 'enabled': False, 'modes': []}]


class WallhavenTests(Env):
    def setUp(self):
        super().setUp()
        sys.modules['wallpapers'] = self.wp
        self.wh = load('wallhaven', self.env)
        self.wh.wallpapers = self.wp
        self.wh.CACHE = self.root / 'cache' / 'arctic' / 'wallhaven'
        self.wh.SETTINGS = self.config / 'wallhaven.json'
        self.screens = mock.patch.object(self.wh, 'screens', return_value=self.wh.screens(WLR))
        self.screens.start()
        self.addCleanup(self.screens.stop)

    def run_cmd(self, *argv):
        out = io.StringIO()
        with mock.patch('sys.stdout', out):
            code = self.wh.main(list(argv))
        return code, json.loads(out.getvalue())

    def test_screens_and_fit_filters(self):
        scr = self.wh.screens(WLR)
        self.assertEqual(scr, [dict(name='eDP-1', width=2560, height=1600), dict(name='DP-1', width=1080, height=1920)])
        self.assertEqual(self.wh.fit_filters(scr), dict(atleast='2560x1600', ratios='16x10,9x16'))
        self.assertEqual(self.wh.fit_filters([dict(name='a', width=1366, height=768)])['ratios'], '16x9')
        self.assertEqual(self.wh.fit_filters([dict(name='a', width=3440, height=1440)])['ratios'], '21x9')
        self.assertEqual(self.wh.fit_filters([dict(name='a', width=1000, height=700)])['ratios'], 'landscape')
        self.assertEqual(self.wh.fit_filters([]), {})

    def test_rate_limit_waits_for_a_slot_then_refuses(self):
        clock = [1000.0]
        slept = []
        now = lambda: clock[0]  # noqa: E731

        def sleep(s):
            slept.append(s)
            clock[0] += s
        for _ in range(45):
            self.wh.take_slot(now, sleep)
            clock[0] += 0.1                    # 45 calls in 4.5 s
        self.assertEqual(slept, [])
        clock[0] = 1000.0 + 55                 # the oldest frees up 5 s from now: wait for it
        self.wh.take_slot(now, sleep)
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], 5.05, places=2)
        (self.wh.CACHE / 'api-calls.json').unlink()
        clock[0] = 2000.0
        for _ in range(45):                    # 45 calls in a burst: the next slot is a minute away
            self.wh.take_slot(now, sleep)
        clock[0] = 2001.0
        with self.assertRaises(self.wh.Failure) as ctx:
            self.wh.take_slot(now, sleep)
        self.assertGreater(ctx.exception.extra['wait'], 8)

    def test_search_fits_the_screens_caches_and_downloads_thumbnails(self):
        http = FakeHTTP(lambda url: SEARCH)
        with mock.patch.object(self.wh.urllib.request, 'urlopen', http):
            code, first = self.run_cmd('search', '--q', 'mountain lake', '--page', '2')
            code2, again = self.run_cmd('search', '--q', 'mountain lake', '--page', '2')
        self.assertEqual((code, code2), (0, 0))
        api = [u for u in http.urls if '/api/v1/' in u]
        self.assertEqual(len(api), 1, 'the second search came from the cache')
        q = api[0]
        for part in ('q=mountain+lake', 'purity=100', 'categories=111', 'sorting=toplist', 'topRange=1M',
                     'page=2', 'atleast=2560x1600', 'ratios=16x10%2C9x16'):
            self.assertIn(part, q)
        self.assertNotIn('apikey', q)
        self.assertEqual([i['id'] for i in first['items']], ['abc123', 'xyz789'])
        self.assertTrue(all(Path(i['thumb']).is_file() for i in first['items']))
        self.assertEqual((first['page'], first['last_page'], first['total']), (1, 7, 150))
        self.assertEqual(again['items'][0]['thumb'], first['items'][0]['thumb'])

    def test_no_fit_and_random_with_a_seed(self):
        http = FakeHTTP(lambda url: dict(SEARCH, meta=dict(SEARCH['meta'], seed='AbC123')))
        with mock.patch.object(self.wh.urllib.request, 'urlopen', http):
            _, r = self.run_cmd('search', '--sorting', 'random', '--no-fit')
            self.run_cmd('search', '--sorting', 'random', '--no-fit', '--seed', 'AbC123', '--page', '2')
            self.run_cmd('search', '--sorting', 'random', '--no-fit', '--seed', 'AbC123', '--page', '2')
            code, bad = self.run_cmd('search', '--sorting', 'random', '--seed', 'x;rm')
        api = [u for u in http.urls if '/api/v1/' in u]
        self.assertEqual(r['seed'], 'AbC123')
        self.assertNotIn('atleast', api[0])
        self.assertNotIn('topRange', api[0])
        self.assertEqual(len(api), 2, 'a seeded page is cached, the unseeded first page is not')
        self.assertIn('seed=AbC123', api[1])
        self.assertEqual(code, 1)

    def test_offline_and_errors_are_sentences(self):
        def down(request, timeout=None):
            raise urllib.error.URLError(OSError('Name or service not known'))
        with mock.patch.object(self.wh.urllib.request, 'urlopen', down):
            code, r = self.run_cmd('search')
        self.assertEqual(code, 1)
        self.assertTrue(r['offline'])
        self.assertIn('can’t be reached', r['error'])
        busy = urllib.error.HTTPError('u', 429, 'Too Many', {}, None)
        with mock.patch.object(self.wh.urllib.request, 'urlopen', FakeHTTP(lambda url: busy)):
            code, r = self.run_cmd('search', '--q', 'busy')
        self.assertEqual((code, r['wait']), (1, 60))

    def test_api_key_is_checked_stored_600_and_never_shown(self):
        account = {'data': {'purity': ['sfw', 'sketchy', 'nsfw'], 'categories': ['general', 'people'],
                            'toplist_range': '6M'}}
        http = FakeHTTP(lambda url: account if 'apikey=GoodKey12345' in url
                        else urllib.error.HTTPError(url, 401, 'Unauthorized', {}, None))
        with mock.patch.object(self.wh.urllib.request, 'urlopen', http):
            code, bad = self.run_cmd('key', '--set', 'WrongKey9999')
            self.assertEqual(code, 1)
            self.assertTrue(bad['unauthorized'])
            self.assertFalse(self.wh.SETTINGS.exists())
            code, st = self.run_cmd('key', '--set', 'GoodKey12345')
        self.assertEqual(code, 0)
        self.assertEqual(stat.S_IMODE(self.wh.SETTINGS.stat().st_mode), 0o600)
        self.assertNotIn('GoodKey12345', json.dumps(st))
        self.assertEqual(st['key_hint'], '…2345')
        self.assertEqual(st['prefs']['purity'], '111')
        self.assertEqual(st['prefs']['categories'], '101')
        self.assertEqual(st['prefs']['range'], '6M')
        with mock.patch.object(self.wh.urllib.request, 'urlopen', FakeHTTP(lambda url: SEARCH)) as http2:
            self.run_cmd('search', '--q', 'x')
        self.assertIn('apikey=GoodKey12345', [u for u in http2.urls if '/api/v1/' in u][0])
        code, st = self.run_cmd('key', '--clear')
        self.assertFalse(st['has_key'])
        self.assertEqual(st['prefs']['purity'], '110', 'NSFW goes with the key')
        self.assertNotIn('GoodKey12345', self.wh.SETTINGS.read_text())

    def test_nsfw_needs_a_key(self):
        code, r = self.run_cmd('prefs', '--purity', '101')
        self.assertEqual(code, 1)
        self.assertIn('API key', r['error'])
        code, r = self.run_cmd('prefs', '--purity', '000')
        self.assertEqual(code, 1)
        code, r = self.run_cmd('prefs', '--purity', '110', '--sorting', 'date_added', '--fit', 'off')
        self.assertEqual((r['prefs']['purity'], r['prefs']['sorting'], r['prefs']['fit']), ('110', 'date_added', False))
        # A hand-edited file with NSFW but no key still searches SFW/sketchy only.
        self.wh.SETTINGS.write_text(json.dumps({'purity': '111'}))
        self.assertEqual(self.wh.prefs()['purity'], '110')

    def test_set_downloads_checks_and_applies(self):
        ident, full = 'abc123', 'https://w.wallhaven.cc/full/ab/wallhaven-abc123.jpg'
        applied = []
        with mock.patch.object(self.wh.urllib.request, 'urlopen', FakeHTTP(lambda url: {})), \
                mock.patch.object(self.wp, 'apply', lambda key: applied.append(key) or key):
            code, r = self.run_cmd('set', ident, full)
            code2, r2 = self.run_cmd('download', ident, full)
        self.assertEqual(code, 0, r)
        dest = self.pictures / 'wallhaven' / 'wallhaven-abc123.jpg'
        self.assertEqual(r['path'], str(dest))
        self.assertTrue(dest.is_file())
        self.assertEqual(applied, [str(dest)])
        self.assertTrue(r2['existed'])
        self.assertIn(str(dest), [i['path'] for i in self.wp.library()['items']])

    def test_downloads_are_validated_and_urls_checked(self):
        def junk(request, timeout=None):
            response = mock.MagicMock()
            response.read.return_value = b'<html>not a picture</html>'
            response.__enter__.return_value = response
            return response
        with mock.patch.object(self.wh.urllib.request, 'urlopen', junk):
            code, r = self.run_cmd('download', 'abc123', 'https://w.wallhaven.cc/full/ab/wallhaven-abc123.jpg')
        self.assertEqual(code, 1)
        self.assertFalse((self.pictures / 'wallhaven').exists() and any((self.pictures / 'wallhaven').iterdir()))
        for ident, url in (('abc123', 'https://evil.example/full/ab/wallhaven-abc123.jpg'),
                           ('abc123', 'https://w.wallhaven.cc/full/ab/wallhaven-zzz999.jpg'),
                           ('../x', 'https://w.wallhaven.cc/full/ab/wallhaven-abc123.jpg')):
            code, r = self.run_cmd('download', ident, url)
            self.assertEqual(code, 1, (ident, url))
        code, r = self.run_cmd('preview', 'abc123', 'https://th.wallhaven.cc/lg/ab/abc123.jpg/../../x')
        self.assertEqual(code, 1)


if __name__ == '__main__':
    unittest.main()
