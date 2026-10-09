pragma Singleton
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io
import "DictationStatus.js" as Status

Singleton {
    id: dictation
    property var status: Status.parse('')
    readonly property bool active: Status.active(status)
    readonly property bool recording: status.state === 'recording'
    readonly property string headline: Status.headline(status)
    readonly property string detail: Status.detail(status)
    property int statusRevision: 0
    property int probeRevision: 0

    function refresh() { snapshot.reload(); }
    function toggle() { Quickshell.execDetached(['arctic-dictation', 'toggle']); }
    function cancel() { Quickshell.execDetached(['arctic-dictation', 'cancel']); }
    function openSettings() { Quickshell.execDetached(['arctic-settings', 'dictation']); }
    function probeStatus() {
        if (probe.running) return;
        probeRevision = statusRevision;
        probe.running = true;
    }

    FileView {
        id: snapshot
        path: Session.runtimeDir + '/arctic/dictation.json'
        watchChanges: true
        printErrors: false
        onFileChanged: reload()
        onLoaded: { dictation.statusRevision++; dictation.status = Status.parse(text()); }
        onLoadFailed: dictation.probeStatus()
    }
    Process {
        id: probe
        command: ['arctic-dictation', 'status']
        stdout: StdioCollector {
            // A file transition that arrived meanwhile is newer than this probe's answer.
            onStreamFinished: if (dictation.probeRevision === dictation.statusRevision) dictation.status = Status.parse(text)
        }
    }
    // Root setup changes readiness before a user recording creates the runtime snapshot.
    // Active polling also reconciles a stale recording file after a broker crash.
    Timer {
        interval: dictation.active || dictation.status.state === 'downloading' || dictation.status.state === 'queued' ? 5000 : 60000
        running: true
        repeat: true
        onTriggered: dictation.probeStatus()
    }
}
