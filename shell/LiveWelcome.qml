import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Wayland

// The live USB's desktop (design LiveDesktop): a frosted "You're trying Arctic Linux" card,
// shown once per boot (arctic-welcome calls `arctic-shell-ipc welcome open`), and the
// Install tile bottom-left, which stays. Both sit on the desktop layer, under windows.
// Super + I starts the installer from anywhere.
Scope {
    id: root
    property bool cardOpen: false
    property bool cardMapped: false
    // Asked for before Session has read /proc/cmdline: show it once we know we're live.
    property bool wanted: false
    readonly property var screen: Outputs.focused

    function show() {
        wanted = true;
        if (!Session.live) return;
        wanted = false;
        cardMapped = true;
        cardOpen = true;
    }
    Connections {
        target: Session
        function onLiveChanged() { if (root.wanted && Session.live) root.show(); }
    }
    function dismiss() { cardOpen = false; }
    function install() {
        dismiss();
        Quickshell.execDetached(['arctic-start-installer']);
    }

    // ---- welcome card ----------------------------------------------------------------------
    PanelWindow {
        id: cardWindow
        screen: root.screen
        visible: root.cardMapped
        anchors { top: true; bottom: true; left: true; right: true }
        color: 'transparent'
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Bottom
        WlrLayershell.namespace: 'arctic-desktop'
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.OnDemand
        mask: Region { item: card }

        Rectangle {
            id: card
            width: 440
            height: body.implicitHeight + 2 * 28
            x: (parent.width - width) / 2
            y: parent.height / 2 - 0.46 * height
            radius: Theme.radiusXl
            color: Theme.frost
            border.width: 1
            border.color: Theme.line
            opacity: root.cardOpen ? 1 : 0
            Behavior on opacity {
                NumberAnimation {
                    duration: Theme.fadeSlow
                    easing.type: Easing.BezierSpline
                    easing.bezierCurve: Theme.easeStandard
                    onRunningChanged: if (!running && !root.cardOpen) root.cardMapped = false
                }
            }
            focus: true
            Keys.onEscapePressed: root.dismiss()

            ColumnLayout {
                id: body
                anchors.fill: parent
                anchors.margins: 28
                spacing: 0
                Mark { size: 48; color: Theme.ink; eye: Theme.accent }
                Text {
                    Layout.topMargin: 12
                    Layout.fillWidth: true
                    text: 'You’re trying Arctic Linux'
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 28
                    font.weight: Font.DemiBold
                    font.letterSpacing: -0.28
                    lineHeight: 36
                    lineHeightMode: Text.FixedHeight
                }
                Text {
                    Layout.topMargin: 4
                    Layout.fillWidth: true
                    text: 'Nothing is saved to this computer. Look around, open apps, then install when you’re ready.'
                    color: Theme.inkMuted
                    wrapMode: Text.Wrap
                    font.family: Theme.fontSans
                    font.pixelSize: 15
                    lineHeight: 22
                    lineHeightMode: Text.FixedHeight
                }
                RowLayout {
                    Layout.topMargin: 20
                    spacing: Theme.space2
                    ArcticButton {
                        id: installButton
                        variant: 'primary'
                        size: 'lg'
                        iconName: 'download'
                        text: 'Install Arctic Linux'
                        onClicked: root.install()
                    }
                    ArcticButton {
                        variant: 'ghost'
                        size: 'lg'
                        text: 'Keep trying'
                        onClicked: root.dismiss()
                    }
                }
                RowLayout {
                    Layout.topMargin: 18
                    spacing: 20
                    RowLayout {
                        spacing: Theme.space1
                        Kbd { text: 'Super' }
                        Text { text: '+'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
                        Kbd { text: 'Space' }
                        Text { text: ' apps'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12; font.weight: Font.Medium }
                    }
                    RowLayout {
                        spacing: Theme.space1
                        Kbd { text: 'Super' }
                        Text { text: '+'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12 }
                        Kbd { text: 'I' }
                        Text { text: ' install'; color: Theme.inkMuted; font.family: Theme.fontSans; font.pixelSize: 12; font.weight: Font.Medium }
                    }
                }
            }
        }
    }

    // ---- Install tile, bottom-left --------------------------------------------------------
    PanelWindow {
        screen: root.screen
        visible: Session.live
        anchors { bottom: true; left: true }
        margins.left: 24
        margins.bottom: 24
        implicitWidth: 96
        implicitHeight: tileColumn.implicitHeight + 20
        color: 'transparent'
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Bottom
        WlrLayershell.namespace: 'arctic-desktop'

        Rectangle {
            anchors.fill: parent
            radius: Theme.radiusLg
            color: tileMouse.containsMouse ? Theme.surfaceRaised : Theme.frost
            Behavior on color { ColorAnimation { duration: Theme.durationFast } }
            ColumnLayout {
                id: tileColumn
                anchors.centerIn: parent
                width: parent.width - 20
                spacing: 6
                AppTile {
                    Layout.alignment: Qt.AlignHCenter
                    size: 48
                    tileId: 'installer'
                    onAccent: true
                }
                Text {
                    Layout.fillWidth: true
                    horizontalAlignment: Text.AlignHCenter
                    wrapMode: Text.Wrap
                    text: 'Install Arctic Linux'
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    lineHeight: 16
                    lineHeightMode: Text.FixedHeight
                }
            }
            MouseArea {
                id: tileMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: root.install()
            }
        }
    }
}
