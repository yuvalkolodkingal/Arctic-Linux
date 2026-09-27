.pragma library
// "Updates ready" for the bar, from /var/lib/arctic/update-status.json (written as root by
// arctic-update, see packaging/updates). Pure functions (tested in tests/test-update-status.cjs).
//
// The file: {state: idle|checking|downloading|ready|failed, packages, download_mb, staged_at,
// checked_at, channel, auto, armed, message, updated_at}. An update is waiting for the next
// restart when the state is "ready", it was armed (scheduled for the next boot) and the
// /system-update link still exists: a dnf transaction after the download removes the link.

const EMPTY = { state: 'idle', packages: 0, download_mb: 0, staged_at: '', armed: false, message: '' };

function parse(text) {
    let data = null;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    const out = Object.assign({}, EMPTY);
    if (!data || typeof data !== 'object' || Array.isArray(data)) return out;
    if (typeof data.state === 'string') out.state = data.state;
    const packages = Number(data.packages);
    out.packages = Number.isFinite(packages) && packages > 0 ? Math.floor(packages) : 0;
    const mb = Number(data.download_mb);
    out.download_mb = Number.isFinite(mb) && mb > 0 ? mb : 0;
    out.staged_at = typeof data.staged_at === 'string' ? data.staged_at : '';
    out.armed = data.armed === true;
    out.message = typeof data.message === 'string' ? data.message : '';
    return out;
}

function isReady(status, linked, live) {
    return !live && !!status && status.state === 'ready' && status.armed === true && status.packages > 0 && linked === true;
}

function plural(n, word) {
    return n + ' ' + word + (n === 1 ? '' : 's');
}

// 0.4 MB · 12 MB · 1.2 GB (empty when the size isn't known).
function size(mb) {
    if (!(mb > 0)) return '';
    if (mb >= 1000) return (mb / 1024).toFixed(1) + ' GB';
    if (mb >= 10) return Math.round(mb) + ' MB';
    return Math.max(mb, 0.1).toFixed(1) + ' MB';
}

// "12 updates · 84 MB"
function summary(status) {
    const s = size(status.download_mb);
    return plural(status.packages, 'update') + (s ? ' · ' + s : '');
}

// The popover's sentence.
function detail(status) {
    const s = size(status.download_mb);
    const n = status.packages;
    return plural(n, 'update') + (s ? ' (' + s + ')' : '') + (n === 1 ? ' is' : ' are')
        + ' downloaded and will be installed the next time you restart, before the desktop starts.';
}

// The desktop notification's body.
function notification(status) {
    return plural(status.packages, 'update') + (status.packages === 1 ? ' is' : ' are')
        + ' ready. ' + (status.packages === 1 ? 'It installs' : 'They install') + ' the next time you restart.';
}

// One notification per downloaded update: its staged_at, remembered by the shell.
function notifyKey(status) {
    return status && status.staged_at ? String(status.staged_at) : '';
}

function shouldNotify(status, ready, notified) {
    const key = notifyKey(status);
    return !!ready && key !== '' && key !== String(notified || '').trim();
}
