"""Exact public fuse unit retains bytes; private context stays fatal."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('public_fuse_screen', HERE/'screen-evidence.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
UNIT = 'modprobe@fuse.service'


class PublicFuseControls(unittest.TestCase):
    def rejected(self, raw):
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaises(RuntimeError) as caught:
            S.external_text(raw)
        self.assertEqual(caught.exception.args, ('Sensitive text in external evidence',))

    def test_bound_public_source_fixture_and_actual_classifier_identity(self):
        raw = (HERE.parent/'tests/fixtures/external-canonical-unit-cases.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            '273a9a9fe3652b8b25446164c72d8f4b36b3b3ac436a9a64dc4b74e32aa554c5')
        item = json.loads(raw)['cases'][1]
        self.assertEqual((item['unit'], item['description'], item['template']),
            (UNIT, 'Load Kernel Module fuse', '/usr/lib/systemd/system/modprobe@.service'))
        self.assertEqual(item['template_sha256'],
            'ac9abd099882e3c01d48786c143b2381c08a690da13984bbfa37ac1c84c8e91b')
        self.assertEqual(S.EXTERNAL_EMAIL_CANDIDATES[1], (UNIT, 'unit-002'))

    def test_exact_delimiters_and_context_decoration_retain_original_bytes(self):
        for left in ('', ' ', '\t', '\r', '\n', ':', 'public '):
            for right in ('', ' ', '\t', '\r', '\n', ':', ' public'):
                raw = (left+UNIT+right).encode()
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    self.assertIs(S.external_text(raw), raw)
                self.assertEqual(out.getvalue(), '')
        raw = ('public \x1b[31m'+UNIT+'\x1b[0m public\r\n').encode()
        self.assertIs(S.external_text(raw), raw)

    def test_affixes_other_units_and_noncontiguous_terminal_spelling_reject(self):
        for value in ('private.'+UNIT, '/'+UNIT, UNIT+'.private', UNIT+'=private',
                UNIT+'ת', UNIT.upper(), UNIT.replace('fuse', 'Fuse'),
                'modprobe@drm.service', 'modprobe@private.service', 'private@example.invalid'):
            self.rejected(value.encode())
        for offset in range(1, len(UNIT)):
            for escape in ('\x1b[31m', '\x1b[2J'):
                self.rejected((UNIT[:offset]+escape+UNIT[offset:]).encode())
        for value in ('\x1bP'+UNIT+'\x1b\\', '\x1b]0; '+UNIT+' \x07'):
            self.rejected(value.encode())

    def test_other_secrets_english_hebrew_transcripts_and_unknown_emails_reject(self):
        values = ('password=private-control', 'Authorization: Bearer private-control',
            'private@example.invalid', 'transcript: private-control', 'תמלול: private-control',
            'https://example.invalid/?query=private-control', '--token private-control')
        for value in values:
            for text in (UNIT+' '+value, value+' '+UNIT):
                self.rejected(text.encode())
        for prefix in ('password=', 'Authorization: Bearer ', 'https://example.invalid/?query='):
            self.rejected((prefix+UNIT).encode())

    def test_atomic_public_upload_has_zero_redactions_and_no_partial_private_upload(self):
        for private in (None, b'password=private-control', b'private\xff'):
            with tempfile.TemporaryDirectory(dir='/tmp') as td:
                root = Path(td);source=root/'source';source.mkdir()
                raw=(UNIT+'\r\n').encode();(source/'a-public.log').write_bytes(raw)
                out=root/'upload'
                if private is None:
                    S.screen_external(source,out)
                    self.assertEqual((out/'a-public.log').read_bytes(),raw)
                    entry=json.loads((out/'upload-screening.json').read_bytes())['files']['a-public.log']
                    self.assertEqual(entry['redactions'],0)
                    self.assertEqual(entry['original_sha256'],hashlib.sha256(raw).hexdigest())
                else:
                    (source/'z-private.log').write_bytes(private)
                    with contextlib.redirect_stdout(io.StringIO()), self.assertRaises((RuntimeError, UnicodeDecodeError)):
                        S.screen_external(source,out)
                    self.assertFalse(out.exists())
                self.assertEqual((source/'a-public.log').read_bytes(),raw)


if __name__ == '__main__':
    unittest.main()
