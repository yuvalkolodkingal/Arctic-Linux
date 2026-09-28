pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import "UpdateStatus.js" as UpdateStatus

// Updates waiting for the next restart (arctic-update, packaging/updates): the status file the
// daily check writes as root, plus the /system-update link that makes the next boot install
// them (a dnf transaction after the download removes it). Never on the live USB.
// ARCTIC_UPDATE_STATUS points it at another status file (screenshots and tests only).
Singleton {
    id: updates
    readonly property string statusPath: Quickshell.env('ARCTIC_UPDATE_STATUS') || '/var/lib/arctic/update-status.json'
    property var status: UpdateStatus.parse('')
    property bool linked: false
    readonly property bool ready: UpdateStatus.isReady(status, linked, Session.live)
    readonly property string summary: UpdateStatus.summary(status)
    readonly property string detail: UpdateStatus.detail(status)
    // The update already announced (its notify_key, kept in ~/.cache/arctic, so a shell restart
    // doesn't announce it again), and the failed install at a restart already reported.
    property string notified: ''
    property bool notifiedLoaded: false
    property string failureNotified: ''
    property bool failureNotifiedLoaded: false

    function refresh() {
        statusView.reload();
        if (!linkCheck.running) linkCheck.running = true;
    }
    // The update installs during the restart (dnf5-offline-transaction.service).
    function restart() { Quickshell.execDetached(['arctic-power', 'restart']); }

    function announce() {
        if (!notifiedLoaded || !UpdateStatus.shouldNotify(status, ready, notified)) return;
        notified = UpdateStatus.notifyKey(status);
        const file = Session.arcticCache + '/update-notified';
        Quickshell.execDetached(['sh', '-c', 'mkdir -p "${1%/*}" && printf "%s\\n" "$2" > "$1"', 'sh', file, notified]);
        Quickshell.execDetached(['notify-send', '-a', 'Arctic Linux', '-i', 'system-software-update',
                                 'Updates are ready', UpdateStatus.notification(status)]);
    }
    onReadyChanged: announce()
    onNotifiedLoadedChanged: announce()

    // Installing the updates at the last restart failed: say so once.
    function announceFailure() {
        if (!failureNotifiedLoaded || !UpdateStatus.shouldNotifyFailure(status, Session.live, failureNotified)) return;
        failureNotified = UpdateStatus.failureKey(status);
        const file = Session.arcticCache + '/update-failure-notified';
        Quickshell.execDetached(['sh', '-c', 'mkdir -p "${1%/*}" && printf "%s\\n" "$2" > "$1"', 'sh', file, failureNotified]);
        Quickshell.execDetached(['notify-send', '-a', 'Arctic Linux', '-u', 'critical', '-i', 'dialog-warning',
                                 'Updates weren\'t installed', UpdateStatus.failureNotification(status)]);
    }
    onStatusChanged: { announceFailure(); runPostUpdateHooks(); }

    // Updates were installed at a restart: your post-update hooks (arctic-hook), once for each
    // (the last one handled is kept in ~/.cache/arctic/post-update-hooked).
    property string hooked: ''
    property bool hookedLoaded: false
    function runPostUpdateHooks() {
        const at = status.installed_at;
        if (!hookedLoaded || !at || at === hooked || Session.live) return;
        hooked = at;
        const file = Session.arcticCache + '/post-update-hooked';
        Quickshell.execDetached(['sh', '-c', 'mkdir -p "${1%/*}" && printf "%s\\n" "$2" > "$1"', 'sh', file, at]);
        Quickshell.execDetached(['sh', '-c', '. /etc/os-release 2>/dev/null; exec arctic-hook post-update "${VERSION_ID:-}"']);
    }
    onHookedLoadedChanged: runPostUpdateHooks()
    FileView {
        path: Session.arcticCache + '/post-update-hooked'
        printErrors: false
        onLoaded: { updates.hooked = text().trim(); updates.hookedLoaded = true; }
        onLoadFailed: updates.hookedLoaded = true
    }
    onFailureNotifiedLoadedChanged: announceFailure()

    FileView {
        id: statusView
        path: updates.statusPath
        watchChanges: true
        printErrors: false
        onFileChanged: updates.refresh()
        onLoaded: {
            updates.status = UpdateStatus.parse(text());
            if (!linkCheck.running) linkCheck.running = true;
        }
        onLoadFailed: updates.status = UpdateStatus.parse('')
    }
    Process {
        id: linkCheck
        command: ['test', '-L', '/system-update']
        running: !Session.live
        onExited: code => updates.linked = code === 0
    }
    // The status file is replaced as a whole and the link can go without it changing: look
    // again every minute while an update waits, every ten minutes otherwise.
    Timer {
        interval: updates.status.state === 'ready' ? 60000 : 600000
        running: !Session.live
        repeat: true
        onTriggered: updates.refresh()
    }
    FileView {
        path: Session.arcticCache + '/update-notified'
        printErrors: false
        onLoaded: { updates.notified = text().trim(); updates.notifiedLoaded = true; }
        onLoadFailed: { updates.notified = ''; updates.notifiedLoaded = true; }
    }
    FileView {
        path: Session.arcticCache + '/update-failure-notified'
        printErrors: false
        onLoaded: { updates.failureNotified = text().trim(); updates.failureNotifiedLoaded = true; }
        onLoadFailed: { updates.failureNotified = ''; updates.failureNotifiedLoaded = true; }
    }
}
