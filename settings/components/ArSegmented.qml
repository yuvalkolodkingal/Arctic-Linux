// A row of mutually exclusive choices (Slower / Arctic / Faster, Dark / Light …): pills on a
// surface-sunken track; the chosen one is surface-raised with the amber edge (the selection).
// ←/→ move the choice, Tab leaves. model = [{value, label}]. Settings-only.
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."

FocusScope {
    id: seg
    property var model: []
    property string value: ""
    property string accessibleName: ""
    signal activated(string value)
    readonly property int currentIndex: {
        for (let i = 0; i < model.length; i++)
            if (model[i].value === value)
                return i;
        return -1;
    }

    implicitWidth: row.implicitWidth + 8
    implicitHeight: Theme.controlMd
    activeFocusOnTab: true
    Accessible.role: Accessible.RadioButton
    Accessible.name: accessibleName

    function pick(i) {
        if (i < 0 || i >= model.length || !enabled)
            return;
        if (model[i].value !== value)
            activated(model[i].value);
    }
    Keys.onLeftPressed: pick(Math.max(0, currentIndex - 1))
    Keys.onRightPressed: pick(Math.min(model.length - 1, currentIndex + 1))

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusMd
        color: Theme.surfaceSunken
        border.width: 1
        border.color: Theme.line
        FocusRing {
            show: seg.activeFocus
            radius: Theme.radiusMd
        }
    }
    Row {
        id: row
        x: 4
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2
        Repeater {
            model: seg.model
            T.AbstractButton {
                id: pill
                required property var modelData
                required property int index
                readonly property bool chosen: seg.currentIndex === index
                implicitWidth: Math.max(56, label.implicitWidth + 2 * Theme.space3)
                implicitHeight: Theme.controlMd - 8
                focusPolicy: Qt.NoFocus
                hoverEnabled: true
                enabled: seg.enabled
                Accessible.role: Accessible.RadioButton
                Accessible.name: modelData.label
                Accessible.checked: chosen
                onClicked: seg.pick(index)
                background: Rectangle {
                    radius: Theme.radiusSm
                    color: pill.chosen ? Theme.surfaceRaised : pill.hovered ? Theme.surface : "transparent"
                    border.width: pill.chosen ? 1 : 0
                    border.color: seg.enabled ? Theme.accentEdge : Theme.line
                    Behavior on color {
                        ColorAnimation { duration: Theme.durationFast }
                    }
                }
                contentItem: ArText {
                    id: label
                    text: pill.modelData.label
                    size: 13
                    lh: 18
                    weight: pill.chosen ? Font.DemiBold : Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    color: !seg.enabled ? Theme.inkDisabled : pill.chosen ? Theme.ink : Theme.inkMuted
                }
            }
        }
    }
}
