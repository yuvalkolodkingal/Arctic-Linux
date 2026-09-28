pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Keyboard layouts, for the bar's layout chip (KeyboardItem.qml), its menu and the lock screen.
// scripts/keyboard.py reads the layouts from Mango's config (the installer's keyboard.conf,
// Settings' settings.conf, user.conf) and follows the active one (`mmsg watch keyboardlayout`);
// it starts again when one of those files changes. With one layout there is nothing to show.
Singleton {
    id: keyboard
    property var layouts: []            // [{code, variant, name, short}]
    property int index: 0
    property string switchLabel: ''     // the layout-switch key in words ("Alt + Shift"), or ''
    readonly property bool multiple: layouts.length > 1
    readonly property var current: layouts[index] || null
    readonly property string name: current ? current.name : ''
    readonly property string shortName: current ? current.short : ''

    function next() { Quickshell.execDetached(['python3', Session.scripts + '/keyboard.py', 'next']); }
    function set(i) {
        if (i >= 0 && i < layouts.length) Quickshell.execDetached(['python3', Session.scripts + '/keyboard.py', 'set', String(i)]);
    }
    function restart() {
        watch.running = false;
        restartTimer.restart();
    }

    Process {
        id: watch
        command: ['python3', Session.scripts + '/keyboard.py', 'watch']
        running: true
        stdout: SplitParser {
            onRead: data => {
                let msg = null;
                try { msg = JSON.parse(data); } catch (e) { return; }
                if (msg.type === 'layouts') {
                    keyboard.layouts = msg.layouts || [];
                    keyboard.switchLabel = msg.switch_label || '';
                    if (keyboard.index >= keyboard.layouts.length) keyboard.index = 0;
                } else if (msg.type === 'active' && msg.index >= 0) {
                    keyboard.index = msg.index;
                }
            }
        }
        // Exit 2: no Mango to follow. Anything else: one reconnect after the compositor restarts.
        onExited: code => { if (code !== 2) retry.restart(); }
    }
    Timer { id: retry; interval: 5000; onTriggered: if (!watch.running) watch.running = true }
    Timer { id: restartTimer; interval: 300; onTriggered: watch.running = true }

    // Mango's config files that can hold the layouts; a change re-reads them. (keyboard.py also
    // re-reads the config on every layout change, for files that didn't exist yet.)
    FileView { path: Session.home + '/.config/mango/settings.conf'; watchChanges: true; printErrors: false; onFileChanged: keyboard.restart() }
    FileView { path: Session.home + '/.config/mango/user.conf'; watchChanges: true; printErrors: false; onFileChanged: keyboard.restart() }
    FileView { path: '/etc/arctic/mango/keyboard.conf'; watchChanges: true; printErrors: false; onFileChanged: keyboard.restart() }
}
