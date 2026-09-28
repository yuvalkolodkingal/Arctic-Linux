import QtQuick
import Quickshell
import Quickshell.Wayland

// A shell surface above the desktop, below the bar: an optional scrim and one card.
//
// placement 'dock'   — the card hangs from the bar and can be dragged to any screen edge,
//                      where it docks (launcher, wallpapers, get apps).
//           'center' — a centred card (keyboard shortcuts).
//           'point'  — a menu under a bar item (power menu); set pointX to the item's centre.
// Clicking outside the card or pressing Esc dismisses it; keyboard focus returns on close.
PanelWindow {
    id: popover
    property bool open: false
    property string placement: 'dock'
    property bool scrim: true
    property bool grabKeyboard: true
    property string layerName: 'arctic-popover'
    property real cardWidth: 520
    property real cardHeight: 400
    property real pointX: 0
    property real cardRadius: Theme.radiusXl
    property color cardColor: Theme.frost
    property int shadow: 0              // 1 shadow-sm, 2 shadow-md (ShadowLayers behind the card)
    property bool animateSize: false    // card width/height changes animate (the bar menu)
    // Size changes animate only once the card has settled after opening, so a menu doesn't
    // grow into place while its content loads.
    property bool sizeSettled: false
    // The tallest a 'point' card may be: the screen below the bar, less a margin.
    readonly property real maxCardHeight: height - 2 * Theme.space4 - Theme.frameWidth
    property alias card: surface
    property alias dock: dockPos
    // What gets keyboard focus when the card opens (and again once the surface is mapped:
    // moving a popover to another screen recreates its window).
    property Item focusItem: null
    default property alias content: body.data
    readonly property bool shown: open || fadeOut.running
    signal dismissed()
    signal opened()

    function close() { if (open) { open = false; dismissed(); } }
    function focusContent() { if (open) (focusItem || surface).forceActiveFocus(); }

    visible: shown
    color: 'transparent'
    anchors { top: true; bottom: true; left: true; right: true }
    margins.top: Theme.topInset
    exclusionMode: ExclusionMode.Ignore
    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: layerName
    WlrLayershell.keyboardFocus: open && grabKeyboard ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    Timer { id: settle; interval: 120; onTriggered: popover.sizeSettled = popover.open }
    onOpenChanged: {
        sizeSettled = false;
        if (open) settle.restart();
        if (open) {
            fadeOut.stop();
            shade.opacity = 1;
            surface.popIn();
            surface.forceActiveFocus();
            opened();
            focusContent();
        } else {
            fadeOut.restart();
        }
    }

    onBackingWindowVisibleChanged: if (backingWindowVisible) Qt.callLater(focusContent)

    DockPosition {
        id: dockPos
        areaWidth: popover.width
        areaHeight: popover.height
        widgetWidth: surface.width
        widgetHeight: surface.height
    }

    // Scrim: dims the desktop behind modal cards; transparent for menus. Catches outside clicks.
    Rectangle {
        id: shade
        anchors.fill: parent
        color: popover.scrim ? Theme.scrim : 'transparent'
        opacity: 0
        Behavior on opacity { NumberAnimation { duration: Theme.fadeBase } }
        MouseArea {
            anchors.fill: parent
            acceptedButtons: Qt.AllButtons
            onPressed: popover.close()
        }
    }

    ShadowLayers {
        target: surface
        elevation: popover.shadow
        radius: popover.cardRadius
    }

    PopupSurface {
        id: surface
        focus: true
        width: popover.cardWidth
        height: popover.cardHeight
        radius: popover.cardRadius
        color: popover.cardColor
        border.width: Theme.lineWidth
        border.color: Theme.line
        dockEdge: popover.placement === 'dock' ? dockPos.edge : ''
        x: popover.placement === 'dock' ? dockPos.animatedX
           : popover.placement === 'point' ? Math.max(Theme.space2, Math.min(popover.pointX - width / 2, popover.width - width - Theme.space2))
           : (popover.width - width) / 2
        y: popover.placement === 'dock' ? dockPos.animatedY
           : popover.placement === 'point' ? Theme.space1 + Theme.frameWidth
           : Math.max(Theme.space4, (popover.height - height) / 2 - Theme.topInset / 2)
        Behavior on width { enabled: popover.animateSize && popover.sizeSettled; NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
        Behavior on height { enabled: popover.animateSize && popover.sizeSettled; NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
        Keys.onEscapePressed: popover.close()
        // Swallow clicks on the card itself so they don't reach the scrim.
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }
        Item {
            id: body
            anchors.fill: parent
        }
    }

    ParallelAnimation {
        id: fadeOut
        NumberAnimation { target: surface; property: 'reveal'; to: 0; duration: Theme.durationFast; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeExit }
        NumberAnimation { target: shade; property: 'opacity'; to: 0; duration: Theme.durationFast }
    }
    Component.onCompleted: if (open) shade.opacity = 1
}
