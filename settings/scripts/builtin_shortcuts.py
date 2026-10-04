"""Per-user remaps of packaged Mango shortcuts, with retained recovery bindings.

Generated copies are rebuilt from current RPM templates at login. Unknown manual
edits are never overwritten, and no privileged/package-owned file is written.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

FILES = ('apps.conf', 'binds.conf')
RECOVERY = [('Return', 'spawn,arctic-open terminal'), ('F12', 'spawn,arctic-settings shortcuts'), ('r', 'reload_config')]


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def state_path(paths):
    return paths.arctic / 'builtin-shortcuts.json'


def state(api, paths):
    try:
        data = json.loads(api.read_text(state_path(paths)) or '{}')
        if not isinstance(data, dict) or not isinstance(data.get('overrides', {}), dict) or not isinstance(data.get('rendered', {}), dict):
            raise ValueError()
        for ident, value in data.get('overrides', {}).items():
            if not re.fullmatch('[0-9a-f]{24}', ident) or not isinstance(value, dict) or set(value) != {'mods', 'key'} or not all(isinstance(v, str) for v in value.values()):
                raise ValueError()
        return data
    except ValueError as exc:
        raise api.Failure('The built-in shortcut state is invalid; restore it from a backup.') from exc


def defaults(api, paths):
    texts, rows = {}, []
    for name in FILES:
        source = paths.share / 'mango' / name
        if not source.is_file():
            return {}, []
        texts[name] = source.read_text()
        mode = 'default'
        for index, line in enumerate(texts[name].splitlines()):
            pair = api.split_line(line)
            if not pair:
                continue
            kind, value = pair
            if kind == 'keymode':
                mode = value
            if not re.fullmatch(r'bind[a-z]*', kind):
                continue
            parts = [p.strip() for p in value.split(',')]
            if len(parts) < 3:
                continue
            mods = api.parse_mods(parts[0])
            ident = digest('|'.join((name, mode, kind, value)))[:24]
            rows.append(dict(id=ident, name=name, line=index, kind=kind, flags=kind[4:], keymode=mode,
                             mods=api.mods_text(mods), key=parts[1], action=parts[2], args=','.join(parts[3:]),
                             label=api.combo_label(mods, parts[1]), what=','.join(parts[3:]) if parts[2] in ('spawn', 'spawn_shell') else api.DISPATCHERS.get(parts[2], parts[2]) + (' ' + ','.join(parts[3:]) if parts[3:] else '')))
    return texts, rows


def listing(api, paths):
    _, rows = defaults(api, paths)
    saved = state(api, paths).get('overrides', {})
    for row in rows:
        row['originalLabel'] = row['label']
        row['modified'] = row['id'] in saved
        if row['modified']:
            row.update(saved[row['id']])
            row['label'] = api.combo_label(api.parse_mods(row['mods']), row['key'])
    return dict(ok=True, bindings=rows, orphaned=sorted(set(saved) - {r['id'] for r in rows}))


def validate_key(api, paths, row, mods, key):
    mods = api.parse_mods(mods)
    key = key.lower() if len(key) == 1 else key
    if not api.RE_KEY.fullmatch(key):
        raise api.Failure('Choose a valid Mango key name.')
    if row['keymode'] in ('default', 'common') and not mods - {'SHIFT'} and not api.FREE_KEYS.match(key):
        raise api.Failure('Use Super, Ctrl or Alt so this shortcut does not take over typing.')
    if mods == {'SUPER', 'CTRL', 'ALT'} and key in {r[0] for r in RECOVERY}:
        raise api.Failure('This is a reserved recovery shortcut.')
    layouts, options = api.chain_keyboard(paths)
    switch = next((o for o in options if o.startswith('grp:')), 'grp:alt_shift_toggle')
    if len(layouts) > 1 and api.switch_clash(switch, mods, key):
        raise api.Failure('That shortcut conflicts with keyboard layout switching.')
    return dict(mods=api.mods_text(mods), key=key)


def replace_file(path, text=None, target=None):
    # Unlike the general settings writer, replace the user's symlink itself.
    fd, temporary = tempfile.mkstemp(prefix='.arctic-bind-', dir=path.parent)
    try:
        if target is not None:
            os.close(fd)
            os.unlink(temporary)
            os.symlink(target, temporary)
        else:
            with os.fdopen(fd, 'w') as handle:
                handle.write(text)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o644)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def apply(api, paths, overrides, old):
    texts, rows = defaults(api, paths)
    if not texts:
        raise api.Failure('Packaged Mango shortcut templates are unavailable.')
    effective = []
    for row in rows:
        row = dict(row)
        if row['id'] in overrides:
            row.update(validate_key(api, paths, row, **overrides[row['id']]))
        effective.append(row)
    external = [b for b in api.chain_binds(paths) if not any(api.same_file(b['file'], paths.mango / 'arctic' / name) for name in FILES)]
    if overrides:
        reserved = {api.combo_id({'SUPER', 'CTRL', 'ALT'}, key) for key, _ in RECOVERY}
        for row in effective + external:
            mods = api.parse_mods(row['mods']) if isinstance(row['mods'], str) else set(row['mods'])
            if api.combo_id(mods, row['key']) in reserved:
                raise api.Failure('A recovery key is already in use. Move that shortcut before enabling built-in remaps.')
    for row in effective:
        if row['id'] not in overrides:
            continue
        combo = api.combo_id(api.parse_mods(row['mods']), row['key'])
        for other in effective + external:
            if other.get('id') == row['id'] or ('r' in row['flags']) != ('r' in other['flags']) or 'c' in other['flags']:
                continue
            if row['keymode'] != other['keymode'] and 'common' not in (row['keymode'], other['keymode']):
                continue
            other_mods = api.parse_mods(other['mods']) if isinstance(other['mods'], str) else set(other['mods'])
            if api.combo_id(other_mods, other['key']) == combo:
                raise api.Failure('That key combination already has a shortcut. No changes made.')
    # Validate every destination before writing either file.
    for name in FILES:
        path = paths.mango / 'arctic' / name
        if not path.parent.resolve().is_relative_to(paths.home.resolve()):
            raise api.Failure('Shortcut copies must be in your own home directory.')
        current = api.read_text(path)
        packaged_link = path.is_symlink() and path.resolve() == (paths.share / 'mango' / name).resolve()
        if not packaged_link and current != texts[name] and digest(current or '') != old.get('rendered', {}).get(name):
            raise api.Failure(name + ' has manual edits. Keep a backup and restore its packaged link before using built-in remapping; nothing was overwritten.')
    rendered = dict(texts)
    for name in FILES:
        lines = texts[name].splitlines(keepends=True)
        for row in effective:
            if row['name'] == name and row['id'] in overrides:
                lines[row['line']] = row['kind'] + '=' + ','.join((row['mods'], row['key'], row['action']) + ((row['args'],) if row['args'] else ())) + '\n'
        rendered[name] = ''.join(lines)
    if overrides:
        recovery = '\n'.join('bind=SUPER+CTRL+ALT,' + key + ',' + action for key, action in RECOVERY)
        rendered['apps.conf'] = '# Generated by Arctic Settings; recovery keys stay available.\nkeymode=common\n' + recovery + '\nkeymode=default\n' + rendered['apps.conf']
    problem = api.mango_check('\n'.join(rendered.values()))
    if problem:
        raise api.Failure(problem)
    changed = False
    for name in FILES:
        path = paths.mango / 'arctic' / name
        if overrides and api.read_text(path) == rendered[name]:
            continue
        if not overrides and path.is_symlink() and path.resolve() == (paths.share/'mango'/name).resolve():
            continue
        api.backup(paths, path)
        if overrides:
            replace_file(path, text=rendered[name])
        else:
            replace_file(path, target=paths.share / 'mango' / name)
        changed = True
    api.atomic_write(state_path(paths), json.dumps(dict(overrides=overrides, rendered={k:digest(v) for k,v in rendered.items()})) + '\n')
    if changed:
        api.reload_mango()
    return listing(api, paths)


def command(api, paths, args):
    old = state(api, paths)
    overrides = dict(old.get('overrides', {}))
    if args == ['sync']:
        if not state_path(paths).exists():
            return listing(api, paths)
    elif args == ['reset-all']:
        overrides = {}
    elif len(args) == 2 and args[0] == 'reset':
        overrides.pop(args[1], None)
    elif len(args) == 4 and args[0] == 'set':
        _, rows = defaults(api, paths)
        row = next((r for r in rows if r['id'] == args[1]), None)
        if row is None:
            raise api.Failure('The packaged shortcut changed. Refresh the page before editing.')
        overrides[row['id']] = validate_key(api, paths, row, args[2], args[3])
    else:
        raise api.Failure('usage: builtin-bind set ID MODS KEY | reset ID | reset-all | sync')
    return apply(api, paths, overrides, old)
