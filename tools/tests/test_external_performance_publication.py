"""Frozen performance publication source, mode and receipt failure controls."""
import copy
import hashlib
import importlib.util
import json
import io
import os
import py_compile
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
import zipfile
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P = load('external_publication', ROOT / 'tools/qualified-release/prepare.py')
C = load('external_plan_composer', ROOT / 'tools/performance/compose-plan.py')


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


def initialize(root, files):
    git(root, 'init', '-q')
    git(root, 'config', 'user.name', 'Arctic publication control')
    git(root, 'config', 'user.email', 'control@example.invalid')
    for name, data in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(data)
    git(root, 'add', '.')
    git(root, 'commit', '-qm', 'Frozen source control')
    return git(root, 'rev-parse', 'HEAD')


class ComposerSourceControls(unittest.TestCase):
    def test_checkout_rejects_wrong_source_dirty_untracked_and_nested_roots(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            head = initialize(root, {'shell/AppsService.qml': 'image catalog\n'})
            self.assertEqual(C.checkout(root, head), root)
            with self.assertRaisesRegex(RuntimeError, 'source checkout differs'):
                C.checkout(root, 'a' * 40)
            with self.assertRaisesRegex(RuntimeError, 'exact Git checkout root'):
                C.checkout(root / 'shell', head)
            (root / 'shell/AppsService.qml').write_text('unreviewed catalog\n')
            with self.assertRaisesRegex(RuntimeError, 'not clean'):
                C.checkout(root, head)
            git(root, 'checkout', '--', 'shell/AppsService.qml')
            (root / 'unreviewed.py').write_text('extra helper\n')
            with self.assertRaisesRegex(RuntimeError, 'not clean'):
                C.checkout(root, head)

    def test_duplicate_and_nonfinite_image_pin_json_is_rejected(self):
        for raw in ('{"source_sha":"a","source_sha":"b"}',
                    '{"bytes":NaN}', '{"bytes":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises((RuntimeError, ValueError)):
                C.image_pin(raw)

    def test_hidden_worktree_edits_and_symlink_payloads_cannot_supply_plan_hashes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            name = 'shell/AppsService.qml'
            initialize(root, {name: 'frozen catalog\n'})
            expected = hashlib.sha256((root / name).read_bytes()).hexdigest()
            self.assertEqual(C.tracked_hashes(root, {name}), {name: expected})
            git(root, 'update-index', '--skip-worktree', name)
            (root / name).write_text('hidden dirty catalog\n')
            self.assertEqual(git(root, 'status', '--porcelain'), '')
            with self.assertRaisesRegex(RuntimeError, 'tracked blob'):
                C.tracked_hashes(root, {name})
            (root / name).unlink()
            (root / name).symlink_to('/etc/hosts')
            with self.assertRaisesRegex(RuntimeError, 'Unsafe or missing'):
                C.tracked_hashes(root, {name})


class FullComposerControls(unittest.TestCase):
    def fixture(self, folder, stale=False):
        contract_path = ROOT / 'tools/performance/contract.py'
        contract = load('composer_contract_fixture', contract_path)
        source, execution = folder / 'source', folder / 'execution'
        source.mkdir()
        execution.mkdir()
        source_files = {name: (ROOT / name).read_text() for name in contract.CANDIDATE_SOURCE_FILES}
        image_source = initialize(source, source_files)
        execution_files = {name: '# Frozen fixture source ' + name + '\n'
                           for name in contract.EXECUTION_FILES}
        for name in ('tools/performance/contract.py', 'tools/performance/compose-plan.py',
                     'tools/performance/guest.py', 'tools/performance/causal.py',
                     'tools/performance/compare.py', 'tools/performance/fixtures/v1.2-offline.toml'):
            execution_files[name] = (ROOT / name).read_text()
        execution_files['.gitignore'] = '__pycache__/\n'
        initialize(execution, execution_files)
        if stale:
            path = execution / 'tools/performance/contract.py'
            good = path.read_bytes()
            bad = good.replace(b'frozen-external-paired-v1', b'frozen-external-paired-v0')
            self.assertNotEqual(good, bad)
            stamp = path.stat()
            path.write_bytes(bad)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            py_compile.compile(str(path), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            path.write_bytes(good)
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            self.assertEqual(load('old_composer_contract', path).MODE, 'frozen-external-paired-v0')
        image = dict(source_sha=image_source, sha256='a' * 64, bytes=1_500_000_000,
                     producer_mode=P.EXTERNAL_PERFORMANCE_MODE, producer_receipt_sha256='b' * 64)
        return source, execution, image, contract

    def test_ready_is_explicit_and_candidate_hashes_come_from_the_image_checkout(self):
        with tempfile.TemporaryDirectory() as temp:
            source, execution, image, contract = self.fixture(Path(temp))
            plan = C.compose(source, execution, image)
            self.assertFalse(plan['ready'])
            self.assertFalse(plan['release_acceptance'])
            self.assertEqual(plan['candidate_source_files'],
                {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                 for name in contract.CANDIDATE_SOURCE_FILES})
            self.assertNotEqual(plan['candidate_source_files']['shell/AppsService.qml'],
                                hashlib.sha256(b'execution-only catalog\n').hexdigest())
            self.assertTrue(C.compose(source, execution, image, ready=True)['ready'])
            wrong_image = dict(image, source_sha=git(execution, 'rev-parse', 'HEAD'))
            with self.assertRaisesRegex(RuntimeError, 'source checkout differs'):
                C.compose(source, execution, wrong_image)
            # A clean execution branch may contain another catalog; it must not
            # replace the exact image's payload source when the plan is frozen.
            changed = execution / 'shell/AppsService.qml'
            changed.parent.mkdir(parents=True)
            changed.write_text('execution-only catalog\n')
            git(execution, 'add', '.')
            git(execution, 'commit', '-qm', 'Different execution-only catalog')
            self.assertEqual(C.compose(source, execution, image)['candidate_source_files'],
                             plan['candidate_source_files'])

    def test_ignored_stale_bytecode_is_bypassed_in_the_real_composer_path(self):
        with tempfile.TemporaryDirectory() as temp:
            source, execution, image, _ = self.fixture(Path(temp), stale=True)
            self.assertEqual(git(execution, 'status', '--porcelain'), '')
            self.assertEqual(C.compose(source, execution, image)['performance_mode'], P.EXTERNAL_PERFORMANCE_MODE)


class PublisherSourceReceiptControls(unittest.TestCase):
    def fixture(self, folder):
        composer = FullComposerControls()
        source, execution, image, _ = composer.fixture(folder)
        git(execution, 'fetch', '--quiet', str(source), image['source_sha'])
        plan = C.compose(source, execution, image, ready=True)
        plan_raw = (json.dumps(plan, indent=2) + '\n').encode()
        path = execution / P.EXTERNAL_PERFORMANCE_PLAN
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(plan_raw)
        git(execution, 'add', '.')
        git(execution, 'commit', '-qm', 'Reviewed plan')
        parent = git(execution, 'rev-parse', 'HEAD')
        marker = execution / P.EXTERNAL_PERFORMANCE_MARKER
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(parent + '\n')
        git(execution, 'add', '.')
        git(execution, 'commit', '-qm', 'Owned performance activation')
        receipt_raw = b'{}\n'
        pin = dict(run_id=200, source_sha=git(execution, 'rev-parse', 'HEAD'),
                   reviewed_parent_sha=parent, performance_mode=P.EXTERNAL_PERFORMANCE_MODE,
                   plan_sha256=hashlib.sha256(plan_raw).hexdigest(),
                   execution_json_sha256=hashlib.sha256(receipt_raw).hexdigest())
        return execution, dict(image=image, performance=pin), receipt_raw

    def archive(self, execution, receipt):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            archive.writestr('execution.json', execution)
            archive.writestr('producer-receipt.json', receipt)
        data.seek(0)
        return zipfile.ZipFile(data)

    def test_exact_git_plan_and_execution_receipt_pins_precede_replay(self):
        with tempfile.TemporaryDirectory() as temp:
            execution, manifest, receipt = self.fixture(Path(temp))
            fetch = SimpleNamespace(read_receipt=Mock())
            with patch.object(P, 'ROOT', execution), self.archive(receipt, b'{}') as archive:
                wrong = copy.deepcopy(manifest)
                wrong['performance']['plan_sha256'] = '0' * 64
                with self.assertRaisesRegex(RuntimeError, 'plan differs'):
                    P.performance_proof(archive, wrong, fetch)
                wrong = copy.deepcopy(manifest)
                wrong['performance']['execution_json_sha256'] = '0' * 64
                with self.assertRaisesRegex(RuntimeError, 'execution receipt differs'):
                    P.performance_proof(archive, wrong, fetch)
            fetch.read_receipt.assert_not_called()

    def test_helper_drift_never_executes_and_oversized_receipt_is_rejected_before_read(self):
        with tempfile.TemporaryDirectory() as temp:
            execution, manifest, receipt = self.fixture(Path(temp))
            fetch = SimpleNamespace(read_receipt=Mock())
            helper = execution / 'tools/performance/compare.py'
            original = helper.read_bytes()
            sentinel = execution / 'wrong-helper-executed'
            helper.write_text('from pathlib import Path\nPath(' + repr(str(sentinel)) + ').touch()\n')
            with patch.object(P, 'ROOT', execution), self.archive(receipt, b'X' * 32769) as archive:
                with self.assertRaisesRegex(RuntimeError, 'helper drift'):
                    P.performance_proof(archive, manifest, fetch)
                self.assertFalse(sentinel.exists())
                helper.write_bytes(original)
                with patch.object(archive, 'read', wraps=archive.read) as read:
                    with self.assertRaisesRegex(RuntimeError, 'Oversized external producer receipt'):
                        P.performance_proof(archive, manifest, fetch)
                    self.assertNotIn(('producer-receipt.json',), [call.args for call in read.call_args_list])
            fetch.read_receipt.assert_not_called()


class PublisherReplayControls(unittest.TestCase):
    def fixture(self):
        # The actual production replay is used below. Only the remote Git object
        # transport is substituted; real immutable Git/source controls are above.
        with patch.object(sys, 'path', [str(ROOT / 'tools/tests'), *sys.path]):
            fixture = load('publisher_original_serial_fixture', ROOT / 'tools/tests/performance_external_fixture.py')
        entries, metadata = fixture.fixture()
        plan = metadata['plan']
        plan['execution_files'] = {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                   for name in fixture.contract.EXECUTION_FILES}
        plan_raw = fixture.encoded(plan)
        old_sha, new_sha = metadata['plan_sha256'], hashlib.sha256(plan_raw).hexdigest()
        metadata['plan_sha256'] = new_sha
        for name in list(entries):
            entries[name] = entries[name].replace(old_sha.encode(), new_sha.encode())
        execution = json.loads(entries['execution.json'])
        execution['execution_files'] = plan['execution_files']
        entries['execution.json'] = fixture.encoded(execution)
        # Context hashes are part of full comparison output, so recompute the
        # fixture after freezing actual local helper bytes; never mock comparison.
        runs = dict(baseline=[], candidate=[])
        with tempfile.TemporaryDirectory() as temp:
            for name, boot in fixture.contract.ORDER:
                path = Path(temp) / (name + str(boot) + '.log')
                path.write_bytes(entries[f'runs/{name}/{boot}/serial-boot.log'])
                runs[name].append(fixture.comparator.read_run(path, strict=True))
        entries['comparison.json'] = fixture.encoded(fixture.comparator.compare_checked(runs,
            candidate_commit=plan['image']['source_sha'][:7],
            candidate_catalog_sha256=plan['candidate_source_files']['shell/AppsService.qml'],
            candidate_battery_sha256=plan['candidate_source_files']['shell/BatteryService.qml']))
        fixture.reseal(entries)
        pin = dict(run_id=metadata['execution_run_id'], source_sha=metadata['execution_source_sha'],
                   reviewed_parent_sha=metadata['reviewed_parent_sha'], performance_mode=P.EXTERNAL_PERFORMANCE_MODE,
                   plan_sha256=new_sha, execution_json_sha256=hashlib.sha256(entries['execution.json']).hexdigest())
        manifest = dict(image=plan['image'], performance=pin)
        def source_hash(ref, name):
            if ref == metadata['execution_source_sha']:
                return plan['execution_files'][name]
            self.assertEqual(ref, plan['image']['source_sha'])
            return plan['candidate_source_files'][name]
        def source_bytes(ref, name):
            self.assertEqual(ref, metadata['execution_source_sha'])
            return plan_raw if name == P.EXTERNAL_PERFORMANCE_PLAN else (ROOT / name).read_bytes()
        return fixture, entries, manifest, source_hash, source_bytes

    def proof(self, fixture, entries, manifest, source_hash, source_bytes):
        fetch = load('publisher_real_fetch', ROOT / 'tools/native-functional/fetch-image.py')
        with patch.object(P, 'source_hash', side_effect=source_hash), \
             patch.object(P, 'source_bytes', side_effect=source_bytes), fixture.archive(entries) as archive:
            return P.performance_proof(archive, manifest, fetch)

    def test_all_six_complete_original_serials_are_replayed_by_the_real_comparator(self):
        fixture, entries, manifest, source_hash, source_bytes = self.fixture()
        proof = self.proof(fixture, entries, manifest, source_hash, source_bytes)
        self.assertEqual(proof['replay']['original_serials_replayed'], 6)
        self.assertEqual(proof['replay']['comparison'], json.loads(entries['comparison.json']))
        self.assertEqual(proof['replay']['image_source_sha'], manifest['image']['source_sha'])
        self.assertNotEqual(proof['replay']['execution_source_sha'], manifest['image']['source_sha'])
        self.assertFalse(proof['replay']['release_acceptance'])

    def test_cherry_picked_redacted_mutated_and_recomputed_invalid_inputs_never_qualify(self):
        fixture, original, manifest, source_hash, source_bytes = self.fixture()
        serial = 'runs/candidate/1/serial-boot.log'
        for fault in ('missing_boot', 'changed_original', 'redacted', 'duplicate_done',
                      'missing_uart_end', 'wrong_observer', 'different_image', 'different_profile',
                      'duplicate_boot_id', 'comparison_metric', 'boolean_metric', 'precision_failed',
                      'trace_loss', 'wide_native_bracket', 'app_regression', 'boot_regression', 'missing_private_sample'):
            entries, pin = copy.deepcopy(original), copy.deepcopy(manifest)
            if fault == 'missing_boot':
                del entries[serial]
            elif fault == 'changed_original':
                entries[serial] += b'changed after measurement\n'
            elif fault == 'redacted':
                screen = json.loads(entries['upload-screening.json'])
                screen['files'][serial]['redactions'] = 1
                entries['upload-screening.json'] = fixture.encoded(screen)
            elif fault == 'duplicate_done':
                entries[serial] += b'ARCTIC-PERFORMANCE {"stage":"installed","check":"done","value":true}\n'
            elif fault == 'missing_uart_end':
                entries[serial] = entries[serial].replace(b'ARCTIC-COLLECT-END', b'END-REMOVED')
            elif fault == 'wrong_observer':
                entries[serial] = entries[serial].replace(
                    fixture.contract.observer_hashes(ROOT)['source_sha256'].encode(), b'0' * 64)
            elif fault in ('different_image', 'different_profile'):
                context = json.loads(entries['runs/candidate/1/performance-context.json'])
                context['iso_sha256' if fault == 'different_image' else 'install_profile_sha256'] = '0' * 64
                entries['runs/candidate/1/performance-context.json'] = fixture.encoded(context)
            elif fault == 'duplicate_boot_id':
                entries[serial] = entries[serial].replace(b'00000000-0000-0000-0000-000000000002',
                                                        b'00000000-0000-0000-0000-000000000001')
            elif fault in ('trace_loss', 'wide_native_bracket', 'app_regression', 'boot_regression', 'missing_private_sample'):
                targets = ([f'runs/candidate/{boot}/serial-boot.log' for boot in (1, 2, 3)]
                           if fault in ('app_regression', 'boot_regression') else [serial])
                for target in targets:
                    lines = []
                    for line in entries[target].decode().splitlines():
                        if line.startswith('ARCTIC-PERFORMANCE '):
                            record = json.loads(line.split(' ', 1)[1])
                            check, value = record['check'], record['value']
                            if fault == 'trace_loss' and check == 'startup_role_terminal_cold_seconds':
                                value['observation_bounds'][0]['causal_lower_bound']['loss_counts']['cpu0']['overrun'] = 1
                            elif fault == 'wide_native_bracket' and check == 'startup_role_terminal_cold_seconds':
                                value['observation_bounds'][0] = fixture.roles.causal_bound(.03, .04, ('foot',))
                            elif fault == 'app_regression' and check == 'fish_seconds':
                                value['median'] = .330001  # Baseline .3; candidate median exceeds original 10%.
                            elif fault == 'boot_regression' and check == 'boot':
                                value['analyze'] = 'Startup finished = 11.00001s'  # Baseline 10 seconds.
                            elif fault == 'missing_private_sample' and check == 'idle_samples':
                                value[0].pop('process_private_bytes')
                            line = 'ARCTIC-PERFORMANCE ' + json.dumps(record)
                        lines.append(line)
                    entries[target] = ('\n'.join(lines) + '\n').encode()
            else:
                comparison = json.loads(entries['comparison.json'])
                if fault == 'comparison_metric':
                    comparison['metrics'][0]['median']['candidate'] -= .001
                elif fault == 'boolean_metric':
                    comparison['idle_cpu_validity']['candidate'][0]['temporary_worker_cpu'][0]['ticks_delta'] = True
                else:
                    comparison['measurement_precision']['valid'] = False
                entries['comparison.json'] = fixture.encoded(comparison)
            if fault in ('trace_loss', 'wide_native_bracket', 'app_regression', 'boot_regression'):
                runs = dict(baseline=[], candidate=[])
                with tempfile.TemporaryDirectory() as temp:
                    for image, boot in fixture.contract.ORDER:
                        path = Path(temp) / (image + str(boot) + '.log')
                        path.write_bytes(entries[f'runs/{image}/{boot}/serial-boot.log'])
                        runs[image].append(fixture.comparator.read_run(path, strict=True))
                result = fixture.comparator.compare_checked(runs,
                    candidate_commit=manifest['image']['source_sha'][:7],
                    candidate_catalog_sha256='b' * 64, candidate_battery_sha256='9' * 64)
                self.assertEqual(result['status'], 'regression_gate_failed'
                    if fault in ('app_regression', 'boot_regression') else 'measurement_precision_gate_failed')
                # Even a correctly recomputed full FAILED report cannot qualify
                # by keeping the outer success marker from another execution.
                entries['comparison.json'] = fixture.encoded(result)
            if fault not in ('changed_original', 'redacted'):
                fixture.reseal(entries)
                pin['performance']['execution_json_sha256'] = hashlib.sha256(entries['execution.json']).hexdigest()
            with self.subTest(fault=fault), self.assertRaises((ValueError, RuntimeError)):
                self.proof(fixture, entries, pin, source_hash, source_bytes)


class PublisherModeControls(unittest.TestCase):
    def manifest(self):
        return dict(image=dict(run_id=100, source_sha='a' * 40, producer_mode=P.EXTERNAL_PERFORMANCE_MODE),
                    performance=dict(run_id=200, source_sha='b' * 40, performance_mode=P.EXTERNAL_PERFORMANCE_MODE,
                        reviewed_parent_sha='c' * 40, plan_sha256='d' * 64, execution_json_sha256='e' * 64,
                        artifact_id=300, archive_bytes=100, archive_sha256='f' * 64))

    def test_mode_switch_is_explicit_and_mutually_exclusive(self):
        manifest = self.manifest()
        self.assertEqual(P.performance_mode(manifest), P.EXTERNAL_PERFORMANCE_MODE)
        for target, key, value in (('image', 'producer_mode', 'unknown'),
                ('performance', 'performance_mode', P.LEGACY_PERFORMANCE_MODE),
                ('image', 'producer_mode', P.LEGACY_PERFORMANCE_MODE)):
            bad = copy.deepcopy(manifest)
            bad[target][key] = value
            with self.assertRaises(RuntimeError):
                P.performance_mode(bad)
        legacy = dict(image={}, performance={})
        self.assertEqual(P.performance_mode(legacy), P.LEGACY_PERFORMANCE_MODE)
        self.assertEqual(P.publication_files(legacy), P.FILES)
        manifest['performance'].pop('performance_mode')
        with self.assertRaisesRegex(RuntimeError, 'modes differ'):
            P.performance_mode(manifest)

    def test_validator_hash_is_checked_before_importing_any_contract_code(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'tools/performance/contract.py'
            path.parent.mkdir(parents=True)
            sentinel = root / 'contract-was-executed'
            path.write_text('from pathlib import Path\nPath(' + repr(str(sentinel)) + ').touch()\nEXECUTION_FILES=set()\n')
            manifest = self.manifest() | dict(execution_files={'tools/performance/contract.py': '0' * 64})
            with patch.object(P, 'ROOT', root):
                for expected in (None, 'invalid', '0' * 64):
                    with self.assertRaisesRegex(RuntimeError, 'reviewed source'):
                        P.performance_contract(expected)
                with self.assertRaisesRegex(RuntimeError, 'reviewed source'):
                    P.publication_files(manifest)
            self.assertFalse(sentinel.exists())

    def test_stale_valid_bytecode_cannot_replace_the_reviewed_validator_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'tools/performance/contract.py'
            path.parent.mkdir(parents=True)
            path.write_text("EXECUTION_FILES={'old'}\n")
            stamp = path.stat()
            py_compile.compile(str(path), doraise=True,
                               invalidation_mode=py_compile.PycInvalidationMode.TIMESTAMP)
            path.write_text("EXECUTION_FILES={'new'}\n")
            os.utime(path, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
            # Demonstrate the real import cache hazard, not a mocked loader.
            self.assertEqual(load('stale_contract_control', path).EXECUTION_FILES, {'old'})
            expected = hashlib.sha256(path.read_bytes()).hexdigest()
            with patch.object(P, 'ROOT', root):
                self.assertEqual(P.performance_contract(expected).EXECUTION_FILES, {'new'})

    def test_failed_external_producer_prevents_artifact_or_lane_acceptance(self):
        fetch = SimpleNamespace(validate_external_producer_steps=Mock(side_effect=RuntimeError('producer failed')))
        with patch.object(P, 'api') as api, self.assertRaisesRegex(RuntimeError, 'producer failed'):
            P.validate_performance_lane(self.manifest(), [], fetch)
        api.assert_not_called()

    def test_external_lane_requires_first_attempt_success_and_marker_only_child(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = initialize(root, {'frozen-helper.py': 'reviewed\n'})
            marker = root / P.EXTERNAL_PERFORMANCE_MARKER
            marker.parent.mkdir(parents=True)
            marker.write_text(parent + '\n')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'Owned marker')
            source = git(root, 'rev-parse', 'HEAD')
            manifest = self.manifest()
            manifest['performance'].update(source_sha=source, reviewed_parent_sha=parent)
            pin = manifest['performance']
            run = dict(head_sha=source, path=P.EXTERNAL_PERFORMANCE_WORKFLOW, event='push', run_attempt=1,
                       status='completed', conclusion='success', head_branch='codex/qualification-dispatch-20261008')
            artifact = dict(workflow_run=dict(id=pin['run_id'], head_sha=source), name='external-paired-performance',
                            expired=False, size_in_bytes=100, digest='sha256:' + 'f' * 64)
            fetch = SimpleNamespace(validate_external_producer_steps=Mock())
            def api(path):
                return artifact if '/artifacts/' in path else run
            with patch.object(P, 'ROOT', root), patch.object(P, 'api', side_effect=api):
                self.assertEqual(P.validate_performance_lane(manifest, [], fetch), artifact)
                for key, value in (('run_attempt', 2), ('run_attempt', True), ('conclusion', 'failure'), ('status', 'in_progress'),
                                   ('event', 'workflow_dispatch'), ('head_sha', 'f' * 40),
                                   ('head_branch', 'main'), ('path', '.github/workflows/iso.yml')):
                    original = run[key]
                    run[key] = value
                    with self.subTest(key=key), self.assertRaises(RuntimeError):
                        P.validate_performance_lane(manifest, [], fetch)
                    run[key] = original
                marker.write_text(parent)  # Same apparent value, not byte-exact marker.
                git(root, 'add', '.')
                git(root, 'commit', '-qm', 'Missing marker newline')
                run['head_sha'] = pin['source_sha'] = git(root, 'rev-parse', 'HEAD')
                artifact['workflow_run']['head_sha'] = pin['source_sha']
                pin['reviewed_parent_sha'] = source
                with self.assertRaisesRegex(RuntimeError, 'marker-only child'):
                    P.validate_performance_lane(manifest, [], fetch)
                parent = git(root, 'rev-parse', 'HEAD')
                marker.write_text(parent + '\n')
                (root / 'frozen-helper.py').write_text('unreviewed extra source\n')
                git(root, 'add', '.')
                git(root, 'commit', '-qm', 'Marker plus source drift')
                run['head_sha'] = pin['source_sha'] = git(root, 'rev-parse', 'HEAD')
                artifact['workflow_run']['head_sha'] = pin['source_sha']
                pin['reviewed_parent_sha'] = parent
                with self.assertRaisesRegex(RuntimeError, 'marker-only child'):
                    P.validate_performance_lane(manifest, [], fetch)


if __name__ == '__main__':
    unittest.main()
