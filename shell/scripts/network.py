#!/usr/bin/env python3
"""NetworkManager for the shell's network menu, through nmcli (no D-Bus bindings needed).

    network.py watch                 long-running (NetworkService.qml); commands on stdin:
                                     {"op":"scan","on":true|false}  {"op":"rescan"}
    network.py status                one "state" object
    network.py scan [--rescan]       {"ok":true,"networks":[…]}
    network.py saved                 {"ok":true,"saved":[…],"vpn":[…]}
    network.py connect --uuid U [--ask]
    network.py connect --ssid S --security open|owe|wep|wpa-psk|sae [--hidden] [--ask]
    network.py enterprise --ssid S --eap peap|ttls --phase2 mschapv2|pap|gtc --identity ID
                          [--anonymous-identity A] [--domain D] (--system-ca|--no-ca) [--hidden] --ask
    network.py disconnect --uuid U
    network.py forget (--uuid U… | --ssid S)
    network.py autoconnect --uuid U on|off
    network.py radio wifi on|off
    network.py airplane on|off       every radio off (rfkill), then back to how they were
    network.py share --uuid U [--reveal]   a QR code (SVG) a phone camera joins with
    network.py vpn-up --uuid U [--ask]  |  vpn-down --uuid U
    network.py vpn-import --file PATH [--type openvpn|wireguard]
    network.py ca-set --uuid U --file PATH
                                     a company (802.1X) network checks its server against this
                                     certificate (copied to ~/.cert/arctic/, where NetworkManager
                                     may read it) instead of the system's
    network.py tailscale status|up|down|operator  |  tailscale exit-node IP|none
                                     Tailscale, when it is installed: `up` hands back the sign-in
                                     page when signed out; `operator` lets this user switch it
                                     (pkexec tailscale set --operator=USER, polkit asks)
    network.py hotspot on [--ssid NAME] | off
                                     this computer as a Wi-Fi access point ("Arctic hotspot"),
                                     sharing its connection; the share card shows its password

One-shot commands print one JSON line: {"ok":true,…} or {"ok":false,"error":"<sentence>",
"code":"<code>"} and exit 0/1. `watch` prints one object per line with a "type": "state"
whenever NetworkManager reports a change (nmcli monitor, 250 ms debounce) and "networks" every
8 s while a menu asked for a scan, and "needs_secrets" when NetworkManager gave up on a saved
Wi-Fi network because its password no longer works (nobody else answers NetworkManager's
password requests in the shell session; the menu asks instead).

Secrets (--ask): the password comes on stdin as one JSON line {"secret":"…"} and reaches nmcli
only through a pipe (`passwd-file /dev/fd/N`): never on a command line, in the environment, in
a file or in a log. Joining a new network adds a profile without a secret first and deletes it
again if the activation fails; a saved profile is kept.

ARCTIC_NETWORK_FIXTURE=<file.json> answers watch/status/scan/saved from the file and lets
every change succeed without running anything (screenshots and tests).
"""
import json
import os
import pwd
import re
import secrets
import selectors
import socket
import subprocess
import sys
import time

FIXTURE = os.environ.get('ARCTIC_NETWORK_FIXTURE', '')
SECRET_MAX = 4096
SCAN_INTERVAL = 8.0
DEBOUNCE = 0.25
TYPES = {'802-11-wireless': 'wifi', 'wifi': 'wifi', '802-3-ethernet': 'ethernet', 'ethernet': 'ethernet',
         'vpn': 'vpn', 'wireguard': 'wireguard'}
HOTSPOT = 'Arctic hotspot'               # the hotspot's profile name (kept apart from Wi-Fi networks)
PASSWORD_CHARS = 'abcdefghijkmnpqrstuvwxyz23456789'      # no l, o, 0 or 1 to misread


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def emit(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + '\n')
    sys.stdout.flush()


# ---- nmcli ------------------------------------------------------------------------------------
def split_terse(line):
    """Split one line of `nmcli -t` output: fields separated by ':', with '\\:' and '\\\\' escapes."""
    out, cur, i = [], [], 0
    while i < len(line):
        c = line[i]
        if c == '\\' and i + 1 < len(line):
            cur.append(line[i + 1])
            i += 2
            continue
        if c == ':':
            out.append(''.join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append(''.join(cur))
    return out


def nmcli(*args, pass_fds=(), timeout=60):
    """Run nmcli; returns (exit status, stdout, stderr). Missing nmcli is exit 127."""
    try:
        p = subprocess.run(['nmcli', *args], capture_output=True, text=True, pass_fds=pass_fds,
                           timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        return 127, '', 'nmcli is not installed'
    except subprocess.TimeoutExpired:
        return 3, '', 'timed out'
    return p.returncode, p.stdout, p.stderr


def rows(*args):
    code, out, _ = nmcli('-t', *args)
    if code != 0:
        return None
    return [split_terse(l) for l in out.splitlines() if l.strip()]


# ---- parsing (pure) ---------------------------------------------------------------------------
def security_of(sec):
    """nmcli's SECURITY column → open, owe, wep, enterprise, sae or wpa-psk."""
    s = (sec or '').strip()
    if s in ('', '--'):
        return 'open'
    if 'OWE' in s and 'WPA' not in s:
        return 'owe'
    if 'WEP' in s:
        return 'wep'
    if '802.1X' in s:
        return 'enterprise'
    if 'WPA3' in s and 'WPA2' not in s and 'WPA1' not in s:
        return 'sae'
    return 'wpa-psk'


def band_of(freq):
    m = re.match(r'\s*(\d+)', freq or '')
    if not m:
        return ''
    mhz = int(m.group(1))
    return '6 GHz' if mhz >= 5925 else '5 GHz' if mhz >= 4900 else '2.4 GHz'


def parse_wifi_list(text, saved=None):
    """`nmcli -t -f IN-USE,SSID,SIGNAL,FREQ,SECURITY device wifi list` → one entry per SSID
    (best signal kept, hidden networks left out), sorted connected → saved → signal → name.
    `saved` maps SSID → the most recently used profile's uuid."""
    saved = saved or {}
    best = {}
    for line in (text or '').splitlines():
        f = split_terse(line)
        if len(f) < 5 or f[1].strip() in ('', '--'):
            continue
        try:
            signal = int(f[2])
        except ValueError:
            signal = 0
        n = {'ssid': f[1], 'signal': max(0, min(100, signal)), 'band': band_of(f[3]),
             'security': security_of(f[4]), 'in_use': f[0].strip() == '*'}
        old = best.get(n['ssid'])
        if old:
            n['in_use'] = n['in_use'] or old['in_use']
            if old['signal'] >= n['signal']:
                n.update(signal=old['signal'], band=old['band'], security=old['security'])
        best[n['ssid']] = n
    out = []
    for n in best.values():
        uuid = saved.get(n['ssid'])
        n['saved'] = uuid is not None
        n['uuid'] = uuid
        n['hidden'] = False
        out.append(n)
    out.sort(key=lambda n: (not n['in_use'], not n['saved'], -n['signal'], n['ssid'].lower()))
    return out


def device_state(text):
    s = (text or '').split(' ')[0]
    if s.startswith('connected'):
        return 'connected'
    if s.startswith('connecting'):
        return 'connecting'
    if s in ('unavailable', 'unmanaged'):
        return s
    return 'disconnected'


def build_state(devices, active, profiles, radio):
    """The watch "state" object from `device status`, `connection show --active`,
    `connection show` and `radio` rows (already split)."""
    wifi = None
    wired = []
    for f in devices or []:
        if len(f) < 4:
            continue
        dev, kind, st, con = f[0], f[1], f[2], f[3]
        if kind == 'wifi' and wifi is None:
            wifi = {'device': dev, 'state': device_state(st)}
        elif kind == 'ethernet':
            wired.append({'device': dev, 'state': device_state(st), 'connection': '' if con == '--' else con})
    hw = en = True
    if radio and len(radio[0]) >= 2:
        hw, en = radio[0][0] == 'enabled', radio[0][1] == 'enabled'
    if wifi is not None:
        wifi.update(hardware=hw, enabled=en)
    act = []
    active_uuids = set()
    for f in active or []:
        if len(f) < 5:
            continue
        name, uuid, kind, dev, st = f[:5]
        active_uuids.add(uuid)
        act.append({'uuid': uuid, 'name': name, 'type': TYPES.get(kind, kind), 'device': '' if dev == '--' else dev,
                    'state': st or 'activated'})
    vpn = []
    for f in profiles or []:
        if len(f) < 4:
            continue
        name, uuid, kind, ts = f[:4]
        if TYPES.get(kind) not in ('vpn', 'wireguard'):
            continue
        try:
            last = int(ts)
        except ValueError:
            last = 0
        vpn.append({'uuid': uuid, 'name': name, 'kind': TYPES[kind], 'active': uuid in active_uuids, 'last_used': last})
    vpn.sort(key=lambda v: v['name'].lower())
    return {'type': 'state', 'nm_running': True, 'wifi': wifi, 'wired': wired, 'active': act, 'vpn': vpn}


def mark_hotspot(state, hotspot, ap_capable):
    """Add the hotspot to a state object: {"active","uuid","ssid"}; its active connection gets the
    type "hotspot", so it isn't taken for the Wi-Fi network the computer is on."""
    if state.get('wifi') is not None:
        state['wifi']['ap_capable'] = bool(ap_capable)
    uuid = hotspot['uuid'] if hotspot else None
    active = False
    for a in state.get('active', []):
        if uuid and a['uuid'] == uuid:
            a['type'] = 'hotspot'
            active = True
    state['hotspot'] = {'active': active, 'uuid': uuid, 'ssid': hotspot['ssid'] if hotspot else None}
    return state


def hotspot_password(length=12):
    return ''.join(secrets.choice(PASSWORD_CHARS) for _ in range(length))


def hotspot_ssid(host=None):
    """The hotspot's name: the computer's name, as phones list it ("arctic-laptop hotspot")."""
    name = re.sub(r'[^\w .-]', '', (host if host is not None else socket.gethostname()).split('.')[0]).strip()
    return ('%s hotspot' % name[:24]) if name and name != 'localhost' else 'Arctic hotspot'


NM_DEVICE_FAILED = 120
NM_REASON_NO_SECRETS = 7


def parse_state_changed(line):
    """A `gdbus monitor --system --dest org.freedesktop.NetworkManager` line announcing a device
    state change → (device path, new state, old state, reason), else None."""
    m = re.match(r'^(/\S+): org\.freedesktop\.NetworkManager\.Device\.StateChanged '
                 r'\(uint32 (\d+), uint32 (\d+), uint32 (\d+)\)', (line or '').strip())
    return (m.group(1), int(m.group(2)), int(m.group(3)), int(m.group(4))) if m else None


def error_for(code, stderr, name):
    """nmcli's exit status and message → (code, sentence) for the menu."""
    msg = (stderr or '').strip()
    low = msg.lower()
    quoted = '“%s”' % name if name else 'The network'
    if 'not authorized' in low or 'insufficient privileges' in low or 'not allowed' in low:
        return 'denied', 'Arctic needs your permission to change this network.'
    if code == 8 or 'networkmanager is not running' in low:
        return 'nm_down', 'NetworkManager isn’t running, so Wi-Fi can’t be changed.'
    if code == 3 or 'timed out' in low or 'timeout' in low:
        return 'timeout', '%s didn’t answer. Move closer to the router and try again.' % quoted
    if code == 10 or 'no network with ssid' in low:
        return 'not_found', '%s is out of range now.' % quoted
    if 'secrets were required' in low or 'no-secrets' in low or '802.1x supplicant' in low or 'reason 7' in low \
            or 'reason 8' in low or 'wrong password' in low:
        return 'auth', 'That password didn’t work for %s. Check it and try again.' % quoted
    first = next((l for l in msg.splitlines() if l.strip()), '')
    first = re.sub(r'^Error:\s*', '', first).strip()[:100]
    sentence = 'Couldn’t connect to %s.' % quoted if name else 'That didn’t work.'
    return 'failed', (sentence + ' ' + first).strip()


def read_secret(stream):
    """One JSON line {"secret": "…"} from stdin; refused when empty, too long or multi-line."""
    raw = stream.readline(SECRET_MAX + 64)
    try:
        secret = json.loads(raw).get('secret', '')
    except (ValueError, AttributeError):
        raise Failure('bad_secret', 'The password didn’t arrive. Try again.')
    if not isinstance(secret, str) or not secret:
        raise Failure('bad_secret', 'Type the password first.')
    if len(secret.encode()) > SECRET_MAX or '\n' in secret or '\r' in secret or '\0' in secret:
        raise Failure('bad_secret', 'That password can’t be used: it is too long or has a line break.')
    return secret


def secret_setting(security):
    return {'wep': '802-11-wireless-security.wep-key0', 'vpn': 'vpn.secrets.password',
            'enterprise': '802-1x.password'}.get(security, '802-11-wireless-security.psk')


def enterprise_settings(eap, phase2, identity, anonymous='', domain='', system_ca=True):
    """nmcli settings for a company (802.1X) network with a username and password: PEAP or TTLS,
    checked against the system's certificates unless told not to. EAP-TLS (a certificate of your
    own) is set up in the connection editor."""
    if eap not in ('peap', 'ttls') or phase2 not in ('mschapv2', 'pap', 'gtc'):
        raise Failure('needs_certificate', 'This sign-in method needs the connection editor.')
    if not identity or '\n' in identity:
        raise Failure('usage', 'Type your username first.')
    out = ['wifi-sec.key-mgmt', 'wpa-eap', '802-1x.eap', eap, '802-1x.phase2-auth', phase2, '802-1x.identity', identity]
    if anonymous:
        out += ['802-1x.anonymous-identity', anonymous]
    if domain:
        out += ['802-1x.domain-suffix-match', domain]
    out += ['802-1x.system-ca-certs', 'yes' if system_ca else 'no']
    return out


def wep_key_type(secret):
    """WEP keys of 5/13 characters or 10/26 hex digits are keys; anything else a passphrase."""
    if len(secret) in (5, 13) or (len(secret) in (10, 26) and re.fullmatch(r'[0-9A-Fa-f]+', secret)):
        return 'key'
    return 'passphrase'


def with_secret(setting, secret, run):
    """Call run(extra_args, pass_fds) with `passwd-file /dev/fd/N` reading one setting line."""
    r, w = os.pipe()
    try:
        os.write(w, ('%s:%s\n' % (setting, secret)).encode())
        os.close(w)
        w = -1
        return run(['passwd-file', '/dev/fd/%d' % r], (r,))
    finally:
        if w >= 0:
            os.close(w)
        os.close(r)


# ---- reading NetworkManager -------------------------------------------------------------------
class Reader:
    def __init__(self):
        self.ssids = {}                  # profile uuid → SSID (profiles rarely change their SSID)
        self.ap = {}                     # Wi-Fi device → can it be an access point

    def profiles(self):
        return rows('-f', 'NAME,UUID,TYPE,TIMESTAMP,AUTOCONNECT', 'connection', 'show') or []

    def ap_capable(self, device):
        if device not in self.ap:
            code, text, _ = nmcli('-g', 'WIFI-PROPERTIES.AP', 'device', 'show', device)
            self.ap[device] = code == 0 and text.strip() == 'yes'
        return self.ap[device]

    def wifi_profiles(self, profiles=None, hotspot=False):
        """Saved Wi-Fi networks; with hotspot=True, the hotspot's profile instead."""
        out = []
        for f in profiles if profiles is not None else self.profiles():
            if len(f) >= 4 and TYPES.get(f[2]) == 'wifi' and (f[0] == HOTSPOT) == hotspot:
                uuid = f[1]
                if uuid not in self.ssids:
                    code, text, _ = nmcli('-g', '802-11-wireless.ssid', 'connection', 'show', 'uuid', uuid)
                    self.ssids[uuid] = split_terse(text.strip())[0] if code == 0 else f[0]
                try:
                    last = int(f[3])
                except ValueError:
                    last = 0
                out.append({'uuid': uuid, 'name': f[0], 'ssid': self.ssids[uuid], 'last_used': last,
                            'autoconnect': len(f) < 5 or f[4] != 'no'})
        return out

    def saved_map(self, profiles=None):
        best = {}
        for p in sorted(self.wifi_profiles(profiles), key=lambda p: p['last_used']):
            best[p['ssid']] = p['uuid']
        return best

    def state(self):
        devices = rows('-f', 'DEVICE,TYPE,STATE,CONNECTION', 'device', 'status')
        if devices is None:
            return {'type': 'state', 'nm_running': False, 'wifi': None, 'wired': [], 'active': [], 'vpn': []}
        active = rows('-f', 'NAME,UUID,TYPE,DEVICE,STATE', 'connection', 'show', '--active')
        profiles = self.profiles()
        radio = rows('-f', 'WIFI-HW,WIFI', 'radio')
        state = build_state(devices, active, profiles, radio)
        known = {p[1] for p in profiles if len(p) > 1}
        self.ssids = {u: s for u, s in self.ssids.items() if u in known}
        state['saved'] = [{'uuid': p['uuid'], 'ssid': p['ssid'], 'autoconnect': p['autoconnect']}
                          for p in self.wifi_profiles(profiles)]
        state['airplane'] = airplane_on(rfkill_state())
        hotspot = next(iter(self.wifi_profiles(profiles, hotspot=True)), None)
        return mark_hotspot(state, hotspot, state['wifi'] is not None and self.ap_capable(state['wifi']['device']))

    def networks(self, rescan=False):
        if rescan:
            nmcli('device', 'wifi', 'rescan')        # NetworkManager may refuse (rate limit): fine
        code, text, _ = nmcli('-t', '-f', 'IN-USE,SSID,SIGNAL,FREQ,SECURITY', 'device', 'wifi', 'list', '--rescan', 'no')
        return parse_wifi_list(text if code == 0 else '', self.saved_map())


# ---- airplane mode (rfkill) -----------------------------------------------------------------------
AIRPLANE_TYPES = ('wlan', 'bluetooth', 'wwan')
STATE_DIR = os.path.join(os.environ.get('XDG_STATE_HOME') or os.path.expanduser('~/.local/state'), 'arctic')


def parse_rfkill(text):
    """`rfkill --json` → {type: soft-blocked for every device of that type} for the radio types."""
    try:
        data = json.loads(text or '{}')
    except ValueError:
        return {}
    devices = next((v for v in data.values() if isinstance(v, list)), []) if isinstance(data, dict) else []
    out = {}
    for d in devices:
        kind = d.get('type')
        if kind in AIRPLANE_TYPES:
            out[kind] = out.get(kind, True) and d.get('soft') == 'blocked'
    return out


def rfkill_state():
    try:
        p = subprocess.run(['rfkill', '--json'], capture_output=True, text=True, timeout=5, stdin=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {}
    return parse_rfkill(p.stdout) if p.returncode == 0 else {}


def airplane_on(state):
    """Airplane mode: every radio there is is soft-blocked (and there is at least one)."""
    return bool(state) and all(state.values())


def cmd_airplane(on):
    if FIXTURE:
        return {'ok': True, 'airplane': on}
    saved = os.path.join(STATE_DIR, 'airplane.json')
    state = rfkill_state()
    if on:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(saved, 'w', encoding='utf-8') as f:
            json.dump({k: not blocked for k, blocked in state.items()}, f)       # which ones were on
        todo = [('block', k) for k in state]
    else:
        try:
            with open(saved, encoding='utf-8') as f:
                were_on = json.load(f)
        except (OSError, ValueError):
            were_on = {k: True for k in state}
        todo = [('unblock', k) for k, was in were_on.items() if was and k in AIRPLANE_TYPES]
    failed = False
    for verb, kind in todo:
        try:
            failed |= subprocess.run(['rfkill', verb, kind], capture_output=True, timeout=5,
                                     stdin=subprocess.DEVNULL).returncode != 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            failed = True
    if failed or not todo:
        # No rfkill access: NetworkManager's radios instead (the shell turns Bluetooth off itself).
        simple('radio', 'all', 'off' if on else 'on')
        return {'ok': True, 'airplane': on, 'fallback': True}
    return {'ok': True, 'airplane': on}


# ---- sharing a network as a QR code ----------------------------------------------------------------
def qr_escape(text):
    return re.sub(r'([\\;,:"])', r'\\\1', text)


def qr_payload(ssid, key_mgmt, secret, hidden=False):
    """The WIFI: text phone cameras understand. Company (802.1X) networks can't be shared."""
    if key_mgmt == 'wpa-eap':
        raise Failure('enterprise', 'Company networks can’t be shared this way: each person signs in.')
    kind = 'WEP' if key_mgmt == 'none' and secret else 'WPA' if key_mgmt in ('wpa-psk', 'sae') else 'nopass'
    out = 'WIFI:T:%s;S:%s;' % (kind, qr_escape(ssid))
    if kind != 'nopass':
        out += 'P:%s;' % qr_escape(secret)
    if hidden:
        out += 'H:true;'
    return out + ';'


def cmd_share(args):
    if FIXTURE:
        data = load_fixture().get('share', {'ssid': 'Fjord', 'key_mgmt': 'wpa-psk', 'psk': 'fixture-password'})
        ssid, mgmt, secret, hidden = data['ssid'], data['key_mgmt'], data['psk'], False
    else:
        def get(field, secrets=False):
            code, text, err = nmcli(*(['-s'] if secrets else []), '-g', field, 'connection', 'show', 'uuid', args.uuid)
            if code != 0:
                raise Failure(*error_for(code, err, ''))
            return split_terse(text.rstrip('\n'))[0] if text.strip() else ''
        ssid, mgmt = get('802-11-wireless.ssid'), get('802-11-wireless-security.key-mgmt')
        hidden = get('802-11-wireless.hidden') == 'yes'
        secret = get('802-11-wireless-security.wep-key0' if mgmt == 'none' else '802-11-wireless-security.psk', True) \
            if mgmt else ''
        if mgmt in ('wpa-psk', 'sae') and not secret:
            raise Failure('denied', 'Arctic couldn’t read the password of “%s” (it may be kept by another app).' % ssid)
    payload = qr_payload(ssid, mgmt, secret, hidden)
    try:
        p = subprocess.run(['qrencode', '-t', 'SVG', '-m', '2', '-l', 'M', '-o', '-'], input=payload,
                           capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise Failure('failed', 'Install qrencode to share networks as a QR code.')
    if p.returncode != 0 or '<svg' not in p.stdout:
        raise Failure('failed', 'Couldn’t draw the QR code.')
    out = {'ok': True, 'ssid': ssid, 'svg': p.stdout[p.stdout.index('<svg'):]}
    if args.reveal:
        out['password'] = secret
    return out


def load_fixture():
    with open(FIXTURE, encoding='utf-8') as f:
        return json.load(f)


# ---- commands -----------------------------------------------------------------------------------
def wifi_device():
    for f in rows('-f', 'DEVICE,TYPE', 'device', 'status') or []:
        if len(f) >= 2 and f[1] == 'wifi':
            return f[0]
    return ''


def activate(uuid, name, setting=None, secret=None, wait='40'):
    def run(extra, fds):
        return nmcli('--wait', wait, 'connection', 'up', 'uuid', uuid, *extra, pass_fds=fds, timeout=int(wait) + 15)
    code, _, err = with_secret(setting, secret, run) if secret is not None else run([], ())
    if code != 0:
        raise Failure(*error_for(code, err, name))


def cmd_connect(args, stdin):
    secret = read_secret(stdin) if args.ask else None
    if args.uuid:
        if FIXTURE:
            return {'ok': True, 'uuid': args.uuid}
        activate(args.uuid, args.name or '', secret_setting(args.security or 'wpa-psk'), secret)
        return {'ok': True, 'uuid': args.uuid}
    ssid, security = args.ssid, args.security or 'open'
    if not ssid:
        raise Failure('usage', 'Type the network’s name first.')
    if security == 'enterprise':
        raise Failure('needs_certificate', '“%s” needs a company login. Set it up in Edit connections.' % ssid)
    if security not in ('open', 'owe') and secret is None:
        raise Failure('auth', 'That network needs a password.')
    if FIXTURE:
        return {'ok': True, 'uuid': 'fixture-' + ssid}
    device = wifi_device()
    if not device:
        raise Failure('radio_off', 'There is no Wi-Fi on this computer.')
    add = ['connection', 'add', 'type', 'wifi', 'ifname', device, 'con-name', ssid, 'ssid', ssid]
    if args.hidden:
        add += ['802-11-wireless.hidden', 'yes']
    if security in ('wpa-psk', 'sae', 'owe'):
        add += ['wifi-sec.key-mgmt', security]
    elif security == 'wep':
        add += ['wifi-sec.key-mgmt', 'none', 'wifi-sec.wep-key-type', wep_key_type(secret)]
    code, out, err = nmcli(*add)
    m = re.search(r'\(([0-9a-f-]{36})\)', out)
    if code != 0 or not m:
        raise Failure(*error_for(code, err, ssid))
    uuid = m.group(1)
    try:
        activate(uuid, ssid, secret_setting(security), secret)
    except Failure:
        nmcli('connection', 'delete', 'uuid', uuid)
        raise
    return {'ok': True, 'uuid': uuid}


def cmd_enterprise(args, stdin):
    secret = read_secret(stdin)
    settings = enterprise_settings(args.eap, args.phase2, args.identity or '', args.anonymous_identity or '',
                                   args.domain or '', not args.no_ca)
    if FIXTURE:
        return {'ok': True, 'uuid': 'fixture-' + args.ssid}
    device = wifi_device()
    if not device:
        raise Failure('radio_off', 'There is no Wi-Fi on this computer.')
    add = ['connection', 'add', 'type', 'wifi', 'ifname', device, 'con-name', args.ssid, 'ssid', args.ssid]
    if args.hidden:
        add += ['802-11-wireless.hidden', 'yes']
    code, out, err = nmcli(*(add + settings))
    m = re.search(r'\(([0-9a-f-]{36})\)', out)
    if code != 0 or not m:
        raise Failure(*error_for(code, err, args.ssid))
    uuid = m.group(1)
    try:
        activate(uuid, args.ssid, secret_setting('enterprise'), secret)
    except Failure as e:
        nmcli('connection', 'delete', 'uuid', uuid)
        if e.code == 'auth':
            raise Failure('auth', 'That username or password didn’t work for “%s”. Check them and try again.' % args.ssid)
        raise
    return {'ok': True, 'uuid': uuid}


def simple(*args, name=''):
    if FIXTURE:
        return {'ok': True}
    code, _, err = nmcli(*args)
    if code != 0:
        raise Failure(*error_for(code, err, name))
    return {'ok': True}


def cmd_forget(args):
    uuids = list(args.uuid or [])
    if args.ssid and not FIXTURE:
        uuids += [p['uuid'] for p in Reader().wifi_profiles() if p['ssid'] == args.ssid]
    if not uuids and not FIXTURE:
        raise Failure('not_found', 'That network isn’t saved.')
    return simple('connection', 'delete', *[x for u in uuids for x in ('uuid', u)], name=args.ssid or '')


def cmd_vpn_up(args, stdin):
    secret = read_secret(stdin) if args.ask else None
    if FIXTURE:
        return {'ok': True}
    try:
        activate(args.uuid, args.name or 'the VPN', 'vpn.secrets.password' if secret is not None else None, secret, wait='60')
    except Failure as e:
        if e.code == 'auth':
            raise Failure('auth', 'Type the password for %s.' % ('“%s”' % args.name if args.name else 'the VPN')
                          if secret is None else 'That password didn’t work for %s.' % ('“%s”' % args.name if args.name else 'the VPN'))
        raise
    return {'ok': True}


def vpn_type(path):
    """OpenVPN or WireGuard, from the file: WireGuard configurations have an [Interface]."""
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            text = f.read(65536)
    except OSError:
        raise Failure('not_found', 'That file can’t be read.')
    if re.search(r'^\s*\[Interface\]', text, re.M):
        return 'wireguard'
    if path.lower().endswith('.ovpn') or re.search(r'^\s*(client|remote|dev\s+tun)\b', text, re.M):
        return 'openvpn'
    raise Failure('usage', 'That file isn’t an OpenVPN or WireGuard configuration.')


def company_details(uuid):
    """For Settings' saved networks: is it a company (802.1X) network, and which certificate file
    does it check the server with ('' = the system's). Profiles without 802.1X answer neither."""
    code, text, _ = nmcli('-g', '802-11-wireless-security.key-mgmt', 'connection', 'show', 'uuid', uuid)
    if code != 0 or text.strip() != 'wpa-eap':
        return {'enterprise': False}
    code, text, _ = nmcli('-g', '802-1x.ca-cert', 'connection', 'show', 'uuid', uuid)
    ca = re.sub(r'\\(.)', r'\1', text.strip()) if code == 0 else ''     # one value: only unescape
    return {'enterprise': True, 'ca_cert': ca[7:] if ca.startswith('file://') else ca}


CERT_DIR = os.path.join(os.path.expanduser('~'), '.cert', 'arctic')


def cmd_ca_set(args):
    path = os.path.abspath(args.file)
    try:
        with open(path, 'rb') as f:
            head = f.read(65536)
    except OSError:
        raise Failure('not_found', 'That file can’t be read.')
    pem = b'-----BEGIN CERTIFICATE-----' in head
    if not pem and not (head[:1] == b'\x30' and len(head) > 100):
        raise Failure('usage', 'That file isn’t a certificate (a .pem, .crt, .cer or .der file).')
    if FIXTURE:
        return {'ok': True}
    # ~/.cert is where SELinux lets NetworkManager read a person's certificates.
    os.makedirs(CERT_DIR, mode=0o700, exist_ok=True)
    dest = os.path.join(CERT_DIR, '%s.%s' % (args.uuid, 'pem' if pem else 'der'))
    if os.path.abspath(dest) != path:
        with open(path, 'rb') as src, open(dest + '.tmp', 'wb') as out:
            out.write(src.read())
        os.replace(dest + '.tmp', dest)
    return simple('connection', 'modify', 'uuid', args.uuid, '802-1x.ca-cert', dest, '802-1x.system-ca-certs', 'no')


def cmd_vpn_import(args):
    kind = args.type or vpn_type(args.file)
    if FIXTURE:
        return {'ok': True, 'kind': kind}
    code, out, err = nmcli('connection', 'import', 'type', kind, 'file', args.file)
    if code != 0:
        if 'plugin' in (err or '').lower():
            raise Failure('failed', 'Install NetworkManager-openvpn to import OpenVPN files.')
        raise Failure(*error_for(code, err, os.path.basename(args.file)))
    m = re.search(r"Connection '(.+)' \(([0-9a-f-]{36})\)", out)
    return {'ok': True, 'kind': kind, 'name': m.group(1) if m else '', 'uuid': m.group(2) if m else ''}


def cmd_hotspot(args):
    """Turn the hotspot on or off. The first time, a profile is added without a password and
    brought up with a new one through a pipe (NetworkManager keeps it; the share card reads it
    back); later it is brought up as it is, with a new password only if the old one is gone."""
    if FIXTURE:
        return {'ok': True, 'active': args.mode == 'on'}
    existing = next(iter(Reader().wifi_profiles(hotspot=True)), None)
    if args.mode == 'off':
        if existing:
            simple('connection', 'down', 'uuid', existing['uuid'])
        return {'ok': True, 'active': False}
    device = wifi_device()
    if not device:
        raise Failure('radio_off', 'There is no Wi-Fi on this computer.')

    def start(uuid, fresh):
        try:
            activate(uuid, '', '802-11-wireless-security.psk' if fresh else None, hotspot_password() if fresh else None)
        except Failure as e:
            if e.code in ('denied', 'nm_down', 'auth'):
                raise
            raise Failure(e.code, 'The hotspot didn’t start. Your Wi-Fi card may not share while it is busy; try again.')

    if existing:
        try:
            start(existing['uuid'], False)
        except Failure as e:
            if e.code != 'auth':
                raise
            start(existing['uuid'], True)            # its password wasn't kept: a new one
        return {'ok': True, 'active': True, 'uuid': existing['uuid'], 'ssid': existing['ssid']}
    ssid = args.ssid or hotspot_ssid()
    # 2.4 GHz WPA2 (AES only): what every phone and laptop can join.
    code, out, err = nmcli('connection', 'add', 'type', 'wifi', 'ifname', device, 'con-name', HOTSPOT,
                           'autoconnect', 'no', 'ssid', ssid, '802-11-wireless.mode', 'ap', '802-11-wireless.band', 'bg',
                           'ipv4.method', 'shared', 'wifi-sec.key-mgmt', 'wpa-psk', 'wifi-sec.proto', 'rsn',
                           'wifi-sec.pairwise', 'ccmp', 'wifi-sec.group', 'ccmp')
    m = re.search(r'\(([0-9a-f-]{36})\)', out)
    if code != 0 or not m:
        raise Failure(*error_for(code, err, ''))
    try:
        start(m.group(1), True)
    except Failure:
        nmcli('connection', 'delete', 'uuid', m.group(1))
        raise
    return {'ok': True, 'active': True, 'uuid': m.group(1), 'ssid': ssid}


# ---- Tailscale ----------------------------------------------------------------------------------
TS_STATES = {'Running': 'running', 'Starting': 'starting', 'Stopped': 'stopped', 'NeedsLogin': 'signed_out',
             'NeedsMachineAuth': 'signed_out', 'NoState': 'signed_out'}
TS_NONE = {'state': 'no_daemon', 'tailnet': '', 'exit_node': '', 'exit_nodes': []}


def parse_tailscale(text):
    """`tailscale status --json` → {state, tailnet, exit_node (its name, '' for none),
    exit_nodes: [{ip, name, online, active}]}; None when it isn't that JSON (no tailscaled)."""
    try:
        data = json.loads(text or '')
    except ValueError:
        return None
    if not isinstance(data, dict) or 'BackendState' not in data:
        return None
    nodes, current = [], ''
    for peer in (data.get('Peer') or {}).values():
        if not isinstance(peer, dict) or not (peer.get('ExitNodeOption') or peer.get('ExitNode')):
            continue
        ips = [ip for ip in peer.get('TailscaleIPs') or [] if isinstance(ip, str)]
        ip = next((i for i in ips if '.' in i), ips[0] if ips else '')
        if not ip:
            continue
        name = (peer.get('DNSName') or '').split('.')[0] or peer.get('HostName') or ip
        node = {'ip': ip, 'name': name, 'online': peer.get('Online') is True, 'active': peer.get('ExitNode') is True}
        if node['active']:
            current = name
        nodes.append(node)
    nodes.sort(key=lambda n: (not n['online'], n['name'].lower()))
    return {'state': TS_STATES.get(data.get('BackendState'), 'stopped'),
            'tailnet': (data.get('CurrentTailnet') or {}).get('Name') or '', 'exit_node': current, 'exit_nodes': nodes}


def tailscale(*args, timeout=30):
    try:
        p = subprocess.run(['tailscale', *args], capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        raise Failure('not_installed', 'Tailscale isn’t installed.')
    except subprocess.TimeoutExpired:
        raise Failure('timeout', 'Tailscale didn’t answer. Try again.')
    return p.returncode, p.stdout, p.stderr


def tailscale_failure(text):
    low = (text or '').lower()
    if 'access denied' in low or 'permission denied' in low or 'prefs write access denied' in low:
        return Failure('denied', 'Only Tailscale’s operator can switch it. Let Arctic switch it (asks for your password once).')
    if "failed to connect to local tailscale" in low or 'is tailscaled running' in low:
        return Failure('no_daemon', 'Tailscale’s service isn’t running.')
    first = next((l.strip() for l in (text or '').splitlines() if l.strip()), '')[:100]
    return Failure('failed', ('Tailscale couldn’t do that. ' + first).strip())


def tailscale_login():
    """Signed out: `tailscale up` prints a sign-in page and then waits (here up to 15 minutes, on
    its own) for the browser sign-in to finish; the page goes back to the menu, which opens it."""
    try:
        p = subprocess.Popen(['tailscale', 'up', '--timeout=15m'], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        raise Failure('not_installed', 'Tailscale isn’t installed.')
    fd = p.stdout.fileno()
    os.set_blocking(fd, False)
    sel = selectors.DefaultSelector()
    sel.register(fd, selectors.EVENT_READ)
    deadline, said, buf, eof = time.monotonic() + 20, '', b'', False
    while not eof and time.monotonic() < deadline and sel.select(max(0.0, deadline - time.monotonic())):
        lines, buf, eof = lines_of(fd, buf)
        for line in lines:
            m = re.search(r'https://\S+', line)
            if m:
                return {'ok': True, 'login_url': m.group(0)}
            said += line + '\n'
    if eof:
        try:
            p.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass
    if p.poll() == 0:
        return {'ok': True}
    raise tailscale_failure(said) if said else Failure('timeout', 'Tailscale didn’t answer. Try again.')


def cmd_tailscale(args):
    action, value = args.action, args.value
    if action == 'exit-node' and not (value == 'none' or re.fullmatch(r'[0-9A-Fa-f.:]{2,45}', value or '')):
        raise Failure('usage', 'usage: tailscale exit-node IP|none')
    if FIXTURE:
        return dict(load_fixture().get('tailscale') or TS_NONE, ok=True) if action == 'status' else {'ok': True}
    if action == 'status':
        _code, out, _err = tailscale('status', '--json', timeout=10)
        return dict(parse_tailscale(out) or TS_NONE, ok=True)
    if action == 'up':
        _code, out, _err = tailscale('status', '--json', timeout=10)
        view = parse_tailscale(out)
        if view is None:
            raise Failure('no_daemon', 'Tailscale’s service isn’t running.')
        if view['state'] == 'signed_out':
            return tailscale_login()
        code, out, err = tailscale('up', '--timeout=30s', timeout=45)
    elif action == 'down':
        code, out, err = tailscale('down')
    elif action == 'exit-node':
        code, out, err = tailscale('set', '--exit-node=' + ('' if value == 'none' else value))
    elif action == 'operator':
        try:
            p = subprocess.run(['pkexec', 'tailscale', 'set', '--operator=' + pwd.getpwuid(os.getuid()).pw_name],
                               capture_output=True, text=True, timeout=300, stdin=subprocess.DEVNULL)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            raise Failure('failed', 'Arctic couldn’t ask for your password.')
        if p.returncode in (126, 127):
            raise Failure('cancelled', 'Tailscale wasn’t changed.')
        code, out, err = p.returncode, p.stdout, p.stderr
    else:
        raise Failure('usage', 'usage: tailscale status|up|down|operator|exit-node IP|none')
    if code != 0:
        raise tailscale_failure(err or out)
    return {'ok': True}


# ---- watch ------------------------------------------------------------------------------------
def lines_of(fd, buf):
    """Read what is available on fd; returns (complete lines, rest, eof)."""
    try:
        chunk = os.read(fd, 65536)
    except BlockingIOError:
        return [], buf, False
    if not chunk:
        return ([buf.decode(errors='replace')] if buf else []), b'', True
    buf += chunk
    parts = buf.split(b'\n')
    return [p.decode(errors='replace') for p in parts[:-1]], parts[-1], False


def watch_fixture():
    data = load_fixture()
    state = dict(data.get('state', {}), type='state')
    state.setdefault('nm_running', True)
    emit(state)
    scanning = False
    for line in sys.stdin:
        try:
            op = json.loads(line)
        except ValueError:
            continue
        if op.get('op') == 'scan':
            scanning = bool(op.get('on'))
        if scanning and op.get('op') in ('scan', 'rescan'):
            emit({'type': 'networks', 'networks': data.get('networks', [])})
    return 0


def watch():
    if FIXTURE:
        return watch_fixture()
    reader = Reader()
    try:
        monitor = subprocess.Popen(['nmcli', 'monitor'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   stdin=subprocess.DEVNULL)
    except FileNotFoundError:
        emit({'type': 'error', 'error': 'nmcli isn’t installed.', 'code': 'nm_down'})
        return 2
    last = None
    joining = None                  # the Wi-Fi profile NetworkManager was last seen activating

    def publish():
        nonlocal last, joining
        state = reader.state()
        text = json.dumps(state, sort_keys=True)
        wifi = next((a for a in state['active'] if a['type'] == 'wifi'), None)
        if wifi:
            joining = wifi
        if text != last:
            last = text
            emit(state)

    publish()
    sel = selectors.DefaultSelector()
    os.set_blocking(sys.stdin.fileno(), False)
    os.set_blocking(monitor.stdout.fileno(), False)
    sel.register(sys.stdin.fileno(), selectors.EVENT_READ, 'stdin')
    sel.register(monitor.stdout.fileno(), selectors.EVENT_READ, 'monitor')
    bufs = {'stdin': b'', 'monitor': b'', 'events': b''}
    # Device failures with their reason, for "needs_secrets" (only nmcli monitor without gdbus).
    try:
        events = subprocess.Popen(['gdbus', 'monitor', '--system', '--dest', 'org.freedesktop.NetworkManager'],
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
        os.set_blocking(events.stdout.fileno(), False)
        sel.register(events.stdout.fileno(), selectors.EVENT_READ, 'events')
    except FileNotFoundError:
        events = None
    scanning, next_scan, refresh_at = False, 0.0, 0.0
    try:
        while True:
            now = time.monotonic()
            deadlines = [d for d in (refresh_at if refresh_at else None, next_scan if scanning else None) if d]
            timeout = max(0.0, min(deadlines) - now) if deadlines else None
            for key, _ in sel.select(timeout):
                lines, bufs[key.data], eof = lines_of(key.fd, bufs[key.data])
                if key.data == 'monitor':
                    if lines:
                        refresh_at = refresh_at or time.monotonic() + DEBOUNCE
                    if eof:
                        return 1                 # NetworkService restarts the helper
                    continue
                if key.data == 'events':
                    for line in lines:
                        change = parse_state_changed(line)
                        if (change and change[1] == NM_DEVICE_FAILED and change[3] == NM_REASON_NO_SECRETS
                                and joining and joining.get('state') == 'activating'):
                            emit({'type': 'needs_secrets', 'uuid': joining['uuid'], 'ssid': joining['name'],
                                  'device': joining['device']})
                            joining = None
                    if eof:
                        sel.unregister(key.fd)
                    continue
                if eof:
                    return 0                     # the shell went away
                for line in lines:
                    try:
                        op = json.loads(line)
                    except ValueError:
                        continue
                    if op.get('op') == 'scan':
                        scanning = bool(op.get('on'))
                        if scanning:
                            emit({'type': 'networks', 'networks': reader.networks(rescan=True)})
                            next_scan = time.monotonic() + SCAN_INTERVAL
                    elif op.get('op') == 'rescan':
                        emit({'type': 'networks', 'networks': reader.networks(rescan=True)})
                        next_scan = time.monotonic() + SCAN_INTERVAL
            now = time.monotonic()
            if refresh_at and now >= refresh_at:
                refresh_at = 0.0
                publish()
            if scanning and now >= next_scan:
                emit({'type': 'networks', 'networks': reader.networks(rescan=True)})
                next_scan = time.monotonic() + SCAN_INTERVAL
    finally:
        monitor.terminate()
        if events:
            events.terminate()


# ---- main -------------------------------------------------------------------------------------
def parse(argv):
    import argparse
    p = argparse.ArgumentParser(prog='network.py')
    sub = p.add_subparsers(dest='cmd', required=True)
    sub.add_parser('watch')
    sub.add_parser('status')
    s = sub.add_parser('scan')
    s.add_argument('--rescan', action='store_true')
    sub.add_parser('saved')
    c = sub.add_parser('connect')
    c.add_argument('--uuid')
    c.add_argument('--ssid')
    c.add_argument('--name', help='shown in messages')
    c.add_argument('--security', choices=['open', 'owe', 'wep', 'wpa-psk', 'sae', 'enterprise'])
    c.add_argument('--hidden', action='store_true')
    c.add_argument('--ask', action='store_true')
    e = sub.add_parser('enterprise')
    e.add_argument('--ssid', required=True)
    e.add_argument('--eap', default='peap')
    e.add_argument('--phase2', default='mschapv2')
    e.add_argument('--identity', required=True)
    e.add_argument('--anonymous-identity')
    e.add_argument('--domain')
    ca = e.add_mutually_exclusive_group()
    ca.add_argument('--system-ca', action='store_true')
    ca.add_argument('--no-ca', action='store_true')
    e.add_argument('--hidden', action='store_true')
    e.add_argument('--ask', action='store_true')
    d = sub.add_parser('disconnect')
    d.add_argument('--uuid', required=True)
    f = sub.add_parser('forget')
    f.add_argument('--uuid', action='append')
    f.add_argument('--ssid')
    a = sub.add_parser('autoconnect')
    a.add_argument('--uuid', required=True)
    a.add_argument('mode', choices=['on', 'off'])
    r = sub.add_parser('radio')
    r.add_argument('what', choices=['wifi'])
    r.add_argument('mode', choices=['on', 'off'])
    sh = sub.add_parser('share')
    sh.add_argument('--uuid', required=True)
    sh.add_argument('--reveal', action='store_true')
    ap = sub.add_parser('airplane')
    ap.add_argument('mode', choices=['on', 'off'])
    u = sub.add_parser('vpn-up')
    u.add_argument('--uuid', required=True)
    u.add_argument('--name')
    u.add_argument('--ask', action='store_true')
    cs = sub.add_parser('ca-set')
    cs.add_argument('--uuid', required=True)
    cs.add_argument('--file', required=True)
    vi = sub.add_parser('vpn-import')
    vi.add_argument('--file', required=True)
    vi.add_argument('--type', choices=['openvpn', 'wireguard'])
    v = sub.add_parser('vpn-down')
    v.add_argument('--uuid', required=True)
    ts = sub.add_parser('tailscale')
    ts.add_argument('action', choices=['status', 'up', 'down', 'operator', 'exit-node'])
    ts.add_argument('value', nargs='?')
    hs = sub.add_parser('hotspot')
    hs.add_argument('mode', choices=['on', 'off'])
    hs.add_argument('--ssid')
    return p.parse_args(argv)


def main(argv=None, stdin=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    stdin = stdin or sys.stdin
    if args.cmd == 'watch':
        return watch()
    try:
        if args.cmd == 'status':
            out = dict(load_fixture().get('state', {}), type='state') if FIXTURE else Reader().state()
            out['ok'] = True
        elif args.cmd == 'scan':
            out = {'ok': True, 'networks': load_fixture().get('networks', []) if FIXTURE else Reader().networks(args.rescan)}
        elif args.cmd == 'saved':
            if FIXTURE:
                data = load_fixture()
                out = {'ok': True, 'saved': data.get('saved', []), 'vpn': data.get('state', {}).get('vpn', [])}
            else:
                reader = Reader()
                state = reader.state()
                saved = [dict(p, **company_details(p['uuid'])) for p in reader.wifi_profiles()]
                out = {'ok': True, 'saved': saved, 'vpn': state['vpn']}
        elif args.cmd == 'connect':
            out = cmd_connect(args, stdin)
        elif args.cmd == 'enterprise':
            out = cmd_enterprise(args, stdin)
        elif args.cmd == 'disconnect':
            out = simple('connection', 'down', 'uuid', args.uuid)
        elif args.cmd == 'forget':
            out = cmd_forget(args)
        elif args.cmd == 'autoconnect':
            out = simple('connection', 'modify', 'uuid', args.uuid, 'connection.autoconnect',
                         'yes' if args.mode == 'on' else 'no')
        elif args.cmd == 'radio':
            out = simple('radio', 'wifi', args.mode)
        elif args.cmd == 'share':
            out = cmd_share(args)
        elif args.cmd == 'airplane':
            out = cmd_airplane(args.mode == 'on')
        elif args.cmd == 'vpn-up':
            out = cmd_vpn_up(args, stdin)
        elif args.cmd == 'vpn-import':
            out = cmd_vpn_import(args)
        elif args.cmd == 'ca-set':
            out = cmd_ca_set(args)
        elif args.cmd == 'vpn-down':
            out = simple('connection', 'down', 'uuid', args.uuid)
        elif args.cmd == 'hotspot':
            out = cmd_hotspot(args)
        elif args.cmd == 'tailscale':
            out = cmd_tailscale(args)
        else:
            raise Failure('usage', 'Unknown command.')
    except Failure as e:
        emit({'ok': False, 'error': e.message, 'code': e.code})
        return 1
    except (OSError, ValueError) as e:
        emit({'ok': False, 'error': 'Couldn’t read the network settings (%s).' % e.__class__.__name__, 'code': 'failed'})
        return 1
    emit(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
