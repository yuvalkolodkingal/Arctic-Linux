import QtQuick
import QtQuick.Templates as T

// Design switch (.ar-toggle, as in the installer): a 40×24 pill track, amber when on, with a
// 16px knob that stretches while pressed, and an optional label. Space toggles; keyboard focus
// shows the focus ring.
T.Switch {
    id: control
    property int labelSize: 13

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    padding: 0
    spacing: Theme.space2
    implicitWidth: implicitIndicatorWidth + (text !== '' ? spacing + implicitContentWidth : 0)
    implicitHeight: Math.max(Theme.targetMin, implicitIndicatorHeight, implicitContentHeight)
    Accessible.role: Accessible.CheckBox
    Accessible.name: text
    Accessible.checkable: true
    Accessible.checked: checked

    indicator: Rectangle {
        implicitWidth: 40
        implicitHeight: 24
        x: control.leftPadding
        y: (control.height - height) / 2
        radius: 12
        antialiasing: true
        color: !control.enabled ? Theme.surfaceSunken
             : control.checked ? (control.pressed ? Theme.accentPressed : control.hovered ? Theme.accentHover : Theme.accent)
             : Theme.surfaceSunken
        border.width: control.checked && control.enabled ? 1 : 1.5
        border.color: !control.enabled ? Theme.line : control.checked ? Theme.accentEdge
                    : control.hovered ? Theme.inkMuted : Theme.lineStrong
        Behavior on color { ColorAnimation { duration: Theme.durationBase } }
        Rectangle {
            y: 4
            x: control.checked ? (control.pressed ? 16 : 20) : 4
            width: control.pressed ? 20 : 16
            height: 16
            radius: 8
            antialiasing: true
            color: !control.enabled ? Theme.inkDisabled : control.checked ? Theme.onAccent : Theme.inkMuted
            Behavior on x { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
            Behavior on width { NumberAnimation { duration: Theme.durationFast } }
        }
        FocusRing { targetRadius: 12; shown: control.visualFocus }
    }

    contentItem: Text {
        leftPadding: control.indicator.width + control.spacing
        verticalAlignment: Text.AlignVCenter
        visible: control.text !== ''
        text: control.text
        textFormat: Text.PlainText
        color: control.enabled ? Theme.ink : Theme.inkDisabled
        font.family: Theme.fontSans
        font.pixelSize: control.labelSize
        font.weight: Font.Medium
        elide: Text.ElideRight
    }
}
