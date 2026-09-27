import QtQuick
import QtQuick.Controls
Button {
    id: control
    property bool prominent: false
    implicitHeight: 36
    implicitWidth: label.implicitWidth + 28
    hoverEnabled: true
    font.family: Theme.font
    font.pixelSize: 12
    background: Rectangle {
        radius: 8
        color: control.prominent ? Theme.accent : control.hovered ? Qt.lighter(Theme.surface, 1.4) : Theme.surface
        opacity: control.enabled ? (control.down ? 0.7 : 1) : 0.4
        border.width: control.activeFocus ? 2 : 0
        border.color: Theme.text
    }
    contentItem: Text {
        id: label
        text: control.text
        font: control.font
        color: control.prominent ? '#111318' : Theme.text
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        opacity: control.enabled ? 1 : 0.5
    }
}
