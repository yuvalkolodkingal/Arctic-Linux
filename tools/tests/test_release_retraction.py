"""Fail-closed cleanup for a qualified release whose public verification failed."""
import importlib.util
import json
from pathlib import Path
import tempfile
from unittest.mock import Mock
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    'qualified_release_retract', ROOT / 'tools/qualified-release/retract.py')
R = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(R)


class ReleaseRetractionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'owned.json'
        self.target = 'a' * 40
        self.assets = {name: {'bytes': index + 1, 'digest': 'sha256:' + str(index + 1) * 64}
                       for index, name in enumerate(('image.iso', 'image.iso.sha256',
                           'image.iso.torrent', 'image.iso.torrent.sha256', 'qualification.json'))}
        self.receipt = {
            'schema': R.SCHEMA, 'repository': R.REPOSITORY,
            'workflow_run_id': 123, 'workflow_run_attempt': 1,
            'release_id': 456, 'tag': R.TAG, 'target': self.target,
            'assets': self.assets,
        }
        self.path.write_text(json.dumps(self.receipt))
        self.environ = {
            'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
            'GITHUB_REPOSITORY': R.REPOSITORY, 'GITHUB_WORKFLOW': R.WORKFLOW,
            'GITHUB_REF': R.BRANCH, 'GITHUB_RUN_ID': '123', 'GITHUB_RUN_ATTEMPT': '1',
        }

    def release(self, draft=False, **changes):
        result = {
            'id': 456, 'tag_name': R.TAG, 'target_commitish': self.target,
            'draft': draft, 'prerelease': False,
            'assets': [{'name': name, 'size': item['bytes'], 'digest': item['digest'],
                        'state': 'uploaded'}
                       for name, item in self.assets.items()],
        }
        return result | changes

    def api(self, releases):
        values = iter(releases)
        def call(path):
            if path.startswith('/releases/'):
                return next(values)
            if path == '/git/ref/tags/' + R.TAG:
                return {'object': {'type': 'commit', 'sha': self.target}}
            raise AssertionError(path)
        return call

    def test_missing_receipt_never_calls_or_changes_github(self):
        call, run = Mock(), Mock()
        self.assertFalse(R.retract(self.path.with_name('missing.json'), self.environ, call, run))
        call.assert_not_called()
        run.assert_not_called()

    def test_matching_public_release_returns_to_draft_and_rechecks(self):
        run = Mock()
        self.assertTrue(R.retract(self.path, self.environ,
                                  self.api([self.release(), self.release(draft=True)]), run))
        run.assert_called_once_with(
            ['gh', 'release', 'edit', R.TAG, '--repo', R.REPOSITORY, '--draft=true'],
            check=True, timeout=60)

    def test_existing_owned_draft_needs_no_mutation(self):
        run = Mock()
        self.assertTrue(R.retract(self.path, self.environ, self.api([self.release(draft=True)]), run))
        run.assert_not_called()

    def test_wrong_run_release_target_or_assets_fails_without_mutation(self):
        cases = [
            ({**self.environ, 'GITHUB_RUN_ID': '999'}, self.release()),
            (self.environ, self.release(target_commitish='b' * 40)),
            (self.environ, self.release(assets=[])),
        ]
        for environ, release in cases:
            with self.subTest(release=release), self.assertRaises(RuntimeError):
                run = Mock()
                R.retract(self.path, environ, self.api([release]), run)
            run.assert_not_called()

    def test_duplicate_receipt_fields_are_rejected(self):
        self.path.write_text('{"schema":"x","schema":"y"}')
        with self.assertRaises(RuntimeError):
            R.retract(self.path, self.environ, Mock(), Mock())

    def test_workflow_records_ownership_before_promotion_and_has_failure_cleanup(self):
        workflow = (ROOT / '.github/workflows/publish-qualified-20261008.yml').read_text()
        receipt = workflow.index("with Path('owned-qualified-release.json').open('x')")
        promotion = workflow.index('          promotion_guard(target)', receipt)
        verification = workflow.index('Verify the full public download', promotion)
        cleanup = workflow.index("tools/qualified-release/retract.py --receipt owned-qualified-release.json",
                                 verification)
        self.assertLess(receipt, promotion)
        self.assertLess(promotion, verification)
        self.assertLess(verification, cleanup)
        self.assertIn('if: ${{ failure() }}', workflow[verification:cleanup])
        self.assertIn('tools/qualified-release/retract.py',
                      (ROOT / 'tools/qualified-release/prepare.py').read_text())


if __name__ == '__main__':
    unittest.main()
