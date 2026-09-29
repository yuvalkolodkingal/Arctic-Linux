pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// Quick Settings (Super + A, `arctic-shell-ipc quick toggle`): battery, Settings / Lock /
// Power, the volume and brightness sliders, the toggle registry's tiles and what is playing.
// A tile's chevron (or a slider's) opens that menu as a page here, with "‹ Quick settings";
// Esc goes back, then closes. `quick open <page>` opens straight on a page.
FocusScope {
    id: panel
    property var menu: null
    property string page: ''
    readonly property var pageComponents: ({
        network: networkPage, bluetooth: bluetoothPage, sound: soundPage,
        battery: batteryPage, display: displayPage, media: mediaPage
    })

    implicitWidth: 380
    implicitHeight: page === '' ? main.implicitHeight : back.implicitHeight + (sub.item ? sub.item.implicitHeight : 0)

    Component.onCompleted: {
        ToggleRegistry.refresh('');
        BrightnessService.refresh();
        if (menu && menu.options && menu.options.page) showPage(menu.options.page);
    }
    function showPage(name) {
        page = pageComponents[name] ? name : '';
        Qt.callLater(() => { if (page === '') main.start(); else if (sub.item) sub.item.forceActiveFocus(); });
    }
    function external(command) {
        if (menu) menu.close();
        Quickshell.execDetached(command);
    }

    // ---- the main page --------------------------------------------------------------------------
    MenuList {
        id: main
        anchors.fill: parent
        visible: panel.page === ''
        focus: visible

        RowLayout {
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space1
            Layout.topMargin: Theme.space1
            Layout.bottomMargin: Theme.space1
            spacing: Theme.space1
            Icon {
                visible: BatteryService.present
                name: BatteryService.charging ? 'battery-charging' : 'battery'
                size: 18
                color: BatteryService.low ? Theme.error : Theme.ink
            }
            Text {
                Layout.fillWidth: true
                text: BatteryService.present ? BatteryService.percent + ' %' + (BatteryService.timeText ? ' · ' + BatteryService.timeText : '') : ''
                elide: Text.ElideRight
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 13
                font.weight: Font.Medium
                font.features: { 'tnum': 1 }
            }
            Repeater {
                model: [
                    { key: 'settings', icon: 'sliders', label: 'Settings', visible: Tools.has('arctic-settings') },
                    { key: 'lock', icon: 'lock', label: 'Lock screen', visible: !Session.live },
                    { key: 'power', icon: 'power', label: 'Power', visible: true }
                ]
                ArcticButton {
                    required property var modelData
                    readonly property bool menuStop: true
                    visible: modelData.visible
                    iconName: modelData.icon
                    iconOnly: true
                    label: modelData.label
                    variant: 'ghost'
                    size: 'sm'
                    focusPolicy: Qt.NoFocus
                    onClicked: {
                        if (modelData.key === 'settings') panel.external(['arctic-settings']);
                        else if (modelData.key === 'lock') { if (panel.menu) panel.menu.close(); panel.menu.shell.lock(); }
                        else { const s = panel.menu.screen; panel.menu.close(); panel.menu.shell.togglePower(s, undefined); }
                    }
                }
            }
        }
        MenuSlider {
            visible: AudioService.available
            icon: 'volume'
            mutedIcon: 'volume-mute'
            label: 'Volume'
            value: AudioService.volume
            muted: AudioService.muted
            showChevron: true
            onMoved: v => AudioService.setVolume(v)
            onMuteToggled: AudioService.toggleMute()
            onOpened: panel.showPage('sound')
        }
        MenuSlider {
            visible: BrightnessService.focused !== null
            icon: 'brightness'
            canMute: false
            label: 'Brightness'
            value: BrightnessService.focused ? BrightnessService.focused.percent / 100 : 0
            showChevron: true
            onMoved: v => BrightnessService.set(BrightnessService.focused, Math.round(v * 100))
            onOpened: panel.showPage('display')
        }
        GridLayout {
            Layout.fillWidth: true
            Layout.margins: Theme.space1
            columns: 2
            rowSpacing: Theme.space2
            columnSpacing: Theme.space2
            Repeater {
                model: ToggleRegistry.visibleToggles
                QuickTile {
                    required property var modelData
                    toggle: modelData
                    onPageRequested: p => panel.showPage(p)
                }
            }
        }
        MenuRow {
            visible: MediaService.available && MediaService.title !== ''
            icon: 'music'
            label: MediaService.title
            detail: MediaService.artist
            trailing: 'chevron'
            onActivated: panel.showPage('media')
            onSecondary: MediaService.playPause()
        }
    }

    // ---- a menu as a page -----------------------------------------------------------------------
    FocusScope {
        id: subPage
        anchors.fill: parent
        visible: panel.page !== ''
        focus: visible
        Keys.onEscapePressed: panel.showPage('')
        Keys.onPressed: event => {
            if ((event.key === Qt.Key_Left || event.key === Qt.Key_Backspace) && sub.item && sub.item.page !== undefined && sub.item.page === '') {
                panel.showPage('');
                event.accepted = true;
            }
        }
        MenuRow {
            id: back
            readonly property bool headerStop: true
            x: Theme.space1
            y: Theme.space1
            width: parent.width - 2 * Theme.space1
            icon: 'chevron-left'
            iconColor: Theme.inkMuted
            label: 'Quick settings'
            onActivated: panel.showPage('')
            implicitHeight: 34 + Theme.space1
        }
        Loader {
            id: sub
            anchors.top: back.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            focus: true
            active: panel.page !== ''
            sourceComponent: panel.pageComponents[panel.page] || null
        }
    }
    Component { id: networkPage; NetworkPanel { menu: panel.menu } }
    Component { id: bluetoothPage; BluetoothPanel { menu: panel.menu } }
    Component { id: soundPage; SoundPanel { menu: panel.menu } }
    Component { id: batteryPage; BatteryPanel { menu: panel.menu } }
    Component { id: displayPage; DisplayPanel { menu: panel.menu } }
    Component { id: mediaPage; MediaPanel { menu: panel.menu } }
}
