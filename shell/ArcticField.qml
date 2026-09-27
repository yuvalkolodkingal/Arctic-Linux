import QtQuick
import QtQuick.Controls.Basic

// Design Input: surface-raised, 1px line-strong, focus = focus border + 1px outer line,
// error = error border. `size: 'lg'` is the 44px login/lock field.
TextField {
    id: field
    property string size: 'md'
    property string iconName: ''
    property bool error: false
    property bool success: false
    property bool focusLook: false      // draw the focus ring even without window activation (lock screen)
    implicitHeight: size === 'lg' ? Theme.controlLg : Theme.controlMd
    leftPadding: iconName ? Theme.space3 + 18 + Theme.space2 : Theme.space3
    rightPadding: Theme.space3
    color: Theme.ink
    placeholderTextColor: Theme.inkSubtle
    selectionColor: Theme.selection
    selectedTextColor: Theme.ink
    font.family: Theme.fontSans
    font.pixelSize: size === 'lg' ? 16 : 15
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    readonly property color edge: error ? Theme.error : success ? Theme.success
                                  : activeFocus || focusLook ? Theme.focus : hovered ? Theme.inkMuted : Theme.lineStrong
    background: Rectangle {
        radius: Theme.radiusMd
        color: field.enabled ? Theme.surfaceRaised : Theme.surfaceSunken
        border.width: field.activeFocus || field.focusLook || field.error || field.success ? 2 : 1
        border.color: field.enabled ? field.edge : Theme.line
        Behavior on border.color { ColorAnimation { duration: Theme.durationFast } }
        Icon {
            visible: field.iconName !== ''
            anchors.left: parent.left
            anchors.leftMargin: Theme.space3
            anchors.verticalCenter: parent.verticalCenter
            name: field.iconName
            size: 18
            color: Theme.inkMuted
        }
    }
}
