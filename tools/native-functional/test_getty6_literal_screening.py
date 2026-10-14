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

BACKEND_OBSERVER_ADDITIONS = (
    b"WRITE_OBSERVATION_LABELS = (\n    ('bytes', ('true', 'false', 'unknown')),\n    ('operations', ('true', 'false', 'unknown')),\n    ('clock', ('true', 'false', 'unknown')),\n    ('vm', ('running', 'not-running', 'process-exited', 'unknown')),\n    ('phase', ('vt-away', 'output-disconnect', 'output-restore', 'unknown')),\n    ('cycle', ('zero', 'unknown')),\n)\nDIAGNOSTIC_CODES = DIAGNOSTIC_CODES | frozenset(\n    'installer-inner-driver-collect-write-' + field + '-' + label\n    for field, labels in WRITE_OBSERVATION_LABELS for label in labels)\n",
    b"def write_observation_codes(error, controller_source):\n    if collection_guard_code(error, controller_source) != 'installer-inner-driver-collect-guard-collection-034':\n        return ()\n    observation = error.__dict__.get('_arctic_installer_write_observation')\n    source = controller_source.__dict__\n    if type(observation) is not tuple or len(observation) != 7 or observation[0] is not source.get('_COLLECTION_GUARD_TOKEN'):\n        return ()\n    if not all(type(value) is str and value in labels\n            for value, (_, labels) in zip(observation[1:], WRITE_OBSERVATION_LABELS)):\n        return ()\n    return tuple('installer-inner-driver-collect-write-' + field + '-' + value\n                 for value, (field, _) in zip(observation[1:], WRITE_OBSERVATION_LABELS))\n\n\n",
    b"            if code == 'installer-inner-driver-collect-guard-collection-034':\n                try:\n                    observed = write_observation_codes(error, controller_source)\n                except Exception:\n                    observed = ()\n                for observation in observed:\n                    print('ARCTIC-INSTALLER-INNER ' + token + ' ' + observation, flush=True)\n",
)

INSTALLED_IDENTITY_START = b'def installed_user_command(nonce):\n'
INSTALLED_IDENTITY_END = b'def boot_installed(vm, startup, vmtest, out, context):\n'
INSTALLED_IDENTITY_BYTES = 6485
INSTALLED_IDENTITY_SHA256 = '3388566f940b0733a1eff0da5da2b13fd8aaf64de9a29a0d36b91bf0abdbdd70'
IDENTITY_OBSERVER_ADDITIONS = (
    b'''_IDENTITY_OBSERVATION_TOKEN = object()
IDENTITY_OBSERVATION_LABELS = (
    ('record-count', ('one', 'multiple')),
    ('token-count', ('zero', 'one', 'two', 'three', 'four', 'five-or-more')),
    ('expected-length', ('shorter', 'equal', 'longer')),
    ('prefix-exact', ('true', 'false')),
    ('nonce-exact', ('true', 'false')),
    ('uid-exact', ('true', 'false')),
    ('user-exact', ('true', 'false')),
)
DIAGNOSTIC_CODES = DIAGNOSTIC_CODES | frozenset(
    'installer-inner-driver-installed-proof-identity-' + field + '-' + label
    for field, labels in IDENTITY_OBSERVATION_LABELS for label in labels)
''',
    b'def identity_observation_codes(error):\n'
    b'    """Project only source-minted closed facts about a rejected OCR record."""\n'
    b'    if type(error) is not RuntimeError or type(error.args) is not tuple or len(error.args) != 1 or \\\n'
    b"            type(error.args[0]) is not str or error.args[0] != 'installed user identity response differs':\n"
    b'        return ()\n'
    b"    observation = error.__dict__.get('_arctic_installer_identity_observation')\n"
    b'    if type(observation) is not tuple or len(observation) != 1 + len(IDENTITY_OBSERVATION_LABELS) or \\\n'
    b'            observation[0] is not _IDENTITY_OBSERVATION_TOKEN:\n'
    b'        return ()\n'
    b'    if not all(type(value) is str and value in labels\n'
    b'            for value, (_, labels) in zip(observation[1:], IDENTITY_OBSERVATION_LABELS)):\n'
    b'        return ()\n'
    b"    return tuple('installer-inner-driver-installed-proof-identity-' + field + '-' + value\n"
    b'                 for value, (field, _) in zip(observation[1:], IDENTITY_OBSERVATION_LABELS))\n'
    b'\n'
    b'\n',
    b'''            if code == 'installer-inner-driver-installed-proof-identity-response-differs':
                try:
                    observed = identity_observation_codes(error)
                except Exception:
                    observed = ()
                for observation in observed:
                    print('ARCTIC-INSTALLER-INNER ' + token + ' ' + observation, flush=True)
''',
)
INSTALLED_PROOF_REPLACEMENTS = (
    (b"    'driver-installed-proof': (('fresh installed login display did not appear', 'login-absent'),\n"
     b"        ('fresh installed proof did not complete', 'proof-incomplete'),\n"
     b"        ('fresh installed console was not visible', 'console-absent'),\n"
     b"        ('exact console prompt was not observed; secret input refused', 'password-prompt-absent'),\n"
     b"        ('installed user login did not reach its identity challenge', 'identity-login-failed'),\n"
     b"        ('installed user identity response differs', 'identity-response-differs'),\n"
     b"        ('installed user identity deadline exceeded', 'identity-deadline'),\n"
     b"        ('installed user identity challenge was not issued; sudo input refused', 'identity-challenge-not-sent'),\n"
     b"        ('exact installed user identity was not observed after exact prompt; sudo input refused', 'identity-response-after-prompt-absent'),\n"
     b"        ('exact installed user identity was not observed after readiness fallback; sudo input refused', 'identity-response-after-fallback-absent'),\n"
     b"        ('installed guest proof failed', 'helper-failed'),\n"
     b"        ('fresh installed authentication/receipt is ambiguous', 'helper-ambiguous'),\n"
     b"        ('fresh installed helper context/authentication differs', 'helper-binding')),\n",
     b"    'driver-installed-proof': (('fresh installed login display did not appear', 'login-absent'),\n"
     b"        ('fresh installed proof did not complete', 'proof-incomplete')),\n"),
    (b"    nonce = uuid.uuid4().hex\n"
     b"    shell = console_user_identity(vm,startup,out,nonce,password)\n",
     b"    shell = console_prompt(vm,startup,out,'installed-login-shell','arcticqual@arctic-qual ~ >',password,archive=False)\n"
     b"    nonce = uuid.uuid4().hex\n"),
    (b"                login_shell=shell,\n",
     b"                login_shell={key: shell[key] for key in ('prompt_kind','observed_line_sha256','observed_ns')},\n"),
)


def restore_identity_observer(driver):
    """Remove each complete closed observer addition and reject near matches."""
    for addition in IDENTITY_OBSERVER_ADDITIONS:
        if driver.count(addition) != 1:
            raise AssertionError('Expected one exact installed identity observer addition')
        driver = driver.replace(addition, b'', 1)
    return driver


def restore_installed_proof(driver):
    """Remove only the exact installed-proof additions before older inverses."""
    driver = restore_identity_observer(driver)
    if driver.count(INSTALLED_IDENTITY_START) != 1 or driver.count(INSTALLED_IDENTITY_END) != 1:
        raise AssertionError('Expected one exact installed identity block')
    start = driver.index(INSTALLED_IDENTITY_START)
    end = driver.index(INSTALLED_IDENTITY_END, start)
    block = driver[start:end]
    if len(block) != INSTALLED_IDENTITY_BYTES or hashlib.sha256(block).hexdigest() != INSTALLED_IDENTITY_SHA256:
        raise AssertionError('Installed identity block bytes differ')
    driver = driver[:start] + driver[end:]
    for current, original in INSTALLED_PROOF_REPLACEMENTS:
        if driver.count(current) != 1:
            raise AssertionError('Expected one exact installed proof replacement')
        driver = driver.replace(current, original, 1)
    return driver

def restore_backend_write_observer(driver):
    """Remove only three exact source additions; preserve historical bytes."""
    for addition in BACKEND_OBSERVER_ADDITIONS:
        if driver.count(addition)!=1:raise AssertionError("Expected one exact backend observer addition")
        driver=driver.replace(addition,b"",1)
    return driver

def restore_bounded_collection_observer(driver):
    """Strict test-only inverse; retain the entire historical fixture hash."""
    driver=restore_installed_proof(driver)
    driver=restore_backend_write_observer(driver)
    for current,original in (
        (b"            # The outer runner independently validates the complete private\n"
         b"            # UART, then replaces this marker with a receipt for its bounded\n"
         b"            # public protocol projection.  Never retain a digest of private\n"
         b"            # console text as a dictionary oracle.\n"
         b"            return report, dict(status='private_uart_validated_pending_public_projection'), prompts\n",
         b"            return report, dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest()), prompts\n"),
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

    def test_backend_inverse_rejects_each_mutated_duplicate_or_missing_addition(self):
        driver=(ROOT/'installer-qualification/driver.py').read_bytes()
        expected=json.loads(FIXTURE.read_bytes())['fixture_source']['source_sha256']
        self.assertEqual(hashlib.sha256(restore_bounded_collection_observer(driver)).hexdigest(),expected)
        for addition in BACKEND_OBSERVER_ADDITIONS:
            for mutant in (driver.replace(addition,addition+b'# changed known addition\n',1),
                    driver.replace(addition,b'',1),driver+addition):
                with self.subTest(addition=addition[:40],bytes=len(mutant)),self.assertRaises(AssertionError):
                    # An unapproved byte adjacent to a known addition must also
                    # fail the unchanged whole historical hash after inversion.
                    restored=restore_bounded_collection_observer(mutant)
                    self.assertEqual(hashlib.sha256(restored).hexdigest(),expected)
        self.assertIn("for key in ('ctrl', 'alt', 'f6')",restore_bounded_collection_observer(driver).decode())

    def test_installed_proof_inverse_rejects_mutated_duplicate_or_missing_additions(self):
        driver=(ROOT/'installer-qualification/driver.py').read_bytes()
        expected=json.loads(FIXTURE.read_bytes())['fixture_source']['source_sha256']
        self.assertEqual(hashlib.sha256(restore_bounded_collection_observer(driver)).hexdigest(),expected)
        start=driver.index(INSTALLED_IDENTITY_START);end=driver.index(INSTALLED_IDENTITY_END,start)
        block=driver[start:end]
        mutants=(
            driver[:start]+block.replace(b'1280,720',b'1280,721',1)+driver[end:],
            driver[:start]+driver[end:],
            driver+block,
        )
        for current,_original in INSTALLED_PROOF_REPLACEMENTS:
            mutants += (driver.replace(current,current+b'# changed known addition\n',1),
                        driver.replace(current,b'',1),driver+current)
        for mutant in mutants:
            with self.subTest(bytes=len(mutant)),self.assertRaises(AssertionError):
                restored=restore_bounded_collection_observer(mutant)
                self.assertEqual(hashlib.sha256(restored).hexdigest(),expected)

    def test_identity_observer_inverse_rejects_mutated_duplicate_or_missing_additions(self):
        driver=(ROOT/'installer-qualification/driver.py').read_bytes()
        expected=json.loads(FIXTURE.read_bytes())['fixture_source']['source_sha256']
        self.assertEqual(hashlib.sha256(restore_bounded_collection_observer(driver)).hexdigest(),expected)
        for addition in IDENTITY_OBSERVER_ADDITIONS:
            mutants=(driver.replace(addition,addition+b'# changed known identity observer addition\n',1),
                     driver.replace(addition,b'',1),driver+addition)
            for mutant in mutants:
                with self.subTest(addition=addition[:48],bytes=len(mutant)),self.assertRaises(AssertionError):
                    restored=restore_bounded_collection_observer(mutant)
                    self.assertEqual(hashlib.sha256(restored).hexdigest(),expected)

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
