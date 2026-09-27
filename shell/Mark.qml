import QtQuick
import "assets/Icons.js" as Icons

// The Arctic fox mark. At 20px and below it uses the 16px drawing (no eyes, wider gap).
Image {
    property int size: 18
    property color color: Theme.ink
    property color eye: 'transparent'
    width: size
    height: size
    sourceSize: Qt.size(size, size)
    source: Icons.mark(size, color, eye.a > 0 ? eye : '')
    smooth: true
}
