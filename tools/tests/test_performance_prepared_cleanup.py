"""Prepared test-image ownership controls; no VM or measurement is simulated."""
import importlib.util
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepared_owned_image', ROOT/'tools/performance/run-paired.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
TASK = 'a'*32
IMAGE = 'sha256:' + 'b'*64
BASE = 'sha256:' + 'c'*64
CONTAINER = 'arctic-paired-' + TASK + '-12345678'


class PreparedImageTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.owner = dict(schema='arctic-paired-test-image-owner-v1', release_acceptance=False,
            task_id=TASK, container=CONTAINER, base_id=BASE)
        self.write_owner()
        self.labels = {'org.arctic.test.vm-tools.scope':'paired-v1',
            'org.arctic.test.vm-tools.task':TASK, 'org.arctic.test.vm-tools.container':CONTAINER,
            'org.arctic.test.vm-tools.base':BASE}
        self.calls = []
        self.identifiers = IMAGE + '\n'
        self.inventory = [dict(Id=IMAGE, Config=dict(Labels=self.labels))]
        self.responses = None

    def write_owner(self):
        (self.folder/'vm-prepared-image-owner.json').write_text(json.dumps(self.owner) + '\n')

    def engine(self, argv, **kwargs):
        self.calls.append(argv)
        self.assertEqual(kwargs['timeout'], 30)
        self.assertTrue(kwargs['check'])
        self.assertFalse(signal.pthread_sigmask(signal.SIG_BLOCK, set()) & {signal.SIGTERM, signal.SIGINT})
        command = argv[1:3]
        output = self.identifiers if command == ['image', 'ls'] else (
            json.dumps(self.inventory) if command == ['image', 'inspect'] else '')
        if self.responses:
            self.responses(argv)
        return types.SimpleNamespace(stdout=output, stderr='')

    def cleanup(self, known=None):
        with patch.object(runner.subprocess, 'run', side_effect=self.engine):
            return runner.cleanup_prepared_image('owned-engine', self.folder, TASK, known)

    def removals(self):
        return [argv for argv in self.calls if argv[1:3] == ['image', 'rm']]

    def test_cancelled_parent_handoff_recovers_committed_id_receipt(self):
        (self.folder/'vm-prepared-image-id.txt').write_text(IMAGE + '\n')
        receipt = self.cleanup()  # Parent's prepared_id is still None.
        self.assertEqual(receipt, dict(status='removed', image_id=IMAGE, errors=[]))
        self.assertEqual(self.removals(), [['owned-engine', 'image', 'rm', IMAGE]])
        self.assertFalse(any(argv[1:3] == ['image', 'ls'] for argv in self.calls))

    def test_commit_completed_before_id_receipt_recovers_exact_task_labels(self):
        self.assertEqual(self.cleanup()['image_id'], IMAGE)
        self.assertEqual(self.calls[0][1:5], ['image', 'ls', '--no-trunc', '--quiet'])
        self.assertIn('label=org.arctic.test.vm-tools.task=' + TASK, self.calls[0])
        self.assertEqual(self.removals(), [['owned-engine', 'image', 'rm', IMAGE]])

    def test_inflight_commit_with_intent_and_empty_query_blocks_without_removal(self):
        self.identifiers = ''
        with self.assertRaisesRegex(RuntimeError, 'outcome unresolved'):
            self.cleanup()
        self.assertFalse(self.removals())

    def test_missing_owner_has_no_removal_and_cannot_authorize_known_image(self):
        (self.folder/'vm-prepared-image-owner.json').unlink()
        self.assertEqual(self.cleanup()['status'], 'not_acquired')
        self.assertEqual(self.calls, [])
        with self.assertRaises(ValueError):
            self.cleanup(IMAGE)

    def test_foreign_image_id_or_each_ownership_label_prevents_removal(self):
        for key in ('Id', *self.labels):
            with self.subTest(key=key):
                self.inventory = [dict(Id=IMAGE, Config=dict(Labels=dict(self.labels)))]
                if key == 'Id':
                    self.inventory[0]['Id'] = 'sha256:' + 'd'*64
                else:
                    self.inventory[0]['Config']['Labels'][key] = 'foreign'
                self.calls.clear()
                with self.assertRaises(ValueError):
                    self.cleanup(IMAGE)
                self.assertFalse(self.removals())

    def test_invalid_owner_or_foreign_task_cannot_authorize_engine_calls(self):
        mutations = [dict(task_id='d'*32), dict(release_acceptance=0), dict(base_id='latest'),
            dict(container='arctic-paired-' + TASK + '-not-owned'), dict(extra=True)]
        original = dict(self.owner)
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.owner = original | mutation
                self.write_owner()
                self.calls.clear()
                with self.assertRaises(ValueError):
                    self.cleanup()
                self.assertEqual(self.calls, [])

    def test_symlink_duplicate_nonfinite_and_oversized_owner_are_rejected(self):
        path = self.folder/'vm-prepared-image-owner.json'
        for content in ('{"task_id":"a","task_id":"b"}', '{"value":NaN}', ' '*4097):
            with self.subTest(content=content[:30]):
                path.write_text(content)
                with self.assertRaises(ValueError):
                    self.cleanup()
        path.unlink()
        foreign = self.folder/'foreign.json'
        foreign.write_text(json.dumps(self.owner))
        original = foreign.read_bytes()
        path.symlink_to(foreign)
        with self.assertRaises(OSError):
            self.cleanup()
        self.assertEqual(foreign.read_bytes(), original)
        self.assertEqual(self.calls, [])

    def test_ambiguous_labeled_images_or_invalid_id_receipts_prevent_removal(self):
        self.identifiers = IMAGE + '\nsha256:' + 'd'*64 + '\n'
        with self.assertRaises(ValueError):
            self.cleanup()
        self.assertFalse(self.removals())
        for content in ('latest\n', IMAGE, IMAGE + '\nextra\n'):
            (self.folder/'vm-prepared-image-id.txt').write_text(content)
            with self.assertRaises(ValueError):
                self.cleanup()
            self.assertFalse(self.removals())
        (self.folder/'vm-prepared-image-id.txt').write_text('sha256:' + 'd'*64 + '\n')
        with self.assertRaises(ValueError):
            self.cleanup(IMAGE)
        self.assertFalse(self.removals())

    def test_duplicate_tags_are_deduplicated_without_weakening_exact_image_check(self):
        self.identifiers = IMAGE + '\n' + IMAGE + '\n'
        self.assertEqual(self.cleanup()['status'], 'removed')
        self.assertEqual(len(self.removals()), 1)

    def test_bare_immutable_id_is_canonicalized_but_malformed_or_different_id_is_rejected(self):
        self.identifiers = IMAGE.removeprefix('sha256:') + '\n'
        self.inventory[0]['Id'] = IMAGE.removeprefix('sha256:')
        self.assertEqual(self.cleanup()['image_id'], IMAGE)
        self.assertEqual(self.removals(), [['owned-engine', 'image', 'rm', IMAGE]])
        for identifier in ('latest', 'b'*63, 'sha256:' + 'd'*64, False, None):
            with self.subTest(identifier=identifier):
                self.calls.clear()
                self.inventory[0]['Id'] = identifier
                with self.assertRaises(ValueError):
                    self.cleanup()
                self.assertFalse(self.removals())

    def test_engine_failure_preserves_failed_cleanup_status_and_original_handlers(self):
        handlers = {s:signal.getsignal(s) for s in (signal.SIGTERM, signal.SIGINT)}
        state = dict(phase='complete_regression_gate_passed')
        phases = []
        def fail(argv):
            if argv[1:3] == ['image', 'rm']:
                raise subprocess.TimeoutExpired(argv, 30)
        self.responses = fail
        with patch.object(runner.subprocess, 'run', side_effect=self.engine):
            with self.assertRaises(subprocess.TimeoutExpired):
                runner.finalize_prepared_image('owned-engine', self.folder, TASK, None, state, phases.append)
        self.assertEqual(phases[-1], 'blocked')
        self.assertEqual(state['vm_prepared_image_cleanup']['errors'], ['TimeoutExpired'])
        self.assertEqual({s:signal.getsignal(s) for s in handlers}, handlers)

    def test_repeated_actual_signals_do_not_skip_owned_removal_or_failed_save(self):
        state = dict(phase='complete_regression_gate_passed')
        phases = []
        def cancel(argv):
            os.kill(os.getpid(), signal.SIGTERM)
            os.kill(os.getpid(), signal.SIGINT)
        self.responses = cancel
        with patch.object(runner.subprocess, 'run', side_effect=self.engine):
            with self.assertRaises(InterruptedError):
                runner.finalize_prepared_image('owned-engine', self.folder, TASK, None, state, phases.append)
        self.assertEqual(self.removals(), [['owned-engine', 'image', 'rm', IMAGE]])
        self.assertEqual(phases[-1], 'blocked')
        self.assertEqual(state['vm_prepared_image_cleanup']['deferred_signals'],
            [signal.SIGTERM, signal.SIGINT]*3)

    def test_late_context_exit_actual_signal_cannot_leave_pass_evidence(self):
        real = runner.defer_prepared_signals
        @contextmanager
        def late():
            with real() as pending:
                yield pending
                os.kill(os.getpid(), signal.SIGTERM)
        phases = []
        with patch.object(runner, 'defer_prepared_signals', late), \
                patch.object(runner.subprocess, 'run', side_effect=self.engine):
            with self.assertRaises(InterruptedError):
                runner.finalize_prepared_image('owned-engine', self.folder, TASK, None,
                    dict(phase='complete_regression_gate_passed'), phases.append)
        self.assertEqual(phases, ['complete_regression_gate_passed', 'blocked'])
        self.assertEqual(len(self.removals()), 1)


FAKE_ENGINE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
root = pathlib.Path(os.environ['FIXTURE_ENGINE_ROOT'])
argv = sys.argv[1:]
with (root/'calls.jsonl').open('a') as log:
    log.write(json.dumps(argv)+'\n')
if argv[0] == 'commit':
    labels = {}
    for index, value in enumerate(argv):
        if value == '--change':
            key, content = argv[index+1].removeprefix('LABEL ').split('=', 1)
            labels[key] = content
    (root/'image.json').write_text(json.dumps([dict(Id='sha256:'+'b'*64, Config=dict(Labels=labels))]))
    (root/'committed').write_text('yes')
    if os.environ.get('FIXTURE_COMMIT_WAIT') == '1': time.sleep(.4)
    print('sha256:'+'b'*64)
elif argv[:2] == ['image','ls']: print('sha256:'+'b'*64)
elif argv[:2] == ['image','inspect']: print((root/'image.json').read_text())
elif argv[:2] == ['image','rm']: (root/'removed').write_text(argv[2])
'''


class PreparationShellTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tools = self.root/'tools'
        (tools/'performance').mkdir(parents=True)
        (tools/'lib').mkdir()
        self.script = tools/'performance/prepare-vm-tools.sh'
        self.script.write_bytes((ROOT/'tools/performance/prepare-vm-tools.sh').read_bytes())
        (tools/'lib/container.sh').write_text('''arctic_die() { echo "$*" >&2; exit 1; }
arctic_ensure_engine() { :; }
arctic_engine() { printf '%s\\n' "$FIXTURE_ENGINE"; }
arctic_container_args() { ARCTIC_CONTAINER_ARGS=(); ARCTIC_CONTAINER_PROLOGUE=''; }
arctic_resolve_image() { printf '%s\\n' "sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"; }
arctic_log() { :; }
''')
        self.engine = self.root/'fixture-engine'
        self.engine.write_text(FAKE_ENGINE)
        self.engine.chmod(0o755)
        self.evidence = self.root/'evidence'
        self.env = dict(os.environ, FIXTURE_ENGINE=str(self.engine), FIXTURE_ENGINE_ROOT=str(self.root),
            ARCTIC_VM_CONTAINER_NAME=CONTAINER, ARCTIC_FEDORA_IMAGE=BASE)

    def test_actual_shell_commit_handoff_cancellation_recovers_labeled_image_without_id_file(self):
        child = subprocess.Popen(['bash', str(self.script), str(self.evidence), TASK],
            env=self.env | dict(FIXTURE_COMMIT_WAIT='1'), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not (self.root/'committed').exists() and time.monotonic() < deadline:
                time.sleep(.01)
            self.assertTrue((self.root/'committed').exists())
            child.send_signal(signal.SIGTERM)
            stdout, stderr = child.communicate(timeout=5)
            self.assertEqual(child.returncode, 143, (stdout, stderr))
            self.assertTrue((self.evidence/'vm-prepared-image-owner.json').is_file())
            self.assertFalse((self.evidence/'vm-prepared-image-id.txt').exists())
            with patch.dict(os.environ, self.env):
                receipt = runner.cleanup_prepared_image(str(self.engine), self.evidence, TASK)
            self.assertEqual(receipt['image_id'], IMAGE)
            self.assertEqual((self.root/'removed').read_text(), IMAGE)
        finally:
            if child.poll() is None:
                child.kill()
            child.communicate(timeout=5)

    def test_native_one_argument_commit_has_original_argv_and_no_paired_receipt(self):
        result = subprocess.run(['bash', str(self.script), str(self.evidence)],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [json.loads(line) for line in (self.root/'calls.jsonl').read_text().splitlines()]
        self.assertEqual([call for call in calls if call[0] == 'commit'], [['commit', CONTAINER]])
        self.assertFalse((self.evidence/'vm-prepared-image-owner.json').exists())
        self.assertEqual((self.evidence/'vm-prepared-image-id.txt').read_text(), IMAGE + '\n')

    def test_exclusive_foreign_owner_receipt_is_preserved_and_prevents_commit(self):
        self.evidence.mkdir()
        foreign = self.evidence/'vm-prepared-image-owner.json'
        foreign.write_bytes(b'Foreign ownership\n')
        result = subprocess.run(['bash', str(self.script), str(self.evidence), TASK],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(foreign.read_bytes(), b'Foreign ownership\n')
        self.assertFalse((self.root/'committed').exists())

    def test_existing_special_file_symlink_cannot_authorize_image_commit(self):
        self.evidence.mkdir()
        foreign = self.evidence/'vm-prepared-image-owner.json'
        foreign.symlink_to('/dev/null')
        result = subprocess.run(['bash', str(self.script), str(self.evidence), TASK],
            env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(os.readlink(foreign), '/dev/null')
        self.assertFalse((self.root/'committed').exists())

    def test_foreign_task_container_or_empty_task_cannot_start_provisioning(self):
        for task, container in ((TASK, 'arctic-paired-foreign-12345678'), ('', CONTAINER)):
            with self.subTest(task=task, container=container):
                result = subprocess.run(['bash', str(self.script), str(self.evidence), task],
                    env=self.env | dict(ARCTIC_VM_CONTAINER_NAME=container),
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse((self.root/'calls.jsonl').exists())
                self.assertFalse(self.evidence.exists())


if __name__ == '__main__':
    unittest.main()
