import QtQuick
import QtQuick.Layouts

// A 1px line between groups of a bar menu, with space-1 above and below.
Item {
    readonly property bool menuBreak: true
    Layout.fillWidth: true
    implicitHeight: 1 + 2 * Theme.space1
    Rectangle {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: Theme.space2
        anchors.rightMargin: Theme.space2
        height: 1
        color: Theme.line
    }
}
