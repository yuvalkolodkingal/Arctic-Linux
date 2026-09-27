// Input (lg) from the design system: 44 px, radius-md, surface-raised fill,
// 1 px line-strong border. Hover: ink-muted border. Focus: amber border plus a
// 1 px amber ring. Error: the same in `error`. Leading icon, amber caret.
pragma ComponentBehavior: Bound

import QtQuick
import ".."

Item {
    id: field

    property alias text: textInput.text
    property alias input: textInput
    property string placeholder
    property string icon
    property bool password: false
    property bool error: false
    // Wayland greeters get no Caps Lock state from SDDM, so the field infers
    // it from the case of typed letters (and the Caps Lock key itself).
    property bool capsLock: false

    signal accepted()
    signal tabbed(bool backwards)

    implicitHeight: Theme.controlLg
    implicitWidth: 240

    readonly property color edge: error ? Theme.error
                                        : textInput.activeFocus ? Theme.focus
                                        : hover.hovered ? Theme.inkMuted : Theme.lineStrong
    readonly property bool ring: error || textInput.activeFocus

    // the extra 1 px ring outside the border (box-shadow: 0 0 0 1px)
    Rectangle {
        anchors.fill: parent
        anchors.margins: -1
        radius: Theme.radiusMd + 1
        color: "transparent"
        border.width: 1
        border.color: field.edge
        visible: field.ring
        antialiasing: true
    }
    Rectangle {
        id: box
        anchors.fill: parent
        radius: Theme.radiusMd
        color: field.enabled ? Theme.surfaceRaised : Theme.surfaceSunken
        border.width: 1
        border.color: field.edge
        antialiasing: true
        Behavior on border.color { ColorAnimation { duration: Theme.durationFast } }
    }

    HoverHandler { id: hover; cursorShape: Qt.IBeamCursor }
    TapHandler { onTapped: textInput.forceActiveFocus() }

    Icon {
        id: lead
        visible: field.icon !== ""
        name: field.icon
        size: 18
        color: field.error ? Theme.error : Theme.inkMuted
        anchors.left: parent.left
        anchors.leftMargin: Theme.space3
        anchors.verticalCenter: parent.verticalCenter
    }

    TextInput {
        id: textInput
        anchors.left: lead.visible ? lead.right : parent.left
        anchors.leftMargin: lead.visible ? Theme.space2 : Theme.space3
        anchors.right: parent.right
        anchors.rightMargin: Theme.space3
        anchors.verticalCenter: parent.verticalCenter
        clip: true
        color: Theme.ink
        selectionColor: Theme.selection
        selectedTextColor: Theme.ink
        selectByMouse: true
        echoMode: field.password ? TextInput.Password : TextInput.Normal
        passwordCharacter: "•"
        passwordMaskDelay: 0
        font.family: Theme.fontSans
        font.pixelSize: field.password && text.length > 0 ? 18 : 16
        font.letterSpacing: field.password && text.length > 0 ? 2.7 : 0
        verticalAlignment: TextInput.AlignVCenter
        onAccepted: field.accepted()

        Keys.onPressed: (event) => {
            if (event.key === Qt.Key_Tab || event.key === Qt.Key_Backtab) {
                field.tabbed(event.key === Qt.Key_Backtab || (event.modifiers & Qt.ShiftModifier))
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_Escape) {
                textInput.text = ""
                event.accepted = true
                return
            }
            if (event.key === Qt.Key_CapsLock) {
                field.capsLock = !field.capsLock
            } else if (event.text.length === 1 && event.text.toUpperCase() !== event.text.toLowerCase()) {
                var shift = (event.modifiers & Qt.ShiftModifier) !== 0
                field.capsLock = (event.text === event.text.toUpperCase()) !== shift
            }
            event.accepted = false
        }

        cursorDelegate: Rectangle {
            width: 1.5
            height: 18
            color: Theme.accentEdge
            visible: textInput.activeFocus
            SequentialAnimation on opacity {
                running: textInput.activeFocus && !Theme.reduceMotion
                loops: Animation.Infinite
                NumberAnimation { to: 1; duration: 0 }
                PauseAnimation { duration: 530 }
                NumberAnimation { to: 0; duration: 0 }
                PauseAnimation { duration: 530 }
            }
        }

        Text {
            anchors.fill: parent
            verticalAlignment: Text.AlignVCenter
            visible: textInput.text.length === 0 && !textInput.inputMethodComposing
            text: field.placeholder
            color: Theme.inkSubtle
            font.family: Theme.fontSans
            font.pixelSize: 16
            elide: Text.ElideRight
        }
    }
}
