"""Exercise the actual shell harness and its generated QEMU network arguments."""
import ast
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class InstallNetworkTest(unittest.TestCase):
    def harness(self, options):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            image = base / 'fixture.iso'
            image.write_bytes(b'fixture')
            out = base / 'output'
            out.mkdir()
            (out / 'target.qcow2').touch()
            ca = base / 'fixture-ca.crt'
            ca.write_text('fixture: no actual TLS or VM runs in this test\n')
            engine = base / 'mock-engine'
            engine.write_text('''#!/usr/bin/env python3
import json, os, sys
assert sys.argv[1] == 'run'
with open(os.environ['TEST_ENGINE_LOG'], 'w') as output:
    json.dump(sys.argv[1:], output)
''')
            engine.chmod(0o755)
            env = dict(os.environ, CONTAINER_ENGINE=str(engine),
                       TEST_ENGINE_LOG=str(base / 'invocation.json'),
                       ARCTIC_CA_BUNDLE=str(ca), HTTPS_PROXY='http://127.0.0.1:18080',
                       HTTP_PROXY='', http_proxy='', https_proxy='',
                       ARCTIC_VM_CONTAINER_NAME='')
            result = subprocess.run([str(ROOT / 'tools/test-install.sh'), '--iso', str(image),
                                     '--out', str(out), *options], env=env,
                                    capture_output=True, text=True, timeout=20)
            invocation = base / 'invocation.json'
            if not invocation.exists():
                return result, None, None, None
            args = json.loads(invocation.read_text())
            values = dict(args[i + 1].split('=', 1)
                          for i, arg in enumerate(args[:-1]) if arg == '-e')
            # Execute the production function emitted by the actual shell invocation;
            # do not copy the network choice into a synthetic implementation.
            function = next(node for node in ast.parse(values['DRIVER']).body
                            if isinstance(node, ast.FunctionDef) and node.name == 'qemu_argv')
            namespace = dict(E=values, out=values['OUT'], fw=values['FIRMWARE'],
                             mem=values['MEMORY'], smp=values['SMP'], accel='kvm')
            exec(compile(ast.Module(body=[function], type_ignores=[]), '<actual QEMU driver>', 'exec'), namespace)
            commands = [namespace['qemu_argv'](name, with_iso)
                        for name, with_iso in [('install', True), ('boot', False)]]
            return result, values, commands, (out / 'data/run.sh').read_text()

    def networks(self, commands):
        for command in commands:
            self.assertFalse(any('hostfwd=' in argument for argument in command))
        return [command[command.index('-netdev') + 1] for command in commands]

    def test_default_install_and_installed_boot_remain_isolated(self):
        for options in ([], ['--stage', 'boot']):
            with self.subTest(options=options):
                result, values, commands, script = self.harness(options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(values['BOOT_NETWORK'], 'offline')
                self.assertEqual(self.networks(commands), ['user,id=net0,restrict=on'] * 2)
                self.assertIn('if [ "0" != 1 ]; then', script)
                self.assertIn('ARCTIC-OFFLINE-GATE=failed', script)
                self.assertNotIn('--test-online', script)

    def test_explicit_online_boot_keeps_live_install_offline_in_both_invocations(self):
        for options in (['--boot-network', 'online'],
                        ['--stage', 'boot', '--boot-network', 'online']):
            with self.subTest(options=options):
                result, values, commands, script = self.harness(options)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(values['BOOT_NETWORK'], 'online')
                self.assertEqual(self.networks(commands), ['user,id=net0,restrict=on', 'user,id=net0'])
                self.assertIn('if [ "0" != 1 ]; then', script)
                self.assertIn("curl --noproxy '*'", script)
                self.assertNotIn('--test-online', script)

    def test_existing_explicit_proxy_mode_still_connects_both_phases(self):
        result, values, commands, script = self.harness(['--online-via-proxy'])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(values['ONLINE_PROXY'], '1')
        self.assertEqual(self.networks(commands), ['user,id=net0'] * 2)
        self.assertIn('--test-online', script)

    def test_invalid_mode_fails_before_container_or_vm_start(self):
        result, values, commands, script = self.harness(['--boot-network', 'anything'])
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('--boot-network takes offline or online', result.stderr)
        self.assertIsNone(commands)
