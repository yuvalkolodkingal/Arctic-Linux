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
        for text in ('dnf remove arctic-shell', 'dnf erase mangowm', 'sudo dnf remove -y fish kernel-core',
                     'dnf rm arctic-shell', 'dnf --repo fedora remove quickshell', 'dnf -c /x --setopt protected_packages= rm systemd'):
            with self.assertRaises(ValueError, msg=text) as caught:
                module.build_command(text)
            self.assertIn('is part of Arctic Linux, so Get apps won’t remove it.', str(caught.exception))
        self.assertEqual(module.build_command('dnf install arctic-shell'), ['pkexec', '/usr/bin/dnf5', 'install', '-y', 'arctic-shell'])

    def test_changes_that_can_remove_packages_ask_and_are_checked_first(self):
        # dnf5's aliases (rm), commands that remove along the way (swap, do, distro-sync …),
        # --allowerasing, an unknown command (your own alias) and options before the command that
        # aren't known here: no -y (a typed one is dropped), and check_removal runs (as you)
        # before pkexec.
        for text in ('dnf rm fish', 'dnf erase fish', 'dnf autoremove', 'dnf --repo fedora remove fish',
                     'dnf -c /etc/dnf/dnf.conf --setopt=x=1 rm quick*', 'dnf swap fish zsh', 'dnf do --action=remove fish',
                     'dnf distro-sync', 'dnf dsync', 'dnf downgrade fish', 'dnf group remove kde', 'dnf grp remove kde',
                     'dnf install --allowerasing fish', 'dnf -qy install fish', 'dnf --unknown upgrade', 'dnf purge fish',
                     'sudo dnf remove -y fish', 'dnf --assumeyes rm fish'):
            with self.subTest(text):
                rest = [a for a in text.split()[2 if text.startswith('sudo') else 1:] if a not in ('-y', '--assumeyes')]
                command = module.build_command(text)
                self.assertEqual(command, ['pkexec', '/usr/bin/dnf5', *rest])
                self.assertEqual(module.console_commands(text), [[*module.CHECK, *rest], command])

    def test_installs_run_unattended_and_questions_as_you(self):
        # -y goes right after the command word, found past the options that take a value.
        for text, argv in (('dnf --repo fedora install fish', ['--repo', 'fedora', 'install', '-y', 'fish']),
                           ('dnf --setopt install_weak_deps=False in fish', ['--setopt', 'install_weak_deps=False', 'in', '-y', 'fish']),
                           ('dnf up', ['up', '-y']), ('dnf group install kde', ['group', '-y', 'install', 'kde']),
                           ('dnf copr enable x/y', ['copr', '-y', 'enable', 'x/y'])):
            self.assertEqual(module.console_commands(text), [['pkexec', '/usr/bin/dnf5', *argv]], text)
        for text in ('dnf --refresh search editor', 'dnf group list', 'dnf rq gimp', 'dnf --version', 'dnf history undo 5'):
            self.assertEqual(module.console_commands(text), [['dnf', *text.split()[1:]]], text)

    def test_flatpak_removals_never_get_yes(self):
        self.assertEqual(module.build_command('flatpak --installation install uninstall org.x.Y'),
                         ['flatpak', '--installation', 'install', 'uninstall', 'org.x.Y'])
        self.assertEqual(module.build_command('flatpak --installation=default install flathub org.x.Y'),
                         ['flatpak', '--installation=default', 'install', '-y', 'flathub', 'org.x.Y'])
        self.assertEqual(module.build_command('flatpak --unknown install flathub org.x.Y'),
                         ['flatpak', '--unknown', 'install', 'flathub', 'org.x.Y'])

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

    def test_asking_is_a_question_at_the_cursor(self):
        self.console.start('question test', [sys.executable, '-c', "print('Working', flush=True); input('Is this ok [y/N]: ')"])
        self.wait_for(lambda: 'Is this ok' in self.snapshot()['output'])
        self.assertTrue(self.console.asking())
        self.console.input('n', False)
        self.wait_for(lambda: self.console.pid is None)
        self.console.start('work test', [sys.executable, '-c', "import time; print('Is this ok [y/N]: n', flush=True); time.sleep(60)"])
        self.wait_for(lambda: 'Is this ok' in self.snapshot()['output'])
        self.assertFalse(self.console.asking())

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

    def test_the_job_finishes_when_the_shell_stops_the_runner(self):
        (self.bin / 'flatpak').write_text('#!/bin/sh\nsleep 1\necho done > "$(dirname "$0")/finished"\n')
        runner = subprocess.Popen([sys.executable, str(Path(__file__).parents[1] / 'scripts/install-terminal.py')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=os.environ.copy())
        runner.stdout.readline()                      # the first state: the runner is up
        job = dict(id='j', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system')
        runner.stdin.write((json.dumps(dict(action='run', job=job)) + '\n').encode())
        runner.stdin.flush()
        runner.stdout.readline()                      # the job started
        runner.send_signal(signal.SIGTERM)
        self.assertEqual(runner.wait(timeout=10), 0)
        self.assertEqual((self.bin / 'finished').read_text(), 'done\n')
        runner.stdin.close()
        runner.stdout.close()

    def runner_with_job(self, flatpak):
        """A runner (as the shell starts it) whose install job runs `flatpak`; returns once the job runs."""
        (self.bin / 'flatpak').write_text(flatpak)
        runner = subprocess.Popen([sys.executable, str(Path(__file__).parents[1] / 'scripts/install-terminal.py')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=os.environ.copy())
        runner.stdout.readline()
        job = dict(id='j', kind='install', source='flatpak', ids=['org.gimp.GIMP'], installation='system')
        runner.stdin.write((json.dumps(dict(action='run', job=job)) + '\n').encode())
        runner.stdin.flush()
        return runner

    def wait_for_file(self, name, timeout=10):
        deadline = time.monotonic() + timeout
        while not (self.bin / name).exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        return (self.bin / name).read_text() if (self.bin / name).exists() else None

    def test_the_job_survives_the_runner_being_killed(self):
        # Quickshell SIGKILLs the runner when the shell stops or reloads. The job keeps its
        # terminal (no SIGHUP) and finishes, though its progress piles up unread.
        runner = self.runner_with_job('''#!/usr/bin/env python3
import os, signal, sys, time
here = os.path.dirname(os.path.abspath(__file__))
signal.signal(signal.SIGHUP, lambda *_: open(os.path.join(here, 'hup'), 'w').write('hup'))
open(os.path.join(here, 'started'), 'w').write('')
for i in range(20):
    print('Installing 1/1… %d%%' % (i * 5), flush=True)
    time.sleep(0.05)
open(os.path.join(here, 'finished'), 'w').write('done')
''')
        self.assertEqual(self.wait_for_file('started'), '')
        runner.kill()
        runner.wait(timeout=5)
        self.assertEqual(self.wait_for_file('finished'), 'done')
        self.assertFalse((self.bin / 'hup').exists())
        runner.stdin.close()
        runner.stdout.close()

    def test_a_question_no_one_can_answer_is_cancelled(self):
        # With the shell gone, a [Y/n] would wait forever (and keep dnf's lock): Ctrl+C ends it.
        runner = self.runner_with_job('''#!/usr/bin/env python3
import os, sys
here = os.path.dirname(os.path.abspath(__file__))
try:
    input('Proceed with these changes to the system installation? [Y/n]: ')
    open(os.path.join(here, 'answer'), 'w').write('answered')
except KeyboardInterrupt:
    open(os.path.join(here, 'answer'), 'w').write('interrupted')
    sys.exit(130)
''')
        while '[Y/n]' not in json.loads(runner.stdout.readline()).get('output', ''):
            pass
        runner.kill()
        runner.wait(timeout=5)
        self.assertEqual(self.wait_for_file('answer'), 'interrupted')
        runner.stdin.close()
        runner.stdout.close()

    def test_an_idle_runner_stops_at_once(self):
        runner = subprocess.Popen([sys.executable, str(Path(__file__).parents[1] / 'scripts/install-terminal.py')],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=os.environ.copy())
        runner.stdout.readline()
        runner.send_signal(signal.SIGTERM)
        self.assertEqual(runner.wait(timeout=5), 0)
        runner.stdin.close()
        runner.stdout.close()


# Stand-ins for dnf5, rpm, getent and pkexec, answering from system.json next to them.
FAKES = r'''#!/usr/bin/env python3
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
data = json.load(open(os.path.join(here, 'system.json')))
tool, args = os.path.basename(sys.argv[0]), sys.argv[1:]
with open(os.path.join(here, 'calls'), 'a') as log:
    log.write(tool + ' ' + ' '.join(args) + '\n')
if tool == 'dnf5':
    store = next(a.split('=', 1)[1] for a in args if a.startswith('--store='))
    found = data['transactions'].get(' '.join(a for a in args if a != '-y' and not a.startswith('--store=')))
    if found is None:
        print('Nothing to do.')
    elif isinstance(found, str):
        print(found)
        sys.exit(1)
    else:
        os.makedirs(store)
        with open(os.path.join(store, 'transaction.json'), 'w') as f:
            json.dump(dict(rpms=[dict(nevra=n, action=a, reason='User') for n, a in found]), f)
elif tool == 'rpm' and args[0] == '-qf':
    for path in args[args.index('--') + 1:]:
        for name in data['owners'].get(path, []):
            print('%s\t%s' % (path, name))
elif tool == 'rpm':
    missing = [n for n in args[3:] if not data['installed'].get(n)]
    for name in args[3:]:
        print('\n'.join([name] * data['installed'][name]) if name not in missing else 'package %s is not installed' % name)
    sys.exit(len(missing))
elif tool == 'getent':
    print('%s:x:1000:1000::/home/%s:/bin/zsh' % (args[1], args[1]))
'''


class RemovalCheckTests(unittest.TestCase):
    """check_removal, the first step of a typed dnf change that can remove packages: what the
    transaction takes away counts, not the words typed."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        for tool in ('dnf5', 'rpm', 'getent', 'pkexec'):
            (self.bin / tool).write_text(FAKES)
            (self.bin / tool).chmod(0o755)
        (self.bin / 'run').mkdir()
        self.system = dict(installed={'kitty': 1, 'foot': 1, 'kernel-core': 2, 'fish': 1, 'zsh': 1},
                           owners={'/bin/zsh': ['zsh'], os.path.realpath('/bin/zsh'): ['zsh']}, transactions={
            'rm quick*': [('quickshell-0.2-1.fc44.x86_64', 'Remove')],
            'remove quickshell.x86_64': [('quickshell-0.2-1.fc44.x86_64', 'Remove')],
            'remove qt6-qtdeclarative': [('qt6-qtdeclarative-6.11.2-2.fc44.x86_64', 'Remove'),
                                         ('quickshell-0.2-1.fc44.x86_64', 'Remove'), ('arctic-shell-0.3-1.noarch', 'Remove')],
            'swap arctic-release fedora-release': [('arctic-release-44-1.noarch', 'Remove'), ('fedora-release-44-1.noarch', 'Install')],
            'rm fish': [('fish-4.0-1.fc44.x86_64', 'Remove')],
            'remove zsh': [('zsh-5.9-1.fc44.x86_64', 'Remove')],
            'remove kitty foot': [('kitty-0.40-1.fc44.x86_64', 'Remove'), ('foot-1.20-1.fc44.x86_64', 'Remove')],
            'remove --oldinstallonly': [('kernel-core-6.10.1-1.fc44.x86_64', 'Remove')],
            'distro-sync': [('kernel-core-6.10.1-1.fc44.x86_64', 'Remove'), ('kernel-core-6.12.1-1.fc44.x86_64', 'Install'),
                            ('fish-3.7-1.fc44.x86_64', 'Replaced'), ('fish-4.0-1.fc44.x86_64', 'Upgrade')],
            'remove kernel-core': [('kernel-core-6.10.1-1.fc44.x86_64', 'Remove'), ('kernel-core-6.12.1-1.fc44.x86_64', 'Remove')],
            'remove broken': 'Error: Problem: conflicting requests',
            'replay /tmp/t': 'Unknown argument "--store=/run/x" for command "replay".',
        })
        self.env = unittest.mock.patch.dict(os.environ, {
            'PATH': str(self.bin) + ':' + os.environ.get('PATH', ''), 'USER': 'tester', 'HOME': str(self.bin),
            'XDG_RUNTIME_DIR': str(self.bin / 'run'), 'XDG_CONFIG_HOME': str(self.bin / 'config'),
            'ARCTIC_PROTECTED_DIR': str(self.bin / 'protected.d')})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def check(self, *args):
        (self.bin / 'system.json').write_text(json.dumps(self.system))
        done = subprocess.run([sys.executable, str(Path(__file__).parents[1] / 'scripts/install-terminal.py'), '--check', *args],
                              capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout.strip().splitlines()[-1] if done.stdout.strip() else done.stderr

    def test_what_the_transaction_removes_is_checked(self):
        self.assertEqual(self.check('rm', 'quick*'),
                         (1, 'Removing quick* would also remove quickshell, which Arctic Linux needs. Nothing was changed.'))
        self.assertEqual(self.check('remove', 'quickshell.x86_64')[0], 1)
        self.assertEqual(self.check('remove', 'qt6-qtdeclarative'),
                         (1, 'Removing qt6-qtdeclarative would also remove arctic-shell, which Arctic Linux needs. Nothing was changed.'))
        self.assertEqual(self.check('swap', 'arctic-release', 'fedora-release'),
                         (1, 'arctic-release is part of Arctic Linux, so it can’t be removed. Nothing was changed.'))
        self.assertEqual(self.check('rm', 'fish'), (0, 'Checking what this would remove…'))
        self.assertFalse(list((self.bin / 'run/arctic-apps').iterdir()))   # the stored transactions are gone

    def test_login_shell_and_only_terminal(self):
        self.assertEqual(self.check('remove', 'zsh'),
                         (1, 'zsh is your login shell. Choose another shell first (see Terminal and shell). Nothing was changed.'))
        code, line = self.check('remove', 'kitty', 'foot')
        self.assertEqual(code, 1)
        self.assertIn('kitty is your only terminal', line)

    def test_a_package_that_stays_installed_is_not_removed(self):
        # The oldest kernel goes, another stays; a new one comes in; fish is upgraded.
        self.assertEqual(self.check('remove', '--oldinstallonly')[0], 0)
        self.assertEqual(self.check('distro-sync')[0], 0)
        self.assertEqual(self.check('remove', 'kernel-core'),
                         (1, 'kernel-core is part of Arctic Linux, so it can’t be removed. Nothing was changed.'))

    def test_dnf_answers_are_left_out_and_failures_refuse(self):
        self.assertEqual(self.check('--assumeno', 'rm', '-y', '--offline', 'fish')[0], 0)
        self.assertIn('dnf5 rm fish --store=', (self.bin / 'calls').read_text())
        self.assertEqual(self.check('remove', 'broken'), (1, 'Error: Problem: conflicting requests'))
        self.assertEqual(self.check('replay', '/tmp/t'),
                         (1, 'The console can’t tell what this would remove, so it doesn’t run it. Nothing was changed.'))
        self.assertEqual(self.check('remove', 'nothere'), (0, 'Checking what this would remove…'))

    def run_console(self, text):
        (self.bin / 'system.json').write_text(json.dumps(self.system))
        console = module.Console()
        console.start(text)
        deadline = time.monotonic() + 20
        while console.pid is not None and time.monotonic() < deadline:
            console.read()
            time.sleep(0.02)
        self.assertIsNone(console.pid)
        return console.text(), (self.bin / 'calls').read_text()

    def test_the_console_checks_before_pkexec(self):
        output, calls = self.run_console('dnf rm quick*')
        self.assertIn('Checking what this would remove…', output)
        self.assertIn('would also remove quickshell', output)
        self.assertIn('[Exit 1]', output)
        self.assertNotIn('pkexec', calls)
        (self.bin / 'calls').unlink()
        output, calls = self.run_console('dnf rm fish')
        self.assertIn('$ pkexec /usr/bin/dnf5 rm fish', output)
        self.assertIn('pkexec /usr/bin/dnf5 rm fish\n', calls)   # no -y: dnf asks [y/N]
        self.assertIn('Done.', output)


if __name__ == '__main__':
    unittest.main()
