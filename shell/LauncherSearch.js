.pragma library
// Ranking for the launcher. Pure functions (tested in tests/test-launcher.cjs).
//
// Each candidate is {name, keywords: string} plus anything the caller needs. A match on the
// name beats one on its generic name or keywords; earlier and word-start matches rank higher.

function words(text) {
    return String(text || '').toLowerCase().split(/[\s\-_.:/]+/).filter(w => w.length);
}

function nameScore(name, query) {
    name = String(name || '').toLowerCase();
    if (!query) return 0;
    if (name === query) return 1000;
    if (name.startsWith(query)) return 900 - name.length;
    const ws = words(name);
    for (let i = 0; i < ws.length; i++) if (ws[i].startsWith(query)) return 800 - i * 10 - name.length;
    const at = name.indexOf(query);
    if (at >= 0) return 600 - at * 5 - name.length;
    // Initials: "vsc" → "Visual Studio Code"
    const initials = ws.map(w => w[0]).join('');
    if (query.length >= 2 && initials.startsWith(query)) return 500 - name.length;
    return -1;
}

function fuzzyScore(text, query) {
    text = String(text || '').toLowerCase();
    let position = -1, gaps = 0;
    for (let i = 0; i < query.length; i++) {
        const next = text.indexOf(query[i], position + 1);
        if (next < 0) return -1;
        if (position >= 0) gaps += next - position - 1;
        position = next;
    }
    return Math.max(1, 200 - gaps * 8 - text.length);
}

function score(candidate, query) {
    query = String(query || '').trim().toLowerCase();
    if (!query) return 0;
    const byName = nameScore(candidate.name, query);
    if (byName >= 0) return byName + 1000;
    const extra = words(candidate.keywords);
    for (let i = 0; i < extra.length; i++) if (extra[i].startsWith(query)) return 700 - i;
    if (String(candidate.keywords || '').toLowerCase().indexOf(query) >= 0) return 400;
    return query.length >= 3 && candidate.fuzzy !== false ? fuzzyScore(candidate.name, query) : -1;
}

// rank(candidates, query[, boost]) -> matching candidates, best first (all of them, by name,
// when empty). A candidate's `bias` and boost(candidate) (what you open often, see frecency)
// are added to its score.
function rank(candidates, query, boost) {
    query = String(query || '').trim().toLowerCase();
    if (!query) return candidates.slice().sort((a, b) => String(a.name).localeCompare(String(b.name)));
    const scored = [];
    for (let i = 0; i < candidates.length; i++) {
        const s = score(candidates[i], query);
        if (s >= 0) scored.push({ item: candidates[i], s: s + (candidates[i].bias || 0) + (boost ? boost(candidates[i]) : 0) });
    }
    scored.sort((a, b) => b.s - a.s || String(a.item.name).localeCompare(String(b.item.name)));
    return scored.map(x => x.item);
}

// What the query line means: {mode: 'calc'|'command'|'web'|'search', text}
function mode(query) {
    const q = String(query || '');
    const t = q.replace(/^\s+/, '');
    if (t.startsWith('=')) return { mode: 'calc', text: t.slice(1).trim() };
    if (t.startsWith('>')) return { mode: 'command', text: t.slice(1).trim() };
    if (t.startsWith('?')) return { mode: 'web', text: t.slice(1).trim() };
    return { mode: 'search', text: q.trim() };
}

// The pages and settings of Arctic Settings, read from its SearchIndex.js (the same file its
// own search uses) without running it: {pages: [{id, title, icon, words}], entries:
// [{page, key, title, words}]}. Empty lists when the file doesn't look as expected.
function parseSettings(text) {
    const src = String(text || '');
    const str = '"((?:[^"\\\\]|\\\\.)*)"';
    const out = { pages: [], entries: [] };
    const pages = /var\s+PAGES\s*=\s*\[([\s\S]*?)\];/.exec(src);
    const entries = /var\s+ENTRIES\s*=\s*\[([\s\S]*?)\];/.exec(src);
    const unquote = s => { try { return JSON.parse('"' + s + '"'); } catch (e) { return s; } };
    if (pages) {
        const objects = pages[1].match(/\{[^{}]*\}/g) || [];
        objects.forEach(o => {
            const page = {};
            const field = new RegExp('(\\w+)\\s*:\\s*' + str, 'g');
            let m;
            while ((m = field.exec(o)) !== null) page[m[1]] = unquote(m[2]);
            if (page.id && page.title) out.pages.push({ id: page.id, title: page.title, icon: page.icon || '', words: page.words || '' });
        });
    }
    if (entries) {
        const row = new RegExp('\\[\\s*' + [str, str, str, str].join('\\s*,\\s*') + '\\s*\\]', 'g');
        let m;
        while ((m = row.exec(entries[1])) !== null)
            out.entries.push({ page: unquote(m[1]), key: unquote(m[2]), title: unquote(m[3]), words: unquote(m[4]) });
    }
    return out;
}

// ---- more to find than apps (LauncherSources.qml) -------------------------------------------
// Each is a candidate for rank(): {kind, name, desc, keywords, glyph, bias, …}. The bias keeps
// an app above a window, setting or app action of the same name; `fuzzy: false` keeps the
// many settings out of loose letter-by-letter matches.

// Settings pages and single settings; Enter opens `arctic-settings <page> <key>`.
function settingsCandidates(pages, entries) {
    const title = {};
    const out = [];
    (pages || []).forEach(p => {
        title[p.id] = p.title;
        out.push({ kind: 'setting', name: p.title, desc: 'Settings page', keywords: p.words + ' settings',
                   page: p.id, key: '', glyph: 'sliders', bias: -150, fuzzy: false, id: 'setting:' + p.id });
    });
    (entries || []).forEach(e => {
        if (!title[e.page]) return;
        out.push({ kind: 'setting', name: e.title, desc: 'Settings › ' + title[e.page], keywords: e.words + ' ' + title[e.page],
                   page: e.page, key: e.key, glyph: 'sliders', bias: -150, fuzzy: false, id: 'setting:' + e.page + '/' + e.key });
    });
    return out;
}

// Open windows ({title, appId, appName, icon, ref}); Enter brings the window forward.
function windowCandidates(windows) {
    return (windows || []).filter(w => w.title || w.appId).map(w => ({
        kind: 'window', name: w.title || w.appName || w.appId, desc: 'Open window · ' + (w.appName || w.appId || 'app'),
        keywords: [w.appName, w.appId].join(' '), glyph: 'tiling', icon: w.icon || '', bias: -100, ref: w.ref, appId: w.appId }));
}

// The web search the launcher offers after its results (and alone after "?"). `engine` is a
// name below or your own https:// address with %s where the words go (shell.json "webSearch").
var ENGINES = {
    duckduckgo: { label: 'DuckDuckGo', url: 'https://duckduckgo.com/?q=%s' },
    startpage: { label: 'Startpage', url: 'https://www.startpage.com/do/search?q=%s' },
    brave: { label: 'Brave Search', url: 'https://search.brave.com/search?q=%s' },
    ecosia: { label: 'Ecosia', url: 'https://www.ecosia.org/search?q=%s' },
    google: { label: 'Google', url: 'https://www.google.com/search?q=%s' },
    bing: { label: 'Bing', url: 'https://www.bing.com/search?q=%s' }
};
function webSearch(engine, text) {
    const words = String(text || '').trim();
    if (!words) return null;
    let e = ENGINES[engine];
    if (!e && /^https:\/\/[^\s]+%s/.test(String(engine || ''))) e = { label: String(engine).split('/')[2], url: String(engine) };
    if (!e) e = ENGINES.duckduckgo;
    return { kind: 'web', name: 'Search the web for “' + words + '”', desc: e.label + ' · start with ? to search only the web', glyph: 'globe',
             url: e.url.replace('%s', encodeURIComponent(words)) };
}

// fd's output (one path per line; folders may end in /) as rows, with ~ for the home folder.
function fileRows(text, home) {
    const out = [];
    String(text || '').split('\n').forEach(line => {
        let path = line.trim();
        if (!path.startsWith('/')) return;
        const folder = /\/$/.test(path);
        path = path.replace(/\/+$/, '');
        const at = path.lastIndexOf('/');
        let where = at > 0 ? path.slice(0, at) : '/';
        if (home && (where === home || where.startsWith(home + '/'))) where = '~' + where.slice(home.length);
        out.push({ kind: 'file', name: path.slice(at + 1), desc: where, path: path, glyph: folder ? 'folder' : 'file', folder: folder });
    });
    return out;
}

// Does this look like "10 km to mi" or "72 °F to °C", worth asking qalc even without "="?
// ("in" would be inches to qalc, so only "to".)
function looksLikeConversion(text) {
    return /^\s*[\d.,]+\s*[^\d\s].*\sto\s+\S+\s*$/i.test(String(text || ''));
}

// Frecency: what you open often and lately ranks higher. stats = {id: {n: times, t: last ms}}
// (~/.local/state/arctic/launcher.json). At most +300, fading over weeks.
function frecency(stats, id, now) {
    const s = stats && id ? stats[id] : null;
    if (!s || !(s.n > 0)) return 0;
    const days = Math.max(0, (now - (s.t || 0)) / 86400000);
    const recency = days < 1 ? 1 : days < 7 ? 0.7 : days < 30 ? 0.45 : 0.2;
    return Math.round(Math.min(300, 60 * Math.log2(1 + s.n)) * recency);
}
function remember(stats, id, now, keep) {
    const out = {};
    Object.keys(stats || {}).forEach(k => { out[k] = stats[k]; });
    const s = out[id] || { n: 0, t: 0 };
    out[id] = { n: (s.n || 0) + 1, t: now };
    const ids = Object.keys(out);
    if (ids.length > (keep || 200))
        ids.sort((a, b) => out[b].t - out[a].t).slice(keep || 200).forEach(k => { delete out[k]; });
    return out;
}
