"""Additional photo checks must not overwrite a failed native gate."""
import hashlib
import importlib.util
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location('photo_composer', HERE / 'compose-photo-probe.py')
C = importlib.util.module_from_spec(spec)
spec.loader.exec_module(C)


class PhotoControls(unittest.TestCase):
    def test_composed_probe_embeds_actual_collection_and_refuses_host(self):
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / 'probe.py'
            sha = C.compose(ROOT, output)
            self.assertEqual(sha, hashlib.sha256((ROOT / 'design/backgrounds/collection.json').read_bytes()).hexdigest())
            compile(output.read_text(), str(output), 'exec')
            result = subprocess.run(['python3', str(output), 'live'], capture_output=True, text=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('Requires root in the owned QEMU test guest', result.stderr)
            self.assertNotIn('ARCTIC-NATIVE-PHOTOS', result.stdout)

    def test_actual_live_shell_native_and_photo_failure_propagation(self):
        source = (ROOT / 'tools/test-install.sh').read_text()
        block = source.split('if [ -f "\\$D/guest-check.py" ]; then\n', 1)[1].split('\nstart=\\$(date', 1)[0]
        block = 'if [ -f "$D/guest-check.py" ]; then\n' + block.replace('\\$', '$')
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            data, binpath = root / 'data', root / 'bin'
            data.mkdir(); binpath.mkdir()
            (data / 'guest-check.py').touch(); (data / 'photo-check.py').touch()
            python = binpath / 'python3'
            python.write_text('#!/bin/bash\necho "${1##*/}" >> "$CALLS"\ncase "$1" in *guest-check.py) exit "$NATIVE_RC";; *) exit "$PHOTO_RC";; esac\n')
            python.chmod(0o755)
            poweroff = binpath / 'systemctl'
            poweroff.write_text('#!/bin/bash\necho poweroff >> "$CALLS"\n')
            poweroff.chmod(0o755)
            for native, photo, expected in ((0, 0, 0), (0, 7, 7), (5, 0, 5)):
                calls = root / 'calls'
                calls.unlink(missing_ok=True)
                env = dict(os.environ, PATH=str(binpath), D=str(data), S=str(root / 'serial'),
                           CALLS=str(calls), NATIVE_RC=str(native), PHOTO_RC=str(photo))
                result = subprocess.run(['/bin/bash', '-c', 'say() { echo "$*"; };\n' + block],
                                        env=env, capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, expected, result.stderr)
                self.assertIn('ARCTIC-LIVE-SMOKE-EXIT=' + str(expected), result.stdout)
                delivered = calls.read_text().splitlines()
                self.assertEqual('photo-check.py' in delivered, native == 0)
                self.assertEqual('poweroff' in delivered, expected != 0)
