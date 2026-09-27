// .ar-meter — 4 segments: 1 error, 2 warning, 3–4 success. Exposes its value.
pragma ComponentBehavior: Bound
import QtQuick
import ".."

Item {
    id: meter
    property int level: 0
    property string label: ""
    property real topPadding: 0
    implicitHeight: 4 + topPadding
    Accessible.role: Accessible.ProgressBar
    Accessible.name: "Passphrase strength: " + label
    Accessible.description: label

    Row {
        y: meter.topPadding
        width: parent.width
        spacing: Theme.space1
        Repeater {
            model: 4
            Rectangle {
                required property int index
                width: (meter.width - 3 * Theme.space1) / 4
                height: 4
                radius: 2
                readonly property bool filled: index < meter.level
                color: !filled ? Theme.surfaceSunken : meter.level === 1 ? Theme.error : meter.level === 2 ? Theme.warning : Theme.success
                border.width: filled ? 0 : 1
                border.color: Theme.line
                Behavior on color {
                    ColorAnimation { duration: Theme.durationBase }
                }
            }
        }
    }
}
