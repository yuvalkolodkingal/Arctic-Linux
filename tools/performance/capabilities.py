#!/usr/bin/env python3
"""Read-only feature checks in a disposable VM, after performance measurements.

Pass the performance probe's namespace to main(). UI launches and package
transactions are tested separately; these checks never weaken system policy.
"""
import json
import os
from pathlib import Path
import re
import sys


def main(performance, wallpaper=False):
    run = performance['run']
    stage = sys.argv[1]
    if (Path(__file__).parent != Path('/run/t') or os.geteuid() != 0
            or run(['systemd-detect-virt', '--vm']) not in ('qemu', 'kvm')):
        raise RuntimeError('Requires root in the disposable QEMU VM')
    prefix = performance['desktop']()
    failed = False

    def check(name, fn):
        nonlocal failed
        try:
            value = fn()
            status = 'passed'
        except Exception as error:
            failed = True
            value, status = str(error), 'failed'
        print('ARCTIC-CAPABILITY ' + json.dumps(dict(stage=stage, check=name,
              status=status, value=value)), flush=True)

    def require(condition, value):
        if not condition:
            raise RuntimeError(value)
        return value

    check('selinux', lambda: require(run(['getenforce']) == 'Enforcing', 'SELinux enforcing'))
    roles = performance['functional_roles'](prefix)
    check('browser-ref', lambda: roles['roles']['browser']['package'])
    browser = roles['roles']['browser']
    app = performance['ROLE_APPS'][browser['id']]
    entry = ('/var/lib/flatpak/exports/share/applications/' if 'flatpak' in app
             else '/usr/share/applications/') + app['desktop']
    check('browser-desktop-entry', lambda: run(prefix + ['test', '-r', entry]))
    check('package-managers', lambda: run(['rpm', '-q', 'dnf5', 'flatpak', 'nix', 'nix-daemon']))
    check('update-repository-key', lambda: require(
          'BEGIN PGP PUBLIC KEY BLOCK' in Path('/etc/pki/rpm-gpg/RPM-GPG-KEY-arctic').read_text(),
          'Public Arctic repository key is installed'))
    check('update-tools', lambda: run(['rpm', '-qf', '/usr/bin/arctic-update', '/usr/bin/arctic-nix']))
    check('network-security-units', lambda: run(['systemctl', 'show', 'NetworkManager.service',
          'firewalld.service', 'nix-daemon.socket', '-p', 'Id', '-p', 'LoadState', '-p', 'ActiveState']))
    check('failed-units-inventory', lambda: run(['systemctl', '--failed', '--no-pager']))
    settings = prefix + ['python3', '/usr/share/arctic/settings/scripts/arctic_settings.py']
    check('settings-shell-options', lambda: json.loads(run(settings + ['shell-options'])))
    if wallpaper:
        def publisher():
            value = json.loads(run(settings + ['login-wallpaper', 'status'], timeout=180))
            require(value.get('ok') and value.get('available', True), value)
            return value
        check('shared-wallpaper-publisher', publisher)
    if stage == 'installed':
        check('btrfs-root', lambda: require(run(['findmnt', '-n', '-o', 'FSTYPE', '/']) == 'btrfs', 'Root is Btrfs'))
        check('installed-filesystem-usage-bytes', lambda: run(['btrfs', 'filesystem', 'usage', '-b', '/'], timeout=180))
        check('encryption', lambda: require(any('luks' in line.lower() and not line.startswith('#')
              for line in Path('/etc/crypttab').read_text().splitlines()), Path('/etc/crypttab').read_text()))
        check('snapshot-configs', lambda: run(['snapper', 'list-configs']))
        check('nix-persistent-mount', lambda: require(
              run(['findmnt', '-n', '-o', 'TARGET', '-T', '/nix']) == '/nix', 'Nix has its persistent mount'))
        check('nix-store-permissions', lambda: require(
              Path('/nix').stat().st_uid == 0 and not Path('/nix').stat().st_mode & 0o022,
              'Nix is root owned and not writable by other users'))
        check('nix-security-config', lambda: run(['/usr/bin/nix', '--extra-experimental-features',
              'nix-command', 'config', 'show', '--json']))
        check('boot-initrds', lambda: require(bool(list(Path('/boot').glob('initramfs-*.img'))),
              [str(path) for path in Path('/boot').glob('initramfs-*.img')]))
        check('pending-offline-requests', lambda: json.loads(Path('/var/lib/arctic/pending.json').read_text())
              if Path('/var/lib/arctic/pending.json').exists() else [])
    check('avc-inventory', lambda: [line for line in run(['journalctl', '-b', '--no-pager', '-o', 'cat'],
          timeout=180).splitlines() if re.search(r'avc:\s+denied', line, re.I)])
    return int(failed)


if __name__ == '__main__':
    raise SystemExit('Use tools/performance/compose-probe.py to build the guest script')
