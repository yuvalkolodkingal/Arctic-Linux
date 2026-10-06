"""Regression for the installed-VM probe's post-exec compositor environment."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('nix_guest', Path(__file__).parents[1]/'nix-acceptance/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class SessionEnvironmentTest(unittest.TestCase):
    def test_reads_child_signature_and_rejects_missing_or_ambiguous_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = Path('/run/user')/str(os.getuid())
            def child(pid, display, signature):
                folder = root/str(pid)
                folder.mkdir()
                (folder/'environ').write_bytes(('WAYLAND_DISPLAY='+display+'\0XDG_RUNTIME_DIR='+str(runtime)+'\0MANGO_INSTANCE_SIGNATURE='+signature+'\0').encode())
            with self.assertRaisesRegex(RuntimeError, 'found 0'):
                guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {})
            child(10, 'wayland-0', '/run/user/test/mango.sock')
            child(11, 'wayland-1', '/run/user/test/other.sock')
            self.assertEqual(guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {}), '/run/user/test/mango.sock')
            child(12, 'wayland-0', '/run/user/test/ambiguous.sock')
            with self.assertRaisesRegex(RuntimeError, 'found 2'):
                guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {})


class RpmSignatureTest(unittest.TestCase):
    def test_rpm6_lowercase_signature_is_accepted_for_every_file(self):
        files = ['/packages/arctic.rpm', '/packages/fedora.rpm']
        output = '\n'.join(filename + ':\n    Header OpenPGP V4 RSA/SHA256 signature, key fingerprint: abc: OK\n    Header SHA256 digest: OK\n    Payload SHA256 digest: OK' for filename in files)
        with patch.object(guest, 'run', return_value=output):
            self.assertEqual(guest.verified_rpm_signatures(files), output)

    def test_unsigned_or_missing_second_rpm_is_rejected_despite_digest_ok(self):
        files = ['/packages/arctic.rpm', '/packages/unsigned.rpm']
        good = files[0] + ':\n    Header OpenPGP V4 RSA/SHA256 signature: OK\n'
        for output in (good, good + files[1] + ':\n    Header SHA256 digest: OK\n    Payload SHA256 digest: OK'):
            with self.subTest(output=output), patch.object(guest, 'run', return_value=output):
                with self.assertRaisesRegex(RuntimeError, 'No valid signature'):
                    guest.verified_rpm_signatures(files)

    def test_untrusted_or_bad_signature_is_rejected(self):
        for result in ('NOKEY', 'BAD', 'NOT OK'):
            output = '/packages/arctic.rpm:\n    Header OpenPGP V4 RSA/SHA256 Signature: ' + result
            with self.subTest(result=result), patch.object(guest, 'run', return_value=output):
                with self.assertRaisesRegex(RuntimeError, 'No valid signature'):
                    guest.verified_rpm_signatures(['/packages/arctic.rpm'])


class OfflineHistoryTest(unittest.TestCase):
    def test_selects_latest_listed_positive_index(self):
        first = 'a' * 32
        latest = 'b' * 32
        listing = ('The following boots appear to contain offline transaction logs:\n'
                   f'1 / {first}: 2026-10-06 00:00:00 44→44\n'
                   f'2 / {latest}: 2026-10-06 02:00:00 44→44')
        with patch.object(guest, 'run', side_effect=[listing, 'actual journal']) as run:
            self.assertEqual(guest.latest_offline_history(),
                             dict(listing=listing, number=2, boot_id=latest, log='actual journal'))
        self.assertEqual(run.call_args_list[-1].args[0],
                         ['dnf5', 'offline', 'log', '--number=2'])

    def test_absent_history_is_rejected(self):
        with patch.object(guest, 'run', return_value='No logs were found.') as run:
            with self.assertRaisesRegex(RuntimeError, 'No listed offline transaction boot'):
                guest.latest_offline_history()
        self.assertEqual(run.call_count, 1)

    def test_latest_history_command_failure_is_retained(self):
        listing = '1 / ' + 'c' * 32 + ': 2026-10-06 02:00:00 44→44'
        with patch.object(guest, 'run', side_effect=[listing, RuntimeError('journal missing')]):
            with self.assertRaisesRegex(RuntimeError, 'journal missing'):
                guest.latest_offline_history()
