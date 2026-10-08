"""Fixed artifact, unsplit image and upload screening negative controls."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

HERE = Path(__file__).resolve().parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F, S = load('fetch-image'), load('screen-evidence')


class ImageTransportControls(unittest.TestCase):
    def image(self):
        return dict(run_id=1, artifact_id=2, source_sha='1' * 40,
                    name='Arctic-Linux-1.2-candidate-1-1-x86_64.iso',
                    bytes=3, sha256=hashlib.sha256(b'iso').hexdigest(),
                    archive_sha256='2' * 64, archive_bytes=100)

    def test_fixed_run_and_artifact_identity_adverses(self):
        image = self.image()
        run = dict(id=1, head_sha=image['source_sha'], event='workflow_dispatch',
                   path='.github/workflows/iso.yml', status='completed', conclusion='success')
        artifact = dict(id=2, name='arctic-linux-iso', expired=False, size_in_bytes=100,
                        digest='sha256:' + image['archive_sha256'],
                        workflow_run=dict(id=1, head_sha=image['source_sha']))
        F.validate(image, run, artifact)
        for key, value in (('head_sha', '3' * 40), ('event', 'push'), ('conclusion', 'failure')):
            wrong = dict(run, **{key: value})
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                F.validate(image, wrong, artifact)
        for key, value in (('id', 3), ('expired', True), ('digest', 'sha256:' + '4' * 64)):
            wrong = dict(artifact, **{key: value})
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                F.validate(image, run, wrong)

    def test_successful_run_cannot_hide_skipped_or_failed_boot_lanes(self):
        job = dict(name='iso', run_attempt=1, head_sha=self.image()['source_sha'],
                   status='completed', conclusion='success', steps=[
                       dict(name=name, status='completed', conclusion='success') for name in F.BOOT_STEPS])
        F.validate_boot_steps(self.image(), [job])
        for index in range(len(F.BOOT_STEPS)):
            for fault in ('skipped', 'failure', 'missing', 'duplicate'):
                wrong = copy.deepcopy(job)
                if fault == 'missing':
                    wrong['steps'].pop(index)
                elif fault == 'duplicate':
                    wrong['steps'].append(dict(wrong['steps'][index]))
                else:
                    wrong['steps'][index]['conclusion'] = fault
                with self.subTest(index=index, fault=fault), self.assertRaises(RuntimeError):
                    F.validate_boot_steps(self.image(), [wrong])

    def archive(self, path, image, extra=None, content=b'iso', source=None):
        wanted = 'iso/' + image['name']
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(wanted, content)
            archive.writestr(wanted + '.sha256', image['sha256'] + '  ' + image['name'] + '\n')
            archive.writestr('BUILD-INFO', 'git_commit=' + (source or image['source_sha']) + '\narctic_repos=enabled\n')
            if extra:
                archive.writestr(extra, 'untrusted')

    def test_actual_bytes_mismatch_wrong_source_and_unsafe_member_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = self.image()
            for index, kwargs in enumerate(({}, dict(content=b'bad'), dict(source='3' * 40), dict(extra='../unsafe'))):
                archive = root / str(index)
                self.archive(archive, image, **kwargs)
                if not kwargs:
                    F.extract(archive, root / 'valid', image)
                    self.assertEqual((root / 'valid/iso' / image['name']).read_bytes(), b'iso')
                else:
                    with self.subTest(kwargs=kwargs), self.assertRaises(RuntimeError):
                        F.extract(archive, root / ('invalid-' + str(index)), image)

    def test_upload_redacts_text_and_failure_publishes_no_partial_directory(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'evidence'
            source.mkdir()
            original = 'fake@example.invalid github_pat_SYNTHETIC authorization: Bearer SYNTHETIC https://example.invalid/?signature=SYNTHETIC'
            (source / 'serial.log').write_text(original)
            target = root / 'screened'
            S.screen(source, target)
            self.assertEqual((source / 'serial.log').read_text(), original)
            value = (target / 'serial.log').read_text()
            self.assertNotIn('SYNTHETIC', value)
            self.assertNotIn('fake@example.invalid', value)
            report = json.loads((target / 'upload-screening.json').read_text())
            self.assertEqual(report['files']['serial.log']['redactions'], 4)
            (source / 'z-unexpected.iso').write_bytes(b'private disk')
            with self.assertRaises(RuntimeError):
                S.screen(source, root / 'rejected')
            self.assertFalse((root / 'rejected').exists())
