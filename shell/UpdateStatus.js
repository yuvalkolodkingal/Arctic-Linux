.pragma library
// "Updates ready" for the bar, from /var/lib/arctic/update-status.json (written as root by
// arctic-update, see packaging/updates). Pure functions (tested in tests/test-update-status.cjs).
//
// The file: {state: idle|checking|downloading|ready|failed, packages, download_mb, staged_at,
// notify_key, checked_at, channel, auto, armed, message, boot_failures, install_error,
// install_failed_at, updated_at}. An update is waiting for the next restart when the state is
// "ready", it was armed (scheduled for the next boot) and the /system-update link still exists:
// a dnf transaction after the download removes the link. install_failed_at: when installing
// the scheduled updates at a restart failed (boot_failures in a row; from 2, automatic
// installs stop until `arctic-update now`).

const EMPTY = { state: 'idle', packages: 0, download_mb: 0, staged_at: '', notify_key: '', armed: false, message: '',
                boot_failures: 0, install_error: '', install_failed_at: '' };

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
    out.notify_key = typeof data.notify_key === 'string' ? data.notify_key : '';
    out.armed = data.armed === true;
    out.message = typeof data.message === 'string' ? data.message : '';
    const failures = Number(data.boot_failures);
    out.boot_failures = Number.isFinite(failures) && failures > 0 ? Math.floor(failures) : 0;
    out.install_error = typeof data.install_error === 'string' ? data.install_error : '';
    out.install_failed_at = typeof data.install_failed_at === 'string' ? data.install_failed_at : '';
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

// One notification per downloaded set of updates: its notify_key (the same updates downloaded
// again by the next daily check keep it), else staged_at; remembered by the shell.
function notifyKey(status) {
    if (!status) return '';
    return String(status.notify_key || status.staged_at || '');
}

function shouldNotify(status, ready, notified) {
    const key = notifyKey(status);
    return !!ready && key !== '' && key !== String(notified || '').trim();
}

// ---- installing at the restart failed --------------------------------------------------------

// One notification per failure: its time, remembered by the shell.
function failureKey(status) {
    return status && status.boot_failures > 0 && status.install_failed_at ? String(status.install_failed_at) : '';
}

function shouldNotifyFailure(status, live, notified) {
    const key = failureKey(status);
    return !live && key !== '' && key !== String(notified || '').trim();
}

function failureNotification(status) {
    const why = status.install_error && status.install_error !== 'see dnf5 offline log'
        ? ' (' + status.install_error.slice(0, 160) + ')' : '';
    if (status.boot_failures >= 2) {
        return 'Installing updates failed again at the last restart' + why + '. Automatic updates are paused: '
            + 'run arctic-update now to try again.';
    }
    return 'The updates couldn\'t be installed at the last restart' + why + '. They will be tried again at the next restart.';
}
