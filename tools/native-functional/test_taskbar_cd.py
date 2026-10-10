"""Actual taskbar ISO ownership metadata; never starts a VM."""
import grp
import os
from pathlib import Path
import pwd
import re
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
HARNESS = (HERE.parents[1] / 'tools/test-install.sh').read_text()
HOST_STAGE = 'dictation_host_stage() {\n' + HARNESS.split('dictation_host_stage() {\n', 1)[1].split(
    '\ndictation_host_stage host-data', 1)[0]
BUILD = HARNESS.split('data_owner_args=()\n', 1)[1].split('\nif [ "$STAGE" != boot ]', 1)[0]
BUILD = HOST_STAGE + '\ndata_owner_args=()\n' + BUILD


class OwnershipControls(unittest.TestCase):
    def test_actual_taskbar_cd_normalizes_rock_ridge_uid_gid_only_for_fixture(self):
        if not shutil.which('xorriso'):
            self.skipTest('Host xorriso absent; actual ISO metadata remains required in Fedora CI')
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            data = out / 'data'
            data.mkdir()
            context = data / 'taskbar-context.json'
            context.write_text('{"scope":"ownership source control only"}\n')
            context.chmod(0o644)
            owner = os.getuid()
            group = os.getgid()
            if os.geteuid() == 0:
                owner = group = 12345
                os.chown(context, owner, group)
            (out / 'sysarea.sh').write_text('#!/bin/sh\nexit 1\n')
            for fixture, expected in (('0', (owner, group)), ('1', (0, 0))):
                env = dict(os.environ, OUT=str(out), NATIVE_TASKBAR_FIXTURE=fixture,
                           ARCTIC_DICTATION_HOST_TOKEN='')
                built = subprocess.run(['bash', '-c', BUILD], env=env, check=True, capture_output=True, timeout=30)
                self.assertLess(len(built.stdout) + len(built.stderr), 65536, 'Actual CD fixture output exceeds bound')
                for stream in (built.stdout, built.stderr):
                    self.assertNotIn(b'ARCTIC-DICTATION-HOST-STAGE', stream, 'Disabled host diagnostics emitted output')
                info = subprocess.run(['xorriso', '-report_about', 'FATAL', '-indev', str(out/'data.iso'),
                    '-find', '/taskbar-context.json', '-exec', 'getfacl', '--'],
                    check=True, capture_output=True, text=True, timeout=30).stdout
                ids = []
                for key, lookup, field in (('owner', pwd.getpwnam, 'pw_uid'),
                                           ('group', grp.getgrnam, 'gr_gid')):
                    match = re.search(r'^# ' + key + r':\s*(\S+)\s*$', info, re.M)
                    self.assertIsNotNone(match, 'Missing actual ISO ' + key + ' metadata')
                    token = match.group(1)
                    ids.append(int(token) if re.fullmatch(r'[0-9]+', token)
                               else getattr(lookup(token), field))
                self.assertEqual(tuple(ids), expected)
                readback = out / ('readback-' + fixture)
                subprocess.run(['xorriso', '-report_about', 'FATAL', '-osirrox', 'on',
                    '-indev', str(out/'data.iso'), '-extract', '/taskbar-context.json', str(readback)],
                    check=True, capture_output=True, timeout=30)
                self.assertEqual(readback.read_bytes(), context.read_bytes())


if __name__ == '__main__':
    unittest.main()
