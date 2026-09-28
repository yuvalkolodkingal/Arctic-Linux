#!/usr/bin/env python3
"""Display brightness for Quick Settings and the display page: the laptop panel through
brightnessctl, external monitors through DDC/CI (ddcutil, when installed).

    brightness.py list                  {"ok":true,"displays":[
                                          {"output":"eDP-1","kind":"backlight","device":"intel_backlight",
                                           "label":"Built-in display","percent":60},
                                          {"output":"DP-1","kind":"ddc","bus":5,"label":"DELL U2723QE","percent":40}]}
    brightness.py set OUTPUT PERCENT    {"ok":true,"output":"DP-1","percent":50}

One JSON line per call. `ddcutil detect` is slow, so what it finds is cached in
~/.cache/arctic/ddc.json for 10 minutes; a monitor that fails three times in a row is left
alone for 30 s (Noctalia's cool-down). Monitors that don't answer are left out.
"""
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import time

CACHE = os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'arctic', 'ddc.json')
DETECT_TTL = 600
COOLDOWN = 30
DRM = os.environ.get('ARCTIC_DRM_DIR', '/sys/class/drm')


def run(args, timeout=10):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, ''
    return p.returncode, p.stdout


# ---- parsing (pure) -----------------------------------------------------------------------------
def parse_brightnessctl(text):
    """`brightnessctl -m -c backlight`: device,class,current,percent%,max per line."""
    out = []
    for line in (text or '').splitlines():
        f = line.strip().split(',')
        if len(f) >= 5 and f[1] == 'backlight':
            try:
                out.append({'device': f[0], 'percent': int(f[3].rstrip('%'))})
            except ValueError:
                continue
    return out


def parse_detect(text):
    """`ddcutil detect --terse` → [{bus, output, label}] for displays with a DRM connector."""
    out, cur = [], None
    for raw in (text or '').splitlines():
        line = raw.strip()
        if re.match(r'^(Invalid )?[Dd]isplay\b', line):
            cur = {'valid': not line.startswith('Invalid')}
            out.append(cur)
            continue
        if cur is None or ':' not in line:
            continue
        key, value = (p.strip() for p in line.split(':', 1))
        if key == 'I2C bus':
            m = re.search(r'i2c-(\d+)', value)
            if m:
                cur['bus'] = int(m.group(1))
        elif key == 'DRM connector':
            cur['output'] = re.sub(r'^card\d+-', '', value)
        elif key == 'Monitor':
            parts = value.split(':')
            cur['label'] = (parts[1] if len(parts) > 1 and parts[1] else parts[0]).strip()
    return [{'bus': d['bus'], 'output': d.get('output', 'bus %d' % d['bus']), 'label': d.get('label') or 'Monitor'}
            for d in out if d.get('valid') and 'bus' in d]


def parse_vcp(text):
    """`ddcutil getvcp 10 --terse` → percent, e.g. "VCP 10 C 50 100" → 50."""
    m = re.search(r'VCP\s+10\s+C\s+(\d+)\s+(\d+)', text or '')
    if not m:
        return None
    cur, top = int(m.group(1)), int(m.group(2))
    return round(cur * 100 / top) if top > 0 else None


def internal_output():
    """The laptop panel's connector (eDP-1, LVDS-1, DSI-1) from sysfs, else ''."""
    for path in sorted(glob.glob(os.path.join(DRM, 'card*-*'))):
        name = re.sub(r'^card\d+-', '', os.path.basename(path))
        if re.match(r'^(eDP|LVDS|DSI)-', name):
            return name
    return ''


# ---- DDC cache ----------------------------------------------------------------------------------
def load_cache():
    try:
        with open(CACHE, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_cache(data):
    try:
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        tmp = CACHE + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        os.replace(tmp, CACHE)
    except OSError:
        pass


def cooling(cache, bus, now):
    f = cache.get('failures', {}).get(str(bus), {})
    return f.get('count', 0) >= 3 and now - f.get('last', 0) < COOLDOWN


def note(cache, bus, ok, now):
    failures = cache.setdefault('failures', {})
    if ok:
        failures.pop(str(bus), None)
    else:
        f = failures.setdefault(str(bus), {'count': 0, 'last': 0})
        f['count'] = f['count'] + 1 if now - f['last'] < COOLDOWN * 4 else 1
        f['last'] = now


def ddc_displays(cache, now):
    if not shutil.which('ddcutil'):
        return []
    if now - cache.get('detected_at', 0) > DETECT_TTL:
        code, text = run(['ddcutil', 'detect', '--terse'], timeout=30)
        cache['displays'] = parse_detect(text) if code == 0 else []
        cache['detected_at'] = now
    out = []
    for d in cache.get('displays', []):
        if cooling(cache, d['bus'], now):
            continue
        code, text = run(['ddcutil', '--bus', str(d['bus']), 'getvcp', '10', '--terse'])
        percent = parse_vcp(text) if code == 0 else None
        note(cache, d['bus'], percent is not None, now)
        if percent is not None:
            out.append(dict(d, kind='ddc', percent=percent))
    return out


def list_displays():
    displays = []
    code, text = run(['brightnessctl', '-m', '-c', 'backlight'])
    if code == 0:
        for b in parse_brightnessctl(text)[:1]:
            displays.append({'output': internal_output() or 'internal', 'kind': 'backlight', 'device': b['device'],
                             'label': 'Built-in display', 'percent': b['percent']})
    cache = load_cache()
    displays += ddc_displays(cache, time.time())
    save_cache(cache)
    return displays


def set_brightness(output, percent):
    percent = max(1, min(100, int(percent)))       # never fully dark (arctic-osd's 1 % floor)
    for d in list_displays() if output else []:
        if d['output'] != output:
            continue
        if d['kind'] == 'backlight':
            code, _ = run(['brightnessctl', '-q', '-d', d['device'], 'set', '%d%%' % percent])
        else:
            code, _ = run(['ddcutil', '--bus', str(d['bus']), 'setvcp', '10', str(percent)])
        if code != 0:
            return {'ok': False, 'error': 'Couldn’t change the brightness of %s.' % d['label']}
        return {'ok': True, 'output': output, 'percent': percent}
    return {'ok': False, 'error': 'That display isn’t there any more.'}


def main(argv):
    if argv[:1] == ['list']:
        out = {'ok': True, 'displays': list_displays()}
    elif argv[:1] == ['set'] and len(argv) == 3 and argv[2].isdigit():
        out = set_brightness(argv[1], int(argv[2]))
    else:
        out = {'ok': False, 'error': 'usage: brightness.py list | set OUTPUT PERCENT'}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
