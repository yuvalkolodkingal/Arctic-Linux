"""Synthetic diagnostics only; no VM, model, microphone or accuracy claims."""
import ast
import importlib.util
import itertools
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

from test_contract import FIXTURES, c, synthetic

SPEC = importlib.util.spec_from_file_location('dictation_wait_diagnostic', Path(__file__).with_name('guest_check.py'))
guest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guest)
BASE = '7bd18e5ecf1748fe09dd4f479766722fce4554c1'
REPO = Path(__file__).resolve().parents[2]
PRIVATE = 'synthetic-private-audio-transcript-argv-password-stderr'

class PrivateString(str):
    def __str__(self): raise AssertionError(PRIVATE)
    def __repr__(self): raise AssertionError(PRIVATE)
    def __eq__(self, other): raise AssertionError(PRIVATE)
    def __hash__(self): raise AssertionError(PRIVATE)

class PrivateMapping(dict):
    def get(self, *args): raise AssertionError(PRIVATE)

class PrivateError(c.Invalid):
    @property
    def args(self): raise AssertionError(PRIVATE)
    def __str__(self): raise AssertionError(PRIVATE)
    def __repr__(self): raise AssertionError(PRIVATE)

class WaitDiagnosticControls(unittest.TestCase):
    def checker(self):
        v = guest.Checker.__new__(guest.Checker)
        v.runtime = Path('/nonexistent-diagnostic-runtime')
        v.account = SimpleNamespace(pw_uid=os.getuid() or 1)
        v._wait_last_status = ('recording', 'cpu')
        v._wait_last_graph = (True, False, False, True, False)
        return v

    def test_codes_are_closed_bounded_and_unknown_is_not_false(self):
        for target, state, backend in itertools.product(guest.WAIT_DIAGNOSTIC_TARGETS,
                (*guest.WAIT_DIAGNOSTIC_STATES, 'unknown'), ('idle', 'cpu', 'vulkan', 'unknown')):
            for bits in itertools.product((True, False, None), repeat=5):
                code = guest.wait_diagnostic_code(target, (state, backend), (state, backend), bits)
                self.assertRegex(code, '^[a-z0-9-]{1,80}$')
                self.assertNotIn(PRIVATE, code)
        code = guest.wait_diagnostic_code('capture-link', None, None, None)
        self.assertEqual(code, 'wait-capture-link-last-unknown-unknown-now-unknown-unknown-lguuuuu')

    def test_hostile_values_getters_subclasses_are_not_formatted(self):
        for value in (None, PRIVATE, PrivateString(PRIVATE), [], PrivateMapping(),
                      {'state': PrivateString(PRIVATE), 'active_backend': PrivateString(PRIVATE)},
                      {'state': PRIVATE, 'active_backend': PRIVATE}):
            self.assertEqual(guest.wait_status_projection(value), ('unknown', 'unknown'))
        class PrivateTuple(tuple):
            def __iter__(self): raise AssertionError(PRIVATE)
        for value in (PrivateTuple((True,) * 5), (PrivateString(PRIVATE),) * 5, None, PRIVATE):
            code = guest.wait_diagnostic_code('capture-link', PrivateTuple(('ready', 'cpu')), None, value)
            self.assertEqual(code, 'wait-capture-link-last-unknown-unknown-now-unknown-unknown-lguuuuu')
        for target in (PrivateString('capture-link'), PRIVATE, None, [], True):
            with self.assertRaisesRegex(c.Invalid, '^unknown-wait-diagnostic-target$'):
                guest.wait_diagnostic_code(target, None, None, None)

    def test_original_wait_predicate_and_budget_success_are_forwarded_exactly(self):
        checker = self.checker()
        predicate, observed = object(), object()
        for seconds in (20, 10, 240, 5, 3, 90):
            with mock.patch.object(guest, 'wait', return_value=observed) as wait, \
                 mock.patch.object(guest, 'wait_runtime_projection', side_effect=AssertionError(PRIVATE)):
                self.assertIs(checker.observe('capture-link', predicate, seconds), observed)
                wait.assert_called_once_with(predicate, seconds)
        with mock.patch.object(guest, 'wait', return_value=observed) as wait:
            self.assertIs(checker.observe('receiver-clear', predicate), observed)
            wait.assert_called_once_with(predicate, 20)

    def test_only_original_fixed_timeout_changes_and_private_args_getter_is_unused(self):
        checker = self.checker()
        with mock.patch.object(guest, 'wait', side_effect=PrivateError('observation-timeout')), \
             mock.patch.object(guest, 'wait_runtime_projection', return_value=('error', 'cpu')):
            with self.assertRaises(c.Invalid) as caught:
                checker.observe('capture-link', object(), 10)
        self.assertEqual(str(caught.exception), 'wait-capture-link-last-recording-cpu-now-error-cpu-lg10010')
        for error in (PrivateError(PRIVATE), PrivateError(PrivateString('observation-timeout')),
                      PrivateError('observation-timeout', PRIVATE), OSError(PRIVATE),
                      ValueError(PRIVATE), guest.subprocess.TimeoutExpired([PRIVATE], 1)):
            with mock.patch.object(guest, 'wait', side_effect=error), \
                 mock.patch.object(guest, 'wait_runtime_projection', side_effect=AssertionError(PRIVATE)):
                with self.assertRaises(type(error)) as caught:
                    checker.observe('capture-link', object(), 10)
                self.assertIs(caught.exception, error)

    def test_diagnostic_failure_does_not_replace_timeout_or_prevent_cleanup(self):
        checker = self.checker()
        class PrivateAccount:
            @property
            def pw_uid(self): raise AssertionError(PRIVATE)
        checker.account = PrivateAccount()
        cleaned = False
        with mock.patch.object(guest, 'wait', side_effect=c.Invalid('observation-timeout')):
            try:
                checker.observe('capture-link', object(), 10)
            except c.Invalid as error:
                self.assertEqual(str(error), 'wait-capture-link-last-unknown-unknown-now-unknown-unknown-lguuuuu')
            finally:
                cleaned = True
        self.assertTrue(cleaned)

    def file(self, root, content):
        path = root / 'state.json'
        path.write_bytes(content)
        path.chmod(0o600)
        uid = os.getuid() or 1
        if os.getuid() == 0:
            os.chown(path, uid, os.getgid())
        return path, uid

    def test_runtime_projection_exports_only_known_enums(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for state, backend in itertools.product(guest.WAIT_DIAGNOSTIC_STATES, guest.WAIT_DIAGNOSTIC_BACKENDS):
                path, uid = self.file(root, json.dumps({'state': state, 'active_backend': backend,
                                                       'error': PRIVATE, 'transcript': PRIVATE}).encode())
                self.assertEqual(guest.wait_runtime_projection(path, uid), (state, backend or 'idle'))

    def test_runtime_rejects_nonregular_symlink_wrong_owner_mode_size_json(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, uid = self.file(root, b'{"state":"recording","active_backend":"cpu"}')
            self.assertEqual(guest.wait_runtime_projection(path, uid + 1), ('unknown', 'unknown'))
            for wrong in (0, True, PrivateString(PRIVATE), None):
                self.assertEqual(guest.wait_runtime_projection(path, wrong), ('unknown', 'unknown'))
            path.chmod(0o644)
            self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
            path.chmod(0o600)
            link = root / 'link'; link.symlink_to(path)
            fifo = root / 'fifo'; os.mkfifo(fifo, 0o600)
            for target in (link, fifo, root, root / 'missing', Path('/dev/null')):
                started = time.monotonic()
                self.assertEqual(guest.wait_runtime_projection(target, uid), ('unknown', 'unknown'))
                self.assertLess(time.monotonic() - started, 1)
            for data in (b'', b'x' * 16385, b'\xff', PRIVATE.encode(), b'[]',
                         b'[' * 5000 + b']' * 5000,
                         b'{"state":"recording","state":"ready","active_backend":"cpu"}',
                         json.dumps({'state': PRIVATE, 'active_backend': PRIVATE}).encode()):
                path, uid = self.file(root, data)
                self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))

    def test_runtime_descriptor_races_short_read_growth_and_closed_read_are_unknown(self):
        with tempfile.TemporaryDirectory() as temporary:
            path, uid = self.file(Path(temporary), b'{"state":"recording","active_backend":"cpu"}')
            actual = path.stat()
            names = ('st_mode', 'st_uid', 'st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
            original = {k: getattr(actual, k) for k in names}
            real_close = guest.os.close
            for field in names:
                changed = dict(original); changed[field] += 1
                with mock.patch.object(guest.os, 'fstat', side_effect=[actual, SimpleNamespace(**changed)]), \
                     mock.patch.object(guest.os, 'close', wraps=real_close) as close:
                    self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
                    self.assertEqual(close.call_count, 1)
            for result in (b'', b'x' * 16385):
                with mock.patch.object(guest.os, 'read', return_value=result):
                    self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
            with mock.patch.object(guest.os, 'read', side_effect=OSError(PRIVATE)):
                self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
            def closed(fd):
                real_close(fd); raise OSError(PRIVATE)
            with mock.patch.object(guest.os, 'close', side_effect=closed):
                self.assertEqual(guest.wait_runtime_projection(path, uid), ('recording', 'cpu'))
            with mock.patch.object(guest.os, 'open', wraps=guest.os.open) as opened:
                guest.wait_runtime_projection(path, uid)
                self.assertEqual(opened.call_args.args[1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)

    def test_runtime_named_file_replacement_deletion_and_metadata_getters_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path, uid = self.file(root, b'{"state":"recording","active_backend":"cpu"}')
            real_read = guest.os.read
            def replaced(fd, size):
                raw = real_read(fd, size)
                path.rename(root / 'old.private')
                self.file(root, b'{"state":"ready","active_backend":""}')
                return raw
            with mock.patch.object(guest.os, 'read', side_effect=replaced):
                self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
            def deleted(fd, size):
                raw = real_read(fd, size); path.unlink(); return raw
            with mock.patch.object(guest.os, 'read', side_effect=deleted):
                self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
            path, uid = self.file(root, b'{"state":"recording","active_backend":"cpu"}')
            class PrivateMetadata:
                @property
                def st_mode(self): raise AssertionError(PRIVATE)
            with mock.patch.object(guest.os, 'fstat', return_value=PrivateMetadata()):
                self.assertEqual(guest.wait_runtime_projection(path, uid), ('unknown', 'unknown'))
            raw = path.read_bytes()
            path, uid = self.file(root, raw + b' ' * (16384 - len(raw)))
            self.assertEqual(guest.wait_runtime_projection(path, uid), ('recording', 'cpu'))

    def test_authenticated_capture_identity_and_facts_are_bool_only(self):
        checker = self.checker(); checker.source = 77
        checker.engines = mock.Mock(return_value=[(41, 123, Path('/synthetic-engine'))])
        def node(identity, pid, media, client=None):
            return {'id': identity, 'type': 'PipeWire:Interface:Node',
                    'info': {'props': {'application.process.id': pid, 'media.class': media,
                                       **({'client.id': client} if client is not None else {})}}}
        client = {'id': 33, 'type': 'PipeWire:Interface:Client', 'info': {'props': {
            'pipewire.protocol': 'protocol-native', 'pipewire.sec.pid': 41, 'pipewire.sec.uid': checker.account.pw_uid}}}
        source = node(77, 1, 'Audio/Source')
        capture = node(81, '41', 'Stream/Input/Audio', 33)
        link = {'id': 82, 'type': 'PipeWire:Interface:Link', 'info': {'output-node-id': 77, 'input-node-id': 81}}
        for objects, expected, facts in (([source], False, (True, False, False, True, False)),
                ([source, node(81, 41, 'Stream/Output/Audio', 33)], False, (True, True, False, True, False)),
                ([source, capture], False, (True, True, True, True, False)),
                ([capture, link], True, (True, True, True, False, True)),
                ([source, capture, link], True, (True, True, True, True, True))):
            checker.cmd = mock.Mock(return_value=SimpleNamespace(stdout=json.dumps([client] + objects).encode()))
            self.assertIs(checker.capture_link(), expected)
            self.assertEqual(checker._wait_last_graph, facts)
            self.assertTrue(all(type(v) is bool for v in facts))
        checker.engines.return_value = []
        with self.assertRaisesRegex(c.Invalid, '^recording-engine-not-unique$'):
            checker.capture_link()

    def test_failed_gate_schema_privacy_and_success_gates_remain_strict(self):
        for phase, profile in itertools.product(('online-installed', 'recovered-offline'), c.PROFILES):
            checker = self.checker()
            checker.context = synthetic(phase, profile=profile)['context']
            checker.gates = c.gates(phase, profile)
            checker.report = synthetic(phase, profile=profile)
            name = 'cpu-english-transcription-insertion'
            checker.report['gates'] = [g for g in checker.report['gates'] if g['id'] != name]
            checker.report['samples'] = []; checker.report['status'] = 'failed'
            with mock.patch.object(guest, 'wait', side_effect=c.Invalid('observation-timeout')):
                self.assertFalse(checker.gate(name, lambda: checker.observe('capture-link', object(), 10)))
            failed = checker.report['gates'][-1]
            self.assertEqual(failed['observations'], {})
            self.assertNotIn(PRIVATE, json.dumps(checker.report))
            c.validate(checker.report, checker.context, require_passed=False, fixture_manifest=FIXTURES)
            with self.assertRaises(c.Invalid):
                c.validate(checker.report, checker.context, require_passed=True, fixture_manifest=FIXTURES)

    def test_entire_original_ast_rolls_back_and_wait_bytes_are_identical(self):
        old = subprocess.check_output(['git', '-C', str(REPO), 'show', BASE + ':tools/dictation-qualification/guest_check.py']).decode()
        new = Path(guest.__file__).read_text()
        # Compatibility CPU fixture controls separately cover this pre-gate
        # requirement; reverse only that addition for the older wait proof.
        new = new.replace("        if self.profile_id == 'small-v2':\n            verify_small_cpu_fixture(cpuinfo)\n", '')
        begin = new.index('\ndef verify_small_cpu_fixture(')
        end = new.index('\ndef authenticated_capture_nodes(', begin)
        new = new[:begin] + new[end:]
        original, revised = ast.parse(old), ast.parse(new)
        helper_names = {'wait_status_projection', 'wait_runtime_projection', 'wait_diagnostic_code',
                        'authenticated_capture_nodes'}
        old_capture = next(n for n in ast.walk(original) if isinstance(n, ast.FunctionDef) and n.name == 'capture_link')
        revised.body = [n for n in revised.body if not (isinstance(n, ast.FunctionDef) and n.name in helper_names)
                        and not (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id.startswith('WAIT_DIAGNOSTIC_') for t in n.targets))]
        for tree in (original, revised):
            for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Checker']:
                if tree is revised:
                    cls.body = [n for n in cls.body if not isinstance(n, ast.FunctionDef) or n.name != 'observe']
                for method in cls.body:
                    if not isinstance(method, ast.FunctionDef): continue
                    if tree is revised:
                        method.body = [n for n in method.body if not (isinstance(n, ast.Assign)
                            and any(isinstance(t, ast.Attribute) and t.attr.startswith('_wait_last_') for t in n.targets))]
                        if method.name == 'capture_link':
                            # The focused client-binding controls separately prove the
                            # intended ownership change; restore this whole method here
                            # to retain the original diagnostics-only rollback proof.
                            method.body = old_capture.body
                        for n in ast.walk(method):
                            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == 'observe':
                                n.func = ast.Name(id='wait', ctx=ast.Load()); n.args = n.args[1:]
        self.assertEqual(ast.dump(revised, include_attributes=False), ast.dump(original, include_attributes=False))
        rollback = new
        begin = rollback.index('WAIT_DIAGNOSTIC_TARGETS = ')
        end = rollback.index('\ndef session_diagnostic_code(', begin)
        rollback = rollback[:begin] + rollback[end:]
        rollback = rollback.replace('        self._wait_last_status = self._wait_last_graph = None\n', '')
        rollback = rollback.replace('        self._wait_last_status = wait_status_projection(value)\n', '')
        begin = rollback.index('\n    def observe(self, target, fn, seconds=20):')
        end = rollback.index('\n    def empty(self):', begin)
        rollback = rollback[:begin] + rollback[end:]
        old_capture = next(n for n in ast.walk(ast.parse(old)) if isinstance(n, ast.FunctionDef) and n.name == 'capture_link')
        new_capture = next(n for n in ast.walk(ast.parse(rollback)) if isinstance(n, ast.FunctionDef) and n.name == 'capture_link')
        lines = rollback.splitlines(keepends=True)
        lines[new_capture.lineno - 1:new_capture.end_lineno] = old.splitlines(keepends=True)[old_capture.lineno - 1:old_capture.end_lineno]
        rollback = ''.join(lines)
        for target in guest.WAIT_DIAGNOSTIC_TARGETS:
            rollback = rollback.replace("self.observe('" + target + "', ", 'wait(')
        self.assertEqual(rollback.encode(), old.encode())
        def body(source, name):
            fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == name)
            return '\n'.join(source.splitlines()[fn.lineno - 1:fn.end_lineno])
        self.assertEqual(body(old, 'wait'), body(new, 'wait'))

if __name__ == '__main__':
    unittest.main()
