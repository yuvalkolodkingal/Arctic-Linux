#!/usr/bin/env python3
"""UPower wire fixture for a private test bus; never connects to the real system bus."""
import os

import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DEVICE = 'org.freedesktop.UPower.Device'
ROOT = '/org/freedesktop/UPower'
DISPLAY = ROOT + '/devices/DisplayDevice'
PROPERTIES = 'org.freedesktop.DBus.Properties'


class Device(dbus.service.Object):
    def __init__(self, bus, path, percentage, capacity):
        super().__init__(bus, path)
        self.values = dict(Type=dbus.UInt32(2), PowerSupply=dbus.Boolean(True),
                           IsPresent=dbus.Boolean(True), Percentage=dbus.Double(percentage),
                           State=dbus.UInt32(2), Energy=dbus.Double(capacity * percentage / 100),
                           EnergyFull=dbus.Double(capacity), EnergyRate=dbus.Double(-5),
                           TimeToEmpty=dbus.Int64(0), TimeToFull=dbus.Int64(0),
                           Capacity=dbus.Double(98), IconName=dbus.String('battery'),
                           NativePath=dbus.String(path.rsplit('/', 1)[-1]), Model=dbus.String('Fixture'))

    @dbus.service.method(PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.values if interface == DEVICE else {}

    @dbus.service.method(PROPERTIES, in_signature='ss', out_signature='v')
    def Get(self, interface, name):
        return self.values[name]

    @dbus.service.signal(PROPERTIES, signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    @dbus.service.method('org.arcticlinux.BatteryFixture', in_signature='dub', out_signature='')
    def Change(self, percentage, state, present):
        changed = dict(Percentage=dbus.Double(percentage), State=dbus.UInt32(state), IsPresent=dbus.Boolean(present))
        self.values.update(changed)
        self.PropertiesChanged(DEVICE, changed, [])


class UPower(dbus.service.Object):
    @dbus.service.method('org.freedesktop.UPower', out_signature='ao')
    def EnumerateDevices(self):
        return [ROOT + '/devices/battery_BAT0', ROOT + '/devices/battery_BAT1']

    @dbus.service.method('org.freedesktop.UPower', out_signature='o')
    def GetDisplayDevice(self):
        return DISPLAY

    @dbus.service.method('org.freedesktop.UPower', out_signature='s')
    def GetCriticalAction(self):
        return 'Suspend'

    @dbus.service.method(PROPERTIES, in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return dict(OnBattery=dbus.Boolean(False), DaemonVersion=dbus.String('fixture'))


if __name__ == '__main__':
    # Require the caller's isolated address; do not accidentally use the host bus.
    address = os.environ['ARCTIC_BATTERY_TEST_BUS']
    DBusGMainLoop(set_as_default=True)
    bus = dbus.bus.BusConnection(address)
    name = dbus.service.BusName('org.freedesktop.UPower', bus=bus)
    upower = UPower(bus, ROOT)
    # 10% of 10Wh plus 90% of 30Wh = 70%, rather than BAT0's 10% or mean 50%.
    devices = [Device(bus, ROOT + '/devices/battery_BAT0', 10, 10),
               Device(bus, ROOT + '/devices/battery_BAT1', 90, 30),
               Device(bus, DISPLAY, 70, 40)]
    GLib.MainLoop().run()
