"""Execution guards: these fixtures never provision containers or start VMs."""
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import runner as N


class ExecutionControls(unittest.TestCase):
    def test_disabled_manifest_fails_before_any_command(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'manifest.json'
            manifest.write_text('{"ready":false,"release_acceptance":false}')
            with patch.object(N.subprocess, 'check_output') as command:
                with self.assertRaisesRegex(RuntimeError, 'disabled'):
                    N.verify(SimpleNamespace(manifest=manifest))
                command.assert_not_called()

    def test_ready_manifest_refuses_non_actions_host_before_commands(self):
        with tempfile.TemporaryDirectory() as folder:
            manifest = Path(folder) / 'manifest.json'
            manifest.write_text('{"ready":true,"release_acceptance":false}')
            with patch.dict(N.os.environ, {}, clear=True), patch.object(N.subprocess, 'check_output') as command:
                with self.assertRaisesRegex(RuntimeError, 'disposable Arctic Actions lane'):
                    N.verify(SimpleNamespace(manifest=manifest))
                command.assert_not_called()

    def test_iso_size_hash_and_symlink_negatives(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs = Path(folder)
            (inputs / 'iso').mkdir()
            path = inputs / 'iso' / 'fixture.iso'
            path.write_bytes(b'synthetic image')
            with patch.object(N.R, 'ISO', path.name, create=True), \
                 patch.object(N.R, 'ISO_BYTES', path.stat().st_size, create=True), \
                 patch.object(N.R, 'ISO_SHA256', hashlib.sha256(path.read_bytes()).hexdigest(), create=True), \
                 patch.object(N.R, 'SOURCE', '1' * 40, create=True):
                self.assertEqual(N.R.verify_iso(inputs)['bytes'], path.stat().st_size)
                path.write_bytes(b'different bytes')
                with self.assertRaisesRegex(RuntimeError, 'byte count|SHA256'):
                    N.R.verify_iso(inputs)
                path.unlink()
                path.symlink_to(inputs / 'missing.iso')
                with self.assertRaisesRegex(RuntimeError, 'absent or a symlink'):
                    N.R.verify_iso(inputs)

    def test_actual_post_provision_source_failure_prevents_vm(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / 'evidence'
            evidence.mkdir()
            args = SimpleNamespace(source=root / 'source', bundle=N.HERE,
                                   inputs=root / 'inputs', evidence=evidence)
            calls = []

            def provision(argv, log, seconds, cwd, env, container):
                calls.append(argv)
                self.assertIn('prepare-vm-tools.sh', ' '.join(argv))
                (evidence / 'vm-prepared-image-id.txt').write_text('sha256:' + '1' * 64)

            with patch.object(N, 'verify', side_effect=[None, RuntimeError('changed exact source after provisioning')]), \
                 patch.object(N.R, 'require_docker', return_value='fixture'), \
                 patch.object(Path, 'is_char_device', return_value=True), \
                 patch.object(N.R, 'execute', side_effect=provision), \
                 patch.object(N.R, 'pinned_file'), patch.object(N.subprocess, 'run'), \
                 patch.object(N.signal, 'signal'), patch.dict(N.os.environ, GITHUB_SHA='3' * 40), \
                 patch.object(N.R, 'SOURCE', '1' * 40, create=True), \
                 patch.object(N.R, 'ISO', 'fixture.iso', create=True), \
                 patch.object(N.R, 'ISO_BYTES', 1, create=True), \
                 patch.object(N.R, 'ISO_SHA256', '2' * 64, create=True), \
                 patch.object(N.R, 'ORIGINAL_RUN', 1, create=True):
                with self.assertRaisesRegex(RuntimeError, 'changed exact source after provisioning'):
                    N.run(args)
            self.assertEqual(len(calls), 1)
            self.assertEqual(json.loads((evidence / 'execution.json').read_text())['status'], 'failed_or_unrun')
