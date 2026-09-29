.pragma library
// Search for Get apps (tests: tests/test-package-search.cjs): completion in the Console, and
// ranked search over names, ids, keywords and summaries for the Flathub and Fedora pages
// (prepareItems / searchItems, at the end).
//
// The index holds dnf package names ("neovim") and Flathub app ids with a "flathub:" prefix
// ("flathub:org.gimp.GIMP"). Which of them are offered depends on the command being typed:
//   neovim …                      a bare name at the start: both kinds (quick install)
//   dnf install|remove|info …     dnf names
//   flatpak install [flathub] …   Flathub ids, inserted without the prefix

const FLATHUB = 'flathub:';
const DNF = ['dnf', 'dnf5', 'sudo'];
const DNF_PACKAGE_VERBS = ['install', 'remove', 'erase', 'uninstall', 'reinstall', 'info', 'upgrade', 'update', 'downgrade', 'list'];
const FLATPAK_PACKAGE_VERBS = ['install', 'uninstall', 'remove', 'info', 'update'];

function tokens(text) {
    return String(text).trim().split(/\s+/).filter(t => t.length);
}

// What the token under the cursor is for:
// {start, end, query, prefix, allowed, source: 'all'|'dnf'|'flathub'}
function context(text, cursor) {
    let start = cursor;
    let end = cursor;
    while (start > 0 && !/\s/.test(text[start - 1])) start--;
    while (end < text.length && !/\s/.test(text[end])) end++;
    const token = text.slice(start, end);
    const before = tokens(text.slice(0, start));
    if (before[0] === 'sudo') before.shift();
    const none = { start: start, end: end, query: token, prefix: '', allowed: false, source: 'all' };
    const tool = before[0] || '';
    const verb = before.slice(1).find(t => !t.startsWith('-')) || '';

    // Cursor right after "dnf install" / "flatpak install": offer names for the next word.
    const whole = before.concat([token]).filter(t => t !== 'sudo');
    if (cursor === text.length && whole.length === 2 && !/\s$/.test(text)) {
        if (DNF.indexOf(whole[0]) >= 0 && DNF_PACKAGE_VERBS.indexOf(whole[1]) >= 0)
            return { start: end, end: end, query: '', prefix: ' ', allowed: true, source: 'dnf' };
        if (whole[0] === 'flatpak' && FLATPAK_PACKAGE_VERBS.indexOf(whole[1]) >= 0)
            return { start: end, end: end, query: '', prefix: ' ', allowed: true, source: 'flathub' };
    }
    if (/^[-@<>=!~/]/.test(token)) return none;
    if (before.length === 0) {
        if (DNF.indexOf(token) >= 0 || token === 'flatpak') return none;
        return { start: start, end: end, query: token, prefix: '', allowed: true, source: 'all' };
    }
    if (DNF.indexOf(tool) >= 0)
        return DNF_PACKAGE_VERBS.indexOf(verb) >= 0 && token !== verb
            ? { start: start, end: end, query: token, prefix: '', allowed: true, source: 'dnf' } : none;
    if (tool === 'flatpak') {
        if (FLATPAK_PACKAGE_VERBS.indexOf(verb) < 0 || token === verb || token === 'flathub') return none;
        return { start: start, end: end, query: token, prefix: '', allowed: true, source: 'flathub' };
    }
    // More bare names after the first one.
    if (before.every(t => !t.startsWith('-')) && DNF.indexOf(tool) < 0 && tool !== 'flatpak')
        return { start: start, end: end, query: token, prefix: '', allowed: true, source: 'all' };
    return none;
}

// Exact, prefix and substring matches (cheap); -1 when the query isn't in the text.
function strictScore(text, query) {
    if (text === query) return 10000;
    if (text.startsWith(query)) return 8000 - text.length;
    const substring = text.indexOf(query);
    if (substring >= 0) return 6000 - substring * 8 - text.length;
    return -1;
}

// Letters in order with gaps ("nvim" in "neovim"); -1 when they aren't all there.
function fuzzyScore(text, query) {
    let position = -1, first = -1, gaps = 0, bonus = 0;
    for (let i = 0; i < query.length; i++) {
        const next = text.indexOf(query[i], position + 1);
        if (next < 0) return -1;
        if (first < 0) first = next;
        if (position >= 0) gaps += next - position - 1;
        if (next === 0 || '/-_.:'.includes(text[next - 1])) bonus += 15;
        position = next;
    }
    // Letters scattered across a long name aren't a useful match.
    if (gaps > Math.max(3, query.length * 2)) return -1;
    return 3000 + bonus - gaps * 12 - first * 6 - text.length;
}

function score(text, query) {
    if (!query) return 0;
    const strict = strictScore(text, query);
    return strict >= 0 ? strict : fuzzyScore(text, query);
}

// prepare(names) -> an index with the lowercase ids and names worked out once, so each
// keystroke only compares strings. search() accepts a prepared index or a plain list.
function prepare(packages) {
    const entries = [], ids = [], names = [], apps = [];
    for (let i = 0; i < packages.length; i++) {
        const entry = packages[i];
        const isApp = entry.startsWith(FLATHUB);
        const id = (isApp ? entry.slice(FLATHUB.length) : entry).toLowerCase();
        entries.push(entry);
        ids.push(id);
        // For app ids, the last part ("gimp" in org.gimp.GIMP) counts as the name.
        names.push(isApp ? id.slice(id.lastIndexOf('.') + 1) : id);
        apps.push(isApp);
    }
    return { prepared: true, entries: entries, ids: ids, names: names, apps: apps, length: entries.length };
}

// search(index, query, source) -> matching entries, best first. The index can hold ~70,000
// names, so the fuzzy pass only runs when exact/prefix/substring matches are few.
function search(packages, query, source, limit) {
    const index = packages && packages.prepared ? packages : prepare(packages || []);
    source = source || 'all';
    limit = limit || 200;
    query = String(query || '').toLowerCase().trim();
    if (query.startsWith(FLATHUB)) { query = query.slice(FLATHUB.length); source = 'flathub'; }
    const strong = [];
    const rest = [];
    for (let i = 0; i < index.length; i++) {
        const isApp = index.apps[i];
        if ((source === 'dnf' && isApp) || (source === 'flathub' && !isApp)) continue;
        if (!query) { strong.push({ entry: index.entries[i], rank: 0 }); continue; }
        const byName = strictScore(index.names[i], query);
        const byId = isApp ? strictScore(index.ids[i], query) : -1;
        const rank = Math.max(byName >= 0 ? byName + (isApp ? 50 : 100) : -1, byId);
        if (rank >= 0) strong.push({ entry: index.entries[i], rank: rank });
        else rest.push(i);
    }
    if (!query) return strong.map(item => item.entry);
    if (strong.length < limit) {
        for (let j = 0; j < rest.length; j++) {
            const i = rest[j], isApp = index.apps[i];
            const byName = fuzzyScore(index.names[i], query);
            const rank = Math.max(byName >= 0 ? byName + (isApp ? 50 : 100) : -1, isApp ? fuzzyScore(index.ids[i], query) : -1);
            if (rank >= 0) strong.push({ entry: index.entries[i], rank: rank });
        }
    }
    strong.sort((a, b) => b.rank - a.rank || a.entry.length - b.entry.length || a.entry.localeCompare(b.entry));
    return strong.map(item => item.entry);
}

function complete(text, cursor, entry) {
    const ctx = context(text, cursor);
    const value = ctx.source === 'flathub' && entry.startsWith(FLATHUB) ? entry.slice(FLATHUB.length) : entry;
    const replacement = ctx.prefix + value;
    return { text: text.slice(0, ctx.start) + replacement + text.slice(ctx.end), cursor: ctx.start + replacement.length };
}

// ---- the Flathub and Fedora pages: search over items -------------------------------------------
// prepareItems([{id, name, summary, keywords?, …}]) -> an index with the lowercase fields worked
// out once. searchItems(index, query, limit) -> items, best first:
//   name      exact / prefix / substring, then fuzzy          weight +100
//   id        the same, on the whole id and its last dotted part (org.gimp.GIMP -> gimp)   +50
//   keywords  substring                                       +20
//   summary   substring only, and only while the matches above are fewer than `limit`
// A display name beats an id, so "gimp" finds GIMP before gimp-help.
function prepareItems(items) {
    const list = items || [];
    const names = [], ids = [], tails = [], keywords = [], summaries = [];
    for (let i = 0; i < list.length; i++) {
        const item = list[i];
        const id = String(item.id || '').toLowerCase();
        names.push(String(item.name || item.id || '').toLowerCase());
        ids.push(id);
        tails.push(id.slice(id.lastIndexOf('.') + 1));
        keywords.push((item.keywords || []).join(' ').toLowerCase());
        summaries.push(String(item.summary || '').toLowerCase());
    }
    return { preparedItems: true, items: list, names: names, ids: ids, tails: tails, keywords: keywords,
             summaries: summaries, length: list.length };
}

function searchItems(prepared, query, limit) {
    const index = prepared && prepared.preparedItems ? prepared : prepareItems(prepared || []);
    limit = limit || 200;
    query = String(query || '').toLowerCase().trim();
    if (!query) return index.items.slice(0, limit);
    const strong = [], rest = [];
    for (let i = 0; i < index.length; i++) {
        const byName = strictScore(index.names[i], query);
        // (package names are their own id: compare them once)
        const same = index.ids[i] === index.names[i] && index.tails[i] === index.names[i];
        const byId = same ? -1 : Math.max(strictScore(index.ids[i], query), strictScore(index.tails[i], query));
        const byKeyword = index.keywords[i] && index.keywords[i].indexOf(query) >= 0 ? 6000 : -1;
        const rank = Math.max(byName >= 0 ? byName + 100 : -1, byId >= 0 ? byId + 50 : -1, byKeyword >= 0 ? byKeyword + 20 : -1);
        if (rank >= 0) strong.push({ i: i, rank: rank });
        else rest.push(i);
    }
    if (strong.length < limit) {
        const loose = [];
        for (let j = 0; j < rest.length; j++) {
            const i = rest[j];
            const byName = fuzzyScore(index.names[i], query);
            const byId = index.tails[i] === index.names[i] ? -1 : fuzzyScore(index.tails[i], query);
            const rank = Math.max(byName >= 0 ? byName + 100 : -1, byId >= 0 ? byId + 50 : -1);
            if (rank >= 0) strong.push({ i: i, rank: rank });
            else loose.push(i);
        }
        // Summaries last: "photo" finds GIMP by what it does.
        if (strong.length < limit && query.length > 2) {
            for (let j = 0; j < loose.length; j++) {
                const at = index.summaries[loose[j]].indexOf(query);
                if (at >= 0) strong.push({ i: loose[j], rank: 1000 - at });
            }
        }
    }
    strong.sort((a, b) => b.rank - a.rank || index.names[a.i].length - index.names[b.i].length
                          || (index.names[a.i] < index.names[b.i] ? -1 : index.names[a.i] > index.names[b.i] ? 1 : 0));
    const out = [];
    for (let k = 0; k < strong.length && k < limit; k++) out.push(index.items[strong[k].i]);
    return out;
}
