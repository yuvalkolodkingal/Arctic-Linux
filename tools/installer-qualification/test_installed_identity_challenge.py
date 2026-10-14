"""Installed Fish readiness and fresh UID challenge controls; no VM qualification."""
import contextlib
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import re
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

    def response(self, nonce=None, *, user='arcticqual', uid=1000, id_un='arcticqual',
                 corrupt=()):
        nonce = nonce or self.nonce
        token = D.installed_user_token(nonce, user, uid, id_un)
        records = [marker + token for marker in D.IDENTITY_MARKERS]
        for index in corrupt:
            records[index] = records[index][:-1] + ('0' if records[index][-1] != '0' else '1')
        return ('\n\n         '.join(records) + '\n').encode()

    def exercise(self, outputs, *, size=(1280, 720), console=True):
        clock = [0.0]
        calls = []
        self.ocr_arguments = []
        rows = iter(outputs)
        previous = [b'']
        with tempfile.TemporaryDirectory(prefix='installed-identity-') as temporary:
            root = Path(temporary)
            probe = root / 'probe.png'

            def shot(_label):
                Image.new('RGB', size).save(probe)
                return probe

            def ocr(*args, **kwargs):
                self.ocr_arguments.append((args, kwargs))
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
        expected = D.installed_user_records(self.nonce)
        self.assertTrue(all(record not in command for record in expected))
        self.assertTrue(all(('\\0' + format(ord(marker), '02o')) in command
                            for marker in D.IDENTITY_MARKERS))
        result = subprocess.run(['/bin/sh', '-c', command], capture_output=True, check=True, timeout=5)
        self.assertEqual(result.stderr, b'')
        rendered = result.stdout.decode()
        self.assertTrue(rendered.startswith('\x1b[2J\x1b[8;10H\x1b[1m'))
        visible = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', rendered)
        records = [line.replace(' ', '') for line in visible.splitlines() if line.strip()]
        token = D.installed_user_token(
            self.nonce, os.environ['USER'], os.getuid(),
            subprocess.check_output(['id', '-un'], text=True).strip())
        self.assertEqual(records, [marker + token for marker in D.IDENTITY_MARKERS])
        self.assertNotIn(self.nonce, rendered)

    def test_both_fixed_fish_prompt_renders_require_a_fresh_exact_response(self):
        expected = self.response()
        for prompt in (b'arcticqual@arctic-qual ~ >\n', b'arcticqual@arctic-qual ~>\n'):
            with self.subTest(prompt=prompt):
                proof, calls, present = self.exercise([prompt, expected])
                self.assertIs(type(proof), dict)
                self.assertEqual(proof['prompt_kind'], 'installed-user-sha256-decimal-identity')
                self.assertEqual(proof['nonce'], self.nonce)
                self.assertEqual(proof['username'], 'arcticqual')
                self.assertEqual(proof['uid'], 1000)
                self.assertEqual(proof['observed_line_sha256'],
                                 hashlib.sha256(('\n'.join(D.installed_user_records(self.nonce))).encode()).hexdigest())
                self.assertEqual(len([call for call in calls if call[0] == 'text']), 1)
                self.assertNotIn('tessedit_char_whitelist=0123456789', self.ocr_arguments[0][0][0])
                self.assertIn('tessedit_char_whitelist=0123456789', self.ocr_arguments[1][0][0])
                self.assertFalse(present)
                self.assertNotIn(self.secret, repr(proof))

    def test_fish_greeting_gets_one_nonsecret_return_before_readiness(self):
        expected = self.response()
        proof, calls, _ = self.exercise([
            b'Welcome to fish, the friendly interactive shell\n',
            b'arcticqual@arctic-qual ~>\n', expected])
        self.assertIs(type(proof), dict)
        self.assertEqual([call[0] for call in calls], ['keys', 'text', 'keys'])
        self.assertEqual(calls[0], ('keys', ('ret',)))
        self.assertNotIn(self.secret, repr(calls))

    def test_unrecognized_cosmetic_prompt_uses_one_nonsecret_readiness_fallback(self):
        expected = self.response()
        proof, calls, _ = self.exercise([
            b'Welcome to fish, the friendly interactive shell\n',
            b'arcticqual at arctic-qual home prompt\n', expected])
        self.assertIs(type(proof), dict)
        self.assertEqual([call[0] for call in calls], ['keys', 'text', 'keys'])
        self.assertEqual(calls[0], ('keys', ('ret',)))
        self.assertNotIn(self.secret, repr(calls))

    def test_one_corrupt_redundant_record_is_accepted_but_one_exact_is_not(self):
        response = self.response(corrupt=(2,))
        proof, calls, _ = self.exercise([
            b'arcticqual@arctic-qual ~>\n', response])
        self.assertIs(type(proof), dict)
        self.assertEqual(proof['observed_line_sha256'],
                         hashlib.sha256(('\n'.join(D.installed_user_records(self.nonce))).encode()).hexdigest())
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])
        self.assertNotIn(self.secret, repr(proof))

        error, calls, _ = self.exercise([
            b'arcticqual@arctic-qual ~>\n', self.response(corrupt=(1, 2))])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])

    def test_duplicate_single_record_cannot_satisfy_two_of_three(self):
        record = D.installed_user_records(self.nonce)[0]
        response = ((record + '\n') * D.IDENTITY_RECORDS).encode()
        error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', response])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])
        self.assertEqual(D.identity_observation_codes(error), (
            'installer-inner-driver-installed-proof-identity-record-count-three',
            'installer-inner-driver-installed-proof-identity-marker-count-three',
            'installer-inner-driver-installed-proof-identity-exact-count-one',
            'installer-inner-driver-installed-proof-identity-challenge-issued-true'))

    def test_repeated_mismatch_waits_to_deadline_and_exports_only_closed_facts(self):
        replay = self.response('0' * 32, user='root', uid=0, id_un='root')
        error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', replay])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])
        self.assertEqual(D.identity_observation_codes(error), (
            'installer-inner-driver-installed-proof-identity-record-count-three',
            'installer-inner-driver-installed-proof-identity-marker-count-three',
            'installer-inner-driver-installed-proof-identity-exact-count-zero',
            'installer-inner-driver-installed-proof-identity-challenge-issued-true'))
        stream = io.StringIO()
        token = 'a' * 32
        with patch.dict(os.environ, {'ARCTIC_INSTALLER_DIAGNOSTIC_TOKEN': token}), \
                contextlib.redirect_stdout(stream):
            D.diagnose('driver-installed-proof', error)
        diagnostic = stream.getvalue()
        self.assertNotIn(self.nonce, diagnostic)
        self.assertNotIn(self.secret, diagnostic)
        self.assertNotIn(replay.decode().strip(), diagnostic)
        self.assertNotIn(hashlib.sha256(replay).hexdigest(), diagnostic)
        self.assertNotIn(self.nonce, repr(error))
        self.assertNotIn(self.nonce, repr(error.__dict__))
        self.assertNotIn(replay.decode().strip(), repr(error.__dict__))
        self.assertNotIn(hashlib.sha256(replay).hexdigest(), repr(error.__dict__))
        self.assertEqual(len(diagnostic.splitlines()), 5)

    def test_absent_response_reports_fixed_challenge_basis_without_private_text(self):
        cases = (
            ([b''], 'installed user identity challenge was not issued; sudo input refused', []),
            ([b'arcticqual@arctic-qual ~>\n'],
             'exact installed user identity was not observed after exact prompt; sudo input refused',
             ['text', 'keys']),
            ([b'Welcome to fish, the friendly interactive shell\n'],
             'exact installed user identity was not observed after readiness fallback; sudo input refused',
             ['keys', 'text', 'keys']),
        )
        for outputs, message, expected_calls in cases:
            with self.subTest(message=message):
                error, calls, _ = self.exercise(outputs)
                self.assertIs(type(error), RuntimeError)
                self.assertEqual(error.args, (message,))
                self.assertEqual([call[0] for call in calls], expected_calls)
                self.assertNotIn(self.secret, repr(error))
                self.assertNotIn(self.nonce, repr(error))

    def test_wrong_or_replayed_response_never_authorizes_sudo(self):
        wrong = (
            self.response(),
            self.response(user='root', uid=0, id_un='root'),
            self.response('0' * 32),
        )
        error, calls, _ = self.exercise([wrong[0]])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual(calls, [])
        for response in wrong[1:]:
            error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', response])
            self.assertIs(type(error), RuntimeError)
            self.assertEqual(error.args, ('installed user identity response differs',))
            self.assertEqual(len([call for call in calls if call[0] == 'text']), 1)

    def test_mismatch_never_returns_authorization_before_exact_response(self):
        response = self.response(user='arcticqua')
        error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', response])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])
        self.assertTrue(all(self.secret not in repr(call) for call in calls))

    def test_login_failure_private_echo_console_and_dimensions_fail_closed(self):
        cases = (
            ([b'Login incorrect\n'], True, (1280, 720)),
            ([(self.secret + '\n').encode()], True, (1280, 720)),
            ([b'arcticqual@arctic-qual ~>\n'], False, (1280, 720)),
            ([b'arcticqual@arctic-qual ~>\n', self.response()], True, (1280, 721)),
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
            'installed user identity challenge was not issued; sudo input refused': 'identity-challenge-not-sent',
            'exact installed user identity was not observed after exact prompt; sudo input refused': 'identity-response-after-prompt-absent',
            'exact installed user identity was not observed after readiness fallback; sudo input refused': 'identity-response-after-fallback-absent',
            'installed guest proof failed': 'helper-failed',
        }
        for message, label in expected.items():
            code = D.diagnostic_code('driver-installed-proof', RuntimeError(message))
            self.assertEqual(code, 'installer-inner-driver-installed-proof-' + label)
            self.assertNotIn(message, code)
            self.assertIn(code, D.DIAGNOSTIC_CODES)

    def test_identity_observation_rejects_forged_or_value_bearing_shapes(self):
        class Hostile(str):
            def __eq__(self, _other):
                raise AssertionError('must not compare hostile private text')

        error = RuntimeError('installed user identity response differs')
        private = 'private-ocr-value-' + self.nonce
        forged = (
            (object(), 'three', 'three', 'zero', 'true'),
            (D._IDENTITY_OBSERVATION_TOKEN, Hostile('three'), 'three', 'zero', 'true'),
            (D._IDENTITY_OBSERVATION_TOKEN, 'three', private, 'zero', 'true'),
            (D._IDENTITY_OBSERVATION_TOKEN, 'three', 'three', 'zero'),
        )
        for observation in forged:
            error._arctic_installer_identity_observation = observation
            self.assertEqual(D.identity_observation_codes(error), ())
        for code in D.DIAGNOSTIC_CODES:
            self.assertNotIn(private, code)


if __name__ == '__main__':
    unittest.main(verbosity=2)
