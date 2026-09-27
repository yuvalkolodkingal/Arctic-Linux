// .ar-card — icon or radio lead, title (+ tag), description, extra content.
// `choice` cards are focusable buttons; selected = 2px amber edge on amber-soft.
import QtQuick
import QtQuick.Templates as T
import ".."

T.AbstractButton {
    id: card
    property string title: ""
    property string desc: ""
    property string iconName: ""
    property color iconColor: Theme.inkMuted
    property bool radio: false
    property bool choice: false
    property bool selected: false
    property bool error: false
    property string tag: ""
    property string tagKind: ""
    default property alias extra: extraSlot.data

    readonly property int pad: Theme.space4
    implicitHeight: Math.max(body.implicitHeight, 22) + 2 * pad + 2
    hoverEnabled: choice && enabled
    focusPolicy: choice ? Qt.StrongFocus : Qt.NoFocus
    checkable: false
    Accessible.role: radio ? Accessible.RadioButton : (choice ? Accessible.Button : Accessible.Grouping)
    Accessible.name: title
    Accessible.description: desc
    Accessible.checkable: radio
    Accessible.checked: selected

    Keys.onReturnPressed: event => {
        // Enter on a choice card picks it and then behaves like Next.
        if (card.choice && !card.selected) {
            card.clicked();
            event.accepted = true;
        } else {
            event.accepted = false;
        }
    }

    background: ShadowRect {
        radius: Theme.radiusLg
        elevation: card.selected || !card.enabled ? 0 : 1
        color: !card.enabled ? Theme.surfaceSunken : card.selected ? Theme.accentSoft : card.pressed ? Theme.surfaceSunken : Theme.surfaceRaised
        border.width: card.selected ? 2 : 1
        border.color: card.error ? Theme.error : card.selected ? Theme.accentEdge : card.hovered ? Theme.lineStrong : Theme.line
        FocusRing {
            show: card.visualFocus
            radius: Theme.radiusLg
        }
    }

    contentItem: Item {
        implicitHeight: body.implicitHeight
        Row {
            id: body
            x: card.pad + 1
            y: card.pad + 1
            width: card.width - 2 * card.pad - 2
            spacing: Theme.space3

            ArCheckIndicator {
                visible: card.radio
                radio: true
                checked: card.selected
                hovered: card.hovered
                disabled: !card.enabled
                y: 2
            }
            Icon {
                visible: !card.radio && card.iconName !== ""
                name: card.iconName || "help"
                size: 22
                color: card.enabled ? card.iconColor : Theme.inkDisabled
                y: 1
            }
            Column {
                width: body.width - (card.radio ? 20 + body.spacing : card.iconName !== "" ? 22 + body.spacing : 0)
                spacing: 2
                Flow {
                    width: parent.width
                    spacing: Theme.space2
                    ArText {
                        text: card.title
                        size: 16
                        lh: 24
                        weight: Font.DemiBold
                        color: card.enabled ? Theme.ink : Theme.inkDisabled
                    }
                    Item {
                        visible: card.tag !== ""
                        width: tagItem.width
                        height: 24
                        ArTag {
                            id: tagItem
                            anchors.verticalCenter: parent.verticalCenter
                            text: card.tag
                            kind: card.tagKind
                        }
                    }
                }
                ArText {
                    visible: card.desc !== ""
                    width: parent.width
                    text: card.desc
                    size: 14
                    lh: 20
                    wrapMode: Text.WordWrap
                    color: card.enabled ? Theme.inkMuted : Theme.inkDisabled
                }
                Column {
                    id: extraSlot
                    width: parent.width
                }
            }
        }
    }
}
