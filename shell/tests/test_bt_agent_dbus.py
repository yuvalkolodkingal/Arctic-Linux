"""The Bluetooth agent (scripts/bt-agent.py) against dbusmock's BlueZ on a private bus: it
registers as the default agent, forwards RequestConfirmation to the shell and answers with the
shell's reply. Skipped without python3-dbus, python3-dbusmock and dbus-daemon.

Run: python3 -m unittest discover -s shell/tests -p 'test_bt_agent_dbus.py'
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import unittest

SCRIPTS = Path(__file__).parents[1] / 'scripts'
try:
    import dbus
    import dbusmock  # noqa: F401
    HAVE = bool(shutil.which('dbus-daemon'))
except ImportError:
    HAVE = False

AGENT = '/org/arcticlinux/shell/agent'
DEVICE = '/org/bluez/hci0/dev_11_22_33_44_55_03'


@unittest.skipUnless(HAVE, 'needs python3-dbus, python3-dbusmock and dbus-daemon')
class AgentOnTheBus(unittest.TestCase):
    def setUp(self):
        # A private bus with the session policy stands in for the system bus.
        out = subprocess.run(['dbus-daemon', '--session', '--fork', '--print-address=1', '--print-pid=1'],
                             capture_output=True, text=True, check=True).stdout.split()
        self.address, self.bus_pid = out[0], int(out[1])
        self.env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS=self.address)
        self.mock = subprocess.Popen([sys.executable, '-m', 'dbusmock', '--system', '--template', 'bluez5'],
                                     env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.bus = dbus.bus.BusConnection(self.address)
        self.wait(lambda: self.bus.name_has_owner('org.bluez'))
        mock = dbus.Interface(self.bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.Mock')
        mock.AddAdapter('hci0', 'arctic-test')
        mock.AddDevice('hci0', '11:22:33:44:55:03', 'Pixel 9')
        self.agent = subprocess.Popen([sys.executable, str(SCRIPTS / 'bt-agent.py')], env=self.env, text=True,
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def tearDown(self):
        for p in (self.agent, self.mock):
            p.kill()
            p.wait()
        self.agent.stdin.close()
        self.agent.stdout.close()
        self.bus.close()
        os.kill(self.bus_pid, 15)

    def wait(self, check, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            if check():
                return
            time.sleep(0.05)
        self.fail('timed out')

    def line(self):
        return json.loads(self.agent.stdout.readline())

    def agent_name(self):
        daemon = dbus.Interface(self.bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus'), 'org.freedesktop.DBus')
        for name in daemon.ListNames():
            if name.startswith(':') and daemon.GetConnectionUnixProcessID(name) == self.agent.pid:
                return name
        self.fail('the agent is not on the bus')

    def ask(self, method, *args):
        """Call the agent like BlueZ does, in a thread (the call waits for the shell's answer), on a
        connection of its own so calls can overlap."""
        result = {}
        name = self.agent_name()

        def call():
            bus = dbus.bus.BusConnection(self.address)
            try:
                result['value'] = getattr(bus.get_object(name, AGENT), method)(*args, dbus_interface='org.bluez.Agent1', timeout=20)
            except dbus.DBusException as e:
                result['error'] = e.get_dbus_name()
            finally:
                bus.close()
        t = threading.Thread(target=call)
        t.start()
        return t, result

    def test_registers_and_relays_a_confirmation(self):
        self.assertEqual(self.line(), {'type': 'ready', 'default': True})
        t, result = self.ask('RequestConfirmation', dbus.ObjectPath(DEVICE), dbus.UInt32(42917))
        req = self.line()
        self.assertEqual((req['kind'], req['passkey'], req['name'], req['device']), ('confirm', '042917', 'Pixel 9', DEVICE))
        self.agent.stdin.write(json.dumps({'op': 'reply', 'id': req['id'], 'accept': True}) + '\n')
        self.agent.stdin.flush()
        t.join(10)
        self.assertNotIn('error', result)

    def test_a_refused_passkey_is_rejected(self):
        self.line()
        t, result = self.ask('RequestPasskey', dbus.ObjectPath(DEVICE))
        req = self.line()
        self.assertEqual(req['kind'], 'passkey')
        self.agent.stdin.write(json.dumps({'op': 'reply', 'id': req['id'], 'accept': True, 'value': '12345678'}) + '\n')
        self.agent.stdin.flush()
        t.join(10)
        self.assertEqual(result.get('error'), 'org.bluez.Error.Rejected')
        t, result = self.ask('RequestPasskey', dbus.ObjectPath(DEVICE))
        req = self.line()
        self.agent.stdin.write(json.dumps({'op': 'reply', 'id': req['id'], 'accept': True, 'value': '042917'}) + '\n')
        self.agent.stdin.flush()
        t.join(10)
        self.assertEqual(result.get('value'), 42917)

    def send(self, op):
        self.agent.stdin.write(json.dumps(op) + '\n')
        self.agent.stdin.flush()

    def test_only_a_device_chosen_in_the_menu_is_solicited(self):
        self.line()
        t, result = self.ask('RequestConfirmation', dbus.ObjectPath(DEVICE), dbus.UInt32(1))
        req = self.line()
        self.assertFalse(req['solicited'])              # the device started it
        self.send({'op': 'reply', 'id': req['id'], 'accept': False})
        t.join(10)
        self.assertEqual(result.get('error'), 'org.bluez.Error.Rejected')
        self.send({'op': 'expect', 'address': '11:22:33:44:55:03'})
        t, result = self.ask('RequestConfirmation', dbus.ObjectPath(DEVICE), dbus.UInt32(2))
        req = self.line()
        self.assertTrue(req['solicited'])
        self.send({'op': 'reply', 'id': req['id'], 'accept': True})
        t.join(10)
        self.assertNotIn('error', result)
        t, result = self.ask('RequestAuthorization', dbus.ObjectPath(DEVICE))
        req = self.line()
        self.assertEqual((req['kind'], req['solicited']), ('authorize', False))
        self.send({'op': 'reply', 'id': req['id'], 'accept': False})
        t.join(10)

    def test_a_second_question_is_turned_down_while_one_waits(self):
        self.line()
        first, first_result = self.ask('RequestConfirmation', dbus.ObjectPath(DEVICE), dbus.UInt32(42917))
        req = self.line()
        second, second_result = self.ask('RequestAuthorization', dbus.ObjectPath(DEVICE))
        second.join(10)
        self.assertEqual(second_result.get('error'), 'org.bluez.Error.Rejected')
        self.send({'op': 'reply', 'id': req['id'], 'accept': True})    # the first is still answerable
        first.join(10)
        self.assertNotIn('error', first_result)
        t, result = self.ask('RequestAuthorization', dbus.ObjectPath(DEVICE))
        self.assertEqual(self.line()['id'], req['id'] + 1)              # nothing was shown for the second
        t.join(0)


if __name__ == '__main__':
    unittest.main()
