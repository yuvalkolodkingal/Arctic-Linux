"""Fresh-image roles, existing choices and optional terminal apps use the same launcher."""
import configparser
import shutil
import subprocess
import unittest

from test_arctic_settings import DOTFILES, Home, stub

REPO = DOTFILES.parent
LIVE_ROLES = REPO / 'packaging/desktop/live-default-apps'
LIVE_MIME = REPO / 'packaging/desktop/live-mimeapps.list'


class LiveAppDefaultsTest(Home):
    def setUp(self):
        super().setUp()
        self.ran = self.tmp / 'launched.txt'
        # Restrict command discovery to test stand-ins and the helper's actual utility tools.
        for name in ('grep', 'tail', 'basename', 'sh', 'python3'):
            (self.bin / name).symlink_to(shutil.which(name))
        self.env['PATH'] = str(self.bin)
        self.env['XDG_DATA_HOME'] = str(self.home / '.local/share')
        self.env['XDG_CONFIG_HOME'] = str(self.home / '.config')
        self.env['XDG_CONFIG_DIRS'] = str(self.etc / 'xdg')
        self.env['XDG_CURRENT_DESKTOP'] = 'mango'
        stub(self.bin, 'setsid', 'shift; exec "$@"\n')  # synchronous fake detachment, real command argv
        stub(self.bin, 'notify-send', 'printf "%s\\n" "$@" > "{}"\n'.format(self.ran))
        # Same production body and real configuration paths, except /etc is our owned fixture.
        source = (DOTFILES / '.local/bin/arctic-open').read_text()
        self.opener = self.bin / 'arctic-open'
        self.opener.write_text(source.replace('/etc/arctic/default-apps', str(self.etc / 'default-apps')))
        self.opener.chmod(0o755)
        (self.etc / 'xdg').mkdir()
        shutil.copy(LIVE_MIME, self.etc / 'xdg/mimeapps.list')

    def command(self, name):
        return stub(self.bin, name, 'printf "%s\\n" "{}" "$@" > "{}"\n'.format(name, self.ran))

    def launch(self, role, *args, rc=0):
        self.ran.unlink(missing_ok=True)
        result = subprocess.run(['/usr/bin/bash', str(self.opener), role, *args], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, rc, result.stderr)
        return self.ran.read_text().splitlines() if self.ran.exists() else []

    def live_roles(self):
        shutil.copy(LIVE_ROLES, self.etc / 'default-apps')

    def desktop(self, ident, command, categories, mimes):
        path = self.data_dirs / 'applications' / (ident + '.desktop')
        path.write_text('[Desktop Entry]\nType=Application\nName=' + ident + '\nExec=' + command +
                        '\nCategories=' + categories + ';\nMimeType=' + mimes + ';\n')

    def test_live_roles_launch_selected_apps_even_when_older_apps_are_present(self):
        self.live_roles()
        for name in ('foot', 'epiphany', 'featherpad', 'pcmanfm', 'kitty', 'nautilus', 'zed', 'firefox'):
            self.command(name)
        for role, command in (('terminal', 'foot'), ('browser', 'epiphany'),
                              ('editor', 'featherpad'), ('files', 'pcmanfm')):
            with self.subTest(role=role):
                self.assertEqual(self.launch(role), [command])
        self.assertNotIn('files-tui=', LIVE_ROLES.read_text())
        self.assertNotIn('yazi', LIVE_ROLES.read_text())

    def test_existing_choices_and_user_override_keep_priority(self):
        self.command('gtk-launch')
        for name in ('foot', 'epiphany', 'featherpad', 'pcmanfm', 'kitty', 'nautilus'):
            self.command(name)
        self.desktop('app.zen_browser.zen', 'zen %U', 'WebBrowser', 'text/html')
        self.desktop('dev.zed.Zed', 'zed %F', 'TextEditor', 'text/plain')
        # Home's system fixture is the untouched generic default-apps file.
        self.assertEqual(self.launch('terminal'), ['kitty'])
        self.assertEqual(self.launch('browser'), ['gtk-launch', 'app.zen_browser.zen'])
        self.assertEqual(self.launch('editor'), ['gtk-launch', 'dev.zed.Zed'])
        self.assertEqual(self.launch('files'), ['nautilus'])
        self.live_roles()
        for name in ('custom-terminal', 'custom-browser', 'custom-editor', 'custom-files'):
            self.command(name)
        override = self.home / '.config/arctic/default-apps'
        override.write_text('\n'.join(role + '=custom-' + role for role in ('terminal', 'browser', 'editor', 'files')) + '\n')
        for role in ('terminal', 'browser', 'editor', 'files'):
            self.assertEqual(self.launch(role), ['custom-' + role])
        self.assertEqual(override.read_text().count('=custom-'), 4)  # launching never rewrites user choices

    def test_new_fallbacks_when_configured_app_is_missing(self):
        for name in ('foot', 'epiphany', 'featherpad', 'pcmanfm'):
            self.command(name)
        self.assertEqual(self.launch('browser'), ['epiphany'])
        self.assertEqual(self.launch('editor'), ['featherpad'])
        self.assertEqual(self.launch('files'), ['pcmanfm'])
        self.command('gtk-launch')
        self.desktop('org.gnome.Epiphany', 'epiphany %U', 'WebBrowser', 'text/html')
        (self.bin / 'epiphany').unlink()
        self.assertEqual(self.launch('browser'), ['gtk-launch', 'org.gnome.Epiphany'])

    def test_foot_app_id_hold_and_command_argv(self):
        self.live_roles()
        self.command('foot')
        args = ['--app-id', 'org.arcticlinux.Dropdown', '--hold', '-e',
                'command with spaces', '$(must-not-expand)', ';literal']
        self.assertEqual(self.launch('terminal', *args), ['foot', *args])

    def test_browser_urls_are_literal_for_native_and_desktop_choices(self):
        self.live_roles()
        self.command('epiphany')
        sentinel = self.tmp / 'must-not-exist'
        urls = ['file:///tmp/offline%20page.html', 'https://example.invalid/?q=$(touch ' + str(sentinel) + ')',
                'https://example.invalid/?q=literal;echo bad', 'https://example.invalid/with space']
        self.assertEqual(self.launch('browser', *urls), ['epiphany', *urls])
        self.assertFalse(sentinel.exists())
        self.command('gtk-launch')
        self.desktop('app.zen_browser.zen', 'zen %U', 'WebBrowser', 'text/html')
        (self.home / '.config/arctic/default-apps').write_text('browser=gtk-launch app.zen_browser.zen\n')
        self.assertEqual(self.launch('browser', *urls), ['gtk-launch', 'app.zen_browser.zen', *urls])
        self.assertFalse(sentinel.exists())
        self.assertEqual(self.launch('browser', '--app-id', 'x', rc=2), [])

    def test_missing_optional_tui_notifies_and_installed_tui_remains_available(self):
        self.live_roles()
        self.command('foot')
        notification = self.launch('files-tui', rc=1)
        self.assertIn('No app set for files-tui', notification)
        self.assertIn('Get apps', ' '.join(notification))
        self.command('yazi')
        self.assertEqual(self.launch('files-tui'), ['foot', '-e', 'yazi'])
        (self.bin / 'yazi').unlink()
        self.command('kitty')
        self.command('ranger')
        self.assertEqual(self.launch('files-tui'), ['kitty', '-e', 'ranger'])

    def test_configured_terminal_command_checks_program_and_preserves_quoting(self):
        self.command('foot')
        self.command('featherpad')
        override = self.home / '.config/arctic/default-apps'
        override.write_text('editor=foot -e "my editor" --flag\n')
        self.assertEqual(self.launch('editor'), ['featherpad'])
        self.command('my editor')
        self.assertEqual(self.launch('editor'), ['foot', '-e', 'my editor', '--flag'])
        self.assertEqual(override.read_text(), 'editor=foot -e "my editor" --flag\n')

    def test_settings_reads_live_roles_and_keeps_user_mime_override(self):
        self.live_roles()
        entries = (
            ('foot', 'foot', 'System;TerminalEmulator', ''),
            ('org.gnome.Epiphany', 'epiphany %U', 'Network;WebBrowser', 'text/html;x-scheme-handler/https'),
            ('featherpad', 'featherpad %U', 'Utility;TextEditor', 'text/plain'),
            ('pcmanfm', 'pcmanfm %U', 'System;FileManager', 'inode/directory'),
            ('io.github.celluloid_player.Celluloid', 'celluloid %U', 'AudioVideo;Player', 'video/mp4;audio/mpeg'),
        )
        for entry in entries:
            self.desktop(*entry)
        data = self.helper('apps')
        current = {role['id']: role['current'] for role in data['roles']}
        self.assertEqual({key: current[key] for key in ('terminal', 'browser', 'editor', 'files')},
                         dict(terminal='foot', browser='org.gnome.Epiphany', editor='featherpad', files='pcmanfm'))
        self.desktop('org.mozilla.firefox', 'firefox %U', 'Network;WebBrowser', 'text/html;x-scheme-handler/https')
        self.helper('app-set', 'browser', 'org.mozilla.firefox')
        self.command('gtk-launch')
        self.assertEqual(self.launch('browser'), ['gtk-launch', 'org.mozilla.firefox'])
        mime = (self.home / '.config/mimeapps.list').read_text()
        self.assertIn('x-scheme-handler/https=org.mozilla.firefox.desktop', mime)
        self.assertNotIn('x-scheme-handler/https=org.mozilla.firefox.desktop', LIVE_MIME.read_text())

    @unittest.skipUnless(shutil.which('xdg-mime'), 'xdg-mime not installed')
    def test_system_mime_roles_and_user_override_with_real_xdg_mime(self):
        # Query only; no app or GUI is launched and all configuration directories are owned.
        for ident in ('org.gnome.Epiphany', 'featherpad', 'pcmanfm',
                      'io.github.celluloid_player.Celluloid', 'xarchiver', 'my-browser'):
            self.desktop(ident, '/usr/bin/true %U', 'Utility', '')
        for mime, ident in (('x-scheme-handler/https', 'org.gnome.Epiphany.desktop'),
                            ('text/plain', 'featherpad.desktop'), ('application/json', 'featherpad.desktop'),
                            ('application/toml', 'featherpad.desktop'), ('inode/directory', 'pcmanfm.desktop'),
                            ('video/mp4', 'io.github.celluloid_player.Celluloid.desktop'),
                            ('application/zip', 'xarchiver.desktop')):
            with self.subTest(mime=mime):
                result = subprocess.run([shutil.which('xdg-mime'), 'query', 'default', mime],
                                        env=dict(self.env, PATH='/usr/bin:/bin'), capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), ident)
        (self.home / '.config/mimeapps.list').write_text(
            '[Default Applications]\nx-scheme-handler/https=my-browser.desktop;\n')
        result = subprocess.run([shutil.which('xdg-mime'), 'query', 'default', 'x-scheme-handler/https'],
                                env=dict(self.env, PATH='/usr/bin:/bin'), capture_output=True, text=True, timeout=10)
        self.assertEqual(result.stdout.strip(), 'my-browser.desktop')

    def test_pcmanfm_new_account_config_preserves_mounts_and_disables_autorun(self):
        libfm = configparser.ConfigParser()
        libfm.read(DOTFILES / '.config/libfm/libfm.conf')
        self.assertEqual(dict(libfm['config']), dict(terminal='foot', archiver='xarchiver'))
        terminals = configparser.ConfigParser()
        terminals.read(DOTFILES / '.config/libfm/terminals.list')
        self.assertEqual(dict(terminals['foot']), dict(open_arg='-e', noclose_arg='--hold -e', desktop_id='foot.desktop'))
        pcmanfm = configparser.ConfigParser()
        pcmanfm.read(DOTFILES / '.config/pcmanfm/default/pcmanfm.conf')
        self.assertEqual(dict(pcmanfm['volume']), dict(mount_on_startup='1', mount_removable='1', autorun='0'))
        # A user's own configuration remains byte-identical while defaults are read/roles launched.
        existing = self.home / '.config/libfm/libfm.conf'
        existing.parent.mkdir()
        existing.write_text('[config]\nterminal=my-terminal\narchiver=my-archiver\n')
        self.live_roles()
        self.command('pcmanfm')
        self.launch('files')
        self.assertEqual(existing.read_text(), '[config]\nterminal=my-terminal\narchiver=my-archiver\n')


if __name__ == '__main__':
    unittest.main()
