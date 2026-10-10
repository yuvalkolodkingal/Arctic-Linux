"""Actual sleeping-child cancellation fixtures; no VM or performance qualification."""
import ast
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'tools/performance/run-paired.py'


class OwnedCommandCleanup(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.root = Path(self.directory.name)
        self.log = self.root / 'harness.log'
        self.children = []
        self.stages = []
        self.engine_calls = []
        self.signal_calls = []
        self.state = {'task_id': uuid.uuid4().hex}
        self.old_mask = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        self.old_handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        def interrupted(signum, frame):
            raise InterruptedError('actual fixture cancellation ' + str(signum))
        self.interrupted = interrupted
        for s in self.old_handlers:
            signal.signal(s, interrupted)
        self.popen = self.start_child
        self.killpg = os.killpg
        self.sigmask = signal.pthread_sigmask
        self.contextmanager = contextmanager
        self.save = self.stages.append
        self.remaining_container = False
        self.engine_signal = False

    def tearDown(self):
        # Only processes freshly created and retained by this fixture can be killed.
        for child in self.children:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=5)
        for s, handler in self.old_handlers.items():
            signal.signal(s, handler)
        signal.pthread_sigmask(signal.SIG_SETMASK, self.old_mask)
        self.directory.cleanup()

    def start_child(self, argv, **kwargs):
        self.assertTrue(kwargs['start_new_session'])
        inherited = signal.pthread_sigmask(signal.SIG_BLOCK, set())
        self.assertFalse({signal.SIGTERM, signal.SIGINT} & inherited)
        child = subprocess.Popen(argv, **kwargs)
        self.children.append(child)
        return child

    def engine_run(self, argv, **kwargs):
        self.engine_calls.append(argv)
        if argv[1] == 'rm':
            if self.engine_signal:
                os.kill(os.getpid(), signal.SIGTERM)
                os.kill(os.getpid(), signal.SIGINT)
            # A container started with --rm may already be absent.
            return subprocess.CompletedProcess(argv, 1)
        self.assertEqual(argv[1:4], ['ps', '--all', '--filter'])
        self.assertEqual(argv[5:], ['--format', '{{.Names}}'])
        name = argv[4].removeprefix('name=')
        return subprocess.CompletedProcess(argv, 0, stdout=(name + '\n').encode() if self.remaining_container else b'')

    def execute(self, program='import time; time.sleep(60)', *, timeout=1, vm=False, provision=False):
        tree = ast.parse(SOURCE.read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        function = next(node for node in main.body if isinstance(node, ast.FunctionDef) and node.name == 'execute')
        namespace = dict(contextmanager=self.contextmanager, json=json, uuid=uuid,
            os=types.SimpleNamespace(environ=os.environ, killpg=self.killpg),
            signal=types.SimpleNamespace(SIGTERM=signal.SIGTERM, SIGINT=signal.SIGINT,
                SIGKILL=signal.SIGKILL, SIG_BLOCK=signal.SIG_BLOCK, SIG_SETMASK=signal.SIG_SETMASK,
                signal=signal.signal, pthread_sigmask=self.sigmask),
            subprocess=types.SimpleNamespace(Popen=self.popen, run=self.engine_run, PIPE=subprocess.PIPE,
                STDOUT=subprocess.STDOUT, TimeoutExpired=subprocess.TimeoutExpired),
            ROOT=self.root, state=self.state, save=self.save, engine='fixture-engine',
            prepared_id='sha256:' + '1' * 64)
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        return namespace['execute']([sys.executable, '-c', program], self.log, timeout, vm=vm, provision=provision)

    def assert_reaped(self):
        self.assertTrue(self.children)
        for child in self.children:
            self.assertIsNotNone(child.returncode)
            with self.assertRaises(ChildProcessError):
                os.waitpid(child.pid, os.WNOHANG)

    def failure_receipts(self):
        prefix = 'ARCTIC-OWNED-COMMAND-CLEANUP='
        return [json.loads(line[len(prefix):]) for line in self.log.read_text().splitlines() if line.startswith(prefix)]

    def test_actual_signal_after_popen_before_assignment_does_not_leak_detached_child(self):
        def start(argv, **kwargs):
            child = self.start_child(argv, **kwargs)
            os.kill(os.getpid(), signal.SIGINT)
            return child
        self.popen = start
        with self.assertRaises(InterruptedError): self.execute(vm=True)
        self.assert_reaped()
        self.assertTrue(self.state['interrupted_command']['child_acquired'])
        self.assertTrue(self.failure_receipts())
        self.assertEqual([call[1] for call in self.engine_calls], ['rm', 'ps'])

    def test_pending_signal_at_atomic_handler_restore_still_reaps_acquired_child(self):
        restores = 0
        def mask(operation, values):
            nonlocal restores
            if operation == signal.SIG_SETMASK:
                restores += 1
                if restores == 2:
                    os.kill(os.getpid(), signal.SIGTERM)
            return signal.pthread_sigmask(operation, values)
        self.sigmask = mask
        with self.assertRaises(InterruptedError): self.execute()
        self.assert_reaped()
        self.assertTrue(self.failure_receipts())

    def test_pending_signal_during_acquisition_install_is_queued_with_unmasked_child(self):
        restores = 0
        def mask(operation, values):
            nonlocal restores
            if operation == signal.SIG_SETMASK:
                restores += 1
                if restores == 1:
                    os.kill(os.getpid(), signal.SIGTERM)
            return signal.pthread_sigmask(operation, values)
        self.sigmask = mask
        with self.assertRaises(InterruptedError): self.execute()
        self.assert_reaped()
        self.assertIn(signal.SIGTERM, self.failure_receipts()[-1]['deferred_signals'])

    def test_repeated_signals_during_wait_and_container_cleanup_cannot_skip_reap(self):
        def start(argv, **kwargs):
            child = self.start_child(argv, **kwargs)
            wait = child.wait
            calls = 0
            def repeated(timeout=None):
                nonlocal calls
                calls += 1
                if calls == 2:
                    os.kill(os.getpid(), signal.SIGTERM)
                    os.kill(os.getpid(), signal.SIGINT)
                return wait(timeout=timeout)
            child.wait = repeated
            return child
        self.popen = start
        self.engine_signal = True
        with self.assertRaises(subprocess.TimeoutExpired): self.execute(timeout=.02, vm=True)
        self.assert_reaped()
        self.assertEqual([call[1] for call in self.engine_calls], ['rm', 'ps'])
        self.assertGreaterEqual(len(self.failure_receipts()[-1]['deferred_signals']), 4)

    def test_save_io_failure_still_stops_child_removes_container_and_keeps_failed_log(self):
        def save(phase):
            self.stages.append(phase)
            raise OSError('synthetic owned status write failure')
        self.save = save
        with self.assertRaises(subprocess.TimeoutExpired): self.execute(timeout=.02, provision=True)
        self.assert_reaped()
        self.assertEqual([call[1] for call in self.engine_calls], ['rm', 'ps'])
        self.assertTrue(any('save failed command: OSError' in r['cleanup_errors'] for r in self.failure_receipts()))

    def test_term_failure_still_waits_kills_and_reaps_actual_child(self):
        def killpg(pid, signum):
            self.signal_calls.append((pid, signum))
            if signum == signal.SIGTERM:
                raise PermissionError('synthetic first stop failure')
            return os.killpg(pid, signum)
        self.killpg = killpg
        began = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired): self.execute(timeout=.02, vm=True)
        self.assert_reaped()
        self.assertLess(time.monotonic() - began, 20)
        self.assertEqual([s for _, s in self.signal_calls], [signal.SIGTERM, signal.SIGKILL])
        self.assertTrue(any('TERM: PermissionError' in r['cleanup_errors'] for r in self.failure_receipts()))
        self.assertEqual([call[1] for call in self.engine_calls], ['rm', 'ps'])

    def test_signal_queued_after_cleanup_final_body_check_cannot_be_swallowed(self):
        scopes = 0
        def manager(function):
            if function.__name__ != 'defer_signals':
                return contextmanager(function)
            @contextmanager
            def wrapped():
                nonlocal scopes
                scopes += 1
                number = scopes
                with contextmanager(function)() as pending:
                    try:
                        yield pending
                    finally:
                        if number == 2:
                            os.kill(os.getpid(), signal.SIGINT)
            return wrapped
        self.contextmanager = manager
        with self.assertRaises(InterruptedError): self.execute('pass')
        self.assert_reaped()
        self.assertTrue(self.failure_receipts())
        self.assertEqual(self.failure_receipts()[-1]['failure_type'], 'InterruptedError')

    def test_container_removal_requires_exact_owned_absence_and_never_other_name(self):
        self.remaining_container = True
        with self.assertRaisesRegex(RuntimeError, 'owned cleanup failed'): self.execute('pass', vm=True)
        self.assert_reaped()
        name = self.engine_calls[0][-1]
        self.assertTrue(name.startswith('arctic-paired-' + self.state['task_id'] + '-'))
        self.assertEqual(self.engine_calls[1][4], 'name=' + name)
        self.assertIn('owned container absence: not proved', self.failure_receipts()[-1]['cleanup_errors'])

    def test_creator_failure_has_no_child_and_still_checks_reserved_container_absence(self):
        def fail(*args, **kwargs): raise FileNotFoundError('synthetic creator failure')
        self.popen = fail
        with self.assertRaises(FileNotFoundError): self.execute(vm=True)
        self.assertEqual(self.children, [])
        self.assertFalse(self.failure_receipts()[-1]['child_acquired'])
        self.assertEqual([call[1] for call in self.engine_calls], ['rm', 'ps'])

    def test_partial_name_match_is_foreign_and_is_never_removed(self):
        original = self.engine_run
        def foreign(argv, **kwargs):
            result = original(argv, **kwargs)
            if argv[1] == 'ps':
                name = argv[4].removeprefix('name=')
                return subprocess.CompletedProcess(argv, 0, stdout=(name + '-foreign\n').encode())
            return result
        self.engine_run = foreign
        self.execute('pass', vm=True)
        self.assert_reaped()
        self.assertEqual([call[1] for call in self.engine_calls], ['rm', 'ps'])
        self.assertNotIn('-foreign', self.engine_calls[0][-1])

    def test_failed_container_inventory_cannot_claim_absence(self):
        original = self.engine_run
        def failed(argv, **kwargs):
            result = original(argv, **kwargs)
            if argv[1] == 'ps': return subprocess.CompletedProcess(argv, 2, stdout=b'')
            return result
        self.engine_run = failed
        with self.assertRaisesRegex(RuntimeError, 'owned cleanup failed'): self.execute('pass', vm=True)
        self.assert_reaped()

    def test_normal_completion_restores_handlers_and_absent_auto_removed_container_is_benign(self):
        self.execute('pass', vm=True)
        self.assert_reaped()
        self.assertEqual(self.failure_receipts(), [])
        for signum in self.old_handlers:
            self.assertIs(signal.getsignal(signum), self.interrupted)
        self.assertEqual(signal.pthread_sigmask(signal.SIG_BLOCK, set()), self.old_mask)

    def test_nonzero_exit_is_preserved_and_reaped(self):
        with self.assertRaisesRegex(RuntimeError, 'harness exit 7'):
            self.execute('raise SystemExit(7)', provision=True)
        self.assert_reaped()
        self.assertEqual(self.children[0].returncode, 7)
        self.assertTrue(self.failure_receipts())


if __name__ == '__main__':
    unittest.main()
