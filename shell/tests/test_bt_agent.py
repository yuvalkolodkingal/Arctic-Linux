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


class Solicited(unittest.TestCase):
    """Only pairing the user started from the menu gets its "yes" button focused."""

    def test_a_code_for_a_device_chosen_in_the_menu(self):
        expected = {}
        agent.expect(expected, 'aa:bb:cc:dd:ee:ff', 100.0)
        for kind in ('confirm', 'passkey', 'pin', 'show_passkey', 'show_pin'):
            self.assertTrue(agent.solicited(kind, 'AA:BB:CC:DD:EE:FF', expected, 130.0), kind)
        self.assertTrue(agent.solicited('confirm', 'AA:BB:CC:DD:EE:FF', expected, 100.0 + agent.EXPECT_S))

    def test_other_devices_and_stale_choices_are_not(self):
        expected = {}
        agent.expect(expected, 'AA:BB:CC:DD:EE:FF', 100.0)
        self.assertFalse(agent.solicited('confirm', '11:22:33:44:55:66', expected, 101.0))
        self.assertFalse(agent.solicited('confirm', '', expected, 101.0))
        self.assertFalse(agent.solicited('confirm', None, expected, 101.0))
        self.assertFalse(agent.solicited('confirm', 'AA:BB:CC:DD:EE:FF', expected, 101.0 + agent.EXPECT_S))
        self.assertFalse(agent.solicited('confirm', 'AA:BB:CC:DD:EE:FF', {}, 101.0))

    def test_authorizations_never_are(self):
        expected = {}
        agent.expect(expected, 'AA:BB:CC:DD:EE:FF', 100.0)
        self.assertFalse(agent.solicited('authorize', 'AA:BB:CC:DD:EE:FF', expected, 101.0))
        self.assertFalse(agent.solicited('service', 'AA:BB:CC:DD:EE:FF', expected, 101.0))

    def test_old_choices_are_dropped(self):
        expected = {}
        agent.expect(expected, 'AA:BB:CC:DD:EE:FF', 100.0)
        agent.expect(expected, '11:22:33:44:55:66', 100.0 + agent.EXPECT_S + 1)
        self.assertEqual(list(expected), ['11:22:33:44:55:66'])
        agent.expect(expected, '', 100.0 + agent.EXPECT_S + 2)
        self.assertEqual(list(expected), ['11:22:33:44:55:66'])


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
