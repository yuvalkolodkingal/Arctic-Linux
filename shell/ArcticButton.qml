import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Design Button: primary (the one amber action), secondary, ghost, destructive;
// sizes sm 28 / md 36 / lg 44; optional leading icon; icon-only buttons need `label`
// for their tooltip and accessible name.
AbstractButton {
    id: control
    property string variant: 'secondary'
    property string size: 'md'
    property string iconName: ''
    property bool iconOnly: false
    property string label: text
    property string tooltip: iconOnly ? label : ''

    readonly property bool primary: variant === 'primary'
    readonly property int controlHeight: size === 'sm' ? Theme.controlSm : size === 'lg' ? Theme.controlLg : Theme.controlMd
    readonly property color fill: {
        if (!enabled) return variant === 'ghost' ? 'transparent' : Theme.surfaceSunken;
        if (primary) return down ? Theme.accentPressed : hovered ? Theme.accentHover : Theme.accent;
        if (variant === 'destructive') return Theme.error;
        if (variant === 'ghost') return down ? Theme.line : hovered ? Theme.surfaceSunken : 'transparent';
        return down ? Theme.line : hovered ? Theme.surfaceSunken : Theme.surfaceRaised;
    }
    readonly property color ink: !enabled ? Theme.inkDisabled : primary ? Theme.onAccent
                                 : variant === 'destructive' ? Theme.onError : Theme.ink

    implicitHeight: controlHeight
    implicitWidth: iconOnly ? controlHeight
                            : Math.max(size === 'lg' ? 112 : size === 'sm' ? 0 : 64, row.implicitWidth + 2 * (size === 'lg' ? Theme.space5 : size === 'sm' ? Theme.space3 : Theme.space4))
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    Accessible.name: label
    Keys.onReturnPressed: clicked()
    Keys.onEnterPressed: clicked()

    background: Rectangle {
        radius: Theme.radiusMd
        color: control.fill
        border.width: control.enabled && (control.primary || control.variant === 'secondary') ? 1 : 0
        border.color: control.primary ? (Theme.dark ? Theme.accent : Theme.accentEdge) : Theme.lineStrong
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
        FocusRing { targetRadius: Theme.radiusMd; shown: control.visualFocus }
    }
    contentItem: Item {
        implicitWidth: row.implicitWidth
        implicitHeight: row.implicitHeight
        RowLayout {
            id: row
            anchors.centerIn: parent
            spacing: Theme.space2
            Icon {
                visible: control.iconName !== ''
                name: control.iconName
                size: control.size === 'sm' ? 16 : 18
                color: control.ink
            }
            Text {
                visible: !control.iconOnly
                text: control.text
                textFormat: Text.PlainText
                color: control.ink
                font.family: Theme.fontSans
                font.pixelSize: control.size === 'sm' ? 13 : 15
                font.weight: Font.DemiBold
            }
        }
    }
    Tip {
        visible: control.tooltip !== '' && control.hovered
        text: control.tooltip
    }
}
