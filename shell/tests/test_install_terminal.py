import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
import unittest

spec = importlib.util.spec_from_file_location('install_terminal', Path(__file__).parents[1]/'scripts/install-terminal.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

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
        self.assertIn('[Exit 0]', output)

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
