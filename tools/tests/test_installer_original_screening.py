"""Installer workflow uploads must retain original UART bytes or fail closed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCANNER = ROOT/'tools/native-functional/screen-evidence.py'
spec = importlib.util.spec_from_file_location('installer_original_screening', SCANNER)
screen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(screen)
PUBLIC = ROOT/'tools/tests/fixtures/external-public-log-37971533836.txt'
ACTIVE = ROOT/'tools/tests/fixtures/external-active-useradd-source.json'
WORKFLOWS = ('installer-candidate-20261009.yml', 'installer-active-candidate-20261009.yml')


class InstallerOriginalScreeningTests(unittest.TestCase):
    def rejected(self, content):
        with self.assertRaisesRegex(RuntimeError, 'Sensitive text|Incomplete terminal escape'):
            screen.external_text(content)

    def command(self, name):
        # Execute the checked-in screening command, so a omitted/wrong mode
        # in either real workflow fails byte identity instead of a regex check.
        lines = [line.strip() for line in (ROOT/'.github/workflows'/name).read_text().splitlines()
                 if 'execution/tools/native-functional/screen-evidence.py ' in line]
        self.assertEqual(len(lines), 1)
        return lines[0]

    def test_both_actual_workflow_commands_preserve_complete_live_and_installed_serial(self):
        for workflow in WORKFLOWS:
            with self.subTest(workflow=workflow), tempfile.TemporaryDirectory() as temp:
                base = Path(temp)
                (base/'execution').symlink_to(ROOT, target_is_directory=True)
                source = base/'arctic-installer/evidence'
                source.mkdir(parents=True)
                originals = {'host/serial.log': PUBLIC.read_bytes(),
                    'host/serial-installed.log': b'[  OK  ] Reached target Graphical Interface.\r\n',
                    'capture.png': b'bounded synthetic capture control',
                    'execution.json': b'{"status":"source-control-only"}\n'}
                for name, content in originals.items():
                    path = source/name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                result = subprocess.run(['/bin/bash', '-c', self.command(workflow)], cwd=base,
                    env=dict(os.environ, RUNNER_TEMP=str(base)), capture_output=True, timeout=15)
                self.assertEqual(result.returncode, 0, result.stderr.decode())
                target = base/'arctic-installer/screened'
                receipt = json.loads((target/'upload-screening.json').read_text())
                self.assertEqual(set(receipt['files']), set(originals))
                for name, content in originals.items():
                    self.assertEqual((target/name).read_bytes(), content)
                    sha = hashlib.sha256(content).hexdigest()
                    self.assertEqual(receipt['files'][name], dict(original_sha256=sha,
                        uploaded_sha256=sha, bytes=len(content), redactions=0))

    def test_cli_default_remains_the_generic_redacting_mode(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp)/'owned', Path(temp)/'screened'
            source.mkdir()
            (source/'serial.log').write_bytes(PUBLIC.read_bytes())
            result = subprocess.run([sys.executable, '-B', str(SCANNER), '--source', str(source),
                '--out', str(target)], capture_output=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr.decode())
            self.assertEqual(len((target/'serial.log').read_bytes()), 5964)
            receipt = json.loads((target/'upload-screening.json').read_text())['files']['serial.log']
            self.assertEqual(receipt['redactions'], 62)
            self.assertNotEqual(receipt['original_sha256'], receipt['uploaded_sha256'])

    def test_workflow_private_text_aborts_without_partial_upload_or_private_errors(self):
        for workflow in WORKFLOWS:
            for private in (b'Transcript: private English control', 'תמלול: private Hebrew control'.encode(),
                            b'\x1bPapi_key=private-dcs-control\x1b\\', b'password=private-value-control'):
                with self.subTest(workflow=workflow, private=private), tempfile.TemporaryDirectory() as temp:
                    base = Path(temp)
                    (base/'execution').symlink_to(ROOT, target_is_directory=True)
                    source = base/'arctic-installer/evidence'
                    source.mkdir(parents=True)
                    (source/'a-public.log').write_bytes(PUBLIC.read_bytes())
                    (source/'z-private.log').write_bytes(private)
                    result = subprocess.run(['/bin/bash', '-c', self.command(workflow)], cwd=base,
                        env=dict(os.environ, RUNNER_TEMP=str(base)), capture_output=True, timeout=15)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse((base/'arctic-installer/screened').exists())
                    self.assertNotIn(private, result.stdout + result.stderr)
                    self.assertEqual((source/'z-private.log').read_bytes(), private)

    def test_active_useradd_fixture_records_real_renderer_and_source_limits(self):
        fixture = json.loads(ACTIVE.read_text())
        content = fixture['expected_record'].encode()
        self.assertEqual(hashlib.sha256(content).hexdigest(), fixture['expected_record_sha256'])
        self.assertEqual(content, (screen.ACTIVE_USERADD + '\n').encode())
        self.assertEqual(fixture['source_commit'], '6078921fb122c301edf3e2cf3c467f21765e77f9')
        self.assertIn('no target ISO or runtime attestation', fixture['scope'])
        # Bind the renderer's ownership rules to actual source, including the
        # active harness fixed identity and the real password redaction label.
        runner = (ROOT/'internal/installer/runner.go').read_text()
        installer = (ROOT/'internal/installer/installer.go').read_text()
        active = (ROOT/'tools/installer-qualification/active-guest.py').read_text()
        self.assertIn('parts = append(parts, "[secret: "+c.SecretLabel+"]")', runner)
        self.assertIn('Redact: []int{len(args) - 2}, SecretLabel: "password hash"', installer)
        self.assertIn("payload['full_name'] == 'Arctic Qualification'", active)
        self.assertIn("payload['username'] == 'arcticqual'", active)
        self.assertIs(screen.external_text(content), content)
        timestamped = b'2026-10-09T23:30:00.1234567Z ' + content
        self.assertIs(screen.external_text(timestamped), timestamped)

    def test_active_mask_never_accepts_other_accounts_real_values_or_adjacent_private_text(self):
        content = json.loads(ACTIVE.read_text())['expected_record'].encode()
        for altered in (content.replace(b'arcticqual', b'private-user'),
                content.replace(b"'Arctic Qualification'", b"'Private Name'"),
                content.replace(b'/mnt', b'/private'), content.replace(b'/usr/bin/fish', b'/bin/bash'),
                content.replace(b'--create-home', b'--extra-private-flag'),
                content.replace(b'[secret: password hash]', b'[secret: private]'),
                content.replace(b'[secret: password hash]', b'[secret: disk passphrase]'),
                content.replace(b'[secret: password hash]', b'$6$synthetic-real-hash-control'),
                content.replace(b'[secret: password hash]', b'private-password-control'),
                content.rstrip(b'\n') + b' api_key=private\n', content + b'password=private\n',
                content + b'\x1bPtoken=private\x1b\\', content + b'Transcript: private\n',
                content + 'תמלול: private\n'.encode()):
            with self.subTest(altered=altered):
                self.rejected(altered)
        mask = b'[secret: password hash]'
        for index in range(1, len(mask)):
            for escape in (b'\x1b[0m', b'\x1b[2J', b'\x1b]0;public\x07', b'\x1bPpublic\x1b\\'):
                self.rejected(content.replace(mask, mask[:index] + escape + mask[index:]))

    def test_free_form_transport_credentials_remain_rejected(self):
        # Until a separately reviewed producer/schema projection removes the
        # ambiguous credential key, a hex token remains a sensitive token.
        for content in (b'{"token":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
                        b'{"ocr":"Password:"}', b'{"api_key":"private"}'):
            self.rejected(content)


if __name__ == '__main__':
    unittest.main()
