// Paints the page colour outside a rounded rectangle, so square content
// (scrolling list rows) never pokes out of a rounded container's corners.
// Works without shader effects.
import QtQuick
import ".."

Item {
    id: mask
    property real radius: Theme.radiusLg
    property color background: Theme.surface
    anchors.fill: parent
    clip: true
    z: 50
    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        anchors.margins: -mask.radius
        radius: mask.radius * 2
        color: "transparent"
        border.width: mask.radius
        border.color: mask.background
        antialiasing: true
    }
}
