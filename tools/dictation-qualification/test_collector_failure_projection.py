"""Closed actual-function failure projections; no VM/audio/model operations."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent

def load(name, file):
    spec = importlib.util.spec_from_file_location(name, HERE / file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

g = load('actual_collector_failure_guest', 'guest_check.py')
r = load('actual_collector_failure_runner', 'runner.py')

ORIGINAL_GUEST_SHA256 = '81e51c751433ef08f88aaa7d2027a872a2a2cb522b23dd589342ed4c4faa2f47'
DIAGNOSTIC_HEADER_SHA256 = 'dd3ea43edd89fd7964e674eeb23a75438250a1d747bf0e02d9a42c613c3157c6'
ORIGINAL_RUN = "def run(argv, timeout=20, check=True, output_role=None):\n    require(output_role is None or (type(output_role) is str and output_role == 'interval-journal'),\n            'unknown-command-output-role')\n    result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)\n    code = 'command-output-bound'\n    if output_role is not None:\n        # Only this source-assigned role and builtin byte counts enter a failed\n        # gate code. Never include argv, the cursor, logs, stderr or error text.\n        require(type(result.stdout) is bytes and type(result.stderr) is bytes, 'command-output-byte-types')\n        code += '-journal-o' + str(len(result.stdout)) + '-e' + str(len(result.stderr))\n    require(len(result.stdout) + len(result.stderr) < 16 * 1024 * 1024, code)\n    if check:\n        require(result.returncode == 0, 'command-failed')\n    return result\n"
ORIGINAL_MAIN = "def main():\n    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))\n    if len(sys.argv) == 4 and sys.argv[1] == '_receiver':\n        receiver(sys.argv[2], sys.argv[3]); return 0\n    parser = argparse.ArgumentParser(description=__doc__)\n    parser.add_argument('stage', choices=('live', 'installed'))\n    parser.add_argument('--disposable-guest', action='store_true')\n    args = parser.parse_args()\n    require(args.disposable_guest and os.geteuid() == 0, 'explicit-root-disposable-guest-required')\n    require(HERE == DATA / 'dictation-qualification', 'reviewed-test-cd-location-required')\n    require(run(['systemd-detect-virt']).stdout.strip() in (b'qemu', b'kvm'), 'qemu-kvm-guest-required')\n    live = 'rd.live.image' in Path('/proc/cmdline').read_text().split()\n    require(live == (args.stage == 'live'), 'actual-boot-stage-mismatch')\n    declared = context(read(DATA / 'dictation-context.json'))\n    if live:\n        declared = dict(declared, phase='live')\n    require((declared['phase'] == 'live') == live, 'context-boot-stage-mismatch')\n    for path, key in ((HERE / 'guest_check.py', 'checker_sha256'), (HERE / 'contract.py', 'contract_sha256'),\n                      (DATA / 'dictation-accuracy/accuracy.py', 'accuracy_sha256'),\n                      (DATA / 'dictation-accuracy/pins.json', 'pins_sha256'), (CONTROLLER, 'controller_sha256'),\n                      (CHILD_EXEC, 'child_exec_sha256')):\n        if path in (CONTROLLER, CHILD_EXEC):\n            owned_file(path)\n        require(sha(path) == declared[key], 'reviewed-source-hash-mismatch')\n    checker = Checker(declared)\n    report = checker.report\n    try:\n        report = checker.execute()\n    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):\n        pass\n    finally:\n        try:\n            checker.close()\n        except (OSError, Invalid, subprocess.TimeoutExpired):\n            report = checker.report\n            failed_gate = 'transcript-private-cleanup' if 'transcript-private-cleanup' in checker.gates else 'no-new-avcs'\n            for gate in report['gates']:\n                if gate['id'] == failed_gate:\n                    gate.update(status='failed', code='owned-cleanup-failed')\n    present = {g['id'] for g in report['gates']}\n    for name in sorted(checker.gates - present):\n        report['gates'].append({'id': name, 'status': 'unrun', 'evidence_kind': EXPECTED_KINDS[name],\n                               'code': 'prerequisite-or-collector-failed', 'observations': {}})\n    report['status'] = 'passed' if all(g['status'] == 'passed' for g in report['gates']) else 'failed'\n    validate(report, declared, fixture_manifest=DATA / 'dictation-fixtures/fixtures.json')\n    print('ARCTIC-DICTATION-QUALIFICATION ' + json.dumps(report, sort_keys=True), flush=True)\n    return int(report['status'] != 'passed')\n"
ORIGINAL_FOOTER = 'if __name__ == \'__main__\':\n    try:\n        sys.exit(main())\n    except (Invalid, OSError, ValueError, subprocess.TimeoutExpired, KeyError, TypeError):\n        print(\'ARCTIC-DICTATION-COLLECTOR-ERROR {"code":"collector-guard-or-setup-failed","release_acceptance":false}\', flush=True)\n        sys.exit(1)\n'

CURRENT_RUN_SHA256 = '88de3bf40377d2b245082689b1f236b965d27db2711931d61302f80348dbabaf'
CURRENT_MAIN_SHA256 = '1a8c9392a74d2a4ae2295e8230f1117f06d0e1ec9594385de509e5dced2ea5cf'
CURRENT_FOOTER_SHA256 = 'de3bab56ae8993d6e30005c326fd50ce9c3228c11f32798b42e7fa09e587c1d0'

def restore_collector_failure_projection(text):
    """Exact whole-byte inverse to actual 53a; unknown changes fail closed."""
    from test_report_guard_projection import restore_report_guard_projection
    text = restore_report_guard_projection(text)
    if "# Failure-only observations." not in text:
        return text
    start = text.index("# Failure-only observations.")
    end = text.index("def verify_small_cpu_fixture(", start)
    header = text[start:end]
    assert hashlib.sha256(header.encode()).hexdigest() == DIAGNOSTIC_HEADER_SHA256
    text = text[:start] + text[end:]
    assert text.count("import dis\n") == 1
    text = text.replace("import dis\n", "", 1)
    for name, original, expected in (("run", ORIGINAL_RUN, CURRENT_RUN_SHA256), ("main", ORIGINAL_MAIN, CURRENT_MAIN_SHA256)):
        node = next(node for node in ast.parse(text).body if isinstance(node, ast.FunctionDef) and node.name == name)
        lines = text.splitlines(keepends=True)
        assert hashlib.sha256("".join(lines[node.lineno - 1:node.end_lineno]).encode()).hexdigest() == expected
        lines[node.lineno - 1:node.end_lineno] = original.splitlines(keepends=True)
        text = "".join(lines)
    footer_start = text.index("if __name__ == '__main__':\n")
    assert hashlib.sha256(text[footer_start:].encode()).hexdigest() == CURRENT_FOOTER_SHA256
    text = text[:footer_start] + ORIGINAL_FOOTER
    assert hashlib.sha256(text.encode()).hexdigest() == ORIGINAL_GUEST_SHA256
    return text

def command_failure(code=17):
    with mock.patch.object(g.subprocess, 'run', return_value=subprocess.CompletedProcess(
            ['private argv'], code, b'private transcript stdout', b'private stderr')):
        try:
            g.run(['private argv'])
        except g.Invalid as error:
            return error
    raise AssertionError('failure was not raised')

class PrivateError(g.Invalid):
    def __str__(self):
        raise AssertionError('private formatting')
    @property
    def args(self):
        raise AssertionError('private args')
    @property
    def __traceback__(self):
        raise AssertionError('private traceback')
    @property
    def __dict__(self):
        raise AssertionError('private dict')

class CollectorFailureProjection(unittest.TestCase):
    def test_whole_byte_inverse_rejects_undeclared_predicate_header_and_footer_changes(self):
        text = HERE.joinpath('guest_check.py').read_text()
        restored = restore_collector_failure_projection(text)
        self.assertEqual(hashlib.sha256(restored.encode()).hexdigest(), ORIGINAL_GUEST_SHA256)
        for before, after in (("require(result.returncode == 0, 'command-failed')", "require(True, 'command-failed')"),
                              ("require(HERE == DATA / 'dictation-qualification'", "require(True"),
                              ("print('ARCTIC-DICTATION-COLLECTOR-FAILURE '", "print('PRIVATE '") ,
                              ("sys.exit(1)", "sys.exit(0)")):
            self.assertIn(before, text)
            with self.assertRaises(AssertionError):
                restore_collector_failure_projection(text.replace(before, after, 1))

    def setUp(self):
        self.old_phase = g.collector_failure_phase
        g.collector_failure_phase = 'checker-init'

    def tearDown(self):
        g.collector_failure_phase = self.old_phase

    def record(self, error):
        value = g.collector_failure(error)
        self.assertIs(value['release_acceptance'], False)
        self.assertNotIn('private', json.dumps(value))
        self.assertEqual(r.collector_failure_record(json.dumps(value).encode()), value)
        return value

    def test_closed_tables_and_hostile_exception_have_no_private_reads(self):
        self.assertEqual(set(g.COLLECTOR_FAILURE_PHASES), r.COLLECTOR_FAILURE_PHASES)
        self.assertEqual({v for _, v in g.COLLECTOR_ERROR_CLASSES} | {'other-error'}, r.COLLECTOR_FAILURE_ERRORS)
        self.assertEqual(set(g.COLLECTOR_FAILURE_FRAMES), r.COLLECTOR_FAILURE_FRAMES)
        self.assertEqual(set(g.COLLECTOR_FAILURE_GUARDS) | {'unknown'}, r.COLLECTOR_FAILURE_GUARDS)
        value = self.record(PrivateError('private transcript'))
        self.assertEqual((value['error'], value['frame'], value['guard']), ('other-error', 'unknown', 'unknown'))
        g.collector_failure_phase = 'private phase'
        self.assertEqual(self.record(FileNotFoundError('private path'))['phase'], 'entry')

    def test_actual_owned_guard_is_finite_and_same_exception_survives(self):
        info = SimpleNamespace(st_mode=stat.S_IFREG | 0o444, st_uid=0, st_size=1)
        with mock.patch.object(g.Path, 'lstat', return_value=info):
            try:
                g.owned_file('/private filename', size=2)
            except g.Invalid as error:
                original = error
                error.args = ('private transcript changed after raising',)
                value = self.record(error)
                self.assertEqual((value['frame'], value['guard']), ('installed-file', 'installed-file-size'))
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    g.emit_collector_failure(error)
                self.assertIs(error, original)
                self.assertNotIn('private', out.getvalue())
            else:
                self.fail('guard did not raise')

    def test_real_command_failure_records_only_source_minted_builtin_exit(self):
        for code in (17, -9):
            with self.subTest(code=code):
                error = command_failure(code)
                value = self.record(error)
                self.assertEqual((value['frame'], value['guard'], value['command_returncode']),
                                 ('command', 'command-failed', code))
        for code in (True, 256, -256):
            with self.subTest(code=code):
                self.assertIsNone(self.record(command_failure(code))['command_returncode'])
        with mock.patch.object(g.subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['private argv'], 17, b'private stdout', b'private stderr')):
            try:
                g.Checker.audit_state()
            except g.Invalid as error:
                value = self.record(error)
                self.assertEqual((value['frame'], value['caller'], value['command_returncode']),
                                 ('command', 'audit-state', 17))
            else:
                self.fail('actual audit command did not fail')

    def test_foreign_raising_frame_or_copied_token_never_mints_guard_or_exit(self):
        proof = command_failure().__dict__['_arctic_dictation_command_exit']
        def foreign():
            g.require(False, 'command-failed')
        try:
            foreign()
        except g.Invalid as error:
            error.__dict__['_arctic_dictation_command_exit'] = proof
            value = self.record(error)
            self.assertEqual((value['frame'], value['guard'], value['command_returncode']),
                             ('unknown', 'unknown', None))
        with mock.patch.object(g.subprocess, 'run', side_effect=g.Invalid('private transcript')):
            try:
                g.run(['private argv'])
            except g.Invalid as error:
                value = self.record(error)
                self.assertEqual((value['frame'], value['guard'], value['command_returncode']),
                                 ('unknown', 'unknown', None))

    def test_truncated_trace_is_unknown_instead_of_partial_owner(self):
        def recurse(depth):
            if depth:
                return recurse(depth - 1)
            raise command_failure()
        try:
            recurse(70)
        except g.Invalid as error:
            value = self.record(error)
            self.assertEqual((value['frame'], value['guard'], value['command_returncode']),
                             ('unknown', 'unknown', None))

    def test_actual_main_argument_guard_phase_and_failure_predicate_preserved(self):
        with mock.patch.object(g.sys, 'argv', ['guest_check.py', 'installed']), \
                mock.patch.object(g.resource, 'setrlimit'):
            try:
                g.main()
            except g.Invalid as error:
                value = self.record(error)
            else:
                self.fail('argument guard did not fail')
        self.assertEqual((value['phase'], value['frame'], value['guard']),
                         ('arguments', 'main', 'explicit-root-disposable-guest-required'))

    def test_emission_failure_cannot_replace_original_exception(self):
        error = command_failure()
        with mock.patch('builtins.print', side_effect=OSError('private output failure')):
            self.assertIsNone(g.emit_collector_failure(error))
        self.assertEqual(self.record(error)['command_returncode'], 17)

    def test_host_parser_rejects_private_unknown_duplicate_and_bool_numeric_fields(self):
        valid = self.record(command_failure())
        for field in ('phase', 'error', 'frame', 'caller', 'guard', 'schema'):
            bad = dict(valid, **{field: 'private transcript'})
            self.assertIsNone(r.collector_failure_record(json.dumps(bad).encode()))
        for code in (True, False, 0, 256, -256, 'private'):
            self.assertIsNone(r.collector_failure_record(json.dumps(dict(valid, command_returncode=code)).encode()))
        for raw in (b'{"phase":"execute","phase":"execute"}', b'{"x":NaN}', b'\x1b[31m' + json.dumps(valid).encode(),
                    b'\xff', b'{}', json.dumps(dict(valid, transcript='private')).encode()):
            self.assertIsNone(r.collector_failure_record(raw))
        bad = dict(valid, frame='main')
        self.assertIsNone(r.collector_failure_record(json.dumps(bad).encode()))

    def test_actual_owned_relay_emits_complete_fixed_records_only(self):
        value = self.record(command_failure())
        marker = b'ARCTIC-DICTATION-COLLECTOR-FAILURE ' + json.dumps(value).encode()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp, 'serial-boot.log')
            path.write_bytes(b'private transcript before\n' + marker + b'\r\n' + marker + b'\n'
                             + b'ARCTIC-DICTATION-COLLECTOR-FAILURE {"phase":"private"}\n'
                             + b'private stderr after\n' + marker)
            path.chmod(0o600)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                r.relay_collector_failures(Path(temp), 'online-installed')
            lines = out.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertNotIn('private', out.getvalue())
            self.assertTrue(lines[0].startswith('ARCTIC-DICTATION-GUEST-FAILURE online-installed '))
            decoded = json.loads(lines[0].split(' ', 2)[2])
            self.assertEqual(decoded, value)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                r.relay_collector_failures(Path(temp), 'private phase')
            self.assertEqual(out.getvalue(), '')

    def test_relay_rejects_symlink_writable_or_changed_owned_source(self):
        marker = b'ARCTIC-DICTATION-COLLECTOR-FAILURE ' + json.dumps(self.record(command_failure())).encode() + b'\n'
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp, 'target'); target.write_bytes(marker); target.chmod(0o600)
            path = Path(temp, 'serial-boot.log'); path.symlink_to(target)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):r.relay_collector_failures(Path(temp), 'online-installed')
            self.assertEqual(out.getvalue(), '')
            path.unlink(); path.write_bytes(marker); path.chmod(0o666)
            with contextlib.redirect_stdout(out):r.relay_collector_failures(Path(temp), 'online-installed')
            self.assertEqual(out.getvalue(), '')
            path.chmod(0o600)
            real_stat = r.os.stat
            def changed(name, *args, **kwargs):
                value = real_stat(name, *args, **kwargs)
                if name == 'serial-boot.log':
                    return SimpleNamespace(**{key: getattr(value, key) + (1 if key == 'st_size' else 0)
                                              for key in ('st_dev', 'st_ino', 'st_uid', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns')})
                return value
            with mock.patch.object(r.os, 'stat', side_effect=changed), contextlib.redirect_stdout(out):
                r.relay_collector_failures(Path(temp), 'online-installed')
            self.assertEqual(out.getvalue(), '')

if __name__ == '__main__':
    unittest.main()
