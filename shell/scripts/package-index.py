#!/usr/bin/env python3
"""Package names and summaries for Get apps, cached so opening it stays instant.

    package-index.py [--details] [--force]

Prints one JSON line right away with what is cached:
    {"packages": ["neovim", …, "flathub:org.gimp.GIMP", …], "refreshing": bool, "error": ""}
and, when the cache is missing or older than a day (or with --force), refreshes it and prints
a second line. `packages` is the Console's completion list. --details adds the rows the
Flathub and Fedora pages search:
    "details": {"dnf": [[name, repo, summary], …], "flathub": [[id, name, summary], …]}

Caches (tab-separated, one package or app per line), in ~/.cache/arctic/:
    packages.tsv   dnf packages: name, repository, summary
                   (dnf5 repoquery --available --qf "%{name}\\t%{repoid}\\t%{summary}\\n")
    flathub.tsv    Flathub apps: id, name, summary (flatpak remote-ls --app
                   --columns=application,name,description flathub, from the installation that
                   has the flathub remote), only when flatpak and that remote are there
The one-name-per-line caches of older shells (packages.txt, flathub.txt) are read when there is
no TSV yet; the screenshot tour seeds those.
"""
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'arctic'
DNF_CACHE = CACHE / 'packages.tsv'
FLATHUB_CACHE = CACHE / 'flathub.tsv'
OLD_CACHES = {DNF_CACHE: CACHE / 'packages.txt', FLATHUB_CACHE: CACHE / 'flathub.txt'}
MAX_AGE = 24 * 3600
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+@:-]*$')
FLATHUB_PREFIX = 'flathub:'


def read_rows(path):
    """Rows of a TSV cache (or of the old name-per-line cache), first field checked."""
    for candidate in (path, OLD_CACHES.get(path)):
        if candidate is None:
            continue
        try:
            text = candidate.read_text()
        except OSError:
            continue
        rows = []
        for line in text.splitlines():
            fields = [f.strip() for f in line.split('\t')]
            if fields and NAME.match(fields[0]):
                rows.append((fields + ['', ''])[:3])
        return rows
    return []


def fresh(path):
    try:
        return time.time() - path.stat().st_mtime < MAX_AGE
    except OSError:
        return False


def write_rows(path, rows):
    """Keep the first row per name (dnf lists one per architecture), sorted."""
    seen = {}
    for row in rows:
        seen.setdefault(row[0], row)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(''.join('\t'.join(seen[name]) + '\n' for name in sorted(seen)))
    temp.replace(path)


def query(command):
    result = subprocess.run(command, capture_output=True, text=True, timeout=600,
                            env=dict(os.environ, LC_ALL='C.UTF-8'))
    if result.returncode:
        raise RuntimeError((result.stderr or result.stdout).strip()[-300:] or 'failed')
    rows = []
    for line in result.stdout.splitlines():
        fields = [' '.join(f.split()) for f in line.split('\t')]
        if fields and NAME.match(fields[0]):
            rows.append((fields + ['', ''])[:3])
    return rows


def flathub_installation():
    """--system or --user: the installation that has the flathub remote (None: neither)."""
    for where in ('--system', '--user'):
        try:
            result = subprocess.run(['flatpak', 'remotes', where, '--columns=name'], capture_output=True,
                                    text=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode == 0 and 'flathub' in [l.split('\t')[0].strip() for l in result.stdout.splitlines()]:
            return where
    return None


def refresh():
    errors = []
    dnf = shutil.which('dnf5') or shutil.which('dnf')
    if dnf:
        try:
            write_rows(DNF_CACHE, query([dnf, '-q', 'repoquery', '--available', '--qf', '%{name}\t%{repoid}\t%{summary}\\n']))
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append('Could not read the dnf package list.')
            print('package-index: dnf: {}'.format(error), file=sys.stderr)
    if shutil.which('flatpak'):
        where = flathub_installation()
        if where:
            try:
                write_rows(FLATHUB_CACHE, query(['flatpak', 'remote-ls', where, '--app',
                                                 '--columns=application,name,description', 'flathub']))
            except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                errors.append('Could not read the Flathub app list.')
                print('package-index: flatpak: {}'.format(error), file=sys.stderr)
        else:
            write_rows(FLATHUB_CACHE, [])   # no Flathub here: nothing to list until it is added
    return ' '.join(errors)


def snapshot(refreshing, error='', details=False):
    dnf, flathub = read_rows(DNF_CACHE), read_rows(FLATHUB_CACHE)
    names = [r[0] for r in dnf] + [FLATHUB_PREFIX + r[0] for r in flathub]
    state = dict(packages=names, refreshing=refreshing, error=error)
    if details:
        state['details'] = dict(dnf=dnf, flathub=flathub)
    print(json.dumps(state, ensure_ascii=False, separators=(',', ':')), flush=True)


def main(args):
    details, force = '--details' in args, '--force' in args
    stale = force or not fresh(DNF_CACHE) or (shutil.which('flatpak') and not fresh(FLATHUB_CACHE))
    snapshot(bool(stale), details=details)
    if not stale:
        return
    CACHE.mkdir(parents=True, exist_ok=True)
    with (CACHE / 'packages.lock').open('w') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fcntl.flock(lock, fcntl.LOCK_EX)   # another refresh is running: wait for it
            snapshot(False, details=details)
            return
        error = refresh()
        snapshot(False, error, details)


if __name__ == '__main__':
    main(sys.argv[1:])
