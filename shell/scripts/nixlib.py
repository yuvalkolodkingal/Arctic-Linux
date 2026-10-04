#!/usr/bin/env python3
"""Arctic's user-owned Nix profile. Never used as a privileged helper.

Nix itself is owned by Fedora RPMs. Profiles use Nix 2.34's version-3 manifest.
No caller can select a store, profile, executable, cache or arbitrary flake URL.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

NIX = '/usr/bin/nix'
SOURCE = 'github:NixOS/nixpkgs/nixos-26.05'
ATTR = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_+-]*(?:\.[A-Za-z0-9_][A-Za-z0-9_+-]*)*\Z')
NAME = re.compile(r'[A-Za-z0-9_][A-Za-z0-9_.+-]*\Z')
REVISION = re.compile(r'[0-9a-f]{40}\Z')


class Error(ValueError):
    pass


def profile():
    # Deliberately independent of XDG_STATE_HOME and NIX_PROFILE: session exports
    # and jobs always select the same user-owned profile, never nix-env's default.
    return Path.home() / '.local/state/nix/profiles/arctic'


def live():
    return os.environ.get('ARCTIC_FORCE_LIVE') == '1' or bool(
        re.search(r'(^|\s)rd\.live\.image(\s|$)', Path('/proc/cmdline').read_text()))


def base():
    return [NIX, '--extra-experimental-features', 'nix-command flakes', '--store', 'daemon']


def run_json(args, timeout=120):
    try:
        result = subprocess.run(base() + args, text=True, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise Error('Nix timed out. Check the network and daemon, then try again.') from exc
    if result.returncode:
        raise Error(result.stderr.strip()[-3000:] or 'Nix failed (exit {}).'.format(result.returncode))
    try:
        value = json.loads(result.stdout)
    except ValueError as exc:
        raise Error('Nix returned invalid JSON; no package state was inferred.') from exc
    if not isinstance(value, dict):
        raise Error('Unsupported Nix response.')
    return value


def installed():
    p = profile()
    if not p.exists() and not p.is_symlink():
        return []
    data = run_json(['profile', 'list', '--profile', str(p), '--json'], timeout=30)
    if data.get('version') != 3 or not isinstance(data.get('elements'), dict):
        raise Error('Unsupported Nix profile format. Arctic expects Nix 2.34 manifest version 3.')
    rows = []
    for name, item in data['elements'].items():
        if not NAME.fullmatch(name) or not isinstance(item, dict):
            raise Error('Unsupported Nix profile entry.')
        attr = item.get('attrPath', '')
        original, locked = item.get('originalUrl', ''), item.get('url', '')
        if not all(isinstance(v, str) for v in (attr, original, locked)):
            raise Error('Unsupported Nix profile reference.')
        paths = item.get('storePaths', [])
        if not isinstance(paths, list) or not all(isinstance(v, str) and v.startswith('/nix/store/') for v in paths):
            raise Error('Unsupported Nix store paths.')
        short = re.sub(r'^(legacyPackages|packages)\.[^.]+\.', '', attr)
        rows.append(dict(id=name, name=name, attr=short, source='nix', original=original,
                         locked=locked, store_paths=paths, active=item.get('active', True),
                         pinned=original != SOURCE, summary='Nix · Only you' +
                         (' · Pinned or externally managed source' if original != SOURCE else '')))
    return sorted(rows, key=lambda r: r['name'])


def search(query):
    query = query.strip()
    if not 2 <= len(query) <= 80 or any(ord(c) < 32 for c in query):
        raise Error('Enter 2–80 characters to search Nix packages.')
    data = run_json(['search', SOURCE, '--json', re.escape(query)], timeout=180)
    rows = []
    for key, item in data.items():
        attr = re.sub(r'^(legacyPackages|packages)\.[^.]+\.', '', key)
        if not ATTR.fullmatch(attr) or not isinstance(item, dict):
            continue
        rows.append(dict(id=attr, name=str(item.get('pname', attr)),
                         version=str(item.get('version', '')), source='nix',
                         summary=str(item.get('description', ''))))
    rows.sort(key=lambda r: (r['id'] != query, r['id']))
    return dict(items=rows[:200], total=len(rows), source=SOURCE)


def status():
    present = Path(NIX).is_file()
    return dict(present=present, live=live(), profile=str(profile()), source=SOURCE,
                free_bytes=shutil.disk_usage('/nix').free if Path('/nix').exists() else None)


def command(action, ids=(), revision=None):
    if action not in ('install', 'remove', 'update', 'rollback'):
        raise Error('Unsupported Nix action.')
    if action in ('install', 'remove'):
        pattern = ATTR if action == 'install' else NAME
        if not 1 <= len(ids) <= 50 or any(not isinstance(i, str) or not pattern.fullmatch(i) for i in ids):
            raise Error('Choose valid Nix package attributes or profile names.')
    elif ids:
        raise Error('This Nix action does not take package names.')
    if revision is not None and (action != 'install' or not REVISION.fullmatch(revision)):
        raise Error('A pin must be a full lowercase nixpkgs Git revision, used with install.')
    argv = base() + ['profile', {'install': 'add', 'update': 'upgrade'}.get(action, action),
                     '--profile', str(profile())]
    if action == 'install':
        source = 'github:NixOS/nixpkgs/' + revision if revision else SOURCE
        argv += [source + '#' + ident for ident in ids]
    elif action == 'remove':
        argv += list(ids)
    elif action == 'update':
        argv += ['--all', '--refresh']
    return argv


def check_profile(uid):
    p = profile()
    p.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not p.parent.resolve().is_relative_to(Path.home().resolve()) or p.parent.stat().st_uid != uid:
        raise Error('The Arctic Nix profile must be in your own home directory.')
    # A profile created here links to a generation next to it. Reject arbitrary
    # foreign-profile links, including a link into another user's writable home.
    if p.is_symlink() and not re.fullmatch(r'arctic-[0-9]+-link', os.readlink(p)):
        raise Error('The Arctic profile points outside its managed generations.')


def mutate(action, ids=(), revision=None):
    argv = command(action, ids, revision)
    if os.geteuid() == 0:
        raise Error('Run user Nix actions as your own account, without sudo or pkexec.')
    if live():
        raise Error('Nix package changes are available after installing Arctic to disk.')
    check_profile(os.geteuid())
    if action != 'install':
        rows = installed()
        if not rows and action != 'rollback':
            raise Error('Your Arctic Nix profile has no packages.')
        if action == 'remove' and not set(ids).issubset({r['id'] for r in rows}):
            raise Error('A selected Nix package is no longer in your profile. Refresh the list.')
        if action == 'update' and any(r['pinned'] for r in rows):
            print('Pinned or external inputs keep their existing update policy.', flush=True)
    result = subprocess.run(argv, check=False)
    if result.returncode:
        raise Error('Nix {} failed (exit {}). See the output above.'.format(action, result.returncode))
    print('Nix {} completed for your profile. Existing application data and older generations were kept.'.format(action), flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'search', 'list', 'install', 'remove', 'update', 'rollback'])
    parser.add_argument('ids', nargs='*')
    parser.add_argument('--revision')
    args = parser.parse_args(argv)
    try:
        if args.action in ('status', 'list') and (args.ids or args.revision):
            raise Error('This action does not take arguments.')
        if args.action == 'status':
            result = status()
        elif args.action == 'list':
            result = dict(apps=installed(), profile=str(profile()))
        elif args.action == 'search':
            if len(args.ids) != 1 or args.revision:
                raise Error('Pass one search string.')
            result = search(args.ids[0])
        else:
            mutate(args.action, args.ids, args.revision)
            return 0
        print(json.dumps(dict(ok=True, **result), ensure_ascii=False))
        return 0
    except (Error, OSError) as exc:
        print(json.dumps(dict(ok=False, error=str(exc)), ensure_ascii=False), flush=True)
        return 1


if __name__ == '__main__':
    sys.exit(main())
