// Text in the Arctic type scale: Figtree, pixel sizes and line heights from
// bundle.css (15/22 body, 13/18 help, 12/16 caption, 28/36 title-1 …).
import QtQuick
import ".."

Text {
    id: arText
    property int size: 15
    property int lh: Math.round(size * 1.47)
    property int weight: Font.Normal
    property real tracking: 0          // letter-spacing in em
    color: Theme.ink
    font.family: Theme.fontSans
    font.pixelSize: size
    font.weight: weight
    font.letterSpacing: tracking * size
    lineHeightMode: Text.FixedHeight
    lineHeight: lh
    // CSS centres the glyphs in the line box (half-leading); Qt puts the extra
    // space below. Shift the glyphs down without changing the layout height.
    // (+1: Qt draws Figtree ~1px higher than Chrome; measured against the mockups.)
    transform: Translate {
        y: Math.max(0, Math.round((arText.lh - arText.size * 1.2) / 2)) + 1
    }
    textFormat: Text.PlainText
    // Keep mixed-script rows (e.g. "עברית" in the language list) aligned with the layout.
    horizontalAlignment: Text.AlignLeft
    elide: Text.ElideNone
    Accessible.role: Accessible.StaticText
    Accessible.name: text
}
