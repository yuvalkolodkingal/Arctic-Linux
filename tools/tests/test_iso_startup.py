"""A timeout, login screen or echoed/partial marker cannot qualify a release."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('iso_startup', ROOT / 'tools/lib/iso_startup.py')
startup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(startup)


class StartupTests(unittest.TestCase):
    def test_only_complete_unique_correct_mode_records_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'serial.log'
            valid = 'ARCTIC-COLLECT-BEGIN\r\nARCTIC-STARTUP-PASS=safe\r\nARCTIC-COLLECT-END\r\n'
            for evidence in ('', 'login screen', valid.replace('safe', 'try'), valid * 2,
                             valid.replace('ARCTIC-COLLECT-END', ''),
                             'warning: ' + valid.replace('\r\n', ' '),
                             valid + 'ARCTIC-STARTUP-FAILED\n',
                             '\n'.join(reversed(valid.splitlines()))):
                path.write_text(evidence)
                self.assertFalse(startup.collection_complete(path, 'safe'), evidence)
            path.write_text(valid)
            self.assertTrue(startup.collection_complete(path, 'safe'))

    def test_guest_command_validates_selected_mode_live_mango_and_selinux(self):
        for mode in ('try', 'install', 'safe'):
            command = startup.collection_command(mode, True)
            subprocess.run(['bash', '-n'], input=command, text=True, check=True)
            subprocess.run(['bash', '-n'], input=shlex.split(command)[-1], text=True, check=True)
            self.assertIn('pgrep -u liveuser -x mango', command)
            self.assertIn('Enforcing', command)
            self.assertIn('rd.live.image', command)
            self.assertIn('arctic.mode=' + ('install' if mode == 'install' else 'try'), command)
            self.assertIn('ARCTIC-STARTUP-PASS=' + mode, command)
        with self.assertRaises(ValueError):
            startup.collection_command('disk', True)

    def test_actual_guest_checks_reject_wrong_mode_missing_mango_and_permissive_selinux(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, body in {'cat': 'exit 0', 'mokutil': 'exit 0', 'systemctl': 'exit 0',
                               'journalctl': 'exit 0', 'flatpak': 'exit 0',
                               'getenforce': 'echo "$TEST_SELINUX"',
                               'pgrep': 'exit "$TEST_MANGO_EXIT"'}.items():
                binary = root / name
                binary.write_text('#!/bin/sh\n' + body + '\n')
                binary.chmod(0o755)
            cmdline, serial = root / 'cmdline', root / 'serial.log'
            command = shlex.split(startup.collection_command('safe', True))[-1]
            command = command.replace('/proc/cmdline', str(cmdline)).replace('/dev/ttyS0', str(serial))
            for kernel, mango, selinux, passes in [
                    ('rd.live.image arctic.mode=try nomodeset', '0', 'Enforcing', True),
                    ('rd.live.image arctic.mode=try', '0', 'Enforcing', False),
                    ('rd.live.image arctic.mode=install nomodeset', '0', 'Enforcing', False),
                    ('arctic.mode=try nomodeset', '0', 'Enforcing', False),
                    ('rd.live.image arctic.mode=try nomodeset', '1', 'Enforcing', False),
                    ('rd.live.image arctic.mode=try nomodeset', '0', 'Permissive', False)]:
                cmdline.write_text(kernel + '\n')
                subprocess.run(['sh', '-c', command], check=True,
                               env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                                    'TEST_MANGO_EXIT': mango, 'TEST_SELINUX': selinux})
                self.assertEqual(startup.collection_complete(serial, 'safe'), passes, serial.read_text())

    def test_every_release_boot_lane_requires_startup(self):
        workflow = (ROOT / '.github/workflows/iso.yml').read_text()
        lanes = [line for line in workflow.splitlines() if 'tools/test-iso.sh ' in line]
        self.assertEqual(len(lanes), 3)
        self.assertTrue(all('--require-startup' in lane for lane in lanes))

    def test_install_collector_preserves_exclusive_focus_installer(self):
        vm = Mock()
        vm.cmd.return_value = {'return': {}}
        with patch.object(startup, 'console_screen', return_value=True):
            startup.collect_session(vm, 'install', True, Mock(), Mock(), sleep=Mock())
        keys = [call.args[0] for call in vm.keys.call_args_list]
        self.assertEqual(keys, ['ret', 'ret'])
        vm.cmd.assert_called_once_with('send-key', keys=[dict(type='qcode',data=key)
            for key in ('ctrl','alt','f3')], **{'hold-time':100})
        self.assertEqual(vm.type_text.call_args_list[0].args[0], 'liveuser')
        command = vm.type_text.call_args_list[1].args[0]
        self.assertIn('call installer state', command)
        self.assertIn('chvt', command)
        self.assertNotIn('meta_l-ret', keys)

    def test_failed_vt_switch_never_types_into_the_graphical_installer(self):
        for error in (True, False):
            vm = Mock()
            vm.cmd.return_value = {'error': {'desc': 'no keyboard'}} if error else {'return': {}}
            with patch.object(startup, 'console_screen', return_value=False), self.assertRaises(RuntimeError):
                startup.collect_session(vm, 'install', True, Mock(), Mock(), sleep=Mock())
            vm.type_text.assert_not_called()
            vm.keys.assert_not_called()

    def test_console_input_guard_refuses_missing_blank_and_graphical_captures(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'console.png'
            self.assertFalse(startup.console_screen(path))
            for color, text, expected in [('#000000',False,False),('#1b232c',True,False),
                                          ('#000000',True,True),('#ffffff',True,False)]:
                image=Image.new('RGB',(1280,800),color)
                if text: ImageDraw.Draw(image).text((0,0),'localhost-live login:',fill='white')
                image.save(path)
                self.assertEqual(startup.console_screen(path),expected)

    def test_actual_installer_probe_rejects_missing_failed_or_unready_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, body in {'id': 'echo 1000', 'runuser': 'printf "%s" "$TEST_STATE"'}.items():
                binary = root / name
                binary.write_text('#!/bin/sh\n' + body + '\n')
                binary.chmod(0o755)
            for state, valid in [
                    ('{"page":"welcome","ready":true,"connected":true,"failure":""}', True),
                    ('', False),
                    ('{"page":"welcome","ready":false,"connected":true,"failure":""}', False),
                    ('{"page":"welcome","ready":true,"connected":false,"failure":""}', False),
                    ('{"page":"welcome","ready":true,"connected":true,"failure":"bridge failed"}', False),
                    ('{"page":"timezone","ready":true,"connected":true,"failure":""}', False)]:
                result = subprocess.run(['sh', '-c', startup.installer_probe()],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                                             'TEST_STATE': state})
                self.assertEqual(result.returncode == 0, valid, state)

    def test_console_restores_only_discovered_live_wayland_vt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = {
                'loginctl': 'case "$1:$2:$4" in list-sessions:*) '
                            'printf "tty 1000 liveuser seat0 tty3\\ngui 1000 liveuser seat0 tty2\\nother 1001 other seat0 tty1\\n";; '
                            'show-session:tty:Type) echo tty;; show-session:gui:Type) echo wayland;; '
                            'show-session:gui:VTNr) echo "$TEST_VT";; *) exit 1;; esac',
                'chvt': 'printf "%s\\n" "$1" >> "$TEST_VT_LOG"; exit "$TEST_VT_EXIT"',
            }
            for name, body in scripts.items():
                binary = root / name
                binary.write_text('#!/bin/sh\n' + body + '\n')
                binary.chmod(0o755)
            log = root / 'vt.log'
            for vt, status, expected in [('2', '0', True), ('2', '1', False),
                                          ('0', '0', False), ('bad', '0', False)]:
                log.write_text('')
                result = subprocess.run(['sh', '-c', startup.restore_desktop()],
                                        env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                                             'TEST_VT': vt, 'TEST_VT_EXIT': status, 'TEST_VT_LOG': str(log)})
                self.assertEqual(result.returncode == 0, expected)
                self.assertEqual(log.read_text(), '2\n' if vt == '2' else '')


if __name__ == '__main__':
    unittest.main()
