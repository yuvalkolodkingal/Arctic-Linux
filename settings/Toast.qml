// The line at the bottom that confirms a change ("Saved · Undo") or says what went wrong
// (design: errors say what happened and what to do). Success fades after 4 s, errors after 9 s.
import QtQuick
import "components"

Item {
    id: toast
    property string kind: "success"
    property string text: ""
    property bool undo: false
    signal undoRequested()

    function show(k, t, u) {
        kind = k;
        text = t;
        undo = u;
        shown = true;
        hide.interval = k === "error" ? 9000 : 4000;
        hide.restart();
    }
    property bool shown: false
    visible: opacity > 0
    opacity: shown ? 1 : 0
    width: Math.min(560, parent ? parent.width - 2 * Theme.space6 : 560)
    height: card.height
    Behavior on opacity {
        NumberAnimation { duration: Theme.durationBase }
    }
    Accessible.role: kind === "error" ? Accessible.AlertMessage : Accessible.StaticText
    Accessible.name: text

    Timer {
        id: hide
        onTriggered: toast.shown = false
    }
    ShadowRect {
        id: card
        width: parent.width
        height: Math.max(44, content.implicitHeight + 2 * Theme.space3)
        radius: Theme.radiusLg
        elevation: 2
        color: toast.kind === "error" ? Theme.errorSoft : Theme.surfaceRaised
        border.width: 1
        border.color: toast.kind === "error" ? Theme.error : Theme.line
        Row {
            id: content
            x: Theme.space4
            anchors.verticalCenter: parent.verticalCenter
            width: parent.width - 2 * Theme.space4
            spacing: Theme.space3
            Icon {
                id: glyph
                name: toast.kind === "error" ? "x-circle" : toast.kind === "info" ? "info" : "check-circle"
                size: 20
                color: toast.kind === "error" ? Theme.error : toast.kind === "info" ? Theme.info : Theme.success
                anchors.verticalCenter: parent.verticalCenter
            }
            ArText {
                width: parent.width - glyph.width - (undoButton.visible ? undoButton.width + parent.spacing : 0) - parent.spacing
                text: toast.text
                size: 14
                lh: 20
                wrapMode: Text.WordWrap
                anchors.verticalCenter: parent.verticalCenter
            }
            ArButton {
                id: undoButton
                visible: toast.undo && Backend.mango.undo === true
                variant: "ghost"
                size: "sm"
                text: "Undo"
                gapColor: card.color
                anchors.verticalCenter: parent.verticalCenter
                onClicked: {
                    toast.shown = false;
                    toast.undoRequested();
                }
            }
        }
    }
}
