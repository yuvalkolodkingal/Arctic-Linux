"""Tests for the scripts behind the clipboard panel (scripts/clipboard.py, with a stand-in
cliphist) and the emoji picker (scripts/emoji-index.py, with a small emoji-test.txt).

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'

EMOJI_TEST = '''\
# group: Smileys & Emotion
# subgroup: face-smiling
1F600                                                  ; fully-qualified     # 😀 E1.0 grinning face
1FAEA                                                  ; fully-qualified     # 🫪 E17.0 distorted face
263A FE0F                                              ; fully-qualified     # ☺️ E0.6 smiling face
263A                                                   ; unqualified         # ☺ E0.6 smiling face
# group: People & Body
# subgroup: hand-fingers-closed
1F44D                                                  ; fully-qualified     # 👍 E0.6 thumbs up
1F44D 1F3FB                                            ; fully-qualified     # 👍🏻 E1.0 thumbs up: light skin tone
1F44D 1F3FF                                            ; fully-qualified     # 👍🏿 E1.0 thumbs up: dark skin tone
# subgroup: family
1F9D1 1F3FB 200D 1F91D 200D 1F9D1 1F3FF                ; fully-qualified     # 🧑🏻‍🤝‍🧑🏿 E12.1 people holding hands: light skin tone, dark skin tone
# group: Component
1F3FB                                                  ; fully-qualified     # 🏻 E1.0 light skin tone
# group: Flags
1F1EE 1F1F1                                            ; fully-qualified     # 🇮🇱 E2.0 flag: Israel
'''
CLDR_HE = '''<?xml version="1.0" encoding="UTF-8"?>
<ldml><annotations>
<annotation cp="👍">אגודל | יד | לייק</annotation>
<annotation cp="👍" type="tts">אגודל למעלה</annotation>
</annotations></ldml>
'''


def run(script, *args, env):
    result = subprocess.run([sys.executable, str(SCRIPTS / script)] + list(args), capture_output=True,
                            timeout=30, env=env)
    return result.returncode, result.stdout.decode()


class EmojiIndexTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'emoji-test.txt').write_text(EMOJI_TEST)
        (root / 'cldr/annotations').mkdir(parents=True)
        (root / 'cldr/annotations/he.xml').write_text(CLDR_HE)
        self.env = dict(os.environ, HOME=str(root), XDG_CACHE_HOME=str(root / 'cache'), XDG_STATE_HOME=str(root / 'state'),
                        ARCTIC_EMOJI_TEST=str(root / 'emoji-test.txt'), ARCTIC_EMOJI_CLDR=str(root / 'cldr/annotations'),
                        LANG='he_IL.UTF-8')
        self.root = root

    def tearDown(self):
        self.tmp.cleanup()

    def index(self):
        code, out = run('emoji-index.py', env=self.env)
        self.assertEqual(code, 0, out)
        return json.loads(out)

    def test_fully_qualified_with_tones_folded(self):
        data = self.index()
        # Not the Emoji 17.0 face: the colour font doesn't draw it yet.
        self.assertEqual([e['e'] for e in data['emoji']], ['😀', '☺️', '👍', '🇮🇱'])
        thumbs = data['emoji'][2]
        self.assertEqual((thumbs['name'], thumbs['group'], thumbs['tones']), ('thumbs up', 'People & Body', ['👍🏻', '👍🏿']))
        self.assertIn('hand fingers closed', thumbs['keys'])
        self.assertIn('לייק', thumbs['keys'])                   # CLDR keywords in your language
        self.assertNotIn('אגודל למעלה', thumbs['keys'])         # not the spoken name
        self.assertEqual(data['unicode'], '12.1')
        self.assertTrue((self.root / 'cache/arctic/emoji.json').exists())

    def test_cache_follows_the_language(self):
        self.index()
        self.env['LANG'] = 'en_US.UTF-8'
        self.assertNotIn('לייק', self.index()['emoji'][2]['keys'])

    def test_recent_and_lines(self):
        for e in ('👍', '😀', '👍'):
            self.assertEqual(run('emoji-index.py', '--used', e, env=self.env)[0], 0)
        self.assertEqual(self.index()['recent'], ['👍', '😀'])
        self.assertEqual(self.index()['tone'], 0)
        self.assertEqual(run('emoji-index.py', '--tone', '3', env=self.env)[0], 0)
        self.assertEqual(run('emoji-index.py', '--tone', '9', env=self.env)[0], 2)
        self.assertEqual((self.index()['tone'], self.index()['recent']), (3, ['👍', '😀']))
        code, out = run('emoji-index.py', '--lines', env=self.env)
        self.assertEqual(code, 0)
        self.assertTrue(out.splitlines()[2].startswith('👍\tthumbs up  hand fingers closed'))

    def test_missing_list(self):
        self.env['ARCTIC_EMOJI_TEST'] = str(self.root / 'nothing.txt')
        code, out = run('emoji-index.py', env=self.env)
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)['ok'])


class ClipboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        (root / 'bin').mkdir()
        self.log = root / 'calls'
        listing = ('124\tsome text  with spaces\n123\t[[ binary data 12 KiB png 800x600 ]]\n'
                   '122\t[[ something else ]]\nnot a line\n')
        (root / 'listing').write_text(listing)
        self.fake(root / 'bin/cliphist', 'echo "cliphist $*" >> {log}\n'
                  'case "$1" in delete) cat > {log}.stdin ;; list) cat {root}/listing ;; decode) [ "$2" = 9 ] && {{ echo "id 9 not found" >&2; exit 1; }}; '
                  'printf "hello" ;; esac'.format(log=self.log, root=root))
        self.fake(root / 'bin/wl-copy', 'echo "wl-copy $*" >> {log}; cat > {log}.copied'.format(log=self.log))
        self.env = dict(os.environ, PATH='{}:/usr/bin:/bin'.format(root / 'bin'), XDG_CACHE_HOME=str(root / 'cache'))

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def fake(path, script):
        path.write_text('#!/bin/sh\n' + script + '\n')
        path.chmod(0o755)

    def call(self, *args):
        code, out = run('clipboard.py', *args, env=self.env)
        data = json.loads(out)
        self.assertEqual(code, 0 if data['ok'] else 1, data)
        return data

    def test_list(self):
        items = self.call('list')['items']
        self.assertEqual(items[0], {'id': '124', 'kind': 'text', 'preview': 'some text  with spaces'})
        self.assertEqual(items[1], {'id': '123', 'kind': 'image', 'size': '12 KiB', 'format': 'png', 'width': 800,
                                    'height': 600, 'thumb': ''})
        self.assertEqual(items[2]['kind'], 'text')              # a preview it doesn't know is text
        self.assertEqual(len(items), 3)

    def test_copy_delete_wipe(self):
        self.assertEqual(self.call('copy', '124')['kind'], 'text')
        self.assertEqual((self.log.parent / 'calls.copied').read_text(), 'hello')
        self.call('delete', '124')
        self.assertEqual((self.log.parent / 'calls.stdin').read_text(), '124\t\n')
        self.call('wipe')
        self.assertEqual(self.log.read_text().splitlines(),
                         ['cliphist decode 124', 'wl-copy ', 'cliphist delete', 'cliphist wipe'])

    def test_errors_are_sentences(self):
        self.assertIn('no longer', self.call('copy', '9')['error'])
        self.assertIn('usage', self.call('copy', '1; rm -rf')['error'])
        self.env['PATH'] = '/nonexistent'
        self.assertIn('isn’t installed', self.call('list')['error'])


if __name__ == '__main__':
    unittest.main()
