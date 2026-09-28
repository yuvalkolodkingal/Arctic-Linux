import QtQuick
import ".."

// A modal panel inside the launcher card (design Dialog): a scrim over the card that swallows
// clicks, and a raised panel, centred or docked to the right edge (`side: true`, details).
// Esc closes it (and stops there: the launcher stays open). Fades and scales like the
// popovers, without motion when reduced motion is on.
Item {
    id: sheet
    property bool open: false
    property bool side: false
    property int panelWidth: 440
    property Item initialFocus: null
    default property alias content: body.data
    readonly property alias panel: panel
    signal closed()

    function show() { open = true; Qt.callLater(() => { if (sheet.initialFocus) sheet.initialFocus.forceActiveFocus(); else panel.forceActiveFocus(); }); }
    function close() { if (open) { open = false; closed(); } }

    anchors.fill: parent
    visible: open || fade.running
    z: 50
    opacity: open ? 1 : 0
    Behavior on opacity { NumberAnimation { id: fade; duration: Theme.durationFast } }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radiusXl
        color: Theme.scrim
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons; onPressed: sheet.close() }
    }
    Rectangle {
        id: panel
        focus: true
        width: Math.min(sheet.panelWidth, sheet.width - 2 * Theme.space4)
        height: sheet.side ? sheet.height - 2 * Theme.space3 : Math.min(body.implicitHeight + 2 * Theme.space5, sheet.height - 2 * Theme.space4)
        x: sheet.side ? sheet.width - width - Theme.space3 : (sheet.width - width) / 2
        y: sheet.side ? Theme.space3 : (sheet.height - height) / 2
        radius: Theme.radiusLg
        color: Theme.surfaceRaised
        border.width: 1
        border.color: Theme.line
        scale: sheet.open || Theme.reduceMotion ? 1 : 0.97
        Behavior on scale { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.OutCubic } }
        Keys.onEscapePressed: event => { sheet.close(); event.accepted = true; }
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
        Item {
            id: body
            anchors.fill: parent
            anchors.margins: Theme.space5
            implicitHeight: childrenRect.height
        }
    }
}
