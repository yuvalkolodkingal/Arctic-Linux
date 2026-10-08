"""Failure-path tests for release evidence; no QEMU, network or disks required."""
import importlib.util
import json
import os
from pathlib import Path
import socket
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

    def test_lightweight_live_editor_is_required(self):
        self.evidence()
        results = report.evaluate(self.path, app_profile='lightweight')
        editor = next(r for r in results if r['stage'] == 'live' and r['check'] == 'app-editor')
        self.assertEqual(editor['status'], 'unrun')
        self.assertIn('evidence', editor)
        p = self.path / 'serial-install.log'
        p.write_text(p.read_text() + report.PREFIX + json.dumps(dict(stage='live', check='app-editor', status='passed')) + '\n')
        self.assertTrue(all(r['status'] == 'passed' for r in report.evaluate(self.path, app_profile='lightweight') if 'evidence' in r))

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

    def test_external_network_is_required_only_after_offline_install(self):
        self.evidence()
        p = self.path / 'serial-install.log'
        p.write_text('\n'.join(line for line in p.read_text().splitlines() if '"network"' not in line))
        results = report.evaluate(self.path)
        live = next(r for r in results if r['stage'] == 'live' and r['check'] == 'network')
        self.assertEqual(live['status'], 'unrun')
        self.assertNotIn('evidence', live)
        self.assertTrue(all(r['status'] == 'passed' for r in results if 'evidence' in r))
        p = self.path / 'serial-boot.log'
        p.write_text('\n'.join(line for line in p.read_text().splitlines() if '"network"' not in line))
        self.assertTrue(any(r['check'] == 'network' and r['status'] == 'unrun' and 'evidence' in r
                            for r in report.evaluate(self.path)))

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

    def test_expected_name_in_fallback_title_does_not_pass(self):
        with self.assertRaisesRegex(RuntimeError, 'no persistent new window'):
            self.probe([{}, {'1': {'appid': 'epiphany', 'title': 'zen'}}])

    def test_app_identity_must_persist(self):
        with self.assertRaisesRegex(RuntimeError, 'no persistent new window'):
            self.probe([{}, {'1': {'appid': 'zen'}}, {'1': {'appid': 'kitty'}}])

    def test_profiles_pin_distinct_apps_and_live_editor(self):
        self.assertNotIn('editor', guest.expected_apps('legacy', 'live'))
        self.assertIn('editor', guest.expected_apps('lightweight', 'live'))
        for role in ('terminal', 'files', 'browser', 'editor', 'media'):
            self.assertNotEqual(guest.expected_apps('legacy', 'installed')[role],
                                guest.expected_apps('lightweight', 'installed')[role])
        with self.assertRaises(ValueError):
            guest.expected_apps('unknown', 'live')


class SessionTests(unittest.TestCase):
    def test_live_probe_never_requests_external_network(self):
        with patch.object(guest, 'run') as run:
            self.assertIsNone(guest.network('live'))
            run.assert_not_called()
        with patch.object(guest, 'run', side_effect=RuntimeError('HTTPS failed')) as run:
            with self.assertRaisesRegex(RuntimeError, 'HTTPS failed'):
                guest.network('installed')
            run.assert_called_once()
    def test_child_signature_is_bound_to_user_display_and_compositor_socket(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime = root / 'runtime'
            runtime.mkdir()
            endpoint = runtime / 'mango-10.sock'
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(endpoint))
                def child(pid, display, signature, directory=runtime):
                    proc = root / str(pid)
                    proc.mkdir()
                    (proc / 'environ').write_bytes(
                        f'WAYLAND_DISPLAY={display}\0XDG_RUNTIME_DIR={directory}\0MANGO_INSTANCE_SIGNATURE={signature}\0'.encode())
                args = (root, os.getuid(), runtime, 'wayland-0', {}, endpoint)
                with self.assertRaisesRegex(RuntimeError, 'found 0'):
                    guest.session_signature(*args)
                child(11, 'wayland-1', endpoint)
                child(12, 'wayland-0', endpoint, root / 'other-runtime')
                with self.assertRaisesRegex(RuntimeError, 'found 0'):
                    guest.session_signature(*args)
                child(13, 'wayland-0', endpoint)
                self.assertEqual(guest.session_signature(*args), str(endpoint))
                with self.assertRaisesRegex(RuntimeError, 'this compositor socket'):
                    guest.session_signature(*args[:-1], runtime / 'mango-99.sock')
                child(14, 'wayland-0', runtime / 'mango-99.sock')
                with self.assertRaisesRegex(RuntimeError, 'found 2'):
                    guest.session_signature(*args)

    def test_unowned_or_non_socket_signature_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            endpoint = root / 'mango-10.sock'
            endpoint.touch()
            env = {'MANGO_INSTANCE_SIGNATURE': str(endpoint)}
            with self.assertRaisesRegex(RuntimeError, 'this compositor socket'):
                guest.session_signature(root, os.getuid(), root, 'wayland-0', env, endpoint)
            endpoint.unlink()
            with socket.socket(socket.AF_UNIX) as sock:
                sock.bind(str(endpoint))
                with self.assertRaisesRegex(RuntimeError, 'this compositor socket'):
                    guest.session_signature(root, os.getuid() + 1, root, 'wayland-0', env, endpoint)


class HarnessTests(unittest.TestCase):
    def test_upgrade_retains_transaction_and_reboot_diagnostics(self):
        script = (ROOT / 'tools/test-install.sh').read_text().split("DRIVER <<'PY' || true\n", 1)[1].split('\nPY\n', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            boots = []
            def boot():
                boots.append(len(boots) + 1)
                for name in ('serial-boot.log', 'qemu-boot.log', 'boot-desktop.png'):
                    (root / name).write_text(f'boot {boots[-1]}')
                return 0
            exit_mock = MagicMock()
            exec('rc = 0\n' + script.rsplit('\nrc = 0\n', 1)[1],
                 {'os': os, 'sys': exit_mock, 'stage': 'boot', 'out': str(root),
                  'E': {'UPGRADE_TO': '1.2'}, 'stage_boot': boot,
                  'serial': lambda phase: str(root / f'serial-{phase}.log'), 'log': lambda text: None})
            self.assertEqual(boots, [1, 2])
            for name in ('serial-upgrade.log', 'qemu-upgrade.log', 'upgrade-boot-desktop.png'):
                self.assertEqual((root / name).read_text(), 'boot 1')
            for name in ('serial-boot.log', 'qemu-boot.log', 'boot-desktop.png'):
                self.assertEqual((root / name).read_text(), 'boot 2')
            exit_mock.exit.assert_called_once_with(0)

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
            self.assertEqual((tmp / 'out/data/guest-check.py').read_text(),
                             (ROOT / 'tools/reliability/guest.py').read_text())
            for name, marker in (('run.sh', 'ARCTIC-LIVE-SMOKE-EXIT='),
                                 ('collect.sh', 'ARCTIC-INSTALLED-SMOKE-EXIT=')):
                self.assertEqual((tmp / 'out/data' / name).read_text().count(marker), 1)

    def test_generic_guest_check_cannot_be_replaced_by_reliability(self):
        result = subprocess.run(['bash', str(ROOT / 'tools/test-install.sh'),
                                 '--reliability-version', '1.2', '--guest-check', '/not-used'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('mutually exclusive', result.stderr)


if __name__ == '__main__':
    unittest.main()
