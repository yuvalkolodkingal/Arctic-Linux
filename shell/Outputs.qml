pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Which screen has focus, so shortcuts open the launcher, OSD and menus where you are.
// Event-driven through scripts/workspaces.py (Mango `mmsg watch all-monitors`, sway and
// Hyprland events). Falls back to the first screen.
Singleton {
    id: outputs
    property string focusedName: ''
    readonly property var focused: {
        const screens = Quickshell.screens;
        for (let i = 0; i < screens.length; i++) if (screens[i].name === focusedName) return screens[i];
        return screens.length ? screens[0] : null;
    }
    Process {
        id: watch
        command: ['python3', Session.scripts + '/workspaces.py', 'focus']
        running: true
        stdout: SplitParser {
            onRead: data => {
                try { outputs.focusedName = JSON.parse(data).focused || ''; } catch (e) {}
            }
        }
        onExited: code => { if (code !== 2) retry.restart(); }
    }
    // One reconnect attempt after the compositor restarts (not a poll).
    Timer { id: retry; interval: 5000; onTriggered: if (!watch.running) watch.running = true }
}
