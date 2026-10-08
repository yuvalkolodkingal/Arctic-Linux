"""Publication must remain disabled before image and qualification pins exist."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('qualified_prepare', ROOT / 'tools/qualified-release/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PublicationGuardTest(unittest.TestCase):
    def test_disabled_or_unapproved_manifest_never_downloads_or_writes_assets(self):
        manifest = json.loads((ROOT / 'tools/qualified-release/manifest.json').read_text())
        self.assertFalse(manifest['ready'])
        for change in ({}, {'ready': True, 'publication_approved': False},
                       {'ready': True, 'release_acceptance': True}):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as temp:
                target = Path(temp) / 'assets'
                with patch.object(prepare, 'api') as api, patch.object(prepare.subprocess, 'run') as run:
                    with self.assertRaisesRegex(RuntimeError, 'disabled'):
                        prepare.prepare(manifest | change, target)
                    api.assert_not_called()
                    run.assert_not_called()
                    self.assertFalse(target.exists())

    def test_failed_or_wrong_image_native_report_cannot_become_release_qualified(self):
        state = dict(status='failed_or_unrun', iso_sha256='a' * 64)
        manifest = dict(image=dict(sha256='a' * 64), native=dict(source_sha='b' * 40))
        with patch.object(prepare, 'read_json', return_value=state), self.assertRaises(RuntimeError):
            prepare.native_proof(None, manifest)
