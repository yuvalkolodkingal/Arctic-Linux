import QtQuick
import "assets/Icons.js" as Icons

// A design line icon (24 grid, 1.75 stroke) drawn in one token colour.
Image {
    id: icon
    property string name: 'help'
    property color color: Theme.ink
    property int size: 16
    // NaN keeps the static design glyph; -1 explicitly means unknown charge.
    property real batteryPercent: NaN
    width: size
    height: size
    sourceSize: Qt.size(size, size)
    source: Icons.icon(name, color, 0, batteryPercent)
    fillMode: Image.PreserveAspectFit
    smooth: true
    asynchronous: false
}
