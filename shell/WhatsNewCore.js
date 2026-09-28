.pragma library
// "What's new" after an Arctic Linux update: whether to show the card (pure functions, tested in
// tests/test-whats-new.cjs). The card shows once, the first time the shell starts on a newer
// Arctic release (VERSION_ID in os-release) than the one recorded in
// ~/.local/state/arctic/whats-new-seen, and only when whats-new.json describes that release. A
// home without the file (a fresh install) records the version and shows nothing: the first
// login has its own welcome.

// "0.10" > "0.9": compare dotted numbers part by part; anything unreadable counts as 0.
function compare(a, b) {
    const pa = String(a || '').split('.'), pb = String(b || '').split('.');
    for (let i = 0; i < Math.max(pa.length, pb.length); i++) {
        const x = parseInt(pa[i], 10) || 0, y = parseInt(pb[i], 10) || 0;
        if (x !== y)
            return x < y ? -1 : 1;
    }
    return 0;
}

// VERSION_ID from os-release text ('' when missing).
function osVersion(text) {
    const m = /^VERSION_ID="?([^"\n]*)"?$/m.exec(String(text || ''));
    return m ? m[1].trim() : '';
}

// The notes, checked: {version, title, items: [{icon, title, text}], notes_url} or null.
function parseNotes(text) {
    let data;
    try {
        data = JSON.parse(text);
    } catch (e) {
        return null;
    }
    if (!data || typeof data !== 'object' || typeof data.version !== 'string' || !Array.isArray(data.items))
        return null;
    const items = data.items.filter(i => i && typeof i.title === 'string' && typeof i.text === 'string')
        .slice(0, 6).map(i => ({ icon: typeof i.icon === 'string' ? i.icon : 'sparkle', title: i.title, text: i.text }));
    if (!items.length)
        return null;
    return { version: data.version, title: typeof data.title === 'string' ? data.title : 'What’s new',
        items: items, notesUrl: typeof data.notes_url === 'string' ? data.notes_url : '' };
}

// {show, record}: show the card; record = the version to write to whats-new-seen now ('' = none).
function decide(version, seen, notes, live) {
    if (live || !version)
        return { show: false, record: '' };
    const last = String(seen || '').trim();
    if (last === '')
        return { show: false, record: version };
    if (compare(version, last) <= 0)
        return { show: false, record: '' };
    if (!notes || notes.version !== version)
        return { show: false, record: version };
    return { show: true, record: '' };
}
