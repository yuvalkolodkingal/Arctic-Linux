import QtQuick
import Quickshell.Io

// A registry toggle backed by a command-line helper with the Arctic status contract:
// `<helper> on|off` changes it and `<helper> status --json` prints one line
// {"ok": true, "active": true|false, "detail": "…"} ("on"/"enabled"/"state" are read too).
// Hidden when the helper isn't installed. Read when Quick Settings opens and whenever
// `arctic-shell-ipc toggle refresh <key>` is called (helpers call it after a change).
Toggle {
    id: t
    property string helper: ''
    available: helper !== '' && Tools.has(helper)
    setter: on => {
        t.busy = true;
        run.command = [t.helper, on ? 'on' : 'off'];
        run.running = true;
    }

    function refresh() { if (available && !status.running) status.running = true; }
    function parse(text) {
        let d = null;
        try { d = JSON.parse(String(text).trim().split('\n').pop()); } catch (e) { return; }
        if (!d || d.ok === false) return;
        const on = d.active !== undefined ? d.active : d.on !== undefined ? d.on : d.enabled !== undefined ? d.enabled : d.state === 'on';
        t.active = on === true;
        t.detail = typeof d.detail === 'string' && d.detail ? d.detail : t.active ? 'On' : 'Off';
    }
    onAvailableChanged: refresh()

    property Process status: Process {
        command: [t.helper, 'status', '--json']
        stdout: StdioCollector { onStreamFinished: t.parse(text) }
    }
    property Process run: Process {
        onExited: { t.busy = false; t.refresh(); }
    }
}
