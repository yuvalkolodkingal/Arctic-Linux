import QtQuick
import "assets/Icons.js" as Icons

// A design line icon (24 grid, 1.75 stroke) drawn in one token colour.
Image {
    id: icon
    property string name: 'help'
    property color color: Theme.ink
    property int size: 16
    width: size
    height: size
    sourceSize: Qt.size(size, size)
    source: Icons.icon(name, color)
    fillMode: Image.PreserveAspectFit
    smooth: true
    asynchronous: false
}
