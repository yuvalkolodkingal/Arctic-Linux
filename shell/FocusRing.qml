import QtQuick

// The design focus ring: a 2px gap in the surface colour, then 2px solid amber (`focus`).
// Shown only for keyboard focus.
Rectangle {
    property Item target: parent
    property real targetRadius: 0
    property bool shown: false
    anchors.fill: target
    anchors.margins: -2 * Theme.focusWidth
    radius: targetRadius > 0 ? targetRadius + 2 * Theme.focusWidth : 0
    color: 'transparent'
    border.width: Theme.focusWidth
    border.color: Theme.focus
    visible: shown
    z: 10
}
