"""Fail-only fixed diagnostics: synthetic private logs, no VM/acceptance result."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import types
import unittest
from unittest.mock import Mock, patch

import performance_external_fixture as F

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT/relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


inner = load('fixed_phase_inner', 'tools/performance/run-paired.py')
outer = load('fixed_phase_outer', 'tools/performance/qualification.py')
screen = load('fixed_phase_screen', 'tools/native-functional/screen-evidence.py')


class FixedFailurePhaseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root/'work'
        self.work.mkdir()
        self.task = 'a'*32
        self.state = dict(task_id=self.task, phase='blocked', error='password=do-not-export')
        self.owner = dict(schema='arctic-paired-test-image-owner-v1', release_acceptance=False,
            task_id=self.task, container='arctic-paired-'+self.task+'-'+'b'*8, base_id='sha256:'+'c'*64)
        self.write('status.json', json.dumps(self.state))
        self.write('vm-prepared-image-owner.json', json.dumps(self.owner))
        self.write('baseline-install-harness.log', 'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean\n')
        self.write('candidate-install-harness.log', 'ARCTIC-PRISTINE-INSTALL-POWEROFF=clean\n')
        self.write('runs/baseline/1/performance-context.json', json.dumps(dict(image='baseline', boot=1,
            collector='console', arbitrary_private='token=private')))
        self.write('runs/baseline/1/harness.log', '[  10s] booting the default entry\n'
            '[  20s] passphrase prompt on screen: boot-31-luks-prompt.png\n'
            'password=do-not-export https://private.invalid/?access_token=private\n')
        self.write('runs/baseline/1/serial-boot.log', 'transcript: private words\n'
            'RuntimeError: No unique actual desktop session for console restoration\n')

    def write(self, name, content):
        path = self.work/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def summary(self, code='sensitive_text'):
        return inner.failure_phase_summary(self.work, code)

    def exporter(self, name, path):
        return inner if name == 'paired_failure_phase' else screen

    def export(self, target=None):
        with patch.object(outer, 'C', F.contract), patch.object(outer, 'load', side_effect=self.exporter):
            outer.export_failure_phase(self.work, target or self.root/'screened', 'sensitive_text')

    def test_private_text_never_enters_closed_summary_and_originals_unchanged(self):
        originals = {p: p.read_bytes() for p in self.work.rglob('*') if p.is_file()}
        result = self.summary()
        content = json.dumps(result).encode()
        for private in (b'do-not-export', b'private words', b'private.invalid', b'access_token', b'arbitrary_private'):
            self.assertNotIn(private, content)
        self.assertEqual(result['observed_context'], 'baseline_1')
        self.assertEqual(result['console_restore_error'], 'no_unique_desktop_session')
        self.assertTrue(result['private_owner_verified'])
        self.assertFalse(result['release_acceptance'])
        self.assertFalse(result['performance_acceptance'])
        self.assertFalse(result['original_evidence_uploaded'])
        self.assertNotIn('completed_boots', result)
        self.assertEqual(originals, {p: p.read_bytes() for p in originals})
        self.assertEqual(screen.external_text(content), content)

    def test_markers_and_smoke_zero_are_only_observations_not_measurements(self):
        self.write('runs/baseline/1/harness.log', 'qemu started (boot): private arguments\n'
            'qemu exited: see qemu-boot.log\nno QMP socket\n')
        self.write('runs/baseline/1/serial-boot.log', 'ARCTIC-PERFORMANCE-CONSOLE-RESTORED session=private vt=1\n'
            'ARCTIC-COLLECT-BEGIN\nARCTIC-COLLECT-END\nARCTIC-INSTALLED-SMOKE-EXIT=0\n')
        result = self.summary()
        self.assertEqual(result['smoke_exit'], 'zero')
        self.assertTrue(result['markers']['collector_end'])
        self.assertTrue(result['markers']['qemu_start'])
        self.assertTrue(result['markers']['qmp_not_connected'])
        self.assertTrue(result['markers']['qemu_exit_before_qmp'])
        self.assertEqual(result['status'], 'unqualified_fixed_observations_only')
        self.assertNotIn('comparison', result)
        self.assertFalse(result['performance_acceptance'])

    def test_duplicate_or_nonzero_exit_has_no_dynamic_value_export(self):
        for content, expected in [('ARCTIC-INSTALLED-SMOKE-EXIT=255\n', 'nonzero'),
                ('ARCTIC-INSTALLED-SMOKE-EXIT=0\nARCTIC-INSTALLED-SMOKE-EXIT=1\n', 'ambiguous'),
                ('ARCTIC-INSTALLED-SMOKE-EXIT=password=private\n', 'absent')]:
            self.write('runs/baseline/1/serial-boot.log', content)
            result = self.summary()
            self.assertEqual(result['smoke_exit'], expected)
            self.assertNotIn('private', json.dumps(result).replace('private_owner_verified', ''))

    def test_wrong_owner_boolean_and_duplicate_json_prevent_log_reads(self):
        for fault in ('task', 'release', 'duplicate'):
            owner = dict(self.owner)
            if fault == 'task': owner['task_id'] = 'd'*32
            if fault == 'release': owner['release_acceptance'] = 0
            content = json.dumps(owner)
            if fault == 'duplicate': content = content[:-1] + ',"task_id":"'+self.task+'"}'
            self.write('vm-prepared-image-owner.json', content)
            result = self.summary()
            self.assertFalse(result['private_owner_verified'])
            self.assertEqual(result['read_status']['serial'], 'unavailable')

    def test_symlinked_root_and_intermediate_directories_are_not_followed(self):
        link = self.root/'linked-work'
        link.symlink_to(self.work, target_is_directory=True)
        self.assertFalse(inner.failure_phase_summary(link, 'unclassified')['private_owner_verified'])
        runs = self.work/'runs'
        runs.rename(self.root/'private-runs')
        runs.symlink_to(self.root/'private-runs', target_is_directory=True)
        result = self.summary()
        self.assertEqual(result['read_status']['context'], 'unsafe_or_oversized')
        self.assertEqual(result['read_status']['serial'], 'unavailable')

    def test_serial_symlink_fifo_and_oversize_are_rejected_without_payload_read(self):
        path = self.work/'runs/baseline/1/serial-boot.log'
        original = self.root/'private-serial.log'
        original.write_text('ARCTIC-COLLECT-END\npassword=private\n')
        for fault in ('symlink', 'fifo', 'oversize'):
            path.unlink()
            if fault == 'symlink': path.symlink_to(original)
            elif fault == 'fifo': os.mkfifo(path)
            else:
                with path.open('wb') as output:
                    output.seek(8388608)
                    output.write(b'x')
            result = self.summary()
            self.assertEqual(result['read_status']['serial'], 'unsafe_or_oversized')
            self.assertFalse(result['markers']['collector_end'])

    def test_malformed_context_and_boolean_boot_are_not_selected(self):
        for content in ('{"image":"baseline","boot":true,"collector":"console"}',
                        '{"image":"baseline","boot":1,"boot":1,"collector":"console"}'):
            self.write('runs/baseline/1/performance-context.json', content)
            result = self.summary()
            self.assertEqual(result['observed_context'], 'none')
            self.assertEqual(result['read_status']['serial'], 'unavailable')

    def test_screen_exception_classifier_never_stringifies_arbitrary_errors(self):
        class PrivateError(RuntimeError):
            def __str__(self): raise AssertionError('Private error must not be rendered')
        for error in (PrivateError('password=private'), RuntimeError('token=private'),
                      RuntimeError('Sensitive text in external evidence', 'password=private'),
                      ValueError('https://private.invalid/?token=private')):
            self.assertEqual(outer.fixed_screen_failure(error), 'unclassified')
        self.assertEqual(outer.fixed_screen_failure(RuntimeError('Sensitive text in external evidence')), 'sensitive_text')
        self.assertEqual(outer.fixed_screen_failure(TimeoutError('password=private')), 'deadline')
        for code in ('password=private', True, 'sensitive_text\nprivate'):
            with self.assertRaises(ValueError): self.summary(code)

    def test_export_uses_unchanged_atomic_scanner_and_keeps_private_originals(self):
        raw = {p: p.read_bytes() for p in self.work.rglob('*') if p.is_file()}
        with self.assertRaises(RuntimeError): screen.external_text(raw[self.work/'runs/baseline/1/serial-boot.log'])
        self.export()
        target = self.root/'screened'
        self.assertEqual({p.name for p in target.iterdir()}, {'unqualified-failure-phase.json', 'upload-screening.json'})
        content = (target/'unqualified-failure-phase.json').read_bytes()
        receipt = json.loads((target/'upload-screening.json').read_bytes())['files']['unqualified-failure-phase.json']
        digest = hashlib.sha256(content).hexdigest()
        self.assertEqual(receipt, dict(original_sha256=digest, uploaded_sha256=digest, bytes=len(content), redactions=0))
        self.assertEqual(raw, {p: p.read_bytes() for p in raw})
        entries = {p.name: p.read_bytes() for p in target.iterdir()}
        _, kwargs = F.fixture()
        with F.archive(entries) as archive, self.assertRaisesRegex(ValueError, 'Missing full original paired inputs'):
            F.contract.validate_evidence(archive, **kwargs)

    def test_existing_or_symlinked_output_and_non_siblings_are_never_modified(self):
        target = self.root/'screened'
        outside = self.root/'private-target'
        outside.write_text('password=private')
        for fault in ('file', 'symlink', 'non_sibling'):
            candidate = target
            if fault == 'file': target.write_text('existing')
            elif fault == 'symlink': target.symlink_to(outside)
            else: candidate = self.root/'elsewhere'/'screened'
            with self.assertRaises(ValueError): self.export(candidate)
            self.assertEqual(outside.read_text(), 'password=private')
            if target.is_symlink() or target.exists(): target.unlink()

    def test_failed_runner_and_rejected_full_export_produce_only_unqualified_summary(self):
        # Exercise the real finalizer with an owned synthetic child and real
        # strict scanner. No process, VM, host log or measurement is created.
        self.work.rename(self.root/'seed')
        seed = self.root/'seed'
        args = types.SimpleNamespace(work=self.work, screened=self.root/'screened', evidence=self.root/'evidence',
            inputs=self.root/'inputs', source=self.root/'source', manifest=self.root/'manifest.json')
        args.inputs.mkdir(); (args.inputs/'PERFORMANCE-PLAN.json').write_text('{}\n'); args.manifest.write_text('{}\n')
        class Child:
            pid = 123456789
            def wait(child, timeout=None):
                if not self.work.exists():
                    import shutil
                    shutil.copytree(seed, self.work)
                return 1
            def poll(child): return 1
        plan = dict(image=dict(name='test.iso', source_sha='a'*40, sha256='b'*64),
            observer={}, candidate_source_files={}, execution_files={})
        contract = types.SimpleNamespace(require=F.contract.require, BASELINE=F.contract.BASELINE, validate_evidence=Mock())
        with patch.object(outer, 'C', contract), patch.object(outer, 'activation', return_value=(plan, 'c'*40)), \
                patch.object(outer, 'verify', return_value={}), patch.object(outer, 'baseline', return_value=self.root/'baseline.iso'), \
                patch.object(outer, 'load', side_effect=self.exporter), patch.object(outer.subprocess, 'Popen', return_value=Child()), \
                patch.dict(os.environ, GITHUB_RUN_ID='31', GITHUB_SHA='d'*40):
            with self.assertRaisesRegex(RuntimeError, 'screen'):
                outer.run(args)
        contract.validate_evidence.assert_not_called()
        diagnostic = json.loads((args.screened/'unqualified-failure-phase.json').read_bytes())
        self.assertEqual(diagnostic['screening_failure'], 'sensitive_text')
        self.assertEqual(diagnostic['status'], 'unqualified_fixed_observations_only')
        self.assertEqual((args.evidence/'runs/baseline/1/serial-boot.log').read_bytes(),
                         (seed/'runs/baseline/1/serial-boot.log').read_bytes())
        self.assertEqual({p.name for p in args.screened.iterdir()}, {'unqualified-failure-phase.json', 'upload-screening.json'})

    def prepare_guest(self):
        # CI runs as root inside Fedora while the mounted checkout may belong
        # to the host runner. Keep the production ownership gate unchanged:
        # its source bytes must come from this test's own source directory.
        self.observer_sources = self.root/'observer-sources'
        for name in ('guest', 'causal'):
            relative = 'tools/performance/'+name+'.py'
            original = (ROOT/relative).read_bytes()
            target = self.observer_sources/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original)
            self.assertEqual(target.read_bytes(), original)
            self.assertEqual(target.stat().st_uid, os.geteuid())
        self.assertEqual(self.observer_sources.stat().st_uid, os.geteuid())
        source_patch = patch.object(inner, 'ROOT', self.observer_sources)
        source_patch.start()
        self.addCleanup(source_patch.stop)
        self.observer = F.contract.observer_hashes(ROOT)
        self.state['observer_sha256'] = self.observer['frozen_sha256']
        self.write('status.json', json.dumps(self.state))
        self.write('runs/baseline/1/performance-context.json', json.dumps(dict(image='baseline', boot=1,
            collector='console', external_execution=dict(observer=self.observer))))
        subprocess.run([sys.executable, str(ROOT/'tools/performance/compose-paired-probe.py'),
            str(self.work/'frozen-observer.py')], check=True, timeout=10)
        # Independent fixtures derive actual raise/function locations, rather
        # than inserting a production code or changing observer source bytes.
        self.sites = []
        for source in ('guest', 'causal'):
            tree = ast.parse((ROOT/('tools/performance/'+source+'.py')).read_bytes())
            parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
            for node in ast.walk(tree):
                if not isinstance(node, ast.Raise) or not isinstance(node.exc, ast.Call) or not node.exc.args:
                    continue
                first = node.exc.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    prefix, exact = first.value, True
                elif isinstance(first, ast.JoinedStr) and isinstance(first.values[0], ast.Constant):
                    prefix, exact = first.values[0].value, False
                elif isinstance(first, ast.BinOp) and isinstance(first.left, ast.Constant):
                    prefix, exact = first.left.value, False
                else:
                    continue
                if not prefix or '\n' in prefix or '\r' in prefix:
                    continue
                function = node
                while not isinstance(function, ast.FunctionDef) and function in parents:
                    function = parents[function]
                self.sites.append(dict(source=source, line=node.lineno,
                    function=function.name if isinstance(function, ast.FunctionDef) else '<module>',
                    exception=node.exc.func.id, prefix=prefix, exact=exact))
        self.assertEqual(len(self.sites), 104)

    def guest_record(self, check, value):
        return 'ARCTIC-PERFORMANCE ' + json.dumps(dict(stage='installed', check=check, value=value)) + '\n'

    def guest_trace(self, site=None, message=None):
        site = site or next(x for x in self.sites if (x['source'], x['line']) == ('guest', 360))
        frames = '  File "/run/t/guest-check.py", line 11, in <module>\n'
        if site['function'] != 'main':
            frames += '  File "/run/t/guest-check.py", line 881, in main\n'
        frames += f'  File "/run/t/guest-check.py", line {site["line"]}, in {site["function"]}\n'
        return ('ARCTIC-COLLECT-BEGIN\n'
            + self.guest_record('observer_source_sha256', self.observer['source_sha256'])
            + self.guest_record('measurement_conditions', {'private': 'password=do-not-export'})
            + 'Traceback (most recent call last):\n' + frames
            + site['exception'] + ': ' + (message if message is not None else site['prefix']) + '\n'
            + 'password=do-not-export transcript: מילים סודיות https://private.invalid/?token=private\n'
            + 'ARCTIC-INSTALLED-SMOKE-EXIT=1\nARCTIC-COLLECT-END\n')

    def test_all_104_actual_source_sites_have_closed_diagnostic_codes_only(self):
        self.prepare_guest()
        for site in self.sites:
            with self.subTest(source=site['source'], line=site['line']):
                self.write('runs/baseline/1/serial-boot.log', self.guest_trace(site))
                result = self.summary()
                self.assertEqual(result['guest_failure'], dict(status='source_known_shape',
                    code=site['source']+'_'+str(site['line']), exception_class=site['exception'],
                    last_observer_phase='measurement_conditions'))
                self.assertFalse(result['performance_acceptance'])
                self.assertFalse(result['release_acceptance'])
                content = json.dumps(result).encode()
                self.assertEqual(screen.external_text(content), content)
                self.assertNotIn(b'do-not-export', content)
                # Exercise the independent consumer's entire closed 104-code
                # inventory without substituting/reimplementing its validator.
                target = self.root/'screened'
                with patch.object(inner, 'failure_phase_summary', return_value=result):
                    self.export(target)
                import shutil
                shutil.rmtree(target)

    def test_known_dynamic_error_and_unknown_private_error_never_export_tails(self):
        self.prepare_guest()
        site = next(x for x in self.sites if (x['source'], x['line']) == ('guest', 211))
        self.write('runs/baseline/1/serial-boot.log', self.guest_trace(site,
            site['prefix']+'password=do-not-export transcript: מילים סודיות'))
        result = self.summary()
        self.assertEqual(result['guest_failure']['code'], 'guest_211')
        original = (self.work/'runs/baseline/1/serial-boot.log').read_bytes()
        self.export()
        exported = (self.root/'screened/unqualified-failure-phase.json').read_bytes()
        self.assertNotIn(b'do-not-export', exported)
        self.assertNotIn('מילים'.encode(), exported)
        self.assertNotIn(b'guest-check.py', exported)
        self.assertEqual((self.work/'runs/baseline/1/serial-boot.log').read_bytes(), original)
        self.write('runs/baseline/1/serial-boot.log', self.guest_trace(message='password=unknown transcript: private'))
        self.assertEqual(self.summary()['guest_failure'], dict(status='unknown', code='none',
            exception_class='none', last_observer_phase='unavailable'))

    def test_echoed_or_injected_literals_frames_paths_and_control_bytes_cannot_classify(self):
        self.prepare_guest()
        valid = self.guest_trace()
        variants = [
            valid.replace('Traceback (most recent call last):', '$ echo Traceback (most recent call last):'),
            valid.replace('/run/t/guest-check.py', '/private/guest-check.py'),
            valid.replace('line 360, in desktop', 'line 361, in desktop'),
            valid.replace('line 360, in desktop', 'line 360, in injected'),
            valid.replace('line 11, in <module>', 'line 8, in <module>'),
            valid.replace('line 881, in main', 'line 881, in injected'),
            valid.replace('Traceback (most recent call last):', '\x1b[31mTraceback (most recent call last):'),
            valid.replace('Traceback (most recent call last):', '\vTraceback (most recent call last):'),
            valid.replace('RuntimeError: No unique non-root Mango session', 'RuntimeError: No unique non-root Mango session EXTRA'),
            valid.replace('ARCTIC-COLLECT-BEGIN\n', '').replace('ARCTIC-COLLECT-END\n', '')]
        for uart in variants:
            with self.subTest(variant=variants.index(uart)):
                self.write('runs/baseline/1/serial-boot.log', uart)
                self.assertNotEqual(self.summary()['guest_failure']['status'], 'source_known_shape')
        escaped = self.guest_record('measurement_conditions', {'private': valid})
        self.write('runs/baseline/1/serial-boot.log', 'ARCTIC-COLLECT-BEGIN\n'+escaped+
            'ARCTIC-INSTALLED-SMOKE-EXIT=1\nARCTIC-COLLECT-END\n')
        self.assertEqual(self.summary()['guest_failure']['status'], 'unknown')

    def test_duplicate_chain_markers_observer_records_and_phases_fail_closed(self):
        self.prepare_guest()
        valid = self.guest_trace()
        variants = [valid.replace('Traceback (most recent call last):',
                'Traceback (most recent call last):\nTraceback (most recent call last):'),
            valid.replace('RuntimeError: No unique non-root Mango session',
                'RuntimeError: No unique non-root Mango session\nRuntimeError: No unique non-root Mango session'),
            valid.replace('ARCTIC-COLLECT-BEGIN\n', 'ARCTIC-COLLECT-BEGIN\nARCTIC-COLLECT-BEGIN\n'),
            valid.replace('ARCTIC-COLLECT-END\n', 'ARCTIC-COLLECT-END\nARCTIC-COLLECT-END\n'),
            valid.replace('ARCTIC-INSTALLED-SMOKE-EXIT=1\n',
                'ARCTIC-INSTALLED-SMOKE-EXIT=1\nARCTIC-INSTALLED-SMOKE-EXIT=1\n'),
            valid.replace('Traceback (most recent call last):',
                self.guest_record('observer_source_sha256', self.observer['source_sha256'])+'Traceback (most recent call last):'),
            valid.replace('Traceback (most recent call last):',
                self.guest_record('measurement_conditions', {})+'Traceback (most recent call last):')]
        for uart in variants:
            self.write('runs/baseline/1/serial-boot.log', uart)
            self.assertNotEqual(self.summary()['guest_failure']['status'], 'source_known_shape')

    def test_truncated_invalid_utf8_invalid_json_or_nonzero_code_fail_closed(self):
        self.prepare_guest()
        valid = self.guest_trace()
        path = self.work/'runs/baseline/1/serial-boot.log'
        variants = [valid.rstrip('\n').encode(), b'\xff'+valid.encode(),
            valid.replace('ARCTIC-COLLECT-END\n', '').encode(),
            valid.replace('"stage": "installed"', '"stage": "installed", "stage": "installed"').encode(),
            valid.replace('"stage": "installed"', '"stage": "live"').encode(),
            valid.replace('ARCTIC-INSTALLED-SMOKE-EXIT=1', 'ARCTIC-INSTALLED-SMOKE-EXIT=999').encode(),
            valid.replace('ARCTIC-INSTALLED-SMOKE-EXIT=1', 'ARCTIC-INSTALLED-SMOKE-EXIT=0').encode()]
        nested = 'ARCTIC-PERFORMANCE {"stage":"installed","check":"measurement_conditions","value":'+ '['*1500+'0'+']'*1500+'}\n'
        variants.append(valid.replace('Traceback (most recent call last):', nested+'Traceback (most recent call last):').encode())
        for uart in variants:
            path.write_bytes(uart)
            self.assertNotEqual(self.summary()['guest_failure']['status'], 'source_known_shape')

    def test_current_context_frozen_observer_and_source_hashes_are_required(self):
        self.prepare_guest()
        self.write('runs/baseline/1/serial-boot.log', self.guest_trace())
        original = (self.work/'frozen-observer.py').read_bytes()
        (self.work/'frozen-observer.py').write_bytes(original+b'# altered\n')
        self.assertEqual(self.summary()['guest_failure']['status'], 'source_mismatch')
        (self.work/'frozen-observer.py').write_bytes(original)
        other = self.root/'other-sources'
        for name in ('guest', 'causal'):
            target = other/('tools/performance/'+name+'.py')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((ROOT/('tools/performance/'+name+'.py')).read_bytes())
        (other/'tools/performance/guest.py').write_bytes(b'# changed\n')
        with patch.object(inner, 'ROOT', other):
            self.assertEqual(self.summary()['guest_failure']['status'], 'source_mismatch')
        # A later current context cannot borrow the earlier boot's traceback.
        self.write('runs/candidate/1/performance-context.json', json.dumps(dict(image='candidate', boot=1,
            collector='console', external_execution=dict(observer=self.observer))))
        self.write('runs/candidate/1/serial-boot.log', 'ARCTIC-INSTALLED-SMOKE-EXIT=1\n')
        self.assertEqual(self.summary()['guest_failure']['status'], 'ambiguous')
        self.assertEqual(self.summary()['observed_context'], 'candidate_1')

    def test_wrong_source_directory_or_file_owner_still_fails_closed(self):
        self.prepare_guest()
        self.write('runs/baseline/1/serial-boot.log', self.guest_trace())
        self.assertEqual(self.summary()['guest_failure']['status'], 'source_known_shape')
        real_fstat = os.fstat
        for path in (self.observer_sources,
                self.observer_sources/'tools/performance/guest.py',
                self.observer_sources/'tools/performance/causal.py'):
            inode = path.stat().st_ino
            def wrong_owner(fd):
                info = real_fstat(fd)
                if info.st_ino == inode:
                    fields = list(info); fields[4] = os.geteuid()+1
                    return os.stat_result(fields)
                return info
            with self.subTest(source=path.name), patch.object(inner.os, 'fstat', side_effect=wrong_owner):
                self.assertEqual(self.summary()['guest_failure']['status'], 'source_mismatch')
        self.assertEqual(self.summary()['guest_failure']['status'], 'source_known_shape')

    def test_actual_descriptor_owner_regular_type_symlink_and_changed_read_guards(self):
        self.prepare_guest()
        path = self.write('runs/baseline/1/serial-boot.log', self.guest_trace())
        original = path.read_bytes()
        real_fstat = os.fstat
        inode = path.stat().st_ino
        def wrong_owner(fd):
            info = real_fstat(fd)
            if info.st_ino == inode:
                fields = list(info); fields[4] = os.geteuid()+1
                return os.stat_result(fields)
            return info
        with patch.object(inner.os, 'fstat', side_effect=wrong_owner):
            result = self.summary()
        self.assertEqual(result['read_status']['serial'], 'unsafe_or_oversized')
        self.assertEqual(result['guest_failure']['status'], 'unavailable')
        real_fdopen = os.fdopen
        class MutatingReader:
            def __init__(reader, source): reader.source = source
            def __enter__(reader): return reader
            def __exit__(reader, *args): reader.source.close()
            def fileno(reader): return reader.source.fileno()
            def read(reader, size):
                data = reader.source.read(size)
                with path.open('ab') as output: output.write(b'changed\n')
                return data
        def mutated_open(fd, mode):
            source = real_fdopen(fd, mode)
            return MutatingReader(source) if real_fstat(fd).st_ino == inode else source
        with patch.object(inner.os, 'fdopen', side_effect=mutated_open):
            result = self.summary()
        self.assertEqual(result['read_status']['serial'], 'unsafe_or_oversized')
        path.unlink()
        outside = self.root/'private-current-uart'; outside.write_bytes(original)
        path.symlink_to(outside)
        self.assertEqual(self.summary()['read_status']['serial'], 'unsafe_or_oversized')
        path.unlink(); os.mkfifo(path)
        self.assertEqual(self.summary()['read_status']['serial'], 'unsafe_or_oversized')

    def test_consumer_rejects_arbitrary_fields_classes_codes_phases_and_wrong_types(self):
        self.prepare_guest()
        self.write('runs/baseline/1/serial-boot.log', self.guest_trace())
        valid = self.summary()
        changes = [dict(code='guest_999'), dict(exception_class='ValueError'),
            dict(last_observer_phase='password=private'), dict(code=True),
            dict(status='measured'), dict(status='unknown'), dict(message='private'),
            dict(last_observer_phase='None'), dict(exception_class='transcript: private')]
        for changed in changes:
            summary = dict(valid, guest_failure=dict(valid['guest_failure'], **changed))
            with patch.object(inner, 'failure_phase_summary', return_value=summary):
                with self.assertRaisesRegex(ValueError, 'Unsafe guest failure diagnostic'):
                    self.export()
            self.assertFalse((self.root/'screened').exists())
        for summary in (dict(valid, arbitrary='private'), dict(valid, schema='unknown')):
            with patch.object(inner, 'failure_phase_summary', return_value=summary):
                with self.assertRaisesRegex(ValueError, 'Unsafe failure summary fields'):
                    self.export()


if __name__ == '__main__':
    unittest.main()
