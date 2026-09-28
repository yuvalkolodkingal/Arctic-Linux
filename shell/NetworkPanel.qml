pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// The network menu (bar network item, Super + Ctrl + W): Wi-Fi on/off, the wired link, nearby
// Wi-Fi networks (scanned only while this is open), joining with the password asked right under
// the network, company (802.1X) networks with a username and password, hidden networks, a
// network's actions (disconnect, connect automatically, forget), a hotspot, VPN switches,
// Tailscale (with its exit nodes), and Settings / the connection editor. Everything goes through network.py
// (NetworkService.run); a password travels to it on stdin and is cleared from the field.
FocusScope {
    id: panel
    property var menu: null
    property string page: ''            // '', 'actions', 'join', 'company', 'exit' (Tailscale's exit node)
    property var target: null           // the network whose actions page is open
    property string pending: ''         // SSID being joined
    property string asking: ''          // SSID whose password field is open
    property string askError: ''
    property var errors: ({})           // SSID → what went wrong
    property string vpnPending: ''
    property string vpnAsking: ''
    property string vpnError: ''
    property bool hotspotPending: false
    property var tailscale: null        // network.py tailscale status, when Tailscale is installed
    property bool tailscalePending: false
    property bool tailscaleDenied: false
    property string tailscaleError: ''
    property bool hotspotConfirm: false   // "This disconnects “Home”" asked, not yet answered
    property string hotspotError: ''
    readonly property var wifi: NetworkService.wifi
    readonly property bool wifiOn: wifi !== null && wifi.enabled && wifi.hardware

    implicitWidth: 340
    implicitHeight: (page === '' ? main : page === 'actions' ? actions : page === 'company' ? company
                     : page === 'exit' ? exitPage : join).implicitHeight

    Component.onCompleted: { NetworkService.setScanning(true); sync(NetworkService.networks); showPage(''); refreshTailscale(); }
    // Opened for a saved network whose password changed: its password field is open.
    function showPage(_name) {
        if (menu && menu.options && menu.options.ask) { page = ''; askError = ''; asking = menu.options.ask; }
    }
    Component.onDestruction: NetworkService.setScanning(false)

    // The scan list as a model that is updated in place, so rows (and a half-typed password)
    // survive the rescans every few seconds.
    ListModel { id: networks }
    function sync(list) {
        for (let i = networks.count - 1; i >= 0; i--)
            if (!list.some(n => n.ssid === networks.get(i).ssid)) networks.remove(i);
        list.forEach((n, i) => {
            const row = { ssid: n.ssid, signal: n.signal || 0, band: n.band || '', security: n.security || 'open',
                          in_use: !!n.in_use, saved: !!n.saved, uuid: n.uuid || '' };
            let at = -1;
            for (let j = 0; j < networks.count; j++) if (networks.get(j).ssid === n.ssid) { at = j; break; }
            if (at < 0) networks.insert(i, row);
            else { if (at !== i) networks.move(at, i, 1); networks.set(i, row); }
        });
    }
    Connections {
        target: NetworkService
        function onNetworksChanged() { panel.sync(NetworkService.networks); }
    }

    function setError(ssid, text) {
        const e = Object.assign({}, errors);
        if (text) e[ssid] = text; else delete e[ssid];
        errors = e;
    }
    function signalWord(s) { return s >= 67 ? 'strong signal' : s >= 34 ? 'good signal' : 'weak signal'; }
    function detailFor(n) {
        if (pending === n.ssid) return 'Connecting…';
        const active = NetworkService.wifiActive;
        if (n.in_use && active && active.state !== 'activated') return 'Connecting…';
        if (n.in_use) return 'Connected · ' + signalWord(n.signal);
        if (n.saved) return 'Saved · ' + signalWord(n.signal);
        if (n.security === 'enterprise') return 'Company login (802.1X)';
        if (n.security === 'open') return 'Open network';
        if (n.security === 'owe') return 'Open network, encrypted';
        return 'Secured · ' + signalWord(n.signal);
    }
    function activate(n) {
        setError(n.ssid, '');
        if (n.in_use) { openActions(n); return; }
        if (n.security === 'enterprise') { openCompany(n.ssid, false); return; }
        if (n.saved || n.security === 'open' || n.security === 'owe') connect(n, null);
        else { askError = ''; asking = n.ssid; }
    }
    // A saved profile (uuid) is brought up; a new network gets a profile first. With `secret`
    // the helper reads it from stdin (--ask).
    function connect(n, secret) {
        pending = n.ssid;
        const args = n.uuid ? ['connect', '--uuid', n.uuid, '--name', n.ssid, '--security', n.security]
                            : ['connect', '--ssid', n.ssid, '--security', n.security].concat(n.hidden ? ['--hidden'] : []);
        if (secret) args.push('--ask');
        NetworkService.run(args, secret, r => {
            if (panel.pending === n.ssid) panel.pending = '';
            if (r.ok) {
                if (panel.asking === n.ssid) panel.asking = '';
                if (panel.page === 'join') panel.page = '';
                return;
            }
            if (r.code === 'auth' && n.security !== 'open' && n.security !== 'owe') {
                if (panel.page === 'join') { joinPassword.selectAll(); panel.joinError = r.error; return; }
                // A saved network whose password no longer works, or a wrong one just typed.
                panel.askError = secret ? r.error : '';
                panel.asking = n.ssid;
                return;
            }
            if (panel.page === 'join') panel.joinError = r.error;
            else panel.setError(n.ssid, r.error);
        });
    }
    function openCompany(ssid, hidden) {
        companySsid = ssid;
        companyHidden = hidden;
        companyError = '';
        page = 'company';
    }
    function joinCompany(secret) {
        companyError = '';
        pending = companySsid;
        const args = ['enterprise', '--ssid', companySsid, '--eap', companyEap, '--phase2', companyPhase2,
                      '--identity', companyUser.text.trim(), companyCheck ? '--system-ca' : '--no-ca', '--ask'];
        if (companyAnon.text.trim()) args.push('--anonymous-identity', companyAnon.text.trim());
        if (companyDomain.text.trim()) args.push('--domain', companyDomain.text.trim());
        if (companyHidden) args.push('--hidden');
        NetworkService.run(args, secret, r => {
            panel.pending = '';
            if (r.ok) { panel.page = ''; return; }
            panel.companyError = r.error;
            companyPassword.selectAll();
        });
    }
    function openActions(n) {
        target = { ssid: n.ssid, uuid: n.uuid, in_use: n.in_use, saved: n.saved, security: n.security };
        confirmForget = false;
        page = 'actions';
    }
    function closePage() {
        page = '';
        Qt.callLater(() => main.start());
    }
    function external(command) {
        if (menu) menu.close();
        Quickshell.execDetached(command);
    }

    // ---- main page ----------------------------------------------------------------------------
    MenuList {
        id: main
        anchors.fill: parent
        visible: panel.page === ''
        focus: visible

        MenuHeader {
            title: panel.wifi ? 'Wi-Fi' : 'Network'
            showSwitch: panel.wifi !== null
            checked: panel.wifiOn
            switchEnabled: panel.wifi !== null && panel.wifi.hardware
            detail: !NetworkService.nmRunning ? 'NetworkManager isn’t running'
                    : NetworkService.airplane ? 'Airplane mode is on'
                    : panel.wifi && !panel.wifi.hardware ? 'Turned off by a switch on the computer' : ''
            onToggled: on => NetworkService.run(['radio', 'wifi', on ? 'on' : 'off'], null, null)
        }
        MenuRow {
            visible: NetworkService.airplane
            icon: 'airplane'
            label: 'Turn off airplane mode'
            onActivated: ToggleRegistry.set('airplane', 'off')
        }
        Repeater {
            model: NetworkService.wired
            MenuRow {
                required property var modelData
                icon: 'ethernet'
                label: 'Wired'
                detail: modelData.state === 'connected' ? 'Connected' : modelData.state === 'connecting' ? 'Connecting…'
                        : modelData.state === 'unavailable' ? 'Cable unplugged' : 'Not connected'
                selected: modelData.state === 'connected'
            }
        }
        MenuSection {
            visible: panel.wifiOn
            text: 'Networks'
            busy: NetworkService.scanning && networks.count === 0
        }
        Text {
            visible: panel.wifiOn && networks.count === 0
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: 'Looking for networks…'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        Repeater {
            model: panel.wifiOn ? networks : null
            ColumnLayout {
                id: entry
                required property string ssid
                required property int signal
                required property string security
                required property bool in_use
                required property bool saved
                required property string uuid
                readonly property var net: ({ ssid: ssid, signal: signal, security: security, in_use: in_use, saved: saved, uuid: uuid })
                Layout.fillWidth: true
                spacing: 0
                MenuRow {
                    icon: entry.signal >= 67 ? 'wifi' : entry.signal >= 34 ? 'wifi-2' : 'wifi-1'
                    iconBase: 'wifi'
                    label: entry.ssid
                    detail: panel.detailFor(entry.net)
                    errorText: panel.errors[entry.ssid] || ''
                    selected: entry.in_use
                    busy: panel.pending === entry.ssid
                    trailing: entry.security !== 'open' && entry.security !== 'owe' && !entry.in_use ? 'lock' : ''
                    onActivated: panel.activate(entry.net)
                    onSecondary: panel.openActions(entry.net)
                    onDeleteRequested: if (entry.saved) { panel.openActions(entry.net); panel.confirmForget = true; }
                }
                MenuField {
                    id: password
                    visible: panel.asking === entry.ssid
                    label: 'Password for “' + entry.ssid + '”'
                    secret: true
                    minLength: entry.security === 'wep' ? 5 : 8
                    errorText: panel.askError
                    busy: panel.pending === entry.ssid
                    onVisibleChanged: if (visible) Qt.callLater(() => main.focusItem(password))
                    onSubmitted: text => { panel.connect(entry.net, text); password.clear(); }
                    onCancelled: { panel.asking = ''; panel.askError = ''; }
                    Connections {
                        target: panel
                        function onAskErrorChanged() { if (panel.askError && password.visible) password.focusField(); }
                    }
                }
            }
        }
        MenuRow {
            visible: panel.wifiOn
            icon: 'plus'
            label: 'Join another network…'
            onActivated: { panel.joinError = ''; panel.joinSecurity = 'wpa-psk'; panel.page = 'join'; }
        }

        // Hotspot (a Wi-Fi card that can be an access point): phones and laptops join this
        // computer and share its connection, usually the wired one.
        MenuSwitchRow {
            id: hotspotRow
            visible: panel.wifiOn && NetworkService.hotspotCapable
            icon: 'hotspot'
            label: 'Hotspot'
            checked: NetworkService.hotspot.active
            busy: panel.hotspotPending
            detail: NetworkService.hotspot.active ? 'On · “' + NetworkService.hotspot.ssid + '”'
                    : NetworkService.wiredLink ? 'Shares your wired connection' : 'Off'
            errorText: panel.hotspotError
            onToggled: on => {
                if (panel.hotspotConfirm) panel.hotspotConfirm = false;
                else if (on && NetworkService.wifiActive) panel.hotspotConfirm = true;
                else panel.setHotspot(on);
            }
        }
        MenuRow {
            visible: hotspotRow.visible && panel.hotspotConfirm && NetworkService.wifiActive !== null
            icon: 'hotspot'
            label: 'Turn on the hotspot'
            detail: 'This disconnects “' + (NetworkService.wifiActive ? NetworkService.wifiActive.name : '') + '”.'
            onActivated: panel.setHotspot(true)
        }
        MenuRow {
            visible: hotspotRow.visible && NetworkService.hotspot.active
            icon: 'qr-code'
            label: 'Show the name and password…'
            onActivated: panel.menu.shell.shareWifi(NetworkService.hotspot.uuid, NetworkService.hotspot.ssid)
        }

        MenuSection {
            visible: NetworkService.vpn.length > 0 || tailscaleRow.visible
            text: 'VPN'
        }
        Repeater {
            model: NetworkService.vpn
            ColumnLayout {
                id: vpnEntry
                required property var modelData
                Layout.fillWidth: true
                spacing: 0
                MenuSwitchRow {
                    icon: 'key'
                    label: vpnEntry.modelData.name
                    checked: vpnEntry.modelData.active
                    busy: panel.vpnPending === vpnEntry.modelData.uuid
                    detail: vpnEntry.modelData.active ? 'Connected' : vpnEntry.modelData.kind === 'wireguard' ? 'WireGuard' : 'VPN'
                    errorText: panel.vpnAsking === '' && panel.vpnError && panel.vpnPending === '' && panel.vpnFailed === vpnEntry.modelData.uuid ? panel.vpnError : ''
                    onToggled: on => panel.vpnSwitch(vpnEntry.modelData, on, null)
                }
                MenuField {
                    id: vpnPassword
                    visible: panel.vpnAsking === vpnEntry.modelData.uuid
                    label: 'Password for “' + vpnEntry.modelData.name + '”'
                    secret: true
                    errorText: panel.vpnError
                    busy: panel.vpnPending === vpnEntry.modelData.uuid
                    onVisibleChanged: if (visible) Qt.callLater(() => main.focusItem(vpnPassword))
                    onSubmitted: text => { panel.vpnSwitch(vpnEntry.modelData, true, text); vpnPassword.clear(); }
                    onCancelled: { panel.vpnAsking = ''; panel.vpnError = ''; }
                }
            }
        }

        // Tailscale (when it is installed and its service runs).
        MenuSwitchRow {
            id: tailscaleRow
            readonly property var ts: panel.tailscale
            visible: ts !== null && ts.state !== 'no_daemon'
            icon: 'key'
            label: 'Tailscale'
            checked: ts !== null && ts.state === 'running'
            busy: panel.tailscalePending || (ts !== null && ts.state === 'starting')
            detail: ts === null ? '' : ts.state === 'running' ? (ts.tailnet || 'Connected') + (ts.exit_node ? ' · through ' + ts.exit_node : '')
                    : ts.state === 'signed_out' ? 'Signed out · turn on to sign in' : 'Off'
            errorText: panel.tailscaleError
            onToggled: on => panel.tailscaleRun([on ? 'up' : 'down'], false)
        }
        MenuRow {
            visible: tailscaleRow.visible && panel.tailscaleDenied
            icon: 'lock'
            label: 'Let Arctic switch Tailscale'
            detail: 'Asks for your password once'
            onActivated: panel.tailscaleRun(['operator'], true)
        }
        MenuRow {
            visible: tailscaleRow.visible && tailscaleRow.checked && tailscaleRow.ts.exit_nodes.length > 0
            icon: 'globe'
            label: 'Exit node'
            detail: tailscaleRow.ts && tailscaleRow.ts.exit_node ? tailscaleRow.ts.exit_node : 'None'
            trailing: 'chevron'
            onActivated: panel.page = 'exit'
        }

        MenuRow {
            visible: Tools.has('arctic-settings')
            icon: 'key'
            label: 'Add a VPN…'
            detail: 'Import an OpenVPN or WireGuard file in Settings'
            onActivated: panel.external(['arctic-settings', 'network'])
        }
        MenuSeparator {}
        MenuRow {
            visible: Tools.has('arctic-settings')
            icon: 'sliders'
            label: 'Network settings'
            onActivated: panel.external(['arctic-settings', 'network'])
        }
        MenuRow {
            visible: Tools.has('nm-connection-editor')
            icon: 'globe'
            label: 'Edit connections…'
            trailing: 'external'
            onActivated: panel.external(['nm-connection-editor'])
        }
    }

    function refreshTailscale() {
        if (!Tools.has('tailscale')) return;
        NetworkService.run(['tailscale', 'status'], null, r => { if (r.ok) panel.tailscale = r; });
    }
    // Tailscale's state changes outside Arctic too (another device, its own CLI): read it again
    // every few seconds while the menu is open.
    Timer { interval: 5000; repeat: true; running: panel.tailscale !== null; onTriggered: panel.refreshTailscale() }
    Connections {
        target: Tools
        function onReadyChanged() { panel.refreshTailscale(); }
    }
    // `thenUp`: after "Let Arctic switch Tailscale" worked, turn it on as was asked.
    function tailscaleRun(args, thenUp) {
        tailscaleError = '';
        tailscalePending = true;
        NetworkService.run(['tailscale'].concat(args), null, r => {
            panel.tailscalePending = false;
            if (r.ok && r.login_url) { panel.external(['xdg-open', r.login_url]); return; }
            if (!r.ok) {
                panel.tailscaleError = r.code === 'cancelled' ? '' : r.error;
                panel.tailscaleDenied = r.code === 'denied' || (panel.tailscaleDenied && r.code === 'cancelled');
            } else {
                panel.tailscaleDenied = false;
                if (thenUp) { panel.tailscaleRun(['up'], false); return; }
            }
            panel.refreshTailscale();
        });
    }

    function setHotspot(on) {
        hotspotConfirm = false;
        hotspotError = '';
        hotspotPending = true;
        NetworkService.run(['hotspot', on ? 'on' : 'off'], null, r => {
            panel.hotspotPending = false;
            if (!r.ok) panel.hotspotError = r.error;
        });
    }

    property string vpnFailed: ''
    function vpnSwitch(v, on, secret) {
        vpnError = '';
        vpnFailed = '';
        vpnPending = v.uuid;
        const args = on ? ['vpn-up', '--uuid', v.uuid, '--name', v.name].concat(secret ? ['--ask'] : []) : ['vpn-down', '--uuid', v.uuid];
        NetworkService.run(args, secret, r => {
            panel.vpnPending = '';
            if (r.ok) { panel.vpnAsking = ''; return; }
            panel.vpnError = r.error;
            if (on && r.code === 'auth') panel.vpnAsking = v.uuid;
            else panel.vpnFailed = v.uuid;
        });
    }

    // ---- a network's actions ------------------------------------------------------------------
    property bool confirmForget: false
    MenuPage {
        id: actions
        anchors.fill: parent
        visible: panel.page === 'actions'
        focus: visible
        title: panel.target ? panel.target.ssid : ''
        detail: panel.target && panel.target.in_use ? 'Connected' : panel.target && panel.target.saved ? 'Saved' : ''
        backText: 'Wi-Fi'
        onBack: panel.closePage()
        onVisibleChanged: if (visible) Qt.callLater(() => actions.first())

        MenuRow {
            visible: panel.target !== null && panel.target.in_use
            icon: 'wifi-off'
            label: 'Disconnect'
            onActivated: {
                const a = NetworkService.wifiActive;
                if (a) NetworkService.run(['disconnect', '--uuid', a.uuid], null, null);
                panel.closePage();
            }
        }
        MenuRow {
            readonly property var profile: panel.target ? NetworkService.savedFor(panel.target.ssid) : null
            visible: profile !== null && panel.target.security !== 'enterprise' && Tools.has('qrencode')
            icon: 'qr-code'
            label: 'Share with a phone…'
            onActivated: panel.menu.shell.shareWifi(profile.uuid, panel.target.ssid)
        }
        MenuSwitchRow {
            readonly property var profile: panel.target ? NetworkService.savedFor(panel.target.ssid) : null
            visible: profile !== null
            label: 'Connect automatically'
            checked: profile ? profile.autoconnect : false
            onToggled: on => NetworkService.run(['autoconnect', '--uuid', profile.uuid, on ? 'on' : 'off'], null, null)
        }
        MenuRow {
            visible: panel.target !== null && panel.target.saved && !panel.confirmForget
            icon: 'trash'
            label: 'Forget this network'
            destructive: true
            onActivated: panel.confirmForget = true
        }
        ColumnLayout {
            visible: panel.confirmForget
            Layout.fillWidth: true
            Layout.margins: Theme.space2
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            spacing: Theme.space2
            onVisibleChanged: if (visible) Qt.callLater(() => forgetButton.forceActiveFocus())
            Text {
                Layout.fillWidth: true
                text: panel.target ? 'Forget “' + panel.target.ssid + '”? You’ll need the password to join again.' : ''
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 13
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space2
                Item { Layout.fillWidth: true }
                ArcticButton {
                    id: keepButton
                    text: 'Cancel'
                    variant: 'ghost'
                    size: 'sm'
                    KeyNavigation.tab: forgetButton
                    KeyNavigation.backtab: forgetButton
                    onClicked: panel.confirmForget = false
                }
                ArcticButton {
                    id: forgetButton
                    text: 'Forget'
                    variant: 'destructive'
                    size: 'sm'
                    KeyNavigation.tab: keepButton
                    KeyNavigation.backtab: keepButton
                    onClicked: {
                        NetworkService.run(['forget', '--ssid', panel.target.ssid], null, null);
                        panel.confirmForget = false;
                        panel.closePage();
                    }
                }
            }
        }
    }

    // ---- Tailscale's exit node ------------------------------------------------------------------
    MenuPage {
        id: exitPage
        anchors.fill: parent
        visible: panel.page === 'exit'
        focus: visible
        title: 'Exit node'
        detail: 'Go online through another of your devices'
        backText: panel.wifi ? 'Wi-Fi' : 'Network'
        onBack: panel.closePage()
        onVisibleChanged: if (visible) Qt.callLater(() => exitPage.first())

        MenuRow {
            readonly property bool current: panel.tailscale !== null && !panel.tailscale.exit_node
            label: 'None'
            detail: 'Your own connection'
            selected: current
            trailing: current ? 'check' : ''
            onActivated: { panel.tailscaleRun(['exit-node', 'none'], false); panel.closePage(); }
        }
        Repeater {
            model: panel.tailscale ? panel.tailscale.exit_nodes : []
            MenuRow {
                required property var modelData
                label: modelData.name
                detail: modelData.online ? modelData.ip : 'Offline'
                enabled: modelData.online
                selected: modelData.active
                trailing: modelData.active ? 'check' : ''
                onActivated: { panel.tailscaleRun(['exit-node', modelData.ip], false); panel.closePage(); }
            }
        }
    }

    // ---- join another (hidden) network ----------------------------------------------------------
    property string joinSecurity: 'wpa-psk'
    property string joinError: ''
    MenuPage {
        id: join
        anchors.fill: parent
        visible: panel.page === 'join'
        focus: visible
        title: 'Join another network'
        detail: 'For networks that don’t show their name'
        backText: 'Wi-Fi'
        onBack: panel.closePage()
        onVisibleChanged: if (visible) Qt.callLater(() => join.focusItem(joinName))

        MenuField {
            id: joinName
            label: 'Network name'
            showButtons: false
            onSubmitted: join.focusItem(panel.joinSecurity === 'open' ? joinButton : joinPassword)
        }
        MenuSection { text: 'Security' }
        Repeater {
            model: [{ id: 'open', label: 'None' }, { id: 'wpa-psk', label: 'WPA or WPA2 Personal' },
                    { id: 'sae', label: 'WPA3 Personal' }, { id: 'wep', label: 'WEP' },
                    { id: 'enterprise', label: 'WPA or WPA2 Enterprise (company login)' }]
            MenuRow {
                required property var modelData
                label: modelData.label
                selected: panel.joinSecurity === modelData.id
                trailing: modelData.id === 'enterprise' ? 'chevron' : ''
                Accessible.role: Accessible.RadioButton
                onActivated: {
                    if (modelData.id !== 'enterprise') { panel.joinSecurity = modelData.id; return; }
                    if (joinName.text.trim() === '') { panel.joinError = 'Type the network’s name first.'; join.focusItem(joinName); return; }
                    panel.openCompany(joinName.text.trim(), true);
                }
            }
        }
        MenuField {
            id: joinPassword
            visible: panel.joinSecurity !== 'open'
            label: 'Password'
            secret: true
            minLength: panel.joinSecurity === 'wep' ? 5 : 8
            primaryText: 'Join'
            showCancel: false
            errorText: panel.joinError
            busy: panel.pending !== '' && panel.pending === joinName.text
            onSubmitted: text => {
                panel.joinError = '';
                panel.connect({ ssid: joinName.text.trim(), security: panel.joinSecurity, hidden: true, uuid: '' }, text);
                joinPassword.clear();
            }
        }
        MenuRow {
            id: joinButton
            visible: panel.joinSecurity === 'open'
            icon: 'wifi'
            label: 'Join'
            errorText: panel.joinError
            busy: panel.pending !== '' && panel.pending === joinName.text
            enabled: joinName.text.trim() !== ''
            onActivated: panel.connect({ ssid: joinName.text.trim(), security: 'open', hidden: true, uuid: '' }, null)
        }
    }

    // ---- a company (802.1X) network: username and password -------------------------------------
    property string companySsid: ''
    property bool companyHidden: false
    property string companyEap: 'peap'
    property string companyPhase2: 'mschapv2'
    property bool companyCheck: true
    property string companyError: ''
    MenuPage {
        id: company
        anchors.fill: parent
        visible: panel.page === 'company'
        focus: visible
        title: panel.companySsid
        detail: 'Company or school login (802.1X)'
        backText: 'Wi-Fi'
        onBack: panel.closePage()
        onVisibleChanged: if (visible) Qt.callLater(() => company.focusItem(companyUser))

        MenuField {
            id: companyUser
            label: 'Username'
            placeholder: 'name@example.org'
            showButtons: false
            onSubmitted: company.focusItem(companyPassword)
        }
        MenuSection { text: 'Sign-in method' }
        Repeater {
            model: [{ eap: 'peap', phase2: 'mschapv2', label: 'PEAP with MSCHAPv2', detail: 'The usual one (eduroam, Windows networks)' },
                    { eap: 'ttls', phase2: 'pap', label: 'TTLS with PAP', detail: '' },
                    { eap: 'ttls', phase2: 'mschapv2', label: 'TTLS with MSCHAPv2', detail: '' },
                    { eap: 'peap', phase2: 'gtc', label: 'PEAP with GTC', detail: '' }]
            MenuRow {
                required property var modelData
                label: modelData.label
                detail: modelData.detail
                selected: panel.companyEap === modelData.eap && panel.companyPhase2 === modelData.phase2
                Accessible.role: Accessible.RadioButton
                onActivated: { panel.companyEap = modelData.eap; panel.companyPhase2 = modelData.phase2; }
            }
        }
        MenuSwitchRow {
            label: 'Check the network’s certificate'
            detail: panel.companyCheck ? 'With the certificates this computer trusts'
                                       : 'Not recommended: another network could pretend to be this one'
            checked: panel.companyCheck
            onToggled: on => panel.companyCheck = on
        }
        MenuField {
            id: companyDomain
            label: 'Domain (optional)'
            placeholder: 'example.org'
            showButtons: false
            onSubmitted: company.focusItem(companyPassword)
        }
        MenuField {
            id: companyAnon
            label: 'Anonymous identity (optional)'
            placeholder: 'anonymous@example.org'
            showButtons: false
            onSubmitted: company.focusItem(companyPassword)
        }
        MenuField {
            id: companyPassword
            label: 'Password'
            secret: true
            primaryText: 'Join'
            showCancel: false
            errorText: panel.companyError
            busy: panel.pending !== '' && panel.pending === panel.companySsid
            onSubmitted: text => {
                if (companyUser.text.trim() === '') { panel.companyError = 'Type your username first.'; company.focusItem(companyUser); return; }
                panel.joinCompany(text);
                companyPassword.clear();
            }
        }
        Text {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: 'Signing in with a certificate of your own (EAP-TLS) is set up in Edit connections.'
            wrapMode: Text.WordWrap
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 12
        }
    }
}
