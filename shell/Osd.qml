import QtQuick
import QtQuick.Layouts
import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import "OsdModel.js" as OsdModel
import "assets/Icons.js" as Icons

// On-screen display for volume and brightness (design OSD): a 280×48 frosted pill,
// bottom centre, 44px above the edge; 20px icon, 6px progress bar, value in tabular figures.
// Muted shows the mute icon and 0. A keyboard-layout switch shows the layout's name instead of
// the bar. Visible for 1.2 s after the last change, then fades out over duration-base. Volume
// follows PipeWire directly (any change, from keys or apps); brightness is shown when
// `arctic-osd brightness …` calls `arctic-shell-ipc osd brightness`, or
// `osd brightnessLevel <percent> <monitor>` after it stepped the focused monitor (the monitor's
// name shows when there is more than one screen). Plugging in or unplugging a laptop shows
// "Charging" / "On battery". Two kinds for everything else (OsdModel.js): a level, the same pill
// with any icon and an optional label (`osd level ICON PERCENT LABEL`), and a notice, an icon and
// a few words with an optional detail and no bar (`osd notice ICON TEXT DETAIL`, `arctic-osd
// notice …` from scripts: Caps Lock, a mode turned on); a notice stays a little longer the more
// it says.
Scope {
    id: osd
    property string kind: 'volume'     // volume, brightness, level, notice
    property string icon: 'info'        // level and notice
    property string text: ''            // notice text, or a level's label
    property string detail: ''
    property int value: 0
    property bool muted: false
    property bool showing: false
    property string label: ''           // the layout's name (kind 'layout'), the power source, a monitor
    readonly property bool textOnly: kind === 'layout' || kind === 'power'
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
    function showLayout(name) {
        kind = 'layout';
        label = name;
        reveal();
    }
    function showBrightness() {
        if (!brightness.running) brightness.running = true;
    }
    function showLevel(iconName, percent, label) {
        kind = 'level';
        icon = OsdModel.icon(iconName, Icons.has);
        text = label || '';
        muted = false;
        value = Math.max(0, Math.min(100, percent));
        reveal();
    }
    function showNotice(iconName, words, more) {
        kind = 'notice';
        icon = OsdModel.icon(iconName, Icons.has);
        text = words || '';
        detail = more || '';
        reveal();
    }
    function showBrightnessLevel(percent, monitor) {
        kind = 'brightness';
        muted = false;
        value = Math.max(0, Math.min(100, percent));
        label = Quickshell.screens.length > 1 ? monitor : '';
        reveal();
    }
    function showPower(onBattery) {
        kind = 'power';
        label = onBattery ? 'On battery' : BatteryService.full ? 'Plugged in' : 'Charging';
        reveal();
    }
    function reveal() {
        fadeOut.stop();
        pillOpacity = 1;
        showing = true;
        hideTimer.interval = OsdModel.duration(kind, text, detail);
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
    Connections {
        target: KeyboardService
        function onSwitched(name) { osd.showLayout(name); }
    }
    // Plugged in or unplugged, on a laptop; not UPower's first report after start-up.
    Timer { id: powerSettle; interval: 5000; running: true }
    Connections {
        target: BatteryService
        function onOnBatteryChanged() {
            if (!powerSettle.running && BatteryService.present) osd.showPower(BatteryService.onBattery);
        }
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
                osd.label = '';
                osd.value = percent;
                osd.reveal();
            }
        }
    }
    Timer { id: hideTimer; interval: 1200; onTriggered: fadeOut.restart() }
    // How wide a notice's words are, for the pill's width.
    TextMetrics { id: noticeText; font: noticeLabel.font; text: osd.text }
    TextMetrics { id: noticeDetail; font: noticeMore.font; text: '· ' + osd.detail }

    PanelWindow {
        id: window
        screen: osd.screen
        visible: osd.showing
        anchors.bottom: true
        margins.bottom: 44
        // icon 20 + gaps + the words (+ the detail) + the side margins
        implicitWidth: OsdModel.width(osd.kind, 2 * Theme.space4 + 20 + Theme.space3 + noticeText.advanceWidth
                                                + (osd.detail ? Theme.space3 + Math.min(180, noticeDetail.advanceWidth) : 0) + 4)
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
            Accessible.name: osd.kind === 'notice' ? osd.text + (osd.detail ? ', ' + osd.detail : '')
                             : osd.kind === 'layout' ? 'Keyboard layout ' + osd.label : osd.kind === 'power' ? osd.label
                             : (osd.kind === 'level' ? osd.text + ' ' : osd.kind === 'brightness' ? 'Brightness ' + (osd.label ? osd.label + ' ' : '')
                                : 'Volume ') + osd.value + '%'

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space4
                anchors.rightMargin: Theme.space4
                spacing: Theme.space3
                Icon {
                    size: 20
                    name: osd.kind === 'notice' || osd.kind === 'level' ? osd.icon : osd.kind === 'layout' ? 'keyboard'
                          : osd.kind === 'power' ? (osd.label === 'On battery' ? 'battery' : 'battery-charging')
                          : osd.kind === 'brightness' ? 'brightness' : osd.muted || osd.value === 0 ? 'volume-mute' : 'volume'
                    color: Theme.ink
                }
                // Notice: the words, then the detail after " · " (elided when too long).
                Text {
                    id: noticeLabel
                    visible: osd.kind === 'notice'
                    Layout.fillWidth: true
                    text: osd.text
                    color: Theme.ink
                    elide: Text.ElideRight
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    id: noticeMore
                    visible: osd.kind === 'notice' && osd.detail !== ''
                    Layout.maximumWidth: 180
                    text: '· ' + osd.detail
                    color: Theme.inkMuted
                    elide: Text.ElideRight
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                }
                Text {
                    visible: osd.kind === 'level' && osd.text !== ''
                    Layout.maximumWidth: 96
                    text: osd.text
                    color: Theme.inkMuted
                    elide: Text.ElideRight
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                }
                Text {
                    // Which monitor the brightness keys changed (with more than one screen).
                    visible: osd.kind === 'brightness' && osd.label !== ''
                    Layout.maximumWidth: 88
                    elide: Text.ElideRight
                    text: osd.label
                    color: Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 12
                }
                Rectangle {
                    visible: osd.kind !== 'notice' && !osd.textOnly
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
                    readonly property bool layout: osd.textOnly
                    visible: osd.kind !== 'notice'
                    Layout.preferredWidth: layout ? -1 : 32
                    Layout.fillWidth: layout
                    horizontalAlignment: layout ? Text.AlignLeft : Text.AlignRight
                    elide: Text.ElideRight
                    text: layout ? osd.label : osd.value
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
