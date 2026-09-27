// .ar-kbd — a keyboard key chip.
import QtQuick
import ".."

Rectangle {
    id: kbd
    property string text: ""
    implicitWidth: label.implicitWidth + 2 * Theme.space1 + 2
    implicitHeight: 18 + 2
    radius: Theme.radiusXs
    color: Theme.surfaceRaised
    border.width: 1
    border.color: Theme.lineStrong
    Accessible.role: Accessible.StaticText
    Accessible.name: text

    Text {
        id: label
        anchors.centerIn: parent
        text: kbd.text
        color: Theme.inkMuted
        font.family: Theme.fontMono
        font.pixelSize: 12
        font.weight: Font.Bold
    }
}
