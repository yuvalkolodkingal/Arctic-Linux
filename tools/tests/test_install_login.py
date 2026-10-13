"""Fail-closed controls for the installed SDDM-to-desktop transition."""
import ast
import importlib.util
from pathlib import Path
import tempfile
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
    def __init__(self, kind, changed=True, cleared=True, fraction=0):
        self.kind = kind
        self.changed = changed
        self.cleared = cleared
        self.fraction = fraction

    def classify(self, path):
        return self.kind(path)

    def login_password_changed(self, before, after):
        return self.changed(before, after) if callable(self.changed) else self.changed

    def login_password_cleared(self, before, after):
        return self.cleared(before, after) if callable(self.cleared) else self.cleared

    def login_password_target(self, _path):
        return (600, 468, 1280, 720)

    def changed_fraction(self, before, after):
        return self.fraction


class FakeOS:
    def __init__(self, fail=None):
        self.removed = []
        self.fail = fail

    def remove(self, path):
        self.removed.append(path)
        if path == self.fail:
            raise OSError('synthetic private cleanup failure')


class FakeVM:
    def __init__(self):
        self.keys_sent = []
        self.key_calls = []
        self.typed = 0
        self.type_calls = []
        self.click_calls = []
        self.pointer_calls = []
        self.events = []
        self.shots = []
        self.calls = []
        self.proc = types.SimpleNamespace(pid=4242)

    def alive(self):
        return True

    def shot(self, name, **selector):
        path = f'/out/{name}.png'
        self.shots.append(path)
        self.calls.append((name, selector))
        return path

    def keys(self, *keys, **selector):
        self.keys_sent.append(keys)
        self.key_calls.append((keys, selector))
        self.events.append(('keys', keys, selector))

    def type_text(self, value, gap=0, **selector):
        self.typed += 1
        self.type_calls.append((value, gap, selector))
        self.events.append(('type', value, selector))

    def click(self, x, y, width, height, **selector):
        self.click_calls.append((x, y, width, height, selector))
        self.events.append(('click', (x, y, width, height), selector))

    def pointer(self, x, y, width, height, **selector):
        self.pointer_calls.append((x, y, width, height, selector))
        self.events.append(('pointer', (x, y, width, height), selector))


def display_proof(heads=(0, 1), console_ids=(7, 8)):
    rows = [dict(console_id=console, head=head, device_address='pci/0000/01.0',
                 width_mm=340, height_mm=190, xoff=head * 1280, yoff=0,
                 width=1280, height=720)
            for head, console in zip(heads, console_ids)]
    return types.SimpleNamespace(proof=dict(
        schema='arctic-qemu-taskbar-display-v1',
        status='uiinfo_applied_pending_guest_two_output_evidence',
        qemu_pid=4242, qemu_uid=0, gpu_id='arctic_taskbar_gpu',
        display_backend='dbus', guest_monitor_verification_required=True,
        heads=rows))


def load_functions(kind, changed=True, cleared=True, fraction=0, fake_os=None):
    fake_time = FakeTime()
    logs = []
    module = ast.Module(body=[FUNCTIONS[name] for name in (
        'discard_private_shot', 'discard_private_shots', 'discard_private_shots_preserving',
        'installed_login_heads',
        'installed_login', 'installed_session_settled')],
                        type_ignores=[])
    fake_os = fake_os or FakeOS()
    namespace = dict(os=fake_os, time=fake_time,
                     vmtest=FakeVmtest(kind, changed, cleared, fraction),
                     password='fixture-password', log=logs.append, out='/out')
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
        self.assertEqual(vm.type_calls[0][0], 'probe')
        self.assertFalse(any(value == 'fixture-password' for value, _, _ in vm.type_calls))
        self.assertEqual(fixture.logs, ['installed password field did not accept physical input'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_perpetual_login_is_bounded_and_fails(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm))
        self.assertEqual(vm.keys_sent.count(('ret',)), 3)
        self.assertEqual(vm.typed, 6)
        # Three exact 150s transition windows plus probe, clear, secret and cleanup.
        self.assertEqual(fixture.time.now, 462)
        self.assertEqual(fixture.logs[-1], 'installed login did not transition (attempt 3)')

    def test_perpetual_login_discards_every_password_bearing_frame(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm))
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))
        self.assertTrue(all(Path(name).name.startswith(('boot-42-password-', 'boot-43-probe'))
                            for name in fixture.os.removed))
        self.assertEqual(vm.keys_sent[-1], ('ctrl-a', 'backspace'))

    def test_non_login_transition_succeeds(self):
        fixture = load_functions(lambda path: 'other' if Path(path).name.startswith('boot-43-probe-') else 'login')
        vm = FakeVM()
        self.assertTrue(fixture.installed_login(vm))
        self.assertEqual(vm.keys_sent.count(('ret',)), 1)
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_settle_rejects_login_immediately(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        self.assertFalse(fixture.installed_session_settled(vm))
        self.assertEqual(len(vm.shots), 1)
        self.assertEqual(fixture.logs, ['installed session returned to the login screen'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_settle_accepts_stable_non_login_only_after_90_seconds(self):
        fixture = load_functions(lambda _path: 'other', fraction=0)
        vm = FakeVM()
        self.assertTrue(fixture.installed_session_settled(vm))
        self.assertGreater(fixture.time.now, 90)
        self.assertEqual(fixture.logs, [f'session settled after {fixture.time.now:.0f}s'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_unstable_session_timeout_is_bounded_and_fails(self):
        fixture = load_functions(lambda _path: 'other', fraction=1)
        vm = FakeVM()
        self.assertFalse(fixture.installed_session_settled(vm))
        self.assertEqual(fixture.time.now, 900)
        self.assertEqual(fixture.logs, ['installed session did not settle within 900s'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_settle_classifier_error_discards_current_frame(self):
        fixture = load_functions(lambda _path: (_ for _ in ()).throw(RuntimeError('synthetic classify')))
        vm = FakeVM()
        with self.assertRaisesRegex(RuntimeError, 'synthetic classify'):
            fixture.installed_session_settled(vm)
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_settle_comparator_error_discards_both_frames(self):
        fixture = load_functions(lambda _path: 'other')
        fixture.vmtest.changed_fraction = lambda _before, _after: (
            _ for _ in ()).throw(RuntimeError('synthetic compare'))
        vm = FakeVM()
        with self.assertRaisesRegex(RuntimeError, 'synthetic compare'):
            fixture.installed_session_settled(vm)
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_stage_boot_guards_collection_with_both_controls(self):
        source = ast.get_source_segment(DRIVER, FUNCTIONS['stage_boot'])
        login = source.index('if not installed_login(vm, display):')
        settle = source.index('if not installed_session_settled(vm, display):')
        collection = source.index('open_terminal(vm')
        self.assertLess(login, settle)
        self.assertLess(settle, collection)
        self.assertIn('if not installed_login(vm, display):\n            log("installed login failed; private greeter capture suppressed")\n            return 1', source)
        self.assertNotIn('boot-44-login-failed', source)
        self.assertIn('if not installed_session_settled(vm, display):\n            log("installed session did not settle; private session capture suppressed")\n            return 1', source)
        self.assertNotIn('boot-50-settle-failed', source)

    def test_dual_head_uses_exact_selectors_and_one_changed_head_suffices(self):
        changed = lambda before, after: before.endswith('head1.png') and after.endswith('head1.png')
        def kind(path):
            if Path(path).name.startswith('boot-43-probe-'):
                return 'other'
            return 'login' if 'head1' in path else 'dark'
        fixture = load_functions(kind,
                                 changed=changed)
        vm = FakeVM()
        self.assertTrue(fixture.installed_login(vm, display_proof()))
        private_calls = [call for call in vm.calls if call[0].startswith('boot-42-password-')]
        self.assertEqual([selector for _, selector in private_calls],
                         [{'device': 'arctic_taskbar_gpu', 'head': head}
                          for head in (0, 1) for _phase in (0,)] +
                         [{'device': 'arctic_taskbar_gpu', 'head': head}
                          for _phase in range(4) for head in (0, 1)])
        self.assertEqual([call[0] for call in vm.type_calls], ['probe', 'fixture-password'])
        self.assertEqual([call[2] for call in vm.type_calls], [
            {'device': 'arctic_taskbar_gpu', 'head': 1},
            {'device': 'arctic_taskbar_gpu', 'head': 1},
        ])
        self.assertFalse(any(selector.get('head') == 0
                             for _, selector in vm.key_calls))
        self.assertEqual([call[-1] for call in vm.click_calls], [
            {'device': 'arctic_taskbar_gpu', 'head': 1},
        ])
        self.assertTrue(all(call[-1].get('head') == 1 for call in vm.pointer_calls))
        self.assertEqual(vm.key_calls[-1], (
            ('ret',), {'device': 'arctic_taskbar_gpu', 'head': 1}))
        self.assertTrue(all(selector for _, selector in private_calls))
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_dual_head_accepts_both_changed_surfaces(self):
        fixture = load_functions(lambda path: 'other' if Path(path).name.startswith('boot-43-probe-') else 'login')
        vm = FakeVM()
        self.assertTrue(fixture.installed_login(vm, display_proof()))
        self.assertEqual(vm.keys_sent.count(('ret',)), 1)

    def test_dual_head_no_roi_fails_without_submit(self):
        fixture = load_functions(lambda _path: 'login', changed=False)
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm, display_proof()))
        self.assertNotIn(('ret',), vm.keys_sent)
        self.assertEqual([call[2] for call in vm.type_calls], [
            {'device': 'arctic_taskbar_gpu', 'head': 0},
            {'device': 'arctic_taskbar_gpu', 'head': 1},
        ])
        self.assertTrue(all(call[0] == 'probe' for call in vm.type_calls))
        self.assertFalse(any(call[0] == 'fixture-password' for call in vm.type_calls))
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_non_login_heads_receive_no_password_or_keys(self):
        fixture = load_functions(lambda path: 'dark' if 'head0' in path else 'other')
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm, display_proof()))
        self.assertEqual(vm.type_calls, [])
        self.assertEqual(vm.key_calls, [])
        self.assertEqual(vm.click_calls, [])
        self.assertEqual(vm.pointer_calls, [])
        self.assertEqual(fixture.logs, ['installed password field did not accept physical input'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_clear_proof_failure_never_sends_secret(self):
        def kind(path):
            return 'dark' if 'head0' in path else 'login'
        fixture = load_functions(kind, changed=True, cleared=False)
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm, display_proof()))
        self.assertEqual([value for value, _, _ in vm.type_calls], ['probe'])
        self.assertFalse(any(value == 'fixture-password' for value, _, _ in vm.type_calls))
        self.assertNotIn(('ret',), vm.keys_sent)
        self.assertFalse(any(call[-1].get('head') == 0 for call in vm.click_calls))
        self.assertFalse(any(selector.get('head') == 0 for _, selector in vm.key_calls))
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_missing_target_fails_before_pointer_key_probe_or_secret(self):
        def kind(path):
            return 'dark' if 'head0' in path else 'login'
        fixture = load_functions(kind)
        fixture.vmtest.login_password_target = lambda _path: None
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm, display_proof()))
        self.assertEqual(vm.click_calls, [])
        self.assertEqual(vm.pointer_calls, [])
        self.assertEqual(vm.key_calls, [])
        self.assertEqual(vm.type_calls, [])
        self.assertEqual(fixture.logs, ['installed login controls are not visible'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_selected_click_failure_cleans_all_frames_and_sends_no_text(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        def click(*_args, **_selector):
            raise RuntimeError('synthetic selected click failure')
        vm.click = click
        with self.assertRaisesRegex(RuntimeError, 'synthetic selected click failure'):
            fixture.installed_login(vm, display_proof())
        self.assertEqual(vm.key_calls, [])
        self.assertEqual(vm.type_calls, [])
        self.assertEqual(vm.pointer_calls, [])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_selected_pointer_failure_cleans_probe_frames_and_sends_no_secret(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        def pointer(*_args, **_selector):
            raise RuntimeError('synthetic selected pointer failure')
        vm.pointer = pointer
        with self.assertRaisesRegex(RuntimeError, 'synthetic selected pointer failure'):
            fixture.installed_login(vm, display_proof())
        self.assertEqual([value for value, _, _ in vm.type_calls], ['probe'])
        self.assertFalse(any(value == 'fixture-password' for value, _, _ in vm.type_calls))
        self.assertNotIn(('ret',), vm.keys_sent)
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_probe_clear_secret_submit_order_stays_on_one_login_head(self):
        def kind(path):
            if Path(path).name.startswith('boot-43-probe-'):
                return 'other'
            return 'dark' if 'head0' in path else 'login'
        fixture = load_functions(kind)
        vm = FakeVM()
        self.assertTrue(fixture.installed_login(vm, display_proof()))
        target = {'device': 'arctic_taskbar_gpu', 'head': 1}
        relevant = [(kind, value, selector) for kind, value, selector in vm.events
                    if kind in ('click', 'keys', 'type', 'pointer')]
        self.assertEqual(relevant[:7], [
            ('click', (600, 468, 1280, 720), target),
            ('keys', ('ctrl-a', 'backspace'), target),
            ('type', 'probe', target),
            ('keys', ('ctrl-a', 'backspace'), target),
            ('pointer', (0, 0, 1280, 720), target),
            ('type', 'fixture-password', target),
            ('keys', ('ret',), target),
        ])

    def test_selected_input_failure_cleans_all_captured_heads(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        original = vm.keys
        def keys(*names, **selector):
            if selector.get('head') == 0:
                raise KeyboardInterrupt('synthetic selected input interruption')
            return original(*names, **selector)
        vm.keys = keys
        with self.assertRaisesRegex(KeyboardInterrupt, 'synthetic selected input interruption'):
            fixture.installed_login(vm, display_proof())
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))
        self.assertEqual(sorted(fixture.os.removed), [
            '/out/boot-42-password-before-1-target0-head0.png',
            '/out/boot-42-password-before-1-target0-head1.png'])

    def test_dual_head_rejects_missing_wrong_and_duplicate_heads_before_input(self):
        cases = (
            display_proof(heads=(0,)),
            display_proof(heads=(0, 2)),
            display_proof(heads=(0, 1), console_ids=(7, 7)),
        )
        for display in cases:
            with self.subTest(heads=display.proof['heads']):
                fixture = load_functions(lambda _path: 'login')
                vm = FakeVM()
                with self.assertRaisesRegex(RuntimeError, 'installed login display heads differ|installed login display proof differs'):
                    fixture.installed_login(vm, display)
                self.assertEqual(vm.typed, 0)
                self.assertEqual(vm.calls, [])

    def test_dual_head_rejects_stale_vm_identity_before_default_capture(self):
        display = display_proof()
        display.proof['qemu_pid'] += 1
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        with self.assertRaisesRegex(RuntimeError, 'installed login display proof differs'):
            fixture.installed_login(vm, display)
        self.assertEqual(vm.calls, [])

    def test_dual_head_missing_or_invalid_selected_capture_fails_closed(self):
        for mode in ('missing', 'invalid'):
            with self.subTest(mode=mode):
                fixture = load_functions(lambda path: 'none' if mode == 'invalid' and 'head1' in path else 'login')
                vm = FakeVM()
                original = vm.shot
                if mode == 'missing':
                    def shot(name, **selector):
                        value = original(name, **selector)
                        return None if selector.get('head') == 1 else value
                    vm.shot = shot
                self.assertFalse(fixture.installed_login(vm, display_proof()))
                self.assertEqual(vm.typed, 0)
                self.assertNotIn(('ret',), vm.keys_sent)
                self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_dual_head_qmp_selection_error_cleans_prior_frames(self):
        fixture = load_functions(lambda _path: 'login')
        vm = FakeVM()
        original = vm.shot
        def shot(name, **selector):
            if selector.get('head') == 1:
                raise RuntimeError('synthetic selected-head failure')
            return original(name, **selector)
        vm.shot = shot
        with self.assertRaisesRegex(RuntimeError, 'synthetic selected-head failure'):
            fixture.installed_login(vm, display_proof())
        self.assertEqual(fixture.os.removed, [
            '/out/boot-42-password-before-1-target0-head0.png',
            '/out/boot-42-password-before-1-target0-head1.png'])

    def test_private_cleanup_attempts_all_paths_and_reports_fixed_error(self):
        failure = '/out/boot-42-password-before-1-target0-head0.png'
        fake_os = FakeOS(fail=failure)
        fixture = load_functions(lambda _path: 'login', fake_os=fake_os)
        vm = FakeVM()
        with self.assertRaisesRegex(RuntimeError, '^private screenshot cleanup failed$') as caught:
            fixture.installed_login(vm, display_proof())
        self.assertNotIn('/out/', str(caught.exception))
        self.assertEqual(sorted(fake_os.removed), sorted(vm.shots))

    def test_wrong_auth_on_head1_cannot_be_hidden_by_dark_head0(self):
        def kind(path):
            name = Path(path).name
            if 'head0' in name:
                return 'dark'
            return 'login'
        fixture = load_functions(kind, changed=lambda old, new: 'head1' in old and 'head1' in new)
        vm = FakeVM()
        self.assertFalse(fixture.installed_login(vm, display_proof()))
        self.assertEqual(vm.keys_sent.count(('ret',)), 3)
        self.assertEqual(fixture.time.now, 462)
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_transition_selected_head_failure_cleans_all_probe_paths(self):
        def kind(path):
            return 'other' if Path(path).name.startswith('boot-43-probe-') else 'login'
        fixture = load_functions(kind)
        vm = FakeVM()
        original = vm.shot
        def shot(name, **selector):
            if name.startswith('boot-43-probe-') and selector.get('head') == 1:
                raise RuntimeError('synthetic transition head failure')
            return original(name, **selector)
        vm.shot = shot
        with self.assertRaisesRegex(RuntimeError, 'synthetic transition head failure'):
            fixture.installed_login(vm, display_proof())
        expected = '/out/boot-43-probe-1-head1.png'
        self.assertIn(expected, fixture.os.removed)
        self.assertTrue(all(path in fixture.os.removed for path in vm.shots))

    def test_transition_cleanup_failure_still_attempts_both_heads(self):
        failure = '/out/boot-43-probe-1-head0.png'
        fake_os = FakeOS(fail=failure)
        fixture = load_functions(
            lambda path: 'other' if Path(path).name.startswith('boot-43-probe-') else 'login',
            fake_os=fake_os)
        vm = FakeVM()
        with self.assertRaisesRegex(RuntimeError, '^private screenshot cleanup failed$'):
            fixture.installed_login(vm, display_proof())
        self.assertIn('/out/boot-43-probe-1-head1.png', fake_os.removed)
        self.assertTrue(all(path in fake_os.removed for path in vm.shots))

    def test_dual_head_session_rejects_login_return_on_head1(self):
        fixture = load_functions(lambda path: 'login' if 'head1' in path else 'other')
        vm = FakeVM()
        self.assertFalse(fixture.installed_session_settled(vm, display_proof()))
        self.assertEqual(fixture.logs, ['installed session returned to the login screen'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_dual_head_session_rejects_missing_selected_capture(self):
        fixture = load_functions(lambda _path: 'other')
        vm = FakeVM()
        original = vm.shot
        def shot(name, **selector):
            value = original(name, **selector)
            return None if selector.get('head') == 1 else value
        vm.shot = shot
        self.assertFalse(fixture.installed_session_settled(vm, display_proof()))
        self.assertEqual(fixture.logs, ['installed session head capture is invalid'])
        self.assertEqual(sorted(fixture.os.removed), sorted(vm.shots))

    def test_session_cancellation_during_sleep_cleans_retained_heads(self):
        failure = '/out/boot-50-session-01-head0.png'
        fake_os = FakeOS(fail=failure)
        fixture = load_functions(lambda _path: 'other', fake_os=fake_os)
        original_sleep = fixture.time.sleep
        calls = 0
        def sleep(seconds):
            nonlocal calls
            if seconds == 20:
                calls += 1
                if calls == 2:
                    raise KeyboardInterrupt('synthetic cancellation')
            original_sleep(seconds)
        fixture.time.sleep = sleep
        vm = FakeVM()
        with self.assertRaisesRegex(KeyboardInterrupt, 'synthetic cancellation'):
            fixture.installed_session_settled(vm, display_proof())
        self.assertEqual(sorted(set(fake_os.removed)), sorted(vm.shots))
        self.assertIn('/out/boot-50-session-01-head1.png', fake_os.removed)

    def test_session_loop_condition_error_survives_cleanup_failure(self):
        failure = '/out/boot-50-session-01-head0.png'
        fake_os = FakeOS(fail=failure)
        fixture = load_functions(lambda _path: 'other', fake_os=fake_os)
        vm = FakeVM()
        calls = 0
        def alive():
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('synthetic alive failure')
            return True
        vm.alive = alive
        with self.assertRaisesRegex(RuntimeError, '^synthetic alive failure$'):
            fixture.installed_session_settled(vm, display_proof())
        self.assertEqual(sorted(set(fake_os.removed)), sorted(vm.shots))
        self.assertIn('/out/boot-50-session-01-head1.png', fake_os.removed)


class VmShotSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('vmtest_qmp_shot', ROOT / 'tools/lib/vmtest.py')
        cls.vmtest = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.vmtest)

    def vm(self, answer=None):
        instance = self.vmtest.VM.__new__(self.vmtest.VM)
        instance.alive = lambda: True
        instance.calls = []
        instance.cmd = lambda name, **args: instance.calls.append((name, args)) or (answer or {'return': {}})
        return instance

    def test_selected_screendump_forwards_exact_device_and_head(self):
        vm = self.vm()
        path = vm.shot('selected', device='arctic_taskbar_gpu', head=1)
        self.assertEqual(path, self.vmtest.OUT + '/selected.png')
        self.assertEqual(vm.calls, [('screendump', {
            'filename': path, 'format': 'png', 'device': 'arctic_taskbar_gpu', 'head': 1})])

    def test_partial_or_invalid_selectors_fail_before_qmp(self):
        for device, head in ((None, 0), ('arctic_taskbar_gpu', None), ('bad/device', 0),
                             ('arctic_taskbar_gpu', -1), ('arctic_taskbar_gpu', True)):
            with self.subTest(device=device, head=head):
                vm = self.vm()
                with self.assertRaisesRegex(ValueError, 'invalid screendump head selector'):
                    vm.shot('invalid', device=device, head=head)
                self.assertEqual(vm.calls, [])

    def test_qmp_selected_head_error_has_no_default_fallback(self):
        with tempfile.TemporaryDirectory() as temp:
            old_out, self.vmtest.OUT = self.vmtest.OUT, temp
            try:
                vm = self.vm({'error': {'class': 'GenericError'}})
                self.assertIsNone(vm.shot('failed', device='arctic_taskbar_gpu', head=0))
                self.assertEqual(len(vm.calls), 1)
                self.assertEqual(vm.calls[0][1]['head'], 0)
            finally:
                self.vmtest.OUT = old_out

    def test_selected_input_forwards_exact_device_and_head(self):
        vm = self.vm()
        vm.press(['ctrl', 'a'], device='arctic_taskbar_gpu', head=1)
        self.assertEqual(len(vm.calls), 1)
        name, arguments = vm.calls[0]
        self.assertEqual(name, 'input-send-event')
        self.assertEqual(arguments['device'], 'arctic_taskbar_gpu')
        self.assertEqual(arguments['head'], 1)
        self.assertEqual([event['data']['down'] for event in arguments['events']],
                         [True, True, False, False])

    def test_keys_and_type_text_keep_the_exact_selected_head(self):
        vm = self.vm()
        vm.keys('backspace', gap=0, device='arctic_taskbar_gpu', head=0)
        vm.type_text('a', gap=0, device='arctic_taskbar_gpu', head=0)
        self.assertEqual(len(vm.calls), 2)
        self.assertTrue(all(name == 'input-send-event' for name, _ in vm.calls))
        self.assertTrue(all(arguments['device'] == 'arctic_taskbar_gpu'
                            and arguments['head'] == 0 for _, arguments in vm.calls))

    def test_selected_click_forwards_exact_head_and_bounded_absolute_pointer(self):
        vm = self.vm()
        vm.click(600, 468, 1280, 720, device='arctic_taskbar_gpu', head=1)
        self.assertEqual(len(vm.calls), 1)
        name, arguments = vm.calls[0]
        self.assertEqual(name, 'input-send-event')
        self.assertEqual((arguments['device'], arguments['head']),
                         ('arctic_taskbar_gpu', 1))
        self.assertEqual(arguments['events'][:2], [
            {'type': 'abs', 'data': {'axis': 'x', 'value': 600 * 0x7fff // 1279}},
            {'type': 'abs', 'data': {'axis': 'y', 'value': 468 * 0x7fff // 719}},
        ])
        self.assertEqual(arguments['events'][2:], [
            {'type': 'btn', 'data': {'down': True, 'button': 'left'}},
            {'type': 'btn', 'data': {'down': False, 'button': 'left'}},
        ])

    def test_selected_pointer_park_forwards_exact_head(self):
        vm = self.vm()
        vm.pointer(0, 0, 1280, 720, device='arctic_taskbar_gpu', head=0)
        self.assertEqual(vm.calls, [('input-send-event', {
            'events': [
                {'type': 'abs', 'data': {'axis': 'x', 'value': 0}},
                {'type': 'abs', 'data': {'axis': 'y', 'value': 0}},
            ],
            'device': 'arctic_taskbar_gpu', 'head': 0,
        })])

    def test_invalid_pointer_coordinates_and_selectors_fail_before_qmp(self):
        for values in ((-1, 0, 1280, 720), (1280, 0, 1280, 720),
                       (0, 720, 1280, 720), (0, 0, 1, 720),
                       (True, 0, 1280, 720)):
            with self.subTest(values=values):
                vm = self.vm()
                with self.assertRaisesRegex(ValueError, 'invalid input pointer coordinates'):
                    vm.click(*values, device='arctic_taskbar_gpu', head=0)
                self.assertEqual(vm.calls, [])
        vm = self.vm()
        with self.assertRaisesRegex(ValueError, 'invalid input head selector'):
            vm.pointer(0, 0, 1280, 720, device=None, head=0)
        self.assertEqual(vm.calls, [])

    def test_selected_pointer_error_never_falls_back(self):
        for method in ('pointer', 'click'):
            with self.subTest(method=method):
                vm = self.vm({'error': {'class': 'GenericError'}})
                with self.assertRaisesRegex(self.vmtest.QMPError,
                                             '^selected pointer event failed$'):
                    getattr(vm, method)(600, 468, 1280, 720,
                                        device='arctic_taskbar_gpu', head=1)
                self.assertEqual([name for name, _ in vm.calls], ['input-send-event'])
                self.assertEqual(vm.calls[0][1]['device'], 'arctic_taskbar_gpu')
                self.assertEqual(vm.calls[0][1]['head'], 1)

    def test_partial_or_invalid_input_selectors_fail_before_qmp(self):
        for device, head in ((None, 0), ('arctic_taskbar_gpu', None), ('bad/device', 0),
                             ('arctic_taskbar_gpu', -1), ('arctic_taskbar_gpu', True)):
            with self.subTest(device=device, head=head):
                vm = self.vm()
                with self.assertRaisesRegex(ValueError, 'invalid input head selector'):
                    vm.press(['a'], device=device, head=head)
                self.assertEqual(vm.calls, [])

    def test_selected_input_error_never_falls_back_to_unselected_send_key(self):
        vm = self.vm({'error': {'class': 'GenericError'}})
        with self.assertRaisesRegex(self.vmtest.QMPError, '^selected input event failed$'):
            vm.press(['a'], device='arctic_taskbar_gpu', head=1)
        self.assertEqual([name for name, _ in vm.calls], ['input-send-event'])
        self.assertEqual(vm.calls[0][1]['device'], 'arctic_taskbar_gpu')
        self.assertEqual(vm.calls[0][1]['head'], 1)

    def test_unselected_input_error_retains_legacy_send_key_fallback(self):
        vm = self.vm({'error': {'class': 'GenericError'}})
        vm.press(['a'])
        self.assertEqual([name for name, _ in vm.calls], ['input-send-event', 'send-key'])


if __name__ == '__main__':
    unittest.main()
