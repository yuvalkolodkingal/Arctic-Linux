import QtQuick
import Quickshell
import Quickshell.Wayland

// While the bar is hidden (Super + Shift + Space), what records, listens or watches still
// shows: the bar's "Mic", "Camera", "Sharing" and "Recording 01:23" pills, alone, on frost in the
// top-right corner of each screen. It takes no input, so clicks reach the window under it;
// showing the bar again gives the pills back their clicks.
PanelWindow {
    id: peek
    required property var modelData
    property var bar: null
    screen: modelData
    visible: (Session.barHidden || (bar !== null && !bar.expanded)) && indicators.urgent
    anchors { top: true; right: true }
    margins.top: Theme.frameWidth + Theme.space2
    margins.right: Theme.frameWidth + Theme.space2
    implicitWidth: box.width
    implicitHeight: box.height
    color: 'transparent'
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: 'arctic-indicators'
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
    mask: Region {}

    Rectangle {
        id: box
        width: indicators.implicitWidth + 2 * Theme.space1
        height: indicators.implicitHeight + 2 * Theme.space1
        radius: height / 2
        color: Theme.frost
        border.width: Theme.lineWidth
        border.color: Theme.line
        ModeIndicators {
            id: indicators
            anchors.centerIn: parent
            bar: null
            urgentOnly: true
        }
    }
}
