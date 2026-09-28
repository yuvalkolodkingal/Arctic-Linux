import QtQuick
import Quickshell
import "assets/Icons.js" as Icons

// App tile: a rounded square (30% radius) in the category tint with one line glyph
// (brand book "Iconography"). Apps without a design tile show their own icon inside it: a
// themed icon name, or a picture file (AppStream and web-app icons, `imageSource`).
Rectangle {
    id: tile
    property string tileId: ''          // design tile id (zen, zed, kitty, installer, …)
    property string iconName: ''        // freedesktop icon name for other apps
    property string imageSource: ''     // an absolute path or a file:// URL
    property string fallbackGlyph: 'grid'
    property string tint: ''            // a colour token for a glyph tile without a design tile
    property int size: 36
    property bool onAccent: false       // the amber Install tile on the live desktop
    readonly property var spec: Icons.app(tileId)
    readonly property string category: spec ? spec.category : 'system'
    readonly property string themedIcon: !spec && iconName ? Quickshell.iconPath(iconName, true) : ''
    readonly property string picture: spec ? '' : imageSource !== '' ? (imageSource.startsWith('/') ? 'file://' + imageSource : imageSource) : themedIcon
    readonly property string fill: !spec && tint ? tint : Icons.tint(category)
    width: size
    height: size
    radius: Math.round(size * 0.3)
    color: onAccent ? Theme.accent : Theme.token(fill)
    border.width: onAccent && !Theme.dark ? 1 : 0
    border.color: Theme.accentEdge

    Icon {
        anchors.centerIn: parent
        visible: !tile.picture || image.status === Image.Error
        size: Math.round(tile.size * 0.55)
        name: tile.spec ? tile.spec.glyph : tile.fallbackGlyph
        color: tile.onAccent ? Theme.onAccent : tile.fill === 'slate900' ? Theme.snow100 : Theme.ink
    }
    Image {
        id: image
        anchors.centerIn: parent
        visible: tile.picture !== '' && status !== Image.Error
        width: Math.round(tile.size * 0.67)
        height: width
        sourceSize: Qt.size(width, height)
        source: tile.picture
        fillMode: Image.PreserveAspectFit
        asynchronous: true
    }
}
