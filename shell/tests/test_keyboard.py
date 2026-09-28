"""Tests for scripts/keyboard.py, the bar's keyboard-layout helper: the Mango config chain, the
names from evdev.xml, mapping Mango's layout name back to an index, and the switch commands
(with a fake mmsg that records its calls).

Run: python3 -m unittest discover -s shell/tests
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import unittest

SCRIPT = Path(__file__).parents[1] / 'scripts' / 'keyboard.py'
sys.path.insert(0, str(SCRIPT.parent))
import keyboard as K  # noqa: E402

EVDEV = textwrap.dedent('''\
    <?xml version="1.0" encoding="UTF-8"?>
    <xkbConfigRegistry version="1.1">
      <layoutList>
        <layout>
          <configItem><name>us</name><shortDescription>en</shortDescription><description>English (US)</description></configItem>
          <variantList>
            <variant><configItem><name>dvorak</name><description>English (Dvorak)</description></configItem></variant>
          </variantList>
        </layout>
        <layout>
          <configItem><name>il</name><shortDescription>he</shortDescription><description>Hebrew</description></configItem>
          <variantList>
            <variant><configItem><name>lyx</name><description>Hebrew (lyx)</description></configItem></variant>
          </variantList>
        </layout>
        <layout>
          <configItem><name>ara</name><shortDescription>ar</shortDescription><description>Arabic</description></configItem>
        </layout>
      </layoutList>
    </xkbConfigRegistry>
    ''')


class KeyboardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.mango = self.home / '.config/mango'
        (self.mango / 'arctic').mkdir(parents=True)
        self.etc = self.root / 'etc'
        self.etc.mkdir()
        (self.mango / 'config.conf').write_text(textwrap.dedent('''\
            source=~/.config/mango/arctic/input.conf
            source-optional={}/keyboard.conf
            source-optional=~/.config/mango/settings.conf
            source-optional=./user.conf
            '''.format(self.etc)))
        (self.mango / 'arctic/input.conf').write_text('xkb_rules_layout=us\nrepeat_rate=30\n')
        self.evdev = self.root / 'evdev.xml'
        self.evdev.write_text(EVDEV)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.log = self.root / 'calls.log'

    def tearDown(self):
        self.tmp.cleanup()

    def fake_mmsg(self, script):
        path = self.bin / 'mmsg'
        path.write_text('#!/bin/sh\necho "mmsg $*" >> "{}"\n{}\n'.format(self.log, script))
        path.chmod(0o755)

    def run_script(self, *args):
        env = dict(os.environ, HOME=str(self.home), ARCTIC_XKB_RULES=str(self.evdev),
                   PATH=str(self.bin) + ':/usr/bin:/bin')
        result = subprocess.run([sys.executable, str(SCRIPT)] + list(args), env=env, capture_output=True,
                                text=True, timeout=30)
        return result.returncode, [json.loads(line) for line in result.stdout.splitlines()]

    def test_the_last_value_wins_in_mangos_order(self):
        (self.etc / 'keyboard.conf').write_text('xkb_rules_layout=us,il\nxkb_rules_options=grp:alt_shift_toggle\n')
        code, out = self.run_script('layouts')
        self.assertEqual(code, 0)
        self.assertEqual([l['code'] for l in out[0]['layouts']], ['us', 'il'])
        self.assertEqual((out[0]['switch_key'], out[0]['switch_label']), ('grp:alt_shift_toggle', 'Alt + Shift'))
        # Settings' file comes later and wins; user.conf (./ next to config.conf) wins over it.
        (self.mango / 'settings.conf').write_text('xkb_rules_layout = us, il, ara  # comment\nxkb_rules_variant=dvorak,lyx\n')
        code, out = self.run_script('layouts')
        self.assertEqual(out[0]['layouts'], [
            dict(code='us', variant='dvorak', name='English (Dvorak)', short='EN'),
            dict(code='il', variant='lyx', name='Hebrew (lyx)', short='HE'),
            dict(code='ara', variant='', name='Arabic', short='AR')])
        (self.mango / 'user.conf').write_text('xkb_rules_layout=il\nxkb_rules_variant=\n')
        code, out = self.run_script('layouts')
        self.assertEqual([(l['code'], l['name']) for l in out[0]['layouts']], [('il', 'Hebrew')])

    def test_missing_files_and_unknown_layouts(self):
        (self.mango / 'arctic/input.conf').unlink()
        self.assertEqual([l['code'] for l in K.layouts(config=K.read_config(self.root / 'nothing.conf'), names={})['layouts']], ['us'])
        info = K.layouts(config={'xkb_rules_layout': 'xx,us'}, names=K.xkb_names(str(self.evdev)))
        self.assertEqual(info['layouts'][0], dict(code='xx', variant='', name='xx', short='XX'))
        self.assertEqual(info['switch_key'], '')
        # Mango sources itself: no endless loop.
        loop = self.root / 'loop.conf'
        loop.write_text('source={}\nxkb_rules_layout=de\n'.format(loop))
        self.assertEqual(K.read_config(loop)['xkb_rules_layout'], 'de')

    def test_mangos_name_to_an_index(self):
        items = K.layouts(config={'xkb_rules_layout': 'us,il', 'xkb_rules_variant': ',lyx'}, names=K.xkb_names(str(self.evdev)))['layouts']
        self.assertEqual(K.index_of('English (US)', items), 0)
        self.assertEqual(K.index_of('Hebrew (lyx)', items), 1)
        self.assertEqual(K.index_of('hebrew (LYX)', items), 1)
        self.assertEqual(K.index_of('he', items), 1)
        self.assertEqual(K.index_of('il', items), 1)
        self.assertEqual(K.index_of('German', items), -1)
        self.assertEqual(K.active('{"layout":"Hebrew (lyx)"}', items), dict(type='active', index=1, name='Hebrew (lyx)'))
        self.assertIsNone(K.active('not json', items))
        self.assertIsNone(K.active('{"other": 1}', items))

    def test_switching(self):
        self.fake_mmsg('echo \'{"success":true}\'')
        self.assertEqual(self.run_script('set', '0'), (0, [{'ok': True}]))
        self.assertEqual(self.run_script('set', '2')[0], 0)
        self.assertEqual(self.run_script('next')[0], 0)
        self.assertEqual(self.log.read_text().splitlines(), [
            'mmsg dispatch switch_keyboard_layout,1',       # the first layout (Mango counts from 1)
            'mmsg dispatch switch_keyboard_layout,3',
            'mmsg dispatch switch_keyboard_layout,0'])       # 0 cycles
        self.assertEqual(self.run_script('set', '-1')[0], 2)
        self.assertEqual(self.run_script('set', 'x')[0], 2)
        self.fake_mmsg('exit 1')
        code, out = self.run_script('next')
        self.assertEqual((code, out[0]['ok']), (1, False))

    def test_watch(self):
        (self.etc / 'keyboard.conf').write_text('xkb_rules_layout=us,il\n')
        self.fake_mmsg(textwrap.dedent('''\
            case "$1" in
              get) echo '{"layout":"English (US)"}' ;;
              watch) echo '{"layout":"English (US)"}'; echo '{"layout":"Hebrew"}'; echo '{"layout":"Hebrew"}'; echo junk ;;
            esac'''))
        code, out = self.run_script('watch')
        self.assertEqual(out[0]['type'], 'layouts')
        self.assertEqual([(o['index'], o['name']) for o in out[1:]], [(0, 'English (US)'), (1, 'Hebrew')])


if __name__ == '__main__':
    unittest.main()
