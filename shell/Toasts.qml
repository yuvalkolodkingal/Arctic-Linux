pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland

// Notification toasts: a stack in the top-right corner of the focused screen, under the bar,
// newest on top, at most three plus a "2 more" row that opens the centre. On the Overlay layer
// on purpose (calls and alarms show over full-screen windows; do not disturb keeps a game or a
// talk quiet), without keyboard focus, and hidden while the screen is locked (the lock screen
// counts them instead). Timing and what pops up at all: NotificationService.
PanelWindow {
    id: toasts
    required property var shell
    readonly property int count: NotificationService.toastModel.count
    screen: Outputs.focused
    visible: !NotificationService.locked && count > 0
    anchors { top: true; right: true }
    margins.top: Theme.topInset + Theme.frameWidth + Theme.space2
    margins.right: Theme.frameWidth + Theme.space2
    implicitWidth: 340
    implicitHeight: Math.max(1, stack.implicitHeight)
    color: 'transparent'
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: 'arctic-toasts'
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    ColumnLayout {
        id: stack
        width: parent.width
        spacing: Theme.space2
        Repeater {
            model: NotificationService.toastModel
            ToastCard {
                required property int index
                Layout.preferredWidth: 340
                Layout.preferredHeight: implicitHeight
                visible: index < NotificationService.maxToasts
            }
        }
        // More waiting than fit: one row that opens the centre.
        Rectangle {
            id: more
            visible: toasts.count > NotificationService.maxToasts
            Layout.preferredWidth: 340
            implicitHeight: 32
            radius: Theme.radiusLg
            color: moreMouse.containsMouse ? Theme.surfaceSunken : Theme.surfaceRaised
            border.width: 1
            border.color: Theme.line
            Text {
                anchors.centerIn: parent
                text: (toasts.count - NotificationService.maxToasts) + ' more · open the notification centre'
                color: Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: 13
                font.weight: Font.Medium
                font.features: { 'tnum': 1 }
            }
            MouseArea {
                id: moreMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: toasts.shell.openNotifications(toasts.screen)
            }
        }
    }
}
