"""Installed graphical-login VT discovery controls; no VM qualification."""
import importlib.util
from pathlib import Path
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('installed_graphical_driver', HERE / 'driver.py')
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


class InstalledGraphicalDiscoveryControls(unittest.TestCase):
    def exercise(self, classify, *, boot_menu=False, alive=lambda: True):
        clock = [0.0]
        calls = []
        vm = types.SimpleNamespace(
            alive=alive,
            shot=lambda label: calls.append(('shot', label)) or Path('/physical.png'),
            keys=lambda *keys: calls.append(('keys', keys)),
            cmd=lambda command, **arguments: calls.append(('cmd', command, arguments)),
        )
        vmtest = types.SimpleNamespace(
            looks_like_boot_menu=lambda _path: boot_menu and not any(c[0] == 'keys' for c in calls),
            classify=lambda _path: classify(calls),
        )
        with patch.object(D.time, 'monotonic', side_effect=lambda: clock[0]), \
                patch.object(D.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)):
            try:
                D.wait_installed_graphical_login(vm, vmtest)
            except BaseException as error:
                return error, calls, clock[0]
        return None, calls, clock[0]

    def test_already_visible_greeter_needs_no_vt_input(self):
        error, calls, elapsed = self.exercise(lambda _calls: 'login')
        self.assertIsNone(error)
        self.assertEqual(calls, [('shot', 'installed-login-probe')])
        self.assertEqual(elapsed, 0)

    def test_boot_menu_is_selected_before_the_same_greeter_classifier(self):
        error, calls, _ = self.exercise(
            lambda calls: 'login' if any(call[0] == 'keys' for call in calls) else 'grub',
            boot_menu=True)
        self.assertIsNone(error)
        self.assertEqual([call[0] for call in calls], ['shot', 'keys'])
        self.assertEqual(calls[1], ('keys', ('ret',)))

    def test_hidden_greeter_is_found_by_bounded_vt_cycle_after_boot_grace(self):
        def classify(calls):
            probes = [call for call in calls if call[0] == 'cmd']
            return 'login' if len(probes) == 3 else 'dark'

        error, calls, elapsed = self.exercise(classify)
        self.assertIsNone(error)
        probes = [call for call in calls if call[0] == 'cmd']
        self.assertEqual(elapsed, 74)
        self.assertEqual([[key['data'] for key in call[2]['keys']] for call in probes],
                         [['ctrl', 'alt', 'f1'], ['ctrl', 'alt', 'f2'], ['ctrl', 'alt', 'f3']])
        self.assertTrue(all(call[1] == 'send-key' and call[2]['hold-time'] == 100 for call in probes))

    def test_absent_greeter_preserves_the_total_deadline_and_fails_closed(self):
        error, calls, elapsed = self.exercise(lambda _calls: 'dark')
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('fresh installed login display did not appear',))
        self.assertEqual(elapsed, 900)
        probes = [call for call in calls if call[0] == 'cmd']
        self.assertGreater(len(probes), 5)
        self.assertEqual([[key['data'] for key in call[2]['keys']][-1] for call in probes[:6]],
                         ['f1', 'f2', 'f3', 'f4', 'f5', 'f1'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
