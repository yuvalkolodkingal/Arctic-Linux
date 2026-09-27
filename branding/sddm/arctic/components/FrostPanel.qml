// A surface that floats over the wallpaper: the `frost` colour over a blurred
// copy of what is behind it (brand book: frost = frost colour + 28 px blur).
//
// The panel must be a direct child of the item that holds `backdrop` at (0, 0)
// (Main.qml's root), so its own x/y are backdrop coordinates. Where blur is
// unavailable (the software scene graph) the brand book asks for
// `surface-raised` at full opacity instead.
import QtQuick
import QtQuick.Effects
import ".."

Item {
    id: panel

    property Item backdrop
    property real radius: Theme.radiusXl
    property color tint: Theme.frost
    property color borderColor: "transparent"
    property bool shadow: false
    property bool blur: true

    // (GraphicsInfo reads Unknown until the window is exposed; treat that as
    // hardware so the first frame already has the blur.)
    readonly property bool blurAvailable: GraphicsInfo.api !== GraphicsInfo.Software
    readonly property int pad: 64

    RectangularShadow {
        visible: panel.shadow && panel.blurAvailable
        anchors.fill: parent
        offset.y: 24
        blur: 56
        spread: -12
        radius: panel.radius
        color: Theme.shadowLg
    }

    ShaderEffectSource {
        id: behind
        visible: false
        sourceItem: panel.blur && panel.blurAvailable ? panel.backdrop : null
        sourceRect: Qt.rect(panel.x - panel.pad, panel.y - panel.pad,
                            panel.width + 2 * panel.pad, panel.height + 2 * panel.pad)
        width: panel.width + 2 * panel.pad
        height: panel.height + 2 * panel.pad
    }

    Item {
        id: mask
        visible: false
        layer.enabled: true
        width: behind.width
        height: behind.height
        Rectangle {
            x: panel.pad
            y: panel.pad
            width: panel.width
            height: panel.height
            radius: panel.radius
            color: "white"
            antialiasing: true
        }
    }

    MultiEffect {
        visible: panel.blur && panel.blurAvailable
        x: -panel.pad
        y: -panel.pad
        width: behind.width
        height: behind.height
        source: behind
        autoPaddingEnabled: false
        blurEnabled: true
        blur: 1.0
        blurMax: Theme.blurLg
        saturation: 0.2
        maskEnabled: true
        maskSource: mask
        maskThresholdMin: 0.5
        maskSpreadAtMin: 1.0
    }

    Rectangle {
        anchors.fill: parent
        radius: panel.radius
        color: panel.blur && panel.blurAvailable ? panel.tint : Theme.surfaceRaised
        border.width: panel.borderColor.a > 0 ? 1 : 0
        border.color: panel.borderColor
        antialiasing: true
    }
}
