"""Fail-closed source controls; these do not claim guest/runtime qualification."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import socket
import stat
import struct
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installer_guest_controls', Path(__file__).with_name('guest.py'))
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


def context():
    return dict(schema='arctic-installer-context-v1', source_sha='1' * 40, execution_sha='2' * 40,
                iso_sha256='3' * 64, iso_bytes=1_929_381_888, token='4' * 32,
                checker_sha256='5' * 64, runtime_sha256='6' * 64,
                native_sha256='7' * 64, capture_sha256='8' * 64)


def engine():
    return dict(hello=dict(engine_version='1.2.1', protocol_version=1, live=True, mock=False, state='wizard', firmware='uefi'),
                wizard=dict(current='keyboard', state='wizard', steps=[dict(id='keyboard', state='current')]),
                welcome=dict(id='welcome', data={'language': 'en_US.UTF-8'}),
                keyboard=dict(id='keyboard', data=copy.deepcopy(guest.KEYBOARD)),
                install=dict(id='install', data={}, options={'modules': []}))


def state():
    return dict(page='keyboard', current='keyboard', keyboard='il', view='step', connected=True,
                ready=True, valid=True, busy=False, failure='', error='', fields={},
                window=dict(visible=True, backing_visible=True, width=1280, height=720,
                            screen='Virtual-1', background='#202428'))


def output(name='Virtual-1', enabled=True):
    return dict(name=name, enabled=enabled, transform='normal', scale=1,
                modes=[dict(current=True, width=1280, height=720)])


def layers(name='Virtual-1'):
    return [dict(name='arctic-installer', layer='top', monitor=name)]


class FakeSocket:
    def __init__(self, data=None, uid=0, pid=1):
        self.data = data if data is not None else b'{"id":1,"result":{"ok":true}}\n'
        self.uid, self.pid = uid, pid
        self.sent, self.closed, self.connected = [], False, None
    def settimeout(self, timeout):
        self.timeout = timeout
    def connect(self, path):
        self.connected = path
    def getsockopt(self, *args):
        return struct.pack('3i', self.pid, self.uid, 0)
    def sendall(self, data):
        self.sent.append(data)
    def recv(self, bound):
        data, self.data = self.data[:bound], self.data[bound:]
        return data
    def close(self):
        self.closed = True


class Controls(unittest.TestCase):
    def test_context_exact_source_image_and_size(self):
        self.assertEqual(guest.validate_context(context()), context())
        changes = [('iso_bytes', True), ('iso_bytes', 2_000_000_000), ('source_sha', 'z' * 40),
                   ('token', 'a' * 64), ('checker_sha256', 'a' * 40), ('extra', 'unsupported')]
        for key, value in changes:
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                changed = context()
                changed[key] = value
                guest.validate_context(changed)

    def test_strict_json_rejects_duplicates_and_nonfinite_numbers(self):
        for text in ('{"id":1,"id":1}', '{"width":NaN}', '{"scale":Infinity}'):
            with self.subTest(text=text), self.assertRaises(RuntimeError):
                guest.strict_json(text)

    def test_socket_activation_root_peer_pid_one_is_valid(self):
        fake = FakeSocket(pid=1)
        rpc = guest.EngineRPC(factory=lambda *args: fake)
        self.assertEqual(fake.connected, '/run/arcticd.sock')
        self.assertEqual(rpc.peer['uid'], 0)
        self.assertIn('none', rpc.peer['pid_claim'])
        self.assertEqual(rpc.call('GetWizard'), {'ok': True})
        self.assertEqual(json.loads(fake.sent[0]), {'id': 1, 'method': 'GetWizard'})
        rpc.close()
        self.assertTrue(fake.closed)

    def test_nonroot_socket_peer_rejected(self):
        fake = FakeSocket(uid=1000)
        with self.assertRaises(RuntimeError):
            guest.EngineRPC(factory=lambda *args: fake)
        self.assertTrue(fake.closed)

    def test_rpc_blocks_install_mutations_disk_refresh_and_subscription_before_send(self):
        fake = FakeSocket()
        rpc = guest.EngineRPC(factory=lambda *args: fake)
        for method, params in (('Start', None), ('Next', None), ('SetStep', {'id': 'keyboard'}),
                               ('GetStep', {'id': 'disk'}), ('Subscribe', {}),
                               ('Hello', {'client': 'installer-ui'}), ('GetStep', {'id': 'keyboard', 'extra': 1})):
            with self.subTest(method=method), self.assertRaises(RuntimeError):
                rpc.call(method, params)
        self.assertEqual(fake.sent, [])

    def test_rpc_rejects_wrong_id_error_event_unbounded_and_extra_frames(self):
        for data in (b'{"id":2,"result":{}}\n', b'{"id":true,"result":{}}\n', b'{"id":1,"error":{"code":"state"}}\n',
                     b'{"event":"done"}\n', b'{"id":1,"result":{},"extra":true}\n',
                     b'{"id":1,"result":{}}\n{}\n', b'x' * (guest.MAX_FILE + 1)):
            with self.subTest(data=data[:80]), self.assertRaises((RuntimeError, ValueError)):
                rpc = guest.EngineRPC(factory=lambda *args: FakeSocket(data))
                rpc.call('GetWizard')

    def test_real_engine_snapshot_requires_hebrew_and_no_install_progress(self):
        baseline = engine()
        self.assertEqual(guest.validate_engine_snapshot(baseline, copy.deepcopy(baseline)), baseline)
        changes = [lambda v: v['hello'].update(mock=True),
                   lambda v: v['hello'].update(protocol_version=True),
                   lambda v: v['keyboard']['data'].update(layout='us'),
                   lambda v: v['keyboard']['data']['xkb'].update(layout='il'),
                   lambda v: v['wizard'].update(current='install'),
                   lambda v: v['install']['options'].update(progress={'percent': 1}),
                   lambda v: v['install']['options'].update(modules=[{'id': 'disk'}]),
                   lambda v: v['welcome']['data'].update(language='he_IL.UTF-8')]
        for mutate in changes:
            value = copy.deepcopy(baseline)
            mutate(value)
            with self.assertRaises(RuntimeError):
                guest.validate_engine_snapshot(value, baseline)

    def test_process_argv_and_environment_rejects_substitute_mock_override(self):
        guest.validate_gui_argv(['quickshell', '-p', guest.GUI_PATH])
        guest.validate_bridge_argv(['/usr/bin/arctic-install', 'bridge'])
        for argv in (['quickshell', '-p', '/tmp/installer'], ['quickshell', '-p', guest.GUI_PATH, '--no-color']):
            with self.assertRaises(RuntimeError):
                guest.validate_gui_argv(argv)
        for argv in (['arctic-install', 'bridge', '--mock'], ['arctic-install', 'bridge', '--socket', '/tmp/mock']):
            with self.assertRaises(RuntimeError):
                guest.validate_bridge_argv(argv)
        for env in (b'ARCTIC_INSTALLER_MOCK=1\0', b'ARCTIC_INSTALLER_BRIDGE=python3 fake\0',
                    b'ARCTIC_INSTALLER_SOCKET=/tmp/sock\0', b'ARCTIC_LIVE_KEYBOARD=true\0',
                    b'ARCTIC_MOCK_HW=test\0', b'A=1\0A=2\0'):
            with self.assertRaises(RuntimeError):
                guest.parse_environment(env)
        self.assertEqual(guest.parse_environment(b'A=1\0ARCTIC_INSTALLER_MOCK=\0')['A'], '1')

    def test_window_requires_actual_backing_visibility_unique_top_and_complete_output(self):
        baseline = state()
        outputs = [output(), output('Virtual-2')]
        self.assertEqual(guest.window_proof(baseline, layers(), outputs)['physical_size'], [1280, 720])
        for mutate in (lambda v: v['window'].update(backing_visible=False),
                       lambda v: v['window'].update(width=1270), lambda v: v.update(ready=False),
                       lambda v: v.update(keyboard='us'), lambda v: v.update(page='welcome')):
            changed = copy.deepcopy(baseline)
            mutate(changed)
            with self.assertRaises(RuntimeError):
                guest.window_proof(changed, layers(), outputs)
        for actual_layers in ([], layers() * 2, [dict(name='arctic-installer', layer='overlay', monitor='Virtual-1')]):
            with self.assertRaises(RuntimeError):
                guest.window_proof(baseline, actual_layers, outputs)

    def test_hosting_loss_requires_one_remaining_nonhosting_visible_output(self):
        moved = state()
        moved['window']['screen'] = 'Virtual-2'
        actual = [output(enabled=False), output('Virtual-2')]
        self.assertEqual(guest.window_proof(moved, layers('Virtual-2'), actual, 1)['window']['screen'], 'Virtual-2')
        with self.assertRaises(RuntimeError):
            guest.window_proof(state(), layers(), actual, 1)
        with self.assertRaises(RuntimeError):
            guest.window_proof(moved, layers('Virtual-2'), actual, 2)

    def test_fractional_geometry_and_physical_mode_are_independently_checked(self):
        actual = output()
        actual['scale'] = 1.5
        value = state()
        value['window'].update(width=1280 / 1.5, height=480)
        self.assertEqual(guest.window_proof(value, layers(), [actual, output('Virtual-2')])['physical_size'], [1280, 720])
        actual['scale'] = float('nan')
        with self.assertRaises(RuntimeError):
            guest.window_proof(value, layers(), [actual, output('Virtual-2')])

    def test_gui_next_is_not_permitted_from_summary_or_keyboard(self):
        worker = guest.Installer.__new__(guest.Installer)
        worker.gui_pid = 101
        worker.assert_gui_identity = lambda: None
        worker.command = lambda argv, **kwargs: (0, json.dumps(state()), '')
        with self.assertRaises(RuntimeError):
            worker.ipc('next')
        with self.assertRaises(RuntimeError):
            worker.ipc('Start')
        with self.assertRaises(RuntimeError):
            worker.ipc('fill', {'layout': 'us'})

    def test_vt_return_is_attempted_after_away_observer_failure(self):
        worker = guest.Installer.__new__(guest.Installer)
        worker.original_vt = 2
        worker.unchanged = lambda: {'engine': engine()}
        calls = []
        worker.command = lambda argv, **kwargs: calls.append(argv)
        worker.wait = lambda *args: (_ for _ in ()).throw(RuntimeError('inactive session not observed'))
        class Native:
            @staticmethod
            def execute(argv, **kwargs):
                calls.append(argv)
        worker.native = Native()
        with self.assertRaises(RuntimeError):
            worker.vt_cycle(0)
        self.assertEqual(calls, [['chvt', '6'], ['chvt', '2']])

    def test_restore_request_is_not_emitted_before_observed_loss(self):
        worker = guest.Installer.__new__(guest.Installer)
        worker.active_session = lambda _: None
        worker.unchanged = lambda: {'engine': engine()}
        worker.outputs = lambda: [output(), output('Virtual-2')]
        worker.ipc = lambda _: json.dumps(state())
        worker.command = lambda *args, **kwargs: (0, json.dumps({'layers': layers()}), '')
        worker.drm_heads = lambda: {'outputs': {'Virtual-1': {'head': 0}, 'Virtual-2': {'head': 1}}}
        requests = []
        worker.request = lambda kind, *args, **kwargs: requests.append(kind)
        worker.wait = lambda fn, *_: fn()  # Actual inventory remains connected: must fail, not request restore.
        with self.assertRaises(RuntimeError):
            worker.output_cycle(1)
        self.assertEqual(requests, ['output-disconnect'])

    def test_engine_log_counts_excludes_observer_hello_and_detects_reconnect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'engine.log'
            data = ('2026/10/09 arcticd: -> Hello {"client":"installer-ui","version":"1.2.1"}\n'
                    '2026/10/09 arcticd: -> Subscribe (session 1)\n'
                    '2026/10/09 arcticd: -> Hello {"client":"installer-restoration-qualification"}\n')
            path.write_text(data)
            with patch.object(guest, 'read_regular', lambda path, *args, **kwargs: Path(path).read_bytes()):
                counts = guest.engine_log_counts(path)
                self.assertEqual((counts['gui_hello_count'], counts['subscribe_count']), (1, 1))
                path.write_text(data + '2026/10/09 arcticd: -> Subscribe (session 3)\n')
                with self.assertRaises(RuntimeError):
                    guest.engine_log_counts(path)
            self.assertFalse(guest.engine_log_counts(Path(directory) / 'absent')['available'])

    def test_read_regular_rejects_symlink_oversize_and_unprotected_root_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'file'
            path.write_bytes(b'data')
            self.assertEqual(guest.read_regular(path, 4), b'data')
            with self.assertRaises(RuntimeError):
                guest.read_regular(path, 3)
            link = Path(directory) / 'link'
            link.symlink_to(path)
            with self.assertRaises(OSError):
                guest.read_regular(link)
            path.chmod(0o666)
            with self.assertRaises(RuntimeError):
                guest.read_regular(path, root_owned=True)

    def test_listener_inode_must_be_owned_by_serving_daemon_fd(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'net').mkdir()
            (root / '42/fd').mkdir(parents=True)
            path = Path('/run/arcticd.sock')
            (root / 'net/unix').write_text('Num RefCount Protocol Flags Type St Inode Path\n'
                'abcd: 00000002 00000000 00010000 0001 01 4321 /run/arcticd.sock\n')
            link = root / '42/fd/3'
            link.symlink_to('socket:[4321]')
            info = types.SimpleNamespace(st_mode=stat.S_IFSOCK | 0o660, st_uid=0, st_dev=9, st_ino=10)
            with patch.object(Path, 'lstat', return_value=info):
                value = guest.listener_proof(42, root, path)
                self.assertEqual(value['stream_inode'], 4321)
                self.assertEqual(value['listening_fds'], [3])
                link.unlink()
                link.symlink_to('socket:[4322]')
                with self.assertRaises(RuntimeError):
                    guest.listener_proof(42, root, path)

    def test_capture_checks_real_image_dimensions_and_background_pixels(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow unavailable: actual image pixel control cannot run')
        with tempfile.TemporaryDirectory(prefix='arctic-native-smoke-installer-', dir='/tmp') as directory:
            worker = guest.Installer.__new__(guest.Installer)
            worker.root, worker.uid, worker.capture_count = Path(directory), os.getuid(), 0
            visible = guest.window_proof(state(), layers(), [output(), output('Virtual-2')])
            color = [32, 36, 40]
            def command(argv, **kwargs):
                Image.new('RGB', (1280, 720), tuple(color)).save(argv[-1], format='PPM')
                return 0, '', ''
            worker.command = command
            value = worker.capture('baseline', visible)
            self.assertEqual(value['background'], color)
            self.assertEqual(value['size'], [1280, 720])
            self.assertEqual(worker.capture_count, 1)
            color[:] = [0, 0, 0]
            with self.assertRaises(RuntimeError):
                worker.capture('vt-0', visible)
            self.assertFalse((worker.root / 'physical-capture.ppm').exists())

    def test_cleanup_failure_still_serializes_failed_report_and_closes_pidfd(self):
        worker = guest.Installer.__new__(guest.Installer)
        worker.context, worker.boot_id, worker.uid, worker.session = context(), 'test-boot', os.getuid(), '1'
        worker.original_vt, worker.results, worker.capture_count = 2, [], 0
        worker.rpc, worker.gui_fd = types.SimpleNamespace(close=lambda: None), 12345
        class Security:
            def finish(self):
                return {'selinux': 'Enforcing'}
        worker.native = types.SimpleNamespace(SecurityInterval=Security)
        worker.prepare = lambda: (_ for _ in ()).throw(RuntimeError('prepared GUI absent'))
        worker.cleanup = lambda: dict(errors=['VT return failed'], original_vt_restored=False)
        with tempfile.TemporaryDirectory(prefix='arctic-native-smoke-installer-', dir='/tmp') as directory:
            worker.root = Path(directory)
            with patch.object(os, 'close', side_effect=OSError('pidfd close failed')):
                report = worker.run()
            self.assertEqual(report['status'], 'failed')
            self.assertTrue(any('pidfd close' in e for e in report['errors']))
            self.assertEqual(json.loads((worker.root / 'installer-report.json').read_text())['status'], 'failed')

    def test_export_preserves_failure_report_and_hashes_without_private_extra_files(self):
        with tempfile.TemporaryDirectory(prefix='arctic-native-smoke-installer-', dir='/tmp') as directory:
            root = Path(directory)
            report = {'schema': guest.SCHEMA, 'status': 'failed', 'errors': ['test-only failure']}
            (root / 'installer-report.json').write_text(json.dumps(report))
            (root / 'baseline.png').write_bytes(b'bounded-public-fixture')
            class Transport:
                read_regular = staticmethod(guest.read_regular)
            stream = io.StringIO()
            guest.export(root, os.getuid(), 'a' * 32, Transport(), stream)
            records = [line.split(' ', 1) for line in stream.getvalue().splitlines()]
            manifest = json.loads(records[-1][1])
            self.assertEqual(manifest['schema'], 'arctic-installer-evidence-v1')
            self.assertEqual({v['path'] for v in manifest['files']}, {'installer-report.json', 'baseline.png'})
            self.assertTrue(all(v['encoding'] == 'zlib+base64' for v in manifest['files']))
            (root / 'private.txt').write_text('not authorized evidence')
            with self.assertRaises(RuntimeError):
                guest.inventory(root, os.getuid(), Transport())


if __name__ == '__main__':
    unittest.main()
