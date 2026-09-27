import QtQuick
import QtQuick.Effects

// An image clipped to rounded corners (thumbnails, the lock-screen avatar).
Item {
    id: root
    property alias source: image.source
    property alias fillMode: image.fillMode
    property alias sourceSize: image.sourceSize
    property alias status: image.status
    property real radius: Theme.radiusMd
    Image {
        id: image
        anchors.fill: parent
        asynchronous: true
        fillMode: Image.PreserveAspectCrop
        visible: false
        layer.enabled: true
    }
    Rectangle {
        id: mask
        anchors.fill: parent
        radius: root.radius
        visible: false
        layer.enabled: true
    }
    MultiEffect {
        anchors.fill: parent
        source: image
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }
}
