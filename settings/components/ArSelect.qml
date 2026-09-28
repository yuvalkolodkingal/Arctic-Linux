// Dropdown: Input-looking box with a chevron (.ar-select) and a menu popup
// (.ar-menu). model = [{value, label}]. Space/Enter/Alt+Down opens, arrows move,
// Enter picks, Esc closes; typing a letter jumps to the first match.
// (Settings: ported from installer-ui/components with one change — when the model is replaced,
// ComboBox jumps to its first item; the selection is re-bound to `value`, so an empty value
// keeps showing the placeholder.)
pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Templates as T
import ".."

Column {
    id: field
    property string label: ""
    property string iconName: ""
    property string help: ""
    property string error: ""
    property var model: []
    property string value: ""
    property string placeholder: "Choose…"
    property alias combo: combo
    readonly property int currentIndex: indexOf(value)
    signal activated(string value)

    spacing: Theme.space1
    width: 280

    function indexOf(v) {
        for (let i = 0; i < model.length; i++)
            if (model[i].value === v)
                return i;
        return -1;
    }

    ArText {
        visible: field.label !== ""
        text: field.label
        size: 13
        lh: 18
        weight: Font.Medium
    }

    T.ComboBox {
        id: combo
        width: parent.width
        height: Theme.controlMd
        model: field.model
        textRole: "label"
        valueRole: "value"
        currentIndex: field.currentIndex
        hoverEnabled: true
        focusPolicy: Qt.StrongFocus
        Accessible.role: Accessible.ComboBox
        Accessible.name: field.label
        Accessible.description: displayText
        onActivated: index => {
            if (index >= 0 && index < field.model.length)
                field.activated(field.model[index].value);
        }
        onCountChanged: Qt.callLater(() => combo.currentIndex = Qt.binding(() => field.currentIndex))
        // Enter on a closed dropdown opens it (Space too, via the template).
        Keys.onReturnPressed: event => {
            if (!popup.visible) {
                popup.open();
                event.accepted = true;
            } else {
                event.accepted = false;
            }
        }
        // Up/Down on a closed dropdown open it instead of silently changing the value.
        Keys.onUpPressed: event => {
            if (popup.visible) {
                event.accepted = false;
                return;
            }
            popup.open();
            event.accepted = true;
        }
        Keys.onDownPressed: event => {
            if (popup.visible) {
                event.accepted = false;
                return;
            }
            popup.open();
            event.accepted = true;
        }

        background: Rectangle {
            radius: Theme.radiusMd
            antialiasing: true
            color: combo.enabled ? Theme.surfaceRaised : Theme.surfaceSunken
            readonly property bool focused: combo.activeFocus || combo.popup.visible
            border.width: (focused || field.error !== "") ? 2 : 1
            border.color: !combo.enabled ? Theme.line : field.error !== "" ? Theme.error : focused ? Theme.focus : combo.hovered ? Theme.inkMuted : Theme.lineStrong
        }
        contentItem: Item {
            Icon {
                id: lead
                visible: field.iconName !== ""
                x: Theme.space3
                anchors.verticalCenter: parent.verticalCenter
                name: field.iconName || "help"
                size: 18
                color: Theme.inkMuted
            }
            ArText {
                anchors.left: lead.visible ? lead.right : parent.left
                anchors.leftMargin: lead.visible ? Theme.space2 : Theme.space3
                anchors.right: chev.left
                anchors.rightMargin: Theme.space2
                anchors.verticalCenter: parent.verticalCenter
                text: combo.currentIndex >= 0 ? combo.displayText : field.placeholder
                color: combo.currentIndex >= 0 ? (combo.enabled ? Theme.ink : Theme.inkDisabled) : Theme.inkSubtle
                elide: Text.ElideRight
                size: 15
                lh: 20
            }
            Icon {
                id: chev
                anchors.right: parent.right
                anchors.rightMargin: Theme.space3
                anchors.verticalCenter: parent.verticalCenter
                name: combo.popup.visible ? "chevron-up" : "chevron-down"
                size: 18
                color: Theme.inkMuted
            }
        }
        indicator: null

        delegate: T.ItemDelegate {
            id: item
            required property int index
            required property var modelData
            width: ListView.view ? ListView.view.width : 200
            height: 34
            hoverEnabled: true
            highlighted: combo.highlightedIndex === index
            readonly property bool selected: combo.currentIndex === index
            Accessible.role: Accessible.ListItem
            Accessible.name: modelData.label
            Accessible.selected: selected
            background: Rectangle {
                radius: Theme.radiusSm
                color: item.selected ? Theme.accentSoft : (item.highlighted || item.hovered) ? Theme.surfaceSunken : "transparent"
                border.width: item.highlighted && menu.keyboardNav ? 2 : 0
                border.color: Theme.focus
            }
            contentItem: Item {
                ArText {
                    x: Theme.space3
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 2 * Theme.space3 - 16
                    text: item.modelData.label
                    elide: Text.ElideRight
                    size: 15
                    lh: 20
                    weight: item.selected ? Font.DemiBold : Font.Normal
                }
                Icon {
                    visible: item.selected
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.space3
                    anchors.verticalCenter: parent.verticalCenter
                    name: "check"
                    size: 16
                    color: Theme.accentText
                }
            }
        }

        popup: T.Popup {
            id: menu
            property bool keyboardNav: true
            y: combo.height + Theme.space1
            width: combo.width
            implicitHeight: Math.min(contentItem.implicitHeight + 2 * padding, 300)
            padding: Theme.space1
            closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutsideParent
            onOpened: {
                keyboardNav = true;
                list.positionViewAtIndex(Math.max(0, combo.currentIndex), ListView.Center);
            }
            background: ShadowRect {
                radius: Theme.radiusLg
                elevation: 2
                color: Theme.surfaceRaised
                border.width: 1
                border.color: Theme.line
            }
            contentItem: ListView {
                id: list
                clip: true
                implicitHeight: contentHeight
                model: combo.delegateModel
                currentIndex: combo.highlightedIndex
                highlightMoveDuration: 0
                boundsBehavior: Flickable.StopAtBounds
                HoverHandler {
                    onHoveredChanged: if (hovered) menu.keyboardNav = false
                }
            }
        }
    }

    Row {
        visible: field.error !== "" || field.help !== ""
        width: parent.width
        spacing: Theme.space1
        Icon {
            visible: field.error !== ""
            name: "alert"
            size: 16
            color: Theme.error
            y: 1
        }
        ArText {
            width: parent.width - (field.error !== "" ? 20 : 0)
            text: field.error !== "" ? field.error : field.help
            size: 13
            lh: 18
            wrapMode: Text.WordWrap
            color: field.error !== "" ? Theme.error : Theme.inkMuted
        }
    }
}
