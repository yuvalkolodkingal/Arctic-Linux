#!/usr/bin/env python3
"""Administrative updates for Arctic's root-owned installer fallback profile.

The entry point uses Python isolated mode. No arguments select paths, programs,
flakes or settings. Only known installer packages may be rebuilt here. Ordinary
users' profiles are never read or changed. Fedora owns the Nix engine.
"""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

# This file and its sibling are installed in a root-owned RPM directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))
import nixlib

PROFILE = Path('/nix/var/nix/profiles/default')
INSTALLER_PIN = 'github:NixOS/nixpkgs/5e2305d577ca00acbba631b05cb1094d172b29f3'
ATTRS = {'legacyPackages.x86_64-linux.lazygit', 'legacyPackages.x86_64-linux.yazi'}
ENV = {'PATH': '/usr/bin:/usr/sbin', 'HOME': '/root', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}


def run(argv, capture=False):
    result = subprocess.run(argv, env=ENV, cwd='/', stdin=subprocess.DEVNULL,
                            text=True, stdout=subprocess.PIPE if capture else None,
                            check=True)
    return result.stdout if capture else ''


def manifest(path):
    return json.loads(run(nixlib.base() + ['profile', 'list', '--profile', str(path), '--json'], capture=True))


def plan(data):
    if not isinstance(data, dict) or data.get('version') != 3 or not isinstance(data.get('elements'), dict):
        raise ValueError('Unsupported shared-profile manifest. No changes made.')
    refs = []
    for name, item in data['elements'].items():
        if (not isinstance(item, dict) or item.get('attrPath') not in ATTRS
                or name != item['attrPath'].rsplit('.', 1)[-1]
                or item.get('originalUrl') not in (INSTALLER_PIN, nixlib.SOURCE)
                or item.get('active') is not True or item.get('priority') != 5
                or item.get('outputs') is not None):
            raise ValueError('The shared profile contains custom entries or settings. An administrator must manage it directly; nothing was changed.')
        refs.append(nixlib.SOURCE + '#' + item['attrPath'])
    if not refs:
        raise ValueError('No shared installer Nix packages are installed.')
    return sorted(refs)


def update():
    before = PROFILE.resolve(strict=True)
    refs = plan(manifest(PROFILE))
    print('Updating shared installer packages for all users from ' + nixlib.SOURCE + '.', flush=True)
    print('The previous pinned generation remains available for rollback.', flush=True)
    # Build the complete replacement first. Failures leave the active profile
    # untouched. Temporary profile roots retain downloads until the final switch.
    with tempfile.TemporaryDirectory(prefix='.arctic-update-', dir=PROFILE.parent) as folder:
        stage = Path(folder) / 'profile'
        run(nixlib.base() + ['profile', 'add', '--profile', str(stage), '--refresh', *refs])
        if plan(manifest(stage)) != refs:
            raise ValueError('The staged profile differs from the requested packages; refusing to switch.')
        if PROFILE.resolve(strict=True) != before:
            raise ValueError('The shared profile changed during the build; refusing to overwrite it.')
        target = stage.resolve(strict=True)
        if target.parent != Path('/nix/store'):
            raise ValueError('The staged profile is not a Nix store path.')
        # nix-env --set directly sets a store path as a generation; it does not
        # run nix-env --install or convert the modern manifest to legacy format.
        run(['/usr/bin/nix-env', '--store', 'daemon', '--profile', str(PROFILE), '--set', str(target)])
    print('Shared Nix packages updated. Restart running applications to use them.', flush=True)


def main(args):
    try:
        if args not in (['update'], ['rollback']):
            raise ValueError('usage: arctic-nix-system update|rollback')
        if os.geteuid() != 0:
            raise ValueError('Administrative authentication is required for the shared installer profile.')
        if re.search(r'(^|\s)rd\.live\.image(\s|$)', Path('/proc/cmdline').read_text()):
            raise ValueError('Shared Nix changes are unavailable on live media.')
        if (PROFILE.parent.resolve() != PROFILE.parent or PROFILE.parent.stat().st_uid != 0
                or PROFILE.parent.stat().st_mode & 0o022):
            raise ValueError('The shared profile directory must be root-owned and not writable by other users.')
        if (not PROFILE.is_symlink() or PROFILE.lstat().st_uid != 0
                or not re.fullmatch(r'default-[0-9]+-link', os.readlink(PROFILE))):
            raise ValueError('No supported shared installer profile is present.')
        # /run is root-owned. Serialize all Arctic administrative operations.
        with open('/run/arctic-nix-system.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args == ['update']:
                update()
            else:
                plan(manifest(PROFILE))  # Never take over a custom shared profile.
                run(nixlib.base() + ['profile', 'rollback', '--profile', str(PROFILE)])
                print('Shared Nix profile rolled back; application data was not changed.', flush=True)
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        print('arctic-nix-system: ' + str(exc), file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
