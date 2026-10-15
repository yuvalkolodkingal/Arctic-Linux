#!/usr/bin/env python3
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import tempfile
import unittest
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
PATH = Path(__file__).with_name('read.py')
SPEC = importlib.util.spec_from_file_location('final_iso_reader', PATH)
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


class ReaderTests(unittest.TestCase):
    def manifest(self, ready=True):
        return {
            'schema': 'arctic-final-iso-identity-reader-v1', 'ready': ready,
            'repository': R.REPOSITORY, 'workflow': R.WORKFLOW,
            'run_id': R.RUN_ID, 'run_attempt': 1, 'source_sha': R.SOURCE_SHA,
            'iso_artifact_id': 9001, 'receipt_artifact_id': 9002,
        }

    def receipt(self):
        image = {'name': f'Arctic-Linux-1.2-candidate-{R.RUN_ID}-1-x86_64.iso',
                 'bytes': 1_936_000_000, 'sha256': '1' * 64}
        inputs = {'expected_source_sha': R.SOURCE_SHA, 'release': False, 'tag': '',
                  'prerelease': True, 'draft': False, 'nix_acceptance': False,
                  'performance_acceptance': False, 'boot_test': True,
                  'performance_mode': 'frozen-external-paired-v1'}
        startup = {}
        for index, (lane, (firmware, mode)) in enumerate({
                'uefi-try': ('uefi', 'try'), 'bios-install': ('bios', 'install'),
                'uefi-safe': ('uefi', 'safe')}.items(), 1):
            startup[lane] = {'firmware': firmware, 'mode': mode, 'status': 'passed',
                             'serial_bytes': index * 100, 'serial_sha256': str(index) * 64}
        return {'schema': 'arctic-producer-performance-receipt-v1',
                'repository': R.REPOSITORY, 'workflow': R.WORKFLOW,
                'event': 'workflow_dispatch', 'source_sha': R.SOURCE_SHA,
                'run_id': R.RUN_ID, 'run_attempt': 1,
                'mode': 'frozen-external-paired-v1', 'release_acceptance': False,
                'inputs': inputs, 'image': image, 'startup_results': startup}

    @staticmethod
    def zipped(name, raw, mode=stat.S_IFREG | 0o600, extra=None):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_STORED) as archive:
            info = zipfile.ZipInfo(name)
            info.external_attr = mode << 16
            archive.writestr(info, raw)
            if extra:
                archive.writestr(extra, b'x')
        return output.getvalue()

    def fixture(self):
        receipt_raw = (json.dumps(self.receipt(), sort_keys=True, indent=2) + '\n').encode()
        receipt_zip = self.zipped(R.RECEIPT_NAME, receipt_raw)
        iso_digest = 'a' * 64
        run = {'id': R.RUN_ID, 'head_sha': R.SOURCE_SHA, 'event': 'workflow_dispatch',
               'path': R.WORKFLOW, 'run_attempt': 1, 'status': 'completed',
               'conclusion': 'success'}
        def artifact(artifact_id, name, size, digest):
            return {'id': artifact_id, 'name': name, 'expired': False,
                    'size_in_bytes': size, 'digest': 'sha256:' + digest,
                    'workflow_run': {'id': R.RUN_ID, 'head_sha': R.SOURCE_SHA}}
        iso = artifact(9001, 'arctic-linux-iso', 1_936_100_000, iso_digest)
        small = artifact(9002, 'arctic-external-producer-receipt', len(receipt_zip),
                         hashlib.sha256(receipt_zip).hexdigest())
        step_names = ('Boot test in QEMU (UEFI, Try mode)', 'Required optimized ISO size',
                      'Write external performance producer receipt',
                      'Upload external-mode ISO and producer receipt (workflow artifact)')
        steps = [{'name': name, 'status': 'completed', 'conclusion': 'success'}
                 for name in step_names]
        steps.append({'name': 'Paired KVM performance acceptance', 'status': 'completed',
                      'conclusion': 'skipped'})
        jobs = {'total_count': 2, 'jobs': [
            {'name': 'iso', 'run_attempt': 1, 'head_sha': R.SOURCE_SHA,
             'status': 'completed', 'conclusion': 'success', 'steps': steps},
            {'name': 'Publish the completed ISO', 'run_attempt': 1,
             'head_sha': R.SOURCE_SHA, 'status': 'completed', 'conclusion': 'skipped',
             'steps': []},
        ]}
        responses = {
            f'/actions/runs/{R.RUN_ID}': run,
            '/actions/artifacts/9001': iso,
            '/actions/artifacts/9002': small,
            f'/actions/runs/{R.RUN_ID}/jobs?filter=all&per_page=100': jobs,
        }
        return receipt_zip, responses

    def test_disabled_and_placeholder_manifests_fail_closed(self):
        manifest = self.manifest(ready=False)
        with self.assertRaisesRegex(RuntimeError, 'remains disabled'):
            R.validate_manifest(manifest)
        manifest['ready'] = True
        manifest['iso_artifact_id'] = 0
        with self.assertRaisesRegex(RuntimeError, 'have not been pinned'):
            R.validate_manifest(manifest)

    def test_manifest_rejects_changed_run_source_or_workflow(self):
        for field, value in (('run_id', R.RUN_ID + 1), ('run_attempt', 2),
                             ('source_sha', '0' * 40), ('workflow', 'other.yml'),
                             ('repository', 'owner/other')):
            with self.subTest(field=field):
                manifest = self.manifest()
                manifest[field] = value
                with self.assertRaisesRegex(RuntimeError, 'Pinned producer'):
                    R.validate_manifest(manifest)

    def test_receipt_archive_rejects_traversal_extra_and_symlink(self):
        raw = b'{}\n'
        duplicate = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(duplicate, 'w', zipfile.ZIP_STORED) as archive:
                archive.writestr(R.RECEIPT_NAME, raw)
                archive.writestr(R.RECEIPT_NAME, raw)
        bad = (self.zipped('../' + R.RECEIPT_NAME, raw),
               self.zipped(R.RECEIPT_NAME, raw, extra='other.txt'),
               duplicate.getvalue(),
               self.zipped(R.RECEIPT_NAME, raw, stat.S_IFLNK | 0o777),
               self.zipped(R.RECEIPT_NAME, b'x' * (R.MAX_RECEIPT_BYTES + 1)))
        for archive in bad:
            with self.subTest(size=len(archive)):
                with self.assertRaises(RuntimeError):
                    R.receipt_member(archive)

    def test_success_downloads_only_receipt_and_prints_only_safe_fields(self):
        receipt_zip, responses = self.fixture()
        downloaded = []
        def api_call(path):
            return responses[path]
        def downloader(artifact_id, target):
            downloaded.append(artifact_id)
            target.write_bytes(receipt_zip)
        fetch = R.load_fetch_contract()
        with tempfile.TemporaryDirectory() as directory:
            report = R.inspect(self.manifest(), Path(directory), api_call, downloader, fetch)
        self.assertEqual(downloaded, [9002])
        output = io.StringIO()
        R.emit(report, output)
        keys = [line.split('=', 1)[0] for line in output.getvalue().splitlines()]
        self.assertEqual(keys, [
            'ISO_NAME', 'ISO_BYTES', 'ISO_SHA256', 'PRODUCER_RECEIPT_SHA256',
            'STARTUP_UEFI_TRY_STATUS', 'STARTUP_UEFI_TRY_SERIAL_BYTES',
            'STARTUP_UEFI_TRY_SERIAL_SHA256', 'STARTUP_BIOS_INSTALL_STATUS',
            'STARTUP_BIOS_INSTALL_SERIAL_BYTES', 'STARTUP_BIOS_INSTALL_SERIAL_SHA256',
            'STARTUP_UEFI_SAFE_STATUS', 'STARTUP_UEFI_SAFE_SERIAL_BYTES',
            'STARTUP_UEFI_SAFE_SERIAL_SHA256', 'ARCHIVE_BYTES', 'ARCHIVE_SHA256',
            'ARTIFACT_ID'])
        self.assertNotIn('transcript', output.getvalue().lower())
        self.assertNotIn('audio', output.getvalue().lower())

    def test_downloaded_archive_digest_and_identity_are_enforced(self):
        receipt_zip, responses = self.fixture()
        responses['/actions/artifacts/9002']['digest'] = 'sha256:' + 'f' * 64
        def downloader(_artifact_id, target):
            target.write_bytes(receipt_zip)
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'bytes differ'):
                R.inspect(self.manifest(), Path(directory), responses.__getitem__, downloader,
                          R.load_fetch_contract())

    def test_workflow_is_read_only_branch_and_marker_scoped(self):
        workflow = (ROOT / '.github/workflows/read-final-iso-38823208615.yml').read_text()
        self.assertIn('branches: [codex/prepare-final-iso-reader-20261015]', workflow)
        self.assertIn('paths: [.github/final-iso-reader-38823208615.activate]', workflow)
        self.assertIn("github.ref == 'refs/heads/codex/prepare-final-iso-reader-20261015'", workflow)
        self.assertNotIn('workflow_dispatch:', workflow)
        self.assertNotIn('contents: write', workflow)


if __name__ == '__main__':
    unittest.main()
