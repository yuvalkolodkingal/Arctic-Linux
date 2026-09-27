// A round avatar (design: `.ar-avatar`): the user's face image when they set
// one, otherwise their initial on warm-soft. The selected user is 64 px with
// the amber ring (2 px surface gap + 2 px accent-edge); others are 40 px.
import QtQuick
import QtQuick.Effects
import ".."

Item {
    id: avatar

    property string name        // display name, for the initial
    property url face           // userModel `icon`
    property bool selected: false
    property bool showFocus: false
    property bool guest: false  // guest accounts get the user glyph instead of an initial

    readonly property real diameter: selected ? 64 : 40
    // SDDM hands every user the default face (…/faces/.face.icon) when they
    // have none; draw the initial instead of that generic picture.
    readonly property bool hasFace: {
        var f = face.toString()
        return f !== "" && !/\/faces\/\.face\.icon$/.test(f) && image.status === Image.Ready
    }

    width: diameter
    height: diameter

    Behavior on width { enabled: !Theme.reduceMotion; NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutCubic } }

    // selection ring
    Rectangle {
        visible: avatar.selected
        anchors.centerIn: parent
        width: parent.width + 8
        height: width
        radius: width / 2
        color: Theme.accentEdge
        Rectangle {
            anchors.centerIn: parent
            width: parent.width - 4
            height: width
            radius: width / 2
            color: Theme.surface
        }
    }

    Rectangle {
        id: disc
        anchors.fill: parent
        radius: width / 2
        color: Theme.warmSoft
        antialiasing: true
        Text {
            anchors.centerIn: parent
            visible: !avatar.hasFace && avatar.name !== "" && !avatar.guest
            text: avatar.name.length ? avatar.name.charAt(0).toUpperCase() : ""
            color: Theme.warm
            font.family: Theme.fontSans
            font.weight: Font.DemiBold
            font.pixelSize: avatar.selected ? 24 : 16
        }
        Icon {
            anchors.centerIn: parent
            visible: !avatar.hasFace && (avatar.name === "" || avatar.guest)
            name: "user"
            size: avatar.selected ? 26 : 18
            color: Theme.warm
        }
    }

    Image {
        id: image
        anchors.fill: parent
        source: avatar.face
        sourceSize: Qt.size(128, 128)
        fillMode: Image.PreserveAspectCrop
        visible: false
        asynchronous: false
    }
    Item {
        id: circleMask
        anchors.fill: parent
        visible: false
        layer.enabled: true
        Rectangle { anchors.fill: parent; radius: width / 2; color: "white"; antialiasing: true }
    }
    MultiEffect {
        anchors.fill: parent
        visible: avatar.hasFace
        source: image
        maskEnabled: true
        maskSource: circleMask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }

    FocusRing {
        radius: width / 2
        shown: avatar.showFocus
        anchors.margins: avatar.selected ? -4 : 0
    }
}
