pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// The power menu (design Menu), under the bar's power item or from Super + Esc.
// Items name what will happen. Settings comes first (the system menu is where people look for
// it); on the live USB there is nothing to lock or log out of, so Restart and Shut down follow.
// The actions run `arctic-power <action>`; Settings runs `arctic-settings`.
Popover {
    id: menu
    required property var shell
    property int current: 0
    readonly property var actions: Session.live
        ? [ { id: 'settings', label: 'Settings', icon: 'sliders', keys: 'Super + S' },
            { id: 'restart', label: 'Restart', icon: 'restart' },
            { id: 'poweroff', label: 'Shut down', icon: 'power' } ]
        : [ { id: 'settings', label: 'Settings', icon: 'sliders', keys: 'Super + S' },
            { id: 'lock', label: 'Lock screen', icon: 'lock', keys: 'Super + L' },
            { id: 'logout', label: 'Log out', icon: 'log-out' },
            { id: 'suspend', label: 'Suspend', icon: 'sleep' },
            { id: 'restart', label: 'Restart', icon: 'restart' },
            { id: 'poweroff', label: 'Shut down', icon: 'power' } ]

    layerName: 'arctic-power'
    placement: 'point'
    scrim: false
    cardColor: Theme.surfaceRaised
    cardRadius: Theme.radiusLg
    cardWidth: 232
    cardHeight: column.implicitHeight + 2 * Theme.space1
    focusItem: column
    onOpened: current = 0

    function run(action) {
        close();
        if (action.id === 'lock') shell.lock();
        else if (action.id === 'settings') Quickshell.execDetached(['arctic-settings']);
        else Quickshell.execDetached(['arctic-power', action.id]);
    }

    Column {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.space1
        spacing: 0
        focus: true
        Keys.onDownPressed: menu.current = (menu.current + 1) % menu.actions.length
        Keys.onUpPressed: menu.current = (menu.current - 1 + menu.actions.length) % menu.actions.length
        Keys.onTabPressed: menu.current = (menu.current + 1) % menu.actions.length
        Keys.onReturnPressed: menu.run(menu.actions[menu.current])
        Keys.onEnterPressed: menu.run(menu.actions[menu.current])
        Keys.onEscapePressed: menu.close()
        Repeater {
            model: menu.actions
            Rectangle {
                id: item
                required property var modelData
                required property int index
                readonly property bool selected: menu.current === index
                width: column.width
                height: 34
                radius: Theme.radiusSm
                color: selected ? Theme.surfaceSunken : 'transparent'
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: Theme.space3
                    anchors.rightMargin: Theme.space3
                    spacing: Theme.space2
                    Icon { name: item.modelData.icon; size: 18; color: Theme.ink }
                    Text {
                        Layout.fillWidth: true
                        text: item.modelData.label
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                    }
                    Kbd { visible: !!item.modelData.keys; text: item.modelData.keys || '' }
                }
                MouseArea {
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onPositionChanged: menu.current = item.index
                    onClicked: menu.run(item.modelData)
                }
            }
        }
    }
}
