pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Do not disturb, for the bell and IPC. When the shell owns notifications
// (NotificationService.owned) it is the shell's own (durations, schedule, Arctic's rule in
// NotificationRules.js); otherwise it is mako's "do-not-disturb" mode as in 0.2 (`arctic-dnd`,
// re-read when arctic-dnd calls `arctic-shell-ipc dnd refresh`).
Singleton {
    id: dnd
    readonly property bool owned: NotificationService.owned
    readonly property bool available: owned || makoAvailable
    readonly property bool active: owned ? NotificationService.dndActive : makoActive
    property bool makoAvailable: false
    property bool makoActive: false
    function refresh() { if (!owned && !query.running) query.running = true; }
    function refreshSoon() { refreshTimer.restart(); }
    // 'on', 'off', 'toggle', '1h', 'tomorrow'.
    function set(mode) {
        if (owned) { NotificationService.setDnd(mode); return; }
        Quickshell.execDetached(['arctic-dnd', mode === 'toggle' || mode === 'on' || mode === 'off' ? mode : 'on']);
        refreshSoon();
    }
    function toggle() { set('toggle'); }
    Process {
        id: query
        command: ['makoctl', 'mode']
        stdout: StdioCollector { onStreamFinished: dnd.makoActive = /^do-not-disturb$/m.test(text) }
        onExited: code => dnd.makoAvailable = code === 0
    }
    Timer { id: refreshTimer; interval: 200; onTriggered: dnd.refresh() }
}
