import QtQuick
import QtQuick.Layouts
import ".."

// The header of a Get apps page: Back, the title, an optional count or subtitle, and room on
// the right for the page's own controls (`default` children).
RowLayout {
    id: header
    property string title: ''
    property string detail: ''
    default property alias trailing: extra.data
    signal back()
    spacing: Theme.space2
    Layout.fillWidth: true

    ArcticButton { variant: 'ghost'; size: 'sm'; iconName: 'chevron-left'; text: 'Back'; focusPolicy: Qt.NoFocus; onClicked: header.back() }
    Text {
        text: header.title
        color: Theme.ink
        font.family: Theme.fontSans
        font.pixelSize: 16
        font.weight: Font.DemiBold
    }
    Text {
        visible: text !== ''
        text: header.detail
        color: Theme.inkSubtle
        font.family: Theme.fontSans
        font.pixelSize: 12
        font.features: { 'tnum': 1 }
    }
    Item { Layout.fillWidth: true }
    RowLayout { id: extra; spacing: Theme.space2 }
}
