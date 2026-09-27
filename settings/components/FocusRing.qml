// focus-ring token: a 2px gap in the surface colour, then 2px solid amber.
// Put it inside the control; it draws outside the control's bounds.
import QtQuick
import ".."

Item {
    id: ring
    property real radius: Theme.radiusMd
    property bool show: false
    property color gapColor: Theme.surface
    property bool inset: false            // list rows: 2px amber inside the edge
    anchors.fill: parent
    anchors.margins: inset ? 0 : -4
    visible: show
    z: 100

    Rectangle {
        anchors.fill: parent
        radius: ring.inset ? ring.radius : ring.radius + 4
        color: "transparent"
        border.width: 2
        border.color: Theme.focus
        antialiasing: true
    }
    Rectangle {
        visible: !ring.inset
        anchors.fill: parent
        anchors.margins: 2
        radius: ring.radius + 2
        color: "transparent"
        border.width: 2
        border.color: ring.gapColor
        antialiasing: true
    }
}
