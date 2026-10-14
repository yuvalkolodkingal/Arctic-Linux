"""Upstream VoxType is quiesced before either lock implementation."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

LOCK = Path(__file__).resolve().parents[2] / 'dotfiles/.local/bin/arctic-lock'

class DictationLockTests(unittest.TestCase):
    def test_cancel_and_stop_precede_shell_or_fallback_lock(self):
        for shell_works in (True, False):
            with self.subTest(shell_works=shell_works), tempfile.TemporaryDirectory() as folder:
                root=Path(folder); binary=root/'bin'; binary.mkdir(); calls=root/'calls'
                stubs={
                    'arctic-is-live':'exit 1',
                    'voxtype':'printf "voxtype %s\\n" "$*" >> "$CALLS"',
                    'systemctl':'printf "systemctl %s\\n" "$*" >> "$CALLS"',
                    'arctic-shell-ipc':'printf "shell %s\\n" "$*" >> "$CALLS"\n'+('[ "$2" = isLocked ] && printf "true\\n"\nexit 0' if shell_works else 'exit 1'),
                    'pgrep':'exit 1', 'arctic-login-wallpaper':'exit 1', 'arctic-wallpaper':'exit 0',
                    'swaylock':'printf "swaylock %s\\n" "$*" >> "$CALLS"; exit 0',
                }
                for name, body in stubs.items():
                    p=binary/name; p.write_text('#!/bin/sh\n'+body+'\n'); p.chmod(0o755)
                done=subprocess.run(['bash',str(LOCK)],env=dict(os.environ,PATH=str(binary)+':/usr/bin:/bin',CALLS=str(calls),XDG_CONFIG_HOME=str(root/'config'),XDG_CACHE_HOME=str(root/'cache')),text=True,capture_output=True,timeout=10)
                self.assertEqual(done.returncode,0,done.stderr)
                events=calls.read_text().splitlines()
                self.assertEqual(events[:3],['voxtype record cancel','systemctl --user stop voxtype.service','shell lock lock'])
                if shell_works:
                    self.assertEqual(events[3], 'shell lock isLocked')
                    self.assertNotIn('systemctl --user start voxtype.service', events)
                else:
                    self.assertIn('swaylock -f', events)
                    self.assertEqual(events[-1], 'systemctl --user start voxtype.service')

if __name__=='__main__': unittest.main()
