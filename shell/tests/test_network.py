"""Tests for scripts/network.py (the network menu's nmcli helper), with a fake nmcli.

Run: python3 -m unittest discover -s shell/tests -p 'test_network.py'
"""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
FIXTURES = Path(__file__).parent / 'fixtures'
spec = importlib.util.spec_from_file_location('network', SCRIPTS / 'network.py')
network = importlib.util.module_from_spec(spec)
spec.loader.exec_module(network)

SECRET = 'correct horse:battery\\staple'
UUID = '11111111-2222-3333-4444-555555555555'

# A fake nmcli: logs its argv (one JSON list per line), copies whatever arrives through a
# passwd-file into secrets.txt, and answers from the scenario in $FAKE_NMCLI.
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
root = os.path.dirname(os.path.abspath(__file__))
args = sys.argv[1:]
with open(os.path.join(root, 'argv.log'), 'a') as f:
    f.write(json.dumps(args) + '\n')
scenario = json.loads(os.environ.get('FAKE_NMCLI', '{}'))
words = ' '.join(a for a in args if not a.startswith('-') or a in ('--active',))
if 'passwd-file' in args:
    path = args[args.index('passwd-file') + 1]
    with open(path) as src, open(os.path.join(root, 'secrets.txt'), 'a') as dst:
        dst.write(src.read())
for key, answer in scenario.items():
    if key in words:
        sys.stdout.write(answer.get('out', ''))
        sys.stderr.write(answer.get('err', ''))
        sys.exit(answer.get('code', 0))
sys.exit(0)
'''

STATUS = {
    'device status': {'out': 'wlp2s0:wifi:connected:Home\nenp3s0:ethernet:unavailable:--\nlo:loopback:unmanaged:--\n'},
    'connection show --active': {'out': 'Home:%s:802-11-wireless:wlp2s0:activated\n' % UUID},
    'connection show uuid': {'out': 'Home\n'},
    'connection show': {'out': 'Home:%s:802-11-wireless:1759000000:yes\n'
                               'Work VPN:99999999-2222-3333-4444-555555555555:vpn:1758000000:no\n'
                               'Wired connection 1:88888888-2222-3333-4444-555555555555:802-3-ethernet:0:yes\n' % UUID},
    'radio': {'out': 'enabled:enabled\n'},
    'device wifi list': {'out': '*:Home:82:5180 MHz:WPA2\n:Home:40:2437 MHz:WPA2\n:Café\\:5G:55:5500 MHz:WPA3\n'
                                ':--:30:2412 MHz:WPA2\n::20:2412 MHz:\n:Airport:61:2412 MHz:\n:Corp:70:5200 MHz:WPA2 802.1X\n'},
}


class Parsing(unittest.TestCase):
    def test_split_terse(self):
        self.assertEqual(network.split_terse('a:b\\:c:d\\\\e:'), ['a', 'b:c', 'd\\e', ''])
        self.assertEqual(network.split_terse(''), [''])

    def test_security(self):
        cases = {'': 'open', '--': 'open', 'OWE': 'owe', 'WEP': 'wep', 'WPA1': 'wpa-psk', 'WPA2': 'wpa-psk',
                 'WPA1 WPA2': 'wpa-psk', 'WPA2 WPA3': 'wpa-psk', 'WPA3': 'sae', 'WPA2 802.1X': 'enterprise',
                 'WPA3 802.1X': 'enterprise'}
        for sec, want in cases.items():
            self.assertEqual(network.security_of(sec), want, sec)

    def test_wifi_list(self):
        nets = network.parse_wifi_list(STATUS['device wifi list']['out'], {'Airport': 'u-airport'})
        self.assertEqual([n['ssid'] for n in nets], ['Home', 'Airport', 'Corp', 'Café:5G'])
        home = nets[0]
        self.assertEqual((home['signal'], home['band'], home['in_use'], home['security']), (82, '5 GHz', True, 'wpa-psk'))
        self.assertEqual((nets[1]['saved'], nets[1]['uuid'], nets[1]['security']), (True, 'u-airport', 'open'))
        self.assertEqual(nets[3]['security'], 'sae')
        self.assertEqual(nets[2]['security'], 'enterprise')
        self.assertEqual(network.band_of('2437 MHz'), '2.4 GHz')
        self.assertEqual(network.band_of('6115 MHz'), '6 GHz')

    def test_state(self):
        rows = lambda key: [network.split_terse(l) for l in STATUS[key]['out'].splitlines()]
        state = network.build_state(rows('device status'), rows('connection show --active'),
                                    rows('connection show'), rows('radio'))
        self.assertEqual(state['wifi'], {'device': 'wlp2s0', 'state': 'connected', 'hardware': True, 'enabled': True})
        self.assertEqual(state['wired'], [{'device': 'enp3s0', 'state': 'unavailable', 'connection': ''}])
        self.assertEqual(state['active'][0]['name'], 'Home')
        self.assertEqual(state['vpn'], [{'uuid': '99999999-2222-3333-4444-555555555555', 'name': 'Work VPN',
                                         'kind': 'vpn', 'active': False, 'last_used': 1758000000}])

    def test_errors(self):
        self.assertEqual(network.error_for(4, 'Error: Connection activation failed: Secrets were required, but not provided.', 'Home')[0], 'auth')
        code, text = network.error_for(3, '', 'Home')
        self.assertEqual(code, 'timeout')
        self.assertIn('“Home” didn’t answer', text)
        self.assertEqual(network.error_for(10, 'Error: No network with SSID', 'Home')[0], 'not_found')
        self.assertEqual(network.error_for(8, '', 'Home')[0], 'nm_down')
        self.assertEqual(network.error_for(1, 'Error: Not authorized to control networking.', 'Home')[0], 'denied')
        code, text = network.error_for(4, 'Error: something odd happened\nmore', 'Home')
        self.assertEqual(code, 'failed')
        self.assertEqual(text, 'Couldn’t connect to “Home”. something odd happened')

    def test_state_changed_lines(self):
        failed = ('/org/freedesktop/NetworkManager/Devices/3: org.freedesktop.NetworkManager.Device.StateChanged '
                  '(uint32 120, uint32 60, uint32 7)')
        self.assertEqual(network.parse_state_changed(failed), ('/org/freedesktop/NetworkManager/Devices/3', 120, 60, 7))
        self.assertIsNone(network.parse_state_changed(
            "/org/freedesktop/NetworkManager/Devices/3: org.freedesktop.DBus.Properties.PropertiesChanged ('x', {}, @as [])"))
        self.assertIsNone(network.parse_state_changed(''))

    def test_secret_input(self):
        self.assertEqual(network.read_secret(io.StringIO(json.dumps({'secret': 'pw'}) + '\n')), 'pw')
        for bad in ['', 'not json\n', json.dumps({'secret': ''}), json.dumps({'secret': 'a\nb'}),
                    json.dumps({'secret': 'a\u0000b'}), json.dumps({'secret': 'x' * 5000}), json.dumps({'secret': 3})]:
            with self.assertRaises(network.Failure, msg=bad):
                network.read_secret(io.StringIO(bad))

    def test_wep_key_type(self):
        self.assertEqual(network.wep_key_type('abcde'), 'key')
        self.assertEqual(network.wep_key_type('0123456789'), 'key')
        self.assertEqual(network.wep_key_type('a longer passphrase'), 'passphrase')


class Commands(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bin = Path(self.tmp.name)
        nmcli = self.bin / 'nmcli'
        nmcli.write_text(FAKE.replace('/usr/bin/env python3', sys.executable, 1))
        nmcli.chmod(0o755)

    def tearDown(self):
        self.tmp.cleanup()

    def run_helper(self, *args, scenario=None, stdin='', env=None):
        e = dict(os.environ, PATH=str(self.bin) + ':/usr/bin:/bin', FAKE_NMCLI=json.dumps(scenario or {}))
        e.pop('ARCTIC_NETWORK_FIXTURE', None)
        e.update(env or {})
        p = subprocess.run([sys.executable, str(SCRIPTS / 'network.py'), *args], input=stdin, capture_output=True,
                           text=True, env=e, timeout=30)
        lines = [json.loads(l) for l in p.stdout.splitlines() if l.strip()]
        return p.returncode, lines[-1] if lines else None

    def argv(self):
        log = self.bin / 'argv.log'
        return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []

    def secrets(self):
        f = self.bin / 'secrets.txt'
        return f.read_text() if f.exists() else ''

    def assertNoSecretOnArgv(self):
        for argv in self.argv():
            for a in argv:
                self.assertNotIn('horse', a, argv)

    def test_status(self):
        code, out = self.run_helper('status', scenario=STATUS)
        self.assertEqual(code, 0)
        self.assertTrue(out['ok'])
        self.assertEqual(out['wifi']['device'], 'wlp2s0')
        self.assertEqual(out['saved'], [{'uuid': UUID, 'ssid': 'Home', 'autoconnect': True}])

    def test_scan_marks_saved(self):
        code, out = self.run_helper('scan', '--rescan', scenario=STATUS)
        self.assertEqual(code, 0)
        self.assertEqual(out['networks'][0]['uuid'], UUID)
        self.assertIn(['device', 'wifi', 'rescan'], self.argv())

    def test_join_new_psk_network_secret_through_pipe(self):
        scenario = dict(STATUS)
        scenario['connection add'] = {'out': "Connection 'Café:5G' (%s) successfully added.\n" % UUID}
        code, out = self.run_helper('connect', '--ssid', 'Café:5G', '--security', 'sae', '--ask',
                                    scenario=scenario, stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual((code, out), (0, {'ok': True, 'uuid': UUID}))
        self.assertEqual(self.secrets(), '802-11-wireless-security.psk:%s\n' % SECRET)
        self.assertNoSecretOnArgv()
        add = next(a for a in self.argv() if a[:2] == ['connection', 'add'])
        self.assertEqual(add[add.index('ssid') + 1], 'Café:5G')
        self.assertEqual(add[add.index('wifi-sec.key-mgmt') + 1], 'sae')
        up = next(a for a in self.argv() if 'up' in a)
        self.assertEqual(up[:4], ['--wait', '40', 'connection', 'up'])
        self.assertTrue(up[-1].startswith('/dev/fd/'))

    def test_hidden_and_wep(self):
        scenario = dict(STATUS)
        scenario['connection add'] = {'out': "Connection 'Lab' (%s) successfully added.\n" % UUID}
        code, _ = self.run_helper('connect', '--ssid', 'Lab', '--security', 'wep', '--hidden', '--ask',
                                  scenario=scenario, stdin=json.dumps({'secret': 'abcde'}) + '\n')
        self.assertEqual(code, 0)
        add = next(a for a in self.argv() if a[:2] == ['connection', 'add'])
        self.assertEqual(add[add.index('802-11-wireless.hidden') + 1], 'yes')
        self.assertEqual(add[add.index('wifi-sec.wep-key-type') + 1], 'key')
        self.assertEqual(self.secrets(), '802-11-wireless-security.wep-key0:abcde\n')

    def test_failed_join_deletes_the_new_profile(self):
        scenario = dict(STATUS)
        scenario['connection add'] = {'out': "Connection 'Home' (%s) successfully added.\n" % UUID}
        scenario['connection up'] = {'code': 4, 'err': 'Error: Connection activation failed: Secrets were required, but not provided.\n'}
        code, out = self.run_helper('connect', '--ssid', 'Home', '--security', 'wpa-psk', '--ask',
                                    scenario=scenario, stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual(code, 1)
        self.assertEqual(out['code'], 'auth')
        self.assertEqual(out['error'], 'That password didn’t work for “Home”. Check it and try again.')
        self.assertIn(['connection', 'delete', 'uuid', UUID], self.argv())
        self.assertNoSecretOnArgv()

    def test_saved_network_keeps_its_profile(self):
        scenario = {'connection up': {'code': 3, 'err': 'Error: Timeout expired (40 seconds)\n'}}
        code, out = self.run_helper('connect', '--uuid', UUID, '--name', 'Home', '--security', 'wpa-psk', '--ask',
                                    scenario=scenario, stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual((code, out['code']), (1, 'timeout'))
        self.assertFalse(any('delete' in a for a in self.argv()))
        self.assertEqual(self.secrets(), '802-11-wireless-security.psk:%s\n' % SECRET)

    def test_company_network(self):
        scenario = dict(STATUS)
        scenario['connection add'] = {'out': "Connection 'eduroam' (%s) successfully added.\n" % UUID}
        code, out = self.run_helper('enterprise', '--ssid', 'eduroam', '--eap', 'ttls', '--phase2', 'pap',
                                    '--identity', 'ada@uni.example', '--anonymous-identity', 'anon@uni.example',
                                    '--domain', 'uni.example', '--system-ca', '--ask',
                                    scenario=scenario, stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual((code, out), (0, {'ok': True, 'uuid': UUID}))
        add = next(a for a in self.argv() if a[:2] == ['connection', 'add'])
        pairs = dict(zip(add[10::2], add[11::2]))
        self.assertEqual(pairs['802-1x.eap'], 'ttls')
        self.assertEqual(pairs['802-1x.phase2-auth'], 'pap')
        self.assertEqual(pairs['802-1x.identity'], 'ada@uni.example')
        self.assertEqual(pairs['802-1x.anonymous-identity'], 'anon@uni.example')
        self.assertEqual(pairs['802-1x.domain-suffix-match'], 'uni.example')
        self.assertEqual(pairs['802-1x.system-ca-certs'], 'yes')
        self.assertEqual(self.secrets(), '802-1x.password:%s\n' % SECRET)
        self.assertNoSecretOnArgv()

    def test_company_network_refusals(self):
        with self.assertRaises(network.Failure):
            network.enterprise_settings('tls', 'mschapv2', 'ada')
        with self.assertRaises(network.Failure):
            network.enterprise_settings('peap', 'mschapv2', '')
        self.assertIn('no', network.enterprise_settings('peap', 'mschapv2', 'ada', system_ca=False))
        scenario = dict(STATUS)
        scenario['connection add'] = {'out': "Connection 'eduroam' (%s) successfully added.\n" % UUID}
        scenario['connection up'] = {'code': 4, 'err': 'Error: Connection activation failed: Secrets were required, but not provided.\n'}
        code, out = self.run_helper('enterprise', '--ssid', 'eduroam', '--identity', 'ada', '--ask',
                                    scenario=scenario, stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual((code, out['code']), (1, 'auth'))
        self.assertIn('username or password', out['error'])
        self.assertIn(['connection', 'delete', 'uuid', UUID], self.argv())

    def test_open_network_needs_no_secret(self):
        scenario = {'device status': STATUS['device status'],
                    'connection add': {'out': "Connection 'Airport' (%s) successfully added.\n" % UUID}}
        code, _ = self.run_helper('connect', '--ssid', 'Airport', '--security', 'open', scenario=scenario)
        self.assertEqual(code, 0)
        add = next(a for a in self.argv() if a[:2] == ['connection', 'add'])
        self.assertNotIn('wifi-sec.key-mgmt', add)
        self.assertEqual(self.secrets(), '')

    def test_refuses_a_multiline_secret(self):
        code, out = self.run_helper('connect', '--uuid', UUID, '--ask', stdin=json.dumps({'secret': 'a\nb'}) + '\n')
        self.assertEqual((code, out['code']), (1, 'bad_secret'))
        self.assertEqual(self.argv(), [])

    def test_forget_disconnect_radio_vpn(self):
        self.assertEqual(self.run_helper('forget', '--uuid', UUID)[0], 0)
        self.assertEqual(self.run_helper('disconnect', '--uuid', UUID)[0], 0)
        self.assertEqual(self.run_helper('radio', 'wifi', 'off')[0], 0)
        self.assertEqual(self.run_helper('autoconnect', '--uuid', UUID, 'off')[0], 0)
        code, _ = self.run_helper('vpn-up', '--uuid', UUID, '--name', 'Work', '--ask', stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual(code, 0)
        self.assertEqual(self.secrets(), 'vpn.secrets.password:%s\n' % SECRET)
        argv = self.argv()
        self.assertIn(['connection', 'delete', 'uuid', UUID], argv)
        self.assertIn(['connection', 'down', 'uuid', UUID], argv)
        self.assertIn(['radio', 'wifi', 'off'], argv)
        self.assertIn(['connection', 'modify', 'uuid', UUID, 'connection.autoconnect', 'no'], argv)
        self.assertNoSecretOnArgv()

    def test_forget_by_ssid(self):
        code, _ = self.run_helper('forget', '--ssid', 'Home', scenario=STATUS)
        self.assertEqual(code, 0)
        self.assertIn(['connection', 'delete', 'uuid', UUID], self.argv())

    def test_vpn_without_password_asks(self):
        scenario = {'connection up': {'code': 4, 'err': 'Error: Connection activation failed: Secrets were required, but not provided.\n'}}
        code, out = self.run_helper('vpn-up', '--uuid', UUID, '--name', 'Work', scenario=scenario)
        self.assertEqual((code, out['code']), (1, 'auth'))
        self.assertEqual(out['error'], 'Type the password for “Work”.')

    def test_fixture_mode_runs_nothing(self):
        env = {'ARCTIC_NETWORK_FIXTURE': str(FIXTURES / 'network.json')}
        code, out = self.run_helper('scan', env=env)
        self.assertEqual(code, 0)
        self.assertGreater(len(out['networks']), 3)
        code, out = self.run_helper('connect', '--ssid', 'Office', '--security', 'wpa-psk', '--ask', env=env,
                                    stdin=json.dumps({'secret': SECRET}) + '\n')
        self.assertEqual(code, 0)
        self.assertEqual(self.argv(), [])
        e = dict(os.environ, **env)
        p = subprocess.run([sys.executable, str(SCRIPTS / 'network.py'), 'watch'], input='{"op":"scan","on":true}\n',
                           capture_output=True, text=True, env=e, timeout=10)
        kinds = [json.loads(l)['type'] for l in p.stdout.splitlines()]
        self.assertEqual(kinds, ['state', 'networks'])


if __name__ == '__main__':
    unittest.main()
