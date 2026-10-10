"""Trusted target-operation observations; synthetic guard controls, no VM."""
import contextlib
import copy
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import runner as R
import test_primary_diagnostics as Primary
G, A, S = Primary.G, Primary.A, Primary.S
PRIVATE = Primary.PRIVATE


class HostileOSError(OSError):
    @property
    def errno(self):
        raise AssertionError('custom errno must not be read')

    @property
    def args(self):
        raise AssertionError('custom args must not be read')

    def __str__(self):
        raise AssertionError('private message must not be formatted')


class TargetModel:
    """Only intercepted operations used by the actual pristine target guard."""
    def __init__(self, owner, value, fail=None, error=None, override=None):
        self.owner, self.value = owner, value
        self.fail, self.error = fail, error
        self.override = override or {}
        self.trace, self.scans = [], 0

    def observe(self, operation):
        self.trace.append(operation)
        self.owner.assertEqual(self.value.diagnostic_phase, operation)
        if self.fail == operation:
            raise self.error

    def path(self, path):
        model = self
        class Node:
            def __init__(self, path):
                self.path = str(path)

            def __truediv__(self, suffix):
                return Node(self.path + '/' + suffix)

            @property
            def name(self):
                return self.path.rsplit('/', 1)[-1]

            @property
            def parent(self):
                return Node(self.path.rsplit('/', 1)[0])

            def __eq__(self, other):
                return self.path == getattr(other, 'path', None)

            def iterdir(self):
                model.scans += 1
                model.observe('target-enumerate' if model.scans == 1 else 'target-pristine-partitions')
                nodes = model.override.get('nodes', ['vda'])
                for node in nodes:
                    yield Node('/sys/class/block/' + node)
                if model.override.get('late_iterator_error') and model.scans == 1:
                    model.observe('target-enumerate')
                    raise model.override['late_iterator_error']

            def exists(self):
                model.observe('target-partition' if model.scans == 1 else 'target-pristine-partitions')
                return self.path.endswith('/vda1/partition')

            def read_text(self):
                if self.path.endswith('/device/serial'):
                    raise FileNotFoundError('virtio serial belongs to the block node')
                if self.path.endswith('/serial'):
                    model.observe('target-serial')
                    if '/sr0/' in self.path or '/vdb/' in self.path:
                        if model.override.get('foreign_serial_error') is not None:
                            raise model.override['foreign_serial_error']
                        raise FileNotFoundError('synthetic unrelated serial')
                    return model.override.get('serial', 'ARCTIC-OWNED-TARGET')
                if self.path.endswith('/size'):
                    model.observe('target-size')
                    return model.override.get('size', '134217728')
                if self.path.endswith('/dev'):
                    model.observe('target-major-minor')
                    return model.override.get('major_minor', '254:0')
                raise AssertionError('unexpected synthetic read')

            def resolve(self, strict=False):
                if self.path.endswith('/device/driver'):
                    model.observe('target-driver')
                    if '/sr0/' in self.path:
                        return Node('/sys/bus/scsi/drivers/sr')
                    return Node('/sys/bus/virtio/drivers/' + model.override.get('driver', 'virtio_blk'))
                model.observe('target-pristine-partitions')
                if self.name == 'vda1':
                    return Node('/sys/devices/owned/block/vda/vda1')
                return Node('/sys/devices/owned/block/vda')

            def stat(self):
                model.observe('target-node-stat')
                return SimpleNamespace(st_rdev=os.makedev(254, 0),
                    st_mode=model.override.get('mode', stat.S_IFBLK | 0o600))
        return Node(path)

    def command(self, argv):
        if argv == ['lsblk', '--json', '--bytes', '--nodeps', '-o', 'NAME,TYPE,SIZE']:
            self.observe('target-lsblk-disks')
            rows = self.override.get('disks', [dict(name='vda', type='disk', size=64 * 1024**3)])
        else:
            self.owner.assertEqual(argv, ['lsblk', '--json', '-o', 'NAME,MOUNTPOINTS', '/dev/vda'])
            self.observe('target-lsblk-mounts')
            rows = self.override.get('mounts', [dict(name='vda', mountpoints=[None])])
        return 0, json.dumps(dict(blockdevices=rows)), ''


class TargetControls(unittest.TestCase):
    def instance(self, root):
        value = Primary.PrimaryControls().instance(root)
        value.context = dict(disk_serial='ARCTIC-OWNED-TARGET', disk_bytes=64 * 1024**3)
        value.diagnostic_phase = 'prepare-target'
        return value

    def test_each_real_target_operation_remains_fatal_and_reports_only_fixed_phase_errno(self):
        for operation in G.TARGET_DIAGNOSTIC_PHASES:
            with self.subTest(operation=operation), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                error = OSError(22, PRIVATE, '/private/target-path')
                self.assertIs(type(error), OSError)
                model = TargetModel(self, value, operation, error)
                value.command = model.command
                value.prepare = lambda: value.target_disk(pristine=True)
                with patch.object(A, 'Path', model.path):
                    report = value.run()
                self.assertIn(operation, model.trace)
                self.assertEqual(report['status'], 'failed')
                self.assertIs(report['release_acceptance'], False)
                self.assertEqual(report['cases'], [])
                self.assertNotIn('baseline', report)
                self.assertIsNone(value.password)
                self.assertNotIn('private', json.dumps(report))
                self.assertIn('[phase=' + operation + '; errno=einval; reason=unknown]', report['errors'][0])
                private_report = (value.root / 'installer-report.json').read_bytes()
                stdout = io.StringIO()
                with contextlib.redirect_stdout(stdout): R.diagnose_report(report, True)
                self.assertEqual((value.root / 'installer-report.json').read_bytes(), private_report)
                self.assertIn('installer-reported-active-primary-phase-' + operation, stdout.getvalue())
                self.assertIn('installer-reported-active-primary-errno-einval', stdout.getvalue())
                self.assertNotIn('private', stdout.getvalue())
                raw = stdout.getvalue().encode()
                self.assertIs(S.external_text(raw), raw)

    def test_success_retains_exact_target_result_and_restores_callers_phase(self):
        for pristine in (False, True):
            with self.subTest(pristine=pristine), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                model = TargetModel(self, value)
                value.command = model.command
                with patch.object(A, 'Path', model.path):
                    result = value.target_disk(pristine=pristine)
                self.assertEqual(result, dict(path='/dev/vda', sysfs='/sys/class/block/vda',
                    serial='ARCTIC-OWNED-TARGET', disk_bytes=64 * 1024**3, major_minor='254:0'))
                self.assertEqual(value.diagnostic_phase, 'prepare-target')
                expected = ['target-enumerate', 'target-partition', 'target-driver', 'target-serial', 'target-driver',
                    'target-size', 'target-node-stat', 'target-major-minor', 'target-lsblk-disks']
                if pristine:
                    expected += ['target-pristine-partitions', 'target-pristine-partitions', 'target-lsblk-mounts']
                self.assertEqual(model.trace, expected)

    def test_missing_unrelated_serial_is_still_only_file_not_found_catch(self):
        for error in (None, OSError(22, PRIVATE), HostileOSError(PRIVATE)):
            with self.subTest(kind=type(error).__name__), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                model = TargetModel(self, value, override=dict(nodes=['vdb', 'vda'], foreign_serial_error=error))
                value.command = model.command
                with patch.object(A, 'Path', model.path):
                    if error is None:
                        self.assertEqual(value.target_disk(pristine=True)['path'], '/dev/vda')
                    else:
                        with self.assertRaises(type(error)) as caught:
                            value.target_disk(pristine=True)
                        self.assertIs(caught.exception, error)
                        self.assertEqual(value.diagnostic_phase, 'target-serial')

    def test_original_guard_failures_and_short_circuit_remain_closed(self):
        cases = [({'serial': 'other'}, 'owned target serial/path is absent or ambiguous'),
            ({'nodes': ['vda', 'vda']}, 'owned target serial/path is absent or ambiguous'),
            ({'driver': 'unsafe'}, 'owned target serial/path is absent or ambiguous'),
            ({'size': '1'}, 'owned target driver/size differs'),
            ({'major_minor': '8:0'}, 'owned target device identity differs'),
            ({'mode': stat.S_IFREG | 0o600}, 'owned target device identity differs'),
            ({'disks': [dict(name='vda', type='disk'), dict(name='sda', type='disk')]}, 'unexpected writable guest disk'),
            ({'nodes': ['vda', 'vda1']}, 'owned target already has partitions'),
            ({'mounts': [dict(name='vda', children=[{}])]}, 'owned target is already in use'),
            ({'mounts': [dict(name='vda', mountpoints=['/mounted'])]}, 'owned target is already in use')]
        for override, message in cases:
            with self.subTest(override=override), tempfile.TemporaryDirectory() as temp:
                value = self.instance(Path(temp))
                model = TargetModel(self, value, override=override)
                value.command = model.command
                with patch.object(A, 'Path', model.path):
                    with self.assertRaisesRegex(RuntimeError, '^' + message + '$'):
                        value.target_disk(pristine=True)
                if override.get('driver') == 'unsafe':
                    self.assertNotIn('target-size', model.trace)
                    self.assertNotIn('target-node-stat', model.trace)

    def test_late_iterator_error_retains_enumeration_phase(self):
        with tempfile.TemporaryDirectory() as temp:
            value = self.instance(Path(temp))
            error = OSError(5, PRIVATE)
            model = TargetModel(self, value, override=dict(late_iterator_error=error))
            value.command = model.command
            with patch.object(A, 'Path', model.path):
                with self.assertRaises(OSError) as caught:
                    value.target_disk(pristine=True)
            self.assertIs(caught.exception, error)
            self.assertEqual(value.diagnostic_phase, 'target-enumerate')

    def test_builtin_descriptor_errno_never_reads_hostile_classes_values_or_messages(self):
        class PrivateInt(int):
            def __hash__(self):
                raise AssertionError('custom errno must not be hashed')
        class PrivateMeta(type):
            def __hash__(self):
                raise AssertionError('custom exception class must not be hashed')
        PrivateClass = PrivateMeta('private-errno-class', (HostileOSError,), {})
        for error in (HostileOSError(PRIVATE), PrivateClass(PRIVATE), PermissionError(13, PRIVATE),
                      FileNotFoundError(2, PRIVATE), RuntimeError(PRIVATE)):
            self.assertEqual(G.primary_diagnostic_errno(error), 'unknown')
            masked = G.masked_active_error(error, 'target-serial')
            self.assertNotIn('; errno=', masked)
            self.assertNotIn('private', masked)
        for number, code in list(G.TARGET_DIAGNOSTIC_ERRNOS.items()) + [(999999, 'other'),
                (None, 'unknown'), (True, 'unknown'), (PRIVATE, 'unknown'), (PrivateInt(22), 'unknown')]:
            with self.subTest(expected=code):
                error = OSError(PRIVATE)
                error.errno = number
                self.assertIs(type(error), OSError)
                self.assertEqual(G.primary_diagnostic_errno(error), code)
                masked = G.masked_active_error(error, 'target-serial')
                self.assertNotIn('private', masked)
                self.assertIn('installer-reported-active-primary-errno-' + code,
                    R.primary_reported_codes({'errors': [masked]}, True))

    def test_closed_host_projection_rejects_forged_errno_and_preserves_old_masks(self):
        valid = G.masked_active_error(OSError(22, PRIVATE), 'target-serial')
        report = dict(errors=[valid], status='failed')
        before = copy.deepcopy(report)
        self.assertIn('installer-reported-active-primary-errno-einval', R.primary_reported_codes(report, True))
        self.assertEqual(report, before)
        for altered in (valid.replace('errno=einval', 'errno=' + PRIVATE),
                        valid.replace('errno=einval', 'errno=22'), valid + '\n', valid + PRIVATE,
                        valid.replace('target-serial', 'prepare-account-fill'),
                        valid.replace('OSError:', 'RuntimeError:')):
            self.assertEqual(R.primary_reported_codes({'errors': [altered]}, True),
                ('installer-reported-active-primary-unknown',))
        old = 'OSError: active installation or restoration failed [phase=prepare-target; reason=unknown]'
        self.assertEqual(R.primary_reported_codes({'errors': [old]}, True), (
            'installer-reported-active-primary-exception-os-error',
            'installer-reported-active-primary-phase-prepare-target',
            'installer-reported-active-primary-reason-unknown'))


if __name__ == '__main__':
    unittest.main()
