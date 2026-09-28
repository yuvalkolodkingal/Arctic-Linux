import QtQuick
import QtQuick.Templates as T

// A slider in the switch's language (a port of settings/components/ArSlider.qml): a 4px track
// in surface-sunken, the filled part and a 16px knob in amber (amber = the current value).
// ←/→ step it, PgUp/PgDn by a tenth, Home/End to the ends. `committed(value)` fires when a drag
// ends or 400 ms after a key press.
T.Slider {
    id: control
    property string accessibleName: ''
    property string valueText: ''
    property bool showFocus: visualFocus
    signal committed(real value)

    implicitWidth: 200
    implicitHeight: 28
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    live: true
    Accessible.role: Accessible.Slider
    Accessible.name: accessibleName
    Accessible.description: valueText

    onPressedChanged: if (!pressed) control.committed(control.value)
    onMoved: if (!pressed) settle.restart()
    Keys.onPressed: event => {
        const page = Math.max(control.stepSize, (control.to - control.from) / 10);
        let v = control.value;
        if (event.key === Qt.Key_PageUp) v = Math.min(control.to, v + page);
        else if (event.key === Qt.Key_PageDown) v = Math.max(control.from, v - page);
        else if (event.key === Qt.Key_Home) v = control.from;
        else if (event.key === Qt.Key_End) v = control.to;
        else return;
        event.accepted = true;
        control.value = v;
        control.moved();
    }
    Timer {
        id: settle
        interval: 400
        onTriggered: control.committed(control.value)
    }

    background: Rectangle {
        x: control.leftPadding
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.availableWidth
        height: 4
        radius: 2
        color: control.enabled ? Theme.surfaceSunken : Theme.line
        border.width: 1
        border.color: control.enabled ? Theme.lineStrong : Theme.line
        Rectangle {
            width: control.visualPosition * parent.width
            height: parent.height
            radius: 2
            color: control.enabled ? Theme.accent : Theme.inkDisabled
        }
    }

    handle: Rectangle {
        x: control.leftPadding + control.visualPosition * (control.availableWidth - width)
        y: control.topPadding + control.availableHeight / 2 - height / 2
        width: control.pressed ? 18 : 16
        height: width
        radius: width / 2
        antialiasing: true
        color: !control.enabled ? Theme.inkDisabled : control.pressed ? Theme.accentPressed : control.hovered ? Theme.accentHover : Theme.accent
        border.width: 1
        border.color: control.enabled ? Theme.accentEdge : Theme.line
        Behavior on width { NumberAnimation { duration: Theme.durationFast } }
        FocusRing { shown: control.showFocus; targetRadius: parent.radius }
    }
}
