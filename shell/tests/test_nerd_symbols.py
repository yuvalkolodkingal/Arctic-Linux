"""The Nerd Font symbols (arctic-fonts-symbols): the fontconfig fallback, the pinned Source1 in
arctic-linux.spec, its download in tools/build-rpms.sh, and the live image listing the package.

Run: python3 -m unittest discover -s shell/tests
"""
from pathlib import Path
import re
import unittest
import xml.etree.ElementTree as ET

REPO = Path(__file__).parents[2]
CONF = REPO / 'packaging' / 'fonts' / '66-arctic-nerd-symbols.conf'
SPEC = (REPO / 'packaging' / 'arctic-linux.spec').read_text()


class NerdSymbolsTests(unittest.TestCase):
    def test_fontconfig_appends_the_symbols_after_the_code_font(self):
        root = ET.parse(CONF).getroot()
        self.assertEqual(root.tag, 'fontconfig')
        families = {}
        for match in root.findall('match'):
            self.assertEqual(match.get('target'), 'pattern')
            test, edit = match.find('test'), match.find('edit')
            self.assertEqual((edit.get('mode'), edit.get('binding')), ('append', 'weak'),
                             'appended weakly: the code font keeps every glyph it has')
            families[test.findtext('string')] = edit.findtext('string')
        self.assertEqual(families['monospace'], 'Symbols Nerd Font Mono')
        self.assertEqual(families['JetBrains Mono'], 'Symbols Nerd Font Mono')

    def test_source1_is_pinned_and_checked(self):
        version = re.search(r'^%global\s+nerd_version\s+(\S+)$', SPEC, re.M).group(1)
        sha = re.search(r'^%global\s+nerd_sha256\s+(\S+)$', SPEC, re.M).group(1)
        self.assertRegex(version, r'^\d+\.\d+\.\d+$')
        self.assertRegex(sha, r'^[0-9a-f]{64}$')
        self.assertRegex(SPEC, r'(?m)^Source1:\s+https://github\.com/ryanoasis/nerd-fonts/releases/download/'
                               r'v%\{nerd_version\}/NerdFontsSymbolsOnly\.tar\.xz')
        self.assertIn('echo "%{nerd_sha256}  %{SOURCE1}" | sha256sum -c', SPEC)
        self.assertRegex(SPEC, r'(?m)^%package -n arctic-fonts-symbols$')
        self.assertRegex(SPEC, r'(?m)^Recommends:\s+arctic-fonts-symbols = %\{version\}-%\{release\}$')
        build = (REPO / 'tools' / 'build-rpms.sh').read_text()
        self.assertIn('NerdFontsSymbolsOnly-$NERD_VERSION.tar.xz', build)
        self.assertIn('sha256sum -c', build)

    def test_the_live_image_lists_it(self):
        kiwi = (REPO / 'iso' / 'kiwi' / 'config.kiwi').read_text()
        self.assertIn('<package name="arctic-fonts-symbols"/>', kiwi)
        self.assertIn('<package name="arctic-themes-extra"/>', kiwi)


if __name__ == '__main__':
    unittest.main()
