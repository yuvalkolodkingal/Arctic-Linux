"""Tests for settings/scripts/arctic_settings.py, the Settings app's backend.

    python3 -m unittest discover -s settings/tests -v

Each test runs the helper as the app does (a subprocess printing JSON) in a throwaway home
directory with the repository's Mango config, and with stand-ins for mmsg, wlr-randr,
arctic-theme, arctic-update and nmcli that record how they were called. When Mango itself is
installed (the Fedora container), `mango -c FILE -p` checks every settings.conf written.
"""
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HELPER = REPO / 'settings' / 'scripts' / 'arctic_settings.py'
DOTFILES = REPO / 'dotfiles'
sys.path.insert(0, str(HELPER.parent))
import arctic_settings as S  # noqa: E402

REAL_MANGO = shutil.which('mango')

WLR_RANDR_JSON = [
    {'name': 'eDP-1', 'description': 'Built-in display', 'make': 'BOE', 'model': '0x0BCA', 'serial': None,
     'physical_size': {'width': 300, 'height': 190}, 'enabled': True,
     'modes': [{'width': 2560, 'height': 1600, 'refresh': 60.002, 'preferred': True, 'current': True},
               {'width': 1920, 'height': 1200, 'refresh': 60.0, 'preferred': False, 'current': False}],
     'position': {'x': 0, 'y': 0}, 'transform': 'normal', 'scale': 1.5, 'adaptive_sync': False},
    {'name': 'HDMI-A-1', 'description': 'Dell U2720Q', 'make': 'Dell Inc.', 'model': 'DELL U2720Q', 'serial': 'X',
     'physical_size': {'width': 600, 'height': 340}, 'enabled': True,
     'modes': [{'width': 3840, 'height': 2160, 'refresh': 59.997, 'preferred': True, 'current': True}],
     'position': {'x': 1707, 'y': 0}, 'transform': 'normal', 'scale': 2.0, 'adaptive_sync': False},
]


def stub(folder, name, body):
    path = Path(folder) / name
    path.write_text('#!/bin/sh\n' + textwrap.dedent(body))
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return path


class Home(unittest.TestCase):
    """A home directory with Arctic's Mango config (as dotfiles/install.sh copies it)."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='arctic-settings-test-'))
        self.home = self.tmp / 'home'
        self.bin = self.tmp / 'bin'
        self.log = self.tmp / 'calls.log'
        self.bin.mkdir()
        mango = self.home / '.config/mango'
        (mango / 'arctic').mkdir(parents=True)
        shutil.copy(DOTFILES / '.config/mango/config.conf', mango / 'config.conf')
        for conf in (DOTFILES / '.config/mango/arctic').glob('*.conf'):
            shutil.copy(conf, mango / 'arctic' / conf.name)
        theme = self.home / '.config/arctic'
        theme.mkdir(parents=True)
        shutil.copytree(DOTFILES / '.config/arctic/themes/polar-night', theme / 'themes/polar-night')
        (theme / 'current').symlink_to('themes/polar-night')
        self.etc = self.tmp / 'etc'
        (self.etc / 'mango').mkdir(parents=True)
        shutil.copy(REPO / 'packaging/desktop/default-apps', self.etc / 'default-apps')
        self.share = self.tmp / 'share'
        self.share.mkdir()
        shutil.copy(DOTFILES / '.local/share/arctic/keys.txt', self.share / 'keys.txt')
        stub(self.bin, 'mmsg', 'echo "mmsg $*" >> "{}"\n'.format(self.log))
        self.data_dirs = self.tmp / 'xdg-data'
        (self.data_dirs / 'applications').mkdir(parents=True)
        path = [str(self.bin), '/usr/bin', '/bin']
        if REAL_MANGO:
            path.insert(1, os.path.dirname(REAL_MANGO))
        self.env = dict(HOME=str(self.home), PATH=':'.join(path), XDG_RUNTIME_DIR=str(self.tmp),
                        ARCTIC_ETC=str(self.etc), ARCTIC_SHARE=str(self.share), XDG_DATA_DIRS=str(self.data_dirs),
                        ARCTIC_SETTINGS_NO_WATCHDOG='1', LANG='C.UTF-8')
        self.paths = S.Paths(self.env)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def helper(self, *args, ok=True):
        result = subprocess.run([sys.executable, str(HELPER)] + [str(a) for a in args], env=self.env,
                                capture_output=True, text=True, timeout=60)
        try:
            data = json.loads(result.stdout)
        except ValueError:
            self.fail('not JSON: {!r} {!r}'.format(result.stdout, result.stderr))
        if ok:
            self.assertTrue(data.get('ok'), data)
            self.assertEqual(result.returncode, 0)
        else:
            self.assertFalse(data.get('ok'), data)
            self.assertEqual(result.returncode, 1)
            self.assertTrue(data.get('error'))
        return data

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    @property
    def settings(self):
        return (self.home / '.config/mango/settings.conf').read_text()

    @property
    def config(self):
        return (self.home / '.config/mango/config.conf').read_text()


class OptionTableTest(unittest.TestCase):
    def test_every_option_is_a_mango_0_17_3_key(self):
        keys = {line.strip() for line in (Path(__file__).parent / 'mango-0.17.3-keys.txt').read_text().splitlines()
                if line.strip() and not line.startswith('#')}
        self.assertEqual(sorted(set(S.OPTIONS) - keys), [])

    def test_layouts_are_mango_layouts(self):
        self.assertIn('tile', S.LAYOUTS)
        self.assertIn('scroller', S.LAYOUTS)
        self.assertEqual(len(S.LAYOUTS), len(set(S.LAYOUTS)))

    def test_normalise(self):
        self.assertEqual(S.normalise('gappih', '12'), '12')
        self.assertEqual(S.normalise('sloppyfocus', 'true'), '1')
        self.assertEqual(S.normalise('trackpad_accel_speed', '-0.250'), '-0.25')
        self.assertEqual(S.normalise('focused_opacity', '1.0'), '1')
        self.assertEqual(S.normalise('xkb_rules_layout', 'us,de'), 'us,de')
        for key, value in [('gappih', '-1'), ('gappih', '65'), ('gappih', '1.5'), ('borderpx', 'x'),
                           ('trackpad_accel_speed', '2'), ('xkb_rules_layout', 'us;rm -rf'),
                           ('xkb_rules_layout', ''), ('xkb_rules_options', 'caps'), ('cursor_theme', 'a,b'),
                           ('cursor_theme', 'a=b'), ('nope', '1'), ('trackpad_accel_speed', 'nan')]:
            with self.assertRaises(S.Failure, msg=(key, value)):
                S.normalise(key, value)

    def test_comments_like_mango(self):
        self.assertEqual(S.split_line('gappih=8 # inner'), ('gappih', '8'))
        self.assertEqual(S.split_line('xkb_rules_variant= # none'), ('xkb_rules_variant', ''))
        self.assertEqual(S.split_line('bind=SUPER,v,spawn_shell,a#b'), ('bind', 'SUPER,v,spawn_shell,a#b'))
        self.assertIsNone(S.split_line('# gappih=8'))
        self.assertIsNone(S.split_line('no equals sign'))


class SettingsFileTest(unittest.TestCase):
    def test_round_trip_keeps_unknown_lines(self):
        text = textwrap.dedent('''\
            # a comment
            gappih=12
            xkb_rules_variant= # none
            tagrule=id:*,layout_name:scroller
            monitorrule=name:^eDP-1$,width:1920,height:1080,refresh:60,x:0,y:0,scale:1.25,rr:0,vrr:0
            keymode=default
            bind=SUPER+ALT,b,spawn_shell,firefox --new-window
            exec-once=nm-applet --indicator
            env=FOO,bar
            gappih=oops
            windowrule=isfloating:1,appid:pavucontrol
            ''')
        model = S.SettingsFile.parse(text)
        self.assertEqual(model.options, {'gappih': '12', 'xkb_rules_variant': ''})
        self.assertEqual(model.layout, 'scroller')
        self.assertEqual(model.monitors[0]['name'], 'eDP-1')
        self.assertEqual(model.monitors[0]['scale'], 1.25)
        self.assertEqual(model.binds, [dict(mods='SUPER+ALT', key='b', command='firefox --new-window')])
        self.assertEqual(model.startup, ['nm-applet --indicator'])
        self.assertEqual(model.extra, ['env=FOO,bar', 'gappih=oops', 'windowrule=isfloating:1,appid:pavucontrol'])
        again = S.SettingsFile.parse(model.render())
        self.assertEqual(again.render(), model.render())
        self.assertIn('xkb_rules_variant= # none\n', model.render())
        self.assertIn('monitorrule=name:^eDP-1$,width:1920,height:1080,refresh:60,x:0,y:0,scale:1.25,rr:0,vrr:0',
                      model.render())

    def test_too_long_lines_are_refused(self):
        model = S.SettingsFile()
        model.startup.append('x' * 600)
        with self.assertRaises(S.Failure):
            model.render()

    def test_out_of_range_hand_edits_are_clamped(self):
        model = S.SettingsFile.parse('borderpx=20\nfocused_opacity=0.1\ngappih=oops\n')
        self.assertEqual(model.options, {'borderpx': '16', 'focused_opacity': '0.3'})
        self.assertEqual(model.extra, ['gappih=oops'])

    def test_binds_of_other_keymodes_stay_verbatim(self):
        text = textwrap.dedent('''\
            keymode=default
            bind=SUPER+ALT,b,spawn_shell,firefox
            keymode=resize
            bind=NONE,h,spawn_shell,notify-send left
            bind=NONE,Escape,setkeymode,default
            keymode=default
            env=FOO,bar
            ''')
        model = S.SettingsFile.parse(text)
        self.assertEqual(model.binds, [dict(mods='SUPER+ALT', key='b', command='firefox')])
        self.assertEqual(model.extra, ['keymode=resize', 'bind=NONE,h,spawn_shell,notify-send left',
                                       'bind=NONE,Escape,setkeymode,default', 'keymode=default', 'env=FOO,bar'])
        self.assertEqual(S.SettingsFile.parse(model.render()).render(), model.render())
        # A file that ends in another keymode gets the way back, so user.conf starts in default.
        model = S.SettingsFile.parse('keymode=resize\nbind=NONE,h,spawn_shell,x\n')
        self.assertEqual(model.binds, [])
        self.assertTrue(model.render().endswith('keymode=default\n'))
        self.assertEqual(S.SettingsFile.parse(model.render()).render(), model.render())

    def test_mimeapps_keeps_other_lines(self):
        text = textwrap.dedent('''\
            # my comment
            [Added Associations]
            text/html=a.desktop;

            [Default Applications]
            # browsers
            text/html=old.desktop
            image/png=viewer.desktop
            text/html=dup.desktop

            [Removed Associations]
            video/mp4=bad.desktop
            ''')
        out = S.update_mimeapps(text, 'Default Applications',
                                {'text/html': 'new.desktop', 'x-scheme-handler/http': 'new.desktop'})
        self.assertEqual(out, textwrap.dedent('''\
            # my comment
            [Added Associations]
            text/html=a.desktop;

            [Default Applications]
            # browsers
            text/html=new.desktop
            image/png=viewer.desktop
            x-scheme-handler/http=new.desktop

            [Removed Associations]
            video/mp4=bad.desktop
            '''))
        self.assertEqual(S.update_mimeapps(None, 'Default Applications', {'a/b': 'x.desktop'}),
                         '[Default Applications]\na/b=x.desktop\n')
        self.assertEqual(S.update_mimeapps('[Added Associations]\na/b=y.desktop\n', 'Default Applications',
                                           {'a/b': 'x.desktop'}),
                         '[Added Associations]\na/b=y.desktop\n\n[Default Applications]\na/b=x.desktop\n')

    @unittest.skipUnless(REAL_MANGO, 'mango is not installed')
    def test_mango_accepts_what_settings_writes(self):
        model = S.SettingsFile.parse('')
        for key, spec in S.OPTIONS.items():
            kind, low, high, default = spec
            model.options[key] = {'layout': 'us,de', 'variant': ',nodeadkeys', 'xkboptions': 'grp:alt_shift_toggle',
                                  'cursor': 'Adwaita'}.get(kind, S.format_number(high) if kind == 'float' else str(high))
        model.options['xkb_rules_variant'] = ''
        model.layout = 'dwindle'
        model.monitors = [dict(name='HEADLESS-1', width=1920, height=1080, refresh=59.94, x=0, y=0, scale=1.5, rr=0, vrr=0)]
        model.binds = [dict(mods='SUPER+ALT', key='b', command='firefox --new-window')]
        model.startup = ['nm-applet --indicator']
        self.assertEqual(S.mango_check(model.render()), '')
        self.assertIn('reject', S.mango_check('bogus_key=1\n'))


class SetAndResetTest(Home):
    def test_set_writes_sources_and_reloads(self):
        before = self.helper('state')
        self.assertEqual(before['options']['gappih']['value'], '8')              # look.conf
        self.assertTrue(before['options']['gappih']['origin'].endswith('look.conf'))
        self.assertFalse(before['options']['gappih']['set'])
        data = self.helper('set', 'gappih=12', 'gappiv=12', 'sloppyfocus=0')
        self.assertEqual(data['options']['gappih']['value'], '12')
        self.assertTrue(data['options']['gappih']['set'])
        self.assertEqual(data['options']['gappih']['arctic'], '8')
        self.assertIn('gappih=12\ngappiv=12\n', self.settings)
        self.assertIn('sloppyfocus=0', self.settings)
        # config.conf now sources settings.conf, just before user.conf
        lines = [l for l in self.config.splitlines() if l.startswith('source')]
        self.assertEqual(lines[-2:], [S.SOURCE_LINE, 'source-optional=~/.config/mango/user.conf'])
        self.assertIn('mmsg dispatch reload_config', self.calls())
        self.assertEqual(data['source'], 'present')     # the repository config already has it

    def test_existing_user_gets_the_source_line_once(self):
        conf = self.home / '.config/mango/config.conf'
        conf.write_text(self.config.replace(S.SOURCE_LINE + '\n', ''))
        self.assertNotIn('settings.conf\n', conf.read_text())
        self.assertEqual(self.helper('set', 'borderpx=3')['source'], 'added')
        self.assertEqual(self.config.count(S.SOURCE_LINE), 1)
        self.assertLess(self.config.index(S.SOURCE_LINE), self.config.index('source-optional=~/.config/mango/user.conf'))
        self.helper('set', 'borderpx=4')
        self.assertEqual(self.config.count(S.SOURCE_LINE), 1)
        backups = list((self.home / '.local/state/arctic/settings-backups').glob('config.conf.*'))
        self.assertEqual(len(backups), 1)

    def test_source_line_appended_without_user_conf_line(self):
        conf = self.home / '.config/mango/config.conf'
        conf.write_text('source=~/.config/mango/arctic/look.conf')      # no final newline
        self.assertEqual(S.ensure_sourced(self.paths), 'added')
        self.assertEqual(conf.read_text(), 'source=~/.config/mango/arctic/look.conf\n' + S.SOURCE_LINE + '\n')
        self.assertEqual(S.ensure_sourced(self.paths), 'present')

    def test_missing_config_is_not_created(self):
        (self.home / '.config/mango/config.conf').unlink()
        self.assertEqual(S.ensure_sourced(self.paths), 'missing')
        self.assertFalse((self.home / '.config/mango/config.conf').exists())

    def test_user_conf_wins_and_is_reported(self):
        (self.home / '.config/mango/user.conf').write_text('borderpx=6\n')
        data = self.helper('set', 'borderpx=3')
        self.assertEqual(data['options']['borderpx']['value'], '6')
        self.assertTrue(data['options']['borderpx']['overridden'])

    def test_bad_values_write_nothing(self):
        for arg in ('gappih=500', 'nope=1', 'gappih', 'xkb_rules_layout=us de'):
            self.helper('set', arg, ok=False)
        self.assertFalse((self.home / '.config/mango/settings.conf').exists())
        self.assertEqual(self.calls(), [])

    def test_reset_and_undo(self):
        self.helper('set', 'gappih=12')
        self.helper('set', 'borderpx=3')
        data = self.helper('reset', 'gappih')
        self.assertNotIn('gappih', self.settings)
        self.assertEqual(data['options']['gappih']['value'], '8')
        self.assertTrue(data['undo'])
        self.helper('undo')
        self.assertIn('gappih=12', self.settings)
        self.helper('undo')
        self.assertNotIn('borderpx', self.settings)

    def test_keyboard_override_clears_installer_variant(self):
        (self.etc / 'mango/keyboard.conf').write_text('xkb_rules_layout=de\nxkb_rules_variant=nodeadkeys\n')
        conf = self.home / '.config/mango/config.conf'
        conf.write_text(conf.read_text().replace('/etc/arctic/mango/keyboard.conf', str(self.etc / 'mango/keyboard.conf')))
        before = self.helper('state')['options']
        self.assertEqual(before['xkb_rules_variant']['value'], 'nodeadkeys')
        data = self.helper('set', 'xkb_rules_layout=us,ru', 'xkb_rules_variant=', 'xkb_rules_options=grp:alt_shift_toggle')
        self.assertIn('xkb_rules_variant= # none\n', self.settings)
        self.assertEqual(data['options']['xkb_rules_variant']['value'], '')
        self.assertEqual(data['options']['xkb_rules_layout']['value'], 'us,ru')
        self.helper('set', 'xkb_rules_layout=us', 'xkb_rules_variant=,phonetic', ok=False)

    def test_default_layout(self):
        self.assertEqual(self.helper('state')['arcticLayout'], 'tile')
        data = self.helper('layout', 'scroller')
        self.assertEqual(data['layout'], 'scroller')
        self.assertIn('tagrule=id:*,layout_name:scroller', self.settings)
        self.helper('layout', 'nonsense', ok=False)
        self.helper('layout', '--reset')
        self.assertNotIn('tagrule', self.settings)

    def test_reduced_motion_stays_in_charge(self):
        (self.home / '.config/arctic/motion.conf').write_text('animations=0\nlayer_animations=0\n')
        data = self.helper('set', 'animation_duration_open=90')
        self.assertEqual(data['options']['animations']['value'], '0')
        self.assertTrue(data['options']['animations']['origin'].endswith('motion.conf'))

    def test_hand_edits_survive(self):
        (self.home / '.config/mango/settings.conf').write_text('env=FOO,bar\ngappih=4\n')
        self.helper('set', 'gappov=20')
        self.assertIn('env=FOO,bar', self.settings)
        self.assertIn('gappih=4', self.settings)

    def test_setting_a_key_drops_its_kept_line(self):
        (self.home / '.config/mango/settings.conf').write_text('borderpx=oops\nenv=FOO,bar\n')
        data = self.helper('set', 'borderpx=3')
        self.assertNotIn('borderpx=oops', self.settings)
        self.assertIn('borderpx=3', self.settings)
        self.assertIn('env=FOO,bar', self.settings)
        self.assertEqual(data['options']['borderpx']['value'], '3')

    def test_first_change_can_be_undone(self):
        self.assertFalse(self.helper('state')['undo'])
        data = self.helper('set', 'gappih=12')
        self.assertTrue(data['undo'])
        self.helper('undo')
        self.assertFalse((self.home / '.config/mango/settings.conf').exists())
        self.assertFalse(self.helper('state')['undo'])
        self.helper('undo', ok=False)

    def test_undo_gives_gtk_the_restored_cursor(self):
        stub(self.bin, 'gsettings', 'echo "gsettings $*" >> "{}"\n'.format(self.log))
        self.helper('set-cursor', 'cursor_size=48')
        self.assertIn('gsettings set org.gnome.desktop.interface cursor-size 48', self.calls())
        restored = self.helper('undo')['options']['cursor_size']['value']
        self.assertEqual(self.calls()[-1], 'gsettings set org.gnome.desktop.interface cursor-size ' + restored)

    def test_parallel_sets_all_land(self):
        # A slow `mango -p` (like the real check) widens the window two writers could overlap in.
        stub(self.bin, 'mango', 'sleep 0.3\n')
        self.env['PATH'] = str(self.bin) + ':/usr/bin:/bin'
        values = ['gappih=12', 'borderpx=7', 'blur=0', 'gappov=20', 'shadows=1']
        procs = [subprocess.Popen([sys.executable, str(HELPER), 'set', v], env=self.env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for v in values]
        for proc in procs:
            out, _err = proc.communicate(timeout=60)
            self.assertTrue(json.loads(out)['ok'], out)
        for value in values:
            self.assertIn(value + '\n', self.settings)
        # Every change left one backup, so undo walks back through all of them.
        backups = sorted((self.tmp / 'home/.local/state/arctic/settings-backups').glob('settings.conf.*'))
        self.assertEqual(len(backups), len(values))


class ShortcutsTest(Home):
    def test_sheet_is_parsed_like_keys_sheet(self):
        data = self.helper('binds')
        titles = [s['title'] for s in data['sheet']]
        self.assertEqual(titles[:2], ['Everyday', 'Windows'])
        self.assertIn(dict(keys='Super + Space', what='Apps (press again to close)'), data['sheet'][0]['rows'])
        close = [b for b in data['all'] if b['action'] == 'killclient']
        self.assertEqual(close[0]['label'], 'Super + Q')
        self.assertEqual(close[0]['what'], 'Close the window')
        launcher = [b for b in data['all'] if b['args'] == 'arctic-launcher']
        self.assertEqual(launcher[0]['label'], 'Super + Space')

    def test_add_and_remove(self):
        data = self.helper('bind-add', 'super+alt', 'B', 'firefox --new-window')
        self.assertEqual(data['mine'][0]['label'], 'Super + Alt + B')
        self.assertIn('keymode=default\nbind=SUPER+ALT,b,spawn_shell,firefox --new-window\n', self.settings)
        self.assertIn('Super + Alt + B', [b['label'] for b in data['all'] if b['mine']])
        self.helper('bind-add', 'SUPER+ALT', 'b', 'foot', ok=False)            # already yours
        data = self.helper('bind-remove', 0)
        self.assertEqual(data['mine'], [])
        self.assertNotIn('bind=', self.settings)

    def test_clashes_and_unsafe_shortcuts_are_refused(self):
        self.assertIn('Close the window', self.helper('bind-add', 'SUPER', 'q', 'foot', ok=False)['error'])
        self.helper('bind-add', 'NONE', 'a', 'foot', ok=False)          # would eat a letter
        self.helper('bind-add', 'SHIFT', 'a', 'foot', ok=False)
        self.helper('bind-add', 'HYPER', 'a', 'foot', ok=False)
        self.helper('bind-add', 'SUPER+ALT', 'a b', 'foot', ok=False)
        self.helper('bind-add', 'SUPER+ALT', 'a', 'echo hi # there', ok=False)
        self.helper('bind-add', 'SUPER+ALT', 'a', 'a,,b', ok=False)
        self.helper('bind-add', 'SUPER+ALT', 'a', '', ok=False)
        self.helper('bind-add', 'NONE', 'F9', 'foot')                   # function keys may go alone


class StartupTest(Home):
    def test_add_remove(self):
        data = self.helper('startup')
        self.assertIn('arctic-session shell', [a['command'] for a in data['arctic']])
        data = self.helper('startup-add', 'syncthing', 'serve')
        self.assertEqual(data['mine'], [dict(index=0, command='syncthing serve')])
        self.assertIn('exec-once=syncthing serve', self.settings)
        self.assertNotIn('mmsg dispatch reload_config', self.calls())    # exec-once runs at login only
        self.helper('startup-add', 'syncthing', 'serve', ok=False)
        self.helper('startup-remove', 0)
        self.assertNotIn('exec-once', self.settings)

    def test_add_app(self):
        (self.data_dirs / 'applications/org.example.Notes.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Notes\nExec=notes --gapplication-service %U\n')
        data = self.helper('startup-add', '--app', 'org.example.Notes')
        self.assertTrue(data['mine'][0]['command'] in ('gtk-launch org.example.Notes', 'notes --gapplication-service'))


class DisplaysTest(Home):
    def setUp(self):
        super().setUp()
        (self.tmp / 'randr.json').write_text(json.dumps(WLR_RANDR_JSON))
        stub(self.bin, 'wlr-randr', '''\
            if [ "$1" = --json ]; then cat "{0}"; exit 0; fi
            echo "wlr-randr $*" >> "{1}"
            '''.format(self.tmp / 'randr.json', self.log))

    def layout(self, **change):
        outputs = self.helper('displays')['outputs']
        for o in outputs:
            o.update(change.get(o['name'], {}))
        return json.dumps(outputs)

    def test_list(self):
        data = self.helper('displays')
        self.assertEqual(data['backend'], 'wlr-randr')
        edp = data['outputs'][0]
        self.assertEqual((edp['width'], edp['height'], edp['refresh'], edp['scale']), (2560, 1600, 60.002, 1.5))
        self.assertEqual((edp['logicalWidth'], edp['logicalHeight']), (1707, 1067))
        self.assertTrue(data['canApply'])

    def test_try_keep(self):
        layout = self.layout(**{'eDP-1': dict(scale=1.25, width=1920, height=1200, refresh=60.0)})
        data = self.helper('display-try', layout)
        self.assertEqual(data['revertAfter'], S.REVERT_AFTER)
        applied = [c for c in self.calls() if c.startswith('wlr-randr')][-1]
        self.assertIn('--output eDP-1 --on --mode 1920x1200@60.000Hz --pos 0,0 --scale 1.25 --transform normal', applied)
        self.assertIn('--output HDMI-A-1 --on --mode 3840x2160@59.997Hz --pos 1707,0 --scale 2', applied)
        self.assertTrue(self.helper('displays')['pending'])
        self.helper('display-keep')
        self.assertIn('monitorrule=name:^eDP-1$,width:1920,height:1200,refresh:60,x:0,y:0,scale:1.25,rr:0,vrr:0', self.settings)
        self.assertIn('monitorrule=name:^HDMI-A-1$,width:3840,height:2160,refresh:59.997,x:1707,y:0,scale:2,rr:0,vrr:0', self.settings)
        self.assertFalse(self.helper('displays')['pending'])
        self.helper('display-keep', ok=False)

    def test_off_is_never_saved(self):
        # A saved disable rule would keep the built-in screen dark even when it is the only one.
        (self.home / '.config/mango/settings.conf').write_text(
            'monitorrule=name:^eDP-1$,width:2560,height:1600,x:0,y:0,scale:1.5,rr:0,vrr:0,disable:1\n')
        self.helper('display-try', self.layout(**{'eDP-1': dict(enabled=False)}))
        applied = [c for c in self.calls() if c.startswith('wlr-randr')][-1]
        self.assertIn('--output eDP-1 --off', applied)
        data = self.helper('display-keep')
        self.assertEqual(data['sessionOnly'], ['eDP-1'])
        self.assertNotIn('disable', self.settings)
        self.assertIn('monitorrule=name:^eDP-1$,width:2560,height:1600', self.settings)
        self.assertIn('monitorrule=name:^HDMI-A-1$', self.settings)

    def test_off_needs_wlr_randr(self):
        (self.bin / 'wlr-randr').unlink()
        stub(self.bin, 'mmsg', '''\
            if [ "$1 $2" = "get all-monitors" ]; then
              echo '{"monitors":[{"name":"eDP-1","x":0,"y":0,"width":1707,"height":1067,"scale":1.5},{"name":"HDMI-A-1","x":1707,"y":0,"width":1920,"height":1080,"scale":2}]}'
            fi
            ''')
        self.helper('display-try', self.layout(**{'eDP-1': dict(enabled=False)}), ok=False)
        self.assertFalse((self.home / '.config/mango/settings.conf').exists())

    def test_try_revert(self):
        self.helper('display-try', self.layout(**{'HDMI-A-1': dict(transform='90')}))
        self.helper('display-revert')
        restored = [c for c in self.calls() if c.startswith('wlr-randr')][-1]
        self.assertIn('--output HDMI-A-1 --on --mode 3840x2160@59.997Hz --pos 1707,0 --scale 2 --transform normal', restored)
        self.assertFalse((self.home / '.config/mango/settings.conf').exists())
        self.helper('display-revert', ok=False)

    def test_watchdog_only_reverts_its_own_change(self):
        token = self.helper('display-try', self.layout())['token']
        self.assertFalse(self.helper('display-revert', '--if-pending', 'other')['reverted'])
        self.assertTrue(self.helper('display-revert', '--if-pending', token)['reverted'])

    def test_unsafe_layouts(self):
        self.helper('display-try', self.layout(**{'eDP-1': dict(enabled=False), 'HDMI-A-1': dict(enabled=False)}), ok=False)
        self.helper('display-try', self.layout(**{'eDP-1': dict(scale=9)}), ok=False)
        self.helper('display-try', self.layout(**{'eDP-1': dict(name='eDP-1;reboot')}), ok=False)
        self.helper('display-try', 'not json', ok=False)
        self.assertEqual([c for c in self.calls() if c.startswith('wlr-randr')], [])

    def test_negative_positions_move_to_zero(self):
        layout = S.check_layout([dict(name='A', width=1920, height=1080, x=-1920, y=-10),
                                 dict(name='B', width=1920, height=1080, x=0, y=0)])
        self.assertEqual([(o['x'], o['y']) for o in layout], [(0, 0), (1920, 10)])


class DefaultAppsTest(Home):
    def setUp(self):
        super().setUp()
        apps = self.data_dirs / 'applications'
        entries = {
            'org.mozilla.firefox': 'Name=Firefox\nExec=firefox %u\nCategories=Network;WebBrowser;\nMimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;',
            'app.zen_browser.zen': 'Name=Zen Browser\nExec=zen %u\nCategories=Network;WebBrowser;\nMimeType=text/html;x-scheme-handler/http;',
            'kitty': 'Name=kitty\nExec=kitty\nCategories=System;TerminalEmulator;',
            'foot': 'Name=Foot\nExec=foot\nCategories=System;TerminalEmulator;',
            'xterm': 'Name=XTerm\nExec=xterm\nCategories=System;TerminalEmulator;',
            'thunar': 'Name=Thunar\nExec=thunar %F\nCategories=System;FileManager;\nMimeType=inode/directory;',
            'nvim': 'Name=Neovim\nExec=nvim %F\nTerminal=true\nCategories=Utility;TextEditor;\nMimeType=text/plain;',
            'vlc': 'Name=VLC\nExec=vlc --started-from-file %U\nCategories=AudioVideo;Player;\nMimeType=video/mp4;video/x-matroska;audio/mpeg;',
            'hidden': 'Name=Hidden\nExec=hidden\nNoDisplay=true\nCategories=WebBrowser;',
        }
        for ident, body in entries.items():
            (apps / (ident + '.desktop')).write_text('[Desktop Entry]\nType=Application\n' + body + '\n')

    def role(self, data, ident):
        return next(r for r in data['roles'] if r['id'] == ident)

    def test_candidates_and_current(self):
        data = self.helper('apps')
        browser = self.role(data, 'browser')
        self.assertEqual([c['id'] for c in browser['candidates']], ['org.mozilla.firefox', 'app.zen_browser.zen'])
        self.assertEqual(browser['current'], 'app.zen_browser.zen')        # /etc/arctic/default-apps
        self.assertFalse(browser['overridden'])
        terminal = self.role(data, 'terminal')
        self.assertEqual([c['id'] for c in terminal['candidates']], ['foot', 'kitty'])   # not xterm (no --hold)
        self.assertEqual(terminal['current'], 'kitty')
        self.assertEqual(self.role(data, 'files')['current'], 'thunar')
        self.assertEqual([c['id'] for c in self.role(data, 'video')['candidates']], ['vlc'])
        self.assertNotIn('pdf', [r['id'] for r in data['roles']])

    def test_set_writes_arctic_open_and_mime_defaults(self):
        data = self.helper('app-set', 'browser', 'org.mozilla.firefox')
        self.assertEqual(self.role(data, 'browser')['current'], 'org.mozilla.firefox')
        self.assertTrue(self.role(data, 'browser')['overridden'])
        self.helper('app-set', 'terminal', 'foot')
        self.helper('app-set', 'editor', 'nvim')
        self.helper('app-set', 'video', 'vlc')
        roles = (self.home / '.config/arctic/default-apps').read_text()
        self.assertIn('browser=gtk-launch org.mozilla.firefox\n', roles)
        self.assertIn('terminal=foot\n', roles)
        self.assertIn('editor=arctic-open terminal -e nvim\n', roles)
        mime = (self.home / '.config/mimeapps.list').read_text()
        self.assertIn('x-scheme-handler/https=org.mozilla.firefox.desktop', mime)
        self.assertIn('video/mp4=vlc.desktop', mime)
        self.assertNotIn('video/webm', mime)                  # VLC didn't say it plays those here
        self.assertNotIn('text/plain', mime)                  # terminal editors don't get MIME types
        self.helper('app-set', 'browser', 'thunar', ok=False)
        self.helper('app-set', 'browser', 'hidden', ok=False)
        self.helper('app-set', 'nothing', 'thunar', ok=False)
        again = self.helper('apps')
        self.assertEqual(self.role(again, 'editor')['current'], 'nvim')
        self.assertEqual(self.role(again, 'terminal')['current'], 'foot')

    def test_arctic_open_uses_the_choice(self):
        self.helper('app-set', 'browser', 'org.mozilla.firefox')
        ran = self.tmp / 'ran.log'
        stub(self.bin, 'setsid', 'shift; echo "$*" >> "{}"\n'.format(ran))       # drop -f, record
        stub(self.bin, 'gtk-launch', 'exit 0\n')
        env = dict(self.env, XDG_DATA_HOME=str(self.home / '.local/share'))
        # arctic-open reads /etc/arctic/default-apps; point it at the test copy.
        script = (DOTFILES / '.local/bin/arctic-open').read_text().replace('/etc/arctic/default-apps', str(self.etc / 'default-apps'))
        opener = self.bin / 'arctic-open-test'
        opener.write_text(script)
        subprocess.run(['bash', str(opener), 'browser'], env=env, check=True, timeout=10)
        self.assertIn('exec gtk-launch org.mozilla.firefox', ran.read_text())


class IdleTest(Home):
    def test_set_and_session_reads_it(self):
        self.helper('idle-set', 600, 0)
        self.assertEqual((self.home / '.config/arctic/idle.conf').read_text().splitlines()[1:], ['lock_after=600', 'suspend_after=0'])
        data = self.helper('idle')
        self.assertEqual((data['lock'], data['suspend']), (600, 0))
        self.helper('idle-set', 900, 300, ok=False)
        self.helper('idle-set', 10, 0, ok=False)
        # arctic-session idle turns the file into swayidle arguments.
        ran = self.tmp / 'swayidle.log'
        stub(self.bin, 'arctic-is-live', 'exit 1\n')
        stub(self.bin, 'pgrep', 'exit 1\n')
        stub(self.bin, 'swayidle', 'echo "$*" >> "{}"\n'.format(ran))
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')
        subprocess.run(['bash', str(DOTFILES / '.local/bin/arctic-session'), 'idle'], env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().strip(), '-w timeout 600 arctic-lock before-sleep arctic-lock')
        (self.home / '.config/arctic/idle.conf').unlink()
        subprocess.run(['bash', str(DOTFILES / '.local/bin/arctic-session'), 'idle'], env=self.env, check=True, timeout=10)
        self.assertEqual(ran.read_text().splitlines()[-1],
                         '-w timeout 300 arctic-lock timeout 900 systemctl suspend before-sleep arctic-lock')


class ThemeTest(Home):
    def test_missing(self):
        data = self.helper('theme')
        self.assertFalse(data['available'])
        self.helper('theme-set', 'winter', ok=False)

    def test_legacy_cli(self):
        stub(self.bin, 'arctic-theme', '''\
            echo "arctic-theme $*" >> "{}"
            case "$1" in "") echo polar-night ;; winter|polar-night) ;; *) exit 2 ;; esac
            '''.format(self.log))
        data = self.helper('theme')
        self.assertEqual((data['modern'], data['current']), (False, 'polar-night'))
        self.helper('theme-set', 'winter')
        self.assertIn('arctic-theme winter', self.calls())
        self.helper('theme-set', 'wallpaper', ok=False)
        self.helper('theme-auto', 'on', ok=False)

    def test_modern_cli(self):
        stub(self.bin, 'arctic-theme', '''\
            echo "arctic-theme $*" >> "{}"
            case "$1 $2" in
              "list --json") echo '[{{"id":"winter","name":"Winter","dark":false}},{{"id":"polar-night","name":"Polar night","dark":true}},{{"id":"wallpaper","name":"From wallpaper"}}]' ;;
              "current --json") echo '{{"theme":"wallpaper","mode":"dark","auto_colors":true}}' ;;
              set*|auto*|mode*) ;;
              *) exit 2 ;;
            esac
            '''.format(self.log))
        data = self.helper('theme')
        self.assertTrue(data['modern'])
        self.assertEqual((data['current'], data['mode'], data['auto']), ('wallpaper', 'dark', True))
        self.assertEqual([t['id'] for t in data['themes']], ['winter', 'polar-night', 'wallpaper'])
        self.helper('theme-set', 'polar-night')
        self.helper('theme-auto', 'off')
        self.helper('theme-mode', 'light')
        self.helper('theme-mode', 'sepia', ok=False)
        self.helper('theme-set', 'x; reboot', ok=False)
        self.assertEqual([c for c in self.calls() if not c.endswith('--json')],
                         ['arctic-theme set polar-night', 'arctic-theme auto off', 'arctic-theme mode light'])


class WallpaperFilesTest(Home):
    """Your own pictures (import, rename, delete) and the Wallhaven browser, through the
    shell's wallpapers.py / wallhaven.py as the app calls them. No network."""

    def setUp(self):
        super().setUp()
        from PIL import Image
        self.pictures = self.home / 'Pictures' / 'Wallpapers'
        self.src = self.tmp / 'Downloads'
        self.src.mkdir()
        Image.new('RGB', (48, 30), (90, 20, 20)).save(self.src / 'Red dunes.jpg')
        (self.src / 'readme.png').write_text('not a picture')
        # Like the real one, it keeps the choice in ~/.config/arctic/wallpaper.
        stub(self.bin, 'arctic-wallpaper', 'echo "arctic-wallpaper $*" >> "{}"\necho "$1" > "$HOME/.config/arctic/wallpaper"\n'.format(self.log))

    def test_import_rename_delete(self):
        data = self.helper('wallpaper-import', 'file://' + str(self.src / 'Red dunes.jpg').replace(' ', '%20'))
        added = Path(data['added'][0])
        self.assertEqual(added, self.pictures / 'Red dunes.jpg')
        self.assertIn(str(added), [i['path'] for i in self.helper('wallpapers')['items']])
        self.helper('wallpaper-import', str(self.src / 'readme.png'), ok=False)
        renamed = Path(self.helper('wallpaper-rename', str(added), 'Dunes at noon')['path'])
        self.assertEqual(renamed.name, 'Dunes at noon.jpg')
        self.helper('wallpaper-rename', str(renamed), '../escape', ok=False)
        self.helper('wallpaper-delete', str(self.src / 'Red dunes.jpg'), ok=False)   # not yours
        self.helper('wallpaper-set', str(renamed))
        self.helper('wallpaper-delete', str(renamed), ok=False)                        # in use
        self.assertIn('arctic-wallpaper ' + str(renamed), self.calls())

    def test_wallhaven_state_and_offline(self):
        state = self.helper('wallhaven', 'state')
        self.assertEqual((state['has_key'], state['prefs']['purity']), (False, '100'))
        self.env.update(https_proxy='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9')
        result = subprocess.run([sys.executable, str(HELPER), 'wallhaven', 'search', '--q', 'snow'], env=self.env,
                                capture_output=True, text=True, timeout=60)
        data = json.loads(result.stdout)
        self.assertEqual((result.returncode, data['ok'], data['offline']), (0, False, True))
        self.helper('wallhaven', 'rm', '-rf', ok=False)


class UpdatesTest(Home):
    def test_missing(self):
        data = self.helper('updates')
        self.assertFalse(data['available'])
        self.assertIn('dnf', data['reason'])
        self.helper('update-run', 'now', ok=False)

    def test_status(self):
        stub(self.bin, 'arctic-update', '''\
            echo "arctic-update $*" >> "{}"
            [ "$1" = status ] && echo '{{"state":"ready","packages":["kernel","mesa"],"download_mb":212.5,"staged_at":"2026-09-27T10:00:00Z","channel":"stable","auto":"on"}}'
            exit 0
            '''.format(self.log))
        data = self.helper('updates')
        self.assertEqual((data['state'], data['count'], data['downloadMb'], data['auto']), ('ready', 2, 212.5, True))
        self.helper('update-run', 'channel', 'testing')
        self.helper('update-run', 'auto', 'off')
        self.helper('update-run', 'channel', 'nightly', ok=False)
        self.assertIn('arctic-update channel testing', self.calls())

    def test_broken_updater(self):
        stub(self.bin, 'arctic-update', 'echo "no such verb" >&2; exit 2\n')
        self.assertFalse(self.helper('updates')['available'])


class NetworkTest(Home):
    def test_status(self):
        stub(self.bin, 'nmcli', r'''
            case "$*" in
              *"device status"*) printf 'wlp2s0:wifi:connected:Caf\\:e 5G\nenp0s31f6:ethernet:unavailable:\nlo:loopback:connected (externally):lo\n' ;;
              "radio wifi") echo enabled ;;
              *"wifi list"*) printf 'yes:Caf\\:e 5G:72\nno:Other:40\n' ;;
            esac
            ''')
        data = self.helper('network')
        self.assertTrue(data['wifi'])
        self.assertEqual(data['devices'][0], dict(device='wlp2s0', type='wifi', state='connected', connection='Caf:e 5G', signal=72))
        self.assertEqual([d['type'] for d in data['devices']], ['wifi', 'ethernet'])

    def test_missing(self):
        self.assertFalse(self.helper('network')['available'])


class PowerProfileTest(Home):
    def test_missing(self):
        self.assertFalse(self.helper('power-profile')['available'])

    def test_tuned_ppd_over_dbus(self):
        state = self.tmp / 'profile'
        state.write_text('balanced')
        stub(self.bin, 'gdbus', '''\
            case "$*" in
              *net.hadess*) exit 1 ;;
              *"Get org.freedesktop.UPower.PowerProfiles ActiveProfile"*) echo "(<'$(cat "{0}")'>,)" ;;
              *"Get org.freedesktop.UPower.PowerProfiles Profiles"*) echo "(<[{{'Profile': <'power-saver'>}}, {{'Profile': <'balanced'>}}]>,)" ;;
              *"Set org.freedesktop.UPower.PowerProfiles ActiveProfile"*) echo "$*" | sed "s/.*<'\\(.*\\)'>.*/\\1/" > "{0}"; echo "()" ;;
              *) exit 1 ;;
            esac
            '''.format(state))
        data = self.helper('power-profile')
        self.assertEqual((data['available'], data['current'], data['profiles']), (True, 'balanced', ['power-saver', 'balanced']))
        self.assertEqual(self.helper('power-profile', 'power-saver')['current'], 'power-saver')
        self.helper('power-profile', 'turbo', ok=False)


class MiscTest(Home):
    def test_about(self):
        data = self.helper('about')
        for key in ('name', 'kernel', 'cpu', 'memory', 'disks', 'gpus', 'wiki', 'issues'):
            self.assertIn(key, data)
        self.assertTrue(data['wiki'].endswith('/wiki'))

    def test_caps(self):
        data = self.helper('caps')
        self.assertTrue(data['mmsg'])
        self.assertFalse(data['arcticUpdate'])

    def test_evdev_lst(self):
        layouts, variants, options = S.parse_evdev_lst(textwrap.dedent('''\
            ! model
              pc105           Generic 105-key PC
            ! layout
              us              English (US)
              de              German
            ! variant
              nodeadkeys      de: German (no dead keys)
              dvorak          us: English (Dvorak)
            ! option
              grp:alt_shift_toggle Alt+Shift
            '''))
        self.assertEqual(layouts, [dict(id='us', label='English (US)'), dict(id='de', label='German')])
        self.assertEqual(variants['de'], [dict(id='nodeadkeys', label='German (no dead keys)')])
        self.assertEqual(options['grp:alt_shift_toggle'], 'Alt+Shift')

    def test_keyboard_data(self):
        data = self.helper('keyboard-data')
        self.assertTrue(data['layouts'])
        self.assertTrue(data['switchKeys'])

    def test_unknown_command(self):
        result = subprocess.run([sys.executable, str(HELPER), 'frobnicate'], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)


if __name__ == '__main__':
    unittest.main()
