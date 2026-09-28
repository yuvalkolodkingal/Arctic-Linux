// The notification rules (NotificationRules.js): node shell/tests/test-notification-rules.cjs
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
function load(file) {
    const c = {};
    vm.createContext(c);
    vm.runInContext(fs.readFileSync(__dirname + '/../' + file, 'utf8').replace('.pragma library', ''), c);
    return c;
}
const R = load('NotificationRules.js');
const plain = o => JSON.parse(JSON.stringify(o));
const at = (h, m) => new Date(2026, 8, 28, h, m, 0);        // Monday 28 September 2026, local time
const secs = d => Math.floor(d.getTime() / 1000);

// ---- settings file ---------------------------------------------------------------------------
assert.deepEqual(plain(R.parseConfig('')), { history: true, dnd_schedule: { enabled: false, from: '22:00', to: '07:00' }, apps: {} });
for (const bad of ['{', 'null', '[]', '42', '"x"']) assert.equal(R.parseConfig(bad).history, true, bad);
const config = R.parseConfig(JSON.stringify({
    history: false,
    dnd_schedule: { enabled: true, from: '22:30', to: '7:00' },
    apps: {
        'org.signal.Signal': { toasts: true, history: true, allow_during_dnd: false, silence_urgent: true },
        'com.slack.Slack': { toasts: false, junk: 1 },
        Alarms: { allow_during_dnd: true },
        'bad': 'yes',
    },
}));
assert.equal(config.history, false);
assert.deepEqual(plain(config.dnd_schedule), { enabled: true, from: '22:30', to: '7:00' });
assert.deepEqual(Object.keys(config.apps).sort(), ['Alarms', 'com.slack.Slack', 'org.signal.Signal']);
assert.deepEqual(plain(R.appRule(config, 'com.slack.Slack')), { toasts: false, history: true, allow_during_dnd: false, silence_urgent: false });
assert.deepEqual(plain(R.appRule(config, 'nobody')), { toasts: true, history: true, allow_during_dnd: false, silence_urgent: false });
// Broken times keep the defaults.
assert.deepEqual(plain(R.parseConfig('{"dnd_schedule": {"enabled": true, "from": "25:00", "to": "7"}}').dnd_schedule),
                 { enabled: true, from: '22:00', to: '07:00' });
assert.equal(R.parseTime('07:05'), 425);
assert.equal(R.parseTime('24:00'), -1);
assert.equal(R.parseTime('7:60'), -1);

// ---- the do-not-disturb state --------------------------------------------------------------
assert.deepEqual(plain(R.parseDnd('')), { mode: 'off', until: 0, skip: 0 });
assert.deepEqual(plain(R.parseDnd('{"mode":"on","skip":5}')), { mode: 'on', until: 0, skip: 0 });
assert.deepEqual(plain(R.parseDnd('{"mode":"until","until":1759080000.7}')), { mode: 'until', until: 1759080000, skip: 0 });
assert.deepEqual(plain(R.parseDnd('{"mode":"until"}')), { mode: 'off', until: 0, skip: 0 });
assert.deepEqual(plain(R.parseDnd('{"mode":"loud"}')), { mode: 'off', until: 0, skip: 0 });
assert.deepEqual(plain(R.parseDnd('{"mode":"off","skip":1759080000}')), { mode: 'off', until: 0, skip: 1759080000 });

// Schedules, across midnight and not.
const night = { enabled: true, from: '22:00', to: '07:00' };
assert.equal(R.scheduleActive(night, at(23, 0)), true);
assert.equal(R.scheduleActive(night, at(3, 0)), true);
assert.equal(R.scheduleActive(night, at(7, 0)), false);          // the end is exclusive
assert.equal(R.scheduleActive(night, at(21, 59)), false);
assert.equal(R.scheduleActive(night, at(22, 0)), true);
const lunch = { enabled: true, from: '12:00', to: '13:30' };
assert.equal(R.scheduleActive(lunch, at(12, 45)), true);
assert.equal(R.scheduleActive(lunch, at(13, 30)), false);
assert.equal(R.scheduleActive(Object.assign({}, night, { enabled: false }), at(23, 0)), false);
assert.equal(R.scheduleActive({ enabled: true, from: '08:00', to: '08:00' }, at(8, 0)), false);

const noon = at(12, 0), now = secs(noon);
const off = { mode: 'off', until: 0 };
const plainConfig = R.parseConfig('');
assert.equal(R.dndReason(off, plainConfig, now, noon), '');
assert.equal(R.dndReason({ mode: 'on', until: 0 }, plainConfig, now, noon), 'on');
assert.equal(R.dndReason({ mode: 'until', until: now + 60 }, plainConfig, now, noon), 'until');
assert.equal(R.dndReason({ mode: 'until', until: now - 1 }, plainConfig, now, noon), '');   // ran out
const scheduled = R.parseConfig('{"dnd_schedule": {"enabled": true, "from": "22:00", "to": "07:00"}}');
assert.equal(R.dndReason(off, scheduled, secs(at(23, 30)), at(23, 30)), 'schedule');

// Turning it off while the schedule is on rests the schedule until the window closes (07:00).
const late = at(23, 30), lateNow = secs(late);
const rested = R.dndCommand({ mode: 'off', until: 0, skip: 0 }, scheduled, 'toggle', late);
assert.deepEqual(plain(rested), { mode: 'off', until: 0, skip: secs(new Date(2026, 8, 29, 7, 0, 0)) });
assert.equal(R.dndReason(rested, scheduled, lateNow, late), '');
assert.equal(R.dndReason(rested, scheduled, secs(new Date(2026, 8, 29, 23, 0)), new Date(2026, 8, 29, 23, 0)), 'schedule');   // the next night
assert.deepEqual(plain(R.dndCommand(rested, scheduled, 'toggle', late)), { mode: 'on', until: 0, skip: 0 });
assert.equal(R.scheduleEnd(scheduled.dnd_schedule, at(3, 0)), secs(at(7, 0)));   // after midnight: the same morning
assert.equal(R.scheduleEnd(scheduled.dnd_schedule, noon), 0);
assert.deepEqual(plain(R.dndCommand(off, plainConfig, 'toggle', noon)), { mode: 'on', until: 0, skip: 0 });
assert.deepEqual(plain(R.dndCommand({ mode: 'on', until: 0, skip: 0 }, plainConfig, 'toggle', noon)), { mode: 'off', until: 0, skip: 0 });
assert.deepEqual(plain(R.dndCommand(off, plainConfig, '1h', noon)), { mode: 'until', until: now + 3600, skip: 0 });
assert.equal(R.dndCommand(off, plainConfig, 'status', noon), null);

// Durations: an hour from now, and 08:00 the next day (local time, also across a month end).
assert.equal(R.untilFor('1h', noon), now + 3600);
assert.equal(R.untilFor('tomorrow', noon), secs(new Date(2026, 8, 29, 8, 0, 0)));
assert.equal(R.untilFor('tomorrow', new Date(2026, 8, 30, 23, 50)), secs(new Date(2026, 9, 1, 8, 0, 0)));
assert.equal(R.untilFor('forever', noon), 0);

// What the centre says.
assert.equal(R.dndDetail(off, plainConfig, now, noon), 'Off');
assert.equal(R.dndDetail({ mode: 'on', until: 0 }, plainConfig, now, noon), 'On until you turn it off');
assert.equal(R.dndDetail({ mode: 'until', until: secs(at(15, 40)) }, plainConfig, now, noon), 'On until 15:40');
assert.equal(R.dndDetail({ mode: 'until', until: R.untilFor('tomorrow', noon) }, plainConfig, now, noon), 'On until tomorrow, 08:00');
assert.equal(R.dndDetail(off, scheduled, secs(at(23, 30)), at(23, 30)), 'On by schedule until 07:00');

// ---- decide(): every row of Arctic's do-not-disturb rule -----------------------------------
const n = (o) => Object.assign({ appName: 'Signal', desktopEntry: 'org.signal.Signal', urgency: 'normal', transient: false, hints: {} }, o);
const rules = R.parseConfig(JSON.stringify({ apps: {
    'org.signal.Signal': { silence_urgent: true },
    Alarms: { allow_during_dnd: true },
    Muted: { toasts: false },
    Quiet: { history: false },
} }));
// Off: everything pops up and is kept.
assert.deepEqual(plain(R.decide(n({}), '', rules)), { toast: true, keep: true, persist: true });
assert.deepEqual(plain(R.decide(n({ appName: 'Muted', desktopEntry: '' }), '', rules)), { toast: false, keep: true, persist: true });
// On: silenced but kept (nothing is lost)…
assert.deepEqual(plain(R.decide(n({ appName: 'Mail', desktopEntry: '' }), 'on', rules)), { toast: false, keep: true, persist: true });
// …except urgent ones (unless the app hides its urgent ones), allowed apps and Arctic's alerts.
assert.equal(R.decide(n({ appName: 'Mail', desktopEntry: '', urgency: 'critical' }), 'until', rules).toast, true);
assert.equal(R.decide(n({ urgency: 'critical' }), 'schedule', rules).toast, false);            // Signal: silence_urgent
assert.equal(R.decide(n({ appName: 'Alarms', desktopEntry: '' }), 'on', rules).toast, true);
assert.equal(R.decide(n({ appName: 'Muted', desktopEntry: '', urgency: 'critical' }), 'on', rules).toast, false);
const alert = n({ appName: 'Arctic Linux', desktopEntry: '', urgency: 'normal', hints: { 'x-arctic-alert': true } });
assert.equal(R.decide(alert, 'on', rules).toast, true);
assert.equal(R.isSystemAlert(n({ appName: 'Arctic Linux', desktopEntry: '' })), false);          // the hint is needed
assert.equal(R.isSystemAlert(n({ hints: { 'x-arctic-alert': true } })), false);                  // and the name
// Transient notifications and apps kept out of history only pop up; history off = not saved.
assert.deepEqual(plain(R.decide(n({ transient: true }), '', rules)), { toast: true, keep: false, persist: false });
assert.deepEqual(plain(R.decide(n({ appName: 'Quiet', desktopEntry: '' }), '', rules)), { toast: true, keep: false, persist: false });
assert.deepEqual(plain(R.decide(n({}), '', R.parseConfig('{"history": false}'))), { toast: true, keep: true, persist: false });

// ---- toast timeouts ------------------------------------------------------------------------
assert.equal(R.toastTimeout({ urgency: 'low', expireTimeout: -1 }), 5000);
assert.equal(R.toastTimeout({ urgency: 'critical', expireTimeout: -1 }), 0);
assert.equal(R.toastTimeout({ urgency: 'normal', expireTimeout: 0 }), 0);          // the app said "stay"
assert.equal(R.toastTimeout({ urgency: 'critical', expireTimeout: 3000 }), 3000);  // the app's own (ms, as sent)
assert.equal(R.toastTimeout({ urgency: 'normal', expireTimeout: 200 }), 1000);     // never a flash

// ---- synchronous tags ------------------------------------------------------------------------
assert.equal(R.syncTag(n({})), '');
assert.equal(R.syncTag(n({ hints: { 'x-canonical-private-synchronous': 'volume' } })), 'volume');
const existing = [
    { id: 3, appName: 'arctic-osd', desktopEntry: '', sync: 'volume' },
    { id: 2, appName: 'arctic-osd', desktopEntry: '', sync: 'brightness' },
    { id: 1, appName: 'other', desktopEntry: '', sync: 'volume' },
];
assert.deepEqual(plain(R.replacedBySync(existing, { appName: 'arctic-osd', hints: { 'x-canonical-private-synchronous': 'volume' } })), [3]);
assert.deepEqual(plain(R.replacedBySync(existing, { appName: 'arctic-osd', hints: {} })), []);

// ---- grouping for the centre -------------------------------------------------------------
const entries = [
    { id: 5, appName: 'Signal', desktopEntry: 'org.signal.Signal', time: 500 },
    { id: 4, appName: 'Firefox', desktopEntry: '', time: 400 },
    { id: 3, appName: 'Signal Beta', desktopEntry: 'org.signal.Signal', time: 300 },
    { id: 2, appName: '', desktopEntry: '', time: 200 },
    { id: 1, appName: 'Firefox', desktopEntry: '', time: 100 },
];
const groups = R.group(entries);
assert.deepEqual(groups.map(g => g.key), ['org.signal.Signal', 'Firefox', 'unknown']);
assert.deepEqual(groups.map(g => g.items.map(e => e.id)), [[5, 3], [4, 1], [2]]);
assert.equal(groups[0].appName, 'Signal');
assert.equal(groups[2].appName, 'unknown');

// ---- relative times ----------------------------------------------------------------------
assert.equal(R.relativeTime(now - 10, now, noon), 'Now');
assert.equal(R.relativeTime(now - 125, now, noon), '2 min ago');
assert.equal(R.relativeTime(now - 3 * 3600, now, noon), '3 h ago');
assert.equal(R.relativeTime(secs(at(8, 0)) - 86400, now, noon), 'Yesterday');
assert.equal(R.relativeTime(secs(new Date(2026, 8, 20, 9, 0)), now, noon), '20 Sep');
assert.equal(R.relativeTime(now + 30, now, noon), 'Now');                          // clock skew

// ---- history file ------------------------------------------------------------------------
const live = (id, time, o) => Object.assign({ id, appName: 'Signal', appIcon: 'signal', desktopEntry: 'org.signal.Signal', summary: 'Hi ' + id,
    body: 'Body', urgency: 'normal', time, image: '', actions: [{ identifier: 'default', text: 'Open' }], live: true, keep: true, persist: true, sync: '' }, o);
const history = [live(9, 900, { image: 'image://qsimage/9/1' }), live(8, 800, { persist: false }), live(7, 700, { image: 'file:///tmp/a.png' })];
const text = R.serializeHistory(history);
const stored = JSON.parse(text);
assert.equal(stored.version, 1);
assert.deepEqual(stored.items.map(i => i.id), [9, 7]);                            // not-persisted ones are left out
assert.equal(stored.items[0].image, '');                                          // pixmaps are not stored
assert.equal(stored.items[1].image, 'file:///tmp/a.png');
assert.equal('actions' in stored.items[0], false);
const back = R.parseHistory(text);
assert.deepEqual(back.map(e => [e.id, e.live, e.actions.length, e.appName, e.desktopEntry]), [[9, false, 0, 'Signal', 'org.signal.Signal'], [7, false, 0, 'Signal', 'org.signal.Signal']]);
for (const bad of ['', '{', '[]', '{"items": 3}', '{"items": [1, null, {"time": 5}]}']) assert.deepEqual(plain(R.parseHistory(bad)), [], bad);
assert.equal(R.parseHistory('{"items": [{"time": 5, "summary": "x", "urgency": "loud"}]}')[0].urgency, 'normal');
// The cap: 50 kept, the oldest go first.
const many = [];
for (let i = 60; i > 0; i--) many.push(live(i, i * 10));
assert.equal(JSON.parse(R.serializeHistory(many)).items.length, R.HISTORY_CAP);
assert.deepEqual(plain(R.overflow(many)), [10, 9, 8, 7, 6, 5, 4, 3, 2, 1]);
assert.deepEqual(plain(R.overflow(many.slice(0, 3))), []);
assert.equal(R.parseHistory(R.serializeHistory(many)).length, 50);

// ---- apps seen (for Settings) --------------------------------------------------------------
let apps = R.parseApps('');
assert.deepEqual(plain(apps), []);
apps = R.noteApp(apps, live(1, 1000));
assert.deepEqual(plain(apps), [{ key: 'org.signal.Signal', app_name: 'Signal', desktop_entry: 'org.signal.Signal', icon: 'signal', last_seen: 1000 }]);
assert.equal(R.noteApp(apps, live(2, 1500)), null);                               // same app, same hour: no write
apps = R.noteApp(apps, live(3, 1600, { appName: 'Firefox', desktopEntry: '', appIcon: '' }));
assert.deepEqual(apps.map(a => a.key), ['Firefox', 'org.signal.Signal']);
apps = R.noteApp(apps, live(4, 1700));
assert.deepEqual(apps.map(a => a.key), ['org.signal.Signal', 'Firefox']);
assert.deepEqual(plain(R.parseApps(R.serializeApps(apps))), plain(apps));
assert.deepEqual(plain(R.parseApps('{"apps": [{"key": ""}, 3, {"key": "x"}]}')).map(a => a.key), ['x']);

console.log('notification rules: all tests passed');
