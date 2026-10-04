pragma ComponentBehavior: Bound
import QtQuick
import Quickshell
import Quickshell.Io

// Workspaces 1–5 for one monitor (design TopBar): the active one is the amber pill (the one
// amber thing on the desktop), occupied ones get a line-strong ring, empty ones are muted
// numbers, urgent ones an error ring. Fed by scripts/workspaces.py, an event-driven bridge to
// Mango (`mmsg watch all-tags`) and Hyprland (socket2) — no polling.
Grid {
    id: workspaces
    property bool vertical: false
    property real verticalWidth: 26
    property real verticalHeight: 22
    property int labelSize: 12
    columns: vertical ? 1 : Math.max(1, entries.length)
    required property string monitorName
    property var entries: []
    property string error: ''
    readonly property string bridge: Session.scripts + '/workspaces.py'
    spacing: Theme.space1
    leftPadding: vertical ? Math.max(0, (width - verticalWidth) / 2) : Theme.space1
    rightPadding: vertical ? Math.max(0, (width - verticalWidth) / 2) : Theme.space1
    topPadding: vertical ? 0 : 2
    bottomPadding: vertical ? 0 : 2
    height: vertical ? implicitHeight : 26

    Process {
        id: events
        command: ['python3', workspaces.bridge, 'watch', workspaces.monitorName]
        running: workspaces.monitorName !== ''
        stdout: SplitParser {
            onRead: data => {
                try {
                    const state = JSON.parse(data);
                    workspaces.entries = state.workspaces;
                    workspaces.error = state.error;
                } catch (e) {
                    workspaces.error = 'Could not read workspace state';
                }
            }
        }
        onExited: code => { workspaces.entries = []; workspaces.error = 'Workspace connection unavailable'; if (code !== 2) reconnect.restart(); }
    }
    // Reconnect after the compositor restarts or the bridge exits (not a poll: one retry).
    Timer { id: reconnect; interval: 3000; onTriggered: if (!events.running) events.running = true }
    Process {
        id: switcher
        stdout: StdioCollector {
            onStreamFinished: {
                if (!text.trim()) return;
                try { const state = JSON.parse(text); if (state.error) workspaces.error = state.error; } catch (e) {}
            }
        }
    }
    function activate(id) {
        if (switcher.running) return;
        switcher.command = ['python3', workspaces.bridge, 'switch', workspaces.monitorName, String(id)];
        switcher.running = true;
    }

    Repeater {
        model: workspaces.entries
        Rectangle {
            id: pill
            required property var modelData
            readonly property bool active: modelData.active
            readonly property bool occupied: modelData.occupied
            readonly property bool urgent: modelData.urgent && !modelData.active
            // The bar's keyboard mode (Bar.qml) moves through the pills too.
            property bool keyboardFocused: false
            readonly property bool barStop: true
            function press() { workspaces.activate(pill.modelData.id); }
            FocusRing { targetRadius: pill.radius; shown: pill.keyboardFocused }
            width: workspaces.vertical ? workspaces.verticalWidth : active ? 30 : 22
            height: workspaces.vertical ? workspaces.verticalHeight : 22
            radius: height / 2
            color: active ? Theme.accent : hover.containsMouse ? Theme.surfaceSunken : 'transparent'
            border.width: urgent || (occupied && !active) ? 1.5 : (active && !Theme.dark ? 1 : 0)
            border.color: urgent ? Theme.error : active ? Theme.accentEdge : Theme.lineStrong
            Behavior on width { NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard } }
            Behavior on color { ColorAnimation { duration: Theme.durationFast } }
            Text {
                anchors.centerIn: parent
                text: pill.modelData.label
                color: pill.active ? Theme.onAccent : pill.urgent ? Theme.error : pill.occupied ? Theme.ink : Theme.inkMuted
                font.family: Theme.fontSans
                font.pixelSize: workspaces.labelSize
                font.weight: Font.DemiBold
                font.features: { 'tnum': 1 }
            }
            MouseArea {
                id: hover
                anchors.fill: parent
                anchors.margins: -3
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: workspaces.activate(pill.modelData.id)
                onContainsMouseChanged: {
                    const tip = 'Workspace ' + pill.modelData.label
                        + (pill.active ? ' · current' : pill.urgent ? ' · needs attention' : pill.occupied ? '' : ' · empty');
                    if (containsMouse) workspaces.hovered(pill, tip); else workspaces.unhovered(pill);
                }
            }
        }
    }
    signal hovered(Item item, string text)
    signal unhovered(Item item)
}
