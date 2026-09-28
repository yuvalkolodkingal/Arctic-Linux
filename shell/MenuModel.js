.pragma library
.import "LauncherSearch.js" as LauncherSearch
// The command menu's model (CommandMenu.qml, Super + Alt + Space). Pure functions, tested in
// tests/test-command-menu.cjs.
//
// The menu is data: menu/arctic-menu.json, with ~/.config/arctic/menu.json merged over it by
// id (a shipped id you repeat changes only the fields you give; "hidden": true removes it; new
// ids are added after the shipped ones). Dotted ids make the tree: "capture.area" is a row of
// "capture". Fields of an entry:
//   label, icon (a design icon name), desc (a second line), keys (its shortcut, shown as a chip)
//   run       ["argv", …] runs it (never through a shell); a string runs with `sh -c` (for
//             entries of your own)
//   go        "<id>": opens that branch instead (a link)
//   provider  rows made when the menu opens: "settings" (the Settings pages), "themes"
//   needs     ["command", …]: hidden unless all are installed (default: the command it runs)
//   ipc       "target function": hidden unless the running shell answers it
//   when      "live" | "installed": only in the live session / only on an installed system
//   test      "<sh condition>": hidden unless it succeeds (for entries of your own)
//   state     ["argv", …] prints JSON (or on/off) saying whether it is on: the row shows a
//             switch; "dark" is the theme's light or dark
//   labelOn   the label while the state is on ("Stop recording")
// Guards and states are checked by one `sh` script per open (guardScript); its lines are read
// back with readGuard. A branch with nothing to show is hidden too.

// ---- data ---------------------------------------------------------------------------------

// Menu files are JSON with whole-line // comments allowed.
function parse(text) {
    const body = String(text || '').split('\n').filter(l => !/^\s*\/\//.test(l)).join('\n');
    if (!body.trim()) return {};
    const data = JSON.parse(body);
    return data && typeof data === 'object' && !Array.isArray(data) ? data : {};
}

// build(shipped, mine) -> {order: [ids], byId: {id: entry}}; either may be an object or text.
function build(shipped, mine) {
    const a = typeof shipped === 'string' ? parse(shipped) : (shipped || {});
    const b = typeof mine === 'string' ? safeParse(mine) : (mine || {});
    const byId = {}, order = [];
    [a, b].forEach(source => {
        Object.keys(source).forEach(id => {
            const fields = source[id];
            if (!validId(id) || !fields || typeof fields !== 'object') return;
            if (!byId[id]) { byId[id] = { id: id }; order.push(id); }
            Object.keys(fields).forEach(k => { if (k !== 'id') byId[id][k] = fields[k]; });
        });
    });
    const ids = order.filter(id => !byId[id].hidden && !hiddenAncestor(byId, id));
    const out = {};
    ids.forEach(id => { out[id] = byId[id]; });
    return { order: ids, byId: out };
}
function safeParse(text) {
    try { return parse(text); } catch (e) { return {}; }
}
function validId(id) { return /^[a-z0-9][a-z0-9_-]*(\.[a-z0-9][a-z0-9_-]*)*$/.test(id); }
function hiddenAncestor(byId, id) {
    for (let p = parentOf(id); p; p = parentOf(p)) if (byId[p] && byId[p].hidden) return true;
    return false;
}
function parentOf(id) {
    const at = String(id).lastIndexOf('.');
    return at < 0 ? '' : id.slice(0, at);
}
function childIds(model, parent) {
    return model.order.filter(id => parentOf(id) === parent);
}

// The commands an entry needs installed.
function needsOf(entry) {
    if (Array.isArray(entry.needs)) return entry.needs.filter(c => typeof c === 'string' && c);
    if (Array.isArray(entry.run) && typeof entry.run[0] === 'string' && entry.run[0]) return [entry.run[0]];
    return [];
}

// ---- the guard script -----------------------------------------------------------------------

function q(s) { return "'" + String(s).replace(/'/g, "'\\''") + "'"; }

// One sh script that prints what the menu needs to know, one tab-separated line each:
//   cmd <name>            the command is installed
//   test <id>             the entry's test succeeded
//   ipc <text>            a line of `quickshell ipc show` (the shell's IPC targets)
//   state <id> <text>     the first 2000 characters of the entry's state command
//   provider <id> <text>  a provider's output on one line
// opts: {shellDir}. Commands never go through the shell: every word is quoted.
function guardScript(model, opts) {
    opts = opts || {};
    const cmds = {}, lines = [];
    let wantIpc = false;
    model.order.forEach(id => {
        const e = model.byId[id];
        needsOf(e).forEach(c => { cmds[c] = true; });
        if (e.ipc) wantIpc = true;
        if (Array.isArray(e.state) && e.state.length) cmds[e.state[0]] = true;
    });
    const names = Object.keys(cmds).sort();
    if (names.length)
        lines.push('for c in ' + names.map(q).join(' ') + '; do command -v -- "$c" >/dev/null 2>&1 && printf \'cmd\\t%s\\n\' "$c"; done');
    if (wantIpc && opts.shellDir)
        lines.push('quickshell ipc -p ' + q(opts.shellDir) + ' show 2>/dev/null | while IFS= read -r l; do printf \'ipc\\t%s\\n\' "$l"; done');
    model.order.forEach(id => {
        const e = model.byId[id];
        if (typeof e.test === 'string' && e.test.trim())
            lines.push('( ' + e.test + ' ) >/dev/null 2>&1 </dev/null && printf \'test\\t%s\\n\' ' + q(id));
    });
    model.order.forEach(id => {
        const e = model.byId[id];
        if (!Array.isArray(e.state) || !e.state.length) return;
        lines.push('( command -v -- ' + q(e.state[0]) + ' >/dev/null 2>&1 && out=$(timeout 3 ' + e.state.map(q).join(' ')
                   + ' 2>/dev/null </dev/null | tr -d \'\\n\\t\' | head -c 2000) && printf \'state\\t%s\\t%s\\n\' ' + q(id) + ' "$out" ) &');
    });
    lines.push('wait');
    model.order.forEach(id => {
        const e = model.byId[id];
        if (e.provider === 'themes')
            lines.push('command -v arctic-theme >/dev/null 2>&1 && printf \'provider\\t%s\\t%s\\n\' ' + q(id)
                       + ' "$(timeout 5 arctic-theme list --json 2>/dev/null </dev/null | tr -d \'\\n\\t\')"');
    });
    return lines.join('\n') + '\n';
}

// A fresh context: nothing known yet. live: the live session; dark: the theme is dark.
function context(live, dark) {
    return { ready: false, live: !!live, dark: !!dark, commands: {}, tests: {}, ipc: {}, ipcTarget: '', states: {}, providers: {} };
}

// Read one line of the guard script's output into ctx (changes ctx; returns it).
function readGuard(ctx, line) {
    const parts = String(line).split('\t');
    const kind = parts[0];
    if (kind === 'cmd' && parts[1]) ctx.commands[parts[1]] = true;
    else if (kind === 'test' && parts[1]) ctx.tests[parts[1]] = true;
    else if (kind === 'ipc') {
        const text = parts.slice(1).join('\t');
        const target = /^\s*target\s+(\S+)/.exec(text);
        const fn = /^\s*function\s+([A-Za-z_]\w*)\s*\(/.exec(text);
        if (target) ctx.ipcTarget = target[1];
        else if (fn && ctx.ipcTarget) ctx.ipc[ctx.ipcTarget + ' ' + fn[1]] = true;
    } else if (kind === 'state' && parts[1]) ctx.states[parts[1]] = stateOf(parts.slice(2).join('\t'));
    else if (kind === 'provider' && parts[1]) {
        try { ctx.providers[parts[1]] = JSON.parse(parts.slice(2).join('\t')); } catch (e) { ctx.providers[parts[1]] = null; }
    }
    return ctx;
}

// Whether a state command's output says "on": true, false, or undefined when it can't tell.
function stateOf(text) {
    const t = String(text || '').trim();
    if (/^(on|yes|true|enabled|active|reduced)$/i.test(t)) return true;
    if (/^(off|no|false|disabled|inactive|normal)$/i.test(t)) return false;
    let v;
    try { v = JSON.parse(t); } catch (e) { return undefined; }
    if (!v || typeof v !== 'object' || v.ok === false) return undefined;
    const keys = ['on', 'active', 'enabled', 'recording', 'dnd'];
    for (let i = 0; i < keys.length; i++) if (typeof v[keys[i]] === 'boolean') return v[keys[i]];
    if (typeof v.state === 'string') return v.state === 'on';
    if (typeof v.class === 'string') return v.class === 'dnd';      // arctic-dnd status (waybar JSON)
    return undefined;
}

// ---- rows ---------------------------------------------------------------------------------

function allowed(entry, ctx) {
    if (entry.when === 'live' && !ctx.live) return false;
    if (entry.when === 'installed' && ctx.live) return false;
    const needs = needsOf(entry);
    for (let i = 0; i < needs.length; i++) if (!ctx.commands[needs[i]]) return false;
    if (entry.ipc && !ctx.ipc[String(entry.ipc).trim().replace(/\s+/g, ' ')]) return false;
    if (typeof entry.test === 'string' && entry.test.trim() && !ctx.tests[entry.id]) return false;
    return true;
}

function checkedOf(entry, ctx) {
    if (entry.state === 'dark') return ctx.dark;
    if (Array.isArray(entry.state)) return ctx.states[entry.id];
    return undefined;
}

// Rows a provider makes. settings: the Settings pages ({pages} from LauncherSearch.parseSettings);
// themes: `arctic-theme list --json`.
function providerRows(entry, ctx, extra) {
    const out = [];
    if (entry.provider === 'settings') {
        const pages = (extra && extra.settingsPages) || [];
        pages.forEach(p => out.push({ id: entry.id + '.' + p.id, label: p.title, icon: p.icon || 'sliders',
                                      desc: '', keys: '', kind: 'action', run: ['arctic-settings', p.id] }));
    } else if (entry.provider === 'themes') {
        const list = ctx.providers[entry.id];
        if (Array.isArray(list)) list.forEach(t => {
            if (!t || typeof t.name !== 'string') return;
            out.push({ id: entry.id + '.' + t.name, label: t.label || t.name, icon: t.mode === 'light' ? 'snowflake' : 'moon',
                       desc: t.name === 'wallpaper' ? 'Colours from your wallpaper' : '', keys: '', kind: 'action',
                       run: ['arctic-theme', 'set', t.name], current: !!t.active });
        });
    }
    return out;
}

function hasRows(model, id, ctx, extra) {
    const e = model.byId[id];
    if (e.provider) return providerRows(e, ctx, extra).length > 0;
    const kids = childIds(model, id);
    for (let i = 0; i < kids.length; i++) {
        const k = model.byId[kids[i]];
        if (!allowed(k, ctx)) continue;
        if (isBranch(model, k)) { if (hasRows(model, k.id, ctx, extra)) return true; }
        else if (k.run || k.go) return true;
    }
    return false;
}
function isBranch(model, entry) {
    return !!entry.provider || model.order.some(id => parentOf(id) === entry.id);
}

// The rows of a branch ('' is the top), in file order:
// {id, label, icon, desc, keys, kind: 'branch'|'action'|'link', run, go, checked, current}.
function rows(model, parent, ctx, extra) {
    const p = parent ? model.byId[parent] : null;
    if (p && p.provider) return providerRows(p, ctx, extra);
    const out = [];
    childIds(model, parent).forEach(id => {
        const e = model.byId[id];
        if (!allowed(e, ctx)) return;
        const branch = isBranch(model, e);
        if (branch && !hasRows(model, id, ctx, extra)) return;
        if (!branch && !e.run && !(e.go && model.byId[e.go])) return;
        const checked = branch ? undefined : checkedOf(e, ctx);
        out.push({ id: id, label: checked === true && e.labelOn ? e.labelOn : (e.label || id), icon: e.icon || (branch ? 'grid' : 'arrow-right'),
                   desc: e.desc || '', keys: e.keys || '', kind: branch ? 'branch' : e.run ? 'action' : 'link',
                   run: e.run, go: e.go || '', checked: checked, keywords: e.keywords || '' });
    });
    return out;
}

// Every row under a branch, for typing to filter: leaves only, each with where it is
// ("Capture", "Toggle › …") as its desc when it has none of its own. Best match first.
function search(model, parent, query, ctx, extra) {
    const found = [];
    function walk(id, trail) {
        rows(model, id, ctx, extra).forEach(r => {
            if (r.kind === 'branch') { walk(r.id, trail.concat([r.label])); return; }
            found.push(Object.assign({}, r, { desc: r.desc || trail.join(' › '), name: r.label,
                                              keywords: [r.keywords, trail.join(' '), r.desc].join(' ') }));
        });
    }
    walk(parent, []);
    return LauncherSearch.rank(found, query);
}

// The labels from the top to a branch, for the header ("Capture", "Style › Theme").
function trail(model, id) {
    const out = [];
    for (let p = id; p; p = parentOf(p)) if (model.byId[p]) out.unshift(model.byId[p].label || p);
    return out;
}

// Where `menu open <path>` goes: {branch, select} (the row to select), or null if unknown.
// A leaf opens its branch with it selected.
function locate(model, path) {
    const id = String(path || '').trim().replace(/[\s/>]+/g, '.').replace(/^\.+|\.+$/g, '').toLowerCase();
    if (!id || id === 'root') return { branch: '', select: '' };
    const e = model.byId[id];
    if (!e) return null;
    return isBranch(model, e) ? { branch: id, select: '' } : { branch: parentOf(id), select: id };
}
