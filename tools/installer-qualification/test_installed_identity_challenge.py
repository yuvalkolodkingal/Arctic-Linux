"""Installed Fish readiness and fresh UID challenge controls; no VM qualification."""
import hashlib
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest
from unittest.mock import patch

from PIL import Image

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('installed_identity_driver', HERE / 'driver.py')
D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(D)


class InstalledIdentityChallengeControls(unittest.TestCase):
    nonce = '1234567890abcdef1234567890abcdef'
    secret = 'f' * 32

    def exercise(self, outputs, *, size=(1280, 720), console=True):
        clock = [0.0]
        calls = []
        rows = iter(outputs)
        previous = [b'']
        with tempfile.TemporaryDirectory(prefix='installed-identity-') as temporary:
            root = Path(temporary)
            probe = root / 'probe.png'

            def shot(_label):
                Image.new('RGB', size).save(probe)
                return probe

            def ocr(*_args, **_kwargs):
                previous[0] = next(rows, previous[0])
                return types.SimpleNamespace(stdout=previous[0])

            vm = types.SimpleNamespace(
                alive=lambda: True,
                shot=shot,
                type_text=lambda text, gap: calls.append(('text', text, gap)),
                keys=lambda *keys: calls.append(('keys', keys)),
            )
            with patch.object(D.time, 'monotonic', side_effect=lambda: clock[0]), \
                    patch.object(D.time, 'monotonic_ns', side_effect=lambda: int(clock[0] * 1e9) + 1), \
                    patch.object(D.time, 'sleep', side_effect=lambda seconds: clock.__setitem__(0, clock[0] + seconds)), \
                    patch.object(D.subprocess, 'run', side_effect=ocr):
                try:
                    proof = D.console_user_identity(
                        vm, types.SimpleNamespace(console_screen=lambda _path: console),
                        root, self.nonce, self.secret)
                except BaseException as error:
                    return error, calls, probe.exists()
                return proof, calls, probe.exists()

    def test_command_cannot_contain_its_exact_response(self):
        command = D.installed_user_command(self.nonce)
        expected = D.installed_user_line(self.nonce)
        self.assertNotIn(expected, command)
        self.assertNotIn('ARCTIC-USER ', command)
        result = subprocess.run(['/bin/sh', '-c', command], capture_output=True, check=True, timeout=5)
        self.assertEqual(result.stderr, b'')
        actual = result.stdout.decode().strip()
        self.assertEqual(actual, 'ARCTIC-USER ' + self.nonce + ' uid=' + str(os.getuid()) +
                         ' user=' + subprocess.check_output(['id', '-un'], text=True).strip())

    def test_both_fixed_fish_prompt_renders_require_a_fresh_exact_response(self):
        expected = (D.installed_user_line(self.nonce) + '\n').encode()
        for prompt in (b'arcticqual@arctic-qual ~ >\n', b'arcticqual@arctic-qual ~>\n'):
            with self.subTest(prompt=prompt):
                proof, calls, present = self.exercise([prompt, expected])
                self.assertIs(type(proof), dict)
                self.assertEqual(proof['prompt_kind'], 'installed-user-nonce-identity')
                self.assertEqual(proof['nonce'], self.nonce)
                self.assertEqual(proof['username'], 'arcticqual')
                self.assertEqual(proof['uid'], 1000)
                self.assertEqual(proof['observed_line_sha256'], hashlib.sha256(expected.rstrip()).hexdigest())
                self.assertEqual(len([call for call in calls if call[0] == 'text']), 1)
                self.assertFalse(present)
                self.assertNotIn(self.secret, repr(proof))

    def test_fish_greeting_gets_one_nonsecret_return_before_readiness(self):
        expected = (D.installed_user_line(self.nonce) + '\n').encode()
        proof, calls, _ = self.exercise([
            b'Welcome to fish, the friendly interactive shell\n',
            b'arcticqual@arctic-qual ~>\n', expected])
        self.assertIs(type(proof), dict)
        self.assertEqual([call[0] for call in calls], ['keys', 'text', 'keys'])
        self.assertEqual(calls[0], ('keys', ('ret',)))
        self.assertNotIn(self.secret, repr(calls))

    def test_wrong_or_replayed_response_never_authorizes_sudo(self):
        wrong = (
            (D.installed_user_line(self.nonce) + '\n').encode(),
            ('ARCTIC-USER ' + self.nonce + ' uid=0 user=root\n').encode(),
            (D.installed_user_line('0' * 32) + '\n').encode(),
        )
        error, calls, _ = self.exercise([wrong[0]])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(calls, [])
        for response in wrong[1:]:
            error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', response])
            self.assertIs(type(error), RuntimeError)
            self.assertEqual(len([call for call in calls if call[0] == 'text']), 1)

    def test_login_failure_private_echo_console_and_dimensions_fail_closed(self):
        cases = (
            ([b'Login incorrect\n'], True, (1280, 720)),
            ([(self.secret + '\n').encode()], True, (1280, 720)),
            ([b'arcticqual@arctic-qual ~>\n'], False, (1280, 720)),
            ([b'arcticqual@arctic-qual ~>\n', (D.installed_user_line(self.nonce) + '\n').encode()], True, (1280, 721)),
        )
        for outputs, console, size in cases:
            with self.subTest(outputs=outputs, console=console, size=size):
                error, _calls, _present = self.exercise(outputs, console=console, size=size)
                self.assertIsInstance(error, BaseException)

    def test_failure_projection_uses_only_fixed_privacy_safe_codes(self):
        expected = {
            'exact console prompt was not observed; secret input refused': 'password-prompt-absent',
            'installed user login did not reach its identity challenge': 'identity-login-failed',
            'installed user identity response differs': 'identity-response-differs',
            'installed user identity deadline exceeded': 'identity-deadline',
            'exact installed user identity was not observed; sudo input refused': 'identity-response-absent',
            'installed guest proof failed': 'helper-failed',
        }
        for message, label in expected.items():
            code = D.diagnostic_code('driver-installed-proof', RuntimeError(message))
            self.assertEqual(code, 'installer-inner-driver-installed-proof-' + label)
            self.assertNotIn(message, code)
            self.assertIn(code, D.DIAGNOSTIC_CODES)


if __name__ == '__main__':
    unittest.main(verbosity=2)
