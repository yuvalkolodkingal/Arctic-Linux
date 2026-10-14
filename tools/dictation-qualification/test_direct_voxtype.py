"""Source controls for the direct official VoxType qualification client."""
import ast
import grp
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
            binds.write_text('bindr=SUPER+CTRL,x,spawn,voxtype record toggle\n'
                             'bindr=SUPER+CTRL,BackSpace,spawn,voxtype record cancel\n')
            with patch.object(guest, 'SKEL_BINDINGS', binds):
                self.assertEqual(checker.command_contract(), {'command_count': 4})
            binds.write_text('bindr=SUPER+CTRL,x,spawn,arctic-dictation toggle\n')
            with patch.object(guest, 'SKEL_BINDINGS', binds), \
                    self.assertRaisesRegex(guest.Invalid, '^mango-not-bound-directly-to-upstream$'):
                checker.command_contract()

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
                    'packaging/dictation/arctic-dictation', 'packaging/dictation/voxtype',
                    'packaging/dictation/arctic-voxtype-setup',
                    'packaging/dictation/voxtype-release-key.asc',
                    'packaging/dictation/org.arcticlinux.dictation.policy',
                    'packaging/systemd/voxtype.service',
                    'packaging/systemd/arctic-dictation-setup.service',
                    'packaging/systemd/arctic-dictation-setup.timer')):
                path = root / str(index)
                path.write_text(str(index))
                path.chmod(0o600)
                paths.append(path)
            with patch.object(guest, 'owned_file', side_effect=lambda path, size=None: Path(path).stat()), \
                    patch.object(guest, 'ADAPTER', paths[0]), patch.object(guest, 'VOXTYPE', paths[1]), \
                    patch.object(guest, 'SETUP', paths[2]), patch.object(guest, 'KEY', paths[3]), \
                    patch.object(guest, 'POLICY', paths[4]), patch.object(guest, 'UNIT', paths[5]), \
                    patch.object(guest, 'SETUP_SERVICE', paths[6]), \
                    patch.object(guest, 'SETUP_TIMER', paths[7]):
                first = guest.installed_integration_sha()
                paths[1].write_text('changed')
                self.assertNotEqual(first, guest.installed_integration_sha())

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


if __name__ == '__main__':
    unittest.main()
