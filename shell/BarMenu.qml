import QtQuick
import Quickshell

// The one popover every bar menu opens in (network, Bluetooth, sound, calendar, battery, media,
// tray, Quick Settings): a raised card with shadow-md under its bar item. `panel` picks what it
// shows; switching panels while open resizes and slides the card (duration-base). One host means
// one menu at a time by construction, and Ctrl+Tab can swap to the neighbouring item's menu.
// Panels are plain items with implicitWidth/implicitHeight; the card is capped to the screen
// and the panel's list scrolls inside.
Popover {
    id: host
    required property var shell
    property string panel: ''
    property var options: ({})
    readonly property var item: loader.item

    layerName: 'arctic-menu'
    placement: 'point'
    scrim: false
    shadow: 2
    animateSize: true
    grabKeyboard: !shell.modalOpen
    cardColor: Theme.surfaceRaised
    cardRadius: Theme.radiusLg
    cardWidth: item ? item.implicitWidth : 320
    cardHeight: Math.min(item ? item.implicitHeight : 120, maxCardHeight)
    focusItem: item
    Behavior on pointX { enabled: host.open; NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }

    onOpened: MenuState.keyboardNav = !!options.keyboard
    // A dialog over the menu (polkit, Bluetooth pairing) had the keyboard; take it back.
    Connections {
        target: host.shell
        function onModalOpenChanged() { if (!host.shell.modalOpen) Qt.callLater(host.focusContent); }
    }

    // Panel id → component; each work package adds its panel here.
    readonly property var panels: ({
        network: networkPanel,
        bluetooth: bluetoothPanel,
    })
    Component { id: networkPanel; NetworkPanel { menu: host } }
    Component { id: bluetoothPanel; BluetoothPanel { menu: host } }

    FocusScope {
        anchors.fill: parent
        focus: true
        Keys.onPressed: event => {
            // Ctrl+Tab / Ctrl+Shift+Tab: the neighbouring menu on the same bar.
            if ((event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) && (event.modifiers & Qt.ControlModifier)) {
                host.shell.cyclePanel(host.screen, event.key === Qt.Key_Backtab || (event.modifiers & Qt.ShiftModifier) ? -1 : 1);
                event.accepted = true;
            }
        }
        Loader {
            id: loader
            anchors.fill: parent
            focus: true
            active: host.shown && host.panel !== ''
            sourceComponent: host.panels[host.panel] || null
            onLoaded: if (host.open) Qt.callLater(host.focusContent)
        }
    }
}
