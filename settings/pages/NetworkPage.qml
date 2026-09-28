// Network: what NetworkManager is connected to, Wi-Fi on/off (nmcli), and the full editor
// (nm-connection-editor) for everything else: proxies, static addresses, company logins.
// Joining a Wi-Fi network happens in the shell's network menu on the bar (network.py).
pragma ComponentBehavior: Bound
import QtQuick
import ".."
import "../components"

Page {
    id: page
    title: "Network"
    lede: "Your connections. Join a Wi-Fi network from the network menu on the bar (Super + Ctrl + W)."
    property var net: ({ available: true, devices: [], wifi: true, hasWifi: false })
    function load() {
        Backend.call(["network"], r => { if (r.ok) page.net = r; }, true);
    }
    onShown: load()
    Timer {
        interval: 4000
        repeat: true
        running: page.visible
        onTriggered: page.load()
    }
    function stateText(s) {
        return ({ connected: "Connected", connecting: "Connecting…", disconnected: "Not connected",
                  unavailable: "Unavailable", unmanaged: "Not managed" })[s] || s;
    }

    ArBanner {
        visible: page.net.available === false
        width: parent.width
        kind: "warning"
        title: "No network information"
        text: page.net.reason || ""
    }

    Group {
        visible: page.net.available !== false
        title: "Connections"
        SettingRow {
            searchKey: "network.wifi"
            visible: page.net.hasWifi === true
            title: "Wi-Fi"
            desc: page.net.wifi ? "On" : "Off. Wired connections keep working."
            resettable: false
            RowSwitch {
                Accessible.name: "Wi-Fi"
                checked: page.net.wifi === true
                onToggled: Backend.call(["wifi", checked ? "on" : "off"], r => {
                    if (r.ok) page.net = r;
                    else checked = page.net.wifi === true;
                })
            }
        }
        Repeater {
            model: page.net.devices || []
            SettingRow {
                id: dev
                required property var modelData
                searchKey: index === 0 ? "network.connections" : ""
                required property int index
                title: (dev.modelData.type === "wifi" ? "Wi-Fi" : dev.modelData.type === "ethernet" ? "Wired" : dev.modelData.type.toUpperCase())
                       + (dev.modelData.connection ? " · " + dev.modelData.connection : "")
                desc: page.stateText(dev.modelData.state) + (dev.modelData.signal !== undefined ? " · signal " + dev.modelData.signal + "%" : "") + " · " + dev.modelData.device
                resettable: false
                Row {
                    spacing: Theme.space2
                    Icon {
                        name: dev.modelData.type === "wifi" ? (dev.modelData.state === "connected" ? "wifi" : "wifi-off") : "ethernet"
                        size: 20
                        color: dev.modelData.state === "connected" ? Theme.success : Theme.inkMuted
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArText {
                        text: dev.modelData.state === "connected" ? "Connected" : ""
                        size: 13
                        lh: 18
                        color: Theme.success
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
            }
        }
    }

    Group {
        title: "More"
        SettingRow {
            title: "Edit connections"
            desc: "Wi-Fi passwords, VPNs, proxies and fixed addresses."
            resettable: false
            enabled: Backend.caps.nmEditor === true
            ArButton {
                text: "Open the editor"
                iconRight: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["nm-connection-editor"])
            }
        }
        SettingRow {
            visible: Backend.caps.nmtui === true
            title: "Join a network from the terminal"
            desc: "nmtui lists the Wi-Fi networks around you."
            resettable: false
            ArButton {
                text: "Open nmtui"
                variant: "ghost"
                iconRight: "external"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["arctic-open", "terminal", "-e", "nmtui"])
            }
        }
    }
}
