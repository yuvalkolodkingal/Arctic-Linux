import QtQuick
import QtQuick.Layouts

// One item on the top bar: a 26px pill, 8px side padding, 16px icon and/or 13px label.
// Hover = surface-sunken, and so is an item whose menu is open (`active`). Icon-only items
// always carry a tooltip (shown by the bar).
Rectangle {
    id: item
    property string iconName: ''
    property color iconColor: Theme.ink
    property string text: ''
    property color textColor: Theme.ink
    property int textWeight: Font.Medium
    property int maxTextWidth: 0        // > 0: the label is elided beyond this (the media title)
    property string tooltip: ''
    property bool interactive: true
    property bool accentFill: false     // the live session's amber Install item
    property bool keyboardFocused: false
    property bool hasMenu: false        // left click opens a bar menu (BarMenu)
    property bool active: false         // …and that menu is open now
    readonly property bool barStop: interactive     // reachable in the bar's keyboard mode
    function press() { clicked(); }
    default property alias extra: row.data
    signal clicked()
    signal rightClicked()
    signal middleClicked()
    signal scrolled(int steps)
    signal hoverChanged(bool hovering)

    implicitWidth: row.implicitWidth + 2 * Theme.space2
    implicitHeight: 26
    radius: 13
    color: accentFill ? (mouse.pressed ? Theme.accentPressed : mouse.containsMouse ? Theme.accentHover : Theme.accent)
                      : interactive && (mouse.containsMouse || keyboardFocused || active) ? Theme.surfaceSunken : 'transparent'
    border.width: accentFill && !Theme.dark ? 1 : 0
    border.color: Theme.accentEdge
    Behavior on color { ColorAnimation { duration: Theme.durationFast } }
    Accessible.role: hasMenu ? Accessible.ButtonMenu : Accessible.Button
    Accessible.name: tooltip || text

    FocusRing { targetRadius: item.radius; shown: item.keyboardFocused }

    RowLayout {
        id: row
        anchors.centerIn: parent
        spacing: Theme.space1
        Icon {
            visible: item.iconName !== ''
            name: item.iconName
            size: 16
            color: item.iconColor
        }
        Text {
            visible: item.text !== ''
            Layout.maximumWidth: item.maxTextWidth > 0 ? item.maxTextWidth : -1
            elide: Text.ElideRight
            text: item.text
            color: item.textColor
            font.family: Theme.fontSans
            font.pixelSize: 13
            font.weight: item.textWeight
            font.features: { 'tnum': 1 }
        }
    }
    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: item.interactive ? Qt.LeftButton | Qt.RightButton | Qt.MiddleButton : Qt.NoButton
        cursorShape: item.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
        onContainsMouseChanged: item.hoverChanged(containsMouse)
        onClicked: mouse => {
            if (mouse.button === Qt.RightButton) item.rightClicked();
            else if (mouse.button === Qt.MiddleButton) item.middleClicked();
            else item.clicked();
        }
        onWheel: wheel => { if (wheel.angleDelta.y !== 0) item.scrolled(wheel.angleDelta.y > 0 ? 1 : -1); }
    }
}
