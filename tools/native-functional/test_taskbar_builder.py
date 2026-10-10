"""Metadata-only replay controls; no container, compiler, ISO or guest is run."""
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent

# Observed Fedora 44 transaction records in original native run 38036601512,
# archive SHA-256 20c66937241cc76f538ef053446b48a8c3d1fc2510ccb0e5bfc7a8b3bf51edb1.
# The idle/active builder logs independently contain the same package versions.
# The RPM command simulator below is a synthetic control, not RPM/VM evidence.
OBSERVED_PACKAGES = {
    'gcc': ['gcc-16.2.1-2.fc44.x86_64'],
    'wayland-devel': ['wayland-devel-1.26.0-1.fc44.x86_64'],
    'libwayland-client': ['libwayland-client-1.26.0-1.fc44.x86_64'],
    'libwayland-server': ['libwayland-server-1.26.0-1.fc44.x86_64'],
    'libwayland-egl': ['libwayland-egl-1.26.0-1.fc44.x86_64'],
    'dbus-daemon': ['dbus-daemon-1.16.2-1.fc44.x86_64'],
    'glib2': ['glib2-2.88.3-1.fc44.x86_64'],
    'qemu-ui-dbus': ['qemu-ui-dbus-10.2.2-1.fc44.x86_64'],
    'qemu-ui-opengl': ['qemu-ui-opengl-10.2.2-1.fc44.x86_64'],
}
COMPILER_PACKAGES = ('gcc', 'wayland-devel', 'libwayland-client',
                     'libwayland-server', 'libwayland-egl')


def metadata_source():
    script = (HERE / 'prepare-taskbar-tools.sh').read_text()
    return script.split('python3 - <<"PY"\n', 1)[1].split('\nPY\n', 1)[0]


class TaskbarBuilderMetadataControls(unittest.TestCase):
    def replay(self, packages):
        writes = {}

        def command(argv, **kwargs):
            if argv == ['gcc', '--version']:
                return 'gcc (GCC) 16.2.1\n'
            self.assertEqual(argv[:2], ['rpm', '-q'])
            self.assertIs(kwargs['text'], True)
            missing = [name for name in argv[2:] if name not in packages]
            if missing:
                raise subprocess.CalledProcessError(1, argv,
                    output='\n'.join('package ' + name + ' is not installed' for name in missing))
            return '\n'.join(record for name in argv[2:] for record in packages[name]) + '\n'

        def fixture_bytes(path):
            return ('synthetic metadata input: ' + str(path)).encode()

        def write(path, content):
            writes[str(path)] = content
            return len(content)

        with patch.object(subprocess, 'check_output', side_effect=command), \
             patch.object(Path, 'read_bytes', fixture_bytes), \
             patch.object(Path, 'write_text', write), \
             patch.dict('os.environ', {'ARCTIC_INSTALLER_ACTIVE': '0'}):
            try:
                exec(compile(metadata_source(), 'actual-taskbar-builder-metadata', 'exec'), {})
            except subprocess.CalledProcessError:
                self.assertFalse(writes)
                raise
        self.assertEqual(set(writes), {'/payload/build-provenance.json'})
        return json.loads(writes['/payload/build-provenance.json'])

    def test_observed_split_package_inventory_produces_complete_provenance(self):
        result = self.replay(OBSERVED_PACKAGES)
        self.assertEqual(result['schema'], 'arctic-taskbar-tools-v1')
        self.assertIs(result['release_acceptance'], False)
        self.assertEqual(result['packages'],
                         [record for name in COMPILER_PACKAGES for record in OBSERVED_PACKAGES[name]])
        self.assertEqual(set(result['binaries']), {'virtual-pointer', 'raw-screencopy'})
        for name, value in result['binaries'].items():
            self.assertEqual(value, hashlib.sha256(
                ('synthetic metadata input: /payload/' + name).encode()).hexdigest())
        self.assertEqual(result['display_host']['backend'], 'dbus')
        self.assertIs(result['display_host']['gl'], False)

    def test_missing_required_compiler_or_wayland_package_fails_closed(self):
        for name in COMPILER_PACKAGES:
            packages = copy.deepcopy(OBSERVED_PACKAGES)
            del packages[name]
            with self.subTest(package=name), self.assertRaises(subprocess.CalledProcessError) as caught:
                self.replay(packages)
            self.assertEqual(caught.exception.returncode, 1)
            self.assertIn(name, caught.exception.cmd)

    def test_all_installed_package_records_are_preserved(self):
        packages = copy.deepcopy(OBSERVED_PACKAGES)
        packages['libwayland-client'].append('libwayland-client-1.26.0-1.fc44.i686')
        result = self.replay(packages)
        self.assertEqual(result['packages'],
                         [record for name in COMPILER_PACKAGES for record in packages[name]])


if __name__ == '__main__':
    unittest.main()
