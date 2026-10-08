"""Opt-in network tools: read-only detection and explicit user-requested actions.

Nothing here changes routes, writes Tor configuration, creates keys, selects an
exit node or signs in automatically. SOCKS availability is not proof of Tor.
"""
import json
import re
import shutil
import socket
import subprocess

TOR_BROWSER = 'org.torproject.torbrowser-launcher'
TOOLS = {'tor': ['tor'], 'tailscale': ['tailscale'], 'openvpn': ['NetworkManager-openvpn']}
UNITS = {'tor': 'tor.service', 'tailscale': 'tailscaled.service'}


def run(argv, timeout=8):
    try:
        p = subprocess.run(argv, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, '', str(exc)


def service(unit):
    code, text, _ = run(['systemctl', 'show', unit, '--property=LoadState,ActiveState,SubState,InvocationID'])
    data = dict(line.split('=', 1) for line in text.splitlines() if '=' in line) if code == 0 else {}
    return dict(unit=unit, installed=data.get('LoadState') == 'loaded',
                running=data.get('ActiveState') == 'active', state=data.get('ActiveState', 'unknown'),
                invocation=data.get('InvocationID', ''))


def socks(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.15) as conn:
            conn.settimeout(0.15)
            conn.sendall(b'\x05\x01\x00')
            return conn.recv(2) == b'\x05\x00'
    except OSError:
        return False


def tor_status():
    default = service('tor.service')
    code, text, _ = run(['systemctl', 'list-units', '--type=service', '--state=running', '--no-legend', '--plain', 'tor*.service'])
    units = [line.split()[0] for line in text.splitlines() if line.split() and re.fullmatch(r'tor(?:@[A-Za-z0-9_.-]+)?\.service', line.split()[0])] if code == 0 else []
    process_present = run(['pgrep', '-x', 'tor'])[0] == 0
    endpoints = [dict(host='127.0.0.1', port=p, protocol='SOCKS5', tor_verified=False) for p in (9050, 9150) if socks(p)]
    bootstrap = None
    if default['running'] and re.fullmatch(r'[0-9a-f]{32}', default['invocation']):
        code, log, _ = run(['journalctl', '--no-pager', '-o', 'cat', '-n', '100',
                            '_SYSTEMD_INVOCATION_ID=' + default['invocation']])
        if code == 0:
            values = re.findall(r'Bootstrapped (\d{1,3})%', log)
            if values and 0 <= int(values[-1]) <= 100:
                bootstrap = int(values[-1])
    browser = []
    if shutil.which('flatpak'):
        for scope in ('user', 'system'):
            if run(['flatpak', 'info', '--'+scope, '--show-ref', TOR_BROWSER])[0] == 0:
                browser.append(scope)
    return dict(installed=bool(shutil.which('tor')), service=default, running_units=units,
                endpoints=endpoints, bootstrap=bootstrap, browser=browser, process_present=process_present,
                can_start=default['installed'] and not default['running'] and not units and not endpoints and not process_present)


def status():
    ts = service('tailscaled.service')
    ts['present'] = bool(shutil.which('tailscale'))
    ts['connection'] = 'unknown'
    if ts['present']:
        code, text, _ = run(['tailscale', 'status', '--json'])
        if code == 0:
            try:
                data = json.loads(text)
                ts['connection'] = str(data.get('BackendState', 'unknown'))
                ts['tailnet'] = str((data.get('CurrentTailnet') or {}).get('Name', ''))
            except (ValueError, AttributeError):
                pass
    return dict(ok=True, tor=tor_status(), tailscale=ts,
                openvpn=run(['rpm', '-q', 'NetworkManager-openvpn'])[0] == 0)


def action(args):
    # Return a fixed argv plan to be shown in a terminal. No shell interpolation.
    if len(args) != 2:
        raise ValueError('Choose a network tool and an action.')
    tool, verb = args
    if tool not in TOOLS:
        raise ValueError('Unknown optional network tool.')
    if verb == 'install':
        return ['pkexec', '/usr/bin/dnf5', 'install', *TOOLS[tool]]
    if tool in UNITS and verb in ('start', 'stop'):
        if tool == 'tor' and verb == 'start' and not tor_status()['can_start']:
            raise ValueError('Tor or a SOCKS endpoint already exists, or the default unit is unavailable. Review the detected instance instead of starting another.')
        return ['systemctl', verb, UNITS[tool]]
    if tool == 'tailscale' and verb in ('login', 'disconnect'):
        return ['pkexec', '/usr/bin/tailscale', 'up' if verb == 'login' else 'down']
    raise ValueError('Unsupported optional network action.')
