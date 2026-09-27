// A design-system icon (24-unit line glyph, 1.75 stroke) in any colour.
// Glyph bodies come from assets/Icons.js (exported from the design bundle).
import QtQuick
import ".."
import "../assets/Icons.js" as Icons

Image {
    id: icon
    property string name: "help"
    property color color: Theme.ink
    property int size: 20
    property real stroke: 1.75
    width: size
    height: size
    sourceSize.width: size
    sourceSize.height: size
    fillMode: Image.PreserveAspectFit
    smooth: true
    asynchronous: false
    cache: true
    source: Icons.svg(name, hex(color), stroke)
    Accessible.ignored: true

    function hex(c) {
        const h = v => {
            const s = Math.round(v * 255).toString(16);
            return s.length < 2 ? "0" + s : s;
        };
        return "#" + h(c.r) + h(c.g) + h(c.b);
    }
}
