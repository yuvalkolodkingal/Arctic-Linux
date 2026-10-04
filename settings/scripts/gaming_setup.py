"""Optional gaming package planning. Does not install, enroll keys or launch games on import."""
import json
from pathlib import Path
import re
import subprocess
import tomllib


def run(argv):
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=10)
        return p.returncode, p.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 1, ''


def hardware(root=Path('/sys/bus/pci/devices')):
    result = []
    for path in sorted(root.glob('*')):
        try:
            kind = (path/'class').read_text().strip().removeprefix('0x')[:4]
            if kind not in ('0300', '0302', '0380'):
                continue
            vendor=(path/'vendor').read_text().strip().removeprefix('0x')
            device=(path/'device').read_text().strip().removeprefix('0x')
            if not re.fullmatch('[0-9a-f]{4}',vendor ) or not re.fullmatch('[0-9a-f]{4}',device):
                continue
            result.append(dict(vendor=vendor, device=device, pci=path.name, kind=kind,
                               name={'1002':'AMD','8086':'Intel','10de':'NVIDIA'}.get(vendor,vendor),
                               driver=(path/'driver').resolve().name if (path/'driver').exists() else 'unbound'))
        except OSError:
            continue
    return result


def matches(rule, gpu):
    return (rule.get('bus') == 'pci' and rule.get('vendor') == gpu['vendor']
            and gpu['kind'] in rule.get('class', []) and gpu['device'] not in rule.get('exclude', [])
            and (not rule.get('devices') or gpu['device'] in rule['devices'])
            and (not rule.get('device_min') or gpu['device'] >= rule['device_min'])
            and (not rule.get('device_max') or gpu['device'] <= rule['device_max']))


def package_plan(gpus, catalog, installed=(), secure_boot='unknown'):
    packages = ['steam', 'vulkan-loader.x86_64', 'vulkan-loader.i686', 'vulkan-tools']
    warnings = []
    blocked = ''
    nvidia = [g for g in gpus if g['vendor'] == '10de']
    if any(g['vendor'] in ('1002','8086') for g in gpus) or not nvidia:
        mesa = 'mesa-vulkan-drivers-freeworld' if 'mesa-vulkan-drivers-freeworld' in installed else 'mesa-vulkan-drivers'
        packages += [mesa+'.x86_64', mesa+'.i686']
    drivers = set()
    for gpu in nvidia:
        for name in ('nvidia','nvidia-580xx'):
            data = catalog.get(name, {})
            if any(matches(rule,gpu) for rule in data.get('detect', [])):
                drivers.add(name)
        if not any(any(matches(r,gpu) for r in catalog.get(n,{}).get('detect',[])) for n in ('nvidia','nvidia-580xx')):
            blocked = 'This NVIDIA device has no supported proprietary driver in Arctic’s catalog. Review the driver guide before gaming setup.'
    if len(drivers) > 1:
        blocked = 'These NVIDIA GPUs need conflicting driver generations. An administrator must choose a supported hardware configuration.'
    for name in sorted(drivers):
        driver_pkgs = catalog[name].get('install', [{}])[0].get('packages', [])
        packages += driver_pkgs
        prefix = 'xorg-x11-drv-' + name
        packages += [prefix+'-libs.x86_64',prefix+'-libs.i686']
        if 'akmod-'+name not in installed and secure_boot != 'disabled':
            blocked = 'Secure Boot is enabled or its state is unknown. Complete Arctic’s documented NVIDIA signing/enrollment workflow before installing a new driver here. No key is generated or enrolled by Settings.'
        warnings.append('NVIDIA kernel modules must finish building for the installed kernel before reboot. Every kernel update needs a matching module; enrollment may be required.')
    if not gpus:
        warnings.append('No graphics device was detected. This package plan does not prove that Vulkan or games will run.')
    if len(gpus)>1:
        warnings.append('Hybrid graphics: use arctic-gpu run steam or the launcher’s discrete-GPU action when needed.')
    warnings.append('Steam downloads Proton when selected. Game and anti-cheat compatibility varies; Mango/Wayland, GPU drivers and individual games require hardware testing.')
    return dict(packages=list(dict.fromkeys(packages)), warnings=warnings, blocked=blocked)


def status(paths):
    catalog = {}
    for name in ('nvidia','nvidia-580xx'):
        file = paths.share/'catalog/drivers'/name/'module.toml'
        if not file.is_file():
            file = Path(__file__).resolve().parents[2]/'modules/drivers'/name/'module.toml'
        try:
            catalog[name] = tomllib.loads(file.read_text())
        except (OSError, ValueError):
            catalog[name] = {}
    names=['steam','akmod-nvidia','akmod-nvidia-580xx','mesa-vulkan-drivers-freeworld','rpmfusion-free-release','rpmfusion-nonfree-release']
    installed=[n for n in names if run(['rpm','-q',n])[0]==0]
    code, boot=run(['mokutil','--sb-state'])
    secure='enabled' if code==0 and 'SecureBoot enabled' in boot else 'disabled' if code==0 and 'SecureBoot disabled' in boot else 'unknown'
    gpus=hardware()
    plan=package_plan(gpus,catalog,installed,secure)
    code, release=run(['rpm','--eval','%{fedora}'])
    return dict(ok=True,gpus=gpus,secure_boot=secure,steam='steam' in installed,
                repositories=all(n in installed for n in ('rpmfusion-free-release','rpmfusion-nonfree-release')),
                release=release if code==0 and re.fullmatch(r'[0-9]{2}',release) else '',**plan)


def setup_argv(data):
    if data['blocked']:
        raise ValueError(data['blocked'])
    if not data['repositories']:
        raise ValueError('Enable RPM Fusion first using the repository setup guide. Its keys and package transaction require your approval.')
    return ['pkexec','/usr/bin/dnf5','install',*data['packages']]
