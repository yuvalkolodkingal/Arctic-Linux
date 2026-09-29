#!/usr/bin/env python3
"""Battery details UPower has but Quickshell doesn't expose, for the battery menu.

    battery.py status      {"ok":true,"present":true,"path":"/org/freedesktop/UPower/devices/battery_BAT0",
                            "percentage_low":20,"percentage_critical":5,"percentage_action":2,
                            "critical_action":"suspend|hibernate|shut down|nothing",
                            "threshold_supported":true,"threshold_enabled":false,
                            "threshold_start":75,"threshold_end":80}
    battery.py limit on|off    UPower Device.EnableChargeThreshold (polkit may ask)

One JSON line, {"ok":false,"error":"…"} on failure. Talks to UPower and logind over the system
bus with python3-dbus. The percentages come from /etc/UPower/UPower.conf and its conf.d
drop-ins (last wins; for the warning copy only). UPower's critical action "Auto"/"Sleep"
means logind's Sleep(), which follows SleepOperation= in systemd's sleep.conf (default
"suspend-then-hibernate suspend hibernate"): the first one logind says it can do.
"""
import glob
import json
import os
import sys

UPOWER = 'org.freedesktop.UPower'
UPOWER_CONF = os.environ.get('ARCTIC_UPOWER_CONF', '/etc/UPower/UPower.conf')
SLEEP_CONF = os.environ.get('ARCTIC_SLEEP_CONF', '/etc/systemd/sleep.conf')
DEFAULTS = {'PercentageLow': 20, 'PercentageCritical': 5, 'PercentageAction': 2}
VERBS = {'suspend-then-hibernate': 'suspend', 'suspend': 'suspend', 'hybrid-sleep': 'suspend',
         'hibernate': 'hibernate'}


def read_conf(paths, section, keys):
    """The last value of each key in [section] over the files in order (drop-ins after)."""
    out = {}
    for path in paths:
        try:
            text = open(path, encoding='utf-8').read()
        except OSError:
            continue
        current = ''
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line[0] in '#;':
                continue
            if line.startswith('[') and line.endswith(']'):
                current = line[1:-1].strip()
                continue
            if current == section and '=' in line:
                key, value = (p.strip() for p in line.split('=', 1))
                if key in keys:
                    out[key] = value
    return out


def conf_chain(main):
    return [main] + sorted(glob.glob(main + '.d/*.conf'))


def percentages(paths):
    values = read_conf(paths, 'UPower', set(DEFAULTS))
    out = {}
    for key, default in DEFAULTS.items():
        try:
            out[key] = int(float(values.get(key, default)))
        except ValueError:
            out[key] = default
    return {'percentage_low': out['PercentageLow'], 'percentage_critical': out['PercentageCritical'],
            'percentage_action': out['PercentageAction']}


def action_verb(action, sleep_paths, can):
    """UPower's GetCriticalAction() → what the warning says Arctic will do. `can(name)` answers
    logind's Can<Name>() ('yes', 'no', 'challenge', …)."""
    a = str(action or '').lower()
    if a == 'poweroff':
        return 'shut down'
    if a == 'hibernate':
        return 'hibernate'
    if a in ('hybridsleep', 'suspend'):
        return 'suspend'
    if a == 'ignore':
        return 'nothing'
    # Auto / Sleep: logind's Sleep() picks the first operation it can do.
    ops = read_conf(sleep_paths, 'Sleep', {'SleepOperation'}).get('SleepOperation', 'suspend-then-hibernate suspend hibernate')
    names = {'suspend-then-hibernate': 'SuspendThenHibernate', 'suspend': 'Suspend', 'hibernate': 'Hibernate',
             'hybrid-sleep': 'HybridSleep'}
    for op in ops.split():
        if op in names and can(names[op]) == 'yes':
            return VERBS[op]
    return 'suspend'


def status(bus):
    import dbus
    upower = bus.get_object(UPOWER, '/org/freedesktop/UPower')
    props = dbus.Interface(upower, UPOWER)
    out = {'ok': True, 'present': False, 'path': ''}
    for path in props.EnumerateDevices():
        dev = bus.get_object(UPOWER, path)
        p = dev.GetAll(UPOWER + '.Device', dbus_interface='org.freedesktop.DBus.Properties')
        if int(p.get('Type', 0)) == 2 and bool(p.get('PowerSupply', False)):
            out.update(present=True, path=str(path),
                       threshold_supported=bool(p.get('ChargeThresholdSupported', False)),
                       threshold_enabled=bool(p.get('ChargeThresholdEnabled', False)),
                       threshold_start=int(p.get('ChargeStartThreshold', 0)),
                       threshold_end=int(p.get('ChargeEndThreshold', 0)))
            break
    out.update(percentages(conf_chain(UPOWER_CONF)))
    try:
        action = str(props.GetCriticalAction())
    except dbus.DBusException:
        action = 'PowerOff'

    def can(name):
        try:
            login = dbus.Interface(bus.get_object('org.freedesktop.login1', '/org/freedesktop/login1'),
                                   'org.freedesktop.login1.Manager')
            return str(getattr(login, 'Can' + name)())
        except dbus.DBusException:
            return 'no'
    out['critical_action'] = action_verb(action, conf_chain(SLEEP_CONF), can)
    return out


def limit(bus, on):
    import dbus
    path = status(bus).get('path')
    if not path:
        return {'ok': False, 'error': 'There is no battery to limit.'}
    dev = dbus.Interface(bus.get_object(UPOWER, path), UPOWER + '.Device')
    try:
        dev.EnableChargeThreshold(dbus.Boolean(on))
    except dbus.DBusException as e:
        if 'NotAuthorized' in e.get_dbus_name() or 'AccessDenied' in e.get_dbus_name():
            return {'ok': False, 'error': 'Arctic needs your permission to change the charge limit.'}
        return {'ok': False, 'error': 'This battery doesn’t take a charge limit.'}
    return {'ok': True, 'enabled': on}


def main(argv):
    if not argv or argv[0] not in ('status', 'limit') or (argv[0] == 'limit' and argv[1:] not in (['on'], ['off'])):
        print(json.dumps({'ok': False, 'error': 'usage: battery.py status | limit on|off'}))
        return 2
    try:
        import dbus
        bus = dbus.SystemBus()
        out = status(bus) if argv[0] == 'status' else limit(bus, argv[1] == 'on')
    except ImportError:
        out = {'ok': False, 'error': 'python3-dbus isn’t installed.'}
    except Exception as e:                   # no UPower, no system bus
        out = {'ok': False, 'error': 'UPower isn’t running (%s).' % e.__class__.__name__}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
