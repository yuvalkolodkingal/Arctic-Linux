pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// One shared event bridge for all taskbars, enabled only for Dodge windows. Layer-shell
// panels/popovers never enter Mango's client list. Losing IPC safely reveals every bar.
Singleton {
    id: geometry
    property var monitors: []
    property var windows: []
    property bool ready: false
    property string error: ''
    readonly property bool enabled: Session.barDodgeWindows && !Session.barHidden
    onEnabledChanged: { retry.stop(); ready = false; }
    Process {
        id: watch
        command: ['python3', Session.scripts + '/window_geometry.py']
        running: geometry.enabled && !retry.running
        stdout: SplitParser {
            onRead: data => {
                try {
                    const state = JSON.parse(data);
                    geometry.monitors = state.monitors || [];
                    geometry.windows = state.windows || [];
                    geometry.error = state.error || '';
                    geometry.ready = state.ready === true;
                } catch (e) { geometry.ready = false; }
            }
        }
        onExited: code => {
            geometry.ready = false;
            if (geometry.enabled && code !== 2) retry.restart();
        }
    }
    // Reconnect only after an actual disconnect, not periodic geometry polling.
    Timer { id: retry; interval: 5000 }
}
