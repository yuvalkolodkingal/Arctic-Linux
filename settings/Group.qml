// A titled group of settings: a heading (headline 16/24), an optional line of help, and the
// rows on a raised card (radius-lg, 1px line) — the installer's card look.
import QtQuick
import "components"

Column {
    id: group
    property string title: ""
    property string desc: ""
    default property alias rows: box.data
    width: parent ? parent.width : 480
    spacing: Theme.space2
    Accessible.role: Accessible.Grouping
    Accessible.name: title

    Column {
        visible: group.title !== "" || group.desc !== ""
        width: parent.width
        spacing: 2
        ArText {
            visible: group.title !== ""
            text: group.title
            size: 16
            lh: 24
            weight: Font.DemiBold
            Accessible.role: Accessible.Heading
        }
        ArText {
            visible: group.desc !== ""
            width: parent.width
            text: group.desc
            size: 13
            lh: 18
            wrapMode: Text.WordWrap
            color: Theme.inkMuted
        }
    }
    Rectangle {
        width: parent.width
        height: box.implicitHeight
        radius: Theme.radiusLg
        color: Theme.surfaceRaised
        border.width: 1
        border.color: Theme.line
        Column {
            id: box
            width: parent.width
        }
    }
}
