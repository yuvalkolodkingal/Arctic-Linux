"""Select software EGL in Safe graphics without forcing it on ordinary GPUs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class GraphicsEnvironmentTests(unittest.TestCase):
    def test_greeter_and_session_follow_the_exact_safe_kernel_flag(self):
        paths = ('packaging/desktop/arctic-graphics.sh',
                 'packaging/sddm-wayland-mango/sddm-compositor-mango')
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            detector = directory / 'systemd-detect-virt'
            detector.write_text('#!/bin/sh\necho none\n')
            detector.chmod(0o755)
            cmdline = directory / 'cmdline'
            for filename in paths:
                script = (ROOT / filename).read_text().replace('/proc/cmdline', str(cmdline))
                script = script.replace('/sys/module/nvidia_drm', str(directory / 'no-nvidia'))
                script = script.split('exec /usr/bin/mango', 1)[0]
                script += '\nprintf "%s,%s,%s\\n" "$WLR_RENDERER_ALLOW_SOFTWARE" "$WLR_RENDERER_FORCE_SOFTWARE" "$LIBGL_ALWAYS_SOFTWARE"\n'
                for kernel, expected in [('quiet rd.live.image', '1,,'),
                                         ('quiet nomodeset rd.live.image', '1,1,1'),
                                         ('nomodeset', '1,1,1'),
                                         ('quiet nomodeset_extra', '1,,')]:
                    cmdline.write_text(kernel + '\n')
                    result = subprocess.run(['sh'], input=script, text=True, check=True, capture_output=True,
                                            env={'PATH': str(directory) + ':/usr/bin:/bin'})
                    self.assertEqual(result.stdout.strip(), expected, filename + ': ' + kernel)


if __name__ == '__main__':
    unittest.main()
