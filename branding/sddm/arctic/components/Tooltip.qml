// Names an icon-only control (design: Tooltip). `ink` fill, `ink-inverse`
// 12 px caption, radius-sm, 6 px above the target. Appears after 500 ms of
// hover or at once on keyboard focus.
import QtQuick
import QtQuick.Effects
import ".."

Item {
    id: tip
    property string text
    property bool hovered: false
    property bool keyboardFocus: false

    readonly property bool shown: keyboardFocus || delay.done

    width: bubble.width
    height: bubble.height
    anchors.bottom: parent.top
    anchors.bottomMargin: 6
    anchors.horizontalCenter: parent.horizontalCenter
    z: 50
    opacity: shown ? 1 : 0
    visible: opacity > 0
    Behavior on opacity { NumberAnimation { duration: Theme.durationFast } }

    Timer {
        id: delay
        property bool done: false
        interval: 500
        running: tip.hovered && !done
        onTriggered: done = true
    }
    onHoveredChanged: if (!hovered) delay.done = false

    RectangularShadow {
        anchors.fill: bubble
        offset.y: 8
        blur: 24
        spread: -6
        radius: bubble.radius
        color: Theme.shadowMd
        visible: GraphicsInfo.api !== GraphicsInfo.Software
    }
    Rectangle {
        id: bubble
        width: label.implicitWidth + 2 * Theme.space2
        height: label.implicitHeight + 2 * Theme.space1
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
            lineHeight: 16
            lineHeightMode: Text.FixedHeight
        }
    }
}
