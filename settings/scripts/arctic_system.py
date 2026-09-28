"""arctic_system.py — Arctic Settings' commands for system features (stream 5 of Arctic 0.3):
night light, keep awake, apps' own autostart entries, printers, date, time and language, Flatpak
apps and firmware. arctic_settings.py merges COMMANDS and WRITERS into its own; the conventions
are its (one JSON object per command, Failure for a sentence, argv lists, never a shell).

    nightlight | nightlight-set KEY=VALUE…|now on|off    night light schedule (arctic-nightlight)
    keep-awake [on [MINUTES]|off] no lock or suspend for a while (arctic-keep-awake)
    autostart | autostart-set ID on|off           apps' own "start on login" entries (XDG autostart)
    printers | printer-default NAME | printer-cancel NAME          CUPS queues (lpstat, lpoptions)
    datetime [zones] [locales] | datetime-set timezone ZONE|ntp on|off|time T|locale LANG
                                  time zone, network time, the clock, the language (polkit)
    more-updates | more-update-run apps|firmware  Flatpak apps and firmware (arctic-update)
    lid | lid-set suspend|lock|screen-off          closing the lid without another screen (lid.conf)
    effects | effects-set lighter auto|on|off | game on|off      arctic-effects
"""
import os
import re
import subprocess
import time
from pathlib import Path

from arctic_settings import (Failure, _loads, atomic_write, backup, exec_command, read_desktop, read_text,
                             run, strip_ansi, which)


# ---- night light and keep awake (arctic-nightlight, arctic-keep-awake) -------------------------

def _helper_json(argv, timeout=20, missing=None):
    """Run an arctic-* helper that answers with one JSON line; its error sentence becomes ours."""
    if not which(argv[0]):
        if missing is not None:
            return missing
        raise Failure('{} isn’t installed.'.format(argv[0]))
    code, out, err = run(argv, timeout=timeout)
    data = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if not isinstance(data, dict):
        raise Failure((strip_ansi(err).strip().splitlines() or ['{} didn’t answer.'.format(argv[0])])[-1])
    if code != 0 or not data.get('ok'):
        raise Failure(data.get('error') or 'That didn’t work.')
    return data


def cmd_nightlight(paths, _args):
    data = _helper_json(['arctic-nightlight', 'status', '--json'], missing=dict(ok=True, helper=False))
    data.setdefault('helper', True)
    return data


def cmd_nightlight_set(paths, args):
    """nightlight-set KEY=VALUE… (the schedule) or nightlight-set now on|off."""
    if args[:1] == ['now']:
        if args[1:] not in (['on'], ['off']):
            raise Failure('usage: nightlight-set now on|off')
        data = _helper_json(['arctic-nightlight', args[1], '--quiet'])
    else:
        allowed = ('mode', 'temp', 'from', 'to', 'lat', 'lon')
        if not args or any(a.split('=', 1)[0] not in allowed or '=' not in a for a in args):
            raise Failure('usage: nightlight-set KEY=VALUE… ({})'.format(', '.join(allowed)))
        data = _helper_json(['arctic-nightlight', 'set'] + list(args))
    data['helper'] = True
    return data


def cmd_keep_awake(paths, args):
    """keep-awake [on [MINUTES]|off]: arctic-keep-awake's status, or turn it on or off."""
    if not args:
        data = _helper_json(['arctic-keep-awake', 'status', '--json'], missing=dict(ok=True, helper=False))
    elif args[0] == 'on' and (len(args) == 1 or (len(args) == 2 and args[1].isdigit())):
        data = _helper_json(['arctic-keep-awake', 'on'] + args[1:] + ['--quiet'])
    elif args == ['off']:
        data = _helper_json(['arctic-keep-awake', 'off', '--quiet'])
    else:
        raise Failure('usage: keep-awake [on [MINUTES]|off]')
    data.setdefault('helper', True)
    return data


# ---- XDG autostart (~/.config/autostart, /etc/xdg/autostart) ------------------------------------

# Entries Arctic keeps off in the Mango session (packaging/desktop/autostart/arctic-starts-it.conf).
ARCTIC_AUTOSTART = {'nm-applet', 'blueman', 'geoclue-demo-agent'}
RE_AUTOSTART_ID = re.compile(r'^[A-Za-z0-9._+-]{1,128}$')


def autostart_dirs(paths):
    system = [Path(d) / 'autostart' for d in (paths.env.get('XDG_CONFIG_DIRS') or '/etc/xdg').split(':') if d]
    return paths.config / 'autostart', system


def _is_true(value):
    return str(value or '').strip().lower() == 'true'


def autostart_entries(paths):
    """What systemd-xdg-autostart-generator starts in the Mango session, as the Startup page
    lists it: a file in ~/.config/autostart replaces the system one of the same name, Hidden=true
    there switches it off, and OnlyShowIn/NotShowIn/TryExec/X-systemd-skip decide as systemd does."""
    user, system = autostart_dirs(paths)
    found = {}
    for folder in [user] + system:
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob('*.desktop')):
            found.setdefault(path.name[:-8], path)
    out = []
    for ident, path in sorted(found.items()):
        raw = read_desktop(path)
        mine = path.parent == user
        if ident in ARCTIC_AUTOSTART or raw.get('Type', 'Application') != 'Application' or not raw.get('Exec'):
            continue
        if (_is_true(raw.get('Hidden')) and not mine) or _is_true(raw.get('X-systemd-skip')):
            continue
        desktops = [d.lower() for d in raw.get('OnlyShowIn', '').split(';') if d]
        if (desktops and 'mango' not in desktops) or 'mango' in [d.lower() for d in raw.get('NotShowIn', '').split(';')]:
            continue
        tryexec = raw.get('TryExec', '')
        if tryexec and not (os.access(tryexec, os.X_OK) if tryexec.startswith('/') else which(tryexec, paths.env)):
            continue
        system_copy = next((str(f / path.name) for f in system if (f / path.name).is_file()), '')
        out.append(dict(id=ident, name=raw.get('Name') or ident, comment=raw.get('Comment', ''),
                        enabled=not _is_true(raw.get('Hidden')), mine=mine, system=system_copy,
                        exec=exec_command(dict(exec=raw['Exec']))))
    return out


def cmd_autostart(paths, _args):
    return dict(ok=True, entries=autostart_entries(paths))


def _set_hidden(text, hidden):
    """The desktop entry text with Hidden=true (or without a Hidden line) in [Desktop Entry]."""
    out, section, done = [], '', False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith('['):
            if section == '[Desktop Entry]' and hidden and not done:
                out.append('Hidden=true')
                done = True
            section = stripped
        elif section == '[Desktop Entry]' and stripped.split('=', 1)[0].strip() == 'Hidden':
            continue
        out.append(line)
    if section == '[Desktop Entry]' and hidden and not done:
        out.append('Hidden=true')
    return '\n'.join(out) + '\n'


def cmd_autostart_set(paths, args):
    """autostart-set ID on|off: switch an app's own "start on login" on or off for you."""
    if len(args) != 2 or args[1] not in ('on', 'off') or not RE_AUTOSTART_ID.match(args[0]):
        raise Failure('usage: autostart-set ID on|off')
    entry = next((e for e in autostart_entries(paths) if e['id'] == args[0]), None)
    if not entry:
        raise Failure('That app doesn’t start on login any more.')
    user, _system = autostart_dirs(paths)
    target = user / (entry['id'] + '.desktop')
    source = target if entry['mine'] else Path(entry['system'])
    text = _set_hidden(read_text(source) or '', args[1] == 'off')
    system_text = read_text(entry['system']) if entry['system'] else None
    if args[1] == 'on' and system_text is not None and _set_hidden(system_text, False) == text:
        target.unlink(missing_ok=True)      # nothing of yours left: follow the app's own file again
    else:
        atomic_write(target, text)
    return cmd_autostart(paths, [])


# ---- printers (CUPS: lpstat, lpoptions, cancel) -------------------------------------------------

RE_QUEUE = re.compile(r'^[^\s/#\\]{1,127}$')     # a CUPS queue name: no spaces, "/", "#" or "\\"


def _c_env(paths):
    env = dict(paths.env)
    env.update(LC_ALL='C', LANG='C')
    return env


def parse_lpstat_printers(text):
    """`lpstat -l -p` → [{name, state, description, location, reason}] (C locale)."""
    printers = []
    for line in (text or '').splitlines():
        head = re.match(r'^printer (\S+) (?:is (idle)|now (printing) \S+?|(disabled))\b', line)
        if head:
            state = head.group(2) or head.group(3) or 'paused'
            printers.append(dict(name=head.group(1), state=state, description='', location='', reason=''))
            continue
        if not printers or not line.startswith('\t'):
            continue
        key, _, value = line.strip().partition(': ')
        if key == 'Description':
            printers[-1]['description'] = value.strip()
        elif key == 'Location':
            printers[-1]['location'] = value.strip()
        elif printers[-1]['state'] == 'paused' and not printers[-1]['reason'] and line.startswith('\t') \
                and ':' not in line and line.strip():
            printers[-1]['reason'] = line.strip()
    return printers


def cmd_printers(paths, _args):
    if not which('lpstat', paths.env):
        return dict(ok=True, available=False, printers=[], network=[],
                    canAdd=bool(which('system-config-printer', paths.env)),
                    scan=bool(which('simple-scan', paths.env)))
    env = _c_env(paths)
    code, out, err = run(['lpstat', '-l', '-p'], timeout=15, env=env)
    running = 'scheduler is not running' not in (out + err).lower()
    printers = parse_lpstat_printers(out) if code == 0 else []
    _c, default, _e = run(['lpstat', '-d'], timeout=10, env=env)
    match = re.search(r'destination: (\S+)', default)
    default = match.group(1) if match else ''
    _c, jobs, _e = run(['lpstat', '-o'], timeout=10, env=env)
    counts = {}
    for line in jobs.splitlines():
        job = line.split(' ', 1)[0]
        if '-' in job:
            counts[job.rsplit('-', 1)[0]] = counts.get(job.rsplit('-', 1)[0], 0) + 1
    for printer in printers:
        printer.update(default=printer['name'] == default, jobs=counts.get(printer['name'], 0))
    # Driverless printers CUPS sees on the network (DNS-SD): any app's print dialog can use them.
    _c, everything, _e = run(['lpstat', '-e'], timeout=15, env=env)
    known = {p['name'] for p in printers}
    network = [dict(name=name, default=name == default) for name in everything.split()
               if name not in known and RE_QUEUE.match(name)]
    return dict(ok=True, available=True, running=running, printers=printers, network=network,
                canAdd=bool(which('system-config-printer', paths.env)),
                scan=bool(which('simple-scan', paths.env)))


def cmd_printer_default(paths, args):
    """printer-default NAME: your default printer (lpoptions -d, in ~/.cups/lpoptions)."""
    if len(args) != 1 or not RE_QUEUE.match(args[0]):
        raise Failure('usage: printer-default NAME')
    code, _out, err = run(['lpoptions', '-d', args[0]], timeout=15, env=_c_env(paths))
    if code != 0:
        raise Failure((err.strip().splitlines() or ['That printer couldn’t be made the default.'])[-1])
    return cmd_printers(paths, [])


def cmd_printer_cancel(paths, args):
    """printer-cancel NAME: cancel your print jobs on that printer."""
    if len(args) != 1 or not RE_QUEUE.match(args[0]):
        raise Failure('usage: printer-cancel NAME')
    code, _out, err = run(['cancel', '-a', args[0]], timeout=15, env=_c_env(paths))
    if code != 0:
        raise Failure((err.strip().splitlines() or ['The print jobs couldn’t be cancelled.'])[-1])
    return cmd_printers(paths, [])


# ---- date, time and language (timedatectl, localectl: timedated / localed through polkit) --------

RE_ZONE = re.compile(r'^[A-Za-z0-9_+-]+(/[A-Za-z0-9_+-]+){0,2}$')
RE_LOCALE = re.compile(r'^[A-Za-z]{2,3}(_[A-Za-z0-9]{2,3})?(\.[A-Za-z0-9-]+)?(@[a-z]+)?$')
RE_DATETIME = re.compile(r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?$')
AUTH_WAIT = 180     # seconds: the password dialog (polkit) may be open for a while


def _show(argv, env):
    """`timedatectl show` / `localectl` style KEY=VALUE lines → dict."""
    code, out, _err = run(argv, timeout=10, env=env)
    values = {}
    if code == 0:
        for line in out.splitlines():
            key, sep, value = line.partition('=')
            if sep:
                values[key.strip()] = value.strip()
    return values


def cmd_datetime(paths, args):
    env = _c_env(paths)
    result = dict(ok=True, available=bool(which('timedatectl', paths.env)), timezone='', ntp=False,
                  ntpSynced=False, canNtp=False, zones=[], locale='', locales=[],
                  localectl=bool(which('localectl', paths.env)))
    if result['available']:
        info = _show(['timedatectl', 'show'], env)
        result['available'] = bool(info)       # systemd-timedated answered
        result.update(timezone=info.get('Timezone', ''), ntp=info.get('NTP') == 'yes',
                      ntpSynced=info.get('NTPSynchronized') == 'yes', canNtp=info.get('CanNTP') == 'yes')
        if 'zones' in args:
            _c, out, _e = run(['timedatectl', 'list-timezones'], timeout=10, env=env)
            result['zones'] = [z for z in out.split() if RE_ZONE.match(z)]
    if not result['timezone']:
        target = os.path.realpath('/etc/localtime')
        result['timezone'] = target.split('/zoneinfo/', 1)[1] if '/zoneinfo/' in target else ''
    if result['localectl']:
        _c, out, _e = run(['localectl', 'status'], timeout=10, env=env)
        match = re.search(r'LANG=(\S+)', out)
        result['locale'] = match.group(1) if match else ''
        if 'locales' in args:
            _c, out, _e = run(['localectl', 'list-locales'], timeout=15, env=env)
            result['locales'] = [l for l in out.split() if RE_LOCALE.match(l) and l.endswith('.UTF-8')]
    now = time.localtime()
    result.update(now=time.strftime('%Y-%m-%d %H:%M', now), offset=time.strftime('%z', now))
    return result


def _auth_run(argv, paths, what):
    code, out, err = run(argv, timeout=AUTH_WAIT, env=_c_env(paths))
    if code != 0:
        said = (err or out).strip().splitlines()
        if said and ('not authorized' in said[-1].lower() or 'access denied' in said[-1].lower()
                     or 'authentication' in said[-1].lower()):
            raise Failure('{} needs your password, and it wasn’t given.'.format(what))
        raise Failure((said or ['{} didn’t work.'.format(what)])[-1])


def cmd_datetime_set(paths, args):
    """datetime-set timezone ZONE | ntp on|off | time 'YYYY-MM-DD HH:MM' | locale LANG."""
    if len(args) != 2:
        raise Failure('usage: datetime-set timezone ZONE|ntp on|off|time "YYYY-MM-DD HH:MM"|locale LANG')
    what, value = args
    if what == 'timezone':
        zones = cmd_datetime(paths, ['zones'])['zones']
        if not RE_ZONE.match(value) or (zones and value not in zones):
            raise Failure('There’s no time zone called {}.'.format(value))
        _auth_run(['timedatectl', 'set-timezone', value], paths, 'Changing the time zone')
    elif what == 'ntp' and value in ('on', 'off'):
        _auth_run(['timedatectl', 'set-ntp', 'true' if value == 'on' else 'false'], paths, 'Changing how the clock is set')
    elif what == 'time':
        if not RE_DATETIME.match(value):
            raise Failure('Write the date and time like 2026-09-28 21:30.')
        if cmd_datetime(paths, [])['ntp']:
            raise Failure('Turn off “Set the time automatically” first.')
        _auth_run(['timedatectl', 'set-time', value if value.count(':') == 2 else value + ':00'], paths, 'Setting the clock')
    elif what == 'locale':
        locales = cmd_datetime(paths, ['locales'])['locales']
        if not RE_LOCALE.match(value) or (locales and value not in locales):
            raise Failure('That language isn’t installed.')
        _auth_run(['localectl', 'set-locale', 'LANG=' + value], paths, 'Changing the language')
    else:
        raise Failure('usage: datetime-set timezone ZONE|ntp on|off|time "YYYY-MM-DD HH:MM"|locale LANG')
    return cmd_datetime(paths, [])


# ---- Flatpak apps and firmware (arctic-update flatpak | firmware) -------------------------------

def cmd_more_updates(paths, _args):
    """What arctic-update says about Flatpak apps (the last daily run) and firmware (fwupd)."""
    result = dict(ok=True, available=bool(which('arctic-update', paths.env)),
                  flatpak=bool(which('flatpak', paths.env)), apps=None, auto=False,
                  firmware=dict(available=False, devices=[], error=''))
    if not result['available']:
        return result
    code, out, _err = run(['arctic-update', 'status', '--json'], timeout=30)
    data = _loads(out) if code == 0 else None
    if isinstance(data, dict):
        result.update(apps=data.get('apps'), auto=data.get('auto') == 'download-and-install-on-reboot')
    code, out, _err = run(['arctic-update', 'firmware', '--json'], timeout=60)
    firmware = _loads(out.strip().splitlines()[-1] if out.strip() else '')
    if code == 0 and isinstance(firmware, dict):
        result['firmware'] = firmware
    return result


def cmd_more_update_run(paths, args):
    """more-update-run apps|firmware: update Flatpak apps now (a notification says how it went),
    or install firmware in a terminal (fwupdmgr shows its progress and asks before restarting)."""
    if args not in (['apps'], ['firmware']):
        raise Failure('usage: more-update-run apps|firmware')
    if not which('arctic-update', paths.env):
        raise Failure('arctic-update isn’t installed.')
    argv = ['arctic-update', 'flatpak', '--notify'] if args == ['apps'] else ['arctic-update', 'firmware', 'install']
    subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     start_new_session=True)
    return dict(ok=True, started=args[0])


# ---- the laptop lid (arctic-display lid-closed, arctic-session lid) ------------------------------

LID_CHOICES = ('suspend', 'lock', 'screen-off')


def _has_lid(paths):
    return bool(paths.env.get('ARCTIC_FORCE_LID')) or any(Path('/proc/acpi/button/lid').glob('*/state'))


def cmd_lid(paths, _args):
    choice = 'suspend'
    for line in (read_text(paths.arctic / 'lid.conf') or '').splitlines():
        key, _, value = line.partition('=')
        if key.strip() == 'when_closed' and value.strip() in LID_CHOICES:
            choice = value.strip()
    return dict(ok=True, present=_has_lid(paths), whenClosed=choice)


def cmd_lid_set(paths, args):
    """lid-set suspend|lock|screen-off: what closing the lid does without another screen."""
    if len(args) != 1 or args[0] not in LID_CHOICES:
        raise Failure('usage: lid-set suspend|lock|screen-off')
    path = paths.arctic / 'lid.conf'
    if path.exists():
        backup(paths, path)
    atomic_write(path, '# Written by Arctic Settings (Power and lock). arctic-display and arctic-session lid read it.\n'
                       'when_closed={}\n'.format(args[0]))
    if which('arctic-session', paths.env):
        run(['arctic-session', 'lid', '--restart'], timeout=10)
    return cmd_lid(paths, [])


# ---- lighter effects and game mode (arctic-effects) -----------------------------------------------

def cmd_effects(paths, _args):
    data = _helper_json(['arctic-effects', 'status', '--json'], missing=dict(ok=True, helper=False))
    data.setdefault('helper', True)
    return data


def cmd_effects_set(paths, args):
    """effects-set lighter auto|on|off | game on|off."""
    if tuple(args) not in {('lighter', 'auto'), ('lighter', 'on'), ('lighter', 'off'), ('game', 'on'), ('game', 'off')}:
        raise Failure('usage: effects-set lighter auto|on|off | game on|off')
    _helper_json(['arctic-effects'] + list(args) + (['--quiet'] if args[0] == 'game' else []), timeout=30)
    return cmd_effects(paths, [])


COMMANDS = {
    'nightlight': cmd_nightlight, 'nightlight-set': cmd_nightlight_set, 'keep-awake': cmd_keep_awake,
    'autostart': cmd_autostart, 'autostart-set': cmd_autostart_set,
    'printers': cmd_printers, 'printer-default': cmd_printer_default, 'printer-cancel': cmd_printer_cancel,
    'datetime': cmd_datetime, 'datetime-set': cmd_datetime_set,
    'more-updates': cmd_more_updates, 'more-update-run': cmd_more_update_run,
    'lid': cmd_lid, 'lid-set': cmd_lid_set, 'effects': cmd_effects, 'effects-set': cmd_effects_set,
}
# Commands that read, change and write back a file of ours (they run one at a time).
WRITERS = {'nightlight-set', 'autostart-set', 'lid-set', 'effects-set'}
