// Bluetooth: on/off and your paired devices through BlueZ (Quickshell.Bluetooth, the same
// service the bar uses); pairing a new device happens in blueman-manager, which also asks
// for PIN codes.
pragma ComponentBehavior: Bound
import QtQuick
import Quickshell.Bluetooth
import ".."
import "../components"

Page {
    id: page
    title: "Bluetooth"
    lede: "Headphones, mice, keyboards and phones."
    readonly property var adapter: Bluetooth.defaultAdapter
    readonly property var devices: adapter ? adapter.devices.values.filter(d => d.paired || d.connected) : []

    ArBanner {
        visible: page.adapter === null
        width: parent.width
        kind: "info"
        title: "No Bluetooth here"
        text: "Settings can’t find a Bluetooth adapter, or the Bluetooth service isn’t running."
    }

    Group {
        visible: page.adapter !== null
        title: "Bluetooth"
        SettingRow {
            searchKey: "bluetooth.power"
            title: "Bluetooth"
            desc: page.adapter && page.adapter.enabled ? "On, and visible as “" + page.adapter.name + "” while you pair." : "Off"
            resettable: false
            RowSwitch {
                Accessible.name: "Bluetooth"
                checked: page.adapter ? page.adapter.enabled : false
                onToggled: if (page.adapter) page.adapter.enabled = checked
            }
        }
    }

    Group {
        visible: page.adapter !== null
        title: "Devices"
        SettingRow {
            searchKey: "bluetooth.devices"
            visible: page.devices.length === 0
            title: "No devices yet"
            desc: "Pair headphones or a mouse to see them here."
            resettable: false
        }
        Repeater {
            model: page.devices
            SettingRow {
                id: device
                required property var modelData
                title: device.modelData.name || device.modelData.address
                desc: (device.modelData.connected ? "Connected" : "Not connected")
                      + (device.modelData.batteryAvailable ? " · battery " + Math.round(device.modelData.battery * 100) + "%" : "")
                resettable: false
                Row {
                    spacing: Theme.space2
                    ArButton {
                        text: device.modelData.connected ? "Disconnect" : "Connect"
                        variant: "secondary"
                        size: "sm"
                        enabled: page.adapter && page.adapter.enabled
                        gapColor: Theme.surfaceRaised
                        onClicked: device.modelData.connected ? device.modelData.disconnect() : device.modelData.connect()
                    }
                    ArButton {
                        text: "Forget"
                        variant: "ghost"
                        size: "sm"
                        gapColor: Theme.surfaceRaised
                        onClicked: device.modelData.forget()
                    }
                }
            }
        }
        SettingRow {
            title: "Pair a new device"
            desc: "Opens the Bluetooth manager, which finds devices near you and asks for codes."
            resettable: false
            enabled: Backend.caps.blueman === true
            ArButton {
                text: "Pair a device"
                iconName: "plus"
                gapColor: Theme.surfaceRaised
                onClicked: Backend.launch(["blueman-manager"])
            }
        }
    }
}
