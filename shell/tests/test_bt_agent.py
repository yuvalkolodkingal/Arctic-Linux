"""Tests for scripts/bt-agent.py (the Bluetooth pairing agent): the parts that need no D-Bus.

Run: python3 -m unittest discover -s shell/tests -p 'test_bt_agent.py'
"""
import importlib.util
from pathlib import Path
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
spec = importlib.util.spec_from_file_location('bt_agent', SCRIPTS / 'bt-agent.py')
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)

DEVICE = '/org/bluez/hci0/dev_AA_BB_CC_DD_EE_FF'
PROPS = {'Address': 'AA:BB:CC:DD:EE:FF', 'Alias': 'Pixel 9', 'Name': 'Pixel', 'Icon': 'phone'}


class Requests(unittest.TestCase):
    def test_confirm_pads_the_passkey(self):
        req = agent.build_request(3, 'confirm', DEVICE, PROPS, passkey=42917)
        self.assertEqual(req, {'type': 'request', 'id': 3, 'kind': 'confirm', 'device': DEVICE,
                               'address': 'AA:BB:CC:DD:EE:FF', 'name': 'Pixel 9', 'icon': 'phone', 'passkey': '042917'})

    def test_show_passkey_counts_typed_digits(self):
        req = agent.build_request(4, 'show_passkey', DEVICE, {'Name': 'MX Keys', 'Icon': 'input-keyboard'}, passkey=7, entered=3)
        self.assertEqual((req['name'], req['passkey'], req['entered'], req['icon']), ('MX Keys', '000007', 3, 'input-keyboard'))

    def test_every_kind_has_a_name(self):
        for kind in ('pin', 'passkey', 'authorize', 'service', 'show_pin'):
            req = agent.build_request(1, kind, DEVICE, {})
            self.assertEqual(req['kind'], kind)
            self.assertEqual(req['name'], 'A device')
        self.assertEqual(agent.build_request(1, 'pin', DEVICE, {'Address': 'AA:BB'})['name'], 'AA:BB')

    def test_service_names(self):
        base = '-0000-1000-8000-00805f9b34fb'
        self.assertEqual(agent.service_name('0000110d' + base), 'audio')        # A2DP
        self.assertEqual(agent.service_name('0000111E' + base), 'audio')        # HFP
        self.assertEqual(agent.service_name('00001124' + base), 'typing and pointing')
        self.assertEqual(agent.service_name('00001105' + base), 'file transfer')
        self.assertEqual(agent.service_name('00001116' + base), 'network sharing')
        self.assertEqual(agent.service_name('0000ffff' + base), 'a service')
        self.assertEqual(agent.service_name('6e400001-b5a3-f393-e0a9-e50e24dcca9e'), 'a service')
        self.assertEqual(agent.service_name(''), 'a service')


class Replies(unittest.TestCase):
    def test_passkeys(self):
        self.assertEqual(agent.check_passkey('042917'), 42917)
        self.assertEqual(agent.check_passkey('0'), 0)
        self.assertEqual(agent.check_passkey('999999'), 999999)
        for bad in ('1000000', '-1', '12a', '', None, '1.5', ' '):
            self.assertIsNone(agent.check_passkey(bad), bad)

    def test_pins(self):
        self.assertEqual(agent.check_pin('0000'), '0000')
        self.assertEqual(agent.check_pin('x' * 16), 'x' * 16)
        for bad in ('', 'x' * 17, 'a\nb', None, '\x00'):
            self.assertIsNone(agent.check_pin(bad), repr(bad))


if __name__ == '__main__':
    unittest.main()
