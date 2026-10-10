"""Real temporary sysfs graph controls for the narrow unbacked-zram proof."""
import contextlib
import copy
import io
import os
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import test_target_diagnostics as T
A = T.A
DEFAULT_ROW = object()


class RamFixture:
    """Actual links/reads; controlled root and block metadata need no privileges.

    No block device is opened or created. Only the fixture's ownership and its
    synthetic /dev node type/rdev are intercepted, retaining real inode,
    graph, attribute, nofollow and bounded-read behavior.
    """
    def __init__(self, root, number=2, major=252, size=2 * 1024**3):
        self.root = root
        self.sys, self.dev, self.proc = (root / name for name in ('sys', 'dev', 'proc'))
        self.number, self.major, self.size = number, major, size
        self.name = 'zram' + str(number)
        self.node = self.sys / 'devices/virtual/block' / self.name
        self.device = self.dev / self.name
        self.row = dict(name=self.name, type='disk', size=size)
        self.owners, self.modes, self.rdevs = {}, {}, {}
        self.open_events, self.read_events = [], []
        self.on_open = None
        self.on_read = None
        for directory in (self.node, self.node / 'slaves', self.node / 'holders',
                          self.sys / 'class/block', self.sys / 'dev/block',
                          self.sys / 'block', self.dev, self.proc):
            directory.mkdir(parents=True, exist_ok=True)
        (self.sys / 'class/block' / self.name).symlink_to(self.node)
        (self.sys / 'block' / self.name).symlink_to(self.node)
        (self.sys / 'dev/block' / (str(major) + ':' + str(number))).symlink_to(self.node)
        (self.node / 'subsystem').symlink_to(self.sys / 'class/block')
        values = dict(dev=str(major) + ':' + str(number), size=str(size // 512),
                      disksize=str(size), initstate='1', comp_algorithm='lzo-rle lzo [zstd]',
                      backing_dev='none', io_stat='0 0 0 0', mm_stat='0 0 0 0 0 0 0 0 0',
                      diskseq='100')
        for name, value in values.items():
            (self.node / name).write_text(value + '\n')
        self.device.write_bytes(b'synthetic block identity; never opened')
        self.rdevs[self.device] = os.makedev(major, number)
        (self.proc / 'devices').write_text(
            'Character devices:\n  1 mem\n\nBlock devices:\n  1 ramdisk\n  8 sd\n'
            + str(major) + ' zram\n254 virtblk\n')

    def replace_link(self, path, target):
        path.unlink()
        path.symlink_to(target)

    @contextlib.contextmanager
    def intercepted(self):
        original_stat, original_lstat = os.stat, os.lstat
        original_fstat, original_open, original_read = os.fstat, os.open, os.read
        original_readlink = os.readlink

        def owned_path(value):
            if isinstance(value, int):
                return None
            path = Path(os.fsdecode(value)).absolute()
            return path if path == self.root or self.root in path.parents else None

        def metadata(info, path):
            if path is None:
                return info
            fields = {name: getattr(info, name) for name in dir(info) if name.startswith('st_')}
            fields['st_uid'] = self.owners.get(path, 0)
            fields['st_gid'] = 0
            fields['st_mode'] = self.modes.get(path, info.st_mode)
            if path == self.device and stat.S_ISREG(info.st_mode):
                fields['st_mode'] = self.modes.get(path, stat.S_IFBLK | 0o600)
                fields['st_rdev'] = self.rdevs.get(path, os.makedev(self.major, self.number))
            return SimpleNamespace(**fields)

        def observed_stat(value, *args, **kwargs):
            return metadata(original_stat(value, *args, **kwargs), owned_path(value))

        def observed_lstat(value, *args, **kwargs):
            return metadata(original_lstat(value, *args, **kwargs), owned_path(value))

        def fd_path(fd):
            try:
                return owned_path(original_readlink('/proc/self/fd/' + str(fd)))
            except OSError:
                return None

        def observed_fstat(fd):
            return metadata(original_fstat(fd), fd_path(fd))

        def observed_open(value, flags, *args, **kwargs):
            path = owned_path(value)
            if path is not None:
                self.open_events.append((path, flags))
                if self.on_open is not None:
                    self.on_open(path, flags)
            return original_open(value, flags, *args, **kwargs)

        def observed_read(fd, size):
            path = fd_path(fd)
            data = original_read(fd, size)
            if path is not None:
                self.read_events.append((path, size))
                if self.on_read is not None:
                    self.on_read(path, data)
            return data

        with contextlib.ExitStack() as stack:
            for name, function in (('stat', observed_stat), ('lstat', observed_lstat),
                                   ('fstat', observed_fstat), ('open', observed_open), ('read', observed_read)):
                stack.enter_context(patch.object(os, name, function))
            yield

    def proven(self, row=DEFAULT_ROW, helper=None):
        with self.intercepted():
            return (helper or A.proven_unbacked_zram)(self.row if row is DEFAULT_ROW else row,
                                                     self.sys, self.dev, self.proc)


class RamAbiControls(unittest.TestCase):
    def test_valid_real_graph_accepts_only_the_bound_unbacked_ram_disk(self):
        for number, major, size in ((0, 251, 4096), (2, 252, 2 * 1024**3), (63, 253, 64 * 1024**3)):
            with self.subTest(number=number, major=major), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp), number, major, size)
                self.assertIs(fixture.proven(), True)
                self.assertFalse(any(path == fixture.device for path, _ in fixture.open_events))

    def test_names_row_types_and_sizes_are_closed(self):
        class PrivateInt(int):
            pass
        rows = [dict(name=name, type='disk', size=4096) for name in
                ('sda', 'vdb', 'ram0', 'zram', 'zram-1', 'zram10000', 'zram02', 'zram2/../../vda', '../zram2')]
        rows += [dict(name='zram2', type=kind, size=4096) for kind in ('part', 'loop', 'rom', None)]
        rows += [dict(name='zram2', type='disk', size=size) for size in
                 (True, '4096', 4096.0, PrivateInt(4096), None, 0, -1, 1, 4095, 64 * 1024**3 + 512)]
        rows += [None, [], {}, dict(name='zram2', size=4096)]
        for row in rows:
            with self.subTest(row=row), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                self.assertIs(fixture.proven(row), False)

    def test_physical_or_parented_names_cannot_masquerade_as_zram(self):
        for kind in ('physical-canonical', 'device-link', 'partition', 'slave'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                if kind == 'physical-canonical':
                    physical = fixture.sys / 'devices/pci0000:00/0000:00:04.0/block/zram2'
                    physical.mkdir(parents=True)
                    fixture.replace_link(fixture.sys / 'class/block/zram2', physical)
                elif kind == 'device-link':
                    (fixture.node / 'device').symlink_to(fixture.sys)
                elif kind == 'partition':
                    (fixture.node / 'partition').write_text('1\n')
                else:
                    (fixture.node / 'slaves/vda').symlink_to(fixture.sys)
                self.assertIs(fixture.proven(), False)

    def test_all_canonical_subsystem_and_major_minor_backlinks_are_required(self):
        for kind in ('class-missing', 'class-wrong', 'subsystem-missing',
                     'subsystem-wrong', 'dev-link-missing', 'dev-link-wrong', 'minor-mismatch'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                class_link = fixture.sys / 'class/block/zram2'
                if kind == 'class-missing':
                    class_link.unlink()
                elif kind == 'class-wrong':
                    fixture.replace_link(class_link, fixture.sys)
                elif kind == 'subsystem-missing':
                    (fixture.node / 'subsystem').unlink()
                elif kind == 'subsystem-wrong':
                    fixture.replace_link(fixture.node / 'subsystem', fixture.sys)
                elif kind == 'dev-link-missing':
                    (fixture.sys / 'dev/block/252:2').unlink()
                elif kind == 'dev-link-wrong':
                    fixture.replace_link(fixture.sys / 'dev/block/252:2', fixture.sys)
                else:
                    (fixture.node / 'dev').write_text('252:3\n')
                    fixture.rdevs[fixture.device] = os.makedev(252, 3)
                    (fixture.sys / 'dev/block/252:3').symlink_to(fixture.node)
                self.assertIs(fixture.proven(), False)

    def test_block_node_type_rdev_symlink_and_owner_are_required(self):
        for kind in ('regular', 'character', 'rdev', 'missing', 'symlink', 'owner'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                if kind == 'regular':
                    fixture.modes[fixture.device] = stat.S_IFREG | 0o600
                elif kind == 'character':
                    fixture.modes[fixture.device] = stat.S_IFCHR | 0o600
                elif kind == 'rdev':
                    fixture.rdevs[fixture.device] = os.makedev(8, 2)
                elif kind == 'missing':
                    fixture.device.unlink()
                elif kind == 'symlink':
                    target = fixture.dev / 'other'
                    target.write_bytes(b'synthetic alias')
                    fixture.device.unlink()
                    fixture.device.symlink_to(target)
                else:
                    fixture.owners[fixture.device] = 1000
                self.assertIs(fixture.proven(), False)

    def test_dynamic_major_registration_is_exact_and_unique(self):
        cases = ('Character devices:\n252 zram\n\nBlock devices:\n254 virtblk\n',
                 'Block devices:\n252 sd\n', 'Block devices:\n251 zram\n',
                 'Block devices:\n252 zram\n252 zram\n',
                 'Block devices:\n252 zram\n251 zram\n',
                 'Block devices:\n252 zram-private\n')
        for data in cases:
            with self.subTest(data=data), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                (fixture.proc / 'devices').write_text(data)
                self.assertIs(fixture.proven(), False)

    def test_backed_missing_or_malformed_zram_attributes_fail_closed(self):
        cases = [('backing_dev', value) for value in ('/dev/vda1\n', '/private/backing\n', '', 'None\n', 'none extra\n')]
        cases += [('initstate', value) for value in ('0\n', '2\n', 'true\n')]
        cases += [('comp_algorithm', value) for value in ('zstd lzo\n', '[zstd] [lzo]\n', '[]\n', '[zstd/private]\n')]
        cases += [('dev', value) for value in ('8:2\n', '252:2 extra\n', '-1:2\n')]
        cases += [(name, None) for name in ('backing_dev', 'initstate', 'disksize', 'dev', 'size', 'comp_algorithm')]
        for name, value in cases:
            with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                path = fixture.node / name
                if value is None:
                    path.unlink()
                else:
                    path.write_text(value)
                self.assertIs(fixture.proven(), False)

    def test_size_capacity_initialization_and_row_must_agree(self):
        cases = [('size', '1\n'), ('size', '-1\n'), ('size', 'true\n'),
                 ('disksize', '0\n'), ('disksize', '4096\n'), ('disksize', '-1\n'),
                 ('disksize', str(64 * 1024**3 + 512) + '\n')]
        for name, value in cases:
            with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                (fixture.node / name).write_text(value)
                self.assertIs(fixture.proven(), False)
        with tempfile.TemporaryDirectory() as temp:
            fixture = RamFixture(Path(temp))
            row = dict(fixture.row, size=fixture.size + 512)
            self.assertIs(fixture.proven(row), False)

    def test_attributes_and_proc_inventory_are_bounded_regular_nofollow_reads(self):
        for kind in ('symlink', 'oversize', 'fifo', 'non-root', 'writable', 'proc-oversize', 'proc-symlink'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                path = fixture.node / 'backing_dev'
                if kind in ('symlink', 'proc-symlink'):
                    if kind == 'proc-symlink':
                        path = fixture.proc / 'devices'
                    target = fixture.root / 'alias-source'
                    target.write_bytes(path.read_bytes())
                    path.unlink()
                    path.symlink_to(target)
                elif kind == 'oversize':
                    path.write_bytes(b'none' + b' ' * 65536 + b'\n')
                elif kind == 'fifo':
                    path.unlink()
                    os.mkfifo(path, 0o600)
                elif kind == 'non-root':
                    fixture.owners[path] = 1000
                elif kind == 'writable':
                    path.chmod(0o666)
                else:
                    path = fixture.proc / 'devices'
                    path.write_bytes(path.read_bytes() + b'\n' * 131072)
                self.assertIs(fixture.proven(), False)
                for opened, flags in fixture.open_events:
                    if opened == path:
                        self.assertTrue(flags & os.O_NOFOLLOW)
                        self.assertTrue(flags & os.O_NONBLOCK)

    def test_required_directories_are_root_owned_and_not_writable_or_redirected(self):
        for path_kind, bad in (('node', 'owner'), ('node', 'writable'), ('slaves', 'owner'),
                               ('slaves', 'symlink')):
            with self.subTest(path_kind=path_kind, bad=bad), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                path = {'node': fixture.node, 'slaves': fixture.node / 'slaves',
                        'class': fixture.sys / 'class/block'}[path_kind]
                if bad == 'owner':
                    fixture.owners[path] = 1000
                elif bad == 'writable':
                    path.chmod(0o777)
                else:
                    path.rmdir()
                    path.symlink_to(fixture.root)
                self.assertIs(fixture.proven(), False)

    def test_changed_second_observation_cannot_reuse_the_first_proof(self):
        for kind in ('backing', 'size', 'initstate', 'algorithm', 'slave', 'rdev', 'inode', 'backlink', 'major'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                count = 0
                original_attribute = A.ram_attribute
                def changed_attribute(path, limit=4096):
                    nonlocal count
                    value = original_attribute(path, limit)
                    if path != fixture.node / 'comp_algorithm':
                        return value
                    count += 1
                    if count != 1:
                        return value
                    if kind == 'backing':
                        (fixture.node / 'backing_dev').write_text('/dev/vda1\n')
                    elif kind == 'size':
                        (fixture.node / 'disksize').write_text('4096\n')
                        (fixture.node / 'size').write_text('8\n')
                    elif kind == 'initstate':
                        (fixture.node / 'initstate').write_text('0\n')
                    elif kind == 'algorithm':
                        (fixture.node / 'comp_algorithm').write_text('[lzo] zstd\n')
                    elif kind == 'slave':
                        (fixture.node / 'slaves/vda').symlink_to(fixture.sys)
                    elif kind == 'rdev':
                        fixture.rdevs[fixture.device] = os.makedev(8, 2)
                    elif kind == 'inode':
                        replacement = fixture.dev / 'replacement'
                        replacement.write_bytes(b'second block identity')
                        replacement.replace(fixture.device)
                    elif kind == 'backlink':
                        fixture.replace_link(fixture.sys / 'dev/block/252:2', fixture.sys)
                    else:
                        (fixture.proc / 'devices').write_text('Block devices:\n252 sd\n')
                    return value
                with patch.object(A, 'ram_attribute', changed_attribute):
                    self.assertIs(fixture.proven(), False)
                self.assertGreaterEqual(count, 1)

    def test_read_failures_stay_private_and_interrupts_are_not_swallowed(self):
        for error in (OSError(5, T.PRIVATE), ValueError(T.PRIVATE), KeyboardInterrupt(), SystemExit(2)):
            with self.subTest(error=type(error).__name__), tempfile.TemporaryDirectory() as temp:
                fixture = RamFixture(Path(temp))
                def failure(path, flags):
                    if path == fixture.node / 'backing_dev':
                        raise error
                fixture.on_open = failure
                output, errors = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
                    if isinstance(error, (OSError, ValueError)):
                        self.assertIs(fixture.proven(), False)
                    else:
                        with self.assertRaises(type(error)) as caught:
                            fixture.proven()
                        self.assertIs(caught.exception, error)
                self.assertEqual(output.getvalue() + errors.getvalue(), '')

    def test_persistent_inventory_exempts_only_actual_proved_ram_and_keeps_owned_guards(self):
        for kind in ('valid', 'backed', 'unproved-name', 'foreign-after-valid', 'owned-size', 'owned-rdev', 'owned-mount'):
            with self.subTest(kind=kind), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                fixture = RamFixture(root / 'graph')
                helper = A.proven_unbacked_zram
                extra = copy.deepcopy(fixture.row)
                override = dict(disks=[dict(name='vda', type='disk', size=64 * 1024**3), extra])
                if kind == 'backed':
                    (fixture.node / 'backing_dev').write_text('/dev/vda1\n')
                elif kind == 'unproved-name':
                    extra['name'] = 'sda'
                elif kind == 'foreign-after-valid':
                    override['disks'].append(dict(name='sda', type='disk', size=4096))
                elif kind == 'owned-size':
                    override['size'] = '1'
                elif kind == 'owned-rdev':
                    override['major_minor'] = '8:0'
                elif kind == 'owned-mount':
                    override['mounts'] = [dict(name='vda', mountpoints=['/mounted'])]
                value = T.TargetControls().instance(root / 'target')
                model = T.TargetModel(self, value, override=override)
                value.command = model.command
                def actual_proof(row):
                    with patch.object(A, 'Path', Path):
                        return fixture.proven(row, helper)
                with patch.object(A, 'Path', model.path), patch.object(A, 'proven_unbacked_zram', actual_proof):
                    if kind == 'valid':
                        result = value.target_disk(pristine=True)
                        self.assertEqual(result['path'], '/dev/vda')
                        self.assertEqual(result['serial'], 'ARCTIC-OWNED-TARGET')
                        self.assertEqual(value.diagnostic_phase, 'prepare-target')
                    else:
                        with self.assertRaises(RuntimeError):
                            value.target_disk(pristine=True)


if __name__ == '__main__':
    unittest.main()
