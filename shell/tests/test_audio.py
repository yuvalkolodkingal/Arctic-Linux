"""Tests for scripts/audio.py (ports and profiles in the sound menu), on a recorded pw-dump.

Run: python3 -m unittest discover -s shell/tests -p 'test_audio.py'
"""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('audio', SCRIPTS / 'audio.py')
audio = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio)
DUMP = json.loads((Path(__file__).parent / 'fixtures' / 'pw-dump.json').read_text())


class Parsing(unittest.TestCase):
    def test_cards(self):
        cards = audio.parse_dump(DUMP)
        self.assertEqual([c['description'] for c in cards], ['Built-in Audio', 'WH-1000XM5'])
        builtin, headset = cards
        self.assertEqual((builtin['id'], builtin['bus']), (45, 'pci'))
        # "off" is not offered; the active profile is marked.
        self.assertEqual([(p['index'], p['active']) for p in builtin['profiles']], [(1, True), (3, False)])
        self.assertEqual(builtin['profiles'][1]['available'], 'no')
        self.assertEqual([p['description'] for p in headset['profiles'] if p['active']], ['High Fidelity Playback (A2DP Sink)'])
        self.assertEqual(headset['routes'], [])

    def test_routes(self):
        routes = audio.parse_dump(DUMP)[0]['routes']
        by_name = {r['description']: r for r in routes}
        self.assertTrue(by_name['Headphones']['active'])
        self.assertFalse(by_name['Speakers']['active'])
        self.assertEqual(by_name['Speakers']['device'], 7)            # the card device the sink uses
        self.assertEqual(by_name['Internal Microphone']['direction'], 'input')
        self.assertEqual(by_name['Headphones']['devices'], [7])

    def test_nothing(self):
        self.assertEqual(audio.parse_dump([]), [])
        self.assertEqual(audio.parse_dump({'not': 'a list'}), [])

    def test_commands(self):
        self.assertEqual(audio.profile_command('61', '2'), ['wpctl', 'set-profile', '61', '2'])
        self.assertEqual(audio.route_command(45, 2, 7), ['pw-cli', 'set-param', '45', 'Route', '{ index: 2, device: 7, save: true }'])
        with self.assertRaises(ValueError):
            audio.route_command('45; rm', 2, 7)
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(audio.main(['route', '45', 'x', '7']), 1)
        self.assertIn('numbers', out.getvalue())


if __name__ == '__main__':
    unittest.main()
