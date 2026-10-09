"""Audio cancellation must precede both lock implementations, even with stale UI status."""
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


LOCK = Path(__file__).resolve().parents[2] / 'dotfiles/.local/bin/arctic-lock'


class DictationLockTests(unittest.TestCase):
    def test_cancellation_precedes_shell_lock_and_swaylock_fallback(self):
        for shell_works, controller_hangs in ((True, False), (False, False), (True, True)):
            with self.subTest(shell_works=shell_works, controller_hangs=controller_hangs), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                binary = root / 'bin'
                binary.mkdir()
                calls = root / 'calls'
                stubs = {
                    'arctic-is-live': 'exit 1',
                    'arctic-dictation': 'printf "dictation %s\\n" "$*" >> "$CALLS"\n'
                        'printf "private diagnostic\\n"\nprintf "private diagnostic\\n" >&2\n'
                        + ('sleep 10' if controller_hangs else ''),
                    'arctic-shell-ipc': 'printf "shell %s\\n" "$*" >> "$CALLS"\n'
                        + ('[ "$2" = isLocked ] && printf "true\\n"\nexit 0' if shell_works else 'exit 1'),
                    'pgrep': 'exit 1',
                    'arctic-login-wallpaper': 'exit 1',
                    'arctic-wallpaper': 'exit 0',
                    'swaylock': 'printf "swaylock %s\\n" "$*" >> "$CALLS"',
                }
                for name, body in stubs.items():
                    path = binary / name
                    path.write_text('#!/bin/sh\n' + body + '\n')
                    path.chmod(0o755)
                started = time.monotonic()
                result = subprocess.run(['bash', str(LOCK)], env=dict(os.environ,
                    PATH=str(binary) + ':/usr/bin:/bin', CALLS=str(calls),
                    XDG_CONFIG_HOME=str(root / 'config'), XDG_CACHE_HOME=str(root / 'cache')),
                    text=True, capture_output=True, timeout=5)
                if controller_hangs:
                    self.assertLess(time.monotonic() - started, 2, 'optional dictation must not hold up the security lock')
                self.assertEqual(result.returncode, 0, result.stderr)
                events = calls.read_text().splitlines()
                self.assertEqual(events[:2], ['dictation lock', 'shell lock lock'])
                self.assertEqual(events[2], 'shell lock isLocked' if shell_works else 'swaylock -f')
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
