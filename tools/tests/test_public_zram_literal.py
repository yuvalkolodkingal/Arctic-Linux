"""Only the exact public zram token is exempt; surrounding text stays screened."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT/'tools/native-functional/screen-evidence.py'
spec = importlib.util.spec_from_file_location('public_zram_literal_screen', SCANNER)
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)
UNIT = b'systemd-zram-setup@zram0.service'


class PublicZramLiteralTests(unittest.TestCase):
    def rejected(self, content):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), self.assertRaisesRegex(
                RuntimeError, '^Sensitive text in external evidence$') as caught:
            screen.external_text(content)
        self.assertEqual(caught.exception.args, ('Sensitive text in external evidence',))
        self.assertNotIn(content.decode(), output.getvalue())

    def test_exact_token_uses_existing_delimiters_without_claiming_lifecycle_context(self):
        self.assertEqual(screen.ZRAM_UNIT.encode(), UNIT)
        # The four former context negatives contain only this public token.
        # They are synthetic controls, not reconstructed target UART records.
        for content in (UNIT, b'Stopped ' + UNIT,
                b'[ 1.2] systemd[2]: Stopped ' + UNIT + b' - Create swap on /dev/zram0.\n',
                b'[ 1.2] systemd[1]: Stopped ' + UNIT + b' - Private text.\n'):
            self.assertIs(screen.external_text(content), content)
        for before in (b'', b' ', b'\t', b'\n', b'\r', b':'):
            for after in (b'', b' ', b'\t', b'\n', b'\r', b':'):
                content = before + UNIT + after
                self.assertIs(screen.external_text(content), content)
        self.assertEqual(screen.EXTERNAL_EMAIL_CANDIDATES[-1], (screen.ZRAM_UNIT, 'unit-012'))
        self.assertNotIn(screen.ZRAM_UNIT, [unit for unit, _ in screen.CANONICAL_UNITS])

    def test_private_instances_case_and_affixes_are_not_public_tokens(self):
        for token in (b'private@zram0.service', b'real.email@example.service',
                UNIT.replace(b'zram0', b'zram1'), UNIT.replace(b'zram0', b'zram00'),
                UNIT.upper(), UNIT.replace(b'.service', b'.Service'),
                b'39m' + UNIT, b'private-' + UNIT, UNIT + b'.private',
                UNIT + b'-private', UNIT + b'/private', UNIT + b'?private',
                b'"' + UNIT + b'"', b'(' + UNIT + b')', b'=' + UNIT, UNIT + b'=private'):
            self.rejected(token)

    def test_ansi_or_terminal_bytes_cannot_construct_the_public_literal(self):
        for position in range(1, len(UNIT)):
            for escape in (b'\x1b[0m', b'\x1b[2J', b'\x1b]0;public\x07', b'\x1bPpublic\x1b\\'):
                self.rejected(UNIT[:position] + escape + UNIT[position:])
        public = b'\x1b[0;1;39m' + UNIT + b'\x1b[0m'
        self.assertIs(screen.external_text(public), public)

    def test_public_token_does_not_exempt_private_values_or_transcripts(self):
        controls = (b'real.email@example.service', b'Authorization: Bearer private',
            b'ghp_syntheticprivatecontrol', b'https://private.invalid?token=value',
            b'password=private', b'api_key: private', b'--token private',
            b'Transcript: private text', b'transcription=private text',
            'תמלול: טקסט פרטי'.encode(), 'תמליל=טקסט פרטי'.encode(),
            b'Trans\x1b[0mcript: private text', b'api_\x1b[2Jkey=private')
        for private in controls:
            for content in (UNIT + b' ' + private, private + b' ' + UNIT,
                    UNIT + b'\n' + private, UNIT + b'\x1b]0;' + private + b'\x07'):
                self.rejected(content)

    def test_original_cli_preserves_exact_bytes_or_rejects_without_private_errors(self):
        for private in (None, b'password=private-control', b'Transcript: private-control',
                'תמלול: טקסט פרטי'.encode()):
            with self.subTest(private=private is not None), tempfile.TemporaryDirectory() as temp:
                source, target = Path(temp)/'owned', Path(temp)/'screened'
                source.mkdir()
                raw = b'public control: ' + UNIT + b'\r\n'
                if private is not None:
                    raw += private + b'\n'
                original = source/'host-serial.log'
                original.write_bytes(raw)
                result = subprocess.run([sys.executable, '-B', str(SCANNER), '--preserve-original',
                    '--source', str(source), '--out', str(target)], capture_output=True, timeout=10)
                self.assertEqual(original.read_bytes(), raw)
                if private is not None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(target.exists())
                    self.assertNotIn(private, result.stdout + result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr.decode())
                    self.assertEqual((target/original.name).read_bytes(), raw)
                    sha = hashlib.sha256(raw).hexdigest()
                    self.assertEqual(json.loads((target/'upload-screening.json').read_text())['files'][original.name],
                        dict(original_sha256=sha, uploaded_sha256=sha, bytes=len(raw), redactions=0))


if __name__ == '__main__':
    unittest.main()
