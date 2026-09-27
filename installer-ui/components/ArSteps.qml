// .ar-steps — the installer rail's step indicator. `current` is the index of the
// current step (names.length = every step done); `error` marks it with "!".
// Screen readers get "Step n of N: name, current step" (aria-current="step").
pragma ComponentBehavior: Bound
import QtQuick
import ".."

Column {
    id: steps
    property var names: []
    property int current: 0
    property bool error: false
    spacing: 2
    Accessible.role: Accessible.List
    Accessible.name: "Installation steps"

    Repeater {
        model: steps.names
        Rectangle {
            id: item
            required property int index
            required property string modelData
            readonly property string state_: index < steps.current ? "done" : index === steps.current ? (steps.error ? "error" : "current") : "todo"
            readonly property bool isCurrent: index === steps.current && !steps.error
            width: steps.width
            height: 34
            radius: Theme.radiusMd
            color: isCurrent ? Theme.surfaceRaised : "transparent"
            Accessible.role: Accessible.ListItem
            Accessible.name: "Step " + (index + 1) + " of " + steps.names.length + ": " + modelData + (state_ === "error" ? ", needs attention" : isCurrent ? ", current step" : state_ === "done" ? ", done" : "")
            Accessible.selected: index === steps.current

            // shadow-sm under the current step
            Rectangle {
                visible: item.isCurrent
                z: -1
                y: 1
                width: parent.width
                height: parent.height
                radius: parent.radius
                color: Theme.shadowSm
            }

            Row {
                x: Theme.space3
                anchors.verticalCenter: parent.verticalCenter
                spacing: Theme.space3

                Rectangle {
                    width: 22
                    height: 22
                    radius: 11
                    anchors.verticalCenter: parent.verticalCenter
                    color: item.state_ === "done" ? Theme.ink : item.state_ === "current" ? Theme.accent : item.state_ === "error" ? Theme.error : "transparent"
                    border.width: item.state_ === "todo" ? 1.5 : (item.state_ === "current" && !Theme.dark ? 1 : 0)
                    border.color: item.state_ === "todo" ? Theme.lineStrong : Theme.accentEdge
                    antialiasing: true
                    Icon {
                        visible: item.state_ === "done"
                        anchors.centerIn: parent
                        name: "check"
                        size: 13
                        stroke: 2.5
                        color: Theme.surface
                    }
                    Text {
                        visible: item.state_ !== "done"
                        anchors.centerIn: parent
                        text: item.state_ === "error" ? "!" : String(item.index + 1)
                        color: item.state_ === "current" ? Theme.inkOnAccent : item.state_ === "error" ? Theme.inkOnError : Theme.inkMuted
                        font.family: Theme.fontSans
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        Accessible.ignored: true
                    }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: item.modelData
                    color: (item.state_ === "todo" || item.state_ === "error") ? Theme.inkMuted : Theme.ink
                    font.family: Theme.fontSans
                    font.pixelSize: 14
                    font.weight: item.isCurrent ? Font.DemiBold : Font.Normal
                    Accessible.ignored: true
                }
            }
        }
    }
}
