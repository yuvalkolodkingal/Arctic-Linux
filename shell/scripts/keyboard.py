#!/usr/bin/env python3
"""Keyboard layouts for the bar's layout chip (KeyboardService.qml): which layouts Mango uses,
which one is active, and switching between them.

    keyboard.py layouts      one JSON line: {"type": "layouts", "layouts": [{"code", "variant",
                             "name", "short"}], "switch_key": "grp:…", "switch_label": "Alt + Shift"}
    keyboard.py watch        that line, then {"type": "active", "index": N, "name": "…"} now and
                             on every change (`mmsg watch keyboardlayout`; the layouts line again
                             when the config changed in between); nothing polls
    keyboard.py set INDEX    make layout INDEX (from 0) active: `mmsg dispatch
                             switch_keyboard_layout,INDEX+1` (Mango 0.17.3 counts from 1; 0 cycles)
    keyboard.py next         the next layout: `mmsg dispatch switch_keyboard_layout,0`

The layouts are the last xkb_rules_layout / xkb_rules_variant / xkb_rules_options in the order
Mango reads its config: ~/.config/mango/config.conf and the files it sources (arctic/input.conf,
/etc/arctic/mango/keyboard.conf from the installer, settings.conf from Settings, user.conf).
Names come from xkeyboard-config's evdev.xml. Mango reports the active layout by its name
("English (US)", src/ipc/ipc.c), which is mapped back to an index here.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET

HOME = Path(os.environ.get('HOME') or Path.home())
CONFIG = HOME / '.config' / 'mango' / 'config.conf'
EVDEV = [os.environ.get('ARCTIC_XKB_RULES', ''), '/usr/share/X11/xkb/rules/evdev.xml',
         '/usr/share/xkeyboard-config-2/rules/evdev.xml']
KEYS = ('xkb_rules_layout', 'xkb_rules_variant', 'xkb_rules_options')
# The layout-switch options Settings offers (arctic_settings.py SWITCH_KEYS), in words.
SWITCH_LABELS = {
    'grp:alt_shift_toggle': 'Alt + Shift', 'grp:ctrl_shift_toggle': 'Ctrl + Shift', 'grp:caps_toggle': 'Caps Lock',
    'grp:alt_space_toggle': 'Alt + Space', 'grp:shifts_toggle': 'both Shift keys', 'grp:toggle': 'Right Alt',
    'grp:lalt_lshift_toggle': 'left Alt + left Shift', 'grp:alt_caps_toggle': 'Alt + Caps Lock',
    'grp:win_space_toggle': 'Super + Space',
}


def emit(data):
    print(json.dumps(data), flush=True)


def expand(value, base):
    """A path as Mango's source= resolves it: ~/…, ./… (next to config.conf) or absolute."""
    if value == '~' or value.startswith('~/'):
        return HOME / value[2:]
    if value.startswith('./'):
        return base / value[2:]
    return Path(value)


def read_config(path=CONFIG, found=None, depth=0):
    """The xkb_rules_* values Mango ends up with: the last one wins, sources in place."""
    found = {} if found is None else found
    if depth > 8:
        return found
    try:
        lines = Path(path).read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return found
    for line in lines:
        line = line.split('#', 1)[0].strip()
        if '=' not in line:
            continue
        key, value = (part.strip() for part in line.split('=', 1))
        if key in ('source', 'source-optional'):
            read_config(expand(value, CONFIG.parent), found, depth + 1)
        elif key in KEYS:
            found[key] = value
    return found


def xkb_names(path=None):
    """{(code, variant): (description, short)} from evdev.xml; variants inherit the layout's
    short name."""
    names = {}
    for candidate in ([path] if path else EVDEV):
        if not candidate or not Path(candidate).is_file():
            continue
        try:
            root = ET.parse(candidate).getroot()
        except ET.ParseError:
            continue
        for layout in root.iter('layout'):
            item = layout.find('configItem')
            if item is None:
                continue
            code, short = item.findtext('name') or '', item.findtext('shortDescription') or ''
            names[(code, '')] = (item.findtext('description') or code, short)
            for variant in layout.iter('variant'):
                vitem = variant.find('configItem')
                if vitem is not None:
                    names[(code, vitem.findtext('name') or '')] = (vitem.findtext('description') or code,
                                                                  vitem.findtext('shortDescription') or short)
        break
    return names


def layouts(config=None, names=None):
    config = read_config() if config is None else config
    names = xkb_names() if names is None else names
    codes = [c.strip() for c in config.get('xkb_rules_layout', 'us').split(',')]
    variants = [v.strip() for v in config.get('xkb_rules_variant', '').split(',')]
    out = []
    for i, code in enumerate(codes):
        if not code:
            continue
        variant = variants[i] if i < len(variants) else ''
        name, short = names.get((code, variant)) or names.get((code, '')) or (code, '')
        out.append(dict(code=code, variant=variant, name=name, short=(short or code)[:3].upper()))
    options = [o.strip() for o in config.get('xkb_rules_options', '').split(',')]
    switch = next((o for o in options if o.startswith('grp:')), '')
    return dict(type='layouts', layouts=out, switch_key=switch, switch_label=SWITCH_LABELS.get(switch, ''))


def index_of(name, items):
    """Mango's name for the active layout → its index (-1 when unknown)."""
    name = (name or '').strip()
    for match in (lambda l: l['name'] == name, lambda l: l['name'].lower() == name.lower(),
                  lambda l: name.lower() in (l['code'].lower(), l['short'].lower())):
        for i, item in enumerate(items):
            if match(item):
                return i
    return -1


def active(line, items):
    try:
        data = json.loads(line)
    except ValueError:
        return None
    name = data.get('layout', data.get('keyboardlayout')) if isinstance(data, dict) else None
    if not isinstance(name, str):
        return None
    return dict(type='active', index=index_of(name, items), name=name)


def dispatch(argument):
    result = subprocess.run(['mmsg', 'dispatch', 'switch_keyboard_layout,{}'.format(argument)],
                            capture_output=True, text=True, timeout=4)
    ok = result.returncode == 0
    emit(dict(ok=ok) if ok else dict(ok=False, error='The layout couldn’t be switched.'))
    return 0 if ok else 1


def watch():
    names = xkb_names()
    info = layouts(names=names)
    emit(info)
    items = info['layouts']
    try:
        now = subprocess.run(['mmsg', 'get', 'keyboardlayout'], capture_output=True, text=True, timeout=4)
        last = active(now.stdout.strip().splitlines()[0] if now.stdout.strip() else '', items)
        if last:
            emit(last)
        process = subprocess.Popen(['mmsg', 'watch', 'keyboardlayout'], stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True)
    except (OSError, subprocess.SubprocessError):
        return 2        # no Mango: nothing to follow or reconnect to
    for line in process.stdout:
        # Settings may have changed the layouts (Mango reloads and reports the layout again).
        fresh = layouts(names=names)
        if fresh != info:
            info, items, last = fresh, fresh['layouts'], None
            emit(info)
        state = active(line, items)
        if state and state != last:
            emit(state)
            last = state
    return process.wait()


def main(argv):
    if argv[:1] == ['layouts']:
        emit(layouts())
        return 0
    if argv[:1] == ['watch']:
        return watch()
    if argv[:1] == ['next']:
        return dispatch(0)
    if argv[:1] == ['set'] and len(argv) == 2 and argv[1].isdigit() and int(argv[1]) < 100:
        return dispatch(int(argv[1]) + 1)
    print(__doc__.strip(), file=sys.stderr)
    return 2


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    sys.exit(main(sys.argv[1:]))
