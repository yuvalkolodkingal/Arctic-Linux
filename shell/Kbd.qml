import QtQuick

// A keyboard key chip: JetBrains Mono 12/700, line-strong border (design Kbd).
Rectangle {
    id: kbd
    property string text: ''
    property bool inverse: false        // inside a tooltip
    implicitWidth: label.implicitWidth + 2 * Theme.space1 + 2
    implicitHeight: 18
    radius: Theme.radiusXs
    color: inverse ? 'transparent' : Theme.surfaceRaised
    border.width: 1
    border.color: inverse ? Theme.inkSubtle : Theme.lineStrong
    Text {
        id: label
        anchors.centerIn: parent
        text: kbd.text
        color: kbd.inverse ? Theme.inkInverse : Theme.inkMuted
        font.family: Theme.fontMono
        font.pixelSize: kbd.inverse ? 11 : 12
        font.weight: Font.Bold
    }
}
