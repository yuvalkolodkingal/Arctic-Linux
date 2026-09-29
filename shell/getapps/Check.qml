import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import ".."

// Design Checkbox: an 18px box (line-strong border; ticked = amber with a check) and its
// label. Space or Enter toggles it; the focus ring shows for keyboard focus.
AbstractButton {
    id: control
    checkable: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    // A click, not toggle(): toggle() doesn't emit toggled, which the sheets' options follow.
    Keys.onReturnPressed: click()
    Keys.onEnterPressed: click()
    implicitHeight: Math.max(24, label.implicitHeight)
    implicitWidth: row.implicitWidth
    background: null
    contentItem: RowLayout {
        id: row
        spacing: Theme.space2
        Rectangle {
            Layout.alignment: Qt.AlignTop
            Layout.topMargin: 2
            implicitWidth: 18
            implicitHeight: 18
            radius: Theme.radiusXs
            color: control.checked ? Theme.accent : Theme.surfaceRaised
            border.width: control.checked ? 0 : 1
            border.color: Theme.lineStrong
            Icon { anchors.centerIn: parent; visible: control.checked; name: 'check'; size: 14; color: Theme.onAccent }
            FocusRing { targetRadius: Theme.radiusXs; shown: control.visualFocus }
        }
        Text {
            id: label
            Layout.fillWidth: true
            text: control.text
            color: control.enabled ? Theme.ink : Theme.inkDisabled
            font.family: Theme.fontSans
            font.pixelSize: 13
            wrapMode: Text.Wrap
        }
    }
}
