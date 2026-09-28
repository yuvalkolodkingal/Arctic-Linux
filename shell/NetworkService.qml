pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Network state and actions for the bar's network item and menu, from scripts/network.py:
// `watch` re-reads NetworkManager only when `nmcli monitor` reports a change, and scans for
// Wi-Fi networks only while a menu asks (setScanning). Hidden when nmcli isn't available.
// Wi-Fi goes through network.py (nmcli); Quickshell.Networking is not used on Fedora 44's
// snapshot (no PSK support, a crash when a network disappears, no wired devices).
Singleton {
    id: net
    property bool available: false
    property bool nmRunning: true
    property var wifi: null             // {device, state, hardware, enabled} or null without Wi-Fi
    property var wired: []              // [{device, state, connection}]
    property var active: []             // [{uuid, name, type, device, state}]
    property var vpn: []                // [{uuid, name, kind, active, last_used}]
    property var saved: []              // [{uuid, ssid, autoconnect}]
    property bool airplane: false       // every radio soft-blocked (rfkill)
    property var hotspot: ({ active: false, uuid: null, ssid: null })   // Arctic's hotspot profile
    readonly property bool hotspotCapable: wifi !== null && wifi.ap_capable === true
    property var networks: []           // the last scan, while scanning
    // NetworkManager gave up on a saved network (its password changed) and the person chose
    // "Enter password" in the notification: shell.qml opens the menu with that network's field.
    signal passwordWanted(string ssid)
    property bool scanning: false
    property int scanRequests: 0

    readonly property var wifiActive: active.find(a => a.type === 'wifi') || null
    readonly property var wiredLink: wired.find(w => w.state === 'connected' || w.state === 'connecting') || null
    readonly property bool wifiEnabled: wifi ? wifi.enabled : true
    readonly property bool vpnActive: vpn.some(v => v.active)
    // What the bar shows: a wired link wins over Wi-Fi (the same rule as before).
    readonly property string kind: wiredLink ? 'ethernet' : wifiActive ? 'wifi' : 'none'
    readonly property string state: kind === 'ethernet' ? wiredLink.state
                                    : kind === 'wifi' ? (wifiActive.state === 'activated' ? 'connected' : 'connecting') : 'disconnected'
    readonly property string name: kind === 'wifi' ? wifiActive.name : kind === 'ethernet' ? (wiredLink.connection || 'Wired') : ''
    readonly property string iconName: kind === 'ethernet' ? 'ethernet' : kind === 'wifi' && state === 'connected' ? 'wifi' : 'wifi-off'
    readonly property string summary: kind === 'wifi' ? (state === 'connected' ? name + ' · Connected' : 'Connecting to ' + name + '…')
                                      : kind === 'ethernet' ? (state === 'connected' ? 'Wired · Connected' : 'Wired · Connecting…')
                                      : !wifiEnabled ? 'Wi-Fi is off · Not connected' : 'Not connected'

    function send(op) { if (watcher.running) watcher.write(JSON.stringify(op) + '\n'); }
    // Menus call setScanning(true) while they are open, and false when they close.
    function setScanning(on) {
        scanRequests = Math.max(0, scanRequests + (on ? 1 : -1));
        const want = scanRequests > 0;
        if (want !== scanning) { scanning = want; send({ op: 'scan', on: want }); }
        if (!want) networks = [];
    }
    function rescan() { send({ op: 'rescan' }); }
    function savedFor(ssid) { return saved.find(s => s.ssid === ssid) || null; }

    // One action (network.py <args>); `secret`, when given, goes to the helper's stdin as one
    // JSON line and is not kept. callback(result) gets {ok, error, code}.
    function run(args, secret, callback) {
        const proc = action.createObject(net, { command: ['python3', Session.scripts + '/network.py'].concat(args),
                                                callback: callback || null, secretLine: secret !== undefined && secret !== null && secret !== ''
                                                ? JSON.stringify({ secret: secret }) + '\n' : '' });
        proc.running = true;
    }

    function apply(line) {
        let data;
        try { data = JSON.parse(line); } catch (e) { return; }
        if (data.type === 'state') {
            net.nmRunning = data.nm_running !== false;
            net.available = net.nmRunning;
            net.wifi = data.wifi || null;
            net.wired = data.wired || [];
            net.active = data.active || [];
            net.vpn = data.vpn || [];
            if (data.saved) net.saved = data.saved;
            net.airplane = data.airplane === true;
            net.hotspot = data.hotspot || { active: false, uuid: null, ssid: null };
        } else if (data.type === 'needs_secrets') {
            // Not while the menu is open: it shows the password field itself.
            if (net.scanning || secretsNotice.running || !data.ssid) return;
            secretsNotice.ssid = data.ssid;
            secretsNotice.command = ['notify-send', '-a', 'Network', '-i', 'network-wireless', '-A', 'open=Enter password',
                                     '“' + data.ssid + '” needs its Wi-Fi password again',
                                     'The saved password didn’t work. Enter the new one to connect.'];
            secretsNotice.running = true;
        } else if (data.type === 'networks') {
            if (net.scanning) net.networks = data.networks || [];
        } else if (data.type === 'error') {
            net.available = false;
        }
    }

    Process {
        id: watcher
        command: ['python3', Session.scripts + '/network.py', 'watch']
        running: true
        stdinEnabled: true
        stdout: SplitParser { onRead: line => net.apply(line) }
        onStarted: if (net.scanning) net.send({ op: 'scan', on: true })
        // Exit 2: nmcli isn't installed; anything else: NetworkManager restarted, try again.
        onExited: code => { if (code === 2) net.available = false; else restart.restart(); }
    }
    Timer { id: restart; interval: 3000; onTriggered: if (!watcher.running) watcher.running = true }
    Process {
        id: secretsNotice
        property string ssid: ''
        stdout: StdioCollector { onStreamFinished: if (text.trim() === 'open') net.passwordWanted(secretsNotice.ssid) }
    }

    Component {
        id: action
        Process {
            id: proc
            property var callback: null
            property string secretLine: ''
            property bool done: false
            stdinEnabled: true
            onStarted: {
                if (secretLine !== '') write(secretLine);
                secretLine = '';
            }
            stdout: StdioCollector {
                onStreamFinished: {
                    if (proc.done) return;
                    proc.done = true;
                    let result = null;
                    try { result = JSON.parse(text.trim().split('\n').pop()); } catch (e) {}
                    if (!result) result = { ok: false, error: 'The network helper didn’t answer.', code: 'failed' };
                    if (proc.callback) proc.callback(result);
                    proc.destroy(1000);
                }
            }
        }
    }
}
