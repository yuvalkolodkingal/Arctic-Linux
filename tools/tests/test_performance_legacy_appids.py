"""Legacy launch predicates must satisfy the unchanged causal identity contract.

These are source controls, with real owned-process identity and readback-file
checks over synthetic kernel receipts. They launch no apps or compositor.
"""
import ast
import copy
from contextlib import ExitStack
import hashlib
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


G = load('legacy_appid_guest', ROOT / 'tools/performance/guest.py')
C = load('legacy_appid_causal', ROOT / 'tools/performance/causal.py')
R = load('legacy_appid_receipts', ROOT / 'tools/tests/test_performance_roles.py')
PARENT_GUEST_SHA = '5f3228d6f09a97e7640f522663bbfa32632f63387a3b59235caa3caab64bf92e'


class LegacyAppidControls(unittest.TestCase):
    def owned_probe(self, directory, appid):
        original = R.causal_bound(.09975, .1, appids=(appid,))
        proof = copy.deepcopy(original['causal_lower_bound'])
        probe = C.LowerBoundProbe([])
        probe.pid = os.getpid()
        probe.instance = Path(directory)
        probe.executable = (Path('/proc') / str(probe.pid) / 'exe').resolve(strict=True)
        proof.update(desktop_uid=os.getuid(), mango_start_ticks=int(
            (Path('/proc') / str(probe.pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]),
            kernel_event_readbacks=R.kernel_event_readbacks(probe.pid))
        probe.proof = proof
        probe.requested_events = set(proof['kernel_event_readbacks'])
        for name, record in proof['kernel_event_readbacks'].items():
            event = probe.instance / 'events' / probe.group / name
            event.mkdir(parents=True)
            for key in ('format', 'filter'):
                (event / key).write_text(record[key + '_text'])
        stats = probe.instance / 'per_cpu' / 'cpu0' / 'stats'
        stats.parent.mkdir(parents=True)
        stats.write_text('overrun: 0\ncommit overrun: 0\ndropped events: 0\n')
        ident = 'c' * 32
        probe.events = {ident: copy.deepcopy(proof['matched_identity_events'][0])}
        probe.lower_events = {ident: copy.deepcopy(proof['matched_events'][0])}
        probe.upper_events = {ident: copy.deepcopy(proof['matched_upper_events'][0])}
        for events in (probe.events, probe.lower_events, probe.upper_events):
            events[ident]['kernel_pid'] = probe.pid
        arguments = (proof['matched_ipc_clients'], original['launch_started_monotonic_ns'],
                     proof['ipc_lower_monotonic_ns'], proof['ipc_upper_monotonic_ns'])
        return probe, arguments

    def measure_branch(self, function=None, declared=None):
        calls, events, order = [], [], []
        with tempfile.TemporaryDirectory() as temporary, ExitStack() as stack:
            directory = Path(temporary)
            (directory / 'boot_id').write_text('00000000-0000-4000-8000-000000000000\n')
            (directory / 'uptime').write_text('1.0 1.0\n')

            class MetricPath:
                def __init__(self, value):
                    self.value = value

                def read_text(self):
                    names = {'/proc/sys/kernel/random/boot_id': 'boot_id', '/proc/uptime': 'uptime'}
                    return (directory / names[self.value]).read_text()

                def is_dir(self):
                    return False

            def launch(prefix, command, pattern, **kwargs):
                probe, arguments = self.owned_probe(directory / ('launch-' + str(len(calls))),
                                                     pattern[0] if isinstance(pattern, tuple) else pattern)
                lower, upper, receipt = probe.bound(*arguments, pattern, timeout=0)
                self.assertEqual(receipt['application_id_predicate'], list(pattern))
                self.assertEqual((lower, upper), (1_099_750_000, 1_100_000_000))
                self.assertEqual(receipt['loss_counts']['cpu0']['dropped events'], 0)
                calls.append((tuple(prefix), tuple(command), pattern, kwargs))
                return (upper - arguments[1]) / 1e9

            stack.enter_context(patch.object(G, 'Path', MetricPath))
            stack.enter_context(patch.object(G, 'run', return_value='source fixture'))
            stack.enter_context(patch.object(G.time, 'sleep'))
            stack.enter_context(patch.object(G, 'collect_idle', return_value=[]))
            stack.enter_context(patch.object(G, 'snapshot', return_value={}))
            stack.enter_context(patch.object(G, 'emit', side_effect=lambda key, value: events.append((key, value))))
            stack.enter_context(patch.object(G, 'startup', side_effect=launch))
            stack.enter_context(patch.object(G, 'CAUSAL_TRACER', object()))
            (function or G.measure)(['owned-fixture-prefix'], declared=declared,
                workload={'files': '/source-fixture-files', 'url': 'http://127.0.0.1/source-fixture'}, order=order)
        return calls, events, order

    def test_complete_legacy_branch_reaches_real_strict_causal_bound(self):
        calls, events, order = self.measure_branch()
        self.assertEqual(len(calls), 9)
        self.assertEqual([call[2] for call in calls], [('kitty',)] * 3 +
            [('org.gnome.nautilus',)] * 3 + [('zen',)] * 3)
        self.assertEqual([call[1] for call in calls], [('kitty',)] * 3 +
            [('nautilus', '--new-window')] * 3 +
            [('flatpak', 'run', 'app.zen_browser.zen', 'about:blank')] * 3)
        measured = [(name, value) for name, value in events if name.startswith('startup_')]
        self.assertEqual([name for name, _ in measured],
            ['startup_kitty_seconds', 'startup_org.gnome.nautilus_seconds', 'startup_zen_seconds'])
        self.assertTrue(all(value['first'] == .1 and value['warm'] == [.1, .1] for _, value in measured))
        self.assertEqual(order, [])
        self.assertEqual(events[-1], ('done', True))

    def test_both_role_bound_branches_keep_exact_declared_tuple_aliases_and_order(self):
        for image in ('baseline', 'candidate'):
            with self.subTest(image=image):
                declared = {'roles': {role: dict(G.ROLE_APPS[ident], id=ident)
                    for role, ident in G.EXPECTED_ROLES[image].items()}}
                calls, events, order = self.measure_branch(declared=declared)
                self.assertEqual(len(calls), 9)
                self.assertEqual([call[2] for call in calls], [declared['roles'][role]['appids']
                    for role in G.ROLE_ORDER for _ in range(3)])
                self.assertEqual(order, ['warm:' + role for role in G.ROLE_ORDER])
                self.assertTrue(all(call[3]['poll_seconds'] == G.ROLE_POLL_SECONDS for call in calls))
                self.assertEqual(events[-1], ('done', True))

    def test_exact_parent_whole_byte_rollback_reproduces_string_predicate_rejection(self):
        data = (ROOT / 'tools/performance/guest.py').read_bytes()
        declared_tuple = b"appids=tuple(app['appids'])"
        self.assertEqual(data.count(declared_tuple), 2)
        data = data.replace(declared_tuple, b"appids=list(app['appids'])")
        old = b'startup(prefix, command, pattern, observations=bounds)'
        new = b'startup(prefix, command, (pattern,), observations=bounds)'
        self.assertEqual(data.count(new), 1)
        previous = data.replace(new, old, 1)
        self.assertEqual(hashlib.sha256(previous).hexdigest(), PARENT_GUEST_SHA)
        definition = next(node for node in ast.parse(previous).body
                          if isinstance(node, ast.FunctionDef) and node.name == 'measure')
        namespace = G.__dict__
        saved = namespace['measure']
        try:
            exec(compile(ast.Module(body=[definition], type_ignores=[]), 'exact-parent-measure', 'exec'), namespace)
            original = namespace['measure']
        finally:
            namespace['measure'] = saved
        with self.assertRaisesRegex(RuntimeError, 'original exact application-ID predicate'):
            self.measure_branch(function=original)

    def test_invalid_predicates_fail_before_receipt_access_and_unrelated_client_is_rejected(self):
        class Poison(dict):
            def __contains__(self, key):
                raise AssertionError('invalid predicate must not access receipts')

        with tempfile.TemporaryDirectory() as temporary:
            probe, arguments = self.owned_probe(temporary, 'kitty')
            original = (probe.events, probe.lower_events, probe.upper_events)
            probe.events = probe.lower_events = probe.upper_events = Poison()
            for pattern in ('kitty', ['kitty'], (), ('kitty', 'kitty'), ('Kitty',), ('bad/id',),
                            ('a' * 32,), ('kitty\x00',), (1,), ('kitty',) * 9):
                with self.subTest(pattern=pattern), self.assertRaisesRegex(RuntimeError, 'original exact application-ID predicate'):
                    probe.bound(*arguments, pattern, timeout=0)
            probe.events, probe.lower_events, probe.upper_events = original
            for pattern in (('not-kitty',), ('kitty-unrelated',)):
                with self.subTest(pattern=pattern), self.assertRaisesRegex(RuntimeError, 'ordering, callsite or current launch'):
                    probe.bound(*arguments, pattern, timeout=0)
            # Exact identities must still agree across original getter and IPC,
            # independent of a title or an application-name substring.
            windows = copy.deepcopy(arguments[0])
            windows[0]['appid'] = 'unrelated-kitty'
            with self.assertRaisesRegex(RuntimeError, 'ordering, callsite or current launch'):
                probe.bound(windows, *arguments[1:], ('kitty',), timeout=0)


if __name__ == '__main__':
    unittest.main()
