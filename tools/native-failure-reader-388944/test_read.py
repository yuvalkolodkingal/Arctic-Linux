#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('native_failure_reader', HERE / 'read.py')
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)


class Validator:
    TERMINAL = __import__('re').compile(r'\x1b\[[0-?]*[ -/]*[@-~]')

    @staticmethod
    def external_text(raw):
        return raw


class SafeNativeReaderTests(unittest.TestCase):
    def qualification(self):
        value = json.loads((HERE / 'qualification-execution-manifest.json').read_text())
        return value

    def raws(self, extra=None):
        qualification = self.qualification()
        pins = reader.load_source_provenance(qualification)
        taskbar = (b'ARCTIC-TASKBAR-BEGIN {}\n'
                   b'ARCTIC-TASKBAR-PROVENANCE {}\n'
                   b'ARCTIC-TASKBAR-REPORT {"private":"never emitted"')
        harness = (b'[   90s] run.sh started (attempt 1)\n'
                   b'[ 1498s] install finished after 1408s: exit 1\n'
                   b'[ 1499s] install stage: exit 1\n')
        stages = json.dumps({
            'results': {
                stage: {'stage': stage, 'status': 'limited-smoke-passed',
                        'release_acceptance': False, 'files': {}, 'provenance': {}}
                for stage in ('live', 'installed')},
            'errors': ['installed harness: Missing/duplicate/nonzero '
                       'ARCTIC-INSTALLED-SMOKE-EXIT'],
            'release_acceptance': False,
        }, sort_keys=True).encode()
        serial = (b'ARCTIC-COLLECT-BEGIN\n'
                  b'ARCTIC-NATIVE-RUNNER-END {"stage":"installed","status":"passed",'
                  b'"error":null,"evidence_export_complete":true,"release_acceptance":false}\n'
                  b'ARCTIC-COLLECT-END\n')
        execution = json.dumps({
            'status': 'failed_or_unrun',
            'candidate_iso_source': qualification['image']['source_sha'],
            'execution_checker_head': reader.RUN_HEAD,
            'iso_bytes': qualification['image']['bytes'],
            'iso_sha256': qualification['image']['sha256'],
            'source_image_run': qualification['image']['run_id'],
            'checker': {'method': 'native-functional',
                        'checker_sha256': pins['checker_sha256'],
                        'native_source_sha256': pins['native_source_sha256'],
                        'release_acceptance': False},
            'harness_evidence': {
                'taskbar-boot.log.bounded-prefix.bin': {
                    'bytes': len(taskbar), 'sha256': hashlib.sha256(taskbar).hexdigest(),
                    'original_bytes': len(taskbar),
                    'original_sha256': hashlib.sha256(taskbar).hexdigest()}},
            'error': ('harness: Native command failed (1); see native-harness.log; '
                      'native stages: installed harness: Missing/duplicate/nonzero '
                      'ARCTIC-INSTALLED-SMOKE-EXIT; taskbar: '
                      'missing/extra/duplicate/reordered taskbar records'),
            'release_acceptance': False,
        }, sort_keys=True).encode()
        values = {
            'execution.json': execution,
            'native-harness.log': harness,
            'native-stages.json': stages,
            'harness/taskbar-boot.log.bounded-prefix.bin': taskbar,
            'harness/serial-boot.log': serial,
        }
        files = {}
        for name, raw in values.items():
            digest = hashlib.sha256(raw).hexdigest()
            files[name] = {'original_sha256': digest, 'uploaded_sha256': digest,
                           'bytes': len(raw), 'redactions': 0}
        values['upload-screening.json'] = json.dumps({
            'scope': 'Owned synthetic QEMU VM only; no host desktop, VM disks or credentials',
            'files': files}, sort_keys=True).encode()
        if extra:
            values[extra] = b'password=private-value\nhttps://private.invalid/?token=secret'
        return values

    @staticmethod
    def archive(values, duplicate=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in values.items():
                archive.writestr(name, raw)
            if duplicate:
                archive.writestr(duplicate, values[duplicate])
        return output.getvalue()

    def inspect(self, values):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'artifact.zip'
            path.write_bytes(self.archive(values))
            with mock.patch.object(reader, 'ARTIFACT_BYTES', path.stat().st_size), \
                    mock.patch.object(reader, 'load_validator', return_value=Validator):
                return reader.inspect_archive(path, {'validator_sha256': 'f' * 64},
                                              self.qualification())

    def test_exact_projection_is_closed_and_distinguishes_native_from_taskbar(self):
        result = self.inspect(self.raws(extra='arbitrary-private-member.log'))
        self.assertEqual(result['runner_failure_code'], 1)
        self.assertEqual(result['harness']['install_stage_exit_code'], 1)
        self.assertEqual(result['native_stages']['results'],
                         {'live': 'passed', 'installed': 'passed'})
        self.assertEqual(result['serial_boot']['installed_smoke_exit'], 'missing')
        self.assertEqual(result['serial_boot']['native_end_statuses'], ['passed'])
        self.assertEqual(result['serial_boot']['taskbar_preflight_failure_stages'], [])
        self.assertEqual(result['taskbar_prefix']['complete_record_kinds'],
                         ['BEGIN', 'PROVENANCE'])
        self.assertEqual(result['taskbar_prefix']['partial_record_kind'], 'REPORT')
        stream = io.StringIO(); reader.emit(result, stream)
        emitted = stream.getvalue()
        for private in ('private-value', 'private.invalid', 'never emitted',
                        reader.ARTIFACT_SHA256, reader.RUN_HEAD):
            self.assertNotIn(private, emitted)

    def test_unknown_archive_member_is_never_read(self):
        values = self.raws(extra='arbitrary-private-member.log')
        raw = self.archive(values)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'artifact.zip'; path.write_bytes(raw)
            original = zipfile.ZipFile.read
            def guarded(archive, member, *args, **kwargs):
                name = member.filename if isinstance(member, zipfile.ZipInfo) else member
                if name == 'arbitrary-private-member.log':
                    raise AssertionError('arbitrary member was read')
                return original(archive, member, *args, **kwargs)
            with mock.patch.object(reader, 'ARTIFACT_BYTES', len(raw)), \
                    mock.patch.object(zipfile.ZipFile, 'read', guarded), \
                    mock.patch.object(reader, 'load_validator', return_value=Validator):
                result = reader.inspect_archive(path, {'validator_sha256': 'f' * 64},
                                                self.qualification())
        self.assertEqual(result['runner_failure_code'], 1)

    def test_duplicate_required_member_and_tampered_screening_are_rejected(self):
        values = self.raws()
        with zipfile.ZipFile(io.BytesIO(self.archive(values, 'native-stages.json'))) as archive, \
                self.assertRaises(reader.ArchiveReject):
            reader.fixed_members(archive)
        self.assertEqual((reader.ARCHIVE_ROLE, reader.ARCHIVE_REASON),
                         ('native_stages', 'duplicate'))
        screening = json.loads(values['upload-screening.json'])
        screening['files']['native-harness.log']['uploaded_sha256'] = '0' * 64
        values['upload-screening.json'] = json.dumps(screening).encode()
        with self.assertRaises(RuntimeError):
            self.inspect(values)

    def test_archive_rejections_emit_only_closed_role_and_reason(self):
        values = self.raws(); values.pop('native-stages.json')
        with zipfile.ZipFile(io.BytesIO(self.archive(values))) as archive, \
                self.assertRaises(reader.ArchiveReject):
            reader.fixed_members(archive)
        self.assertEqual((reader.ARCHIVE_ROLE, reader.ARCHIVE_REASON),
                         ('native_stages', 'missing-required'))
        complete = self.archive(self.raws())
        mutations = (
            ('type', lambda item: setattr(item, 'external_attr', (stat.S_IFDIR | 0o755) << 16), None),
            ('encryption', lambda item: setattr(item, 'flag_bits', item.flag_bits | 1), None),
            ('compression', lambda item: setattr(item, 'compress_type', 99), None),
            ('size', lambda item: setattr(item, 'file_size', 2 * 1024 * 1024), None),
            ('crc', lambda _item: None, zipfile.BadZipFile('private crc detail')),
            ('read', lambda _item: None, OSError('private path detail')),
        )
        for expected, mutate, failure in mutations:
            with self.subTest(reason=expected), zipfile.ZipFile(io.BytesIO(complete)) as archive:
                item = next(row for row in archive.infolist()
                            if row.filename == 'upload-screening.json')
                mutate(item)
                context = (mock.patch.object(archive, 'read', side_effect=failure)
                           if failure else contextlib.nullcontext())
                with context, self.assertRaises(reader.ArchiveReject):
                    reader.fixed_members(archive)
                self.assertEqual((reader.ARCHIVE_ROLE, reader.ARCHIVE_REASON),
                                 ('screening', expected))
        with self.assertRaises(reader.ArchiveReject):
            reader.archive_reject('private/path', 'password=private')
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            reader.write_rejection('archive')
        self.assertEqual(stream.getvalue(),
                         'ARCTIC-NATIVE-READER-REJECTION=archive:archive:read\n')

    def test_execution_requires_exact_public_error_and_taskbar_receipt(self):
        values = self.raws()
        execution = json.loads(values['execution.json'])
        taskbar = values['harness/taskbar-boot.log.bounded-prefix.bin']
        for mutation in ('error', 'taskbar-hash', 'taskbar-size'):
            changed = json.loads(json.dumps(execution))
            if mutation == 'error':
                changed['error'] += '; password=private'
            elif mutation == 'taskbar-hash':
                changed['harness_evidence']['taskbar-boot.log.bounded-prefix.bin']['sha256'] = '0' * 64
            else:
                changed['harness_evidence']['taskbar-boot.log.bounded-prefix.bin']['original_bytes'] = len(taskbar)-1
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                reader.validate_execution(json.dumps(changed).encode(), self.qualification(), taskbar)

    def test_native_stage_projection_rejects_changed_or_private_error(self):
        raw = self.raws()['native-stages.json']
        expected = reader.validate_native_stages(raw)
        self.assertEqual(expected['results']['installed'], 'passed')
        value = json.loads(raw)
        for errors in ([], ['password=private'], value['errors'] * 2):
            changed = json.loads(json.dumps(value)); changed['errors'] = errors
            with self.subTest(errors=errors), self.assertRaises(RuntimeError):
                reader.validate_native_stages(json.dumps(changed).encode())

    def test_taskbar_prefix_projects_kinds_only_and_fails_closed(self):
        raw = self.raws()['harness/taskbar-boot.log.bounded-prefix.bin']
        value = reader.validate_taskbar_prefix(raw)
        self.assertNotIn('private', json.dumps(value))
        complete = (b'ARCTIC-TASKBAR-BEGIN {}\nARCTIC-TASKBAR-PROVENANCE {}\n'
                    b'ARCTIC-TASKBAR-REPORT {}\nARCTIC-TASKBAR-EVIDENCE-CHUNK {}\n'
                    b'ARCTIC-TASKBAR-EVIDENCE-MANIFEST {}\nARCTIC-TASKBAR-END {}\n')
        self.assertEqual(reader.validate_taskbar_prefix(complete)['complete_record_kinds'][-2:],
                         ['EVIDENCE-MANIFEST', 'END'])
        invalid = (
            b'password=private\n',
            b'ARCTIC-TASKBAR-END {}\n',
            b'ARCTIC-TASKBAR-BEGIN {}\nARCTIC-TASKBAR-BEGIN {}\n',
            b'ARCTIC-TASKBAR-BEGIN {}\x00',
            b'ARCTIC-TASKBAR-BEGIN {}\r\n',
            b'ARCTIC-TASKBAR-BEGIN {}\nARCTIC-TASKBAR-PRIVATE secret',
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), self.assertRaises(RuntimeError):
                reader.validate_taskbar_prefix(candidate)

    def test_serial_projection_exposes_no_unrecognized_text(self):
        raw = self.raws()['harness/serial-boot.log'] + b'password=private outside fixed records\n'
        value = reader.validate_serial_boot(raw, Validator)
        self.assertNotIn('private', json.dumps(value))
        self.assertEqual(value['native_end_statuses'], ['passed'])
        self.assertEqual(value['installed_smoke_exit'], 'missing')
        malformed = raw + b'ARCTIC-INSTALLED-SMOKE-EXIT=secret\n'
        self.assertEqual(reader.validate_serial_boot(malformed, Validator)
                         ['installed_smoke_exit'], 'malformed')

    def test_harness_screening_failure_and_changed_exit_are_closed(self):
        private = b'password=do-not-print\nhttps://private.invalid/?token=secret\n'
        class RejectingValidator(Validator):
            @staticmethod
            def external_text(raw):
                print('ARCTIC-EVIDENCE-RULE=source-view-named-secret')
                raise RuntimeError(private.decode())
        outer = io.StringIO()
        with contextlib.redirect_stdout(outer), self.assertRaises(RuntimeError):
            reader.validate_harness(private, RejectingValidator)
        self.assertEqual(outer.getvalue(), '')
        changed = self.raws()['native-harness.log'].replace(b'exit 1', b'exit 2')
        with self.assertRaises(RuntimeError):
            reader.validate_harness(changed, Validator)

    def test_optional_serial_absence_is_explicit(self):
        values = self.raws()
        values.pop('harness/serial-boot.log')
        screening = json.loads(values['upload-screening.json'])
        screening['files'].pop('harness/serial-boot.log')
        values['upload-screening.json'] = json.dumps(screening, sort_keys=True).encode()
        self.assertEqual(self.inspect(values)['serial_boot'], {'present': False})

    def test_strict_json_metadata_and_workflow_pins(self):
        with self.assertRaises(RuntimeError):
            reader.strict_json(b'{"x":1,"x":2}', 100)
        with self.assertRaises(RuntimeError):
            reader.strict_json(b'{"x":NaN}', 100)
        artifact = {'id': reader.ARTIFACT_ID, 'name': reader.ARTIFACT_NAME,
                    'expired': False, 'size_in_bytes': reader.ARTIFACT_BYTES,
                    'digest': 'sha256:' + reader.ARTIFACT_SHA256,
                    'workflow_run': {'id': reader.RUN_ID, 'head_sha': reader.RUN_HEAD}}
        reader.validate_artifact(artifact)
        bad = dict(artifact); bad['digest'] = 'sha256:' + '0' * 64
        with self.assertRaises(RuntimeError):
            reader.validate_artifact(bad)
        workflow = Path(reader.READER_WORKFLOW).read_text()
        self.assertIn('actions/checkout@34e114876b0b11c390a56381ad16ebd13914f8d5', workflow)
        self.assertNotIn('actions/checkout@v', workflow)
        self.assertIn(reader.ACTIVATION.as_posix(), workflow)

    def test_exact_producer_action_resolution_is_required(self):
        checkout = reader.ACTION_RESOLUTIONS['actions/checkout']
        upload = reader.ACTION_RESOLUTIONS['actions/upload-artifact']
        raw = (('2026-10-16T11:32:18.1598921Z Download action repository '
                "'actions/checkout@v4' (SHA:" + checkout + ')\n'
                '2026-10-16T11:32:18.5163282Z Download action repository '
                "'actions/upload-artifact@v4' (SHA:" + upload + ')\n'
                'private unrelated log text that is never projected\n').encode())
        self.assertTrue(reader.validate_action_resolution(raw))
        mutations = (
            raw.replace(checkout.encode(), b'0' * 40),
            raw.replace(b'actions/checkout@v4', b'actions/checkout@v5'),
            raw + raw.splitlines(keepends=True)[0],
            raw.replace(b'actions/upload-artifact@v4', b'private/action@v4'),
            raw.replace(b'Download action repository ', b'Download action repository private '),
        )
        for changed in mutations:
            with self.subTest(changed=changed[:80]), self.assertRaises(RuntimeError):
                reader.validate_action_resolution(changed)

    def test_bounded_job_log_capture_stops_oversize_and_stderr(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / 'ok.log'
            size = reader.bounded_command_to_file(
                [sys.executable, '-c', "import sys;sys.stdout.buffer.write(b'x'*1024)"],
                target, 2048, 10)
            self.assertEqual(size, 1024)
            self.assertEqual(target.stat().st_size, 1024)
            with self.assertRaises(RuntimeError):
                reader.bounded_command_to_file(
                    [sys.executable, '-c', "import sys;sys.stdout.buffer.write(b'x'*4096)"],
                    root / 'oversize.log', 2048, 10)
            with self.assertRaises(RuntimeError):
                reader.bounded_command_to_file(
                    [sys.executable, '-c', "import sys;sys.stderr.buffer.write(b'x'*70000);sys.stdout.write('x')"],
                    root / 'stderr.log', 2048, 10)

    def test_action_commits_must_resolve_to_the_pinned_objects(self):
        def exact(endpoint):
            return {'sha': endpoint.rsplit('/', 1)[1]}
        with mock.patch.object(reader, 'api_endpoint', side_effect=exact):
            self.assertTrue(reader.validate_action_commits())
        with mock.patch.object(reader, 'api_endpoint', return_value={'sha': '0' * 40}), \
                self.assertRaises(RuntimeError):
            reader.validate_action_commits()

    def test_run_requires_both_checkout_steps_and_exact_job_identity(self):
        run = {'id': reader.RUN_ID, 'run_attempt': reader.RUN_ATTEMPT,
               'head_sha': reader.RUN_HEAD,
               'head_branch': 'codex/qualification-dispatch-20261010',
               'path': reader.WORKFLOW, 'event': 'push', 'status': 'completed',
               'conclusion': 'failure',
               'repository': {'full_name': reader.REPOSITORY}}
        names = [
            ('Set up job', 'success'),
            ('Run actions/checkout@v4', 'success'),
            ('Verify reviewed single-file activation and pinned source', 'success'),
            ('Run actions/checkout@v4', 'success'),
            ('Fetch and verify retained ISO archive and actual image bytes', 'success'),
            ('Native live and encrypted offline installed acceptance', 'failure'),
            ('Screen bounded diagnostic files before upload', 'success'),
            ('Run actions/upload-artifact@v4', 'success'),
            ('Post Run actions/checkout@v4', 'success'),
            ('Post Run actions/checkout@v4', 'success'),
        ]
        job = {'id': reader.JOB_ID, 'run_id': reader.RUN_ID,
               'run_attempt': reader.RUN_ATTEMPT, 'head_sha': reader.RUN_HEAD,
               'name': 'native', 'status': 'completed', 'conclusion': 'failure',
               'steps': [{'name': name, 'conclusion': conclusion}
                         for name, conclusion in names]}
        jobs = {'total_count': 1, 'jobs': [job]}
        reader.validate_run(run, jobs)
        for mutation in ('job', 'checkout', 'upload'):
            changed = json.loads(json.dumps(jobs))
            if mutation == 'job':
                changed['jobs'][0]['id'] += 1
            elif mutation == 'checkout':
                changed['jobs'][0]['steps'][3]['name'] = 'Run actions/checkout@v5'
            else:
                changed['jobs'][0]['steps'][7]['name'] = 'Run actions/upload-artifact@v5'
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                reader.validate_run(run, changed)


if __name__ == '__main__':
    unittest.main()
