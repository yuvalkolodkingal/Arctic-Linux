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
    count, byte_count, map_sequence = 0, 0, 0
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
        keymap = Gdk.Keymap.get_for_display(window.get_display())
        settings = Gtk.Settings.get_for_screen(window.get_screen())
        def im_settings():
            properties = {p.name for p in settings.list_properties()}
            return {name: dict(status='observed',value=settings.get_property(name)) if name in properties
                    else dict(status='unavailable',reason='property not exposed')
                    for name in ('gtk-im-module','gtk-enable-accels')}
        def read_map(value=None):
            # Read-only translation, never filter/activate a GTK binding.
            result = keymap.get_entries_for_keyval(Gdk.KEY_Return)
            entries = [dict(keycode=int(k.keycode),group=int(k.group),level=int(k.level)) for k in result[1]] if result[0] else []
            if len(entries)>64: raise RuntimeError('Return map entry bound exceeded')
            output = dict(sequence=map_sequence,return_entries=entries,return_entries_valid=bool(result[0]),im_settings=im_settings())
            if value is not None:
                translated = keymap.translate_keyboard_state(value.hardware_keycode,value.state,value.group)
                output['event_current_translation'] = dict(valid=bool(translated[0]),keyval=int(translated[1]),
                    keyval_name=Gdk.keyval_name(translated[1]),effective_group=int(translated[2]),
                    level=int(translated[3]),consumed_modifiers=int(translated[4]))
            return output
        def current_map(value=None):
            try: return read_map(value)
            except BaseException as exc:
                (root/'gtk-control-error.json').write_text(json.dumps(dict(error=type(exc).__name__+': '+str(exc))))
                application.quit()
                return dict(status='collector-error',error=str(exc))
        def map_changed(*_):
            nonlocal map_sequence
            map_sequence += 1
            log('keys-changed',current_map=current_map())
        keymap.connect('keys-changed',map_changed)
        settings.connect('notify::gtk-im-module',lambda *_: log('im-setting-changed',im_settings=im_settings()))
        def event(widget, value, name):
            log(name, keyval=int(value.keyval), keyval_name=Gdk.keyval_name(value.keyval),
                hardware_keycode=int(value.hardware_keycode), state=int(value.state),
                has_focus=bool(entry.has_focus()), is_focus=bool(entry.is_focus()), text=entry.get_text(),
                group=int(value.group),is_modifier=bool(value.is_modifier),send_event=bool(value.send_event),
                current_map=current_map(value))
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
        handled_requests = set()
        def requested_snapshot():
            request_path = root/'gtk-snapshot-request.json'
            if not request_path.exists(): return True
            try:
                info = request_path.lstat()
                if request_path.is_symlink() or info.st_uid != os.getuid() or info.st_size>4096:
                    raise RuntimeError('snapshot request ownership/bound differs')
                request = json.loads(request_path.read_text())
                nonce = request.get('nonce')
                if not re.fullmatch('[0-9a-f]{32}',nonce or '') or request != dict(nonce=nonce,appid=appid):
                    raise RuntimeError('snapshot request schema/identity differs')
                if nonce in handled_requests: return True
                if handled_requests: raise RuntimeError('GTK snapshot is one-use')
                handled_requests.add(nonce)
                value = dict(schema='arctic-gtk-widget-snapshot-v1',nonce=nonce,appid=appid,
                    title=window.get_title(),pid=os.getpid(),uid=os.getuid(),start_ticks=start_ticks,
                    boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),monotonic_ns=time.monotonic_ns(),
                    text=entry.get_text(),has_focus=bool(entry.has_focus()),is_focus=bool(entry.is_focus()),
                    window_active=bool(window.is_active()),activations=count,current_map=current_map())
                output = root/'gtk-widget-snapshot.json'
                with output.open('x') as stream: stream.write(json.dumps(value,sort_keys=True)+'\n')
                log('owned-widget-snapshot',snapshot=value)
            except BaseException as exc:
                (root/'gtk-control-error.json').write_text(json.dumps(dict(error=type(exc).__name__+': '+str(exc))))
                application.quit(); return False
            return True
        # A disclosed read-only owned-widget observation timer; no focus or input changes.
        GLib.timeout_add(100,requested_snapshot)
        log('mapped', appid=appid,current_map=current_map(), program_name=GLib.get_prgname(), gtk_version=[Gtk.get_major_version(),Gtk.get_minor_version(),Gtk.get_micro_version()],
            backend=type(Gdk.Display.get_default()).__name__)
    app.connect('activate', activated)
    return app.run([])


if __name__ == '__main__':
    raise SystemExit(main())
