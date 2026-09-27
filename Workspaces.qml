import QtQuick
import QtQuick.Controls
import Quickshell
import Quickshell.Io

Row {
    id: workspaces
    required property string monitorName
    property var entries: []
    property string error: ''
    readonly property string bridge: Quickshell.env('HOME') + '/.config/quickshell/scripts/workspaces.py'
    spacing: 4
    height: 32
    Process {
        id: events
        command: ['python3', workspaces.bridge, 'watch', workspaces.monitorName]
        running: workspaces.monitorName !== ''
        stdout: SplitParser {
            onRead: data => {
                try { const state = JSON.parse(data); workspaces.entries = state.workspaces; workspaces.error = state.error; }
                catch (e) { workspaces.error = 'Could not read workspace state'; }
            }
        }
        onExited: { workspaces.entries = []; workspaces.error = 'Workspace connection unavailable'; reconnect.restart(); }
    }
    Timer { id: reconnect; interval: 3000; onTriggered: if (!events.running) events.running = true }
    Process {
        id: switcher
        stdout: StdioCollector {
            onStreamFinished: { if (text.trim()) { try { const state = JSON.parse(text); if (state.error) workspaces.error = state.error; } catch (e) {} } }
        }
    }
    Repeater {
        model: workspaces.entries
        Button {
            id: button
            required property var modelData
            width: 32
            height: 32
            hoverEnabled: true
            onClicked: {
                if (switcher.running) return;
                switcher.command = ['python3', workspaces.bridge, 'switch', workspaces.monitorName, String(modelData.id)];
                switcher.running = true;
            }
            background: Rectangle {
                radius: 7
                color: button.modelData.active ? Theme.accent : button.hovered ? Theme.surface : 'transparent'
                border.width: button.activeFocus || button.modelData.urgent ? 1 : 0
                border.color: Theme.accent
                Behavior on color { ColorAnimation { duration: 140 } }
                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 3
                    width: button.modelData.urgent ? 12 : 4
                    height: 2
                    radius: 1
                    visible: button.modelData.occupied || button.modelData.urgent
                    color: button.modelData.active ? Theme.background : Theme.accent
                }
            }
            contentItem: Text {
                text: button.modelData.label
                color: button.modelData.active ? '#111318' : button.modelData.occupied ? Theme.text : Theme.muted
                font.family: Theme.font
                font.pixelSize: 12
                font.weight: button.modelData.active ? Font.DemiBold : Font.Normal
                horizontalAlignment: Text.AlignHCenter
                verticalAlignment: Text.AlignVCenter
            }
            ToolTip.visible: hovered
            ToolTip.text: 'Workspace ' + modelData.label + (modelData.urgent ? ' · needs attention' : '')
        }
    }
    Text {
        visible: workspaces.entries.length === 0
        height: 32
        verticalAlignment: Text.AlignVCenter
        text: workspaces.error ? 'Workspaces unavailable' : '…'
        color: Theme.muted
        font.family: Theme.font
        font.pixelSize: 11
    }
}
