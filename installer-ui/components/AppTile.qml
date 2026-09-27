// App tile (rounded square in a category tint, one line glyph), exported from
// the design for both themes: assets/tiles/<id>-{light,dark}.svg.
import QtQuick
import ".."

Image {
    property string tile: "zen"
    property int size: 36
    width: size
    height: size
    sourceSize.width: size
    sourceSize.height: size
    source: Qt.resolvedUrl("../assets/tiles/" + tile + "-" + (Theme.dark ? "dark" : "light") + ".svg")
    smooth: true
    Accessible.ignored: true
}
