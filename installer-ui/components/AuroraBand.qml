// auroraBand(): the aurora gradient (green → teal → ice) fading down from the
// top edge. Only on Welcome and Done. Drawn as two gradients (no shaders):
// the aurora at 55% over the surface, then the surface fading in towards the bottom.
import QtQuick
import ".."

Item {
    id: band
    property color background: Theme.surface
    height: 150
    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        opacity: 0.55
        gradient: Gradient {
            orientation: Gradient.Horizontal
            GradientStop { position: 0.0; color: Theme.aurora1 }
            GradientStop { position: 0.45; color: Theme.aurora2 }
            GradientStop { position: 1.0; color: Theme.aurora3 }
        }
    }
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.rgba(band.background.r, band.background.g, band.background.b, 0) }
            GradientStop { position: 1.0; color: band.background }
        }
    }
}
