// A foldable group in the app checklist (catalog categories with collapsed = true,
// the "More apps"): a full-width row with a chevron, the group name, its rule and
// how many apps are ticked in it and, while folded, the apps inside. The whole row
// is the control: a click, Space or Enter opens or closes the group.
import QtQuick
import QtQuick.Templates as T
import ".."

T.AbstractButton {
    id: head
    property string name: ""
    property string rule: "Pick any"
    property int picked: 0
    property int count: 0
    property string preview: ""        // the apps inside, shown while folded
    property bool expanded: false
    property bool error: false

    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    checkable: false
    implicitHeight: expanded ? 44 : 60
    Accessible.role: Accessible.Button
    Accessible.name: name
    Accessible.description: rule + (picked ? ", " + picked + " picked" : "") + ", " + count + (count === 1 ? " app" : " apps") + (expanded ? ", open" : ", folded")

    // As on ArButton: Enter activates, and a held key (auto-repeat) doesn't.
    Keys.onReturnPressed: event => {
        if (!event.isAutoRepeat)
            head.clicked();
        event.accepted = true;
    }
    Keys.onEnterPressed: event => {
        if (!event.isAutoRepeat)
            head.clicked();
        event.accepted = true;
    }

    background: Rectangle {
        radius: Theme.radiusMd
        antialiasing: true
        color: head.pressed ? Theme.surfaceSunken : head.hovered ? Theme.surfaceRaised : head.expanded ? "transparent" : Theme.surfaceRaised
        border.width: 1
        border.color: head.error ? Theme.error : head.hovered ? Theme.lineStrong : Theme.line
        Behavior on color {
            ColorAnimation { duration: Theme.durationFast }
        }
        FocusRing {
            show: head.visualFocus
            radius: Theme.radiusMd
        }
    }

    contentItem: Item {
        Icon {
            id: chevron
            x: Theme.space3
            y: head.expanded ? (parent.height - height) / 2 : Theme.space3 + 1
            name: head.expanded ? "chevron-down" : "chevron-right"
            size: 18
            color: Theme.inkMuted
        }
        Row {
            id: titleRow
            x: chevron.x + chevron.width + Theme.space2
            y: head.expanded ? (parent.height - height) / 2 : Theme.space3
            width: parent.width - x - countLabel.width - 2 * Theme.space3
            spacing: Theme.space2
            ArText {
                id: nameLabel
                text: head.name.toUpperCase()
                size: 13
                lh: 18
                weight: Font.DemiBold
                tracking: 0.06
                color: head.enabled ? Theme.ink : Theme.inkDisabled
            }
            ArText {
                width: Math.max(0, titleRow.width - nameLabel.width - titleRow.spacing)
                text: head.rule + (head.picked ? " · " + head.picked + " picked" : "")
                size: 12
                lh: 18
                elide: Text.ElideRight
                color: head.picked ? Theme.accentText : Theme.inkSubtle
            }
        }
        ArText {
            visible: !head.expanded
            x: titleRow.x
            y: titleRow.y + titleRow.height + 2
            width: parent.width - x - Theme.space3
            text: head.preview
            size: 12
            lh: 16
            elide: Text.ElideRight
            color: Theme.inkMuted
        }
        ArText {
            id: countLabel
            x: parent.width - width - Theme.space3
            y: titleRow.y
            text: head.count + (head.count === 1 ? " app" : " apps")
            size: 12
            lh: 18
            color: Theme.inkSubtle
        }
    }
}
