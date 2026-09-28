pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Services.Notifications
import Quickshell.Wayland
import "NotificationRules.js" as Rules

// The shell's notification server: it owns org.freedesktop.Notifications in the Quickshell
// session (mako stays for the waybar fallback) and feeds the toasts (Toasts.qml), the centre
// under the bell (NotificationCenter.qml), the lock screen's count and do not disturb.
//
// Every notification is tracked at once and only closed on purpose (dismissed from the centre,
// its action run, or expired when the app asked for a timeout), so an app waiting on an action
// (`notify-send -A … -w`) keeps waiting while the notification sits in the centre. What pops up
// and what is kept is NotificationRules.js. State lives in ~/.local/state/arctic/notifications/
// (history.json: the centre across restarts, capped at 50; dnd.json; apps.json: the apps seen,
// for Settings); Settings writes ~/.config/arctic/notifications.json (schedule, per-app rules).
//
// Owning the name: checked a second after start (gdbus asks the bus for the owner's pid).
// If mako was started by an early `notify-send` (D-Bus activation), it is stopped and the
// server takes the name when it is released. If nobody could take it, mako is started as the
// fallback (`arctic-session mako --fallback`), like the polkit agent. Another daemon (dunst,
// swaync) is left alone: `owned` stays false and the bell falls back to DndService's makoctl path.
Singleton {
    id: service

    readonly property string stateDir: (Quickshell.env('XDG_STATE_HOME') || Session.home + '/.local/state') + '/arctic/notifications'
    property bool owned: false
    property bool checked: false
    property string foreign: ''         // the process that owns the name instead ('' = none known)
    // Newest first: plain objects {id, nid, appName, appIcon, desktopEntry, summary, body,
    // urgency, time, image, actions: [{identifier, text}], hasDefault, value, live, keep,
    // persist, sync}. `live` while the app's notification is open (its actions work).
    property var entries: []
    readonly property var centreEntries: entries.filter(e => e.keep)
    readonly property int count: centreEntries.length
    property int unseen: 0              // kept since the centre was last opened
    property bool locked: false         // set by LockScreen's lock() and unlock
    property int lockedCount: 0         // kept while the screen was locked
    property var config: Rules.parseConfig('')
    property var dnd: ({ mode: 'off', until: 0, skip: 0 })
    property var apps: []
    property real now: Date.now() / 1000
    readonly property string dndReason: Rules.dndReason(dnd, config, Math.floor(now), new Date(now * 1000))
    readonly property bool dndActive: dndReason !== ''
    readonly property string dndDetail: Rules.dndDetail(dnd, config, Math.floor(now), new Date(now * 1000))
    property alias toastModel: toastList
    readonly property int maxToasts: 3

    // Session-local ids (the server's own ids restart from 1 with every shell).
    property int lastId: 0
    // id → the live Notification, and id → the toast clock {left, since, hover}. Plain maps:
    // nothing binds to them.
    property var live: ({})
    property var clocks: ({})
    property bool historyLoaded: false

    function find(id) {
        for (let i = 0; i < entries.length; i++) if (entries[i].id === id) return entries[i];
        return null;
    }
    function touch() { entries = entries.slice(); }
    function tick() { now = Date.now() / 1000; }

    // ---- incoming ---------------------------------------------------------------------------
    function urgencyName(u) { return u === NotificationUrgency.Critical ? 'critical' : u === NotificationUrgency.Low ? 'low' : 'normal'; }
    function describe(n, e) {
        const hints = n.hints || {};
        const value = Number(hints.value);
        e.nid = n.id;
        e.appName = n.appName || '';
        e.appIcon = n.appIcon || '';
        e.desktopEntry = n.desktopEntry || '';
        e.summary = n.summary || '';
        e.body = n.body || '';
        e.urgency = urgencyName(n.urgency);
        e.image = n.image || '';
        e.actions = (n.actions || []).filter(a => a.identifier !== 'default').map(a => ({ identifier: a.identifier, text: a.text }));
        e.hasDefault = (n.actions || []).some(a => a.identifier === 'default');
        e.value = Number.isFinite(value) && value >= 0 && value <= 100 ? Math.round(value) : -1;
        e.resident = n.resident;
        e.sync = Rules.syncTag({ hints: hints });
        e.time = Math.floor(Date.now() / 1000);
        return e;
    }
    function receive(n, adopted) {
        n.tracked = true;
        tick();
        const e = describe(n, { id: ++lastId, live: true });
        const facts = { appName: e.appName, desktopEntry: e.desktopEntry, urgency: e.urgency, transient: n.transient, hints: n.hints || {} };
        const decision = Rules.decide(facts, dndReason, config);
        e.keep = decision.keep;
        e.persist = decision.persist;
        e.toasted = decision.toast;
        // A newer message with the same synchronous tag takes the old one's place.
        const replaced = Rules.replacedBySync(entries, facts);
        let slot = -1;
        replaced.forEach(id => { const at = toastIndex(id); if (at >= 0 && slot < 0) slot = at; drop(id); });
        // Closing it from inside Notify would send NotificationClosed before its id (the
        // snapshot lacks Quickshell's ordering fix), so that waits for the next turn.
        if (!decision.toast && !decision.keep) { later(() => n.dismiss()); return; }
        live[e.id] = n;
        const id = e.id;
        n.closed.connect(reason => service.closedByApp(id, reason));
        // replaces_id: the server updates the same object in place.
        const update = () => { updates[id] = true; later(service.flushUpdates); };
        n.summaryChanged.connect(update);
        n.bodyChanged.connect(update);
        n.actionsChanged.connect(update);
        n.hintsChanged.connect(update);
        entries = [e].concat(entries);
        overflow();
        if (e.keep) {
            if (!adopted) unseen++;
            if (locked && !adopted) lockedCount++;
            noteApp(e);
        }
        if (decision.toast && !adopted && !locked) showToast(id, Rules.toastTimeout(n), slot);
        else if (!e.keep) later(() => service.remove(id));
        save();
    }
    // Work for the next turn of the event loop. (Qt.callLater runs a function once per turn
    // with the last arguments given, so each job is queued here instead.)
    property var jobs: []
    property var updates: ({})
    function later(job) {
        jobs.push(job);
        Qt.callLater(service.runJobs);
    }
    function runJobs() {
        const run = jobs;
        jobs = [];
        run.forEach(job => { try { job(); } catch (e) { console.warn('Arctic notifications:', e); } });
    }
    function flushUpdates() {
        const ids = Object.keys(updates).map(Number);
        updates = {};
        ids.forEach(id => updated(id));
    }
    function updated(id) {
        const e = find(id), n = live[id];
        if (!e || !n) return;
        describe(n, e);
        entries = [e].concat(entries.filter(x => x.id !== id));
        if (e.toasted && !locked) showToast(id, Rules.toastTimeout(n), toastIndex(id));
        save();
    }
    // The app closed it (CloseRequested: it's no longer relevant), it expired (the app's
    // timeout: kept as history), or it was dismissed (by us, or by running an action).
    function closedByApp(id, reason) {
        delete live[id];
        const e = find(id);
        if (!e) return;
        hideToast(id);
        if (reason === NotificationCloseReason.CloseRequested || !e.keep) {
            entries = entries.filter(x => x.id !== id);
        } else {
            e.live = false;
            e.actions = [];
            e.hasDefault = false;
            touch();
        }
        save();
    }
    // Remove an entry for good, closing the app's notification if it is still open.
    function drop(id) {
        const n = live[id];
        delete live[id];
        hideToast(id);
        entries = entries.filter(x => x.id !== id);
        if (n) n.dismiss();
    }
    function overflow() { Rules.overflow(centreEntries).forEach(id => drop(id)); }

    // ---- toasts -----------------------------------------------------------------------------
    function toastIndex(id) {
        for (let i = 0; i < toastList.count; i++) if (toastList.get(i).nid === id) return i;
        return -1;
    }
    function showToast(id, timeout, slot) {
        clocks[id] = { left: timeout, since: 0, hover: false };
        const at = toastIndex(id);
        if (at >= 0) {
            if (slot >= 0 && at !== slot) toastList.move(at, slot, 1);
            else if (slot < 0 && at !== 0) toastList.move(at, 0, 1);
            return;
        }
        toastList.insert(slot >= 0 ? Math.min(slot, toastList.count) : 0, { nid: id });
    }
    function hideToast(id) {
        const at = toastIndex(id);
        if (at >= 0) toastList.remove(at, 1);
        delete clocks[id];
    }
    function hoverToast(id, hovering) {
        const c = clocks[id];
        if (c) c.hover = hovering;
    }
    // A toast's time ran out or it was closed: hide it; expire the notification when the app
    // asked for a timeout; drop it when it isn't kept in the centre.
    function dismissToast(id) {
        hideToast(id);
        const e = find(id), n = live[id];
        if (!e) return;
        if (!e.keep) drop(id);
        else if (n && n.expireTimeout > 0) n.expire();
    }
    function countDown() {
        if (locked) return;
        const t = Date.now();
        const due = [];
        for (let i = 0; i < Math.min(maxToasts, toastList.count); i++) {
            const id = toastList.get(i).nid, c = clocks[id];
            if (!c || c.left <= 0) continue;
            if (c.hover) { if (c.since) { c.left -= t - c.since; c.since = 0; } continue; }
            if (!c.since) c.since = t;
            else if (t - c.since >= c.left) due.push(id);
        }
        due.forEach(id => dismissToast(id));
    }

    // ---- actions (toasts, the centre, IPC) ----------------------------------------------------
    // Run an action; the app closes a non-resident notification itself after that.
    function invokeAction(id, identifier) {
        const n = live[id];
        if (!n) return false;
        const action = (n.actions || []).find(a => a.identifier === identifier);
        if (!action) return false;
        hideToast(id);
        if (!n.resident) {
            delete live[id];
            entries = entries.filter(x => x.id !== id);
            save();
        }
        action.invoke();
        return true;
    }
    // A click on a toast or card (Enter in the centre): the default action, else the app's
    // window, else the app itself (entries from before a restart).
    function activate(id) {
        const e = find(id);
        if (!e) return;
        if (e.hasDefault && invokeAction(id, 'default')) return;
        hideToast(id);
        if (!focusApp(e) && !e.live) openApp(e);
    }
    function focusApp(e) {
        const ids = [e.desktopEntry, e.appName].filter(s => s).map(s => s.toLowerCase());
        const window = ToplevelManager.toplevels.values.find(t => ids.indexOf((t.appId || '').toLowerCase()) >= 0);
        if (!window) return false;
        window.activate();
        return true;
    }
    function openApp(e) {
        const entry = e.desktopEntry ? DesktopEntries.byId(e.desktopEntry) : null;
        if (entry) entry.execute();
    }
    function remove(id) { drop(id); save(); }

    // Pictures: the notification's image while it lives (pixmaps die with it; files are kept),
    // else the app's icon (its own, its desktop entry's, a lookup by name).
    function iconUrl(icon) {
        if (!icon) return '';
        if (icon.startsWith('/')) return 'file://' + icon;
        if (/^[a-z]+:/.test(icon)) return icon;
        return Quickshell.iconPath(icon, true);
    }
    function imageFor(e) { return e && e.image && (e.live || e.image.startsWith('file:')) ? iconUrl(e.image) : ''; }
    function desktopFor(e) {
        if (!e) return null;
        return (e.desktopEntry ? DesktopEntries.byId(e.desktopEntry) : null) || (e.appName ? DesktopEntries.heuristicLookup(e.appName) : null);
    }
    function appIconFor(e) {
        if (!e) return '';
        const own = iconUrl(e.appIcon);
        if (own) return own;
        const d = desktopFor(e);
        return d ? iconUrl(d.icon) : '';
    }
    function appNameFor(e) {
        if (!e) return '';
        if (e.appName) return e.appName;
        const d = desktopFor(e);
        return d ? d.name : 'Notification';
    }
    function clearGroup(key) {
        entries.filter(e => e.keep && Rules.appKey(e) === key).map(e => e.id).forEach(id => drop(id));
        save();
    }
    function clearAll() {
        centreEntries.map(e => e.id).forEach(id => drop(id));
        save();
    }
    function markSeen() { unseen = 0; }
    // Super + Delete: hide the newest toast (it stays in the centre). Shift: every toast.
    function dismissNewest() {
        if (toastList.count > 0) dismissToast(toastList.get(0).nid);
    }
    function dismissToasts() {
        while (toastList.count > 0) dismissToast(toastList.get(0).nid);
    }
    // Super + Alt + comma: the newest toast's (else the newest live entry's) default action.
    function invokeNewest() {
        const e = toastList.count > 0 ? find(toastList.get(0).nid) : centreEntries.find(x => x.live) || null;
        if (e) activate(e.id);
    }
    function historyLines() {
        return centreEntries.map(e => JSON.stringify({ app_name: e.appName, desktop_entry: e.desktopEntry, summary: e.summary,
                                                       body: e.body, urgency: e.urgency, time: e.time, live: e.live })).join('\n');
    }

    // ---- do not disturb -----------------------------------------------------------------------
    // 'on', 'off', 'toggle', '1h', 'tomorrow' (anything else just reports). Returns on / off.
    function setDnd(command) {
        tick();
        const next = Rules.dndCommand(dnd, config, command, new Date(now * 1000));
        if (next) {
            dnd = next;
            ensureDir.run(() => dndFile.setText(JSON.stringify(next) + '\n'));
            tick();
        }
        return dndActive ? 'on' : 'off';
    }

    // ---- files ----------------------------------------------------------------------------------
    function save() { if (historyLoaded && !saveTimer.running) saveTimer.start(); }
    function noteApp(e) {
        const next = Rules.noteApp(apps, e);
        if (!next) return;
        apps = next;
        ensureDir.run(() => appsFile.setText(Rules.serializeApps(next)));
    }
    Timer {
        id: saveTimer
        interval: 1000
        onTriggered: ensureDir.run(() => historyFile.setText(Rules.serializeHistory(service.centreEntries)))
    }
    // A write still waiting when the shell quits lands first (the file writes block).
    Component.onDestruction: if (saveTimer.running && ensureDir.done) historyFile.setText(Rules.serializeHistory(centreEntries))
    // ~/.local/state/arctic/notifications, private (install -d -m 0700), made once before the
    // first write.
    Process {
        id: ensureDir
        property bool done: false
        property var pending: []
        function run(write) {
            if (done) { write(); return; }
            pending.push(write);
            if (!running) running = true;
        }
        command: ['install', '-d', '-m', '0700', service.stateDir]
        onExited: code => {
            done = code === 0;
            const writes = pending;
            pending = [];
            if (done) writes.forEach(w => w());
        }
    }
    FileView {
        id: historyFile
        path: service.stateDir + '/history.json'
        printErrors: false
        atomicWrites: true
        blockWrites: true
        onLoaded: service.restore(text())
        onLoadFailed: service.restore('')
    }
    function restore(text) {
        if (historyLoaded) return;
        const known = {};
        entries.forEach(e => known[e.time + '\u0000' + e.summary] = true);
        const old = Rules.parseHistory(text).filter(e => !known[e.time + '\u0000' + e.summary]);
        old.forEach(e => e.id = ++lastId);
        entries = entries.concat(old);
        historyLoaded = true;
        overflow();
    }
    FileView {
        id: dndFile
        path: service.stateDir + '/dnd.json'
        printErrors: false
        atomicWrites: true
        onLoaded: { service.dnd = Rules.parseDnd(text()); service.tick(); }
    }
    FileView {
        id: appsFile
        path: service.stateDir + '/apps.json'
        printErrors: false
        atomicWrites: true
        onLoaded: service.apps = Rules.parseApps(text())
    }
    // Settings also calls `arctic-shell-ipc notifications reload` after writing it (a file that
    // didn't exist yet has no watch).
    function reloadConfig() { configFile.reload(); }
    FileView {
        id: configFile
        path: Session.arcticConfig + '/notifications.json'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: { service.config = Rules.parseConfig(text()); service.tick(); }
        onLoadFailed: service.config = Rules.parseConfig('')
    }
    // Timed do not disturb and the schedule change on the minute.
    Timer { interval: 30000; running: true; repeat: true; onTriggered: service.tick() }
    Timer { interval: 200; running: toastList.count > 0; repeat: true; onTriggered: service.countDown() }
    onLockedChanged: if (!locked) lockedCount = 0

    ListModel { id: toastList }

    NotificationServer {
        id: server
        keepOnReload: true
        actionsSupported: true
        actionIconsSupported: false
        bodySupported: true
        bodyMarkupSupported: false
        bodyHyperlinksSupported: false
        bodyImagesSupported: false
        imageSupported: true
        persistenceSupported: true
        inlineReplySupported: false
        extraHints: ['x-canonical-private-synchronous']
        onNotification: n => service.receive(n, false)
    }
    // After a QML reload the server keeps its notifications (keepOnReload): adopt them quietly.
    Component.onCompleted: server.trackedNotifications.values.forEach(n => { if (!service.live[n.id]) service.receive(n, true); })

    // ---- who owns org.freedesktop.Notifications --------------------------------------------------
    property bool stoppedMako: false
    function refreshOwner() { if (!ownerQuery.running) ownerQuery.running = true; }
    function ownerIs(pid) {
        if (pid === Quickshell.processId) {
            owned = true;
            foreign = '';
            checked = true;
            return;
        }
        ownerName.command = ['cat', '/proc/' + pid + '/comm'];
        ownerName.running = true;
    }
    function nobodyOwns() {
        owned = false;
        foreign = 'mako';
        checked = true;
        Quickshell.execDetached(['arctic-session', 'mako', '--fallback']);
        DndService.refreshSoon();
    }
    Timer { interval: 1000; running: true; onTriggered: service.refreshOwner() }
    Timer { id: recheck; interval: 1000; onTriggered: service.refreshOwner() }
    Process {
        id: ownerQuery
        command: ['gdbus', 'call', '--session', '--dest', 'org.freedesktop.DBus', '--object-path', '/org/freedesktop/DBus',
                  '--method', 'org.freedesktop.DBus.GetConnectionUnixProcessID', 'org.freedesktop.Notifications']
        stdout: StdioCollector {
            onStreamFinished: {
                const m = /uint32\s+(\d+)/.exec(text);
                if (m) service.ownerIs(Number(m[1]));
            }
        }
        // NameHasNoOwner: the server couldn't take the name and nobody else has it.
        onExited: code => { if (code !== 0) service.nobodyOwns(); }
    }
    Process {
        id: ownerName
        stdout: StdioCollector {
            onStreamFinished: {
                const comm = text.trim();
                if (comm === 'mako' && !service.stoppedMako) {
                    service.stoppedMako = true;
                    Quickshell.execDetached(Session.user ? ['pkill', '-u', Session.user, '-x', 'mako'] : ['pkill', '-x', 'mako']);
                    recheck.restart();
                    return;
                }
                service.owned = false;
                service.foreign = comm || 'another program';
                service.checked = true;
                DndService.refreshSoon();
            }
        }
    }
}
