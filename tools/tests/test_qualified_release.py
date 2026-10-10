"""Publication must remain disabled before image and qualification pins exist."""
import importlib.util
import ast
import copy
import json
from pathlib import Path
import re
import subprocess
import tempfile
import textwrap
from types import SimpleNamespace
import unittest
import zipfile
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

    def test_legacy_native_artifact_without_taskbar_report_never_qualifies(self):
        with self.assertRaisesRegex(RuntimeError, 'Missing/duplicate actual-image taskbar'):
            prepare.taskbar_proof(SimpleNamespace(infolist=lambda: []), {})

    def test_taskbar_publisher_binds_real_transport_contract_to_image_boot_and_source(self):
        spec = importlib.util.spec_from_file_location('taskbar_publisher_fixture',
            ROOT / 'tools/native-functional/test_taskbar_transport.py')
        fixture = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture)
        fixture.Controls.setUpClass()
        control = fixture.Controls()
        report = copy.deepcopy(control.report)
        report['reservation_observer'] = 'Mango maximized-client rectangles; IPC does not expose raw exclusive-zone values'
        report['installed_inputs'].update({'/usr/bin/mango':'a'*64, '/usr/bin/mmsg':'a'*64,
                                          '/usr/share/arctic/shell/shell.qml':'a'*64})
        report['owned_window'] = dict(pid=1234, start_ticks=5678, client_id='42', uid=1000,
            executable='/usr/bin/foot', executable_sha256='b'*64, is_xwayland=False)
        files = dict(control.files)
        files['taskbar-report.json'] = json.dumps(report).encode()
        context = copy.deepcopy(control.context)
        manifest = dict(image=dict(source_sha=context['source_sha'], sha256=context['iso_sha256'],
                                   bytes=context['iso_bytes']), native=dict(source_sha=context['execution_sha'],
                                                                          archive_sha256='f'*64))
        def source_hash(ref, name):
            return {'tools/native-functional/taskbar.py':'5'*64,
                    'tools/native-functional/taskbar-runtime.py':'6'*64,
                    'tools/native-functional/native_smoke.py':'7'*64}.get(name, 'a'*64)
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            serial, port = control.port_serial(control.rows(files, report))
            state = fixture.e.check_taskbar(serial, context, folder/'taskbar', transport_serial=port)
            manifest['taskbar_media_review'] = dict(visual_status='passed', image_sha256=context['iso_sha256'],
                native_archive_sha256='f'*64, images={'taskbar/'+name:item['sha256']
                    for name,item in state['files'].items() if Path(name).suffix == '.png'})
            execution = dict(taskbar_context=context, taskbar=state, taskbar_build=dict(
                schema='arctic-taskbar-tools-v1', release_acceptance=False,
                sources={name:'a'*64 for name in ('shell/dev/virtual-pointer.c',
                    'tools/native-functional/taskbar-screencopy.c', 'shell/dev/wlr-screencopy-unstable-v1.xml')},
                binaries={'virtual-pointer':'8'*64, 'raw-screencopy':'9'*64}))
            port_bytes = port.encode()
            prefix_bytes = port_bytes[:64*1024]
            transport_sha = prepare.hashlib.sha256(port_bytes).hexdigest()
            prefix_sha = prepare.hashlib.sha256(prefix_bytes).hexdigest()
            execution['taskbar_transport'] = dict(name='taskbar-boot.log', bytes=len(port_bytes),sha256=transport_sha,
                kind='root-owned named virtio-serial output bound to original installed native boot')
            execution['harness_evidence'] = {'taskbar-boot.log.bounded-prefix.bin':dict(bytes=len(prefix_bytes),
                sha256=prefix_sha,original_bytes=len(port_bytes),original_sha256=transport_sha)}
            (folder/'harness').mkdir()
            (folder/'harness/taskbar-boot.log.bounded-prefix.bin').write_bytes(prefix_bytes)
            (folder/'execution.json').write_text(json.dumps(execution))
            (folder/'native-installed').mkdir()
            proof = folder/'native-installed/serial-native-provenance.json'
            proof.write_text(json.dumps(control.native))
            def archive():
                path = folder/'evidence.zip'
                with zipfile.ZipFile(path, 'w') as output:
                    for item in folder.rglob('*'):
                        if item.is_file() and item != path:
                            output.write(item, item.relative_to(folder).as_posix())
                return zipfile.ZipFile(path)
            with patch.object(prepare, 'source_hash', side_effect=source_hash), archive() as evidence:
                self.assertEqual(prepare.taskbar_proof(evidence, manifest)['cases'], 24)
                wrong = copy.deepcopy(manifest)
                wrong['image']['sha256'] = 'f'*64
                with self.assertRaisesRegex(RuntimeError, 'exact-image execution context'):
                    prepare.taskbar_proof(evidence, wrong)
                wrong = copy.deepcopy(manifest)
                wrong['taskbar_media_review']['visual_status'] = 'pending'
                with self.assertRaisesRegex(RuntimeError, 'visual review is absent'):
                    prepare.taskbar_proof(evidence, wrong)
            proof.write_text(json.dumps(dict(control.native, boot_id='ffffffff-ffff-ffff-ffff-ffffffffffff')))
            with patch.object(prepare, 'source_hash', side_effect=source_hash), archive() as evidence:
                with self.assertRaisesRegex(RuntimeError, 'installed boot/session identity'):
                    prepare.taskbar_proof(evidence, manifest)

    def test_failed_or_wrong_image_dictation_report_never_qualifies_release(self):
        image = dict(sha256='a' * 64, source_sha='b' * 40)
        manifest = dict(image=image, dictation={'turbo-q5-v3':dict(source_sha='c' * 40, fixture_manifest_sha256='d' * 64)})
        state = dict(schema='arctic-dictation-execution-v2', hardware_profile='turbo-q5-v3', status='failed_or_unrun', image=image,
                     execution_checker_head='c' * 40, release_acceptance=False,
                     fixture_manifest_sha256='d' * 64)
        for change in ({}, {'status': 'exact_image_dictation_online_offline_local_sessions_passed',
                            'image': image | {'sha256': 'e' * 64}},
                       {'status': 'exact_image_dictation_online_offline_local_sessions_passed',
                        'release_acceptance': True}):
            with patch.object(prepare, 'read_json', return_value=state | change), patch.object(prepare, 'source_hash') as source:
                with self.assertRaisesRegex(RuntimeError, 'Dictation execution'):
                    prepare.dictation_lane_proof(None, manifest, 'turbo-q5-v3')
                source.assert_not_called()

    def test_dictation_release_cannot_replace_two_hardware_lanes_with_one_artifact_or_checker(self):
        profiles = {'small-v2', 'turbo-q5-v3'}
        pins = {profile:dict(source_sha='a'*40,run_id=1,fixture_manifest_sha256='b'*64,
                    artifact_id=index+1,archive_sha256=str(index+1)*64) for index,profile in enumerate(sorted(profiles))}
        with patch.object(prepare, 'dictation_lane_proof') as lane:
            for names in ({'small-v2'}, profiles):
                manifest = dict(dictation={name:pins[name] for name in names})
                if len(names)==2:
                    manifest['dictation']['turbo-q5-v3'] = pins['small-v2']
                with self.assertRaisesRegex(RuntimeError, 'Dictation execution'):
                    prepare.dictation_proof({name:None for name in names},manifest)
            changed = copy.deepcopy(pins)
            changed['turbo-q5-v3']['source_sha'] = 'c'*40
            with self.assertRaisesRegex(RuntimeError, 'Dictation execution'):
                prepare.dictation_proof({name:None for name in profiles},dict(dictation=changed))
            lane.assert_not_called()


class ActualPublicationScriptTest(unittest.TestCase):
    def setUp(self):
        workflow = (ROOT / '.github/workflows/publish-qualified-20261008.yml').read_text()
        body = workflow.split("python3 -B - <<'PY'\n", 1)[1].rsplit('\n          PY', 1)[0]
        nodes = [node for node in ast.parse(textwrap.dedent(body)).body
                 if isinstance(node, ast.FunctionDef) and node.name in ('tag_target', 'promotion_guard', 'ensure_tag', 'uploaded_draft')]
        self.env = dict(re=re, json=json, subprocess=subprocess, repo='repos/control/repo', api=Mock())
        exec(compile(ast.Module(body=nodes, type_ignores=[]), '<actual publisher functions>', 'exec'), self.env)

    def test_uploaded_draft_uses_its_unique_id_and_rejects_published_or_wrong_target(self):
        target = 'a' * 40
        release = dict(id=7, tag_name='v1.2.1', draft=True, target_commitish=target)
        self.env['api'].side_effect = [[release], release]
        self.assertEqual(self.env['uploaded_draft'](target)['id'], 7)
        self.assertEqual(self.env['api'].call_args.args[0], '/releases/7')
        for rows, actual in (([], release), ([release, release], release),
                             ([release], release | {'draft': False}),
                             ([release], release | {'target_commitish': 'b' * 40}),
                             ([release], release | {'id': 8})):
            self.env['api'].side_effect = [rows, actual]
            with self.assertRaises(AssertionError):
                self.env['uploaded_draft'](target)

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
