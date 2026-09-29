"""Tests for arctic-remind (dotfiles/.local/bin): the words it understands (the same cases as the
launcher's, tests/fixtures/reminders.json), and setting, listing, firing and cancelling with
stand-ins for systemd-run, systemctl and notify-send.

Run: python3 -m unittest discover -s shell/tests
"""
import importlib.machinery
import importlib.util
import json
import os
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-remind'
CASES = json.loads((Path(__file__).parent / 'fixtures' / 'reminders.json').read_text())


def load():
    sys.dont_write_bytecode = True     # nothing written next to the helper
    loader = importlib.machinery.SourceFileLoader('arctic_remind', str(HELPER))
    spec = importlib.util.spec_from_loader('arctic_remind', loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class GrammarTests(unittest.TestCase):
    def test_the_launchers_cases(self):
        remind = load()
        for text, want in CASES:
            with self.subTest(text=text):
                got = remind.parse(text)
                self.assertEqual(got, want and dict(want))

    def test_a_time_that_has_passed_is_tomorrow(self):
        remind = load()
        now = datetime(2026, 9, 28, 18, 0, 0)
        self.assertEqual(remind.due_time(remind.parse('17:30 x'), now), datetime(2026, 9, 29, 17, 30))
        self.assertEqual(remind.due_time(remind.parse('19:00 x'), now), datetime(2026, 9, 28, 19, 0))
        self.assertEqual(remind.due_time(remind.parse('10m x'), now), datetime(2026, 9, 28, 18, 10))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.state = root / 'state'
        self.bin = root / 'bin'
        self.bin.mkdir()
        self.log = root / 'calls'
        self.answer = root / 'answer'

        def stub(name, body):
            (self.bin / name).write_text('#!/bin/sh\n' + body + '\n')
            (self.bin / name).chmod(0o755)
        stub('systemd-run', 'echo "systemd-run $*" >> "{}"'.format(self.log))
        stub('systemctl', 'echo "systemctl $*" >> "{}"'.format(self.log))
        stub('notify-send', 'echo "notify $*" >> "{0}"; cat "{1}" 2>/dev/null'.format(self.log, self.answer))
        self.env = dict(os.environ, XDG_STATE_HOME=str(self.state), PATH=str(self.bin) + ':/usr/bin:/bin')

    def tearDown(self):
        self.tmp.cleanup()

    def remind(self, *args, code=0):
        out = subprocess.run([sys.executable, str(HELPER)] + list(args), env=self.env, capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stdout + out.stderr)
        return out.stdout

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def saved(self):
        return json.loads((self.state / 'arctic' / 'reminders.json').read_text())['reminders']

    def test_set_list_fire_and_snooze(self):
        out = json.loads(self.remind('--', "10m tea; don't forget"))
        self.assertEqual(out['text'], "tea; don't forget")
        ident = out['id']
        run = [c for c in self.calls() if c.startswith('systemd-run')][0]
        self.assertIn('--user', run)
        self.assertIn('--unit arctic-reminder-' + ident, run)
        self.assertIn('--on-calendar', run)
        self.assertTrue(run.endswith('arctic-remind fire ' + ident), run)
        self.assertNotIn('tea', run, 'what it says stays off the command line')
        self.assertEqual(oct((self.state / 'arctic' / 'reminders.json').stat().st_mode & 0o777), '0o600')
        self.assertIn(ident, self.remind('list'))
        self.remind('pending')
        # The timer fires; the person picks "Again in 10 minutes".
        self.answer.write_text('snooze\n')
        self.remind('fire', ident)
        again = self.saved()
        self.assertEqual(len(again), 1)
        self.assertNotEqual(again[0]['id'], ident)
        self.assertEqual(again[0]['text'], "tea; don't forget")
        self.assertTrue(any('-u critical' in c and 'Again in 10 minutes' in c for c in self.calls()))

    def test_snooze_keeps_a_text_that_starts_with_a_number(self):
        ident = json.loads(self.remind('8pm', '2', 'pills'))['id']
        self.answer.write_text('snooze\n')
        before = time.time()
        self.remind('fire', ident)
        again = self.saved()
        self.assertEqual([r['text'] for r in again], ['2 pills'])
        self.assertTrue(before + 590 <= again[0]['due'] <= time.time() + 610, again)

    def test_cancel(self):
        ident = json.loads(self.remind('17:30', 'call', 'Ana'))['id']
        self.remind('10m', 'tea')
        self.assertEqual(json.loads(self.remind('cancel', ident))['cancelled'], 1)
        self.assertIn('systemctl --user stop arctic-reminder-{}.timer'.format(ident), self.calls())
        self.assertEqual([r['text'] for r in self.saved()], ['tea'])
        self.remind('cancel', 'all')
        self.assertEqual(self.saved(), [])
        self.remind('pending', code=1)
        self.remind('cancel', 'nope', code=1)

    def test_no_when_no_reminder(self):
        out = json.loads(self.remind('tea', code=1))
        self.assertFalse(out['ok'])
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
