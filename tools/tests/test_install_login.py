"""Fail-closed controls for the installed SDDM-to-desktop transition."""
import ast
from pathlib import Path
import types
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (ROOT / 'tools/test-install.sh').read_text()
DRIVER = SCRIPT.split("read -r -d '' DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]
TREE = ast.parse(DRIVER)
FUNCTIONS = {node.name: node for node in TREE.body if isinstance(node, ast.FunctionDef)}


class FakeTime:
    def __init__(self):
        self.now = 0

    def time(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeVmtest:
    def __init__(self, kind, changed=True, fraction=0):
        self.kind = kind
        self.changed = changed
        self.fraction = fraction

    def classify(self, path):
        return self.kind(path)

    def login_password_changed(self, before, after):
        return self.changed

    def changed_fraction(self, before, after):
        return self.fraction


class FakeOS:
    def __init__(self):
        self.removed = []

    def remove(self, path):
        self.removed.append(path)


class FakeVM:
    def __init__(self):
        self.keys_sent = []
        self.typed = 0
        self.shots = []

    def alive(self):
        return True

    def shot(self, name):
        self.shots.append(name)
        return name

    def keys(self, *keys):
        self.keys_sent.append(keys)

    def type_text(self, value, gap=0):
        self.typed += 1


def load_functions(kind, changed=True, fraction=0):
    fake_time = FakeTime()
    logs = []
    module = ast.Module(body=[FUNCTIONS['discard_private_shot'], FUNCTIONS['installed_login'], FUNCTIONS['installed_session_settled']],
                        type_ignores=[])
    fake_os = FakeOS()
    namespace = dict(os=fake_os, time=fake_time, vmtest=FakeVmtest(kind, changed, fraction),
                     password='fixture-password', log=logs.append)
    exec(compile(ast.fix_missing_locations(module), '<install-driver-test>', 'exec'), namespace)
    namespace['logs'] = logs
    return types.SimpleNamespace(**namespace)


class InstalledLoginTests(unittest.TestCase):
    def test_missing_password_roi_change_fails_without_submit(self):
        fixture = load_functions(lambda _path: 'login', changed=False)
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm))
        self.assertNotIn(('ret',), vm.keys_sent)
        self.assertEqual(vm.typed, 1)
        self.assertEqual(fixture.logs, ['installed password field did not accept physical input'])

    def test_perpetual_login_is_bounded_and_fails(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm))
        self.assertEqual(vm.keys_sent.count(('ret',)), 3)
        self.assertEqual(vm.typed, 3)
        # Three 150s transition windows plus typed/cleanup seconds stay bounded.
        self.assertLessEqual(fixture.time.now, 456)
        self.assertEqual(fixture.logs[-1], 'installed login did not transition (attempt 3)')

    def test_perpetual_login_discards_every_password_bearing_frame(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm))
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))
        self.assertTrue(all(name.startswith(('boot-42-password-', 'boot-43-probe'))
                            for name in fixture.os.removed))
        self.assertEqual(vm.keys_sent[-1], ('ctrl-a', 'backspace'))

    def test_non_login_transition_succeeds(self):
        fixture = load_functions(lambda path: 'other' if path == 'boot-43-probe' else 'login')
        vm = FakeVM()
        self.assertTrue(fixture.installed_login(vm))
        self.assertEqual(vm.keys_sent.count(('ret',)), 1)

    def test_settle_rejects_login_immediately(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        self.assertFalse(fixture.installed_session_settled(vm))
        self.assertEqual(len(vm.shots), 1)
        self.assertEqual(fixture.logs, ['installed session returned to the login screen'])

    def test_settle_accepts_stable_non_login_only_after_90_seconds(self):
        fixture = load_functions(lambda _path: 'other', fraction=0)
        vm = FakeVM()
        self.assertTrue(fixture.installed_session_settled(vm))
        self.assertGreater(fixture.time.now, 90)
        self.assertEqual(fixture.logs, [f'session settled after {fixture.time.now:.0f}s'])

    def test_unstable_session_timeout_is_bounded_and_fails(self):
        fixture = load_functions(lambda _path: 'other', fraction=1)
        vm = FakeVM()
        self.assertFalse(fixture.installed_session_settled(vm))
        self.assertEqual(fixture.time.now, 900)
        self.assertEqual(fixture.logs, ['installed session did not settle within 900s'])

    def test_stage_boot_guards_collection_with_both_controls(self):
        source = ast.get_source_segment(DRIVER, FUNCTIONS['stage_boot'])
        login = source.index('if not installed_login(vm):')
        settle = source.index('if not installed_session_settled(vm):')
        collection = source.index('open_terminal(vm')
        self.assertLess(login, settle)
        self.assertLess(settle, collection)
        self.assertIn('if not installed_login(vm):\n            log("installed login failed; private greeter capture suppressed")\n            return 1', source)
        self.assertNotIn('boot-44-login-failed', source)
        self.assertIn('if not installed_session_settled(vm):\n            vm.shot("boot-50-settle-failed")\n            return 1', source)


if __name__ == '__main__':
    unittest.main()
