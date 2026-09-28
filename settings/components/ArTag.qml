// .ar-tag — small uppercase label: default (warm), "accent" or "info".
import QtQuick
import ".."

Rectangle {
    id: tag
    property string text: ""
    property string kind: ""
    property int textSize: 11
    property int hpad: Theme.space2
    implicitWidth: label.implicitWidth + 2 * hpad
    implicitHeight: 20
    radius: Theme.radiusSm
    color: kind === "accent" ? Theme.accent : kind === "info" ? Theme.infoSoft : Theme.warmSoft

    ArText {
        id: label
        anchors.centerIn: parent
        text: tag.text.toUpperCase()
        size: tag.textSize
        lh: 16
        weight: Font.DemiBold
        tracking: 0.06
        color: tag.kind === "accent" ? Theme.inkOnAccent : tag.kind === "info" ? Theme.info : Theme.warm
    }
}
