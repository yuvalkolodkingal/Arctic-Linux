import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland

// A shell surface above the desktop, below the bar: an optional scrim and one card.
//
// placement 'dock'   — the card hangs from the bar and can be dragged to any screen edge,
//                      where it docks (launcher, wallpapers, get apps).
//           'center' — a centred card (keyboard shortcuts).
//           'point'  — a menu under a bar item (power menu); set pointX to the item's centre.
// Clicking outside the card or pressing Esc dismisses it; keyboard focus returns on close.
//
// hideWhileCaptured — while the screen is recorded (arctic-record) or shared (the portal), the
//                     card shows a warning in place of its content, so a password dialog or
//                     the clipboard doesn't end up in the recording; "Show anyway" brings it
//                     back until the card closes. (Mango's shield_when_capture isn't used: it
//                     blacks out the whole layer surface, which is the whole screen here.)
PanelWindow {
    id: popover
    property bool open: false
    property string placement: 'dock'
    property bool scrim: true
    property bool grabKeyboard: true
    property string layerName: 'arctic-popover'
    property bool hideWhileCaptured: false
    property bool showAnyway: false
    readonly property string capture: RecordService.recording ? 'recorded'
                                    : PrivacyService.sharing.length > 0 ? 'shared' : ''
    readonly property bool guarded: hideWhileCaptured && capture !== '' && !showAnyway
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
    function focusContent() { if (open) (guarded ? showButton : focusItem || surface).forceActiveFocus(); }
    onGuardedChanged: focusContent()

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
            showAnyway = false;
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
        height: Math.max(popover.cardHeight, popover.guarded ? guard.implicitHeight : 0)
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
            visible: !popover.guarded
        }
        // The warning shown in place of the content while the screen is captured.
        Item {
            id: guard
            anchors.fill: parent
            visible: popover.guarded
            implicitHeight: guardBody.implicitHeight + 2 * Theme.space5
            ColumnLayout {
                id: guardBody
                anchors { left: parent.left; right: parent.right; top: parent.top; margins: Theme.space5 }
                spacing: 0
                RowLayout {
                    spacing: Theme.space3
                    Layout.fillWidth: true
                    Rectangle {
                        Layout.alignment: Qt.AlignTop
                        implicitWidth: 40
                        implicitHeight: 40
                        radius: 20
                        color: Theme.warningSoft
                        Icon { anchors.centerIn: parent; name: 'eye-off'; size: 22; color: Theme.warning }
                    }
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space1
                        Text {
                            Layout.fillWidth: true
                            text: 'Your screen is being ' + popover.capture
                            color: Theme.ink
                            font.family: Theme.fontSans
                            font.pixelSize: 20
                            font.weight: Font.DemiBold
                            wrapMode: Text.Wrap
                        }
                        Text {
                            Layout.fillWidth: true
                            text: 'This is hidden so it doesn’t show up in the '
                                  + (popover.capture === 'shared' ? 'screen share' : 'recording')
                                  + '. Stop ' + (popover.capture === 'shared' ? 'sharing' : 'recording')
                                  + ' to see it, or show it anyway.'
                            color: Theme.inkMuted
                            font.family: Theme.fontSans
                            font.pixelSize: 15
                            wrapMode: Text.Wrap
                        }
                    }
                }
                RowLayout {
                    Layout.topMargin: Theme.space6
                    Layout.fillWidth: true
                    spacing: Theme.space2
                    Item { Layout.fillWidth: true }
                    ArcticButton { variant: 'ghost'; text: 'Cancel'; onClicked: popover.close() }
                    ArcticButton { id: showButton; text: 'Show anyway'; onClicked: popover.showAnyway = true }
                }
            }
        }
    }

    ParallelAnimation {
        id: fadeOut
        NumberAnimation { target: surface; property: 'reveal'; to: 0; duration: Theme.durationFast; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeExit }
        NumberAnimation { target: shade; property: 'opacity'; to: 0; duration: Theme.durationFast }
    }
    Component.onCompleted: if (open) shade.opacity = 1
}
