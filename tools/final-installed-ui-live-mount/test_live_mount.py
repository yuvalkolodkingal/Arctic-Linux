#!/usr/bin/env python3
"""Exercise the live entry point at the unchanged harness's actual CD mount."""
import contextlib
import importlib.util
import io
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('ui_live_mount_guest', HERE / 'guest.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)


def context():
    return dict(schema='arctic-final-installed-ui-context-v1', nonce='a' * 32,
                execution_sha='b' * 40,
                source_sha='326690f173d4dc4f049f43e046c8380e66825a07',
                iso_sha256='807eaaa64ab8480ec2b18bc8434fd5e37d82c41b73a3e0a6f002c35d152ba54c',
                native_sha256='c' * 64, ui_sha256='d' * 64)


class LiveMount(unittest.TestCase):
    def test_real_harness_live_mount_reaches_existing_native_guard(self):
        harness = (HERE.parents[1] / 'tools' / 'test-install.sh').read_text()
        block = re.search(r"cat > \"\$OUT/sysarea\.sh\" <<'EOF'\n(.*?)\nEOF", harness, re.S)
        self.assertIsNotNone(block)
        mount = re.search(r'^mkdir -p (/[^\s]+)$', block.group(1), re.M).group(1)
        self.assertIn('mount -o ro /dev/disk/by-label/ARCTICTEST ' + mount, block.group(1))
        self.assertIn('exec bash ' + mount + '/run.sh', block.group(1))
        self.assertIn('python3 "\\$D/guest-check.py" live', harness)
        calls = []
        native = {'guest_guard': lambda stage, explicit: calls.append((stage, explicit))}
        output = io.StringIO()
        with patch.object(G, '__file__', mount + '/guest-check.py'), \
             patch.object(sys, 'argv', [mount + '/guest-check.py', 'live']), \
             patch.object(G.os, 'geteuid', return_value=0), contextlib.redirect_stdout(output):
            self.assertEqual(G.main(native, context()), 0)
        self.assertEqual(calls, [('live', True)])
        self.assertEqual(output.getvalue(), 'ARCTIC-FINAL-UI-LIVE-PRECHECK=PASS\n')

    def test_wrong_mount_and_nonroot_still_reject_before_native_guard(self):
        for directory, uid in [('/data', 0), ('/tmp', 0), ('/run/t/foreign', 0), ('/run/t', 1000)]:
            with self.subTest(directory=directory, uid=uid):
                calls = []
                native = {'guest_guard': lambda *args: calls.append(args)}
                output = io.StringIO()
                with patch.object(G, '__file__', directory + '/guest-check.py'), \
                     patch.object(sys, 'argv', [directory + '/guest-check.py', 'live']), \
                     patch.object(G.os, 'geteuid', return_value=uid), \
                     contextlib.redirect_stdout(output), self.assertRaisesRegex(RuntimeError, '^owned-data-cd$'):
                    G.main(native, context())
                self.assertEqual(calls, [])
                self.assertEqual(output.getvalue(), '')


if __name__ == '__main__':
    unittest.main()
