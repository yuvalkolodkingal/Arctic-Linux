// The brand focus ring: a 2 px gap in the surface colour, then 2 px amber
// (`focus-ring` = 0 0 0 2px surface, 0 0 0 4px focus). Shown only while the
// target has keyboard focus.
import QtQuick
import ".."

Item {
    id: ring
    property real radius: Theme.radiusMd
    property bool shown: false

    anchors.fill: parent
    visible: shown

    Rectangle {
        anchors.fill: parent
        anchors.margins: -2
        radius: ring.radius + 2
        color: "transparent"
        border.width: 2
        border.color: Theme.surface
        antialiasing: true
    }
    Rectangle {
        anchors.fill: parent
        anchors.margins: -4
        radius: ring.radius + 4
        color: "transparent"
        border.width: 2
        border.color: Theme.focus
        antialiasing: true
    }
}
