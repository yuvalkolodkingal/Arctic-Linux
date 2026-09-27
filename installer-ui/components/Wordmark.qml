// wordmark(size): mark at 1.25× the type size, "arctic" 600 + " linux" 400 muted.
import QtQuick
import ".."

Row {
    id: wm
    property int size: 18
    spacing: Math.round(size * 0.3)
    Accessible.role: Accessible.StaticText
    Accessible.name: "Arctic Linux"

    Mark {
        size: Math.round(wm.size * 1.25)
        anchors.verticalCenter: parent.verticalCenter
    }
    Row {
        anchors.verticalCenter: parent.verticalCenter
        Text {
            text: "arctic"
            color: Theme.ink
            font.family: Theme.fontSans
            font.pixelSize: wm.size
            font.weight: Font.DemiBold
            font.letterSpacing: -0.02 * wm.size
            Accessible.ignored: true
        }
        Text {
            text: " linux"
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: wm.size
            font.weight: Font.Normal
            font.letterSpacing: -0.02 * wm.size
            Accessible.ignored: true
        }
    }
}
