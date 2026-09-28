import QtQuick
import QtQuick.Layouts

// A Quick Settings tile for one registry toggle (Toggle.qml): a split button, 56px high. The
// main part switches it (Space/Enter); the chevron part (Right) opens its page. Off: surface-
// sunken; on: accent-soft with a 1px accent edge and the icon in accent-text (a checked
// control); cycle tiles (power mode) stay sunken and name the current mode.
Item {
    id: tile
    required property var toggle
    readonly property bool menuStop: true
    readonly property string label: toggle.label
    readonly property bool on: toggle.kind !== 'cycle' && toggle.active
    readonly property bool hasPage: toggle.page !== ''
    signal pageRequested(string page)

    Layout.fillWidth: true
    implicitWidth: 168
    implicitHeight: 56
    Accessible.role: toggle.kind === 'cycle' ? Accessible.Button : Accessible.CheckBox
    Accessible.name: toggle.label
    Accessible.description: toggle.detail
    Accessible.checkable: toggle.kind !== 'cycle'
    Accessible.checked: on

    Keys.onPressed: event => {
        MenuState.keyboardNav = true;
        if (event.key === Qt.Key_Space || event.key === Qt.Key_Return || event.key === Qt.Key_Enter) tile.toggle.toggle();
        else if (event.key === Qt.Key_Right && tile.hasPage) tile.pageRequested(tile.toggle.page);
        else return;
        event.accepted = true;
    }

    Rectangle {
        id: face
        anchors.fill: parent
        radius: Theme.radiusMd
        color: tile.on ? Theme.accentSoft : mainMouse.containsMouse || pageMouse.containsMouse ? Theme.line : Theme.surfaceSunken
        border.width: tile.on ? 1 : 0
        border.color: Theme.accentEdge
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
        FocusRing { targetRadius: Theme.radiusMd; shown: tile.activeFocus && MenuState.keyboardNav }
    }
    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space3
        anchors.rightMargin: tile.hasPage ? 0 : Theme.space3
        spacing: Theme.space2
        Icon {
            name: !tile.toggle.active && tile.toggle.iconOff !== '' ? tile.toggle.iconOff : tile.toggle.icon
            size: 20
            color: tile.on ? Theme.accentText : Theme.ink
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 0
            Text {
                Layout.fillWidth: true
                text: tile.toggle.label
                elide: Text.ElideRight
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
            Text {
                Layout.fillWidth: true
                text: tile.toggle.detail
                elide: Text.ElideRight
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 12
            }
        }
        Spinner { visible: tile.toggle.busy; running: visible; size: 14 }
        // The chevron segment, split off by a 1px line.
        Item {
            visible: tile.hasPage
            Layout.fillHeight: true
            Layout.preferredWidth: 30
            Rectangle {
                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width: 1
                height: parent.height - 2 * Theme.space3
                color: tile.on ? Theme.accentEdge : Theme.lineStrong
                opacity: 0.6
            }
            Icon { anchors.centerIn: parent; name: 'chevron-right'; size: 16; color: tile.on ? Theme.accentText : Theme.inkMuted }
            MouseArea {
                id: pageMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: { MenuState.keyboardNav = false; tile.pageRequested(tile.toggle.page); }
            }
            Accessible.role: Accessible.Button
            Accessible.name: tile.toggle.label + ' settings'
        }
    }
    MouseArea {
        id: mainMouse
        anchors.fill: parent
        anchors.rightMargin: tile.hasPage ? 30 : 0
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: { MenuState.keyboardNav = false; tile.toggle.toggle(); }
    }
}
