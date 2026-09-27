import QtQuick
import Quickshell
import "assets/Icons.js" as Icons

// App tile: a rounded square (30% radius) in the category tint with one line glyph
// (brand book "Iconography"). Apps without a design tile show their own icon inside it.
Rectangle {
    id: tile
    property string tileId: ''          // design tile id (zen, zed, kitty, installer, …)
    property string iconName: ''        // freedesktop icon name for other apps
    property string fallbackGlyph: 'grid'
    property int size: 36
    property bool onAccent: false       // the amber Install tile on the live desktop
    readonly property var spec: Icons.app(tileId)
    readonly property string category: spec ? spec.category : 'system'
    readonly property string themedIcon: !spec && iconName ? Quickshell.iconPath(iconName, true) : ''
    width: size
    height: size
    radius: Math.round(size * 0.3)
    color: onAccent ? Theme.accent : Theme.token(Icons.tint(category))
    border.width: onAccent && !Theme.dark ? 1 : 0
    border.color: Theme.accentEdge

    Icon {
        anchors.centerIn: parent
        visible: !tile.themedIcon
        size: Math.round(tile.size * 0.55)
        name: tile.spec ? tile.spec.glyph : tile.fallbackGlyph
        color: tile.onAccent ? Theme.onAccent : tile.category === 'terminal' ? Theme.snow100 : Theme.ink
    }
    Image {
        anchors.centerIn: parent
        visible: tile.themedIcon !== ''
        width: Math.round(tile.size * 0.67)
        height: width
        sourceSize: Qt.size(width, height)
        source: tile.themedIcon
        fillMode: Image.PreserveAspectFit
        asynchronous: true
    }
}
