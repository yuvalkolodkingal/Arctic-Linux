import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland

// On-screen display for volume and brightness (design OSD): a 280×48 frosted pill,
// bottom centre, 44px above the edge; 20px icon, 6px progress bar, value in tabular figures.
// Muted shows the mute icon and 0. Visible for 1.2 s after the last change, then fades out
// over duration-base. Volume follows PipeWire directly (any change, from keys or apps);
// brightness is shown when `arctic-osd brightness …` calls `arctic-shell-ipc osd brightness`.
// The "message" kind is an icon and a few words, no bar (`arctic-shell-ipc osd message ICON TEXT`,
// or `arctic-osd show ICON TEXT` from scripts): Caps Lock, touchpad off, a mode turned on.
Scope {
    id: osd
    property string kind: 'volume'
    property string message: ''
    property string messageIcon: 'info'
    property int value: 0
    property bool muted: false
    property bool showing: false
    readonly property var screen: Outputs.focused

    function showVolume() {
        if (!AudioService.available) return;
        // Read the node itself: this runs from its change signal, before derived bindings update.
        const audio = AudioService.sink.audio;
        kind = 'volume';
        muted = audio.muted;
        value = muted ? 0 : Math.round(audio.volume * 100);
        reveal();
    }
    function showBrightness() {
        if (!brightness.running) brightness.running = true;
    }
    function showMessage(icon, text) {
        kind = 'message';
        messageIcon = icon || 'info';
        message = text;
        reveal();
    }
    function reveal() {
        fadeOut.stop();
        pillOpacity = 1;
        showing = true;
        hideTimer.restart();
    }
    property real pillOpacity: 0
    NumberAnimation {
        id: fadeOut
        target: osd
        property: 'pillOpacity'
        to: 0
        duration: Theme.fadeBase
        easing.type: Easing.BezierSpline
        easing.bezierCurve: Theme.easeExit
        onFinished: osd.showing = false
    }

    Connections {
        target: AudioService
        function onChanged() { osd.showVolume(); }
    }
    Process {
        id: brightness
        command: ['brightnessctl', '-m']
        stdout: StdioCollector {
            onStreamFinished: {
                // device,class,current,percent%,max
                const fields = text.trim().split('\n')[0].split(',');
                const percent = parseInt((fields[3] || '').replace('%', ''));
                if (isNaN(percent)) return;
                osd.kind = 'brightness';
                osd.muted = false;
                osd.value = percent;
                osd.reveal();
            }
        }
    }
    Timer { id: hideTimer; interval: 1200; onTriggered: fadeOut.restart() }

    PanelWindow {
        id: window
        screen: osd.screen
        visible: osd.showing
        anchors.bottom: true
        margins.bottom: 44
        implicitWidth: 280
        implicitHeight: 48
        color: 'transparent'
        exclusionMode: ExclusionMode.Ignore
        WlrLayershell.layer: WlrLayer.Overlay
        WlrLayershell.namespace: 'arctic-osd'
        WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
        mask: Region {}

        Rectangle {
            id: pill
            anchors.fill: parent
            radius: height / 2
            color: Theme.frost
            border.width: 1
            border.color: Theme.line
            opacity: osd.pillOpacity
            Accessible.role: Accessible.StatusBar
            Accessible.name: osd.kind === 'message' ? osd.message : (osd.kind === 'brightness' ? 'Brightness ' : 'Volume ') + osd.value + '%'

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space4
                anchors.rightMargin: Theme.space4
                spacing: Theme.space3
                Icon {
                    size: 20
                    name: osd.kind === 'message' ? osd.messageIcon : osd.kind === 'brightness' ? 'brightness' : osd.muted || osd.value === 0 ? 'volume-mute' : 'volume'
                    color: Theme.ink
                }
                Text {
                    visible: osd.kind === 'message'
                    Layout.fillWidth: true
                    text: osd.message
                    color: Theme.ink
                    elide: Text.ElideRight
                    font.family: Theme.fontSans
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                Rectangle {
                    visible: osd.kind !== 'message'
                    Layout.fillWidth: true
                    implicitHeight: 6
                    radius: 3
                    color: Theme.surfaceSunken
                    border.width: 1
                    border.color: Theme.line
                    Rectangle {
                        width: parent.width * Math.max(0, Math.min(100, osd.value)) / 100
                        height: parent.height
                        radius: 3
                        color: Theme.accent
                        border.width: Theme.dark ? 0 : 1
                        border.color: Theme.accentEdge
                        visible: osd.value > 0
                        Behavior on width { NumberAnimation { duration: Theme.durationFast } }
                    }
                }
                Text {
                    visible: osd.kind !== 'message'
                    Layout.preferredWidth: 32
                    horizontalAlignment: Text.AlignRight
                    text: osd.value
                    color: Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    font.features: { 'tnum': 1 }
                }
            }
        }
    }
}
