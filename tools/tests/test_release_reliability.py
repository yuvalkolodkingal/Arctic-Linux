"""Failure-path tests for release evidence; no QEMU, network or disks required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, mock_open, patch

ROOT = Path(__file__).resolve().parents[2]


def module(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/reliability' / filename)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


report = module('reliability_report', 'report.py')
fetch = module('reliability_fetch', 'fetch-iso.py')
guest = module('reliability_guest', 'guest.py')


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)

    def evidence(self, upgrade=False):
        (self.path / 'test.log').write_text('[123] boot stage: exit 0\n' +
                                          ('[456] post-upgrade boot stage: exit 0\n' if upgrade else ''))
        for stage, filename, extra in [('live', 'serial-install.log', ()),
                                       ('installed', 'serial-boot.log', ('upgrade',) if upgrade else ()),
                                       *([('installed', 'serial-upgrade.log', ('upgrade-transaction',))] if upgrade else [])]:
            lines = [report.PREFIX + json.dumps(dict(stage=stage, check=c, status='passed'))
                     for c in report.CHECKS + extra if not (stage == 'live' and c == 'app-editor')]
            if stage == 'live':
                lines.append('ARCTIC-INSTALL-EXIT=0')
            (self.path / filename).write_text('\r\n'.join(lines) + '\r\n')

    def automated(self, upgrade=False):
        return [r for r in report.evaluate(self.path, upgrade) if 'evidence' in r or r['check'] == 'evidence']

    def test_missing_logs_are_unrun_not_passed(self):
        self.assertTrue(all(r['status'] == 'unrun' for r in self.automated()))

    def test_complete_evidence_passes_but_manual_stays_unrun(self):
        self.evidence()
        self.assertTrue(all(r['status'] == 'passed' for r in self.automated()))
        self.assertTrue(any(r['status'] == 'unrun' for r in report.evaluate(self.path)))

    def test_failed_probe_fails(self):
        self.evidence()
        p = self.path / 'serial-boot.log'
        p.write_text(p.read_text().replace('"passed"', '"failed"', 1))
        self.assertTrue(any(r['status'] == 'failed' for r in self.automated()))

    def test_duplicate_probe_cannot_mask_failure(self):
        self.evidence()
        p = self.path / 'serial-boot.log'
        p.write_text(p.read_text() * 2)
        self.assertTrue(any(r['status'] == 'failed' for r in self.automated()))

    def test_collection_marker_alone_does_not_pass(self):
        (self.path / 'serial-boot.log').write_text('ARCTIC-COLLECT-END\n')
        self.assertTrue(all(r['status'] == 'unrun' for r in self.automated()))

    def test_malformed_json_fails(self):
        for value in ('{bad', '[]', '{"status":"maybe"}'):
            with self.subTest(value=value):
                (self.path / 'serial-boot.log').write_text(report.PREFIX + value)
                self.assertTrue(any(r['status'] == 'failed' for r in self.automated()))

    def test_upgrade_requires_transaction_and_reboot_evidence(self):
        self.evidence()
        self.assertTrue(any(r['status'] != 'passed' for r in self.automated(True)))
        self.evidence(True)
        self.assertTrue(all(r['status'] == 'passed' for r in self.automated(True)))

    def test_nonzero_installer_exit_fails(self):
        self.evidence()
        p = self.path / 'serial-install.log'
        p.write_text(p.read_text().replace('ARCTIC-INSTALL-EXIT=0', 'ARCTIC-INSTALL-EXIT=7'))
        self.assertEqual(next(r for r in self.automated() if r['check'] == 'installer-exit')['status'], 'failed')

    def test_cli_missing_evidence_exits_nonzero_and_writes_report(self):
        result = subprocess.run(['python3', str(ROOT / 'tools/reliability/report.py'), str(self.path)], capture_output=True)
        self.assertEqual(result.returncode, 1)
        self.assertTrue((self.path / 'results.json').exists())


class FetchTests(unittest.TestCase):
    def test_rejects_missing_parts_before_download(self):
        names = ['Arctic-Linux-1.1-x86_64.iso.sha256', 'Arctic-Linux-1.1-x86_64.iso.part01']
        with patch.object(fetch.subprocess, 'check_output', return_value=json.dumps({'assets': [{'name': n} for n in names]})), \
             patch.object(fetch.subprocess, 'run') as download:
            with self.assertRaises(ValueError):
                fetch.fetch('owner/repo', 'v1.1.0', Path('/unused'))
            download.assert_not_called()

    def test_checksum_mismatch_rejected(self):
        iso = 'Arctic-Linux-1.1-x86_64.iso'
        names = [iso, iso + '.sha256']
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / 'download'
            def download(args, **kwargs):
                name = args[args.index('--pattern') + 1]
                (dest / name).write_text('bad ISO' if name == iso else '0' * 64 + '  ' + iso)
            with patch.object(fetch.subprocess, 'check_output', return_value=json.dumps({'assets': [{'name': n} for n in names]})), \
                 patch.object(fetch.subprocess, 'run', side_effect=download):
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    fetch.fetch('owner/repo', 'v1.1.0', dest)
                self.assertFalse((dest / 'provenance.json').exists())


class AppTests(unittest.TestCase):
    def probe(self, snapshots):
        child = MagicMock()
        child.poll.return_value = None
        with patch.object(guest, 'clients', side_effect=snapshots), \
             patch.object(guest.subprocess, 'Popen', return_value=child), \
             patch.object(guest.time, 'monotonic', side_effect=[0, 1, 61]), \
             patch.object(guest.time, 'sleep'), patch('builtins.open', mock_open()):
            return guest.app([], ['arctic-open', 'browser'], 'zen')

    def test_matching_persistent_window_passes(self):
        client = {'1': {'appid': 'zen', 'title': 'Zen'}}
        self.assertIn('persisted', self.probe([{}, client, client]))

    def test_unrelated_new_window_does_not_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'no persistent new window'):
            self.probe([{}, {'1': {'appid': 'kitty', 'title': 'Terminal'}}])

    def test_crashing_window_does_not_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'no persistent new window'):
            self.probe([{}, {'1': {'appid': 'zen'}}, {}])

    def test_existing_window_does_not_pass(self):
        client = {'1': {'appid': 'zen'}}
        with self.assertRaisesRegex(RuntimeError, 'no persistent new window'):
            self.probe([client, client])


class HarnessTests(unittest.TestCase):
    def test_generated_guest_shell_and_python_driver_parse(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            iso = tmp / 'dummy.iso'
            iso.touch()
            engine = tmp / 'engine'
            engine.write_text('#!/bin/bash\nprintf "%s\\n" "$@" > "' + str(tmp / 'args') + '"\n')
            engine.chmod(0o755)
            import os
            subprocess.run([str(ROOT / 'tools/test-install.sh'), '--iso', str(iso),
                            '--out', str(tmp / 'out'), '--reliability-version', '1.1'],
                           env={**os.environ, 'CONTAINER_ENGINE': str(engine)},
                           check=True, capture_output=True)
            for name in ('run.sh', 'collect.sh'):
                subprocess.run(['bash', '-n', str(tmp / 'out/data' / name)], check=True)
            script = (ROOT / 'tools/test-install.sh').read_text().split("DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]
            compile(script, 'vm-driver', 'exec')
            self.assertEqual(json.loads((tmp / 'out/data/config.json').read_text())['version'], '1.1')


if __name__ == '__main__':
    unittest.main()
