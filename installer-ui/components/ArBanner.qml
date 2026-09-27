// Inline banner (.ar-toast without shadow): info / warning / error / success,
// with icon, optional title, text (supports <b>), and an optional action link.
import QtQuick
import QtQuick.Templates as T
import ".."

Rectangle {
    id: banner
    property string kind: "info"
    property string title: ""
    property string text: ""
    property bool strong: false        // text in ink (warnings in the mockups), else muted
    property string actionText: ""
    signal action()

    readonly property string iconName: ({
            info: "info",
            warning: "alert",
            error: "x-circle",
            success: "check-circle"
        })[kind] || "info"
    readonly property color tone: kind === "warning" ? Theme.warning : kind === "error" ? Theme.error : kind === "success" ? Theme.success : Theme.info

    // .ar-toast has a 1px (transparent) border: +1px on every side
    implicitHeight: content.implicitHeight + 2 * Theme.space3 + 2
    radius: Theme.radiusLg
    color: kind === "warning" ? Theme.warningSoft : kind === "error" ? Theme.errorSoft : kind === "success" ? Theme.successSoft : Theme.infoSoft
    Accessible.role: kind === "error" ? Accessible.AlertMessage : Accessible.StaticText
    Accessible.name: title !== "" ? title : body.text.replace(/<[^>]*>/g, "")
    Accessible.description: title !== "" ? body.text.replace(/<[^>]*>/g, "") : ""

    Row {
        id: content
        x: Theme.space4 + 1
        y: Theme.space3 + 1
        width: parent.width - 2 * Theme.space4 - 2
        spacing: Theme.space3
        Icon {
            name: banner.iconName
            size: 20
            color: banner.tone
            y: banner.title !== "" ? 1 : 0
        }
        Column {
            width: parent.width - 20 - parent.spacing
            spacing: 0
            ArText {
                visible: banner.title !== ""
                width: parent.width
                text: banner.title
                size: 15
                lh: 22
                weight: Font.DemiBold
                wrapMode: Text.WordWrap
            }
            ArText {
                id: body
                visible: banner.text !== ""
                width: parent.width
                text: banner.text
                textFormat: Text.StyledText
                size: 13
                lh: 18
                wrapMode: Text.WordWrap
                color: banner.strong ? Theme.ink : Theme.inkMuted
            }
            T.AbstractButton {
                id: act
                visible: banner.actionText !== ""
                topPadding: Theme.space1
                implicitWidth: actLabel.implicitWidth
                implicitHeight: actLabel.implicitHeight + topPadding
                focusPolicy: Qt.StrongFocus
                hoverEnabled: true
                Accessible.role: Accessible.Link
                Accessible.name: banner.actionText
                onClicked: banner.action()
                Keys.onReturnPressed: event => {
                    banner.action();
                    event.accepted = true;
                }
                contentItem: ArText {
                    id: actLabel
                    text: banner.actionText
                    size: 13
                    lh: 22
                    weight: Font.DemiBold
                    color: Theme.accentText
                    font.underline: act.hovered
                }
                background: Item {
                    FocusRing {
                        show: act.visualFocus
                        radius: Theme.radiusXs
                        gapColor: banner.color
                    }
                }
            }
        }
    }
}
