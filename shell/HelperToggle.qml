import QtQuick
import Quickshell.Io

// A registry toggle backed by a command-line helper with the Arctic status contract:
// `<helper> on|off` changes it and `<helper> status --json` prints one line
// {"ok": true, "active": true|false, "detail": "…"} ("on"/"enabled"/"state" are read too;
// "untilText" becomes "Until 07:00"). Hidden when the helper isn't installed or says
// "available": false (night light without wlsunset). Read at start, when Quick Settings opens,
// whenever `arctic-shell-ipc toggle refresh <key>` is called (arctic-nightlight and
// arctic-keep-awake call it after a change) and once a minute (a schedule turns night light on
// without anyone running the helper).
Toggle {
    id: t
    property string helper: ''
    property bool reportsAvailable: true
    readonly property bool installed: helper !== '' && Tools.has(helper)
    available: installed && reportsAvailable
    setter: on => {
        t.busy = true;
        run.command = [t.helper, on ? 'on' : 'off'];
        run.running = true;
    }

    function refresh() { if (installed && !status.running) status.running = true; }
    function parse(text) {
        let d = null;
        try { d = JSON.parse(String(text).trim().split('\n').pop()); } catch (e) { return; }
        if (!d || d.ok === false) return;
        const on = d.active !== undefined ? d.active : d.on !== undefined ? d.on : d.enabled !== undefined ? d.enabled : d.state === 'on';
        t.reportsAvailable = d.available !== false;
        t.active = on === true;
        t.detail = typeof d.detail === 'string' && d.detail ? d.detail
                 : t.active && typeof d.untilText === 'string' && d.untilText ? 'Until ' + d.untilText : t.active ? 'On' : 'Off';
    }
    onInstalledChanged: refresh()
    property Timer poll: Timer { interval: 60000; repeat: true; running: t.installed; onTriggered: t.refresh() }

    property Process status: Process {
        command: [t.helper, 'status', '--json']
        stdout: StdioCollector { onStreamFinished: t.parse(text) }
    }
    property Process run: Process {
        onExited: { t.busy = false; t.refresh(); }
    }
}
