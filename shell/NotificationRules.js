.pragma library
// Arctic's notification rules, for NotificationService.qml. Pure functions (tested in
// tests/test-notification-rules.cjs).
//
// What a notification does: decide() says whether it pops up as a toast, stays in the centre
// after its toast (keep) and is saved across restarts (persist). Do not disturb is Arctic's own
// rule: silenced notifications still go to the centre, and Arctic's system alerts, urgent
// notifications (unless the app is set to "hide its urgent notifications") and apps allowed
// during do not disturb still pop up. (Omarchy blocks urgent ones too, because chat apps mark
// everything urgent; here that is a per-app switch in Settings.)
//
// Files: ~/.config/arctic/notifications.json (Settings writes it) → parseConfig();
// ~/.local/state/arctic/notifications/dnd.json → parseDnd(); history.json → parseHistory().

var HISTORY_CAP = 50;
var APPS_CAP = 100;
var TIMEOUT_LOW = 5000;
var TIMEOUT_NORMAL = 8000;
var TOMORROW_HOUR = 8;          // "Until tomorrow" ends at 08:00 the next day, local time
var SYNC_HINT = 'x-canonical-private-synchronous';
var ALERT_HINT = 'x-arctic-alert';
var SYSTEM_APP = 'Arctic Linux';

var RULE_DEFAULTS = { toasts: true, history: true, allow_during_dnd: false, silence_urgent: false };

function isObject(o) { return o !== null && typeof o === 'object' && !Array.isArray(o); }
function str(v) { return typeof v === 'string' ? v : ''; }
function pad(n) { return (n < 10 ? '0' : '') + n; }

// The key a notification is grouped and ruled by: its desktop entry, else its app name.
function appKey(n) {
    var key = str(n && n.desktopEntry).trim() || str(n && n.desktop_entry).trim() || str(n && n.appName).trim() || str(n && n.app_name).trim();
    return key || 'unknown';
}

// ---- settings (~/.config/arctic/notifications.json) ---------------------------------------

// "HH:MM" → minutes since midnight, or -1.
function parseTime(text) {
    var m = /^(\d{1,2}):(\d{2})$/.exec(str(text).trim());
    if (!m) return -1;
    var h = Number(m[1]), min = Number(m[2]);
    return h < 24 && min < 60 ? h * 60 + min : -1;
}

function parseConfig(text) {
    var data = null;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    var out = { history: true, dnd_schedule: { enabled: false, from: '22:00', to: '07:00' }, apps: {} };
    if (!isObject(data)) return out;
    if (data.history === false) out.history = false;
    var s = data.dnd_schedule;
    if (isObject(s)) {
        out.dnd_schedule.enabled = s.enabled === true;
        if (parseTime(s.from) >= 0) out.dnd_schedule.from = s.from.trim();
        if (parseTime(s.to) >= 0) out.dnd_schedule.to = s.to.trim();
    }
    if (isObject(data.apps)) {
        Object.keys(data.apps).forEach(function (key) {
            var r = data.apps[key];
            if (!isObject(r)) return;
            var rule = {};
            Object.keys(RULE_DEFAULTS).forEach(function (k) { if (typeof r[k] === 'boolean') rule[k] = r[k]; });
            out.apps[key] = rule;
        });
    }
    return out;
}

// One app's rule with the defaults filled in.
function appRule(config, key) {
    var own = config && config.apps && isObject(config.apps[key]) ? config.apps[key] : {};
    var out = {};
    Object.keys(RULE_DEFAULTS).forEach(function (k) { out[k] = typeof own[k] === 'boolean' ? own[k] : RULE_DEFAULTS[k]; });
    return out;
}

// ---- do not disturb ------------------------------------------------------------------------

// dnd.json: {"mode": "off" | "on" | "until", "until": <unix seconds>, "skip": <unix seconds>}.
// `skip`: turned off by hand while the schedule was on; the schedule rests until then.
function parseDnd(text) {
    var data = null;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    if (!isObject(data)) return { mode: 'off', until: 0, skip: 0 };
    var until = Number(data.until), skip = Number(data.skip);
    skip = Number.isFinite(skip) && skip > 0 ? Math.floor(skip) : 0;
    if (data.mode === 'on') return { mode: 'on', until: 0, skip: 0 };
    if (data.mode === 'until' && Number.isFinite(until) && until > 0) return { mode: 'until', until: Math.floor(until), skip: 0 };
    return { mode: 'off', until: 0, skip: skip };
}

// Is the schedule's window open at `date` (a local Date)? A window may cross midnight
// (22:00–07:00); from == to is an empty window.
function scheduleActive(schedule, date) {
    if (!schedule || schedule.enabled !== true) return false;
    var from = parseTime(schedule.from), to = parseTime(schedule.to);
    if (from < 0 || to < 0 || from === to) return false;
    var now = date.getHours() * 60 + date.getMinutes();
    return from < to ? now >= from && now < to : now >= from || now < to;
}

// When the schedule's current window closes (unix seconds), or 0 when it isn't open.
function scheduleEnd(schedule, date) {
    if (!scheduleActive(schedule, date)) return 0;
    var to = parseTime(schedule.to);
    var end = new Date(date.getFullYear(), date.getMonth(), date.getDate(), Math.floor(to / 60), to % 60, 0);
    if (end <= date) end = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1, Math.floor(to / 60), to % 60, 0);
    return Math.floor(end.getTime() / 1000);
}

// Why do not disturb is on right now: 'on' (until turned off), 'until' (timed), 'schedule',
// or '' (off). `now` is unix seconds, `date` the same moment as a local Date.
function dndReason(dnd, config, now, date) {
    if (dnd && dnd.mode === 'on') return 'on';
    if (dnd && dnd.mode === 'until' && dnd.until > now) return 'until';
    if (config && scheduleActive(config.dnd_schedule, date) && !(dnd && dnd.skip > now)) return 'schedule';
    return '';
}

// The state after a command from the bell, the centre, arctic-dnd or Settings: 'on', 'off',
// 'toggle', '1h' or 'tomorrow'. Turning it off while the schedule is on rests the schedule
// until its window closes.
function dndCommand(dnd, config, command, date) {
    var now = Math.floor(date.getTime() / 1000);
    var active = dndReason(dnd, config, now, date) !== '';
    if (command === 'toggle') command = active ? 'off' : 'on';
    if (command === 'on') return { mode: 'on', until: 0, skip: 0 };
    if (command === '1h' || command === 'tomorrow') return { mode: 'until', until: untilFor(command, date), skip: 0 };
    if (command === 'off') return { mode: 'off', until: 0, skip: config ? scheduleEnd(config.dnd_schedule, date) : 0 };
    return null;
}

// The end of a timed do not disturb for a choice in the centre or Settings: '1h' or
// 'tomorrow' (08:00 the next day). Unix seconds.
function untilFor(choice, date) {
    var now = Math.floor(date.getTime() / 1000);
    if (choice === '1h') return now + 3600;
    if (choice === 'tomorrow') {
        var d = new Date(date.getFullYear(), date.getMonth(), date.getDate() + 1, TOMORROW_HOUR, 0, 0);
        return Math.floor(d.getTime() / 1000);
    }
    return 0;
}

function clock(date) { return pad(date.getHours()) + ':' + pad(date.getMinutes()); }

// The do-not-disturb row's detail line in the centre and Settings.
function dndDetail(dnd, config, now, date) {
    var reason = dndReason(dnd, config, now, date);
    if (reason === 'on') return 'On until you turn it off';
    if (reason === 'until') {
        var end = new Date(dnd.until * 1000);
        var sameDay = end.getFullYear() === date.getFullYear() && end.getMonth() === date.getMonth() && end.getDate() === date.getDate();
        return sameDay ? 'On until ' + clock(end) : 'On until tomorrow, ' + clock(end);
    }
    if (reason === 'schedule') return 'On by schedule until ' + config.dnd_schedule.to;
    return 'Off';
}

// ---- one notification ----------------------------------------------------------------------

// Arctic's own alerts (critical battery, a failed update) always pop up.
function isSystemAlert(n) {
    var hints = n && isObject(n.hints) ? n.hints : {};
    return str(n && n.appName) === SYSTEM_APP && (hints[ALERT_HINT] === true || hints[ALERT_HINT] === 1);
}

// n: {appName, desktopEntry, urgency: 'low'|'normal'|'critical', transient, hints}.
// dnd: the dndReason() ('' = off). Returns {toast, keep, persist}.
function decide(n, dnd, config) {
    var rule = appRule(config, appKey(n));
    var keep = n.transient !== true && rule.history;
    var out = { toast: true, keep: keep, persist: keep && !(config && config.history === false) };
    if (isSystemAlert(n)) return out;
    if (!rule.toasts) out.toast = false;
    else if (dnd) out.toast = rule.allow_during_dnd || (n.urgency === 'critical' && !rule.silence_urgent);
    return out;
}

// How long a toast stays, in ms; 0 = until dismissed. The app's own timeout when it set one
// (expire_timeout > 0, in ms as sent: Fedora's Quickshell snapshot passes it through), 0 from
// the app means "stay"; otherwise low 5 s, normal 8 s, critical until dismissed.
function toastTimeout(n) {
    var t = Number(n.expireTimeout);
    if (Number.isFinite(t) && t > 0) return Math.max(1000, Math.round(t));
    if (t === 0) return 0;
    if (n.urgency === 'critical') return 0;
    return n.urgency === 'low' ? TIMEOUT_LOW : TIMEOUT_NORMAL;
}

// The x-canonical-private-synchronous tag ('' when none): a new notification with the same
// tag from the same app replaces the previous one (volume and brightness style messages).
function syncTag(n) {
    var hints = n && isObject(n.hints) ? n.hints : {};
    var tag = hints[SYNC_HINT];
    return tag === undefined || tag === null || tag === '' ? '' : String(tag);
}

// Entries (newest first) that a new notification with this sync tag replaces.
function replacedBySync(entries, n) {
    var tag = syncTag(n);
    if (!tag) return [];
    var key = appKey(n);
    return entries.filter(function (e) { return e.sync === tag && appKey(e) === key; }).map(function (e) { return e.id; });
}

// ---- the centre ------------------------------------------------------------------------------

// Entries (newest first) grouped by app, newest group first:
// [{key, appName, appIcon, desktopEntry, items: [...], time}].
function group(entries) {
    var groups = [], byKey = {};
    entries.forEach(function (e) {
        var key = appKey(e);
        var g = byKey[key];
        if (!g) {
            g = { key: key, appName: str(e.appName) || key, appIcon: str(e.appIcon), desktopEntry: str(e.desktopEntry), items: [], time: e.time };
            byKey[key] = g;
            groups.push(g);
        }
        g.items.push(e);
        if (e.time > g.time) g.time = e.time;
    });
    groups.sort(function (a, b) { return b.time - a.time; });
    return groups;
}

var MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// "Now", "5 min ago", "3 h ago", "Yesterday", "28 Sep". t and now in unix seconds.
function relativeTime(t, now, date) {
    var s = Math.max(0, now - t);
    if (s < 60) return 'Now';
    if (s < 3600) return Math.floor(s / 60) + ' min ago';
    var then = new Date(t * 1000);
    var today = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    var yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
    if (then >= today) return Math.floor(s / 3600) + ' h ago';
    if (then >= yesterday) return 'Yesterday';
    return then.getDate() + ' ' + MONTHS[then.getMonth()];
}

// ---- history (~/.local/state/arctic/notifications/history.json) ------------------------------

var URGENCIES = ['low', 'normal', 'critical'];

// One stored item → an entry for the centre (restored: no live notification, no actions).
function fromStored(item) {
    if (!isObject(item)) return null;
    var id = Number(item.id), time = Number(item.time);
    if (!Number.isFinite(time) || time <= 0) return null;
    var summary = str(item.summary), body = str(item.body);
    if (!summary && !body) return null;
    var image = str(item.image);
    return {
        id: Number.isFinite(id) ? id : 0, appName: str(item.app_name), appIcon: str(item.app_icon),
        desktopEntry: str(item.desktop_entry), summary: summary, body: body,
        urgency: URGENCIES.indexOf(item.urgency) >= 0 ? item.urgency : 'normal', time: Math.floor(time),
        image: /^file:\/\//.test(image) ? image : '', actions: [], live: false, keep: true, persist: true, sync: ''
    };
}

function toStored(e) {
    return {
        id: e.id, app_name: e.appName, app_icon: e.appIcon, desktop_entry: e.desktopEntry, summary: e.summary,
        body: e.body, urgency: e.urgency, time: e.time,
        // Pixmaps sent as image data live only as long as the notification; files are kept.
        image: /^file:\/\//.test(str(e.image)) ? e.image : ''
    };
}

function parseHistory(text) {
    var data = null;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    if (!isObject(data) || !Array.isArray(data.items)) return [];
    var out = [];
    data.items.forEach(function (item) { var e = fromStored(item); if (e) out.push(e); });
    out.sort(function (a, b) { return b.time - a.time; });
    return out.slice(0, HISTORY_CAP);
}

function serializeHistory(entries) {
    var items = entries.filter(function (e) { return e.persist === true; }).slice(0, HISTORY_CAP).map(toStored);
    return JSON.stringify({ version: 1, items: items }, null, 1) + '\n';
}

// Ids of the entries past the cap (entries newest first).
function overflow(entries, cap) {
    return entries.slice(cap || HISTORY_CAP).map(function (e) { return e.id; });
}

// apps.json: the apps seen, for the rules list in Settings (newest first, capped).
function parseApps(text) {
    var data = null;
    try { data = JSON.parse(String(text || '')); } catch (e) { data = null; }
    if (!isObject(data) || !Array.isArray(data.apps)) return [];
    return data.apps.filter(function (a) { return isObject(a) && str(a.key) !== ''; }).map(function (a) {
        return { key: a.key, app_name: str(a.app_name) || a.key, desktop_entry: str(a.desktop_entry), icon: str(a.icon), last_seen: Number(a.last_seen) || 0 };
    });
}

// The apps list with this notification's app moved to the front (null when nothing changed
// that is worth a write: the same app again within an hour).
function noteApp(apps, e) {
    var key = appKey(e);
    var old = null, rest = [];
    apps.forEach(function (a) { if (a.key === key) old = a; else rest.push(a); });
    if (old && apps[0] === old && e.time - old.last_seen < 3600 && old.app_name === (e.appName || key)) return null;
    var entry = { key: key, app_name: e.appName || key, desktop_entry: e.desktopEntry || '', icon: e.appIcon || '', last_seen: e.time };
    return [entry].concat(rest).slice(0, APPS_CAP);
}

function serializeApps(apps) {
    return JSON.stringify({ version: 1, apps: apps }, null, 1) + '\n';
}
