import QtQuick
import QtQuick.Layouts

// The title of a bar menu (15/600) with an optional detail line and an optional switch for the
// whole thing ("Wi-Fi", "Bluetooth"), or, on a page, a back row ("‹ Wi-Fi"). The switch and the
// back row are stops; a plain title is not.
ColumnLayout {
    id: header
    property string title: ''
    property string detail: ''
    property string trailingText: ''
    property bool showSwitch: false
    property bool checked: false
    property bool switchEnabled: true
    property bool busy: false
    property string backText: ''
    signal toggled(bool on)
    signal back()

    Layout.fillWidth: true
    spacing: 0

    MenuRow {
        visible: header.backText !== ''
        icon: 'chevron-left'
        iconColor: Theme.inkMuted
        label: header.backText
        onActivated: header.back()
    }
    Item {
        id: titleRow
        readonly property bool menuStop: header.showSwitch
        readonly property bool menuBreakAfter: true
        readonly property bool headerStop: true     // not where the keyboard starts (MenuList.start)
        readonly property string label: header.title
        readonly property bool highlighted: header.showSwitch && header.switchEnabled
                                            && (mouse.containsMouse || (activeFocus && MenuState.keyboardNav))
        enabled: !header.showSwitch || header.switchEnabled
        Layout.fillWidth: true
        implicitHeight: Math.max(header.detail !== '' ? 50 : 40, titleLayout.implicitHeight + 12)
        Accessible.role: header.showSwitch ? Accessible.CheckBox : Accessible.Heading
        Accessible.name: header.title
        Accessible.description: header.detail
        Accessible.checkable: header.showSwitch
        Accessible.checked: header.checked
        Keys.onPressed: event => {
            MenuState.keyboardNav = true;
            if (!header.showSwitch) return;
            if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                if (header.switchEnabled && !header.busy) header.toggled(!header.checked);
                event.accepted = true;
            }
        }
        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusSm
            color: titleRow.highlighted ? Theme.surfaceSunken : 'transparent'
        }
        RowLayout {
            id: titleLayout
            anchors.fill: parent
            anchors.leftMargin: Theme.space3
            anchors.rightMargin: Theme.space3
            spacing: Theme.space2
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1
                Text {
                    Layout.fillWidth: true
                    text: header.title
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }
                Text {
                    Layout.fillWidth: true
                    visible: header.detail !== ''
                    text: header.detail
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.features: { 'tnum': 1 }
                }
            }
            Text {
                visible: header.trailingText !== ''
                text: header.trailingText
                textFormat: Text.PlainText
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
                font.weight: Font.DemiBold
                font.features: { 'tnum': 1 }
            }
            Spinner { visible: header.busy; running: visible }
            ArcticSwitch {
                visible: header.showSwitch
                checked: header.checked
                enabled: header.switchEnabled
                focusPolicy: Qt.NoFocus
            }
        }
        MouseArea {
            id: mouse
            anchors.fill: parent
            visible: header.showSwitch
            enabled: header.switchEnabled
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPositionChanged: MenuState.keyboardNav = false
            onClicked: if (!header.busy) header.toggled(!header.checked)
        }
    }
}
