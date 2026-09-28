import QtQuick

// The keyboard layout on the bar ("EN", "HE"), shown only with more than one layout. Click:
// the next layout; right click: the layout menu (KeyboardPanel.qml). The tooltip names the
// layout and the key that switches it (Settings → Keyboard and mouse sets that key).
BarItem {
    id: item
    visible: KeyboardService.multiple
    text: KeyboardService.shortName
    textWeight: Font.DemiBold
    tooltip: KeyboardService.name + (KeyboardService.switchLabel ? ' · switch with ' + KeyboardService.switchLabel : '')
             + ' · right click for all layouts'
    onClicked: KeyboardService.next()
}
