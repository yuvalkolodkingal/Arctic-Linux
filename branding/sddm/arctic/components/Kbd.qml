// A keyboard chip (design: Kbd): JetBrains Mono 12/16 bold, 1 px line-strong
// border, radius-xs, surface-raised.
import QtQuick
import ".."

Rectangle {
    property alias text: label.text
    implicitWidth: label.implicitWidth + 2 * Theme.space1 + 2
    implicitHeight: 18
    radius: Theme.radiusXs
    color: Theme.surfaceRaised
    border.width: 1
    border.color: Theme.lineStrong
    Text {
        id: label
        anchors.centerIn: parent
        color: Theme.inkMuted
        font.family: Theme.fontMono
        font.pixelSize: 12
        font.weight: Font.Bold
    }
}
