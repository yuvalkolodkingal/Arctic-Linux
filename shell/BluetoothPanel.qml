pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Bluetooth

// The Bluetooth menu (bar Bluetooth item, Super + Ctrl + B): power, your devices (click to
// connect or disconnect; right click, the Menu key or the dots for a device's page: stay
// trusted, battery, forget), and "Pair a new device", which makes the computer visible and
// searches while it is open. Codes and questions while pairing come up in BluetoothPairDialog
// through the shell's own agent. blueman-manager stays reachable for file transfer and more.
FocusScope {
    id: panel
    property var menu: null
    property string page: ''            // '', 'device', 'pair'
    property var target: null           // the device whose page is open
    property bool confirmForget: false
    property string pairError: ''
    property string pairing: ''         // address being paired
    property bool wasDiscoverable: false
    property bool searching: false      // this menu made the adapter visible and searching
    readonly property var adapter: BluetoothService.adapter
    readonly property bool on: BluetoothService.enabled

    implicitWidth: 340
    implicitHeight: (page === '' ? main : page === 'device' ? devicePage : pairPage).implicitHeight

    Component.onCompleted: if (menu && menu.options && menu.options.page) showPage(menu.options.page)
    function showPage(name) { if (name === 'pair') openPair(); else if (name === '') back(); }
    Component.onDestruction: stopSearch()
    onPageChanged: if (page !== 'pair') stopSearch()

    function external(command) {
        if (menu) menu.close();
        Quickshell.execDetached(command);
    }
    function openDevice(d) {
        target = d;
        confirmForget = false;
        page = 'device';
    }
    function back() {
        page = '';
        Qt.callLater(() => main.start());
    }
    function openPair() {
        if (!adapter) return;
        if (!adapter.enabled) adapter.enabled = true;
        pairError = '';
        page = 'pair';
        BluetoothService.claimDefault();
        if (!searching) wasDiscoverable = adapter.discoverable;
        searching = true;
        adapter.pairable = true;
        adapter.discoverable = true;
        search();
    }
    function search() {
        if (!adapter) return;
        adapter.discovering = true;
        searchTimer.restart();
    }
    // Leaving the pairing page (or closing the menu): stop searching, hide the computer again.
    function stopSearch() {
        searchTimer.stop();
        if (!adapter || !searching) return;
        searching = false;
        if (adapter.discovering) adapter.discovering = false;
        if (adapter.discoverable !== wasDiscoverable) adapter.discoverable = wasDiscoverable;
    }
    function pair(d) {
        pairError = '';
        pairing = d.address;
        BluetoothService.expect(d.address);
        d.pair();
    }
    function toggleConnect(d) {
        if (d.connected) d.disconnect(); else d.connect();
    }
    Timer { id: searchTimer; interval: 60000; onTriggered: if (panel.adapter) panel.adapter.discovering = false }

    // ---- main page ----------------------------------------------------------------------------
    MenuList {
        id: main
        anchors.fill: parent
        visible: panel.page === ''
        focus: visible

        MenuHeader {
            title: 'Bluetooth'
            showSwitch: true
            checked: panel.on
            switchEnabled: panel.adapter !== null && panel.adapter.state !== BluetoothAdapterState.Blocked
            busy: panel.adapter !== null && (panel.adapter.state === BluetoothAdapterState.Enabling || panel.adapter.state === BluetoothAdapterState.Disabling)
            detail: panel.adapter && panel.adapter.state === BluetoothAdapterState.Blocked ? 'Turned off by a switch on the computer' : ''
            onToggled: on => BluetoothService.setEnabled(on)
        }
        MenuSection {
            visible: panel.on
            text: 'Your devices'
        }
        Repeater {
            model: panel.on && panel.adapter ? panel.adapter.devices : null
            MenuRow {
                required property var modelData
                visible: modelData.paired || modelData.connected
                icon: BluetoothService.iconFor(modelData.icon)
                label: modelData.name || modelData.address
                detail: BluetoothService.stateText(modelData)
                selected: modelData.connected
                busy: modelData.state === BluetoothDeviceState.Connecting || modelData.state === BluetoothDeviceState.Disconnecting
                trailing: 'dots'
                onActivated: panel.toggleConnect(modelData)
                onSecondary: panel.openDevice(modelData)
                onDeleteRequested: { panel.openDevice(modelData); panel.confirmForget = true; }
            }
        }
        Text {
            visible: panel.on && panel.adapter !== null && !panel.adapter.devices.values.some(d => d.paired || d.connected)
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: 'No devices yet.'
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        MenuRow {
            visible: panel.on
            icon: 'plus'
            label: 'Pair a new device'
            trailing: 'chevron'
            onActivated: panel.openPair()
        }
        MenuSeparator {}
        MenuRow {
            visible: Tools.has('arctic-settings')
            icon: 'sliders'
            label: 'Bluetooth settings'
            onActivated: panel.external(['arctic-settings', 'bluetooth'])
        }
        MenuRow {
            visible: Tools.has('blueman-manager')
            icon: 'bluetooth'
            label: 'More Bluetooth options…'
            trailing: 'external'
            onActivated: panel.external(['blueman-manager'])
        }
    }

    // ---- one device ---------------------------------------------------------------------------
    MenuPage {
        id: devicePage
        anchors.fill: parent
        visible: panel.page === 'device'
        focus: visible
        readonly property var d: panel.target
        title: d ? (d.name || d.address) : ''
        detail: d ? BluetoothService.stateText(d) : ''
        backText: 'Bluetooth'
        onBack: panel.back()
        onVisibleChanged: if (visible) Qt.callLater(() => devicePage.start())

        MenuRow {
            visible: devicePage.d !== null
            icon: devicePage.d && devicePage.d.connected ? 'x-circle' : 'bluetooth'
            label: devicePage.d && devicePage.d.connected ? 'Disconnect' : 'Connect'
            busy: devicePage.d !== null && (devicePage.d.state === BluetoothDeviceState.Connecting || devicePage.d.state === BluetoothDeviceState.Disconnecting)
            onActivated: panel.toggleConnect(devicePage.d)
        }
        MenuSwitchRow {
            visible: devicePage.d !== null
            label: 'Let it connect without asking'
            detail: 'It can reconnect by itself when it is near'
            checked: devicePage.d ? devicePage.d.trusted : false
            onToggled: on => devicePage.d.trusted = on
        }
        MenuRow {
            visible: devicePage.d !== null && devicePage.d.batteryAvailable
            icon: 'battery'
            label: 'Battery'
            trailing: 'text'
            trailingText: BluetoothService.batteryText(devicePage.d)
        }
        MenuRow {
            visible: devicePage.d !== null && !panel.confirmForget
            icon: 'trash'
            label: 'Forget this device'
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
                text: devicePage.d ? 'Forget “' + (devicePage.d.name || devicePage.d.address) + '”? You’ll need to pair it again.' : ''
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
                        const d = devicePage.d;
                        panel.confirmForget = false;
                        panel.back();
                        if (d) d.forget();
                    }
                }
            }
        }
    }

    // ---- pairing ------------------------------------------------------------------------------
    MenuPage {
        id: pairPage
        anchors.fill: parent
        visible: panel.page === 'pair'
        focus: visible
        title: 'Pair a new device'
        detail: panel.adapter ? 'Visible as “' + panel.adapter.name + '” while this is open' : ''
        backText: 'Bluetooth'
        onBack: panel.back()
        onVisibleChanged: if (visible) Qt.callLater(() => pairPage.start())

        MenuSection {
            text: 'Nearby'
            busy: panel.adapter !== null && panel.adapter.discovering
        }
        Repeater {
            model: panel.adapter ? panel.adapter.devices : null
            MenuRow {
                id: candidate
                required property var modelData
                visible: !modelData.paired && modelData.deviceName !== ''
                icon: BluetoothService.iconFor(modelData.icon)
                label: modelData.name || modelData.deviceName
                detail: modelData.pairing ? 'Pairing…' : 'Ready to pair'
                busy: modelData.pairing
                errorText: panel.pairError !== '' && panel.pairing === modelData.address ? panel.pairError : ''
                onActivated: modelData.pairing ? modelData.cancelPair() : panel.pair(modelData)
                Keys.onEscapePressed: event => {
                    if (modelData.pairing) { modelData.cancelPair(); event.accepted = true; }
                    else event.accepted = false;
                }
                Connections {
                    target: candidate.modelData
                    function onPairedChanged() {
                        if (!candidate.modelData.paired || panel.pairing !== candidate.modelData.address) return;
                        candidate.modelData.trusted = true;
                        candidate.modelData.connect();
                        panel.pairing = '';
                        panel.back();
                    }
                    function onPairingChanged() {
                        if (candidate.modelData.pairing || candidate.modelData.paired || panel.pairing !== candidate.modelData.address) return;
                        panel.pairError = 'Couldn’t pair with “' + candidate.label + '”. Make sure it’s in pairing mode, then try again.';
                    }
                }
            }
        }
        Text {
            visible: panel.adapter !== null && !panel.adapter.devices.values.some(d => !d.paired && d.deviceName !== '')
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: panel.adapter && panel.adapter.discovering ? 'Looking for devices… Put the device in pairing mode.' : 'Nothing found.'
            wrapMode: Text.WordWrap
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        MenuRow {
            visible: panel.adapter !== null && !panel.adapter.discovering
            icon: 'refresh'
            label: 'Search again'
            onActivated: panel.search()
        }
    }
}
