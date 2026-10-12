.pragma library
// "What's new" after an Arctic Linux update. Each packaged notes file carries a unique update_id.
// The card appears once per account whenever that id changes. A home without a seen file is a fresh
// account: record the current id without showing it because FirstLogin already welcomes the user.

function clipped(value, limit) {
    return String(value || '').trim().slice(0, limit);
}

function validId(value) {
    return typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/.test(value);
}

// Checked notes: {updateId, title, items: [{icon, title, text}], notesUrl}, or null.
// Keep packaged text bounded so a malformed update cannot make an unusable full-screen card.
function parseNotes(text) {
    let data;
    try {
        data = JSON.parse(text);
    } catch (e) {
        return null;
    }
    if (!data || typeof data !== 'object' || data.schema !== 1 || !validId(data.update_id)
            || !Array.isArray(data.items))
        return null;
    const items = data.items.filter(i => i && typeof i.title === 'string' && typeof i.text === 'string')
        .map(i => ({
            icon: /^[a-z0-9-]{1,48}$/.test(String(i.icon || '')) ? i.icon : 'sparkle',
            title: clipped(i.title, 80),
            text: clipped(i.text, 320)
        }))
        .filter(i => i.title && i.text)
        .slice(0, 6);
    if (!items.length)
        return null;
    const url = typeof data.notes_url === 'string' && /^https:\/\//.test(data.notes_url)
        ? data.notes_url.slice(0, 512) : '';
    return {
        updateId: data.update_id,
        title: clipped(data.title, 120) || 'What’s new',
        items: items,
        notesUrl: url
    };
}

// {show, record}: record is the update id to write immediately (empty means no write).
function decide(seen, notes, live) {
    if (live || !notes)
        return { show: false, record: '' };
    const last = String(seen || '').trim();
    if (!last)
        return { show: false, record: notes.updateId };
    if (last === notes.updateId)
        return { show: false, record: '' };
    return { show: true, record: '' };
}
