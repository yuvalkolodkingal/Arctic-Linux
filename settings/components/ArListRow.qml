// .ar-list-row — leading icon or app tile, title + description, meta, trailing
// slot (children go there). States: hover, selected (amber-soft + 3px edge),
// keyboard focus (inset ring), pressed, disabled, error.
import QtQuick
import QtQuick.Templates as T
import ".."

T.AbstractButton {
    id: row
    property string title: ""
    property string desc: ""
    property string iconName: ""
    property string tile: ""
    property string meta: ""
    property string metaIcon: ""
    property bool selected: false
    property bool showFocus: false
    property bool error: false
    property bool first: false
    property bool check: false          // amber check at the end (selected language, layout …)
    default property alias trailing: trailSlot.data

    // border-top: 1px on every row but the first, on top of the 48px minimum
    topPadding: first ? 0 : 1
    implicitHeight: Math.max(48, content.implicitHeight + 2 * Theme.space3) + topPadding
    hoverEnabled: enabled
    focusPolicy: Qt.NoFocus
    Accessible.role: Accessible.ListItem
    Accessible.name: title
    Accessible.description: desc
    Accessible.selected: selected
    Accessible.selectable: true

    background: Rectangle {
        color: row.selected ? Theme.accentSoft : !row.enabled ? "transparent" : row.pressed ? Theme.line : row.hovered ? Theme.surfaceSunken : "transparent"
        Behavior on color {
            ColorAnimation { duration: Theme.durationFast }
        }
        // top divider (not on the first row)
        Rectangle {
            visible: !row.first
            width: parent.width
            height: 1
            color: Theme.line
        }
        // selected: 3px amber edge on the left
        Rectangle {
            visible: row.selected
            x: 0
            y: 8
            width: 3
            height: parent.height - 16
            topRightRadius: 3
            bottomRightRadius: 3
            color: Theme.accentEdge
        }
        FocusRing {
            inset: true
            show: row.showFocus
            radius: 0
        }
    }

    contentItem: Item {
        implicitHeight: content.implicitHeight
        Row {
            id: content
            x: Theme.space4
            width: parent.width - 2 * Theme.space4
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.space3

            AppTile {
                id: tileItem
                visible: row.tile !== ""
                tile: row.tile || "zen"
                size: 36
                anchors.verticalCenter: parent.verticalCenter
            }
            Icon {
                id: lead
                visible: row.tile === "" && row.iconName !== ""
                name: row.iconName || "help"
                size: 20
                color: row.enabled ? Theme.inkMuted : Theme.inkDisabled
                anchors.verticalCenter: parent.verticalCenter
            }
            Column {
                id: main
                width: content.width - x - metaRow.width - trailSlot.width - checkIcon.width - (content.spacing * ((metaRow.visible ? 1 : 0) + (trailSlot.width > 0 ? 1 : 0) + (checkIcon.visible ? 1 : 0)))
                anchors.verticalCenter: parent.verticalCenter
                ArText {
                    width: parent.width
                    text: row.title
                    size: 15
                    lh: 22
                    weight: Font.Medium
                    elide: Text.ElideRight
                    color: row.enabled ? Theme.ink : Theme.inkDisabled
                }
                ArText {
                    visible: row.desc !== ""
                    width: parent.width
                    text: row.desc
                    size: 13
                    lh: 18
                    wrapMode: Text.WordWrap
                    color: !row.enabled ? Theme.inkDisabled : row.error ? Theme.error : Theme.inkMuted
                }
            }
            Row {
                id: metaRow
                visible: row.meta !== "" || row.metaIcon !== ""
                width: visible ? implicitWidth : 0
                spacing: Theme.space2
                anchors.verticalCenter: parent.verticalCenter
                ArText {
                    visible: row.meta !== ""
                    text: row.meta
                    size: 13
                    lh: 18
                    color: row.enabled ? Theme.inkSubtle : Theme.inkDisabled
                    anchors.verticalCenter: parent.verticalCenter
                }
                Icon {
                    visible: row.metaIcon !== ""
                    name: row.metaIcon || "help"
                    size: 16
                    color: row.enabled ? Theme.inkSubtle : Theme.inkDisabled
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
            Row {
                id: trailSlot
                spacing: Theme.space2
                anchors.verticalCenter: parent.verticalCenter
            }
            Icon {
                id: checkIcon
                visible: row.check
                width: visible ? 18 : 0
                name: "check"
                size: 18
                color: Theme.accentText
                anchors.verticalCenter: parent.verticalCenter
            }
        }
    }
}
