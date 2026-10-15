"""Source controls for the direct official VoxType qualification client."""
import ast
import grp
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location('direct_voxtype_guest', HERE / 'guest_check.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class DirectVoxtypeControls(unittest.TestCase):
    def checker(self):
        value = guest.Checker.__new__(guest.Checker)
        value.prefix = []
        value.account = SimpleNamespace(pw_uid=os.getuid(), pw_gid=os.getgid(),
                                        pw_name='arctic-test', pw_dir='/tmp/arctic-test')
        value.runtime = Path('/tmp')
        value.snapshots = []
        return value

    def test_record_calls_only_official_cli_and_closed_verbs(self):
        checker = self.checker()
        checker.cmd = Mock(return_value=SimpleNamespace(stdout=b'', stderr=b'', returncode=0))
        for action in ('start', 'stop', 'toggle', 'cancel'):
            checker.record(action)
            checker.cmd.assert_called_with(['/usr/bin/voxtype', 'record', action], check=True)
        with self.assertRaisesRegex(guest.Invalid, '^unknown-upstream-record-command$'):
            checker.record('status')

    def test_adapter_is_never_used_for_recording_in_session_methods(self):
        tree = ast.parse((HERE / 'guest_check.py').read_text())
        checker = next(node for node in tree.body
                       if isinstance(node, ast.ClassDef) and node.name == 'Checker')
        calls = []
        for node in ast.walk(checker):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == 'self' and node.func.attr == 'adapter'
                    and node.args and isinstance(node.args[0], ast.Constant)):
                calls.append(node.args[0].value)
        self.assertFalse({'start', 'stop', 'toggle', 'cancel'} & set(calls))

    def test_native_state_file_is_private_and_closed_enum(self):
        checker = self.checker()
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'state'
            checker.state_path = path
            for state in ('idle', 'recording', 'transcribing', 'streaming'):
                path.write_text(state + '\n')
                path.chmod(0o600)
                self.assertEqual(checker.state(), state)
            path.write_text('ready\n')
            with self.assertRaisesRegex(guest.Invalid, '^upstream-state-invalid$'):
                checker.state()
            path.write_text('idle\n')
            path.chmod(0o644)
            with self.assertRaisesRegex(guest.Invalid, '^upstream-state-file-unsafe$'):
                checker.state()

    def test_local_he_en_config_disables_evdev_remote_and_transcript_notification(self):
        checker = self.checker()
        checker.names = {'model': 'ggml-small.bin'}
        with tempfile.TemporaryDirectory() as temp:
            checker.config_path = Path(temp) / 'config.toml'
            checker.config_path.write_text('''
engine = "whisper"
state_file = "auto"
[hotkey]
enabled = false
[whisper]
mode = "local"
model = "/opt/arctic/voxtype/models/ggml-small.bin"
language = ["he", "en"]
[output]
mode = "type"
driver_order = ["wtype"]
fallback_to_clipboard = false
[output.notification]
on_transcription = false
''')
            checker.config_path.chmod(0o600)
            self.assertEqual(checker.config_contract(), {'language_count': 2})
            for needle in ('mode = "remote"', 'enabled = true',
                           'language = ["he", "fr"]', 'on_transcription = true'):
                body = checker.config_path.read_text()
                if needle.startswith('mode = "remote"'):
                    body = body.replace('mode = "local"', needle)
                elif needle.startswith('enabled'):
                    body = body.replace('enabled = false', needle)
                elif needle.startswith('language'):
                    body = body.replace('language = ["he", "en"]', needle)
                else:
                    body = body.replace('on_transcription = false', needle)
                checker.config_path.write_text(body)
                with self.assertRaisesRegex(guest.Invalid, '^voxtype-local-he-en-config$'):
                    checker.config_contract()
                checker.config_path.write_text('''
engine = "whisper"
state_file = "auto"
[hotkey]
enabled = false
[whisper]
mode = "local"
model = "/opt/arctic/voxtype/models/ggml-small.bin"
language = ["he", "en"]
[output]
mode = "type"
driver_order = ["wtype"]
fallback_to_clipboard = false
[output.notification]
on_transcription = false
''')

    def test_no_input_group_requires_actual_supplementary_membership_absence(self):
        checker = self.checker()
        with patch.object(guest.os, 'getgrouplist', return_value=[1000]), \
                patch.object(guest.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=18)):
            self.assertEqual(checker.no_input(), {'input_group_membership': 0})
        with patch.object(guest.os, 'getgrouplist', return_value=[18, 1000]), \
                patch.object(guest.grp, 'getgrnam', return_value=SimpleNamespace(gr_gid=18)):
            with self.assertRaisesRegex(guest.Invalid, '^desktop-user-has-input-group$'):
                checker.no_input()

    def test_microphone_disconnect_waits_for_projection_and_restores_clean_daemon(self):
        checker = self.checker()
        checker.empty = Mock()
        checker.select = Mock()
        checker.record = Mock(return_value=SimpleNamespace(returncode=0))
        checker.capture_link = Mock(return_value=True)
        checker.destroy_route = Mock()
        checker.route = Mock()
        checker.state = Mock(side_effect=['recording', 'idle', 'idle'])
        checker.engines = Mock(return_value=[(123, 456, Path('/usr/bin/voxtype'))])
        checker.adapter = Mock(side_effect=[
            {'state': 'ready', 'error': ''},
            {'state': 'error', 'error': 'VoxType could not open the microphone.'},
        ])
        observed = []
        def observe(target, fn, _seconds=20):
            observed.append(target)
            value = fn()
            if not value:
                value = fn()
            if not value:
                raise guest.Invalid('observation-timeout')
            return value
        checker.observe = Mock(side_effect=observe)
        with tempfile.TemporaryDirectory() as temp:
            checker.root = Path(temp)
            (checker.root / 'received.private').write_bytes(b'')
            def command(argv, check=True):
                if argv == ['/usr/bin/pw-dump']:
                    output = b'[]'
                elif argv == ['systemctl', '--user', 'is-active', 'voxtype.service']:
                    output = b'active\n'
                else:
                    output = b''
                return SimpleNamespace(stdout=output, stderr=b'', returncode=0)
            checker.cmd = Mock(side_effect=command)
            self.assertEqual(checker.microphone(),
                             {'count': 0, 'drained': True, 'restored': True})
        self.assertIn('microphone-actionable-error', observed)
        self.assertIn('microphone-daemon-restored', observed)
        self.assertEqual(checker.adapter.call_count, 2)
        checker.destroy_route.assert_called_once_with(restore=False)
        checker.route.assert_called_once_with()
        restart = ['systemctl', '--user', 'restart', 'voxtype.service']
        self.assertTrue(any(call.args == (restart,) for call in checker.cmd.call_args_list))

    def test_microphone_failed_assertion_still_restores_independent_gate_state(self):
        checker = self.checker()
        checker.empty = Mock()
        checker.select = Mock()
        checker.record = Mock(return_value=SimpleNamespace(returncode=0))
        checker.capture_link = Mock(return_value=True)
        checker.destroy_route = Mock()
        checker.route = Mock()
        checker.state = Mock(side_effect=['recording', 'idle', 'idle'])
        checker.engines = Mock(return_value=[(123, 456, Path('/usr/bin/voxtype'))])
        checker.adapter = Mock(return_value={'state': 'ready', 'error': ''})
        def observe(target, fn, _seconds=20):
            value = fn()
            if target == 'microphone-actionable-error':
                raise guest.Invalid('observation-timeout')
            if not value:
                raise guest.Invalid('observation-timeout')
            return value
        checker.observe = Mock(side_effect=observe)
        with tempfile.TemporaryDirectory() as temp:
            checker.root = Path(temp)
            (checker.root / 'received.private').write_bytes(b'')
            checker.cmd = Mock(side_effect=lambda argv, check=True: SimpleNamespace(
                stdout=(b'[]' if argv == ['/usr/bin/pw-dump'] else
                        b'active\n' if argv == ['systemctl', '--user', 'is-active',
                                                'voxtype.service'] else b''),
                stderr=b'', returncode=0))
            with self.assertRaisesRegex(guest.Invalid, '^observation-timeout$'):
                checker.microphone()
        checker.route.assert_called_once_with()
        restart = ['systemctl', '--user', 'restart', 'voxtype.service']
        self.assertTrue(any(call.args == (restart,) for call in checker.cmd.call_args_list))

    def test_failed_lock_assertion_unlocks_and_restores_service_for_later_gates(self):
        checker = self.checker()
        checker.empty = Mock()
        checker.select = Mock()
        checker.record = Mock(return_value=SimpleNamespace(returncode=0))
        checker.capture_link = Mock(return_value=True)
        checker.play = Mock()
        checker.kill = Mock()
        checker.player = None
        checker.fixtures = [{}]
        checker.state = Mock(side_effect=['recording', 'stopped', 'idle'])
        checker.engines = Mock(side_effect=[[], [(123, 456, Path('/usr/bin/voxtype'))]])
        lock_states = iter((b'true\n', b'false\n'))
        service_states = iter((b'inactive\n', b'active\n'))
        def command(argv, check=True):
            if argv == ['/usr/bin/arctic-shell-ipc', 'lock', 'isLocked']:
                output = next(lock_states)
            elif argv == ['systemctl', '--user', 'is-active', 'voxtype.service']:
                output = next(service_states)
            else:
                output = b''
            return SimpleNamespace(stdout=output, stderr=b'', returncode=0)
        checker.cmd = Mock(side_effect=command)
        def observe(_target, fn, _seconds=20):
            value = fn()
            if not value:
                raise guest.Invalid('observation-timeout')
            return value
        checker.observe = Mock(side_effect=observe)
        with tempfile.TemporaryDirectory() as temp, patch('builtins.print') as output:
            checker.root = Path(temp)
            (checker.root / 'received.private').write_bytes(b'unexpected')
            with self.assertRaisesRegex(guest.Invalid, '^lock-inserted-text$'):
                checker.locked()
        output.assert_called_once_with('ARCTIC-DESKTOP-UNLOCK-REQUESTED', flush=True)
        start = ['systemctl', '--user', 'start', 'voxtype.service']
        self.assertTrue(any(call.args == (start,) and call.kwargs == {'check': False}
                            for call in checker.cmd.call_args_list))
        self.assertEqual(checker.state.call_count, 3)
        self.assertEqual(checker.engines.call_count, 2)

    def test_gpu_error_projection_is_bounded_observation_before_cpu_recovery(self):
        tree = ast.parse((HERE / 'guest_check.py').read_text())
        checker = next(node for node in tree.body
                       if isinstance(node, ast.ClassDef) and node.name == 'Checker')
        method = next(node for node in checker.body
                      if isinstance(node, ast.FunctionDef) and node.name == 'gpu_failure')
        calls = [node for node in ast.walk(method) if isinstance(node, ast.Call)
                 and isinstance(node.func, ast.Attribute)
                 and isinstance(node.func.value, ast.Name)
                 and node.func.value.id == 'self' and node.func.attr == 'observe']
        targets = [call.args[0].value for call in calls if call.args
                   and isinstance(call.args[0], ast.Constant)]
        self.assertIn('gpu-failure-actionable-error', targets)
        source = ast.get_source_segment((HERE / 'guest_check.py').read_text(), method)
        self.assertLess(source.index("gpu-failure-actionable-error"),
                        source.index("self.select(backend='cpu')"))

    def test_command_contract_requires_direct_mango_binds_and_rejecting_adapter(self):
        checker = self.checker()
        def command(argv, check=True):
            if argv == ['/usr/bin/voxtype', 'record', '--help']:
                return SimpleNamespace(stdout=b'Commands:\n  start x\n  stop x\n  toggle x\n  cancel x\n',
                                       stderr=b'', returncode=0)
            if argv[:1] == ['/usr/bin/arctic-dictation']:
                return SimpleNamespace(stdout=b'', stderr=b'', returncode=2)
            raise AssertionError(argv)
        checker.cmd = Mock(side_effect=command)
        checker.record = Mock(return_value=SimpleNamespace(returncode=0))
        with tempfile.TemporaryDirectory() as temp:
            binds = Path(temp) / 'binds.conf'
            guard = Path(temp) / 'arctic-dictation-toggle'
            guard.write_text('voxtype record toggle >/dev/null 2>&1\n')
            checker.user_bindings = binds
            binds.write_text('bindr=SUPER+CTRL,x,spawn,arctic-dictation-toggle\n'
                             'bindr=SUPER+CTRL,BackSpace,spawn,voxtype record cancel\n')
            with patch.object(guest, 'SKEL_BINDINGS', binds), patch.object(guest, 'TOGGLE', guard), \
                    patch.object(guest, 'owned_text', side_effect=lambda path, _uid, _code: Path(path).read_text()), \
                    patch.object(guest, 'owned_binding_link', side_effect=lambda path, _uid, _code: Path(path).read_text()):
                self.assertEqual(checker.command_contract(), {'command_count': 4})
            binds.write_text('bindr=SUPER+CTRL,x,spawn,arctic-dictation toggle\n')
            with patch.object(guest, 'SKEL_BINDINGS', binds), patch.object(guest, 'TOGGLE', guard), \
                    patch.object(guest, 'owned_text', side_effect=lambda path, _uid, _code: Path(path).read_text()), \
                    patch.object(guest, 'owned_binding_link', side_effect=lambda path, _uid, _code: Path(path).read_text()), \
                    self.assertRaisesRegex(guest.Invalid, '^mango-not-bound-directly-to-upstream$'):
                checker.command_contract()

    def test_command_contract_requires_both_skel_and_active_user_bindings(self):
        checker = self.checker()
        checker.cmd = Mock(side_effect=lambda argv, check=True: SimpleNamespace(
            stdout=(b'  start x\n  stop x\n  toggle x\n  cancel x\n'
                    if argv == ['/usr/bin/voxtype', 'record', '--help'] else b''),
            stderr=b'', returncode=2 if argv[:1] == ['/usr/bin/arctic-dictation'] else 0))
        checker.record = Mock()
        valid = 'spawn,arctic-dictation-toggle\nspawn,voxtype record cancel\n'
        with tempfile.TemporaryDirectory() as temp:
            skel, active, guard = Path(temp) / 'skel', Path(temp) / 'active', Path(temp) / 'guard'
            skel.write_text(valid); active.write_text(valid)
            guard.write_text('voxtype record toggle >/dev/null 2>&1\n')
            skel.chmod(0o600); active.chmod(0o600)
            checker.user_bindings = active
            with patch.object(guest, 'SKEL_BINDINGS', skel), patch.object(guest, 'TOGGLE', guard), \
                    patch.object(guest, 'owned_text', side_effect=lambda path, _uid, _code: Path(path).read_text()), \
                    patch.object(guest, 'owned_binding_link', side_effect=lambda path, _uid, _code: Path(path).read_text()):
                self.assertEqual(checker.command_contract(), {'command_count': 4})
                active.write_text('spawn,arctic-dictation-toggle\n')
                with self.assertRaisesRegex(guest.Invalid, '^mango-not-bound-directly-to-upstream$'):
                    checker.command_contract()
                active.write_text(valid); skel.write_text('spawn,voxtype record cancel\n')
                with self.assertRaisesRegex(guest.Invalid, '^mango-not-bound-directly-to-upstream$'):
                    checker.command_contract()

    def test_owned_binding_reader_rejects_writable_and_non_utf8_files(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'binds.conf'
            path.write_text('spawn,voxtype record toggle\n')
            path.chmod(0o600)
            self.assertEqual(guest.owned_text(path, os.getuid(), 'unsafe'), path.read_text())
            path.chmod(0o622)
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest.owned_text(path, os.getuid(), 'unsafe')
            path.chmod(0o600); path.write_bytes(b'\xff')
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest.owned_text(path, os.getuid(), 'unsafe')

    def test_owned_binding_link_accepts_only_exact_absolute_packaged_target(self):
        uid = os.getuid()
        valid = 'spawn,arctic-dictation-toggle\nspawn,voxtype record cancel\n'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / 'config'
            parent.mkdir(mode=0o700)
            target = root / 'packaged-binds.conf'
            target.write_text(valid)
            target.chmod(0o600)
            link = parent / 'binds.conf'
            link.symlink_to(target)
            self.assertEqual(
                guest._owned_binding_link(link, uid, target, uid, 'unsafe'), valid)

            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid + 1, target, uid, 'unsafe')
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, root / 'other', uid, 'unsafe')

            link.unlink()
            link.symlink_to('../packaged-binds.conf')
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid, 'unsafe')

            link.unlink()
            link.write_text(valid)
            link.chmod(0o600)
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid, 'unsafe')

    def test_owned_binding_link_pins_root_owned_packaged_path(self):
        path = Path('/home/arctic/.config/mango/arctic/binds.conf')
        with patch.object(guest, '_owned_binding_link', return_value='binds') as reader:
            self.assertEqual(guest.owned_binding_link(path, 1000, 'unsafe'), 'binds')
        reader.assert_called_once_with(path, 1000, guest.PACKAGED_BINDINGS, 0, 'unsafe')

    def test_owned_binding_link_rejects_chained_writable_missing_and_unsafe_parent(self):
        uid = os.getuid()
        valid = 'spawn,arctic-dictation-toggle\nspawn,voxtype record cancel\n'
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            parent = root / 'config'
            parent.mkdir(mode=0o700)
            target = root / 'packaged-binds.conf'
            final = root / 'final-binds.conf'
            final.write_text(valid)
            final.chmod(0o600)
            target.symlink_to(final)
            link = parent / 'binds.conf'
            link.symlink_to(target)
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid, 'unsafe')

            target.unlink()
            target.write_text(valid)
            target.chmod(0o622)
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid, 'unsafe')

            target.unlink()
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid, 'unsafe')

            target.write_text(valid)
            target.chmod(0o600)
            parent.chmod(0o770)
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid, 'unsafe')
            parent.chmod(0o700)
            with self.assertRaisesRegex(guest.Invalid, '^unsafe$'):
                guest._owned_binding_link(link, uid, target, uid + 1, 'unsafe')

    def test_journal_decoder_retains_full_strings_and_rejects_truncation(self):
        raw = (json.dumps({'MESSAGE': 'English private fixture'}) + '\n'
               + json.dumps({'MESSAGE': 'עברית פרטית'}) + '\n').encode()
        self.assertEqual(guest.journal_messages(raw), 'English private fixture\nעברית פרטית')
        with self.assertRaises(guest.Invalid):
            guest.journal_messages(raw[:-4])

    def test_integration_hash_binds_adapter_selector_setup_key_and_unit(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = []
            for index, _name in enumerate((
                    'packaging/dictation/arctic-dictation',
                    'packaging/dictation/arctic-dictation-toggle',
                    'packaging/dictation/voxtype',
                    'packaging/dictation/arctic-voxtype-setup',
                    'packaging/dictation/arctic-voxtype-host-profile',
                    'packaging/dictation/arctic-voxtype-configure',
                    'packaging/dictation/voxtype-release-key.asc',
                    'packaging/dictation/provenance/v1.1.0/SHA256SUMS.txt',
                    'packaging/dictation/provenance/v1.1.0/SHA256SUMS.txt.asc',
                    'packaging/dictation/provenance/v1.1.0/voxtype-1.1.0-linux-x86_64-baseline.asc',
                    'packaging/dictation/provenance/v1.1.0/voxtype-1.1.0-linux-x86_64-avx2.asc',
                    'packaging/dictation/org.arcticlinux.dictation.policy',
                    'packaging/systemd/voxtype.service',
                    'packaging/systemd/arctic-dictation-setup.service',
                    'packaging/systemd/arctic-dictation-setup.timer')):
                path = root / str(index)
                if index < 6:
                    shell = 'bash' if index == 3 else 'sh'
                    path.write_text('#!/usr/bin/' + shell + '\n' + str(index))
                else:
                    path.write_text(str(index))
                path.chmod(0o600)
                paths.append(path)
            with patch.object(guest, 'owned_file', side_effect=lambda path, size=None: Path(path).stat()), \
                    patch.object(guest, 'ADAPTER', paths[0]), patch.object(guest, 'TOGGLE', paths[1]), \
                    patch.object(guest, 'VOXTYPE', paths[2]), \
                    patch.object(guest, 'SETUP', paths[3]), \
                    patch.object(guest, 'HOST_PROFILE', paths[4]), \
                    patch.object(guest, 'CONFIGURE', paths[5]), \
                    patch.object(guest, 'KEY', paths[6]), \
                    patch.object(guest, 'PROVENANCE_SUMS', paths[7]), \
                    patch.object(guest, 'PROVENANCE_SUMS_SIG', paths[8]), \
                    patch.object(guest, 'PROVENANCE_BASELINE_SIG', paths[9]), \
                    patch.object(guest, 'PROVENANCE_AVX2_SIG', paths[10]), \
                    patch.object(guest, 'POLICY', paths[11]), patch.object(guest, 'UNIT', paths[12]), \
                    patch.object(guest, 'SETUP_SERVICE', paths[13]), \
                    patch.object(guest, 'SETUP_TIMER', paths[14]):
                first = guest.installed_integration_sha()
                paths[1].write_text('#!/usr/bin/sh\nchanged')
                self.assertNotEqual(first, guest.installed_integration_sha())

    def test_installed_integration_hash_reverses_only_rpm_shebang_mangling(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paths = []
            shells = ('sh', 'sh', 'sh', 'bash', 'sh', 'sh')
            source_hash = hashlib.sha256()
            for index, (name, shell) in enumerate(zip((
                    'packaging/dictation/arctic-dictation',
                    'packaging/dictation/arctic-dictation-toggle',
                    'packaging/dictation/voxtype',
                    'packaging/dictation/arctic-voxtype-setup',
                    'packaging/dictation/arctic-voxtype-host-profile',
                    'packaging/dictation/arctic-voxtype-configure'), shells)):
                path = root / str(index)
                source = ('#!/bin/' + shell + '\npayload-' + str(index) + '\n').encode()
                installed = source.replace(b'#!/bin/', b'#!/usr/bin/', 1)
                path.write_bytes(installed); path.chmod(0o600); paths.append(path)
                encoded = name.encode()
                source_hash.update(len(encoded).to_bytes(4, 'big'))
                source_hash.update(encoded); source_hash.update(source)
            remaining = (
                'packaging/dictation/voxtype-release-key.asc',
                'packaging/dictation/provenance/v1.1.0/SHA256SUMS.txt',
                'packaging/dictation/provenance/v1.1.0/SHA256SUMS.txt.asc',
                'packaging/dictation/provenance/v1.1.0/voxtype-1.1.0-linux-x86_64-baseline.asc',
                'packaging/dictation/provenance/v1.1.0/voxtype-1.1.0-linux-x86_64-avx2.asc',
                'packaging/dictation/org.arcticlinux.dictation.policy',
                'packaging/systemd/voxtype.service',
                'packaging/systemd/arctic-dictation-setup.service',
                'packaging/systemd/arctic-dictation-setup.timer')
            for index, name in enumerate(remaining, start=6):
                path = root / str(index); content = ('payload-' + str(index)).encode()
                path.write_bytes(content); path.chmod(0o600); paths.append(path)
                encoded = name.encode()
                source_hash.update(len(encoded).to_bytes(4, 'big'))
                source_hash.update(encoded); source_hash.update(content)
            patches = dict(ADAPTER=paths[0], TOGGLE=paths[1], VOXTYPE=paths[2],
                           SETUP=paths[3], HOST_PROFILE=paths[4], CONFIGURE=paths[5],
                           KEY=paths[6], PROVENANCE_SUMS=paths[7],
                           PROVENANCE_SUMS_SIG=paths[8], PROVENANCE_BASELINE_SIG=paths[9],
                           PROVENANCE_AVX2_SIG=paths[10], POLICY=paths[11], UNIT=paths[12],
                           SETUP_SERVICE=paths[13], SETUP_TIMER=paths[14])
            with patch.object(guest, 'owned_file', side_effect=lambda path, size=None: Path(path).stat()), \
                    patch.multiple(guest, **patches):
                self.assertEqual(guest.installed_integration_sha(), source_hash.hexdigest())
                paths[0].write_bytes(b'#!/bin/sh\npayload-0\n')
                with self.assertRaisesRegex(guest.Invalid, 'installed-integration-shebang-mismatch'):
                    guest.installed_integration_sha()

    def test_status_adapter_has_exact_bounded_public_contract(self):
        checker = self.checker()
        checker.snapshots = []
        value = {
            'state': 'ready', 'ready': True, 'error': '', 'version': '1.1.0',
            'language': 'auto', 'backend': 'cpu', 'profile': 'small-v2',
            'model': 'small', 'model_download_bytes': 487601967,
            'download_bytes': 506181191, 'vulkan_download_bytes': 66342968,
        }
        checker.cmd = Mock(return_value=SimpleNamespace(
            stdout=(json.dumps(value) + '\n').encode(), stderr=b'', returncode=0))
        self.assertEqual(checker.adapter('status'), value)
        value['private'] = 'transcript'
        checker.cmd = Mock(return_value=SimpleNamespace(
            stdout=(json.dumps(value) + '\n').encode(), stderr=b'', returncode=0))
        with self.assertRaisesRegex(guest.Invalid, '^adapter-status-contract$'):
            checker.adapter('status')

    def test_payload_binds_split_paths_and_flat_receipt(self):
        checker = self.checker()
        checker.profile_id = 'small-v2'
        checker.assets = guest.PROFILE_ASSETS['small-v2']
        checker.report = {}
        binary = checker.assets['cpu']
        model = checker.assets['model']
        receipt = {
            'integration': 'upstream-direct-v1', 'version': '1.1.0',
            'source_commit': guest.UPSTREAM['source_commit'],
            'release_signing_fingerprint': guest.UPSTREAM['signed_sums_fingerprint'],
            'user': checker.account.pw_name, 'profile': 'small-v2',
            'binary': binary['name'], 'binary_bytes': binary['bytes'],
            'binary_sha256': binary['sha256'],
            'model_path': '/opt/arctic/voxtype/models/' + model['name'],
            'model': 'small.bin', 'model_bytes': model['bytes'],
            'model_sha256': model['sha256'], 'backend': 'cpu',
        }
        def installed_hash(path):
            return model['sha256'] if Path(path).parent == guest.MODELS else binary['sha256']
        with patch.object(guest, 'read', return_value=receipt), \
                patch.object(guest, 'owned_file', return_value=SimpleNamespace(st_mode=0o100755)), \
                patch.object(guest, 'sha', side_effect=installed_hash):
            self.assertEqual(checker.payload(), {'file_count': 2})
        changed = dict(receipt, model_path='/opt/arctic/voxtype/1.1.0/' + model['name'])
        with patch.object(guest, 'read', return_value=changed), \
                patch.object(guest, 'owned_file', return_value=SimpleNamespace(st_mode=0o100755)), \
                patch.object(guest, 'sha', side_effect=installed_hash), \
                self.assertRaisesRegex(guest.Invalid, '^receipt-selected-assets-pin$'):
            checker.payload()

    def test_recovery_uses_root_service_only_when_pending(self):
        checker = self.checker()
        enabled = SimpleNamespace(stdout=b'enabled\n', stderr=b'', returncode=0)
        ready = {'ready': True}
        with tempfile.TemporaryDirectory() as temp, patch.object(guest, 'SYSTEM', Path(temp)), \
                patch.object(guest, 'run', return_value=enabled) as command:
            checker.adapter = Mock(return_value=ready)
            self.assertEqual(checker.recovery(),
                             {'ready': True, 'pending': False, 'automatic_ready': True})
            self.assertFalse(any(call.args[0][:2] == ['systemctl', 'start']
                                 for call in command.call_args_list))
        with tempfile.TemporaryDirectory() as temp, patch.object(guest, 'SYSTEM', Path(temp)), \
                patch.object(guest, 'run', return_value=enabled) as command:
            (Path(temp) / 'pending').write_text('1.1.0\n')
            def status(*_args, **_kwargs):
                if any(call.args[0][:2] == ['systemctl', 'start']
                       for call in command.call_args_list):
                    (Path(temp) / 'pending').unlink(missing_ok=True)
                    return ready
                return {'ready': False}
            checker.adapter = Mock(side_effect=status)
            self.assertEqual(checker.recovery(),
                             {'ready': True, 'pending': False, 'automatic_ready': False})
            command.assert_any_call(['systemctl', 'start', 'arctic-dictation-setup.service'], 750)


if __name__ == '__main__':
    unittest.main()
