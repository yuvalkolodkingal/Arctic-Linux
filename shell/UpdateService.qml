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
    // staged_at of the update already announced (kept in ~/.cache/arctic, so a shell restart
    // doesn't announce it again).
    property string notified: ''
    property bool notifiedLoaded: false

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
}
