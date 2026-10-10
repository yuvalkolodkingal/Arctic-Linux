#!/usr/bin/env python3
"""Root checker on the fresh installed disk; no live root or credentials exported."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import pwd
import re
import stat
import subprocess
import sys


def require(value, message):
    if not value:
        raise RuntimeError(message)


def protected(path, limit=4*1024*1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0 and not info.st_mode & 0o022
                and 0 <= info.st_size <= limit, 'installed fixture protection differs')
        result = os.read(fd, limit + 1)
        require(len(result) == info.st_size, 'installed fixture bytes differ')
        return result
    finally:
        os.close(fd)


def command(argv):
    result = subprocess.run(argv, capture_output=True, timeout=10, check=True)
    require(len(result.stdout) <= 65536, 'installed command exceeds bound')
    return result.stdout.decode().strip()


def main():
    require(os.geteuid() == 0 and len(sys.argv) == 2 and re.fullmatch('[0-9a-f]{32}', sys.argv[1]),
            'installed root invocation differs')
    context = json.loads(protected('/run/t/installer-context.json', 16384))
    guest = protected('/run/t/installer-guest.py')
    require(hashlib.sha256(guest).hexdigest() == context['checker_sha256'], 'installed base checker bytes differ')
    spec = importlib.util.spec_from_file_location('installed_checked_base', '/run/t/installer-guest.py')
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    module.validate_context(context)
    require(context['schema'] == 'arctic-installer-active-context-v1'
            and hashlib.sha256(protected('/run/t/installed-guest.py')).hexdigest() == context['installed_checker_sha256'],
            'installed active checker bytes differ')
    require('rd.live.image' not in Path('/proc/cmdline').read_text().split()
            and not Path('/run/initramfs/live').exists() and command(['systemd-detect-virt']) in ('qemu', 'kvm'),
            'fresh installed boot reused a live root')
    require(os.environ.get('SUDO_USER') == 'arcticqual' and os.environ.get('SUDO_UID') == '1000'
            and pwd.getpwnam('arcticqual').pw_uid == 1000, 'actual installed account authentication differs')
    session = os.environ.get('XDG_SESSION_ID') or os.environ.get('SUDO_SESSION_ID')
    # Sudo may strip XDG_SESSION_ID: derive the only real tty6 login from logind.
    sessions = command(['loginctl', 'list-sessions', '--no-legend']).splitlines()
    matches = [row.split()[0] for row in sessions if len(row.split()) >= 3 and row.split()[2] == 'arcticqual'
               and command(['loginctl', 'show-session', row.split()[0], '-p', 'TTY', '--value']) == 'tty6']
    require(len(matches) == 1 and command(['loginctl', 'show-session', matches[0], '-p', 'User', '--value']) == '1000',
            'installed console login identity differs')
    source = command(['findmnt', '--raw', '--noheadings', '-o', 'SOURCE', '--mountpoint', '/'])
    block = command(['findmnt', '--raw', '--nofsroot', '--noheadings', '-o', 'SOURCE', '--mountpoint', '/'])
    require(re.fullmatch('/dev/vda[1-9][0-9]*', block) and source in (block, block + '[/@]')
            and command(['findmnt', '--raw', '--noheadings', '-o', 'FSTYPE', '--mountpoint', '/']) == 'btrfs'
            and Path('/sys/class/block/' + Path(block).name).resolve().parent == Path('/sys/class/block/vda').resolve(),
            'installed root is not this owned target disk')
    require(Path('/sys/class/block/vda/device/driver').resolve(strict=True).name == 'virtio_blk',
            'installed target driver differs')
    serial = Path('/sys/class/block/vda/serial').read_text().strip()
    require(serial == context['disk_serial'] and command(['getenforce']) == 'Enforcing', 'installed target/security differs')
    values = dict(row.split('=', 1) for row in protected('/etc/vconsole.conf', 4096).decode().splitlines()
                  if '=' in row and not row.startswith('#'))
    keyboard = dict(xkb_layout=values.get('XKBLAYOUT'), xkb_options=values.get('XKBOPTIONS'), vconsole_keymap=values.get('KEYMAP'))
    require(keyboard == dict(xkb_layout='us,il', xkb_options='grp:alt_shift_toggle', vconsole_keymap='us')
            and b'xkb_rules_layout=us,il\n' in protected('/etc/arctic/mango/keyboard.conf', 4096)
            and b'xkb_rules_options=grp:alt_shift_toggle\n' in protected('/etc/arctic/mango/keyboard.conf', 4096),
            'installed Hebrew keyboard was not preserved')
    report = dict(schema='arctic-active-installed-boot-v1', context=context,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(), selinux='Enforcing',
                  root=dict(source=source, block_source=block, fstype='btrfs', serial=serial), keyboard=keyboard,
                  authentication=dict(nonce=sys.argv[1], username='arcticqual', uid=1000, status='exact_installed_uid_response'),
                  release_acceptance=False)
    print('ARCTIC-ACTIVE-INSTALLED-READY=' + sys.argv[1] + ' user=arcticqual uid=1000', flush=True)
    print('ARCTIC-ACTIVE-INSTALLED ' + json.dumps(report, sort_keys=True, allow_nan=False), flush=True)


if __name__ == '__main__':
    try:
        main()
    except BaseException:
        print('ARCTIC-ACTIVE-INSTALLED-FAILED', flush=True)
        raise SystemExit(1)
