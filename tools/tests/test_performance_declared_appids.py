"""Actual declaration/launch branches against strict causal source controls.

No GUI, VM or tracing is started. Readback files and kernel events are explicit
synthetic fixtures; their owner identity is this real owned Python process.
"""
import ast
import copy
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


L = load('declared_appids_legacy', ROOT/'tools/tests/test_performance_legacy_appids.py')
G, C, R = L.G, L.C, L.R
BASE_GUEST_SHA = 'f8e8e9d2cc7900607111f98d51c5071b09e2434aedb6eda9a000f3badd45c57c'


class DeclaredAppidControls(unittest.TestCase):
    def declared(self, image, functional=False):
        fixture = R.role_run(image, 1)
        state = copy.deepcopy(fixture['app_roles']['pristine_state'])
        state['sources'] = fixture['app_roles']['configuration_sources']

        def run(argv, **kwargs):
            if 'python3' in argv:
                return json.dumps(state)
            if 'xdg-settings' in argv:
                return fixture['app_roles']['default_browser_desktop']
            if 'flatpak' in argv:
                return 'a'*64
            if argv[:2] == ['rpm', '-qf']:
                program = Path(argv[-1]).name
                for app in fixture['app_roles']['roles'].values():
                    descriptor = G.ROLE_APPS[app['id']]
                    if program == descriptor.get('desktop'):
                        return app['package']['desktop_owner']
                    if program == G.ROLE_APPS[app['id']]['program']:
                        return app['package']['binary_owner']
            raise AssertionError('Unexpected public fixture command')

        prefix = ['runuser', '-u', 'ci', '--', 'env']
        with patch.object(G, 'run', side_effect=run), patch.object(G.pwd, 'getpwnam', return_value=types.SimpleNamespace(pw_uid=1000)):
            if functional:
                return G.functional_roles(prefix, fixture['rpm_inventory'])
            return G.declare_roles(prefix, fixture['app_roles']['boot_context'], fixture['rpm_inventory'])

    def launch(self, directory, prefix, command, pattern, **kwargs):
        """Run unchanged startup, then real bound with real owned readback files."""
        factory = L.LegacyAppidControls('runTest')
        appid = pattern[0]
        probe, arguments = factory.owned_probe(directory, appid)
        windows, started, lower, upper = arguments

        class Observer:
            identifier = G.CAUSAL_MAPPING_OBSERVER
            clock = 'CLOCK_MONOTONIC_RAW'
            roundtrips = []

            def __init__(self, *args, **options): self.queries = 0
            def __enter__(self): return self
            def __exit__(self, *unused): return False
            def now_ns(self): return started
            def query(self):
                self.queries += 1
                return {} if self.queries == 1 else {'1': windows[0]}
            def begin_observation(self, *args, **unused): pass
            def finish_observation(self, *args):
                return dict(windows=copy.deepcopy(windows), lower_ns=lower, upper_ns=upper)

        child = types.SimpleNamespace(poll=lambda:0)
        actual_open = open
        def output(path, *args, **options):
            return actual_open(directory/'owned-launch-output' if path == '/tmp/arctic-performance-apps.log' else path, *args, **options)

        with patch.object(G, 'NativeClientQuery', Observer), patch.object(G, 'clients', return_value={}), \
             patch.object(G.subprocess, 'Popen', return_value=child), patch.object(G.time, 'sleep'), \
             patch.object(G, 'emit'), patch.object(G, 'snapshot', return_value={}), \
             patch.object(G, 'CAUSAL_TRACER', probe), patch('builtins.open', side_effect=output):
            return REAL_STARTUP(prefix, command, pattern, **kwargs)

    def test_actual_declarations_preserve_aliases_and_json_wire_values(self):
        for image in ('baseline', 'candidate'):
            for functional in (False, True):
                with self.subTest(image=image, functional=functional):
                    declared = self.declared(image, functional)
                    before_wire = copy.deepcopy(declared)
                    for role, app in declared['roles'].items():
                        self.assertIs(type(app['appids']), tuple)
                        self.assertEqual(app['appids'], G.ROLE_APPS[app['id']]['appids'])
                        before_wire['roles'][role]['appids'] = list(app['appids'])
                    self.assertEqual(json.dumps(declared), json.dumps(before_wire))

    def test_actual_first_use_and_preconditioning_reach_unchanged_startup_and_causal_bound(self):
        for image in ('baseline', 'candidate'):
            for functional in (False, True):
                with self.subTest(image=image, functional=functional), tempfile.TemporaryDirectory() as temp:
                    declared = self.declared(image, functional)
                    workload = dict(files='/source-fixture-files', url='http://127.0.0.1/source-fixture')
                    calls = []
                    def launch(prefix, command, pattern, **kwargs):
                        calls.append((pattern, kwargs.get('hold_seconds', 5)))
                        return self.launch(Path(temp)/str(len(calls)), prefix, command, pattern, **kwargs)
                    with patch.object(G, 'startup', side_effect=launch), patch.object(G, 'emit'):
                        order = G.first_use_and_precondition([], declared, workload)
                    self.assertEqual([hold for _, hold in calls], [5]*3+[45]*3)
                    self.assertEqual([pattern for pattern, _ in calls], [declared['roles'][r]['appids'] for _ in range(2) for r in G.ROLE_ORDER])
                    self.assertEqual(order, [phase+':'+r for phase in ('cold','precondition') for r in G.ROLE_ORDER])

    def test_actual_declaration_to_measure_warm_branch_reaches_strict_causal_bound(self):
        factory = L.LegacyAppidControls('runTest')
        for image in ('baseline', 'candidate'):
            for functional in (False, True):
                with self.subTest(image=image, functional=functional):
                    declared = self.declared(image, functional)
                    calls, _, order = factory.measure_branch(declared=declared)
                    self.assertEqual([call[2] for call in calls], [declared['roles'][r]['appids'] for r in G.ROLE_ORDER for _ in range(3)])
                    self.assertEqual(order, ['warm:'+r for r in G.ROLE_ORDER])

    def test_original_whole_byte_declaration_reproduces_real_strict_guard_rejection(self):
        raw = (ROOT/'tools/performance/guest.py').read_bytes()
        current = b"appids=tuple(app['appids'])"
        self.assertEqual(raw.count(current), 2)
        old = raw.replace(current, b"appids=list(app['appids'])")
        self.assertEqual(hashlib.sha256(old).hexdigest(), BASE_GUEST_SHA)
        for name in ('declare_roles', 'functional_roles'):
            definition = next(n for n in ast.parse(old).body if isinstance(n, ast.FunctionDef) and n.name == name)
            original = getattr(G, name)
            try:
                exec(compile(ast.Module(body=[definition], type_ignores=[]), 'exact-original-role-declaration', 'exec'), G.__dict__)
                oldfunction = getattr(G, name)
            finally:
                setattr(G, name, original)
            with patch.object(G, name, oldfunction):
                declared = self.declared('candidate', name == 'functional_roles')
            with tempfile.TemporaryDirectory() as temp:
                app = declared['roles']['terminal']
                with self.assertRaisesRegex(RuntimeError, 'original exact application-ID predicate'):
                    self.launch(Path(temp), [], ['owned-fixture-command'], app['appids'], label='source-control')

    def test_empty_nonstring_and_invalid_tuple_predicates_remain_rejected(self):
        factory = L.LegacyAppidControls('runTest')
        for pattern in ([], ['foot'], (), ('',), (None,), (True,), ('bad/id',), ('foot\0',), ('Foot',), ('a'*32,), ('foot','foot'), ('foot',)*9):
            with self.subTest(kind=type(pattern).__name__), tempfile.TemporaryDirectory() as temp:
                probe, arguments = factory.owned_probe(temp, 'foot')
                with self.assertRaisesRegex(RuntimeError, 'original exact application-ID predicate'):
                    probe.bound(*arguments, pattern, timeout=0)


REAL_STARTUP = G.startup
if __name__ == '__main__': unittest.main()
