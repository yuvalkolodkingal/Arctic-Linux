"""One package/fixture-supported public literal; all unknown emails stay private."""
import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('owned_getty6_scanner',Path(__file__).with_name('screen-evidence.py'))
S=importlib.util.module_from_spec(spec);spec.loader.exec_module(S)
UNIT='getty@tty6.service'
DESCRIPTION='Getty on tty6'
FIXTURE=ROOT/'tests/fixtures/installer-getty6-public-template.json'
FIXTURE_SHA='b50504c68f9d21ac69ee9b38e5d0df2af915db4546244b2137b3c0910c6c35fa'

def restore_bounded_collection_observer(driver):
    """Strict test-only inverse; retain the entire historical fixture hash."""
    for current,original in (
        (b'MAX_COLLECTION_DIAGNOSTIC_FRAMES = 64\n',b''),
        (b'        for _ in range(MAX_COLLECTION_DIAGNOSTIC_FRAMES):\n            if traceback is None:\n                break\n',b'        while traceback is not None:\n'),
        (b'        if traceback is not None:\n            return None  # Never present a truncated prefix as the deepest phase.\n',b''),
    ):
        if driver.count(current)!=1:raise AssertionError('Expected one exact bounded observer addition')
        driver=driver.replace(current,original,1)
    return driver

class GettySixControls(unittest.TestCase):
    def rejected(self,value):
        stream=io.StringIO();raw=value.encode()
        with contextlib.redirect_stdout(stream),self.assertRaises(RuntimeError):S.external_text(raw)
        self.assertNotIn(value,stream.getvalue())

    def test_fixed_template_package_and_explicit_vt6_fixture_are_bound(self):
        raw=FIXTURE.read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),FIXTURE_SHA);d=json.loads(raw)
        template=d['template_utf8'].encode();self.assertEqual(hashlib.sha256(template).hexdigest(),d['template_sha256'])
        self.assertEqual(d['template_sha256'],'988eaaf6676a10fa3d34548eb25bd9e73c6544ee0674bf0b374f56a9019b5d1e')
        self.assertEqual(template.count(b'Description=Getty on %I\n'),1)
        self.assertEqual('Getty on %I'.replace('%I',d['instance']),DESCRIPTION)
        self.assertEqual((d['unit'],d['description']),(UNIT,DESCRIPTION))
        for proof in d['package_inventory_evidence']:
            self.assertEqual((proof['package']['version'],proof['package']['release']),('259.9','1.fc44'))
            self.assertIs(proof['verified_unit_record']['rpm_file_digest_verified'],True)
            self.assertEqual(proof['verified_unit_record']['rpm_file_digest'],d['template_sha256'])
        driver=(ROOT/'installer-qualification/driver.py').read_bytes()
        driver=restore_bounded_collection_observer(driver)
        self.assertEqual(hashlib.sha256(driver).hexdigest(),d['fixture_source']['source_sha256'])
        self.assertIn("for key in ('ctrl', 'alt', 'f6')",driver.decode())
        self.assertTrue(any('no private prior uart token' in value.lower() for value in d['limits']))

    def test_bounded_observer_inverse_rejects_mutated_addition_and_unknown_original_byte(self):
        driver=(ROOT/'installer-qualification/driver.py').read_bytes()
        expected=json.loads(FIXTURE.read_bytes())['fixture_source']['source_sha256']
        self.assertEqual(hashlib.sha256(restore_bounded_collection_observer(driver)).hexdigest(),expected)
        with self.assertRaises(AssertionError):
            restore_bounded_collection_observer(driver.replace(b'MAX_COLLECTION_DIAGNOSTIC_FRAMES = 64',b'MAX_COLLECTION_DIAGNOSTIC_FRAMES = 63',1))
        unknown=restore_bounded_collection_observer(driver+b'\n# uncontrolled original-byte mutation\n')
        with self.assertRaises(AssertionError):self.assertEqual(hashlib.sha256(unknown).hexdigest(),expected)

    def test_exact_all_three_lifecycle_contexts_preserve_original_bytes_without_output(self):
        for prefix in ('[ 1.234] systemd[1]: ','[  OK  ] ','         '):
            for verb in ('Starting','Stopping','Started','Finished','Stopped'):
                punctuation='...'if verb in ('Starting','Stopping')else'.'
                line=prefix+verb+' '+UNIT+' - '+DESCRIPTION+punctuation
                for timestamp in ('','2026-10-10T18:00:00.1234567Z '):
                    raw=(timestamp+line+'\r\n').encode();stream=io.StringIO()
                    with contextlib.redirect_stdout(stream):self.assertIs(S.external_text(raw),raw)
                    self.assertEqual(stream.getvalue(),'')
        raw=('[ 1.234] systemd[1]: '+UNIT+': Deactivated successfully.\n').encode()
        self.assertIs(S.external_text(raw),raw)

    def test_tty7_arbitrary_email_description_or_context_mutations_remain_fatal(self):
        original='[ 1.234] systemd[1]: Started '+UNIT+' - '+DESCRIPTION+'.'
        for value in (original.replace('tty6','tty7'),original.replace(UNIT,'private@example.invalid'),
            original.replace(DESCRIPTION,'Getty on tty7'),original.replace(UNIT,UNIT+'.extra'),
            'private-prefix '+original,original+' extra',UNIT,'Stopped '+UNIT,
            original.replace('systemd[1]','systemd[2]'),original.replace('Started ','Started secret=')):
            with self.subTest(value=value):self.rejected(value)

    def test_sgr_inside_token_split_terminal_and_private_terminal_payloads_remain_fatal(self):
        original='[ 1.234] systemd[1]: Started '+UNIT+' - '+DESCRIPTION+'.'
        for value in (original.replace('getty@','get\x1b[31mty@'),
            original.replace('getty@','get\x1b[2Jty@'),
            original.replace('getty@','get\x1b]0;private\x07ty@'),
            original+'\x1b]0;password=private\x07',original+'\x1bPtoken=private\x1b\\'):
            with self.subTest(value=value):self.rejected(value)

    def test_safe_context_decoration_is_allowed_but_private_suffix_or_record_is_not(self):
        original='[ 1.234] systemd[1]: Started '+UNIT+' - '+DESCRIPTION+'.'
        decorated=original.replace('Started','\x1b[32mStarted\x1b[0m')
        raw=(decorated+'\n').encode();self.assertIs(S.external_text(raw),raw)
        for value in (decorated+' password=private',decorated+'\nAuthorization: Bearer private',
            decorated+'\nתמלול:private',decorated+'\nprivate@example.invalid'):
            with self.subTest(value=value):self.rejected(value)

    def test_original_ten_tuple_order_is_retained_and_only_getty6_is_added(self):
        old=ROOT/'tests/fixtures/external-canonical-unit-cases.json';d=json.loads(old.read_bytes())
        historical=tuple((value['unit'],value['description'])for value in d['cases'])
        self.assertEqual(tuple(row for row in S.CANONICAL_UNITS if row!=(UNIT,DESCRIPTION)),historical)
        self.assertEqual(S.CANONICAL_UNITS.count((UNIT,DESCRIPTION)),1);self.assertEqual(len(S.CANONICAL_UNITS),11)
        self.assertEqual(hashlib.sha256(old.read_bytes()).hexdigest(),json.loads(FIXTURE.read_bytes())['original_ten_unit_fixture']['sha256'])

if __name__=='__main__':unittest.main()
