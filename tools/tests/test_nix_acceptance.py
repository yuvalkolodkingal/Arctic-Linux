"""Regression for the installed-VM probe's post-exec compositor environment."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('nix_guest', Path(__file__).parents[1]/'nix-acceptance/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class SessionEnvironmentTest(unittest.TestCase):
    def test_reads_child_signature_and_rejects_missing_or_ambiguous_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = Path('/run/user')/str(os.getuid())
            def child(pid, display, signature):
                folder = root/str(pid)
                folder.mkdir()
                (folder/'environ').write_bytes(('WAYLAND_DISPLAY='+display+'\0XDG_RUNTIME_DIR='+str(runtime)+'\0MANGO_INSTANCE_SIGNATURE='+signature+'\0').encode())
            with self.assertRaisesRegex(RuntimeError, 'found 0'):
                guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {})
            child(10, 'wayland-0', '/run/user/test/mango.sock')
            child(11, 'wayland-1', '/run/user/test/other.sock')
            self.assertEqual(guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {}), '/run/user/test/mango.sock')
            child(12, 'wayland-0', '/run/user/test/ambiguous.sock')
            with self.assertRaisesRegex(RuntimeError, 'found 2'):
                guest.session_signature(root, os.getuid(), runtime, 'wayland-0', {})
