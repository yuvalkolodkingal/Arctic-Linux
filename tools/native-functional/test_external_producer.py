"""Synthetic adversarial producer transport controls; these are not VM evidence."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load('external_producer_fetch', ROOT / 'tools/native-functional/fetch-image.py')
W = load('external_producer_writer', ROOT / 'tools/performance/producer-receipt.py')


class ExternalProducerControls(unittest.TestCase):
    def inputs(self):
        return dict(expected_source_sha='1' * 40, release=False, tag='', prerelease=True,
                    draft=False, nix_acceptance=False, performance_acceptance=False,
                    boot_test=True, performance_mode=F.EXTERNAL_MODE)

    def image(self):
        return dict(run_id=7, source_sha='1' * 40, artifact_id=8, archive_bytes=100,
                    archive_sha256='2' * 64, producer_mode=F.EXTERNAL_MODE,
                    producer_receipt_sha256='3' * 64,
                    name='Arctic-Linux-1.2-candidate-7-1-x86_64.iso', bytes=3,
                    sha256=hashlib.sha256(b'iso').hexdigest())

    def receipt(self):
        image = self.image()
        return dict(schema='arctic-producer-performance-receipt-v1',
                    repository='yuvalkolodkingal/Arctic-Linux', workflow='.github/workflows/iso.yml',
                    event='workflow_dispatch', source_sha=image['source_sha'], run_id=7,
                    run_attempt=1, mode=F.EXTERNAL_MODE, release_acceptance=False,
                    inputs=self.inputs(), image={key: image[key] for key in ('name', 'bytes', 'sha256')},
                    startup_results={name: dict(firmware=firmware, mode=mode, status='passed',
                                               serial_bytes=100, serial_sha256='4' * 64)
                                     for name, (firmware, mode) in F.STARTUP_LANES.items()})

    def jobs(self):
        return [dict(name='iso', head_sha=self.image()['source_sha'], status='completed',
                     conclusion='success', run_attempt=1,
                     steps=[dict(name=name, status='completed', conclusion='success') for name in
                            (*F.BOOT_STEPS, F.SIZE_STEP, F.RECEIPT_STEP, F.EXTERNAL_UPLOAD_STEP)] +
                           [dict(name=F.PAIRED_STEP, status='completed', conclusion='skipped')]),
                dict(name='Publish the completed ISO', head_sha=self.image()['source_sha'],
                     status='completed', conclusion='skipped', run_attempt=1)]

    def environment(self, root):
        inputs = self.inputs()
        event = root / 'dispatch.json'
        event.write_text(json.dumps(dict(inputs={key: ('true' if value else 'false') if type(value) is bool
                                                else value for key, value in inputs.items()})))
        return dict(GITHUB_SHA='1' * 40, GITHUB_REPOSITORY='yuvalkolodkingal/Arctic-Linux',
                    GITHUB_EVENT_NAME='workflow_dispatch',
                    GITHUB_WORKFLOW_REF='yuvalkolodkingal/Arctic-Linux/.github/workflows/iso.yml@refs/heads/test',
                    GITHUB_RUN_ID='7', GITHUB_RUN_ATTEMPT='1',
                    PRODUCER_INPUTS_JSON=json.dumps(inputs), GITHUB_EVENT_PATH=str(event))

    def fixture(self, root):
        environment = self.environment(root)
        image = root / self.image()['name']
        image.write_bytes(b'iso')
        image.with_name(image.name + '.sha256').write_text(self.image()['sha256'] + '  ' + image.name + '\n')
        for lane, (_, mode) in F.STARTUP_LANES.items():
            serial = root / 'startup' / lane / 'serial.log'
            serial.parent.mkdir(parents=True)
            serial.write_text('ARCTIC-COLLECT-BEGIN\nARCTIC-STARTUP-PASS=' + mode + '\nARCTIC-COLLECT-END\n')
        return environment, image, root / 'startup', root / F.RECEIPT_NAME

    def test_explicit_external_receipt_and_first_attempt_job_are_accepted(self):
        self.assertEqual(F.validate_external_receipt(self.receipt(), self.image()), self.receipt())
        F.validate_external_producer_steps(self.image(), self.jobs())
        F.validate_boot_steps(self.image(), self.jobs())

    def test_missing_unknown_legacy_and_unpinned_modes_cannot_use_receipt(self):
        for mode in (None, 'unknown', F.LEGACY_MODE):
            image = self.image()
            if mode is None:
                image.pop('producer_mode')
            else:
                image['producer_mode'] = mode
            with self.subTest(mode=mode), self.assertRaises(RuntimeError):
                F.validate_external_receipt(self.receipt(), image)
        for pin in (None, 'x' * 64, True):
            image = dict(self.image(), producer_receipt_sha256=pin)
            with self.subTest(pin=pin), self.assertRaises(RuntimeError):
                F.validate_external_receipt(self.receipt(), image)

    def test_receipt_source_run_size_mode_scope_and_types_are_strict(self):
        mutations = [('schema', 'unknown'), ('repository', 'other/Arctic-Linux'), ('workflow', 'other.yml'),
                     ('event', 'push'), ('source_sha', '5' * 40), ('run_id', 8), ('run_id', True),
                     ('run_attempt', 2), ('run_attempt', True), ('mode', F.LEGACY_MODE),
                     ('release_acceptance', True), ('release_acceptance', 0)]
        for key, value in mutations:
            receipt = copy.deepcopy(self.receipt()); receipt[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                F.validate_external_receipt(receipt, self.image())
        for key, value in (('bytes', True), ('bytes', 4), ('sha256', '6' * 64), ('name', 'other.iso')):
            receipt = copy.deepcopy(self.receipt()); receipt['image'][key] = value
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                F.validate_external_receipt(receipt, self.image())
        receipt = self.receipt(); receipt['untyped_extra'] = True
        with self.assertRaises(RuntimeError): F.validate_external_receipt(receipt, self.image())

    def test_dispatch_mutually_exclusive_booleans_and_exact_fields_are_required(self):
        mutations = [('release', True), ('boot_test', False), ('performance_acceptance', True),
                     ('release', 'false'), ('release', 0), ('boot_test', 1),
                     ('performance_mode', F.LEGACY_MODE), ('expected_source_sha', '5' * 40),
                     ('nix_acceptance', 'false'), ('tag', 'line\nbreak')]
        for key, value in mutations:
            receipt = copy.deepcopy(self.receipt()); receipt['inputs'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                F.validate_external_receipt(receipt, self.image())
        for fault in ('extra', 'missing'):
            receipt = copy.deepcopy(self.receipt())
            if fault == 'extra': receipt['inputs']['unknown'] = False
            else: receipt['inputs'].pop('release')
            with self.subTest(fault=fault), self.assertRaises(RuntimeError):
                F.validate_external_receipt(receipt, self.image())

    def test_startup_receipt_missing_or_contradictory_results_are_rejected(self):
        for lane in F.STARTUP_LANES:
            for field, value in (('status', 'failed'), ('mode', 'disk'), ('firmware', 'other'),
                                 ('serial_bytes', True), ('serial_bytes', 0),
                                 ('serial_bytes', 10_000_001), ('serial_sha256', 'bad')):
                receipt = copy.deepcopy(self.receipt()); receipt['startup_results'][lane][field] = value
                with self.subTest(lane=lane, field=field, value=value), self.assertRaises(RuntimeError):
                    F.validate_external_receipt(receipt, self.image())
            receipt = self.receipt(); receipt['startup_results'].pop(lane)
            with self.assertRaises(RuntimeError): F.validate_external_receipt(receipt, self.image())

    def test_external_job_requires_size_startup_receipt_upload_and_skipped_paired(self):
        for index in range(len(self.jobs()[0]['steps'])):
            for fault in ('missing', 'duplicate', 'failure', 'opposite', 'running'):
                jobs = copy.deepcopy(self.jobs()); steps = jobs[0]['steps']
                if fault == 'missing': steps.pop(index)
                elif fault == 'duplicate': steps.append(copy.deepcopy(steps[index]))
                elif fault == 'running': steps[index]['status'] = 'in_progress'
                else: steps[index]['conclusion'] = 'failure' if fault == 'failure' else (
                    'success' if steps[index]['conclusion'] == 'skipped' else 'skipped')
                with self.subTest(index=index, fault=fault), self.assertRaises(RuntimeError):
                    F.validate_external_producer_steps(self.image(), jobs)

    def test_external_job_failed_rerun_wrong_source_or_publication_is_rejected(self):
        for index in (0, 1):
            for key, value in (('run_attempt', 2), ('run_attempt', True), ('head_sha', '5' * 40),
                               ('status', 'in_progress'), ('conclusion', 'failure')):
                jobs = copy.deepcopy(self.jobs()); jobs[index][key] = value
                with self.subTest(index=index, key=key, value=value), self.assertRaises(RuntimeError):
                    F.validate_external_producer_steps(self.image(), jobs)
        for conclusion in ('success', 'cancelled', None):
            jobs = self.jobs(); jobs[1]['conclusion'] = conclusion
            with self.subTest(conclusion=conclusion), self.assertRaises(RuntimeError):
                F.validate_external_producer_steps(self.image(), jobs)
        for jobs in (self.jobs()[:1], self.jobs() + [self.jobs()[1]], self.jobs() + [self.jobs()[0]]):
            with self.assertRaises(RuntimeError): F.validate_external_producer_steps(self.image(), jobs)

    def test_failed_historical_producer_is_rejected_in_both_modes(self):
        image = json.loads((ROOT / 'tools/native-functional/execution-manifest.json').read_text())['image']
        run = dict(id=image['run_id'], head_sha=image['source_sha'], event='workflow_dispatch',
                   path='.github/workflows/iso.yml', run_attempt=1, status='completed', conclusion='failure')
        for mode in (F.LEGACY_MODE, F.EXTERNAL_MODE):
            pinned = dict(image, producer_mode=mode)
            if mode == F.EXTERNAL_MODE: pinned['producer_receipt_sha256'] = '3' * 64
            with self.subTest(mode=mode), self.assertRaises(RuntimeError): F.validate(pinned, run, {})

    def test_actual_dispatch_payload_context_and_first_attempt_must_match(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); environment = self.environment(root)
            self.assertEqual(W.request(environment)['inputs'], self.inputs())
            for key, value in (('GITHUB_RUN_ATTEMPT', '2'), ('GITHUB_EVENT_NAME', 'push'),
                               ('GITHUB_REPOSITORY', 'other/Arctic-Linux'),
                               ('GITHUB_WORKFLOW_REF', 'yuvalkolodkingal/Arctic-Linux/other.yml@ref'),
                               ('GITHUB_RUN_ID', '01')):
                with self.subTest(key=key), self.assertRaises(RuntimeError):
                    W.request(dict(environment, **{key: value}))
            event = Path(environment['GITHUB_EVENT_PATH'])
            data = json.loads(event.read_text()); data['inputs']['boot_test'] = 'false'; event.write_text(json.dumps(data))
            with self.assertRaises(RuntimeError): W.request(environment)

    def test_observed_default_empty_tag_omission_gets_canonical_typed_receipt(self):
        # Verbatim public inputs context from failed first-attempt ISO
        # 38031125436; the separate dispatch artifact retained all nine fields.
        observed = (ROOT / 'tools/tests/fixtures/external-producer-inputs-38031125436.json').read_text()
        inputs = json.loads(observed)
        self.assertEqual(set(inputs), set(F.INPUT_TYPES) - {'tag'})
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); environment, image, startup, output = self.fixture(root)
            inputs['expected_source_sha'] = environment['GITHUB_SHA']
            environment['PRODUCER_INPUTS_JSON'] = json.dumps(inputs)
            result = W.write_receipt(environment, image, startup, output)
            self.assertEqual(result['inputs'], self.inputs())
            self.assertEqual(set(result['inputs']), set(F.INPUT_TYPES))
            self.assertTrue(all(type(result['inputs'][key]) is kind for key, kind in F.INPUT_TYPES.items()))
            pinned = dict(self.image(), producer_receipt_sha256=F.digest(output))
            self.assertEqual(F.read_receipt(output.read_bytes(), pinned), result)
            # Stored receipts never gain the context-only omission allowance.
            result['inputs'].pop('tag')
            with self.assertRaises(RuntimeError): F.validate_external_receipt(result, pinned)

    def test_context_omission_does_not_restore_other_fields_or_coerce_types(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = self.environment(Path(folder))
            for omit_tag in (False, True):
                for key in set(F.INPUT_TYPES) - {'tag'}:
                    inputs = self.inputs()
                    if omit_tag: inputs.pop('tag')
                    inputs.pop(key)
                    with self.subTest(omit_tag=omit_tag, missing=key), self.assertRaises(RuntimeError):
                        W.request(dict(environment, PRODUCER_INPUTS_JSON=json.dumps(inputs)))
                inputs = self.inputs()
                if omit_tag: inputs.pop('tag')
                inputs['unknown'] = False
                with self.subTest(omit_tag=omit_tag, unknown=True), self.assertRaises(RuntimeError):
                    W.request(dict(environment, PRODUCER_INPUTS_JSON=json.dumps(inputs)))
                wrong_types = {key: ('true', 'false', 0, 1, None) if kind is bool else (None, False, 1)
                               for key, kind in F.INPUT_TYPES.items() if key != 'tag'}
                for key, values in wrong_types.items():
                    for value in values:
                        inputs = self.inputs()
                        if omit_tag: inputs.pop('tag')
                        inputs[key] = value
                        with self.subTest(omit_tag=omit_tag, key=key, value=value), self.assertRaises(RuntimeError):
                            W.request(dict(environment, PRODUCER_INPUTS_JSON=json.dumps(inputs)))
            for tag in (None, False, 0, [], {}, 'v1.2.1', ' ', '\n'):
                inputs = dict(self.inputs(), tag=tag)
                with self.subTest(tag=tag), self.assertRaises(RuntimeError):
                    W.request(dict(environment, PRODUCER_INPUTS_JSON=json.dumps(inputs)))
            raw = json.dumps(self.inputs())[:-1] + ', "tag": ""}'
            with self.assertRaisesRegex(RuntimeError, 'Duplicate producer dispatch JSON field'):
                W.request(dict(environment, PRODUCER_INPUTS_JSON=raw))

    def test_optional_empty_tag_projection_matrix_keeps_all_nine_canonical_fields(self):
        # Event omission is a synthetic default-equivalence control, not a
        # claim that the failed producer exposed its event projection.
        for omit_context in (False, True):
            for omit_event in (False, True):
                with self.subTest(omit_context=omit_context, omit_event=omit_event), tempfile.TemporaryDirectory() as folder:
                    environment = self.environment(Path(folder))
                    inputs = self.inputs()
                    if omit_context: inputs.pop('tag')
                    environment['PRODUCER_INPUTS_JSON'] = json.dumps(inputs)
                    event = Path(environment['GITHUB_EVENT_PATH'])
                    data = json.loads(event.read_text())
                    if omit_event: data['inputs'].pop('tag')
                    event.write_text(json.dumps(data))
                    self.assertEqual(W.request(environment)['inputs'], self.inputs())

    def test_frozen_flags_and_exact_event_binding_survive_context_omission(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); environment = self.environment(root)
            for omit_tag in (False, True):
                for key, value in (('tag', 'v1.2.1'), ('prerelease', False), ('draft', True),
                                   ('nix_acceptance', True), ('release', True), ('boot_test', False),
                                   ('performance_acceptance', True), ('performance_mode', F.LEGACY_MODE),
                                   ('expected_source_sha', '5' * 40)):
                    inputs = self.inputs()
                    if omit_tag: inputs.pop('tag')
                    inputs[key] = value
                    with self.subTest(omit_tag=omit_tag, key=key), self.assertRaises(RuntimeError):
                        W.request(dict(environment, PRODUCER_INPUTS_JSON=json.dumps(inputs)))
            inputs = self.inputs(); inputs.pop('tag')
            environment['PRODUCER_INPUTS_JSON'] = json.dumps(inputs)
            event = Path(environment['GITHUB_EVENT_PATH'])
            original = json.loads(event.read_text())
            for fault in ('nonempty-tag', 'unknown', 'missing-release',
                          'typed-bool', 'wrong-bool', 'duplicate-tag'):
                data = copy.deepcopy(original)
                if fault == 'nonempty-tag': data['inputs']['tag'] = 'v1.2.1'
                elif fault == 'unknown': data['inputs']['unknown'] = 'false'
                elif fault == 'missing-release': data['inputs'].pop('release')
                elif fault == 'typed-bool': data['inputs']['release'] = False
                elif fault == 'wrong-bool': data['inputs']['boot_test'] = 'false'
                raw = json.dumps(data)
                if fault == 'duplicate-tag':
                    raw = raw.replace('"tag": ""', '"tag": "", "tag": ""')
                event.write_text(raw)
                with self.subTest(fault=fault), self.assertRaises(RuntimeError): W.request(environment)
            for omit_tag in (False, True):
                for key in set(F.INPUT_TYPES) - {'tag'}:
                    data = copy.deepcopy(original)
                    if omit_tag: data['inputs'].pop('tag')
                    data['inputs'].pop(key)
                    event.write_text(json.dumps(data))
                    with self.subTest(omit_tag=omit_tag, missing_event=key), self.assertRaises(RuntimeError):
                        W.request(environment)
                data = copy.deepcopy(original)
                if omit_tag: data['inputs'].pop('tag')
                data['inputs']['unknown'] = 'false'
                event.write_text(json.dumps(data))
                with self.subTest(omit_tag=omit_tag, unknown_event=True), self.assertRaises(RuntimeError):
                    W.request(environment)

    def test_writer_records_actual_iso_and_complete_unique_startup_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); environment, image, startup, output = self.fixture(root)
            result = W.write_receipt(environment, image, startup, output)
            self.assertEqual(result['image']['sha256'], hashlib.sha256(image.read_bytes()).hexdigest())
            for lane, value in result['startup_results'].items():
                raw = (startup / lane / 'serial.log').read_bytes()
                self.assertEqual(value['serial_bytes'], len(raw))
                self.assertEqual(value['serial_sha256'], hashlib.sha256(raw).hexdigest())
            pinned = dict(self.image(), producer_receipt_sha256=F.digest(output))
            self.assertEqual(F.read_receipt(output.read_bytes(), pinned), result)
            with self.assertRaises(RuntimeError): W.write_receipt(environment, image, startup, output)

    def test_writer_rejects_partial_duplicate_wrong_mode_symlink_and_mismatched_checksum(self):
        for fault in ('partial', 'duplicate', 'wrong-mode', 'extra-mode', 'failure', 'symlink', 'checksum', 'missing'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); environment, image, startup, output = self.fixture(root)
                serial = startup / 'uefi-try/serial.log'
                if fault == 'partial': serial.write_text('ARCTIC-COLLECT-BEGIN\nARCTIC-STARTUP-PASS=try\n')
                elif fault == 'duplicate': serial.write_text(serial.read_text() + 'ARCTIC-COLLECT-END\n')
                elif fault == 'wrong-mode': serial.write_text(serial.read_text().replace('PASS=try', 'PASS=install'))
                elif fault == 'extra-mode': serial.write_text(serial.read_text() + 'ARCTIC-STARTUP-PASS=install\n')
                elif fault == 'failure': serial.write_text(serial.read_text() + 'ARCTIC-STARTUP-FAILED\n')
                elif fault == 'symlink':
                    saved = root / 'saved.log'; serial.rename(saved); serial.symlink_to(saved)
                elif fault == 'missing': serial.unlink()
                else: image.with_name(image.name + '.sha256').write_text('bad\n')
                with self.assertRaises(RuntimeError): W.write_receipt(environment, image, startup, output)
                self.assertFalse(output.exists())

    def test_receipt_json_duplicate_fields_or_wrong_exact_byte_hash_are_rejected(self):
        raw = json.dumps(self.receipt()).encode()
        image = dict(self.image(), producer_receipt_sha256=hashlib.sha256(raw).hexdigest())
        F.read_receipt(raw, image)
        with self.assertRaises(RuntimeError): F.read_receipt(raw + b'\n', image)
        duplicate = raw[:-1] + b',"run_attempt":1}'
        image['producer_receipt_sha256'] = hashlib.sha256(duplicate).hexdigest()
        with self.assertRaises(RuntimeError): F.read_receipt(duplicate, image)

    def test_archive_requires_explicit_byte_pinned_receipt_and_rejects_wrong_mode(self):
        for fault in ('valid', 'missing', 'changed', 'legacy', 'duplicate'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as folder:
                root = Path(folder); image = self.image(); raw = json.dumps(self.receipt()).encode()
                image['producer_receipt_sha256'] = hashlib.sha256(raw).hexdigest()
                if fault == 'legacy':
                    image.pop('producer_mode'); image.pop('producer_receipt_sha256')
                wanted = 'iso/' + image['name']; archive = root / 'artifact.zip'
                with zipfile.ZipFile(archive, 'w') as output:
                    output.writestr(wanted, b'iso')
                    output.writestr(wanted + '.sha256', image['sha256'] + '  ' + image['name'] + '\n')
                    output.writestr('BUILD-INFO', 'git_commit=' + image['source_sha'] + '\narctic_repos=enabled\n')
                    if fault != 'missing': output.writestr(F.RECEIPT_NAME, raw + (b'\n' if fault == 'changed' else b''))
                    if fault == 'duplicate': output.writestr(F.RECEIPT_NAME, raw)
                if fault == 'valid':
                    F.extract(archive, root / 'inputs', image)
                    self.assertEqual((root / 'inputs' / F.RECEIPT_NAME).read_bytes(), raw)
                else:
                    with self.assertRaises(RuntimeError): F.extract(archive, root / 'inputs', image)
                    self.assertFalse((root / 'inputs').exists())

    def test_oversized_compressed_receipt_is_rejected_before_any_archive_read(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); image = self.image(); wanted = 'iso/' + image['name']
            archive = root / 'compressed.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as output:
                output.writestr(wanted, b'iso')
                output.writestr(wanted + '.sha256', image['sha256'] + '  ' + image['name'] + '\n')
                output.writestr('BUILD-INFO', 'git_commit=' + image['source_sha'] + '\narctic_repos=enabled\n')
                output.writestr(F.RECEIPT_NAME, b' ' * 32_769)
            with patch.object(zipfile.ZipFile, 'read', side_effect=AssertionError('oversized member was read')) as read:
                with self.assertRaisesRegex(RuntimeError, 'Oversized producer receipt member'):
                    F.extract(archive, root / 'inputs', image)
                read.assert_not_called()
            self.assertFalse((root / 'inputs').exists())


if __name__ == '__main__':
    unittest.main()
