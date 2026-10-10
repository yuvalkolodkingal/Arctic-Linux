"""Closed package comparisons and actual nested copy operations; no VM."""
import ast
import contextlib
import copy
import io
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_contract as F
import test_primary_diagnostics as P
import runner as R

C, G, A, S = F.C, P.G, P.A, P.S
PRIVATE = P.PRIVATE


class PackageComparisonControls(unittest.TestCase):
    def codes(self, observed, expected):
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            C.diagnose_packaged_sources(observed, expected)
        raw = stream.getvalue().encode()
        self.assertIs(S.external_text(raw), raw)
        self.assertNotIn(PRIVATE, stream.getvalue())
        lines = stream.getvalue().splitlines()
        self.assertEqual(len(lines), 6)
        return lines

    def test_six_static_paths_are_exact_and_do_not_emit_hashes_or_values(self):
        self.assertEqual({path for _, path in C.PACKAGED_SOURCE_DIAGNOSTIC_PATHS}, set(C.PACKAGED_SOURCES))
        report, _, _, _, _ = F.fixture()
        expected = report['baseline']['packaged_sources']
        for line, (label, _) in zip(self.codes(expected, expected), C.PACKAGED_SOURCE_DIAGNOSTIC_PATHS):
            self.assertEqual(line, 'ARCTIC-INSTALLER-DIAGNOSTIC=installer-packaged-source-' + label +
                '-expected-present-observed-present-types-valid-bytes-equal-sha256-equal')
        self.assertNotIn(next(iter(expected.values()))['sha256'], '\n'.join(self.codes(expected, expected)))

    def test_every_path_independently_classifies_presence_shape_bytes_and_hash(self):
        report, _, _, _, _ = F.fixture()
        expected = report['baseline']['packaged_sources']
        for index, (_, path) in enumerate(C.PACKAGED_SOURCE_DIAGNOSTIC_PATHS):
            for suffix, mutate in (
                ('observed-absent-types-invalid-bytes-uncompared-sha256-uncompared', lambda d: d.pop(path)),
                ('observed-present-types-invalid-bytes-uncompared-sha256-uncompared', lambda d: d.update({path: {'bytes': True, 'sha256': PRIVATE}})),
                ('observed-present-types-valid-bytes-different-sha256-equal', lambda d: d[path].update(bytes=d[path]['bytes'] + 1)),
                ('observed-present-types-valid-bytes-equal-sha256-different', lambda d: d[path].update(sha256='f' * 64))):
                observed = copy.deepcopy(expected); mutate(observed)
                lines = self.codes(observed, expected)
                self.assertTrue(lines[index].endswith(suffix))
                for other, line in enumerate(lines):
                    if other != index:
                        self.assertTrue(line.endswith('types-valid-bytes-equal-sha256-equal'))

    def test_hostile_subclasses_unknown_fields_and_missing_expected_are_closed(self):
        class HostileDict(dict):
            def __len__(self): raise AssertionError('private mapping length read')
            def __iter__(self): raise AssertionError('private mapping iterated')
            def __getitem__(self, key): raise AssertionError('private mapping read')
        class HostileString(str):
            def __hash__(self): raise AssertionError('private value hashed')
            def __eq__(self, other): raise AssertionError('private value compared')
        path = C.PACKAGED_SOURCE_DIAGNOSTIC_PATHS[0][1]
        expected = {path: {'bytes': 1, 'sha256': 'a' * 64}}
        for value in (None, PRIVATE, HostileDict(), {PRIVATE: PRIVATE},
                      {path: HostileDict()}, {path: {'bytes': 1, 'sha256': HostileString('a' * 64)}},
                      {path: {'bytes': 1, 'sha256': 'a' * 64, PRIVATE: PRIVATE}},
                      {str(i): PRIVATE for i in range(7)}):
            self.codes(value, expected)
        self.assertTrue(all('-expected-unknown-' in c for c in self.codes(expected, None)))

    def test_original_source_byte_gate_and_error_args_still_fail_after_observation(self):
        report, state, files, media, _ = F.fixture()
        expected = copy.deepcopy(report['baseline']['packaged_sources'])
        path = C.PACKAGED_SOURCE_DIAGNOSTIC_PATHS[0][1]
        report['baseline']['packaged_sources'][path]['sha256'] = 'f' * 64
        original = copy.deepcopy(report)
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream), self.assertRaises(RuntimeError) as caught:
            C.validate_report(report, state['context'], files, lambda name: media['installer/' + name], expected)
        self.assertEqual(caught.exception.args, ('packaged GUI bytes differ from exact image source',))
        self.assertEqual(R.contract_assertion_code(caught.exception, C), 'installer-report-validation-assertion-idle-031')
        self.assertEqual(report, original)
        self.assertIn('wrapper-expected-present-observed-present-types-valid-bytes-equal-sha256-different', stream.getvalue())

    def test_closed_stdout_does_not_replace_original_source_byte_failure(self):
        for error in (OSError(PRIVATE), ValueError(PRIVATE), RuntimeError(PRIVATE), TypeError(PRIVATE), P.HostileError(PRIVATE)):
            report, state, files, media, _ = F.fixture()
            original = copy.deepcopy(report)
            with patch('builtins.print', side_effect=error), self.assertRaises(RuntimeError) as caught:
                C.validate_report(report, state['context'], files, lambda name: media['installer/' + name], None)
            self.assertIs(type(caught.exception), RuntimeError)
            self.assertEqual(caught.exception.args, ('packaged GUI bytes differ from exact image source',))
            self.assertEqual(R.contract_assertion_code(caught.exception, C), 'installer-report-validation-assertion-idle-031')
            self.assertIs(caught.exception._arctic_installer_assertion[0], C._ASSERTION_TOKEN)
            self.assertEqual(report, original)
        for error in (KeyboardInterrupt(PRIVATE), SystemExit(PRIVATE)):
            report, state, files, media, _ = F.fixture()
            with patch('builtins.print', side_effect=error), self.assertRaises(type(error)) as caught:
                C.validate_report(report, state['context'], files, lambda name: media['installer/' + name], None)
            self.assertIs(caught.exception, error)


class CopyFixture:
    def __init__(self, owner):
        self.owner = owner
        self.value = A.installer_type(G).__new__(A.installer_type(G))
        self.value.diagnostic_phase = 'prepare-copy'
        self.value.baseline = None; self.value.samples = []; self.value.started_ns = 1
        self.value.safe_config = {'synthetic': True}
        self.identities = {'daemon': {'pid': 20}}
        self.engine = dict(hello={'state': 'installing'}, wizard={'state': 'installing', 'current': 'install'},
            keyboard={'data': G.KEYBOARD}, install={'options': {'progress': {'event': 'progress', 'phase': 'copy',
                'percent': 10, 'paused': False}, 'attention': None, 'failed': None}})
        self.keyboard = {'synthetic-keyboard': True}
        self.writer = {'process': {'pid': 30}}
        self.fail = None; self.error = None; self.trace = []
        self.value.identities = lambda: self.observe('copy-identities', self.identities)
        self.value.rpc = SimpleNamespace(snapshot=lambda: self.observe('copy-snapshot', self.engine),
            config=lambda: self.observe('copy-config', self.value.safe_config))
        self.value.keyboard_files = lambda: self.observe('copy-keyboard-files', self.keyboard)
        self.value.writer = lambda identities: self.observe('copy-writer', self.writer)
        self.value.drm_heads = lambda: self.observe('copy-shipped-bindings', {'synthetic-drm': True})
        self.value.packaged_sources = lambda: self.observe('copy-shipped-bindings', {'synthetic-source': True})

    def observe(self, phase, result=None):
        self.owner.assertEqual(self.value.diagnostic_phase, phase)
        self.trace.append(phase)
        if self.fail == phase:
            raise self.error
        return result


class WriterFixture:
    def __init__(self, owner):
        self.owner = owner
        self.value = A.installer_type(G).__new__(A.installer_type(G))
        self.value.diagnostic_phase = 'copy-writer'; self.value.writer_identity = None
        self.value.context = {'disk_serial': 'ARCTIC-OWNED-TARGET'}
        self.proof = {'pid': 30, 'argv': ['/usr/bin/rsync', '--info=progress2', '/run/rootfsbase/', '/mnt/']}
        self.fail = None; self.error = None; self.trace = []
        self.empty = False; self.foreign_partition = False; self.mount_override = {}
        self.value.command = self.command

    def observe(self, phase, result=None):
        self.owner.assertEqual(self.value.diagnostic_phase, phase)
        self.trace.append(phase)
        if self.fail == phase: raise self.error
        return result

    def command(self, argv):
        phase = 'writer-mount-fstype' if argv[4] == 'FSTYPE' else 'writer-mount-block' if '--nofsroot' in argv else 'writer-mount-source'
        result = 'btrfs' if phase.endswith('fstype') else '/dev/vda1' if phase.endswith('block') else '/dev/vda1[/@]'
        return 0, self.observe(phase, self.mount_override.get(phase, result))

    def path(self, raw):
        fixture = self
        class Node:
            def __init__(self, raw): self.raw = str(raw)
            def __truediv__(self, suffix): return Node(self.raw + '/' + str(suffix))
            @property
            def name(self): return self.raw.rsplit('/', 1)[-1]
            @property
            def parent(self): return Node(self.raw.rsplit('/', 1)[0])
            def __eq__(self, other): return self.raw == other.raw
            def glob(self, pattern):
                fixture.owner.assertEqual(pattern, '[0-9]*')
                return fixture.observe('writer-enumerate', [] if fixture.empty else [Node('/proc/30')])
            def read_text(self):
                if self.raw.endswith('/stat'): return fixture.observe('writer-process-stat', '30 (rsync) S 20 0')
                if self.raw.endswith('/comm'): return fixture.observe('writer-process-filter', 'rsync')
                if self.raw.endswith('/dev'): return fixture.observe('writer-partition-major-minor', '254:1')
                raise AssertionError('unexpected synthetic file')
            def resolve(self):
                fixture.observe('writer-partition-guard')
                if fixture.foreign_partition and self.name == 'vda1': return Node('/sys/devices/foreign/block/vdb/vdb1')
                return Node('/sys/devices/owned/block/' + ('vda/vda1' if self.name == 'vda1' else 'vda'))
        return Node(raw)


class NestedCopyControls(unittest.TestCase):
    def assert_private_failure(self, value, error, phase):
        self.assertEqual(value.diagnostic_phase, phase)
        masked = G.masked_active_error(error, phase)
        self.assertNotIn('private', masked); self.assertNotIn('תמלול', masked)
        codes = R.primary_reported_codes({'errors': [masked]}, True)
        self.assertIn('installer-reported-active-primary-phase-' + phase, codes)
        raw = ('\n'.join('ARCTIC-INSTALLER-DIAGNOSTIC=' + c for c in codes) + '\n').encode()
        self.assertIs(S.external_text(raw), raw)

    def test_actual_copy_operations_keep_exact_hostile_exception_and_nested_phase(self):
        for phase in ('copy-identities', 'copy-snapshot', 'copy-config', 'copy-keyboard-files', 'copy-writer', 'copy-shipped-bindings'):
            fixture = CopyFixture(self); fixture.fail = phase; fixture.error = P.HostileError(PRIVATE)
            if phase == 'copy-shipped-bindings':
                fixture.value.baseline = {'identities': fixture.identities, 'drm_heads': {'synthetic-drm': True}}
            with self.assertRaises(P.HostileError) as caught: fixture.value.unchanged()
            self.assertIs(caught.exception, fixture.error)
            self.assert_private_failure(fixture.value, caught.exception, phase)

    def test_actual_original_copy_guards_remain_fatal_at_closed_phase(self):
        for phase, mutate, message in (
            ('copy-identity-continuity', lambda f: setattr(f.value, 'baseline', {'identities': {}}), 'original active engine/GUI identity changed'),
            ('copy-progress-guard', lambda f: f.engine['install']['options']['progress'].update(percent=0), 'genuine copy phase is required for every disruption observation'),
            ('copy-config', lambda f: setattr(f.value.rpc, 'config', lambda: {}), 'active safe configuration changed'),
            ('copy-keyboard-continuity', lambda f: setattr(f.value, 'baseline', {'identities': f.identities, 'drm_heads': {'synthetic-drm': True},
                'packaged_sources': {'synthetic-source': True}, 'keyboard_files': {}}), 'active Hebrew configuration changed'),
            ('copy-progress-continuity', lambda f: f.value.samples.append({'engine': {'install': {'options': {'progress': {'percent': 11}}}}}), 'active engine progress regressed')):
            fixture = CopyFixture(self); mutate(fixture)
            with self.assertRaises(RuntimeError) as caught: fixture.value.unchanged()
            self.assertEqual(caught.exception.args, (message,))
            self.assert_private_failure(fixture.value, caught.exception, phase)

    def test_copy_success_restores_caller_phase_and_original_observation(self):
        fixture = CopyFixture(self)
        result = fixture.value.unchanged()
        self.assertEqual(fixture.value.diagnostic_phase, 'prepare-copy')
        self.assertIs(result, fixture.value.samples[0]); self.assertIs(result['engine'], fixture.engine)
        self.assertIs(result['identities'], fixture.identities); self.assertIs(result['writer'], fixture.writer)

    def test_actual_writer_operations_keep_exact_exception_and_last_nested_phase(self):
        for phase in ('writer-enumerate', 'writer-process-stat', 'writer-process-filter', 'writer-process-proof',
                      'writer-mount-source', 'writer-mount-block', 'writer-mount-fstype', 'writer-partition-guard', 'writer-partition-major-minor'):
            fixture = WriterFixture(self); fixture.fail = phase; fixture.error = P.HostileError(PRIVATE)
            with patch.object(A, 'Path', fixture.path), patch.object(G, 'process_proof',
                    lambda *args: fixture.observe('writer-process-proof', (fixture.proof, None))):
                with self.assertRaises(P.HostileError) as caught: fixture.value.writer({'daemon': {'pid': 20}})
            self.assertIs(caught.exception, fixture.error)
            self.assert_private_failure(fixture.value, caught.exception, phase)

    def test_actual_writer_success_restores_caller_and_retains_exact_mount_proof(self):
        fixture = WriterFixture(self)
        with patch.object(A, 'Path', fixture.path), patch.object(G, 'process_proof',
                lambda *args: fixture.observe('writer-process-proof', (fixture.proof, None))):
            result = fixture.value.writer({'daemon': {'pid': 20}})
        self.assertEqual(fixture.value.diagnostic_phase, 'copy-writer')
        self.assertEqual(result['ancestor_pids'], [30, 20]); self.assertIs(result['process'], fixture.proof)
        self.assertEqual(result['mount'], {'target': '/mnt', 'source': '/dev/vda1[/@]', 'block_source': '/dev/vda1',
            'fstype': 'btrfs', 'major_minor': '254:1'})

    def test_original_writer_guards_remain_fatal_at_closed_phase(self):
        for phase, mutate, message in (
            ('writer-process-argv', lambda f: f.proof.update(argv=['/usr/bin/rsync', '/foreign/', '/mnt/']), 'actual copy writer argv differs'),
            ('writer-unique', lambda f: setattr(f, 'empty', True), 'one original daemon-owned copy writer is required'),
            ('writer-continuity', lambda f: setattr(f.value, 'writer_identity', {}), 'original copy writer was replaced'),
            ('writer-mount-guard', lambda f: f.mount_override.update({'writer-mount-fstype': 'ext4'}), 'actual writer target mount is not owned btrfs'),
            ('writer-partition-guard', lambda f: setattr(f, 'foreign_partition', True), 'target partition belongs to another disk')):
            fixture = WriterFixture(self); mutate(fixture)
            with patch.object(A, 'Path', fixture.path), patch.object(G, 'process_proof',
                    lambda *args: fixture.observe('writer-process-proof', (fixture.proof, None))):
                with self.assertRaises(RuntimeError) as caught: fixture.value.writer({'daemon': {'pid': 20}})
            self.assertEqual(caught.exception.args, (message,))
            self.assert_private_failure(fixture.value, caught.exception, phase)

    def test_original_wait_timeout_keeps_composite_error_private_and_fixed_nested_phase(self):
        fixture = CopyFixture(self); fixture.value.deadline = 480
        fixture.fail = 'copy-snapshot'; fixture.error = RuntimeError(PRIVATE)
        with patch.object(G.time, 'monotonic', side_effect=[0, 0, 179.9, 180.1]), patch.object(G.time, 'sleep'):
            with self.assertRaises(RuntimeError) as caught:
                fixture.value.wait(fixture.value.unchanged, 180, 'real GUI engine did not enter genuine copy')
        self.assertEqual(caught.exception.args, ('real GUI engine did not enter genuine copy: ' + PRIVATE,))
        self.assertEqual(fixture.trace, ['copy-identities', 'copy-snapshot'] * 2)
        self.assert_private_failure(fixture.value, caught.exception, 'copy-snapshot')
        self.assertEqual(G.primary_diagnostic_reason(caught.exception), 'unknown')

    def test_all_new_phase_literals_have_actual_source_assignments_and_no_errno_widening(self):
        tree = ast.parse(Path(__file__).with_name('active-guest.py').read_text())
        phases = {node.value.value for node in ast.walk(tree) if isinstance(node, ast.Assign) and
            isinstance(node.value, ast.Constant) and type(node.value.value) is str and
            any(isinstance(target, ast.Attribute) and target.attr == 'diagnostic_phase' for target in node.targets)}
        for phase in (p for p in G.ACTIVE_DIAGNOSTIC_PHASES if p.startswith(('copy-', 'writer-'))):
            self.assertIn(phase, phases); self.assertNotIn(phase, G.TARGET_DIAGNOSTIC_PHASES)
            self.assertNotIn('errno=', G.masked_active_error(OSError(6, PRIVATE), phase))


if __name__ == '__main__': unittest.main()
