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
    bind-remove INDEX
    startup                       startup apps: yours (exec-once in settings.conf) and Arctic's
    startup-add COMMAND | --app DESKTOP-ID
    startup-remove INDEX
    displays                      outputs (wlr-randr --json, else mmsg) and saved monitor rules
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
    updates | update-run now|apply|channel NAME|auto on|off                     (arctic-update)
    network | wifi on|off         NetworkManager status (nmcli)
    notifications                 do not disturb, its schedule, history and the per-app rules
    notification-set KEY VALUE    history on|off, schedule on|off, schedule-from / schedule-to HH:MM
    notification-rule-set APP KEY on|off…   toasts, history, allow_during_dnd, silence_urgent
    notification-history-clear    empty the notification centre
    dnd-set on|off|1h|tomorrow    do not disturb now (arctic-dnd)
    about                         Arctic and Fedora versions, hardware, Mango and Quickshell
    caps                          which helper commands and tools are installed

Writes are atomic (temporary file + rename), user-level, validated first (our own key table,
then `mango -c FILE -p` when Mango is installed) and backed up to
~/.local/state/arctic/settings-backups. Nothing here needs root.
"""
import contextlib
import fcntl
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
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


def backup(paths, path):
    """Copy path into the backups folder (newest BACKUPS_KEPT per file). Returns the copy."""
    path = Path(path)
    if not path.is_file():
        return None
    paths.backups.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-%06d' % (time.time_ns() // 1000 % 1000000)
    target = paths.backups / '{}.{}'.format(path.name, stamp)
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
    stamp = time.strftime('%Y%m%d-%H%M%S') + '-%06d' % (time.time_ns() // 1000 % 1000000)
    target = paths.backups / '{}.{}{}'.format(path.name, stamp, ABSENT)
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
    reloaded = reload_mango() if reload else False
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
             'backslash': '\\'}
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


def chain_binds(paths):
    """Keyboard binds in the config chain: [{mods, key, action, args, file, keymode, label}]."""
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
                        mine=same_file(origin, paths.settings_conf)))
    return out


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
    mine = [dict(index=i, label=combo_label(parse_mods(b['mods']), b['key']), command=b['command'],
                 mods=b['mods'], key=b['key']) for i, b in enumerate(model.binds)]
    return dict(ok=True, sheet=parse_sheet(sheet or ''), all=chain_binds(paths), mine=mine)


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
    command = validate_command(args[2])
    # Mango joins spawn arguments split at commas again, but stops at an empty part or a "0".
    parts = command.split(',')
    if len(parts) > 5 or any(p == '' or p == '0' for p in parts[1:]):
        raise Failure('Mango can’t pass that many commas on. Put the command in a script instead.')
    combo = (frozenset(mods), key.lower())
    for bind in chain_binds(paths):
        if bind['keymode'] not in ('default', 'common'):
            continue
        if (frozenset(bind['mods']), bind['key'].lower()) == combo:
            raise Failure('{} already does something: {}. Pick another key.'.format(bind['label'], bind['what']))
    model = load_settings(paths)
    for bind in model.binds:
        if (frozenset(parse_mods(bind['mods'])), bind['key'].lower()) == combo:
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

TRANSFORMS = ['normal', '90', '180', '270', 'flipped', 'flipped-90', 'flipped-180', 'flipped-270']


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
                return [dict(name=m.get('name', ''), description='', make='', model='', enabled=True,
                             modes=[], width=0, height=0, refresh=0, x=m.get('x', 0), y=m.get('y', 0),
                             scale=m.get('scale', 1), transform='normal', adaptiveSync=bool(m.get('is_vrr')),
                             logicalWidth=m.get('width', 0), logicalHeight=m.get('height', 0))
                        for m in monitors], 'mmsg'
            except (ValueError, AttributeError):
                pass
    return [], ''


def normalise_wlr(o):
    modes = [dict(width=m['width'], height=m['height'], refresh=round(float(m.get('refresh', 0)), 3),
                  preferred=bool(m.get('preferred')), current=bool(m.get('current')))
             for m in o.get('modes', [])]
    current = next((m for m in modes if m['current']), modes[0] if modes else None)
    pos = o.get('position') or {}
    scale = float(o.get('scale') or 1)
    transform = o.get('transform') or 'normal'
    width = current['width'] if current else 0
    height = current['height'] if current else 0
    if transform in ('90', '270', 'flipped-90', 'flipped-270'):
        width, height = height, width
    return dict(name=o.get('name', ''), description=o.get('description', ''), make=o.get('make') or '',
                model=o.get('model') or '', serial=o.get('serial') or '', enabled=bool(o.get('enabled', True)),
                modes=modes, width=current['width'] if current else 0, height=current['height'] if current else 0,
                refresh=current['refresh'] if current else 0, x=int(pos.get('x', 0)), y=int(pos.get('y', 0)),
                scale=scale, transform=transform, adaptiveSync=bool(o.get('adaptive_sync')),
                logicalWidth=round(width / scale) if scale else width,
                logicalHeight=round(height / scale) if scale else height)


def cmd_displays(paths, _args):
    outputs, backend = list_outputs()
    pending = read_text(paths.display_pending)
    return dict(ok=True, outputs=outputs, backend=backend, rules=load_settings(paths).monitors,
                canApply=backend in ('wlr-randr', 'mmsg'), canChangeMode=backend == 'wlr-randr',
                pending=bool(pending), revertAfter=REVERT_AFTER)


def check_layout(outputs):
    """Validate a display layout from the app; returns it cleaned (positions from 0,0)."""
    if not isinstance(outputs, list) or not outputs:
        raise Failure('No displays to set up.')
    clean = []
    for o in outputs:
        name = str(o.get('name', ''))
        if not RE_OUTPUT.match(name):
            raise Failure('That display name isn’t valid.')
        item = dict(name=name, enabled=bool(o.get('enabled', True)))
        try:
            item['width'] = int(o.get('width') or 0)       # 0: keep the current mode
            item['height'] = int(o.get('height') or 0)
            item['refresh'] = round(float(o.get('refresh') or 0), 3)
            item['x'] = int(o.get('x', 0))
            item['y'] = int(o.get('y', 0))
            item['scale'] = round(float(o.get('scale') or 1), 3)
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
    enabled = [o for o in clean if o['enabled']]
    if not enabled:
        raise Failure('At least one display has to stay on.')
    # XWayland misreads clicks with negative positions (Mango docs): start at 0,0.
    min_x = min(o['x'] for o in enabled)
    min_y = min(o['y'] for o in enabled)
    for o in clean:
        o['x'] -= min_x
        o['y'] -= min_y
    return clean


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
    try:
        layout = check_layout(json.loads(args[0] if args else '[]'))
    except ValueError:
        raise Failure('The display settings came in garbled.') from None
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
    return dict(ok=True, token=token, revertAfter=REVERT_AFTER, backend=backend or 'config')


def set_monitor_rules(model, layout):
    """Save the layout as monitor rules. A display switched off is never saved as `disable:1`:
    Mango applies that rule whenever the output appears, even when it is the only screen (a
    laptop started without its dock would come up dark). Off lasts for this session only; the
    display keeps its earlier rule, if any, without a disable key. Returns the displays that
    are off for this session only."""
    rules = {r['name']: r for r in model.monitors}
    session_only = []
    for o in layout:
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
        rules[o['name']] = rule
    model.monitors = list(rules.values())
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
         keys='Super + W'),
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
    return dict(ok=True, layouts=sorted(layouts, key=lambda l: l['label'].lower()), variants=variants,
                switchKeys=switch, capsOptions=caps)


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
            out.append(dict(id=ident, name=str(item.get('name') or ident), dark=item.get('dark'),
                            kind=str(item.get('kind') or item.get('type') or '')))
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
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', name):
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
    code, out, _err = run(['gsettings', 'get'] + schema, timeout=5)
    try:
        return dict(ok=True, available=code == 0, value=float(out.strip()) if code == 0 else 1.0)
    except ValueError:
        return dict(ok=True, available=False, value=1.0)


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
    home = osr.get('HOME_URL', 'https://github.com/yuvalkolodkingal/O-Tism')
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
         'arcticDnd': 'arctic-dnd'}


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


COMMANDS = {
    'state': cmd_state, 'set': cmd_set, 'set-cursor': cmd_set_cursor, 'reset': cmd_reset, 'layout': cmd_layout,
    'undo': cmd_undo, 'binds': cmd_binds, 'bind-add': cmd_bind_add, 'bind-remove': cmd_bind_remove,
    'startup': cmd_startup, 'startup-add': cmd_startup_add, 'startup-remove': cmd_startup_remove,
    'displays': cmd_displays, 'display-try': cmd_display_try, 'display-keep': cmd_display_keep,
    'display-revert': cmd_display_revert, 'display-forget': cmd_display_forget, 'devices': cmd_devices,
    'power-profile': cmd_power_profile, 'apps': cmd_apps, 'app-set': cmd_app_set, 'idle': cmd_idle,
    'idle-set': cmd_idle_set, 'keyboard-data': cmd_keyboard_data, 'cursor-themes': cmd_cursor_themes,
    'theme': cmd_theme, 'theme-set': cmd_theme_set, 'theme-auto': cmd_theme_auto, 'theme-mode': cmd_theme_mode,
    'motion': cmd_motion, 'motion-set': cmd_motion_set, 'text-scale': cmd_text_scale,
    'wallpapers': cmd_wallpapers, 'wallpaper-set': cmd_wallpaper_set, 'updates': cmd_updates,
    'update-run': cmd_update_run, 'network': cmd_network, 'wifi': cmd_wifi, 'about': cmd_about, 'caps': cmd_caps,
    'ensure-source': lambda paths, _a: dict(ok=True, source=ensure_sourced(paths)),
    'notifications': cmd_notifications, 'notification-set': cmd_notification_set,
    'notification-rule-set': cmd_notification_rule_set, 'notification-history-clear': cmd_notification_history_clear,
    'dnd-set': cmd_dnd_set,
}


# Commands that read, change and write back settings.conf (or another file of ours): they run
# one at a time (settings_lock). display-revert takes the lock itself, after its wait.
WRITERS = {'set', 'set-cursor', 'reset', 'layout', 'undo', 'bind-add', 'bind-remove', 'startup-add',
           'startup-remove', 'display-try', 'display-keep', 'display-forget', 'app-set', 'idle-set',
           'ensure-source', 'notification-set', 'notification-rule-set'}


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
