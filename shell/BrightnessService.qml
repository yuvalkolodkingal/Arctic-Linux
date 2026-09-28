pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Display brightness for Quick Settings and its display page (scripts/brightness.py): the
// laptop panel and DDC/CI monitors, read when Quick Settings opens. `focused` is the display
// on the focused output, else the first. Changes are coalesced (DDC/CI is slow).
Singleton {
    id: bright
    property var displays: []
    readonly property var focused: displays.find(d => d.output === Outputs.focusedName) || (displays.length ? displays[0] : null)
    property var pending: ({})          // output → percent waiting to be written

    function refresh() { if (!list.running) list.running = true; }
    function set(display, percent) {
        if (!display) return;
        const p = Math.max(1, Math.min(100, Math.round(percent)));
        displays = displays.map(d => d.output === display.output ? Object.assign({}, d, { percent: p }) : d);
        const next = Object.assign({}, pending);
        next[display.output] = p;
        pending = next;
        flush.restart();
    }

    Process {
        id: list
        command: ['python3', Session.scripts + '/brightness.py', 'list']
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                try {
                    const data = JSON.parse(text);
                    if (data.ok) bright.displays = data.displays || [];
                } catch (e) {}
            }
        }
    }
    Timer {
        id: flush
        interval: 150
        onTriggered: {
            const outputs = Object.keys(bright.pending);
            if (!outputs.length || writer.running) { if (outputs.length) restart(); return; }
            const output = outputs[0];
            writer.command = ['python3', Session.scripts + '/brightness.py', 'set', output, String(bright.pending[output])];
            const rest = Object.assign({}, bright.pending);
            delete rest[output];
            bright.pending = rest;
            writer.running = true;
        }
    }
    Process {
        id: writer
        onExited: if (Object.keys(bright.pending).length) flush.restart()
    }
}
