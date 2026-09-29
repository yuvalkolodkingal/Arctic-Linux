#!/usr/bin/env python3
"""A tray icon with a menu, for screenshots of the shell's tray menus (test data only).

A StatusNotifierItem (python3-dbus + GLib) whose DBusMenu has what tray menus can have: a
plain entry, a separator, a check box, a radio pair, a disabled entry, a submenu and an entry
with an icon. It registers with the StatusNotifierWatcher (the shell) and runs until killed.
"""
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

ITEM = 'org.kde.StatusNotifierItem'
MENU = 'com.canonical.dbusmenu'

# id → (properties, children)
ENTRIES = {
    0: ({'children-display': 'submenu'}, [1, 2, 3, 4, 5, 6, 7, 8]),
    1: ({'label': '_Open Syncthing'}, []),
    2: ({'type': 'separator'}, []),
    3: ({'label': 'Pause syncing', 'toggle-type': 'checkmark', 'toggle-state': 1}, []),
    4: ({'label': 'Sync on Wi-Fi only', 'toggle-type': 'radio', 'toggle-state': 1}, []),
    5: ({'label': 'Sync on any network', 'toggle-type': 'radio', 'toggle-state': 0}, []),
    6: ({'label': 'Rescan all folders', 'enabled': False}, []),
    7: ({'label': 'Recent folders', 'children-display': 'submenu'}, [9, 10]),
    8: ({'label': 'Quit', 'icon-name': 'application-exit'}, []),
    9: ({'label': 'Photos'}, []),
    10: ({'label': 'Documents'}, []),
}


def layout(eid):
    props, kids = ENTRIES[eid]
    return dbus.Struct((dbus.Int32(eid), dbus.Dictionary(props, signature='sv'),
                        dbus.Array([dbus.Struct(layout(k), signature='ia{sv}av', variant_level=1) for k in kids], signature='v')),
                       signature='ia{sv}av')


class Menu(dbus.service.Object):
    @dbus.service.method(MENU, in_signature='iias', out_signature='u(ia{sv}av)')
    def GetLayout(self, parent, depth, names):
        return dbus.UInt32(1), layout(parent if parent in ENTRIES else 0)

    @dbus.service.method(MENU, in_signature='aias', out_signature='a(ia{sv})')
    def GetGroupProperties(self, ids, names):
        return [dbus.Struct((dbus.Int32(i), dbus.Dictionary(ENTRIES[i][0], signature='sv'))) for i in ids if i in ENTRIES]

    @dbus.service.method(MENU, in_signature='is', out_signature='v')
    def GetProperty(self, eid, name):
        return ENTRIES[eid][0].get(name, '')

    @dbus.service.method(MENU, in_signature='isvu', out_signature='')
    def Event(self, eid, event, data, timestamp):
        pass

    @dbus.service.method(MENU, in_signature='a(isvu)', out_signature='ai')
    def EventGroup(self, events):
        return []

    @dbus.service.method(MENU, in_signature='i', out_signature='b')
    def AboutToShow(self, eid):
        return False

    @dbus.service.method(MENU, in_signature='ai', out_signature='aiai')
    def AboutToShowGroup(self, ids):
        return [], []

    @dbus.service.signal(MENU, signature='ui')
    def LayoutUpdated(self, revision, parent):
        pass

    @dbus.service.signal(MENU, signature='a(ia{sv})a(ias)')
    def ItemsPropertiesUpdated(self, updated, removed):
        pass

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ss', out_signature='v')
    def Get(self, iface, name):
        return self.GetAll(iface)[name]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, iface):
        return {'Version': dbus.UInt32(3), 'TextDirection': 'ltr', 'Status': 'normal',
                'IconThemePath': dbus.Array([], signature='s')}


class Item(dbus.service.Object):
    @dbus.service.method(ITEM, in_signature='ii')
    def Activate(self, x, y):
        pass

    @dbus.service.method(ITEM, in_signature='ii')
    def SecondaryActivate(self, x, y):
        pass

    @dbus.service.method(ITEM, in_signature='ii')
    def ContextMenu(self, x, y):
        pass

    @dbus.service.method(ITEM, in_signature='is')
    def Scroll(self, delta, orientation):
        pass

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='ss', out_signature='v')
    def Get(self, iface, name):
        return self.GetAll(iface)[name]

    @dbus.service.method(dbus.PROPERTIES_IFACE, in_signature='s', out_signature='a{sv}')
    def GetAll(self, iface):
        return {'Category': 'ApplicationStatus', 'Id': 'arctic-fixture', 'Title': 'Syncthing (test)',
                'Status': 'Active', 'IconName': 'folder', 'IconThemePath': '',
                'ItemIsMenu': dbus.Boolean(True), 'Menu': dbus.ObjectPath('/MenuBar'),
                'ToolTip': dbus.Struct(('', dbus.Array([], signature='(iiay)'), 'Syncthing (test)', ''), signature='sa(iiay)ss')}


def main():
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SessionBus()
    name = dbus.service.BusName('org.kde.StatusNotifierItem-%d-1' % __import__('os').getpid(), bus)
    Item(bus, '/StatusNotifierItem')
    Menu(bus, '/MenuBar')

    def register():
        try:
            watcher = bus.get_object('org.kde.StatusNotifierWatcher', '/StatusNotifierWatcher')
            watcher.RegisterStatusNotifierItem(name.get_name(), dbus_interface='org.kde.StatusNotifierWatcher')
            return False
        except dbus.DBusException:
            return True                     # the shell isn't up yet: try again
    GLib.timeout_add(500, register)
    GLib.MainLoop().run()


if __name__ == '__main__':
    main()
