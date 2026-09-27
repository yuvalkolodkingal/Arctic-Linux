// .ar-app — one app in the checklist: check (or radio), tile, name, Default tag
// (and Proprietary for non-free apps), one-line summary. The whole row is the
// control; Space toggles. Long names elide so the tags always fit.
import QtQuick
import QtQuick.Templates as T
import ".."

T.AbstractButton {
    id: app
    property string appId: ""
    property string tile: appId
    property string name: ""
    property string summary: ""
    property bool isDefault: false
    property bool proprietary: false
    property bool radio: false
    property bool error: false
    property string sizeLabel: ""

    checkable: false          // `checked` is bound by the page; a click only emits clicked()
    hoverEnabled: true
    focusPolicy: Qt.StrongFocus
    implicitHeight: 56
    Accessible.role: radio ? Accessible.RadioButton : Accessible.CheckBox
    Accessible.name: name + (isDefault ? " (default)" : "") + (proprietary ? " (proprietary)" : "")
    Accessible.description: summary
    Accessible.checkable: true
    Accessible.checked: checked

    background: Rectangle {
        radius: Theme.radiusMd
        antialiasing: true
        color: !app.enabled ? Theme.surfaceSunken : app.checked ? Theme.accentSoft : Theme.surfaceRaised
        border.width: 1
        border.color: app.error ? Theme.error : app.checked ? Theme.accentEdge : app.hovered ? Theme.lineStrong : Theme.line
        Behavior on color {
            ColorAnimation { duration: Theme.durationFast }
        }
        FocusRing {
            show: app.visualFocus
            radius: Theme.radiusMd
        }
    }

    contentItem: Item {
        Row {
            x: Theme.space3
            width: parent.width - 2 * Theme.space3
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.space3
            ArCheckIndicator {
                radio: app.radio
                checked: app.checked
                hovered: app.hovered
                pressed: app.pressed
                disabled: !app.enabled
                anchors.verticalCenter: parent.verticalCenter
            }
            AppTile {
                tile: app.tile
                size: 36
                anchors.verticalCenter: parent.verticalCenter
            }
            Column {
                width: parent.width - 20 - 36 - 2 * parent.spacing
                anchors.verticalCenter: parent.verticalCenter
                Row {
                    id: nameRow
                    width: parent.width
                    spacing: Theme.space2
                    readonly property real tagsWidth: (defaultTag.visible ? defaultTag.width + spacing : 0) + (propTag.visible ? propTag.width + spacing : 0)
                    ArText {
                        width: Math.min(implicitWidth, nameRow.width - nameRow.tagsWidth)
                        text: app.name
                        size: 15
                        lh: 20
                        weight: Font.DemiBold
                        elide: Text.ElideRight
                        color: app.enabled ? Theme.ink : Theme.inkDisabled
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArTag {
                        id: defaultTag
                        visible: app.isDefault
                        text: "Default"
                        textSize: 10
                        hpad: 6
                        implicitHeight: 16
                        anchors.verticalCenter: parent.verticalCenter
                    }
                    ArTag {
                        id: propTag
                        visible: app.proprietary
                        text: "Proprietary"
                        kind: "info"
                        textSize: 10
                        hpad: 6
                        implicitHeight: 16
                        anchors.verticalCenter: parent.verticalCenter
                    }
                }
                ArText {
                    width: parent.width
                    text: app.summary
                    size: 12
                    lh: 16
                    elide: Text.ElideRight
                    color: app.enabled ? Theme.inkMuted : Theme.inkDisabled
                }
            }
        }
    }
}
