#!/usr/bin/env python3
"""Sound cards' ports and profiles for the sound menu's device page, from PipeWire.

    audio.py devices                     {"ok":true,"devices":[{"id":45,"name":"alsa_card.pci-0000_00_1f.3",
                                           "description":"Built-in Audio","bus":"pci",
                                           "profiles":[{"index":1,"name":"output:analog-stereo","description":"Analog Stereo Output",
                                                        "available":"yes","active":true}],
                                           "routes":[{"index":3,"devices":[7],"name":"analog-output-headphones",
                                                      "description":"Headphones","direction":"output","available":"yes",
                                                      "active":true,"device":7}]}]}
    audio.py profile DEVICE_ID INDEX     wpctl set-profile DEVICE_ID INDEX
    audio.py route DEVICE_ID ROUTE DEVICE
                                         pw-cli set-param DEVICE_ID Route '{ index: ROUTE, device: DEVICE, save: true }'

Reads `pw-dump` (pipewire-utils): the Audio/Device objects with their EnumProfile, Profile,
EnumRoute and Route params. A sink or source node names its card with the node property
`device.id` and its place on the card with `card.profile.device`, which is how the menu picks
the routes (ports) that belong to one output. One JSON line per call.
"""
import json
import subprocess
import sys


def run(args, timeout=10):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return 127, ''
    return p.returncode, p.stdout


def parse_dump(objects):
    """pw-dump's objects → the sound cards with their profiles and routes."""
    out = []
    for obj in objects if isinstance(objects, list) else []:
        if obj.get('type') != 'PipeWire:Interface:Device':
            continue
        info = obj.get('info') or {}
        props = info.get('props') or {}
        if props.get('media.class') != 'Audio/Device':
            continue
        params = info.get('params') or {}
        active_profile = {p.get('index') for p in params.get('Profile') or []}
        active_routes = {(r.get('index'), r.get('device')) for r in params.get('Route') or []}
        route_device = {r.get('index'): r.get('device') for r in params.get('Route') or []}
        profiles = [{'index': p.get('index'), 'name': p.get('name', ''), 'description': p.get('description') or p.get('name', ''),
                     'available': p.get('available', 'unknown'), 'active': p.get('index') in active_profile}
                    for p in params.get('EnumProfile') or [] if p.get('name') != 'off']
        routes = []
        for r in params.get('EnumRoute') or []:
            devices = r.get('devices') or []
            index = r.get('index')
            active_device = route_device.get(index)
            routes.append({'index': index, 'devices': devices, 'name': r.get('name', ''),
                           'description': r.get('description') or r.get('name', ''),
                           'direction': str(r.get('direction', '')).lower(), 'available': r.get('available', 'unknown'),
                           'active': (index, active_device) in active_routes,
                           'device': active_device if active_device is not None else (devices[0] if devices else None)})
        out.append({'id': obj.get('id'), 'name': props.get('device.name', ''),
                    'description': props.get('device.description') or props.get('device.nick') or props.get('device.name', ''),
                    'bus': props.get('device.bus', ''), 'profiles': profiles, 'routes': routes})
    return out


def route_command(device_id, route, device):
    return ['pw-cli', 'set-param', str(int(device_id)), 'Route',
            '{ index: %d, device: %d, save: true }' % (int(route), int(device))]


def profile_command(device_id, index):
    return ['wpctl', 'set-profile', str(int(device_id)), str(int(index))]


def main(argv):
    try:
        if argv[:1] == ['devices']:
            code, text = run(['pw-dump'])
            if code != 0:
                out = {'ok': False, 'error': 'PipeWire isn’t running (pw-dump failed).'}
            else:
                out = {'ok': True, 'devices': parse_dump(json.loads(text or '[]'))}
        elif argv[:1] == ['profile'] and len(argv) == 3:
            code, _ = run(profile_command(argv[1], argv[2]))
            out = {'ok': code == 0} if code == 0 else {'ok': False, 'error': 'Couldn’t switch the profile.'}
        elif argv[:1] == ['route'] and len(argv) == 4:
            code, _ = run(route_command(argv[1], argv[2], argv[3]))
            out = {'ok': code == 0} if code == 0 else {'ok': False, 'error': 'Couldn’t switch the output.'}
        else:
            out = {'ok': False, 'error': 'usage: audio.py devices | profile DEVICE INDEX | route DEVICE ROUTE DEVICE'}
    except ValueError:
        out = {'ok': False, 'error': 'Those aren’t PipeWire numbers.'}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
