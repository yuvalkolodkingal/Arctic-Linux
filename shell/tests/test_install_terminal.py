import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import termios
import time
import unittest

spec = importlib.util.spec_from_file_location('install_terminal', Path(__file__).parents[1]/'scripts/install-terminal.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CommandTests(unittest.TestCase):
    """What each typed line runs: dnf through pkexec, Flathub through flatpak, never a shell.
    Changes never wait for a [y/N]: they get -y unless the line answers already."""

    def test_bare_names_install_with_dnf(self):
        self.assertEqual(module.build_command('neovim htop'), ['pkexec', '/usr/bin/dnf5', 'install', '-y', 'neovim', 'htop'])

    def test_flathub_ids_install_with_flatpak(self):
        self.assertEqual(module.build_command('flathub:org.gimp.GIMP'), ['flatpak', 'install', '-y', 'flathub', 'org.gimp.GIMP'])

    def test_mixed_sources_are_refused(self):
        with self.assertRaises(ValueError):
            module.build_command('neovim flathub:org.gimp.GIMP')

    def test_dnf_changes_need_pkexec_and_queries_do_not(self):
        self.assertEqual(module.build_command('dnf install -y fish'), ['pkexec', '/usr/bin/dnf5', 'install', '-y', 'fish'])
        self.assertEqual(module.build_command('sudo dnf remove fish'), ['pkexec', '/usr/bin/dnf5', 'remove', '-y', 'fish'])
        self.assertEqual(module.build_command('dnf upgrade'), ['pkexec', '/usr/bin/dnf5', 'upgrade', '-y'])
        self.assertEqual(module.build_command('dnf --refresh upgrade --assumeno'), ['pkexec', '/usr/bin/dnf5', '--refresh', 'upgrade', '--assumeno'])
        self.assertEqual(module.build_command('dnf search editor'), ['dnf', 'search', 'editor'])
        self.assertEqual(module.build_command('dnf info neovim'), ['dnf', 'info', 'neovim'])

    def test_flatpak_commands_run_as_typed(self):
        self.assertEqual(module.build_command('flatpak install flathub org.gimp.GIMP'),
                         ['flatpak', 'install', '-y', 'flathub', 'org.gimp.GIMP'])
        self.assertEqual(module.build_command('flatpak --user uninstall --noninteractive org.gimp.GIMP'),
                         ['flatpak', '--user', 'uninstall', '--noninteractive', 'org.gimp.GIMP'])
        self.assertEqual(module.build_command('flatpak search gimp'), ['flatpak', 'search', 'gimp'])

    def test_other_commands_and_shell_syntax_are_refused(self):
        for text in ('rm -rf ~', 'curl example.com | sh', '$(reboot)', 'neovim; reboot', '-y neovim', '', 'dnf', 'flatpak', 'a\nb'):
            with self.assertRaises(ValueError, msg=text):
                module.build_command(text)


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.console = module.Console()

    def tearDown(self):
        if self.console.pid:
            os.kill(self.console.pid, signal.SIGKILL)
            os.waitpid(self.console.pid, 0)
            os.close(self.console.master)

    def wait_for(self, condition):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            self.console.read()
            if condition():
                return
            time.sleep(0.01)
        self.fail('PTY did not reach expected state')

    def snapshot(self):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.console.emit()
        return json.loads(stream.getvalue())

    def test_password_is_not_echoed_and_confirmation_works(self):
        program = '''import getpass
secret = getpass.getpass('Password: ')
print('Authenticated' if secret == 'test-secret-739' else 'Rejected', flush=True)
answer = input('Continue? [Yes/No] ')
print('Confirmed ' + answer, flush=True)
'''
        self.console.start('authentication test', [sys.executable, '-c', program])
        self.wait_for(lambda: self.console.secret)
        self.console.input('test-secret-739', True)
        self.wait_for(lambda: not self.console.secret and 'Continue?' in self.snapshot()['output'])
        self.console.input('Yes', False)
        self.wait_for(lambda: self.console.pid is None)
        output = self.snapshot()['output']
        self.assertNotIn('test-secret-739', output)
        self.assertIn('Authenticated', output)
        self.assertIn('Confirmed Yes', output)
        self.assertIn('Done.', output)

    def lflag(self):
        return termios.tcgetattr(self.console.master)[3]

    def test_sudo_use_pty_confirmation_is_not_a_password(self):
        # What sudo does on Fedora 44 (use_pty is the default since sudo 1.9.14): it asks for
        # the password with echo off in canonical mode, then puts this terminal in raw mode
        # (echo off too) while the command runs in a PTY of its own, where dnf asks [y/N].
        program = '''import getpass, os, tty
password = getpass.getpass(os.environ['SUDO_PROMPT'].replace('%p', getpass.getuser()))
print('Authenticated' if password == 'test-secret-739' else 'Rejected', flush=True)
tty.setraw(0)
os.write(1, b'Is this ok [y/N]: ')
answer = b''
while not answer.endswith((b'\\n', b'\\r')):
    answer += os.read(0, 1)
os.write(1, b'\\r\\nConfirmed ' + answer.strip() + b'\\r\\n')
'''
        self.console.start('sudo dnf install test', [sys.executable, '-c', program])
        self.wait_for(lambda: self.console.secret)
        self.assertIn('[sudo] password for ', self.snapshot()['output'])
        self.console.input('test-secret-739', True)
        self.wait_for(lambda: 'Is this ok' in self.snapshot()['output'])
        self.assertFalse(self.lflag() & (termios.ECHO | termios.ICANON))   # raw, as under sudo
        self.console.read()
        self.assertFalse(self.console.secret)
        self.console.input('y', False)
        self.assertEqual(self.console.notice, '')
        self.wait_for(lambda: self.console.pid is None)
        output = self.snapshot()['output']
        self.assertNotIn('test-secret-739', output)
        self.assertIn('Authenticated', output)
        self.assertIn('Confirmed y', output)

    def test_sudo_password_read_without_canonical_mode_is_secret(self):
        # sudoers' pwfeedback makes sudo read the password with canonical mode off as well;
        # its prompt still marks it as a password.
        program = '''import getpass, os, termios
attrs = termios.tcgetattr(0)
attrs[3] &= ~(termios.ECHO | termios.ICANON)
termios.tcsetattr(0, termios.TCSANOW, attrs)
os.write(1, os.environ['SUDO_PROMPT'].replace('%p', getpass.getuser()).encode())
password = b''
while not password.endswith((b'\\n', b'\\r')):
    password += os.read(0, 1)
os.write(1, b'\\r\\n' + (b'Authenticated' if password.strip() == b'test-secret-739' else b'Rejected') + b'\\r\\n')
'''
        self.console.start('pwfeedback test', [sys.executable, '-c', program])
        self.wait_for(lambda: self.console.secret)
        self.console.input('test-secret-739', True)
        self.wait_for(lambda: self.console.pid is None)
        output = self.snapshot()['output']
        self.assertNotIn('test-secret-739', output)
        self.assertIn('Authenticated', output)

    @unittest.skipUnless(shutil.which('sudo') and subprocess.run(['sudo', '-n', 'true'], capture_output=True).returncode == 0,
                         'needs sudo without a password')
    def test_real_sudo_confirmation_is_not_a_password(self):
        self.console.start('sudo test', ['sudo', '-n', sys.executable, '-c', "print('Confirmed ' + input('Is this ok [y/N]: '))"])
        self.wait_for(lambda: 'Is this ok' in self.snapshot()['output'])
        self.console.read()
        self.assertFalse(self.console.secret)
        self.console.input('y', False)
        self.assertEqual(self.console.notice, '')
        self.wait_for(lambda: self.console.pid is None)
        self.assertIn('Confirmed y', self.snapshot()['output'])

    def test_stale_secret_input_is_rejected(self):
        self.console.start('prompt test', [sys.executable, '-c', "print(input('Answer: '))"])
        self.wait_for(lambda: 'Answer:' in self.snapshot()['output'])
        self.console.input('do-not-echo', True)
        self.assertIn('prompt changed', self.console.notice)
        self.assertNotIn('do-not-echo', self.snapshot()['output'])
        self.console.input('safe', False)
        self.wait_for(lambda: self.console.pid is None)

    def test_interrupt_and_exit_status(self):
        self.console.start('interrupt test', [sys.executable, '-c', "import time; print('Ready', flush=True); time.sleep(60)"])
        self.wait_for(lambda: 'Ready' in self.snapshot()['output'])
        self.console.interrupt()
        self.wait_for(lambda: self.console.pid is None)
        self.assertIn('[Exit ', self.snapshot()['output'])

if __name__ == '__main__':
    unittest.main()
