// .ar-check.radio — radio button with label and optional description.
// Arrow keys move within an exclusive group (ButtonGroup / autoExclusive).
import QtQuick
import QtQuick.Templates as T
import ".."

T.RadioButton {
    id: control
    property string description: ""
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    spacing: Theme.space3
    topPadding: Theme.space1
    bottomPadding: Theme.space1
    implicitWidth: implicitIndicatorWidth + spacing + (contentItem ? contentItem.implicitWidth : 0)
    implicitHeight: Math.max(Theme.targetMin, Math.max(implicitIndicatorHeight + 1, contentItem ? contentItem.implicitHeight : 0) + topPadding + bottomPadding)
    Accessible.role: Accessible.RadioButton
    Accessible.name: text
    Accessible.description: description
    Accessible.checkable: true
    Accessible.checked: checked

    indicator: ArCheckIndicator {
        radio: true
        x: control.leftPadding
        y: control.topPadding + 1
        checked: control.checked
        hovered: control.hovered
        pressed: control.pressed
        disabled: !control.enabled
        focusRing: control.visualFocus
    }
    contentItem: Column {
        leftPadding: control.indicator.width + control.spacing
        ArText {
            text: control.text
            size: 15
            lh: 22
            color: control.enabled ? Theme.ink : Theme.inkDisabled
        }
        ArText {
            visible: control.description !== ""
            text: control.description
            size: 13
            lh: 18
            color: control.enabled ? Theme.inkMuted : Theme.inkDisabled
        }
    }
}
