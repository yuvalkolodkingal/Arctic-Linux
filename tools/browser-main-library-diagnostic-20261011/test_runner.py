import base64
import ast
from contextlib import redirect_stdout, contextmanager
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import os
import signal
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

HERE = Path(__file__).parent
def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result
runner = module('runner'); wrapper = module('guest-wrapper')


@contextmanager
def synthetic_root_metadata(private):
    """Only root UID is simulated; actual mode/inode/bytes/child cleanup remain real."""
    original_stat, original_fstat = Path.stat, os.fstat
    def root_uid(info):
        values = {key: getattr(info, key) for key in dir(info) if key.startswith('st_')}
        return types.SimpleNamespace(**dict(values, st_uid=0))
    def stat_fixture(path, *args, **kwargs):
        info = original_stat(path, *args, **kwargs)
        return root_uid(info) if path == private else info
    with patch.object(Path, 'stat', stat_fixture), patch.object(wrapper.os, 'fstat', side_effect=lambda fd: root_uid(original_fstat(fd))):
        yield


class SourceControls(unittest.TestCase):
    def manifest(self):
        return json.loads((HERE / 'execution-manifest.json').read_text())

    def test_disabled_rejects_before_any_acquisition(self):
        m = self.manifest(); m['ready'] = False; m['profile_binding'] = None
        runner.validate_manifest(m)
        with patch.object(runner, 'capture', side_effect=AssertionError('acquisition')), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'disabled_or_profile_not_admitted'):
                runner.activation_guard(HERE, m)

    def test_ready_without_actual_profile_rejects(self):
        m = self.manifest(); m['ready'] = True; m['profile_binding'] = None
        with self.assertRaisesRegex(RuntimeError, 'disabled_or_profile_not_admitted'):
            runner.validate_manifest(m, executable=True)

    def test_operational_ready_still_rejects_local_lane_before_acquisition(self):
        m = self.manifest(); m['ready'] = True; runner.validate_manifest(m, executable=True)
        with patch.object(runner, 'capture', side_effect=AssertionError('acquisition')), patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'hosted_lane'):
                runner.activation_guard(HERE, m)

    def test_actual_profile_metadata_and_helper_bindings_are_consistent(self):
        root = HERE.parents[1]; m = self.manifest(); profiles = []
        for name in ('causal.py', 'compare.py'):
            path = root / 'tools/performance' / name; raw = path.read_bytes()
            if name == 'causal.py':
                self.assertEqual(hashlib.sha256(raw).hexdigest(), m['helper_files'][name])
            frozen = types.ModuleType('admitted_profile_control_' + name.replace('.', '_'))
            frozen.__file__ = str(path); exec(compile(raw, str(path), 'exec'), frozen.__dict__)
            profiles.append(next(value for value in frozen.MAPPING_PROFILES
                if value['executable_sha256'] == m['profile_binding']['mango_sha256']))
        self.assertEqual(profiles[0], profiles[1])
        self.assertEqual(profiles[0]['native_audit_sha256'], m['profile_binding']['audit_sha256'])
        self.assertEqual(m['profile_binding']['causal_sha256'], m['helper_files']['causal.py'])
        self.assertEqual(m['helper_files']['guest.py'], hashlib.sha256((root / 'tools/performance/guest.py').read_bytes()).hexdigest())
        for name, expected in m['observer_files'].items():
            raw = (root / name).read_bytes()
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            self.assertEqual(raw, subprocess.check_output(['git', '-C', str(root), 'show', runner.OBSERVER + ':' + name]))

    def test_exact_ten_fields_and_conditions(self):
        for group, field, replacement in [('image', 'bytes', True), ('image', 'bytes', float(runner.IMAGE['bytes'])),
                ('image', 'artifact_id', 1), ('conditions', 'vcpus', 2.0),
                ('image', 'sha256', 'f' * 64), ('conditions', 'vcpus', 4),
                ('conditions', 'boot_append', 'nomodeset'), ('conditions', 'precondition_seconds', 0)]:
            m = self.manifest(); m[group][field] = replacement
            with self.assertRaises(RuntimeError): runner.validate_manifest(m)

    def test_duplicate_and_nonfinite_json_reject(self):
        for raw in [b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}']:
            with self.assertRaises(RuntimeError): runner.read_json(raw)

    def test_real_emitter_reader_and_private_noise(self):
        raw = (json.dumps({'enum': 'fixed', 'ns': 123456789}) + '\n').encode()
        out = io.StringIO()
        with redirect_stdout(out): wrapper.emit_report(raw)
        actual, value = runner.extract_report(b'private ordinary UART text\n' + out.getvalue().encode() + b'private trailer\n')
        self.assertEqual(actual, raw); self.assertEqual(value['ns'], 123456789)

    def test_real_multi_piece_envelope_counterfactuals(self):
        raw = (json.dumps({'fixed': 'a' * 2000}) + '\n').encode()
        out = io.StringIO()
        with redirect_stdout(out): wrapper.emit_report(raw)
        original = out.getvalue().encode(); runner.extract_report(original)
        lines = original.splitlines()
        negatives = [original + original, b'\n'.join(lines[:1] + lines[2:]),
                     original.replace(b'DATA 1 ', b'DATA 0 '),
                     original.replace(hashlib.sha256(raw).hexdigest().encode(), b'f' * 64),
                     original.replace(b'DATA 0 ', b'DATA 00 ')]
        for bad in negatives:
            with self.assertRaises((RuntimeError, ValueError)): runner.extract_report(bad)

    def test_payload_byte_validation_no_exec(self):
        files = {'profile.py': b'fixed', 'guest.py': b'fixed_guest', 'causal.py': b'fixed_causal'}
        context = {'ready': True, 'modules': {k: hashlib.sha256(v).hexdigest()
                   for k, v in files.items() if k != 'profile.py'}}
        files['browser-startup-context.json'] = json.dumps(context).encode()
        payload = {'context': context, 'execution': {}, 'files': {name:
            {'base64': base64.b64encode(raw).decode(), 'bytes': len(raw),
             'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files.items()}}
        self.assertEqual(wrapper.staged_payload(payload), files)
        payload['files']['guest.py']['sha256'] = 'f' * 64
        with self.assertRaises(RuntimeError): wrapper.staged_payload(payload)

    def test_safe_file_real_symlink_and_fifo_reject(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); (root / 'regular').write_bytes(b'fixed')
            self.assertEqual(runner.safe_file(root, 'regular', 10), b'fixed')
            (root / 'link').symlink_to(root / 'regular'); os.mkfifo(root / 'fifo')
            for name in ('link', 'fifo'):
                with self.assertRaises((RuntimeError, OSError)): runner.safe_file(root, name, 10)

    def test_actual_owned_child_success_and_timeout_cleanup(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            runner.execute([sys.executable, '-c', 'print("private_stdout")'], root / 'success.log', root, dict(os.environ), 10)
            self.assertEqual((root / 'success.log').stat().st_mode & 0o777, 0o600)
            pidfile = root / 'pid'
            program = 'from pathlib import Path;import os,time;Path("pid").write_text(str(os.getpid()));time.sleep(30)'
            with self.assertRaisesRegex(RuntimeError, 'owned_command_or_cleanup_failed'):
                runner.execute([sys.executable, '-c', program], root / 'timeout.log', root, dict(os.environ), .2)
            pid = int(pidfile.read_text())
            with self.assertRaises(ProcessLookupError): os.kill(pid, 0)

    def test_template_cannot_run_without_host_payload(self):
        result = subprocess.run([sys.executable, '-B', str(HERE / 'guest-wrapper.py'), 'installed'],
                                capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        phase = b'arguments' if os.geteuid() != 0 else b'payload'
        self.assertEqual(result.stdout, b'ARCTIC-BROWSER-STARTUP-DIAGNOSTIC transport_failed\n'
                         b'ARCTIC-BROWSER-STARTUP-FAILURE guest ' + phase + b' guest_guard\n')
        self.assertEqual(result.stderr, b'')

    def test_actual_composer_freezes_original_sources_and_staging_modes(self):
        m = self.manifest(); root = HERE.parents[1]
        activation = {'schema': 'arctic-browser-diagnostic-activation-v1', 'execution_sha': 'a' * 40,
                      'parent_sha': 'b' * 40, 'run_id': 1, 'run_attempt': 1,
                      'release_acceptance': False, 'performance_acceptance': False}
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / 'wrapper.py'
            context, staged = runner.compose(root, m, activation, output)
            tree = ast.parse(output.read_bytes())
            assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'PAYLOAD' for target in node.targets))
            payload = ast.literal_eval(assignment.value)
            decoded = wrapper.staged_payload(payload)
            self.assertEqual(decoded['profile.py'], (root / 'tools/browser-main-library-source/profile.py').read_bytes())
            self.assertEqual(context['image'], runner.IMAGE)
            self.assertTrue(context['ready'])
            self.assertEqual(payload['execution'], activation)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            self.assertTrue(all(pin['mode'] == '0600' and pin['uid'] == 0 for pin in staged.values()))
            self.assertFalse(m['ready'])  # Disabled preparation does not activate this composition.
            self.assertEqual(m['profile_binding']['helper_leaf'], 'aade629162be39b378ce7e16233411947bf4d283')
            self.assertFalse((root / runner.MARKER).exists())  # Composition is not activation.

    def test_real_private_original_receipts_export_digests_only(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw); content = b'private arbitrary UART content\n'
            (root / 'boot-harness.log').write_bytes(content)
            actual = runner.private_original_receipts(root)
            self.assertEqual(actual, {'boot-harness.log': {'bytes': len(content),
                'sha256': hashlib.sha256(content).hexdigest(), 'uploaded': False}})
            self.assertNotIn('private arbitrary', json.dumps(actual))
            (root / 'image-fetch.log').symlink_to(root / 'boot-harness.log')
            with self.assertRaises(RuntimeError): runner.private_original_receipts(root)

    def test_actual_source_privacy_scanner_preserves_safe_fixture_and_rejects_secret(self):
        root = HERE.parents[1]; m = self.manifest()
        path = root / 'tools/native-functional/screen-evidence.py'
        # The runtime scanner is invoked from exact SourceA, not this execution checkout.
        raw = subprocess.check_output(['git', '-C', str(root), 'show', runner.SOURCE + ':tools/native-functional/screen-evidence.py'])
        self.assertEqual(hashlib.sha256(raw).hexdigest(), m['source_files']['tools/native-functional/screen-evidence.py'])
        scanner = types.ModuleType('exact_source_privacy_scanner'); scanner.__file__ = str(path)
        exec(compile(raw, str(path), 'exec'), scanner.__dict__)
        with tempfile.TemporaryDirectory() as value:
            temp = Path(value); good = temp / 'good'; good.mkdir()
            original = (json.dumps({'schema': 'source_only_control_fixture', 'image': runner.IMAGE,
                'conditions': runner.CONDITIONS, 'runtime_measured': False, 'qualification': False}) + '\n').encode()
            (good / 'host-receipt.json').write_bytes(original)
            scanner.screen_external(good, temp / 'screened')
            self.assertEqual((temp / 'screened/host-receipt.json').read_bytes(), original)
            bad = temp / 'bad'; bad.mkdir(); (bad / 'report.json').write_bytes(b'{"password":"synthetic-private-control"}\n')
            with self.assertRaises(RuntimeError), redirect_stdout(io.StringIO()):
                scanner.screen_external(bad, temp / 'rejected')
            self.assertFalse((temp / 'rejected').exists())


class FiniteFailureControls(unittest.TestCase):
    def test_actual_host_guard_code_requires_owned_source_frame(self):
        manifest = json.loads((HERE / 'execution-manifest.json').read_bytes())
        manifest['conditions']['vcpus'] = 4
        try: runner.validate_manifest(manifest)
        except RuntimeError as error: record = runner.finite_host_failure(error, 'activation')
        self.assertEqual(record, {'scope': 'host', 'phase': 'activation', 'reason': 'manifest_identity'})
        self.assertEqual(runner.finite_host_failure(RuntimeError('manifest_identity'), 'activation')['reason'],
                         'unclassified_exception')

    def test_actual_child_nonzero_keeps_private_output_and_classifies_command(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            with self.assertRaises(runner.OwnedCommandFailure) as caught:
                runner.execute([sys.executable, '-c', 'import sys;print("private transcript");sys.exit(7)'],
                    root / 'boot-harness.log', root, dict(os.environ), 10)
            record = runner.finite_host_failure(caught.exception, 'separate_diagnostic_boot')
            self.assertEqual(record, {'scope': 'host_command', 'phase': 'separate_diagnostic_boot',
                'command': 'nonzero', 'cleanup': []})
            self.assertNotIn('private', json.dumps(record))
            self.assertIn(b'private transcript', (root / 'boot-harness.log').read_bytes())

    def test_real_cancellation_at_Popen_retains_and_reaps_owned_child(self):
        children = []; original = subprocess.Popen
        def spawn(*args, **kwargs):
            child = original(*args, **kwargs); children.append(child)
            os.kill(os.getpid(), signal.SIGTERM)
            return child
        def interrupt(*_): raise InterruptedError('private cancel detail')
        old = signal.signal(signal.SIGTERM, interrupt)
        try:
            with tempfile.TemporaryDirectory() as value, patch.object(runner.subprocess, 'Popen', side_effect=spawn):
                root = Path(value)
                with self.assertRaises(runner.OwnedCommandFailure) as caught:
                    runner.execute([sys.executable, '-c', 'import time;time.sleep(30)'], root / 'boot-harness.log',
                        root, dict(os.environ), 10)
                record = runner.finite_host_failure(caught.exception, 'unknown')
                self.assertEqual(record['command'], 'interrupted'); self.assertEqual(record['cleanup'], [])
                self.assertEqual(len(children), 1)
                self.assertIsNotNone(children[0].poll())
                with self.assertRaises(ProcessLookupError): os.kill(children[0].pid, 0)
        finally: signal.signal(signal.SIGTERM, old)

    def test_cleanup_failure_still_rejects_a_successful_real_owned_child(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value); name = 'owned-private-control-name'
            with patch.object(runner.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)), \
                 patch.object(runner, 'capture', return_value=(name + '\n').encode()):
                with self.assertRaises(runner.OwnedCommandFailure) as caught:
                    runner.execute([sys.executable, '-c', 'pass'], root / 'boot-harness.log', root, dict(os.environ), 10, name)
            record = runner.finite_host_failure(caught.exception, 'unknown')
            self.assertEqual(record['command'], 'success')
            self.assertEqual(record['cleanup'], ['container_absence_unproved'])
            self.assertNotIn(name, json.dumps(record))

    def test_poisoned_host_records_and_exception_representations_never_export(self):
        poison = {'scope': 'host_command', 'phase': ['private'], 'command': 'private', 'cleanup': []}
        value = runner.finite_host_failure(runner.OwnedCommandFailure(poison), ['private'])
        self.assertEqual(value, {'scope': 'host', 'phase': 'unknown', 'reason': 'unclassified_exception'})
        class Hostile(RuntimeError):
            def __str__(self): raise AssertionError('private representation')
            def __repr__(self): raise AssertionError('private representation')
            def __getattribute__(self, name):
                if name in ('args', '__traceback__'): raise AssertionError('private field')
                return super().__getattribute__(name)
        self.assertEqual(runner.finite_host_failure(Hostile('private transcript'), 'separate_diagnostic_boot')['reason'],
                         'unclassified_exception')
        for item in ('private', [], True):
            with self.assertRaises(RuntimeError), redirect_stdout(io.StringIO()):
                wrapper.emit_finite_failure({'scope': 'guest', 'phase': item, 'reason': 'guest_guard'})
        out = io.StringIO()
        with patch.object(runner, 'finite_host_failure', side_effect=RuntimeError('private transcript')), redirect_stdout(out):
            value = runner.emit_host_failure(RuntimeError('private original'), 'separate_diagnostic_boot')
        self.assertEqual(value, {'scope': 'host', 'phase': 'unknown', 'reason': 'unclassified_exception'})
        self.assertNotIn('private', out.getvalue())

    def test_actual_guest_stderr_capture_forwards_only_one_validated_marker(self):
        root = HERE.parents[1]; profile_bytes = (root / 'tools/browser-main-library-source/profile.py').read_bytes()
        checksum = hashlib.sha256(profile_bytes).hexdigest(); original = subprocess.run
        private_bytes = b'private transcript and queried URL\nARCTIC-BROWSER-STARTUP-FAILURE collector runtime_inventory runtime_package_binding\n'
        def child(argv, **kwargs):
            self.assertEqual(argv, ['/usr/bin/python3', '-B', '/run/t/profile.py'])
            self.assertEqual(kwargs['timeout'], 900); self.assertIs(kwargs['stdout'], subprocess.DEVNULL)
            return original([sys.executable, '-c', 'import os;os.write(2,' + repr(private_bytes) + ');raise SystemExit(1)'], **kwargs)
        with tempfile.TemporaryDirectory() as value:
            private = Path(value) / 'private'; out = io.StringIO()
            with synthetic_root_metadata(private), patch.object(wrapper.subprocess, 'run', side_effect=child), redirect_stdout(out):
                with self.assertRaises(subprocess.CalledProcessError): wrapper.invoke_collector(profile_bytes, checksum, private)
            self.assertEqual(out.getvalue(), 'ARCTIC-BROWSER-STARTUP-FAILURE collector runtime_inventory runtime_package_binding\n')
            self.assertEqual((private / 'collector.stderr').read_bytes(), private_bytes)
            self.assertEqual(private.stat().st_mode & 0o777, 0o700)
            self.assertEqual((private / 'collector.stderr').stat().st_mode & 0o777, 0o600)

    def test_real_guest_timeout_reaps_child_and_large_stderr_stays_private(self):
        root = HERE.parents[1]; raw = (root / 'tools/browser-main-library-source/profile.py').read_bytes()
        original = subprocess.run
        with tempfile.TemporaryDirectory() as value:
            base = Path(value); pidfile = base / 'pid'
            script = 'from pathlib import Path;import os,time;Path(' + repr(str(pidfile)) + ').write_text(str(os.getpid()));os.write(2,b"private"*10000);time.sleep(30)'
            def child(argv, **kwargs):
                self.assertEqual(kwargs['timeout'], 900)
                kwargs['timeout'] = .2
                return original([sys.executable, '-c', script], **kwargs)
            out = io.StringIO()
            with synthetic_root_metadata(base / 'private'), patch.object(wrapper.subprocess, 'run', side_effect=child), redirect_stdout(out):
                with self.assertRaises(subprocess.TimeoutExpired):
                    wrapper.invoke_collector(raw, hashlib.sha256(raw).hexdigest(), base / 'private')
            self.assertEqual(out.getvalue(), 'ARCTIC-BROWSER-STARTUP-FAILURE collector unknown unclassified_exception\n')
            self.assertGreater((base / 'private/collector.stderr').stat().st_size, 4096)
            with self.assertRaises(ProcessLookupError): os.kill(int(pidfile.read_text()), 0)
            with patch.object(wrapper.subprocess, 'run', side_effect=AssertionError('no child before binding')):
                with self.assertRaises(RuntimeError): wrapper.invoke_collector(raw, 'f' * 64, base / 'never-created')
            self.assertFalse((base / 'never-created').exists())

    def test_actual_host_UART_projection_rejects_poison_duplicates_and_symlink(self):
        root = HERE.parents[1]; manifest = json.loads((HERE / 'execution-manifest.json').read_bytes())
        good = b'ARCTIC-BROWSER-STARTUP-FAILURE collector runtime_inventory runtime_package_binding\n'
        with tempfile.TemporaryDirectory() as value:
            work = Path(value); (work / 'diagnostic-boot').mkdir(); path = work / 'diagnostic-boot/serial-boot.log'
            path.write_bytes(b'private UART text\n' + good)
            got = runner.guest_failure_observation(root, work, manifest)
            self.assertEqual(got, {'status': 'valid_finite_markers', 'records': [
                {'scope': 'collector', 'phase': 'runtime_inventory', 'reason': 'runtime_package_binding'}]})
            self.assertNotIn('private', json.dumps(got))
            for bad in (good + good, good.replace(b'runtime_inventory', b'private'), good + b'ARCTIC-BROWSER-STARTUP-FAILURE guest staging private\n'):
                path.write_bytes(bad)
                self.assertEqual(runner.guest_failure_observation(root, work, manifest), {'status': 'invalid_finite_marker', 'records': []})
            path.unlink(); (work / 'other').write_bytes(good); path.symlink_to(work / 'other')
            self.assertEqual(runner.guest_failure_observation(root, work, manifest), {'status': 'unavailable', 'records': []})


if __name__ == '__main__': unittest.main(verbosity=2)
