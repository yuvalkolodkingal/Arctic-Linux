"""New prerequisite controls; public RPMs and synthetic command boundaries only."""
import ast
import hashlib
import json
import os
import signal
import subprocess
import sys
import types
import unittest
from pathlib import Path
from unittest import mock
import producer as P

HERE = Path(__file__).parent
RAW = (HERE / 'producer.py').read_bytes()
WITNESS = Path('/dev/shm/arctic-browser-Fedora44-SDK-availability-Source-20261012')
INPUTS = {row[2]: (WITNESS / row[2]).read_bytes() for row in P.ARCHIVED_GLIB_INPUTS}

class Controls(unittest.TestCase):
    def invoke(self, db):
        try:
            return P.archived_glib_prerequisite(db)
        except BaseException as error:
            # unittest.assertRaises clears its caught object's traceback;
            # classify the real still-live original throwing frames first.
            self.live_finite = P.finite_producer_failure(error)
            self.live_record = P.failure_record(error)
            raise
    def context(self, bad_signature=None, changed_input=False, wrong_installed=False, primary=None):
        calls = []
        reads = {}
        def read(path, size, sha):
            row = next(row for row in P.ARCHIVED_GLIB_INPUTS if row[2] == path.name)
            self.assertEqual(path, Path('/inputs') / row[2])
            self.assertEqual((size, sha), (row[3], row[4]))
            raw = INPUTS[path.name]
            self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), (size, sha))
            reads[path.name] = reads.get(path.name, 0) + 1
            return raw + b'changed' if changed_input and reads[path.name] == 2 else raw
        def run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv[0] == 'rpmkeys':
                self.assertEqual(kwargs, {'capture_output': True, 'timeout': 60})
                self.assertEqual(argv[1:5], ['--dbpath', str(P.ROOT / 'signature-db'), '--checksig', '--verbose'])
                stdout = b'key fingerprint: 36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6: OK\n'
                return types.SimpleNamespace(returncode=0, stdout=stdout if bad_signature is None else bad_signature, stderr=b'')
            self.assertEqual(argv, ['dnf5', 'install', '--assumeyes',
                *[str(Path('/inputs') / row[2]) for row in P.ARCHIVED_GLIB_INPUTS]])
            self.assertEqual(kwargs, {'check': True, 'timeout': 900})
            if primary is not None:
                raise primary
            return types.SimpleNamespace(returncode=0)
        def query(argv, **kwargs):
            calls.append((argv, kwargs))
            self.assertEqual(kwargs, {'timeout': 30})
            if '-qp' in argv:
                row = next(row for row in P.ARCHIVED_GLIB_INPUTS if row[2] == Path(argv[-1]).name)
            else:
                self.assertEqual(argv[:2], ['rpm', '-q'])
                row = next(row for row in P.ARCHIVED_GLIB_INPUTS if row[0] == argv[-1])
            result = (row[1] + '\n' + row[5] + '\n').encode('ascii')
            return result + b'foreign-header\n' if wrong_installed and '-qp' not in argv else result
        stack = __import__('contextlib').ExitStack()
        stack.enter_context(mock.patch.object(P.os, 'geteuid', return_value=0))
        stack.enter_context(mock.patch.object(P.Path, 'is_file', return_value=True))
        stack.enter_context(mock.patch.object(P, 'read_bound', side_effect=read))
        stack.enter_context(mock.patch.object(P.subprocess, 'run', side_effect=run))
        stack.enter_context(mock.patch.object(P.subprocess, 'check_output', side_effect=query))
        return stack, calls, reads

    def test_exact_signed_two_package_transaction_and_header_postflight(self):
        stack, calls, reads = self.context()
        with stack:
            self.assertIsNone(self.invoke(P.ROOT / 'signature-db'))
        self.assertEqual(len(calls), 7)
        self.assertEqual(list(reads.values()), [3, 3])
        self.assertEqual(sum(call[0][0] == 'dnf5' for call in calls), 1)
        self.assertEqual({row[0] for row in P.ARCHIVED_GLIB_INPUTS}, {'glib2', 'glib2-devel'})

    def test_unknown_nonOK_or_unsigned_signature_denies_before_install(self):
        for status in (b'key fingerprint: 0000000000000000000000000000000000000000: OK',
                       b'key fingerprint: 36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6: NOT OK',
                       b'digests OK', b'key fingerprint: 36f612dcf27f7d1a48a835e4dbfcf71c6d9f90a6: OK\nNOKEY'):
            stack, calls, _ = self.context(bad_signature=status)
            with stack, self.assertRaises(RuntimeError) as caught:
                self.invoke(P.ROOT / 'signature-db')
            self.assertEqual(str(caught.exception), 'producer_archived_signature')
            self.assertFalse(any(call[0][0] == 'dnf5' for call in calls))
            self.assertEqual(self.live_finite, ('archived_sdk_signature', 'producer_archived_signature'))

    def test_input_change_or_wrong_installed_header_rejects(self):
        for changed, installed, reason in ((True, False, 'producer_archived_input_changed'),
                                           (False, True, 'producer_archived_installed_header')):
            stack, calls, _ = self.context(changed_input=changed, wrong_installed=installed)
            with stack, self.assertRaises(RuntimeError) as caught:
                self.invoke(P.ROOT / 'signature-db')
            self.assertEqual(str(caught.exception), reason)
            self.assertEqual(self.live_finite[1], reason)
            self.assertEqual(any(call[0][0] == 'dnf5' for call in calls), installed)

    def test_scope_and_old_default_disabled_context_before_primitive(self):
        with mock.patch.object(P, 'read_bound', side_effect=AssertionError('unentered input')):
            with self.assertRaises(RuntimeError) as caught:
                self.invoke(P.ROOT / 'signature-db')
        self.assertEqual(str(caught.exception), 'producer_container_only')
        for wrong in ('signature-db', P.ROOT / 'other-db'):
            with mock.patch.object(P.os, 'geteuid', return_value=0), mock.patch.object(P.Path, 'is_file', return_value=True):
                with self.assertRaises(RuntimeError) as caught:
                    self.invoke(wrong)
                self.assertEqual(str(caught.exception), 'producer_archived_scope')
        context = {'schema': 'arctic-accelerator-ab-hosted-build-v1', 'ready': False, 'container': None,
            'candidate': {'bytes': P.CANDIDATE_BYTES, 'sha256': P.CANDIDATE_SHA},
            'window_source': {'bytes': P.WINDOW_BYTES, 'sha256': P.WINDOW_SHA},
            'gtk_control': {'bytes': P.GTK_CONTROL_BYTES, 'sha256': P.GTK_CONTROL_SHA},
            'build_environment': 'one_disposable_rootful_Fedora44_container_no_host_package_install'}
        with self.assertRaises(RuntimeError) as caught:
            P.validate_context(context)
        self.assertEqual(str(caught.exception), 'producer_disabled')

    def test_same_command_error_and_real_INT_preserved_without_operands(self):
        primary = subprocess.CalledProcessError(1, ['private-owned-fixture'], output=b'opaque')
        stack, _, _ = self.context(primary=primary)
        with stack, self.assertRaises(subprocess.CalledProcessError) as caught:
            self.invoke(P.ROOT / 'signature-db')
        self.assertIs(caught.exception, primary)
        self.assertEqual(self.live_finite, ('archived_sdk_install', 'command_failed'))
        record = self.live_record
        self.assertNotIn('private-owned-fixture', json.dumps(record))
        cancel = KeyboardInterrupt('owned synthetic cancellation')
        before_stdout = sys.stdout
        before_trace = sys.gettrace()
        sent = []
        def handler(_signal, _frame):
            raise cancel
        old_handler = signal.signal(signal.SIGINT, handler)
        def trace(frame, event, argument):
            if event == 'line' and frame.f_code is P.archived_glib_prerequisite.__code__ and not sent:
                sent.append(True)
                os.kill(os.getpid(), signal.SIGINT)
            return trace
        stack, _, _ = self.context()
        try:
            with stack:
                sys.settrace(trace)
                with self.assertRaises(KeyboardInterrupt) as caught:
                    self.invoke(P.ROOT / 'signature-db')
        finally:
            sys.settrace(before_trace)
            signal.signal(signal.SIGINT, old_handler)
        self.assertTrue(sent)
        self.assertIs(caught.exception, cancel)
        self.assertIs(sys.stdout, before_stdout)

    def test_original_five_pin_command_budgets_and_all_old_function_ASTs_preserved(self):
        inverse = json.loads((HERE / 'source-inverse.json').read_bytes())
        restored = RAW.replace(inverse['added_body_exact_UTF8'].encode(), b'')
        restored = restored.replace(inverse['main_new_UTF8'].encode(), inverse['main_old_UTF8'].encode())
        restored = restored.replace(inverse['new_body_SHA'].encode(), inverse['old_body_SHA'].encode())
        restored = restored.replace(inverse['require_table_added_exact_UTF8'].encode(), b'')
        restored = restored.replace(inverse['command_table_added_exact_UTF8'].encode(), b'')
        restored = restored.replace(inverse['new_PHASES_prefix_UTF8'].encode(), b'')
        restored = restored.replace(inverse['new_REASONS_prefix_UTF8'].encode(), b'')
        restored = restored.replace(b'FAILURE_BODY_CODES = (archived_glib_prerequisite.__code__,', b'FAILURE_BODY_CODES = (')
        self.assertEqual(len(restored), inverse['old_producer']['bytes'])
        self.assertEqual(hashlib.sha256(restored).hexdigest(), inverse['old_producer']['sha256'])
        old_nodes = {n.name: n for n in ast.parse(restored).body if isinstance(n, ast.FunctionDef)}
        new_nodes = {n.name: n for n in ast.parse(RAW).body if isinstance(n, ast.FunctionDef)}
        for name, node in old_nodes.items():
            if name != 'main':
                self.assertEqual(ast.dump(node, include_attributes=False), ast.dump(new_nodes[name], include_attributes=False))
        original = "subprocess.run(['dnf5','install','--assumeyes',*EXPECTED_RUNTIME_DEVEL.values()],check=True,timeout=900)"
        self.assertEqual(RAW.count(original.encode()), 1)
        self.assertEqual(hashlib.sha256(RAW.split(b'FAILURE_PREFIX = ', 1)[0]).hexdigest(), P.FAILURE_BODY_SHA256)

if __name__ == '__main__':
    unittest.main(verbosity=2)
