pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// The battery and power menu (bar battery item, Super + Ctrl + P): charge and time left, the
// power mode, the charge limit UPower offers (labelled with its real number), battery health
// and other devices' batteries. On a desktop only the power mode shows (in Quick Settings).
FocusScope {
    id: panel
    property var menu: null
    property string limitError: ''
    property bool limitBusy: false
    readonly property var b: BatteryService

    implicitWidth: 320
    implicitHeight: list.implicitHeight
    Component.onCompleted: BatteryService.refresh()

    function external(command) {
        if (menu) menu.close();
        Quickshell.execDetached(command);
    }

    MenuList {
        id: list
        anchors.fill: parent
        focus: true

        MenuHeader {
            title: panel.b.present ? 'Battery' : 'Power'
            trailingText: panel.b.present ? panel.b.percent + ' %' : ''
            detail: panel.b.present ? (panel.b.timeText + (panel.b.info.threshold_enabled && !panel.b.charging && !panel.b.full && !panel.b.onBattery
                                                           ? ' (limit ' + panel.b.info.threshold_end + ' %)' : '')) : ''
        }
        MenuSection {
            visible: PowerService.available
            text: 'Power mode'
        }
        Repeater {
            model: PowerService.available ? PowerService.modes : []
            MenuRow {
                required property var modelData
                icon: modelData.icon
                label: modelData.label
                detail: modelData.detail
                selected: PowerService.profile === modelData.profile
                Accessible.role: Accessible.RadioButton
                onActivated: PowerService.set(modelData.profile)
            }
        }
        Text {
            visible: PowerService.available && PowerService.degradation !== ''
            Layout.fillWidth: true
            Layout.leftMargin: Theme.space3
            Layout.rightMargin: Theme.space3
            Layout.bottomMargin: Theme.space1
            text: PowerService.degradation
            wrapMode: Text.WordWrap
            color: Theme.inkMuted
            font.family: Theme.fontSans
            font.pixelSize: 12
        }
        MenuSection {
            visible: panel.b.present && (panel.b.info.threshold_supported || panel.b.health)
            text: 'Battery care'
        }
        MenuSwitchRow {
            visible: panel.b.present && panel.b.info.threshold_supported === true
            label: 'Limit charging to ' + panel.b.info.threshold_end + ' %'
            detail: 'Better for the battery when it stays plugged in'
            errorText: panel.limitError
            checked: panel.b.info.threshold_enabled === true
            busy: panel.limitBusy
            onToggled: on => {
                panel.limitBusy = true;
                panel.limitError = '';
                BatteryService.setLimit(on, r => { panel.limitBusy = false; if (!r.ok) panel.limitError = r.error; });
            }
        }
        MenuRow {
            visible: panel.b.health
            icon: 'battery'
            label: 'Battery health ' + panel.b.healthPercent + ' %'
            detail: 'Of its original capacity'
        }
        MenuSection {
            visible: panel.b.peripherals.length > 0
            text: 'Other devices'
        }
        Repeater {
            model: panel.b.peripherals
            MenuRow {
                required property var modelData
                icon: BatteryService.kindOf(modelData).icon
                label: modelData.model || BatteryService.kindOf(modelData).name
                trailing: 'text'
                trailingText: Math.round(modelData.percentage > 1 ? modelData.percentage : modelData.percentage * 100) + ' %'
            }
        }
        MenuSeparator {}
        MenuRow {
            visible: Tools.has('arctic-settings')
            icon: 'sliders'
            label: 'Power settings'
            onActivated: panel.external(['arctic-settings', 'power'])
        }
    }
}
