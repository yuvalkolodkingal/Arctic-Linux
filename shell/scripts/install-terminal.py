#!/usr/bin/env python3
"""Get apps' job runner: dnf and Flatpak commands in a real PTY, one at a time. Input is never logged.

The shell's AppsService talks to this process with one JSON object per line on stdin and gets
the state back as one JSON object per line on stdout. Requests:
  {"action": "start", "text": "dnf search editor", "secret": false}   a line typed in the Console
  {"action": "input", "text": ..., "secret": bool}                      an answer to a prompt
  {"action": "interrupt"} · {"action": "clear"}
  {"action": "transcript", "on": bool}      whether state lines carry the transcript ("output");
                                            on until the shell says otherwise
  {"action": "run", "job": {"id": "j7", "kind": "install", "source": "dnf", "ids": ["gimp"]}}
                                            an install or removal from a Get apps page; its
                                            commands come from appslib.build_job, never from
                                            text the shell sends
State lines: {output?, running, secret, notice, job} after every change (at most ten a second
while a job runs), and {…, "finished": {id, ok, code, message}} once when a job ends. A typed
command shows as a job of kind "console", so the pages know the runner is busy.

What you can type in the Console:
  neovim htop                      install packages with dnf (pkexec dnf5 install -y neovim htop)
  flathub:org.gimp.GIMP            install a Flathub app (flatpak install -y flathub org.gimp.GIMP)
  dnf install|upgrade …            run as pkexec dnf5 … -y
  dnf remove|erase …               run as pkexec dnf5 …: it lists what goes and asks [y/N]
  dnf search|info|list …           run as dnf … (no password needed)
  flatpak install|update …         and other flatpak commands, as typed (changes get -y, except
                                   uninstall/remove, which list what goes and ask first)
Packages that are part of Arctic Linux (protected-packages.conf) can't be removed here.

Installs run unattended: dnf and flatpak get -y, so nothing waits for a [y/N]. Root rights
come from polkit (pkexec), whose password dialog is the shell's own (PolkitDialog); the
org.arcticlinux.pkexec.dnf action keeps the authorisation for a few minutes, so a second
install doesn't ask again. Whatever a program still asks (a typed removal's [y/N], a typed
`sudo` command, or pkexec without the graphical agent) is answered in the console: while a
program reads a password the input line is masked (see Console.prompt_is_secret), and a
response typed for a prompt that has since changed is refused rather than sent, so a password
can't land in a visible prompt. Nothing typed is written to a file or log.

When stdin closes (the shell stopped) while a job runs, the job still finishes: the runner
stops reading requests but keeps the PTY open until the job exits, so a shell restart doesn't
cut a dnf transaction short.
"""
import fcntl
import json
import os
import pty
import re
import selectors
import shlex
import struct
import subprocess
import sys
import termios
import time

import pyte

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import appslib  # noqa: E402

COLUMNS, ROWS = 88, 26
DNF_READONLY = {'search', 'info', 'list', 'repoquery', 'provides', 'whatprovides', 'check-update',
                'repolist', 'repoinfo', 'history', 'help', '--help', '-h', '--version', 'advisory',
                'changelog', 'leaves', 'environment'}
DNF = appslib.DNF
PKEXEC_DNF = appslib.PKEXEC_DNF
DNF_YES = {'-y', '--assumeyes', '--assumeno'}
# Typed removals are left to confirm: dnf and flatpak list what goes and ask [y/N] here.
DNF_REMOVALS = {'remove', 'erase', 'autoremove'}
FLATPAK_CHANGES = {'install', 'uninstall', 'remove', 'update', 'upgrade', 'repair', 'remote-add',
                   'remote-delete', 'mask', 'pin'}
FLATPAK_REMOVALS = {'uninstall', 'remove'}
FLATPAK_YES = {'-y', '--assumeyes', '--noninteractive'}
NAME = appslib.NAME
FLATHUB_PREFIX = 'flathub:'
# Theme hooks that set up a newly installed Flatpak app (30-zed: the Arctic theme and fonts in
# the Zed Flatpak's own config folder). Otherwise that happens at the next login or theme switch.
FLATPAK_THEME_HOOKS = ('30-zed',)
# sudo's password prompt, set through the environment (the commands stay plain `sudo dnf …`),
# so the console can tell it apart from other prompts on the same line.
SUDO_PROMPT = '[sudo] password for %p: '
SUDO_PROMPT_SHOWN = re.compile(r'\[sudo\] password for \S+:$')
WELCOME = ('Console\r\n'
           'Type a dnf or flatpak command, or an app name to install it. Removals list what goes\r\n'
           'and ask first. The other Get apps pages have search, details and Remove apps.\r\n'
           'Examples: neovim  ·  dnf search editor  ·  flathub:org.gimp.GIMP\r\n\r\n')
# A running job's state goes out at most this often (seconds).
EMIT_INTERVAL = 0.1
WAITING_STEP = 'Waiting for another software change to finish'


def build_command(text):
    """What to run for one line typed in the console, as an argv list (never a shell)."""
    if any(c in text for c in ('\n', '\r', '\x00')):
        raise ValueError('Enter one command at a time.')
    args = shlex.split(text)
    if args and args[0] == 'sudo':
        args.pop(0)
    if not args:
        raise ValueError('Type an app name, or a dnf or flatpak command.')
    head = args[0]
    if head in ('dnf', 'dnf5', '/usr/bin/dnf', '/usr/bin/dnf5'):
        rest = args[1:]
        verb = next((a for a in rest if not a.startswith('-')), None)
        if verb is None:
            raise ValueError('Add what dnf should do, like: dnf install neovim')
        if verb in DNF_READONLY:
            return ['dnf', *rest]
        if verb in DNF_REMOVALS:
            appslib.protection().check([a for a in rest[rest.index(verb) + 1:] if not a.startswith('-')])
            return [*PKEXEC_DNF, *rest]
        return [*PKEXEC_DNF, *with_yes(rest, verb, DNF_YES, '-y')]
    if head in ('flatpak', '/usr/bin/flatpak'):
        rest = args[1:]
        verb = next((a for a in rest if not a.startswith('-')), None)
        if verb is None:
            raise ValueError('Add what flatpak should do, like: flatpak install flathub org.gimp.GIMP')
        if verb in FLATPAK_CHANGES and verb not in FLATPAK_REMOVALS:
            rest = with_yes(rest, verb, FLATPAK_YES, '-y')
        return ['flatpak', *rest]
    # Bare names: a quick install. Package names only, no options.
    for name in args:
        if not NAME.match(name):
            raise ValueError('“{}” isn’t a package name. Type a name, or a dnf or flatpak command.'.format(name))
    apps = [a[len(FLATHUB_PREFIX):] for a in args if a.startswith(FLATHUB_PREFIX)]
    packages = [a for a in args if not a.startswith(FLATHUB_PREFIX)]
    if apps and packages:
        raise ValueError('Install Flathub apps and dnf packages separately.')
    if apps:
        return ['flatpak', 'install', '-y', 'flathub', *apps]
    return [*PKEXEC_DNF, 'install', '-y', *packages]


def theme_hook(name):
    """The theme hook `name` as arctic-theme would run it (a file of yours wins), or None."""
    config = os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    for d in (os.path.join(config, 'arctic', 'theme-hooks.d'),
              os.path.join(os.environ.get('ARCTIC_DATA_DIR') or '/usr/share/arctic', 'theme-hooks.d')):
        path = os.path.join(d, name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def after_flatpak_install(command):
    """Run the theme hooks for Flatpak apps after `flatpak install` succeeded (in the
    background; their output is not shown)."""
    if not command or os.path.basename(command[0]) != 'flatpak':
        return []
    verb = next((a for a in command[1:] if not a.startswith('-')), None)
    if verb != 'install':
        return []
    started = []
    for name in FLATPAK_THEME_HOOKS:
        path = theme_hook(name)
        if path is None:
            continue
        try:
            subprocess.Popen([path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, start_new_session=True)
            started.append(path)
        except OSError:
            pass
    return started


def with_yes(args, verb, answers, flag):
    """args with `flag` right after the verb, unless an answer (-y, --assumeno …) is given."""
    if any(a in answers for a in args):
        return list(args)
    i = args.index(verb) + 1
    return [*args[:i], flag, *args[i:]]


def job_label(job):
    """The name a job's messages use (the page's display name, else its ids)."""
    name = job.get('name') if isinstance(job.get('name'), str) else ''
    name = appslib.clean_name(name, 80)
    return name or ', '.join(str(i) for i in (job.get('ids') or [])[:3]) or 'The app'


class Console:
    def __init__(self):
        self.screen = pyte.HistoryScreen(COLUMNS, ROWS, history=2000)
        self.stream = pyte.ByteStream(self.screen)
        self.master = None
        self.pid = None
        self.command = None
        self.queue = []                 # the job's commands still to run
        self.job = None                 # the job running: {id, kind, source, ids, phase, percent, …}
        self.finished = None            # sent once, with the next state line
        self.transcript = True
        self.secret = False
        self.notice = ''
        self.dirty = True
        self.last_emit = 0.0
        self.stream.feed(WELCOME.encode())

    def text(self):
        history = [''.join(row[i].data for i in range(self.screen.columns)).rstrip() for row in self.screen.history.top]
        return '\n'.join(history + [row.rstrip() for row in self.screen.display]).rstrip()

    def emit(self):
        state = dict(running=self.pid is not None, secret=self.secret, notice=self.notice, job=self.job)
        if self.transcript:
            state['output'] = self.text()
        if self.finished is not None:
            state['finished'] = self.finished
            self.finished = None
        print(json.dumps(state), flush=True)
        self.dirty = False
        self.last_emit = time.monotonic()

    def due(self):
        """Emit now? Changes go out at once when nothing runs, else at most every EMIT_INTERVAL."""
        if not self.dirty:
            return False
        return self.pid is None or self.finished is not None or time.monotonic() - self.last_emit >= EMIT_INTERVAL

    def write_output(self, text):
        self.stream.feed(text.encode())
        self.dirty = True

    def prompt_is_secret(self):
        """Is the program in the PTY reading a password right now?

        getpass() and sudo's own password prompt turn echo off and keep the terminal in
        canonical (line) mode. Echo off alone is not enough: with use_pty (sudo's default
        since 1.9.14, so on Fedora 44) sudo runs the command in a PTY of its own and puts this
        one in raw mode — echo and canonical mode both off — for as long as the command runs.
        dnf's "Is this ok [y/N]" arrives that way, and what is typed there is echoed back by
        sudo's inner terminal. So raw mode counts only when the cursor sits right after sudo's
        password prompt (sudo reads the password that way with the pwfeedback option).
        """
        if self.master is None:
            return False
        try:
            lflag = termios.tcgetattr(self.master)[3]
        except termios.error:
            return False
        if lflag & termios.ECHO:
            return False
        if lflag & termios.ICANON:
            return True
        return self.at_sudo_prompt()

    def at_sudo_prompt(self):
        cursor = self.screen.cursor
        before_cursor = self.screen.display[cursor.y][:cursor.x].rstrip()
        return bool(SUDO_PROMPT_SHOWN.search(before_cursor))

    def start(self, text, command=None):
        """A line typed in the console (or, in tests, a given argv)."""
        if self.pid is not None:
            return
        commands = [command] if command is not None else [build_command(text)]
        self.job = dict(id='', kind='console', source='', ids=[], phase='running', percent=None,
                        done=None, total=None, step='')
        self.queue = commands[1:]
        self.spawn(commands[0], text if command is not None else None)

    def run(self, job):
        """A structured job from a Get apps page: its commands, in order, until one fails."""
        ident = str(job.get('id') or '')
        if self.pid is not None:
            self.finished = dict(id=ident, ok=False, code=-1, message='Get apps is busy with another change. Try again when it’s done.')
            self.dirty = True
            return
        try:
            commands = appslib.build_job(job)
        except ValueError as error:
            self.finished = dict(id=ident, ok=False, code=-1, message=str(error))
            self.dirty = True
            return
        self.job = dict(id=ident, kind=job.get('kind'), source=job.get('source'), ids=list(job.get('ids') or []),
                        name=job_label(job), phase='running', percent=None, done=None, total=None, step='')
        self.queue = commands[1:]
        self.spawn(commands[0])

    def spawn(self, command, shown=None):
        shown = shown if shown is not None else ' '.join(shlex.quote(a) for a in command)
        self.notice = ''
        self.write_output('$ ' + shown + '\r\n')
        pid, fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env.update(TERM='xterm', LC_ALL='C.UTF-8', COLUMNS=str(COLUMNS), LINES=str(ROWS),
                       SUDO_PROMPT=SUDO_PROMPT)
            try:
                os.execvpe(command[0], command, env)
            except OSError as error:
                os.write(1, ('{}: {}\r\n'.format(command[0], error.strerror)).encode())
                os._exit(127)
        self.pid, self.master, self.command = pid, fd, command
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLUMNS, 0, 0))
        os.set_blocking(fd, False)
        self.dirty = True

    def input(self, text, secret):
        if self.master is None:
            return
        # Refuse stale UI input rather than risk echoing a password at a new prompt.
        if bool(secret) != self.prompt_is_secret():
            self.notice = 'The prompt changed. Please enter your response again.'
            self.dirty = True
            return
        if any(c in text for c in ('\n', '\r', '\x00')):
            raise ValueError('Enter one response at a time.')
        os.write(self.master, (text + '\n').encode())
        self.notice = ''

    def interrupt(self):
        if self.master is not None:
            self.queue = []
            os.write(self.master, b'\x03')

    def screen_lines(self):
        """The screen's lines down to the cursor (the newest output)."""
        return [row.rstrip() for row in self.screen.display[:self.screen.cursor.y + 1]]

    def track(self):
        """The running job's progress from what is on the screen."""
        if self.job is None:
            return
        lines = self.screen_lines()[-6:]
        tail = '\n'.join(lines)
        found = appslib.progress(lines)
        before = dict(self.job)
        if appslib.waiting(tail):
            self.job['step'] = WAITING_STEP
        elif found:
            self.job.update(percent=found['percent'], done=found['done'], total=found['total'],
                            step=found['step'] or self.job['step'])
        if self.job != before:
            self.dirty = True

    def read(self):
        if self.master is None:
            return
        got = False
        for _ in range(32):
            try:
                data = os.read(self.master, 8192)
                if not data:
                    break
                self.stream.feed(data)
                self.dirty = got = True
            except (BlockingIOError, OSError):
                break
        if got:
            self.track()
        secret = self.prompt_is_secret()
        if secret != self.secret:
            self.secret = secret
            self.dirty = True
        finished, status = os.waitpid(self.pid, os.WNOHANG)
        if finished:
            # Drain remaining output after process completion.
            try:
                while True:
                    data = os.read(self.master, 8192)
                    if not data:
                        break
                    self.stream.feed(data)
            except OSError:
                pass
            os.close(self.master)
            self.master = self.pid = None
            self.secret = False
            code = os.waitstatus_to_exitcode(status)
            if code == 0:
                after_flatpak_install(self.command)
            command, self.command = self.command, None
            if code == 0 and self.queue:
                self.spawn(self.queue.pop(0))
                return
            self.queue = []
            self.write_output('\r\n' + ('Done.' if code == 0 else '[Exit ' + str(code) + ']') + '\r\n\r\n')
            job, self.job = self.job, None
            if job is not None and job.get('kind') != 'console':
                tail = '\n'.join(self.text().splitlines()[-40:])
                message = appslib.explain(dict(job, argv=command), code, tail, job.get('name', ''))
                if code != 0 and ' already installed' in tail and job.get('source') == 'flatpak':
                    code, message = 0, ''
                self.finished = dict(id=job['id'], ok=code == 0, code=code, message=message)
            elif job is not None:
                self.finished = dict(id='', ok=code == 0, code=code, message='')


def handle(console, request):
    action = request.get('action')
    if action == 'start':
        console.start(request.get('text', ''))
    elif action == 'run':
        job = request.get('job')
        console.run(job if isinstance(job, dict) else {})
    elif action == 'input':
        console.input(request.get('text', ''), request.get('secret', False))
    elif action == 'interrupt':
        console.interrupt()
    elif action == 'transcript':
        console.transcript = bool(request.get('on'))
        console.dirty = True
    elif action == 'clear' and console.pid is None:
        console.screen.reset()
        console.dirty = True


def main():
    console = Console()
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin, selectors.EVENT_READ)
    reading = True
    incoming = b''
    console.emit()
    try:
        while True:
            if not reading and console.pid is None:
                return
            timeout = EMIT_INTERVAL / 2 if console.pid else None
            events = selector.select(timeout) if reading else (time.sleep(EMIT_INTERVAL / 2) or [])
            for key, _ in events:
                data = os.read(key.fd, 65536)
                if not data:
                    # The shell went away: finish the running job, then stop.
                    selector.unregister(sys.stdin)
                    reading = False
                    break
                incoming += data
                while b'\n' in incoming:
                    line, incoming = incoming.split(b'\n', 1)
                    try:
                        handle(console, json.loads(line))
                    except ValueError as error:
                        # Only our own messages; the typed text itself is never echoed back.
                        console.notice = str(error) if str(error) else 'Could not process that input.'
                        console.dirty = True
                    except OSError:
                        console.notice = 'Could not process that input. Type an app name, or a dnf or flatpak command.'
                        console.dirty = True
                    finally:
                        line = b''
            console.read()
            if reading and console.due():
                console.emit()
    finally:
        if console.master is not None:
            os.close(console.master)


if __name__ == '__main__':
    main()
