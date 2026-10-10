"""Actual main() controls for owned parent/child images; no engine or guest."""
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).parent))
import test_stage_diagnostics as Stage


class DockerImageModel:
    """Reproduce dependency rejection and Docker's default ancestor pruning."""
    parent = 'd' * 64
    child = 'e' * 64
    foreign = 'f' * 64
    malformed = 'foreign-image:latest'

    def __init__(self, owner, child_present=True, failed_image=None):
        self.owner = owner
        self.alive = {self.parent, self.foreign, self.malformed}
        if child_present:
            self.alive.add(self.child)
        self.failed_image = failed_image
        self.calls = []

    def remove(self, argv, kwargs):
        self.owner.assertIn(argv, (
            ['docker', 'image', 'rm', self.parent],
            ['docker', 'image', 'rm', self.child],
            ['docker', 'image', 'rm', '--no-prune', self.parent],
            ['docker', 'image', 'rm', '--no-prune', self.child]))
        self.owner.assertEqual(kwargs, dict(check=True, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
        image = argv[-1]
        self.calls.append(list(argv))
        if image == self.failed_image:
            raise subprocess.TimeoutExpired(['private-owned-image-command'], 30,
                output=b'private-transcript-output', stderr=b'private-transcript-stderr')
        if image not in self.alive or (image == self.parent and self.child in self.alive):
            raise subprocess.CalledProcessError(1, ['private-owned-image-command'],
                output=b'private-transcript-output', stderr=b'private-transcript-stderr')
        self.alive.remove(image)
        if image == self.child and '--no-prune' not in argv:
            self.alive.discard(self.parent)
        return SimpleNamespace(returncode=0)


class Controls(unittest.TestCase):
    def test_actual_main_removes_child_then_parent_without_implicit_pruning(self):
        for active in (False, True):
            with self.subTest(active=active):
                model = DockerImageModel(self)
                status, stdout, state, _, contract = Stage.Controls().pipeline(
                    active=active, image_cleanup=model.remove)
                self.assertEqual(status, 0)
                self.assertEqual(stdout, '')
                self.assertEqual(state['errors'], [])
                self.assertIn('pending_manual_visual_review', state['status'])
                self.assertIs(state['release_acceptance'], False)
                self.assertEqual(contract.cleanup_images, [model.child, model.parent])
                self.assertEqual(model.calls, [
                    ['docker', 'image', 'rm', '--no-prune', model.child],
                    ['docker', 'image', 'rm', '--no-prune', model.parent]])
                self.assertEqual(model.alive, {model.foreign, model.malformed})

    def test_failed_child_cleanup_still_attempts_parent_and_persists_failure(self):
        for active in (False, True):
            with self.subTest(active=active):
                model = DockerImageModel(self, failed_image=DockerImageModel.child)
                status, stdout, state, _, contract = Stage.Controls().pipeline(
                    active=active, image_cleanup=model.remove)
                self.assertEqual(status, 1)
                self.assertEqual(state['status'], 'failed')
                self.assertIs(state['release_acceptance'], False)
                self.assertEqual(contract.cleanup_images, [model.child, model.parent])
                self.assertEqual(len(state['errors']), 2)
                self.assertEqual(stdout.splitlines(), [
                    'ARCTIC-INSTALLER-DIAGNOSTIC=installer-cleanup-timeout',
                    'ARCTIC-INSTALLER-DIAGNOSTIC=installer-cleanup-command-error'])
                self.assertNotIn('private-', stdout)
                self.assertEqual(model.alive, {model.parent, model.child, model.foreign, model.malformed})

    def test_prior_runtime_failure_is_preserved_after_owned_images_are_removed(self):
        for active in (False, True):
            with self.subTest(active=active):
                model = DockerImageModel(self)
                status, stdout, state, _, contract = Stage.Controls().pipeline(
                    'run-live', active=active, image_cleanup=model.remove)
                self.assertEqual(status, 1)
                self.assertEqual(state['status'], 'failed')
                self.assertIs(state['release_acceptance'], False)
                self.assertEqual(len(state['errors']), 1)
                self.assertEqual(stdout.strip(), 'ARCTIC-INSTALLER-DIAGNOSTIC=installer-run-live-value-error')
                self.assertEqual(contract.cleanup_images, [model.child, model.parent])
                self.assertEqual(model.alive, {model.foreign, model.malformed})

    def test_partial_preparation_removes_only_images_allocated_before_failure(self):
        for active in (False, True):
            for stage, owned in (('docker-info', []), ('provision', []),
                                 ('capture-build', [DockerImageModel.parent])):
                with self.subTest(active=active, stage=stage):
                    model = DockerImageModel(self, child_present=False)
                    status, stdout, state, _, contract = Stage.Controls().pipeline(
                        stage, active=active, image_cleanup=model.remove)
                    self.assertEqual(status, 1)
                    self.assertEqual(state['status'], 'failed')
                    self.assertEqual(contract.cleanup_images, owned)
                    self.assertIs(state['release_acceptance'], False)
                    self.assertNotIn('private-', stdout)
                    expected = {model.foreign, model.malformed}
                    if not owned:
                        expected.add(model.parent)
                    self.assertEqual(model.alive, expected)


if __name__ == '__main__':
    unittest.main()
