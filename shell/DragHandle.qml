import QtQuick

// The small grip at the top of a popover card. Drag it and the card follows, then docks to
// the nearest screen edge when released (DockPosition).
MouseArea {
    id: handle
    property real windowX: 0
    property real windowY: 0
    property point pressPoint
    property point startPosition
    signal moved(real nextX, real nextY)
    implicitHeight: 14
    hoverEnabled: true
    cursorShape: pressed ? Qt.ClosedHandCursor : Qt.OpenHandCursor
    preventStealing: true
    onPressed: mouse => {
        pressPoint = mapToGlobal(mouse.x, mouse.y);
        startPosition = Qt.point(windowX, windowY);
    }
    onPositionChanged: mouse => {
        if (!pressed) return;
        const position = mapToGlobal(mouse.x, mouse.y);
        moved(startPosition.x + position.x - pressPoint.x,
              startPosition.y + position.y - pressPoint.y);
    }
    Rectangle {
        anchors.centerIn: parent
        width: 36
        height: 4
        radius: 2
        color: handle.containsMouse || handle.pressed ? Theme.inkMuted : Theme.lineStrong
        opacity: handle.containsMouse || handle.pressed ? 1 : 0.6
        Behavior on color { ColorAnimation { duration: Theme.durationFast } }
    }
}
