#!/usr/bin/env python3
"""Get apps and Remove apps: what is installed, what an app would take along, catalogues.

Everything here runs as you, never with pkexec: listing, previews and metadata. Installs and
removals themselves are jobs of scripts/install-terminal.py (`run`), which builds their commands
with appslib.build_job.

    apps.py sources                       which sources work here (flatpak, dnf, web apps …)
    apps.py catalog flathub|fedora [--appstream FILE] [--tsv]
                                          app names, summaries and icons from AppStream
    apps.py info flatpak ID | info dnf NAME
    apps.py installed flatpak|dnf|terminal [--other]
    apps.py installed-ids                 ids of everything installed (for "Installed" chips)
    apps.py counts                        removable apps per source
    apps.py preview-remove dnf [--no-autoremove] PKG…
    apps.py preview-remove flatpak ID --installation system|user
    apps.py owner DESKTOP_ID              where a launcher entry came from, for Delete
    apps.py terminal-app add --name NAME --command CMD --window float|tile [--icon PNG]
    apps.py terminal-app remove ID
    apps.py launcher-entry remove DESKTOP_ID
    apps.py protected                     the protected-package patterns

Each command prints exactly one JSON line: {"ok": true, …} (exit 0), or {"ok": false,
"error": "<sentence>", "code": "<code>"} (exit 1); usage errors exit 2. `catalog … --tsv` is a
development hook for the screenshot tour: it prints `id<TAB>name<TAB>summary` lines instead.
"""
import grp
import gzip
import json
import os
import re
import secrets
import shlex
import shutil
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import appslib  # noqa: E402

HOME = Path.home()
DATA_HOME = Path(os.environ.get('XDG_DATA_HOME') or HOME / '.local/share')
CONFIG_HOME = Path(os.environ.get('XDG_CONFIG_HOME') or HOME / '.config')
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or HOME / '.cache') / 'arctic'
RUNTIME = Path(os.environ.get('XDG_RUNTIME_DIR') or '/tmp')
DATA_DIRS = [Path(d) for d in (os.environ.get('XDG_DATA_DIRS') or '/usr/local/share:/usr/share').split(':') if d]
# Test and screenshot hooks (the real paths otherwise).
SWCATALOG = Path(os.environ.get('ARCTIC_SWCATALOG') or '/usr/share/swcatalog')
FLATPAK_SYSTEM = Path(os.environ.get('ARCTIC_FLATPAK_SYSTEM_DIR') or '/var/lib/flatpak')
FLATPAK_USER = DATA_HOME / 'flatpak'
RPMDB = Path(os.environ.get('ARCTIC_RPMDB') or '/usr/lib/sysimage/rpm/rpmdb.sqlite')
INSTALL_MARK = Path(os.environ.get('ARCTIC_INSTALL_MARK') or '/var/log/arctic-install')
DEFAULT_APPS = [Path(os.environ.get('ARCTIC_DEFAULT_APPS') or '/etc/arctic/default-apps'),
                CONFIG_HOME / 'arctic/default-apps']
SNAPPER_ROOT = Path(os.environ.get('ARCTIC_SNAPPER_ROOT') or '/etc/snapper/configs/root')
WEBAPP = os.environ.get('ARCTIC_WEBAPP_CMD') or 'arctic-webapp'
WEBAPP_PREFIX = 'org.arcticlinux.WebApp.'
TERMINAL_PREFIX = 'org.arcticlinux.TerminalApp.'
REPO_LABELS = (('fedora', 'Fedora'), ('updates', 'Fedora'), ('rpmfusion-', 'RPM Fusion'),
               ('copr:', 'COPR'), ('arctic', 'Arctic Linux'))
ROLE_LABELS = dict(browser='web browser', terminal='terminal', editor='text editor', files='file manager',
                   video='video player', music='music player', images='picture viewer', pdf='PDF viewer')
ROLE_WHAT = dict(browser='your web links', terminal='your terminal windows', editor='your text files',
                 files='your folders', video='your videos', music='your music', images='your pictures',
                 pdf='your PDF documents')


class Failure(Exception):
    def __init__(self, message, code='failed'):
        super().__init__(message)
        self.code = code


def out(data):
    print(json.dumps(dict(ok=True, **data), ensure_ascii=False, separators=(',', ':')), flush=True)


def usage(message):
    print(json.dumps(dict(ok=False, error=message, code='usage'), ensure_ascii=False), flush=True)
    sys.exit(2)


def repo_label(repo):
    for prefix, label in REPO_LABELS:
        if repo == prefix or (prefix.endswith(('-', ':')) and repo.startswith(prefix)) or repo.startswith(prefix + '-'):
            return label
    return repo or ''


def stamp(path):
    try:
        st = Path(path).stat()
        return '{:.6f}'.format(st.st_mtime)
    except OSError:
        return ''


def cmdline_live():
    if os.environ.get('ARCTIC_FORCE_LIVE') == '1':
        return True
    try:
        return re.search(r'(^|\s)rd\.live\.image(\s|$)', Path('/proc/cmdline').read_text()) is not None
    except OSError:
        return False


def in_wheel():
    forced = os.environ.get('ARCTIC_WHEEL')
    if forced in ('0', '1'):
        return forced == '1'
    try:
        gid = grp.getgrnam('wheel').gr_gid
    except KeyError:
        return False
    return gid in os.getgroups() or os.getgid() == gid


def default_roles():
    roles = {}
    for path in DEFAULT_APPS:
        try:
            text = path.read_text()
        except OSError:
            continue
        for line in text.splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                roles[key.strip()] = value.strip()
    return roles


def role_targets(command):
    """(desktop id, program) a role=command line opens."""
    words = command.split()
    if not words:
        return '', ''
    if words[0] == 'gtk-launch' and len(words) > 1:
        return words[1], ''
    program = os.path.basename(words[0])
    if program in appslib.TERMINALS and '-e' in words and words.index('-e') + 1 < len(words):
        return '', os.path.basename(words[words.index('-e') + 1])
    return '', program


# ---- sources ----------------------------------------------------------------------------------

def webapp_present():
    return shutil.which(WEBAPP) is not None


def cmd_sources(_args):
    flatpak = shutil.which('flatpak') is not None
    flathub = appslib.flathub_installations() if flatpak else dict(system=False, user=False)
    wheel = in_wheel()
    files = [str(p) for p in fedora_catalog_files()]
    out(dict(live=cmdline_live(), wheel=wheel,
             flatpak=dict(present=flatpak, flathub=flathub, install_to='system' if wheel else 'user'),
             dnf=dict(present=shutil.which('dnf5') is not None),
             fedora_catalog=dict(present=bool(files), files=files),
             webapp=dict(present=webapp_present(), command=WEBAPP),
             snapshots=SNAPPER_ROOT.exists()))


# ---- AppStream catalogues ---------------------------------------------------------------------

LANG = '{http://www.w3.org/XML/1998/namespace}lang'


def fedora_catalog_files():
    folder = SWCATALOG / 'xml'
    try:
        return sorted(p for p in folder.iterdir() if p.name.endswith(('.xml', '.xml.gz')))
    except OSError:
        return []


def flathub_appstream():
    """(appstream file, icon folder) of the first installation with a flathub checkout."""
    arch = os.uname().machine
    for base in (FLATPAK_SYSTEM, FLATPAK_USER):
        active = base / 'appstream/flathub' / arch / 'active'
        for name in ('appstream.xml.gz', 'appstream.xml'):
            if (active / name).is_file():
                return active / name, active / 'icons'
    return None, None


def _text(element, tag):
    for child in element.findall(tag):
        if child.get(LANG) is None:
            return ' '.join((child.text or '').split())
    return ''


def parse_appstream(path, icon_root=None, origin_icons=None):
    """Desktop apps in one AppStream XML file (gzip or plain)."""
    items = []
    opener = gzip.open if str(path).endswith('.gz') else open
    with opener(path, 'rb') as handle:
        origin = ''
        for event, element in ET.iterparse(handle, events=('start', 'end')):
            if event == 'start':
                if element.tag == 'components':
                    origin = element.get('origin') or ''
                continue
            if element.tag != 'component':
                continue
            if element.get('type') not in ('desktop-application', 'desktop'):
                element.clear()
                continue
            ident = (element.findtext('id') or '').strip()
            name = _text(element, 'name')
            if not ident or not name:
                element.clear()
                continue
            item = dict(id=ident[:-8] if ident.endswith('.desktop') else ident, name=name,
                        summary=_text(element, 'summary'),
                        categories=[c.text.strip() for c in element.findall('categories/category') if c.text],
                        keywords=[k.text.strip() for k in element.findall('keywords/keyword')
                                  if k.text and k.get(LANG) is None][:12])
            pkg = (element.findtext('pkgname') or '').strip()
            if pkg:
                item['pkg'] = pkg
            developer = _text(element, 'developer_name') or _text(element, 'developer/name')
            if developer:
                item['developer'] = developer
            license_ = (element.findtext('project_license') or '').strip()
            if license_:
                item['license'] = license_
            for url in element.findall('url'):
                if url.get('type') == 'homepage' and url.text:
                    item['homepage'] = url.text.strip()
                    break
            paragraphs = [' '.join(''.join(p.itertext()).split()) for p in element.findall('description/p')
                          if p.get(LANG) is None][:3]
            if paragraphs:
                item['description'] = paragraphs
            item['verified'] = any(v.get('key') == 'flathub::verification::verified' and (v.text or '').strip() == 'true'
                                   for v in element.findall('custom/value'))
            icon = ''
            for kind in ('cached', 'stock'):
                for node in element.findall('icon'):
                    if node.get('type') != kind or not node.text:
                        continue
                    if kind == 'stock':
                        icon = node.text.strip()
                        break
                    roots = [icon_root] if icon_root else [SWCATALOG / 'icons' / origin] if origin else []
                    for root in roots:
                        for size in ('128x128', '64x64'):
                            candidate = Path(root) / size / node.text.strip()
                            if candidate.is_file():
                                icon = str(candidate)
                                break
                        if icon:
                            break
                    if icon:
                        break
                if icon:
                    break
            item['icon'] = icon
            items.append(item)
            element.clear()
    return items


def cached_catalog(source, files, parse):
    key = [[str(f), f.stat().st_mtime_ns, f.stat().st_size] for f in files]
    cache = CACHE / 'appstream-{}.json'.format(source)
    try:
        data = json.loads(cache.read_text())
        if data.get('key') == key:
            return data['items']
    except (OSError, ValueError, KeyError, AttributeError):
        pass
    items = parse()
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        temp = cache.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(key=key, items=items), ensure_ascii=False))
        temp.replace(cache)
    except OSError:
        pass
    return items


def known_packages():
    """dnf names that are available (the package index cache) or installed; None: unknown."""
    names = set()
    for path in (CACHE / 'packages.tsv', CACHE / 'packages.txt'):
        try:
            names.update(line.split('\t', 1)[0].strip() for line in path.read_text().splitlines() if line.strip())
            break
        except OSError:
            continue
    if not names:
        return None
    code, text, _err = appslib.run(['rpm', '-qa', '--qf', '%{NAME}\\n'], timeout=30)
    if code == 0:
        names.update(text.split())
    return names


def cmd_catalog(args):
    if not args or args[0] not in ('flathub', 'fedora'):
        usage('usage: apps.py catalog flathub|fedora [--appstream FILE] [--tsv]')
    source, rest = args[0], args[1:]
    tsv = '--tsv' in rest
    given = rest[rest.index('--appstream') + 1] if '--appstream' in rest and rest.index('--appstream') + 1 < len(rest) else ''
    if given:
        items = parse_appstream(given)
    elif source == 'flathub':
        path, icons = flathub_appstream()
        if not path:
            return out(dict(source=source, items=[], missing=True))
        items = cached_catalog(source, [path], lambda: parse_appstream(path, icons))
    else:
        files = fedora_catalog_files()
        if not files:
            return out(dict(source=source, items=[], missing=True))
        items = cached_catalog(source, files, lambda: [i for f in files for i in parse_appstream(f) if i.get('pkg')])
        known = known_packages()
        if known is not None:
            items = [i for i in items if i['pkg'] in known]
        seen = set()
        items = [i for i in items if not (i['id'] in seen or seen.add(i['id']))]
    if tsv:
        for item in items:
            print('\t'.join([item['id'], item['name'], item.get('summary', '')]))
        return None
    items.sort(key=lambda i: i['name'].lower())
    return out(dict(source=source, items=items, missing=False))


# ---- details ----------------------------------------------------------------------------------

def parse_size(text):
    m = re.match(r'^\s*([\d.,]+)\s*([kKMGT]?i?B|bytes)?', text or '')
    if not m:
        return None
    number = float(m.group(1).replace(',', ''))
    unit = (m.group(2) or 'B').replace('i', '').upper()
    return int(number * {'B': 1, 'BYTES': 1, 'KB': 1e3, 'MB': 1e6, 'GB': 1e9, 'TB': 1e12}.get(unit, 1))


def cmd_info(args):
    if len(args) != 2 or args[0] not in ('flatpak', 'dnf'):
        usage('usage: apps.py info flatpak ID | info dnf NAME')
    source, ident = args
    if source == 'dnf':
        if not appslib.NAME.match(ident):
            raise Failure('That isn’t a package name.', 'invalid')
        qf = '\t'.join(['%{name}', '%{evr}', '%{repoid}', '%{downloadsize}', '%{installsize}', '%{license}',
                        '%{url}', '%{summary}', '%{description}']) + '\\n\x1e\\n'
        code, text, err = appslib.run(['dnf5', '-q', 'repoquery', '--latest-limit=1', '--qf', qf, ident], timeout=120)
        record = next((r.strip('\n') for r in text.split('\x1e') if r.strip()), '')
        fields = record.split('\t', 8)
        if code != 0 or len(fields) < 9:
            raise Failure('Get apps couldn’t read the details of {}.'.format(ident), 'not-found')
        name, evr, repo, download, install, license_, url, summary, description = fields
        return out(dict(name=name, evr=evr, repo=repo, repo_label=repo_label(repo),
                        download_bytes=int(download) if download.isdigit() else None,
                        install_bytes=int(install) if install.isdigit() else None,
                        license=license_, url=url, summary=summary, description=description.strip()))
    if not appslib.FLATPAK_ID.match(ident):
        raise Failure('That isn’t a Flatpak app id.', 'invalid')
    flathub = appslib.flathub_installations()
    where = 'system' if flathub['system'] or not flathub['user'] else 'user'
    code, text, _err = appslib.run(['flatpak', 'remote-info', '--' + where, 'flathub', ident], timeout=60)
    if code != 0:
        raise Failure('Get apps couldn’t read the details of {}. Are you online?'.format(ident), 'offline')
    facts = {}
    for line in text.splitlines():
        key, sep, value = line.strip().partition(':')
        if sep:
            facts[key.strip().lower()] = value.strip()
    return out(dict(id=ident, version=facts.get('version', ''), license=facts.get('license', ''),
                    download_bytes=parse_size(facts.get('download')), install_bytes=parse_size(facts.get('installed'))))


# ---- installed apps ---------------------------------------------------------------------------

def flatpak_exports(installation):
    base = FLATPAK_SYSTEM if installation == 'system' else FLATPAK_USER
    return base / 'exports/share/applications'


def installed_flatpaks():
    if not shutil.which('flatpak'):
        return []
    code, text, _err = appslib.run(['flatpak', 'list', '--app', '--columns=application,name,version,origin,installation,size'], timeout=60)
    if code != 0:
        raise Failure('Get apps couldn’t list your Flatpak apps.', 'flatpak')
    apps = []
    for line in text.splitlines():
        fields = line.split('\t')
        if len(fields) < 6 or not appslib.FLATPAK_ID.match(fields[0].strip()):
            continue
        ident, name, version, origin, installation, size = (f.strip() for f in fields[:6])
        entry = appslib.read_desktop(flatpak_exports(installation) / (ident + '.desktop'))
        apps.append(dict(id=ident, name=entry.get('Name') or name or ident, version=version, origin=origin,
                         installation=installation, size_text=size, icon=entry.get('Icon') or ident,
                         desktop_id=ident, data_path=str(HOME / '.var/app' / ident)))
    apps.sort(key=lambda a: (a['name'].lower(), a['installation']))
    return apps


def system_desktop_dirs():
    """applications folders of XDG_DATA_DIRS, without Flatpak exports, /nix and your own."""
    dirs = []
    for d in DATA_DIRS:
        text = str(d)
        if 'flatpak/exports' in text or text.startswith('/nix') or d == DATA_HOME:
            continue
        dirs.append(d / 'applications')
    return dirs


def rpm_owners(paths):
    """{path: [package, …]} for the rpm-owned ones among `paths`."""
    owners = {}
    if not paths:
        return owners
    wanted = set(paths)
    code, text, _err = appslib.run(['rpm', '-qf', '--qf', '[%{FILENAMES}\t%{=NAME}\n]', '--', *paths], timeout=60)
    if code == 127:
        return owners
    for line in text.splitlines():
        path, sep, name = line.partition('\t')
        if sep and path in wanted and name not in owners.setdefault(path, []):
            owners[path].append(name)
    return owners


def package_facts(names=None):
    """{name: {reason, repo, installtime, install_bytes, evr, summary}} of installed packages."""
    qf = '\t'.join(['%{name}', '%{reason}', '%{from_repo}', '%{installtime}', '%{installsize}', '%{evr}', '%{summary}']) + '\\n'
    code, text, _err = appslib.run(['dnf5', '-q', 'repoquery', '--installed', '--qf', qf, *(names or [])], timeout=120)
    facts = {}
    if code != 0:
        return facts
    for line in text.splitlines():
        fields = line.split('\t')
        if len(fields) < 7 or fields[0] in facts:
            continue
        name, reason, repo, when, size, evr, summary = fields[:7]
        facts[name] = dict(reason=reason, repo=repo, installtime=int(when) if when.isdigit() else 0,
                           install_bytes=int(size) if size.isdigit() else None, evr=evr, summary=summary)
    return facts


def desktop_closure():
    """Packages the Arctic desktop needs (the hard Requires of arctic-desktop, recursively),
    cached per rpmdb change."""
    cache = CACHE / 'desktop-closure.json'
    key = stamp(RPMDB)
    try:
        data = json.loads(cache.read_text())
        if key and data.get('key') == key:
            return set(data['names'])
    except (OSError, ValueError, KeyError):
        pass
    code, text, _err = appslib.run(['dnf5', '-q', 'repoquery', '--installed', '--providers-of=requires', '--recursive',
                                    '--qf', '%{name}\\n', 'arctic-desktop'], timeout=120)
    names = sorted(set(text.split())) if code == 0 else []
    if code == 0 and key:
        try:
            CACHE.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(dict(key=key, names=names)))
        except OSError:
            pass
    return set(names)


def login_shell_package():
    user = os.environ.get('USER') or ''
    code, text, _err = appslib.run(['getent', 'passwd', user], timeout=10) if user else (1, '', '')
    shell = text.strip().split(':')[6] if code == 0 and text.count(':') >= 6 else ''
    if not shell:
        return '', ''
    real = os.path.realpath(shell)
    owners = rpm_owners([real]).get(real) or rpm_owners([shell]).get(shell) or ['']
    return owners[0], os.path.basename(shell)


def protection_reason(name, display, protected, closure, shell_pkg):
    if protected.match(name):
        return 'protected', '{} is part of Arctic Linux.'.format(display)
    if name in closure:
        return 'needed-by-desktop', 'The Arctic desktop needs {}.'.format(display)
    if name == shell_pkg:
        return 'login-shell', '{} is your login shell.'.format(display)
    return '', ''


def installed_dnf(other=False):
    """(removable rows, protected rows), cached until the rpm database, the launcher entry
    folders, the default apps, the protection lists or your shell change."""
    rpmdb = stamp(RPMDB)
    key = None
    if rpmdb:
        watched = [str(d) for d in system_desktop_dirs()] + [str(p) for p in DEFAULT_APPS] + \
                  [str(INSTALL_MARK), str(appslib.PROTECTED_FILE), str(appslib.PROTECTED_DIR)]
        key = [rpmdb, other, os.environ.get('USER', ''), [[w, stamp(w)] for w in watched]]
        cache = CACHE / 'installed-dnf.json'
        try:
            data = json.loads(cache.read_text())
            if data.get(str(other)) and data[str(other)].get('key') == key:
                return data[str(other)]['apps'], data[str(other)]['protected']
        except (OSError, ValueError, AttributeError):
            pass
    apps, blocked = scan_installed_dnf(other)
    if key is not None:
        try:
            try:
                data = json.loads((CACHE / 'installed-dnf.json').read_text())
            except (OSError, ValueError):
                data = {}
            data[str(other)] = dict(key=key, apps=apps, protected=blocked)
            CACHE.mkdir(parents=True, exist_ok=True)
            temp = CACHE / 'installed-dnf.tmp'
            temp.write_text(json.dumps(data, ensure_ascii=False))
            temp.replace(CACHE / 'installed-dnf.json')
        except OSError:
            pass
    return apps, blocked


def scan_installed_dnf(other=False):
    entries = appslib.desktop_entries(system_desktop_dirs())
    owners = rpm_owners([e['path'] for e in entries.values()])
    by_package = {}
    for entry in entries.values():
        for name in owners.get(entry['path'], []):
            by_package.setdefault(name, []).append(entry)
    facts = package_facts()
    try:
        mark = INSTALL_MARK.stat().st_mtime
    except OSError:
        mark = None
    protected = appslib.protection()
    closure = desktop_closure()
    shell_pkg, _shell = login_shell_package()
    roles = default_roles()
    apps, blocked = [], []
    names = sorted(facts) if other else sorted(by_package)
    for name in names:
        fact = facts.get(name, {})
        found = by_package.get(name, [])
        if other:
            if found or fact.get('reason') != 'User' or mark is None or fact.get('installtime', 0) <= mark:
                continue
            if protected.match(name) or name in closure:
                continue
        visible = [e for e in found if not e['nodisplay']]
        if not other and not visible:
            continue
        main = next((e for e in visible if e['id'] == name or e['id'].lower().endswith('.' + name.lower())), visible[0] if visible else None)
        display = main['name'] if main else name
        row = dict(package=name, evr=fact.get('evr', ''), name=display, summary=fact.get('summary', ''),
                   desktop_ids=[e['id'] for e in visible], icon=main['icon'] if main else '',
                   repo=fact.get('repo', ''), repo_label=repo_label(fact.get('repo', '')),
                   install_bytes=fact.get('install_bytes'))
        if mark is not None and fact:
            row['added'] = 'you' if fact.get('reason') == 'User' and fact.get('installtime', 0) > mark else 'arctic'
        programs = {appslib.exec_program(e) for e in found}
        row['roles'] = sorted(role for role, command in roles.items()
                              if (lambda t: t[0] in row['desktop_ids'] or (t[1] and t[1] in programs))(role_targets(command)))
        code, message = protection_reason(name, display, protected, closure, shell_pkg)
        row.update(protected=bool(code), protected_reason=code, message=message)
        (blocked if code else apps).append(row)
    apps.sort(key=lambda r: r['name'].lower())
    blocked.sort(key=lambda r: r['name'].lower())
    return apps, blocked


def terminal_apps():
    folder = DATA_HOME / 'applications'
    apps = []
    try:
        paths = sorted(folder.glob(TERMINAL_PREFIX + '*.desktop'))
    except OSError:
        paths = []
    for path in paths:
        entry = appslib.read_desktop(path)
        ident = entry.get('X-Arctic-TerminalApp-Id')
        if not ident:
            continue
        apps.append(dict(id=ident, name=entry.get('Name', ident), command=entry.get('X-Arctic-TerminalApp-Command', ''),
                         window=entry.get('X-Arctic-TerminalApp-Window', 'float'), icon=entry.get('Icon', ''),
                         desktop_file=str(path)))
    return apps


def cmd_installed(args):
    if not args or args[0] not in ('flatpak', 'dnf', 'terminal'):
        usage('usage: apps.py installed flatpak|dnf|terminal [--other]')
    if args[0] == 'flatpak':
        return out(dict(source='flatpak', apps=installed_flatpaks()))
    if args[0] == 'terminal':
        return out(dict(source='terminal', apps=terminal_apps()))
    apps, blocked = installed_dnf(other='--other' in args[1:])
    return out(dict(source='dnf', apps=apps, protected=blocked))


def cmd_installed_ids(_args):
    flatpaks = dict(system=[], user=[])
    for app in installed_flatpaks():
        flatpaks.setdefault(app['installation'], []).append(app['id'])
    code, text, _err = appslib.run(['rpm', '-qa', '--qf', '%{NAME}\\n'], timeout=60)
    out(dict(flatpak=flatpaks, dnf=sorted(set(text.split())) if code == 0 else []))


def webapp_list():
    if not webapp_present():
        return None
    code, text, _err = appslib.run([WEBAPP, 'list', '--json'], timeout=30)
    try:
        data = json.loads(text.strip().splitlines()[-1]) if code == 0 and text.strip() else {}
    except ValueError:
        data = {}
    return data.get('apps') if data.get('ok') else None


def cmd_counts(_args):
    web = webapp_list()
    try:
        flatpaks = len(installed_flatpaks())
    except Failure:
        flatpaks = 0
    out(dict(flatpak=flatpaks, dnf=len(installed_dnf()[0]) if shutil.which('rpm') else 0,
             web=len(web) if web is not None else 0, terminal=len(terminal_apps())))


# ---- removal previews -------------------------------------------------------------------------

def split_nevra(nevra):
    """name, evr of "gimp-2:3.0.4-1.fc44.x86_64" (the epoch may be missing)."""
    base = nevra.rsplit('.', 1)[0] if re.search(r'\.[A-Za-z0-9_]+$', nevra) else nevra
    parts = base.rsplit('-', 2)
    if len(parts) < 3:
        return base, ''
    name, version, release = parts
    return name, version + '-' + release


WHY = {'User': 'asked', 'Dependency': 'needs-it', 'Clean': 'unused'}


def installed_sizes(names):
    code, text, _err = appslib.run(['rpm', '-q', '--qf', '%{NAME}\t%{SIZE}\\n', *names], timeout=30)
    sizes = {}
    for line in text.splitlines():
        name, sep, size = line.partition('\t')
        if sep and size.strip().isdigit():
            sizes[name] = int(size)
    return sizes


def preview_dnf(names, autoremove):
    for name in names:
        if not appslib.NAME.match(name):
            raise Failure('“{}” isn’t a package name.'.format(name), 'invalid')
    folder = RUNTIME / 'arctic-apps' / ('remove-' + secrets.token_hex(8))
    folder.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        code, text, err = appslib.run(['dnf5', 'remove', '--store=' + str(folder), '-y',
                                       *([] if autoremove else ['--no-autoremove']), *names], timeout=300)
        combined = text + '\n' + err
        if code != 0:
            if 'protected packages' in combined or 'protected package' in combined:
                return None, combined
            last = [l.strip() for l in combined.splitlines() if l.strip()]
            raise Failure('dnf couldn’t work out this removal: {}'.format(last[-1] if last else 'it failed'), 'dnf')
        try:
            data = json.loads((folder / 'transaction.json').read_text())
        except (OSError, ValueError):
            raise Failure('{} isn’t installed.'.format(', '.join(names)), 'not-installed') from None
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    packages = []
    for rpm in data.get('rpms', []):
        if rpm.get('action') != 'Remove':
            continue
        name, evr = split_nevra(rpm.get('nevra', ''))
        why = 'asked' if name in names else WHY.get(rpm.get('reason'), 'needs-it')
        packages.append(dict(name=name, evr=evr, why=why))
    order = {'asked': 0, 'needs-it': 1, 'unused': 2}
    packages.sort(key=lambda p: (order[p['why']], p['name']))
    return packages, ''


def cmd_preview_remove(args):
    if not args or args[0] not in ('dnf', 'flatpak'):
        usage('usage: apps.py preview-remove dnf [--no-autoremove] PKG… | flatpak ID --installation system|user')
    if args[0] == 'flatpak':
        return preview_flatpak(args[1:])
    rest = args[1:]
    autoremove = '--no-autoremove' not in rest
    names = [a for a in rest if a != '--no-autoremove']
    if not names:
        usage('usage: apps.py preview-remove dnf [--no-autoremove] PKG…')
    protected = appslib.protection()
    result = dict(source='dnf', request=names, autoremove=autoremove, rpmdb=stamp(RPMDB),
                  packages=[], frees_bytes=0, blocked=None, warnings=[], undo=SNAPPER_ROOT.exists())
    for name in names:
        if protected.match(name):
            result['blocked'] = dict(package=name, code='protected',
                                     message='{} is part of Arctic Linux, so it can’t be removed.'.format(name))
            return out(result)
    packages, refusal = preview_dnf(names, autoremove)
    if packages is None:
        result['blocked'] = dict(package='', code='protected',
                                 message='dnf won’t remove {}: the system needs it.'.format(', '.join(names)))
        return out(result)
    sizes = installed_sizes([p['name'] for p in packages]) if packages else {}
    for p in packages:
        p['install_bytes'] = sizes.get(p['name'])
    result['packages'] = packages
    result['frees_bytes'] = sum(p['install_bytes'] or 0 for p in packages)
    removed = {p['name'] for p in packages}
    asked = ', '.join(names)
    for p in packages:
        if protected.match(p['name']):
            result['blocked'] = dict(package=p['name'], code='protected',
                                     message='Removing {} would also remove {}, which Arctic Linux needs.'.format(asked, p['name']))
            return out(result)
    shell_pkg, shell_name = login_shell_package()
    if shell_pkg and shell_pkg in removed:
        result['blocked'] = dict(package=shell_pkg, code='login-shell',
                                 message='{} is your login shell. Choose another shell first (see Terminal and shell).'.format(shell_name))
        return out(result)
    code, text, _err = appslib.run(['rpm', '-q', '--qf', '%{NAME}\\n', *appslib.TERMINALS], timeout=10)
    terminals = [t for t in text.split() if t in appslib.TERMINALS]
    if terminals and all(t in removed for t in terminals):
        keys = appslib.role_keys().get('terminal', 'Super + Enter')
        result['blocked'] = dict(package=terminals[0], code='only-terminal',
                                 message='{} is your only terminal, so {} would stop working. Install another terminal first.'.format(terminals[0], keys))
        return out(result)
    entries = appslib.desktop_entries(system_desktop_dirs())
    owned = rpm_owners([e['path'] for e in entries.values()])
    ids = {e['id'] for e in entries.values() if set(owned.get(e['path'], [])) & removed}
    programs = {appslib.exec_program(e): e for e in entries.values() if set(owned.get(e['path'], [])) & removed}
    keys = appslib.role_keys()
    for role, command in sorted(default_roles().items()):
        desktop_id, program = role_targets(command)
        entry = next((e for e in entries.values() if e['id'] == desktop_id), None) if desktop_id in ids else programs.get(program)
        if not entry:
            continue
        key = keys.get(role)
        what = ROLE_WHAT.get(role, 'your {} files'.format(role))
        message = '{} opens {}{}. Choose another {} in Settings → Default apps after removing it.'.format(
            entry['name'], what, ' and ' + key if key else '', ROLE_LABELS.get(role, 'app'))
        result['warnings'].append(dict(code='default-app', role=role, message=message))
    return out(result)


def folder_size(path, budget=2.0):
    """Bytes under `path`, giving up (None) after `budget` seconds."""
    total, deadline, stack = 0, time.monotonic() + budget, [str(path)]
    while stack:
        if time.monotonic() > deadline:
            return None
        try:
            with os.scandir(stack.pop()) as it:
                for item in it:
                    try:
                        if item.is_dir(follow_symlinks=False):
                            stack.append(item.path)
                        else:
                            total += item.stat(follow_symlinks=False).st_size
                    except OSError:
                        pass
        except OSError:
            pass
    return total


def preview_flatpak(args):
    if not args or not appslib.FLATPAK_ID.match(args[0]):
        raise Failure('That isn’t a Flatpak app id.', 'invalid')
    ident = args[0]
    installation = args[args.index('--installation') + 1] if '--installation' in args and args.index('--installation') + 1 < len(args) else 'system'
    if installation not in appslib.INSTALLATIONS:
        raise Failure('Flatpak apps are installed for the system or for you.', 'invalid')
    entry = appslib.read_desktop(flatpak_exports(installation) / (ident + '.desktop'))
    data = HOME / '.var/app' / ident
    return out(dict(source='flatpak', id=ident, name=entry.get('Name') or ident, installation=installation,
                    data_path=str(data), data_bytes=folder_size(data) if data.is_dir() else 0))


# ---- owners of launcher entries ---------------------------------------------------------------

def desktop_search_dirs():
    return [DATA_HOME / 'applications'] + [d / 'applications' for d in DATA_DIRS]


def find_desktop(desktop_id):
    """(folder, path) of a desktop id in XDG order; the real path stays inside its folder."""
    if not re.match(r'^[A-Za-z0-9_][A-Za-z0-9._+-]*$', desktop_id or ''):
        raise Failure('That isn’t a launcher entry.', 'invalid')
    for folder in desktop_search_dirs():
        candidates = [folder / (desktop_id + '.desktop')]
        parts = desktop_id.split('-')
        for i in range(1, len(parts)):
            candidates.append(folder.joinpath(*parts[:i]) / ('-'.join(parts[i:]) + '.desktop'))
        for path in candidates:
            if not path.is_file():
                continue
            real, root = os.path.realpath(path), os.path.realpath(folder)
            if not real.startswith(root + os.sep):
                continue
            return folder, path
    return None, None


def owner_of(desktop_id):
    folder, path = find_desktop(desktop_id)
    if not path:
        raise Failure('Arctic Linux can’t find that app’s launcher entry.', 'not-found')
    entry = appslib.read_desktop(path)
    name = entry.get('Name') or desktop_id
    result = dict(desktop_id=desktop_id, name=name, icon=entry.get('Icon', ''), path=str(path),
                  source='unknown', target={}, blocked=None)
    text = str(path)
    if desktop_id.startswith(WEBAPP_PREFIX) or entry.get('X-Arctic-WebApp-Id'):
        result.update(source='webapp', target=dict(id=entry.get('X-Arctic-WebApp-Id') or desktop_id))
    elif entry.get('X-Arctic-TerminalApp-Id'):
        result.update(source='terminal-app', target=dict(id=entry['X-Arctic-TerminalApp-Id']))
    elif 'flatpak/exports/share/applications' in text or entry.get('X-Flatpak'):
        installation = 'user' if text.startswith(str(FLATPAK_USER)) else 'system'
        result.update(source='flatpak', target=dict(id=entry.get('X-Flatpak') or desktop_id, installation=installation))
    elif folder == DATA_HOME / 'applications':
        overrides = any((d / 'applications' / (desktop_id + '.desktop')).is_file() for d in DATA_DIRS)
        result.update(source='launcher', target=dict(path=text, overrides=overrides))
    elif text.startswith('/nix/') or os.path.realpath(text).startswith('/nix/'):
        result.update(source='nix', target=dict(name=name))
    else:
        owners = rpm_owners([text]).get(text, [])
        if owners:
            package = owners[0]
            result.update(source='dnf', target=dict(package=package))
            if cmdline_live():
                result['blocked'] = dict(code='live', message='Apps can’t be removed while you’re trying Arctic Linux.')
            else:
                shell_pkg, _ = login_shell_package()
                code, message = protection_reason(package, name, appslib.protection(), desktop_closure(), shell_pkg)
                if code:
                    result['blocked'] = dict(code=code, message=message)
        else:
            result['blocked'] = dict(code='unknown', message='Arctic Linux can’t tell where {} came from.'.format(name))
    return result


def cmd_owner(args):
    if len(args) != 1:
        usage('usage: apps.py owner DESKTOP_ID')
    out(owner_of(args[0]))


def cmd_launcher_entry(args):
    if len(args) != 2 or args[0] != 'remove':
        usage('usage: apps.py launcher-entry remove DESKTOP_ID')
    found = owner_of(args[1])
    if found['source'] != 'launcher':
        raise Failure('That launcher entry isn’t one of your own.', 'not-yours')
    Path(found['path']).unlink()
    out(dict(removed=found['path']))


# ---- terminal apps ----------------------------------------------------------------------------

def cmd_terminal_app(args):
    if not args or args[0] not in ('add', 'remove'):
        usage('usage: apps.py terminal-app add --name NAME --command CMD --window float|tile [--icon PNG] | remove ID')
    if args[0] == 'remove':
        if len(args) != 2 or not args[1].startswith(TERMINAL_PREFIX) or not re.match(r'^[A-Za-z0-9._]+$', args[1]):
            raise Failure('That isn’t a terminal app.', 'invalid')
        path = DATA_HOME / 'applications' / (args[1] + '.desktop')
        if not path.is_file() or not appslib.read_desktop(path).get('X-Arctic-TerminalApp-Id'):
            raise Failure('That terminal app isn’t there any more.', 'not-found')
        path.unlink()
        icon = DATA_HOME / 'icons/hicolor/256x256/apps' / (args[1] + '.png')
        if icon.is_file():
            icon.unlink()
        return out(dict(removed=args[1]))
    options = {}
    rest = args[1:]
    while rest:
        if rest[0] not in ('--name', '--command', '--window', '--icon') or len(rest) < 2:
            usage('usage: apps.py terminal-app add --name NAME --command CMD --window float|tile [--icon PNG]')
        options[rest[0][2:]] = rest[1]
        rest = rest[2:]
    raw_name = options.get('name', '')
    if '/' in raw_name or not raw_name.strip():
        raise Failure('Give the app a name without “/”.', 'invalid')
    name = appslib.clean_name(raw_name)
    command = options.get('command', '')
    if any(c in command for c in '\n\r\x00') or not command.strip():
        raise Failure('Enter the command on one line.', 'invalid')
    try:
        words = shlex.split(command)
    except ValueError:
        raise Failure('The command has an unfinished quote.', 'invalid') from None
    if not words or not shutil.which(words[0]):
        program = words[0] if words else command
        raise Failure('{} isn’t installed. Install it from Fedora packages first.'.format(program), 'missing')
    window = options.get('window', 'float')
    if window not in ('float', 'tile'):
        raise Failure('The window is floating or tiled.', 'invalid')
    ident = '{}{}.{}'.format(TERMINAL_PREFIX, 'Float' if window == 'float' else 'Tile', appslib.slug(name))
    folder = DATA_HOME / 'applications'
    path = folder / (ident + '.desktop')
    if any(p.is_file() for p in (folder / (TERMINAL_PREFIX + w + '.' + appslib.slug(name) + '.desktop') for w in ('Float', 'Tile'))):
        raise Failure('You already have a terminal app called {}.'.format(name), 'exists')
    icon = ''
    if options.get('icon'):
        try:
            from PIL import Image
            with Image.open(options['icon']) as picture:
                picture = picture.convert('RGBA')
                picture.thumbnail((256, 256))
                canvas = Image.new('RGBA', (256, 256), (0, 0, 0, 0))
                canvas.paste(picture, ((256 - picture.width) // 2, (256 - picture.height) // 2))
                target = DATA_HOME / 'icons/hicolor/256x256/apps' / (ident + '.png')
                target.parent.mkdir(parents=True, exist_ok=True)
                canvas.save(target)
            icon = ident
        except (ImportError, OSError, ValueError):
            raise Failure('That picture couldn’t be read. Choose a PNG or JPEG file.', 'icon') from None
    if not icon:
        program = os.path.basename(words[0])
        own = appslib.desktop_entries(system_desktop_dirs()).get(program)
        icon = own['icon'] if own and own.get('icon') else 'utilities-terminal'
    exec_line = ' '.join(appslib.exec_quote(w) for w in ['arctic-open', 'terminal', '--app-id', ident, '-e', *words])
    keyword = os.path.basename(words[0]).replace(';', '')
    text = '\n'.join([
        '[Desktop Entry]', 'Type=Application', 'Version=1.5', 'Name=' + name,
        'Comment=Terminal app · ' + ' '.join(words).replace('\n', ' ')[:120], 'Exec=' + exec_line, 'Icon=' + icon,
        'Terminal=false', 'Categories=System;X-Arctic-TerminalApp;', 'Keywords=terminal;tui;{};'.format(keyword),
        'X-Arctic-TerminalApp-Id=' + ident, 'X-Arctic-TerminalApp-Command=' + ' '.join(shlex.quote(w) for w in words),
        'X-Arctic-TerminalApp-Window=' + window, ''])
    folder.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(text)
    temp.replace(path)
    out(dict(app=dict(id=ident, name=name, desktop_file=str(path))))


def cmd_protected(_args):
    out(dict(patterns=appslib.protection().patterns))


COMMANDS = {
    'sources': cmd_sources, 'catalog': cmd_catalog, 'info': cmd_info, 'installed': cmd_installed,
    'installed-ids': cmd_installed_ids, 'counts': cmd_counts, 'preview-remove': cmd_preview_remove,
    'owner': cmd_owner, 'terminal-app': cmd_terminal_app, 'launcher-entry': cmd_launcher_entry,
    'protected': cmd_protected,
}


def main(argv):
    if not argv or argv[0] not in COMMANDS:
        usage('usage: apps.py ' + '|'.join(COMMANDS) + ' …')
    try:
        COMMANDS[argv[0]](argv[1:])
    except Failure as error:
        print(json.dumps(dict(ok=False, error=str(error), code=error.code), ensure_ascii=False), flush=True)
        sys.exit(1)
    except (OSError, ValueError) as error:
        print(json.dumps(dict(ok=False, error='Get apps couldn’t do that: {}'.format(error), code='failed'),
                         ensure_ascii=False), flush=True)
        sys.exit(1)


if __name__ == '__main__':
    main(sys.argv[1:])
