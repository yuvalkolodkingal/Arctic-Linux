pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import ".."

// Segmented control, also used as tabs: a sunken track, the selected segment in the selection
// colours (accentSoft + accentEdge). Ctrl+Tab / Ctrl+Page Down and Ctrl+Page Up switch from
// anywhere on the page (the page calls step()); clicks and Space/Enter on a focused segment too.
// model: [{key, label}]
Rectangle {
    id: control
    property var model: []
    property string current: model.length ? model[0].key : ''
    signal activated(string key)

    function step(delta) {
        if (!model.length) return;
        const at = Math.max(0, model.findIndex(m => m.key === current));
        const next = model[(at + delta + model.length) % model.length].key;
        if (next !== current) { current = next; activated(next); }
    }

    implicitHeight: Theme.controlSm + 4
    implicitWidth: row.implicitWidth + 4
    radius: Theme.radiusMd
    color: Theme.surfaceSunken
    border.width: 1
    border.color: Theme.line

    RowLayout {
        id: row
        anchors.fill: parent
        anchors.margins: 2
        spacing: 2
        Repeater {
            model: control.model
            delegate: Rectangle {
                id: segment
                required property var modelData
                readonly property bool selected: control.current === modelData.key
                Layout.fillHeight: true
                implicitWidth: label.implicitWidth + 2 * Theme.space3
                radius: Theme.radiusSm
                color: selected ? Theme.accentSoft : mouse.containsMouse ? Theme.surfaceRaised : 'transparent'
                border.width: selected ? 1 : 0
                border.color: Theme.accentEdge
                activeFocusOnTab: true
                Accessible.role: Accessible.PageTab
                Accessible.name: modelData.label
                Keys.onSpacePressed: { control.current = modelData.key; control.activated(modelData.key); }
                Keys.onReturnPressed: { control.current = modelData.key; control.activated(modelData.key); }
                Text {
                    id: label
                    anchors.centerIn: parent
                    text: segment.modelData.label
                    textFormat: Text.PlainText
                    color: segment.selected ? Theme.ink : Theme.inkMuted
                    font.family: Theme.fontSans
                    font.pixelSize: 13
                    font.weight: segment.selected ? Font.DemiBold : Font.Medium
                }
                FocusRing { targetRadius: Theme.radiusSm; shown: segment.activeFocus }
                MouseArea {
                    id: mouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { control.current = segment.modelData.key; control.activated(segment.modelData.key); }
                }
            }
        }
    }
}
