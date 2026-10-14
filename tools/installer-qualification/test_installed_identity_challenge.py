"""Installed Fish readiness and fresh UID challenge controls; no VM qualification."""
import contextlib
import hashlib
import importlib.util
import io
import json
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
        region = [0]
        with tempfile.TemporaryDirectory(prefix='installed-identity-') as temporary:
            root = Path(temporary)
            probe = root / 'probe.png'

            def shot(_label):
                Image.new('RGB', size).save(probe)
                previous[0] = next(rows, previous[0])
                region[0] = 0
                return probe

            def ocr(*args, **kwargs):
                self.ocr_arguments.append((args, kwargs))
                if args[0][1] == 'stdin':
                    lines = [line for line in previous[0].splitlines() if line.strip()]
                    output = lines[region[0]] if len(lines) == 3 else previous[0]
                    region[0] += 1
                    return types.SimpleNamespace(stdout=output)
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
                    self.retained = {p.name: p.read_bytes() for p in root.iterdir()
                                     if p.name.startswith('installed-identity-challenge')}
                    return error, calls, probe.exists()
                self.retained = {p.name: p.read_bytes() for p in root.iterdir()
                                 if p.name.startswith('installed-identity-challenge')}
                return proof, calls, probe.exists()

    def test_two_exact_rows_never_bypass_the_full_three_row_consensus(self):
        expected = D.installed_user_records(self.nonce)
        for rows in (expected[:2], (expected[0], expected[1], expected[1])):
            with self.subTest(rows=rows):
                accepted, _ = D._identity_ocr_observation(('\n'.join(rows)).encode(), expected, True)
                self.assertFalse(accepted)

    def test_zero_exact_rows_can_only_pass_with_every_digit_correct_by_consensus(self):
        expected = D.installed_user_records(self.nonce)
        rows = list(expected)
        for index, column in enumerate((2, 8, 15)):
            digit = '0' if rows[index][column] != '0' else '1'
            rows[index] = rows[index][:column] + digit + rows[index][column + 1:]
        accepted, observation = D._identity_ocr_observation(('\n'.join(rows)).encode(), expected, True)
        self.assertTrue(accepted)
        self.assertEqual(observation, ('three', 'three', 'zero', 'true'))
        # A column with three different digits has no consensus, even with two
        # exact rows in other columns. A fourth numeric record also denies.
        rows[1] = rows[1][:2] + ('2' if rows[0][2] != '2' else '3') + rows[1][3:]
        rows[2] = rows[2][:2] + ('4' if rows[0][2] != '4' else '5') + rows[2][3:]
        self.assertFalse(D._identity_ocr_observation(('\n'.join(rows)).encode(), expected, True)[0])
        self.assertFalse(D._identity_ocr_observation(('\n'.join((*expected, expected[0]))).encode(), expected, True)[0])

    def test_mismatch_keeps_at_most_three_original_failure_only_frames(self):
        error, _, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', self.response(uid=0)])
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual(set(self.retained), {*D.IDENTITY_CHALLENGE_IMAGES, D.IDENTITY_CHALLENGE_METADATA})
        raw = self.retained[D.IDENTITY_CHALLENGE_METADATA]
        metadata = json.loads(raw)
        self.assertIs(metadata['authentication'], False)
        self.assertIs(metadata['release_acceptance'], False)
        for name, record in zip(D.IDENTITY_CHALLENGE_IMAGES, metadata['captures']):
            self.assertEqual(record['path'], name)
            self.assertEqual(record['bytes'], len(self.retained[name]))
            self.assertEqual(record['sha256'], hashlib.sha256(self.retained[name]).hexdigest())
            self.assertEqual(record['size'], [1280, 720])
        self.assertNotIn(self.nonce.encode(), raw)
        self.assertNotIn(self.secret.encode(), raw)
        self.assertNotIn(self.response(uid=0).strip(), raw)
        guards = [args for args, _ in self.ocr_arguments[1:] if '-c' not in args[0]]
        self.assertEqual(len(guards), 3)

    def test_later_exact_consensus_removes_all_failure_only_members(self):
        proof, _, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', self.response(uid=0), self.response()])
        self.assertIs(type(proof), dict)
        self.assertEqual(self.retained, {})

    def test_private_input_in_unwhitelisted_guard_is_never_retained(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); probe = root / 'probe.png'
            Image.new('RGB', (1280, 720)).save(probe)
            with patch.object(D.subprocess, 'run', return_value=types.SimpleNamespace(stdout=self.secret.upper().encode())) as guard:
                with self.assertRaisesRegex(RuntimeError, 'image withheld'):
                    D.identity_challenge_capture(probe, root, self.secret, [], D.time.monotonic() + 20)
            self.assertNotIn('-c', guard.call_args.args[0])
            self.assertEqual({p.name for p in root.iterdir()}, {'probe.png'})

    def test_changed_frame_and_foreign_metadata_generation_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); probe = root / 'probe.png'
            Image.new('RGB', (1280, 720)).save(probe)
            def change(*_args, **_kwargs):
                Image.new('RGB', (1280, 720), 'red').save(probe)
                return types.SimpleNamespace(stdout=b'')
            with patch.object(D.subprocess, 'run', side_effect=change), self.assertRaises(RuntimeError):
                D.identity_challenge_capture(probe, root, self.secret, [], D.time.monotonic() + 20)
            self.assertFalse((root / D.IDENTITY_CHALLENGE_METADATA).exists())
            captures = []
            with patch.object(D.subprocess, 'run', return_value=types.SimpleNamespace(stdout=b'')):
                D.identity_challenge_capture(probe, root, self.secret, captures, D.time.monotonic() + 20)
                metadata = root / D.IDENTITY_CHALLENGE_METADATA
                foreign = root / 'foreign.json'; foreign.write_bytes(metadata.read_bytes())
                os.replace(foreign, metadata)
                with self.assertRaisesRegex(RuntimeError, 'ownership differs'):
                    D.identity_challenge_capture(probe, root, self.secret, captures, D.time.monotonic() + 20)
                with self.assertRaisesRegex(RuntimeError, 'ownership differs'):
                    D.discard_identity_challenges(root, captures)
            self.assertTrue(metadata.exists())

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

    def test_disjoint_row_errors_reconstruct_only_by_full_digit_consensus(self):
        records = list(D.installed_user_records(self.nonce))
        first = 4
        second = 11
        records[1] = records[1][:first] + ('0' if records[1][first] != '0' else '1') + records[1][first + 1:]
        records[2] = records[2][:second] + ('0' if records[2][second] != '0' else '1') + records[2][second + 1:]
        response = ('\n\n         '.join(records) + '\n').encode()
        proof, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', response])
        self.assertIs(type(proof), dict)
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])
        self.assertEqual(proof['observed_line_sha256'],
                         hashlib.sha256(('\n'.join(D.installed_user_records(self.nonce))).encode()).hexdigest())

    def test_same_column_wrong_majority_and_duplicate_markers_are_rejected(self):
        expected = list(D.installed_user_records(self.nonce))
        column = 7
        wrong = '0' if expected[1][column] != '0' else '1'
        expected[1] = expected[1][:column] + wrong + expected[1][column + 1:]
        expected[2] = expected[2][:column] + wrong + expected[2][column + 1:]
        wrong_majority = ('\n'.join(expected) + '\n').encode()
        error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', wrong_majority])
        self.assertIs(type(error), RuntimeError)
        self.assertEqual(error.args, ('installed user identity response differs',))
        self.assertEqual([call[0] for call in calls], ['text', 'keys'])

        records = list(D.installed_user_records(self.nonce))
        duplicate_markers = ('\n'.join((records[0], records[0], records[2])) + '\n').encode()
        error, calls, _ = self.exercise([b'arcticqual@arctic-qual ~>\n', duplicate_markers])
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
