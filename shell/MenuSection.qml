import QtQuick
import QtQuick.Layouts

// A section label in a bar menu: overline 11px, uppercase, +0.08em, ink-subtle, with optional
// trailing text or a spinner (a scan in progress). Starts a new keyboard group (Tab).
Item {
    id: section
    property string text: ''
    property string trailingText: ''
    property bool busy: false
    readonly property bool menuBreak: true
    Layout.fillWidth: true
    implicitHeight: 30
    Accessible.role: Accessible.Heading
    Accessible.name: text

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space3
        anchors.rightMargin: Theme.space3
        anchors.topMargin: Theme.space2
        spacing: Theme.space2
        Text {
            Layout.fillWidth: true
            text: section.text.toUpperCase()
            textFormat: Text.PlainText
            elide: Text.ElideRight
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 11
            font.weight: Font.DemiBold
            font.letterSpacing: 0.88
        }
        Spinner { visible: section.busy; running: visible; size: 14 }
        Text {
            visible: section.trailingText !== ''
            text: section.trailingText
            textFormat: Text.PlainText
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 11
        }
    }
}
