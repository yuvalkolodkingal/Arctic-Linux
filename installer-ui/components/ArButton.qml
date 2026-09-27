// .ar-btn — primary (the one amber action), secondary, ghost, destructive;
// sizes sm 28 / md 36 / lg 44. States: hover, pressed, keyboard focus (ring),
// disabled, error. Enter and Space activate.
import QtQuick
import QtQuick.Templates as T
import ".."

T.Button {
    id: control
    property string variant: "secondary"
    property string size: "md"
    property string iconName: ""
    property string iconRight: ""
    property bool error: false
    property color gapColor: Theme.surface

    readonly property int hpad: size === "lg" ? Theme.space5 : size === "sm" ? Theme.space3 : Theme.space4
    readonly property int minWidth: size === "lg" ? 112 : size === "sm" ? 0 : 64
    readonly property color fg: !enabled ? Theme.inkDisabled : variant === "primary" ? Theme.inkOnAccent : variant === "destructive" ? Theme.inkOnError : Theme.ink

    implicitHeight: size === "lg" ? Theme.controlLg : size === "sm" ? Theme.controlSm : Theme.controlMd
    implicitWidth: Math.max(minWidth, row.implicitWidth + 2 * hpad)
    leftPadding: hpad
    rightPadding: hpad
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.role: Accessible.Button
    Accessible.name: text

    Keys.onReturnPressed: event => {
        if (control.enabled)
            control.clicked();
        event.accepted = true;
    }
    Keys.onEnterPressed: event => {
        if (control.enabled)
            control.clicked();
        event.accepted = true;
    }

    background: Rectangle {
        radius: Theme.radiusMd
        antialiasing: true
        border.width: 1
        color: {
            if (!control.enabled)
                return control.variant === "ghost" ? "transparent" : Theme.surfaceSunken;
            switch (control.variant) {
            case "primary":
                return control.down ? Theme.accentPressed : control.hovered ? Theme.accentHover : Theme.accent;
            case "destructive":
                return (control.down || control.hovered) ? Theme.errorHover : Theme.error;
            case "ghost":
                return control.down ? Theme.line : control.hovered ? Theme.surfaceSunken : "transparent";
            default:
                return control.down ? Theme.line : control.hovered ? Theme.surfaceSunken : Theme.surfaceRaised;
            }
        }
        border.color: {
            if (control.error)
                return Theme.error;
            if (!control.enabled)
                return "transparent";
            if (control.variant === "primary")
                return Theme.accentEdge;
            if (control.variant === "secondary")
                return Theme.lineStrong;
            return "transparent";
        }
        Behavior on color {
            ColorAnimation { duration: Theme.durationFast }
        }
        FocusRing {
            show: control.visualFocus
            radius: Theme.radiusMd
            gapColor: control.gapColor
        }
    }

    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        Row {
            id: row
            anchors.centerIn: parent
            spacing: Theme.space2
            Icon {
                visible: control.iconName !== ""
                name: control.iconName || "help"
                size: control.size === "sm" ? 16 : 18
                color: control.fg
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: control.text
                color: control.fg
                font.family: Theme.fontSans
                font.pixelSize: control.size === "sm" ? 13 : 15
                font.weight: Font.DemiBold
                anchors.verticalCenter: parent.verticalCenter
                Accessible.ignored: true
            }
            Icon {
                visible: control.iconRight !== ""
                name: control.iconRight || "help"
                size: 18
                color: control.fg
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
