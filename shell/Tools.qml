pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Which optional commands are installed, checked once at start (and on `refresh()`), so menus
// hide a row whose tool is missing instead of offering something that can't run: the stock
// editors behind "More settings…" and the helpers Quick Settings toggles call.
Singleton {
    id: tools
    readonly property var names: ['nm-connection-editor', 'blueman-manager', 'pavucontrol', 'pwvucontrol',
        'arctic-settings', 'arctic-dnd', 'arctic-nightlight', 'arctic-keep-awake', 'arctic-theme',
        'brightnessctl', 'notify-send', 'playerctl', 'qrencode']
    property var found: ({})
    property bool ready: false
    function has(name) { return found[name] === true; }
    function refresh() { if (!check.running) check.running = true; }

    Process {
        id: check
        running: true
        command: ['sh', '-c', 'for c in "$@"; do command -v "$c" >/dev/null 2>&1 && echo "$c"; done', 'tools'].concat(tools.names)
        stdout: StdioCollector {
            onStreamFinished: {
                const out = {};
                text.split('\n').forEach(n => { if (n) out[n] = true; });
                tools.found = out;
                tools.ready = true;
            }
        }
    }
}
