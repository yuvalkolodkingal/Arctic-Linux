import QtQuick

// Where a popover card sits: docked to the nearest screen edge (top by default, hanging from
// the bar) at the position it was dragged to. From the original shell: widgets unfold from
// an edge and snap back to the closest one when dropped.
QtObject {
    id: dock
    required property real areaWidth
    required property real areaHeight
    required property real widgetWidth
    required property real widgetHeight
    property string edge: 'top'
    property real alongX: areaWidth / 2
    property real alongY: areaHeight / 2
    // Keep a docked card clear of the frame's rounded corners.
    readonly property real corner: Theme.frameWidth > 0 ? Theme.frameRadius : 0
    readonly property real left: 0
    readonly property real right: Math.max(left, areaWidth - widgetWidth)
    readonly property real top: 0
    readonly property real bottom: Math.max(top, areaHeight - widgetHeight)
    readonly property real x: edge === 'left' ? left : edge === 'right' ? right
                              : clamp(alongX - widgetWidth / 2, left + corner, right - corner)
    readonly property real y: edge === 'top' ? top : edge === 'bottom' ? bottom
                              : clamp(alongY - widgetHeight / 2, top + corner, bottom - corner)
    property real animatedX: x
    property real animatedY: y
    Behavior on animatedX { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
    Behavior on animatedY { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
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
    function reset() { edge = 'top'; alongX = areaWidth / 2; alongY = areaHeight / 2; }
}
