"""Actual signal/owned-child controls; no VM or fabricated performance result."""
import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('external_owned_cleanup',
    ROOT/'tools/performance/qualification.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class Child:
    pid = 123456789  # Synthetic PID; killpg is always patched for this object.
    def __init__(self, first_wait=None, cleanup_wait=None):
        self.returncode = None
        self.waits = []
        self.first_wait = first_wait
        self.cleanup_wait = cleanup_wait
    def poll(self):
        return self.returncode
    def wait(self, timeout=None):
        self.waits.append(timeout)
        if len(self.waits) == 1 and self.first_wait:
            return self.first_wait()
        if len(self.waits) == 2 and self.cleanup_wait:
            return self.cleanup_wait()
        self.returncode = 0
        return self.returncode


class OwnedCleanupTest(unittest.TestCase):
    def setUp(self):
        self.handlers = {s: signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.args = types.SimpleNamespace(manifest=root/'manifest.json', source=root/'source',
            inputs=root/'inputs', work=root/'work', evidence=root/'evidence', screened=root/'screened')
        self.args.manifest.write_text('{}\n')
        self.args.inputs.mkdir()
        (self.args.inputs/'PERFORMANCE-PLAN.json').write_text('{}\n')
        self.plan = dict(image=dict(name='test.iso', source_sha='a'*40, sha256='b'*64),
            observer={}, candidate_source_files={}, execution_files={})
        def require(condition, reason):
            if not condition:
                raise ValueError(reason)
        self.contract = types.SimpleNamespace(require=require, BASELINE={}, validate_evidence=Mock())
        self.screens = []
        def screen(source, target):
            self.screens.append(json.loads((source/'execution.json').read_text())['status'])
            shutil.copytree(source, target)
        self.screen = types.SimpleNamespace(screen_external=screen)
        self.stack = []
        for context in (patch.object(runner, 'C', self.contract),
                patch.object(runner, 'activation', return_value=(self.plan, 'c'*40)),
                patch.object(runner, 'verify', return_value={}),
                patch.object(runner, 'baseline', return_value=root/'original.iso'),
                patch.object(runner, 'load', side_effect=lambda name, path:
                    self.screen if name == 'paired_screen' else types.SimpleNamespace()),
                patch.dict(os.environ, GITHUB_RUN_ID='31', GITHUB_SHA='d'*40)):
            context.start()
            self.stack.append(context)
        self.addCleanup(self.restore)

    def restore(self):
        for context in reversed(self.stack):
            context.stop()
        for signum, handler in self.handlers.items():
            signal.signal(signum, handler)

    def failed_evidence(self):
        for root in (self.args.evidence, self.args.screened):
            state = json.loads((root/'execution.json').read_text())
            self.assertEqual(state['status'], 'frozen_external_paired_failed')
            self.assertFalse(state['release_acceptance'])
            self.assertIn('runner-cleanup.json', state['files'])
        self.contract.validate_evidence.assert_not_called()
        for signum, handler in self.handlers.items():
            self.assertIs(signal.getsignal(signum), handler)

    def test_signal_between_actual_child_spawn_and_ownership_handoff_reaps_child(self):
        actual_popen = subprocess.Popen
        acquired = []
        def spawn(*args, **kwargs):
            child = actual_popen([sys.executable, '-c', 'import time; time.sleep(60)'],
                start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            acquired.append(child)
            os.kill(os.getpid(), signal.SIGINT)  # Arrives before run() assigns child.
            return child
        try:
            with patch.object(runner.subprocess, 'Popen', side_effect=spawn):
                with self.assertRaises(InterruptedError):
                    runner.run(self.args)
            self.assertEqual(len(acquired), 1)
            self.assertIsNotNone(acquired[0].poll())
            with self.assertRaises(ProcessLookupError):
                os.kill(acquired[0].pid, 0)
            self.failed_evidence()
        finally:
            for child in acquired:
                if child.poll() is None:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait(timeout=5)

    def test_repeated_actual_signals_during_stop_wait_do_not_skip_kill_reap_or_save(self):
        def first_wait():
            os.kill(os.getpid(), signal.SIGTERM)
        def cleanup_wait():
            os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGTERM)
            raise subprocess.TimeoutExpired('owned fixture', 60)
        child = Child(first_wait, cleanup_wait)
        with patch.object(runner.subprocess, 'Popen', return_value=child), \
                patch.object(runner.os, 'killpg') as kill:
            with self.assertRaises(InterruptedError):
                runner.run(self.args)
        self.assertEqual(child.waits, [None, runner.CLEANUP_GRACE_SECONDS, 15])
        self.assertEqual(kill.call_args_list[0].args, (child.pid, signal.SIGTERM))
        self.assertEqual(kill.call_args_list[1].args, (child.pid, signal.SIGKILL))
        receipt = json.loads((self.args.evidence/'runner-cleanup.json').read_text())
        self.assertEqual(receipt['deferred_signals'], [signal.SIGINT, signal.SIGTERM])
        self.failed_evidence()

    def test_term_failure_still_attempts_both_waits_kill_and_failed_screening(self):
        def first_wait():
            raise RuntimeError('Synthetic owned execution failure')
        def cleanup_wait():
            raise subprocess.TimeoutExpired('owned fixture', 60)
        child = Child(first_wait, cleanup_wait)
        def kill(pid, signum):
            if signum == signal.SIGTERM:
                raise PermissionError('Synthetic TERM failure')
        with patch.object(runner.subprocess, 'Popen', return_value=child), \
                patch.object(runner.os, 'killpg', side_effect=kill) as send:
            with self.assertRaises(RuntimeError):
                runner.run(self.args)
        self.assertEqual(child.waits, [None, runner.CLEANUP_GRACE_SECONDS, 15])
        self.assertEqual(send.call_count, 2)
        self.failed_evidence()

    def test_collection_failure_still_saves_and_screens_minimal_failure_receipt(self):
        def execution():
            self.args.work.mkdir()
            (self.args.work/'unowned.log').symlink_to(self.args.inputs/'PERFORMANCE-PLAN.json')
            child.returncode = 0
            return 0
        child = Child(first_wait=execution)
        with patch.object(runner.subprocess, 'Popen', return_value=child):
            with self.assertRaises(RuntimeError):
                runner.run(self.args)
        self.assertTrue((self.args.evidence/'producer-receipt.json').is_file())
        self.failed_evidence()

    def test_post_guard_foreign_evidence_directory_or_symlink_is_never_adopted(self):
        collect = runner.collect
        for kind in ('directory', 'symlink'):
            with self.subTest(kind=kind):
                if self.args.evidence.is_symlink():
                    self.args.evidence.unlink()
                elif self.args.evidence.exists():
                    shutil.rmtree(self.args.evidence)
                if self.args.screened.exists():
                    shutil.rmtree(self.args.screened)
                foreign = self.args.inputs/('foreign-' + kind)
                foreign.mkdir()
                originals = {'execution.json':b'Foreign execution\n',
                    'producer-receipt.json':b'Foreign receipt\n'}
                for name, content in originals.items():
                    (foreign/name).write_bytes(content)
                def replace(*args, **kwargs):
                    if kind == 'directory':
                        foreign.rename(self.args.evidence)
                    else:
                        self.args.evidence.symlink_to(foreign, target_is_directory=True)
                    return collect(*args, **kwargs)
                with patch.object(runner.subprocess, 'Popen', return_value=Child()), \
                        patch.object(runner, 'collect', side_effect=replace):
                    with self.assertRaises(RuntimeError):
                        runner.run(self.args)
                target = self.args.evidence if kind == 'directory' else foreign
                self.assertEqual({p.name:p.read_bytes() for p in target.iterdir()}, originals)
                self.assertFalse(self.args.screened.exists())
                self.contract.validate_evidence.assert_not_called()

    def test_actual_signal_during_save_is_resealed_failed_before_public_screening(self):
        original_write = runner.write_execution
        writes = []
        def write(evidence, state):
            writes.append(state['status'])
            if len(writes) == 1:
                os.kill(os.getpid(), signal.SIGINT)
            original_write(evidence, state)
        with patch.object(runner.subprocess, 'Popen', return_value=Child()), \
                patch.object(runner, 'write_execution', side_effect=write):
            with self.assertRaises(InterruptedError):
                runner.run(self.args)
        self.assertEqual(writes[-1], 'frozen_external_paired_failed')
        self.failed_evidence()

    def test_repeated_actual_signals_during_screening_replace_only_owned_pass_snapshot(self):
        screen = self.screen.screen_external
        def interrupted_screen(source, target):
            screen(source, target)
            if len(self.screens) == 1:
                os.kill(os.getpid(), signal.SIGTERM)
                os.kill(os.getpid(), signal.SIGINT)
        self.screen.screen_external = interrupted_screen
        with patch.object(runner.subprocess, 'Popen', return_value=Child()):
            with self.assertRaises(InterruptedError):
                runner.run(self.args)
        self.assertEqual(self.screens, ['frozen_external_paired_regression_gate_passed',
            'frozen_external_paired_failed'])
        self.failed_evidence()

    def test_actual_int_during_cleanup_handler_transition_is_deferred_until_owned_stop(self):
        install = signal.signal
        queue_installs = 0
        def transition(signum, handler):
            nonlocal queue_installs
            previous = install(signum, handler)
            if signum == signal.SIGTERM and getattr(handler, '__name__', '') == 'queued':
                queue_installs += 1
                if queue_installs == 2:
                    # INT's previous raising handler is still installed here.
                    os.kill(os.getpid(), signal.SIGINT)
            return previous
        def first_wait():
            raise RuntimeError('Synthetic owned execution failure')
        child = Child(first_wait)
        with patch.object(runner.subprocess, 'Popen', return_value=child), \
                patch.object(runner.os, 'killpg') as kill, \
                patch.object(runner.signal, 'signal', side_effect=transition):
            with self.assertRaises(RuntimeError):
                runner.run(self.args)
        self.assertEqual(child.waits, [None, runner.CLEANUP_GRACE_SECONDS])
        kill.assert_called_once_with(child.pid, signal.SIGTERM)
        self.failed_evidence()

    def test_actual_term_after_cleanup_body_before_context_exit_is_not_swallowed(self):
        defer = runner.defer_signals
        scopes = 0
        @contextmanager
        def late_defer():
            nonlocal scopes
            scopes += 1
            scope = scopes
            with defer() as pending:
                yield pending
                if scope == 2:
                    os.kill(os.getpid(), signal.SIGTERM)
        with patch.object(runner.subprocess, 'Popen', return_value=Child()), \
                patch.object(runner, 'defer_signals', late_defer):
            with self.assertRaises(InterruptedError):
                runner.run(self.args)
        self.assertEqual(self.screens, ['frozen_external_paired_regression_gate_passed',
            'frozen_external_paired_failed'])
        self.failed_evidence()

    def test_actual_child_does_not_inherit_transition_cancellation_mask(self):
        with runner.defer_signals():
            result = subprocess.check_output([sys.executable, '-c',
                'import signal; print(sorted(int(s) for s in signal.pthread_sigmask(signal.SIG_BLOCK, set())))'])
        blocked = json.loads(result)
        self.assertNotIn(int(signal.SIGTERM), blocked)
        self.assertNotIn(int(signal.SIGINT), blocked)

    def test_actual_term_during_cleanup_handler_restore_preserves_failed_evidence(self):
        install = signal.signal
        restores = 0
        def transition(signum, handler):
            nonlocal restores
            previous = install(signum, handler)
            if signum == signal.SIGTERM and getattr(handler, '__name__', '') == 'interrupted':
                restores += 1
                if restores == 3:  # Initial install, acquisition restore, cleanup restore.
                    os.kill(os.getpid(), signal.SIGTERM)
            return previous
        with patch.object(runner.subprocess, 'Popen', return_value=Child()), \
                patch.object(runner.signal, 'signal', side_effect=transition):
            with self.assertRaises(InterruptedError):
                runner.run(self.args)
        self.failed_evidence()

    def test_actual_int_during_initial_handler_install_restores_caller_before_spawn(self):
        install = signal.signal
        sent = False
        def transition(signum, handler):
            nonlocal sent
            previous = install(signum, handler)
            if not sent and signum == signal.SIGTERM and getattr(handler, '__name__', '') == 'interrupted':
                sent = True
                os.kill(os.getpid(), signal.SIGINT)
            return previous
        with patch.object(runner.subprocess, 'Popen') as spawn, \
                patch.object(runner.signal, 'signal', side_effect=transition):
            with self.assertRaises(InterruptedError):
                runner.run(self.args)
        spawn.assert_not_called()
        for signum, handler in self.handlers.items():
            self.assertIs(signal.getsignal(signum), handler)

    def test_existing_screening_is_rejected_before_spawn_and_preserved(self):
        self.args.screened.mkdir()
        sentinel = self.args.screened/'sentinel.txt'
        sentinel.write_text('Preexisting unowned data\n')
        with patch.object(runner.subprocess, 'Popen') as spawn:
            with self.assertRaises(ValueError):
                runner.run(self.args)
        spawn.assert_not_called()
        self.assertEqual(sentinel.read_text(), 'Preexisting unowned data\n')

    def test_evidence_deadline_restores_alarm_after_real_short_timeout(self):
        previous = signal.getsignal(signal.SIGALRM)
        with self.assertRaises(TimeoutError):
            with runner.evidence_deadline(.02):
                time.sleep(.1)
        self.assertIs(signal.getsignal(signal.SIGALRM), previous)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))

    def test_clean_completion_still_requires_original_full_evidence_replay(self):
        with patch.object(runner.subprocess, 'Popen', return_value=Child()):
            runner.run(self.args)
        self.contract.validate_evidence.assert_called_once()
        self.assertEqual(self.screens, ['frozen_external_paired_regression_gate_passed'])
        for signum, handler in self.handlers.items():
            self.assertIs(signal.getsignal(signum), handler)


if __name__ == '__main__':
    unittest.main()
