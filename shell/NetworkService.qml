pragma Singleton
import QtQuick
import Quickshell
import Quickshell.Io

// Network state from NetworkManager's own event stream (`nmcli monitor`): re-read the device
// list only when NetworkManager reports a change. Hidden when nmcli isn't available.
// (Quickshell.Networking only knows Wi-Fi devices in this release, so wired links need nmcli.)
Singleton {
    id: net
    property bool available: false
    property string kind: 'none'        // wifi, ethernet, none
    property string state: 'disconnected'
    property string name: ''
    property bool wifiEnabled: true
    readonly property string iconName: kind === 'ethernet' ? 'ethernet' : kind === 'wifi' && state === 'connected' ? 'wifi' : 'wifi-off'
    readonly property string summary: kind === 'wifi' ? (state === 'connected' ? name + ' · Connected' : 'Connecting to ' + name + '…')
                                      : kind === 'ethernet' ? (state === 'connected' ? 'Wired · Connected' : 'Wired · Connecting…')
                                      : !wifiEnabled ? 'Wi-Fi is off · Not connected' : 'Not connected'

    function refresh() { if (!query.running) query.running = true; else again.restart(); }

    Process {
        id: query
        command: ['sh', '-c', 'nmcli -t -f TYPE,STATE,CONNECTION device status && echo "radio:$(nmcli radio wifi)"']
        running: true
        stdout: StdioCollector {
            onStreamFinished: {
                let best = null;
                let rank = { connected: 3, connecting: 2 };
                net.wifiEnabled = !/^radio:disabled/m.test(text);
                text.split('\n').forEach(line => {
                    const parts = line.split(':');
                    const type = parts[0], state = (parts[1] || '').split(' ')[0];
                    if (type !== 'wifi' && type !== 'ethernet') return;
                    const score = (rank[state] || 0) * 2 + (type === 'ethernet' ? 1 : 0);
                    if ((rank[state] || 0) > 0 && (!best || score > best.score))
                        best = { score: score, type: type, state: state, name: parts.slice(2).join(':').replace(/\\:/g, ':') };
                });
                net.kind = best ? best.type : 'none';
                net.state = best ? best.state : 'disconnected';
                net.name = best ? best.name : '';
            }
        }
        onExited: code => { net.available = code === 0; if (code === 0 && !monitor.running) monitor.running = true; }
    }
    Process {
        id: monitor
        command: ['nmcli', 'monitor']
        stdout: SplitParser { onRead: _ => again.restart() }
        onExited: net.available = false
    }
    // Coalesce a burst of monitor lines into one re-read.
    Timer { id: again; interval: 250; onTriggered: net.refresh() }
}
