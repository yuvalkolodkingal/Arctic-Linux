import QtQuick

// One toast (design Toast): a 340px surface-raised card with a 1px line, radius-lg and 12px
// padding around the notification (NotificationCard.qml). Urgent ones carry a 3px error edge
// on the left as well as the word. Hovering pauses its timer and shows the close button; a
// click runs the default action (or brings the app's window forward); the close button only
// hides the toast, the notification stays in the centre.
Rectangle {
    id: toast
    required property int nid
    readonly property var entry: { NotificationService.entries; return NotificationService.find(nid); }
    readonly property bool urgent: entry !== null && entry.urgency === 'critical'

    width: 340
    implicitHeight: content.implicitHeight + 2 * Theme.space3
    radius: Theme.radiusLg
    color: Theme.surfaceRaised
    border.width: 1
    border.color: Theme.line
    clip: true
    opacity: 0
    Component.onCompleted: opacity = 1
    Behavior on opacity { NumberAnimation { duration: Theme.fadeBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeEnter } }
    Accessible.role: Accessible.AlertMessage
    Accessible.name: entry ? NotificationService.appNameFor(entry) + ': ' + entry.summary + (entry.body ? '. ' + entry.body : '') : ''

    Rectangle {
        visible: toast.urgent
        anchors { left: parent.left; top: parent.top; bottom: parent.bottom }
        width: 3
        color: Theme.error
    }

    HoverHandler {
        id: hover
        onHoveredChanged: NotificationService.hoverToast(toast.nid, hovered)
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: NotificationService.activate(toast.nid)
    }

    NotificationCard {
        id: content
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.space3 }
        entry: toast.entry
        showTime: !hover.hovered
        onActionInvoked: identifier => NotificationService.invokeAction(toast.nid, identifier)
    }

    ArcticButton {
        anchors { right: parent.right; top: parent.top; margins: Theme.space2 }
        visible: hover.hovered
        variant: 'ghost'
        size: 'sm'
        iconOnly: true
        iconName: 'x'
        label: 'Close'
        tooltip: ''
        focusPolicy: Qt.NoFocus
        onClicked: NotificationService.dismissToast(toast.nid)
    }
}
