import QtQuick
import QtQuick.Layouts

// An inline form row in a bar menu: a label, a design field (for secrets: hidden text, an eye
// button and no prediction or auto-caps), an error line, then Cancel and the primary button.
// Enter submits, Esc cancels. The text is cleared whenever the row hides, so a password never
// outlives its question.
FocusScope {
    id: form
    property string label: ''
    property string placeholder: ''
    property bool secret: false
    property string errorText: ''
    property string primaryText: 'Connect'
    property string busyText: 'Connecting…'
    property bool busy: false
    property bool showCancel: true
    property bool showButtons: true
    property int minLength: 0
    property alias text: field.text
    readonly property bool menuStop: true
    property bool revealed: false
    signal submitted(string text)
    signal cancelled()

    function selectAll() { field.selectAll(); field.forceActiveFocus(); }
    function clear() { field.clear(); revealed = false; }
    function submit() { if (!busy && field.text.length >= Math.max(1, minLength)) submitted(field.text); }
    function focusField() { field.forceActiveFocus(); }

    Layout.fillWidth: true
    implicitHeight: layout.implicitHeight + 2 * Theme.space2
    onVisibleChanged: if (!visible) clear()
    Component.onDestruction: field.clear()

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: Theme.space2
        anchors.leftMargin: Theme.space3
        anchors.rightMargin: Theme.space3
        spacing: Theme.space2
        Text {
            Layout.fillWidth: true
            visible: form.label !== ''
            text: form.label
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: 13
            font.weight: Font.Medium
        }
        ArcticField {
            id: field
            Layout.fillWidth: true
            focus: true
            enabled: !form.busy
            placeholderText: form.placeholder
            error: form.errorText !== ''
            echoMode: form.secret && !form.revealed ? TextInput.Password : TextInput.Normal
            inputMethodHints: form.secret ? Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase : Qt.ImhNone
            rightPadding: form.secret ? Theme.space2 + 28 : Theme.space3
            Accessible.name: form.label || form.placeholder
            Keys.onReturnPressed: form.submit()
            Keys.onEnterPressed: form.submit()
            Keys.onEscapePressed: form.cancelled()
            KeyNavigation.tab: !form.showButtons ? null : form.showCancel ? cancel : primary
            Rectangle {
                visible: form.secret
                anchors.right: parent.right
                anchors.rightMargin: Theme.space1
                anchors.verticalCenter: parent.verticalCenter
                width: 28
                height: 28
                radius: Theme.radiusSm
                color: eye.containsMouse ? Theme.surfaceSunken : 'transparent'
                Icon { anchors.centerIn: parent; name: form.revealed ? 'eye-off' : 'eye'; size: 16; color: Theme.inkMuted }
                MouseArea {
                    id: eye
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: form.revealed = !form.revealed
                }
                Accessible.role: Accessible.Button
                Accessible.name: form.revealed ? 'Hide password' : 'Show password'
            }
        }
        Text {
            Layout.fillWidth: true
            visible: form.errorText !== ''
            text: form.errorText
            textFormat: Text.PlainText
            wrapMode: Text.WordWrap
            color: Theme.error
            font.family: Theme.fontSans
            font.pixelSize: 12
            lineHeight: 1.2
        }
        RowLayout {
            Layout.fillWidth: true
            visible: form.showButtons
            spacing: Theme.space2
            Item { Layout.fillWidth: true }
            ArcticButton {
                id: cancel
                visible: form.showCancel
                text: 'Cancel'
                variant: 'ghost'
                size: 'sm'
                KeyNavigation.tab: primary
                KeyNavigation.backtab: field
                Keys.onEscapePressed: form.cancelled()
                onClicked: form.cancelled()
            }
            ArcticButton {
                id: primary
                text: form.busy ? form.busyText : form.primaryText
                variant: 'primary'
                size: 'sm'
                enabled: !form.busy && field.text.length >= Math.max(1, form.minLength)
                KeyNavigation.tab: field
                KeyNavigation.backtab: form.showCancel ? cancel : field
                Keys.onEscapePressed: form.cancelled()
                onClicked: form.submit()
            }
        }
    }
}
