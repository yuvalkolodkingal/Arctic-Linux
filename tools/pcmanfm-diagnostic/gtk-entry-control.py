#!/usr/bin/env python3
"""One disposable Gtk3 entry; logs only its own received input and activation."""
import json
import os
from pathlib import Path
import re
import sys
import time


def main():
    if len(sys.argv) != 3 or os.geteuid() == 0:
        raise RuntimeError('requires owned output directory/application ID as desktop UID')
    root, appid = Path(sys.argv[1]), sys.argv[2]
    if not root.is_dir() or root.is_symlink() or root.stat().st_uid != os.getuid() or not re.fullmatch(
            r'org\.arctic\.Diagnostic\.Entry\.a[0-9a-f]{16}', appid):
        raise RuntimeError('invalid owned control output/application identity')
    import gi
    gi.require_version('Gtk', '3.0')
    # Gtk3 Wayland initializes the actual app ID from g_get_prgname, not merely
    # Gtk.Application.application_id. Set our diagnostic nonce before GTK init.
    from gi.repository import GLib
    GLib.set_prgname(appid)
    from gi.repository import Gtk, Gdk, Gio, GLib
    path = root/'gtk-events.log'
    raw_stat = Path('/proc/self/stat').read_text()
    start_ticks = int(raw_stat[raw_stat.rindex(')') + 2:].split()[19])
    if path.exists():
        raise RuntimeError('control evidence must be unused')
    count, byte_count = 0, 0
    def log(event, **fields):
        nonlocal byte_count
        record = dict(event=event, monotonic_ns=time.monotonic_ns(), pid=os.getpid(), uid=os.getuid(), start_ticks=start_ticks, **fields)
        row = (json.dumps(record,sort_keys=True)+'\n').encode()
        byte_count += len(row)
        if byte_count > 2*1024*1024:
            (root/'gtk-control-error.json').write_text(json.dumps(dict(error='own GDK event log exceeded bound')))
            app.quit()
            return
        with path.open('ab') as stream:
            stream.write(row)
    app = Gtk.Application(application_id=appid, flags=Gio.ApplicationFlags.NON_UNIQUE)
    def activated(application):
        nonlocal count
        window = Gtk.ApplicationWindow(application=application)
        window.set_title('Arctic Gtk3 diagnostic '+appid)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        entry = Gtk.Entry(); label = Gtk.Label(label='Activations: 0')
        box.pack_start(entry, True, True, 12); box.pack_start(label, True, True, 12)
        window.add(box); window.set_default_size(480, 180)
        def event(widget, value, name):
            log(name, keyval=int(value.keyval), keyval_name=Gdk.keyval_name(value.keyval),
                hardware_keycode=int(value.hardware_keycode), state=int(value.state),
                has_focus=bool(entry.has_focus()), is_focus=bool(entry.is_focus()), text=entry.get_text())
            return False
        entry.connect('key-press-event', lambda w,e: event(w,e,'key-press'))
        entry.connect('key-release-event', lambda w,e: event(w,e,'key-release'))
        entry.connect('focus-in-event', lambda *_: (log('focus-in', text=entry.get_text()) or False))
        entry.connect('focus-out-event', lambda *_: (log('focus-out', text=entry.get_text()) or False))
        entry.connect('changed', lambda *_: log('changed', text=entry.get_text()))
        def activate(widget):
            nonlocal count
            count += 1; label.set_text('Activations: '+str(count))
            log('activate', count=count, text=entry.get_text(), has_focus=bool(entry.has_focus()))
        entry.connect('activate', activate)
        window.connect('destroy', lambda *_: application.quit())
        window.show_all()
        GLib.idle_add(lambda: (entry.grab_focus() or False))
        log('mapped', appid=appid, program_name=GLib.get_prgname(), gtk_version=[Gtk.get_major_version(),Gtk.get_minor_version(),Gtk.get_micro_version()],
            backend=type(Gdk.Display.get_default()).__name__)
    app.connect('activate', activated)
    return app.run([])


if __name__ == '__main__':
    raise SystemExit(main())
