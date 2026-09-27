#!/usr/bin/env python3
"""Get apps console: dnf and Flatpak commands in a real PTY. Input is never logged.

The shell's InstallConsole talks to this process with one JSON object per line on stdin
({"action": "start"|"input"|"interrupt"|"clear", "text": ..., "secret": bool}) and gets the
terminal state back as one JSON object per line on stdout ({output, running, secret, notice}).

What you can type:
  neovim htop                      install packages with dnf (sudo dnf install neovim htop)
  flathub:org.gimp.GIMP            install a Flathub app (flatpak install flathub org.gimp.GIMP)
  dnf install|remove|upgrade …     run as sudo dnf …
  dnf search|info|list …           run as dnf … (no password needed)
  flatpak install flathub …        and other flatpak commands, as typed

Passwords (sudo) and confirmations (dnf's [y/N]) are answered in the console. While the
terminal has echo turned off the input line is masked, and a response typed for a prompt
that has since changed is refused rather than sent, so a password can't land in a visible
prompt. Nothing typed is written to a file or log.
"""
import fcntl
import json
import os
import pty
import re
import selectors
import shlex
import struct
import sys
import termios

import pyte

COLUMNS, ROWS = 88, 26
DNF_READONLY = {'search', 'info', 'list', 'repoquery', 'provides', 'whatprovides', 'check-update',
                'repolist', 'repoinfo', 'history', 'help', '--help', '-h', '--version', 'advisory',
                'changelog', 'leaves', 'environment'}
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+@:-]*$')
FLATHUB_PREFIX = 'flathub:'
WELCOME = ('Get apps\r\n'
           'Type an app name to install it, or a dnf or flatpak command.\r\n'
           'Examples: neovim  ·  dnf search editor  ·  flathub:org.gimp.GIMP\r\n\r\n')


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
        return ['sudo', 'dnf', *rest]
    if head in ('flatpak', '/usr/bin/flatpak'):
        if len(args) < 2:
            raise ValueError('Add what flatpak should do, like: flatpak install flathub org.gimp.GIMP')
        return ['flatpak', *args[1:]]
    # Bare names: a quick install. Package names only, no options.
    for name in args:
        if not NAME.match(name):
            raise ValueError('“{}” isn’t a package name. Type a name, or a dnf or flatpak command.'.format(name))
    apps = [a[len(FLATHUB_PREFIX):] for a in args if a.startswith(FLATHUB_PREFIX)]
    packages = [a for a in args if not a.startswith(FLATHUB_PREFIX)]
    if apps and packages:
        raise ValueError('Install Flathub apps and dnf packages separately.')
    if apps:
        return ['flatpak', 'install', 'flathub', *apps]
    return ['sudo', 'dnf', 'install', *packages]


class Console:
    def __init__(self):
        self.screen = pyte.HistoryScreen(COLUMNS, ROWS, history=2000)
        self.stream = pyte.ByteStream(self.screen)
        self.master = None
        self.pid = None
        self.secret = False
        self.notice = ''
        self.dirty = True
        self.stream.feed(WELCOME.encode())

    def emit(self):
        history = [''.join(row[i].data for i in range(self.screen.columns)).rstrip() for row in self.screen.history.top]
        text = '\n'.join(history + [row.rstrip() for row in self.screen.display]).rstrip()
        print(json.dumps(dict(output=text, running=self.pid is not None, secret=self.secret, notice=self.notice)), flush=True)
        self.dirty = False

    def write_output(self, text):
        self.stream.feed(text.encode())
        self.dirty = True

    def echo_off(self):
        try:
            return self.master is not None and not (termios.tcgetattr(self.master)[3] & termios.ECHO)
        except termios.error:
            return False

    def start(self, text, command=None):
        if self.pid is not None:
            return
        shown = text
        if command is None:
            command = build_command(text)
            shown = ' '.join(shlex.quote(a) for a in command)
        self.notice = ''
        self.write_output('$ ' + shown + '\r\n')
        pid, fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env.update(TERM='xterm', LC_ALL='C.UTF-8', COLUMNS=str(COLUMNS), LINES=str(ROWS))
            try:
                os.execvpe(command[0], command, env)
            except OSError as error:
                os.write(1, ('{}: {}\r\n'.format(command[0], error.strerror)).encode())
                os._exit(127)
        self.pid, self.master = pid, fd
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', ROWS, COLUMNS, 0, 0))
        os.set_blocking(fd, False)
        self.dirty = True

    def input(self, text, secret):
        if self.master is None:
            return
        # Refuse stale UI input rather than risk echoing a password at a new prompt.
        if bool(secret) != bool(self.echo_off()):
            self.notice = 'The prompt changed. Please enter your response again.'
            self.dirty = True
            return
        if any(c in text for c in ('\n', '\r', '\x00')):
            raise ValueError('Enter one response at a time.')
        os.write(self.master, (text + '\n').encode())
        self.notice = ''

    def interrupt(self):
        if self.master is not None:
            os.write(self.master, b'\x03')

    def read(self):
        if self.master is None:
            return
        for _ in range(32):
            try:
                data = os.read(self.master, 8192)
                if not data:
                    break
                self.stream.feed(data)
                self.dirty = True
            except (BlockingIOError, OSError):
                break
        secret = bool(self.echo_off())
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
            self.write_output('\r\n' + ('Done.' if code == 0 else '[Exit ' + str(code) + ']') + '\r\n\r\n')


def main():
    console = Console()
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin, selectors.EVENT_READ)
    incoming = b''
    console.emit()
    try:
        while True:
            for key, _ in selector.select(0.05 if console.pid else None):
                data = os.read(key.fd, 65536)
                if not data:
                    return
                incoming += data
                while b'\n' in incoming:
                    line, incoming = incoming.split(b'\n', 1)
                    try:
                        request = json.loads(line)
                        action = request.get('action')
                        if action == 'start':
                            console.start(request.get('text', ''))
                        elif action == 'input':
                            console.input(request.get('text', ''), request.get('secret', False))
                        elif action == 'interrupt':
                            console.interrupt()
                        elif action == 'clear' and console.pid is None:
                            console.screen.reset()
                            console.dirty = True
                    except ValueError as error:
                        # Only our own messages; the typed text itself is never echoed back.
                        console.notice = str(error) if str(error) else 'Could not process that input.'
                        console.dirty = True
                    except OSError:
                        console.notice = 'Could not process that input. Type an app name, or a dnf or flatpak command.'
                        console.dirty = True
                    finally:
                        line = b''
                        request = None
            console.read()
            if console.dirty:
                console.emit()
    finally:
        if console.master is not None:
            os.close(console.master)


if __name__ == '__main__':
    main()
