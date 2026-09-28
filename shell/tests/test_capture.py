"""Tests for dotfiles/.local/bin/arctic-capture, the capture helpers' engine, with stand-ins for
mmsg and tesseract on PATH (no desktop needed).

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HELPER = Path(__file__).parents[2] / 'dotfiles/.local/bin/arctic-capture'

CLIENTS = {'clients': [
    {'id': 1, 'appid': 'kitty', 'title': 'zsh', 'monitor': 'eDP-1', 'is_visible': True, 'is_floating': False,
     'is_minimized': False, 'is_fullscreen': False, 'x': 8, 'y': 40, 'width': 600, 'height': 400},
    {'id': 2, 'appid': 'firefox', 'title': 'Arctic', 'monitor': 'eDP-1', 'is_visible': False, 'is_floating': False,
     'is_minimized': False, 'is_fullscreen': False, 'x': 0, 'y': 0, 'width': 900, 'height': 700},
    {'id': 3, 'appid': 'org.arcticlinux.Settings', 'title': 'Arctic  Settings', 'monitor': 'eDP-1', 'is_visible': True,
     'is_floating': True, 'is_minimized': False, 'is_fullscreen': False, 'x': 300, 'y': 200, 'width': 500, 'height': 300},
]}
MONITORS = {'monitors': [
    {'name': 'eDP-1', 'active': False, 'x': 0, 'y': 0, 'width': 1536, 'height': 960, 'scale': 1.25},
    {'name': 'HDMI-A-1', 'active': True, 'x': 1536, 'y': 0, 'width': 1920, 'height': 1080, 'scale': 1},
]}


class CaptureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.home = self.root / 'home'
        mango = self.home / '.config/mango'
        (mango / 'arctic').mkdir(parents=True)
        (mango / 'config.conf').write_text('source=~/.config/mango/arctic/look.conf\n'
                                           'source-optional=~/.config/mango/user.conf\n')
        (mango / 'arctic/look.conf').write_text('borderpx=2\n')
        (mango / 'user.conf').write_text('# mine\nborderpx=3   # thicker\nxkb_rules_layout=us,il\n')
        self.focused = {'id': 1, 'appid': 'kitty', 'title': 'zsh', 'monitor': 'eDP-1', 'is_fullscreen': False,
                        'x': 8, 'y': 40, 'width': 600, 'height': 400}
        self.write_mmsg()

    def tearDown(self):
        self.tmp.cleanup()

    def write_mmsg(self):
        answers = {'focusing-client': self.focused, 'all-clients': CLIENTS, 'all-monitors': MONITORS}
        for name, data in answers.items():
            (self.root / (name + '.json')).write_text(json.dumps(data))
        self.fake('mmsg', 'cat "{}/$2.json"'.format(self.root))

    def fake(self, name, script):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + script + '\n')
        path.chmod(0o755)

    def run_helper(self, *args, stdin=None, env=None):
        environ = dict(HOME=str(self.home), PATH='{}:/usr/bin:/bin'.format(self.bin), LANG='he_IL.UTF-8')
        environ.update(env or {})
        result = subprocess.run([sys.executable, str(HELPER)] + list(args), env=environ, input=stdin,
                                capture_output=True, timeout=30)
        return result.returncode, result.stdout.decode()

    def json(self, *args, **kw):
        code, out = self.run_helper(*args, **kw)
        self.assertEqual(len(out.splitlines()), 1, out)
        data = json.loads(out)
        self.assertEqual(code, 0 if data['ok'] else 2 if data['code'] == 'usage' else 1, data)
        return data

    def test_window_leaves_out_the_border_from_the_config_chain(self):
        data = self.json('window')
        self.assertEqual(data['geometry'], '11,43 594x394')            # user.conf's borderpx=3 wins
        self.assertEqual((data['app_id'], data['output']), ('kitty', 'eDP-1'))

    def test_full_screen_windows_have_no_border(self):
        self.focused.update(is_fullscreen=True, x=0, y=0, width=1536, height=960)
        self.write_mmsg()
        self.assertEqual(self.json('window')['geometry'], '0,0 1536x960')

    def test_no_focused_window(self):
        self.focused = {'error': 'no focused client'}
        self.write_mmsg()
        data = self.json('window')
        self.assertEqual(data['code'], 'no_window')

    def test_without_mango(self):
        (self.bin / 'mmsg').unlink()
        data = self.json('output', env={'PATH': str(self.bin)})
        self.assertEqual(data['code'], 'no_display')
        self.assertTrue(data['error'].endswith('.'))

    def test_focused_output_and_by_name(self):
        data = self.json('output')
        self.assertEqual((data['name'], data['count'], data['scale'], data['geometry']),
                         ('HDMI-A-1', 2, 1, '1536,0 1920x1080'))
        self.assertEqual(self.json('output', 'eDP-1')['scale'], 1.25)
        self.assertEqual(self.json('output', 'DP-9')['code'], 'no_display')

    def test_rects_are_visible_windows_floating_first(self):
        code, out = self.run_helper('rects')
        self.assertEqual(code, 0)
        self.assertEqual(out.splitlines(), ['303,203 494x294 org.arcticlinux.Settings', '11,43 594x394 kitty'])

    def test_pixel_from_a_grim_frame(self):
        frame = b'P6\n# grim\n2 2\n255\n' + bytes([30, 42, 56]) + bytes(9)
        data = self.json('pixel', stdin=frame)
        self.assertEqual((data['hex'], data['rgb'], data['hsl']), ('#1e2a38', [30, 42, 56], [212, 30, 17]))
        self.assertEqual(data['rgb_text'], 'rgb(30, 42, 56)')
        self.assertEqual(self.json('pixel', stdin=b'P3\n1 1\n255\n0 0 0\n')['code'], 'capture_failed')
        self.assertEqual(self.json('pixel', stdin=b'')['code'], 'capture_failed')

    def test_ocr_reads_in_your_languages(self):
        self.fake('tesseract', 'if [ "$1" = --list-langs ]; then\n'
                  '  echo "List of available languages in \\"/usr/share/tesseract/tessdata/\\" (3):"\n'
                  '  printf "eng\\nheb\\nosd\\n"\nelse\n  echo "$@" > "$(dirname "$0")/args"\n'
                  '  printf "שלום world\\nsecond line\\n\\n"\nfi')
        data = self.json('ocr', 'shot.png')
        self.assertEqual(data['text'], 'שלום world\nsecond line')
        self.assertEqual((data['lines'], data['langs'], data['missing']), (2, ['heb', 'eng'], []))
        self.assertEqual((self.bin / 'args').read_text().split(), ['shot.png', '-', '-l', 'heb+eng'])

    def test_ocr_offers_a_missing_language(self):
        self.fake('tesseract', 'if [ "$1" = --list-langs ]; then echo "List (1):"; echo eng; else true; fi')
        data = self.json('ocr', 'shot.png', env={'LANG': 'de_DE.UTF-8'})
        self.assertEqual(data['code'], 'not_found')              # tesseract read nothing
        self.assertEqual((data['langs'], data['missing'], data['missing_name']), (['eng'], ['deu'], 'German'))

    def test_ocr_without_tesseract(self):
        data = self.json('ocr', 'shot.png', env={'PATH': str(self.bin)})
        self.assertEqual((data['code'], data['tool']), ('missing_tool', 'tesseract'))

    def test_qr_kinds_never_show_secrets(self):
        self.fake('zbarimg', 'printf "%s\\n" "$ZBAR_OUT"')
        env = {'PYTHONPATH': str(self.root)}     # hide a real zxingcpp: zbarimg's path is tested
        (self.root / 'zxingcpp.py').write_text('raise ImportError("hidden in tests")\n')
        cases = [('https://arcticlinux.org/' + 'x' * 80, 'url'), ('otpauth://totp/me?secret=ABC', 'otpauth'),
                 ('WIFI:T:WPA;S:Cafe\\;Net;P:hunter2;;', 'wifi'), ('hello', 'text')]
        for text, kind in cases:
            with self.subTest(kind):
                env['ZBAR_OUT'] = text
                data = self.json('qr', 'code.png', env=env)
                self.assertEqual((data['codes'], data['kind']), ([text], kind))
                self.assertNotIn('secret', data['shown'])
                self.assertNotIn('hunter2', data['shown'])
                self.assertLessEqual(len(data['shown']), 60)
        env['ZBAR_OUT'] = 'WIFI:T:WPA;S:Cafe\\;Net;P:hunter2;;'
        self.assertEqual(self.json('qr', 'code.png', env=env)['shown'], 'Cafe;Net')
        env['ZBAR_OUT'] = ''
        self.assertEqual(self.json('qr', 'code.png', env=env)['code'], 'not_found')

    def test_swatch_and_uri(self):
        out = self.root / 'swatch.svg'
        self.json('swatch', '#1E2A38', str(out))
        self.assertIn('fill="#1e2a38"', out.read_text())
        self.assertEqual(self.json('swatch', 'red', str(out))['code'], 'usage')
        self.assertEqual(self.json('uri', '/tmp/My Pictures/a#1.png')['uri'], 'file:///tmp/My%20Pictures/a%231.png')

    def test_usage(self):
        code, _out = self.run_helper('frobnicate')
        self.assertEqual(code, 2)


class RecordStatusTest(unittest.TestCase):
    """arctic-record status --json, which the bar reads (the recording itself needs a desktop)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / 'arctic'
        self.run_dir.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def status(self):
        result = subprocess.run(['bash', str(HELPER.parent / 'arctic-record'), 'status', '--json'], capture_output=True,
                                text=True, timeout=30, env=dict(os.environ, XDG_RUNTIME_DIR=self.tmp.name))
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_not_recording(self):
        self.assertEqual(self.status(), {'ok': True, 'recording': False})

    def test_recording_and_stale_state(self):
        sleeper = subprocess.Popen(['sleep', '30'])
        try:
            state = {'ok': True, 'recording': True, 'pid': sleeper.pid, 'started': 1, 'file': '/x.webm'}
            (self.run_dir / 'record.json').write_text(json.dumps(state))
            self.assertEqual(self.status(), state)
        finally:
            sleeper.kill()
            sleeper.wait()
        # The recorder is gone (it crashed, or the session restarted): not recording any more.
        self.assertEqual(self.status(), {'ok': True, 'recording': False})
        self.assertFalse((self.run_dir / 'record.json').exists())


if __name__ == '__main__':
    unittest.main()
