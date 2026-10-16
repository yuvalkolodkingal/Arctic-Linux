import hashlib
from io import BytesIO
import importlib.util
import json
from pathlib import Path
import unittest
import zipfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location(
    'reader', HERE / 'read-producer-receipt-388796.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)


def fixture():
    startup = {}
    for index, (lane, (firmware, mode)) in enumerate(reader.LANES.items(), 1):
        startup[lane] = {
            'firmware': firmware,
            'mode': mode,
            'status': 'passed',
            'serial_bytes': index * 100,
            'serial_sha256': str(index) * 64,
        }
    return {
        'schema': 'arctic-producer-performance-receipt-v1',
        'repository': reader.REPOSITORY,
        'workflow': reader.WORKFLOW_PATH,
        'event': 'workflow_dispatch',
        'source_sha': reader.SOURCE_SHA,
        'run_id': reader.RUN_ID,
        'run_attempt': reader.RUN_ATTEMPT,
        'mode': 'frozen-external-paired-v1',
        'release_acceptance': False,
        'inputs': dict(reader.INPUTS),
        'image': {
            'name': reader.IMAGE_NAME,
            'bytes': 1_900_000_000,
            'sha256': 'a' * 64,
        },
        'startup_results': startup,
    }


def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


class ReceiptReaderTest(unittest.TestCase):
    def test_strict_schema_accepts_only_public_producer_fields(self):
        value = fixture()
        raw = encoded(value)
        self.assertEqual(reader.strict_receipt(raw), value)
        projection = reader.public_projection(value, raw)
        self.assertEqual(set(projection), {'artifact', 'receipt_sha256', 'receipt'})
        self.assertEqual(projection['receipt_sha256'], hashlib.sha256(raw).hexdigest())

    def test_strict_schema_rejects_extra_duplicate_wrong_type_and_failed_lane(self):
        mutations = []
        extra = fixture(); extra['private_log'] = 'forbidden'; mutations.append(encoded(extra))
        duplicate = encoded(fixture()).replace(
            b'  "run_id": 38879661832,',
            b'  "run_id": 38879661832,\n  "run_id": 38879661832,', 1)
        mutations.append(duplicate)
        wrong_type = fixture(); wrong_type['inputs']['release'] = 0; mutations.append(encoded(wrong_type))
        failed = fixture(); failed['startup_results']['uefi-safe']['status'] = 'failed'; mutations.append(encoded(failed))
        oversized = fixture(); oversized['image']['bytes'] = 2_000_000_000; mutations.append(encoded(oversized))
        for raw in mutations:
            with self.subTest(raw=hashlib.sha256(raw).hexdigest()):
                with self.assertRaises((ValueError, json.JSONDecodeError)):
                    reader.strict_receipt(raw)

    def test_archive_rejects_wrong_digest_and_unsafe_inventory(self):
        original_bytes = reader.ARTIFACT_BYTES
        original_sha = reader.ARTIFACT_SHA256
        try:
            for names in ([reader.RECEIPT_MEMBER], [reader.RECEIPT_MEMBER, 'extra'], ['../receipt']):
                stream = BytesIO()
                with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_STORED) as archive:
                    for name in names:
                        archive.writestr(name, encoded(fixture()))
                raw = stream.getvalue()
                reader.ARTIFACT_BYTES = len(raw)
                reader.ARTIFACT_SHA256 = hashlib.sha256(raw).hexdigest()
                if names == [reader.RECEIPT_MEMBER]:
                    receipt, receipt_raw = reader.validate_archive(raw)
                    self.assertEqual(receipt, fixture())
                    self.assertEqual(receipt_raw, encoded(fixture()))
                    with self.assertRaises(ValueError):
                        reader.validate_archive(raw + b'x')
                else:
                    with self.assertRaises(ValueError):
                        reader.validate_archive(raw)
        finally:
            reader.ARTIFACT_BYTES = original_bytes
            reader.ARTIFACT_SHA256 = original_sha

    def test_run_and_artifact_are_exactly_pinned(self):
        run = {
            'id': reader.RUN_ID, 'run_attempt': 1, 'name': 'ISO',
            'workflow_id': reader.WORKFLOW_ID, 'path': reader.WORKFLOW_PATH,
            'head_branch': reader.SOURCE_BRANCH, 'head_sha': reader.SOURCE_SHA,
            'event': 'workflow_dispatch', 'status': 'completed', 'conclusion': 'success',
            'repository': {'full_name': reader.REPOSITORY},
            'head_repository': {'full_name': reader.REPOSITORY},
        }
        reader.validate_run(run)
        for key, value in (('run_attempt', 2), ('conclusion', 'failure'), ('head_sha', '0' * 40)):
            changed = dict(run, **{key: value})
            with self.assertRaises(ValueError):
                reader.validate_run(changed)
        artifact = {
            'id': reader.ARTIFACT_ID, 'name': reader.ARTIFACT_NAME, 'expired': False,
            'size_in_bytes': reader.ARTIFACT_BYTES,
            'digest': 'sha256:' + reader.ARTIFACT_SHA256,
            'workflow_run': {'id': reader.RUN_ID, 'head_sha': reader.SOURCE_SHA,
                             'head_branch': reader.SOURCE_BRANCH},
        }
        reader.validate_artifact_metadata(artifact)
        artifact['digest'] = 'sha256:' + '0' * 64
        with self.assertRaises(ValueError):
            reader.validate_artifact_metadata(artifact)


if __name__ == '__main__':
    unittest.main()
