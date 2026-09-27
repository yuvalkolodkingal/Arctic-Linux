import QtQuick

Rectangle {
    id: surface
    property real reveal: 1
    property string dockEdge: 'top'
    clip: true
    function popIn() { entrance.restart(); }
    opacity: 1
    topLeftRadius: dockEdge === 'top' || dockEdge === 'left' ? 0 : radius
    topRightRadius: dockEdge === 'top' || dockEdge === 'right' ? 0 : radius
    bottomLeftRadius: dockEdge === 'bottom' || dockEdge === 'left' ? 0 : radius
    bottomRightRadius: dockEdge === 'bottom' || dockEdge === 'right' ? 0 : radius
    transform: Scale {
        origin.x: surface.dockEdge === 'left' ? 0 : surface.dockEdge === 'right' ? surface.width : surface.width / 2
        origin.y: surface.dockEdge === 'bottom' ? surface.height : 0
        xScale: surface.dockEdge === 'left' || surface.dockEdge === 'right' ? surface.reveal : 1
        yScale: surface.dockEdge === 'top' || surface.dockEdge === 'bottom' ? surface.reveal : 1
    }
    Behavior on topLeftRadius { NumberAnimation { duration: Theme.glideDuration; easing.type: Easing.OutCubic } }
    Behavior on topRightRadius { NumberAnimation { duration: Theme.glideDuration; easing.type: Easing.OutCubic } }
    Behavior on bottomLeftRadius { NumberAnimation { duration: Theme.glideDuration; easing.type: Easing.OutCubic } }
    Behavior on bottomRightRadius { NumberAnimation { duration: Theme.glideDuration; easing.type: Easing.OutCubic } }
    NumberAnimation {
        id: entrance
        target: surface
        property: 'reveal'
        from: 0
        to: 1
        duration: Theme.motionDuration
        easing.type: Easing.OutQuart
    }
}
