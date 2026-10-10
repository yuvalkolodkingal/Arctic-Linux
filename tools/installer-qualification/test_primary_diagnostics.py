"""Trusted first-error diagnostics stay private, bounded and failure-only."""
import ast
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import re
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import runner as R
G = R.E.guest
spec = importlib.util.spec_from_file_location('primary_active_guest', Path(__file__).parent / 'active-guest.py')
A = importlib.util.module_from_spec(spec)
spec.loader.exec_module(A)
spec = importlib.util.spec_from_file_location('primary_private_scanner', Path(__file__).parent.parent / 'native-functional/screen-evidence.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
PRIVATE = 'password=private-account; Transcript: private-audio; תמלול: private-hebrew'


class HostileError(RuntimeError):
    @property
    def args(self):
        raise AssertionError('private args must not be read')

    def __str__(self):
        raise AssertionError('private exception must not be formatted')


class PrimaryControls(unittest.TestCase):
    def test_every_trusted_literal_has_real_source_call_and_exact_projection(self):
        messages = set()
        for name in ('guest.py', 'active-guest.py'):
            for node in ast.walk(ast.parse((Path(__file__).parent / name).read_text())):
                if isinstance(node, ast.Call) and node.args:
                    func = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
                    last = node.args[-1]
                    if func in ('require', 'RuntimeError', 'wait') and isinstance(last, ast.Constant) and type(last.value) is str:
                        messages.add(last.value)
        self.assertGreater(len(G.PRIMARY_DIAGNOSTIC_LITERALS), 100)
        self.assertEqual(len(set(G.PRIMARY_DIAGNOSTIC_LITERALS.values())), len(G.PRIMARY_DIAGNOSTIC_LITERALS))
        for message, reason in G.PRIMARY_DIAGNOSTIC_LITERALS.items():
            with self.subTest(reason=reason):
                self.assertIn(message, messages)
                self.assertRegex(reason, r'^[a-z0-9]+(?:-[a-z0-9]+)*$')
                self.assertLessEqual(len(reason), 80)
                error = RuntimeError(message)
                self.assertEqual(G.primary_diagnostic_reason(error), reason)
                report = {'status': 'failed', 'errors': ['RuntimeError: ' + message]}
                before = copy.deepcopy(report)
                codes = R.primary_reported_codes(report, False)
                self.assertEqual(codes, ('installer-reported-idle-primary-reason-' + reason,))
                self.assertEqual(report, before)
                raw = ('ARCTIC-INSTALLER-DIAGNOSTIC=' + codes[0] + '\n').encode()
                self.assertIs(S.external_text(raw), raw)
                masked = G.masked_active_error(error, 'prepare-find-gui')
                codes = R.primary_reported_codes({'errors': [masked]}, True)
                self.assertEqual(codes[-1], 'installer-reported-active-primary-reason-' + reason)

    def test_near_literals_private_values_unicode_and_escape_never_match(self):
        message = 'requires exactly one already running packaged installer'
        for altered in (message + PRIVATE, PRIVATE + message, message + '\n', message + ' ',
                        message.replace('one', 'one\x1b[0m'), 'Transcript: ' + message,
                        'תמלול: ' + message, message.upper(), message.replace(' ', '\t')):
            with self.subTest(altered=repr(altered)):
                self.assertEqual(G.primary_diagnostic_reason(RuntimeError(altered)), 'unknown')
                self.assertEqual(R.primary_reported_codes({'errors': ['RuntimeError: ' + altered]}, False),
                                 ('installer-reported-idle-primary-unknown',))
                value = G.masked_active_error(RuntimeError(altered), 'prepare-account-fill')
                self.assertNotIn(PRIVATE, value)
                self.assertTrue(value.endswith('; reason=unknown]'))

    def test_hostile_exception_types_args_and_strings_are_never_inspected(self):
        class PrivateMeta(type):
            def __hash__(self):
                raise AssertionError('private class must not be hashed')
        PrivateClass = PrivateMeta('private-account-transcript', (HostileError,), {})
        for error in (HostileError(PRIVATE), PrivateClass(PRIVATE), RuntimeError(),
                      RuntimeError(PRIVATE, 'extra'), RuntimeError({'password': PRIVATE}),
                      ValueError(PRIVATE), OSError(PRIVATE), KeyboardInterrupt(PRIVATE), SystemExit(PRIVATE)):
            with self.subTest(kind=type(error).__name__):
                self.assertEqual(G.primary_diagnostic_reason(error), 'unknown')
                value = G.masked_active_error(error, 'prepare-account-fill')
                self.assertNotIn('private', value)
                self.assertNotIn('Transcript', value)
                self.assertNotIn('תמלול', value)
                self.assertTrue(R.primary_reported_codes({'errors': [value]}, True)[-1].endswith('reason-unknown'))

    def test_all_fixed_phases_reject_arbitrary_and_subclass_inputs(self):
        class PrivateString(str):
            def __hash__(self):
                raise AssertionError('private phase must not be hashed')
        for phase in G.ACTIVE_DIAGNOSTIC_PHASES:
            masked = G.masked_active_error(RuntimeError(PRIVATE), phase)
            codes = R.primary_reported_codes({'errors': [masked]}, True)
            self.assertIn('installer-reported-active-primary-phase-' + phase, codes)
            self.assertNotIn('private', '\n'.join(codes))
        for phase in (PRIVATE, None, {}, [], PrivateString('prepare-find-gui'), 'prepare-find-gui\n'):
            masked = G.masked_active_error(HostileError(PRIVATE), phase)
            self.assertIn('[phase=unknown;', masked)
            self.assertNotIn('private', masked)

    def test_report_bounds_first_error_only_and_old_active_mask_are_preserved(self):
        valid = G.masked_active_error(RuntimeError('requires exactly one already running packaged installer'), 'prepare-find-gui')
        for active in (False, True):
            prefix = 'installer-reported-' + ('active' if active else 'idle') + '-primary-'
            for report in (None, [], {}, {'errors': None}, {'errors': (valid,)}, {'errors': [valid] * 65},
                           {'errors': [None]}, {'errors': [{}]}, {'errors': ['x' * 4097]}):
                self.assertEqual(R.primary_reported_codes(report, active), (prefix + 'invalid',))
            self.assertEqual(R.primary_reported_codes({'errors': []}, active), (prefix + 'unrun',))
            self.assertEqual(R.primary_reported_codes({'errors': [PRIVATE, valid]}, active), (prefix + 'unknown',))
        self.assertEqual(R.primary_reported_codes({'errors': ['RuntimeError: active installation or restoration failed']}, True),
                         ('installer-reported-active-primary-masked',))
        for altered in (valid + '\n', valid + PRIVATE, valid.replace('prepare-find-gui', PRIVATE),
                        valid.replace('reason=requires-', 'reason=private-requires-'), valid.replace('RuntimeError:', 'PrivateError:')):
            self.assertEqual(R.primary_reported_codes({'errors': [altered]}, True),
                             ('installer-reported-active-primary-unknown',))

    def instance(self, root):
        value = A.installer_type(G).__new__(A.installer_type(G))
        value.context = {}; value.boot_id = 'synthetic-boot'; value.uid = 1000; value.session = 'synthetic-session'
        value.original_vt = 1; value.root = root; value.results = []; value.samples = []; value.capture_count = 0
        value.rpc = None; value.gui_fd = None; value.password = PRIVATE
        value.native = SimpleNamespace(SecurityInterval=lambda: SimpleNamespace(finish=lambda: {'selinux': 'Enforcing', 'observed_new_avcs': 0}))
        value.cleanup = lambda: {'original_vt_restored': True, 'engine_retained': False, 'errors': []}
        return value

    def test_actual_active_run_keeps_failed_verdict_cleanup_and_private_report_bytes(self):
        for phase in ('prepare-find-gui', 'prepare-account-fill', 'prepare-copy', 'prepare-baseline-physical'):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                def fault():
                    value.diagnostic_phase = phase
                    raise HostileError(PRIVATE)
                value.prepare = fault
                report = value.run()
                self.assertEqual(report['status'], 'failed')
                self.assertIs(report['release_acceptance'], False)
                self.assertNotIn('baseline', report)
                self.assertEqual(report['cases'], [])
                self.assertTrue(report['cleanup']['original_vt_restored'])
                self.assertIsNone(value.password)
                self.assertNotIn('private', json.dumps(report))
                private = (value.root / 'installer-report.json').read_bytes()
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout): R.diagnose_report(report, True)
                self.assertEqual((value.root / 'installer-report.json').read_bytes(), private)
                self.assertIn('installer-reported-active-primary-phase-' + phase, stdout.getvalue())
                self.assertNotIn('private', stdout.getvalue())
                raw = stdout.getvalue().encode()
                self.assertIs(S.external_text(raw), raw)

    def test_actual_prepare_first_shared_operations_assign_their_fixed_phase(self):
        for operation, phase in (('find_gui', 'prepare-find-gui'), ('identities', 'prepare-identities'),
                                 ('target_disk', 'prepare-target')):
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                value.find_gui = lambda: None
                value.identities = lambda: {}
                value.target_disk = lambda **_: {}
                setattr(value, operation, lambda *_, **__: (_ for _ in ()).throw(HostileError(PRIVATE)))
                with patch.object(G.EngineRPC, '__init__', lambda _: None):
                    with self.assertRaises(HostileError): value.prepare()
                self.assertEqual(value.diagnostic_phase, phase)
        with tempfile.TemporaryDirectory() as temp:
            value = self.instance(Path(temp)); value.find_gui = lambda: None; value.identities = lambda: {}
            with patch.object(G.EngineRPC, '__init__', side_effect=HostileError(PRIVATE)):
                with self.assertRaises(HostileError): value.prepare()
            self.assertEqual(value.diagnostic_phase, 'prepare-rpc')

    def test_actual_prepare_wizard_failure_phases_survive_masking_without_credentials(self):
        pages = ('welcome', 'keyboard', 'network', 'timezone', 'disk', 'encryption', 'account', 'apps', 'summary')
        phases = [('prepare-' + page + '-' + operation) for page in pages for operation in ('ready', 'valid', 'next')]
        phases += ['prepare-' + page + '-fill' for page in ('keyboard', 'network', 'disk', 'encryption', 'account', 'apps')]
        phases += ['prepare-credentials', 'prepare-summary-config', 'prepare-summary-identities', 'prepare-copy', 'prepare-visible', 'prepare-baseline-physical']
        for phase in phases:
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                observed = []
                def tick():
                    observed.append(value.diagnostic_phase)
                    if value.diagnostic_phase == phase:
                        raise HostileError(PRIVATE)
                value.find_gui = lambda: None
                value.identities = lambda: tick() or {'synthetic': 'same-original-identity'}
                value.target_disk = lambda **_: tick() or {}
                value.ipc = lambda *_, **__: tick() or 'ok'
                def wait(*_):
                    tick()
                    return {'identities': {'synthetic': 'same-original-identity'}, 'writer': {'process': {}}} if value.diagnostic_phase == 'prepare-copy' else True
                value.wait = wait
                value.state = lambda: tick() or {}
                value.outputs = lambda: tick() or []
                value.command = lambda *_, **__: tick() or (0, '{"layers": []}', '')
                value.visible = lambda *_, **__: tick() or {}
                value.capture = lambda *_, **__: tick() or {}
                value.drm_heads = lambda: tick() or {}
                value.packaged_sources = lambda: tick() or {}
                def read(*_):
                    tick()
                    return json.dumps({'password': 'a' * 32}).encode()
                def rpc_init(self):
                    self.peer = {}
                def rpc_call(_self, _method, params):
                    tick()
                    data = {'disk': {'disk': '/dev/vda', 'mode': 'erase'}, 'encryption': {'enabled': False},
                            'network': {'offline': True}, 'apps': {}}[params['id']]
                    return {'data': data}
                with patch.object(G, 'read_regular', read), patch.object(G.EngineRPC, '__init__', rpc_init), \
                     patch.object(G.EngineRPC, 'call', rpc_call), patch.object(G.EngineRPC, 'close', lambda _: None):
                    report = value.run()
                self.assertIn(phase, observed)
                self.assertEqual(report['status'], 'failed')
                self.assertIs(report['release_acceptance'], False)
                self.assertEqual(report['cases'], [])
                self.assertNotIn('baseline', report)
                self.assertIsNone(value.password)
                self.assertNotIn('private', json.dumps(report))
                codes = R.primary_reported_codes(report, True)
                self.assertIn('installer-reported-active-primary-phase-' + phase, codes)
                self.assertNotIn('private', '\n'.join(codes))

    def test_no_new_report_field_success_gate_or_masked_exception_formatting(self):
        source = ast.parse((Path(__file__).parent / 'active-guest.py').read_text())
        calls = [node for node in ast.walk(source) if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                 and node.func.attr == 'masked_active_error']
        self.assertEqual(len(calls), 1)
        self.assertEqual(ast.unparse(calls[0]), 'G.masked_active_error(exc, self.diagnostic_phase)')
        self.assertNotIn('str(error)', ast.unparse(ast.parse(__import__('inspect').getsource(G.masked_active_error))))
        self.assertNotIn('str(error)', ast.unparse(ast.parse(__import__('inspect').getsource(G.primary_diagnostic_reason))))
        value = G.masked_active_error(RuntimeError(PRIVATE), 'prepare-account-fill')
        report = {'status': 'failed', 'errors': [value], 'cases': [], 'release_acceptance': False}
        before = copy.deepcopy(report)
        R.reported_codes(report, True)
        self.assertEqual(report, before)
        with patch('builtins.print', side_effect=BrokenPipeError('private')): R.diagnose_report(report, True)


if __name__ == '__main__':
    unittest.main()
