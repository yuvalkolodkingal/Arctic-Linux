pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Do not disturb = mako's "do-not-disturb" mode (arctic-dnd). Re-read when arctic-dnd changes
// it (it calls `arctic-shell-ipc dnd refresh`) and after the bell is clicked.
Singleton {
    id: dnd
    property bool available: false
    property bool active: false
    function refresh() { if (!query.running) query.running = true; }
    function toggle() {
        Quickshell.execDetached(['arctic-dnd', 'toggle']);
        refreshSoon.restart();
    }
    Process {
        id: query
        command: ['makoctl', 'mode']
        running: true
        stdout: StdioCollector { onStreamFinished: dnd.active = /^do-not-disturb$/m.test(text) }
        onExited: code => dnd.available = code === 0
    }
    Timer { id: refreshSoon; interval: 200; onTriggered: dnd.refresh() }
}
