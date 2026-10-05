"""Native desktop paths and IPC identity must survive terminal environment changes."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    'performance_guest', Path(__file__).parents[1]/'performance/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


class NativeSessionTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.proc = Path(self.directory.name)
        self.uid = os.getuid()
        self.runtime = Path('/run/user')/str(self.uid)
        self.base = dict(PATH='/home/ci/.local/state/nix/profiles/arctic/bin:/usr/bin',
                         XDG_DATA_DIRS='/var/lib/flatpak/exports/share:/usr/share',
                         XDG_SESSION_ID='2', XDG_CURRENT_DESKTOP='mango:wlroots')

    def child(self, pid, **changes):
        path = self.proc/str(pid)
        path.mkdir()
        env = dict(self.base, XDG_RUNTIME_DIR=str(self.runtime),
                   WAYLAND_DISPLAY='wayland-0', MANGO_INSTANCE_SIGNATURE='/run/user/test/mango.sock',
                   DISPLAY=':0', QT_QPA_PLATFORM='wayland;xcb')
        env.update(changes)
        (path/'environ').write_bytes(('\0'.join(k+'='+v for k,v in env.items())+'\0').encode())

    def environment(self):
        return guest.session_environment(self.proc, self.uid, self.runtime, 'wayland-0', self.base)

    def test_terminal_paths_do_not_hide_flatpak_or_nix_and_session_identity_is_preserved(self):
        self.child(10)
        self.child(11, XDG_DATA_DIRS='/usr/lib64/kitty/shell-integration:'+self.base['XDG_DATA_DIRS'],
                   PATH='/different/app/path', XDG_SESSION_ID='unrelated-child')
        self.child(12, WAYLAND_DISPLAY='wayland-1', MANGO_INSTANCE_SIGNATURE='unrelated-socket')
        env = self.environment()
        self.assertEqual(env['PATH'], self.base['PATH'])
        self.assertEqual(env['XDG_DATA_DIRS'], self.base['XDG_DATA_DIRS'])
        self.assertEqual(env['XDG_SESSION_ID'], '2')
        self.assertEqual(env['DISPLAY'], ':0')
        self.assertNotIn('QT_QPA_PLATFORM', env)
        self.assertEqual(env['MANGO_INSTANCE_SIGNATURE'], '/run/user/test/mango.sock')

    def test_portal_backend_does_not_replace_unset_login_backend(self):
        self.child(10, GDK_BACKEND='wayland,x11')
        env = self.environment()
        self.assertNotIn('QT_QPA_PLATFORM', env)
        self.assertNotIn('GDK_BACKEND', env)
        self.base['QT_QPA_PLATFORM'] = 'wayland'
        self.base['GDK_BACKEND'] = 'wayland'
        env = self.environment()
        self.assertEqual(env['QT_QPA_PLATFORM'], 'wayland')
        self.assertEqual(env['GDK_BACKEND'], 'wayland')

    def test_missing_or_ambiguous_ipc_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, 'found 0'):
            self.environment()
        self.child(10)
        self.child(11, MANGO_INSTANCE_SIGNATURE='ambiguous-socket')
        with self.assertRaisesRegex(RuntimeError, 'found 2'):
            self.environment()

    def test_missing_login_data_paths_are_rejected_instead_of_guessed(self):
        self.child(10)
        self.base.pop('XDG_DATA_DIRS')
        with self.assertRaisesRegex(RuntimeError, 'Missing actual desktop'):
            self.environment()


if __name__ == '__main__':
    unittest.main()
