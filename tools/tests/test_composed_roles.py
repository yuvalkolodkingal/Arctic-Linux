"""Composed acceptance must use authenticated installed defaults."""
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).parents[2]
spec = importlib.util.spec_from_file_location('composed_guest', ROOT / 'tools/performance/guest.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


class ComposedRoleControls(unittest.TestCase):
    def resolve(self, image='candidate', mutate=None):
        expected = G.EXPECTED_ROLES[image]
        state = dict(uid=1000, sources=[], configured={}, programs={})
        inventory = {'nevra': []}
        for role, ident in expected.items():
            app = G.ROLE_APPS[ident]
            state['configured'][role] = app['configured'][0]
            state['programs'][app['program']] = '/usr/bin/' + app['program']
            if 'rpm' in app:
                inventory['nevra'].append(app['rpm'] + '-0:1-1.x86_64')
        browser = G.ROLE_APPS[expected['browser']]['desktop']
        if mutate:
            mutate(state, inventory)

        def run(argv):
            if '-c' in argv:
                return json.dumps(state)
            if 'xdg-settings' in argv:
                return browser
            if '-qf' in argv:
                return Path(argv[-1]).name + '-0:1-1.x86_64'
            if 'flatpak' in argv:
                return 'a' * 64
            raise AssertionError(argv)

        with patch.object(G, 'run', side_effect=run), patch.object(G.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=1000)):
            return G.functional_roles(['runuser', '-u', 'ci', '--', 'env'], inventory)

    def test_actual_lightweight_and_legacy_role_identities(self):
        for image in ('candidate', 'baseline'):
            with self.subTest(image=image):
                result = self.resolve(image)
                self.assertEqual({role: app['id'] for role, app in result['roles'].items()}, G.EXPECTED_ROLES[image])
                self.assertFalse(result['first_use_measurement'])

    def test_wrong_uid_mixed_configuration_missing_binary_and_owner_refused(self):
        mutations = [lambda s, i: s.update(uid=0),
                     lambda s, i: s['configured'].update(terminal='kitty'),
                     lambda s, i: s['configured'].update(browser='chromium'),
                     lambda s, i: s['programs'].update(epiphany=None),
                     lambda s, i: s['programs'].update(epiphany='/usr/bin/other'),
                     lambda s, i: i.update(nevra=[])]
        for mutate in mutations:
            with self.subTest(mutate=mutate), self.assertRaises(RuntimeError):
                self.resolve(mutate=mutate)

    def test_composed_measurement_uses_roles_without_pristine_timing_claim(self):
        declared = self.resolve()
        prefix = ['runuser', '-u', 'ci', '--', 'env']

        @contextmanager
        def workload(user):
            self.assertEqual(user, prefix)
            yield {'url': 'http://127.0.0.1:1234/', 'files': '/tmp/synthetic'}

        def run(argv):
            self.assertNotIn('kitty', argv)
            if 'systemd-detect-virt' in argv:
                return 'qemu'
            if 'arctic-keep-awake' in argv:
                return '{"on":false}'
            return 'synthetic'

        with patch.object(G, 'Path', side_effect=lambda value: SimpleNamespace(parent=Path('/run/t'))
                          if value == G.__file__ else Path(value)), \
             patch.object(G.os, 'geteuid', return_value=0), patch.object(G, 'run', side_effect=run), \
             patch.object(G, 'desktop', return_value=prefix), patch.object(G, 'rpm_inventory', return_value={}), \
             patch.object(G, 'functional_roles', return_value=declared) as resolve, \
             patch.object(G, 'role_workload', side_effect=workload), patch.object(G, 'measure') as measure, \
             patch.object(G, 'declare_roles') as pristine, patch.object(G, 'emit'):
            G.main(functional=True)
            resolve.assert_called_once_with(prefix, {})
            pristine.assert_not_called()
            self.assertIs(measure.call_args.args[1], declared)
            self.assertFalse(measure.call_args.kwargs['preconditioned'])
