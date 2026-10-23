"""arctic-openwhispr (dotfiles/.local/bin): voice typing with OpenWhispr. A local file:// release
answers for GitHub; fake rpm, pkexec, dnf, gtk-launch and arctic-settings log what they're asked.

Run: python3 -m unittest discover -s shell/tests
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

REPO = Path(__file__).parents[2]
HELPER = REPO / 'dotfiles' / '.local' / 'bin' / 'arctic-openwhispr'
RPM_NAME = 'OpenWhispr-1.10.4-linux-x86_64.rpm'


@unittest.skipUnless(os.uname().machine == 'x86_64', 'OpenWhispr only builds for x86_64')
class OpenWhisprTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(self.tmp.name)
        self.root = root
        self.log = root / 'log'
        self.state = root / 'installed'          # the fake rpm database: the installed version
        fakes = root / 'fakes'
        fakes.mkdir()
        self.fake(fakes, 'rpm', '''
case "$*" in
  "-q --qf %{VERSION} open-whispr") [ -f "$STATE" ] && cat "$STATE" && exit 0; exit 1 ;;
  "-ql open-whispr") [ -f "$STATE" ] || exit 1
    echo /usr/share/applications/open-whispr.desktop; echo /opt/OpenWhispr/open-whispr ;;
esac''')
        self.fake(fakes, 'pkexec', 'exec "$@"')
        self.fake(fakes, 'gtk-launch', '')
        self.fake(fakes, 'arctic-settings', '')
        self.fake(fakes, 'pgrep', 'exit 1')
        # dnf is called by absolute path; the helper's /usr/bin/dnf is swapped for this fake.
        self.fake(fakes, 'dnf', '''
case "$1" in
  install) [ -f "$4" ] && echo 1.10.4 > "$STATE" ;;
  remove) rm -f "$STATE" ;;
esac''')
        helper = HELPER.read_text().replace('"/usr/bin/dnf"', repr(str(fakes / 'dnf')).replace("'", '"'))
        self.helper = root / 'arctic-openwhispr'
        self.helper.write_text(helper)
        self.payload = b'rpm payload'
        release = root / 'release'
        release.mkdir()
        (release / RPM_NAME).write_bytes(self.payload)
        self.api = root / 'latest.json'
        self.write_release(hashlib.sha256(self.payload).hexdigest())
        self.env = dict(os.environ, HOME=str(root), XDG_CONFIG_HOME=str(root / 'config'),
                        XDG_CACHE_HOME=str(root / 'cache'), STATE=str(self.state), LOG=str(self.log),
                        ARCTIC_OPENWHISPR_API=self.api.as_uri(), PATH=str(fakes) + ':/usr/bin:/bin')

    def tearDown(self):
        self.tmp.cleanup()

    def fake(self, folder, name, body):
        path = folder / name
        path.write_text('#!/bin/sh\necho "{} $*" >> "$LOG"\n{}\n'.format(name, body))
        path.chmod(0o755)

    def write_release(self, sha, url=None):
        # The helper only accepts OpenWhispr's own download URLs: point that prefix at the file.
        self.api.write_text(json.dumps({'tag_name': 'v1.10.4', 'assets': [
            {'name': 'OpenWhispr-1.10.4.AppImage', 'browser_download_url': 'https://example.org/x', 'digest': ''},
            {'name': RPM_NAME, 'size': len(self.payload), 'digest': 'sha256:' + sha,
             'browser_download_url': url or 'https://github.com/OpenWhispr/openwhispr/releases/download/v1.10.4/' + RPM_NAME},
        ]}))

    def openwhispr(self, *args, code=0):
        # urllib can't fetch the fake github.com URL: serve it from the release folder instead.
        shim = ('import runpy, sys, urllib.request\n'
                'real = urllib.request.urlopen\n'
                'def urlopen(req, timeout=None):\n'
                '    url = req.full_url if hasattr(req, "full_url") else req\n'
                '    prefix = "https://github.com/OpenWhispr/openwhispr/releases/download/v1.10.4/"\n'
                '    if url.startswith(prefix): url = "file://{}/" + url[len(prefix):]\n'
                '    return real(url, timeout=timeout)\n'
                'urllib.request.urlopen = urlopen\n'
                'sys.argv = sys.argv[1:]\n'
                'runpy.run_path(sys.argv[0], run_name="__main__")\n').format(self.root / 'release')
        out = subprocess.run([sys.executable, '-c', shim, str(self.helper)] + list(args), env=self.env,
                             capture_output=True, text=True, timeout=30)
        self.assertEqual(out.returncode, code, out.stderr)
        return out

    def calls(self, prefix):
        deadline = time.monotonic() + 3
        while True:
            lines = [l for l in (self.log.read_text().splitlines() if self.log.exists() else []) if l.startswith(prefix)]
            if lines or time.monotonic() > deadline:
                return lines
            time.sleep(0.05)

    def status(self):
        return json.loads(self.openwhispr('status').stdout)

    def test_install_checks_the_download_then_opens_and_removes(self):
        self.assertEqual(self.status()['installed'], False)
        self.openwhispr('open')                                 # not installed: Settings → Voice typing
        self.assertEqual(self.calls('arctic-settings'), ['arctic-settings voice'])
        result = json.loads(self.openwhispr('install').stdout)
        self.assertEqual((result['ok'], result['version'], result['release']), (True, '1.10.4', 'v1.10.4'))
        [install] = self.calls('dnf install')
        self.assertIn('--nogpgcheck', install)
        self.assertTrue(install.endswith('/' + RPM_NAME))
        if os.geteuid() != 0:                                   # the password dialog, as a user
            self.assertEqual(self.calls('pkexec')[0].split()[1], str(self.root / 'fakes' / 'dnf'))
        self.assertFalse(list((self.root / 'cache' / 'arctic').iterdir()), 'the download is cleaned up')
        self.openwhispr('open')
        self.assertEqual(self.calls('gtk-launch'), ['gtk-launch open-whispr.desktop'])
        self.openwhispr('autostart', 'on')
        autostart = self.root / 'config' / 'autostart' / 'open-whispr.desktop'
        self.assertIn('Exec=', autostart.read_text())
        self.assertEqual(self.status()['autostart'], True)
        self.assertEqual(json.loads(self.openwhispr('remove').stdout)['installed'], False)
        self.assertFalse(autostart.exists())
        self.assertEqual(self.status()['installed'], False)

    def test_a_download_that_does_not_match_its_sha256_is_not_installed(self):
        self.write_release('0' * 64)
        out = self.openwhispr('install', code=1)
        self.assertIn('does not match its SHA-256', json.loads(out.stdout)['error'])
        self.assertEqual(self.calls('dnf'), [])

    def test_only_openwhispr_downloads_with_a_digest_are_used(self):
        self.write_release(hashlib.sha256(self.payload).hexdigest(), url='https://example.org/' + RPM_NAME)
        self.assertIn('no x86_64 RPM', json.loads(self.openwhispr('install', code=1).stdout)['error'])
        self.write_release('')
        self.assertIn('no SHA-256', json.loads(self.openwhispr('install', code=1).stdout)['error'])
        self.assertEqual(self.calls('dnf'), [])

    def test_autostart_needs_the_app_and_usage_errors(self):
        self.openwhispr('autostart', 'on', code=2)
        self.assertEqual(self.openwhispr('autostart').stdout.strip(), 'off')
        self.openwhispr('autostart', 'maybe', code=2)
        self.openwhispr('frobnicate', code=2)


if __name__ == '__main__':
    unittest.main()
