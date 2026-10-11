"""Failure-only synthetic diagnostics; no VM, private-content export or acceptance."""
import ast
import contextlib
import io
import os
import socket
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import runner as R
import test_stage_diagnostics as Stage
PrivateError = Stage.PrivateError
D = R._driver
TOKEN = 'a' * 32
PRIVATE = b'private-password-argv-transcript-stderr'


def record(code, token=TOKEN):
    return ('ARCTIC-INSTALLER-INNER ' + token + ' ' + code + '\n').encode()


class InnerControls(unittest.TestCase):
    def test_actual_driver_phase_failure_preserves_owned_cleanup_and_private_state(self):
        for failed_stage in ('driver-display', 'driver-prepare', 'driver-acquire', 'driver-enable',
                             'driver-menu', 'driver-console', 'driver-controller', 'driver-launch',
                             'driver-collect', 'driver-transitions', 'driver-live-report'):
            with self.subTest(stage=failed_stage), tempfile.TemporaryDirectory() as temp:
                out = Path(temp); (out / 'data').mkdir()
                (out / 'data/installer-context.json').write_text(
                    '{"schema":"arctic-installer-active-context-v1","disk_bytes":68719476736,"disk_serial":"arctic-a-aaaaaaaaaaa","write_bps":8388608}')
                (out / 'installer-port.log').write_text('ARCTIC-INSTALLER-REPORT {"status":"failed"}\n')
                cleanup = []; saved = []; stopped = False
                def fault(stage):
                    if failed_stage == stage: raise ValueError('private-stage-error')
                def operation(stage, result=None):
                    def call(*args, **kwargs): fault(stage); return result
                    return call
                proc = SimpleNamespace(pid=17, poll=lambda: 0 if stopped else None)
                vm = SimpleNamespace(proc=proc, alive=lambda: failed_stage != 'driver-collect',
                    type_text=operation('driver-launch'), keys=lambda *_: None,
                    close_handles=lambda: cleanup.append('handles'))
                display = SimpleNamespace(enable=operation('driver-enable', {}), closed=False)
                control = SimpleNamespace(poll=lambda *_: None, finish=operation('driver-transitions', []),
                    restore=lambda: cleanup.append('outputs') or {})
                display_module = SimpleNamespace(TaskbarDisplay=operation('driver-display', display),
                    qmp_query=lambda _vm, name: {'running': True})
                controller_module = SimpleNamespace(InstallerController=operation('driver-controller', control),
                    strict_json=__import__('json').loads, cleanup_signals=lambda: contextlib.nullcontext([]),
                    persist_cleanup_state=lambda path, state, errors, pending: saved.append((dict(state), list(errors))))
                def load(name, path): return display_module if name == 'installer_display_fixture' else controller_module
                def stop(*_):
                    nonlocal stopped
                    stopped = True; display.closed = True; cleanup.append('host')
                def factory(*_): fault('driver-acquire'); return vm
                stream = io.StringIO()
                with contextlib.ExitStack() as stack:
                    for obj, name, value in ((D.os, 'geteuid', lambda: 0), (Path, 'is_char_device', lambda _: True),
                        (D, 'load', load), (D, 'sha', lambda _: 'a' * 64), (D.signal, 'signal', lambda *_: None),
                        (D, 'prepare_vm', operation('driver-prepare', ['private-argv'])),
                        (D, 'owned_vm_type', lambda *_: factory), (D, 'choose_install', operation('driver-menu')),
                        (D, 'authenticate_console', operation('driver-console', {})), (D, 'stop_owned', stop)):
                        stack.enter_context(patch.object(obj, name, value))
                    stack.enter_context(patch.dict(sys.modules, {'vmtest': SimpleNamespace(serial_has=lambda *_: True),
                                                                 'iso_startup': SimpleNamespace()}))
                    stack.enter_context(patch.dict(os.environ, {'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN': TOKEN}))
                    stack.enter_context(patch.object(sys, 'argv', ['driver', '--out', str(out)]))
                    stack.enter_context(contextlib.redirect_stdout(stream))
                    status = D.main()
                self.assertEqual(status, 1)
                self.assertEqual(len(saved), 1)
                self.assertIs(saved[0][0]['release_acceptance'], False)
                self.assertTrue(saved[0][1])
                self.assertIn('host', cleanup)
                self.assertNotIn('private', stream.getvalue())
                suffix = 'evidence-incomplete' if failed_stage == 'driver-collect' else 'collector-failed' if failed_stage == 'driver-live-report' else 'value-error'
                self.assertEqual(R.inner_codes(stream.getvalue().encode(), TOKEN),
                                 ('installer-inner-' + failed_stage + '-' + suffix,))

    def test_fixed_driver_classes_and_literals_never_format_private_errors(self):
        for stage in D.DIAGNOSTIC_STAGES:
            for error_class, label in D.DIAGNOSTIC_ERROR_TYPES:
                if error_class is subprocess.TimeoutExpired:
                    error = error_class(['private-argv'], 1, output=PRIVATE, stderr=PRIVATE)
                elif error_class is subprocess.CalledProcessError:
                    error = error_class(1, ['private-argv'], output=PRIVATE, stderr=PRIVATE)
                else:
                    error = error_class(PRIVATE)
                code = D.diagnostic_code(stage, error)
                self.assertEqual(code, 'installer-inner-' + stage + '-' + label)
                self.assertIn(code, D.DIAGNOSTIC_CODES)
            for message, label in D.DIAGNOSTIC_LITERALS.get(stage, ()):
                code = D.diagnostic_code(stage, PrivateError(message))
                self.assertEqual(code, 'installer-inner-' + stage + '-' + label)
                self.assertIn(code, D.DIAGNOSTIC_CODES)
            for args in ((), (PRIVATE,), ('private', 'extra'), ({'private': 'text'},)):
                self.assertEqual(D.diagnostic_code(stage, PrivateError(*args)),
                                 'installer-inner-' + stage + '-runtime-error')
        self.assertTrue(all(len(code) <= 80 for code in D.DIAGNOSTIC_CODES))

    def test_nonce_bound_complete_lines_reject_forgery_and_private_content(self):
        code = 'installer-inner-driver-live-report-collector-failed'
        raw = PRIVATE + b'\n' + record(code, 'b' * 32) + record('private-forged-stage') + record(code)
        raw += record(code) + record(code).rstrip(b'\n')
        self.assertEqual(R.inner_codes(raw, TOKEN), (code,))
        for raw in (PRIVATE, record(code).rstrip(b'\n'), b'private-prefix ' + record(code),
                    record(code).replace(b'\n', b'\r\n'), record(code)[:-2] + b'\xff\n', b'x' * (16 * 1024 * 1024 + 1)):
            self.assertEqual(R.inner_codes(raw, TOKEN), ())
        for token in ('', 'private-token', 'a' * 31, 'A' * 32, None):
            self.assertEqual(R.inner_codes(record(code), token), ())

    def test_relay_retains_original_log_rejects_symlinks_and_closed_stdout(self):
        code = 'installer-inner-container-data-command-error'
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'private.log'; raw = PRIVATE + b'\n' + record(code); path.write_bytes(raw)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout): R.relay_inner(path, TOKEN)
            self.assertEqual(stdout.getvalue(), 'ARCTIC-INSTALLER-DIAGNOSTIC=' + code + '\n')
            self.assertEqual(path.read_bytes(), raw)
            link = Path(temp) / 'link'; link.symlink_to(path)
            with contextlib.redirect_stdout(io.StringIO()) as out: R.relay_inner(link, TOKEN)
            self.assertEqual(out.getvalue(), '')
            with patch('builtins.print', side_effect=BrokenPipeError('private')): R.relay_inner(path, TOKEN)
            fifo = Path(temp) / 'fifo'; os.mkfifo(fifo)
            sock_path = Path(temp) / 'socket'
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.bind(str(sock_path))
                for nonregular in (fifo, sock_path, Path(temp)):
                    script = 'import sys;sys.path.insert(0,sys.argv[1]);import runner;runner.relay_inner(sys.argv[2],sys.argv[3])'
                    result = subprocess.run([sys.executable, '-B', '-c', script, str(Path(__file__).parent), str(nonregular), TOKEN],
                                            capture_output=True, timeout=2)
                    self.assertEqual(result.returncode, 0)
                    self.assertEqual(result.stdout, b'')

    def test_shell_emission_failure_status_and_fixed_stage_binding(self):
        source = (Path(__file__).parent / 'run-live.sh').read_text()
        # Execute each actual shell emitter/trap, without running host setup or containers.
        host = source[source.index('diagnostic_stage=run-live-init'):source.index('HERE=')]
        container = source[source.index('diagnostic_stage=container-packages'):source.index('rpm -q qemu-system')]
        for prelude, stage in ((host, 'run-live-init'), (container, 'container-packages')):
            for status in (0, 7):
                result = subprocess.run(['bash', '-c', 'set -euo pipefail\n' + prelude + '\nexit ' + str(status)],
                                        env=dict(os.environ, ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN=TOKEN), capture_output=True)
                self.assertEqual(result.returncode, status)
                expected = record('installer-inner-' + stage + '-command-error') if status else b''
                self.assertEqual(result.stdout, expected)
                self.assertEqual(R.inner_codes(result.stdout, TOKEN),
                                 ('installer-inner-' + stage + '-command-error',) if status else ())
        import re
        for stage in re.findall(r'^diagnostic_stage=([a-z-]+)$', source, re.M):
            self.assertIn(stage, D.DIAGNOSTIC_STAGES)
        bootstrap = source.split("<<'BOOTSTRAP'\n", 1)[1].split('\nBOOTSTRAP', 1)[0]
        self.assertNotIn('DIAGNOSTIC_TOKEN', bootstrap)
        self.assertNotIn('DIAGNOSTIC_TOKEN', source.split("<<'PY'\n", 1)[1].split('\nPY', 1)[0])

    def test_failed_actual_runner_relays_only_its_host_nonce_and_keeps_failure(self):
        code = 'installer-inner-driver-live-report-collector-failed'
        def raw(token): return PRIVATE + b'\n' + record(code, 'b' * 32) + record(code, token) + record('private-stage', token)
        status, stdout, state, _, contract = Stage.Controls().pipeline('run-live', active=True, inner_log=raw)
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertIs(state['release_acceptance'], False)
        self.assertIn('ARCTIC-INSTALLER-DIAGNOSTIC=' + code, stdout)
        self.assertNotIn('private-', stdout)
        self.assertEqual(len(contract.cleanup_images), 2)
        self.assertNotIn('diagnostic_token', state)
        self.assertNotIn('diagnostic_token', state['context'])

    def test_report_summary_fixed_required_cases_and_scalars_are_not_acceptance(self):
        report = {'status': 'failed', 'baseline': {'secret': 'private'}, 'cases': [
            {'kind': 'vt', 'cycle': 0, 'status': 'passed'},
            {'kind': 'output', 'cycle': 0, 'status': 'private-status'}],
            'cleanup': {'original_vt_restored': True, 'engine_retained': False},
            'security': {'selinux': 'Enforcing', 'observed_new_avcs': 0}, 'errors': [PRIVATE.decode()]}
        original = repr(report)
        codes = R.reported_codes(report, True)
        for label in ('status-failed', 'baseline-observed', 'completion-unrun', 'vt-0-passed', 'output-0-invalid',
                      'cleanup-original-vt-restored-passed', 'cleanup-engine-retained-failed', 'selinux-enforcing', 'avcs-clean'):
            self.assertIn('installer-reported-active-' + label, codes)
        self.assertEqual(repr(report), original)
        self.assertNotIn('private', '\n'.join(codes))
        report['cases'].append({'kind': 'vt', 'cycle': 0, 'status': 'passed'})
        self.assertIn('installer-reported-active-vt-0-invalid', R.reported_codes(report, True))
        report['cases'] = [{'kind': 'vt', 'cycle': False, 'status': 'passed'}]
        self.assertIn('installer-reported-active-vt-0-unrun', R.reported_codes(report, True))
        idle = R.reported_codes({'status': 'failed', 'cases': []}, False)
        self.assertTrue(all('installer-reported-idle-' + kind + '-' + str(cycle) + '-unrun' in idle
                            for kind in ('vt', 'output') for cycle in range(3)))
        status, stdout, state, _, _ = Stage.Controls().pipeline('report-validation', active=True, report_value=report)
        self.assertEqual(status, 1)
        self.assertEqual(state['status'], 'failed')
        self.assertIs(state['release_acceptance'], False)
        self.assertNotIn('private', stdout)
        self.assertIn('installer-reported-active-completion-unrun', stdout)

    def test_selected_validation_literals_are_actual_constant_assertions(self):
        root = Path(__file__).parent
        literals = {node.value for name in ('contract.py', 'active-contract.py')
                    for node in ast.walk(ast.parse((root / name).read_text()))
                    if isinstance(node, ast.Constant) and type(node.value) is str}
        for message, _ in R.DIAGNOSTIC_LITERALS['report-validation']:
            self.assertIn(message, literals | {'Host and guest actual transitions differ'})

    def test_driver_emit_missing_nonce_and_closed_stdout_are_silent(self):
        for token in ('', 'private', 'a' * 31):
            with patch.dict(os.environ, {'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN': token}), contextlib.redirect_stdout(io.StringIO()) as out:
                D.diagnose('driver-collect', PrivateError('private'))
            self.assertEqual(out.getvalue(), '')
        with patch.dict(os.environ, {'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN': TOKEN}), patch('builtins.print', side_effect=ValueError('private')):
            D.diagnose('driver-collect', PrivateError('private'))


if __name__ == '__main__': unittest.main()
