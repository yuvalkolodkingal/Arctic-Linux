#!/usr/bin/env python3
"""A deterministic freedesktop notification service for the native host smoke test."""
import json
import sys
from gi.repository import Gio, GLib

XML = '''<node><interface name="org.freedesktop.Notifications">
<method name="GetCapabilities"><arg direction="out" type="as"/></method>
<method name="GetServerInformation"><arg direction="out" type="s"/><arg direction="out" type="s"/><arg direction="out" type="s"/><arg direction="out" type="s"/></method>
<method name="Notify"><arg direction="in" type="s"/><arg direction="in" type="u"/><arg direction="in" type="s"/><arg direction="in" type="s"/><arg direction="in" type="s"/><arg direction="in" type="as"/><arg direction="in" type="a{sv}"/><arg direction="in" type="i"/><arg direction="out" type="u"/></method>
<method name="CloseNotification"><arg direction="in" type="u"/></method>
<signal name="ActionInvoked"><arg type="u"/><arg type="s"/></signal>
<signal name="NotificationClosed"><arg type="u"/><arg type="u"/></signal>
</interface><interface name="org.arcticlinux.TestNotifications"><method name="ClickLatest"/></interface></node>'''
bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
node = Gio.DBusNodeInfo.new_for_xml(XML)
latest = 0

def call(connection, sender, path, interface, method, params, invocation):
    global latest
    if method == 'GetCapabilities':
        invocation.return_value(GLib.Variant('(as)', (['actions', 'body', 'persistence'],)))
    elif method == 'GetServerInformation':
        invocation.return_value(GLib.Variant('(ssss)', ('Arctic Test', 'Arctic', '1', '1.2')))
    elif method == 'Notify':
        app, replacement, icon, title, body, actions, hints, timeout = params.unpack()
        latest = replacement or latest + 1
        with open(sys.argv[1], 'a') as log:
            log.write(json.dumps({'id': latest, 'app': app, 'title': title, 'desktop': hints.get('desktop-entry')}) + '\n')
        invocation.return_value(GLib.Variant('(u)', (latest,)))
    elif method == 'CloseNotification':
        connection.emit_signal(None, path, 'org.freedesktop.Notifications', 'NotificationClosed', GLib.Variant('(uu)', (params.unpack()[0], 3)))
        invocation.return_value(None)
    elif method == 'ClickLatest':
        connection.emit_signal(None, path, 'org.freedesktop.Notifications', 'ActionInvoked', GLib.Variant('(us)', (latest, 'default')))
        invocation.return_value(None)

for interface in node.interfaces:
    bus.register_object('/org/freedesktop/Notifications', interface, call, None, None)
Gio.bus_own_name_on_connection(bus, 'org.freedesktop.Notifications', Gio.BusNameOwnerFlags.NONE, None, None)
GLib.MainLoop().run()
