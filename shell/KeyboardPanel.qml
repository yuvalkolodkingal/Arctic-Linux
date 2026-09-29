pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Layouts
import Quickshell

// The layout menu under the bar's layout chip (design Menu card, like the power menu): one row
// per layout with a check on the active one, and "Keyboard settings". ↑/↓ move, Enter picks,
// Esc closes. `arctic-shell-ipc keyboard menu` opens it from a key.
Popover {
    id: panel
    property int current: 0
    readonly property int count: KeyboardService.layouts.length + 1      // + Keyboard settings

    layerName: 'arctic-keyboard'
    placement: 'point'
    scrim: false
    cardColor: Theme.surfaceRaised
    cardRadius: Theme.radiusLg
    cardWidth: 260
    cardHeight: column.implicitHeight + 2 * Theme.space1
    focusItem: column
    onOpened: current = KeyboardService.index
    // One layout left (Settings changed them): nothing to pick.
    Connections {
        target: KeyboardService
        function onMultipleChanged() { if (!KeyboardService.multiple) panel.close(); }
    }

    function run(i) {
        close();
        if (i < KeyboardService.layouts.length) KeyboardService.set(i);
        else Quickshell.execDetached(['arctic-settings', 'input']);
    }

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: Theme.space1
        spacing: 0
        focus: true
        Keys.onDownPressed: panel.current = (panel.current + 1) % panel.count
        Keys.onUpPressed: panel.current = (panel.current - 1 + panel.count) % panel.count
        Keys.onTabPressed: panel.current = (panel.current + 1) % panel.count
        Keys.onReturnPressed: panel.run(panel.current)
        Keys.onEnterPressed: panel.run(panel.current)
        Keys.onSpacePressed: panel.run(panel.current)
        Keys.onEscapePressed: panel.close()

        Repeater {
            model: KeyboardService.layouts
            LayoutRow {
                required property var modelData
                required index
                menu: panel
                icon: 'keyboard'
                label: modelData.name
                trailing: modelData.short
                checked: index === KeyboardService.index
            }
        }
        Rectangle {
            Layout.fillWidth: true
            Layout.topMargin: Theme.space1
            Layout.bottomMargin: Theme.space1
            implicitHeight: 1
            color: Theme.line
        }
        LayoutRow {
            menu: panel
            index: KeyboardService.layouts.length
            icon: 'sliders'
            label: 'Keyboard settings'
        }
    }

    // One 34px row (the power menu's look): icon, label, the short name, a check when active.
    // (Inline components don't see this file's ids, so each row gets `menu`.)
    component LayoutRow: Rectangle {
        id: row
        required property var menu
        property int index: 0
        property string icon: ''
        property string label: ''
        property string trailing: ''
        property bool checked: false
        readonly property bool selected: row.menu.current === index
        Layout.fillWidth: true
        implicitHeight: 34
        radius: Theme.radiusSm
        color: selected ? Theme.surfaceSunken : 'transparent'
        Accessible.role: Accessible.MenuItem
        Accessible.name: label + (checked ? ', active' : '')
        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: Theme.space3
            anchors.rightMargin: Theme.space3
            spacing: Theme.space2
            Icon { name: row.icon; size: 18; color: Theme.ink }
            Text {
                Layout.fillWidth: true
                text: row.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
                color: Theme.ink
                font.family: Theme.fontSans
                font.pixelSize: 15
            }
            Text {
                visible: row.trailing !== ''
                text: row.trailing
                textFormat: Text.PlainText
                color: Theme.inkSubtle
                font.family: Theme.fontSans
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
            Icon {
                visible: row.checked
                name: 'check'
                size: 16
                color: Theme.accentText
            }
        }
        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPositionChanged: row.menu.current = row.index
            onClicked: row.menu.run(row.index)
        }
    }
}
