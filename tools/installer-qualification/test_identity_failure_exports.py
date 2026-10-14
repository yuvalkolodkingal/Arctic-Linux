"""Bounded guarded challenge failure exports; no VM or authentication claim."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import runner as R


class IdentityFailureExportControls(unittest.TestCase):
    def fixture(self, root, count=3):
        vm = root / 'vm'; vm.mkdir()
        target = root / 'host'; target.mkdir()
        probe = vm / 'probe.png'; captures = []
        for index in range(count):
            Image.new('RGB', (1280, 720), (index, 20, 30)).save(probe)
            with patch.object(R._driver.subprocess, 'run', return_value=types.SimpleNamespace(stdout=b'246')):
                R._driver.identity_challenge_capture(probe, vm, 'f' * 32, captures,
                                                     R._driver.time.monotonic() + 20)
        return vm, target

    def test_original_pixels_and_closed_metadata_survive_strict_whole_screening(self):
        spec = importlib.util.spec_from_file_location('identity_export_screen', HERE.parent / 'native-functional/screen-evidence.py')
        scanner = importlib.util.module_from_spec(spec); spec.loader.exec_module(scanner)
        for count in (1, 2, 3):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory); vm, target = self.fixture(root, count)
                R.preserve_identity_failure(vm, target)
                expected = {*R._driver.IDENTITY_CHALLENGE_IMAGES[:count], R._driver.IDENTITY_CHALLENGE_METADATA}
                self.assertEqual({p.name for p in target.iterdir()}, expected)
                for name in expected:
                    self.assertEqual((target / name).read_bytes(), (vm / name).read_bytes())
                screened = root / 'screened'
                scanner.screen(target, screened, external=True)
                for name in expected:
                    self.assertEqual((screened / name).read_bytes(), (vm / name).read_bytes())
                self.assertFalse(json.loads((target / R._driver.IDENTITY_CHALLENGE_METADATA).read_text())['authentication'])

    def test_private_fields_types_and_inventory_drift_never_export_any_member(self):
        metadata_name = R._driver.IDENTITY_CHALLENGE_METADATA
        changes = {
            'private-field': lambda v: v.update(transcript='private text'),
            'auth-integer': lambda v: v.update(authentication=0),
            'capture-private-field': lambda v: v['captures'][0].update(response='private value'),
            'byte-boolean': lambda v: v['captures'][0].update(bytes=True),
            'size-float': lambda v: v['captures'][0].update(size=[1280.0, 720]),
            'guard-integer': lambda v: v['captures'][0].update(private_input_guard_passed=1),
            'path-traversal': lambda v: v['captures'][0].update(path='../probe.png'),
            'duplicate-path': lambda v: v['captures'][1].update(path=v['captures'][0]['path']),
            'digest': lambda v: v['captures'][0].update(sha256='0' * 64),
            'too-many': lambda v: v['captures'].append(v['captures'][0]),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                vm, target = self.fixture(Path(directory))
                path = vm / metadata_name; value = json.loads(path.read_text()); mutate(value)
                path.write_text(json.dumps(value))
                with self.assertRaises(RuntimeError):
                    R.preserve_identity_failure(vm, target)
                self.assertEqual(list(target.iterdir()), [])
        for scenario in ('missing-metadata', 'missing-pixels', 'extra-pixels', 'wrong-dimensions',
                         'symlink', 'completed-boot', 'duplicate-key', 'writable-image', 'writable-metadata'):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                vm, target = self.fixture(Path(directory))
                if scenario == 'missing-metadata':
                    (vm / metadata_name).unlink()
                elif scenario == 'missing-pixels':
                    (vm / R._driver.IDENTITY_CHALLENGE_IMAGES[0]).unlink()
                elif scenario == 'extra-pixels':
                    (vm / 'installed-identity-challenge-3.png').write_bytes(b'private')
                elif scenario == 'completed-boot':
                    (vm / 'installed-boot.json').write_text('{}')
                elif scenario == 'duplicate-key':
                    path = vm / metadata_name
                    path.write_bytes(path.read_bytes().replace(b'"authentication": false', b'"authentication": false, "authentication": false'))
                elif scenario.startswith('writable-'):
                    path = vm / (metadata_name if scenario == 'writable-metadata' else R._driver.IDENTITY_CHALLENGE_IMAGES[0])
                    path.chmod(0o666)
                else:
                    path = vm / R._driver.IDENTITY_CHALLENGE_IMAGES[0]
                    path.unlink()
                    if scenario == 'symlink':
                        path.symlink_to(vm / 'probe.png')
                    else:
                        Image.new('RGB', (1280, 721)).save(path)
                        raw = path.read_bytes(); metadata = vm / metadata_name
                        value = json.loads(metadata.read_text()); value['captures'][0].update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
                        metadata.write_text(json.dumps(value))
                with self.assertRaises((RuntimeError, OSError)):
                    R.preserve_identity_failure(vm, target)
                self.assertEqual(list(target.iterdir()), [])

    def test_guarded_public_images_remain_readable_under_private_container_umask(self):
        with tempfile.TemporaryDirectory() as directory:
            prior = os.umask(0o077)
            try:
                vm, target = self.fixture(Path(directory), count=1)
            finally:
                os.umask(prior)
            for name in (R._driver.IDENTITY_CHALLENGE_IMAGES[0], R._driver.IDENTITY_CHALLENGE_METADATA):
                self.assertEqual((vm / name).stat().st_mode & 0o777, 0o644)
            R.preserve_identity_failure(vm, target)

    def test_success_archive_inventory_does_not_admit_failure_diagnostics(self):
        active = R.E.active_contract()
        self.assertEqual(len(active.REQUIRED_IMAGES), 7)
        self.assertTrue(all('host/' + name not in active.ARCHIVE_FILES
                            for name in (*R._driver.IDENTITY_CHALLENGE_IMAGES, R._driver.IDENTITY_CHALLENGE_METADATA)))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); vm = root / 'vm'; vm.mkdir(); target = root / 'host'; target.mkdir()
            R.preserve_identity_failure(vm, target)
            self.assertEqual(list(target.iterdir()), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
