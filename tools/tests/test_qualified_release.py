"""Publication must remain disabled before image and qualification pins exist."""
import importlib.util
import ast
import json
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('qualified_prepare', ROOT / 'tools/qualified-release/prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class PublicationGuardTest(unittest.TestCase):
    def test_unknown_runtime_roots_and_build_inputs_require_rebuild(self):
        names = ['go.sum', 'vendor/example/file.go', 'new-runtime/data.bin', 'shell/ScreenFrame.qml',
                 'tools/build-iso.sh', 'tools/build-cache.py', '.github/workflows/iso.yml',
                 'tools/native-functional/execution-manifest.json',
                 '.github/workflows/publish-qualified-20261008.yml', 'docs/release.md', 'README.md',
                 'iso/kiwi/README.md', 'shell/dev/test-lock-clock.py']
        self.assertEqual(prepare.product_changes(names), names[:7])

    def test_product_rename_into_helper_root_still_requires_rebuild(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()
            git('init', '-q')
            git('config', 'user.name', 'Arctic guard control')
            git('config', 'user.email', 'guard@example.invalid')
            source = root / 'profiles/ci/offline.toml'
            source.parent.mkdir(parents=True)
            source.write_text('[profile]\nname = "offline"\n')
            git('add', '.')
            git('commit', '-qm', 'Runtime profile')
            before = git('rev-parse', 'HEAD')
            destination = root / 'tools/reliability/profiles/offline.toml'
            destination.parent.mkdir(parents=True)
            source.rename(destination)
            git('add', '-A')
            git('commit', '-qm', 'Move into helper tree')
            self.assertEqual(git('diff', '--name-only', before, 'HEAD'),
                             'tools/reliability/profiles/offline.toml')
            with patch.object(prepare, 'ROOT', root):
                self.assertEqual(prepare.changed_product_files(before, 'HEAD'),
                                 ['profiles/ci/offline.toml'])

    def test_docs_only_stable_fallback_rejects_runtime_changes_and_failed_exact_run(self):
        source, stable = 'a' * 40, 'b' * 40
        def run(sha, path, number, conclusion='success'):
            return dict(head_sha=sha, head_branch='main', event='push', path=path,
                        run_attempt=1, status='completed', conclusion=conclusion, id=number)
        ci = run(source, '.github/workflows/ci.yml', 1)
        prior = run(stable, '.github/workflows/repo.yml', 2)
        jobs = dict(total_count=15, jobs=[dict(status='completed', conclusion='success')] * 15)
        def api(path):
            if '/jobs?' in path:
                return jobs
            return dict(workflow_runs=[ci] if source in path else [prior])
        with patch.object(prepare, 'api', side_effect=api), patch.object(prepare, 'git', return_value='docs/release.md\nREADME.md'):
            self.assertEqual(prepare.main_checks(source, stable)['stable_source_sha'], stable)
        for name in ('shell/LockScreen.qml', 'tools/qualified-release/prepare.py', '.github/workflows/repo.yml'):
            with patch.object(prepare, 'api', side_effect=api), patch.object(prepare, 'git', return_value=name), self.assertRaises(RuntimeError):
                prepare.main_checks(source, stable)
        failed = run(source, '.github/workflows/repo.yml', 3, 'failure')
        with patch.object(prepare, 'api', return_value=dict(workflow_runs=[ci, failed])), patch.object(prepare, 'git') as git:
            with self.assertRaises(RuntimeError):
                prepare.main_checks(source, stable)
            git.assert_not_called()

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


class ActualPublicationScriptTest(unittest.TestCase):
    def setUp(self):
        workflow = (ROOT / '.github/workflows/publish-qualified-20261008.yml').read_text()
        body = workflow.split("python3 -B - <<'PY'\n", 1)[1].rsplit('\n          PY', 1)[0]
        nodes = [node for node in ast.parse(textwrap.dedent(body)).body
                 if isinstance(node, ast.FunctionDef) and node.name in ('tag_target', 'promotion_guard', 'ensure_tag')]
        self.env = dict(re=re, json=json, subprocess=subprocess, repo='repos/control/repo', api=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual publisher functions>', 'exec'), self.env)

    def test_fresh_tag_is_created_and_reverified_before_draft_upload(self):
        target = 'a' * 40
        self.env['tag_target'] = Mock(side_effect=[None, target])
        with patch.object(subprocess, 'run') as write:
            self.env['ensure_tag'](target)
            self.assertIn('ref=refs/tags/v1.2.1', write.call_args.args[0])
            self.assertIn('sha=' + target, write.call_args.args[0])
        self.env['tag_target'] = Mock(side_effect=[target, target])
        with patch.object(subprocess, 'run') as write:
            self.env['ensure_tag'](target)
            write.assert_not_called()
        for values in (['b' * 40], [None, 'b' * 40]):
            self.env['tag_target'] = Mock(side_effect=values)
            with patch.object(subprocess, 'run'), self.assertRaises(AssertionError):
                self.env['ensure_tag'](target)

    def response(self, sha='a' * 40, kind='commit'):
        return SimpleNamespace(returncode=0, stdout=json.dumps({'object': {'type': kind, 'sha': sha}}), stderr='')

    def test_lightweight_and_annotated_tags_resolve_the_actual_commit(self):
        with patch.object(subprocess, 'run', return_value=self.response()):
            self.assertEqual(self.env['tag_target'](), 'a' * 40)
        self.env['api'].return_value = {'object': {'type': 'commit', 'sha': 'c' * 40}}
        with patch.object(subprocess, 'run', return_value=self.response('b' * 40, 'tag')):
            self.assertEqual(self.env['tag_target'](), 'c' * 40)
        self.env['api'].assert_called_with('/git/tags/' + 'b' * 40)

    def test_missing_tag_is_optional_but_authentication_errors_cycles_and_noncommit_are_rejected(self):
        for status in ('404', '403'):
            response = SimpleNamespace(returncode=1, stdout='', stderr='gh: failure (HTTP ' + status + ')')
            with patch.object(subprocess, 'run', return_value=response):
                if status == '404':
                    self.assertIsNone(self.env['tag_target'](optional=True))
                else:
                    with self.assertRaises(AssertionError):
                        self.env['tag_target'](optional=True)
                with self.assertRaises(AssertionError):
                    self.env['tag_target']()
        self.env['api'].return_value = {'object': {'type': 'tag', 'sha': 'b' * 40}}
        for kind in ('blob', 'tag'):
            with patch.object(subprocess, 'run', return_value=self.response('b' * 40, kind)), self.assertRaises(AssertionError):
                self.env['tag_target']()

    def test_main_advancement_new_pr_or_wrong_tag_stops_public_promotion(self):
        target = 'a' * 40
        for tag, main, prs in ((target, 'b' * 40, []), (target, target, [{'number': 99}]),
                                ('b' * 40, target, []), (target, target, [])):
            self.env['tag_target'] = lambda: tag
            self.env['api'] = lambda path: {'object': {'sha': main}} if 'heads/main' in path else prs
            with self.subTest(tag=tag, main=main, prs=prs):
                if tag == main == target and not prs:
                    self.env['promotion_guard'](target)
                else:
                    with self.assertRaises(AssertionError):
                        self.env['promotion_guard'](target)
