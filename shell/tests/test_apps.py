"""Tests for scripts/apps.py and scripts/appslib.py (Get apps and Remove apps).

    python3 -m unittest discover -s shell/tests -p 'test_apps.py'

apps.py runs as the shell runs it (a subprocess printing one JSON line) in a throwaway home,
with stand-ins for flatpak, rpm, dnf5, getent and arctic-webapp that answer from a JSON file.
The dnf5 transactions are the ones shell/tests/test-dnf5-remove.sh captured from the real dnf5.
Standard library only: %check in the RPM build runs this file too.
"""
import gzip
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / 'shell' / 'scripts'
FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'apps'
sys.path.insert(0, str(SCRIPTS))
import appslib  # noqa: E402

# The stand-ins: each reads $FAKE_DATA/fake.json.
FAKE = r'''#!/usr/bin/env python3
import json, os, shutil, sys
data = json.load(open(os.path.join(os.environ['FAKE_DATA'], 'fake.json')))
tool, args = os.path.basename(sys.argv[0]), sys.argv[1:]
with open(os.path.join(os.environ['FAKE_DATA'], 'calls.log'), 'a') as log:
    log.write(tool + ' ' + ' '.join(args) + '\n')
if tool == 'flatpak':
    if args[0] == 'remotes':
        where = args[1][2:]
        print('\n'.join(data.get('remotes', {}).get(where, [])))
    elif args[0] == 'list':
        for row in data.get('flatpaks', []):
            print('\t'.join(row))
    sys.exit(0)
if tool == 'rpm':
    owners, installed = data.get('owners', {}), data.get('installed', {})
    if args[0] == '-qf':
        paths = args[args.index('--') + 1:] if '--' in args else args[3:]
        failed = 0
        for path in paths:
            names = owners.get(path, [])
            if not names:
                failed += 1
                print('file %s is not owned by any package' % path)
            for name in names:
                print('/usr/share/%s/other\t%s' % (name, name))
                print('%s\t%s' % (path, name))
        sys.exit(1 if failed else 0)
    if args[0] == '-qa':
        print('\n'.join(sorted(installed)))
        sys.exit(0)
    if args[0] == '-q':
        fmt, names = args[2], args[3:]
        for name in names:
            if name in installed:
                print('%s\t%s' % (name, installed[name]) if 'SIZE' in fmt else name)
        sys.exit(0)
if tool == 'dnf5':
    if 'repoquery' in args and '--providers-of=requires' in args:
        print('\n'.join(data.get('closure', [])))
    elif 'repoquery' in args:
        names = [a for a in args[args.index('--qf') + 2:]]
        for row in data.get('facts', []):
            if not names or row[0] in names:
                print('\t'.join(row))
    elif args[0] == 'remove':
        store = next(a.split('=', 1)[1] for a in args if a.startswith('--store='))
        names = [a for a in args[1:] if not a.startswith('-')]
        key = ' '.join(names) + (' --no-autoremove' if '--no-autoremove' in args else '')
        if key not in data.get('transactions', {}):
            print('No packages to remove for argument: ' + names[0])
            sys.exit(0)
        os.makedirs(store)
        shutil.copy(data['transactions'][key], os.path.join(store, 'transaction.json'))
    sys.exit(0)
if tool == 'getent':
    print('%s:x:1000:1000::/home/%s:%s' % (args[1], args[1], data.get('shell', '/bin/bash')))
    sys.exit(0)
if tool == 'arctic-webapp':
    print(json.dumps(dict(ok=True, apps=data.get('webapps', []))))
    sys.exit(0)
sys.exit(3)
'''

FEDORA_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<components version="0.16" origin="fedora">
  <component type="desktop-application">
    <id>org.gimp.GIMP</id>
    <pkgname>gimp</pkgname>
    <name>GIMP</name>
    <name xml:lang="de">GIMP (de)</name>
    <summary>Create images and edit photographs</summary>
    <summary xml:lang="de">Bilder</summary>
    <developer_name>The GIMP team</developer_name>
    <project_license>GPL-3.0-or-later</project_license>
    <description><p>GIMP is an <em>image</em> editor.</p><p xml:lang="de">Nein</p><p>Second.</p></description>
    <launchable type="desktop-id">gimp.desktop</launchable>
    <icon type="stock">gimp</icon>
    <icon type="cached" width="64" height="64">gimp_gimp.png</icon>
    <categories><category>Graphics</category></categories>
    <keywords><keyword>photo</keyword><keyword xml:lang="de">foto</keyword></keywords>
    <url type="homepage">https://www.gimp.org/</url>
  </component>
  <component type="console-application">
    <id>ripgrep</id><pkgname>ripgrep</pkgname><name>ripgrep</name><summary>Search</summary>
  </component>
  <component type="desktop-application">
    <id>gone.desktop</id><pkgname>gone</pkgname><name>Gone</name><summary>Not in the repositories</summary>
  </component>
  <component type="desktop-application">
    <id>nopkg</id><name>No package</name>
  </component>
</components>
'''

FLATHUB_XML = '''<?xml version="1.0" encoding="UTF-8"?>
<components version="0.8" origin="flathub">
  <component type="desktop-application">
    <id>org.gimp.GIMP</id>
    <name>GNU Image Manipulation Program</name>
    <summary>High-end image creation and manipulation</summary>
    <icon type="cached" height="128" width="128">org.gimp.GIMP.png</icon>
    <categories><category>Graphics</category></categories>
    <custom><value key="flathub::verification::verified">true</value></custom>
  </component>
  <component type="desktop-application">
    <id>org.example.Plain</id>
    <name>Plain</name>
    <summary>Not verified</summary>
    <icon type="cached" height="64" width="64">org.example.Plain.png</icon>
  </component>
</components>
'''


def desktop(path, **keys):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('[Desktop Entry]\n' + ''.join('{}={}\n'.format(k.replace('_', '-'), v) for k, v in keys.items()))
    return path


class Apps(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.home = self.root / 'home'
        self.bin = self.root / 'bin'
        self.share = self.root / 'usr/share'
        self.flatpak_system = self.root / 'var/lib/flatpak'
        for d in (self.home, self.bin, self.share / 'applications', self.root / 'run'):
            d.mkdir(parents=True, exist_ok=True)
        for tool in ('flatpak', 'rpm', 'dnf5', 'getent', 'arctic-webapp'):
            (self.bin / tool).write_text(FAKE)
            (self.bin / tool).chmod(0o755)
        (self.root / 'mark').mkdir()
        os.utime(self.root / 'mark', (1000, 1000))
        self.data = dict(remotes={'system': ['flathub'], 'user': []}, flatpaks=[], owners={}, installed={},
                         facts=[], closure=[], transactions={}, shell='/bin/bash', webapps=[])
        self.env = dict(
            PATH=str(self.bin) + ':/usr/bin:/bin', HOME=str(self.home), USER='tester', FAKE_DATA=str(self.root),
            XDG_DATA_HOME=str(self.home / '.local/share'), XDG_CONFIG_HOME=str(self.home / '.config'),
            XDG_CACHE_HOME=str(self.home / '.cache'), XDG_RUNTIME_DIR=str(self.root / 'run'),
            XDG_DATA_DIRS=str(self.share) + ':' + str(self.flatpak_system / 'exports/share'),
            ARCTIC_SWCATALOG=str(self.share / 'swcatalog'), ARCTIC_FLATPAK_SYSTEM_DIR=str(self.flatpak_system),
            ARCTIC_RPMDB=str(self.root / 'rpmdb.sqlite'), ARCTIC_INSTALL_MARK=str(self.root / 'mark'),
            ARCTIC_DEFAULT_APPS=str(self.root / 'default-apps'), ARCTIC_PROTECTED_DIR=str(self.root / 'protected.d'),
            ARCTIC_SNAPPER_ROOT=str(self.root / 'snapper-root'), ARCTIC_WHEEL='1')

    def tearDown(self):
        self.tmp.cleanup()

    def run_apps(self, *args, code=0):
        (self.root / 'fake.json').write_text(json.dumps(self.data))
        done = subprocess.run([sys.executable, str(SCRIPTS / 'apps.py'), *args], env=self.env,
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(done.returncode, code, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        if '--tsv' in args:
            return lines
        self.assertEqual(len(lines), 1, done.stdout)
        result = json.loads(lines[0])
        self.assertEqual(result['ok'], code == 0, result)
        if code:
            self.assertIn('error', result)
            self.assertIn('code', result)
        return result

    def dnf_system(self):
        apps = self.share / 'applications'
        desktop(apps / 'gimp.desktop', Name='GIMP', Exec='gimp %U', Icon='gimp', MimeType='image/png;')
        desktop(apps / 'gimp-extra.desktop', Name='GIMP helper', Exec='gimp-helper', NoDisplay='true')
        desktop(apps / 'htop.desktop', Name='Htop', Exec='htop', Terminal='true', Icon='htop')
        desktop(apps / 'hidden-only.desktop', Name='Hidden', Exec='hidden', NoDisplay='true')
        desktop(apps / 'blueman-manager.desktop', Name='Bluetooth Manager', Exec='blueman-manager')
        desktop(apps / 'kitty.desktop', Name='kitty', Exec='kitty')
        desktop(apps / 'unowned.desktop', Name='Unowned', Exec='unowned')
        desktop(apps / 'firefox.desktop', Name='Firefox', Exec='firefox %u')
        desktop(apps / 'zsh-thing.desktop', Name='Z shell', Exec='zsh')
        self.data['owners'] = {str(apps / n): [p] for n, p in [
            ('gimp.desktop', 'gimp'), ('gimp-extra.desktop', 'gimp'), ('htop.desktop', 'htop'),
            ('hidden-only.desktop', 'hidden'), ('blueman-manager.desktop', 'blueman'), ('kitty.desktop', 'kitty'),
            ('firefox.desktop', 'firefox'), ('zsh-thing.desktop', 'zsh')]}
        self.data['facts'] = [
            ['gimp', 'User', 'fedora', '2000', '201326592', '2:3.0.4-1.fc44', 'GNU Image Manipulation Program'],
            ['htop', 'User', 'updates', '500', '400000', '3.4-1.fc44', 'Interactive process viewer'],
            ['hidden', 'User', 'fedora', '2000', '1', '1-1', 'Hidden'],
            ['blueman', 'Dependency', 'fedora', '500', '1', '2-1', 'Bluetooth'],
            ['kitty', 'Weak Dependency', 'fedora', '500', '1', '0.40-1', 'Terminal'],
            ['firefox', 'User', 'fedora', '500', '1', '140-1', 'Browser'],
            ['zsh', 'User', 'fedora', '500', '1', '5.9-1', 'Shell'],
            ['ripgrep', 'User', 'fedora', '3000', '5000000', '14-1', 'Search tool'],
            ['bash', 'User', 'fedora', '500', '1', '5-1', 'Bash'],
            ['arctic-shell', 'User', 'arctic', '3000', '1', '0.3-1', 'Shell'],
        ]
        self.data['closure'] = ['blueman', 'pavucontrol']
        self.data['shell'] = '/bin/zsh'
        self.data['installed'] = {'gimp': 201326592, 'htop': 400000, 'kitty': 1, 'firefox': 1, 'zsh': 1, 'babl': 3145728,
                                  'gimp-data-extras': 1048576, 'arctic-desktop': 1, 'blueman': 1}
        (self.root / 'default-apps').write_text('browser=gtk-launch firefox\nimages=gimp\nterminal=kitty\n')
        self.data['owners']['/bin/zsh'] = ['zsh']
        self.data['owners'][os.path.realpath('/bin/zsh')] = ['zsh']

    def calls(self):
        try:
            return (self.root / 'calls.log').read_text()
        except OSError:
            return ''


class ContractTests(Apps):
    def test_usage_and_unknown_commands_exit_2(self):
        self.run_apps(code=2)
        self.run_apps('nothing', code=2)
        self.run_apps('installed', 'snap', code=2)

    def test_sources(self):
        result = self.run_apps('sources')
        self.assertEqual(result['flatpak'], dict(present=True, flathub=dict(system=True, user=False), install_to='system'))
        self.assertEqual(result['webapp']['present'], True)
        self.assertFalse(result['live'])
        self.assertFalse(result['fedora_catalog']['present'])
        self.env['ARCTIC_WHEEL'] = '0'
        (self.bin / 'arctic-webapp').unlink()
        result = self.run_apps('sources')
        self.assertEqual(result['flatpak']['install_to'], 'user')
        self.assertFalse(result['webapp']['present'])

    def test_protected_lists_the_patterns(self):
        (self.root / 'protected.d').mkdir()
        (self.root / 'protected.d/site.conf').write_text('# ours\nour-agent\n')
        patterns = self.run_apps('protected')['patterns']
        self.assertIn('arctic-*', patterns)
        self.assertEqual(patterns[-1], 'our-agent')


class CatalogTests(Apps):
    def setUp(self):
        super().setUp()
        xml = self.share / 'swcatalog/xml'
        xml.mkdir(parents=True)
        with gzip.open(xml / 'fedora.xml.gz', 'wt') as handle:
            handle.write(FEDORA_XML)
        icons = self.share / 'swcatalog/icons/fedora/64x64'
        icons.mkdir(parents=True)
        (icons / 'gimp_gimp.png').write_bytes(b'png')
        active = self.flatpak_system / 'appstream/flathub' / os.uname().machine / 'active'
        (active / 'icons/128x128').mkdir(parents=True)
        (active / 'icons/64x64').mkdir(parents=True)
        (active / 'icons/128x128/org.gimp.GIMP.png').write_bytes(b'png')
        (active / 'icons/64x64/org.example.Plain.png').write_bytes(b'png')
        with gzip.open(active / 'appstream.xml.gz', 'wt') as handle:
            handle.write(FLATHUB_XML)
        self.active = active

    def test_fedora_apps_with_icons_and_untranslated_text(self):
        result = self.run_apps('catalog', 'fedora')
        self.assertFalse(result['missing'])
        ids = [i['id'] for i in result['items']]
        self.assertEqual(ids, ['org.gimp.GIMP', 'gone'])   # no index yet: nothing filtered
        gimp = result['items'][0]
        self.assertEqual(gimp['name'], 'GIMP')
        self.assertEqual(gimp['pkg'], 'gimp')
        self.assertEqual(gimp['summary'], 'Create images and edit photographs')
        self.assertEqual(gimp['keywords'], ['photo'])
        self.assertEqual(gimp['categories'], ['Graphics'])
        self.assertEqual(gimp['developer'], 'The GIMP team')
        self.assertEqual(gimp['desktop'], 'gimp')
        self.assertEqual(gimp['description'], ['GIMP is an image editor.', 'Second.'])
        self.assertEqual(gimp['icon'], str(self.share / 'swcatalog/icons/fedora/64x64/gimp_gimp.png'))

    def test_fedora_apps_are_filtered_by_the_package_index(self):
        cache = self.home / '.cache/arctic'
        cache.mkdir(parents=True)
        (cache / 'packages.tsv').write_text('gimp\tfedora\tGNU Image Manipulation Program\n')
        self.assertEqual([i['id'] for i in self.run_apps('catalog', 'fedora')['items']], ['org.gimp.GIMP'])

    def test_flathub_verified_flag_and_icons(self):
        items = {i['id']: i for i in self.run_apps('catalog', 'flathub')['items']}
        self.assertTrue(items['org.gimp.GIMP']['verified'])
        self.assertFalse(items['org.example.Plain']['verified'])
        self.assertEqual(items['org.gimp.GIMP']['icon'], str(self.active / 'icons/128x128/org.gimp.GIMP.png'))
        self.assertEqual(items['org.example.Plain']['icon'], str(self.active / 'icons/64x64/org.example.Plain.png'))

    def test_cache_follows_the_file(self):
        self.run_apps('catalog', 'flathub')
        cache = self.home / '.cache/arctic/appstream-flathub.json'
        data = json.loads(cache.read_text())
        data['items'][0]['name'] = 'From the cache'
        cache.write_text(json.dumps(data))
        self.assertIn('From the cache', [i['name'] for i in self.run_apps('catalog', 'flathub')['items']])
        with gzip.open(self.active / 'appstream.xml.gz', 'wt') as handle:
            handle.write(FLATHUB_XML.replace('Plain', 'Changed'))
        os.utime(self.active / 'appstream.xml.gz', (5, 5))
        names = [i['name'] for i in self.run_apps('catalog', 'flathub')['items']]
        self.assertNotIn('From the cache', names)
        self.assertIn('Changed', names)

    def test_missing_files(self):
        shutil.rmtree(self.share / 'swcatalog')
        shutil.rmtree(self.flatpak_system / 'appstream')
        self.assertEqual(self.run_apps('catalog', 'fedora'), dict(ok=True, source='fedora', items=[], missing=True))
        self.assertTrue(self.run_apps('catalog', 'flathub')['missing'])

    def test_tsv_for_the_tour(self):
        path = self.root / 'appstream.xml'
        path.write_text(FLATHUB_XML)
        self.assertEqual(self.run_apps('catalog', 'flathub', '--appstream', str(path), '--tsv'),
                         ['org.gimp.GIMP\tGNU Image Manipulation Program\tHigh-end image creation and manipulation',
                          'org.example.Plain\tPlain\tNot verified'])


class InstalledTests(Apps):
    def test_flatpaks_in_both_installations(self):
        self.data['flatpaks'] = [
            ['org.gimp.GIMP', 'GIMP', '3.0.4', 'flathub', 'system', '412.3 MB'],
            ['org.gimp.GIMP', 'GIMP', '3.0.4', 'flathub', 'user', '412.3 MB'],
            ['not an id', 'x', '', '', 'system', ''],
        ]
        desktop(self.flatpak_system / 'exports/share/applications/org.gimp.GIMP.desktop', Name='GIMP Image Editor',
                Icon='org.gimp.GIMP.Icon', Exec='flatpak run org.gimp.GIMP')
        apps = self.run_apps('installed', 'flatpak')['apps']
        self.assertEqual([(a['id'], a['installation'], a['name']) for a in apps],
                         [('org.gimp.GIMP', 'user', 'GIMP'), ('org.gimp.GIMP', 'system', 'GIMP Image Editor')])
        apps.reverse()
        self.assertEqual(apps[0]['icon'], 'org.gimp.GIMP.Icon')
        self.assertEqual(apps[0]['data_path'], str(self.home / '.var/app/org.gimp.GIMP'))
        self.assertEqual(apps[0]['size_text'], '412.3 MB')

    def test_dnf_apps_are_grouped_per_package(self):
        self.dnf_system()
        result = self.run_apps('installed', 'dnf')
        rows = {r['package']: r for r in result['apps']}
        self.assertEqual(sorted(rows), ['firefox', 'gimp', 'htop', 'kitty'])
        self.assertEqual(rows['gimp']['desktop_ids'], ['gimp'])
        self.assertEqual(rows['gimp']['name'], 'GIMP')
        self.assertEqual(rows['gimp']['repo_label'], 'Fedora')
        self.assertEqual(rows['gimp']['added'], 'you')
        self.assertEqual(rows['htop']['added'], 'arctic')
        self.assertEqual(rows['gimp']['roles'], ['images'])
        self.assertEqual(rows['firefox']['roles'], ['browser'])
        self.assertEqual(rows['kitty']['roles'], ['terminal'])
        self.assertEqual(rows['gimp']['install_bytes'], 201326592)
        protected = {r['package']: r for r in result['protected']}
        self.assertEqual(protected['blueman']['protected_reason'], 'needed-by-desktop')
        self.assertEqual(protected['blueman']['message'], 'The Arctic desktop needs Bluetooth Manager.')
        self.assertEqual(protected['zsh']['protected_reason'], 'login-shell')

    def test_other_packages_you_added(self):
        self.dnf_system()
        rows = self.run_apps('installed', 'dnf', '--other')['apps']
        self.assertEqual([r['package'] for r in rows], ['ripgrep'])   # not arctic-shell (protected)

    def test_the_list_is_cached_until_the_rpm_database_changes(self):
        self.dnf_system()
        db = self.root / 'rpmdb.sqlite'
        db.write_text('')
        os.utime(db, (100, 100))
        self.assertEqual(len(self.run_apps('installed', 'dnf')['apps']), 4)
        (self.root / 'calls.log').unlink()
        self.data['facts'] = [f for f in self.data['facts'] if f[0] != 'htop']
        self.assertEqual(len(self.run_apps('installed', 'dnf')['apps']), 4)   # from the cache
        self.assertNotIn('repoquery --installed', self.calls())
        os.utime(db, (200, 200))
        rows = self.run_apps('installed', 'dnf')['apps']
        self.assertEqual(rows[[r['package'] for r in rows].index('htop')]['summary'], '')   # scanned again
        self.assertIn('repoquery --installed', self.calls())

    def test_added_is_left_out_without_the_install_mark(self):
        self.dnf_system()
        self.env['ARCTIC_INSTALL_MARK'] = str(self.root / 'no-such-mark')
        rows = self.run_apps('installed', 'dnf')['apps']
        self.assertTrue(all('added' not in r for r in rows))

    def test_installed_ids_and_counts(self):
        self.dnf_system()
        self.data['flatpaks'] = [['org.gimp.GIMP', 'GIMP', '3', 'flathub', 'system', '1 MB']]
        self.data['webapps'] = [{'id': 'org.arcticlinux.WebApp.Music_123456', 'name': 'Music'}]
        ids = self.run_apps('installed-ids')
        self.assertEqual(ids['flatpak'], dict(system=['org.gimp.GIMP'], user=[]))
        self.assertIn('gimp', ids['dnf'])
        self.assertEqual(self.run_apps('counts'), dict(ok=True, flatpak=1, dnf=4, web=1, terminal=0))

    def test_desktop_parsing_matches_settings(self):
        self.dnf_system()
        desktop(self.share / 'applications/sub/dir.desktop', Name='Nested', Exec='nested')
        desktop(self.share / 'applications/link.desktop', Type='Link', Name='L', URL='x')
        sys.path.insert(0, str(REPO / 'settings/scripts'))
        import arctic_settings
        paths = arctic_settings.Paths(dict(self.env, XDG_DATA_DIRS=str(self.share)))
        theirs = {k: {f: v[f] for f in ('name', 'exec', 'icon', 'terminal', 'nodisplay', 'categories')}
                  for k, v in arctic_settings.desktop_entries(paths).items() if str(self.share) in v['path']}
        ours = {k: {f: v[f] for f in ('name', 'exec', 'icon', 'terminal', 'nodisplay', 'categories')}
                for k, v in appslib.desktop_entries([self.share / 'applications']).items()}
        self.assertEqual(ours, theirs)
        self.assertIn('sub-dir', ours)


class PreviewTests(Apps):
    def setUp(self):
        super().setUp()
        self.dnf_system()
        self.data['transactions'] = {
            'gimp': str(self.write_transaction('gimp', [('gimp-2:3.0.4-1.fc44.x86_64', 'User'),
                                                        ('gimp-data-extras-1-1.noarch', 'Dependency'),
                                                        ('babl-0.1-1.fc44.x86_64', 'Clean')])),
            'gimp --no-autoremove': str(self.write_transaction('keep', [('gimp-2:3.0.4-1.fc44.x86_64', 'User'),
                                                                        ('gimp-data-extras-1-1.noarch', 'Dependency')])),
            'blueman': str(self.write_transaction('blueman', [('blueman-2-1.noarch', 'User'),
                                                              ('arctic-desktop-0.3-1.noarch', 'Dependency')])),
            'kitty': str(self.write_transaction('kitty', [('kitty-0.40-1.x86_64', 'User')])),
            'zsh': str(self.write_transaction('zsh', [('zsh-5.9-1.x86_64', 'User')])),
            'firefox': str(self.write_transaction('firefox', [('firefox-140-1.x86_64', 'User')])),
            't-app': str(FIXTURES / 'dnf5-remove-app.json'),
            't-lib': str(FIXTURES / 'dnf5-remove-lib.json'),
        }

    def write_transaction(self, name, rpms):
        path = self.root / (name + '.json')
        path.write_text(json.dumps(dict(rpms=[dict(nevra=n, action='Remove', reason=r, repo_id='@System') for n, r in rpms],
                                        version='1.0')))
        return path

    def test_preview_lists_what_goes_and_why(self):
        (self.root / 'rpmdb.sqlite').write_text('')
        result = self.run_apps('preview-remove', 'dnf', 'gimp')
        self.assertEqual([(p['name'], p['why'], p['evr']) for p in result['packages']],
                         [('gimp', 'asked', '2:3.0.4-1.fc44'), ('gimp-data-extras', 'needs-it', '1-1'), ('babl', 'unused', '0.1-1.fc44')])
        self.assertEqual(result['frees_bytes'], 201326592 + 1048576 + 3145728)
        self.assertIsNone(result['blocked'])
        self.assertTrue(result['autoremove'])
        self.assertTrue(result['rpmdb'])
        self.assertFalse(result['undo'])
        self.assertEqual(result['warnings'], [dict(code='default-app', role='images', message=
                         'GIMP opens your pictures. Choose another picture viewer in Settings → Default apps after removing it.')])
        self.assertIn('--store=', self.calls())
        self.assertFalse(list((self.root / 'run/arctic-apps').iterdir()))   # the stored transaction is gone

    def test_no_autoremove(self):
        (self.root / 'snapper-root').write_text('')
        result = self.run_apps('preview-remove', 'dnf', '--no-autoremove', 'gimp')
        self.assertEqual([p['why'] for p in result['packages']], ['asked', 'needs-it'])
        self.assertFalse(result['autoremove'])
        self.assertTrue(result['undo'])

    def test_real_dnf5_transactions(self):
        self.assertEqual([(p['name'], p['why']) for p in self.run_apps('preview-remove', 'dnf', 't-app')['packages']],
                         [('t-app', 'asked'), ('t-lib', 'unused')])
        self.assertEqual([(p['name'], p['why']) for p in self.run_apps('preview-remove', 'dnf', 't-lib')['packages']],
                         [('t-lib', 'asked'), ('t-app', 'needs-it')])

    def test_blocked_removals(self):
        blocked = self.run_apps('preview-remove', 'dnf', 'blueman')['blocked']
        self.assertEqual(blocked['package'], 'arctic-desktop')
        self.assertEqual(blocked['message'], 'Removing blueman would also remove arctic-desktop, which Arctic Linux needs.')
        (self.root / 'calls.log').unlink()
        blocked = self.run_apps('preview-remove', 'dnf', 'arctic-shell')['blocked']
        self.assertEqual(blocked['code'], 'protected')
        self.assertNotIn('--store=', self.calls())   # refused before dnf ran
        blocked = self.run_apps('preview-remove', 'dnf', 'zsh')['blocked']
        self.assertEqual(blocked['code'], 'login-shell')
        self.assertIn('zsh is your login shell', blocked['message'])
        blocked = self.run_apps('preview-remove', 'dnf', 'kitty')['blocked']
        self.assertEqual(blocked['code'], 'only-terminal')
        self.assertIn('kitty is your only terminal', blocked['message'])

    def test_default_browser_warning(self):
        (self.home / '.config/mango/arctic').mkdir(parents=True)
        (self.home / '.config/mango/arctic/apps.conf').write_text('bind=SUPER,b,spawn,arctic-open browser\n')
        warnings = self.run_apps('preview-remove', 'dnf', 'firefox')['warnings']
        self.assertEqual(warnings[0]['message'], 'Firefox opens your web links and Super + B. '
                                                 'Choose another web browser in Settings → Default apps after removing it.')

    def test_not_installed_and_bad_names(self):
        self.assertEqual(self.run_apps('preview-remove', 'dnf', 'nothere', code=1)['code'], 'not-installed')
        self.assertEqual(self.run_apps('preview-remove', 'dnf', '-rf', code=1)['code'], 'invalid')

    def test_flatpak_preview_measures_the_data(self):
        data = self.home / '.var/app/org.gimp.GIMP/config'
        data.mkdir(parents=True)
        (data / 'a').write_bytes(b'x' * 1000)
        result = self.run_apps('preview-remove', 'flatpak', 'org.gimp.GIMP', '--installation', 'user')
        self.assertEqual((result['installation'], result['data_bytes']), ('user', 1000))
        self.run_apps('preview-remove', 'flatpak', '../x', code=1)


class OwnerTests(Apps):
    def owner(self, desktop_id, code=0):
        return self.run_apps('owner', desktop_id, code=code)

    def test_each_source(self):
        mine = self.home / '.local/share/applications'
        desktop(mine / 'org.arcticlinux.WebApp.Music_4c1a9e.desktop', Name='Music', Exec='arctic-webapp run x',
                X_Arctic_WebApp_Id='org.arcticlinux.WebApp.Music_4c1a9e')
        desktop(mine / 'org.arcticlinux.TerminalApp.Float.Btop.desktop', Name='Btop', Exec='arctic-open',
                X_Arctic_TerminalApp_Id='org.arcticlinux.TerminalApp.Float.Btop')
        desktop(self.flatpak_system / 'exports/share/applications/org.gimp.GIMP.desktop', Name='GIMP', Exec='flatpak run org.gimp.GIMP')
        desktop(self.share / 'applications/htop.desktop', Name='Htop', Exec='htop')
        desktop(self.share / 'applications/blueman-manager.desktop', Name='Bluetooth', Exec='blueman-manager')
        desktop(self.share / 'applications/mystery.desktop', Name='Mystery', Exec='mystery')
        desktop(self.share / 'applications/kitty.desktop', Name='kitty', Exec='kitty')
        desktop(mine / 'kitty.desktop', Name='My kitty', Exec='kitty -1')
        desktop(mine / 'mine.desktop', Name='Mine', Exec='mine')
        self.data['owners'] = {str(self.share / 'applications/htop.desktop'): ['htop'],
                               str(self.share / 'applications/blueman-manager.desktop'): ['blueman']}
        self.data['closure'] = ['blueman']
        self.assertEqual(self.owner('org.arcticlinux.WebApp.Music_4c1a9e')['source'], 'webapp')
        self.assertEqual(self.owner('org.arcticlinux.TerminalApp.Float.Btop')['target'], dict(id='org.arcticlinux.TerminalApp.Float.Btop'))
        gimp = self.owner('org.gimp.GIMP')
        self.assertEqual((gimp['source'], gimp['target']), ('flatpak', dict(id='org.gimp.GIMP', installation='system')))
        htop = self.owner('htop')
        self.assertEqual((htop['source'], htop['target'], htop['blocked']), ('dnf', dict(package='htop'), None))
        self.assertEqual(self.owner('blueman-manager')['blocked']['code'], 'needed-by-desktop')
        self.assertEqual(self.owner('mystery')['source'], 'unknown')
        kitty = self.owner('kitty')
        self.assertEqual((kitty['source'], kitty['target']['overrides'], kitty['name']), ('launcher', True, 'My kitty'))
        self.assertFalse(self.owner('mine')['target']['overrides'])
        self.assertEqual(self.owner('nothere', code=1)['code'], 'not-found')
        self.owner('../etc/passwd', code=1)

    def test_launcher_entry_remove_only_removes_your_own(self):
        mine = self.home / '.local/share/applications'
        path = desktop(mine / 'mine.desktop', Name='Mine', Exec='mine')
        desktop(self.share / 'applications/htop.desktop', Name='Htop', Exec='htop')
        self.data['owners'] = {str(self.share / 'applications/htop.desktop'): ['htop']}
        self.run_apps('launcher-entry', 'remove', 'htop', code=1)
        self.run_apps('launcher-entry', 'remove', 'mine')
        self.assertFalse(path.exists())

    def test_a_symlink_out_of_the_folder_is_not_followed(self):
        outside = desktop(self.root / 'elsewhere/evil.desktop', Name='Evil', Exec='evil')
        mine = self.home / '.local/share/applications'
        mine.mkdir(parents=True, exist_ok=True)
        (mine / 'evil.desktop').symlink_to(outside)
        self.owner('evil', code=1)


class TerminalAppTests(Apps):
    def test_add_writes_the_launcher_entry(self):
        (self.bin / 'btop').write_text('#!/bin/sh\n')
        (self.bin / 'btop').chmod(0o755)
        desktop(self.share / 'applications/btop.desktop', Name='btop++', Exec='btop', Icon='btop')
        result = self.run_apps('terminal-app', 'add', '--name', 'Btop', '--command', 'btop --utf-force', '--window', 'float')
        ident = 'org.arcticlinux.TerminalApp.Float.Btop'
        self.assertEqual(result['app']['id'], ident)
        text = Path(result['app']['desktop_file']).read_text()
        self.assertEqual(text, '\n'.join([
            '[Desktop Entry]', 'Type=Application', 'Version=1.5', 'Name=Btop', 'Comment=Terminal app · btop --utf-force',
            'Exec=arctic-open terminal --app-id ' + ident + ' -e btop --utf-force', 'Icon=btop', 'Terminal=false',
            'Categories=System;X-Arctic-TerminalApp;', 'Keywords=terminal;tui;btop;', 'X-Arctic-TerminalApp-Id=' + ident,
            'X-Arctic-TerminalApp-Command=btop --utf-force', 'X-Arctic-TerminalApp-Window=float', '']))
        self.assertEqual(self.run_apps('terminal-app', 'add', '--name', 'Btop', '--command', 'btop', '--window', 'tile', code=1)['code'], 'exists')
        apps = self.run_apps('installed', 'terminal')['apps']
        self.assertEqual([(a['id'], a['command'], a['window']) for a in apps], [(ident, 'btop --utf-force', 'float')])
        self.run_apps('terminal-app', 'remove', ident)
        self.assertEqual(self.run_apps('installed', 'terminal')['apps'], [])

    def test_exec_quoting(self):
        self.assertEqual(appslib.exec_quote('plain'), 'plain')
        self.assertEqual(appslib.exec_quote('two words'), '"two words"')
        self.assertEqual(appslib.exec_quote('say "hi" $HOME `x` \\'), '"say \\"hi\\" \\$HOME \\`x\\` \\\\"')
        self.assertEqual(appslib.exec_quote('100%'), '100%%')
        self.assertEqual(appslib.slug('YouTube Music!'), 'YouTubeMusic')
        self.assertEqual(appslib.slug('2048'), 'App2048')
        self.assertEqual(appslib.slug('???'), 'App')

    def test_refusals(self):
        self.assertEqual(self.run_apps('terminal-app', 'add', '--name', 'a/b', '--command', 'sh', '--window', 'float', code=1)['code'], 'invalid')
        self.assertEqual(self.run_apps('terminal-app', 'add', '--name', 'X', '--command', 'sh\nreboot', '--window', 'float', code=1)['code'], 'invalid')
        missing = self.run_apps('terminal-app', 'add', '--name', 'Nope', '--command', 'no-such-program-x', '--window', 'float', code=1)
        self.assertEqual(missing, dict(ok=False, code='missing', error='no-such-program-x isn’t installed. Install it from Fedora packages first.'))
        self.run_apps('terminal-app', 'remove', 'org.gimp.GIMP', code=1)

    def test_icon_is_resized(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('needs Pillow')
        Image.new('RGB', (40, 20), (255, 0, 0)).save(self.root / 'pic.png')
        result = self.run_apps('terminal-app', 'add', '--name', 'Shell thing', '--command', 'sh -c "echo 1"',
                               '--window', 'tile', '--icon', str(self.root / 'pic.png'))
        ident = 'org.arcticlinux.TerminalApp.Tile.ShellThing'
        self.assertEqual(result['app']['id'], ident)
        with Image.open(self.home / '.local/share/icons/hicolor/256x256/apps' / (ident + '.png')) as icon:
            self.assertEqual(icon.size, (256, 256))
        text = Path(result['app']['desktop_file']).read_text()
        self.assertIn('Icon=' + ident + '\n', text)
        self.assertIn(' -e sh -c "echo 1"\n', text)


class ProtectionTests(unittest.TestCase):
    def test_the_desktop_base_is_protected(self):
        module = tomllib.loads((REPO / 'modules/_system/desktop-base/module.toml').read_text())
        protected = appslib.protection(extra_dir='/nonexistent')
        for install in module['install']:
            for name in install.get('packages', []):
                self.assertTrue(protected.match(name), name)

    def test_weak_dependencies_stay_removable(self):
        protected = appslib.protection(extra_dir='/nonexistent')
        for name in ('kitty', 'zsh', 'Thunar', 'vlc', 'btop', 'gimp', 'pavucontrol', 'blueman'):
            self.assertIsNone(protected.match(name), name)
        with self.assertRaises(ValueError):
            protected.check(['gimp', 'kernel-modules-extra'])

    def test_administrators_add_patterns(self):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, 'site.conf').write_text('corp-*  # our agents\n')
            self.assertEqual(appslib.protection(extra_dir=folder).match('corp-vpn'), 'corp-*')

    def test_role_keys_follow_apps_conf(self):
        keys = appslib.role_keys([REPO / 'dotfiles/.config/mango/arctic/apps.conf'])
        self.assertEqual(keys['terminal'], 'Super + Enter')
        self.assertEqual(keys['editor'], 'Super + E')
        self.assertEqual(keys['files'], 'Super + F')
        self.assertRegex(keys['browser'], r'^Super \+ [A-Z]$')


class JobTests(unittest.TestCase):
    """The commands GUI jobs run (install-terminal.py `run`), exactly."""

    def setUp(self):
        self.protected = appslib.protection(extra_dir='/nonexistent')

    def build(self, **job):
        return appslib.build_job(job, protected=self.protected, user_remotes=job.pop('_remotes', []))

    def test_argv(self):
        self.assertEqual(self.build(kind='install', source='dnf', ids=['gimp']), [['pkexec', '/usr/bin/dnf5', 'install', '-y', 'gimp']])
        self.assertEqual(self.build(kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system', remote='flathub'),
                         [['flatpak', 'install', '--system', '-y', '--noninteractive', 'flathub', 'org.gimp.GIMP']])
        self.assertEqual(self.build(kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='user'),
                         [['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub', appslib.FLATHUB_URL],
                          ['flatpak', 'install', '--user', '-y', '--noninteractive', 'flathub', 'org.gimp.GIMP']])
        self.assertEqual(self.build(kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='user', _remotes=['flathub']),
                         [['flatpak', 'install', '--user', '-y', '--noninteractive', 'flathub', 'org.gimp.GIMP']])
        self.assertEqual(self.build(kind='remove', source='dnf', ids=['gimp'], autoremove=True), [['pkexec', '/usr/bin/dnf5', 'remove', '-y', 'gimp']])
        self.assertEqual(self.build(kind='remove', source='dnf', ids=['gimp'], autoremove=False),
                         [['pkexec', '/usr/bin/dnf5', 'remove', '-y', '--no-autoremove', 'gimp']])
        self.assertEqual(self.build(kind='remove', source='flatpak', ids=['org.gimp.GIMP'], installation='user', delete_data=True, unused=True),
                         [['flatpak', 'uninstall', '--user', '-y', '--noninteractive', '--delete-data', 'org.gimp.GIMP'],
                          ['flatpak', 'uninstall', '--user', '-y', '--noninteractive', '--unused']])
        self.assertEqual(self.build(kind='remove', source='flatpak', ids=['org.gimp.GIMP'], installation='system', unused=False),
                         [['flatpak', 'uninstall', '--system', '-y', '--noninteractive', 'org.gimp.GIMP']])
        self.assertEqual(self.build(kind='add-remote', source='flatpak', remote='flathub', installation='system'),
                         [['flatpak', 'remote-add', '--system', '--if-not-exists', 'flathub', appslib.FLATHUB_URL]])

    def test_refusals(self):
        for job in (dict(kind='install', source='dnf', ids=['-rf']), dict(kind='install', source='dnf', ids=['a b']),
                    dict(kind='install', source='dnf', ids=[]), dict(kind='install', source='dnf', ids='gimp'),
                    dict(kind='install', source='flatpak', ids=['org.gimp']), dict(kind='install', source='flatpak', ids=['../x']),
                    dict(kind='install', source='flatpak', ids=['a b.c.d']),
                    dict(kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='both'),
                    dict(kind='install', source='flatpak', ids=['org.gimp.GIMP'], remote='fedora'),
                    dict(kind='remove', source='dnf', ids=['arctic-shell']), dict(kind='remove', source='dnf', ids=['gimp', 'kernel-core']),
                    dict(kind='install', source='dnf', ids=['p%d' % i for i in range(51)]),
                    dict(kind='reboot', source='dnf', ids=['gimp'])):
            with self.subTest(job), self.assertRaises(ValueError):
                self.build(**job)


class ProgressTests(unittest.TestCase):
    def test_dnf5_counters(self):
        lines = ['Transaction Summary:', '[1/7] Verify package files              100% |   0.0   B/s |   5.0   B |  00m00s',
                 '[3/7] Installing t-tool-0:1-1.noarch    100% |  63.8 KiB/s | 392.0   B |  00m00s']
        self.assertEqual(appslib.progress(lines), dict(percent=42, done=3, total=7, step='Installing t-tool-0:1-1.noarch'))
        self.assertEqual(appslib.progress(['[ 2/12] gimp-3.0.4-1.fc44.x86_64   45% [=====     ] | 3.2 MiB/s']),
                         dict(percent=16, done=2, total=12, step='gimp-3.0.4-1.fc44.x86_64   45% [=====     ]'.split('   45%')[0]))

    def test_flatpak_percent(self):
        self.assertEqual(appslib.progress(['Installing 1/2… ████████▌  45%  1.2 MB/s  00:10']),
                         dict(percent=45, done=None, total=None, step='Installing 1/2'))
        self.assertIsNone(appslib.progress(['', 'Looking for matches…']))

    def test_explain(self):
        job = dict(kind='install', source='dnf', ids=['gimp'])
        self.assertEqual(appslib.explain(job, 0, ''), '')
        self.assertEqual(appslib.explain(job, 126, ''), 'You closed the password prompt. Nothing was installed.')
        self.assertEqual(appslib.explain(dict(job, kind='remove'), 126, ''), 'You closed the password prompt. Nothing was removed.')
        self.assertEqual(appslib.explain(job, 127, ''), 'Arctic Linux couldn’t get permission to make this change. Nothing was changed.')
        self.assertEqual(appslib.explain(job, 1, 'No match for argument: gimp', 'GIMP'),
                         'GIMP isn’t in Fedora’s repositories any more. Try Flathub.')
        self.assertIn('couldn’t be downloaded', appslib.explain(job, 1, 'Curl error (6): Could not resolve host', 'GIMP'))
        self.assertEqual(appslib.explain(job, 1, 'Error', 'GIMP'), 'GIMP wasn’t installed. Show details has what went wrong.')


if __name__ == '__main__':
    unittest.main()
