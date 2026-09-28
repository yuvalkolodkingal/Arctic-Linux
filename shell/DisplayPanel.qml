pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// Brightness for every display that can report it (Quick Settings → display, Super + Ctrl + D):
// the laptop panel and DDC/CI monitors, one slider each, named by the monitor. Monitors that
// don't answer are left out. Night light and display modes add their rows through `extraRows`.
FocusScope {
    id: panel
    property var menu: null
    default property alias extraRows: extra.data

    implicitWidth: 340
    implicitHeight: list.implicitHeight
    Component.onCompleted: BrightnessService.refresh()

    MenuList {
        id: list
        anchors.fill: parent
        focus: true

        MenuHeader { title: 'Display' }
        Repeater {
            model: BrightnessService.displays
            MenuSlider {
                required property var modelData
                icon: 'brightness'
                canMute: false
                caption: BrightnessService.displays.length > 1 ? modelData.label : ''
                label: modelData.label + ' brightness'
                value: modelData.percent / 100
                onMoved: v => BrightnessService.set(modelData, Math.round(v * 100))
            }
        }
        Text {
            visible: BrightnessService.displays.length === 0
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            Layout.bottomMargin: Theme.space2
            text: 'No display here can change its brightness from the computer.'
            wrapMode: Text.WordWrap
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 13
        }
        ColumnLayout {
            id: extra
            Layout.fillWidth: true
            spacing: 0
        }
        MenuSeparator {}
        MenuRow {
            visible: Tools.has('arctic-settings')
            icon: 'sliders'
            label: 'Display settings'
            onActivated: { if (panel.menu) panel.menu.close(); Quickshell.execDetached(['arctic-settings', 'displays']); }
        }
    }
}
