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
import unittest.mock

spec = importlib.util.spec_from_file_location('install_terminal', Path(__file__).parents[1]/'scripts/install-terminal.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class CommandTests(unittest.TestCase):
    """What each typed line runs: dnf through pkexec, Flathub through flatpak, never a shell.
    Installs never wait for a [y/N]: they get -y unless the line answers already. Removals
    ask: dnf and flatpak list what goes first."""

    def test_bare_names_install_with_dnf(self):
        self.assertEqual(module.build_command('neovim htop'), ['pkexec', '/usr/bin/dnf5', 'install', '-y', 'neovim', 'htop'])

    def test_flathub_ids_install_with_flatpak(self):
        self.assertEqual(module.build_command('flathub:org.gimp.GIMP'), ['flatpak', 'install', '-y', 'flathub', 'org.gimp.GIMP'])

    def test_mixed_sources_are_refused(self):
        with self.assertRaises(ValueError):
            module.build_command('neovim flathub:org.gimp.GIMP')

    def test_dnf_changes_need_pkexec_and_queries_do_not(self):
        self.assertEqual(module.build_command('dnf install -y fish'), ['pkexec', '/usr/bin/dnf5', 'install', '-y', 'fish'])
        self.assertEqual(module.build_command('sudo dnf remove fish'), ['pkexec', '/usr/bin/dnf5', 'remove', 'fish'])
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
        self.assertEqual(module.build_command('flatpak uninstall org.gimp.GIMP'), ['flatpak', 'uninstall', 'org.gimp.GIMP'])

    def test_protected_packages_are_not_removed(self):
        for text in ('dnf remove arctic-shell', 'dnf erase mangowm', 'sudo dnf remove -y fish kernel-core'):
            with self.assertRaises(ValueError, msg=text) as caught:
                module.build_command(text)
            self.assertIn('is part of Arctic Linux, so Get apps won’t remove it.', str(caught.exception))
        self.assertEqual(module.build_command('dnf install arctic-shell'), ['pkexec', '/usr/bin/dnf5', 'install', '-y', 'arctic-shell'])

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


class FlatpakThemeHookTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.share = Path(self.tmp.name) / 'share'
        (self.share / 'theme-hooks.d').mkdir(parents=True)
        self.out = Path(self.tmp.name) / 'ran'
        hook = self.share / 'theme-hooks.d/30-zed'
        hook.write_text('#!/bin/sh\necho ran > "{}"\n'.format(self.out))
        hook.chmod(0o755)
        self.env = {'ARCTIC_DATA_DIR': str(self.share), 'XDG_CONFIG_HOME': str(Path(self.tmp.name) / 'config')}

    def tearDown(self):
        self.tmp.cleanup()

    def test_zed_hook_runs_after_a_flatpak_install(self):
        with unittest.mock.patch.dict(os.environ, self.env):
            self.assertEqual(module.after_flatpak_install(['pkexec', '/usr/bin/dnf5', 'install', '-y', 'zed']), [])
            self.assertEqual(module.after_flatpak_install(['flatpak', 'update', '-y']), [])
            started = module.after_flatpak_install(['flatpak', 'install', '-y', 'flathub', 'dev.zed.Zed'])
        self.assertEqual(started, [str(self.share / 'theme-hooks.d/30-zed')])
        deadline = time.monotonic() + 5
        while not self.out.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.out.read_text(), 'ran\n')

    def test_your_own_hook_wins_and_a_missing_one_is_skipped(self):
        own = Path(self.env['XDG_CONFIG_HOME']) / 'arctic/theme-hooks.d/30-zed'
        own.parent.mkdir(parents=True)
        own.write_text('#!/bin/sh\nexit 0\n')
        own.chmod(0o755)
        with unittest.mock.patch.dict(os.environ, self.env):
            self.assertEqual(module.theme_hook('30-zed'), str(own))
            self.assertIsNone(module.theme_hook('99-none'))

class RunTests(unittest.TestCase):
    """Structured jobs (`run`): their commands run in the PTY, their progress and end go out as
    data, and a job outlives the shell."""

    FLATPAK = '''#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls"
printf 'Looking for matches…\\n'
printf 'Installing 1/1… ████  45%%  1.2 MB/s\\n'
sleep 0.3
printf 'Installing 1/1… ████████  100%%\\n'
[ -e "$(dirname "$0")/fail" ] && { echo "error: Unable to load summary from remote flathub: Could not resolve host"; exit 1; }
exit 0
'''

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        (self.bin / 'flatpak').write_text(self.FLATPAK)
        (self.bin / 'flatpak').chmod(0o755)
        self.env = unittest.mock.patch.dict(os.environ, {'PATH': str(self.bin) + ':' + os.environ.get('PATH', ''),
                                                         'XDG_CONFIG_HOME': str(self.bin / 'config'),
                                                         'ARCTIC_DATA_DIR': str(self.bin / 'share')})
        self.env.start()
        self.console = module.Console()

    def tearDown(self):
        self.env.stop()
        if self.console.pid:
            os.kill(self.console.pid, signal.SIGKILL)
            os.waitpid(self.console.pid, 0)
            os.close(self.console.master)
        self.tmp.cleanup()

    def states(self, job):
        lines = []
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.console.run(job)
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                self.console.read()
                if self.console.dirty:
                    self.console.emit()
                if self.console.pid is None and self.console.job is None and not self.console.dirty:
                    break
                time.sleep(0.02)
        lines = [json.loads(l) for l in stream.getvalue().splitlines()]
        return lines

    def test_a_flatpak_install_reports_progress_then_success(self):
        lines = self.states(dict(id='j8', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system', name='GIMP'))
        running = [l['job'] for l in lines if l.get('job')]
        self.assertTrue(running)
        self.assertEqual(running[0]['id'], 'j8')
        self.assertIn(45, [j['percent'] for j in running])
        self.assertEqual(lines[-1]['finished'], dict(id='j8', ok=True, code=0, message=''))
        self.assertIsNone(lines[-1]['job'])
        self.assertIn('install --system -y --noninteractive flathub org.gimp.GIMP', (self.bin / 'calls').read_text())
        self.assertIn('$ flatpak install --system', lines[-1]['output'])   # the console shows GUI jobs too

    def test_a_failed_job_says_why(self):
        (self.bin / 'fail').write_text('')
        lines = self.states(dict(id='j9', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system', name='GIMP'))
        self.assertEqual(lines[-1]['finished'], dict(id='j9', ok=False, code=1, message=
                         'GIMP couldn’t be downloaded. Check your internet connection and try again. Nothing else changed.'))

    def test_a_flatpak_removal_runs_both_commands(self):
        lines = self.states(dict(id='j10', kind='remove', source='flatpak', ids=['org.gimp.GIMP'], installation='user', delete_data=False))
        self.assertTrue(lines[-1]['finished']['ok'])
        self.assertEqual((self.bin / 'calls').read_text().splitlines(),
                         ['uninstall --user -y --noninteractive org.gimp.GIMP', 'uninstall --user -y --noninteractive --unused'])

    def test_refused_jobs_and_a_second_job(self):
        lines = self.states(dict(id='j1', kind='remove', source='dnf', ids=['arctic-shell']))
        self.assertEqual(lines[-1]['finished'], dict(id='j1', ok=False, code=-1, message='arctic-shell is part of Arctic Linux, so Get apps won’t remove it.'))
        self.assertFalse((self.bin / 'calls').exists())
        self.console.run(dict(id='a', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system'))
        self.console.run(dict(id='b', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system'))
        self.assertEqual(self.console.finished['id'], 'b')
        self.assertFalse(self.console.finished['ok'])
        self.assertEqual(self.console.job['id'], 'a')

    def test_transcript_can_be_turned_off(self):
        module.handle(self.console, dict(action='transcript', on=False))
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            self.console.emit()
        self.assertNotIn('output', json.loads(stream.getvalue()))

    def test_a_typed_command_is_a_console_job(self):
        self.console.start('x', [sys.executable, '-c', 'print(1)'])
        self.assertEqual(self.console.job['kind'], 'console')

    def test_the_job_finishes_after_the_shell_goes_away(self):
        (self.bin / 'flatpak').write_text('#!/bin/sh\nsleep 1\necho done > "$(dirname "$0")/finished"\n')
        runner = subprocess.Popen([sys.executable, str(Path(__file__).parents[1] / 'scripts/install-terminal.py')],
                                  stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=os.environ.copy())
        job = dict(id='j', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system')
        runner.stdin.write((json.dumps(dict(action='run', job=job)) + '\n').encode())
        runner.stdin.close()
        self.assertEqual(runner.wait(timeout=10), 0)
        self.assertEqual((self.bin / 'finished').read_text(), 'done\n')


if __name__ == '__main__':
    unittest.main()
