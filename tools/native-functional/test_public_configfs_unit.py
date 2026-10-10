"""Preserve one attested public unit; keep every private rejection intact."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import tracemalloc
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('public_configfs_screen', HERE/'screen-evidence.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)
UNIT = 'modprobe@configfs.service'
PRIVATE = 'private-value-תמליל'


class PublicConfigfsControls(unittest.TestCase):
    def rejected(self, raw):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(RuntimeError) as caught:
            S.external_text(raw)
        self.assertEqual(caught.exception.args, ('Sensitive text in external evidence',))
        self.assertNotIn(PRIVATE, out.getvalue())

    def test_public_source_fixture_and_closed_actual_candidate_are_bound(self):
        raw = (HERE.parent/'tests/fixtures/external-canonical-unit-cases.json').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),
            '273a9a9fe3652b8b25446164c72d8f4b36b3b3ac436a9a64dc4b74e32aa554c5')
        first = json.loads(raw)['cases'][0]
        self.assertEqual((first['unit'], first['description'], first['template']),
            (UNIT, 'Load Kernel Module configfs', '/usr/lib/systemd/system/modprobe@.service'))
        self.assertEqual(first['template_sha256'],
            'ac9abd099882e3c01d48786c143b2381c08a690da13984bbfa37ac1c84c8e91b')
        self.assertEqual(S.EXTERNAL_EMAIL_CANDIDATES[0], (UNIT, 'unit-001'))
        self.assertEqual(S.CANONICAL_UNITS[0], (UNIT, 'Load Kernel Module configfs'))

    def test_exact_delimiters_and_original_bytes_survive_without_output(self):
        for before in ('', ' ', '\t', '\r', '\n', ':', 'public '):
            for after in ('', ' ', '\t', '\r', '\n', ':', ' public'):
                raw = (before+UNIT+after).encode()
                with self.subTest(before=before, after=after):
                    out = io.StringIO()
                    with contextlib.redirect_stdout(out):
                        self.assertIs(S.external_text(raw), raw)
                    self.assertEqual(out.getvalue(), '')
        for raw in ((UNIT+':').encode(), ('\x1b[31m'+UNIT+'\x1b[0m').encode(),
                    ('public \x1b[31m'+UNIT+'\x1b[0m public\r\n').encode()):
            self.assertIs(S.external_text(raw), raw)

    def test_private_affixes_case_confusables_and_wrong_delimiters_remain_fatal(self):
        for value in ('private-'+UNIT, 'private.'+UNIT, 'private'+UNIT,
                UNIT+'.private', UNIT+'-private', UNIT+'+private', UNIT+'=private',
                UNIT+'/private', '/'+UNIT, UNIT+';', '('+UNIT+')', '['+UNIT+']',
                UNIT.upper(), UNIT.replace('configfs', 'Configfs'),
                UNIT.replace('service', 'servicе')+'.private', UNIT+'ת',
                UNIT.replace('configfs', 'private'), UNIT.replace('service', 'serviceX')):
            with self.subTest(value=value):
                self.rejected(value.encode())

    def test_internal_ansi_control_and_terminal_payload_remain_fatal(self):
        for index in range(1, len(UNIT)):
            for escape in ('\x1b[31m', '\x1b[2J'):
                with self.subTest(index=index, escape=escape):
                    self.rejected((UNIT[:index]+escape+UNIT[index:]).encode())
        for raw in (('\x1bP'+UNIT+'\x1b\\').encode(),
                    ('\x1b]0;'+UNIT+'\x07').encode(),
                    ('\x1b]0; public '+UNIT+' \x07').encode()):
            self.rejected(raw)

    def test_other_public_units_and_unknown_emails_retain_original_rejection(self):
        for literal, _ in S.EXTERNAL_EMAIL_CANDIDATES[1:]:
            with self.subTest(literal=literal):
                self.rejected(literal.encode())
        self.rejected(b'private@example.invalid')

    def test_same_full_match_and_all_other_private_rules_remain_fatal(self):
        cases = ('ghp_private123', 'AKIA0123456789ABCDEF',
            'Authorization: Bearer '+PRIVATE, 'private@example.invalid',
            'https://example.invalid/?query='+PRIVATE,
            'https://'+PRIVATE+'@example.invalid/', 'password='+PRIVATE,
            '--token '+PRIVATE, 'cryptsetup open /dev/vda4 owned < '+PRIVATE,
            'תמלול:'+PRIVATE)
        for private in cases:
            for value in (UNIT+' '+private, private+' '+UNIT):
                with self.subTest(value=value):
                    self.rejected(value.encode())
        for prefix in ('password=', 'Authorization: Bearer ', 'https://example.invalid/?query='):
            value = prefix+UNIT
            self.assertEqual(S.public_token_spans(value), set())
            self.rejected(value.encode())

    def test_oversized_private_match_is_not_copied_by_literal_exception(self):
        value = 'prefix ' + 'x' * (2 * 1024 * 1024) + '@example.invalid suffix'
        tracemalloc.start()
        try:
            self.assertEqual(S.public_token_spans(value), set())
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 128 * 1024)

    def test_atomic_upload_preserves_public_token_and_rejects_private_or_invalid_utf8(self):
        for bad in (('password='+PRIVATE).encode(), b'bad\xffprivate'):
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                source = root/'source'
                source.mkdir()
                public = source/'a-public.log'
                public.write_bytes((UNIT+'\r\n').encode())
                before = public.stat()
                (source/'z-rejected.txt').write_bytes(bad)
                with contextlib.redirect_stdout(io.StringIO()), self.assertRaises((RuntimeError, UnicodeDecodeError)):
                    S.screen_external(source, root/'upload')
                self.assertFalse((root/'upload').exists())
                after = public.stat()
                self.assertEqual((before.st_ino, before.st_mtime_ns, before.st_mode),
                    (after.st_ino, after.st_mtime_ns, after.st_mode))
                self.assertEqual(public.read_bytes(), (UNIT+'\r\n').encode())
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root/'source'
            source.mkdir()
            original = (UNIT+'\r\n').encode()
            (source/'public.log').write_bytes(original)
            S.screen_external(source, root/'upload')
            self.assertEqual((root/'upload/public.log').read_bytes(), original)
            receipt = json.loads((root/'upload/upload-screening.json').read_bytes())
            self.assertEqual(receipt['files']['public.log']['original_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(receipt['files']['public.log']['uploaded_sha256'], hashlib.sha256(original).hexdigest())
            self.assertEqual(receipt['files']['public.log']['redactions'], 0)


if __name__ == '__main__':
    unittest.main()
