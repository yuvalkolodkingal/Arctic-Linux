"""Real owned producer cancellation and unreaped-group lifecycle controls."""
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('journal_owned_lifecycle_native', HERE / 'native_smoke.py')
N = importlib.util.module_from_spec(spec)
spec.loader.exec_module(N)
spec = importlib.util.spec_from_file_location('journal_owned_lifecycle_guest', HERE.parent / 'installer-qualification/guest.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)
ARGV = ['journalctl', '-b', '--no-pager', '--after-cursor', 'owned-public-cursor', '-o', 'json', '--quiet']


class OwnedJournalLifecycle(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='arctic-journal-owned-lifecycle-')
        self.root = Path(self.tmp.name)
        self.children = []
        self.descendants = []
        self.old = {value: signal.getsignal(value) for value in (signal.SIGINT, signal.SIGTERM)}
        self.real_popen = subprocess.Popen

    def tearDown(self):
        try:
            for child in self.children:
                self.assertIsNotNone(child.returncode, 'Owned leader was not reaped')
                self.assertTrue(child.stdout.closed and child.stderr.closed, 'Owned pipe was not closed')
                with self.assertRaises(ChildProcessError):
                    os.waitpid(child.pid, os.WNOHANG)
            for pid in self.descendants:
                self.assert_stopped(pid)
            self.assertEqual({value: signal.getsignal(value) for value in self.old}, self.old)
        finally:
            # A failed control must still clean only its own known processes.
            for child in self.children:
                if child.poll() is None:
                    try: os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError: pass
                    child.wait(timeout=3)
            for pid in self.descendants:
                try: os.kill(pid, signal.SIGKILL)
                except ProcessLookupError: pass
            for value, handler in self.old.items():
                signal.signal(value, handler)
            self.tmp.cleanup()

    def assert_stopped(self, pid):
        end = time.monotonic() + 2
        while time.monotonic() < end:
            try: state = (Path('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[0]
            except FileNotFoundError: return
            if state in ('Z', 'X'): return
            time.sleep(.01)
        self.fail('Owned descendant remained running')

    def route(self, code, after_acquire=None):
        def acquire(argv, **kwargs):
            self.assertEqual(argv, ARGV)
            child = self.real_popen([sys.executable, '-c', code], **kwargs)
            self.children.append(child)
            if after_acquire is not None:
                after_acquire(child)
            return child
        return mock.patch.object(N.subprocess, 'Popen', side_effect=acquire)

    def fork_source(self, status=0):
        note = self.root / 'public-child-pid'
        source = ('import os,time\nchild=os.fork()\n'
                  f'if child:\n open({str(note)!r},"w").write(str(child));raise SystemExit({status})\n'
                  'os.close(1);os.close(2);time.sleep(30)\n')
        return source, note

    def retain_descendant(self, note):
        pid = int(note.read_text())
        self.descendants.append(pid)
        return pid

    def test_real_SIGINT_after_acquisition_before_assignment_is_reaped(self):
        with self.route('import time;time.sleep(30)', lambda child: signal.raise_signal(signal.SIGINT)):
            with self.assertRaises(KeyboardInterrupt):
                N.execute_journal_interval(ARGV, timeout=1)
        self.assertEqual(self.children[0].returncode, -signal.SIGKILL)

    def test_real_SIGTERM_after_acquisition_before_assignment_is_reaped(self):
        with self.route('import time;time.sleep(30)', lambda child: signal.raise_signal(signal.SIGTERM)):
            with self.assertRaises(InterruptedError):
                N.execute_journal_interval(ARGV, timeout=1)
        self.assertEqual(self.children[0].returncode, -signal.SIGKILL)

    def test_success_closed_pipe_descendant_stopped_before_leader_reap(self):
        source, note = self.fork_source()
        events = []
        real_kill = os.killpg
        def stop(pid, sig):
            leader = self.children[0]
            self.assertIsNone(leader.returncode)
            info = os.waitid(os.P_PID, leader.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            self.assertIsNotNone(info)
            self.assertEqual(info.si_code, os.CLD_EXITED)
            self.assertEqual(info.si_status, 0)
            events.append('stop-while-leader-reserved')
            return real_kill(pid, sig)
        with self.route(source), mock.patch.object(N.os, 'killpg', side_effect=stop):
            self.assertEqual(N.execute_journal_interval(ARGV, timeout=2), (0, '', ''))
        self.retain_descendant(note)
        self.assertEqual(events, ['stop-while-leader-reserved'])
        self.assertEqual(self.children[0].returncode, 0)

    def test_nonzero_real_status_retained_and_closed_pipe_descendant_stopped(self):
        source, note = self.fork_source(7)
        with self.route(source):
            try: N.execute_journal_interval(ARGV, timeout=2)
            except RuntimeError as error:
                row = G.security_finalization_diagnostic(error, N)
            else: self.fail('Nonzero real leader status was accepted')
        self.retain_descendant(note)
        self.assertEqual(row['guard'], 'guard-019')
        self.assertEqual(row['exit_code'], 7)
        self.assertEqual(self.children[0].returncode, 7)

    def test_real_signal_status_uses_original_negative_returncode(self):
        with self.route('import os,signal;os.kill(os.getpid(),signal.SIGUSR1)'):
            try: N.execute_journal_interval(ARGV, timeout=2)
            except RuntimeError as error: row = G.security_finalization_diagnostic(error, N)
            else: self.fail('Signaled real leader status was accepted')
        self.assertEqual(row['guard'], 'guard-019')
        self.assertEqual(row['exit_code'], -signal.SIGUSR1)
        self.assertEqual(self.children[0].returncode, -signal.SIGUSR1)

    def test_closed_pipe_running_leader_observed_under_original_deadline(self):
        with self.route('import os,time;os.close(1);os.close(2);time.sleep(30)'):
            start = time.monotonic()
            with self.assertRaises(subprocess.TimeoutExpired):
                N.execute_journal_interval(ARGV, timeout=.1)
        self.assertLess(time.monotonic() - start, 1)
        self.assertEqual(self.children[0].returncode, -signal.SIGKILL)

    def test_repeated_real_SIGINT_during_group_cleanup_does_not_interrupt_owned_stop(self):
        real_kill = os.killpg
        def stop(pid, sig):
            signal.raise_signal(signal.SIGINT)
            signal.raise_signal(signal.SIGINT)
            return real_kill(pid, sig)
        with self.route('import time;time.sleep(30)', lambda child: signal.raise_signal(signal.SIGINT)), \
                mock.patch.object(N.os, 'killpg', side_effect=stop):
            with self.assertRaises(KeyboardInterrupt):
                N.execute_journal_interval(ARGV, timeout=1)
        self.assertEqual(self.children[0].returncode, -signal.SIGKILL)

    def test_foreign_reap_fails_closed_and_never_kills_released_group_id(self):
        real_waitid = os.waitid
        released = False
        def observe(*args):
            nonlocal released
            value = real_waitid(*args)
            if value is not None:
                self.children[0].wait(timeout=1)
                released = True
                raise ChildProcessError('Owned public control reaped the leader')
            return value
        with self.route('raise SystemExit(0)'), mock.patch.object(N.os, 'waitid', side_effect=observe), \
                mock.patch.object(N.os, 'killpg') as stop:
            with self.assertRaises(ChildProcessError):
                N.execute_journal_interval(ARGV, timeout=1)
        self.assertTrue(released)
        stop.assert_not_called()

    def test_selector_construction_failure_stops_acquired_child_and_preserves_identity(self):
        error = OSError('PRIVATE_SELECTOR_SENTINEL')
        with self.route('import time;time.sleep(30)'), \
                mock.patch.object(N.selectors, 'DefaultSelector', side_effect=error):
            try: N.execute_journal_interval(ARGV, timeout=1)
            except OSError as actual: self.assertIs(actual, error)
            else: self.fail('Selector construction failure was lost')
        self.assertEqual(self.children[0].returncode, -signal.SIGKILL)


if __name__ == '__main__':
    unittest.main(verbosity=2)
