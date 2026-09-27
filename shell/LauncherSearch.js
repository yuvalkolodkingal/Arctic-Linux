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
    return query.length >= 3 ? fuzzyScore(candidate.name, query) : -1;
}

// rank(candidates, query) -> matching candidates, best first (all of them, by name, when empty).
function rank(candidates, query) {
    query = String(query || '').trim().toLowerCase();
    if (!query) return candidates.slice().sort((a, b) => String(a.name).localeCompare(String(b.name)));
    const scored = [];
    for (let i = 0; i < candidates.length; i++) {
        const s = score(candidates[i], query);
        if (s >= 0) scored.push({ item: candidates[i], s: s });
    }
    scored.sort((a, b) => b.s - a.s || String(a.item.name).localeCompare(String(b.item.name)));
    return scored.map(x => x.item);
}

// What the query line means: {mode: 'calc'|'command'|'search', text}
function mode(query) {
    const q = String(query || '');
    const t = q.replace(/^\s+/, '');
    if (t.startsWith('=')) return { mode: 'calc', text: t.slice(1).trim() };
    if (t.startsWith('>')) return { mode: 'command', text: t.slice(1).trim() };
    return { mode: 'search', text: q.trim() };
}
