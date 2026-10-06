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


class NixSocketDefaultsTest(unittest.TestCase):
    def test_socket_must_be_enabled_and_active_with_eager_service_disabled(self):
        with patch.object(guest, 'run', side_effect=['enabled', 'disabled', 'active']) as run:
            self.assertIn('eager service disabled', guest.nix_socket_defaults())
        self.assertEqual(run.call_count, 3)
        for states in (['disabled', 'disabled'], ['enabled', 'enabled'],
                       ['enabled', 'disabled', 'inactive'],
                       ['enabled', 'disabled', RuntimeError('inactive')]):
            with self.subTest(states=states), patch.object(guest, 'run', side_effect=states):
                with self.assertRaises(RuntimeError):
                    guest.nix_socket_defaults()


class NixAVCIntervalTest(unittest.TestCase):
    def test_historical_denials_are_excluded_but_new_nix_and_foot_denials_fail(self):
        before = 'old avc: denied comm="nix-daemon"\n'
        with patch.object(guest, 'run', return_value=before + 'normal activity\n'):
            self.assertIn('no matching new', guest.no_new_nix_avc(before))
        for denial in ('avc: denied { connectto } comm="nix"',
                       'AVC: DENIED { execute } comm="Foot"'):
            with self.subTest(denial=denial), patch.object(guest, 'run', return_value=before + denial):
                with self.assertRaisesRegex(RuntimeError, 'New Nix/Foot AVC'):
                    guest.no_new_nix_avc(before)

    def test_changed_journal_prefix_is_checked_conservatively_and_read_errors_fail(self):
        for outcome in ('avc: denied comm="nix-daemon"', RuntimeError('journal unavailable')):
            with self.subTest(outcome=outcome), patch.object(guest, 'run', side_effect=[outcome]):
                with self.assertRaises(RuntimeError):
                    guest.no_new_nix_avc('prior journal\n')


class OnlinePreflightTest(unittest.TestCase):
    prefix = ['runuser', '-u', 'ci', '--', 'env', 'HOME=/home/ci']

    def test_direct_dns_and_https_use_the_guest_user_and_bounded_verified_requests(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(
                guest, 'run', side_effect=['1.2.3.4 STREAM', '5.6.7.8 STREAM', '200', '200']) as run:
            result = guest.online_preflight(self.prefix)
        self.assertEqual(result['dns_mode'], 'direct')
        self.assertEqual(result['dns_hosts'], ['api.github.com', 'cache.nixos.org'])
        for call in run.call_args_list:
            self.assertEqual(call.args[0][:len(self.prefix)], self.prefix)
        for call in run.call_args_list[2:]:
            args = call.args[0]
            self.assertIn('--fail', args)
            self.assertNotIn('--insecure', args)
            self.assertEqual(args[args.index('--max-time') + 1], '30')
            self.assertEqual(call.kwargs['timeout'], 40)

    def test_dns_failure_stops_before_https_and_empty_dns_is_rejected(self):
        for outcome in (RuntimeError('Could not resolve host'), ''):
            with self.subTest(outcome=outcome), patch.dict(os.environ, {}, clear=True), \
                    patch.object(guest, 'run', side_effect=[outcome]) as run:
                with self.assertRaisesRegex(RuntimeError, 'resolve|DNS'):
                    guest.online_preflight(self.prefix)
                self.assertEqual(run.call_count, 1)

    def test_tls_or_http_failure_is_not_accepted_as_connectivity(self):
        for outcome in (RuntimeError('TLS verification failed'), '403'):
            with self.subTest(outcome=outcome), patch.dict(os.environ, {}, clear=True), \
                    patch.object(guest, 'run', side_effect=['address', 'address', outcome]) as run:
                with self.assertRaisesRegex(RuntimeError, 'TLS|HTTP'):
                    guest.online_preflight(self.prefix)
                self.assertEqual(run.call_count, 3)

    def test_supported_proxy_checks_proxy_dns_and_keeps_upstream_tls_verification(self):
        with patch.dict(os.environ, {'HTTPS_PROXY': 'http://10.0.2.2:18080'}, clear=True), \
                patch.object(guest, 'run', side_effect=['10.0.2.2 STREAM', '200', '200']) as run:
            result = guest.online_preflight(self.prefix)
        self.assertEqual(result['dns_mode'], 'proxy')
        self.assertEqual(result['dns_hosts'], ['10.0.2.2'])
        self.assertEqual(run.call_args_list[0].args[0], self.prefix + ['getent', 'ahosts', '10.0.2.2'])
        self.assertEqual(result['verified_https'],
                         ['https://api.github.com/', 'https://cache.nixos.org/nix-cache-info'])


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
