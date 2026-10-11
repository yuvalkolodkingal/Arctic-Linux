"""Actual idle preparation waits through the asynchronous page/engine handoff."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))
import guest as G


class FillObserved(Exception):
    pass


class IdleReadinessTests(unittest.TestCase):
    def execute_prepare(self, transitions):
        value = G.Installer.__new__(G.Installer)
        value.deadline = 100
        value.gui_pid = 12345
        value.find_gui = Mock()
        value.identities = Mock()
        value.assert_gui_identity = Mock()
        clock = SimpleNamespace(now=0.0, index=0, next_seen=False)
        welcome = dict(page='welcome', current='welcome', ready=True, connected=True)
        calls = []
        waits = []

        def state():
            return transitions[min(clock.index, len(transitions)-1)] if clock.next_seen else welcome

        def command(argv, desktop=False):
            self.assertTrue(desktop)
            self.assertEqual(argv[:6], ['quickshell', 'ipc', '--pid', '12345', 'call', 'installer'])
            calls.append((argv[6], dict(state()), clock.now))
            if argv[6] == 'next':
                clock.next_seen = True
                return (0, 'ok', '')
            self.assertEqual(argv[6], 'fill')
            self.assertEqual(json.loads(argv[7]), {'layout': 'il', 'variant': ''})
            raise FillObserved()

        def ipc(method, payload=None):
            if method == 'state':
                return json.dumps(state())
            return G.Installer.ipc(value, method, payload)

        def sleep(seconds):
            clock.now += seconds
            clock.index += 1

        def wait(predicate, seconds, reason):
            waits.append((seconds, reason))
            return G.Installer.wait(value, predicate, seconds, reason)

        value.command = command
        value.ipc = ipc
        value.wait = wait
        rpc = SimpleNamespace(snapshot=lambda: {'wizard': {'current': 'welcome'}})
        with patch.object(G, 'EngineRPC', return_value=rpc), patch.object(
                G, 'time', SimpleNamespace(monotonic=lambda: clock.now, sleep=sleep)):
            try:
                G.Installer.prepare(value)
            except (FillObserved, RuntimeError) as error:
                return error, calls, waits, clock.now
        self.fail('Preparation unexpectedly continued beyond the first Hebrew fill')

    def test_actual_prepare_waits_for_page_current_and_ready_before_real_fill_guard(self):
        states = [dict(page='keyboard', current='welcome', ready=False),
                  dict(page='keyboard', current='keyboard', ready=False),
                  dict(page='keyboard', current='keyboard', ready=True)]
        error, calls, waits, elapsed = self.execute_prepare(states)
        self.assertIsInstance(error, FillObserved)
        self.assertEqual([c[0] for c in calls], ['next', 'fill'])
        self.assertEqual(calls[-1][1], states[-1])
        self.assertAlmostEqual(elapsed, .4)
        self.assertEqual(waits, [(15, 'real keyboard page did not load')])

    def test_incomplete_or_non_boolean_readiness_keeps_original_timeout_and_never_fills(self):
        for state in (dict(page='keyboard', current='welcome', ready=True),
                      dict(page='keyboard', current='keyboard', ready=False),
                      dict(page='keyboard', current='keyboard', ready=1),
                      dict(page='keyboard', current='keyboard'),
                      dict(page='welcome', current='keyboard', ready=True)):
            with self.subTest(state=state):
                error, calls, waits, elapsed = self.execute_prepare([state])
                self.assertIsInstance(error, RuntimeError)
                self.assertEqual(str(error), 'real keyboard page did not load')
                self.assertEqual([c[0] for c in calls], ['next'])
                self.assertGreaterEqual(elapsed, 15)
                self.assertLess(elapsed, 15.21)
                self.assertEqual(waits, [(15, 'real keyboard page did not load')])

    def test_already_ready_keyboard_proceeds_without_delay_or_extra_next(self):
        ready = dict(page='keyboard', current='keyboard', ready=True)
        error, calls, waits, elapsed = self.execute_prepare([ready])
        self.assertIsInstance(error, FillObserved)
        self.assertEqual([c[0] for c in calls], ['next', 'fill'])
        self.assertEqual(elapsed, 0)
        self.assertEqual(waits, [(15, 'real keyboard page did not load')])


if __name__ == '__main__':
    unittest.main()
