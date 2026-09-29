pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io
import Quickshell.Bluetooth

// Bluetooth for the bar item, its menu and the pairing dialog: the default adapter from
// Quickshell.Bluetooth, and scripts/bt-agent.py, the pairing agent (Quickshell has no BlueZ
// Agent1), run while an adapter exists. The agent's questions arrive as `request`; the dialog
// answers with reply(). Restarted after an exit with a 5 s back-off, at most 3 times a minute.
Singleton {
    id: bt
    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property bool available: adapter !== null
    readonly property bool enabled: adapter !== null && adapter.enabled
    readonly property var connected: adapter ? adapter.devices.values.filter(d => d.connected) : []
    property var request: null          // the pairing question waiting for an answer, or null
    property bool agentReady: false
    property var restarts: []

    // BlueZ's device icon names → design glyphs.
    function iconFor(name) {
        const n = String(name || '');
        if (n === 'audio-headset') return 'headset';
        if (n === 'audio-headphones') return 'headphones';
        if (n === 'audio-card' || n === 'multimedia-player') return 'speaker';
        if (n === 'input-keyboard') return 'keyboard';
        if (n === 'input-mouse') return 'mouse';
        if (n === 'input-gaming') return 'gamepad';
        if (n === 'input-tablet') return 'pen-nib';
        if (n === 'phone') return 'phone';
        if (n === 'computer') return 'laptop';
        if (n === 'video-display') return 'display';
        if (n.indexOf('camera') === 0) return 'camera';
        return 'bluetooth';
    }
    function batteryText(d) { return d && d.batteryAvailable ? Math.round(d.battery * 100) + ' %' : ''; }
    function stateText(d) {
        if (!d) return '';
        if (d.state === BluetoothDeviceState.Connecting) return 'Connecting…';
        if (d.state === BluetoothDeviceState.Disconnecting) return 'Disconnecting…';
        if (d.connected) return 'Connected' + (d.batteryAvailable ? ' · battery ' + batteryText(d) : '');
        return d.paired ? 'Not connected' : '';
    }
    function setEnabled(on) { if (adapter) adapter.enabled = on; }

    // The dialog's answer to `request` (value: the typed passkey or PIN).
    function reply(accept, value) {
        if (!request) return;
        agent.write(JSON.stringify({ op: 'reply', id: request.id, accept: accept, value: value === undefined ? '' : String(value) }) + '\n');
        request = null;
    }
    function dismiss() { request = null; }
    // Blueman's applet makes itself the default agent; pairing from Arctic's menu asks back.
    function claimDefault() { if (agent.running) agent.write('{"op":"default"}\n'); }
    // The user chose this device in the menu: for a minute its codes come marked "solicited",
    // and only then does the dialog focus Pair.
    function expect(address) { if (agent.running && address) agent.write(JSON.stringify({ op: 'expect', address: String(address) }) + '\n'); }

    function handle(line) {
        let data;
        try { data = JSON.parse(line); } catch (e) { return; }
        if (data.type === 'request') {
            // "Type this code" updates arrive again for every digit: keep the dialog, update it.
            if (data.kind === 'show_passkey' && bt.request && bt.request.kind === 'show_passkey' && bt.request.device === data.device)
                data.id = bt.request.id;
            // The agent asks one question at a time, but a code to type can still come meanwhile:
            // the question it replaces is answered no rather than left waiting.
            else if (bt.request && bt.request.kind !== 'show_passkey' && bt.request.kind !== 'show_pin')
                bt.reply(false);
            bt.request = data;
        } else if (data.type === 'cancel') {
            if (bt.request && (data.id === 0 || data.id === bt.request.id)) bt.request = null;
        } else if (data.type === 'ready') {
            bt.agentReady = true;
        } else if (data.type === 'released' || data.type === 'error') {
            bt.agentReady = false;
        }
    }

    Process {
        id: agent
        command: ['python3', Session.scripts + '/bt-agent.py']
        running: bt.available
        stdinEnabled: true
        stdout: SplitParser { onRead: line => bt.handle(line) }
        onExited: code => {
            bt.agentReady = false;
            bt.request = null;
            if (code === 2 || !bt.available) return;         // python3-dbus missing, or no adapter
            const now = Date.now();
            bt.restarts = bt.restarts.filter(t => now - t < 60000).concat([now]);
            if (bt.restarts.length <= 3) again.restart();
        }
    }
    Timer { id: again; interval: 5000; onTriggered: if (bt.available && !agent.running) agent.running = true }
}
