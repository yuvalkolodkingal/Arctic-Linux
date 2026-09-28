import QtQuick

// Wi-Fi signal as a meter: the full `wifi` glyph in ink-disabled with the bars that are lit
// drawn over it in ink (weak below 34, good below 67, strong from 67: the installer's steps).
Item {
    id: meter
    property int signal: 0
    property int size: 18
    property color color: Theme.ink
    readonly property string lit: signal >= 67 ? 'wifi' : signal >= 34 ? 'wifi-2' : 'wifi-1'
    implicitWidth: size
    implicitHeight: size
    Icon { name: 'wifi'; size: meter.size; color: Theme.inkDisabled }
    Icon { name: meter.lit; size: meter.size; color: meter.color }
}
