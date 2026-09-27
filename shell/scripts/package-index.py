#!/usr/bin/env python3
"""Package names for the Get apps console's completion, cached so opening it stays instant.

    package-index.py

Prints one JSON line right away with what is cached:
    {"packages": ["neovim", …, "flathub:org.gimp.GIMP", …], "refreshing": bool, "error": ""}
and, when the cache is missing or older than a day, refreshes it and prints a second line.

Caches (plain text, one name per line), in ~/.cache/arctic/:
    packages.txt   dnf package names   (dnf5 repoquery --available --qf "%{name}\\n")
    flathub.txt    Flathub app ids     (flatpak remote-ls --app --columns=application flathub),
                   only when flatpak and its flathub remote are there
"""
import fcntl
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'arctic'
DNF_CACHE = CACHE / 'packages.txt'
FLATHUB_CACHE = CACHE / 'flathub.txt'
MAX_AGE = 24 * 3600


def read_list(path):
    try:
        return [line.strip() for line in path.read_text().splitlines() if line.strip()]
    except OSError:
        return []


def fresh(path):
    try:
        return time.time() - path.stat().st_mtime < MAX_AGE
    except OSError:
        return False


def write_list(path, names):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(''.join(n + '\n' for n in sorted(set(names))))
    temp.replace(path)


def query(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=600,
                            env=dict(os.environ, LC_ALL='C.UTF-8'))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-300:] or 'failed')
    return [line.strip() for line in result.stdout.splitlines() if line.strip() and ' ' not in line.strip()]


def refresh():
    errors = []
    dnf = shutil.which('dnf5') or shutil.which('dnf')
    if dnf:
        try:
            write_list(DNF_CACHE, query([dnf, '-q', 'repoquery', '--available', '--qf', '%{name}\\n']))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append('Could not read the dnf package list.')
            print('package-index: dnf: {}'.format(error), file=sys.stderr)
    if shutil.which('flatpak'):
        try:
            write_list(FLATHUB_CACHE, query(['flatpak', 'remote-ls', '--app', '--columns=application', 'flathub']))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            print('package-index: flatpak: {}'.format(error), file=sys.stderr)
    return ' '.join(errors)


def snapshot(refreshing, error=''):
    names = read_list(DNF_CACHE) + [FLATHUB_PREFIX + a for a in read_list(FLATHUB_CACHE)]
    print(json.dumps(dict(packages=names, refreshing=refreshing, error=error)), flush=True)


FLATHUB_PREFIX = 'flathub:'


def main():
    stale = not fresh(DNF_CACHE) or (shutil.which('flatpak') and not fresh(FLATHUB_CACHE))
    snapshot(bool(stale))
    if not stale:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / 'packages.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fcntl.flock(lock, fcntl.LOCK_EX)   # another refresh is running: wait for it
            snapshot(False)
            return
        error = refresh()
        snapshot(False, error)


if __name__ == '__main__':
    main()
