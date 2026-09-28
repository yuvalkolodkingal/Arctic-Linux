pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Screen recording (arctic-record, Super + Alt + R) for a bar indicator: arctic-record writes
// $XDG_RUNTIME_DIR/arctic/record.json while it records, removes it when it stops, and calls
// `arctic-shell-ipc record refresh` both times. `elapsed` counts seconds only while recording.
Singleton {
    id: record
    property bool recording: false
    property int startedAt: 0          // Unix seconds
    property string file: ''
    property int elapsed: 0
    function refresh() { state.reload(); }
    function stop() { Quickshell.execDetached(['arctic-record', 'stop']); }
    function toggle() { Quickshell.execDetached(['arctic-record', 'toggle']); }

    function tick() { elapsed = recording ? Math.max(0, Math.floor(Date.now() / 1000) - startedAt) : 0; }
    FileView {
        id: state
        path: Session.runtimeDir + '/arctic/record.json'
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            let data = {};
            try { data = JSON.parse(text()); } catch (e) { data = {}; }
            record.recording = data.recording === true;
            record.startedAt = data.started || 0;
            record.file = data.file || '';
            record.tick();
        }
        onLoadFailed: {
            record.recording = false;
            record.file = '';
            record.tick();
        }
    }
    Timer { interval: 1000; repeat: true; running: record.recording; onTriggered: record.tick() }
}
