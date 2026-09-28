// The 20px box of .ar-check (checkbox) or .ar-check.radio.
import QtQuick
import ".."

Rectangle {
    id: box
    property bool radio: false
    property bool checked: false
    property bool hovered: false
    property bool pressed: false
    property bool disabled: false
    property bool error: false
    property bool focusRing: false

    implicitWidth: 20
    implicitHeight: 20
    radius: radio ? 10 : Theme.radiusXs
    antialiasing: true
    color: {
        if (disabled)
            return checked && !radio ? Theme.line : Theme.surfaceSunken;
        if (radio)
            return Theme.surfaceRaised;
        if (checked)
            return pressed ? Theme.accentPressed : hovered ? Theme.accentHover : Theme.accent;
        return pressed ? Theme.surfaceSunken : Theme.surfaceRaised;
    }
    border.width: radio && checked && !disabled ? 6 : 1.5
    border.color: {
        if (error)
            return Theme.error;
        if (disabled)
            return Theme.line;
        if (checked)
            return radio ? (hovered ? Theme.accentHover : Theme.accent) : Theme.accentEdge;
        return hovered ? Theme.inkMuted : Theme.lineStrong;
    }
    Behavior on color {
        ColorAnimation { duration: Theme.durationFast }
    }

    // Winter: a 1px accent-edge ring keeps the amber radio at 3:1 on white.
    Rectangle {
        visible: box.radio && box.checked && !box.disabled && !Theme.dark
        anchors.fill: parent
        anchors.margins: -1
        radius: width / 2
        color: "transparent"
        border.width: 1
        border.color: Theme.accentEdge
    }
    Icon {
        visible: !box.radio && box.checked
        anchors.centerIn: parent
        name: "check"
        size: 14
        stroke: 2.5
        color: box.disabled ? Theme.inkDisabled : Theme.inkOnAccent
    }
    FocusRing {
        show: box.focusRing
        radius: box.radius
    }
}
