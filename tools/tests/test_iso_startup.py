"""A timeout, login screen or echoed/partial marker cannot qualify a release."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import socket
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
        with patch.object(startup, 'console_screen', return_value=True), \
                patch.object(startup, 'console_authenticated', return_value=True):
            startup.collect_session(vm, 'install', True, Mock(), Mock(), sleep=Mock(), serial_path='owned.log')
        keys = [call.args[0] for call in vm.keys.call_args_list]
        self.assertEqual(keys, ['ret', 'ret', 'ret', 'ret'])
        vm.cmd.assert_called_once_with('send-key', keys=[dict(type='qcode',data=key)
            for key in ('ctrl','alt','f6')], **{'hold-time':100})
        self.assertEqual(vm.type_text.call_args_list[0].args[0], 'liveuser')
        self.assertIn('ARCTIC-CONSOLE-READY=', vm.type_text.call_args_list[1].args[0])
        command = vm.type_text.call_args_list[2].args[0]
        self.assertIn('call installer state', command)
        self.assertIn('chvt', command)
        self.assertNotIn('meta_l-ret', keys)

    def test_failed_vt_switch_never_types_into_the_graphical_installer(self):
        for error in (True, False):
            vm = Mock()
            vm.cmd.return_value = {'error': {'desc': 'no keyboard'}} if error else {'return': {}}
            with patch.object(startup, 'console_screen', return_value=False), self.assertRaises(RuntimeError):
                startup.collect_session(vm, 'install', True, Mock(), Mock(), sleep=Mock(), serial_path='owned.log')
            vm.type_text.assert_not_called()
            vm.keys.assert_not_called()

    def test_missing_console_authentication_refuses_privileged_collection(self):
        vm = Mock()
        vm.cmd.return_value = {'return': {}}
        with patch.object(startup, 'console_screen', return_value=True), \
                patch.object(startup, 'console_authenticated', return_value=False), \
                self.assertRaisesRegex(RuntimeError, 'authentication'):
            startup.collect_session(vm, 'install', True, Mock(), Mock(), sleep=Mock(), serial_path='owned.log')
        self.assertEqual(len(vm.type_text.call_args_list), 2)
        self.assertNotIn('ARCTIC-COLLECT-BEGIN', vm.type_text.call_args_list[-1].args[0])

    def test_authentication_response_rejects_echoes_wrong_identity_and_replay(self):
        nonce = 'a' * 32
        valid = 'ARCTIC-CONSOLE-READY=' + nonce + ' user=liveuser uid=1000\n'
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'serial.log'
            self.assertFalse(startup.console_authenticated(path, nonce))
            for value in ('', 'echo ' + valid, valid.replace(nonce, 'b' * 32),
                          valid.replace('liveuser', 'root'), valid.replace('1000', '0'),
                          valid.replace('1000', '999'), valid * 2, valid.replace('1000', '2147483648'),
                          'x' * (1024 * 1024 + 1)):
                path.write_text(value)
                self.assertFalse(startup.console_authenticated(path, nonce))
            path.write_text(valid.replace('\n', '\r\n'))
            self.assertTrue(startup.console_authenticated(path, nonce))
            self.assertFalse(startup.console_authenticated(path, 'invalid'))

    def test_actual_console_response_requires_live_user_uid_and_sudo(self):
        nonce = 'a' * 32
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, body in {
                'id': 'case "$*" in -un) echo "$TEST_USER";; "-u liveuser") echo 1000;; -u) echo "$TEST_UID";; *) exit 1;; esac',
                'sudo': '[ "$TEST_SUDO" = yes ] || exit 1; exec "$@"',
            }.items():
                p = root / name
                p.write_text('#!/bin/sh\n' + body + '\n')
                p.chmod(0o755)
            serial = root / 'serial.log'
            command = startup.console_auth_command(nonce).replace('/dev/ttyS0', str(serial))
            subprocess.run(['bash', '-n'], input=command, text=True, check=True)
            for user, uid, sudo, passes in [('liveuser', '1000', 'yes', True),
                    ('root', '0', 'yes', False), ('other', '1000', 'yes', False),
                    ('liveuser', '1001', 'yes', False), ('liveuser', '1000', 'no', False)]:
                serial.unlink(missing_ok=True)
                subprocess.run(['sh', '-c', command], check=False, env={**os.environ,
                    'PATH': str(root) + ':' + os.environ['PATH'], 'TEST_USER': user,
                    'TEST_UID': uid, 'TEST_SUDO': sudo})
                self.assertEqual(startup.console_authenticated(serial, nonce), passes)
            with self.assertRaises(ValueError):
                startup.console_auth_command('invalid')

    def test_console_input_guard_refuses_missing_blank_and_graphical_captures(self):
        from PIL import Image, ImageDraw
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'console.png'
            self.assertFalse(startup.console_screen(path))
            for color, foreground, expected in [('#000000',None,False),
                    ('#1b232c','white',False), ('#000000','white',True),
                    ('#000000','#aaaaaa',True), ('#000000','#888888',False),
                    ('#ffffff','white',False)]:
                image=Image.new('RGB',(1280,800),color)
                if foreground:
                    ImageDraw.Draw(image).text((0,0),'localhost-live login:',fill=foreground)
                image.save(path)
                self.assertEqual(startup.console_screen(path),expected)

    def test_actual_installer_probe_rejects_missing_failed_or_unready_ui(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root/'run/1000'
            runtime.mkdir(parents=True)
            display = socket.socket(socket.AF_UNIX)
            self.addCleanup(display.close)
            display.bind(str(runtime/'wayland-17'))
            mango = socket.socket(socket.AF_UNIX)
            self.addCleanup(mango.close)
            mango.bind(str(runtime/'mango-123.sock'))
            for name, body in {'id': 'echo 1000',
                    'runuser': 'shift 3; exec "$@"',
                    'quickshell': 'test "$WAYLAND_DISPLAY" = wayland-17 && '
                        'test "$XDG_RUNTIME_DIR" = "$TEST_RUNTIME" || exit 1; '
                        'printf "%s" "$TEST_STATE"',
                    'mmsg': 'test "$MANGO_INSTANCE_SIGNATURE" = "$TEST_RUNTIME/mango-123.sock" && '
                        'test "$*" = "get all-layers" || exit 1; '
                        'if [ -n "$TEST_TRANSIENT_FILE" ]; then '
                        'n=$(cat "$TEST_TRANSIENT_FILE" 2>/dev/null || echo 0); n=$((n+1)); '
                        'echo "$n" >"$TEST_TRANSIENT_FILE"; [ "$n" -ge 3 ] || exit 1; fi; '
                        'printf "%s" "$TEST_LAYERS"'}.items():
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
                command = startup.installer_probe().replace('/run/user/',str(root/'run')+'/')
                result = subprocess.run(['sh', '-c', command],
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        env={**os.environ, 'PATH': str(root) + ':' + os.environ['PATH'],
                                             'TEST_STATE': state, 'TEST_RUNTIME':str(runtime),
                                             'WAYLAND_DISPLAY':'wrong-console-display'})
                self.assertEqual(result.returncode == 0, valid, state)
            valid_window = dict(visible=True, backing_visible=True, width=1280,
                                height=800, screen='Virtual-1')
            layer = dict(name='arctic-installer',layer='top',monitor='Virtual-1')
            valid_layers = json.dumps(dict(layers=[layer]))
            for window, valid in [(valid_window,True), ({},False),
                    ({**valid_window,'visible':False},False),
                    ({**valid_window,'backing_visible':False},False),
                    ({**valid_window,'width':100},False),
                    ({**valid_window,'height':100},False),
                    ({**valid_window,'screen':''},False)]:
                state=json.dumps(dict(page='welcome',ready=True,connected=True,
                                      failure='',window=window))
                command=startup.installer_probe(require_visible=True).replace(
                    '/run/user/',str(root/'run')+'/')
                result=subprocess.run(['sh','-c',command],stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,env={**os.environ,'PATH':str(root)+':'+os.environ['PATH'],
                    'TEST_STATE':state,'TEST_RUNTIME':str(runtime),'WAYLAND_DISPLAY':'wrong-console-display',
                    'TEST_LAYERS':valid_layers})
                self.assertEqual(result.returncode==0,valid,state)
            state=json.dumps(dict(page='welcome',ready=True,connected=True,failure='',window=valid_window))
            env={**os.environ,'PATH':str(root)+':'+os.environ['PATH'],'TEST_STATE':state,
                 'TEST_RUNTIME':str(runtime),'WAYLAND_DISPLAY':'wrong-console-display',
                 'MANGO_INSTANCE_SIGNATURE':'wrong-console-compositor'}
            for layers, valid in [(valid_layers,True), ('',False), ('{}',False),
                    (json.dumps(dict(layers=[])),False),
                    (json.dumps(dict(layers=[layer,layer])),False),
                    (json.dumps(dict(layers=[dict(layer,layer='bottom')])),False),
                    (json.dumps(dict(layers=[dict(layer,monitor='Virtual-2')])),False)]:
                result=subprocess.run(['sh','-c',command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      env=dict(env,TEST_LAYERS=layers))
                self.assertEqual(result.returncode==0,valid,layers)
                if valid:
                    self.assertTrue(result.stdout.startswith(b'ARCTIC-INSTALLER-WINDOW='))
            deadline = startup.installer_restoration_probe().replace('/run/user/',str(root/'run')+'/')
            counter=root/'retries'
            (root/'sleep').write_text('#!/bin/sh\nexit 0\n')
            (root/'sleep').chmod(0o755)
            result=subprocess.run(['sh','-c',deadline],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                env=dict(env,TEST_LAYERS=valid_layers,TEST_TRANSIENT_FILE=str(counter)),timeout=5)
            self.assertEqual(result.returncode,0,result.stderr.decode())
            self.assertEqual(counter.read_text().strip(),'3')
            self.assertTrue(result.stdout.startswith(b'ARCTIC-INSTALLER-WINDOW='))
            (root/'sleep').unlink()
            deadline=startup.installer_restoration_probe(1).replace('/run/user/',str(root/'run')+'/')
            result=subprocess.run(['sh','-c',deadline],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                  env=dict(env,TEST_LAYERS='{}'),timeout=5)
            self.assertEqual(result.returncode,124)
            self.assertNotIn(b'ARCTIC-INSTALLER-WINDOW=',result.stdout)
            for bad in (0,26,True,'25'):
                with self.assertRaises(ValueError):
                    startup.installer_restoration_probe(bad)
            # Missing, regular, or ambiguous compositor sockets cannot select
            # an unrelated inherited instance or become successful evidence.
            mango.close()
            (runtime/'mango-123.sock').unlink()
            for extra in (False,True):
                (runtime/'mango-123.sock').touch()
                if extra:
                    peers=[]
                    for name in ('mango-4.sock','mango-9.sock'):
                        peer=socket.socket(socket.AF_UNIX);peers.append(peer);self.addCleanup(peer.close)
                        peer.bind(str(runtime/name))
                result=subprocess.run(['sh','-c',command],stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      env=dict(env,TEST_LAYERS=valid_layers))
                self.assertNotEqual(result.returncode,0)

    def test_installer_probe_requires_one_actual_wayland_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root/'run/1000'
            runtime.mkdir(parents=True)
            for name, body in {'id':'echo 1000',
                    'runuser':'touch "$TEST_CALLED"; exit 1'}.items():
                binary=root/name
                binary.write_text('#!/bin/sh\n'+body+'\n')
                binary.chmod(0o755)
            called=root/'called'
            command=startup.installer_probe().replace('/run/user/',str(root/'run')+'/')
            env={**os.environ,'PATH':str(root)+':'+os.environ['PATH'],'TEST_CALLED':str(called)}
            # A regular file and lock file cannot impersonate a Wayland socket.
            (runtime/'wayland-0').touch()
            (runtime/'wayland-0.lock').touch()
            result=subprocess.run(['sh','-c',command],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(called.exists())
            sockets=[]
            for name in ('wayland-3','wayland-9'):
                display=socket.socket(socket.AF_UNIX)
                sockets.append(display)
                self.addCleanup(display.close)
                display.bind(str(runtime/name))
            result=subprocess.run(['sh','-c',command],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode,0)
            self.assertFalse(called.exists())

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
