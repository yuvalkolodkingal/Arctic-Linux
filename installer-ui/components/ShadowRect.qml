// A rounded surface with the shadow-sm / shadow-md token approximated by
// offset layers (no shader effects, so it also works with software rendering).
import QtQuick
import ".."

Item {
    id: root
    property alias color: face.color
    property alias border: face.border
    property real radius: Theme.radiusLg
    property int elevation: 1            // 0 none, 1 shadow-sm, 2 shadow-md
    property alias face: face

    Rectangle {
        visible: root.elevation >= 2
        x: -2; y: 4; width: root.width + 4; height: root.height + 6
        radius: root.radius + 3
        color: Theme.dark ? "#40000000" : "#0f12171e"
    }
    Rectangle {
        visible: root.elevation >= 1
        x: 0; y: 1; width: root.width; height: root.height + (root.elevation >= 2 ? 2 : 1)
        radius: root.radius
        color: root.elevation >= 2 ? Theme.shadowMd : Theme.shadowSm
        opacity: root.elevation >= 2 ? 0.6 : 1
    }
    Rectangle {
        id: face
        anchors.fill: parent
        radius: root.radius
        color: Theme.surfaceRaised
        antialiasing: true
    }
}
