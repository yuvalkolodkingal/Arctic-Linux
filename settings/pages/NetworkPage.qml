// Network: what NetworkManager is connected to, Wi-Fi on/off (nmcli), and the full editor
// (nm-connection-editor) for everything else: proxies, static addresses, company logins.
// Joining a Wi-Fi network happens in the shell's network menu on the bar (network.py).
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Dialogs
import QtQuick.Templates as T
import ".."
import "../components"

Page {
    id: page
    title: "Network"
    lede: "Your connections. Join a Wi-Fi network from the network menu on the bar (Super + Ctrl + W)."
    property var net: ({ available: true, devices: [], wifi: true, hasWifi: false })
    property var saved: ({ available: false, saved: [], vpn: [] })
    property var optional: ({ tor: { installed: false, service: { running: false }, can_start: false, running_units: [], endpoints: [], browser: [], bootstrap: null }, tailscale: { present: false, running: false, state: "unknown", connection: "unknown" }, openvpn: false })
    function loadOptional() { Backend.call(["optional-network"], r => { if (r.ok) page.optional = r; }, true); }
    function askOptional(tool, verb, explanation) {
        optionalDialog.args = [tool, verb]; optionalDialog.body = explanation; optionalDialog.open();
    }
    function load() {
        Backend.call(["network"], r => { if (r.ok) page.net = r; }, true);
    }
    function loadSaved() {
        Backend.call(["network-saved"], r => { if (r.ok) page.saved = r; }, true);
    }
    function savedCall(args) {
        Backend.call(args, r => { if (r.ok) page.saved = r; else page.loadSaved(); });
    }
    onShown: { load(); loadSaved(); loadOptional(); }
    Timer {
        interval: 4000
        repeat: true
        running: page.visible
        onTriggered: page.load()
    }
    Timer { interval: 15000; repeat: true; running: page.visible; onTriggered: page.loadOptional() }
    ArDialog {
        id: optionalDialog
        parent: T.Overlay.overlay
        title: "Optional network change"
        property var args: []
        ArButton {
            text: "Continue in a terminal"
            onClicked: {
                Backend.call(["optional-network-run"].concat(optionalDialog.args), r => {
                    if (r.ok) { optionalDialog.close(); page.loadOptional(); }
                });
            }
        }
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
        visible: page.saved.available === true && page.saved.saved.length > 0
        title: "Saved Wi-Fi networks"
        Repeater {
            model: page.saved.saved || []
            SettingRow {
                id: savedRow
                required property var modelData
                required property int index
                searchKey: index === 0 ? "network.saved" : ""
                title: savedRow.modelData.ssid || savedRow.modelData.name
                desc: savedRow.modelData.enterprise === true
                      ? "Company login · " + (savedRow.modelData.ca_cert ? "checked with " + savedRow.modelData.ca_cert.split("/").pop()
                                                                          : "checked with the system’s certificates")
                      : savedRow.modelData.autoconnect === false ? "Joins only when you pick it" : "Joins by itself when it is near"
                resettable: false
                Row {
                    spacing: Theme.space2
                    ArButton {
                        // A company network whose IT department gave you its own certificate file.
                        visible: savedRow.modelData.enterprise === true
                        text: "Certificate…"
                        variant: "ghost"
                        size: "sm"
                        gapColor: Theme.surfaceRaised
                        onClicked: { caDialog.uuid = savedRow.modelData.uuid; caDialog.open(); }
                    }
                    ArButton {
                        text: "Forget"
                        variant: "ghost"
                        size: "sm"
                        gapColor: Theme.surfaceRaised
                        onClicked: page.savedCall(["network-forget", savedRow.modelData.uuid])
                    }
                }
            }
        }
    }

    Group {
        visible: page.saved.available === true
        title: "VPN"
        Repeater {
            model: page.saved.vpn || []
            SettingRow {
                id: vpnRow
                required property var modelData
                title: vpnRow.modelData.name
                desc: (vpnRow.modelData.active ? "Connected" : "Not connected") + " · " + (vpnRow.modelData.kind === "wireguard" ? "WireGuard" : "VPN")
                resettable: false
                ArButton {
                    text: vpnRow.modelData.active ? "Disconnect" : "Connect"
                    variant: "secondary"
                    size: "sm"
                    gapColor: Theme.surfaceRaised
                    onClicked: page.savedCall(["vpn", vpnRow.modelData.active ? "down" : "up", vpnRow.modelData.uuid])
                }
            }
        }
        SettingRow {
            searchKey: "network.vpn"
            title: "Import a VPN file"
            desc: "An OpenVPN (.ovpn) or WireGuard (.conf) file from your VPN provider. It then has a switch in the network menu."
            resettable: false
            ArButton {
                text: "Import…"
                iconName: "plus"
                gapColor: Theme.surfaceRaised
                onClicked: vpnDialog.open()
            }
        }
    }

    Group {
        title: "Optional privacy and private networks"
        desc: "Tor is for selected apps. Tailscale connects your own devices. A commercial VPN uses a provider's network. None is enabled automatically."
        visible: !Backend.live
        SettingRow {
            title: "Tor Browser"
            desc: page.optional.tor.browser.length ? "Installed. Its connection covers this browser, not other apps." : "Optional browser with Tor built in; download and connection setup happen when you open it."
            resettable: false
            ArButton {
                text: page.optional.tor.browser.length ? "Open Tor Browser" : "Get Tor Browser…"
                gapColor: Theme.surfaceRaised
                onClicked: {
                    if (page.optional.tor.browser.length)
                        Backend.launch(["flatpak", "run", "--" + page.optional.tor.browser[0], "org.torproject.torbrowser-launcher"]);
                    else Backend.launch(["arctic-shell-ipc", "apps", "search", "flatpak", "org.torproject.torbrowser-launcher"]);
                }
            }
        }
        SettingRow {
            searchKey: "network.tor"
            title: "Tor SOCKS client"
            desc: {
                const t = page.optional.tor;
                const state = !t.installed ? "Not installed." : t.service.running ? "Default service is running." : t.running_units.length ? "An existing Tor instance is running." : "Installed; default service is stopped.";
                const boot = t.bootstrap === null ? " Bootstrap status is unknown." : " Current service reported bootstrap " + t.bootstrap + "%.";
                const ports = t.endpoints.map(e => e.host + ":" + e.port).join(", ");
                return state + boot + (ports ? " SOCKS5 responds at " + ports + "; its Tor identity is not verified." : " No SOCKS5 response on the usual local ports.")
                    + " Configure each app separately, including proxy-side DNS. UDP and unconfigured apps can bypass Tor. This is not proof of anonymity.";
            }
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    visible: !page.optional.tor.installed
                    text: "Install Tor…"; gapColor: Theme.surfaceRaised
                    onClicked: page.askOptional("tor", "install", "Install Fedora's optional Tor client. This does not configure app routing or start a connection.")
                }
                ArButton {
                    visible: page.optional.tor.service.running || page.optional.tor.can_start
                    text: page.optional.tor.service.running ? "Stop service…" : "Start service…"; gapColor: Theme.surfaceRaised
                    onClicked: page.askOptional("tor", page.optional.tor.service.running ? "stop" : "start", "Change the default Tor service for this session using its existing configuration. It may contact the Tor network. No system routes or proxy settings are changed.")
                }
            }
        }
        SettingRow {
            searchKey: "network.tailscale"
            title: "Tailscale"
            desc: !page.optional.tailscale.present ? "Optional private network between your devices. No subscription or account is created here."
                : "Service: " + page.optional.tailscale.state + ". Connection: " + page.optional.tailscale.connection + ". Use the network menu for existing exit-node choices; none is selected automatically."
            resettable: false
            Row {
                spacing: Theme.space2
                ArButton {
                    visible: !page.optional.tailscale.present
                    text: "Install…"; gapColor: Theme.surfaceRaised
                    onClicked: page.askOptional("tailscale", "install", "Install Tailscale from Fedora. Sign-in and network routing remain separate choices.")
                }
                ArButton {
                    visible: page.optional.tailscale.present && !page.optional.tailscale.running
                    text: "Start service…"; gapColor: Theme.surfaceRaised
                    onClicked: page.askOptional("tailscale", "start", "Start the existing Tailscale service for this session. A previously authenticated configuration may reconnect; its existing routing preferences are preserved.")
                }
                ArButton {
                    visible: page.optional.tailscale.running
                    text: page.optional.tailscale.connection === "Running" ? "Disconnect…" : "Sign in / connect…"; gapColor: Theme.surfaceRaised
                    onClicked: page.askOptional("tailscale", page.optional.tailscale.connection === "Running" ? "disconnect" : "login", "Open Tailscale's authenticated connection command in a terminal. Follow its sign-in link yourself if required. Existing routing preferences remain in force; this does not select a new exit node.")
                }
            }
        }
        SettingRow {
            title: "WireGuard and OpenVPN"
            desc: "Import a provider or administrator profile above. WireGuard uses NetworkManager directly. OpenVPN's extra plugin is installed only on request."
            resettable: false
            ArButton {
                visible: !page.optional.openvpn
                text: "Add OpenVPN support…"; gapColor: Theme.surfaceRaised
                onClicked: page.askOptional("openvpn", "install", "Install the OpenVPN NetworkManager plugin. No connection profile is imported or activated automatically.")
            }
        }
    }

    FileDialog {
        id: caDialog
        property string uuid: ""
        title: "Pick your network's certificate"
        nameFilters: ["Certificates (*.pem *.crt *.cer *.der)", "All files (*)"]
        onAccepted: page.savedCall(["network-ca-set", uuid, String(selectedFile)])
    }

    FileDialog {
        id: vpnDialog
        title: "Import a VPN file"
        nameFilters: ["VPN files (*.ovpn *.conf)", "All files (*)"]
        onAccepted: page.savedCall(["vpn", "import", String(selectedFile)])
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
