import QtQuick
import QtQuick.Controls.Basic

// Design Tooltip inside a surface: ink fill, ink-inverse 12px text, radius-sm.
ToolTip {
    id: tip
    delay: 600
    timeout: -1
    padding: 0
    topPadding: Theme.space1
    bottomPadding: Theme.space1
    leftPadding: Theme.space2
    rightPadding: Theme.space2
    contentItem: Text {
        text: tip.text
        textFormat: Text.PlainText
        color: Theme.inkInverse
        font.family: Theme.fontSans
        font.pixelSize: 12
        font.weight: Font.Medium
    }
    background: Rectangle { radius: Theme.radiusSm; color: Theme.ink }
    enter: Transition { NumberAnimation { property: 'opacity'; from: 0; to: 1; duration: Theme.durationFast } }
    exit: Transition { NumberAnimation { property: 'opacity'; from: 1; to: 0; duration: Theme.durationFast } }
}
