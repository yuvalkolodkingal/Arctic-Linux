#!/usr/bin/env python3
"""arctic_settings.py — the backend of Arctic Settings (settings/shell.qml).

Every read and write the Settings app does goes through here, so the QML stays a thin view and
the file formats are tested (settings/tests/test_arctic_settings.py). Each command prints one
JSON object; failures print {"ok": false, "error": "<a sentence for the person>"} and exit 1.

    state                         Mango options (effective values, where they come from), custom
                                  shortcuts, startup apps, monitor rules, capabilities
    set KEY=VALUE…                change Mango options (written to ~/.config/mango/settings.conf)
    reset KEY…                    back to Arctic's value (the key is removed from settings.conf)
    layout NAME|--reset           default window layout (tagrule=id:*,layout_name:NAME)
    undo                          put the previous settings.conf back (from the backups)
    binds                         the shortcut sheet (keys.txt), every bind in the config, yours
    bind-add MODS KEY COMMAND     add a shortcut that runs COMMAND (checked for clashes)
    notices                       what to say once at login about shortcuts (arctic-settings --check-binds)
    clipboard                     clipboard history: kept or not, and how many entries
    clipboard-set history on|off  keep clipboard history (~/.config/arctic/clipboard.conf)
    clipboard-clear               forget clipboard history (cliphist wipe)
    bind-remove INDEX
    startup                       startup apps: yours (exec-once in settings.conf) and Arctic's
    startup-add COMMAND | --app DESKTOP-ID
    startup-remove INDEX
    displays                      outputs (wlr-randr --json, else mmsg) and saved monitor rules
    display-arrange JSON [OP]     tidy a layout (touching, no overlap, from 0,0) after OP:
                                  --move NAME X Y [--threshold PX] | --nudge NAME left|right|up|down
                                  | --main NAME | --enable NAME | --disable NAME | --anchor NAME
    display-try JSON              apply a layout now (wlr-randr); it reverts by itself after 20 s
    display-keep                  keep it: written as monitorrule lines
    display-revert                go back to the layout from before display-try
    display-forget [NAME…]        drop saved monitor rules (Arctic's defaults apply again)
    devices                       connected keyboards, mice and touchpads (mmsg get all-devices)
    power-profile [NAME]          power mode: power-saver, balanced, performance (tuned-ppd over D-Bus)
    apps                          default apps per role (browser, terminal, files, editor, …)
    app-set ROLE DESKTOP-ID       ~/.config/arctic/default-apps (arctic-open) + mimeapps.list
    idle | idle-set LOCK SUSPEND  lock / suspend timeouts in seconds (0 = never), for swayidle
    keyboard-data                 XKB layouts, variants and layout-switch keys (evdev.lst)
    cursor-themes                 installed cursor themes
    theme | theme-set NAME | theme-auto on|off | theme-mode auto|dark|light      (arctic-theme)
    motion | motion-set on|off    reduced motion (arctic-motion)
    text-scale [FACTOR]           GTK text size (org.gnome.desktop.interface text-scaling-factor)
    wallpapers | wallpaper-set KEY                the shell's picker backend (wallpapers.py)
    wallpaper-import PATH|URL…    copy pictures into your wallpaper folder (checked with Pillow)
    wallpaper-delete PATH | wallpaper-rename PATH NAME     your own pictures only
    wallhaven ARGS…               the Wallhaven browser (the shell's wallhaven.py: search, preview,
                                  set, state, key, prefs); answers {"ok": false, "offline": true}
                                  instead of failing when Wallhaven can't be reached
    updates | update-run now|apply|channel NAME|auto on|off                     (arctic-update)
    network | wifi on|off         NetworkManager status (nmcli)
    notifications                 do not disturb, its schedule, history and the per-app rules
    notification-set KEY VALUE    history on|off, schedule on|off, schedule-from / schedule-to HH:MM
    notification-rule-set APP KEY on|off…   toasts, history, allow_during_dnd, silence_urgent
    notification-history-clear    empty the notification centre
    dnd-set on|off|1h|tomorrow    do not disturb now (arctic-dnd)
    about                         Arctic and Fedora versions, hardware, Mango and Quickshell
    caps                          which helper commands and tools are installed
    webapps                       web apps and kept sign-in data, with sizes (arctic-webapp list)
    webapp-set ID KEY VALUE       change a web app (KEY: name links notifications devtools rendering
                                  runtime category mail-links add-domain remove-domain
                                  forget-certificate icon)
    webapp-reset-permissions ID | webapp-refresh ID | webapp-clear ID | webapp-open ID | webapp-runtimes
    webapp-remove ID keep|delete | webapp-forget ID
    nightlight, keep-awake, autostart, printers, datetime, more-updates …   see arctic_system.py
    shell-options | shell-option-set KEY VALUE    the shell's options (shell.json): webSearch,
                                  weather, weatherUnits, barWeather
    weather-place [search TEXT | set NAME LAT LON [DETAIL] | zone]    where the weather is for
    daylight | daylight-set off|sun|hours LIGHT DARK      light and dark by the clock (arctic-daylight)
    accessibility                 what the Accessibility page needs (the keyboard pointer, wl-kbptr,
                                  high contrast)
    contrast-set on|off           high contrast (arctic-theme contrast)
    fonts | font-set FAMILY       the code font (arctic-font): terminals, GTK's monospace, the shell
    wallpaper-rotate [off | 30m|1h|1d FOLDER|arctic [shuffle]]     a new picture every so often
    theme-install URL | theme-remove NAME     themes from the web (arctic-theme install / remove)

Writes are atomic (temporary file + rename), user-level, validated first (our own key table,
then `mango -c FILE -p` when Mango is installed) and backed up to
~/.local/state/arctic/settings-backups. Nothing here needs root.
"""
import contextlib
import fcntl
import json
import math
import os
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE_LINE = 'source-optional=~/.config/mango/settings.conf'
HEADER = """\
# Arctic Settings keeps this file (the Settings app, arctic-settings). Changes you make there
# land here; ~/.config/mango/config.conf sources it after Arctic's own files and before
# user.conf, so anything in user.conf still wins. Lines Settings doesn't know are kept at the end.
"""
MAX_LINE = 500      # Mango reads 511 bytes per line and 255 per value
MAX_VALUE = 250
BACKUPS_KEPT = 20
TERMINALS = ('kitty', 'foot', 'alacritty')   # take `-e COMMAND…` and `--hold` (arctic-open)
REVERT_AFTER = 20   # seconds before an unconfirmed display change undoes itself


class Failure(Exception):
    """An error meant for the person using Settings (one plain sentence)."""


# ---- paths ------------------------------------------------------------------------------------

class Paths:
    """Where things live. Mango reads ~/.config/mango by $HOME (not XDG_CONFIG_HOME); the
    arctic-* helpers use XDG_CONFIG_HOME. ARCTIC_ETC / ARCTIC_SHARE exist for tests."""

    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.env = env
        self.home = Path(env.get('HOME') or Path.home())
        self.config = Path(env.get('XDG_CONFIG_HOME') or self.home / '.config')
        self.data = Path(env.get('XDG_DATA_HOME') or self.home / '.local/share')
        self.state = Path(env.get('XDG_STATE_HOME') or self.home / '.local/state')
        self.runtime = Path(env.get('XDG_RUNTIME_DIR') or tempfile.gettempdir())
        self.etc = Path(env.get('ARCTIC_ETC') or '/etc/arctic')
        self.share = Path(env.get('ARCTIC_SHARE') or '/usr/share/arctic')
        self.mango = self.home / '.config' / 'mango'
        self.config_conf = self.mango / 'config.conf'
        self.settings_conf = self.mango / 'settings.conf'
        self.user_conf = self.mango / 'user.conf'
        self.arctic = self.config / 'arctic'
        self.default_apps = self.arctic / 'default-apps'
        self.default_apps_system = self.etc / 'default-apps'
        self.idle_conf = self.arctic / 'idle.conf'
        self.mimeapps = self.config / 'mimeapps.list'
        self.backups = self.state / 'arctic' / 'settings-backups'
        self.display_pending = self.runtime / 'arctic-settings-display.json'
        self.lock = self.runtime / 'arctic-settings.lock'

    def expand(self, value):
        """A path as Mango's `source=` resolves it: ~/…, ./… (next to config.conf) or absolute."""
        if value == '~' or value.startswith('~/'):
            return self.home / value[2:]
        if value.startswith('./'):
            return self.mango / value[2:]
        return Path(value)


# ---- small helpers ----------------------------------------------------------------------------

def which(name, env=None):
    return shutil.which(name, path=(env or os.environ).get('PATH'))


def run(argv, timeout=10, input_text=None, env=None):
    """Run a command; never raises. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                input=input_text, env=env)
        return result.returncode, result.stdout, result.stderr
    except (OSError, subprocess.SubprocessError) as error:
        return 127, '', str(error)


ANSI = re.compile(r'\x1b\[[0-9;]*m')


def strip_ansi(text):
    return ANSI.sub('', text or '')


def atomic_write(path, text, mode=None):
    """Write text to path through a temporary file in the same folder and a rename, so a
    crash never leaves half a file. A symlinked file is written where the link points."""
    path = Path(path)
    if path.is_symlink():
        path = Path(os.path.realpath(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    if mode is None:
        try:
            mode = path.stat().st_mode & 0o777
        except OSError:
            mode = 0o644
    fd, tmp = tempfile.mkstemp(prefix='.' + path.name + '.', dir=str(path.parent))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def backup_stamp(paths, name):
    """A name part for the next backup of `name` that sorts after every backup it already has.
    One clock reading (seconds and microseconds from two readings could go backwards across a
    second), and never earlier than the newest backup, so undo always takes the latest one."""
    def micros(stamp):
        day, micro = stamp.rsplit('-', 1)
        return int(time.mktime(time.strptime(day, '%Y%m%d-%H%M%S'))) * 1000000 + int(micro)
    now = time.time_ns() // 1000
    olds = sorted(p.name[len(name) + 1:].split('.')[0] for p in paths.backups.glob(name + '.*'))
    if olds:
        try:
            now = max(now, micros(olds[-1]) + 1)
        except ValueError:
            pass
    return time.strftime('%Y%m%d-%H%M%S', time.localtime(now // 1000000)) + '-%06d' % (now % 1000000)


def backup(paths, path):
    """Copy path into the backups folder (newest BACKUPS_KEPT per file). Returns the copy."""
    path = Path(path)
    if not path.is_file():
        return None
    paths.backups.mkdir(parents=True, exist_ok=True)
    target = paths.backups / '{}.{}'.format(path.name, backup_stamp(paths, path.name))
    shutil.copy2(path, target)
    olds = sorted(paths.backups.glob(path.name + '.*'))
    for old in olds[:-BACKUPS_KEPT]:
        try:
            old.unlink()
        except OSError:
            pass
    return target


ABSENT = '.absent'   # a backup meaning "there was no file yet" (undo deletes the file)


def backup_absent(paths, path):
    """Record in the backups that path didn't exist, so the first change can be undone too."""
    path = Path(path)
    paths.backups.mkdir(parents=True, exist_ok=True)
    target = paths.backups / '{}.{}{}'.format(path.name, backup_stamp(paths, path.name), ABSENT)
    target.write_text('', encoding='utf-8')
    return target


@contextlib.contextmanager
def settings_lock(paths):
    """One writer at a time: every command that reads, changes and writes back a file holds this
    for the whole read-change-write, so two quick changes from the app can't overwrite each other."""
    paths.lock.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(paths.lock), os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)     # releases the lock


def read_text(path):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return None


# ---- Mango config lines -----------------------------------------------------------------------

def strip_comment(line):
    """Mango's remove_comment(): '#' starts a comment when it follows whitespace, outside
    quotes. A line that starts with '#' is skipped before that."""
    if line.startswith('#'):
        return ''
    quote = ''
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ''
        elif ch in '\'"':
            quote = ch
        elif ch == '#' and i > 0 and line[i - 1].isspace():
            return line[:i]
    return line


def split_line(line):
    """'key = value' → (key, value) as Mango's parser sees it, or None."""
    text = strip_comment(line.rstrip('\n'))
    if '=' not in text:
        return None
    key, value = text.split('=', 1)
    key = key.strip()
    if not key:
        return None
    return key, value.strip()


def read_chain(paths):
    """Every key=value Mango reads, in order, following source= / source-optional= from
    ~/.config/mango/config.conf. Returns [(key, value, file path string)]."""
    out = []
    stack = []

    def visit(path, depth):
        real = os.path.realpath(str(path))
        if depth > 10 or real in stack:
            return
        text = read_text(path)
        if text is None:
            return
        stack.append(real)
        for line in text.splitlines():
            pair = split_line(line)
            if not pair:
                continue
            key, value = pair
            if key in ('source', 'source-optional'):
                visit(paths.expand(value), depth + 1)
            else:
                out.append((key, value, str(path)))
        stack.pop()

    visit(paths.config_conf, 0)
    return out


def same_file(a, b):
    try:
        return os.path.realpath(str(a)) == os.path.realpath(str(b))
    except OSError:
        return False


# ---- the options Settings exposes ---------------------------------------------------------------
# Every key below is parsed by Mango 0.17.3 (src/config/parse_config.c; the test compares this
# table with settings/tests/mango-0.17.3-keys.txt). (kind, low, high, Mango's own default).

B = ('bool', 0, 1)
OPTIONS = {
    # windows and gaps
    'gappih': ('int', 0, 64, 5), 'gappiv': ('int', 0, 64, 5),
    'gappoh': ('int', 0, 64, 10), 'gappov': ('int', 0, 64, 10),
    'borderpx': ('int', 0, 16, 4), 'border_radius': ('int', 0, 32, 0),
    'no_border_when_single': B + (0,), 'no_radius_when_single': B + (0,), 'smartgaps': B + (0,),
    'focused_opacity': ('float', 0.3, 1.0, 1.0), 'unfocused_opacity': ('float', 0.3, 1.0, 1.0),
    # effects and motion
    'animations': B + (1,), 'layer_animations': B + (1,),
    'animation_duration_open': ('int', 0, 2000, 400), 'animation_duration_move': ('int', 0, 2000, 500),
    'animation_duration_tag': ('int', 0, 2000, 300), 'animation_duration_close': ('int', 0, 2000, 300),
    'blur': B + (0,), 'blur_layer': B + (0,), 'shadows': B + (0,), 'layer_shadows': B + (0,),
    # focus and layout
    'sloppyfocus': B + (1,), 'warpcursor': B + (1,), 'focus_on_activate': B + (1,),
    'new_is_master': B + (1,), 'default_mfact': ('float', 0.1, 0.9, 0.55),
    'enable_hotarea': B + (0,), 'hotarea_corner': ('int', 0, 3, 2),
    # cursor
    'cursor_size': ('int', 12, 128, 24), 'cursor_theme': ('cursor', 0, 0, ''),
    'cursor_hide_timeout': ('int', 0, 600, 0),
    # keyboard
    'repeat_rate': ('int', 1, 100, 25), 'repeat_delay': ('int', 100, 2000, 600), 'numlockon': B + (0,),
    'xkb_rules_layout': ('layout', 0, 0, 'us'), 'xkb_rules_variant': ('variant', 0, 0, ''),
    'xkb_rules_options': ('xkboptions', 0, 0, ''),
    # touchpad
    'disable_trackpad': B + (0,), 'tap_to_click': B + (1,), 'tap_and_drag': B + (1,), 'drag_lock': B + (1,),
    'trackpad_natural_scrolling': B + (0,), 'trackpad_disable_while_typing': B + (1,),
    'trackpad_middle_button_emulation': B + (0,), 'trackpad_left_handed': B + (0,),
    'trackpad_accel_profile': ('int', 0, 2, 2), 'trackpad_accel_speed': ('float', -1.0, 1.0, 0.0),
    'trackpad_scroll_factor': ('float', 0.1, 10.0, 1.0), 'trackpad_click_method': ('int', 0, 2, 1),
    # mouse
    'mouse_natural_scrolling': B + (0,), 'mouse_left_handed': B + (0,),
    'mouse_accel_profile': ('int', 0, 2, 2), 'mouse_accel_speed': ('float', -1.0, 1.0, 0.0),
    'axis_scroll_factor': ('float', 0.1, 10.0, 1.0),
}
# Keys that may be set to nothing (clearing a value the installer wrote in keyboard.conf).
# Mango rejects "key=" with no value, so they are written "key= # none": the comment is cut
# off and the value trims to "".
EMPTY_OK = {'xkb_rules_variant', 'xkb_rules_options'}
LAYOUTS = ['tile', 'scroller', 'monocle', 'grid', 'deck', 'center_tile', 'vertical_tile',
           'right_tile', 'vertical_scroller', 'vertical_grid', 'vertical_deck', 'dwindle',
           'fair', 'vertical_fair']

RE_LAYOUT = re.compile(r'^[A-Za-z0-9_-]+(,[A-Za-z0-9_-]+){0,3}$')
RE_VARIANT = re.compile(r'^[A-Za-z0-9_-]*(,[A-Za-z0-9_-]*){0,3}$')
RE_XKBOPT = re.compile(r'^[a-z0-9_]+:[A-Za-z0-9_+-]+$')
RE_CURSOR = re.compile(r'^[A-Za-z0-9 _.+-]{1,64}$')


def format_number(value):
    text = ('%.3f' % value).rstrip('0').rstrip('.')
    return '0' if text in ('-0', '') else text


def normalise(key, raw):
    """Validate one option value and return it the way it is written. Raises Failure."""
    if key not in OPTIONS:
        raise Failure('Settings doesn’t know the option “{}”.'.format(key))
    kind, low, high = OPTIONS[key][:3]
    value = str(raw).strip()
    if len(value) > MAX_VALUE or '\n' in value or '\r' in value:
        raise Failure('That value for {} is too long.'.format(key))
    if kind in ('bool', 'int'):
        if value.lower() in ('true', 'on', 'yes') and kind == 'bool':
            value = '1'
        elif value.lower() in ('false', 'off', 'no') and kind == 'bool':
            value = '0'
        if not re.fullmatch(r'-?\d+', value):
            raise Failure('{} needs a whole number.'.format(key))
        number = int(value)
        if not low <= number <= high:
            raise Failure('{} must be between {} and {}.'.format(key, low, high))
        return str(number)
    if kind == 'float':
        try:
            number = float(value)
        except ValueError:
            raise Failure('{} needs a number.'.format(key)) from None
        if number != number or not low - 1e-9 <= number <= high + 1e-9:
            raise Failure('{} must be between {} and {}.'.format(key, format_number(low), format_number(high)))
        return format_number(number)
    if kind == 'layout':
        if not RE_LAYOUT.match(value):
            raise Failure('Pick between one and four keyboard layouts.')
        return value
    if kind == 'variant':
        if not RE_VARIANT.match(value):
            raise Failure('That keyboard variant isn’t valid.')
        return value
    if kind == 'xkboptions':
        if value and not all(RE_XKBOPT.match(part) for part in value.split(',')):
            raise Failure('That keyboard option isn’t valid.')
        return value
    if kind == 'cursor':
        if not RE_CURSOR.match(value):
            raise Failure('That cursor theme name isn’t valid.')
        return value
    raise Failure('Unknown kind of option.')


def clamp_option(key, raw):
    """normalise(), except that a number outside Settings' range (a hand edit such as
    borderpx=20) is brought into it rather than refused. Raises Failure for anything else."""
    try:
        return normalise(key, raw)
    except Failure:
        kind, low, high = OPTIONS[key][:3]
        if kind not in ('int', 'float'):
            raise
        try:
            number = float(str(raw).strip()) if kind == 'float' else int(str(raw).strip())
        except ValueError:
            raise Failure('not a number') from None
        if number != number:
            raise
        return normalise(key, min(max(number, low), high))


# ---- settings.conf model ------------------------------------------------------------------------

class SettingsFile:
    """~/.config/mango/settings.conf as data: options, default layout, monitor rules, custom
    shortcuts, startup commands, and any other lines (kept verbatim at the end)."""

    def __init__(self):
        self.options = {}
        self.layout = ''
        self.monitors = []      # [{name, width, height, refresh, x, y, scale, rr, vrr, disable}]
        self.binds = []         # [{mods, key, command}]
        self.startup = []       # [command]
        self.extra = []         # other lines, verbatim

    @classmethod
    def parse(cls, text):
        model = cls()
        keymode = 'default'
        for line in (text or '').splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            pair = split_line(line)
            if not pair:
                model.extra.append(line)
                continue
            key, value = pair
            if key == 'keymode':
                # Binds after another keymode belong to it: keep them (and the way back to
                # default) verbatim, so they never turn into default-mode shortcuts.
                if value != 'default' or keymode != 'default':
                    model.extra.append(line)
                keymode = value
            elif key == 'bind' and keymode != 'default':
                model.extra.append(line)
            elif key in OPTIONS:
                try:
                    if value == '' and key not in EMPTY_OK:
                        raise Failure('empty')
                    model.options[key] = clamp_option(key, value) if value else ''
                except Failure:
                    model.extra.append(line)
            elif key == 'tagrule' and re.fullmatch(r'id:\*,layout_name:([a-z_]+)', value) \
                    and value.split(':')[-1] in LAYOUTS:
                model.layout = value.split(':')[-1]
            elif key == 'monitorrule':
                rule = parse_monitor_rule(value)
                if rule:
                    model.monitors.append(rule)
                else:
                    model.extra.append(line)
            elif key == 'bind':
                parts = value.split(',', 3)
                if len(parts) == 4 and parts[2].strip() == 'spawn_shell' and _mods_ok(parts[0]):
                    model.binds.append(dict(mods=parts[0].strip(), key=parts[1].strip(), command=parts[3].strip()))
                else:
                    model.extra.append(line)
            elif key == 'exec-once':
                model.startup.append(value)
            else:
                model.extra.append(line)
        return model

    def render(self):
        out = [HEADER.rstrip('\n')]
        if self.options:
            out.append('')
            out.append('# ---- Options')
            for key in OPTIONS:
                if key in self.options:
                    value = self.options[key]
                    out.append('{}= # none'.format(key) if value == '' else '{}={}'.format(key, value))
        if self.layout:
            out.append('')
            out.append('# ---- Default layout for every workspace')
            out.append('tagrule=id:*,layout_name:{}'.format(self.layout))
        if self.monitors:
            out.append('')
            out.append('# ---- Displays')
            for rule in self.monitors:
                out.append('monitorrule=' + format_monitor_rule(rule))
        if self.binds:
            out.append('')
            out.append('# ---- Your shortcuts (Mango uses the first bind for a key, so these add, never replace)')
            out.append('keymode=default')
            for bind in self.binds:
                out.append('bind={},{},spawn_shell,{}'.format(bind['mods'], bind['key'], bind['command']))
        if self.startup:
            out.append('')
            out.append('# ---- Startup apps (run once when you log in)')
            for command in self.startup:
                out.append('exec-once=' + command)
        if self.extra:
            out.append('')
            out.append('# ---- Kept from before (not written by Settings)')
            out.extend(self.extra)
            modes = [pair[1] for pair in map(split_line, self.extra) if pair and pair[0] == 'keymode']
            if modes and modes[-1] != 'default':
                out.append('keymode=default')     # files read after this one start in default mode
        text = '\n'.join(out).rstrip('\n') + '\n'
        for line in text.splitlines():
            if len(line.encode('utf-8')) > MAX_LINE:
                raise Failure('A line in settings.conf would be too long for Mango.')
        return text

    def drop_extra(self, keys):
        """Forget kept lines that set one of keys: Settings now writes those keys itself, and a
        later line in the file would otherwise win in Mango."""
        keys = set(keys)
        self.extra = [line for line in self.extra if (split_line(line) or ('',))[0] not in keys]


def _mods_ok(text):
    try:
        parse_mods(text)
        return True
    except Failure:
        return False


MONITOR_KEYS = ('name', 'width', 'height', 'refresh', 'x', 'y', 'scale', 'rr', 'vrr', 'disable')
RE_OUTPUT = re.compile(r'^[A-Za-z0-9_-]{1,64}$')


def parse_monitor_rule(value):
    rule = {}
    for token in value.split(','):
        if ':' not in token:
            return None
        key, val = token.split(':', 1)
        key, val = key.strip(), val.strip()
        if key == 'name':
            match = re.fullmatch(r'\^([A-Za-z0-9_-]+)\$', val)
            if not match:
                return None
            rule['name'] = match.group(1)
        elif key in ('width', 'height', 'x', 'y', 'rr', 'vrr', 'disable'):
            if not re.fullmatch(r'-?\d+', val):
                return None
            rule[key] = int(val)
        elif key in ('refresh', 'scale'):
            try:
                rule[key] = float(val)
            except ValueError:
                return None
        else:
            return None
    return rule if 'name' in rule else None


def format_monitor_rule(rule):
    if not RE_OUTPUT.match(str(rule.get('name', ''))):
        raise Failure('That display name isn’t valid.')
    parts = ['name:^{}$'.format(rule['name'])]
    for key in MONITOR_KEYS[1:]:
        if key not in rule or rule[key] is None:
            continue
        value = rule[key]
        parts.append('{}:{}'.format(key, format_number(value) if isinstance(value, float) else int(value)))
    return ','.join(parts)


# ---- reading and writing settings.conf ------------------------------------------------------------

def load_settings(paths):
    return SettingsFile.parse(read_text(paths.settings_conf) or '')


def mango_check(text, env=None):
    """Let Mango's own parser read the file (`mango -c FILE -p`). Returns an error sentence or
    ''. Skipped (returns '') when Mango isn't installed, e.g. in CI."""
    mango = which('mango', env)
    if not mango:
        return ''
    with tempfile.TemporaryDirectory(prefix='arctic-settings-') as folder:
        path = Path(folder) / 'settings.conf'
        path.write_text(text, encoding='utf-8')
        code, out, err = run([mango, '-c', str(path), '-p'], timeout=15)
    output = strip_ansi(out + err)
    # `mango -p` exits 0 when it also found a key-binding clash, so read its output as well.
    errors = [line.strip() for line in output.splitlines() if '[ERROR]' in line]
    if code not in (0, 127) or errors:
        detail = errors[0].replace('[ERROR]:', '').strip() if errors else 'it could not read the file'
        return 'Mango would reject this change ({}).'.format(detail)
    return ''


def ensure_sourced(paths):
    """Add `source-optional=~/.config/mango/settings.conf` to config.conf (just before the
    user.conf line) when it isn't there. Returns 'present', 'added' or 'missing'."""
    text = read_text(paths.config_conf)
    if text is None:
        return 'missing'
    lines = text.splitlines(keepends=True)
    for line in lines:
        pair = split_line(line)
        if pair and pair[0] in ('source', 'source-optional') and \
                same_file(paths.expand(pair[1]), paths.settings_conf):
            return 'present'
    insert = len(lines)
    for i, line in enumerate(lines):
        pair = split_line(line)
        if pair and pair[0] in ('source', 'source-optional') and \
                same_file(paths.expand(pair[1]), paths.user_conf):
            insert = i
            break
    if insert == len(lines) and lines and not lines[-1].endswith('\n'):
        lines[-1] += '\n'
    lines.insert(insert, SOURCE_LINE + '\n')
    backup(paths, paths.config_conf)
    atomic_write(paths.config_conf, ''.join(lines))
    return 'added'


def reload_mango(env=None):
    """Ask the running Mango to re-read its config. False when it isn't reachable."""
    if not which('mmsg', env):
        return False
    code, _out, _err = run(['mmsg', 'dispatch', 'reload_config'], timeout=5)
    return code == 0


def save_settings(paths, model, reload=True):
    text = model.render()
    old = read_text(paths.settings_conf)
    problem = mango_check(text)
    if problem:
        raise Failure(problem)
    source = ensure_sourced(paths)
    if old != text:
        if old is None:
            backup_absent(paths, paths.settings_conf)
        else:
            backup(paths, paths.settings_conf)
        atomic_write(paths.settings_conf, text)
    # Only when Mango has something new to read: a reload re-applies every rule, monitor rules
    # included, so a save that changed nothing shouldn't make Mango redo the screens.
    reloaded = reload_mango() if reload and (old != text or source == 'added') else False
    return dict(ok=True, source=source, reloaded=reloaded, changed=old != text)


# ---- state --------------------------------------------------------------------------------------

def mango_state(paths):
    chain = read_chain(paths)
    model = load_settings(paths)
    in_settings = {}
    last = {}
    arctic = {}
    for index, (key, value, origin) in enumerate(chain):
        if key not in OPTIONS:
            continue
        last[key] = (value, origin, index)
        if same_file(origin, paths.settings_conf):
            in_settings[key] = index
        else:
            arctic[key] = value
    options = {}
    for key, spec in OPTIONS.items():
        default = spec[3]
        value, origin, index = last.get(key, (None, '', -1))
        if value is None:
            value = format_number(default) if isinstance(default, float) else str(default)
        overridden = key in in_settings and index > in_settings[key]
        options[key] = dict(value=value, origin=origin,
                            set=key in model.options, overridden=overridden,
                            arctic=arctic.get(key, format_number(default) if isinstance(default, float) else str(default)))
    layouts = [value.split('layout_name:')[-1].split(',')[0] for key, value, _ in chain
               if key == 'tagrule' and 'layout_name:' in value]
    sourced = any(same_file(origin, paths.settings_conf) for _k, _v, origin in chain) or \
        _config_mentions_settings(paths)
    return dict(ok=True, options=options, layout=model.layout, layouts=LAYOUTS,
                arcticLayout=layouts[0] if layouts else 'tile',
                monitors=model.monitors, customBinds=model.binds, startup=model.startup,
                extraLines=len(model.extra), settingsFile=str(paths.settings_conf),
                sourced=sourced, configExists=paths.config_conf.is_file(),
                undo=bool(list(paths.backups.glob('settings.conf.*'))) if paths.backups.is_dir() else False)


def _config_mentions_settings(paths):
    text = read_text(paths.config_conf) or ''
    for line in text.splitlines():
        pair = split_line(line)
        if pair and pair[0] in ('source', 'source-optional') and same_file(paths.expand(pair[1]), paths.settings_conf):
            return True
    return False


def cmd_set(paths, args):
    if not args:
        raise Failure('Nothing to change.')
    model = load_settings(paths)
    for arg in args:
        if '=' not in arg:
            raise Failure('Expected KEY=VALUE, got “{}”.'.format(arg))
        key, value = arg.split('=', 1)
        key = key.strip()
        if value.strip() == '' and key in EMPTY_OK:
            normalise(key, '')      # known key
            model.options[key] = ''
            continue
        model.options[key] = normalise(key, value)
    model.drop_extra(model.options.keys() & {a.split('=', 1)[0].strip() for a in args})
    if 'xkb_rules_variant' in model.options and 'xkb_rules_layout' in model.options:
        layouts = model.options['xkb_rules_layout'].count(',') + 1
        if model.options['xkb_rules_variant'].count(',') + 1 > layouts:
            raise Failure('There are more keyboard variants than layouts.')
    result = save_settings(paths, model)
    result.update(mango_state(paths))
    return result


def cmd_reset(paths, args):
    model = load_settings(paths)
    for key in args:
        if key == 'all':
            model.options.clear()
            model.drop_extra(OPTIONS)
        elif key in OPTIONS:
            model.options.pop(key, None)
            model.drop_extra([key])
        else:
            raise Failure('Settings doesn’t know the option “{}”.'.format(key))
    result = save_settings(paths, model)
    result.update(mango_state(paths))
    return result


def cmd_layout(paths, args):
    model = load_settings(paths)
    name = args[0] if args else ''
    if name == '--reset':
        model.layout = ''
    elif name in LAYOUTS:
        model.layout = name
    else:
        raise Failure('Mango has no layout called “{}”.'.format(name))
    result = save_settings(paths, model)
    result.update(mango_state(paths))
    return result


def cmd_undo(paths, _args):
    backups = sorted(paths.backups.glob('settings.conf.*')) if paths.backups.is_dir() else []
    if not backups:
        raise Failure('There’s nothing to undo.')
    newest = backups[-1]
    cursor_before = _cursor_values(mango_state(paths))
    if newest.name.endswith(ABSENT):
        paths.settings_conf.unlink(missing_ok=True)
    else:
        text = newest.read_text(encoding='utf-8')
        problem = mango_check(text)
        if problem:
            raise Failure(problem)
        atomic_write(paths.settings_conf, text)
    newest.unlink()
    result = dict(ok=True, reloaded=reload_mango())
    result.update(mango_state(paths))
    # GTK apps got the cursor through gsettings (set-cursor): give them the restored one too.
    cursor_after = _cursor_values(result)
    if cursor_after != cursor_before:
        apply_cursor_gsettings(cursor_after)
    return result


def _cursor_values(state):
    return {key: state['options'][key]['value'] for key in ('cursor_theme', 'cursor_size')}


# ---- shortcuts ----------------------------------------------------------------------------------

MOD_NAMES = {'SUPER': 'Super', 'LOGO': 'Super', 'SHIFT': 'Shift', 'CTRL': 'Ctrl', 'CONTROL': 'Ctrl',
             'ALT': 'Alt', 'NONE': ''}
KEY_NAMES = {'return': 'Enter', 'space': 'Space', 'slash': '/', 'comma': ',', 'period': '.',
             'escape': 'Esc', 'tab': 'Tab', 'delete': 'Delete', 'backspace': 'Backspace',
             'left': '←', 'right': '→', 'up': '↑', 'down': '↓', 'print': 'Print',
             'page_up': 'Page Up', 'page_down': 'Page Down', 'minus': '-', 'equal': '=',
             'grave': '`', 'semicolon': ';', 'apostrophe': "'", 'bracketleft': '[', 'bracketright': ']',
             'backslash': '\\', 'code:49': '`', 'caps_lock': 'Caps Lock'}
DISPATCHERS = {
    'killclient': 'Close the window', 'togglefloating': 'Float / tile the window',
    'togglemaximizescreen': 'Maximise', 'togglefullscreen': 'Full screen',
    'focusstack': 'Next / previous window', 'toggleoverview': 'Overview', 'zoom': 'Swap with the main window',
    'focusdir': 'Move focus', 'exchange_client': 'Swap with the neighbour', 'setmfact': 'Resize the main area',
    'incnmaster': 'More / fewer main windows', 'switch_layout': 'Next layout', 'view': 'Go to workspace',
    'tag': 'Move the window to a workspace', 'viewtoleft': 'Previous workspace', 'viewtoright': 'Next workspace',
    'tagtoleft': 'Move the window to the previous workspace', 'tagtoright': 'Move the window to the next workspace',
    'focusmon': 'Focus the other monitor', 'tagmon': 'Move the window to the other monitor',
    'reload_config': 'Reload the desktop config', 'quit': 'Log out', 'switch_keyboard_layout': 'Next keyboard layout',
    'switcher': 'Switch windows', 'togglejump': 'Jump to a window', 'focuslast': 'Back to the previous window',
    'toggle_special_tag': 'Scratch workspace', 'tag_special_tag': 'Move the window to the scratch workspace',
    'toggle_named_scratchpad': 'Drop-down window', 'minimized': 'Hide the window',
    'restore_minimized': 'Bring back a hidden window', 'groupjoin': 'Join a tab group',
    'groupfocus': 'Next / previous tab in the group', 'groupleave': 'Leave the tab group',
    'toggleglobal': 'Show the window on every workspace', 'centerwin': 'Centre the window',
    'toggle_trackpad_enable': 'Touchpad on / off', 'toggle_scratchpad': 'Show hidden windows',
    'setlayout': 'Layout',
}
RE_KEY = re.compile(r'^(?:[A-Za-z0-9_]{1,40}|code:\d{1,3})$')
FREE_KEYS = re.compile(r'^(?:F\d{1,2}|XF86\w+|Print|Pause|Scroll_Lock|Menu)$')


def parse_mods(text):
    mods = set()
    for part in text.replace(' ', '').split('+'):
        name = part.upper()
        if name in ('', 'NONE'):
            continue
        if name not in MOD_NAMES:
            raise Failure('“{}” isn’t a modifier Mango knows (Super, Shift, Ctrl, Alt).'.format(part))
        mods.add({'LOGO': 'SUPER', 'CONTROL': 'CTRL'}.get(name, name))
    return mods


def mods_text(mods):
    order = ['SUPER', 'CTRL', 'ALT', 'SHIFT']
    return '+'.join(m for m in order if m in mods) or 'NONE'


def key_label(key):
    lower = key.lower()
    if lower in KEY_NAMES:
        return KEY_NAMES[lower]
    if key.startswith('XF86'):
        return re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', key[4:])
    return key.upper() if len(key) == 1 else key.replace('_', ' ')


def combo_label(mods, key):
    names = [MOD_NAMES[m] for m in ['SUPER', 'CTRL', 'ALT', 'SHIFT'] if m in mods]
    return ' + '.join(names + [key_label(key)])


def combo_id(mods, key):
    """What Mango matches a key press on. code:49 is the key above Tab (grave on us)."""
    key = key.lower()
    return (frozenset(mods), 'grave' if key == 'code:49' else key)


def mark_shadowed(binds):
    """Mango runs only the first bind that matches a key press, unless that bind has the `c`
    flag, so a later bind on the same keys in the same keymode (or in `common`, which applies in
    every mode) never runs. Release binds (`r`) and press binds don't meet."""
    for i, bind in enumerate(binds):
        for earlier in binds[:i]:
            if earlier['combo'] != bind['combo'] or ('r' in earlier['flags']) != ('r' in bind['flags']):
                continue
            if 'c' in earlier['flags']:
                continue
            if earlier['keymode'] != bind['keymode'] and 'common' not in (earlier['keymode'], bind['keymode']):
                continue
            bind['shadowedBy'] = dict(label=earlier['label'], what=earlier['what'],
                                      file=os.path.basename(earlier['file']))
            break
    for bind in binds:
        del bind['combo']
    return binds


def chain_binds(paths):
    """Keyboard binds in the config chain: [{mods, key, action, args, file, keymode, label,
    flags, shadowedBy?}]."""
    out = []
    keymode = 'default'
    for key, value, origin in read_chain(paths):
        if key == 'keymode':
            keymode = value
            continue
        if not re.fullmatch(r'bind[a-z]*', key):
            continue
        parts = [p.strip() for p in value.split(',')]
        if len(parts) < 3:
            continue
        try:
            mods = parse_mods(parts[0])
        except Failure:
            continue
        action = parts[2]
        args = ','.join(parts[3:]).strip(',')
        if action in ('spawn', 'spawn_shell'):
            what = args
        else:
            what = DISPATCHERS.get(action, action.replace('_', ' '))
            if args and action in ('view', 'tag'):
                what += ' ' + args.split(',')[0]
        out.append(dict(mods=sorted(mods), key=parts[1], action=action, args=args, file=origin,
                        keymode=keymode, label=combo_label(mods, parts[1]), what=what,
                        mine=same_file(origin, paths.settings_conf), flags=key[4:],
                        combo=combo_id(mods, parts[1])))
    return mark_shadowed(out)


def arctic_file(paths, origin):
    """A file of Arctic's own (its Mango config, links into /usr/share/arctic, the theme's
    colours), rather than one of yours."""
    if same_file(origin, paths.settings_conf) or same_file(origin, paths.user_conf):
        return False
    real = os.path.realpath(origin)
    return any(real.startswith(os.path.realpath(str(root)) + os.sep)
               for root in (paths.mango / 'arctic', paths.share, paths.arctic, paths.etc))


def parse_sheet(text):
    """keys.txt sections, parsed exactly like the shell's KeysSheet.qml."""
    sections = []
    for line in (text or '').split('\n'):
        if not line.strip():
            continue
        entry = re.match(r'^ {4}(\S.*?)\s{2,}(\S.*)$', line)
        if entry and sections:
            sections[-1]['rows'].append(dict(keys=entry.group(1), what=entry.group(2)))
            continue
        heading = re.match(r'^ {2}(\S.*?)(\s{2,}.*)?$', line)
        if heading and 'Keyboard shortcuts' not in line:
            sections.append(dict(title=heading.group(1), rows=[]))
    return sections


def cmd_binds(paths, _args):
    sheet = ''
    for candidate in (paths.data / 'arctic' / 'keys.txt', paths.share / 'keys.txt'):
        sheet = read_text(candidate)
        if sheet:
            break
    model = load_settings(paths)
    binds = chain_binds(paths)
    mine = []
    for i, b in enumerate(model.binds):
        mods = parse_mods(b['mods'])
        entry = dict(index=i, label=combo_label(mods, b['key']), command=b['command'], mods=b['mods'], key=b['key'])
        shadow = next((c['shadowedBy'] for c in binds if c['mine'] and 'shadowedBy' in c
                       and combo_id(c['mods'], c['key']) == combo_id(mods, b['key'])
                       and c['args'] == b['command']), None)
        if shadow:
            entry['shadowedBy'] = shadow
        mine.append(entry)
    # Your binds (settings.conf, user.conf or a file you sourced) that never run, with the
    # sheet's words for the bind that wins ("Browser" rather than "arctic-open browser").
    sections = parse_sheet(sheet or '')
    words = {row['keys']: row['what'] for section in sections for row in section['rows']}
    for c in binds:
        if 'shadowedBy' in c:
            c['shadowedBy']['sheet'] = words.get(c['shadowedBy']['label'], '')
    shadowed = [dict(label=c['label'], what=c['what'], file=os.path.basename(c['file']), shadowedBy=c['shadowedBy'])
                for c in binds if 'shadowedBy' in c and not arctic_file(paths, c['file'])]
    return dict(ok=True, sheet=sections, all=binds, mine=mine, shadowed=shadowed)


def cmd_notices(paths, _args):
    """Things to say once, at login, about the shortcuts: where 0.3 moved the browser, your own
    shortcuts that an Arctic key now shadows, and copies of Arctic's binds files that don't get
    new keys. Each notice is said once (~/.local/state/arctic/notices.json)."""
    state = paths.state / 'arctic' / 'notices.json'
    try:
        shown = set(json.loads(read_text(state) or '{}').get('shown', []))
    except (ValueError, AttributeError):
        shown = set()
    notices = []
    if 'keys-0.3.0' not in shown:
        notices.append(dict(id='keys-0.3.0', summary='Super + B opens your browser',
                            body='It was Super + W before Arctic Linux 0.3. Super + Shift + S takes a screenshot, '
                                 'and Super + / shows every shortcut.',
                            action=['arctic-keys'], actionLabel='Show shortcuts'))
    shadowed = cmd_binds(paths, [])['shadowed']
    if shadowed:
        ident = 'shadowed-' + '|'.join(sorted('{}:{}'.format(s['label'], s['what']) for s in shadowed))
        if ident not in shown:
            s = shadowed[0]
            notices.append(dict(
                id=ident, summary='A shortcut of yours doesn’t run' if len(shadowed) == 1
                else '{} of your shortcuts don’t run'.format(len(shadowed)),
                body='Arctic’s “{}” shortcut uses {}, so yours ({}) never runs. Pick another key for it.'.format(
                    s['shadowedBy'].get('sheet') or s['shadowedBy']['what'], s['label'], s['what']),
                action=['arctic-settings', 'shortcuts'], actionLabel='Open Shortcuts'))
    for name in ('apps.conf', 'binds.conf'):
        mine, arctic = paths.mango / 'arctic' / name, paths.share / 'mango' / name
        ident = 'copied-{}-0.3.0'.format(name)
        if ident in shown or mine.is_symlink() or not mine.is_file() or not arctic.is_file():
            continue
        if read_text(mine) != read_text(arctic):
            notices.append(dict(
                id=ident, summary='Your copy of {} doesn’t have the new shortcuts'.format(name),
                body='You replaced Arctic’s {} with your own copy, so the keys Arctic Linux 0.3 added '
                     '(Super + B browser, Super + Shift + S screenshot, Alt + Tab) aren’t in it.'.format(name),
                action=['gio', 'open', str(arctic)], actionLabel='Show the new file'))
    if notices:
        state.parent.mkdir(parents=True, exist_ok=True)
        # The shadowed set is remembered as it is now, so a later change is said again.
        kept = {i for i in shown if not i.startswith('shadowed-')} | {n['id'] for n in notices}
        if not any(n['id'].startswith('shadowed-') for n in notices):
            kept |= {i for i in shown if i.startswith('shadowed-')}
        atomic_write(state, json.dumps(dict(shown=sorted(kept))) + '\n')
    return dict(ok=True, notices=notices)


def clipboard_history_on(paths):
    return (read_text(paths.arctic / 'clipboard.conf') or '').split().count('history=off') == 0


def cmd_clipboard(paths, _args):
    entries = 0
    if which('cliphist', paths.env):
        code, out, _err = run(['cliphist', 'list'], env=paths.env)
        entries = len(out.splitlines()) if code == 0 else 0
    return dict(ok=True, history=clipboard_history_on(paths), entries=entries,
                available=bool(which('cliphist', paths.env)))


def cmd_clipboard_set(paths, args):
    if len(args) != 2 or args[0] != 'history' or args[1] not in ('on', 'off'):
        raise Failure('usage: clipboard-set history on|off')
    atomic_write(paths.arctic / 'clipboard.conf',
                 '# Clipboard history (Super + V), set in Settings > Keyboard and mouse.\nhistory={}\n'.format(args[1]))
    run(['arctic-session', 'clipboard', '--restart'], env=paths.env)
    return cmd_clipboard(paths, [])


def cmd_clipboard_clear(paths, _args):
    if not which('cliphist', paths.env) or run(['cliphist', 'wipe'], env=paths.env)[0] != 0:
        raise Failure('Clipboard history couldn’t be cleared.')
    return cmd_clipboard(paths, [])


def validate_command(command, what='command'):
    command = (command or '').strip()
    if not command:
        raise Failure('Type the {} to run.'.format(what))
    if '\n' in command or '\r' in command or len(command) > 200:
        raise Failure('That {} is too long or has more than one line.'.format(what))
    if '#' in command:
        raise Failure('Mango would read “#” as the start of a comment. Put the command in a script instead.')
    if any(ord(ch) < 32 for ch in command):
        raise Failure('That {} has control characters in it.'.format(what))
    return command


def cmd_bind_add(paths, args):
    if len(args) != 3:
        raise Failure('usage: bind-add MODS KEY COMMAND')
    mods = parse_mods(args[0])
    key = args[1].strip()
    if not RE_KEY.match(key):
        raise Failure('“{}” isn’t a key name Mango knows (for example s, F5, Return or code:38).'.format(key))
    if len(key) == 1:
        key = key.lower()
    if not (mods - {'SHIFT'}) and not FREE_KEYS.match(key):
        raise Failure('Add Super, Ctrl or Alt, so the shortcut doesn’t take over a key you type with.')
    layouts, options = chain_keyboard(paths)
    switch = next((o for o in options if o.startswith('grp:')), 'grp:alt_shift_toggle')
    if len(layouts) > 1 and switch_clash(switch, mods, key):
        chord = ' + '.join(MOD_NAMES[m] for m in ['SUPER', 'CTRL', 'ALT', 'SHIFT'] if m in SWITCH_CHORDS[switch][0])
        if SWITCH_CHORDS[switch][1]:
            chord = ' + '.join(filter(None, [chord, key_label(SWITCH_CHORDS[switch][1])]))
        raise Failure('{} switches your keyboard layout, so this shortcut would switch it too. Pick another key, '
                      'or change “Switch layouts with” on the Keyboard and mouse page.'.format(chord))
    command = validate_command(args[2])
    # Mango joins spawn arguments split at commas again, but stops at an empty part or a "0".
    parts = command.split(',')
    if len(parts) > 5 or any(p == '' or p == '0' for p in parts[1:]):
        raise Failure('Mango can’t pass that many commas on. Put the command in a script instead.')
    combo = combo_id(mods, key)
    for bind in chain_binds(paths):
        if bind['keymode'] not in ('default', 'common') or 'r' in bind['flags']:
            continue
        if combo_id(bind['mods'], bind['key']) == combo:
            raise Failure('{} already does something: {}. Pick another key.'.format(bind['label'], bind['what']))
    model = load_settings(paths)
    for bind in model.binds:
        if combo_id(parse_mods(bind['mods']), bind['key']) == combo:
            raise Failure('You already have a shortcut on {}.'.format(combo_label(mods, key)))
    model.binds.append(dict(mods=mods_text(mods), key=key, command=command))
    result = save_settings(paths, model)
    result.update(cmd_binds(paths, []))
    return result


def cmd_bind_remove(paths, args):
    model = load_settings(paths)
    try:
        index = int(args[0])
        model.binds.pop(index)
    except (IndexError, ValueError):
        raise Failure('That shortcut is already gone.') from None
    result = save_settings(paths, model)
    result.update(cmd_binds(paths, []))
    return result


# ---- startup apps -------------------------------------------------------------------------------

def cmd_startup(paths, _args):
    model = load_settings(paths)
    arctic = []
    for key, value, origin in read_chain(paths):
        if key == 'exec-once' and not same_file(origin, paths.settings_conf):
            arctic.append(dict(command=value, file=origin, user=same_file(origin, paths.user_conf)))
    return dict(ok=True, mine=[dict(index=i, command=c) for i, c in enumerate(model.startup)],
                arctic=arctic, apps=[dict(id=e['id'], name=e['name'], icon=e.get('icon', ''))
                                     for e in sorted(desktop_entries(paths).values(),
                                                     key=lambda e: e['name'].lower())
                                     if not e['nodisplay']])


def exec_command(entry):
    """A desktop entry's Exec line without field codes (%f, %U …)."""
    try:
        words = shlex.split(entry.get('exec', ''))
    except ValueError:
        words = entry.get('exec', '').split()
    words = [w for w in words if not re.fullmatch(r'%[fFuUdDnNickvm]', w)]
    return ' '.join(shlex.quote(w) for w in words).replace('%%', '%')


def cmd_startup_add(paths, args):
    if args[:1] == ['--app']:
        entries = desktop_entries(paths)
        entry = entries.get(args[1] if len(args) > 1 else '')
        if not entry:
            raise Failure('That app isn’t installed any more.')
        command = 'gtk-launch ' + entry['id'] if which('gtk-launch') else exec_command(entry)
    else:
        command = ' '.join(args)
    command = validate_command(command)
    model = load_settings(paths)
    if command in model.startup:
        raise Failure('That already starts when you log in.')
    model.startup.append(command)
    result = save_settings(paths, model, reload=False)   # exec-once only runs at login
    result.update(cmd_startup(paths, []))
    return result


def cmd_startup_remove(paths, args):
    model = load_settings(paths)
    try:
        model.startup.pop(int(args[0]))
    except (IndexError, ValueError):
        raise Failure('That startup app is already gone.') from None
    result = save_settings(paths, model, reload=False)
    result.update(cmd_startup(paths, []))
    return result


# ---- displays -----------------------------------------------------------------------------------

# wl_output transforms in their enum order: Mango's monitorrule `rr:` is the index (rr:1 = 90).
TRANSFORMS = ['normal', '90', '180', '270', 'flipped', 'flipped-90', 'flipped-180', 'flipped-270']


# ---- display arrangement (the Displays page's editor; pure geometry) -----------------------------
#
# Mango (wlroots) puts each display at x,y in logical pixels, where it takes the size of its mode,
# turned for 90°/270°, divided by its scale. The pointer only goes from one display to the next
# where their edges touch, and overlapping displays show the same part of the desktop, so a
# layout is kept connected edge to edge without overlaps. XWayland misreads clicks at negative
# positions (Mango's docs), so the top-left corner is 0,0. Mango has no primary display: the
# pointer starts at 0,0, so the display there is where you start after login (focus, the first
# windows, the launcher; Mango keeps XWayland's primary output on the focused display). That is
# the "main" display here. The page only draws; each change to a layout goes through these.

ROTATED = ('90', '270', 'flipped-90', 'flipped-270')
CONTACT_PART = 8        # a snapped display shares at least 1/8 of the shorter of the two edges
DIRECTIONS = {'left': (-1, 0), 'right': (1, 0), 'up': (0, -1), 'down': (0, 1)}


def _f32(value):
    """value in single precision, as wlroots' float arithmetic has it."""
    return struct.unpack('f', struct.pack('f', value))[0]


def logical_size(o):
    """(width, height) a display takes in the layout, as wlroots' wlr_output_effective_resolution
    computes it: the mode, turned for 90° and 270°, divided by the scale in single precision and
    cut to whole pixels (2560 × 1600 at 150 % is 1706 × 1066). Without a mode (mmsg reports only
    the logical size) the physical size is the estimate in physicalWidth/physicalHeight."""
    width = int(o.get('width') or o.get('physicalWidth') or 0)
    height = int(o.get('height') or o.get('physicalHeight') or 0)
    if width <= 0 or height <= 0:
        return max(1, int(o.get('logicalWidth') or 1)), max(1, int(o.get('logicalHeight') or 1))
    if str(o.get('transform') or 'normal') in ROTATED:
        width, height = height, width
    scale = _f32(float(o.get('scale') or 1))
    if scale <= 0:
        scale = 1.0
    return max(1, int(_f32(width / scale))), max(1, int(_f32(height / scale)))


def _box(o):
    width, height = logical_size(o)
    return (int(o.get('x') or 0), int(o.get('y') or 0), width, height)


def overlaps(a, b):
    """Do two boxes (x, y, width, height) share any area?"""
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def contact(a, b):
    """How long an edge two boxes share (0 when they don't touch, or only at a corner)."""
    if a[0] + a[2] == b[0] or b[0] + b[2] == a[0]:
        return max(0, min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1]))
    if a[1] + a[3] == b[1] or b[1] + b[3] == a[1]:
        return max(0, min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0]))
    return 0


def _gap(a, b):
    """Distance between two boxes (0 when they touch or overlap)."""
    dx = max(b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]), 0)
    dy = max(b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]), 0)
    return math.hypot(dx, dy)


def _enabled(layout):
    return [o for o in layout if o.get('enabled', True)]


def _reached(boxes):
    """Indexes of the boxes the pointer can reach from the first one, edge to edge (or through
    an overlap, which layout_problems reports on its own)."""
    reached, todo = {0}, [0]
    while boxes and todo:
        i = todo.pop()
        for j in range(len(boxes)):
            if j not in reached and (contact(boxes[i], boxes[j]) > 0 or overlaps(boxes[i], boxes[j])):
                reached.add(j)
                todo.append(j)
    return reached if boxes else set()


def layout_problems(layout):
    """[] for a good layout, else sentences: displays that overlap, displays cut off from the
    first one (the pointer couldn't reach them)."""
    on = [(o['name'], _box(o)) for o in _enabled(layout)]
    problems = []
    for i, (name_a, a) in enumerate(on):
        for name_b, b in on[i + 1:]:
            if overlaps(a, b):
                problems.append('{} and {} overlap.'.format(name_a, name_b))
    reached = _reached([box for _name, box in on])
    problems += ['{} doesn’t touch the other displays.'.format(on[j][0]) for j in range(len(on)) if j not in reached]
    return problems


def main_output(layout):
    """The display you start on: the one at the layout's top-left corner (Mango starts the
    pointer at 0,0), or the one nearest to that corner when no display covers it (Mango moves
    the pointer to the closest display). '' when every display is off."""
    on = _enabled(layout)
    if not on:
        return ''
    boxes = [_box(o) for o in on]
    left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)

    def distance(b):
        return math.hypot(max(b[0] - left, 0), max(b[1] - top, 0))
    return on[min(range(len(on)), key=lambda i: (distance(boxes[i]), i))]['name']


def _side(box, other):
    """Which side of `other` box lies on, by their centres (right, left, below or above)."""
    dx = (box[0] + box[2] / 2 - other[0] - other[2] / 2) / (box[2] + other[2])
    dy = (box[1] + box[3] / 2 - other[1] - other[3] / 2) / (box[3] + other[3])
    if abs(dx) >= abs(dy):
        return 'right' if dx >= 0 else 'left'
    return 'below' if dy >= 0 else 'above'


def _spots(size, others, target):
    """Places for a box of `size` along each side of each of `others`: the point of that side
    nearest to `target`, and every place on it lined up with an edge or the centre of one of
    them (or flush against one). Yields ((x, y), aligned, side, index of the box it touches,
    the nearest point of that side)."""
    w, h = size
    xs, ys = set(), set()
    for bx, by, bw, bh in others:
        xs.update((bx, bx + bw - w, bx + (bw - w) // 2, bx - w, bx + bw))
        ys.update((by, by + bh - h, by + (bh - h) // 2, by - h, by + bh))
    for i, (bx, by, bw, bh) in enumerate(others):
        need_y = max(1, min(h, bh) // CONTACT_PART)
        need_x = max(1, min(w, bw) // CONTACT_PART)
        for side, fixed, lo, hi, free, aligned in (
                ('right', bx + bw, by - h + need_y, by + bh - need_y, target[1], ys),
                ('left', bx - w, by - h + need_y, by + bh - need_y, target[1], ys),
                ('below', by + bh, bx - w + need_x, bx + bw - need_x, target[0], xs),
                ('above', by - h, bx - w + need_x, bx + bw - need_x, target[0], xs)):
            flat = side in ('right', 'left')
            near = min(max(free, lo), hi)
            nearest = (fixed, near) if flat else (near, fixed)
            for v in {near} | {v for v in aligned if lo <= v <= hi}:
                yield ((fixed, v) if flat else (v, fixed)), v in aligned, side, i, nearest


def default_threshold(size):
    """How far (logical px) a display jumps to line up with another: 1/20 of its longer side."""
    return max(16, max(size) // 20)


def snap_position(size, others, target, threshold=None, bound=None, prefer=None):
    """Where a box of `size` dropped at `target` goes: the nearest place where it touches one of
    `others` along an edge (at least 1/8 of it) without overlapping any. A place lined up with
    their edges or centres wins when it is within `threshold` px of that along the edge.
    bound=(x, y): not left of x nor above y. prefer=a box: places on the side of each neighbour
    that box was on come first (so a display that was right of another stays right of it)."""
    w, h = size
    target = (int(round(target[0])), int(round(target[1])))
    threshold = default_threshold(size) if threshold is None else threshold
    best = None
    for (x, y), aligned, side, i, nearest in _spots(size, others, target):
        if bound and (x < bound[0] or y < bound[1]):
            continue
        if any(overlaps((x, y, w, h), b) for b in others):
            continue
        away = 0 if prefer is None or _side(prefer, others[i]) == side else 1
        # How far to that side, then along it; lining up is worth `threshold` along the edge.
        along = abs(x - nearest[0]) + abs(y - nearest[1])
        score = math.hypot(nearest[0] - target[0], nearest[1] - target[1]) + along - (threshold if aligned else 0)
        key = (away, score, not aligned, y, x)
        if best is None or key < best[0]:
            best = (key, (x, y))
    if best:
        return best[1]
    # Never reached with a bound at a box's corner, but to be safe: right of everything.
    right = max(others, key=lambda b: b[0] + b[2])
    return right[0] + right[2], right[1]


def _fits(box, placed, bound):
    return (not bound or (box[0] >= bound[0] and box[1] >= bound[1])) \
        and not any(overlaps(box, b) for b in placed) and any(contact(box, b) > 0 for b in placed)


def normalize_layout(layout, anchor=None, main=None):
    """A tidy copy of layout: the displays that are on touch edge to edge without overlapping,
    and the top-left corner is 0,0. `anchor` keeps its place and the others settle around it
    (default: the main display): one that touches a settled display without overlapping keeps
    its place; otherwise it moves to the nearest free place next to them, on the side it was
    on. The main display stays the main one (it keeps the top-left corner); `main` makes a
    given display the main one instead. Each display gets logicalWidth, logicalHeight and main.
    A layout that is already tidy only moves to 0,0."""
    items = [dict(o) for o in layout]
    for o in items:
        o['x'], o['y'] = int(o.get('x') or 0), int(o.get('y') or 0)
    on = _enabled(items)
    if on:
        names = [o['name'] for o in on]
        forced = main in names
        main = main if forced else main_output(items)
        first = on[names.index(main)]
        left, top = min(o['x'] for o in on), min(o['y'] for o in on)
        corner = (first['x'], first['y'])
        bound = corner if forced or corner == (left, top) else None
        start = on[names.index(anchor)] if anchor in names else first
        boxes = [_box(start)]
        rest = [o for o in on if o is not start]
        while rest:
            fits = [o for o in rest if _fits(_box(o), boxes, bound)]
            if fits:
                o = fits[0]
            else:
                o = min(rest, key=lambda p: min(_gap(_box(p), b) for b in boxes))
                box = _box(o)
                o['x'], o['y'] = snap_position(box[2:], boxes, box[:2], bound=bound, prefer=box)
            rest.remove(o)
            boxes.append(_box(o))
        left, top = min(b[0] for b in boxes), min(b[1] for b in boxes)
        for o in items:
            o['x'] -= left
            o['y'] -= top
    main = main_output(items)
    for o in items:
        o['logicalWidth'], o['logicalHeight'] = logical_size(o)
        o['main'] = o['name'] == main
    return items


def _output(layout, name, enabled=None):
    for o in layout:
        if o.get('name') == name:
            if enabled and not o.get('enabled', True):
                raise Failure('{} is off.'.format(name))
            return o
    raise Failure('{} isn’t connected.'.format(name))


def snap_output(layout, name, x, y, threshold=None):
    """Drop display `name` at x,y (logical px, in the layout's coordinates): it goes to the
    nearest place touching another display (snap_position), and displays it no longer connected
    settle next to the rest."""
    items = [dict(o) for o in layout]
    moving = _output(items, name, enabled=True)
    others = [_box(o) for o in _enabled(items) if o is not moving]
    if others:
        moving['x'], moving['y'] = snap_position(logical_size(moving), others, (x, y), threshold)
    return normalize_layout(items, anchor=name)


def nudge_output(layout, name, direction):
    """An arrow key on display `name`: it moves a step (1/10 of its size) that way along the
    edge it sits on, stopping where it lines up with an edge or centre of another display, and
    goes round a corner at the end of the edge; places where every display still touches the
    rest come first. It stays where it is when there's no place that way."""
    if direction not in DIRECTIONS:
        raise Failure('Move a display left, right, up or down.')
    items = [dict(o) for o in layout]
    moving = _output(items, name, enabled=True)
    box = _box(moving)
    others = [_box(o) for o in _enabled(items) if o is not moving]
    dx, dy = DIRECTIONS[direction]
    step = max(8, (box[3] if dy else box[2]) // 10)
    best = None
    for (x, y), _aligned, _where, _i, _nearest in _spots(box[2:], others, (box[0] + dx * step, box[1] + dy * step)):
        moved = (x, y) + box[2:]
        if any(overlaps(moved, b) for b in others):
            continue
        along = (x - box[0]) * dx + (y - box[1]) * dy
        across = abs((x - box[0]) * dy) + abs((y - box[1]) * dx)
        cut_off = len(_reached([moved] + others)) <= len(others)
        key = (cut_off, along + 2 * across, y, x)
        if along > 0 and (best is None or key < best[0]):
            best = (key, (x, y))
    if best:
        moving['x'], moving['y'] = best[1]
    return normalize_layout(items, anchor=name)


def make_main(layout, name):
    """Make `name` the main display (where you start; Mango has no other notion of primary):
    it trades places with the display at the top-left corner, and the others settle round."""
    items = [dict(o) for o in layout]
    new = _output(items, name, enabled=True)
    old = _output(items, main_output(items))
    if new is not old:
        (new['x'], new['y']), (old['x'], old['y']) = (old['x'], old['y']), (new['x'], new['y'])
    return normalize_layout(items, anchor=name, main=name)


def set_output_enabled(layout, name, enabled):
    """Switch a display on (it joins at the right of the others) or off (the rest close up).
    The last display that is on can't be switched off."""
    items = [dict(o) for o in layout]
    target = _output(items, name)
    if enabled and not target.get('enabled', True):
        boxes = [_box(o) for o in _enabled(items)]
        target['enabled'] = True
        if boxes:
            target['x'] = max(b[0] + b[2] for b in boxes)
            target['y'] = min(b[1] for b in boxes)
    elif not enabled and target.get('enabled', True):
        if len(_enabled(items)) == 1:
            raise Failure('At least one display has to stay on.')
        target['enabled'] = False
    return normalize_layout(items)


def list_outputs():
    """[(outputs, backend)]: wlr-randr --json when installed (full mode lists), else mmsg
    (current size only)."""
    if which('wlr-randr'):
        code, out, _err = run(['wlr-randr', '--json'], timeout=5)
        if code == 0:
            try:
                return [normalise_wlr(o) for o in json.loads(out)], 'wlr-randr'
            except (ValueError, TypeError, KeyError):
                pass
    if which('mmsg'):
        code, out, _err = run(['mmsg', 'get', 'all-monitors'], timeout=5)
        if code == 0:
            try:
                monitors = json.loads(out).get('monitors', [])
                # No mode (width 0 = keep it); the physical size is estimated for the editor.
                return [dict(name=m.get('name', ''), description='', make='', model='', enabled=True,
                             modes=[], width=0, height=0, refresh=0, x=m.get('x', 0), y=m.get('y', 0),
                             scale=m.get('scale', 1), transform='normal', adaptiveSync=bool(m.get('is_vrr')),
                             logicalWidth=m.get('width', 0), logicalHeight=m.get('height', 0),
                             physicalWidth=round(m.get('width', 0) * (m.get('scale') or 1)),
                             physicalHeight=round(m.get('height', 0) * (m.get('scale') or 1)))
                        for m in monitors], 'mmsg'
            except (ValueError, AttributeError):
                pass
    return [], ''


def normalise_wlr(o):
    modes = [dict(width=m['width'], height=m['height'], refresh=round(float(m.get('refresh', 0)), 3),
                  preferred=bool(m.get('preferred')), current=bool(m.get('current')))
             for m in o.get('modes', [])]
    # A display that is off has no current mode: it would come back in its preferred one.
    current = next((m for m in modes if m['current']), None) or \
        next((m for m in modes if m['preferred']), modes[0] if modes else None)
    pos = o.get('position') or {}
    item = dict(name=o.get('name', ''), description=o.get('description', ''), make=o.get('make') or '',
                model=o.get('model') or '', serial=o.get('serial') or '', enabled=bool(o.get('enabled', True)),
                modes=modes, width=current['width'] if current else 0, height=current['height'] if current else 0,
                refresh=current['refresh'] if current else 0, x=int(pos.get('x', 0)), y=int(pos.get('y', 0)),
                scale=float(o.get('scale') or 1), transform=o.get('transform') or 'normal',
                adaptiveSync=bool(o.get('adaptive_sync')))
    item['logicalWidth'], item['logicalHeight'] = logical_size(item)
    return item


EDIT_KEYS = ('name', 'enabled', 'width', 'height', 'refresh', 'x', 'y', 'scale', 'transform', 'adaptiveSync',
             'logicalWidth', 'logicalHeight', 'physicalWidth', 'physicalHeight')


def cmd_displays(paths, _args):
    """The displays as they are (outputs), and the same layout tidied for the editor (arranged:
    only what a layout holds; the same unless displays overlap or don't touch)."""
    outputs, backend = list_outputs()
    pending = read_text(paths.display_pending)
    main = main_output(outputs)
    for o in outputs:
        o['main'] = o['name'] == main
    arranged = normalize_layout([{k: o[k] for k in EDIT_KEYS if k in o} for o in outputs])
    return dict(ok=True, outputs=outputs, arranged=arranged, main=main, problems=layout_problems(outputs),
                backend=backend, rules=load_settings(paths).monitors,
                canApply=backend in ('wlr-randr', 'mmsg'), canChangeMode=backend == 'wlr-randr',
                pending=bool(pending), revertAfter=REVERT_AFTER)


def _layout_arg(text):
    try:
        layout = json.loads(text)
    except ValueError:
        raise Failure('The display settings came in garbled.') from None
    if not isinstance(layout, list) or not layout or not all(isinstance(o, dict) for o in layout):
        raise Failure('No displays to set up.')
    return layout


def cmd_display_arrange(paths, args):
    """The editor's moves (nothing is applied): the layout after one of --move NAME X Y
    [--threshold PX], --nudge NAME DIRECTION, --main NAME, --enable NAME, --disable NAME,
    --anchor NAME (NAME changed size: the others settle around it), or none (just tidy it)."""
    if not args:
        raise Failure('No displays to set up.')
    layout = check_layout(_layout_arg(args[0]), tidy=False)
    rest = list(args[1:])
    threshold = None
    if '--threshold' in rest:
        i = rest.index('--threshold')
        try:
            threshold = max(0, int(float(rest[i + 1])))
        except (IndexError, ValueError):
            raise Failure('The snapping distance isn’t a number.') from None
        del rest[i:i + 2]
    op, names = (rest[0], rest[1:]) if rest else ('', [])
    try:
        if op == '--move' and len(names) == 3:
            layout = snap_output(layout, names[0], float(names[1]), float(names[2]), threshold)
        elif op == '--nudge' and len(names) == 2:
            layout = nudge_output(layout, names[0], names[1])
        elif op == '--main' and len(names) == 1:
            layout = make_main(layout, names[0])
        elif op in ('--enable', '--disable') and len(names) == 1:
            layout = set_output_enabled(layout, names[0], op == '--enable')
        elif op == '--anchor' and len(names) == 1:
            layout = normalize_layout(layout, anchor=names[0])
        elif not op:
            layout = normalize_layout(layout)
        else:
            raise Failure('Settings asked for a display move it doesn’t know.')
    except ValueError:
        raise Failure('That position isn’t a number.') from None
    return dict(ok=True, outputs=layout, main=main_output(layout), problems=layout_problems(layout))


def check_layout(outputs, tidy=True):
    """Validate a display layout from the app; returns it cleaned and, with tidy, arranged
    (normalize_layout: touching, no overlaps, from 0,0; a tidy layout only moves to 0,0)."""
    if not isinstance(outputs, list) or not outputs or not all(isinstance(o, dict) for o in outputs):
        raise Failure('No displays to set up.')
    clean = []
    for o in outputs:
        name = str(o.get('name', ''))
        if not RE_OUTPUT.match(name):
            raise Failure('That display name isn’t valid.')
        if any(c['name'] == name for c in clean):
            raise Failure('{} is in the layout twice.'.format(name))
        item = dict(name=name, enabled=bool(o.get('enabled', True)))
        try:
            item['width'] = int(o.get('width') or 0)       # 0: keep the current mode
            item['height'] = int(o.get('height') or 0)
            item['refresh'] = round(float(o.get('refresh') or 0), 3)
            item['x'] = int(o.get('x', 0))
            item['y'] = int(o.get('y', 0))
            item['scale'] = round(float(o.get('scale') or 1), 3)
            # Without a mode (mmsg), the size the editor knows the display by.
            for key in ('logicalWidth', 'logicalHeight', 'physicalWidth', 'physicalHeight'):
                if o.get(key):
                    item[key] = min(max(int(o[key]), 1), 65536)
        except (KeyError, TypeError, ValueError):
            raise Failure('The display settings for {} are incomplete.'.format(name)) from None
        if (item['width'] or item['height']) and not (320 <= item['width'] <= 16384 and 200 <= item['height'] <= 16384):
            raise Failure('{} can’t use that resolution.'.format(name))
        if not 0.5 <= item['scale'] <= 4:
            raise Failure('Scale must be between 50% and 400%.')
        if not 0 <= item['refresh'] <= 1000:
            raise Failure('That refresh rate isn’t valid.')
        transform = str(o.get('transform') or 'normal')
        if transform not in TRANSFORMS:
            raise Failure('That rotation isn’t valid.')
        item['transform'] = transform
        item['adaptiveSync'] = bool(o.get('adaptiveSync', False))
        clean.append(item)
        if not all(abs(item[key]) <= 1 << 20 for key in ('x', 'y')):
            raise Failure('{} is too far away.'.format(name))
    enabled = [o for o in clean if o['enabled']]
    if not enabled:
        raise Failure('At least one display has to stay on.')
    # XWayland misreads clicks with negative positions (Mango docs): start at 0,0.
    return normalize_layout(clean) if tidy else clean


def wlr_randr_args(layout):
    argv = ['wlr-randr']
    for o in layout:
        argv += ['--output', o['name']]
        if not o['enabled']:
            argv.append('--off')
            continue
        argv.append('--on')
        if o.get('width') and o.get('height'):
            mode = '{}x{}'.format(o['width'], o['height'])
            if o.get('refresh'):
                mode += '@{:.3f}Hz'.format(o['refresh'])
            argv += ['--mode', mode]
        argv += ['--pos', '{},{}'.format(o['x'], o['y']),
                 '--scale', format_number(o['scale']), '--transform', o['transform'],
                 '--adaptive-sync', 'enabled' if o.get('adaptiveSync') else 'disabled']
    return argv


def snapshot(outputs):
    return [dict(name=o['name'], enabled=o['enabled'], width=o['width'], height=o['height'],
                 refresh=o['refresh'], x=o['x'], y=o['y'], scale=o['scale'], transform=o['transform'],
                 adaptiveSync=o.get('adaptiveSync', False))
            for o in outputs if o.get('width')]


def cmd_display_try(paths, args):
    layout = check_layout(_layout_arg(args[0] if args else '[]'))
    outputs, backend = list_outputs()
    before = snapshot(outputs)
    known = {o['name'] for o in outputs}
    for o in layout:
        if o['name'] not in known:
            raise Failure('{} isn’t connected any more.'.format(o['name']))
    if backend != 'wlr-randr' and any(not o['enabled'] for o in layout):
        # Without wlr-randr, "off" could only be a saved disable rule, which would also switch
        # the screen off when it is the only one (see set_monitor_rules).
        raise Failure('Turning a display off needs wlr-randr.')
    token = '%x' % time.time_ns()
    if backend == 'wlr-randr':
        pending = dict(token=token, backend='wlr-randr', before=before, layout=layout)
        atomic_write(paths.display_pending, json.dumps(pending), mode=0o600)
        code, _out, err = run(wlr_randr_args(layout), timeout=15)
        if code != 0:
            run(wlr_randr_args(before), timeout=15)
            paths.display_pending.unlink(missing_ok=True)
            raise Failure('The display didn’t accept that ({}). Nothing changed.'.format(strip_ansi(err).strip()[:120] or 'wlr-randr failed'))
    else:
        # No wlr-randr: write the rules and reload Mango; reverting restores the old file.
        model = load_settings(paths)
        old = read_text(paths.settings_conf)
        set_monitor_rules(model, layout)
        pending = dict(token=token, backend='config', old=old, layout=layout)
        atomic_write(paths.display_pending, json.dumps(pending), mode=0o600)
        save_settings(paths, model)
    # A watchdog puts the old layout back if nobody confirms (the new mode may show nothing).
    try:
        if paths.env.get('ARCTIC_SETTINGS_NO_WATCHDOG') == '1':
            raise OSError('watchdog disabled (tests)')
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), 'display-revert', '--if-pending', token,
                          '--after', str(REVERT_AFTER)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except OSError:
        pass
    return dict(ok=True, token=token, revertAfter=REVERT_AFTER, backend=backend or 'config', layout=layout)


def set_monitor_rules(model, layout):
    """Save the layout as monitor rules (Mango 0.17.3 reads them in src/config/parse_config.c,
    parse_option: name is a regex, x/y are logical px, rr is the wl_output transform, and a mode
    is used only with width, height and refresh; src/manage/monitor.c applies them). The main
    display's rule comes first, then the others top to bottom, left to right, then the rules of
    displays that aren't connected now (or are off): as they were, but without x/y where they
    would overlap this layout.

    A display switched off is never saved as `disable:1`: Mango applies that rule whenever the
    output appears, even when it is the only screen (a laptop started without its dock would
    come up dark). Off lasts for this session only; the display keeps its earlier rule, if any,
    without a disable key. Returns the displays that are off for this session only."""
    rules = {r['name']: r for r in model.monitors}
    session_only = []
    main = main_output(layout)
    placed = []
    for o in sorted(layout, key=lambda o: (o['name'] != main, o['y'], o['x'])):
        if not o['enabled']:
            session_only.append(o['name'])
            if o['name'] in rules:
                rules[o['name']] = {k: v for k, v in rules[o['name']].items() if k != 'disable'}
            continue
        rule = dict(name=o['name'], x=o['x'], y=o['y'], scale=float(o['scale']),
                    rr=TRANSFORMS.index(o['transform']), vrr=1 if o.get('adaptiveSync') else 0)
        if o.get('width') and o.get('height'):
            rule.update(width=o['width'], height=o['height'])
            if o.get('refresh'):
                rule['refresh'] = float(o['refresh'])
        rules.pop(o['name'], None)
        placed.append(rule)
    # A display that isn't connected now (the monitor at home, while at work) or is off keeps
    # its rule; where its saved place would overlap the layout just kept, it loses x/y, and Mango
    # puts it right of the others when it comes back, instead of on top of one.
    boxes = [_box(dict(rule, transform=TRANSFORMS[rule['rr']])) for rule in placed]
    for name, rule in list(rules.items()):
        if 'x' not in rule or 'y' not in rule or not rule.get('width'):
            continue
        box = _box(dict(rule, transform=TRANSFORMS[min(max(int(rule.get('rr', 0)), 0), 7)]))
        if any(overlaps(box, b) for b in boxes):
            rules[name] = {k: v for k, v in rule.items() if k not in ('x', 'y')}
    model.monitors = placed + list(rules.values())
    session_only.sort(key=[o['name'] for o in layout].index)
    return session_only


def cmd_display_keep(paths, _args):
    text = read_text(paths.display_pending)
    if not text:
        raise Failure('There’s no display change waiting to be kept.')
    pending = json.loads(text)
    paths.display_pending.unlink(missing_ok=True)
    if pending.get('backend') == 'wlr-randr':
        model = load_settings(paths)
        session_only = set_monitor_rules(model, pending['layout'])
        # Mango already shows this layout; a reload would only redo it.
        result = save_settings(paths, model, reload=False)
        result['sessionOnly'] = session_only
    else:
        result = dict(ok=True, sessionOnly=[])
    result.update(cmd_displays(paths, []))
    return result


def cmd_display_revert(paths, args):
    token = ''
    delay = 0
    while args:
        if args[0] == '--if-pending' and len(args) > 1:
            token, args = args[1], args[2:]
        elif args[0] == '--after' and len(args) > 1:
            delay, args = int(args[1]), args[2:]
        else:
            args = args[1:]
    if delay:
        time.sleep(delay)
    with settings_lock(paths):
        return _display_revert(paths, token)


def _display_revert(paths, token):
    text = read_text(paths.display_pending)
    if not text:
        if token:
            return dict(ok=True, reverted=False)
        raise Failure('There’s no display change to undo.')
    pending = json.loads(text)
    if token and pending.get('token') != token:
        return dict(ok=True, reverted=False)
    paths.display_pending.unlink(missing_ok=True)
    if pending.get('backend') == 'wlr-randr':
        run(wlr_randr_args(pending['before']), timeout=15)
    else:
        old = pending.get('old')
        if old is None:
            paths.settings_conf.unlink(missing_ok=True)
        else:
            atomic_write(paths.settings_conf, old)
        reload_mango()
    result = dict(ok=True, reverted=True)
    if not token:
        result.update(cmd_displays(paths, []))
    return result


def cmd_display_forget(paths, args):
    """Drop saved monitor rules (all of them, or one display's): Arctic's defaults apply again
    the next time Mango reads its config."""
    model = load_settings(paths)
    before = len(model.monitors)
    model.monitors = [r for r in model.monitors if args and r['name'] not in args]
    if len(model.monitors) == before:
        raise Failure('There’s no saved display layout to forget.')
    result = save_settings(paths, model)
    result.update(cmd_displays(paths, []))
    return result


# ---- input devices, power profiles -------------------------------------------------------------

def cmd_devices(paths, _args):
    """Which kinds of pointer devices are connected (mmsg get all-devices), so Settings can hide
    the touchpad group on a desktop. Unknown (no Mango IPC) shows everything."""
    if not which('mmsg'):
        return dict(ok=True, known=False, trackpad=True, mouse=True, devices=[])
    code, out, _err = run(['mmsg', 'get', 'all-devices'], timeout=5)
    data = _loads(out) if code == 0 else None
    items = data.get('devices', []) if isinstance(data, dict) else data if isinstance(data, list) else None
    if not isinstance(items, list):
        return dict(ok=True, known=False, trackpad=True, mouse=True, devices=[])
    devices = []
    for item in items:
        if not isinstance(item, dict):
            continue
        kinds = item.get('types') or item.get('type') or []
        kinds = [kinds] if isinstance(kinds, str) else [str(k) for k in kinds]
        devices.append(dict(name=str(item.get('name', '')), types=kinds))
    kinds = {k for d in devices for k in d['types']}
    return dict(ok=True, known=True, trackpad=bool(kinds & {'trackpad', 'touchpad'}),
                mouse='pointer' in kinds or not kinds & {'trackpad', 'touchpad'}, devices=devices)


PROFILES = ['power-saver', 'balanced', 'performance']
# Arctic ships tuned-ppd, which serves the power-profiles D-Bus API but no powerprofilesctl;
# gdbus (glib2) talks to it directly. Both bus names are tried (new, then the older one).
PPD_BUSES = [('org.freedesktop.UPower.PowerProfiles', '/org/freedesktop/UPower/PowerProfiles'),
             ('net.hadess.PowerProfiles', '/net/hadess/PowerProfiles')]


def _ppd(method, *args):
    for name, path in PPD_BUSES:
        code, out, err = run(['gdbus', 'call', '--system', '--dest', name, '--object-path', path,
                              '--method', 'org.freedesktop.DBus.Properties.' + method, name] + list(args), timeout=10)
        if code == 0:
            return out, ''
        last = err
    return None, last


def cmd_power_profile(paths, args):
    """The power mode: power-saver, balanced or performance (tuned-ppd / power-profiles-daemon)."""
    if args and args[0] not in PROFILES:
        raise Failure('There’s no power mode called “{}”.'.format(args[0]))
    if which('gdbus'):
        if args:
            out, err = _ppd('Set', 'ActiveProfile', "<'{}'>".format(args[0]))
            if out is None:
                raise Failure('The power mode couldn’t be changed ({}).'.format(strip_ansi(err).strip()[:100] or 'no power-profiles service'))
        out, _err = _ppd('Get', 'ActiveProfile')
        if out is not None:
            match = re.search(r"'([a-z-]+)'", out)
            listing, _e = _ppd('Get', 'Profiles')
            offered = [p for p in PROFILES if listing and "'{}'".format(p) in listing] or PROFILES
            return dict(ok=True, available=bool(match), current=match.group(1) if match else '', profiles=offered)
    if which('powerprofilesctl'):
        if args:
            code, _out, err = run(['powerprofilesctl', 'set', args[0]], timeout=10)
            if code != 0:
                raise Failure('The power mode couldn’t be changed.')
        code, out, _err = run(['powerprofilesctl', 'get'], timeout=5)
        if code == 0:
            return dict(ok=True, available=True, current=out.strip(), profiles=PROFILES)
    return dict(ok=True, available=False)


# ---- desktop entries and default apps -------------------------------------------------------------

def desktop_dirs(paths):
    env = paths.env
    dirs = [paths.data / 'applications']
    for d in (env.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':'):
        if d:
            dirs.append(Path(d) / 'applications')
    dirs += [paths.data / 'flatpak/exports/share/applications', Path('/var/lib/flatpak/exports/share/applications')]
    return dirs


def read_desktop(path):
    entry = {}
    section = ''
    text = read_text(path) or ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
            continue
        if section != '[Desktop Entry]' or '=' not in line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        entry.setdefault(key.strip(), value.strip())
    return entry


def desktop_entries(paths):
    """Installed applications by desktop id (XDG precedence: the first one found wins)."""
    entries = {}
    for folder in desktop_dirs(paths):
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*.desktop')):
            ident = str(path.relative_to(folder))[:-8].replace('/', '-')
            if ident in entries:
                continue
            raw = read_desktop(path)
            if raw.get('Type', 'Application') != 'Application' or raw.get('Hidden', '').lower() == 'true':
                entries[ident] = None
                continue
            if 'Exec' not in raw or 'Name' not in raw:
                entries[ident] = None
                continue
            entries[ident] = dict(
                id=ident, name=raw['Name'], exec=raw['Exec'], icon=raw.get('Icon', ''),
                comment=raw.get('GenericName') or raw.get('Comment', ''),
                categories=[c for c in raw.get('Categories', '').split(';') if c],
                mimes=[m for m in raw.get('MimeType', '').split(';') if m],
                terminal=raw.get('Terminal', '').lower() == 'true',
                nodisplay=raw.get('NoDisplay', '').lower() == 'true', path=str(path))
    return {k: v for k, v in entries.items() if v}


VIDEO = ['video/mp4', 'video/x-matroska', 'video/webm', 'video/mpeg', 'video/quicktime', 'video/x-msvideo', 'video/ogg']
AUDIO = ['audio/mpeg', 'audio/flac', 'audio/ogg', 'audio/x-vorbis+ogg', 'audio/x-wav', 'audio/mp4', 'audio/opus']
IMAGES = ['image/png', 'image/jpeg', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff', 'image/svg+xml']
ROLES = [
    dict(id='browser', label='Web browser', open='browser', icon='globe', categories=['WebBrowser'],
         mimes=['x-scheme-handler/http', 'x-scheme-handler/https', 'text/html', 'application/xhtml+xml'],
         keys='Super + B'),
    dict(id='terminal', label='Terminal', open='terminal', icon='terminal', categories=['TerminalEmulator'],
         mimes=[], keys='Super + Enter'),
    dict(id='files', label='Files', open='files', icon='folder', categories=['FileManager'],
         mimes=['inode/directory'], keys='Super + F'),
    dict(id='editor', label='Text editor', open='editor', icon='code', categories=['TextEditor'],
         mimes=['text/plain'], keys='Super + E'),
    dict(id='video', label='Videos', open='', icon='film', categories=[], mimes=VIDEO, prefix='video/'),
    dict(id='music', label='Music', open='', icon='music', categories=[], mimes=AUDIO, prefix='audio/'),
    dict(id='images', label='Pictures', open='', icon='image', categories=[], mimes=IMAGES, prefix='image/'),
    dict(id='pdf', label='PDF documents', open='', icon='document', categories=[], mimes=['application/pdf']),
]


def exec_program(entry):
    try:
        words = shlex.split(entry.get('exec', ''))
    except ValueError:
        words = entry.get('exec', '').split()
    while words and (words[0] == 'env' or '=' in words[0]):
        words = words[1:]
    if words and os.path.basename(words[0]) == 'flatpak':
        return words[-1] if words else ''
    return os.path.basename(words[0]) if words else ''


def role_candidates(role, entries):
    out = []
    for entry in entries.values():
        if entry['nodisplay'] and role['id'] != 'terminal':
            continue
        if role['id'] == 'terminal':
            if exec_program(entry) in TERMINALS:
                out.append(entry)
            continue
        if set(entry['categories']) & set(role['categories']) or set(entry['mimes']) & set(role['mimes']) \
                or (role.get('prefix') and any(m.startswith(role['prefix']) for m in entry['mimes'])):
            out.append(entry)
    return sorted(out, key=lambda e: e['name'].lower())


def read_role_file(path):
    roles = {}
    for line in (read_text(path) or '').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        roles[key.strip()] = value.strip()
    return roles


def role_command_entry(command, entries):
    """Which desktop entry a role=command line opens ('' when it doesn't match one)."""
    words = command.split()
    if not words:
        return ''
    if words[0] == 'gtk-launch' and len(words) > 1:
        return words[1] if words[1] in entries else ''
    program = os.path.basename(words[0])
    terminal = False
    if program in TERMINALS and '-e' in words and words.index('-e') + 1 < len(words):
        program, terminal = os.path.basename(words[words.index('-e') + 1]), True
    elif words[:3] == ['arctic-open', 'terminal', '-e'] and len(words) > 3:
        program, terminal = os.path.basename(words[3]), True
    for entry in sorted(entries.values(), key=lambda e: e['id']):
        if exec_program(entry) == program and (entry['terminal'] == terminal or not terminal):
            return entry['id']
    return ''


def read_mimeapps(path):
    """{section: {key: value}} of a mimeapps.list, keeping the order of the sections."""
    data = {}
    section = None
    for line in (read_text(path) or '').splitlines():
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            section = stripped[1:-1]
            data.setdefault(section, {})
        elif section and '=' in stripped and not stripped.startswith('#'):
            key, value = stripped.split('=', 1)
            data[section][key.strip()] = value.strip()
    return data


def update_mimeapps(text, section, values):
    """text with the keys in values set in [section]; every other line (comments, other
    sections, other keys) is copied through unchanged."""
    lines = (text or '').splitlines()
    todo = dict(values)
    out = []
    current = None
    end = None            # index in out just after the last line of the target section

    def flush():
        if todo:
            insert = [k + '=' + v for k, v in todo.items()]
            out[end:end] = insert
            todo.clear()

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('[') and stripped.endswith(']'):
            if current == section:
                flush()
            current = stripped[1:-1]
            out.append(line)
            if current == section:
                end = len(out)
            continue
        if current == section and '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in values:
                if key in todo:
                    out.append(key + '=' + todo.pop(key))
                    end = len(out)
                continue          # a duplicate of a key we set
        out.append(line)
        if current == section and stripped:
            end = len(out)
    if current == section:
        flush()
    elif todo:
        if out and out[-1].strip():
            out.append('')
        out.append('[{}]'.format(section))
        out.extend(k + '=' + v for k, v in todo.items())
    return '\n'.join(out).rstrip('\n') + '\n'


def mime_default(paths, mime):
    """The desktop id opening a MIME type, from the user's mimeapps.list then the system's."""
    for path in [paths.mimeapps, Path('/etc/xdg/mimeapps.list'),
                 paths.data / 'applications/mimeapps.list', Path('/usr/local/share/applications/mimeapps.list'),
                 Path('/usr/share/applications/mimeapps.list')]:
        value = read_mimeapps(path).get('Default Applications', {}).get(mime, '')
        first = value.split(';')[0].strip()
        if first:
            return first[:-8] if first.endswith('.desktop') else first
    return ''


def cmd_apps(paths, _args):
    entries = desktop_entries(paths)
    system = read_role_file(paths.default_apps_system)
    user = read_role_file(paths.default_apps)
    roles = []
    for role in ROLES:
        candidates = role_candidates(role, entries)
        current = ''
        command = ''
        overridden = False
        if role['open']:
            command = user.get(role['open']) or system.get(role['open'], '')
            overridden = role['open'] in user
            current = role_command_entry(command, entries)
        if not current and role['mimes']:
            current = mime_default(paths, role['mimes'][0])
        if not candidates and not role['open']:
            continue
        roles.append(dict(id=role['id'], label=role['label'], icon=role['icon'], keys=role.get('keys', ''),
                          current=current, command=command, overridden=overridden,
                          candidates=[dict(id=e['id'], name=e['name'], icon=e['icon'], comment=e['comment'])
                                      for e in candidates]))
    return dict(ok=True, roles=roles)


def cmd_app_set(paths, args):
    if len(args) != 2:
        raise Failure('usage: app-set ROLE DESKTOP-ID')
    role = next((r for r in ROLES if r['id'] == args[0]), None)
    if not role:
        raise Failure('There’s no default app called “{}”.'.format(args[0]))
    entries = desktop_entries(paths)
    entry = entries.get(args[1])
    if not entry or entry['id'] not in {e['id'] for e in role_candidates(role, entries)}:
        raise Failure('That app can’t be the {}.'.format(role['label'].lower()))
    if role['open']:
        if role['id'] == 'terminal':
            command = exec_program(entry)
        elif entry['terminal']:
            command = 'arctic-open terminal -e ' + exec_command(entry)
        else:
            command = 'gtk-launch ' + entry['id']
        text = read_text(paths.default_apps)
        lines = text.splitlines() if text else [
            '# Your default apps (Arctic Settings). arctic-open reads /etc/arctic/default-apps, then',
            '# this file: one role=command line per role.']
        prefix = role['open'] + '='
        lines = [l for l in lines if not l.strip().startswith(prefix)]
        lines.append(prefix + command)
        if text is not None:
            backup(paths, paths.default_apps)
        atomic_write(paths.default_apps, '\n'.join(lines) + '\n')
    if role['mimes'] and not entry['terminal']:
        text = read_text(paths.mimeapps)
        if text is not None:
            backup(paths, paths.mimeapps)
        handled = set(entry['mimes']) | set(role['mimes'] if role['id'] in ('browser', 'files', 'editor') else [])
        defaults = {mime: entry['id'] + '.desktop' for mime in role['mimes'] if mime in handled}
        atomic_write(paths.mimeapps, update_mimeapps(text, 'Default Applications', defaults))
    result = cmd_apps(paths, [])
    result['ok'] = True
    return result


# ---- idle ---------------------------------------------------------------------------------------

def read_idle(paths):
    values = dict(lock=300, suspend=900)
    for line in (read_text(paths.idle_conf) or '').splitlines():
        pair = line.split('=', 1)
        if len(pair) == 2 and pair[1].strip().isdigit():
            key = {'lock_after': 'lock', 'suspend_after': 'suspend'}.get(pair[0].strip())
            if key:
                values[key] = int(pair[1].strip())
    return values


def is_live(paths):
    if paths.env.get('ARCTIC_FORCE_LIVE') == '1':
        return True
    return bool(re.search(r'(^|\s)rd\.live\.image(\s|$)', read_text('/proc/cmdline') or ''))


def cmd_idle(paths, _args):
    values = read_idle(paths)
    code, _out, _err = run(['pgrep', '-u', str(os.getuid()), '-x', 'swayidle'], timeout=3)
    values.update(ok=True, running=code == 0, live=is_live(paths), swayidle=bool(which('swayidle')))
    return values


def cmd_idle_set(paths, args):
    try:
        lock, suspend = int(args[0]), int(args[1])
    except (IndexError, ValueError):
        raise Failure('usage: idle-set LOCK-SECONDS SUSPEND-SECONDS') from None
    for value in (lock, suspend):
        if value != 0 and not 60 <= value <= 4 * 3600:
            raise Failure('Pick between one minute and four hours, or never.')
    if lock and suspend and suspend < lock:
        raise Failure('Suspend can’t come before the screen locks.')
    text = ('# Written by Arctic Settings. `arctic-session idle` (swayidle) reads it; 0 means never.\n'
            'lock_after={}\nsuspend_after={}\n').format(lock, suspend)
    # Stream 5: keep the other keys (battery times, dimming, screens off: arctic_system.py).
    text += ''.join(line + '\n' for line in (read_text(paths.idle_conf) or '').splitlines()
                    if re.match(r'^\w+=\d+$', line) and line.split('=')[0] not in ('lock_after', 'suspend_after'))
    if paths.idle_conf.exists():
        backup(paths, paths.idle_conf)
    atomic_write(paths.idle_conf, text)
    restarted = False
    if which('arctic-session') and not is_live(paths):
        code, _o, _e = run(['arctic-session', 'idle', '--restart'], timeout=10)
        restarted = code == 0
    result = cmd_idle(paths, [])
    result['restarted'] = restarted
    return result


# ---- keyboard data ------------------------------------------------------------------------------

# Layout-switch keys offered in Settings. Not Win+Space: Super + Space opens the launcher.
SWITCH_KEYS = ['grp:alt_shift_toggle', 'grp:ctrl_shift_toggle', 'grp:caps_toggle', 'grp:alt_space_toggle',
               'grp:shifts_toggle', 'grp:toggle', 'grp:lalt_lshift_toggle', 'grp:alt_caps_toggle']
CAPS_OPTIONS = ['caps:escape', 'ctrl:nocaps', 'caps:backspace', 'caps:super', 'caps:none', 'caps:swapescape']
# The Compose key: press it, then two keys (' then e types é).
COMPOSE_OPTIONS = ['compose:ralt', 'compose:menu', 'compose:rctrl', 'compose:caps', 'compose:sclk']
COMPOSE_LABELS = {'compose:ralt': 'Right Alt', 'compose:menu': 'Menu', 'compose:rctrl': 'Right Ctrl',
                  'compose:caps': 'Caps Lock', 'compose:sclk': 'Scroll Lock'}
# The keys a layout-switch option takes over: (modifiers the chord holds, the key or None).
# Any shortcut holding them switches the layout too (Alt + Shift + Tab under Alt + Shift).
SWITCH_CHORDS = {
    'grp:alt_shift_toggle': ({'ALT', 'SHIFT'}, None), 'grp:lalt_lshift_toggle': ({'ALT', 'SHIFT'}, None),
    'grp:ctrl_shift_toggle': ({'CTRL', 'SHIFT'}, None), 'grp:alt_space_toggle': ({'ALT'}, 'space'),
    'grp:caps_toggle': (set(), 'caps_lock'), 'grp:alt_caps_toggle': ({'ALT'}, 'caps_lock'),
}


def switch_clash(option, mods, key):
    chord = SWITCH_CHORDS.get(option)
    if not chord:
        return False
    need, chord_key = chord
    return need <= set(mods) and (chord_key is None or key.lower() == chord_key)


def chain_keyboard(paths):
    """(layouts, options) as Mango reads them: the last xkb_rules_* in the chain."""
    values = {}
    for key, value, _origin in read_chain(paths):
        if key in ('xkb_rules_layout', 'xkb_rules_options'):
            values[key] = value
    layouts = [l for l in values.get('xkb_rules_layout', 'us').split(',') if l.strip()]
    options = [o for o in values.get('xkb_rules_options', '').split(',') if o.strip()]
    return layouts, options


def parse_evdev_lst(text):
    layouts, variants, options = [], {}, {}
    section = ''
    for line in (text or '').splitlines():
        if line.startswith('! '):
            section = line[2:].strip()
            continue
        match = re.match(r'^\s+(\S+)\s+(.*)$', line)
        if not match:
            continue
        name, desc = match.group(1), match.group(2).strip()
        if section == 'layout':
            layouts.append(dict(id=name, label=desc))
        elif section == 'variant':
            parent, _, label = desc.partition(':')
            variants.setdefault(parent.strip(), []).append(dict(id=name, label=label.strip()))
        elif section == 'option':
            options[name] = desc
    return layouts, variants, options


def cmd_keyboard_data(paths, _args):
    text = ''
    for candidate in ('/usr/share/X11/xkb/rules/evdev.lst', '/usr/share/xkeyboard-config-2/rules/evdev.lst'):
        text = read_text(candidate)
        if text:
            break
    layouts, variants, options = parse_evdev_lst(text or '')
    if not layouts:
        layouts = [dict(id='us', label='English (US)')]
    switch = [dict(id=o, label=options.get(o, o)) for o in SWITCH_KEYS if o in options or not options]
    caps = [dict(id=o, label=options.get(o, {'caps:none': 'Caps Lock is disabled'}.get(o, o))) for o in CAPS_OPTIONS]
    compose = [dict(id=o, label=COMPOSE_LABELS[o]) for o in COMPOSE_OPTIONS if o in options or not options]
    # The shortcuts each switch option would also fire (Settings says so under the choice).
    clashes = {o: [] for o in SWITCH_CHORDS}
    for bind in chain_binds(paths):
        if bind['keymode'] not in ('default', 'common') or 'shadowedBy' in bind:
            continue
        for option in clashes:
            if switch_clash(option, bind['mods'], bind['key']):
                clashes[option].append('{} ({})'.format(bind['label'], bind['what']))
    return dict(ok=True, layouts=sorted(layouts, key=lambda l: l['label'].lower()), variants=variants,
                switchKeys=switch, capsOptions=caps, composeKeys=compose,
                switchClashes={o: v for o, v in clashes.items() if v})


def cmd_cursor_themes(paths, _args):
    themes = set()
    for folder in (paths.data / 'icons', paths.home / '.icons', Path('/usr/share/icons'), Path('/usr/local/share/icons')):
        if folder.is_dir():
            for sub in folder.iterdir():
                if (sub / 'cursors').is_dir() and RE_CURSOR.match(sub.name):
                    themes.add(sub.name)
    return dict(ok=True, themes=sorted(themes, key=str.lower))


# ---- arctic-theme, arctic-motion, gsettings, wallpapers -------------------------------------------

def _loads(text):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _theme_items(data):
    items = data.get('themes', data.get('items', [])) if isinstance(data, dict) else data
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, str):
            out.append(dict(id=item, name=item.replace('-', ' ').capitalize()))
        elif isinstance(item, dict) and (item.get('id') or item.get('name')):
            ident = str(item.get('id') or item.get('name'))
            entry = dict(id=ident, name=str(item.get('name') or ident), dark=item.get('dark'),
                         kind=str(item.get('kind') or item.get('type') or ''))
            # The theme gallery (arctic-themes-extra): its label, mode, pair and colours.
            if item.get('gallery') is True:
                swatches = item.get('swatches') if isinstance(item.get('swatches'), dict) else {}
                entry.update(gallery=True, label=str(item.get('label') or ident), mode=str(item.get('mode') or ''),
                             pair=str(item.get('pair') or ''),
                             installedFrom=str(item.get('installed_from') or ''),
                             swatches={k: v for k, v in swatches.items()
                                       if isinstance(k, str) and isinstance(v, str) and re.fullmatch(r'#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?', v)})
            out.append(entry)
    return out


def cmd_theme(paths, _args):
    if not which('arctic-theme'):
        return dict(ok=True, available=False, reason='The theme switcher (arctic-theme) isn’t installed.')
    code, out, _err = run(['arctic-theme', 'list', '--json'], timeout=10)
    listing = _loads(out) if code == 0 else None
    settings = _loads(read_text(paths.arctic / 'settings.json') or '') or {}
    if listing is None:
        code, out, _err = run(['arctic-theme'], timeout=10)
        current = out.strip().splitlines()[-1] if code == 0 and out.strip() else 'polar-night'
        return dict(ok=True, available=True, modern=False, current=current, mode='', auto=False,
                    themes=[dict(id='winter', name='Winter'), dict(id='polar-night', name='Polar night')],
                    reason='This version of arctic-theme switches between Winter and Polar night only.')
    themes = _theme_items(listing)
    code, out, _err = run(['arctic-theme', 'current', '--json'], timeout=10)
    cur = _loads(out) if code == 0 else None
    if isinstance(cur, str):
        cur = dict(theme=cur)
    cur = cur if isinstance(cur, dict) else {}
    current = str(cur.get('theme') or cur.get('id') or cur.get('name') or cur.get('current') or '')
    if not current:
        current = (read_text(paths.arctic / 'theme') or 'polar-night').strip()
    auto = cur.get('auto_colors', cur.get('auto', cur.get('autoColors', settings.get('auto_colors', False))))
    ids = {t['id'] for t in themes}
    for ident, name in (('winter', 'Winter'), ('polar-night', 'Polar night'), ('wallpaper', 'From wallpaper')):
        if ident not in ids:
            themes.append(dict(id=ident, name=name))
    return dict(ok=True, available=True, modern=True, themes=themes, current=current,
                mode=str(cur.get('mode') or settings.get('mode') or 'auto'), auto=bool(auto),
                source=str(cur.get('source') or cur.get('base') or ''))


def cmd_theme_set(paths, args):
    name = args[0] if args else ''
    # arctic-theme's names: an installed theme keeps the dots of its repository's name.
    if not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', name):
        raise Failure('That isn’t a theme name.')
    state = cmd_theme(paths, [])
    if not state['available']:
        raise Failure(state['reason'])
    if state['modern']:
        argv = ['arctic-theme', 'set', name]
    elif name in ('winter', 'polar-night'):
        argv = ['arctic-theme', name]
    else:
        raise Failure(state['reason'])
    code, out, err = run(argv, timeout=60)
    if code != 0:
        raise Failure((strip_ansi(err or out).strip().splitlines() or ['The theme couldn’t be changed.'])[-1])
    return cmd_theme(paths, [])


def _theme_verb(paths, verb, value, allowed):
    if value not in allowed:
        raise Failure('usage: theme-{} {}'.format(verb, '|'.join(allowed)))
    state = cmd_theme(paths, [])
    if not state['available'] or not state['modern']:
        raise Failure(state.get('reason') or 'arctic-theme can’t do that yet.')
    code, out, err = run(['arctic-theme', verb, value], timeout=60)
    if code != 0:
        raise Failure((strip_ansi(err or out).strip().splitlines() or ['That didn’t work.'])[-1])
    return cmd_theme(paths, [])


def cmd_theme_auto(paths, args):
    return _theme_verb(paths, 'auto', args[0] if args else '', ('on', 'off'))


def cmd_theme_mode(paths, args):
    return _theme_verb(paths, 'mode', args[0] if args else '', ('auto', 'dark', 'light'))


def cmd_motion(paths, _args):
    if not which('arctic-motion'):
        return dict(ok=True, available=False, reduced=(paths.arctic / 'motion.conf').exists())
    code, out, _err = run(['arctic-motion'], timeout=5)
    return dict(ok=True, available=True, reduced=out.strip() == 'reduced' if code == 0
                else (paths.arctic / 'motion.conf').exists())


def cmd_motion_set(paths, args):
    value = args[0] if args else ''
    if value not in ('on', 'off'):
        raise Failure('usage: motion-set on|off')
    if not which('arctic-motion'):
        raise Failure('arctic-motion isn’t installed.')
    code, _out, err = run(['arctic-motion', value], timeout=15)
    if code != 0:
        raise Failure(err.strip() or 'Reduced motion couldn’t be changed.')
    return cmd_motion(paths, [])


def cmd_text_scale(paths, args):
    if not which('gsettings'):
        return dict(ok=True, available=False)
    schema = ['org.gnome.desktop.interface', 'text-scaling-factor']
    if args:
        try:
            value = float(args[0])
        except ValueError:
            raise Failure('Text size needs a number.') from None
        if not 0.75 <= value <= 2.0:
            raise Failure('Text size must be between 75% and 200%.')
        code, _o, err = run(['gsettings', 'set'] + schema + [format_number(value)], timeout=5)
        if code != 0:
            raise Failure(err.strip() or 'Text size couldn’t be changed.')
        # The terminals follow (arctic-font size): 10.5 pt at 100%, to the nearest half point.
        if which('arctic-font'):
            size = 'reset' if value == 1 else format_number(round(TERMINAL_PT * value * 2) / 2)
            run(['arctic-font', 'size', size, '--json'], timeout=20)
    code, out, _err = run(['gsettings', 'get'] + schema, timeout=5)
    try:
        result = dict(ok=True, available=code == 0, value=float(out.strip()) if code == 0 else 1.0)
    except ValueError:
        return dict(ok=True, available=False, value=1.0)
    if which('arctic-font'):
        code, out, _err = run(['arctic-font', 'current', '--json'], timeout=10)
        data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
        if code == 0 and isinstance(data, dict) and isinstance(data.get('size'), (int, float)):
            result['terminalPt'] = data['size']
    return result


TERMINAL_PT = 10.5      # arctic-font's default terminal size


def apply_cursor_gsettings(options):
    """GTK apps draw their own cursor: tell them the theme and size too (best effort)."""
    if not which('gsettings'):
        return
    if options.get('cursor_theme'):
        run(['gsettings', 'set', 'org.gnome.desktop.interface', 'cursor-theme', options['cursor_theme']], timeout=5)
    if options.get('cursor_size'):
        run(['gsettings', 'set', 'org.gnome.desktop.interface', 'cursor-size', options['cursor_size']], timeout=5)


def shell_script(paths, name):
    for folder in (paths.env.get('ARCTIC_SHELL_DIR'), str(paths.config / 'quickshell/arctic'),
                   str(paths.share / 'shell'), str(HERE.parent.parent / 'shell')):
        if folder and (Path(folder) / 'scripts' / name).is_file():
            return Path(folder) / 'scripts' / name
    return None


def cmd_wallpapers(paths, _args):
    script = shell_script(paths, 'wallpapers.py')
    if not script:
        return dict(ok=True, available=False, items=[], reason='The shell’s wallpaper picker isn’t installed.')
    code, out, _err = run([sys.executable, str(script), 'list'], timeout=120)
    data = _loads(out) or {}
    if code != 0 or 'items' not in data:
        raise Failure(data.get('error') or 'Your wallpapers couldn’t be listed.')
    data.update(ok=True, available=True)
    return data


def cmd_wallpaper_set(paths, args):
    script = shell_script(paths, 'wallpapers.py')
    if not args:
        raise Failure('usage: wallpaper-set KEY')
    if script:
        code, out, _err = run([sys.executable, str(script), 'apply', args[0]], timeout=60)
        data = _loads(out) or {}
        if code != 0 or not data.get('ok'):
            raise Failure(data.get('error') or 'The wallpaper couldn’t be set.')
        return data
    code, _out, err = run(['arctic-wallpaper', args[0]], timeout=60)
    if code != 0:
        raise Failure(err.strip() or 'The wallpaper couldn’t be set.')
    return dict(ok=True, current=args[0])


def _wallpaper_files(paths, argv, what):
    script = shell_script(paths, 'wallpapers.py')
    if not script:
        raise Failure('The shell’s wallpaper picker isn’t installed.')
    code, out, _err = run([sys.executable, str(script)] + argv, timeout=120)
    data = _loads(out) or {}
    if code != 0 or not data.get('ok'):
        raise Failure(data.get('error') or 'The picture couldn’t be {}.'.format(what))
    return data


def cmd_wallpaper_import(paths, args):
    if not args:
        raise Failure('usage: wallpaper-import PATH|URL…')
    return _wallpaper_files(paths, ['import'] + list(args), 'added')


def cmd_wallpaper_delete(paths, args):
    if len(args) != 1:
        raise Failure('usage: wallpaper-delete PATH')
    return _wallpaper_files(paths, ['delete', args[0]], 'deleted')


def cmd_wallpaper_rename(paths, args):
    if len(args) != 2:
        raise Failure('usage: wallpaper-rename PATH NAME')
    return _wallpaper_files(paths, ['rename', args[0], args[1]], 'renamed')


WALLHAVEN_TIMEOUTS = {'search': 90, 'preview': 60, 'download': 300, 'set': 300}


def cmd_wallhaven(paths, args):
    """The Wallhaven browser: every network call happens in wallhaven.py. Its answer comes
    back as is (so the page can show "offline" or "wait N s" in place, not as an error)."""
    script = shell_script(paths, 'wallhaven.py')
    if not script:
        return dict(ok=False, available=False, error='The Wallhaven browser isn’t installed.')
    if not args or args[0] not in ('search', 'preview', 'download', 'set', 'state', 'key', 'prefs'):
        raise Failure('usage: wallhaven search|preview|download|set|state|key|prefs …')
    code, out, err = run([sys.executable, str(script)] + list(args), timeout=WALLHAVEN_TIMEOUTS.get(args[0], 30))
    data = _loads(out)
    if not isinstance(data, dict):
        raise Failure(strip_ansi(err).strip().splitlines()[-1] if err.strip() else 'Wallhaven didn’t answer in time.')
    data.setdefault('ok', code == 0)
    return data


# ---- arctic-update ------------------------------------------------------------------------------

def cmd_updates(paths, _args):
    if not which('arctic-update'):
        return dict(ok=True, available=False,
                    reason='Automatic updates (arctic-update) aren’t on this system yet. You can still update from a terminal with sudo dnf upgrade.')
    code, out, err = run(['arctic-update', 'status', '--json'], timeout=30)
    data = _loads(out)
    if code != 0 or not isinstance(data, dict):
        return dict(ok=True, available=False,
                    reason=(strip_ansi(err).strip().splitlines() or ['The updater didn’t answer.'])[-1])
    packages = data.get('packages', [])
    count = len(packages) if isinstance(packages, list) else int(packages or 0)
    auto = data.get('auto', data.get('auto_mode', data.get('automatic')))
    if isinstance(auto, str):
        auto = auto.lower() in ('on', 'true', 'yes', '1', 'download', 'install')
    return dict(ok=True, available=True, state=str(data.get('state') or 'idle'), count=count,
                packages=packages if isinstance(packages, list) else [],
                downloadMb=data.get('download_mb') or 0, stagedAt=str(data.get('staged_at') or ''),
                channel=str(data.get('channel') or 'stable'), auto=bool(auto), error=str(data.get('error') or ''))


def cmd_update_run(paths, args):
    allowed = {('now',), ('apply',), ('channel', 'stable'), ('channel', 'testing'), ('auto', 'on'), ('auto', 'off')}
    if tuple(args) not in allowed:
        raise Failure('usage: update-run now|apply|channel stable|testing|auto on|off')
    if not which('arctic-update'):
        raise Failure('arctic-update isn’t installed.')
    if args[0] in ('now', 'apply'):
        # These run for a while (download, or restart into the update): start and detach.
        subprocess.Popen(['arctic-update'] + args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        time.sleep(0.5)
    else:
        code, out, err = run(['arctic-update'] + args, timeout=60)
        if code != 0:
            raise Failure((strip_ansi(err or out).strip().splitlines() or ['That didn’t work.'])[-1])
    return cmd_updates(paths, [])


# ---- network ------------------------------------------------------------------------------------

def nmcli_fields(line):
    """Split one `nmcli -t` line at unescaped colons."""
    out, current, escape = [], '', False
    for ch in line:
        if escape:
            current += ch
            escape = False
        elif ch == '\\':
            escape = True
        elif ch == ':':
            out.append(current)
            current = ''
        else:
            current += ch
    out.append(current)
    return out


def cmd_network(paths, _args):
    if not which('nmcli'):
        return dict(ok=True, available=False, reason='NetworkManager (nmcli) isn’t installed.')
    code, out, err = run(['nmcli', '-t', '-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status'], timeout=10)
    if code != 0:
        return dict(ok=True, available=False, reason='NetworkManager isn’t running.')
    devices = []
    for line in out.splitlines():
        f = nmcli_fields(line)
        if len(f) >= 4 and f[1] in ('wifi', 'ethernet', 'wwan', 'gsm', 'bt', 'wireguard', 'vpn'):
            devices.append(dict(device=f[0], type=f[1], state=f[2].split(' ')[0], connection=f[3]))
    code, out, _err = run(['nmcli', 'radio', 'wifi'], timeout=5)
    wifi = out.strip() == 'enabled'
    signal = {}
    code2, out2, _e = run(['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL', 'device', 'wifi', 'list', '--rescan', 'no'], timeout=10)
    if code2 == 0:
        for line in out2.splitlines():
            f = nmcli_fields(line)
            if len(f) >= 3 and f[0] == 'yes':
                signal[f[1]] = int(f[2]) if f[2].isdigit() else 0
    for d in devices:
        if d['type'] == 'wifi' and d['connection'] in signal:
            d['signal'] = signal[d['connection']]
    return dict(ok=True, available=True, wifi=wifi, hasWifi=any(d['type'] == 'wifi' for d in devices),
                devices=devices, editor=bool(which('nm-connection-editor')))


def cmd_wifi(paths, args):
    if args[:1] not in (['on'], ['off']):
        raise Failure('usage: wifi on|off')
    code, _out, err = run(['nmcli', 'radio', 'wifi', args[0]], timeout=15)
    if code != 0:
        raise Failure(err.strip() or 'Wi-Fi couldn’t be switched.')
    return cmd_network(paths, [])


# ---- battery (the shell's battery.py) and shell settings ----------------------------------------

SHELL_KEYS = {'batteryWarnings': ('true', 'false')}


def shell_settings(paths):
    try:
        data = json.loads((paths.config / 'arctic/shell.json').read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def cmd_battery(paths, args):
    """The laptop battery as the battery menu sees it (battery.py status: charge limit), plus
    whether the low-battery warning is on. `battery limit on|off` sets UPower's charge limit."""
    warnings = shell_settings(paths).get('batteryWarnings') is not False
    script = shell_script(paths, 'battery.py')
    if not script:
        return dict(ok=True, present=False, warnings=warnings)
    if args[:1] == ['limit'] and args[1:] in (['on'], ['off']):
        code, out, _err = run([sys.executable, str(script), 'limit', args[1]], timeout=60)
    elif not args:
        code, out, _err = run([sys.executable, str(script), 'status'], timeout=20)
    else:
        raise Failure('usage: battery [limit on|off]')
    try:
        data = json.loads(out)
    except ValueError:
        data = dict(ok=False, error='The battery helper didn’t answer.')
    if args and data.get('ok'):
        return cmd_battery(paths, [])
    if not data.get('ok'):
        if args:
            raise Failure(data.get('error') or 'That didn’t work.')
        return dict(ok=True, present=False, warnings=warnings)
    data['warnings'] = warnings
    return data


def cmd_shell_set(paths, args):
    """shell-set KEY VALUE: one of the shell's own settings in ~/.config/arctic/shell.json
    (read by the shell's Session.qml), keeping the others."""
    if len(args) != 2 or args[0] not in SHELL_KEYS or args[1] not in SHELL_KEYS[args[0]]:
        raise Failure('usage: shell-set batteryWarnings true|false')
    data = shell_settings(paths)
    data[args[0]] = args[1] == 'true'
    atomic_write(paths.config / 'arctic/shell.json', json.dumps(data, indent=2) + '\n')
    return dict(ok=True, **{args[0]: data[args[0]]})


# ---- saved networks and VPNs (the shell's network.py) --------------------------------------------

def network_script(paths, args):
    script = shell_script(paths, 'network.py')
    if not script:
        raise Failure('The shell’s network helper isn’t installed.')
    _code, out, _err = run([sys.executable, str(script)] + args, timeout=90)
    try:
        data = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        raise Failure('The network helper didn’t answer.')
    if not data.get('ok'):
        raise Failure(data.get('error') or 'That didn’t work.')
    return data


def cmd_network_saved(paths, _args):
    """Saved Wi-Fi networks and VPN connections."""
    try:
        data = network_script(paths, ['saved'])
    except Failure:
        return dict(ok=True, available=False, saved=[], vpn=[])
    return dict(ok=True, available=True, saved=data.get('saved', []), vpn=data.get('vpn', []))


def cmd_network_forget(paths, args):
    if not args or not all(re.fullmatch(r'[0-9a-fA-F-]{36}', a) for a in args):
        raise Failure('usage: network-forget UUID…')
    network_script(paths, ['forget'] + [x for a in args for x in ('--uuid', a)])
    return cmd_network_saved(paths, [])


def local_path(arg):
    """A path, or a file:// URL from a file dialog (percent-encoded)."""
    return urllib.parse.unquote(arg[7:]) if arg.startswith('file://') else arg


def cmd_network_ca_set(paths, args):
    """network-ca-set UUID PATH: a company (802.1X) network checks its server with this certificate."""
    if len(args) != 2 or not re.fullmatch(r'[0-9a-fA-F-]{36}', args[0]):
        raise Failure('usage: network-ca-set UUID PATH')
    network_script(paths, ['ca-set', '--uuid', args[0], '--file', local_path(args[1])])
    return cmd_network_saved(paths, [])


def cmd_vpn(paths, args):
    """vpn-up|vpn-down UUID, vpn-import PATH."""
    verb = args[0] if args else ''
    if verb in ('up', 'down') and len(args) == 2 and re.fullmatch(r'[0-9a-fA-F-]{36}', args[1]):
        network_script(paths, ['vpn-' + verb, '--uuid', args[1]])
    elif verb == 'import' and len(args) == 2:
        network_script(paths, ['vpn-import', '--file', local_path(args[1])])
    else:
        raise Failure('usage: vpn up|down UUID | vpn import PATH')
    return cmd_network_saved(paths, [])


def cmd_bluetooth_pair(_paths, _args):
    """Pair a device: the shell's Bluetooth menu on its pairing page (codes come up in Arctic's
    own dialog); without the shell, the Bluetooth manager."""
    code, _out, _err = run(['arctic-shell-ipc', 'bluetooth', 'pair'], timeout=10)
    if code == 0:
        return dict(ok=True, opened='shell')
    if which('blueman-manager'):
        subprocess.Popen(['blueman-manager'], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return dict(ok=True, opened='blueman')
    raise Failure('The Arctic shell isn’t running, and the Bluetooth manager isn’t installed.')
# ---- notifications --------------------------------------------------------------------------------
# The shell's notification server (shell/NotificationService.qml) reads
# ~/.config/arctic/notifications.json (written here) and keeps its own state in
# ~/.local/state/arctic/notifications/ (apps.json: the apps seen, for the rules list).
# Do not disturb goes through arctic-dnd, which talks to the shell or to mako.

NOTIFY_RULE_KEYS = ('toasts', 'history', 'allow_during_dnd', 'silence_urgent')
NOTIFY_RULE_DEFAULTS = dict(toasts=True, history=True, allow_during_dnd=False, silence_urgent=False)
HHMM = re.compile(r'^([01]?\d|2[0-3]):[0-5]\d$')


def notifications_file(paths):
    return paths.arctic / 'notifications.json'


def notifications_state(paths):
    return paths.state / 'arctic' / 'notifications'


def read_notification_config(paths):
    data = _loads(read_text(notifications_file(paths)) or '')
    data = data if isinstance(data, dict) else {}
    schedule = data.get('dnd_schedule') if isinstance(data.get('dnd_schedule'), dict) else {}
    start, end = str(schedule.get('from', '')), str(schedule.get('to', ''))
    rules = data.get('apps') if isinstance(data.get('apps'), dict) else {}
    apps = {}
    for key, rule in rules.items():
        if isinstance(rule, dict):
            apps[str(key)] = {k: rule[k] for k in NOTIFY_RULE_KEYS if isinstance(rule.get(k), bool)}
    return {'history': data.get('history') is not False,
            'dnd_schedule': {'enabled': schedule.get('enabled') is True,
                             'from': start if HHMM.match(start) else '22:00', 'to': end if HHMM.match(end) else '07:00'},
            'apps': apps}


def write_notification_config(paths, config):
    atomic_write(notifications_file(paths), json.dumps(config, indent=1, sort_keys=True) + '\n')
    if which('arctic-shell-ipc'):       # the shell re-reads it (its watch needs the file to exist)
        run(['arctic-shell-ipc', 'notifications', 'reload'], timeout=5)


def cmd_notifications(paths, _args):
    config = read_notification_config(paths)
    seen = _loads(read_text(notifications_state(paths) / 'apps.json') or '')
    seen = seen.get('apps') if isinstance(seen, dict) and isinstance(seen.get('apps'), list) else []
    apps, keys = [], set()
    for app in seen:
        if isinstance(app, dict) and isinstance(app.get('key'), str) and app['key'] and app['key'] not in keys:
            keys.add(app['key'])
            apps.append(dict(key=app['key'], name=str(app.get('app_name') or app['key']),
                             desktopEntry=str(app.get('desktop_entry') or ''), lastSeen=app.get('last_seen') or 0))
    for key in sorted(set(config['apps']) - keys):     # rules for apps not seen lately
        apps.append(dict(key=key, name=key, desktopEntry='', lastSeen=0))
    for app in apps:
        app['rule'] = dict(NOTIFY_RULE_DEFAULTS, **config['apps'].get(app['key'], {}))
    # The shell answers on / off when it owns notifications, "unowned" when mako (or another
    # daemon) has them; arctic-dnd answers either way.
    code, out, _err = run(['arctic-shell-ipc', 'notifications', 'dnd', 'status'], timeout=5) if which('arctic-shell-ipc') else (1, '', '')
    owned = code == 0 and out.strip() in ('on', 'off')
    dnd = out.strip() == 'on' if owned else False
    if not owned and which('arctic-dnd'):
        code, out, _err = run(['arctic-dnd', 'status'], timeout=5)
        status = _loads(out) or {}
        dnd = isinstance(status, dict) and status.get('class') == 'dnd'
    return dict(ok=True, owned=owned, dnd=dnd, history=config['history'], schedule=config['dnd_schedule'], apps=apps)


def cmd_notification_set(paths, args):
    """notification-set history on|off · schedule on|off · schedule-from HH:MM · schedule-to HH:MM"""
    if len(args) != 2:
        raise Failure('usage: notification-set history|schedule on|off, or schedule-from|schedule-to HH:MM')
    key, value = args
    config = read_notification_config(paths)
    if key in ('history', 'schedule') and value in ('on', 'off'):
        if key == 'history':
            config['history'] = value == 'on'
        else:
            config['dnd_schedule']['enabled'] = value == 'on'
    elif key in ('schedule-from', 'schedule-to') and HHMM.match(value):
        config['dnd_schedule'][key.split('-')[1]] = '{:0>5}'.format(value)
    else:
        raise Failure('That isn’t a notification setting Settings knows.')
    write_notification_config(paths, config)
    return cmd_notifications(paths, [])


def cmd_notification_rule_set(paths, args):
    """notification-rule-set APP KEY on|off [KEY on|off…]; KEY: toasts, history,
    allow_during_dnd, silence_urgent. Rules that match the defaults are dropped."""
    if len(args) < 3 or len(args) % 2 == 0:
        raise Failure('usage: notification-rule-set APP KEY on|off…')
    app, pairs = args[0], args[1:]
    if not app or len(app) > 200 or any(ord(ch) < 32 for ch in app):
        raise Failure('That app name can’t be used.')
    config = read_notification_config(paths)
    rule = dict(NOTIFY_RULE_DEFAULTS, **config['apps'].get(app, {}))
    for key, value in zip(pairs[::2], pairs[1::2]):
        if key not in NOTIFY_RULE_KEYS or value not in ('on', 'off'):
            raise Failure('usage: notification-rule-set APP toasts|history|allow_during_dnd|silence_urgent on|off')
        rule[key] = value == 'on'
    changed = {k: v for k, v in rule.items() if v != NOTIFY_RULE_DEFAULTS[k]}
    if changed:
        config['apps'][app] = changed
    else:
        config['apps'].pop(app, None)
    write_notification_config(paths, config)
    return cmd_notifications(paths, [])


def cmd_notification_history_clear(paths, _args):
    """Clear the notification centre: through the shell when it runs, else the saved history."""
    code = run(['arctic-shell-ipc', 'notifications', 'clearHistory'], timeout=5)[0] if which('arctic-shell-ipc') else 1
    if code != 0:
        try:
            (notifications_state(paths) / 'history.json').unlink()
        except FileNotFoundError:
            pass
    return cmd_notifications(paths, [])


def cmd_dnd_set(paths, args):
    """dnd-set on|off|1h|tomorrow — do not disturb now (arctic-dnd)."""
    commands = {'on': ['on'], 'off': ['off'], '1h': ['for', '1h'], 'tomorrow': ['until-tomorrow']}
    if len(args) != 1 or args[0] not in commands:
        raise Failure('usage: dnd-set on|off|1h|tomorrow')
    if not which('arctic-dnd'):
        raise Failure('arctic-dnd isn’t installed.')
    code, out, err = run(['arctic-dnd'] + commands[args[0]], timeout=10)
    if code != 0:
        raise Failure((err or out).strip() or 'Do not disturb couldn’t be changed.')
    return cmd_notifications(paths, [])


# ---- about --------------------------------------------------------------------------------------

def parse_os_release(text):
    data = {}
    for line in (text or '').splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            try:
                data[key] = shlex.split(value)[0] if value.strip() else ''
            except (ValueError, IndexError):
                data[key] = value.strip('"')
    return data


PCI_VENDORS = {'0x8086': 'Intel', '0x1002': 'AMD', '0x10de': 'NVIDIA', '0x1af4': 'Virtio', '0x15ad': 'VMware',
               '0x1234': 'QEMU', '0x80ee': 'VirtualBox', '0x1414': 'Microsoft', '0x5143': 'Qualcomm'}


def gpus():
    names = []
    if which('lspci'):
        code, out, _err = run(['lspci', '-mm'], timeout=5)
        if code == 0:
            for line in out.splitlines():
                try:
                    parts = shlex.split(line)
                except ValueError:
                    continue
                if len(parts) >= 4 and re.search(r'VGA|3D|Display', parts[1]):
                    names.append('{} {}'.format(parts[2], parts[3]).replace(' Corporation', ''))
    if names:
        return names
    for card in sorted(Path('/sys/class/drm').glob('card[0-9]')):
        vendor = (read_text(card / 'device/vendor') or '').strip()
        driver = ''
        for line in (read_text(card / 'device/uevent') or '').splitlines():
            if line.startswith('DRIVER='):
                driver = line[7:]
        if vendor or driver:
            names.append('{}{}'.format(PCI_VENDORS.get(vendor, 'Graphics'), ' ({})'.format(driver) if driver else ''))
    return names


def cmd_about(paths, _args):
    osr = parse_os_release(read_text('/etc/os-release') or read_text('/usr/lib/os-release'))
    platform = osr.get('PLATFORM_ID', '')
    fedora = 'Fedora ' + platform.split(':f')[-1] if platform.startswith('platform:f') else ''
    match = re.search(r'Fedora\s+\d+', osr.get('VERSION', ''))
    if match:
        fedora = match.group(0)
    cpu = ''
    cores = 0
    for line in (read_text('/proc/cpuinfo') or '').splitlines():
        if line.startswith('model name') and not cpu:
            cpu = line.split(':', 1)[1].strip()
        if line.startswith('processor'):
            cores += 1
    mem_kb = 0
    for line in (read_text('/proc/meminfo') or '').splitlines():
        if line.startswith('MemTotal:'):
            mem_kb = int(re.sub(r'\D', '', line) or 0)
    disks = []
    for mount in ('/', '/home'):
        try:
            st = os.statvfs(mount)
        except OSError:
            continue
        total = st.f_blocks * st.f_frsize
        free = st.f_bavail * st.f_frsize
        if disks and disks[-1]['total'] == total:
            continue
        disks.append(dict(mount=mount, total=total, free=free))
    vendor = (read_text('/sys/class/dmi/id/sys_vendor') or '').strip()
    product = (read_text('/sys/class/dmi/id/product_name') or '').strip()
    versions = {}
    for name, argv in (('mango', ['mango', '-v']), ('quickshell', ['quickshell', '--version'])):
        if which(argv[0]):
            code, out, _err = run(argv, timeout=5)
            match = re.search(r'\d+\.\d+(\.\d+)?', out or '')
            versions[name] = match.group(0) if code == 0 and match else ''
    home = osr.get('HOME_URL', 'https://github.com/yuvalkolodkingal/Arctic-Linux')
    return dict(ok=True, name=osr.get('NAME', 'Arctic Linux'), version=osr.get('VERSION_ID', ''),
                pretty=osr.get('PRETTY_NAME', ''), fedora=fedora, kernel=os.uname().release,
                hostname=os.uname().nodename, cpu=cpu, cores=cores, memory=mem_kb * 1024, disks=disks,
                gpus=gpus(), machine=' '.join(x for x in (vendor, product) if x and 'To Be Filled' not in x),
                mango=versions.get('mango', ''), quickshell=versions.get('quickshell', ''),
                home=home, wiki=home.rstrip('/') + '/wiki',
                issues=osr.get('BUG_REPORT_URL', home.rstrip('/') + '/issues'), live=is_live(paths))


# ---- capabilities -------------------------------------------------------------------------------

TOOLS = {'mmsg': 'mmsg', 'mango': 'mango', 'wlrRandr': 'wlr-randr', 'nmcli': 'nmcli', 'nmEditor': 'nm-connection-editor',
         'bluetoothctl': 'bluetoothctl', 'blueman': 'blueman-manager', 'wpctl': 'wpctl', 'pavucontrol': 'pavucontrol',
         'pwvucontrol': 'pwvucontrol', 'wdisplays': 'wdisplays', 'arcticTheme': 'arctic-theme',
         'arcticUpdate': 'arctic-update', 'arcticMotion': 'arctic-motion', 'arcticWallpaper': 'arctic-wallpaper',
         'gsettings': 'gsettings', 'swayidle': 'swayidle', 'gtkLaunch': 'gtk-launch', 'xdgOpen': 'xdg-open',
         'arcticSession': 'arctic-session', 'nmtui': 'nmtui', 'wlCopy': 'wl-copy', 'powerprofilesctl': 'powerprofilesctl',
         'shellIpc': 'arctic-shell-ipc', 'arcticDnd': 'arctic-dnd'}


# ---- web apps (stream 1) -------------------------------------------------------------------------
# The Web apps page runs arctic-webapp with an argv and passes its one line of --json through:
# it already has ok and error (a sentence).

WEBAPP_KEYS = {'name': '--name', 'links': '--links', 'notifications': '--notifications', 'devtools': '--devtools',
               'rendering': '--rendering', 'runtime': '--runtime', 'category': '--category',
               'mail-links': '--mail-links', 'add-domain': '--add-domain', 'remove-domain': '--remove-domain',
               'forget-certificate': '--forget-certificate', 'icon': '--icon'}


def run_webapp(args, timeout=60):
    exe = which('arctic-webapp')
    if not exe:
        raise Failure('Web apps aren’t installed (package arctic-webapps).')
    try:
        proc = subprocess.run([exe] + args + ['--json'], capture_output=True, text=True, timeout=timeout,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        raise Failure('Web apps took too long to answer. Try again.') from None
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    try:
        result = json.loads(lines[-1]) if lines else None
    except ValueError:
        result = None
    if not isinstance(result, dict) or 'ok' not in result:
        raise Failure('Web apps answered with something Settings can’t read.')
    return result


def webapp_id(args, count=1):
    if len(args) != count or not re.fullmatch(r'org\.arcticlinux\.WebApp\.[A-Za-z][A-Za-z0-9]{0,31}_[0-9a-f]{6,8}', args[0]):
        raise Failure('That isn’t a web app.')
    return args[0]


def cmd_webapps(_paths, _args):
    return run_webapp(['list', '--kept', '--sizes'])


def cmd_webapp_set(_paths, args):
    if len(args) != 3:
        raise Failure('Expected a web app, a setting and a value.')
    app, key, value = webapp_id(args[:1]), args[1], args[2]
    if key not in WEBAPP_KEYS:
        raise Failure('Settings can’t change “{}” for a web app.'.format(key))
    if '\n' in value or '\0' in value or len(value) > 2048:
        raise Failure('That value isn’t valid.')
    return run_webapp(['set', app, WEBAPP_KEYS[key] + '=' + value])


def cmd_webapp_reset_permissions(_paths, args):
    return run_webapp(['set', webapp_id(args), '--reset-permissions'])


def cmd_webapp_refresh(_paths, args):
    return run_webapp(['update', webapp_id(args)], timeout=90)


def cmd_webapp_clear(_paths, args):
    return run_webapp(['clear-data', webapp_id(args)])


def cmd_webapp_open(_paths, args):
    return run_webapp(['launch', webapp_id(args)])


def cmd_webapp_remove(_paths, args):
    if len(args) != 2 or args[1] not in ('keep', 'delete'):
        raise Failure('Expected a web app and keep or delete.')
    return run_webapp(['remove', webapp_id(args[:1])] + (['--keep-data'] if args[1] == 'keep' else []))


def cmd_webapp_forget(_paths, args):
    return run_webapp(['forget', webapp_id(args)])


def cmd_webapp_runtimes(_paths, _args):
    return run_webapp(['runtimes'])


def cmd_caps(paths, _args):
    out = {key: bool(which(cmd)) for key, cmd in TOOLS.items()}
    out.update(ok=True, live=is_live(paths))
    return out


def cmd_state(paths, args):
    result = mango_state(paths)
    result['caps'] = cmd_caps(paths, args)
    return result


def cmd_set_cursor(paths, args):
    """set, plus telling GTK apps (gsettings) about the cursor."""
    result = cmd_set(paths, args)
    apply_cursor_gsettings(dict(a.split('=', 1) for a in args if '=' in a))
    return result


# ---- the shell's own options (~/.config/arctic/shell.json) --------------------------------------
# The shell watches the file, so a change shows at once. Only the keys below are written here;
# every other key in the file is kept as it is.

WEB_ENGINES = (('duckduckgo', 'DuckDuckGo'), ('startpage', 'Startpage'), ('brave', 'Brave Search'),
               ('ecosia', 'Ecosia'), ('google', 'Google'), ('bing', 'Bing'))


def _web_search_ok(value):
    return value in dict(WEB_ENGINES) or bool(re.fullmatch(r'https://[^\s"\\]{1,200}', value) and '%s' in value)


def _as_bool(value):
    return value == 'true'


SHELL_OPTIONS = {
    # key: (default, check(value) -> bool[, convert(value) -> what shell.json holds])
    'webSearch': ('duckduckgo', _web_search_ok),
    # Weather (WeatherService.qml): off until turned on; units; the temperature on the bar.
    'weather': (False, lambda v: v in ('true', 'false'), _as_bool),
    'weatherUnits': ('auto', lambda v: v in ('auto', 'metric', 'imperial')),
    'barWeather': (False, lambda v: v in ('true', 'false'), _as_bool),
}


def read_shell_json(paths):
    data = _loads(read_text(paths.arctic / 'shell.json') or '')
    return data if isinstance(data, dict) else {}


def cmd_shell_options(paths, _args):
    data = read_shell_json(paths)
    out = {key: data.get(key, spec[0]) for key, spec in SHELL_OPTIONS.items()}
    out.update(ok=True, engines=[dict(id=i, name=n) for i, n in WEB_ENGINES])
    return out


def cmd_shell_option_set(paths, args):
    if len(args) != 2 or args[0] not in SHELL_OPTIONS:
        raise Failure('usage: shell-option-set {} VALUE'.format('|'.join(SHELL_OPTIONS)))
    key, value = args
    spec = SHELL_OPTIONS[key]
    if not spec[1](value):
        raise Failure('That isn’t a value Arctic can use for this.')
    data = read_shell_json(paths)
    data[key] = spec[2](value) if len(spec) > 2 else value
    atomic_write(paths.arctic / 'shell.json', json.dumps(data, indent=2) + '\n')
    return cmd_shell_options(paths, [])


# ---- where you are, for the weather (shell/scripts/weather.py, Open-Meteo) ------------------------

def cmd_weather_place(paths, args):
    """weather-place                       the place the weather is for
    weather-place search TEXT           places called that (asks Open-Meteo's geocoding)
    weather-place set NAME LAT LON [DETAIL]   use that place (~/.config/arctic/location.json)
    weather-place zone                  back to your time zone's city"""
    script = shell_script(paths, 'weather.py')
    if not script:
        return dict(ok=True, available=False)
    location = paths.arctic / 'location.json'
    if args and args[0] == 'search' and len(args) == 2:
        code, out, _err = run([sys.executable, str(script), 'geocode', args[1], '--json'], timeout=20)
        data = _loads(out.strip())
        if not isinstance(data, dict) or not data.get('ok'):
            raise Failure((data or {}).get('error') if isinstance(data, dict) else 'Places couldn’t be searched.')
        return dict(ok=True, available=True, places=data.get('places', []))
    if args and args[0] == 'set' and len(args) in (4, 5):
        try:
            lat, lon = float(args[2]), float(args[3])
        except ValueError:
            raise Failure('A place needs a latitude and a longitude.') from None
        name, detail = args[1].strip(), (args[4].strip() if len(args) == 5 else '')
        if not (0 < len(name) <= 80 and len(detail) <= 120 and -90 <= lat <= 90 and -180 <= lon <= 180):
            raise Failure('That isn’t a place Arctic can use.')
        atomic_write(location, json.dumps(dict(name=name, detail=detail, lat=round(lat, 4), lon=round(lon, 4))) + '\n')
    elif args == ['zone']:
        with contextlib.suppress(FileNotFoundError):
            location.unlink()
    elif args:
        raise Failure('usage: weather-place [search TEXT | set NAME LAT LON [DETAIL] | zone]')
    code, out, _err = run([sys.executable, str(script), 'place', '--json'], timeout=10)
    data = _loads(out.strip())
    if not isinstance(data, dict) or not data.get('ok'):
        return dict(ok=True, available=True, place=None)
    return dict(ok=True, available=True, place=dict(name=data.get('name'), detail=data.get('detail', ''),
                                                     source=data.get('source')))


# ---- light and dark by the clock (arctic-daylight) ------------------------------------------------

def cmd_daylight(paths, args):
    if not which('arctic-daylight'):
        return dict(ok=True, available=False)
    argv = ['arctic-daylight'] + (list(args) if args else ['--json'])
    code, out, err = run(argv, timeout=60)
    data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if not isinstance(data, dict):
        raise Failure((strip_ansi(err).strip().splitlines() or ['The light and dark schedule couldn’t be read.'])[-1])
    if not data.get('ok'):
        raise Failure(data.get('error') or 'That didn’t work.')
    data['available'] = True
    return data


def cmd_daylight_set(paths, args):
    if not args or args[0] not in ('off', 'sun', 'hours') or (args[0] == 'hours') != (len(args) == 3) \
            or (args[0] != 'hours' and len(args) != 1):
        raise Failure('usage: daylight-set off|sun|hours LIGHT DARK')
    if not which('arctic-daylight'):
        raise Failure('arctic-daylight isn’t installed.')
    return cmd_daylight(paths, args)


# ---- the code font (arctic-font) ------------------------------------------------------------------

def cmd_fonts(paths, _args):
    if not which('arctic-font'):
        return dict(ok=True, available=False)
    code, out, err = run(['arctic-font', 'list', '--json'], timeout=20)
    data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if code != 0 or not isinstance(data, dict):
        raise Failure((strip_ansi(err).strip().splitlines() or ['The fonts couldn’t be listed.'])[-1])
    return dict(ok=True, available=True, current=str(data.get('current') or ''), size=data.get('size'),
                fonts=[str(f.get('family')) for f in data.get('fonts', []) if isinstance(f, dict) and f.get('family')],
                symbols=data.get('symbols') is True)


def cmd_font_set(paths, args):
    if len(args) != 1 or not args[0].strip():
        raise Failure('usage: font-set FAMILY')
    if not which('arctic-font'):
        raise Failure('arctic-font isn’t installed.')
    code, out, err = run(['arctic-font', 'set', args[0], '--json'], timeout=30)
    data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if not isinstance(data, dict) or not data.get('ok'):
        raise Failure((data or {}).get('error') if isinstance(data, dict) else (strip_ansi(err).strip() or 'The font couldn’t be changed.'))
    result = cmd_fonts(paths, [])
    result.update(changed=data.get('changed', []), skipped=data.get('skipped', []))
    return result


# ---- themes from the web (arctic-theme install / remove) -----------------------------------------

def _theme_json_verb(argv, what):
    if not which('arctic-theme'):
        raise Failure('arctic-theme isn’t installed.')
    code, out, err = run(['arctic-theme'] + argv + ['--json'], timeout=150)
    data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if code != 0 or not isinstance(data, dict) or not data.get('ok'):
        message = (strip_ansi(err).strip().splitlines() or ['The theme couldn’t be {}.'.format(what)])[-1]
        message = message.replace('arctic-theme: ', '')
        raise Failure(message[:1].upper() + message[1:] + ('' if message.endswith('.') else '.'))
    return data


def cmd_theme_install(paths, args):
    """theme-install URL: a theme repository (GitHub, GitLab, Codeberg); only its colours and
    pictures are kept."""
    if len(args) != 1 or not re.fullmatch(r'https://[^\s]{1,300}', args[0]):
        raise Failure('A theme link starts with https://, like https://github.com/owner/name.')
    data = _theme_json_verb(['install', args[0]], 'installed')
    result = cmd_theme(paths, [])
    result.update(installed=dict(name=data.get('name'), label=data.get('label'),
                                 dropped=[str(d) for d in data.get('dropped', [])][:50],
                                 backgrounds=data.get('backgrounds', 0)))
    return result


def cmd_theme_remove(paths, args):
    if len(args) != 1 or not re.fullmatch(r'[a-z0-9][a-z0-9._-]{0,63}', args[0]):
        raise Failure('usage: theme-remove NAME')
    _theme_json_verb(['remove', args[0]], 'removed')
    return cmd_theme(paths, [])


# ---- wallpaper rotation (arctic-wallpaper rotate) ------------------------------------------------

ROTATE_EVERY = ('off', '30m', '1h', '1d')


def cmd_wallpaper_rotate(paths, args):
    """wallpaper-rotate [off | 30m|1h|1d FOLDER|arctic [shuffle]]: a new picture every so often,
    without changing the chosen wallpaper or the colours."""
    if not which('arctic-wallpaper'):
        return dict(ok=True, available=False, every='off')
    if args:
        every = args[0]
        if every not in ROTATE_EVERY or (every == 'off') != (len(args) == 1) or len(args) > 3 \
                or (len(args) == 3 and args[2] != 'shuffle'):
            raise Failure('usage: wallpaper-rotate off | 30m|1h|1d FOLDER|arctic [shuffle]')
        argv = ['arctic-wallpaper', 'rotate', every] + ([] if every == 'off' else
                                                          [args[1]] + (['--shuffle'] if len(args) == 3 else []))
        code, _out, err = run(argv, timeout=30)
        if code != 0:
            message = (strip_ansi(err).strip().splitlines() or ['The wallpaper rotation couldn’t be changed.'])[-1]
            message = message.replace('arctic-wallpaper: ', '')
            raise Failure(message[:1].upper() + message[1:])
    code, out, _err = run(['arctic-wallpaper', 'rotate'], timeout=10)
    data = _loads(out.strip())
    if code != 0 or not isinstance(data, dict):
        return dict(ok=True, available=True, every='off')
    every = data.get('every') if data.get('every') in ROTATE_EVERY else 'off'
    return dict(ok=True, available=True, every=every, folder=str(data.get('folder') or ''),
                shuffle=data.get('shuffle') is True)


# ---- accessibility ---------------------------------------------------------------------------------

def cmd_accessibility(paths, _args):
    """What the Accessibility page shows besides motion, text size and the pointer. contrast is
    None when arctic-theme can't say (an older one: the row is hidden)."""
    contrast = None
    if which('arctic-theme'):
        code, out, _err = run(['arctic-theme', 'contrast', '--json'], timeout=10)
        data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
        if code == 0 and isinstance(data, dict) and data.get('ok'):
            contrast = data.get('contrast') == 'high'
    return dict(ok=True, kbptr=bool(which('wl-kbptr')), kbptrHelper=bool(which('arctic-kbptr')), contrast=contrast)


def cmd_contrast_set(paths, args):
    """High contrast on or off: arctic-theme relinks the active theme to its high-contrast take."""
    if len(args) != 1 or args[0] not in ('on', 'off'):
        raise Failure('usage: contrast-set on|off')
    if not which('arctic-theme'):
        raise Failure('arctic-theme isn’t installed.')
    code, out, err = run(['arctic-theme', 'contrast', args[0], '--json'], timeout=60)
    data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if code != 0 or not isinstance(data, dict) or not data.get('ok'):
        raise Failure((strip_ansi(err).strip().splitlines() or ['High contrast couldn’t be changed.'])[-1])
    return cmd_accessibility(paths, [])


COMMANDS = {
    'state': cmd_state, 'set': cmd_set, 'set-cursor': cmd_set_cursor, 'reset': cmd_reset, 'layout': cmd_layout,
    'undo': cmd_undo, 'binds': cmd_binds, 'bind-add': cmd_bind_add, 'bind-remove': cmd_bind_remove,
    'notices': cmd_notices, 'clipboard': cmd_clipboard, 'clipboard-set': cmd_clipboard_set,
    'clipboard-clear': cmd_clipboard_clear,
    'startup': cmd_startup, 'startup-add': cmd_startup_add, 'startup-remove': cmd_startup_remove,
    'displays': cmd_displays, 'display-arrange': cmd_display_arrange, 'display-try': cmd_display_try,
    'display-keep': cmd_display_keep,
    'display-revert': cmd_display_revert, 'display-forget': cmd_display_forget, 'devices': cmd_devices,
    'power-profile': cmd_power_profile, 'apps': cmd_apps, 'app-set': cmd_app_set, 'idle': cmd_idle,
    'idle-set': cmd_idle_set, 'keyboard-data': cmd_keyboard_data, 'cursor-themes': cmd_cursor_themes,
    'theme': cmd_theme, 'theme-set': cmd_theme_set, 'theme-auto': cmd_theme_auto, 'theme-mode': cmd_theme_mode,
    'motion': cmd_motion, 'motion-set': cmd_motion_set, 'text-scale': cmd_text_scale,
    'wallpapers': cmd_wallpapers, 'wallpaper-set': cmd_wallpaper_set, 'wallpaper-import': cmd_wallpaper_import,
    'wallpaper-delete': cmd_wallpaper_delete, 'wallpaper-rename': cmd_wallpaper_rename, 'wallhaven': cmd_wallhaven,
    'updates': cmd_updates,
    'update-run': cmd_update_run, 'network': cmd_network, 'wifi': cmd_wifi, 'about': cmd_about, 'caps': cmd_caps,
    'bluetooth-pair': cmd_bluetooth_pair, 'battery': cmd_battery, 'shell-set': cmd_shell_set,
    'network-saved': cmd_network_saved, 'network-forget': cmd_network_forget, 'vpn': cmd_vpn,
    'network-ca-set': cmd_network_ca_set,
    'ensure-source': lambda paths, _a: dict(ok=True, source=ensure_sourced(paths)),
    'notifications': cmd_notifications, 'notification-set': cmd_notification_set,
    'notification-rule-set': cmd_notification_rule_set, 'notification-history-clear': cmd_notification_history_clear,
    'dnd-set': cmd_dnd_set,
}
# Web apps (stream 1)
TOOLS['arcticWebapp'] = 'arctic-webapp'
COMMANDS.update({
    'webapps': cmd_webapps, 'webapp-set': cmd_webapp_set, 'webapp-reset-permissions': cmd_webapp_reset_permissions,
    'webapp-refresh': cmd_webapp_refresh, 'webapp-clear': cmd_webapp_clear, 'webapp-open': cmd_webapp_open,
    'webapp-remove': cmd_webapp_remove, 'webapp-forget': cmd_webapp_forget, 'webapp-runtimes': cmd_webapp_runtimes,
})


# Commands that read, change and write back settings.conf (or another file of ours): they run
# one at a time (settings_lock). display-revert takes the lock itself, after its wait.
WRITERS = {'set', 'set-cursor', 'reset', 'layout', 'undo', 'bind-add', 'bind-remove', 'startup-add',
           'startup-remove', 'display-try', 'display-keep', 'display-forget', 'app-set', 'idle-set',
           'ensure-source', 'shell-set', 'notification-set', 'notification-rule-set'}


# Stream 5 (system): night light, keep awake, XDG autostart, printers, date and time, Flatpak
# and firmware updates are in arctic_system.py (settings/tests/test_system_helpers.py).
sys.modules.setdefault('arctic_settings', sys.modules[__name__])   # when run as a script
import arctic_system  # noqa: E402
COMMANDS.update(arctic_system.COMMANDS)
WRITERS |= arctic_system.WRITERS

# The shell's options, the light/dark schedule, fonts and accessibility (0.3 "experience").
COMMANDS.update({'shell-options': cmd_shell_options, 'shell-option-set': cmd_shell_option_set,
                 'daylight': cmd_daylight, 'daylight-set': cmd_daylight_set, 'accessibility': cmd_accessibility,
                 'contrast-set': cmd_contrast_set, 'wallpaper-rotate': cmd_wallpaper_rotate,
                 'weather-place': cmd_weather_place, 'theme-install': cmd_theme_install,
                 'theme-remove': cmd_theme_remove,
                 'fonts': cmd_fonts, 'font-set': cmd_font_set})
WRITERS |= {'shell-option-set', 'weather-place'}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ('-h', '--help') or argv[0] not in COMMANDS:
        print(__doc__.strip())
        return 0 if argv and argv[0] in ('-h', '--help') else 2
    paths = Paths()
    try:
        with settings_lock(paths) if argv[0] in WRITERS else contextlib.nullcontext():
            result = COMMANDS[argv[0]](paths, argv[1:])
    except Failure as error:
        print(json.dumps(dict(ok=False, error=str(error))))
        return 1
    except Exception as error:  # noqa: BLE001 — every failure reaches the app as a sentence
        print(json.dumps(dict(ok=False, error='Something went wrong: {}'.format(error or error.__class__.__name__))))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    sys.exit(main())
