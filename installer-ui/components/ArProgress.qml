// .ar-progress with the label row (.ar-progress-lbl). state: "", "error", "success".
import QtQuick
import ".."

Column {
    id: prog
    property real value: 0            // 0-100
    property string label: ""
    property string valueText: ""   // right-hand label ("About 6 min left")
    property string state_: ""
    property int barHeight: 6
    property bool indeterminate: false
    spacing: Theme.space2
    Accessible.role: Accessible.ProgressBar
    Accessible.name: label
    Accessible.description: valueText

    Item {
        visible: prog.label !== "" || prog.valueText !== ""
        width: parent.width
        height: 18
        ArText {
            anchors.left: parent.left
            anchors.right: rightLabel.left
            anchors.rightMargin: Theme.space3
            text: prog.label
            size: 13
            lh: 18
            elide: Text.ElideRight
            color: Theme.inkMuted
        }
        ArText {
            id: rightLabel
            anchors.right: parent.right
            text: prog.valueText !== "" ? prog.valueText : Math.round(prog.value) + "%"
            size: 13
            lh: 18
            color: Theme.inkMuted
        }
    }
    Rectangle {
        width: parent.width
        height: prog.barHeight
        radius: height / 2
        color: Theme.surfaceSunken
        border.width: 1
        border.color: Theme.line
        clip: true
        Rectangle {
            id: fill
            x: prog.indeterminate ? parent.width * 0.35 : 0
            height: parent.height
            width: prog.indeterminate ? parent.width * 0.3 : Math.max(height, parent.width * Math.max(0, Math.min(100, prog.value)) / 100)
            visible: prog.indeterminate || prog.value > 0
            radius: height / 2
            color: prog.state_ === "error" ? Theme.error : prog.state_ === "success" ? Theme.success : Theme.accent
            border.width: (!Theme.dark && prog.state_ === "") ? 1 : 0
            border.color: Theme.accentEdge
            Behavior on width {
                NumberAnimation { duration: Theme.durationBase; easing.type: Easing.BezierSpline; easing.bezierCurve: Theme.easeStandard }
            }
        }
    }
}
