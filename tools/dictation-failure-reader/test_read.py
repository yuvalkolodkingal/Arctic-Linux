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
                          'stage_present': True, 'stage': 214})
        gate['observations']['failure_stage'] = 215
        with self.assertRaises(RuntimeError):
            reader.staged_gate(gate, set(range(201, 215)))
        gate['observations']['failure_stage'] = 201
        gate['code'] = 'private arbitrary error'
        with self.assertRaises(RuntimeError):
            reader.staged_gate(gate, set(range(201, 215)))

    def test_exact_artifact_projects_stages_and_never_raw_content(self):
        raw, fixture_sha = self.archive()
        pin = {'id': 17, 'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        artifact = {'id': 17, 'name': pin['name'], 'expired': False,
                    'size_in_bytes': len(raw), 'digest': 'sha256:' + pin['sha256'],
                    'workflow_run': {'id': reader.RUN_ID, 'head_sha': reader.SOURCE_SHA}}
        with mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                mock.patch.dict(reader.CONTEXT_PINS, {'fixture_manifest_sha256': fixture_sha}):
            result = reader.inspect_artifact('turbo-q5-v3', pin, artifact, raw, Contract)
        self.assertEqual(result['english']['stage'], 11)
        self.assertEqual(result['gpu']['stage'], 210)
        self.assertEqual(result['privacy']['family'], 'invalid')
        self.assertFalse(result['privacy']['matched_present'])
        self.assertEqual(result['cleanup']['file_count'], 0)
        self.assertFalse(result['recovery_receipts']['entry_present'])
        report = {'schema': 'arctic-dictation-safe-diagnostic-v1',
                  'run_id': reader.RUN_ID, 'release_acceptance': False,
                  'profiles': {'small-v2': result, 'turbo-q5-v3': result}}
        stream = io.StringIO()
        reader.emit(report, stream)
        emitted = stream.getvalue()
        self.assertTrue(emitted.startswith('ARCTIC-DICTATION-SAFE-DIAGNOSTIC='))
        self.assertNotIn('private-content', emitted)
        self.assertNotIn('fixture manifest', emitted)
        self.assertNotIn(reader.IMAGE['sha256'], emitted)

    def test_unknown_archive_member_is_rejected_without_reading_it(self):
        raw, fixture_sha = self.archive(extra='private.log')
        pin = {'id': 17, 'name': 'dictation-candidate-qualification-turbo-q5-v3',
               'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}
        artifact = {'id': 17, 'name': pin['name'], 'expired': False,
                    'size_in_bytes': len(raw), 'digest': 'sha256:' + pin['sha256'],
                    'workflow_run': {'id': reader.RUN_ID, 'head_sha': reader.SOURCE_SHA}}
        with mock.patch.object(reader, 'FIXTURE_SHA256', fixture_sha), \
                mock.patch.dict(reader.CONTEXT_PINS, {'fixture_manifest_sha256': fixture_sha}), \
                self.assertRaises(RuntimeError):
            reader.inspect_artifact('turbo-q5-v3', pin, artifact, raw, Contract)

    def test_manifest_pins_local_reader_contract_and_both_exact_artifacts(self):
        manifest = reader.read_json_file(HERE / 'execution-manifest.json', 32768)
        reader.validate_manifest(manifest)


if __name__ == '__main__':
    unittest.main()
