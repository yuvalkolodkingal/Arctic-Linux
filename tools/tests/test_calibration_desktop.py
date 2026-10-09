"""Research-only VT restoration must bind the real desktop before any timing."""
import ast
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'performance/compose-calibration-probe.py'
PREFIX = ['runuser', '-u', 'ci', '--', 'env', '-i', 'XDG_SESSION_ID=2', 'WAYLAND_DISPLAY=wayland-0']


def entry_source():
    tree = ast.parse(SOURCE.read_text())
    return next(ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign) and any(isinstance(n, ast.Name) and n.id == 'entry' for n in node.targets))


class Clock:
    def __init__(self): self.now = 0
    def monotonic(self): self.now += 1; return self.now
    def sleep(self, seconds): self.now += seconds


class CalibrationDesktopTests(unittest.TestCase):
    def fixture(self, properties=None, replies=None, uid=1000, outputs=None):
        props = dict(Type='wayland', User='1000', VTNr='1', Active='yes')
        props.update(properties or {})
        inventory = replies or [dict(monitors=[dict(name='Virtual-1', width=1280, height=720)])]
        physical = outputs if outputs is not None else [dict(name='Virtual-1', enabled=True, modes=[dict(current=True, width=1280, height=720)])]
        calls = []
        def run(argv, timeout):
            calls.append((argv, timeout))
            if argv[:2] == ['loginctl', 'show-session']:
                self.assertEqual(argv[2], '2')
                return props[argv[4]]
            if argv[0] == 'chvt': return ''
            if argv == PREFIX + ['wlr-randr', '--json']: return json.dumps(physical)
            self.assertEqual(argv, PREFIX + ['mmsg', 'get', 'all-monitors'])
            return json.dumps(inventory.pop(0) if len(inventory) > 1 else inventory[0])
        node = next(n for n in ast.parse(entry_source()).body if isinstance(n, ast.FunctionDef) and n.name == 'restore_calibration_desktop')
        namespace = dict(measurement={'run': run}, json=json, time=Clock())
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), 'exec'), namespace)
        return namespace['restore_calibration_desktop'], calls, patch('pwd.getpwnam', return_value=SimpleNamespace(pw_uid=uid))

    def test_actual_session_vt_is_restored_then_geometry_is_retained(self):
        fn, calls, user = self.fixture()
        with user: result = fn(PREFIX)
        self.assertEqual((result['session'], result['desktop_uid'], result['vt']), ('2', 1000, 1))
        self.assertEqual(result['monitors'], [dict(name='Virtual-1', width=1280, height=720)])
        self.assertEqual(result['enabled_outputs'], [dict(name='Virtual-1', width=1280, height=720)])
        self.assertLess(next(i for i, (a, _) in enumerate(calls) if a[0] == 'chvt'),
                        next(i for i, (a, _) in enumerate(calls) if a[-1] == 'all-monitors'))
        self.assertTrue(all(timeout <= 10 for _, timeout in calls))

    def test_invalid_owner_session_type_and_vt_cannot_switch(self):
        for properties, uid in [(dict(User='0'), 1000), (dict(Type='tty'), 1000),
                                (dict(VTNr='0'), 1000), (dict(VTNr='64'), 1000),
                                (dict(VTNr='1\n2'), 1000), ({}, 0)]:
            with self.subTest(properties=properties, uid=uid):
                fn, calls, user = self.fixture(properties, uid=uid)
                with user, self.assertRaises(RuntimeError): fn(PREFIX)
                self.assertFalse(any(a[0] == 'chvt' for a, _ in calls))

    def test_missing_or_duplicate_session_cannot_switch(self):
        for prefix in [PREFIX[:-2], PREFIX + ['XDG_SESSION_ID=3'], PREFIX[:-2] + ['XDG_SESSION_ID=../../1'], ['env']]:
            with self.subTest(prefix=prefix):
                fn, calls, user = self.fixture()
                with user, self.assertRaises(RuntimeError): fn(prefix)
                self.assertEqual(calls, [])

    def test_empty_output_inventory_waits_for_actual_monitor(self):
        fn, calls, user = self.fixture(replies=[dict(monitors=[]), dict(monitors=[dict(name='Virtual-1', width=1280, height=720)])])
        with user: result = fn(PREFIX)
        self.assertTrue(result['active'])
        self.assertEqual(sum(a[-1] == 'all-monitors' for a, _ in calls), 2)

    def test_inactive_or_invalid_geometry_remains_unready(self):
        cases = [(dict(Active='no'), dict(monitors=[dict(name='Virtual-1', width=1280, height=720)])),
                 ({}, dict(monitors=[])), ({}, dict(monitors=[dict(name='Virtual-1', width=True, height=720)])),
                 ({}, dict(monitors=[dict(name='Virtual-1', width=1280, height=0)])),
                 ({}, dict(monitors=[dict(name='Virtual-1', width=1280, height=720)] * 2))]
        for props, reply in cases:
            with self.subTest(props=props, reply=reply):
                fn, _, user = self.fixture(props, [reply])
                with user, self.assertRaisesRegex(RuntimeError, 'did not restore visible monitors'): fn(PREFIX)

    def test_cached_monitor_does_not_substitute_for_enabled_physical_output(self):
        for physical in [[], [dict(name='Virtual-1', enabled=False, modes=[])],
                         [dict(name='Virtual-1', enabled=1, modes=[dict(current=True, width=1280, height=720)])]]:
            with self.subTest(physical=physical):
                fn, _, user = self.fixture(outputs=physical)
                with user, self.assertRaisesRegex(RuntimeError, 'did not restore visible monitors'): fn(PREFIX)

    def test_physical_mode_identity_and_inventory_are_not_guessed(self):
        for physical in [[dict(name='Foreign-1', enabled=True, modes=[dict(current=True, width=1280, height=720)])],
                         [dict(name='Virtual-1', enabled=True, modes=[])],
                         [dict(name='Virtual-1', enabled=True, modes=[dict(current=True, width=True, height=720)])],
                         [dict(name='Virtual-1', enabled=True, modes=[dict(current=True, width=1280, height=720)] * 2)],
                         [dict(name='Virtual-1', enabled=True, modes=[])] * 2]:
            with self.subTest(physical=physical):
                fn, _, user = self.fixture(outputs=physical)
                with user, self.assertRaises(RuntimeError): fn(PREFIX)

    def test_restoration_precedes_instrumentation_and_limits_are_unchanged(self):
        source = entry_source()
        self.assertLess(source.index("state['desktop_readiness']=restore_calibration_desktop(prefix)"),
                        source.index('with causal.LowerBoundProbe(prefix)'))
        self.assertIn('for index in range(4):', source)
        self.assertIn('limit=min(.005,measured*.025)', source)
        self.assertIn("original_producer_status='failed_measurement_precision'", source)
        self.assertIn("release_acceptance=False", source)


if __name__ == '__main__': unittest.main()
