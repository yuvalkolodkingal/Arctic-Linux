"""Regression for the installed-VM probe's post-exec compositor environment."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('nix_guest', Path(__file__).parents[1]/'nix-acceptance/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class NixFootIdentityTest(unittest.TestCase):
    """A native Foot/old Nix Foot with identical app IDs must never qualify."""
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.store = self.root / 'nix/store'
        self.output = self.store / ('a' * 32 + '-foot-1.27.0')
        self.binary = self.output / 'bin/foot'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'\x7fELFfixture')
        self.binary.chmod(0o755)
        self.entry = self.output / 'share/applications/foot.desktop'
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text('[Desktop Entry]\nType=Application\nName=Foot\n'
                              f'Exec={self.binary}\nIcon=foot\n')
        self.icon = self.output / 'share/icons/hicolor/48x48/apps/foot.png'
        self.icon.parent.mkdir(parents=True)
        self.icon.write_bytes(b'fixture PNG')
        self.generations = [self.root / f'profile-{i}' for i in range(1, 4)]
        for i, generation in enumerate(self.generations):
            (generation / 'bin').mkdir(parents=True)
            (generation / 'share').mkdir()
            if i != 1:
                (generation / 'bin/foot').symlink_to(self.binary)
                (generation / 'share/applications').symlink_to(self.entry.parent)
                (generation / 'share/icons').symlink_to(self.output / 'share/icons')
        self.profile = self.root / 'home/.local/state/nix/profiles/arctic'
        self.profile.parent.mkdir(parents=True)
        self.profile.symlink_to(self.generations[0])
        self.native = self.root / 'usr/bin/foot'
        self.native.parent.mkdir(parents=True)
        self.native.write_bytes(b'\x7fELFnative')
        self.native.chmod(0o755)
        self.native_entry = self.root / 'usr/share/applications/foot.desktop'
        self.native_entry.parent.mkdir(parents=True)
        self.native_entry.write_text('[Desktop Entry]\nExec=foot\nIcon=foot\n')
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.uid = os.getuid()
        import pwd
        self.prefix = ['runuser', '-u', pwd.getpwuid(self.uid).pw_name, '--', 'env']
        self.store_patch = patch.object(guest, 'NIX_STORE', self.store)
        self.store_patch.start()
        self.addCleanup(self.store_patch.stop)

    def export(self):
        with patch.object(guest, 'user_executable', return_value=str(self.binary)), \
                patch.object(guest, 'user_desktop_file', return_value=str(self.entry)):
            return guest.nix_foot_export(self.prefix, self.profile)

    def selected(self):
        data = guest.configparser.ConfigParser(interpolation=None)
        data.read(self.entry)
        command = data['Desktop Entry']['Exec']
        return dict(id='foot', execString=command, command=guest.shlex.split(command),
                    icon='foot', iconPath='image://icon/foot', iconReady=True, iconPresent=True)

    def process(self, pid=42, ticks=100, executable=None, state='S'):
        folder = self.proc / str(pid)
        folder.mkdir(exist_ok=True)
        # proc stat field22 is starttime; comm can itself contain parentheses.
        fields = [state] + ['0'] * 18 + [str(ticks)]
        (folder / 'stat').write_text(f'{pid} (foot (terminal)) ' + ' '.join(fields))
        (folder / 'exe').unlink(missing_ok=True)
        (folder / 'exe').symlink_to(executable or self.binary)
        return folder

    def client(self, pid=42, **changes):
        return dict(id=7, appid='foot', title='Foot', pid=pid, is_xwayland=False,
                    is_visible=True, width=800, height=600, **changes)

    def test_private_profile_export_selected_command_icon_and_user_path_are_proven(self):
        export = self.export()
        self.assertEqual(export['executable'], str(self.binary))
        self.assertEqual(export['desktop_file'], str(self.entry))
        self.assertEqual(guest.nix_desktop_entry(self.selected(), export), self.selected())
        with patch.object(guest, 'run', return_value='"' + str(self.binary) + '"') as run:
            self.assertEqual(guest.user_executable(self.prefix, 'foot'), str(self.binary))
        self.assertEqual(run.call_args.args[0][:len(self.prefix)], self.prefix)
        self.assertEqual(run.call_args.args[0][-1], 'foot')

    def test_native_path_or_native_same_id_entry_is_not_private_nix_evidence(self):
        with patch.object(guest, 'user_executable', return_value=str(self.native)):
            with self.assertRaisesRegex(RuntimeError, 'PATH'):
                guest.nix_foot_export(self.prefix, self.profile)
        export = self.export()
        selected = self.selected() | dict(execString='foot', command=['foot'])
        with self.assertRaisesRegex(RuntimeError, 'different/native'):
            guest.nix_desktop_entry(selected, export)
        for changes in (dict(command=[str(self.native)]), dict(iconPath=str(self.native)),
                        dict(iconReady=False), dict(iconPresent=False), dict(command='foot')):
            with self.subTest(changes=changes), self.assertRaises((RuntimeError, OSError)):
                guest.nix_desktop_entry(self.selected() | changes, export)

    def test_profile_native_symlink_broken_export_or_wrong_desktop_exec_is_rejected(self):
        link = self.profile / 'bin/foot'
        link.unlink()
        link.symlink_to(self.native)
        with self.assertRaisesRegex(RuntimeError, 'Not a Nix-store'):
            self.export()
        link.unlink()
        link.symlink_to(self.binary)
        self.entry.write_text('[Desktop Entry]\nExec=some-other-foot\nIcon=foot\n')
        with self.assertRaisesRegex(RuntimeError, 'desktop export'):
            self.export()
        self.entry.unlink()
        with self.assertRaises(FileNotFoundError):
            self.export()

    def test_upstream_bare_exec_requires_both_private_path_and_xdg_precedence(self):
        self.entry.write_text('[Desktop Entry]\nExec=foot\nIcon=foot\n')
        export = self.export()
        self.assertEqual(guest.nix_desktop_entry(self.selected(), export)['command'], ['foot'])
        with patch.object(guest, 'user_executable', return_value=str(self.native)), \
                patch.object(guest, 'user_desktop_file', return_value=str(self.entry)):
            with self.assertRaisesRegex(RuntimeError, 'PATH'):
                guest.nix_foot_export(self.prefix, self.profile)
        with patch.object(guest, 'user_executable', return_value=str(self.binary)), \
                patch.object(guest, 'user_desktop_file', return_value=str(self.native_entry)):
            with self.assertRaisesRegex(RuntimeError, 'XDG precedence'):
                guest.nix_foot_export(self.prefix, self.profile)

    def test_fresh_private_nix_elf_window_and_exact_output_wrapper_are_accepted(self):
        self.process()
        proof = guest.nix_window_identity(self.client(), set(), self.binary, self.uid, self.proc)
        self.assertEqual(proof, dict(pid=42, start_ticks=100, executable=str(self.binary)))
        wrapped = self.binary.with_name('.foot-wrapped')
        wrapped.write_bytes(b'\x7fELFwrapped')
        self.process(executable=wrapped)
        self.assertEqual(guest.nix_window_identity(self.client(), set(), self.binary,
                         self.uid, self.proc)['executable'], str(wrapped))

    def test_native_different_store_old_process_and_recycled_pid_are_distinguished(self):
        for executable in (self.native, self.store / ('b' * 32 + '-foot-2.0') / 'bin/foot'):
            if not executable.exists():
                executable.parent.mkdir(parents=True)
                executable.write_bytes(b'\x7fELFother')
            self.process(executable=executable)
            with self.subTest(executable=executable), self.assertRaisesRegex(RuntimeError, 'different/native'):
                guest.nix_window_identity(self.client(), set(), self.binary, self.uid, self.proc)
        self.process()
        before = guest.process_snapshot(self.proc, self.uid)
        with self.assertRaisesRegex(RuntimeError, 'stale/pre-existing'):
            guest.nix_window_identity(self.client(), before, self.binary, self.uid, self.proc)
        self.process(ticks=101)
        self.assertEqual(guest.nix_window_identity(self.client(), before, self.binary,
                         self.uid, self.proc)['start_ticks'], 101)

    def test_dead_missing_wrong_uid_xwayland_unmapped_and_non_elf_are_rejected(self):
        self.process()
        for changes in (dict(pid=None), dict(pid=True), dict(is_xwayland=True),
                        dict(is_visible=False), dict(width=0)):
            with self.subTest(changes=changes), self.assertRaisesRegex(RuntimeError, 'native Wayland PID'):
                guest.nix_window_identity(self.client() | changes, set(), self.binary, self.uid, self.proc)
        with self.assertRaisesRegex(RuntimeError, 'owned'):
            guest.nix_window_identity(self.client(), set(), self.binary, self.uid + 1, self.proc)
        self.process(state='Z')
        with self.assertRaisesRegex(RuntimeError, 'live process'):
            guest.nix_window_identity(self.client(), set(), self.binary, self.uid, self.proc)
        self.process()
        self.binary.write_text('#!/bin/sh\n')
        with self.assertRaisesRegex(RuntimeError, 'Nix ELF'):
            guest.nix_window_identity(self.client(), set(), self.binary, self.uid, self.proc)

    def test_mapped_window_keeps_exact_pid_identity_and_only_owned_test_process_is_closed(self):
        child = Mock()
        child.poll.return_value = 0
        def launch(*args, **kwargs):
            self.process()
            return child
        with patch.object(guest.subprocess, 'Popen', side_effect=launch), \
                patch.object(guest, 'clients', side_effect=[{}, {'7': self.client()}, {'7': self.client()}]), \
                patch.object(guest.time, 'sleep'), patch.object(guest.os, 'kill') as kill:
            self.assertIn('start_ticks', guest.app(self.prefix, ['foot'], 'foot',
                          expected_executable=self.binary, proc_root=self.proc))
        kill.assert_called_once_with(42, guest.signal.SIGTERM)
        def recycle(seconds):
            self.process(ticks=102)
        with patch.object(guest.subprocess, 'Popen', side_effect=launch), \
                patch.object(guest, 'clients', side_effect=[{}, {'7': self.client()}, {'7': self.client()}]), \
                patch.object(guest.time, 'sleep', side_effect=recycle), patch.object(guest.os, 'kill') as kill:
            # Snapshot sees100, so use a new PID/start incarnation at launch.
            self.process(ticks=99)
            with self.assertRaisesRegex(RuntimeError, 'changed PID/start'):
                guest.app(self.prefix, ['foot'], 'foot', expected_executable=self.binary, proc_root=self.proc)
        kill.assert_not_called()

    def test_native_window_cannot_pass_desktop_launcher_even_with_old_nix_process_alive(self):
        self.process(pid=41)
        child = Mock()
        child.poll.return_value = 0
        def launch(*args, **kwargs):
            self.process(executable=self.native)
            return child
        with patch.object(guest.subprocess, 'Popen', side_effect=launch), \
                patch.object(guest, 'clients', side_effect=[{}, {'7': self.client()}]), \
                patch.object(guest.os, 'kill') as kill:
            with self.assertRaisesRegex(RuntimeError, 'different/native'):
                guest.app(self.prefix, ['quickshell', 'ipc', 'launch'], 'foot',
                          expected_executable=self.binary, proc_root=self.proc)
        kill.assert_not_called()

    def test_offline_cached_add_remove_rollback_refreshes_exports_and_restores_generation(self):
        export = self.export()
        calls, index, epoch = [], 0, 0
        def resolver(prefix, name):
            return str(self.binary if (self.profile / 'bin/foot').exists() else self.native)
        def selected():
            return self.selected() if (self.profile / 'bin/foot').exists() else \
                dict(id='foot', execString='foot', command=['foot'])
        def desktop_file(prefix, name):
            return str(self.entry if (self.profile / 'bin/foot').exists() else self.native_entry)
        def run(argv, **kwargs):
            nonlocal index, epoch
            calls.append(argv)
            if 'profile' not in argv:
                self.assertIn('nixlib.refresh_desktop()', argv[-1])
                epoch += 1
                return ''
            self.assertIn('--offline', argv)
            action = argv[argv.index('profile') + 1]
            if action == 'list':
                return '{"elements":{"foot":{"storePaths":["' + str(self.output) + '"]}}}'
            index += {'remove': 1, 'add': 1, 'rollback': -1}[action]
            self.profile.unlink()
            self.profile.symlink_to(self.generations[index])
            if action == 'add':
                self.assertEqual(argv[-1], str(self.output))
                self.assertNotIn('github:', ' '.join(argv))
            return ''
        with patch.object(guest, 'run', side_effect=run), \
                patch.object(guest, 'user_executable', side_effect=resolver), \
                patch.object(guest, 'user_desktop_file', side_effect=desktop_file), \
                patch.object(guest, 'nix_foot_app', return_value='proven Nix window') as app:
            result = guest.offline_foot_cycle(self.prefix, self.profile, export, selected, lambda: epoch)
        self.assertEqual(str(self.profile.resolve()), str(self.generations[0]))
        self.assertEqual(result['removed_selected_entry']['execString'], 'foot')
        self.assertIn('no flake evaluation', result['mode'])
        app.assert_called_once_with(self.prefix, self.profile)
        self.assertEqual(len(calls), 9)  # list + four offline ops + four installed refreshes
        self.assertEqual(epoch, 4)

    def test_stale_hot_model_epoch_never_qualifies_a_profile_refresh(self):
        with patch.object(guest.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'hot rescan'):
                guest.wait_desktop_rescan(lambda: 3, 3)
            with self.assertRaisesRegex(RuntimeError, 'epoch is unavailable'):
                guest.wait_desktop_rescan(lambda: 3, None)
        self.assertEqual(guest.wait_desktop_rescan(lambda: 4, 3), 4)


class SessionEnvironmentTest(unittest.TestCase):
    def test_reads_child_signature_and_rejects_missing_or_ambiguous_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = Path('/run/user')/str(os.getuid())
            def child(pid, display, signature):
                folder = root/str(pid)
                folder.mkdir()
                (folder/'environ').write_bytes(('WAYLAND_DISPLAY='+display+'\0XDG_RUNTIME_DIR='+str(runtime)+'\0MANGO_INSTANCE_SIGNATURE='+signature+'\0').encode())
            with self.assertRaisesRegex(RuntimeError, 'found 0'):
                guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {})
            child(10, 'wayland-0', '/run/user/test/mango.sock')
            child(11, 'wayland-1', '/run/user/test/other.sock')
            self.assertEqual(guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {}), '/run/user/test/mango.sock')
            child(12, 'wayland-0', '/run/user/test/ambiguous.sock')
            with self.assertRaisesRegex(RuntimeError, 'found 2'):
                    guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {})


class ConfiguredBrowserTest(unittest.TestCase):
    def test_system_and_user_choices_select_the_actual_supported_browser(self):
        with tempfile.TemporaryDirectory() as directory:
            system, user = Path(directory) / 'system', Path(directory) / 'user'
            system.write_text('browser=gtk-launch app.zen_browser.zen\n')
            self.assertEqual(guest.configured_browser([system, user]), 'zen')
            user.write_text('browser=gtk-launch org.gnome.Epiphany\n')
            self.assertEqual(guest.configured_browser([system, user]), 'epiphany')
            user.write_text('browser=firefox\n')
            self.assertEqual(guest.configured_browser([system, user]), 'firefox')
            user.write_text('browser=chromium-browser\n')
            with self.assertRaisesRegex(RuntimeError, 'non-Chromium'):
                guest.configured_browser([system, user])
            with self.assertRaisesRegex(RuntimeError, 'non-Chromium'):
                guest.configured_browser([])

    def test_handlers_must_match_the_configured_browser_for_every_web_mime_type(self):
        prefix = ['runuser', '-u', 'desktop', '--']
        with patch.object(guest, 'run', return_value='org.gnome.Epiphany.desktop') as run:
            self.assertEqual(len(guest.browser_handlers(prefix, 'epiphany')), 4)
        self.assertTrue(all(call.args[0][:len(prefix)] == prefix for call in run.call_args_list))
        with patch.object(guest, 'run', side_effect=['org.gnome.Epiphany.desktop'] * 3 + ['app.zen_browser.zen.desktop']):
            with self.assertRaisesRegex(RuntimeError, 'HTML/HTTP/HTTPS handlers'):
                guest.browser_handlers(prefix, 'epiphany')

    def test_configured_offline_page_requires_its_title_visible_window_and_full_ui_proof(self):
        import pwd
        prefix = ['runuser', '-u', pwd.getpwuid(os.getuid()).pw_name, '--']
        fixture = dict(uri='file:///home/desktop/.cache/browser.html', title='unique local JS ready')
        proof = dict(pid=42, start_ticks=100, executable='/usr/bin/epiphany')
        client = dict(pid=42, appid='org.gnome.Epiphany', title=fixture['title'],
                      is_xwayland=False, is_visible=True, width=800, height=600)
        with patch.object(guest, 'browser_choice', return_value='epiphany'), \
                patch.object(guest, 'offline_browser_fixture', return_value=fixture), \
                patch.object(guest, 'browser_handlers', return_value={'text/html': 'org.gnome.Epiphany.desktop'}), \
                patch.object(guest, 'process_snapshot', return_value=set()), \
                patch.object(guest, 'user_executable', return_value='/usr/bin/epiphany'), \
                patch.object(guest, 'process_identity', return_value=proof), \
                patch.object(guest, 'run', return_value='epiphany version'), \
                patch.object(guest, 'app', return_value='mapped') as app, \
                patch.object(guest.time, 'sleep'), \
                patch.object(guest, 'webkit_sandbox', return_value=['verified']) as sandbox, \
                patch.object(guest, 'clients', side_effect=[{}, {'7': client}]):
            value = guest.browser(prefix)
        self.assertEqual(app.call_args.args[1], ['/usr/bin/arctic-open', 'browser', fixture['uri']])
        sandbox.assert_called_once_with(proof, os.getuid())
        self.assertEqual(value['ui_process'], proof)
        for change in (dict(title='old welcome page'), dict(is_visible=False), dict(width=0),
                       dict(is_xwayland=True), dict(pid=True)):
            with self.subTest(change=change), \
                    patch.object(guest, 'browser_choice', return_value='epiphany'), \
                    patch.object(guest, 'offline_browser_fixture', return_value=fixture), \
                    patch.object(guest, 'browser_handlers', return_value={}), \
                    patch.object(guest, 'process_snapshot', return_value=set()), \
                    patch.object(guest, 'user_executable', return_value='/usr/bin/epiphany'), \
                    patch.object(guest, 'run', return_value='epiphany version'), \
                    patch.object(guest, 'app', return_value='mapped'), \
                    patch.object(guest.time, 'sleep'), \
                    patch.object(guest, 'clients', side_effect=[{}, {'7': client | change}]), \
                    self.assertRaisesRegex(RuntimeError, 'identifiable native Wayland window'):
                guest.browser(prefix)


class ArchiveToolsTest(unittest.TestCase):
    def test_required_helpers_resolve_in_actual_desktop_user_environment(self):
        prefix = ['runuser', '-u', 'desktop', '--', 'env']
        def resolve(user_prefix, command):
            self.assertEqual(user_prefix, prefix)
            return '/usr/bin/' + command if command != '7z' else None
        with patch.object(guest, 'user_executable', side_effect=resolve):
            value = guest.archive_tools(prefix)
        self.assertEqual(value['executables']['7zip'], '/usr/bin/7zz')
        self.assertEqual(set(value['executables']), {'7zip', 'zip', 'unzip', 'tar', 'xz', 'bzip2', 'zstd', 'cpio'})
        self.assertIn('no archive-format roundtrip', value['scope'])

    def test_missing_zip_never_passes_when_other_archive_helpers_are_available(self):
        with patch.object(guest, 'user_executable', side_effect=lambda prefix, name:
                          None if name == 'zip' else '/usr/bin/' + name):
            with self.assertRaisesRegex(RuntimeError, 'PATH: zip'):
                guest.archive_tools(['desktop'])


class WebKitSandboxTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.binary = self.root / 'usr/libexec/webkitgtk-6.0/WebKitWebProcess'
        self.binary.parent.mkdir(parents=True)
        self.binary.write_bytes(b'\x7fELF')
        self.proc = self.root / 'proc'
        self.proc.mkdir()
        self.uid = os.getuid()
        self.patch = patch.object(guest, 'WEBKIT_WEB_PROCESS', self.binary)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.ui_binary = self.root / 'epiphany'
        self.ui_binary.write_bytes(b'\x7fELF')
        self.process(40, 1, namespaces=('mnt:[1]', 'pid:[1]'), executable=self.ui_binary)
        self.ui_proof = guest.process_identity(self.proc / '40', self.uid)

    def process(self, pid=42, parent=40, seccomp='2', privileges='1',
                namespaces=('mnt:[2]', 'pid:[2]'), env=b'', executable=None):
        folder = self.proc / str(pid)
        folder.mkdir(exist_ok=True)
        (folder / 'stat').write_text(f'{pid} (WebKitWebProcess) S {parent} ' + '0 ' * 17 + '100')
        (folder / 'status').write_text(f'Seccomp:\t{seccomp}\nNoNewPrivs:\t{privileges}\n')
        (folder / 'environ').write_bytes(env)
        (folder / 'exe').unlink(missing_ok=True)
        (folder / 'exe').symlink_to(executable or self.binary)
        (folder / 'ns').mkdir(exist_ok=True)
        for name, target in zip(('mnt', 'pid'), namespaces):
            (folder / 'ns' / name).unlink(missing_ok=True)
            (folder / 'ns' / name).symlink_to(target)
        return folder

    def test_verified_browser_descendant_with_sandbox_filters_namespaces_is_accepted(self):
        self.process(pid=41, executable=self.root / 'bubblewrap')
        self.process(parent=41)
        value = guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)
        self.assertEqual(value[0]['pid'], 42)
        self.assertEqual(value[0]['descendant_of'], 40)
        self.assertEqual(value[0]['seccomp'], 2)
        self.assertEqual(value[0]['no_new_privs'], 1)

    def test_unrelated_old_webkit_or_wrong_engine_output_cannot_provide_sandbox_evidence(self):
        self.process(parent=1)
        with self.assertRaisesRegex(RuntimeError, 'No verified descendant'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)
        other = self.root / 'webkitgtk-4.1/WebKitWebProcess'
        other.parent.mkdir()
        other.write_bytes(b'\x7fELF')
        self.process(executable=other)
        with self.assertRaisesRegex(RuntimeError, 'No verified descendant'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)

    def test_missing_filters_privileges_or_namespace_is_fail_closed(self):
        for changes in (dict(seccomp='0'), dict(seccomp=''), dict(privileges='0'),
                        dict(namespaces=('mnt:[1]', 'pid:[2]')),
                        dict(namespaces=('mnt:[2]', 'pid:[1]'))):
            with self.subTest(changes=changes):
                self.process(**changes)
                with self.assertRaisesRegex(RuntimeError, 'Seccomp|namespace'):
                    guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)
        folder = self.process()
        (folder / 'ns/pid').unlink()
        with self.assertRaisesRegex(RuntimeError, 'No verified descendant'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)

    def test_sandbox_disable_environment_wrong_user_or_cyclic_parent_chain_is_rejected(self):
        self.process(env=b'WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=1\0')
        with self.assertRaisesRegex(RuntimeError, 'sandbox-disabling'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)
        self.process()
        with self.assertRaisesRegex(RuntimeError, 'owned'):
            guest.webkit_sandbox(self.ui_proof, self.uid + 1, self.proc)
        self.process(parent=42)
        with self.assertRaisesRegex(RuntimeError, 'No verified descendant'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)

    def test_ui_recycled_before_or_during_sandbox_scan_never_supplies_browser_evidence(self):
        self.process()
        stat = self.proc / '40/stat'
        original = stat.read_text()
        stat.write_text(original.replace('100', '200'))
        with self.assertRaisesRegex(RuntimeError, 'before sandbox inspection'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)
        stat.write_text(original)
        other = self.root / 'ArcticWebApp'
        other.write_bytes(b'\x7fELF')
        (self.proc / '40/exe').unlink()
        (self.proc / '40/exe').symlink_to(other)
        with self.assertRaisesRegex(RuntimeError, 'before sandbox inspection'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)
        (self.proc / '40/exe').unlink()
        (self.proc / '40/exe').symlink_to(self.ui_binary)
        def recycle(*args):
            stat.write_text(original.replace('100', '200'))
            return True
        with patch.object(guest, 'process_descends_from', side_effect=recycle):
            with self.assertRaisesRegex(RuntimeError, 'during sandbox inspection'):
                guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)

    def test_ui_sandbox_disable_environment_is_rejected_even_if_renderer_environment_was_filtered(self):
        self.process()
        (self.proc / '40/environ').write_bytes(b'WEBKIT_DISABLE_SANDBOX_THIS_IS_DANGEROUS=0\0')
        with self.assertRaisesRegex(RuntimeError, 'sandbox-disabling'):
            guest.webkit_sandbox(self.ui_proof, self.uid, self.proc)


class NixSocketDefaultsTest(unittest.TestCase):
    def test_socket_must_be_enabled_and_active_with_eager_service_disabled(self):
        with patch.object(guest, 'run', side_effect=['enabled', 'disabled', 'active']) as run:
            self.assertIn('eager service disabled', guest.nix_socket_defaults())
        self.assertEqual(run.call_count, 3)
        for states in (['disabled', 'disabled'], ['enabled', 'enabled'],
                       ['enabled', 'disabled', 'inactive'],
                       ['enabled', 'disabled', RuntimeError('inactive')]):
            with self.subTest(states=states), patch.object(guest, 'run', side_effect=states):
                with self.assertRaises(RuntimeError):
                    guest.nix_socket_defaults()


class NixAVCIntervalTest(unittest.TestCase):
    def test_historical_denials_are_excluded_but_new_nix_and_foot_denials_fail(self):
        before = 'old avc: denied comm="nix-daemon"\n'
        with patch.object(guest, 'run', return_value=before + 'normal activity\n'):
            self.assertIn('no matching new', guest.no_new_nix_avc(before))
        for denial in ('avc: denied { connectto } comm="nix"',
                       'AVC: DENIED { execute } comm="Foot"'):
            with self.subTest(denial=denial), patch.object(guest, 'run', return_value=before + denial):
                with self.assertRaisesRegex(RuntimeError, 'New Nix/Foot AVC'):
                    guest.no_new_nix_avc(before)

    def test_changed_journal_prefix_is_checked_conservatively_and_read_errors_fail(self):
        for outcome in ('avc: denied comm="nix-daemon"', RuntimeError('journal unavailable')):
            with self.subTest(outcome=outcome), patch.object(guest, 'run', side_effect=[outcome]):
                with self.assertRaises(RuntimeError):
                    guest.no_new_nix_avc('prior journal\n')


class OnlinePreflightTest(unittest.TestCase):
    prefix = ['runuser', '-u', 'ci', '--', 'env', 'HOME=/home/ci']

    def test_direct_dns_and_https_use_the_guest_user_and_bounded_verified_requests(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                guest, 'run', side_effect=['1.2.3.4 STREAM', '5.6.7.8 STREAM', '200', '200']) as run:
            result = guest.online_preflight(self.prefix)
        self.assertEqual(result['dns_mode'], 'direct')
        self.assertEqual(result['dns_hosts'], ['api.github.com', 'cache.nixos.org'])
        for call in run.call_args_list:
            self.assertEqual(call.args[0][:len(self.prefix)], self.prefix)
        for call in run.call_args_list[2:]:
            args = call.args[0]
            self.assertIn('--fail', args)
            self.assertNotIn('--insecure', args)
            self.assertEqual(args[args.index('--max-time') + 1], '30')
            self.assertEqual(call.kwargs['timeout'], 40)

    def test_dns_failure_stops_before_https_and_empty_dns_is_rejected(self):
        for outcome in (RuntimeError('Could not resolve host'), ''):
            with self.subTest(outcome=outcome), patch.dict(os.environ, {}, clear=True), \
                    patch.object(guest, 'run', side_effect=[outcome]) as run:
                with self.assertRaisesRegex(RuntimeError, 'resolve|DNS'):
                    guest.online_preflight(self.prefix)
                self.assertEqual(run.call_count, 1)

    def test_tls_or_http_failure_is_not_accepted_as_connectivity(self):
        for outcome in (RuntimeError('TLS verification failed'), '403'):
            with self.subTest(outcome=outcome), patch.dict(os.environ, {}, clear=True), \
                    patch.object(guest, 'run', side_effect=['address', 'address', outcome]) as run:
                with self.assertRaisesRegex(RuntimeError, 'TLS|HTTP'):
                    guest.online_preflight(self.prefix)
                self.assertEqual(run.call_count, 3)

    def test_supported_proxy_checks_proxy_dns_and_keeps_upstream_tls_verification(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://10.0.2.2:18080'}, clear=True), \
                patch.object(guest, 'run', side_effect=['10.0.2.2 STREAM', '200', '200']) as run:
            result = guest.online_preflight(self.prefix)
        self.assertEqual(result['dns_mode'], 'proxy')
        self.assertEqual(result['dns_hosts'], ['10.0.2.2'])
        self.assertEqual(run.call_args_list[0].args[0], self.prefix + ['getent', 'ahosts', '10.0.2.2'])
        self.assertEqual(result['verified_https'],
                         ['https://api.github.com/', 'https://cache.nixos.org/nix-cache-info'])


class RpmSignatureTest(unittest.TestCase):
    def test_rpm6_lowercase_signature_is_accepted_for_every_file(self):
        files = ['/packages/arctic.rpm', '/packages/fedora.rpm']
        output = '\n'.join(filename + ':\n    Header OpenPGP V4 RSA/SHA256 signature, key fingerprint: abc: OK\n    Header SHA256 digest: OK\n    Payload SHA256 digest: OK' for filename in files)
        with patch.object(guest, 'run', return_value=output):
            self.assertEqual(guest.verified_rpm_signatures(files), output)

    def test_unsigned_or_missing_second_rpm_is_rejected_despite_digest_ok(self):
        files = ['/packages/arctic.rpm', '/packages/unsigned.rpm']
        good = files[0] + ':\n    Header OpenPGP V4 RSA/SHA256 signature: OK\n'
        for output in (good, good + files[1] + ':\n    Header SHA256 digest: OK\n    Payload SHA256 digest: OK'):
            with self.subTest(output=output), patch.object(guest, 'run', return_value=output):
                with self.assertRaisesRegex(RuntimeError, 'No valid signature'):
                    guest.verified_rpm_signatures(files)

    def test_untrusted_or_bad_signature_is_rejected(self):
        for result in ('NOKEY', 'BAD', 'NOT OK'):
            output = '/packages/arctic.rpm:\n    Header OpenPGP V4 RSA/SHA256 Signature: ' + result
            with self.subTest(result=result), patch.object(guest, 'run', return_value=output):
                with self.assertRaisesRegex(RuntimeError, 'No valid signature'):
                    guest.verified_rpm_signatures(['/packages/arctic.rpm'])


class OfflineHistoryTest(unittest.TestCase):
    def test_selects_latest_listed_positive_index(self):
        first = 'a' * 32
        latest = 'b' * 32
        listing = ('The following boots appear to contain offline transaction logs:\n'
                   f'1 / {first}: 2026-10-06 00:00:00 44→44\n'
                   f'2 / {latest}: 2026-10-06 02:00:00 44→44')
        with patch.object(guest, 'run', side_effect=[listing, 'actual journal']) as run:
            self.assertEqual(guest.latest_offline_history(),
                             dict(listing=listing, number=2, boot_id=latest, log='actual journal'))
        self.assertEqual(run.call_args_list[-1].args[0],
                         ['dnf5', 'offline', 'log', '--number=2'])

    def test_absent_history_is_rejected(self):
        with patch.object(guest, 'run', return_value='No logs were found.') as run:
            with self.assertRaisesRegex(RuntimeError, 'No listed offline transaction boot'):
                guest.latest_offline_history()
        self.assertEqual(run.call_count, 1)

    def test_latest_history_command_failure_is_retained(self):
        listing = '1 / ' + 'c' * 32 + ': 2026-10-06 02:00:00 44→44'
        with patch.object(guest, 'run', side_effect=[listing, RuntimeError('journal missing')]):
            with self.assertRaisesRegex(RuntimeError, 'journal missing'):
                guest.latest_offline_history()
