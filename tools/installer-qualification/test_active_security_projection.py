"""Source controls for verified native security -> bounded active public telemetry."""
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


AG = load('active_security_projection_guest', HERE / 'active-guest.py')
G = load('active_security_projection_idle_guest', HERE / 'guest.py')
N = load('active_security_projection_native', HERE.parent / 'native-functional/native_smoke.py')
F = load('active_security_projection_consumer_fixture', HERE / 'test_active_contract.py')


class PoisonInterval:
    """Any inspection of the excluded operand is a failing control."""
    def __getattribute__(self, name):
        raise AssertionError('excluded audit interval was inspected')

    def __repr__(self):
        raise AssertionError('excluded audit interval was formatted')

    __str__ = __repr__
    __bool__ = __repr__
    __iter__ = __repr__

    def __getitem__(self, key):
        raise AssertionError('excluded audit interval was read')

    def __eq__(self, other):
        raise AssertionError('excluded audit interval was compared')


class Controls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report, cls.state, cls.files, cls.media, _ = F.fixture()

    def native_verified(self, enabled=1, lost=0):
        before = dict(selinux='Enforcing', audit=dict(enabled=enabled, lost=lost))
        content = b'type=SYSCALL synthetic source control\n'
        summary = N.scan_audit_interval(io.BytesIO(content), len(content))
        return N.verify_security(before, copy.deepcopy(before), 0, summary)

    def consume(self, security):
        report = dict(self.report, security=security)
        return F.A.validate_report(report, self.state['context'], self.files,
            lambda name: self.media['installer/' + name], report['baseline']['packaged_sources'])

    def test_actual_native_verified_output_fails_old_shape_then_projects_for_current_consumer(self):
        verified = self.native_verified()
        self.assertEqual(set(verified), {'selinux', 'audit', 'observed_new_avcs', 'audit_enabled', 'scope', 'audit_interval'})
        with self.assertRaisesRegex(RuntimeError, 'security projection contains private fields'):
            self.consume(verified)
        public = AG.project_security(verified)
        self.assertEqual(self.consume(public)['status'], 'passed_pending_manual_visual_review')
        self.assertFalse(self.consume(public)['release_acceptance'])
        self.assertNotIn('audit_interval', public)
        self.assertIsNot(public['audit'], verified['audit'])
        verified['audit']['lost'] = 99
        self.assertEqual(public['audit']['lost'], 0)

    def test_legacy_and_current_kernel_audit_modes_keep_existing_consumer_semantics(self):
        for enabled in (0, 1, 2):
            for legacy in (False, True):
                with self.subTest(enabled=enabled, legacy=legacy):
                    verified = self.native_verified(enabled, lost=7)
                    if legacy:
                        verified.pop('audit_interval')
                    public = AG.project_security(verified)
                    self.assertEqual(public['audit'], dict(enabled=enabled, lost=7))
                    self.assertIs(public['audit_enabled'], enabled in (1, 2))
                    self.assertEqual(self.consume(public)['status'], 'passed_pending_manual_visual_review')

    def test_excluded_interval_operand_is_never_read_compared_or_formatted(self):
        verified = self.native_verified()
        verified['audit_interval'] = PoisonInterval()
        public = AG.project_security(verified)
        self.assertNotIn('audit_interval', public)
        self.assertNotIn('audit_interval', json.dumps(public, sort_keys=True))
        self.assertEqual(self.consume(public)['status'], 'passed_pending_manual_visual_review')

    def test_unknown_private_fields_and_missing_known_fields_fail_closed(self):
        for legacy in (False, True):
            for location in ('outer', 'audit'):
                for key in ('password', 'raw_account', 'audit_record'):
                    verified = self.native_verified()
                    if legacy:
                        verified.pop('audit_interval')
                    else:
                        verified['audit_interval'] = PoisonInterval()
                    target = verified if location == 'outer' else verified['audit']
                    target[key] = PoisonInterval()
                    with self.subTest(legacy=legacy, location=location, key=key), self.assertRaisesRegex(
                            RuntimeError, '^active security telemetry projection differs$'):
                        AG.project_security(verified)
        for key in ('selinux', 'audit', 'observed_new_avcs', 'audit_enabled', 'scope'):
            verified = self.native_verified()
            verified.pop(key)
            with self.subTest(missing=key), self.assertRaises(RuntimeError):
                AG.project_security(verified)

    def test_changed_avc_enforcing_scope_and_type_aliases_are_rejected(self):
        class StringAlias(str):
            pass

        class IntegerAlias(int):
            pass

        class DictAlias(dict):
            pass

        mutations = [
            ('selinux', 'Permissive'), ('selinux', StringAlias('Enforcing')),
            ('observed_new_avcs', 1), ('observed_new_avcs', -1),
            ('observed_new_avcs', False), ('observed_new_avcs', 0.0),
            ('observed_new_avcs', IntegerAlias(0)), ('audit_enabled', 1),
            ('audit_enabled', False), ('scope', 'different telemetry scope'),
            ('scope', StringAlias(self.native_verified()['scope'])),
            ('audit', DictAlias(enabled=1, lost=0)),
        ]
        for key, value in mutations:
            verified = self.native_verified()
            verified[key] = value
            with self.subTest(key=key, value_type=type(value).__name__), self.assertRaises(RuntimeError):
                AG.project_security(verified)
        for key, values in (('enabled', (True, 1.0, IntegerAlias(1), -1, 3)),
                            ('lost', (False, 0.0, IntegerAlias(0), -1))):
            for value in values:
                verified = self.native_verified()
                verified['audit'][key] = value
                with self.subTest(audit_key=key, value_type=type(value).__name__), self.assertRaises(RuntimeError):
                    AG.project_security(verified)
        for verified in (DictAlias(self.native_verified()), None, []):
            with self.subTest(outer_type=type(verified).__name__), self.assertRaises(RuntimeError):
                AG.project_security(verified)
        verified = self.native_verified()
        verified[StringAlias('selinux')] = verified.pop('selinux')
        with self.assertRaises(RuntimeError):
            AG.project_security(verified)
        verified = self.native_verified()
        verified['audit'][StringAlias('lost')] = verified['audit'].pop('lost')
        with self.assertRaises(RuntimeError):
            AG.project_security(verified)

    def run_guest(self, journal_avcs):
        """Exercise the actual run/finally path; GUI work alone is synthetic."""
        with tempfile.TemporaryDirectory(prefix='arctic-native-smoke-installer-security-control-') as temporary:
            root = Path(temporary)
            interval = N.SecurityInterval.__new__(N.SecurityInterval)
            interval.before = dict(selinux='Enforcing', audit=dict(enabled=1, lost=0))
            interval.cursor = 'synthetic-source-cursor'
            interval.audit_file = root / 'absent-audit.log'
            interval.audit_offset = None
            installer = AG.installer_type(G)
            instance = installer.__new__(installer)
            for key in ('context', 'boot_id', 'desktop_uid', 'active_desktop_session', 'original_vt'):
                attribute = {'desktop_uid': 'uid', 'active_desktop_session': 'session'}.get(key, key)
                setattr(instance, attribute, self.report[key])
            instance.native = SimpleNamespace(SecurityInterval=lambda: interval)
            instance.root, instance.results, instance.samples = root, [], self.report['samples']
            instance.capture_count, instance.rpc, instance.gui_fd = 4, None, None
            with mock.patch.object(interval, 'state', return_value=copy.deepcopy(interval.before)), \
                    mock.patch.object(N, 'journal_avc_count', return_value=dict(records=1, avcs=journal_avcs)), \
                    mock.patch.object(N, 'verify_security', wraps=N.verify_security) as verify, \
                    mock.patch.object(AG, 'project_security', wraps=AG.project_security) as projection, \
                    mock.patch.object(instance, 'prepare', return_value=self.report['baseline']), \
                    mock.patch.object(instance, 'vt_cycle', return_value=self.report['cases'][0]), \
                    mock.patch.object(instance, 'output_cycle', return_value=self.report['cases'][1]), \
                    mock.patch.object(instance, 'finish_install', return_value=self.report['completion']), \
                    mock.patch.object(instance, 'cleanup', return_value=self.report['cleanup']):
                report = instance.run()
                verify.assert_called_once()
                if journal_avcs:
                    projection.assert_not_called()
                else:
                    projection.assert_called_once()
                    self.assertIn('audit_interval', projection.call_args.args[0])
                self.assertEqual(json.loads((root / 'installer-report.json').read_bytes()), report)
                return report

    def test_actual_active_run_projects_only_after_native_finish_verifies(self):
        report = self.run_guest(0)
        self.assertEqual(report['status'], 'passed')
        self.assertNotIn('audit_interval', report['security'])
        self.assertEqual(self.consume(report['security'])['status'], 'passed_pending_manual_visual_review')

    def test_actual_native_avc_failure_stays_failed_and_never_reaches_projection(self):
        report = self.run_guest(1)
        self.assertEqual(report['status'], 'failed')
        self.assertNotIn('security', report)
        self.assertTrue(report['errors'])


if __name__ == '__main__':
    unittest.main()
