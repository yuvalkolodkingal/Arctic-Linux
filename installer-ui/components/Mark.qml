// The fox mark with amber eyes (assets/mark-*.svg, exported from the design).
import QtQuick
import ".."

Image {
    property int size: 44
    width: size
    height: size
    sourceSize.width: size
    sourceSize.height: size
    source: Qt.resolvedUrl("../assets/mark-" + (Theme.dark ? "dark" : "light") + ".svg")
    smooth: true
    Accessible.role: Accessible.Graphic
    Accessible.name: "Arctic Linux"
}
