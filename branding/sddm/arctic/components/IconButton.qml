// Icon-only button (design: Button, `iconOnly`). `ghost` for the power
// cluster, `primary` for the one amber action (log in).
import QtQuick
import ".."

Item {
    id: button

    property string icon
    property string label            // accessible name + tooltip
    property string variant: "ghost" // "ghost" | "primary"
    property real size: Theme.controlMd
    property bool showFocus: false   // keyboard focus ring (set by Main)
    property bool tooltip: variant === "ghost"
    readonly property bool hovered: mouse.containsMouse

    signal clicked()

    implicitWidth: size
    implicitHeight: size

    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: button.clicked()

    Keys.onPressed: (event) => {
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            button.clicked()
            event.accepted = true
        }
    }

    Rectangle {
        id: face
        anchors.fill: parent
        radius: button.variant === "primary" ? Theme.radiusMd : Math.min(Theme.radiusMd, height / 2)
        color: {
            if (button.variant === "primary")
                return mouse.pressed ? Theme.accentPressed : (button.hovered ? Theme.accentHover : Theme.accent)
            return mouse.pressed ? Theme.line : (button.hovered ? Theme.surfaceSunken : "transparent")
        }
        border.width: button.variant === "primary" ? 1 : 0
        border.color: Theme.dark ? Theme.accent : Theme.accentEdge
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
    }

    Icon {
        anchors.centerIn: parent
        name: button.icon
        size: 18
        color: button.variant === "primary" ? Theme.onAccent : Theme.ink
    }

    FocusRing {
        radius: face.radius
        shown: button.activeFocus && button.showFocus
    }

    Tooltip {
        text: button.label
        hovered: button.tooltip && button.hovered
        keyboardFocus: button.tooltip && button.activeFocus && button.showFocus
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: button.clicked()
    }
}
