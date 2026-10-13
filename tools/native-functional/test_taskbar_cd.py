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
MODE_NORMALIZATION = '  # Do not let' + HARNESS.split('  # Do not let', 1)[1].split(
    '\n  [[ -f "$NATIVE_TASKBAR_DISPLAY_CONTROLLER"', 1)[0]
BUILD = HARNESS.split('data_owner_args=()\n', 1)[1].split('\nif [ "$STAGE" != boot ]', 1)[0]
BUILD = (HOST_STAGE + '\nDATA="$OUT/data"\nif [[ "$NATIVE_TASKBAR_FIXTURE" == 1 ]]; then\n' +
         MODE_NORMALIZATION + '\nfi\ndata_owner_args=()\n' + BUILD)


class OwnershipControls(unittest.TestCase):
    def test_actual_taskbar_cd_normalizes_owner_and_modes_only_for_fixture(self):
        if not shutil.which('xorriso'):
            self.skipTest('Host xorriso absent; actual ISO metadata remains required in Fedora CI')
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            data = out / 'data'
            data.mkdir()
            files = {
                'taskbar-context.json': ('{"scope":"ownership source control only"}\n', 0o664, 0o644),
                'taskbar-runtime.py': ('# protected Python fixture\n', 0o664, 0o644),
                'virtual-pointer': ('protected native helper\n', 0o775, 0o755),
            }
            for name, (contents, source_mode, _protected_mode) in files.items():
                path = data / name
                path.write_text(contents)
                path.chmod(source_mode)
            context = data / 'taskbar-context.json'
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
                for name, (_contents, source_mode, protected_mode) in files.items():
                    acl = subprocess.run(['xorriso', '-report_about', 'FATAL', '-indev', str(out/'data.iso'),
                        '-find', '/' + name, '-exec', 'getfacl', '--'], check=True, capture_output=True,
                        text=True, timeout=30).stdout
                    expected_mode = protected_mode if fixture == '1' else source_mode
                    permissions = {key: value for key, value in re.findall(
                        r'^(user::|group::|other::)([rwx-]{3})$', acl, re.M)}
                    rendered = ''.join(permissions[key] for key in ('user::', 'group::', 'other::'))
                    digits = [(4 if 'r' in part else 0) + (2 if 'w' in part else 0) +
                              (1 if 'x' in part else 0)
                              for part in (rendered[0:3], rendered[3:6], rendered[6:9])]
                    actual_mode = (digits[0] << 6) | (digits[1] << 3) | digits[2]
                    self.assertEqual(actual_mode, expected_mode, (fixture, name, acl))
                    readback = out / ('readback-' + fixture + '-' + name)
                    subprocess.run(['xorriso', '-report_about', 'FATAL', '-osirrox', 'on',
                        '-indev', str(out/'data.iso'), '-extract', '/' + name, str(readback)],
                        check=True, capture_output=True, timeout=30)
                    self.assertEqual(readback.read_bytes(), (data/name).read_bytes())

    def test_taskbar_bootstrap_stages_and_reprotects_desktop_automounted_media(self):
        bootstrap = HARNESS.split('if [[ -n "$NATIVE_TASKBAR_BUNDLE" ]]; then\n', 1)[1].split(
            "\nEOF\nelse\n", 1)[0]
        required = (
            'mount -t iso9660 -o ro,nodev,nosuid "$media" "$source"',
            'findmnt -nro SOURCE -T "$source"',
            'find "$source" -xdev ! -type d ! -type f',
            'cp -R --no-preserve=ownership "$source"/. "$stage"/',
            'chown -R 0:0 "$stage"',
            'chmod -R go-w "$stage"',
            'chmod -R a-s "$stage"',
            'find "$stage" -xdev \\( ! -uid 0 -o ! -gid 0 -o -perm /6022 \\)',
            'mount --bind "$stage" "$target"',
            'mount -o remount,bind,ro,nodev,nosuid "$target"',
            'case "$target_options" in *,nodev,*)',
            'case "$target_options" in *,nosuid,*)',
        )
        for command in required:
            self.assertIn(command, bootstrap)
        self.assertNotIn('mount -o ro /dev/disk/by-label/ARCTICTEST /run/t', bootstrap)


if __name__ == '__main__':
    unittest.main()
