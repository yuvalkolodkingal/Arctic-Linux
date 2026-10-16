#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('dictation_failure_reader', HERE / 'read.py')
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


class Contract:
    @staticmethod
    def validate(report, expected, require_passed=False, fixture_manifest=None):
        assert report['context'] == expected
        assert require_passed is False
        assert fixture_manifest
        return {'contract_valid': True}


class SafeReaderTests(unittest.TestCase):
    def artifact(self, pin):
        return {'id': pin['id'], 'name': pin['name'], 'expired': False,
                'size_in_bytes': pin['bytes'], 'digest': 'sha256:' + pin['sha256'],
                'workflow_run': {'id': reader.RUN_ID, 'head_sha': reader.SOURCE_SHA,
                    'head_branch': reader.QUALIFICATION_BRANCH,
                    'repository_id': reader.REPOSITORY_ID,
                    'head_repository_id': reader.REPOSITORY_ID}}

    def gate(self, name, status='passed', code='observed', observations=None):
        return {'id': name, 'status': status, 'code': code,
                'observations': observations or {}, 'evidence_kind': 'actual-session'}

    def report(self, profile, fixture_sha):
        installation = '01234567-89ab-cdef-0123-456789abcdef'
        context = dict(reader.CONTEXT_PINS, schema='arctic-voxtype-context-v3',
                       phase='online-installed', hardware_profile=profile,
                       installation_id=installation, fixture_manifest_sha256=fixture_sha)
        gates = [
            self.gate(reader.GATE_NAMES['english'], 'failed',
                      'gate-cpu-english-transcription-insertion-timeout', {'failure_stage': 11}),
            self.gate(reader.GATE_NAMES['hebrew'], observations={'count': 5}),
            self.gate(reader.GATE_NAMES['gpu'], 'failed',
                      'gate-gpu-failure-explicit-cpu-fallback-invalid', {'failure_stage': 210}),
            self.gate(reader.GATE_NAMES['cleanup'], observations={'file_count': 0, 'drained': True}),
            self.gate(reader.GATE_NAMES['privacy'], 'failed',
                      'gate-transcript-log-notification-leak-scan-invalid'),
        ]
        return {'context': context, 'boot_id': '11111111-2222-3333-4444-555555555555',
                'status': 'failed', 'gates': gates}

    def archive(self, profile='turbo-q5-v3', extra=None):
        fixture = b'fixed public fixture manifest for unit test'
        fixture_sha = hashlib.sha256(fixture).hexdigest()
        report = self.report(profile, fixture_sha)
        live = dict(report)
        live['context'] = dict(report['context'], phase='live')
        live['boot_id'] = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee'
        live['status'] = 'passed'
        indicator = b'\x89PNG\r\n\x1a\nunit-test-pixels'
        installation = report['context']['installation_id']
        raw_report = json.dumps(report, sort_keys=True).encode()
        raw_live = json.dumps(live, sort_keys=True).encode()
        proof = {
            'path': 'dictation-indicator-online-installed.png',
            'sha256': hashlib.sha256(indicator).hexdigest(),
            'iso_sha256': reader.IMAGE['sha256'], 'installation_id': installation,
            'request': {'boot_id': report['boot_id'], 'installation_id': installation,
                        'phase': 'online-installed', 'desktop_uid': 1000,
                        'receiver_empty': True, 'capture_nonce': 'a' * 32},
        }
        state = {
            'schema': 'arctic-voxtype-execution-v3', 'hardware_profile': profile,
            'status': 'failed_or_unrun', 'release_acceptance': False,
            'image': reader.IMAGE, 'execution_checker_head': reader.SOURCE_SHA,
            'fixture_manifest_sha256': fixture_sha,
            'reports': {
                'online-installed-live': {'path': 'online-installed-live.json',
                    'sha256': hashlib.sha256(raw_live).hexdigest(), 'phase': 'live',
                    'installation_id': installation, 'boot_id': live['boot_id'], 'status': 'passed'},
            },
            'installations': {'online': installation,
                              'offline': '99999999-8888-7777-6666-555555555555'},
            'indicators': {'online-installed': proof}, 'recovery_screens': {},
            'recorded_at_utc': '2026-10-16T02:00:00+00:00',
            'vm_tool_image_id': 'b' * 64, 'current_phase': 'online-installed',
            'error': 'Qualification failed; inspect private Actions harness logs',
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            archive.writestr('execution.json', json.dumps(state, sort_keys=True))
            archive.writestr('fixtures.json', fixture)
            archive.writestr('online-installed-live.json', raw_live)
            archive.writestr('online-installed.json', raw_report)
            archive.writestr('dictation-indicator-online-installed.png', indicator)
            if extra:
                archive.writestr(extra, b'private-content')
        return output.getvalue(), fixture_sha

    def projection(self):
        raw, fixture_sha = self.archive()
        pin = {'id': reader.ARTIFACT_ID,
               'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        with mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                mock.patch.dict(reader.CONTEXT_PINS,
                                {'fixture_manifest_sha256': fixture_sha}):
            result = reader.inspect_artifact(
                'turbo-q5-v3', pin, self.artifact(pin), raw, Contract)
        return {'schema': 'arctic-dictation-safe-diagnostic-v1',
                'run_id': reader.RUN_ID, 'release_acceptance': False,
                'profiles': {'turbo-q5-v3': result}}

    def recovery_bundle(self, desktop_uid=1000):
        installation = '01234567-89ab-cdef-0123-456789abcdef'
        boot = '11111111-2222-3333-4444-555555555555'
        value = {}
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for index, (stage, name) in enumerate(reader.RECOVERY_MEMBERS.items()):
                image = b'\x89PNG\r\n\x1a\nrecovery-' + stage.encode()
                archive.writestr(name, image)
                value[stage] = {
                    'path': name, 'sha256': hashlib.sha256(image).hexdigest(),
                    'iso_sha256': reader.IMAGE['sha256'],
                    'installation_id': installation,
                    'request': {
                        'boot_id': boot, 'installation_id': installation,
                        'phase': 'online-installed', 'desktop_uid': desktop_uid,
                        'receiver_empty': True, 'stage': stage,
                        'state': 'error' if stage == 'gpu_failure' else 'ready',
                        'backend': 'cpu', 'language': 'he',
                        'capture_nonce': str(index + 1) * 32,
                    },
                }
        return value, output.getvalue(), installation, {'boot_id': boot}

    def test_duplicate_json_and_nonfinite_values_are_rejected(self):
        with self.assertRaises(RuntimeError):
            reader.strict_json(b'{"x":1,"x":2}', 100)
        with self.assertRaises(RuntimeError):
            reader.strict_json(b'{"x":NaN}', 100)

    def test_staged_projection_admits_only_closed_numeric_inventory(self):
        gate = self.gate(reader.GATE_NAMES['gpu'], 'failed',
                         'gate-gpu-failure-explicit-cpu-fallback-timeout',
                         {'failure_stage': 214})
        self.assertEqual(reader.staged_gate(gate, set(range(201, 215))),
                         {'status': 'failed', 'family': 'timeout',
                          'stage_present': True, 'stage': 214,
                          'substage_present': False, 'substage': 0,
                          'returncode_present': False, 'returncode': 0})
        gate['observations']['failure_stage'] = 215
        with self.assertRaises(RuntimeError):
            reader.staged_gate(gate, set(range(201, 215)))

        gate['observations'] = {'failure_stage': 6, 'failure_substage': 608}
        self.assertEqual(reader.staged_gate(gate, set(range(1, 20)))['substage'], 608)
        gate['observations']['failure_substage'] = 613
        with self.assertRaises(RuntimeError):
            reader.staged_gate(gate, set(range(1, 20)))

        gate['observations']['failure_stage'] = 201
        gate['code'] = 'private arbitrary error'
        with self.assertRaises(RuntimeError):
            reader.staged_gate(gate, set(range(201, 215)))

    def test_exact_artifact_projects_stages_and_never_raw_content(self):
        raw, fixture_sha = self.archive()
        pin = {'id': reader.ARTIFACT_ID, 'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        artifact = self.artifact(pin)
        with mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                mock.patch.dict(reader.CONTEXT_PINS, {'fixture_manifest_sha256': fixture_sha}):
            result = reader.inspect_artifact('turbo-q5-v3', pin, artifact, raw, Contract)
        self.assertEqual(result['english']['stage'], 11)
        self.assertEqual(result['gpu']['stage'], 210)
        self.assertEqual(result['privacy']['family'], 'invalid')
        self.assertFalse(result['privacy']['matched_present'])
        self.assertEqual(result['cleanup']['file_count'], 0)
        self.assertFalse(result['recovery_receipts']['entry_present'])
        self.assertEqual(result['artifact_inventory'], sorted(reader.BASE_MEMBERS))
        report = {'schema': 'arctic-dictation-safe-diagnostic-v1',
                  'run_id': reader.RUN_ID, 'release_acceptance': False,
                  'profiles': {'turbo-q5-v3': result}}
        stream = io.StringIO()
        reader.emit(report, stream)
        emitted = stream.getvalue()
        self.assertTrue(emitted.startswith('ARCTIC-DICTATION-SAFE-DIAGNOSTIC='))
        self.assertNotIn('private-content', emitted)
        self.assertNotIn('fixture manifest', emitted)
        self.assertNotIn(reader.IMAGE['sha256'], emitted)

    def test_unknown_archive_member_is_rejected_without_reading_it(self):
        raw, fixture_sha = self.archive(extra='private.log')
        pin = {'id': reader.ARTIFACT_ID, 'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        artifact = self.artifact(pin)
        with mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                mock.patch.dict(reader.CONTEXT_PINS, {'fixture_manifest_sha256': fixture_sha}), \
                self.assertRaises(RuntimeError):
            reader.inspect_artifact('turbo-q5-v3', pin, artifact, raw, Contract)


    def test_run_pins_exact_attempt_source_workflow_and_turbo_job(self):
        run = {'id': reader.RUN_ID, 'run_attempt': reader.RUN_ATTEMPT,
               'workflow_id': reader.WORKFLOW_ID, 'name': reader.WORKFLOW_NAME,
               'head_sha': reader.SOURCE_SHA,
               'head_branch': reader.QUALIFICATION_BRANCH,
               'path': reader.WORKFLOW, 'event': 'push',
               'status': 'completed', 'conclusion': 'failure',
               'repository': {'id': reader.REPOSITORY_ID, 'full_name': reader.REPOSITORY},
               'head_repository': {'id': reader.REPOSITORY_ID,
                                   'full_name': reader.REPOSITORY}}
        steps = [
            {'name': 'Fetch the retained ISO and verify its real bytes and source',
             'conclusion': 'success'},
            {'name': 'Direct upstream commands, online install, offline retry, local sessions and privacy',
             'conclusion': 'failure'},
            {'name': 'Run actions/upload-artifact@v4', 'conclusion': 'success'},
        ]
        jobs = {'total_count': 2, 'jobs': [
            {'id': 1, 'name': 'dictation (small-v2)', 'status': 'in_progress',
             'conclusion': None, 'steps': []},
            {'id': reader.JOB_ID, 'name': 'dictation (turbo-q5-v3)',
             'run_id': reader.RUN_ID, 'workflow_name': reader.WORKFLOW_NAME,
             'head_sha': reader.SOURCE_SHA, 'head_branch': reader.QUALIFICATION_BRANCH,
             'status': 'completed', 'conclusion': 'failure', 'steps': steps},
        ]}
        reader.validate_run(run, jobs)
        for field, wrong in (('run_attempt', 2), ('head_sha', '0' * 40),
                             ('path', '.github/workflows/other.yml')):
            changed = dict(run); changed[field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                reader.validate_run(changed, jobs)
        changed_jobs = json.loads(json.dumps(jobs))
        changed_jobs['jobs'][1]['id'] += 1
        with self.assertRaises(RuntimeError):
            reader.validate_run(run, changed_jobs)

    def test_workflow_api_and_reader_source_are_immutable(self):
        workflow = {'id': reader.WORKFLOW_ID, 'name': reader.WORKFLOW_NAME,
                    'path': reader.WORKFLOW, 'state': 'active'}
        reader.validate_workflow(workflow)
        for field, wrong in (('id', 1), ('name', 'other'), ('path', 'other.yml'),
                             ('state', 'disabled_manually')):
            changed = dict(workflow); changed[field] = wrong
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                reader.validate_workflow(changed)
        source = (reader.ROOT / reader.READER_WORKFLOW).read_text()
        checkout = 'uses: actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5'
        self.assertEqual(source.count(checkout), 1)
        self.assertNotIn('actions/checkout@v4', source)

    def test_projection_rejects_top_and_nested_transcript_fields_without_output(self):
        for mutate in (
                lambda value: value.update(transcript='private top'),
                lambda value: value['profiles']['turbo-q5-v3']['english'].update(
                    transcript='private nested' * (reader.MAX_OUTPUT_BYTES + 1)),
                lambda value: value['profiles']['turbo-q5-v3']['cleanup'].update(
                    excerpt='private nested')):
            report = self.projection()
            mutate(report)
            output = io.StringIO()
            with self.assertRaises(RuntimeError):
                reader.emit(report, output)
            self.assertEqual(output.getvalue(), '')

    def test_projection_size_cap_rejects_before_any_output(self):
        report = self.projection()
        output = io.StringIO()
        with mock.patch.object(reader, 'MAX_OUTPUT_BYTES', 32), \
                self.assertRaises(RuntimeError):
            reader.emit(report, output)
        self.assertEqual(output.getvalue(), '')

    def test_bounded_archive_stream_requires_exact_size_and_hash(self):
        payload = b'fixed archive bytes'
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'artifact.zip'
            path.write_bytes(payload)
            digest = hashlib.sha256(payload).hexdigest()
            self.assertEqual(reader.bounded_archive(path, len(payload), digest), payload)
            for size, sha in ((len(payload) - 1, digest), (len(payload), '0' * 64),
                              (reader.MAX_DOWNLOAD_BYTES + 1, digest)):
                with self.subTest(size=size, sha=sha), self.assertRaises(RuntimeError):
                    reader.bounded_archive(path, size, sha)

    def test_download_applies_exact_rlimit_and_rejects_oversized_file(self):
        class Child:
            def __init__(self, _argv, **kwargs):
                kwargs['preexec_fn']()
                kwargs['stdout'].write(b'x' * 17)
            def wait(self, timeout):
                self.timeout = timeout
                return 0
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(reader.resource, 'setrlimit') as limit, \
                mock.patch.object(reader.subprocess, 'Popen', Child):
            target = Path(temporary) / 'artifact.zip'
            reader.download(reader.ARTIFACT_ID, target, 17)
            limit.assert_called_once_with(reader.resource.RLIMIT_FSIZE, (17, 17))
            with self.assertRaises(RuntimeError):
                reader.download(reader.ARTIFACT_ID, Path(temporary) / 'too-large.zip',
                                reader.MAX_DOWNLOAD_BYTES + 1)
        class Oversized(Child):
            def __init__(self, _argv, **kwargs):
                kwargs['stdout'].write(b'x' * 18)
        with tempfile.TemporaryDirectory() as temporary, \
                mock.patch.object(reader.subprocess, 'Popen', Oversized), \
                self.assertRaises(RuntimeError):
            reader.download(reader.ARTIFACT_ID, Path(temporary) / 'artifact.zip', 17)

    def test_artifact_metadata_binds_both_repository_ids_and_branch(self):
        raw, fixture_sha = self.archive()
        pin = {'id': reader.ARTIFACT_ID,
               'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        for field, wrong in (('repository_id', 1), ('head_repository_id', 1),
                             ('head_branch', 'other')):
            artifact = self.artifact(pin)
            artifact['workflow_run'][field] = wrong
            with self.subTest(field=field), \
                    mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                    mock.patch.dict(reader.CONTEXT_PINS,
                                    {'fixture_manifest_sha256': fixture_sha}), \
                    self.assertRaises(RuntimeError):
                reader.inspect_artifact('turbo-q5-v3', pin, artifact, raw, Contract)

    def test_recovery_desktop_uid_is_positive_int_and_matches_indicator(self):
        value, raw, installation, report = self.recovery_bundle()
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            self.assertEqual(reader.validate_recovery(
                value, archive, installation, report, 1000),
                {'gpu_failure': True, 'cpu_ready': True})
        for invalid in ('1000', True, 0):
            value, raw, installation, report = self.recovery_bundle()
            value['gpu_failure']['request']['desktop_uid'] = invalid
            with self.subTest(invalid=invalid), zipfile.ZipFile(io.BytesIO(raw)) as archive, \
                    self.assertRaises(RuntimeError):
                reader.validate_recovery(value, archive, installation, report, 1000)
        value, raw, installation, report = self.recovery_bundle(desktop_uid=1001)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, self.assertRaises(RuntimeError):
            reader.validate_recovery(value, archive, installation, report, 1000)

    def test_activation_guard_rejects_merge_or_non_marker_activation(self):
        parent, child = 'a' * 40, 'b' * 40
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / reader.ACTIVATION
            marker.parent.mkdir(parents=True)
            marker.write_text(parent + '\n')
            event = root / 'event.json'
            event.write_text(json.dumps({'before': parent, 'after': child}))
            env = {
                'GITHUB_REPOSITORY': reader.REPOSITORY, 'GITHUB_EVENT_NAME': 'push',
                'GITHUB_REF': 'refs/heads/' + reader.BRANCH,
                'GITHUB_WORKFLOW': 'Read safe Turbo diagnostics for dictation run 38887529276',
                'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': child,
                'GITHUB_EVENT_PATH': str(event),
            }
            def clean(command, **_kwargs):
                if 'rev-list' in command: return child + ' ' + parent + '\n'
                if 'diff' in command: return reader.ACTIVATION.as_posix() + '\n'
                if 'status' in command: return ''
                raise AssertionError(command)
            with mock.patch.object(reader, 'ROOT', root), \
                    mock.patch.dict(reader.os.environ, env, clear=True), \
                    mock.patch.object(reader.subprocess, 'check_output', side_effect=clean):
                reader.activation_guard()
            def merge(command, **kwargs):
                value = clean(command, **kwargs)
                return value.rstrip() + ' ' + ('c' * 40) + '\n' if 'rev-list' in command else value
            with mock.patch.object(reader, 'ROOT', root), \
                    mock.patch.dict(reader.os.environ, env, clear=True), \
                    mock.patch.object(reader.subprocess, 'check_output', side_effect=merge), \
                    self.assertRaises(RuntimeError):
                reader.activation_guard()
            def changed_reader(command, **kwargs):
                value = clean(command, **kwargs)
                if 'diff' in command:
                    return value + '.github/workflows/read-dictation-turbo-failure-388875.yml\n'
                return value
            with mock.patch.object(reader, 'ROOT', root), \
                    mock.patch.dict(reader.os.environ, env, clear=True), \
                    mock.patch.object(reader.subprocess, 'check_output', side_effect=changed_reader), \
                    self.assertRaises(RuntimeError):
                reader.activation_guard()

    def test_duplicate_archive_member_is_rejected_before_content_projection(self):
        raw, fixture_sha = self.archive()
        source = zipfile.ZipFile(io.BytesIO(raw))
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as target:
            for item in source.infolist():
                target.writestr(item.filename, source.read(item.filename))
            target.writestr('execution.json', b'{"private":"must-not-be-read"}')
        tampered = output.getvalue()
        pin = {'id': reader.ARTIFACT_ID, 'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(tampered), 'sha256': hashlib.sha256(tampered).hexdigest()}
        artifact = self.artifact(pin)
        with mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                mock.patch.dict(reader.CONTEXT_PINS, {'fixture_manifest_sha256': fixture_sha}), \
                self.assertRaises(RuntimeError):
            reader.inspect_artifact('turbo-q5-v3', pin, artifact, tampered, Contract)

    def test_manifest_pins_local_reader_contract_and_exact_turbo_artifact(self):
        manifest = reader.read_json_file(HERE / 'execution-manifest.json', 32768)
        reader.validate_manifest(manifest)
        self.assertEqual(manifest['job_id'], reader.JOB_ID)
        self.assertEqual(manifest['run_attempt'], 1)
        self.assertEqual(manifest['source_sha'], reader.SOURCE_SHA)
        self.assertEqual(manifest['artifacts']['turbo-q5-v3']['id'], reader.ARTIFACT_ID)
        self.assertEqual(manifest['artifacts']['turbo-q5-v3']['bytes'], reader.ARTIFACT_BYTES)
        self.assertEqual(manifest['artifacts']['turbo-q5-v3']['sha256'],
                         reader.ARTIFACT_SHA256)
        self.assertEqual(manifest['reader_workflow_sha256'], hashlib.sha256(
            (reader.ROOT / reader.READER_WORKFLOW).read_bytes()).hexdigest())
        frozen = json.loads((HERE / 'qualification-execution-manifest.json').read_text())
        self.assertEqual(reader.IMAGE, frozen['image'])
        self.assertEqual(reader.FIXTURE_SHA256, frozen['fixture_manifest_sha256'])
        self.assertEqual(reader.CONTEXT_PINS['source_sha'], frozen['image']['source_sha'])
        self.assertEqual(reader.CONTEXT_PINS['iso_sha256'], frozen['image']['sha256'])
        self.assertEqual(reader.CONTEXT_PINS['iso_bytes'], frozen['image']['bytes'])
        self.assertEqual(reader.CONTEXT_PINS['fixture_manifest_sha256'],
                         frozen['fixture_manifest_sha256'])
        for field, path in {
                'checker_sha256': 'tools/dictation-qualification/guest_check.py',
                'contract_sha256': 'tools/dictation-qualification/contract.py',
                'accuracy_sha256': 'tools/dictation-accuracy/accuracy.py',
                'pins_sha256': 'tools/dictation-accuracy/pins.json'}.items():
            self.assertEqual(reader.CONTEXT_PINS[field], frozen['execution_files'][path])


if __name__ == '__main__':
    unittest.main()
