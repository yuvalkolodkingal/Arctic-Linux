import QtQuick
import QtQuick.Layouts

// A bar-menu row with a switch: icon, label, detail and the design switch at the end. The row
// is the stop: Enter or Space (or a click anywhere on it) asks to flip it through `toggled`;
// `checked` stays bound to the real state, so the switch only moves once the system agrees.
Item {
    id: row
    property string icon: ''
    property string label: ''
    property string detail: ''
    property string errorText: ''
    property bool checked: false
    property bool busy: false
    readonly property bool menuStop: true
    readonly property bool highlighted: enabled && (mouse.containsMouse || (activeFocus && MenuState.keyboardNav))
    signal toggled(bool on)
    signal secondary()

    Layout.fillWidth: true
    implicitWidth: layout.implicitWidth + 2 * Theme.space3
    implicitHeight: Math.max(detail !== '' || errorText !== '' ? 48 : 38, layout.implicitHeight + 2 * 6)
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.description: errorText || detail
    Accessible.checkable: true
    Accessible.checked: checked

    Keys.onPressed: event => {
        MenuState.keyboardNav = true;
        if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
            if (row.enabled && !row.busy) row.toggled(!row.checked);
        } else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier))) {
            row.secondary();
        } else {
            return;
        }
        event.accepted = true;
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSm
        color: row.highlighted ? Theme.surfaceSunken : 'transparent'
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
    }
    RowLayout {
        id: layout
        anchors.fill: parent
        anchors.leftMargin: Theme.space3
        anchors.rightMargin: Theme.space3
        spacing: Theme.space2 + 2
        Icon {
            visible: row.icon !== ''
            name: row.icon || 'help'
            size: 18
            color: row.enabled ? Theme.ink : Theme.inkDisabled
        }
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text {
                Layout.fillWidth: true
                text: row.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: row.enabled ? Theme.ink : Theme.inkDisabled
                font.family: Theme.fontSans
                font.pixelSize: 15
            }
            Text {
                Layout.fillWidth: true
                visible: row.detail !== '' && row.errorText === ''
                text: row.detail
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: row.enabled ? Theme.inkMuted : Theme.inkDisabled
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.features: { 'tnum': 1 }
            }
            Text {
                Layout.fillWidth: true
                visible: row.errorText !== ''
                text: row.errorText
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
                color: Theme.error
                font.family: Theme.fontSans
                font.pixelSize: 12
            }
        }
        Spinner { visible: row.busy; running: visible }
        ArcticSwitch {
            checked: row.checked
            enabled: row.enabled
            focusPolicy: Qt.NoFocus
        }
    }
    // Over the switch too: a click asks for the change instead of flipping the switch itself.
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: row.enabled
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        cursorShape: Qt.PointingHandCursor
        onPositionChanged: MenuState.keyboardNav = false
        onClicked: m => {
            MenuState.keyboardNav = false;
            if (m.button === Qt.RightButton) row.secondary();
            else if (!row.busy) row.toggled(!row.checked);
        }
    }
}
