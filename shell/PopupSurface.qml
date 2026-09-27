import QtQuick

// A popover card that unfolds from the edge it is docked to: the docked corners are square,
// the others radius-xl, and it opens with a fade and a short scale from that edge
// (duration-slow, ease-standard; reduced motion: fade only).
Rectangle {
    id: surface
    property real reveal: 1
    property string dockEdge: 'top'     // top, bottom, left, right, or '' for a free card
    clip: true
    function popIn() { entrance.restart(); }
    topLeftRadius: dockEdge === 'top' || dockEdge === 'left' ? 0 : radius
    topRightRadius: dockEdge === 'top' || dockEdge === 'right' ? 0 : radius
    bottomLeftRadius: dockEdge === 'bottom' || dockEdge === 'left' ? 0 : radius
    bottomRightRadius: dockEdge === 'bottom' || dockEdge === 'right' ? 0 : radius
    transform: Scale {
        readonly property real amount: Theme.reduceMotion ? 1 : 0.98 + 0.02 * surface.reveal
        origin.x: surface.dockEdge === 'left' ? 0 : surface.dockEdge === 'right' ? surface.width : surface.width / 2
        origin.y: surface.dockEdge === 'bottom' ? surface.height : surface.dockEdge === 'top' ? 0 : surface.height / 2
        xScale: surface.dockEdge === 'top' || surface.dockEdge === 'bottom' ? 1 : amount
        yScale: surface.dockEdge === 'left' || surface.dockEdge === 'right' ? 1 : amount
    }
    opacity: reveal
    Behavior on topLeftRadius { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
    Behavior on topRightRadius { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
    Behavior on bottomLeftRadius { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
    Behavior on bottomRightRadius { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
    NumberAnimation {
        id: entrance
        target: surface
        property: 'reveal'
        from: 0
        to: 1
        duration: Theme.fadeSlow
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Theme.easeEnter
    }
}
