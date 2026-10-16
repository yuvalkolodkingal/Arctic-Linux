"""Controls for the temporary screened evidence review exporter."""

import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import wave
import zipfile

from PIL import Image


ROOT = Path(__file__).resolve().parents[2]


def load():
    path = ROOT / 'tools/evidence-review-export/export.py'
    spec = importlib.util.spec_from_file_location('evidence_review_export', path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


exporter = load()


def png(width=2, height=3, color=(31, 41, 55)):
    output = io.BytesIO()
    Image.new('RGB', (width, height), color).save(output, format='PNG')
    return output.getvalue()


def wav_audio(nonzero=True):
    output = io.BytesIO()
    with wave.open(output, 'wb') as target:
        target.setnchannels(2)
        target.setsampwidth(2)
        target.setframerate(48_000)
        target.writeframes((b'\x01\x00\x01\x00' if nonzero else b'\0\0\0\0') * 128)
    return output.getvalue()


def file_entry(raw=None):
    raw = png() if raw is None else raw
    return {
        'member': 'screened/session/desktop.png',
        'output': 'evidence/native/desktop.png',
        'kind': 'png',
        'privacy_class': 'screened-vm-ui',
        'bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'width': 2,
        'height': 3,
    }


def contact_member(index, raw=None):
    raw = png(16, 9, (index % 255, 41, 55)) if raw is None else raw
    return {
        'member': f'taskbar/frame-{index:03d}.png',
        'max_bytes': max(1000, len(raw)),
        'width': 16,
        'height': 9,
    }


def contact_sheet(index, members):
    return {
        'output': f'evidence/native/taskbar-contact-{index:02d}.png',
        'kind': 'png-contact-sheet',
        'privacy_class': 'screened-vm-ui',
        'members': members,
        'columns': 4,
        'thumbnail_width': 320,
        'thumbnail_height': 180,
        'label_height': 24,
        'max_output_bytes': 5_000_000,
        'exact_frames': [],
    }


def artifact(raw=None, archive_bytes=100, archive_sha='a' * 64):
    return {
        'artifact_id': 456,
        'run_id': 123,
        'run_attempt': 1,
        'head_sha': 'b' * 40,
        'head_branch': 'codex/qualification-dispatch-20261010',
        'workflow_path': '.github/workflows/native-candidate-20261008.yml',
        'event': 'push',
        'name': 'native-candidate-qualification',
        'archive_bytes': archive_bytes,
        'archive_sha256': archive_sha,
        'screening': {'stage': 'producer-screened', 'transcript_free': True,
                      'inventory_member': None},
        'files': [file_entry(raw)],
    }


def manifest(artifacts=None, ready=True):
    return {
        'schema': exporter.SCHEMA,
        'ready': ready,
        'review_only': True,
        'repository': exporter.REPOSITORY,
        'source_branch': exporter.SOURCE_BRANCH,
        'target_branch': exporter.TARGET_BRANCH,
        'bounds': copy.deepcopy(exporter.BOUNDS),
        'artifacts': [artifact()] if artifacts is None and ready else (artifacts or []),
    }


class ManifestControls(unittest.TestCase):
    def test_repository_manifest_is_bound_to_final_media_artifacts(self):
        value = exporter.strict_json((ROOT / exporter.MANIFEST).read_text())
        self.assertTrue(value['ready'])
        self.assertEqual(exporter.validate_manifest(value), value)
        self.assertEqual(len(value['artifacts']), 3)
        by_workflow = {item['workflow_path']: item for item in value['artifacts']}
        expected = {
            '.github/workflows/native-candidate-20261008.yml':
                (38830684742, 12017679100, '225ecfd9f2cc01b889a34ae3af707b918fcd4a2a',
                 78271956, '25f07dc38952d06c2c153de3acc102b9ca7e5facd4475aa7928dfd2399ed6f7f'),
            '.github/workflows/installer-candidate-20261009.yml':
                (38830679610, 12017450791, '145f5bb76a1e282758ba62b36703523420754608',
                 1001362, 'b3f56c254637aaf86ab3de685d55c7fc03803ad09eec31b0d31a17bf7ae68101'),
            '.github/workflows/installer-active-candidate-20261009.yml':
                (38834124836, 12018832093, '54e22f81a7db439c143273d4ede6647dd93b21d5',
                 433233, '1841dc56fe6f1e6a86fa56f6780cf08335c06cf2cc42ff8c5701b76dedf859c3'),
        }
        self.assertEqual(set(by_workflow), set(expected))
        for workflow, identity in expected.items():
            artifact = by_workflow[workflow]
            self.assertEqual((artifact['run_id'], artifact['artifact_id'], artifact['head_sha'],
                              artifact['archive_bytes'], artifact['archive_sha256']), identity)
            self.assertEqual(artifact['run_attempt'], 1)
        native = by_workflow['.github/workflows/native-candidate-20261008.yml']
        sheets = [item for item in native['files'] if item['kind'] == 'png-contact-sheet']
        audio = [item for item in native['files'] if item['kind'] == 'native-system-audio']
        self.assertEqual((len(sheets), sum(len(item['members']) for item in sheets),
                          sum(len(item['exact_frames']) for item in sheets)), (9, 488, 40))
        self.assertEqual({item['audio_class'] for item in audio},
                         {'native-virtual-output-boot', 'native-virtual-output-install'})
        self.assertFalse((ROOT / exporter.MARKER).exists())

    def test_exact_pins_allowlist_privacy_classes_and_fixed_bounds_are_required(self):
        value = manifest()
        self.assertEqual(exporter.validate_manifest(value), value)
        cases = []
        bad = copy.deepcopy(value); bad['review_only'] = False; cases.append(bad)
        bad = copy.deepcopy(value); bad['bounds']['max_export_files'] += 1; cases.append(bad)
        bad = copy.deepcopy(value); bad['target_branch'] = 'main'; cases.append(bad)
        bad = copy.deepcopy(value); bad['artifacts'][0]['workflow_path'] = '.github/workflows/repo.yml'; cases.append(bad)
        bad = copy.deepcopy(value); bad['artifacts'][0]['screening']['transcript_free'] = False; cases.append(bad)
        bad = copy.deepcopy(value); bad['artifacts'][0]['files'][0]['privacy_class'] = 'raw'; cases.append(bad)
        bad = copy.deepcopy(value); bad['artifacts'][0]['files'][0]['sha256'] = '0' * 63; cases.append(bad)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                exporter.validate_manifest(case)

    def test_duplicate_outputs_and_bounds_fail_closed(self):
        first = artifact()
        second = copy.deepcopy(first)
        second['artifact_id'] += 1
        second['files'][0]['member'] = 'screened/other.png'
        with self.assertRaises(RuntimeError):
            exporter.validate_manifest(manifest([first, second]))
        too_many = manifest([first])
        too_many['artifacts'][0]['archive_bytes'] = exporter.BOUNDS['max_archive_bytes_each'] + 1
        with self.assertRaises(RuntimeError):
            exporter.validate_manifest(too_many)

    def test_eight_contact_sheets_cover_480_taskbar_frames_without_480_outputs(self):
        taskbar = artifact()
        taskbar['screening']['inventory_member'] = 'upload-screening.json'
        taskbar['files'] = [contact_sheet(page + 1, [contact_member(index) for index in
                             range(page * 60, (page + 1) * 60)]) for page in range(8)]
        value = manifest([taskbar])
        self.assertEqual(exporter.validate_manifest(value), value)
        self.assertEqual(sum(len(item['members']) for item in taskbar['files']), 480)
        ninth = copy.deepcopy(taskbar['files'][0])
        ninth['output'] = 'evidence/native/taskbar-contact-09.png'
        taskbar['files'].append(ninth)
        with self.assertRaises(RuntimeError):
            exporter.validate_manifest(value)


class ArchiveControls(unittest.TestCase):
    def make_archive(self, root, members):
        path = root / 'artifact.zip'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
            for name, raw in members:
                archive.writestr(name, raw)
        return path

    def test_only_exact_selected_file_is_extracted(self):
        raw = png()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = self.make_archive(root, [
                ('screened/session/desktop.png', raw),
                ('private/transcript.txt', b'must stay in archive'),
            ])
            item = artifact(raw, archive_path.stat().st_size,
                            hashlib.sha256(archive_path.read_bytes()).hexdigest())
            out = root / 'out'; out.mkdir()
            records, exported_bytes = exporter.extract_artifact(item, archive_path, out)
            self.assertEqual(records, [dict(sorted(file_entry(raw).items()))])
            self.assertEqual(exported_bytes, len(raw))
            self.assertEqual((out / 'evidence/native/desktop.png').read_bytes(), raw)
            self.assertFalse((out / 'private/transcript.txt').exists())

    def test_contact_sheet_is_bounded_and_maps_every_cell_to_an_exact_source(self):
        raws = [png(16, 9, (index * 20, 41, 55)) for index in range(1, 5)]
        sources = [contact_member(index, raw) for index, raw in enumerate(raws, start=1)]
        sheet = contact_sheet(1, sources)
        sheet.update(columns=2, thumbnail_width=160, thumbnail_height=90,
                     label_height=16, max_output_bytes=1_000_000)
        exact = {'member': sources[0]['member'],
                 'output': 'evidence/native/exact-frame-001.png'}
        sheet['exact_frames'] = [exact]
        inventory = json.dumps({'scope': 'screened synthetic VM', 'files': {
            source['member']: {'bytes': len(raw), 'uploaded_sha256': hashlib.sha256(raw).hexdigest()}
            for source, raw in zip(sources, raws)
        }}).encode()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = self.make_archive(root, list(zip(
                [source['member'] for source in sources], raws)) +
                [('upload-screening.json', inventory)] +
                [('private/transcript.txt', b'must stay in archive')])
            item = artifact(raws[0], archive_path.stat().st_size,
                            hashlib.sha256(archive_path.read_bytes()).hexdigest())
            item['files'] = [sheet]
            item['screening']['inventory_member'] = 'upload-screening.json'
            exporter.validate_manifest(manifest([item]))
            out = root / 'out'; out.mkdir()
            records, exported_bytes = exporter.extract_artifact(item, archive_path, out)
            self.assertEqual(len(records), 2)
            self.assertEqual([cell['member'] for cell in records[0]['cells']],
                             [source['member'] for source in sources])
            self.assertEqual((records[0]['width'], records[0]['height']), (320, 212))
            self.assertEqual(exported_bytes, records[0]['bytes'] + len(raws[0]))
            with Image.open(out / sheet['output']) as image:
                self.assertEqual(image.size, (320, 212))
            self.assertEqual((out / exact['output']).read_bytes(), raws[0])
            self.assertFalse((out / 'private/transcript.txt').exists())
            bad_inventory = json.loads(inventory)['files']
            bad_inventory[sources[0]['member']]['uploaded_sha256'] = '0' * 64
            with zipfile.ZipFile(archive_path) as archive, self.assertRaises(RuntimeError):
                exporter.render_contact_sheet(archive, sheet, root / 'bad/contact.png',
                                              bad_inventory, root / 'bad')

    def test_native_audio_is_bound_to_screening_inventory_and_measured_on_export(self):
        raw = wav_audio()
        member = 'virtual-audio/native-audio-boot.wav'
        audio = {
            'member': member, 'output': 'evidence/native/native-audio-boot.wav',
            'kind': 'native-system-audio',
            'privacy_class': 'validated-native-system-audio',
            'audio_class': 'native-virtual-output-boot', 'max_bytes': len(raw) + 100,
        }
        inventory = json.dumps({'scope': 'screened synthetic VM', 'files': {
            member: {'bytes': len(raw), 'uploaded_sha256': hashlib.sha256(raw).hexdigest()}
        }}).encode()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive_path = self.make_archive(root, [(member, raw),
                                                     ('upload-screening.json', inventory)])
            item = artifact(raw, archive_path.stat().st_size,
                            hashlib.sha256(archive_path.read_bytes()).hexdigest())
            item['files'] = [audio]
            item['screening']['inventory_member'] = 'upload-screening.json'
            exporter.validate_manifest(manifest([item]))
            out = root / 'out'; out.mkdir()
            records, exported_bytes = exporter.extract_artifact(item, archive_path, out)
            self.assertEqual((records[0]['bytes'], records[0]['sha256']),
                             (len(raw), hashlib.sha256(raw).hexdigest()))
            self.assertEqual(exported_bytes, len(raw))
            self.assertEqual((out / audio['output']).read_bytes(), raw)

    def test_changed_bytes_traversal_and_symlink_fail_closed(self):
        raw = png()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name, symlink in (('screened/session/desktop.png', False), ('../desktop.png', False),
                                  ('screened/session/desktop.png', True)):
                path = root / ('a' if not symlink and name.startswith('screened') else 'b' if '..' in name else 'c')
                with zipfile.ZipFile(path, 'w') as archive:
                    if symlink:
                        info = zipfile.ZipInfo(name)
                        info.create_system = 3
                        info.external_attr = (0o120777 << 16)
                        archive.writestr(info, raw)
                    else:
                        archive.writestr(name, raw + (b'changed' if path.name == 'a' else b''))
                item = artifact(raw, path.stat().st_size, hashlib.sha256(path.read_bytes()).hexdigest())
                out = root / ('out-' + path.name); out.mkdir()
                with self.subTest(name=name, symlink=symlink), self.assertRaises(RuntimeError):
                    exporter.extract_artifact(item, path, out)

    def test_json_privacy_filter_rejects_transcript_and_secret_shapes(self):
        for value in ({'transcript': 'hello'}, {'status': 'token=secret'},
                      {'status': 'person@example.org'}, {'text': 'hello'}):
            with self.subTest(value=value), self.assertRaises(RuntimeError):
                exporter.inspect_json_value(value)
        exporter.inspect_json_value({'status': 'passed', 'metrics': {'count': 3}})

    def test_pinned_safe_json_and_two_native_audio_classes_are_accepted(self):
        safe_json = b'{"metrics":{"count":3},"status":"passed"}\n'
        json_item = {
            'member': 'screened/result.json', 'output': 'evidence/result.json',
            'kind': 'json', 'privacy_class': 'screened-summary',
            'bytes': len(safe_json), 'sha256': hashlib.sha256(safe_json).hexdigest(),
        }
        exporter.validate_file(json_item)
        exporter.inspect_selected(safe_json, json_item)
        native = wav_audio()
        native_item = {
            'member': 'virtual-audio/native-audio-boot.wav',
            'output': 'evidence/native-audio-boot.wav', 'kind': 'native-system-audio',
            'privacy_class': 'validated-native-system-audio',
            'audio_class': 'native-virtual-output-boot', 'max_bytes': len(native) + 100,
        }
        exporter.validate_file(native_item)
        exporter.inspect_native_wav(native)
        install_item = native_item | {
            'member': 'virtual-audio/native-audio-install.wav',
            'output': 'evidence/native-audio-install.wav',
            'audio_class': 'native-virtual-output-install',
        }
        exporter.validate_file(install_item)
        exporter.inspect_native_wav(native)
        native_artifact = artifact()
        native_artifact['files'] = [native_item, install_item]
        native_artifact['screening']['inventory_member'] = 'upload-screening.json'
        exporter.validate_manifest(manifest([native_artifact]))
        silent = wav_audio(nonzero=False)
        with self.assertRaises(RuntimeError):
            exporter.inspect_native_wav(silent)

    def test_dictation_transcript_and_cross_workflow_audio_are_rejected(self):
        audio = wav_audio()
        base = {
            'member': 'virtual-audio/native-audio-boot.wav',
            'output': 'evidence/native-audio-boot.wav', 'kind': 'native-system-audio',
            'privacy_class': 'validated-native-system-audio',
            'audio_class': 'native-virtual-output-boot', 'max_bytes': len(audio) + 100,
        }
        for field, name in (('member', 'virtual-audio/dictation-native-audio-boot.wav'),
                            ('output', 'evidence/whisper-native-audio-boot.wav')):
            changed = copy.deepcopy(base); changed[field] = name
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                exporter.validate_file(changed)
        narration = base | {'member': 'screened/narration.mp3',
                            'output': 'evidence/narration.mp3',
                            'audio_class': 'showcase-public-narration',
                            'privacy_class': 'public-narration'}
        with self.assertRaises(RuntimeError):
            exporter.validate_file(narration)
        wrong_workflow = artifact()
        wrong_workflow['files'] = [base]
        wrong_workflow['screening']['inventory_member'] = 'upload-screening.json'
        wrong_workflow['workflow_path'] = '.github/workflows/dictation-candidate-20261009.yml'
        with self.assertRaises(RuntimeError):
            exporter.validate_manifest(manifest([wrong_workflow]))


class IdentityAndActivationControls(unittest.TestCase):
    def test_remote_run_and_artifact_must_match_all_pins_and_be_successful(self):
        item = artifact()
        metadata = {'id': 456, 'name': item['name'], 'expired': False,
                    'size_in_bytes': 100, 'digest': 'sha256:' + 'a' * 64,
                    'workflow_run': {'id': 123, 'head_sha': 'b' * 40,
                                     'head_branch': item['head_branch']}}
        run = {'id': 123, 'run_attempt': 1, 'head_sha': 'b' * 40,
               'head_branch': item['head_branch'], 'path': item['workflow_path'],
               'event': 'push', 'status': 'completed', 'conclusion': 'success'}
        exporter.verify_remote_identity(item, metadata, run)
        for field, value in (('conclusion', 'failure'), ('head_sha', 'c' * 40),
                             ('path', '.github/workflows/ci.yml')):
            changed = copy.deepcopy(run); changed[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                exporter.verify_remote_identity(item, metadata, changed)

    def test_activation_requires_marker_only_child_on_fixed_branch(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.name', 'test'], check=True)
            subprocess.run(['git', '-C', str(root), 'config', 'user.email', 'test@example.invalid'], check=True)
            manifest_path = root / exporter.MANIFEST
            manifest_path.parent.mkdir(parents=True)
            manifest_path.write_text(json.dumps(manifest()))
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'prepare'], check=True)
            parent = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
            marker = root / exporter.MARKER
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text(parent + '\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(['git', '-C', str(root), 'commit', '-qm', 'activate'], check=True)
            head = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
            event = root / 'event.json'
            (root / '.git/info/exclude').write_text('event.json\n')
            event.write_text(json.dumps({'before': parent, 'after': head}))
            env = {'GITHUB_ACTIONS': 'true', 'RUNNER_ENVIRONMENT': 'github-hosted',
                   'GITHUB_REPOSITORY': exporter.REPOSITORY,
                   'GITHUB_REF': 'refs/heads/' + exporter.SOURCE_BRANCH,
                   'GITHUB_EVENT_NAME': 'push', 'GITHUB_RUN_ATTEMPT': '1',
                   'GITHUB_SHA': head, 'GITHUB_EVENT_PATH': str(event)}
            with patch.object(exporter, 'ROOT', root), patch.dict(os.environ, env, clear=False):
                actual, actual_parent, actual_head = exporter.validate_activation(manifest_path)
            self.assertEqual((actual, actual_parent, actual_head), (manifest(), parent, head))


class WorkflowControls(unittest.TestCase):
    def test_workflow_is_fixed_marker_only_nonpublishing_and_nonreplacing(self):
        text = (ROOT / exporter.WORKFLOW).read_text()
        self.assertIn('branches: [codex/final-evidence-review-export-20261016]', text)
        self.assertIn('paths: [.github/final-evidence-review-export-20261016.activate]', text)
        self.assertNotIn('workflow_dispatch:', text)
        self.assertIn('persist-credentials: false', text)
        self.assertIn('apt-get install -y python3-pil', text)
        self.assertIn('contents: write', text)
        self.assertIn('actions: read', text)
        self.assertIn('TARGET_BRANCH: codex/final-evidence-review-artifacts-20261016', text)
        self.assertIn('Review branch already exists; refusing to replace it', text)
        self.assertIn('push origin "HEAD:refs/heads/$TARGET_BRANCH"', text)
        for forbidden in ('--force', 'gh release', 'tools/build-iso.sh', 'tools/publish-repo.sh',
                          'refs/heads/main', 'actions/upload-artifact'):
            self.assertNotIn(forbidden, text)


if __name__ == '__main__':
    unittest.main()
