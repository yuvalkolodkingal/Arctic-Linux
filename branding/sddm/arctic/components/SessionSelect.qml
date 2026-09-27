// Session picker (design: Dropdown). The trigger is a 36 px Input with the
// tiling icon and a chevron; the menu opens upwards (it sits at the bottom of
// the screen): surface-raised, radius-lg, shadow-md, 4 px inset, 34 px items.
// Enter / Space / Up / Down open it, arrows move, Enter picks, Esc closes.
pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Effects
import ".."

Item {
    id: select

    property var model                 // sessionModel
    property int currentIndex: 0
    property bool showFocus: false
    property bool open: false
    property int highlighted: currentIndex
    property string currentName: ""

    signal picked(int index)

    implicitWidth: 220
    implicitHeight: Theme.controlMd

    Accessible.role: Accessible.ComboBox
    Accessible.name: qsTr("Session")
    Accessible.description: currentName

    function openMenu() { highlighted = currentIndex; open = true }
    function choose(i) { if (i >= 0) { currentIndex = i; picked(i) } open = false }

    onActiveFocusChanged: if (!activeFocus) open = false

    Keys.onPressed: (event) => {
        var n = model ? model.count : 0
        if (!open) {
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space
                    || event.key === Qt.Key_Up || event.key === Qt.Key_Down) {
                openMenu(); event.accepted = true
            }
            return
        }
        if (event.key === Qt.Key_Escape) { open = false; event.accepted = true }
        else if (event.key === Qt.Key_Up) { highlighted = Math.max(0, highlighted - 1); event.accepted = true }
        else if (event.key === Qt.Key_Down) { highlighted = Math.min(n - 1, highlighted + 1); event.accepted = true }
        else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            choose(highlighted); event.accepted = true
        }
    }

    // current name (the model only exposes roles through a delegate)
    Repeater {
        model: select.model
        delegate: Item {
            id: sessionEntry
            required property int index
            required property string name
            Binding { target: select; property: "currentName"; value: sessionEntry.name; when: sessionEntry.index === select.currentIndex }
        }
    }

    // ---- trigger ----
    Rectangle {
        anchors.fill: parent
        anchors.margins: -1
        radius: Theme.radiusMd + 1
        color: "transparent"
        border.width: 1
        border.color: Theme.focus
        visible: select.activeFocus && select.showFocus
    }
    Rectangle {
        id: trigger
        anchors.fill: parent
        radius: Theme.radiusMd
        color: Theme.surfaceRaised
        border.width: 1
        border.color: select.activeFocus && select.showFocus ? Theme.focus
                     : triggerMouse.containsMouse ? Theme.inkMuted : Theme.lineStrong
        Behavior on border.color { ColorAnimation { duration: Theme.durationFast } }

        Icon {
            id: lead
            name: "tiling"
            size: 18
            color: Theme.inkMuted
            anchors.left: parent.left
            anchors.leftMargin: Theme.space3
            anchors.verticalCenter: parent.verticalCenter
        }
        Text {
            anchors.left: lead.right
            anchors.leftMargin: Theme.space2
            anchors.right: chev.left
            anchors.rightMargin: Theme.space2
            anchors.verticalCenter: parent.verticalCenter
            text: select.currentName
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 15
            elide: Text.ElideRight
        }
        Icon {
            id: chev
            name: select.open ? "chevron-up" : "chevron-down"
            size: 18
            color: Theme.inkMuted
            anchors.right: parent.right
            anchors.rightMargin: Theme.space3
            anchors.verticalCenter: parent.verticalCenter
        }
        MouseArea {
            id: triggerMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                select.forceActiveFocus()
                if (select.open) select.open = false; else select.openMenu()
            }
        }
    }

    // ---- menu ----
    Item {
        id: menu
        z: 100
        width: Math.max(select.width, column.implicitWidth + 2 * Theme.space1)
        height: column.implicitHeight + 2 * Theme.space1 + 2
        anchors.bottom: parent.top
        anchors.bottomMargin: Theme.space1 + (Theme.reduceMotion || select.open ? 0 : -4)
        anchors.left: parent.left
        opacity: select.open ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: Theme.reduceMotion ? 0 : Theme.durationBase; easing.type: Easing.OutCubic } }
        Behavior on anchors.bottomMargin { NumberAnimation { duration: Theme.reduceMotion ? 0 : Theme.durationBase; easing.type: Easing.OutCubic } }

        RectangularShadow {
            anchors.fill: parent
            offset.y: 8
            blur: 24
            spread: -6
            radius: Theme.radiusLg
            color: Theme.shadowMd
            visible: GraphicsInfo.api !== GraphicsInfo.Software
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusLg
            color: Theme.surfaceRaised
            border.width: 1
            border.color: Theme.line
        }
        Column {
            id: column
            x: Theme.space1 + 1
            y: Theme.space1 + 1
            width: menu.width - 2 * Theme.space1 - 2
            Repeater {
                model: select.model
                delegate: Rectangle {
                    id: item
                    required property int index
                    required property string name
                    readonly property bool selected: index === select.currentIndex
                    readonly property bool hot: index === select.highlighted || itemMouse.containsMouse
                    width: column.width
                    implicitWidth: label.implicitWidth + check.width + 3 * Theme.space3
                    height: 34
                    radius: Theme.radiusSm
                    color: selected ? Theme.accentSoft : (hot ? Theme.surfaceSunken : "transparent")
                    Text {
                        id: label
                        anchors.left: parent.left
                        anchors.leftMargin: Theme.space3
                        anchors.right: check.left
                        anchors.rightMargin: Theme.space2
                        anchors.verticalCenter: parent.verticalCenter
                        text: item.name
                        color: Theme.ink
                        font.family: Theme.fontSans
                        font.pixelSize: 15
                        font.weight: item.selected ? Font.DemiBold : Font.Normal
                        elide: Text.ElideRight
                    }
                    Icon {
                        id: check
                        name: "check"
                        size: 16
                        visible: item.selected
                        color: Theme.accentText
                        anchors.right: parent.right
                        anchors.rightMargin: Theme.space3
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    // keyboard highlight on the selected row: an inset amber edge
                    Rectangle {
                        anchors.fill: parent
                        radius: parent.radius
                        color: "transparent"
                        border.width: 1
                        border.color: Theme.accentEdge
                        visible: item.selected && item.index === select.highlighted && select.showFocus
                    }
                    MouseArea {
                        id: itemMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: select.choose(item.index)
                    }
                }
            }
        }
    }
}
