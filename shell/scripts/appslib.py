"""Shared pieces of Get apps and Remove apps (scripts/apps.py and scripts/install-terminal.py).

No import side effects: nothing here runs a command or reads a file until it is called.

    build_job(job)        the argv lists a structured install/remove job runs, in order
    progress(lines)       percent and step text from dnf5 / flatpak output on the screen
    explain(job, code, tail)   one sentence for a job that failed
    protection()          the packages Get apps never removes (protected-packages.conf)
    desktop_entries(dirs) installed applications by desktop id (the rules Settings uses)
    flathub_installations()    which Flatpak installations have the flathub remote
    role_keys()           the keys that open each default-app role (mango apps.conf)
"""
import fnmatch
import os
import re
import shlex
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
# dnf5 itself (/usr/bin/dnf is a link to it): the path the polkit action names.
DNF = '/usr/bin/dnf5'
PKEXEC_DNF = ['pkexec', DNF]
NAME = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+@:-]*$')
FLATPAK_ID = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]*(\.[A-Za-z_][A-Za-z0-9_-]*){2,}$')
FLATHUB_URL = 'https://dl.flathub.org/repo/flathub.flatpakrepo'
INSTALLATIONS = ('system', 'user')
MAX_IDS = 50
TERMINALS = ('kitty', 'foot', 'alacritty')   # the same list as Settings (arctic_settings.py)
# The static list, and where administrators add their own patterns.
PROTECTED_FILE = HERE / 'protected-packages.conf'
PROTECTED_DIR = Path(os.environ.get('ARCTIC_PROTECTED_DIR') or '/etc/arctic/protected-packages.d')


# ---- protected packages -----------------------------------------------------------------------

class Protection:
    """fnmatch patterns, one per line with # comments, from the shipped file and the
    administrator's directory."""

    def __init__(self, patterns):
        self.patterns = [p for p in patterns if p]

    def match(self, name):
        return next((p for p in self.patterns if fnmatch.fnmatchcase(name, p)), None)

    def check(self, names):
        """ValueError with the sentence for the first protected name."""
        for name in names:
            if self.match(name):
                raise ValueError('{} is part of Arctic Linux, so Get apps won’t remove it.'.format(name))


def read_patterns(path):
    try:
        text = Path(path).read_text()
    except OSError:
        return []
    return [line.split('#', 1)[0].strip() for line in text.splitlines() if line.split('#', 1)[0].strip()]


def protection(static=None, extra_dir=None):
    patterns = read_patterns(static or PROTECTED_FILE)
    folder = Path(extra_dir or PROTECTED_DIR)
    try:
        for path in sorted(folder.glob('*.conf')):
            patterns += read_patterns(path)
    except OSError:
        pass
    return Protection(patterns)


# ---- structured jobs --------------------------------------------------------------------------

def _names(job, pattern, what):
    ids = job.get('ids') or []
    if not isinstance(ids, list) or not ids:
        raise ValueError('Choose at least one {}.'.format(what))
    if len(ids) > MAX_IDS:
        raise ValueError('Choose at most {} at a time.'.format(MAX_IDS))
    for name in ids:
        if not isinstance(name, str) or not pattern.match(name):
            raise ValueError('“{}” isn’t a {}.'.format(name, what))
    return ids


def _installation(job):
    value = job.get('installation') or 'system'
    if value not in INSTALLATIONS:
        raise ValueError('Flatpak installs go to the system or to you, not “{}”.'.format(value))
    return value


def _remote(job):
    value = job.get('remote') or 'flathub'
    if value != 'flathub':
        raise ValueError('Get apps installs from Flathub only.')
    return value


def build_job(job, protected=None, user_remotes=None):
    """The commands a GUI job runs, in order, until one fails. Never a shell; every id is
    checked. `user_remotes`: the remotes of the user installation (None: ask flatpak)."""
    kind, source = job.get('kind'), job.get('source')
    if source == 'nix':
        import nixlib
        ids = job.get('ids') or []
        if not isinstance(ids, list):
            raise ValueError('Choose Nix packages from the list.')
        nixlib.command(kind, ids)  # Validate before handing the job to the PTY.
        return [['python3', str(HERE / 'nixlib.py'), kind, *ids]]
    if kind == 'install' and source == 'dnf':
        return [[*PKEXEC_DNF, 'install', '-y', *_names(job, NAME, 'package name')]]
    if kind == 'install' and source == 'flatpak':
        ids = _names(job, FLATPAK_ID, 'Flatpak app id')
        where, remote = _installation(job), _remote(job)
        steps = []
        if where == 'user':
            remotes = user_remotes if user_remotes is not None else flatpak_remotes('user')
            if remote not in remotes:
                steps.append(['flatpak', 'remote-add', '--user', '--if-not-exists', 'flathub', FLATHUB_URL])
        steps.append(['flatpak', 'install', '--' + where, '-y', '--noninteractive', remote, *ids])
        return steps
    if kind == 'remove' and source == 'dnf':
        ids = _names(job, NAME, 'package name')
        (protected or protection()).check(ids)
        autoremove = job.get('autoremove', True) is not False
        return [[*PKEXEC_DNF, 'remove', '-y', *([] if autoremove else ['--no-autoremove']), *ids]]
    if kind == 'remove' and source == 'flatpak':
        ids = _names(job, FLATPAK_ID, 'Flatpak app id')
        where = '--' + _installation(job)
        steps = [['flatpak', 'uninstall', where, '-y', '--noninteractive',
                  *(['--delete-data'] if job.get('delete_data') else []), *ids]]
        if job.get('unused', True) is not False:
            steps.append(['flatpak', 'uninstall', where, '-y', '--noninteractive', '--unused'])
        return steps
    if kind == 'add-remote' and source == 'flatpak':
        _remote(job)
        return [['flatpak', 'remote-add', '--' + _installation(job), '--if-not-exists', 'flathub', FLATHUB_URL]]
    raise ValueError('Get apps can’t do that.')


# ---- progress and errors ----------------------------------------------------------------------

DNF_COUNTER = re.compile(r'^\[\s*(\d+)/(\d+)\]\s*(.*)$')
PERCENT = re.compile(r'(\d{1,3})%')
# What follows the step text on a dnf5 progress line: "100% |  1.2 MiB/s | 3.0 MiB |  00m02s".
FLATPAK_BAR = re.compile('[…▀-▟#\\[]|\\.\\.\\.')
DNF_TAIL = re.compile(r'\s+(-?\d{1,3}%.*|\.\.\.)$')


def progress(lines):
    """{percent, done, total, step} from the last lines on the screen (dnf5's "[ 3/12] Installing
    foo" counters, else flatpak's last "NN%"); None when they say nothing."""
    for line in reversed([l.strip() for l in lines if l and l.strip()]):
        m = DNF_COUNTER.match(line)
        if m:
            done, total = int(m.group(1)), int(m.group(2))
            if total <= 0:
                continue
            step = DNF_TAIL.sub('', m.group(3)).strip()
            return dict(percent=min(100, done * 100 // total), done=done, total=total, step=step)
        found = PERCENT.findall(line)
        if found and int(found[-1]) <= 100:
            # "Installing 1/2… ████████▌  45%  1.2 MB/s": the words before the bar.
            step = FLATPAK_BAR.split(line.split(found[-1] + '%')[0], 1)[0].strip()
            return dict(percent=int(found[-1]), done=None, total=None, step=step[:80])
    return None


def waiting(tail):
    return 'Waiting for process with pid' in tail or 'waiting for a lock' in tail.lower()


def explain(job, code, tail, name=''):
    """The sentence for a job that ended with `code` (0: ''), from the end of its output."""
    if code == 0:
        return ''
    if (job or {}).get('source') == 'nix':
        return 'Nix could not complete the change. Show details has its error; refresh the profile before retrying.'
    removing = (job or {}).get('kind') == 'remove'
    label = name or ', '.join((job or {}).get('ids') or []) or 'The app'
    nothing = 'Nothing was removed.' if removing else 'Nothing was installed.'
    if code == 126:
        return 'You closed the password prompt. ' + nothing
    if code == 127 and 'pkexec' in ' '.join((job or {}).get('argv') or ['pkexec']):
        return 'Arctic Linux couldn’t get permission to make this change. Nothing was changed.'
    if 'No match for argument' in tail:
        return '{} isn’t in Fedora’s repositories any more. Try Flathub.'.format(label)
    lowered = tail.lower()
    if any(k in lowered for k in ('curl error', 'could not resolve host', 'failed to download',
                                   'cannot download', 'unable to connect', 'network is unreachable',
                                   'while fetching', 'unable to load summary')):
        return '{} couldn’t be downloaded. Check your internet connection and try again. Nothing else changed.'.format(label)
    if code == 130 or code == -2:
        return 'Stopped. ' + nothing
    if removing:
        return '{} wasn’t removed. Show details has what went wrong.'.format(label)
    return '{} wasn’t installed. Show details has what went wrong.'.format(label)


# ---- desktop entries (the rules of settings/scripts/arctic_settings.py desktop_entries) ------

def read_desktop(path):
    entry = {}
    section = ''
    try:
        text = Path(path).read_text(errors='replace')
    except OSError:
        text = ''
    for line in text.splitlines():
        line = line.strip()
        if line.startswith('['):
            section = line
            continue
        if section != '[Desktop Entry]' or '=' not in line or line.startswith('#'):
            continue
        key, value = line.split('=', 1)
        entry.setdefault(key.strip(), value.strip())
    return entry


def desktop_entries(dirs):
    """Installed applications by desktop id (XDG precedence: the first one found wins)."""
    entries = {}
    for folder in dirs:
        folder = Path(folder)
        if not folder.is_dir():
            continue
        for path in sorted(folder.rglob('*.desktop')):
            ident = str(path.relative_to(folder))[:-8].replace('/', '-')
            if ident in entries:
                continue
            raw = read_desktop(path)
            if raw.get('Type', 'Application') != 'Application' or raw.get('Hidden', '').lower() == 'true':
                entries[ident] = None
                continue
            if 'Exec' not in raw or 'Name' not in raw:
                entries[ident] = None
                continue
            entries[ident] = dict(
                id=ident, name=raw['Name'], exec=raw['Exec'], icon=raw.get('Icon', ''),
                comment=raw.get('GenericName') or raw.get('Comment', ''),
                categories=[c for c in raw.get('Categories', '').split(';') if c],
                mimes=[m for m in raw.get('MimeType', '').split(';') if m],
                terminal=raw.get('Terminal', '').lower() == 'true',
                nodisplay=raw.get('NoDisplay', '').lower() == 'true', path=str(path), raw=raw)
    return {k: v for k, v in entries.items() if v}


def exec_program(entry):
    """The program a desktop entry runs (the app id for `flatpak run`)."""
    try:
        words = shlex.split(entry.get('exec', ''))
    except ValueError:
        words = entry.get('exec', '').split()
    while words and (words[0] == 'env' or '=' in words[0]):
        words = words[1:]
    if words and os.path.basename(words[0]) == 'flatpak':
        return words[-1]
    return os.path.basename(words[0]) if words else ''


# ---- desktop entry values ---------------------------------------------------------------------

EXEC_RESERVED = set(' \t\n"\'\\><~|&;$*?#()`')
CONTROL = re.compile('[\x00-\x1f\x7f‎‏‪-‮⁦-⁩]')


def exec_quote(word):
    """One Exec argument, quoted per the Desktop Entry spec ("%" becomes "%%")."""
    word = word.replace('%', '%%')
    if word and not any(c in EXEC_RESERVED for c in word):
        return word
    escaped = ''.join('\\' + c if c in '"`$\\' else c for c in word)
    return '"' + escaped + '"'


def clean_name(text, limit=64):
    return ' '.join(CONTROL.sub('', text).split())[:limit].strip()


def slug(name):
    """ASCII letters and digits in CamelCase, as the web-app engine makes its ids."""
    words = re.findall(r'[A-Za-z0-9]+', name)
    out = ''.join(w[:1].upper() + w[1:] for w in words)[:32]
    if not out:
        return 'App'
    return 'App' + out if out[0].isdigit() else out


# ---- flatpak and default apps -----------------------------------------------------------------

def run(argv, timeout=60, env=None):
    """(code, stdout, stderr); code 127 when the program is missing."""
    try:
        done = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              env=dict(env or os.environ, LC_ALL='C.UTF-8'))
        return done.returncode, done.stdout, done.stderr
    except FileNotFoundError:
        return 127, '', '{}: not found'.format(argv[0])
    except (OSError, subprocess.SubprocessError) as error:
        return 1, '', str(error)


def flatpak_remotes(installation):
    code, out, _err = run(['flatpak', 'remotes', '--' + installation, '--columns=name'], timeout=20)
    if code != 0:
        return []
    return [line.split('\t')[0].strip() for line in out.splitlines() if line.strip()]


def flathub_installations():
    """{'system': bool, 'user': bool}: where the flathub remote is set up."""
    return {where: 'flathub' in flatpak_remotes(where) for where in INSTALLATIONS}


def role_keys(paths=None):
    """{role: 'Super + B'} from mango's apps.conf (`bind=SUPER,b,spawn,arctic-open browser`)."""
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    for path in paths or (config / 'mango/arctic/apps.conf', Path('/usr/share/arctic/mango/apps.conf')):
        try:
            text = Path(path).read_text()
        except OSError:
            continue
        keys = {}
        for line in text.splitlines():
            m = re.match(r'^\s*bind\s*=\s*([A-Z+]+)\s*,\s*([^,]+?)\s*,\s*spawn\s*,\s*arctic-open\s+(\S+)\s*$', line)
            if m and m.group(3) not in keys:
                mods = [w.capitalize() for w in m.group(1).split('+') if w]
                key = m.group(2)
                key = 'Enter' if key == 'Return' else key.upper() if len(key) == 1 else key
                keys[m.group(3)] = ' + '.join(mods + [key])
        return keys
    return {}
