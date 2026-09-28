import QtQuick

// shadow-sm / shadow-md behind a card, as offset layers (no shader effects, so it also works
// with software rendering). A port of settings/components/ShadowRect.qml's layers, placed as a
// sibling behind the card because PopupSurface clips; it follows the card's reveal fade.
Item {
    id: root
    property Item target: null
    property int elevation: 2           // 1 shadow-sm, 2 shadow-md
    property real radius: Theme.radiusLg
    x: target ? target.x : 0
    y: target ? target.y : 0
    width: target ? target.width : 0
    height: target ? target.height : 0
    opacity: target ? target.opacity : 0
    visible: target !== null && target.visible && elevation > 0

    Rectangle {
        visible: root.elevation >= 2
        x: -2; y: 4; width: root.width + 4; height: root.height + 6
        radius: root.radius + 3
        color: Theme.dark ? '#40000000' : '#0f12171e'
    }
    Rectangle {
        x: 0; y: 1; width: root.width; height: root.height + (root.elevation >= 2 ? 2 : 1)
        radius: root.radius
        color: root.elevation >= 2 ? Theme.shadowMd : Theme.shadowSm
        opacity: root.elevation >= 2 ? 0.6 : 1
    }
}
