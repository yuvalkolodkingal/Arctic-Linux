"""A timeout, login screen or echoed/partial marker cannot qualify a release."""
import importlib.util
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

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


if __name__ == '__main__':
    unittest.main()
