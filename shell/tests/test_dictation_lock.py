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
        for shell_works, controller_hangs, fallback_fails in ((True, False, False), (False, False, False),
                                                            (True, True, False), (False, False, True),
                                                            (False, True, False)):
            with self.subTest(shell_works=shell_works, controller_hangs=controller_hangs,
                              fallback_fails=fallback_fails), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                binary = root / 'bin'
                binary.mkdir()
                calls = root / 'calls'
                stubs = {
                    'arctic-is-live': 'exit 1',
                    'arctic-dictation': 'printf "dictation %s\\n" "$*" >> "$CALLS"\n'
                        'printf "private diagnostic\\n"\nprintf "private diagnostic\\n" >&2\n'
                        + ('sleep 60' if controller_hangs else '') + '\n'
                        + ('[ "$1" = lock-fallback ] && exit 1\nexit 0' if fallback_fails else ''),
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
                    text=True, capture_output=True, timeout=22)
                if controller_hangs:
                    if shell_works:
                        self.assertLess(time.monotonic() - started, 2, 'optional dictation must not hold up the shell lock')
                    else:
                        self.assertLess(time.monotonic() - started, 18, 'optional dictation must not prevent fallback locking')
                self.assertEqual(result.returncode, 0, result.stderr)
                events = calls.read_text().splitlines()
                self.assertEqual(events[:2], ['dictation lock', 'shell lock lock'])
                self.assertEqual(events[2], 'shell lock isLocked' if shell_works else 'dictation lock-fallback')
                if fallback_fails or (controller_hangs and not shell_works):
                    self.assertEqual(events[3], 'swaylock -f')
                self.assertEqual(result.stdout, '')
                self.assertEqual(result.stderr, '')


if __name__ == '__main__':
    unittest.main()
