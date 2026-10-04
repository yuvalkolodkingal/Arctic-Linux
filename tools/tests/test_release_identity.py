"""Keep package, boot-media and client identities consistent across release bumps."""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


class ReleaseIdentityTest(unittest.TestCase):
    def test_packages_clients_and_boot_media_agree(self):
        spec = (ROOT / 'packaging/arctic-linux.spec').read_text()
        version = re.search(r'^Version:\s+(\S+)', spec, re.M)[1]
        short = '.'.join(version.split('.')[:2])
        self.assertRegex(spec, rf'(?m)^%global arctic_version\s+{re.escape(short)}$')
        self.assertIn(f'VERSION_ID={short}\n', (ROOT / 'packaging/release/os-release').read_text())
        kiwi = ET.parse(ROOT / 'iso/kiwi/config.kiwi').getroot()
        self.assertEqual(kiwi.findtext('preferences/version'), version)
        self.assertEqual(kiwi.find('preferences/type').get('volid'), 'Arctic-Linux-' + short)
        for path, marker in [('internal/backend/backend.go', 'EngineVersion = '),
                             ('internal/webapp/version.go', 'Version = '),
                             ('installer-ui/Engine.qml', 'clientVersion: ')]:
            self.assertIn(marker + '"' + version + '"', (ROOT / path).read_text(), path)
        filename = 'Arctic-Linux-' + short + '-x86_64.iso'
        for path in ['tools/build-iso.sh', 'tools/test-iso.sh', 'tools/test-install.sh',
                     'tools/screenshot-tour.sh', '.github/workflows/iso.yml']:
            self.assertIn(filename, (ROOT / path).read_text(), path)
