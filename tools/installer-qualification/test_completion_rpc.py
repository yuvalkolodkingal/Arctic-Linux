"""Real framed ActiveRPC/completion controls; no daemon, VM or ISO qualification."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import tracemalloc
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import runner as R
G = R.E.guest
HERE = Path(__file__).parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


A = load('completion_rpc_active', HERE / 'active-guest.py')
AC = load('completion_rpc_contract', HERE / 'active-contract.py')
Installer = A.installer_type(G)
# Use the exact class captured by real prepare, not a replacement snapshot.
ActiveRPC = dict(zip(Installer.prepare.__code__.co_freevars,
                    (cell.cell_contents for cell in Installer.prepare.__closure__)))['ActiveRPC']
PRIVATE = 'password=private-account; Transcript: private-audio; תמלול: private-hebrew'


class FramedSocket:
    """A bounded synthetic wire peer; real EngineRPC.call parses every reply."""
    def __init__(self, states=('done',), failed=False, attention=False):
        self.states = list(states)
        self.failed, self.attention = failed, attention
        self.requests, self.pending = [], b''
        self.state = 'wizard'
        self.config = {'disk': {'disk': '/dev/vda', 'mode': 'erase'},
                       'encryption': {'enabled': False}, 'apps': {'selection': {}},
                       'network': {'offline': True}}
        self.hello_overrides = {}
        self.injected = None
        self.bad_id = False
        self.closed = False
        self.operand_states = []
        self.phase = 'finalize'
        self.phase_states = []

    def settimeout(self, timeout):
        assert .01 <= timeout <= 5

    def connect(self, path):
        assert path == G.SOCKET_PATH

    def getsockopt(self, level, option, size):
        assert (level, option, size) == (socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize('3i'))
        return struct.pack('3i', 1, 0, 0)  # Synthetic credentials, not a real root daemon claim.

    def sendall(self, wire):
        if self.injected is not None:
            raise self.injected
        assert wire.endswith(b'\n') and wire.count(b'\n') == 1 and not self.pending
        request = json.loads(wire)
        self.requests.append(request)
        method, params = request['method'], request.get('params')
        if method == 'Hello':
            assert params == {'client': 'installer-restoration-qualification', 'version': '1.2.1'}
            if self.states:
                self.state = self.states.pop(0)
            if self.operand_states:
                self.failed, self.attention = self.operand_states.pop(0)
            if self.phase_states:
                self.phase = self.phase_states.pop(0)
            result = dict(engine_version='1.2.1', protocol_version=1, live=True, mock=False,
                          firmware='uefi', state=self.state, private_details=PRIVATE)
            result.update(self.hello_overrides)
        elif method == 'GetWizard':
            assert params is None
            result = dict(current='done' if self.state == 'done' else 'install', state=self.state)
        elif method == 'GetStep' and params == {'id': 'install'}:
            result = dict(id='install', options=dict(modules=[], failed=self.failed, attention=self.attention,
                progress=dict(event='progress', percent=100, phase=self.phase, apps_done=0,
                              apps_total=0, paused=False), private_details=PRIVATE))
        elif method == 'GetStep' and params == {'id': 'keyboard'}:
            result = dict(id='keyboard', data={'layout': 'il', 'variant': ''})
        elif method == 'GetStep' and params['id'] in self.config:
            result = dict(data=self.config[params['id']])
        elif method == 'GetStep' and params == {'id': 'welcome'}:
            result = dict(id='welcome', data={'language': 'he'})
        else:
            raise AssertionError('fixture request outside the original whitelist')
        self.pending = (json.dumps({'id': request['id'] + (1 if self.bad_id else 0),
                                  'result': result}) + '\n').encode()

    def recv(self, size):
        chunk, self.pending = self.pending[:min(size, 7)], self.pending[min(size, 7):]
        return chunk

    def close(self):
        self.closed = True


def fixture(peer):
    def factory(family, kind):
        assert (family, kind) == (socket.AF_UNIX, socket.SOCK_STREAM)
        return peer
    rpc = ActiveRPC(factory=factory)
    value = Installer.__new__(Installer)
    value.rpc, value.deadline, value.started_ns = rpc, 5000, 1
    value.diagnostic_phase = 'completion'
    identities = {'daemon': {'pid': 20}}
    keyboard = {'synthetic-keyboard': 'Hebrew il'}
    value.safe_config = peer.config
    value.baseline = dict(identities=identities, keyboard_files=keyboard)
    value.ipc = lambda method: json.dumps({'page': 'done', 'current': 'done', 'percent': 100})
    value.identities = lambda: identities
    value.keyboard_files = lambda: keyboard
    return value


class CompletionRPCControls(unittest.TestCase):
    def test_real_active_wire_snapshot_reaches_done_while_shared_default_stays_wizard(self):
        peer = FramedSocket(states=('installing', 'done'))
        value = fixture(peer)
        clock = [0]
        def sleep(seconds):
            self.assertEqual(seconds, .2)
            self.assertEqual(value.diagnostic_phase, 'completion-wait')
            clock[0] += seconds
        with patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(G.time, 'monotonic_ns', return_value=101), patch.object(G.time, 'sleep', side_effect=sleep):
            result = value.finish_install()
        self.assertEqual(result['engine']['hello']['state'], 'done')
        self.assertEqual(result['gui'], {'page': 'done', 'current': 'done', 'percent': 100})
        self.assertEqual(result['keyboard_files'], value.baseline['keyboard_files'])
        self.assertEqual(result['identities'], value.baseline['identities'])
        self.assertEqual(result['elapsed_ns'], 100)
        self.assertEqual(value.diagnostic_phase, 'completion')
        self.assertNotIn('private', json.dumps(result))
        self.assertEqual([request['id'] for request in peer.requests], list(range(1, len(peer.requests) + 1)))
        for state in ('done', 'installing'):
            peer = FramedSocket(states=(state,))
            rpc = G.EngineRPC(factory=lambda *_: peer)
            with self.subTest(default_state=state), self.assertRaisesRegex(RuntimeError, 'actual live engine identity/state differs'):
                rpc.snapshot()
        peer = FramedSocket(states=('wizard',))
        self.assertEqual(G.EngineRPC(factory=lambda *_: peer).snapshot()['hello']['state'], 'wizard')

    def test_real_wire_failure_operands_use_same_snapshot_and_original_bound(self):
        for failed, attention in ((False, True), (True, False), (True, True)):
            peer = FramedSocket(failed={'details': PRIVATE} if failed else None,
                                attention={'details': PRIVATE} if attention else None)
            value, clock = fixture(peer), [0]
            def sleep(seconds):
                self.assertEqual(seconds, .2)
                clock[0] = 2401
            with self.subTest(failed=failed, attention=attention), \
                    patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(G.time, 'sleep', side_effect=sleep), self.assertRaises(RuntimeError) as caught:
                value.finish_install()
            self.assertEqual(caught.exception.args, ('same real installation did not finish within its separate bound: real active installation failed or requires attention',))
            self.assertEqual(value.diagnostic_phase, 'completion-engine-guard')
            label = 'failed-' + str(failed).lower() + '-attention-' + str(attention).lower()
            self.assertEqual(value.completion_guard_diagnostic, label)
            masked = G.masked_active_error(caught.exception, value.diagnostic_phase, value.completion_guard_diagnostic)
            codes = R.primary_reported_codes({'errors': [masked]}, True)
            self.assertIn('installer-reported-active-primary-engine-guard-' + label, codes)
            self.assertNotIn('private', masked + '\n'.join(codes))
            self.assertEqual(sum(request['method'] == 'Hello' for request in peer.requests), 1)

    def test_real_wire_identity_framing_and_cancellation_are_not_relaxed(self):
        for key, bad in (('live', False), ('mock', True), ('engine_version', 'foreign'), ('protocol_version', 2)):
            peer = FramedSocket(); peer.hello_overrides[key] = bad
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'actual active engine identity differs'):
                fixture(peer).rpc.snapshot()
        peer = FramedSocket(); peer.bad_id = True
        with self.assertRaisesRegex(RuntimeError, 'engine returned an error, event, or different response id'):
            fixture(peer).rpc.snapshot()
        for error in (TypeError(PRIVATE), KeyboardInterrupt(PRIVATE), SystemExit(PRIVATE)):
            peer = FramedSocket(); peer.injected = error
            value = fixture(peer)
            with self.subTest(error=type(error).__name__), patch.object(G.time, 'monotonic', return_value=0), \
                    patch.object(G.time, 'sleep', side_effect=AssertionError('must not retry cancellation')), \
                    self.assertRaises(type(error)) as caught:
                value.finish_install()
            self.assertIs(caught.exception, error)
            self.assertEqual(error.args, (PRIVATE,))
            self.assertEqual(value.diagnostic_phase, 'completion-snapshot')

    def test_last_guard_observation_tracks_each_real_snapshot_without_changing_retries(self):
        peer = FramedSocket()
        peer.operand_states = [({'details': PRIVATE}, None), (None, {'details': PRIVATE})]
        peer.phase_states = ['copy', 'bootloader']
        value, clock = fixture(peer), [0]
        calls = []
        phases = []
        def sleep(seconds):
            self.assertEqual(seconds, .2)
            calls.append(value.completion_guard_diagnostic)
            phases.append(value.completion_phase_diagnostic)
            clock[0] = .2 if len(calls) == 1 else 2401
        with patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(G.time, 'sleep', side_effect=sleep), self.assertRaises(RuntimeError):
            value.finish_install()
        self.assertEqual(calls, ['failed-true-attention-false', 'failed-false-attention-true'])
        self.assertEqual(value.completion_guard_diagnostic, calls[-1])
        self.assertEqual(phases, ['copy', 'bootloader'])
        self.assertEqual(value.completion_phase_diagnostic, phases[-1])
        self.assertEqual(sum(request['method'] == 'Hello' for request in peer.requests), 2)

    def test_optional_observer_cannot_replace_real_guard_or_its_original_retry_reason(self):
        class HostileObserverError(RuntimeError):
            def __str__(self): raise AssertionError('observer exception was formatted')
        for helper in ('completion_guard_diagnostic', 'completion_phase_diagnostic'):
            for error in (RuntimeError(PRIVATE), TypeError(PRIVATE), HostileObserverError(PRIVATE)):
                value = fixture(FramedSocket(failed={'details': PRIVATE}))
                value.completion_guard_diagnostic = 'failed-false-attention-true'
                value.completion_phase_diagnostic = 'copy'
                clock = [0]
                def sleep(seconds):
                    self.assertEqual(seconds, .2)
                    clock[0] = 2401
                with self.subTest(helper=helper, observer=type(error).__name__), \
                        patch.object(G, helper, side_effect=error), \
                        patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]), \
                        patch.object(G.time, 'sleep', side_effect=sleep), self.assertRaises(RuntimeError) as caught:
                    value.finish_install()
                self.assertEqual(caught.exception.args, ('same real installation did not finish within its separate bound: real active installation failed or requires attention',))
                self.assertEqual(getattr(value, helper), 'unknown')
                other = 'completion_phase_diagnostic' if helper == 'completion_guard_diagnostic' else 'completion_guard_diagnostic'
                self.assertEqual(getattr(value, other), 'finalize' if other == 'completion_phase_diagnostic' else 'failed-true-attention-false')
                self.assertEqual(value.diagnostic_phase, 'completion-engine-guard')
                masked = G.masked_active_error(caught.exception, value.diagnostic_phase, value.completion_guard_diagnostic, value.completion_phase_diagnostic)
                self.assertIn('installer-reported-active-primary-' + ('engine-guard-' if helper == 'completion_guard_diagnostic' else 'engine-phase-') + 'unknown',
                              R.primary_reported_codes({'errors': [masked]}, True))
                self.assertNotIn('private', masked)

        # Isolate the real nested guard once to prove the handler bare-raises
        # its exact exception, rather than creating a diagnostic replacement.
        value = fixture(FramedSocket(failed={'details': PRIVATE}))
        observed = []
        original_require = G.require
        def observe_require(ok, reason):
            try:
                return original_require(ok, reason)
            except RuntimeError as error:
                if reason == 'real active installation failed or requires attention':
                    observed.append(error)
                raise
        value.wait = lambda action, seconds, reason: action()
        with patch.object(G, 'require', side_effect=observe_require), \
                patch.object(G, 'completion_guard_diagnostic', side_effect=TypeError(PRIVATE)), \
                self.assertRaises(RuntimeError) as caught:
            value.finish_install()
        self.assertEqual(len(observed), 1)
        self.assertIs(caught.exception, observed[0])
        self.assertEqual(caught.exception.args, ('real active installation failed or requires attention',))

    def test_failure_observer_preserves_cancellation_and_is_never_called_on_success(self):
        for helper in ('completion_guard_diagnostic', 'completion_phase_diagnostic'):
            for error in (KeyboardInterrupt(PRIVATE), SystemExit(PRIVATE)):
                value = fixture(FramedSocket(failed={'details': PRIVATE}))
                with self.subTest(helper=helper, cancellation=type(error).__name__), \
                        patch.object(G.time, 'monotonic', return_value=0), \
                        patch.object(G.time, 'sleep', side_effect=AssertionError('cancellation was retried')), \
                        patch.object(G, helper, side_effect=error), \
                        self.assertRaises(type(error)) as caught:
                    value.finish_install()
                self.assertIs(caught.exception, error)
                self.assertEqual(getattr(value, helper), 'unknown')
        value = fixture(FramedSocket())
        with patch.object(G.time, 'monotonic', return_value=0), \
                patch.object(G.time, 'monotonic_ns', return_value=101), \
                patch.object(G, 'completion_guard_diagnostic', side_effect=AssertionError('success invoked failure observer')), \
                patch.object(G, 'completion_phase_diagnostic', side_effect=AssertionError('success invoked phase observer')):
            result = value.finish_install()
        self.assertEqual(result['gui']['percent'], 100)
        self.assertFalse(hasattr(value, 'completion_guard_diagnostic'))
        self.assertFalse(hasattr(value, 'completion_phase_diagnostic'))

    def test_last_reported_phase_is_finite_same_snapshot_and_scoped_failure_only(self):
        expected = {'unknown', 'disk', 'copy', 'configure', 'bootloader', 'apps', 'finalize'}
        self.assertEqual(G.COMPLETION_PHASE_DIAGNOSTICS, expected)
        for phase in sorted(expected - {'unknown'}):
            peer = FramedSocket(failed={'details': PRIVATE}); peer.phase = phase
            value, clock = fixture(peer), [0]
            def sleep(seconds): clock[0] = 2401
            with self.subTest(phase=phase), patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(G.time, 'sleep', side_effect=sleep), self.assertRaises(RuntimeError) as caught:
                value.finish_install()
            self.assertEqual(value.completion_phase_diagnostic, phase)
            masked = G.masked_active_error(caught.exception, value.diagnostic_phase, value.completion_guard_diagnostic, value.completion_phase_diagnostic)
            self.assertIn('installer-reported-active-primary-engine-phase-' + phase, R.primary_reported_codes({'errors': [masked]}, True))
            self.assertEqual(sum(request['method'] == 'Hello' for request in peer.requests), 1)
        class Hostile:
            def __str__(self): raise AssertionError('private phase formatted')
            def __hash__(self): raise AssertionError('private phase hashed')
        class HostileDict(dict):
            def get(self, key): raise AssertionError('private phase getter')
        for phase in (None, False, 1, [], {}, Hostile(), 'foreign', PRIVATE, PRIVATE * 20000):
            snapshot = {'install': {'options': {'progress': {'phase': phase}}}}
            tracemalloc.start()
            self.assertEqual(G.completion_phase_diagnostic(snapshot), 'unknown')
            _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            self.assertLess(peak, 16384)
        for snapshot in (HostileDict(), {'install': HostileDict()}, {'install': {'options': {'progress': HostileDict()}}},
                         {'install': {'options': {'progress': {'phase': 'copy', **{str(i): 0 for i in range(16)}}}}}):
            self.assertEqual(G.completion_phase_diagnostic(snapshot), 'unknown')
        masked = G.masked_active_error(RuntimeError(PRIVATE), 'completion-engine-guard', 'unknown', 'copy')
        for altered in (masked.replace('engine-phase=copy', 'engine-phase=foreign'),
                        masked.replace('phase=completion-engine-guard', 'phase=completion-snapshot'),
                        masked.replace('; engine-guard=unknown', ''),
                        masked.replace('engine-phase=copy', 'engine-phase=copy; engine-phase=apps'),
                        masked.replace('engine-phase=copy', 'engine-phase=copy-' + PRIVATE)):
            self.assertEqual(R.primary_reported_codes({'errors': [altered]}, True), ('installer-reported-active-primary-unknown',))
        original = G.masked_active_error(RuntimeError(PRIVATE), 'completion-snapshot')
        self.assertEqual(G.masked_active_error(RuntimeError(PRIVATE), 'completion-snapshot', Hostile(), Hostile()), original)

    def test_observer_ignores_hostile_shapes_and_parser_rejects_foreign_diagnostic_scope(self):
        class Hostile:
            def __bool__(self): raise AssertionError('private bool callback')
            def __str__(self): raise AssertionError('private string callback')
            def __eq__(self, other): raise AssertionError('private equality callback')
        class HostileDict(dict):
            def get(self, key): raise AssertionError('private getter callback')
        class HostileKey:
            def __hash__(self): return 0
            def __eq__(self, other): raise AssertionError('private key equality callback')
        hostile = Hostile()
        for malformed in (hostile, HostileDict(), {}, {'install': hostile},
                          {'install': {'options': HostileDict()}},
                          {'install': {'options': {'failed': hostile, 'attention': False}}},
                          {'install': {'options': {'failed': 1, 'attention': False}}},
                          {'install': {'options': {'failed': False}}},
                          {HostileKey(): PRIVATE},
                          {str(index): False for index in range(17)}):
            self.assertEqual(G.completion_guard_diagnostic(malformed), 'unknown')
        oversized = {'install': {'options': {'failed': PRIVATE * 20000, 'attention': False}}}
        tracemalloc.start()
        self.assertEqual(G.completion_guard_diagnostic(oversized), 'unknown')
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        self.assertLess(peak, 16384)  # No copy or formatting of the private operand.
        masked = G.masked_active_error(RuntimeError(PRIVATE), 'completion-engine-guard', hostile)
        self.assertIn('; engine-guard=unknown]', masked)
        old = G.masked_active_error(RuntimeError(PRIVATE), 'prepare-start')
        self.assertEqual(G.masked_active_error(RuntimeError(PRIVATE), 'prepare-start', hostile), old)
        for altered in (old[:-1] + '; engine-guard=failed-true-attention-false]',
                        masked.replace('engine-guard=unknown', 'engine-guard=private'),
                        masked.replace('; engine-guard=unknown', '; failed=' + PRIVATE)):
            self.assertEqual(R.primary_reported_codes({'errors': [altered]}, True),
                             ('installer-reported-active-primary-unknown',))
        self.assertNotIn('private', masked)

    def test_actual_failed_run_preserves_inventory_rejection_and_failure_only_stdout(self):
        peer = FramedSocket(failed={'details': PRIVATE})
        value, clock = fixture(peer), [0]
        value.context = dict(schema='arctic-installer-active-context-v1', source_sha='a'*40,
            execution_sha='b'*40, binding_id='c'*32, iso_sha256='d'*64, iso_bytes=1900000000,
            checker_sha256='1'*64, native_sha256='2'*64, runtime_sha256='3'*64, capture_sha256='4'*64,
            active_checker_sha256='5'*64, installed_checker_sha256='6'*64,
            disk_serial='arctic-a-'+'1'*11, disk_bytes=64*1024**3, disk_node='target0', write_bps=8*1024**2)
        value.boot_id, value.uid, value.session, value.original_vt = 'synthetic', 1000, 'synthetic', 1
        value.results, value.samples, value.capture_count, value.password, value.gui_fd = [], [], 4, PRIVATE, None
        def security_failure(): raise RuntimeError(PRIVATE)
        value.native = SimpleNamespace(SecurityInterval=lambda: SimpleNamespace(finish=security_failure))
        value.prepare = lambda: value.baseline
        value.vt_cycle = lambda cycle: dict(kind='vt', cycle=cycle, status='passed')
        value.output_cycle = lambda cycle: dict(kind='output', cycle=cycle, status='passed')
        value.cleanup = lambda: dict(original_vt_restored=True, engine_retained=True, errors=[])
        def sleep(seconds): self.assertEqual(seconds, .2); clock[0] = 2401
        stdout = io.StringIO()
        with tempfile.TemporaryDirectory() as temporary:
            value.root = Path(temporary)
            with patch.object(G.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(G.time, 'sleep', side_effect=sleep), contextlib.redirect_stdout(stdout):
                report = value.run()
                R.diagnose_report(report, True)
            self.assertEqual(report['status'], 'failed')
            self.assertIs(report['release_acceptance'], False)
            self.assertNotIn('completion', report); self.assertNotIn('security', report)
            self.assertIsNone(value.password)
            self.assertTrue(peer.closed)
            self.assertEqual(json.loads((value.root / 'installer-report.json').read_bytes()), report)
            with self.assertRaises(RuntimeError) as caught:
                AC.validate_report(report, value.context, {}, lambda _: b'')
            self.assertEqual(R.diagnostic_code('report-validation', caught.exception, AC),
                             'installer-report-validation-assertion-active-054')
            self.assertEqual(caught.exception.args, ('active report contains missing or private fields',))
        self.assertIn('installer-reported-active-primary-engine-guard-failed-true-attention-false', stdout.getvalue())
        self.assertIn('installer-reported-active-primary-engine-phase-finalize', stdout.getvalue())
        self.assertNotIn('private', json.dumps(report) + stdout.getvalue())
        with patch('builtins.print', side_effect=BrokenPipeError(PRIVATE)):
            R.diagnose_report(report, True)


if __name__ == '__main__':
    unittest.main()
