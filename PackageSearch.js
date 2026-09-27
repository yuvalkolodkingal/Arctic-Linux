.pragma library

function context(text, cursor) {
    let start = cursor;
    let end = cursor;
    while (start > 0 && !/\s/.test(text[start - 1])) start--;
    while (end < text.length && !/\s/.test(text[end])) end++;
    const token = text.slice(start, end);
    if (start === 0 && (token === 'emerge' || token === '/usr/bin/emerge'))
        return { start: end, end: end, query: '', prefix: ' ', allowed: true };
    return { start: start, end: end, query: token, prefix: '', allowed: !/^[-@<>=!~]/.test(token) };
}

function score(text, query) {
    if (!query) return 0;
    if (text === query) return 10000;
    if (text.startsWith(query)) return 8000 - text.length;
    const substring = text.indexOf(query);
    if (substring >= 0) return 6000 - substring * 8 - text.length;
    let position = -1, first = -1, gaps = 0, bonus = 0;
    for (let i = 0; i < query.length; i++) {
        const next = text.indexOf(query[i], position + 1);
        if (next < 0) return -1;
        if (first < 0) first = next;
        if (position >= 0) gaps += next - position - 1;
        if (next === 0 || '/-_'.includes(text[next - 1])) bonus += 15;
        position = next;
    }
    return 3000 + bonus - gaps * 12 - first * 6 - text.length;
}

function search(packages, query) {
    query = query.toLowerCase().trim();
    if (!query) return packages;
    const ranked = [];
    for (let i = 0; i < packages.length; i++) {
        const atom = packages[i];
        const name = atom.slice(atom.indexOf('/') + 1);
        const nameScore = query.includes('/') ? -1 : score(name.toLowerCase(), query);
        const atomScore = score(atom.toLowerCase(), query);
        const rank = Math.max(nameScore >= 0 ? nameScore + 100 : -1, atomScore);
        if (rank >= 0) ranked.push({atom: atom, rank: rank});
    }
    ranked.sort((a, b) => b.rank - a.rank || a.atom.localeCompare(b.atom));
    return ranked.map(item => item.atom);
}

function complete(text, cursor, atom) {
    const ctx = context(text, cursor);
    const replacement = ctx.prefix + atom;
    return { text: text.slice(0, ctx.start) + replacement + text.slice(ctx.end), cursor: ctx.start + replacement.length };
}
