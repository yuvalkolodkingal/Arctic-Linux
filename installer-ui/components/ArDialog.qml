// .ar-dialog — modal card on the scrim. Esc closes.
import QtQuick
import QtQuick.Templates as T
import ".."

T.Popup {
    id: dialog
    property string title: ""
    property string body: ""
    property string iconName: ""
    property string tone: "info"
    default property alias content: extra.data
    property alias buttons: buttonRow.data

    modal: true
    focus: true
    closePolicy: T.Popup.CloseOnEscape | T.Popup.CloseOnPressOutside
    anchors.centerIn: T.Overlay.overlay
    width: 440
    padding: Theme.space5
    // T.Popup has no implicit size of its own (the styles add it).
    implicitHeight: contentItem.implicitHeight + topPadding + bottomPadding
    enter: Transition {
        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.fadeSlow }
        NumberAnimation { property: "scale"; from: Theme.reduceMotion ? 1 : 0.98; to: 1; duration: Theme.durationSlow }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.durationFast }
    }

    T.Overlay.modal: Rectangle {
        color: Theme.scrim
    }

    background: ShadowRect {
        radius: Theme.radiusXl
        elevation: 2
        color: Theme.surfaceRaised
        border.width: 1
        border.color: Theme.line
    }

    contentItem: Column {
        spacing: Theme.space6
        Accessible.role: Accessible.Dialog
        Accessible.name: dialog.title
        Row {
            width: parent.width
            spacing: Theme.space3
            Rectangle {
                visible: dialog.iconName !== ""
                width: 40
                height: 40
                radius: 20
                color: dialog.tone === "error" ? Theme.errorSoft : dialog.tone === "warning" ? Theme.warningSoft : Theme.infoSoft
                Icon {
                    anchors.centerIn: parent
                    name: dialog.iconName || "info"
                    size: 22
                    color: dialog.tone === "error" ? Theme.error : dialog.tone === "warning" ? Theme.warning : Theme.info
                }
            }
            Column {
                width: parent.width - (dialog.iconName !== "" ? 40 + parent.spacing : 0)
                spacing: Theme.space1
                ArText {
                    width: parent.width
                    text: dialog.title
                    size: 20
                    lh: 28
                    weight: Font.DemiBold
                    wrapMode: Text.WordWrap
                    Accessible.role: Accessible.Heading
                }
                ArText {
                    visible: dialog.body !== ""
                    width: parent.width
                    text: dialog.body
                    size: 15
                    lh: 22
                    wrapMode: Text.WordWrap
                    color: Theme.inkMuted
                }
                Column {
                    id: extra
                    width: parent.width
                    spacing: Theme.space2
                    topPadding: children.length ? Theme.space2 : 0
                }
            }
        }
        Row {
            id: buttonRow
            anchors.right: parent.right
            spacing: Theme.space2
        }
    }
}
