.pragma library
// The on-screen display's sizes and timing (Osd.qml). Pure functions, tested in
// tests/test-osd-model.cjs.
//
// Two kinds: a level (icon, bar, value: volume, brightness) and a notice (icon and a few words,
// "Caps Lock on", with an optional detail after " · ").

// How long it stays: a level 1.2 s after the last change; a notice 1.6 s, plus 60 ms for every
// character beyond 20, at most 3 s.
function duration(kind, text, detail) {
    if (kind !== 'notice') return 1200;
    const n = String(text || '').length + (detail ? String(detail).length + 3 : 0);
    return Math.min(3000, 1600 + Math.max(0, n - 20) * 60);
}

// The pill's width: a level is 280; a notice fits its words, between 200 and 420 (longer text
// is elided).
function width(kind, contentWidth) {
    if (kind !== 'notice') return 280;
    return Math.round(Math.max(200, Math.min(420, Number(contentWidth) || 0)));
}

// A design icon name, or "info" for one the shell doesn't have.
function icon(name, known) {
    return name && known(String(name)) ? String(name) : 'info';
}
