"""Synthetic/static source controls; no VM, ISO build or target execution evidence."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import types
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'tools/exact-image-inspection'
S = types.ModuleType('exact_image_inspector')
S.__file__ = str(HERE / 'inspect.py')
exec(compile((HERE / 'inspect.py').read_bytes(), S.__file__, 'exec'), S.__dict__)
F = S.fetch_module()


def image():
    return dict(source_sha='1' * 40, run_id=7, artifact_id=8,
                name='Arctic-Linux-1.2-candidate-7-1-x86_64.iso', bytes=3,
                sha256=hashlib.sha256(b'iso').hexdigest(), archive_bytes=100,
                archive_sha256='2' * 64, producer_mode=F.EXTERNAL_MODE,
                producer_receipt_sha256='3' * 64)


def manifest():
    return dict(schema='arctic-exact-image-mango-inspection-v1', ready=True, release_acceptance=False,
                performance_acceptance=False, observer_profile_admitted=False, image=image(),
                source_files={name: dict(blob_sha='4' * 40, sha256='5' * 64, bytes=10, mode='100644')
                              for name in S.SOURCE_FILES},
                execution_files={name: '6' * 64 for name in S.EXECUTION_FILES})


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], text=True).strip()


class ManifestControls(unittest.TestCase):
    def test_shipped_lane_is_disabled_and_has_exact_execution_hashes_no_marker(self):
        shipped = S.read_json((HERE / 'execution-manifest.json').read_text())
        self.assertIs(shipped['ready'], False)
        self.assertEqual(shipped['image'], {})
        self.assertEqual(shipped['source_files'], {})
        self.assertFalse((ROOT / S.MARKER).exists())
        self.assertEqual(shipped['execution_files'],
                         {name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest() for name in S.EXECUTION_FILES})
        with patch.object(S, 'api') as api, self.assertRaisesRegex(ValueError, 'disabled'):
            S.activation_guard(shipped, ROOT)
        api.assert_not_called()

    def test_generated_evidence_upload_includes_only_owned_hidden_source_exports(self):
        workflow = (ROOT / S.WORKFLOW).read_text()
        upload = workflow.split('- name: Upload static inspection evidence (unqualified)', 1)[1]
        self.assertIn('path: ${{ runner.temp }}/arctic-exact-image-mango-evidence\n', upload)
        self.assertIn('include-hidden-files: true\n', upload)
        self.assertNotIn('github.workspace', upload)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            with patch.object(S, 'OUTPUT', output), patch.object(S, 'ALLOWED', set()):
                name = 'candidate/source/.github/workflows/iso.yml'
                S.put(name, b'public pinned producer workflow')
                S.write_report()
                report = S.read_json((output / 'report.json').read_text())
                self.assertEqual(report['files'][name]['sha256'], S.sha(output / name))

    def test_exact_typed_pins_cannot_enable_acceptance_or_guess_an_image(self):
        self.assertEqual(S.validate_manifest(manifest()), image())
        mutations = [('ready', False), ('ready', 1), ('release_acceptance', True),
                     ('release_acceptance', 0), ('performance_acceptance', True), ('observer_profile_admitted', True)]
        for field, value in mutations:
            wrong = manifest(); wrong[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError): S.validate_manifest(wrong)
        for field, value in [('run_id', True), ('artifact_id', 0), ('bytes', 2_000_000_000),
                             ('archive_bytes', 2_010_000_000), ('source_sha', 'a' * 7),
                             ('sha256', 'x' * 64), ('producer_receipt_sha256', None),
                             ('producer_mode', F.LEGACY_MODE), ('name', 'unknown.iso')]:
            wrong = manifest(); wrong['image'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): S.validate_manifest(wrong)
        for collection in ('execution_files', 'source_files'):
            wrong = manifest(); wrong[collection].pop(next(iter(wrong[collection])))
            with self.subTest(collection=collection), self.assertRaises(ValueError): S.validate_manifest(wrong)
        for field, value in [('bytes', True), ('mode', '120000'), ('blob_sha', 'x' * 40), ('sha256', None)]:
            wrong = manifest(); next(iter(wrong['source_files'].values()))[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): S.validate_manifest(wrong)

    def test_duplicate_and_nonfinite_json_cannot_supply_pins(self):
        for raw in ('{"ready":false,"ready":true}', '{"bytes":NaN}', '{"bytes":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError): S.read_json(raw)

    def activation(self, root):
        git(root, 'init', '-q'); git(root, 'config', 'user.name', 'Static control')
        git(root, 'config', 'user.email', 'control@example.invalid')
        value = manifest()
        for name in S.EXECUTION_FILES:
            path = root / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('reviewed ' + name + '\n')
        value['execution_files'] = {name: S.sha(root / name) for name in S.EXECUTION_FILES}
        path = root / 'tools/exact-image-inspection/execution-manifest.json'
        path.write_text(json.dumps(value))
        git(root, 'add', '.'); git(root, 'commit', '-qm', 'Reviewed preparation')
        parent = git(root, 'rev-parse', 'HEAD')
        marker = root / S.MARKER; marker.parent.mkdir(exist_ok=True); marker.write_text(parent + '\n')
        git(root, 'add', '.'); git(root, 'commit', '-qm', 'Sole activation child')
        head = git(root, 'rev-parse', 'HEAD')
        event = root.parent / 'event.json'; event.write_text(json.dumps(dict(before=parent, after=head)))
        environment = dict(GITHUB_REPOSITORY=S.REPO, GITHUB_EVENT_NAME='push',
            GITHUB_REF='refs/heads/' + S.BRANCH, RUNNER_ENVIRONMENT='github-hosted',
            GITHUB_RUN_ATTEMPT='1', GITHUB_SHA=head, GITHUB_EVENT_PATH=str(event), GITHUB_RUN_ID='9')
        return value, environment, head

    def test_real_git_activation_requires_exact_child_ref_and_hidden_source_bytes(self):
        for fault in (None, 'wrong_ref', 'rerun', 'dirty', 'hidden_source', 'hidden_manifest', 'marker'):
            with tempfile.TemporaryDirectory() as temp:
                root = Path(temp) / 'checkout'; root.mkdir()
                value, environment, head = self.activation(root)
                ref = dict(ref='refs/heads/' + S.BRANCH, object=dict(sha=head))
                if fault == 'wrong_ref': ref['object']['sha'] = '9' * 40
                elif fault == 'rerun': environment['GITHUB_RUN_ATTEMPT'] = '2'
                elif fault == 'dirty': (root / 'unreviewed').write_text('extra')
                elif fault in ('hidden_source', 'hidden_manifest'):
                    name = ('tools/exact-image-inspection/inspect.py' if fault == 'hidden_source'
                            else 'tools/exact-image-inspection/execution-manifest.json')
                    git(root, 'update-index', '--skip-worktree', name)
                    path = root / name; path.write_text(path.read_text() + '\n')
                    self.assertEqual(git(root, 'status', '--porcelain'), '')
                elif fault == 'marker': (root / S.MARKER).write_text(head + '\n')
                with patch.dict(os.environ, environment), patch.object(S, 'api', return_value=ref):
                    if fault is None: self.assertEqual(S.activation_guard(value, root), image())
                    else:
                        with self.subTest(fault=fault), self.assertRaises(ValueError): S.activation_guard(value, root)


class OriginalArtifactControls(unittest.TestCase):
    def fixture(self, folder, fault=None):
        pin = image()
        receipt = dict(schema='arctic-producer-performance-receipt-v1', repository=S.REPO,
            workflow='.github/workflows/iso.yml', event='workflow_dispatch', source_sha=pin['source_sha'],
            run_id=pin['run_id'], run_attempt=1, mode=F.EXTERNAL_MODE, release_acceptance=False,
            inputs=dict(expected_source_sha=pin['source_sha'], release=False, tag='', prerelease=True,
                        draft=False, nix_acceptance=False, performance_acceptance=False, boot_test=True,
                        performance_mode=F.EXTERNAL_MODE),
            image={key: pin[key] for key in ('name', 'bytes', 'sha256')},
            startup_results={name: dict(firmware=firmware, mode=mode, status='passed', serial_bytes=100,
                                       serial_sha256='4' * 64) for name, (firmware, mode) in F.STARTUP_LANES.items()})
        if fault == 'receipt': receipt['run_attempt'] = 2
        raw_receipt = json.dumps(receipt).encode()
        pin['producer_receipt_sha256'] = hashlib.sha256(raw_receipt).hexdigest()
        memory = io.BytesIO()
        with zipfile.ZipFile(memory, 'w') as archive:
            archive.writestr('iso/' + pin['name'], b'bad' if fault == 'iso_hash' else b'iso')
            archive.writestr('iso/' + pin['name'] + '.sha256', pin['sha256'] + '  ' + pin['name'] + '\n')
            archive.writestr('BUILD-INFO', 'git_commit=' + pin['source_sha'] + '\narctic_repos=enabled\n')
            archive.writestr(F.RECEIPT_NAME, raw_receipt)
            if fault == 'unsafe_zip': archive.writestr('../outside', 'bad')
        data = memory.getvalue()
        if fault == 'crc':
            index = data.index(b'iso', data.index(pin['name'].encode()) + len(pin['name']))
            data = data[:index] + b'bad' + data[index + 3:]
        pin['archive_bytes'] = len(data); pin['archive_sha256'] = hashlib.sha256(data).hexdigest()
        run = dict(id=7, head_sha=pin['source_sha'], run_attempt=1, event='workflow_dispatch',
                   path='.github/workflows/iso.yml', status='completed', conclusion='success')
        artifact = dict(id=8, name='arctic-linux-iso', expired=False, size_in_bytes=len(data),
                        digest='sha256:' + pin['archive_sha256'], workflow_run=dict(id=7, head_sha=pin['source_sha']))
        steps = [dict(name=name, status='completed', conclusion='success') for name in
                 (*F.BOOT_STEPS, F.SIZE_STEP, F.RECEIPT_STEP, F.EXTERNAL_UPLOAD_STEP)] + [
                 dict(name=F.PAIRED_STEP, status='completed', conclusion='skipped')]
        jobs = [dict(name='iso', head_sha=pin['source_sha'], run_attempt=1, status='completed', conclusion='success', steps=steps),
                dict(name='Publish the completed ISO', head_sha=pin['source_sha'], run_attempt=1, status='completed', conclusion='skipped')]
        if fault == 'failed_run': run['conclusion'] = 'failure'
        elif fault == 'rerun': run['run_attempt'] = 2
        elif fault == 'source': run['head_sha'] = '8' * 40
        elif fault == 'artifact': artifact['workflow_run']['head_sha'] = '8' * 40
        elif fault == 'artifact_digest': artifact['digest'] = 'sha256:' + '8' * 64
        elif fault == 'expired': artifact['expired'] = True
        elif fault == 'zip_hash': pin['archive_sha256'] = '8' * 64; artifact['digest'] = 'sha256:' + pin['archive_sha256']
        elif fault == 'boot': steps[0]['conclusion'] = 'skipped'
        elif fault == 'paired': steps[-1]['conclusion'] = 'success'
        elif fault == 'publish': jobs[1]['conclusion'] = 'success'
        def api(path):
            if path.endswith('/jobs?filter=all&per_page=100'): return dict(total_count=len(jobs), jobs=jobs)
            return artifact if '/artifacts/' in path else run
        def download(argv, **kwargs):
            kwargs['stdout'].write(data)
            return types.SimpleNamespace(returncode=0)
        return pin, api, download

    def test_actual_original_archive_receipt_crc_and_iso_are_verified_before_extraction(self):
        for fault in (None, 'failed_run', 'rerun', 'source', 'artifact', 'artifact_digest', 'expired', 'zip_hash',
                      'boot', 'paired', 'publish', 'receipt', 'iso_hash', 'unsafe_zip', 'crc'):
            with tempfile.TemporaryDirectory() as temp:
                folder = Path(temp); output = folder / 'evidence'; output.mkdir()
                pin, api, download = self.fixture(folder, fault)
                with patch.object(S, 'api', side_effect=api), patch.object(S.subprocess, 'run', side_effect=download), \
                        patch.object(S, 'OUTPUT', output), patch.object(S, 'ALLOWED', set()):
                    if fault is None:
                        path, proof = S.download_candidate(pin, folder)
                        self.assertEqual(path.read_bytes(), b'iso')
                        self.assertTrue(proof['artifact']['all_members_crc_verified'])
                        self.assertEqual(len(proof['artifact']['original_zip_inventory']), 4)
                        self.assertFalse(proof['producer']['conclusion'] != 'success')
                    else:
                        with self.subTest(fault=fault), self.assertRaises((RuntimeError, ValueError, zipfile.BadZipFile)):
                            S.download_candidate(pin, folder)
                        self.assertNotIn('candidate/performance-plan.json', S.ALLOWED)


class StaticExtractionControls(unittest.TestCase):
    def test_evidence_names_cannot_escape_owned_output_through_absolute_traversal_or_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); output = root / 'evidence'; output.mkdir()
            outside = root / 'outside'; outside.mkdir()
            (output / 'escape').symlink_to(outside, target_is_directory=True)
            with patch.object(S, 'OUTPUT', output), patch.object(S, 'ALLOWED', set()):
                for name in ('/absolute.txt', '../outside.txt', 'nested/../../outside.txt', 'escape/payload.txt'):
                    with self.subTest(name=name), self.assertRaises(ValueError): S.put(name, b'unsafe')
                self.assertEqual(list(outside.iterdir()), [])
                path = S.put('candidate/regular.txt', b'allowed')
                self.assertEqual(path.read_bytes(), b'allowed')
                self.assertEqual(S.ALLOWED, {'candidate/regular.txt'})

    def test_reader_has_no_network_capabilities_privileges_or_target_entrypoint(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, RUNNER_TEMP=temp), \
                patch.object(S, 'READER', 'sha256:' + '1' * 64):
            command = S.reader_command('/usr/bin/fsck.erofs', [(Path(temp), '/output', False)], name='owned-static')
            for flag in ('--network=none', '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges'):
                self.assertIn(flag, command)
            self.assertEqual(command[command.index('--entrypoint') + 1], '/usr/bin/fsck.erofs')
            self.assertIn(str(os.geteuid()) + ':' + str(os.getegid()), command)
            with self.assertRaises(ValueError): S.reader_command('/usr/bin/fsck.erofs', [(Path('/etc'), '/input', True)])

    def test_library_selected_only_from_unique_regular_exact_image_rpmdb(self):
        inventory = 'wlroots0.20\t0.20.2\tx86_64\n'
        row = '/usr/lib64/libwlroots-0.20.so.0.20.2\t' + '1' * 64 + '\t' + str(stat.S_IFREG | 0o755) + '\n'
        with patch.object(S, 'rpm_query', side_effect=[inventory, row]):
            self.assertEqual(S.library_record(Path('/proof')), ('wlroots0.20', '/usr/lib64/libwlroots-0.20.so.0.20.2'))
        for rows, files in ((inventory * 2, row), ('wlroots0.20\t0.20.3\tx86_64\n', row),
                            (inventory, row * 2), (inventory, row.replace(str(stat.S_IFREG | 0o755), str(stat.S_IFLNK | 0o755)))):
            with patch.object(S, 'rpm_query', side_effect=[rows, files]), self.assertRaises(ValueError):
                S.library_record(Path('/proof'))

    def test_unversioned_and_versioned_library_selection_preserves_regular_uniqueness_and_diagnostics(self):
        inventory = 'wlroots0.20\t0.20.2\tx86_64\n'
        paths = ('/usr/lib64/libwlroots-0.20.so', '/usr/lib64/libwlroots-0.20.so.0.20.2')
        def row(path, mode=stat.S_IFREG | 0o755):
            return path + '\t' + '1' * 64 + '\t' + str(mode) + '\n'
        for path in paths:
            report = {'tools': {}}
            with patch.object(S, 'REPORT', report), patch.object(S, 'rpm_query', side_effect=[inventory, row(path)]):
                self.assertEqual(S.library_record(Path('/proof')), ('wlroots0.20', path))
            diagnostic = report['tools']['wlroots_library_selection']
            self.assertEqual(diagnostic['regular_match_count'], 1)
            self.assertEqual(diagnostic['candidates'][0]['path'], path)
            self.assertEqual(diagnostic['status'], 'selected_pending_payload_hash_and_ELF_ABI_verification')
        for files, count in ((row(paths[0]) + row(paths[1]), 2),
                             (row(paths[0], stat.S_IFLNK | 0o755), 0)):
            report = {'tools': {}}
            with patch.object(S, 'REPORT', report), patch.object(S, 'rpm_query', side_effect=[inventory, files]), \
                    self.assertRaises(ValueError): S.library_record(Path('/proof'))
            self.assertEqual(report['tools']['wlroots_library_selection']['regular_match_count'], count)
        report = {'tools': {}}
        files = row(paths[0]) + row(paths[1], stat.S_IFLNK | 0o755)
        with patch.object(S, 'REPORT', report), patch.object(S, 'rpm_query', side_effect=[inventory, files]):
            self.assertEqual(S.library_record(Path('/proof')), ('wlroots0.20', paths[0]))

    def test_missing_wrong_version_and_many_candidate_diagnostics_stay_bounded(self):
        report = {'tools': {}}
        with patch.object(S, 'REPORT', report), patch.object(S, 'rpm_query', return_value='wlroots0.20\t0.20.3\tx86_64\n'), \
                self.assertRaises(ValueError): S.library_record(Path('/proof'))
        self.assertEqual(report['tools']['wlroots_library_selection']['matching_package_count'], 0)
        self.assertEqual(report['tools']['wlroots_library_selection']['observed_packages'][0]['version'], '0.20.3')
        report = {'tools': {}}
        with patch.object(S, 'REPORT', report), patch.object(S, 'rpm_query', side_effect=['wlroots0.20\t0.20.2\tx86_64\n', '']), \
                self.assertRaises(ValueError): S.library_record(Path('/proof'))
        self.assertEqual(report['tools']['wlroots_library_selection']['candidate_count'], 0)
        self.assertEqual(report['tools']['wlroots_library_selection']['regular_match_count'], 0)
        self.assertEqual(report['tools']['wlroots_library_selection']['candidates'], [])
        rows = ''.join('/usr/lib64/libwlroots-0.20.so.' + str(i) + '\t' + '1' * 64 + '\t' +
                       str(stat.S_IFLNK | 0o755) + '\n' for i in range(100))
        report = {'tools': {}}
        with patch.object(S, 'REPORT', report), patch.object(S, 'rpm_query', side_effect=['wlroots0.20\t0.20.2\tx86_64\n', rows]), \
                self.assertRaises(ValueError): S.library_record(Path('/proof'))
        diagnostic = report['tools']['wlroots_library_selection']
        self.assertEqual(diagnostic['candidate_count'], 100)
        self.assertEqual(diagnostic['regular_match_count'], 0)
        self.assertEqual(len(diagnostic['candidates']), 8)
        self.assertEqual(diagnostic['candidate_samples_omitted'], 92)
        self.assertLess(len(json.dumps(diagnostic)), 5000)

    def test_filtered_extraction_accepts_exact_unversioned_or_versioned_library_only(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, RUNNER_TEMP=temp), \
                patch.object(S, 'reader_capture', return_value=(0, '')) as reader:
            for name in ('/usr/lib64/libwlroots-0.20.so', '/usr/lib64/libwlroots-0.20.so.0.20.2'):
                proof = {}
                S.extract_selected(Path(temp) / 'rootfs.image', Path(temp), name, 'wlroots', proof, time.monotonic() + 120)
                self.assertIn('--path=' + name, reader.call_args.args[1])
            reader.reset_mock()
            for name in ('/usr/lib64/libwlroots-0.21.so', '/usr/lib64/libwlroots-0.20.so.debug',
                         '/usr/lib64/libwlroots-0.20.so/../../etc/passwd'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    S.extract_selected(Path(temp) / 'rootfs.image', Path(temp), name, 'wlroots', {}, time.monotonic() + 120)
            reader.assert_not_called()

    def test_selected_library_still_requires_exact_rpm_payload_digest(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'wlroots'; path.write_bytes(b'actual image library')
            target = '/usr/lib64/libwlroots-0.20.so'
            identity = 'wlroots0.20\t0.20.2\t1.fc44\tx86_64\t8\n'
            row = target + '\t' + '0' * 64 + '\t' + str(stat.S_IFREG | 0o755) + '\n'
            with patch.object(S, 'rpm_query', side_effect=[identity, row]), self.assertRaises(ValueError):
                S.rpm_identity(Path(temp), path, target, 'wlroots0.20', '0.20.2')

    @unittest.skipUnless(all(shutil.which(name) for name in ('gcc', 'readelf', 'objdump')), 'Native static ELF tools needed')
    def test_real_elf_is_archived_and_disassembled_without_running_it(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); source = root / 'fixture.c'; binary = root / 'fixture'
            source.write_text('int main(void) { return 73; }\n')
            subprocess.run(['gcc', '-fPIE', '-pie', '-o', str(binary), str(source)], check=True)
            output = root / 'evidence'; output.mkdir()
            with patch.object(S, 'OUTPUT', output), patch.object(S, 'ALLOWED', set()):
                report = S.save_elf('fixture', binary, 1024 * 1024)
                self.assertEqual((output / 'candidate/fixture.elf').read_bytes(), binary.read_bytes())
                self.assertEqual(report['sha256'], S.sha(binary))
                self.assertIn('<main>:', (output / 'candidate/fixture-disassembly.txt').read_text())
                self.assertEqual(report['profile_status'], 'requires_independent_machine_code_and_abi_review')
                self.assertFalse(S.REPORT['observer_profile_admitted'])
            binary.write_bytes(b'not an ELF')
            with self.assertRaises(ValueError): S.save_elf('invalid', binary, 1024 * 1024)


if __name__ == '__main__':
    unittest.main()
