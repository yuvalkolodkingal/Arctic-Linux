#!/home/bitzonx/.local/opt/quickshell-wallpaper-venv/bin/python
"""Line-oriented emerge console over a real PTY. Input is never logged."""
import fcntl
import json
import os
import pty
import selectors
import shlex
import signal
import struct
import sys
import termios
import time
import pyte

class Console:
    def __init__(self):
        self.screen = pyte.HistoryScreen(76, 26, history=1000)
        self.stream = pyte.ByteStream(self.screen)
        self.master = None
        self.pid = None
        self.secret = False
        self.notice = ''
        self.dirty = True
        self.stream.feed(b'Portage\r\nType a package name or an emerge command.\r\nExample: emerge --ask app-editors/neovim\r\n\r\n')

    def emit(self):
        history = [''.join(row[i].data for i in range(self.screen.columns)).rstrip() for row in self.screen.history.top]
        text = '\n'.join(history + self.screen.display).rstrip()
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
        if command is None:
            args = shlex.split(text)
            if not args:
                return
            if args[0] in ('emerge', '/usr/bin/emerge'):
                args.pop(0)
            if not args:
                raise ValueError('Enter a package name or emerge arguments.')
            if any(c in text for c in ('\n', '\r', '\x00')):
                raise ValueError('Enter one emerge command at a time.')
            command = ['/usr/bin/doas', '/usr/bin/emerge', '--ask', *args]
        self.notice = ''
        self.write_output('$ ' + text + '\r\n')
        pid, fd = pty.fork()
        if pid == 0:
            env = os.environ.copy()
            env.update(TERM='xterm', LC_ALL='C.UTF-8')
            os.execvpe(command[0], command, env)
        self.pid, self.master = pid, fd
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', 26, 76, 0, 0))
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
            self.write_output('\r\n[Exit ' + str(os.waitstatus_to_exitcode(status)) + ']\r\n')


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
                            console.screen.reset(); console.dirty = True
                    except (ValueError, OSError):
                        console.notice = 'Could not process that input. Enter a package name or emerge command.'
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
