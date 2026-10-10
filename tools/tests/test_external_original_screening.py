"""Preserve attested public spans without redacting original paired evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import tracemalloc
import unittest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('external_original_screening',
    ROOT/'tools/native-functional/screen-evidence.py')
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)

# Verbatim selected records from the unscreened public job 37971533836,
# source SHA256 3c3597fc1cfbc71a7b35b295cd8b12bab055a9db3e76867e7b24886e5375b2f0.
# Original one-based lines: 388,396,398,399,402-414,417-429,437,441,708,710,713,715.
FIXTURE = ROOT/'tools/tests/fixtures/external-public-log-37971533836.txt'
FIXTURE_SHA = 'f62599c94e94599972400fe08dff19347927b677d75bf9b10ff31ec9c9a3953b'
# These source-owned placeholder lines are unchanged by the original generic
# sanitizer: none matches its SENSITIVE regex (asserted below). Selected from
# producer37903438836's already-screened, verified complete installation logs:
# baseline lines1189/1192, uploaded SHA19ef70097da3247fe8e7ab775de570d52efe8df899efb94694e03b9fe41b7297;
# candidate lines1141/1144, uploaded SHA21005f9b1fa4a2cdf51709b578678960c8bf07a59d86db94d08c0a61258a1706.
# Whole original files are unavailable; no deleted substring is reconstructed.
MASK_FIXTURE = ROOT/'tools/tests/fixtures/external-public-masks-37903438836.txt'
MASK_FIXTURE_SHA = '15e42c79c0a94bdcd42aa1d117b77891d6b0875bde1a215a5934cd038ce8da42'
CANONICAL_FIXTURE = ROOT/'tools/tests/fixtures/external-canonical-unit-cases.json'
CANONICAL_FIXTURE_SHA = '273a9a9fe3652b8b25446164c72d8f4b36b3b3ac436a9a64dc4b74e32aa554c5'


def dns(url):
    return ('>>> Curl error (6): Could not resolve hostname for ' + url +
        ' [Could not resolve host: mirrors.fedoraproject.org] - ' + url + '\n').encode()


class ExternalOriginalScreeningTests(unittest.TestCase):
    def rejected(self, content):
        with self.assertRaisesRegex(RuntimeError, 'Sensitive text|Incomplete terminal escape'):
            screen.external_text(content)

    def test_all_36_original_public_records_and_ansi_are_byte_identical(self):
        content = FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), FIXTURE_SHA)
        self.assertEqual(len(content.splitlines()), 36)
        self.assertIn(b'\x1b[0;1;39m', content)
        self.assertIs(screen.external_text(content), content)
        # UART records have the same message without the Actions timestamp.
        uart = b''.join(line.split(b' ', 1)[1] for line in content.splitlines(keepends=True))
        self.assertIs(screen.external_text(uart), uart)

    def test_directory_keeps_all_original_bytes_and_zero_redaction_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'owned', Path(temp)/'screened'
            source.mkdir()
            originals = {'serial-install.log': FIXTURE.read_bytes(),
                'execution.json': b'{"status":"synthetic-control-only"}\n',
                'capture.png': b'bounded synthetic binary control'}
            for name, content in originals.items():
                (source/name).write_bytes(content)
            screen.screen_external(source, target)
            receipt = json.loads((target/'upload-screening.json').read_text())
            self.assertEqual(set(receipt['files']), set(originals))
            for name, content in originals.items():
                self.assertEqual((target/name).read_bytes(), content)
                sha = hashlib.sha256(content).hexdigest()
                self.assertEqual(receipt['files'][name], dict(original_sha256=sha,
                    uploaded_sha256=sha, bytes=len(content), redactions=0))

    def test_unknown_match_in_later_member_aborts_without_partial_output(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'owned', Path(temp)/'screened'
            source.mkdir()
            (source/'a-public.log').write_bytes(FIXTURE.read_bytes())
            private = b'Transcript: private Hebrew control \xd7\xa9\xd7\x9c\xd7\x95\xd7\x9d\n'
            (source/'z-private.log').write_bytes(private)
            with self.assertRaisesRegex(RuntimeError, 'Sensitive text'):
                screen.screen_external(source, target)
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(temp).iterdir()), [source])
            self.assertEqual((source/'z-private.log').read_bytes(), private)

    def test_generic_other_vm_screening_retains_original_behavior(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'owned', Path(temp)/'screened'
            source.mkdir()
            content = dns(screen.FEDORA_METADATA[0])
            (source/'serial.log').write_bytes(content)
            screen.screen(source, target)
            self.assertIn(b'[redacted]', (target/'serial.log').read_bytes())
            receipt = json.loads((target/'upload-screening.json').read_text())
            self.assertEqual(receipt['files']['serial.log']['redactions'], 2)

    def test_fedora_query_host_userinfo_port_fragment_encoding_variations_rejected(self):
        original = screen.FEDORA_METADATA[0]
        variants = (
            original + '&token=private', original + '#private', original + '/private',
            original.replace('repo=fedora-44', 'repo=private'),
            original.replace('arch=x86_64', 'arch=x86_64&arch=x86_64'),
            original.replace('https://', 'http://'),
            original.replace('mirrors.fedoraproject.org', 'mirrors.fedoraproject.org.evil'),
            original.replace('mirrors.fedoraproject.org', 'mirrors.fedoraproject.org:443'),
            original.replace('https://', 'https://private@'),
            original.replace('https://', 'https://private%40secret@'),
            original.replace('fedora-44', 'fedora%2d44'),
            original.replace('repo=', 'secret=private&repo='),
            original.replace('arch=x86_64', 'arch=x86_64?private'),
        )
        for url in variants:
            with self.subTest(url=url):
                self.rejected(dns(url))

    def test_metadata_tokens_require_exact_observed_context(self):
        for url in screen.FEDORA_METADATA:
            for content in (url.encode() + b'\n', b'ordinary public URL: ' + url.encode(),
                    dns(url).replace(b'Curl error (6)', b'Curl error (9)'),
                    dns(url).replace(b'mirrors.fedoraproject.org]', b'private.example]')):
                with self.subTest(content=content):
                    self.rejected(content)
    def test_connect_latency_only_varies_as_a_bounded_decimal_field(self):
        actual = next(line for line in FIXTURE.read_bytes().splitlines(keepends=True)
            if b'Curl error (7)' in line)
        for latency in (b'0', b'5', b'999999'):
            content = actual.replace(b'after 2 ms', b'after ' + latency + b' ms')
            self.assertIs(screen.external_text(content), content)
        for latency in (b'1000000', b'-1', b'02', b'2 token=private', b'private'):
            self.rejected(actual.replace(b'after 2 ms', b'after ' + latency + b' ms'))

    def test_only_source_owned_placeholder_in_exact_benchmark_command_is_public(self):
        actual = next(line for line in FIXTURE.read_bytes().splitlines(keepends=True)
            if b'$ useradd ' in line)
        self.assertIs(screen.external_text(actual), actual)
        for content in (b'secret: password hash', b'[secret: password hash]',
                actual.replace(b'[secret: password hash]', b'[secret: private]'),
                actual.replace(b'[secret: password hash]', b'[secret: disk passphrase]'),
                actual.replace(b'[secret: password hash]', b'private-password'),
                actual.replace(b"'Arctic CI'", b"'Private Name'"),
                actual.replace(b'password hash]', b'password\x1b[0m hash]'),
                actual.replace(b'[secret:', b'[\x1b[0msecret:'),
                actual.rstrip(b'\n') + b' token=private\n', actual + b'password=private\n'):
            with self.subTest(content=content):
                self.rejected(content)

    def test_both_existing_encrypted_installations_preserve_source_owned_stdin_masks(self):
        content = MASK_FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), MASK_FIXTURE_SHA)
        self.assertEqual(len(content.splitlines()), 4)
        self.assertIsNone(screen.SENSITIVE.search(content.decode()))
        self.assertIs(screen.external_text(content), content)
        for line in content.splitlines(keepends=True):
            self.assertIs(screen.external_text(line), line)

    def test_stdin_masks_require_exact_owned_disk_command_and_literal_proof(self):
        actual = MASK_FIXTURE.read_bytes().splitlines(keepends=True)
        for line in actual:
            for content in (line.replace(b'/dev/vda4', b'/dev/private4'),
                    line.replace(b'[secret: disk passphrase]', b'[secret: private]'),
                    line.replace(b'[secret: disk passphrase]', b'private-passphrase'),
                    line.replace(b'[secret: disk passphrase]', b'[secret: password hash]'),
                    line.replace(b'[secret: disk passphrase]', b'[secret: disk\x1b[0m passphrase]'),
                    line.replace(b'[secret: disk passphrase]', b'[secret: disk passphrase\x1b[0m]'),
                    line.replace(b'cryptsetup ', b'cryptsetup --injected-flag '),
                    line.rstrip(b'\r\n') + b' https://private.example?secret=value\n',
                    line + b'password=private\n'):
                with self.subTest(content=content):
                    self.rejected(content)
        opened = next(line for line in actual if b'cryptsetup open ' in line)
        for uuid in (b'private', b'00000000-0000-0000-0000-000000000000',
                b'00000000-0000-4000-c000-000000000000'):
            import re
            self.rejected(re.sub(rb'luks-[0-9a-f-]{36}', b'luks-' + uuid, opened))
        self.rejected(b'[secret: disk passphrase]')

    def test_canonical_cases_bind_the_package_inventory_and_explicit_limits(self):
        content = CANONICAL_FIXTURE.read_bytes()
        self.assertEqual(hashlib.sha256(content).hexdigest(), CANONICAL_FIXTURE_SHA)
        data = json.loads(content)
        self.assertEqual(tuple((case['unit'], case['description']) for case in data['cases']),
            tuple(row for row in screen.CANONICAL_UNITS if row != ('getty@tty6.service', 'Getty on tty6')))
        self.assertEqual(len(data['cases']), 10)
        self.assertEqual(data['source_proposal_sha256'],
            '8264929e394d500093487c61882c518a4bea08111304b3f9ceaed27ded7f3cc2')
        for package in data['packages'].values():
            self.assertEqual((package['version'], package['release'], package['file_digest_algorithm']),
                ('259.9', '1.fc44', 8))
        self.assertTrue(any('not proof of target ISO runtime' in limit for limit in data['limits']))
        self.assertTrue(any('signatures not independently verified' in limit for limit in data['limits']))
        self.assertTrue(any('No omitted historical raw token was reconstructed' in limit for limit in data['limits']))

    def test_all_ten_literals_preserve_bounded_systemd_lifecycle_and_deactivation_records(self):
        records = []
        for unit, description in screen.CANONICAL_UNITS:
            for verb in ('Starting', 'Started', 'Finished', 'Stopping', 'Stopped'):
                punctuation = '...' if verb in ('Starting', 'Stopping') else '.'
                for prefix in ('[ 1.234] systemd[1]: ', '[  OK  ] ', '         '):
                    line = prefix + verb + ' \x1b[0;1;39m' + unit + '\x1b[0m - ' + description + punctuation
                    for timestamp in ('', '2026-10-09T18:34:30.1234567Z '):
                        content = (timestamp + line + '\r\n').encode()
                        self.assertIs(screen.external_text(content), content)
                    records.append((line + '\n').encode())
            content = ('[ 1.234] systemd[1]: ' + unit + ': Deactivated successfully.\n').encode()
            self.assertIs(screen.external_text(content), content)
            records.append(content)
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'owned', Path(temp)/'screened'
            source.mkdir()
            content = b''.join(records)
            (source/'full-canonical-control.log').write_bytes(content)
            screen.screen_external(source, target)
            self.assertEqual((target/'full-canonical-control.log').read_bytes(), content)
            sha = hashlib.sha256(content).hexdigest()
            receipt = json.loads((target/'upload-screening.json').read_text())['files']['full-canonical-control.log']
            self.assertEqual(receipt, dict(original_sha256=sha, uploaded_sha256=sha, bytes=len(content), redactions=0))

    def test_unknown_canonical_instances_descriptions_suffixes_or_contexts_reject(self):
        for unit, description in screen.CANONICAL_UNITS:
            original = '[ 1.234] systemd[1]: Finished ' + unit + ' - ' + description + '.'
            variants = (original.replace(unit, 'private@unknown.service'),
                original.replace(unit, 'real.email@example.service'),
                original.replace(unit, '39m' + unit), original.replace(unit, unit + '.private'),
                original.replace(unit, unit.replace('.service', '.Service')),
                original.replace(description, 'Private description'),
                original.replace('systemd[1]', 'systemd[2]'),
                original.replace('Finished', 'UnexpectedStatus'),
                original.replace(' - ', ': '), original + ' extra text', unit,
                original.replace('[ 1.234] systemd[1]: ', 'ordinary text: '))
            for variant_index, content in enumerate(variants):
                with self.subTest(unit=unit, content=content):
                    raw = content.encode()
                    # The separately reviewed exact configfs token is public
                    # without a lifecycle/description prerequisite. Its private
                    # affixes, case changes and every other unit remain rejected.
                    if unit == 'modprobe@configfs.service' and variant_index in (5, 6, 7, 8, 9, 10, 11):
                        self.assertIs(screen.external_text(raw), raw)
                    else:
                        self.rejected(raw)
        for unit, description in (('user@1001.service', 'User Manager for UID 1001'),
                ('user@01000.service', 'User Manager for UID 01000'),
                ('user-runtime-dir@0.service', 'User Runtime Directory /run/user/0'),
                ('getty@tty2.service', 'Getty on tty2'),
                ('serial-getty@ttyS1.service', 'Serial Getty on ttyS1'),
                ('modprobe@private.service', 'Load Kernel Module private'),
                ('modprobe@nvmet_tcp.service', 'Load Kernel Module nvmet_tcp'),
                ('modprobe@thunderbolt_net.service', 'Load Kernel Module thunderbolt_net')):
            self.rejected(('[ 1.234] systemd[1]: Finished ' + unit + ' - ' + description + '.').encode())

    def test_every_canonical_token_character_boundary_rejects_inserted_ansi(self):
        for unit, description in screen.CANONICAL_UNITS:
            for position in range(1, len(unit)):
                for escape in ('\x1b[0m', '\x1b[2J', '\x1b]0;control\x07', '\x1bPcontrol\x1b\\'):
                    decorated = unit[:position] + escape + unit[position:]
                    content = ('[ 1.234] systemd[1]: Finished ' + decorated + ' - ' + description + '.').encode()
                    with self.subTest(unit=unit, position=position, escape=escape):
                        self.rejected(content)

    def test_canonical_records_do_not_hide_adjacent_or_same_record_sensitive_values(self):
        controls = (b'real.email@example.service', b'Authorization: Bearer private',
            b'ghp_syntheticprivatecontrol', b'https://private.example?token=value',
            b'Transcript: private text', 'תמלול: טקסט פרטי'.encode())
        for unit, description in screen.CANONICAL_UNITS:
            public = ('[ 1.234] systemd[1]: Finished ' + unit + ' - ' + description + '.\n').encode()
            for control in controls:
                self.rejected(public + control + b'\n')
                self.rejected(public.rstrip(b'\n') + b' ' + control + b'\n')
                self.rejected(public + b'\x1b]0;' + control + b'\x07')

    def test_real_service_emails_and_unknown_unit_names_rejected(self):
        for unit in ('real.email@example.service', 'private@zram0.service',
                'systemd-zram-setup@zram1.service', '39msystemd-zram-setup@zram0.service',
                'systemd-zram-setup@zram0.service.private'):
            self.rejected(('[ 1.2] systemd[1]: Stopped ' + unit +
                ' - Create swap on /dev/zram0.\n').encode())

    def test_ansi_inside_token_is_not_an_exception_or_a_hidden_private_url(self):
        url = screen.FEDORA_METADATA[0]
        self.rejected(dns(url.replace('fedora-44', 'fedora-\x1b[0m44')))
        self.rejected(('[ 1.2] systemd[1]: Stopped ' +
            screen.ZRAM_UNIT.replace('@', '\x1b[0m@') +
            ' - Create swap on /dev/zram0.\n').encode())
        self.rejected(b'\x1b]8;;https://private.example?secret=value\x07public\n')

    def test_other_terminal_bookkeeping_is_preserved_and_not_skipped(self):
        content = b'ordinary \x1b[2Jterminal cursor command\n\x1b]3008;end=0123456789abcdef\x1b\\\n'
        self.assertIs(screen.external_text(content), content)
        self.rejected(content + b'Authorization: Bearer private\n')

    def test_large_plain_text_has_compact_escape_mapping_at_token_boundaries(self):
        unit = screen.ZRAM_UNIT
        record = '[ 1.2] systemd[1]: Stopped \x1b[0m\x1b[0;1;39m' + unit + '\x1b[0m - Create swap on /dev/zram0.\n'
        value = 'bounded plain diagnostic control ' + 'x ' * (4 * 1024 * 1024) + '\n' + record
        tracemalloc.start()
        try:
            view, boundaries, removed = screen.classification_view(value)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(len(boundaries), 3)
        self.assertEqual(len(removed), 3)
        self.assertEqual(boundaries.itemsize * len(boundaries) + removed.itemsize * len(removed), 24)
        self.assertLess(peak, 4 * len(value))  # A per-character Python-int map fails this bound.
        start = view.index(unit)
        original_start, original_end = screen.original_span(start, start + len(unit), boundaries, removed)
        self.assertEqual(value[original_start:original_end], unit)
        content = value.encode()
        self.assertIs(screen.external_text(content), content)

    def test_many_empty_records_do_not_allocate_a_per_record_list(self):
        content = b'\n' * (2 * 1024 * 1024)
        tracemalloc.start()
        try:
            self.assertIs(screen.external_text(content), content)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(peak, 4 * len(content))

    def test_sensitive_header_can_span_records_and_still_rejects(self):
        self.rejected(dns(screen.FEDORA_METADATA[0]) + b'Authorization:\nBearer private\n')

    def test_independent_sensitive_records_near_public_spans_are_not_skipped(self):
        public = dns(screen.FEDORA_METADATA[0])
        controls = (
            b'real.email@example.service', b'https://private.example?value=private',
            b'ghp_syntheticprivatecontrol', b'github_pat_syntheticprivatecontrol',
            b'AKIAABCDEFGHIJKLMNOP', b'Authorization: Bearer synthetic-private',
            b'password=synthetic-private', b'api_key: synthetic-private', b'token=synthetic-private',
            b'"access_token":"synthetic-private"', b'https://private@host/path',
            b'Transcript: synthetic private text', b'"transcription":"synthetic private text"',
            'תמלול: טקסט פרטי לבדיקה'.encode(), '"תמליל":"טקסט פרטי לבדיקה"'.encode(),
        )
        for control in controls:
            for content in (public + control + b'\n', public.rstrip(b'\n') + b' ' + control + b'\n'):
                with self.subTest(control=control):
                    self.rejected(content)

    def test_ansi_does_not_hide_independent_secret_or_transcript(self):
        for control in (b'ghp_\x1b[0msyntheticprivatecontrol',
                b'Trans\x1b[0mcript: private text',
                b'private\x1b[0m@example.service',
                b'api_\x1b[0mkey=private'):
            self.rejected(dns(screen.FEDORA_METADATA[0]) + control)

    def test_csi_osc_dcs_cannot_split_a_sensitive_label_or_token(self):
        separators = (b'\x1b[2J', b'\x1b]3008;end=0123456789abcdef\x1b\\',
            b'\x1b]0;synthetic-title\x07', b'\x1bPsynthetic-bookkeeping\x1b\\')
        controls = ((b'ghp_', b'syntheticprivatecontrol'),
            (b'Trans', b'cript: private text'), (b'Author', b'ization: Bearer private'),
            ('תמ'.encode(), 'לול: טקסט פרטי'.encode()))
        for separator in separators:
            for prefix, suffix in controls:
                with self.subTest(separator=separator, prefix=prefix):
                    self.rejected(dns(screen.FEDORA_METADATA[0]) + prefix + separator + suffix)

    def test_terminal_payload_secrets_are_scanned_before_bookkeeping_removal(self):
        for frame in (b'\x1b]0;token=private\x07',
                b'\x1b]0;Transcript: private text\x1b\\',
                b'\x1bPAuthorization: Bearer private\x1b\\',
                b'\x1bPhttps://private.example?token=value\x1b\\'):
            self.rejected(dns(screen.FEDORA_METADATA[0]) + frame)

    def test_string_introducers_do_not_hide_boundary_adjacent_credential_labels(self):
        public = (dns(screen.FEDORA_METADATA[0]),
            ('[ 1.2] systemd[1]: Stopped ' + screen.ZRAM_UNIT +
                ' - Create swap on /dev/zram0.\n').encode(),
            b'[ 1.2] systemd[1]: Finished modprobe@drm.service - Load Kernel Module drm.\n',
            b'ordinary bounded control\n')
        labels = (b'password', b'passwd', b'token', b'access_token', b'refresh_token',
            b'api_key', b'client_secret', b'secret')
        for prefix in public:
            for intro in (b'P', b'X', b'_', b'^', b']0;'):
                for label in labels:
                    payload = label + b'=synthetic_private'
                    frame = b'\x1b' + intro + payload + b'\x1b\\'
                    for content in (prefix + frame, prefix.rstrip(b'\n') + frame,
                            frame, prefix + frame + b'\n' + prefix):
                        with self.subTest(intro=intro, label=label):
                            self.rejected(content)

    def test_nested_incomplete_and_fe_string_frames_do_not_hide_credentials(self):
        public = b'[ 1.2] systemd[1]: Finished modprobe@drm.service - Load Kernel Module drm.\n'
        frames = (
            b'\x1bPapi_key=private', b'\x1bXpassword=private', b'\x1b_token=private',
            b'\x1b]0;api_key=private',
            b'\x1bPapi_\x1b[0mkey=private\x1b\\',
            b'\x1bPapi_\x1b[2Jkey=private\x1b\\',
            b'\x1bPapi_\x1b]0;control\x07key=private\x1b\\',
            b'\x1bPapi_\x1bc key=private\x1b\\',
            b'\x1bP\x1b]0;api_key=private\x07\x1b\\',
            b'\x1b]0;\x1bPapi_key=private\x1b\\\x07',
            b'\x1bcapi_key=private', b'\x1b#8api_key=private',
        )
        for frame in frames:
            self.rejected(public + frame)
            self.rejected(frame)

    def test_complete_benign_string_and_fe_bookkeeping_remains_byte_identical(self):
        public = b'[ 1.2] systemd[1]: Finished modprobe@drm.service - Load Kernel Module drm.\n'
        frames = (b'\x1bP+q544e\x1b\\', b'\x1bXsynthetic bookkeeping\x1b\\',
            b'\x1b_synthetic bookkeeping\x1b\\', b'\x1b^synthetic bookkeeping\x1b\\',
            b'\x1b]3008;end=0123456789abcdef\x1b\\', b'\x1b]0;synthetic title\x07',
            b'\x1bc', b'\x1b#8')
        for frame in frames:
            for content in (frame, public + frame + b'\n', frame + b'\n' + public):
                self.assertIs(screen.external_text(content), content)

    def test_incomplete_terminal_sequences_fail_closed(self):
        for frame in (b'\x1b', b'\x1b[', b'\x1b[2', b'\x1b]3008;end=control',
                b'\x1bPunterminated-bookkeeping', b'\x1b]0;malformed\n'):
            self.rejected(dns(screen.FEDORA_METADATA[0]) + frame)

    def test_unqueried_public_provenance_urls_keep_the_existing_scope(self):
        content = b'{"html_url":"https://github.com/yuvalkolodkingal/Arctic-Linux/actions/runs/37971533836"}\n'
        self.assertIs(screen.external_text(content), content)


if __name__ == '__main__':
    unittest.main()
