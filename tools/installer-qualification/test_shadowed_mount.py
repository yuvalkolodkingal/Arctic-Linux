"""Actual writer plus real findmnt/kernel-table controls; no mounts, disk or VM."""
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_source_copy_diagnostics as F

A, G = F.A, F.G
BASE = '24 1 0:34 / / rw,relatime - overlay overlay rw\n'
BIND = '28 24 0:34 /mnt /mnt rw,relatime - overlay overlay rw\n'
OWNED = '29 28 254:1 /@ /mnt rw,relatime - btrfs /dev/vda1 rw,subvolid=256,subvol=/@\n'


@unittest.skipUnless(shutil.which('findmnt'), 'findmnt is required for kernel-table ABI controls')
class ShadowedMountControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='arctic-synthetic-mount-table-')
        self.addCleanup(self.temp.cleanup)
        self.table = Path(self.temp.name) / 'mountinfo'
        self.fixture = F.WriterFixture(self)
        self.commands = []
        self.original_commands = False
        self.fixture.value.command = self.command

    def command(self, argv):
        self.assertEqual(argv[0], 'findmnt')
        self.assertIn('--uniq', argv)
        self.assertNotIn('--first-only', argv)
        self.commands.append(list(argv))
        actual = [argv[0], '--kernel', '--tab-file', str(self.table)] + argv[1:]
        if self.original_commands:
            actual.remove('--uniq')
        result = subprocess.run(actual, capture_output=True, text=True, timeout=5, check=True)
        return 0, result.stdout.strip(), result.stderr.strip()

    def writer(self, data):
        self.table.write_text(data)
        before = hashlib.sha256(self.table.read_bytes()).hexdigest()
        with patch.object(A, 'Path', self.fixture.path), patch.object(G, 'process_proof',
                lambda *args: self.fixture.observe('writer-process-proof', (self.fixture.proof, None))):
            try:
                return self.fixture.value.writer({'daemon': {'pid': 20}})
            finally:
                self.assertEqual(hashlib.sha256(self.table.read_bytes()).hexdigest(), before)

    def rejected(self, data, message='actual writer target mount is not owned btrfs'):
        with self.assertRaises(RuntimeError) as caught:
            self.writer(data)
        self.assertEqual(caught.exception.args, (message,))
        self.assertEqual(self.fixture.value.diagnostic_phase,
                         'writer-partition-guard' if message.startswith('target partition') else 'writer-mount-guard')

    def test_private_bind_and_topmost_btrfs_use_original_exact_proof(self):
        value = self.writer(BASE + BIND + OWNED)
        self.assertEqual(value['mount'], {'target': '/mnt', 'source': '/dev/vda1[/@]',
            'block_source': '/dev/vda1', 'fstype': 'btrfs', 'major_minor': '254:1'})
        self.assertIs(value['process'], self.fixture.proof)
        self.assertEqual(value['ancestor_pids'], [30, 20])
        self.assertEqual(self.fixture.value.diagnostic_phase, 'copy-writer')
        self.assertEqual(len(self.commands), 3)

    def test_original_queries_fail_same_legitimate_stack_counterfactual(self):
        self.original_commands = True
        self.rejected(BASE + BIND + OWNED)

    def test_single_owned_mount_retains_exact_original_proof(self):
        value = self.writer(BASE + OWNED.replace('29 28', '29 24'))
        self.assertEqual(value['mount']['block_source'], '/dev/vda1')
        self.assertEqual(value['mount']['source'], '/dev/vda1[/@]')

    def test_foreign_or_non_btrfs_topmost_cannot_reuse_shadowed_owned_mount(self):
        for top in (
            '30 29 254:17 /@ /mnt rw - btrfs /dev/vdb1 rw\n',
            '30 29 254:1 / /mnt rw - ext4 /dev/vda1 rw\n',
            '30 29 0:35 / /mnt rw - tmpfs tmpfs rw\n',
            '30 29 0:36 /mnt /mnt rw - overlay overlay rw\n',
            '30 29 254:1 /foreign /mnt rw - btrfs /dev/vda1 rw\n',
            '30 29 254:0 /@ /mnt rw - btrfs /dev/vda rw\n'):
            self.commands.clear()
            self.rejected(BASE + BIND + OWNED + top)

    def test_original_sysfs_partition_parent_guard_remains_fatal(self):
        self.fixture.foreign_partition = True
        self.rejected(BASE + BIND + OWNED, 'target partition belongs to another disk')

    def test_more_than_one_shadowed_row_still_selects_only_owned_topmost(self):
        second = '29 28 0:35 / /mnt rw - tmpfs tmpfs rw\n'
        value = self.writer(BASE + BIND + second + OWNED.replace('29 28', '30 29'))
        self.assertEqual(value['mount']['fstype'], 'btrfs')
        self.assertEqual(value['mount']['source'], '/dev/vda1[/@]')


if __name__ == '__main__':
    unittest.main()
