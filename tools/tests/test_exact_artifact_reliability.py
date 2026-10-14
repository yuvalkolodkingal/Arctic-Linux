"""Source controls for the non-publishing exact-artifact reliability gate."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


contract = load('exact_artifact_reliability', ROOT / 'tools/reliability/exact-artifact.py')
prepare = load('qualified_release_with_reliability', ROOT / 'tools/qualified-release/prepare.py')


def image():
    return {
        'run_id': 123, 'artifact_id': 456, 'archive_bytes': 789,
        'archive_sha256': 'a' * 64, 'source_sha': 'b' * 40,
        'name': 'Arctic-Linux-1.2-candidate-123-1-x86_64.iso',
        'bytes': 1_500_000_000, 'sha256': 'c' * 64,
        'producer_mode': 'frozen-external-paired-v1',
        'producer_receipt_sha256': 'd' * 64,
    }


def results():
    rows = []
    for stage, check in sorted(contract.AUTOMATED):
        rows.append({'stage': stage, 'check': check, 'status': 'passed', 'evidence': contract.EVIDENCE_FILES[(stage, check)], 'detail': []})
    for stage, check in sorted(contract.UNRUN):
        rows.append({'stage': stage, 'check': check, 'status': 'unrun'})
    return rows


class ContractTests(unittest.TestCase):
    def test_disabled_manifest_has_no_artifact_and_cannot_validate(self):
        value = json.loads((ROOT / contract.MANIFEST).read_text())
        self.assertFalse(value['ready'])
        self.assertIsNone(value['image'])
        self.assertEqual(value['execution_files'], {})
        self.assertFalse((ROOT / contract.MARKER).exists())
        with self.assertRaises(RuntimeError):
            contract.validate_manifest(value)

    def test_manifest_requires_exact_external_image_and_reviewed_files(self):
        hashes = {name: hashlib.sha256(name.encode()).hexdigest() for name in contract.EXECUTION_FILES}
        value = {'ready': True, 'release_acceptance': False, 'version': '1.2',
                 'app_profile': 'lightweight', 'image': image(), 'execution_files': hashes}
        self.assertEqual(contract.validate_manifest(value, hashes), value)
        for mutation in ('release', 'mode', 'file', 'size'):
            bad = copy.deepcopy(value)
            if mutation == 'release': bad['release_acceptance'] = True
            if mutation == 'mode': bad['image']['producer_mode'] = 'in-producer-paired-v1'
            if mutation == 'file': bad['execution_files'].pop(next(iter(hashes)))
            if mutation == 'size': bad['image']['bytes'] = 2_000_000_000
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                contract.validate_manifest(bad, hashes)

    def test_real_marker_only_child_and_execution_hashes_are_required(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'Reliability test'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.invalid'], check=True)
            hashes = {}
            for name in contract.EXECUTION_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text('reviewed ' + name + '\n')
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            manifest_path = root / contract.MANIFEST
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps({'ready': True, 'release_acceptance': False,
                'version': '1.2', 'app_profile': 'lightweight', 'image': image(),
                'execution_files': hashes}))
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'Reviewed preparation'], check=True)
            parent = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
            marker = root / contract.MARKER
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(parent + '\n')
            subprocess.run(['git', '-C', str(root), 'add', str(marker.relative_to(root))], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'Activate reliability'], check=True)
            head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
            event = root / 'event.json'
            (root / '.git/info/exclude').write_text('event.json\n')
            event.write_text(json.dumps({'before': parent, 'after': head}))
            env = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                   'GITHUB_REPOSITORY': 'yuvalkolodkingal/Arctic-Linux',
                   'GITHUB_REF': 'refs/heads/' + contract.BRANCH, 'GITHUB_EVENT_NAME': 'push',
                   'GITHUB_RUN_ATTEMPT': '1', 'GITHUB_SHA': head, 'GITHUB_EVENT_PATH': str(event)}
            with patch.object(contract, 'ROOT', root), patch.dict(os.environ, env):
                actual, actual_parent, actual_head = contract.validate_activation(manifest_path)
            self.assertEqual((actual['image'], actual_parent, actual_head), (image(), parent, head))

    def test_required_install_and_reboot_results_fail_closed(self):
        valid = results()
        self.assertEqual(contract.validate_results(valid), valid)
        for mutation in ('missing', 'failed', 'duplicate', 'extra'):
            bad = copy.deepcopy(valid)
            if mutation == 'missing': bad.pop()
            if mutation == 'failed': bad[0]['status'] = 'failed'
            if mutation == 'duplicate': bad[-1] = copy.deepcopy(bad[0])
            if mutation == 'extra': bad.append({'stage': 'live', 'check': 'invented', 'status': 'passed', 'evidence': 'x'})
            with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                contract.validate_results(bad)

    def test_collection_exports_only_fixed_public_results_and_uses_exclusive_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'private-results.json'
            private = results()
            private[0]['detail'] = 'private transcript must not be uploaded'
            source.write_text(json.dumps(private))
            public = root / 'results.json'
            execution = root / 'execution.json'
            manifest = {'app_profile': 'lightweight', 'version': '1.2', 'image': image()}
            with patch.object(contract, 'validate_activation', return_value=(manifest, 'f' * 40, 'e' * 40)), \
                    patch.dict(os.environ, {'GITHUB_RUN_ID': '900', 'GITHUB_RUN_ATTEMPT': '1'}):
                receipt, _ = contract.collect(root / 'manifest.json', source, public, execution, 'bios')
                with self.assertRaises(FileExistsError):
                    contract.collect(root / 'manifest.json', source, public, execution, 'bios')
            self.assertNotIn(b'private transcript', public.read_bytes())
            proof = contract.validate_evidence(receipt, public.read_bytes(), image=image(), firmware='bios',
                                               source_sha='e' * 40, run_id=900)
            self.assertEqual(proof['automated_passed'], len(contract.AUTOMATED))

    def receipt(self, raw):
        return {
            'schema': contract.SCHEMA, 'status': 'blank_disk_install_reboot_passed',
            'release_acceptance': False, 'firmware': 'uefi', 'app_profile': 'lightweight',
            'version': '1.2', 'image': image(), 'execution_source_sha': 'e' * 40,
            'reviewed_parent_sha': 'f' * 40, 'run_id': 900, 'run_attempt': 1,
            'vm': {'acceleration': 'kvm', 'memory_mib': 4096, 'vcpus': 2,
                   'disk': 'new-blank-sparse-qcow2', 'boot_network': 'online'},
            'results': {'path': 'results.json', 'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'automated_passed': len(contract.AUTOMATED), 'unrun': len(contract.UNRUN)},
        }

    def test_receipt_binds_actual_results_image_firmware_source_and_run(self):
        public = [{key: value for key, value in row.items() if key != 'detail'} for row in results()]
        raw = (json.dumps(public, sort_keys=True) + '\n').encode()
        receipt = self.receipt(raw)
        proof = contract.validate_evidence(receipt, raw, image=image(), firmware='uefi',
                                           source_sha='e' * 40, run_id=900)
        self.assertEqual(proof['status'], 'blank_disk_install_reboot_passed')
        cases = []
        changed = bytearray(raw); changed[-2] = ord(' '); cases.append((receipt, bytes(changed), image(), 'uefi', 'e' * 40, 900))
        bad = copy.deepcopy(receipt); bad['image']['sha256'] = '0' * 64; cases.append((bad, raw, image(), 'uefi', 'e' * 40, 900))
        cases.append((receipt, raw, image(), 'bios', 'e' * 40, 900))
        cases.append((receipt, raw, image(), 'uefi', '0' * 40, 900))
        cases.append((receipt, raw, image(), 'uefi', 'e' * 40, 901))
        for args in cases:
            with self.subTest(args=args[3:]), self.assertRaises((RuntimeError, ValueError, json.JSONDecodeError)):
                contract.validate_evidence(args[0], args[1], image=args[2], firmware=args[3],
                                           source_sha=args[4], run_id=args[5])

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        for raw in ('{"ready":true,"ready":false}', '{"bytes":NaN}', '{"bytes":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises((RuntimeError, ValueError)):
                contract.strict_json(raw)


class WorkflowControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (ROOT / contract.WORKFLOW).read_text()

    def test_dedicated_lane_is_marker_only_artifact_only_and_nonpublishing(self):
        text = self.workflow
        self.assertIn('paths: [.github/qualification-20261010.reliability]', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertNotIn('${{ runner.temp }}', text)
        self.assertIn('EVIDENCE: /tmp/arctic-reliability-${{ github.run_id }}-${{ matrix.firmware }}', text)
        self.assertIn('matrix:\n        firmware: [uefi, bios]', text)
        self.assertIn('max-parallel: 1', text)
        self.assertIn('tools/native-functional/fetch-image.py --manifest', text)
        self.assertIn('--reliability-app-profile lightweight', text)
        self.assertIn('--install-timeout 2400', text)
        self.assertIn('candidate-release-reliability-${{ matrix.firmware }}', text)
        self.assertNotIn('continue-on-error', text)
        for forbidden in ('gh release', 'git push', 'tools/build-iso.sh', 'tools/publish-repo.sh'):
            self.assertNotIn(forbidden, text)

    def test_existing_tag_reliability_workflow_remains_dispatchable(self):
        tagged = (ROOT / '.github/workflows/release-reliability.yml').read_text()
        self.assertIn('workflow_dispatch:', tagged)
        self.assertIn('Exact existing release or RC tag', tagged)
        self.assertIn('release-reliability-${{ matrix.firmware }}', tagged)


class QualifiedPublicationControls(unittest.TestCase):
    def pins(self):
        base = {'run_id': 50, 'source_sha': 'a' * 40, 'artifact_id': 60,
                'archive_bytes': 100, 'archive_sha256': 'b' * 64}
        return {'uefi': base, 'bios': base | {'artifact_id': 61, 'archive_sha256': 'c' * 64}}

    def test_publication_manifest_requires_reliability_before_activation(self):
        value = json.loads((ROOT / 'tools/qualified-release/manifest.json').read_text())
        self.assertIn('reliability', value)
        self.assertIsNone(value['reliability'])
        self.assertIn(contract.WORKFLOW, prepare.FILES)
        self.assertIn('tools/reliability/exact-artifact.py', prepare.FILES)

    def test_both_firmware_pins_share_run_source_and_are_distinct(self):
        for mutation in ('missing', 'run', 'source', 'artifact', 'archive'):
            pins = copy.deepcopy(self.pins())
            if mutation == 'missing': pins.pop('bios')
            if mutation == 'run': pins['bios']['run_id'] = 51
            if mutation == 'source': pins['bios']['source_sha'] = 'd' * 40
            if mutation == 'artifact': pins['bios']['artifact_id'] = pins['uefi']['artifact_id']
            if mutation == 'archive': pins['bios']['archive_sha256'] = pins['uefi']['archive_sha256']
            with self.subTest(mutation=mutation), patch.object(prepare, 'validate_lane') as lane, \
                    self.assertRaises(RuntimeError):
                prepare.validate_reliability_lane({'reliability': pins})
            lane.assert_not_called()


if __name__ == '__main__':
    unittest.main()
