import QtQuick

QtObject {
    id: dock
    required property real screenWidth
    required property real screenHeight
    required property real widgetWidth
    required property real widgetHeight
    property string edge: 'top'
    property real alongX: screenWidth / 2
    property real alongY: screenHeight / 2
    readonly property real left: Theme.frameWidth
    readonly property real right: Math.max(left, screenWidth - Theme.frameWidth - widgetWidth)
    readonly property real top: Theme.barHeight + Theme.frameWidth
    readonly property real bottom: Math.max(top, screenHeight - Theme.frameWidth - widgetHeight)
    readonly property real x: edge === 'left' ? left : edge === 'right' ? right : clamp(alongX - widgetWidth / 2, Math.min(right, Theme.frameRadius), Math.max(left, right - Theme.frameRadius + Theme.frameWidth))
    readonly property real y: edge === 'top' ? top : edge === 'bottom' ? bottom : clamp(alongY - widgetHeight / 2, top, Math.max(top, bottom - Theme.frameRadius + Theme.frameWidth))
    property real animatedX: x
    property real animatedY: y
    Behavior on animatedX { NumberAnimation { duration: Theme.glideDuration; easing.type: Easing.OutCubic } }
    Behavior on animatedY { NumberAnimation { duration: Theme.glideDuration; easing.type: Easing.OutCubic } }
    function clamp(value, low, high) { return Math.max(low, Math.min(value, Math.max(low, high))); }
    function moveTo(nextX, nextY) {
        const candidates = [
            { edge: 'top', distance: Math.abs(nextY - top) },
            { edge: 'bottom', distance: Math.abs(nextY - bottom) },
            { edge: 'left', distance: Math.abs(nextX - left) },
            { edge: 'right', distance: Math.abs(nextX - right) }
        ];
        candidates.sort((a, b) => a.distance - b.distance);
        alongX = nextX + widgetWidth / 2;
        alongY = nextY + widgetHeight / 2;
        edge = candidates[0].edge;
    }
}
