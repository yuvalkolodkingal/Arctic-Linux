#!/usr/bin/env python3
"""Embed native desktop discovery and real Nix/offline updater acceptance."""
import argparse
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=Path)
parser.add_argument('--online-proxy', action='store_true',
                    help='Require the explicit VM test proxy; configure the daemon only in /run')
args = parser.parse_args()
root = Path(__file__).resolve().parent
performance = (root/'guest.py').read_text()
nix = (root.parent/'nix-acceptance/guest.py').read_text()
setup = '''
import json
import os
from pathlib import Path
from urllib.parse import urlparse
if (Path(__file__).parent != Path('/run/t') or os.geteuid() != 0
        or measurement['run'](['systemd-detect-virt', '--vm']) not in ('qemu', 'kvm')):
    raise RuntimeError('Requires the disposable VM data CD')
proxy = None
if ONLINE_PROXY:
    if not Path('/run/t/proxy.env').is_file():
        raise RuntimeError('Explicit online VM test proxy was not provisioned')
    proxy = os.environ.get('HTTPS_PROXY', '')
    parsed = urlparse(proxy)
    if (parsed.scheme != 'http' or parsed.hostname != '10.0.2.2'
            or not parsed.port or parsed.username or parsed.password or parsed.path):
        raise RuntimeError('Unexpected VM test proxy endpoint')
    # Root collection already installed this test CA with TLS verification enabled.
    if not Path('/etc/pki/ca-trust/source/anchors/arctic-test-proxy.crt').is_file():
        raise RuntimeError('VM test CA was not provisioned')
    dropin = Path('/run/systemd/system/nix-daemon.service.d/arctic-test-proxy.conf')
    dropin.parent.mkdir(parents=True, exist_ok=True)
    dropin.write_text('[Service]\\nEnvironment="HTTPS_PROXY='+proxy+'" "https_proxy='+proxy+'" '
                      '"NO_PROXY=localhost,127.0.0.1" "no_proxy=localhost,127.0.0.1"\\n')
    measurement['run'](['systemctl', 'daemon-reload'])
    measurement['run'](['systemctl', 'try-restart', 'nix-daemon.service'])
    print('ARCTIC-NIX-TEST-PROXY runtime_only=true tls_verification=enabled', flush=True)
def native_desktop():
    prefix = measurement['desktop']()
    if proxy:
        prefix += ['HTTPS_PROXY='+proxy, 'https_proxy='+proxy,
                   'NO_PROXY=localhost,127.0.0.1', 'no_proxy=localhost,127.0.0.1']
    return prefix
nix_acceptance['desktop'] = native_desktop
prefix = native_desktop()
awake = json.loads(measurement['run'](prefix+['arctic-keep-awake', 'status', '--json']))
if not awake.get('on'):
    measurement['run'](prefix+['arctic-keep-awake', 'on', '--quiet'])
try:
    result = nix_acceptance['main'](update_method='arctic-offline')
finally:
    if not awake.get('on'):
        measurement['run'](prefix+['arctic-keep-awake', 'off', '--quiet'])
raise SystemExit(result)
'''
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    '#!/usr/bin/env python3\n'
    'measurement = {"__name__": "arctic_measurement", "__file__": __file__}\n'
    f'exec(compile({performance!r}, __file__, "exec"), measurement)\n'
    'nix_acceptance = {"__name__": "arctic_nix_acceptance", "__file__": __file__}\n'
    f'exec(compile({nix!r}, __file__, "exec"), nix_acceptance)\n'
    f'ONLINE_PROXY = {args.online_proxy!r}\n' + setup)
