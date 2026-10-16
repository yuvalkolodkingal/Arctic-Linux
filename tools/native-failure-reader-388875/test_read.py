#!/usr/bin/env python3
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock
import zipfile
import zlib

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
    @staticmethod
    def png(width=1280, height=720):
        def chunk(kind, data):
            return (len(data).to_bytes(4, 'big') + kind + data
                    + (zlib.crc32(kind + data) & 0xffffffff).to_bytes(4, 'big'))
        ihdr = (width.to_bytes(4, 'big') + height.to_bytes(4, 'big')
                + b'\x08\x02\x00\x00\x00')
        pixels = (b'\x00' + b'\x00' * (width * 3)) * height
        return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))

    def captured_host_frame(self, native_source, image):
        return {
            'schema': 'arctic-native-host-frame-v1', 'stage': 'live',
            'status': 'captured', 'release_acceptance': False,
            'product_change_authorized': False,
            'capture': {'path': 'native-host-celluloid-live.png', 'bytes': len(image),
                        'sha256': hashlib.sha256(image).hexdigest(),
                        'device': 'arctic_taskbar_gpu', 'head': 1,
                        'physical_size': [1280, 720],
                        'exported_crop': [0, 0, 1280, 720]},
            'comparison': 'host-matched-guest-unmatched',
            'interpretation': 'guest-screencopy-divergence-observed',
            'identical_palette_oracle': True, 'same_paused_player_hold': 20,
            'native_oracle_source_sha256': native_source,
            'oracle': {'status': 'matched'},
        }

    def qualification(self):
        provenance = Path('tools/native-functional/source-provenance.json').read_bytes()
        display = Path('tools/native-functional/taskbar-display.py').read_bytes()
        return {
            'ready': True, 'release_acceptance': False,
            'execution_files': {
                'tools/native-functional/source-provenance.json': hashlib.sha256(provenance).hexdigest(),
                'tools/native-functional/taskbar-display.py': hashlib.sha256(display).hexdigest(),
            },
            'image': {'source_sha': 'f369b978aeb05a3310c512660811084fd5bc97d1',
                      'bytes': 1936160768,
                      'sha256': 'cf0505f366c964a13a4134a74327df58839050751f2a227da81a8e055523adcb',
                      'run_id': 38879661832},
        }

    def raws(self, extra=None, harness=None, stop=None, execution=None):
        stop_value = stop or {
            'schema': 'arctic-native-harness-stop-v1', 'phase': 'install',
            'qemu_returncode': None, 'elapsed_seconds': 2400.25,
            'deadline_seconds': 2400, 'deadline_reached': True,
            'exit_marker_present': False, 'reason': 'deadline-expired',
            'release_acceptance': False,
        }
        stop_raw = json.dumps(stop_value, sort_keys=True).encode()
        execution_value = execution or {
            'status': 'failed_or_unrun',
            'candidate_iso_source': self.qualification()['image']['source_sha'],
            'execution_checker_head': reader.RUN_HEAD,
            'iso_bytes': self.qualification()['image']['bytes'],
            'iso_sha256': self.qualification()['image']['sha256'],
            'source_image_run': self.qualification()['image']['run_id'],
            'checker': {'method': 'native-functional',
                        **{key: value for key, value in
                           reader.load_source_provenance(self.qualification()).items()
                           if key in ('checker_sha256', 'native_source_sha256')},
                        'release_acceptance': False},
            'harness_evidence': {'native-stop-install.json': {
                'bytes': len(stop_raw), 'sha256': hashlib.sha256(stop_raw).hexdigest(),
                'private_original': True, 'release_acceptance': False}},
            'error': ('harness: Native command failed (91); see native-harness.log; '
                      'native stages: fixed source failure'),
            'release_acceptance': False,
        }
        execution_raw = json.dumps(execution_value, sort_keys=True).encode()
        harness_raw = harness or (
            b'[  100s] run.sh started (attempt 1)\n'
            b'[ 2501s] install finished after 2401s: exit None\n'
            b'[ 2501s] install timed out\n'
            b'[ 2502s] install stage: exit 91\n')
        qemu_raw = b'qemu-system-x86_64: terminating on signal 15 from pid 1234 (python3)\n'
        display_raw = json.dumps({
            'schema': 'arctic-qemu-taskbar-display-v1',
            'status': 'uiinfo_applied_pending_guest_two_output_evidence',
            'qemu_pid': 123, 'qemu_uid': 0, 'gpu_id': 'arctic_taskbar_gpu',
            'bus_pid': 124, 'bus_owner': ':1.2', 'display_backend': 'dbus',
            'guest_monitor_verification_required': True,
            'controller_sha256': reader.load_source_provenance(
                self.qualification())['taskbar_display_sha256'],
            'heads': [
                {'console_id': 0, 'head': 0, 'device_address': 'pci/0000/01.0',
                 'width_mm': 340, 'height_mm': 190, 'xoff': 0, 'yoff': 0,
                 'width': 1280, 'height': 720},
                {'console_id': 1, 'head': 1, 'device_address': 'pci/0000/01.0',
                 'width_mm': 340, 'height_mm': 190, 'xoff': 1280, 'yoff': 0,
                 'width': 1280, 'height': 720},
            ],
        }, sort_keys=True).encode()
        files = {}
        for name, raw, redactions in (
                ('execution.json', execution_raw, 0),
                ('harness/native-stop-install.json', stop_raw, 0),
                ('native-harness.log', harness_raw, 0),
                ('harness/qemu-install.log', qemu_raw, 0),
                ('harness/taskbar-display-install.json', display_raw, 0)):
            digest = hashlib.sha256(raw).hexdigest()
            files[name] = {'original_sha256': digest, 'uploaded_sha256': digest,
                           'bytes': len(raw), 'redactions': redactions}
        screening = {'scope': 'Owned synthetic QEMU VM only; no host desktop, VM disks or credentials',
                     'files': files}
        values = {'execution.json': execution_raw,
                  'harness/native-stop-install.json': stop_raw,
                  'native-harness.log': harness_raw,
                  'harness/qemu-install.log': qemu_raw,
                  'harness/taskbar-display-install.json': display_raw,
                  'upload-screening.json': json.dumps(screening, sort_keys=True).encode()}
        if extra:
            values[extra] = b'password=private-value\nhttps://private.invalid/?token=secret'
        return values

    def archive(self, values, duplicate=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
            for name, raw in values.items():
                archive.writestr(name, raw)
            if duplicate:
                archive.writestr(duplicate, values[duplicate])
        return output.getvalue()

    def without_stop(self, retention='not-recorded'):
        values = self.raws()
        values.pop('harness/native-stop-install.json')
        screening = json.loads(values['upload-screening.json'])
        screening['files'].pop('harness/native-stop-install.json')
        values['upload-screening.json'] = json.dumps(screening, sort_keys=True).encode()
        execution = json.loads(values['execution.json'])
        if retention == 'not-recorded':
            execution['harness_evidence'].pop('native-stop-install.json')
        elif retention == 'closed-record-rejected':
            execution['harness_evidence']['native-stop-install.json'] = {
                'retained': False, 'reason': 'closed-record-rejected',
                'release_acceptance': False}
        else:
            execution['harness_evidence']['native-stop-install.json'] = retention
        values['execution.json'] = json.dumps(execution, sort_keys=True).encode()
        record = screening = json.loads(values['upload-screening.json'])
        digest = hashlib.sha256(values['execution.json']).hexdigest()
        record['files']['execution.json'] = {
            'original_sha256': digest, 'uploaded_sha256': digest,
            'bytes': len(values['execution.json']), 'redactions': 0}
        values['upload-screening.json'] = json.dumps(record, sort_keys=True).encode()
        return values

    def inspect(self, values):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'artifact.zip'
            path.write_bytes(self.archive(values))
            with mock.patch.object(reader, 'ARTIFACT_BYTES', path.stat().st_size):
                manifest = {'validator_sha256': 'f' * 64}
                with mock.patch.object(reader, 'load_validator', return_value=Validator):
                    return reader.inspect_archive(path, manifest, self.qualification())

    def test_exact_projection_contains_only_closed_typed_diagnostics(self):
        result = self.inspect(self.raws(extra='arbitrary-private-member.log'))
        self.assertEqual(result['runner_failure_code'], 91)
        self.assertEqual(result['stop']['reason'], 'deadline-expired')
        self.assertEqual(result['harness']['install_stage_exit_code'], 91)
        self.assertEqual(result['harness']['install_exit_marker'], 'missing')
        self.assertEqual(result['qemu']['families'], ['signal-termination'])
        self.assertEqual(result['display']['geometry'], '2560x720')
        self.assertFalse(result['host_frame']['present'])
        stream = io.StringIO()
        reader.emit(result, stream)
        emitted = stream.getvalue()
        self.assertTrue(emitted.startswith('ARCTIC-NATIVE-SAFE-DIAGNOSTIC='))
        self.assertNotIn('private-value', emitted)
        self.assertNotIn('private.invalid', emitted)
        self.assertNotIn(reader.ARTIFACT_SHA256, emitted)
        self.assertNotIn(reader.RUN_HEAD, emitted)

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
        self.assertEqual(result['runner_failure_code'], 91)

    def test_duplicate_fixed_member_and_tampered_screening_hash_are_rejected(self):
        values = self.raws()
        raw = self.archive(values, duplicate='native-harness.log')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'artifact.zip'; path.write_bytes(raw)
            with mock.patch.object(reader, 'ARTIFACT_BYTES', len(raw)), \
                    self.assertRaises(reader.ArchiveReject):
                with zipfile.ZipFile(path) as archive:
                    reader.fixed_members(archive)
            self.assertEqual((reader.ARCHIVE_ROLE, reader.ARCHIVE_REASON),
                             ('harness', 'duplicate'))
        values = self.raws()
        screening = json.loads(values['upload-screening.json'])
        screening['files']['native-harness.log']['uploaded_sha256'] = '0' * 64
        values['upload-screening.json'] = json.dumps(screening).encode()
        with self.assertRaises(RuntimeError):
            self.inspect(values)

    def test_optional_native_members_can_be_absent_with_closed_presence(self):
        values = self.raws()
        screening = json.loads(values['upload-screening.json'])
        for name in ('harness/qemu-install.log', 'harness/taskbar-display-install.json'):
            values.pop(name); screening['files'].pop(name)
        values['upload-screening.json'] = json.dumps(screening, sort_keys=True).encode()
        result = self.inspect(values)
        self.assertEqual(result['qemu'], {'present': False})
        self.assertEqual(result['display'], {'present': False})
        self.assertEqual(result['stage_logs'], {
            'stage_log': {'present': False}, 'current_stage_log': {'present': False}})
        self.assertEqual(result['host_frame'], {'present': False})

    def test_stop_can_be_absent_only_with_closed_execution_retention(self):
        for retention in ('not-recorded', 'closed-record-rejected'):
            with self.subTest(retention=retention):
                result = self.inspect(self.without_stop(retention))
                self.assertEqual(result['stop'],
                                 {'present': False, 'retention': retention})

        invalid = (
            None,
            {'retained': True, 'reason': 'closed-record-rejected',
             'release_acceptance': False},
            {'retained': False, 'reason': 'private-reason',
             'release_acceptance': False},
            {'retained': False, 'reason': 'closed-record-rejected',
             'release_acceptance': False, 'private': 'value'},
            {'bytes': 1, 'sha256': '0' * 64, 'private_original': True,
             'release_acceptance': False},
        )
        for retention in invalid:
            with self.subTest(retention=retention), self.assertRaises(RuntimeError):
                self.inspect(self.without_stop(retention))

    def test_present_stop_still_requires_exact_retained_receipt(self):
        values = self.raws()
        execution = json.loads(values['execution.json'])
        for receipt in (None,
                        {'retained': False, 'reason': 'closed-record-rejected',
                         'release_acceptance': False}):
            changed = json.loads(json.dumps(execution))
            if receipt is None:
                changed['harness_evidence'].pop('native-stop-install.json')
            else:
                changed['harness_evidence']['native-stop-install.json'] = receipt
            with self.subTest(receipt=receipt), self.assertRaises(RuntimeError):
                reader.validate_execution(json.dumps(changed).encode(), self.qualification(),
                                          values['harness/native-stop-install.json'])

    def test_archive_rejections_use_only_closed_role_and_reason(self):
        values = self.raws(); values.pop('native-harness.log')
        raw = self.archive(values)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive, \
                self.assertRaises(reader.ArchiveReject):
            reader.fixed_members(archive)
        self.assertEqual((reader.ARCHIVE_ROLE, reader.ARCHIVE_REASON),
                         ('harness', 'missing-required'))

        mutations = (
            ('type', lambda item: setattr(item, 'external_attr',
                                          (stat.S_IFDIR | 0o755) << 16), None),
            ('encryption', lambda item: setattr(item, 'flag_bits', item.flag_bits | 1), None),
            ('compression', lambda item: setattr(item, 'compress_type', 99), None),
            ('size', lambda item: setattr(item, 'file_size', 2 * 1024 * 1024), None),
            ('crc', lambda _item: None, zipfile.BadZipFile('private crc detail')),
            ('read', lambda _item: None, OSError('private path detail')),
        )
        complete = self.archive(self.raws())
        for expected, mutate, failure in mutations:
            with self.subTest(reason=expected), zipfile.ZipFile(io.BytesIO(complete)) as archive:
                item = next(row for row in archive.infolist()
                            if row.filename == 'upload-screening.json')
                mutate(item)
                context = (mock.patch.object(archive, 'read', side_effect=failure)
                           if failure is not None else contextlib.nullcontext())
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
        self.assertNotIn('private', stream.getvalue())

    def test_stop_contract_rejects_changed_deadline_marker_and_nonfinite(self):
        base = json.loads(self.raws()['harness/native-stop-install.json'])
        mutations = (
            lambda value: value.update(deadline_seconds=2399),
            lambda value: value.update(exit_marker_present=True),
            lambda value: value.update(reason='private arbitrary reason'),
            lambda value: value.update(elapsed_seconds=float('nan')),
        )
        for mutate in mutations:
            value = dict(base); mutate(value)
            raw = json.dumps(value, allow_nan=True).encode()
            with self.subTest(value=value), self.assertRaises((RuntimeError, ValueError)):
                reader.validate_stop(raw)

    def test_harness_parser_rejects_private_or_changed_lines_without_emitting_them(self):
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
        self.assertNotIn('do-not-print', outer.getvalue())
        changed = self.raws()['native-harness.log'].replace(b'exit 91', b'exit 90')
        with self.assertRaises(RuntimeError):
            reader.validate_harness(changed, Validator)

    def test_execution_error_is_never_projected_and_must_bind_code_91(self):
        values = self.raws()
        execution = json.loads(values['execution.json'])
        execution['error'] = 'password=private-value; harness returned another code'
        with self.assertRaises(RuntimeError):
            reader.validate_execution(json.dumps(execution).encode(), self.qualification(),
                                      values['harness/native-stop-install.json'])

    def test_stage_qemu_and_host_frame_project_only_closed_fields(self):
        stage = (b'[   10s] boot menu on screen: install-01-boot-menu.png\n'
                 b'[  100s] run.sh started (attempt 1)\n'
                 b'[  439s] install stage: exit 91\n'
                 b'password=private text outside recognized grammar\n')
        projected = reader.validate_stage_log(stage, Validator)
        self.assertEqual(projected['last_recognized_event'], 'install-stage-exit')
        self.assertNotIn('private', json.dumps(projected))
        qemu = reader.validate_qemu(b'arbitrary private qemu details\n', Validator)
        self.assertEqual(qemu['families'], ['unclassified'])
        self.assertNotIn('arbitrary', json.dumps(qemu))
        native = reader.load_source_provenance(self.qualification())['native_source_sha256']
        self.assertEqual(reader.validate_host_frame({}, native), {'present': False})
        unknown = json.dumps({'schema': 'arctic-native-host-frame-v1', 'stage': 'live',
                              'status': 'unknown', 'error': 'value-error',
                              'release_acceptance': False,
                              'product_change_authorized': False}).encode()
        self.assertEqual(reader.validate_host_frame({'host_frame_receipt': unknown}, native),
                         {'present': True, 'status': 'unknown', 'error_family': 'value-error'})

    def test_strict_json_rejects_duplicates_and_nonfinite_numbers(self):
        with self.assertRaises(RuntimeError):
            reader.strict_json(b'{"x":1,"x":2}', 100)
        with self.assertRaises(RuntimeError):
            reader.strict_json(b'{"x":NaN}', 100)

    def test_metadata_validation_is_exact(self):
        artifact = {'id': reader.ARTIFACT_ID, 'name': reader.ARTIFACT_NAME,
                    'expired': False, 'size_in_bytes': reader.ARTIFACT_BYTES,
                    'digest': 'sha256:' + reader.ARTIFACT_SHA256,
                    'workflow_run': {'id': reader.RUN_ID, 'head_sha': reader.RUN_HEAD}}
        reader.validate_artifact(artifact)
        for key, changed in (('expired', True), ('size_in_bytes', 1),
                             ('digest', 'sha256:' + '0' * 64)):
            bad = dict(artifact); bad[key] = changed
            with self.assertRaises(RuntimeError):
                reader.validate_artifact(bad)

    def test_execution_checker_and_native_source_are_pinned(self):
        values = self.raws()
        execution = json.loads(values['execution.json'])
        pins = reader.load_source_provenance(self.qualification())
        for field in ('checker_sha256', 'native_source_sha256'):
            changed = json.loads(json.dumps(execution))
            changed['checker'][field] = '0' * 64
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                reader.validate_execution(json.dumps(changed).encode(), self.qualification(),
                                          values['harness/native-stop-install.json'], pins)

    def test_display_rejects_controller_duplicate_console_and_split_device(self):
        raw = self.raws()['harness/taskbar-display-install.json']
        value = json.loads(raw)
        expected = reader.load_source_provenance(self.qualification())['taskbar_display_sha256']
        reader.validate_display(raw, expected)
        mutations = (
            lambda row: row.update(controller_sha256='0' * 64),
            lambda row: row['heads'][1].update(console_id=row['heads'][0]['console_id']),
            lambda row: row['heads'][1].update(device_address='pci/0000/02.0'),
        )
        for mutate in mutations:
            changed = json.loads(json.dumps(value)); mutate(changed)
            with self.subTest(value=changed), self.assertRaises(RuntimeError):
                reader.validate_display(json.dumps(changed).encode(), expected)

    def test_host_frame_binds_comparison_oracle_and_native_source(self):
        native = reader.load_source_provenance(self.qualification())['native_source_sha256']
        image = self.png(); receipt = self.captured_host_frame(native, image)
        result = reader.validate_host_frame(
            {'host_frame_receipt': json.dumps(receipt).encode(),
             'host_frame_image': image}, native)
        self.assertEqual(result['oracle_status'], 'matched')
        mutations = (
            lambda row: row['oracle'].update(status='unmatched'),
            lambda row: row.update(native_oracle_source_sha256='0' * 64),
        )
        for mutate in mutations:
            changed = json.loads(json.dumps(receipt)); mutate(changed)
            with self.subTest(value=changed), self.assertRaises(RuntimeError):
                reader.validate_host_frame(
                    {'host_frame_receipt': json.dumps(changed).encode(),
                     'host_frame_image': image}, native)

    def test_png_requires_complete_chunks_crc_and_complete_pixel_stream(self):
        image = self.png(1, 1)
        self.assertEqual(reader.png_dimensions(image), (1, 1))
        with self.assertRaises(RuntimeError):
            reader.png_dimensions(image[:-1])
        forged = bytearray(image); forged[-1] ^= 1
        with self.assertRaises(RuntimeError):
            reader.png_dimensions(bytes(forged))
        # Keep valid chunk CRCs while supplying a complete zlib stream with no pixel row.
        def chunk(kind, data):
            return (len(data).to_bytes(4, 'big') + kind + data
                    + (zlib.crc32(kind + data) & 0xffffffff).to_bytes(4, 'big'))
        ihdr = b'\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00'
        empty = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                 + chunk(b'IDAT', zlib.compress(b'')) + chunk(b'IEND', b''))
        with self.assertRaises(RuntimeError):
            reader.png_dimensions(empty)
        bad_filter = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                      + chunk(b'IDAT', zlib.compress(b'\x05\x00\x00\x00'))
                      + chunk(b'IEND', b''))
        with self.assertRaises(RuntimeError):
            reader.png_dimensions(bad_filter)
        unknown_critical = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                            + chunk(b'ABCD', b'fixed')
                            + chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00'))
                            + chunk(b'IEND', b''))
        with self.assertRaises(RuntimeError):
            reader.png_dimensions(unknown_critical)
        compressed = zlib.compress(b'\x00\x00\x00\x00')
        split = max(1, len(compressed) // 2)
        nonconsecutive = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', ihdr)
                          + chunk(b'IDAT', compressed[:split])
                          + chunk(b'tEXt', b'key\x00value')
                          + chunk(b'IDAT', compressed[split:]) + chunk(b'IEND', b''))
        with self.assertRaises(RuntimeError):
            reader.png_dimensions(nonconsecutive)


if __name__ == '__main__':
    unittest.main()
