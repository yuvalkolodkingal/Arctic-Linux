// .ar-toggle — a 40×24 switch with a label. Space toggles.
import QtQuick
import QtQuick.Templates as T
import ".."

T.Switch {
    id: control
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    spacing: Theme.space3
    implicitWidth: implicitIndicatorWidth + spacing + (contentItem ? contentItem.implicitWidth : 0)
    implicitHeight: Math.max(Theme.targetMin, implicitIndicatorHeight)
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checkable: true
    Accessible.checked: checked

    indicator: Rectangle {
        id: track
        implicitWidth: 40
        implicitHeight: 24
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 12
        antialiasing: true
        color: !control.enabled ? Theme.surfaceSunken : control.checked ? (control.pressed ? Theme.accentPressed : control.hovered ? Theme.accentHover : Theme.accent) : Theme.surfaceSunken
        border.width: control.checked && control.enabled ? 1 : 1.5
        border.color: !control.enabled ? Theme.line : control.checked ? Theme.accentEdge : control.hovered ? Theme.inkMuted : Theme.lineStrong
        Behavior on color {
            ColorAnimation { duration: Theme.durationBase }
        }
        Rectangle {
            id: knob
            y: 4
            x: control.checked ? (control.pressed ? 12 : 20) : 4
            width: control.pressed ? 20 : 16
            height: 16
            radius: 8
            color: !control.enabled ? Theme.inkDisabled : control.checked ? Theme.inkOnAccent : Theme.inkMuted
            Behavior on x {
                NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
            }
        }
        FocusRing {
            show: control.visualFocus
            radius: 12
        }
    }
    contentItem: ArText {
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        text: control.text
        size: 15
        lh: 22
        color: control.enabled ? Theme.ink : Theme.inkDisabled
    }
}
