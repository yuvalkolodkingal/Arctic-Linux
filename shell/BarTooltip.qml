import QtQuick
import Quickshell

// The bar's tooltip (design Tooltip): ink fill, ink-inverse 12px text, radius-sm, shown under
// the hovered item after a short delay. One per bar, moved to whichever item is hovered.
PopupWindow {
    id: tip
    property Item target: null
    property string text: ''
    property Item pending: null
    property string pendingText: ''

    function request(item, message) {
        pending = item;
        pendingText = message;
        if (visible) { target = item; text = message; } else delay.restart();
    }
    function release(item) {
        if (pending === item) { pending = null; delay.stop(); }
        if (target === item) visible = false;
    }

    anchor.item: target
    anchor.rect.x: 0
    anchor.rect.y: 0
    anchor.rect.width: target ? target.width : 1
    anchor.rect.height: target ? target.height + 6 : 1
    anchor.edges: Edges.Bottom
    anchor.gravity: Edges.Bottom
    implicitWidth: label.implicitWidth + 2 * Theme.space2
    implicitHeight: label.implicitHeight + 2 * Theme.space1
    color: 'transparent'
    visible: false

    Timer {
        id: delay
        interval: 500
        onTriggered: {
            if (!tip.pending || tip.pendingText === '') return;
            tip.target = tip.pending;
            tip.text = tip.pendingText;
            tip.visible = true;
        }
    }
    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusSm
        color: Theme.ink
        Text {
            id: label
            anchors.centerIn: parent
            text: tip.text
            color: Theme.inkInverse
            font.family: Theme.fontSans
            font.pixelSize: 12
            font.weight: Font.Medium
        }
    }
}
